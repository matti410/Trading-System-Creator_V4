"""
Condizioni di FILTER.

Un filtro viene sempre messo in AND con la condizione di Entry: la
strategia entra solo quando l'Entry E TUTTI i filtri assegnati sono veri
contemporaneamente. Stessa firma delle altre condizioni: funzione(df) ->
Series booleana.

Adattato allo stile V4 (17-18/9): niente decoratori applicati alla
definizione — a differenza della versione precedente, la registrazione nel
motore avviene tramite `registra_filtri()`, chiamata a mano nel notebook.
Stesso pattern di `registra_trigger_long()` in entry_long.py e
`registra_exit_long()` in exit_long.py: un dizionario nome -> (funzione,
direction), e un bridge idempotente verso `engine.registry.register_filter`.


LA DIREZIONE DI UN FILTRO
-------------------------
`register_filter(nome, direction=...)` dichiara a quale lato del mercato
il filtro appartiene:

    +1  descrive uno stato di mercato RIALZISTA
    -1  descrive uno stato di mercato RIBASSISTA
     0  neutro rispetto alla direzione (volatilita', volume, regime)

Serve alla grid search dei filtri: su un sistema solo long si provano i
neutri piu' quelli +1, senza sprecare campione su filtri che per
costruzione lavorano contro l'ingresso.

ATTENZIONE, ED E' IL PUNTO PIU' DELICATO DEL FILE. `direction` descrive
lo STATO DI MERCATO che il filtro individua, non il verso dell'entry con
cui va accoppiato. Per un'entry di CONTINUAZIONE i due coincidono: un
Marubozu rialzista vuole contesto rialzista. Per un'entry di INVERSIONE
si rovesciano: un Engulfing rialzista di esaurimento vuole contesto
RIBASSISTA, cioe' un filtro -1 su un ingresso long.

Quindi `direction` e' un DEFAULT ragionevole, non una regola. Su entry di
inversione va usato l'insieme completo dei filtri e lasciato decidere ai
dati — che era la scelta originale documentata in F8/F9 e che resta
valida.

Nota per questo percorso (V4, 18/9): la pipeline Trend Following usa
`direction` cosi' com'e' (filtro e entry stessa direzione = conferma). La
pipeline Mean Reverting, quando riparte, la usa rovesciata (filtro
opposto all'entry).


COPPIE DI FILTRI (`pair`) — AGGIUNTA 18/9/2026
------------------------------------------------
Un filtro come F12_EXTENDED_UP/F13_EXTENDED_DOWN e' una singola idea
("il prezzo e' esteso rispetto alla media") che ha due facce, una per
direzione. Testarli come due righe indipendenti nella grid search (F12 sul
solo long, F13 sul solo short, ciascuna a se') e' due esperimenti diversi
("l'estensione aiuta il long da sola?", "aiuta lo short da sola?"), non lo
stesso esperimento di un sistema che richiede l'estensione coerente su
entrambe le gambe. Per questo le coppie dichiarate qui sotto vengono
raccolte in un'UNICA riga dalla grid search (vedi
`engine.filter_search_bt`): il membro +1 va sul lato long, il -1 sul lato
short, nella stessa riga — stessa logica gia' in uso per `exit_rule_pairs`.

COME REGISTRARE UN FILTRO NUOVO (leggi questo prima di aggiungerne uno):

1. NEUTRO/SIMMETRICO PER NATURA (misura una magnitudine, non ha verso —
   volatilita', volume, coerenza) -> `direction=0`, NESSUN `pair`. Si
   applica sempre a entrambi i lati attivi, come oggi.

2. DIREZIONALE CON UNO SPECULARE NATURALE -> scrivi le due funzioni
   insieme, stesso `pair`, direction opposte: la versione "su" con
   `direction=1, pair="ETICHETTA"`, la versione "giu'" con
   `direction=-1, pair="ETICHETTA"`. La grid search le trova da sola e le
   testa in un'unica riga.

3. DIREZIONALE SENZA SPECULARE (idea a senso unico, o lo speculare non e'
   ancora stato scritto) -> `direction=±1`, SENZA `pair`. Resta testato da
   solo sul proprio unico lato compatibile — comportamento invariato,
   nessun obbligo di scrivere sempre una coppia.

4. Se in futuro scrivi lo speculare mancante di un filtro del punto 3
   (diventa punto 2): aggiungi `pair="ETICHETTA"` a ENTRAMBE le
   registrazioni — quella nuova e quella vecchia, va editata anche lei.
   Da quel momento vengono raccolte insieme automaticamente, nessun'altra
   modifica al motore.

GUARDIA EREDITATA da `list_exit_pairs()`: se un'etichetta `pair` finisce
condivisa da piu' di un filtro +1 o piu' di un -1 (ambiguo), quella coppia
viene scartata con un avviso stampato, non un errore — i suoi membri, se
richiesti singolarmente, tornano al comportamento standalone del punto 3.

SE IL TRIGGER DI INGRESSO E' A UN SOLO LATO (solo long o solo short): la
grid search applica solo il membro della coppia compatibile con quel lato
e etichetta la riga col nome del singolo filtro, non con l'etichetta della
coppia — la coppia come unita' unica ha senso solo quando entrambi i lati
del trigger sono davvero attivi. Nessun errore, nessuna riga inventata per
il lato assente.


PROVENIENZA E SCARTI
--------------------
I filtri da F10 in poi derivano dai "101 Formulaic Alphas" (Kakushadze,
WorldQuant, 2015 - arXiv:1601.00991). Vivevano in un file separato per
provenienza; sono stati uniti qui perche' dividere per provenienza e' un
criterio debole: si cercano "i filtri di trend", non "i filtri Alpha101".

Del set originale sono stati ELIMINATI, e non vanno reintrodotti senza
rifare l'analisi:

A8_OPEN_RETURNS_SHOCK
    `sum(open,5) * sum(returns,5)`: su BTC il primo fattore vale
    centinaia di migliaia e trenda con il prezzo, il secondo oscilla
    intorno a zero. Il prodotto e' dominato dal LIVELLO del prezzo, non
    dallo shock di rendimento che dovrebbe misurare. Serie non
    stazionaria: il filtro misura il 2021 contro il 2026.

A20_GAP_ANOMALY
    Doppio problema. Su cripto H24 il gap d'apertura non esiste: `Open`
    coincide praticamente sempre con il `Close` precedente, quindi i tre
    termini sono rumore intorno a zero. E c'e' un bug di soglia: il
    prodotto di tre percentili in [0,1] supera 0.5 in una frazione
    minima dei casi, il filtro non scatterebbe quasi mai.

A30 - parte volume
    `sum(volume,5)/sum(volume,20)` poggia sul tick volume di MetaTrader,
    che su BTCUSD CFD e' il numero di variazioni di prezzo registrate dal
    feed del singolo broker, non il volume scambiato. La parte sulla
    coerenza delle ultime variazioni e' invece pulita e sopravvive da
    sola, qui sotto, come F15_SHORT_TERM_CONSISTENCY.

Sono state eliminate anche tutte le entry e le bidirezionali Alpha101:
rank cross-sezionale non trasferibile su asset singolo, tick volume del
broker inaffidabile, segno fisso che e' una magnitudine e non una
direzione.


NOTA SUL VWAP (riguarda F16/F17)
--------------------------------
Su un asset H24 l'ancoraggio giornaliero del VWAP e' una convenzione, non
un fatto. Mezzanotte UTC e' lo standard piu' diffuso su cripto, ma se il
feed IC Markets e' su fuso broker (tipicamente UTC+2/+3) il reset cade a
meta' sessione asiatica e il filtro si sposta in modo non banale.
Verificare su quale ora ancora `engine.vwap_ops.vwap_anchored_daily`
prima di dare peso ai risultati di questi due filtri.
"""
import numpy as np
import pandas as pd

