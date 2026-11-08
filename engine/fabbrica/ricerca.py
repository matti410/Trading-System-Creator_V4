"""
La ricerca della fabbrica (docs/82 P4, P5, P6, P7, lavori L3b e L4a): passo 1, zoom, altopiano, selezione, ripresa.

    esito = lancia(config, cartella_dati)     # salva la config, legge i pezzi, prova, scrive; se interrotta riprende
    esito.imbuto                              # teorie → passo 1 → passo 2 → altopiano → selezione → scelte
    esito.sopravvissute                       # una riga per teoria che regge l'altopiano
    esito.selezione.tabella                   # una riga per sopravvissuta sul pezzo di selezione (selezione.py)
    esito.conto                               # le prove di questa ricerca, dell'asset e la soglia, solo da leggere

Passo 1 (P4). Sul solo pezzo di ricerca, una teoria alla volta, al massimo `per_teoria_passo_1` prove sui valori larghi:
griglia completa se i punti ammessi ci stanno, altrimenti il genetico tarato in ampiezza (AMPIEZZA). L'obiettivo è il t
netto di ogni strategia calcolabile; la condizione di qualità 1 decide solo alla fine (07/11): la teoria è tenuta se
almeno una strategia passa e vale il t della migliore fra quelle che passano. Al passo 2 vanno le `teorie_passo_2`
teorie tenute con quel t più alto (a parità, l'id più piccolo).

Passo 2, lo zoom (P5). `giri_zoom` giri da `prove_per_giro` prove. Ogni giro riparte dalle 5 strategie con il t più
alto fra tutte quelle calcolabili della teoria provate fin lì, passo 1 compreso (07/11). Per ogni parametro l'intervallo
va dal minimo al massimo delle 5, allargato del passo del giro prima da ogni lato (al primo giro il buco più largo della
griglia), dentro lo spazio; il passo nuovo è la metà del buco più largo, poi la media geometrica fra quella e il passo
fine, poi il passo fine (passi_zoom). Il reticolo parte dal minimo delle 5. Il target è una scelta, non un numero: nel
giro restano i valori che hanno le 5. Uno spazio che ci sta nel giro si prova tutto; se no, il genetico (PREDEFINITE).

L'altopiano (P5). Le candidate sono le strategie della teoria che passano la condizione 1, dalla migliore, fino a
`candidati_max`. Per ognuna si provano i vicini (vicini) e si giudica (giudica_altopiano): la prima che regge è la
scelta; se nessuna regge, la teoria esce.

Le prove (P7). Ogni strategia valutata è una riga nel file delle prove. Una strategia già vista nella stessa teoria
(stessa impronta, id_strategia) non si rivaluta e non si conta. Una combinazione proposta dallo zoom o dall'altopiano
passa prima da verifica_degenerazione: se è degenere si scarta, si annota e non conta. Né l'una né l'altra consumano
una prova del budget, che non si supera mai.

La selezione (P6, L4a). Finito il passo 2, le sopravvissute vanno sul pezzo di selezione (selezione.seleziona) e
l'esito si scrive in selezione.json; alla ripresa si rilegge. Il conto delle prove dell'asset e la soglia che gli
corrisponde stanno accanto al test individuale, solo da leggere (P7).

Ripresa e processi. Il seme di una teoria nasce da seme della ricerca + id della teoria (e del giro): il risultato non
dipende dall'ordine né dal numero di processi. Ogni teoria finita si scrive su disco, nell'ordine delle teorie; alla
ripresa si saltano quelle già scritte, e il risultato è identico bit per bit. Ogni processo imposta da sé il mercato
crypto (dati.imposta_mercato_crypto). Nessuna lettura o scrittura fuori da dati/fabbrica/<SYMBOL>_<TIMEFRAME>/.
"""
from __future__ import annotations

import itertools
import json
import math
import multiprocessing as mp
import os
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from engine.giudizio import soglia_rumore
from engine.indicatori import aggiungi_indicatori

from . import registro
from . import selezione as sel_mod
from .blocchi import BARRE_MINIME, blocchi_da_config
from .cache import Cache
from .config import cartella_asset, controlla_budget, controlla_config, impronta_config, salva_config
from .dati import Confini, carica_pezzi, imposta_mercato_crypto
from .generatore import (NOME_LATO, ControlloDegenerazione, SpazioTeoria, Teoria, genera_teorie, lati_config,
                         misura_famiglie, resoconto_teorie, seme_teoria, togli_degeneri)
from .ottimizzatore import AMPIEZZA, PREDEFINITE, Categoria, Intero, Reale, Spazio, genetico
from .valutatore import Costi, Strategia, Valutatore, id_strategia, obiettivo, qualita_1

LIMITE_CACHE_MB = 1500          # per processo: indicatori, maschere e soglie già calcolati
MIGLIORI_ZOOM = 5               # le strategie da cui riparte ogni giro (P5)
PEZZO = "ricerca"
FILE_PASSO_1, FILE_PASSO_2, FILE_STATO = "passo_1.jsonl", "passo_2.jsonl", "stato.json"
FILE_SELEZIONE = "selezione.json"


def _arrotonda(x: float) -> int:
    """All'intero più vicino, a metà strada verso l'alto, come cache.barre_da_ore."""
    return math.floor(float(x) + 0.5 + 1e-9)


def _finito(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x)


