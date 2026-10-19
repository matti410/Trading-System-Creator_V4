"""
Trigger di ingresso LONG.

Ogni funzione `entry_*` prende il DataFrame di mercato (OHLCV +
indicatori: rsi, ema20, ema50, zlema50) e restituisce una Series
booleana della stessa lunghezza: True dove il trigger scatta.

Tutte le funzioni restituiscono EVENTI (una sola barra True per
occorrenza), non stati.

Due funzioni d'uso, in fondo al file:

  aggiungi_trigger_long(df)   calcola tutti i trigger e li aggiunge come
                               colonne al df (usalo quando ti servono le
                               colonne, es. per ispezionarle a mano).

  registra_trigger_long()     registra tutte le funzioni nel motore
                               (engine.registry), cosi' run_event_study
                               le trova da solo. Va chiamata prima di
                               run_event_study.

Per aggiungere un nuovo trigger:
1. scrivere una nuova funzione `entry_*(df) -> pd.Series`
2. aggiungerla al dizionario `TRIGGER_LONG` qui sotto
"""
import pandas as pd
import talib

from helpers import (
    _evento,
    _vsa_figure,
    _cross_up,
    _cross_up_zlema,
    _cross_down,
    _ts_rank,
    _cdl_bull,
    _confermato,
    _conferma_rialzista,
)
from engine.livelli import primo_del_giorno, quarantena_cached, range_finestra
from engine.sessioni import in_sessione


# ------------------------------------------------------------- E1 --------
def entry_rsi_cross_oversold(df: pd.DataFrame, threshold: float = 30.0) -> pd.Series:
    """L'RSI attraversa la soglia di ipervenduto verso il basso -> long."""
    return _evento(_cross_down(df["rsi"], pd.Series(threshold, index=df.index)))


# ------------------------------------------------------------- E2 --------
def entry_zlema_cross_up(df: pd.DataFrame) -> pd.Series:
    """Il prezzo attraversa la ZLEMA dal basso verso l'alto -> long."""
    return _evento(_cross_up_zlema(df["Open"], df["Close"], df["zlema50"]))


# ------------------------------------------------------------- E3 --------
def entry_long_intrabar_weakness_fade(
    df: pd.DataFrame,
    pos_window: float = 10,
    rank_window: float = 20,
    threshold: float = 0.15,
) -> pd.Series:
    """
    Close nella parte bassa del range recente E barra chiusa debole
    rispetto all'apertura -> fade rialzista.
    """
    posizione = _ts_rank(df["Close"], pos_window)
    forza = _ts_rank(df["Close"] / df["Open"], rank_window)
    return _evento((posizione < threshold) & (forza < threshold))


# ------------------------------------------------------------- E4 --------
def entry_ema_cross_up(df: pd.DataFrame) -> pd.Series:
    """EMA20 attraversa EMA50 dal basso verso l'alto -> long."""
    return _evento(_cross_up(df["ema20"], df["ema50"]))


# ------------------------------------------------------------- E5 --------
def entry_quick_pullback(df: pd.DataFrame) -> pd.Series:
    """
    High di 2 barre fa > High di 1 barra fa (pullback nel massimo) E
    Low di 2 barre fa < Low di 1 barra fa (pullback nel minimo) E
    chiusura corrente sopra l'High di 2 barre fa -> rottura rialzista.
    """
    high2, high1 = df["High"].shift(2), df["High"].shift(1)
    low2, low1 = df["Low"].shift(2), df["Low"].shift(1)
    cond = (high2 > high1) & (low2 < low1) & (df["Close"] > high2)
    return _evento(cond)


# ------------------------------------------------------------- E6 --------
def entry_back_in_style(df: pd.DataFrame) -> pd.Series:
    """
    High di 3 barre fa < Low corrente E Low corrente < High di 1 barra
    fa E High corrente < High di 2 barre fa E High di 1 barra fa <
    High di 2 barre fa -> struttura di compressione rialzista.
    """
    h, l = df["High"], df["Low"]
    cond = (
        (h.shift(3) < l)
        & (l < h.shift(1))
        & (h < h.shift(2))
        & (h.shift(1) < h.shift(2))
    )
    return _evento(cond)


