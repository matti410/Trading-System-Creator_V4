"""
Suite di validazione della GIORNATA DEI SYMBOL DA EXCHANGE a 00:00 UTC
(20/10/2026, docs/63 §10.1 punto 3): l'interruttore di engine/livelli.py
(imposta_giornata, giornata_attiva), giorno_fx, range_finestra("ROLLOVER"),
primo_del_giorno, i periodi H4, D, W, M di indicatori.id_periodo, l'ATR del
money management, F39, F38, gap_trend e il caricamento di engine/vetrina.py.

Cosa verifica
-------------
A  l'interruttore: default 17:00 New York, valori ammessi, errore sugli altri;
B  il broker non cambia: con GIORNATA_FX la giornata e i periodi sono quelli
   di prima (formula di prima riscritta qui), anche nei cambi d'ora;
C  con GIORNATA_UTC: giornate da 00:00 a 00:00 UTC, H4 alle 0-4-8-12-16-20
   UTC, settimana dal lunedi' 00:00 UTC, mese UTC, E23 e un trigger al giorno;
D  ATR a 5 giornate UTC chiuse uguale al calcolo a mano sulle candele
   giornaliere UTC; la giornata in corso non entra;
E  nessun lookahead per troncamento (ATR, F39, F38, gap_trend, E23, E31);
F  le cache rispettano l'interruttore;
G  carica_storico: un symbol da exchange accende la giornata UTC, EURUSD
   (se c'e' in dati/) la riporta a 17:00 New York.

Come si lancia (da terminale, dalla cartella del progetto):

    python test_giornata_utc.py

Non serve la rete. G2 usa dati/EURUSD_M15.csv se c'e'.
Alla fine stampa «RISULTATO: N/N test superati».
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import warnings

import numpy as np
import pandas as pd

warnings.simplefilter("ignore")

import engine.vetrina as v
from engine import exchange as X
from engine import livelli as L
from engine import quarantena as Q
from engine.confidenza import gap_trend
from engine.indicatori import (accordo_orizzonti, atr_giornaliero_chiuso, colonne_multi_timeframe,
                               giorno_inside, id_periodo)

QUI = os.path.dirname(os.path.abspath(__file__))
DATI = os.path.join(QUI, "dati")


def muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def storico_24_7(inizio="2023-02-20", giorni=60, passo="15min", prezzo=30000.0, seme=11):
    """Un random walk 24/7 (copre il cambio d'ora USA del 12/3/2023 e quello europeo del 26/3)."""
    idx = pd.date_range(inizio, periods=int(pd.Timedelta(days=giorni) / pd.Timedelta(passo)),
                        freq=passo, tz="UTC")
    rng = np.random.default_rng(seme)
    close = prezzo * np.exp(np.cumsum(rng.normal(0, 0.002, len(idx))))
    open_ = np.r_[prezzo, close[:-1]]
    alto = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.001, len(idx))))
    basso = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.001, len(idx))))
    return pd.DataFrame({"Open": open_, "High": alto, "Low": basso, "Close": close,
                         "Volume": rng.uniform(1, 100, len(idx))}, index=idx.rename("Date"))


