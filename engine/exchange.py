"""
Exchange — dati e costi dei symbol presi da un exchange crypto (19/10/2026).

PERCHE' ESISTE
--------------
La versione crypto del Lab non usa il broker CFD (MT5) ma i dati degli
exchange, scaricati con la libreria ccxt. Cambiano tre cose rispetto al
broker, e tutte e tre stanno qui:

  1. I DATI. Le candele degli exchange hanno gia' l'ora UTC (niente regola
     del fuso del server, niente controllo su EURUSD) e sono fatte con i
     prezzi degli scambi, non con il BID: il rollover delle 17:00 di New York
     non esiste, la quarantena del rollover si spegne
     (engine.quarantena.imposta_rollover(None)). Resta la quarantena dopo
     un'interruzione (manutenzioni dell'exchange).

  2. I COSTI. Niente spread di listino in pips: l'exchange fa pagare una
     COMMISSIONE in percentuale del controvalore, per lato. Il Lab entra a
     mercato all'apertura della barra dopo il segnale ed esce a mercato (o
     sullo stop), quindi paga la commissione TAKER su tutti e due i lati.
     E' esattamente il parametro `commission` di backtesting.py (frazione
     per lato, vedi engine/costi.parametri_backtest). Lo spread pagato
     entrando a mercato su queste coppie e' di un passo di prezzo
     (SPREAD_PASSI): su BTCUSDT 0,1 $ contro 30 $ di commissione taker.

  3. LO SCARICAMENTO. `scarica_storico` usa SOLO funzioni pubbliche di
     lettura di ccxt (load_markets, fetch_ohlcv), senza chiavi API: senza
     chiavi nessun ordine e' possibile. ccxt si importa dentro le funzioni:
     il resto del modulo gira anche dove ccxt non c'e' (Colab).

I symbol, il pip, i lotti e la leva massima stanno in engine/simboli.py
(SIMBOLI_EXCHANGE, LOTTI_EXCHANGE, LEVA_EXCHANGE). Nome di un symbol:
EXCHANGE_MERCATO_COPPIA, es. BINANCE_PERP_BTCUSDT; il CSV e'
dati/{symbol}_{timeframe}.csv con colonne Date,Open,High,Low,Close,Volume
e Date in UTC.

  4. IL FUNDING DEI PERPETUAL (21/10/2026, docs/63 §5). Ogni poche ore
     (di solito 8, a volte 4, 2 o 1) chi e' long paga a chi e' short il
     tasso del funding (o il contrario, se il tasso e' negativo).
     `scarica_funding` lo scarica con fetch_funding_rate_history (pubblica,
     senza chiavi); `funding_per_trade` lo conta trade per trade nella
     colonna FundingPips (+ = pagato, - = incassato), che
     metriche.pips_per_trade sottrae come CostoExtraPips. Regola: si paga
     ogni liquidazione S con ingresso < S <= uscita, al prezzo Open della
     barra che inizia in S (l'exchange usa il prezzo «mark», che non
     abbiamo: approssimazione dichiarata, di pochi millesimi sul costo).

Modulo ADDITIVO.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from .simboli import SIMBOLI_EXCHANGE, da_exchange, info_symbol, pip_symbol


# ========================================================================
# Commissioni e spread
# ========================================================================

# Commissione per lato, in FRAZIONE del controvalore (0.0005 = 0,05%),
# livello base (VIP 0 / Regular, nessuno sconto in BNB o simili). Verificate
# il 19/10/2026 sulle pagine ufficiali:
#   Binance spot      binance.com/en/fee/schedule (Regular User: 0,100% / 0,100%)
#   Binance perpetual binance.com/en/support/articles/360033544231, agg. 1/5/2026
#                     («Regular User's maker fee is 0.02% ... taker fee is 0.05%»)
#   Bybit             bybit.com/en/help-center/article/Trading-Fee-Structure,
#                     agg. 2/9/2026, riga VIP 0: spot 0,1000% / 0,1000%,
#                     perpetual e futures taker 0,0550%, maker 0,0200%
COMMISSIONI = {
    ("BINANCE", "SPOT"): {"maker": 0.0010, "taker": 0.0010},
    ("BINANCE", "PERP"): {"maker": 0.0002, "taker": 0.0005},
    ("BYBIT",   "SPOT"): {"maker": 0.0010, "taker": 0.0010},
    ("BYBIT",   "PERP"): {"maker": 0.0002, "taker": 0.00055},
}

# Spread pagato entrando a mercato, in passi di prezzo (il «tick»: 10 ** -cifre
# di SIMBOLI_EXCHANGE). Uno: su queste coppie il libro e' quasi sempre largo un
# passo. Da verificare dal vivo con le prime operazioni.
SPREAD_PASSI = 1

# Da come il progetto scrive il timeframe a come lo scrive ccxt.
TIMEFRAME_CCXT = {"M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
                  "H1": "1h", "H4": "4h", "D1": "1d"}

# Da EXCHANGE e MERCATO del nome all'exchange di ccxt.
CCXT_ID = {("BINANCE", "SPOT"): "binance", ("BINANCE", "PERP"): "binanceusdm",
           ("BYBIT", "SPOT"): "bybit", ("BYBIT", "PERP"): "bybit"}


def parti_symbol(symbol: str) -> dict:
    """
    BINANCE_PERP_BTCUSDT -> {"exchange": "BINANCE", "mercato": "PERP",
    "coppia": "BTCUSDT", "base": "BTC", "quotata": "USDT", "ccxt_id":
    "binanceusdm", "ccxt_symbol": "BTC/USDT:USDT"}. Solo symbol di
    SIMBOLI_EXCHANGE: gli altri si fermano con un errore.
    """
    s = (symbol or "").upper()
    if not da_exchange(s):
        raise KeyError(f"'{symbol}' non e' un symbol da exchange: aggiungilo a SIMBOLI_EXCHANGE "
                       "in engine/simboli.py (nome EXCHANGE_MERCATO_COPPIA).")
    exchange, mercato, coppia = s.split("_", 2)
    quotata = info_symbol(s)["valuta"]
    if not coppia.endswith(quotata):
        raise ValueError(f"{s}: la coppia {coppia} non finisce con la valuta {quotata}.")
    base = coppia[: -len(quotata)]
    ccxt_symbol = f"{base}/{quotata}" + (f":{quotata}" if mercato == "PERP" else "")
    return {"exchange": exchange, "mercato": mercato, "coppia": coppia, "base": base,
            "quotata": quotata, "ccxt_id": CCXT_ID[(exchange, mercato)],
            "ccxt_symbol": ccxt_symbol}


def solo_long(symbol: str) -> bool:
    """True sullo spot: si compra la moneta, lo short non esiste."""
    return da_exchange(symbol) and parti_symbol(symbol)["mercato"] == "SPOT"


def commissioni(symbol: str) -> dict:
    """{"maker", "taker"} per lato, in frazione. Errore se l'exchange non e' in tabella."""
    p = parti_symbol(symbol)
    chiave = (p["exchange"], p["mercato"])
    if chiave not in COMMISSIONI:
        raise KeyError(f"Mancano le commissioni di {chiave} in COMMISSIONI (engine/exchange.py): "
                       "aggiungile dal listino ufficiale, livello base.")
    return dict(COMMISSIONI[chiave])


def passo_prezzo(symbol: str) -> float:
    """Il passo di prezzo (tick) del symbol, dalle cifre di SIMBOLI_EXCHANGE."""
    return 10.0 ** -info_symbol(symbol)["cifre"]


def costi_exchange(symbol: str, df: pd.DataFrame) -> dict:
    """
    I costi pronti per i motori (stesso dizionario di costi.parametri_backtest):

        spread      frazione di prezzo pagata una volta (SPREAD_PASSI passi
                    sul prezzo mediano di df, come parametri_backtest)
        commission  commissione TAKER per lato, in frazione
        pip_size    il pip fisso del symbol (engine/simboli.py)

    Piu' due voci per la vetrina: spread_pips (lo spread in pips, serve al
    money management) e taker (la commissione per lato).
    """
    c = commissioni(symbol)
    pip = pip_symbol(symbol)
    prezzo = float(df["Close"].astype(float).median())
    spread_prezzo = SPREAD_PASSI * passo_prezzo(symbol)
    return {"spread": spread_prezzo / prezzo, "commission": float(c["taker"]),
            "pip_size": float(pip), "spread_pips": spread_prezzo / pip,
            "taker": float(c["taker"]), "maker": float(c["maker"])}


# ========================================================================
# Lettura dei CSV
# ========================================================================

def leggi_csv(percorso) -> pd.DataFrame:
    """
    Un CSV di scarica_dati_crypto.py: Date (UTC, senza fuso scritto),
    Open, High, Low, Close, Volume. Ritorna il DataFrame con indice UTC,
    ordinato e senza barre doppie.
    """
    df = pd.read_csv(percorso, index_col="Date")
    idx = pd.DatetimeIndex(pd.to_datetime(df.index))
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    df.index = idx.as_unit("ns")
    df.index.name = "Date"
    df = df[~df.index.duplicated(keep="first")].sort_index()
    return df[["Open", "High", "Low", "Close", "Volume"]].astype(float)


# ========================================================================
# Controlli dei dati (docs/10 e docs/11, adattati a un mercato 24/7)
# ========================================================================

def controlla_storico(df: pd.DataFrame, timeframe: str, n_buchi: int = 5) -> dict:
    """
    I controlli dopo lo scaricamento. Su un mercato 24/7 ogni distacco piu'
    lungo di una barra e' un BUCO (manutenzione dell'exchange, dati mancanti):
    non ci sono weekend ne' rollover.

    Ritorna: barre, prima, ultima, doppie, fuori_griglia (barre che non
    cadono su un multiplo del timeframe), buchi (quanti), barre_mancanti,
    buchi_maggiori (i `n_buchi` piu' lunghi: inizio, durata), volume_zero,
    ohlc_incoerenti (High sotto Open/Close o Low sopra), dopo_interruzione
    (barre in quarantena, rollover spento).
    """
    from .quarantena import quarantena
    passo = pd.Timedelta(TIMEFRAME_CCXT[timeframe].replace("m", "min"))
    idx = pd.DatetimeIndex(df.index)
    doppie = int(idx.duplicated().sum())
    pulito = df[~idx.duplicated()].sort_index()
    idx = pd.DatetimeIndex(pulito.index)
    ns = idx.as_unit("ns").asi8
    fuori = int((ns % passo.value != 0).sum())
    salto = pd.Series(idx).diff()
    buchi = salto[salto > passo]
    mancanti = int(((buchi / passo) - 1).round().sum()) if len(buchi) else 0
    maggiori = buchi.sort_values(ascending=False).head(n_buchi)
    elenco = [(idx[i - 1].strftime("%Y-%m-%d %H:%M"), str(salto.iloc[i])) for i in maggiori.index]
    o, h, l, c = (pulito[k].to_numpy(dtype=float) for k in ("Open", "High", "Low", "Close"))
    incoerenti = int(((h < np.maximum(o, c)) | (l > np.minimum(o, c)) | (h < l)).sum())
    q = quarantena(pulito, rollover=None, verbose=False)
    return {"barre": len(pulito), "prima": idx[0] if len(idx) else None,
            "ultima": idx[-1] if len(idx) else None, "doppie": doppie,
            "fuori_griglia": fuori, "buchi": int(len(buchi)), "barre_mancanti": mancanti,
            "buchi_maggiori": elenco,
            "volume_zero": int((pulito["Volume"].to_numpy(dtype=float) <= 0).sum()),
            "ohlc_incoerenti": incoerenti,
            "dopo_interruzione": int(q["dopo_interruzione"].sum())}


# ========================================================================
# Scaricamento con ccxt (solo lettura, API pubbliche)
# ========================================================================

def apri_exchange(symbol: str):
    """
    L'oggetto ccxt dell'exchange del symbol, SENZA chiavi API (solo dati
    pubblici: nessun ordine possibile), con il limite di frequenza attivo.
    Sul PC di Mattia Python non riconosceva i certificati HTTPS (antivirus):
    se c'e' il pacchetto truststore, si usano i certificati di Windows.
    """
    try:
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        pass
    import ccxt
    p = parti_symbol(symbol)
    return getattr(ccxt, p["ccxt_id"])({"enableRateLimit": True})


def _utc(t) -> pd.Timestamp:
    """Una data (testo o Timestamp, con o senza fuso) in UTC; senza fuso vale come UTC."""
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tz is None else t.tz_convert("UTC")


def _con_tentativi(chiamata, tentativi: int, attesa: float):
    """Esegue `chiamata`; se fallisce riprova, aspettando attesa, 2*attesa, ... secondi."""
    for k in range(int(tentativi)):
        try:
            return chiamata()
        except Exception:
            if k == int(tentativi) - 1:
                raise
            time.sleep(attesa * 2 ** k)


def scarica_storico(symbol: str, timeframe: str = "M15", da="2020-01-02",
                    a=None, ex=None, limite: int = 1000, verbose: bool = True,
                    tentativi: int = 6, attesa: float = 2.0) -> pd.DataFrame:
    """
    Le candele di `symbol` da `da` ad `a` (UTC; None = adesso), a blocchi di
    `limite` con fetch_ohlcv. Solo le barre CHIUSE: quella in corso si scarta.

    ex          l'oggetto ccxt gia' aperto (None = apri_exchange). I test passano
                un exchange finto, senza rete.
    tentativi   un blocco che fallisce si richiede fino a `tentativi` volte, con
    attesa      attesa crescente (2, 4, 8, ... secondi): Bybit risponde a volte
                «internal error» o «Get kline failed» (19/10/2026), errori del
                server che passano riprovando.

    Ritorna il DataFrame Open, High, Low, Close, Volume con indice UTC.
    """
    if timeframe not in TIMEFRAME_CCXT:
        raise ValueError(f"Timeframe {timeframe!r} non previsto: usa uno di {list(TIMEFRAME_CCXT)}.")
    p = parti_symbol(symbol)
    ex = ex if ex is not None else apri_exchange(symbol)
    tf = TIMEFRAME_CCXT[timeframe]
    passo_ms = int(pd.Timedelta(tf.replace("m", "min")).total_seconds() * 1000)
    inizio = int(_utc(da).timestamp() * 1000)
    adesso = int(time.time() * 1000)
    fine = adesso if a is None else min(adesso, int(_utc(a).timestamp() * 1000))
    righe, cursore, blocchi = [], inizio, 0
    while cursore < fine:
        blocco = _con_tentativi(lambda: ex.fetch_ohlcv(p["ccxt_symbol"], tf, since=cursore, limit=limite),
                                tentativi, attesa)
        blocchi += 1
        if not blocco:
            break
        righe.extend(blocco)
        ultimo = int(blocco[-1][0])
        if ultimo < cursore:          # l'exchange non va avanti: stop, niente ciclo infinito
            break
        cursore = ultimo + passo_ms
        if verbose and blocchi % 50 == 0:
            print(f"  {symbol} {timeframe}: {len(righe):,} barre, fino al "
                  f"{pd.Timestamp(ultimo, unit='ms', tz='UTC'):%Y-%m-%d}")
    df = pd.DataFrame(righe, columns=["ms", "Open", "High", "Low", "Close", "Volume"])
    df = df[(df["ms"] >= inizio) & (df["ms"] + passo_ms <= min(fine, adesso))]   # solo barre chiuse
    df = df.drop_duplicates("ms").sort_values("ms")
    df.index = pd.DatetimeIndex(pd.to_datetime(df["ms"], unit="ms", utc=True), name="Date").as_unit("ns")
    return df[["Open", "High", "Low", "Close", "Volume"]].astype(float)


def salva_csv(df: pd.DataFrame, percorso) -> None:
    """Scrive il CSV con Date in UTC senza fuso scritto (es. 2020-01-02 00:15:00)."""
    out = df.copy()
    out.index = pd.DatetimeIndex(out.index).tz_convert("UTC").tz_localize(None)
    out.index.name = "Date"
    out.to_csv(percorso)


def simboli_exchange() -> list[str]:
    """Tutti i symbol da exchange della tabella, in ordine."""
    return list(SIMBOLI_EXCHANGE)


# ========================================================================
# Funding dei perpetual (21/10/2026, docs/63 §5)
# ========================================================================

COLONNA_FUNDING = "FundingPips"     # nei trade: + = pagato, - = incassato

# Tassi al massimo per richiesta. Bybit ne restituisce al massimo 200 e lavora
# ALL'INDIETRO dalla data finale (docs/63 §2.1): con una finestra che contiene
# piu' di 200 liquidazioni perde le piu' vecchie senza dirlo. La finestra si
# dimensiona quindi sull'intervallo piu' corto possibile, 1 ora: 150 ore
# contengono al massimo 151 liquidazioni. Binance va in avanti da `since`.
LIMITE_FUNDING = {"binanceusdm": 1000, "bybit": 200}
FINESTRA_FUNDING_ORE = {"bybit": 150}

# Soglia di SEGNALAZIONE dei tassi anomali, fissata a priori: 0,30% per
# liquidazione, 30 volte il tasso base (0,01%). Non e' il tetto dell'exchange,
# che cambia per coppia e nel tempo. I tassi oltre la soglia si segnalano e
# restano: il -2% di SOL del 9-10/11/2022 (crollo di FTX) e' vero.
SOGLIA_TASSO_ANOMALO = 0.003

ORE_RIFERIMENTO = 8                 # il tasso si riporta a 8 ore per confrontarlo


def file_funding(symbol: str, cartella="dati") -> str:
    """dati/<SYMBOL>_FUNDING.csv"""
    import os
    return os.path.join(str(cartella), f"{symbol.upper()}_FUNDING.csv")


def ha_funding(symbol: str) -> bool:
    """True sui perpetual da exchange: sono gli unici che pagano il funding."""
    return da_exchange(symbol) and parti_symbol(symbol)["mercato"] == "PERP"


def _funding_vuoto() -> pd.DataFrame:
    vuoto = pd.DataFrame({"tasso": pd.Series(dtype=float), "intervallo_ore": pd.Series(dtype=float)})
    vuoto.index = pd.DatetimeIndex([], tz="UTC", name="Date").as_unit("ns")
    return vuoto


def con_intervalli(funding: pd.DataFrame) -> pd.DataFrame:
    """
    Ordina, toglie le liquidazioni doppie e ricalcola `intervallo_ore`, le ore
    dalla liquidazione precedente, riga per riga: l'intervallo e' cambiato nel
    tempo (SOL a 2 ore nel novembre 2022), quindi si legge, non si suppone.
    La prima riga non ha una precedente: NaN.
    """
    f = funding[~funding.index.duplicated(keep="last")].sort_index()
    out = pd.DataFrame({"tasso": f["tasso"].astype(float).to_numpy()}, index=f.index)
    out["intervallo_ore"] = (pd.Series(out.index, index=out.index).diff().dt.total_seconds() / 3600.0).to_numpy()
    return out


def _tabella_funding(righe: list, inizio_ms: int, fine_ms: int) -> pd.DataFrame:
    """Dalle risposte di ccxt alla tabella Date (UTC, al minuto) -> tasso, intervallo_ore."""
    if not righe:
        return _funding_vuoto()
    ms = np.array([int(x["timestamp"]) for x in righe], dtype="int64")
    tasso = np.array([np.nan if x.get("fundingRate") is None else float(x["fundingRate"]) for x in righe])
    tieni = (ms >= inizio_ms) & (ms <= fine_ms)
    # Binance scrive gli orari con qualche millesimo in piu' (08:00:00.005): al minuto
    idx = pd.DatetimeIndex(pd.to_datetime(ms[tieni], unit="ms", utc=True), name="Date").round("min").as_unit("ns")
    return con_intervalli(pd.DataFrame({"tasso": tasso[tieni]}, index=idx))


def scarica_funding(symbol: str, da="2020-01-02", a=None, ex=None, verbose: bool = True,
                    tentativi: int = 6, attesa: float = 2.0, finestra_ore: float | None = None) -> pd.DataFrame:
    """
    Lo storico del funding di un perpetual da `da` ad `a` (UTC; None = adesso),
    con la sola fetch_funding_rate_history di ccxt (pubblica, nessuna chiave).

    ex            l'oggetto ccxt gia' aperto (None = apri_exchange); i test passano
                  un exchange finto, senza rete
    finestra_ore  ampiezza di ogni richiesta, per gli exchange che lavorano
                  all'indietro dalla data finale (Bybit: FINESTRA_FUNDING_ORE).
                  None = quella della tabella; per gli altri si va in avanti
                  da `since`, a blocchi di LIMITE_FUNDING.
    Se una finestra torna piena (tanti tassi quanti il limite), qualche tasso
    potrebbe essere rimasto fuori: si ferma con un errore invece di salvare
    uno storico con dei buchi.

    Ritorna il DataFrame tasso, intervallo_ore con indice Date (UTC, al minuto).
    """
    p = parti_symbol(symbol)
    if p["mercato"] != "PERP":
        raise ValueError(f"{symbol}: il funding esiste solo sui perpetual (PERP).")
    ex = ex if ex is not None else apri_exchange(symbol)
    limite = int(LIMITE_FUNDING.get(ex.id, 200))
    finestra = FINESTRA_FUNDING_ORE.get(ex.id) if finestra_ore is None else finestra_ore
    inizio = int(_utc(da).timestamp() * 1000)
    adesso = int(time.time() * 1000)
    fine = adesso if a is None else min(adesso, int(_utc(a).timestamp() * 1000))
    righe, cursore, richieste = [], inizio, 0
    while cursore < fine:
        if finestra:
            fine_f = min(cursore + int(float(finestra) * 3600 * 1000), fine)
            blocco = _con_tentativi(lambda: ex.fetch_funding_rate_history(
                p["ccxt_symbol"], since=cursore, limit=limite, params={"endTime": fine_f}), tentativi, attesa)
            if len(blocco) >= limite:
                raise RuntimeError(
                    f"{symbol}: la finestra di {finestra} ore dal "
                    f"{pd.Timestamp(cursore, unit='ms', tz='UTC'):%Y-%m-%d %H:%M} UTC ha restituito {len(blocco)} "
                    f"tassi, il massimo per richiesta: qualche tasso potrebbe mancare. Riduci FINESTRA_FUNDING_ORE "
                    "in engine/exchange.py.")
            righe.extend(blocco)
            cursore = fine_f + 1
        else:
            blocco = _con_tentativi(lambda: ex.fetch_funding_rate_history(
                p["ccxt_symbol"], since=cursore, limit=limite), tentativi, attesa)
            if not blocco:
                break
            righe.extend(blocco)
            ultimo = max(int(x["timestamp"]) for x in blocco)
            if ultimo < cursore:          # l'exchange non va avanti: stop, niente ciclo infinito
                break
            cursore = ultimo + 1
        richieste += 1
        if verbose and richieste % 100 == 0:
            print(f"  {symbol} funding: {len(righe):,} tassi, fino al "
                  f"{pd.Timestamp(min(cursore, fine), unit='ms', tz='UTC'):%Y-%m-%d}")
    return _tabella_funding(righe, inizio, fine)


def salva_funding(funding: pd.DataFrame, percorso) -> None:
    """Scrive dati/<SYMBOL>_FUNDING.csv: Date (UTC senza fuso scritto), tasso, intervallo_ore."""
    out = con_intervalli(funding)
    out.index = pd.DatetimeIndex(out.index).tz_convert("UTC").tz_localize(None)
    out.index.name = "Date"
    out.to_csv(percorso)


def leggi_funding(percorso) -> pd.DataFrame:
    """Un CSV di salva_funding: indice Date in UTC, colonne tasso e intervallo_ore (ricalcolato)."""
    f = pd.read_csv(percorso, index_col="Date")
    idx = pd.DatetimeIndex(pd.to_datetime(f.index))
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    f.index = idx.as_unit("ns")
    f.index.name = "Date"
    return con_intervalli(f[["tasso"]])


def liquidazioni_mancanti(funding: pd.DataFrame) -> pd.Series:
    """
    True dove manca (almeno) una liquidazione prima della riga: l'intervallo e'
    piu' lungo di quelli delle righe vicine (8, 16, 8 ore). Un cambio di regime
    (da 8 a 2 ore e ritorno) non e' una mancanza.
    """
    ore = funding["intervallo_ore"].astype(float)
    vicine = pd.concat([ore.shift(1), ore.shift(-1)], axis=1).max(axis=1)
    return (ore > vicine + 1e-9).fillna(False)


def copertura_funding(funding: pd.DataFrame, df: pd.DataFrame) -> str | None:
    """
    None se il funding copre le barre di `df`, altrimenti il motivo. Coprire
    vuol dire: nessuna liquidazione dentro le barre puo' mancare all'inizio o
    alla fine. Il primo tasso arriva entro 8 ore dalla prima barra (prima di
    quel tasso l'intervallo non e' noto: 8 ore, quello di partenza di tutti gli
    exchange); la liquidazione dopo l'ultima (ultimo tasso + il suo
    intervallo) cade dopo l'inizio dell'ultima barra.
    """
    f = funding.dropna(subset=["tasso"])
    if f.empty:
        return "il file del funding non ha tassi"
    t0, t1 = pd.DatetimeIndex(df.index)[[0, -1]]
    primo, ultimo = f.index[0], f.index[-1]
    if primo > t0 + pd.Timedelta(hours=ORE_RIFERIMENTO):
        return (f"il primo tasso e' del {primo:%d/%m/%Y %H:%M} UTC, la prima barra del {t0:%d/%m/%Y %H:%M}: "
                "mancano le liquidazioni dell'inizio")
    passo = f["intervallo_ore"].dropna()
    ultimo_passo = pd.Timedelta(hours=float(passo.iloc[-1]) if len(passo) else ORE_RIFERIMENTO)
    if ultimo + ultimo_passo <= t1:
        return (f"l'ultimo tasso e' del {ultimo:%d/%m/%Y %H:%M} UTC, l'ultima barra del {t1:%d/%m/%Y %H:%M}: "
                "il funding e' meno aggiornato delle barre")
    return None


def controlla_funding(funding: pd.DataFrame, df: pd.DataFrame | None = None, n: int = 5) -> dict:
    """
    I controlli a fine scaricamento (docs/63 §5.1). Ritorna:
      tassi, primo, ultimo        quante liquidazioni, la prima e l'ultima
      senza_tasso                 righe con il tasso vuoto
      intervalli_per_anno         tabella anno x intervallo (ore): quante volte
      mancanti, elenco_mancanti   liquidazioni mancanti (liquidazioni_mancanti)
      fuori_orario                liquidazioni non all'ora esatta
      anomali, elenco_anomali     |tasso| > SOGLIA_TASSO_ANOMALO, i `n` piu' estremi:
                                  si segnalano, non si tolgono
      tasso_medio_8h              tasso medio riportato a 8 ore
    Con `df` (le barre): prima_barra, ore_primo_tasso (ore dalla prima barra
    al primo tasso: negativo = il funding parte prima) e copertura (None = ok,
    altrimenti il motivo, come copertura_funding).
    """
    f = funding
    ore = f["intervallo_ore"].astype(float)
    anni = pd.DatetimeIndex(f.index).year
    tab = pd.crosstab(anni[1:], ore.iloc[1:].round(2).to_numpy()) if len(f) > 1 else pd.DataFrame()
    if len(tab):
        tab.index.name, tab.columns.name = "anno", "ore"
    manc = liquidazioni_mancanti(f)
    tasso = f["tasso"].astype(float)
    oltre = tasso[tasso.abs() > SOGLIA_TASSO_ANOMALO]
    estremi = oltre.reindex(oltre.abs().sort_values(ascending=False).index).head(n)
    idx = pd.DatetimeIndex(f.index)
    a8 = tasso * ORE_RIFERIMENTO / ore
    out = {"tassi": int(len(f)), "primo": idx[0] if len(f) else None, "ultimo": idx[-1] if len(f) else None,
           "senza_tasso": int(tasso.isna().sum()), "intervalli_per_anno": tab,
           "mancanti": int(manc.sum()),
           "elenco_mancanti": [(t.strftime("%Y-%m-%d %H:%M"), float(o)) for t, o in ore[manc].head(n).items()],
           "fuori_orario": int(((idx.minute != 0) | (idx.second != 0)).sum()),
           "anomali": int(len(oltre)),
           "elenco_anomali": [(t.strftime("%Y-%m-%d %H:%M"), float(v)) for t, v in estremi.items()],
           "tasso_medio_8h": float(a8[np.isfinite(a8)].mean()) if np.isfinite(a8).any() else np.nan}
    if df is not None:
        t0 = pd.DatetimeIndex(df.index)[0]
        out["prima_barra"] = t0
        out["ore_primo_tasso"] = (float((idx[0] - t0).total_seconds() / 3600.0) if len(f) else np.nan)
        out["copertura"] = copertura_funding(f, df)
    return out


def _istanti(valori, riferimento: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Gli istanti `valori` nello stesso fuso di `riferimento` (UTC o senza fuso)."""
    t = pd.DatetimeIndex(valori)
    if riferimento.tz is None:
        return t.tz_convert("UTC").tz_localize(None) if t.tz is not None else t
    return t.tz_localize("UTC") if t.tz is None else t.tz_convert(riferimento.tz)


