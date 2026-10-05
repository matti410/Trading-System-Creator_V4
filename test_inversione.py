"""
Suite di validazione dell'INVERSIONE su segnale opposto (5/10/2026).

Cosa verifica
-------------
`_StrategiaGenerica` (engine/exit_search_bt.py) ha un parametro nuovo,
`inverti_su_opposto`, spento di default. Acceso, un segnale d'ingresso OPPOSTO
a posizione aperta chiude la posizione e ne apre una al contrario, tutto
all'Open della barra successiva al segnale (come ogni altro ordine).

Regole concordate:
  1. segnale nello stesso verso con posizione aperta  -> ignorato
  2. long e short sulla stessa barra                   -> non succede nulla
  3. uscita a tempo o a regola                         -> chiude e resta flat,
     senza invertire. Se nella stessa barra c'e' anche un segnale opposto,
     prevale l'inversione. L'inversione azzera il timer del nuovo trade.

Come si lancia (da terminale, dalla cartella del progetto):

    python test_inversione.py

Non servono MetaTrader 5 ne' file di dati: le serie sono costruite a mano.
Dura pochi secondi. Alla fine stampa «RISULTATO: N/N test superati».
"""
from __future__ import annotations

import sys
import warnings

import numpy as np
import pandas as pd
from backtesting import Backtest

from engine.exit_search_bt import _StrategiaGenerica

warnings.simplefilter("ignore")

N = 16
OPEN = 1.1000 + 0.0010 * np.arange(N)      # prezzi noti, crescenti
CASH = 100_000.0


def serie(long_su=(), short_su=(), uscita_long_su=(), uscita_short_su=(),
          sl_short=np.nan, alto_barra=None):
    """Serie a prezzi noti. `*_su` = indici di barra in cui il segnale e' vero."""
    idx = pd.date_range("2024-01-02 10:00", periods=N, freq="15min", tz="UTC")
    d = pd.DataFrame({"Open": OPEN, "High": OPEN + 0.0005, "Low": OPEN - 0.0005,
                      "Close": OPEN + 0.0002, "Volume": 100.0}, index=idx)
    for nome, quando in (("__long", long_su), ("__short", short_su),
                         ("__xlong", uscita_long_su), ("__xshort", uscita_short_su)):
        v = np.zeros(N, dtype=bool)
        for i in quando:
            v[i] = True
        d[nome] = v
    d["sl_long"] = np.nan
    d["tp_long"] = np.nan
    d["sl_short"] = sl_short
    d["tp_short"] = np.nan
    if alto_barra is not None:
        barra, valore = alto_barra
        d.iloc[barra, d.columns.get_loc("High")] = valore
    return d


