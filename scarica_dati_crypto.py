"""
Scarica dagli exchange crypto (Binance, Bybit) le candele dei symbol di
engine/simboli.py (SIMBOLI_EXCHANGE) e controlla la qualita' dei dati.

    python scarica_dati_crypto.py                      tutti i symbol, M15
    python scarica_dati_crypto.py M15 H1               piu' timeframe
    python scarica_dati_crypto.py M15 BINANCE_PERP_BTCUSDT BYBIT_SPOT_ETHUSDT
    python scarica_dati_crypto.py --solo-funding        solo il funding dei perpetual

Gira sul PC, NON su Colab: Binance e Bybit bloccano gli indirizzi degli Stati
Uniti, dove stanno i server di Colab. I CSV si caricano poi su Google Drive,
in Il mio Drive/Trading-System-Creator_V4/dati/, come quelli del broker.

Cosa fa, per ogni symbol e timeframe:
  1. scarica le candele dal 2/1/2020 (o dalla prima disponibile) a oggi con
     le SOLE funzioni pubbliche di lettura di ccxt (load_markets,
     fetch_ohlcv), senza chiavi API: nessun ordine e' possibile. Se il CSV
     c'e' gia', scarica solo le barre nuove e le aggiunge;
  2. salva dati/<SYMBOL>_<TF>.csv con le colonne
         Date,Open,High,Low,Close,Volume
     e Date in UTC (senza fuso scritto). Si legge con
         from engine.exchange import leggi_csv
         df = leggi_csv("dati/BINANCE_PERP_BTCUSDT_M15.csv")
  3. controlla, adattando docs/10 e docs/11 a un mercato aperto 24/7:
       - fuso: le date dell'exchange sono gia' UTC, non c'e' una regola da
         verificare;
       - barre doppie, barre fuori dalla griglia del timeframe, OHLC
         incoerenti, barre a volume zero;
       - buchi: ogni distacco piu' lungo di una barra (manutenzioni
         dell'exchange, dati mancanti), con i piu' lunghi;
       - quarantena: solo le barre dopo un'interruzione (il rollover del
         broker qui non esiste).
Sui perpetual, nello stesso giro (21/10/2026, docs/63 §5.1), scarica anche
il FUNDING con fetch_funding_rate_history (pubblica, sola lettura, senza
chiavi): dati/<SYMBOL>_FUNDING.csv con Date (UTC, arrotondata al minuto),
tasso e intervallo_ore (dalla liquidazione precedente, letto riga per riga:
e' cambiato nel tempo). Se il file c'e' gia', scarica solo i tassi nuovi.
Controlli: primo tasso rispetto alla prima barra, intervalli per anno,
liquidazioni mancanti, tassi anomali (si segnalano, non si tolgono).

A fine corsa stampa una tabella riassuntiva.

Richiede ccxt (pip install ccxt==4.5.78) e, sul PC di Mattia, truststore
(pip install truststore==0.10.1) per i certificati HTTPS di Windows.
"""
import os
import sys
from pathlib import Path

import pandas as pd

from engine.exchange import (SOGLIA_TASSO_ANOMALO, TIMEFRAME_CCXT, apri_exchange, controlla_funding,
                             controlla_storico, file_funding, ha_funding, leggi_csv, leggi_funding,
                             parti_symbol, salva_csv, salva_funding, scarica_funding, scarica_storico,
                             simboli_exchange)

INIZIO = "2020-01-02"       # come i dati del broker (decisione di Mattia del 19/10/2026)
INIZIO_FUNDING = "2019-12-25"   # una settimana prima delle barre: i primi tassi coprono le prime barre
CARTELLA = Path(__file__).resolve().parent / "dati"


def _argomenti(argv):
    argv = [a for a in argv if a != "--solo-funding"]
    tf = [a.upper() for a in argv if a.upper() in TIMEFRAME_CCXT]
    sym = [a.upper() for a in argv if a.upper() not in TIMEFRAME_CCXT]
    sconosciuti = [s for s in sym if s not in simboli_exchange()]
    if sconosciuti:
        sys.exit(f"Symbol non in SIMBOLI_EXCHANGE (engine/simboli.py): {sconosciuti}")
    return tf or ["M15"], sym or simboli_exchange()


def aggiorna(symbol: str, timeframe: str, aperti: dict) -> dict:
    """Scarica (o completa) un CSV e ne restituisce i controlli."""
    p = parti_symbol(symbol)
    if p["ccxt_id"] not in aperti:
        aperti[p["ccxt_id"]] = apri_exchange(symbol)
    ex = aperti[p["ccxt_id"]]
    f = CARTELLA / f"{symbol}_{timeframe}.csv"
    vecchio = leggi_csv(f) if f.exists() else None
    da = INIZIO if vecchio is None or vecchio.empty else vecchio.index[-1]
    nuovo = scarica_storico(symbol, timeframe, da=da, ex=ex)
    df = nuovo if vecchio is None else pd.concat([vecchio, nuovo])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    if df.empty:
        raise RuntimeError(f"{symbol} {timeframe}: l'exchange non ha restituito barre.")
    salva_csv(df, f)
    c = controlla_storico(df, timeframe)
    c["nuove"] = len(df) - (0 if vecchio is None else len(vecchio))
    return c


