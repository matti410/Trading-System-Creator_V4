"""
La rosa dei candidati (18/10/2026, decisioni di Mattia del 17/10/2026).

A COSA SERVE
------------
Dopo l'event study, e dopo la ricerca delle uscite, il catalogo propone
decine di candidati. La rosa ne SUGGERISCE un gruppo: quelli con un
andamento positivo che difficilmente e' solo fortuna, e diversi fra loro
(un'idea per famiglia, profitti giornalieri poco correlati). La scelta resta
dell'utente: la rosa non approva niente, e la validazione che viene dopo
(filtri, due meta', out-of-sample una volta sola) non cambia.

DUE CANCELLI PER DUE COMPITI (docs/02)
--------------------------------------
La soglia di rumore della validazione (Sidak) controlla la probabilita' che
fra tutte le prove anche UNA sola sia un colpo di fortuna: e' giusto che sia
severa, ma per proporre candidati lascia passare troppo poco. Qui si usa il
controllo della QUOTA di falsi positivi (Benjamini-Hochberg): in media, nella
rosa, al massimo q dei candidati e' un colpo di fortuna (q = 20%). Prova di
potenza del 17/10/2026, EURUSD, H = 25, 1.000 eventi: con 3 pips di vantaggio
vero a trade la validazione ne trova il 46%, la rosa l'89%, con meno di una
entry finta per giro su 75.

COME SI COSTRUISCE
------------------
1. Per ogni candidato il t NETTO: lo scarto dalla linea del mercato diviso la
   sua incertezza. Per le entry a orizzonte H, con l'incertezza dell'event
   study che tiene conto dei trigger vicini; per i sistemi sui pips netti dei
   trade veri, togliendo a ogni trade la deriva del mercato nelle barre in cui
   e' rimasto aperto. Su un asset che sale da solo (BTCUSD, indici) una long
   «positiva» spesso misura solo la salita: lo scarto la toglie.
2. Benjamini-Hochberg al livello q sul p a UNA coda (solo andamenti positivi).
3. Lo scarto dal mercato deve essere positivo su ENTRAMBE le meta'
   dell'in-sample.
4. Il gruppo: dal t piu' alto in giu', un candidato entra se e' di una
   famiglia non ancora presente (engine/famiglie.py, soglia 60%) e se ha
   |rho| <= rho_max (0,3) con tutti quelli gia' presi, sui profitti
   giornalieri (giornata FX). Per le entry i profitti sono quelli della sola
   entry a H barre (misurato il 17/10/2026: stessa mappa delle correlazioni
   dei trade interi, accordo 0,99, 60 volte piu' veloce); per i sistemi
   quelli dei trade veri. Per le entry le famiglie si misurano solo fra le
   candidate (punti 1-3 superati): un trigger bocciato non entra nel calcolo
   (18/11/2026, decisione di Mattia).

Si passa SOLO l'in-sample. L'orizzonte H e' quello scelto prima (passo 1 del
notebook di ricerca, passo 2 del Lab): la rosa non sceglie orizzonti.

LA BASELINE ORARIA (18/10/2026, decisione di Mattia)
----------------------------------------------------
Con baseline="oraria" (il predefinito) la linea del mercato di ogni trigger
e' la media della SUA fascia oraria (engine/stagionalita.py), non quella di
tutte le barre: un trigger che scatta sempre alla stessa ora non viene
premiato, o punito, per l'ora. Per i sistemi si toglie a ogni trade la
deriva tipica delle fasce orarie in cui e' rimasto aperto. L'incertezza
include il rumore della media di fascia. Il confronto con la media di tutte
le barre resta visibile (scarto_globale_pips, t_globale); baseline="globale"
ridà esattamente i numeri di prima.
"""
from __future__ import annotations

import itertools
import os
from statistics import NormalDist

import numpy as np
import pandas as pd

from . import registry as _reg
from .event_study import _errore_standard_sovrapposti
from .famiglie import SOGLIA_FAMIGLIA, barre_vere, famiglie
from .giudizio import t_stat
from .livelli import giorno_fx
from .metriche import atr_alla_entrata, pips_per_trade
from .quarantena_trade import maschera_segnali_puliti
from .stagionalita import (FUSO_PREDEFINITO, UNITA, barre_settimana, deriva_per_barra_oraria, fasce_orarie,
                           in_unita, media_per_fascia, scarto_orario, scarto_orario_medio)

Q_ROSA = 0.20
RHO_MAX = 0.30
MIN_EVENTI = 200

_NORMALE = NormalDist()


# ========================================================================
# Pezzi comuni
# ========================================================================

def benjamini_hochberg(p, q: float = Q_ROSA) -> np.ndarray:
    """
    Vero per le prove che passano il controllo della quota di falsi positivi
    al livello q (procedura «step-up» di Benjamini-Hochberg): ordinati i p dal
    piu' piccolo, si trova il rango r piu' alto con p_(r) <= q * r / k e
    passano i primi r. I p non finiti contano nelle k prove ma non passano.
    """
    p = np.asarray(p, dtype=float)
    k = p.size
    passa = np.zeros(k, dtype=bool)
    if k == 0:
        return passa
    pp = np.where(np.isfinite(p), p, np.inf)
    ordine = np.argsort(pp, kind="stable")
    ok = pp[ordine] <= q * np.arange(1, k + 1) / k
    if ok.any():
        passa[ordine[: int(np.flatnonzero(ok).max()) + 1]] = True
    return passa


def _p_una_coda(t: float) -> float:
    return 1.0 - _NORMALE.cdf(t) if np.isfinite(t) else np.nan


