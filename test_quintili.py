"""
Collaudo dei quintili del rendimento giornaliero: E41 (docs/50 §10, riga 19;
variante di Mattia del 19/10/2026 sul momentum di Liu e Tsyvinski).

    A  la colonna quintile_giorno contro una riscrittura indipendente (un ciclo
       giornata per giornata con np.quantile), su un mercato 24/7 e su uno forex
    B  le due entry: verso giusto, una volta al giorno, solo sulla candela che
       finisce a mezzanotte UTC
    C  le soglie: 20° e 80° percentile delle 300 giornate PRIMA (oggi escluso);
       un caso a mano
    D  il riscaldamento: NaN finche' non ci sono 300 rendimenti precedenti
    E  il forex: il lunedi' parte dalla mezzanotte del venerdi'
    F  i timeframe: M5 e H1 come la riscrittura; H4 a mezzanotte UTC si', H4
       del broker (sfasate) colonna vuota
    G  il backtest: E41 apre a mezzanotte UTC e chiude dopo H barre
    H  lookahead per troncamento, con la trappola dei quintili su tutto il
       campione
    I  i symbol veri di dati/: conteggi e verifica_degenerazione su BTCUSD
    J  registrazione e colonna nell'elenco del collaudo

Esecuzione:  python test_quintili.py   (su Windows: PYTHONIOENCODING=utf-8)
"""
from __future__ import annotations

import contextlib
import io
import os
import sys

import numpy as np
import pandas as pd

CARTELLA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CARTELLA)

from engine import registry as R                                    # noqa: E402
from engine.collaudo_catalogo import mercato_sintetico, verifica_degenerazione, verifica_lookahead  # noqa: E402
from engine.exit_search_bt import run_exit_search_bt                # noqa: E402
from engine.indicatori import COLONNE_INDICATORI, quintile_giornaliero  # noqa: E402
from entry_long import TRIGGER_LONG, entry_daily_quintile_up, registra_trigger_long  # noqa: E402
from entry_short import (TRIGGER_SHORT, entry_short_daily_quintile_down,  # noqa: E402
                         registra_trigger_short)
from test_algoxplorer import _leggi                                 # noqa: E402

ENTRY_NUOVE = {"E41_DAILY_QUINTILE_UP": entry_daily_quintile_up,
               "E41_SHORT_DAILY_QUINTILE_DOWN": entry_short_daily_quintile_down}


def _mercato_24_7(inizio="2023-01-01", fine="2024-10-01", seme=3, freq="15min") -> pd.DataFrame:
    idx = pd.date_range(inizio, fine, freq=freq, tz="UTC", inclusive="left")
    rng = np.random.default_rng(seme)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, len(idx))))
    op = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"Open": op, "High": np.maximum(op, close) * 1.001, "Low": np.minimum(op, close) * 0.999,
                         "Close": close, "Volume": 100.0}, index=idx)


def _con_colonna(df: pd.DataFrame, **kw) -> pd.DataFrame:
    d = df.copy()
    d["quintile_giorno"] = quintile_giornaliero(d, **kw)["quintile_giorno"]
    return d


def _riferimento(df: pd.DataFrame, giornate=300, percentili=(0.20, 0.80)) -> pd.Series:
    """Riscrittura indipendente, giornata per giornata."""
    passo = df.index[1] - df.index[0]
    fine = (df.index + passo).tz_convert("UTC")
    close = df["Close"].to_numpy()
    esito = pd.Series(np.nan, index=df.index)
    chiusure, rendimenti, pronto = [], [], False
    for i, t in enumerate(fine):
        if pronto:
            esito.iloc[i] = 0.0
        if t.hour == 0 and t.minute == 0:
            chiusure.append(close[i])
            if len(chiusure) >= 2:
                r = chiusure[-1] / chiusure[-2] - 1
                if len(rendimenti) >= giornate:
                    lo, hi = np.quantile(rendimenti[-giornate:], percentili)
                    if not pronto:
                        pronto = True
                        esito.iloc[i] = 0.0
                    esito.iloc[i] = 1.0 if r > hi else (-1.0 if r < lo else 0.0)
                rendimenti.append(r)
    return esito