# ------------------------------------------------------------- E7 --------
def entry_big_tail_bars(
    df: pd.DataFrame,
    period: float = 10,
    window: float = 2000,
    percentile: float = 0.90,
) -> pd.Series:
    """Prevalenza di bull tail bars nel decile alto della propria storia recente."""
    o, h, l, c = df["Open"], df["High"], df["Low"], df["Close"]
    bull_tail = (c > o) & ((o - l) > (c - o)) & (h > h.shift(1))
    bear_tail = (c < o) & ((h - o) > (o - c)) & (l < l.shift(1))
    bull_count = bull_tail.rolling(int(period)).sum()
    bear_count = bear_tail.rolling(int(period)).sum()

    soglia = bull_count.rolling(int(window)).quantile(percentile).shift(1)
    cond = (bull_count > bear_count) & (bull_count > soglia)
    return _evento(cond)


# ------------------------------------------------------------- E8 --------
def entry_closing_pattern_only(df: pd.DataFrame) -> pd.Series:
    """
    Close di 1 barra fa > Close di 3 barre fa E Close corrente > Close
    di 2 barre fa E Close di 2 barre fa > Close di 1 barra fa ->
    struttura di chiusure in accelerazione rialzista.
    """
    c = df["Close"]
    cond = (c.shift(1) > c.shift(3)) & (c > c.shift(2)) & (c.shift(2) > c.shift(1))
    return _evento(cond)


# ------------------------------------------------------------- E9 --------
def entry_closing_pattern_only_ii(df: pd.DataFrame) -> pd.Series:
    """
    Close di 1 barra fa < Close di 2 barre fa < Close di 5 barre fa <
    Close di 3 barre fa < Close di 4 barre fa -> struttura di chiusure
    a "dente di sega" con recupero recente.
    """
    c = df["Close"]
    cond = (
        (c.shift(1) < c.shift(2))
        & (c.shift(2) < c.shift(5))
        & (c.shift(5) < c.shift(3))
        & (c.shift(3) < c.shift(4))
    )
    return _evento(cond)


# ------------------------------------------------------------ E10 --------
def entry_hammer(df: pd.DataFrame) -> pd.Series:
    """Hammer -> reversal rialzista dopo un downtrend."""
    return _cdl_bull(df, talib.CDLHAMMER)


# ------------------------------------------------------------ E11 --------
def entry_inverted_hammer(df: pd.DataFrame) -> pd.Series:
    """Inverted Hammer -> reversal rialzista dopo un downtrend."""
    return _cdl_bull(df, talib.CDLINVERTEDHAMMER)


def entry_inverted_hammer_confirmed(df: pd.DataFrame) -> pd.Series:
    """Inverted Hammer + chiusura rialzista sulla barra successiva."""
    return _confermato(_cdl_bull(df, talib.CDLINVERTEDHAMMER), _conferma_rialzista(df))


# ------------------------------------------------------------ E12 --------
def entry_engulfing(df: pd.DataFrame) -> pd.Series:
    """Bullish Engulfing."""
    return _cdl_bull(df, talib.CDLENGULFING)


def entry_engulfing_confirmed(df: pd.DataFrame) -> pd.Series:
    """Bullish Engulfing + chiusura rialzista sulla barra successiva."""
    return _confermato(_cdl_bull(df, talib.CDLENGULFING), _conferma_rialzista(df))


# ------------------------------------------------------------ E13 --------
def entry_harami(df: pd.DataFrame) -> pd.Series:
    """Bullish Harami."""
    return _cdl_bull(df, talib.CDLHARAMI)


def entry_harami_confirmed(df: pd.DataFrame) -> pd.Series:
    """Bullish Harami + chiusura rialzista sulla barra successiva."""
    return _confermato(_cdl_bull(df, talib.CDLHARAMI), _conferma_rialzista(df))


# ------------------------------------------------------------ E14 --------
def entry_harami_cross(df: pd.DataFrame) -> pd.Series:
    """Bullish Harami Cross."""
    return _cdl_bull(df, talib.CDLHARAMICROSS)


def entry_harami_cross_confirmed(df: pd.DataFrame) -> pd.Series:
    """Bullish Harami Cross + chiusura rialzista sulla barra successiva."""
    return _confermato(_cdl_bull(df, talib.CDLHARAMICROSS), _conferma_rialzista(df))


# ------------------------------------------------------------ E15 --------
def entry_piercing(df: pd.DataFrame) -> pd.Series:
    """Piercing Pattern -> reversal rialzista dopo un downtrend."""
    return _cdl_bull(df, talib.CDLPIERCING)


# ------------------------------------------------------------ E16 --------
def entry_morning_star(df: pd.DataFrame) -> pd.Series:
    """Morning Star -> reversal rialzista dopo un downtrend."""
    return _cdl_bull(df, talib.CDLMORNINGSTAR)


