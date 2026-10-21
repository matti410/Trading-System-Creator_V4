"""
Suite di validazione dei DATI DA EXCHANGE crypto (19/10/2026, versione
crypto del Lab): engine/exchange.py, le tabelle SIMBOLI_EXCHANGE /
LOTTI_EXCHANGE / LEVA_EXCHANGE di engine/simboli.py, l'interruttore del
rollover di engine/quarantena.py, il caricamento e i costi di
engine/vetrina.py (carica_storico, costi_storico, prepara) e la leva scelta
del money management.

Cosa verifica
-------------
A  le tabelle dei 16 symbol (pip, contratto, valuta, cifre, lotti, leva
   massima italiana: perpetual 2, spot 1) e la leva scelta;
B  nomi, commissioni e costi (commissione taker per lato, spread di un passo);
C  la quarantena: rollover spento sui dati da exchange, cache che rispettano
   l'interruttore, soglia delle interruzioni almeno due barre (H1, H4);
D  lettura dei CSV e controlli dei dati (doppie, griglia, buchi, OHLC, volume);
E  lo scaricamento a blocchi con un exchange FINTO (nessuna rete);
F  prepara su uno storico sintetico 24/7: perpetual e spot (solo long);
G  il broker non cambia: dopo un symbol da exchange EURUSD torna col rollover;
H  i CSV veri in dati/, se ci sono (scarica_dati_crypto.py).

Come si lancia (da terminale, dalla cartella del progetto):

    python test_exchange.py

Non serve la rete. Le sezioni G e H usano i CSV di dati/ se ci sono.
Alla fine stampa «RISULTATO: N/N test superati».
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import warnings

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")

import engine.vetrina as v
from engine import exchange as X
from engine import quarantena as Q
from engine.costi import classifica_simbolo
from engine.livelli import quarantena_cached
from engine.montecarlo import valore_pip_lotto
from engine.mm_adattatore import limiti_symbol
from engine.simboli import (LEVA, LEVA_EXCHANGE, LOTTI_EXCHANGE, SIMBOLI, SIMBOLI_EXCHANGE,
                            da_exchange, info_symbol, leva_scelta, leva_symbol, lotti_symbol,
                            pip_symbol)
from engine.stagionalita import fuso_profilo

QUI = os.path.dirname(os.path.abspath(__file__))
DATI = os.path.join(QUI, "dati")


def muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def storico_24_7(inizio="2023-01-01", giorni=200, passo="15min", prezzo=30000.0, seme=7):
    """Un random walk 24/7, senza weekend, con OHLC coerenti e volume > 0."""
    idx = pd.date_range(inizio, periods=int(pd.Timedelta(days=giorni) / pd.Timedelta(passo)),
                        freq=passo, tz="UTC")
    rng = np.random.default_rng(seme)
    r = rng.normal(0, 0.002, len(idx))
    close = prezzo * np.exp(np.cumsum(r))
    open_ = np.r_[prezzo, close[:-1]]
    alto = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.001, len(idx))))
    basso = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.001, len(idx))))
    return pd.DataFrame({"Open": open_, "High": alto, "Low": basso, "Close": close,
                         "Volume": rng.uniform(1, 100, len(idx))}, index=idx.rename("Date"))


class ExchangeFinto:
    """fetch_ohlcv come ccxt: dal `since` in avanti, al massimo `limit` barre."""

    def __init__(self, df, passo_ms, fermo=False):
        self.ms = (pd.DatetimeIndex(df.index).as_unit("ns").asi8 // 1_000_000).astype(np.int64)
        self.v = df[["Open", "High", "Low", "Close", "Volume"]].to_numpy()
        self.chiamate = 0
        self.fermo = fermo

    def fetch_ohlcv(self, simbolo, tf, since=None, limit=1000):
        self.chiamate += 1
        if self.fermo and self.chiamate > 1:
            since = int(self.ms[0])            # un exchange che non va avanti
        i = int(np.searchsorted(self.ms, since))
        return [[int(self.ms[k]), *map(float, self.v[k])] for k in range(i, min(i + limit, len(self.ms)))]


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def saltato(nome, motivo):
        print(f"  [SALTATO] {nome}  — {motivo}")

    def errore(f, tipo=Exception, testo=""):
        try:
            muto(f)
        except tipo as e:
            return testo in str(e)
        return False

    # ------------------------------------------------------------ tabelle --
    print("\nA · Le tabelle dei symbol da exchange")
    attesi = {f"{ex}_{m}_{c}USDT" for ex in ("BINANCE", "BYBIT") for m in ("SPOT", "PERP")
              for c in ("BTC", "ETH", "SOL", "XRP")}
    check("A1. 16 symbol: Binance e Bybit, spot e perpetual, BTC ETH SOL XRP",
          set(SIMBOLI_EXCHANGE) == attesi, f"{len(SIMBOLI_EXCHANGE)} symbol")
    pip_moneta = {"BTC": 1.0, "ETH": 0.1, "SOL": 0.01, "XRP": 0.0001}
    check("A2. pip fisso per moneta (BTC 1, ETH 0,1, SOL 0,01, XRP 0,0001), uguale su ogni mercato",
          all(pip_symbol(s) == pip_moneta[s.split("_")[2][:-4]] for s in attesi))
    check("A3. classe crypto, contratto 1, valuta USDT",
          all(info_symbol(s)["classe"] == "crypto" and info_symbol(s)["contratto"] == 1.0
              and info_symbol(s)["valuta"] == "USDT" for s in attesi))
    tick = {"BINANCE_SPOT_BTCUSDT": 0.01, "BINANCE_PERP_BTCUSDT": 0.1, "BYBIT_SPOT_BTCUSDT": 0.1,
            "BYBIT_PERP_XRPUSDT": 0.0001, "BINANCE_SPOT_SOLUSDT": 0.01}
    check("A4. cifre = decimali del passo di prezzo letto dall'exchange (19/10)",
          all(np.isclose(X.passo_prezzo(s), t) for s, t in tick.items()))
    check("A5. pip = passo di prezzo x una potenza di 10 (mai piu' fine del passo)",
          all(pip_symbol(s) >= X.passo_prezzo(s) - 1e-15
              and np.isclose(np.log10(pip_symbol(s) / X.passo_prezzo(s)),
                             round(np.log10(pip_symbol(s) / X.passo_prezzo(s)))) for s in attesi))
    check("A6. LOTTI_EXCHANGE e LEVA_EXCHANGE: stessi symbol di SIMBOLI_EXCHANGE",
          set(LOTTI_EXCHANGE) == attesi and set(LEVA_EXCHANGE) == attesi)
    coerenti = all(0 < m <= x and np.isclose(m / p, round(m / p)) and np.isclose(x / p, round(x / p))
                   for m, p, x in LOTTI_EXCHANGE.values())
    check("A7. lotti coerenti: minimo e massimo multipli del passo", coerenti)
    check("A8. lotti letti dall'exchange: Binance perpetual BTC 0,001 / 0,001 / 120",
          lotti_symbol("binance_perp_btcusdt") == {"minimo": 0.001, "passo": 0.001, "massimo": 120.0})
    check("A9. leva massima italiana: perpetual 2 (Consob 20976, ESMA 2026), spot 1",
          all(leva_symbol(s) == (2 if "_PERP_" in s else 1) for s in attesi))
    check("A10. leva scelta: None = la massima, 1,5 ammessa sul perpetual",
          leva_scelta("BYBIT_PERP_ETHUSDT") == 2 and leva_scelta("BYBIT_PERP_ETHUSDT", 1.5) == 1.5)
    check("A11. leva oltre il tetto italiano o sotto 1 -> errore",
          errore(lambda: leva_scelta("BINANCE_PERP_BTCUSDT", 3), ValueError, "Italia")
          and errore(lambda: leva_scelta("BINANCE_SPOT_BTCUSDT", 2), ValueError)
          and errore(lambda: leva_scelta("BINANCE_PERP_BTCUSDT", 0.5), ValueError))
    check("A12. limiti_symbol con la leva scelta; senza, la massima (come prima per i CFD)",
          limiti_symbol("BINANCE_PERP_BTCUSDT", valore_leva=1.5)["leva"] == 1.5
          and limiti_symbol("EURUSD")["leva"] == 30)
    check("A13. tabelle del broker intatte: 9 symbol, EURUSD 30, BTCUSD 2",
          len(SIMBOLI) == 9 and LEVA["EURUSD"] == 30 and LEVA["BTCUSD"] == 2
          and not da_exchange("BTCUSD") and da_exchange("bybit_spot_solusdt"))
    check("A14. symbol sconosciuto: l'errore cita anche SIMBOLI_EXCHANGE",
          errore(lambda: info_symbol("KRAKEN_SPOT_BTCUSD"), KeyError, "SIMBOLI_EXCHANGE"))

    # ------------------------------------------------- nomi, costi, classe --
    print("\nB · Nomi, commissioni e costi")
    p = X.parti_symbol("BINANCE_PERP_BTCUSDT")
    check("B1. BINANCE_PERP_BTCUSDT -> binanceusdm, BTC/USDT:USDT",
          p["ccxt_id"] == "binanceusdm" and p["ccxt_symbol"] == "BTC/USDT:USDT" and p["base"] == "BTC")
    p = X.parti_symbol("BYBIT_SPOT_XRPUSDT")
    check("B2. BYBIT_SPOT_XRPUSDT -> bybit, XRP/USDT", p["ccxt_id"] == "bybit" and p["ccxt_symbol"] == "XRP/USDT")
    check("B3. solo long sullo spot, long e short sul perpetual, mai sui CFD",
          X.solo_long("BINANCE_SPOT_ETHUSDT") and not X.solo_long("BINANCE_PERP_ETHUSDT")
          and not X.solo_long("BTCUSD"))
    check("B4. commissioni di listino (19/10): Binance perp 0,02/0,05%, Bybit perp 0,02/0,055%, spot 0,1%",
          X.commissioni("BINANCE_PERP_BTCUSDT") == {"maker": 0.0002, "taker": 0.0005}
          and X.commissioni("BYBIT_PERP_BTCUSDT") == {"maker": 0.0002, "taker": 0.00055}
          and X.commissioni("BINANCE_SPOT_BTCUSDT")["taker"] == 0.001
          and X.commissioni("BYBIT_SPOT_BTCUSDT")["taker"] == 0.001)
    sint = storico_24_7(giorni=10)
    c = X.costi_exchange("BINANCE_PERP_BTCUSDT", sint)
    mediana = float(sint["Close"].median())
    check("B5. commission = taker per lato (backtesting.py la addebita in entrata e in uscita)",
          c["commission"] == 0.0005)
    check("B6. spread = un passo di prezzo sul prezzo mediano, in pips 0,1 su BTC perpetual",
          np.isclose(c["spread"], 0.1 / mediana) and np.isclose(c["spread_pips"], 0.1)
          and c["pip_size"] == 1.0)
    check("B7. classifica_simbolo: i symbol da exchange sono crypto; BTCUSD e US30 come prima",
          classifica_simbolo("BYBIT_PERP_SOLUSDT") == "crypto" and classifica_simbolo("BTCUSD") == "crypto"
          and classifica_simbolo("US30") == "altro")
    check("B8. valore di 1 pip per 1 lotto (1 moneta): BTC 1 $, XRP 0,0001 $",
          valore_pip_lotto("BINANCE_PERP_BTCUSDT", 1.0) == 1.0
          and np.isclose(valore_pip_lotto("BYBIT_SPOT_XRPUSDT", 0.0001), 0.0001))
    check("B9. profilo orario in UTC sugli exchange, New York su BTCUSD del broker",
          fuso_profilo("BINANCE_PERP_BTCUSDT") == "UTC" and fuso_profilo("BTCUSD") == "America/New_York")

    # ---------------------------------------------------------- quarantena --
    print("\nC · La quarantena: rollover spento sui dati da exchange")
    Q.imposta_rollover(Q.ROLLOVER_DEFAULT)
    m15 = storico_24_7(giorni=20)
    acceso = Q.quarantena(m15, verbose=False)
    check("C1. finestra attiva di default: il rollover 16:45-18:00 NY marca 5 barre al giorno",
          Q.rollover_attivo() == Q.ROLLOVER_DEFAULT and int(acceso["rollover"].sum()) == 5 * 20)
    Q.imposta_rollover(None)
    spento = Q.quarantena(m15, verbose=False)
    check("C2. imposta_rollover(None): nessuna barra di rollover", int(spento["rollover"].sum()) == 0)
    check("C3. il parametro esplicito vale ancora: rollover=ROLLOVER_DEFAULT marca le stesse barre",
          Q.quarantena(m15, rollover=Q.ROLLOVER_DEFAULT, verbose=False)["rollover"].equals(acceso["rollover"]))
    q_off = quarantena_cached(m15)["rollover"].sum()
    Q.imposta_rollover(Q.ROLLOVER_DEFAULT)
    q_on = quarantena_cached(m15)["rollover"].sum()
    import entry_metro
    Q.imposta_rollover(None)
    metro_off = entry_metro.quarantena_cached(m15)["rollover"].sum()
    Q.imposta_rollover(Q.ROLLOVER_DEFAULT)
    metro_on = entry_metro.quarantena_cached(m15)["rollover"].sum()
    check("C4. le due cache (livelli, entry_metro) seguono l'interruttore, niente quarantene vecchie",
          q_off == 0 and q_on == 100 and metro_off == 0 and metro_on == 100)
    buco = m15.drop(m15.index[500:520])
    check("C5. dopo un buco (manutenzione) la prima barra resta in quarantena anche a rollover spento",
          int(Q.quarantena(buco, rollover=None, verbose=False)["dopo_interruzione"].sum()) == 1)
    h1 = storico_24_7(giorni=30, passo="1h")
    h4 = storico_24_7(giorni=60, passo="4h")
    check("C6. H1 e H4 24/7: nessuna barra «dopo un'interruzione» (prima le marcava tutte)",
          int(Q.quarantena(h1, rollover=None, verbose=False)["dopo_interruzione"].sum()) == 0
          and int(Q.quarantena(h4, rollover=None, verbose=False)["dopo_interruzione"].sum()) == 0)
    buco_h1 = h1.drop(h1.index[100:103])
    check("C7. H1: un buco di 4 ore e' ancora un'interruzione",
          int(Q.quarantena(buco_h1, rollover=None, verbose=False)["dopo_interruzione"].sum()) == 1)

    # ------------------------------------------------- lettura e controlli --
    print("\nD · Lettura dei CSV e controlli dei dati")
    with tempfile.TemporaryDirectory() as tmp:
        f = os.path.join(tmp, "x.csv")
        X.salva_csv(m15, f)
        prima_riga = open(f, encoding="utf-8").read().splitlines()[1]
        letto = X.leggi_csv(f)
        check("D1. CSV: Date in UTC senza fuso scritto; riletto con indice UTC identico",
              prima_riga.startswith("2023-01-01 00:00:00,") and str(letto.index.tz) == "UTC"
              and letto.index.equals(m15.index) and np.allclose(letto["Close"], m15["Close"]))
        doppio = pd.concat([m15.iloc[:10], m15.iloc[5:15]])
        X.salva_csv(doppio, f)
        check("D2. leggi_csv toglie le barre doppie e ordina", X.leggi_csv(f).index.equals(m15.index[:15]))
    sporco = m15.iloc[:1000].copy()
    sporco = pd.concat([sporco, sporco.iloc[[10]]])                     # una doppia
    sporco = sporco.drop(sporco.index[200:204])                         # un buco di 4 barre
    sporco.iloc[300, sporco.columns.get_loc("Volume")] = 0.0            # volume zero
    sporco.iloc[400, sporco.columns.get_loc("High")] = sporco.iloc[400]["Low"] * 0.99   # OHLC incoerente
    sporco.index = sporco.index.where(np.arange(len(sporco)) != 500,
                                      sporco.index[500] + pd.Timedelta(minutes=7))      # fuori griglia
    c = X.controlla_storico(sporco, "M15")
    check("D3. controlli: 1 doppia, 1 OHLC incoerente, 1 volume zero, 1 fuori griglia",
          c["doppie"] == 1 and c["ohlc_incoerenti"] == 1 and c["volume_zero"] == 1
          and c["fuori_griglia"] == 1, str({k: c[k] for k in ("doppie", "ohlc_incoerenti",
                                                              "volume_zero", "fuori_griglia")}))
    check("D4. il buco di 4 barre e' contato, con le barre mancanti",
          c["buchi"] >= 1 and c["barre_mancanti"] >= 4 and c["buchi_maggiori"][0][1] == "0 days 01:15:00",
          f"buchi {c['buchi']}, mancanti {c['barre_mancanti']}, il piu' lungo {c['buchi_maggiori'][0]}")
    pulito = X.controlla_storico(m15, "M15")
    check("D5. storico pulito: tutto a zero", all(pulito[k] == 0 for k in
          ("doppie", "fuori_griglia", "buchi", "volume_zero", "ohlc_incoerenti", "dopo_interruzione")))

    # ------------------------------------------------------- scaricamento --
    print("\nE · Scaricamento a blocchi, con un exchange finto (nessuna rete)")
    fonte = storico_24_7(inizio="2024-01-01", giorni=30)
    finto = ExchangeFinto(fonte, 900_000)
    giu = X.scarica_storico("BINANCE_PERP_BTCUSDT", "M15", da="2024-01-01", a="2024-01-31",
                            ex=finto, limite=500, verbose=False)
    check("E1. tutte le barre richieste, a blocchi di 500, senza doppie",
          len(giu) == 30 * 96 and giu.index.is_unique and finto.chiamate >= 6,
          f"{len(giu)} barre in {finto.chiamate} chiamate")
    check("E2. valori e date identici alla fonte, indice UTC in nanosecondi",
          giu.index.equals(fonte.index) and np.allclose(giu["Close"], fonte["Close"])
          and str(giu.index.dtype) == "datetime64[ns, UTC]")
    giu2 = X.scarica_storico("BINANCE_PERP_BTCUSDT", "M15", da="2024-01-10", a="2024-01-11",
                             ex=ExchangeFinto(fonte, 900_000), verbose=False)
    check("E3. finestra da-a rispettata, solo barre chiuse prima di «a»",
          len(giu2) == 96 and giu2.index[0] == pd.Timestamp("2024-01-10", tz="UTC")
          and giu2.index[-1] == pd.Timestamp("2024-01-10 23:45", tz="UTC"))
    bloccato = ExchangeFinto(fonte, 900_000, fermo=True)
    X.scarica_storico("BINANCE_PERP_BTCUSDT", "M15", da="2024-01-01", ex=bloccato, limite=100,
                      verbose=False)
    check("E4. un exchange che non va avanti non fa girare all'infinito", bloccato.chiamate == 2)
    class Capriccioso(ExchangeFinto):
        """Come Bybit il 19/10: ogni tanto «internal error», poi risponde."""
        def __init__(self, *a, errori=2, **k):
            super().__init__(*a, **k)
            self.errori = errori

        def fetch_ohlcv(self, *a, **k):
            if self.errori > 0:
                self.errori -= 1
                raise RuntimeError('bybit {"retCode":10016,"retMsg":"internal error"}')
            return super().fetch_ohlcv(*a, **k)

    cap = Capriccioso(fonte, 900_000, errori=2)
    giu3 = X.scarica_storico("BYBIT_PERP_BTCUSDT", "M15", da="2024-01-01", a="2024-01-31", ex=cap,
                             limite=500, verbose=False, attesa=0.01)
    check("E4b. errori temporanei del server: si riprova e lo storico arriva intero",
          giu3.index.equals(fonte.index))
    check("E4c. un errore che non passa si ferma dopo i tentativi previsti",
          errore(lambda: X.scarica_storico("BYBIT_PERP_BTCUSDT", "M15", da="2024-01-01", a="2024-01-31",
                                           ex=Capriccioso(fonte, 900_000, errori=99), tentativi=3,
                                           attesa=0.01), RuntimeError, "internal error"))
    check("E5. timeframe sconosciuto -> errore",
          errore(lambda: X.scarica_storico("BINANCE_PERP_BTCUSDT", "M7", ex=finto), ValueError))
    sorgente = (open(os.path.join(QUI, "engine", "exchange.py"), encoding="utf-8").read()
                + open(os.path.join(QUI, "scarica_dati_crypto.py"), encoding="utf-8").read())
    check("E6. solo dati pubblici: nessuna chiave API, nessuna funzione di ordine nel codice",
          not any(k in sorgente for k in ("apiKey", "secret", "create_order", "cancel_order",
                                          "edit_order", "fetch_balance")))

    # ------------------------------------------------------------- prepara --
    print("\nF · prepara su uno storico sintetico 24/7 (perpetual e spot)")
    with tempfile.TemporaryDirectory() as tmp:
        dati = storico_24_7(giorni=200)
        for nome in ("BINANCE_PERP_BTCUSDT", "BINANCE_SPOT_BTCUSDT"):
            X.salva_csv(dati, os.path.join(tmp, f"{nome}_M15.csv"))
        X.salva_csv(dati, os.path.join(tmp, "BYBIT_PERP_BTCUSDT_M30.csv"))    # nome sbagliato: barre M15
        # 21/10/2026: sui perpetual il funding e' acceso di default, serve il suo CSV (test_funding.py)
        orari = pd.date_range(dati.index[0].floor("8h"), dati.index[-1].ceil("8h"), freq="8h")
        X.salva_funding(X.con_intervalli(pd.DataFrame({"tasso": 0.0001}, index=orari.rename("Date"))),
                        X.file_funding("BINANCE_PERP_BTCUSDT", tmp))
        s = muto(v.prepara, "BINANCE_PERP_BTCUSDT", H=8, cartella=tmp)
        check("F1. perpetual: dati da exchange, long e short, profilo e orari in UTC",
              s.da_exchange and not s.solo_long and s.lati() == (1, -1) and s.fuso == "UTC"
              and s.timeframe == "M15")
        check("F2. costi: commissione taker 0,05% per lato, spread un passo, nessun rollover",
              s.costi["commission"] == 0.0005 and np.isclose(s.costi["spread"] * float(dati["Close"].median()), 0.1)
              and s.costi["spread_rollover_pips"] is None and s.spread_rollover_pips is None)
        check("F3. nessuna barra di rollover in quarantena (rollover spento)",
              Q.rollover_attivo() is None and int(quarantena_cached(s.df)["rollover"].sum()) == 0)
        rie = s.tabelle["riepilogo"]
        testo = " ".join(rie[" "].astype(str))
        check("F4. riepilogo: barre M15, ore dell'orizzonte da 15 minuti, funding contato (dal 21/10/2026)",
              "Barre M15" in list(rie[""]) and "8 barre (2,0 ore)" in testo
              and "Funding (perpetual)" in list(rie[""]) and "nessun rollover" in testo
              and rie.set_index("")[" "]["Funding (perpetual)"].startswith("contato"))
        s2 = muto(v.prepara, "BINANCE_SPOT_BTCUSDT", H=8, cartella=tmp)
        check("F5. spot: solo long, commissione 0,1%, nessuna riga di funding",
              s2.solo_long and s2.lati() == (1,) and s2.costi["commission"] == 0.001
              and "Funding (perpetual)" not in list(s2.tabelle["riepilogo"][""]))
        muto(v.esplora, s2)
        check("F6. spot: l'event study misura solo trigger long",
              len(s2.ev.sintesi) > 0 and set(s2.ev.sintesi["direction"]) == {1})
        check("F7. spot: scegliere un trigger short si ferma con la spiegazione",
              errore(lambda: v.scegli_trigger(s2, long="E1_RSI_CROSS_OVERSOLD",
                                              short="E4_SHORT_EMA_CROSS_DOWN"), ValueError, "spot"))
        muto(v.scegli_trigger, s2, long="E1_RSI_CROSS_OVERSOLD")
        tab = muto(v.imposta_uscite, s2, barre_long=8, sl=90)
        check("F8. spot: il sistema base gira con il solo lato long",
              list(tab["Sistema"]) == ["Solo long"] and int(tab["Trade"].iloc[0]) > 0,
              f"{int(tab['Trade'].iloc[0])} trade")
        check("F9. il CSV deve avere il timeframe del nome (barre M15 in un file M30 -> errore)",
              errore(lambda: v.carica_storico("BYBIT_PERP_BTCUSDT", tmp, "M30"), ValueError, "M30"))
        check("F10. timeframe fuori elenco o file mancante -> errore con l'istruzione",
              errore(lambda: v.carica_storico("BINANCE_PERP_BTCUSDT", tmp, "M7"), ValueError)
              and errore(lambda: v.carica_storico("BYBIT_SPOT_ETHUSDT", tmp, "M15"), FileNotFoundError,
                         "scarica_dati_crypto.py"))
        h1 = dati.resample("1h").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last",
                                      "Volume": "sum"})
        X.salva_csv(h1, os.path.join(tmp, "BINANCE_PERP_BTCUSDT_H1.csv"))
        s3 = muto(v.prepara, "BINANCE_PERP_BTCUSDT", H=8, cartella=tmp, timeframe="H1")
        check("F11. timeframe H1: «Barre H1» e 8 barre = 8 ore; nessuna barra in quarantena",
              "Barre H1" in list(s3.tabelle["riepilogo"][""])
              and "8 barre (8,0 ore)" in " ".join(s3.tabelle["riepilogo"][" "].astype(str))
              and int(quarantena_cached(s3.df)["totale"].sum()) == 0)
        from engine.montecarlo import sizing
        sz_btc = sizing(1000.0, 10.0, 1.0, passo=v.passo_lotti("BINANCE_PERP_BTCUSDT"))
        sz_cfd = sizing(1000.0, 10.0, 1.0)
        check("F12b. lotti consigliati al passo dell'exchange: 0,01 BTC calcolati -> 0,01, "
              "0,0069 -> 0,006 (prima 0); broker al passo 0,01 come prima",
              sz_btc["lotti_consigliati"] == 0.01
              and sizing(1000.0, 6.9, 1.0, passo=0.001)["lotti_consigliati"] == 0.006
              and sizing(1000.0, 6.9, 1.0)["lotti_consigliati"] == 0.0
              and sz_cfd["lotti_consigliati"] == 0.01 and v.passo_lotti("EURUSD") == 0.01)
        check("F12. money management: leva oltre il tetto si ferma subito",
              errore(lambda: v.money_management_trade("BINANCE_PERP_BTCUSDT", s.df_is.iloc[:0], s.df_is,
                                                      None, None, pip=1.0, leva=5), ValueError, "Italia"))

    # ------------------------------------------------- il broker non cambia --
    print("\nG · Il broker non cambia")
    eur = os.path.join(DATI, "EURUSD_M15.csv")
    if not os.path.exists(eur):
        saltato("G", "dati/EURUSD_M15.csv non c'e'")
    else:
        Q.imposta_rollover(None)
        df = muto(v.carica_storico, "EURUSD", DATI, "M15")
        check("G1. caricare EURUSD riaccende il rollover 16:45-18:00 NY",
              Q.rollover_attivo() == Q.ROLLOVER_DEFAULT)
        q_nuova = Q.quarantena(df, verbose=False)
        q_vecchia = Q.quarantena(df, rollover=("16:45", "18:00"), soglia_interruzione_min=60, verbose=False)
        check("G2. quarantena di EURUSD M15 identica a prima (stessa finestra, stessa soglia di 60 minuti)",
              q_nuova.equals(q_vecchia), f"{int(q_nuova['totale'].sum()):,} barre")
        costi, sp = v.costi_storico("EURUSD", df)
        check("G3. costi di EURUSD dal listino, come prima: 0,8 pips, nessuna commissione",
              sp["normale"] == 0.8 and sp["rollover"] == 1.5 and costi["commission"] == 0.0
              and costi["pip_size"] == 0.0001)

    # ------------------------------------------------------- i CSV veri --
    print("\nH · I CSV veri in dati/ (scarica_dati_crypto.py)")
    trovati = [s for s in SIMBOLI_EXCHANGE if os.path.exists(os.path.join(DATI, f"{s}_M15.csv"))]
    if not trovati:
        saltato("H", "nessun CSV da exchange in dati/")
    else:
        problemi, incoerenti = {}, {}
        for nome in trovati:
            c = X.controlla_storico(X.leggi_csv(os.path.join(DATI, f"{nome}_M15.csv")), "M15")
            if c["doppie"] or c["fuori_griglia"]:
                problemi[nome] = (c["doppie"], c["fuori_griglia"])
            if c["ohlc_incoerenti"]:
                incoerenti[nome] = c["ohlc_incoerenti"]
        check(f"H1. {len(trovati)} CSV: nessuna barra doppia, nessuna barra fuori griglia",
              not problemi, str(problemi) if problemi else "")
        # 19/10/2026: BYBIT_PERP_XRPUSDT ha una barra (10/6/2021 23:30) con l'Open un passo sotto
        # il Low, un difetto dell'exchange. I dati non si correggono: si ammettono casi isolati
        check("H1b. barre con OHLC incoerenti: al massimo casi isolati (1 per file), elencati",
              all(n <= 1 for n in incoerenti.values()), str(incoerenti) if incoerenti else "nessuna")
        if "BINANCE_PERP_BTCUSDT" in trovati:
            s = muto(v.prepara, "BINANCE_PERP_BTCUSDT", H=31, cartella=DATI)
            check("H2. prepara su BINANCE_PERP_BTCUSDT M15 vero: dal 2/1/2020, UTC, commissione 0,05%",
                  s.df.index[0] < pd.Timestamp("2020-02-01", tz="UTC") and s.costi["commission"] == 0.0005,
                  f"{len(s.df):,} barre")
    Q.imposta_rollover(Q.ROLLOVER_DEFAULT)

    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
