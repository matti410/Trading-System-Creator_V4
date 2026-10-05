"""
Quarantena applicata ai TRADE (5/10/2026).

PERCHE' ESISTE
--------------
La regola di `11_DATI_QUARANTENA.md` — «intorno al rollover i prezzi bid non
sono affidabili: nessun segnale deve nascere o chiudersi li'» — era rispettata
solo dalle condizioni che escludono la quarantena da se' (metro, E22/E23,
filtri di sessione). I motori di backtest non la conoscevano. Misurato
sull'In-Sample EURUSD: 110 ingressi su 2.689 e 151 uscite cadevano su barre
in quarantena, e `E11_INVERTED_HAMMER` scattava li' il 14,5% delle volte
contro il 5,2% atteso.

DUE COSE, SEPARATE
------------------
1. GLI INGRESSI — `maschera_segnali_puliti`. Un segnale si scarta se la sua
   barra, OPPURE la barra d'ingresso (quella dopo), e' in quarantena. Vale
   per ogni condizione, presente e futura.

2. I COSTI — `costo_extra_pips`. Le uscite (a tempo o in stop) possono ancora
   cadere nel rollover: restano dove sono, ma pagano lo spread di quel
   momento. `backtesting.py` ha un solo spread costante, quindi il costo in
   piu' si calcola dopo, trade per trade, e finisce nella colonna
   `CostoExtraPips` dei trade. `engine/metriche.pips_per_trade` la sottrae.

   Lo spread e' un costo del giro completo: meta' si paga entrando, meta'
   uscendo. Il backtest lo addebita gia' tutto, al valore normale. Un lato
   che cade in quarantena paga quindi in piu' META' della differenza:

       extra per lato = (spread_rollover_pips - spread_normale_pips) / 2

   Esempio, conto Standard EURUSD: (1,5 - 0,8) / 2 = 0,35 pips.

Modulo ADDITIVO. Lo richiamano exit_search_bt.py, filter_search_bt.py ed
event_study.py (modifiche dichiarate).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

COLONNA_EXTRA = "CostoExtraPips"


def barre_in_quarantena(df: pd.DataFrame, quarantena=True) -> np.ndarray | None:
    """
    Vettore booleano, una voce per barra di `df`: True = barra in quarantena.

    quarantena
        True       calcolata da `engine.quarantena.quarantena(df)` (con cache)
        False/None nessuna quarantena: ritorna None
        DataFrame  quello restituito da `quarantena()` (si usa `totale`)
        Series     booleana, sullo stesso indice
    """
    if quarantena is None or quarantena is False:
        return None
    if quarantena is True:
        if pd.DatetimeIndex(df.index).tz is None:
            raise ValueError(
                "quarantena=True richiede un indice UTC (vedi to_utc_index). "
                "Su dati senza fuso passa quarantena=False."
            )
        from .livelli import quarantena_cached
        return quarantena_cached(df)["totale"].to_numpy(dtype=bool)
    if isinstance(quarantena, pd.DataFrame):
        if "totale" not in quarantena.columns:
            raise ValueError("Il DataFrame di quarantena non ha la colonna 'totale'.")
        quarantena = quarantena["totale"]
    serie = pd.Series(quarantena)
    if not serie.index.equals(df.index):
        if not df.index.isin(serie.index).all():
            raise ValueError("La quarantena passata non copre tutte le barre di df.")
        serie = serie.reindex(df.index)
    return serie.fillna(False).to_numpy(dtype=bool)


def maschera_segnali_puliti(df: pd.DataFrame, quarantena=True) -> np.ndarray:
    """
    True dove un segnale PUO' essere tradato: ne' la sua barra ne' la barra
    d'ingresso (la successiva) sono in quarantena. Tutto True se la
    quarantena e' spenta.
    """
    q = barre_in_quarantena(df, quarantena)
    if q is None:
        return np.ones(len(df), dtype=bool)
    q_dopo = np.r_[q[1:], False]
    return ~(q | q_dopo)


def costo_extra_pips(trades: pd.DataFrame, df: pd.DataFrame, quarantena,
                     spread: float, spread_rollover_pips: float | None,
                     pip_size: float) -> pd.DataFrame:
    """
    Restituisce una COPIA dei trade con la colonna `CostoExtraPips`.

    spread                 lo stesso float passato a Backtest() (frazione)
    spread_rollover_pips   spread nel rollover, in pips. None = nessun costo
                           in piu' (colonna a zero)

    Per ogni trade: spread normale in pips = spread x EntryPrice / pip_size;
    ogni lato (EntryBar, ExitBar) in quarantena aggiunge meta' della
    differenza col rollover. Mai negativo.
    """
    trades = trades.copy()
    if len(trades) == 0:
        trades[COLONNA_EXTRA] = pd.Series(dtype=float)
        return trades
    q = barre_in_quarantena(df, quarantena) if spread_rollover_pips is not None else None
    if q is None:
        trades[COLONNA_EXTRA] = 0.0
        return trades
    if spread_rollover_pips < 0:
        raise ValueError("spread_rollover_pips non puo' essere negativo.")
    normale = float(spread or 0.0) * trades["EntryPrice"].to_numpy(dtype=float) / pip_size
    per_lato = np.maximum(float(spread_rollover_pips) - normale, 0.0) / 2.0
    lati = (q[trades["EntryBar"].to_numpy(dtype=int)].astype(int)
            + q[trades["ExitBar"].to_numpy(dtype=int)].astype(int))
    trades[COLONNA_EXTRA] = per_lato * lati
    return trades