# ------------------------------------------------------------ E17 --------
def entry_three_inside(df: pd.DataFrame) -> pd.Series:
    """Three Inside Up."""
    return _cdl_bull(df, talib.CDL3INSIDE)


# ------------------------------------------------------------ E18 --------
def entry_three_outside(df: pd.DataFrame) -> pd.Series:
    """Three Outside Up."""
    return _cdl_bull(df, talib.CDL3OUTSIDE)


# ------------------------------------------------------------ E19 --------
def entry_three_white_soldiers(df: pd.DataFrame) -> pd.Series:
    """Three Advancing White Soldiers."""
    return _cdl_bull(df, talib.CDL3WHITESOLDIERS)


# ------------------------------------------------------------ E20 --------
def entry_marubozu(df: pd.DataFrame) -> pd.Series:
    """Bullish (Closing) Marubozu -> candela di piena convinzione rialzista."""
    return _cdl_bull(df, talib.CDLMARUBOZU)


# ------------------------------------------------------------ E21 --------
def entry_belt_hold(df: pd.DataFrame) -> pd.Series:
    """Bullish Belt-hold."""
    return _cdl_bull(df, talib.CDLBELTHOLD)


def entry_belt_hold_confirmed(df: pd.DataFrame) -> pd.Series:
    """Bullish Belt-hold + chiusura rialzista sulla barra successiva."""
    return _confermato(_cdl_bull(df, talib.CDLBELTHOLD), _conferma_rialzista(df))


# =========================================================================
# TEMPO + PREZZO
# Il tempo definisce un livello, il prezzo decide quando lo rompe.
#
# I livelli arrivano da engine/livelli.py, che garantisce due cose:
#  - nessun lookahead: il livello alla barra i viene da una finestra chiusa
#    PRIMA di i (verificato per forza bruta nei test);
#  - le barre in quarantena (finestra del rollover, dove i prezzi bid sono
#    deformati dall'allargamento dello spread) non entrano nel calcolo di
#    massimi e minimi.
#
# Nessun buffer e nessuna soglia: la rottura e' Close > massimo, punto.
# Ogni parametro in piu' sarebbe una prova in piu' nel conteggio dei test
# multipli.
# =========================================================================


def entry_asian_range_breakout(df: pd.DataFrame) -> pd.Series:
    """
    La chiusura esce sopra il massimo del range asiatico -> long.

    Il range va dall'apertura di Tokyo all'apertura di Londra. Il trigger
    puo' scattare dall'apertura di Londra alla chiusura di New York, una
    volta sola al giorno (la prima rottura).
    """
    livelli = range_finestra(df, "TOKYO", "LONDRA")
    finestra = in_sessione(df, "LONDRA") | in_sessione(df, "NEW_YORK")
    rottura = (df["Close"] > livelli["massimo"]) & livelli["pronto"] & finestra
    pulita = ~quarantena_cached(df)["totale"]
    return primo_del_giorno(rottura & pulita, df)


def entry_prev_day_high_breakout(df: pd.DataFrame) -> pd.Series:
    """
    La chiusura esce sopra il massimo della giornata FX precedente -> long.

    La giornata e' ancorata al rollover delle 17:00 di New York, non a
    mezzanotte. Il trigger vale per tutta la giornata, una volta sola.
    """
    livelli = range_finestra(df, "ROLLOVER")
    rottura = (df["Close"] > livelli["massimo"]) & livelli["pronto"]
    pulita = ~quarantena_cached(df)["totale"]
    return primo_del_giorno(rottura & pulita, df)


# ------------------------------------------------------------ E24 --------
def entry_cycle_turn_up(df: pd.DataFrame) -> pd.Series:
    """
    Il ciclo dominante smette di scendere e inizia a salire -> long.

    Legge `ciclo_pendenza` (engine/indicatori.py, finestra di 300 barre solo
    sul passato): l'evento e' la barra in cui passa da negativa a positiva.

    Fonte dell'idea: Sofien Kaabar, "Forecasting Market Cycles with Fourier
    Transform in Python", 29/9/2026, https://medium.com/@kaabar-sofien/forecasting-market-cycles-with-fourier-transform-in-python-9b29c110cd3c
    """
    zero = pd.Series(0.0, index=df.index)
    return _evento(_cross_up(df["ciclo_pendenza"], zero))


