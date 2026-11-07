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


def hurst_rs(close: pd.Series, barre: int = 100, lisciatura: int = 5) -> pd.Series:
    """
    Esponente di Hurst con la stima R/S semplificata dello script PhenLabs,
    lisciato con una ema di Pine. Sopra 0,5 i movimenti tendono a proseguire,
    sotto 0,5 a rientrare, 0,5 = cammino casuale.

    Riga per riga dallo script, a ogni barra:
      r      = log(Close / Close precedente) (0 sulla prima barra)
      finestra = gli ultimi `barre` rendimenti (barra corrente compresa)
      S      = deviazione standard (di popolazione, array.stdev di Pine)
      profilo = somme cumulate degli scarti dalla media, dal piu' vecchio
      R      = massimo - minimo del profilo
      H      = log(R / S) / log(`barre`)  (0,5 se S o R/S <= 1e-9)
      hurst  = ema di Pine (`_ema_pine`) di H su `lisciatura` barre
    Usa solo la barra corrente e le precedenti. Riscaldamento: H dalla barra
    `barre` - 1, hurst dalla barra `barre` + `lisciatura` - 2 (103 col
    default). Il primo rendimento (0) entra nella prima finestra come nello
    script.

    LIMITI DELLA STIMA (docs/51 §3 R2): log(R/S)/log(n) su una sola finestra
    e' distorta verso l'alto su finestre corte: su un cammino casuale con
    n = 100 vale in media circa 0,55-0,6 invece di 0,5 (correzione di
    Anis-Lloyd, non applicata dallo script). Sotto ~100 barre la stima e'
    poco affidabile. Le soglie dello script (0,6 e 0,4) non tengono conto di
    questa distorsione: si usano comunque come dichiarate.

    Parametri: i default dello script (100, 5), mai provati in varianti.

    Fonte: PhenLabs, "Hurst Exponent Oscillator [PhenLabs]", TradingView.
    LICENZA: CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/),
    dichiarata nell'header: NON COMMERCIALE. Tradotta per uso personale e di
    ricerca, scelta di Mattia del 13/10/2026; questa funzione resta sotto la
    stessa licenza (attribuzione a PhenLabs, non commerciale, stessa licenza).
    """
    n = int(barre)
    c = close.to_numpy(dtype=float)
    r = np.zeros(len(c))
    if len(c) > 1:
        prima = c[:-1]
        ok = np.isfinite(prima) & (prima > 0) & (c[1:] > 0)
        r[1:] = np.where(ok, np.log(np.where(ok, c[1:] / np.where(ok, prima, 1.0), 1.0)), 0.0)
    h = np.full(len(c), np.nan)
    blocco = 20000                                   # finestre per volta (memoria)
    for inizio in range(n - 1, len(c), blocco):
        fine = min(inizio + blocco, len(c))
        w = sliding_window_view(r[inizio - n + 1:fine], n)      # una riga per barra
        s = w.std(axis=1)
        profilo = np.cumsum(w - w.mean(axis=1, keepdims=True), axis=1)
        ampiezza = profilo.max(axis=1) - profilo.min(axis=1)
        rs = ampiezza / np.where(s > 1e-9, s, 1.0)
        valido = (s > 1e-9) & (rs > 1e-9)
        h[inizio:fine] = np.where(valido, np.log(np.where(valido, rs, 1.0)) / np.log(n), 0.5)
    h = pd.Series(h, index=close.index)
    return _ema_pine(h, lisciatura) if int(lisciatura) > 1 else h


def _rma_pine(serie: pd.Series, barre: int) -> pd.Series:
    """
    Media di Wilder come `ta.rma` di Pine: alpha = 1 / barre, il primo valore
    e' la media semplice delle prime `barre` barre valide (prima NaN), poi la
    ricorsione. Stessa partenza di `_ema_pine`, cambia solo alpha.
    """
    n = int(barre)
    v = serie.to_numpy(dtype=float)
    esito = np.full(len(v), np.nan)
    valide = np.flatnonzero(np.isfinite(v))
    if len(valide) >= n:
        inizio = valide[0] + n - 1
        semi = v[inizio:].copy()
        semi[0] = v[valide[0]:inizio + 1].mean()
        esito[inizio:] = pd.Series(semi).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()
    return pd.Series(esito, index=serie.index)


def _atr_pine(df: pd.DataFrame, barre: int) -> pd.Series:
    """`ta.atr` di Pine: rma del true range, con ta.tr(true) (sulla prima barra massimo - minimo)."""
    chiusura_prima = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - chiusura_prima).abs(),
                    (df["Low"] - chiusura_prima).abs()], axis=1).max(axis=1)   # skipna: prima barra H - L
    return _rma_pine(tr, barre)


def filtri_jdehorty(df: pd.DataFrame, atr_breve: int = 1, atr_lungo: int = 10) -> pd.DataFrame:
    """
    Le grandezze dei due filtri `filter_volatility` e `regime_filter` della
    libreria MLExtensions di jdehorty (usati da "Machine Learning: Lorentzian
    Classification"). Il classificatore e `filter_adx` NON sono tradotti
    (docs/51 §3 R3: l'ADX e' gia' nel progetto).

    Colonne:
      jdh_atr_diff  ta.atr(1) - ta.atr(10): sopra zero la volatilita' recente
                    supera quella storica (filter_volatility: recentAtr >
                    historicalAtr). ATR di Pine: rma del true range, che parte
                    dalla media semplice; dalla barra `atr_lungo` - 1.
      jdh_regime    "normalized_slope_decline" di regime_filter, sul prezzo
                    ohlc4, riga per riga:
                      value1 = 0,2 x (src - src prec.) + 0,8 x value1 prec.
                      value2 = 0,1 x (massimo - minimo) + 0,8 x value2 prec.
                      omega  = |value1 / value2|
                      alpha  = (-omega^2 + sqrt(omega^4 + 16 omega^2)) / 8
                      klmf   = alpha x src + (1 - alpha) x klmf prec.
                      pend.  = |klmf - klmf prec.|
                      jdh_regime = (pend. - ema200(pend.)) / ema200(pend.)
                    con nz() di Pine (il valore precedente mancante vale 0:
                    klmf parte da zero e sale verso il prezzo) e la ema di
                    Pine (`_ema_pine`). Dalla barra 201.
    Usa solo la barra corrente e le precedenti. Le ricorsioni dipendono dal
    punto di partenza dei dati, con un peso che si dimezza ogni ~70 barre
    (ema a 200): dopo ~3000 barre la differenza e' sotto 1e-9. Attenzione:
    il salto iniziale di klmf (da 0 al prezzo, come nello script) entra nella
    ema a 200 e tiene jdh_regime artificialmente basso per ~1000 barre
    dall'inizio dei dati (taglio di riscaldamento dei motori: da verificare).
    Prezzo fermo (ema della pendenza nulla): jdh_regime vale 0 invece di NaN.

    Parametri: i default usati dallo script Lorentzian (1, 10; ema 200 fissa
    nella libreria), mai provati in varianti.

    Fonte: jdehorty, libreria "MLExtensions" e indicatore "Machine Learning:
    Lorentzian Classification", TradingView. Licenza: Mozilla Public License
    2.0 (https://mozilla.org/MPL/2.0/): questa traduzione resta sotto MPL 2.0.
    """
    atr_diff = _atr_pine(df, atr_breve) - _atr_pine(df, atr_lungo)
    src = ((df["Open"] + df["High"] + df["Low"] + df["Close"]) / 4.0).to_numpy(dtype=float)
    ampiezza = (df["High"] - df["Low"]).to_numpy(dtype=float)
    n = len(src)
    klmf = np.full(n, np.nan)
    v1 = v2 = k = np.nan
    for i in range(n):
        v1 = 0.2 * (src[i] - (src[i - 1] if i > 0 else np.nan)) + 0.8 * (0.0 if np.isnan(v1) else v1)
        v2 = 0.1 * ampiezza[i] + 0.8 * (0.0 if np.isnan(v2) else v2)
        with np.errstate(divide="ignore", invalid="ignore"):
            omega = abs(v1 / v2)
        alpha = (-omega ** 2 + np.sqrt(omega ** 4 + 16 * omega ** 2)) / 8
        k = alpha * src[i] + (1 - alpha) * (0.0 if np.isnan(k) else k)
        klmf[i] = k
    klmf = pd.Series(klmf, index=df.index)
    pendenza = (klmf - klmf.shift(1)).abs()
    media = _ema_pine(pendenza, 200)
    regime = (pendenza - media) / media.where(media > 0)
    regime = regime.where(~(media == 0), 0.0)
    return pd.DataFrame({"jdh_atr_diff": atr_diff, "jdh_regime": regime}, index=df.index)


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


def _sentiment_per_giorno(df: pd.DataFrame, giorni_media: int = 30,
                          giorni_percentile: int = 365) -> pd.DataFrame:
    """
    Il cuore di `sentiment_giornaliero`: una riga per giornata FX presente
    nello storico (indice = numero progressivo di `giorno_fx`), con le
    quattro componenti, il punteggio e la classe CALCOLATI A FINE GIORNATA.
    Le giornate senza barre utili, o con un rendimento non calcolabile,
    hanno NaN e non entrano nelle finestre (che contano solo giornate valide).
    """
    from engine.livelli import giorno_fx, quarantena_cached

    giorno = giorno_fx(df).to_numpy()
    utile = ~quarantena_cached(df)["totale"].reindex(df.index).fillna(False).to_numpy(dtype=bool)
    g, close = giorno[utile], df["Close"].to_numpy(dtype=float)[utile]
    # rendimenti fra barre UTILI consecutive della stessa giornata: il primo di
    # ogni giornata (scavalca il confine) e quelli che partirebbero da una barra
    # in quarantena non esistono
    rend = np.full(len(close), np.nan)
    if len(close) > 1:
        with np.errstate(divide="ignore", invalid="ignore"):
            rend[1:] = np.where(g[1:] == g[:-1], np.log(close[1:] / close[:-1]), np.nan)
    barre = pd.DataFrame({"g": g, "close": close, "rend": rend,
                          "volume": df["Volume"].to_numpy(dtype=float)[utile]})
    per_g = barre.groupby("g").agg(close=("close", "last"), vol=("rend", "std"),
                                   volume=("volume", "mean"))
    per_g = per_g.reindex(np.arange(int(giorno.max()) + 1 if len(giorno) else 0))

    m, p = int(giorni_media), int(giorni_percentile)
    valide = per_g.dropna().copy()
    valide = valide[(valide["close"] > 0) & (valide["volume"] > 0)]
    rend_g = np.log(valide["close"] / valide["close"].shift(1))
    # 1 volatilita' del giorno rispetto alla sua media a `m` giorni (alta = paura)
    v1 = valide["vol"] / valide["vol"].rolling(m).mean()
    # 2 distanza dal massimo delle chiusure degli ultimi `m` giorni (profonda = paura)
    v2 = valide["close"] / valide["close"].rolling(m).max() - 1.0
    # 3 chiusura rispetto alla media delle chiusure a `m` giorni (sotto = paura)
    v3 = valide["close"] / valide["close"].rolling(m).mean() - 1.0
    # 4 volume medio per barra del giorno / media a `m` giorni, col segno del
    #   rendimento del giorno (volume alto in calo = paura, in salita = avidita')
    v4 = np.sign(rend_g) * valide["volume"] / valide["volume"].rolling(m).mean()

    def _pct(s: pd.Series) -> pd.Series:
        # percentile sui soli giorni con il valore (i primi `m` non ce l'hanno)
        s = s.dropna()
        return s.rolling(p).rank(pct=True).reindex(valide.index)

    comp = pd.DataFrame({"sent_volatilita": 1.0 - _pct(v1), "sent_drawdown": _pct(v2),
                         "sent_momentum": _pct(v3), "sent_volume": _pct(v4)})
    # 1 - rank: il valore piu' alto della finestra (rank 1) diventa 0, il piu'
    # basso (1/p) diventa 1 - 1/p: scala (0, 1] rovesciata in [0, 1), voluta
    punteggio = 100.0 * comp.mean(axis=1, skipna=False)
    rango = punteggio.dropna().rolling(p).rank(pct=True).reindex(valide.index)
    classe = pd.Series(np.select([rango <= 0.2, rango <= 0.4, rango <= 0.6, rango <= 0.8, rango <= 1.0],
                                 [1.0, 2.0, 3.0, 4.0, 5.0], default=np.nan), index=valide.index)
    esito = comp.assign(sentiment_score=punteggio, sentiment_classe=classe)
    return esito.reindex(per_g.index)


