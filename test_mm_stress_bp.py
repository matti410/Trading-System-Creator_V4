"""
Suite di validazione del money management P1-P4 e dello stress test in bp
(23/10/2026, docs/61 §15).

Si lancia da terminale, dalla cartella del progetto:

    python test_mm_stress_bp.py

Non serve MetaTrader 5 e non serve nessun file di dati: usa trade costruiti a
mano e un perpetual sintetico in una cartella temporanea. Sezioni:

    A · P1, la secure f controllata anche sulla storia vera (tratti lunghi
        quanto l'orizzonte del Monte Carlo)
    B · P2, l'avviso oltre Kelly (Kelly calcolato a mano)
    C · P3, rischio in percentuale contro stessa esposizione a ogni trade
    D · P4, i decimali dei lotti dal passo dell'exchange
    E · lo stress test in bp: due trade del +1 % a prezzi diversi, lotti dal
        drawdown in bp e dal prezzo
    F · il broker resta in pips, identico al calcolo di prima
    G · il percorso del Lab su un perpetual sintetico (schermate 7 e 9)
"""
from __future__ import annotations

import contextlib
import copy
import io
import os
import sys
import tempfile
import warnings

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

import engine.money_management as mm
from engine import registry as reg
from engine.montecarlo import (bp_per_dataset, montecarlo_completo, pips_per_dataset, sizing,
                               valore_pip_lotto)
from engine.quarantena import imposta_rollover

warnings.simplefilter("ignore")

SPENTI = {}            # nessun limite dei lotti: lotti continui


def _muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def _tabella(pips, inizio="2021-01-04"):
    """Tabella del money management: rischio 1 pip, valore 1 $ per pip, date un giorno l'una."""
    n = len(pips)
    entrate = pd.date_range(inizio, periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"entrata": entrate, "uscita": entrate + pd.Timedelta("12h"),
                         "pips_netti": np.asarray(pips, dtype=float), "rischio_pips": 1.0,
                         "valore_entrata": 1.0, "valore_uscita": 1.0})


