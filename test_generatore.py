"""
Suite di collaudo del generatore di indicatori e trigger, prezzo + volume (15/11/2026, docs/83).
Moduli: engine/generatore/ (ricette.py, trigger.py, catalogo.py, __main__.py).

Cosa verifica (docs/50 §7)
--------------------------
A  le ricette: al massimo 3 operazioni, finestre 5, 14, 50, 200, sempre prezzo + volume (sv vale per tutti e due),
   tp solo dentro delta, zscore e rango, ordine fisso dalle piu' semplici, stesso elenco a ogni lancio, regole di
   scrittura (A×B = B×A, A−B = −(B−A), abs di una serie mai negativa);
B  i calcoli rifatti a mano, barra per barra, con cicli semplici: ingredienti (pos 0,5 se High = Low, v sulla
   mediana di 50 barre, delta di tp in rapporto), media, dev, zscore, rango, delta, corr, ÷ protetto;
C  i trigger: percentile mobile su 500 barre con la barra ESCLUSA, media 20 barre con la barra compresa,
   attraversamenti nei due versi, solo la prima barra, long e short con la stessa serie, nomi e famiglia;
D  il catalogo: stesso file a ogni lancio, il tetto piu' piccolo e' l'inizio di quello piu' grande, ricette uguali
   tolte (somma = media sulla stessa finestra; ar × v = r × sv), nessuna coppia tenuta con gli stessi trigger sul
   sintetico, vincolo rispettato, conteggi coerenti, file salvato e riletto con gli stessi trigger, comando senza N;
E  verifica_lookahead (troncamento) su ricette da 1, 2 e 3 operazioni che usano tutte le operazioni e tutti gli
   ingredienti, con una trappola che guarda avanti: la trappola e' LOOKAHEAD, i trigger generati OK;
F  verifica_degenerazione: i degeneri sono segnalati (non tolti), l'esito sul sintetico sta nel catalogo, il
   registro del motore torna com'era.

Come si lancia (da terminale, dalla cartella del progetto):

    python test_generatore.py

Non serve la rete ne' i dati veri. Alla fine stampa «RISULTATO: N/N test superati».
"""
from __future__ import annotations

import contextlib
import io
import itertools
import json
import pickle
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.simplefilter("ignore")

from engine import registry as reg
from engine.generatore import catalogo as C
from engine.generatore import ricette as R
from engine.generatore import trigger as T
from engine.generatore.__main__ import main as comando

ESITI: list[bool] = []