def sentiment_giornaliero(df: pd.DataFrame, giorni_media: int = 30,
                          giorni_percentile: int = 365) -> pd.DataFrame:
    """
    Indice di sentiment "paura / avidita'" costruito SOLO dalle barre del
    symbol (prezzo e tick volume), aggiornato una volta al giorno.

    Per ogni giornata FX (da rollover a rollover, 17:00 New York, `giorno_fx`),
    a fine giornata, quattro componenti, ciascuna trasformata nel suo
    percentile sugli ultimi `giorni_percentile` giorni (0 = paura, 1 = avidita'):

      1 volatilita'   deviazione standard dei rendimenti M15 del giorno, divisa
                      per la sua media a `giorni_media` giorni; ROVESCIATA
                      (volatilita' alta = paura)
      2 drawdown      chiusura del giorno / massimo delle chiusure degli ultimi
                      `giorni_media` giorni - 1 (lontano dai massimi = paura)
      3 momentum      chiusura del giorno / media delle chiusure a
                      `giorni_media` giorni - 1 (sotto la media = paura)
      4 volume        tick volume medio per barra del giorno / sua media a
                      `giorni_media` giorni, col segno del rendimento del
                      giorno (volume alto in calo = paura, in salita = avidita')

      sentiment_score   media delle quattro, x 100: da 0 (paura) a 100 (avidita')
      sentiment_classe  percentile del punteggio sugli ultimi `giorni_percentile`
                        giorni, in 5 quintili: 1 paura estrema (fino al 20%),
                        2 paura, 3 neutro, 4 avidita', 5 avidita' estrema (oltre l'80%)

    COSA VEDE UNA BARRA: i valori della giornata FX gia' CHIUSA piu' recente.
    Dentro la giornata in corso il valore resta fermo (quello di ieri), e
    cambia solo sulla prima barra della giornata successiva. Nessun valore
    "di oggi" e' usato durante oggi.

    Dettagli:
    - Le barre in quarantena (rollover, prima barra dopo una pausa) non
      entrano nei valori, come in `range_finestra`; il confine della giornata
      viene dal calendario puro.
    - Si usa il volume MEDIO per barra e la deviazione standard per barra:
      una giornata corta (festivo, apertura della domenica) non sembra una
      giornata "a volume basso". La volatilita' usa i rendimenti fra barre
      utili consecutive della stessa giornata: il primo di ogni giornata
      (scavalca il confine) e quelli che partono da una barra in quarantena
      sono esclusi. Cambiare prezzi o volumi delle barre in quarantena non
      cambia nulla.
    - I giorni sono giornate di contrattazione presenti nei dati, non giorni
      di calendario: su BTCUSD (7 su 7) 365 giornate sono un anno, sul forex
      (5 su 7) circa 17 mesi.
    - Componenti a pesi uguali (25% ciascuna), mai ottimizzati.
    - Riscaldamento: `giorni_media` + 2 x `giorni_percentile` giornate circa
      (~760 col default, piu' una giornata per il rendimento): prima e' NaN.

    Parametri fissati a priori (scheda approvata da Mattia il 15/10/2026), mai
    provati in varianti.

    Fonte dell'IDEA: Crypto Fear & Greed Index di alternative.me,
    https://alternative.me/crypto/fear-and-greed-index/ (letto il 15/10/2026).
    Delle sue sei componenti si riprendono, con formula nostra, solo le due
    calcolabili dai prezzi (volatilita'/drawdown, momentum/volume); social,
    sondaggi, dominance e Google Trends restano fuori (dati che non abbiamo).
    Formula, dati e nome di alternative.me NON sono usati: codice scritto da
    zero, nessuna licenza di terzi.
    """
    per_g = _sentiment_per_giorno(df, giorni_media, giorni_percentile)
    from engine.livelli import giorno_fx
    ieri = giorno_fx(df).to_numpy() - 1                  # l'ultima giornata chiusa
    colonne = ["sentiment_score", "sentiment_classe"]
    valori = np.full((len(df), len(colonne)), np.nan)
    ok = ieri >= 0
    valori[ok] = per_g[colonne].to_numpy()[ieri[ok]]
    return pd.DataFrame(valori, index=df.index, columns=colonne)


# =========================================================================
# Multi timeframe (docs/50 §10, riga 12; schede approvate da Mattia il
# 15/10/2026): candele superiori costruite dalle M15, e le colonne di
# F37 (continuita' dei timeframe), E31 (Triple Screen), F38 (accordo di tre
# orizzonti), F39 (giorno inside).
# =========================================================================

REGOLE_PERIODO = ("H1", "H4", "D", "W", "M")


def id_periodo(df: pd.DataFrame, regola: str) -> np.ndarray:
    """
    Numero progressivo del periodo superiore di ogni barra (0, 1, 2, ...):
    cresce di uno a ogni periodo nuovo PRESENTE nei dati (un periodo senza
    barre, es. il weekend, non ha numero).

        H1  l'ora (i confini orari coincidono in UTC e a New York)
        H4  blocchi di 4 ore ancorati al rollover delle 17:00 di New York:
            17, 21, 01, 05, 09, 13 (ora di New York, con l'ora legale)
        D   la giornata FX (17:00 NY -> 17:00 NY): identica a giorno_fx
        W   la settimana FX: inizia domenica alle 17:00 NY (giornata FX del lunedi')
        M   il mese della data FX

    Sui symbol da exchange (livelli.GIORNATA_UTC, 20/10/2026, docs/63 §10.1
    punto 3) gli stessi periodi partono dalla mezzanotte UTC, come le candele
    degli exchange: H4 alle 0, 4, 8, 12, 16, 20 UTC, D da 00:00 a 00:00 UTC,
    W dal lunedi' alle 00:00 UTC, M il mese UTC.

    Serve l'indice con fuso orario. I confini vengono dal calendario puro,
    senza quarantena (come range_finestra).
    """
    from engine.livelli import GIORNATA_UTC, giornata_attiva

    idx = pd.DatetimeIndex(df.index)
    if regola == "H1":
        chiave = idx.floor("h").asi8
    else:
        if giornata_attiva() == GIORNATA_UTC:
            loc = idx.tz_convert("UTC").tz_localize(None)
        else:
            # +7 ore all'ora DA OROLOGIO di New York: le 17:00 diventano la mezzanotte
            # della data FX. Si somma all'ora locale senza fuso: sommando a un orario
            # con fuso, la notte del cambio d'ora i blocchi H4 si spostavano di un'ora
            # (la data FX resta la stessa di giorno_fx: il cambio d'ora e' alle 2:00)
            loc = idx.tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)
        # giorni dal 1/1/1970 della data FX (conversione esplicita: l'unita'
        # interna delle date cambia fra pandas 2 e 3)
        giorni = loc.to_numpy().astype("datetime64[D]").astype(np.int64)
        if regola == "H4":
            chiave = giorni * 6 + loc.hour // 4
        elif regola == "D":
            chiave = giorni
        elif regola == "W":
            chiave = giorni - (giorni + 3) % 7          # il lunedi' FX della settimana (1/1/1970 = giovedi')
        elif regola == "M":
            chiave = loc.year.to_numpy() * 12 + loc.month.to_numpy()
        else:
            raise ValueError(f"regola {regola!r} sconosciuta: usa una di {REGOLE_PERIODO}")
    chiave = np.asarray(chiave)
    nuovo = np.ones(len(chiave), dtype=np.int64)
    nuovo[1:] = chiave[1:] != chiave[:-1]
    return np.cumsum(nuovo) - 1


def barre_superiori(df: pd.DataFrame, regola: str) -> tuple[pd.DataFrame, np.ndarray]:
    """
    Le candele del timeframe superiore `regola` (vedi id_periodo), costruite
    dalle barre M15 NON in quarantena: Open della prima barra utile, High e Low
    estremi, Close dell'ultima, Volume (tick) sommato. Un periodo senza barre
    utili ha NaN.

    Restituisce (candele indicizzate dal numero del periodo, numero del
    periodo di ogni barra M15). Per leggere una candela da una barra M15 usa
    `al_periodo_chiuso`: SOLO l'ultimo periodo gia' chiuso.
    """
    from engine.livelli import quarantena_cached

    pid = id_periodo(df, regola)
    utile = ~quarantena_cached(df)["totale"].reindex(df.index).fillna(False).to_numpy(dtype=bool)
    # 20/10/2026: Volume solo se c'e' (l'ATR delle unita' di docs/63 §4 gira anche su dati senza)
    colonne = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
    b = pd.DataFrame({c: df[c].to_numpy(dtype=float)[utile] for c in colonne})
    b["pid"] = pid[utile]
    regole = dict(Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"),
                  Close=("Close", "last"), Volume=("Volume", "sum"))
    candele = b.groupby("pid").agg(**{c: regole[c] for c in colonne})
    n = int(pid[-1]) + 1 if len(pid) else 0
    return candele.reindex(np.arange(n)), pid


def al_periodo_chiuso(pid: np.ndarray, valori, indice) -> pd.Series:
    """
    Porta su ogni barra M15 il valore del periodo superiore PRECEDENTE al suo
    (pid - 1): l'ultimo gia' chiuso. Una candela superiore diventa visibile
    dalla prima barra M15 del periodo dopo, mai prima (stessa regola di F36:
    al massimo una barra di ritardo, nessun dato del periodo in corso).
    """
    v = np.asarray(valori, dtype=float)
    esito = np.full(len(pid), np.nan)
    ok = pid >= 1
    esito[ok] = v[pid[ok] - 1]
    return pd.Series(esito, index=indice)


def atr_giornaliero_chiuso(df: pd.DataFrame, giorni: int = 5) -> pd.Series:
    """
    ATR giornaliero per il modello a volatilita' del money management
    (16/10/2026, docs/61 §14; Unger, cap. 4.5, p. 81-84): media SEMPLICE del
    true range delle ultime `giorni` giornate FX chiuse (come nel libro; non
    la media di Wilder di TA-Lib).

        true range = max(massimo, chiusura del giorno prima)
                     - min(minimo, chiusura del giorno prima)
        (il primo giorno dei dati: massimo - minimo)

    Giornate FX e candele di `barre_superiori` (17:00 New York, senza le barre
    in quarantena; sui symbol da exchange 00:00 UTC, livelli.GIORNATA_UTC);
    su ogni barra M15 il valore dell'ultima giornata chiusa
    (`al_periodo_chiuso`): la giornata in corso non entra mai.

    Non e' in aggiungi_indicatori: le colonne del catalogo non cambiano. Lo
    chiama engine/mm_adattatore.py. In unita' di prezzo.
    """
    g, pid = barre_superiori(df, "D")
    prima = g["Close"].shift(1)
    tr = (np.maximum(g["High"], prima) - np.minimum(g["Low"], prima)).where(prima.notna(),
                                                                           g["High"] - g["Low"])
    atr = tr.rolling(int(giorni), min_periods=int(giorni)).mean()
    return al_periodo_chiuso(pid, atr.to_numpy(), df.index)


def _apertura_periodo_in_corso(df: pd.DataFrame, regola: str) -> pd.Series:
    """
    Apertura del periodo IN CORSO nota alla barra: l'Open della prima barra
    utile del periodo, da quella barra in poi (NaN sulle barre in quarantena
    che la precedono: a quel punto l'apertura non si conosce ancora).
    """
    from engine.livelli import quarantena_cached

    pid = id_periodo(df, regola)
    utile = ~quarantena_cached(df)["totale"].reindex(df.index).fillna(False).to_numpy(dtype=bool)
    utili_prima = pd.Series(utile.astype(int)).groupby(pid).cumsum().to_numpy()
    prima = utile & (utili_prima == 1)
    aperture = pd.Series(np.where(prima, df["Open"].to_numpy(dtype=float), np.nan))
    return pd.Series(aperture.groupby(pid).ffill().to_numpy(), index=df.index)


def continuita_timeframe(df: pd.DataFrame, periodi=("H1", "D", "W", "M")) -> pd.Series:
    """
    "Full timeframe continuity" (The Strat): +1 se la chiusura della barra e'
    SOPRA l'apertura del periodo in corso di tutti i `periodi` (ora, giornata
    FX, settimana FX, mese), -1 se e' SOTTO tutte, 0 altrimenti; NaN finche'
    un'apertura non e' nota.

    Usa il periodo IN CORSO, non quello chiuso: e' causale, perche'
    l'apertura si conosce dalla prima barra del periodo (eccezione voluta alla
    regola "solo candela chiusa", scheda B).

    Parametri: i quattro periodi indicati dalla fonte come i piu' comuni,
    nessuna soglia. Fonte: LuxAlgo, "The Strat" (concetto di Rob Smith),
    https://www.luxalgo.com/library/concept/the-strat/ (letto il 15/10/2026).
    """
    close = df["Close"].to_numpy(dtype=float)
    aperture = np.vstack([_apertura_periodo_in_corso(df, r).to_numpy() for r in periodi])
    nota = ~np.isnan(aperture).any(axis=0)
    sopra = (close > aperture).all(axis=0)
    sotto = (close < aperture).all(axis=0)
    esito = np.where(sopra, 1.0, np.where(sotto, -1.0, 0.0))
    return pd.Series(np.where(nota, esito, np.nan), index=df.index)


