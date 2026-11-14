"""
Suite di collaudo del generatore della fabbrica (docs/82 P3 e P-L2, lavoro L3a; C2, docs/82 §11.3, §11.4, §11.7):
valori degeneri e «STATO», famiglie misurate, un blocco per famiglia, teorie del turno 1 e del turno 2, spazio del passo 1.

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
from engine.fabbrica.blocchi import FAMIGLIA_ADX_ATR, Blocco, blocchi_da_config
from engine.fabbrica.cache import Cache
from engine.fabbrica.config import budget_massimo, config_standard
from engine.fabbrica.generatore import (QUATTORDICI, STATO_CATALOGO, ControlloDegenerazione, Teoria,
                                        filtri_compatibili, lati_config, misura_famiglie, resoconto_teorie, seme_teoria,
                                        spazio_teoria, stato_registro, teorie_turno_1, teorie_turno_2, togli_degeneri,
                                        un_blocco_per_famiglia)
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
    """L'avvio della ricerca sul pezzo della cache: degeneri, famiglie, un blocco per famiglia, turno 1."""
    blocchi = blocchi if blocchi is not None else blocchi_da_config(cfg)
    lati = lati_config(cfg)
    controllo = ControlloDegenerazione(cache)
    rimaste, tolte = togli_degeneri(blocchi, cache, lati, controllo)
    famiglie, misura = misura_famiglie(blocchi, cache, lati, rimaste)
    tenuti, tabella = un_blocco_per_famiglia(blocchi, misura, controllo, lati, rimaste)
    teorie = teorie_turno_1(cfg, blocchi, tenuti)
    return blocchi, rimaste, tolte, misura, tenuti, tabella, teorie


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
    blocchi, rimaste, tolte, misura, tenuti, tabella, teorie = _tutto(cfg, cache)
    scelte = ["-", "F3_VOLUME_ABOVE_AVG", "ADX", "ATR_RELATIVO"]
    attese = [f"L|{t}|{f}|{u}" for t in ("E47", "RSI_RIENTRO") for f in scelte for u in ("X0", "X3")]
    check("1. turno 1 con il conto esatto: 2 trigger × (1 + 3 filtri) × 2 uscite = 16 per lato, 32 in tutto, in "
          "quest'ordine (tutti tenuti: nessuno nella stessa famiglia misurata sulle barre sintetiche; E47 e DONCHIAN "
          "invece sì, e resta DONCHIAN)",
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
    print("\nLa config standard (C2: tutto il catalogo) sulle barre sintetiche M15")
    std = config_standard(PERP, "M15")
    prima = stato_registro()
    b_std, r_std, tolte_std, m_std, ten_std, tab_std, t_std = _tutto(std, cache)
    dopo = stato_registro()
    res = resoconto_teorie(std, b_std, ten_std, r_std, t_std)
    per_nome = {b.nome: b for b in b_std}
    conti = {lato: (sum(per_nome[n].tipo == "trigger" for n in ten_std[lato]),
                    sum(per_nome[n].tipo == "filtro" for n in ten_std[lato])) for lato in (1, -1)}
    check("8. 45 trigger e 30 filtri sul long, 44 e 30 sullo short; teorie del turno 1 = trigger tenuti × (1 + filtri "
          "tenuti) × 3 uscite, per lato", res["blocchi"]["long"]["trigger"]["blocchi"] == 45
          and res["blocchi"]["short"]["trigger"]["blocchi"] == 44 and res["blocchi"]["long"]["filtro"]["blocchi"] == 30
          and all(res["per_lato"][gen.NOME_LATO[lato]] == t * (1 + f) * 3 for lato, (t, f) in conti.items())
          and len(t_std) == sum(t * (1 + f) * 3 for t, f in conti.values()),
          f"long {conti[1]}, short {conti[-1]}, {len(t_std)} teorie")
    check("9. il registro delle condizioni è identico prima e dopo degeneri, famiglie e un blocco per famiglia",
          _uguale_registro(prima, dopo))
    di_nuovo = _tutto(std, cache)
    check("10. stesso ordine, stessi tenuti e stessa tabella a ogni lancio",
          [t.id for t in di_nuovo[6]] == [t.id for t in t_std] and di_nuovo[4] == ten_std and di_nuovo[5] == tab_std)
    righe = pd.DataFrame(tab_std)
    vivi = righe[righe["famiglia"].notna()]
    regola = []
    for (lato, tipo, fam), g in vivi.groupby(["lato", "tipo", "famiglia"]):
        dei14 = g[g["blocco"].isin(QUATTORDICI)]
        pool = dei14 if len(dei14) else g
        atteso = sorted(zip(-pool["scatta"], pool["blocco"]))[0][1]
        regola.append(list(g[g["esito"] == "tenuto"]["blocco"]) == [atteso])
    check("11. in ogni famiglia misurata di ogni lato resta un blocco solo, quello della regola (uno dei 14; fra due o più "
          "dei 14, o senza, quello che scatta più spesso; a parità il nome più piccolo)",
          all(regola) and len(regola) == len(vivi[vivi["esito"] == "tenuto"]),
          f"{len(regola)} famiglie, {int((righe['esito'] == 'tolto').sum())} blocchi tolti")
    check("12. la tabella ha una riga per blocco e lato (E19 solo sul long) con le colonne di §11.3; ogni tolto ha il "
          "suo motivo", list(righe.columns) == gen.COLONNE_TENUTI and len(righe) == 75 + 74
          and not len(righe[(righe["blocco"] == "E19") & (righe["lato"] == "short")])
          and all(righe["motivo"].str.len() > 0))
    check("13. E19 non ha teorie short; lo spot ha solo teorie long, anche con lo short scritto nei lati",
          not any(t.trigger == "E19" and t.lato == -1 for t in t_std)
          and all(t.lato == 1 for t in teorie_turno_1({**config_standard(SPOT, "M15"), "lati": ["long", "short"]},
                                                       b_std, ten_std)))
    _, _, _, _, ten_sp, tab_sp, t_sp = _tutto(config_standard(SPOT, "M15"), cache)
    check("14. spot: famiglie e tenuti solo sul long, teorie tutte long", set(ten_sp) == {1}
          and {r["lato"] for r in tab_sp} == {"long"} and t_sp and all(t.lato == 1 for t in t_sp))
    fam = m_std.set_index(["lato", "blocco"])
    check("15. famiglie misurate per lato, trigger con trigger e filtri con filtri; la dichiarazione non unisce: ADX e "
          "ATR relativo, in famiglie misurate diverse, restano tutti e due",
          set(m_std["lato"]) == {"long", "short"} and set(m_std["tipo"]) == {"trigger", "filtro"}
          and fam.loc[("long", "ADX"), "famiglia"] != fam.loc[("long", "ATR_RELATIVO"), "famiglia"]
          and {"ADX", "ATR_RELATIVO"} <= set(ten_std[1]) and {"ADX", "ATR_RELATIVO"} <= set(ten_std[-1])
          and res["coppie_stessa_famiglia"] == [{"lato": "long", "filtri": ["ADX", "ATR_RELATIVO"],
                                                 "famiglia": FAMIGLIA_ADX_ATR},
                                                {"lato": "short", "filtri": ["ADX", "ATR_RELATIVO"],
                                                 "famiglia": FAMIGLIA_ADX_ATR}])

    # ------------------------------------------------------------------ un blocco per famiglia, maschere a mano
    print("\nUn blocco per famiglia, con maschere fatte a mano dall'esito noto (docs/82 §11.3, §11.7)")
    c2 = Cache(df, 600)
    NB = len(df)                                                  # le barre dopo aggiungi_indicatori
    r = np.random.default_rng(7)
    A, B, C, D, F, G = (_eventi(r, NB) for _ in range(6))
    D2 = np.r_[False, D[:-1]]                                     # gli stessi eventi una barra dopo: stessa frequenza
    S1, S2 = _stato(r, NB), _stato(r, NB)
    rari = np.zeros(NB, dtype=bool)
    rari[[100, 5_000, 9_000]] = True
    a_mano = [
        _blocco_a_mano(c2, "DONCHIAN", "trigger", {1: _ogni_due(A), -1: _ogni_due(A)}),     # uno dei 14, scatta meno
        _blocco_a_mano(c2, "E12", "trigger", {1: A, -1: A}),
        _blocco_a_mano(c2, "E21", "trigger", {1: B, -1: B}),                                 # nessuno dei 14
        _blocco_a_mano(c2, "E8", "trigger", {1: _ogni_due(B), -1: _ogni_due(B)}),
        _blocco_a_mano(c2, "E5", "trigger", {1: C, -1: C}),                                  # due dei 14
        _blocco_a_mano(c2, "E47", "trigger", {1: _ogni_due(C), -1: _ogni_due(C)}),
        _blocco_a_mano(c2, "E30", "trigger", {1: D, -1: D}),                                 # parità
        _blocco_a_mano(c2, "E2", "trigger", {1: D2, -1: D2}),
        _blocco_a_mano(c2, "E3", "trigger", {1: F, -1: F}),                                  # E1 con E3 solo sul long
        _blocco_a_mano(c2, "E1", "trigger", {1: _ogni_due(F), -1: G}),
        _blocco_a_mano(c2, "E40", "trigger", {1: rari, -1: rari}),                           # degenere: rara
        _blocco_a_mano(c2, "ADX", "filtro", {1: S1, -1: S1}, FAMIGLIA_ADX_ATR, neutro=True),
        _blocco_a_mano(c2, "F1_ADX_ABOVE", "filtro", {1: S1 & (np.arange(NB) % 10 != 0)} | {-1: S1 & (np.arange(NB) % 10 != 0)},
                       neutro=True),
        _blocco_a_mano(c2, "ATR_RELATIVO", "filtro", {1: S2, -1: S2}, FAMIGLIA_ADX_ATR, neutro=True),
        _blocco_a_mano(c2, "F2_HIGH_VOLATILITY", "filtro", {1: S2 & (np.arange(NB) % 7 != 0)} | {-1: S2 & (np.arange(NB) % 7 != 0)},
                       neutro=True),
    ]
    uscite = blocchi_da_config({"timeframe": "M15", "blocchi": {"X0": {}}})
    prima_m = stato_registro()
    mano_cfg = {**_config(PERP, {"X0": {}}), "blocchi": {b.nome: {} for b in a_mano + uscite}}
    _, rim_m, tolte_m, mis_m, ten_m, tab_m, teo_m = _tutto(mano_cfg, c2, a_mano + uscite)
    riga = {(x["lato"], x["blocco"]): x for x in tab_m}
    n_ = {nome: int(m.sum()) for nome, m in (("A", A), ("B", B), ("C", C), ("D", D))}

    def tenuto(lato, nome):
        return riga[(lato, nome)]["esito"] == "tenuto"

    check("16. una famiglia con uno dei 14 tiene quello, anche se scatta meno: DONCHIAN tenuto, E12 tolto",
          tenuto("long", "DONCHIAN") and not tenuto("long", "E12")
          and riga[("long", "E12")]["motivo"] == "stessa famiglia di DONCHIAN, che è uno dei 14 di oggi"
          and riga[("long", "DONCHIAN")]["motivo"] == "uno dei 14 di oggi"
          and riga[("long", "DONCHIAN")]["scatta"] < riga[("long", "E12")]["scatta"], riga[("long", "E12")]["motivo"])
    check("17. una famiglia senza i 14 tiene quello che scatta più spesso: E21 tenuto, E8 tolto, con i numeri",
          tenuto("long", "E21") and not tenuto("long", "E8") and riga[("long", "E21")]["motivo"] == "scatta più spesso"
          and riga[("long", "E8")]["motivo"] == f"stessa famiglia di E21, che scatta più spesso ({n_['B']} segnali "
                                                f"contro {int(_ogni_due(B).sum())})", riga[("long", "E8")]["motivo"])
    check("18. due dei 14 nella stessa famiglia misurata: resta quello che scatta più spesso (E5), E47 tolto",
          tenuto("long", "E5") and not tenuto("long", "E47")
          and riga[("long", "E5")]["motivo"] == "dei 14 di oggi, scatta più spesso"
          and riga[("long", "E47")]["motivo"].startswith("stessa famiglia di E5, che scatta più spesso ("))
    check("19. a parità di frequenza, il nome più piccolo: E2 tenuto, E30 tolto",
          riga[("long", "E2")]["scatta"] == riga[("long", "E30")]["scatta"] and tenuto("long", "E2")
          and not tenuto("long", "E30"))
    check("20. lo stesso blocco tenuto su un lato e tolto sull'altro: E1 tolto sul long (con E3), tenuto sullo short",
          not tenuto("long", "E1") and tenuto("long", "E3") and tenuto("short", "E1") and tenuto("short", "E3")
          and riga[("short", "E1")]["motivo"] == "solo nella sua famiglia")
    check("21. ADX e ATR relativo in famiglie misurate diverse (ADX con F1, ATR relativo con F2_HIGH): restano tutti e "
          "due, F1 e F2_HIGH tolti; nel turno 2 mai insieme",
          tenuto("long", "ADX") and tenuto("long", "ATR_RELATIVO") and not tenuto("long", "F1_ADX_ABOVE")
          and not tenuto("long", "F2_HIGH_VOLATILITY")
          and riga[("long", "F1_ADX_ABOVE")]["motivo"] == "stessa famiglia di ADX, che è uno dei 14 di oggi"
          and not any({"ADX", "ATR_RELATIVO"} <= set(t.filtri) for t in teorie_turno_2(
              [t for t in teo_m if len(t.filtri) == 1], mano_cfg, a_mano + uscite, ten_m)))
    check("22. un blocco del catalogo degenere su questi dati esce dal lato con il motivo, senza famiglia",
          not tenuto("long", "E40") and riga[("long", "E40")]["famiglia"] is None
          and riga[("long", "E40")]["motivo"] == "degenere sul pezzo di ricerca (scatta meno di 30 volte)"
          and {"blocco": "E40", "lato": "long", "valori": {}, "esito": "RARA", "quota_vere": 3 / NB} in tolte_m)
    check("23. tenuti: long DONCHIAN, E21, E5, E2, E3, ADX, ATR relativo (in ordine di config); short anche E1",
          ten_m[1] == ["DONCHIAN", "E21", "E5", "E2", "E3", "ADX", "ATR_RELATIVO"]
          and ten_m[-1] == ["DONCHIAN", "E21", "E5", "E2", "E3", "E1", "ADX", "ATR_RELATIVO"], str(ten_m))
    check("24. il registro delle condizioni identico prima e dopo", _uguale_registro(prima_m, stato_registro()))

    # ------------------------------------------------------------------ STATO
    print("\nSTATO (Mattia, 12/11, scelta A)")
    c3 = Cache(df, 600)
    due_di_fila = _eventi(np.random.default_rng(3), NB)
    due_di_fila[np.flatnonzero(due_di_fila)[:5] + 1] = True       # cinque volte su due barre di fila
    e23 = _blocco_a_mano(c3, "E23", "trigger", {1: due_di_fila, -1: _eventi(np.random.default_rng(4), NB)})
    e12 = _blocco_a_mano(c3, "E12", "trigger", {1: A, -1: A})
    blo = [e23, e12, *uscite]
    cfg_s = {**_config(PERP, {"X0": {}}), "blocchi": {b.nome: {} for b in blo}}
    _, rim_s, tolte_s, _, ten_s, tab_s, teo_s = _tutto(cfg_s, c3, blo)
    riga_s = {(x["lato"], x["blocco"]): x for x in tab_s}
    check("25. un trigger del catalogo vero su due barre di fila esce da quel lato con il motivo «vero su due barre di "
          "fila: non è un evento su questi dati»; resta sull'altro lato; la ricerca prosegue con le altre teorie",
          "E23" not in ten_s[1] and "E23" in ten_s[-1] and riga_s[("long", "E23")]["motivo"] == STATO_CATALOGO
          and STATO_CATALOGO == "vero su due barre di fila: non è un evento su questi dati"
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
    b_d, r_d, tolte_d, _, ten_d, _, t_d = _tutto(_config(PERP, con_adx), cache)
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
    b_v, r_v, _, _, ten_v, tab_v, t_v = _tutto(cfg_v, cache)
    res_v = resoconto_teorie(cfg_v, b_v, ten_v, r_v, t_v)
    check("30. tutte le combinazioni degeneri: il blocco esce, il resoconto e la tabella dei tenuti lo dicono",
          not any("ADX" in t.filtri for t in t_v) and len(t_v) == 2 * 2 * (1 + 2) * 2
          and {(x["blocco"], x["lato"]) for x in res_v["blocchi_usciti"]} == {("ADX", "long"), ("ADX", "short")}
          and {x["motivo"] for x in tab_v if x["blocco"] == "ADX"} == {"tutte le combinazioni della griglia sono degeneri"})
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
    check("36. RSI + ATR relativo + X3: 5 × 5 × 2 × 3 × 4 × 4 × 4 × 2 punti, tutti ammessi senza valori degeneri",
          st2.spazio.totale == 5 * 5 * 2 * 3 * 4 * 4 * 4 * 2 and len(st2.punti_ammessi()) == st2.spazio.totale)
    st3 = spazio_teoria(Teoria(1, "E47", ("ADX",), "X0"), b_d, r_d)
    check("37. con una combinazione tolta lo spazio la rifiuta: ammesso dice no", st3.ammesso(
          {"E47": {}, "ADX": {"periodo_barre": 5, "soglia": 30}, "X0": {}}) and not st3.ammesso(
          {"E47": {}, "ADX": {"periodo_barre": 5, "soglia": 15}, "X0": {}}) and len(st3.punti_ammessi()) == 32)
    st4 = spazio_teoria(Teoria(1, "E47", ("ADX",), "X0"), b_d, {})
    check("38. senza valori degeneri: tutti i punti ammessi", len(st4.punti_ammessi()) == 2 * 32)

    # ------------------------------------------------------------------ D1, da leggere
    print("\nD1, barre sintetiche: le combinazioni degeneri tolte")
    d1 = aggiungi_indicatori(sintetici.mercato(12_300, seme=0, minuti=1440, prezzo=30_000))
    std_d1 = config_standard(PERP, "D1")
    c_d1 = Cache(d1, 300)
    b1, r1, tolte1, _, ten1, tab1, t1 = _tutto(std_d1, c_d1)
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