def _motivo(r) -> str:
    """Il primo controllo che un non candidato non supera."""
    if not np.isfinite(r["t_netto"]):
        return "non misurabile (troppo pochi casi)"
    if r["t_netto"] <= 0:
        return "non fa meglio del mercato"
    if not r["bh"]:
        return "non supera la quota di falsi positivi"
    return "non positiva in una delle due metà"


def _gruppo(tabella: pd.DataFrame, serie: dict, rho_max: float, per_lato: bool = False) -> pd.DataFrame:
    """
    Il gruppo suggerito, dal t piu' alto in giu' fra i `candidata`: entra chi
    e' di una famiglia nuova e ha |rho| <= rho_max con tutti i gia' presi.
    Aggiunge le colonne nella_rosa, rho_max (il |rho| piu' alto con gli altri
    membri della rosa) e perche (il motivo, per chi resta fuori).

    per_lato (25/10/2026, decisione di Mattia): la correlazione si controlla, e
    rho_max si misura, solo con i membri dello STESSO lato (colonna
    `direction`). Un long e uno short legati in negativo non sono doppioni: il
    mercato li muove in versi opposti, e la loro convivenza si misura alla
    rosa dei sistemi, sui trade veri. Il controllo della famiglia non cambia.
    False (default, la rosa dei sistemi) = tutti i membri, come prima.
    """
    t = tabella.copy()
    t["nella_rosa"] = False
    t["rho_max"] = np.nan
    t["perche"] = ""
    giorni = sorted(set().union(*[set(v.index) for v in serie.values()])) if serie else []
    giorni = pd.Index(giorni)
    allineate = {k: v.reindex(giorni, fill_value=0.0) for k, v in serie.items()}

    def rho(a, b):
        x, y = allineate[a].to_numpy(), allineate[b].to_numpy()
        if x.std() == 0 or y.std() == 0:
            return 0.0
        return float(np.corrcoef(x, y)[0, 1])

    lato = (dict(zip(t["candidato"], t["direction"])) if per_lato and "direction" in t.columns else {})

    def confrontabili(nome, presi):
        # per_lato: solo i membri dello stesso lato; altrimenti tutti (come prima)
        return [p for p in presi if p != nome and (not lato or lato.get(p) == lato.get(nome))]

    presi, famiglie_prese = [], {}
    for i in t.sort_values("t_netto", ascending=False).index:
        r = t.loc[i]
        if not r["candidata"]:
            t.loc[i, "perche"] = _motivo(r)
            continue
        nome = r["candidato"]
        if r["famiglia"] in famiglie_prese:
            t.loc[i, "perche"] = f"famiglia già nella rosa ({famiglie_prese[r['famiglia']]})"
            continue
        rhos = {p: rho(nome, p) for p in confrontabili(nome, presi)}
        troppo = {p: v for p, v in rhos.items() if abs(v) > rho_max}
        if troppo:
            p, v = max(troppo.items(), key=lambda kv: abs(kv[1]))
            t.loc[i, "perche"] = f"correlata con {p} (rho {v:+.2f})"
            continue
        presi.append(nome)
        famiglie_prese[r["famiglia"]] = nome
        t.loc[i, "nella_rosa"] = True
    for i in t.index:
        nome = t.loc[i, "candidato"]
        altri = confrontabili(nome, presi)
        if altri and nome in allineate:
            t.loc[i, "rho_max"] = max(abs(rho(nome, p)) for p in altri)
    return t


def _controlla_baseline(baseline: str) -> str:
    if baseline not in ("oraria", "globale"):
        raise ValueError("baseline deve essere 'oraria' o 'globale'.")
    return baseline


def _controlla_unita(unita: str, unita_extra) -> tuple[str, list[str]]:
    """L'unita' che decide e le altre da mostrare accanto (20/10/2026, docs/63 §4)."""
    if unita not in UNITA:
        raise ValueError(f"unita deve essere una di {UNITA}.")
    if unita_extra is None:                     # le altre due, nell'ordine di UNITA
        unita_extra = [u for u in UNITA if u != unita]
    extra = [u for u in unita_extra if u != unita]
    for u in extra:
        if u not in UNITA:
            raise ValueError(f"unita_extra: {u!r} non e' una di {UNITA}.")
    return unita, extra


def _atr_su(df_is: pd.DataFrame, atr) -> np.ndarray:
    """L'ATR giornaliero a 5 giornate chiuse allineato a df_is (None = calcolato su df_is)."""
    if atr is None:
        from .indicatori import atr_giornaliero_chiuso
        atr = atr_giornaliero_chiuso(df_is)
    return pd.Series(atr).reindex(df_is.index).to_numpy(dtype=float)


def _ordina(t: pd.DataFrame) -> pd.DataFrame:
    return (t.sort_values(["nella_rosa", "candidata", "t_netto"], ascending=False)
            .reset_index(drop=True))


# ========================================================================
# Rosa delle entry (dopo l'event study)
# ========================================================================

