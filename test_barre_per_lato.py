"""
Suite di validazione della SCADENZA A TEMPO PER LATO (6/10/2026).

Cosa verifica
-------------
`run_exit_search_bt`, `run_filter_search_bt` e `due_meta` hanno due parametri
nuovi e facoltativi, `n_barre_long` e `n_barre_short`. Non indicati, ogni lato
usa `n_barre` e il risultato e' identico a prima. Indicati, i trade di quel
lato scadono dopo quelle barre e le soglie di stop/target di quel lato si
misurano sul suo orizzonte.

Come si lancia (da terminale, dalla cartella del progetto):

    python test_barre_per_lato.py

Su Colab, in una cella:   !python test_barre_per_lato.py

Non servono MetaTrader 5 ne' file di dati: le serie sono costruite a mano.
Dura pochi secondi. Alla fine stampa «RISULTATO: N/N test superati».
"""
from __future__ import annotations

import sys
import warnings

import numpy as np
import pandas as pd
from backtesting import Backtest

import engine.registry as reg
from engine.exit_search_bt import (_StrategiaGenerica, barre_per_lato,
                                   run_exit_search_bt, soglie_adattive,
                                   soglie_per_lato)
from engine.filter_search_bt import run_filter_search_bt
from engine.due_meta import due_meta

warnings.simplefilter("ignore")

N = 40
OPEN = 1.1000 + 0.0010 * np.arange(N)
CASH = 100_000.0


def serie(long_su=(), short_su=()):
    idx = pd.date_range("2024-01-02 10:00", periods=N, freq="15min", tz="UTC")
    d = pd.DataFrame({"Open": OPEN, "High": OPEN + 0.0005, "Low": OPEN - 0.0005,
                      "Close": OPEN + 0.0002, "Volume": 100.0}, index=idx)
    for nome, quando in (("__long", long_su), ("__short", short_su)):
        v = np.zeros(N, dtype=bool)
        for i in quando:
            v[i] = True
        d[nome] = v
    for c in ("sl_long", "tp_long", "sl_short", "tp_short"):
        d[c] = np.nan
    return d


def esegui_bt(d, **kw):
    bt = Backtest(d, _StrategiaGenerica, cash=CASH, exclusive_orders=True,
                  finalize_trades=True)
    return bt.run(long_col="__long", short_col="__short", **kw)["_trades"]


