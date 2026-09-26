"""
Suite di validazione di engine/confidenza.py.

Si lancia da terminale, dalla cartella del progetto:

    python test_confidenza.py

Non serve MetaTrader 5 e non serve nessun file di dati: usa un mercato
sintetico (random walk). Richiede backtesting==0.6.6 e il file
engine/volatility_features_engineering.py. Dura circa un minuto.
"""
from __future__ import annotations

import sys
import warnings

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

from engine.collaudo_catalogo import mercato_sintetico
from engine.confidenza import (ETICHETTE_CELLA, asse_volatilita, cella_contesto,
                               congela_filtro, congela_confidenza_nota,
                               confidenza_rolling, esiti_trade, gap_trend,
                               plot_oos_confidenza, registra_filtro_confidenza,
                               report_calibrazione)
from engine.filter_search_bt import BASELINE, run_filter_search_bt
from engine.livelli import giorno_fx, svuota_cache
from engine.registry import (clear_registry, get_entry, list_entries, list_filters,
                             register_entry, register_filter)

warnings.simplefilter("ignore")


# riferimento: la regressione del file di Mattia, a ciclo, per UNA giornata
def _regressione_ciclo(y):
    n = len(y)
    fitted = np.empty(n)
    sum_y = sum_xy = 0.0
    for i in range(n):
        sum_y += y[i]
        sum_xy += i * y[i]
        if i == 0:
            fitted[i] = y[i]
        else:
            n_points = i + 1
            sum_x = i * (i + 1) / 2
            sum_x2 = i * (i + 1) * (2 * i + 1) / 6
            denom = n_points * sum_x2 - sum_x * sum_x
            slope = (n_points * sum_xy - sum_x * sum_y) / denom
            intercept = (sum_y - slope * sum_x) / n_points
            fitted[i] = intercept + slope * i
    return fitted


