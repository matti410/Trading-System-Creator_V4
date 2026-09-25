"""
Controlli di portabilita' prima di un backtest.

PERCHE' ESISTE (25/9/2026)
--------------------------
`backtesting.py` non compra frazioni di unita'. Se il prezzo di una barra
supera il capitale disponibile (cash / margin), l'ordine non si puo' eseguire
e viene lasciato cadere SENZA errore: i trade spariscono in silenzio.

Su EURUSD non succede mai (prezzo ~1,1). Su BTCUSD con cash=10.000 si': dal
settembre 2020 bitcoin costa piu' del capitale, e il primo run del notebook su
BTCUSD aveva 120 trade in-sample invece di 814, zero nella seconda meta' e zero
nell'Out-of-Sample.

La libreria stampa un suo avviso («Some prices are larger than initial cash
value»), in inglese e fra altri messaggi: facile non vederlo. Questo lo dice
in chiaro, con i numeri e con la correzione.

I pips per trade non dipendono dal capitale (la formula non contiene la size):
alzare `cash` non cambia `avg_trade_netto`, rende solo i trade possibili.

Modulo ADDITIVO. Lo richiamano exit_search_bt.py e filter_search_bt.py (una
riga ciascuno, modifica dichiarata).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def avviso_capitale(df: pd.DataFrame, cash: float, margin: float = 1.0,
                    close_col: str = "Close", contesto: str = "") -> bool:
    """
    Controlla che il capitale basti a comprare almeno un'unita' su ogni barra.

    Il potere d'acquisto e' cash / margin (margin=1 = niente leva). Se il
    prezzo lo supera anche su una sola barra, stampa un avviso con la quota
    di barre coinvolte e il capitale consigliato (10 volte il prezzo
    massimo, cosi' regge anche un drawdown). Viene stampato sempre, anche
    con verbose=False: e' un problema che cambia i risultati.

    Ritorna True se ha stampato l'avviso, False se il capitale basta.
    """
    potere = float(cash) / float(margin)
    prezzi = df[close_col].astype(float)
    sopra = prezzi > potere
    if not sopra.any():
        return False

    massimo = float(prezzi.max())
    consigliato = 10 ** int(np.ceil(np.log10(massimo * 10)))
    dove = f" ({contesto})" if contesto else ""
    print("!" * 72)
    print(f"!!! ATTENZIONE{dove}: IL CAPITALE E' PIU' PICCOLO DEL PREZZO")
    print(f"!!! cash {cash:,.0f} (margin {margin:g}) · prezzo massimo {massimo:,.2f} · "
          f"{sopra.mean():.0%} delle barre sopra il capitale")
    print("!!! backtesting.py non compra frazioni: su quelle barre gli ordini")
    print("!!! vengono ignorati e i trade SPARISCONO senza errore.")
    print(f"!!! Rilancia con cash={consigliato:,.0f} (i pips per trade non cambiano).")
    print("!" * 72)
    return True
