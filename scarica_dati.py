"""
Scarica da MT5 le barre M15 di piu' symbol e controlla la qualita' dei dati.

    python scarica_dati.py

Cosa fa, per ogni symbol:
  1. scarica le barre M15 dal 2020-01-01 a oggi con le sole funzioni di
     LETTURA di engine/mt5_interaction.py (nessun ordine inviato, modificato
     o chiuso);
  2. salva dati/<SYMBOL>_M15.csv nello stesso formato di EURUSD_M15.csv:
         Date,Open,High,Low,Close,Volume,spread
     con Date in ORA SERVER del broker, senza fuso (come arriva da MT5).
     La conversione in UTC si fa al caricamento, come nel notebook:
         df = pd.read_csv("dati/EURUSD_M15.csv", index_col="Date")
         df = to_utc_index(df, "A_US_DST (NY+7h)", on_dst_gap="drop")
  3. controlla, secondo docs/10 e docs/11:
       - fuso del broker: diagnose_broker_offset, solo sui symbol chiusi nel
         weekend. Chi tratta il sabato nell'ultimo anno (cripto) e' "aperto
         nel weekend" e la diagnosi non si fa (docs/10): i weekend chiusi di
         un passato lontano (BTCUSD nel 2020) non bastano. La regola e' una
         proprieta' del SERVER, quindi fa fede il consenso dei symbol forex;
       - conversione in UTC con la regola "A_US_DST (NY+7h)": barre scartate
         nei cambi d'ora;
       - pause oltre 1 ora che non sono il weekend, divise in due:
           pause ricorrenti  = la stessa pausa (stessa ora di New York di
                               chiusura e di riapertura) che si ripete in
                               almeno 20 volte: chiusura regolare del
                               mercato (ogni giorno per indici e oro, ogni
                               venerdi' per BTCUSD);
           buchi             = tutte le altre (festivi, manutenzioni, dati
                               mancanti);
       - quarantena: barre di rollover e dopo un'interruzione.
A fine corsa stampa una tabella riassuntiva.

Connessione: se esiste credenziali_mt5.txt usa start_mt5; altrimenti si
aggancia al terminale MT5 gia' aperto e collegato (MetaTrader5.initialize()
senza argomenti). Le credenziali non vengono mai stampate.

Formato di credenziali_mt5.txt (nel .gitignore, facoltativo), una voce per riga:
    login=12345678
    password=...
    server=ICMarketsSC-Demo
    path=C:\\Program Files\\MetaTrader 5\\terminal64.exe
"""
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

import MetaTrader5
from engine.mt5_interaction import (start_mt5, initialize_symbols,
                                    retrieve_candlestick_data_range)
from engine.broker_tz_diagnostic import diagnose_broker_offset, to_utc_index
from engine.quarantena import quarantena, verifica_indice_utc

# USDCAD tolto il 10/10/2026: IC Markets lo fornisce in M15 solo da gennaio 2025.
SYMBOLS = ["EURUSD", "BTCUSD", "GBPUSD", "USDJPY", "US500",
           "XAUUSD", "USTEC", "DE40", "NZDUSD"]
TIMEFRAME = "M15"
INIZIO = dt.datetime(2020, 1, 1)
CARTELLA = Path(__file__).resolve().parent / "dati"
FILE_CREDENZIALI = Path(__file__).resolve().parent / "credenziali_mt5.txt"

REGOLA_FUSO = "A_US_DST (NY+7h)"          # docs/10: regola verificata del server
BUCO_MINIMO = pd.Timedelta(hours=1)       # docs/11: soglia di interruzione
WEEKEND_MINIMO = pd.Timedelta(hours=36)   # una pausa di weekend dura ~48h
MATCH_MINIMO = 0.80                       # sotto, la diagnosi del fuso non e' affidabile
RIPETIZIONI_MINIME = 20                   # una pausa che torna 20+ volte e' una chiusura regolare
NY = "America/New_York"


# ------------------------------------------------------------ connessione --
def connetti() -> None:
    """Apre la connessione a MT5 senza mai stampare le credenziali."""
    if FILE_CREDENZIALI.exists():
        voci = {}
        for riga in FILE_CREDENZIALI.read_text(encoding="utf-8").splitlines():
            if "=" in riga:
                chiave, valore = riga.split("=", 1)
                voci[chiave.strip().lower()] = valore.strip()
        mancano = [k for k in ("login", "password", "server", "path") if not voci.get(k)]
        if mancano:
            sys.exit(f"credenziali_mt5.txt: mancano le voci {mancano}.")
        try:
            ok = start_mt5(voci["login"], voci["password"], voci["server"], voci["path"])
        except Exception:
            ok = False
        if not ok:
            sys.exit(f"Accesso a MT5 non riuscito (errore MT5: {MetaTrader5.last_error()}).")
        print("Collegato a MT5 con credenziali_mt5.txt.")
    else:
        if not MetaTrader5.initialize():
            sys.exit("MT5 non raggiungibile: apri MetaTrader 5, accedi al conto e "
                     f"riprova (errore MT5: {MetaTrader5.last_error()}).")
        print("Collegato al terminale MT5 gia' aperto.")
    info = MetaTrader5.account_info()
    if info is not None:
        print(f"Server: {info.server}")


