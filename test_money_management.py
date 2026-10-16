"""
Suite di validazione del money management (16/10/2026, fase 1 di docs/61).

  A  esempi numerici del libro (Unger, «The Successful Trader's Guide to Money
     Management», Wiley 2021): contratti, capitale, drawdown, TWR, optimal f,
     Kelly, capitale che non basta, formula con prezzo e stop
  B  limiti dei lotti: passo, minimo (salto), massimo, leva (riduzione e
     salto), rischio ignoto, capitale a zero. Il SALTO si prova qui, a parte
  C  identita' (salto sotto il minimo e leva SPENTI, regola di Mattia del
     16/10): lotti continui = capitale x TWR; lotti fissi = pips x valore;
     Monte Carlo con la sequenza vera = storia vera
  D  nessun lookahead: troncamento della sequenza, trade futuri cambiati,
     stop di calcolo su storico troncato, prezzo del segnale
  E  calibrazione e banda: scelta senza salti, limiti estremi, ripetibilita'
  F  adattatore su un backtest vero di EURUSD: pips identici a
     pips_per_dataset, stop del motore = soglia adattiva, stop di calcolo
  G  adattatore sui symbol di dati/ (saltato se manca): valore del pip
     trade per trade uguale a valore_pip_lotto (USDJPY, DE40, XAUUSD, BTCUSD)
  H  il modulo puro non importa niente da engine/ (si copia nel repo crypto)

Si lancia da terminale, dalla cartella del progetto:

    python test_money_management.py

Usa EURUSD_M15.csv (nel repo). Dura circa un minuto.
"""
from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.simplefilter("ignore")

import engine.money_management as mm
from engine.broker_tz_diagnostic import to_utc_index
from engine.exit_search_bt import soglie_per_lato
from engine.filter_search_bt import run_filter_search_bt
from engine.indicatori import aggiungi_indicatori
from engine.mm_adattatore import limiti_symbol, tabella_trade
from engine.montecarlo import pips_per_dataset, valore_pip_lotto
from engine.registry import clear_registry, register_entry
from engine.simboli import pip_symbol

QUI = Path(__file__).resolve().parent
TRADE_LIBRO = np.array([-500, 1300, 700, -1250, -1000, 2500, 5350, -1250, 600, 350.0])
SPENTI = {}            # nessun limite: lotti continui, niente salti, niente leva


def _muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def _tab(pips, rischio=1250.0, v_in=1.0, v_out=1.0, **extra):
    d = {"pips_netti": np.asarray(pips, dtype=float), "rischio_pips": rischio,
         "valore_entrata": v_in, "valore_uscita": v_out}
    d.update(extra)
    return pd.DataFrame(d)


def _carica(nome: str) -> pd.DataFrame:
    with contextlib.redirect_stdout(io.StringIO()):
        return to_utc_index(pd.read_csv(nome, index_col="Date"), "A_US_DST (NY+7h)",
                            on_dst_gap="drop", verbose=False)