def _eventi(s: pd.Series) -> pd.Series:
    return s[s.fillna(0) != 0]


def main() -> int:
    ESITI: list[bool] = []

    def check(nome: str, condizione: bool, dettaglio: str = ""):
        ESITI.append(bool(condizione))
        stato = "OK  " if condizione else "FAIL"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def saltato(nome: str, motivo: str):
        print(f"  [SALT] {nome}  — {motivo}")

    crypto = _mercato_24_7()
    forex = mercato_sintetico("2023-01-01", "2024-10-01", seme=5)
    dc, df_ = _con_colonna(crypto), _con_colonna(forex)

    # =====================================================================
    print("\nA · LA COLONNA CONTRO UNA RISCRITTURA INDIPENDENTE\n" + "-" * 70)
    rc, rf = _riferimento(crypto), _riferimento(forex)
    ec, ef = _eventi(dc["quintile_giorno"]), _eventi(df_["quintile_giorno"])
    check("A1. 24/7: stessi eventi, stesse candele, stesso verso", ec.equals(_eventi(rc)), f"{len(ec)} eventi")
    check("A2. forex: stessi eventi, stesse candele, stesso verso", ef.equals(_eventi(rf)) and len(ef) > 30,
          f"{len(ef)} eventi")
    check("A3. 24/7 e forex: NaN e zeri dove li mette la riscrittura",
          dc["quintile_giorno"].isna().equals(rc.isna()) and df_["quintile_giorno"].isna().equals(rf.isna()))

    # =====================================================================
    print("\nB · LE DUE ENTRY\n" + "-" * 70)
    su, giu = entry_daily_quintile_up(dc), entry_short_daily_quintile_down(dc)
    check("B1. long dove quintile_giorno = +1, short dove -1, mai insieme",
          su.equals(dc["quintile_giorno"] == 1) and giu.equals(dc["quintile_giorno"] == -1) and not (su & giu).any())
    tutte = dc.index[su | giu]
    check("B2. solo sulla candela delle 23:45 UTC (finisce a mezzanotte), al massimo una al giorno",
          set(tutte.strftime("%H:%M")) == {"23:45"} and pd.Series(tutte.date).is_unique)
    pronte = int(dc["quintile_giorno"].notna().sum() // 96)
    check("B3. circa il 20% delle giornate per lato",
          0.12 < su.sum() / max(pronte, 1) < 0.28 and 0.12 < giu.sum() / max(pronte, 1) < 0.28,
          f"{su.sum()} su, {giu.sum()} giu' in {pronte} giornate")

    # =====================================================================
    print("\nC · LE SOGLIE\n" + "-" * 70)
    t = ec.index[7]
    fine_c = (crypto.index + pd.Timedelta(minutes=15))
    chiusure = crypto["Close"][(fine_c.hour == 0) & (fine_c.minute == 0)]
    fino = chiusure[chiusure.index <= t]
    rend = (fino / fino.shift(1) - 1).dropna().to_numpy()
    lo, hi = np.quantile(rend[-301:-1], [0.2, 0.8])
    r = rend[-1]
    atteso = 1.0 if r > hi else (-1.0 if r < lo else 0.0)
    check("C1. un caso a mano: il rendimento di oggi contro i quintili delle 300 giornate prima",
          dc.loc[t, "quintile_giorno"] == atteso != 0, f"r = {r:+.4f}, soglie {lo:+.4f} / {hi:+.4f}")
    stretti = _con_colonna(crypto, percentili=(0.05, 0.95))
    check("C2. con soglie piu' larghe (5° e 95°) gli eventi sono di meno",
          len(_eventi(stretti["quintile_giorno"])) < len(ec))

    # =====================================================================
    print("\nD · IL RISCALDAMENTO\n" + "-" * 70)
    n_chiusure = pd.Series(np.cumsum(((fine_c.hour == 0) & (fine_c.minute == 0))), index=crypto.index)
    primo = n_chiusure[dc["quintile_giorno"].notna()].min()
    check("D1. NaN finche' non ci sono 300 rendimenti prima di oggi: la prima giornata valutata e' la chiusura n. 302",
          primo == 302, f"prima chiusura valutata: {primo}")
    check("D2. meno di 300 giornate: colonna tutta NaN senza errore",
          quintile_giornaliero(crypto.iloc[: 250 * 96])["quintile_giorno"].isna().all())

    # =====================================================================
    print("\nE · IL FOREX\n" + "-" * 70)
    lun = ef[(ef.index + pd.Timedelta(minutes=15)).dayofweek == 0]
    t = lun.index[0]
    fine_f = forex.index + pd.Timedelta(minutes=15)
    ch_fx = forex["Close"][(fine_f.hour == 0) & (fine_f.minute == 0)]
    prima = ch_fx[ch_fx.index < t]
    check("E1. la giornata che chiude lunedi' a mezzanotte parte dalla mezzanotte del venerdi'",
          (prima.index[-1] + pd.Timedelta(minutes=15)).dayofweek == 4 and len(lun) > 3)

    # =====================================================================
    print("\nF · I TIMEFRAME\n" + "-" * 70)
    for passo in (5, 60):
        x = _mercato_24_7(freq=f"{passo}min", seme=11)
        m = _con_colonna(x)
        check(f"F1. candele da {passo} minuti: identica alla riscrittura",
              _eventi(m["quintile_giorno"]).equals(_eventi(_riferimento(x))) and len(_eventi(m["quintile_giorno"])) > 30)
    h4 = crypto.resample("4h").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
    a = _eventi(dc["quintile_giorno"])
    b = _eventi(_con_colonna(h4)["quintile_giorno"])
    check("F2. H4 che iniziano a mezzanotte UTC: stessi eventi delle M15, sulla candela delle 20:00",
          list(a.to_numpy()) == list(b.to_numpy()) and set(b.index.strftime("%H:%M")) == {"20:00"})
    sfasate = crypto.resample("4h", offset="1h").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last",
                                                       "Volume": "sum"})
    check("F3. H4 sfasate (come quelle del broker): colonna vuota senza errore",
          quintile_giornaliero(sfasate)["quintile_giorno"].isna().all())

    # =====================================================================
    print("\nG · IL BACKTEST\n" + "-" * 70)
    R.clear_registry()
    for k, f in ENTRY_NUOVE.items():
        R.register_entry(k, -1 if "SHORT" in k else 1)(f)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        es = run_exit_search_bt(dc, entry_cols_long=["E41_DAILY_QUINTILE_UP"],
                                entry_cols_short=["E41_SHORT_DAILY_QUINTILE_DOWN"], n_barre=96,
                                perc_sl=0, perc_tp=0, spread=0.0, commission=0.0,
                                cash=1_000_000, pip_size=0.01, verbose=False, min_trades=1, quarantena=False)
    tr = es.trades(es.risultati["combinazione"].iloc[0])
    entrate = pd.DatetimeIndex(tr["EntryTime"])
    check("G1. ogni trade si apre a mezzanotte UTC, il giorno dopo l'evento, e dura un giorno (96 barre)",
          set(entrate.strftime("%H:%M")) == {"00:00"} and len(tr) > 100
          and set(entrate) <= set(ec.index + pd.Timedelta(minutes=15)),
          f"{len(tr)} trade")
    R.clear_registry()

    # =====================================================================
    print("\nH · LOOKAHEAD PER TRONCAMENTO\n" + "-" * 70)

    def _prepara(d: pd.DataFrame) -> pd.DataFrame:
        d = _con_colonna(d, giornate=60)
        # trappola: l'80° percentile calcolato su TUTTO il campione
        passo = d.index[1] - d.index[0]
        f = d.index + passo
        e0 = (f.hour == 0) & (f.minute == 0)
        c0 = pd.Series(np.where(e0, d["Close"], np.nan), index=d.index)
        rend = c0.dropna().pct_change()
        soglia = rend.quantile(0.8) if rend.notna().any() else np.nan
        d["t_tutto"] = (rend.reindex(d.index) > soglia).astype(float)
        return d

    R.clear_registry()
    for k, f in ENTRY_NUOVE.items():
        R.register_entry(k, -1 if "SHORT" in k else 1)(f)
    R.register_entry("T_TUTTO", 1)(lambda d: d["t_tutto"] > 0)
    insiemi = [("24/7 sintetico", crypto.tail(120 * 96)), ("forex sintetico", forex.tail(120 * 96))]
    btc = _leggi("BTCUSD")
    if btc is not None:
        insiemi.append(("BTCUSD vero, ultime 12000 barre", btc.tail(12000)))
    for nome, dati in insiemi:
        with contextlib.redirect_stdout(io.StringIO()):
            rep = verifica_lookahead(dati, prepara=_prepara, tagli_per_condizione=8, riscaldamento=300,
                                     verbose=False).set_index("nome")
        check(f"H1. {nome}: la trappola (quintili su tutto il campione) e' segnata LOOKAHEAD",
              rep.loc["T_TUTTO", "esito"] == "LOOKAHEAD")
        esiti = {k: rep.loc[k, "esito"] for k in list(ENTRY_NUOVE) + ["quintile_giorno"]}
        check(f"H2. {nome}: entry e colonna OK (esercitate, nessun lookahead)",
              all(e == "OK" for e in esiti.values()), "" if all(e == "OK" for e in esiti.values()) else str(esiti))
    R.clear_registry()

    # =====================================================================
    print("\nI · I SYMBOL VERI DI dati/\n" + "-" * 70)
    simboli = ["EURUSD", "GBPUSD", "USDJPY", "NZDUSD", "BTCUSD", "US500", "USTEC", "XAUUSD", "DE40"]
    righe, ok_tutti, visti = [], True, 0
    for sym in simboli:
        with contextlib.redirect_stdout(io.StringIO()):
            vero = _leggi(sym)
        if vero is None:
            saltato(f"I. {sym}", "manca il file di dati")
            continue
        visti += 1
        d = _con_colonna(vero)
        su, giu = int(entry_daily_quintile_up(d).sum()), int(entry_short_daily_quintile_down(d).sum())
        ev = d.index[(d["quintile_giorno"].fillna(0) != 0).to_numpy()]
        righe.append({"symbol": sym, "E41 L": su, "E41 S": giu})
        ok_tutti &= su >= 100 and giu >= 100 and set((ev + pd.Timedelta(minutes=15)).strftime("%H:%M")) == {"00:00"}
    if righe:
        print(pd.DataFrame(righe).set_index("symbol").to_string())
        check("I1. su ogni symbol presente: almeno 100 eventi per lato, sempre sulla candela che finisce a mezzanotte UTC",
              ok_tutti, f"{visti} symbol")
    if btc is not None:
        R.clear_registry()
        for k, f in ENTRY_NUOVE.items():
            R.register_entry(k, -1 if "SHORT" in k else 1)(f)
        with contextlib.redirect_stdout(io.StringIO()):
            deg = verifica_degenerazione(_con_colonna(btc), verbose=False).set_index("nome")
        esiti = {k: deg.loc[k, "esito"] for k in ENTRY_NUOVE if k in deg.index}
        check("I2. verifica_degenerazione su BTCUSD M15: le due entry OK",
              len(esiti) == 2 and all(e == "OK" for e in esiti.values()), str(esiti))
        R.clear_registry()
    else:
        saltato("I2. verifica_degenerazione", "manca il file di dati")

    # =====================================================================
    print("\nJ · REGISTRAZIONE\n" + "-" * 70)
    R.clear_registry()
    with contextlib.redirect_stdout(io.StringIO()):
        registra_trigger_long()
        registra_trigger_short()
    check("J1. E41 nei dizionari dei trigger, con le funzioni giuste e la direzione giusta",
          all((TRIGGER_SHORT if "SHORT" in k else TRIGGER_LONG).get(k) is f for k, f in ENTRY_NUOVE.items())
          and all(R.get_entry_direction(k) == (-1 if "SHORT" in k else 1) for k in ENTRY_NUOVE))
    check("J2. la colonna nuova e' nell'elenco che il collaudo verifica", "quintile_giorno" in COLONNE_INDICATORI)
    R.clear_registry()

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(main())
