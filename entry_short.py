"""
Trigger di ingresso SHORT.

Ogni funzione `entry_*` prende il DataFrame di mercato (OHLCV +
indicatori: rsi, ema20, ema50, zlema50) e restituisce una Series
booleana della stessa lunghezza: True dove il trigger scatta.

Tutte le funzioni restituiscono EVENTI (una sola barra True per
occorrenza), non stati.

`aggiungi_trigger_short(df)` in fondo al file chiama tutte le funzioni
e restituisce il df con una colonna in più per ciascun trigger.

Per aggiungere un nuovo trigger:
1. scrivere una nuova funzione `entry_*(df) -> pd.Series`
2. aggiungerla al dizionario dentro `aggiungi_trigger_short`
"""
import pandas as pd
import talib

from helpers import (
    _evento,
    _cross_up,
    _cross_down,
    _ts_rank,
    _cdl_bear,
    _confermato,
    _conferma_ribassista,
)


# ------------------------------------------------------------- E1 --------
def entry_short_rsi_cross_overbought(df: pd.DataFrame, threshold: float = 70.0) -> pd.Series:
    """L'RSI attraversa la soglia di ipercomprato verso l'alto -> short."""
    return _evento(_cross_up(df["rsi"], pd.Series(threshold, index=df.index)))


# ------------------------------------------------------------- E2 --------
def entry_short_zlema_cross_down(df: pd.DataFrame) -> pd.Series:
    """Il prezzo attraversa la ZLEMA dall'alto verso il basso -> short."""
    return _evento(_cross_down(df["Close"], df["zlema50"]))


# ------------------------------------------------------------- E3 --------
def entry_short_intrabar_strength_fade(
    df: pd.DataFrame,
    pos_window: float = 10,
    rank_window: float = 20,
    threshold: float = 0.85,
) -> pd.Series:
    """
    Close nella parte alta del range recente E barra chiusa forte
    rispetto all'apertura -> fade ribassista.
    """
    posizione = _ts_rank(df["Close"], pos_window)
    forza = _ts_rank(df["Close"] / df["Open"], rank_window)
    return _evento((posizione > threshold) & (forza > threshold))


# ------------------------------------------------------------- E4 --------
def entry_short_ema_cross_down(df: pd.DataFrame) -> pd.Series:
    """EMA20 attraversa EMA50 dall'alto verso il basso -> short."""
    return _evento(_cross_down(df["ema20"], df["ema50"]))


# ------------------------------------------------------------- E5 --------
def entry_short_quick_pullback(df: pd.DataFrame) -> pd.Series:
    """Speculare del pullback rapido: rottura ribassista dopo pullback."""
    high2, high1 = df["High"].shift(2), df["High"].shift(1)
    low2, low1 = df["Low"].shift(2), df["Low"].shift(1)
    cond = (low2 < low1) & (high2 > high1) & (df["Close"] < low2)
    return _evento(cond)


# ------------------------------------------------------------- E6 --------
def entry_short_back_in_style(df: pd.DataFrame) -> pd.Series:
    """Speculare di back-in-style, con Low al posto di High."""
    h, l = df["High"], df["Low"]
    cond = (
        (l.shift(3) > h)
        & (h > l.shift(1))
        & (l > l.shift(2))
        & (l.shift(1) > l.shift(2))
    )
    return _evento(cond)


# ------------------------------------------------------------- E7 --------
def entry_short_big_tail_bars(
    df: pd.DataFrame,
    period: float = 10,
    window: float = 2000,
    percentile: float = 0.90,
) -> pd.Series:
    """Prevalenza di bear tail bars nel decile alto della propria storia recente."""
    o, h, l, c = df["Open"], df["High"], df["Low"], df["Close"]
    bull_tail = (c > o) & ((o - l) > (c - o)) & (h > h.shift(1))
    bear_tail = (c < o) & ((h - o) > (o - c)) & (l < l.shift(1))
    bull_count = bull_tail.rolling(int(period)).sum()
    bear_count = bear_tail.rolling(int(period)).sum()

    soglia = bear_count.rolling(int(window)).quantile(percentile).shift(1)
    cond = (bull_count < bear_count) & (bear_count > soglia)
    return _evento(cond)


