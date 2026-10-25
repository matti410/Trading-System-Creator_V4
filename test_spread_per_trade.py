"""
Suite di validazione dello SPREAD PER TRADE (25/10/2026, docs/71, strada D).

Sui symbol da exchange lo spread di un passo esce dal prezzo di fill e
diventa un costo di ogni trade nella colonna CostoExtraPips: fisso in pips,
passo / prezzo d'ingresso in bp. Moduli: engine/exchange.py
(aggiungi_spread_passo, spread_bp), engine/exit_search_bt.py,
engine/filter_search_bt.py, engine/due_meta.py (spread_passo_pips),
engine/atlante.py, engine/confidenza.py (costo per barra), engine/vetrina.py
(costi_storico, money management, riepilogo).

Cosa verifica (i numeri sono quelli del docs/71 §4)
-------------
A  un trade a mano: Open 100 e 200, passo 0,01, pip 0,01 -> 1 pip, 1 bp e 0,5 bp (1);
B  i due motori con spread zero e il passo in CostoExtraPips: trade identici al
   bit (2); fill all'Open; la somma torna sui trade con la stessa uscita (3);
   due_meta porta lo spread per trade;
C  l'atlante: il netto di ogni cella scende di un passo in pips (4);
D  la confidenza: la soglia della barra usa il Close della barra del segnale;
   due segnali con la stessa media e prezzi diversi (5);
E  i costi della vetrina: exchange con lo spread per trade, broker com'era (7);
   il money management non conta lo spread due volte (6); il riepilogo (8).

Come si lancia (da terminale, dalla cartella del progetto):

    python test_spread_per_trade.py

Non serve la rete. Alla fine stampa «RISULTATO: N/N test superati».
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import warnings

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")

from engine import confidenza as CF
from engine import exchange as X
from engine import motore_veloce as mv
from engine import registry as reg
from engine.metriche import bp_per_trade, costo_pips_per_trade, pips_per_trade

QUI = os.path.dirname(os.path.abspath(__file__))
DATI = os.path.join(QUI, "dati")


def muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def dati_finti(rng, n, prezzo=100.0):
    """Un random walk 24/7 con salti all'apertura (per stop e target)."""
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    ritorni = rng.normal(0, 0.004, n) + np.where(rng.random(n) < 0.05, rng.normal(0, 0.03, n), 0)
    chiusura = prezzo * np.exp(np.cumsum(ritorni))
    apertura = np.r_[prezzo, chiusura[:-1]] * np.exp(np.where(rng.random(n) < 0.1, rng.normal(0, 0.02, n), 0))
    alto = np.maximum(apertura, chiusura) * (1 + np.abs(rng.normal(0, 0.003, n)))
    basso = np.minimum(apertura, chiusura) * (1 - np.abs(rng.normal(0, 0.003, n)))
    return pd.DataFrame({"Open": apertura, "High": alto, "Low": basso, "Close": chiusura,
                         "Volume": 1.0}, index=idx)


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def errore(f, tipo=Exception, testo=""):
        try:
            muto(f)
        except tipo as e:
            return testo in str(e)
        return False

    # ---------------------------------------------------------------- A --
    print("\nA · Un trade a mano (docs/71 §4 punto 1)")
    tr = pd.DataFrame({"Size": [1.0, 1.0, -1.0], "EntryPrice": [100.0, 200.0, 200.0],
                       "ExitPrice": [101.0, 202.0, 198.0], "EntryBar": [1, 5, 9], "ExitBar": [3, 7, 11],
                       "CostoExtraPips": [0.0, 0.0, 0.0]})
    con = X.aggiungi_spread_passo(tr, 1.0)
    lordi, netti = pips_per_trade(con, 0.01, 0.0)
    _, netti0 = pips_per_trade(tr, 0.01, 0.0)
    _, bp1 = bp_per_trade(con, 0.01, 0.0)
    _, bp0 = bp_per_trade(tr, 0.01, 0.0)
    check("A1. un passo (0,01 con pip 0,01) = 1 pip per trade, long e short",
          np.allclose(con["CostoExtraPips"], 1.0) and np.allclose(netti0 - netti, 1.0))
    check("A2. in bp: 1 bp all'Open 100, 0,5 bp all'Open 200",
          np.allclose((bp0 - bp1).to_numpy(), [1.0, 0.5, 0.5]))
    check("A3. si somma al CostoExtraPips che c'e' gia' (rollover del broker)",
          np.allclose(X.aggiungi_spread_passo(tr.assign(CostoExtraPips=[0.5, 0.0, 2.0]), 1.0)["CostoExtraPips"],
                      [1.5, 1.0, 3.0]))
    check("A4. None: i trade tornano come sono (stesso oggetto)", X.aggiungi_spread_passo(tr, None) is tr)
    check("A5. spread_bp: passo / prezzo x 10.000",
          np.allclose(X.spread_bp(1.0, 0.0001, [0.2, 2.5]), [5.0, 0.4]))

    # ---------------------------------------------------------------- B --
    print("\nB · I due motori: spread zero e un passo in CostoExtraPips (docs/71 §4 punti 2-3)")
    from engine.due_meta import due_meta
    from engine.exit_search_bt import run_exit_search_bt
    from engine.filter_search_bt import run_filter_search_bt
    rng = np.random.default_rng(7)
    df = dati_finti(rng, 20_000)
    nb = len(df)
    sl, ss = rng.random(nb) < 0.01, rng.random(nb) < 0.01
    xl, xs = rng.random(nb) < 0.02, rng.random(nb) < 0.02
    f1 = rng.random(nb) < 0.6

    def su(a):
        s_ = pd.Series(a, index=df.index)
        return lambda x: s_.reindex(x.index).fillna(False).astype(bool)

    reg.clear_registry()
    reg.register_entry("SP_T_LONG", 1)(su(sl))
    reg.register_entry("SP_T_SHORT", -1)(su(ss))
    reg.register_exit("SP_X_LONG", 1, pair="SP_X")(su(xl))
    reg.register_exit("SP_X_SHORT", -1, pair="SP_X")(su(xs))
    reg.register_filter("SP_F1", 0)(su(f1))
    PIP, PASSO, SPREAD = 0.01, 1.0, 0.0002          # un passo = 1 pip; lo spread «vecchio» in frazione
    base = dict(commission=0.0005, cash=float(df["Close"].max()) * 100, pip_size=PIP)
    comuni = dict(n_barre=12, perc_sl=90.0, perc_tp=95.0, finestra=200, lag=1, quarantena=False,
                  inverti_su_opposto=True, verbose=False, unita="bp")
    D = dict(spread=0.0, spread_passo_pips=PASSO, **base)
    vecchio = mv.comportamento_vecchio()     # l'oracolo: «veloce» identico a «bt»
    vecchio.__enter__()
    try:
        es = {m_: run_exit_search_bt(df, entry_cols_long=["SP_T_LONG"], entry_cols_short=["SP_T_SHORT"],
                                     exit_rule_pairs=[None, "SP_X"], motore=m_, **comuni, **D)
              for m_ in ("bt", "veloce")}
        es_old = run_exit_search_bt(df, entry_cols_long=["SP_T_LONG"], entry_cols_short=["SP_T_SHORT"],
                                    exit_rule_pairs=[None, "SP_X"], motore="veloce", spread=SPREAD, **comuni, **base)
        fs = {m_: run_filter_search_bt(df, entry_long="SP_T_LONG", entry_short="SP_T_SHORT", exit_rule_pair="SP_X",
                                       filtri=["SP_F1"], n_boot=300, motore=m_, **comuni, **D)
              for m_ in ("bt", "veloce")}
    finally:
        vecchio.__exit__(None, None, None)
    combo = es["bt"].risultati["combinazione"].tolist()
    check("B1. run_exit_search_bt: «bt» e «veloce» danno la stessa tabella",
          es["bt"].risultati.equals(es["veloce"].risultati))
    check("B2. ... e gli stessi trade, colonna CostoExtraPips compresa",
          all(es["bt"].trades(c_).equals(es["veloce"].trades(c_)) for c_ in combo))
    check("B2b. run_filter_search_bt: stessa tabella e stessi trade nei due motori",
          fs["bt"].risultati.equals(fs["veloce"].risultati)
          and all(fs["bt"].trades(f_).equals(fs["veloce"].trades(f_)) for f_ in fs["bt"].risultati["filtro"]))
    t_d = es["veloce"].trades(combo[-1])
    check("B3. ogni trade paga un passo in CostoExtraPips; il fill e' l'Open della barra d'ingresso",
          np.allclose(t_d["CostoExtraPips"], PASSO)
          and np.allclose(t_d["EntryPrice"], df["Open"].to_numpy()[t_d["EntryBar"].to_numpy(int)]),
          f"{len(t_d)} trade")
    check("B3b. il risultato ricorda lo spread per trade; due_meta lo riprende da fs",
          es["veloce"].spread_passo_pips == PASSO and fs["veloce"].spread_passo_pips == PASSO)
    t_o = es_old.trades(combo[-1])
    # stessi trade per barra d'ingresso e lato (la Size cambia con il prezzo di fill)
    m = (t_d.assign(lato=np.sign(t_d["Size"])).merge(t_o.assign(lato=np.sign(t_o["Size"])),
                                                     on=["EntryBar", "lato"], suffixes=("_d", "_o")))
    stessa = m[np.isclose(m["ExitPrice_d"], m["ExitPrice_o"], rtol=0, atol=1e-12) & (m["ExitBar_d"] == m["ExitBar_o"])]
    cambiate = len(m) - len(stessa)
    segno = stessa["lato"].to_numpy(dtype=float)
    entrata = df["Open"].to_numpy()[stessa["EntryBar"].to_numpy(int)]
    lordi_d = (stessa["ExitPrice_d"] - stessa["EntryPrice_d"]) / PIP * segno
    lordi_o = (stessa["ExitPrice_o"] - stessa["EntryPrice_o"]) / PIP * segno
    comm_d = base["commission"] * (stessa["EntryPrice_d"] + stessa["ExitPrice_d"]) / PIP
    comm_o = base["commission"] * (stessa["EntryPrice_o"] + stessa["ExitPrice_o"]) / PIP
    diff = (lordi_d - comm_d - PASSO) - (lordi_o - comm_o)
    attesa = entrata * SPREAD / PIP - base["commission"] * (stessa["EntryPrice_d"] - stessa["EntryPrice_o"]) / PIP - PASSO
    check("B4. la somma torna sui trade con la stessa uscita: netti_D - netti_oggi = spread nel prezzo - un passo "
          "(+ il pezzetto di commissione)",
          len(stessa) > 0 and np.allclose(diff.to_numpy(), attesa.to_numpy(), rtol=0, atol=1e-9),
          f"{len(m)} trade abbinati su {len(t_d)}: {len(stessa)} con la stessa uscita, {cambiate} con l'uscita "
          "cambiata (stop o target)")
    diverse = m.loc[~m.index.isin(stessa.index)]

    def al_livello(x, livello):
        return np.isclose(diverse[f"ExitPrice_{x}"], diverse[f"{livello}_{x}"], rtol=1e-12, atol=0)
    da_livello = al_livello("d", "SL") | al_livello("d", "TP") | al_livello("o", "SL") | al_livello("o", "TP")
    check("B4b. i trade con l'uscita cambiata sono chiusi da stop o target in almeno uno dei due giri "
          "(il livello si sposta di circa un passo)", cambiate > 0 and bool(np.all(da_livello)),
          f"{int(np.sum(da_livello))}/{cambiate}")
    with contextlib.redirect_stdout(io.StringIO()):
        dm = due_meta(df, fs["veloce"], [None, "SP_F1"], perc_sl=90.0, perc_tp=95.0, finestra=200, lag=1,
                      quarantena=False, verbose=False, **{k: D[k] for k in ("spread", "commission", "cash")})
    tr_m1 = dm.metà1.trades(dm.metà1.risultati["filtro"].iloc[0])
    check("B5. due_meta: le due meta' pagano anche loro un passo per trade",
          len(tr_m1) > 0 and np.allclose(tr_m1["CostoExtraPips"], PASSO))
    _, n_old = pips_per_trade(es_old.trades(combo[-1]), PIP, base["commission"])
    check("B6. senza spread_passo_pips tutto come prima: CostoExtraPips a zero, spread nel prezzo",
          es_old.spread_passo_pips is None and np.allclose(t_o["CostoExtraPips"], 0.0)
          and not np.allclose(t_o["EntryPrice"], df["Open"].to_numpy()[t_o["EntryBar"].to_numpy(int)]))

    # ---------------------------------------------------------------- C --
    print("\nC · L'atlante (docs/71 §4 punto 4)")
    from engine.atlante import atlante
    from engine.indicatori import aggiungi_indicatori
    from engine.quarantena import imposta_rollover
    imposta_rollover(None)
    with contextlib.redirect_stdout(io.StringIO()):
        dfi = aggiungi_indicatori(dati_finti(np.random.default_rng(3), 20_000))
    seg = pd.Series(np.random.default_rng(4).random(len(dfi)) < 0.02, index=dfi.index)
    reg.register_entry("SP_ATL", 1)(lambda x: seg.reindex(x.index).fillna(False))
    kw_a = dict(nomi=["SP_ATL"], quarantena=False, min_eventi=10)
    with contextlib.redirect_stdout(io.StringIO()):
        a0 = atlante(dfi, 8, PIP, costi={"commission": 0.0005, "spread": 0.0}, unita="pips", **kw_a)
        a1 = atlante(dfi, 8, PIP, costi={"commission": 0.0005, "spread": 0.0, "spread_passo_pips": PASSO},
                     unita="pips", **kw_a)
    altre = [c_ for c_ in a0.select_dtypes("number").columns if c_ != "netto_pips"]
    check("C1. il netto in pips di ogni cella scende di un passo, il resto (scarto, t, due meta') non cambia",
          np.allclose((a0["netto_pips"] - a1["netto_pips"]).dropna(), PASSO)
          and a0[altre].equals(a1[altre]), f"{len(a0)} celle")

    # ---------------------------------------------------------------- D --
    print("\nD · La confidenza: la soglia della barra del segnale (docs/71 §3, §4 punto 5)")
    idx = pd.date_range("2024-01-01", periods=4, freq="15min", tz="UTC")
    close = pd.Series([100.0, 10_000.0, 100.0, 10_000.0], index=idx)
    costi = {"commission": 0.0005, "spread": 0.0, "spread_passo_pips": PASSO, "pip_size": PIP}
    costo = CF.costo_andata_ritorno_bp(costi, close)
    check("D1. costo per barra = 10 bp di commissione + un passo al Close della barra",
          np.allclose(costo.to_numpy(), [11.0, 10.01, 11.0, 10.01]) and costo.index.equals(idx))
    check("D2. senza il prezzo si ferma (il costo dipende dal prezzo)",
          errore(lambda: CF.costo_andata_ritorno_bp(costi), ValueError, "dipende dal prezzo"))
    check("D3. senza spread per trade: il numero solo, come prima",
          CF.costo_andata_ritorno_bp({"commission": 0.0005, "spread": 0.0001}) == (0.001 + 0.0001) * 10_000)
    conf = pd.DataFrame({"bp_medi": [15.0, 15.0, np.nan, 20.0]}, index=idx)
    nomi = CF.registra_filtro_confidenza([1.4], conf_long=conf, metrica="bp_medi", costo_bp=costo,
                                         prefisso="SPTEST")
    maschera = (CF._funzione_filtro(nomi[0]))(pd.DataFrame(index=idx))
    check("D4. stessa media (15 bp), prezzi diversi: a 100 la soglia 1,4C vale 15,4 bp (fuori), a 10.000 "
          "14,01 bp (dentro); senza confidenza: fuori",
          maschera.tolist() == [False, True, False, True])
    tab = CF.soglie_confidenza(nomi)
    check("D5. la tabella delle soglie dice mediana, minimo e massimo in bp",
          np.isclose(tab["soglia_da"].iloc[0], 14.014) and np.isclose(tab["soglia_a"].iloc[0], 15.4))
    check("D6. la soglia di una barra usa il Close di QUELLA barra (nessun lookahead): cambiare il Close "
          "dopo non la tocca",
          np.allclose(CF.costo_andata_ritorno_bp(costi, close.iloc[:2]).to_numpy(), costo.iloc[:2].to_numpy()))

    # ---------------------------------------------------------------- E --
    print("\nE · I costi della vetrina, il money management, il riepilogo (docs/71 §4 punti 6-8)")
    import engine.vetrina as v
    sint = dati_finti(np.random.default_rng(9), 3000, prezzo=30_000.0)
    c_ex, sp_ex = v.costi_storico("BINANCE_PERP_BTCUSDT", sint)
    check("E1. exchange: spread zero nel prezzo, un passo per trade (BTC perp 0,1 pips), commissione 0,05%",
          c_ex["spread"] == 0.0 and np.isclose(c_ex["spread_passo_pips"], 0.1) and c_ex["commission"] == 0.0005
          and np.isclose(sp_ex["normale"], 0.1))
    c_xrp, _ = v.costi_storico("BINANCE_PERP_XRPUSDT", sint / 30_000.0)
    check("E1b. XRP: un passo = 1 pip", np.isclose(c_xrp["spread_passo_pips"], 1.0))
    eur = os.path.join(DATI, "EURUSD_M15.csv")
    if os.path.exists(eur):
        df_eur = muto(v.carica_storico, "EURUSD", DATI, "M15")
        c_eur, sp_eur = v.costi_storico("EURUSD", df_eur)
        check("E2. broker: come prima (spread di listino nel prezzo, nessuno spread per trade)",
              "spread_passo_pips" not in c_eur and c_eur["spread"] > 0 and sp_eur["normale"] == 0.8)
        imposta_rollover(None)
    else:
        print("  [SALTATO] E2. dati/EURUSD_M15.csv non c'e'")
    preso = {}
    import engine.mm_adattatore as mma
    originale = mma.tabella_trade

    def spia(trades, df_, **kw):
        preso.setdefault("spread_pips", []).append(kw.get("spread_pips"))
        raise RuntimeError("fermo qui")
    try:
        mma.tabella_trade = spia
        for simbolo in ("BINANCE_PERP_BTCUSDT", "EURUSD"):
            try:
                muto(v.money_management_trade, simbolo, tr, sint, None, None, pip=0.1, spread_pips=0.7)
            except RuntimeError:
                pass
    finally:
        mma.tabella_trade = originale
    check("E3. money management: sui symbol da exchange lo spread non si aggiunge (e' gia' nei netti), sul "
          "broker si'", preso.get("spread_pips") == [0.0, 0.7], str(preso.get("spread_pips")))
    with tempfile.TemporaryDirectory() as tmp:
        idx2 = pd.date_range("2024-01-01", periods=96 * 120, freq="15min", tz="UTC")
        g = np.random.default_rng(5)
        cl = 30_000 * np.exp(np.cumsum(g.normal(0, 0.002, len(idx2))))
        op = np.r_[30_000.0, cl[:-1]]
        d2 = pd.DataFrame({"Open": op, "High": np.maximum(op, cl) * 1.001, "Low": np.minimum(op, cl) * 0.999,
                           "Close": cl, "Volume": g.uniform(1, 9, len(idx2))}, index=idx2.rename("Date"))
        X.salva_csv(d2, os.path.join(tmp, "BINANCE_PERP_BTCUSDT_M15.csv"))
        orari = pd.date_range(idx2[0].floor("8h"), idx2[-1].ceil("8h"), freq="8h")
        X.salva_funding(X.con_intervalli(pd.DataFrame({"tasso": 0.0001}, index=orari.rename("Date"))),
                        X.file_funding("BINANCE_PERP_BTCUSDT", tmp))
        s = muto(v.prepara, "BINANCE_PERP_BTCUSDT", H=8, cartella=tmp)
        testo = s.tabelle["riepilogo"].set_index("")[" "]["Costo per trade in bp"]
        lo = float(np.min(0.1 / s.df_is["Close"]) * 1e4)
        check("E4. riepilogo: lo spread di un passo al prezzo d'ingresso, da ... a ... bp nell'in-sample",
              "al prezzo d'ingresso di ogni trade" in testo and v._fmt(lo, 2) in testo, testo)
        check("E5. prepara: s.costi con lo spread per trade arriva ai motori",
              s.costi["spread"] == 0.0 and np.isclose(s.costi["spread_passo_pips"], 0.1))

    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