def rosa_entry(df_is: pd.DataFrame, H: int, pip: float, nomi=None,
               q: float = Q_ROSA, soglia_famiglia: float = SOGLIA_FAMIGLIA,
               rho_max: float = RHO_MAX, min_eventi: int = MIN_EVENTI,
               quarantena=True, baseline: str = "oraria",
               fuso: str = FUSO_PREDEFINITO, unita: str = "pips",
               unita_extra=None, atr=None, processi=1) -> pd.DataFrame:
    """
    La rosa delle entry sull'in-sample, a orizzonte H. Stessa convenzione
    dell'event study: trigger sulla barra i, ingresso a Open[i+1], misura a
    Close[i+H], ogni occorrenza contata, quarantena applicata.

    df_is        l'IN-SAMPLE con gli indicatori (split_is_oos)
    H            l'orizzonte gia' scelto (non si sceglie qui)
    pip          il pip fisso del symbol (engine/simboli.py, pip_symbol)
    nomi         le entry da considerare; None = tutte le registrate tranne
                 le metro e le composite in OR
    min_eventi   sotto questa soglia l'entry non si misura (come MIN_TRADES
                 dell'event study)
    baseline     "oraria" (predefinito): il mercato e' la media della fascia
                 oraria di ogni trigger; "globale": la media di tutte le barre
    fuso         il fuso delle fasce (engine/stagionalita.fuso_profilo(symbol))
    unita        l'unita' che DECIDE (20/10/2026, docs/63 §4): "pips" (come
                 prima), "bp" (punti base del prezzo d'ingresso) o "atr"
                 (multipli dell'ATR giornaliero noto al segnale)
    unita_extra  le unita' misurate accanto, solo da mostrare: colonne
                 scarto_<u>, t_<u>, due_meta_<u>; None = le altre due
    atr          la serie di indicatori.atr_giornaliero_chiuso (meglio sullo
                 storico intero); None = calcolata su df_is
    processi     18/11/2026: i processi della misura (1 = questo processo, None = PROCESSI); stessi
                 numeri. La misura e' quella di rosa_orizzonti_entry, a un orizzonte solo.

    Con unita="pips" i numeri delle colonne di prima sono identici.

    Una riga per entry misurata:
        candidato, direction, eventi
        scarto_<unita> media a H barre meno il mercato nello stesso verso
        t_netto, p     t dello scarto e p a una coda
        bh             passa il controllo della quota di falsi positivi a q
        due_meta       scarto positivo su entrambe le meta' dell'in-sample
        candidata      t > 0, bh e due_meta
        famiglia       numero della famiglia (engine/famiglie.py), solo per le candidate;
                       vuota (<NA>) per le altre (18/11/2026)
        nella_rosa     nel gruppo suggerito
        rho_max        |rho| piu' alto con gli altri membri della rosa dello stesso lato (25/10/2026)
        perche         perche' e' fuori dalla rosa: il primo controllo non superato,
                       oppure la famiglia o la correlazione con un membro
        scarto_globale_<unita>, t_globale
                       (solo con baseline oraria) lo stesso confronto con la media
                       di tutte le barre, per vedere quanto conta l'ora
        incertezza_blocchi  28/10/2026: True se la varianza del t che decide e' uscita
                       zero o negativa e si e' usata la stima a blocchi di una settimana
    In .attrs: k (entry misurate), q, rho_max, H, scartate (sotto min_eventi),
    baseline, fuso, unita.
    """
    return rosa_orizzonti_entry(df_is, [H], pip, nomi=nomi, q=q, soglia_famiglia=soglia_famiglia, rho_max=rho_max,
                                min_eventi=min_eventi, quarantena=quarantena, baseline=baseline, fuso=fuso,
                                unita=unita, unita_extra=unita_extra, atr=atr, processi=processi)[0][int(H)]


# ------------------------------------------------------------------------
# La misura dei trigger, a uno o piu' orizzonti e in uno o piu' processi (18/11/2026, decisioni di Mattia)
# ------------------------------------------------------------------------
# - Ogni trigger si calcola una volta e si misura a tutti gli orizzonti chiesti.
# - I trigger generati long e short della stessa ricetta, livello e verso hanno la stessa serie
#   (engine/generatore/trigger.py): segnale e misura si fanno una volta per coppia e lo short e' l'opposto esatto
#   del long (scarto, t e due meta' col segno cambiato, stessa incertezza, serie giornaliera negata). Nel BH contano
#   tutti e due. I trigger del catalogo si misurano uno per uno, come prima.
# - Con piu' processi ognuno misura i suoi gruppi di trigger (una ricetta generata, o qualche trigger del catalogo)
#   sugli stessi dati: i numeri sono quelli di un processo solo, al bit.
# - Il conto dell'event study (run_event_study) senza l'event study: per ogni trigger le occasioni con la sua
#   maschera (segnale & ingresso valido & quarantena) e la prima barra k in cui almeno un'occasione ha il prezzo;
#   e' misurato a H se le occasioni sono almeno il minimo e quella barra e' <= H (misurati_event_study).

PROCESSI = 4     # 18/11/2026: i processi della misura (memoria massima sotto 4 GB su M5 con «tutti», docs/83)


def _base(df_is: pd.DataFrame, quarantena, oraria: bool, fuso: str, atr_is) -> dict:
    """I dati comuni a tutti gli orizzonti, solo array (si passano ai processi)."""
    n = len(df_is)
    close = df_is["Close"].to_numpy(dtype=float)
    open_ = df_is["Open"].to_numpy(dtype=float)
    ingresso = np.full(n, np.nan)
    ingresso[: n - 1] = open_[1:]
    meta = n // 2
    return dict(n=n, close=close, ingresso=ingresso, pulito=maschera_segnali_puliti(df_is, quarantena),
                meta=meta, prima=np.arange(n) < meta, giorno=np.asarray(giorno_fx(df_is)),
                codici=fasce_orarie(df_is.index, fuso)[0] if oraria else None,
                settimana=barre_settimana(df_is.index), atr=atr_is)