# ------------------------------------------------------------- E8 --------
def entry_short_closing_pattern_only(df: pd.DataFrame) -> pd.Series:
    """Speculare di closing-pattern-only: chiusure in accelerazione ribassista."""
    c = df["Close"]
    cond = (c.shift(1) < c.shift(3)) & (c < c.shift(2)) & (c.shift(2) < c.shift(1))
    return _evento(cond)


# ------------------------------------------------------------- E9 --------
def entry_short_closing_pattern_only_ii(df: pd.DataFrame) -> pd.Series:
    """Speculare di closing-pattern-only-II, disuguaglianze invertite."""
    c = df["Close"]
    cond = (
        (c.shift(1) > c.shift(2))
        & (c.shift(2) > c.shift(5))
        & (c.shift(5) > c.shift(3))
        & (c.shift(3) > c.shift(4))
    )
    return _evento(cond)


# ------------------------------------------------------------ E10 --------
def entry_short_hanging_man(df: pd.DataFrame) -> pd.Series:
    """Hanging Man -> stessa geometria dell'Hammer, ma in coda a un uptrend."""
    return _cdl_bear(df, talib.CDLHANGINGMAN)


# ------------------------------------------------------------ E11 --------
def entry_short_shooting_star(df: pd.DataFrame) -> pd.Series:
    """Shooting Star -> reversal ribassista dopo un uptrend."""
    return _cdl_bear(df, talib.CDLSHOOTINGSTAR)


def entry_short_shooting_star_confirmed(df: pd.DataFrame) -> pd.Series:
    """Shooting Star + chiusura ribassista sulla barra successiva."""
    return _confermato(_cdl_bear(df, talib.CDLSHOOTINGSTAR), _conferma_ribassista(df))


# ------------------------------------------------------------ E12 --------
def entry_short_engulfing(df: pd.DataFrame) -> pd.Series:
    """Bearish Engulfing."""
    return _cdl_bear(df, talib.CDLENGULFING)


def entry_short_engulfing_confirmed(df: pd.DataFrame) -> pd.Series:
    """Bearish Engulfing + chiusura ribassista sulla barra successiva."""
    return _confermato(_cdl_bear(df, talib.CDLENGULFING), _conferma_ribassista(df))


# ------------------------------------------------------------ E13 --------
def entry_short_harami(df: pd.DataFrame) -> pd.Series:
    """Bearish Harami."""
    return _cdl_bear(df, talib.CDLHARAMI)


def entry_short_harami_confirmed(df: pd.DataFrame) -> pd.Series:
    """Bearish Harami + chiusura ribassista sulla barra successiva."""
    return _confermato(_cdl_bear(df, talib.CDLHARAMI), _conferma_ribassista(df))


# ------------------------------------------------------------ E14 --------
def entry_short_harami_cross(df: pd.DataFrame) -> pd.Series:
    """Bearish Harami Cross."""
    return _cdl_bear(df, talib.CDLHARAMICROSS)


def entry_short_harami_cross_confirmed(df: pd.DataFrame) -> pd.Series:
    """Bearish Harami Cross + chiusura ribassista sulla barra successiva."""
    return _confermato(_cdl_bear(df, talib.CDLHARAMICROSS), _conferma_ribassista(df))


# ------------------------------------------------------------ E15 --------
def entry_short_dark_cloud_cover(df: pd.DataFrame) -> pd.Series:
    """Dark Cloud Cover -> reversal ribassista dopo un uptrend."""
    return _cdl_bear(df, talib.CDLDARKCLOUDCOVER)


# ------------------------------------------------------------ E16 --------
def entry_short_evening_star(df: pd.DataFrame) -> pd.Series:
    """Evening Star -> reversal ribassista dopo un uptrend."""
    return _cdl_bear(df, talib.CDLEVENINGSTAR)


# ------------------------------------------------------------ E17 --------
def entry_short_three_inside(df: pd.DataFrame) -> pd.Series:
    """Three Inside Down."""
    return _cdl_bear(df, talib.CDL3INSIDE)


# ------------------------------------------------------------ E18 --------
def entry_short_three_outside(df: pd.DataFrame) -> pd.Series:
    """Three Outside Down."""
    return _cdl_bear(df, talib.CDL3OUTSIDE)


