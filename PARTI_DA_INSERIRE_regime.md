# PARTI DA AGGIUNGERE — filtri di regime F25, F26 (e F27 opzionale)

Non riscrivere nessun file intero. Sono 5 interventi piccoli + 1 file nuovo.
Apri ogni file su GitHub (matita "Edit"), fai la modifica, poi "Commit changes".
Se lavori su Colab/PC, apri il file in un editor di testo e salva.

## Intervento 1 — `engine/indicatori.py`: due funzioni nuove
DOVE: subito PRIMA della riga `def aggiungi_indicatori(df: pd.DataFrame) -> pd.DataFrame:`
(dopo la fine della funzione `intraday_intensity`, lascia due righe vuote prima e dopo).
COSA: incolla questo blocco.

```python
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
```

## Intervento 2 — `engine/indicatori.py`: due righe dentro `aggiungi_indicatori`
DOVE: nella funzione `aggiungi_indicatori`, subito dopo la riga `df["iix"] = intraday_intensity(df)`
e prima di `return df.dropna()`. Stessa indentazione (4 spazi).

```python
    df["chop"] = indice_choppiness(df)
    df["vr"] = variance_ratio(df["Close"])
```

## Intervento 3 — `engine/indicatori.py`: elenco colonne
DOVE: in fondo al file, la lista `COLONNE_INDICATORI`. Dopo la riga che finisce con `"st_dir", "iix",` aggiungi:

```python
    "chop", "vr",
```

