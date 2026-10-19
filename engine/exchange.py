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

NON ANCORA CONTATO: il funding dei perpetual (fase 2, ramo a parte).

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
