"""
Le ricette del generatore (docs/83 §3, §4): ingredienti, operazioni, elenco in ordine fisso.

Una ricetta e' un albero di tuple:

    ("ing", nome)                 un ingrediente (r, ar, rng, pos, corpo, v, sv, tp)
    ("t", op, N, figlio)          un'operazione nel tempo su N barre: media, somma, max, min, dev, zscore, rango, delta
    ("corr", N, a, b)             la correlazione di a e b su N barre
    ("b", op, a, b)               fra due serie: per (×), diviso (÷), meno (−)
    ("f", op, figlio)             di forma: segno, abs

Ogni nodo che non e' un ingrediente conta un'operazione; al massimo 3 (MAX_OPERAZIONI).

Regole (decise da Mattia il 15/11, docs/83 §2 e la chat dell'incarico):
- `sv` (segno del rendimento × volume relativo) conta come ingrediente di prezzo E di volume;
- `tp` entra solo come argomento diretto di delta, zscore e rango; il delta di tp e' in rapporto, log(tp / tp di N
  barre fa);
- ogni ricetta ha almeno un ingrediente di prezzo e uno di volume.

L'elenco non guarda nessun dato: `elenca()` da' sempre le stesse ricette nello stesso ordine.
"""
from __future__ import annotations

from typing import Iterator

import numpy as np
import pandas as pd

MAX_OPERAZIONI = 3
FINESTRE = (5, 14, 50, 200)
MEDIANA_VOLUME = 50                     # v = Volume / mediana delle ultime 50 barre (barra compresa)
EPS = 1e-12                             # protezione dallo zero nelle divisioni

# ingredienti nell'ordine della tabella di docs/83 §3 (tp a parte: solo dentro delta, zscore, rango)
INGREDIENTI = ("r", "ar", "rng", "pos", "corpo", "v", "sv")
TP = "tp"
PREZZO = frozenset({"r", "ar", "rng", "pos", "corpo", "sv", "tp"})
VOLUME = frozenset({"v", "sv"})
NON_NEGATIVI = frozenset({"ar", "rng", "pos", "v"})
CON_TP = ("zscore", "rango", "delta")

OP_TEMPO = ("media", "somma", "max", "min", "dev", "zscore", "rango", "delta")
OP_DUE = ("mul", "div", "sub")
OP_FORMA = ("segno", "abs")
SIMBOLO = {"mul": "×", "div": "÷", "sub": "−"}


# ------------------------------------------------------------------ lettura ----
def n_operazioni(e: tuple) -> int:
    k = e[0]
    if k == "ing":
        return 0
    if k == "t":
        return 1 + n_operazioni(e[3])
    if k in ("corr", "b"):
        return 1 + n_operazioni(e[2]) + n_operazioni(e[3])
    return 1 + n_operazioni(e[2])


def ingredienti(e: tuple) -> frozenset:
    k = e[0]
    if k == "ing":
        return frozenset({e[1]})
    if k == "t":
        return ingredienti(e[3])
    if k in ("corr", "b"):
        return ingredienti(e[2]) | ingredienti(e[3])
    return ingredienti(e[2])


def finestre(e: tuple) -> list[int]:
    k = e[0]
    if k == "ing":
        return []
    if k == "t":
        return [e[2]] + finestre(e[3])
    if k == "corr":
        return [e[1]] + finestre(e[2]) + finestre(e[3])
    if k == "b":
        return finestre(e[2]) + finestre(e[3])
    return finestre(e[2])


def testo(e: tuple) -> str:
    """La ricetta leggibile, es. «zscore(r × v, 50)», «corr(r, v, 14)», «media(sv, 14)»."""
    k = e[0]
    if k == "ing":
        return e[1]
    if k == "t":
        return f"{e[1]}({testo(e[3])}, {e[2]})"
    if k == "corr":
        return f"corr({testo(e[2])}, {testo(e[3])}, {e[1]})"
    if k == "b":
        def _p(x):
            return f"({testo(x)})" if x[0] == "b" else testo(x)
        return f"{_p(e[2])} {SIMBOLO[e[1]]} {_p(e[3])}"
    return f"{e[1]}({testo(e[2])})"


def rispetta_vincolo(e: tuple) -> bool:
    """Almeno un ingrediente di prezzo e uno di volume (sv vale per tutti e due)."""
    ing = ingredienti(e)
    return bool(ing & PREZZO) and bool(ing & VOLUME)