def triple_screen_colonne(df: pd.DataFrame) -> pd.DataFrame:
    """
    Le grandezze del Triple Screen di Elder, sul timeframe superiore e lette
    SOLO dall'ultima candela chiusa (al_periodo_chiuso):

      mtf_h4_macdh_pend  schermo 1: pendenza del MACD-Histogram (12/26/9)
                         sulle H4: +1 se l'ultima barra e' piu' alta della
                         precedente, -1 se piu' bassa, 0 se uguali
      mtf_h1_force       schermo 2: Force Index sulle H1, (Close - Close
                         precedente) x tick volume, lisciato con EMA a 2 periodi
      mtf_h1_high        schermo 3: massimo e minimo dell'ultima H1 chiusa
      mtf_h1_low

    Timeframe: H4 / H1 per l'ingresso su M15 (fattore 4, vicino al "fattore
    5" del libro); oscillatore Force Index (l'esempio guidato del libro);
    scelte di Mattia del 15/10/2026. Parametri del libro, mai provati in varianti.

    Fonte: A. Elder, "Trading for a Living", Wiley 1993, cap. 43 (Triple
    Screen, pp. 235-243), cap. 42 (Force Index), cap. 26 (MACD-Histogram).
    """
    h4, pid4 = barre_superiori(df, "H4")
    c4 = h4["Close"].dropna()
    pend = pd.Series(np.nan, index=h4.index)
    if len(c4) > 34:
        _, _, istogramma = ta.MACD(c4.to_numpy(dtype=float), fastperiod=12, slowperiod=26, signalperiod=9)
        pend.loc[c4.index] = np.sign(pd.Series(istogramma).diff().to_numpy())
    h1, pid1 = barre_superiori(df, "H1")
    v1 = h1.dropna(subset=["Close"])
    forza_grezza = (v1["Close"] - v1["Close"].shift(1)) * v1["Volume"]
    forza = forza_grezza.ewm(span=2, adjust=False).mean().reindex(h1.index)
    return pd.DataFrame({
        "mtf_h4_macdh_pend": al_periodo_chiuso(pid4, pend.to_numpy(), df.index),
        "mtf_h1_force": al_periodo_chiuso(pid1, forza.to_numpy(), df.index),
        "mtf_h1_high": al_periodo_chiuso(pid1, h1["High"].to_numpy(), df.index),
        "mtf_h1_low": al_periodo_chiuso(pid1, h1["Low"].to_numpy(), df.index),
    }, index=df.index)


def accordo_orizzonti(df: pd.DataFrame, orizzonti=(1, 5, 21)) -> pd.Series:
    """
    Accordo di tre orizzonti (time-series momentum): sull'ultima giornata FX
    CHIUSA, +1 se il rendimento dalla chiusura di 1, 5 e 21 giornate prima e'
    positivo su tutti e tre, -1 se negativo su tutti e tre, 0 altrimenti.
    Le giornate sono quelle presenti nei dati (chiusura dell'ultima barra
    utile); ogni barra vede la giornata g-1, come F36.

    Traduzione nostra (approvata da Mattia il 15/10/2026): la fonte usa 1, 3
    e 12 MESI su dati mensili e somma le tre posizioni; qui giornate (giorno,
    settimana, mese) e "tutti e tre d'accordo".

    Fonte: Hurst, Ooi, Pedersen, "A Century of Evidence on Trend-Following
    Investing", J. of Portfolio Management, autunno 2017, sezione
    "Constructing the time-series momentum strategy".
    """
    giorni, pid = barre_superiori(df, "D")
    c = giorni["Close"].dropna()
    c = c[c > 0]
    segni = np.vstack([np.sign((c / c.shift(k) - 1.0).to_numpy()) for k in orizzonti])
    definito = ~np.isnan(segni).any(axis=0)
    esito = np.where((segni > 0).all(axis=0), 1.0, np.where((segni < 0).all(axis=0), -1.0, 0.0))
    per_g = pd.Series(np.where(definito, esito, np.nan), index=c.index).reindex(giorni.index)
    return al_periodo_chiuso(pid, per_g.to_numpy(), df.index)


def giorno_inside(df: pd.DataFrame) -> pd.Series:
    """
    1 se l'ultima giornata FX CHIUSA e' "inside" rispetto a quella prima
    (massimo <= massimo precedente e minimo >= minimo precedente, barre in
    quarantena escluse: barra di "tipo 1" della Strat), 0 altrimenti, NaN se
    manca una delle due giornate. Il valore vale per tutta la giornata dopo.

    Fonte: LuxAlgo, "The Strat", https://www.luxalgo.com/library/concept/the-strat/
    """
    giorni, pid = barre_superiori(df, "D")
    v = giorni.dropna(subset=["High", "Low"])
    dentro = ((v["High"] <= v["High"].shift(1)) & (v["Low"] >= v["Low"].shift(1))).astype(float)
    dentro.iloc[:1] = np.nan
    return al_periodo_chiuso(pid, dentro.reindex(giorni.index).to_numpy(), df.index)


COLONNE_MULTI_TIMEFRAME = ("ftfc", "mtf_h4_macdh_pend", "mtf_h1_force", "mtf_h1_high",
                           "mtf_h1_low", "tsmom", "inside_day")


def colonne_multi_timeframe(df: pd.DataFrame) -> pd.DataFrame:
    """Le sette colonne multi timeframe (vedi le funzioni qui sopra), in un DataFrame."""
    esito = triple_screen_colonne(df)
    esito.insert(0, "ftfc", continuita_timeframe(df))
    esito["tsmom"] = accordo_orizzonti(df)
    esito["inside_day"] = giorno_inside(df)
    return esito[list(COLONNE_MULTI_TIMEFRAME)]


# ---------------------------------------------------------------------------
# Momentum intraday (docs/50 §10, riga 15; scheda approvata da Mattia il
# 18/10/2026, con gli orari del paper)
# ---------------------------------------------------------------------------

# gli orari di Shen, Urquhart, Wang (2022), ora di New York con l'ora legale,
# uguali per tutti i symbol (l'orologio del paper, non quello della piazza)
MOMENTUM_INTRADAY_FUSO = "America/New_York"
MOMENTUM_INTRADAY_ORARI = {"chiusura": "17:00", "apertura": "09:30",
                           "penultima": "16:00", "ultima": "16:30"}
COLONNE_MOMENTUM_INTRADAY = ("imm_r1", "imm_r12")


def momentum_intraday(df: pd.DataFrame, fuso: str = MOMENTUM_INTRADAY_FUSO,
                      orari: dict | None = None) -> pd.DataFrame:
    """
    I due rendimenti del momentum intraday, scritti SOLO sulla candela del
    segnale (quella che finisce alle 16:30 di New York: il trade si apre alle
    16:30 e si chiude alle 17:00 con X_ORA_@17:00); NaN su tutte le altre.

      imm_r1   «prima mezz'ora»: dal prezzo delle 17:00 del giorno di trading
               prima (l'ultima chiusura delle 17:00 disponibile) al prezzo
               delle 09:30 di oggi
      imm_r12  «penultima mezz'ora»: dal prezzo delle 16:00 a quello delle
               16:30 di oggi

    Il prezzo «alle HH:MM» e' il Close della candela che finisce alle HH:MM,
    cosi' su M5, M15 e M30 e' lo stesso istante. Su H1 e H4 le 09:30 e le
    16:30 non sono l'inizio di una candela: le colonne restano tutte NaN (le
    entry non scattano mai, verifica_degenerazione lo segnala) invece di
    fermare il catalogo intero. Se manca la candela di un orario, quel giorno
    non c'e' valore.

    Nessun lookahead: alle 16:30 tutti e quattro i prezzi sono gia' noti.
    Nota sul dato del broker (decisione di Mattia del 18/10/2026: orari del
    paper, i dati verranno da exchange crypto): il prezzo delle 17:00 e' il
    Close della candela delle 16:45, che sul broker e' in quarantena.

    Fonti: Shen, Urquhart, Wang, "Bitcoin Intraday Time-Series Momentum",
    Financial Review 57(2), 2022, pp. 319-344, §2 e §3.4 (formule 7 e 8);
    Gao, Han, Li, Zhou, "Intraday Momentum: The First Half-Hour Return
    Predicts the Last Half-Hour Return", J. of Financial Economics 2018.
    """
    from engine.stagionalita import segnale_prima_di
    o = dict(MOMENTUM_INTRADAY_ORARI, **(orari or {}))
    vuoto = pd.DataFrame(np.nan, index=df.index, columns=list(COLONNE_MOMENTUM_INTRADAY))
    if getattr(df.index, "tz", None) is None or len(df) < 2:
        return vuoto
    try:
        fine = {k: segnale_prima_di(df, v, fuso).to_numpy() for k, v in o.items()}
    except ValueError:
        return vuoto
    close = df["Close"].to_numpy(dtype=float)
    pos = np.arange(len(df))

    def ultimo(maschera: np.ndarray) -> np.ndarray:
        # posizione dell'ultima candela (fino a questa compresa) con la maschera vera, -1 se nessuna
        return np.maximum.accumulate(np.where(maschera, pos, -1))

    u_chiusura, u_apertura, u_penultima = (ultimo(fine[k]) for k in ("chiusura", "apertura", "penultima"))
    segnale = fine["ultima"]
    t = df.index
    # stessa giornata: l'apertura di oggi viene dopo l'ultima chiusura delle 17:00,
    # e la penultima mezz'ora e' di oggi (dopo l'apertura, 30 minuti prima del segnale)
    passo = pd.Timedelta(minutes=30)
    ok1 = segnale & (u_apertura > u_chiusura) & (u_chiusura >= 0)
    ok12 = segnale & (u_penultima > u_apertura) & (u_apertura >= 0)
    r1 = np.full(len(df), np.nan)
    r12 = np.full(len(df), np.nan)
    i1 = np.flatnonzero(ok1)
    r1[i1] = close[u_apertura[i1]] / close[u_chiusura[i1]] - 1.0
    i12 = np.flatnonzero(ok12)
    stessa = (t[i12] - t[u_penultima[i12]]) == passo
    i12 = i12[np.asarray(stessa)]
    r12[i12] = close[i12] / close[u_penultima[i12]] - 1.0
    return pd.DataFrame({"imm_r1": r1, "imm_r12": r12}, index=df.index)


# ---------------------------------------------------------------------------
# Coppie di ore UTC (docs/50 §10, riga 17; scheda approvata da Mattia il
# 19/10/2026: coppie 8~22 e 12~13 di Wen, Bouri, Xu, Zhao, 2022)
# ---------------------------------------------------------------------------

# colonna -> (inizio dell'ora del segnale, fine dell'ora del segnale, ora in
# cui si apre il trade), tutto in UTC fisso come nel paper (prezzi Bitstamp in
# GMT, senza ora legale). L'ora «i» del paper va da (i-1):00 a i:00 (eq. 1).
ORE_UTC_COPPIE = {"ora_r8": ("07:00", "08:00", "21:00"),     # 8~22: momentum
                  "ora_r12": ("11:00", "12:00", "12:00")}    # 12~13: inversione
COLONNE_ORE_UTC = tuple(ORE_UTC_COPPIE)


def rendimenti_ore_utc(df: pd.DataFrame, coppie: dict | None = None) -> pd.DataFrame:
    """
    Il rendimento di un'ora UTC fissa, scritto SOLO sulla candela del segnale
    (quella che finisce all'ora in cui si apre il trade); NaN altrove.

      ora_r8   ora 8 del paper: dal prezzo delle 07:00 a quello delle 08:00
               UTC, sulla candela che finisce alle 21:00 (trade 21:00 -> 22:00)
      ora_r12  ora 12 del paper: dal prezzo delle 11:00 a quello delle 12:00
               UTC, sulla candela che finisce alle 12:00 (trade 12:00 -> 13:00)

    Il prezzo «alle HH:MM» e' il Close della candela che finisce alle HH:MM
    (come in momentum_intraday). Tutto nello stesso giorno UTC: se manca una
    delle tre candele, quel giorno non c'e' valore. Su candele piu' larghe di
    un'ora (H4) le colonne restano tutte NaN: le entry non scattano mai.

    Nessun lookahead: alla fine della candela del segnale i due prezzi sono
    gia' noti; il motore apre all'Open della candela dopo.

    Fonte: Wen, Bouri, Xu, Zhao, "Intraday return predictability in the
    cryptocurrency markets: momentum, reversal, or both", North American J.
    of Economics and Finance 62, 2022 (SSRN 4080253), §2.1 eq. 1, Tab. 2,
    §5.1 eq. 8.
    """
    from engine.quarantena import passo_barre
    c = dict(ORE_UTC_COPPIE if coppie is None else coppie)
    esito = pd.DataFrame(np.nan, index=df.index, columns=list(c))
    if getattr(df.index, "tz", None) is None or len(df) < 2:
        return esito
    passo = passo_barre(df.index)
    if passo > pd.Timedelta(hours=1):
        return esito
    fine = pd.DatetimeIndex(df.index + passo).tz_convert("UTC")   # l'istante in cui la candela finisce
    giorno = fine.normalize()
    close = df["Close"].to_numpy(dtype=float)

    def _durata(hhmm: str) -> pd.Timedelta:
        ore, minuti = hhmm.split(":")
        return pd.Timedelta(hours=int(ore), minutes=int(minuti))

    for col, (da, a, segnale) in c.items():
        i_seg = np.flatnonzero(np.asarray(fine - giorno == _durata(segnale)))
        g = giorno[i_seg]
        p_da = fine.get_indexer(g + _durata(da))
        p_a = fine.get_indexer(g + _durata(a))
        ok = (p_da >= 0) & (p_a >= 0)
        valori = np.full(len(df), np.nan)
        valori[i_seg[ok]] = close[p_a[ok]] / close[p_da[ok]] - 1.0
        esito[col] = valori
    return esito


