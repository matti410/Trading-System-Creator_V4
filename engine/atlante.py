"""
L'atlante del trigger (22/10/2026, lavoro C, docs/63 §6 e docs/66).

A COSA SERVE
------------
La rosa (engine/rosa.py) misura ogni trigger su tutto l'in-sample. Un trigger
piatto in media puo' funzionare in una parte del mercato e perdere in
un'altra. L'atlante guarda DOVE: per ogni entry vera e ogni cella del
mercato, lo scarto del trigger dal mercato della stessa cella e se paga i
costi. E' una mappa, non un cancello: la cella scelta (al massimo una per
lato) si misura poi al passo 5 come un filtro, con la soglia di rumore a
k = celle misurate qui (strada B, docs/63 §10.1 punto 1).

LE CELLE (docs/66 §2), per lato, assi NON incrociati fra loro
-------------------------------------------------------------
    vol_trend  4 celle: volatilita' alta/bassa x trend a favore/contro
               (indicatori.cella_vol_trend, la griglia di confidenza.py)
    sessione   4 celle: ASIA_NOTTE (e fine settimana), EUROPA, LONDRA_NY,
               AMERICA, sulla barra d'ingresso (indicatori.sessione_ingresso)
    basis      2 celle, solo perpetual con lo spot: basis alta/bassa
               (indicatori.basis_alta)
Ogni stato della barra del segnale usa solo dati fino al suo Close.

LA MISURA (docs/66 §3), stessa convenzione della rosa
-----------------------------------------------------
Segnale sulla barra i, ingresso a Open[i+1], misura a Close[i+H], quarantena
applicata. Per ogni entry e cella:
  1. lo scarto LORDO dal mercato della stessa cella e della stessa fascia
     oraria (stagionalita.scarto_orario con i codici «fascia x cella»), con
     t, p a una coda, Benjamini-Hochberg su tutte le celle misurate e le due
     meta' dell'in-sample;
  2. il guadagno NETTO del trigger nella cella: rendimento a H barre meno
     commissione (andata e ritorno), spread e, sui perpetual, funding
     (exchange.funding_avanti), convertiti come per i trade.
Una cella PASSA con almeno min_eventi eventi, t > 0, BH, due meta' e netto > 0.
Le celle sotto min_eventi non si misurano e non entrano in k.

VELOCITA' (docs/66 §7)
----------------------
Il riferimento della cella non dipende dall'entry: si calcola una volta per
asse, lato e unita'. L'incertezza di tutte le celle di un asse si calcola in
un passaggio solo (numba), perche' le celle di un asse si dividono le barre:
due barre contano insieme solo se sono nella stessa cella. Stessi numeri di
scarto_orario (test_atlante.py), a meno dell'ordine delle somme.

Modulo ADDITIVO: non modifica nessun file esistente dell'engine.
"""
from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd

from . import registry as _reg
from .indicatori import (SESSIONI_ATLANTE, basis_alta, cella_vol_trend, sessione_ingresso)
from .quarantena_trade import maschera_segnali_puliti
from .rosa import MIN_EVENTI, Q_ROSA, _entry_vere, benjamini_hochberg
from .stagionalita import FUSO_PREDEFINITO, UNITA, fasce_orarie, in_unita

try:
    from numba import njit
