"""
Adattatore del money management per il V4 (16/10/2026, fase 1 di docs/61).

engine/money_management.py non sa niente di forex: lavora su una tabella di
trade. Questo modulo la costruisce dai trade di backtesting.py, con le regole
del V4. E' l'unico pezzo da riscrivere nel repo crypto.

LE REGOLE (decisioni di Mattia del 16/10/2026, docs/61 §3 e §10)
------------------------------------------------------------------
- Lotti decisi alla CHIUSURA DELLA BARRA DEL SEGNALE (la barra prima
  dell'ingresso, lag barre prima): l'apertura dell'ingresso, al momento
  dell'ordine, non si conosce ancora. Nessun numero viene dal futuro.
- Rischio del trade = distanza dallo stop + costo, in pips:
      stop acceso  frazione dello stop del trade (colonna SL, messa dal motore
                   con soglie_adattive) x prezzo del segnale
      stop spento  "stop di calcolo" (strada A): la stessa soglia adattiva al
                   90° percentile, calcolata come fa il motore ma non usata per
                   uscire. Va letto come rischio TIPICO, non massimo
      costo        spread di listino normale + commissione ed extra del
                   rollover del trade (pips lordi meno netti)
- Valore del pip per lotto nella valuta del conto (USD): contratto x pip x
  cambio della valuta di quotazione. USD -> 1; symbol che inizia per USD
  (USDJPY) -> 1 / prezzo; altre valute (DE40 in EUR) -> {valuta}USD dal CSV
  della cartella dei dati. Al segnale per i lotti, all'uscita per il guadagno.
- Limiti: lotto minimo, passo e massimo da simboli.LOTTI, leva da simboli.LEVA.
- 16/10/2026, fase 3 (docs/61 §14): misura="volatilita'" = modello a
  volatilita' del libro (cap. 4.5): il "rischio" e' l'ATR giornaliero a 5
  giornate FX chiuse (indicatori.atr_giornaliero_chiuso; sui symbol da
  exchange giornate da 00:00 UTC, dal 20/10/2026) alla barra del
  segnale, in pips, senza costi. Il modulo puro non cambia.

Modulo ADDITIVO: legge simboli, metriche, exit_search_bt (soglie_per_lato) e il
fuso del broker, senza modificarli.
"""
from __future__ import annotations

import contextlib
import io
import os

import numpy as np
import pandas as pd

from .broker_tz_diagnostic import to_utc_index
from .exit_search_bt import soglie_per_lato
from .metriche import pips_per_trade
from .simboli import VALUTE_IN_DOLLARI, info_symbol, leva_scelta, leva_symbol, lotti_symbol

MISURE = ("stop", "volatilita")

PERC_STOP_CALCOLO = 90.0            # strada A: stesso percentile dello stop di default
REGOLA_FUSO = "A_US_DST (NY+7h)"


def limiti_symbol(symbol: str, leva: bool = True, valore_leva: float | None = None) -> dict:
    """
    I limiti dei lotti per money_management: minimo, passo, massimo e leva.

    valore_leva (19/10/2026)   None = la leva massima del symbol, come prima;
                               un numero = la leva scelta, fra 1 e la massima
                               concessa in Italia (engine/simboli.leva_scelta).
    """
    lt = lotti_symbol(symbol)
    return {"minimo": lt["minimo"], "passo": lt["passo"], "massimo": lt["massimo"],
            "leva": leva_scelta(symbol, valore_leva) if leva else None}


def _cambi(valuta: str, cartella) -> pd.Series:
    f = os.path.join(str(cartella), f"{valuta}USD_M15.csv")
    if not os.path.exists(f):
        raise FileNotFoundError(f"Per convertire {valuta} in dollari serve {f}.")
    with contextlib.redirect_stdout(io.StringIO()):
        d = to_utc_index(pd.read_csv(f, index_col="Date"), REGOLA_FUSO,
                         on_dst_gap="drop", verbose=False)
    return d["Close"]


def _conversione(symbol: str, prezzi: np.ndarray, tempi: pd.DatetimeIndex,
                 cambi: pd.Series | None) -> np.ndarray:
    """Dollari per 1 unita' della valuta di quotazione, trade per trade."""
    info = info_symbol(symbol)
    if info["valuta"] in VALUTE_IN_DOLLARI:      # 19/10/2026: anche USDT (conto in USDT)
        return np.ones(len(prezzi))
    if symbol.upper().startswith("USD"):
        return 1.0 / np.asarray(prezzi, dtype=float)
    pos = cambi.index.searchsorted(tempi, side="right") - 1      # ultimo cambio <= tempo
    if (pos < 0).any():
        raise ValueError(f"il cambio {info['valuta']}USD non copre i primi trade.")
    return cambi.to_numpy(dtype=float)[pos]