# ---------------------------------------------------------------------------
# Momentum dopo un salto (docs/50 §10, riga 18; scheda approvata da Mattia il
# 19/10/2026: Baltussen, Da, Lammers, Martens 2021, §4.3, solo il candidato C)
# ---------------------------------------------------------------------------

SALTO_FUSO = "America/New_York"   # la «chiusura» e' quella di E36: le 17:00 di New York
SALTO_CHIUSURA = 17 * 60          # minuti dalla mezzanotte di New York
SALTO_GIORNATE = 250              # giornate chiuse su cui si calcolano i percentili (traduzione nostra)
SALTO_PERCENTILI = (0.10, 0.90)   # come nel paper (Tab. 10)
COLONNE_SALTO = ("salto",)


def salto_giornaliero(df: pd.DataFrame, giornate: int = SALTO_GIORNATE,
                      percentili: tuple = SALTO_PERCENTILI) -> pd.DataFrame:
    """
    Il primo «salto» della giornata, scritto SOLO sulla candela che lo
    rivela: +1 se il rendimento dalla chiusura di ieri supera il 90°
    percentile dei rendimenti giornalieri, -1 se scende sotto il 10°; 0 sulle
    altre candele; NaN finche' non ci sono `giornate` rendimenti giornalieri.

      chiusura   il Close della candela che finisce alle 17:00 di New York
                 (come imm_r1 di E36); la giornata va da una chiusura alla
                 successiva; se una chiusura manca (weekend del forex) si usa
                 l'ultima disponibile
      controlli  ogni mezz'ora, sulle candele che finiscono alle :00 e alle :30
                 di New York, esclusa quella delle 17:00 (e' la chiusura)
      soglie     10° e 90° percentile dei rendimenti fra chiusure successive
                 delle ultime `giornate` giornate CHIUSE (mai quella in corso)

    Un solo salto al giorno, il primo, nel suo verso. Il trade si chiude alla
    chiusura con X_ORA_@17:00. Su candele che non dividono la mezz'ora (H1,
    H4) la colonna resta tutta NaN.

    Nessun lookahead: alla fine della candela di controllo il rendimento e le
    soglie (fatte di giornate gia' chiuse) sono noti. Il paper usa il
    percentile di tutto il campione: qui e' mobile, sul passato (§6 di
    docs/50).

    Fonte: Baltussen, Da, Lammers, Martens, "Hedging demand and market
    intraday momentum", J. of Financial Economics 2021 (SSRN 3760365,
    26/8/2020), §4.3 e Tab. 10.
    """
    from engine.quarantena import passo_barre
    vuoto = pd.DataFrame(np.nan, index=df.index, columns=list(COLONNE_SALTO))
    if getattr(df.index, "tz", None) is None or len(df) < 2:
        return vuoto
    passo = passo_barre(df.index)
    if passo > pd.Timedelta(minutes=30) or pd.Timedelta(minutes=30) % passo != pd.Timedelta(0):
        return vuoto
    fine = pd.DatetimeIndex(df.index + passo).tz_convert(SALTO_FUSO)
    minuti = np.asarray(fine.hour * 60 + fine.minute, dtype=np.int64)
    close = df["Close"].to_numpy(dtype=float)
    e_chiusura = minuti == SALTO_CHIUSURA
    pos_chiusure = np.flatnonzero(e_chiusura)
    if len(pos_chiusure) <= giornate:
        return vuoto
    c17 = close[pos_chiusure]
    giornaliero = pd.Series(c17[1:] / c17[:-1] - 1.0)              # rendimento della giornata chiusa j+1
    basso = giornaliero.rolling(giornate).quantile(percentili[0]).to_numpy()
    alto = giornaliero.rolling(giornate).quantile(percentili[1]).to_numpy()
    # giornata di ogni candela: quante chiusure ci sono state PRIMA di lei
    giorno = np.cumsum(e_chiusura) - e_chiusura
    controllo = (minuti % 30 == 0) & ~e_chiusura & (giorno >= 1)
    i = np.flatnonzero(controllo)
    k = giorno[i]                                                  # la chiusura di ieri e' c17[k-1]
    # soglie della giornata k: rendimenti delle giornate chiuse fino a k-1, cioe' giornaliero[k-2]
    j = k - 2
    ok = j >= 0
    i, k, j = i[ok], k[ok], j[ok]
    r = close[i] / c17[k - 1] - 1.0
    lo, hi = basso[j], alto[j]
    pronta = np.isfinite(lo) & np.isfinite(hi)
    segno = np.where(r > hi, 1.0, np.where(r < lo, -1.0, 0.0))
    esito_col = np.full(len(df), np.nan)
    # NaN fino alla prima giornata con le soglie pronte, poi 0
    if pronta.any():
        primo_giorno = k[pronta].min()
        esito_col[giorno >= primo_giorno] = 0.0
    i, k, segno = i[pronta], k[pronta], segno[pronta]
    salti = segno != 0
    i, k, segno = i[salti], k[salti], segno[salti]
    _, primo = np.unique(k, return_index=True)                     # il primo salto di ogni giornata
    esito_col[i[primo]] = segno[primo]
    vuoto["salto"] = esito_col
    return vuoto


# ---------------------------------------------------------------------------
# Quintili del rendimento giornaliero (docs/50 §10, riga 19; variante di
# Mattia del 19/10/2026 sul momentum di Liu e Tsyvinski, Tab. 14-17)
# ---------------------------------------------------------------------------

QUINTILE_GIORNATE = 300            # giornate chiuse su cui si calcolano i quintili (scelta di Mattia)
QUINTILE_PERCENTILI = (0.20, 0.80)  # 1° e 5° quintile
COLONNE_QUINTILE = ("quintile_giorno",)


def quintile_giornaliero(df: pd.DataFrame, giornate: int = QUINTILE_GIORNATE,
                         percentili: tuple = QUINTILE_PERCENTILI) -> pd.DataFrame:
    """
    Il quintile estremo del rendimento della giornata appena chiusa, scritto
    SOLO sulla candela che chiude la giornata (quella che finisce alla
    mezzanotte UTC): +1 se il rendimento supera l'80° percentile dei
    rendimenti delle `giornate` giornate chiuse prima (5° quintile), -1 se
    scende sotto il 20° (1° quintile); 0 sulle altre candele; NaN finche'
    non ci sono `giornate` rendimenti precedenti.

    La giornata va da una mezzanotte UTC alla successiva, come nel paper
    (chiusure CoinDesk); il rendimento e' fra il Close della candela che
    finisce a mezzanotte e quello della mezzanotte precedente disponibile (sul
    forex il lunedi' parte dalla mezzanotte del venerdi'). Su candele che non
    finiscono a mezzanotte UTC (le H4 del broker) la colonna resta tutta NaN.
    Il trade si apre all'inizio della giornata dopo; si chiude dopo H barre o
    all'ora scelta nelle uscite.

    Nessun lookahead: alla fine della candela di mezzanotte il rendimento e'
    noto, le soglie usano solo le giornate precedenti (oggi escluso).

    Fonte: Liu, Tsyvinski, "Risks and Returns of Cryptocurrency", Review of
    Financial Studies 2021 (NBER WP 24877, 2018), §4.1, Tab. 14-17
    (quintili del rendimento appena chiuso); finestra mobile di 300 giornate
    e passo giornaliero decisi da Mattia il 19/10/2026.
    """
    from engine.quarantena import passo_barre
    vuoto = pd.DataFrame(np.nan, index=df.index, columns=list(COLONNE_QUINTILE))
    if getattr(df.index, "tz", None) is None or len(df) < 2:
        return vuoto
    passo = passo_barre(df.index)
    if passo > pd.Timedelta(days=1):
        return vuoto
    fine = pd.DatetimeIndex(df.index + passo).tz_convert("UTC")
    e_chiusura = np.asarray((fine.hour == 0) & (fine.minute == 0))
    pos = np.flatnonzero(e_chiusura)
    if len(pos) <= giornate + 1:
        return vuoto
    c = df["Close"].to_numpy(dtype=float)[pos]
    rend = pd.Series(c[1:] / c[:-1] - 1.0)                       # rendimento della giornata chiusa in pos[j+1]
    # soglie dalle `giornate` giornate PRIMA di quella appena chiusa
    basso = rend.rolling(giornate).quantile(percentili[0]).shift(1).to_numpy()
    alto = rend.rolling(giornate).quantile(percentili[1]).shift(1).to_numpy()
    r = rend.to_numpy()
    pronta = np.isfinite(basso) & np.isfinite(alto)
    segno = np.where(r > alto, 1.0, np.where(r < basso, -1.0, 0.0))
    esito_col = np.full(len(df), np.nan)
    if pronta.any():
        esito_col[pos[1:][np.argmax(pronta)]:] = 0.0
        dove = pos[1:][pronta]
        esito_col[dove] = segno[pronta]
    vuoto["quintile_giorno"] = esito_col
    return vuoto


# ---------------------------------------------------------------------------
# AlgoXplorer 0.1c (docs/50 §10, riga 13; scheda approvata da Mattia il
# 17/10/2026). Script Pine v5 scritto da Mattia e da un amico, uso concordato.
# Traduzione riga per riga; fedelta' verificata con PineTS su una copia di
# collaudo (pine_sources/algoxplorer_0_1c_v5.pine) che sostituisce solo
# request.security: candele HA con la formula standard, volume del grafico.
# ---------------------------------------------------------------------------
def heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """
    Candele Heikin Ashi dello stesso timeframe, come `ticker.heikinashi` di
    TradingView: chiusura = (O + H + L + C) / 4; apertura = media di apertura
    e chiusura HA della barra prima (prima barra dei dati: (O + C) / 2);
    massimo = max(High, apertura HA, chiusura HA), minimo = min(Low, ...).

    Solo barre passate. L'apertura e' ricorsiva: dipende dalla prima barra
    dei dati, ma la differenza si dimezza a ogni barra (sparita dopo ~60).
    Le barre in quarantena entrano nel calcolo, come nello script.
    """
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("Open", "High", "Low", "Close"))
    ha_c = (o + h + l + c) / 4
    ha_o = np.empty(len(df))
    if len(df):
        ha_o[0] = (o[0] + c[0]) / 2
    for i in range(1, len(df)):
        ha_o[i] = (ha_o[i - 1] + ha_c[i - 1]) / 2
    ha_h = np.maximum(h, np.maximum(ha_o, ha_c))
    ha_l = np.minimum(l, np.minimum(ha_o, ha_c))
    return pd.DataFrame({"ha_open": ha_o, "ha_high": ha_h, "ha_low": ha_l, "ha_close": ha_c},
                        index=df.index)


def pvsra_climax(df: pd.DataFrame, barre: int = 10, multiplo: float = 2.0) -> pd.Series:
    """
    Candela "climax" del PVSRA come nello script AlgoXplorer: volume almeno
    `multiplo` volte la media delle ultime `barre` barre (barra corrente
    compresa, `math.sum(volume, 10) / 10`), oppure volume x (High - Low) il
    piu' alto delle ultime `barre`. +1 se la candela vera chiude sopra
    l'apertura (colore lime), -1 altrimenti (rosso), 0 se non e' climax.
    Usa il tick volume di MT5. Riscaldamento: `barre` - 1 barre (0).
    """
    v = df["Volume"].astype(float)
    media = v.rolling(barre).sum() / barre
    v2 = v * (df["High"] - df["Low"])
    climax = (v >= media * multiplo) | (v2 >= v2.rolling(barre).max())
    rialzo = df["Close"] > df["Open"]
    return pd.Series(np.where(climax, np.where(rialzo, 1, -1), 0), index=df.index, dtype=float)


