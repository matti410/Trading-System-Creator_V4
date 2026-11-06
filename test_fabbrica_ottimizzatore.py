"""
Suite di collaudo dell'ottimizzatore della fabbrica (docs/82 §4, lavoro L1).

Si lancia da terminale, dalla cartella del progetto:

    python test_fabbrica_ottimizzatore.py

Non servono dati, MetaTrader 5 o internet: solo funzioni matematiche di prova.
Stampa una riga per collaudo e alla fine «RISULTATO: n/n test superati».

Tolleranze, budget e semi qui sotto sono fissati PRIMA del primo lancio. Le
opzioni dell'ottimizzatore si tarano su altri semi (1000-1049): i semi 0-49 di
questa suite non servono a sceglierle.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import random
import struct
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from engine.fabbrica.funzioni_prova import (FUNZIONI, ackley, obiettivo, rastrigin, rosenbrock, spazio_prova,
                                            sphere)
from engine.fabbrica.ottimizzatore import (AMPIEZZA, PREDEFINITE, Categoria, Esito, Intero, Opzioni, Reale,
                                           Spazio, genetico, griglia_larga)

QUI = Path(__file__).resolve().parent
FILE_OTTIMIZZATORE = QUI / "engine" / "fabbrica" / "ottimizzatore.py"

# ----- Fissati prima del primo lancio: nome -> (funzione, dimensioni, «vicino al minimo»: f <=, budget) -----
COLLAUDI = {
    "Rastrigin 2D": ("rastrigin", 2, 0.5, 2_000),
    "Rastrigin 5D": ("rastrigin", 5, 0.5, 20_000),
    "Sphere 5D": ("sphere", 5, 0.01, 3_000),
    "Rosenbrock 2D": ("rosenbrock", 2, 0.001, 5_000),
    "Ackley 5D": ("ackley", 5, 0.5, 8_000),
}
SEMI = range(50)            # i semi del collaudo
VICINI_MINIMI = 45          # almeno 45 semi su 50 vicino al minimo
BUDGET_AMPIEZZA = 400       # il preset del passo 1: meglio del caso a questo budget, su ognuna
BUDGET_PASSO_1 = 40         # il tetto per teoria del passo 1 (docs/82 P4)
SEME_CASO = 100_000         # la ricerca a caso usa seme + questo numero


def _impronta_esito(e: Esito) -> str:
    """Impronta di tutto l'esito, bit per bit (i float come byte)."""
    testo = json.dumps({"punti": e.punti, "valori": [struct.pack(">d", v).hex() for v in e.valori],
                        "valutazioni": e.valutazioni, "stato": e.stato}, sort_keys=True, allow_nan=False)
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()


def _a_caso(funzione, spazio, budget, seme) -> float:
    """Ricerca a caso, stesso budget e stessa griglia: il minimo trovato."""
    r = np.random.Generator(np.random.PCG64(seme + SEME_CASO))
    indici = np.column_stack([r.integers(0, p.n, budget) for p in spazio.parametri])
    migliore = math.inf
    for riga in indici.tolist():
        v = funzione([p.valore(i) for p, i in zip(spazio.parametri, riga)])
        migliore = min(migliore, v)
    return migliore


def _misto(contatore=None):
    """Interi, reali e categorie, con una zona di NaN. Massimo noto: intero=20, reale=1.5, scelta='b'."""
    spazio = Spazio([Intero("intero", 2, 48, 2), Reale("reale", 0.5, 3.0, 0.25), Categoria("scelta", ("a", "b", None))])
    fuori = []

    def f(p):
        if contatore is not None:
            contatore.append(dict(p))
        if not (2 <= p["intero"] <= 48 and p["intero"] % 2 == 0 and 0.5 <= p["reale"] <= 3.0
                and p["scelta"] in ("a", "b", None)):
            fuori.append(dict(p))
        if p["intero"] > 40:
            return float("nan")
        bonus = {"a": 0.0, "b": 5.0, None: 1.0}[p["scelta"]]
        return bonus - abs(p["intero"] - 20) / 4 - abs(p["reale"] - 1.5)

    return spazio, f, fuori