def aggiorna_funding(symbol: str, aperti: dict) -> dict:
    """
    Scarica (o completa) dati/<SYMBOL>_FUNDING.csv di un perpetual e ne
    restituisce i controlli, confrontati con le barre M15 se ci sono.
    """
    p = parti_symbol(symbol)
    if p["ccxt_id"] not in aperti:
        aperti[p["ccxt_id"]] = apri_exchange(symbol)
    ex = aperti[p["ccxt_id"]]
    f = file_funding(symbol, CARTELLA)
    vecchio = leggi_funding(f) if os.path.exists(f) else None
    da = (INIZIO_FUNDING if vecchio is None or vecchio.empty
          else vecchio.index[-1] + pd.Timedelta(minutes=1))
    nuovo = scarica_funding(symbol, da=da, ex=ex)
    tutto = nuovo if vecchio is None else pd.concat([vecchio, nuovo])
    if tutto.empty:
        raise RuntimeError(f"{symbol}: l'exchange non ha restituito tassi del funding.")
    salva_funding(tutto, f)
    funding = leggi_funding(f)
    barre = CARTELLA / f"{symbol}_M15.csv"
    c = controlla_funding(funding, leggi_csv(barre) if barre.exists() else None)
    c["nuovi"] = len(funding) - (0 if vecchio is None else len(vecchio))
    return c


def stampa_funding(symbol: str, c: dict) -> dict:
    """Stampa i controlli del funding e restituisce la riga del riepilogo."""
    print(f"  funding: {c['tassi']:,} tassi ({c['nuovi']:+,}) dal {c['primo']:%Y-%m-%d %H:%M} al "
          f"{c['ultimo']:%Y-%m-%d %H:%M} UTC · tasso medio {c['tasso_medio_8h'] * 100:.4f}% ogni 8 ore")
    if "ore_primo_tasso" in c:
        quando = "prima della" if c["ore_primo_tasso"] <= 0 else "dopo la"
        print(f"    primo tasso {abs(c['ore_primo_tasso']):,.1f} ore {quando} prima barra M15 "
              f"({c['prima_barra']:%Y-%m-%d %H:%M}) · copre le barre: "
              + ("si'" if c["copertura"] is None else f"NO, {c['copertura']}"))
    print("    intervalli fra le liquidazioni (ore), per anno:")
    print("      " + c["intervalli_per_anno"].to_string().replace("\n", "\n      "))
    print(f"    liquidazioni mancanti {c['mancanti']} {c['elenco_mancanti'][:3]} · fuori orario "
          f"{c['fuori_orario']} · tassi vuoti {c['senza_tasso']}")
    print(f"    tassi oltre {SOGLIA_TASSO_ANOMALO:.2%} (segnalati, non tolti): {c['anomali']} "
          + ", ".join(f"{t} {v:+.4%}" for t, v in c["elenco_anomali"]))
    return {"symbol": symbol, "tf": "FUNDING", "esito": "ok", "barre": c["tassi"],
            "dal": f"{c['primo']:%Y-%m-%d}", "al": f"{c['ultimo']:%Y-%m-%d}",
            "liquidazioni mancanti": c["mancanti"], "tassi anomali": c["anomali"],
            "copre le barre": ("-" if "copertura" not in c else "si" if c["copertura"] is None else "NO")}


def main(argv) -> None:
    timeframes, simboli = _argomenti(argv)
    solo_funding = "--solo-funding" in argv
    CARTELLA.mkdir(exist_ok=True)
    aperti, righe = {}, []
    for symbol in simboli:
        for tf in ([] if solo_funding else timeframes):
            print(f"{symbol} {tf} ...", flush=True)
            try:
                c = aggiorna(symbol, tf, aperti)
            except Exception as e:          # un exchange giu' non ferma gli altri
                print(f"  ERRORE: {type(e).__name__}: {str(e)[:200]}")
                righe.append({"symbol": symbol, "tf": tf, "esito": "ERRORE"})
                continue
            print(f"  {c['barre']:,} barre ({c['nuove']:+,}) dal {c['prima']:%Y-%m-%d %H:%M} "
                  f"al {c['ultima']:%Y-%m-%d %H:%M} UTC · buchi {c['buchi']} "
                  f"({c['barre_mancanti']:,} barre mancanti)")
            for inizio, durata in c["buchi_maggiori"][:3]:
                print(f"    buco dopo il {inizio} UTC, durata {durata}")
            righe.append({"symbol": symbol, "tf": tf, "esito": "ok", "barre": c["barre"],
                          "dal": f"{c['prima']:%Y-%m-%d}", "al": f"{c['ultima']:%Y-%m-%d}",
                          "doppie": c["doppie"], "fuori griglia": c["fuori_griglia"],
                          "buchi": c["buchi"], "barre mancanti": c["barre_mancanti"],
                          "volume zero": c["volume_zero"], "OHLC incoerenti": c["ohlc_incoerenti"],
                          "quarantena": c["dopo_interruzione"]})
        if ha_funding(symbol):           # 21/10/2026: il funding dei perpetual, nello stesso giro
            print(f"{symbol} funding ...", flush=True)
            try:
                righe.append(stampa_funding(symbol, aggiorna_funding(symbol, aperti)))
            except Exception as e:
                print(f"  ERRORE: {type(e).__name__}: {str(e)[:200]}")
                righe.append({"symbol": symbol, "tf": "FUNDING", "esito": "ERRORE"})
    print("\nRIEPILOGO")
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(pd.DataFrame(righe).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1:])