def _contesto(B: dict, H: int, pip: float, unita: str, extra, oraria: bool) -> dict:
    """Rendimenti a H barre, barre utili e mercato in ogni unita' (stesse formule di prima)."""
    n, close, ingresso = B["n"], B["close"], B["ingresso"]
    fwd = np.full(n, np.nan)                      # rendimento long a H barre, in pips
    if n > H:
        fwd[: n - H] = (close[H:] - ingresso[: n - H]) / pip
    valido = np.isfinite(fwd) & np.isfinite(ingresso) & (ingresso > 0)
    meta, prima, codici = B["meta"], B["prima"], B["codici"]

    def mercato_in(u: str) -> dict:
        f = in_unita(fwd, u, pip, prezzo=ingresso, atr=B["atr"])
        usa = valido & B["pulito"] & np.isfinite(f)
        M = dict(fwd=f, mercato=float(np.nanmean(f)),
                 mercato_meta=(float(np.nanmean(f[:meta])), float(np.nanmean(f[meta:]))),
                 usa=usa, usa_meta=(usa & prima, usa & ~prima))
        if oraria:
            # le medie di fascia e le barre per fascia sono le stesse per tutti i trigger: una volta sola
            n_cod = int(codici.max()) + 1
            M.update(media=media_per_fascia(f, codici, usa),
                     media_meta=tuple(media_per_fascia(f, codici, x) for x in M["usa_meta"]),
                     barre_fascia=np.bincount(codici, weights=usa.astype(float), minlength=n_cod))
            M["resto"] = np.where(usa, f - M["media"], 0.0)
            M["codici_usa"] = np.where(usa, codici, n_cod)
        return M

    return dict(H=H, valido=valido, uscita=np.minimum(np.arange(n) + H, n - 1),
                mercati={u: mercato_in(u) for u in (unita, *extra)})


def _misura_unita(B: dict, C: dict, M: dict, pos: np.ndarray, d: int, oraria: bool) -> dict:
    """Scarto, t e due meta' di un trigger nell'unita' di M, nel verso d (stesse formule di prima)."""
    H, prima, settimana, codici = C["H"], B["prima"], B["settimana"], B["codici"]
    f = M["fwd"]
    pos = pos[np.isfinite(f[pos])]          # in ATR: niente valore nelle prime giornate
    if pos.size < 2:
        return dict(scarto=np.nan, t=np.nan, globale=np.nan, t_globale=np.nan, v=None, pos=pos, blocchi=False,
                    meta_ok=False, meta=(np.nan, np.nan))
    v = d * f[pos]
    se, blocchi = _errore_standard_sovrapposti(v, pos, H, settimana, con_blocchi=True)
    scarto = float(v.mean()) - d * M["mercato"]
    t = scarto / se if (np.isfinite(se) and se > 0) else np.nan
    a, b = prima[pos], ~prima[pos]
    out = dict(globale=scarto, t_globale=t, v=v, pos=pos, meta_ok=bool(a.any() and b.any()))
    if oraria:
        scarto, se_o, blocchi = scarto_orario(f, codici, M["usa"], pos, d, H, settimana, con_blocchi=True,
                                              media=M["media"], barre_fascia=M["barre_fascia"], resto=M["resto"],
                                              codici_usa=M["codici_usa"])
        t = scarto / se_o if (np.isfinite(se_o) and se_o > 0) else np.nan
        # le due meta' guardano solo il segno dello scarto (senza l'incertezza, che non serve)
        meta = ((scarto_orario_medio(f, M["media_meta"][0], pos[a], d),
                 scarto_orario_medio(f, M["media_meta"][1], pos[b], d)) if out["meta_ok"] else (np.nan, np.nan))
    else:
        meta = ((v[a].mean() - d * M["mercato_meta"][0], v[b].mean() - d * M["mercato_meta"][1])
                if out["meta_ok"] else (np.nan, np.nan))
    out.update(scarto=scarto, t=t, meta=meta, blocchi=blocchi)
    return out


def _due_meta(x: dict) -> bool:
    return bool(x["meta_ok"] and x["meta"][0] > 0 and x["meta"][1] > 0)


def _misura_trigger(B: dict, C: dict, m: np.ndarray, d: int, P: dict) -> dict:
    """La misura di un trigger a un orizzonte: {"scartata": eventi} sotto il minimo, altrimenti il risultato."""
    pos = np.flatnonzero(m & C["valido"] & B["pulito"])
    if pos.size < max(int(P["min_eventi"]), 2):
        return {"scartata": int(pos.size)}
    per_u = {u: _misura_unita(B, C, C["mercati"][u], pos, d, P["oraria"]) for u in (P["unita"], *P["extra"])}
    r = per_u[P["unita"]]
    serie = (pd.Series(r["v"], index=B["giorno"][C["uscita"][r["pos"]]]).groupby(level=0).sum()
             if r["v"] is not None else None)
    chiavi = ("scarto", "t", "globale", "t_globale", "blocchi", "meta_ok", "meta")
    return {"eventi": int(pos.size), "u": {u: {k: x[k] for k in chiavi} for u, x in per_u.items()}, "serie": serie}


def _opposto(res: dict) -> dict:
    """Lo stesso trigger misurato nel verso opposto: scarto, t e due meta' col segno cambiato, stessa incertezza."""
    if "scartata" in res:
        return res
    u = {k: dict(x, scarto=-x["scarto"], t=-x["t"], globale=-x["globale"], t_globale=-x["t_globale"],
                 meta=(-x["meta"][0], -x["meta"][1])) for k, x in res["u"].items()}
    return {"eventi": res["eventi"], "u": u, "serie": -res["serie"] if res["serie"] is not None else None}


