"""
Simboli — la tabella fissa dei symbol: classe, pip, contratto, valuta.

PERCHE' ESISTE (10/10/2026)
---------------------------
Il pip era dedotto dal prezzo medio (`event_study.deduci_pip`, soglie a 20
e 5.000). Su un symbol che attraversa una soglia il pip cambia con la
finestra di dati: su US500 era 0,01 nella parte in-sample (prezzo medio
sotto 5.000) e 1,0 in quella out-of-sample, cioe' gli stessi movimenti
contati in pips 100 volte diversi. E il pip entra nei calcoli: converte lo
spread di listino in prezzo (`costi.parametri_backtest`), il costo del
rollover (`quarantena_trade.costo_extra_pips`), i pips per trade e il
sizing (`montecarlo.valore_pip_lotto`).

Il pip e' un'unita' di misura: qui e' FISSO per symbol, scritto a mano,
senza guardare il prezzo e senza MT5 (il notebook gira anche su Colab).
Un symbol che non c'e' ferma tutto con un messaggio: niente pip indovinato.

CONVENZIONE
-----------
    forex          0,0001 (0,01 se la valuta quotata e' JPY)  = 10 punti MT5
    oro (XAUUSD)   0,10 $                                     = 10 punti MT5
    indici         1 punto di indice                          = 100 punti MT5
    crypto         1 $ (BTCUSD, come prima)                   = 100 punti MT5

Forex e oro: "pip = 10 punti" sulle quotazioni a una cifra in piu' del
vecchio pip (convenzione di mercato). Indici: l'unita' in cui si parla di
spread e stop. BTCUSD: tenuto a 1 $ per non cambiare nessun numero.

FONTE DEI VALORI
----------------
Contratto, cifre decimali, passo di prezzo e valuta di quotazione letti con
MetaTrader5.symbol_info() in sola lettura il 10/10/2026, server
ICMarketsEU-Demo, conto in USD. Il collaudo `test_simboli.py` li ricontrolla
contro MT5 quando MT5 c'e' (e salta quel controllo quando non c'e').

Un symbol nuovo = una riga in SIMBOLI (e una in LOTTI, dal 16/10/2026:
lotto minimo, passo, lotto massimo). Modulo ADDITIVO.

EXCHANGE CRYPTO (19/10/2026)
----------------------------
I symbol presi da un exchange (Binance, Bybit: dati con ccxt, non da MT5)
stanno in tabelle separate, SIMBOLI_EXCHANGE, LOTTI_EXCHANGE e
LEVA_EXCHANGE, con i valori letti dall'exchange. Le funzioni di lettura
guardano tutte e due le tabelle; `da_exchange(symbol)` dice da dove viene.
"""
from __future__ import annotations

# nome: (classe, pip, contratto per lotto, valuta di quotazione, cifre MT5)
SIMBOLI = {
    "EURUSD": ("forex",   0.0001, 100_000.0, "USD", 5),
    "GBPUSD": ("forex",   0.0001, 100_000.0, "USD", 5),
    "NZDUSD": ("forex",   0.0001, 100_000.0, "USD", 5),
    "USDJPY": ("forex",   0.01,   100_000.0, "JPY", 3),
    "XAUUSD": ("metalli", 0.10,   100.0,     "USD", 2),
    "US500":  ("indici",  1.0,    1.0,       "USD", 2),
    "USTEC":  ("indici",  1.0,    1.0,       "USD", 2),
    "DE40":   ("indici",  1.0,    1.0,       "EUR", 2),
    "BTCUSD": ("crypto",  1.0,    1.0,       "USD", 2),
}