def non_negativa(e: tuple) -> bool:
    """Vero se la ricetta, per come e' scritta, non e' mai negativa."""
    k = e[0]
    if k == "ing":
        return e[1] in NON_NEGATIVI
    if k == "t":
        if e[1] in ("dev", "rango"):
            return True
        return e[1] in ("media", "somma", "max", "min") and non_negativa(e[3])
    if k == "b":
        return e[1] in ("mul", "div") and non_negativa(e[2]) and non_negativa(e[3])
    if k == "f":
        return e[1] == "abs"
    return False


def da_json(x) -> tuple:
    """Da liste annidate (il file del catalogo) a tuple."""
    return tuple(da_json(y) if isinstance(y, list) else y for y in x)


# ------------------------------------------------------------------- elenco ----
def _regola_scrittura(e: tuple, rango: dict) -> str | None:
    """None se la ricetta e' nuova per scrittura; altrimenti il motivo per cui e' uguale a un'altra."""
    k = e[0]
    if k in ("corr", "b"):
        a, b = e[2], e[3]
        if a == b:
            return "stessa serie due volte"
        op = "corr" if k == "corr" else e[1]
        if op in ("corr", "mul", "sub") and rango[a] > rango[b]:
            return "operandi scambiati (A×B = B×A, A−B = −(B−A))"
    if k == "f":
        x = e[2]
        if e[1] == "abs" and non_negativa(x):
            return "valore assoluto di una serie mai negativa"
        if x[0] == "f":
            return "forma di una forma (segno o valore assoluto di un segno)"
        if e[1] == "abs" and x == ("ing", "r"):
            return "abs(r) = ar"
        if e[1] == "abs" and x == ("ing", "sv"):
            return "abs(sv) = v"
        if e[1] == "segno" and x == ("ing", "sv"):
            return "segno(sv) = segno(r)"
    return None


def _livello(k: int, livelli: list[list[tuple]], rango: dict) -> Iterator[tuple[tuple, str | None]]:
    """Le ricette con k operazioni, in ordine fisso, con il motivo se sono uguali per scrittura a un'altra."""
    figli = livelli[k - 1]
    # 1) nel tempo: operazione, figlio, finestra
    for op in OP_TEMPO:
        candidati = list(figli) + ([("ing", TP)] if k == 1 and op in CON_TP else [])
        for x in candidati:
            for n in FINESTRE:
                yield ("t", op, n, x), None
    # coppie di figli con i + j = k - 1 operazioni
    def coppie():
        for i in range(k):
            for a in livelli[i]:
                for b in livelli[k - 1 - i]:
                    yield a, b
    # 2) correlazione
    for a, b in coppie():
        for n in FINESTRE:
            e = ("corr", n, a, b)
            yield e, _regola_scrittura(e, rango)
    # 3) fra due serie
    for op in OP_DUE:
        for a, b in coppie():
            e = ("b", op, a, b)
            yield e, _regola_scrittura(e, rango)
    # 4) di forma
    for op in OP_FORMA:
        for x in figli:
            e = ("f", op, x)
            yield e, _regola_scrittura(e, rango)


def elenca(max_operazioni: int = MAX_OPERAZIONI) -> Iterator[tuple[tuple, str | None]]:
    """
    Tutte le ricette da 1 a `max_operazioni` operazioni, in ordine fisso (docs/83 §4.1): prima quelle da 1, poi da 2,
    poi da 3; dentro lo stesso numero: nel tempo (media, somma, max, min, dev, zscore, rango, delta), correlazione,
    fra due serie (×, ÷, −), di forma (segno, abs); poi gli ingredienti nell'ordine della tabella, le finestre
    dalla piu' corta.

    Restituisce coppie (ricetta, motivo): motivo None se la ricetta e' nuova per scrittura, altrimenti perche' e'
    uguale a un'altra. Le ricette che non rispettano il vincolo prezzo + volume escono anche loro (servono come pezzi
    delle ricette piu' lunghe): il filtro lo fa chi chiama, con `rispetta_vincolo`. Le ricette da 3 operazioni si
    generano una alla volta, senza tenerle tutte in memoria.
    """
    livelli: list[list[tuple]] = [[("ing", n) for n in INGREDIENTI]]
    rango = {e: i for i, e in enumerate(livelli[0])}
    for k in range(1, max_operazioni + 1):
        nuovi = []
        for e, motivo in _livello(k, livelli, rango):
            yield e, motivo
            if motivo is None and k < max_operazioni:
                nuovi.append(e)
                rango[e] = len(rango)
        livelli.append(nuovi)


