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


def supertrend_direzione(df: pd.DataFrame, periodo_atr: int = 10,
                         moltiplicatore: float = 3.0) -> pd.Series:
    """
    Direzione del Supertrend: +1 rialzista, -1 ribassista.

    Bande a (massimo + minimo) / 2 +/- moltiplicatore x ATR. La banda
    inferiore puo' solo salire e quella superiore solo scendere, finche' la
    chiusura precedente non le attraversa. La direzione diventa rialzista
    quando la chiusura supera la banda superiore, ribassista quando scende
    sotto quella inferiore. Stessa logica di ta.supertrend di TradingView,
    che parte ribassista sulla prima barra con ATR disponibile.

    Usa solo la barra corrente e le precedenti; lo stato ha memoria dal
    primo dato. ATR di TA-Lib (media di Wilder), come l'`atr` del progetto.

    Parametri: ATR 10, moltiplicatore 3, quelli della fonte.

    Fonte: Sayedali Richu, "My Simple Formula for Filtering Intraday Buy &
    Sell Signals", 27/9/2026,
    https://medium.com/@sayedali_3166/my-simple-formula-for-filtering-intraday-buy-sell-signals-0267e115d0f5
    """
    atr = ta.ATR(df["High"], df["Low"], df["Close"], timeperiod=periodo_atr).to_numpy()
    centro = ((df["High"] + df["Low"]) / 2.0).to_numpy()
    close = df["Close"].to_numpy(dtype=float)
    stato = np.full(len(df), np.nan)
    bassa_prima = alta_prima = 0.0          # come nz() di Pine: 0 prima del primo valore
    sopra = True                            # la linea della barra prima era la banda alta?
    pronto_prima = False
    for i in range(len(df)):
        if not np.isfinite(atr[i]):
            pronto_prima = False
            continue
        bassa = centro[i] - moltiplicatore * atr[i]
        alta = centro[i] + moltiplicatore * atr[i]
        if i > 0:
            if not (bassa > bassa_prima or close[i - 1] < bassa_prima):
                bassa = bassa_prima
            if not (alta < alta_prima or close[i - 1] > alta_prima):
                alta = alta_prima
        if not pronto_prima:
            direzione = -1                  # prima barra con ATR: ribassista
        elif sopra:
            direzione = 1 if close[i] > alta else -1
        else:
            direzione = -1 if close[i] < bassa else 1
        stato[i] = direzione
        sopra = direzione == -1
        bassa_prima, alta_prima, pronto_prima = bassa, alta, True
    return pd.Series(stato, index=df.index)


def intraday_intensity(df: pd.DataFrame, barre: int = 21) -> pd.Series:
    """
    Intraday Intensity, somma sulle ultime `barre`: positiva quando, pesando
    con il volume, le chiusure stanno nella parte alta delle barre
    (pressione di acquisto), negativa quando stanno in basso.

    Per barra: (2 x chiusura - massimo - minimo) x volume / (massimo - minimo);
    se massimo = minimo il denominatore vale 1 (la barra vale zero). Poi
    somma mobile su 21 barre. E' la versione classica (David Bostian), la
    stessa dello script "INTRADAY INTENSITY INDEX" di KIVANC su TradingView
    che Mattia ha fornito l'8/10/2026. Il volume e' il tick volume di MT5.

    Fonte: Sayedali Richu, "My Simple Formula for Filtering Intraday Buy &
    Sell Signals", 27/9/2026 (URL in supertrend_direzione).
    """
    ampiezza = (df["High"] - df["Low"]).astype(float)
    per_barra = ((2.0 * df["Close"] - df["High"] - df["Low"]) * df["Volume"].astype(float)
                 / ampiezza.where(ampiezza != 0, 1.0))
    return per_barra.rolling(int(barre)).sum()


