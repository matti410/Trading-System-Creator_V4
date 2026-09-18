"""
engine/equity_plot.py — equity della strategia vs buy & hold (Passo 6, Out-of-Sample).

Modulo ADDITIVO: legge `.trades(...)` gia' calcolato da un FilterSearchBT
(fs, dm.metà1/metà2, oos, ...), non lo modifica e non rilancia nessun
backtest.

RICOSTRUZIONE DELL'EQUITY
--------------------------
Il framework impone trade non sovrapposti (nessuna posizione aperta
mentre un'altra e' in corso — vedi ways-of-working.md), quindi l'equity
al tempo t e' `cash + somma di PnL di tutti i trade gia' chiusi entro t`.
Verificato su un run reale: combacia (a meno di arrotondamento) con il
`Return [%]` che la libreria calcola internamente — non e' una stima,
e' la stessa cifra. La curva resta piatta fra un'uscita e la prossima
entrata (nessuna posizione = nessun cambiamento di equity).

BUY & HOLD (versione PIENA)
-----------------------------
Quanto varrebbe `cash` investito interamente in `close_col` all'inizio
della serie e tenuto fino alla fine, senza mai uscire. E' il benchmark
passivo pieno, non aggiustato per l'esposizione del sistema (che sta a
mercato solo una piccola frazione del tempo) — scelta esplicita per
questo giro di verifica OOS, non un default definitivo del modulo.
"""
from __future__ import annotations

import pandas as pd


def _equity_strategia(trades, df, cash):
    pnl_a_uscita = trades.set_index("ExitTime")["PnL"].sort_index()
    cumulato = cash + pnl_a_uscita.cumsum()
    # punto iniziale a cash0 sul primo istante del df, cosi' la curva
    # parte dall'inizio della serie anche se il primo trade chiude dopo
    inizio = pd.Series([cash], index=[df.index[0]])
    curva = pd.concat([inizio, cumulato])
    return curva.reindex(df.index, method="ffill")


def _buy_hold_pieno(df, cash, close_col):
    prezzo = df[close_col]
    return cash * prezzo / prezzo.iloc[0]


def plot_equity(trades, df, cash=10_000.0, close_col="Close",
                etichetta="strategia", ax=None, figsize=(12, 6)):
    """
    Grafico equity strategia vs buy & hold pieno, sullo stesso df/periodo
    del backtest da cui viene `trades`.

    trades
        Il DataFrame grezzo restituito da `.trades(nome)` di un
        FilterSearchBT (fs, dm.metà1/metà2, oos, ...).
    df
        Lo stesso DataFrame passato a run_filter_search_bt/due_meta per
        quel run (serve `close_col` e il suo indice temporale) — per
        l'Out-of-Sample e' `df_oos`.
    cash
        Stesso capitale iniziale usato nel backtest che ha prodotto `trades`.
    etichetta
        Nome della strategia in legenda (es. "VWAP_SESSION_CLOSE (OOS)").

    Ritorna (ax, curva): `curva` e' un DataFrame con le colonne
    `strategia` e `buy_hold`, sull'indice di `df` — utile per ispezionare
    i numeri, non solo per il disegno.
    """
    import matplotlib.pyplot as plt

    eq_strategia = _equity_strategia(trades, df, cash)
    eq_bh = _buy_hold_pieno(df, cash, close_col)
    curva = pd.DataFrame({"strategia": eq_strategia, "buy_hold": eq_bh})

    if ax is None:
        _, ax = plt.subplots(figsize=figsize)
    ax.plot(curva.index, curva["strategia"], color="tab:blue", lw=1.8, label=etichetta)
    ax.plot(curva.index, curva["buy_hold"], color="black", ls="--", lw=1.2, label="buy & hold pieno")
    ax.axhline(cash, color="grey", lw=0.8, ls=":")
    ax.set_ylabel(f"equity (cash iniziale {cash:,.0f})")
    ax.legend()
    ax.set_title(f"{etichetta} — equity vs buy & hold (Out-of-Sample)")
    return ax, curva
