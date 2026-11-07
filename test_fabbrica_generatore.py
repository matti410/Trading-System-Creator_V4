"""
Suite di collaudo del generatore della fabbrica (docs/82 P3 e P-L2, lavoro L3a): teorie, famiglie, valori degeneri e
spazio del passo 1.

Si lancia da terminale, dalla cartella del progetto:

    python test_fabbrica_generatore.py

Solo dati sintetici (engine/fabbrica/sintetici.py): non servono i file in dati/, MetaTrader 5 o internet. Stampa una
riga per collaudo e alla fine «RISULTATO: n/n test superati».
"""
from __future__ import annotations

import itertools
import math
import sys
import time
import warnings

import numpy as np
import pandas as pd

from engine import registry as reg
from engine.fabbrica import generatore as gen
from engine.fabbrica import sintetici
from engine.fabbrica.blocchi import Blocco, blocchi_da_config
from engine.fabbrica.cache import Cache
from engine.fabbrica.config import config_standard, controlla_budget
from engine.fabbrica.generatore import (ControlloDegenerazione, Teoria, genera_teorie, lati_config, misura_famiglie,
                                        resoconto_teorie, seme_teoria, spazio_teoria, stato_registro, togli_degeneri)
from engine.fabbrica.ottimizzatore import Categoria, Intero
from engine.indicatori import aggiungi_indicatori

warnings.simplefilter("ignore")

PERP, SPOT = "BINANCE_PERP_BTCUSDT", "BYBIT_SPOT_ETHUSDT"


def _config(symbol, blocchi, modelli=((0, 2),), lati=("long", "short")) -> dict:
    cfg = config_standard(symbol, "M15")
    cfg["blocchi"] = {n: dict(g) for n, g in blocchi.items()}
    cfg["modelli"] = [{"trigger": 1, "filtri": list(m), "uscite": 1} for m in modelli]
    cfg["lati"] = list(lati)
    return cfg


def _tutto(cfg, cache):
    blocchi = blocchi_da_config(cfg)
    lati = lati_config(cfg)
    rimaste, tolte = togli_degeneri(blocchi, cache, lati)
    famiglie, misura = misura_famiglie(blocchi, cache, lati)
    teorie = genera_teorie(cfg, blocchi, famiglie, rimaste)
    return blocchi, rimaste, tolte, famiglie, misura, teorie


