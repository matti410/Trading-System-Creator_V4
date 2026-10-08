"""
Funzioni di supporto condivise da entry_long.py ed entry_short.py.

Nessuna di queste calcola un trigger: sono mattoncini usati dalle
funzioni nei due file di ingresso.
"""
import pandas as pd


def _evento(mask: pd.Series) -> pd.Series:
    """
    Da STATO a EVENTO: tiene solo la prima barra di ogni blocco
    consecutivo di True. Esempio: [F,T,T,T,F,T] diventa [F,T,F,F,F,T].
    """
    mask = mask.fillna(False).astype(bool)
    return mask & ~mask.shift(1, fill_value=False)


def _cross_up(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """`fast` attraversa `slow` dal basso verso l'alto (evento puntuale)."""
    return (fast > slow) & (fast.shift(1) <= slow.shift(1))


def _cross_down(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """`fast` attraversa `slow` dall'alto verso il basso (evento puntuale)."""
    return (fast < slow) & (fast.shift(1) >= slow.shift(1))


def _ts_rank(series: pd.Series, window: int) -> pd.Series:
    """
    Percentile della barra corrente rispetto alle ultime `window` barre
    della stessa serie (rolling, mai cross-sezionale). Valori in (0, 1].
    """
    return series.rolling(int(window)).rank(pct=True)


def _cdl_bull(df: pd.DataFrame, talib_func) -> pd.Series:
    """
    Lato rialzista di una funzione di pattern recognition TA-Lib (CDL*):
    qualunque valore positivo. Evento a singola barra.
    """
    raw = talib_func(
        df["Open"].values.astype(float),
        df["High"].values.astype(float),
        df["Low"].values.astype(float),
        df["Close"].values.astype(float),
    )
    return _evento(pd.Series(raw, index=df.index) > 0)


def _cdl_bear(df: pd.DataFrame, talib_func) -> pd.Series:
    """Lato ribassista della stessa funzione TA-Lib: qualunque valore negativo."""
    raw = talib_func(
        df["Open"].values.astype(float),
        df["High"].values.astype(float),
        df["Low"].values.astype(float),
        df["Close"].values.astype(float),
    )
    return _evento(pd.Series(raw, index=df.index) < 0)


def _confermato(pattern_evento: pd.Series, conferma: pd.Series) -> pd.Series:
    """
    Sposta un evento (vero a T) alla barra T+1 e lo AND-a con una
    condizione valutata sui dati della barra corrente (T+1 stesso, zero
    look-ahead): il pattern avviene a T, la conferma arriva a T+1, il
    segnale finale scatta a T+1.
    """
    pattern_shifted = pattern_evento.shift(1, fill_value=False).astype(bool)
    return pattern_shifted & conferma.fillna(False).astype(bool)


def _conferma_rialzista(df: pd.DataFrame) -> pd.Series:
    """Barra di conferma generica: chiusura sopra l'apertura alla barra corrente."""
    return df["Close"] > df["Open"]


def _conferma_ribassista(df: pd.DataFrame) -> pd.Series:
    """Barra di conferma generica: chiusura sotto l'apertura alla barra corrente."""
    return df["Close"] < df["Open"]


def _vsa_figure(df: pd.DataFrame, barre_volume: int = 7, barre_ampiezza: int = 7,
                barre_trend: int = 30, alto: float = 1.2, climax: float = 2.0,
                basso: float = 0.5, larga: float = 1.2) -> dict:
    """
    Le sei figure della Volume Spread Analysis usate da E27 e X2, una
    Series booleana ciascuna (vera sulla barra in cui la figura compare).

    Ogni barra si classifica cosi' (parametri della fonte, fissati):
      volume   / media a 7 barre:  >= 2,0 climax, >= 1,2 alto, <= 0,5 basso
      ampiezza / media a 7 barre:  >= 1,2 larga, <= 1/1,2 stretta
      chiusura nella barra:        >= 70% alta, <= 30% bassa
      trend:   chiusura sopra o sotto la media a 30 barre
    Con media non disponibile o nulla, volume o ampiezza a zero: "normale",
    come nella fonte.

    Figure rialziste: stopping_volume, no_supply, effort_up_reverse.
    Figure ribassiste: climax_sell, no_demand, effort_down_reverse.

    Su MetaTrader il volume e' tick volume; la fonte lavora su BTC
    giornaliero con volume reale. I numeri in barre restano quelli della
    fonte anche su M15 (scelta dell'8/10/2026).

    Fonte: PyQuantLab, "Volume Spread Analysis (VSA) Strategy: Quantifying
    Market Action for Trading Signals with Rolling Backtesting", 20/6/2025,
    https://medium.com/@pyquantlab/volume-spread-analysis-vsa-strategy-quantifying-market-action-for-trading-signals-with-rolling-9aa57fb79fe9
    """
    volume = df["Volume"].astype(float)
    ampiezza = (df["High"] - df["Low"]).astype(float)
    media_v = volume.rolling(barre_volume).mean()
    media_a = ampiezza.rolling(barre_ampiezza).mean()
    valido_v = media_v.notna() & (media_v != 0) & (volume != 0)
    valido_a = media_a.notna() & (media_a != 0) & (ampiezza != 0)
    rv = volume / media_v.where(media_v != 0)
    ra = ampiezza / media_a.where(media_a != 0)

    v_climax = valido_v & (rv >= climax)
    v_alto = valido_v & (rv >= alto) & ~v_climax
    v_basso = valido_v & (rv <= basso) & ~(rv >= alto)
    a_larga = valido_a & (ra >= larga)
    a_stretta = valido_a & (ra <= 1.0 / larga) & ~(ra >= larga)

    posizione = (df["Close"] - df["Low"]) / ampiezza.where(ampiezza != 0)
    c_alta = (ampiezza != 0) & (posizione >= 0.7)
    c_bassa = (ampiezza != 0) & (posizione <= 0.3) & ~c_alta
    c_media = ~c_alta & ~c_bassa

    media_t = df["Close"].rolling(barre_trend).mean()
    t_su = df["Close"] > media_t
    t_giu = df["Close"] < media_t
    barra_su = df["Close"] > df["Open"]
    barra_giu = df["Close"] < df["Open"]

    return {
        "stopping_volume": v_climax & a_larga & t_giu & barra_giu & (c_media | c_alta),
        "no_supply": v_basso & a_stretta & t_su & barra_giu & c_alta,
        "effort_up_reverse": v_alto & a_stretta & t_giu & barra_su & (c_media | c_bassa),
        "climax_sell": v_climax & a_larga & t_su & barra_su & (c_media | c_bassa),
        "no_demand": v_basso & a_stretta & t_giu & barra_su & c_bassa,
        "effort_down_reverse": v_alto & a_stretta & t_su & barra_giu & (c_media | c_alta),
    }
