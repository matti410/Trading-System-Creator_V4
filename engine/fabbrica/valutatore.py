"""
Il valutatore della fabbrica (docs/82 P4, lavoro L3a; più monete, §14): da una strategia ai risultati netti e alle misure.

    costi = Costi(df, pezzi.costi("ricerca"))       # commissione taker, spread di un passo, funding, pip
    v = Valutatore(blocchi, cache, costi)            # una moneta: cache dello stesso df
    vl = ValutatoreLista(blocchi, caches, costi)     # la lista (§14): {symbol: Cache}, {symbol: Costi}
    m = vl.valuta(strategia)                         # Misure: trade, ATR, t, EV, drawdown, peso del migliore, bp accanto
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
- id_strategia: l'impronta della lista di monete, timeframe, lato, blocchi e valori in barre (docs/82 P8). Un parametro
  cambiato è una strategia nuova; la stessa strategia, da qualunque giro arrivi, ha la stessa impronta.
- Più monete (20/11, docs/82 §14.1–§14.2): una strategia è una regola applicata a una lista di monete; i trade di tutte
  vanno in un solo elenco, in ordine d'ingresso sull'orologio comune (a parità, nell'ordine della lista). Decide
  l'ATR: ogni trade è il netto diviso l'ATR giornaliero a 5 giornate chiuse noto al segnale
  (indicatori.atr_giornaliero_chiuso); i trade delle prime giornate, senza ATR, non entrano. I bp accanto, da leggere.
  Il t (t_sovrapposti): stagionalita.errore_sovrapposti con le barre d'ingresso sull'orologio, H = le barre massime
  dell'uscita e la correzione n/(n-1), come event_study: due trade di qualunque moneta a meno di H barre contano per
  intero. Senza trade a meno di H barre il t è giudizio.t_stat, al bit.
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
from engine.indicatori import atr_giornaliero_chiuso
from engine.mercato_nullo import barre_utili
from engine.metriche import bp_per_trade, pips_per_trade
from engine.montecarlo import drawdown_da_zero
from engine.motore_veloce import MotoreVeloce, _ciclo, stop_dalla_barra_dopo
from engine.quarantena_trade import costo_extra_pips
from engine.stagionalita import barre_settimana, errore_sovrapposti

from .dati import orologio


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


def id_strategia(strategia: Strategia, monete, timeframe: str) -> str:
    """L'impronta della strategia: la lista di monete (docs/82 §14), timeframe, lato, blocchi e valori in barre."""
    if isinstance(monete, str):
        raise ValueError("id_strategia vuole la lista delle monete (docs/82 §14), anche di una moneta sola.")
    testo = json.dumps([list(monete), timeframe, strategia.lato, strategia.trigger, list(strategia.filtri), strategia.uscita,
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
    """Le misure di una strategia sulla lista, in ATR (decide, docs/82 §14.1); ev_bp accanto, da leggere."""
    trade: int
    totale_atr: float
    ev_atr: float
    t: float
    dd_atr: float
    peso_max: float          # il trade migliore / la somma dei trade in guadagno
    totale_su_dd: float
    ev_bp: float

    def come_dict(self) -> dict:
        return asdict(self)


def t_sovrapposti(x, pos, H: int, settimana: int) -> float:
    """
    Il t dei trade `x` (in ordine di `pos`, le barre d'ingresso sull'orologio comune, crescenti) con l'incertezza dei
    rendimenti sovrapposti (docs/82 §14.2): stagionalita.errore_sovrapposti(x − media, H, settimana, pos,
    correzione_n=True), come event_study._errore_standard_sovrapposti. t = media × n / errore, scritto come
    giudizio.t_stat × √(diagonale) / errore: senza trade a meno di H barre l'errore è la radice della diagonale e il t
    è t_stat, al bit. NaN se t_stat non si calcola.
    """
    x = np.asarray(x, dtype=float)
    t0 = t_stat(x)
    if not np.isfinite(t0):
        return math.nan
    n = x.size
    u = x - x.mean()
    se, _ = errore_sovrapposti(u, int(H), int(settimana), pos=np.asarray(pos), correzione_n=True)
    diagonale = float((u ** 2).sum())
    diagonale = diagonale * n / (n - 1)
    if not (np.isfinite(se) and se > 0):
        return math.nan
    return float(t0 * (float(np.sqrt(diagonale)) / se))


def misure_lista(x_atr, bp, pos, H: int, settimana: int) -> Misure:
    """
    Le misure dei trade di una lista (già in ordine d'ingresso sull'orologio): EV, totale, drawdown e peso del migliore
    in ATR, t con t_sovrapposti; i trade senza ATR (prime giornate) non entrano. ev_bp sugli stessi trade.
    """
    x = np.asarray(x_atr, dtype=float)
    ok = np.isfinite(x)
    x, b, p = x[ok], np.asarray(bp, dtype=float)[ok], np.asarray(pos)[ok]
    n = int(x.size)
    if n == 0:
        return Misure(0, 0.0, math.nan, math.nan, 0.0, math.nan, math.nan, math.nan)
    totale = float(x.sum())
    dd = drawdown_da_zero(x)
    guadagni = float(x[x > 0].sum())
    peso = float(x.max()) / guadagni if guadagni > 0 else math.nan
    if dd > 0:
        su_dd = totale / dd
    else:
        su_dd = math.inf if totale > 0 else math.nan
    return Misure(n, totale, float(x.mean()), t_sovrapposti(x, p, H, settimana), float(dd), peso, su_dd,
                  float(b.mean()))


def unisci(per_moneta: dict) -> dict:
    """
    I trade di più monete in un solo elenco, in ordine d'ingresso sull'orologio (a parità, nell'ordine della lista).
    `per_moneta` = {symbol: {"pos", "atr", "bp", ...}} con array della stessa lunghezza; ritorna gli stessi campi uniti
    e «moneta» (il symbol di ogni trade).
    """
    monete = list(per_moneta)
    if not monete:
        return {"pos": np.zeros(0, dtype=np.int64), "atr": np.zeros(0), "bp": np.zeros(0), "moneta": np.array([], dtype=object)}
    campi = list(per_moneta[monete[0]])
    tutto = {c: np.concatenate([np.asarray(per_moneta[m][c]) for m in monete]) for c in campi}
    tutto["moneta"] = np.concatenate([np.full(len(per_moneta[m]["pos"]), m, dtype=object) for m in monete])
    ordine = np.argsort(tutto["pos"], kind="stable")
    return {c: v[ordine] for c, v in tutto.items()}


def qualita_1(m: Misure, q: dict) -> tuple[bool, str]:
    """Condizione di qualità 1 (docs/82 P4; EV in ATR dal 20/11, §14): (passa, motivo). Il motivo è vuoto se passa."""
    if m.trade < q["trade_min"]:
        return False, f"{m.trade} trade, meno di {q['trade_min']}"
    if not m.ev_atr > q["ev_min"]:
        return False, f"EV netto {m.ev_atr:.4f} ATR, non sopra {q['ev_min']}"
    if not m.peso_max <= q["peso_max"]:
        return False, f"il trade migliore pesa il {100 * m.peso_max:.1f}% dei guadagni, oltre il {100 * q['peso_max']:.0f}%"
    if not m.totale_su_dd >= q["totale_su_dd_min"]:
        return False, f"totale / drawdown {m.totale_su_dd:.2f}, sotto {q['totale_su_dd_min']}"
    return True, ""


def obiettivo(m: Misure) -> float:
    """Il numero che l'ottimizzatore massimizza: il t netto (in ATR dal 20/11), NaN se non si può calcolare (07/11)."""
    return m.t if m.t == m.t else math.nan


# ------------------------------------------------------------------ il valutatore
def _acceso(perc) -> bool:
    return perc not in (None, 0)


def _alla_barra_dopo(ok: np.ndarray) -> np.ndarray:
    """ok della barra d'ingresso letto alla barra del segnale: ok.shift(-1, fill_value=False)."""
    return np.r_[ok[1:], False]


class Valutatore:
    """
    Vedi la testa del file: una moneta. `blocchi`: i Blocco della config; `cache`: la Cache del pezzo. `inizio`: i segnali
    prima di quella barra sono spenti (selezione e cassaforte: ogni trade nasce nel loro pezzo); 0 = nessuno.
    """

    def __init__(self, blocchi, cache, costi: Costi, inizio: int = 0):
        self.blocchi = {b.nome: b for b in blocchi}
        self.cache, self.costi = cache, costi
        df = cache.df
        self._o, self._h, self._l = (np.ascontiguousarray(df[c].to_numpy(np.float64)) for c in ("Open", "High", "Low"))
        self._utili = barre_utili(df)
        self.inizio = int(inizio)
        if self.inizio:
            self._utili = self._utili.copy()
            self._utili[: self.inizio] = False
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

    def netti(self, s: Strategia) -> tuple:
        """(barra d'ingresso, prezzo d'ingresso, pips netti) per trade, con le operazioni di metriche.bp_per_trade."""
        lato, eb, xb, ep, xp = self.trade(s)
        c = self.costi
        segno = np.where(lato > 0, 1, -1)
        netti = (xp - ep) / c.pip * segno - c.commission * (ep + xp) / c.pip
        if c.spread_passo_pips is not None:
            netti = netti - (0.0 + float(c.spread_passo_pips))
        if c.funding is not None:
            netti = netti - c.funding_pips(lato, eb, xb)
        return eb, ep, netti

    def bp(self, s: Strategia) -> np.ndarray:
        """I bp netti per trade, con le operazioni di metriche.bp_per_trade nello stesso ordine."""
        _, ep, netti = self.netti(s)
        return netti * (self.costi.pip * 10_000.0 / ep)


def in_atr(netti_pips, pip: float, atr_segnale) -> np.ndarray:
    """Il netto di ogni trade in ATR: pips netti × pip / ATR giornaliero al segnale; NaN dove l'ATR non c'è (§14.1)."""
    a = np.asarray(atr_segnale, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(a > 0, np.asarray(netti_pips, dtype=float) * float(pip) / a, np.nan)


class ValutatoreLista:
    """
    La lista di monete (docs/82 §14): un Valutatore per moneta, l'orologio comune, l'ATR giornaliero di ogni moneta.
    `caches` = {symbol: Cache} nell'ordine della lista; `costi` = {symbol: Costi}; `inizio` = {symbol: barra} per
    selezione e cassaforte (None = 0).
    """

    def __init__(self, blocchi, caches: dict, costi: dict, inizio: dict | None = None):
        self.monete = list(caches)
        self.per_moneta = {m: Valutatore(blocchi, caches[m], costi[m], (inizio or {}).get(m, 0)) for m in self.monete}
        primo = caches[self.monete[0]]
        self.orologi = orologio({m: caches[m].df.index for m in self.monete}, primo.minuti_barra)
        self.atr = {m: atr_giornaliero_chiuso(caches[m].df).to_numpy(dtype=float) for m in self.monete}
        self.settimana = barre_settimana(pd.DatetimeIndex(primo.df.index))

    def per_trade(self, s: Strategia) -> dict:
        """{symbol: {"eb", "pos", "atr", "bp"}}: i trade di ogni moneta (barra d'ingresso, barra sull'orologio, netto in
        ATR e in bp)."""
        out = {}
        for m in self.monete:
            v = self.per_moneta[m]
            eb, ep, netti = v.netti(s)
            eb = np.asarray(eb, dtype=np.int64)
            out[m] = {"eb": eb, "pos": self.orologi[m][eb], "atr": in_atr(netti, v.costi.pip, self.atr[m][eb - 1]),
                      "bp": netti * (v.costi.pip * 10_000.0 / ep)}
        return out

    def valuta(self, s: Strategia) -> Misure:
        u = unisci({m: {k: x[k] for k in ("pos", "atr", "bp")} for m, x in self.per_trade(s).items()})
        return misure_lista(u["atr"], u["bp"], u["pos"], durata_uscita(s), self.settimana)

    def per_moneta_misure(self, s: Strategia) -> dict:
        """{symbol: Misure}: la tabella per moneta, solo da leggere (§14.1 punto 5)."""
        H = durata_uscita(s)
        return {m: misure_lista(x["atr"], x["bp"], x["pos"], H, self.settimana) for m, x in self.per_trade(s).items()}


def durata_uscita(s: Strategia) -> int:
    """H del t (docs/82 §14.2): le barre massime dell'uscita della strategia."""
    return int(s.valori_di(s.uscita)["durata_barre"])


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