def durate(t):
    lato = np.where(t["Size"] > 0, "L", "S")
    return [(l, int(b)) for l, b in zip(lato, t["ExitBar"] - t["EntryBar"])]


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def solleva(f):
        try:
            f()
        except ValueError:
            return True
        return False

    print("\nA · La strategia, su prezzi noti")
    d = serie(long_su=[1], short_su=[15])
    t = esegui_bt(d, n_barre=6)
    check("1. senza i parametri nuovi: entrambi i lati durano n_barre",
          durate(t) == [("L", 6), ("S", 6)], str(durate(t)))
    t = esegui_bt(d, n_barre=6, n_barre_long=3, n_barre_short=9)
    check("2. long 3 barre, short 9 barre: durate esatte",
          durate(t) == [("L", 3), ("S", 9)], str(durate(t)))
    t = esegui_bt(d, n_barre=6, n_barre_short=9)
    check("3. solo n_barre_short: il long resta su n_barre",
          durate(t) == [("L", 6), ("S", 9)], str(durate(t)))
    t = esegui_bt(d, n_barre=6, n_barre_long=3)
    check("4. solo n_barre_long: lo short resta su n_barre",
          durate(t) == [("L", 3), ("S", 6)], str(durate(t)))
    a = esegui_bt(d, n_barre=6)
    b = esegui_bt(d, n_barre=6, n_barre_long=6, n_barre_short=6)
    check("5. indicati uguali a n_barre: trade identici", a.equals(b))
    # inversione: long entra a 2 (scadenza 10), short a barra 4 -> inverte a 5;
    # il nuovo short ha il SUO timer (4 barre): esce a 9
    t = esegui_bt(serie(long_su=[1], short_su=[4]), n_barre=6, n_barre_long=10,
                  n_barre_short=4, inverti_su_opposto=True)
    r = [(int(x.EntryBar), int(x.ExitBar)) for x in t.itertuples()]
    check("6. con inversione: il trade invertito usa le barre del suo lato",
          r == [(2, 5), (5, 9)], str(r))

    print("\nB · I controlli sui valori")
    check("7. barre_per_lato: None = n_barre", barre_per_lato(25) == (25, 25))
    check("8. barre_per_lato: valori indicati", barre_per_lato(25, 8, 12) == (8, 12))
    check("9. n_barre_long = 0 -> errore", solleva(lambda: barre_per_lato(25, 0, 12)))
    check("10. n_barre_short = 0 -> errore", solleva(lambda: barre_per_lato(25, 8, 0)))

    print("\nC · Le funzioni di ricerca, su una serie casuale")
    n = 6000
    rng = np.random.default_rng(7)
    close = 1.10 * np.exp(np.cumsum(rng.normal(0, 0.0004, n)))
    apertura = np.r_[close[0], close[:-1]]
    mk = pd.DataFrame({"Open": apertura,
                       "High": np.maximum(apertura, close) * 1.0002,
                       "Low": np.minimum(apertura, close) * 0.9998,
                       "Close": close, "Volume": 100.0},
                      index=pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC"))
    sig_l = rng.random(n) < 0.02
    sig_s = rng.random(n) < 0.02
    filtro = rng.random(n) < 0.6
    reg.clear_registry()
    reg.register_entry("T_LONG", 1)(lambda d: pd.Series(sig_l[:len(d)], index=d.index))
    reg.register_entry("T_SHORT", -1)(lambda d: pd.Series(sig_s[:len(d)], index=d.index))
    reg.register_filter("T_FILTRO", 0)(lambda d: pd.Series(filtro[:len(d)], index=d.index))

    # soglie: il lato short si misura sul suo orizzonte
    s = soglie_per_lato(mk, 6, 14, 500, 90.0, 80.0, lag=1)
    s6 = soglie_adattive(mk, 6, 500, 90.0, 80.0, lag=1)
    s14 = soglie_adattive(mk, 14, 500, 90.0, 80.0, lag=1)
    check("11. soglie del long = orizzonte long",
          s["sl_long"].equals(s6["sl_long"]) and s["tp_long"].equals(s6["tp_long"]))
    check("12. soglie dello short = orizzonte short",
          s["sl_short"].equals(s14["sl_short"]) and s["tp_short"].equals(s14["tp_short"]))
    uguali = soglie_per_lato(mk, 6, 6, 500, 90.0, 80.0, lag=1)
    check("13. orizzonti uguali: soglie identiche a soglie_adattive",
          all(uguali[k].equals(s6[k]) for k in s6))

    ke = dict(entry_cols_long=["T_LONG"], entry_cols_short=["T_SHORT"], n_barre=8,
              verbose=False, quarantena=False)
    e_def = run_exit_search_bt(mk, **ke)
    e_ug = run_exit_search_bt(mk, n_barre_long=8, n_barre_short=8, **ke)
    check("14. run_exit_search_bt: indicati uguali a n_barre == non indicati",
          e_def.risultati.equals(e_ug.risultati) and e_def.trades().equals(e_ug.trades()))
    e = run_exit_search_bt(mk, n_barre_long=5, n_barre_short=13, **ke)
    tr = e.trades()
    dl = (tr["ExitBar"] - tr["EntryBar"])[tr["Size"] > 0]
    ds = (tr["ExitBar"] - tr["EntryBar"])[tr["Size"] < 0]
    check("15. run_exit_search_bt: ogni long dura 5 barre, ogni short 13",
          len(dl) > 20 and len(ds) > 20 and set(dl) == {5} and set(ds) == {13},
          f"{len(dl)} long · {len(ds)} short")
    check("16. il risultato ricorda le barre per lato",
          (e.n_barre, e.n_barre_long, e.n_barre_short) == (8, 5, 13)
          and (e_def.n_barre_long, e_def.n_barre_short) == (8, 8))
    e_sl = run_exit_search_bt(mk, n_barre_long=5, n_barre_short=13, perc_sl=70.0,
                              perc_tp=70.0, inverti_su_opposto=True, **ke)
    tr = e_sl.trades()
    dl = (tr["ExitBar"] - tr["EntryBar"])[tr["Size"] > 0]
    ds = (tr["ExitBar"] - tr["EntryBar"])[tr["Size"] < 0]
    check("17. con stop, target e inversione: nessun long oltre 5, nessuno short oltre 13",
          dl.max() <= 5 and ds.max() <= 13 and dl.min() < 5 and ds.min() < 13,
          f"long max {int(dl.max())} · short max {int(ds.max())}")
    solo_l = run_exit_search_bt(mk, entry_cols_long=["T_LONG"], n_barre=8, n_barre_long=5,
                                n_barre_short=13, verbose=False, quarantena=False)
    rif_l = run_exit_search_bt(mk, entry_cols_long=["T_LONG"], n_barre=5,
                               verbose=False, quarantena=False)
    check("18. solo long con n_barre_long=5 == vecchia chiamata con n_barre=5",
          solo_l.trades().equals(rif_l.trades()))
    solo_s = run_exit_search_bt(mk, entry_cols_short=["T_SHORT"], n_barre=8, n_barre_long=5,
                                n_barre_short=13, perc_sl=80.0, verbose=False, quarantena=False)
    rif_s = run_exit_search_bt(mk, entry_cols_short=["T_SHORT"], n_barre=13, perc_sl=80.0,
                               verbose=False, quarantena=False)
    check("19. solo short con n_barre_short=13 e stop == vecchia chiamata con n_barre=13",
          solo_s.trades().equals(rif_s.trades()))

    kf = dict(entry_long="T_LONG", entry_short="T_SHORT", n_barre=8, filtri=["T_FILTRO"],
              verbose=False, n_boot=200, quarantena=False)
    f_def = run_filter_search_bt(mk, **kf)
    f_ug = run_filter_search_bt(mk, n_barre_long=8, n_barre_short=8, **kf)
    check("20. run_filter_search_bt: indicati uguali a n_barre == non indicati",
          f_def.risultati.equals(f_ug.risultati))
    f = run_filter_search_bt(mk, n_barre_long=5, n_barre_short=13, **kf)
    ok = True
    for nome in (None, "T_FILTRO"):
        tr = f.trades(nome)
        d_ = tr["ExitBar"] - tr["EntryBar"]
        ok &= set(d_[tr["Size"] > 0]) == {5} and set(d_[tr["Size"] < 0]) == {13}
    check("21. run_filter_search_bt: baseline e riga filtrata rispettano le barre per lato", ok)
    check("22. la baseline dei filtri == la riga di run_exit_search_bt",
          f.trades(None).equals(e.trades()))
    check("23. il risultato dei filtri ricorda le barre per lato",
          (f.n_barre_long, f.n_barre_short) == (5, 13))

    dm = due_meta(mk, f, [None, "T_FILTRO"], verbose=False, quarantena=False)
    ok = True
    for meta in (dm.metà1, dm.metà2):
        tr = meta.trades(None)
        d_ = tr["ExitBar"] - tr["EntryBar"]
        ok &= set(d_[tr["Size"] > 0]) == {5} and set(d_[tr["Size"] < 0]) == {13}
    check("24. due_meta: le due meta' usano le barre per lato lette da fs", ok)
    reg.clear_registry()

    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
