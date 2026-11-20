"""
Suite di collaudo della fabbrica su più monete (docs/82 §14.7, 20/11/2026).

Si lancia da terminale, dalla cartella del progetto:

    python test_fabbrica_monete.py

Solo dati sintetici (engine/fabbrica/sintetici.py), in cartelle temporanee: non servono i file in dati/, MetaTrader 5 o
internet. Stampa una riga per collaudo e alla fine «RISULTATO: n/n test superati». Dura qualche minuto.

I collaudi di §14.7:
- l'orologio comune: una moneta più giovane resta allineata per ora; una copia con barre tolte ha lo stesso orologio;
- con una moneta: la rosa = la rosa del Lab, al bit; il t del valutatore = giudizio.t_stat quando nessun trade è a meno di
  H barre da un altro; il money management senza trade sovrapposti = quello di prima, al bit;
- due copie della stessa moneta = lo stesso scarto e lo stesso t di una sola (rosa e valutatore); due monete
  indipendenti con lo stesso vantaggio piantato = t circa 1,4 volte; prezzi × 10 = gli stessi numeri in ATR;
- money management: due trade aperti insieme su due monete, il secondo prende i lotti dal capitale senza il primo e la
  leva somma le due posizioni; il Monte Carlo tiene insieme i trade dello stesso giorno;
- per ogni moneta i trade del valutatore = MotoreVeloce.run con i suoi costi e il suo funding; una strategia = una riga
  nel conto; un blocco degenere su una moneta esce per tutte; nessuna barra di cassaforte letta prima della cella 5; la
  cella 2 con la rosa salvata = la rosa rifatta; fermata e ripresa = corsa unica; la cella 6 su due monete.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import math
import os
import sys
import tempfile
import time
import warnings

import matplotlib
import numpy as np
import pandas as pd

from engine import money_management as mm
from engine import montecarlo as mc
from engine import registry as reg
from engine.fabbrica import registro, sintetici
from engine.fabbrica import cassaforte as cas
from engine.fabbrica import sessione as ses
from engine.fabbrica.blocchi import blocchi_da_config, trigger_generati
from engine.fabbrica.cache import Cache, MemoriaComune
from engine.fabbrica.config import cartella_asset, config_standard, nome_lista
from engine.fabbrica.dati import Confini, carica_pezzi, imposta_mercato_crypto, orologio
from engine.fabbrica.generatore import (ControlloDegenerazione, ControlloLista, Teoria, _registro_isolato,
                                        segnali_trigger, togli_degeneri)
from engine.fabbrica.ricerca import FILE_ROSA, lancia, prepara
from engine.fabbrica.rosa_lista import base_moneta, misura_rosa
from engine.fabbrica.valutatore import (Costi, Strategia, Valutatore, ValutatoreLista, misure_lista, t_sovrapposti,
                                        trade_completi)
from engine.giudizio import t_stat
from engine.indicatori import aggiungi_indicatori, atr_giornaliero_chiuso
from engine.metriche import bp_per_trade
from engine.rosa import rosa_orizzonti_entry
from engine.stagionalita import barre_settimana

warnings.simplefilter("ignore")
matplotlib.use("Agg")

BTC, ETH, SOL = "BINANCE_PERP_BTCUSDT", "BINANCE_PERP_ETHUSDT", "BINANCE_PERP_SOLUSDT"
DATA = "20260101"
CONFINI = {"inizio": "2024-01-01 00:00", "ricerca_ore": 4000, "selezione_ore": 1000, "cassaforte_ore": 500}
REGOLE = {"orizzonti_barre": [4, 16, 32], "q": 0.2, "soglia_famiglia": 0.6, "rho_max": 0.3, "min_eventi": 200}
COLONNE_ROSA = ["candidato", "direction", "eventi", "scarto_atr", "t_netto", "p", "bh", "due_meta", "candidata",
                "famiglia", "nella_rosa", "rho_max", "perche", "incertezza_blocchi"]
ESITI: list = []


def check(nome: str, ok, dettaglio: str = "") -> None:
    ESITI.append(bool(ok))
    print(f"[{'OK ' if ok else 'KO '}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""), flush=True)


def _zitto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def _leggi(p):
    with open(p, "rb") as f:
        return f.read()


# ------------------------------------------------------------------ la rosa su una lista fatta a mano
def _rosa_lista(dfs: dict, blocchi, lati=(1, -1), regole=REGOLE):
    """La rosa di rosa_lista su {nome: df con gli indicatori}, con i blocchi dati, come la prepara ricerca.prepara."""
    caches = {m: Cache(df, 2000) for m, df in dfs.items()}
    oro = orologio({m: df.index for m, df in dfs.items()}, 15)
    n_or = int(max(int(o[-1]) for o in oro.values())) + 1
    basi = {m: base_moneta(df, 1.0, regole["orizzonti_barre"], oro[m], n_or // 2) for m, df in dfs.items()}
    segnali = {m: segnali_trigger(blocchi, caches[m], list(lati)) for m in dfs}
    da = {}
    from engine.fabbrica.generatore import _gruppo_segnale
    for lato in lati:
        for b in blocchi:
            if b.tipo == "trigger" and lato in b.lati:
                da[f"{b.nome}_{'long' if lato == 1 else 'short'}"] = (_gruppo_segnale(b, lato), lato)
    return misura_rosa(basi, segnali, da, regole, n_or, barre_settimana(next(iter(dfs.values())).index), 1)


def _riga(rose, H, nome):
    t = rose[H].set_index("candidato")
    return t.loc[nome] if nome in t.index else None


def collaudi_orologio():
    print("\nL'orologio comune (docs/82 §14.2)")
    btc = sintetici.mercato(3000, seme=1, inizio="2024-01-01")
    sol = sintetici.mercato(2000, seme=2, inizio="2024-01-11 10:00")            # più giovane di dieci giorni e 10 ore
    o = orologio({BTC: btc.index, SOL: sol.index}, 15)
    in_btc = pd.Index(btc.index).get_indexer(sol.index[:500])
    check("O1. una moneta più giovane (SOL dal 11/01 10:00): la sua prima barra ha il numero di quell'ora sull'orologio di "
          "BTC; ogni barra comune ha lo stesso numero sulle due monete", o[SOL][0] == 10 * 96 + 40
          and np.array_equal(o[SOL][:500], o[BTC][in_btc]), f"prima barra di SOL: {o[SOL][0]}")
    tolte = np.sort(np.random.default_rng(3).choice(np.arange(1, 3000), 300, replace=False))
    bucata = btc.drop(btc.index[tolte])
    ob = orologio({"copia": bucata.index, BTC: btc.index}, 15)
    check("O2. una copia di BTC con 300 barre tolte: le barre rimaste hanno lo stesso numero di prima (l'orologio viene "
          "dall'ora, non dalla posizione)", np.array_equal(ob["copia"], ob[BTC][np.setdiff1d(np.arange(3000), tolte)])
          and np.array_equal(ob[BTC], np.arange(3000)))
    try:
        orologio({BTC: btc.index, "storta": btc.index + pd.Timedelta(minutes=7)}, 15)
        storta = False
    except ValueError:
        storta = True
    check("O3. una barra fuori dalla griglia del timeframe: errore", storta)


def collaudi_rosa():
    print("\nLa rosa su più monete (docs/82 §14.2 e §14.7)")
    imposta_mercato_crypto()
    G = "G0045_P50_SU"
    gen = list(trigger_generati())[:60]
    cfg = {"timeframe": "M15", "blocchi": {**{n: {} for n in ("E1", "E3", "E5", "E12", "E36", "DONCHIAN")},
                                           **{g: {} for g in [G, *gen]}}}
    blocchi = blocchi_da_config(cfg)
    grezzo = sintetici.mercato_con_generato(G, n=26_000, seme=1)
    a = aggiungi_indicatori(grezzo)
    # 1. una moneta = la rosa del Lab, al bit
    t0 = time.perf_counter()
    nuova = _rosa_lista({BTC: a}, blocchi)
    cache = Cache(a, 2000)
    nomi, cond = [], {}
    for lato in (1, -1):
        for b in blocchi:
            if b.tipo == "trigger" and lato in b.lati:
                n = f"{b.nome}_{'long' if lato == 1 else 'short'}"
                nomi.append(n)
                cond[n] = (b.condizione(cache, lato), lato)
    with _registro_isolato():
        for n, (f, lato) in cond.items():
            reg.register_entry(n, direction=lato)(f)
        lab, _ = rosa_orizzonti_entry(a, REGOLE["orizzonti_barre"], 1.0, nomi=nomi, q=0.2, soglia_famiglia=0.6,
                                      rho_max=0.3, min_eventi=200, fuso="UTC", unita="atr",
                                      atr=atr_giornaliero_chiuso(a), processi=1)
    uguali = all(lab[H][COLONNE_ROSA].reset_index(drop=True).equals(nuova[H][COLONNE_ROSA].reset_index(drop=True))
                 for H in (4, 16, 32))
    check("R1. una moneta: la rosa della lista è la rosa del Lab (unità ATR), al bit, ai tre orizzonti, colonna per colonna",
          uguali and sum(len(lab[H]) for H in lab) > 100, f"{sum(len(lab[H]) for H in lab)} righe, "
                                                          f"{time.perf_counter() - t0:.0f} s")
    # 2. due copie della stessa moneta = lo stesso scarto e lo stesso t
    doppia = _rosa_lista({BTC: a, "copia": a.copy()}, blocchi)
    diff, eventi = 0.0, True
    for H in (4, 16, 32):                 # i trigger misurati con una moneta (con due copie ne passano di più i 200)
        una, due = nuova[H].set_index("candidato"), doppia[H].set_index("candidato")
        due = due.loc[una.index]
        diff = max(diff, float(np.nanmax(np.abs(una[["scarto_atr", "t_netto"]].to_numpy()
                                                - due[["scarto_atr", "t_netto"]].to_numpy()))))
        eventi &= bool((due["eventi"] == 2 * una["eventi"]).all())
    check("R2. due copie della stessa moneta: gli eventi raddoppiano, scarto e t restano quelli di una sola (due eventi "
          "sulla stessa barra contano per intero)", diff < 1e-9 and eventi, f"differenza massima {diff:.1e}")
    # 3. prezzi × 10 = gli stessi numeri in ATR
    dieci = grezzo.copy()
    dieci[["Open", "High", "Low", "Close"]] *= 10.0
    donchian = [x for x in blocchi if x.nome == "DONCHIAN"]
    per_dieci = _rosa_lista({BTC: aggiungi_indicatori(dieci)}, donchian)
    base = _rosa_lista({BTC: a}, donchian)
    d10 = max(float(np.nanmax(np.abs(per_dieci[H][["scarto_atr", "t_netto"]].to_numpy()
                                     - base[H][["scarto_atr", "t_netto"]].to_numpy()))) for H in (4, 16, 32))
    check("R3. prezzi × 10: gli stessi numeri in ATR (scarto e t)", d10 < 1e-9, f"differenza massima {d10:.1e}")
    # 4. due monete indipendenti con lo stesso vantaggio piantato: t circa 1,4 volte
    b = aggiungi_indicatori(sintetici.mercato_con_generato(G, n=26_000, seme=7))
    piantato = [x for x in blocchi if x.nome == G]
    solo_a = _rosa_lista({BTC: a}, piantato, lati=(1,))
    solo_b = _rosa_lista({ETH: b}, piantato, lati=(1,))
    insieme = _rosa_lista({BTC: a, ETH: b}, piantato, lati=(1,))
    rapporti = []
    for H in (4, 16):
        ta, tb, tt = (float(_riga(r, H, f"{G}_long")["t_netto"]) for r in (solo_a, solo_b, insieme))
        rapporti.append(tt / ((ta + tb) / 2))
    check("R4. due monete indipendenti con lo stesso vantaggio piantato: il t della lista è circa 1,4 volte quello di "
          "una moneta (la radice di 2)", all(1.2 <= x <= 1.65 for x in rapporti),
          ", ".join(f"{x:.2f}" for x in rapporti))
    # 5. una moneta più giovane: le sue barre entrano dove ci sono, l'orologio resta allineato
    giovane = b.iloc[5000:]
    gio = _rosa_lista({BTC: a, ETH: giovane}, piantato, lati=(1,))
    check("R5. una moneta più giovane nella lista: i suoi eventi si sommano a quelli dell'altra, nessun errore",
          int(_riga(gio, 16, f"{G}_long")["eventi"]) < int(_riga(insieme, 16, f"{G}_long")["eventi"])
          and int(_riga(gio, 16, f"{G}_long")["eventi"]) > int(_riga(solo_a, 16, f"{G}_long")["eventi"]))


def collaudi_valutatore():
    print("\nIl valutatore su più monete (docs/82 §14.2 e §14.7)")
    x = np.random.default_rng(4).normal(0.05, 1.0, 300)
    lontani = np.arange(300) * 50
    check("V1. nessun trade a meno di H barre da un altro: il t è giudizio.t_stat, al bit",
          t_sovrapposti(x, lontani, 16, 672) == t_stat(x) and misure_lista(x, x, lontani, 16, 672).t == t_stat(x))
    vicini = np.sort(np.random.default_rng(5).integers(0, 3000, 300))
    t_v = t_sovrapposti(x, vicini, 16, 672)
    check("V2. trade vicini: il t cambia (le coppie a meno di H barre contano per intero)", t_v != t_stat(x)
          and np.isfinite(t_v), f"t_stat {t_stat(x):.3f}, con i vicini {t_v:.3f}")
    xx, pp = np.repeat(x, 2), np.repeat(lontani, 2)
    t2 = t_sovrapposti(xx, pp, 16, 672)
    check("V3. due copie della stessa moneta (gli stessi trade sulle stesse barre): lo stesso t di una sola, a meno della "
          "correzione n/(n−1)", abs(t2 / t_stat(x) - 1) < 2 / len(x), f"{t2:.4f} contro {t_stat(x):.4f}")

    with tempfile.TemporaryDirectory() as d:
        imposta_mercato_crypto()
        dfs, costi = {}, {}
        for m, seme, prezzo in ((BTC, 5, 30_000.0), (ETH, 6, 2_000.0)):
            df = sintetici.mercato_piantato(22_000, seme=seme, minuti=15, inizio="2024-01-01", prezzo=prezzo)
            sintetici.scrivi_storico(d, m, "M15", df)
            sintetici.scrivi_funding(d, m, df, seme=seme)
        pezzi = carica_pezzi([BTC, ETH], "M15", Confini.da_config(CONFINI), d)
        cfg = {"timeframe": "M15", "blocchi": {"DONCHIAN": {"canale_barre": [40]}, "RSI_RIENTRO": {}, "ADX": {},
                                               "X0": {}, "X3": {}}}
        blocchi = blocchi_da_config(cfg)
        comune = MemoriaComune(1500)
        caches = {m: Cache(aggiungi_indicatori(pezzi[m].ricerca), 1500, comune) for m in (BTC, ETH)}
        cst = {m: Costi(caches[m].df, pezzi[m].costi("ricerca")) for m in (BTC, ETH)}
        vl = ValutatoreLista(blocchi, caches, cst)
        prove, uguali, n_trade, funding = [], [], 0, 0.0
        for lato in (1, -1):
            for uscita, durata, stop, target in (("X0", 12, 90, None), ("X3", 32, 80, 90)):
                prove.append(Strategia.da_teoria(Teoria(lato, "DONCHIAN", (), uscita), {
                    "DONCHIAN": {"canale_barre": 40}, uscita: {"durata_barre": durata, "perc_stop": stop, "target": target}}))
            prove.append(Strategia.da_teoria(Teoria(lato, "RSI_RIENTRO", ("ADX",), "X0"), {
                "RSI_RIENTRO": {"periodo_barre": 14, "soglia": 30}, "ADX": {"periodo_barre": 14, "soglia": 25},
                "X0": {"durata_barre": 16, "perc_stop": 90, "target": 90}}))
        for s in prove:
            for m in (BTC, ETH):
                v = vl.per_moneta[m]
                t = trade_completi(s, v, pezzi[m].costi("ricerca"))
                uguali.append(np.allclose(v.bp(s), t["BpNetti"].to_numpy(), atol=1e-9, rtol=0))
                n_trade += len(t)
                funding += float(t["FundingPips"].abs().sum()) if "FundingPips" in t else 0.0
        check(f"V4. per ogni moneta i trade del valutatore = MotoreVeloce.run con i suoi costi e il suo funding "
              f"({len(prove)} strategie × 2 monete)", all(uguali) and n_trade > 200 and funding > 0, f"{n_trade} trade")
        piantata = prove[0]
        solo = {m: ValutatoreLista(blocchi, {m: caches[m]}, {m: cst[m]}).valuta(piantata) for m in (BTC, ETH)}
        insieme = vl.valuta(piantata)
        rapporto = insieme.t / ((solo[BTC].t + solo[ETH].t) / 2)
        check("V5. due monete indipendenti con lo stesso vantaggio piantato (Donchian 40, esce dopo 12): il t della lista "
              "è circa 1,4 volte quello di una moneta; i trade si sommano", 1.2 <= rapporto <= 1.65
              and insieme.trade == solo[BTC].trade + solo[ETH].trade,
              f"t {solo[BTC].t:.2f} e {solo[ETH].t:.2f} da sole, {insieme.t:.2f} insieme ({rapporto:.2f})")
        per = vl.per_trade(piantata)
        tutte = np.sort(np.concatenate([per[m]["pos"] for m in (BTC, ETH)]))
        check("V6. i trade delle due monete stanno sull'orologio comune, in ordine d'ingresso", len(tutte) == insieme.trade
              and (np.diff(tutte) >= 0).all())
        # prezzi × 10 sullo spot, senza spread di un passo: gli stessi numeri in ATR
        spot = "BYBIT_SPOT_ETHUSDT"
        base = aggiungi_indicatori(sintetici.mercato_piantato(8000, seme=8, minuti=15, inizio="2024-01-01", prezzo=2000.0))
        dieci = base.copy()
        dieci[["Open", "High", "Low", "Close"]] *= 10.0
        c = {"spread": 0.0, "commission": 0.001, "pip_size": 0.1, "spread_passo_pips": None, "funding": None}
        mis = [ValutatoreLista(blocchi, {spot: Cache(df, 500)}, {spot: Costi(df, c)}).valuta(piantata)
               for df in (base, dieci)]
        check("V7. prezzi × 10: gli stessi numeri in ATR (EV, t, drawdown), i bp uguali",
              abs(mis[0].ev_atr - mis[1].ev_atr) < 1e-12 and abs(mis[0].t - mis[1].t) < 1e-9
              and abs(mis[0].dd_atr - mis[1].dd_atr) < 1e-9 and mis[0].trade == mis[1].trade > 0,
              f"EV {mis[0].ev_atr:.5f} e {mis[1].ev_atr:.5f} ATR")
        # un blocco degenere su una moneta esce per tutte
        rimaste, tolte = togli_degeneri(blocchi_da_config({"timeframe": "M15", "blocchi": {
            "DONCHIAN": {"canale_barre": [40, 30000]}}}), {BTC: caches[BTC], ETH: caches[ETH]}, [1, -1])
        check("V8. una combinazione degenere su una moneta esce per tutte (Donchian di 30.000 barre non scatta mai): una "
              "riga per lato con la moneta", rimaste[("DONCHIAN", 1)] == ({"canale_barre": 40},)
              and rimaste[("DONCHIAN", -1)] == ({"canale_barre": 40},)
              and {(t["lato"], t["moneta"]) for t in tolte} == {("long", BTC), ("short", BTC)}, str(tolte))


def collaudi_mm():
    print("\nMoney management e Monte Carlo su più monete (docs/82 §14.4)")
    r = np.random.default_rng(0)
    n = 300
    ingresso = pd.date_range("2024-01-01 01:00", periods=n, freq="D", tz="UTC")
    t = pd.DataFrame({"pips_netti": r.normal(5, 40, n), "rischio_pips": r.uniform(20, 60, n), "valore_entrata": 1.0,
                      "valore_uscita": r.uniform(0.9, 1.1, n), "nozionale_lotto": r.uniform(800, 1200, n),
                      "entrata": ingresso, "uscita": ingresso + pd.Timedelta(hours=5)})
    lim = {"minimo": 0.01, "passo": 0.01, "massimo": 50, "leva": 2}
    t2 = t.assign(ingresso=ingresso, giorno=ingresso.floor("D"), lotto_minimo=0.01, lotto_passo=0.01, lotto_massimo=50.0)
    a, b = mm.montecarlo_mm(t, 1e4, [0.01, 0.03], 120, n_sim=400, limiti=lim, percorsi=True), \
        mm.montecarlo_mm(t2, 1e4, [0.01, 0.03], 120, n_sim=400, limiti=lim, percorsi=True)
    ca, fa = mm.calibra(t, 1e4, 20, 120, n_sim=300, limiti=lim)
    cb, fb = mm.calibra(t2, 1e4, 20, 120, n_sim=300, limiti=lim)
    sa, sb = mm.controlla_storia(t, 1e4, 20, 120, fa, limiti=lim), mm.controlla_storia(t2, 1e4, 20, 120, fb, limiti=lim)
    check("M1. una moneta senza trade sovrapposti, un trade al giorno: storia vera, Monte Carlo, calibrazione, storia a "
          "tratti, banda ed esposizione fissa con le colonne nuove = quelli di prima, al bit",
          mm.ripercorri(t, 1e4, 0.02, lim).equals(mm.ripercorri(t2, 1e4, 0.02, lim))
          and all(np.array_equal(a[f][k], b[f][k]) for f in a for k in a[f]) and ca.equals(cb) and fa == fb
          and sa["tabella"].equals(sb["tabella"]) and sa["f"] == sb["f"]
          and mm.banda(t, 1e4, 0.02, 80, n_sim=200, limiti=lim).equals(mm.banda(t2, 1e4, 0.02, 80, n_sim=200, limiti=lim))
          and mm.confronto_esposizione_fissa(t, 1e4, 0.02, 80, n_sim=200, limiti=lim, per_nozionale=True).equals(
              mm.confronto_esposizione_fissa(t2, 1e4, 0.02, 80, n_sim=200, limiti=lim, per_nozionale=True)))
    due = pd.DataFrame({"pips_netti": [100.0, 50.0, 10.0], "rischio_pips": [10.0] * 3, "valore_entrata": 1.0,
                        "valore_uscita": 1.0, "nozionale_lotto": [1000.0] * 3,
                        "ingresso": pd.to_datetime(["2024-01-01 01:00", "2024-01-01 02:00", "2024-01-01 06:00"], utc=True),
                        "uscita": pd.to_datetime(["2024-01-01 05:00", "2024-01-01 07:00", "2024-01-01 08:00"], utc=True),
                        "giorno": pd.to_datetime(["2024-01-01"] * 3, utc=True)})
    p1 = mm.ripercorri(due, 10_000, 0.01, {"leva": 2})
    check("M2. due trade aperti insieme su due monete: il secondo prende i lotti dal capitale senza il primo (10.000, "
          "non 11.000); il terzo, dopo la chiusura del primo, da 11.000", list(p1["capitale_prima"]) == [10_000, 10_000,
                                                                                                         11_000]
          and list(p1["lotti"]) == [10, 10, 11] and list(p1["capitale_dopo"]) == [11_000, 11_500, 11_610])
    p2 = mm.ripercorri(due, 10_000, 0.02, {"leva": 2})
    check("M3. la leva somma le posizioni aperte: con il 2% il primo trade usa tutto il tetto (20 lotti × 1.000 = 2 × "
          "10.000), il secondo scende a zero", list(p2["lotti"][:2]) == [20, 0] and p2["esito"][1] == mm.RIDOTTO_LEVA)
    g = mm.montecarlo_mm(due, 10_000, [0.01], 3, limiti={"leva": 2}, indici=np.array([[0, 0, 0]]))[0.01]
    check("M4. il Monte Carlo pesca il giorno intero: i tre trade insieme, con la stessa regola dentro il giorno",
          g["finale"][0] == 11_610)
    x = np.random.default_rng(3).normal(size=200)
    gg = pd.date_range("2024-01-01", periods=200, freq="D")
    check("M5. stress test, un trade al giorno: yardstick e Monte Carlo completo con i giorni = quelli di prima, al bit",
          mc.yardstick(x, n_sim=2000).equals(mc.yardstick(x, n_sim=2000, giorni=gg))
          and all(np.array_equal(v, mc.montecarlo_completo(x, n_sim=2000, giorni=gg)[k]) if isinstance(v, np.ndarray)
                  else v == mc.montecarlo_completo(x, n_sim=2000, giorni=gg)[k]
                  for k, v in mc.montecarlo_completo(x, n_sim=2000).items()))
    primo, quanti = mc.gruppi_giorni(np.repeat(np.arange(50), 4))
    pos = mc.sequenze_giorni(primo, quanti, np.array([[3, -1, 7, 1]]), 10)
    check("M6. le sequenze dei giorni: tutti i trade di ogni giorno pescato, in ordine, tagliati alla lunghezza",
          list(pos[0]) == [12, 13, 14, 15, 28, 29, 30, 31, 4, 5])


def _dati_due(cartella, veleno=None, seme_eth=6):
    for m, seme, prezzo, inizio in ((BTC, 5, 30_000.0, "2024-01-01"), (ETH, seme_eth, 2_000.0, "2024-01-15")):
        n = 22_100 if m == BTC else 22_100 - 14 * 96
        df = sintetici.mercato_piantato(n, seme=seme, minuti=15, inizio=inizio, prezzo=prezzo)
        if veleno == m:
            dentro = df.index >= Confini.da_config(CONFINI).tratto_cassaforte[0]
            df.loc[dentro, ["Open", "High", "Low", "Close"]] *= 3.0
            df.loc[dentro, "Volume"] = 1.0
        sintetici.scrivi_storico(cartella, m, "M15", df)
        sintetici.scrivi_funding(cartella, m, df, seme=seme)


def _cfg(processi=1):
    cfg = config_standard([BTC, ETH], "M15", seme=0, processi=processi)
    cfg["confini"] = dict(CONFINI)
    cfg["blocchi"] = {k: v for k, v in cfg["blocchi"].items()
                      if k in ("E47", "E5", "DONCHIAN", "RSI_RIENTRO", "F3_VOLUME_ABOVE_AVG", "ADX", "X0")}
    cfg["rosa"]["min_eventi"] = 60
    cfg["rosa"]["q"] = 1.0
    cfg["qualita_1"]["trade_min"] = 30
    cfg["budget"].update({"per_teoria_passo_1": 6, "teorie_turno_2": 2, "teorie_passo_2": 3, "giri_zoom": 2,
                          "prove_per_giro": 10, "totale": 100_000})
    cfg["altopiano"]["prove_max"] = 10
    return cfg


def _file(e):
    return {n: hashlib.sha256(_leggi(os.path.join(e.cartella, n))).hexdigest() for n in sorted(os.listdir(e.cartella))}


def collaudi_ricerca():
    print("\nLa ricerca su due monete (BTC ed ETH perp sintetiche, ETH più giovane di 14 giorni)")
    with tempfile.TemporaryDirectory() as radice:
        A, R, P, W, S = (os.path.join(radice, k) for k in ("A", "R", "P", "W", "S"))
        for c in (A, R, P, S):
            _dati_due(c)
        _dati_due(W, veleno=ETH)
        cfg = _cfg()
        e = lancia(cfg, A, verbose=False, data=DATA)
        csv = pd.read_csv(registro.FileProve(e.cartella).percorso, dtype=str, keep_default_na=False)
        check("L1. la ricerca su due monete finisce; la cartella è quella della lista; la rosa è salvata (S2)", e.finita
              and os.path.basename(os.path.dirname(e.cartella)) == "BINANCE_PERP_BTCUSDT+ETHUSDT_M15"
              and nome_lista([BTC, ETH]) == "BINANCE_PERP_BTCUSDT+ETHUSDT"
              and os.path.exists(os.path.join(e.cartella, FILE_ROSA)), f"imbuto {e.imbuto}")
        check("L2. una strategia è una riga sola nel conto (per pezzo), con due monete: nessuna riga per moneta",
              not csv.duplicated(["id_ricerca", "pezzo", "id_strategia"]).any() and len(csv) == e.prove
              == registro.conto_prove(A, [BTC, ETH], "M15") and registro.conto_prove(A, [BTC], "M15") == 0
              and "ev_atr" in csv.columns, f"{len(csv)} prove")
        pezzi = carica_pezzi([BTC, ETH], "M15", Confini.da_config(CONFINI), S)
        rifatta = prepara(cfg, pezzi)
        letta = prepara(cfg, pezzi, cartella_ricerca=e.cartella)
        check("L3. la cella 2 con la rosa salvata = la rosa rifatta: stessi valori degeneri, rosa, trigger tenuti, teorie e "
              "budget (S2)", letta.rosa_letta and not rifatta.rosa_letta
              and json.loads(registro.json_riga(letta.rosa)) == json.loads(registro.json_riga(rifatta.rosa))
              and letta.rimaste == rifatta.rimaste and letta.tolte == json.loads(registro.json_riga(rifatta.tolte))
              and letta.tenuti == rifatta.tenuti and [t.id for t in letta.teorie] == [t.id for t in rifatta.teorie]
              and letta.budget_massimo == rifatta.budget_massimo, f"{len(rifatta.rosa)} righe della rosa")
        a = lancia(cfg, R, ferma_dopo=3, verbose=False, data=DATA)
        b = lancia(cfg, R, ferma_dopo=5, verbose=False, data=DATA)
        c = lancia(cfg, R, verbose=False, data=DATA)
        check("L4. fermata e ripresa = corsa unica, bit per bit (rosa salvata, turni, zoom, selezione, prove)",
              not a.finita and not b.finita and c.finita and _file(c) == _file(e))
        tre = lancia(_cfg(processi=3), P, verbose=False, data=DATA)
        f3, f1 = _file(tre), _file(e)
        diversi = sorted(n for n in set(f3) | set(f1) if f3.get(n) != f1.get(n))
        check("L5. 3 processi = 1 processo, al bit: ogni file della ricerca uguale (config.json tiene i processi del primo "
              "salvataggio, che non stanno nell'impronta)", diversi == ["config.json"] and tre.id_ricerca == e.id_ricerca,
              f"diversi: {diversi}")
        ew = lancia(cfg, W, verbose=False, data=DATA)
        check("L6. la cassaforte di ETH avvelenata (prezzi × 3): passi 1–7 identici al bit, nessuna barra di cassaforte "
              "letta prima della cella 5", _file(ew) == _file(e))
        # la cassaforte e la cella 6 su due monete
        scelte = list(e.selezione.scelte["id_strategia"])
        tutte = list(e.selezione.tabella["id_strategia"])
        if not scelte and tutte:                       # per collaudare la cella 6 serve una strategia entrata
            p = os.path.join(e.cartella, "selezione.json")
            dati = json.loads(_leggi(p))
            dati["tabella"][0]["esito"] = "scelta"
            with open(p, "w", encoding="utf-8") as f:
                f.write(registro.json_riga(dati) + "\n")
            scelte = [tutte[0]]
        if not scelte:
            check("L7. la cassaforte su due monete", False, f"nessuna strategia in selezione: {e.imbuto}")
            return
        ca = cas.entra(A, e.id_ricerca, scelte[:1])
        id0 = scelte[0]
        cw = cas.entra(W, ew.id_ricerca, scelte[:1])
        check("L7. la cassaforte su due monete: i trade di ogni moneta; la tabella per moneta; un ingresso e un esito; con "
              "ETH avvelenata cambia solo la sua valutazione", set(ca.trade[id0]) == {BTC, ETH}
              and set(ca.per_moneta["moneta"]) == {BTC, ETH}
              and int(ca.tabella["trade"].iloc[0]) == sum(len(ca.trade[id0][m]) for m in (BTC, ETH))
              and cw.trade[id0][BTC].equals(ca.trade[id0][BTC]) and not cw.trade[id0][ETH].equals(ca.trade[id0][ETH]),
              ca.per_moneta.round(3).to_string(index=False).replace("\n", " | "))
        with ses.sessioni(ca, id0) as ss:
            mm_out = _zitto(ses.money_management, ss, simulazioni=200)
            tab_is = mm_out["tabella_is"]
            st = _zitto(ses.stress_test, ss, mm_out, simulazioni=1000)
            ver = _zitto(ses.verifica_trade, ss)
            check("L8. la cella 6 su due monete: il money management sui trade di tutte e due in ordine d'ingresso, con "
                  "ingresso, uscita, giorno e i lotti di ogni moneta; lo stress test a giorni interi; la verifica moneta "
                  "per moneta, ogni regola OK", set(tab_is["moneta"]) == {BTC, ETH}
                  and pd.DatetimeIndex(tab_is["ingresso"]).is_monotonic_increasing
                  and {"giorno", "lotto_minimo", "lotto_passo"} <= set(tab_is)
                  and set(tab_is.loc[tab_is["moneta"] == ETH, "lotto_minimo"]) == {0.001}
                  and st["unita"] == "bp" and {x["moneta"] for x in st["sizing"]["lotti"]} == {BTC, ETH}
                  and (ver["regole"]["Esito"] == "OK").all() and set(ver["regole"]["moneta"]) == {BTC, ETH},
                  f"{len(tab_is)} trade in-sample, rischio {mm_out['f']}")
        check("L9. alla fine il catalogo è pulito: nessuna condizione temporanea della Sessione",
              not any(n.startswith(ses.PREFISSO) for n in reg.list_entries() + reg.list_filters()))


def esegui() -> int:
    t0 = time.perf_counter()
    collaudi_orologio()
    collaudi_rosa()
    collaudi_valutatore()
    collaudi_mm()
    collaudi_ricerca()
    print("\n" + "=" * 70)
    print(f"Durata: {time.perf_counter() - t0:.0f} s")
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