# --------------------------------------------------------------- download --
def scarica(symbol: str) -> pd.DataFrame:
    """Barre M15 dal 2020-01-01 a oggi, indice naive in ora server."""
    try:
        initialize_symbols([symbol])
    except Exception:
        simili = MetaTrader5.symbols_get(group=f"*{symbol}*") or []
        nomi = ", ".join(s.name for s in simili[:8]) or "nessuno"
        raise RuntimeError(f"symbol non trovato nel terminale (nomi simili: {nomi})")
    fine = dt.datetime.now() + dt.timedelta(days=1)   # margine: arriva fino all'ultima barra
    try:
        df = retrieve_candlestick_data_range(INIZIO, fine, symbol, TIMEFRAME, dataframe=True)
    except Exception:
        raise RuntimeError(f"nessuna barra ricevuta (errore MT5: {MetaTrader5.last_error()})")
    if df is None or df.empty:
        raise RuntimeError(f"nessuna barra ricevuta (errore MT5: {MetaTrader5.last_error()})")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df[["Open", "High", "Low", "Close", "Volume", "spread"]]


# --------------------------------------------------------------- controlli --
def aperto_nel_weekend(df: pd.DataFrame) -> bool:
    """Vero se il symbol ha barre di sabato (ora server) nell'ultimo anno."""
    recenti = df.index[df.index >= df.index[-1] - pd.Timedelta(days=365)]
    return bool((recenti.dayofweek == 5).any())


def pause(df: pd.DataFrame) -> dict:
    """
    Pause oltre BUCO_MINIMO fra due barre, weekend esclusi, divise in
    ricorrenti (ripetute) e buchi (il resto).

    Una pausa e' identificata dall'ora di New York in cui il mercato smette
    di quotare (fine dell'ultima barra) e da quella in cui riprende. L'ora di
    New York, e non quella server, perche' gli orari di borsa sono in ora
    locale (docs/10). Se la stessa coppia si ripete almeno
    RIPETIZIONI_MINIME volte e' una chiusura regolare del mercato:
    quotidiana (indici, oro) o settimanale (la pausa del venerdi' di
    BTCUSD, docs/11).
    Le pause sfasate di un'ora nelle settimane in cui i DST americano ed
    europeo non coincidono (DE40) tornano ogni anno, quindi superano anch'esse
    la soglia nell'arco di qualche anno.
    """
    idx = df.index
    salti = pd.Series(idx).diff().to_numpy()
    passo = pd.Timedelta(minutes=15)
    weekend = salti >= WEEKEND_MINIMO
    lunghe = (salti > BUCO_MINIMO) & ~weekend
    pos = lunghe.nonzero()[0]

    ny = pd.DatetimeIndex((idx - pd.Timedelta(hours=7))
                          .tz_localize(NY, ambiguous="NaT", nonexistent="NaT"))
    chiude = ny[pos - 1] + passo                        # fine dell'ultima barra
    riapre = ny[pos]
    chiavi = pd.Series([f"{c:%H:%M}-{a:%H:%M}" if pd.notna(c) and pd.notna(a) else "?"
                        for c, a in zip(chiude, riapre)], dtype=object)
    conteggi = chiavi.map(chiavi.value_counts())
    ricorrente = ((conteggi >= RIPETIZIONI_MINIME) & (chiavi != "?")).to_numpy()

    durate = pd.Series(salti[pos])
    buchi = durate[~ricorrente]
    tipica = chiavi[ricorrente].value_counts()
    return {
        "weekend": int(weekend.sum()),
        "pause_ricorrenti": int(ricorrente.sum()),
        "pausa_tipica": f"{tipica.index[0]} NY" if len(tipica) else "-",
        "buchi": len(buchi),
        "buco_max": buchi.max() if len(buchi) else pd.Timedelta(0),
    }


def controlla(df: pd.DataFrame) -> dict:
    """Controlli di docs/10 e docs/11 su un df in ora server (indice naive)."""
    r = {"prima": df.index[0], "ultima": df.index[-1], "barre": len(df)}

    r.update(pause(df))
    r["primo_avviso"] = None
    if r["prima"] > INIZIO + dt.timedelta(days=10):
        r["primo_avviso"] = ("storico piu' corto del richiesto: in MT5 alza "
                             "Strumenti > Opzioni > Grafici > Barre max nel grafico")

    # Fuso del broker: serve la pausa del weekend (non sui 24/7, docs/10).
    r["aperto_weekend"] = aperto_nel_weekend(df)
    r["fuso"], r["match"] = "n.d. (aperto nel weekend)", None
    if not r["aperto_weekend"] and r["weekend"] >= 10:
        try:
            sintesi, _ = diagnose_broker_offset(df, verbose=False)
            r["fuso"], r["match"] = sintesi.iloc[0]["ipotesi"], float(sintesi.iloc[0]["match"])
        except Exception as e:
            r["fuso"] = f"errore: {e}"

    # Conversione in UTC con la regola verificata e quarantena.
    utc = to_utc_index(df, REGOLA_FUSO, on_dst_gap="drop", verbose=False)
    r["scartate_dst"] = len(df) - len(utc)
    try:
        verifica_indice_utc(utc, verbose=False)
        r["utc_ok"] = "n.d." if r["aperto_weekend"] or r["weekend"] < 10 else "OK"
    except ValueError:
        r["utc_ok"] = "n.d." if r["aperto_weekend"] else "NO"
    q = quarantena(utc, verbose=False)
    r["quarantena_pct"] = 100.0 * q["totale"].mean()
    return r