# =========================================================================
# Indicatori di regime entrati da articoli il 9/10/2026
# (metodo: 50_IDEE_DA_ARTICOLI.md)
# =========================================================================
def indice_choppiness(df: pd.DataFrame, barre: int = 14) -> pd.Series:
    """
    Choppiness Index: quanto il prezzo va a zig-zag invece di marciare.
    Da 0 (tendenza pulita) a circa 100 (movimento tutto laterale).

        CHOP = 100 x log10( somma del true range delle ultime n barre
                            / (massimo piu' alto - minimo piu' basso delle n barre) )
               / log10(n)

    Il true range e' il massimo fra: massimo - minimo, |massimo - chiusura
    precedente|, |minimo - chiusura precedente|. Se il prezzo avanza in linea
    retta la somma dei true range e' poco piu' dell'ampiezza e CHOP e' vicino
    a 0; se oscilla avanti e indietro la somma e' circa n volte l'ampiezza e
    CHOP e' vicino a 100.

    Solo somme e massimi/minimi su finestra mobile: nessun ciclo, nessuno
    smoothing. Usa la barra corrente e le n-1 precedenti. Le prime n barre
    sono NaN (il true range della prima barra manca).

    Mercato fermo (massimo = minimo su tutta la finestra): vale 100 ("tutto
    laterale") invece di NaN, perche' `aggiungi_indicatori` toglie le righe
    con un NaN e un buco nei dati sposterebbe tutte le finestre.

    Parametro: n = 14, il valore standard dell'indicatore (E. W. Dreiss). Non
    e' quello dell'articolo (7), che l'autore dichiara scelto sulla stessa
    storia che mostra.

    Fonte: PyQuantLab, "Can We Detect a Market Crash Before It Happens? I
    Tested 5 Regime Filters", 7/9/2026,
    https://pyquantlab.medium.com/can-we-detect-a-market-crash-before-it-happens-i-tested-5-regime-filters-c45290f652fa
    L'articolo lo usa insieme a un segno di momentum negativo, per segnalare
    il rischio di ribasso: qui e' la sola magnitudine, senza verso.
    """
    n = int(barre)
    chiusura_prima = df["Close"].shift(1)
    true_range = pd.concat(
        [df["High"] - df["Low"],
         (df["High"] - chiusura_prima).abs(),
         (df["Low"] - chiusura_prima).abs()],
        axis=1,
    ).max(axis=1, skipna=False)
    somma_tr = true_range.rolling(n).sum()
    ampiezza = df["High"].rolling(n).max() - df["Low"].rolling(n).min()
    rapporto = somma_tr / ampiezza.where(ampiezza > 0)
    chop = 100.0 * np.log10(rapporto) / np.log10(n)
    ferma = somma_tr.notna() & (ampiezza == 0)
    return chop.where(~ferma, 100.0)


def variance_ratio(close: pd.Series, orizzonte: int = 4, finestra: int = 192) -> pd.Series:
    """
    Variance ratio su finestra mobile: la tendenza a proseguire (sopra 1) o a
    tornare indietro (sotto 1) del prezzo, all'orizzonte scelto.

        VR = varianza dei rendimenti a `orizzonte` barre
             / (orizzonte x varianza dei rendimenti a 1 barra)

    Entrambe le varianze sono calcolate sulle ultime `finestra` barre, sui
    rendimenti logaritmici. In una passeggiata casuale vale circa 1: un
    rendimento a q barre e' la somma di q rendimenti a una barra e la
    varianza si somma. Se i rendimenti tendono a ripetersi (persistenza) le
    onde a q barre sono piu' ampie e VR sale sopra 1; se tendono a
    rimbalzare scende sotto 1.

    Solo rendimenti e varianze mobili: nessun ciclo per barra. Usa la barra
    corrente e le precedenti. Le prime `finestra` + `orizzonte` - 1 barre
    sono NaN. Prezzo fermo (varianza a 1 barra nulla): vale 1, come una
    passeggiata neutra, per non lasciare buchi (vedi indice_choppiness).

    Parametri, scelti a priori e mai provati in varianti (idea non
    dell'articolo ma proposta il 9/10/2026, in alternativa piu' leggera
    all'esponente di Hurst):
      orizzonte 4   = 1 ora su M15;
      finestra 192  = 2 giorni di contrattazione su M15. Con 192 barre lo
                      scarto tipico di VR in una passeggiata casuale e' circa
                      0,13 (formula asintotica di Lo e MacKinlay).
    I salti del weekend entrano nei rendimenti come ogni altra barra.

    Fonte: A. W. Lo e A. C. MacKinlay, "Stock Market Prices Do Not Follow
    Random Walks", Review of Financial Studies, 1988. Il tema (persistenza
    del prezzo come filtro di regime) viene da PyQuantLab, "Enhancing Trading
    Strategies With a Hurst-Based Regime Filter", 6/3/2026,
    https://pyquantlab.medium.com/enhancing-trading-strategies-with-a-hurst-based-regime-filter-ac6639be43cf
    che usa l'esponente di Hurst (R/S ricalcolato a ogni barra, piu' pesante
    e piu' rumoroso su 120 punti).
    """
    q, w = int(orizzonte), int(finestra)
    log_prezzo = np.log(close.astype(float))
    var_1 = log_prezzo.diff().rolling(w).var()
    var_q = log_prezzo.diff(q).rolling(w).var()
    vr = var_q / (q * var_1.where(var_1 > 0))
    return vr.where(~(var_1 == 0), 1.0)