def algoxplorer(df: pd.DataFrame, barre_ema: int = 50, con_volume: bool = True) -> pd.DataFrame:
    """
    La macchina dello script AlgoXplorer 0.1c ("Sensibility" 2 = EMA a 50
    barre, strategia "careful"). Restituisce tre colonne, una riga per barra:

      segnale  +1 sull'etichetta Buy, -1 sull'etichetta Sell, 0 altrove
      stato    +1 dopo l'ultimo Buy, -1 dopo l'ultimo Sell, 0 prima del primo
      careful  +1 sulla barra dell'ingresso long "careful", -1 short, 0 altrove

    Setup (sulla stessa barra; HA = Heikin Ashi, `heikin_ashi`):
      BUY   1. candela PVSRA climax rialzista (`pvsra_climax` = +1)
            2. chiusura HA sopra la EMA dei massimi (`_ema_pine`, come ta.ema)
            3. massimo HA sopra la chiusura HA
            4. chiusura HA sopra il massimo HA della barra prima
      SELL  1. candela PVSRA climax ribassista (-1)
            2. chiusura HA sotto la EMA dei minimi
            3. massimo HA uguale all'apertura HA (nessuna ombra superiore)
            4. chiusura HA sotto il minimo HA della barra prima
    Long e short non sono speculari (punto 3): come nello script.
    `con_volume=False` toglie il punto 1 (interruttore "Forex" dello script).

    Alternanza: l'etichetta Buy compare solo se lo stato della barra prima non
    e' gia' long (Sell lo stesso). Buy e Sell non possono cadere sulla stessa
    barra (chiusura HA sopra la EMA dei massimi e sotto quella dei minimi).

    Careful: al Buy il livello e' il massimo HA della candela del segnale;
    l'ingresso long e' la PRIMA barra successiva, ancora in stato long e
    prima del Sell, il cui massimo HA supera il livello (nello script: la
    prima etichetta "Max profit", "massimi" da 1 a 2). Se non succede prima
    del Sell, nessun ingresso ("Not enter"). Short: minimo HA sotto il minimo
    HA della candela del Sell. Il motore entra all'Open della barra dopo.
    """
    ha = heikin_ashi(df)
    ha_o, ha_h, ha_l, ha_c = (ha[k].to_numpy() for k in ("ha_open", "ha_high", "ha_low", "ha_close"))
    ema_h = _ema_pine(df["High"], barre_ema).to_numpy()
    ema_l = _ema_pine(df["Low"], barre_ema).to_numpy()
    ha_h1 = np.r_[np.nan, ha_h[:-1]]
    ha_l1 = np.r_[np.nan, ha_l[:-1]]
    buy = (ha_c > ema_h) & (ha_h > ha_c) & (ha_c > ha_h1)
    sell = (ha_c < ema_l) & (ha_h == ha_o) & (ha_c < ha_l1)
    if con_volume:
        colore = pvsra_climax(df).to_numpy()
        buy &= colore == 1
        sell &= colore == -1
    n = len(df)
    segnale, stato, careful = np.zeros(n), np.zeros(n), np.zeros(n)
    st, livello, entrato = 0, np.nan, True
    for i in range(n):
        prima = st
        if buy[i] and prima != 1:
            segnale[i], st, livello, entrato = 1, 1, ha_h[i], False
        elif sell[i] and prima != -1:
            segnale[i], st, livello, entrato = -1, -1, ha_l[i], False
        elif not entrato and prima == 1 and ha_h[i] > livello:
            careful[i], entrato = 1, True
        elif not entrato and prima == -1 and ha_l[i] < livello:
            careful[i], entrato = -1, True
        stato[i] = st
    return pd.DataFrame({"segnale": segnale, "stato": stato, "careful": careful}, index=df.index)


# ---------------------------------------------------------------------------
# VSA · Modulo Unico (docs/50 §10, riga 14; scheda approvata da Mattia il
# 17/10/2026). Script Pine v6 scritto da Mattia, nessun vincolo. Traduzione
# riga per riga dei rami usati (motore d'asta, scanner VSA, trend following,
# Stop & Reverse); fedelta' verificata con PineTS su una copia di collaudo
# (pine_sources/vsa_modulo_unico.pine: tolte grafica, pannello e alert).
# ---------------------------------------------------------------------------
def _percentrank_pine(x: np.ndarray, barre: int) -> np.ndarray:
    """`ta.percentrank`: quota delle `barre` barre PRECEDENTI <= della barra corrente, x 100."""
    esito = np.full(len(x), np.nan)
    if len(x) > barre:
        finestre = sliding_window_view(x[:-1], barre)
        esito[barre:] = (finestre <= x[barre:, None]).sum(axis=1) / barre * 100
    return esito


def _percentile_pine(x: np.ndarray, barre: int, percento: float) -> np.ndarray:
    """`ta.percentile_linear_interpolation`: sulle ultime `barre` barre (corrente compresa),
    posizione n * p - 0,5 nei valori ordinati, interpolazione lineare (verificato con PineTS)."""
    esito = np.full(len(x), np.nan)
    if len(x) >= barre:
        ordinati = np.sort(sliding_window_view(x, barre), axis=1)
        pos = min(max(barre * percento / 100.0 - 0.5, 0.0), barre - 1.0)
        basso = int(np.floor(pos))
        alto = min(basso + 1, barre - 1)
        esito[barre - 1:] = ordinati[:, basso] + (pos - basso) * (ordinati[:, alto] - ordinati[:, basso])
    return esito


def vsa_modulo_unico(df: pd.DataFrame, pct_corpo: float = 50, barre_stat: int = 100,
                     min_barre_gamba: int = 2, pct_alto: float = 70, pct_basso: float = 30,
                     soglia_forza: float = 1.0, zona_morta: float = 20.0, attesa_max: int = 3,
                     pct_conferma: float = 50, k_livello: float = 2.0,
                     pct_pieno: float = 65) -> pd.DataFrame:
    """
    Lo script "VSA · Modulo Unico" con i suoi default ("Corpo (accettazione)",
    "Percentile", "Reversal (classica)", gamba in corso nel momentum), SENZA
    filtro di sessione (decisione di Mattia del 17/10/2026). Quattro colonne:

      asta  +1 / -1 asta confermata (almeno 2 BOS di fila nello stesso verso), 0 no
      bias  segnale VSA della barra: assorbimento (volume >= 70° percentile,
            corpo <= 30°) o esaurimento (volume <= 30°, corpo >= 70°), sempre
            contrario al colore della candela; 0 se nessuno o doji
      go    +1 / -1 sulla barra del GO trend following (Step 12-17)
      sr    +1 / -1 sulla barra dello Stop & Reverse (Step 24)

    Motore d'asta: zig-zag sui corpi; uno swing si conferma quando il prezzo
    torna indietro di almeno la mediana dei corpi (ultime 100 barre) e sono
    passate almeno 2 barre dall'ultimo pivot. Il livello esiste dalla barra
    di conferma. BOS = prima chiusura oltre l'ultimo swing; CHoCH = BOS contrario
    a un'asta confermata. Forza di una gamba = ampiezza / (barre x mediana corpi).

    GO trend (spunte dello script che filtrano davvero):
      1. asta confermata               2. momentum (forza delle due gambe, scarto
      3. forza massima >= 1               di almeno il 20%) nel verso dell'asta
      4. una candela di incongruenza VSA nel verso dell'asta nelle 3 barre prima
      5. il minimo (long) o il massimo (short) di quella candela a non piu' di 2
         mediane dei corpi da uno degli ultimi 24 swing
      6. candela di conferma: del colore dell'asta, corpo >= 50° percentile
    Le spunte 7 (stop), 8 (R:R >= 2) e 10 (rischio) con i default sono sempre
    vere (la cascata dei target finisce nella "proiezione R"): non entrano.

    Stop & Reverse: CHoCH chiuso da una candela del verso nuovo con corpo >= 65°
    percentile.

    Tutto a barra chiusa, solo passato. I prezzi si arrotondano a 10 decimali:
    nei CSV di MT5 due corpi "uguali" differiscono di 1e-16 e il rango
    percentile deciderebbe a caso; per la stessa ragione si arrotondano a 10
    decimali le differenze di prezzo (corpo, ampiezza della gamba, distanza
    dal livello), lo scarto del momentum e la forza prima delle soglie. Tick volume. Le barre in quarantena entrano
    nel calcolo, come nello script. Il ramo RANGE non c'e': con i default non
    puo' scattare (docs/50 §10 sexies).
    """
    o, h, l, c = (np.round(df[k].to_numpy(dtype=float), 10) for k in ("Open", "High", "Low", "Close"))
    v = df["Volume"].to_numpy(dtype=float)
    n = len(df)
    corpo = np.round(np.abs(c - o), 10)
    su = c > o
    giu = c < o
    doji = corpo == 0
    alto_c, basso_c = np.maximum(o, c), np.minimum(o, c)
    mediana = np.round(_percentile_pine(corpo, barre_stat, pct_corpo), 10)
    rango_v = _percentrank_pine(v, barre_stat)
    rango_c = _percentrank_pine(corpo, barre_stat)
    pronto = ~np.isnan(rango_v) & ~np.isnan(rango_c) & (np.arange(n) > barre_stat)
    assorb = ~doji & pronto & (rango_v >= pct_alto) & (rango_c <= pct_basso)
    esaur = ~doji & pronto & (rango_v <= pct_basso) & (rango_c >= pct_alto)
    bias = np.where(assorb | esaur, np.where(su, -1, 1), 0)
    rc = np.nan_to_num(rango_c, nan=-1.0)

    asta = np.zeros(n)
    go = np.zeros(n)
    sr = np.zeros(n)
    nan = float("nan")
    gamba = 1
    piv_h, piv_h_bar = (alto_c[0], 0) if n else (nan, 0)
    piv_l, piv_l_bar = (basso_c[0], 0) if n else (nan, 0)
    ultimo_bar, ultimo_px = 0, nan
    sw_h = sw_l = nan
    sw_h_rotto = sw_l_rotto = False
    serie = 0
    forza_su = forza_giu = nan
    livelli_h, livelli_l = [], []
    seg_bar, seg_dir, dist_liv = None, 0, nan
    for i in range(n):
        mb = mediana[i]
        soglia_ok = not np.isnan(mb) and mb > 0
        prima = 1 if serie >= 2 else (-1 if serie <= -2 else 0)
        bos_su = bos_giu = choch_su = choch_giu = False
        if soglia_ok:
            hs, ls = alto_c[i], basso_c[i]
            if gamba == 1:
                if np.isnan(piv_h) or hs > piv_h:
                    piv_h, piv_h_bar, piv_l, piv_l_bar = hs, i, ls, i
                else:
                    if ls < piv_l:
                        piv_l, piv_l_bar = ls, i
                    if round(piv_h - piv_l, 10) >= mb and i - ultimo_bar >= min_barre_gamba:
                        lunghezza = max(piv_h_bar - ultimo_bar, 1)
                        if not np.isnan(ultimo_px):
                            forza_su = abs(piv_h - ultimo_px) / (lunghezza * mb)
                        ultimo_bar, ultimo_px = piv_h_bar, piv_h
                        sw_h, sw_h_rotto = piv_h, False
                        livelli_h.append(piv_h)
                        del livelli_h[:-24]
                        gamba = -1
                        piv_h, piv_h_bar = hs, i
            else:
                if np.isnan(piv_l) or ls < piv_l:
                    piv_l, piv_l_bar, piv_h, piv_h_bar = ls, i, hs, i
                else:
                    if hs > piv_h:
                        piv_h, piv_h_bar = hs, i
                    if round(piv_h - piv_l, 10) >= mb and i - ultimo_bar >= min_barre_gamba:
                        lunghezza = max(piv_l_bar - ultimo_bar, 1)
                        if not np.isnan(ultimo_px):
                            forza_giu = abs(ultimo_px - piv_l) / (lunghezza * mb)
                        ultimo_bar, ultimo_px = piv_l_bar, piv_l
                        sw_l, sw_l_rotto = piv_l, False
                        livelli_l.append(piv_l)
                        del livelli_l[:-24]
                        gamba = 1
                        piv_l, piv_l_bar = ls, i
            if not np.isnan(sw_h) and not sw_h_rotto and c[i] > sw_h:
                bos_su, sw_h_rotto = True, True
            if not np.isnan(sw_l) and not sw_l_rotto and c[i] < sw_l:
                bos_giu, sw_l_rotto = True, True
            if bos_su and not bos_giu:
                serie = serie + 1 if serie > 0 else 1
                choch_su = prima == -1
            elif bos_giu and not bos_su:
                serie = serie - 1 if serie < 0 else -1
                choch_giu = prima == 1
        a = 1 if serie >= 2 else (-1 if serie <= -2 else 0)
        asta[i] = a
        # momentum (Step 3), con la gamba in corso
        dal_pivot = i - ultimo_bar
        in_corso = abs(piv_h - ultimo_px) if gamba == 1 else abs(ultimo_px - piv_l)
        viva = in_corso / (dal_pivot * mb) if (dal_pivot >= 2 and soglia_ok and not np.isnan(in_corso)) else nan
        f_su = viva if (gamba == 1 and not np.isnan(viva)) else forza_su
        f_giu = viva if (gamba == -1 and not np.isnan(viva)) else forza_giu
        forza_max = round(max(0.0 if np.isnan(f_su) else f_su, 0.0 if np.isnan(f_giu) else f_giu), 10)
        if np.isnan(f_su) or np.isnan(f_giu):
            momento = 0
        else:
            scarto = round(abs(f_su - f_giu) / max(f_su, f_giu, 0.0001), 10)
            momento = 0 if scarto < zona_morta / 100.0 else (1 if f_su > f_giu else -1)
        # trend following (Step 12-17)
        if bias[i] != 0 and a != 0 and bias[i] == a:
            seg_bar, seg_dir = i, int(bias[i])
            ancora = l[i] if seg_dir == 1 else h[i]
            distanze = [round(abs(x - ancora), 10) for x in livelli_h + livelli_l]
            dist_liv = min(distanze) if distanze else nan
        vivo = seg_bar is not None and 1 <= i - seg_bar <= attesa_max and seg_dir != 0
        conferma = (vivo and seg_dir == a and rc[i] >= pct_conferma
                    and (su[i] if seg_dir == 1 else giu[i]))
        if (conferma and a != 0 and momento == a and forza_max >= soglia_forza
                and not np.isnan(dist_liv) and soglia_ok and dist_liv <= mb * k_livello):
            go[i] = seg_dir
        # Stop & Reverse (Step 24)
        if choch_su and su[i] and rc[i] >= pct_pieno:
            sr[i] = 1
        elif choch_giu and giu[i] and rc[i] >= pct_pieno:
            sr[i] = -1
    return pd.DataFrame({"asta": asta, "bias": bias.astype(float), "go": go, "sr": sr}, index=df.index)