# ------------------------------------------------------------ E25 --------
def entry_atc_pvo_setup_up(df: pd.DataFrame) -> pd.Series:
    """
    Setup completo della fonte, lato long: tutte e quattro insieme, sulla
    stessa barra.

      1. il canale di trend adattivo passa da ribassista a rialzista
         (`atc_regime` da -1 a +1);
      2. la barra del segnale chiude sopra l'apertura;
      3. anche la barra precedente chiude sopra l'apertura;
      4. l'istogramma del PVO (12/26/9, tick volume) e' sopra zero.

    Una sola prova: l'AND e' l'ipotesi dell'autore (regola di 50 §4). Se
    una conferma manca sulla barra del cambio, nessun ingresso: la fonte non
    aspetta conferme arrivate dopo.

    Dal 9/10/2026 sostituisce E25_ADAPTIVE_CHANNEL_UP (solo il canale).

    Fonte: "Adaptive Trend Channel" di MarketStructureLab (TradingView,
    licenza CC BY-NC-SA 4.0), usato in Sayedali Richu, "Want to Find Better
    Trading Opportunities? Start With These 2 Indicators", 24/9/2026,
    https://medium.com/@sayedali_3166/want-to-find-better-trading-opportunities-start-with-these-2-indicators-ea37c3ee6f55
    """
    regime = df["atc_regime"]
    cambio = (regime == 1) & (regime.shift(1) == -1)
    verde = df["Close"] > df["Open"]
    due_verdi = verde & verde.shift(1, fill_value=False)
    return _evento(cambio & due_verdi & (df["pvo_hist"] > 0))


# ------------------------------------------------------------ E26 --------
def entry_supertrend_iix_setup_up(df: pd.DataFrame) -> pd.Series:
    """
    Setup completo della fonte, lato long: tutte e tre insieme, sulla stessa
    barra.

      1. il Supertrend (ATR 10, moltiplicatore 3) passa da ribassista a
         rialzista (`st_dir` da -1 a +1);
      2. la barra PRECEDENTE quella del segnale chiude sopra l'apertura (la
         barra del segnale non e' richiesta: la fonte non la nomina);
      3. l'Intraday Intensity a 21 barre e' sopra zero.

    Una sola prova: l'AND e' l'ipotesi dell'autore (regola di 50 §4).

    Dal 9/10/2026 sostituisce E26_SUPERTREND_UP (solo il Supertrend).

    Fonte: Sayedali Richu, "My Simple Formula for Filtering Intraday Buy &
    Sell Signals", 27/9/2026, https://medium.com/@sayedali_3166/my-simple-formula-for-filtering-intraday-buy-sell-signals-0267e115d0f5
    """
    direzione = df["st_dir"]
    cambio = (direzione == 1) & (direzione.shift(1) == -1)
    precedente_verde = (df["Close"] > df["Open"]).shift(1, fill_value=False)
    return _evento(cambio & precedente_verde & (df["iix"] > 0))


# ------------------------------------------------------------ E27 --------
def entry_vsa_bullish(df: pd.DataFrame) -> pd.Series:
    """
    Figura VSA rialzista: "stopping volume" oppure "no supply" -> long.

    Sono le due figure con cui la fonte apre un long senza il punteggio di
    contesto (tolto: nel codice della fonte non calcola cio' che dichiara).
    Un'OR, quindi una sola prova. Classificazioni in helpers._vsa_figure.

    Fonte: PyQuantLab, "Volume Spread Analysis (VSA) Strategy: Quantifying
    Market Action for Trading Signals with Rolling Backtesting", 20/6/2025,
    https://medium.com/@pyquantlab/volume-spread-analysis-vsa-strategy-quantifying-market-action-for-trading-signals-with-rolling-9aa57fb79fe9
    """
    figure = _vsa_figure(df)
    return _evento(figure["stopping_volume"] | figure["no_supply"])


# ------------------------------------------------------------ E28 --------
def entry_vfi_cross_up(df: pd.DataFrame) -> pd.Series:
    """
    Il Volume Flow Indicator (colonna `vfi`, 130 barre) passa sopra lo zero
    -> long. Evento: la barra in cui va da <= 0 a > 0.

    Dipende dalla qualita' del volume (tick volume su MT5). Riscaldamento:
    261 barre.

    Fonte dell'indicatore: LazyBear, "Volume Flow Indicator [LazyBear]",
    TradingView, https://www.tradingview.com/script/MhlDpfdS-Volume-Flow-Indicator-LazyBear/
    (nessuna licenza dichiarata). Regola d'ingresso: docs/51 §3, V1.
    """
    zero = pd.Series(0.0, index=df.index)
    return _evento(_cross_up(df["vfi"], zero))