# ------------------------------------------------------------------------
# Symbol da exchange crypto (19/10/2026, versione crypto del Lab)
# ------------------------------------------------------------------------
# Tabelle SEPARATE da quelle di MT5: i loro valori non vengono da MT5 ma
# dall'exchange (ccxt, load_markets, sola lettura, API pubbliche senza
# chiavi, letti il 19/10/2026). Le funzioni qui sotto (info_symbol,
# pip_symbol, lotti_symbol, leva_symbol, in_tabella) leggono entrambe.
#
# Nome: EXCHANGE_MERCATO_COPPIA, es. BINANCE_PERP_BTCUSDT; il CSV e'
# dati/{nome}_{timeframe}.csv, come per i symbol del broker.
#   SPOT = mercato a pronti (si compra la moneta, niente short)
#   PERP = perpetual lineare in USDT (long e short)
# Contratto 1: 1 «lotto» = 1 moneta (su Binance e Bybit il perpetual lineare
# ha contractSize 1). Valuta USDT: il conto e' in USDT, 1 USDT conta come
# 1 dollaro (VALUTE_IN_DOLLARI). Cifre = decimali del passo di prezzo.
# Pip fisso per moneta, scritto a mano come per i CFD, circa 1/10.000 del
# prezzo tipico: BTC 1 $ (come BTCUSD), ETH 0,1, SOL 0,01, XRP 0,0001.
#
# nome: (classe, pip, contratto per lotto, valuta di quotazione, cifre)
SIMBOLI_EXCHANGE = {
    "BINANCE_SPOT_BTCUSDT": ("crypto", 1.0,    1.0, "USDT", 2),
    "BINANCE_SPOT_ETHUSDT": ("crypto", 0.1,    1.0, "USDT", 2),
    "BINANCE_SPOT_SOLUSDT": ("crypto", 0.01,   1.0, "USDT", 2),
    "BINANCE_SPOT_XRPUSDT": ("crypto", 0.0001, 1.0, "USDT", 4),
    "BINANCE_PERP_BTCUSDT": ("crypto", 1.0,    1.0, "USDT", 1),
    "BINANCE_PERP_ETHUSDT": ("crypto", 0.1,    1.0, "USDT", 2),
    "BINANCE_PERP_SOLUSDT": ("crypto", 0.01,   1.0, "USDT", 2),
    "BINANCE_PERP_XRPUSDT": ("crypto", 0.0001, 1.0, "USDT", 4),
    "BYBIT_SPOT_BTCUSDT":   ("crypto", 1.0,    1.0, "USDT", 1),
    "BYBIT_SPOT_ETHUSDT":   ("crypto", 0.1,    1.0, "USDT", 2),
    "BYBIT_SPOT_SOLUSDT":   ("crypto", 0.01,   1.0, "USDT", 2),
    "BYBIT_SPOT_XRPUSDT":   ("crypto", 0.0001, 1.0, "USDT", 4),
    "BYBIT_PERP_BTCUSDT":   ("crypto", 1.0,    1.0, "USDT", 1),
    "BYBIT_PERP_ETHUSDT":   ("crypto", 0.1,    1.0, "USDT", 2),
    "BYBIT_PERP_SOLUSDT":   ("crypto", 0.01,   1.0, "USDT", 2),
    "BYBIT_PERP_XRPUSDT":   ("crypto", 0.0001, 1.0, "USDT", 4),
}

# Valute di quotazione che il conto conta in dollari senza cambio: USD e,
# per i symbol da exchange, USDT (il conto e' in USDT).
VALUTE_IN_DOLLARI = ("USD", "USDT")


def _riga(symbol: str):
    s = (symbol or "").upper()
    return SIMBOLI.get(s) or SIMBOLI_EXCHANGE.get(s)


def da_exchange(symbol: str) -> bool:
    """True se il symbol e' di un exchange crypto (SIMBOLI_EXCHANGE)."""
    return (symbol or "").upper() in SIMBOLI_EXCHANGE


def info_symbol(symbol: str) -> dict:
    """
    La riga della tabella come dizionario: classe, pip, contratto, valuta,
    cifre. Symbol assente -> KeyError con l'istruzione per aggiungerlo.
    Legge SIMBOLI (broker) e SIMBOLI_EXCHANGE (exchange crypto).
    """
    riga = _riga(symbol)
    if riga is None:
        raise KeyError(
            f"'{symbol}' non e' nella tabella di engine/simboli.py. Aggiungi una "
            "riga a SIMBOLI con classe, pip, contratto per lotto, valuta di "
            "quotazione e cifre decimali (si leggono in MT5: tasto destro sul "
            "symbol -> Specifiche), oppure a SIMBOLI_EXCHANGE per un symbol da "
            "exchange crypto. Il pip non viene indovinato dal prezzo."
        )
    classe, pip, contratto, valuta, cifre = riga
    return {"classe": classe, "pip": pip, "contratto": contratto,
            "valuta": valuta, "cifre": cifre}