def _conto_es(B: dict, m_es: np.ndarray, k_max: int) -> tuple[int, int]:
    """
    Il conto dell'event study per un trigger: le occasioni con la sua maschera (segnale & ingresso valido &
    quarantena) e la prima barra k (1..k_max) in cui almeno un'occasione ha il rendimento; k_max + 1 se nessuna.
    """
    ing = B["ingresso"]
    pos = np.flatnonzero(m_es & np.isfinite(ing) & (ing > 0) & B["pulito"])
    if pos.size == 0:
        return 0, k_max + 1
    n, close = B["n"], B["close"]
    for k in range(1, k_max + 1):
        p = pos[pos + k < n]
        if p.size and np.isfinite(close[p + k] / ing[p] - 1.0).any():
            return int(pos.size), k
    return int(pos.size), k_max + 1


_PROC: dict = {}


def _avvia_processo(B: dict, df_piccolo: pd.DataFrame, P: dict) -> None:
    """Prepara un processo (anche quello principale): i dati e il contesto di ogni orizzonte."""
    _PROC.clear()
    _PROC.update(B=B, df=df_piccolo, P=P,
                 C={H: _contesto(B, H, P["pip"], P["unita"], P["extra"], P["oraria"]) for H in P["Hs"]})


def _esegui_compito(compito: list) -> dict:
    """Un gruppo di trigger: {nome: {"es": (occasioni, prima barra), H: risultato, ...}}."""
    B, df, P, C = _PROC["B"], _PROC["df"], _PROC["P"], _PROC["C"]
    out = {}
    for sorgente, membri in compito:
        if sorgente[0] == "generato":
            grezzo = sorgente[1](df)
            m = grezzo.fillna(False).to_numpy(dtype=bool)
            m_es = grezzo.to_numpy(dtype=bool)
        else:
            m = np.unpackbits(sorgente[1], count=B["n"]).astype(bool)
            m_es = np.unpackbits(sorgente[2], count=B["n"]).astype(bool)
        es = _conto_es(B, m_es, P["k_max"])
        d0 = membri[0][1]
        misure = {H: _misura_trigger(B, C[H], m, d0, P) for H in P["Hs"]}
        vere = None
        for nome, d in membri:
            out[nome] = {"es": es, **{H: (x if d == d0 else _opposto(x)) for H, x in misure.items()}}
            # i generati che possono diventare candidati (t > 0 e due meta' a qualche H) portano con se' le barre
            # vere per famiglie.py, che cosi' non le ricalcola (stessi numeri)
            if sorgente[0] == "generato" and any(_puo_essere_candidata(out[nome][H], P["unita"]) for H in P["Hs"]):
                if vere is None:
                    vere = np.packbits(barre_vere(grezzo))
                out[nome]["vere"] = vere
    return out


def _puo_essere_candidata(res: dict, unita: str) -> bool:
    if "scartata" in res:
        return False
    r = res["u"][unita]
    return bool(r["t"] > 0 and _due_meta(r))


def _compiti(df_is: pd.DataFrame, nomi: list):
    """
    I gruppi di lavoro, uno alla volta: prima, per ogni ricetta generata, le sue coppie (long e short con la stessa
    serie insieme); poi il catalogo, 8 trigger per gruppo, con i segnali calcolati qui (compressi a 1 bit per barra)
    mentre i processi misurano i generati.
    """
    from .generatore.trigger import TriggerGenerato
    per_ricetta, catalogo = {}, []
    for nome in nomi:
        f = _reg.get_entry(nome)
        d = int(_reg.get_entry_direction(nome))
        if isinstance(f, TriggerGenerato):
            coppie = per_ricetta.setdefault(f.ricetta, {})
            chiave = (f.livello, f.verso)
            if chiave not in coppie:
                coppie[chiave] = (("generato", f), [])
            coppie[chiave][1].append((nome, d))
        else:
            catalogo.append((nome, d, f))
    for coppie in per_ricetta.values():
        yield list(coppie.values())
    gruppo = []
    for nome, d, f in catalogo:
        grezzo = f(df_is)
        sorgente = ("segnale", np.packbits(grezzo.fillna(False).to_numpy(dtype=bool)),
                    np.packbits(grezzo.to_numpy(dtype=bool)))
        gruppo.append((sorgente, [(nome, d)]))
        if len(gruppo) == 8:
            yield gruppo
            gruppo = []
    if gruppo:
        yield gruppo


def _esegui(compiti, B: dict, df_piccolo: pd.DataFrame, P: dict, processi) -> dict:
    """I compiti (uno alla volta, anche da un generatore) in uno o piu' processi; stessi risultati."""
    quanti = 1 if processi == 1 else max(1, min(int(processi or PROCESSI), os.cpu_count() or 1))
    if quanti > 1:
        from concurrent.futures import ProcessPoolExecutor
        from concurrent.futures.process import BrokenProcessPool
        from .filter_search_bt import _contesto_processi
        contesto = _contesto_processi(processi is not None)
        if contesto is not None:
            compiti, presi = iter(compiti), []

            def uno_alla_volta():
                for c in compiti:
                    presi.append(c)
                    yield c
            try:
                with ProcessPoolExecutor(max_workers=quanti, mp_context=contesto, initializer=_avvia_processo,
                                         initargs=(B, df_piccolo, P)) as ex:
                    futuri = [ex.submit(_esegui_compito, c) for c in uno_alla_volta()]   # i processi partono subito
                    out = {}
                    for f in futuri:
                        out.update(f.result())
                    return out
            except (BrokenProcessPool, OSError) as e:
                print(f"rosa: processi non disponibili ({type(e).__name__}), si prosegue in un processo solo.")
                compiti = itertools.chain(presi, compiti)
    _avvia_processo(B, df_piccolo, P)
    try:
        out = {}
        for c in compiti:
            out.update(_esegui_compito(c))
        return out
    finally:
        _PROC.clear()


