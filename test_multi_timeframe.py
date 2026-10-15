"""
Collaudo delle condizioni multi timeframe (docs/50 §10, riga 12; schede
approvate da Mattia il 15/10/2026):

    engine/indicatori.py   id_periodo, barre_superiori, al_periodo_chiuso,
                           colonne_multi_timeframe (ftfc, mtf_h4_macdh_pend,
                           mtf_h1_force, mtf_h1_high, mtf_h1_low, tsmom, inside_day)
    F37_FTFC_UP / F37_FTFC_DOWN            coppia "FTFC"
    E31_TRIPLE_SCREEN_UP / E31_SHORT_TRIPLE_SCREEN_DOWN   setup di Elder
    F38_TSMOM_ALL_UP / F38_TSMOM_ALL_DOWN  coppia "TSMOM"
    F39_INSIDE_DAY                         neutro

Sezioni (docs/50 §7):

    A  le colonne contro una riscrittura indipendente (cicli espliciti)
    B  casi a risultato noto: confini dei periodi (H4 alle 17 NY con l'ora
       legale, settimana dalla domenica 17 NY), solo candele chiuse,
       quarantena ignorata, specchio long/short, giorno inside costruito a mano
    C  lookahead per troncamento (verifica_lookahead) con una trappola che usa
       la candela H1 in corso e deve risultare LOOKAHEAD; tagli a meta' ora
    D  riscaldamento: stesse condizioni da qualunque punto partano i dati
    E  i 9 symbol di dati/ (solo conteggi) e verifica_degenerazione su EURUSD
    F  registrazione nel motore e righe di aggiungi_indicatori invariate

Si lancia da terminale, dalla cartella del progetto:

    python test_multi_timeframe.py

(su Windows: PYTHONIOENCODING=utf-8). Le prove sui dati veri girano solo se
ci sono i file di dati/; se mancano vengono SALTATE e lo dice. Non serve MT5.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import os
import sys
import warnings

import numpy as np
import pandas as pd
import talib

warnings.simplefilter(action="ignore", category=FutureWarning)

from engine import registry as R
from engine.broker_tz_diagnostic import to_utc_index
from engine.collaudo_catalogo import mercato_sintetico, verifica_degenerazione, verifica_lookahead
from engine.indicatori import (COLONNE_INDICATORI, COLONNE_MULTI_TIMEFRAME, aggiungi_indicatori,
                               barre_superiori, colonne_multi_timeframe, id_periodo)
from engine.livelli import giorno_fx, svuota_cache
from engine.quarantena import quarantena
from entry_long import TRIGGER_LONG, entry_triple_screen_up, registra_trigger_long
from entry_short import TRIGGER_SHORT, entry_short_triple_screen_down, registra_trigger_short
from filter_conditions import (FILTRI, filter_ftfc_down, filter_ftfc_up, filter_inside_day,
                               filter_tsmom_all_down, filter_tsmom_all_up, registra_filtri)

CARTELLA = os.path.dirname(os.path.abspath(__file__))
DATI = os.path.join(CARTELLA, "dati")
SYMBOL = ("EURUSD", "GBPUSD", "USDJPY", "NZDUSD", "BTCUSD", "US500", "USTEC", "XAUUSD", "DE40")
FILTRI_NUOVI = {"F37_FTFC_UP": (filter_ftfc_up, 1, "FTFC"), "F37_FTFC_DOWN": (filter_ftfc_down, -1, "FTFC"),
                "F38_TSMOM_ALL_UP": (filter_tsmom_all_up, 1, "TSMOM"),
                "F38_TSMOM_ALL_DOWN": (filter_tsmom_all_down, -1, "TSMOM"),
                "F39_INSIDE_DAY": (filter_inside_day, 0, None)}
SPENTI = ("F37_FTFC_UP", "F37_FTFC_DOWN", "F38_TSMOM_ALL_UP", "F38_TSMOM_ALL_DOWN")   # doppioni, docs/50 §10 quater
ENTRY_NUOVE = {"E31_TRIPLE_SCREEN_UP": entry_triple_screen_up,
               "E31_SHORT_TRIPLE_SCREEN_DOWN": entry_short_triple_screen_down}
COLONNE = COLONNE_MULTI_TIMEFRAME


def _leggi(symbol: str) -> pd.DataFrame | None:
    percorso = os.path.join(DATI, f"{symbol}_M15.csv")
    if not os.path.exists(percorso):
        return None
    df = pd.read_csv(percorso, parse_dates=["Date"], index_col="Date")
    df = to_utc_index(df, "A_US_DST (NY+7h)", on_dst_gap="drop", verbose=False)
    return df[["Open", "High", "Low", "Close", "Volume"]]


def _crypto_sintetico(giorni: int = 200, seme: int = 7, prezzo: float = 30000.0) -> pd.DataFrame:
    """Random walk M15 aperto 7 giorni su 7, con la pausa del venerdi' 17:00-18:00 NY come BTCUSD."""
    idx = pd.date_range("2022-01-03", periods=giorni * 96, freq="15min", tz="UTC")
    ny = idx.tz_convert("America/New_York")
    idx = idx[~((ny.dayofweek == 4) & (ny.hour == 17))]
    rng = np.random.default_rng(seme)
    n = len(idx)
    close = prezzo * np.exp(np.cumsum(rng.normal(0, 0.003, n)))
    op = np.r_[close[0], close[:-1]] * np.exp(rng.normal(0, 0.0005, n))
    return pd.DataFrame({"Open": op, "High": np.maximum(op, close) * 1.001,
                         "Low": np.minimum(op, close) * 0.999, "Close": close,
                         "Volume": rng.integers(100, 5000, n).astype(float)}, index=idx)


