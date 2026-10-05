"""
Entry composite: PIU' ENTRY IN «OR», registrate come una entry sola.

A cosa serve
------------
Il motore usa UNA entry per lato. Per far lavorare insieme piu' condizioni
d'ingresso («entro long se scatta A oppure B oppure C») si registra una entry
composita: per il resto del framework e' una entry come le altre
(`run_event_study`, `run_exit_search_bt`, `run_filter_search_bt`, collaudo).

Come si usa (dal notebook, dopo aver registrato le entry di base) — il modo
semplice, `risolvi_scelta`: una condizione singola OPPURE una lista, e il lato
dichiarato in modo esplicito:

    from entry_composita import risolvi_scelta

    LONG_condition_scelta  = risolvi_scelta("E1_RSI_CROSS_OVERSOLD", lato="long")
    LONG_condition_scelta  = risolvi_scelta(["E1_RSI_CROSS_OVERSOLD",
                                             "E4_EMA_CROSS_UP"], lato="long")
    SHORT_condition_scelta = risolvi_scelta(["E9_SHORT_CLOSING_PATTERN_ONLY_II",
                                             "E4_SHORT_EMA_CROSS_DOWN"], lato="short")

La variabile che ne esce e' sempre UN NOME (una stringa): le celle dopo
(`entry_cols_long=[LONG_condition_scelta]`, `entry_long=LONG_condition_scelta`)
restano come sono. Con una lista di 2 o piu' entry il nome e' generato da solo,
tipo `OR(E1_RSI_CROSS_OVERSOLD|E4_EMA_CROSS_UP)`, con le entry in ordine
alfabetico (stessa lista in ordine diverso = stessa composita).

`registra_or(nome, [...])` e' la funzione sotto, se vuoi dare tu un nome.

Regole
------
* Servono almeno 2 entry, con nomi diversi e TUTTE della stessa direzione.
  La composita eredita quella direzione.
* Il risultato passa per `_evento`: resta un evento puntuale (una barra True
  per occorrenza), come richiede il collaudo. Se A scatta alla barra t e B alla
  barra t+1, la composita ha un solo evento, a t: il secondo segnale nello
  stesso verso sarebbe comunque ignorato a posizione aperta.
* Nessun lookahead aggiunto: la composita e' un OR barra per barra di
  condizioni gia' causali, quindi lo e' a sua volta.
* Si puo' richiamare piu' volte: se il nome e' gia' registrato con LA STESSA
  definizione viene saltato con un avviso; con una definizione diversa
  solleva errore (per non sostituire in silenzio una entry sotto un nome
  gia' usato nei risultati).

Attenzione ai test multipli
---------------------------
Ogni composita provata e' una prova in piu' nel conteggio `k` della soglia di
rumore. E la composita non dice QUALE delle entry ha fatto scattare il trade:
prima si valida ogni entry da sola (event study), poi si combinano solo quelle
che hanno retto. `componenti(nome)` restituisce le entry di base.
"""
from __future__ import annotations

import difflib

import numpy as np
import pandas as pd

from helpers import _evento

# nome della composita -> tuple dei nomi delle entry di base
_COMPOSITE: dict[str, tuple[str, ...]] = {}


def _con_suggerimenti(mancanti, registrate) -> str:
    """'NOME (simili: A, B)' per ogni nome non trovato: aiuta quando una numerazione e' cambiata."""
    pezzi = []
    for n in mancanti:
        simili = difflib.get_close_matches(n, sorted(registrate), n=3, cutoff=0.6)
        pezzi.append(f"'{n}'" + (f" (simili registrate: {', '.join(simili)})" if simili else ""))
    return "; ".join(pezzi)


def componenti(nome: str) -> tuple[str, ...]:
    """Le entry di base di una composita registrata. KeyError se non lo e'."""
    if nome not in _COMPOSITE:
        raise KeyError(f"'{nome}' non e' una entry composita registrata da registra_or. "
                       f"Composite note: {sorted(_COMPOSITE)}.")
    return _COMPOSITE[nome]


def elenca_composite() -> dict[str, tuple[str, ...]]:
    """Tutte le composite registrate in questa sessione: {nome: (entry di base, ...)}."""
    return dict(_COMPOSITE)