def rosa_orizzonti_entry(df_is: pd.DataFrame, orizzonti, pip: float, nomi=None,
                         q: float = Q_ROSA, soglia_famiglia: float = SOGLIA_FAMIGLIA,
                         rho_max: float = RHO_MAX, min_eventi: int = MIN_EVENTI,
                         quarantena=True, baseline: str = "oraria",
                         fuso: str = FUSO_PREDEFINITO, unita: str = "pips",
                         unita_extra=None, atr=None, processi=1, conto_fino_a: int | None = None):
    """
    18/11/2026: la rosa delle entry (rosa_entry) a piu' orizzonti, con ogni trigger calcolato una volta, le coppie
    dei generati misurate una volta e `processi` processi (1 = questo processo; None = PROCESSI, se si possono
    avviare). Stessi numeri di rosa_entry a ogni H, al bit.

    Ritorna ({H: rosa}, conto) con conto = {nome: (occasioni, prima barra)}: il conto dell'event study
    (misurati_event_study), con la prima barra cercata fino a max(conto_fino_a, orizzonti).
    """
    oraria = _controlla_baseline(baseline) == "oraria"
    unita, extra = _controlla_unita(unita, unita_extra)
    Hs = [int(H) for H in orizzonti]
    if not Hs or min(Hs) < 1:
        raise ValueError("H deve essere almeno 1 barra.")
    if pip is None or not float(pip) > 0:
        raise ValueError("pip obbligatorio: il pip fisso del symbol (engine/simboli.py).")
    pip = float(pip)
    nomi = _entry_vere() if nomi is None else list(nomi)
    atr_is = _atr_su(df_is, atr) if "atr" in (unita, *extra) else None
    B = _base(df_is, quarantena, oraria, fuso, atr_is)
    P = dict(Hs=Hs, pip=pip, unita=unita, extra=list(extra), oraria=oraria, min_eventi=int(min_eventi),
             k_max=max(Hs + [int(conto_fino_a or 0)]))
    ohlcv = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df_is.columns]
    risultati = _esegui(_compiti(df_is, nomi), B, df_is[ohlcv], P, processi)
    # i segnali delle candidate per famiglie.py, una volta per tutti gli orizzonti (quelli dei generati dai processi)
    memoria = {n: risultati[n]["vere"] for n in nomi if "vere" in risultati[n]}
    rose = {H: _rosa_finale(df_is, nomi, {n: risultati[n][H] for n in nomi}, H, q, soglia_famiglia, rho_max,
                            baseline, fuso, oraria, unita, extra, memoria) for H in Hs}
    return rose, {n: risultati[n]["es"] for n in nomi}


def misurati_event_study(conto: dict, nomi, H: int, min_eventi: int) -> list:
    """
    I trigger che run_event_study(nomi, horizon=H, min_trades=min_eventi) mette nella sintesi, dal conto di
    rosa_orizzonti_entry: almeno min_eventi occasioni (e almeno una) e un'occasione con il rendimento entro H barre.
    """
    return [n for n in nomi if conto[n][0] >= max(int(min_eventi), 1) and conto[n][1] <= int(H)]


def _rosa_finale(df_is, nomi, misure: dict, H: int, q, soglia_famiglia, rho_max, baseline, fuso, oraria, unita,
                 extra, memoria=None) -> pd.DataFrame:
    """Le righe nell'ordine dei nomi, poi BH, famiglie fra le candidate e il gruppo (come prima)."""
    righe, serie, scartate = [], {}, []
    for nome in nomi:
        res = misure[nome]
        if "scartata" in res:
            scartate.append((nome, res["scartata"]))
            continue
        d = int(_reg.get_entry_direction(nome))
        r = res["u"][unita]
        riga = {"candidato": nome, "direction": d, "eventi": res["eventi"]}
        if oraria:
            riga.update({f"scarto_globale_{unita}": r["globale"], "t_globale": r["t_globale"]})
        riga.update({f"scarto_{unita}": r["scarto"], "t_netto": r["t"], "p": _p_una_coda(r["t"]),
                     "due_meta": _due_meta(r)})
        for u in extra:
            x = res["u"][u]
            riga.update({f"scarto_{u}": x["scarto"], f"t_{u}": x["t"], f"due_meta_{u}": _due_meta(x)})
        riga["incertezza_blocchi"] = r["blocchi"]
        righe.append(riga)
        if res["serie"] is not None:
            serie[nome] = res["serie"]

    colonne = ["candidato", "direction", "eventi", f"scarto_{unita}", "t_netto", "p", "bh",
               "due_meta", "candidata", "famiglia", "nella_rosa", "rho_max", "perche"]
    if oraria:
        colonne += [f"scarto_globale_{unita}", "t_globale"]
    for u in extra:
        colonne += [f"scarto_{u}", f"t_{u}", f"due_meta_{u}"]
    colonne += ["incertezza_blocchi"]   # 28/10/2026: la stima a blocchi di una settimana (docs/75 §7)
    info = dict(q=q, rho_max=rho_max, H=H, scartate=scartate,
                baseline=baseline, fuso=fuso if oraria else None, unita=unita)
    if not righe:
        vuota = pd.DataFrame(columns=colonne)
        vuota.attrs.update(k=0, **info)
        return vuota
    t = pd.DataFrame(righe)
    t["bh"] = benjamini_hochberg(t["p"].to_numpy(), q)
    t["candidata"] = (t["t_netto"] > 0) & t["bh"] & t["due_meta"]
    # 18/11/2026 (decisione di Mattia): le famiglie si misurano solo fra le candidate; un trigger bocciato non entra
    # nel calcolo e la sua famiglia resta vuota. Il BH resta unico su tutti i k misurati (sopra).
    candidate = list(t.loc[t["candidata"], "candidato"])
    fam = (famiglie(df_is, "entry", nomi=candidate, soglia=soglia_famiglia, memoria=memoria)
           .set_index("nome")["famiglia"]
           if candidate else pd.Series(dtype=float))
    t["famiglia"] = t["candidato"].map(fam).astype("Int64")
    t = _ordina(_gruppo(t, serie, rho_max, per_lato=True))[colonne]      # 25/10/2026: rho solo sullo stesso lato
    t.attrs.update(k=len(t), **info)
    return t