def esegui_bt(d, n_barre=4, spread=0.0, commission=0.0, inverti=None,
              con_regola=False):
    """Lancia la strategia vera dell'engine. `inverti=None` = parametro non passato."""
    bt = Backtest(d, _StrategiaGenerica, cash=CASH, spread=spread,
                  commission=commission, exclusive_orders=True,
                  finalize_trades=True)
    kw = dict(long_col="__long", short_col="__short", n_barre=n_barre,
              exit_rule_long_col="__xlong" if con_regola else None,
              exit_rule_short_col="__xshort" if con_regola else None)
    if inverti is not None:
        kw["inverti_su_opposto"] = inverti
    return bt.run(**kw)["_trades"]


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def riga(t, k):
        r = t.iloc[k]
        return int(r.EntryBar), int(r.ExitBar), float(r.EntryPrice), float(r.ExitPrice), float(r.Size)

    print("\nA · L'inversione, nei due versi")
    # long: segnale a barra 1 -> entra all'Open 2. Short a barra 4 -> all'Open 5
    # chiude il long e apre lo short. Short a tempo: entra 5, esce 5 + 4 = 9.
    t = esegui_bt(serie(long_su=[1], short_su=[4]), n_barre=4, inverti=True)
    check("1. long poi short: due trade", len(t) == 2, f"trade: {len(t)}")
    e0, x0, pe0, px0, s0 = riga(t, 0)
    e1, x1, pe1, px1, s1 = riga(t, 1)
    check("2. il long entra all'Open della barra dopo il segnale", e0 == 2 and np.isclose(pe0, OPEN[2]) and s0 > 0)
    check("3. il long esce all'Open della barra dopo il segnale opposto (non al timer)",
          x0 == 5 and np.isclose(px0, OPEN[5]), f"uscita barra {x0}")
    check("4. lo short entra nella STESSA barra e allo stesso prezzo dell'uscita del long",
          e1 == 5 and np.isclose(pe1, OPEN[5]) and s1 < 0)
    equity = CASH + float(t.iloc[0].PnL)          # capitale dopo la chiusura del long
    check("5. lo short ha una taglia piena (come un trade normale), non ridotta",
          0.99 <= abs(s1) * OPEN[5] / equity <= 1.001, f"{abs(s1) * OPEN[5] / equity:.4f} dell'equity")
    check("6. il timer riparte dall'ingresso dello short (esce a 5 + 4)", x1 == 9, f"uscita barra {x1}")

    t = esegui_bt(serie(short_su=[1], long_su=[4]), n_barre=4, inverti=True)
    e0, x0, _, _, s0 = riga(t, 0)
    e1, x1, pe1, _, s1 = riga(t, 1)
    check("7. short poi long: inversione simmetrica",
          len(t) == 2 and s0 < 0 and s1 > 0 and x0 == 5 and e1 == 5 and np.isclose(pe1, OPEN[5]))

    print("\nB · Le regole concordate")
    t = esegui_bt(serie(long_su=[1, 3]), n_barre=4, inverti=True)
    check("8. stesso verso a posizione aperta: ignorato, il timer NON si rinnova",
          len(t) == 1 and riga(t, 0)[:2] == (2, 6), f"trade: {len(t)}, barre {riga(t, 0)[:2]}")

    t_conf =esegui_bt(serie(long_su=[1, 4], short_su=[4]), n_barre=4, inverti=True)
    check("9. long e short sulla stessa barra, a posizione aperta: nessuna inversione",
          len(t_conf) == 1 and riga(t_conf, 0)[:2] == (2, 6), f"trade: {len(t_conf)}")

    t = esegui_bt(serie(long_su=[1], short_su=[1]), n_barre=4, inverti=True)
    check("10. long e short sulla stessa barra, da flat: non si entra", len(t) == 0)

    t = esegui_bt(serie(long_su=[1]), n_barre=3, inverti=True)
    check("11. uscita a tempo senza segnale opposto: chiude e resta flat",
          len(t) == 1 and riga(t, 0)[:2] == (2, 5))

    t = esegui_bt(serie(long_su=[1], uscita_long_su=[3]), n_barre=10, inverti=True, con_regola=True)
    check("12. uscita a regola: chiude (Open barra 4) e resta flat, senza invertire",
          len(t) == 1 and riga(t, 0)[:2] == (2, 4), f"barre {riga(t, 0)[:2]}")

    # long entra a 2, n_barre=3: la chiusura a tempo si richiede a barra 4. Il
    # segnale short e' proprio a barra 4: prevale l'inversione.
    t = esegui_bt(serie(long_su=[1], short_su=[4]), n_barre=3, inverti=True)
    check("13. uscita a tempo e segnale opposto sulla stessa barra: prevale l'inversione",
          len(t) == 2 and riga(t, 0)[:2] == (2, 5) and riga(t, 1)[0] == 5 and riga(t, 1)[4] < 0)

    print("\nC · Parametro spento = comportamento di prima")
    d = serie(long_su=[1], short_su=[4])
    t_def = esegui_bt(d, n_barre=4)                     # parametro non passato
    t_off = esegui_bt(d, n_barre=4, inverti=False)
    cols = ["EntryBar", "ExitBar", "EntryPrice", "ExitPrice", "Size"]
    check("14. non passato == False: trade identici", t_def[cols].equals(t_off[cols]))
    check("15. spento: il segnale opposto a posizione aperta e' ignorato (un solo trade)",
          len(t_off) == 1 and riga(t_off, 0)[:2] == (2, 6), f"trade: {len(t_off)}")

    print("\nD · Costi e stop sul trade invertito")
    s, c = 0.0002, 0.0001
    t = esegui_bt(serie(long_su=[1], short_su=[4]), n_barre=4, spread=s, commission=c, inverti=True)
    _, _, pe0, px0, _ = riga(t, 0)
    _, _, pe1, px1, s1 = riga(t, 1)
    check("16. spread: il long entra a Open x (1 + s), esce al prezzo pieno",
          np.isclose(pe0, OPEN[2] * (1 + s)) and np.isclose(px0, OPEN[5]))
    check("17. spread: lo short entra a Open x (1 - s), una volta sola",
          np.isclose(pe1, OPEN[5] * (1 - s)))
    # la libreria calcola la commissione sui prezzi di fill (spread incluso):
    # vale per ogni trade, invertito o no
    com = [c * (r.EntryPrice + r.ExitPrice) * abs(r.Size) for r in (t.iloc[0], t.iloc[1])]
    check("18. commissione: c x (entrata + uscita) su ciascuno dei due trade",
          np.isclose(t.iloc[0].Commission, com[0]) and np.isclose(t.iloc[1].Commission, com[1]))
    t_solo = esegui_bt(serie(long_su=[1]), n_barre=3, spread=s, commission=c)
    check("18b. il trade che poi viene invertito costa come lo stesso trade senza inversione",
          np.isclose(t.iloc[0].Commission, t_solo.iloc[0].Commission)
          and np.isclose(t.iloc[0].EntryPrice, t_solo.iloc[0].EntryPrice))

    # stop dello short invertito: 1% sopra l'ingresso, attivo dalla barra dopo
    # l'ingresso. Lo short entra a barra 5; a barra 6 il massimo supera lo stop.
    stop = 0.01
    d = serie(long_su=[1], short_su=[4], sl_short=stop, alto_barra=(6, OPEN[5] * 1.02))
    t = esegui_bt(d, n_barre=8, inverti=True)
    r = t.iloc[1]
    check("19. lo stop viene assegnato anche al trade nato da un'inversione",
          int(r.ExitBar) == 6 and np.isclose(float(r.ExitPrice), OPEN[5] * (1 + stop)),
          f"uscita barra {int(r.ExitBar)} a {float(r.ExitPrice):.5f}")

    print("\nE · I due motori di ricerca (mercato sintetico, entry finte)")
    from engine import registry as reg
    from engine.exit_search_bt import run_exit_search_bt
    from engine.filter_search_bt import run_filter_search_bt

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
    reg.clear_registry()
    reg.register_entry("T_LONG", 1)(lambda d: pd.Series(sig_l[:len(d)], index=d.index))
    reg.register_entry("T_SHORT", -1)(lambda d: pd.Series(sig_s[:len(d)], index=d.index))
    reg.register_filter("T_SEMPRE", 0)(lambda d: pd.Series(True, index=d.index))

    kw = dict(entry_cols_long=["T_LONG"], entry_cols_short=["T_SHORT"], n_barre=8, verbose=False)
    r_def = run_exit_search_bt(mk, **kw).risultati
    r_off = run_exit_search_bt(mk, inverti_su_opposto=False, **kw).risultati
    r_on = run_exit_search_bt(mk, inverti_su_opposto=True, **kw).risultati
    check("20. run_exit_search_bt: default == False (stessi trade e stesso pnl)",
          r_def[["trades", "pnl_pct"]].equals(r_off[["trades", "pnl_pct"]]))
    check("21. run_exit_search_bt: acceso cambia i trade (le inversioni esistono)",
          int(r_on["trades"].iloc[0]) != int(r_off["trades"].iloc[0]),
          f"spento {int(r_off['trades'].iloc[0])} · acceso {int(r_on['trades'].iloc[0])}")

    kf = dict(entry_long="T_LONG", entry_short="T_SHORT", n_barre=8, filtri=["T_SEMPRE"],
              verbose=False, n_boot=200)
    f_def = run_filter_search_bt(mk, **kf).risultati
    f_off = run_filter_search_bt(mk, inverti_su_opposto=False, **kf).risultati
    f_on = run_filter_search_bt(mk, inverti_su_opposto=True, **kf).risultati
    check("22. run_filter_search_bt: default == False",
          f_def[["filtro", "trades", "pnl_pct"]].equals(f_off[["filtro", "trades", "pnl_pct"]]))
    check("23. run_filter_search_bt: acceso cambia i trade della baseline",
          int(f_on["trades"].iloc[0]) != int(f_off["trades"].iloc[0]),
          f"spento {int(f_off['trades'].iloc[0])} · acceso {int(f_on['trades'].iloc[0])}")
    check("24. run_filter_search_bt acceso: un filtro sempre vero == baseline",
          int(f_on["trades"].iloc[0]) == int(f_on["trades"].iloc[1]))
    reg.clear_registry()

    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
