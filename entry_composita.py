"""
Entry composite: PIU' ENTRY IN «OR», registrate come una entry sola.

A cosa serve
------------
Il motore usa UNA entry per lato. Per far lavorare insieme piu' condizioni
d'ingresso («entro long se scatta A oppure B oppure C») si registra una entry
composita: per il resto del framework e' una entry come le altre
(`run_event_study`, `run_exit_search_bt`, `run_filter_search_bt`, collaudo).

Come si usa (dal notebook, dopo aver registrato le entry di base):

    from entry_composita import registra_or

    registra_or("C1_LONG_EMA_O_ENGULFING",
                ["E4_EMA_CROSS_UP", "E12_ENGULFING"])

    # poi, come qualunque altra entry:
    #   entry_cols_long=["C1_LONG_EMA_O_ENGULFING"]

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

import numpy as np
import pandas as pd

from helpers import _evento

# nome della composita -> tuple dei nomi delle entry di base
_COMPOSITE: dict[str, tuple[str, ...]] = {}


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
        raise ValueError(f"Entry non registrate: {mancanti}. "
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
