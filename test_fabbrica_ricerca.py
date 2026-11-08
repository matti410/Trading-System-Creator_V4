"""
Suite di collaudo della ricerca della fabbrica (docs/82 P4, P5, P7, lavoro L3b): passo 1, zoom, altopiano, ripresa.

Si lancia da terminale, dalla cartella del progetto:

    python test_fabbrica_ricerca.py

Solo dati sintetici (engine/fabbrica/sintetici.py), scritti in cartelle temporanee: non servono i file in dati/,
MetaTrader 5 o internet. Usa 3 processi per un collaudo. Stampa una riga per collaudo e alla fine
«RISULTATO: n/n test superati». Dura circa un minuto e mezzo.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import sys
import tempfile
import time
import warnings

import numpy as np
import pandas as pd

from engine.fabbrica import registro, sintetici
from engine.fabbrica.blocchi import blocchi_da_config
from engine.fabbrica.config import cartella_asset, config_standard, impronta_config
from engine.fabbrica.dati import Confini, carica_pezzi
from engine.fabbrica.generatore import Teoria, stato_registro
from engine.fabbrica.ottimizzatore import Categoria, Intero, Spazio
from engine.fabbrica.ricerca import (Asse, _Lavoro, _ProveTeoria, cerca, giudica_altopiano, lancia, passi_zoom,
                                     prepara, spazio_giro, vicini, zoom)
from engine.fabbrica.valutatore import Strategia, qualita_1

warnings.simplefilter("ignore")

PERP, SPOT = "BINANCE_PERP_BTCUSDT", "BYBIT_SPOT_ETHUSDT"
CONFINI = {"inizio": "2024-01-01 00:00", "ricerca_ore": 4000, "selezione_ore": 1000, "cassaforte_ore": 500}
BARRE = 22_100
DATA = "20260101"
BLOCCHI_PICCOLI = ("E47", "DONCHIAN", "RSI_RIENTRO", "F3_VOLUME_ABOVE_AVG", "ADX", "X0")
SOGLIE_ALT = {"mediana_min": 0.7, "peggiore_min": 0.4}


def _dati(cartella, seme=3):
    df = sintetici.mercato(BARRE, seme=seme, minuti=15, inizio="2024-01-01", prezzo=30_000.0)
    sintetici.scrivi_storico(cartella, PERP, "M15", df)
    sintetici.scrivi_funding(cartella, PERP, df, seme=seme)


def _config(processi=1, seme=0):
    cfg = config_standard(PERP, "M15", seme=seme, processi=processi)
    cfg["confini"] = dict(CONFINI)
    cfg["blocchi"] = {k: v for k, v in cfg["blocchi"].items() if k in BLOCCHI_PICCOLI}
    cfg["qualita_1"]["trade_min"] = 30
    cfg["budget"].update({"teorie_passo_2": 4, "prove_per_giro": 30})
    return cfg


def _leggi(percorso):
    with open(percorso, "rb") as f:
        return f.read()


def _jsonl(percorso):
    with open(percorso, encoding="utf-8") as f:
        return [json.loads(r) for r in f.read().splitlines()]


def _file(esito):
    return {n: _leggi(os.path.join(esito.cartella, n)) for n in ("passo_1.jsonl", "passo_2.jsonl")} | {
        "prove": _leggi(registro.FileProve(esito.cartella).percorso)}


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


def _in_ordine(righe, quante, solo_passano=False):
    scelte = [(i, r) for i, r in enumerate(righe) if r["t"] == r["t"] and r["t"] is not None
              and (r["passa"] or not solo_passano)]
    scelte.sort(key=lambda x: (-x[1]["t"], x[0]))
    return [r for _, r in scelte[:quante]]


def _raggiungibili(griglia, fine, reale=False):
    """Per ogni valore fine fra minimo e massimo della griglia: lo zoom di 3 giri lo prova? (passo 1 = la griglia)."""
    asse = Asse("X.p", tuple(griglia), fine, reale)
    mancati = []
    for obiettivo in range(asse.massimo + 1):
        provati = {}

        def f(piatti, giro=0, _o=obiettivo):
            k = asse.unita(piatti["X.p"])
            if k in provati:
                return provati[k], False
            provati[k] = -abs(k - _o)
            return provati[k], True

        for g in griglia:
            f({"X.p": g})

        def migliori():
            return [{"X.p": asse.valore(k)} for k, _ in sorted(provati.items(), key=lambda kv: -kv[1])[:5]]

        zoom([asse], migliori, f, 3, 90, [1, 2, 3])
        if obiettivo not in provati:
            mancati.append(asse.valore(obiettivo))
    return asse.massimo + 1, mancati


def esegui() -> int:
    ESITI = []
    t0 = time.perf_counter()

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        print(f"[{'OK ' if condizione else 'KO '}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""), flush=True)

    # ------------------------------------------------------------------ lo zoom, da solo
    print("Lo zoom: passi, intervalli, ogni intero raggiungibile")
    casi = {8: [4, 2, 1], 96: [48, 7, 1], 12: [6, 2, 1], 16: [8, 3, 1], 1: [1, 1, 1], 0: [1, 1, 1]}
    check("1. passi dei 3 giri: buco 8 → 4, 2, 1; buco 96 → 48, 7, 1 (esempi di P5) e altri",
          all(passi_zoom(b, 3) == p for b, p in casi.items()) and passi_zoom(8, 1) == [1]
          and passi_zoom(8, 4) == [4, 3, 2, 1], str({b: passi_zoom(b, 3) for b in casi}))
    canale = Asse("DONCHIAN.canale_barre", (16, 32, 48, 96, 192, 384), 1)
    sp = spazio_giro([canale], [{"DONCHIAN.canale_barre": 32}, {"DONCHIAN.canale_barre": 48}], 1, 3)
    valori = [canale.valore(sp.parametri[0].valore(i)) for i in range(sp.parametri[0].n)]
    check("2. primo giro da 32 e 48: da 32 meno 192 (dentro lo spazio: 16) a 48 + 192, passo 96, il reticolo parte da 32",
          valori == [32, 128, 224], str(valori))
    rng = np.random.default_rng(1)
    buoni = 0
    for _ in range(300):
        a = [canale, Asse("RSI.soglia", (15, 20, 25, 30, 35), 1), Asse("ATR.soglia", (0.8, 1.0, 1.2, 1.5), 0.1, True),
             Asse("X0.target", (None, 90), None)][int(rng.integers(4))]
        giro = int(rng.integers(1, 4))
        partenza = []
        for _ in range(int(rng.integers(1, 6))):
            if a.scelta:
                partenza.append({a.chiave: a.griglia[int(rng.integers(len(a.griglia)))]})
            else:
                partenza.append({a.chiave: a.valore(int(rng.integers(a.massimo + 1)))})
        p = spazio_giro([a], partenza, giro, 3).parametri[0]
        if a.scelta:
            buoni += set(p.valori) == {x[a.chiave] for x in partenza}
            continue
        u = [a.unita(x[a.chiave]) for x in partenza]
        passi = passi_zoom(a.buco, 3)
        largo = a.buco if giro == 1 else passi[giro - 2]
        buoni += (p.passo == passi[giro - 1] and (min(u) - p.minimo) % p.passo == 0 and p.minimo >= max(0, min(u) - largo)
                  and p.massimo <= min(a.massimo, max(u) + largo) and p.massimo + p.passo > min(a.massimo, max(u) + largo))
    check("3. 300 giri a caso: il minimo delle partenze sta sul reticolo, intervallo e passo come la regola, dentro lo "
          "spazio; per il target restano i valori delle partenze", buoni == 300, f"{buoni}/300")
    griglie = {"canale M15": ((16, 32, 48, 96, 192, 384), 1, False), "periodo RSI M15": ((8, 16, 24, 36, 48), 1, False),
               "soglia RSI": ((15, 20, 25, 30, 35), 1, False), "periodo ADX M15": ((16, 24, 36), 1, False),
               "durata M15": ((4, 8, 16, 32), 1, False), "percentile stop": ((70, 80, 90, 95), 1, False),
               "soglia ATR relativo": ((0.8, 1.0, 1.2, 1.5), 0.1, True), "ATR lungo M15": ((96, 192, 384), 1, False),
               "canale H4": ((1, 2, 3, 6, 12, 24), 1, False), "canale D1": ((1, 2, 4), 1, False)}
    totale, mancati = 0, {}
    for nome, (g, fine, reale) in griglie.items():
        n, m = _raggiungibili(g, fine, reale)
        totale += n
        if m:
            mancati[nome] = m[:5]
    check(f"4. ogni valore fine fra due punti della griglia larga è raggiungibile in 3 giri ({len(griglie)} griglie)",
          not mancati, f"{totale} valori provati, mancati {mancati}")

    contate, chiamate = [0], [0]

    def f_meta(punto):
        chiamate[0] += 1
        if punto["a"] % 2:                       # metà dei punti è «degenere»: non consuma il budget
            return math.nan, False
        contate[0] += 1
        return -abs(punto["a"] - 20) - abs(punto["b"] - 3), True

    spazio_ab = Spazio([Intero("a", 0, 40), Intero("b", 0, 9)])
    cerca(f_meta, spazio_ab, 30, 7, None)
    primi = (contate[0], chiamate[0])
    contate[0] = chiamate[0] = 0
    cerca(f_meta, spazio_ab, 30, 7, None)
    check("5. cerca: 30 prove contate esatte, i punti scartati non consumano il budget; stesso seme, stesse chiamate",
          primi[0] == 30 and primi[1] > 30 and (contate[0], chiamate[0]) == primi, f"contate {primi[0]}, chiamate {primi[1]}")
    contate[0] = chiamate[0] = 0
    cerca(f_meta, Spazio([Intero("a", 0, 5), Intero("b", 0, 2)]), 30, 7, None)
    check("6. cerca: se lo spazio finisce prima, si ferma (9 punti buoni su 18)", contate[0] == 9 and chiamate[0] == 18)

    # ------------------------------------------------------------------ l'altopiano
    print("\nL'altopiano: i vicini e il giudizio")

    def vicini_di(tf, blocco, valori, chiave):
        b = {x.nome: x for x in blocchi_da_config({"timeframe": tf, "blocchi": {blocco: {}, "X0": {}}})}
        teoria = Teoria(1, blocco, (), "X0") if b[blocco].tipo == "trigger" else Teoria(1, "DONCHIAN", (blocco,), "X0")
        if teoria.trigger == "DONCHIAN":
            b.update({x.nome: x for x in blocchi_da_config({"timeframe": tf, "blocchi": {"DONCHIAN": {}}})})
        v = {"X0": {"durata_barre": 4, "perc_stop": 90, "target": 90}, blocco: valori}
        if teoria.trigger == "DONCHIAN":
            v["DONCHIAN"] = {"canale_barre": 16}
        s = Strategia.da_teoria(teoria, {k: dict(x) for k, x in v.items()})
        return sorted(x[2] for x in vicini(s, b) if x[0] == chiave)

    def durata(tf, barre):
        b = {x.nome: x for x in blocchi_da_config({"timeframe": tf, "blocchi": {"E5": {}, "X0": {}}})}
        s = Strategia.da_teoria(Teoria(1, "E5", (), "X0"), {"X0": {"durata_barre": barre, "perc_stop": 90, "target": None}})
        return sorted(x[2] for x in vicini(s, b) if x[0] == "X0.durata_barre")

    tabella = {("M15", 4): [3, 5], ("M15", 8): [7, 9], ("M15", 16): [14, 18], ("M15", 32): [27, 37],
               ("H1", 1): [2], ("H1", 2): [1, 3], ("H1", 4): [3, 5], ("H1", 8): [7, 9],
               ("H4", 1): [2], ("H4", 2): [1, 3], ("D1", 1): [2]}
    sbagliati = {k: durata(*k) for k, atteso in tabella.items() if durata(*k) != atteso}
    check("7. la tabella dei vicini in ore (P5) rifatta: M15, H1, H4, D1, spostamento minimo di 1 barra", not sbagliati,
          str(sbagliati))
    check("8. periodo di RSI al minimo di 5 barre: resta solo il vicino sopra (H4 5 → 6; H1 6 → 5 e 7)",
          vicini_di("H4", "RSI_RIENTRO", {"periodo_barre": 5, "soglia": 25}, "RSI_RIENTRO.periodo_barre") == [6]
          and vicini_di("H1", "RSI_RIENTRO", {"periodo_barre": 6, "soglia": 25}, "RSI_RIENTRO.periodo_barre") == [5, 7])
    check("9. soglie e percentile: il valore adiacente della griglia; al bordo uno solo; fra due valori, quei due",
          vicini_di("M15", "RSI_RIENTRO", {"periodo_barre": 24, "soglia": 25}, "RSI_RIENTRO.soglia") == [20, 30]
          and vicini_di("M15", "RSI_RIENTRO", {"periodo_barre": 24, "soglia": 15}, "RSI_RIENTRO.soglia") == [20]
          and vicini_di("M15", "RSI_RIENTRO", {"periodo_barre": 24, "soglia": 22}, "RSI_RIENTRO.soglia") == [20, 25]
          and vicini_di("M15", "ATR_RELATIVO", {"breve_barre": 8, "lungo_barre": 192, "soglia": 1.1},
                        "ATR_RELATIVO.soglia") == [1.0, 1.2]
          and vicini_di("M15", "ATR_RELATIVO", {"breve_barre": 8, "lungo_barre": 192, "soglia": 1.5},
                        "ATR_RELATIVO.soglia") == [1.2]
          and vicini_di("M15", "ADX", {"periodo_barre": 24, "soglia": 30}, "X0.perc_stop") == [80, 95])
    b_x0 = {x.nome: x for x in blocchi_da_config({"timeframe": "M15", "blocchi": {"E5": {}, "X0": {}}})}
    s_x0 = Strategia.da_teoria(Teoria(1, "E5", (), "X0"), {"X0": {"durata_barre": 16, "perc_stop": 85, "target": 90}})
    chiavi = [x[0] for x in vicini(s_x0, b_x0)]
    check("10. il target non ha vicini; durata 16 e percentile 85 ne hanno due ciascuno",
          chiavi == ["X0.durata_barre"] * 2 + ["X0.perc_stop"] * 2, str(chiavi))

    def picco(larghezza):
        b = {x.nome: x for x in blocchi_da_config({"timeframe": "M15", "blocchi": {"DONCHIAN": {}, "X0": {}}})}
        s = Strategia.da_teoria(Teoria(1, "DONCHIAN", (), "X0"), {"DONCHIAN": {"canale_barre": 40},
                                                                   "X0": {"durata_barre": 16, "perc_stop": 90, "target": None}})

        def t(st):
            c, d = st.valori_di("DONCHIAN")["canale_barre"], st.valori_di("X0")["durata_barre"]
            return 10.0 * math.exp(-((c - 40) / larghezza) ** 2 - ((d - 16) / larghezza) ** 2)

        vic = [(t(Strategia.da_teoria(Teoria(1, "DONCHIAN", (), "X0"), v)), 5.0) for *_, v in vicini(s, b)]
        return giudica_altopiano(t(s), vic, SOGLIE_ALT)

    stretto, largo = picco(3.0), picco(60.0)
    check("11. picco stretto: il t crolla a ±15% sulle ore, non regge", not stretto["regge"], stretto["motivo"])
    check("12. picco largo: il t a ±15% resta alto, regge", largo["regge"] and largo["mediana"] > 9)
    check("13. un vicino con EV non positivo, un vicino non calcolabile, nessun vicino: non regge",
          not giudica_altopiano(10, [(9, 5), (9, -1)], SOGLIE_ALT)["regge"]
          and not giudica_altopiano(10, [(9, 5), (math.nan, 5)], SOGLIE_ALT)["regge"]
          and not giudica_altopiano(10, [], SOGLIE_ALT)["regge"]
          and giudica_altopiano(10, [(7, 1), (4, 1), (8, 1)], SOGLIE_ALT)["regge"]
          and not giudica_altopiano(10, [(9, 1), (3.9, 1), (9, 1)], SOGLIE_ALT)["regge"])

    with tempfile.TemporaryDirectory() as radice:
        F, R, P, S = (os.path.join(radice, x) for x in ("F", "R", "P", "S"))
        for c in (F, R, P, S):
            _dati(c)
        os.makedirs(os.path.join(F, "studio"))
        with open(os.path.join(F, "studio", "diario_pc.jsonl"), "w", encoding="utf-8") as f:
            f.write('{"prova": 1}\n')
        prima = _fotografia(F)

        # ------------------------------------------------------------------ una ricerca piccola
        print("\nUna ricerca piccola: 24 teorie, 4 al passo 2, giri da 30 prove")
        cfg = _config()
        e = lancia(cfg, F, verbose=False, data=DATA)
        r1, r2 = _jsonl(os.path.join(e.cartella, "passo_1.jsonl")), _jsonl(os.path.join(e.cartella, "passo_2.jsonl"))
        csv_f = pd.read_csv(registro.FileProve(e.cartella).percorso, dtype=str, keep_default_na=False)
        check("14. finita: config, passo 1, passo 2, prove e stato su disco",
              e.finita and all(os.path.exists(os.path.join(e.cartella, n)) for n in
                               ("config.json", "passo_1.jsonl", "passo_2.jsonl", "stato.json"))
              and json.load(open(os.path.join(e.cartella, "stato.json"), encoding="utf-8"))["fase"] == "finita",
              f"imbuto {e.imbuto}, {e.prove} prove, {e.durata_s:.0f} s")
        somma = sum(len(r["prove"]) for r in r1 + r2) + len(e.selezione.tabella)
        check("15. conteggio esatto: righe del file = prove dei passi e della selezione = conto dell'asset",
              len(csv_f) == somma == e.prove == registro.conto_prove(F, PERP, "M15"), f"{len(csv_f)}, {somma}, {e.prove}")
        check("16. ogni strategia una riga sola per pezzo (passo 1, giri e altopiano insieme; poi la selezione)",
              csv_f["id_strategia"][csv_f["pezzo"] == "ricerca"].is_unique
              and sorted(csv_f.loc[csv_f["pezzo"] == "selezione", "id_strategia"]) == sorted(e.sopravvissute["id_strategia"]))
        check("17. passo 1: al massimo 40 prove per teoria, esattamente min(40, punti ammessi)",
              all(len(r["prove"]) == min(40, r["punti_ammessi"]) for r in r1))
        giri_ok = all(g["prove"] <= 30 for r in r2 for g in r["giri"]) and all(r["prove_altopiano"] <= 60 for r in r2)
        check("18. budget mai superato: ogni giro ≤ 30, altopiano ≤ 60, totale ≤ budget massimo meno selezione e cassaforte",
              giri_ok and e.prove <= e.budget_massimo - 2 * 4, f"{e.prove} ≤ {e.budget_massimo - 8}")
        gia = sum(g["gia_viste"] for r in r2 for g in r["giri"])
        check("19. la stessa strategia in due giri: non si rivaluta e non si conta (già viste nei giri)", gia > 0
              and all(sum(1 for p in r["prove"] if p["fase"].startswith("zoom")) == r["prove_zoom"] for r in r2), f"{gia}")
        tenute = sorted((r for r in r1 if r["migliore"]), key=lambda r: (-r["t"], r["teoria"]))
        check("20. al passo 2 le 4 teorie tenute con il t più alto della migliore che passa la condizione 1",
              [r["teoria"] for r in r2] == [r["teoria"] for r in tenute[:4]]
              and all(next(p for p in r["prove"] if p["id"] == r["migliore"])["passa"] for r in tenute))
        bene = True
        for r in r2:
            storia = next(x for x in r1 if x["teoria"] == r["teoria"])["prove"]
            for g in r["giri"]:
                bene &= g["partenza"] == [x["id"] for x in _in_ordine(storia, 5)]
                storia = storia + [p for p in r["prove"] if p["fase"] == f"zoom_{g['giro']}"]
        check("21. ogni giro riparte dalle 5 strategie con il t più alto fra tutte quelle calcolabili fin lì", bene)
        bene = all(r["scelta"] is None or (r["scelta"]["passa"] and qualita_1_passa(r["scelta"], cfg)) for r in r2)
        prima_cand = all(not r["altopiano"] or r["altopiano"][0]["candidata"] == _in_ordine(
            next(x for x in r1 if x["teoria"] == r["teoria"])["prove"]
            + [p for p in r["prove"] if p["fase"].startswith("zoom")], 1, True)[0]["id"] for r in r2)
        check("22. altopiano: la prima candidata è la migliore che passa la condizione 1 dopo lo zoom; la scelta passa "
              "la condizione 1",
              bene and prima_cand)
        t_sel = e.selezione.tabella
        check("23. imbuto e tabelle coerenti", e.imbuto == {"teorie": 24, "passo_1_tenute": len(tenute), "passo_2": 4,
                                                            "altopiano": int((e.passo_2["esito"] == "regge").sum()),
                                                            "selezione": int((t_sel["esito"] != "scartata").sum()),
                                                            "scelte": int((t_sel["esito"] == "scelta").sum())}
              and len(e.sopravvissute) == e.imbuto["altopiano"], str(e.imbuto))
        eventi = registro.leggi_registro(cartella_asset(F, PERP, "M15"))
        avvio = [x for x in eventi if x["tipo"] == "avvio_ricerca"]
        fine = [x for x in eventi if x["tipo"] == "fine_ricerca"]
        check("24. registro: avvio con impronta della config, teorie e perché, famiglie misurate e dichiarate, degeneri "
              "all'avvio, budget", len(avvio) == 1 and avvio[0]["impronta_config"] == impronta_config(cfg)
              and avvio[0]["teorie"]["teorie"] == 24 and {"dichiarata", "gruppo_misurato", "famiglia"} <= set(avvio[0]["famiglie"][0])
              and avvio[0]["degeneri_avvio"] == e.degeneri_avvio and avvio[0]["budget_massimo"] == e.budget_massimo)
        check("25. registro: fine con imbuto, degeneri dello zoom, prove contate e soglia da leggere",
              len(fine) == 1 and fine[0]["imbuto"] == e.imbuto and fine[0]["prove"]["questa_ricerca"] == e.prove
              and fine[0]["prove"]["asset"] == e.prove and fine[0]["prove"]["soglia_da_leggere"] > 1.96
              and fine[0]["degeneri_zoom"] == e.degeneri_zoom)

        # ------------------------------------------------------------------ ripresa
        print("\nFermata a metà e ripresa")
        a = lancia(cfg, R, ferma_dopo=7, verbose=False, data=DATA)
        p1 = os.path.join(a.cartella, "passo_1.jsonl")
        with open(p1, "a", encoding="utf-8") as f:
            f.write('{"teoria": "L|DONCHIAN|-')                        # il PC si spegne a metà riga
        with open(registro.FileProve(a.cartella).percorso, "a", encoding="utf-8") as f:
            f.write(f"{a.id_ricerca},ricerca,passo_1,L|E47")
        b = lancia(cfg, R, ferma_dopo=19, verbose=False, data=DATA)
        c = lancia(cfg, R, verbose=False, data=DATA)
        check("26. fermata dopo 7 teorie, poi dopo altre 19 (dentro il passo 2), poi fino in fondo",
              not a.finita and len(a.passo_1) == 7 and not b.finita and len(b.passo_1) == 24 and len(b.passo_2) == 2
              and c.finita)
        check("27. ripresa = corsa unica, bit per bit: passo 1, passo 2 e file delle prove (righe a metà comprese)",
              _file(c) == _file(e))
        check("28. stesse tabelle e stesso conto delle prove", c.passo_1.equals(e.passo_1) and c.passo_2.equals(e.passo_2)
              and c.prove == e.prove and registro.conto_prove(R, PERP, "M15") == e.prove)
        ev_r = registro.leggi_registro(cartella_asset(R, PERP, "M15"))
        check("29. la ripresa non scrive un secondo avvio né una seconda fine",
              [x["tipo"] for x in ev_r] == ["avvio_ricerca", "fine_ricerca"])
        d = lancia(cfg, R, verbose=False, data=DATA)
        check("30. rilanciare una ricerca finita non aggiunge niente", _file(d) == _file(e)
              and len(registro.leggi_registro(cartella_asset(R, PERP, "M15"))) == 2)

        # ------------------------------------------------------------------ processi
        print("\n1 processo o 3")
        falsa = os.path.join(cartella_asset(P, PERP, "M15"), "20250101_falsa")
        registro.aggiungi_prove(falsa, [{"id_ricerca": "falsa", "pezzo": "ricerca", "fase": "passo_1", "teoria": "x",
                                         "id_strategia": f"s{i}", "trade": 1, "ev_bp": 1.0, "t": 1.0} for i in range(5)])
        cfg3 = _config(processi=3)
        tre = lancia(cfg3, P, verbose=False, data=DATA)
        f3, f1 = _file(tre), _file(e)
        stesse = f3["passo_1.jsonl"] == f1["passo_1.jsonl"] and f3["passo_2.jsonl"] == f1["passo_2.jsonl"]
        check("31. 3 processi = 1 processo: passo 1, passo 2 e prove identici, stesso id (i processi non stanno "
              "nell'impronta)", stesse and tre.id_ricerca == e.id_ricerca and f3["prove"] == f1["prove"]
              and tre.passo_2.equals(e.passo_2))
        check("32. con il conto alterato (5 prove di un'altra ricerca) gli esiti non cambiano: cambia solo il numero",
              stesse and registro.conto_prove(P, PERP, "M15") == tre.prove + 5)

        # ------------------------------------------------------------------ seme e due ricerche
        print("\nIl seme e due ricerche sullo stesso asset")
        istantanea = stato_registro()
        cfg1 = _config(seme=1)
        e1 = lancia(cfg1, F, verbose=False, data=DATA)
        q1 = {r["teoria"]: [p["id"] for p in r["prove"]] for r in r1}
        q2 = {r["teoria"]: [p["id"] for p in r["prove"]] for r in _jsonl(os.path.join(e1.cartella, "passo_1.jsonl"))}
        genetiche = [r["teoria"] for r in r1 if r["modo"] == "genetico"]
        check("33. seme diverso: il genetico prova altri punti; la griglia completa resta uguale",
              any(q1[t] != q2[t] for t in genetiche) and all(q1[r["teoria"]] == q2[r["teoria"]] for r in r1
                                                           if r["modo"] == "griglia completa"))
        check("34. due ricerche sullo stesso asset si sommano", registro.conto_prove(F, PERP, "M15") == e.prove + e1.prove,
              f"{e.prove} + {e1.prove}")
        check("35. registro delle condizioni identico prima e dopo una ricerca", stato_registro() == istantanea)
        dopo = _fotografia(F)
        nuovi = {tuple(os.path.relpath(os.path.join(r, n), F).split(os.sep)[:2]) for r, _, ns in os.walk(F) for n in ns}
        check("36. separazione: la cartella dello studio e i dati restano identici al bit; si scrive solo in "
              "fabbrica/<SYMBOL>_<TIMEFRAME>/", dopo == prima and all(x[0] != "fabbrica" or x[1] == f"{PERP}_M15"
                                                                       for x in nuovi), str(sorted(set(dopo) ^ set(prima))))

        # ------------------------------------------------------------------ le combinazioni degeneri
        print("\nLe combinazioni degeneri")
        pezzi = carica_pezzi(PERP, "M15", Confini.da_config(CONFINI), S)
        prep = prepara(cfg, pezzi)
        # una griglia di RSI che arriva alla soglia 3: le soglie basse su un RSI lungo non scattano quasi mai
        cfg_deg = _config()
        cfg_deg["blocchi"]["RSI_RIENTRO"] = {"periodo_ore": [2, 12], "soglia": [3, 35]}
        lav = prepara(cfg_deg, pezzi).lavoro
        rsi = lav.per_nome["RSI_RIENTRO"]
        trovata = None
        for periodo, soglia in itertools.product(range(47, 37, -1), (4, 5, 6)):
            if periodo not in rsi.griglia["periodo_barre"] and lav.controllo.degenere(rsi, 1, {"periodo_barre": periodo,
                                                                                               "soglia": soglia}):
                trovata = {"periodo_barre": periodo, "soglia": soglia}
                break
        teoria_rsi = Teoria(1, "RSI_RIENTRO", (), "X0")
        pt = _ProveTeoria(lav, teoria_rsi)
        uscita = {"durata_barre": 16, "perc_stop": 90, "target": None}
        t_deg, contata = pt.valuta({"RSI_RIENTRO": dict(trovata or {}), "X0": dict(uscita)}, "zoom_2") if trovata else (0, True)
        check("37. una combinazione nuova (fuori dalla griglia) degenere: si scarta, si annota, non conta",
              trovata is not None and math.isnan(t_deg) and not contata and not pt.nuove and len(pt.degeneri) == 1
              and next(iter(pt.degeneri.values()))["esito"] in ("RARA", "SEMPRE_FALSA"), str(trovata))
        t_ok, contata_ok = pt.valuta({"RSI_RIENTRO": {"periodo_barre": 25, "soglia": 26}, "X0": dict(uscita)}, "zoom_2")
        check("38. una combinazione nuova buona passa da verifica_degenerazione e conta una prova",
              contata_ok and len(pt.nuove) == 1 and (rsi.nome, 1, (("periodo_barre", 25), ("soglia", 26)))
              in lav.controllo._esiti)
        tolte = {(n, l): (c[1:] if n == "RSI_RIENTRO" and l == 1 else c) for (n, l), c in prep.rimaste.items()}
        lav_t = _Lavoro(cfg, prep.df, prep.costi, tolte, cache=prep.lavoro.cache, controllo=prep.lavoro.controllo)
        ris = lav_t.passo_1(teoria_rsi)
        via = prep.rimaste[("RSI_RIENTRO", 1)][0]
        check("39. passo 1: un punto tolto all'avvio come degenere non consuma una delle 40 prove",
              len(ris["prove"]) == 40 and ris["degeneri_proposti"] > 0
              and all(p["valori"]["RSI_RIENTRO"] != via for p in ris["prove"]), f"{ris['degeneri_proposti']} proposti")

        # ------------------------------------------------------------------ il vantaggio piantato
        print("\nIl vantaggio piantato, ridotto: DONCHIAN long a 40 barre, uscita dopo 12")
        V = os.path.join(radice, "V")
        df_v = sintetici.mercato_piantato(BARRE, seme=5, minuti=15, inizio="2024-01-01", prezzo=2_000.0)
        sintetici.scrivi_storico(V, SPOT, "M15", df_v)
        cfg_v = config_standard(SPOT, "M15", seme=0, processi=1)
        cfg_v["confini"] = dict(CONFINI)
        cfg_v["blocchi"] = {k: v for k, v in cfg_v["blocchi"].items() if k in ("E47", "DONCHIAN", "RSI_RIENTRO",
                                                                                "F3_VOLUME_ABOVE_AVG", "X0")}
        cfg_v["qualita_1"]["trade_min"] = 30
        cfg_v["budget"].update({"teorie_passo_2": 2, "prove_per_giro": 60})
        ev = lancia(cfg_v, V, verbose=False, data=DATA)
        primo = ev.sopravvissute.iloc[0] if len(ev.sopravvissute) else None
        valori_v = json.loads(primo["valori"]) if primo is not None else {}
        canale_v = valori_v.get("DONCHIAN", {}).get("canale_barre")
        durata_v = valori_v.get("X0", {}).get("durata_barre")
        check("40. la teoria in cima è DONCHIAN long; lo zoom porta canale e durata vicino a 40 e 12, fuori dalla griglia "
              "larga", primo is not None and primo["teoria"].startswith("L|DONCHIAN|") and canale_v is not None
              and abs(canale_v - 40) <= 8 and canale_v not in (32, 48) and abs(durata_v - 12) <= 2,
              f"{primo['teoria'] if primo is not None else '-'}: canale {canale_v}, durata {durata_v}")

    print("\n" + "=" * 70)
    print(f"Durata: {time.perf_counter() - t0:.0f} s")
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


def qualita_1_passa(riga, cfg) -> bool:
    """La condizione 1 rifatta dalle misure scritte nella riga."""
    from engine.fabbrica.valutatore import Misure
    m = Misure(*(riga[k] for k in ("trade", "totale_bp", "ev_bp", "t", "dd_bp", "peso_max", "totale_su_dd")))
    return qualita_1(m, cfg["qualita_1"])[0]


if __name__ == "__main__":
    sys.exit(esegui())
