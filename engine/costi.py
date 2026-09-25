"""
Costi — il costo round-turn di UNO strumento, ricavato dai dati.

Rifatto (19/9/2026) dal `costi.py` del percorso precedente. Le parti
corrette sono tenute come erano: `classifica_simbolo` e soprattutto
`nozionale_valuta_conto`, che risolve il problema del nozionale in valuta
di quotazione (vedi il suo docstring). Le differenze sono elencate qui
sotto.


PERCHE' QUESTO MODULO ESISTE
----------------------------
La formula scritta a mano `spread=0.00001, commissione_pct=7.0/108_000`
non e' portabile su nessun altro strumento:

  1. LA COMMISSIONE NON SI APPLICA OVUNQUE. IC Markets la addebita solo su
     Forex e metalli. Su indici e crypto il costo e' tutto dentro lo
     spread. Verificato sul sito il 19/9/2026:
     "The commission only applies to Forex and Metals".

  2. IL NOZIONALE CAMBIA. La commissione e' in valuta per LOTTO, il costo
     che serve alla pipeline e' in PERCENTUALE. Il ponte fra i due e' il
     nozionale in valuta del conto: ~110.000 USD per EURUSD, il prezzo del
     bitcoin per BTCUSD, 100 once per XAUUSD.

  3. LO SPREAD IN PERCENTUALE NON E' COSTANTE NEL TEMPO. Lo spread di
     BTCUSD e' ~6.46 USD: con bitcoin a 100.000 sono 0.65 bp, con bitcoin
     a 20.000 sono 3.2 bp. Lo stesso spread nominale vale cinque volte
     tanto a seconda dell'anno. Su uno strumento che ha fatto 10x nel
     campione un costo fisso e' matematicamente garantito sbagliato.
     Vedi `deriva_costo_nel_tempo`.


COSA E' CAMBIATO RISPETTO ALLA VERSIONE PRECEDENTE
---------------------------------------------------
  A. LA COMMISSIONE DIPENDE DALLA VALUTA DEL CONTO. Non e' 7.0 sempre:
     IC Markets addebita 7.00 USD / 6.50 EUR / 5.50 GBP / 9.00 AUD
     round-turn per lotto standard (help centre, 19/9/2026). La tabella e'
     quindi indicizzata su (classe, valuta_conto). Una valuta non in
     tabella su una classe che PAGA commissione solleva un errore invece
     di restituire zero: uno zero silenzioso sottostima i costi, che e'
     il verso sbagliato in cui sbagliare.

  B. SPREAD E COMMISSIONE RESTANO SEPARATI. La versione precedente
     restituiva un costo unico round-turn. backtesting.py vuole due
     parametri e li tratta in modo diverso (vedi `parametri_backtest`):
     sommarli e passarli a uno dei due e' un errore che raddoppia o
     dimezza i costi.

  C. MT5 IMPORTATO DENTRO LE FUNZIONI, non in cima al file. Cosi' il
     modulo si importa anche dove MetaTrader5 non esiste (Colab), e le
     funzioni che non ne hanno bisogno restano usabili.

  D. NOMI DI COLONNA PARAMETRIZZATI. La versione precedente leggeva
     `bars["close"]` minuscolo; i CSV del progetto hanno `Close`. Ora la
     colonna si cerca senza distinzione di maiuscole.

  E. `spread_corrente` — la funzione `retrieve_latest_tick` dell'utente,
     con tre controlli aggiunti: simbolo selezionato, tick non vecchio,
     unita' dichiarate. Serve come CONTROLLO di coerenza, non come fonte
     del costo per un backtest pluriennale (vedi il suo docstring).

  F. `verifica_da_storico_deals` — nuova: legge la commissione REALMENTE
     addebitata dai deal MT5 e la confronta con la tabella.


AVVERTENZA SULLA COLONNA `spread` DELLE BARRE MT5
--------------------------------------------------
E' un INTERO in punti. Su EURUSD un punto e' 0.00001, cioe' 0.1 pip:
qualunque spread piu' piccolo legge 0. Verificato sul percorso precedente:
la mediana e' 0.0 per 23 ore su 24, mentre nell'ora di rollover lo spread
vero e' ~1.3 bp. Quel campo e' quindi un PAVIMENTO ottimistico.

Per questo il default e' `percentile=75` e non la mediana: un backtest che
sopravvive al 75esimo percentile dello spread e' molto piu' credibile di
uno che sopravvive al valore tipico.

Modulo ADDITIVO: nessun file esistente dell'engine viene modificato.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .event_study import deduci_pip


# ========================================================================
# 1 · Le specifiche del broker
# ========================================================================

# Commissione round-turn per 1 lotto standard, nella valuta del conto.
# IC Markets Raw Spread su MetaTrader: 3.50 per lato = 7.00 round-turn in
# USD. Verificato sul sito il 19/9/2026.
COMMISSIONE_RT = {
    "USD": 7.00,
    "EUR": 6.50,
    "GBP": 5.50,
    "AUD": 9.00,
}

# Solo queste classi pagano commissione. Le altre hanno il costo tutto
# dentro lo spread.
CLASSI_CON_COMMISSIONE = {"forex", "metalli"}

# Contratto standard per la strada SENZA MT5 (solo forex a 6 lettere: per
# metalli, indici e crypto il contratto varia troppo per essere indovinato,
# e la funzione lo dice invece di tirare a caso).
CONTRATTO_FOREX = 100_000.0


def _mt5():
    """MetaTrader5, importato alla chiamata. Errore chiaro se manca."""
    try:
        import MetaTrader5 as mt5
    except ImportError as e:
        raise ImportError(
            "MetaTrader5 non e' disponibile in questo ambiente (es. Colab). "
            "Usa parametri_backtest(..., usa_mt5=False, spread_pips=...) "
            "per la strada senza MT5."
        ) from e
    return mt5


def _info(mt5, symbol: str):
    """symbol_info con errore parlante (la causa piu' comune e' initialize())."""
    info = mt5.symbol_info(symbol)
    if info is None:
        raise ValueError(
            f"simbolo '{symbol}' non trovato in MT5. Controlla che "
            "mt5.initialize() sia andato a buon fine e che il simbolo sia "
            "visibile in Market Watch (mt5.symbol_select(symbol, True))."
        )
    return info


def _colonna(df: pd.DataFrame, nome: str) -> str:
    """
    Il nome reale della colonna `nome`, ignorando maiuscole/minuscole.
    Serve perche' i CSV del progetto hanno 'Close' e il codice del
    percorso precedente cercava 'close'.
    """
    if nome in df.columns:
        return nome
    minuscole = {c.lower(): c for c in df.columns}
    if nome.lower() in minuscole:
        return minuscole[nome.lower()]
    raise KeyError(
        f"colonna '{nome}' non trovata. Disponibili: {list(df.columns)}."
    )


# Valute ufficiali (ISO 4217) che compaiono nelle coppie forex dei broker, e
# le sigle crypto piu' comuni. Servono quando manca il path di MT5 (Colab):
# prima del 25/9 bastava avere 6 lettere per essere "forex", e BTCUSD lo era.
VALUTE_FIAT = {
    "USD", "EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD", "SEK", "NOK",
    "DKK", "PLN", "HUF", "CZK", "TRY", "ZAR", "MXN", "SGD", "HKD", "CNH",
    "CNY", "RUB", "ILS", "THB", "INR", "KRW", "BRL", "RON", "ISK",
}
SIGLE_CRYPTO = {
    "BTC", "ETH", "LTC", "XRP", "BCH", "ADA", "DOT", "SOL", "DOG", "DOGE",
    "LNK", "LINK", "XLM", "EOS", "BNB", "UNI", "AVAX", "MATIC", "TRX", "XTZ",
}


def classifica_simbolo(symbol: str, path: str = "") -> str:
    """
    Classe dell'asset, dedotta dal `path` di MT5 (es. 'Forex\\Majors\\EURUSD').
    Il path e' piu' affidabile del nome: 'US500' e 'USDJPY' iniziano uguale.

    Senza path (strada senza MT5) si guarda il nome: e' forex solo se e'
    fatto di DUE valute ufficiali (EURUSD, USDJPY); e' crypto se comincia con
    una sigla crypto nota (BTCUSD, ETHUSD). Corretto il 25/9: prima BTCUSD,
    avendo 6 lettere, risultava forex.
    """
    p, s = (path or "").lower(), (symbol or "").upper()
    if "crypto" in p:                                              return "crypto"
    if "metal" in p or s.startswith(("XAU", "XAG", "XPT", "XPD")): return "metalli"
    if "ind" in p or "cash" in p:                                  return "indici"
    if "share" in p or "stock" in p or "equit" in p:               return "azioni"
    if "forex" in p or "fx" in p:                                  return "forex"
    if any(s.startswith(c) for c in SIGLE_CRYPTO):                 return "crypto"
    if len(s) == 6 and s.isalpha() and s[:3] in VALUTE_FIAT and s[3:] in VALUTE_FIAT:
        return "forex"
    return "altro"


def commissione_round_turn(classe: str, valuta_conto: str = "USD") -> float:
    """
    Commissione round-turn per lotto, nella valuta del conto, per una
    classe di asset. Zero dove il broker non la applica.

    Una valuta sconosciuta su una classe che PAGA commissione e' un errore,
    non uno zero: restituire zero sottostimerebbe i costi in silenzio.
    """
    if classe not in CLASSI_CON_COMMISSIONE:
        return 0.0
    v = (valuta_conto or "").upper()
    if v not in COMMISSIONE_RT:
        raise ValueError(
            f"valuta del conto '{valuta_conto}' non in tabella per la classe "
            f"'{classe}'. Disponibili: {sorted(COMMISSIONE_RT)}. Aggiungila a "
            "COMMISSIONE_RT o passa commissione_rt= a mano."
        )
    return COMMISSIONE_RT[v]


# ========================================================================
# 2 · Il nozionale in valuta del conto
# ========================================================================

def nozionale_valuta_conto(info, prezzo: float) -> float:
    """
    Valore di 1 lotto NELLA VALUTA DEL CONTO.

    ATTENZIONE — questo e' il punto in cui e' facile sbagliare, e in cui
    una prima versione di questo modulo HA sbagliato.

    La strada intuitiva, `trade_contract_size * prezzo`, da' il nozionale
    nella valuta di QUOTAZIONE:

        EURUSD   100.000 EUR x 1.10   = 110.000 USD    <- valuta conto, ok
        USDJPY   100.000 USD x 150    = 15.000.000 JPY <- NON dollari!

    Dividendo una commissione in USD per un nozionale in JPY si ottiene un
    numero privo di senso: sulla tabella del percorso precedente la
    commissione di USDJPY risultava 0.005 bp invece di ~0.65 bp, cioe' 130
    volte piu' bassa. Colpisce tutte le coppie in cui il dollaro non e' la
    valuta quotata (USDJPY, USDCHF, USDCAD) e tutti i cross.

    La via robusta usa `trade_tick_value`, che MT5 fornisce GIA' convertito
    nella valuta del conto: quanti tick ci sono in un movimento del 100%,
    moltiplicato per il valore di un tick.

        nozionale = prezzo / tick_size * tick_value

    Funziona senza casi speciali su forex, metalli, indici e crypto.
    """
    ts = getattr(info, "trade_tick_size", 0) or getattr(info, "point", 0)
    tv = getattr(info, "trade_tick_value", 0)
    if ts and tv:
        return prezzo / ts * tv
    return info.trade_contract_size * prezzo  # ripiego, valido se quotato in valuta conto


def nozionale_senza_mt5(symbol: str, prezzo: float,
                        valuta_conto: str = "USD") -> float:
    """
    Nozionale in valuta del conto senza MT5, per le sole coppie forex a 6
    lettere. Due casi su tre sono esatti senza bisogno di cambi esterni:

        conto nella valuta BASE     (EUR su EURUSD) -> 100.000 netti
        conto nella valuta QUOTATA  (USD su EURUSD) -> 100.000 x prezzo

    Il terzo caso (cross: conto USD su EURGBP) richiede un cambio che qui
    non c'e', e la funzione lo dice invece di indovinare.
    """
    s, v = (symbol or "").upper(), (valuta_conto or "").upper()
    if not (len(s) == 6 and s.isalpha()):
        raise ValueError(
            f"'{symbol}' non e' una coppia forex a 6 lettere: senza MT5 il "
            "nozionale non e' deducibile. Passa nozionale= a mano, oppure usa "
            "la strada con MT5."
        )
    base, quotata = s[:3], s[3:]
    if v == base:
        return CONTRATTO_FOREX
    if v == quotata:
        return CONTRATTO_FOREX * float(prezzo)
    raise ValueError(
        f"conto in {v} su {s}: ne' base ne' valuta quotata. Serve il cambio "
        f"{base}/{v}: passa nozionale= a mano, oppure usa la strada con MT5."
    )


# ========================================================================
# 3 · Lo spread
# ========================================================================

def spread_corrente(symbol: str, max_eta_secondi: int = 300,
                    verbose: bool = True) -> dict:
    """
    Spread dell'ULTIMO TICK (ask - bid).

    A COSA SERVE, E A COSA NO
    --------------------------
    Serve come CONTROLLO DI COERENZA accanto allo spread ricavato dalle
    barre: se i due numeri sono molto diversi, qualcosa non torna e si
    vede subito.

    NON serve come fonte del costo di un backtest pluriennale. E' un
    istante: lanciata nel weekend, durante il rollover o su una news
    restituisce un valore di un'altra grandezza, e non vede la variazione
    del costo nel tempo (che su BTCUSD e' il fattore dominante — vedi
    `deriva_costo_nel_tempo`).

    Rispetto alla `retrieve_latest_tick` di partenza, tre controlli:
      - il simbolo viene selezionato in Market Watch, altrimenti
        symbol_info_tick restituisce None e ._asdict() solleva
        AttributeError;
      - se il tick e' piu' vecchio di `max_eta_secondi` (mercato chiuso)
        il risultato e' marcato non fresco e viene stampato un avviso;
      - lo spread e' restituito in TRE unita' dichiarate: prezzo, punti,
        frazione. Mescolare punti e unita' di prezzo e' l'errore facile
        (la colonna `spread` delle barre e' in punti, ask-bid e' in
        prezzo).
    """
    mt5 = _mt5()
    mt5.symbol_select(symbol, True)
    info = _info(mt5, symbol)

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise ValueError(
            f"nessun tick per '{symbol}'. Il simbolo e' visibile in Market "
            "Watch? (mt5.symbol_select(symbol, True))"
        )
    d = tick._asdict()

    bid, ask = float(d["bid"]), float(d["ask"])
    if not (bid > 0 and ask > 0):
        raise ValueError(f"tick di '{symbol}' con bid/ask non validi: {bid}/{ask}")

    mid = (bid + ask) / 2.0
    spread_prezzo = ask - bid
    point = float(getattr(info, "point", 0) or 0)
    eta = time.time() - float(d.get("time", 0))
    fresco = eta <= max_eta_secondi

    out = {
        "spread_prezzo": spread_prezzo,
        "spread_punti": spread_prezzo / point if point else np.nan,
        "spread_rel": spread_prezzo / mid,
        "bid": bid, "ask": ask, "mid": mid,
        "eta_secondi": eta, "fresco": bool(fresco),
    }

    if verbose:
        print(f"{symbol}  spread corrente: {out['spread_prezzo']:.6g} di prezzo "
              f"= {out['spread_punti']:.1f} punti = {out['spread_rel']*1e4:.3f} bp")
        if not fresco:
            print(f"   ATTENZIONE: tick vecchio di {eta/60:.0f} minuti — mercato "
                  "probabilmente chiuso. Questo numero non rappresenta le "
                  "condizioni di esecuzione.")
    return out


def _spread_rel_da_barre(bars: pd.DataFrame, point: float, percentile: float,
                         col_close: str, col_spread: str) -> tuple[float, str]:
    """Spread relativo come percentile della colonna `spread` (in punti)."""
    c_close = _colonna(bars, col_close)
    c_spread = _colonna(bars, col_spread)
    sr = (bars[c_spread].astype(float) * point / bars[c_close].astype(float)).dropna()
    if sr.empty:
        raise ValueError(
            f"la colonna '{c_spread}' non contiene valori validi: impossibile "
            "ricavare lo spread dai dati."
        )
    valore = float(np.percentile(sr, percentile))
    fonte = f"barre ({len(sr):,} righe, percentile {percentile:.0f})"
    return valore, fonte


# ========================================================================
# 4 · Il costo dello strumento
# ========================================================================

def costo_simbolo(symbol: str, bars: pd.DataFrame | None = None,
                  percentile: float = 75.0, valuta_conto: str = "USD",
                  commissione_rt: float | None = None,
                  col_close: str = "Close", col_spread: str = "spread",
                  verbose: bool = True) -> dict:
    """
    Spread e commissione dello strumento, in FRAZIONE di prezzo, tenuti
    SEPARATI (per il perche' vedi `parametri_backtest`).

    Richiede MT5 (per le specifiche del simbolo). Per la strada senza MT5
    vedi `parametri_backtest(..., usa_mt5=False)`.

    bars
        Le barre MT5 con la colonna `spread` (quelle di
        `mt5.copy_rates_range`). Se mancano, o se la colonna non c'e', si
        ripiega su `spread_corrente` — che e' una fotografia di un istante:
        va bene per un ordine di grandezza, non per un backtest.
    percentile
        Percentile dello spread: 50 = mediana, 75 = prudente (default, vedi
        l'avvertenza in cima al modulo), 90 = pessimista.
    valuta_conto
        Valuta del conto: decide l'importo della commissione.
    commissione_rt
        Forza la commissione round-turn per lotto, scavalcando la tabella.

    Ritorna un dict:
        spread_rel     frazione di prezzo, spread pagato UNA volta
        comm_rel_rt    frazione di prezzo, commissione ROUND-TURN
        classe, nozionale, prezzo, commissione_rt, fonte_spread
    """
    mt5 = _mt5()
    info = _info(mt5, symbol)

    classe = classifica_simbolo(symbol, getattr(info, "path", ""))
    comm_rt = (commissione_round_turn(classe, valuta_conto)
               if commissione_rt is None else float(commissione_rt))

    point = float(getattr(info, "point", 0) or 0)

    # --- spread ---------------------------------------------------------
    ha_spread = False
    if bars is not None:
        try:
            _colonna(bars, col_spread)
            ha_spread = True
        except KeyError:
            ha_spread = False

    if ha_spread:
        spread_rel, fonte = _spread_rel_da_barre(bars, point, percentile,
                                                 col_close, col_spread)
    else:
        corrente = spread_corrente(symbol, verbose=False)
        spread_rel = corrente["spread_rel"]
        fonte = ("tick corrente — nessuna colonna 'spread' nelle barre "
                 "(fotografia di un istante)")

    # --- prezzo di riferimento e commissione ----------------------------
    if bars is not None:
        prezzo = float(bars[_colonna(bars, col_close)].astype(float).median())
    else:
        prezzo = float(getattr(info, "ask", 0) or getattr(info, "bid", 0) or 0)
    if not prezzo > 0:
        raise ValueError(f"prezzo di riferimento non valido per '{symbol}': {prezzo}")

    nozionale = nozionale_valuta_conto(info, prezzo)
    comm_rel_rt = (comm_rt / nozionale) if nozionale else 0.0

    out = {"spread_rel": spread_rel, "comm_rel_rt": comm_rel_rt,
           "classe": classe, "nozionale": nozionale, "prezzo": prezzo,
           "commissione_rt": comm_rt, "fonte_spread": fonte}

    if verbose:
        _stampa_costo(symbol, out, valuta_conto)
    return out


def _stampa_costo(symbol: str, c: dict, valuta_conto: str) -> None:
    rt = c["spread_rel"] + c["comm_rel_rt"]
    print(f"{symbol}  [{c['classe']}]  conto in {valuta_conto}")
    noz = c.get("nozionale")
    testo_noz = (f"{noz:,.0f} {valuta_conto}" if noz is not None and np.isfinite(noz)
                 else "— (non serve: niente commissione)")
    print(f"   prezzo mediano   : {c['prezzo']:,.6g}   nozionale: {testo_noz}")
    print(f"   spread           : {c['spread_rel']*1e4:6.3f} bp   <- {c['fonte_spread']}")
    print(f"   commissione      : {c['comm_rel_rt']*1e4:6.3f} bp   <- "
          f"{c['commissione_rt']:.2f} {valuta_conto} round-turn per lotto")
    print(f"   COSTO ROUND-TURN : {rt*1e4:6.3f} bp")


# ========================================================================
# 5 · Il ponte verso backtesting.py
# ========================================================================

def parametri_backtest(symbol: str, bars: pd.DataFrame | None = None,
                       valuta_conto: str = "USD", percentile: float = 75.0,
                       spread_pips: float | None = None,
                       pip_size: float | None = None,
                       prezzo: float | None = None,
                       nozionale: float | None = None,
                       commissione_rt: float | None = None,
                       col_close: str = "Close", col_spread: str = "spread",
                       usa_mt5: bool = True, verbose: bool = True) -> dict:
    """
    I due parametri di costo pronti per Backtest(), da spacchettare con **.

        costi = parametri_backtest("EURUSD", bars=df)
        es = run_exit_search_bt(df_is, ..., **costi)

    PERCHE' DUE PARAMETRI E NON UNO — E PERCHE' LA COMMISSIONE SI DIMEZZA
    ----------------------------------------------------------------------
    backtesting.py tratta i due costi in modo diverso. Verificato
    empiricamente su 0.6.6:

      `spread=`      applicato UNA volta sola, all'ingresso, DENTRO il
                     prezzo di fill. Con spread=0.00014 su 1.10000
                     l'EntryPrice diventa 1.1001540, l'ExitPrice resta
                     1.1000000. Corrisponde esattamente a pagare lo spread
                     una volta nel giro completo: ci va `spread_rel` cosi'
                     com'e'.

      `commission=`  addebitato all'ingresso E all'uscita, sulla cassa, non
                     sul prezzo. E' quindi un costo PER LATO. Un costo
                     round-turn passato qui verrebbe RADDOPPIATO:

                         commission = comm_rel_rt / 2

    Controprova numerica, EURUSD conto USD a prezzo 1.10:
        nozionale   = 100.000 EUR x 1.10       = 110.000 USD
        comm_rel_rt = 7.00 / 110.000           = 6.364e-05  (0.636 bp)
        commission  = 6.364e-05 / 2            = 3.182e-05
        costo       = 3.182e-05 x (1.10+1.10)  = 7.00e-05 di prezzo
                    = 0.700 pips round-turn

    LE DUE STRADE
    --------------
    usa_mt5=True (default): tutto da MT5 e dalle barre. E' la strada buona.
    usa_mt5=False: per un ambiente senza MT5 (Colab). Serve `spread_pips`
    (da listino) e il simbolo deve essere una coppia forex a 6 lettere, o
    va passato `nozionale`. E' un ripiego dichiarato, non equivalente.

    Ritorna {"spread": float, "commission": float}.
    """
    if usa_mt5:
        c = costo_simbolo(symbol, bars=bars, percentile=percentile,
                          valuta_conto=valuta_conto, commissione_rt=commissione_rt,
                          col_close=col_close, col_spread=col_spread,
                          verbose=False)
        spread_rel, comm_rel_rt = c["spread_rel"], c["comm_rel_rt"]
    else:
        if spread_pips is None:
            raise ValueError(
                "senza MT5 serve spread_pips (valore di listino dello spread, "
                "in pips). Su EURUSD Raw Spread e' ~0.1."
            )
        if prezzo is None:
            if bars is None:
                raise ValueError("senza MT5 serve prezzo= oppure bars=.")
            prezzo = float(bars[_colonna(bars, col_close)].astype(float).median())
        prezzo = float(prezzo)
        if pip_size is None:
            pip_size = deduci_pip(prezzo)

        classe = classifica_simbolo(symbol)
        comm_rt = (commissione_round_turn(classe, valuta_conto)
                   if commissione_rt is None else float(commissione_rt))
        # Il nozionale serve solo a convertire la commissione. Dove la
        # commissione e' zero (crypto, indici, azioni) non serve, e non si
        # chiede: nozionale_senza_mt5 sa calcolarlo solo per il forex.
        if nozionale is not None:
            noz = float(nozionale)
        elif comm_rt > 0:
            noz = nozionale_senza_mt5(symbol, prezzo, valuta_conto)
        else:
            noz = float("nan")

        spread_rel = float(spread_pips) * float(pip_size) / prezzo
        comm_rel_rt = (comm_rt / noz) if (comm_rt > 0 and noz) else 0.0
        c = {"spread_rel": spread_rel, "comm_rel_rt": comm_rel_rt,
             "classe": classe, "nozionale": noz, "prezzo": prezzo,
             "commissione_rt": comm_rt,
             "fonte_spread": f"listino ({spread_pips} pips) — senza MT5"}

    out = {"spread": float(spread_rel), "commission": float(comm_rel_rt) / 2.0}

    if verbose:
        _stampa_costo(symbol, c, valuta_conto)
        pip = pip_size if pip_size is not None else deduci_pip(c["prezzo"])
        costo_pips = out["commission"] * 2 * c["prezzo"] / pip
        spread_in_pips = spread_rel * c["prezzo"] / pip
        print(f"   -> spread={out['spread']:.3e}   commission={out['commission']:.3e}"
              f"   (commission e' PER LATO: round-turn / 2)")
        print(f"   -> in pips: spread {spread_in_pips:.3f} + commissione "
              f"{costo_pips:.3f} = {spread_in_pips + costo_pips:.3f} pips round-turn")
    return out


# ========================================================================
# 6 · Controlli
# ========================================================================

def deriva_costo_nel_tempo(symbol: str, bars: pd.DataFrame,
                           valuta_conto: str = "USD",
                           commissione_rt: float | None = None,
                           col_close: str = "Close", col_spread: str = "spread"
                           ) -> pd.DataFrame:
    """
    Il costo anno per anno.

    Risponde a una domanda che un costo scalare nasconde: il costo di
    questo strumento e' cambiato nel campione? Su BTCUSD la risposta e'
    si', di molto, perche' lo spread e' quasi fisso in dollari mentre il
    prezzo ha fatto piu' volte 10x.

    SE `costo_bp` VARIA DI UN FATTORE 2 O PIU', un backtest a costo
    costante e' inaffidabile e va rifatto a costo variabile.
    """
    mt5 = _mt5()
    info = _info(mt5, symbol)
    classe = classifica_simbolo(symbol, getattr(info, "path", ""))
    comm_rt = (commissione_round_turn(classe, valuta_conto)
               if commissione_rt is None else float(commissione_rt))
    point = float(getattr(info, "point", 0) or 0)

    c_close = _colonna(bars, col_close)
    c_spread = _colonna(bars, col_spread)

    b = bars.copy()
    b["_close"] = b[c_close].astype(float)
    b["spread_rel"] = b[c_spread].astype(float) * point / b["_close"]
    b["comm_rel"] = comm_rt / b["_close"].map(
        lambda p: nozionale_valuta_conto(info, p))
    b["costo_bp"] = (b["spread_rel"] + b["comm_rel"]) * 1e4

    out = b.groupby(b.index.year).agg(
        barre=("costo_bp", "size"),
        prezzo_mediano=("_close", "median"),
        spread_bp=("spread_rel", lambda s: s.median() * 1e4),
        comm_bp=("comm_rel", lambda s: s.median() * 1e4),
        costo_bp=("costo_bp", "median"),
    ).round(3)
    return out


def verifica_da_storico_deals(symbol: str, giorni: int = 365,
                              valuta_conto: str = "USD",
                              commissione_rt: float | None = None,
                              verbose: bool = True) -> dict:
    """
    La prova del nove: la commissione REALMENTE addebitata dal broker,
    letta dai tuoi deal MT5, confrontata con la tabella.

    Richiede MT5 inizializzato e uno storico di operazioni su `symbol`.

    COME SI RICAVA IL ROUND-TURN
    -----------------------------
        round_turn = 2 * somma(|commission|) / somma(volume)

    dove le somme corrono su TUTTI i deal (ingressi e uscite). La formula
    da' il risultato giusto in entrambe le convenzioni possibili:

      - commissione addebitata sui due lati (3.50 + 3.50 su 1+1 lotti):
        2 * 7.00 / 2.00 = 7.00
      - commissione addebitata solo all'ingresso (7.00 su 1+1 lotti):
        2 * 7.00 / 2.00 = 7.00

    LIMITE: una posizione aperta e non ancora chiusa nella finestra
    conta il solo ingresso e sposta il rapporto. Con poche decine di deal
    il numero e' indicativo; guarda `per_lotto_per_lato_mediana` e la
    dispersione prima di fidarti.

    Ritorna un dict con l'osservato, il valore di tabella e lo scostamento.
    """
    mt5 = _mt5()
    info = _info(mt5, symbol)
    classe = classifica_simbolo(symbol, getattr(info, "path", ""))
    atteso = (commissione_round_turn(classe, valuta_conto)
              if commissione_rt is None else float(commissione_rt))

    a = datetime.now()
    da = a - timedelta(days=int(giorni))
    deals = mt5.history_deals_get(da, a, group=f"*{symbol}*")
    if deals is None or len(deals) == 0:
        raise ValueError(
            f"nessun deal su '{symbol}' negli ultimi {giorni} giorni. "
            "Allarga `giorni`, o controlla che mt5.initialize() sia riuscito."
        )

    d = pd.DataFrame([x._asdict() for x in deals])
    # solo deal di mercato (type 0 = BUY, 1 = SELL): esclude versamenti,
    # prelievi, interessi, che hanno volume 0 e commissione 0.
    d = d[d["type"].isin([0, 1]) & (d["volume"] > 0)].copy()
    if d.empty:
        raise ValueError(
            f"nessun deal di mercato su '{symbol}' negli ultimi {giorni} giorni "
            "(solo operazioni di saldo)."
        )

    d["comm_abs"] = d["commission"].abs()
    d["per_lotto_per_lato"] = d["comm_abs"] / d["volume"]

    vol_tot = float(d["volume"].sum())
    osservato = 2.0 * float(d["comm_abs"].sum()) / vol_tot if vol_tot else np.nan
    scostamento = ((osservato - atteso) / atteso * 100.0) if atteso else np.nan

    out = {
        "symbol": symbol, "classe": classe, "n_deals": int(len(d)),
        "volume_totale_lotti": vol_tot,
        "commissione_totale": float(d["comm_abs"].sum()),
        "per_lotto_per_lato_mediana": float(d["per_lotto_per_lato"].median()),
        "per_lotto_per_lato_min": float(d["per_lotto_per_lato"].min()),
        "per_lotto_per_lato_max": float(d["per_lotto_per_lato"].max()),
        "round_turn_osservato": osservato,
        "round_turn_tabella": atteso,
        "scostamento_pct": scostamento,
    }

    if verbose:
        print(f"{symbol}  [{classe}]  {out['n_deals']} deal di mercato negli "
              f"ultimi {giorni} giorni, {vol_tot:.2f} lotti in tutto")
        print(f"   per lotto per lato : mediana {out['per_lotto_per_lato_mediana']:.3f}"
              f"   (min {out['per_lotto_per_lato_min']:.3f}"
              f"  max {out['per_lotto_per_lato_max']:.3f})")
        print(f"   ROUND-TURN osservato: {osservato:.3f} {valuta_conto}")
        print(f"   round-turn tabella  : {atteso:.3f} {valuta_conto}")
        if np.isfinite(scostamento):
            print(f"   scostamento         : {scostamento:+.1f}%")
            if abs(scostamento) > 10:
                print("   ATTENZIONE: scostamento oltre il 10% — la tabella "
                      "COMMISSIONE_RT non descrive questo conto. Usa il valore "
                      "osservato con commissione_rt=.")
        if out["per_lotto_per_lato_max"] > 3 * max(out["per_lotto_per_lato_mediana"], 1e-9):
            print("   nota: forte dispersione fra i deal — probabile mix di "
                  "convenzioni (commissione su un lato solo) o di simboli.")
    return out