def _entry_vere() -> list[str]:
    """Le entry del registro senza le metro e senza le composite in OR."""
    esclusi = set()
    try:
        from entry_metro import NOMI_METRO
        esclusi |= set(NOMI_METRO)
    except ImportError:
        pass
    try:
        from entry_composita import elenca_composite
        esclusi |= set(elenca_composite())
    except ImportError:
        pass
    # le entry a orario (ORA_LONG_@HH:MM, 19/10/2026) si registrano solo su richiesta
    from condizioni_orarie import e_oraria
    return [n for n in _reg.list_entries() if n not in esclusi and not e_oraria(n)]


# ========================================================================
# Rosa dei sistemi (dopo la ricerca delle uscite, prima dei filtri)
# ========================================================================

def _famiglia_sistemi(df_is, risultati: pd.DataFrame, soglia: float) -> pd.Series:
    """
    La famiglia di un sistema e' la terna (famiglia dell'entry long, famiglia
    dell'entry short, famiglia della regola di uscita): due sistemi sono la
    stessa idea se coincidono tutte e tre. Lato spento o uscita solo a tempo
    = «—». Restituisce un'etichetta per riga, es. «L2·S5·X1».
    """
    def per_tipo(nomi, tipo):
        nomi = sorted({x for x in nomi if isinstance(x, str)})
        if not nomi:
            return {}
        f = famiglie(df_is, tipo, nomi=nomi, soglia=soglia)
        return f.set_index("nome")["famiglia"].to_dict()

    entrate = per_tipo(list(risultati["entry_long"]) + list(risultati["entry_short"]), "entry")
    coppie = {p: el for p, el, _ in _reg.list_exit_pairs()}
    uscite_l = {p: coppie.get(p) for p in risultati["exit_rule_pair"] if isinstance(p, str)}
    fam_u = per_tipo([x for x in uscite_l.values() if x], "exit")

    def etichetta(r):
        el = entrate.get(r["entry_long"]) if isinstance(r["entry_long"], str) else None
        es = entrate.get(r["entry_short"]) if isinstance(r["entry_short"], str) else None
        p = r["exit_rule_pair"]
        x = fam_u.get(uscite_l.get(p)) if isinstance(p, str) else None
        return "·".join(f"{c}{v if v is not None else '—'}" for c, v in (("L", el), ("S", es), ("X", x)))

    return risultati.apply(etichetta, axis=1)


