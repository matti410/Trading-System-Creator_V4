"""
L'ottimizzatore della fabbrica (docs/82 §4, lavoro L1).

Riceve una funzione e uno spazio, restituisce valori. Non sa nulla di trading e
importa solo la libreria standard e numpy (test_fabbrica_ottimizzatore lo controlla).

Lo spazio
---------
    spazio = Spazio([Intero("periodo", 2, 48, 2), Reale("soglia", 0.5, 3.0, 0.25),
                     Categoria("target", (None, 90))])

Dentro l'ottimizzatore un punto è una lista di INDICI, uno per parametro: così i
reali non accumulano errori di arrotondamento e lo stato si salva in JSON. Fuori
un punto è un dizionario {nome: valore}.

Griglia
-------
    griglia_larga(spazio, punti_max, seme) -> list[punto]

Griglia completa se ci sta; altrimenti esattamente `punti_max` punti diversi,
sparsi in modo uniforme (ipercubo latino: ogni parametro è coperto a fasce uguali).

Algoritmo genetico
------------------
    genetico(funzione, spazio, budget, seme, opzioni=None, stato=None) -> Esito

Massimizza `funzione(punto)`. A ogni generazione: si tengono le `elite` migliori
della precedente, poi si creano i figli (torneo, incrocio uniforme, mutazione) più
qualche punto a caso.

Regole:
- NaN vuol dire «scartata», ma è una valutazione contata. Un infinito vale come NaN:
  altrimenti un errore di calcolo diventerebbe il migliore.
- Un punto già valutato non si rivaluta e non si conta due volte: un figlio già visto
  si muta ancora; se non basta, si prende un punto mai visto a caso.
- Il budget non si supera mai. Se lo spazio finisce prima, ci si ferma (`esaurito`).
- Il caso viene solo da un Generator creato dal seme: niente stato globale.

Fermarsi e riprendere
---------------------
Per fermarsi si chiama con un budget più piccolo. Per riprendere si richiama con gli
stessi funzione, spazio, seme e opzioni, un budget più grande e `stato=esito.stato`:
il risultato è identico, bit per bit, a una corsa unica. `stato` è JSON puro.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from dataclasses import asdict, dataclass
from numbers import Integral, Real
from typing import Any, Callable

import numpy as np

_VERSIONE_STATO = 1
_ELENCABILE = 100_000       # fino a qui, i punti rimasti si possono elencare tutti


@dataclass(frozen=True)
class Intero:
    """Interi da `minimo` a `massimo`, a passo `passo`."""
    nome: str
    minimo: int
    massimo: int
    passo: int = 1

    def __post_init__(self):
        if not all(isinstance(v, Integral) and not isinstance(v, bool) for v in (self.minimo, self.massimo, self.passo)):
            raise ValueError(f"{self.nome}: Intero vuole minimo, massimo e passo interi")
        if self.passo <= 0 or self.minimo > self.massimo:
            raise ValueError(f"{self.nome}: serve passo > 0 e minimo <= massimo")

    @property
    def n(self) -> int:
        return (int(self.massimo) - int(self.minimo)) // int(self.passo) + 1

    @property
    def ordinato(self) -> bool:
        return True

    def valore(self, i: int) -> int:
        return int(self.minimo) + i * int(self.passo)

    def descrizione(self) -> list:
        return ["intero", self.nome, int(self.minimo), int(self.massimo), int(self.passo)]


@dataclass(frozen=True)
class Reale:
    """Reali da `minimo` a `massimo`, a passo `passo`. L'ultimo valore non supera mai `massimo`."""
    nome: str
    minimo: float
    massimo: float
    passo: float

    def __post_init__(self):
        if not all(isinstance(v, Real) and math.isfinite(v) for v in (self.minimo, self.massimo, self.passo)):
            raise ValueError(f"{self.nome}: Reale vuole minimo, massimo e passo finiti")
        if self.passo <= 0 or self.minimo > self.massimo:
            raise ValueError(f"{self.nome}: serve passo > 0 e minimo <= massimo")

    @property
    def n(self) -> int:
        return math.floor((float(self.massimo) - float(self.minimo)) / float(self.passo) + 1e-9) + 1

    @property
    def ordinato(self) -> bool:
        return True

    def valore(self, i: int) -> float:
        # arrotondato: 0,8 + 4 × 0,1 è 1,2 e non 1,2000000000000002, così lo stesso valore ha sempre la stessa impronta
        return min(float(self.massimo), round(float(self.minimo) + i * float(self.passo), 10))

    def descrizione(self) -> list:
        return ["reale", self.nome, float(self.minimo), float(self.massimo), float(self.passo)]


