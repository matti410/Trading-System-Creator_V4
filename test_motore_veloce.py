"""
Suite di validazione del MOTORE VELOCE (21/10/2026, docs/65).

Cosa verifica
-------------
engine/motore_veloce.py deve dare GLI STESSI TRADE, al bit, di backtesting.py
0.6.6 con _StrategiaGenerica (l'oracolo), e le stesse cinque statistiche.

  A. Oracolo su configurazioni casuali: meta' su pezzi di dati veri
     (dati/BINANCE_PERP_BTCUSDT_M15.csv, se c'e'), meta' su dati costruiti
     apposta (salti forti fra le barre, barre piatte, barre larghe). A caso:
     lati, densita' dei segnali, regole d'uscita, stop e target, scadenze per
     lato, inversione, spread, commissione. Uguali al bit tutte le colonne dei
     trade (anche i tipi) e le statistiche.
  B. I casi limite di docs/65 §6, uno per uno, con il risultato scritto a mano.
  C. La sezione D di docs/21 (commissione, spread, stop non attivo sulla barra
     d'ingresso) rifatta sul motore veloce.
  D. Il capitale simulato che si esaurisce (docs/65 §3.2, l'unica differenza
     dichiarata): trade uguali fino a quel punto, poi tutti i trade per unita',
     statistiche in % NaN, avviso con la data.
  E. La scelta del motore: predefinito, nome sbagliato, numba assente.
  F. I motori del tool con motore="bt" e motore="veloce": stesse tabelle,
     stessi trade (run_exit_search_bt, run_filter_search_bt, due_meta).

Come si lancia (da terminale, dalla cartella del progetto):

    python test_motore_veloce.py            # 200 configurazioni, circa un minuto
    python test_motore_veloce.py --tante    # 2.000 configurazioni, circa 5 minuti

Alla fine stampa «RISULTATO: N/N test superati».
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import warnings

import numpy as np
import pandas as pd
import backtesting.backtesting as _libreria_bt
from backtesting import Backtest

from engine import motore_veloce as mv
from engine.exit_search_bt import _StrategiaGenerica, soglie_per_lato

warnings.simplefilter("ignore")
_libreria_bt._tqdm = lambda seq, **_: seq

DATI = os.path.join("dati", "BINANCE_PERP_BTCUSDT_M15.csv")
COLONNE = ["Size", "EntryBar", "ExitBar", "EntryPrice", "ExitPrice", "SL", "TP", "PnL",
           "Commission", "ReturnPct", "EntryTime", "ExitTime", "Duration", "Tag"]
STATS = list(mv._VOCI_STATS)
SOGLIE = ("sl_long", "tp_long", "sl_short", "tp_short")


# ------------------------------------------------------------------------
# strumenti
# ------------------------------------------------------------------------

def tabella_bt(d, run_kw, **bt_kw):
    """L'oracolo: backtesting.py con la strategia vera dell'engine."""
    return Backtest(d, _StrategiaGenerica, exclusive_orders=True, **bt_kw).run(**run_kw)


def veloce(d, run_kw, **bt_kw):
    with contextlib.redirect_stderr(io.StringIO()):
        return mv.MotoreVeloce(d, exclusive_orders=True, **bt_kw).run(**run_kw)


def stesse_colonne(a: pd.DataFrame, b: pd.DataFrame) -> list[str]:
    """Le colonne diverse fra due tabelle di trade (valori al bit e tipi)."""
    diverse = []
    if list(a.columns) != list(b.columns) or len(a) != len(b):
        return ["forma"]
    for c in a.columns:
        if a[c].dtype != b[c].dtype:
            diverse.append(f"{c} (tipo {a[c].dtype} contro {b[c].dtype})")
        elif not a[c].equals(b[c]):
            diverse.append(c)
    return diverse


def stesse_statistiche(a, b) -> list[str]:
    diverse = []
    for k in STATS:
        x, y = float(a[k]), float(b[k])
        if not ((np.isnan(x) and np.isnan(y)) or x == y):
            diverse.append(k)
    return diverse


def serie(n, prezzi, segnali=None, soglie=None, alto=None, basso=None):
    """Serie a prezzi scritti a mano: prezzi = Open; Close = Open; High/Low +-0,5."""
    idx = pd.date_range("2024-01-02 10:00", periods=n, freq="15min", tz="UTC")
    o = np.asarray(prezzi, dtype=float)
    d = pd.DataFrame({"Open": o, "High": o + 0.5, "Low": o - 0.5, "Close": o, "Volume": 1.0}, index=idx)
    if alto:
        for i, v in alto.items():
            d.iloc[i, d.columns.get_loc("High")] = v
    if basso:
        for i, v in basso.items():
            d.iloc[i, d.columns.get_loc("Low")] = v
    for c in ("L", "S", "XL", "XS"):
        d[c] = False
    for c, barre in (segnali or {}).items():
        for i in barre:
            d.iloc[i, d.columns.get_loc(c)] = True
    for c in SOGLIE:
        d[c] = np.nan if not soglie or c not in soglie else soglie[c]
    return d


KW = dict(long_col="L", short_col="S", exit_rule_long_col="XL", exit_rule_short_col="XS")


def dati_veri(rng, n):
    df = _veri()
    a = int(rng.integers(0, len(df) - n))
    return df.iloc[a:a + n].copy()


_CACHE = {}


def _veri():
    if "df" not in _CACHE:
        df = pd.read_csv(DATI, index_col=0, parse_dates=True)
        _CACHE["df"] = df[["Open", "High", "Low", "Close", "Volume"]]
    return _CACHE["df"]


def dati_finti(rng, n):
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    ritorni = rng.normal(0, 0.004, n) + np.where(rng.random(n) < 0.05, rng.normal(0, 0.03, n), 0)
    chiusura = 100 * np.exp(np.cumsum(ritorni))
    apertura = np.r_[100.0, chiusura[:-1]] * np.exp(np.where(rng.random(n) < 0.1, rng.normal(0, 0.02, n), 0))
    alto = np.maximum(apertura, chiusura) * (1 + np.abs(rng.normal(0, 0.003, n)))
    basso = np.minimum(apertura, chiusura) * (1 - np.abs(rng.normal(0, 0.003, n)))
    piatte = rng.random(n) < 0.02
    alto[piatte] = basso[piatte] = apertura[piatte] = chiusura[piatte]
    return pd.DataFrame({"Open": apertura, "High": alto, "Low": basso, "Close": chiusura,
                         "Volume": 1.0}, index=idx)


def configurazione(rng, df):
    n = len(df)
    p = lambda: float(rng.choice([0.0, 0.002, 0.02, 0.2]))
    pl, ps = p(), p()
    if pl == 0 and ps == 0:
        pl = 0.02
    nl, ns = int(rng.integers(1, 41)), int(rng.integers(1, 41))
    finestra = int(rng.choice([50, 200]))
    soglie = soglie_per_lato(df, nl, ns, finestra, float(rng.choice([0, 50, 90])),
                             float(rng.choice([0, 50, 90])), lag=1)
    d = df.copy()
    for c in SOGLIE:
        d[c] = soglie[c].to_numpy()
    seg_l, seg_s = rng.random(n) < pl, rng.random(n) < ps
    if rng.random() < 0.7:       # come i motori: niente segnale senza soglia calcolabile
        for c in SOGLIE:
            ok = np.r_[~np.isnan(d[c].to_numpy())[1:], False] if d[c].notna().any() else np.ones(n, bool)
            if c.endswith("long"):
                seg_l &= ok
            else:
                seg_s &= ok
    d["L"], d["S"] = seg_l, seg_s
    d["XL"] = rng.random(n) < float(rng.choice([0, 0, 0.01, 0.1]))
    d["XS"] = rng.random(n) < float(rng.choice([0, 0, 0.01, 0.1]))
    run_kw = dict(KW, n_barre=nl, n_barre_long=nl, n_barre_short=ns,
                  inverti_su_opposto=bool(rng.random() < 0.5))
    bt_kw = dict(cash=float(df["Close"].max()) * 1000, spread=float(rng.choice([0, 1e-4, 1e-3])),
                 commission=float(rng.choice([0, 5e-4, 7e-5])), margin=1.0)
    return d, run_kw, bt_kw


def esegui():
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        print(f"  [{'OK ' if condizione else 'KO '}] {nome}" + (f"  —  {dettaglio}" if dettaglio else ""))

    tante = "--tante" in sys.argv
    print(f"numba disponibile: {mv.DISPONIBILE} · motore predefinito: {mv.MOTORE_PREDEFINITO}")
    if not mv.DISPONIBILE:
        print("numba non installato: la suite prova solo la logica, piu' lentamente.")

    # ====================================================================
    print("\nA · Oracolo su configurazioni casuali")
    quante = 2000 if tante else 200
    rng = np.random.default_rng(65)
    ci_sono_veri = os.path.exists(DATI)
    if not ci_sono_veri:
        print(f"  ({DATI} non c'e': solo dati costruiti)")
    identiche = esaurite = esaurite_pari = n_trade = 0
    prima_diversa = ""
    for k in range(quante):
        df = dati_veri(rng, 20_000) if (k % 2 == 0 and ci_sono_veri) else dati_finti(rng, 3_000)
        d, run_kw, bt_kw = configurazione(rng, df)
        st_bt = tabella_bt(d, run_kw, **bt_kw)
        st_v = veloce(d, run_kw, **bt_kw)
        t_bt, t_v = st_bt["_trades"], st_v["_trades"]
        if st_v["_capitale_esaurito"] is not None:
            # docs/65 §3.2: prima del trade da cui il capitale e' esaurito, identici. Dopo, la
            # libreria salta gli ordini finche' il capitale non torna a bastare (se il prezzo
            # scende) e prosegue su un'altra strada: da li' i trade non si confrontano
            esaurite += 1
            j = st_v["_trade_esaurito"]
            pari = (len(t_bt) >= j
                    and all(np.array_equal(t_bt[c].iloc[:j].to_numpy(float), t_v[c].iloc[:j].to_numpy(float),
                                           equal_nan=True)
                            for c in ("Size", "EntryBar", "ExitBar", "EntryPrice", "ExitPrice", "SL", "TP",
                                      "PnL", "Commission", "ReturnPct")))
            esaurite_pari += pari
            continue
        diverse = stesse_colonne(t_bt, t_v) + stesse_statistiche(st_bt, st_v)
        n_trade += len(t_bt)
        if diverse:
            prima_diversa = prima_diversa or f"configurazione {k}: {diverse}"
        else:
            identiche += 1
    confrontate = quante - esaurite
    check(f"A1. {confrontate} configurazioni: trade e statistiche identici al bit",
          identiche == confrontate and confrontate > 0,
          f"identiche {identiche} · trade confrontati {n_trade:,}" + (f" · {prima_diversa}" if prima_diversa else ""))
    check("A2. capitale esaurito: trade identici fino a quel punto (docs/65 §3.2)",
          esaurite_pari == esaurite, f"casi {esaurite}")

    # ====================================================================
    print("\nB · Casi limite (docs/65 §6)")
    P = 100.0 + np.arange(12, dtype=float)          # Open crescenti, noti
    base = dict(cash=1e6, spread=0.0, commission=0.0, margin=1.0)

    def entrambi(d, run_kw, **kw):
        a, b = tabella_bt(d, run_kw, **kw), veloce(d, run_kw, **kw)
        return a, b, not stesse_colonne(a["_trades"], b["_trades"]) and not stesse_statistiche(a, b)

    a, b, ug = entrambi(serie(12, P, {"L": [0]}), dict(KW, n_barre=3), **base)
    check("B1. segnale sulla barra 0: ignorato", ug and len(b["_trades"]) == 0)
    a, b, ug = entrambi(serie(12, P, {"L": [11]}), dict(KW, n_barre=3), **base)
    check("B2. segnale sull'ultima barra: nessun trade", ug and len(b["_trades"]) == 0)
    # gap oltre lo stop: stop al 2% sotto l'ingresso (102 -> 99,96); la barra 4 apre a 95
    P2 = P.copy()
    P2[4] = 95.0
    a, b, ug = entrambi(serie(12, P2, {"L": [1]}, {"sl_long": 0.02}), dict(KW, n_barre=8), **base)
    t = b["_trades"]
    check("B3. gap oltre lo stop: uscita all'Open (peggio dello stop)",
          ug and len(t) == 1 and t["ExitPrice"].iloc[0] == 95.0 and t["ExitBar"].iloc[0] == 4,
          f"uscita {t['ExitPrice'].iloc[0] if len(t) else '—'}")
    P3 = P.copy()
    P3[4] = 130.0
    a, b, ug = entrambi(serie(12, P3, {"L": [1]}, {"tp_long": 0.02}), dict(KW, n_barre=8), **base)
    t = b["_trades"]
    check("B4. gap oltre il target: uscita all'Open (meglio del target)",
          ug and len(t) == 1 and t["ExitPrice"].iloc[0] == 130.0, f"uscita {t['ExitPrice'].iloc[0] if len(t) else '—'}")
    # stop e target nella stessa barra: barra 4 larga, tocca 99 e 110
    a, b, ug = entrambi(serie(12, P, {"L": [1]}, {"sl_long": 0.02, "tp_long": 0.05},
                              alto={4: 120.0}, basso={4: 90.0}), dict(KW, n_barre=8), **base)
    t = b["_trades"]
    stop = 102.0 * (1 - 0.02)
    check("B5. stop e target nella stessa barra: vince lo stop",
          ug and len(t) == 1 and t["ExitPrice"].iloc[0] == stop, f"uscita {t['ExitPrice'].iloc[0] if len(t) else '—'}")
    # barra piatta che vale esattamente lo stop
    P4 = P.copy()
    P4[5] = stop
    d = serie(12, P4, {"L": [1]}, {"sl_long": 0.02}, alto={5: stop}, basso={5: stop})
    d.iloc[5, d.columns.get_loc("Close")] = stop
    a, b, ug = entrambi(d, dict(KW, n_barre=8), **base)
    t = b["_trades"]
    check("B6. barra piatta uguale allo stop: lo stop scatta", ug and len(t) == 1 and t["ExitBar"].iloc[0] == 5)
    a, b, ug = entrambi(serie(12, P, {"L": [8]}), dict(KW, n_barre=10), **base)
    check("B7. trade aperto alla fine: escluso dai trade, dentro il rendimento",
          ug and len(b["_trades"]) == 0 and b["Return [%]"] != 0, f"Return {b['Return [%]']:.4f}%")
    a, b, ug = entrambi(serie(12, P, {"L": [2]}), dict(KW, n_barre=1), **base)
    t = b["_trades"]
    check("B8. scadenza 1: esce alla barra dopo l'ingresso",
          ug and len(t) == 1 and (t["EntryBar"].iloc[0], t["ExitBar"].iloc[0]) == (3, 4))
    a, b, ug = entrambi(serie(12, P, {"L": [1], "S": [2]}), dict(KW, n_barre=8, inverti_su_opposto=True), **base)
    t = b["_trades"]
    check("B9. inversione sulla barra d'ingresso: chiude il long e apre lo short all'Open dopo",
          ug and len(t) == 2 and (t["EntryBar"].iloc[0], t["ExitBar"].iloc[0]) == (2, 3) and t["Size"].iloc[0] > 0
          and t["EntryBar"].iloc[1] == 3 and t["Size"].iloc[1] < 0)
    a, b, ug = entrambi(serie(12, P, {"L": [1], "S": [3], "XL": [3]}), dict(KW, n_barre=8, inverti_su_opposto=True),
                        **base)
    t = b["_trades"]
    check("B10. regola d'uscita e inversione sulla stessa barra: vince l'inversione",
          ug and len(t) == 1 and t["ExitBar"].iloc[0] == 4 and b["_trades"]["Size"].iloc[0] > 0)
    a, b, ug = entrambi(serie(12, P, {"L": [1, 3], "S": [3]}), dict(KW, n_barre=5, inverti_su_opposto=True), **base)
    t = b["_trades"]
    check("B11. long e short insieme a posizione aperta: niente", ug and len(t) == 1 and t["ExitBar"].iloc[0] == 7)
    errore_bt = errore_v = False
    try:
        tabella_bt(serie(12, P, {"L": [1]}, {"sl_long": 1.5}), dict(KW, n_barre=5), **base)
    except AssertionError:
        errore_bt = True
    try:
        veloce(serie(12, P, {"L": [1]}, {"sl_long": 1.5}), dict(KW, n_barre=5), **base)
    except ValueError:
        errore_v = True
    check("B12. stop con frazione >= 1: tutti e due si fermano con un errore", errore_bt and errore_v)

    # ====================================================================
    print("\nC · Sezione D di docs/21 sul motore veloce")
    c, s = 0.001, 0.0005
    a, b, ug = entrambi(serie(12, P, {"L": [1]}), dict(KW, n_barre=3), cash=1e6, spread=0.0, commission=c, margin=1.0)
    t = b["_trades"].iloc[0]
    atteso = c * (t["EntryPrice"] + t["ExitPrice"]) * abs(t["Size"])
    check("D1. commissione su entrambi i lati, fuori dal prezzo", ug and np.isclose(t["Commission"], atteso)
          and t["EntryPrice"] == P[2] and t["ExitPrice"] == P[5])
    a, b, ug = entrambi(serie(12, P, {"L": [1], "S": [6]}), dict(KW, n_barre=3), cash=1e6, spread=s, commission=0.0,
                        margin=1.0)
    t = b["_trades"]
    check("D2. spread una volta sola, dentro il prezzo d'ingresso; uscita al prezzo pieno",
          ug and len(t) == 2 and t["EntryPrice"].iloc[0] == P[2] * (1 + s) and t["ExitPrice"].iloc[0] == P[5]
          and t["EntryPrice"].iloc[1] == P[7] * (1 - s) and t["ExitPrice"].iloc[1] == P[10])
    # la barra d'ingresso (2) scende sotto lo stop: il trade resta aperto
    a, b, ug = entrambi(serie(12, P, {"L": [1]}, {"sl_long": 0.01}, basso={2: 90.0}), dict(KW, n_barre=4), **base)
    t = b["_trades"]
    check("D3. stop non attivo sulla barra d'ingresso, attivo dalla dopo",
          ug and len(t) == 1 and t["ExitBar"].iloc[0] == 6)

    # ====================================================================
    print("\nD · Capitale simulato esaurito (docs/65 §3.2)")
    # un sistema che perde sempre: prezzo fermo a 1000, spread del 20% (compra a 1200, rivende a 1000)
    n = 40
    d = serie(n, np.full(n, 1000.0), {"L": list(range(1, n - 2, 2))})
    run_kw = dict(KW, n_barre=1)
    kw = dict(cash=3000.0, spread=0.2, commission=0.0, margin=1.0)
    st_bt = tabella_bt(d, run_kw, **kw)
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        st_v = mv.MotoreVeloce(d, **kw).run(**run_kw)
    tb, tv = st_bt["_trades"], st_v["_trades"]
    m = len(tb)
    check("D4. backtesting.py perde trade, il motore veloce li tiene tutti per unita'",
          len(tv) > m and len(tv) == len(range(1, n - 2, 2)), f"libreria {m} · veloce {len(tv)}")
    check("D5. fino all'annullo i trade coincidono (prezzi, barre, Size)",
          all(tb[c].reset_index(drop=True).equals(tv[c].iloc[:m].reset_index(drop=True))
              for c in ("EntryBar", "ExitBar", "EntryPrice", "ExitPrice", "Size")))
    check("D6. dopo: Size +-1; Return, Sharpe e Max. Drawdown NaN",
          (tv["Size"].iloc[m:].abs() == 1).all()
          and all(np.isnan(st_v[k]) for k in ("Return [%]", "Sharpe Ratio", "Max. Drawdown [%]")))
    check("D7. avviso con la data", st_v["_capitale_esaurito"] is not None and "esaurito" in err.getvalue()
          and str(st_v["_capitale_esaurito"])[:10] in err.getvalue())

    # ====================================================================
    print("\nE · La scelta del motore")
    check("E1. None = il predefinito", mv.scegli_motore(None) == mv.MOTORE_PREDEFINITO)
    try:
        mv.scegli_motore("vectorbt")
        nome_ok = False
    except ValueError:
        nome_ok = True
    check("E2. nome sbagliato: errore", nome_ok)
    vecchio, mv.DISPONIBILE, mv._avvisato_numba = mv.DISPONIBILE, False, False
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        ripiego = mv.scegli_motore("veloce")
    mv.DISPONIBILE = vecchio
    check("E3. senza numba «veloce» ripiega su «bt» con un avviso, senza fermarsi",
          ripiego == "bt" and "numba" in err.getvalue())

    # ====================================================================
    print("\nF · I motori del tool con «bt» e con «veloce»")
    from engine import registry as reg
    from engine.exit_search_bt import run_exit_search_bt
    from engine.filter_search_bt import run_filter_search_bt
    from engine.due_meta import due_meta
    rng = np.random.default_rng(7)
    df = dati_veri(rng, 30_000) if ci_sono_veri else dati_finti(rng, 30_000)
    nb = len(df)
    sl, ss = rng.random(nb) < 0.01, rng.random(nb) < 0.01
    xl, xs = rng.random(nb) < 0.02, rng.random(nb) < 0.02
    f1, f2 = rng.random(nb) < 0.6, rng.random(nb) < 0.5
    def su(a):
        """La condizione registrata: i valori di `a`, letti per data (vale anche sulle due meta')."""
        serie_ = pd.Series(a, index=df.index)
        return lambda x: serie_.reindex(x.index).fillna(False).astype(bool)

    reg.clear_registry()
    reg.register_entry("MV_T_LONG", 1)(su(sl))
    reg.register_entry("MV_T_SHORT", -1)(su(ss))
    reg.register_exit("MV_X_LONG", 1, pair="MV_X")(su(xl))
    reg.register_exit("MV_X_SHORT", -1, pair="MV_X")(su(xs))
    reg.register_filter("MV_F1", 0)(su(f1))
    reg.register_filter("MV_F2", 1)(su(f2))
    costi = dict(spread=0.0002, commission=0.0005, cash=float(df["Close"].max()) * 100, pip_size=0.1)
    comuni = dict(n_barre=12, perc_sl=90.0, perc_tp=0.0, finestra=200, lag=1, quarantena=False,
                  inverti_su_opposto=True, verbose=False, unita="bp", **costi)
    es = {m_: run_exit_search_bt(df, entry_cols_long=["MV_T_LONG", None], entry_cols_short=["MV_T_SHORT", None],
                                 exit_rule_pairs=[None, "MV_X"], motore=m_, **comuni) for m_ in ("bt", "veloce")}
    check("F1. run_exit_search_bt: stessa tabella", es["bt"].risultati.equals(es["veloce"].risultati))
    check("F2. run_exit_search_bt: stessi trade per ogni combinazione",
          all(not stesse_colonne(es["bt"].trades(c_), es["veloce"].trades(c_))
              for c_ in es["bt"].risultati["combinazione"]))
    check("F3. il risultato ricorda il motore", (es["bt"].motore, es["veloce"].motore) == ("bt", "veloce"))
    fs = {m_: run_filter_search_bt(df, entry_long="MV_T_LONG", entry_short="MV_T_SHORT", exit_rule_pair="MV_X",
                                   filtri=["MV_F1", "MV_F2"], n_boot=500, motore=m_, **comuni)
          for m_ in ("bt", "veloce")}
    check("F4. run_filter_search_bt: stessa tabella", fs["bt"].risultati.equals(fs["veloce"].risultati))
    check("F5. run_filter_search_bt: stessi trade per ogni riga",
          all(not stesse_colonne(fs["bt"].trades(f_), fs["veloce"].trades(f_)) for f_ in fs["bt"].risultati["filtro"]))
    with contextlib.redirect_stdout(io.StringIO()):
        dm = {m_: due_meta(df, fs[m_], [None, "MV_F1", "MV_F2"], perc_sl=90.0, finestra=200, lag=1,
                           quarantena=False, verbose=False, **{k: costi[k] for k in ("spread", "commission", "cash")})
              for m_ in ("bt", "veloce")}
    check("F6. due_meta usa il motore di fs e da' la stessa tabella",
          dm["bt"].tabella.equals(dm["veloce"].tabella) and dm["veloce"].metà1.motore == "veloce")
    reg.clear_registry()

    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
