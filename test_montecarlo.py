"""
Suite di validazione di engine/montecarlo.py e della correzione del drawdown
in engine/giudizio.py (26/9/2026).

Si lancia da terminale, dalla cartella del progetto:

    python test_montecarlo.py

Non serve MetaTrader 5 e non serve nessun file di dati. Dura una ventina di
secondi.
"""
from __future__ import annotations

import sys
import warnings

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

from engine.giudizio import _drawdown_chiusi, drawdown_montecarlo
from engine.montecarlo import (drawdown_da_zero, grafici_montecarlo, montecarlo_completo,
                               pips_per_dataset, sizing, valore_pip_lotto, yardstick)

warnings.simplefilter("ignore")


def _trades(pips, inizio="2024-01-01", pip=0.0001, prezzo=1.10):
    """Trade finti nel formato di backtesting.py: long, commissione zero."""
    n = len(pips)
    uscite = pd.date_range(inizio, periods=n, freq="h")
    return pd.DataFrame({
        "Size": np.full(n, 1000), "EntryPrice": np.full(n, prezzo),
        "ExitPrice": prezzo + np.asarray(pips) * pip,
        "EntryBar": np.arange(n), "ExitBar": np.arange(n) + 1,
        "EntryTime": uscite - pd.Timedelta("30min"), "ExitTime": uscite,
    })


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    print("\nA · Il drawdown parte da zero")
    casi = {(-5, -3): 8, (5, -3): 3, (-2, 4, -7, 1): 7, (3, 2): 0, (-1,): 1}
    ok = all(np.isclose(drawdown_da_zero(k), v) for k, v in casi.items())
    ok_g = all(np.isclose(_drawdown_chiusi(k), v) for k, v in casi.items())
    check("1. montecarlo.drawdown_da_zero: casi a mano", ok, "(-5,-3) -> 8 · (5,-3) -> 3 · (-2,4,-7,1) -> 7")
    check("2. giudizio._drawdown_chiusi corretto: stessi casi", ok_g)
    tutti_neg = drawdown_montecarlo([-1.0] * 10, n_sim=50)
    check("3. giudizio.drawdown_montecarlo: 10 trade da -1 -> drawdown 10 in ogni sequenza",
          np.isclose(tutti_neg["dd_50"], 10) and np.isclose(tutti_neg["dd_99"], 10),
          f"dd_50 {tutti_neg['dd_50']:.1f}")

    print("\nB · Yardstick")
    rng = np.random.default_rng(3)
    nullo = rng.normal(0, 10, 2000)
    nullo -= nullo.mean()                         # EV esattamente zero
    y0 = yardstick(nullo, n_sim=20_000, seed=1)
    check("4. EV nullo -> P(P&L < 0) circa 50% a ogni orizzonte",
          (abs(y0["p_pnl_negativo"] - 50) < 2).all(),
          " · ".join(f"{h}: {v:.1f}%" for h, v in y0["p_pnl_negativo"].items()))
    check("5. i percentili del drawdown crescono con l'orizzonte e col percentile",
          (np.diff(y0["dd_p95"].to_numpy()) > 0).all()
          and (np.diff(y0.loc[20, [f"dd_p{p}" for p in (50, 75, 90, 95, 99)]].to_numpy()) > 0).all())
    # un solo trade possibile: tutto deterministico
    y1 = yardstick([2.0] * 10 + [2.0], orizzonti=(10,), n_sim=500)
    check("6. trade tutti uguali a +2: drawdown 0, P&L 20 a 10 trade, P(<0) 0",
          y1.loc[10, "dd_p99"] == 0 and np.isclose(y1.loc[10, "pnl_p50"], 20)
          and y1.loc[10, "p_pnl_negativo"] == 0)
    # confronto con il calcolo esatto: 2 esiti equiprobabili +1/-1 su 10 trade
    y2 = yardstick([1.0, -1.0] * 50, orizzonti=(10,), n_sim=200_000, seed=2)
    from math import comb
    p_neg = sum(comb(10, k) for k in range(0, 5)) / 2 ** 10 * 100   # meno di 5 vincenti
    check("7. moneta +1/-1: P(P&L<0) a 10 trade uguale al valore esatto (37,7%)",
          abs(y2.loc[10, "p_pnl_negativo"] - p_neg) < 0.5,
          f"simulato {y2.loc[10, 'p_pnl_negativo']:.2f}% · esatto {p_neg:.2f}%")
    check("8. stesso seme -> stessa tabella", yardstick(nullo, n_sim=2000, seed=5)
          .equals(yardstick(nullo, n_sim=2000, seed=5)))

    print("\nC · Monte Carlo completo")
    mc = montecarlo_completo(nullo[:300], n_sim=5000, soglia_dd=100, seed=0)
    check("9. dd_reale = drawdown della sequenza vera, da zero",
          np.isclose(mc["dd_reale"], drawdown_da_zero(nullo[:300])) and mc["n_trade"] == 300)
    check("10. P(drawdown >= soglia) coerente con la distribuzione",
          np.isclose(mc["p_dd_oltre_soglia"], (mc["_dd"] >= 100).mean() * 100)
          and len(mc["_dd"]) == 5000)

    print("\nD · I trade del dataset")
    t_is, t_oos = _trades([1, -2, 3]), _trades([4, -5], inizio="2025-01-01")
    full = pips_per_dataset(t_is, t_oos, 0.0001, 0.0, "FULL")
    check("11. IS / OOS / FULL: pips netti giusti e nell'ordine di uscita",
          np.allclose(full, [1, -2, 3, 4, -5])
          and np.allclose(pips_per_dataset(t_is, t_oos, 0.0001, 0.0, "IS"), [1, -2, 3])
          and np.allclose(pips_per_dataset(t_is, t_oos, 0.0001, 0.0, "oos"), [4, -5]))
    netti = pips_per_dataset(t_is, None, 0.0001, 0.00003, "IS")
    atteso = np.array([1, -2, 3]) - 0.00003 * (1.10 + 1.10 + np.array([1, -2, 3]) * 0.0001) / 0.0001
    try:
        pips_per_dataset(t_is, None, 0.0001, 0.0, "FULL")
        errore = False
    except ValueError:
        errore = True
    check("12. commissione tolta come in metriche.py; FULL senza OOS -> errore",
          np.allclose(netti, atteso) and errore)

    print("\nE · Sizing")
    check("13. valore del pip per lotto: EURUSD 10 $, BTCUSD 1 $, USDJPY a 150 -> 6,67 $",
          np.isclose(valore_pip_lotto("EURUSD", 0.0001), 10)
          and np.isclose(valore_pip_lotto("BTCUSD", 1.0), 1)
          and np.isclose(valore_pip_lotto("USDJPY", 0.01, prezzo=150), 100_000 * 0.01 / 150))
    s = sizing({"dd_p95": 500.0}, dd_accettabile_usd=10_000, valore_pip=10.0)
    check("14. metodo del drawdown: 10.000 $ / (500 pips x 10 $) = 2 lotti",
          np.isclose(s["lotti_drawdown"], 2) and s["lotti_consigliati"] == 2.0
          and np.isnan(s["lotti_peggior_trade"]))
    s2 = sizing(500.0, 10_000, 10.0, perdita_max_trade_usd=1_500, peggior_trade_pips=-100)
    check("15. col peggior trade: 1.500 $ / (100 x 10 $) = 1,5 -> consigliati il piu' prudente",
          np.isclose(s2["lotti_peggior_trade"], 1.5) and s2["lotti_consigliati"] == 1.5)
    s3 = sizing({"dd_p95": 333.0}, 10_000, 10.0)
    check("16. arrotondamento per difetto a 0,01 lotti", s3["lotti_consigliati"] == 3.0
          and s3["lotti_drawdown"] > 3.0, f"{s3['lotti_drawdown']:.4f} -> {s3['lotti_consigliati']}")

    print("\nF · Grafici")
    figs = grafici_montecarlo(nullo[:300], n_sim_grafici=500, titolo="test")
    check("17. tre figure, 4 orizzonti x 2 righe di istogrammi", len(figs) == 3
          and len(figs[1].axes) == 8)

    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