def progressivo(chiave) -> np.ndarray:
    """0, 1, 2, ... che cresce quando la chiave cambia (come id_periodo)."""
    chiave = np.asarray(chiave)
    nuovo = np.ones(len(chiave), dtype=np.int64)
    nuovo[1:] = chiave[1:] != chiave[:-1]
    return np.cumsum(nuovo) - 1


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def saltato(nome, motivo):
        print(f"  [SALTATO] {nome}  — {motivo}")

    df = storico_24_7()
    idx = pd.DatetimeIndex(df.index)
    Q.imposta_rollover(None)                       # come sui dati da exchange
    L.svuota_cache()

    # ------------------------------------------------------- interruttore --
    print("\nA · L'interruttore della giornata")
    check("A1. default: 17:00 New York (GIORNATA_FX)", L.giornata_attiva() == L.GIORNATA_FX)
    L.imposta_giornata(L.GIORNATA_UTC)
    ok_utc = L.giornata_attiva() == L.GIORNATA_UTC
    L.imposta_giornata()
    check("A2. imposta_giornata(GIORNATA_UTC) e ritorno al default", ok_utc and L.giornata_attiva() == L.GIORNATA_FX)
    try:
        L.imposta_giornata("NY")
        rifiutato = False
    except ValueError:
        rifiutato = True
    check("A3. un valore sconosciuto si ferma con errore", rifiutato and L.giornata_attiva() == L.GIORNATA_FX)

    # -------------------------------------------------- broker invariato --
    print("\nB · Con GIORNATA_FX nulla cambia (formula di prima)")
    L.imposta_giornata(L.GIORNATA_FX)
    ny = idx.tz_convert("America/New_York")
    data_fx = (ny + pd.Timedelta(hours=7)).date
    check("B1. giorno_fx = data a 17:00 New York, come prima", np.array_equal(L.giorno_fx(df).to_numpy(), progressivo(data_fx)))
    loc = ny.tz_localize(None) + pd.Timedelta(hours=7)
    giorni = loc.to_numpy().astype("datetime64[D]").astype(np.int64)
    attese = {"H4": giorni * 6 + loc.hour // 4, "D": giorni, "W": giorni - (giorni + 3) % 7,
              "M": loc.year.to_numpy() * 12 + loc.month.to_numpy()}
    check("B2. periodi H4, D, W, M ancorati alle 17:00 New York, come prima (cambi d'ora compresi)",
          all(np.array_equal(id_periodo(df, r), progressivo(c)) for r, c in attese.items()))
    nuovi_h4 = ny[np.r_[True, np.diff(id_periodo(df, "H4")) == 1]]
    check("B3. i blocchi H4 partono alle 17, 21, 1, 5, 9, 13 di New York",
          set(nuovi_h4[1:].hour) == {17, 21, 1, 5, 9, 13} and set(nuovi_h4[1:].minute) == {0})

    # ------------------------------------------------------- giornata UTC --
    print("\nC · Con GIORNATA_UTC: giornate e periodi da 00:00 UTC")
    L.imposta_giornata(L.GIORNATA_UTC)
    g = L.giorno_fx(df).to_numpy()
    inizi = idx[np.r_[True, np.diff(g) == 1]]
    check("C1. la giornata cambia solo alle 00:00 UTC, una per data UTC",
          bool(((inizi[1:].hour == 0) & (inizi[1:].minute == 0)).all())
          and g.max() + 1 == len(pd.unique(idx.date)), f"{g.max() + 1} giornate")
    check("C2. D di id_periodo identico a giorno_fx", np.array_equal(id_periodo(df, "D"), g))
    i4 = idx[np.r_[True, np.diff(id_periodo(df, "H4")) == 1]]
    check("C3. H4 alle 0, 4, 8, 12, 16, 20 UTC, anche nelle settimane del cambio d'ora",
          set(i4[1:].hour) == {0, 4, 8, 12, 16, 20} and set(i4[1:].minute) == {0})
    iw = idx[np.r_[True, np.diff(id_periodo(df, "W")) == 1]]
    check("C4. la settimana parte il lunedi' alle 00:00 UTC",
          bool(((iw[1:].dayofweek == 0) & (iw[1:].hour == 0) & (iw[1:].minute == 0)).all()), f"{len(iw)} settimane")
    im = idx[np.r_[True, np.diff(id_periodo(df, "M")) == 1]]
    check("C5. il mese parte il primo del mese alle 00:00 UTC",
          bool(((im[1:].day == 1) & (im[1:].hour == 0) & (im[1:].minute == 0)).all()) and len(im) == 3)
    rf = L.range_finestra(df, "ROLLOVER")
    giorno_utc = df.resample("1D").agg({"High": "max", "Low": "min"})
    ieri = idx.floor("D") - pd.Timedelta(days=1)
    dopo_il_primo = idx.floor("D") > idx[0].floor("D")
    check("C6. E23: il massimo e il minimo letti sono quelli della giornata UTC di ieri",
          np.allclose(rf["massimo"].to_numpy()[dopo_il_primo], giorno_utc["High"].reindex(ieri).to_numpy()[dopo_il_primo])
          and np.allclose(rf["minimo"].to_numpy()[dopo_il_primo], giorno_utc["Low"].reindex(ieri).to_numpy()[dopo_il_primo]))
    tutte = pd.Series(True, index=idx)
    primi = L.primo_del_giorno(tutte, df)
    check("C7. un trigger al giorno: la prima barra di ogni giornata e' quella delle 00:00 UTC",
          bool(((idx[primi.to_numpy()].hour == 0) & (idx[primi.to_numpy()].minute == 0)).all())
          and int(primi.sum()) == g.max() + 1)

    # -------------------------------------------------------------- ATR --
    print("\nD · ATR del money management sulle giornate UTC")
    atr = atr_giornaliero_chiuso(df)
    d = df.resample("1D").agg({"High": "max", "Low": "min", "Close": "last"})
    prima = d["Close"].shift(1)
    tr = (np.maximum(d["High"], prima) - np.minimum(d["Low"], prima)).where(prima.notna(), d["High"] - d["Low"])
    atr_mano = tr.rolling(5).mean().shift(1)           # visibile dal giorno dopo
    attesa = atr_mano.reindex(idx.floor("D")).to_numpy()
    check("D1. ATR a 5 giornate UTC chiuse = calcolo a mano su candele giornaliere UTC",
          np.allclose(atr.to_numpy(), attesa, equal_nan=True), f"{int(atr.notna().sum()):,} barre con valore")
    costante = atr.groupby(idx.date).nunique(dropna=False).max() == 1
    check("D2. dentro una giornata UTC l'ATR non cambia (la giornata in corso non entra)", bool(costante))
    L.imposta_giornata(L.GIORNATA_FX)
    atr_fx = atr_giornaliero_chiuso(df)
    L.imposta_giornata(L.GIORNATA_UTC)
    check("D3. con la giornata a 17:00 New York l'ATR e' un altro (l'interruttore conta)",
          not np.allclose(atr_fx.to_numpy(), atr.to_numpy(), equal_nan=True))

    # -------------------------------------------------------- lookahead --
    print("\nE · Nessun lookahead per troncamento (GIORNATA_UTC)")
    calcoli = {
        "ATR": lambda x: atr_giornaliero_chiuso(x),
        "F39 giorno inside": lambda x: giorno_inside(x),
        "F38 tre orizzonti": lambda x: accordo_orizzonti(x),
        "gap_trend": lambda x: gap_trend(x),
        "E23 massimo di ieri": lambda x: L.range_finestra(x, "ROLLOVER")["massimo"],
        "E31 e multi timeframe": lambda x: colonne_multi_timeframe(x),
    }
    tagli = [len(df) // 3 + 37, len(df) // 2 + 5, 2 * len(df) // 3 + 61]   # anche a meta' giornata
    for nome, f in calcoli.items():
        pieno = f(df)
        uguale = True
        for t in tagli:
            L.svuota_cache()
            corto = f(df.iloc[:t])
            a = np.asarray(pieno.iloc[:t], dtype=float)
            b = np.asarray(corto, dtype=float)
            uguale &= np.allclose(a, b, equal_nan=True)
        check(f"E. {nome}: i valori fino al taglio non cambiano se si tolgono le barre dopo", uguale)

    # ------------------------------------------------------------- cache --
    print("\nF · Le cache rispettano l'interruttore")
    L.svuota_cache()
    L.imposta_giornata(L.GIORNATA_FX)
    fx = L.range_finestra(df, "ROLLOVER")["massimo"].copy()
    L.imposta_giornata(L.GIORNATA_UTC)
    utc = L.range_finestra(df, "ROLLOVER")["massimo"]
    check("F1. range_finestra(\"ROLLOVER\") ricalcolato quando cambia la giornata (senza svuotare la cache)",
          not np.allclose(fx.to_numpy(), utc.to_numpy(), equal_nan=True))

    # ------------------------------------------------------ carica_storico --
    print("\nG · carica_storico imposta la giornata")
    L.imposta_giornata(L.GIORNATA_FX)
    with tempfile.TemporaryDirectory() as tmp:
        X.salva_csv(df, os.path.join(tmp, "BINANCE_PERP_BTCUSDT_M15.csv"))
        muto(v.carica_storico, "BINANCE_PERP_BTCUSDT", tmp, "M15")
        check("G1. un symbol da exchange accende la giornata 00:00 UTC (e spegne il rollover)",
              L.giornata_attiva() == L.GIORNATA_UTC and Q.rollover_attivo() is None)
    eur = os.path.join(DATI, "EURUSD_M15.csv")
    if not os.path.exists(eur):
        saltato("G2", "dati/EURUSD_M15.csv non c'e'")
    else:
        muto(v.carica_storico, "EURUSD", DATI, "M15")
        check("G2. EURUSD riporta la giornata a 17:00 New York (e il rollover)",
              L.giornata_attiva() == L.GIORNATA_FX and Q.rollover_attivo() == Q.ROLLOVER_DEFAULT)
    L.imposta_giornata(L.GIORNATA_FX)
    Q.imposta_rollover(Q.ROLLOVER_DEFAULT)

    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