def _durata(t: pd.Timedelta) -> str:
    if t == pd.Timedelta(0):
        return "-"
    ore, resto = divmod(int(t.total_seconds()) // 60, 60)
    return f"{ore}h{resto:02d}m"


def stampa_tabella(risultati: dict) -> None:
    righe = []
    for sym, r in risultati.items():
        if "errore" in r:
            righe.append({"symbol": sym, "prima barra": "ERRORE (vedi avvisi)"})
            continue
        righe.append({
            "symbol": sym,
            "prima barra": f"{r['prima']:%Y-%m-%d %H:%M}",
            "ultima barra": f"{r['ultima']:%Y-%m-%d %H:%M}",
            "barre": f"{r['barre']:,}",
            "pause ricorr.": str(r["pause_ricorrenti"]),
            "pausa tipica": r["pausa_tipica"],
            "buchi>1h": str(r["buchi"]),
            "buco max": _durata(r["buco_max"]),
            "fuso (diagnosi)": r["fuso"],
            "match": "-" if r["match"] is None else f"{r['match']:.1%}",
            "UTC": r["utc_ok"],
            "scartate DST": str(r["scartate_dst"]),
            "quarantena": f"{r['quarantena_pct']:.2f}%",
        })
    tab = pd.DataFrame(righe).fillna("")
    print("\n" + "=" * 100)
    print("RIEPILOGO  (orari delle barre in ORA SERVER del broker, come nei file)")
    print("=" * 100)
    print(tab.to_string(index=False))

    print("\nAvvisi:")
    avvisi = 0
    for sym, r in risultati.items():
        if "errore" in r:
            print(f"  {sym}: {r['errore']}"); avvisi += 1
            continue
        if r["primo_avviso"]:
            print(f"  {sym}: {r['primo_avviso']}"); avvisi += 1
        if r["match"] is not None and (r["fuso"] != REGOLA_FUSO or r["match"] < MATCH_MINIMO):
            print(f"  {sym}: la riapertura del weekend non cade domenica 17:00 New York "
                  f"(diagnosi {r['fuso']}, match {r['match']:.1%}"
                  + (", verifica_indice_utc non superata" if r["utc_ok"] == "NO" else "")
                  + "). Atteso per indici e metalli, che riaprono a orari loro: "
                  "fa fede il fuso dei symbol forex."); avvisi += 1
    if not avvisi:
        print("  nessuno")

    # Consenso sul fuso: la regola e' del server, si legge sui symbol forex.
    forex = [r for r in risultati.values()
             if "errore" not in r and r["match"] is not None and r["match"] >= MATCH_MINIMO]
    regole = sorted({r["fuso"] for r in forex})
    print("\nFuso del broker (symbol con match >= 80%): "
          + (", ".join(regole) if regole else "nessuna diagnosi affidabile"))
    if regole == [REGOLA_FUSO]:
        print(f"  Confermato {REGOLA_FUSO} come in docs/10: i file si caricano con "
              f"to_utc_index(df, \"{REGOLA_FUSO}\", on_dst_gap=\"drop\").")
    else:
        print("  ATTENZIONE: diverso da docs/10. Non usare i file prima di aver capito perche'.")


# -------------------------------------------------------------------- main --
def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # la console di Windows non stampa tutti i caratteri
    except Exception:
        pass
    CARTELLA.mkdir(exist_ok=True)
    connetti()
    risultati = {}
    try:
        for sym in SYMBOLS:
            print(f"\n{sym}: scarico...", flush=True)
            try:
                df = scarica(sym)
            except RuntimeError as e:
                print(f"  ERRORE: {e}")
                risultati[sym] = {"errore": str(e)}
                continue
            percorso = CARTELLA / f"{sym}_{TIMEFRAME}.csv"
            df.to_csv(percorso)
            print(f"  {len(df):,} barre salvate in {percorso.relative_to(CARTELLA.parent)}")
            risultati[sym] = controlla(df)
    finally:
        MetaTrader5.shutdown()                   # chiude solo la connessione di Python, non il terminale
    stampa_tabella(risultati)


if __name__ == "__main__":
    main()
