"""
Suite di collaudo della selezione della fabbrica (docs/82 P6 e P7, lavoro L4a): condizione di qualità 2, test
individuale, famiglie fra le strategie, conto delle prove, vantaggio piantato fino alla selezione.

Si lancia da terminale, dalla cartella del progetto:

    python test_fabbrica_selezione.py

Solo dati sintetici (engine/fabbrica/sintetici.py e mercati fatti a mano qui sotto), scritti in cartelle temporanee:
non servono i file in dati/, MetaTrader 5 o internet. Stampa una riga per collaudo e alla fine
«RISULTATO: n/n test superati». Dura circa un minuto.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import tempfile
import time
import warnings

import numpy as np
import pandas as pd

from engine import registry as reg
from engine.fabbrica import registro, selezione as sel_mod, sintetici
from engine.fabbrica.blocchi import blocchi_da_config
from engine.fabbrica.cache import Cache
from engine.fabbrica.config import cartella_asset, config_standard
from engine.fabbrica.dati import Confini, carica_pezzi
from engine.fabbrica.generatore import Teoria, stato_registro
from engine.fabbrica.ricerca import lancia
from engine.fabbrica.selezione import (PREFISSO, ValutatoreSelezione, ammesse, controlla_ammessa, famiglie_strategie,
                                       giudica, pezzo_selezione, seleziona, soglia_test, strategia_da_riga, teoria_da_id)
from engine.fabbrica.valutatore import Costi, Strategia, id_strategia, trade_completi
from engine.giudizio import soglia_rumore, t_stat

warnings.simplefilter("ignore")

PERP, SPOT = "BINANCE_PERP_BTCUSDT", "BYBIT_SPOT_ETHUSDT"
DATA = "20260101"
ESITI: list[bool] = []


def check(nome: str, ok: bool, dettaglio: str = "") -> None:
    ESITI.append(bool(ok))
    print(f"[{'OK ' if ok else 'KO '}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""))


def errore(funzione, tipo=Exception) -> bool:
    try:
        funzione()
    except tipo:
        return True
    return False


def _leggi(percorso):
    with open(percorso, "rb") as f:
        return f.read()


def _fotografia(cartella, salta="fabbrica"):
    """{percorso: sha256} di tutti i file sotto `cartella`, tranne quelli sotto `salta`."""
    out = {}
    for radice, _, nomi in os.walk(cartella):
        if os.path.relpath(radice, cartella).split(os.sep)[0] == salta:
            continue
        for n in nomi:
            p = os.path.join(radice, n)
            out[os.path.relpath(p, cartella)] = hashlib.sha256(_leggi(p)).hexdigest()
    return out


def _cfg(symbol, blocchi, confini, **altro):
    cfg = config_standard(symbol, "M15", seme=0, processi=1)
    cfg["confini"] = dict(confini)
    cfg["blocchi"] = {k: v for k, v in cfg["blocchi"].items() if k in blocchi}
    cfg.update(altro)
    return cfg


def _riga(s: Strategia, symbol: str) -> dict:
    return {"teoria": s.teoria_id, "id_strategia": id_strategia(s, symbol, "M15"),
            "valori": json.dumps(s.come_dict()["valori"], ensure_ascii=False, sort_keys=True)}


def _con_t(t_voluto: float, n: int = 100) -> np.ndarray:
    """bp alternati ±1 attorno a una media scelta così che t_stat dia esattamente t_voluto."""
    dev = np.tile([1.0, -1.0], n // 2)
    t1 = t_stat(1.0 + dev)                  # con media 1: t = 1 / (s / radice di n)
    return t_voluto / t1 + dev


# ------------------------------------------------------------------ il mercato fatto a mano
PASSO_MANO = 80          # barre fra due segnali
INGRESSO = 100.5         # prezzo d'ingresso di ogni trade


def mercato_mano(n_ric, n_sel, n_cas, guadagni_ric, guadagni_sel, aperto_alla_fine=True):
    """
    Prezzo fermo a 100 con barre strette (± 0,05). Ogni segnale k: la barra chiude a 100,5, sopra il massimo delle 16
    barre prima (rottura del canale di Donchian di 16 barre); la barra dopo apre a 100,5 (l'ingresso, Low = 100,5) e
    il prezzo resta a 100,5 + g per 13 barre: un long che esce dopo 4 barre guadagna g, sempre, senza toccare lo stop.
    Con `aperto_alla_fine` un segnale in più 3 barre prima della fine della selezione: il trade resterebbe aperto.
    """
    n = n_ric + n_sel + n_cas
    o = np.full(n, 100.0)
    c, h, l = o.copy(), o + 0.05, o - 0.05
    segnali = []

    def rottura(k, g):
        o[k], c[k], h[k], l[k] = 100.0, INGRESSO, INGRESSO + 0.05, 99.95
        o[k + 1], c[k + 1], h[k + 1], l[k + 1] = INGRESSO, INGRESSO + g, INGRESSO + g + 0.05, INGRESSO
        for j in range(k + 2, min(k + 14, n)):
            o[j] = c[j] = INGRESSO + g
            h[j], l[j] = c[j] + 0.05, c[j] - 0.05
        segnali.append(k)

    k = 600
    for g in guadagni_ric:
        rottura(k, g)
        k += PASSO_MANO
    k = n_ric + 20
    for g in guadagni_sel:
        rottura(k, g)
        k += PASSO_MANO
    assert k < n_ric + n_sel - 20
    if aperto_alla_fine:
        rottura(n_ric + n_sel - 3, 0.6)
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 1000.0}, index=idx), segnali


def bp_a_mano(g: float, costi: dict) -> float:
    """I bp netti di un long da 100,5 a 100,5 + g: commissione sui due lati e spread di un passo (metriche.bp_per_trade)."""
    pip, comm, passo = float(costi["pip_size"]), float(costi["commission"]), float(costi["spread_passo_pips"])
    ep, xp = INGRESSO, INGRESSO + g
    return ((xp - ep) / pip - comm * (ep + xp) / pip - passo) * pip * 10_000.0 / ep


DONCHIAN_16 = Strategia.da_teoria(Teoria(1, "DONCHIAN", (), "X0"), {
    "DONCHIAN": {"canale_barre": 16}, "X0": {"durata_barre": 4, "perc_stop": 90, "target": None}})


def giro_a_mano(cartella, guadagni_sel, aperto_alla_fine=True):
    """Il mercato fatto a mano su disco, i pezzi, e la selezione della sola DONCHIAN_16."""
    n_ric, n_sel, n_cas = 1200, 61 * PASSO_MANO + 100, 400
    df, segnali = mercato_mano(n_ric, n_sel, n_cas, [0.6] * 5, guadagni_sel, aperto_alla_fine)
    sintetici.scrivi_storico(cartella, SPOT, "M15", df)
    confini = {"inizio": "2024-01-01 00:00", "ricerca_ore": n_ric / 4, "selezione_ore": n_sel / 4,
               "cassaforte_ore": n_cas / 4}
    cfg = _cfg(SPOT, ("DONCHIAN", "X0"), confini)
    pezzi = carica_pezzi(SPOT, "M15", Confini.da_config(confini), cartella)
    sel = seleziona(pd.DataFrame([_riga(DONCHIAN_16, SPOT)]), pezzi, cfg)
    return sel, pezzi, cfg, df, segnali


def esegui() -> int:
    t0 = time.perf_counter()
    q2 = config_standard(PERP, "M15")["qualita_2"]
    cfg_q = {"qualita_2": q2, "test_individuale": {"alfa": 0.05}}

    # ------------------------------------------------------------------ le regole, su bp fatti a mano
    print("Le regole: condizione di qualità 2 e test individuale (docs/82 P6)")
    check("1. la soglia del test individuale è quella di una prova sola: 1,96",
          soglia_test(0.05) == soglia_rumore(1, 0.05) and abs(soglia_test(0.05) - 1.959964) < 1e-6)
    sotto, sopra = giudica(_con_t(1.95), cfg_q), giudica(_con_t(1.97), cfg_q)
    check("2. t appena sotto 1,96: passa la condizione 2, non il test individuale, che decide",
          abs(sotto["t"] - 1.95) < 1e-12 and sotto["qualita_2"] and not sotto["test"] and not sotto["passa"]
          and sotto["motivo"].startswith("test individuale"), f"t {sotto['t']:.6f}, P(EV<0) {sotto['p_ev_neg']:.1f}%")
    check("3. t appena sopra 1,96: passa", abs(sopra["t"] - 1.97) < 1e-12 and sopra["passa"] and sopra["motivo"] == "",
          f"t {sopra['t']:.6f}")
    alterni = np.tile([2.0, -1.0], 25)
    casi = {
        "49 trade": (alterni[:49], "49 trade, meno di 50"),
        "EV zero": (np.tile([1.0, -1.0], 50), "verdetto SCARTATA: EV netto"),
        "P(EV<0) oltre il 5%": (np.tile([1.27, -1.0], 50), "verdetto SCARTATA: P(EV<0)"),
        "un trade pesa troppo": (np.r_[np.tile([2.0, -1.0], 99), 2.0, 60.0], "il trade migliore pesa"),
        "totale / drawdown sotto 0,5": (np.r_[np.full(300, 2.0)[:150], np.full(101, -4.0), np.full(150, 2.0)],
                                        "totale / drawdown"),
    }
    motivi, sbagliati = {}, []
    for nome, (bp, atteso) in casi.items():
        g = giudica(bp, cfg_q)
        motivi[nome] = g["motivo_q2"]
        if g["qualita_2"] or not g["motivo_q2"].startswith(atteso) or g["passa"]:
            sbagliati.append(nome)
    check(f"4. {len(casi)} casi fatti a mano: ognuno fermato dalla regola giusta della condizione 2", not sbagliati,
          f"sbagliati: {sbagliati}" if sbagliati else "")
    g_tdd = giudica(casi["totale / drawdown sotto 0,5"][0], cfg_q)
    g_peso = giudica(casi["un trade pesa troppo"][0], cfg_q)
    check("5. le due regole sopra fermano strategie che il t da solo farebbe passare",
          g_tdd["t"] > 1.96 and g_peso["t"] > 1.96 and not g_tdd["passa"] and not g_peso["passa"],
          f"t {g_tdd['t']:.2f} e {g_peso['t']:.2f}")
    g50 = giudica(alterni, cfg_q)
    check("6. 50 trade esatti: la regola dei trade passa (alterni +2 / -1, t sopra 1,96)", g50["passa"] and g50["trade"] == 50,
          f"t {g50['t']:.2f}")
    vuota = giudica(np.array([]), cfg_q)
    check("7. nessun trade: scartata, nessun errore", not vuota["passa"] and vuota["trade"] == 0)

    with tempfile.TemporaryDirectory() as radice:
        # ------------------------------------------------------------------ il mercato fatto a mano
        print("\nUna strategia con il segnale noto su dati fatti a mano (DONCHIAN 16 barre, esce dopo 4)")
        A = os.path.join(radice, "mano_a")
        gs = [0.6, 0.4] * 30
        sel_a, pezzi_a, cfg_a, df_a, seg_a = giro_a_mano(A, gs)
        p = pezzo_selezione(pezzi_a)
        r = sel_a.tabella.iloc[0]
        costi_sel = pezzi_a.costi("selezione")
        attesi = np.array([bp_a_mano(g, costi_sel) for g in gs])
        check("8. il pezzo passato alla selezione finisce all'ultima barra della selezione, senza barre della cassaforte",
              p.df.index[-1] == pezzi_a.selezione.index[-1] and p.df.index[-1] < pezzi_a.confini.tratto_cassaforte[0]
              and pd.DatetimeIndex(p.df.index[p.inizio:]).equals(pd.DatetimeIndex(pezzi_a.selezione.index))
              and p.df.index[p.inizio - 1] == pezzi_a.ricerca.index[-1],
              f"ultima barra {p.df.index[-1]:%d/%m %H:%M}, cassaforte dal {pezzi_a.confini.tratto_cassaforte[0]:%d/%m %H:%M}")
        cache = Cache(p.df, 500)
        v = ValutatoreSelezione(blocchi_da_config(cfg_a), cache, Costi(p.df, p.costi), p.inizio)
        tr = trade_completi(DONCHIAN_16, v, p.costi)
        primo_sel = int(pd.DatetimeIndex(df_a.index).searchsorted(pezzi_a.selezione.index[0]))
        ingressi_attesi = [p.df.index.get_loc(df_a.index[k + 1]) for k in seg_a if primo_sel <= k < len(df_a) - 400 - 3]
        check("9. trade = i 60 segnali della selezione, uno per segnale, ingresso alla barra dopo a 100,5; nessuno dei 5 "
              "segnali della ricerca", list(tr["EntryBar"]) == ingressi_attesi and len(tr) == 60
              and (tr["EntryPrice"] == INGRESSO).all() and int(r["trade"]) == 60,
              f"{len(tr)} trade")
        check("10. il trade che resterebbe aperto all'ultima barra della selezione resta fuori (motore, U7): nessun "
              "prezzo dalla cassaforte, nessuna uscita dopo l'ultima barra",
              int(tr["ExitBar"].max()) <= len(p.df) - 1 and (tr["ExitBar"] - tr["EntryBar"] == 4).all()
              and p.df.index.get_loc(df_a.index[seg_a[-1]]) == len(p.df) - 3,
              f"ultimo segnale a {len(p.df) - 1 - p.df.index.get_loc(df_a.index[seg_a[-1]])} barre dalla fine")
        check("11. bp netti, EV e t uguali a quelli fatti a mano (commissione, spread di un passo)",
              np.allclose(tr["BpNetti"].to_numpy(), attesi, atol=1e-9, rtol=0)
              and abs(r["ev_bp"] - attesi.mean()) < 1e-9 and abs(r["t"] - t_stat(attesi)) < 1e-9,
              f"EV {r['ev_bp']:.4f} bp contro {attesi.mean():.4f} a mano")
        check("12. passa la regola: condizione 2 e test individuale, esito «scelta»",
              bool(r["qualita_2"]) and bool(r["test"]) and r["esito"] == "scelta", f"t {r['t']:.1f}")
        B = os.path.join(radice, "mano_b")
        sel_b = giro_a_mano(B, [0.6, 0.4] * 24 + [0.6])[0].tabella.iloc[0]
        check("13. 49 segnali chiusi più quello aperto alla fine: 49 trade, non passa (meno di 50)",
              int(sel_b["trade"]) == 49 and not sel_b["qualita_2"] and sel_b["esito"] == "scartata"
              and sel_b["motivo"] == "condizione 2: 49 trade, meno di 50", sel_b["motivo"])
        C = os.path.join(radice, "mano_c")
        gs_c = [0.25, 0.15] * 30
        sel_c = giro_a_mano(C, gs_c)[0].tabella.iloc[0]
        ev_c = np.mean([bp_a_mano(g, costi_sel) for g in gs_c])
        check("14. guadagni lordi più piccoli dei costi: EV netto negativo come a mano, non passa",
              abs(sel_c["ev_bp"] - ev_c) < 1e-9 and ev_c < 0 and not sel_c["qualita_2"] and sel_c["esito"] == "scartata"
              and "EV netto" in sel_c["motivo"], f"EV {sel_c['ev_bp']:.3f} bp; {sel_c['motivo']}")

        # ------------------------------------------------------------------ il percorso corto contro il motore
        print("\nIl percorso corto contro il motore completo, sul perpetual con il funding")
        Pd = os.path.join(radice, "perp")
        confini_p = {"inizio": "2024-01-01 00:00", "ricerca_ore": 3000, "selezione_ore": 1500, "cassaforte_ore": 500}
        df_p = sintetici.mercato(int((3000 + 1500 + 500) * 4) + 50, seme=7, minuti=15, inizio="2024-01-01",
                                 prezzo=30_000.0)
        sintetici.scrivi_storico(Pd, PERP, "M15", df_p)
        sintetici.scrivi_funding(Pd, PERP, df_p, seme=7)
        cfg_p = _cfg(PERP, ("E47", "DONCHIAN", "RSI_RIENTRO", "F3_VOLUME_ABOVE_AVG", "ADX", "X0", "X3", "X1"), confini_p)
        pezzi_p = carica_pezzi(PERP, "M15", Confini.da_config(confini_p), Pd)
        pp = pezzo_selezione(pezzi_p)
        cache_p = Cache(pp.df, 800)
        vp = ValutatoreSelezione(blocchi_da_config(cfg_p), cache_p, Costi(pp.df, pp.costi), pp.inizio)
        prove_s = []
        for lato in (1, -1):
            for canale, uscita, durata, stop, target in ((16, "X0", 16, 90, None), (40, "X3", 32, 80, 90),
                                                         (96, "X1", 8, 95, None)):
                prove_s.append(Strategia.da_teoria(Teoria(lato, "DONCHIAN", (), uscita), {
                    "DONCHIAN": {"canale_barre": canale},
                    uscita: {"durata_barre": durata, "perc_stop": stop, "target": target}}))
            prove_s.append(Strategia.da_teoria(Teoria(lato, "RSI_RIENTRO", ("ADX",), "X0"), {
                "RSI_RIENTRO": {"periodo_barre": 24, "soglia": 25}, "ADX": {"periodo_barre": 24, "soglia": 20},
                "X0": {"durata_barre": 16, "perc_stop": 90, "target": 90}}))
            prove_s.append(Strategia.da_teoria(Teoria(lato, "E47", ("F3_VOLUME_ABOVE_AVG",), "X0"), {
                "E47": {}, "F3_VOLUME_ABOVE_AVG": {}, "X0": {"durata_barre": 8, "perc_stop": 70, "target": None}}))
        uguali, dentro, n_trade, funding = [], [], 0, 0.0
        for s in prove_s:
            t = trade_completi(s, vp, pp.costi)
            uguali.append(np.allclose(vp.bp(s), t["BpNetti"].to_numpy(), atol=1e-9, rtol=0))
            dentro.append(bool(len(t) == 0 or (t["EntryBar"].min() >= pp.inizio + 1
                                               and t["ExitBar"].max() <= len(pp.df) - 1)))
            n_trade += len(t)
            funding += float(t["FundingPips"].abs().sum()) if "FundingPips" in t else 0.0
        check(f"15. {len(prove_s)} strategie, long e short: bp del percorso corto = MotoreVeloce.run + bp_per_trade "
              "(1e-9), funding compreso", all(uguali) and n_trade > 200 and funding > 0, f"{n_trade} trade")
        check("16. ogni trade nasce nella selezione (segnale dalla prima barra) e chiude entro l'ultima", all(dentro))
        soglie = blocchi_da_config(cfg_p)[-3].soglie(cache_p, 1, {"durata_barre": 16, "perc_stop": 90, "target": None})
        sola_selezione = pp.df.iloc[pp.inizio:].copy()
        solo_sel = Cache(sola_selezione, 200)
        soglie_sole = blocchi_da_config(cfg_p)[-3].soglie(solo_sel, 1, {"durata_barre": 16, "perc_stop": 90,
                                                                      "target": None})
        check("17. gli indicatori non ripartono da zero: lo stop adattivo c'è già alla prima barra della selezione "
              "(sulla sola selezione no)", not math.isnan(soglie["sl"][pp.inizio]) and math.isnan(soglie_sole["sl"][0])
              and len(sola_selezione) == len(pezzi_p.selezione))

        # ------------------------------------------------------------------ le famiglie
        print("\nLe famiglie fra le strategie (quota 70%, lift 1,3, famiglia 60%)")
        idx = pd.date_range("2024-01-01", periods=20_000, freq="15min", tz="UTC")
        df_f = pd.DataFrame(index=idx)
        rng = np.random.default_rng(1)
        m_a, m_b, m_c = (rng.random(len(idx)) < 0.01 for _ in range(3))
        m_d = m_a.copy()
        m_d[np.flatnonzero(m_a)[::10]] = False                      # il 90% di A
        prima = stato_registro()
        fam, sov = famiglie_strategie({"aa": m_a, "bb": m_b, "cc": m_c, "dd": m_a.copy(), "ee": m_d}, df_f, 1,
                                      {"aa": 3.0, "bb": 2.5, "cc": 2.2, "dd": 4.0, "ee": 3.0})
        f = fam.set_index("id_strategia")
        check("18. due strategie con lo stesso segnale (e una quasi uguale) stanno nella stessa famiglia; ne resta una, "
              "quella con il t più alto", f.loc["aa", "famiglia"] == f.loc["dd", "famiglia"] == f.loc["ee", "famiglia"] == "dd"
              and bool(f.loc["dd", "migliore"]) and not f.loc["aa", "migliore"] and not f.loc["ee", "migliore"]
              and int(f.loc["aa", "membri"]) == 3, f"famiglie: {dict(zip(fam['id_strategia'], fam['famiglia']))}")
        check("19. segnali indipendenti: famiglie diverse, ognuna la sua scelta",
              f.loc["bb", "famiglia"] == "bb" and f.loc["cc", "famiglia"] == "cc" and bool(f.loc["bb", "migliore"])
              and bool(f.loc["cc", "migliore"]))
        pari = famiglie_strategie({"zz": m_a, "yy": m_a.copy()}, df_f, -1, {"zz": 2.0, "yy": 2.0})[0]
        check("20. a parità di t resta l'id più piccolo; il lato è nella riga",
              pari.set_index("id_strategia").loc["yy", "migliore"] and set(pari["lato"]) == {"short"})
        check("21. i doppioni di sovrapposizioni stanno nella tabella (quota 70%, lift 1,3)",
              bool(((sov["contenuta"] == "ee") & (sov["dentro"] == "aa") & sov["doppione"]).any()))
        dopo = stato_registro()
        senza_prefisso = not any(n.startswith(PREFISSO) for n in reg.list_entries())
        check("22. registro delle condizioni identico prima e dopo, nessuna strategia temporanea rimasta",
              prima == dopo and senza_prefisso)
        vera = sel_mod.famiglie_misurate

        def rompi(*a, **k):
            raise RuntimeError("misura rotta apposta")

        sel_mod.famiglie_misurate = rompi
        try:
            fermata = errore(lambda: famiglie_strategie({"aa": m_a, "bb": m_b}, df_f, 1, {"aa": 1.0, "bb": 2.0}),
                             RuntimeError)
        finally:
            sel_mod.famiglie_misurate = vera
        check("23. la misura si ferma con un errore a metà: il registro torna identico, nessuna strategia temporanea",
              fermata and stato_registro() == prima and not any(n.startswith(PREFISSO) for n in reg.list_entries()))
        check("24. id della teoria avanti e indietro; una riga con valori cambiati si ferma",
              teoria_da_id("S|E47|ADX+F3_VOLUME_ABOVE_AVG|X3") == Teoria(-1, "E47", ("ADX", "F3_VOLUME_ABOVE_AVG"), "X3")
              and teoria_da_id("L|DONCHIAN|-|X0").id == "L|DONCHIAN|-|X0"
              and strategia_da_riga(_riga(DONCHIAN_16, SPOT), SPOT, "M15") == DONCHIAN_16
              and errore(lambda: strategia_da_riga({**_riga(DONCHIAN_16, SPOT), "valori": json.dumps(
                  {"DONCHIAN": {"canale_barre": 17}, "X0": {"durata_barre": 4, "perc_stop": 90, "target": None}})},
                  SPOT, "M15")))

        # ------------------------------------------------------------------ tutta la pipeline
        print("\nIl vantaggio piantato fino alla selezione: DONCHIAN long a 40 barre, uscita dopo 12")
        confini_v = {"inizio": "2024-01-01 00:00", "ricerca_ore": 3000, "selezione_ore": 2000, "cassaforte_ore": 500}
        barre_v = int((3000 + 2000 + 500) * 4) + 100
        df_v = sintetici.mercato_piantato(barre_v, seme=5, minuti=15, inizio="2024-01-01", prezzo=2_000.0)
        cfg_v = _cfg(SPOT, ("E47", "DONCHIAN", "RSI_RIENTRO", "F3_VOLUME_ABOVE_AVG", "X0"), confini_v)
        cfg_v["qualita_1"]["trade_min"] = 30
        cfg_v["budget"].update({"teorie_passo_2": 4, "prove_per_giro": 60})
        V = os.path.join(radice, "V")
        sintetici.scrivi_storico(V, SPOT, "M15", df_v)
        sintetici.scrivi_storico(V, PERP, "M15", df_p)               # un altro dataset accanto
        os.makedirs(os.path.join(V, "studio"))
        for nome, testo in (("confine.json", '{"confine": "2025-06-15 17:30"}\n'),
                            ("diario_pc.jsonl", '{"prova": 1}\n'), ("giornale_pc.jsonl", '{"voce": "trigger"}\n')):
            with open(os.path.join(V, "studio", nome), "w", encoding="utf-8") as fh:
                fh.write(testo)
        foto = _fotografia(V)
        e = lancia(cfg_v, V, verbose=False, data=DATA)
        tab = e.selezione.tabella
        scelte = e.selezione.scelte
        primo = scelte.iloc[0] if len(scelte) else None
        valori_v = json.loads(primo["valori"]) if primo is not None else {}
        canale_v = valori_v.get("DONCHIAN", {}).get("canale_barre")
        durata_v = valori_v.get("X0", {}).get("durata_barre")
        check("25. la teoria piantata passa la selezione: DONCHIAN long scelta, canale e durata vicini a 40 e 12, t sopra "
              "1,96", primo is not None and primo["teoria"].startswith("L|DONCHIAN|") and abs(canale_v - 40) <= 8
              and abs(durata_v - 12) <= 2 and primo["t"] >= 1.96 and primo["esito"] == "scelta",
              f"{primo['teoria'] if primo is not None else '-'}: canale {canale_v}, durata {durata_v}, "
              f"t {primo['t'] if primo is not None else float('nan'):.1f}; imbuto {e.imbuto}")
        famiglie_ok = all(tab.loc[tab["esito"] == "stessa famiglia", "famiglia"].isin(scelte["id_strategia"]))
        per_fam = tab[tab["esito"] != "scartata"].groupby("famiglia")["esito"].apply(lambda x: (x == "scelta").sum())
        check("26. una sola «scelta» per famiglia, le altre rimandano a lei; le scartate non hanno famiglia",
              famiglie_ok and (per_fam == 1).all() and tab.loc[tab["esito"] == "scartata", "famiglia"].isna().all()
              and set(tab["esito"]) <= set(sel_mod.ESITI), str(tab["esito"].value_counts().to_dict()))
        non_scelte = list(tab.loc[tab["esito"] != "scelta", "id_strategia"])
        check("27. una strategia scartata in selezione (o tolta dalla famiglia) non può comparire ai passi dopo: errore",
              non_scelte and all(errore(lambda i=i: controlla_ammessa(tab, i)) for i in non_scelte)
              and errore(lambda: controlla_ammessa(tab, "id_mai_visto"))
              and all(controlla_ammessa(tab, i) is None for i in scelte["id_strategia"])
              and ammesse(tab) == list(scelte["id_strategia"]), f"{len(non_scelte)} non scelte")
        csv_v = pd.read_csv(registro.FileProve(e.cartella).percorso, dtype=str, keep_default_na=False)
        righe_sel = csv_v[csv_v["pezzo"] == "selezione"]
        check("28. ogni strategia valutata in selezione è una riga del file delle prove (pezzo «selezione»)",
              sorted(righe_sel["id_strategia"]) == sorted(e.sopravvissute["id_strategia"])
              and len(righe_sel) == len(tab) and (righe_sel["fase"] == "selezione").all())
        k = registro.conto_prove(V, SPOT, "M15")
        check("29. conto delle prove: totale dell'asset e soglia corrispondente accanto al test, solo da leggere",
              e.conto["asset"] == k == len(csv_v) and e.conto["questa_ricerca"] == k
              and (tab["prove_asset"] == k).all() and np.allclose(tab["soglia_da_leggere"], soglia_rumore(k))
              and list(tab.columns).index("soglia_da_leggere") == list(tab.columns).index("test") + 2,
              f"k = {k}, soglia {soglia_rumore(k):.2f}")
        fine = [x for x in registro.leggi_registro(cartella_asset(V, SPOT, "M15")) if x["tipo"] == "fine_ricerca"]
        check("30. registro: la fine porta imbuto con selezione e scelte, conto e una riga per strategia selezionata",
              len(fine) == 1 and fine[0]["imbuto"] == e.imbuto and fine[0]["prove"]["asset"] == k
              and [x["id_strategia"] for x in fine[0]["selezione"]] == list(tab["id_strategia"])
              and {"selezione", "scelte"} <= set(e.imbuto))
        check("31. separazione dal Lab: la cartella dello studio e gli altri dati restano identici al bit",
              _fotografia(V) == foto and os.path.isdir(os.path.join(V, "fabbrica")))
        byte_sel = _leggi(os.path.join(e.cartella, "selezione.json"))
        byte_prove = _leggi(registro.FileProve(e.cartella).percorso)
        e2 = lancia(cfg_v, V, verbose=False, data=DATA)
        check("32. rilancio: la selezione si rilegge, nessuna prova in più, stessa tabella",
              _leggi(os.path.join(e.cartella, "selezione.json")) == byte_sel
              and _leggi(registro.FileProve(e.cartella).percorso) == byte_prove
              and e2.selezione.tabella.equals(tab) and e2.conto == e.conto)

        print("\nLa selezione non legge la cassaforte, e il conto non decide")
        W = os.path.join(radice, "W")
        velenoso = df_v.copy()
        dentro_c = velenoso.index >= Confini.da_config(confini_v).tratto_cassaforte[0]
        velenoso.loc[dentro_c, ["Open", "High", "Low", "Close"]] *= 1000.0
        velenoso.loc[dentro_c, "Volume"] = 1.0
        sintetici.scrivi_storico(W, SPOT, "M15", velenoso)
        ew = lancia(cfg_v, W, verbose=False, data=DATA)
        check("33. cassaforte avvelenata (prezzi × 1000): passi 1–2, selezione e prove identici al bit",
              ew.id_ricerca == e.id_ricerca and _leggi(os.path.join(ew.cartella, "selezione.json")) == byte_sel
              and _leggi(registro.FileProve(ew.cartella).percorso) == byte_prove
              and all(_leggi(os.path.join(ew.cartella, n)) == _leggi(os.path.join(e.cartella, n))
                      for n in ("passo_1.jsonl", "passo_2.jsonl")))
        X = os.path.join(radice, "X")
        sintetici.scrivi_storico(X, SPOT, "M15", df_v)
        registro.aggiungi_prove(os.path.join(cartella_asset(X, SPOT, "M15"), "20250101_altra"),
                                [{"id_ricerca": "altra", "pezzo": "ricerca", "fase": "passo_1", "teoria": "x",
                                  "id_strategia": f"s{i}", "trade": 1, "ev_bp": 1.0, "t": 1.0} for i in range(500)])
        ex = lancia(cfg_v, X, verbose=False, data=DATA)
        tx = ex.selezione.tabella
        fisse = [c for c in tab.columns if c not in ("prove_asset", "soglia_da_leggere")]
        check("34. con il conto alterato (500 prove di un'altra ricerca) gli esiti non cambiano: cambiano solo il conto e "
              "la soglia da leggere", tx[fisse].equals(tab[fisse]) and (tx["prove_asset"] == k + 500).all()
              and np.allclose(tx["soglia_da_leggere"], soglia_rumore(k + 500)) and ex.imbuto == e.imbuto,
              f"soglia {soglia_rumore(k):.2f} → {soglia_rumore(k + 500):.2f}")

    print("\n" + "=" * 70)
    print(f"Durata: {time.perf_counter() - t0:.0f} s")
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