# ------------------------------------------------ riscrittura indipendente --
def _chiave_rif(ts: pd.Timestamp, regola: str):
    if regola == "H1":
        return ts.floor("h")
    fx = ts.tz_convert("America/New_York").tz_localize(None) + dt.timedelta(hours=7)
    d = fx.date()
    return {"H4": (d, fx.hour // 4), "D": d, "W": d - dt.timedelta(days=d.weekday()),
            "M": (d.year, d.month)}[regola]


def _riferimento(df: pd.DataFrame) -> pd.DataFrame:
    """Tutte le colonne, a cicli espliciti: periodi per chiave di calendario, candele, letture."""
    q = quarantena(df, verbose=False)["totale"].to_numpy()
    o, h, l, c, v = (df[k].to_numpy(dtype=float) for k in ("Open", "High", "Low", "Close", "Volume"))
    n = len(df)
    pid, candele = {}, {}
    for r in ("H1", "H4", "D", "W", "M"):
        ids, k, prec = np.zeros(n, dtype=int), -1, None
        for i, ts in enumerate(df.index):
            ch = _chiave_rif(ts, r)
            if ch != prec:
                k += 1
                prec = ch
            ids[i] = k
        pid[r] = ids
        tab = {}
        for i in range(n):
            if q[i]:
                continue
            p = ids[i]
            if p not in tab:
                tab[p] = [o[i], h[i], l[i], c[i], v[i]]
            else:
                t = tab[p]
                t[1], t[2], t[3], t[4] = max(t[1], h[i]), min(t[2], l[i]), c[i], t[4] + v[i]
        candele[r] = tab
    esito = {nome: np.full(n, np.nan) for nome in COLONNE}
    # ftfc: apertura della prima barra utile del periodo, nota da quella barra in poi
    aperture = {r: np.full(n, np.nan) for r in ("H1", "D", "W", "M")}
    for r in aperture:
        nota, prec = np.nan, -1
        for i in range(n):
            if pid[r][i] != prec:
                nota, prec = np.nan, pid[r][i]
            if np.isnan(nota) and not q[i]:
                nota = o[i]
            aperture[r][i] = nota
    for i in range(n):
        ap = [aperture[r][i] for r in aperture]
        if not any(np.isnan(ap)):
            esito["ftfc"][i] = 1.0 if all(c[i] > a for a in ap) else (-1.0 if all(c[i] < a for a in ap) else 0.0)
    # H4: MACD-Histogram (talib) sulle chiusure dei periodi con dati, pendenza
    p4 = sorted(candele["H4"])
    pend4 = {}
    if len(p4) > 34:
        _, _, ist = talib.MACD(np.array([candele["H4"][p][3] for p in p4]), 12, 26, 9)
        for j in range(1, len(p4)):
            pend4[p4[j]] = np.sign(ist[j] - ist[j - 1])
    # H1: Force Index con EMA a 2 scritta a mano (alfa 2/3, parte dal primo valore)
    p1 = sorted(candele["H1"])
    forza, ema = {}, None
    for j in range(1, len(p1)):
        grezza = (candele["H1"][p1[j]][3] - candele["H1"][p1[j - 1]][3]) * candele["H1"][p1[j]][4]
        ema = grezza if ema is None else ema + 2.0 / 3.0 * (grezza - ema)
        forza[p1[j]] = ema
    # giornate: rendimenti a 1, 5, 21 e giorno inside
    pd_ = sorted(candele["D"])
    ts_g, dentro = {}, {}
    for j, p in enumerate(pd_):
        if j >= 21:
            segni = [np.sign(candele["D"][p][3] / candele["D"][pd_[j - k]][3] - 1.0) for k in (1, 5, 21)]
            ts_g[p] = 1.0 if all(s > 0 for s in segni) else (-1.0 if all(s < 0 for s in segni) else 0.0)
        if j >= 1:
            a, b = candele["D"][p], candele["D"][pd_[j - 1]]
            dentro[p] = 1.0 if (a[1] <= b[1] and a[2] >= b[2]) else 0.0
    for i in range(n):
        prima = pid["H4"][i] - 1
        esito["mtf_h4_macdh_pend"][i] = pend4.get(prima, np.nan)
        prima = pid["H1"][i] - 1
        esito["mtf_h1_force"][i] = forza.get(prima, np.nan)
        if prima in candele["H1"]:
            esito["mtf_h1_high"][i], esito["mtf_h1_low"][i] = candele["H1"][prima][1], candele["H1"][prima][2]
        prima = pid["D"][i] - 1
        esito["tsmom"][i] = ts_g.get(prima, np.nan)
        esito["inside_day"][i] = dentro.get(prima, np.nan)
    return pd.DataFrame(esito, index=df.index)


def _uguali(a, b, tol: float = 1e-9) -> bool:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    scala = np.maximum(1.0, np.abs(b))
    return a.shape == b.shape and bool(np.all((np.isnan(a) & np.isnan(b)) | (np.abs(a - b) <= tol * scala)))


def _con_colonne(df: pd.DataFrame) -> pd.DataFrame:
    m = colonne_multi_timeframe(df)
    return df.assign(**{c: m[c] for c in COLONNE})


def _trappola_h1_in_corso(df: pd.DataFrame) -> pd.Series:
    """punto medio dell'ora IN CORSO (manca lo spostamento di un periodo): guarda dentro l'ora"""
    h1, pid = barre_superiori(df, "H1")
    return pd.Series(((h1["High"] + h1["Low"]) / 2).to_numpy()[pid], index=df.index)


def _prepara(df: pd.DataFrame) -> pd.DataFrame:
    """Solo le colonne multi timeframe (e la trappola): aggiungi_indicatori intero e' troppo lento qui."""
    d = _con_colonne(df.copy())
    d["t_h1_high_in_corso"] = _trappola_h1_in_corso(d)
    return d


def _specchio(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"Open": -df["Open"], "High": -df["Low"], "Low": -df["High"],
                         "Close": -df["Close"], "Volume": df["Volume"]}, index=df.index)