# ---------------------------------------------------------------- calcolo ----
def _protetto(a: pd.Series, b: pd.Series) -> pd.Series:
    return a / b.where(b.abs() > EPS)


def _ingrediente(nome: str, df: pd.DataFrame, memo: dict) -> pd.Series:
    if nome in memo:
        return memo[nome]
    o, h, l, c = (df[x].astype(float) for x in ("Open", "High", "Low", "Close"))
    if nome == "r":
        s = np.log(c / c.shift(1))
    elif nome == "ar":
        s = _ingrediente("r", df, memo).abs()
    elif nome == "rng":
        s = (h - l) / c
    elif nome == "pos":
        s = ((c - l) / (h - l).where(h > l)).fillna(0.5).where(c.notna())
    elif nome == "corpo":
        s = ((c - o) / (h - l).where(h > l)).fillna(0.0).where(c.notna())
    elif nome == "v":
        vol = df["Volume"].astype(float)
        s = _protetto(vol, vol.rolling(MEDIANA_VOLUME, min_periods=MEDIANA_VOLUME).median())
    elif nome == "sv":
        s = np.sign(_ingrediente("r", df, memo)) * _ingrediente("v", df, memo)
    elif nome == "tp":
        s = (h + l + c) / 3.0
    else:
        raise ValueError(f"ingrediente sconosciuto: {nome!r}")
    memo[nome] = s
    return s


def _tempo(op: str, n: int, x: pd.Series, e_figlio: tuple) -> pd.Series:
    w = x.rolling(n, min_periods=n)
    if op == "media":
        return w.mean()
    if op == "somma":
        return w.sum()
    if op == "max":
        return w.max()
    if op == "min":
        return w.min()
    if op == "dev":
        return w.std(ddof=0)
    if op == "zscore":
        return _protetto(x - w.mean(), w.std(ddof=0))
    if op == "rango":
        return w.rank(pct=True)
    if op == "delta":
        if e_figlio == ("ing", TP):
            return np.log(x / x.shift(n))
        return x - x.shift(n)
    raise ValueError(f"operazione sconosciuta: {op!r}")


def calcola(e: tuple, df: pd.DataFrame, memo: dict | None = None) -> pd.Series:
    """
    Il valore della ricetta su ogni barra di `df` (OHLCV). Usa solo la barra stessa e quelle prima: nessun lookahead.
    I valori infiniti diventano NaN.
    """
    memo = {} if memo is None else memo
    k = e[0]
    if k == "ing":
        out = _ingrediente(e[1], df, memo)
    elif k == "t":
        out = _tempo(e[1], e[2], calcola(e[3], df, memo), e[3])
    elif k == "corr":
        a, b = calcola(e[2], df, memo), calcola(e[3], df, memo)
        out = a.rolling(e[1], min_periods=e[1]).corr(b).clip(-1.0, 1.0)
    elif k == "b":
        a, b = calcola(e[2], df, memo), calcola(e[3], df, memo)
        out = a * b if e[1] == "mul" else (_protetto(a, b) if e[1] == "div" else a - b)
    elif k == "f":
        x = calcola(e[2], df, memo)
        out = np.sign(x) if e[1] == "segno" else x.abs()
    else:
        raise ValueError(f"nodo sconosciuto: {e!r}")
    out = out.replace([np.inf, -np.inf], np.nan)
    return out.astype(float)


# --------------------------------------------------------------- famiglia ----
_GRUPPI_PREZZO = (("pressione", frozenset({"r", "sv", "corpo", "pos"})),
                  ("conferma", frozenset({"ar", "rng"})),
                  ("momento", frozenset({"tp"})))


def famiglia(e: tuple) -> str:
    """
    La famiglia dichiarata (docs/83 §6), dagli ingredienti di prezzo: «volume-pressione» se c'e' la direzione della
    barra (r, sv, corpo, pos: tipo OBV, MFI, Chaikin), «volume-conferma» se c'e' solo l'ampiezza (ar, rng: sforzo e
    risultato), «volume-momento» se c'e' il prezzo tipico (tp: dove sta il prezzo su N barre). Con piu' gruppi i nomi
    si uniscono con «+» in quest'ordine, es. «volume-pressione+conferma».
    """
    ing = ingredienti(e)
    parti = [nome for nome, gruppo in _GRUPPI_PREZZO if ing & gruppo]
    return "volume-" + "+".join(parti)