def pip_symbol(symbol: str) -> float:
    """Il pip del symbol, in unita' di prezzo. Fisso, dalla tabella."""
    return info_symbol(symbol)["pip"]


def in_tabella(symbol: str) -> bool:
    return _riga(symbol) is not None


# ------------------------------------------------------------------------
# Lotti (16/10/2026, fase 0 del money management, docs/61)
# ------------------------------------------------------------------------
# Lotto minimo, passo e lotto massimo per ordine, letti con
# MetaTrader5.symbol_info() in sola lettura il 16/10/2026 (permesso di
# Mattia), server ICMarketsEU-Demo, conto in USD: campi volume_min,
# volume_step, volume_max. Tabella separata da SIMBOLI per non cambiare la
# sua tupla. test_simboli.py li ricontrolla contro MT5 quando MT5 c'e'.
# Un symbol nuovo = una riga anche qui.
#
# nome: (lotto minimo, passo, lotto massimo)
LOTTI = {
    "EURUSD": (0.01, 0.01, 200.0),
    "GBPUSD": (0.01, 0.01, 200.0),
    "NZDUSD": (0.01, 0.01, 100.0),
    "USDJPY": (0.01, 0.01, 200.0),
    "XAUUSD": (0.01, 0.01, 100.0),
    "US500":  (0.1,  0.1,  250.0),
    "USTEC":  (0.1,  0.1,  250.0),
    "DE40":   (0.1,  0.1,  250.0),
    "BTCUSD": (0.01, 0.01, 10.0),
}


def lotti_symbol(symbol: str) -> dict:
    """
    Lotto minimo, passo e lotto massimo del symbol, come dizionario
    (minimo, passo, massimo). Symbol assente -> KeyError con l'istruzione:
    i limiti dei lotti non vengono indovinati.
    """
    s = (symbol or "").upper()
    riga = LOTTI.get(s) or LOTTI_EXCHANGE.get(s)
    if riga is None:
        raise KeyError(
            f"'{symbol}' non e' nella tabella LOTTI di engine/simboli.py. Aggiungi "
            "una riga con lotto minimo, passo e lotto massimo (in MT5: tasto destro "
            "sul symbol -> Specifiche -> Volume minimo / Passo volume / Volume massimo; "
            "per un symbol da exchange in LOTTI_EXCHANGE, dai limiti del mercato)."
        )
    minimo, passo, massimo = riga
    return {"minimo": minimo, "passo": passo, "massimo": massimo}


# Lotti dei symbol da exchange (19/10/2026): quantita' minima, passo e
# quantita' massima per ORDINE A MERCATO (il Lab entra a mercato), in monete,
# dai limiti di ccxt (load_markets, sola lettura). Binance da' un massimo
# per gli ordini a mercato (limits.market.max, arrotondato per difetto al
# passo); Bybit no, e vale il massimo per ordine (limits.amount.max).
#
# nome: (minimo, passo, massimo)
LOTTI_EXCHANGE = {
    "BINANCE_SPOT_BTCUSDT": (0.00001, 0.00001, 132.0),
    "BINANCE_SPOT_ETHUSDT": (0.0001,  0.0001,  3846.0),
    "BINANCE_SPOT_SOLUSDT": (0.001,   0.001,   81765.0),
    "BINANCE_SPOT_XRPUSDT": (0.1,     0.1,     2581913.0),
    "BINANCE_PERP_BTCUSDT": (0.001,   0.001,   120.0),
    "BINANCE_PERP_ETHUSDT": (0.001,   0.001,   2000.0),
    "BINANCE_PERP_SOLUSDT": (0.01,    0.01,    80000.0),
    "BINANCE_PERP_XRPUSDT": (0.1,     0.1,     2000000.0),
    "BYBIT_SPOT_BTCUSDT":   (0.000001, 0.000001, 230.0),
    "BYBIT_SPOT_ETHUSDT":   (0.00001, 0.00001, 8118.0),
    "BYBIT_SPOT_SOLUSDT":   (0.0001,  0.0001,  26000.0),
    "BYBIT_SPOT_XRPUSDT":   (0.01,    0.01,    1200000.0),
    "BYBIT_PERP_BTCUSDT":   (0.001,   0.001,   1500.0),
    "BYBIT_PERP_ETHUSDT":   (0.01,    0.01,    10000.0),
    "BYBIT_PERP_SOLUSDT":   (0.1,     0.1,     96000.0),
    "BYBIT_PERP_XRPUSDT":   (0.1,     0.1,     7500000.0),
}