def _esiti_finti(n_barre, n_trade, rng, durata=(2, 20)):
    segnale = np.sort(rng.integers(600, n_barre - 30, n_trade))
    uscita = segnale + 1 + rng.integers(durata[0], durata[1], n_trade)
    lato = rng.choice([1, -1], n_trade)
    return pd.DataFrame({"barra_segnale": segnale, "barra_uscita": uscita,
                         "lato": lato, "pips_netti": 0.0, "vinto": 0})


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    svuota_cache()
    df = mercato_sintetico("2023-01-01", "2024-07-01", seme=3)
    n = len(df)
    rng = np.random.default_rng(7)

    # ------------------------------------------------------------ contesto --
    print("\nA · Il contesto")

    gap = gap_trend(df)
    giorno = giorno_fx(df)
    atteso = np.full(n, np.nan)
    tipico = ((df["High"] + df["Low"] + df["Close"]) / 3).to_numpy()
    vol = df["Volume"].to_numpy()
    close = df["Close"].to_numpy()
    for g in np.unique(giorno.to_numpy()):
        idx = np.flatnonzero(giorno.to_numpy() == g)
        vwap = np.cumsum(tipico[idx] * vol[idx]) / np.cumsum(vol[idx])
        atteso[idx] = _regressione_ciclo(close[idx]) - vwap
    scarto = np.nanmax(np.abs(gap.to_numpy() - atteso))
    check("1. aura_gap vettoriale = regressione a ciclo del file originale, per giornata FX",
          scarto < 1e-9, f"scarto massimo {scarto:.2e} su {len(np.unique(giorno))} giornate")

    # la giornata si taglia al rollover delle 17:00 di New York
    ny = df.index.tz_convert("America/New_York")
    prime = np.r_[True, giorno.to_numpy()[1:] != giorno.to_numpy()[:-1]]
    ore_prime = pd.Series(ny[prime].hour).value_counts()
    check("2. la regressione riparte a ogni rollover (17:00 New York)",
          ore_prime.index[0] == 17 and np.isclose(gap.to_numpy()[prime],
          close[prime] - tipico[prime]).all(),
          f"ora di inizio piu' frequente: {ore_prime.index[0]}:00 NY")

    v = asse_volatilita(df, finestra_vol=20, finestra=500)
    std20 = (np.log(df["Close"] / df["Close"].shift(1)) * 100).rolling(20).std()
    mediana = std20.rolling(500, min_periods=500).median()
    attesa_v = (std20 > mediana).astype(float).where(mediana.notna())
    uguali = (v.fillna(-1) == attesa_v.fillna(-1)).all()
    check("3. asse volatilita' (build_labels a 0.5) = std20 sopra la mediana rolling a 500",
          uguali and set(v.dropna().unique()) == {0.0, 1.0},
          f"quota alta {v.mean():.2f}")

    cl = cella_contesto(df, 1)
    cs = cella_contesto(df, -1)
    entrambe = cl.notna() & cs.notna()
    trend_l = cl[entrambe] % 2
    trend_s = cs[entrambe] % 2
    vol_uguale = ((cl[entrambe] // 2) == (cs[entrambe] // 2)).all()
    speculari = (trend_l + trend_s == 1).mean()
    check("4. long e short: stessa volatilita', trend a favore/contro speculare",
          vol_uguale and speculari > 0.99, f"speculari nel {speculari:.1%} delle barre")

    quote = cl.value_counts(normalize=True).sort_index()
    check("5. le quattro celle sono tutte popolate", len(quote) == 4 and quote.min() > 0.10,
          " · ".join(f"{ETICHETTE_CELLA[int(c)]} {q:.0%}" for c, q in quote.items()))

    tagli = rng.integers(3000, n - 100, 5)
    ok = True
    for t in tagli:
        svuota_cache()
        parziale = cella_contesto(df.iloc[:t], 1)
        ok &= (parziale.fillna(-1).to_numpy() == cl.iloc[:t].fillna(-1).to_numpy()).all()
    svuota_cache()
    check("6. nessun lookahead nella cella: troncando lo storico i valori non cambiano",
          ok, f"{len(tagli)} tagli")

    # ---------------------------------------------------------- confidenza --
    print("\nB · La confidenza, su esiti costruiti a mano")

    e = _esiti_finti(n, 3000, rng)
    e["pips_netti"] = rng.normal(0, 1, len(e))
    e["vinto"] = (e["pips_netti"] > 0).astype(int)
    conf = confidenza_rolling(df, e, 1, finestra_trade=500, min_obs=30)
    celle = cl.to_numpy()

    # forza bruta su 300 barre a caso
    el = e[e["lato"] == 1].copy()
    el["cella"] = celle[el["barra_segnale"]]
    el = el.sort_values("barra_uscita", kind="mergesort")
    diff = 0.0
    for t in rng.integers(2000, n, 300):
        usciti = el[el["barra_uscita"] <= t].tail(500)
        g = usciti[usciti["cella"] == celle[t]]
        att = g["pips_netti"].mean() if (not np.isnan(celle[t]) and len(g) >= 30) else np.nan
        got = conf["pips_medi"].iat[t]
        if np.isnan(att) != np.isnan(got):
            diff = np.inf
            break
        if not np.isnan(att):
            diff = max(diff, abs(att - got))
    check("7. confidenza = media a forza bruta degli ultimi 500 trade usciti, stessa cella",
          diff < 1e-12, f"scarto massimo {diff:.1e} su 300 barre")

    ultimi = conf["pips_medi"].iloc[-1000:].groupby(conf["etichetta"].iloc[-1000:]).mean()
    check("8. esiti casuali -> confidenza piatta intorno a zero in ogni cella",
          (ultimi.abs() < 0.4).all(),
          " · ".join(f"{k.split('·')[0][4:]}/{k.split('·')[1][6:]} {v:+.2f}" for k, v in ultimi.items()))

    e2 = e.copy()
    cella_segnale = celle[e2["barra_segnale"]]
    e2["pips_netti"] = np.where(cella_segnale == 3, 2.0, -0.5)
    e2["vinto"] = (e2["pips_netti"] > 0).astype(int)
    conf2 = confidenza_rolling(df, e2, 1, min_obs=30)
    ok3 = conf2.loc[conf2["cella"] == 3, "pips_medi"].dropna()
    ok_altre = conf2.loc[conf2["cella"].isin([0, 1, 2]), "pips_medi"].dropna()
    check("9. esiti che rendono solo in VOL_ALTA·TREND_FAVORE -> quella cella emerge, esatta",
          (ok3 == 2.0).all() and (ok_altre == -0.5).all() and len(ok3) > 0,
          f"{len(ok3)} barre a +2.0, {len(ok_altre)} a -0.5")
    check("10. win rate coerente: 1 nella cella buona, 0 nelle altre",
          (conf2.loc[conf2["cella"] == 3, "win_rate"].dropna() == 1).all()
          and (conf2.loc[conf2["cella"] != 3, "win_rate"].dropna() == 0).all())

    sotto = conf2[(conf2["n_storia"] < 30) & conf2["cella"].notna()]
    check("11. sotto min_obs la confidenza e' NaN",
          sotto["pips_medi"].isna().all() and len(sotto) > 0, f"{len(sotto)} barre nel riscaldamento")

    # un trade conta dalla sua barra di uscita, non prima
    t_segnale = int(np.flatnonzero(celle == 3)[-200])
    t_uscita = t_segnale + 40
    e3 = pd.DataFrame({"barra_segnale": [t_segnale], "barra_uscita": [t_uscita],
                       "lato": [1], "pips_netti": [5.0], "vinto": [1]})
    conf3 = confidenza_rolling(df, e3, 1, min_obs=1)
    stessa = np.flatnonzero(celle == 3)
    prima = stessa[(stessa < t_uscita) & (stessa > t_segnale)]
    dopo = stessa[stessa >= t_uscita]
    check("12. un trade entra nella storia alla barra in cui esce, non prima",
          conf3["pips_medi"].iloc[prima].isna().all()
          and (conf3["pips_medi"].iloc[dopo] == 5.0).all() and len(prima) > 0,
          f"{len(prima)} barre prima dell'uscita senza confidenza, {len(dopo)} dopo con")

    conf_corta = confidenza_rolling(df, e, 1, finestra_trade=50, min_obs=5)
    t = n - 1
    usciti = el[el["barra_uscita"] <= t].tail(50)
    g = usciti[usciti["cella"] == celle[t]]
    check("13. la finestra conta gli ultimi N trade del lato, non di tutti i lati",
          np.isclose(conf_corta["pips_medi"].iat[t], g["pips_netti"].mean())
          or (len(g) < 5 and np.isnan(conf_corta["pips_medi"].iat[t])))

    # -------------------------------------------------- dentro al backtest --
    print("\nC · Dentro al backtest (backtesting.py)")
    clear_registry()
    segnali = pd.Series(rng.random(n), index=df.index)
    register_entry("T_RANDOM_LONG", 1)(lambda d: (segnali.reindex(d.index) < 0.012))
    register_entry("T_RANDOM_SHORT", -1)(lambda d: (segnali.reindex(d.index) > 0.988))

    costi = {"spread": 0.00001, "commission": 0.0000325}
    param = dict(entry_long="T_RANDOM_LONG", entry_short="T_RANDOM_SHORT",
                 n_barre=12, perc_sl=90.0, perc_tp=0.0, **costi, verbose=False)
    fs_base = run_filter_search_bt(df, filtri=[], **param)
    tr = fs_base.trades()
    es = esiti_trade(tr, df, fs_base.pip_size, costi["commission"])
    pips_check = np.isclose(es["pips_netti"].mean(), fs_base.risultati["avg_trade_netto"].iat[0])
    check("14. esiti_trade: stessi pips netti della tabella dei filtri, segnale = ingresso - 1",
          pips_check and (df.index[es["barra_segnale"] + 1] == pd.DatetimeIndex(tr["EntryTime"])).all(),
          f"{len(es)} trade, avg_trade_netto {es['pips_netti'].mean():+.3f}")

    conf_l = confidenza_rolling(df, es, 1)
    conf_s = confidenza_rolling(df, es, -1)

    # lookahead dell'intera catena: backtest, esiti, confidenza su storico troncato
    ok = True
    for t in rng.integers(n // 3, n - 200, 3):
        svuota_cache()
        d = df.iloc[:t]
        fb = run_filter_search_bt(d, filtri=[], **param)
        est = esiti_trade(fb.trades(), d, fb.pip_size, costi["commission"])
        cp = confidenza_rolling(d, est, 1)
        a = cp["pips_medi"].to_numpy()
        b = conf_l["pips_medi"].iloc[:t].to_numpy()
        ok &= np.allclose(np.nan_to_num(a, nan=-99), np.nan_to_num(b, nan=-99))
    svuota_cache()
    check("15. nessun lookahead nella catena intera (backtest -> esiti -> confidenza), 3 tagli", ok)

    nomi = registra_filtro_confidenza([0.0, 0.5], conf_long=conf_l, conf_short=conf_s)
    check("16. registrazione: una coppia per soglia",
          nomi == ["CONF_PIPS_MEDI_0_L", "CONF_PIPS_MEDI_0_S",
                   "CONF_PIPS_MEDI_0.5_L", "CONF_PIPS_MEDI_0.5_S"], str(nomi))

    split = int(n * 0.8)
    df_is, df_oos = df.iloc[:split], df.iloc[split:]
    fs = run_filter_search_bt(df_is, filtri=nomi, **param)
    righe = set(fs.risultati["filtro"])
    check("17. nella grid search dei filtri ogni soglia e' UNA riga (coppia)",
          righe == {BASELINE, "CONF_PIPS_MEDI_0", "CONF_PIPS_MEDI_0.5"}, str(sorted(righe)))

    m = fs.risultati.set_index("filtro")
    tenuti = m.loc["CONF_PIPS_MEDI_0", "n_tenuti"]
    base_is = run_filter_search_bt(df_is, filtri=[], **param).trades()
    e_is = esiti_trade(base_is, df, fs.pip_size, costi["commission"])
    attesi = sum(
        int((c["pips_medi"].to_numpy()[e_is.loc[e_is["lato"] == lato, "barra_segnale"]] > 0).sum())
        for c, lato in ((conf_l, 1), (conf_s, -1)))
    check("18. i trade tenuti sono quelli con confidenza > soglia alla barra del segnale",
          tenuti == attesi, f"{tenuti} tenuti, attesi {attesi}")

    oos = run_filter_search_bt(df_oos, filtri=nomi[:2], **param)
    check("19. lo stesso filtro gira sull'OOS senza ricalcoli",
          len(oos.risultati) == 2 and oos.risultati["trades"].min() > 0,
          f"trade OOS: {oos.risultati.set_index('filtro')['trades'].to_dict()}")

    conf_l2 = conf_l.copy()
    conf_l2["pips_medi"] = 100.0
    prima_n = len(list_filters())
    registra_filtro_confidenza([0.0, 0.5], conf_long=conf_l2, conf_short=conf_s)
    from engine.registry import get_filter
    tutto_vero = bool(get_filter("CONF_PIPS_MEDI_0_L")(df).all())
    check("20. rieseguire la registrazione aggiorna i valori senza doppioni",
          len(list_filters()) == prima_n and tutto_vero)
    registra_filtro_confidenza([0.0, 0.5], conf_long=conf_l, conf_short=conf_s)

    try:
        altro = mercato_sintetico("2025-01-01", "2025-02-01", seme=9)
        get_filter("CONF_PIPS_MEDI_0_L")(altro)
        errore = False
    except ValueError:
        errore = True
    check("21. su barre per cui la confidenza non e' calcolata il filtro si ferma con un errore",
          errore)

    # ----------------------------------------------------------- lettura --
    print("\nD · La lettura")
    rep = report_calibrazione(es, df, df_oos.index[0], conf_long=conf_l, conf_short=conf_s)
    check("22. report_calibrazione: di default niente righe OOS",
          set(rep["parte"]) == {"IS"} and len(rep) == 8)
    rep2 = report_calibrazione(es, df, df_oos.index[0], conf_long=conf_l, conf_short=conf_s,
                               mostra_oos=True)
    el_ = es[es["lato"] == 1]
    pos = el_["barra_segnale"].to_numpy()
    sel = (conf_l["etichetta"].to_numpy()[pos] == ETICHETTE_CELLA[3]) & \
          (df.index[pos] >= df_oos.index[0]) & ~np.isnan(conf_l["pips_medi"].to_numpy()[pos])
    riga = rep2[(rep2["parte"] == "OOS") & (rep2["lato"] == "long")
                & (rep2["cella"] == ETICHETTE_CELLA[3])].iloc[0]
    check("23. report_calibrazione: previsto e reale letti alla barra del segnale",
          riga["trade"] == sel.sum()
          and np.isclose(riga["pips_reali"], el_["pips_netti"].to_numpy()[sel].mean())
          and np.isclose(riga["pips_previsti"], conf_l["pips_medi"].to_numpy()[pos][sel].mean()))

    ax, tab = plot_oos_confidenza(oos.trades(), oos.trades("CONF_PIPS_MEDI_0"),
                                  oos.pip_size, costi["commission"])
    t_s = oos.trades()
    from engine.metriche import pips_per_trade
    _, netti = pips_per_trade(t_s, oos.pip_size, costi["commission"])
    netti = netti.to_numpy()[np.argsort(pd.DatetimeIndex(t_s["ExitTime"]).to_numpy(), kind="mergesort")]
    curva = np.r_[0.0, np.cumsum(netti)]
    dd = (np.maximum.accumulate(curva) - curva).max()
    r0 = tab.iloc[0]
    check("24. plot_oos_confidenza: trade, media, totale e drawdown giusti",
          r0["trade"] == len(netti) and np.isclose(r0["avg_trade_netto"], netti.mean())
          and np.isclose(r0["pips_totali"], netti.sum()) and np.isclose(r0["max_dd_pips"], dd)
          and len(ax.get_lines()) == 3,
          f"senza: {int(r0['trade'])} trade, dd {r0['max_dd_pips']:.1f} pips")

    # ------------------------------------------------ il filtro congelato --
    print("\nE · Il filtro scelto congelato dentro l'entry")

    register_filter("F_TEST_UP", direction=1, pair="T_CTX")(
        lambda d: d["Close"] > d["Close"].shift(20))
    register_filter("F_TEST_DOWN", direction=-1, pair="T_CTX")(
        lambda d: d["Close"] < d["Close"].shift(20))

    def stessi_trade(a, b):
        col = ["EntryTime", "ExitTime", "EntryPrice", "ExitPrice", "Size"]
        return len(a) == len(b) and len(a) > 0 and \
            a[col].reset_index(drop=True).equals(b[col].reset_index(drop=True))

    # coppia su un setup long + short
    fs_f = run_filter_search_bt(df_is, filtri=["F_TEST_UP", "F_TEST_DOWN"], **param)
    el_, es_ = congela_filtro(fs_f, "T_CTX")
    fb = run_filter_search_bt(df_is, **{**param, "entry_long": el_, "entry_short": es_}, filtri=[])
    check("25. coppia congelata: la baseline nuova ha gli STESSI trade della riga della coppia",
          (el_, es_) == ("T_RANDOM_LONG+F_TEST_UP", "T_RANDOM_SHORT+F_TEST_DOWN")
          and stessi_trade(fb.trades(), fs_f.trades("T_CTX")),
          f"{len(fb.trades())} trade, {el_} / {es_}")

    # setup solo long: la coppia si riduce al membro long, la riga prende il suo nome
    p_long = {**param, "entry_short": None}
    fs_lo = run_filter_search_bt(df_is, filtri=["F_TEST_UP", "F_TEST_DOWN"], **p_long)
    el_, es_ = congela_filtro(fs_lo, "F_TEST_UP")
    fb = run_filter_search_bt(df_is, **{**p_long, "entry_long": el_}, filtri=[])
    check("26. setup solo long (come E22 + F8): stessi trade della riga del filtro, short None",
          es_ is None and el_ == "T_RANDOM_LONG+F_TEST_UP"
          and stessi_trade(fb.trades(), fs_lo.trades("F_TEST_UP")),
          f"{len(fb.trades())} trade")

    # filtro singolo +1 su setup long + short: lo short resta com'e'
    fs_s = run_filter_search_bt(df_is, filtri=["F_TEST_UP"], **param)
    el_, es_ = congela_filtro(fs_s, "F_TEST_UP")
    fb = run_filter_search_bt(df_is, **{**param, "entry_long": el_, "entry_short": es_}, filtri=[])
    check("27. filtro long su setup long + short: short invariato, stessi trade della riga",
          es_ == "T_RANDOM_SHORT" and stessi_trade(fb.trades(), fs_s.trades("F_TEST_UP")))

    try:
        congela_filtro(fs_lo, "T_CTX")
        errore = False
    except ValueError as err:
        errore = "F_TEST_UP" in str(err)
    check("28. etichetta assente -> errore con l'elenco di quelle disponibili; None -> entry di fs",
          errore and congela_filtro(fs_lo, None) == ("T_RANDOM_LONG", None))

    n_prima = len(list_entries())
    ripetuto = congela_filtro(fs_lo, "F_TEST_UP")
    check("29. richiamarla non registra doppioni",
          ripetuto == ("T_RANDOM_LONG+F_TEST_UP", None) and len(list_entries()) == n_prima)

    intera = get_entry("T_RANDOM_LONG+F_TEST_UP")(df)
    ok = True
    for t in rng.integers(1000, n - 10, 5):
        ok &= get_entry("T_RANDOM_LONG+F_TEST_UP")(df.iloc[:t]).equals(intera.iloc[:t])
    check("30. nessun lookahead nell'entry congelata (5 tagli)", ok)

    # ------------------------------------------ solo confidenza nota --
    print("\nF · Le soglie si confrontano solo fra trade a confidenza nota")
    el_n, es_n = congela_confidenza_nota("T_RANDOM_LONG", "T_RANDOM_SHORT", conf_l, conf_s)
    raw_l = get_entry("T_RANDOM_LONG")(df).astype(bool)
    got_l = get_entry(el_n)(df)
    atteso = raw_l & conf_l["pips_medi"].notna()
    check("31. l'entry ristretta scatta solo dove la confidenza e' nota",
          el_n == "T_RANDOM_LONG+CONF_NOTA" and got_l.equals(atteso)
          and int(raw_l.sum()) > int(got_l.sum()) > 0,
          f"{int(raw_l.sum())} segnali -> {int(got_l.sum())} a confidenza nota")

    fs_n = run_filter_search_bt(df_is, filtri=nomi[:2],
                                **{**param, "entry_long": el_n, "entry_short": es_n})
    e_n = esiti_trade(fs_n.trades(), df, fs_n.pip_size, costi["commission"])
    note = np.where(e_n["lato"] == 1, conf_l["pips_medi"].to_numpy()[e_n["barra_segnale"]],
                    conf_s["pips_medi"].to_numpy()[e_n["barra_segnale"]])
    r0 = fs_n.risultati.set_index("filtro").loc["CONF_PIPS_MEDI_0"]
    sopra = int((note > 0).sum())
    check("32. baseline tutta a confidenza nota; tenuti = sopra soglia, scartati = sotto",
          not np.isnan(note).any() and r0["n_tenuti"] == sopra
          and r0["n_scartati"] == len(note) - sopra and r0["n_scartati"] > 0,
          f"baseline {len(note)} · tenuti {int(r0['n_tenuti'])} · scartati {int(r0['n_scartati'])}")

    n_prima = len(list_entries())
    ancora = congela_confidenza_nota("T_RANDOM_LONG", "T_RANDOM_SHORT", conf_l, conf_s)
    ok = True
    for t in rng.integers(3000, n - 10, 4):
        ok &= get_entry(el_n)(df.iloc[:t]).equals(got_l.iloc[:t])
    check("33. nessun doppione rieseguendo, nessun lookahead (4 tagli)",
          ancora == (el_n, es_n) and len(list_entries()) == n_prima and ok)

    try:
        congela_confidenza_nota("T_RANDOM_LONG", None, None, None)
        errore = False
    except ValueError:
        errore = True
    check("34. lato attivo senza tabella di confidenza -> errore; lato None resta None",
          errore and congela_confidenza_nota(None, "T_RANDOM_SHORT", None, conf_s)[0] is None)

    clear_registry()
    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