# =========================================================================
# Indicatori tradotti da script TradingView (docs/51_INDICATORI_TRADINGVIEW.md)
# Traduzione riga per riga del Pine; fedelta' verificata con PineTS
# (test_indicatori_tradingview.py).
# =========================================================================
def volume_flow(df: pd.DataFrame, lunghezza: int = 130, coef: float = 0.2,
                vcoef: float = 2.5) -> pd.Series:
    """
    Volume Flow Indicator (VFI): il volume delle ultime `lunghezza` barre,
    contato col segno del movimento del prezzo tipico, diviso per il volume
    medio. Sopra zero prevale il volume che accompagna i rialzi.

    Riga per riga dallo script (smoothVFI = false, il default):
      tipico  = (H + L + C) / 3
      cutoff  = coef x dev. std. (di popolazione, come Pine) su 30 barre dei
                rendimenti log del tipico x Close
      vave    = media del volume su `lunghezza` barre, fino alla barra PRIMA
      vc      = volume, tagliato a vcoef x vave
      vcp     = +vc se il tipico sale piu' di cutoff, -vc se scende piu' di
                cutoff, altrimenti 0 (finche' cutoff non esiste vale 0, come
                in Pine dove un confronto con na e' falso)
      VFI     = somma di vcp su `lunghezza` barre / vave
    Usa solo la barra corrente e le precedenti. Riscaldamento: le prime
    2 x `lunghezza` - 1 barre sono NaN (261 con il default).
    Volume medio nullo (dati senza volume): vale 0 ("nessun flusso") invece
    di NaN, perche' `aggiungi_indicatori` toglie le righe con un NaN.

    VOLUME: dipende dalla qualita' del volume. Su MT5 (forex, CFD) e' il
    tick volume del broker, sugli exchange crypto e' volume reale: il codice
    non assume ne' l'uno ne' l'altro.

    Parametri: i default dello script (130, 0.2, 2.5), mai provati in varianti.

    Fonte: LazyBear, "Volume Flow Indicator [LazyBear]", TradingView,
    https://www.tradingview.com/script/MhlDpfdS-Volume-Flow-Indicator-LazyBear/
    Licenza: nessuna dichiarata nell'header (script open source della
    community; l'autore chiede solo una segnalazione se lo si riusa).
    L'indicatore e' di Markos Katsanos (2004).
    """
    n = int(lunghezza)
    tipico = (df["High"] + df["Low"] + df["Close"]) / 3.0
    volume = df["Volume"].astype(float)
    inter = np.log(tipico).diff()
    cutoff = coef * inter.rolling(30).std(ddof=0) * df["Close"]
    vave = volume.rolling(n).mean().shift(1)
    vmax = vave * vcoef
    vc = volume.where(volume < vmax, vmax)
    mf = tipico.diff()
    vcp = np.where(mf > cutoff, vc, np.where(mf < -cutoff, -vc, 0.0))
    # somma rifatta da capo su ogni finestra: la somma mobile di pandas
    # (aggiungi l'ultima, togli la piu' vecchia) lascia residui di 1e-16
    # dove la somma vera e' zero, e il segno di VFI deciderebbe a caso
    somma = np.full(len(vcp), np.nan)
    if len(vcp) >= n:
        somma[n - 1:] = sliding_window_view(vcp, n).sum(axis=1)
    vfi = pd.Series(somma, index=df.index) / vave.where(vave > 0)
    return vfi.where(~(vave == 0), 0.0)


