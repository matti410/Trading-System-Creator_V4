"""
Indicatori tecnici del notebook, in un posto solo.

Prima vivevano nella cella 14 del notebook principale. Stanno qui perche'
il collaudo del catalogo (engine/collaudo_catalogo.py) deve poterli
RICALCOLARE da zero sui dati tagliati: una condizione che legge una
colonna gia' calcolata non puo' rivelare un lookahead nascosto dentro
l'indicatore. Con una copia sola, notebook e collaudo usano per forza la
stessa formula.

Nel notebook principale la cella 14 diventa:

    from engine.indicatori import aggiungi_indicatori
    df = aggiungi_indicatori(df)

Le formule sono identiche a quelle della cella 14 (22/9/2026).

Modulo ADDITIVO: non modifica nessun file esistente dell'engine.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import talib as ta
from numpy.lib.stride_tricks import sliding_window_view

from engine.vwap_ops import vwap_anchored_daily


def zlema(series: pd.Series, period: int) -> pd.Series:
    """Media mobile a ritardo ridotto: proietta il prezzo per compensare il lag."""
    lag = int((period - 1) / 2)
    return (2 * series - series.shift(lag)).ewm(span=period, adjust=False).mean()


# =========================================================================
# Indicatori entrati da articoli (metodo: 50_IDEE_DA_ARTICOLI.md)
# =========================================================================
def ciclo_dominante(close: pd.Series, finestra: int = 300,
                    periodo_min: int = 10, periodo_max: int = 150) -> pd.DataFrame:
    """
    Ciclo dominante delle ultime `finestra` barre, calcolato solo sul passato.

    Restituisce due colonne, una riga per barra:

        ciclo_quota      quota (0-1) dell'energia del movimento recente che
                         sta nel ciclo dominante: vicino a 1 = il mercato
                         oscilla in modo regolare, vicino a 0 = nessun ciclo
        ciclo_pendenza   verso del ciclo dominante sulla barra corrente, fra
                         -1 e +1: positivo = il ciclo sta salendo

    Come si calcola, barra per barra:
      1. si prendono i rendimenti logaritmici delle ultime `finestra` barre
         (finestra mobile: l'ultima e' la barra corrente, nessuna successiva);
      2. si toglie la media (e' il trend della finestra) e si applica una
         finestra di Hann, che evita gli artefatti ai bordi;
      3. trasformata di Fourier: fra i cicli lunghi da `periodo_min` a
         `periodo_max` barre si tiene il piu' forte, uno solo;
      4. il periodo si affina guardando i due vicini (interpolazione), poi si
         legge in che punto del ciclo cade la barra corrente.

    Si lavora sui RENDIMENTI e non sul prezzo: lo spettro di un prezzo e'
    dominato per costruzione dalle onde piu' lente, e su una passeggiata
    casuale il "ciclo dominante" del prezzo risulta lungo 150 o 100 barre nel
    97% dei casi (misurato). Sui rendimenti il rumore non ha un periodo
    preferito, e un ciclo vero si riconosce allo stesso modo.

    Parametri fissati a priori, mai provati in varianti: 300 barre e' il
    valore dell'articolo; la banda 10-150 barre e una sola armonica sono
    scelte dichiarate nella scheda del 7/10/2026.

    Le prime `finestra` barre restano NaN (storia insufficiente).

    Fonte dell'idea: Sofien Kaabar, "Forecasting Market Cycles with Fourier
    Transform in Python", 29/9/2026,
    https://medium.com/@kaabar-sofien/forecasting-market-cycles-with-fourier-transform-in-python-9b29c110cd3c
    L'articolo fa la trasformata sull'intero campione (guarda il futuro) e
    proietta in avanti la finestra: qui niente di tutto questo.
    """
    N = int(finestra)
    k_min = int(np.ceil(N / periodo_max))
    k_max = int(np.floor(N / periodo_min))
    if k_min < 2 or k_max + 1 > N // 2 or k_min > k_max:
        raise ValueError("banda dei periodi incompatibile con la finestra")

    quota = np.full(len(close), np.nan)
    pendenza = np.full(len(close), np.nan)
    if len(close) > N:
        rend = np.diff(np.log(close.to_numpy(dtype=float)))
        finestre = sliding_window_view(rend, N)          # riga j -> barra j + N
        n = np.arange(N)
        hann = 0.5 - 0.5 * np.cos(2.0 * np.pi * n / N)
        for a in range(0, len(finestre), 20_000):        # a blocchi: memoria
            w = finestre[a:a + 20_000]
            w = (w - w.mean(axis=1, keepdims=True)) * hann
            spettro = np.fft.rfft(w, axis=1)
            energia = spettro.real ** 2 + spettro.imag ** 2
            righe = np.arange(len(w))
            k = k_min + np.argmax(energia[:, k_min:k_max + 1], axis=1)
            centro = np.sqrt(energia[righe, k])
            sotto = np.sqrt(energia[righe, k - 1])
            sopra = np.sqrt(energia[righe, k + 1])
            verso = np.where(sopra >= sotto, 1.0, -1.0)
            vicino = np.maximum(sopra, sotto)
            con_segnale = centro > 0
            rapporto = np.divide(vicino, centro, out=np.zeros_like(centro), where=con_segnale)
            # frazione di "gradino" fra una frequenza e la successiva (Hann)
            scarto = np.clip((2.0 * rapporto - 1.0) / (rapporto + 1.0), 0.0, 0.5) * verso
            totale = energia[:, 1:].sum(axis=1)
            lobo = energia[righe, k - 1] + energia[righe, k] + energia[righe, k + 1]
            q = np.divide(lobo, totale, out=np.zeros_like(lobo), where=totale > 0)
            # fase al centro della finestra, portata all'ultima barra
            fase = (np.angle(spettro[righe, k]) + np.pi * k
                    + 2.0 * np.pi * (k + scarto) / N * (N - 1 - N / 2.0))
            p = np.where(con_segnale, np.cos(fase), 0.0)
            buone = np.isfinite(w).all(axis=1)
            quota[a + N:a + N + len(w)] = np.where(buone, q, np.nan)
            pendenza[a + N:a + N + len(w)] = np.where(buone, p, np.nan)
    return pd.DataFrame({"ciclo_quota": quota, "ciclo_pendenza": pendenza}, index=close.index)


def _fine_regressione(serie: pd.Series, barre: int) -> pd.Series:
    """Valore, sulla barra corrente, della retta di regressione sulle ultime `barre`."""
    n = int(barre)
    esito = pd.Series(0.0, index=serie.index)
    for j in range(n):                                   # j = 0 e' la piu' vecchia
        peso = 2.0 * (3 * j - n + 2) / (n * (n + 1))
        esito = esito + peso * serie.shift(n - 1 - j)
    return esito


def canale_adattivo_regime(df: pd.DataFrame, regressione: int = 7,
                           reazione: int = 2) -> pd.Series:
    """
    Stato del canale di trend adattivo: +1 rialzista, -1 ribassista.

    Massimi, minimi e chiusure vengono lisciati con una retta di regressione
    sulle ultime `regressione` barre. In stato rialzista il canale si porta
    dietro un supporto che puo' solo salire; passa a ribassista quando il
    massimo lisciato scende sotto quel supporto e la chiusura lisciata sta
    sotto il minimo lisciato della barra prima. In stato ribassista fa il
    contrario, con una resistenza che puo' solo scendere.

    Usa solo la barra corrente e le precedenti. Lo stato ha memoria: dipende
    dalla storia a partire dall'inizio dei dati (parte rialzista per
    convenzione, come lo script d'origine).

    Parametri: 7 e 2, i valori predefiniti dello script. La larghezza del
    canale (ATR) serve solo al disegno e qui non viene calcolata.

    Fonte: "Adaptive Trend Channel" di MarketStructureLab (TradingView),
    usato in Sayedali Richu, "Want to Find Better Trading Opportunities?
    Start With These 2 Indicators", 24/9/2026,
    https://medium.com/@sayedali_3166/want-to-find-better-trading-opportunities-start-with-these-2-indicators-ea37c3ee6f55
    LICENZA: lo script d'origine e' Creative Commons BY-NC-SA 4.0
    (https://creativecommons.org/licenses/by-nc-sa/4.0/). Questa funzione ne
    e' una riscrittura in Python e resta sotto la stessa licenza: uso non
    commerciale, con attribuzione, stessa licenza per le opere derivate.
    """
    reg_high = _fine_regressione(df["High"], regressione)
    reg_low = _fine_regressione(df["Low"], regressione)
    reg_close = _fine_regressione(df["Close"], regressione)
    reazione_alta = reg_high.rolling(reazione).mean().to_numpy()
    reazione_bassa = reg_low.rolling(reazione).mean().to_numpy()
    picco = reg_high.rolling(reazione).max().to_numpy()
    valle = reg_low.rolling(reazione).min().to_numpy()
    high_prima = reg_high.shift(1).to_numpy()
    low_prima = reg_low.shift(1).to_numpy()
    rh, rl, rc = reg_high.to_numpy(), reg_low.to_numpy(), reg_close.to_numpy()

    pronto = (np.isfinite(reazione_alta) & np.isfinite(reazione_bassa)
              & np.isfinite(high_prima) & np.isfinite(low_prima) & np.isfinite(rc))
    pronto[: int(regressione) + 1] = False     # come lo script: parte dopo `regressione` barre
    stato = np.full(len(df), np.nan)
    regime = 0                       # 0 = non ancora partito
    supporto = resistenza = np.nan
    for i in range(len(df)):
        if not pronto[i]:
            if regime:
                stato[i] = regime
            continue
        if regime == 0:
            regime, supporto = 1, rl[i]
        elif regime == 1:
            supporto = max(supporto, valle[i])
            if reazione_alta[i] < supporto and rc[i] < low_prima[i]:
                regime, resistenza = -1, rh[i]
        else:
            resistenza = min(resistenza, picco[i])
            if reazione_bassa[i] > resistenza and rc[i] > high_prima[i]:
                regime, supporto = 1, rl[i]
        stato[i] = regime
    return pd.Series(stato, index=df.index)


def pvo_istogramma(volume: pd.Series, veloce: int = 12, lenta: int = 26,
                   segnale: int = 9) -> pd.Series:
    """
    Istogramma del Percentage Volume Oscillator: positivo quando i volumi
    stanno accelerando, negativo quando rallentano.

    PVO = 100 x (media esponenziale veloce - lenta) / lenta, sui volumi;
    istogramma = PVO - media esponenziale del PVO. Valori standard 12/26/9.
    Su MetaTrader il volume e' tick volume (numero di variazioni di prezzo),
    non volume scambiato.

    Fonte: indicatore standard, usato in Sayedali Richu, "Want to Find Better
    Trading Opportunities? Start With These 2 Indicators", 24/9/2026 (URL in
    canale_adattivo_regime).
    """
    v = volume.astype(float)
    ema_veloce = v.ewm(span=veloce, adjust=False, min_periods=veloce).mean()
    ema_lenta = v.ewm(span=lenta, adjust=False, min_periods=lenta).mean()
    pvo = 100.0 * (ema_veloce - ema_lenta) / ema_lenta.where(ema_lenta != 0)
    pvo = pvo.where(ema_lenta.isna() | (ema_lenta != 0), 0.0)   # volumi tutti a zero: nessun segnale
    linea = pvo.ewm(span=segnale, adjust=False, min_periods=segnale).mean()
    return pvo - linea


def aggiungi_indicatori(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggiunge al DataFrame di mercato le colonne usate dalle condizioni:

        rsi, macd, macd_signal, macd_hist, ema20, ema50, zlema50,
        atr, realized_vol, adx, vwap,
        ciclo_quota, ciclo_pendenza, atc_regime, pvo_hist

    Le ultime quattro vengono da articoli (7/10/2026): vedi le funzioni
    ciclo_dominante, canale_adattivo_regime e pvo_istogramma qui sopra. Il
    ciclo dominante ha bisogno di 300 barre di storia: sono le prime 300
    righe a essere tolte, non piu' le prime 100 circa.

    poi toglie le righe con almeno un NaN (il riscaldamento iniziale degli
    indicatori).

    Servono le colonne Open, High, Low, Close, Volume.
    Non modifica il df originale: restituisce una copia.
    """
    df = df.copy()
    df["rsi"] = ta.RSI(df["Close"], timeperiod=14)
    df["macd"], df["macd_signal"], df["macd_hist"] = ta.MACD(
        df["Close"], fastperiod=12, slowperiod=26, signalperiod=9
    )
    df["ema20"] = df["Close"].ewm(span=20, min_periods=20).mean()
    df["ema50"] = df["Close"].ewm(span=50, min_periods=50).mean()
    df["zlema50"] = zlema(df["Close"], 50)
    df["atr"] = ta.ATR(df["High"], df["Low"], df["Close"], timeperiod=14)
    df["realized_vol"] = df["Close"].pct_change().rolling(96).std()
    df["adx"] = ta.ADX(df["High"], df["Low"], df["Close"], timeperiod=14)
    df["vwap"] = vwap_anchored_daily(df)
    ciclo = ciclo_dominante(df["Close"])
    df["ciclo_quota"] = ciclo["ciclo_quota"]
    df["ciclo_pendenza"] = ciclo["ciclo_pendenza"]
    df["atc_regime"] = canale_adattivo_regime(df)
    df["pvo_hist"] = pvo_istogramma(df["Volume"])
    return df.dropna()


# le colonne che aggiungi_indicatori crea: il collaudo le verifica una per una
COLONNE_INDICATORI = (
    "rsi", "macd", "macd_signal", "macd_hist", "ema20", "ema50", "zlema50",
    "atr", "realized_vol", "adx", "vwap",
    "ciclo_quota", "ciclo_pendenza", "atc_regime", "pvo_hist",
)
