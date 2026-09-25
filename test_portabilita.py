"""
Suite di validazione della portabilita' su asset diversi da EURUSD (25/9/2026).

Due difetti trovati al primo run su BTCUSD:

  1. prezzo > capitale: backtesting.py non compra frazioni e i trade
     spariscono in silenzio -> engine/controlli.py, avviso_capitale
  2. senza MT5, BTCUSD veniva classificato forex (6 lettere) -> costi.py

Si lancia da terminale, dalla cartella del progetto:

    python test_portabilita.py

Non serve MetaTrader 5 e non serve nessun file di dati. Richiede
backtesting==0.6.6. Dura pochi secondi.
"""
from __future__ import annotations

import contextlib
import io
import sys
import warnings

import numpy as np
import pandas as pd

from engine.collaudo_catalogo import mercato_sintetico
from engine.controlli import avviso_capitale
from engine.costi import classifica_simbolo, parametri_backtest
from engine.exit_search_bt import run_exit_search_bt
from engine.filter_search_bt import run_filter_search_bt
from engine.registry import clear_registry, register_entry

warnings.simplefilter("ignore")


def _cattura(funzione, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = funzione(*a, **k)
    return out, buf.getvalue()


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    # ------------------------------------------------------ classificazione --
    print("\nA · Classe dell'asset senza MT5")
    attese = {"EURUSD": "forex", "USDJPY": "forex", "GBPAUD": "forex", "EURGBP": "forex",
              "BTCUSD": "crypto", "ETHUSD": "crypto", "LTCUSD": "crypto",
              "XAUUSD": "metalli", "XAGUSD": "metalli", "US500": "altro", "ABCDEF": "altro"}
    trovate = {s: classifica_simbolo(s) for s in attese}
    check("1. forex solo se sono due valute ufficiali, crypto per sigla",
          trovate == attese,
          " · ".join(f"{s}={c}" for s, c in trovate.items()))
    check("2. col path di MT5 decide il path, come prima",
          classifica_simbolo("BTCUSD", "Crypto\\BTCUSD") == "crypto"
          and classifica_simbolo("US500", "Indices\\US500") == "indici"
          and classifica_simbolo("EURUSD", "Forex\\Majors\\EURUSD") == "forex")

    # --------------------------------------------------------------- costi --
    print("\nB · Costi senza MT5")
    idx = pd.date_range("2024-01-01", periods=500, freq="15min", tz="UTC")
    eur = pd.DataFrame({"Close": np.linspace(1.05, 1.15, 500)}, index=idx)
    btc = pd.DataFrame({"Close": np.linspace(40_000, 60_000, 500)}, index=idx)

    nuovo, _ = _cattura(parametri_backtest, "EURUSD", bars=eur, usa_mt5=False, spread_pips=0.1)
    atteso_spread = 0.1 * 0.0001 / float(eur["Close"].median())
    atteso_comm = 7.0 / (100_000 * float(eur["Close"].median())) / 2
    check("3. EURUSD: numeri invariati (spread di listino, 7 $ round-turn su 100.000)",
          np.isclose(nuovo["spread"], atteso_spread) and np.isclose(nuovo["commission"], atteso_comm),
          f"spread {nuovo['spread']:.3e} · commission {nuovo['commission']:.3e}")

    c_btc, stampa = _cattura(parametri_backtest, "BTCUSD", bars=btc, usa_mt5=False, spread_pips=12.58)
    check("4. BTCUSD: classe crypto, commissione zero, nessun nozionale inventato",
          c_btc["commission"] == 0.0 and "[crypto]" in stampa and "non serve" in stampa,
          stampa.splitlines()[0].strip())
    check("5. BTCUSD: spread relativo = spread_pips x pip / prezzo mediano",
          np.isclose(c_btc["spread"], 12.58 * 1.0 / float(btc["Close"].median())),
          f"{c_btc['spread'] * 1e4:.3f} bp")

    try:
        parametri_backtest("US500", bars=btc, usa_mt5=False, spread_pips=1.0, verbose=False)
        ok = True
    except Exception:
        ok = False
    check("6. un simbolo senza commissione non chiede piu' il nozionale forex", ok)

    # ------------------------------------------------------------- capitale --
    print("\nC · Capitale e prezzo")
    df_btc = mercato_sintetico("2024-01-01", "2024-04-01", seme=4, prezzo=50_000, vol_barra=60,
                               gap_open=10)
    avviso, testo = _cattura(avviso_capitale, df_btc, 10_000)
    check("7. prezzo sopra il capitale -> avviso, con la correzione",
          avviso and "SPARISCONO" in testo and "cash=1,000,000" in testo,
          testo.splitlines()[2].strip("! ").strip() if avviso else "")
    avviso, testo = _cattura(avviso_capitale, df_btc, 10_000_000)
    check("8. capitale sufficiente -> nessun avviso", not avviso and testo == "")
    df_eur = mercato_sintetico("2024-01-01", "2024-02-01", seme=4)
    avviso, _ = _cattura(avviso_capitale, df_eur, 10_000)
    check("9. EURUSD con cash 10.000: nessun avviso (comportamento invariato)", not avviso)

    # --------------------------------------------------- dentro i motori --
    print("\nD · Dentro i due motori di backtest")
    clear_registry()
    rng = np.random.default_rng(1)
    segnali = pd.Series(rng.random(len(df_btc)), index=df_btc.index)
    register_entry("T_PORT_LONG", 1)(lambda d: segnali.reindex(d.index) < 0.01)
    p = dict(n_barre=8, perc_sl=0.0, perc_tp=0.0, spread=0.0, commission=0.0, verbose=False)

    fs_poco, testo_poco = _cattura(run_filter_search_bt, df_btc, entry_long="T_PORT_LONG",
                                   filtri=[], cash=10_000, **p)
    fs_ok, testo_ok = _cattura(run_filter_search_bt, df_btc, entry_long="T_PORT_LONG",
                               filtri=[], cash=10_000_000, **p)
    n_poco, n_ok = len(fs_poco.trades()), len(fs_ok.trades())
    check("10. run_filter_search_bt: avvisa anche con verbose=False, e i trade mancano davvero",
          "SPARISCONO" in testo_poco and "SPARISCONO" not in testo_ok and n_poco == 0 and n_ok > 50,
          f"cash 10.000: {n_poco} trade · cash 10.000.000: {n_ok} trade")

    fs_leva, testo_leva = _cattura(run_filter_search_bt, df_btc, entry_long="T_PORT_LONG",
                                   filtri=[], cash=10_000, **{**p, "margin": 0.1})
    fs_leva2, testo_leva2 = _cattura(run_filter_search_bt, df_btc, entry_long="T_PORT_LONG",
                                     filtri=[], cash=1_000, **{**p, "margin": 0.1})
    check("11. conta la leva (cash / margin), verificato sul motore: 10.000 a leva 10 bastano, 1.000 no",
          "SPARISCONO" not in testo_leva and len(fs_leva.trades()) == n_ok
          and "SPARISCONO" in testo_leva2 and len(fs_leva2.trades()) == 0,
          f"{len(fs_leva.trades())} trade e {len(fs_leva2.trades())} trade")

    _, testo_es = _cattura(run_exit_search_bt, df_btc, entry_cols_long=["T_PORT_LONG"],
                           cash=10_000, **{k: v for k, v in p.items()})
    check("12. run_exit_search_bt: stesso avviso", "SPARISCONO" in testo_es)

    fs_ok2, _ = _cattura(run_filter_search_bt, df_btc, entry_long="T_PORT_LONG",
                         filtri=[], cash=100_000_000, **p)
    check("13. alzare cash non cambia i pips per trade",
          np.isclose(fs_ok.risultati["avg_trade_netto"].iat[0],
                     fs_ok2.risultati["avg_trade_netto"].iat[0])
          and len(fs_ok2.trades()) == n_ok,
          f"avg_trade_netto {fs_ok.risultati['avg_trade_netto'].iat[0]:+.3f} con 10 M e 100 M")

    clear_registry()
    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