def _importi_funding(df: pd.DataFrame, funding: pd.DataFrame, open_col: str = "Open"):
    """
    Le liquidazioni (istanti S) e il loro importo in prezzo per una unita' long:
    tasso x prezzo in S, con il prezzo = Open della prima barra di `df` che
    inizia in S o dopo (di norma quella che inizia in S; dopo una pausa dei
    dati, la prima che riapre). Le liquidazioni dopo l'ultima barra non entrano
    in nessun trade: importo zero. Ritorna (S, cumulata con lo zero in testa).
    """
    idx = pd.DatetimeIndex(df.index)
    f = funding.dropna(subset=["tasso"])
    S = _istanti(f.index, idx)
    ordine = np.argsort(S.asi8, kind="mergesort")
    S = S[ordine]
    tasso = f["tasso"].to_numpy(dtype=float)[ordine]
    pos = idx.searchsorted(S, side="left")
    dentro = pos < len(idx)
    prezzo = np.zeros(len(S))
    prezzo[dentro] = df[open_col].to_numpy(dtype=float)[pos[dentro]]
    importo = np.where(dentro, tasso * prezzo, 0.0)
    return S, np.r_[0.0, np.cumsum(importo)]


def funding_per_trade(trades: pd.DataFrame, df: pd.DataFrame, funding: pd.DataFrame,
                      pip_size: float) -> pd.Series:
    """
    Il funding di ogni trade, in pips: + = pagato, - = incassato.

    Si contano le liquidazioni S con EntryTime < S <= ExitTime: il motore entra
    all'apertura di una barra, un istante DOPO il suo inizio (una liquidazione
    proprio all'ingresso non si paga), ed esce all'apertura di una barra o
    dentro una barra sullo stop, comunque DOPO il suo inizio (una liquidazione
    proprio all'uscita si paga). Importo: lato x tasso x prezzo in S / pip, con
    lato +1 long (paga se il tasso e' positivo), -1 short.
    """
    if len(trades) == 0:
        return pd.Series(dtype=float)
    idx = pd.DatetimeIndex(df.index)
    S, cumulata = _importi_funding(df, funding)
    ingresso = _istanti(trades["EntryTime"], idx)
    uscita = _istanti(trades["ExitTime"], idx)
    lo = S.searchsorted(ingresso, side="right")
    hi = S.searchsorted(uscita, side="right")
    lato = np.where(trades["Size"].to_numpy(dtype=float) > 0, 1.0, -1.0)
    return pd.Series(lato * (cumulata[hi] - cumulata[lo]) / float(pip_size), index=trades.index)


