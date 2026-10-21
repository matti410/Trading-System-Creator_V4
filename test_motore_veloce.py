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
  G. E4: maschere in cache, filtri VWAP, bootstrap.
  H. Stop e target attivi sulla barra d'ingresso (21/10/2026): casi a
     risultato noto, long e short, uscita a tempo, nessun rientro nella
     stessa barra, funding sui trade di durata zero, lag < 1, troncamento.

Dal 21/10/2026 il motore veloce attiva stop e target gia' sulla barra
d'ingresso; backtesting.py resta l'oracolo del comportamento VECCHIO. Per
questo A-F confrontano i due motori dentro `mv.comportamento_vecchio()`
(l'interruttore interno, solo per i test): stessa severita' di prima, al bit.

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


def veloce(d, run_kw, vecchio=True, **bt_kw):
    """Il motore veloce; vecchio=True = stop e target dalla barra dopo, come l'oracolo."""
    with contextlib.redirect_stderr(io.StringIO()):
        if vecchio:
            with mv.comportamento_vecchio():
                return mv.MotoreVeloce(d, exclusive_orders=True, **bt_kw).run(**run_kw)
        return mv.MotoreVeloce(d, exclusive_orders=True, **bt_kw).run(**run_kw)


def veloce_nuovo(d, run_kw, **bt_kw):
    """Il motore veloce com'e' dal 21/10/2026: stop e target attivi sulla barra d'ingresso."""
    return veloce(d, run_kw, vecchio=False, **bt_kw)


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
    with contextlib.redirect_stderr(err), mv.comportamento_vecchio():
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
    vecchio = mv.comportamento_vecchio()     # confronto con l'oracolo: comportamento vecchio
    vecchio.__enter__()
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
    vecchio.__exit__(None, None, None)
    check("F6. due_meta usa il motore di fs e da' la stessa tabella",
          dm["bt"].tabella.equals(dm["veloce"].tabella) and dm["veloce"].metà1.motore == "veloce")

    # ====================================================================
    # 21/10/2026 (E4, docs/65 §16): ogni pezzo con la sua prova di identita'
    print("\nG · E4: maschere in cache, filtri VWAP, bootstrap (identici al bit)")
    chiamate = {"n": 0}
    def contata(a):
        f_ = su(a)
        def filtro(x):
            chiamate["n"] += 1
            return f_(x)
        return filtro
    reg.register_filter("MV_F3", -1)(contata(rng.random(nb) < 0.55))
    filtri_g = ["MV_F1", "MV_F2", "MV_F3"]
    kw_fs = dict(entry_long="MV_T_LONG", entry_short="MV_T_SHORT", exit_rule_pair="MV_X",
                 filtri=filtri_g, n_boot=500, **comuni)
    senza = run_filter_search_bt(df, **kw_fs)
    cache = {}
    prima = run_filter_search_bt(df, cache_maschere=cache, **kw_fs)
    n_prima = chiamate["n"]
    dopo = run_filter_search_bt(df, cache_maschere=cache, **kw_fs)
    def stesso_fs(a, b):
        return a.risultati.equals(b.risultati) and all(
            not stesse_colonne(a.trades(f_), b.trades(f_)) for f_ in a.risultati["filtro"])
    check("G1. cache delle maschere: stessa tabella e stessi trade, alla prima e alla seconda chiamata",
          stesso_fs(senza, prima) and stesso_fs(senza, dopo))
    check("G2. alla seconda chiamata sullo stesso df le maschere si riusano",
          n_prima == 2 and chiamate["n"] == 2, f"chiamate del filtro: {chiamate['n']} (attese 2)")
    corto = df.iloc[: nb // 2]
    altro = run_filter_search_bt(corto, cache_maschere=cache, **kw_fs)
    check("G3. stessa cache con un df diverso: si svuota e ricalcola, risultati giusti",
          stesso_fs(run_filter_search_bt(corto, **kw_fs), altro) and chiamate["n"] == 4)
    reg.clear_registry()
    reg.register_entry("MV_T_LONG", 1)(su(sl))
    reg.register_entry("MV_T_SHORT", -1)(su(ss))
    reg.register_exit("MV_X_LONG", 1, pair="MV_X")(su(xl))
    reg.register_exit("MV_X_SHORT", -1, pair="MV_X")(su(xs))
    reg.register_filter("MV_F1", 0)(su(~f1))          # stesso nome, funzione nuova
    reg.register_filter("MV_F2", 1)(su(f2))
    reg.register_filter("MV_F3", -1)(contata(rng.random(nb) < 0.55))
    nuovo = run_filter_search_bt(corto, cache_maschere=cache, **kw_fs)
    check("G4. filtro registrato di nuovo con lo stesso nome: la maschera si ricalcola",
          stesso_fs(run_filter_search_bt(corto, **kw_fs), nuovo))
    voce = next(v_ for k_, v_ in cache.items() if k_ == "MV_F1")
    try:
        voce[1][0] = not voce[1][0]
        sola_lettura = False
    except ValueError:
        sola_lettura = True
    check("G5. le maschere in cache sono in sola lettura", sola_lettura)
    fs_c = run_filter_search_bt(df, **kw_fs)
    with contextlib.redirect_stdout(io.StringIO()):
        kw_dm = dict(perc_sl=90.0, finestra=200, lag=1, quarantena=False, verbose=False,
                     **{k: costi[k] for k in ("spread", "commission", "cash")})
        dm_senza = due_meta(df, fs_c, [None, *filtri_g], **kw_dm)
        cache_dm = {}
        dm_1 = due_meta(df, fs_c, [None, *filtri_g], cache_maschere=cache_dm, **kw_dm)
        dm_2 = due_meta(df, fs_c, [None, *filtri_g], cache_maschere=cache_dm, **kw_dm)
    check("G6. due_meta con la cache (una per meta'): stessa tabella",
          dm_senza.tabella.equals(dm_1.tabella) and dm_senza.tabella.equals(dm_2.tabella)
          and set(cache_dm) == {"metà 1", "metà 2"})
    reg.clear_registry()

    # filtri VWAP: la regressione compilata contro quella di prima (pandas)
    from engine import vwap_ops
    import vwap_regime_filter_conditions as vrf
    df_v = _veri().copy() if ci_sono_veri else dati_finti(np.random.default_rng(3), 60_000)
    df_v["vwap"] = vwap_ops.vwap_anchored_daily(df_v)
    casi = {"tutta la serie": df_v["Close"], "un giorno": df_v["Close"].iloc[:40],
            "con un NaN": df_v["Close"].where(np.arange(len(df_v)) != 1000),
            "senza fuso": df_v["Close"].tz_localize(None) if df_v.index.tz is not None else df_v["Close"],
            "una barra": df_v["Close"].iloc[:1]}
    diversi = [k_ for k_, c_ in casi.items()
               if not vwap_ops.regression_trend_fit(c_).equals(vwap_ops._regression_trend_fit_pandas(c_))]
    check("G7. regression_trend_fit compilata = quella di prima, al bit (serie, giorno, NaN, fuso, una barra)",
          not diversi, f"diversi: {diversi}" if diversi else f"{len(df_v):,} barre")
    nuovi = {n_: f_(df_v) for n_, (f_, _, _) in vrf.FILTRI_VWAP.items()}
    originale = vwap_ops.regression_trend_fit
    vwap_ops.regression_trend_fit = vrf.regression_trend_fit = vwap_ops._regression_trend_fit_pandas
    try:
        vecchi = {n_: f_(df_v) for n_, (f_, _, _) in vrf.FILTRI_VWAP.items()}
    finally:
        vwap_ops.regression_trend_fit = vrf.regression_trend_fit = originale
    check(f"G8. i {len(nuovi)} filtri VWAP accesi: stesse maschere di prima",
          all(nuovi[n_].equals(vecchi[n_]) for n_ in nuovi), ", ".join(nuovi))

    # bootstrap di P(EV<0): stessi indici casuali e stesse medie di rng.choice(...).mean(axis=1)
    from engine import giudizio
    rng_g = np.random.default_rng(11)
    lunghezze = list(range(2, 140)) + [255, 256, 257, 1000, 1500, 4099, 8191, 8193, 12001]
    diverse = []
    for n_ in lunghezze:
        x_ = rng_g.standard_t(3, size=n_) * rng_g.choice([0.1, 7.0, 300.0]) + rng_g.normal(0, 1)
        nb_ = 2000 if n_ < 2000 else 300
        for seme in (0, 5):
            a_ = np.random.default_rng(seme).choice(x_, size=(nb_, n_), replace=True).mean(axis=1)
            if not np.array_equal(a_, giudizio._medie_bootstrap(x_, nb_, seme)):
                diverse.append(n_)
    check("G9. bootstrap: stesse medie di rng.choice(...).mean(axis=1), al bit",
          not diverse, f"lunghezze diverse: {diverse[:10]}" if diverse else f"{len(lunghezze)} lunghezze, 2 semi")
    x_ = rng_g.normal(0.3, 10, 1200)
    vecchio_p = float((np.random.default_rng(0).choice(x_, size=(10_000, x_.size), replace=True)
                       .mean(axis=1) < 0).mean() * 100.0)
    giudizio.DISPONIBILE = False
    try:
        p_senza_numba = giudizio.p_ev_negativo(x_)
    finally:
        giudizio.DISPONIBILE = mv.DISPONIBILE
    check("G10. p_ev_negativo = il calcolo di prima, anche senza numba",
          giudizio.p_ev_negativo(x_) == vecchio_p == p_senza_numba, f"P(EV<0) = {vecchio_p:.2f}%")

    # le funzioni compilate rilette dalla cache di numba (21/10/2026: una funzione
    # ricorsiva, riletta dalla cache, mandava in crash Python): due processi nuovi di fila
    import subprocess
    codice = ("import numpy as np, pandas as pd\n"
              "from engine.giudizio import p_ev_negativo\n"
              "from engine.vwap_ops import regression_trend_fit\n"
              "x = np.random.default_rng(0).normal(0.1, 1, 3000)\n"
              "i = pd.date_range('2024-01-01', periods=3000, freq='15min', tz='UTC')\n"
              "print(p_ev_negativo(x), regression_trend_fit(pd.Series(x, index=i)).sum())\n")
    uscite = [subprocess.run([sys.executable, "-c", codice], capture_output=True, text=True,
                             cwd=os.path.dirname(os.path.abspath(__file__))) for _ in range(2)]
    check("G11. funzioni compilate rilette dalla cache di numba: nessun crash, stessi numeri",
          all(u.returncode == 0 for u in uscite) and uscite[0].stdout == uscite[1].stdout != "",
          f"codici di uscita {[u.returncode for u in uscite]}")


    # ====================================================================
    # 21/10/2026: stop e target attivi gia' sulla barra d'ingresso
    print("\nH · Stop e target sulla barra d'ingresso (comportamento nuovo)")
    # P: Open 100, 101, 102...; High = Open + 0,5; Low = Open - 0,5. Segnale alla barra 1,
    # ingresso all'Open della barra 2 (102)
    def uno(d, run_kw, **kw):
        t_ = veloce_nuovo(d, run_kw, **kw)["_trades"]
        return t_, [(int(a_), int(b_), float(c_)) for a_, b_, c_ in
                    zip(t_["EntryBar"], t_["ExitBar"], t_["ExitPrice"])]
    _, tr = uno(serie(12, P, {"L": [1]}, {"sl_long": 0.01}, basso={2: 90.0}), dict(KW, n_barre=4), **base)
    check("H1. long: stop toccato nella barra d'ingresso, uscita allo stop nella stessa barra",
          tr == [(2, 2, 102.0 * (1 - 0.01))], f"{tr}")
    _, tr = uno(serie(12, P, {"S": [1]}, {"sl_short": 0.01}, alto={2: 110.0}), dict(KW, n_barre=4), **base)
    check("H2. short: stop toccato nella barra d'ingresso, uscita allo stop nella stessa barra",
          tr == [(2, 2, 102.0 * (1 + 0.01))], f"{tr}")
    _, tr = uno(serie(12, P, {"L": [1]}, {"tp_long": 0.003}), dict(KW, n_barre=4), **base)
    check("H3. long: target toccato nella barra d'ingresso (High 102,5 >= 102,306)",
          tr == [(2, 2, 102.0 * (1 + 0.003))], f"{tr}")
    _, tr = uno(serie(12, P, {"S": [1]}, {"tp_short": 0.003}), dict(KW, n_barre=4), **base)
    check("H4. short: target toccato nella barra d'ingresso (Low 101,5 <= 101,694)",
          tr == [(2, 2, 102.0 * (1 - 0.003))], f"{tr}")
    _, tr = uno(serie(12, P, {"L": [1]}, {"sl_long": 0.01, "tp_long": 0.003}, basso={2: 90.0}),
                dict(KW, n_barre=4), **base)
    check("H5. long: stop e target nella barra d'ingresso, vince lo stop",
          tr == [(2, 2, 102.0 * (1 - 0.01))], f"{tr}")
    _, tr = uno(serie(12, P, {"S": [1]}, {"sl_short": 0.01, "tp_short": 0.003}, alto={2: 110.0}),
                dict(KW, n_barre=4), **base)
    check("H6. short: stop e target nella barra d'ingresso, vince lo stop",
          tr == [(2, 2, 102.0 * (1 + 0.01))], f"{tr}")
    # spread 1%: ingresso 103,02, stop 0,5% sotto = 102,5049 > Open 102: si esce all'Open
    _, tr = uno(serie(12, P, {"L": [1]}, {"sl_long": 0.005}), dict(KW, n_barre=4),
                cash=1e6, spread=0.01, commission=0.0, margin=1.0)
    check("H7. stop dentro lo spread: uscita all'Open della barra d'ingresso", tr == [(2, 2, 102.0)], f"{tr}")
    d = serie(12, P, {"L": [1], "S": [7]}, {"sl_long": 0.05, "tp_long": 0.05, "sl_short": 0.05})
    a, b = tabella_bt(d, dict(KW, n_barre=3), **base), veloce_nuovo(d, dict(KW, n_barre=3), **base)
    check("H8. stop e target non toccati: trade e statistiche identici a backtesting.py",
          not stesse_colonne(a["_trades"], b["_trades"]) and not stesse_statistiche(a, b)
          and len(b["_trades"]) == 2)
    _, tr = uno(serie(12, P, {"L": [1, 2]}, {"sl_long": 0.01}, basso={2: 90.0}), dict(KW, n_barre=4), **base)
    check("H9. nessun rientro nella stessa barra: chiuso sulla barra d'ingresso (2), il segnale della "
          "barra 2 apre all'Open della 3",
          len(tr) == 2 and tr[0] == (2, 2, 102.0 * (1 - 0.01)) and tr[1][0] == 3, f"{tr}")
    d = serie(12, P, {"L": [1, 3]}, {"sl_long": 0.01}, basso={2: 90.0})
    _, tr = uno(d, dict(KW, n_barre=4), **base)
    tr_v = [(int(a_), int(b_)) for a_, b_ in zip(*(veloce(d, dict(KW, n_barre=4), **base)["_trades"][c]
                                                   for c in ("EntryBar", "ExitBar")))]
    check("H10. il posto liberato: col comportamento vecchio un trade (2-6), col nuovo due (2-2 e 4-8)",
          tr_v == [(2, 6)] and [(x[0], x[1]) for x in tr] == [(2, 2), (4, 8)], f"vecchio {tr_v} · nuovo {tr}")
    for nb_, atteso in ((1, (2, 3)), (3, (2, 5)), (5, (2, 7))):
        d = serie(12, P, {"L": [1]}, {"sl_long": 0.05, "tp_long": 0.05})
        _, tr = uno(d, dict(KW, n_barre=nb_), **base)
        t_bt = tabella_bt(d, dict(KW, n_barre=nb_), **base)["_trades"]
        check(f"H11. uscita a tempo dopo {nb_} barre: stesso conteggio di oggi ({atteso[0]}-{atteso[1]})",
              [(x[0], x[1]) for x in tr] == [atteso]
              and (int(t_bt["EntryBar"].iloc[0]), int(t_bt["ExitBar"].iloc[0])) == atteso, f"{tr}")

    # funding sui trade di durata zero (perpetual): barre da 07:30 UTC, la barra 2 apre alle 08:00
    from engine.exchange import funding_per_trade
    indice_f = pd.date_range("2024-01-02 07:30", periods=12, freq="15min", tz="UTC")
    funding_f = pd.DataFrame({"tasso": [0.001, 0.001]},
                             index=pd.DatetimeIndex(["2024-01-02 08:00", "2024-01-02 16:00"], tz="UTC"))
    pip_f = 0.01
    esiti_f = {}
    for nome_, segnali_, soglie_, estremi_ in (
            ("long", {"L": [1]}, {"sl_long": 0.01}, dict(basso={2: 90.0})),
            ("short", {"S": [1]}, {"sl_short": 0.01}, dict(alto={2: 110.0}))):
        d = serie(12, P, segnali_, soglie_, **estremi_)
        d.index = indice_f
        t_ = veloce_nuovo(d, dict(KW, n_barre=4), **base)["_trades"]
        esiti_f[nome_] = (t_, funding_per_trade(t_, d, funding_f, pip_f) if len(t_) else pd.Series(dtype=float))
    t_l, f_l = esiti_f["long"]
    t_s, f_s = esiti_f["short"]
    check("H12. funding, durata zero: long e short entrati all'Open delle 08:00 e usciti nella stessa barra "
          "non pagano la liquidazione delle 08:00 (regola di oggi: ingresso < S <= uscita)",
          len(t_l) == len(t_s) == 1 and t_l["EntryTime"].iloc[0] == t_l["ExitTime"].iloc[0] == indice_f[2]
          and t_s["EntryTime"].iloc[0] == t_s["ExitTime"].iloc[0] == indice_f[2]
          and f_l.iloc[0] == 0.0 and f_s.iloc[0] == 0.0, f"long {f_l.tolist()} · short {f_s.tolist()}")
    # controprova: barre da 07:15, ingresso alla barra 2 (07:45), stop toccato nella 3 (08:00)
    d = serie(12, P, {"L": [1]}, {"sl_long": 0.01}, basso={3: 90.0})
    d.index = pd.date_range("2024-01-02 07:15", periods=12, freq="15min", tz="UTC")
    t_c = veloce_nuovo(d, dict(KW, n_barre=4), **base)["_trades"]
    f_c = funding_per_trade(t_c, d, funding_f, pip_f)
    atteso_c = 0.001 * float(d["Open"].iloc[3]) / pip_f
    check("H13. funding, controprova: ingresso alle 07:45, stop nella barra delle 08:00: paga la liquidazione "
          "delle 08:00 (long, tasso positivo)",
          len(t_c) == 1 and (int(t_c["EntryBar"].iloc[0]), int(t_c["ExitBar"].iloc[0])) == (2, 3)
          and np.isclose(f_c.iloc[0], atteso_c), f"{f_c.tolist()} (atteso {atteso_c:.4f})")

    # lag < 1: con il comportamento nuovo i motori si fermano
    reg.clear_registry()
    reg.register_entry("MV_T_LONG", 1)(su(sl))
    reg.register_entry("MV_T_SHORT", -1)(su(ss))
    kw_lag = dict(comuni, lag=0)
    errori = {}
    for nome_, chiama in (("exit", lambda **k: run_exit_search_bt(df, entry_cols_long=["MV_T_LONG"],
                                                                   entry_cols_short=["MV_T_SHORT"], **k)),
                          ("filter", lambda **k: run_filter_search_bt(df, entry_long="MV_T_LONG",
                                                                       entry_short="MV_T_SHORT", filtri=[],
                                                                       n_boot=200, **k))):
        try:
            chiama(motore="veloce", **kw_lag)
            errori[nome_] = False
        except ValueError as e:
            errori[nome_] = "lag" in str(e)
    senza_stop = dict(kw_lag, perc_sl=0.0, perc_tp=0.0)
    try:
        run_exit_search_bt(df, entry_cols_long=["MV_T_LONG"], entry_cols_short=["MV_T_SHORT"],
                           motore="veloce", **senza_stop)
        run_exit_search_bt(df, entry_cols_long=["MV_T_LONG"], entry_cols_short=["MV_T_SHORT"],
                           motore="bt", **kw_lag)
        with mv.comportamento_vecchio():
            run_exit_search_bt(df, entry_cols_long=["MV_T_LONG"], entry_cols_short=["MV_T_SHORT"],
                               motore="veloce", **kw_lag)
        altri_ok = True
    except ValueError:
        altri_ok = False
    check("H14. lag < 1 con stop o target accesi: run_exit_search_bt e run_filter_search_bt si fermano "
          "(non con stop e target spenti, non con «bt», non col comportamento vecchio)",
          all(errori.values()) and altri_ok, f"{errori} · altri casi senza errore: {altri_ok}")
    reg.clear_registry()

    # lookahead per troncamento: tagliato lo storico alla barra T, i trade chiusi prima di T non cambiano
    rng_h = np.random.default_rng(21)
    diversi_h, provati = 0, 0
    for _k in range(20):
        df_h = dati_finti(rng_h, 2_000)
        d, run_kw, bt_kw = configurazione(rng_h, df_h)
        bt_kw["cash"] = 1e12
        pieno = veloce_nuovo(d, run_kw, **bt_kw)["_trades"]
        for T in (700, 1_300, 1_900):
            # il motore vede solo le prime T barre (segnali e soglie, gia' causali, tagliati)
            tagliato = veloce_nuovo(d.iloc[:T].copy(), run_kw, **bt_kw)["_trades"]
            chiusi = pieno[pieno["ExitBar"] < T - 1].reset_index(drop=True)
            provati += len(chiusi)
            primi = tagliato.iloc[:len(chiusi)].reset_index(drop=True)
            if stesse_colonne(chiusi[COLONNE[:10]], primi[COLONNE[:10]]):
                diversi_h += 1
    # due trade chiusi nella stessa barra (uno all'Open, l'altro sullo stop dentro la barra)
    from engine.equity_plot import _equity_strategia
    d = serie(12, P, {"L": [1], "S": [2]}, {"sl_short": 0.01}, alto={3: 120.0})
    # long alla barra 2; lo short della barra 2 lo inverte: chiusura e short all'Open della 3,
    # e lo short tocca lo stop nella stessa barra 3
    t_eq = veloce_nuovo(d, dict(KW, n_barre=4, inverti_su_opposto=True),
                        cash=1e6, spread=0.0, commission=0.0, margin=1.0)["_trades"]
    curva = _equity_strategia(t_eq, d, 1e6)
    vecchia = (1e6 + t_eq.set_index("ExitTime")["PnL"].sort_index().cumsum()) if t_eq["ExitTime"].is_unique else None
    check("H16. equity del grafico con due trade chiusi nella stessa barra: i PnL si sommano",
          len(t_eq) == 2 and t_eq["ExitTime"].iloc[0] == t_eq["ExitTime"].iloc[1] and vecchia is None
          and np.isclose(curva.iloc[-1], 1e6 + t_eq["PnL"].sum()) and curva.index.equals(d.index),
          f"{[(int(a_), int(b_)) for a_, b_ in zip(t_eq['EntryBar'], t_eq['ExitBar'])]}")
    check("H15. troncamento: i trade chiusi prima del taglio non cambiano (20 configurazioni, 3 tagli)",
          diversi_h == 0 and provati > 0, f"tagli con differenze {diversi_h} · trade confrontati {provati:,}")

    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
