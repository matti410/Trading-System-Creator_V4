"""
Aggiornamento dei dati da exchange (25/10/2026, docs/70 §1, §6, §7.1).

A COSA SERVE
------------
Fino al 25/10 i dati si scaricavano a parte con scarica_dati_crypto.py e il
Lab li leggeva dal CSV. Ora, in locale, il Lab puo' aggiornarli a ogni run,
con il timeframe scelto alla schermata 1. Le due funzioni che lo script
aveva dentro (aggiorna, aggiorna_funding) stanno qui, con la stessa logica:
lo script e il Lab usano lo stesso codice.

    aggiorna_storico(symbol, timeframe, cartella)   le candele: se il CSV c'e'
        scarica solo le barre dopo l'ultima; se non c'e', tutto dal 2/1/2020.
        Salva il CSV ogni `salva_ogni` blocchi: un download interrotto riparte
        dall'ultima barra salvata (docs/70 §1.3).
    aggiorna_funding(symbol, cartella, timeframe)   il funding di un perpetual,
        con i controlli confrontati con le barre del timeframe scelto (lo
        script li faceva sempre su M15).
    aggiorna_per_lab(symbol, timeframe, cartella)   quello che fa la schermata 1
        con l'interruttore acceso: candele, spot della stessa coppia (per la
        basis dell'atlante) e funding sui perpetual. Un errore di rete NON
        ferma: si lavora sui dati che ci sono, con un avviso. Si ferma solo
        se il CSV delle candele non c'e' e non si riesce a scaricarlo.

SOLA LETTURA: solo le funzioni pubbliche di ccxt load_markets, fetch_ohlcv,
fetch_funding_rate_history, senza chiavi API (engine/exchange.apri_exchange).
Solo barre CHIUSE (exchange.scarica_storico scarta quella in corso).

Modulo ADDITIVO: le funzioni spostate dallo script danno gli stessi file.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd

from .exchange import (TIMEFRAME_CCXT, apri_exchange, controlla_funding, controlla_storico, file_funding,
                       ha_funding, leggi_csv, leggi_funding, parti_symbol, salva_csv, salva_funding,
                       scarica_funding, scarica_storico)

INIZIO = "2020-01-02"           # come i dati del broker (decisione di Mattia del 19/10/2026)
INIZIO_FUNDING = "2019-12-25"   # una settimana prima delle barre: i primi tassi coprono le prime barre
SALVA_OGNI = 100                # blocchi di fetch_ohlcv fra un salvataggio e l'altro (docs/70 §1.3)
LIMITE = 1000                   # barre per richiesta, come scarica_storico


def passo_timeframe(timeframe: str) -> pd.Timedelta:
    """La durata di una barra del timeframe (M15 -> 15 minuti)."""
    if timeframe not in TIMEFRAME_CCXT:
        raise ValueError(f"Timeframe {timeframe!r} non previsto: usa uno di {list(TIMEFRAME_CCXT)}.")
    return pd.Timedelta(TIMEFRAME_CCXT[timeframe].replace("m", "min"))


def file_storico(symbol: str, timeframe: str, cartella) -> Path:
    return Path(cartella) / f"{symbol}_{timeframe}.csv"


def _exchange(symbol: str, aperti: dict | None):
    """L'oggetto ccxt dell'exchange del symbol, aperto una volta sola (aperti: ccxt_id -> oggetto)."""
    aperti = {} if aperti is None else aperti
    p = parti_symbol(symbol)
    if p["ccxt_id"] not in aperti:
        aperti[p["ccxt_id"]] = apri_exchange(symbol)
    return aperti[p["ccxt_id"]]


def aggiorna_storico(symbol: str, timeframe: str, cartella, aperti: dict | None = None,
                     salva_ogni: int = SALVA_OGNI, limite: int = LIMITE, verbose: bool = True,
                     attesa: float = 2.0) -> dict:
    """
    Scarica (o completa) {cartella}/{symbol}_{timeframe}.csv e ne restituisce i
    controlli (exchange.controlla_storico), piu':
      nuove        quante barre in piu' rispetto a prima
      vecchia      l'ultima barra che c'era prima (None se il CSV non c'era)
    Lavora a tappe di `salva_ogni` blocchi di `limite` barre: dopo ogni tappa
    con barre nuove il CSV si salva. Se una tappa fallisce l'errore sale, ma le
    tappe prima sono gia' nel file.
    """
    ex = _exchange(symbol, aperti)
    f = file_storico(symbol, timeframe, cartella)
    passo = passo_timeframe(timeframe)
    vecchio = leggi_csv(f) if f.exists() else None
    vuoto = vecchio is None or vecchio.empty
    # come lo script: si riparte dall'ultima barra (riscaricata e tenuta nella versione nuova)
    da = pd.Timestamp(INIZIO, tz="UTC") if vuoto else vecchio.index[-1]
    tappa = passo * int(limite) * int(salva_ogni)
    df = None if vuoto else vecchio
    adesso = pd.Timestamp(time.time(), unit="s", tz="UTC")
    while da < adesso:
        a = da + tappa
        nuovo = scarica_storico(symbol, timeframe, da=da, a=a, ex=ex, limite=limite, verbose=verbose,
                                attesa=attesa)
        if len(nuovo):
            df = nuovo if df is None else pd.concat([df, nuovo])
            df = df[~df.index.duplicated(keep="last")].sort_index()
            salva_csv(df, f)
        da = a
    if df is None or df.empty:
        raise RuntimeError(f"{symbol} {timeframe}: l'exchange non ha restituito barre.")
    c = controlla_storico(df, timeframe)
    c["nuove"] = len(df) - (0 if vuoto else len(vecchio))
    c["vecchia"] = None if vuoto else vecchio.index[-1]
    return c


def aggiorna_funding(symbol: str, cartella, timeframe: str = "M15", aperti: dict | None = None,
                     verbose: bool = True) -> dict:
    """
    Scarica (o completa) {cartella}/<SYMBOL>_FUNDING.csv di un perpetual e ne
    restituisce i controlli, confrontati con le barre del `timeframe` se ci sono
    (lo script li confrontava sempre con M15, che resta il predefinito).
    """
    ex = _exchange(symbol, aperti)
    f = file_funding(symbol, cartella)
    vecchio = leggi_funding(f) if os.path.exists(f) else None
    da = (INIZIO_FUNDING if vecchio is None or vecchio.empty
          else vecchio.index[-1] + pd.Timedelta(minutes=1))
    nuovo = scarica_funding(symbol, da=da, ex=ex, verbose=verbose)
    tutto = nuovo if vecchio is None else pd.concat([vecchio, nuovo])
    if tutto.empty:
        raise RuntimeError(f"{symbol}: l'exchange non ha restituito tassi del funding.")
    salva_funding(tutto, f)
    funding = leggi_funding(f)
    barre = file_storico(symbol, timeframe, cartella)
    c = controlla_funding(funding, leggi_csv(barre) if barre.exists() else None)
    c["nuovi"] = len(funding) - (0 if vecchio is None else len(vecchio))
    return c


def controlli_nuove(symbol: str, timeframe: str, cartella, vecchia) -> dict:
    """
    I controlli sulle sole barre nuove (docs/70 §6.4): dall'ultima barra che
    c'era prima (compresa, cosi' un buco fra la vecchia e la prima nuova si
    vede) alla fine. Senza barra vecchia: su tutto il file.
    """
    df = leggi_csv(file_storico(symbol, timeframe, cartella))
    pezzo = df if vecchia is None else df.loc[pd.Timestamp(vecchia):]
    return controlla_storico(pezzo, timeframe)


def spot_della_coppia(symbol: str) -> str | None:
    """Lo spot dello stesso exchange e della stessa coppia di un perpetual (None sugli altri)."""
    p = parti_symbol(symbol)
    return f"{p['exchange']}_SPOT_{p['coppia']}" if p["mercato"] == "PERP" else None


def aggiorna_per_lab(symbol: str, timeframe: str, cartella, aperti: dict | None = None,
                     verbose: bool = True, attesa: float = 2.0) -> dict:
    """
    L'aggiornamento della schermata 1 con l'interruttore acceso (docs/70 §1.3).
    Ritorna un dizionario con una voce per parte, "candele", "spot" (solo
    perpetual), "funding" (solo perpetual), ciascuna:
        {"esito": "aggiornato" | "non aggiornato", "nome", "nuove", "dal", "al",
         "controlli" (sulle barre nuove), "errore" (il motivo, se non aggiornato)}
    Un errore di rete o dell'exchange non ferma: la parte resta «non
    aggiornato» con il motivo. Si ferma (FileNotFoundError) solo se il CSV
    delle candele non c'e' e non si riesce a scaricarlo.
    """
    aperti = {} if aperti is None else aperti
    Path(cartella).mkdir(parents=True, exist_ok=True)
    out = {}

    def candele(nome):
        f = file_storico(nome, timeframe, cartella)
        c_prima = leggi_csv(f).index[-1] if f.exists() else None
        try:
            c = aggiorna_storico(nome, timeframe, cartella, aperti=aperti, verbose=verbose, attesa=attesa)
        except Exception as e:                      # rete, manutenzione, exchange giu'
            return {"esito": "non aggiornato", "nome": nome, "nuove": 0, "errore": f"{type(e).__name__}: {e}"[:300],
                    "al": c_prima, "c_esiste": f.exists()}
        return {"esito": "aggiornato", "nome": nome, "nuove": c["nuove"],
                "dal": c["prima"] if c["vecchia"] is None else c["vecchia"], "al": c["ultima"],
                "controlli": controlli_nuove(nome, timeframe, cartella, c["vecchia"]), "c_esiste": True}

    out["candele"] = candele(symbol)
    if not out["candele"]["c_esiste"]:
        raise FileNotFoundError(
            f"Non trovo {file_storico(symbol, timeframe, cartella)} e non sono riuscito a scaricarlo "
            f"({out['candele']['errore']}). Controlla la connessione e riprova.")
    spot = spot_della_coppia(symbol)
    if spot is not None:
        out["spot"] = candele(spot)
    if ha_funding(symbol):
        try:
            c = aggiorna_funding(symbol, cartella, timeframe, aperti=aperti, verbose=verbose)
            out["funding"] = {"esito": "aggiornato", "nome": f"{symbol} funding", "nuove": c["nuovi"],
                              "al": c["ultimo"], "controlli": c}
        except Exception as e:
            f = file_funding(symbol, cartella)
            out["funding"] = {"esito": "non aggiornato", "nome": f"{symbol} funding", "nuove": 0,
                              "errore": f"{type(e).__name__}: {e}"[:300],
                              "al": leggi_funding(f).index[-1] if os.path.exists(f) else None}
    for v in out.values():
        v.pop("c_esiste", None)
    return out