def check(nome, condizione, dettaglio=""):
    ESITI.append(bool(condizione))
    print(f"  [{'OK' if condizione else 'FALLITO'}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""))


def muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def ing(n):
    return ("ing", n)


# ------------------------------------------------------------ sezione A --
def sezione_a():
    print("\nA · Le ricette: limiti, vincolo, ordine, regole di scrittura")
    prime = list(itertools.islice(R.elenca(), 60000))     # tutte quelle da 1 e 2 operazioni e l'inizio delle 3
    valide = [e for e, m in prime if m is None]
    ops = [R.n_operazioni(e) for e, _ in prime]
    check("A1. al massimo 3 operazioni, e l'elenco va da 1 a 2 a 3 senza tornare indietro",
          max(ops) <= 3 and ops == sorted(ops) and set(ops) == {1, 2, 3}, f"{dict(pd.Series(ops).value_counts())}")
    fin = {n for e in valide for n in R.finestre(e)}
    check("A2. finestre solo 5, 14, 50, 200 barre", fin == {5, 14, 50, 200}, str(sorted(fin)))

    def tp_ok(e, padre=None):
        if e == ing("tp"):
            return padre is not None and padre[0] == "t" and padre[1] in ("delta", "zscore", "rango")
        return all(tp_ok(x, e) for x in e[2:] if isinstance(x, tuple))
    check("A3. tp entra solo come argomento diretto di delta, zscore e rango", all(tp_ok(e) for e in valide))
    con_vincolo = [e for e in valide if R.rispetta_vincolo(e)]
    check("A4. il vincolo prezzo + volume: «media(r, 14)» e «media(v, 14)» no, «media(sv, 14)», «r × v», "
          "«zscore(tp, 50) × v» si'",
          not R.rispetta_vincolo(("t", "media", 14, ing("r"))) and not R.rispetta_vincolo(("t", "media", 14, ing("v")))
          and R.rispetta_vincolo(("t", "media", 14, ing("sv"))) and R.rispetta_vincolo(("b", "mul", ing("r"), ing("v")))
          and R.rispetta_vincolo(("b", "mul", ("t", "zscore", 50, ing("tp")), ing("v"))))
    seconde = list(itertools.islice(R.elenca(), 60000))
    check("A5. lo stesso elenco a ogni lancio (60.000 ricette, stesso ordine, stessi motivi)", prime == seconde)
    testi = [R.testo(e) for e in valide]
    check("A6. nessuna ricetta scritta due volte", len(testi) == len(set(testi)))
    tutte = {R.testo(e): m for e, m in prime}
    check("A7. regole di scrittura: «r × v» tenuta e «v × r» tolta; «r − v» tenuta e «v − r» tolta; «r ÷ v» e "
          "«v ÷ r» tenute tutte e due",
          tutte.get("r × v") is None and tutte.get("v × r") is not None and tutte.get("r − v") is None
          and tutte.get("v − r") is not None and tutte.get("r ÷ v") is None and tutte.get("v ÷ r") is None)
    check("A8. abs di una serie mai negativa, abs(r) = ar, abs(sv) = v, segno(sv) = segno(r), «v × v», "
          "corr(x, x) tolte per scrittura",
          all(tutte.get(t) is not None for t in ("abs(v)", "abs(ar)", "abs(r)", "abs(sv)", "segno(sv)", "v × v",
                                                 "corr(r, r, 14)")) and tutte.get("segno(r)") is None
          and tutte.get("abs(corpo)") is None)
    check("A9. l'ordine dentro le ricette da 1 operazione: nel tempo, correlazione, fra due serie, di forma",
          [k for k, _ in itertools.groupby(e[0] for e, _ in prime if R.n_operazioni(e) == 1)] == ["t", "corr", "b", "f"])
    check("A10. testo leggibile: «zscore(r × v, 50)», «(r × v) ÷ media(v, 14)», «corr(r, v, 14)»",
          R.testo(("t", "zscore", 50, ("b", "mul", ing("r"), ing("v")))) == "zscore(r × v, 50)"
          and R.testo(("b", "div", ("b", "mul", ing("r"), ing("v")), ("t", "media", 14, ing("v"))))
          == "(r × v) ÷ media(v, 14)" and R.testo(("corr", 14, ing("r"), ing("v"))) == "corr(r, v, 14)")
    check("A11. famiglie dichiarate dagli ingredienti di prezzo",
          R.famiglia(("t", "media", 14, ing("sv"))) == "volume-pressione"
          and R.famiglia(("b", "mul", ing("rng"), ing("v"))) == "volume-conferma"
          and R.famiglia(("b", "mul", ("t", "zscore", 50, ing("tp")), ing("v"))) == "volume-momento"
          and R.famiglia(("b", "mul", ing("rng"), ing("sv"))) == "volume-pressione+conferma")
    check("A12. ogni ricetta tenuta con il vincolo ha almeno un ingrediente di prezzo e uno di volume",
          all(R.ingredienti(e) & R.PREZZO and R.ingredienti(e) & R.VOLUME for e in con_vincolo))


# ------------------------------------------------------------ sezione B --
def sezione_b():
    print("\nB · I calcoli rifatti a mano, barra per barra")
    d = C.dataset_sintetico(barre=900, seme=5)
    for k in ("High", "Low", "Close"):                     # barra 300 piatta: High = Low = Open = Close
        d.iloc[300, d.columns.get_loc(k)] = d.iloc[300, d.columns.get_loc("Open")]
    o, h, l, c, vol = (d[k].to_numpy() for k in ("Open", "High", "Low", "Close", "Volume"))
    n = len(d)
    rr = np.full(n, np.nan)
    pos = np.full(n, np.nan)
    v = np.full(n, np.nan)
    for i in range(n):
        if i:
            rr[i] = np.log(c[i] / c[i - 1])
        pos[i] = 0.5 if h[i] == l[i] else (c[i] - l[i]) / (h[i] - l[i])
        if i >= 49:
            v[i] = vol[i] / np.median(vol[i - 49:i + 1])
    sv = np.sign(rr) * v
    tp = (h + l + c) / 3
    val = lambda e: R.calcola(e, d).to_numpy()  # noqa: E731
    vicini = lambda a, b: bool(np.allclose(a, b, equal_nan=True, rtol=1e-9, atol=1e-12))  # noqa: E731
    check("B1. ingredienti r, pos (0,5 sulla barra con High = Low), v (mediana di 50 barre), sv",
          vicini(val(ing("r")), rr) and vicini(val(ing("pos")), pos) and pos[300] == 0.5
          and vicini(val(ing("v")), v) and vicini(val(ing("sv")), sv))
    N = 14
    media, dev, z, rango, delta, corr = (np.full(n, np.nan) for _ in range(6))
    for i in range(N - 1, n):
        w = sv[i - N + 1:i + 1]
        if np.isfinite(w).all():
            media[i], dev[i] = w.mean(), w.std()
            z[i] = (sv[i] - w.mean()) / w.std()
            rango[i] = (np.sum(w < sv[i]) + (np.sum(w == sv[i]) + 1) / 2) / N
        a, b = rr[i - N + 1:i + 1], v[i - N + 1:i + 1]
        if np.isfinite(a).all() and np.isfinite(b).all():
            corr[i] = np.corrcoef(a, b)[0, 1]
        if i >= N:
            delta[i] = np.log(tp[i] / tp[i - N])
    check("B2. media, dev (popolazione) e zscore di sv su 14 barre", vicini(val(("t", "media", N, ing("sv"))), media)
          and vicini(val(("t", "dev", N, ing("sv"))), dev) and vicini(val(("t", "zscore", N, ing("sv"))), z))
    check("B3. rango di sv su 14 barre (quota della finestra sotto la barra, pari a meta')",
          vicini(val(("t", "rango", N, ing("sv"))), rango))
    check("B4. delta di tp in rapporto: log(tp / tp di 14 barre fa)", vicini(val(("t", "delta", N, ing("tp"))), delta))
    check("B5. corr(r, v, 14)", np.allclose(val(("corr", N, ing("r"), ing("v"))), corr, equal_nan=True, atol=1e-7))
    zero = d.copy()
    zero.iloc[400, zero.columns.get_loc("Close")] = zero.iloc[399]["Close"]      # r = 0 sulla barra 400
    q = R.calcola(("b", "div", ing("v"), ing("r")), zero)
    check("B6. ÷ protetto dallo zero: v ÷ r e' NaN dove r = 0, finito altrove",
          np.isnan(q.iloc[400]) and np.isfinite(q.iloc[450]))


# ------------------------------------------------------------ sezione C --
def sezione_c():
    print("\nC · I trigger: livelli, attraversamenti, eventi, lati")
    d = C.dataset_sintetico(barre=1500, seme=9)
    e = ("t", "zscore", 14, ing("sv"))
    x = R.calcola(e, d).to_numpy()
    p25 = T.livello(pd.Series(x, index=d.index), "P25").to_numpy()
    m20 = T.livello(pd.Series(x, index=d.index), "MEDIA20").to_numpy()
    ok_p = ok_m = True
    for i in (700, 900, 1234, 1499):
        ok_p &= np.isclose(p25[i], np.quantile(x[i - 500:i], 0.25))          # le 500 barre PRIMA, barra esclusa
        ok_m &= np.isclose(m20[i], x[i - 19:i + 1].mean())                   # 20 barre con la barra
    check("C1. percentile mobile su 500 barre con la barra esclusa; media 20 barre con la barra", ok_p and ok_m)
    s = pd.Series([0.0, 1.0, 2.0, 1.0, -1.0, 0.0, 1.0, 1.0])
    su, giu = T.attraversa(s, 0.5, "SU").tolist(), T.attraversa(s, 0.5, "GIU").tolist()
    check("C2. attraversamenti a mano: sale sopra 0,5 alle barre 1 e 6, scende sotto alle barre 4",
          su == [False, True, False, False, False, False, True, False]
          and giu == [False, False, False, False, True, False, False, False])
    voce = C.voce_ricetta("G0099", e)
    cat = {"ricette": [voce]}
    lunghi, corti = C.trigger_del_catalogo(cat)
    out = {k: f(d) for k, f in {**lunghi, **corti}.items()}
    check("C3. 28 trigger per un indicatore con segno (7 livelli × 2 versi × 2 lati), 24 senza (rango)",
          len(out) == 28 and len(C.voce_ricetta("G0098", ("t", "rango", 14, ing("sv")))["trigger"]) == 24)
    check("C4. ogni trigger e' una Series booleana con l'indice del df",
          all(isinstance(s, pd.Series) and s.dtype == bool and s.index.equals(d.index) for s in out.values()))
    check("C5. eventi, non stati: mai due barre vere di fila",
          all(not (s & s.shift(1, fill_value=False)).any() for s in out.values()))
    check("C6. long e short dello stesso attraversamento hanno la stessa serie; nomi G0099_P25_SU e "
          "G0099_SHORT_P25_SU", "G0099_P25_SU" in lunghi and out["G0099_P25_SU"].equals(out["G0099_SHORT_P25_SU"])
          and all(out[k].equals(out[k.replace("G0099_", "G0099_SHORT_")]) for k in lunghi))
    f = lunghi["G0099_P25_SU"]
    atteso = pd.Series(x, index=d.index)
    atteso = (atteso > pd.Series(p25, index=d.index)) & (atteso.shift(1) <= pd.Series(p25, index=d.index).shift(1))
    check("C7. il trigger P25 verso l'alto e' l'attraversamento rifatto a mano", f(d).equals(atteso.fillna(False)))
    g = pickle.loads(pickle.dumps(f))
    check("C8. il trigger si puo' passare a un altro processo (pickle) e da' la stessa serie; famiglia dichiarata",
          g(d).equals(f(d)) and g.famiglia == "volume-pressione" and f.lato == 1 and corti["G0099_SHORT_P25_SU"].lato == -1)
    T.svuota_cache()
    check("C9. stesso risultato con la cache svuotata e su una copia del df",
          f(d.copy()).equals(out["G0099_P25_SU"]))


# ------------------------------------------------------------ sezione D --
def sezione_d():
    print("\nD · Il catalogo")
    a = C.genera_catalogo(40, degeneri=False)
    b = C.genera_catalogo(40, degeneri=False)
    piccolo = C.genera_catalogo(15, degeneri=False)
    with tempfile.TemporaryDirectory() as cartella:
        pa, pb = C.salva_catalogo(a, Path(cartella) / "a.json"), C.salva_catalogo(b, Path(cartella) / "b.json")
        check("D1. due lanci danno lo stesso file, byte per byte", pa.read_bytes() == pb.read_bytes())
        riletto = C.carica_catalogo(pa)
    check("D2. il tetto piu' piccolo (15) e' l'inizio di quello piu' grande (40): gli stessi nomi G0001...",
          [r["ricetta"] for r in piccolo["ricette"]] == [r["ricetta"] for r in a["ricette"][:15]])
    uguali = {u["ricetta"]: u["uguale_a"] for u in a["tolte_uguali"]}
    nomi = {r["ricetta"]: r["id"] for r in a["ricette"]}
    check("D3. somma(sv, N) tolta come uguale a media(sv, N) (stessi trigger: cambia solo la scala)",
          all(uguali.get(f"somma(sv, {n})") == nomi.get(f"media(sv, {n})") is not None for n in R.FINESTRE))
    grande = C.genera_catalogo(100, degeneri=False)
    ug = {u["ricetta"]: u["uguale_a"] for u in grande["tolte_uguali"]}
    nomi_g = {r["id"]: r["ricetta"] for r in grande["ricette"]}
    check("D4. «ar × v» tolta come uguale a «r × sv» (|r| × v in tutti e due)", nomi_g.get(ug.get("ar × v")) == "r × sv")
    sint = C.dataset_sintetico()
    firme = [C._firma(r["albero"], sint, {})[0] for r in grande["ricette"]]
    check("D5. fra le 100 ricette tenute nessuna coppia ha gli stessi trigger sul sintetico",
          len(set(firme)) == len(firme))
    check("D6. ogni ricetta tenuta ha prezzo e volume e al massimo 3 operazioni",
          all(R.rispetta_vincolo(r["albero"]) and r["operazioni"] <= 3 for r in grande["ricette"]))
    k = grande["conteggi"]
    check("D7. conteggi coerenti: generate = tolte (scrittura + uguali + senza trigger) + tenute; trigger = somma",
          k["generate"] == k["tolte_scrittura"] + k["tolte_uguali"] + k["tolte_senza_trigger"] + k["tenute"]
          and k["tenute"] == 100 and k["trigger"] == sum(len(r["trigger"]) for r in grande["ricette"]), str(k))
    d = C.dataset_sintetico(barre=2000, seme=21)
    l1, s1 = C.trigger_del_catalogo(a)
    l2, s2 = C.trigger_del_catalogo(riletto)
    check("D8. il catalogo salvato e riletto da' gli stessi trigger, nello stesso ordine",
          list(l1) == list(l2) and list(s1) == list(s2)
          and C.calcola_trigger(d, {**l1, **s1}).equals(C.calcola_trigger(d, {**l2, **s2})))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        codice = comando([])
    check("D9. «python -m engine.generatore» senza --n si ferma e chiede il tetto",
          codice == 2 and "Manca il tetto N" in out.getvalue())
    with tempfile.TemporaryDirectory() as cartella:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            codice = comando(["--n", "12", "--file", str(Path(cartella) / "g.json")])
        testo_cmd = out.getvalue()
        scritto = json.loads((Path(cartella) / "g.json").read_text(encoding="utf-8"))
    check("D10. con --n 12 scrive il file e stampa ricette generate, tolte come uguali e trigger risultanti",
          codice == 0 and len(scritto["ricette"]) == 12 and "ricette generate" in testo_cmd
          and "uguali sul dataset sintetico" in testo_cmd and "trigger risultanti" in testo_cmd)


# ------------------------------------------------------------ sezione E --
RICETTE_E = [
    ("t", "media", 14, ing("sv")),
    ("corr", 50, ing("r"), ing("v")),
    ("t", "zscore", 50, ("b", "mul", ing("r"), ing("v"))),
    ("b", "div", ("t", "delta", 5, ing("tp")), ("t", "max", 14, ing("v"))),
    ("b", "sub", ("t", "rango", 14, ing("tp")), ("t", "min", 5, ing("v"))),
    ("t", "somma", 200, ("b", "mul", ("f", "abs", ing("corpo")), ing("v"))),
    ("corr", 14, ("f", "segno", ing("r")), ("t", "dev", 5, ing("sv"))),
    ("t", "delta", 14, ("b", "mul", ing("pos"), ("t", "rango", 50, ing("v")))),
    ("b", "div", ("b", "mul", ing("rng"), ing("v")), ("t", "media", 14, ing("ar"))),
]


def trappola(df):
    """Guarda la barra dopo: il controllo deve vederla."""
    x = R.calcola(("t", "media", 14, ing("sv")), df).shift(-1)
    return T.attraversa(x, 0.0, "SU")


def sezione_e():
    print("\nE · verifica_lookahead (troncamento) su ricette da 1, 2 e 3 operazioni")
    from engine.collaudo_catalogo import verifica_lookahead
    cat = {"ricette": [C.voce_ricetta(f"G{i + 1:04d}", e) for i, e in enumerate(RICETTE_E)]}
    tutte_op = {e2[1] if e2[0] in ("t", "b", "f") else e2[0] for e in RICETTE_E for e2 in _nodi(e)} - {"r", "v"}
    check("E0. le ricette di prova usano tutte le operazioni e tutti gli ingredienti",
          set(R.OP_TEMPO + R.OP_DUE + R.OP_FORMA + ("corr",)) <= tutte_op
          and set(R.INGREDIENTI + (R.TP,)) <= set().union(*(R.ingredienti(e) for e in RICETTE_E)), str(tutte_op))
    d = C.dataset_sintetico(barre=4500, seme=7)
    prima = set(reg.list_entries())
    reg_vecchio = {k: dict(getattr(reg, k)) for k in ("_ENTRY_REGISTRY", "_ENTRY_DIRECTION")}
    reg.clear_registry()
    try:
        C.registra_trigger_generati(cat)
        reg.register_entry("TRAPPOLA_BARRA_DOPO", direction=1)(trappola)
        look = muto(verifica_lookahead, d, prepara=lambda x: x.copy(), tagli_per_condizione=2, verbose=False)
    finally:
        reg.clear_registry()
        for k, v in reg_vecchio.items():
            getattr(reg, k).update(v)
    trap = look[look["nome"] == "TRAPPOLA_BARRA_DOPO"]
    check("E1. la trappola che guarda la barra dopo e' LOOKAHEAD: il controllo la vede",
          len(trap) == 1 and trap["esito"].iloc[0] == "LOOKAHEAD")
    gen = look[look["nome"].str.startswith("G")]
    n_attesi = sum(len(r["trigger"]) for r in cat["ricette"])
    esercitati = gen[gen["esito"] == "OK"]
    check("E2. nessun trigger generato guarda avanti (OK o mai scattato, mai LOOKAHEAD o ERRORE)",
          len(gen) == n_attesi and gen["esito"].isin(["OK", "NON_ESERCITATA"]).all(),
          str(gen.loc[~gen["esito"].isin(["OK", "NON_ESERCITATA"]), ["nome", "esito", "primo_caso"]].head(3)
              .to_dict("records")))
    check("E3. quasi tutti i trigger esercitati (almeno il 95%), ognuno su almeno 96 tagli (uno per ora del giorno)",
          len(esercitati) >= 0.95 * n_attesi and (esercitati["tagli"] >= 96).all(), f"{len(esercitati)}/{n_attesi}")
    check("E4. il registro del motore torna com'era", set(reg.list_entries()) == prima)


def _nodi(e):
    yield e
    for x in e[2:]:
        if isinstance(x, tuple):
            yield from _nodi(x)


# ------------------------------------------------------------ sezione F --
def sezione_f():
    print("\nF · verifica_degenerazione: i degeneri segnalati, non tolti")
    cat = C.genera_catalogo(30)
    esiti = [t.get("esito_sintetico") for r in cat["ricette"] for t in r["trigger"]]
    check("F1. ogni trigger del catalogo porta l'esito sul sintetico; i degeneri restano nel catalogo",
          all(esiti) and "OK" in esiti and any(x != "OK" for x in esiti)
          and cat["conteggi"]["trigger_degeneri_sintetico"] == sum(x != "OK" for x in esiti))
    rango5 = next(r for r in cat["ricette"] if r["ricetta"] == "rango(sv, 5)")
    e10 = {t["nome"]: t["esito_sintetico"] for t in rango5["trigger"]}
    check("F2. rango(sv, 5) che scende sotto il suo 10° percentile non puo' scattare (il rango minimo e' 0,2): "
          "SEMPRE_FALSA", e10["G" + rango5["id"][1:] + "_P10_GIU"] == "SEMPRE_FALSA", str(e10))
    d = C.dataset_sintetico(barre=3000, seme=13)
    d["Volume"] = 1000.0                                  # volume costante: v = 1, corr(r, v) non esiste
    piccolo = {"ricette": [C.voce_ricetta("G0001", ("corr", 14, ing("r"), ing("v")), True),
                           C.voce_ricetta("G0002", ("t", "zscore", 14, ing("sv")), True)]}
    prima = set(reg.list_entries())
    tab = C.segnala_degeneri(d, piccolo)
    g1 = tab[tab["nome"].str.startswith("G0001")]
    g2 = tab[tab["nome"].str.startswith("G0002")]
    check("F3. con il volume costante corr(r, v, 14) e' SEMPRE_FALSA su tutti i 28 trigger; zscore(sv, 14) no",
          len(g1) == 28 and (g1["esito"] == "SEMPRE_FALSA").all() and (g2["esito"] != "SEMPRE_FALSA").any())
    check("F4. segnala_degeneri guarda solo i trigger generati e lascia il registro com'era",
          len(tab) == 56 and set(reg.list_entries()) == prima)


def esegui() -> int:
    print("=" * 70)
    print("test_generatore · generatore di indicatori e trigger prezzo + volume (docs/83)")
    print("=" * 70)
    try:
        sezione_a()
        sezione_b()
        sezione_c()
        sezione_d()
        sezione_e()
        sezione_f()
    finally:
        T.svuota_cache()
    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