def aggiungi_indicatori(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggiunge al DataFrame di mercato le colonne usate dalle condizioni:

        rsi, macd, macd_signal, macd_hist, ema20, ema50, zlema50,
        atr, realized_vol, adx, vwap,
        ciclo_quota, ciclo_pendenza, atc_regime, pvo_hist, st_dir, iix,
        chop, vr, vfi, rvol, sqz_on, sqz_mom, wt1, wt2, ker, hurst,
        jdh_atr_diff, jdh_regime, sentiment_score, sentiment_classe,
        ftfc, mtf_h4_macdh_pend, mtf_h1_force, mtf_h1_high, mtf_h1_low,
        tsmom, inside_day, ha_open, ha_high, ha_low, ha_close, pvsra,
        algox_segnale, algox_stato, algox_careful, algox_nv_careful,
        vsa_asta, vsa_bias, vsa_go, vsa_sr, imm_r1, imm_r12, ora_r8, ora_r12, salto, quintile_giorno
        (momentum intraday: vedi momentum_intraday, valori solo sulla
        candela che finisce alle 16:30 di New York, aggiunte dopo il taglio;
        coppie di ore UTC: vedi rendimenti_ore_utc, stessa logica;
        salto: vedi salto_giornaliero, riscaldamento di 250 giornate;
        quintile_giorno: vedi quintile_giornaliero, riscaldamento di 300 giornate;
        AlgoXplorer: vedi algoxplorer, riscaldamento 50 barre; VSA: vedi
        vsa_modulo_unico, riscaldamento 100 barre piu' gli swing)
        (docs/51: riscaldamento V1 261 barre, V2 30, M1 38, M2 41, R1 10,
        R2 103, R3 201; multi timeframe: vedi colonne_multi_timeframe, al
        massimo un mese, aggiunte come il sentiment dopo il taglio)

    Le ultime sei vengono da articoli (7-8/10/2026): vedi le funzioni
    ciclo_dominante, canale_adattivo_regime, pvo_istogramma,
    supertrend_direzione e intraday_intensity qui sopra. Il
    ciclo dominante ha bisogno di 300 barre di storia: sono le prime 300
    righe a essere tolte, non piu' le prime 100 circa.

    poi toglie le righe con almeno un NaN (il riscaldamento iniziale degli
    indicatori). Le due colonne del sentiment (`sentiment_giornaliero`)
    si aggiungono DOPO questo taglio: restano NaN nel loro riscaldamento
    (~2 anni) senza togliere righe.

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
    df["hurst"] = hurst_rs(df["Close"])
    jdh = filtri_jdehorty(df)
    df["jdh_atr_diff"] = jdh["jdh_atr_diff"]
    df["jdh_regime"] = jdh["jdh_regime"]
    onda = wavetrend(df)
    df["wt1"] = onda["wt1"]
    df["wt2"] = onda["wt2"]
    # AlgoXplorer (E32, E33, X4, F40): nessun NaN, non tolgono righe
    for k, v in heikin_ashi(df).items():
        df[k] = v
    df["pvsra"] = pvsra_climax(df)
    algox = algoxplorer(df)
    df["algox_segnale"] = algox["segnale"]
    df["algox_stato"] = algox["stato"]
    df["algox_careful"] = algox["careful"]
    df["algox_nv_careful"] = algoxplorer(df, con_volume=False)["careful"]
    # VSA Modulo Unico (E34, E35): nessun NaN, non tolgono righe
    vsa = vsa_modulo_unico(df)
    for k in ("asta", "bias", "go", "sr"):
        df[f"vsa_{k}"] = vsa[k]
    df = df.dropna()
    # dopo il taglio: il sentiment ha ~2 anni di riscaldamento (NaN) e non deve
    # togliere righe alle altre condizioni; un filtro su NaN e' semplicemente falso.
    # La giornata FX richiede l'indice UTC: senza fuso (es. dati ricampionati nei
    # test degli altri indicatori) le colonne restano NaN e F36 e' sempre falso,
    # cosa che verifica_degenerazione segnala
    if getattr(df.index, "tz", None) is None:
        sentiment = pd.DataFrame(np.nan, index=df.index, columns=["sentiment_score", "sentiment_classe"])
        mtf = pd.DataFrame(np.nan, index=df.index, columns=list(COLONNE_MULTI_TIMEFRAME))
    else:
        sentiment = sentiment_giornaliero(df)
        mtf = colonne_multi_timeframe(df)
    df["sentiment_score"] = sentiment["sentiment_score"]
    df["sentiment_classe"] = sentiment["sentiment_classe"]
    # multi timeframe (F37, E31, F38, F39): come il sentiment, dopo il taglio,
    # NaN nel loro riscaldamento senza togliere righe
    for c in COLONNE_MULTI_TIMEFRAME:
        df[c] = mtf[c]
    # momentum intraday (E36, E37): valori solo sulla candela del segnale, NaN
    # altrove: dopo il taglio, come il sentiment
    imm = momentum_intraday(df)
    for c in COLONNE_MOMENTUM_INTRADAY:
        df[c] = imm[c]
    # coppie di ore UTC (E38, E39): stessa logica, dopo il taglio
    ore_utc = rendimenti_ore_utc(df)
    for c in COLONNE_ORE_UTC:
        df[c] = ore_utc[c]
    # momentum dopo un salto (E40): NaN nel riscaldamento di 250 giornate, dopo il taglio
    salto = salto_giornaliero(df)
    for c in COLONNE_SALTO:
        df[c] = salto[c]
    # quintili del rendimento giornaliero (E41): NaN nel riscaldamento di 300 giornate, dopo il taglio
    quintile = quintile_giornaliero(df)
    for c in COLONNE_QUINTILE:
        df[c] = quintile[c]
    return df


# le colonne che aggiungi_indicatori crea: il collaudo le verifica una per una
COLONNE_INDICATORI = (
    "rsi", "macd", "macd_signal", "macd_hist", "ema20", "ema50", "zlema50",
    "atr", "realized_vol", "adx", "vwap",
    "ciclo_quota", "ciclo_pendenza", "atc_regime", "pvo_hist", "st_dir", "iix",
    "chop", "vr", "vfi", "rvol", "sqz_on", "sqz_mom", "wt1", "wt2", "ker", "hurst",
    "jdh_atr_diff", "jdh_regime", "sentiment_score", "sentiment_classe",
    "ftfc", "mtf_h4_macdh_pend", "mtf_h1_force", "mtf_h1_high", "mtf_h1_low", "tsmom", "inside_day",
    "ha_open", "ha_high", "ha_low", "ha_close", "pvsra",
    "algox_segnale", "algox_stato", "algox_careful", "algox_nv_careful",
    "vsa_asta", "vsa_bias", "vsa_go", "vsa_sr",
    "imm_r1", "imm_r12", "ora_r8", "ora_r12", "salto", "quintile_giorno",
)


# 29/10/2026 (docs/77, lavoro 1): tolti funding_liquidato e basis_bp, gli stati dei perpetual
# (il funding come variabile e la basis). Il funding resta come costo dei trade (engine/exchange.py).


# ------------------------------------------------------------------------
# Stati dell'atlante del trigger (22/10/2026, docs/66 §2): le finestre sono
# DURATE in ore, convertite nelle barre del timeframe, con almeno 20
# rendimenti (docs/63 §10.1 punto 2). Su M15 sono le 20 e 500 barre di
# engine/confidenza.py. FUORI da aggiungi_indicatori: le colonne del catalogo
# non cambiano. Ogni stato della barra i usa solo dati fino al Close di i.
# ------------------------------------------------------------------------

ORE_VOLATILITA = 5         # la deviazione dei rendimenti: 20 barre su M15
ORE_MEDIANA = 125          # la mediana mobile: le 500 barre M15 di confidenza.py (~5,2 giorni)
MINIMO_RENDIMENTI = 20
SESSIONI_ATLANTE = ("ASIA_NOTTE", "EUROPA", "LONDRA_NY", "AMERICA")
# 04/11/2026 (docs/80, docs/81 §2.3, regole fisse di Mattia, mai tarate sui dati): VWAP e regressione di
# gap_trend ripartono dal periodo piu' corto con almeno MINIMO_RENDIMENTI barre, e la mediana dei due assi
# copre il maggiore fra ORE_MEDIANA e PERIODI_MEDIANA periodi di ancora. Per la mediana il mese conta 30
# giorni: la finestra e' un numero fisso di barre, il mese solare cambia durata.
PERIODI_MEDIANA = 5
ORE_PERIODO_ANCORA = {"D": 24, "W": 7 * 24, "M": 30 * 24}


def barre_per_durata(index, ore: float, minimo: int = MINIMO_RENDIMENTI) -> int:
    """Le barre del timeframe di `index` in `ore` ore, almeno `minimo`."""
    from engine.quarantena import passo_barre
    minuti = passo_barre(pd.DatetimeIndex(index)) / pd.Timedelta(minutes=1)
    return max(int(minimo), int(round(float(ore) * 60.0 / minuti)))


def regola_ancora(index, minimo: int = MINIMO_RENDIMENTI) -> str:
    """
    Il periodo da cui ripartono VWAP e regressione di gap_trend (docs/80, lavoro 2): il piu' corto, fra
    giornata ("D"), settimana ("W") e mese ("M", il piu' corto da 28 giorni), con almeno `minimo` barre.
    Dalla durata della barra, a calendario: M5, M15, M30, H1 la giornata; H4 la settimana; D1 il mese.
    Una barra piu' lunga non ha un periodo adatto: si ferma con un errore.
    """
    from engine.quarantena import passo_barre
    al_giorno = 1440.0 / (passo_barre(pd.DatetimeIndex(index)) / pd.Timedelta(minutes=1))
    for regola, giorni in (("D", 1), ("W", 7), ("M", 28)):
        if al_giorno * giorni >= minimo:
            return regola
    raise ValueError(f"Barre troppo lunghe: nemmeno un mese contiene {minimo} barre (ne contiene "
                     f"{al_giorno * 28:.1f}). VWAP e regressione non hanno un periodo da cui ripartire.")


def periodo_ancora(df: pd.DataFrame, minimo: int = MINIMO_RENDIMENTI) -> pd.Series:
    """
    Numero progressivo del periodo di ancora di ogni barra (regola_ancora). Fino a H1 e' la giornata di
    sempre, giorno_fx; su H4 la settimana e su D1 il mese di id_periodo: dal lunedi' e dal giorno 1 alle
    00:00 UTC sugli exchange, dalla settimana e dal mese FX sul broker. Con meno di due barre la durata
    della barra non si conosce: si resta alla giornata.
    """
    from engine.livelli import giorno_fx
    regola = "D" if len(df) < 2 else regola_ancora(df.index, minimo)
    if regola == "D":
        return giorno_fx(df)
    return pd.Series(id_periodo(df, regola), index=df.index)


def barre_mediana(index, ore: float = ORE_MEDIANA, minimo: int = MINIMO_RENDIMENTI) -> int:
    """
    Le barre della mediana dei due assi (docs/81 §2.3): il maggiore fra `ore` ore e PERIODI_MEDIANA
    periodi di ancora, almeno `minimo`. Fino a H1 restano le `ore` (125 ore e 5 giornate = 120 ore),
    su H4 sono 5 settimane (210 barre), su D1 5 mesi da 30 giorni (150 barre).
    """
    ore_periodi = PERIODI_MEDIANA * ORE_PERIODO_ANCORA[regola_ancora(index, minimo)]
    return barre_per_durata(index, max(float(ore), float(ore_periodi)), minimo)


def volatilita_durata(df: pd.DataFrame, ore: float = ORE_VOLATILITA, ore_mediana: float = ORE_MEDIANA,
                      minimo: int = MINIMO_RENDIMENTI) -> pd.Series:
    """
    Volatilita' alta (1) o bassa (0) di ogni barra: la deviazione dei
    log-rendimenti Close su Close delle ultime `ore` ore, sopra o no la sua
    mediana mobile (barre_mediana: almeno `ore_mediana` ore e 5 periodi di
    ancora). NaN finche' le finestre non sono piene. Stesse formule di
    confidenza.asse_volatilita (file di Mattia volatility_features_engineering.py:
    std, quantile 0,5): su M15 con i valori di default e' identica, bit per
    bit, a asse_volatilita(df, 20, 500).
    """
    w = barre_per_durata(df.index, ore, minimo)
    m = barre_mediana(df.index, ore_mediana, minimo)
    rendimenti = np.log(df["Close"] / df["Close"].shift(1)) * 100
    deviazione = rendimenti.rolling(window=w).std()
    mediana = deviazione.rolling(m, min_periods=m).quantile(0.5)
    classe = np.select([deviazione <= mediana, deviazione > mediana], [0.0, 1.0], default=np.nan)
    return pd.Series(classe, index=df.index).where(mediana.notna(), other=np.nan).rename("vol")


def trend_durata(df: pd.DataFrame, direzione: int, ore_mediana: float = ORE_MEDIANA,
                 minimo: int = MINIMO_RENDIMENTI) -> pd.Series:
    """
    Trend «a favore» (1) o «contro» (0) del lato `direzione`: gap_trend
    (confidenza.py, regressione del periodo di ancora meno il VWAP dello
    stesso periodo) nel verso del trade, sopra o no la sua mediana mobile
    (barre_mediana: almeno `ore_mediana` ore e 5 periodi di ancora). «A
    favore» vuol dire «nella meta' alta degli ultimi giorni», non «il prezzo
    sta salendo». NaN finche' non e' calcolabile.
    """
    if direzione not in (1, -1):
        raise ValueError("direzione deve essere 1 (long) o -1 (short).")
    from engine.confidenza import gap_trend
    m = barre_mediana(df.index, ore_mediana, minimo)
    allineato = gap_trend(df) * direzione
    mediana = allineato.rolling(m, min_periods=m).median()
    return ((allineato > mediana).astype(float)
            .where(mediana.notna() & allineato.notna()).rename("trend"))


def cella_vol_trend(df: pd.DataFrame, direzione: int, ore: float = ORE_VOLATILITA,
                    ore_mediana: float = ORE_MEDIANA, minimo: int = MINIMO_RENDIMENTI) -> pd.Series:
    """
    La cella 0-3 della griglia volatilita' x trend del lato `direzione`:
    2 x volatilita' + trend (0 = bassa e contro, 1 = bassa e a favore,
    2 = alta e contro, 3 = alta e a favore). Su M15 = confidenza.cella_contesto.
    """
    vol = volatilita_durata(df, ore, ore_mediana, minimo)
    trend = trend_durata(df, direzione, ore_mediana, minimo)
    return (2 * vol + trend).rename("cella")


def sessione_ingresso(df: pd.DataFrame) -> pd.Series:
    """
    La sessione della barra in cui si apre il trade (la i+1 del segnale sulla
    barra i), come le condizioni orarie dal 19/10/2026: 0 = ASIA_NOTTE
    (Londra e New York chiuse, compreso il fine settimana), 1 = EUROPA (solo
    Londra), 2 = LONDRA_NY (tutte e due), 3 = AMERICA (solo New York). Ora
    locale delle piazze con l'ora legale (engine/sessioni.py). L'inizio della
    barra i+1 si conosce dal calendario: inizio della barra i piu' la durata
    di una barra, anche se la barra i+1 mancasse nei dati.
    """
    from engine.quarantena import passo_barre
    from engine.sessioni import in_sessione
    prossima = pd.DataFrame(index=pd.DatetimeIndex(df.index) + passo_barre(df.index))
    londra = in_sessione(prossima, "LONDRA").to_numpy()
    new_york = in_sessione(prossima, "NEW_YORK").to_numpy()
    codice = np.select([londra & new_york, londra, new_york], [2.0, 1.0, 3.0], default=0.0)
    return pd.Series(codice, index=df.index, name="sessione")


# ------------------------------------------------------------------------
# Variabili della mappa delle anomalie (27/10/2026, docs/73 §B, schede di
# docs/74). FUORI da aggiungi_indicatori: le chiama solo engine/mappa.py, le
# colonne del catalogo non cambiano. Ogni valore della barra i usa solo dati
# fino al Close di i. I rendimenti si prendono per data, non per posizione:
# una barra mancante da' NaN invece di un rendimento su un'altra durata.
# ------------------------------------------------------------------------

def _rendimento_ore(close: pd.Series, ore: float) -> pd.Series:
    """Il rendimento dal Close della barra di `ore` ore prima (stessa griglia), NaN se quella barra manca."""
    idx = pd.DatetimeIndex(close.index)
    prima = close.astype(float).reindex(idx - pd.Timedelta(hours=float(ore))).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        return pd.Series(close.astype(float).to_numpy() / prima - 1.0, index=idx)


def rendimento_4h(df: pd.DataFrame) -> pd.Series:
    """Il rendimento delle ultime 4 ore al Close della barra, in bp (docs/74, M07)."""
    return (_rendimento_ore(df["Close"], 4) * 10_000.0).rename("rendimento_4h")


def quintile_rendimento_4h(df: pd.DataFrame) -> pd.Series:
    """
    Il quintile (0 = Q1 ... 4 = Q5) del rendimento a 4 ore della barra, con le soglie della scheda M07
    della mappa (29/10/2026, docs/77, lavoro 3): mappa.fasce_quintili sulla finestra della scheda (365
    giorni di sole barre passate, la barra esclusa). NaN dove il rendimento manca (un buco nelle 4 ore) o la
    finestra non e' ancora piena. FUORI da aggiungi_indicatori: le colonne del catalogo non cambiano.
    """
    from engine.ipotesi import SCHEDE
    from engine.mappa import fasce_quintili
    codici = fasce_quintili(rendimento_4h(df), SCHEDE["M07"].finestra_giorni)
    return pd.Series(codici, index=df.index, name="quintile_r4h")


def entra_nel_quintile_r4h(df: pd.DataFrame, quintile: int) -> pd.Series:
    """
    L'EVENTO della scheda M07 (docs/77, lavoro 3): il rendimento a 4 ore ENTRA nel quintile `quintile`
    (0 = Q1, 4 = Q5), cioe' la barra e' in quel quintile e la barra subito prima (una barra esatta prima,
    nessun buco) aveva un quintile noto e diverso. Un quintile non noto (NaN) non conta mai come «fuori».
    """
    from engine.quarantena import passo_barre
    q = quintile_rendimento_4h(df).to_numpy(dtype=float)
    idx = pd.DatetimeIndex(df.index)
    prima = np.r_[np.nan, q[:-1]]
    contigua = np.r_[False, np.asarray((idx[1:] - idx[:-1]) == passo_barre(idx))] if len(idx) > 1 else np.zeros(len(idx), bool)
    entra = (q == float(quintile)) & np.isfinite(prima) & (prima != float(quintile)) & contigua
    return pd.Series(entra, index=df.index, name=f"entra_q{int(quintile) + 1}_r4h")


def scarto_btc_1h(df: pd.DataFrame, df_btc: pd.DataFrame) -> pd.Series:
    """
    Il rendimento di BTC nell'ultima ora MENO quello dell'altcoin `df` nella
    stessa ora, in bp (docs/74, M06, versione A). `df_btc` e' BTC dello stesso
    exchange e mercato, sulla stessa griglia: le barre si allineano per data,
    e una barra che manca in uno dei due da' NaN.
    """
    r_alt = _rendimento_ore(df["Close"], 1)
    r_btc = _rendimento_ore(df_btc["Close"], 1).reindex(pd.DatetimeIndex(df.index))
    return ((r_btc - r_alt) * 10_000.0).rename("scarto_btc_1h")


# 29/10/2026 (docs/77, lavoro 1): tolte le variabili del funding delle schede M01 e M04
# (barre_prima_del_pagamento, funding_segno_prima_pagamento, funding_rispetto_al_base).


# ------------------------------------------------------------------------
# Trigger intraday (02/11/2026, docs/78 e docs/79): le sette idee E46-E52.
# FUORI da aggiungi_indicatori, come E45: le chiamano le entry, le colonne del
# catalogo non cambiano e il collaudo le ricalcola a ogni taglio. Le finestre
# sono DURATE in minuti (docs/78 §3, regola 3), convertite nelle barre del
# timeframe; ogni idea vale solo sui timeframe dove la conversione ha senso
# (docs/79 §1): fuori, la condizione e' tutta falsa e un avviso lo dice.
# Le finestre si contano in barre consecutive (un buco nei dati non si salta).
# Ogni valore della barra i usa solo dati fino al Close di i.
# ------------------------------------------------------------------------

CANALE_MINUTI = 24 * 60            # idea 1: canale delle 24 ore
IMPULSO_MINUTI = 45                # idea 1: 3 barre da 15 minuti nella fonte
IMPULSO_PERCENTILI = (0.60, 0.40)  # idea 1: long sopra il 60°, short sotto il 40°
TF_CANALE_IMPULSO = (5, 15)
ATR_COMPRESSIONE_MINUTI = 70       # idea 2: ATR 14 su barre da 5 minuti
MEDIA_ATR_MINUTI = 60              # idea 2: media 12 su barre da 5 minuti
CANALE_COMPRESSIONE_MINUTI = 180   # idea 2: canale 36 su barre da 5 minuti
FATTORE_COMPRESSIONE = 0.8
TF_COMPRESSIONE = (5, 15)
PIVOT_LATO_MINUTI = 15             # idea 3: 3 barre da 5 minuti per lato
FINESTRA_PIVOT_MINUTI = 500        # idea 3: 100 barre da 5 minuti
PIVOT_UGUALI = 3
BANDA_UGUALI = 0.002
TF_MASSIMI_UGUALI = (5, 15)
SWEEP_LATO_MINUTI = 180            # idea 4: 3 candele orarie per lato
SWEEP_CANDELA_MINUTI = 60          # idea 4: la candela oraria
TF_SWEEP = (5, 15, 30, 60)
SALTO_FINESTRA_MINUTI = 900        # idea 5: 60 barre da 15 minuti
SALTO_SOGLIA = 3.0
TF_SALTO = (5, 15, 30, 60)
MOVIMENTO_MINUTI = 300             # idea 6: 5 periodi orari
DEVIAZIONE_MOVIMENTO_MINUTI = 6000  # idea 6: 100 periodi orari
TF_MOVIMENTO_VOLUME = (5, 15, 30, 60)
AREA_GIORNI = 14                   # idea 7: parametri base del paper
AREA_MOLTIPLICATORE = 1.0
AREA_CONTROLLO_MINUTI = 30
TF_AREA_RUMORE = (5, 15, 30)


def _minuti_ammessi(index, ammessi: tuple, nome: str) -> float | None:
    """I minuti di una barra se il timeframe e' fra gli `ammessi`; altrimenti None e un avviso."""
    import warnings
    from engine.quarantena import passo_barre
    minuti = passo_barre(pd.DatetimeIndex(index)) / pd.Timedelta(minutes=1)
    if minuti not in ammessi:
        warnings.warn(f"{nome}: barre da {minuti:g} minuti, fuori dai timeframe ammessi "
                      f"({', '.join(f'{a}m' for a in ammessi)}): la condizione e' tutta falsa.", stacklevel=3)
        return None
    return minuti


def _barre_di(minuti_finestra: float, minuti_barra: float) -> int:
    """Una durata in barre del timeframe, arrotondata all'intero piu' vicino (almeno 1)."""
    return max(1, int(round(minuti_finestra / minuti_barra)))


def _falsa(df: pd.DataFrame) -> pd.Series:
    return pd.Series(False, index=df.index)


def _lato_valido(lato: int) -> int:
    if lato not in (1, -1):
        raise ValueError("lato deve essere 1 (long) o -1 (short).")
    return lato


def canale_24h_impulso(df: pd.DataFrame, lato: int) -> pd.Series:
    """
    Idea 1 (E46), lo STATO: long, il Close supera il massimo degli High delle 24 ore prima (barra
    esclusa) e il rendimento degli ultimi 45 minuti e' sopra il suo 60° percentile sulle 24 ore (barra
    compresa, come la fonte); short, sotto il minimo dei Low e sotto il 40° percentile. M5 e M15.
    """
    _lato_valido(lato)
    m = _minuti_ammessi(df.index, TF_CANALE_IMPULSO, "canale_24h_impulso")
    if m is None:
        return _falsa(df)
    w, r = _barre_di(CANALE_MINUTI, m), _barre_di(IMPULSO_MINUTI, m)
    c = df["Close"].astype(float)
    impulso = c / c.shift(r) - 1.0
    if lato == 1:
        livello = df["High"].rolling(w).max().shift(1)
        soglia = impulso.rolling(w).quantile(IMPULSO_PERCENTILI[0])
        return ((c > livello) & (impulso > soglia)).fillna(False).astype(bool)
    livello = df["Low"].rolling(w).min().shift(1)
    soglia = impulso.rolling(w).quantile(IMPULSO_PERCENTILI[1])
    return ((c < livello) & (impulso < soglia)).fillna(False).astype(bool)


def compressione_rottura(df: pd.DataFrame, lato: int) -> pd.Series:
    """
    Idea 2 (E47), lo STATO: sulla barra prima l'ATR (media semplice del true range su 70 minuti) era
    sotto 0,8 volte la sua media dell'ultima ora, e il Close rompe il canale delle 3 ore fino alla barra
    prima (massimo degli High per il long, minimo dei Low per lo short). Su M15 l'ATR e' di 5 barre
    (75 minuti, arrotondato), la media di 4, il canale di 12. M5 e M15.
    """
    _lato_valido(lato)
    m = _minuti_ammessi(df.index, TF_COMPRESSIONE, "compressione_rottura")
    if m is None:
        return _falsa(df)
    n_atr, n_media, n_canale = (_barre_di(x, m) for x in (ATR_COMPRESSIONE_MINUTI, MEDIA_ATR_MINUTI,
                                                         CANALE_COMPRESSIONE_MINUTI))
    h, l, c = df["High"].astype(float), df["Low"].astype(float), df["Close"].astype(float)
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n_atr).mean()
    compressa = (atr < FATTORE_COMPRESSIONE * atr.rolling(n_media).mean()).shift(1, fill_value=False).astype(bool)
    if lato == 1:
        return (compressa & (c > h.rolling(n_canale).max().shift(1))).fillna(False).astype(bool)
    return (compressa & (c < l.rolling(n_canale).min().shift(1))).fillna(False).astype(bool)


def pivot_chiusure(close: pd.Series, k: int, lato: int) -> np.ndarray:
    """
    I massimi (lato 1) o minimi (lato -1) locali delle chiusure: la chiusura e' strettamente sopra (sotto)
    le k chiusure prima e le k dopo. Vale per la barra del pivot, ma si CONOSCE solo k barre dopo: chi lo
    usa deve guardare solo i pivot di posizione <= i - k.
    """
    v = close.to_numpy(dtype=float)
    out = np.ones(len(v), dtype=bool)
    for j in range(1, int(k) + 1):
        prima = np.r_[np.full(j, np.nan), v[:-j]]
        dopo = np.r_[v[j:], np.full(j, np.nan)]
        with np.errstate(invalid="ignore"):
            out &= (v > prima) & (v > dopo) if lato == 1 else (v < prima) & (v < dopo)
    return out


def massimi_uguali_rottura(df: pd.DataFrame, lato: int) -> pd.Series:
    """
    Idea 3 (E48), lo STATO: gli ultimi 3 massimi locali delle chiusure gia' confermati (15 minuti per lato:
    3 barre su M5, 1 su M15) dentro la finestra di 500 minuti (100 barre su M5, 33 su M15) stanno entro lo
    0,2% (massimo / minimo - 1) e il Close e' >= la loro media x 1,001. Short: lo speculare sui minimi,
    Close <= media x 0,999. M5 e M15.
    """
    _lato_valido(lato)
    m = _minuti_ammessi(df.index, TF_MASSIMI_UGUALI, "massimi_uguali_rottura")
    if m is None:
        return _falsa(df)
    k, w = _barre_di(PIVOT_LATO_MINUTI, m), _barre_di(FINESTRA_PIVOT_MINUTI, m)
    v = df["Close"].to_numpy(dtype=float)
    n = len(v)
    pos = np.flatnonzero(pivot_chiusure(df["Close"], k, lato))
    out = np.zeros(n, dtype=bool)
    if len(pos) >= PIVOT_UGUALI:
        t = np.arange(n)
        quanti = np.searchsorted(pos, t - k, side="right")          # pivot confermati: posizione <= t - k
        ok = (quanti >= PIVOT_UGUALI) & (t >= w)                      # come la fonte: dalla barra w in poi
        q = np.clip(quanti, PIVOT_UGUALI, None)
        ultimi = np.stack([pos[q - PIVOT_UGUALI + i] for i in range(PIVOT_UGUALI)], axis=1)
        ok &= ultimi[:, 0] >= t - w + 1                              # tutti dentro la finestra
        prezzi = v[ultimi]
        with np.errstate(invalid="ignore", divide="ignore"):
            ok &= prezzi.max(axis=1) / prezzi.min(axis=1) - 1.0 <= BANDA_UGUALI
            media = prezzi.mean(axis=1)
            rotta = v >= media * (1 + BANDA_UGUALI / 2) if lato == 1 else v <= media * (1 - BANDA_UGUALI / 2)
        out = ok & rotta
    return pd.Series(out, index=df.index)


def livello_sweep(df: pd.DataFrame, lato: int) -> pd.Series:
    """
    Idea 4 (E49), il LIVELLO: l'ultimo minimo locale confermato dei Low (lato 1) o massimo degli High
    (lato -1). Un minimo e' il Low piu' basso fra 3 ore prima e 3 ore dopo (uguaglianze comprese, come la
    fonte) e si conferma 3 ore dopo; resta il livello finche' non se ne conferma uno nuovo, anche se e' gia'
    stato spazzato (la fonte lo porta avanti con ffill). NaN prima del primo. M5, M15, M30, H1.
    """
    _lato_valido(lato)
    m = _minuti_ammessi(df.index, TF_SWEEP, "livello_sweep")
    if m is None:
        return pd.Series(np.nan, index=df.index)
    k = _barre_di(SWEEP_LATO_MINUTI, m)
    x = (df["Low"] if lato == 1 else df["High"]).astype(float)
    estremo = x.rolling(2 * k + 1).min() if lato == 1 else x.rolling(2 * k + 1).max()
    confermato = (x.shift(k) == estremo).fillna(False).astype(bool)   # il pivot della barra i - k, noto alla barra i
    return x.shift(k).where(confermato).ffill()


def sweep_reclaim(df: pd.DataFrame, lato: int) -> pd.Series:
    """
    Idea 4 (E49), lo STATO: nell'ultima ora (candela oraria mobile, barra compresa) il Low e' andato sotto
    il livello di livello_sweep e il Close della barra e' sopra (long); lo speculare sul massimo (short,
    traduzione nostra: la fonte scrive solo il long). M5, M15, M30, H1.
    """
    _lato_valido(lato)
    m = _minuti_ammessi(df.index, TF_SWEEP, "sweep_reclaim")
    if m is None:
        return _falsa(df)
    h = _barre_di(SWEEP_CANDELA_MINUTI, m)
    livello = livello_sweep(df, lato)
    c = df["Close"].astype(float)
    if lato == 1:
        return ((df["Low"].rolling(h).min() < livello) & (c > livello)).fillna(False).astype(bool)
    return ((df["High"].rolling(h).max() > livello) & (c < livello)).fillna(False).astype(bool)


def salto_z(df: pd.DataFrame) -> pd.Series:
    """
    Idea 5 (E50): il rendimento logaritmico della barra diviso la deviazione standard dei rendimenti delle
    barre delle 15 ore PRIMA (barra esclusa, nessuna media tolta). M5, M15, M30, H1; NaN altrove.
    """
    m = _minuti_ammessi(df.index, TF_SALTO, "salto_z")
    if m is None:
        return pd.Series(np.nan, index=df.index)
    n = _barre_di(SALTO_FINESTRA_MINUTI, m)
    r = np.log(df["Close"].astype(float)).diff()
    return (r / r.rolling(n).std().shift(1)).rename("salto_z")


def salto_contro(df: pd.DataFrame, lato: int) -> pd.Series:
    """Idea 5 (E50), lo STATO: salto_z sotto -3 (long, contro la discesa) o sopra +3 (short)."""
    _lato_valido(lato)
    z = salto_z(df)
    return ((z < -SALTO_SOGLIA) if lato == 1 else (z > SALTO_SOGLIA)).fillna(False).astype(bool)


def movimento_volume_calo(df: pd.DataFrame, lato: int) -> pd.Series:
    """
    Idea 6 (E51), lo STATO (traduzione oraria tutta nostra): il movimento delle ultime 5 ore (Close meno
    Close di 5 ore prima), in valore assoluto, supera la deviazione standard dei movimenti a 5 ore delle
    ultime 100 ore, e il volume medio delle ultime 5 ore e' sotto quello delle 5 ore prima. Long se il
    movimento e' negativo, short se positivo (contro il movimento). M5, M15, M30, H1.
    """
    _lato_valido(lato)
    m = _minuti_ammessi(df.index, TF_MOVIMENTO_VOLUME, "movimento_volume_calo")
    if m is None:
        return _falsa(df)
    a, lunga = _barre_di(MOVIMENTO_MINUTI, m), _barre_di(DEVIAZIONE_MOVIMENTO_MINUTI, m)
    c = df["Close"].astype(float)
    mossa = c - c.shift(a)
    volume = df["Volume"].astype(float).rolling(a).mean()
    forte_e_calo = (mossa.abs() > mossa.rolling(lunga).std()) & (volume < volume.shift(a))
    verso = (mossa < 0) if lato == 1 else (mossa > 0)
    return (forte_e_calo & verso).fillna(False).astype(bool)


def area_rumore(df: pd.DataFrame, giorni: int = AREA_GIORNI,
                moltiplicatore: float = AREA_MOLTIPLICATORE) -> pd.DataFrame:
    """
    Idea 7 (E52), l'area di rumore (Zarattini, Aziz, Barbon). Giornata da 00:00 a 00:00 UTC; l'apertura e'
    l'Open della barra che inizia alle 00:00 (senza quella barra la giornata non ha area). I CONTROLLI sono
    le barre che FINISCONO alle HH:00 o HH:30 della stessa giornata (dalle 00:30 alle 23:30): l'indice
    delle barre e' l'INIZIO della barra, quindi su M15 il controllo delle 10:30 e' la barra con indice
    10:15. A ogni controllo sigma e' la media, sui 14 giorni PRIMA (tutti presenti), del movimento
    assoluto |Close / apertura - 1| allo stesso orario; i confini sono apertura x (1 +- sigma). La
    correzione per il gap del paper sparisce: sulle crypto la chiusura di ieri e' l'apertura di oggi.
    Colonne: controllo (bool), sigma, alto, basso (NaN fuori dai controlli). M5, M15, M30.
    """
    idx = pd.DatetimeIndex(df.index)
    out = pd.DataFrame({"controllo": False, "sigma": np.nan, "alto": np.nan, "basso": np.nan}, index=idx)
    m = _minuti_ammessi(idx, TF_AREA_RUMORE, "area_rumore")
    if m is None:
        return out
    chiusura = idx + pd.Timedelta(minutes=m)
    giorno = idx.floor("D")
    prima_barra = pd.Series(idx, index=idx).groupby(giorno).transform("first")
    apertura = df["Open"].astype(float).groupby(giorno).transform("first")
    apertura = apertura.where(np.asarray(prima_barra == giorno))
    minuto = np.asarray(chiusura.hour * 60 + chiusura.minute)
    controllo = ((minuto % AREA_CONTROLLO_MINUTI == 0) & np.asarray(chiusura.floor("D") == giorno)
                 & apertura.notna().to_numpy())
    if not controllo.any():
        return out
    mossa = (df["Close"].astype(float) / apertura - 1.0).abs().to_numpy()
    tab = pd.DataFrame({"giorno": giorno[controllo], "minuto": minuto[controllo], "mossa": mossa[controllo]}
                       ).pivot_table(index="giorno", columns="minuto", values="mossa", aggfunc="first")
    giorni_tutti = pd.date_range(tab.index.min(), tab.index.max(), freq="D", tz=tab.index.tz)
    media = tab.reindex(giorni_tutti).shift(1).rolling(int(giorni), min_periods=int(giorni)).mean()
    righe = media.index.get_indexer(giorno[controllo])
    colonne = media.columns.get_indexer(minuto[controllo])
    sigma = np.full(len(idx), np.nan)
    sigma[controllo] = media.to_numpy(dtype=float)[righe, colonne]
    ap = apertura.to_numpy()
    out["controllo"] = controllo
    out["sigma"] = sigma
    out["alto"] = ap * (1 + moltiplicatore * sigma)
    out["basso"] = ap * (1 - moltiplicatore * sigma)
    return out


def area_rumore_uscita(df: pd.DataFrame, lato: int) -> pd.Series:
    """
    Idea 7 (E52), l'EVENTO: a un controllo il Close e' sopra il confine alto (long) o sotto il basso
    (short) e al controllo prima della stessa giornata non lo era (il primo controllo della giornata non ha
    un «prima»: basta che sia fuori). Ogni uscita dall'area e' un evento, anche due nella stessa giornata.
    """
    _lato_valido(lato)
    area = area_rumore(df)
    valido = area["controllo"].to_numpy() & np.isfinite(area["sigma"].to_numpy())
    out = _falsa(df)
    if not valido.any():
        return out
    c = df["Close"].astype(float).to_numpy()
    fuori = (c > area["alto"].to_numpy()) if lato == 1 else (c < area["basso"].to_numpy())
    f = pd.Series(fuori[valido], index=df.index[valido])
    giorno = pd.DatetimeIndex(df.index[valido]).floor("D")
    prima = f.groupby(giorno).shift(1, fill_value=False).astype(bool)
    out.iloc[np.flatnonzero(valido)] = (f & ~prima).to_numpy()
    return out


# ------------------------------------------------------------------------
# Fabbrica di strategie (06/11/2026, docs/82 P-L2): gli indicatori che mancavano, con i periodi come
# parametri. FUORI da aggiungi_indicatori: le colonne del catalogo non cambiano.
# ------------------------------------------------------------------------

def donchian_massimo(df: pd.DataFrame, barre: int) -> pd.Series:
    """Il massimo degli High delle `barre` barre precedenti, barra corrente esclusa."""
    return df["High"].astype(float).rolling(int(barre)).max().shift(1)


def donchian_minimo(df: pd.DataFrame, barre: int) -> pd.Series:
    """Il minimo dei Low delle `barre` barre precedenti, barra corrente esclusa."""
    return df["Low"].astype(float).rolling(int(barre)).min().shift(1)


def atr_relativo(df: pd.DataFrame, breve: int, lungo: int) -> pd.Series:
    """ATR di `breve` barre diviso ATR di `lungo` barre: sopra 1 la volatilita' recente e' piu' alta del solito."""
    h, l, c = (df[k].astype(float) for k in ("High", "Low", "Close"))
    return ta.ATR(h, l, c, timeperiod=int(breve)) / ta.ATR(h, l, c, timeperiod=int(lungo))
