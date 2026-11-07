"""
Il valutatore della fabbrica (docs/82 P4, lavoro L3a): da una strategia ai bp netti e alle misure.

    costi = Costi(df, pezzi.costi("ricerca"))       # commissione taker, spread di un passo, funding, pip
    v = Valutatore(blocchi, cache, costi)            # cache dello stesso df
    m = v.valuta(strategia)                          # Misure: trade, bp, t, EV, drawdown, peso del migliore
    passa, motivo = qualita_1(m, config["qualita_1"])
    trade_completi(strategia, v, costi_dict)         # gli stessi trade con MotoreVeloce.run, per il passo 9

- Il percorso corto usa il ciclo del motore veloce (motore_veloce._ciclo), che decide i trade, e calcola i bp netti
  con le stesse operazioni di metriche.bp_per_trade: commissione taker sui due lati, spread di un passo per trade,
  funding trade per trade sui perpetual (exchange.funding_per_trade). Non costruisce le tabelle del motore completo.
  Il collaudo più importante della fabbrica è che dia gli stessi bp di MotoreVeloce.run + bp_per_trade.
- Il segnale è quello di exit_search_bt: trigger E filtri, né la barra del segnale né quella d'ingresso in quarantena
  (mercato_nullo.barre_utili, che toglie anche l'ultima barra), e uno stop o un target acceso devono avere la soglia
  alla barra d'ingresso. La regola d'uscita non passa dalla quarantena.
- t netto in bp (giudizio.t_stat): è il numero che l'ottimizzatore massimizza, per ogni strategia calcolabile
  (decisione del 07/11); la condizione di qualità 1 decide solo alla fine. NaN solo se il t non si può calcolare.
- id_strategia: l'impronta di symbol, timeframe, lato, blocchi e valori in barre (docs/82 P8). Un parametro cambiato è
  una strategia nuova; la stessa strategia, da qualunque giro arrivi, ha la stessa impronta.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from engine.exchange import _importi_funding, aggiungi_funding, aggiungi_spread_passo
from engine.giudizio import t_stat
from engine.mercato_nullo import barre_utili
from engine.metriche import bp_per_trade
from engine.montecarlo import drawdown_da_zero
from engine.motore_veloce import MotoreVeloce, _ciclo, stop_dalla_barra_dopo
from engine.quarantena_trade import costo_extra_pips


# ------------------------------------------------------------------ la strategia
def _nativo(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    return v


@dataclass(frozen=True)
class Strategia:
    """Una teoria con tutti i numeri. `valori` = ((blocco, ((parametro, valore), ...)), ...), nell'ordine dei blocchi."""
    lato: int
    trigger: str
    filtri: tuple
    uscita: str
    valori: tuple

    @classmethod
    def da_teoria(cls, teoria, valori: dict) -> "Strategia":
        blocchi = (teoria.trigger, *teoria.filtri, teoria.uscita)
        estranei = set(valori) - set(blocchi)
        if estranei:
            raise ValueError(f"valori per blocchi che la teoria non ha: {sorted(estranei)}")
        return cls(int(teoria.lato), teoria.trigger, tuple(teoria.filtri), teoria.uscita,
                   tuple((n, tuple(sorted((k, _nativo(v)) for k, v in valori.get(n, {}).items()))) for n in blocchi))

    @property
    def blocchi(self) -> tuple:
        return (self.trigger, *self.filtri, self.uscita)

    @property
    def teoria_id(self) -> str:
        return f"{'L' if self.lato == 1 else 'S'}|{self.trigger}|{'+'.join(self.filtri) or '-'}|{self.uscita}"

    def valori_di(self, nome: str) -> dict:
        return dict(dict(self.valori)[nome])

    def come_dict(self) -> dict:
        return {"lato": self.lato, "trigger": self.trigger, "filtri": list(self.filtri), "uscita": self.uscita,
                "valori": {n: dict(v) for n, v in self.valori}}


