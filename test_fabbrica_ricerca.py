"""
Suite di collaudo della ricerca della fabbrica (docs/82 P4, P5, P7, lavoro L3b; C2, docs/82 §11.7): passo 1 in due
turni, zoom, altopiano, ripresa.

Si lancia da terminale, dalla cartella del progetto:

    python test_fabbrica_ricerca.py

Solo dati sintetici (engine/fabbrica/sintetici.py), scritti in cartelle temporanee: non servono i file in dati/,
MetaTrader 5 o internet. Usa 3 processi per alcuni collaudi. Stampa una riga per collaudo e alla fine
«RISULTATO: n/n test superati». Dura qualche minuto.
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
from engine.fabbrica.config import budget_massimo, cartella_asset, config_standard, impronta_config
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
BLOCCHI_PICCOLI = ("E47", "DONCHIAN", "RSI_RIENTRO", "F3_VOLUME_ABOVE_AVG", "ADX", "ATR_RELATIVO", "X0")
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
    cfg["budget"].update({"teorie_turno_2": 3, "teorie_passo_2": 4, "prove_per_giro": 30})
    return cfg


def _leggi(percorso):
    with open(percorso, "rb") as f:
        return f.read()


def _jsonl(percorso):
    with open(percorso, encoding="utf-8") as f:
        return [json.loads(r) for r in f.read().splitlines()]


def _file(esito):
    return {n: _leggi(os.path.join(esito.cartella, n)) for n in ("passo_1.jsonl", "turno_2.jsonl", "passo_2.jsonl")} | {
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
        print("\nUna ricerca piccola in due turni: turno 1 di 16 teorie, turno 2 dalle 3 T+F migliori, 4 allo zoom")
        cfg = _config()
        e = lancia(cfg, F, verbose=False, data=DATA)
        r1, r2 = _jsonl(os.path.join(e.cartella, "passo_1.jsonl")), _jsonl(os.path.join(e.cartella, "passo_2.jsonl"))
        rt2 = _jsonl(os.path.join(e.cartella, "turno_2.jsonl"))
        csv_f = pd.read_csv(registro.FileProve(e.cartella).percorso, dtype=str, keep_default_na=False)
        check("14. finita: config, turno 1, turno 2, passo 2, prove e stato su disco",
              e.finita and all(os.path.exists(os.path.join(e.cartella, n)) for n in
                               ("config.json", "passo_1.jsonl", "turno_2.jsonl", "passo_2.jsonl", "stato.json"))
              and json.load(open(os.path.join(e.cartella, "stato.json"), encoding="utf-8"))["fase"] == "finita",
              f"imbuto {e.imbuto}, {e.prove} prove, {e.durata_s:.0f} s")
        somma = sum(len(r["prove"]) for r in r1 + rt2 + r2) + len(e.selezione.tabella)
        check("15. conteggio esatto: righe del file = prove dei due turni, del passo 2 e della selezione = conto dell'asset",
              len(csv_f) == somma == e.prove == registro.conto_prove(F, PERP, "M15"), f"{len(csv_f)}, {somma}, {e.prove}")
        fasi = csv_f["fase"].value_counts().to_dict()
        check("16. ogni prova del turno 2 nel conto con la fase «passo_1_turno_2», quelle del turno 1 con «passo_1»; ogni "
              "strategia una riga sola per pezzo", fasi.get("passo_1_turno_2") == sum(len(r["prove"]) for r in rt2) > 0
              and fasi.get("passo_1") == sum(len(r["prove"]) for r in r1)
              and all(p["fase"] == "passo_1_turno_2" for r in rt2 for p in r["prove"])
              and csv_f["id_strategia"][csv_f["pezzo"] == "ricerca"].is_unique
              and sorted(csv_f.loc[csv_f["pezzo"] == "selezione", "id_strategia"]) == sorted(e.sopravvissute["id_strategia"]),
              str(fasi))
        check("17. passo 1, nei due turni: al massimo 40 prove per teoria, esattamente min(40, punti ammessi)",
              all(len(r["prove"]) == min(40, r["punti_ammessi"]) for r in r1 + rt2))
        giri_ok = all(g["prove"] <= 30 for r in r2 for g in r["giri"]) and all(r["prove_altopiano"] <= 60 for r in r2)
        check("18. budget mai superato: ogni giro ≤ 30, altopiano ≤ 60, totale ≤ budget massimo meno selezione e "
              "cassaforte; il budget massimo con la formula nuova (turno 2 compreso)",
              giri_ok and e.prove <= e.budget_massimo - 2 * 4
              and e.budget_massimo == budget_massimo(16, cfg, 12, 3) == (16 + 3 * 2) * 40 + 4 * 90 + 4 * 60 + 8,
              f"{e.prove} ≤ {e.budget_massimo - 8}")
        gia = sum(g["gia_viste"] for r in r2 for g in r["giri"])
        check("19. la stessa strategia in due giri: non si rivaluta e non si conta (già viste nei giri)", gia > 0
              and all(sum(1 for p in r["prove"] if p["fase"].startswith("zoom")) == r["prove_zoom"] for r in r2), f"{gia}")
        tf = sorted((r for r in r1 if r["migliore"] and r["teoria"].split("|")[2] not in ("-",)),
                    key=lambda r: (-r["t"], r["teoria"]))
        attese_t2 = []
        for r in tf[:3]:
            lato, trig, f1, u = r["teoria"].split("|")
            for f2 in ("F3_VOLUME_ABOVE_AVG", "ADX", "ATR_RELATIVO"):
                if f2 != f1 and {f1, f2} != {"ADX", "ATR_RELATIVO"}:
                    filtri = [x for x in ("F3_VOLUME_ABOVE_AVG", "ADX", "ATR_RELATIVO") if x in (f1, f2)]
                    attese_t2.append(f"{lato}|{trig}|{'+'.join(filtri)}|{u}")
        attese_t2 = list(dict.fromkeys(attese_t2))
        check("20. turno 2: le 3 teorie T+F tenute con il t più alto (i due lati insieme), ognuna con tutti i secondi filtri "
              "compatibili, mai ADX con ATR relativo, i doppi tolti", [r["teoria"] for r in rt2] == attese_t2
              and len(tf) > 3, f"{[r['teoria'] for r in rt2]}")
        tenute = sorted((r for r in r1 + rt2 if r["migliore"]), key=lambda r: (-r["t"], r["teoria"]))
        check("21. allo zoom le 4 teorie tenute dei due turni con il t più alto della migliore che passa la condizione 1",
              [r["teoria"] for r in r2] == [r["teoria"] for r in tenute[:4]]
              and all(next(p for p in r["prove"] if p["id"] == r["migliore"])["passa"] for r in tenute),
              f"{[r['teoria'] for r in r2]}")
        bene = True
        for r in r2:
            storia = next(x for x in r1 + rt2 if x["teoria"] == r["teoria"])["prove"]
            for g in r["giri"]:
                bene &= g["partenza"] == [x["id"] for x in _in_ordine(storia, 5)]
                storia = storia + [p for p in r["prove"] if p["fase"] == f"zoom_{g['giro']}"]
        check("22. ogni giro riparte dalle 5 strategie con il t più alto fra tutte quelle calcolabili fin lì", bene)
        bene = all(r["scelta"] is None or (r["scelta"]["passa"] and qualita_1_passa(r["scelta"], cfg)) for r in r2)
        prima_cand = all(not r["altopiano"] or r["altopiano"][0]["candidata"] == _in_ordine(
            next(x for x in r1 + rt2 if x["teoria"] == r["teoria"])["prove"]
            + [p for p in r["prove"] if p["fase"].startswith("zoom")], 1, True)[0]["id"] for r in r2)
        check("23. altopiano: la prima candidata è la migliore che passa la condizione 1 dopo lo zoom; la scelta passa "
              "la condizione 1", bene and prima_cand)
        t_sel = e.selezione.tabella
        check("24. imbuto e tabelle coerenti, con i due turni",
              e.imbuto == {"turno_1": 16, "turno_1_tenute": sum(1 for r in r1 if r["migliore"]), "turno_2": len(rt2),
                           "turno_2_tenute": sum(1 for r in rt2 if r["migliore"]), "passo_2": 4,
                           "altopiano": int((e.passo_2["esito"] == "regge").sum()),
                           "selezione": int((t_sel["esito"] != "scartata").sum()),
                           "scelte": int((t_sel["esito"] == "scelta").sum())}
              and len(e.sopravvissute) == e.imbuto["altopiano"]
              and list(e.passo_1["turno"]) == [1] * 16 + [2] * len(rt2), str(e.imbuto))
        eventi = registro.leggi_registro(cartella_asset(F, PERP, "M15"))
        avvio = [x for x in eventi if x["tipo"] == "avvio_ricerca"]
        fine = [x for x in eventi if x["tipo"] == "fine_ricerca"]
        tt = {(x["lato"], x["blocco"]): x for x in e.tenuti_tolti}
        check("25. registro: avvio con impronta della config, teorie e perché, famiglie misurate, tenuti e tolti, degeneri "
              "all'avvio, budget", len(avvio) == 1 and avvio[0]["impronta_config"] == impronta_config(cfg)
              and avvio[0]["teorie"]["teorie"] == 16 and {"dichiarata", "gruppo_misurato", "famiglia"} <= set(avvio[0]["famiglie"][0])
              and avvio[0]["tenuti_tolti"] == json.loads(registro.json_riga(e.tenuti_tolti))
              and tt[("long", "E47")]["esito"] == "tolto" and tt[("long", "DONCHIAN")]["esito"] == "tenuto"
              and avvio[0]["degeneri_avvio"] == e.degeneri_avvio and avvio[0]["budget_massimo"] == e.budget_massimo)
        check("26. registro: fine con imbuto, degeneri dello zoom, prove contate e soglia da leggere",
              len(fine) == 1 and fine[0]["imbuto"] == e.imbuto and fine[0]["prove"]["questa_ricerca"] == e.prove
              and fine[0]["prove"]["asset"] == e.prove and fine[0]["prove"]["soglia_da_leggere"] > 1.96
              and fine[0]["degeneri_zoom"] == e.degeneri_zoom)

        # ------------------------------------------------------------------ ripresa
        print("\nFermata a metà e ripresa: nel turno 1, nel turno 2, nello zoom")
        a = lancia(cfg, R, ferma_dopo=7, verbose=False, data=DATA)
        p1 = os.path.join(a.cartella, "passo_1.jsonl")
        with open(p1, "a", encoding="utf-8") as f:
            f.write('{"teoria": "L|DONCHIAN|-')                        # il PC si spegne a metà riga
        with open(registro.FileProve(a.cartella).percorso, "a", encoding="utf-8") as f:
            f.write(f"{a.id_ricerca},ricerca,passo_1,L|E47")
        b = lancia(cfg, R, ferma_dopo=10, verbose=False, data=DATA)    # 9 del turno 1 e la prima del turno 2
        with open(os.path.join(b.cartella, "turno_2.jsonl"), "a", encoding="utf-8") as f:
            f.write('{"teoria": "S|DONCHIAN|F3')                        # anche nel turno 2
        b2 = lancia(cfg, R, ferma_dopo=4, verbose=False, data=DATA)    # il resto del turno 2 e il primo dello zoom
        c = lancia(cfg, R, verbose=False, data=DATA)
        check("27. fermata dopo 7 teorie, poi dentro il turno 2, poi dentro lo zoom, poi fino in fondo",
              not a.finita and len(a.passo_1) == 7 and not b.finita and len(b.passo_1) == 16 + 1
              and not b2.finita and len(b2.passo_2) == 2 and c.finita,
              f"{len(a.passo_1)}, {len(b.passo_1)}, {len(b2.passo_1)} e {len(b2.passo_2)}")
        check("28. ripresa = corsa unica, bit per bit: turno 1, turno 2, passo 2 e file delle prove (righe a metà comprese)",
              _file(c) == _file(e))
        check("29. stesse tabelle e stesso conto delle prove", c.passo_1.equals(e.passo_1) and c.passo_2.equals(e.passo_2)
              and c.prove == e.prove and registro.conto_prove(R, PERP, "M15") == e.prove and c.imbuto == e.imbuto)
        ev_r = registro.leggi_registro(cartella_asset(R, PERP, "M15"))
        check("30. la ripresa non scrive un secondo avvio né una seconda fine",
              [x["tipo"] for x in ev_r] == ["avvio_ricerca", "fine_ricerca"])
        d = lancia(cfg, R, verbose=False, data=DATA)
        check("31. rilanciare una ricerca finita non aggiunge niente", _file(d) == _file(e)
              and len(registro.leggi_registro(cartella_asset(R, PERP, "M15"))) == 2)

        # ------------------------------------------------------------------ processi
        print("\n1 processo o 3")
        falsa = os.path.join(cartella_asset(P, PERP, "M15"), "20250101_falsa")
        registro.aggiungi_prove(falsa, [{"id_ricerca": "falsa", "pezzo": "ricerca", "fase": "passo_1", "teoria": "x",
                                         "id_strategia": f"s{i}", "trade": 1, "ev_bp": 1.0, "t": 1.0} for i in range(5)])
        cfg3 = _config(processi=3)
        tre = lancia(cfg3, P, verbose=False, data=DATA)
        f3, f1 = _file(tre), _file(e)
        stesse = all(f3[n] == f1[n] for n in ("passo_1.jsonl", "turno_2.jsonl", "passo_2.jsonl"))
        check("32. 3 processi = 1 processo: turno 1, turno 2, passo 2 e prove identici, stesso id (i processi non stanno "
              "nell'impronta)", stesse and tre.id_ricerca == e.id_ricerca and f3["prove"] == f1["prove"]
              and tre.passo_2.equals(e.passo_2))
        check("33. con il conto alterato (5 prove di un'altra ricerca) gli esiti non cambiano: cambia solo il numero",
              stesse and registro.conto_prove(P, PERP, "M15") == tre.prove + 5)

        # ------------------------------------------------------------------ seme e due ricerche
        print("\nIl seme e due ricerche sullo stesso asset")
        istantanea = stato_registro()
        cfg1 = _config(seme=1)
        e1 = lancia(cfg1, F, verbose=False, data=DATA)
        q1 = {r["teoria"]: [p["id"] for p in r["prove"]] for r in r1}
        q2 = {r["teoria"]: [p["id"] for p in r["prove"]] for r in _jsonl(os.path.join(e1.cartella, "passo_1.jsonl"))}
        genetiche = [r["teoria"] for r in r1 if r["modo"] == "genetico"]
        check("34. seme diverso: il genetico prova altri punti; la griglia completa resta uguale",
              any(q1[t] != q2[t] for t in genetiche) and all(q1[r["teoria"]] == q2[r["teoria"]] for r in r1
                                                           if r["modo"] == "griglia completa"))
        check("35. due ricerche sullo stesso asset si sommano", registro.conto_prove(F, PERP, "M15") == e.prove + e1.prove,
              f"{e.prove} + {e1.prove}")
        check("36. registro delle condizioni identico prima e dopo una ricerca", stato_registro() == istantanea)
        dopo = _fotografia(F)
        nuovi = {tuple(os.path.relpath(os.path.join(r, n), F).split(os.sep)[:2]) for r, _, ns in os.walk(F) for n in ns}
        check("37. separazione: la cartella dello studio e i dati restano identici al bit; si scrive solo in "
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
        check("38. una combinazione nuova (fuori dalla griglia) degenere: si scarta, si annota, non conta",
              trovata is not None and math.isnan(t_deg) and not contata and not pt.nuove and len(pt.degeneri) == 1
              and next(iter(pt.degeneri.values()))["esito"] in ("RARA", "SEMPRE_FALSA"), str(trovata))
        t_ok, contata_ok = pt.valuta({"RSI_RIENTRO": {"periodo_barre": 25, "soglia": 26}, "X0": dict(uscita)}, "zoom_2")
        check("39. una combinazione nuova buona passa da verifica_degenerazione e conta una prova",
              contata_ok and len(pt.nuove) == 1 and (rsi.nome, 1, (("periodo_barre", 25), ("soglia", 26)))
              in lav.controllo._esiti)
        tolte = {(n, l): (c[1:] if n == "RSI_RIENTRO" and l == 1 else c) for (n, l), c in prep.rimaste.items()}
        lav_t = _Lavoro(cfg, prep.df, prep.costi, tolte, cache=prep.lavoro.cache, controllo=prep.lavoro.controllo)
        ris = lav_t.passo_1(teoria_rsi)
        via = prep.rimaste[("RSI_RIENTRO", 1)][0]
        check("40. passo 1: un punto tolto all'avvio come degenere non consuma una delle 40 prove",
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
        cfg_v["budget"].update({"teorie_turno_2": 2, "teorie_passo_2": 2, "prove_per_giro": 60})
        ev = lancia(cfg_v, V, verbose=False, data=DATA)
        primo = ev.sopravvissute.iloc[0] if len(ev.sopravvissute) else None
        valori_v = json.loads(primo["valori"]) if primo is not None else {}
        canale_v = valori_v.get("DONCHIAN", {}).get("canale_barre")
        durata_v = valori_v.get("X0", {}).get("durata_barre")
        check("41. la teoria in cima è DONCHIAN long; lo zoom porta canale e durata vicino a 40 e 12, fuori dalla griglia "
              "larga", primo is not None and primo["teoria"].startswith("L|DONCHIAN|") and canale_v is not None
              and abs(canale_v - 40) <= 8 and canale_v not in (32, 48) and abs(durata_v - 12) <= 2,
              f"{primo['teoria'] if primo is not None else '-'}: canale {canale_v}, durata {durata_v}")

        # ------------------------------------------------------------------ C2: la config standard, tutto il catalogo
        print("\nC2: la config standard, tutto il catalogo, con budget ridotti")
        S2 = os.path.join(radice, "S2")
        df_s = sintetici.mercato(BARRE, seme=3, minuti=15, inizio="2024-01-01", prezzo=30_000.0)
        sintetici.scrivi_storico(S2, PERP, "M15", df_s)
        sintetici.scrivi_funding(S2, PERP, df_s, seme=3)
        cfg_s = config_standard(PERP, "M15", seme=0, processi=1)
        cfg_s["confini"] = dict(CONFINI)
        cfg_s["qualita_1"]["trade_min"] = 30
        cfg_s["budget"].update({"per_teoria_passo_1": 2, "teorie_turno_2": 3, "teorie_passo_2": 2, "giri_zoom": 1,
                                "prove_per_giro": 5})
        cfg_s["altopiano"]["prove_max"] = 4
        es = lancia(cfg_s, S2, verbose=False, data=DATA)
        res = es.resoconto["blocchi"]
        filtri_max = max(res[x]["filtro"]["tenuti"] for x in res)
        tf_s = sum(1 for t in es.passo_1.itertuples() if t.turno == 1 and "|-|" not in t.teoria)
        check("42. config standard con tutto il catalogo (45 trigger e 30 filtri sul long, 44 e 30 sullo short): un blocco "
              "per famiglia, turno 1 = trigger × (1 + filtri) × 3 per lato, budget massimo con la formula nuova, tetto "
              "rispettato, prove sotto il massimo", es.finita
              and res["long"]["trigger"]["blocchi"] == 45 and res["short"]["trigger"]["blocchi"] == 44
              and es.imbuto["turno_1"] == sum(res[x]["trigger"]["tenuti"] * (1 + res[x]["filtro"]["tenuti"]) * 3
                                              for x in res)
              and es.budget_massimo == budget_massimo(es.imbuto["turno_1"], cfg_s, tf_s, filtri_max)
              and es.budget_massimo <= cfg_s["budget"]["totale"] and es.prove <= es.budget_massimo
              and 0 < es.imbuto["turno_2"] <= 3 * (filtri_max - 1),
              f"imbuto {es.imbuto}, prove {es.prove} di {es.budget_massimo}, tetto {cfg_s['budget']['totale']}")

        # ------------------------------------------------------------------ C2 su più timeframe (docs/82 §11.7)
        n = 43
        for symbol, tf, minuti, confini in CASI_TF:
            n = _caso_timeframe(check, radice, symbol, tf, minuti, confini, n)

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


# ------------------------------------------------------------------ C2 su più timeframe (docs/82 §11.7)
# Barre sintetiche su M15, M5 e H1 (perpetual) e uno spot (solo long), con la config standard intera (tutto il catalogo
# ammesso sul timeframe) e budget ridotti. Su ogni caso: esclusioni per timeframe con il motivo, famiglie e tenuti,
# turno 1 e turno 2, conto delle prove, ripresa dopo una fermata = corsa unica, 1 processo = 3, cassaforte sigillata.
CASI_TF = (
    (PERP, "M15", 15, {"inizio": "2024-01-01 00:00", "ricerca_ore": 3000, "selezione_ore": 1200, "cassaforte_ore": 600}),
    (PERP, "M5", 5, {"inizio": "2024-01-01 00:00", "ricerca_ore": 1500, "selezione_ore": 700, "cassaforte_ore": 300}),
    (PERP, "H1", 60, {"inizio": "2024-01-01 00:00", "ricerca_ore": 9000, "selezione_ore": 4000, "cassaforte_ore": 2000}),
    (SPOT, "M15", 15, {"inizio": "2024-01-01 00:00", "ricerca_ore": 3000, "selezione_ore": 1200, "cassaforte_ore": 600}),
)


def _cfg_tf(symbol, tf, confini, processi=1):
    cfg = config_standard(symbol, tf, seme=0, processi=processi)
    cfg["confini"] = dict(confini)
    cfg["qualita_1"]["trade_min"] = 30
    cfg["budget"].update({"per_teoria_passo_1": 1, "teorie_turno_2": 3, "teorie_passo_2": 2, "giri_zoom": 1,
                          "prove_per_giro": 5})
    cfg["altopiano"]["prove_max"] = 4
    return cfg


def _scrivi_tf(cartella, symbol, tf, minuti, confini, veleno=False):
    n = int(sum(confini[k] for k in ("ricerca_ore", "selezione_ore", "cassaforte_ore")) * 60 / minuti) + 100
    df = sintetici.mercato_piantato(n, seme=5, minuti=minuti, inizio="2024-01-01", prezzo=30_000.0)
    if veleno:                       # la cassaforte avvelenata: prezzi × 3, volume 1
        dentro = df.index >= Confini.da_config(confini).tratto_cassaforte[0]
        df.loc[dentro, ["Open", "High", "Low", "Close"]] *= 3.0
        df.loc[dentro, "Volume"] = 1.0
    sintetici.scrivi_storico(cartella, symbol, tf, df)
    if "_PERP_" in symbol:
        sintetici.scrivi_funding(cartella, symbol, df, seme=5)


def _file_ricerca(esito) -> dict:
    """{nome: sha256} di ogni file nella cartella della ricerca (config, turni, passo 2, prove, selezione, stato)."""
    return {n: hashlib.sha256(_leggi(os.path.join(esito.cartella, n))).hexdigest() for n in sorted(os.listdir(esito.cartella))}


def _caso_timeframe(check, radice, symbol, tf, minuti, confini, n) -> int:
    from engine.fabbrica.blocchi import MOTIVI_ESCLUSIONE
    from engine.fabbrica.config import BLOCCHI_STANDARD, blocchi_esclusi
    from engine.fabbrica.generatore import QUATTORDICI, teorie_turno_2
    from engine.fabbrica.schede import esclusi_dalla_config
    nome = f"{symbol} {tf}"
    print(f"\nC2 su {nome}: config standard intera, budget ridotti")
    cartelle = {k: os.path.join(radice, f"tf_{symbol}_{tf}_{k}") for k in ("A", "R", "P", "W")}
    for k, c in cartelle.items():
        _scrivi_tf(c, symbol, tf, minuti, confini, veleno=(k == "W"))
    cfg = _cfg_tf(symbol, tf, confini)
    e = lancia(cfg, cartelle["A"], verbose=False, data=DATA)

    esclusi = blocchi_esclusi(tf)
    fuori = {x["blocco"] for x in esclusi}
    righe = pd.DataFrame(e.tenuti_tolti)
    check(f"{n}. {nome}: i blocchi esclusi sul timeframe ({len(esclusi)}) stanno fuori dalla config, ognuno con il suo "
          "motivo; la scheda li elenca uguali; nessuno di loro nella tabella dei tenuti",
          set(cfg["blocchi"]) == set(BLOCCHI_STANDARD) - fuori
          and all((x["blocco"], tf) in MOTIVI_ESCLUSIONE and x["motivo"] for x in esclusi)
          and esclusi_dalla_config(cfg) == esclusi and not (set(righe["blocco"]) & fuori),
          ", ".join(sorted(fuori)) or "nessuno")
    vivi = righe[righe["famiglia"].notna()]
    regola = []
    for _, g in vivi.groupby(["lato", "tipo", "famiglia"]):
        pool = g[g["blocco"].isin(QUATTORDICI)]
        pool = pool if len(pool) else g
        regola.append(list(g[g["esito"] == "tenuto"]["blocco"]) == [sorted(zip(-pool["scatta"], pool["blocco"]))[0][1]])
    res = e.resoconto["blocchi"]
    lati = ["long"] if symbol == SPOT else ["long", "short"]
    check(f"{n + 1}. {nome}: famiglie e tenuti: un blocco per famiglia misurata, con la regola; i tolti hanno il motivo; "
          f"lati {lati}; E19 solo long", all(regola) and sorted(set(righe["lato"])) == sorted(lati)
          and list(res) == lati and all(righe["motivo"].str.len() > 0)
          and not len(righe[(righe["blocco"] == "E19") & (righe["lato"] == "short")])
          and all(res[x][t]["tenuti"] == int(((righe["lato"] == x) & (righe["tipo"] == t)
                                              & (righe["esito"] == "tenuto")).sum()) for x in lati
                  for t in ("trigger", "filtro")),
          "; ".join(f"{x}: {res[x]['trigger']['blocchi']} trigger → {res[x]['trigger']['tenuti']}, "
                    f"{res[x]['filtro']['blocchi']} filtri → {res[x]['filtro']['tenuti']}" for x in lati))
    p1 = e.passo_1
    t1 = p1[p1["turno"] == 1]
    tf_tenute = t1[t1["tenuta"] & ~t1["teoria"].str.contains(r"\|-\|") & ~t1["teoria"].str.contains(r"\+")]
    scelte = [Teoria(1 if t.startswith("L") else -1, t.split("|")[1], (t.split("|")[2],), t.split("|")[3])
              for t in tf_tenute.sort_values(["t", "teoria"], ascending=[False, True])["teoria"][:3]]
    attese = [t.id for t in teorie_turno_2(scelte, cfg, blocchi_da_config(cfg), {
        (1 if x == "long" else -1): list(righe[(righe["lato"] == x) & (righe["esito"] == "tenuto")]["blocco"])
        for x in lati})]
    t2 = list(p1[p1["turno"] == 2]["teoria"])
    check(f"{n + 2}. {nome}: turno 1 = trigger tenuti × (1 + filtri tenuti) × 3 uscite; turno 2 = le 3 T+F migliori con "
          "tutti i secondi filtri compatibili, mai ADX con ATR relativo; tutte dei lati della ricerca",
          e.imbuto["turno_1"] == len(t1) == sum(res[x]["trigger"]["tenuti"] * (1 + res[x]["filtro"]["tenuti"]) * 3
                                                for x in lati)
          and t2 == attese and len(t2) > 0 and not any("ADX" in t and "ATR_RELATIVO" in t for t in t2)
          and all(t[0] in "".join(x[0].upper() for x in lati) for t in p1["teoria"]),
          f"turno 1 {len(t1)} teorie, turno 2 {len(t2)}")
    csv_f = pd.read_csv(registro.FileProve(e.cartella).percorso, dtype=str, keep_default_na=False)
    fasi = csv_f["fase"].value_counts().to_dict()
    check(f"{n + 3}. {nome}: conto delle prove esatto (turno 1, turno 2 con la sua fase, zoom, altopiano, selezione) = "
          "conto dell'asset; sotto il budget massimo, che sta sotto il tetto",
          e.finita and len(csv_f) == e.prove == registro.conto_prove(cartelle["A"], symbol, tf)
          and fasi.get("passo_1") == int(t1["prove"].sum())
          and fasi.get("passo_1_turno_2", 0) == int(p1[p1["turno"] == 2]["prove"].sum())
          and e.prove <= e.budget_massimo <= cfg["budget"]["totale"], f"{e.prove} prove, {fasi}")
    a = lancia(cfg, cartelle["R"], ferma_dopo=e.imbuto["turno_1"] + max(1, e.imbuto["turno_2"] // 2), verbose=False,
               data=DATA)
    b = lancia(cfg, cartelle["R"], verbose=False, data=DATA)
    tre = lancia(_cfg_tf(symbol, tf, confini, processi=3), cartelle["P"], verbose=False, data=DATA)
    check(f"{n + 4}. {nome}: fermata a metà del turno 2 e ripresa = corsa unica, bit per bit; 3 processi = 1 processo "
          "(turni, zoom, prove, selezione, stato)",
          not a.finita and len(a.passo_1) < e.imbuto["turno_1"] + e.imbuto["turno_2"] and b.finita
          and _file_ricerca(b) == _file_ricerca(e) and tre.id_ricerca == e.id_ricerca
          and {k: v for k, v in _file_ricerca(tre).items() if k != "config.json"}
          == {k: v for k, v in _file_ricerca(e).items() if k != "config.json"},
          f"fermata dopo {len(a.passo_1)} teorie; con 3 processi diverso solo config.json, che scrive «processi»")
    w = lancia(cfg, cartelle["W"], verbose=False, data=DATA)
    check(f"{n + 5}. {nome}: cassaforte avvelenata (prezzi × 3, volume 1): ogni file della ricerca identico al bit, "
          "turni compresi: la cassaforte resta sigillata", w.id_ricerca == e.id_ricerca
          and _file_ricerca(w) == _file_ricerca(e) and w.tenuti_tolti == e.tenuti_tolti)
    return n + 6

if __name__ == "__main__":
    sys.exit(esegui())
