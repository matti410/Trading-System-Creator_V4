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


def confine_da_quota(df: pd.DataFrame, passo, is_ratio: float = 0.8) -> pd.Timestamp:
    """
    Il confine (25/10/2026, docs/70 §2.1) che corrisponde a `split_is_oos(df,
    is_ratio)`: la FINE dell'ultima barra in-sample (inizio + `passo`, la durata
    di una barra). Con split_al_confine da' gli stessi due pezzi.
    """
    df_is, _ = split_is_oos(df, is_ratio=is_ratio)
    return pd.Timestamp(df_is.index[-1]) + pd.Timedelta(passo)


def split_al_confine(df: pd.DataFrame, confine, passo) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Divide `df` in (df_is, df_oos) a un CONFINE fisso (25/10/2026, docs/70 §2):
    in-sample = le barre che si CHIUDONO entro il confine (inizio + `passo` <=
    confine), out-of-sample = le altre. Con «si chiudono» la regola vale uguale
    su ogni timeframe: nessuna barra in-sample contiene un minuto oltre il
    confine. Le barre nuove di un CSV aggiornato finiscono tutte nell'out-of-sample.

    confine   istante (testo o Timestamp; senza fuso vale come UTC)
    passo     la durata di una barra (Timedelta o testo, es. "15min")
    """
    if not df.index.is_monotonic_increasing:
        raise ValueError("Il DataFrame non è ordinato cronologicamente: ordina l'indice "
                         "prima di chiamare split_al_confine().")
    c = pd.Timestamp(confine)
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        c = c.tz_localize("UTC") if c.tzinfo is None else c.tz_convert(idx.tz)
    elif c.tzinfo is not None:
        c = c.tz_convert("UTC").tz_localize(None)
    dentro = (idx + pd.Timedelta(passo)) <= c
    n = int(dentro.sum())
    if not dentro[:n].all():
        raise ValueError("split_al_confine: indice con barre fuori ordine.")
    return df.iloc[:n].copy(), df.iloc[n:].copy()


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