def rosa_sistemi(es, df_is: pd.DataFrame, pip: float, commission: float = 0.0,
                 q: float = Q_ROSA, soglia_famiglia: float = SOGLIA_FAMIGLIA,
                 rho_max: float = RHO_MAX, min_trades: int | None = None,
                 baseline: str = "oraria", fuso: str = FUSO_PREDEFINITO,
                 unita: str = "pips", unita_extra=None, atr=None) -> pd.DataFrame:
    """
    La rosa dei sistemi completi, sui trade veri di una ricerca delle uscite
    (`run_exit_search_bt` sull'IN-SAMPLE). Ogni combinazione e' un sistema.

    es           il risultato di run_exit_search_bt (sull'in-sample)
    df_is        lo stesso in-sample (serve per la deriva del mercato, le
                 famiglie e le giornate FX)
    pip          il pip fisso del symbol
    commission   come nei costi del backtest (i pips sono NETTI)
    min_trades   sotto questa soglia il sistema non si misura (conta comunque
                 fra le prove, con p = 1); None = quella della ricerca
    baseline     "oraria" (predefinito): la deriva tolta a ogni trade e' quella
                 tipica delle fasce orarie in cui e' rimasto aperto; "globale":
                 la variazione media di una barra, uguale a ogni ora
    fuso         il fuso delle fasce (engine/stagionalita.fuso_profilo(symbol))
    unita, unita_extra, atr
                 come rosa_entry (20/10/2026, docs/63 §4): lo scarto di ogni
                 trade in pips si converte nell'unita' col SUO prezzo
                 d'ingresso (bp) o con l'ATR alla barra del segnale (atr).
                 Con unita="pips" i numeri di prima sono identici.

    Lo scarto di ogni trade e' il suo guadagno netto meno la deriva del
    mercato nel suo verso per le barre in cui e' rimasto aperto (deriva = la
    variazione media di una barra sull'in-sample, in pips). I trade di un
    sistema non si sovrappongono (una posizione alla volta): il t e' quello
    classico. Le due meta' si dividono sulla data d'ingresso.

    Colonne come rosa_entry, con `combinazione` al posto di `candidato`,
    `trades` al posto di `eventi` e `famiglia` nella forma «L2·S5·X1».
    """
    oraria = _controlla_baseline(baseline) == "oraria"
    unita, extra = _controlla_unita(unita, unita_extra)
    if pip is None or not float(pip) > 0:
        raise ValueError("pip obbligatorio: il pip fisso del symbol (engine/simboli.py).")
    pip = float(pip)
    risultati = es.risultati
    atr_is = (pd.Series(_atr_su(df_is, atr), index=df_is.index)
              if "atr" in (unita, *extra) else None)

    def fattore(tr, u: str) -> np.ndarray:
        """Da pips all'unita' u, trade per trade (NaN dove l'ATR non c'e')."""
        if u == "pips":
            return np.ones(len(tr))
        if u == "bp":
            return pip * 10_000.0 / tr["EntryPrice"].to_numpy(dtype=float)
        a = atr_alla_entrata(tr, atr_is).to_numpy(dtype=float)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(a > 0, pip / a, np.nan)
    min_trades = es.min_trades if min_trades is None else int(min_trades)
    open_ = df_is["Open"].to_numpy(dtype=float)
    deriva = float(np.nanmean(np.diff(open_))) / pip       # pips per barra, verso long
    if oraria:
        # deriva cumulata per fascia oraria: D[j] = somma delle derive delle barre < j
        cumulata = np.concatenate([[0.0], np.cumsum(deriva_per_barra_oraria(df_is, pip, fuso))])
    meta = df_is.index[len(df_is) // 2]
    giorno = pd.Series(np.asarray(giorno_fx(df_is)), index=df_is.index)

    def misura(x_glob, x, f, ingresso) -> dict:
        """Scarto, t e due meta' nell'unita' del fattore f (stesse formule di prima)."""
        ok = np.isfinite(f)
        xg, xo, ing = x_glob[ok] * f[ok], x[ok] * f[ok], ingresso[ok]
        if xo.size < 2:
            return dict(globale=np.nan, t_globale=np.nan, scarto=np.nan, t=np.nan, due_meta=False)
        a, b = xo[ing < meta], xo[ing >= meta]
        return dict(globale=float(np.mean(xg)), t_globale=t_stat(xg), scarto=float(np.mean(xo)),
                    t=t_stat(xo), due_meta=bool(a.size and b.size and a.mean() > 0 and b.mean() > 0))

    righe, serie = [], {}
    for _, r in risultati.iterrows():
        comb = r["combinazione"]
        tr = es.trades(comb)
        riga = {"candidato": comb, "trades": int(len(tr)), f"scarto_{unita}": np.nan,
                "t_netto": np.nan, "p": 1.0, "due_meta": False}
        if oraria:
            riga.update({f"scarto_globale_{unita}": np.nan, "t_globale": np.nan})
        for u in extra:
            riga.update({f"scarto_{u}": np.nan, f"t_{u}": np.nan, f"due_meta_{u}": False})
        if len(tr) >= max(min_trades, 2):
            _, netti = pips_per_trade(tr, pip, commission)
            segno = np.where(tr["Size"].to_numpy() > 0, 1, -1)
            barre = (tr["ExitBar"] - tr["EntryBar"]).to_numpy(dtype=float)
            x_glob = netti.to_numpy(dtype=float) - segno * deriva * barre
            x = x_glob
            if oraria:
                ing = tr["EntryBar"].to_numpy(dtype=int)
                usc = tr["ExitBar"].to_numpy(dtype=int)
                x = netti.to_numpy(dtype=float) - segno * (cumulata[usc] - cumulata[ing])
            ingresso = pd.DatetimeIndex(tr["EntryTime"])
            f = fattore(tr, unita)
            m = misura(x_glob, x, f, ingresso)
            if oraria:
                riga.update({f"scarto_globale_{unita}": m["globale"], "t_globale": m["t_globale"]})
            riga.update({f"scarto_{unita}": m["scarto"], "t_netto": m["t"], "p": _p_una_coda(m["t"]),
                         "due_meta": m["due_meta"]})
            for u in extra:
                mu = misura(x_glob, x, fattore(tr, u), ingresso)
                riga.update({f"scarto_{u}": mu["scarto"], f"t_{u}": mu["t"], f"due_meta_{u}": mu["due_meta"]})
            g = giorno.reindex(pd.DatetimeIndex(tr["ExitTime"])).to_numpy()
            ok = np.isfinite(f)
            serie[comb] = pd.Series((netti.to_numpy(dtype=float) * f)[ok], index=g[ok]).groupby(level=0).sum()
        righe.append(riga)

    colonne = ["candidato", "trades", f"scarto_{unita}", "t_netto", "p", "bh", "due_meta",
               "candidata", "famiglia", "nella_rosa", "rho_max", "perche"]
    if oraria:
        colonne += [f"scarto_globale_{unita}", "t_globale"]
    for u in extra:
        colonne += [f"scarto_{u}", f"t_{u}", f"due_meta_{u}"]
    info = dict(q=q, rho_max=rho_max, baseline=baseline, fuso=fuso if oraria else None, unita=unita)
    if not righe:
        vuota = pd.DataFrame(columns=colonne)
        vuota.attrs.update(k=0, **info)
        return vuota.rename(columns={"candidato": "combinazione"})
    t = pd.DataFrame(righe)
    t["p"] = t["p"].fillna(1.0)
    t["bh"] = benjamini_hochberg(t["p"].to_numpy(), q)
    t["candidata"] = (t["t_netto"] > 0) & t["bh"] & t["due_meta"]
    t["famiglia"] = _famiglia_sistemi(df_is, risultati, soglia_famiglia).to_numpy()
    t = _ordina(_gruppo(t, serie, rho_max))[colonne]
    t.attrs.update(k=len(t), **info)
    return t.rename(columns={"candidato": "combinazione"})