def main() -> int:
    ESITI: list[bool] = []

    def check(nome: str, condizione: bool, dettaglio: str = ""):
        ESITI.append(bool(condizione))
        stato = "OK  " if condizione else "FAIL"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def saltato(nome: str, motivo: str):
        print(f"  [SALT] {nome}  — {motivo}")

    reali = {s: _leggi(s) for s in SYMBOL}
    forex = mercato_sintetico("2024-01-01", "2024-07-01", seme=4)       # comprende il cambio d'ora di marzo
    crypto = _crypto_sintetico(200)

    # =====================================================================
    print("\nA · LE COLONNE CONTRO UNA RISCRITTURA INDIPENDENTE\n" + "-" * 70)
    insiemi_a = [("forex sintetico", forex), ("crypto sintetico", crypto)]
    if reali["EURUSD"] is not None:
        insiemi_a.append(("EURUSD vero, ultime 12000 barre", reali["EURUSD"].tail(12000)))
    else:
        saltato("A. EURUSD vero", "manca il file di dati")
    for nome, dati in insiemi_a:
        svuota_cache()
        mio = colonne_multi_timeframe(dati)
        rif = _riferimento(dati)
        diverse = [c for c in COLONNE if not _uguali(mio[c], rif[c])]
        check(f"A1. {nome}: le 7 colonne coincidono con la riscrittura a cicli", not diverse,
              f"diverse: {diverse}" if diverse else f"{len(dati)} barre")
        piene = {c: int(mio[c].notna().sum()) for c in COLONNE}
        check(f"A2. {nome}: tutte le colonne hanno valori (non sono NaN da cima a fondo)",
              all(v > 0 for v in piene.values()), str(piene))

    # =====================================================================
    print("\nB · CASI A RISULTATO NOTO\n" + "-" * 70)
    svuota_cache()
    idx = forex.index
    ny = idx.tz_convert("America/New_York")
    p4 = id_periodo(forex, "H4")
    inizi = np.r_[False, p4[1:] != p4[:-1]]           # la prima barra dei dati non e' un inizio vero
    ore = sorted(set(ny[inizi].hour))
    check("B1. le H4 iniziano alle 17, 21, 01, 05, 09, 13 di New York (anche dopo il cambio d'ora)",
          set(ore) <= {17, 21, 1, 5, 9, 13} and len(ore) == 6, f"ore d'inizio {ore}")
    utc_inverno = sorted(set(idx[inizi & (idx < "2024-03-01")].hour))
    utc_estate = sorted(set(idx[inizi & (idx > "2024-04-01")].hour))
    check("B2. ... e in UTC si spostano di un'ora fra inverno e estate (ancorate a New York, non a UTC)",
          utc_inverno != utc_estate, f"inverno {utc_inverno}, estate {utc_estate}")
    check("B3. la giornata D coincide con giorno_fx", bool((id_periodo(forex, "D") == giorno_fx(forex).to_numpy()).all()))
    pw = id_periodo(forex, "W")
    iw = np.flatnonzero(np.r_[True, pw[1:] != pw[:-1]])[1:]
    check("B4. ogni settimana FX inizia domenica alle 17:00 di New York",
          bool(((ny[iw].dayofweek == 6) & (ny[iw].hour == 17) & (ny[iw].minute == 0)).all()), f"{len(iw)} settimane")
    pm = id_periodo(forex, "M")
    im = np.flatnonzero(np.r_[True, pm[1:] != pm[:-1]])[1:]
    fx = ny[im] + pd.Timedelta(hours=7)
    check("B5. ogni mese inizia sul primo giorno FX del mese", bool((fx.day <= 3).all()), f"giorni {sorted(set(fx.day))}")
    m = colonne_multi_timeframe(forex)
    p1 = id_periodo(forex, "H1")
    pdg = id_periodo(forex, "D")
    fermo = True
    for colonna, pp in (("mtf_h1_high", p1), ("mtf_h1_force", p1), ("mtf_h4_macdh_pend", p4),
                        ("tsmom", pdg), ("inside_day", pdg)):
        s = m[colonna].to_numpy()
        stesso = pp[1:] == pp[:-1]
        cambia = ~((s[1:] == s[:-1]) | (np.isnan(s[1:]) & np.isnan(s[:-1])))
        fermo &= not bool((cambia & stesso).any())
    check("B6. le letture delle candele chiuse restano ferme dentro il periodo (cambiano solo alla sua prima barra)", fermo)
    # quarantena: sporcare le barre in quarantena non cambia le candele
    q = quarantena(forex, verbose=False)["totale"].to_numpy()
    sporco = forex.copy()
    rng = np.random.default_rng(1)
    for k in ("Open", "High", "Low", "Close"):
        sporco.loc[q, k] = sporco.loc[q, k] * (1 + rng.normal(0, 0.05, q.sum()))
    sporco.loc[q, "High"] = sporco.loc[q, ["Open", "High", "Low", "Close"]].max(axis=1) * 1.01
    sporco.loc[q, "Low"] = sporco.loc[q, ["Open", "High", "Low", "Close"]].min(axis=1) * 0.99
    sporco.loc[q, "Volume"] = 99999.0
    svuota_cache()
    ms = colonne_multi_timeframe(sporco)
    leggono_candele = [c for c in COLONNE if c != "ftfc"]
    check(f"B7. barre in quarantena sporcate ({int(q.sum())}): le candele superiori non cambiano",
          all(_uguali(ms[c], m[c]) for c in leggono_candele))
    check("B8. ... e l'apertura dei periodi (ftfc) cambia solo sulle barre in quarantena stesse",
          _uguali(ms["ftfc"].to_numpy()[~q], m["ftfc"].to_numpy()[~q]))
    # specchio: prezzi rovesciati -> long e short si scambiano
    svuota_cache()
    base = _con_colonne(forex)
    svuota_cache()
    spec = _con_colonne(_specchio(forex))
    check("B9. specchio dei prezzi: E31 long diventa E31 short e viceversa",
          entry_triple_screen_up(base).equals(entry_short_triple_screen_down(spec))
          and entry_short_triple_screen_down(base).equals(entry_triple_screen_up(spec)),
          f"{int(entry_triple_screen_up(base).sum())} long, {int(entry_short_triple_screen_down(base).sum())} short")
    check("B10. specchio dei prezzi: F37 su e giu' si scambiano, F39 non cambia",
          filter_ftfc_up(base).equals(filter_ftfc_down(spec)) and filter_inside_day(base).equals(filter_inside_day(spec)))
    inverso = forex.assign(Open=1 / forex["Open"], High=1 / forex["Low"], Low=1 / forex["High"], Close=1 / forex["Close"])
    svuota_cache()
    inv = _con_colonne(inverso)
    check("B11. prezzo inverso (1/p): F38 su e giu' si scambiano",
          filter_tsmom_all_up(base).equals(filter_tsmom_all_down(inv)) and filter_tsmom_all_down(base).equals(filter_tsmom_all_up(inv)),
          f"{int(filter_tsmom_all_up(base).sum())} barre su, {int(filter_tsmom_all_down(base).sum())} giu'")
    # E31: ogni evento rispetta i tre schermi e la barra prima no
    ev = entry_triple_screen_up(base)
    tre = (base["mtf_h4_macdh_pend"] > 0) & (base["mtf_h1_force"] < 0) & (base["Close"] > base["mtf_h1_high"])
    check("B12. E31 long: sulle barre del segnale valgono i tre schermi, sulla barra prima no (evento)",
          bool(ev.sum() > 0 and tre[ev].all() and not tre.shift(1, fill_value=False)[ev].any()), f"{int(ev.sum())} eventi")
    # giorno inside costruito a mano: la giornata 3 sta dentro la 2
    giorni = sorted(set(pdg))
    gg = forex.copy()
    sel = {g: np.flatnonzero(pdg == g) for g in giorni[1:5]}
    centro = float(gg["Close"].iloc[sel[giorni[2]]].mean())
    for g, ampiezza in ((giorni[1], 0.010), (giorni[2], 0.020), (giorni[3], 0.005), (giorni[4], 0.030)):
        pos = sel[g]
        gg.iloc[pos, gg.columns.get_loc("Open")] = centro
        gg.iloc[pos, gg.columns.get_loc("Close")] = centro
        gg.iloc[pos, gg.columns.get_loc("High")] = centro + ampiezza
        gg.iloc[pos, gg.columns.get_loc("Low")] = centro - ampiezza
    svuota_cache()
    ins = colonne_multi_timeframe(gg)["inside_day"]
    letto = {g: set(ins.to_numpy()[pdg == g + 1]) for g in giorni[2:5]}
    check("B13. giornate costruite a mano: inside solo la giornata stretta dopo una larga, letto il giorno dopo",
          letto[giorni[2]] == {0.0} and letto[giorni[3]] == {1.0} and letto[giorni[4]] == {0.0}, str(letto))

    # =====================================================================
    print("\nC · LOOKAHEAD PER TRONCAMENTO\n" + "-" * 70)
    R.clear_registry()
    for k, (f, direzione, coppia) in FILTRI_NUOVI.items():
        R.register_filter(k, direction=direzione, pair=coppia)(f)
    R.register_entry("E31_TRIPLE_SCREEN_UP", 1)(entry_triple_screen_up)
    R.register_entry("E31_SHORT_TRIPLE_SCREEN_DOWN", -1)(entry_short_triple_screen_down)
    R.register_filter("T_H1_IN_CORSO")(lambda df: df["Close"] > df["t_h1_high_in_corso"])
    insiemi_c = [("forex sintetico", forex), ("crypto sintetico", crypto)]
    if reali["EURUSD"] is not None:
        insiemi_c.append(("EURUSD vero, ultime 30000 barre", reali["EURUSD"].tail(30000)))
    for nome, dati in insiemi_c:
        svuota_cache()
        rep = verifica_lookahead(dati, prepara=_prepara, tagli_per_condizione=8, verbose=False).set_index("nome")
        check(f"C1. {nome}: la trappola (punto medio dell'ora in corso) e' segnata LOOKAHEAD",
              rep.loc["T_H1_IN_CORSO", "esito"] == "LOOKAHEAD" and rep.loc["t_h1_high_in_corso", "esito"] == "LOOKAHEAD")
        esiti = {k: rep.loc[k, "esito"] for k in list(FILTRI_NUOVI) + list(ENTRY_NUOVE) + list(COLONNE)}
        check(f"C2. {nome}: condizioni e colonne nuove OK (esercitate, nessun lookahead)",
              all(e == "OK" for e in esiti.values()), "" if all(e == "OK" for e in esiti.values()) else str(esiti))
        svuota_cache()
        intero = colonne_multi_timeframe(dati)
        rng = np.random.default_rng(3)
        diversi = 0
        for t in rng.choice(np.arange(3000, len(dati) - 1), 20, replace=False):
            svuota_cache()
            tagliato = colonne_multi_timeframe(dati.iloc[:t + 1])
            diversi += sum(0 if _uguali(tagliato[c], intero[c].iloc[:t + 1]) else 1 for c in COLONNE)
        check(f"C3. {nome}: 20 tagli a caso (anche a meta' ora e giornata), serie tagliata = serie intera",
              diversi == 0, f"{diversi} colonne diverse" if diversi else "")
    R.clear_registry()

    # =====================================================================
    print("\nD · RISCALDAMENTO: stesse condizioni da qualunque punto partano i dati\n" + "-" * 70)
    lungo = reali["EURUSD"].tail(60000) if reali["EURUSD"] is not None else mercato_sintetico("2023-01-01", "2024-07-01", seme=9)
    svuota_cache()
    intero = _con_colonne(lungo)
    condizioni = {**{k: f for k, (f, _, _) in FILTRI_NUOVI.items()}, **ENTRY_NUOVE}
    for partenza in (777, 9001):
        svuota_cache()
        parziale = _con_colonne(lungo.iloc[partenza:])
        comune = parziale.index[96 * 75:]                 # circa 75 giornate dopo la partenza
        sporche = {k: int((f(intero).loc[comune] != f(parziale).loc[comune]).sum()) for k, f in condizioni.items()}
        sporche = {k: v for k, v in sporche.items() if v}
        check(f"D. partenza alla barra {partenza}: dopo ~75 giornate condizioni identiche ({len(comune)} barre)",
              not sporche and len(comune) > 20000, str(sporche) if sporche else "")

    # =====================================================================
    print("\nE · I 9 SYMBOL DI dati/ (solo conteggi)\n" + "-" * 70)
    righe, tutte_ok = [], True
    for symbol, df in reali.items():
        if df is None:
            saltato(f"E. {symbol}", "manca il file di dati")
            continue
        svuota_cache()
        d = _con_colonne(df)
        riga = {"symbol": symbol, "barre": len(d)}
        for k, f in condizioni.items():
            s = f(d).fillna(False)
            riga[k.split("_")[0] + ("s" if "SHORT" in k or "DOWN" in k else "")] = (
                int(s.sum()) if k in ENTRY_NUOVE else round(100 * s.mean(), 1))
            tutte_ok &= bool(0 < s.sum() < len(s) * (0.6 if k not in ENTRY_NUOVE else 0.05))
        righe.append(riga)
    if righe:
        with pd.option_context("display.width", 200, "display.max_columns", 20):
            print("  (filtri: % di barre vere; E31: numero di eventi)")
            print(pd.DataFrame(righe).set_index("symbol").to_string())
        check("E1. gira su tutti i symbol presenti; nessuna condizione sempre falsa o quasi sempre vera", tutte_ok)
    if reali["EURUSD"] is not None:
        R.clear_registry()
        for k, (f, direzione, coppia) in FILTRI_NUOVI.items():
            R.register_filter(k, direction=direzione, pair=coppia)(f)
        for k, f in ENTRY_NUOVE.items():
            R.register_entry(k, -1 if "SHORT" in k else 1)(f)
        svuota_cache()
        deg = verifica_degenerazione(_con_colonne(reali["EURUSD"]), verbose=False).set_index("nome")
        nostri = deg.loc[[k for k in condizioni if k in deg.index]]
        print(nostri[["esito"]].T.to_string())
        check("E2. verifica_degenerazione su EURUSD M15: tutte OK", (nostri["esito"] == "OK").all(),
              str(nostri["esito"].to_dict()))
        R.clear_registry()

    # =====================================================================
    print("\nF · REGISTRAZIONE\n" + "-" * 70)
    R.clear_registry()
    with contextlib.redirect_stdout(io.StringIO()):
        registra_filtri()
        registra_trigger_long()
        registra_trigger_short()
    accesi = {k: v for k, v in FILTRI_NUOVI.items() if k not in SPENTI}
    check("F1. F39 e' registrato (neutro) e F37, F38 non lo sono (spenti come doppioni, 15/10/2026)",
          all(k in R.list_filters(direction=d) for k, (_, d, _) in accesi.items())
          and not any(k in R.list_filters() for k in SPENTI))
    coppie = {c[0] for c in R.list_filter_pairs()}
    check("F2. le coppie FTFC e TSMOM non arrivano alla ricerca dei filtri", not ({"FTFC", "TSMOM"} & coppie))
    check("F3. nel dizionario FILTRI: F39 con funzione e direction giuste, F37 e F38 assenti (riga commentata)",
          all(FILTRI[k] == (f, d, p) for k, (f, d, p) in accesi.items()) and not any(k in FILTRI for k in SPENTI))
    check("F4. E31 long e short nei dizionari dei trigger",
          TRIGGER_LONG.get("E31_TRIPLE_SCREEN_UP") is entry_triple_screen_up
          and TRIGGER_SHORT.get("E31_SHORT_TRIPLE_SCREEN_DOWN") is entry_short_triple_screen_down)
    check("F5. le colonne nuove sono nell'elenco che il collaudo verifica", set(COLONNE) <= set(COLONNE_INDICATORI))
    R.clear_registry()
    if reali["EURUSD"] is not None:
        import engine.indicatori as I
        pezzo = reali["EURUSD"].head(6000)
        svuota_cache()
        con = aggiungi_indicatori(pezzo)
        originale = I.colonne_multi_timeframe
        try:   # senza le colonne nuove: le righe devono essere le stesse
            I.colonne_multi_timeframe = lambda df: pd.DataFrame(0.0, index=df.index, columns=list(COLONNE))
            senza = I.aggiungi_indicatori(pezzo)
        finally:
            I.colonne_multi_timeframe = originale
        check("F6. aggiungi_indicatori: le colonne multi timeframe non tolgono righe",
              con.index.equals(senza.index) and all(c in con.columns for c in COLONNE),
              f"{len(con)} righe contro {len(senza)}")
    else:
        saltato("F6. righe di aggiungi_indicatori", "manca il file di dati")

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(main())