from engine.alpha_ops import delta, ts_rank, ts_sum
from engine.livelli import al_ultima_apertura, quarantena_cached, range_finestra
from engine.sessioni import in_sessione


# ======================================================================
# Neutri - volatilita', volume, regime
# ======================================================================

def filter_adx_above(df: pd.DataFrame, threshold: float = 20.0) -> pd.Series:
    """ADX sopra soglia. Misura la FORZA del trend, non il verso: neutro."""
    return df["adx"] > threshold


def filter_low_volatility(df: pd.DataFrame, window: int = 500,
                          percentile: float = 0.35) -> pd.Series:
    """
    Volatilita' BASSA

    Una soglia fissa in unita' di prezzo non e' trasferibile: il valore
    giusto per EURUSD non lo e' per XAUUSD, e non lo e' nemmeno per EURUSD
    fra due regimi di volatilita' diversi. Si usa il percentile rolling
    dell'ATR sulla propria storia recente, cosi' il filtro si auto-adatta
    a strumento, timeframe e regime - stessa scelta fatta in
    F14_LOW_DRIFT_REGIME per lo stesso motivo.

    window=500 su M15 sono circa 5 giorni di contrattazione.
    percentile=0.5 seleziona la meta' piu' volatile; alza a 0.7 per essere
    piu' severo.
    """
    soglia = df["atr"].rolling(int(window)).quantile(percentile)
    return df["atr"] <= soglia


def filter_mid_volatility(df: pd.DataFrame, window: int = 500,
                          percentile: float = 0.75) -> pd.Series:
    """
    Volatilita' MEDIA

    Una soglia fissa in unita' di prezzo non e' trasferibile: il valore
    giusto per EURUSD non lo e' per XAUUSD, e non lo e' nemmeno per EURUSD
    fra due regimi di volatilita' diversi. Si usa il percentile rolling
    dell'ATR sulla propria storia recente, cosi' il filtro si auto-adatta
    a strumento, timeframe e regime - stessa scelta fatta in
    F14_LOW_DRIFT_REGIME per lo stesso motivo.

    window=500 su M15 sono circa 5 giorni di contrattazione.
    percentile=0.5 seleziona la meta' piu' volatile; alza a 0.7 per essere
    piu' severo.
    """
    soglia = df["atr"].rolling(int(window)).quantile(percentile)
    return df["atr"] <= soglia


def filter_high_volatility(df: pd.DataFrame, window: int = 500,
                          percentile: float = 0.75) -> pd.Series:
    """
    Volatilita' ALTA

    Una soglia fissa in unita' di prezzo non e' trasferibile: il valore
    giusto per EURUSD non lo e' per XAUUSD, e non lo e' nemmeno per EURUSD
    fra due regimi di volatilita' diversi. Si usa il percentile rolling
    dell'ATR sulla propria storia recente, cosi' il filtro si auto-adatta
    a strumento, timeframe e regime - stessa scelta fatta in
    F14_LOW_DRIFT_REGIME per lo stesso motivo.

    window=500 su M15 sono circa 5 giorni di contrattazione.
    percentile=0.5 seleziona la meta' piu' volatile; alza a 0.7 per essere
    piu' severo.
    """
    soglia = df["atr"].rolling(int(window)).quantile(percentile)
    return df["atr"] > soglia