def tabella_trade(trades: pd.DataFrame, df: pd.DataFrame, symbol: str, pip: float,
                  commission: float = 0.0, spread_pips: float = 0.0, perc_sl: float = 90.0,
                  n_barre_long: int = 25, n_barre_short: int = 25, finestra: int = 500,
                  lag: int = 1, cartella="dati", misura: str = "stop",
                  atr: pd.Series | None = None) -> pd.DataFrame:
    """
    La tabella dei trade per engine/money_management.py, in ordine di uscita.

    trades      `.trades(...)` di un backtest del motore, sul DataFrame `df`
    df          lo stesso DataFrame passato al backtest (df_is o df_oos)
    pip, commission, spread_pips
                pip del symbol, commissione del backtest, spread di listino normale
    perc_sl, n_barre_long, n_barre_short, finestra, lag
                gli stessi parametri del backtest: servono allo stop di calcolo
                quando lo stop e' spento (perc_sl = 0)
    cartella    dove sta {valuta}USD_M15.csv per i symbol non quotati in USD
    misura      "stop" (rischio fisso: distanza dallo stop + costi) oppure
                "volatilita" (modello a volatilita': ATR giornaliero in pips)
    atr         facoltativo, per misura="volatilita": l'ATR gia' calcolato su
                uno storico piu' lungo che contiene df (cosi' l'out-of-sample
                non riparte da zero). Senza, si calcola su df.

    Colonne: entrata, uscita, lato, pips_netti, costo_pips, frazione_stop,
    rischio_pips, prezzo_segnale, valore_entrata, valore_uscita, nozionale_lotto,
    atr_pips (NaN con misura="stop").
    """
    misura = "volatilita" if str(misura).lower().startswith("volatilit") else str(misura).lower()
    if misura not in MISURE:
        raise ValueError(f"misura deve essere 'stop' o 'volatilita', non {misura!r}.")
    if len(trades) == 0:
        return pd.DataFrame(columns=["entrata", "uscita", "lato", "pips_netti", "costo_pips",
                                     "frazione_stop", "rischio_pips", "prezzo_segnale",
                                     "valore_entrata", "valore_uscita", "nozionale_lotto",
                                     "atr_pips"])
    t = trades.sort_values("ExitTime", kind="mergesort")
    lordi, netti = pips_per_trade(t, pip, commission)
    entrata = pd.DatetimeIndex(t["EntryTime"])
    pos = df.index.get_indexer(entrata)
    if (pos < 0).any():
        raise ValueError("alcuni trade non entrano su barre di df: passa lo stesso df del backtest.")
    segnale = pos - int(lag)
    if (segnale < 0).any():
        raise ValueError("un trade entra prima che esista la sua barra del segnale.")
    lato = np.where(t["Size"].to_numpy() > 0, 1, -1)
    prezzo_segnale = df["Close"].to_numpy(dtype=float)[segnale]
    tempo_segnale = df.index[segnale]

    if perc_sl and perc_sl > 0:
        frazione = (np.abs(t["EntryPrice"].to_numpy(dtype=float) - t["SL"].to_numpy(dtype=float))
                    / t["EntryPrice"].to_numpy(dtype=float))
    else:
        s = soglie_per_lato(df, int(n_barre_long), int(n_barre_short), int(finestra),
                            PERC_STOP_CALCOLO, 0.0, lag=int(lag))
        frazione = np.where(lato > 0, s["sl_long"].to_numpy()[pos], s["sl_short"].to_numpy()[pos])

    costo = float(spread_pips) + (lordi - netti).to_numpy(dtype=float)
    # 21/10/2026 (docs/63 §5): il funding resta nel risultato (pips_netti) ma NON
    # nel rischio: si conosce solo a trade chiuso (sarebbe lookahead) e un incasso
    # abbasserebbe il rischio. lordi - netti lo contiene: si toglie
    if "FundingPips" in t.columns:
        costo = costo - t["FundingPips"].fillna(0.0).to_numpy(dtype=float)
    rischio = frazione * prezzo_segnale / float(pip) + costo
    atr_pips = np.full(len(t), np.nan)
    if misura == "volatilita":
        from .indicatori import atr_giornaliero_chiuso
        serie = atr_giornaliero_chiuso(df) if atr is None else atr
        atr_pips = serie.reindex(tempo_segnale).to_numpy(dtype=float) / float(pip)
        rischio = atr_pips

    info = info_symbol(symbol)
    cambi = None
    if info["valuta"] not in VALUTE_IN_DOLLARI and not symbol.upper().startswith("USD"):
        cambi = _cambi(info["valuta"], cartella)
    conv_in = _conversione(symbol, prezzo_segnale, tempo_segnale, cambi)
    conv_out = _conversione(symbol, t["ExitPrice"].to_numpy(dtype=float),
                            pd.DatetimeIndex(t["ExitTime"]), cambi)
    contratto = float(info["contratto"])
    return pd.DataFrame({
        "entrata": entrata,
        "uscita": pd.DatetimeIndex(t["ExitTime"]),
        "lato": lato,
        "pips_netti": netti.to_numpy(dtype=float),
        "costo_pips": costo,
        "frazione_stop": frazione,
        "rischio_pips": rischio,
        "prezzo_segnale": prezzo_segnale,
        "valore_entrata": contratto * float(pip) * conv_in,
        "valore_uscita": contratto * float(pip) * conv_out,
        "nozionale_lotto": contratto * prezzo_segnale * conv_in,
        "atr_pips": atr_pips,
    }).reset_index(drop=True)


def trade_per_anno(trades: pd.DataFrame, df: pd.DataFrame) -> float:
    """Frequenza dei trade: trade diviso gli anni coperti da df."""
    anni = (df.index[-1] - df.index[0]).total_seconds() / (365.25 * 86400)
    return len(trades) / anni if anni > 0 else float("nan")