except Exception:          # senza numba: lo stesso conto in Python, piu' lento
    def njit(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda f: f

CELLE = {
    "vol_trend": ("VOL_BASSA_TREND_CONTRO", "VOL_BASSA_TREND_FAVORE",
                  "VOL_ALTA_TREND_CONTRO", "VOL_ALTA_TREND_FAVORE"),
    "sessione": SESSIONI_ATLANTE,
    "basis": ("BASIS_BASSA", "BASIS_ALTA"),
}
ASSI = ("vol_trend", "sessione", "basis")
# come si mostra il nome di una cella (decisione di Mattia del 22/10/2026, docs/66 §13)
ETICHETTE = {"ASIA_NOTTE": "ASIA_NOTTE (e fine settimana)"}
PREFISSO_FILTRI = "CELLA_"

_NORMALE = NormalDist()


def etichetta_cella(cella: str) -> str:
    return ETICHETTE.get(cella, cella)


def asse_di(cella: str) -> str:
    """L'asse a cui appartiene una cella; errore se la cella non esiste."""
    for asse, nomi in CELLE.items():
        if cella in nomi:
            return asse
    tutte = [c for nomi in CELLE.values() for c in nomi]
    raise ValueError(f"Cella {cella!r} sconosciuta. Celle possibili: {', '.join(tutte)}.")


def ha_basis(df: pd.DataFrame) -> bool:
    """True se df ha lo spot agganciato (colonna spot_close con almeno un valore)."""
    return "spot_close" in df.columns and bool(np.isfinite(df["spot_close"].to_numpy(dtype=float)).any())


def assi_disponibili(df: pd.DataFrame) -> tuple:
    """vol_trend e sessione sempre; basis solo con lo spot agganciato (perpetual)."""
    return ASSI if ha_basis(df) else ASSI[:2]


def _stato(df: pd.DataFrame, asse: str, direzione: int) -> pd.Series:
    if asse == "vol_trend":
        return cella_vol_trend(df, direzione)
    if asse == "sessione":
        return sessione_ingresso(df)
    if asse == "basis":
        return basis_alta(df)
    raise ValueError(f"Asse {asse!r} sconosciuto: usa uno di {ASSI}.")


def celle_atlante(df: pd.DataFrame, direzione: int, assi=None) -> pd.DataFrame:
    """
    I codici di cella di ogni barra per il lato `direzione`, una colonna per
    asse (0..celle-1, nell'ordine di CELLE). NaN dove lo stato non e' ancora
    calcolabile (inizio dello storico, spot mancante).
    """
    if direzione not in (1, -1):
        raise ValueError("direzione deve essere 1 (long) o -1 (short).")
    assi = assi_disponibili(df) if assi is None else tuple(assi)
    return pd.DataFrame({a: _stato(df, a, direzione).to_numpy(dtype=float) for a in assi}, index=df.index)


# ========================================================================
# L'incertezza di tutte le celle di un asse in un passaggio
# ========================================================================

@njit(cache=True)
def _somme_per_cella(u, cella, n_celle, H):
    """
    Per ogni cella j: somma_t u_t^2 + 2 somma_{t<s<t+H, stessa cella} (1-(s-t)/H) u_t u_s.
    E' errore_standard_pesato (stagionalita.py) al quadrato, una cella alla
    volta: u e' zero fuori dalle barre usate, e le celle si dividono le barre.
    """
    tot = np.zeros(n_celle)
    n = u.size
    for t in range(n):
        ut = u[t]
        ct = cella[t]
        if ct < 0 or ut == 0.0:
            continue
        acc = ut * ut
        fine = min(n, t + H)
        for s in range(t + 1, fine):
            if cella[s] == ct:
                acc += 2.0 * (1.0 - (s - t) / H) * ut * u[s]
        tot[ct] += acc
    return tot


def _media_per_codice(valori, codici, usa, n_cod):
    v = np.where(usa, valori, 0.0)
    somma = np.bincount(codici, weights=v, minlength=n_cod)
    conta = np.bincount(codici, weights=usa.astype(float), minlength=n_cod)
    with np.errstate(invalid="ignore", divide="ignore"):
        media = np.where(conta > 0, somma / conta, np.nan)
    return media, conta


def _p_una_coda(t: float) -> float:
    return 1.0 - _NORMALE.cdf(t) if np.isfinite(t) else np.nan


def _motivo(r) -> str:
    if not r["misurata"]:
        return "troppo pochi casi"
    if not (np.isfinite(r["t"]) and r["t"] > 0):
        return "non fa meglio del mercato della cella"
    if not r["bh"]:
        return "non supera la quota di falsi positivi"
    if not r["due_meta"]:
        return "non positiva in una metà"
    if not r["netto"] > 0:
        return "non paga i costi"
    return ""


# ========================================================================
# L'atlante
# ========================================================================

def atlante(df_is: pd.DataFrame, H: int, pip: float, costi: dict | None = None, funding=None,
            nomi=None, assi=None, unita: str = "bp", min_eventi: int = MIN_EVENTI,
            q: float = Q_ROSA, fuso: str = FUSO_PREDEFINITO, quarantena=True,
            mostra=None, atr=None) -> pd.DataFrame:
    """
    L'atlante sull'IN-SAMPLE, a orizzonte H: una riga per entry x cella.

    df_is      l'in-sample con gli indicatori (sui perpetual con lo spot
               agganciato: vetrina.aggancia_spot)
    H          l'orizzonte gia' scelto
    pip        il pip fisso del symbol (engine/simboli.py)
    costi      i costi di vetrina.costi_storico: commission (per lato, frazione)
               e spread (frazione del prezzo); None = netto senza costi
    funding    lo storico del funding (perpetual); None = non contato
    nomi       le entry; None = le entry vere (rosa._entry_vere)
    assi       None = assi_disponibili(df_is)
    unita      l'unita' che DECIDE: "bp" sui symbol da exchange, "pips" sul broker
    min_eventi sotto questa soglia una cella non si misura e non conta in k
    q          livello del controllo della quota di falsi positivi
    fuso       il fuso delle fasce orarie (stagionalita.fuso_profilo)
    mostra     le entry per cui calcolare anche le altre unita' (pips, ATR),
               solo da mostrare (decisione di Mattia del 22/10/2026): colonne
               scarto_<u>, t_<u>, netto_<u>; None = nessuna
    atr        indicatori.atr_giornaliero_chiuso (serve solo per l'ATR in `mostra`)

    Colonne: candidato, direction, asse, cella, eventi, misurata,
    scarto_<unita>, t, p, bh, due_meta, netto_<unita>, passa, motivo.
    In .attrs: k_misurate (le celle misurate, il k del passo 5), H, q,
    unita, assi, min_eventi, fuso, scartate (entry sotto min_eventi in tutto).
    """
    if unita not in UNITA:
        raise ValueError(f"unita deve essere una di {UNITA}.")
    H = int(H)
    if H < 1:
        raise ValueError("H deve essere almeno 1 barra.")
    if pip is None or not float(pip) > 0:
        raise ValueError("pip obbligatorio: il pip fisso del symbol (engine/simboli.py).")
    pip = float(pip)
    assi = assi_disponibili(df_is) if assi is None else tuple(assi)
    for a in assi:
        if a not in ASSI:
            raise ValueError(f"Asse {a!r} sconosciuto: usa uno di {ASSI}.")
    nomi = _entry_vere() if nomi is None else list(nomi)
    mostra = set(mostra or [])
    costi = costi or {}
    commissione = float(costi.get("commission") or 0.0)
    spread = float(costi.get("spread") or 0.0)

    n = len(df_is)
    close = df_is["Close"].to_numpy(dtype=float)
    ingresso = np.full(n, np.nan)
    ingresso[: n - 1] = df_is["Open"].to_numpy(dtype=float)[1:]
    uscita = np.full(n, np.nan)
    fwd = np.full(n, np.nan)                      # rendimento long a H barre, in pips
    if n > H:
        uscita[: n - H] = close[H:]
        fwd[: n - H] = (close[H:] - ingresso[: n - H]) / pip
    valido = np.isfinite(fwd) & np.isfinite(ingresso) & (ingresso > 0)
    pulito = maschera_segnali_puliti(df_is, quarantena)
    prima = np.arange(n) < n // 2
    fascia = fasce_orarie(df_is.index, fuso)[0].astype(np.int64)
    n_fasce = int(fascia.max()) + 1 if n else 1
    # i costi in pips di un evento: commissione sui due lati, spread all'ingresso (come i trade)
    with np.errstate(invalid="ignore"):
        costo_pips = (commissione * (ingresso + uscita) + spread * ingresso) / pip
    if funding is not None:
        from .exchange import funding_avanti
        fondo = np.nan_to_num(funding_avanti(df_is, H, funding, pip))     # + = un long paga
    else:
        fondo = np.zeros(n)
    atr_is = None
    if mostra and "atr" in UNITA and unita != "atr":
        from .rosa import _atr_su
        atr_is = _atr_su(df_is, atr)

    def in_u(valori_pips, u):
        return in_unita(valori_pips, u, pip, prezzo=ingresso, atr=atr_is)

    stati = {}

    def stato(asse, d):
        chiave = (asse, d if asse == "vol_trend" else 0)
        if chiave not in stati:
            c = _stato(df_is, asse, d).to_numpy(dtype=float)
            stati[chiave] = np.where(np.isfinite(c), c, -1).astype(np.int64)
        return stati[chiave]

    rif = {}

    def riferimento(asse, d, u):
        """Il mercato della cella e della fascia, nell'unita' u: una volta per asse, lato e unita'."""
        chiave = (asse, d if asse == "vol_trend" else 0, u)
        if chiave not in rif:
            f = in_u(fwd, u)
            cella = stato(asse, d)
            m = len(CELLE[asse])
            usa = valido & pulito & np.isfinite(f) & (cella >= 0)
            codici = np.where(cella >= 0, fascia * m + cella, 0)
            n_cod = n_fasce * m
            b, barre = _media_per_codice(f, codici, usa, n_cod)
            b_a, _ = _media_per_codice(f, codici, usa & prima, n_cod)
            b_b, _ = _media_per_codice(f, codici, usa & ~prima, n_cod)
            rif[chiave] = dict(f=f, cella=np.where(usa, cella, -1), m=m, usa=usa, codici=codici,
                               n_cod=n_cod, b=b, b_a=b_a, b_b=b_b, barre=barre,
                               r=np.where(usa, f - b[codici], 0.0))
        return rif[chiave]

    def misura(R, pos, d, netto_u):
        """Scarto, t, due meta' e netto di ogni cella di un asse, in un passaggio."""
        m, f, codici = R["m"], R["f"], R["codici"]
        pos = pos[R["usa"][pos]]
        cp = R["cella"][pos]
        conta = np.bincount(cp, minlength=m)
        out = []
        misurate = conta >= max(int(min_eventi), 2)
        x = d * (f[pos] - R["b"][codici[pos]])
        somma = np.bincount(cp, weights=x, minlength=m)
        with np.errstate(invalid="ignore", divide="ignore"):
            scarto = np.where(conta > 0, somma / conta, np.nan)
        se = np.full(m, np.nan)
        if misurate.any():
            dentro = misurate[cp]
            pm, cm = pos[dentro], cp[dentro]
            n_t = conta.astype(float)
            trig = np.bincount(codici[pm], minlength=R["n_cod"]).astype(float)
            with np.errstate(invalid="ignore", divide="ignore"):
                quota = np.where(R["barre"] > 0, trig / R["barre"], 0.0)
            cella_barra = R["cella"]
            ok = (cella_barra >= 0)
            ok[ok] = misurate[cella_barra[ok]]
            c = np.zeros(n)
            c[ok] = -quota[codici[ok]] / n_t[cella_barra[ok]]
            c[pm] += 1.0 / n_t[cm]
            r = R["r"].copy()
            r[pm] -= d * scarto[cm]
            u = np.where(ok, c * r, 0.0)
            tot = _somme_per_cella(u, np.where(ok, cella_barra, -1), m, H)
            se = np.where(misurate, np.sqrt(np.maximum(tot, 0.0)), np.nan)
        # le due meta': lo scarto dal mercato della cella di ciascuna meta'
        a = prima[pos]
        xa = d * (f[pos] - R["b_a"][codici[pos]])
        xb = d * (f[pos] - R["b_b"][codici[pos]])
        na = np.bincount(cp[a], minlength=m)
        nb = np.bincount(cp[~a], minlength=m)
        with np.errstate(invalid="ignore", divide="ignore"):
            sa = np.bincount(cp[a], weights=xa[a], minlength=m) / na
            sb = np.bincount(cp[~a], weights=xb[~a], minlength=m) / nb
            netto = np.bincount(cp, weights=netto_u[pos], minlength=m) / conta
        for j in range(m):
            t = scarto[j] / se[j] if (misurate[j] and np.isfinite(se[j]) and se[j] > 0) else np.nan
            out.append(dict(eventi=int(conta[j]), misurata=bool(misurate[j]),
                            scarto=float(scarto[j]) if misurate[j] else np.nan, t=float(t),
                            due_meta=bool(misurate[j] and na[j] > 0 and nb[j] > 0 and sa[j] > 0 and sb[j] > 0),
                            netto=float(netto[j]) if misurate[j] else np.nan))
        return out

    altre = [u for u in UNITA if u != unita]
    righe, scartate = [], []
    for nome in nomi:
        d = int(_reg.get_entry_direction(nome))
        maschera = _reg.get_entry(nome)(df_is).fillna(False).to_numpy(dtype=bool) & valido & pulito
        pos = np.flatnonzero(maschera)
        if pos.size < max(int(min_eventi), 2):
            scartate.append((nome, int(pos.size)))
            continue
        netto_pips = d * fwd - costo_pips - d * fondo
        netto = {unita: in_u(netto_pips, unita)}
        unita_riga = [unita] + (altre if nome in mostra else [])
        for u in unita_riga[1:]:
            netto[u] = in_u(netto_pips, u)
        for asse in assi:
            misure = {u: misura(riferimento(asse, d, u), pos[np.isfinite(netto[u][pos])], d, netto[u])
                      for u in unita_riga}
            for j, cella in enumerate(CELLE[asse]):
                mm = misure[unita][j]
                riga = {"candidato": nome, "direction": d, "asse": asse, "cella": cella,
                        "eventi": mm["eventi"], "misurata": mm["misurata"],
                        f"scarto_{unita}": mm["scarto"], "t": mm["t"], "p": _p_una_coda(mm["t"]),
                        "due_meta": mm["due_meta"], f"netto_{unita}": mm["netto"], "netto": mm["netto"]}
                for u in unita_riga[1:]:
                    x = misure[u][j]
                    riga.update({f"scarto_{u}": x["scarto"], f"t_{u}": x["t"], f"netto_{u}": x["netto"]})
                righe.append(riga)

    colonne = ["candidato", "direction", "asse", "cella", "eventi", "misurata", f"scarto_{unita}",
               "t", "p", "bh", "due_meta", f"netto_{unita}", "passa", "motivo"]
    if mostra:
        for u in altre:
            colonne += [f"scarto_{u}", f"t_{u}", f"netto_{u}"]
    info = dict(H=H, q=q, unita=unita, assi=assi, min_eventi=int(min_eventi), fuso=fuso,
                scartate=scartate)
    if not righe:
        vuota = pd.DataFrame(columns=colonne)
        vuota.attrs.update(k_misurate=0, **info)
        return vuota
    t = pd.DataFrame(righe)
    for c in colonne:
        if c not in t.columns:
            t[c] = np.nan
    misurate = t["misurata"].to_numpy(dtype=bool)
    bh = np.zeros(len(t), dtype=bool)
    bh[misurate] = benjamini_hochberg(t.loc[misurate, "p"].to_numpy(), q)
    t["bh"] = bh
    t["motivo"] = [_motivo(r) for _, r in t.iterrows()]
    t["passa"] = t["motivo"] == ""
    t = t[colonne]
    t.attrs.update(k_misurate=int(misurate.sum()), **info)
    return t


def celle_che_passano(tab: pd.DataFrame, trigger) -> list[str]:
    """Le celle che passano per almeno uno dei trigger indicati."""
    if isinstance(trigger, str):
        trigger = [trigger]
    r = tab[tab["candidato"].isin(list(trigger)) & tab["passa"]]
    return list(dict.fromkeys(r["cella"]))


# ========================================================================
# Le celle scelte come filtri del passo 5 (strada B, docs/66 §5)
# ========================================================================

_DATI_FILTRI: dict = {}


def nome_filtro_cella(cella_long: str | None, cella_short: str | None) -> str:
    """
    Il nome della riga del passo 5 (quello da scrivere nella scheda):
    CELLA_<C> con la stessa cella sui due lati, CELLA_<CL>_L / CELLA_<CS>_S
    con un lato solo, CELLA_<CL>_L_<CS>_S con due celle diverse.
    """
    if cella_long and cella_short:
        if cella_long == cella_short:
            return f"{PREFISSO_FILTRI}{cella_long}"
        return f"{PREFISSO_FILTRI}{cella_long}_L_{cella_short}_S"
    if cella_long:
        return f"{PREFISSO_FILTRI}{cella_long}_L"
    if cella_short:
        return f"{PREFISSO_FILTRI}{cella_short}_S"
    raise ValueError("Serve almeno una cella, long o short.")


def _funzione_filtro(nome: str):
    def filtro(d: pd.DataFrame) -> pd.Series:
        valori, codice = _DATI_FILTRI[nome]
        if not d.index.isin(valori.index).all():
            raise ValueError(f"{nome}: il df passato contiene barre per cui la cella non e' stata "
                             "calcolata. Registra le celle sullo storico completo.")
        return (valori.reindex(d.index) == codice).fillna(False).astype(bool)
    return filtro


def registra_filtri_cella(df_storico: pd.DataFrame, cella_long: str | None = None,
                          cella_short: str | None = None) -> list[str]:
    """
    Registra le celle scelte come filtri del passo 5, su richiesta (non nel
    dizionario FILTRI): il membro +1 al long, il -1 allo short, con un `pair`
    comune se i lati sono due (una riga sola nella ricerca dei filtri). Gli
    stati si calcolano sullo storico COMPLETO (in-sample e out-of-sample,
    senza lookahead: indicatori.py), il filtro e' vero dove la barra del
    segnale e' nella cella. Toglie dal registro i filtri CELLA_ di prima.

    Ritorna i nomi da passare a `filtri=`; la riga del passo 5 si chiama
    nome_filtro_cella(cella_long, cella_short).
    """
    if not cella_long and not cella_short:
        raise ValueError("Serve almeno una cella, long o short.")
    _reg.remove_filters(PREFISSO_FILTRI)
    _DATI_FILTRI.clear()
    coppia = nome_filtro_cella(cella_long, cella_short) if (cella_long and cella_short) else None
    nomi = []
    for cella, direzione, suffisso in ((cella_long, 1, "_L"), (cella_short, -1, "_S")):
        if not cella:
            continue
        asse = asse_di(cella)
        if asse == "basis" and not ha_basis(df_storico):
            raise ValueError(f"La cella {cella} serve la basis: lo storico non ha lo spot agganciato.")
        nome = f"{PREFISSO_FILTRI}{cella}{suffisso}"
        _DATI_FILTRI[nome] = (_stato(df_storico, asse, direzione), float(CELLE[asse].index(cella)))
        _reg.register_filter(nome, direction=direzione, pair=coppia)(_funzione_filtro(nome))
        nomi.append(nome)
    return nomi
