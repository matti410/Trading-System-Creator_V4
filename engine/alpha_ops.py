"""
Operatori ausiliari per la traduzione dei "101 Formulaic Alphas"
(Kakushadze, WorldQuant, 2015 — arXiv:1601.00991) su un SINGOLO
asset/serie storica.

Perché questo modulo esiste
----------------------------
Il paper originale definisce alcuni operatori — in particolare `rank(x)` e
`scale(x)` — come CROSS-SEZIONALI: calcolati confrontando un valore tra
centinaia/migliaia di titoli diversi allo stesso istante t. Il nostro
motore lavora invece su UN SOLO strumento alla volta, quindi il
cross-sectional rank non ha significato quantitativo (non c'è nulla con
cui confrontare) ed è stato sostituito, dove necessario, con `ts_rank`:
un percentile "nel tempo" calcolato sulla storia recente dello stesso
asset, invece che "nello spazio" tra asset diversi. Stessa idea per
`scale`. Discussione completa in STATO_PROGETTO.md.

Questo modulo NON contiene condizioni (quelle vivono in conditions/,
come sempre) — solo operatori generici e riutilizzabili, importati
esplicitamente dai file conditions/alpha101_*.py che ne hanno bisogno.
Il core del motore (registry/loader/combination/backtest/ranking/
inspection) non lo importa mai direttamente: aggiungerlo qui non rompe
il principio "core mai toccato per aggiungere condizioni", perché questi
sono operatori matematici generici, non logica di strategia.

Convenzione: tutte le funzioni accettano/restituiscono pd.Series indicizzate
come il DataFrame di mercato, coerenti con le colonne OHLCV Capitalizzate
(Open/High/Low/Close/Volume) e gli indicatori minuscoli usati nel resto
del progetto.

Nota sulle finestre temporali: i parametri di default ricalcano i valori
giorno-per-giorno usati nel paper originale (dati daily). Il progetto
lavora su timeframe intraday (M15): questi default vanno probabilmente
ricalibrati — sono esposti come parametri proprio per questo, ma la
ricalibrazione va fatta esplicitamente, non è automatica.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import rankdata


def _floor_window(d: float) -> int:
    """Un numero di giorni non intero viene troncato per difetto (floor),
    come da definizione del paper (Appendice A.1)."""
    return max(1, int(math.floor(d)))


# --------------------------------------------------------------------------
# Operatori "ts_" — sostituiscono gli equivalenti cross-sezionali del paper
# --------------------------------------------------------------------------

def ts_rank(x: pd.Series, window: float) -> pd.Series:
    """
    Percentile rolling: per ogni barra, la posizione percentile (0-1)
    dell'ultimo valore rispetto alle ultime `window` barre (se stesso
    incluso). Sostituisce il `rank(x)` cross-sezionale del paper (che
    confrontava tra titoli diversi) con un rank "nel tempo", sull'unico
    asset disponibile.
    """
    w = _floor_window(window)

    def _last_pct_rank(arr: np.ndarray) -> float:
        return rankdata(arr)[-1] / len(arr)

    return x.rolling(w).apply(_last_pct_rank, raw=True)


def ts_min(x: pd.Series, window: float) -> pd.Series:
    """Minimo mobile sulle ultime `window` barre."""
    return x.rolling(_floor_window(window)).min()


def ts_max(x: pd.Series, window: float) -> pd.Series:
    """Massimo mobile sulle ultime `window` barre."""
    return x.rolling(_floor_window(window)).max()


def ts_argmax(x: pd.Series, window: float) -> pd.Series:
    """Quante barre fa si è verificato il massimo delle ultime `window`
    barre (0 = oggi/barra corrente, window-1 = la barra più vecchia)."""
    w = _floor_window(window)
    return x.rolling(w).apply(lambda a: w - 1 - int(np.argmax(a)), raw=True)


def ts_argmin(x: pd.Series, window: float) -> pd.Series:
    """Come ts_argmax, ma per il minimo."""
    w = _floor_window(window)
    return x.rolling(w).apply(lambda a: w - 1 - int(np.argmin(a)), raw=True)


def ts_sum(x: pd.Series, window: float) -> pd.Series:
    """Somma mobile sulle ultime `window` barre."""
    return x.rolling(_floor_window(window)).sum()


def ts_product(x: pd.Series, window: float) -> pd.Series:
    """Prodotto mobile sulle ultime `window` barre."""
    return x.rolling(_floor_window(window)).apply(np.prod, raw=True)


def ts_stddev(x: pd.Series, window: float) -> pd.Series:
    """Deviazione standard mobile sulle ultime `window` barre."""
    return x.rolling(_floor_window(window)).std()


def ts_correlation(x: pd.Series, y: pd.Series, window: float) -> pd.Series:
    """Correlazione mobile tra due serie sulle ultime `window` barre."""
    return x.rolling(_floor_window(window)).corr(y)


def ts_covariance(x: pd.Series, y: pd.Series, window: float) -> pd.Series:
    """Covarianza mobile tra due serie sulle ultime `window` barre."""
    return x.rolling(_floor_window(window)).cov(y)


def decay_linear(x: pd.Series, window: float) -> pd.Series:
    """
    Media mobile ponderata con pesi decrescenti linearmente: il valore più
    recente ha peso `window`, quello più vecchio della finestra ha peso 1,
    pesi rinormalizzati a somma 1.
    """
    w = _floor_window(window)
    weights = np.arange(1, w + 1, dtype=float)
    weights /= weights.sum()
    return x.rolling(w).apply(lambda a: float(np.dot(a, weights)), raw=True)


# --------------------------------------------------------------------------
# Operatori "puntuali" (non richiedono una finestra, o la usano solo per lo
# spostamento temporale)
# --------------------------------------------------------------------------

def delay(x: pd.Series, d: int = 1) -> pd.Series:
    """Valore di x, d barre fa."""
    return x.shift(d)


def delta(x: pd.Series, d: int = 1) -> pd.Series:
    """Valore di x oggi meno il valore di x, d barre fa."""
    return x - x.shift(d)


def signedpower(x: pd.Series, a: float) -> pd.Series:
    """x elevato alla a, preservando il segno di x (utile per a non interi)."""
    return np.sign(x) * (x.abs() ** a)


def scale(x: pd.Series, a: float = 1.0, window: float = 20) -> pd.Series:
    """
    Riscala x in modo che sum(abs(x)) = a. Nel paper è un'operazione
    CROSS-SEZIONALE (riscala rispetto a tutti i titoli allo stesso
    istante); qui diventa un'operazione rolling sulla propria storia
    recente (finestra `window`, default 20 barre) — stessa idea, applicata
    nel tempo invece che nello spazio. Cambia la scala assoluta del
    segnale, non solo la sua forma: da usare con consapevolezza.
    """
    w = _floor_window(window)
    rolling_abs_sum = x.abs().rolling(w).sum()
    return a * x / rolling_abs_sum


def adv(close: pd.Series, volume: pd.Series, window: float) -> pd.Series:
    """Volume medio in valuta (average dollar volume) sulle ultime
    `window` barre — equivalente di adv{d} nel paper."""
    return (close * volume).rolling(_floor_window(window)).mean()


def returns(close: pd.Series) -> pd.Series:
    """Rendimento percentuale barra-su-barra (close-to-close)."""
    return close.pct_change()


# --------------------------------------------------------------------------
# Discretizzazione: da score continuo con segno a evento bidirezionale
# --------------------------------------------------------------------------

def crossing_signal(score: pd.Series, threshold: float = 0.0) -> pd.Series:
    """
    Converte uno score continuo con segno in un segnale bidirezionale
    discreto {-1, 0, +1}, nello stesso spirito di B1_EMA_TREND_FLIP /
    B2_RSI_EXTREMES già presenti nel progetto: +1 quando lo score
    attraversa `threshold` dal basso, -1 quando attraversa -`threshold`
    dall'alto, 0 altrove (nessun nuovo evento — se una posizione è aperta,
    resta quella determinata dall'ultimo segnale, secondo la logica di
    "flip" del motore in Strategy Inspection bidirezionale).
    """
    above = score > threshold
    below = score < -threshold
    cross_up = above & (~above.shift(1).fillna(False))
    cross_down = below & (~below.shift(1).fillna(False))
    return cross_up.astype(int) - cross_down.astype(int)