@dataclass(frozen=True)
class Categoria:
    """Una scelta fra valori senza ordine (anche None, per esempio «target spento»)."""
    nome: str
    valori: tuple

    def __post_init__(self):
        if not self.valori or len({repr(v) for v in self.valori}) != len(self.valori):
            raise ValueError(f"{self.nome}: Categoria vuole almeno un valore e nessun doppione")

    @property
    def n(self) -> int:
        return len(self.valori)

    @property
    def ordinato(self) -> bool:
        return False

    def valore(self, i: int) -> Any:
        return self.valori[i]

    def descrizione(self) -> list:
        return ["categoria", self.nome, [repr(v) for v in self.valori]]


class Spazio:
    """L'elenco dei parametri. `totale` è il numero di punti dello spazio."""

    def __init__(self, parametri):
        self.parametri = tuple(parametri)
        if not self.parametri:
            raise ValueError("uno spazio vuole almeno un parametro")
        nomi = [p.nome for p in self.parametri]
        if len(set(nomi)) != len(nomi):
            raise ValueError(f"nomi di parametro doppi: {nomi}")
        self.dimensioni = tuple(p.n for p in self.parametri)
        self.totale = math.prod(self.dimensioni)

    def punto(self, indici) -> dict:
        return {p.nome: p.valore(i) for p, i in zip(self.parametri, indici)}

    def descrizione(self) -> list:
        return [p.descrizione() for p in self.parametri]


@dataclass(frozen=True)
class Opzioni:
    """
    popolazione  punti per generazione.
    elite        i migliori che passano alla generazione dopo senza cambiare.
    torneo       quanti punti si confrontano per scegliere un genitore.
    incrocio     probabilità di un figlio da due genitori (l'«eredità»); se no, da uno solo.
    mutazione    probabilità che un parametro del figlio cambi.
    azzera       quando un parametro cambia, probabilità di un valore del tutto nuovo invece di un salto.
    immigrati    quota di figli sostituiti da punti a caso.
    salto        il salto più grande, come quota dell'intervallo del parametro.
    decadi       di quante potenze di 10 il salto può essere più piccolo: copre passi larghi e stretti;
                 la scala è la stessa per tutti i parametri di un figlio.
    tentativi    quante volte si rimuta un figlio già visto, prima di prendere un punto a caso.
    """
    popolazione: int = 40
    elite: int = 2
    torneo: int = 3
    incrocio: float = 0.8
    mutazione: float = 0.5
    azzera: float = 0.05
    immigrati: float = 0.02
    salto: float = 0.2
    decadi: float = 3.0
    tentativi: int = 5

    def __post_init__(self):
        if self.popolazione < 2 or not 0 <= self.elite < self.popolazione or self.torneo < 1 or self.tentativi < 1:
            raise ValueError(f"opzioni non valide: {self}")
        if not all(0.0 <= v <= 1.0 for v in (self.incrocio, self.mutazione, self.azzera, self.immigrati)):
            raise ValueError(f"le probabilità stanno fra 0 e 1: {self}")
        if not self.salto > 0 or self.decadi < 0:
            raise ValueError(f"serve salto > 0 e decadi >= 0: {self}")


PREDEFINITE = Opzioni()
# Il passo 1 della fabbrica: molta mutazione, poca eredità, punti lontani fino in fondo.
AMPIEZZA = Opzioni(popolazione=16, elite=1, torneo=3, incrocio=0.2, mutazione=0.6, azzera=0.3, immigrati=0.15,
                   salto=0.3, decadi=1.5)


@dataclass
class Esito:
    """
    punti            i punti provati, nell'ordine (dizionari).
    valori           il valore di ogni punto; NaN = scartato.
    migliore         il punto con il valore più alto; None se sono tutti scartati.
    valore_migliore  il suo valore; NaN se non c'è.
    valutazioni      le valutazioni fatte, comprese quelle delle corse precedenti.
    stato            per riprendere: JSON puro.
    esaurito         True se sono stati provati tutti i punti dello spazio.
    """
    punti: list
    valori: list
    migliore: dict | None
    valore_migliore: float
    valutazioni: int
    stato: dict
    esaurito: bool