# ------------------------------------------------------------ E19 --------
def entry_short_three_black_crows(df: pd.DataFrame) -> pd.Series:
    """Three Black Crows -> speculare di Three White Soldiers."""
    return _cdl_bear(df, talib.CDL3BLACKCROWS)


# ------------------------------------------------------------ E20 --------
def entry_short_marubozu(df: pd.DataFrame) -> pd.Series:
    """Bearish Marubozu -> candela di piena convinzione ribassista."""
    return _cdl_bear(df, talib.CDLMARUBOZU)


# ------------------------------------------------------------ E21 --------
def entry_short_belt_hold(df: pd.DataFrame) -> pd.Series:
    """Bearish Belt-hold."""
    return _cdl_bear(df, talib.CDLBELTHOLD)


def entry_short_belt_hold_confirmed(df: pd.DataFrame) -> pd.Series:
    """Bearish Belt-hold + chiusura ribassista sulla barra successiva."""
    return _confermato(_cdl_bear(df, talib.CDLBELTHOLD), _conferma_ribassista(df))


# =========================================================================
def aggiungi_trigger_short(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcola tutti i trigger short e li aggiunge come colonne al df.
    Non modifica il df originale: ne restituisce una copia.

    Per aggiungere un nuovo trigger: scrivere la funzione qui sopra e
    aggiungere una riga al dizionario `trigger` qui sotto.
    """
    df = df.copy()

    trigger = {
        "E1_SHORT_RSI_CROSS_OVERBOUGHT": entry_short_rsi_cross_overbought(df),
        "E2_SHORT_ZLEMA_CROSS_DOWN": entry_short_zlema_cross_down(df),
        "E3_SHORT_INTRABAR_STRENGTH_FADE": entry_short_intrabar_strength_fade(df),
        "E4_SHORT_EMA_CROSS_DOWN": entry_short_ema_cross_down(df),
        "E5_SHORT_QUICK_PULLBACK": entry_short_quick_pullback(df),
        "E6_SHORT_BACK_IN_STYLE": entry_short_back_in_style(df),
        "E7_SHORT_BIG_TAIL_BARS": entry_short_big_tail_bars(df),
        "E8_SHORT_CLOSING_PATTERN_ONLY": entry_short_closing_pattern_only(df),
        "E9_SHORT_CLOSING_PATTERN_ONLY_II": entry_short_closing_pattern_only_ii(df),
        "E10_SHORT_HANGING_MAN": entry_short_hanging_man(df),
        "E11_SHORT_SHOOTING_STAR": entry_short_shooting_star(df),
        "E11_SHORT_SHOOTING_STAR_CONFIRMED": entry_short_shooting_star_confirmed(df),
        "E12_SHORT_ENGULFING": entry_short_engulfing(df),
        "E12_SHORT_ENGULFING_CONFIRMED": entry_short_engulfing_confirmed(df),
        "E13_SHORT_HARAMI": entry_short_harami(df),
        "E13_SHORT_HARAMI_CONFIRMED": entry_short_harami_confirmed(df),
        "E14_SHORT_HARAMI_CROSS": entry_short_harami_cross(df),
        "E14_SHORT_HARAMI_CROSS_CONFIRMED": entry_short_harami_cross_confirmed(df),
        "E15_SHORT_DARK_CLOUD_COVER": entry_short_dark_cloud_cover(df),
        "E16_SHORT_EVENING_STAR": entry_short_evening_star(df),
        "E17_SHORT_THREE_INSIDE": entry_short_three_inside(df),
        "E18_SHORT_THREE_OUTSIDE": entry_short_three_outside(df),
        "E19_SHORT_THREE_BLACK_CROWS": entry_short_three_black_crows(df),
        "E20_SHORT_MARUBOZU": entry_short_marubozu(df),
        "E21_SHORT_BELT_HOLD": entry_short_belt_hold(df),
        "E21_SHORT_BELT_HOLD_CONFIRMED": entry_short_belt_hold_confirmed(df),
    }

    for nome_colonna, serie in trigger.items():
        df[nome_colonna] = serie

    return df