# ------------------------------------------------------------------------
# Leva massima (16/10/2026, fase 0 del money management, docs/61)
# ------------------------------------------------------------------------
# Leve massime di un conto RETAIL europeo (limiti ESMA, recepiti da tutti i
# broker UE): 30 sulle coppie principali (solo USD, EUR, JPY, GBP, CAD,
# CHF), 20 sulle altre coppie, sull'oro e sugli indici principali, 2 sul
# crypto. Decisione di Mattia del 16/10/2026: si usa questo schema e non la
# leva del conto demo (1:100), che un conto retail reale non avrebbe. Non si
# leggono da MT5: con symbol_info la leva per symbol dei CFD non c'e'.
# Servono al tetto della leva nel calcolo dei lotti (nozionale <= capitale x leva).
#
# nome: leva massima
LEVA = {
    "EURUSD": 30,
    "GBPUSD": 30,
    "USDJPY": 30,
    "NZDUSD": 20,     # NZD non e' fra le valute principali
    "XAUUSD": 20,
    "US500":  20,
    "USTEC":  20,
    "DE40":   20,
    "BTCUSD": 2,
}


# Leva massima dei symbol da exchange (19/10/2026, decisione di Mattia: la
# leva si sceglie, ma non oltre quella concessa in Italia a un cliente al
# dettaglio). Fonti:
#   - Consob, delibera n. 20976 del 2019 (misura nazionale sui CFD, art. 42
#     MiFIR), allegato I: margine iniziale del 50% del nozionale quando il
#     sottostante e' una criptovaluta, cioe' leva massima 2;
#   - ESMA, dichiarazione del 24/2/2026: i derivati venduti come «perpetual
#     futures» rientrano di regola nelle misure nazionali sui CFD, quindi
#     anche lo stesso tetto di leva.
# PERP = 2. SPOT = 1: si compra con i soldi del conto, il nozionale non
# supera il capitale (il margin trading e' un altro prodotto, non usato qui).
LEVA_EXCHANGE = {nome: (2 if "_PERP_" in nome else 1) for nome in SIMBOLI_EXCHANGE}


def leva_symbol(symbol: str) -> int:
    """Leva massima retail del symbol (in Italia). Symbol assente -> KeyError."""
    s = (symbol or "").upper()
    leva = LEVA.get(s) or LEVA_EXCHANGE.get(s)
    if leva is None:
        raise KeyError(
            f"'{symbol}' non e' nella tabella LEVA di engine/simboli.py. Aggiungi una "
            "riga con la leva massima retail europea (30 coppie principali; 20 altre "
            "coppie, oro e indici principali; 10 altre materie prime e indici; 2 crypto)."
        )
    return leva


def leva_scelta(symbol: str, leva: float | None = None) -> float:
    """
    La leva da usare nel money management (19/10/2026). None = la massima
    del symbol (leva_symbol); altrimenti un numero fra 1 e la massima: oltre
    il tetto concesso in Italia si ferma con un errore.
    """
    massima = leva_symbol(symbol)
    if leva is None:
        return massima
    leva = float(leva)
    if not (1.0 <= leva <= massima):
        raise ValueError(
            f"Leva {leva:g} non ammessa su {symbol.upper()}: deve stare fra 1 e {massima}, "
            "la massima concessa in Italia a un cliente al dettaglio (engine/simboli.py)."
        )
    return leva