def _generatore(seme: int) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seme))


def _controlla_spazio(spazio) -> None:
    if not isinstance(spazio, Spazio):
        raise ValueError("serve uno Spazio")


def _griglia_indici(spazio: Spazio, n: int, rng: np.random.Generator) -> list[tuple]:
    """Griglia completa se ci sta; altrimenti n punti diversi, ipercubo latino più punti a caso se servono."""
    if spazio.totale <= n:
        return list(itertools.product(*(range(k) for k in spazio.dimensioni)))
    colonne = []
    for k in spazio.dimensioni:
        fasce = (rng.permutation(n) + rng.random(n)) / n
        colonne.append(np.minimum((fasce * k).astype(np.int64), k - 1).tolist())
    punti, visti = [], set()
    for p in zip(*colonne):
        if p not in visti:
            visti.add(p)
            punti.append(p)
    while len(punti) < n:
        p = _a_caso(spazio.dimensioni, rng)
        if p not in visti:
            visti.add(p)
            punti.append(p)
    return punti


def _a_caso(dimensioni, rng: np.random.Generator) -> tuple:
    return tuple(int(rng.random() * k) for k in dimensioni)


def griglia_larga(spazio: Spazio, punti_max: int, seme: int) -> list[dict]:
    """La griglia completa se ci sta in `punti_max`, altrimenti `punti_max` punti diversi sparsi in modo uniforme."""
    _controlla_spazio(spazio)
    if punti_max < 1:
        raise ValueError("punti_max vuole almeno 1")
    return [spazio.punto(p) for p in _griglia_indici(spazio, int(punti_max), _generatore(seme))]


def _impronta(spazio: Spazio, seme: int, opzioni: Opzioni) -> str:
    testo = json.dumps({"spazio": spazio.descrizione(), "seme": int(seme), "opzioni": asdict(opzioni)}, sort_keys=True)
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()


def _chiave(valori: list, i: int) -> tuple:
    """Per ordinare dal migliore: valore più alto, a parità il più vecchio; NaN in fondo."""
    v = valori[i]
    return (-math.inf if v != v else v, -i)


def _nuova_popolazione(popolazione: list, inizio: int, valori: list, elite: int) -> list:
    """Le `elite` migliori della generazione prima più tutta l'ultima generazione, dalla migliore in giù."""
    vecchi = sorted(popolazione, key=lambda i: _chiave(valori, i), reverse=True)[:elite]
    return sorted(vecchi + list(range(inizio, len(valori))), key=lambda i: _chiave(valori, i), reverse=True)


def _punto_nuovo(spazio: Spazio, visti: set, rng: np.random.Generator) -> tuple | None:
    """Un punto mai visto, a caso. None se lo spazio è finito."""
    if len(visti) >= spazio.totale:
        return None
    for _ in range(20):
        p = _a_caso(spazio.dimensioni, rng)
        if p not in visti:
            return p
    if spazio.totale <= _ELENCABILE:
        rimasti = [p for p in itertools.product(*(range(k) for k in spazio.dimensioni)) if p not in visti]
        return rimasti[int(rng.random() * len(rimasti))]
    while True:
        p = _a_caso(spazio.dimensioni, rng)
        if p not in visti:
            return p


def _scala(opzioni: Opzioni, rng: np.random.Generator) -> float:
    """La scala dei salti di un figlio, fra larga e stretta. Unica per figlio: serve a muovere più parametri insieme."""
    return opzioni.salto * 10.0 ** (-opzioni.decadi * rng.random())


def _muta_gene(i: int, k: int, ordinato: bool, scala: float, opzioni: Opzioni, rng: np.random.Generator) -> int:
    """Un valore del tutto nuovo, oppure un salto attorno a quello attuale, di almeno una posizione."""
    if not ordinato or rng.random() < opzioni.azzera:
        return int(rng.random() * k)
    d = int(round(rng.standard_normal() * scala * k))
    if d == 0:
        d = 1 if rng.random() < 0.5 else -1
    return max(0, min(k - 1, i + d))