def id_strategia(strategia: Strategia, symbol: str, timeframe: str) -> str:
    """L'impronta della strategia: symbol, timeframe, lato, blocchi e valori in barre."""
    testo = json.dumps([symbol, timeframe, strategia.lato, strategia.trigger, list(strategia.filtri), strategia.uscita,
                        [[n, [list(kv) for kv in v]] for n, v in strategia.valori]],
                       ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()[:20]


# ------------------------------------------------------------------ i costi
class Costi:
    """
    I costi del pezzo (vetrina.costi_storico via Pezzi.costi), preparati per il percorso corto: commissione per lato,
    spread di un passo in pips, pip, e il funding già cumulato barra per barra (None = spot).
    """

    def __init__(self, df: pd.DataFrame, costi: dict):
        if float(costi.get("spread", 0.0) or 0.0) != 0.0:
            raise ValueError("la fabbrica lavora sui symbol da exchange: lo spread sta fuori dal prezzo di fill (docs/71)")
        self.commission = float(costi["commission"])
        self.pip = float(costi["pip_size"])
        self.spread_passo_pips = costi.get("spread_passo_pips")
        self.funding = costi.get("funding")
        self._pos = self._cumulata = None
        if self.funding is not None:
            S, cumulata = _importi_funding(df, self.funding)
            self._pos = np.asarray(S.searchsorted(pd.DatetimeIndex(df.index), side="right"), dtype=np.int64)
            self._cumulata = np.asarray(cumulata, dtype=float)

    def funding_pips(self, lato: np.ndarray, eb: np.ndarray, xb: np.ndarray) -> np.ndarray:
        """Come exchange.funding_per_trade: le liquidazioni con ingresso < S <= uscita, + = pagato."""
        if self._pos is None:
            return np.zeros(len(eb))
        segno = np.where(lato > 0, 1.0, -1.0)
        return segno * (self._cumulata[self._pos[xb]] - self._cumulata[self._pos[eb]]) / self.pip


# ------------------------------------------------------------------ le misure
@dataclass(frozen=True)
class Misure:
    trade: int
    totale_bp: float
    ev_bp: float
    t: float
    dd_bp: float
    peso_max: float          # il trade migliore / la somma dei trade in guadagno
    totale_su_dd: float

    def come_dict(self) -> dict:
        return asdict(self)


def misure_da_bp(bp) -> Misure:
    x = np.asarray(bp, dtype=float)
    n = int(x.size)
    if n == 0:
        return Misure(0, 0.0, math.nan, math.nan, 0.0, math.nan, math.nan)
    totale = float(x.sum())
    dd = drawdown_da_zero(x)
    guadagni = float(x[x > 0].sum())
    peso = float(x.max()) / guadagni if guadagni > 0 else math.nan
    if dd > 0:
        su_dd = totale / dd
    else:
        su_dd = math.inf if totale > 0 else math.nan
    return Misure(n, totale, float(x.mean()), t_stat(x), float(dd), peso, su_dd)


def qualita_1(m: Misure, q: dict) -> tuple[bool, str]:
    """Condizione di qualità 1 (docs/82 P4): (passa, motivo). Il motivo è vuoto se passa."""
    if m.trade < q["trade_min"]:
        return False, f"{m.trade} trade, meno di {q['trade_min']}"
    if not m.ev_bp > q["ev_min_bp"]:
        return False, f"EV netto {m.ev_bp:.2f} bp, non sopra {q['ev_min_bp']}"
    if not m.peso_max <= q["peso_max"]:
        return False, f"il trade migliore pesa il {100 * m.peso_max:.1f}% dei guadagni, oltre il {100 * q['peso_max']:.0f}%"
    if not m.totale_su_dd >= q["totale_su_dd_min"]:
        return False, f"totale / drawdown {m.totale_su_dd:.2f}, sotto {q['totale_su_dd_min']}"
    return True, ""


def obiettivo(m: Misure) -> float:
    """Il numero che l'ottimizzatore massimizza: il t netto in bp, NaN se non si può calcolare (07/11)."""
    return m.t if m.t == m.t else math.nan


# ------------------------------------------------------------------ il valutatore
def _acceso(perc) -> bool:
    return perc not in (None, 0)


def _alla_barra_dopo(ok: np.ndarray) -> np.ndarray:
    """ok della barra d'ingresso letto alla barra del segnale: ok.shift(-1, fill_value=False)."""
    return np.r_[ok[1:], False]


class Valutatore:
    """Vedi la testa del file. `blocchi`: i Blocco della config; `cache`: la Cache del pezzo."""

    def __init__(self, blocchi, cache, costi: Costi):
        self.blocchi = {b.nome: b for b in blocchi}
        self.cache, self.costi = cache, costi
        df = cache.df
        self._o, self._h, self._l = (np.ascontiguousarray(df[c].to_numpy(np.float64)) for c in ("Open", "High", "Low"))
        self._utili = barre_utili(df)
        self._falso = np.zeros(len(df), np.bool_)
        self._nan = np.full(len(df), np.nan)

    def segnali(self, s: Strategia) -> dict:
        """Le colonne che il motore riceve: segnale, regola d'uscita, barre, stop e target del lato."""
        c, lato = self.cache, s.lato
        seg = self.blocchi[s.trigger].maschera(c, lato, s.valori_di(s.trigger) or None)
        for f in s.filtri:
            seg = seg & self.blocchi[f].maschera(c, lato, s.valori_di(f) or None)
        u = self.blocchi[s.uscita]
        vu = s.valori_di(s.uscita)
        regola = u.maschera(c, lato, vu)
        soglie = u.soglie(c, lato, vu)
        ok = np.ones(len(seg), dtype=bool)
        if _acceso(vu["perc_stop"]):
            ok &= ~np.isnan(soglie["sl"])
        if _acceso(vu["target"]):
            ok &= ~np.isnan(soglie["tp"])
        seg = np.ascontiguousarray(seg & self._utili & _alla_barra_dopo(ok))
        return {"segnale": seg, "regola": np.ascontiguousarray(regola, dtype=np.bool_), "barre": soglie["barre"],
                "sl": np.ascontiguousarray(soglie["sl"], dtype=np.float64),
                "tp": np.ascontiguousarray(soglie["tp"], dtype=np.float64)}

    def trade(self, s: Strategia) -> tuple:
        """(lato, barra d'ingresso, barra d'uscita, prezzo d'ingresso, prezzo d'uscita) dei trade chiusi."""
        g = self.segnali(s)
        f, n = self._falso, self._nan
        if s.lato == 1:
            colonne = (g["segnale"], f, g["regola"], f, g["sl"], g["tp"], n, n)
        else:
            colonne = (f, g["segnale"], f, g["regola"], n, n, g["sl"], g["tp"])
        lato, eb, xb, ep, xp, _, _, _, errore = _ciclo(self._o, self._h, self._l, *colonne, int(g["barre"]),
                                                       int(g["barre"]), 0.0, False, bool(stop_dalla_barra_dopo()))
        if errore >= 0:
            raise ValueError(f"stop o target non positivo alla barra {errore}: la frazione delle soglie adattive è >= 1")
        return lato, eb, xb, ep, xp

    def bp(self, s: Strategia) -> np.ndarray:
        """I bp netti per trade, con le operazioni di metriche.bp_per_trade nello stesso ordine."""
        lato, eb, xb, ep, xp = self.trade(s)
        c = self.costi
        segno = np.where(lato > 0, 1, -1)
        netti = (xp - ep) / c.pip * segno - c.commission * (ep + xp) / c.pip
        if c.spread_passo_pips is not None:
            netti = netti - (0.0 + float(c.spread_passo_pips))
        if c.funding is not None:
            netti = netti - c.funding_pips(lato, eb, xb)
        return netti * (c.pip * 10_000.0 / ep)

    def valuta(self, s: Strategia) -> Misure:
        return misure_da_bp(self.bp(s))


def trade_completi(s: Strategia, valutatore: Valutatore, costi: dict) -> pd.DataFrame:
    """
    Gli stessi trade con il motore completo (MotoreVeloce.run) e i costi come in exit_search_bt (CostoExtraPips,
    FundingPips), più le colonne BpLordi e BpNetti di metriche.bp_per_trade. Per il passo 9 e per il collaudo.
    """
    df = valutatore.cache.df
    g = valutatore.segnali(s)
    df_bt = df[["Open", "High", "Low", "Close"]].copy()
    verso = "long" if s.lato == 1 else "short"
    altro = "short" if s.lato == 1 else "long"
    df_bt[f"sl_{verso}"], df_bt[f"tp_{verso}"] = g["sl"], g["tp"]
    df_bt[f"sl_{altro}"], df_bt[f"tp_{altro}"] = np.nan, np.nan
    df_bt["__segnale"], df_bt["__regola"] = g["segnale"], g["regola"]
    motore = MotoreVeloce(df_bt, cash=costi.get("cash", 10_000_000), spread=float(costi.get("spread", 0.0) or 0.0),
                          commission=float(costi["commission"]), margin=1.0, exclusive_orders=True)
    colonne = ({"long_col": "__segnale", "exit_rule_long_col": "__regola"} if s.lato == 1
               else {"short_col": "__segnale", "exit_rule_short_col": "__regola"})
    stats = motore.run(n_barre=int(g["barre"]), **colonne)
    pip = float(costi["pip_size"])
    trades = costo_extra_pips(stats["_trades"], df, False, 0.0, None, pip)
    trades = aggiungi_funding(trades, df, costi.get("funding"), pip)
    trades = aggiungi_spread_passo(trades, costi.get("spread_passo_pips"))
    lordi, netti = bp_per_trade(trades, pip, float(costi["commission"]))
    trades["BpLordi"], trades["BpNetti"] = lordi.to_numpy(), netti.to_numpy()
    return trades
