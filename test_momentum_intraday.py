"""
Collaudo del momentum intraday: E36 ed E37 (docs/50 §10, riga 15; scheda
approvata da Mattia il 18/10/2026, orari del paper).

    A  le colonne imm_r1 e imm_r12 contro una riscrittura indipendente
       (ricerca dei prezzi per orario di New York), su un mercato 24/7 e su
       uno forex (il lunedi' riparte dalla chiusura del venerdi')
    B  le quattro entry: segni, rendimento zero = nessun trade, una volta al
       giorno sulla candela che finisce alle 16:30
    C  l'ora legale: le 16:30 di New York tutto l'anno
    D  i timeframe: M5 e M30 danno gli stessi rendimenti di M15; H1 e H4
       colonne vuote, senza fermare nulla
    E  barre mancanti: senza la candela delle 09:30 quel giorno niente segnale
    F  il backtest: E36 con X_ORA_@17:00 apre alle 16:30 e chiude alle 17:00
    G  lookahead per troncamento, con una trappola che guarda le 17:00 di oggi
    H  i symbol veri di dati/: conteggi e verifica_degenerazione su BTCUSD
    I  registrazione e colonne nell'elenco del collaudo

Esecuzione:  python test_momentum_intraday.py   (su Windows: PYTHONIOENCODING=utf-8)
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
from engine.indicatori import COLONNE_INDICATORI, momentum_intraday  # noqa: E402
from entry_long import (TRIGGER_LONG, entry_intraday_momentum_combo_up,  # noqa: E402
                        entry_intraday_momentum_up, registra_trigger_long)
from entry_short import (TRIGGER_SHORT, entry_short_intraday_momentum_combo_down,  # noqa: E402
                         entry_short_intraday_momentum_down, registra_trigger_short)
from test_algoxplorer import _leggi                                 # noqa: E402

NY = "America/New_York"
ENTRY_NUOVE = {"E36_INTRADAY_MOMENTUM_UP": entry_intraday_momentum_up,
               "E36_SHORT_INTRADAY_MOMENTUM_DOWN": entry_short_intraday_momentum_down,
               "E37_INTRADAY_MOMENTUM_COMBO_UP": entry_intraday_momentum_combo_up,
               "E37_SHORT_INTRADAY_MOMENTUM_COMBO_DOWN": entry_short_intraday_momentum_combo_down}
COLONNE = ("imm_r1", "imm_r12")


def _mercato_24_7(inizio="2024-01-01", fine="2024-09-01", seme=3, freq="15min") -> pd.DataFrame:
    idx = pd.date_range(inizio, fine, freq=freq, tz="UTC", inclusive="left")
    rng = np.random.default_rng(seme)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, len(idx))))
    op = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"Open": op, "High": np.maximum(op, close) * 1.001, "Low": np.minimum(op, close) * 0.999,
                         "Close": close, "Volume": 100.0}, index=idx)


def _con_colonne(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    for k, v in momentum_intraday(d).items():
        d[k] = v
    return d


def _riferimento(df: pd.DataFrame) -> pd.DataFrame:
    """Riscrittura indipendente: per ogni giorno, i prezzi cercati per ora di New York (fine candela)."""
    passo = df.index[1] - df.index[0]
    fine = (df.index + passo).tz_convert(NY)          # l'istante in cui la candela finisce
    prezzo = pd.Series(df["Close"].to_numpy(), index=fine)
    giorni = sorted(set(fine.date))
    alle = {}
    for t, p in prezzo.items():
        alle[(t.date(), t.strftime("%H:%M"))] = (p, t)
    r1 = pd.Series(np.nan, index=df.index)
    r12 = pd.Series(np.nan, index=df.index)
    chiusura_prima = None                               # ultima chiusura delle 17:00 vista
    for g in giorni:
        p0930, p1600, p1630 = (alle.get((g, h)) for h in ("09:30", "16:00", "16:30"))
        if p1630 is not None:
            barra = df.index[fine.get_loc(p1630[1])]
            if p0930 is not None and chiusura_prima is not None:
                r1[barra] = p0930[0] / chiusura_prima - 1
            if p1600 is not None:
                r12[barra] = p1630[0] / p1600[0] - 1
        if (g, "17:00") in alle:
            chiusura_prima = alle[(g, "17:00")][0]
    return pd.DataFrame({"imm_r1": r1, "imm_r12": r12})


def _uguali(a: pd.Series, b: pd.Series) -> bool:
    return bool(a.isna().equals(b.isna()) and np.allclose(a.dropna(), b.dropna(), rtol=0, atol=1e-12))


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
    forex = mercato_sintetico("2024-01-01", "2024-09-01", seme=5)
    dc, df_ = _con_colonne(crypto), _con_colonne(forex)

    # =====================================================================
    print("\nA · LE COLONNE CONTRO UNA RISCRITTURA INDIPENDENTE\n" + "-" * 70)
    rc, rf = _riferimento(crypto), _riferimento(forex)
    check("A1. 24/7: imm_r1 identica alla riscrittura", _uguali(dc["imm_r1"], rc["imm_r1"]),
          f"{dc['imm_r1'].notna().sum()} valori")
    check("A2. 24/7: imm_r12 identica alla riscrittura", _uguali(dc["imm_r12"], rc["imm_r12"]))
    check("A3. forex: imm_r1 e imm_r12 identiche alla riscrittura",
          _uguali(df_["imm_r1"], rf["imm_r1"]) and _uguali(df_["imm_r12"], rf["imm_r12"]))
    lun = df_["imm_r1"].dropna()
    lun = lun[lun.index.tz_convert(NY).dayofweek == 0]
    venerdi = forex[(forex.index.tz_convert(NY).dayofweek == 4)
                    & (forex.index.tz_convert(NY).strftime("%H:%M") == "16:45")]["Close"]
    t = lun.index[3]
    atteso = forex.loc[forex.index.tz_convert(NY).normalize() == t.tz_convert(NY).normalize()]
    p0930 = atteso[atteso.index.tz_convert(NY).strftime("%H:%M") == "09:15"]["Close"].iloc[0]
    v_prima = venerdi[venerdi.index < t].iloc[-1]
    check("A4. forex, lunedi': la «prima mezz'ora» parte dalla chiusura delle 17:00 del venerdi'",
          abs(lun.iloc[3] - (p0930 / v_prima - 1)) < 1e-12 and len(lun) > 25)
    check("A5. 24/7: un valore al giorno anche il sabato e la domenica",
          dc["imm_r1"].dropna().index.tz_convert(NY).dayofweek.nunique() == 7
          and dc["imm_r1"].notna().sum() >= 240)

    # =====================================================================
    print("\nB · LE QUATTRO ENTRY\n" + "-" * 70)
    s = {k: f(dc) for k, f in ENTRY_NUOVE.items()}
    r1, r12 = dc["imm_r1"], dc["imm_r12"]
    check("B1. E36 long dove imm_r1 > 0, short dove < 0, mai insieme",
          s["E36_INTRADAY_MOMENTUM_UP"].equals((r1 > 0)) and s["E36_SHORT_INTRADAY_MOMENTUM_DOWN"].equals((r1 < 0))
          and not (s["E36_INTRADAY_MOMENTUM_UP"] & s["E36_SHORT_INTRADAY_MOMENTUM_DOWN"]).any())
    check("B2. E37 long: mattina su e penultima mezz'ora giu'; short l'opposto",
          s["E37_INTRADAY_MOMENTUM_COMBO_UP"].equals((r1 > 0) & (r12 < 0))
          and s["E37_SHORT_INTRADAY_MOMENTUM_COMBO_DOWN"].equals((r1 < 0) & (r12 > 0)))
    piatto = dc.copy()
    piatto.loc[piatto["imm_r1"].notna(), "imm_r1"] = 0.0
    check("B3. rendimento della mattina zero: nessun trade, ne' long ne' short",
          not entry_intraday_momentum_up(piatto).any() and not entry_short_intraday_momentum_down(piatto).any())
    tutte = pd.concat(s.values(), axis=1).any(axis=1)
    giorni = pd.Series(tutte[tutte].index.tz_convert(NY).date)
    check("B4. ogni entry al massimo una volta al giorno, sempre sulla candela delle 16:15 (il trade parte alle 16:30)",
          all(pd.Series(v[v].index.tz_convert(NY).date).is_unique for v in s.values())
          and _ore(tutte[tutte].index) == {"16:15"} and giorni.is_unique)

    # =====================================================================
    print("\nC · L'ORA LEGALE\n" + "-" * 70)
    t = dc["imm_r1"].dropna().index
    check("C1. segnale alle 16:15 di New York: 21:15 UTC d'inverno, 20:15 d'estate",
          bool((t[t.month == 1].hour == 21).all() and (t[t.month == 7].hour == 20).all()
               and (t[t.month == 1].minute == 15).all()))

    # =====================================================================
    print("\nD · I TIMEFRAME\n" + "-" * 70)
    for regola, passo in (("5min", 5), ("30min", 30)):
        fine = _mercato_24_7(freq=f"{passo}min", seme=11)
        m = _con_colonne(fine)
        check(f"D1. M{passo}: colonne identiche alla riscrittura, segnale sulla candela che finisce alle 16:30",
              _uguali(m["imm_r1"], _riferimento(fine)["imm_r1"]) and _uguali(m["imm_r12"], _riferimento(fine)["imm_r12"])
              and m["imm_r1"].notna().sum() > 200
              and _ore(m["imm_r1"].dropna().index + pd.Timedelta(minutes=passo)) == {"16:30"})
    # M15 ricampionato in M30: stessi rendimenti nella stessa giornata
    m30 = crypto.resample("30min", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
    a = dc["imm_r1"].dropna()
    b = _con_colonne(m30)["imm_r1"].dropna()
    a.index = a.index.tz_convert(NY).date
    b.index = b.index.tz_convert(NY).date
    check("D2. le stesse barre in M15 e in M30 danno gli stessi rendimenti della mattina",
          len(a) == len(b) and np.allclose(a.to_numpy(), b.reindex(a.index).to_numpy()))
    for regola in ("1h", "4h"):
        grosse = crypto.resample(regola).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last",
                                               "Volume": "sum"})
        m = momentum_intraday(grosse)
        check(f"D3. {regola.upper()}: le 09:30 non sono l'inizio di una candela, colonne vuote senza errore",
              m.isna().all().all() and len(m) == len(grosse))

    # =====================================================================
    print("\nE · BARRE MANCANTI\n" + "-" * 70)
    loc = crypto.index.tz_convert(NY)
    giorno = pd.Timestamp("2024-03-12").date()
    buco = crypto[~((loc.date == giorno) & (loc.strftime("%H:%M") == "09:15"))]
    m = _con_colonne(buco)
    del_giorno = m["imm_r1"][m.index.tz_convert(NY).date == giorno]
    check("E1. senza la candela delle 09:15 (prezzo delle 09:30) quel giorno non c'e' segnale",
          del_giorno.isna().all() and m["imm_r1"].notna().sum() == dc["imm_r1"].notna().sum() - 1)
    buco2 = crypto[~((loc.date == giorno) & (loc.strftime("%H:%M") == "15:45"))]
    m2 = _con_colonne(buco2)
    check("E2. senza la candela delle 15:45 (prezzo delle 16:00) manca solo imm_r12 di quel giorno",
          m2["imm_r12"][m2.index.tz_convert(NY).date == giorno].isna().all()
          and m2["imm_r1"].notna().sum() == dc["imm_r1"].notna().sum())

    # =====================================================================
    print("\nF · IL BACKTEST CON X_ORA_@17:00\n" + "-" * 70)
    R.clear_registry()
    co.imposta_fuso(NY)
    for k, f in ENTRY_NUOVE.items():
        R.register_entry(k, -1 if "SHORT" in k else 1)(f)
    co.registra_uscita_oraria("X_ORA_@17:00")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        es = run_exit_search_bt(dc, entry_cols_long=["E36_INTRADAY_MOMENTUM_UP"],
                                entry_cols_short=["E36_SHORT_INTRADAY_MOMENTUM_DOWN"], n_barre=10,
                                exit_rule_pairs=["X_ORA_@17:00"], perc_sl=0, perc_tp=0, spread=0.0, commission=0.0,
                                cash=1_000_000, pip_size=0.01, verbose=False, min_trades=1)
    tr = es.trades(es.risultati["combinazione"].iloc[0])
    check("F1. i trade si aprono alle 16:30 e si chiudono alle 17:00 di New York (l'ultima mezz'ora)",
          _ore(tr["EntryTime"]) == {"16:30"} and _ore(tr["ExitTime"]) == {"17:00"} and len(tr) > 200,
          f"{len(tr)} trade")
    R.clear_registry()

    # =====================================================================
    print("\nG · LOOKAHEAD PER TRONCAMENTO\n" + "-" * 70)

    def _prepara(d: pd.DataFrame) -> pd.DataFrame:
        d = _con_colonne(d)
        # trappola: sulla candela del segnale sa gia' il prezzo delle 17:00 di OGGI
        fine = (d.index + (d.index[1] - d.index[0])).tz_convert(NY)
        alle_17 = pd.Series(np.where(fine.strftime("%H:%M") == "17:00", d["Close"], np.nan), index=d.index).bfill()
        d["t_futuro"] = np.where(d["imm_r1"].notna(), (alle_17 > d["Close"]).astype(float), np.nan)
        return d

    R.clear_registry()
    for k, f in ENTRY_NUOVE.items():
        R.register_entry(k, -1 if "SHORT" in k else 1)(f)
    R.register_entry("T_FUTURO", 1)(lambda d: d["t_futuro"] > 0)
    insiemi = [("24/7 sintetico", crypto.tail(12000)), ("forex sintetico", forex.tail(12000))]
    btc = _leggi("BTCUSD")
    if btc is not None:
        insiemi.append(("BTCUSD vero, ultime 20000 barre", btc.tail(20000)))
    for nome, dati in insiemi:
        with contextlib.redirect_stdout(io.StringIO()):
            rep = verifica_lookahead(dati, prepara=_prepara, tagli_per_condizione=8, riscaldamento=300,
                                     verbose=False).set_index("nome")
        check(f"G1. {nome}: la trappola (prezzo delle 17:00 di oggi) e' segnata LOOKAHEAD",
              rep.loc["T_FUTURO", "esito"] == "LOOKAHEAD")
        esiti = {k: rep.loc[k, "esito"] for k in list(ENTRY_NUOVE) + list(COLONNE)}
        check(f"G2. {nome}: entry e colonne nuove OK (esercitate, nessun lookahead)",
              all(e == "OK" for e in esiti.values()), "" if all(e == "OK" for e in esiti.values()) else str(esiti))
    R.clear_registry()

    # =====================================================================
    print("\nH · I SYMBOL VERI DI dati/\n" + "-" * 70)
    simboli = ["EURUSD", "GBPUSD", "USDJPY", "NZDUSD", "BTCUSD", "US500", "USTEC", "XAUUSD", "DE40"]
    righe, ok_tutti, visti = [], True, 0
    for sym in simboli:
        with contextlib.redirect_stdout(io.StringIO()):
            vero = _leggi(sym)
        if vero is None:
            saltato(f"H. {sym}", "manca il file di dati")
            continue
        visti += 1
        d = _con_colonne(vero)
        riga = {"symbol": sym, "giorni": int(d["imm_r1"].notna().sum())}
        for k, f in ENTRY_NUOVE.items():
            n = int(f(d).sum())
            riga[k.split("_INTRADAY")[0] + (" S" if "SHORT" in k else " L")] = n
            ok_tutti &= n >= 100
        ok_tutti &= _ore(d["imm_r1"].dropna().index) == {"16:15"}
        righe.append(riga)
    if righe:
        print(pd.DataFrame(righe).set_index("symbol").to_string())
        check("H1. su ogni symbol presente: almeno 100 eventi per entry, sempre alle 16:15 di New York",
              ok_tutti, f"{visti} symbol")
    if btc is not None:
        R.clear_registry()
        for k, f in ENTRY_NUOVE.items():
            R.register_entry(k, -1 if "SHORT" in k else 1)(f)
        with contextlib.redirect_stdout(io.StringIO()):
            deg = verifica_degenerazione(_con_colonne(btc), verbose=False).set_index("nome")
        esiti = {k: deg.loc[k, "esito"] for k in ENTRY_NUOVE if k in deg.index}
        check("H2. verifica_degenerazione su BTCUSD M15: le quattro entry OK",
              len(esiti) == 4 and all(e == "OK" for e in esiti.values()), str(esiti))
        R.clear_registry()
    else:
        saltato("H2. verifica_degenerazione", "manca il file di dati")

    # =====================================================================
    print("\nI · REGISTRAZIONE\n" + "-" * 70)
    R.clear_registry()
    with contextlib.redirect_stdout(io.StringIO()):
        registra_trigger_long()
        registra_trigger_short()
    check("I1. E36 ed E37 nei dizionari dei trigger, con le funzioni giuste e la direzione giusta",
          all((TRIGGER_SHORT if "SHORT" in k else TRIGGER_LONG).get(k) is f for k, f in ENTRY_NUOVE.items())
          and all(R.get_entry_direction(k) == (-1 if "SHORT" in k else 1) for k in ENTRY_NUOVE))
    check("I2. le colonne nuove sono nell'elenco che il collaudo verifica", set(COLONNE) <= set(COLONNE_INDICATORI))
    R.clear_registry()

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(main())