def volume_relativo(volume: pd.Series, barre: int = 30) -> pd.Series:
    """
    RVOL: il volume della barra diviso per la media del volume delle `barre`
    barre PRECEDENTI (la barra corrente non entra nella media). 1 = volume
    normale, 2 = il doppio del solito.

    Riga per riga dallo script (array dei volumi da volume[1] a volume[30],
    poi rvol = volume / array.avg). Nelle prime `barre` barre lo script fa la
    media dei soli valori gia' esistenti; qui vale NaN finche' la storia non
    e' completa (le condizioni restano false). Riscaldamento: 30 barre.
    Media nulla (dati senza volume): vale 1 ("normale") invece di NaN o
    infinito, perche' `aggiungi_indicatori` toglie le righe con un NaN.

    Non e' il "Relative Volume at Time" di TradingView (che confronta la
    stessa ora dei giorni passati): non tiene conto dell'ora del giorno, quindi
    all'apertura delle sessioni il volume risulta "alto" per costruzione.
    Scelta di Mattia del 15/10/2026: il codice di ta.relativeVolume non e'
    disponibile.

    VOLUME: dipende dalla qualita' del volume. Su MT5 (forex, CFD) e' il
    tick volume del broker, sugli exchange crypto e' volume reale: il codice
    non assume ne' l'uno ne' l'altro.

    Parametro: il default dello script (30), mai provato in varianti.

    Fonte: veryfid, "Relative Volume" (RVOL), TradingView. Licenza: Mozilla
    Public License 2.0 (https://mozilla.org/MPL/2.0/), dichiarata
    nell'header: questa traduzione della riga di calcolo resta sotto MPL 2.0.
    """
    v = volume.astype(float)
    media = v.shift(1).rolling(int(barre)).mean()
    rvol = v / media.where(media > 0)
    return rvol.where(~(media == 0), 1.0)


def squeeze_momentum(df: pd.DataFrame, bb: int = 20, mult: float = 2.0,
                     kc: int = 20, mult_kc: float = 1.5) -> pd.DataFrame:
    """
    Squeeze Momentum di LazyBear: lo "squeeze" (le bande di Bollinger stanno
    dentro il canale di Keltner, cioe' la volatilita' si e' compressa) e
    l'istogramma del momentum.

    Riga per riga dallo script (useTrueRange = true, il default):
      Bollinger  media semplice di Close su `bb` barre +- mult x dev. std.
                 (di popolazione, come Pine)
      Keltner    media semplice di Close su `kc` barre +- mult_kc x media
                 semplice del true range (ta.tr: manca sulla prima barra)
      sqz_on     1 se Bollinger inferiore > Keltner inferiore E Bollinger
                 superiore < Keltner superiore, altrimenti 0
      sqz_mom    valore sulla barra corrente della retta di regressione (su
                 `kc` barre) di Close - media fra [(massimo + minimo delle
                 `kc` barre) / 2] e la media semplice di Close: e'
                 l'istogramma "a regressione lineare" di LazyBear, non il
                 momentum semplice di J. Carter.
    Colonne: sqz_on (0/1) e sqz_mom. Usa solo la barra corrente e le
    precedenti. Riscaldamento: sqz_on dalla barra `kc` (serve il true
    range), sqz_mom dalla barra 2 x `kc` - 2 (38 col default): prima NaN.

    CORREZIONE NOSTRA (docs/51 §2): nel sorgente pubblicato su TradingView la
    deviazione delle Bollinger usa il moltiplicatore del Keltner (1.5) e
    l'input "BB MultFactor" (2.0) resta inutilizzato; qui si usa `mult`, come
    nella versione aggiornata dell'autore (link pastebin nella pagina, non
    raggiungibile il 15/10/2026). E' l'unica riga diversa dallo script.

    Parametri: i default dello script (20, 2.0, 20, 1.5), mai provati in
    varianti.

    Fonte: LazyBear, "Squeeze Momentum Indicator [LazyBear]", TradingView,
    https://www.tradingview.com/script/nqQ1DT5a-Squeeze-Momentum-Indicator-LazyBear/
    Licenza: nessuna dichiarata nell'header (script open source della
    community). Idea dello squeeze: John Carter, "Mastering the Trade", TTM
    Squeeze.
    """
    close, high, low = df["Close"], df["High"], df["Low"]
    base = close.rolling(int(bb)).mean()
    dev = mult * close.rolling(int(bb)).std(ddof=0)
    bb_sup, bb_inf = base + dev, base - dev
    chiusura_prima = close.shift(1)
    true_range = pd.concat([high - low, (high - chiusura_prima).abs(),
                            (low - chiusura_prima).abs()], axis=1).max(axis=1, skipna=False)
    media_kc = close.rolling(int(kc)).mean()
    ampiezza = true_range.rolling(int(kc)).mean()
    kc_sup, kc_inf = media_kc + ampiezza * mult_kc, media_kc - ampiezza * mult_kc
    pronto = bb_inf.notna() & kc_inf.notna()
    sqz_on = ((bb_inf > kc_inf) & (bb_sup < kc_sup)).astype(float).where(pronto)
    centro = ((high.rolling(int(kc)).max() + low.rolling(int(kc)).min()) / 2 + media_kc) / 2
    sqz_mom = _fine_regressione(close - centro, int(kc))
    return pd.DataFrame({"sqz_on": sqz_on, "sqz_mom": sqz_mom}, index=df.index)


