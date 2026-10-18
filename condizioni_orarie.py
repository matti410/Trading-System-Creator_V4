"""
Condizioni ORARIE: entry e uscite legate all'ora del giorno (19/10/2026,
decisioni di Mattia del 19/10/2026).

Come entry_composita.py, sono condizioni che si registrano su richiesta, con
il nome che dice cosa fanno. Per il resto del framework sono condizioni come
le altre (event study, ricerca delle uscite, filtri, out-of-sample).

LA REGOLA DEGLI ORARI (vale per tutto)
--------------------------------------
L'ora scritta e' l'ora in cui il trade SI APRE (o si chiude). Il segnale
scatta sulla candela prima e il motore apre o chiude all'Open della candela
successiva: e' lo stesso significato delle fasce del profilo orario
(engine/stagionalita.py). L'ora e' quella locale della piazza del symbol
(engine/stagionalita.fuso_profilo: New York, Francoforte per DE40), con
l'ora legale gestita da pandas. Su ogni timeframe l'ora deve essere l'inizio
di una candela: altrimenti si ferma con errore e dice gli orari possibili.

LE CONDIZIONI
-------------
    ORA_LONG_@HH:MM    entry long: apre il trade ogni giorno alle HH:MM
    ORA_SHORT_@HH:MM   entry short: apre il trade ogni giorno alle HH:MM
    X_ORA_@HH:MM       coppia di uscite: chiude il trade (long o short) alle HH:MM
    X_INVERSIONE_TREND coppia di uscite: chiude il long quando si entra in
                       un'ora che il profilo orario segna colorata CONTRO
                       (scarto negativo oltre la quota dei colpi di fortuna),
                       e lo short quando si entra in un'ora colorata a favore
                       del long. Solo le fasce colorate (decisione di Mattia).
                       Il profilo si calcola sull'IN-SAMPLE e si CONGELA:
                       sull'out-of-sample si usa quello, mai ricalcolato.

Le uscite a regola chiudono PRIMA del tetto a tempo, che resta sempre attivo.

Senza lookahead: entry e X_ORA usano solo l'ora d'inizio della candela del
segnale; X_INVERSIONE_TREND anche il profilo congelato, che non cambia con i
dati su cui si valuta.

ATTENZIONE AI TEST MULTIPLI (docs/50 §10)
-----------------------------------------
Ogni orario provato e' una prova in piu'. Un orario preso da un paper conta
come una prova; uno preso fra le fasce colorate del profilo ha gia' pagato il
conto delle fasce (il controllo le conta tutte), ma va preso UNO per gruppo
di fasce vicine. X_INVERSIONE_TREND conta una prova per ogni sistema su cui
la provi.

Come si usa (notebook di ricerca):

    import condizioni_orarie as co
    co.imposta_fuso(fuso_profilo(symbol))
    co.registra_inversione_trend(df_is, H, pip_symbol(symbol))
    co.registra_uscita_oraria("X_ORA_@16:00")
    LONG_condition_scelta = risolvi_scelta("ORA_LONG_@12:30", lato="long")

`risolvi_scelta` (entry_composita.py) registra da sola i nomi ORA_LONG_@ e
ORA_SHORT_@ che trova.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from engine.stagionalita import (FUSO_PREDEFINITO, codice_orario, fasce_orarie,
                                 profilo_orario, segnale_prima_di)

_ENTRY = re.compile(r"^ORA_(LONG|SHORT)_@(\d{2}:\d{2})$")
_USCITA = re.compile(r"^X_ORA_@(\d{2}:\d{2})$")
INVERSIONE = "X_INVERSIONE_TREND"

# il fuso di lavoro (lo imposta il notebook, o prepara() nel Lab)
_FUSO = {"corrente": FUSO_PREDEFINITO}
# nome -> fuso con cui e' stato registrato (la funzione lo legge a ogni chiamata)
_DEF: dict[str, str] = {}
# il profilo congelato di X_INVERSIONE_TREND
_CONGELATO: dict = {}


def imposta_fuso(fuso: str) -> str:
    """Il fuso delle condizioni orarie registrate da qui in poi (e di quelle gia' registrate)."""
    _FUSO["corrente"] = str(fuso)
    for nome in _DEF:
        _DEF[nome] = _FUSO["corrente"]
    return _FUSO["corrente"]


def fuso_corrente() -> str:
    return _FUSO["corrente"]


def e_oraria(nome) -> bool:
    """Vero se `nome` e' una entry oraria (ORA_LONG_@HH:MM / ORA_SHORT_@HH:MM)."""
    return isinstance(nome, str) and bool(_ENTRY.match(nome.strip()))


def _orario_valido(orario: str) -> str:
    ore, minuti = orario.split(":")
    if not (0 <= int(ore) < 24 and 0 <= int(minuti) < 60):
        raise ValueError(f"Orario '{orario}' non valido: le ore vanno da 00 a 23, i minuti da 00 a 59.")
    return orario


# ========================================================================
# Entry a orario
# ========================================================================

def registra_entry_oraria(nome: str) -> str:
    """
    Registra l'entry `ORA_LONG_@HH:MM` o `ORA_SHORT_@HH:MM` (se non c'e' gia')
    e ne restituisce il nome. Vera sulla candela che precede quella delle
    HH:MM: il trade si apre alle HH:MM, una volta al giorno.
    """
    from engine.registry import list_entries, register_entry
    m = _ENTRY.match(str(nome).strip())
    if not m:
        raise ValueError(f"'{nome}' non e' un'entry oraria: scrivila come ORA_LONG_@HH:MM "
                         f"o ORA_SHORT_@HH:MM, es. ORA_LONG_@12:30.")
    nome = m.group(0)
    orario = _orario_valido(m.group(2))
    _DEF[nome] = _FUSO["corrente"]
    if nome in list_entries():
        return nome

    def entry_oraria(df: pd.DataFrame, _n=nome, _o=orario) -> pd.Series:
        return segnale_prima_di(df, _o, _DEF[_n])

    register_entry(nome, 1 if m.group(1) == "LONG" else -1)(entry_oraria)
    return nome


def registra_se_oraria(nomi) -> list[str]:
    """Registra le entry orarie fra `nomi` (un nome o una lista); le altre le lascia stare."""
    nomi = [nomi] if isinstance(nomi, str) else list(nomi or [])
    return [registra_entry_oraria(n) for n in nomi if e_oraria(n)]


# ========================================================================
# Uscita a orario fisso
# ========================================================================

def registra_uscita_oraria(nome_o_orario: str) -> str:
    """
    Registra la coppia di uscite `X_ORA_@HH:MM` (accetta anche solo "HH:MM")
    e ne restituisce l'etichetta, da passare come exit_rule_pairs /
    regola_uscita. Chiude il trade, long o short, alle HH:MM.
    """
    from engine.registry import list_exits, register_exit
    testo = str(nome_o_orario).strip()
    if re.match(r"^\d{2}:\d{2}$", testo):
        testo = f"X_ORA_@{testo}"
    m = _USCITA.match(testo)
    if not m:
        raise ValueError(f"'{nome_o_orario}' non e' un'uscita oraria: scrivila come X_ORA_@HH:MM, "
                         f"es. X_ORA_@16:00.")
    coppia = m.group(0)
    orario = _orario_valido(m.group(1))
    _DEF[coppia] = _FUSO["corrente"]
    for lato, d in (("LONG", 1), ("SHORT", -1)):
        nome = f"{coppia}_{lato}"
        if nome in list_exits():
            continue

        def uscita_oraria(df: pd.DataFrame, _c=coppia, _o=orario) -> pd.Series:
            return segnale_prima_di(df, _o, _DEF[_c])

        register_exit(nome, direction=d, pair=coppia)(uscita_oraria)
    return coppia


# ========================================================================
# Uscita sull'inversione del profilo orario
# ========================================================================

def registra_inversione_trend(df_is: pd.DataFrame, H: int, pip: float, quarantena=True) -> str:
    """
    Calcola il profilo orario sull'IN-SAMPLE (H barre, fuso corrente), lo
    CONGELA e registra la coppia X_INVERSIONE_TREND. Si puo' richiamare: il
    profilo congelato viene sostituito (con un avviso se cambia).

        long   chiude quando la prossima candela apre una fascia colorata
               contro il long (scarto < 0 e oltre la quota dei colpi di
               fortuna) e la candela attuale no: «si entra in un'ora contro»
        short  lo stesso con le fasce colorate a favore del long

    Restituisce l'etichetta della coppia.
    """
    from engine.registry import list_exits, register_exit
    fuso = _FUSO["corrente"]
    prof = profilo_orario(df_is, H, pip, fuso=fuso, quarantena=quarantena)
    colorate = prof[prof["bh"]] if len(prof) else prof
    contro_long = {codice_orario(f, df_is.index, fuso)[0] for f in colorate.loc[colorate["scarto_pips"] < 0, "fascia"]}
    contro_short = {codice_orario(f, df_is.index, fuso)[0] for f in colorate.loc[colorate["scarto_pips"] > 0, "fascia"]}
    nuovo = dict(fuso=fuso, H=int(H), contro_long=contro_long, contro_short=contro_short, profilo=prof)
    vecchio = _CONGELATO.get("profilo")
    if vecchio is not None and (_CONGELATO["contro_long"], _CONGELATO["contro_short"], _CONGELATO["fuso"]) != \
            (contro_long, contro_short, fuso):
        print(f"[registra_inversione_trend] profilo congelato sostituito (H = {int(H)}, ora di {fuso}).")
    _CONGELATO.update(nuovo)

    for lato, d, chiave in (("LONG", 1, "contro_long"), ("SHORT", -1, "contro_short")):
        nome = f"{INVERSIONE}_{lato}"
        if nome in list_exits():
            continue

        def uscita_inversione(df: pd.DataFrame, _k=chiave) -> pd.Series:
            codici, larghezza = fasce_orarie(df.index, _CONGELATO["fuso"])
            n = max(1, -(-1440 // larghezza))
            contro = np.array(sorted(_CONGELATO[_k]), dtype=np.int64)
            ora_attuale = np.isin(codici, contro)
            prossima = np.isin((codici + 1) % n, contro)
            return pd.Series(prossima & ~ora_attuale, index=df.index)

        register_exit(nome, direction=d, pair=INVERSIONE)(uscita_inversione)
    return INVERSIONE


def profilo_congelato() -> pd.DataFrame | None:
    """Il profilo orario congelato da registra_inversione_trend (None se non c'e')."""
    return _CONGELATO.get("profilo")


def fasce_contro() -> dict:
    """Le fasce (ora di apertura) che chiudono il long e lo short in X_INVERSIONE_TREND."""
    p = _CONGELATO.get("profilo")
    if p is None:
        return {"long": [], "short": []}
    col = p[p["bh"]]
    return {"long": list(col.loc[col["scarto_pips"] < 0, "fascia"]),
            "short": list(col.loc[col["scarto_pips"] > 0, "fascia"])}