# ------------------------------------------------------------ E29 --------
def entry_squeeze_release_up(df: pd.DataFrame) -> pd.Series:
    """
    Rilascio dello squeeze con momentum positivo -> long: sulla barra
    precedente le Bollinger erano dentro il Keltner (`sqz_on` = 1), su questa
    non piu' (`sqz_on` = 0), e l'istogramma `sqz_mom` e' sopra zero.

    Evento per costruzione (lo squeeze si spegne una volta per episodio).
    Riscaldamento: 38 barre.

    Fonte dell'indicatore: LazyBear, "Squeeze Momentum Indicator [LazyBear]",
    TradingView, https://www.tradingview.com/script/nqQ1DT5a-Squeeze-Momentum-Indicator-LazyBear/
    (nessuna licenza dichiarata; moltiplicatore BB corretto, vedi
    engine.indicatori.squeeze_momentum). Regola: docs/51 §3, M1.
    """
    rilascio = (df["sqz_on"].shift(1) == 1) & (df["sqz_on"] == 0)
    return _evento(rilascio & (df["sqz_mom"] > 0))


# ------------------------------------------------------------ E30 --------
def entry_wavetrend_cross_up(df: pd.DataFrame, rank_window: int = 500,
                             percentile: float = 0.10) -> pd.Series:
    """
    WaveTrend: WT1 incrocia sopra WT2 mentre WT1 e' in ipervenduto -> long.

    Ipervenduto = WT1, sulla barra dell'incrocio, nel 10% piu' basso delle
    proprie ultime 500 barre (percentile rolling al posto della soglia fissa
    -60 dello script). La finestra (500) e' molto piu' larga di quella
    dell'indicatore (~40 barre) e resta usabile su H4 e D1 (scelta di Mattia
    del 15/10/2026: 2000 barre erano 8 anni in D1). Parametri fissati a
    priori, mai provati in varianti. Riscaldamento: circa 540 barre.

    Fonte dell'indicatore: LazyBear, "WaveTrend Oscillator [WT]", TradingView,
    https://www.tradingview.com/script/2KE8wTuF-Indicator-WaveTrend-Oscillator-WT/
    (nessuna licenza dichiarata). Regola: docs/51 §3, M2; soglia a percentile
    rolling al posto di +-60 (traduzione nostra, scelta di Mattia il 15/10/2026).
    """
    ipervenduto = _ts_rank(df["wt1"], rank_window) <= percentile
    return _evento(_cross_up(df["wt1"], df["wt2"]) & ipervenduto)


# ------------------------------------------------------------ E31 --------
def entry_triple_screen_up(df: pd.DataFrame) -> pd.Series:
    """
    Triple Screen di Elder, setup completo (tre schermi in AND) -> long.

      1. schermo 1, la marea: la pendenza del MACD-Histogram (12/26/9) delle
         H4 e' in salita (`mtf_h4_macdh_pend` > 0)
      2. schermo 2, l'onda contraria: il Force Index (EMA a 2) dell'ultima H1
         chiusa e' sotto zero (`mtf_h1_force` < 0)
      3. schermo 3, l'ingresso: la chiusura M15 supera il massimo dell'ultima
         H1 chiusa (`mtf_h1_high`); evento, prima barra in cui succede

    Tutte le candele superiori sono gia' chiuse (engine.indicatori.
    triple_screen_colonne). Traduzioni nostre approvate da Mattia il
    15/10/2026: timeframe H4/H1 per l'ingresso su M15; lo stop d'acquisto "un
    tick sopra il massimo" diventa la chiusura sopra il massimo (il motore
    entra all'Open dopo); omessa la clausola "purche' non a un nuovo minimo
    di piu' settimane".

    Fonte: A. Elder, "Trading for a Living", Wiley 1993, cap. 43 (pp. 235-243).
    """
    cond = ((df["mtf_h4_macdh_pend"] > 0) & (df["mtf_h1_force"] < 0)
            & (df["Close"] > df["mtf_h1_high"]))
    return _evento(cond)


