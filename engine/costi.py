"""
Costi — il costo round-turn di UNO strumento, ricavato dai dati.

PERCHE' QUESTO MODULO ESISTE
----------------------------
La formula usata su EURUSD era:

    COST = costo_da_dati(df, spread=0.00001, commissione_pct=7.0/108_000)

Non e' portabile su nessun altro strumento, per tre motivi indipendenti:

  1. LA COMMISSIONE NON SI APPLICA OVUNQUE. Il broker la addebita su Forex
     e metalli preziosi. Su indici e crypto no: li' il costo e' tutto
     dentro lo spread. Applicarla lo stesso gonfia il costo e ti fa
     scartare segnali veri.

  2. IL NOZIONALE CAMBIA. La commissione e' in valuta per LOTTO, ma il
     costo che serve alla pipeline e' in PERCENTUALE. Il ponte fra i due
     e' il nozionale = trade_contract_size * prezzo. Per EURUSD e'
     ~108.000 USD, per BTCUSD e' il prezzo del bitcoin, per XAUUSD sono
     100 once. Tre ordini di grandezza diversi.

  3. LO SPREAD IN PERCENTUALE NON E' COSTANTE NEL TEMPO. Questo e' il
     punto piu' insidioso. Lo spread di BTCUSD e' ~6.46 USD. Con bitcoin
     a 100.000 sono 0.65 bp; con bitcoin a 20.000 sono 3.2 bp. Lo stesso
     spread nominale vale CINQUE VOLTE TANTO a seconda dell'anno. Su uno
     strumento che ha fatto 10x nel campione, un costo fisso e'
     matematicamente garantito sbagliato: sottostima i costi nella prima
     meta' del campione e li sovrastima nella seconda.

Qui il costo si ricava dalla colonna `spread` delle barre MT5 e dalle
specifiche del simbolo. Nessun numero scritto a mano.


AVVERTENZA SULLA COLONNA `spread` DI MT5
-----------------------------------------
Verificato su EURUSD: la mediana e' 0.0 per 23 ore su 24, mentre il
valore medio nell'ora di rollover e' ~1.3 bp. MT5 in quel campo registra
il MINIMO della barra, non lo spread medio ne' quello all'esecuzione.
Quindi il costo che esce di qui e' un PAVIMENTO ottimistico. Usare
`percentile=75` per una stima piu' prudente: un backtest che sopravvive
al 75esimo percentile e' molto piu' credibile di uno che sopravvive alla
mediana.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Commissione round-turn in valuta del conto, per 1 lotto standard.
# IC Markets Raw Spread: 7 USD su Forex e metalli preziosi; zero altrove
# (indici e crypto hanno il costo dentro lo spread).
COMMISSIONE_RT = {"forex": 7.0, "metalli": 7.0, "indici": 0.0,
                  "crypto": 0.0, "azioni": 0.0, "altro": 0.0}


def classifica_simbolo(symbol: str, path: str = "") -> str:
    """
    Classe dell'asset, dedotta dal `path` di MT5 (es. 'Forex\\Majors\\EURUSD').
    Il path e' piu' affidabile del nome: 'US500' e 'USDJPY' iniziano uguale.
    """
    p, s = (path or "").lower(), (symbol or "").upper()
    if "crypto" in p:                                   return "crypto"
    if "metal" in p or s.startswith(("XAU", "XAG", "XPT", "XPD")): return "metalli"
    if "ind" in p or "cash" in p:                       return "indici"
    if "share" in p or "stock" in p or "equit" in p:    return "azioni"
    if "forex" in p or "fx" in p:                       return "forex"
    if len(s) == 6 and s.isalpha():                     return "forex"
    return "altro"


def nozionale_valuta_conto(info, prezzo: float) -> float:
    """
    Valore di 1 lotto NELLA VALUTA DEL CONTO.

    ATTENZIONE — questo e' il punto in cui e' facile sbagliare, e in cui
    una prima versione di questo modulo HA sbagliato.

    La strada intuitiva, `trade_contract_size * prezzo`, da' il nozionale
    nella valuta di QUOTAZIONE:

        EURUSD   100.000 EUR x 1.08   = 108.000 USD   <- valuta conto, ok
        USDJPY   100.000 USD x 150    = 15.000.000 JPY <- NON dollari!

    Dividendo una commissione in USD per un nozionale in JPY si ottiene un
    numero privo di senso: sulla nostra tabella la commissione di USDJPY
    risultava 0.005 bp invece di ~0.65 bp, cioe' 130 volte piu' bassa.
    Colpisce tutte le coppie in cui il dollaro non e' la valuta quotata
    (USDJPY, USDCHF, USDCAD) e tutti i cross.

    La via robusta usa `trade_tick_value`, che MT5 fornisce gia' convertito
    nella valuta del conto: quanti tick ci sono in un movimento del 100%,
    moltiplicato per il valore di un tick.

        nozionale = prezzo / tick_size * tick_value

    Funziona senza casi speciali su forex, metalli, indici e crypto.
    """
    ts = getattr(info, "trade_tick_size", 0) or getattr(info, "point", 0)
    tv = getattr(info, "trade_tick_value", 0)
    if ts and tv:
        return prezzo / ts * tv
    return info.trade_contract_size * prezzo   # ripiego, valido se quotato in valuta conto


def costo_simbolo(symbol: str, bars: pd.DataFrame | None = None,
                  percentile: float = 75.0, commissione_rt: float | None = None,
                  verbose: bool = True) -> float:
    """
    Costo round-turn dello strumento, in FRAZIONE di prezzo (non bp),
    pronto da passare come `cost_pct` alla pipeline.

        costo = spread_relativo + commissione / nozionale

    `bars` sono le barre MT5 con la colonna `spread` (quelle scaricate con
    `mt5.copy_rates_range`). Se mancano, si ripiega sullo spread corrente,
    che e' una fotografia di un istante e va bene solo per un ordine di
    grandezza.

    `percentile` e' il percentile dello spread da usare: 50 = mediana,
    75 = prudente (consigliato), 90 = pessimista.
    """
    import MetaTrader5 as mt5

    info = mt5.symbol_info(symbol)
    if info is None:
        raise ValueError(f"simbolo {symbol} non trovato in MT5")

    classe = classifica_simbolo(symbol, getattr(info, "path", ""))
    comm_rt = COMMISSIONE_RT.get(classe, 0.0) if commissione_rt is None else commissione_rt

    # --- spread relativo, dai dati se disponibili ---
    if bars is not None and "spread" in bars.columns:
        sr = bars["spread"] * info.point / bars["close"]
        spread_rel = float(np.percentile(sr.dropna(), percentile))
        fonte = f"dati ({len(sr)} barre, percentile {percentile:.0f})"
    else:
        spread_rel = info.spread * info.point / info.ask if info.ask else np.nan
        fonte = "spread corrente (nessuna barra fornita)"

    # --- commissione relativa al nozionale ---
    prezzo = float(bars["close"].median()) if bars is not None else float(info.ask)
    nozionale = nozionale_valuta_conto(info, prezzo)
    comm_rel = comm_rt / nozionale if nozionale else 0.0

    costo = spread_rel + comm_rel

    if verbose:
        print(f"{symbol}  [{classe}]")
        print(f"   contratto        : {info.trade_contract_size:,.4g}"
              f"   prezzo mediano: {prezzo:,.5g}   nozionale: {nozionale:,.0f}")
        print(f"   spread           : {spread_rel*1e4:6.3f} bp   <- {fonte}")
        print(f"   commissione      : {comm_rel*1e4:6.3f} bp   <- {comm_rt:.2f} per lotto round-turn")
        print(f"   COSTO ROUND-TURN : {costo*1e4:6.3f} bp")
    return costo


def deriva_costo_nel_tempo(symbol: str, bars: pd.DataFrame,
                           commissione_rt: float | None = None) -> pd.DataFrame:
    """
    Il costo anno per anno.

    Serve a rispondere a una domanda che un costo scalare nasconde: il
    costo di questo strumento e' cambiato nel campione? Su BTCUSD la
    risposta e' si', di molto, perche' lo spread e' quasi fisso in dollari
    mentre il prezzo ha fatto piu' volte 10x. Se la colonna `costo_bp`
    varia di un fattore 2 o piu', un backtest a costo costante e'
    inaffidabile e va rifatto a costo variabile.
    """
    import MetaTrader5 as mt5

    info = mt5.symbol_info(symbol)
    classe = classifica_simbolo(symbol, getattr(info, "path", ""))
    comm_rt = COMMISSIONE_RT.get(classe, 0.0) if commissione_rt is None else commissione_rt

    b = bars.copy()
    b["spread_rel"] = b["spread"] * info.point / b["close"]
    b["comm_rel"] = comm_rt / b["close"].map(lambda p: nozionale_valuta_conto(info, p))
    b["costo_bp"] = (b["spread_rel"] + b["comm_rel"]) * 1e4

    out = b.groupby(b.index.year).agg(
        barre=("costo_bp", "size"),
        prezzo_mediano=("close", "median"),
        spread_bp=("spread_rel", lambda s: s.median() * 1e4),
        costo_bp=("costo_bp", "median"),
    ).round(3)
    return out