def aggiungi_funding(trades: pd.DataFrame, df: pd.DataFrame, funding: pd.DataFrame | None,
                     pip_size: float) -> pd.DataFrame:
    """
    Una COPIA dei trade con la colonna FundingPips (funding_per_trade).
    funding=None (CFD, spot, funding spento): i trade tornano come sono,
    senza la colonna, e tutto resta identico a prima.
    """
    if funding is None:
        return trades
    out = trades.copy()
    out[COLONNA_FUNDING] = funding_per_trade(trades, df, funding, pip_size) if len(trades) else pd.Series(dtype=float)
    return out


def funding_avanti(df: pd.DataFrame, H: int, funding: pd.DataFrame, pip: float) -> np.ndarray:
    """
    Il funding dentro il rendimento a H barre di ogni barra (per l'atlante,
    lavoro C), in pips, verso LONG: + = un long paga, uno short ha il segno
    opposto. Stessa convenzione di stagionalita.rendimenti_avanti: segnale
    sulla barra i, ingresso all'Open della i+1 (un istante dopo il suo inizio),
    misura al Close della i+H (un istante prima della sua fine). Contano le
    liquidazioni con inizio della barra i+1 < S < fine della barra i+H.
    NaN dove la misura non esiste (le ultime H barre).
    """
    H = int(H)
    idx = pd.DatetimeIndex(df.index)
    n = len(idx)
    out = np.full(n, np.nan)
    if n <= H:
        return out
    from .quarantena import passo_barre
    S, cumulata = _importi_funding(df, funding)
    apre = idx[1:n - H + 1]                               # inizio della barra i+1
    chiude = idx[H:n] + passo_barre(idx)                  # fine della barra i+H
    lo = S.searchsorted(apre, side="right")
    hi = S.searchsorted(chiude, side="left")
    out[: n - H] = (cumulata[hi] - cumulata[lo]) / float(pip)
    return out


