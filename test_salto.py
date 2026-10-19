"""
Collaudo del momentum dopo un salto: E40 (docs/50 §10, riga 18; scheda
approvata da Mattia il 19/10/2026, Baltussen, Da, Lammers, Martens 2021,
§4.3).

    A  la colonna salto contro una riscrittura indipendente (un ciclo candela
       per candela con np.quantile), su un mercato 24/7 e su uno forex
    B  le due entry: verso giusto, al massimo una volta al giorno, solo sui
       controlli di mezz'ora, mai sulla candela delle 17:00
    C  le soglie: 10° e 90° percentile delle 250 giornate chiuse; un caso a mano
    D  il riscaldamento: NaN finche' non ci sono 250 rendimenti giornalieri
    E  il forex: il lunedi' parte dalla chiusura del venerdi'
    F  i timeframe: M5 e M30 come la riscrittura; H1 e H4 colonna vuota
    G  il backtest: E40 con X_ORA_@17:00 apre al controllo e chiude alle 17:00
    H  lookahead per troncamento, con la trappola del percentile su tutto il
       campione (come nel paper)
    I  i symbol veri di dati/: conteggi e verifica_degenerazione su BTCUSD
    J  registrazione e colonna nell'elenco del collaudo

Esecuzione:  python test_salto.py   (su Windows: PYTHONIOENCODING=utf-8)
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

import condizioni_orarie as co                                      # noqa: E402
from engine import registry as R                                    # noqa: E402
from engine.collaudo_catalogo import mercato_sintetico, verifica_degenerazione, verifica_lookahead  # noqa: E402
from engine.exit_search_bt import run_exit_search_bt                # noqa: E402
from engine.indicatori import COLONNE_INDICATORI, salto_giornaliero  # noqa: E402
from entry_long import TRIGGER_LONG, entry_jump_momentum_up, registra_trigger_long  # noqa: E402
from entry_short import (TRIGGER_SHORT, entry_short_jump_momentum_down,  # noqa: E402
                         registra_trigger_short)
from test_algoxplorer import _leggi                                 # noqa: E402

NY = "America/New_York"
ENTRY_NUOVE = {"E40_JUMP_MOMENTUM_UP": entry_jump_momentum_up,
               "E40_SHORT_JUMP_MOMENTUM_DOWN": entry_short_jump_momentum_down}


def _mercato_24_7(inizio="2023-01-01", fine="2024-10-01", seme=3, freq="15min") -> pd.DataFrame:
    idx = pd.date_range(inizio, fine, freq=freq, tz="UTC", inclusive="left")
    rng = np.random.default_rng(seme)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, len(idx))))
    op = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"Open": op, "High": np.maximum(op, close) * 1.001, "Low": np.minimum(op, close) * 0.999,
                         "Close": close, "Volume": 100.0}, index=idx)


def _con_colonna(df: pd.DataFrame, **kw) -> pd.DataFrame:
    d = df.copy()
    d["salto"] = salto_giornaliero(d, **kw)["salto"]
    return d


def _riferimento(df: pd.DataFrame, giornate=250, percentili=(0.10, 0.90)) -> pd.Series:
    """Riscrittura indipendente, candela per candela: +1/-1 sul primo salto della giornata, 0 altrove."""
    passo = df.index[1] - df.index[0]
    fine = (df.index + passo).tz_convert(NY)
    close = df["Close"].to_numpy()
    esito = pd.Series(np.nan, index=df.index)
    chiusure, rendimenti, fatto, pronto = [], [], False, False
    for i, t in enumerate(fine):
        m = t.hour * 60 + t.minute
        if pronto:
            esito.iloc[i] = 0.0
        if m == 17 * 60:
            chiusure.append(close[i])
            if len(chiusure) >= 2:
                rendimenti.append(chiusure[-1] / chiusure[-2] - 1)
            fatto = False
            if len(rendimenti) >= giornate:
                pronto = True
            continue
        if m % 30 or not chiusure or len(rendimenti) < giornate or fatto:
            continue
        lo, hi = np.quantile(rendimenti[-giornate:], percentili)
        r = close[i] / chiusure[-1] - 1
        if r > hi:
            esito.iloc[i], fatto = 1.0, True
        elif r < lo:
            esito.iloc[i], fatto = -1.0, True
    return esito


def _eventi(s: pd.Series) -> pd.Series:
    return s[s.fillna(0) != 0]


def _ore(index) -> set:
    return set(pd.DatetimeIndex(index).tz_convert(NY).strftime("%H:%M"))


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
    ec, ef = _eventi(dc["salto"]), _eventi(df_["salto"])
    check("A1. 24/7: stessi salti, stesse candele, stesso verso", ec.equals(_eventi(rc)), f"{len(ec)} salti")
    check("A2. forex: stessi salti, stesse candele, stesso verso", ef.equals(_eventi(rf)) and len(ef) > 50,
          f"{len(ef)} salti")
    check("A3. 24/7 e forex: NaN e zeri dove li mette la riscrittura",
          dc["salto"].isna().equals(rc.isna()) and df_["salto"].isna().equals(rf.isna()))

    # =====================================================================
    print("\nB · LE DUE ENTRY\n" + "-" * 70)
    su, giu = entry_jump_momentum_up(dc), entry_short_jump_momentum_down(dc)
    check("B1. long dove salto = +1, short dove -1, mai insieme",
          su.equals(dc["salto"] == 1) and giu.equals(dc["salto"] == -1) and not (su & giu).any())
    fine = (dc.index + pd.Timedelta(minutes=15)).tz_convert(NY)
    giorno = pd.Series(np.cumsum(fine.strftime("%H:%M") == "17:00"), index=dc.index)
    tutte = su | giu
    check("B2. al massimo un salto per giornata (fra long e short)", giorno[tutte].is_unique)
    ore_fine = set((dc.index[tutte] + pd.Timedelta(minutes=15)).tz_convert(NY).strftime("%M"))
    check("B3. solo sulle candele che finiscono alle :00 o alle :30, mai su quella delle 17:00",
          ore_fine <= {"00", "30"} and "16:45" not in _ore(dc.index[tutte]))
    check("B4. ci sono salti in tutti e due i versi", su.sum() > 30 and giu.sum() > 30, f"{su.sum()} su, {giu.sum()} giu'")

    # =====================================================================
    print("\nC · LE SOGLIE\n" + "-" * 70)
    t = ec.index[5]
    fine_t = (t + pd.Timedelta(minutes=15)).tz_convert(NY)
    chiusure = crypto["Close"][(crypto.index + pd.Timedelta(minutes=15)).tz_convert(NY).strftime("%H:%M") == "17:00"]
    prima = chiusure[chiusure.index < t]
    rend = (prima / prima.shift(1) - 1).dropna().to_numpy()[-250:]
    lo, hi = np.quantile(rend, [0.1, 0.9])
    r = crypto.loc[t, "Close"] / prima.iloc[-1] - 1
    atteso = 1.0 if r > hi else (-1.0 if r < lo else 0.0)
    check("C1. un caso a mano: rendimento dalla chiusura di ieri contro i percentili delle 250 giornate chiuse",
          dc.loc[t, "salto"] == atteso != 0, f"{fine_t:%d/%m %H:%M} NY, r = {r:+.4f}, soglie {lo:+.4f} / {hi:+.4f}")
    larghe = _con_colonna(crypto, percentili=(0.02, 0.98))
    check("C2. con soglie piu' larghe (2° e 98°) i salti sono di meno",
          len(_eventi(larghe["salto"])) < len(ec))

    # =====================================================================
    print("\nD · IL RISCALDAMENTO\n" + "-" * 70)
    n_chiusure = int((fine.strftime("%H:%M") == "17:00").sum())
    pronte = dc["salto"].notna()
    giorno_pronto = giorno[pronte].min()
    check("D1. NaN finche' non ci sono 250 rendimenti giornalieri (251 chiusure), poi 0 o +-1",
          giorno_pronto == 251 and dc["salto"][pronte].isin([0.0, 1.0, -1.0]).all() and n_chiusure > 300,
          f"prima giornata pronta: {giorno_pronto}")
    corto = crypto.iloc[: 200 * 96]
    check("D2. meno di 250 giornate: colonna tutta NaN senza errore", salto_giornaliero(corto)["salto"].isna().all())

    # =====================================================================
    print("\nE · IL FOREX\n" + "-" * 70)
    lun = ef[ef.index.tz_convert(NY).dayofweek == 0]
    t = lun.index[0]
    ch_fx = forex["Close"][(forex.index + pd.Timedelta(minutes=15)).tz_convert(NY).strftime("%H:%M") == "17:00"]
    ultima = ch_fx[ch_fx.index < t]
    check("E1. un salto del lunedi' misura il rendimento dalla chiusura del venerdi'",
          ultima.index[-1].tz_convert(NY).dayofweek == 4 and len(lun) > 3)

    # =====================================================================
    print("\nF · I TIMEFRAME\n" + "-" * 70)
    for passo in (5, 30):
        x = _mercato_24_7(freq=f"{passo}min", seme=11)
        m = _con_colonna(x)
        check(f"F1. candele da {passo} minuti: identica alla riscrittura",
              _eventi(m["salto"]).equals(_eventi(_riferimento(x))) and len(_eventi(m["salto"])) > 30)
    for regola in ("1h", "4h"):
        grosse = crypto.resample(regola).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last",
                                               "Volume": "sum"})
        check(f"F2. {regola.upper()}: colonna vuota senza errore", salto_giornaliero(grosse)["salto"].isna().all())

    # =====================================================================
    print("\nG · IL BACKTEST CON X_ORA_@17:00\n" + "-" * 70)
    R.clear_registry()
    co.imposta_fuso(NY)
    for k, f in ENTRY_NUOVE.items():
        R.register_entry(k, -1 if "SHORT" in k else 1)(f)
    co.registra_uscita_oraria("X_ORA_@17:00")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        es = run_exit_search_bt(dc, entry_cols_long=["E40_JUMP_MOMENTUM_UP"],
                                entry_cols_short=["E40_SHORT_JUMP_MOMENTUM_DOWN"], n_barre=200,
                                exit_rule_pairs=["X_ORA_@17:00"], perc_sl=0, perc_tp=0, spread=0.0, commission=0.0,
                                cash=1_000_000, pip_size=0.01, verbose=False, min_trades=1, quarantena=False)
    tr = es.trades(es.risultati["combinazione"].iloc[0])
    entrate = pd.DatetimeIndex(tr["EntryTime"])
    attese = pd.DatetimeIndex(ec.index + pd.Timedelta(minutes=15))
    check("G1. ogni trade si apre all'ora del controllo che ha rivelato il salto e si chiude alle 17:00 di New York",
          _ore(tr["ExitTime"]) == {"17:00"} and set(entrate) <= set(attese) and len(tr) > 30,
          f"{len(tr)} trade")
    R.clear_registry()

    # =====================================================================
    print("\nH · LOOKAHEAD PER TRONCAMENTO\n" + "-" * 70)

    def _prepara(d: pd.DataFrame) -> pd.DataFrame:
        d = _con_colonna(d, giornate=100)
        # trappola: la soglia del 90° percentile calcolata su TUTTO il campione (come nel paper)
        passo = d.index[1] - d.index[0]
        fine_d = (d.index + passo).tz_convert(NY)
        e17 = fine_d.strftime("%H:%M") == "17:00"
        c17 = pd.Series(np.where(e17, d["Close"], np.nan), index=d.index)
        rend = c17.dropna().pct_change().dropna()
        soglia = rend.quantile(0.9) if len(rend) else np.nan
        ieri = c17.ffill().shift(1).where(~pd.Series(e17, index=d.index))
        d["t_tutto"] = ((d["Close"] / ieri - 1) > soglia).astype(float)
        return d

    R.clear_registry()
    for k, f in ENTRY_NUOVE.items():
        R.register_entry(k, -1 if "SHORT" in k else 1)(f)
    R.register_entry("T_TUTTO", 1)(lambda d: d["t_tutto"] > 0)
    insiemi = [("24/7 sintetico", crypto.tail(150 * 96)), ("forex sintetico", forex.tail(150 * 96))]
    btc = _leggi("BTCUSD")
    if btc is not None:
        insiemi.append(("BTCUSD vero, ultime 15000 barre", btc.tail(15000)))
    for nome, dati in insiemi:
        with contextlib.redirect_stdout(io.StringIO()):
            rep = verifica_lookahead(dati, prepara=_prepara, tagli_per_condizione=8, riscaldamento=300,
                                     verbose=False).set_index("nome")
        check(f"H1. {nome}: la trappola (percentile su tutto il campione) e' segnata LOOKAHEAD",
              rep.loc["T_TUTTO", "esito"] == "LOOKAHEAD")
        esiti = {k: rep.loc[k, "esito"] for k in list(ENTRY_NUOVE) + ["salto"]}
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
        su, giu = int(entry_jump_momentum_up(d).sum()), int(entry_short_jump_momentum_down(d).sum())
        ev = d.index[(d["salto"].fillna(0) != 0).to_numpy()]
        minuti = set((ev + pd.Timedelta(minutes=15)).tz_convert(NY).strftime("%M"))
        righe.append({"symbol": sym, "E40 L": su, "E40 S": giu})
        ok_tutti &= su >= 100 and giu >= 100 and minuti <= {"00", "30"}
    if righe:
        print(pd.DataFrame(righe).set_index("symbol").to_string())
        check("I1. su ogni symbol presente: almeno 100 eventi per lato, solo sui controlli di mezz'ora",
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
    check("J1. E40 nei dizionari dei trigger, con le funzioni giuste e la direzione giusta",
          all((TRIGGER_SHORT if "SHORT" in k else TRIGGER_LONG).get(k) is f for k, f in ENTRY_NUOVE.items())
          and all(R.get_entry_direction(k) == (-1 if "SHORT" in k else 1) for k in ENTRY_NUOVE))
    check("J2. la colonna nuova e' nell'elenco che il collaudo verifica", "salto" in COLONNE_INDICATORI)
    R.clear_registry()

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(main())