def _trade_finti(df: pd.DataFrame, n: int = 40, seme: int = 3, durata: int = 8) -> pd.DataFrame:
    """Trade costruiti a mano su un df vero: ingresso all'apertura, uscita dopo `durata` barre."""
    rng = np.random.default_rng(seme)
    pos = np.sort(rng.choice(np.arange(600, len(df) - durata - 1), size=n, replace=False))
    lato = rng.choice([1, -1], size=n)
    ep = df["Open"].to_numpy()[pos]
    xp = df["Close"].to_numpy()[pos + durata]
    return pd.DataFrame({"Size": lato, "EntryBar": pos, "ExitBar": pos + durata,
                         "EntryPrice": ep, "ExitPrice": xp,
                         "SL": ep * (1 - lato * 0.004),
                         "EntryTime": df.index[pos], "ExitTime": df.index[pos + durata]})


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def saltato(nome, motivo):
        print(f"  [SALTATO] {nome}  — {motivo}")

    contratti = {"minimo": 1, "passo": 1}
    tab = _tab(TRADE_LIBRO)

    # ----------------------------------------------------------- libro --
    print("\nA · Esempi numerici del libro")
    attesi = {  # fig. 4.1, p. 57: contratti trade per trade e capitale finale
        0.025: ([2, 1, 2, 2, 1, 1, 2, 2, 2, 2], 110_800), 0.05: ([4, 3, 4, 4, 3, 3, 4, 5, 4, 4], 123_150),
        0.075: ([6, 5, 6, 6, 6, 5, 6, 8, 7, 7], 135_450), 0.10: ([8, 7, 8, 8, 8, 7, 8, 12, 11, 11], 148_450),
        0.15: ([12, 11, 12, 14, 11, 10, 13, 21, 18, 20], 174_300),
        0.20: ([16, 14, 17, 19, 15, 13, 18, 33, 27, 29], 197_250),
        0.25: ([20, 18, 22, 25, 19, 15, 23, 47, 36, 40], 215_950),
        0.50: ([40, 32, 48, 62, 31, 18, 36, 113, 57, 70], 201_750)}
    percorsi = {f: mm.ripercorri(tab, 100_000, f, contratti) for f in attesi}
    ok = all(percorsi[f]["lotti"].astype(int).tolist() == c and
             np.isclose(percorsi[f]["capitale_dopo"].iloc[-1], fin) for f, (c, fin) in attesi.items())
    check("1. tab. 4.2 e fig. 4.1 (p. 56-57): contratti e capitale finale per le 8 percentuali", ok)
    dd = {f: round(float(p["drawdown_pct"].max()), 2) for f, p in percorsi.items()}
    check("2. fig. 4.2 (p. 58): drawdown massimo 3,44 · 7,64 · 12,53 · 16,26 · 24,42 · 69,91 %",
          [dd[f] for f in (0.025, 0.05, 0.075, 0.10, 0.15, 0.50)] == [3.44, 7.64, 12.53, 16.26, 24.42, 69.91])
    check("3. fig. 4.2, colonne 20% e 25%: rifatti 31,74 e 39,01 % (il libro scrive 33,64 e 43,41: "
          "massimo sbagliato in alcune righe, docs/61 §7)", (dd[0.20], dd[0.25]) == (31.74, 39.01))
    twr_attesi = [1.1366, 1.2732, 1.4082, 1.5397, 1.7857, 1.9980, 2.1647, 2.0726]
    check("4. fig. 4.4 (p. 64): TWR teorici delle 8 percentuali",
          [round(mm.twr(TRADE_LIBRO / 1250, f), 4) for f in attesi] == twr_attesi)
    f_opt, t_opt = mm.optimal_f(TRADE_LIBRO / 1250, np.arange(1, 100) / 100)
    check("5. optimal f dei 10 trade = 36 %, TWR 2,3260 (il libro scrive 37 %: 2,3251 e' il TWR al 37 %)",
          np.isclose(f_opt, 0.36) and round(t_opt, 4) == 2.3260
          and round(mm.twr(TRADE_LIBRO / 1250, 0.37), 4) == 2.3251)
    check("6. Kelly, moneta che paga 1,25 contro 1 (p. 22): 10 %", np.isclose(mm.kelly([1.25, -1] * 50), 0.10))
    check("7. Kelly, palline 3 contro 1 su 3 (p. 27): 11,11 %; 2,5 contro 1 (p. 29): 6,67 %",
          np.isclose(mm.kelly([3, -1, -1] * 30), 1 / 9) and round(mm.kelly([2.5, -1, -1] * 30), 4) == 0.0667)
    sistema = [1.3248] * 4907 + [-1.0] * 5093
    check("8. Kelly del sistema del cap. 3 (p. 37-40): W 49,07 %, R 1,3248 -> 10,6265 %",
          round(mm.kelly(sistema), 6) == 0.106265, f"{mm.kelly(sistema) * 100:.4f} %")
    check("9. tab. 6.3 (p. 116): 14.900 al 10 % su stop 1.500 -> 0 contratti, trade saltato",
          mm.lotti_rischio_fisso(14_900, 0.10, 1500, 1, contratti) == (0.0, mm.SALTATO_MINIMO))
    check("10. tab. 6.4 (p. 117): con l'11 % lo stesso capitale fa 1 contratto",
          mm.lotti_rischio_fisso(14_900, 0.11, 1500, 1, contratti) == (1.0, mm.OK))
    check("11. Mediaset (p. 220): 100.000 al 2 % con stop di 0,55 -> 3.636 azioni",
          mm.lotti_rischio_fisso(100_000, 0.02, 0.55, 1, {"passo": 1})[0] == 3636)
    check("12. DAX (p. 235): rischio 96 punti x 25 = 2.400 > 2.000 -> 0 contratti, trade saltato",
          mm.lotti_rischio_fisso(100_000, 0.02, 96, 25, contratti) == (0.0, mm.SALTATO_MINIMO))
    check("13. p. 54: 100.000 al 5 % e al 4 % su stop 1.250 -> 4 e 3 contratti",
          mm.lotti_rischio_fisso(100_000, 0.05, 1250, 1, contratti)[0] == 4
          and mm.lotti_rischio_fisso(100_000, 0.04, 1250, 1, contratti)[0] == 3)

    # ------------------------------------------------------ limiti lotti --
    print("\nB · Limiti dei lotti (il salto si prova qui, a parte)")
    lim = {"minimo": 0.01, "passo": 0.01, "massimo": 2.0}
    check("14. arrotondamento per difetto al passo: 10.000 al 1 % su 30 pips x 10 $ = 0,333 -> 0,33",
          mm.lotti_rischio_fisso(10_000, 0.01, 30, 10, lim) == (0.33, mm.OK))
    check("15. passo 0,1 (indici): 0,666 -> 0,6",
          mm.lotti_rischio_fisso(10_000, 0.01, 15, 10, {"minimo": 0.1, "passo": 0.1})[0] == 0.6)
    check("16. sotto il lotto minimo -> 0 lotti, saltato",
          mm.lotti_rischio_fisso(100, 0.01, 30, 10, lim) == (0.0, mm.SALTATO_MINIMO))
    check("17. sopra il lotto massimo -> tagliato al massimo",
          mm.lotti_rischio_fisso(1e7, 0.01, 30, 10, lim) == (2.0, mm.RIDOTTO_MASSIMO))
    lv = dict(lim, leva=30)
    check("18. leva 30: 10.000 al 5 % su 5 pips = 10 lotti, nozionale 110.000 per lotto -> 2,72 lotti, "
          "ridotto dalla leva",
          mm.lotti_rischio_fisso(10_000, 0.05, 5, 10, dict(lv, massimo=None), nozionale_lotto=110_000)
          == (2.72, mm.RIDOTTO_LEVA))
    check("19. leva che porta sotto il minimo -> saltato, contato come intervento della leva",
          mm.lotti_rischio_fisso(30, 0.5, 1, 10, dict(lv, minimo=0.01), nozionale_lotto=110_000)
          == (0.0, mm.SALTATO_LEVA))
    check("20. rischio ignoto (NaN) -> saltato",
          mm.lotti_rischio_fisso(10_000, 0.01, np.nan, 10, lim) == (0.0, mm.SALTATO_RISCHIO))
    t_salti = _tab([-100.0] * 12 + [500.0] * 12, rischio=100.0, v_in=1.0, v_out=1.0,
                   nozionale_lotto=1.0)
    p = mm.ripercorri(t_salti, 1_000, 0.10, {"minimo": 1, "passo": 1})
    s = mm.sintesi_percorso(p, 1_000)
    check("21. capitale che scende sotto il minimo: da li' in poi tutti saltati, conteggio esatto",
          s["fatti"] == 1 and s["saltati"] == 23 and np.isclose(s["capitale_finale"], 900),
          f"fatti {s['fatti']} · saltati {s['saltati']}")
    p = mm.ripercorri(_tab([-100.0, 50.0], rischio=10.0), 1_000, 1.0, SPENTI)
    check("22. il capitale non scende sotto zero; a zero il trade dopo fa 0 lotti",
          p["capitale_dopo"].iloc[0] == 0 and p["lotti"].iloc[1] == 0)
    t_leva = _tab([10.0] * 5, rischio=2.0, v_in=10.0, v_out=10.0, nozionale_lotto=100_000.0)
    s = mm.sintesi_percorso(mm.ripercorri(t_leva, 10_000, 0.05, {"passo": 0.01, "leva": 30}), 10_000)
    check("23. interventi della leva contati nella sintesi", s["leva_interviene"] == 5 and s["saltati"] == 0)

    # ---------------------------------------------------------- identita' --
    print("\nC · Identita' (salto sotto il minimo e leva spenti)")
    rng = np.random.default_rng(7)
    pips = rng.normal(2, 20, 300)
    rischio = rng.uniform(10, 40, 300)
    t_id = _tab(pips, rischio=rischio, v_in=10.0, v_out=10.0)
    for f in (0.005, 0.02):
        fin = mm.ripercorri(t_id, 10_000, f, SPENTI)["capitale_dopo"].iloc[-1]
        check(f"24. lotti continui, f {f:.1%}: capitale finale = capitale x TWR",
              np.isclose(fin, 10_000 * mm.twr(pips / rischio, f), rtol=1e-12))
    p = mm.ripercorri(t_id.assign(rischio_pips=1.0, valore_entrata=1.0), 1.0, 1.0, SPENTI)
    check("25. 1 lotto sempre (capitale 1, f 100 %, rischio 1): guadagno = pips x valore all'uscita",
          np.allclose(p["guadagno"].to_numpy()[:1], pips[:1] * 10.0))
    p_lf = mm.ripercorri(t_id, 10_000, 0.01, SPENTI)
    check("26. guadagno di ogni trade = lotti x pips x valore all'uscita",
          np.allclose(p_lf["guadagno"], p_lf["lotti"] * pips * 10.0))
    seq = np.arange(len(t_id))[None, :]
    r = mm.montecarlo_mm(t_id, 10_000, [0.01], len(t_id), limiti=SPENTI, indici=seq)[0.01]
    check("27. Monte Carlo con la sequenza vera = storia vera (capitale e drawdown)",
          np.isclose(r["finale"][0], p_lf["capitale_dopo"].iloc[-1])
          and np.isclose(r["drawdown_pct"][0], p_lf["drawdown_pct"].max()))
    lim_on = {"minimo": 0.01, "passo": 0.01, "massimo": 200, "leva": 30}
    t_noz = t_id.assign(nozionale_lotto=110_000.0)
    r2 = mm.montecarlo_mm(t_noz, 10_000, [0.01], len(t_id), limiti=lim_on, indici=seq)[0.01]
    p2 = mm.ripercorri(t_noz, 10_000, 0.01, lim_on)
    check("28. stessa identita' con tutti i limiti accesi (lotti, salto e leva come nella storia vera)",
          np.isclose(r2["finale"][0], p2["capitale_dopo"].iloc[-1])
          and r2["saltati"][0] == (p2["lotti"] == 0).sum())

    # -------------------------------------------------------- lookahead --
    print("\nD · Nessun lookahead")
    p_tutto = mm.ripercorri(t_noz, 10_000, 0.02, lim_on)
    ok = all(mm.ripercorri(t_noz.iloc[:k], 10_000, 0.02, lim_on)
             .equals(p_tutto.iloc[:k]) for k in (1, 7, 50, 199))
    check("29. troncamento: i primi k trade danno gli stessi lotti e capitale della sequenza intera", ok)
    futuro = t_noz.copy()
    futuro.loc[150:, "pips_netti"] = -999.0
    check("30. trade futuri cambiati: lotti e capitale fino al trade 150 identici",
          mm.ripercorri(futuro, 10_000, 0.02, lim_on).iloc[:151][["lotti", "capitale_prima"]]
          .equals(p_tutto.iloc[:151][["lotti", "capitale_prima"]]))

    eur = _carica(QUI / "EURUSD_M15.csv")
    eur = eur.loc["2024-01-01":"2024-12-31"]
    finti = _trade_finti(eur)
    tb = tabella_trade(finti, eur, "EURUSD", pip_symbol("EURUSD"), spread_pips=0.8, perc_sl=0,
                       n_barre_long=10, n_barre_short=18)
    ok = True
    for i in (0, 13, 39):
        pos = int(finti["EntryBar"].iloc[i])
        corto = tabella_trade(finti.iloc[[i]], eur.iloc[:pos + 1], "EURUSD", pip_symbol("EURUSD"),
                              spread_pips=0.8, perc_sl=0, n_barre_long=10, n_barre_short=18)
        ok &= np.isclose(corto["frazione_stop"].iloc[0], tb["frazione_stop"].iloc[i])
    check("31. stop di calcolo (stop spento): uguale con lo storico tagliato alla barra d'ingresso",
          ok and np.isfinite(tb["frazione_stop"]).all())
    ingressi = finti["EntryBar"].to_numpy()
    ok = True
    for i in (2, 20, 37):
        sporco = eur.copy()
        for col in ("Open", "High", "Low", "Close"):      # dalla barra d'ingresso in poi: il futuro del trade i
            sporco.iloc[ingressi[i]:, sporco.columns.get_loc(col)] *= 1.01
        tb_s = tabella_trade(finti.iloc[[i]], sporco, "EURUSD", pip_symbol("EURUSD"), spread_pips=0.8,
                             perc_sl=0, n_barre_long=10, n_barre_short=18)
        ok &= (np.isclose(tb_s["prezzo_segnale"].iloc[0], tb["prezzo_segnale"].iloc[i])
               and np.isclose(tb_s["rischio_pips"].iloc[0], tb["rischio_pips"].iloc[i]))
    check("32. prezzi falsati dalla barra d'ingresso in poi: prezzo del segnale, stop di calcolo e rischio "
          "del trade invariati", ok)
    check("33. prezzo del segnale = chiusura della barra prima dell'ingresso",
          np.allclose(tb["prezzo_segnale"], eur["Close"].to_numpy()[ingressi - 1]))

    # ------------------------------------------------- calibrazione --
    print("\nE · Calibrazione e banda")
    cal, f = mm.calibra(t_noz, 10_000, 20, 200, n_sim=2_000, limiti=lim_on)
    sotto = cal.loc[cal["f"] <= f, "drawdown_p95"] if f else pd.Series(dtype=float)
    dopo = cal.loc[cal["f"] > f, "drawdown_p95"] if f else pd.Series(dtype=float)
    check("34. scelta: tutte le frazioni fino alla scelta stanno entro il limite, la successiva no",
          f is not None and (sotto <= 20).all() and (dopo.empty or dopo.iloc[0] > 20),
          f"f scelta {f:.2%}" if f else "nessuna")
    check("35. drawdown al 95° crescente con la frazione (stesse sequenze per tutte)",
          cal["drawdown_p95"].is_monotonic_increasing)
    _, f_tutto = mm.calibra(t_noz, 10_000, 1e9, 50, n_sim=500, limiti=lim_on)
    _, f_niente = mm.calibra(t_noz, 10_000, 0.001, 50, n_sim=500, limiti=lim_on)
    check("36. limite enorme -> l'ultima della griglia; limite minuscolo -> nessuna scelta",
          np.isclose(f_tutto, mm.GRIGLIA[-1]) and f_niente is None)
    a = mm.calibra(t_noz, 10_000, 20, 100, n_sim=500, limiti=lim_on, seed=4)[0]
    b = mm.calibra(t_noz, 10_000, 20, 100, n_sim=500, limiti=lim_on, seed=4)[0]
    check("37. stesso seme -> stessa tabella", a.equals(b))
    bd = mm.banda(t_noz, 10_000, 0.01, 60, n_sim=1_000, limiti=lim_on)
    check("38. banda: 61 righe (da 0 a 60 trade), parte dal capitale, 5° <= 50° <= 95°",
          len(bd) == 61 and np.allclose(bd.iloc[0], 10_000)
          and (bd["p5"] <= bd["p50"]).all() and (bd["p50"] <= bd["p95"]).all())
    check("39. optimal f e Kelly senza vantaggio: optimal f 0 (TWR 1), Kelly negativo",
          mm.optimal_f([-1, 0.5, -1, 0.5]) == (0.0, 1.0) and mm.kelly([-1, 0.5, -1, 0.5]) < 0)

    # -------------------------------------------- backtest vero EURUSD --
    print("\nF · Adattatore su un backtest vero di EURUSD (2024)")
    d = _muto(aggiungi_indicatori, eur.copy())
    clear_registry()
    segnali = pd.Series(np.random.default_rng(11).random(len(d)), index=d.index)
    register_entry("T_MM_LONG", 1)(lambda x: segnali.reindex(x.index) < 0.004)
    register_entry("T_MM_SHORT", -1)(lambda x: segnali.reindex(x.index) > 0.996)
    pip = pip_symbol("EURUSD")
    costi = dict(spread=0.8 * pip / float(d["Close"].median()), commission=0.0, cash=1e7)
    comuni = dict(entry_long="T_MM_LONG", entry_short="T_MM_SHORT", filtri=[], n_barre=10,
                  n_barre_long=10, n_barre_short=18, finestra=500, lag=1, min_trades=1,
                  inverti_su_opposto=True, verbose=False, **costi)
    fs_on = _muto(run_filter_search_bt, d, perc_sl=90.0, **comuni)
    fs_off = _muto(run_filter_search_bt, d, perc_sl=0.0, **comuni)
    tr_on, tr_off = fs_on.trades(), fs_off.trades()
    clear_registry()
    t_on = tabella_trade(tr_on, d, "EURUSD", pip, spread_pips=0.8, perc_sl=90,
                         n_barre_long=10, n_barre_short=18)
    t_off = tabella_trade(tr_off, d, "EURUSD", pip, spread_pips=0.8, perc_sl=0,
                          n_barre_long=10, n_barre_short=18)
    check("40. pips netti della tabella identici a pips_per_dataset (stesso ordine di uscita)",
          np.array_equal(t_on["pips_netti"].to_numpy(),
                         pips_per_dataset(tr_on, None, pip, 0.0, dataset="IS"))
          and np.array_equal(t_off["pips_netti"].to_numpy(),
                             pips_per_dataset(tr_off, None, pip, 0.0, dataset="IS")),
          f"{len(t_on)} e {len(t_off)} trade")
    s_m = soglie_per_lato(d, 10, 18, 500, 90.0, 0.0, lag=1)
    pos = d.index.get_indexer(pd.DatetimeIndex(t_on["entrata"]))
    attese = np.where(t_on["lato"] > 0, s_m["sl_long"].to_numpy()[pos], s_m["sl_short"].to_numpy()[pos])
    check("41. stop acceso: frazione dello stop dei trade = soglia adattiva della barra d'ingresso",
          np.allclose(t_on["frazione_stop"], attese, rtol=1e-9))
    pos_off = d.index.get_indexer(pd.DatetimeIndex(t_off["entrata"]))
    vuoti = ~np.isfinite(t_off["frazione_stop"].to_numpy())
    riscaldamento = 500 + 18 + 1                     # finestra + barre del lato piu' lungo + lag
    check("42. stop spento: stop di calcolo pieno dopo il riscaldamento, ignoto (trade saltato) solo prima",
          (pos_off[vuoti] < riscaldamento).all() and (pos_off[~vuoti] >= 500).all()
          and (t_off.loc[~vuoti, "rischio_pips"] > 0.8).all(),
          f"{int(vuoti.sum())} trade nel riscaldamento")
    check("43. rischio = frazione x prezzo del segnale / pip + costo (0,8 pips di spread)",
          np.allclose(t_on["rischio_pips"],
                      t_on["frazione_stop"] * t_on["prezzo_segnale"] / pip + 0.8))
    check("44. EURUSD: valore del pip 10 $ e nozionale 100.000 x prezzo del segnale",
          np.allclose(t_on["valore_entrata"], 10.0) and np.allclose(t_on["valore_uscita"], 10.0)
          and np.allclose(t_on["nozionale_lotto"], 100_000 * t_on["prezzo_segnale"]))
    check("45. il money management non cambia i trade: stessi trade prima e dopo la tabella",
          fs_on.trades().equals(tr_on))

    # ---------------------------------------------- symbol in dati/ --
    print("\nG · Valore del pip trade per trade sui symbol di dati/")
    cartella = QUI / "dati"
    for sym in ("USDJPY", "DE40", "XAUUSD", "BTCUSD"):
        f_csv = cartella / f"{sym}_M15.csv"
        if not f_csv.exists() or (sym == "DE40" and not (cartella / "EURUSD_M15.csv").exists()):
            saltato(f"G {sym}", "dati/ non c'e' (es. Colab)")
            continue
        dd_s = _carica(f_csv).loc["2024-01-01":"2024-12-31"]
        ft = _trade_finti(dd_s, n=20, seme=5)
        tb = tabella_trade(ft, dd_s, sym, pip_symbol(sym), spread_pips=1.0, perc_sl=90,
                           cartella=cartella)
        if sym == "DE40":
            cambi = _carica(cartella / "EURUSD_M15.csv")["Close"]
            atteso = [valore_pip_lotto(sym, 1.0, cambio=float(cambi.loc[:t].iloc[-1]))
                      for t in dd_s.index[ft["EntryBar"].to_numpy() - 1]]
        else:
            atteso = [valore_pip_lotto(sym, pip_symbol(sym), prezzo=p) for p in tb["prezzo_segnale"]]
        check(f"G {sym}: valore del pip al segnale = valore_pip_lotto con prezzo e cambio di quel momento",
              np.allclose(tb["valore_entrata"], atteso),
              f"da {tb['valore_entrata'].min():.4g} a {tb['valore_entrata'].max():.4g} $")
    check("G limiti: DE40 0,1 / 0,1 / 250 con leva 20; BTCUSD 0,01 / 0,01 / 10 con leva 2",
          limiti_symbol("DE40") == {"minimo": 0.1, "passo": 0.1, "massimo": 250.0, "leva": 20}
          and limiti_symbol("BTCUSD") == {"minimo": 0.01, "passo": 0.01, "massimo": 10.0, "leva": 2})

    # ------------------------------------------------- portabilita' --
    print("\nH · Il modulo puro si copia nel repo crypto")
    codice = (QUI / "engine" / "money_management.py").read_text(encoding="utf-8")
    import_righe = [r for r in codice.splitlines() if r.startswith(("import ", "from "))]
    pulito = subprocess.run(
        [sys.executable, "-c",
         "import sys, importlib.util as u; s=u.spec_from_file_location('m','engine/money_management.py'); "
         "m=u.module_from_spec(s); s.loader.exec_module(m); "
         "print(sorted(k for k in sys.modules if k.startswith('engine')))"],
        cwd=QUI, capture_output=True, text=True).stdout.strip() == "[]"
    check("46. money_management.py importa solo numpy e pandas e gira da solo, senza engine/",
          all(r.split()[1].split(".")[0] in ("__future__", "numpy", "pandas") for r in import_righe) and pulito,
          " · ".join(import_righe))

    # ----------------------------------------------------------- fase 2 --
    print("\nI · Fase 2: z-score e tabella di controllo (docs/61 §13)")
    # sequenza con i numeri del libro: 243 serie vincenti (230 da 2 trade + 13 da 1 = 473)
    # alternate a 243 serie perdenti (5 da 3 + 238 da 2 = 491): 964 trade, 486 serie
    vinc = [2] * 230 + [1] * 13
    perd = [3] * 5 + [2] * 238
    seq = []
    for a, b in zip(vinc, perd):
        seq += [1.0] * a + [-1.0] * b
    zs = mm.zscore(seq)
    check("47. z-score del libro (p. 112): N 964, serie 486, W 473, L 491 -> 0,2364",
          (zs["n"], zs["serie"], zs["vincenti"], zs["perdenti"]) == (964, 486, 473, 491)
          and round(zs["z"], 4) == 0.2365 and abs(zs["z"] - 0.2364) < 2e-4, f"z = {zs['z']:.4f}")
    check("48. alternanza perfetta -> z molto positivo; due blocchi -> z molto negativo",
          mm.zscore([1.0, -1.0] * 200)["z"] > 10 and mm.zscore([1.0] * 200 + [-1.0] * 200)["z"] < -10)
    check("49. i trade a zero contano fra i perdenti; senza perdite z non disponibile",
          mm.zscore([1.0, 0.0, 1.0, 0.0])["perdenti"] == 2 and np.isnan(mm.zscore([1.0, 2.0])["z"]))
    orizz = {"3 mesi": 40, "12 mesi": 160}
    ctrl = mm.tabella_controllo(t_noz, 10_000, 0.01, orizz, n_sim=2_000, limiti=lim_on, seed=3)
    rif = mm.montecarlo_mm(t_noz, 10_000, [0.01], 160, n_sim=2_000, limiti=lim_on, seed=3)[0.01]
    check("50. tabella di controllo: percentili identici a montecarlo_mm alla stessa lunghezza e seme",
          np.isclose(ctrl.loc[1, "drawdown_p95"], np.percentile(rif["drawdown_pct"], 95))
          and np.isclose(ctrl.loc[1, "drawdown_p99"], np.percentile(rif["drawdown_pct"], 99))
          and np.isclose(ctrl.loc[1, "rendimento_p5"], np.percentile((rif["finale"] / 10_000 - 1) * 100, 5)))
    check("51. tabella di controllo: 50° <= 95° <= 99°, e il drawdown cresce col periodo",
          (ctrl["drawdown_p50"] <= ctrl["drawdown_p95"]).all()
          and (ctrl["drawdown_p95"] <= ctrl["drawdown_p99"]).all()
          and ctrl["drawdown_p95"].is_monotonic_increasing)
    dd_sim = mm.montecarlo_mm(t_noz, 10_000, [0.01], 100, n_sim=2_000, limiti=lim_on, seed=0)[0.01]["drawdown_pct"]
    q90 = float(np.percentile(dd_sim, 90))
    check("52. percentile di un drawdown osservato: il 90° percentile simulato cade al 90 %",
          abs(mm.percentile_drawdown(t_noz, 10_000, 0.01, 100, q90, n_sim=2_000, limiti=lim_on) - 90) < 0.1
          and mm.percentile_drawdown(t_noz, 10_000, 0.01, 100, 1e9, n_sim=500, limiti=lim_on) == 100.0)

    ok, tot = sum(ESITI), len(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