def _trades(entrate, uscite, prezzi_in, prezzi_out):
    n = len(prezzi_in)
    return pd.DataFrame({
        "Size": np.ones(n), "EntryPrice": np.asarray(prezzi_in, dtype=float),
        "ExitPrice": np.asarray(prezzi_out, dtype=float),
        "EntryBar": np.arange(n), "ExitBar": np.arange(n) + 1,
        "EntryTime": pd.DatetimeIndex(entrate), "ExitTime": pd.DatetimeIndex(uscite)})


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    import engine.vetrina as vt

    # =================================================================== A ==
    print("\nA · P1: la secure f anche sulla storia vera")
    # 100 trade: vincenti +1,5 R, perdenti -1 R; 30 perdenti, di cui 10 DI FILA dal trade 40
    pips = np.full(100, 1.5)
    pips[40:50] = -1.0
    altri = [i for i in range(0, 100, 3) if not 40 <= i < 50][:20]
    pips[altri] = -1.0
    assert (pips < 0).sum() == 30
    tab = _tabella(pips)
    N, DD = 50, 20.0
    cal, f_mc = mm.calibra(tab, 10_000, DD, N, n_sim=4_000, limiti=SPENTI)
    st = mm.controlla_storia(tab, 10_000, DD, N, f_mc, limiti=SPENTI)
    t = st["tabella"]
    f = st["f"]
    i = int(np.argmin(np.abs(t["f"].to_numpy() - f))) if f is not None else -1
    riga = vt._riga_ha_deciso(st, tab, DD)
    peggiore = t.iloc[int(np.argmin(np.abs(t["f"].to_numpy() - f_mc)))]
    check("1. 10 perdite di fila (la storia vera e' peggiore del 95° percentile): P1 scende sotto la scelta "
          "del Monte Carlo; con la percentuale scelta il tratto peggiore sta entro il limite, con il gradino "
          "sopra no; la riga dice «storia vera» con le date del tratto peggiore (contiene le 10 perdite)",
          f_mc is not None and f is not None and f < f_mc and st["deciso"] == "storia vera"
          and t["drawdown_storia"].iloc[i] <= DD < t["drawdown_storia"].iloc[i + 1]
          and peggiore["inizio"] <= 40 and peggiore["fine"] >= 49 and st["lunghezza"] == N
          and st["tratti"] == 51 and riga.startswith("Ha deciso: la storia vera")
          and f"{tab['entrata'].iloc[int(peggiore['inizio'])]:%d/%m/%Y}" in riga,
          f"Monte Carlo {f_mc:.2%}, storia vera {f:.2%} · {riga[:150]}…")

    alterna = np.where(np.arange(100) % 10 < 3, -1.0, 1.5)            # le stesse 30 perdite, mai piu' di 3 di fila
    tab2 = _tabella(alterna)
    cal2, f_mc2 = mm.calibra(tab2, 10_000, DD, N, n_sim=4_000, limiti=SPENTI)
    st2 = mm.controlla_storia(tab2, 10_000, DD, N, f_mc2, limiti=SPENTI)
    riga2 = vt._riga_ha_deciso(st2, tab2, DD)
    check("2. storia vera innocua (perdite sparse): P1 lascia la percentuale del Monte Carlo identica al bit, "
          "la riga dice «Monte Carlo»",
          f_mc2 is not None and st2["f"] == f_mc2 and st2["deciso"] == "Monte Carlo"
          and riga2.startswith("Ha deciso: il Monte Carlo"), f"{f_mc2:.2%}")

    cal3, f_mc3 = mm.calibra(tab, 10_000, 2.0, N, n_sim=4_000, limiti=SPENTI)
    st3 = mm.controlla_storia(tab, 10_000, 2.0, N, f_mc3, limiti=SPENTI)
    riga3 = vt._riga_ha_deciso(st3, tab, 2.0)
    check("3. limite del 2 %: il Monte Carlo passa, ma 10 perdite di fila allo 0,25 % fanno il 2,47 %: nessun "
          "gradino tiene la storia vera, percentuale «nessuna» e la riga lo dice",
          f_mc3 is not None and st3["f"] is None and st3["deciso"] == "storia vera"
          and np.isclose(t["drawdown_storia"].iloc[0], (1 - 0.9975 ** 10) * 100, atol=0.3)
          and "nemmeno il più basso" in riga3, f"Monte Carlo {f_mc3:.2%} · drawdown storia allo 0,25 % "
          f"{st3['tabella']['drawdown_storia'].iloc[0]:.2f} %")

    # =================================================================== B ==
    print("\nB · P2: l'avviso oltre Kelly")
    k = mm.kelly([2, 2, -1, -1, -1])
    kn = mm.kelly([1, -1, -1])
    check("4. Kelly a mano: W 0,4, R 2 -> 0,4 - 0,6/2 = 10 %; avviso con f 15 % (i due numeri), niente con "
          "f 5 %; Kelly [+1, -1, -1] = 1/3 - 2/3 = -33 %: l'avviso dice «≤ 0»",
          np.isclose(k, 0.10) and np.isclose(kn, -1 / 3)
          and "15,00 %" in vt._avviso_kelly(0.15, k) and "10,00 %" in vt._avviso_kelly(0.15, k)
          and "supera" in vt._avviso_kelly(0.15, k) and vt._avviso_kelly(0.05, k) is None
          and "≤ 0" in vt._avviso_kelly(0.01, kn) and vt._avviso_kelly(None, k) is None,
          vt._avviso_kelly(0.15, k))

    # =================================================================== C ==
    print("\nC · P3: rischio in percentuale contro stessa esposizione")
    rng = np.random.default_rng(3)
    casuali = np.where(rng.random(300) < 0.45, rng.uniform(0.5, 3.0, 300), -rng.uniform(0.3, 1.2, 300))
    tc = _tabella(casuali)
    tc["nozionale_lotto"] = rng.uniform(5_000, 60_000, 300)
    _, fc = mm.calibra(tc, 10_000, 20.0, 80, n_sim=3_000, limiti=SPENTI)
    conf = mm.confronto_esposizione_fissa(tc, 10_000, fc, 80, n_sim=3_000, limiti=SPENTI, per_nozionale=True)
    cal_c, _ = mm.calibra(tc, 10_000, 20.0, 80, n_sim=3_000, limiti=SPENTI)
    rc = cal_c.iloc[int(np.argmin(np.abs(cal_c["f"].to_numpy() - fc)))]
    a_mano = mm.montecarlo_fisso(_tabella([10.0, -20.0, 5.0]), 100.0, 2.0, 4, indici=np.array([[0, 1, 1, 2]]))
    tn = _tabella([10.0, -20.0])
    tn["nozionale_lotto"] = [100.0, 200.0]
    noz = mm.montecarlo_fisso(tn, 1_000.0, 400.0, 2, indici=np.array([[0, 1]]), per_nozionale=True)
    check("5. P3: l'esposizione fissa trovata ha lo stesso drawdown sfortunato della percentuale (entro lo "
          "0,05 %); la riga della percentuale e' quella della calibrazione; a mano: 100 $, 2 lotti, trade "
          "+10, -20, -20, +5 -> 120, 80, 40, 50, drawdown 66,67 %; 400 $ di nozionale su trade del +10 % e "
          "del -10 % -> 1.000 +40 -40",
          abs(conf["drawdown_p95"].iloc[1] - conf["drawdown_p95"].iloc[0]) < 0.05
          and np.isclose(conf["drawdown_p95"].iloc[0], rc["drawdown_p95"])
          and np.isclose(conf["rendimento_p50"].iloc[0], rc["rendimento_p50"])
          and np.isclose(a_mano["finale"][0], 50.0) and np.isclose(a_mano["drawdown_pct"][0], 200 / 3)
          and np.isclose(noz["finale"][0], 1_000.0) and np.isclose(noz["drawdown_pct"][0], 40 / 1040 * 100),
          f"percentuale {fc:.2%}, esposizione fissa {conf['esposizione'].iloc[1]:,.0f} $ · drawdown "
          f"sfortunato {conf['drawdown_p95'].iloc[0]:.2f} / {conf['drawdown_p95'].iloc[1]:.2f} %")

    # =================================================================== G (preparazione) ==
    # il percorso del Lab su un perpetual sintetico serve alle sezioni D, E, F e G
    import engine.exchange as X
    from test_atlante import H, Mercato, _deriva_dopo, _indice, _registra_entry
    imposta_rollover(None)
    M = Mercato(_indice(giorni=500), seme=11)
    d0 = M.df()
    n = len(d0)
    pos = np.sort(np.random.default_rng(5).choice(np.arange(600, n - 2 * H), size=n // 80, replace=False))
    d = M.df(_deriva_dopo(n, pos, np.full(len(pos), 0.0003)))
    d[["Open", "High", "Low", "Close"]] *= 100.0                 # prezzi come BTC (pip 1 $)
    _registra_entry("T_MM_BP", 1, d.index[pos])
    orari = pd.date_range(d.index[0].floor("8h"), d.index[-1].ceil("8h"), freq="8h")
    fund = X.con_intervalli(pd.DataFrame({"tasso": 0.0001}, index=orari))
    with tempfile.TemporaryDirectory() as tmp:
        X.salva_csv(d, os.path.join(tmp, "BINANCE_PERP_BTCUSDT_M15.csv"))
        X.salva_funding(fund, X.file_funding("BINANCE_PERP_BTCUSDT", tmp))
        s = _muto(vt.prepara, "BINANCE_PERP_BTCUSDT", H=H, cartella=tmp)
        _muto(vt.esplora, s)
        _muto(vt.scegli_trigger, s, long="T_MM_BP")
        _muto(vt.imposta_uscite, s, barre_long=H, sl=90)
        _muto(vt.trova_strategia, s)
        _muto(vt.scheda, s, None)
        tr_is, tr_oos = s.trades_is.copy(), s.trades_oos.copy()
        m = _muto(vt.money_management, s, 10_000, 20, 1)
        r = _muto(vt.stress_test, s, 10_000)
        sb = copy.copy(s)                                        # la stessa scheda vista da un symbol del broker
        sb.symbol, sb.da_exchange, sb.mm, sb.tabelle = "EURUSD", False, None, {}
        rb = _muto(vt.stress_test, sb, 10_000)

    # =================================================================== D ==
    print("\nD · P4: i decimali dei lotti")
    sin = m["sintesi"].set_index("") if m["sintesi"] is not None else None
    lotti_txt = [] if sin is None else [sin.at[v, "In-sample (storia vera)"]
                                        for v in ("Lotti minimi", "Lotti medi", "Lotti massimi")]
    check("6. P4: passo 0,001 -> 3 decimali, 0,01 e 0,1 -> 2 (broker come prima); schermata 7 sul perpetual "
          "BTC: lotti scritti con 3 decimali, nessun «0,00»",
          vt._cifre_lotti(0.001) == 3 and vt._cifre_lotti(0.01) == 2 and vt._cifre_lotti(0.1) == 2
          and sin is not None and all(len(x.split(",")[-1]) == 3 and x != "0,000" for x in lotti_txt)
          and "0,00 " not in " ".join(lotti_txt), f"lotti {lotti_txt}")

    # =================================================================== E ==
    print("\nE · Lo stress test in bp")
    ent = pd.to_datetime(["2024-01-01 00:00", "2024-02-01 00:00"], utc=True)
    due = _trades(ent, ent + pd.Timedelta("2h"), [10_000.0, 50_000.0], [10_100.0, 50_500.0])
    bp = bp_per_dataset(due, due.iloc[:0], 1.0, 0.0)
    pp = pips_per_dataset(due, due.iloc[:0], 1.0, 0.0)
    check("7. due trade del +1 % a 10.000 e a 50.000 $: in bp 100 e 100 (pesano uguale), in pips 100 e 500",
          np.allclose(bp, [100.0, 100.0]) and np.allclose(pp, [100.0, 500.0]), f"bp {bp} · pips {pp}")
    sz = sizing(500.0, 2_000.0, 50_000.0 / 10_000.0, passo=0.001)
    check("8. lotti in bp: drawdown sfortunato 500 bp, prezzo 50.000 $ (1 bp con 1 lotto = 5 $), drawdown "
          "accettato 2.000 $ -> 0,8 lotti",
          np.isclose(sz["lotti_drawdown"], 0.8) and sz["lotti_consigliati"] == 0.8, f"{sz['lotti_consigliati']}")

    # =================================================================== F ==
    print("\nF · Il broker resta in pips")
    pips_b = pips_per_dataset(s.trades_is, s.trades_oos, s.fs.pip_size, s.fs.commission or 0.0, "FULL")
    mc_b = montecarlo_completo(pips_b, n_sim=20_000)
    sz_b = sizing(mc_b, 10_000, valore_pip_lotto("EURUSD", s.fs.pip_size, prezzo=float(s.df["Close"].iloc[-1])),
                  percentile=95, passo=0.01)
    cb = sb.tabelle["stress"]
    check("9. broker: stress test identico al calcolo in pips di prima (Monte Carlo, lotti, colonne «(pips)», "
          "nessuna riga del prezzo)",
          rb["unita"] == "pips" and all(rb["montecarlo"][k2] == mc_b[k2] for k2 in mc_b if not k2.startswith("_"))
          and rb["sizing"] == sz_b and "Drawdown da allarme (pips)" in cb["controllo"].columns
          and "Prezzo usato per i lotti" not in list(cb["sintesi"][""]) and "prezzo" not in rb,
          f"{mc_b['n_trade']} trade, lotti {sz_b['lotti_consigliati']}")

    # =================================================================== G ==
    print("\nG · Il percorso del Lab sul perpetual sintetico")
    bp_s = bp_per_dataset(s.trades_is, s.trades_oos, s.fs.pip_size, s.fs.commission or 0.0, "FULL")
    mc_s = montecarlo_completo(bp_s, n_sim=20_000)
    st_tab = s.tabelle["stress"]
    prezzo = float(s.df["Close"].iloc[-1])
    avviso = m["avviso_kelly"]
    k_s, f_s = m["kelly"], m["f"]
    kelly_ok = ((f_s is None and avviso is None) or (f_s is not None and np.isfinite(k_s) and k_s <= 0
                and "≤ 0" in avviso) or (f_s is not None and np.isfinite(k_s) and k_s > 0
                and ((f_s > k_s) == (avviso is not None and "supera" in avviso))))
    fissa = m["esposizione_fissa"]
    check("10. Lab: stress test in bp (Monte Carlo identico a montecarlo_completo sui bp IS + OOS, colonne "
          "«(bp)», riga del prezzo, lotti = drawdown accettato / (drawdown al 95° x prezzo / 10.000)); "
          "schermata 7 con la riga «Ha deciso», l'avviso di Kelly coerente e la tabellina P3 in $ di "
          "nozionale; i trade della scheda non cambiano",
          r["unita"] == "bp" and all(r["montecarlo"][k2] == mc_s[k2] for k2 in mc_s if not k2.startswith("_"))
          and "Drawdown da allarme (bp)" in st_tab["controllo"].columns
          and "Prezzo usato per i lotti" in list(st_tab["sintesi"][""]) and r["prezzo"] == prezzo
          and np.isclose(r["sizing"]["lotti_drawdown"], r["drawdown_max_usd"] / (mc_s["dd_p95"] * prezzo / 1e4))
          and m["riga_deciso"].startswith("Ha deciso") and kelly_ok and f_s is not None
          and fissa is not None and len(fissa) == 2 and "$ di nozionale" in fissa["Esposizione"].iloc[1]
          and s.trades_is.equals(tr_is) and s.trades_oos.equals(tr_oos),
          f"{mc_s['n_trade']} trade · drawdown sfortunato {mc_s['dd_p95']:.0f} bp · lotti "
          f"{r['sizing']['lotti_consigliati']} · percentuale {f_s} ({m['deciso']}) · Kelly {k_s:.2%}")

    reg.clear_registry()
    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