def registra_or(nome: str, entry_nomi) -> str:
    """
    Registra `nome` come entry composita: vera dove scatta ALMENO UNA delle
    `entry_nomi`. Restituisce `nome`.

    Solleva ValueError se: meno di 2 entry, nomi ripetuti, entry non registrate,
    direzioni miste, o `nome` gia' usato con una definizione diversa.
    """
    from engine.registry import (get_entry, get_entry_direction, list_entries,
                                 register_entry)

    if isinstance(entry_nomi, str):
        raise ValueError("entry_nomi dev'essere una lista di nomi, non una stringa sola.")
    entry_nomi = tuple(entry_nomi)
    if len(entry_nomi) < 2:
        raise ValueError("Una composita in OR richiede almeno 2 entry.")
    if len(set(entry_nomi)) != len(entry_nomi):
        raise ValueError(f"Entry ripetute nella composita: {list(entry_nomi)}.")

    registrate = set(list_entries())
    mancanti = [n for n in entry_nomi if n not in registrate]
    if mancanti:
        raise ValueError(f"Entry non registrate: {_con_suggerimenti(mancanti, registrate)}. "
                         f"Registrale prima (es. registra_trigger_long()).")

    direzioni = {n: get_entry_direction(n) for n in entry_nomi}
    if len(set(direzioni.values())) != 1:
        raise ValueError(f"Direzioni miste, un OR deve stare su un lato solo: {direzioni}.")
    direction = next(iter(direzioni.values()))

    if nome in registrate:
        if _COMPOSITE.get(nome) == entry_nomi:
            print(f"[registra_or] '{nome}' gia' registrata con la stessa definizione, salto.")
            return nome
        raise ValueError(
            f"Il nome '{nome}' e' gia' registrato"
            + (f" come composita di {list(_COMPOSITE[nome])}" if nome in _COMPOSITE else "")
            + ". Scegli un nome nuovo.")

    def composita(df: pd.DataFrame) -> pd.Series:
        # le entry si valutano al momento dell'uso, non alla registrazione
        maschere = [get_entry(n)(df).fillna(False).astype(bool).to_numpy() for n in entry_nomi]
        unione = pd.Series(np.logical_or.reduce(maschere), index=df.index)
        return _evento(unione)

    register_entry(nome, direction)(composita)
    _COMPOSITE[nome] = entry_nomi
    print(f"[registra_or] '{nome}' registrata ({'long' if direction == 1 else 'short'}): "
          f"{' OR '.join(entry_nomi)}.")
    return nome


def risolvi_scelta(scelta, lato: str, consenti_invertite: bool = False):
    """
    Dalla scelta fatta dopo l'event study al NOME da passare al motore.

    scelta
        Un nome di entry (str) oppure una lista di nomi. Con una sola entry
        restituisce quel nome com'e'. Con 2 o piu' registra la composita in OR
        (`OR(A|B)`, entry in ordine alfabetico) e ne restituisce il nome.
        None -> None (lato non attivo).
    lato
        "long" o "short", obbligatorio: dichiara per quale lato stai
        scegliendo e fa da controllo. Se una entry e' dell'altro lato
        solleva ValueError e dice quali. Il nome della variabile non basta:
        la direzione di ogni entry e' scritta nel registro.
    consenti_invertite
        True = accetta entry dell'altro lato (il motore le tradera' con il
        segnale invertito). Default False: quasi sempre e' un errore di copia.

    Il risultato e' una stringa: le celle successive non cambiano.
    """
    from engine.registry import get_entry_direction, list_entries

    attese = {"long": 1, "short": -1}
    if lato not in attese:
        raise ValueError("lato dev'essere 'long' oppure 'short'.")
    if scelta is None:
        return None

    nomi = (scelta,) if isinstance(scelta, str) else tuple(scelta)
    if not nomi:
        raise ValueError(f"Scelta {lato.upper()} vuota: una lista senza entry. "
                         f"Usa None se quel lato non deve entrare.")
    if not all(isinstance(n, str) for n in nomi):
        raise ValueError(f"Scelta {lato.upper()}: servono nomi di entry (stringhe), trovato {list(nomi)}.")

    registrate = set(list_entries())
    mancanti = [n for n in nomi if n not in registrate]
    if mancanti:
        raise ValueError(f"Scelta {lato.upper()}: entry non registrate: "
                         f"{_con_suggerimenti(mancanti, registrate)}.")

    if not consenti_invertite:
        sbagliate = [n for n in nomi if get_entry_direction(n) != attese[lato]]
        if sbagliate:
            altro = "short" if lato == "long" else "long"
            raise ValueError(
                f"Scelta {lato.upper()}: queste entry sono {altro.upper()}: {sbagliate}. "
                f"Se vuoi davvero tradarle con il segnale invertito passa consenti_invertite=True.")

    if len(nomi) == 1:
        return nomi[0]

    ordinati = sorted(nomi)
    return registra_or("OR(" + "|".join(ordinati) + ")", ordinati)
