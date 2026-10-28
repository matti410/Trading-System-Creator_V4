"""
Collaudo dell'incertezza del Lab sui rendimenti sovrapposti (28/10/2026,
docs/75 §3, PR 1 del §6): SOLO il collaudo, nessuna correzione.

Su mercati inventati SENZA nessun effetto (random walk M15, 800 giorni; una
variante con la volatilita' variabile) e trigger finti indipendenti dai prezzi,
con H = 41, si conta quante volte i quattro punti del Lab promuovono per caso:

    rosa (3a)          il trigger e' «candidata» (t > 0, quota di falsi positivi, due meta')
    atlante (3c)       la situazione «passa»
    event study (2c)   «Supera il rumore» a favore del trade
    profilo (2a)       almeno un'ora colorata su 96

con il calcolo di OGGI (lo sconto dei pesi decrescenti) e con quello della MAPPA
(le coppie a meno di H barre per intero, i blocchi di una settimana se la
varianza esce zero o negativa). Dal 28/10/2026 (PR 2, docs/75 §7) il calcolo
della mappa e' quello dell'engine (stagionalita.errore_sovrapposti) e il calcolo
di oggi si ottiene a richiesta (stagionalita.calcolo_vecchio()). La sezione D
confronta l'engine con il calcolo collaudato nella PR #86 (le formule di prima
con le quattro funzioni sostituite dentro il test, calcolo_mappa): al bit, e
nell'atlante entro 1e-12 (ordine delle somme).

I trigger finti (10 per mercato, meta' long e meta' short):
    F · frequente   circa 15.000 volte, a grappoli (episodi di circa 16 barre)
    M · medio       3.000 volte, sparse a caso
    R · raro        300 volte, sempre a 200 barre o piu' di distanza: il riferimento
                    della rosa e dell'event study
    D · raro denso  circa 1.800 volte, a 41 o 42 barre di distanza (mai due a meno
                    di H): il riferimento dell'atlante (Mattia, 28/10/2026), dove il
                    raro ha troppo pochi ingressi per cella e non si misura mai

Il criterio, deciso da Mattia prima del collaudo (docs/75 §5, D4): con il
calcolo della mappa, F e M entro 3 punti dal riferimento e sotto il 20%; il
profilo entro q (i mercati con almeno un'ora colorata). Il calcolo di oggi si
riporta, non si giudica. Se un riferimento non misura niente (zero situazioni
misurate in rosa, atlante o event study), il test si ferma con un errore.

La sezione C scompone l'incertezza su 3 mercati (rosa con il raro, atlante con
il raro denso) in parte del trigger, parte del mercato della stessa ora e parte
incrociata, nei due calcoli: la parte del trigger deve coincidere al bit.

Si lancia da terminale, dalla cartella del progetto:

    python test_incertezza_lab.py                 # 200 mercati (100 + 100), la suite
    python test_incertezza_lab.py --mercati 1000  # il giro da 1.000 per variante, una volta sola

(su Windows: PYTHONIOENCODING=utf-8). Non serve nessun file di dati.
"""
from __future__ import annotations

import contextlib
import sys
import time
import warnings

import numpy as np
import pandas as pd

warnings.simplefilter("ignore")

import engine.atlante as at
import engine.event_study as es
import engine.rosa as ro
import engine.stagionalita as stg
from engine import mappa as mp
from engine import registry as reg
from engine.quarantena import imposta_rollover
from test_atlante import _indice
from test_mappa import _prezzi

H, PIP = 41, 0.01
SETTIMANA = 7 * 96                      # barre M15 in una settimana: i blocchi della mappa
MARGINE, LIMITE = 0.03, 0.20            # D4 (Mattia, 28/10/2026): entro 3 punti dal raro, sotto il 20%
TIPI = (("F", 4), ("M", 4), ("R", 2), ("D", 2))
RIFERIMENTO = {"rosa": "R", "atlante": "D", "es": "R"}   # Mattia, 28/10/2026
NOMI = [f"TL_{t}{j}" for t, k in TIPI for j in range(k)]
MASCHERE: dict = {}


def _registra() -> None:
    for nome in NOMI:
        d = 1 if int(nome[-1]) % 2 == 0 else -1
        reg.register_entry(nome, direction=d)(lambda df, _n=nome: pd.Series(MASCHERE[_n], index=df.index))