(Facoltativo: nel testo di spiegazione di `aggiungi_indicatori` aggiungi `chop, vr` all'elenco delle colonne.)

## Intervento 4 — `filter_conditions.py`: funzioni dei filtri
DOVE: subito PRIMA della riga `FILTRI = {` (dopo `filter_two_bars_down`). Gli import in alto bastano già (`np`, `pd`, `ts_rank` ci sono).

```python
def _stato_isteresi(rango: pd.Series, entra: float, esce: float, basso: bool) -> pd.Series:
    """
    Stato "acceso/spento" con isteresi, da un percentile rolling (0-1).

    Una soglia sola fa sfarfallare lo stato quando il valore le gira
    attorno. Qui lo stato si ACCENDE con una soglia e si SPEGNE con un'altra,
    piu' lontana: una volta acceso resta acceso finche' il percentile non
    torna oltre la soglia di uscita. Nessuna media sul valore di partenza:
    non si aggiunge ritardo all'indicatore, solo all'uscita dallo stato.

        basso=True   acceso quando rango <= entra, spento quando rango > esce
        basso=False  acceso quando rango >= entra, spento quando rango < esce

    Rango non disponibile (NaN): lo stato si spegne, come ogni condizione
    del progetto quando manca la storia. Parte spento.

    Lo stato ha MEMORIA: dipende dalla storia dall'inizio dei dati, fino
    all'ultima volta in cui si e' spento. Il percentile torna sopra la soglia
    di uscita spesso, quindi la memoria si azzera presto: il collaudo
    (test_regime.py) verifica che dopo 60 barre di rango casuale, e dopo 3000
    barre di dati veri, il punto di partenza dei dati non cambi niente.

    Idea: l'articolo "Can We Detect a Market Crash Before It Happens? I
    Tested 5 Regime Filters" (PyQuantLab, 7/9/2026,
    https://pyquantlab.medium.com/can-we-detect-a-market-crash-before-it-happens-i-tested-5-regime-filters-c45290f652fa)
    tiene l'allarme acceso finche' il prezzo non rientra sopra una media
    esponenziale. Qui l'uscita e' una soglia sul percentile (l'articolo non
    dichiara il periodo della media): traduzione nostra.
    """
    r = rango.to_numpy(dtype=float)
    acceso = np.zeros(len(r), dtype=bool)
    stato = False
    for i, x in enumerate(r):
        if not np.isfinite(x):
            stato = False
        elif stato:
            if (x > esce) if basso else (x < esce):
                stato = False
        else:
            if (x <= entra) if basso else (x >= entra):
                stato = True
        acceso[i] = stato
    return pd.Series(acceso, index=rango.index)


# --- F25: choppiness ------------------------------------------------------

def filter_chop_trend(df: pd.DataFrame, rank_window: int = 500,
                      entra: float = 0.25, esce: float = 0.50) -> pd.Series:
    """
    Regime di TENDENZA: choppiness bassa. Il Choppiness Index a 14 barre
    (colonna `chop`) entra sotto il 25° percentile delle proprie ultime 500
    barre e ne esce quando risale sopra il 50° (isteresi, vedi
    `_stato_isteresi`).

    Neutro (direction 0): misura quanto il prezzo marcia in linea retta, non
    in che verso. La finestra del percentile (500) e' molto piu' larga di
    quella dell'indicatore (14), come vuole la regola 2 dei filtri.
    Parametri scelti a priori e mai provati in varianti. Finestra massima:
    circa 515 barre.

    Fonte: PyQuantLab, "Can We Detect a Market Crash Before It Happens? I
    Tested 5 Regime Filters", 7/9/2026 (URL in `_stato_isteresi`). Percentili,
    isteresi e uso senza segno di momentum: traduzione nostra.
    """
    return _stato_isteresi(ts_rank(df["chop"], rank_window), entra, esce, basso=True)


def filter_chop_range(df: pd.DataFrame, rank_window: int = 500,
                      entra: float = 0.75, esce: float = 0.50) -> pd.Series:
    """
    Regime LATERALE: choppiness alta. Speculare di F25_CHOP_TREND: entra
    sopra il 75° percentile, esce quando scende sotto il 50°.

    E' un filtro a se', non il "contrario" del precedente: i due non sono
    mai veri insieme, ma nella zona di mezzo possono essere entrambi falsi.
    Si prova da solo (serve alle entry di rimbalzo). Neutro. Finestra
    massima: circa 515 barre.
    """
    return _stato_isteresi(ts_rank(df["chop"], rank_window), entra, esce, basso=False)


# --- F26: variance ratio --------------------------------------------------

def filter_variance_ratio_trend(df: pd.DataFrame, rank_window: int = 1000,
                                entra: float = 0.75, esce: float = 0.50) -> pd.Series:
    """
    Regime di PERSISTENZA: il variance ratio a 4 barre su 192 (colonna `vr`)
    entra sopra il 75° percentile delle proprie ultime 1000 barre e ne esce
    quando scende sotto il 50° (isteresi).

    Neutro: misura se i rendimenti tendono a ripetersi o a rimbalzare, non
    il verso. La finestra del percentile (1000) e' circa 5 volte quella
    dell'indicatore (192), come per F14. Parametri scelti a priori e mai
    provati in varianti. Finestra massima: circa 1200 barre.

    Idea (non dell'articolo): alternativa piu' leggera all'esponente di
    Hurst proposto da PyQuantLab, "Enhancing Trading Strategies With a
    Hurst-Based Regime Filter", 6/3/2026 (URL in `variance_ratio`).
    """
    return _stato_isteresi(ts_rank(df["vr"], rank_window), entra, esce, basso=False)


# --- F27 (OPZIONALE): regime di tendenza composito ------------------------

def _adx_forte(df: pd.DataFrame, rank_window: int = 500,
               entra: float = 0.75, esce: float = 0.50) -> pd.Series:
    """ADX (colonna `adx`) alto rispetto alle proprie ultime 500 barre, con isteresi. Neutro."""
    return _stato_isteresi(ts_rank(df["adx"], rank_window), entra, esce, basso=False)


def filter_regime_trend_composite(df: pd.DataFrame, voti_minimi: int = 2) -> pd.Series:
    """
    Regime di tendenza "a consenso": vero quando almeno `voti_minimi` su 3
    misure di tendenza concordano, ciascuna col suo stato a isteresi:

      1. choppiness bassa   (F25_CHOP_TREND)
      2. persistenza alta   (F26_VARIANCE_RATIO_TREND)
      3. ADX alto           (colonna `adx`, 500 barre, 75°/50°)

    Perche' un voto e non una media: le tre misure guardano lo stesso
    prezzo in tre modi diversi (lunghezza del percorso, autocorrelazione,
    forza direzionale) e sbagliano in momenti diversi. Il consenso toglie
    rumore SENZA aggiungere ritardo nel tempo: non c'e' nessuna media mobile
    in piu'. Le tre misure guardano scale diverse (14 barre, 192 barre, ADX
    lungo) e sono poco correlate fra loro (0,02-0,17 su EURUSD): il voto e'
    un consenso fra orizzonti diversi. Il prezzo e' che quello piu' reattivo
    (CHOP) e l'ADX dominano la durata degli stati.

    Neutro. Tutti i parametri sono quelli dei tre componenti (nessuno nuovo
    tranne il numero di voti: 2 su 3). E' UNA prova sola, ma i componenti
    1 e 2 sono prove a parte. Finestra massima: circa 1200 barre.

    Idea dell'insieme (traduzione nostra, proposta da Mattia il 9/10/2026):
    voto fra segnali di regime come in PyQuantLab, "Regime Filtered Trend
    Strategy", 12/7/2025, https://pyquantlab.medium.com/regime-filtered-trend-strategy-a-market-adaptive-trend-following-system-fa933e001237
    (3 su 4 segnali) e nell'articolo del 7/9/2026 citato sopra (almeno 2 su
    5). Componenti e soglie sono nostri: nelle fonti sono assoluti e tarati
    su BTC giornaliero.
    """
    voti = (filter_chop_trend(df).astype(int)
            + filter_variance_ratio_trend(df).astype(int)
            + _adx_forte(df).astype(int))
    return voti >= int(voti_minimi)
```

## Intervento 5 — `filter_conditions.py`: righe nel dizionario FILTRI
DOVE: dentro `FILTRI = { ... }`, dopo la riga `"F24_TWO_BARS_DOWN": ...`, prima della `}` finale.
La riga F27 resta commentata (con `#`): si attiva solo se la approvi.

```python
    "F25_CHOP_TREND":            (filter_chop_trend, 0, None),
    "F25_CHOP_RANGE":            (filter_chop_range, 0, None),
    "F26_VARIANCE_RATIO_TREND":  (filter_variance_ratio_trend, 0, None),
    # F27: OPZIONALE, togli il "#" solo se approvato (conta 1 prova in piu')
    # "F27_REGIME_TREND_COMPOSITE": (filter_regime_trend_composite, 0, None),
```

## Intervento 6 — `test_idee_articoli.py`: un controllo vecchio da aggiornare
Il controllo C7 vietava i nomi F25/F26/F27 (numeri allora liberati); ora sono i nuovi filtri.
DOVE: la riga che inizia con `check("C7.` (2 righe). Sostituiscila con:

```python
    nuovi_regime = {"F25_CHOP_TREND", "F25_CHOP_RANGE", "F26_VARIANCE_RATIO_TREND",
                    "F27_REGIME_TREND_COMPOSITE"}
    check("C7. i filtri PVO e IIX non ci sono piu', le due candele non sono piu' F26 (F25-F27 ora sono i filtri di regime)",
          not any(k.startswith(("F25", "F26", "F27")) and k not in nuovi_regime
                  or "PVO" in k or "IIX" in k for k in FILTRI))
```

## File NUOVO — `test_regime.py`
Questo è l'unico file intero: caricalo nella cartella principale del repo, accanto a `test_idee_articoli.py`.

## Come si esegue
1. Dopo gli interventi, nella cartella del progetto: `python test_regime.py`
   Atteso: ultima riga `RISULTATO: 41/41 test superati`.
2. Poi `python test_idee_articoli.py` → atteso `64/64`.
3. Su Colab: riavvia il runtime (così i dizionari si ricaricano) e rilancia `Collaudo_Catalogo.ipynb`:
   A1/A2 tutti superati; B con 0 LOOKAHEAD e 0 ERRORE; D/E superati.
4. Se un numero non torna, non modificare niente: incollami l'output.