def efficienza_kaufman(close: pd.Series, barre: int = 10) -> pd.Series:
    """
    Kaufman Efficiency Ratio (KER) CON SEGNO: quanto del cammino fatto dal
    prezzo nelle ultime `barre` barre e' spostamento netto, e in che verso.

        KER = (Close - Close di `barre` barre fa)
              / somma di |Close - Close precedente| sulle ultime `barre` barre

    Da -1 (discesa in linea retta) a +1 (salita in linea retta); vicino a 0
    il prezzo va avanti e indietro. Lo script calcola il valore assoluto del
    numeratore (da 0 a 1): qui si tiene il segno, come chiede docs/51 §3 R1;
    |KER| coincide con lo script.

    Usa la barra corrente e le precedenti. Riscaldamento: le prime `barre`
    barre sono NaN. Prezzo fermo per `barre` barre (cammino nullo): vale 0
    ("nessuna efficienza") invece di NaN, perche' `aggiungi_indicatori` toglie
    le righe con un NaN. La somma del cammino e' rifatta da capo su ogni
    finestra (vedi volume_flow): niente residui di 1e-16 vicino alle soglie.

    Parametro: il default dello script (10, il valore di Kaufman), mai
    provato in varianti.

    Fonte: Zorba_the_Buddha, "Kaufman Efficiency Ratio (KER)", TradingView,
    30/10/2023, https://www.tradingview.com/script/7imltc5K-Kaufman-Efficiency-Ratio-KER/
    Licenza: "open-source script" secondo le regole di TradingView, nessuna
    licenza specifica dichiarata. Indicatore di Perry Kaufman ("Smarter
    Trading", 1995).
    """
    n = int(barre)
    c = close.to_numpy(dtype=float)
    passi = np.abs(np.diff(c, prepend=np.nan))
    cammino = np.full(len(c), np.nan)
    if len(c) > n:
        cammino[n:] = sliding_window_view(passi[1:], n).sum(axis=1)
    netto = close - close.shift(n)
    cammino = pd.Series(cammino, index=close.index)
    ker = netto / cammino.where(cammino > 0)
    return ker.where(~(cammino == 0), 0.0)


def _ema_pine(serie: pd.Series, barre: int) -> pd.Series:
    """
    Media esponenziale come `ta.ema` di Pine: alpha = 2 / (barre + 1), il
    primo valore e' la media semplice delle prime `barre` barre valide (prima
    e' NaN), poi la ricorsione. Diversa da `ewm(span=...)` di pandas, che
    parte dal primo valore. I NaN iniziali della serie (riscaldamento di un
    indicatore a monte) si saltano; la serie non deve avere NaN dopo.
    """
    n = int(barre)
    v = serie.to_numpy(dtype=float)
    esito = np.full(len(v), np.nan)
    valide = np.flatnonzero(np.isfinite(v))
    if len(valide) >= n:
        inizio = valide[0] + n - 1
        semi = v[inizio:].copy()
        semi[0] = v[valide[0]:inizio + 1].mean()
        esito[inizio:] = pd.Series(semi).ewm(alpha=2.0 / (n + 1), adjust=False).mean().to_numpy()
    return pd.Series(esito, index=serie.index)