def _maschere(rng, n: int) -> None:
    """I trigger finti di un mercato: indipendenti dai prezzi per costruzione."""
    for nome in NOMI:
        tipo = nome[3]
        m = np.zeros(n, dtype=bool)
        if tipo == "F":                 # acceso circa il 20% delle barre, episodi di circa 16 barre
            i, acceso = 0, False
            while i < n:
                durata = int(rng.geometric(1 / 16 if acceso else 1 / 64))
                if acceso:
                    m[i:i + durata] = True
                i, acceso = i + durata, not acceso
        elif tipo == "M":
            m[rng.choice(n - 200, 3000, replace=False)] = True
        elif tipo == "D":               # distanze casuali di 41 o 42 barre: nessuna coppia a meno di H
            pos = 500 + np.cumsum(rng.integers(H, H + 2, size=n // H))
            m[pos[pos < n - 200]] = True
        else:
            m[np.sort(rng.choice(np.arange(500, n - 200, 200), 300, replace=False))] = True
        MASCHERE[nome] = m


# ========================================================================
# Il calcolo della mappa, applicato solo dentro il test
# ========================================================================

PUNTO = ["-"]                           # il punto del Lab che si sta misurando (per i contatori)
BLOCCHI: dict = {}                      # (punto, tipo) -> [incertezze calcolate, di cui con i blocchi di una settimana]


def _tipo_in_misura() -> str:
    """Il tipo (F, M, R, D) del trigger che rosa, atlante o event study stanno misurando: la variabile
    `nome` del ciclo sui trigger, qualche chiamata piu' su; "-" se non c'e' (il profilo)."""
    f = sys._getframe(2)
    while f is not None:
        nome = f.f_locals.get("nome")
        if isinstance(nome, str) and nome in NOMI:
            return nome[3]
        f = f.f_back
    return "-"


def _conta_blocchi(a_blocchi: bool) -> None:
    c = BLOCCHI.setdefault((PUNTO[0], _tipo_in_misura()), [0, 0])
    c[0] += 1
    c[1] += int(a_blocchi)


def _es_senza_sconto(v: np.ndarray, pos: np.ndarray, k: int, settimana=None, con_blocchi: bool = False):
    """event_study._errore_standard_sovrapposti senza i pesi decrescenti; blocchi di una settimana se <= 0.
    Il calcolo collaudato nella PR #86 (settimana e con_blocchi: la firma dell'engine dal 28/10/2026)."""
    nv = v.size
    if nv < 2:
        return (np.nan, False) if con_blocchi else np.nan
    res = v - v.mean()
    tot = float((res ** 2).sum()) * nv / (nv - 1)
    d = 1
    while d < nv:
        dist = pos[d:] - pos[:-d]
        vicini = dist < k
        if not vicini.any():
            break
        tot += 2.0 * float((res[d:][vicini] * res[:-d][vicini]).sum())
        d += 1
    blocchi = tot <= 0
    _conta_blocchi(blocchi)
    if blocchi:
        b = pos // SETTIMANA
        somme = np.bincount(b - b.min(), weights=res)
        tot = float((somme ** 2).sum()) * nv / (nv - 1)
    se = float(np.sqrt(tot)) / nv
    return (se, bool(blocchi)) if con_blocchi else se


def _somme_senza_sconto(u: np.ndarray, cella: np.ndarray, n_celle: int, H_: int) -> np.ndarray:
    """atlante._somme_per_cella con mappa.errore_sovrapposti, una cella alla volta."""
    out = np.zeros(n_celle)
    for j in range(n_celle):
        uj = np.where(cella == j, u, 0.0)
        if not uj.any():                # cella non misurata: u tutto zero, niente da contare
            continue
        se, blocchi = mp.errore_sovrapposti(uj, H_, SETTIMANA)
        _conta_blocchi(blocchi)
        out[j] = se ** 2
    return out


def _pesato_senza_sconto(u: np.ndarray, H_: int) -> float:
    """stagionalita.errore_standard_pesato con mappa.errore_sovrapposti."""
    se, blocchi = mp.errore_sovrapposti(u, H_, SETTIMANA)
    _conta_blocchi(blocchi)
    return se


@contextlib.contextmanager
def calcolo_mappa():
    """Le quattro funzioni dell'incertezza sostituite, solo per la durata del blocco."""
    vecchie = (stg.errore_standard_pesato, es._errore_standard_sovrapposti, ro._errore_standard_sovrapposti,
               at._somme_per_cella)
    stg.errore_standard_pesato = _pesato_senza_sconto
    es._errore_standard_sovrapposti = ro._errore_standard_sovrapposti = _es_senza_sconto
    at._somme_per_cella = _somme_senza_sconto
    try:
        yield
    finally:
        (stg.errore_standard_pesato, es._errore_standard_sovrapposti, ro._errore_standard_sovrapposti,
         at._somme_per_cella) = vecchie


# ========================================================================
# La misura di un mercato
# ========================================================================

def _misura(df: pd.DataFrame) -> dict:
    """Le promozioni per caso dei quattro punti: {punto: {trigger: promosso}}, le ore colorate e le
    situazioni misurate di ogni trigger (rosa ed event study: 0 o 1; atlante: le celle misurate)."""
    PUNTO[0] = "rosa"
    r = ro.rosa_entry(df, H, PIP, nomi=NOMI, fuso="UTC", unita="bp")
    PUNTO[0] = "atlante"
    a = at.atlante(df, H, PIP, nomi=NOMI, fuso="UTC")
    PUNTO[0] = "es"
    e = es.run_event_study(df, entry_names=NOMI, horizon=H, pip=PIP, verbose=False, fuso="UTC").sintesi
    PUNTO[0] = "profilo"
    p = stg.profilo_orario(df, H, PIP, fuso="UTC")
    PUNTO[0] = "-"
    blk = {}                            # (punto, tipo) -> [righe, con la stima a blocchi]: la colonna dell'engine
    for punto, tab in (("rosa", r), ("atlante", a[a["misurata"].astype(bool)]), ("es", e)):
        if "incertezza_blocchi" in tab.columns:
            for nome, g in tab.groupby("candidato"):
                c = blk.setdefault((punto, nome[3]), [0, 0])
                c[0] += len(g)
                c[1] += int(g["incertezza_blocchi"].astype(bool).sum())
    if "incertezza_blocchi" in p.columns:
        blk[("profilo", "-")] = [len(p), int(p["incertezza_blocchi"].astype(bool).sum())]
    return {"blocchi": blk,
            "rosa": dict(zip(r["candidato"], r["candidata"].astype(bool))),
            "atlante": {k: (int(g["passa"].sum()), len(g)) for k, g in a.groupby("candidato")},
            "es": dict(zip(e["candidato"], (e["oltre_rumore"].astype(bool) & (e["volte_incertezza"] > 0)))),
            "profilo": int(p["bh"].sum()),
            "incertezza_ore": p["incertezza"].to_numpy(dtype=float),
            "misurate": {"rosa": dict(zip(r["candidato"], np.isfinite(r["t_netto"].to_numpy(dtype=float)))),
                         "atlante": {k: int(g["misurata"].astype(bool).sum()) for k, g in a.groupby("candidato")},
                         "es": dict(zip(e["candidato"], np.isfinite(e["volte_incertezza"].to_numpy(dtype=float))))},
            "se_rosa": dict(zip(r["candidato"], r["scarto_bp"].to_numpy(dtype=float)
                                / r["t_netto"].to_numpy(dtype=float))),
            "t_es": dict(zip(e["candidato"], e["volte_incertezza"]))}


def giro(mercati: int, volatilita_variabile: bool, variabili: int) -> dict:
    """`mercati` mercati (variabili x mercati/variabili), i due calcoli sugli stessi mercati e trigger."""
    idx = _indice("2022-01-03", giorni=800, minuti=15)
    n = len(idx)
    conti = {c: {"rosa": {}, "atlante": {}, "es": {}, "profilo": 0} for c in ("oggi", "mappa")}
    raro_uguale = True
    misurate = {c: {p: 0 for p in RIFERIMENTO} for c in ("oggi", "mappa")}
    rapporti = []                       # profilo: incertezza della mappa / incertezza di oggi, ora per ora
    rapporti_raro = []                  # rosa, raro: incertezza della mappa / incertezza di oggi
    solo_in = {"oggi": 0, "mappa": 0}   # rosa, raro: promozioni in un calcolo e non nell'altro
    BLOCCHI.clear()
    per_variabile = mercati // variabili
    for v in range(variabili):
        _maschere(np.random.default_rng(90_000 + 100 * v + int(volatilita_variabile)), n)
        for k in range(per_variabile):
            df = _prezzi(idx, np.random.default_rng(91_000 + 1_000 * v + k + 500_000 * int(volatilita_variabile)),
                         volatilita_variabile=volatilita_variabile)
            with stg.calcolo_vecchio():      # il calcolo di prima, a richiesta (D5)
                oggi = _misura(df)
            nuovo = _misura(df)                  # l'engine: dal 28/10/2026 il calcolo della mappa
            for chiave, (nn, bb) in nuovo["blocchi"].items():
                c_ = BLOCCHI.setdefault(chiave, [0, 0])
                c_[0] += nn
                c_[1] += bb
            for nome in NOMI:
                if nome[3] == "R":      # senza coppie a meno di H barre l'event study deve coincidere al bit
                    raro_uguale &= bool(oggi["t_es"][nome] == nuovo["t_es"][nome])
                    rapporti_raro.append(nuovo["se_rosa"][nome] / oggi["se_rosa"][nome])
                    a, b = bool(oggi["rosa"].get(nome, False)), bool(nuovo["rosa"].get(nome, False))
                    solo_in["oggi"] += int(a and not b)
                    solo_in["mappa"] += int(b and not a)
            for c, m in (("oggi", oggi), ("mappa", nuovo)):
                for p, t in RIFERIMENTO.items():
                    misurate[c][p] += int(sum(v for k_, v in m["misurate"][p].items() if k_[3] == t))
            if oggi["incertezza_ore"].size == nuovo["incertezza_ore"].size:
                rapporti.extend(nuovo["incertezza_ore"] / oggi["incertezza_ore"])
            for c, m in (("oggi", oggi), ("mappa", nuovo)):
                for nome in NOMI:
                    t = nome[3]
                    for punto in ("rosa", "es"):
                        s = conti[c][punto].setdefault(t, [0, 0])
                        s[0] += int(m[punto].get(nome, False))
                        s[1] += 1
                    s = conti[c]["atlante"].setdefault(t, [0, 0])
                    passa, celle = m["atlante"].get(nome, (0, 0))
                    s[0] += passa
                    s[1] += celle
                conti[c]["profilo"] += int(m["profilo"] > 0)
    for c in conti:
        conti[c]["mercati"] = per_variabile * variabili
    conti["raro_uguale"] = raro_uguale
    conti["misurate"] = misurate
    conti["rapporto_profilo"] = float(np.nanmean(rapporti)) if rapporti else np.nan
    conti["blocchi"] = {k: list(v) for k, v in BLOCCHI.items()}
    rr = np.asarray(rapporti_raro, dtype=float)
    rr = rr[np.isfinite(rr)]
    conti["rapporto_raro"] = (float(rr.mean()), float(rr.min()), float(rr.max())) if rr.size else (np.nan,) * 3
    conti["solo_in"] = solo_in
    return conti


def _blocchi(conti: dict, punto: str, tipo: str | None = None) -> str:
    n = b = 0
    for (p, t), (nn, bb) in conti["blocchi"].items():
        if p == punto and (tipo is None or t == tipo):
            n, b = n + nn, b + bb
    return f"{b} su {n}"


# ========================================================================
# La scomposizione dell'incertezza (Mattia, 28/10/2026)
# ========================================================================
# L'incertezza e' una forma quadratica di u = c * r su tutte le barre. Con
# u = uT + uB (uT: i pesi +1/n sulle barre del trigger; uB: il resto, cioe' la
# media del mercato della stessa ora) si divide esattamente in
#   (1) Q(uT, uT)  parte del trigger
#   (2) Q(uB, uB)  parte del mercato della stessa ora
#   (3) 2 Q(uT, uB) parte incrociata
# I due calcoli cambiano solo il peso delle coppie a meno di H barre: se gli
# ingressi del trigger sono tutti a H barre o piu', la (1) non ha coppie e deve
# coincidere al bit; la differenza sta in (2) e (3).

def _forma(a: np.ndarray, b: np.ndarray, H_: int, sconto: bool) -> float:
    """sum a_t b_t + sum_{0<d<H} w_d (a_{t+d} b_t + b_{t+d} a_t); w_d = 1 - d/H (oggi) o 1 (mappa)."""
    tot = float((a * b).sum())
    for d in range(1, min(int(H_), a.size)):
        w = (1.0 - d / H_) if sconto else 1.0
        tot += w * float((a[d:] * b[:-d]).sum() + (b[d:] * a[:-d]).sum())
    return tot


def _parti(uT: np.ndarray, uB: np.ndarray, se_oggi, se_mappa) -> dict:
    """Le tre parti nei due calcoli; la (1) anche con le funzioni dell'engine (se_oggi, se_mappa su uT)."""
    a, b = se_oggi(uT), se_mappa(uT)[0]
    out = {"uguale_motore": a == b, "diff_motore": abs(a - b) / a if a else 0.0, "blocchi": se_mappa(uT + uB)[1]}
    for c, sconto in (("oggi", True), ("mappa", False)):
        out[c] = (_forma(uT, uT, H, sconto), _forma(uB, uB, H, sconto), 2.0 * _forma(uT, uB, H, sconto))
    out["totale"] = {"oggi": se_oggi(uT + uB) ** 2, "mappa": se_mappa(uT + uB)[0] ** 2}
    return out


def scomponi(df: pd.DataFrame) -> dict:
    """Rosa del raro (TL_R0) e atlante del raro denso (TL_D0): le parti dell'incertezza, cella per cella."""
    presi = []
    pesato, somme = stg.errore_standard_pesato, at._somme_per_cella

    def cattura_rosa(u, H_):            # chiamata (via _errore_lab) da scarto_orario: c, r, pos, n_t sono li'
        f = sys._getframe(1)
        while f is not None and f.f_code.co_name != "scarto_orario":
            f = f.f_back
        if f is not None and not presi:
            L = f.f_locals
            uT = np.zeros(u.size)
            uT[L["pos"]] = L["r"][L["pos"]] / L["n_t"]
            presi.append((uT, np.nan_to_num(L["c"] * L["r"]) - uT))
        return pesato(u, H_)

    stg.errore_standard_pesato = cattura_rosa
    try:
        ro.rosa_entry(df, H, PIP, nomi=["TL_R0"], fuso="UTC", unita="bp")
    finally:
        stg.errore_standard_pesato = pesato
    uT, uB = presi[0]
    rosa = _parti(uT, uB, lambda x: pesato(x, H), lambda x: mp.errore_sovrapposti(x, H, SETTIMANA))

    celle = []

    def cattura_atlante(u, cella, n_celle, H_):   # chiamata da atlante.misura: pm, cm, n_t, r sono li'
        L = sys._getframe(1).f_locals
        uT = np.zeros(u.size)
        uT[L["pm"]] = L["r"][L["pm"]] / L["n_t"][L["cm"]]
        for j in np.unique(L["cm"]):
            dentro = cella == j
            uTj, uj = np.where(dentro, uT, 0.0), np.where(dentro, u, 0.0)
            celle.append(_parti(uTj, uj - uTj, lambda x, _c=cella, _j=j: float(np.sqrt(somme(x, _c, n_celle, H_)[_j])),
                                lambda x: mp.errore_sovrapposti(x, H, SETTIMANA)))
        return somme(u, cella, n_celle, H_)

    at._somme_per_cella = cattura_atlante
    try:
        at.atlante(df, H, PIP, nomi=["TL_D0"], fuso="UTC")
    finally:
        at._somme_per_cella = somme
    return {"rosa": rosa, "atlante": celle}


def _riga_parti(nome: str, ps: list) -> dict:
    """Una riga della tabella: le parti sommate (celle dell'atlante), divise per la (1)."""
    riga = {"mercato e punto": nome}
    uno = sum(p["oggi"][0] for p in ps)
    for c in ("oggi", "mappa"):
        tre = [sum(p[c][i] for p in ps) for i in range(3)]
        riga[f"{c} (2)/(1)"], riga[f"{c} (3)/(1)"] = tre[1] / uno, tre[2] / uno
        riga[f"{c} totale/(1)"] = sum(tre) / uno
    riga["(1) uguale al bit"] = (f"{sum(p['oggi'][0] == p['mappa'][0] for p in ps)}/{len(ps)}, motore "
                                 f"{sum(bool(p['uguale_motore']) for p in ps)}/{len(ps)}")
    riga["blocchi"] = sum(bool(p["blocchi"]) for p in ps)
    return riga


# ========================================================================
# Il codice nuovo contro il calcolo collaudato (PR #86)
# ========================================================================

N_D = 20                                # mercati per variante (i primi di ogni giro della PR #86)


def _valori(df: pd.DataFrame) -> dict:
    """Le incertezze, i t e le promozioni dei quattro punti, in un ordine fisso."""
    r = ro.rosa_entry(df, H, PIP, nomi=NOMI, fuso="UTC", unita="bp").sort_values("candidato")
    a = at.atlante(df, H, PIP, nomi=NOMI, fuso="UTC").sort_values(["candidato", "asse", "cella"])
    ev = es.run_event_study(df, entry_names=NOMI, horizon=H, pip=PIP, verbose=False, fuso="UTC")
    e = ev.sintesi.sort_values("candidato")
    p = stg.profilo_orario(df, H, PIP, fuso="UTC")
    return {"rosa_t": r[["t_netto", "t_globale"]].to_numpy(dtype=float),
            "es_incertezza": ev.incertezza[sorted(ev.incertezza.columns)].to_numpy(dtype=float),
            "es_t": e["volte_incertezza"].to_numpy(dtype=float),
            "profilo_incertezza": p["incertezza"].to_numpy(dtype=float),
            "atlante_t": a["t"].to_numpy(dtype=float),
            "scelte": {"rosa": r[["candidata", "nella_rosa"]].to_numpy(dtype=bool),
                       "atlante": a["passa"].to_numpy(dtype=bool),
                       "event study": e["oltre_rumore"].to_numpy(dtype=bool),
                       "profilo": p["bh"].to_numpy(dtype=bool)}}


def confronto_collaudo(per_variante: int) -> dict:
    """Su `per_variante` mercati per variante: il calcolo collaudato (le formule di prima con le quattro
    funzioni sostituite, come nella PR #86) e il codice nuovo dell'engine."""
    idx = _indice("2022-01-03", giorni=800, minuti=15)
    bit = dict.fromkeys(("es_incertezza", "es_t", "rosa_t", "profilo_incertezza"), True)
    scelte = dict.fromkeys(("rosa", "atlante", "event study", "profilo"), True)
    diff, nan_uguali, uguali, celle = 0.0, True, 0, 0
    for vv in (False, True):
        for v in range(2):
            _maschere(np.random.default_rng(90_000 + 100 * v + int(vv)), len(idx))
            for k in range(per_variante // 2):
                df = _prezzi(idx, np.random.default_rng(91_000 + 1_000 * v + k + 500_000 * int(vv)),
                             volatilita_variabile=vv)
                with stg.calcolo_vecchio(), calcolo_mappa():
                    c = _valori(df)
                n_ = _valori(df)
                for chiave in bit:
                    bit[chiave] &= bool(c[chiave].shape == n_[chiave].shape
                                        and np.array_equal(c[chiave], n_[chiave], equal_nan=True))
                for chiave in scelte:
                    scelte[chiave] &= bool(np.array_equal(c["scelte"][chiave], n_["scelte"][chiave]))
                a, b = c["atlante_t"], n_["atlante_t"]
                nan_uguali &= bool(a.shape == b.shape and np.array_equal(np.isnan(a), np.isnan(b)))
                ok = np.isfinite(a) & np.isfinite(b)
                if ok.any():
                    diff = max(diff, float(np.max(np.abs(a[ok] - b[ok]) / np.abs(a[ok]))))
                    uguali += int((a[ok] == b[ok]).sum())
                    celle += int(ok.sum())
    return {"bit": bit, "scelte": scelte, "diff_atlante": diff, "nan_uguali": nan_uguali,
            "atlante_bit": (uguali, celle)}


def _quota(x) -> float:
    return x[0] / x[1] if x[1] else np.nan


def tabella(conti: dict) -> pd.DataFrame:
    righe = []
    for c in ("oggi", "mappa"):
        riga = {"calcolo": c}
        for punto in ("rosa", "atlante", "es"):
            for t, _ in TIPI:
                riga[f"{punto} {t}"] = _quota(conti[c][punto].get(t, [0, 0]))
        riga["profilo (mercati con un'ora colorata)"] = conti[c]["profilo"] / conti[c]["mercati"]
        righe.append(riga)
    return pd.DataFrame(righe).set_index("calcolo")


def esegui(argv) -> int:
    ESITI: list[bool] = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        print(f"  [{'OK  ' if condizione else 'FAIL'}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    mercati = int(argv[argv.index("--mercati") + 1]) if "--mercati" in argv else 100
    variabili = 10 if mercati >= 1000 else 2
    imposta_rollover(None)                   # mercato 24/7: nessuna quarantena, come gli exchange
    _registra()

    print("\nA · IL CALCOLO DELLA MAPPA DENTRO IL TEST\n" + "-" * 70)
    res = np.array([1.0, -1.0] * 20)
    pos_lontane = np.arange(40) * 100
    pos_vicine = np.arange(40) * 40                    # vicini a 40 barre (< H), su piu' settimane
    tot_coppie = 40 * 40 / 39 - 2 * 39                 # i prodotti fra vicini sono tutti -1: varianza negativa
    check("A1. event study senza sconto: con ingressi a più di H barre coincide con il calcolo di oggi; con "
          "ingressi vicini e prodotti negativi la varianza va ai blocchi di una settimana",
          _es_senza_sconto(res, pos_lontane, H) == es._errore_standard_sovrapposti_vecchio(res, pos_lontane, H)
          and tot_coppie < 0 and np.isfinite(_es_senza_sconto(res, pos_vicine, H))
          and _es_senza_sconto(res, pos_vicine, H) > 0)
    prima = (stg.errore_standard_pesato, es._errore_standard_sovrapposti, ro._errore_standard_sovrapposti,
             at._somme_per_cella)
    with calcolo_mappa():
        dentro = (es._errore_standard_sovrapposti is _es_senza_sconto and ro._errore_standard_sovrapposti is
                  _es_senza_sconto and at._somme_per_cella is _somme_senza_sconto
                  and stg.errore_standard_pesato is not prima[0])
    dopo = (stg.errore_standard_pesato, es._errore_standard_sovrapposti, ro._errore_standard_sovrapposti,
            at._somme_per_cella)
    check("A2. dentro il blocco le quattro funzioni sono sostituite; dopo tornano quelle dell'engine",
          dentro and all(a is b for a, b in zip(prima, dopo)))
    fuori = not stg.usa_calcolo_vecchio()
    dentro = errore = False
    try:
        with stg.calcolo_vecchio():
            dentro = stg.usa_calcolo_vecchio()
            raise RuntimeError("errore di prova dentro il blocco")
    except RuntimeError:
        errore = True
    check("A3. calcolo_vecchio(): dentro il blocco il calcolo di prima; all'uscita, anche con un errore dentro, "
          "torna sempre il calcolo nuovo", fuori and dentro and errore and not stg.usa_calcolo_vecchio())

    print("\nC · LE PARTI DELL'INCERTEZZA: ROSA CON IL RARO, ATLANTE CON IL RARO DENSO, 3 MERCATI\n" + "-" * 70)
    idx = _indice("2022-01-03", giorni=800, minuti=15)
    righe, rose, celle = [], [], []
    for nome, vv, k in (("costante 1", False, 0), ("variabile 1", True, 0), ("variabile 2", True, 1)):
        _maschere(np.random.default_rng(90_000 + int(vv)), len(idx))
        df = _prezzi(idx, np.random.default_rng(91_000 + k + 500_000 * int(vv)), volatilita_variabile=vv)
        with stg.calcolo_vecchio():        # le formule di prima, dove la PR #86 le ha scomposte
            sc = scomponi(df)
        righe += [_riga_parti(f"{nome} · rosa", [sc["rosa"]]),
                  _riga_parti(f"{nome} · atlante ({len(sc['atlante'])} celle)", sc["atlante"])]
        rose.append(sc["rosa"])
        celle += sc["atlante"]
    tutte = rose + celle
    with pd.option_context("display.width", 220, "display.max_columns", 20):
        print(pd.DataFrame(righe).set_index("mercato e punto").round(4).to_string())
    check("C1a. con la stessa formula la parte del trigger (1) coincide al bit nei due calcoli, in ogni misura",
          all(p["oggi"][0] == p["mappa"][0] for p in tutte), f"{len(tutte)} misure")
    # nell'atlante il motore (numba) somma i quadrati in fila, mappa.errore_sovrapposti (numpy) a coppie: stesso
    # conto, arrotondamento diverso. Differenza massima vista il 28/10/2026: 7,6e-16 in relativo (5 ulp)
    diff = max(p["diff_motore"] for p in celle)
    check("C1b. con le funzioni dell'engine la (1) coincide al bit nella rosa e, nell'atlante, entro 1e-12 in "
          "relativo (la differenza viene dall'ordine delle somme: in fila contro a coppie)",
          all(p["uguale_motore"] for p in rose) and diff <= 1e-12,
          f"atlante: uguali al bit {sum(bool(p['uguale_motore']) for p in celle)}/{len(celle)}, "
          f"differenza massima {diff:.1e}")
    check("C2. le tre parti sommate danno l'incertezza di ciascun calcolo (a meno degli arrotondamenti), senza "
          "blocchi di una settimana",
          all(not p["blocchi"] and abs(sum(p[c]) - p["totale"][c]) <= 1e-9 * abs(p["totale"][c])
              for p in tutte for c in ("oggi", "mappa")))

    for vv, nome in ((False, "volatilità costante"), (True, "volatilità variabile")):
        print(f"\nB · SENZA EFFETTO, {nome.upper()}, {mercati} MERCATI\n" + "-" * 70)
        t0 = time.time()
        conti = giro(mercati, vv, variabili)
        tab = tabella(conti)
        with pd.option_context("display.width", 200, "display.max_columns", 20):
            print((tab * 100).round(1).to_string())
        print(f"  ({time.time() - t0:.0f} s)")
        mis = conti["misurate"]
        print("  situazioni misurate dei riferimenti (somma sui mercati): "
              + ", ".join(f"{p} ({t}) oggi {mis['oggi'][p]}, mappa {mis['mappa'][p]}" for p, t in RIFERIMENTO.items()))
        vuoti = [f"{p} ({c})" for c in ("oggi", "mappa") for p in RIFERIMENTO if mis[c][p] == 0]
        if vuoti:
            raise RuntimeError("Un riferimento non misura niente: zero situazioni misurate in " + ", ".join(vuoti)
                               + ". Il confronto con il riferimento sarebbe vuoto: test fermato.")
        print(f"  profilo: incertezza della mappa / incertezza di oggi, in media sulle ore: "
              f"{conti['rapporto_profilo']:.3f}")
        print("  righe con la stima a blocchi di una settimana (colonna incertezza_blocchi dell'engine), calcolo "
              "nuovo: " + ", ".join(f"{p} {_blocchi(conti, p)}" for p in ("rosa", "atlante", "profilo", "es")))
        # solo da scrivere, non sono criteri (Mattia, 28/10/2026)
        print(f"  raro denso: promozioni per caso nella rosa oggi {tab.loc['oggi', 'rosa D']:.1%}, mappa "
              f"{tab.loc['mappa', 'rosa D']:.1%}; nell'event study oggi {tab.loc['oggi', 'es D']:.1%}, mappa "
              f"{tab.loc['mappa', 'es D']:.1%}; riserva dei blocchi nella rosa {_blocchi(conti, 'rosa', 'D')}, "
              f"nell'event study {_blocchi(conti, 'es', 'D')}")
        rm, rmin, rmax = conti["rapporto_raro"]
        print(f"  raro nella rosa: incertezza della mappa / incertezza di oggi media {rm:.3f}, minimo {rmin:.3f}, "
              f"massimo {rmax:.3f}; promozioni solo con il calcolo di oggi {conti['solo_in']['oggi']}, solo con "
              f"quello della mappa {conti['solo_in']['mappa']}")
        lettera = "c" if not vv else "v"
        check(f"B{lettera}1. il trigger raro (ingressi a 200 barre o più) ha la stessa solidità dell'event study nei "
              "due calcoli", conti["raro_uguale"])
        m = tab.loc["mappa"]
        dentro = all(m[f"{p} {t}"] <= m[f"{p} {RIFERIMENTO[p]}"] + MARGINE and m[f"{p} {t}"] < LIMITE
                     for p in RIFERIMENTO for t in ("F", "M"))
        check(f"B{lettera}2. calcolo della mappa: trigger frequenti e medi entro 3 punti dal riferimento (raro; "
              "raro denso nell'atlante) e sotto il 20%, in rosa, atlante ed event study (D4)", dentro,
              ", ".join(f"{p} F {m[f'{p} F']:.1%} M {m[f'{p} M']:.1%} {RIFERIMENTO[p]} "
                        f"{m[f'{p} {RIFERIMENTO[p]}']:.1%}" for p in RIFERIMENTO))
        prof = m["profilo (mercati con un'ora colorata)"]
        check(f"B{lettera}3. calcolo della mappa: il profilo colora almeno un'ora per caso in non più del 20% dei "
              "mercati (q)", prof <= LIMITE, f"{prof:.1%}")

    print(f"\nD · IL CODICE NUOVO CONTRO IL CALCOLO COLLAUDATO NELLA PR #86, {2 * N_D} MERCATI\n" + "-" * 70)
    t0 = time.time()
    d = confronto_collaudo(N_D)
    print(f"  ({time.time() - t0:.0f} s) atlante: differenza relativa massima {d['diff_atlante']:.1e}, "
          f"t uguali al bit {d['atlante_bit'][0]}/{d['atlante_bit'][1]}")
    check("D1. event study (incertezza a ogni barra e solidità), rosa (t_netto e t_globale) e profilo "
          "(incertezza): identici al bit al calcolo collaudato",
          all(d["bit"].values()), ", ".join(f"{k} {'sì' if v else 'NO'}" for k, v in d["bit"].items()))
    # l'atlante: il motore numba somma in fila, il collaudo (mappa.errore_sovrapposti) a coppie con numpy
    check("D2. atlante: t entro 1e-12 in relativo dal calcolo collaudato (la differenza viene dall'ordine "
          "delle somme: in fila contro a coppie), stesse celle misurate",
          d["nan_uguali"] and d["diff_atlante"] <= 1e-12, f"differenza massima {d['diff_atlante']:.1e}")
    check("D3. le stesse promozioni del calcolo collaudato: candidata e nella rosa, celle che passano, «Supera "
          "il rumore», ore colorate", all(d["scelte"].values()),
          ", ".join(f"{k} {'sì' if v else 'NO'}" for k, v in d["scelte"].items()))

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui(sys.argv[1:]))