def esegui() -> int:
    ESITI = []
    t0 = time.perf_counter()

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        print(f"[{'OK ' if condizione else 'KO '}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""), flush=True)

    # ------------------------------------------------------------------ separazione
    print("Separazione dal resto del progetto")
    albero = ast.parse(FILE_OTTIMIZZATORE.read_text(encoding="utf-8"))
    radici, relativi = set(), 0
    for n in ast.walk(albero):
        if isinstance(n, ast.Import):
            radici |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            relativi += n.level > 0
            if n.module:
                radici.add(n.module.split(".")[0])
    estranei = {r for r in radici if r != "numpy" and r not in sys.stdlib_module_names}
    check("1. ottimizzatore.py importa solo libreria standard e numpy", not estranei and not relativi,
          f"importa {sorted(radici)}")
    prova = ("import importlib.util, sys\n"
             f"s = importlib.util.spec_from_file_location('ott', r'{FILE_OTTIMIZZATORE}')\n"
             "m = importlib.util.module_from_spec(s); sys.modules['ott'] = m; s.loader.exec_module(m)\n"
             "print(sorted({'pandas', 'engine', 'talib', 'numba', 'backtesting', 'matplotlib'} & set(sys.modules)))")
    r = subprocess.run([sys.executable, "-c", prova], capture_output=True, text=True, cwd=QUI)
    check("2. caricato da solo non porta con sé né engine né pandas", r.returncode == 0 and r.stdout.strip() == "[]",
          r.stdout.strip() or r.stderr.strip()[-200:])

    # ------------------------------------------------------------------ funzioni di prova
    print("\nLe funzioni di prova")
    check("3. Sphere: valori noti", sphere([0, 0]) == 0 and sphere([1, 2]) == 5)
    check("4. Rastrigin: minimo in zero, valore noto in (1, 0)",
          abs(rastrigin([0, 0])) < 1e-12 and abs(rastrigin([1, 0]) - 1.0) < 1e-9)
    check("5. Rosenbrock: minimo in (1, 1), valore noto in (0, 0)", rosenbrock([1, 1]) == 0 and rosenbrock([0, 0]) == 1)
    check("6. Ackley: minimo in zero, più alto altrove", abs(ackley([0, 0])) < 1e-12 and ackley([1, 1]) > 3.0)
    def sulla_griglia(nome):
        prova_f = FUNZIONI[nome]
        return [p.valore(round((prova_f.minimo_x - p.minimo) / p.passo)) for p in spazio_prova(nome, 2).parametri]

    check("7. il minimo sta sulla griglia di ogni funzione di prova",
          all(abs(FUNZIONI[n].funzione(sulla_griglia(n))) < 1e-6 for n in FUNZIONI))

    # ------------------------------------------------------------------ lo spazio
    print("\nLo spazio")
    i = Intero("i", 2, 11, 3)
    check("8. interi a passo", [i.valore(k) for k in range(i.n)] == [2, 5, 8, 11] and i.n == 4)
    x = Reale("x", 0.0, 1.0, 0.1)
    valori_x = [x.valore(k) for k in range(x.n)]
    check("9. reali a passo, mai oltre il massimo", x.n == 11 and valori_x[-1] <= 1.0 and abs(valori_x[3] - 0.3) < 1e-12
          and all(isinstance(v, float) for v in valori_x))
    c = Categoria("c", ("uno", 2, None))
    check("10. categorie anche di tipo diverso", [c.valore(k) for k in range(c.n)] == ["uno", 2, None])
    check("11. punti totali dello spazio", Spazio([i, x, c]).totale == 4 * 11 * 3)
    errori = 0
    for rotto in (lambda: Intero("a", 5, 1), lambda: Intero("a", 1, 5, 0), lambda: Intero("a", 1.5, 5),
                  lambda: Reale("a", 1.0, 0.0, 0.1), lambda: Reale("a", 0.0, 1.0, 0.0), lambda: Categoria("a", ()),
                  lambda: Categoria("a", ("x", "x")), lambda: Spazio([]), lambda: Spazio([i, Intero("i", 1, 2)])):
        try:
            rotto()
        except ValueError:
            errori += 1
    check("12. spazi sbagliati si fermano con un errore", errori == 9, f"{errori}/9")

    # ------------------------------------------------------------------ griglia
    print("\ngriglia_larga")
    piccolo = Spazio([Intero("a", 1, 3), Categoria("b", ("x", "y"))])
    g = griglia_larga(piccolo, 40, 7)
    check("13. griglia completa se ci sta", len(g) == 6 and {(p["a"], p["b"]) for p in g} ==
          {(a, b) for a in (1, 2, 3) for b in ("x", "y")})
    check("14. griglia completa al limite esatto", len(griglia_larga(piccolo, 6, 7)) == 6)
    g5 = griglia_larga(piccolo, 5, 7)
    check("15. un punto oltre il limite: esattamente punti_max, senza doppioni",
          len(g5) == 5 and len({(p["a"], p["b"]) for p in g5}) == 5)
    grande = Spazio([Intero("a", 0, 999), Reale("b", 0.0, 1.0, 0.001), Categoria("c", ("x", "y", "z", "w"))])
    g = griglia_larga(grande, 400, 3)
    tuple_g = [(p["a"], p["b"], p["c"]) for p in g]
    check("16. spazio grande: esattamente punti_max, senza doppioni", len(g) == 400 and len(set(tuple_g)) == 400)
    per_decile = np.bincount([p["a"] // 100 for p in g], minlength=10)
    per_categoria = [sum(p["c"] == v for p in g) for v in ("x", "y", "z", "w")]
    check("17. punti sparsi in modo uniforme", per_decile.min() >= 35 and per_decile.max() <= 45
          and min(per_categoria) >= 70 and max(per_categoria) <= 130, f"decili {per_decile.min()}-{per_decile.max()}, "
          f"categorie {min(per_categoria)}-{max(per_categoria)}")
    check("18. griglia: stesso seme, stessi punti; seme diverso, punti diversi",
          griglia_larga(grande, 400, 3) == g and griglia_larga(grande, 400, 4) != g)
    check("19. griglia: nessun valore fuori intervallo", all(0 <= p["a"] <= 999 and 0.0 <= p["b"] <= 1.0 for p in g))

    # ------------------------------------------------------------------ regole del genetico
    print("\nLe regole del genetico")
    spazio_r, nomi_r = spazio_prova("rastrigin", 3), [p.nome for p in spazio_prova("rastrigin", 3).parametri]
    f_r = obiettivo(rastrigin, nomi_r)
    chiamate = []

    def conta(p):
        chiamate.append(dict(p))
        return f_r(p)

    e = genetico(conta, spazio_r, 500, 1)
    check("20. il budget si usa esattamente e non si supera", len(chiamate) == 500 == e.valutazioni == len(e.punti) == len(e.valori))
    uniche = {tuple(sorted(p.items())) for p in chiamate}
    check("21. nessun punto rivalutato", len(uniche) == 500)
    check("22. Esito: massimizza, migliore è il valore più alto", e.valore_migliore == max(e.valori)
          and e.migliore == e.punti[e.valori.index(max(e.valori))])
    check("23. Esito: i punti sono quelli passati alla funzione, nell'ordine", e.punti == chiamate)

    chiamate.clear()
    tutto = Spazio([Intero("a", 1, 5), Categoria("b", ("x", "y", "z"))])
    e = genetico(lambda p: chiamate.append(dict(p)) or float(p["a"]), tutto, 1000, 2)
    check("24. spazio piccolo e budget più grande: ogni punto una volta sola, poi si ferma", e.valutazioni == 15 == len(chiamate)
          and len({(p["a"], p["b"]) for p in chiamate}) == 15 and e.esaurito)
    check("25. uno spazio di un punto solo", genetico(lambda p: 1.0, Spazio([Intero("a", 3, 3)]), 10, 0).valutazioni == 1)
    e0 = genetico(f_r, spazio_r, 0, 1)
    check("26. budget zero: nessuna valutazione, nessun migliore", e0.valutazioni == 0 and e0.migliore is None
          and math.isnan(e0.valore_migliore))
    errore = False
    try:
        genetico(f_r, spazio_r, -1, 1)
    except ValueError:
        errore = True
    check("27. budget negativo: errore", errore)

    chiamate.clear()
    e = genetico(lambda p: chiamate.append(1) or float("nan"), spazio_r, 200, 3)
    check("28. tutto NaN: 200 valutazioni contate, nessun migliore, nessun errore", e.valutazioni == 200 == len(chiamate)
          and e.migliore is None and all(math.isnan(v) for v in e.valori))
    e = genetico(lambda p: float("nan") if p[nomi_r[0]] < 0 else f_r(p), spazio_r, 300, 4)
    scartati = sum(math.isnan(v) for v in e.valori)
    check("29. NaN contati, conservati, mai migliori", e.valutazioni == 300 and scartati > 0 and not math.isnan(e.valore_migliore)
          and e.migliore[nomi_r[0]] >= 0, f"{scartati} scartati")
    e = genetico(lambda p: math.inf if p[nomi_r[0]] < 0 else f_r(p), spazio_r, 100, 4)
    check("30. un infinito vale come scartato, non come migliore", math.isfinite(e.valore_migliore) and e.valutazioni == 100)

    # ------------------------------------------------------------------ il seme
    print("\nIl seme")
    a, b, altro = genetico(f_r, spazio_r, 700, 5), genetico(f_r, spazio_r, 700, 5), genetico(f_r, spazio_r, 700, 6)
    check("31. stesso seme, stessi punti, bit per bit", _impronta_esito(a) == _impronta_esito(b))
    check("32. seme diverso, punti diversi", a.punti != altro.punti)
    np.random.seed(11)
    random.seed(11)
    prima_np, prima_py = np.random.get_state()[1].copy(), random.getstate()
    c1 = genetico(f_r, spazio_r, 300, 5)
    griglia_larga(grande, 100, 5)
    check("33. lo stato globale del caso non viene toccato", np.array_equal(prima_np, np.random.get_state()[1])
          and prima_py == random.getstate())
    np.random.seed(99)
    random.seed(99)
    check("34. e non influenza il risultato", _impronta_esito(genetico(f_r, spazio_r, 300, 5)) == _impronta_esito(c1))
    prova = ("import hashlib, json\n"
             "from engine.fabbrica.ottimizzatore import Categoria, Intero, Reale, Spazio, genetico\n"
             "s = Spazio([Intero('i', 0, 50), Reale('r', 0.0, 2.0, 0.01), Categoria('c', ('x', 'y', None))])\n"
             "f = lambda p: -abs(p['i'] - 7) - abs(p['r'] - 1.1) + (p['c'] == 'y')\n"
             "e = genetico(f, s, 300, 8)\n"
             "print(hashlib.sha256(json.dumps(e.stato, sort_keys=True).encode()).hexdigest())\n")
    uscite = []
    for semehash in ("1", "2"):
        r = subprocess.run([sys.executable, "-c", prova], capture_output=True, text=True, cwd=QUI,
                           env=dict(os.environ, PYTHONHASHSEED=semehash))
        uscite.append(r.stdout.strip() or r.stderr.strip()[-200:])
    check("35. stesso risultato in processi diversi, anche con hash di Python diverso",
          uscite[0] == uscite[1] and len(uscite[0]) == 64, uscite[0][:12])

    # ------------------------------------------------------------------ la ripresa
    print("\nInterrotto e ripreso")
    budget = 1000
    intero_e = genetico(f_r, spazio_r, budget, 9)
    pop = PREDEFINITE.popolazione
    tagli = [0, 1, pop - 1, pop, pop + 1, 2 * pop, 333, 999, 1000]
    tutti_ok, conta_ok = True, True
    for taglio in tagli:
        chiamate_a = []
        parte = genetico(lambda p: chiamate_a.append(1) or f_r(p), spazio_r, taglio, 9)
        stato = json.loads(json.dumps(parte.stato, allow_nan=False))
        chiamate_b = []
        fine = genetico(lambda p: chiamate_b.append(1) or f_r(p), spazio_r, budget, 9, stato=stato)
        tutti_ok &= _impronta_esito(fine) == _impronta_esito(intero_e)
        conta_ok &= len(chiamate_a) == taglio and len(chiamate_b) == budget - taglio
    check("36. ripreso dopo il salvataggio in JSON = tutto in una volta, bit per bit", tutti_ok, f"tagli {tagli}")
    check("37. stesso conteggio: le valutazioni fatte prima non si rifanno", conta_ok)
    e = None
    for b_parziale in (37, 41, 200, 201, 655, 1000):
        e = genetico(f_r, spazio_r, b_parziale, 9, stato=None if e is None else json.loads(json.dumps(e.stato)))
    check("38. tante interruzioni di fila = tutto in una volta", _impronta_esito(e) == _impronta_esito(intero_e))

    def f_nan(p):
        return float("nan") if p[nomi_r[1]] < -1 else f_r(p)

    parte = genetico(f_nan, spazio_r, 333, 9)
    fine = genetico(f_nan, spazio_r, 1000, 9, stato=json.loads(json.dumps(parte.stato, allow_nan=False)))
    check("39. ripresa anche con i NaN nello stato", _impronta_esito(fine) == _impronta_esito(genetico(f_nan, spazio_r, 1000, 9)))
    parte = genetico(f_r, spazio_r, 300, 9, AMPIEZZA)
    fine = genetico(f_r, spazio_r, 1000, 9, AMPIEZZA, stato=json.loads(json.dumps(parte.stato)))
    check("40. ripresa anche con il preset ampiezza", _impronta_esito(fine) == _impronta_esito(genetico(f_r, spazio_r, 1000, 9, AMPIEZZA)))
    parte = genetico(f_r, spazio_r, 300, 9)
    chiamate.clear()
    fine = genetico(lambda p: chiamate.append(1) or f_r(p), spazio_r, 100, 9, stato=parte.stato)
    check("41. ripresa con un budget già usato: nessuna valutazione in più", not chiamate and fine.valutazioni == 300)
    errori = 0
    for rotta in (lambda: genetico(f_r, spazio_r, 400, 10, stato=parte.stato),
                  lambda: genetico(f_r, spazio_r, 400, 9, AMPIEZZA, stato=parte.stato),
                  lambda: genetico(f_r, spazio_prova("rastrigin", 4), 400, 9, stato=parte.stato)):
        try:
            rotta()
        except ValueError:
            errori += 1
    check("42. stato di un'altra corsa (seme, opzioni o spazio diversi): errore", errori == 3, f"{errori}/3")
    copia = json.dumps(parte.stato, sort_keys=True)
    genetico(f_r, spazio_r, 400, 9, stato=parte.stato)
    check("43. lo stato ricevuto non viene modificato", json.dumps(parte.stato, sort_keys=True) == copia)
    check("44. lo stato è JSON puro, senza NaN", json.dumps(genetico(lambda p: float("nan"), spazio_r, 50, 1).stato, allow_nan=False) != "")

    # ------------------------------------------------------------------ opzioni
    print("\nLe opzioni")
    errori = 0
    for rotta in (dict(popolazione=1), dict(elite=-1), dict(popolazione=10, elite=10), dict(torneo=0), dict(incrocio=1.5),
                  dict(mutazione=-0.1), dict(azzera=2.0), dict(immigrati=1.5), dict(salto=0.0), dict(decadi=-1.0), dict(tentativi=0)):
        try:
            Opzioni(**rotta)
        except ValueError:
            errori += 1
    check("45. opzioni fuori intervallo: errore", errori == 11, f"{errori}/11")
    check("46. il preset ampiezza ha più mutazione e meno eredità", AMPIEZZA.mutazione > PREDEFINITE.mutazione
          and AMPIEZZA.incrocio < PREDEFINITE.incrocio)

    # ------------------------------------------------------------------ spazi misti
    print("\nSpazi con interi, reali, categorie e NaN")
    for nome_opz, opz in (("predefinite", PREDEFINITE), ("ampiezza", AMPIEZZA)):
        fuori_tot, doppi, nan_visti, scoperti = 0, 0, 0, 0
        for seme in SEMI:
            visti = []
            spazio, f, fuori = _misto(visti)
            e = genetico(f, spazio, 300, seme, opz)
            fuori_tot += len(fuori)
            doppi += len(visti) - len({(p["intero"], p["reale"], p["scelta"]) for p in visti})
            nan_visti += sum(math.isnan(v) for v in e.valori)
            scoperti += e.migliore == {"intero": 20, "reale": 1.5, "scelta": "b"}
        check(f"47. misto, {nome_opz}: nessun errore, nessun valore fuori intervallo, nessun doppione",
              fuori_tot == 0 and doppi == 0 and nan_visti > 0, f"{nan_visti} NaN su 50 semi")
        check(f"48. misto, {nome_opz}: trova il massimo noto in almeno 45 semi su 50", scoperti >= VICINI_MINIMI, f"{scoperti}/50")

    # ------------------------------------------------------------------ il collaudo di docs/82 §4
    print("\nLe funzioni di prova: almeno 45 semi su 50 e meglio della ricerca a caso")
    for nome, (funzione, dim, tolleranza, budget) in COLLAUDI.items():
        t1 = time.perf_counter()
        fn = FUNZIONI[funzione].funzione
        spazio = spazio_prova(funzione, dim)
        f = obiettivo(fn, [p.nome for p in spazio.parametri])
        minimi = [-genetico(f, spazio, budget, s).valore_migliore for s in SEMI]
        caso = [_a_caso(fn, spazio, budget, s) for s in SEMI]
        vicini = sum(m <= tolleranza for m in minimi)
        print(f"      {nome}: budget {budget}, tolleranza f <= {tolleranza}: {vicini}/50 vicini; "
              f"media {np.mean(minimi):.5f}, a caso {np.mean(caso):.5f} ({time.perf_counter() - t1:.0f} s)")
        check(f"49. {nome}: vicino al minimo in almeno {VICINI_MINIMI} semi su 50", vicini >= VICINI_MINIMI, f"{vicini}/50")
        check(f"50. {nome}: meglio della ricerca a caso, in media", np.mean(minimi) < np.mean(caso))

    # ------------------------------------------------------------------ il preset ampiezza
    print(f"\nIl preset ampiezza (passo 1: {BUDGET_PASSO_1} prove per teoria)")
    for nome, (funzione, dim, _, _) in COLLAUDI.items():
        fn = FUNZIONI[funzione].funzione
        spazio = spazio_prova(funzione, dim)
        f = obiettivo(fn, [p.nome for p in spazio.parametri])
        minimi = [-genetico(f, spazio, BUDGET_AMPIEZZA, s, AMPIEZZA).valore_migliore for s in SEMI]
        caso = [_a_caso(fn, spazio, BUDGET_AMPIEZZA, s) for s in SEMI]
        check(f"51. {nome}: ampiezza meglio della ricerca a caso a {BUDGET_AMPIEZZA} prove", np.mean(minimi) < np.mean(caso),
              f"{np.mean(minimi):.3f} contro {np.mean(caso):.3f}")

    def dispersione(opz):
        spazio = spazio_prova("rastrigin", 5)
        nomi = [p.nome for p in spazio.parametri]
        f = obiettivo(rastrigin, nomi)
        return np.mean([np.mean(np.std([[p[n] for n in nomi] for p in genetico(f, spazio, BUDGET_AMPIEZZA, s, opz).punti[-100:]],
                                       axis=0)) for s in SEMI])

    d_amp, d_pre = dispersione(AMPIEZZA), dispersione(PREDEFINITE)
    check("52. ampiezza continua a esplorare: nelle ultime 100 prove i punti sono più sparsi", d_amp > d_pre,
          f"{d_amp:.2f} contro {d_pre:.2f}")
    e = genetico(f_r, spazio_r, BUDGET_PASSO_1, 0, AMPIEZZA)
    check(f"53. ampiezza: budget di {BUDGET_PASSO_1} rispettato, senza doppioni", e.valutazioni == BUDGET_PASSO_1
          and len({tuple(sorted(p.items())) for p in e.punti}) == BUDGET_PASSO_1)

    print("\n" + "=" * 70)
    print(f"Durata: {time.perf_counter() - t0:.0f} s")
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (numpy {np.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