def entry_algox_careful_up(df: pd.DataFrame) -> pd.Series:
    """
    AlgoXplorer 0.1c, setup completo con ingresso "careful" -> long.

      1. etichetta Buy: candela PVSRA climax rialzista, chiusura Heikin Ashi
         sopra la EMA a 50 dei massimi, massimo HA sopra la chiusura HA,
         chiusura HA sopra il massimo HA della barra prima; l'ultimo
         segnale non era gia' un Buy
      2. ingresso: prima barra dopo il Buy, prima del Sell, il cui massimo HA
         supera il massimo HA della candela del Buy (nessun ingresso se non
         succede: "Not enter")

    Colonna `algox_careful` (engine.indicatori.algoxplorer). Parametri dello
    script: Sensibility 2 (EMA 50), strategia careful.

    Fonte: "AlgoXplorer 0.1c", indicatore Pine v5 scritto da Mattia e da un
    amico, uso concordato (docs/50 §10, riga 13; 17/10/2026).
    """
    return _evento(df["algox_careful"] == 1)


def entry_algox_novol_careful_up(df: pd.DataFrame) -> pd.Series:
    """
    Come E32_ALGOX_CAREFUL_UP ma senza la candela PVSRA (interruttore
    "Forex" dello script acceso): il Buy non chiede il volume climax. Uguale
    su tutti i symbol (decisione di Mattia del 17/10/2026). Colonna
    `algox_nv_careful`.

    Fonte: "AlgoXplorer 0.1c" (Mattia e un amico), docs/50 §10, riga 13.
    """
    return _evento(df["algox_nv_careful"] == 1)


def entry_vsa_trend_go_up(df: pd.DataFrame) -> pd.Series:
    """
    VSA · Modulo Unico, GO trend following (Step 12-17), setup completo -> long:

      1. asta rialzista confermata (almeno 2 BOS di fila al rialzo)
      2. momentum rialzista: la gamba al rialzo e' piu' forte di quella al
         ribasso di almeno il 20%
      3. forza d'asta >= 1 corpo mediano per candela
      4. nelle 3 barre prima, una candela di incongruenza VSA rialzista
         (assorbimento o esaurimento contrario al colore della candela)
      5. il minimo di quella candela a non piu' di 2 corpi mediani da uno swing
      6. candela di conferma rialzista con corpo >= 50° percentile

    Senza filtro di sessione (decisione di Mattia del 17/10/2026). Colonna
    `vsa_go` (engine.indicatori.vsa_modulo_unico).

    Fonte: "VSA · Modulo Unico", indicatore Pine v6 scritto da Mattia
    (docs/50 §10, riga 14).
    """
    return _evento(df["vsa_go"] == 1)


def entry_vsa_stop_reverse_up(df: pd.DataFrame) -> pd.Series:
    """
    VSA · Modulo Unico, Stop & Reverse (Step 24) -> long: CHoCH al rialzo (il
    primo BOS rialzista dopo un'asta ribassista confermata), chiuso da una
    candela rialzista con corpo >= 65° percentile. Colonna `vsa_sr`.

    Fonte: "VSA · Modulo Unico" (Mattia), docs/50 §10, riga 14.
    """
    return _evento(df["vsa_sr"] == 1)


# ------------------------------------------------------------ E36 --------
def entry_intraday_momentum_up(df: pd.DataFrame) -> pd.Series:
    """
    Momentum intraday: il prezzo delle 09:30 di New York e' sopra quello
    delle 17:00 del giorno di trading prima (`imm_r1` > 0) -> long alle 16:30,
    da chiudere alle 17:00 con X_ORA_@17:00 (l'ultima mezz'ora del paper).
    Una volta al giorno, sulla candela che finisce alle 16:30.

    Fonte: Shen, Urquhart, Wang, "Bitcoin Intraday Time-Series Momentum",
    Financial Review 57(2), 2022, §3.4, formula 7 (idea di Gao, Han, Li,
    Zhou, J. of Financial Economics 2018). Colonne: engine.indicatori.
    momentum_intraday.
    """
    return _evento(df["imm_r1"] > 0)


# ------------------------------------------------------------ E37 --------
def entry_intraday_momentum_combo_up(df: pd.DataFrame) -> pd.Series:
    """
    Momentum intraday combinato (setup in AND, come nella fonte) -> long
    alle 16:30, da chiudere alle 17:00 con X_ORA_@17:00:

      1. la «prima mezz'ora» e' salita: 17:00 del giorno prima -> 09:30
         (`imm_r1` > 0)
      2. la penultima mezz'ora e' scesa: 16:00 -> 16:30 (`imm_r12` < 0)

    I segni opposti sono quelli di Bitcoin nella fonte (la penultima mezz'ora
    va contro l'ultima); sull'S&P 500 Gao e altri chiedono lo stesso segno.

    Fonte: Shen, Urquhart, Wang, "Bitcoin Intraday Time-Series Momentum",
    Financial Review 57(2), 2022, §3.4, formula 8.
    """
    return _evento((df["imm_r1"] > 0) & (df["imm_r12"] < 0))


