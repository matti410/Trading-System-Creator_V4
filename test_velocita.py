"""
Suite di validazione delle modifiche di VELOCITA' (17/10/2026).

Cosa verifica
-------------
Due modifiche che devono lasciare i risultati IDENTICI:

  A. `_StrategiaGenerica` (engine/exit_search_bt.py) legge le colonne una volta
     sola in init() e poi per indice, invece di farsele ritagliare a ogni
     barra da backtesting.py. Confronto trade per trade con una copia della
     strategia com'era prima, su serie casuali (stop, target, regola di
     uscita, scadenza per lato, inversione accesa e spenta).
  B. `esegui_giri` (engine/filter_search_bt.py) fa girare i backtest su piu'
     processi: stessi risultati, nello stesso ordine, che in sequenza.
  C. `run_filter_search_bt` su dati veri (dati/EURUSD_M15.csv, se c'e'):
     tabella e trade identici con processi=1, processi=2 e automatico.

Come si lancia (da terminale, dalla cartella del progetto):

    python test_velocita.py

La parte C serve il file dati/EURUSD_M15.csv; senza, viene saltata e lo dice.
Dura circa un minuto. Alla fine stampa «RISULTATO: N/N test superati».
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy

from engine.exit_search_bt import _StrategiaGenerica
from engine import filter_search_bt as fsb

warnings.simplefilter("ignore")

CASH = 100_000.0


class _StrategiaPrima(Strategy):
    """Copia letterale di _StrategiaGenerica prima del 17/10/2026 (il metro)."""
    long_col = None
    short_col = None
    exit_rule_long_col = None
    exit_rule_short_col = None
    n_barre = 32
    n_barre_long = None
    n_barre_short = None
    inverti_su_opposto = False

    def init(self):
        pass

    def next(self):
        if self.position:
            trade = self.trades[-1]
            barra_corrente = len(self.data) - 1
            if trade.entry_bar == barra_corrente:
                if trade.is_long:
                    frac_sl, frac_tp = self.data.sl_long[-1], self.data.tp_long[-1]
                    if not np.isnan(frac_sl):
                        trade.sl = trade.entry_price * (1 - frac_sl)
                    if not np.isnan(frac_tp):
                        trade.tp = trade.entry_price * (1 + frac_tp)
                else:
                    frac_sl, frac_tp = self.data.sl_short[-1], self.data.tp_short[-1]
                    if not np.isnan(frac_sl):
                        trade.sl = trade.entry_price * (1 + frac_sl)
                    if not np.isnan(frac_tp):
                        trade.tp = trade.entry_price * (1 - frac_tp)
            if self.inverti_su_opposto:
                segnale_long = (self.long_col is not None
                                and bool(getattr(self.data, self.long_col)[-1]))
                segnale_short = (self.short_col is not None
                                 and bool(getattr(self.data, self.short_col)[-1]))
                if trade.is_long and segnale_short and not segnale_long:
                    self.sell()
                    return
                if trade.is_short and segnale_long and not segnale_short:
                    self.buy()
                    return
            col_regola = self.exit_rule_long_col if trade.is_long else self.exit_rule_short_col
            if col_regola is not None and bool(getattr(self.data, col_regola)[-1]):
                self.position.close()
                return
            scadenza = self.n_barre_long if trade.is_long else self.n_barre_short
            if scadenza is None:
                scadenza = self.n_barre
            if barra_corrente - trade.entry_bar >= scadenza - 1:
                self.position.close()
            return
        segnale_long = (self.long_col is not None
                        and bool(getattr(self.data, self.long_col)[-1]))
        segnale_short = (self.short_col is not None
                         and bool(getattr(self.data, self.short_col)[-1]))
        if segnale_long and not segnale_short:
            self.buy()
        elif segnale_short and not segnale_long:
            self.sell()


def serie_casuale(n, seed):
    """Passeggiata casuale M15 con segnali, regole di uscita e soglie casuali."""
    rng = np.random.default_rng(seed)
    close = 1.10 * np.exp(np.cumsum(rng.normal(0, 0.0008, n)))
    open_ = np.r_[close[0], close[:-1]] * np.exp(rng.normal(0, 0.0002, n))
    alto = np.maximum(open_, close) * np.exp(np.abs(rng.normal(0, 0.0006, n)))
    basso = np.minimum(open_, close) * np.exp(-np.abs(rng.normal(0, 0.0006, n)))
    idx = pd.date_range("2024-01-02", periods=n, freq="15min", tz="UTC")
    d = pd.DataFrame({"Open": open_, "High": alto, "Low": basso, "Close": close,
                      "Volume": 100.0}, index=idx)
    d["__long"] = rng.random(n) < 0.03
    d["__short"] = rng.random(n) < 0.03
    d["__xlong"] = rng.random(n) < 0.02
    d["__xshort"] = rng.random(n) < 0.02
    for c in ("sl_long", "tp_long", "sl_short", "tp_short"):
        v = rng.uniform(0.0008, 0.004, n)
        v[rng.random(n) < 0.1] = np.nan          # soglie mancanti qua e la'
        d[c] = v
    return d


def stessi(a, b):
    try:
        pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))
        return True
    except AssertionError:
        return False


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    print("=" * 70)
    print("A · la strategia nuova da' gli stessi trade di quella di prima")
    print("=" * 70)
    casi = [
        ("base, solo scadenza", dict(n_barre=12)),
        ("scadenza diversa per lato", dict(n_barre=12, n_barre_long=7, n_barre_short=20)),
        ("con regola di uscita", dict(n_barre=16, exit_rule_long_col="__xlong",
                                      exit_rule_short_col="__xshort")),
        ("inversione accesa", dict(n_barre=16, inverti_su_opposto=True)),
        ("inversione + regola + per lato", dict(n_barre=10, n_barre_long=14, n_barre_short=6,
                                                exit_rule_long_col="__xlong",
                                                exit_rule_short_col="__xshort",
                                                inverti_su_opposto=True)),
        ("solo long", dict(n_barre=12, short_col=None)),
        ("solo short", dict(n_barre=12, long_col=None)),
    ]
    for seed, (nome, kw) in enumerate(casi):
        d = serie_casuale(6000, seed)
        run_kw = dict(long_col="__long", short_col="__short")
        run_kw.update(kw)
        for spread, commissione in ((0.0, 0.0), (0.00008, 0.00003)):
            uscite = []
            for strategia in (_StrategiaPrima, _StrategiaGenerica):
                bt = Backtest(d, strategia, cash=CASH, spread=spread, commission=commissione,
                              exclusive_orders=True, finalize_trades=True)
                uscite.append(bt.run(**run_kw))
            prima, dopo = uscite
            uguali_stats = all(prima[k] == dopo[k] or (pd.isna(prima[k]) and pd.isna(dopo[k]))
                               for k in fsb._VOCI_STATS)
            check(f"{nome} (spread {spread:g})",
                  len(prima["_trades"]) > 50 and stessi(prima["_trades"], dopo["_trades"])
                  and uguali_stats,
                  f"{len(prima['_trades'])} trade")

    print("=" * 70)
    print("B · esegui_giri: piu' processi = stessi risultati della sequenza")
    print("=" * 70)
    d = serie_casuale(8000, 99)
    bt_kw = dict(cash=CASH, spread=0.00008, commission=0.00003, exclusive_orders=True)
    bt = Backtest(d, _StrategiaGenerica, **bt_kw)
    giri = [dict(long_col="__long", short_col="__short", n_barre=n,
                 exit_rule_long_col=x, exit_rule_short_col=x and "__xshort",
                 inverti_su_opposto=inv)
            for n in (6, 12, 24) for x in (None, "__xlong") for inv in (False, True)]
    seq = fsb.esegui_giri(bt, d, bt_kw, giri, processi=1)
    par = fsb.esegui_giri(bt, d, bt_kw, giri, processi=2)
    check("stesso numero di risultati, nello stesso ordine", len(seq) == len(par) == len(giri))
    check("trade identici giro per giro",
          all(stessi(a["_trades"], b["_trades"]) for a, b in zip(seq, par)))
    check("statistiche identiche giro per giro",
          all(all(a[k] == b[k] or (pd.isna(a[k]) and pd.isna(b[k])) for k in fsb._VOCI_STATS)
              for a, b in zip(seq, par)))
    check("i giri sono davvero diversi fra loro (il confronto non e' banale)",
          len({len(a["_trades"]) for a in seq}) > 3)
    check("numero_processi: automatico con pochi giri = 1", fsb.numero_processi(None, 3) == 1)
    check("numero_processi: esplicito, mai piu' dei giri", fsb.numero_processi(8, 3) == 3)
    check("numero_processi: esplicito 1 = sequenza", fsb.numero_processi(1, 40) == 1)
    if "fork" not in __import__("multiprocessing").get_all_start_methods():
        check("Windows, script: in automatico si resta in sequenza",
              fsb._contesto_processi(esplicito=False) is None)
        check("Windows, script: chiesti esplicitamente si usano (spawn)",
              fsb._contesto_processi(esplicito=True).get_start_method() == "spawn")
    else:
        check("fork disponibile: si usa sempre",
              fsb._contesto_processi(esplicito=False).get_start_method() == "fork")

    print("=" * 70)
    print("C · run_filter_search_bt su EURUSD vero: processi 1, 2 e automatico")
    print("=" * 70)
    file_dati = os.path.join("dati", "EURUSD_M15.csv")
    if not os.path.exists(file_dati):
        print(f"  saltata: manca {file_dati}")
    else:
        from engine import registry as reg
        from engine.vetrina import prepara, _zitto
        with _zitto():
            s = prepara("EURUSD", H=25, cartella="dati")
        df = s.df_is.iloc[-40_000:]
        filtri = (reg.list_filters(0)[:6] + reg.list_filters(1)[:3] + reg.list_filters(-1)[:3])
        kw = dict(entry_long="E16_MORNING_STAR", entry_short="E1_SHORT_RSI_CROSS_OVERBOUGHT",
                  n_barre=18, n_barre_long=18, n_barre_short=25, filtri=filtri, perc_sl=90,
                  spread=0.00008, commission=0.0, pip_size=0.0001, verbose=False)
        uscite = {p: fsb.run_filter_search_bt(df, processi=p, **kw) for p in (1, 2, None)}
        r1 = uscite[1].risultati
        for p in (2, None):
            r = uscite[p].risultati
            check(f"processi={p}: tabella identica a processi=1", stessi(r1, r), f"{len(r)} righe")
            check(f"processi={p}: trade identici riga per riga",
                  all(stessi(uscite[1].trades(f), uscite[p].trades(f)) for f in r1["filtro"]))
        check("la baseline ha trade (il confronto non e' banale)",
              len(uscite[1].trades()) > 30, f"{len(uscite[1].trades())} trade")

    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
