"""
API pubblica del motore.

Riesporta esplicitamente le funzioni/classi dei sotto-moduli, cosi'
`import engine as eng` da' accesso diretto a `eng.<nome>` per tutto cio'
che il notebook usa, senza dover ricordare in quale file .py vive
ciascuna funzione.

Se aggiungi una nuova funzione pubblica a un modulo del motore, aggiungila
anche qui sotto (nell'import corrispondente ed in __all__), altrimenti
resta accessibile solo come eng.<nome_modulo>.<funzione>.

NOTA (settembre 2026) — la vecchia metodologia (combination, backtest,
ranking, inspection, exit_lab, viability, selection) e' stata rimossa: era
stata SOSTITUITA, non estesa, da event_study + exit_search. Resta nella
cronologia di git se dovesse servire.
"""
from __future__ import annotations

# --- registro condizioni ---------------------------------------------
from .registry import (
    register_entry,
    register_exit,
    register_filter,
    register_bidirectional_entry,
    get_entry,
    get_exit,
    get_filter,
    get_bidirectional_entry,
    get_entry_direction,
    get_exit_direction,
    get_exit_pair,
    list_exit_pairs,
    list_entries,
    list_exits,
    list_filters,
    list_bidirectional_entries,
    clear_registry,
)

# --- loader dinamico conditions/ --------------------------------------
from .loader import load_conditions

# --- split In-Sample / Out-of-Sample -----------------------------------
from .splitting import split_is_oos, describe_split

# --- operatori VWAP condivisi (usati anche direttamente nel notebook) --
from .vwap_ops import vwap_anchored_daily, regression_trend_fit, vwap_gap

# --- Sessione 1 · event study ------------------------------------------
from .event_study import run_event_study

# --- Sessione 2 · ricerca delle uscite ---------------------------------
from .exit_search import run_exit_search, due_meta

# --- controllo automatico delle scadenze -------------------------------
from .controlli import verifica_scadenze, ricerca_uscite, due_meta_controllato

__all__ = [
    # registry
    "register_entry", "register_exit", "register_filter",
    "register_bidirectional_entry",
    "get_entry", "get_exit", "get_filter", "get_bidirectional_entry",
    "get_entry_direction", "get_exit_direction", "get_exit_pair",
    "list_exit_pairs", "list_entries", "list_exits", "list_filters",
    "list_bidirectional_entries", "clear_registry",
    # loader
    "load_conditions",
    # splitting
    "split_is_oos", "describe_split",
    # vwap_ops
    "vwap_anchored_daily", "regression_trend_fit", "vwap_gap",
    # event_study
    "run_event_study",
    # exit_search
    "run_exit_search", "due_meta",
    # controlli
    "verifica_scadenze", "ricerca_uscite", "due_meta_controllato",
]
