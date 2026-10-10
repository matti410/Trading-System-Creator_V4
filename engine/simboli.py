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

Un symbol nuovo = una riga in SIMBOLI. Modulo ADDITIVO.
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