def _figli(spazio: Spazio, popolazione: list, punti: list, opzioni: Opzioni, rng: np.random.Generator,
           visti: set) -> list[tuple]:
    """I punti della prossima generazione: tutti mai visti. La popolazione è ordinata dalla migliore."""
    dimensioni, ordinati = spazio.dimensioni, [p.ordinato for p in spazio.parametri]
    cambiabili = [j for j, k in enumerate(dimensioni) if k > 1]
    quanti = opzioni.popolazione - opzioni.elite
    immigrati = round(quanti * opzioni.immigrati)
    n_pop = len(popolazione)

    def genitore():
        # la popolazione è ordinata: vince la posizione più bassa fra quelle estratte
        return punti[popolazione[min(int(rng.random() * n_pop) for _ in range(opzioni.torneo))]]

    nuovi = []
    for numero in range(quanti):
        if len(visti) >= spazio.totale:
            break
        figlio = None
        if numero >= immigrati:
            a = genitore()
            if rng.random() < opzioni.incrocio:
                b = genitore()
                figlio = [x if rng.random() < 0.5 else y for x, y in zip(a, b)]
            else:
                figlio = list(a)
            scala = _scala(opzioni, rng)
            for j in cambiabili:
                if rng.random() < opzioni.mutazione:
                    figlio[j] = _muta_gene(figlio[j], dimensioni[j], ordinati[j], scala, opzioni, rng)
            for _ in range(opzioni.tentativi):
                if tuple(figlio) not in visti:
                    break
                j = cambiabili[int(rng.random() * len(cambiabili))]
                figlio[j] = _muta_gene(figlio[j], dimensioni[j], ordinati[j], scala, opzioni, rng)
            figlio = tuple(figlio)
        if figlio is None or figlio in visti:
            figlio = _punto_nuovo(spazio, visti, rng)
        visti.add(figlio)
        nuovi.append(figlio)
    return nuovi


def _stato(impronta, rng, punti, valori, popolazione, inizio, coda) -> dict:
    return {"versione": _VERSIONE_STATO, "impronta": impronta, "rng": rng.bit_generator.state,
            "punti": [list(p) for p in punti], "valori": [None if v != v else v for v in valori],
            "popolazione": list(popolazione), "inizio": inizio, "coda": [list(p) for p in coda]}


def genetico(funzione: Callable[[dict], float], spazio: Spazio, budget: int, seme: int,
             opzioni: Opzioni | None = None, stato: dict | None = None) -> Esito:
    """Massimizza `funzione` con al massimo `budget` valutazioni in tutto (vedi la testa del file)."""
    _controlla_spazio(spazio)
    if budget < 0:
        raise ValueError("il budget non può essere negativo")
    opzioni = PREDEFINITE if opzioni is None else opzioni
    impronta = _impronta(spazio, seme, opzioni)

    if stato is None:
        rng = _generatore(seme)
        punti, valori, popolazione, inizio = [], [], [], 0
        coda = _griglia_indici(spazio, opzioni.popolazione, rng)
    else:
        if stato.get("versione") != _VERSIONE_STATO or stato.get("impronta") != impronta:
            raise ValueError("questo stato è di un'altra corsa: spazio, seme o opzioni sono diversi")
        rng = _generatore(seme)
        rng.bit_generator.state = stato["rng"]
        punti = [tuple(p) for p in stato["punti"]]
        valori = [math.nan if v is None else v for v in stato["valori"]]
        popolazione, inizio = list(stato["popolazione"]), stato["inizio"]
        coda = [tuple(p) for p in stato["coda"]]

    visti = set(punti) | set(coda)
    prossimo = 0
    while len(punti) < budget:
        if prossimo == len(coda):
            popolazione = _nuova_popolazione(popolazione, inizio, valori, opzioni.elite)
            inizio = len(punti)
            coda, prossimo = _figli(spazio, popolazione, punti, opzioni, rng, visti), 0
            if not coda:
                break
        p = coda[prossimo]
        prossimo += 1
        v = float(funzione(spazio.punto(p)))
        punti.append(p)
        valori.append(v if math.isfinite(v) else math.nan)

    finiti = [i for i, v in enumerate(valori) if v == v]
    i_migliore = max(finiti, key=lambda i: _chiave(valori, i)) if finiti else None
    return Esito(punti=[spazio.punto(p) for p in punti], valori=valori,
                 migliore=None if i_migliore is None else spazio.punto(punti[i_migliore]),
                 valore_migliore=math.nan if i_migliore is None else valori[i_migliore],
                 valutazioni=len(punti),
                 stato=_stato(impronta, rng, punti, valori, popolazione, inizio, coda[prossimo:]),
                 esaurito=len(punti) == spazio.totale)
