"""
Operatori VWAP condivisi — adattati dal file `vwap_indicator_features.py`
fornito dall'utente. Vivono in engine/ (non in conditions/) per lo stesso
motivo di alpha_ops.py: sono operatori generici sul prezzo, riutilizzabili
da più file di condizioni, non logica di una singola strategia.

`vwap_anchored_daily` calcola la colonna base `vwap`, richiesta da diverse
formule alpha101 (#5, #41, #42, #57, #61, #62 ecc.) — va eseguita UNA VOLTA
nella cella "1.1 Features Engineering" del notebook, non dentro le
condizioni (altrimenti verrebbe ricalcolata ad ogni chiamata).

`regression_trend_fit` e `vwap_gap` sono invece usate solo dai filtri di
regime in conditions/vwap_regime_filter_conditions.py (price_over_under,
gap_trend, last_close_position) — non fanno parte delle 101 formule del
paper, sono un'estensione proposta dall'utente.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .motore_veloce import DISPONIBILE, njit   # numba, se c'e' (21/10/2026, E4)


def vwap_anchored_daily(df: pd.DataFrame) -> pd.Series:
    """
    VWAP intraday ancorato al giorno (si azzera e riparte ad ogni nuova
    sessione), calcolato come cumulata di prezzo tipico * volume diviso
    cumulata di volume, entrambe raggruppate per data.
    """
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    tp_x_vol = typical_price * df["Volume"]

    date_groups = df.index.date
    cumulative_tp_vol = tp_x_vol.groupby(date_groups).cumsum()
    cumulative_vol = df["Volume"].groupby(date_groups).cumsum()

    return cumulative_tp_vol / cumulative_vol


@njit(cache=True)
def _regressione_giorni(y, inizio_giorno):
    """Il ciclo di `_cumulative_regression_fitted_fast`, su tutta la serie:
    le somme ripartono da zero dove `inizio_giorno` e' True. Stesse
    operazioni nello stesso ordine: stesso risultato al bit."""
    n = y.size
    fitted = np.empty(n)
    sum_y = 0.0
    sum_xy = 0.0
    i = 0
    for k in range(n):
        if inizio_giorno[k]:
            sum_y = 0.0
            sum_xy = 0.0
            i = 0
        sum_y += y[k]
        sum_xy += i * y[k]
        if i == 0:
            fitted[k] = y[k]
        else:
            n_points = i + 1
            sum_x = i * (i + 1) / 2
            sum_x2 = i * (i + 1) * (2 * i + 1) / 6
            denom = n_points * sum_x2 - sum_x * sum_x
            slope = (n_points * sum_xy - sum_x * sum_y) / denom
            intercept = (sum_y - slope * sum_x) / n_points
            fitted[k] = intercept + slope * i
        i += 1
    return fitted


def regression_trend_fit(close: pd.Series) -> pd.Series:
    """
    Regressione lineare incrementale (O(n)) del prezzo di chiusura,
    ricalcolata da zero ad ogni nuova sessione (stessa logica di
    `regression_vwap_gap` nel file originale, isolata dal calcolo del gap
    vero e proprio).

    21/10/2026 (E4, docs/65 §16): con numba il ciclo gira compilato su tutta
    la serie (`_regressione_giorni`), circa 0,02 s invece di 0,7 s su
    190.000 barre; stesso risultato al bit (test_motore_veloce.py, sezione G).
    Senza numba, serie vuota o indice non in ordine: il calcolo di prima,
    `_regression_trend_fit_pandas`.
    """
    if not DISPONIBILE or len(close) == 0 or not close.index.is_monotonic_increasing:
        return _regression_trend_fit_pandas(close)
    giorni = close.index.normalize().asi8          # la data di ogni barra, come index.date
    inizio = np.empty(len(giorni), dtype=np.bool_)
    inizio[0] = True
    inizio[1:] = giorni[1:] != giorni[:-1]
    y = np.ascontiguousarray(close.to_numpy(dtype=float))
    return pd.Series(_regressione_giorni(y, inizio), index=close.index, name=close.name)


def _regression_trend_fit_pandas(close: pd.Series) -> pd.Series:
    """Il calcolo originale (gruppi per data con pandas): riserva senza numba
    e termine di paragone dei test."""

    def _cumulative_regression_fitted_fast(close_session: pd.Series) -> pd.Series:
        y = close_session.values
        n = len(y)
        fitted = np.empty(n)

        sum_y = 0.0
        sum_xy = 0.0

        for i in range(n):
            sum_y += y[i]
            sum_xy += i * y[i]

            if i == 0:
                fitted[i] = y[i]
            else:
                n_points = i + 1
                sum_x = i * (i + 1) / 2
                sum_x2 = i * (i + 1) * (2 * i + 1) / 6

                denom = n_points * sum_x2 - sum_x * sum_x
                slope = (n_points * sum_xy - sum_x * sum_y) / denom
                intercept = (sum_y - slope * sum_x) / n_points

                fitted[i] = intercept + slope * i

        return pd.Series(fitted, index=close_session.index)

    date_groups = close.index.date
    fitted = close.groupby(date_groups).apply(_cumulative_regression_fitted_fast)
    if isinstance(fitted.index, pd.MultiIndex):
        fitted = fitted.droplevel(0)
    return fitted


def vwap_gap(df: pd.DataFrame, vwap: pd.Series) -> pd.Series:
    """Scarto tra il fair value stimato via regressione intraday e il vwap."""
    fitted = regression_trend_fit(df["Close"])
    return fitted - vwap