# ------------------------------------------------------------------ gli assi dello zoom
@dataclass(frozen=True)
class Asse:
    """
    Un parametro della teoria per lo zoom. `griglia` sono i valori larghi rimasti dopo i valori degeneri (P3): ne
    danno minimo e massimo. `fine` è il passo più fine (1, o 0,1 per la soglia di ATR relativo); None = una scelta.
    Dentro lo zoom un valore è un numero di passi fini dal minimo («unità»): niente errori di arrotondamento.
    """
    chiave: str
    griglia: tuple
    fine: float | None
    reale: bool = False

    @property
    def scelta(self) -> bool:
        return self.fine is None

    def unita(self, v) -> int:
        return _arrotonda((float(v) - float(self.griglia[0])) / float(self.fine))

    def valore(self, u: int):
        if self.reale:
            return round(float(self.griglia[0]) + int(u) * float(self.fine), 10)
        return int(self.griglia[0]) + int(u) * int(self.fine)

    @property
    def massimo(self) -> int:
        return self.unita(self.griglia[-1])

    @property
    def buco(self) -> int:
        """Il buco più largo fra due valori della griglia, in passi fini; 0 se la griglia ha un valore solo."""
        if self.scelta or len(self.griglia) < 2:
            return 0
        u = [self.unita(v) for v in self.griglia]
        return max(b - a for a, b in zip(u, u[1:]))


def assi_teoria(st: SpazioTeoria, blocchi) -> list[Asse]:
    per_nome = {b.nome: b for b in blocchi}
    out = []
    for chiave, griglia in st.griglie.items():
        nome, par = chiave.split(".", 1)
        p = next(q for q in per_nome[nome].parametri if q.nome == par)
        if isinstance(p, Categoria):
            out.append(Asse(chiave, tuple(griglia), None))
        elif isinstance(p, Reale):
            out.append(Asse(chiave, tuple(griglia), float(p.passo), True))
        else:
            out.append(Asse(chiave, tuple(griglia), int(p.passo)))
    return out


def passi_zoom(buco: int, giri: int) -> list[int]:
    """
    Il passo di ogni giro, in passi fini (P5, 07/11): la metà del buco più largo, poi la media geometrica fra quella e
    il passo fine, poi il passo fine; con più giri, una scala geometrica dalla metà al passo fine. Arrotondati a metà
    strada verso l'alto, mai sotto il passo fine. Un buco di 8 dà 4, 2, 1; uno di 96 dà 48, 7, 1.
    """
    if giri < 1:
        raise ValueError("serve almeno un giro di zoom")
    if buco <= 0 or giri == 1:
        return [1] * giri
    meta = max(1, _arrotonda(buco / 2))
    return [max(1, _arrotonda(meta ** ((giri - g) / (giri - 1)))) for g in range(1, giri + 1)]


