"""
Suite di collaudo del generatore della fabbrica (docs/82 P3 e P-L2, lavoro L3a; C2, docs/82 §11.4; §13): valori
degeneri e «STATO», la rosa dei trigger (§13.6), teorie del turno 1 e del turno 2, spazio del passo 1.

Si lancia da terminale, dalla cartella del progetto:

    python test_fabbrica_generatore.py

Solo dati sintetici (engine/fabbrica/sintetici.py): non servono i file in dati/, MetaTrader 5 o internet. Stampa una
riga per collaudo e alla fine «RISULTATO: n/n test superati».
"""
from __future__ import annotations

import math
import sys
import time
import warnings

import numpy as np
import pandas as pd

from engine.fabbrica import generatore as gen
from engine.fabbrica import sintetici
from engine.fabbrica.blocchi import FAMIGLIA_ADX_ATR, Blocco, blocchi_da_config, trigger_generati
from engine.fabbrica.cache import Cache
from engine.fabbrica.config import ROSA_STANDARD, budget_massimo, config_standard
from engine.fabbrica.dati import imposta_mercato_crypto
from engine.fabbrica.generatore import (ControlloDegenerazione, Teoria, filtri_compatibili, filtri_rimasti, lati_config,
                                        resoconto_teorie, rosa_dei_trigger, seme_teoria, spazio_teoria, stato_registro,
                                        teorie_turno_1, teorie_turno_2, togli_degeneri)
from engine.fabbrica.ottimizzatore import Categoria, Intero
from engine.indicatori import aggiungi_indicatori

warnings.simplefilter("ignore")

PERP, SPOT = "BINANCE_PERP_BTCUSDT", "BYBIT_SPOT_ETHUSDT"
N = 20_300


def _config(symbol, blocchi, modelli=((0, 2),), lati=("long", "short"), timeframe="M15") -> dict:
    cfg = config_standard(symbol, timeframe)
    cfg["blocchi"] = {n: dict(g) for n, g in blocchi.items()}
    cfg["modelli"] = [{"trigger": 1, "filtri": list(m), "uscite": 1} for m in modelli]
    cfg["lati"] = list(lati)
    return cfg


def _tutto(cfg, cache, blocchi=None):
    """Degeneri e turno 1 con TUTTI i blocchi rimasti (senza la rosa, che ha la sua sezione): (blocchi, rimaste, tolte,
    tenuti, teorie)."""
    blocchi = blocchi if blocchi is not None else blocchi_da_config(cfg)
    lati = lati_config(cfg)
    rimaste, tolte = togli_degeneri(blocchi, cache, lati, ControlloDegenerazione(cache))
    trigger = {lato: [b.nome for b in blocchi if b.tipo == "trigger" and lato in b.lati
                      and rimaste.get((b.nome, lato), (None,))] for lato in lati}
    filtri = filtri_rimasti(blocchi, lati, rimaste)
    tenuti = {lato: trigger[lato] + filtri[lato] for lato in lati}
    return blocchi, rimaste, tolte, tenuti, teorie_turno_1(cfg, blocchi, tenuti)


def _senza_generati(cfg) -> dict:
    """La config senza i trigger generati (più veloce, quando il collaudo non li riguarda)."""
    return {**cfg, "blocchi": {k: v for k, v in cfg["blocchi"].items() if k not in trigger_generati()}}


def _uguale_registro(a: dict, b: dict) -> bool:
    return all(list(a[k].items()) == list(b[k].items()) for k in a)


# ------------------------------------------------------------------ maschere fatte a mano
def _eventi(r, n=N, quanti=400) -> np.ndarray:
    """Eventi sparsi (mai due barre di fila, distanza almeno 10 barre), in posizioni a caso."""
    pos = np.sort(r.choice(np.arange(20, n - 20, 10), size=quanti, replace=False))
    m = np.zeros(n, dtype=bool)
    m[pos] = True
    return m


def _ogni_due(m: np.ndarray) -> np.ndarray:
    """Un evento sì e uno no: sta tutto dentro `m`, scatta la metà delle volte."""
    out = np.zeros_like(m)
    out[np.flatnonzero(m)[::2]] = True
    return out