def filter_volume_above_avg(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Volume sopra la propria media mobile."""
    return df["Volume"] > df["Volume"].rolling(window).mean()


def filter_tall_candle(df: pd.DataFrame, window: int = 20,
                       multiplier: float = 1.5) -> pd.Series:
    """
    Range (High-Low) della barra corrente sopra `multiplier` volte la
    propria media mobile recente -> candela "alta"/di convinzione.
    E' il fattore con l'evidenza piu' forte trovata nella ricerca (piu'
    robusto del volume secondo i test di Bulkowski): non un filtro
    generico qualsiasi, e' quello da provare per primo.
    """
    candle_range = df["High"] - df["Low"]
    avg_range = candle_range.rolling(window).mean()
    return candle_range > avg_range * multiplier


def filter_volume_above_avg_50(df: pd.DataFrame, window: int = 50) -> pd.Series:
    """
    Stessa logica di F3, finestra 50 invece di 20 -> l'ipotesi originale
    di volume "sopra media" con orizzonte piu' lungo, tenuta come
    variante a parita' di logica.
    """
    return df["Volume"] > df["Volume"].rolling(window).mean()


def filter_volume_climax(df: pd.DataFrame, window: int = 50,
                         quantile: float = 0.9) -> pd.Series:
    """
    Volume sopra il `quantile`-esimo percentile della propria finestra
    recente (default 90), non semplicemente sopra la media come F3/F6.
    Copre l'ipotesi diversa di "climax/esaurimento" (tipica dei pattern
    di reversal), distinta da "partecipazione sostenuta sopra media"
    (piu' adatta ai pattern di continuation).
    """
    threshold = df["Volume"].rolling(window).quantile(quantile)
    return df["Volume"] > threshold


def filter_low_drift_regime(
    df: pd.DataFrame,
    window: float = 100,
    rank_window: float = 500,
    percentile: float = 0.3,
) -> pd.Series:
    """
    (ex A24) Alpha#24 del paper: usa
    `delta(sum(close,100)/100,100)/delay(close,100) < 0.05` come innesco
    per scegliere fra due rami di comportamento. Qui isolato come filtro
    di regime a se'.

    DUE CORREZIONI rispetto alla versione originale.

    1. Il confronto era unilaterale (`drift < 0.05`) e quindi non
       misurava affatto la bassa direzionalita': un mercato in forte
       discesa ha drift molto negativo e passava il filtro senza
       problemi. Diceva "non fortemente rialzista", non "poco
       direzionale". Ora si usa il valore assoluto.

    2. La soglia 0.05 e' un default da dati daily. Su M15 il drift a 100
       barre (25 ore) non la raggiunge praticamente mai: verificato
       empiricamente su 20.000 barre, il filtro risultava True nel 99%
       dei casi - cioe' non filtrava niente. Al posto della magnitudine
       fissa si usa il PERCENTILE ROLLING del drift sulla propria storia
       recente: il filtro si auto-adatta al timeframe e al regime di
       volatilita', e non ha piu' nessun numero calibrato a mano sulla
       scala del prezzo.

    True quando il drift assoluto della media a `window` barre e' nel
    `percentile` piu' basso delle ultime `rank_window` barre - regime di
    consolidamento, che tipicamente precede un breakout e non e' di per
    se' un trigger di ingresso.

    Neutro per costruzione: il valore assoluto rende la domanda "quanto
    poco si muove", che non ha verso.
    """
    sma = df["Close"].rolling(int(window)).mean()
    drift = (delta(sma, window) / df["Close"].shift(int(window))).abs()
    return ts_rank(drift, rank_window) < percentile


def filter_short_term_consistency(
    df: pd.DataFrame,
    consistency_threshold: int = 2,
) -> pd.Series:
    """
    (ex A30) Alpha#30 del paper, ridotta alla sola componente di coerenza
    di segno: `sign(close-delay(close,1)) + sign(delay(close,1)-delay(close,2))
    + sign(delay(close,2)-delay(close,3))`.

    True quando almeno `consistency_threshold` delle ultime 3 variazioni
    sono concordi in segno - micro-trend coerente a brevissimo termine,
    indipendente dal verso (si usa il valore assoluto della somma).

    Neutro per costruzione: il valore assoluto unisce le micro-serie al
    rialzo e quelle al ribasso, ed e' corretto perche' la domanda e' "c'e'
    coerenza?", non "in che verso". Si potrebbe spaccare in due per
    guadagnare informazione, ma si perderebbe la domanda originale.

    Il fattore di ponderazione sul volume del paper e' stato rimosso: vedi
    la nota sugli scarti in cima al file.
    """
    segno = np.sign(df["Close"].diff().fillna(0.0))
    coerenza = (segno + segno.shift(1) + segno.shift(2)).abs()
    return coerenza >= consistency_threshold


# ======================================================================
# Direzionali - a coppie speculari
# ======================================================================

def filter_macd_above_signal(df: pd.DataFrame) -> pd.Series:
    """MACD sopra la signal line (conferma di momentum rialzista)."""
    return df["macd"] > df["macd_signal"]


def filter_macd_below_signal(df: pd.DataFrame) -> pd.Series:
    """MACD sotto la signal line (conferma di momentum ribassista)."""
    return df["macd"] < df["macd_signal"]


def filter_uptrend_context(df: pd.DataFrame) -> pd.Series:
    """
    Prezzo sopra l'EMA50 -> contesto di trend rialzista in corso.

    NOTA STORICA, ancora valida. La versione precedente non aveva
    direction, e il docstring motivava la scelta: sta alla ricerca
    combinatoria scoprire empiricamente se un dato pattern funziona
    meglio ALLINEATO al trend (continuation, es. Marubozu/Belt-hold) o
    CONTRO il trend precedente (reversal da esaurimento, es. Engulfing/
    Harami). Quel ragionamento non e' stato buttato: direction=1 dice
    "questo filtro individua un mercato che sale", che e' un fatto, e
    resta un DEFAULT per gli ingressi di continuazione. Su un'entry di
    inversione vanno provati tutti i filtri, non solo quelli concordi.
    """
    return df["Close"] > df["ema50"]


def filter_downtrend_context(df: pd.DataFrame) -> pd.Series:
    """Speculare di F8: prezzo sotto l'EMA50 -> trend ribassista in corso."""
    return df["Close"] < df["ema50"]


def filter_trend_conviction_up(
    df: pd.DataFrame,
    lookback: float = 350,
    rank_window: float = 500,
    threshold: float = 0.7,
) -> pd.Series:
    """
    (ex A19_TREND_CONVICTION) Alpha#19 del paper:
    `(-1*sign(...)) * (1+rank((1+sum(returns,250))))`. Si usa solo la
    seconda componente; gli `1+` esterni si elidono nel confronto con una
    soglia, quindi la condizione e' "il rendimento cumulato sulle ultime
    `lookback` barre e' nel percentile alto della propria storia recente".

    CORREZIONE IMPORTANTE. Il docstring precedente dichiarava che si
    usava solo la MAGNITUDO del trend di fondo, "mai il fattore di
    segno", e concludeva che il filtro fosse indipendente dal verso. Non
    lo era: `ts_sum(returns, lookback)` e' il rendimento CUMULATO, una
    grandezza con segno, non una magnitudine. Stare nel percentile alto
    significa "il cumulato e' vicino al suo massimo recente", cioe'
    deriva rialzista. Il filtro e' quindi direzionale long, ed e' ora
    dichiarato tale. F11 e' lo speculare che mancava.

    DUE FINESTRE DISTINTE, e vanno tenute distinte:
      lookback     su quante barre si somma il rendimento (350)
      rank_window  su quante barre si calcola il PERCENTILE (500)

    `rank_window` era 20, cioe' un percentile stimato su venti
    osservazioni. Allineato a 500 come in F14, che fa la stessa
    operazione. Alzare `lookback` tenendo `rank_window` corta peggiora le
    cose: un cumulato a 350 barre si muove lentamente, su 20 barre cambia
    pochissimo, e il percentile finirebbe per misurare il contributo
    delle ultime manciate di barre invece della posizione del trend.

    Riscaldamento: lookback + rank_window barre (circa 9 giorni su M15).
    """
    returns = df["Close"].pct_change()
    return ts_rank(ts_sum(returns, lookback), rank_window) > threshold


def filter_trend_conviction_down(
    df: pd.DataFrame,
    lookback: float = 350,
    rank_window: float = 500,
    threshold: float = 0.7,
) -> pd.Series:
    """
    Speculare di F10: il rendimento cumulato e' nel percentile BASSO della
    propria storia recente - deriva ribassista di fondo.

    La soglia si specchia (`< 1 - threshold`) invece di essere un secondo
    numero indipendente, cosi' i due filtri restano simmetrici per
    costruzione: con threshold=0.7 F10 prende il 30% piu' alto e F11 il
    30% piu' basso. Cambiando un solo parametro si muovono entrambi,
    ed e' impossibile tararli di fino uno contro l'altro per sbaglio.
    """
    returns = df["Close"].pct_change()
    return ts_rank(ts_sum(returns, lookback), rank_window) < (1.0 - threshold)


def filter_extended_up(
    df: pd.DataFrame,
    long_window: float = 8,
    short_window: float = 2,
) -> pd.Series:
    """
    (ex A21_PRICE_EXTENDED_FROM_MEAN, ramo rialzista) Alpha#21 del paper:
    struttura a tre rami sul confronto fra media mobile lunga (piu' o meno
    la deviazione standard) e media mobile corta. Qui ridotta al nucleo di
    "estensione di prezzo".

    PERCHE' E' STATO SPACCATO IN DUE. La versione originale restituiva
    `estesa_giu | estesa_su`, cioe' un OR fra due rami OPPOSTI: si
    accendeva sia quando il prezzo era esteso al rialzo sia quando lo era
    al ribasso. Per un'entry direzionale quelle due popolazioni non sono
    equivalenti - una e' continuazione, l'altra e' ritorno alla media - e
    mescolarle in un unico booleano produce un filtro che seleziona due
    gruppi che si contraddicono, col risultato medio vicino a niente
    qualunque sia il merito delle due meta'.

    Il resto della base di codice questo problema lo aveva gia' risolto:
    F18/F19 sono la stessa idea gia' divisa in due.

    True quando la media corta e' uscita SOPRA la banda
    SMA(long) + stddev(long). Normalizzato sulla deviazione standard,
    quindi scale-free e auto-adattivo alla volatilita' del momento.

    Il ramo sul volume del paper e' omesso: e' coperto separatamente da
    F3_VOLUME_ABOVE_AVG.
    """
    sma_long = df["Close"].rolling(int(long_window)).mean()
    std_long = df["Close"].rolling(int(long_window)).std()
    sma_short = df["Close"].rolling(int(short_window)).mean()
    return sma_short > (sma_long + std_long)


def filter_extended_down(
    df: pd.DataFrame,
    long_window: float = 8,
    short_window: float = 2,
) -> pd.Series:
    """
    Speculare di F12: la media corta e' scesa SOTTO la banda
    SMA(long) - stddev(long).
    """
    sma_long = df["Close"].rolling(int(long_window)).mean()
    std_long = df["Close"].rolling(int(long_window)).std()
    sma_short = df["Close"].rolling(int(short_window)).mean()
    return sma_short < (sma_long - std_long)


def filter_price_above_vwap(df: pd.DataFrame) -> pd.Series:
    """
    (ex A41_PRICE_ABOVE_VWAP) Alpha#41 del paper: sqrt(high*low) - vwap,
    qui come filtro booleano di posizionamento. True quando la media
    geometrica di High/Low e' sopra il VWAP - regime "prezzo forte
    rispetto al fair value della sessione".

    Concettualmente il piu' adatto all'intraday di tutto il gruppo, ed e'
    l'unico che usa il volume senza esserne danneggiato: il VWAP e' una
    media di prezzi PESATA per volume, quindi molto piu' robusto alla
    qualita' del tick volume di quanto lo sia un rapporto di volumi.

    Richiede df["vwap"] - vedi engine.vwap_ops.vwap_anchored_daily e la
    nota sull'ancoraggio in cima al file.
    """
    mid_geometrico = (df["High"] * df["Low"]) ** 0.5
    return mid_geometrico > df["vwap"]


def filter_price_below_vwap(df: pd.DataFrame) -> pd.Series:
    """Speculare di F16: prezzo sotto il VWAP di sessione."""
    mid_geometrico = (df["High"] * df["Low"]) ** 0.5
    return mid_geometrico < df["vwap"]


def filter_high_near_range_top(
    df: pd.DataFrame,
    window: float = 9,
    threshold: float = 0.25,
) -> pd.Series:
    """
    (ex A4_HIGH_NEAR_RANGE_TOP) True quando il massimo della barra e'
    nella parte ALTA del proprio range recente.

    Si usa ts_rank(-High) invece di ts_rank(High) > 1-threshold perche'
    ts_rank su `window` barre assume solo `window` valori discreti: con
    window=9 e threshold=0.25 il filtro basso cattura le posizioni 1 e 2,
    mentre "> 0.75" ne catturerebbe TRE (7, 8, 9). Negando la serie il
    rank riparte dall'alto e la soglia 0.25 cattura esattamente le due
    posizioni piu' alte - stessa selettivita' del gemello, che e' il punto.

    Su direction: e' un filtro POSIZIONALE, non di trend. direction=1
    perche' descrive prezzo forte, ma su un'entry di inversione
    (esaurimento) l'accoppiamento utile e' l'opposto. Vedi la nota in
    cima al file.
    """
    return ts_rank(-df["High"], window) < threshold


def filter_low_near_range_bottom(
    df: pd.DataFrame,
    window: float = 9,
    threshold: float = 0.25,
) -> pd.Series:
    """
    (ex A4_LOW_NEAR_RANGE_BOTTOM) Alpha#4 del paper:
    -1*Ts_Rank(rank(low),9). Il rank cross-sezionale interno e' rimosso
    (privo di senso su asset singolo, l'outer ts_rank basta): qui si usa
    direttamente ts_rank(Low, window).

    True quando il minimo della barra e' nella parte bassa del proprio
    range recente - regime di possibile supporto/ipervenduto.

    ATTENZIONE alla granularita': ts_rank su `window` barre assume solo
    `window` valori discreti (1/window, 2/window, ..., 1), quindi il
    minimo raggiungibile e' 1/window. Con window=9 il minimo e' ~0.111 e
    una soglia sotto quel valore non farebbe mai scattare il filtro. Il
    default 0.25 include le due posizioni piu' basse.

    Stessa avvertenza di F18: filtro posizionale, direction e' un default.
    """
    return ts_rank(df["Low"], window) < threshold


# nome -> (funzione, direction, pair)
# =========================================================================
# FILTRI DI TEMPO  (F20-F22, aggiunti 22/9/2026)
#
# Usano le primitive di engine/sessioni.py: sessioni definite in ora LOCALE
# di borsa, con il DST gestito da pandas. Un filtro orario scritto in ora
# server sbaglia di un'ora nelle ~4 settimane l'anno in cui il DST
# americano ed europeo sono sfasati: non genera errori, falsa il backtest
# in silenzio.
#
# Tutti escludono le barre in quarantena (finestra del rollover, dove i
# prezzi bid sono deformati dall'allargamento dello spread).
# =========================================================================


def _quarantena(df: pd.DataFrame) -> pd.DataFrame:
    return quarantena_cached(df)


# --- F20: dentro quale sessione siamo ------------------------------------
# direction=0: stare dentro una sessione non dice niente su rialzo o
# ribasso. E' la regola "direction=0 solo se usa davvero la sola magnitudo"
# applicata correttamente.

def filter_session_asia(df: pd.DataFrame) -> pd.Series:
    """Dentro la sessione di Tokyo (09:00-18:00 ora di Tokyo)."""
    return in_sessione(df, "TOKYO", quarantena=_quarantena(df))


def filter_session_europe(df: pd.DataFrame) -> pd.Series:
    """Dentro la sessione di Londra (08:00-17:00 ora di Londra)."""
    return in_sessione(df, "LONDRA", quarantena=_quarantena(df))


def filter_session_us(df: pd.DataFrame) -> pd.Series:
    """Dentro la sessione di New York (08:00-17:00 ora di New York)."""
    return in_sessione(df, "NEW_YORK", quarantena=_quarantena(df))


def filter_session_overlap(df: pd.DataFrame) -> pd.Series:
    """
    Londra e New York aperte insieme: le ore di massima liquidita'.

    E' un AND fra due stati, non un OR fra rami opposti: la regola 3 dei
    filtri e' rispettata.
    """
    q = _quarantena(df)
    return in_sessione(df, "LONDRA", quarantena=q) & in_sessione(df, "NEW_YORK", quarantena=q)


# --- F21: la variazione notturna -----------------------------------------
# Coppia direzionale: la notte in salita e' contesto rialzista.

def _variazione_notturna(df: pd.DataFrame) -> pd.Series:
    """
    Quanto si e' mosso il prezzo mentre gli americani non c'erano: dalla
    chiusura PULITA della sessione americana precedente all'apertura di
    quella corrente.

    Sul forex non e' un "gap": il mercato ha trattato, c'erano Londra e
    l'Asia. E' il rendimento overnight, e misura cosa e' successo fuori
    dall'orario americano.

    La chiusura e' quella dell'ultima barra non in quarantena, cioe' le
    16:30 di New York e non le 16:45.

    Il valore viene fotografato all'apertura americana e resta fermo fino
    all'apertura successiva (24 ore). Cosi' vale anche durante l'Asia e
    l'Europa del giorno dopo, e il filtro non finisce per fare anche da
    filtro di sessione — che renderebbe il risultato non interpretabile,
    perche' mescolerebbe due effetti senza poterli separare.
    """
    sessione_usa = range_finestra(df, "NEW_YORK", "ROLLOVER")
    chiusura = al_ultima_apertura(df, "NEW_YORK", sessione_usa["ultimo_close"])
    apertura = al_ultima_apertura(df, "NEW_YORK", df["Open"])
    return apertura / chiusura - 1.0


def filter_overnight_up(df: pd.DataFrame) -> pd.Series:
    """La notte ha portato il prezzo in su -> contesto rialzista."""
    return (_variazione_notturna(df) > 0) & ~_quarantena(df)["totale"]


def filter_overnight_down(df: pd.DataFrame) -> pd.Series:
    """La notte ha portato il prezzo in giu' -> contesto ribassista."""
    return (_variazione_notturna(df) < 0) & ~_quarantena(df)["totale"]


# --- F22: distanza dal rollover ------------------------------------------

ORE_DAL_ROLLOVER = 4.0


def filter_far_from_rollover(df: pd.DataFrame) -> pd.Series:
    """
    Mancano almeno 4 ore al rollover delle 17:00 di New York.

    Serve a non aprire posizioni destinate a morire dentro la finestra
    dello spread largo, dove si paga anche lo swap.

    Le 4 ore sono un PARAMETRO, e va dichiarato. Non e' stato ottimizzato:
    viene dai picchi osservati nell'event study, fra la barra 15 e la 30,
    cioe' fra 4 e 8 ore. Scelta fatta a priori una volta sola, mai provata
    in varianti.
    """
    locale = df.index.tz_convert("America/New_York")
    minuti = locale.hour * 60 + locale.minute
    mancanti = (17 * 60 - minuti) % 1440
    vicino = pd.Series(mancanti >= ORE_DAL_ROLLOVER * 60, index=df.index)
    return vicino & ~_quarantena(df)["totale"]


# =========================================================================
# Filtri entrati da articoli il 7/10/2026 (metodo: 50_IDEE_DA_ARTICOLI.md)
# =========================================================================

# --- F23: il mercato sta oscillando in modo regolare ---------------------

def filter_cycle_strength(df: pd.DataFrame, rank_window: int = 2000,
                          percentile: float = 0.70) -> pd.Series:
    """
    Ciclo forte: la quota di energia nel ciclo dominante (`ciclo_quota`,
    calcolata su 300 barre) e' sopra il 70° percentile delle proprie ultime
    2000 barre.

    Neutro: misura quanto il movimento e' ciclico, non il suo verso. La
    finestra del percentile (2000) e' molto piu' larga di quella del valore
    che classifica (300), come vuole la regola 2 dei filtri. Vera circa il
    30% delle barre, per costruzione. Parametri fissati a priori, mai
    provati in varianti. Finestra massima: 2300 barre.

    Fonte dell'idea: Sofien Kaabar, "Forecasting Market Cycles with Fourier
    Transform in Python", 29/9/2026, https://medium.com/@kaabar-sofien/forecasting-market-cycles-with-fourier-transform-in-python-9b29c110cd3c
    """
    return ts_rank(df["ciclo_quota"], rank_window) > percentile


# --- F24: due candele di fila nello stesso verso -------------------------
# (era F26 fino all'8/10/2026: rinumerato il 9/10, quando i filtri PVO,
# F24/F25, e IIX, F27, sono stati tolti ed entrati nei setup completi E25/E26.)
# Coppia direzionale: due chiusure sopra l'apertura sono contesto rialzista.

def filter_two_bars_up(df: pd.DataFrame) -> pd.Series:
    """
    La barra corrente e la precedente chiudono entrambe sopra l'apertura.

    Fonte: Sayedali Richu, "Want to Find Better Trading Opportunities? Start
    With These 2 Indicators", 24/9/2026, https://medium.com/@sayedali_3166/want-to-find-better-trading-opportunities-start-with-these-2-indicators-ea37c3ee6f55
    """
    su = df["Close"] > df["Open"]
    return su & su.shift(1, fill_value=False)


def filter_two_bars_down(df: pd.DataFrame) -> pd.Series:
    """La barra corrente e la precedente chiudono entrambe sotto l'apertura. Vedi F24_TWO_BARS_UP."""
    giu = df["Close"] < df["Open"]
    return giu & giu.shift(1, fill_value=False)


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


# --- F28: segno del Volume Flow Indicator (docs/51, V1) -------------------
# Coppia direzionale: il volume dei rialzi prevale (sopra zero) o no.

def filter_vfi_positive(df: pd.DataFrame) -> pd.Series:
    """
    Volume Flow Indicator (colonna `vfi`, 130 barre) sopra lo zero: nelle
    ultime 130 barre il volume dei rialzi supera quello dei ribassi.
    Dipende dalla qualita' del volume (tick volume su MT5). Riscaldamento:
    261 barre.

    Fonte dell'indicatore: LazyBear, "Volume Flow Indicator [LazyBear]",
    TradingView, https://www.tradingview.com/script/MhlDpfdS-Volume-Flow-Indicator-LazyBear/
    (nessuna licenza dichiarata). Regola del filtro: docs/51 §3, V1.
    """
    return df["vfi"] > 0


def filter_vfi_negative(df: pd.DataFrame) -> pd.Series:
    """Volume Flow Indicator sotto lo zero. Speculare di F28_VFI_POSITIVE."""
    return df["vfi"] < 0


# --- F29: volume relativo alto / basso (docs/51, V2) ---------------------
# Due filtri neutri a se', non una coppia: misurano l'intensita' del volume,
# non un verso. Mai veri insieme; nella zona di mezzo entrambi falsi.

def filter_rvol_high(df: pd.DataFrame, rank_window: int = 500,
                     percentile: float = 0.75) -> pd.Series:
    """
    Volume relativo ALTO: RVOL (colonna `rvol`, volume / media delle 30 barre
    precedenti) nel 25% piu' alto delle proprie ultime 500 barre.

    SPENTO nel dizionario FILTRI: e' un doppione di F3_VOLUME_ABOVE_AVG
    (contenuto al 100% su EURUSD in-sample, controllo del 15/10/2026).

    Neutro. La finestra del percentile (500, scelta di Mattia del 15/10/2026
    perche' resti usabile su H4 e D1) e' molto piu' larga di quella
    dell'indicatore (30). Parametri fissati a priori, mai provati in
    varianti. Riscaldamento: 530 barre.
    Dipende dalla qualita' del volume (tick volume su MT5).

    Fonte dell'indicatore: veryfid, "Relative Volume" (RVOL), TradingView,
    licenza MPL 2.0 (vedi engine.indicatori.volume_relativo). Regola: docs/51
    §3, V2 (solo filtri, neutri); soglie a percentile rolling: traduzione
    nostra (lo script non ne ha).
    """
    return ts_rank(df["rvol"], rank_window) >= percentile


def filter_rvol_low(df: pd.DataFrame, rank_window: int = 500,
                    percentile: float = 0.25) -> pd.Series:
    """Volume relativo BASSO: RVOL nel 25% piu' basso delle ultime 500 barre. Vedi F29_RVOL_HIGH."""
    return ts_rank(df["rvol"], rank_window) <= percentile


# --- F32: efficienza del movimento, Kaufman (docs/51, R1) ----------------
# Coppia direzionale TREND_UP/TREND_DOWN (soglia +-0,5, la linea "Efficient"
# dello script: il KER ha una scala teorica) e un filtro neutro a se', il
# laterale, con percentile e isteresi come F25.

def filter_ker_trend_up(df: pd.DataFrame, soglia: float = 0.5) -> pd.Series:
    """
    SPENTO nel dizionario FILTRI: doppione di F4 MACD, F8 contesto, F16 VWAP (docs/50 §7.5,
    controllo del 15/10/2026).

    Tendenza rialzista efficiente: KER con segno (colonna `ker`, 10 barre)
    sopra +0,5, cioe' piu' di meta' del cammino delle ultime 10 barre e'
    salita netta. Riscaldamento: 10 barre.

    Fonte dell'indicatore: Zorba_the_Buddha, "Kaufman Efficiency Ratio (KER)",
    TradingView, https://www.tradingview.com/script/7imltc5K-Kaufman-Efficiency-Ratio-KER/
    (open source, nessuna licenza specifica). Regola: docs/51 §3, R1; scelte
    di Mattia del 15/10/2026.
    """
    return df["ker"] > soglia


def filter_ker_trend_down(df: pd.DataFrame, soglia: float = 0.5) -> pd.Series:
    """Tendenza ribassista efficiente: KER sotto -0,5. Speculare di F32_KER_TREND_UP."""
    return df["ker"] < -soglia


def filter_ker_range(df: pd.DataFrame, rank_window: int = 500,
                     entra: float = 0.25, esce: float = 0.50) -> pd.Series:
    """
    Mercato inefficiente / laterale: |KER| (senza segno) entra sotto il 25°
    percentile delle proprie ultime 500 barre e ne esce quando risale sopra
    il 50° (isteresi, vedi `_stato_isteresi`: toglie lo sfarfallio senza
    ritardare l'indicatore). Stessi numeri di F25_CHOP_TREND: nessun
    parametro nuovo.

    Neutro: misura l'efficienza, non il verso. Finestra del percentile (500)
    molto piu' larga di quella dell'indicatore (10). Riscaldamento: 510 barre.

    Fonte dell'indicatore: Zorba_the_Buddha, "Kaufman Efficiency Ratio (KER)",
    TradingView, https://www.tradingview.com/script/7imltc5K-Kaufman-Efficiency-Ratio-KER/
    (open source, nessuna licenza specifica). Regola: docs/51 §3, R1; scelte
    di Mattia del 15/10/2026.
    """
    return _stato_isteresi(ts_rank(df["ker"].abs(), rank_window), entra, esce, basso=True)


# --- F33: esponente di Hurst (docs/51, R2) -------------------------------
# Due filtri neutri a se' (non una coppia): persistenza e ritorno alla media
# non sono due versi dello stesso movimento. Mai veri insieme.

def filter_hurst_persistent(df: pd.DataFrame, soglia: float = 0.6) -> pd.Series:
    """
    Regime PERSISTENTE: esponente di Hurst (colonna `hurst`, R/S su 100
    barre, ema a 5) sopra 0,6, la linea "Strong Trending" dello script.

    Neutro: la persistenza non dice il verso. ATTENZIONE: la stima R/S su
    100 barre e' distorta verso l'alto (su un cammino casuale vale in media
    circa 0,53 e supera 0,6 nel ~6% delle barre): la soglia dello script non
    ne tiene conto. Riscaldamento: 103 barre.

    Fonte dell'indicatore: PhenLabs, "Hurst Exponent Oscillator [PhenLabs]",
    TradingView. LICENZA CC BY-NC-SA 4.0, NON COMMERCIALE: uso personale e di
    ricerca (scelta di Mattia del 13/10/2026), vedi engine.indicatori.hurst_rs.
    Regola: docs/51 §3, R2; soglie 0,6 / 0,4 = le linee dello script.
    """
    return df["hurst"] > soglia


def filter_hurst_mean_reverting(df: pd.DataFrame, soglia: float = 0.4) -> pd.Series:
    """
    Regime di RITORNO ALLA MEDIA: esponente di Hurst sotto 0,4, la linea
    "Strong Mean-Reverting" dello script. Neutro. Per la distorsione verso
    l'alto della stima (vedi F33_HURST_PERSISTENT) e' raro: su un cammino
    casuale meno dell'1% delle barre. Riscaldamento: 103 barre.

    Fonte dell'indicatore: PhenLabs, "Hurst Exponent Oscillator [PhenLabs]",
    TradingView. LICENZA CC BY-NC-SA 4.0, NON COMMERCIALE: uso personale e di
    ricerca (scelta di Mattia del 13/10/2026), vedi engine.indicatori.hurst_rs.
    Regola: docs/51 §3, R2; soglie 0,6 / 0,4 = le linee dello script.
    """
    return df["hurst"] < soglia


# --- F34, F35: i filtri di jdehorty (docs/51, R3) -------------------------
# Neutri, a se'. Il classificatore Lorentzian e filter_adx non sono tradotti.

def filter_jdh_volatility(df: pd.DataFrame) -> pd.Series:
    """
    SPENTO nel dizionario FILTRI: doppione di F3_VOLUME_ABOVE_AVG e F6
    (docs/50 §7.5, controllo del 15/10/2026).

    Volatilita' in espansione (filter_volatility di jdehorty): ATR a 1 barra
    (il true range della barra) sopra l'ATR a 10 barre (colonna
    `jdh_atr_diff` > 0). Neutro. Cambia stato quasi a ogni barra: e' il
    filtro dello script, senza lisciature aggiunte. Riscaldamento: 10 barre.

    Fonte: jdehorty, libreria "MLExtensions" (usata da "Machine Learning:
    Lorentzian Classification"), TradingView, licenza MPL 2.0; vedi
    engine.indicatori.filtri_jdehorty. Regola: docs/51 §3, R3; default dello
    script Lorentzian.
    """
    return df["jdh_atr_diff"] > 0


def filter_jdh_regime_trend(df: pd.DataFrame, soglia: float = -0.1) -> pd.Series:
    """
    Regime di tendenza (regime_filter di jdehorty): la pendenza della curva
    lisciata `klmf` non e' scesa piu' del 10% sotto la sua media a 200 barre
    (colonna `jdh_regime` >= -0,1). Falso quando il movimento si sta
    spegnendo rispetto al recente. Neutro. Riscaldamento: 201 barre; la
    media a 200 rende il valore dipendente dal punto di partenza per qualche
    migliaio di barre (vedi filtri_jdehorty).

    Fonte: jdehorty, libreria "MLExtensions" (usata da "Machine Learning:
    Lorentzian Classification"), TradingView, licenza MPL 2.0; vedi
    engine.indicatori.filtri_jdehorty. Regola: docs/51 §3, R3; default dello
    script Lorentzian.
    """
    return df["jdh_regime"] >= soglia


# --- F30: segno del momentum dello Squeeze (docs/51, M1) -----------------

def filter_sqz_mom_positive(df: pd.DataFrame) -> pd.Series:
    """
    SPENTO nel dizionario FILTRI: doppione di F4 MACD, F8 contesto, F16 VWAP (docs/50 §7.5,
    controllo del 15/10/2026).

    Istogramma dello Squeeze Momentum (colonna `sqz_mom`, regressione su 20
    barre) sopra lo zero: il prezzo sta sopra il centro del suo range
    recente. Riscaldamento: 38 barre.

    Fonte dell'indicatore: LazyBear, "Squeeze Momentum Indicator [LazyBear]",
    TradingView, https://www.tradingview.com/script/nqQ1DT5a-Squeeze-Momentum-Indicator-LazyBear/
    (nessuna licenza dichiarata; moltiplicatore BB corretto, vedi
    engine.indicatori.squeeze_momentum). Regola del filtro: docs/51 §3, M1.
    """
    return df["sqz_mom"] > 0


def filter_sqz_mom_negative(df: pd.DataFrame) -> pd.Series:
    """Istogramma dello Squeeze Momentum sotto lo zero. Speculare di F30_SQZ_MOM_POSITIVE."""
    return df["sqz_mom"] < 0


# --- F31: WaveTrend sopra/sotto la sua media (docs/51, M2) ---------------

def filter_wt_above_signal(df: pd.DataFrame) -> pd.Series:
    """
    SPENTO nel dizionario FILTRI: doppione di F4 MACD (docs/50 §7.5,
    controllo del 15/10/2026).

    WaveTrend: WT1 sopra WT2 (la sua media a 4 barre), cioe' l'oscillatore
    sta salendo. Riscaldamento: 41 barre.

    Fonte dell'indicatore: LazyBear, "WaveTrend Oscillator [WT]", TradingView,
    https://www.tradingview.com/script/2KE8wTuF-Indicator-WaveTrend-Oscillator-WT/
    (nessuna licenza dichiarata). Regola del filtro: docs/51 §3, M2.
    """
    return df["wt1"] > df["wt2"]


def filter_wt_below_signal(df: pd.DataFrame) -> pd.Series:
    """WaveTrend: WT1 sotto WT2. Speculare di F31_WT_ABOVE_SIGNAL."""
    return df["wt1"] < df["wt2"]


# =========================================================================
# Filtro di sentiment entrato il 15/10/2026 (docs/50 §10, riga 11)
# =========================================================================

# --- F36: sentiment paura / avidita', letto in modo CONTRARIAN -----------
# Coppia "SENTIMENT". ATTENZIONE alla direction, eccezione dichiarata alla
# convenzione di questo file (direction = stato di mercato): qui direction e'
# il LATO su cui il filtro si applica. La paura estrema e' uno stato
# ribassista, ma l'ipotesi della fonte e' contrarian ("la paura estrema e'
# un'occasione per comprare"): va sul long (+1) e l'avidita' estrema sullo
# short (-1), cosi' la coppia prova in una riga sola l'ipotesi della fonte.
# Scelta approvata da Mattia il 15/10/2026 (solo la versione contrarian,
# 1 prova; la versione momentum non e' nel catalogo).

def filter_sent_extreme_fear(df: pd.DataFrame) -> pd.Series:
    """
    Paura estrema: il sentiment dell'ultima giornata FX chiusa
    (`sentiment_classe`, vedi engine.indicatori.sentiment_giornaliero) e'
    nel quintile piu' basso delle ultime 365 giornate. Si applica al long
    (contrarian, vedi sopra).

    Il valore cambia solo sulla prima barra della giornata FX: dentro la
    giornata il filtro resta fermo. Falso nel riscaldamento (~760 giornate).
    Parametri fissati a priori, mai provati in varianti.

    Fonte dell'idea: Crypto Fear & Greed Index di alternative.me,
    https://alternative.me/crypto/fear-and-greed-index/ (15/10/2026). Formula
    e codice nostri, nessun dato esterno.
    """
    return df["sentiment_classe"] == 1


def filter_sent_extreme_greed(df: pd.DataFrame) -> pd.Series:
    """Avidita' estrema: `sentiment_classe` nel quintile piu' alto. Si applica allo short. Vedi F36_SENT_EXTREME_FEAR."""
    return df["sentiment_classe"] == 5


# =========================================================================
# Filtri multi timeframe entrati il 15/10/2026 (docs/50 §10, riga 12)
# Le colonne vengono da engine/indicatori.py (colonne_multi_timeframe):
# candele superiori costruite dalle M15, lette solo se gia' chiuse
# (eccezione dichiarata: F37 usa l'apertura del periodo in corso).
# =========================================================================

# --- F37: continuita' dei timeframe (The Strat) -- coppia "FTFC" ---------
def filter_ftfc_up(df: pd.DataFrame) -> pd.Series:
    """
    Continuita' dei timeframe al rialzo: la chiusura della barra e' sopra
    l'apertura dell'ora, della giornata FX, della settimana FX e del mese in
    corso, tutte e quattro (`ftfc` = +1, vedi engine.indicatori.continuita_timeframe).

    Fonte: LuxAlgo, "The Strat" (concetto di Rob Smith),
    https://www.luxalgo.com/library/concept/the-strat/ (15/10/2026).
    """
    return df["ftfc"] == 1


def filter_ftfc_down(df: pd.DataFrame) -> pd.Series:
    """Continuita' dei timeframe al ribasso: chiusura sotto le quattro aperture (`ftfc` = -1). Vedi F37_FTFC_UP."""
    return df["ftfc"] == -1


# --- F38: accordo di tre orizzonti (time-series momentum) -- coppia "TSMOM"
def filter_tsmom_all_up(df: pd.DataFrame) -> pd.Series:
    """
    Rendimento positivo su 1, 5 e 21 giornate FX chiuse, tutti e tre
    (`tsmom` = +1, vedi engine.indicatori.accordo_orizzonti). Il valore cambia
    solo sulla prima barra della giornata.

    Fonte: Hurst, Ooi, Pedersen, "A Century of Evidence on Trend-Following
    Investing", J. of Portfolio Management, 2017; orizzonti in giornate e
    "tutti d'accordo" sono la nostra traduzione (approvata da Mattia il 15/10/2026).
    """
    return df["tsmom"] == 1


def filter_tsmom_all_down(df: pd.DataFrame) -> pd.Series:
    """Rendimento negativo su 1, 5 e 21 giornate FX chiuse, tutti e tre (`tsmom` = -1). Vedi F38_TSMOM_ALL_UP."""
    return df["tsmom"] == -1


# --- F39: giorno inside (barra di "tipo 1" della Strat), neutro ---------
def filter_inside_day(df: pd.DataFrame) -> pd.Series:
    """
    La giornata FX chiusa piu' recente e' rimasta dentro il massimo e il
    minimo di quella prima (`inside_day` = 1): compressione. Vale per tutta la
    giornata dopo. Neutro: non dice in che direzione si uscira'.

    Fonte: LuxAlgo, "The Strat", https://www.luxalgo.com/library/concept/the-strat/
    """
    return df["inside_day"] == 1


def filter_algox_state_long(df: pd.DataFrame) -> pd.Series:
    """
    AlgoXplorer 0.1c (versione con PVSRA): l'ultimo segnale e' un Buy
    (colonna `algox_stato` = +1), cioe' la barra verde dello script. Vero
    dalla barra del Buy fino a quella prima del Sell. Falso prima del primo
    segnale dei dati.

    Fonte: "AlgoXplorer 0.1c" (Mattia e un amico), docs/50 §10, riga 13.
    """
    return df["algox_stato"] == 1


def filter_algox_state_short(df: pd.DataFrame) -> pd.Series:
    """L'ultimo segnale AlgoXplorer e' un Sell (barra rossa). Speculare di F40_ALGOX_STATE_LONG."""
    return df["algox_stato"] == -1


FILTRI = {
    "F1_ADX_ABOVE":              (filter_adx_above, 0, None),
    # "F2_LOW_VOLATILITY":         (filter_low_volatility, 0, None),   # SPENTO 17/10/2026, dentro F2_MID per costruzione (docs/50 §10 septies)
    "F2_MID_VOLATILITY":         (filter_mid_volatility, 0, None),
    "F2_HIGH_VOLATILITY":        (filter_high_volatility, 0, None),
    "F3_VOLUME_ABOVE_AVG":       (filter_volume_above_avg, 0, None),
    # "F5_TALL_CANDLE":            (filter_tall_candle, 0, None),   # SPENTO 17/10/2026, famiglia del volume alto: resta F3 (docs/50 §10 septies)
    # "F6_VOLUME_ABOVE_AVG_50":    (filter_volume_above_avg_50, 0, None),   # SPENTO 17/10/2026, famiglia del volume alto: resta F3 (docs/50 §10 septies)
    # "F7_VOLUME_CLIMAX":          (filter_volume_climax, 0, None),   # SPENTO 17/10/2026, famiglia del volume alto: resta F3 (docs/50 §10 septies)
    "F14_LOW_DRIFT_REGIME":      (filter_low_drift_regime, 0, None),
    "F15_SHORT_TERM_CONSISTENCY": (filter_short_term_consistency, 0, None),
    "F4_MACD_ABOVE_SIGNAL":      (filter_macd_above_signal, 1, "MACD_SIGNAL"),
    "F4_MACD_BELOW_SIGNAL":      (filter_macd_below_signal, -1, "MACD_SIGNAL"),
    "F8_UPTREND_CONTEXT":        (filter_uptrend_context, 1, "TREND_CONTEXT"),
    "F9_DOWNTREND_CONTEXT":      (filter_downtrend_context, -1, "TREND_CONTEXT"),
    "F10_TREND_CONVICTION_UP":   (filter_trend_conviction_up, 1, "TREND_CONVICTION"),
    "F11_TREND_CONVICTION_DOWN": (filter_trend_conviction_down, -1, "TREND_CONVICTION"),
    # "F12_EXTENDED_UP":           (filter_extended_up, 1, "EXTENDED_FROM_MEAN"),   # SPENTO 17/10/2026, famiglia di F4 MACD (docs/50 §10 septies)
    # "F13_EXTENDED_DOWN":         (filter_extended_down, -1, "EXTENDED_FROM_MEAN"),   # SPENTO 17/10/2026, famiglia di F4 MACD (docs/50 §10 septies)
    # "F16_PRICE_ABOVE_VWAP":      (filter_price_above_vwap, 1, "VWAP_POSITION"),   # SPENTO 17/10/2026, famiglia di F8/F9 (docs/50 §10 septies)
    # "F17_PRICE_BELOW_VWAP":      (filter_price_below_vwap, -1, "VWAP_POSITION"),   # SPENTO 17/10/2026, famiglia di F8/F9 (docs/50 §10 septies)
    # "F18_HIGH_NEAR_RANGE_TOP":   (filter_high_near_range_top, 1, "RANGE_POSITION"),   # SPENTO 17/10/2026, famiglia di F4 MACD (docs/50 §10 septies)
    # "F19_LOW_NEAR_RANGE_BOTTOM": (filter_low_near_range_bottom, -1, "RANGE_POSITION"),   # SPENTO 17/10/2026, famiglia di F4 MACD (docs/50 §10 septies)
    "F20_SESSION_ASIA":          (filter_session_asia, 0, None),
    "F20_SESSION_EUROPE":        (filter_session_europe, 0, None),
    "F20_SESSION_US":            (filter_session_us, 0, None),
    "F20_SESSION_OVERLAP":       (filter_session_overlap, 0, None),
    "F22_FAR_FROM_ROLLOVER":     (filter_far_from_rollover, 0, None),
    "F21_OVERNIGHT_UP":          (filter_overnight_up, 1, "OVERNIGHT_RETURN"),
    "F21_OVERNIGHT_DOWN":        (filter_overnight_down, -1, "OVERNIGHT_RETURN"),
    "F23_CYCLE_STRENGTH":        (filter_cycle_strength, 0, None),
    "F24_TWO_BARS_UP":           (filter_two_bars_up, 1, "TWO_BARS"),
    "F24_TWO_BARS_DOWN":         (filter_two_bars_down, -1, "TWO_BARS"),
    "F25_CHOP_TREND":            (filter_chop_trend, 0, None),
    "F25_CHOP_RANGE":            (filter_chop_range, 0, None),
    "F26_VARIANCE_RATIO_TREND":  (filter_variance_ratio_trend, 0, None),
    "F28_VFI_POSITIVE":          (filter_vfi_positive, 1, "VFI_SIGN"),
    "F28_VFI_NEGATIVE":          (filter_vfi_negative, -1, "VFI_SIGN"),
    # F29_RVOL_HIGH: SPENTO, doppione (docs/50 §7.5): su EURUSD in-sample sta
    # al 100% dentro F3_VOLUME_ABOVE_AVG e al 91% dentro F6. Togli il "#" solo
    # se Mattia lo decide (conta 1 prova in piu').
    # "F29_RVOL_HIGH":             (filter_rvol_high, 0, None),
    "F29_RVOL_LOW":              (filter_rvol_low, 0, None),
    # "F33_HURST_PERSISTENT":      (filter_hurst_persistent, 0, None),   # SPENTO 17/10/2026, famiglia di F26 variance ratio (docs/50 §10 septies)
    # "F33_HURST_MEAN_REVERTING":  (filter_hurst_mean_reverting, 0, None),   # SPENTO 17/10/2026, rara: 0,3% delle barre (docs/50 §10 septies)
    #   F34: SPENTO, doppione (75% dentro F3_VOLUME_ABOVE_AVG = 1,64 volte il caso,
    #   72% dentro F6 = 1,53 volte; regola di docs/50 §7.5 del 15/10/2026)
    # "F34_JDH_VOLATILITY":        (filter_jdh_volatility, 0, None),
    "F35_JDH_REGIME_TREND":      (filter_jdh_regime_trend, 0, None),
    # F36: contrarian, direction = lato su cui si applica (vedi la funzione)
    "F36_SENT_EXTREME_FEAR":     (filter_sent_extreme_fear, 1, "SENTIMENT"),
    "F36_SENT_EXTREME_GREED":    (filter_sent_extreme_greed, -1, "SENTIMENT"),
    # multi timeframe (docs/50 §10, riga 12; 15/10/2026). F37 e F38 SPENTI come
    # doppioni (docs/50 §10 quater: F37 dentro F8/F9 e VWAP, F38 dentro VWAP
    # sessione precedente e F28; decisione di Mattia del 15/10/2026): la
    # funzione resta, si riattivano togliendo il #
    # "F37_FTFC_UP":               (filter_ftfc_up, 1, "FTFC"),
    # "F37_FTFC_DOWN":             (filter_ftfc_down, -1, "FTFC"),
    # "F38_TSMOM_ALL_UP":          (filter_tsmom_all_up, 1, "TSMOM"),
    # "F38_TSMOM_ALL_DOWN":        (filter_tsmom_all_down, -1, "TSMOM"),
    "F39_INSIDE_DAY":            (filter_inside_day, 0, None),
    # AlgoXplorer 0.1c (docs/50 §10, riga 13; 17/10/2026)
    "F40_ALGOX_STATE_LONG":      (filter_algox_state_long, 1, "ALGOX_STATE"),
    "F40_ALGOX_STATE_SHORT":     (filter_algox_state_short, -1, "ALGOX_STATE"),
    # Doppioni SPENTI (regola di docs/50 §7.5 alla lettera, decisione di Mattia
    # del 15/10/2026): contenuti al 70% o piu' in filtri gia' presenti, su
    # EURUSD in-sample. Togli il "#" solo se Mattia lo decide (1 prova a coppia).
    #   F30: 72-76% dentro F4 MACD, F8/F9 contesto, F16/F17 VWAP (e viceversa)
    # "F30_SQZ_MOM_POSITIVE":      (filter_sqz_mom_positive, 1, "SQZ_MOM"),
    # "F30_SQZ_MOM_NEGATIVE":      (filter_sqz_mom_negative, -1, "SQZ_MOM"),
    #   F32 trend: 88-96% dentro F4 MACD, F8/F9, F16/F17
    # "F32_KER_TREND_UP":          (filter_ker_trend_up, 1, "KER_TREND"),
    # "F32_KER_TREND_DOWN":        (filter_ker_trend_down, -1, "KER_TREND"),
    "F32_KER_RANGE":             (filter_ker_range, 0, None),
    #   F31: 75% dentro F4 MACD (e viceversa) -- SPENTO, doppione
    # "F31_WT_ABOVE_SIGNAL":       (filter_wt_above_signal, 1, "WAVETREND"),
    # "F31_WT_BELOW_SIGNAL":       (filter_wt_below_signal, -1, "WAVETREND"),
    # F27: OPZIONALE, togli il "#" solo se approvato (conta 1 prova in piu')
    # "F27_REGIME_TREND_COMPOSITE": (filter_regime_trend_composite, 0, None),
}


def registra_filtri():
    """
    Registra tutti i filtri di questo file nel motore (engine.registry),
    cosi' filter_search_bt li trova da sola tramite get_filter(nome), e le
    coppie tramite list_filter_pairs().

    Va chiamata una volta prima di usare i filtri. E' sicura da richiamare
    piu' volte nella stessa sessione: i nomi gia' registrati vengono
    saltati con un avviso, non sollevano errore.
    """
    from engine.registry import register_filter, list_filters

    gia_presenti = set(list_filters())
    nuovi = 0
    for nome, (funzione, direction, pair) in FILTRI.items():
        if nome in gia_presenti:
            print(f"[registra_filtri] '{nome}' gia' registrato, salto.")
            continue
        register_filter(nome, direction=direction, pair=pair)(funzione)
        nuovi += 1
    print(f"[registra_filtri] {nuovi} filtri registrati "
          f"({len(FILTRI) - nuovi} gia' presenti).")
