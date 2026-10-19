"""
Collaudo delle coppie di ore UTC: E38 (8~22, momentum) ed E39 (12~13,
inversione) e dell'uscita X_ORA_@HH:MM_UTC (docs/50 §10, riga 17; scheda
approvata da Mattia il 19/10/2026, Wen, Bouri, Xu, Zhao 2022).

    A  le colonne ora_r8 e ora_r12 contro una riscrittura indipendente
       (ricerca dei prezzi per ora UTC), su un mercato 24/7 e su uno forex
    B  le quattro entry: segni, rendimento zero = nessun trade, una volta al
       giorno sulla candela che finisce alle 21:00 (E38) e alle 12:00 (E39)
    C  l'ora UTC e' fissa: stesso orario d'inverno e d'estate
    D  i timeframe: M5, M30 e H1 come la riscrittura; H4 colonne vuote
    E  barre mancanti: senza una delle candele quel giorno niente segnale
    F  l'uscita X_ORA_@HH:MM_UTC: nome, fuso fisso, imposta_fuso non la cambia
    G  il backtest: E38 apre alle 21:00 e chiude alle 22:00 UTC, E39 alle 12:00
       e alle 13:00, con il fuso di New York impostato; senza quarantena (dati
       da exchange) un trade al giorno; con la quarantena del broker E38 resta
       solo con l'ora solare di New York (orari del paper, non adattati)
    H  il Lab (vetrina) accetta l'uscita con _UTC
    I  lookahead per troncamento, con una trappola che guarda le 22:00 di oggi
    J  i symbol veri di dati/: conteggi e verifica_degenerazione su BTCUSD
    K  registrazione e colonne nell'elenco del collaudo

Esecuzione:  python test_ore_utc.py   (su Windows: PYTHONIOENCODING=utf-8)
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd

CARTELLA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CARTELLA)

import condizioni_orarie as co                                      # noqa: E402
from engine import registry as R                                    # noqa: E402
from engine.collaudo_catalogo import mercato_sintetico, verifica_degenerazione, verifica_lookahead  # noqa: E402
from engine.exit_search_bt import run_exit_search_bt                # noqa: E402
from engine.indicatori import COLONNE_INDICATORI, rendimenti_ore_utc  # noqa: E402
from entry_long import (TRIGGER_LONG, entry_hour_momentum_up,       # noqa: E402
                        entry_hour_reversal_up, registra_trigger_long)
from entry_short import (TRIGGER_SHORT, entry_short_hour_momentum_down,  # noqa: E402
                         entry_short_hour_reversal_down, registra_trigger_short)
from test_algoxplorer import _leggi                                 # noqa: E402

NY = "America/New_York"
ENTRY_NUOVE = {"E38_HOUR_MOMENTUM_UP": entry_hour_momentum_up,
               "E38_SHORT_HOUR_MOMENTUM_DOWN": entry_short_hour_momentum_down,
               "E39_HOUR_REVERSAL_UP": entry_hour_reversal_up,
               "E39_SHORT_HOUR_REVERSAL_DOWN": entry_short_hour_reversal_down}
COLONNE = ("ora_r8", "ora_r12")
# colonna -> (da, a, ora d'apertura del trade), riscritte qui a mano dal paper
ORE = {"ora_r8": ("07:00", "08:00", "21:00"), "ora_r12": ("11:00", "12:00", "12:00")}


def _mercato_24_7(inizio="2024-01-01", fine="2024-09-01", seme=3, freq="15min") -> pd.DataFrame:
    idx = pd.date_range(inizio, fine, freq=freq, tz="UTC", inclusive="left")
    rng = np.random.default_rng(seme)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, len(idx))))
    op = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"Open": op, "High": np.maximum(op, close) * 1.001, "Low": np.minimum(op, close) * 0.999,
                         "Close": close, "Volume": 100.0}, index=idx)


def _con_colonne(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    for k, v in rendimenti_ore_utc(d).items():
        d[k] = v
    return d


def _riferimento(df: pd.DataFrame) -> pd.DataFrame:
    """Riscrittura indipendente: per ogni giorno UTC, i prezzi cercati per ora di fine candela."""
    passo = df.index[1] - df.index[0]
    alle = {}
    for i, t in enumerate(df.index):
        f = (t + passo).tz_convert("UTC")
        alle[(f.date(), f.strftime("%H:%M"))] = i
    esito = pd.DataFrame(np.nan, index=df.index, columns=list(ORE))
    close = df["Close"].to_numpy()
    for (g, hhmm), i in alle.items():
        for col, (da, a, seg) in ORE.items():
            if hhmm == seg and (g, da) in alle and (g, a) in alle:
                esito.iloc[i, esito.columns.get_loc(col)] = close[alle[(g, a)]] / close[alle[(g, da)]] - 1
    return esito


def _uguali(a: pd.Series, b: pd.Series) -> bool:
    return bool(a.isna().equals(b.isna()) and np.allclose(a.dropna(), b.dropna(), rtol=0, atol=1e-12))


def _ore(index, fuso="UTC") -> set:
    return set(pd.DatetimeIndex(index).tz_convert(fuso).strftime("%H:%M"))


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
    check("A1. 24/7: ora_r8 identica alla riscrittura", _uguali(dc["ora_r8"], rc["ora_r8"]),
          f"{dc['ora_r8'].notna().sum()} valori")
    check("A2. 24/7: ora_r12 identica alla riscrittura", _uguali(dc["ora_r12"], rc["ora_r12"]),
          f"{dc['ora_r12'].notna().sum()} valori")
    check("A3. forex: ora_r8 e ora_r12 identiche alla riscrittura",
          _uguali(df_["ora_r8"], rf["ora_r8"]) and _uguali(df_["ora_r12"], rf["ora_r12"])
          and df_["ora_r8"].notna().sum() > 100)
    check("A4. 24/7: un valore al giorno anche il sabato e la domenica",
          dc["ora_r8"].dropna().index.dayofweek.nunique() == 7 and dc["ora_r8"].notna().sum() >= 240)
    t = dc["ora_r8"].dropna().index[10]
    g = t.normalize()
    p7 = crypto.loc[g + pd.Timedelta("06:45:00"), "Close"]
    p8 = crypto.loc[g + pd.Timedelta("07:45:00"), "Close"]
    check("A5. un caso a mano: rendimento dal Close della candela delle 06:45 a quello delle 07:45",
          abs(dc.loc[t, "ora_r8"] - (p8 / p7 - 1)) < 1e-12)

    # =====================================================================
    print("\nB · LE QUATTRO ENTRY\n" + "-" * 70)
    s = {k: f(dc) for k, f in ENTRY_NUOVE.items()}
    r8, r12 = dc["ora_r8"], dc["ora_r12"]
    check("B1. E38: long dove ora_r8 > 0, short dove < 0 (momentum), mai insieme",
          s["E38_HOUR_MOMENTUM_UP"].equals(r8 > 0) and s["E38_SHORT_HOUR_MOMENTUM_DOWN"].equals(r8 < 0)
          and not (s["E38_HOUR_MOMENTUM_UP"] & s["E38_SHORT_HOUR_MOMENTUM_DOWN"]).any())
    check("B2. E39: long dove ora_r12 < 0, short dove > 0 (inversione), mai insieme",
          s["E39_HOUR_REVERSAL_UP"].equals(r12 < 0) and s["E39_SHORT_HOUR_REVERSAL_DOWN"].equals(r12 > 0)
          and not (s["E39_HOUR_REVERSAL_UP"] & s["E39_SHORT_HOUR_REVERSAL_DOWN"]).any())
    piatto = dc.copy()
    for c in COLONNE:
        piatto.loc[piatto[c].notna(), c] = 0.0
    check("B3. rendimento zero: nessun trade, ne' long ne' short",
          not any(f(piatto).any() for f in ENTRY_NUOVE.values()))
    ok = True
    for k, v in s.items():
        attesa = "20:45" if k.startswith("E38") else "11:45"
        ok &= pd.Series(v[v].index.date).is_unique and _ore(v[v].index) == {attesa}
    check("B4. ogni entry al massimo una volta al giorno: E38 sulla candela delle 20:45 UTC, E39 delle 11:45",
          ok)

    # =====================================================================
    print("\nC · L'ORA UTC E' FISSA\n" + "-" * 70)
    t8 = dc["ora_r8"].dropna().index
    check("C1. E38 alle 20:45 UTC d'inverno e d'estate (16:45 di New York d'estate, 15:45 d'inverno)",
          _ore(t8[t8.month == 1]) == {"20:45"} and _ore(t8[t8.month == 7]) == {"20:45"}
          and _ore(t8[t8.month == 1], NY) == {"15:45"} and _ore(t8[t8.month == 7], NY) == {"16:45"})

    # =====================================================================
    print("\nD · I TIMEFRAME\n" + "-" * 70)
    for passo in (5, 30, 60):
        fine = _mercato_24_7(freq=f"{passo}min", seme=11)
        m = _con_colonne(fine)
        r = _riferimento(fine)
        check(f"D1. candele da {passo} minuti: colonne identiche alla riscrittura, segnale sulla candela che "
              f"finisce alle 21:00 e alle 12:00",
              _uguali(m["ora_r8"], r["ora_r8"]) and _uguali(m["ora_r12"], r["ora_r12"])
              and m["ora_r8"].notna().sum() > 200
              and _ore(m["ora_r8"].dropna().index + pd.Timedelta(minutes=passo)) == {"21:00"}
              and _ore(m["ora_r12"].dropna().index + pd.Timedelta(minutes=passo)) == {"12:00"})
    m60 = crypto.resample("1h", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
    a = dc["ora_r8"].dropna()
    b = _con_colonne(m60)["ora_r8"].dropna()
    a.index, b.index = a.index.date, b.index.date
    check("D2. le stesse barre in M15 e in H1 danno gli stessi rendimenti dell'ora 8",
          len(a) == len(b) and np.allclose(a.to_numpy(), b.reindex(a.index).to_numpy()))
    h4 = crypto.resample("4h").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
    m = rendimenti_ore_utc(h4)
    check("D3. H4: colonne vuote senza errore", m.isna().all().all() and len(m) == len(h4))
    senza_fuso = crypto.tz_localize(None)
    check("D4. indice senza fuso: colonne vuote senza errore", rendimenti_ore_utc(senza_fuso).isna().all().all())

    # =====================================================================
    print("\nE · BARRE MANCANTI\n" + "-" * 70)
    giorno = pd.Timestamp("2024-03-12", tz="UTC")
    for ora, col, nome in (("06:45", "ora_r8", "07:00"), ("07:45", "ora_r8", "08:00"),
                           ("20:45", "ora_r8", "21:00, la candela del segnale"),
                           ("10:45", "ora_r12", "11:00")):
        buco = crypto.drop(giorno + pd.Timedelta(f"{ora}:00"))
        m = _con_colonne(buco)
        altra = "ora_r12" if col == "ora_r8" else "ora_r8"
        check(f"E1. senza la candela che finisce alle {nome}: quel giorno niente {col}, il resto uguale",
              m[col][m.index.normalize() == giorno].isna().all()
              and m[col].notna().sum() == dc[col].notna().sum() - 1
              and m[altra].notna().sum() == dc[altra].notna().sum())

    # =====================================================================
    print("\nF · L'USCITA X_ORA_@HH:MM_UTC\n" + "-" * 70)
    R.clear_registry()
    co.imposta_fuso(NY)
    check("F1. orario_uscita legge orario e fuso",
          co.orario_uscita("X_ORA_@22:00_UTC") == ("22:00", "UTC") and co.orario_uscita("13:00_UTC") == ("13:00", "UTC")
          and co.orario_uscita("X_ORA_@16:00") == ("16:00", NY))
    coppia = co.registra_uscita_oraria("X_ORA_@22:00_UTC")
    semplice = co.registra_uscita_oraria("X_ORA_@16:00")
    check("F2. registra la coppia con il suffisso nel nome, long e short",
          coppia == "X_ORA_@22:00_UTC"
          and {"X_ORA_@22:00_UTC_LONG", "X_ORA_@22:00_UTC_SHORT"} <= set(R.list_exits()))
    co.imposta_fuso("Europe/Berlin")
    usc = R.get_exit("X_ORA_@22:00_UTC_LONG")(crypto)
    usc16 = R.get_exit(f"{semplice}_LONG")(crypto)
    check("F3. imposta_fuso non sposta l'uscita UTC (vera sulla candela delle 21:45 UTC), sposta quella senza suffisso",
          _ore(usc[usc].index) == {"21:45"} and _ore(usc16[usc16].index, "Europe/Berlin") == {"15:45"})
    try:
        co.registra_uscita_oraria("X_ORA_@22:00_CET")
        errore = False
    except ValueError:
        errore = True
    check("F4. un suffisso diverso da _UTC si ferma con errore", errore)
    co.imposta_fuso(NY)
    R.clear_registry()

    # =====================================================================
    print("\nG · IL BACKTEST CON LE USCITE UTC\n" + "-" * 70)
    def _trade(entry: str, uscita: str, quarantena: bool) -> pd.DataFrame:
        R.clear_registry()
        co.imposta_fuso(NY)
        for k, f in ENTRY_NUOVE.items():
            R.register_entry(k, -1 if "SHORT" in k else 1)(f)
        co.registra_uscita_oraria(uscita)
        lunga = [k for k in ENTRY_NUOVE if k.startswith(entry) and "SHORT" not in k]
        corta = [k for k in ENTRY_NUOVE if k.startswith(entry) and "SHORT" in k]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            es = run_exit_search_bt(dc, entry_cols_long=lunga, entry_cols_short=corta, n_barre=10,
                                    exit_rule_pairs=[uscita], perc_sl=0, perc_tp=0, spread=0.0, commission=0.0,
                                    cash=1_000_000, pip_size=0.01, verbose=False, min_trades=1,
                                    quarantena=quarantena)
        return es.trades(es.risultati["combinazione"].iloc[0])

    # senza quarantena: come saranno i dati da exchange (nessun rollover del broker)
    for entry, uscita, ore_attese in (("E38", "X_ORA_@22:00_UTC", ("21:00", "22:00")),
                                      ("E39", "X_ORA_@13:00_UTC", ("12:00", "13:00"))):
        tr = _trade(entry, uscita, quarantena=False)
        check(f"G1. {entry} con {uscita}, senza quarantena: si apre alle {ore_attese[0]} e si chiude alle "
              f"{ore_attese[1]} UTC, un trade al giorno",
              _ore(tr["EntryTime"]) == {ore_attese[0]} and _ore(tr["ExitTime"]) == {ore_attese[1]} and len(tr) >= 240,
              f"{len(tr)} trade")
    # con la quarantena del broker (16:45 -> 18:00 di New York): d'estate le 20:45 e le 21:00 UTC
    # sono le 16:45 e le 17:00 di New York, quindi E38 resta solo con l'ora solare (orari del paper,
    # decisione di Mattia: non si adattano al broker)
    tr = _trade("E38", "X_ORA_@22:00_UTC", quarantena=True)
    ingresso_ny = pd.DatetimeIndex(tr["EntryTime"]).tz_convert(NY)
    check("G2. E38 con la quarantena del broker: restano solo i giorni con l'ora solare di New York (ingresso "
          "alle 16:00 NY)", len(tr) > 50 and set(ingresso_ny.strftime("%H:%M")) == {"16:00"}, f"{len(tr)} trade")
    tr = _trade("E39", "X_ORA_@13:00_UTC", quarantena=True)
    check("G3. E39 con la quarantena del broker: nessun trade perso (12:00 UTC e' fuori dal rollover)",
          len(tr) >= 240, f"{len(tr)} trade")
    R.clear_registry()

    # =====================================================================
    print("\nH · IL LAB ACCETTA L'USCITA CON _UTC\n" + "-" * 70)
    from engine import vetrina
    R.clear_registry()
    co.imposta_fuso(NY)
    sess = SimpleNamespace(df_is=crypto, fuso=NY, H=10, pip=0.01)
    check("H1. _regola_oraria registra X_ORA_@22:00_UTC", vetrina._regola_oraria(sess, "X_ORA_@22:00_UTC") ==
          "X_ORA_@22:00_UTC" and "X_ORA_@22:00_UTC_SHORT" in R.list_exits())
    h1 = crypto.resample("1h").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
    try:
        vetrina._regola_oraria(SimpleNamespace(df_is=h1, fuso=NY, H=10, pip=0.01), "X_ORA_@22:30_UTC")
        errore = False
    except ValueError:
        errore = True
    check("H2. su H1 le 22:30 UTC non sono l'inizio di una candela: si ferma con errore", errore)
    R.clear_registry()

    # =====================================================================
    print("\nI · LOOKAHEAD PER TRONCAMENTO\n" + "-" * 70)

    def _prepara(d: pd.DataFrame) -> pd.DataFrame:
        d = _con_colonne(d)
        # trappola: sulla candela del segnale di E38 sa gia' il prezzo delle 22:00 di OGGI
        fine = (d.index + (d.index[1] - d.index[0])).tz_convert("UTC")
        alle_22 = pd.Series(np.where(fine.strftime("%H:%M") == "22:00", d["Close"], np.nan), index=d.index).bfill()
        d["t_futuro"] = np.where(d["ora_r8"].notna(), (alle_22 > d["Close"]).astype(float), np.nan)
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
        check(f"I1. {nome}: la trappola (prezzo delle 22:00 di oggi) e' segnata LOOKAHEAD",
              rep.loc["T_FUTURO", "esito"] == "LOOKAHEAD")
        esiti = {k: rep.loc[k, "esito"] for k in list(ENTRY_NUOVE) + list(COLONNE)}
        check(f"I2. {nome}: entry e colonne nuove OK (esercitate, nessun lookahead)",
              all(e == "OK" for e in esiti.values()), "" if all(e == "OK" for e in esiti.values()) else str(esiti))
    R.clear_registry()

    # =====================================================================
    print("\nJ · I SYMBOL VERI DI dati/\n" + "-" * 70)
    simboli = ["EURUSD", "GBPUSD", "USDJPY", "NZDUSD", "BTCUSD", "US500", "USTEC", "XAUUSD", "DE40"]
    righe, ok_tutti, visti = [], True, 0
    for sym in simboli:
        with contextlib.redirect_stdout(io.StringIO()):
            vero = _leggi(sym)
        if vero is None:
            saltato(f"J. {sym}", "manca il file di dati")
            continue
        visti += 1
        d = _con_colonne(vero)
        riga = {"symbol": sym}
        for k, f in ENTRY_NUOVE.items():
            n = int(f(d).sum())
            riga[k.split("_HOUR")[0] + (" S" if "SHORT" in k else " L")] = n
            ok_tutti &= n >= 100
        ok_tutti &= _ore(d["ora_r8"].dropna().index) == {"20:45"} and _ore(d["ora_r12"].dropna().index) == {"11:45"}
        righe.append(riga)
    if righe:
        print(pd.DataFrame(righe).set_index("symbol").to_string())
        check("J1. su ogni symbol presente: almeno 100 eventi per entry, sempre alle 20:45 e alle 11:45 UTC",
              ok_tutti, f"{visti} symbol")
    if btc is not None:
        R.clear_registry()
        for k, f in ENTRY_NUOVE.items():
            R.register_entry(k, -1 if "SHORT" in k else 1)(f)
        with contextlib.redirect_stdout(io.StringIO()):
            deg = verifica_degenerazione(_con_colonne(btc), verbose=False).set_index("nome")
        esiti = {k: deg.loc[k, "esito"] for k in ENTRY_NUOVE if k in deg.index}
        check("J2. verifica_degenerazione su BTCUSD M15: le quattro entry OK",
              len(esiti) == 4 and all(e == "OK" for e in esiti.values()), str(esiti))
        R.clear_registry()
    else:
        saltato("J2. verifica_degenerazione", "manca il file di dati")

    # =====================================================================
    print("\nK · REGISTRAZIONE\n" + "-" * 70)
    R.clear_registry()
    with contextlib.redirect_stdout(io.StringIO()):
        registra_trigger_long()
        registra_trigger_short()
    check("K1. E38 ed E39 nei dizionari dei trigger, con le funzioni giuste e la direzione giusta",
          all((TRIGGER_SHORT if "SHORT" in k else TRIGGER_LONG).get(k) is f for k, f in ENTRY_NUOVE.items())
          and all(R.get_entry_direction(k) == (-1 if "SHORT" in k else 1) for k in ENTRY_NUOVE))
    check("K2. le colonne nuove sono nell'elenco che il collaudo verifica", set(COLONNE) <= set(COLONNE_INDICATORI))
    R.clear_registry()

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(main())
