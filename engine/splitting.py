"""
Split In-Sample / Out-of-Sample.

Per dati di serie storiche lo split è sempre CRONOLOGICO, mai casuale:
il tratto iniziale (In-Sample) è quello su cui gira l'intero processo
iterativo di ricerca (Pass 1, 2, 3, ...); il tratto finale (Out-of-Sample)
resta "sigillato" e va usato una sola volta, alla fine, per validare le
strategie sopravvissute a tutti i passaggi. Non va mai usato per scegliere
o scartare strategie durante la ricerca: altrimenti perde il suo scopo
(diventerebbe esso stesso in-sample "per osmosi").
"""
from __future__ import annotations
import pandas as pd


def split_is_oos(df: pd.DataFrame, is_ratio: float = 0.8) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Divide `df` in (df_is, df_oos) secondo `is_ratio` (default 80/20),
    rispettando l'ordine temporale.

    Parametri
    ---------
    df : DataFrame con indice temporale ordinato in modo crescente.
    is_ratio : quota (0-1) di barre da assegnare all'In-Sample.

    Ritorna
    -------
    (df_is, df_oos)
    """
    if not 0.0 < is_ratio < 1.0:
        raise ValueError("is_ratio deve essere compreso tra 0 e 1 (es. 0.8 per 80/20).")
    if len(df) < 2:
        raise ValueError("Il DataFrame è troppo corto per essere diviso.")
    if not df.index.is_monotonic_increasing:
        raise ValueError(
            "Il DataFrame non è ordinato cronologicamente: ordina l'indice "
            "prima di chiamare split_is_oos()."
        )

    split_pos = int(len(df) * is_ratio)
    split_pos = max(1, min(split_pos, len(df) - 1))  # garantisce entrambi i lati non vuoti

    df_is = df.iloc[:split_pos].copy()
    df_oos = df.iloc[split_pos:].copy()
    return df_is, df_oos


def describe_split(df_is: pd.DataFrame, df_oos: pd.DataFrame) -> pd.DataFrame:
    """Piccolo riepilogo utile da stampare nel notebook dopo lo split."""
    total = len(df_is) + len(df_oos)
    return pd.DataFrame(
        {
            "n_barre": [len(df_is), len(df_oos), total],
            "quota": [len(df_is) / total, len(df_oos) / total, 1.0],
            "dal": [df_is.index.min(), df_oos.index.min(), df_is.index.min()],
            "al": [df_is.index.max(), df_oos.index.max(), df_oos.index.max()],
        },
        index=["In-Sample", "Out-of-Sample", "Totale"],
    )