# ------------------------------------------------------------ E38 --------
def entry_hour_momentum_up(df: pd.DataFrame) -> pd.Series:
    """
    Coppia di ore 8~22 (momentum): l'ora 07:00 -> 08:00 UTC e' salita
    (`ora_r8` > 0) -> long alle 21:00 UTC dello stesso giorno, da chiudere
    alle 22:00 con X_ORA_@22:00_UTC. Una volta al giorno, sulla candela che
    finisce alle 21:00 UTC.

    Fonte: Wen, Bouri, Xu, Zhao, "Intraday return predictability in the
    cryptocurrency markets: momentum, reversal, or both", North American J.
    of Economics and Finance 62, 2022 (SSRN 4080253), Tab. 2 e §5.1 eq. 8.
    Colonna: engine.indicatori.rendimenti_ore_utc.
    """
    return _evento(df["ora_r8"] > 0)


# ------------------------------------------------------------ E39 --------
def entry_hour_reversal_up(df: pd.DataFrame) -> pd.Series:
    """
    Coppia di ore 12~13 (inversione): l'ora 11:00 -> 12:00 UTC e' scesa
    (`ora_r12` < 0) -> long alle 12:00 UTC, da chiudere alle 13:00 con
    X_ORA_@13:00_UTC. Una volta al giorno, sulla candela che finisce alle
    12:00 UTC.

    Fonte: Wen, Bouri, Xu, Zhao, North American J. of Economics and Finance
    62, 2022 (SSRN 4080253), Tab. 2 e §5.1 eq. 8. Colonna:
    engine.indicatori.rendimenti_ore_utc.
    """
    return _evento(df["ora_r12"] < 0)


# ------------------------------------------------------------ E40 --------
def entry_jump_momentum_up(df: pd.DataFrame) -> pd.Series:
    """
    Momentum dopo un salto: al primo controllo di mezz'ora della giornata in
    cui il rendimento dalla chiusura di ieri (17:00 di New York) supera il
    90° percentile dei rendimenti giornalieri delle ultime 250 giornate
    (`salto` == 1) -> long, da chiudere alla chiusura con X_ORA_@17:00.
    Al massimo una volta al giorno.

    Fonte: Baltussen, Da, Lammers, Martens, "Hedging demand and market
    intraday momentum", J. of Financial Economics 2021 (SSRN 3760365),
    §4.3 e Tab. 10. Colonna: engine.indicatori.salto_giornaliero.
    """
    return _evento(df["salto"] == 1)