def _stato(r, n=N, quota=0.3) -> np.ndarray:
    """Uno stato a tratti (filtro), vero su circa `quota` delle barre."""
    m = np.zeros(n, dtype=bool)
    i = 0
    while i < n:
        lung = int(r.integers(20, 120))
        m[i: i + lung] = r.random() < quota
        i += lung
    return m


def _blocco_a_mano(cache, nome, tipo, maschere: dict, famiglia=None, neutro=False) -> Blocco:
    """Un blocco come quelli del catalogo (senza parametri, la maschera è «del registro»), con le maschere date per
    lato messe nella cache: nessuna condizione registrata."""
    nomi = (f"MANO_{nome}_L", f"MANO_{nome}_L" if neutro else f"MANO_{nome}_S")
    for lato, n in ((1, nomi[0]), (-1, nomi[1])):
        m = maschere[lato]
        cache.prendi(("catalogo", n), lambda _m=m: _m)
    return Blocco(nome, tipo, famiglia or f"famiglia di {nome}", 15, neutro=neutro, _catalogo=nomi)


def esegui() -> int:
    ESITI = []
    t0 = time.perf_counter()

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        print(f"[{'OK ' if condizione else 'KO '}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""), flush=True)

    def errore(f) -> bool:
        try:
            f()
        except ValueError:
            return True
        return False

    df = aggiungi_indicatori(sintetici.mercato(N, seme=1, minuti=15, prezzo=30_000))
    cache = Cache(df, 600)

    # ------------------------------------------------------------------ il turno 1, a mano
    print("Il turno 1, su una lista fatta a mano")
    piccola = {"E47": {}, "RSI_RIENTRO": {}, "F3_VOLUME_ABOVE_AVG": {}, "ADX": {}, "ATR_RELATIVO": {}, "X0": {}, "X3": {}}
    cfg = _config(PERP, piccola)
    blocchi, rimaste, tolte, tenuti, teorie = _tutto(cfg, cache)
    scelte = ["-", "F3_VOLUME_ABOVE_AVG", "ADX", "ATR_RELATIVO"]
    attese = [f"L|{t}|{f}|{u}" for t in ("E47", "RSI_RIENTRO") for f in scelte for u in ("X0", "X3")]
    check("1. turno 1 con il conto esatto: 2 trigger × (1 + 3 filtri) × 2 uscite = 16 per lato, 32 in tutto, in "
          "quest'ordine",
          len(teorie) == 32 and [t.id for t in teorie if t.lato == 1] == attese
          and [t.id for t in teorie if t.lato == -1] == [a.replace("L|", "S|", 1) for a in attese]
          and all(len(tenuti[lato]) == 5 for lato in (1, -1)), f"{len(teorie)} teorie")
    solo_tu = teorie_turno_1(_config(PERP, piccola, modelli=((0, 0),)), blocchi, tenuti)
    solo_tf = teorie_turno_1(_config(PERP, piccola, modelli=((1, 2),)), blocchi, tenuti)
    check("2. i modelli decidono cosa entra nel turno 1: solo T+U dà 2 × 2 = 4 per lato; da 1 a 2 filtri dà solo le T+F",
          len(solo_tu) == 8 and all(not t.filtri for t in solo_tu)
          and len(solo_tf) == 24 and all(len(t.filtri) == 1 for t in solo_tf))
    check("3. un id per teoria, leggibile e senza doppi", len({t.id for t in teorie}) == len(teorie)
          and Teoria(1, "E47", ("F3_VOLUME_ABOVE_AVG", "ADX"), "X3").id == "L|E47|F3_VOLUME_ABOVE_AVG+ADX|X3"
          and Teoria(-1, "E5", (), "X0").id == "S|E5|-|X0")

    # ------------------------------------------------------------------ il turno 2, a mano
    print("\nIl turno 2, da un elenco dato di teorie T+F")
    tf = [t for t in teorie if len(t.filtri) == 1]
    dato = [tf[5], tf[0], tf[13], tf[3], tf[0]]                  # un ordine qualunque, con un doppio
    t2 = teorie_turno_2(dato, cfg, blocchi, tenuti)
    attese_2 = []
    for s in dato:
        for f2 in filtri_compatibili(s.filtri[0], s.lato, blocchi, tenuti):
            filtri = tuple(x for x in ("F3_VOLUME_ABOVE_AVG", "ADX", "ATR_RELATIVO") if x in (s.filtri[0], f2))
            attese_2.append(Teoria(s.lato, s.trigger, filtri, s.uscita).id)
    attese_2 = list(dict.fromkeys(attese_2))
    stesse = all(t.lato == s.lato and t.trigger == s.trigger and t.uscita == s.uscita and s.filtri[0] in t.filtri
                 for t in t2 for s in [next(x for x in dato if x.lato == t.lato and x.trigger == t.trigger
                                            and x.uscita == t.uscita and x.filtri[0] in t.filtri)])
    check("4. turno 2: ogni T+F prende un secondo filtro, tutti i compatibili; stesso lato, trigger e uscita; filtri "
          "nell'ordine della config; i doppi tolti (T+F3 e T+ADX danno una volta T+F3+ADX)",
          [t.id for t in t2] == attese_2 and stesse and len(t2) == len(set(t.id for t in t2)) and len(t2) < 2 * len(dato),
          f"{len(t2)} teorie: {[t.id for t in t2]}")
    check("5. turno 2: mai ADX con ATR relativo (stessa famiglia dichiarata, D1 = B), e mai lo stesso filtro due volte",
          not any({"ADX", "ATR_RELATIVO"} <= set(t.filtri) for t in t2) and all(len(set(t.filtri)) == 2 for t in t2)
          and filtri_compatibili("ADX", 1, blocchi, tenuti) == ["F3_VOLUME_ABOVE_AVG"]
          and filtri_compatibili("F3_VOLUME_ABOVE_AVG", 1, blocchi, tenuti) == ["ADX", "ATR_RELATIVO"])
    check("6. turno 2: lo stesso ordine a ogni lancio; senza due filtri nei modelli, nessuna teoria; una teoria non T+F "
          "si ferma", [t.id for t in teorie_turno_2(dato, cfg, blocchi, tenuti)] == [t.id for t in t2]
          and teorie_turno_2(dato, _config(PERP, piccola, modelli=((0, 1),)), blocchi, tenuti) == []
          and errore(lambda: teorie_turno_2([Teoria(1, "E47", (), "X0")], cfg, blocchi, tenuti)))
    check("7. il budget massimo con la formula nuova: turno 1 × 40 + min(150, T+F) × (filtri del lato più largo − 1) × 40 "
          "+ zoom, altopiano, selezione e cassaforte (docs/82 §11.5)",
          budget_massimo(32, cfg, 24, 3) == (32 + 24 * 2) * 40 + 80 * 270 + 80 * 60 + 2 * 80
          and budget_massimo(4860, config_standard(PERP, "M15"), 4644, 22) == 370_200)

    # ------------------------------------------------------------------ la config standard, tutto il catalogo
    print("\nLa config standard (C2: tutto il catalogo, senza i generati) sulle barre sintetiche M15")
    std = _senza_generati(config_standard(PERP, "M15"))
    prima = stato_registro()
    b_std, r_std, tolte_std, ten_std, t_std = _tutto(std, cache)
    dopo = stato_registro()
    res = resoconto_teorie(std, b_std, ten_std, r_std, t_std)
    per_nome = {b.nome: b for b in b_std}
    conti = {lato: (sum(per_nome[n].tipo == "trigger" for n in ten_std[lato]),
                    sum(per_nome[n].tipo == "filtro" for n in ten_std[lato])) for lato in (1, -1)}
    check("8. 45 trigger e 30 filtri sul long, 44 e 30 sullo short; teorie del turno 1 = trigger × (1 + filtri) × 3 "
          "uscite, per lato", res["blocchi"]["long"]["trigger"]["blocchi"] == 45
          and res["blocchi"]["short"]["trigger"]["blocchi"] == 44 and res["blocchi"]["long"]["filtro"]["blocchi"] == 30
          and all(res["per_lato"][gen.NOME_LATO[lato]] == t * (1 + f) * 3 for lato, (t, f) in conti.items())
          and len(t_std) == sum(t * (1 + f) * 3 for t, f in conti.values()),
          f"long {conti[1]}, short {conti[-1]}, {len(t_std)} teorie")
    check("9. il registro delle condizioni è identico prima e dopo i valori degeneri", _uguale_registro(prima, dopo))
    di_nuovo = _tutto(std, cache)
    check("10. stesso ordine e stessi blocchi a ogni lancio",
          [t.id for t in di_nuovo[4]] == [t.id for t in t_std] and di_nuovo[3] == ten_std)
    f_std = filtri_rimasti(b_std, [1, -1], r_std)
    check("11. i filtri: tutti quelli rimasti dopo i valori degeneri, nell'ordine della config (docs/82 §13, scelta A)",
          f_std[1] == [b.nome for b in b_std if b.tipo == "filtro" and r_std.get((b.nome, 1), (None,))]
          and len(f_std[1]) == conti[1][1], str(len(f_std[1])))
    check("13. E19 non ha teorie short; lo spot ha solo teorie long, anche con lo short scritto nei lati",
          not any(t.trigger == "E19" and t.lato == -1 for t in t_std)
          and all(t.lato == 1 for t in teorie_turno_1({**config_standard(SPOT, "M15"), "lati": ["long", "short"]},
                                                       b_std, ten_std)))
    _, _, _, ten_sp, t_sp = _tutto(_senza_generati(config_standard(SPOT, "M15")), cache)
    check("14. spot: blocchi e teorie solo sul long", set(ten_sp) == {1} and t_sp and all(t.lato == 1 for t in t_sp))
    check("15. ADX e ATR relativo (stessa famiglia dichiarata) entrano tutti e due, ma mai nella stessa teoria",
          {"ADX", "ATR_RELATIVO"} <= set(ten_std[1]) and {"ADX", "ATR_RELATIVO"} <= set(ten_std[-1])
          and res["coppie_stessa_famiglia"] == [{"lato": "long", "filtri": ["ADX", "ATR_RELATIVO"],
                                                 "famiglia": FAMIGLIA_ADX_ATR},
                                                {"lato": "short", "filtri": ["ADX", "ATR_RELATIVO"],
                                                 "famiglia": FAMIGLIA_ADX_ATR}])

    # ------------------------------------------------------------------ la rosa dei trigger (docs/82 §13.6)
    print("\nLa rosa dei trigger (docs/82 §13): un vantaggio piantato in un trigger generato")
    imposta_mercato_crypto()
    G = "G0045_P50_SU"
    piantato = aggiungi_indicatori(sintetici.mercato_con_generato(G))
    c_r = Cache(piantato, 600)
    NB = len(piantato)
    rari = _eventi(np.random.default_rng(5), NB, quanti=150)
    rara = _blocco_a_mano(c_r, "E40", "trigger", {1: rari, -1: rari})            # 150 eventi: sotto i 200
    cfg_r = _config(PERP, {"E47": {}, "RSI_RIENTRO": {}, G: {}, "G0001_P25_SU": {}, "X0": {}})
    b_r = blocchi_da_config(cfg_r) + [rara]
    rim_r, _ = togli_degeneri(b_r, c_r, [1, -1])
    prima_r = stato_registro()
    entrano, tab = rosa_dei_trigger(b_r, c_r, [1, -1], rim_r, PERP, ROSA_STANDARD, processi=1)
    dopo_r = stato_registro()
    righe_g = [r for r in tab if r["blocco"] == G]
    check("R1. il vantaggio piantato nel generato arriva nella rosa, sul long, ai tre orizzonti; lo short della coppia "
          "(lo stesso segnale, l'opposto) no", G in entrano[1] and G not in entrano[-1]
          and {r["orizzonte"] for r in righe_g if r["lato"] == "long" and r["nella_rosa"]} == {4, 16, 32},
          str(entrano))
    dentro = {(r["lato"], r["blocco"]) for r in tab if r["nella_rosa"]}
    check("R2. entra esattamente chi è nella rosa ad almeno un orizzonte, nell'ordine della config",
          all(entrano[lato] == [b.nome for b in b_r if (gen.NOME_LATO[lato], b.nome) in dentro] for lato in (1, -1)))
    from engine.rosa import rosa_orizzonti_entry
    from engine.simboli import pip_symbol
    with gen._registro_isolato():
        nomi = []
        for lato in (1, -1):
            for b in b_r:
                if b.tipo == "trigger" and rim_r.get((b.nome, lato), (None,)):
                    n = f"{b.nome}_{gen.NOME_LATO[lato]}"
                    gen.reg.register_entry(n, direction=lato)(b.condizione(c_r, lato))
                    nomi.append(n)
        diretta, _ = rosa_orizzonti_entry(piantato, [4, 16, 32], pip_symbol(PERP), nomi=nomi, fuso="UTC", unita="bp")
    attesa = sorted((h, n, round(float(t), 9), bool(r)) for h, d in diretta.items()
                    for n, t, r in zip(d["candidato"], d["t_netto"], d["nella_rosa"]))
    avuta = sorted((r["orizzonte"], f"{r['blocco']}_{r['lato']}", round(r["t"], 9), r["nella_rosa"]) for r in tab)
    check("R3. gli stessi numeri della rosa del Lab chiamata direttamente, ufficiali e generati nella stessa chiamata "
          "(un solo Benjamini-Hochberg)", attesa == avuta and {r["blocco"] for r in tab} >= {"RSI_RIENTRO", G},
          f"{len(avuta)} righe")
    check("R4. sotto i 200 eventi un trigger non è misurato: niente righe, niente prove, non entra",
          not any(r["blocco"] == "E40" for r in tab) and "E40" not in entrano[1])
    check("R5. una riga per trigger misurato e orizzonte, con eventi, scarto e t", len(tab) == len(attesa)
          and all(set(r) == {"orizzonte", "lato", "blocco", "eventi", "scarto_bp", "t", "candidata", "nella_rosa"}
                  for r in tab))
    check("R6. il registro delle condizioni è identico prima e dopo la rosa", _uguale_registro(prima_r, dopo_r))
    solo_l, tab_l = rosa_dei_trigger(b_r, c_r, [1], rim_r, SPOT, ROSA_STANDARD, processi=1)
    check("R7. sullo spot solo il long: righe e trigger solo long", set(solo_l) == {1}
          and {r["lato"] for r in tab_l} == {"long"} and G in solo_l[1])
    vuoto, _ = rosa_dei_trigger([rara], c_r, [1, -1], {}, PERP, ROSA_STANDARD, processi=1)
    check("R8. nessun trigger nella rosa: liste vuote (la ricerca poi si ferma, collaudo in test_fabbrica_ricerca)",
          vuoto == {1: [], -1: []})

    # ------------------------------------------------------------------ STATO
    print("\nSTATO (Mattia, 12/11, scelta A)")
    c3 = Cache(df, 600)
    NB = len(df)                                                  # le barre dopo aggiungi_indicatori
    A = _eventi(np.random.default_rng(7), NB)
    due_di_fila = _eventi(np.random.default_rng(3), NB)
    due_di_fila[np.flatnonzero(due_di_fila)[:5] + 1] = True       # cinque volte su due barre di fila
    e23 = _blocco_a_mano(c3, "E23", "trigger", {1: due_di_fila, -1: _eventi(np.random.default_rng(4), NB)})
    e12 = _blocco_a_mano(c3, "E12", "trigger", {1: A, -1: A})
    uscite = blocchi_da_config({"timeframe": "M15", "blocchi": {"X0": {}}})
    blo = [e23, e12, *uscite]
    cfg_s = {**_config(PERP, {"X0": {}}), "blocchi": {b.nome: {} for b in blo}}
    _, rim_s, tolte_s, ten_s, teo_s = _tutto(cfg_s, c3, blo)
    check("25. un trigger del catalogo vero su due barre di fila esce da quel lato; resta sull'altro lato; la ricerca "
          "prosegue con le altre teorie",
          "E23" not in ten_s[1] and "E23" in ten_s[-1] and rim_s[("E23", 1)] == ()
          and any(t["blocco"] == "E23" and t["esito"] == "STATO" for t in tolte_s)
          and {t.id for t in teo_s} == {"L|E12|-|X0", "S|E23|-|X0", "S|E12|-|X0"}, str([t.id for t in teo_s]))
    a_stato = Blocco("PARAM_STATO", "trigger", "prova", 15, (Intero("p_barre", 5, 5, 1),), {"p_barre": (5,)},
                     _calcola=lambda c, l, v, _m=due_di_fila: _m)
    check("26. un blocco con parametri della fabbrica in «STATO»: è un errore del blocco, la ricerca si ferma",
          errore(lambda: togli_degeneri([a_stato], c3, [1, -1])))

    # ------------------------------------------------------------------ il seme
    print("\nIl seme della teoria")
    semi = {t.id: seme_teoria(7, t.id) for t in t_std}
    rovescio = {t.id: seme_teoria(7, t.id) for t in reversed(t_std)}
    check("27. seme della ricerca + id: non dipende dall'ordine; cambia con l'id e con il seme della ricerca",
          semi == rovescio and len(set(semi.values())) == len(semi) and seme_teoria(8, t_std[0].id) != semi[t_std[0].id]
          and all(isinstance(s, int) and 0 <= s < 2**60 for s in semi.values()))

    # ------------------------------------------------------------------ i valori degeneri
    print("\nI valori degeneri (decisione del 07/11)")
    con_adx = dict(piccola, ADX={"periodo_ore": [1.25], "soglia": [15, 30]})
    b_d, r_d, tolte_d, ten_d, t_d = _tutto(_config(PERP, con_adx), cache)
    riga_d = [t for t in tolte_d if t["blocco"] == "ADX"]
    check("28. ADX a 5 barre: la soglia 15 è quasi sempre vera e si toglie, una volta per i due lati; la 30 resta",
          len(riga_d) == 1 and riga_d[0]["valori"] == {"periodo_barre": 5, "soglia": 15} and riga_d[0]["lato"] == "entrambi"
          and riga_d[0]["esito"] == "QUASI_SEMPRE_VERA" and riga_d[0]["quota_vere"] >= 0.95
          and r_d[("ADX", 1)] == r_d[("ADX", -1)] == ({"periodo_barre": 5, "soglia": 30},), str(riga_d))
    t_adx = next(t for t in t_d if t.filtri == ("ADX",) and t.lato == 1)
    st = spazio_teoria(t_adx, b_d, r_d)
    check("29. lo spazio segue la griglia rimasta: ADX.soglia ha solo 30", st._valori["ADX.soglia"] == (30,)
          and st._valori["ADX.periodo_barre"] == (5,))
    vuoto = dict(piccola, ADX={"periodo_ore": [1.25], "soglia": [15, 20]})
    cfg_v = _config(PERP, vuoto)
    b_v, r_v, _, ten_v, t_v = _tutto(cfg_v, cache)
    res_v = resoconto_teorie(cfg_v, b_v, ten_v, r_v, t_v)
    check("30. tutte le combinazioni degeneri: il blocco esce e il resoconto lo dice",
          not any("ADX" in t.filtri for t in t_v) and len(t_v) == 2 * 2 * (1 + 2) * 2
          and {(x["blocco"], x["lato"]) for x in res_v["blocchi_usciti"]} == {("ADX", "long"), ("ADX", "short")}
          and {x["perche"] for x in res_v["blocchi_usciti"]} == {"tutte le combinazioni della griglia sono degeneri"})
    salita = aggiungi_indicatori(sintetici.mercato(N, seme=6, minuti=15, prezzo=30_000, spinta=np.full(N, 0.0005)))
    c_sal = Cache(salita, 300)
    b_l = blocchi_da_config({"timeframe": "M15", "blocchi": {"DONCHIAN": {"canale_ore": [24, 2500]}}})
    r_l, tolte_l = togli_degeneri(b_l, c_sal, [1, -1])
    check("31. per lato: su un mercato che sale molto il canale di 10.000 barre non scatta mai sullo short ed esce solo da lì",
          tolte_l == [{"blocco": "DONCHIAN", "lato": "short", "valori": {"canale_barre": 10000}, "esito": "SEMPRE_FALSA",
                       "quota_vere": 0.0}] and r_l[("DONCHIAN", 1)] == ({"canale_barre": 96}, {"canale_barre": 10000})
          and r_l[("DONCHIAN", -1)] == ({"canale_barre": 96},), str(tolte_l))
    uscita = next(b for b in b_std if b.nome == "X0")
    ctl = ControlloDegenerazione(cache)
    check("32. le uscite non passano dal controllo (decisione del 07/11): errore se ci si prova, nessuna riga nell'elenco",
          errore(lambda: ctl.esiti([(uscita, 1, {"durata_barre": 4, "perc_stop": 90, "target": None})]))
          and not any(t["blocco"] in ("X0", "X1", "X3") for t in tolte_std))
    rotto = Blocco("ROTTO", "filtro", "rotto", 15, (Intero("p_barre", 5, 5, 1),), {"p_barre": (5,)}, neutro=True,
                   _calcola=lambda c, l, v: 1 / 0)
    prima_r = stato_registro()
    check("33. un blocco che va in errore non è un valore da togliere: si ferma", errore(lambda: ctl.esiti([(rotto, 1, {"p_barre": 5})]))
          and _uguale_registro(prima_r, stato_registro()))
    chiamate = []
    originale = gen.verifica_degenerazione
    gen.verifica_degenerazione = lambda *a, **k: chiamate.append(1) or originale(*a, **k)
    try:
        ctl2 = ControlloDegenerazione(cache)
        togli_degeneri(b_d, cache, [1, -1], ctl2)
        n_prima = len(chiamate)
        togli_degeneri(b_d, cache, [1, -1], ctl2)
    finally:
        gen.verifica_degenerazione = originale
    check("34. una combinazione già misurata non si rimisura", n_prima >= 1 and len(chiamate) == n_prima, f"{n_prima} misure, poi nessuna")

    # ------------------------------------------------------------------ lo spazio del passo 1
    print("\nLo spazio del passo 1, sui valori larghi")
    st1 = spazio_teoria(Teoria(1, "E47", (), "X0"), b_std, r_std)
    nomi = [p.nome for p in st1.spazio.parametri]
    punti = st1.punti_ammessi()
    valori = [st1.valori(p)["X0"] for p in punti]
    check("35. E47 + X0: durata, stop e target; 4 × 4 × 2 = 32 punti, i valori della griglia larga",
          nomi == ["X0.durata_barre", "X0.perc_stop", "X0.target"] and len(punti) == 32
          and isinstance(st1.spazio.parametri[0], Intero) and isinstance(st1.spazio.parametri[2], Categoria)
          and sorted({v["durata_barre"] for v in valori}) == [4, 8, 16, 32] and {v["target"] for v in valori} == {None, 90}
          and st1.valori(punti[0]) == {"E47": {}, "X0": {"durata_barre": 4, "perc_stop": 70, "target": None}})
    st2 = spazio_teoria(Teoria(-1, "RSI_RIENTRO", ("ATR_RELATIVO",), "X3"), b_std, r_std)
    check("36. RSI + ATR relativo + X3 sui valori standard (docs/82 §12): 1 × 1 × 1 × 1 × 1 × 4 × 4 × 2 = 32 punti, "
          "tutti ammessi senza valori degeneri", st2.spazio.totale == 4 * 4 * 2 and len(st2.punti_ammessi()) == 32
          and all(st2.valori(p)["RSI_RIENTRO"] == {"periodo_barre": 14, "soglia": 30}
                  and st2.valori(p)["ATR_RELATIVO"] == {"breve_barre": 14, "lungo_barre": 100, "soglia": 1.0}
                  for p in st2.punti_ammessi()))
    st3 = spazio_teoria(Teoria(1, "E47", ("ADX",), "X0"), b_d, r_d)
    check("37. con una combinazione tolta lo spazio la rifiuta: ammesso dice no", st3.ammesso(
          {"E47": {}, "ADX": {"periodo_barre": 5, "soglia": 30}, "X0": {}}) and not st3.ammesso(
          {"E47": {}, "ADX": {"periodo_barre": 5, "soglia": 15}, "X0": {}}) and len(st3.punti_ammessi()) == 32)
    st4 = spazio_teoria(Teoria(1, "E47", ("ADX",), "X0"), b_d, {})
    check("38. senza valori degeneri: tutti i punti ammessi", len(st4.punti_ammessi()) == 2 * 32)

    # ------------------------------------------------------------------ §12: un valore standard degenere su un lato
    print("\n§12 · Un valore standard degenere su un lato (docs/82 §12.8)")
    r_up = np.random.default_rng(4)
    chiusure = 100.0 * np.exp(np.cumsum(0.002 + 0.001 * r_up.standard_normal(6000)))   # sale sempre: mai sotto il minimo
    su = pd.DataFrame({"Open": chiusure / 1.0005, "High": chiusure * 1.001, "Low": chiusure / 1.002, "Close": chiusure,
                       "Volume": 1000.0}, index=pd.date_range("2024-01-01", periods=6000, freq="15min", tz="UTC"))
    cfg_su = _config(PERP, {"DONCHIAN": {}, "E5": {}, "X0": {}}, modelli=((0, 0),))
    _, rim_su, tolte_su, ten_su, teo_su = _tutto(cfg_su, Cache(su, 50))
    check("39b. Donchian 20 (il valore standard) degenere sullo short: esce da quel lato, resta sul long",
          rim_su[("DONCHIAN", 1)] == ({"canale_barre": 20},) and rim_su[("DONCHIAN", -1)] == ()
          and any(t["blocco"] == "DONCHIAN" and t["lato"] == "short" and t["valori"] == {"canale_barre": 20}
                  for t in tolte_su)
          and "DONCHIAN" in ten_su[1] and "DONCHIAN" not in ten_su[-1]
          and not any(t.trigger == "DONCHIAN" and t.lato == -1 for t in teo_su), str(rim_su))

    # ------------------------------------------------------------------ D1, da leggere
    print("\nD1, barre sintetiche: le combinazioni degeneri tolte")
    d1 = aggiungi_indicatori(sintetici.mercato(12_300, seme=0, minuti=1440, prezzo=30_000))
    std_d1 = _senza_generati(config_standard(PERP, "D1"))
    c_d1 = Cache(d1, 300)
    b1, r1, tolte1, ten1, t1 = _tutto(std_d1, c_d1)
    elenco = "; ".join(f"{x['blocco']} {x['lato']} {x['valori']} {x['esito']} {x['quota_vere']:.1%}" for x in tolte1
                       if x["valori"])
    coerenti = all((x["esito"] == "QUASI_SEMPRE_VERA" and x["quota_vere"] >= 0.95) or (x["esito"] == "SEMPRE_FALSA" and x["quota_vere"] == 0)
                   or x["esito"] in ("RARA", "SEMPRE_VERA", "STATO") for x in tolte1)
    adx = [p for p in spazio_teoria(Teoria(1, ten1[1][0], ("ADX",), "X0"), b1, r1).spazio.parametri if p.nome == "ADX.soglia"]
    check("39. su D1 le combinazioni tolte hanno esiti coerenti con la quota, e lo spazio di ADX parte dalla soglia rimasta",
          tolte1 and coerenti and adx and r1[("ADX", 1)] and min(c["soglia"] for c in r1[("ADX", 1)]) > 15,
          f"{len(t1)} teorie; tolte con parametri: {elenco}")
    print("    blocchi del catalogo tolti su D1: " + "; ".join(f"{x['blocco']} {x['lato']} {x['esito']}" for x in tolte1
                                                              if not x["valori"]))

    print("\n" + "=" * 70)
    print(f"Durata: {time.perf_counter() - t0:.0f} s")
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