def wavetrend(df: pd.DataFrame, canale: int = 10, media: int = 21) -> pd.DataFrame:
    """
    WaveTrend Oscillator di LazyBear: un CCI lisciato sul prezzo tipico.

    Riga per riga dallo script:
      ap   = (H + L + C) / 3
      esa  = ema(ap, canale)
      d    = ema(|ap - esa|, canale)
      ci   = (ap - esa) / (0.015 x d)
      wt1  = ema(ci, media)
      wt2  = media semplice di wt1 su 4 barre
    con le ema di Pine (`_ema_pine`: partono dalla media semplice). Colonne
    wt1 e wt2. Usa solo la barra corrente e le precedenti. Riscaldamento:
    wt1 dalla barra 2 x `canale` + `media` - 3 (38 col default), wt2 tre barre
    dopo (41). Le ema sono ricorsive: il valore dipende un poco dal punto di
    partenza dei dati, con un peso che si dimezza ogni ~7 barre (media 21),
    quindi dopo qualche centinaio di barre la differenza e' sotto 1e-9.
    Prezzo fermo (d = 0): ci vale 0 invece di NaN/inf.

    Parametri: i default dello script (10, 21), mai provati in varianti. Le
    soglie dello script (+-60, +-53) NON si usano: le condizioni usano un
    percentile rolling (docs/50 §5, scelta di Mattia del 15/10/2026).

    Fonte: LazyBear, "WaveTrend Oscillator [WT]", TradingView,
    https://www.tradingview.com/script/2KE8wTuF-Indicator-WaveTrend-Oscillator-WT/
    Licenza: nessuna dichiarata nell'header (script open source della
    community; l'autore chiede solo una segnalazione se lo si riusa).
    """
    ap = (df["High"] + df["Low"] + df["Close"]) / 3.0
    esa = _ema_pine(ap, canale)
    d = _ema_pine((ap - esa).abs(), canale)
    ci = ((ap - esa) / (0.015 * d.where(d > 0))).where(~(d == 0), 0.0)
    wt1 = _ema_pine(ci, media)
    wt2 = wt1.rolling(4).mean()
    return pd.DataFrame({"wt1": wt1, "wt2": wt2}, index=df.index)


def aggiungi_indicatori(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggiunge al DataFrame di mercato le colonne usate dalle condizioni:

        rsi, macd, macd_signal, macd_hist, ema20, ema50, zlema50,
        atr, realized_vol, adx, vwap,
        ciclo_quota, ciclo_pendenza, atc_regime, pvo_hist, st_dir, iix,
        chop, vr, vfi, rvol, sqz_on, sqz_mom, wt1, wt2, ker
        (docs/51: riscaldamento V1 261 barre, V2 30, M1 38, M2 41, R1 10)

    Le ultime sei vengono da articoli (7-8/10/2026): vedi le funzioni
    ciclo_dominante, canale_adattivo_regime, pvo_istogramma,
    supertrend_direzione e intraday_intensity qui sopra. Il
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
    df["st_dir"] = supertrend_direzione(df)
    df["iix"] = intraday_intensity(df)
    df["chop"] = indice_choppiness(df)
    df["vr"] = variance_ratio(df["Close"])
    df["vfi"] = volume_flow(df)
    df["rvol"] = volume_relativo(df["Volume"])
    squeeze = squeeze_momentum(df)
    df["sqz_on"] = squeeze["sqz_on"]
    df["sqz_mom"] = squeeze["sqz_mom"]
    df["ker"] = efficienza_kaufman(df["Close"])
    onda = wavetrend(df)
    df["wt1"] = onda["wt1"]
    df["wt2"] = onda["wt2"]
    return df.dropna()


# le colonne che aggiungi_indicatori crea: il collaudo le verifica una per una
COLONNE_INDICATORI = (
    "rsi", "macd", "macd_signal", "macd_hist", "ema20", "ema50", "zlema50",
    "atr", "realized_vol", "adx", "vwap",
    "ciclo_quota", "ciclo_pendenza", "atc_regime", "pvo_hist", "st_dir", "iix",
    "chop", "vr", "vfi", "rvol", "sqz_on", "sqz_mom", "wt1", "wt2", "ker",
)