def colonne_perpetual(df: pd.DataFrame, funding: pd.DataFrame | None = None,
                      spot: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Le colonne grezze per gli stati dei perpetual (docs/63 §5.3), da aggiungere
    DOPO indicatori.aggiungi_indicatori (che toglie le righe con un NaN):

      funding_tasso, funding_intervallo_ore   il tasso e l'intervallo della
               liquidazione, sulla prima barra che inizia in S o dopo; NaN
               sulle altre barre (piu' liquidazioni sulla stessa barra, dopo
               una pausa dei dati: vale l'ultima)
      spot_close   il Close dello spot della stessa coppia sulla stessa barra;
               NaN dove lo spot manca (Bybit spot parte nel 2021, Binance spot
               ha dei buchi)

    Le leggono indicatori.funding_liquidato e indicatori.basis_bp. Copia di df.
    """
    out = df.copy()
    idx = pd.DatetimeIndex(df.index)
    if funding is not None:
        f = funding.dropna(subset=["tasso"])
        S = _istanti(f.index, idx)
        pos = idx.searchsorted(S, side="left")
        dentro = pos < len(idx)
        tab = pd.DataFrame({"pos": pos[dentro], "tasso": f["tasso"].to_numpy(dtype=float)[dentro],
                            "ore": f["intervallo_ore"].to_numpy(dtype=float)[dentro]}).groupby("pos").last()
        tasso = np.full(len(idx), np.nan)
        ore = np.full(len(idx), np.nan)
        tasso[tab.index.to_numpy()] = tab["tasso"].to_numpy()
        ore[tab.index.to_numpy()] = tab["ore"].to_numpy()
        out["funding_tasso"], out["funding_intervallo_ore"] = tasso, ore
    if spot is not None:
        sp = spot["Close"].astype(float)
        sp.index = _istanti(sp.index, idx)
        out["spot_close"] = sp[~sp.index.duplicated(keep="first")].reindex(idx).to_numpy()
    return out
