"""
Metriche per trade — un posto unico per il calcolo di `avg_trade`.

PERCHE' QUESTO MODULO ESISTE
-----------------------------
Il blocco che calcola `avg_trade` era DUPLICATO, identico, in
`exit_search_bt.py` e in `filter_search_bt.py`. Correggerne uno e
dimenticare l'altro e' un incidente che nel progetto e' gia' capitato piu'
volte. Qui il calcolo sta in un posto solo, e i due motori lo importano.

IL PUNTO CHE QUESTO MODULO CORREGGE — `avg_trade` E' LORDO
-------------------------------------------------------------
Verificato empiricamente su backtesting.py 0.6.6 (non dedotto dal codice):

  - lo SPREAD e' dentro i prezzi di fill. Con spread=0.00014 su prezzo
    1.10000 l'EntryPrice diventa 1.1001540. Quindi
    (ExitPrice - EntryPrice) lo paga GIA'.

  - la COMMISSIONE non e' nei prezzi. Viene addebitata alla cassa: gli
    stessi trade con e senza commissione hanno EntryPrice/ExitPrice
    identici e PnL diverso.

Quindi `avg_trade` calcolato dai soli prezzi e' NETTO di spread ma LORDO di
commissione. La vecchia roadmap affermava il contrario ("con
commission > 0, avg_trade e' gia' al netto dei costi"): era sbagliato, e su
quella frase poggiava il gate economico.

LA FORMULA DELLA COMMISSIONE
-----------------------------
backtesting.py addebita `commission * abs(size) * price` all'ingresso E
all'uscita. Il costo di un trade, in unita' di prezzo, e' quindi

    commission * (EntryPrice + ExitPrice)

Verificato: commission=0.00007, size=9090, prezzi 1.10/1.10 ->
0.00007 * 2.20 * 9090 = 1.39986, contro 1.399860 addebitati dalla libreria.

Nella formula NON c'e' la size: il costo in pips e' quindi
leverage-invariant, esattamente come `avg_trade`. La proprieta' che rende
`avg_trade` la metrica giusta per confrontare trigger fra loro resta
valida anche sul netto.

PERCHE' `avg_trade` RESTA LORDO E IL NETTO E' UNA COLONNA IN PIU'
-------------------------------------------------------------------
Scelta dell'utente (19/9/2026): `avg_trade` non cambia significato, cosi'
le tabelle gia' prodotte restano confrontabili e resta un riferimento
lordo per confronti futuri. Il numero da confrontare con zero e'
`avg_trade_netto`.

Modulo ADDITIVO: non dipende da nessun altro modulo dell'engine.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def costo_pips_per_trade(trades: pd.DataFrame, pip_size: float,
                         commission: float = 0.0) -> pd.Series:
    """
    Costo di commissione di ciascun trade, in pips (round-turn).

        costo = commission * (EntryPrice + ExitPrice) / pip_size

    `commission` deve essere il float passato a Backtest(). backtesting.py
    accetta anche una tupla (fisso, relativo) o una funzione: in quei casi
    questa formula non vale e la funzione solleva TypeError invece di
    restituire un numero sbagliato in silenzio.
    """
    if commission is None:
        commission = 0.0
    if isinstance(commission, bool) or not isinstance(commission, (int, float)):
        raise TypeError(
            "commission deve essere un numero (frazione per lato). Ricevuto "
            f"{type(commission).__name__}: con una tupla (fisso, relativo) o "
            "una funzione la formula commission*(Entry+Exit) non vale piu' e "
            "il costo andrebbe ricavato dal PnL."
        )
    if commission < 0:
        raise ValueError("commission non puo' essere negativa.")

    if len(trades) == 0:
        return pd.Series(dtype=float)
    return float(commission) * (trades["EntryPrice"] + trades["ExitPrice"]) / pip_size


def pips_per_trade(trades: pd.DataFrame, pip_size: float,
                   commission: float = 0.0) -> tuple[pd.Series, pd.Series]:
    """
    Le due serie di pips per trade: (lordi, netti).

    I lordi sono (ExitPrice - EntryPrice)/pip_size con il segno del lato
    (Size > 0 = long). Lo spread, se attivo, e' gia' dentro i prezzi.
    I netti sottraggono la commissione.
    """
    if len(trades) == 0:
        vuota = pd.Series(dtype=float)
        return vuota, vuota
    segno = np.where(trades["Size"] > 0, 1, -1)
    lordi = (trades["ExitPrice"] - trades["EntryPrice"]) / pip_size * segno
    netti = lordi - costo_pips_per_trade(trades, pip_size, commission)
    # 5/10/2026: costo in piu' dei lati che cadono nel rollover, se il motore
    # l'ha calcolato (vedi engine/quarantena_trade.py). Senza la colonna il
    # comportamento e' quello di prima.
    if "CostoExtraPips" in trades.columns:
        netti = netti - trades["CostoExtraPips"].fillna(0.0)
    # 21/10/2026 (docs/63 §5.2): il funding dei perpetual, con il segno (+ = pagato,
    # - = incassato), se il motore l'ha contato (engine/exchange.aggiungi_funding)
    if "FundingPips" in trades.columns:
        netti = netti - trades["FundingPips"].fillna(0.0)
    return lordi, netti


def bp_per_trade(trades: pd.DataFrame, pip_size: float,
                 commission: float = 0.0) -> tuple[pd.Series, pd.Series]:
    """
    I pips per trade (lordi, netti) in PUNTI BASE del prezzo d'ingresso
    (20/10/2026, docs/63 §4, unita' bp): 1 bp = 0,01% del prezzo.

        bp = pips x pip_size / EntryPrice x 10.000

    Un trade dell'1% vale 100 bp a 7.000 $ come a 70.000 $: i bp pesano
    allo stesso modo un trade del 2020 e uno del 2025. I costi sono gli
    stessi di pips_per_trade (commissione, CostoExtraPips), convertiti
    trade per trade con il suo prezzo d'ingresso.
    """
    lordi, netti = pips_per_trade(trades, pip_size, commission)
    if len(trades) == 0:
        return lordi, netti
    fattore = float(pip_size) * 10_000.0 / trades["EntryPrice"].astype(float)
    return lordi * fattore, netti * fattore


def atr_alla_entrata(trades: pd.DataFrame, atr: pd.Series) -> pd.Series:
    """
    L'ATR noto alla barra del SEGNALE di ogni trade: la barra prima di
    EntryTime nell'indice di `atr` (il segnale e' sulla barra i, l'ingresso
    all'Open della i+1). `atr` va calcolata sullo storico intero
    (indicatori.atr_giornaliero_chiuso), cosi' anche i trade out-of-sample
    hanno il valore. NaN se l'ingresso non e' nell'indice o e' la prima barra.
    """
    if len(trades) == 0:
        return pd.Series(dtype=float)
    pos = pd.DatetimeIndex(atr.index).get_indexer(pd.DatetimeIndex(trades["EntryTime"])) - 1
    valori = atr.to_numpy(dtype=float)
    esito = np.where(pos >= 0, valori[np.clip(pos, 0, None)], np.nan)
    return pd.Series(esito, index=trades.index)


def atr_per_trade(trades: pd.DataFrame, atr: pd.Series, pip_size: float,
                  commission: float = 0.0) -> tuple[pd.Series, pd.Series]:
    """
    I pips per trade (lordi, netti) in multipli dell'ATR giornaliero a 5
    giornate chiuse noto al segnale (20/10/2026, docs/63 §4, unita' ATR; lo
    stesso ATR del money management). Non e' la «R» del money management
    (distanza dallo stop): e' il risultato rispetto alla volatilita' del
    momento. NaN dove l'ATR non c'e' ancora (prime giornate dello storico).
    """
    lordi, netti = pips_per_trade(trades, pip_size, commission)
    if len(trades) == 0:
        return lordi, netti
    a = atr_alla_entrata(trades, atr)
    fattore = float(pip_size) / a.where(a > 0)
    return lordi * fattore, netti * fattore


UNITA_CHE_DECIDONO = ("pips", "bp")     # 20/10/2026, docs/63 §4.2 (U2)


def netti_in_unita(trades: pd.DataFrame, pip_size: float, commission: float = 0.0,
                   unita: str = "pips") -> tuple[pd.Series, pd.Series]:
    """
    (lordi, netti) per trade nell'unita' che decide (20/10/2026, U2):
    "pips" = pips_per_trade, "bp" = bp_per_trade. L'ATR resta una colonna
    da leggere (atr_per_trade): ha NaN nelle prime giornate e non decide.
    """
    if unita == "pips":
        return pips_per_trade(trades, pip_size, commission)
    if unita == "bp":
        return bp_per_trade(trades, pip_size, commission)
    raise ValueError(f"unita' che decide {unita!r} non prevista: usa una di {UNITA_CHE_DECIDONO}.")


def metriche_per_trade(trades: pd.DataFrame, pip_size: float,
                       commission: float = 0.0, unita: str = "pips") -> dict:
    """
    Le metriche per-trade di una riga di risultati.

    trades
        DataFrame nativo di backtesting.py (`stats["_trades"]`). Servono le
        colonne Size, EntryPrice, ExitPrice, EntryBar, ExitBar.
    pip_size
        Dimensione di un pip in unita' di prezzo (da event_study.deduci_pip).
    commission
        Lo stesso float passato a Backtest(). E' una frazione PER LATO:
        vedi engine/costi.py, parametri_backtest(), che la calcola.

    Ritorna un dict con:
        n_trades          quanti trade conclusi
        avg_trade         pips medi per trade, LORDI di commissione
        avg_trade_netto   pips medi per trade, al netto — il numero da
                          confrontare con zero
        costo_pips        costo di commissione medio per trade, in pips
        durata_media      barre, media
        durata_max        barre, massimo

    Con zero trade tutti i valori numerici sono NaN (durata_max = 0), come
    nel comportamento precedente dei due motori.

    unita (20/10/2026, U2): con "bp" avg_trade, avg_trade_netto e
    costo_pips sono in punti base (il nome della chiave resta, per
    compatibilita'), e si aggiunge avg_trade_netto_pips, i pips accanto.
    """
    n_t = int(len(trades))
    if n_t == 0:
        vuoto = {"n_trades": 0, "avg_trade": np.nan, "avg_trade_netto": np.nan,
                 "costo_pips": np.nan, "durata_media": np.nan, "durata_max": 0}
        if unita != "pips":
            vuoto["avg_trade_netto_pips"] = np.nan
        return vuoto

    lordi, netti = netti_in_unita(trades, pip_size, commission, unita)
    costo = lordi - netti        # commissione + eventuale costo extra del rollover
    durate = (trades["ExitBar"] - trades["EntryBar"]).to_numpy()

    esito = {
        "n_trades": n_t,
        "avg_trade": float(lordi.mean()),
        "avg_trade_netto": float(netti.mean()),
        "costo_pips": float(costo.mean()) if len(costo) else 0.0,
        "durata_media": float(durate.mean()),
        "durata_max": int(durate.max()),
    }
    if unita != "pips":
        esito["avg_trade_netto_pips"] = float(pips_per_trade(trades, pip_size, commission)[1].mean())
    return esito