def _uguale_registro(a: dict, b: dict) -> bool:
    return all(list(a[k].items()) == list(b[k].items()) for k in a)


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

    df = aggiungi_indicatori(sintetici.mercato(20_300, seme=1, minuti=15, prezzo=30_000))
    cache = Cache(df, 600)

    # ------------------------------------------------------------------ il conto a mano
    print("Il conto delle teorie, su una lista fatta a mano")
    piccola = {"E47": {}, "DONCHIAN": {}, "F3_VOLUME_ABOVE_AVG": {}, "ADX": {}, "ATR_RELATIVO": {}, "X0": {}, "X3": {}}
    cfg = _config(PERP, piccola)
    blocchi, rimaste, tolte, famiglie, misura, teorie = _tutto(cfg, cache)
    scelte = ["-", "F3_VOLUME_ABOVE_AVG", "ADX", "ATR_RELATIVO", "F3_VOLUME_ABOVE_AVG+ADX", "F3_VOLUME_ABOVE_AVG+ATR_RELATIVO"]
    attese = [f"L|{t}|{f}|{u}" for t in ("E47", "DONCHIAN") for f in scelte for u in ("X0", "X3")]
    check("1. 2 trigger × (1 + 3 filtri + 2 coppie, ADX con ATR relativo no) × 2 uscite = 24 per lato, 48 in tutto, in quest'ordine",
          len(teorie) == 48 and [t.id for t in teorie if t.lato == 1] == attese and [t.id for t in teorie if t.lato == -1]
          == [a.replace("L|", "S|", 1) for a in attese], f"{len(teorie)} teorie")
    due = genera_teorie(_config(PERP, piccola, modelli=((0, 0), (2, 2))), blocchi, famiglie, rimaste)
    sovrapposti = genera_teorie(_config(PERP, piccola, modelli=((0, 1), (1, 2))), blocchi, famiglie, rimaste)
    check("2. due modelli (T+U e T+F+F+U): 2 × (1 + 2) × 2 = 12 per lato; modelli che si sovrappongono non contano doppio",
          len(due) == 24 and len(sovrapposti) == 48 and {t.id for t in sovrapposti} == {t.id for t in teorie},
          f"{len(due)} e {len(sovrapposti)} teorie")
    check("3. un id per teoria, leggibile e senza doppi", len({t.id for t in teorie}) == len(teorie)
          and Teoria(1, "E47", ("F3_VOLUME_ABOVE_AVG", "ADX"), "X3").id == "L|E47|F3_VOLUME_ABOVE_AVG+ADX|X3"
          and Teoria(-1, "E5", (), "X0").id == "S|E5|-|X0")

    # ------------------------------------------------------------------ la config standard
    print("\nLa config standard (lista di P-L2)")
    std = config_standard(PERP, "M15")
    prima = stato_registro()                     # il catalogo è già registrato dalle maschere qui sopra
    b_std, r_std, tolte_std, f_std, m_std, t_std = _tutto(std, cache)
    dopo = stato_registro()
    res = resoconto_teorie(std, b_std, f_std, r_std, t_std)
    check("4. 1.176 teorie, 588 per lato, sotto il budget (96.840 prove)", len(t_std) == 1176 and res["per_lato"] == {"long": 588, "short": 588}
          and controlla_budget(len(t_std), std) == 96_840, str(res["per_lato"]))
    check("5. il resoconto dice perché: solo ADX con ATR relativo è escluso, sui due lati; nessun blocco uscito",
          res["coppie_stessa_famiglia"] == [{"lato": "long", "filtri": ["ADX", "ATR_RELATIVO"], "famiglia": "ADX"},
                                             {"lato": "short", "filtri": ["ADX", "ATR_RELATIVO"], "famiglia": "ADX"}]
          and res["blocchi_usciti"] == [], "degeneri sulle barre sintetiche M15: " + "; ".join(
              f"{x['blocco']} {x['lato']} {x['valori']} {x['esito']} {x['quota_vere']:.1%}" for x in tolte_std))
    stesse = [t.id for t in t_std if len({f_std[t.lato][f] for f in t.filtri}) < len(t.filtri)]
    check("6. nessuna teoria con due filtri della stessa famiglia", not stesse)
    check("7. il registro delle condizioni è identico prima e dopo famiglie e degenerazione", _uguale_registro(prima, dopo))
    di_nuovo = _tutto(std, cache)
    check("8. stesso ordine e stesse famiglie a ogni giro", [t.id for t in di_nuovo[5]] == [t.id for t in t_std] and di_nuovo[3] == f_std)
    spot = config_standard(SPOT, "M15")
    _, r_sp, _, f_sp, _, t_sp = _tutto(spot, cache)
    forzata = {**spot, "lati": ["long", "short"]}
    check("9. spot: 588 teorie, tutte long; anche con lo short scritto nei lati", len(t_sp) == 588 and all(t.lato == 1 for t in t_sp)
          and all(t.lato == 1 for t in genera_teorie(forzata, b_std, f_std, r_std)))

    # ------------------------------------------------------------------ le famiglie
    print("\nLe famiglie: misura o dichiarazione (decisione del 07/11)")
    fam = m_std.set_index(["lato", "blocco"])
    check("10. ADX e ATR relativo: gruppi diversi nella misura, stessa famiglia perché dichiarati insieme",
          fam.loc[("long", "ADX"), "gruppo_misurato"] != fam.loc[("long", "ATR_RELATIVO"), "gruppo_misurato"]
          and f_std[1]["ADX"] == f_std[1]["ATR_RELATIVO"] == "ADX" and f_std[-1]["ADX"] == f_std[-1]["ATR_RELATIVO"])
    incoerenti = []
    for lato, gruppo in m_std.groupby("lato"):
        for (_, a), (_, c) in itertools.combinations(gruppo.iterrows(), 2):
            if a["tipo"] == c["tipo"] and (a["gruppo_misurato"] == c["gruppo_misurato"] or a["dichiarata"] == c["dichiarata"]):
                if a["famiglia"] != c["famiglia"]:
                    incoerenti.append((lato, a["blocco"], c["blocco"]))
    misurate = [(r.lato, r.blocco) for r in m_std.itertuples() if r.famiglia != r.blocco and r.dichiarata != "forza del trend e volatilita relativa"]
    check("11. blocchi uniti dalla misura stanno nella stessa famiglia", not incoerenti,
          f"uniti dalla misura: {misurate}" if misurate else "nessuno unito dalla sola misura")
    check("12. le famiglie si misurano per lato, trigger con trigger e filtri con filtri", set(m_std["lato"]) == {"long", "short"}
          and set(m_std["tipo"]) == {"trigger", "filtro"} and len(m_std) == 2 * 14)

    # ------------------------------------------------------------------ il seme
    print("\nIl seme della teoria")
    semi = {t.id: seme_teoria(7, t.id) for t in t_std}
    rovescio = {t.id: seme_teoria(7, t.id) for t in reversed(t_std)}
    check("13. seme della ricerca + id: non dipende dall'ordine; cambia con l'id e con il seme della ricerca",
          semi == rovescio and len(set(semi.values())) == len(semi) and seme_teoria(8, t_std[0].id) != semi[t_std[0].id]
          and all(isinstance(s, int) and 0 <= s < 2**60 for s in semi.values()))

    # ------------------------------------------------------------------ i valori degeneri
    print("\nI valori degeneri (decisione del 07/11)")
    con_adx = dict(piccola, ADX={"periodo_ore": [1.25], "soglia": [15, 30]})
    b_d, r_d, tolte_d, f_d, _, t_d = _tutto(_config(PERP, con_adx), cache)
    riga = [t for t in tolte_d if t["blocco"] == "ADX"]
    check("14. ADX a 5 barre: la soglia 15 è quasi sempre vera e si toglie, una volta per i due lati; la 30 resta",
          len(riga) == 1 and riga[0]["valori"] == {"periodo_barre": 5, "soglia": 15} and riga[0]["lato"] == "entrambi"
          and riga[0]["esito"] == "QUASI_SEMPRE_VERA" and riga[0]["quota_vere"] >= 0.95
          and r_d[("ADX", 1)] == r_d[("ADX", -1)] == ({"periodo_barre": 5, "soglia": 30},), str(riga))
    t_adx = next(t for t in t_d if t.filtri == ("ADX",) and t.lato == 1)
    st = spazio_teoria(t_adx, b_d, r_d)
    check("15. lo spazio segue la griglia rimasta: ADX.soglia ha solo 30", st._valori["ADX.soglia"] == (30,)
          and st._valori["ADX.periodo_barre"] == (5,))
    vuoto = dict(piccola, ADX={"periodo_ore": [1.25], "soglia": [15, 20]})
    b_v, r_v, tolte_v, f_v, _, t_v = _tutto(_config(PERP, vuoto), cache)
    res_v = resoconto_teorie(_config(PERP, vuoto), b_v, f_v, r_v, t_v)
    check("16. tutte le combinazioni degeneri: il blocco esce dalla config, e il resoconto lo dice",
          not any("ADX" in t.filtri for t in t_v) and len(t_v) == 2 * 2 * (1 + 2 + 1) * 2
          and {(x["blocco"], x["lato"]) for x in res_v["blocchi_usciti"]} == {("ADX", "long"), ("ADX", "short")})
    salita = aggiungi_indicatori(sintetici.mercato(20_300, seme=6, minuti=15, prezzo=30_000, spinta=np.full(20_300, 0.0005)))
    c_sal = Cache(salita, 300)
    b_l = blocchi_da_config({"timeframe": "M15", "blocchi": {"DONCHIAN": {"canale_ore": [24, 2500]}}})
    r_l, tolte_l = togli_degeneri(b_l, c_sal, [1, -1])
    check("17. per lato: su un mercato che sale molto il canale di 10.000 barre non scatta mai sullo short ed esce solo da lì",
          tolte_l == [{"blocco": "DONCHIAN", "lato": "short", "valori": {"canale_barre": 10000}, "esito": "SEMPRE_FALSA",
                       "quota_vere": 0.0}] and r_l[("DONCHIAN", 1)] == ({"canale_barre": 96}, {"canale_barre": 10000})
          and r_l[("DONCHIAN", -1)] == ({"canale_barre": 96},), str(tolte_l))
    uscita = next(b for b in b_std if b.nome == "X0")
    ctl = ControlloDegenerazione(cache)
    check("18. le uscite non passano dal controllo (decisione del 07/11): errore se ci si prova, nessuna riga nell'elenco",
          errore(lambda: ctl.esiti([(uscita, 1, {"durata_barre": 4, "perc_stop": 90, "target": None})]))
          and not any(t["blocco"] in ("X0", "X1", "X3") for t in tolte_std))
    rotto = Blocco("ROTTO", "filtro", "rotto", 15, (Intero("p_barre", 5, 5, 1),), {"p_barre": (5,)}, neutro=True,
                   _calcola=lambda c, l, v: 1 / 0)
    prima_r = stato_registro()
    check("19. un blocco che va in errore non è un valore da togliere: si ferma", errore(lambda: ctl.esiti([(rotto, 1, {"p_barre": 5})]))
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
    check("20. una combinazione già misurata non si rimisura", n_prima >= 1 and len(chiamate) == n_prima, f"{n_prima} misure, poi nessuna")

    # ------------------------------------------------------------------ lo spazio del passo 1
    print("\nLo spazio del passo 1, sui valori larghi")
    st1 = spazio_teoria(Teoria(1, "E47", (), "X0"), b_std, r_std)
    nomi = [p.nome for p in st1.spazio.parametri]
    punti = st1.punti_ammessi()
    valori = [st1.valori(p)["X0"] for p in punti]
    check("21. E47 + X0: durata, stop e target; 4 × 4 × 2 = 32 punti, i valori della griglia larga",
          nomi == ["X0.durata_barre", "X0.perc_stop", "X0.target"] and len(punti) == 32
          and isinstance(st1.spazio.parametri[0], Intero) and isinstance(st1.spazio.parametri[2], Categoria)
          and sorted({v["durata_barre"] for v in valori}) == [4, 8, 16, 32] and {v["target"] for v in valori} == {None, 90}
          and st1.valori(punti[0]) == {"E47": {}, "X0": {"durata_barre": 4, "perc_stop": 70, "target": None}})
    st2 = spazio_teoria(Teoria(-1, "RSI_RIENTRO", ("ATR_RELATIVO",), "X3"), b_std, r_std)
    check("22. RSI + ATR relativo + X3: 5 × 5 × 2 × 3 × 4 × 4 × 4 × 2 punti, tutti ammessi senza valori degeneri",
          st2.spazio.totale == 5 * 5 * 2 * 3 * 4 * 4 * 4 * 2 and len(st2.punti_ammessi()) == st2.spazio.totale)
    st3 = spazio_teoria(Teoria(1, "E47", ("ADX",), "X0"), b_d, r_d)
    check("23. con una combinazione tolta lo spazio la rifiuta: ammesso dice no", st3.ammesso(
          {"E47": {}, "ADX": {"periodo_barre": 5, "soglia": 30}, "X0": {}}) and not st3.ammesso(
          {"E47": {}, "ADX": {"periodo_barre": 5, "soglia": 15}, "X0": {}}) and len(st3.punti_ammessi()) == 32)
    st4 = spazio_teoria(Teoria(1, "E47", ("ADX",), "X0"), b_d, {})
    check("24. senza valori degeneri: tutti i punti ammessi", len(st4.punti_ammessi()) == 2 * 32)

    # ------------------------------------------------------------------ D1, da leggere
    print("\nD1, barre sintetiche: le combinazioni degeneri tolte")
    d1 = aggiungi_indicatori(sintetici.mercato(12_300, seme=0, minuti=1440, prezzo=30_000))
    std_d1 = config_standard(PERP, "D1")
    c_d1 = Cache(d1, 300)
    b1, r1, tolte1, f1, _, t1 = _tutto(std_d1, c_d1)
    elenco = "; ".join(f"{x['blocco']} {x['lato']} {x['valori']} {x['esito']} {x['quota_vere']:.1%}" for x in tolte1)
    coerenti = all((x["esito"] == "QUASI_SEMPRE_VERA" and x["quota_vere"] >= 0.95) or (x["esito"] == "SEMPRE_FALSA" and x["quota_vere"] == 0)
                   or x["esito"] in ("RARA", "SEMPRE_VERA") for x in tolte1)
    adx = [p for p in spazio_teoria(next(t for t in t1 if "ADX" in t.filtri), b1, r1).spazio.parametri if p.nome == "ADX.soglia"]
    check("25. su D1 le combinazioni tolte hanno esiti coerenti con la quota, e lo spazio di ADX parte dalla soglia rimasta",
          tolte1 and coerenti and adx and r1[("ADX", 1)] and min(c["soglia"] for c in r1[("ADX", 1)]) > 15,
          f"{len(t1)} teorie; tolte: {elenco}")

    print("\n" + "=" * 70)
    print(f"Durata: {time.perf_counter() - t0:.0f} s")
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