# =========================================================================
# Dizionario nome -> funzione. E' l'unica cosa da toccare per aggiungere
# un trigger: scrivere la funzione qui sopra e aggiungere una riga qui.
# =========================================================================
TRIGGER_LONG = {
    "E1_RSI_CROSS_OVERSOLD": entry_rsi_cross_oversold,
    "E2_ZLEMA_CROSS_UP": entry_zlema_cross_up,
    "E3_LONG_INTRABAR_WEAKNESS_FADE": entry_long_intrabar_weakness_fade,
    "E4_EMA_CROSS_UP": entry_ema_cross_up,
    "E5_QUICK_PULLBACK": entry_quick_pullback,
    "E6_BACK_IN_STYLE": entry_back_in_style,
    "E7_BIG_TAIL_BARS": entry_big_tail_bars,
    "E8_CLOSING_PATTERN_ONLY": entry_closing_pattern_only,
    "E9_CLOSING_PATTERN_ONLY_II": entry_closing_pattern_only_ii,
    "E10_HAMMER": entry_hammer,
    "E11_INVERTED_HAMMER": entry_inverted_hammer,
    # "E11_INVERTED_HAMMER_CONFIRMED": entry_inverted_hammer_confirmed,   # SPENTO 17/10/2026, versione confermata, al 100% dentro la base (docs/50 §10 septies)
    "E12_ENGULFING": entry_engulfing,
    # "E12_ENGULFING_CONFIRMED": entry_engulfing_confirmed,   # SPENTO 17/10/2026, versione confermata, al 100% dentro la base (docs/50 §10 septies)
    "E13_HARAMI": entry_harami,
    # "E13_HARAMI_CONFIRMED": entry_harami_confirmed,   # SPENTO 17/10/2026, versione confermata, al 100% dentro la base (docs/50 §10 septies)
    # "E14_HARAMI_CROSS": entry_harami_cross,   # SPENTO 17/10/2026, al 100% dentro E13 harami (docs/50 §10 septies)
    # "E14_HARAMI_CROSS_CONFIRMED": entry_harami_cross_confirmed,   # SPENTO 17/10/2026, versione confermata, al 100% dentro la base (docs/50 §10 septies)
    # "E15_PIERCING": entry_piercing,   # SPENTO 17/10/2026, rara: 47-122 eventi in-sample (docs/50 §10 septies)
    "E16_MORNING_STAR": entry_morning_star,
    # "E17_THREE_INSIDE": entry_three_inside,   # SPENTO 17/10/2026, al 100% dentro E13 harami (docs/50 §10 septies)
    # "E18_THREE_OUTSIDE": entry_three_outside,   # SPENTO 17/10/2026, al 100% dentro E12 engulfing (docs/50 §10 septies)
    "E19_THREE_WHITE_SOLDIERS": entry_three_white_soldiers,
    # "E20_MARUBOZU": entry_marubozu,   # SPENTO 17/10/2026, al 100% dentro E21 belt hold (docs/50 §10 septies)
    "E21_BELT_HOLD": entry_belt_hold,
    # "E21_BELT_HOLD_CONFIRMED": entry_belt_hold_confirmed,   # SPENTO 17/10/2026, versione confermata, al 100% dentro la base (docs/50 §10 septies)
    "E22_ASIAN_RANGE_BREAKOUT": entry_asian_range_breakout,
    "E23_PREV_DAY_HIGH_BREAKOUT": entry_prev_day_high_breakout,
    "E24_CYCLE_TURN_UP": entry_cycle_turn_up,
    "E25_ATC_PVO_SETUP_UP": entry_atc_pvo_setup_up,    "E26_SUPERTREND_IIX_SETUP_UP": entry_supertrend_iix_setup_up,
    "E27_VSA_BULLISH": entry_vsa_bullish,
    "E28_VFI_CROSS_UP": entry_vfi_cross_up,
    "E29_SQUEEZE_RELEASE_UP": entry_squeeze_release_up,
    "E30_WAVETREND_CROSS_UP": entry_wavetrend_cross_up,
    "E31_TRIPLE_SCREEN_UP": entry_triple_screen_up,
    "E32_ALGOX_CAREFUL_UP": entry_algox_careful_up,
    "E33_ALGOX_NOVOL_CAREFUL_UP": entry_algox_novol_careful_up,
    "E34_VSA_TREND_GO_UP": entry_vsa_trend_go_up,
    "E35_VSA_STOP_REVERSE_UP": entry_vsa_stop_reverse_up,
    "E36_INTRADAY_MOMENTUM_UP": entry_intraday_momentum_up,
    "E37_INTRADAY_MOMENTUM_COMBO_UP": entry_intraday_momentum_combo_up,
    "E38_HOUR_MOMENTUM_UP": entry_hour_momentum_up,
    "E39_HOUR_REVERSAL_UP": entry_hour_reversal_up,
    "E40_JUMP_MOMENTUM_UP": entry_jump_momentum_up,
}


def aggiungi_trigger_long(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcola tutti i trigger long e li aggiunge come colonne al df.
    Non modifica il df originale: ne restituisce una copia.
    """
    df = df.copy()
    for nome_colonna, funzione in TRIGGER_LONG.items():
        df[nome_colonna] = funzione(df)
    return df


def registra_trigger_long():
    """
    Registra tutti i trigger long nel motore (engine.registry), cosi'
    run_event_study (e il resto del framework) li trova da solo.

    Va chiamata una volta prima di run_event_study. E' sicura da
    richiamare piu' volte nella stessa sessione: i nomi gia' registrati
    vengono saltati con un avviso, non sollevano errore.
    """
    from engine.registry import register_entry, list_entries

    gia_presenti = set(list_entries())
    nuovi = 0
    for nome, funzione in TRIGGER_LONG.items():
        if nome in gia_presenti:
            print(f"[registra_trigger_long] '{nome}' gia' registrata, salto.")
            continue
        register_entry(nome, direction=1)(funzione)
        nuovi += 1
    print(f"[registra_trigger_long] {nuovi} entry long registrate "
          f"({len(TRIGGER_LONG) - nuovi} gia' presenti).")
