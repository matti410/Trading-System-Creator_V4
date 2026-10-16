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


def info_symbol(symbol: str) -> dict:
    """
    La riga della tabella come dizionario: classe, pip, contratto, valuta,
    cifre. Symbol assente -> KeyError con l'istruzione per aggiungerlo.
    """
    s = (symbol or "").upper()
    if s not in SIMBOLI:
        raise KeyError(
            f"'{symbol}' non e' nella tabella di engine/simboli.py. Aggiungi una "
            "riga a SIMBOLI con classe, pip, contratto per lotto, valuta di "
            "quotazione e cifre decimali (si leggono in MT5: tasto destro sul "
            "symbol -> Specifiche). Il pip non viene indovinato dal prezzo."
        )
    classe, pip, contratto, valuta, cifre = SIMBOLI[s]
    return {"classe": classe, "pip": pip, "contratto": contratto,
            "valuta": valuta, "cifre": cifre}


def pip_symbol(symbol: str) -> float:
    """Il pip del symbol, in unita' di prezzo. Fisso, dalla tabella."""
    return info_symbol(symbol)["pip"]


def in_tabella(symbol: str) -> bool:
    return (symbol or "").upper() in SIMBOLI


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
    if s not in LOTTI:
        raise KeyError(
            f"'{symbol}' non e' nella tabella LOTTI di engine/simboli.py. Aggiungi "
            "una riga con lotto minimo, passo e lotto massimo (in MT5: tasto destro "
            "sul symbol -> Specifiche -> Volume minimo / Passo volume / Volume massimo)."
        )
    minimo, passo, massimo = LOTTI[s]
    return {"minimo": minimo, "passo": passo, "massimo": massimo}


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


def leva_symbol(symbol: str) -> int:
    """Leva massima retail europea del symbol. Symbol assente -> KeyError."""
    s = (symbol or "").upper()
    if s not in LEVA:
        raise KeyError(
            f"'{symbol}' non e' nella tabella LEVA di engine/simboli.py. Aggiungi una "
            "riga con la leva massima retail europea (30 coppie principali; 20 altre "
            "coppie, oro e indici principali; 10 altre materie prime e indici; 2 crypto)."
        )
    return LEVA[s]