def spazio_giro(assi, partenza: list[dict], giro: int, giri: int) -> Spazio:
    """
    Lo spazio del giro `giro` (da 1): per ogni asse dal minimo al massimo dei valori di `partenza` ({chiave: valore}),
    allargato del passo del giro prima (al primo giro: il buco più largo), dentro i confini, al passo nuovo, con il
    reticolo che parte dal minimo. Per una scelta, i valori presenti in `partenza`, nell'ordine della griglia.
    """
    if not partenza:
        raise ValueError("lo zoom riparte da almeno una strategia calcolabile")
    parametri = []
    for a in assi:
        valori = [p[a.chiave] for p in partenza]
        if a.scelta:
            parametri.append(Categoria(a.chiave, tuple(v for v in a.griglia if v in valori)))
            continue
        passi = passi_zoom(a.buco, giri)
        passo = passi[giro - 1]
        largo = a.buco if giro == 1 else passi[giro - 2]
        u = [a.unita(v) for v in valori]
        m, mm = min(u), max(u)
        basso, alto = max(0, m - largo), min(a.massimo, mm + largo)
        lo = m - ((m - basso) // passo) * passo
        hi = lo + ((alto - lo) // passo) * passo
        parametri.append(Intero(a.chiave, lo, hi, passo))
    return Spazio(parametri)


def valori_punto(assi, punto: dict) -> dict:
    """Da un punto dello spazio del giro (unità, o valori per le scelte) a {chiave: valore}."""
    return {a.chiave: (punto[a.chiave] if a.scelta else a.valore(punto[a.chiave])) for a in assi}


def descrivi_giro(assi, spazio: Spazio) -> list[dict]:
    """Per il registro: per ogni parametro da, a e passo in valori veri (o i valori di una scelta)."""
    out = []
    for a, p in zip(assi, spazio.parametri):
        if a.scelta:
            out.append({"parametro": a.chiave, "valori": list(p.valori)})
        else:
            out.append({"parametro": a.chiave, "da": a.valore(p.minimo), "a": a.valore(p.massimo),
                        "passo": round(p.passo * a.fine, 10) if a.reale else int(p.passo * a.fine)})
    return out


def cerca(funzione: Callable[[dict], tuple], spazio: Spazio, prove: int, seme: int, opzioni) -> None:
    """
    Il genetico di L1 con `prove` valutazioni CONTATE. `funzione(punto) -> (valore, contata)`: un punto degenere o già
    visto torna con contata=False e non consuma il budget. Il genetico si riprende dal suo stato con un budget più
    grande (identico a una corsa sola, L1) finché le contate arrivano a `prove` o lo spazio finisce.
    """
    contate = [0]

    def f(punto):
        valore, contata = funzione(punto)
        contate[0] += bool(contata)
        return valore

    stato, chiamate = None, 0
    while contate[0] < prove:
        esito = genetico(f, spazio, chiamate + (prove - contate[0]), seme, opzioni, stato)
        if esito.valutazioni == chiamate or esito.esaurito:
            break
        chiamate, stato = esito.valutazioni, esito.stato


def zoom(assi, migliori: Callable[[], list[dict]], funzione: Callable[[dict, int], tuple], giri: int, per_giro: int,
         semi: list[int]) -> list[dict]:
    """
    I giri dello zoom. `migliori()` dà i {chiave: valore} delle strategie da cui ripartire; `funzione(valori, giro)`
    -> (t, contata). Uno spazio con al massimo `per_giro` punti si prova tutto (forza bruta), se no il genetico.
    """
    out = []
    for g in range(1, giri + 1):
        spazio = spazio_giro(assi, migliori(), g, giri)

        def f(punto, _g=g):
            return funzione(valori_punto(assi, punto), _g)

        if spazio.totale <= per_giro:
            modo = "forza bruta"
            for indici in itertools.product(*(range(k) for k in spazio.dimensioni)):
                f(spazio.punto(indici))
        else:
            modo = "genetico"
            cerca(f, spazio, per_giro, semi[g - 1], PREDEFINITE)
        out.append({"giro": g, "punti": int(spazio.totale), "modo": modo, "spazio": descrivi_giro(assi, spazio)})
    return out


# ------------------------------------------------------------------ l'altopiano
def vicini(strategia: Strategia, blocchi: dict, variazione_ore: float = 0.15, spostamento_min: int = 1) -> list[tuple]:
    """
    I vicini della strategia, un parametro alla volta (P5): (chiave, verso, valore, valori della strategia vicina).
    - Parametri in ore (in barre): ±`variazione_ore`, alla barra più vicina, spostamento di almeno `spostamento_min`
      barre; sotto il minimo del parametro (1 barra; 5 per periodo di RSI e ADX e ATR lungo) il vicino non c'è.
    - Altri numeri (soglie, percentile dello stop): il valore adiacente nella griglia di P-L2, sopra e sotto; fra due
      valori della griglia, quei due; al bordo uno solo.
    - Il target è un interruttore: niente vicini.
    """
    out = []
    for nome in strategia.blocchi:
        b, valori = blocchi[nome], strategia.valori_di(nome)
        for p in b.parametri:
            if isinstance(p, Categoria):
                continue
            v = valori[p.nome]
            if p.nome.endswith("_barre"):
                giu = _arrotonda(v * (1.0 - variazione_ore))
                su = _arrotonda(v * (1.0 + variazione_ore))
                giu = min(giu, v - spostamento_min)
                su = max(su, v + spostamento_min)
                coppia = (giu if giu >= BARRE_MINIME.get(p.nome, 1) else None, su)
            else:
                griglia = sorted(b.griglia[p.nome])
                sotto = [g for g in griglia if g < v]
                sopra = [g for g in griglia if g > v]
                coppia = (sotto[-1] if sotto else None, sopra[0] if sopra else None)
            for verso, x in zip(("giu", "su"), coppia):
                if x is None:
                    continue
                nuovi = {n: strategia.valori_di(n) for n in strategia.blocchi}
                nuovi[nome][p.nome] = x
                out.append((f"{nome}.{p.nome}", verso, x, nuovi))
    return out


def giudica_altopiano(t_centro: float, vicini_t_ev: list[tuple], soglie: dict) -> dict:
    """
    La strategia regge se (P5): la mediana del t dei vicini è almeno `mediana_min` × il suo t, il vicino peggiore
    almeno `peggiore_min` × il suo t, e tutti i vicini hanno EV netto > 0. Un t non calcolabile vale come il peggiore
    possibile. Senza vicini non si può dire che regga.
    """
    if not vicini_t_ev:
        return {"mediana": math.nan, "peggiore": math.nan, "ev_positivi": False, "regge": False,
                "motivo": "nessun vicino da provare"}
    ts = np.array([t if _finito(t) else -math.inf for t, _ in vicini_t_ev], dtype=float)
    mediana, peggiore = float(np.median(ts)), float(ts.min())
    ev_positivi = all(_finito(ev) and ev > 0 for _, ev in vicini_t_ev)
    motivo = ""
    if not mediana >= soglie["mediana_min"] * t_centro:
        motivo = f"mediana dei vicini {mediana:.2f}, sotto {soglie['mediana_min']} × {t_centro:.2f}"
    elif not peggiore >= soglie["peggiore_min"] * t_centro:
        motivo = f"vicino peggiore {peggiore:.2f}, sotto {soglie['peggiore_min']} × {t_centro:.2f}"
    elif not ev_positivi:
        motivo = "un vicino ha EV netto non positivo"
    return {"mediana": mediana, "peggiore": peggiore, "ev_positivi": ev_positivi, "regge": not motivo,
            "motivo": motivo}


# ------------------------------------------------------------------ il lavoro di un processo
def _annida(teoria: Teoria, piatti: dict) -> dict:
    out = {n: {} for n in teoria.blocchi}
    for chiave, v in piatti.items():
        nome, par = chiave.split(".", 1)
        out[nome][par] = v
    return out


def _appiattisci(valori: dict) -> dict:
    return {f"{n}.{p}": v for n, d in valori.items() for p, v in d.items()}


def _in_ordine_di_t(righe, quante: int, solo_passano: bool = False) -> list[dict]:
    """Le righe calcolabili dal t più alto, a parità la più vecchia; con solo_passano, quelle della condizione 1."""
    scelte = [(i, r) for i, r in enumerate(righe) if _finito(r["t"]) and (r["passa"] or not solo_passano)]
    scelte.sort(key=lambda x: (-x[1]["t"], x[0]))
    return [r for _, r in scelte[:quante]]


class _ProveTeoria:
    """Le prove di una teoria: memoria per impronta, righe contate, combinazioni degeneri annotate."""

    def __init__(self, lavoro: "_Lavoro", teoria: Teoria, righe_prima=()):
        self.l, self.teoria = lavoro, teoria
        self.viste = {r["id"]: r for r in righe_prima}
        self.ordine = list(righe_prima)      # tutte le righe della teoria, nell'ordine in cui sono state valutate
        self.nuove: list[dict] = []          # le righe contate in questo passo
        self.degeneri: dict = {}
        self.gia_viste = 0
        self.scartate_degeneri = 0

    def degenere(self, valori: dict, fase: str) -> bool:
        """verifica_degenerazione sulle combinazioni dei trigger e filtri con parametri; annota le degeneri."""
        l, t = self.l, self.teoria
        richieste = [(l.per_nome[n], t.lato, valori[n]) for n in (t.trigger, *t.filtri) if l.per_nome[n].parametri]
        if not richieste:
            return False
        brutta = False
        for (b, lato, v), (esito, quota) in zip(richieste, l.controllo.esiti(richieste)):
            if esito == "OK":
                continue
            brutta = True
            k = (b.nome, 0 if b.neutro else lato, tuple(sorted(v.items())))
            if k not in self.degeneri:
                self.degeneri[k] = {"fase": fase, "blocco": b.nome,
                                    "lato": "entrambi" if b.neutro and l.due_lati else NOME_LATO[lato],
                                    "valori": dict(v), "esito": esito, "quota_vere": quota, "volte": 0}
            self.degeneri[k]["volte"] += 1
        self.scartate_degeneri += brutta
        return brutta

    def strategia(self, valori: dict) -> tuple[Strategia, str]:
        s = Strategia.da_teoria(self.teoria, valori)
        return s, id_strategia(s, self.l.symbol, self.l.timeframe)

    def valuta(self, valori: dict, fase: str, controlla: bool = True) -> tuple[float, bool]:
        """(t, contata). Degenere: NaN, non contata. Già vista: il suo t, non contata."""
        if controlla and self.degenere(valori, fase):
            return math.nan, False
        s, i = self.strategia(valori)
        r = self.viste.get(i)
        if r is not None:
            self.gia_viste += 1
            return (r["t"] if _finito(r["t"]) else math.nan), False
        m = self.l.valutatore.valuta(s)
        passa, motivo = qualita_1(m, self.l.config["qualita_1"])
        r = {"fase": fase, "id": i, "valori": s.come_dict()["valori"], **m.come_dict(), "passa": passa,
             "motivo": motivo}
        self.viste[i] = r
        self.ordine.append(r)
        self.nuove.append(r)
        return obiettivo(m), True


class _Lavoro:
    """Quello che serve a un processo per lavorare sulle teorie: blocchi, cache, controllo, valutatore."""

    def __init__(self, config: dict, df: pd.DataFrame, costi: dict, rimaste: dict, esiti: dict | None = None,
                 cache: Cache | None = None, controllo: ControlloDegenerazione | None = None):
        self.config = config
        self.symbol, self.timeframe = config["symbol"], config["timeframe"]
        self.due_lati = len(lati_config(config)) > 1
        self.blocchi = blocchi_da_config(config)
        self.per_nome = {b.nome: b for b in self.blocchi}
        self.cache = cache if cache is not None else Cache(df, LIMITE_CACHE_MB)
        self.controllo = controllo if controllo is not None else ControlloDegenerazione(self.cache)
        if esiti:
            self.controllo._esiti.update(esiti)
        self.valutatore = Valutatore(self.blocchi, self.cache, Costi(self.cache.df, costi))
        self.rimaste = rimaste

    # -------------------------------------------------------------- passo 1
    def passo_1(self, teoria: Teoria) -> dict:
        st = SpazioTeoria(teoria, self.blocchi, self.rimaste)
        pt = _ProveTeoria(self, teoria)
        seme = seme_teoria(self.config["seme"], teoria.id)
        budget = self.config["budget"]["per_teoria_passo_1"]
        degeneri = [0]

        def f(punto):
            valori = st.valori(punto)
            if not st.ammesso(valori):           # tolta all'avvio come degenere: non consuma una prova
                degeneri[0] += 1
                return math.nan, False
            return pt.valuta(valori, "passo_1", controlla=False)

        ammessi = st.quanti_ammessi()
        if ammessi <= budget:
            modo = "griglia completa"
            for punto in st.punti_ammessi():
                f(punto)
        else:
            modo = "genetico"
            cerca(f, st.spazio, budget, seme, AMPIEZZA)
        migliore = _in_ordine_di_t(pt.nuove, 1, solo_passano=True)
        return {"teoria": teoria.id, "seme": seme, "modo": modo, "punti_ammessi": ammessi,
                "degeneri_proposti": degeneri[0], "prove": pt.nuove,
                "migliore": migliore[0]["id"] if migliore else None, "t": migliore[0]["t"] if migliore else None}

    # -------------------------------------------------------------- passo 2: zoom e altopiano
    def passo_2(self, compito: tuple) -> dict:
        teoria, righe_1 = compito
        cfg_b, alt = self.config["budget"], self.config["altopiano"]
        st = SpazioTeoria(teoria, self.blocchi, self.rimaste)
        assi = assi_teoria(st, self.blocchi)
        pt = _ProveTeoria(self, teoria, righe_1)
        giri_n = cfg_b["giri_zoom"]
        semi = [seme_teoria(self.config["seme"], f"{teoria.id}|zoom_{g}") for g in range(1, giri_n + 1)]
        conti = {g: [0, 0, 0] for g in range(1, giri_n + 1)}     # contate, già viste, degeneri

        def migliori():
            return [_appiattisci(r["valori"]) for r in _in_ordine_di_t(pt.ordine, MIGLIORI_ZOOM)]

        def funzione(piatti, g):
            prima = (pt.gia_viste, pt.scartate_degeneri)
            t, contata = pt.valuta(_annida(teoria, piatti), f"zoom_{g}")
            conti[g][0] += contata
            conti[g][1] += pt.gia_viste - prima[0]
            conti[g][2] += pt.scartate_degeneri - prima[1]
            return t, contata

        partenze = []

        def migliori_annotati():
            m = migliori()
            partenze.append([id_strategia(Strategia.da_teoria(teoria, _annida(teoria, x)), self.symbol,
                                          self.timeframe) for x in m])
            return m

        giri = zoom(assi, migliori_annotati, funzione, giri_n, cfg_b["prove_per_giro"], semi)
        for g in giri:
            n = g["giro"]
            g.update({"partenza": partenze[n - 1], "prove": conti[n][0], "gia_viste": conti[n][1],
                      "degeneri": conti[n][2]})

        # l'altopiano
        prove_alt, giudizi, scelta, motivo = 0, [], None, ""
        for c in _in_ordine_di_t(pt.ordine, alt["candidati_max"], solo_passano=True):
            s = Strategia.da_teoria(teoria, c["valori"])
            righe, finito = [], False
            for chiave, verso, valore, valori in vicini(s, self.per_nome, alt["variazione_ore"],
                                                         alt["spostamento_min_barre"]):
                riga = {"parametro": chiave, "verso": verso, "valore": valore}
                if pt.degenere(valori, "altopiano"):
                    righe.append({**riga, "degenere": True})
                    continue
                _, i = pt.strategia(valori)
                if i not in pt.viste and prove_alt >= alt["prove_max"]:
                    finito = True
                    break
                _, contata = pt.valuta(valori, "altopiano", controlla=False)
                prove_alt += contata
                r = pt.viste[i]
                righe.append({**riga, "id": i, "t": r["t"], "ev_bp": r["ev_bp"], "contata": contata})
            if finito:
                motivo = f"budget dell'altopiano finito ({alt['prove_max']} prove)"
                giudizi.append({"candidata": c["id"], "t": c["t"], "vicini": righe, "regge": False, "motivo": motivo})
                break
            g = giudica_altopiano(c["t"], [(r["t"], r["ev_bp"]) for r in righe if not r.get("degenere")], alt)
            giudizi.append({"candidata": c["id"], "t": c["t"], "vicini": righe, **g})
            if g["regge"]:
                scelta = c
                break
        if scelta is None and not motivo:
            motivo = (f"nessuna delle {len(giudizi)} candidate regge l'altopiano" if giudizi
                      else "nessuna strategia passa la condizione 1")
        return {"teoria": teoria.id, "giri": giri, "altopiano": giudizi,
                "prove_zoom": sum(c[0] for c in conti.values()), "prove_altopiano": prove_alt,
                "esito": "regge" if scelta is not None else "esce", "motivo": "" if scelta is not None else motivo,
                "scelta": scelta, "prove": pt.nuove, "degeneri": list(pt.degeneri.values())}


# ------------------------------------------------------------------ i processi
_LAVORO: _Lavoro | None = None


def _inizia(config, df, costi, rimaste, esiti) -> None:
    global _LAVORO
    imposta_mercato_crypto()
    _LAVORO = _Lavoro(config, df, costi, rimaste, esiti)


def _fai_passo_1(teoria):
    return _LAVORO.passo_1(teoria)


def _fai_passo_2(compito):
    return _LAVORO.passo_2(compito)


def _in_ordine(funzione, compiti: list, prep: "Preparazione", processi: int):
    """I risultati nell'ordine dei compiti, con 1 processo (qui) o con `processi` processi."""
    global _LAVORO
    if processi <= 1 or len(compiti) <= 1:
        _LAVORO = prep.lavoro
        for c in compiti:
            yield funzione(c)
        return
    ctx = mp.get_context("spawn")
    with ctx.Pool(min(processi, len(compiti)), initializer=_inizia, initargs=prep.per_processi()) as pool:
        yield from pool.imap(funzione, compiti, chunksize=1)


# ------------------------------------------------------------------ la preparazione
@dataclass
class Preparazione:
    """Indicatori, valori degeneri, famiglie, teorie e budget: tutto quello che si fa prima della prima prova."""
    config: dict
    df: pd.DataFrame
    costi: dict
    blocchi: list
    lati: list
    rimaste: dict
    tolte: list
    famiglie: dict
    misura: pd.DataFrame
    teorie: list
    resoconto: dict
    budget_massimo: int
    lavoro: _Lavoro
    durata_s: float

    def per_processi(self) -> tuple:
        return (self.config, self.df, self.costi, self.rimaste, dict(self.lavoro.controllo._esiti))


def prepara(config: dict, pezzi) -> Preparazione:
    """Sul solo pezzo di ricerca: niente prove, solo segnali (valori degeneri, famiglie)."""
    t0 = time.perf_counter()
    imposta_mercato_crypto()
    df = aggiungi_indicatori(pezzi.ricerca)
    cache = Cache(df, LIMITE_CACHE_MB)
    blocchi = blocchi_da_config(config)
    lati = lati_config(config)
    controllo = ControlloDegenerazione(cache)
    rimaste, tolte = togli_degeneri(blocchi, cache, lati, controllo)
    famiglie, misura = misura_famiglie(blocchi, cache, lati)
    teorie = genera_teorie(config, blocchi, famiglie, rimaste)
    if not teorie:
        raise ValueError("nessuna teoria: tutti i blocchi sono usciti o la config non ne forma nessuna.")
    resoconto = resoconto_teorie(config, blocchi, famiglie, rimaste, teorie)
    massimo = controlla_budget(len(teorie), config)
    costi = pezzi.costi(PEZZO)
    lavoro = _Lavoro(config, df, costi, rimaste, cache=cache, controllo=controllo)
    return Preparazione(config, df, costi, blocchi, lati, rimaste, tolte, famiglie, misura, teorie, resoconto, massimo,
                        lavoro, time.perf_counter() - t0)


# ------------------------------------------------------------------ i file della ricerca
def _leggi_jsonl(percorso: str) -> list[dict]:
    registro.togli_riga_rotta(percorso)
    if not os.path.exists(percorso):
        return []
    with open(percorso, encoding="utf-8") as f:
        return [json.loads(r) for r in f.read().splitlines() if r]


def _aggiungi_jsonl(percorso: str, oggetto: dict) -> None:
    with open(percorso, "a", encoding="utf-8") as f:
        f.write(registro.json_riga(oggetto) + "\n")


def _scrivi_stato(cartella: str, stato: dict) -> None:
    percorso = os.path.join(cartella, FILE_STATO)
    with open(percorso + ".tmp", "w", encoding="utf-8") as f:
        json.dump(stato, f, ensure_ascii=False, indent=2)
    os.replace(percorso + ".tmp", percorso)


def _righe_prove(id_ricerca: str, teoria: str, righe) -> list[dict]:
    return [{"id_ricerca": id_ricerca, "pezzo": PEZZO, "fase": r["fase"], "teoria": teoria, "id_strategia": r["id"],
             "trade": r["trade"], "ev_bp": r["ev_bp"], "t": r["t"]} for r in righe]


def _controlla_gia_fatte(fatte: list[dict], attese: list[str], nome: str) -> None:
    ids = [r["teoria"] for r in fatte]
    if ids != attese[: len(ids)]:
        raise ValueError(f"{nome}: le teorie già scritte non sono quelle di questa ricerca, nello stesso ordine: "
                         "la ripresa si ferma (la cartella è stata toccata o i dati sono cambiati).")


# ------------------------------------------------------------------ il registro della ricerca
def _evento_avvio(id_ricerca, config, pezzi, prep: Preparazione) -> dict:
    misura = prep.misura.replace({np.nan: None}).to_dict("records") if len(prep.misura) else []
    return {"tipo": "avvio_ricerca", "id_ricerca": id_ricerca, "impronta_config": impronta_config(config),
            "symbol": config["symbol"], "timeframe": config["timeframe"], "impronte_dati": dict(pezzi.impronte),
            "barre": {"ricerca": len(pezzi.ricerca), "selezione": len(pezzi.selezione)},
            "teorie": prep.resoconto, "famiglie": misura, "degeneri_avvio": prep.tolte,
            "budget_massimo": prep.budget_massimo}


def _registra_avvio(base: str, evento: dict) -> None:
    """Scrive l'avvio una volta sola; a una ripresa controlla che dati e teorie siano gli stessi."""
    for e in registro.leggi_registro(base):
        if e.get("tipo") == "avvio_ricerca" and e.get("id_ricerca") == evento["id_ricerca"]:
            for k in ("impronta_config", "impronte_dati", "teorie", "degeneri_avvio"):
                if (json.dumps(e.get(k), sort_keys=True, default=registro.nativo)
                        != json.dumps(json.loads(registro.json_riga(evento[k])), sort_keys=True)):
                    raise ValueError(f"ripresa di {evento['id_ricerca']}: «{k}» è cambiato dall'avvio "
                                     "(i dati o il codice sono diversi): la ricerca si ferma.")
            if e.get("macchina") == registro.macchina():
                return
    registro.scrivi_evento(base, evento)


# ------------------------------------------------------------------ l'esito
@dataclass
class EsitoRicerca:
    id_ricerca: str
    cartella: str
    finita: bool
    imbuto: dict
    passo_1: pd.DataFrame
    passo_2: pd.DataFrame
    sopravvissute: pd.DataFrame
    prove: int                       # le righe di questa ricerca nel file delle prove di questa macchina
    budget_massimo: int
    degeneri_avvio: list
    degeneri_zoom: list
    resoconto: dict
    durata_s: float
    tempi: dict = field(default_factory=dict)
    selezione: "sel_mod.Selezione | None" = None
    conto: dict = field(default_factory=dict)


def _tabelle(ris_1: list[dict], ris_2: list[dict], al_passo_2: list[str]):
    entrano = set(al_passo_2)
    p1 = pd.DataFrame([{"teoria": r["teoria"], "modo": r["modo"], "punti_ammessi": r["punti_ammessi"],
                        "prove": len(r["prove"]), "degeneri_proposti": r["degeneri_proposti"],
                        "tenuta": r["migliore"] is not None, "t": r["t"] if r["t"] is not None else math.nan,
                        "id_strategia": r["migliore"], "al_passo_2": r["teoria"] in entrano} for r in ris_1])
    righe = []
    for r in ris_2:
        s = r["scelta"] or {}
        righe.append({"teoria": r["teoria"], "prove_zoom": r["prove_zoom"], "prove_altopiano": r["prove_altopiano"],
                      "esito": r["esito"], "motivo": r["motivo"], "id_strategia": s.get("id"),
                      "t": s.get("t", math.nan), "ev_bp": s.get("ev_bp", math.nan), "trade": s.get("trade", 0),
                      "valori": json.dumps(s.get("valori"), ensure_ascii=False, sort_keys=True) if s else None})
    p2 = pd.DataFrame(righe, columns=["teoria", "prove_zoom", "prove_altopiano", "esito", "motivo", "id_strategia", "t",
                                      "ev_bp", "trade", "valori"])
    vive = p2[p2["esito"] == "regge"].sort_values(["t", "teoria"], ascending=[False, True]).reset_index(drop=True)
    return p1, p2, vive


def _degeneri_zoom(ris_2: list[dict], tolte: list[dict]) -> list[dict]:
    """Le combinazioni nuove trovate degeneri durante zoom e altopiano, una volta ciascuna, con quante teorie."""
    gia = {(t["blocco"], t["lato"], json.dumps(t["valori"], sort_keys=True)) for t in tolte}
    out: dict = {}
    for r in ris_2:
        for d in r["degeneri"]:
            k = (d["blocco"], d["lato"], json.dumps(d["valori"], sort_keys=True))
            if k in gia:
                continue
            if k not in out:
                out[k] = {**{c: d[c] for c in ("blocco", "lato", "valori", "esito", "quota_vere")}, "teorie": 0,
                          "volte": 0}
            out[k]["teorie"] += 1
            out[k]["volte"] += d["volte"]
    return [out[k] for k in sorted(out)]


# ------------------------------------------------------------------ il lancio
def lancia(config: dict, cartella_dati, *, ferma_dopo: int | None = None, verbose: bool = True,
           data: str | None = None, avanzamento: Callable[[dict], None] | None = None) -> EsitoRicerca:
    """
    La ricerca dei passi 1 e 2 con l'altopiano (vedi la testa del file). Se la stessa config è già stata lanciata,
    riprende da dove era. `ferma_dopo` = fermati dopo tante teorie (per i collaudi della ripresa).
    `avanzamento` (L5a, 08/11): chiamata dopo ogni teoria scritta con {fase, numero, totale, prove, prove_ora,
    secondi, budget_massimo}; prove_ora = le prove di questa chiamata, secondi = da quando è partita. Non cambia nulla
    della ricerca.
    """
    t_inizio = time.perf_counter()
    controlla_config(config)
    symbol, timeframe, processi = config["symbol"], config["timeframe"], config["processi"]
    id_ricerca = salva_config(config, cartella_dati, data)
    base = cartella_asset(cartella_dati, symbol, timeframe)
    cartella = os.path.join(base, id_ricerca)
    pezzi = carica_pezzi(symbol, timeframe, Confini.da_config(config["confini"]), cartella_dati)
    prep = prepara(config, pezzi)
    _registra_avvio(base, _evento_avvio(id_ricerca, config, pezzi, prep))
    prove = registro.FileProve(cartella)
    per_id = {t.id: t for t in prep.teorie}
    tempi = {"preparazione_s": prep.durata_s}
    fatte_ora = [0]                  # teorie finite in questa chiamata, passo 1 e passo 2
    prove_prima = len(prove)

    def scrivi(percorso, ris, nome_fase, numero, totale):
        prove.aggiungi(_righe_prove(id_ricerca, ris["teoria"], ris["prove"]))
        _aggiungi_jsonl(percorso, ris)
        fatte_ora[0] += 1
        if avanzamento is not None:
            avanzamento({"fase": nome_fase, "numero": numero, "totale": totale, "prove": len(prove),
                         "prove_ora": len(prove) - prove_prima, "secondi": time.perf_counter() - t_inizio,
                         "budget_massimo": prep.budget_massimo})
        if verbose and (numero % 50 == 0 or numero == totale):
            print(f"  {nome_fase}: teoria {numero} di {totale}, {len(prove)} prove, "
                  f"{time.perf_counter() - t_inizio:.0f} s", flush=True)

    def basta() -> bool:
        return ferma_dopo is not None and fatte_ora[0] >= ferma_dopo

    def stato(fase, **altro):
        _scrivi_stato(cartella, {"id_ricerca": id_ricerca, "fase": fase, "teorie": len(prep.teorie), **altro})

    if verbose:
        print(f"Ricerca {id_ricerca}: {len(prep.teorie)} teorie, budget massimo {prep.budget_massimo} prove, "
              f"{processi} processi", flush=True)

    # ---------------------------------------------------------- passo 1
    t0 = time.perf_counter()
    p1 = os.path.join(cartella, FILE_PASSO_1)
    gia = _leggi_jsonl(p1)
    _controlla_gia_fatte(gia, [t.id for t in prep.teorie], "passo 1")
    da_fare = prep.teorie[len(gia):]
    for numero, ris in enumerate(_in_ordine(_fai_passo_1, da_fare, prep, processi), start=len(gia) + 1):
        scrivi(p1, ris, "passo 1", numero, len(prep.teorie))
        if basta():
            break
    tempi["passo_1_s"] = time.perf_counter() - t0
    ris_1 = _leggi_jsonl(p1)
    if len(ris_1) < len(prep.teorie):
        stato("passo_1", fatte=len(ris_1))
        return _esito(id_ricerca, cartella, False, prep, ris_1, [], [], prove, t_inizio, tempi)

    tenute = sorted((r for r in ris_1 if r["migliore"] is not None), key=lambda r: (-r["t"], r["teoria"]))
    al_passo_2 = [r["teoria"] for r in tenute[: config["budget"]["teorie_passo_2"]]]
    stato("passo_2", fatte_passo_1=len(ris_1), al_passo_2=len(al_passo_2))

    # ---------------------------------------------------------- passo 2 e altopiano
    t0 = time.perf_counter()
    p2 = os.path.join(cartella, FILE_PASSO_2)
    gia = _leggi_jsonl(p2)
    _controlla_gia_fatte(gia, al_passo_2, "passo 2")
    righe_1 = {r["teoria"]: r["prove"] for r in ris_1}
    compiti = [(per_id[t], righe_1[t]) for t in al_passo_2[len(gia):]]
    if compiti and not basta():
        for numero, ris in enumerate(_in_ordine(_fai_passo_2, compiti, prep, processi), start=len(gia) + 1):
            scrivi(p2, ris, "passo 2", numero, len(al_passo_2))
            if basta():
                break
    tempi["passo_2_s"] = time.perf_counter() - t0
    ris_2 = _leggi_jsonl(p2)
    if len(ris_2) < len(al_passo_2):
        stato("passo_2", fatte_passo_1=len(ris_1), al_passo_2=len(al_passo_2), fatte_passo_2=len(ris_2))
        return _esito(id_ricerca, cartella, False, prep, ris_1, ris_2, al_passo_2, prove, t_inizio, tempi)

    pezzi.verifica_impronte()
    # ---------------------------------------------------------- selezione (P6)
    t0 = time.perf_counter()
    _, _, vive = _tabelle(ris_1, ris_2, al_passo_2)
    selezione = _selezione(cartella, vive, pezzi, config, id_ricerca, prove)
    pezzi.verifica_impronte()
    tempi["selezione_s"] = time.perf_counter() - t0
    k = registro.conto_prove(cartella_dati, symbol, timeframe)
    conto = {"questa_ricerca": sum(1 for c in prove.chiavi if c[0] == id_ricerca), "asset": k,
             "soglia_da_leggere": soglia_rumore(k, config["test_individuale"]["alfa"]) if k else None}
    selezione = sel_mod.con_conto(selezione, conto)
    esito = _esito(id_ricerca, cartella, True, prep, ris_1, ris_2, al_passo_2, prove, t_inizio, tempi, selezione,
                   conto)
    if not any(e.get("tipo") == "fine_ricerca" and e.get("id_ricerca") == id_ricerca
               and e.get("macchina") == registro.macchina() for e in registro.leggi_registro(base)):
        registro.scrivi_evento(base, {
            "tipo": "fine_ricerca", "id_ricerca": id_ricerca, "impronta_config": impronta_config(config),
            "imbuto": esito.imbuto, "degeneri_zoom": esito.degeneri_zoom, "prove": conto,
            "sopravvissute": esito.sopravvissute[["teoria", "id_strategia", "t"]].to_dict("records"),
            "selezione": selezione.tabella[["teoria", "id_strategia", "t", "esito", "motivo"]].to_dict("records")})
    stato("finita", fatte_passo_1=len(ris_1), al_passo_2=len(al_passo_2), fatte_passo_2=len(ris_2),
          prove=esito.prove)
    return esito


def _selezione(cartella, vive, pezzi, config, id_ricerca, prove) -> "sel_mod.Selezione":
    """La selezione delle sopravvissute; scritta una volta in selezione.json e da lì riletta (ripresa)."""
    percorso = os.path.join(cartella, FILE_SELEZIONE)
    if not os.path.exists(percorso):
        s = sel_mod.seleziona(vive, pezzi, config, id_ricerca, prove)
        testo = registro.json_riga({k: getattr(s, k).to_dict("records") for k in ("tabella", "famiglie",
                                                                                  "sovrapposizioni")})
        with open(percorso + ".tmp", "w", encoding="utf-8") as f:
            f.write(testo + "\n")
        os.replace(percorso + ".tmp", percorso)
    with open(percorso, encoding="utf-8") as f:
        dati = json.loads(f.read())
    tabella = pd.DataFrame(dati["tabella"], columns=sel_mod.COLONNE)
    if list(tabella["id_strategia"]) != list(dict.fromkeys(vive["id_strategia"])):
        raise ValueError(f"{percorso}: le strategie non sono le sopravvissute di questa ricerca: la ripresa si ferma.")
    return sel_mod.Selezione(tabella, pd.DataFrame(dati["famiglie"]), pd.DataFrame(dati["sovrapposizioni"]))


def _esito(id_ricerca, cartella, finita, prep, ris_1, ris_2, al_passo_2, prove, t_inizio, tempi, selezione=None,
           conto=None) -> EsitoRicerca:
    p1, p2, vive = _tabelle(ris_1, ris_2, al_passo_2)
    imbuto = {"teorie": len(prep.teorie), "passo_1_tenute": int(p1["tenuta"].sum()) if len(p1) else 0,
              "passo_2": len(ris_2), "altopiano": len(vive)}
    if selezione is not None:
        t = selezione.tabella
        imbuto["selezione"] = int((t["esito"] != "scartata").sum())
        imbuto["scelte"] = int((t["esito"] == "scelta").sum())
    return EsitoRicerca(id_ricerca, cartella, finita, imbuto, p1, p2, vive,
                        sum(1 for k in prove.chiavi if k[0] == id_ricerca), prep.budget_massimo, prep.tolte,
                        _degeneri_zoom(ris_2, prep.tolte), prep.resoconto, time.perf_counter() - t_inizio, tempi,
                        selezione, dict(conto or {}))
