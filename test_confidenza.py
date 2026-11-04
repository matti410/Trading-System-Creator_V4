"""
Suite di validazione di engine/confidenza.py.

Si lancia da terminale, dalla cartella del progetto:

    python test_confidenza.py

Non serve MetaTrader 5 e non serve nessun file di dati: usa un mercato
sintetico (random walk). Richiede backtesting==0.6.6 e il file
engine/volatility_features_engineering.py. Dura circa un minuto.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import warnings
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

from engine import confidenza as modulo_confidenza
from engine import registro_dataset as rd
from engine import vetrina as vt
from engine import vetrina_verifica as vt_verifica
from engine.collaudo_catalogo import mercato_sintetico
from engine.confidenza import (ETICHETTE_CELLA, asse_volatilita, cella_contesto,
                               congela_filtro, congela_confidenza_nota,
                               confidenza_rolling, esiti_trade, gap_trend,
                               plot_oos_confidenza, registra_filtro_confidenza,
                               report_calibrazione)
from engine.exchange import con_intervalli, file_funding, salva_csv, salva_funding
from engine.filter_search_bt import BASELINE, run_filter_search_bt
from engine.indicatori import (barre_mediana, barre_per_durata, cella_vol_trend, id_periodo,
                               periodo_ancora, regola_ancora)
from engine.livelli import (GIORNATA_FX, GIORNATA_UTC, giorno_fx, imposta_giornata, svuota_cache)
from engine.motore_veloce import comportamento_vecchio
from engine.quarantena import ROLLOVER_DEFAULT, imposta_rollover
from engine.registry import (clear_registry, get_entry, get_filter, list_entries, list_filters,
                             register_entry, register_filter)

from test_atlante import Mercato, _deriva_dopo, _indice, _registra_entry

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


def _gap_vecchio(df):
    """Il gap_trend di prima del 04/11/2026, congelato: sempre dalla giornata (giorno_fx)."""
    giorno = giorno_fx(df)
    close = df["Close"].astype(float)
    tipico = (df["High"] + df["Low"] + df["Close"]) / 3
    vol = df["Volume"].astype(float)
    cum_tpv = (tipico * vol).groupby(giorno).cumsum()
    cum_vol = vol.groupby(giorno).cumsum()
    vwap = cum_tpv / cum_vol.where(cum_vol > 0)
    i = close.groupby(giorno).cumcount().astype(float)
    somma_y = close.groupby(giorno).cumsum()
    somma_xy = (i * close).groupby(giorno).cumsum()
    n = i + 1
    somma_x = i * (i + 1) / 2
    somma_x2 = i * (i + 1) * (2 * i + 1) / 6
    denom = n * somma_x2 - somma_x ** 2
    pendenza = (n * somma_xy - somma_x * somma_y) / denom.where(denom != 0)
    intercetta = (somma_y - pendenza * somma_x) / n
    fitted = (intercetta + pendenza * i).where(i > 0, close)
    return (fitted - vwap).rename("aura_gap")


def _cella_vecchia(df, direzione):
    """La cella_contesto di prima del 04/11/2026, congelata: 20 e 500 barre, a qualunque timeframe."""
    vol = asse_volatilita(df, finestra_vol=20, finestra=500)
    allineato = _gap_vecchio(df) * direzione
    mediana = allineato.rolling(500, min_periods=500).median()
    trend = (allineato > mediana).astype(float).where(mediana.notna() & allineato.notna())
    return (2 * vol + trend).rename("cella")


def _serie_24_7(minuti, barre, seme=11, inizio="2021-03-03"):
    """Un random walk 24/7 come sugli exchange, sul timeframe voluto."""
    idx = pd.date_range(inizio, periods=barre, freq=f"{minuti}min", tz="UTC")
    g = np.random.default_rng(seme)
    sigma = 0.0004 * np.sqrt(minuti / 15)
    close = 30000.0 * np.exp(np.cumsum(g.normal(0, sigma, barre)))
    op = np.r_[30000.0, close[:-1]]
    return pd.DataFrame({"Open": op, "High": np.maximum(op, close) * (1 + np.abs(g.normal(0, sigma, barre))),
                         "Low": np.minimum(op, close) * (1 - np.abs(g.normal(0, sigma, barre))), "Close": close,
                         "Volume": g.integers(20, 2000, barre).astype(float)}, index=idx)


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
    print("\nC · Dentro al backtest (motore predefinito, «veloce»)")
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

    # ------------------------------------------------ l'unita' bp (22/10) --
    print("\nG · L'unita' che decide: bp (22/10/2026)")

    # caso a mano: due trade dell'1% a 7.000 e a 70.000, pip 1, niente commissione
    t_in = [df.index[1000], df.index[2000]]
    t_out = [df.index[1010], df.index[2010]]
    tr_mano = pd.DataFrame({"EntryTime": t_in, "ExitTime": t_out, "Size": [1.0, 1.0],
                            "EntryPrice": [7_000.0, 70_000.0], "ExitPrice": [7_070.0, 70_700.0]})
    em = esiti_trade(tr_mano, df, 1.0, 0.0, unita="bp")
    check("35. a mano: +1% a 7.000 e a 70.000 = 70 e 700 pips, 100 bp ciascuno; vinto uguale",
          np.allclose(em["pips_netti"], [70.0, 700.0]) and np.allclose(em["bp_netti"], [100.0, 100.0])
          and list(em["vinto"]) == [1, 1], f"bp {list(em['bp_netti'].round(6))}")

    c3 = np.flatnonzero(celle == 3)
    s1, s2 = int(c3[-300]), int(c3[-250])
    e_mano = pd.DataFrame({"barra_segnale": [s1, s2], "barra_uscita": [s1 + 5, s2 + 5],
                           "lato": [1, 1], "pips_netti": [70.0, 700.0], "vinto": [1, 1],
                           "bp_netti": [100.0, 100.0]})
    cm = confidenza_rolling(df, e_mano, 1, min_obs=2, unita="bp")
    dopo = c3[c3 >= s2 + 5]
    check("36. a mano: nella cella dei due trade bp_medi = 100, pips_medi = 385",
          len(dopo) > 0 and (cm["bp_medi"].iloc[dopo] == 100.0).all()
          and (cm["pips_medi"].iloc[dopo] == 385.0).all(), f"{len(dopo)} barre")

    # sul backtest vero: bp_netti = metriche.bp_per_trade, i pips non cambiano
    from engine.metriche import bp_per_trade
    es_bp = esiti_trade(tr, df, fs_base.pip_size, costi["commission"], unita="bp")
    _, bp_atteso = bp_per_trade(tr, fs_base.pip_size, costi["commission"])
    es_pips = esiti_trade(tr, df, fs_base.pip_size, costi["commission"], unita="pips")
    check("37. esiti_trade in bp: bp_netti = bp_per_trade; pips e vinto identici; "
          "unita='pips' = chiamata di prima",
          np.array_equal(es_bp["bp_netti"].to_numpy(), bp_atteso.to_numpy(dtype=float))
          and es_bp.drop(columns="bp_netti").equals(es) and es_pips.equals(es)
          and "bp_netti" not in es_pips.columns,
          f"bp medi {es_bp['bp_netti'].mean():+.3f}")

    conf_lb = confidenza_rolling(df, es_bp, 1, unita="bp")
    conf_sb = confidenza_rolling(df, es_bp, -1, unita="bp")
    elb = es_bp[es_bp["lato"] == 1].copy()
    elb["cella"] = celle[elb["barra_segnale"]]
    elb = elb.sort_values("barra_uscita", kind="mergesort")
    diff = 0.0
    for t in rng.integers(2000, n, 300):
        usciti = elb[elb["barra_uscita"] <= t].tail(500)
        g = usciti[usciti["cella"] == celle[t]]
        att = g["bp_netti"].mean() if (not np.isnan(celle[t]) and len(g) >= 30) else np.nan
        got = conf_lb["bp_medi"].iat[t]
        if np.isnan(att) != np.isnan(got):
            diff = np.inf
            break
        if not np.isnan(att):
            diff = max(diff, abs(att - got))
    check("38. bp_medi = media a forza bruta dei bp, stessa cella; colonne in pips identiche",
          diff < 1e-9 and conf_lb.drop(columns="bp_medi").equals(conf_l)
          and conf_lb["bp_medi"].isna().equals(conf_l["pips_medi"].isna())
          and confidenza_rolling(df, es, 1, unita="pips").equals(conf_l),
          f"scarto massimo {diff:.1e} su 300 barre")

    # il costo andata e ritorno in bp, a mano, dai costi di costi_storico
    from engine.confidenza import costo_andata_ritorno_bp, soglie_confidenza
    from engine.vetrina import costi_storico
    piatto = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    c_perp, _ = costi_storico("BINANCE_PERP_BTCUSDT", piatto.assign(Open=50_000.0, High=50_000.0,
                                                                     Low=50_000.0, Close=50_000.0))
    c_spot, _ = costi_storico("BYBIT_SPOT_ETHUSDT", piatto.assign(Open=2_000.0, High=2_000.0,
                                                                  Low=2_000.0, Close=2_000.0))
    # 25/10/2026 (docs/71, strada D): lo spread e' un passo al prezzo del trade, il costo si chiede barra
    # per barra con il Close; a prezzo fisso e' lo stesso numero di prima su ogni barra
    k_perp = costo_andata_ritorno_bp(c_perp, pd.Series(50_000.0, index=piatto.index))
    k_spot = costo_andata_ritorno_bp(c_spot, pd.Series(2_000.0, index=piatto.index))
    # perpetual Binance: 2 x 0,05% = 10 bp + un passo di 0,1 su 50.000 = 0,02 bp
    # spot Bybit:        2 x 0,10% = 20 bp + un passo di 0,01 su 2.000 = 0,05 bp
    check("39. costo andata e ritorno in bp, a mano: perpetual 10,02 bp, spot 20,05 bp",
          np.allclose(k_perp, 10.02, atol=1e-9) and np.allclose(k_spot, 20.05, atol=1e-9),
          f"perpetual {k_perp.iloc[0]:.4f} bp · spot {k_spot.iloc[0]:.4f} bp")

    nomi_bp = registra_filtro_confidenza([0.0, 0.5, 0.8], conf_long=conf_lb, conf_short=conf_sb,
                                         metrica="bp_medi", costo_bp=k_perp)
    tab_s = soglie_confidenza(nomi_bp).set_index("filtro")
    nomi_s = registra_filtro_confidenza([0.5], conf_short=conf_sb, metrica="bp_medi",
                                        costo_bp=k_spot, prefisso="CONFSPOT")
    soglia_spot = soglie_confidenza(nomi_s)["soglia"].iat[0]
    check("40. soglia in bp = multiplo x costo, a mano: 0,5 x 10,02 = 5,01; 0,8 x 10,02 = 8,016; "
          "0,5 x 20,05 = 10,025",
          nomi_bp == ["CONF_BP_MEDI_0C_L", "CONF_BP_MEDI_0C_S", "CONF_BP_MEDI_0.5C_L",
                      "CONF_BP_MEDI_0.5C_S", "CONF_BP_MEDI_0.8C_L", "CONF_BP_MEDI_0.8C_S"]
          and np.isclose(tab_s.loc["CONF_BP_MEDI_0.5C", "soglia"], 5.01)
          and np.isclose(tab_s.loc["CONF_BP_MEDI_0.8C", "soglia"], 8.016)
          and tab_s.loc["CONF_BP_MEDI_0C", "soglia"] == 0.0
          and nomi_s == ["CONFSPOT_BP_MEDI_0.5C_S"] and np.isclose(soglia_spot, 10.025),
          " · ".join(f"{k} {v:.3f} bp" for k, v in tab_s["soglia"].items()))

    # sul mercato sintetico i bp medi stanno intorno a -1: sopra 5,01 bp quasi nessuna barra,
    # la divisione non banale si chiede alla soglia 0
    vero0 = get_filter("CONF_BP_MEDI_0C_L")(df)
    vero5 = get_filter("CONF_BP_MEDI_0.5C_L")(df)
    note_l = int(conf_lb["bp_medi"].notna().sum())
    check("41. il filtro in bp e' vero solo dove bp_medi > multiplo x costo (NaN = falso)",
          vero0.equals((conf_lb["bp_medi"] > 0.0).fillna(False).astype(bool))
          and vero5.equals((conf_lb["bp_medi"] > 0.5 * k_perp).fillna(False).astype(bool))
          and 0 < int(vero0.sum()) < note_l,
          f"su {note_l} barre note: {int(vero0.sum())} sopra 0 bp, {int(vero5.sum())} sopra 5,01 bp")

    fs_b = run_filter_search_bt(df_is, filtri=nomi_bp[:4], **param, unita="bp")
    mb = fs_b.risultati.set_index("filtro")
    base_b = run_filter_search_bt(df_is, filtri=[], **param, unita="bp").trades()
    e_b = esiti_trade(base_b, df, fs_b.pip_size, costi["commission"], unita="bp")
    ok = set(mb.index) == {BASELINE, "CONF_BP_MEDI_0C", "CONF_BP_MEDI_0.5C"}
    for etichetta, mult in (("CONF_BP_MEDI_0C", 0.0), ("CONF_BP_MEDI_0.5C", 0.5)):
        attesi = sum(
            int((c["bp_medi"].to_numpy()[e_b.loc[e_b["lato"] == lato, "barra_segnale"]]
                 > mult * float(k_perp.iloc[0])).sum())   # prezzo fisso: lo stesso costo su ogni barra
            for c, lato in ((conf_lb, 1), (conf_sb, -1)))
        ok &= mb.loc[etichetta, "n_tenuti"] == attesi
    check("42. nella ricerca dei filtri: tenuti = trade con bp_medi > multiplo x costo al segnale",
          ok, f"tenuti 0C {int(mb.loc['CONF_BP_MEDI_0C', 'n_tenuti'])} · "
              f"0.5C {int(mb.loc['CONF_BP_MEDI_0.5C', 'n_tenuti'])}")

    ok = True
    for t in rng.integers(n // 3, n - 200, 2):
        svuota_cache()
        d = df.iloc[:t]
        fb = run_filter_search_bt(d, filtri=[], **param)
        est = esiti_trade(fb.trades(), d, fb.pip_size, costi["commission"], unita="bp")
        a = confidenza_rolling(d, est, 1, unita="bp")["bp_medi"].to_numpy()
        b = conf_lb["bp_medi"].iloc[:t].to_numpy()
        ok &= np.allclose(np.nan_to_num(a, nan=-99), np.nan_to_num(b, nan=-99))
    svuota_cache()
    check("43. nessun lookahead nella catena in bp (backtest -> esiti -> confidenza), 2 tagli", ok)

    errori = 0
    for prova in (lambda: esiti_trade(tr, df, fs_base.pip_size, unita="atr"),
                  lambda: confidenza_rolling(df, es, 1, unita="bp"),
                  lambda: registra_filtro_confidenza([0.5], conf_long=conf_lb, metrica="bp_medi"),
                  lambda: registra_filtro_confidenza([0.5], conf_long=conf_l, metrica="bp_medi",
                                                     costo_bp=10.0),
                  lambda: registra_filtro_confidenza([0.5], conf_long=conf_l, costo_bp=10.0),
                  lambda: report_calibrazione(es, df, df_oos.index[0], conf_long=conf_l, unita="bp")):
        try:
            prova()
        except ValueError:
            errori += 1
    check("44. errori chiari: unita' sconosciuta, bp senza bp_netti / bp_medi / costo, "
          "costo con i pips", errori == 6, f"{errori}/6 errori")

    rep_b = report_calibrazione(es_bp, df, df_oos.index[0], conf_long=conf_lb, conf_short=conf_sb,
                                mostra_oos=True, unita="bp")
    elb_ = es_bp[es_bp["lato"] == 1]
    pos = elb_["barra_segnale"].to_numpy()
    sel = (conf_lb["etichetta"].to_numpy()[pos] == ETICHETTE_CELLA[3]) & \
          (df.index[pos] >= df_oos.index[0]) & ~np.isnan(conf_lb["bp_medi"].to_numpy()[pos])
    riga = rep_b[(rep_b["parte"] == "OOS") & (rep_b["lato"] == "long")
                 & (rep_b["cella"] == ETICHETTE_CELLA[3])].iloc[0]
    check("45. report_calibrazione in bp: bp previsti e reali alla barra del segnale; "
          "le colonne in pips identiche",
          np.isclose(riga["bp_reali"], elb_["bp_netti"].to_numpy()[sel].mean())
          and np.isclose(riga["bp_previsti"], conf_lb["bp_medi"].to_numpy()[pos][sel].mean())
          and rep_b.drop(columns=["bp_previsti", "bp_reali"]).equals(rep2))

    ax_b, tab_b = plot_oos_confidenza(oos.trades(), oos.trades("CONF_PIPS_MEDI_0"),
                                      oos.pip_size, costi["commission"], unita="bp")
    _, bp_oos = bp_per_trade(oos.trades(), oos.pip_size, costi["commission"])
    check("46. plot_oos_confidenza in bp: curva, totale e drawdown in pips identici, media in bp accanto",
          tab_b.drop(columns="avg_trade_netto_bp").equals(tab)
          and np.isclose(tab_b["avg_trade_netto_bp"].iat[0], bp_oos.mean()),
          f"senza: {tab_b['avg_trade_netto_bp'].iat[0]:+.3f} bp per trade")

    # ================================================= docs/80 e docs/81, 04/11/2026 ==
    print("\nH · Le finestre in ore (docs/80, lavoro 1): prima sul broker, con la giornata FX")
    check("47. M15 broker: cella_contesto = la formula di prima, bit per bit, sui due lati",
          cella_contesto(df, 1).equals(_cella_vecchia(df, 1)) and cella_contesto(df, -1).equals(_cella_vecchia(df, -1))
          and gap_trend(df).equals(_gap_vecchio(df)))

    originale = modulo_confidenza.cella_contesto
    conf_nuova = {u: confidenza_rolling(df, es_bp, 1, unita=u) for u in ("pips", "bp")}
    nomi_nuovi = registra_filtro_confidenza([0.0, 0.5], conf_long=conf_nuova["pips"], prefisso="CONFN")
    maschere_nuove = {n: get_filter(n)(df).to_numpy() for n in nomi_nuovi}
    modulo_confidenza.cella_contesto = lambda d, direzione, **k: _cella_vecchia(d, direzione)
    try:
        conf_vecchia = {u: confidenza_rolling(df, es_bp, 1, unita=u) for u in ("pips", "bp")}
    finally:
        modulo_confidenza.cella_contesto = originale
    registra_filtro_confidenza([0.0, 0.5], conf_long=conf_vecchia["pips"], prefisso="CONFV")
    maschere_vecchie = {n: get_filter(n.replace("CONFN", "CONFV"))(df).to_numpy() for n in nomi_nuovi}
    check("48. M15 broker: confidenza e filtri CONF_ = quelli di prima, bit per bit, in pips e in bp",
          conf_nuova["pips"].equals(conf_vecchia["pips"]) and conf_nuova["bp"].equals(conf_vecchia["bp"])
          and all(np.array_equal(maschere_nuove[n], maschere_vecchie[n]) for n in nomi_nuovi))

    # il broker sospeso: H4 e D1 ricavate dalle M15, con i fine settimana vuoti; basta che non si rompa
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    br = {tf: df.resample(r).agg(agg).dropna(subset=["Close"]) for tf, r in (("H4", "4h"), ("D1", "1D"))}
    celle_br = {tf: cella_contesto(d, 1) for tf, d in br.items()}
    ny = br["H4"].index.tz_convert("America/New_York")
    prime = np.r_[False, np.diff(periodo_ancora(br["H4"]).to_numpy()) == 1]
    check("49. broker (sospeso): H4 e D1 non si rompono, con le quattro celle; su H4 la settimana riparte "
          "la domenica sera o il lunedi' di New York",
          all(set(c.dropna().unique()) == {0.0, 1.0, 2.0, 3.0} for c in celle_br.values())
          and set(ny[prime].dayofweek) <= {6, 0}, f"giorni di ripartenza {sorted(set(ny[prime].dayofweek))}")

    imposta_rollover(None)
    imposta_giornata(GIORNATA_UTC)
    svuota_cache()
    TF = {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
    BARRE = {"M5": 12000, "M15": 6000, "M30": 3000, "H1": 3000, "H4": 3000, "D1": 2000}
    serie = {tf: _serie_24_7(m, BARRE[tf]) for tf, m in TF.items()}
    attese = {"M5": (60, 1500), "M15": (20, 500), "M30": (20, 250), "H1": (20, 125), "H4": (20, 210), "D1": (20, 150)}
    trovate = {tf: (barre_per_durata(d.index, 5), barre_mediana(d.index)) for tf, d in serie.items()}
    check("50. deviazione e mediana in barre: la tabella di docs/81 §1", trovate == attese, str(trovate))
    prima_cella = {tf: int(np.flatnonzero(cella_contesto(d, 1).notna().to_numpy())[0]) for tf, d in serie.items()}
    check("51. prima cella calcolabile: deviazione + mediana - 1 barre, su ogni timeframe",
          prima_cella == {tf: a + b - 1 for tf, (a, b) in attese.items()}, str(prima_cella))
    ore_coperte = {tf: (attese[tf][0] * m / 60, attese[tf][1] * m / 60) for tf, m in TF.items()}
    check("52. M5 copre le stesse ore di M15 (5 e 125); H1 la stessa mediana, ma la deviazione a 20 ore "
          "per il minimo di 20 barre (docs/81 §1)",
          ore_coperte["M5"] == ore_coperte["M15"] == (5.0, 125.0) and ore_coperte["H1"] == (20.0, 125.0))
    d15 = serie["M15"]
    check("53. M15 exchange: cella_contesto = la formula di prima, bit per bit, sui due lati",
          cella_contesto(d15, 1).equals(_cella_vecchia(d15, 1)) and cella_contesto(d15, -1).equals(_cella_vecchia(d15, -1)))
    d5 = serie["M5"]
    check("54. su M5 la confidenza non usa piu' le 20 e 500 barre di M15: la cella e' quella in ore",
          cella_contesto(d5, 1).equals(cella_vol_trend(d5, 1)) and not cella_contesto(d5, 1).equals(_cella_vecchia(d5, 1)))
    e_d5 = _esiti_finti(len(d5), 400, np.random.default_rng(5))
    check("55. confidenza_rolling legge la cella in ore: la colonna cella e' cella_vol_trend",
          np.array_equal(confidenza_rolling(d5, e_d5, 1)["cella"].to_numpy(), cella_vol_trend(d5, 1).to_numpy(), equal_nan=True))
    lunga = cella_contesto(d15, 1, ore_mediana=250)
    check("56. i parametri ore e ore_mediana arrivano alle finestre (250 ore su M15: 1.000 barre)",
          int(np.flatnonzero(lunga.notna().to_numpy())[0]) == 20 + 1000 - 1)
    errori_vecchi = 0
    for kw in ({"finestra": 500}, {"finestra_vol": 20}):
        try:
            confidenza_rolling(d15, e_d5, 1, **kw)
        except TypeError:
            errori_vecchi += 1
    check("57. i parametri vecchi in barre non si accettano piu' in silenzio", errori_vecchi == 2)

    print("\nI · L'ancora secondo il timeframe (docs/80, lavoro 2)")
    regole = {tf: regola_ancora(d.index) for tf, d in serie.items()}
    check("58. la regola: fino a H1 la giornata, H4 la settimana, D1 il mese",
          regole == {"M5": "D", "M15": "D", "M30": "D", "H1": "D", "H4": "W", "D1": "M"}, str(regole))
    idx_lunghi = {"H2": 120, "H8": 480, "H12": 720}
    regole_altre = {k: regola_ancora(pd.date_range("2024-01-01", periods=9, freq=f"{m}min", tz="UTC"))
                    for k, m in idx_lunghi.items()}
    try:
        regola_ancora(pd.date_range("2024-01-01", periods=9, freq="7D", tz="UTC"))
        settimanale = False
    except ValueError:
        settimanale = True
    check("59. la regola e' generale (H2, H8 settimana; H12 mese); una barra settimanale si ferma con un errore",
          regole_altre == {"H2": "W", "H8": "W", "H12": "M"} and settimanale, str(regole_altre))
    fino_h1 = all(gap_trend(serie[tf]).equals(_gap_vecchio(serie[tf])) for tf in ("M5", "M15", "M30", "H1"))
    check("60. fino a H1 gap_trend e' identico al bit a quello di prima", fino_h1)
    check("61. su H4 e D1 il gap cambia per costruzione",
          not gap_trend(serie["H4"]).equals(_gap_vecchio(serie["H4"]))
          and not gap_trend(serie["D1"]).equals(_gap_vecchio(serie["D1"])))
    d4, d1 = serie["H4"], serie["D1"]
    per4, per1 = periodo_ancora(d4).to_numpy(), periodo_ancora(d1).to_numpy()
    nuove4 = d4.index[np.r_[False, np.diff(per4) == 1]]
    nuove1 = d1.index[np.r_[False, np.diff(per1) == 1]]
    check("62. su H4 si riparte al lunedi' alle 00:00 UTC, con 42 barre a settimana piena",
          (nuove4.dayofweek == 0).all() and (nuove4.hour == 0).all()
          and np.array_equal(per4, id_periodo(d4, "W")) and (np.bincount(per4)[1:-1] == 42).all(),
          f"{len(nuove4)} ripartenze")
    giorni_mese = np.bincount(per1)[1:-1]
    check("63. su D1 si riparte il giorno 1 del mese, con 28-31 barre",
          (nuove1.day == 1).all() and giorni_mese.min() >= 28 and giorni_mese.max() <= 31,
          f"da {giorni_mese.min()} a {giorni_mese.max()} barre")
    scarti = {}
    for tf, d, per in (("H4", d4, per4), ("D1", d1, per1)):
        tipico_p = ((d["High"] + d["Low"] + d["Close"]) / 3).to_numpy()
        vol_p, close_p = d["Volume"].to_numpy(), d["Close"].to_numpy()
        att = np.full(len(d), np.nan)
        for g in np.unique(per):
            ii = np.flatnonzero(per == g)
            att[ii] = _regressione_ciclo(close_p[ii]) - np.cumsum(tipico_p[ii] * vol_p[ii]) / np.cumsum(vol_p[ii])
        scarti[tf] = float(np.nanmax(np.abs(gap_trend(d).to_numpy() - att)))
    check("64. gap vettoriale = regressione a ciclo del file originale, per settimana e per mese",
          max(scarti.values()) < 1e-8, str({k: f"{v:.1e}" for k, v in scarti.items()}))
    diversi = []
    for tf in ("M5", "H4", "D1"):
        d = serie[tf]
        piena = {lato: cella_contesto(d, lato) for lato in (1, -1)}
        for t in (len(d) // 3, len(d) // 2, len(d) - 11):
            for lato in (1, -1):
                if not np.array_equal(cella_contesto(d.iloc[:t], lato).to_numpy(), piena[lato].iloc[:t].to_numpy(),
                                      equal_nan=True):
                    diversi.append((tf, t, lato))
    check("65. nessun lookahead: tagliato lo storico le celle non cambiano (M5, H4, D1; 3 tagli, due lati)",
          not diversi, str(diversi))
    corto = d4.iloc[:1]
    check("66. una barra sola: gap_trend non si ferma (Close meno prezzo tipico)",
          np.isclose(gap_trend(corto).iloc[0], corto["Close"].iloc[0] - (corto["High"] + corto["Low"] + corto["Close"]).iloc[0] / 3))

    print("\nL · La confidenza dai trade del motore veloce (docs/81 §4, domanda 4)")
    clear_registry()
    dv = _serie_24_7(15, 12000, seme=21)
    segnali_v = pd.Series(np.random.default_rng(22).random(len(dv)), index=dv.index)
    register_entry("V_LONG", 1)(lambda d: (segnali_v.reindex(d.index) < 0.03))
    register_entry("V_SHORT", -1)(lambda d: (segnali_v.reindex(d.index) > 0.97))
    costi_v = {"spread": 0.0, "commission": 0.0005, "spread_passo_pips": 1.0}
    param_v = dict(entry_long="V_LONG", entry_short="V_SHORT", n_barre=8, perc_sl=20.0, perc_tp=0.0,
                   unita="bp", pip_size=1.0, cash=10_000_000, **costi_v, verbose=False)
    fv = run_filter_search_bt(dv, filtri=[], motore="veloce", **param_v)
    tv = fv.trades()
    ev = esiti_trade(tv, dv, fv.pip_size, costi_v["commission"], unita="bp")
    stessa_barra = ev[ev["barra_uscita"] == ev["barra_segnale"] + 1]
    check("67. esiti dal veloce: segnale = ingresso - 1; ci sono trade usciti sulla barra d'ingresso",
          (dv.index[ev["barra_segnale"] + 1] == pd.DatetimeIndex(tv["EntryTime"])).all() and len(stessa_barra) > 0,
          f"{len(ev)} trade, {len(stessa_barra)} usciti sulla barra d'ingresso")
    conf_v = confidenza_rolling(dv, ev, 1, min_obs=1, unita="bp")
    celle_v = conf_v["cella"].to_numpy()
    lato_l = ev[ev["lato"] == 1].sort_values("barra_uscita", kind="mergesort")
    ok_bruta = True
    for t in np.random.default_rng(23).integers(1000, len(dv) - 1, 200):
        if np.isnan(celle_v[t]):
            continue
        usciti = lato_l[lato_l["barra_uscita"] <= t].tail(500)
        attesi = int((celle_v[usciti["barra_segnale"].to_numpy()] == celle_v[t]).sum())
        ok_bruta &= conf_v["n_storia"].iat[t] == attesi
    # un trade uscito sulla barra d'ingresso, con la stessa cella al segnale e all'uscita
    candidati = stessa_barra[(stessa_barra["lato"] == 1)
                             & (celle_v[stessa_barra["barra_segnale"].to_numpy()]
                                == celle_v[stessa_barra["barra_uscita"].to_numpy()])]
    rx = int(candidati.iloc[-1]["barra_uscita"])
    conf_cum = confidenza_rolling(dv, ev, 1, min_obs=1, finestra_trade=len(ev) + 1, unita="bp")
    nella_cella = lato_l[lato_l["barra_segnale"].map(lambda p: celle_v[int(p)] == celle_v[rx])]
    entro = int((nella_cella["barra_uscita"] <= rx).sum())
    prima_di = int((nella_cella["barra_uscita"] <= rx - 1).sum())
    check("68. un trade uscito sulla barra d'ingresso entra nella storia da quella barra, non prima "
          "(storia contata a mano su 200 barre)",
          ok_bruta and conf_cum["n_storia"].iat[rx] == entro and entro > prima_di)
    ok_tagli = True
    for t in (len(dv) // 2, len(dv) * 3 // 4):
        svuota_cache()
        dt = dv.iloc[:t]
        fb = run_filter_search_bt(dt, filtri=[], motore="veloce", **param_v)
        est = esiti_trade(fb.trades(), dt, fb.pip_size, costi_v["commission"], unita="bp")
        ok_tagli &= np.allclose(np.nan_to_num(confidenza_rolling(dt, est, 1, unita="bp")["bp_medi"].to_numpy(), nan=-99),
                                np.nan_to_num(confidenza_rolling(dv, ev, 1, unita="bp")["bp_medi"].iloc[:t].to_numpy(), nan=-99))
    svuota_cache()
    check("69. nessun lookahead nella catena con motore=\"veloce\" (backtest -> esiti -> confidenza), 2 tagli", ok_tagli)
    param_c = dict(param_v)
    param_c.update(spread=0.00001, spread_passo_pips=None, perc_sl=90.0)
    with comportamento_vecchio():
        fw = run_filter_search_bt(dv, filtri=[], motore="veloce", **param_c)
        conf_w = confidenza_rolling(dv, esiti_trade(fw.trades(), dv, fw.pip_size, costi_v["commission"], unita="bp"), 1,
                                    unita="bp")
    fb_bt = run_filter_search_bt(dv, filtri=[], motore="bt", **param_c)
    conf_bt = confidenza_rolling(dv, esiti_trade(fb_bt.trades(), dv, fb_bt.pip_size, costi_v["commission"], unita="bp"), 1,
                                 unita="bp")
    check("70. con comportamento_vecchio() la confidenza dal veloce e' identica al bit a quella da «bt»",
          conf_w.equals(conf_bt), f"{int(conf_bt['bp_medi'].notna().sum())} barre a confidenza nota")
    orari = pd.date_range(dv.index[0].floor("8h"), dv.index[-1].ceil("8h"), freq="8h", name="Date").as_unit("ns")
    funding_v = con_intervalli(pd.DataFrame({"tasso": 0.0002}, index=orari))
    fz = run_filter_search_bt(dv, filtri=[], motore="veloce", funding=funding_v, **param_v)
    tz = fz.trades()
    ez = esiti_trade(tz, dv, fz.pip_size, costi_v["commission"], unita="bp")
    riga_z = fz.risultati.iloc[0]
    check("71. CostoExtraPips e funding nei netti: pips e bp degli esiti = la tabella dei filtri; funding contato",
          tz["CostoExtraPips"].abs().sum() > 0 and tz["FundingPips"].abs().sum() > 0
          and np.isclose(ez["bp_netti"].mean(), riga_z["avg_trade_netto"])
          and np.isclose(ez["pips_netti"].mean(), riga_z["avg_trade_netto_pips"]),
          f"{ez['bp_netti'].mean():+.3f} bp, {ez['pips_netti'].mean():+.3f} pips per trade")

    # ======================================================== la 5b del Lab (docs/81 §3) ==
    print("\nM · La cella 5b del Lab e la 6 con una soglia")
    clear_registry()
    rd.azzera()
    M_ = Mercato(_indice(giorni=300), seme=31)
    n_m = len(M_.idx)
    g_m = np.random.default_rng(32)
    # long nei giorni pari, short nei dispari, con un movimento dopo il segnale che paga i costi: la confidenza
    # sopra lo zero deve esistere, per provare la 6 con una soglia. Come test_riordino_lab
    giorno_m = (np.arange(n_m) // 96) % 2
    adatte = np.arange(600, n_m - 50, 4)
    pos_l = np.sort(g_m.choice(adatte[giorno_m[adatte] == 0], size=1800, replace=False))
    pos_s = np.sort(g_m.choice(adatte[giorno_m[adatte] == 1], size=1800, replace=False))
    d_m = M_.df(_deriva_dopo(n_m, pos_l, np.full(pos_l.size, 0.0002))
                + _deriva_dopo(n_m, pos_s, np.full(pos_s.size, -0.0002)))
    d_m[["Open", "High", "Low", "Close"]] *= 300.0
    _registra_entry("T_L", 1, M_.idx[pos_l])
    _registra_entry("T_S", -1, M_.idx[pos_s])
    register_filter("F_MATTINA", direction=0)(lambda d: pd.Series(d.index.hour < 12, index=d.index))
    register_filter("F_SERA", direction=0)(lambda d: pd.Series(d.index.hour >= 12, index=d.index))
    register_filter("F_PARI", direction=0)(lambda d: pd.Series(d.index.day % 2 == 0, index=d.index))
    SYM = "BINANCE_PERP_BTCUSDT"
    orari_m = pd.date_range(d_m.index[0].floor("8h"), d_m.index[-1].ceil("8h"), freq="8h")
    fund_m = con_intervalli(pd.DataFrame({"tasso": 0.0001}, index=orari_m))

    def muto(f, *a, **k):
        with contextlib.redirect_stdout(io.StringIO()):
            return f(*a, **k)

    def parlato(f, *a, **k):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r_ = f(*a, **k)
        return r_, buf.getvalue()

    def rifiuta(f, testo):
        try:
            muto(f)
        except ValueError as e:
            return testo in str(e)
        return False

    def conto(s_):
        return {k_: (dict(v_) if isinstance(v_, dict) else v_) for k_, v_ in s_.prove.items()}

    with tempfile.TemporaryDirectory() as tmp:
        salva_csv(d_m, os.path.join(tmp, f"{SYM}_M15.csv"))
        salva_funding(fund_m, file_funding(SYM, tmp))
        s = muto(vt.prepara, SYM, H=8, cartella=tmp)
        muto(vt.esplora, s)
        muto(vt.scegli_trigger, s, long="T_L", short="T_S")
        muto(vt.imposta_uscite, s, 8, 8, 90, 0)
        muto(vt.trova_strategia, s)
        n_is = int(s.df.index.searchsorted(s.df_oos.index[0]))

        # la 6 senza la 5b, il riferimento delle prove d'identita' dentro la sessione
        tab_senza = muto(vt.scheda, s, None)
        tr_senza = (s.trades_is.copy(), s.trades_oos.copy())
        s.filtro = s.oos = s.trades_is = s.trades_oos = None

        chiamate = []
        vero_motore = vt.run_filter_search_bt
        vt.run_filter_search_bt = lambda *a, **k: (chiamate.append(1), vero_motore(*a, **k))[1]
        prima = conto(s)
        diario_0 = len(s.storia.diario)
        try:
            r0, t0 = parlato(vt.confidenza_strategia, s)
        finally:
            vt.run_filter_search_bt = vero_motore
        check("72. 5b spenta (il default): nessun backtest, nessuna prova, una riga che lo dice",
              r0 is None and not chiamate and conto(s) == prima and s.conf is None and "Confidenza spenta" in t0)

        tab, t1 = parlato(vt.confidenza_strategia, s, usa=True)
        chiave_lab = vt.chiave_confidenza(vt._chiave_filtri(s), (0.0, 0.5, 0.8), None)
        nomi_soglie = list(tab["Soglia"])[1:]
        check("73. 5b accesa: baseline e 3 soglie fisse, i nomi in multipli del costo, in bp",
              nomi_soglie == ["CONF_BP_MEDI_0C", "CONF_BP_MEDI_0.5C", "CONF_BP_MEDI_0.8C"]
              and modulo_confidenza.SOGLIE_CONFIDENZA == (0.0, 0.5, 0.8) and tab["Vale (bp)"].iloc[1] == 0.0
              and tab["Vale (bp)"].iloc[2] > 0 and tab["Vale (bp)"].iloc[3] > tab["Vale (bp)"].iloc[2], str(nomi_soglie))
        check("74. il conto: la voce della 3.3 con 3 prove, scritta una volta; la riga delle prove lo dice",
              s.prove["filtri"].get(chiave_lab) == 3 and "questa schermata: 3 soglie della confidenza" in t1
              and {k_: v_ for k_, v_ in conto(s)["filtri"].items() if k_ != chiave_lab} == prima["filtri"])
        chiave_ricerca = vt.chiave_confidenza(
            vt.chiave_filtri(("T_L",), ("T_S",), vt.impostazioni_uscite(8, 8, 90.0, 0.0, None), "Long + Short"),
            [0.0, 0.5, 0.8], None)
        storia_finta = SimpleNamespace(prove={"filtri": {}})
        ricerca_finta = SimpleNamespace(risultati=pd.DataFrame({"filtro": [BASELINE, "a", "b", "c"]}))
        vt.conta_filtri(storia_finta, ricerca_finta, ["T_L"], ["T_S"], 8, 90.0, 0.0, None, "Long + Short",
                        confidenza=([0.0, 0.5, 0.8], None))
        check("75. stesso setup nel Lab e nella ricerca: la stessa chiave, quindi conta una volta",
              chiave_ricerca == chiave_lab and list(storia_finta.prove["filtri"]) == [chiave_lab])
        tab_prima = tab.copy()
        cal_prima = s.tabelle["confidenza_calibrazione"].copy()
        conto_1 = conto(s)
        tab2 = muto(vt.confidenza_strategia, s, usa=True)
        check("76. rifatta uguale: +0 prove, la stessa tabella", conto(s) == conto_1 and tab2.equals(tab_prima))
        tab_mattina = muto(vt.confidenza_strategia, s, usa=True, filtro="F_MATTINA")
        chiave_m = vt.chiave_confidenza(vt._chiave_filtri(s), (0.0, 0.5, 0.8), "F_MATTINA")
        check("77. con un altro filtro: +3 prove, con la sua chiave; altri numeri",
              s.prove["filtri"].get(chiave_m) == 3 and not tab_mattina.equals(tab_prima)
              and tab_mattina["Trade"].iloc[0] < tab_prima["Trade"].iloc[0])
        muto(vt.confidenza_strategia, s, usa=True, filtro="F_MATTINA, F_PARI")
        chiave_due = vt.chiave_confidenza(vt._chiave_filtri(s), (0.0, 0.5, 0.8), "F_MATTINA + F_PARI")
        n_filtri_5 = int((s.fs.risultati["filtro"] != BASELINE).sum())
        check("77b. con due filtri in catena: la chiave li nomina tutti e due, e c'e' la voce delle combinazioni della 6",
              s.prove["filtri"].get(chiave_due) == 3 and s.conf.filtri == ["F_MATTINA", "F_PARI"]
              and s.prove["combinazioni"].get((vt._chiave_filtri(s), 2)) == n_filtri_5 * (n_filtri_5 - 1) // 2,
              f"{n_filtri_5} filtri alla 5; {s.prove['filtri'].get(chiave_due)}; {dict(s.prove['combinazioni'])}")
        tab3 = muto(vt.confidenza_strategia, s, usa=True)
        check("78. di nuovo senza filtro: la tabella e la calibrazione di prima (la cache non tiene maschere vecchie)",
              tab3.equals(tab_prima) and s.tabelle["confidenza_calibrazione"].equals(cal_prima))
        check("79. la 5b resta nell'in-sample: out-of-sample non aperto, diario invariato, niente dati dopo il confine",
              s.oos is None and s.trades_oos is None and len(s.storia.diario) == diario_0
              and s.conf.fs.trades()["ExitTime"].max() < s.df_oos.index[0])
        e_c = s.conf.esiti[(s.conf.esiti["barra_segnale"] < n_is) & (s.conf.esiti["barra_uscita"] < n_is)]
        cal_mano = modulo_confidenza.report_calibrazione(e_c, s.df, s.df_oos.index[0], conf_long=s.conf.conf_long,
                                                         conf_short=s.conf.conf_short, unita="bp")
        check("80. la calibrazione conta solo i trade chiusi nell'in-sample",
              set(cal_mano["parte"]) == {"IS"} and s.tabelle["confidenza_calibrazione"]["Trade"].sum() == cal_mano["trade"].sum()
              and s.tabelle["confidenza_calibrazione"]["Trade"].sum() <= len(e_c))
        risc = s.tabelle["confidenza_riscaldamento"]
        check("81. la riga del riscaldamento: quanti trade hanno una confidenza nota, e da quando",
              "Confidenza nota:" in t1 and "dal" in risc["testo"] and 0 < risc["note"] <= risc["tot"], risc["testo"])
        n_f = 2000
        idx_f = pd.date_range("2024-01-01", periods=n_f, freq="15min", tz="UTC")
        d_f = pd.DataFrame({"Close": 1.0}, index=idx_f)
        s_f = SimpleNamespace(df=d_f, df_is=d_f.iloc[:1500], df_oos=d_f.iloc[1500:], unita="bp")
        e_f = pd.DataFrame({"barra_segnale": [100, 900, 1000], "barra_uscita": [110, 910, 1010], "lato": [1, 1, 1]})
        c_f = pd.DataFrame({"bp_medi": np.r_[np.full(950, np.nan), np.ones(n_f - 950)]}, index=idx_f)
        r_tardi = vt._riscaldamento_confidenza(s_f, e_f, c_f, None)
        c_f2 = pd.DataFrame({"bp_medi": np.ones(n_f)}, index=idx_f)
        r_presto = vt._riscaldamento_confidenza(s_f, e_f, c_f2, None)
        check("82. riscaldamento a mano: nota oltre la meta' dell'in-sample = avviso; meno di 100 trade noti = avviso",
              r_tardi["tardi"] and r_tardi["pochi"] and r_tardi["note"] == 1 and r_tardi["tot"] == 3
              and not r_presto["tardi"] and r_presto["note"] == 3)
        prima_nulla = conto(s)
        vera_conf = vt.confidenza_rolling

        def conf_ignota(*a, **k):
            c_ = vera_conf(*a, **k)
            return c_.assign(pips_medi=np.nan, bp_medi=np.nan, win_rate=np.nan)
        vt.confidenza_rolling = conf_ignota
        try:
            r_n, t_n = parlato(vt.confidenza_strategia, s, usa=True, filtro="F_SERA")
        finally:
            vt.confidenza_rolling = vera_conf
        check("83. nessun segnale a confidenza nota: lo dice e si ferma, senza errori e senza prove",
              r_n is None and s.conf is None and conto(s) == prima_nulla and "Nessun segnale con una confidenza nota" in t_n)

        tab_id = muto(vt.scheda, s, None)
        check("84. la 6 senza soglia dopo la 5b: identica alla 6 senza 5b",
              s.trades_is.equals(tr_senza[0]) and s.trades_oos.equals(tr_senza[1])
              and tab_id[["", "In-sample", "Out-of-sample"]].equals(tab_senza[["", "In-sample", "Out-of-sample"]])
              and s.soglia_scelta is None and "confidenza" not in s.storia.diario[-1]
              and "oos_confidenza" not in s.tabelle)

        muto(vt.confidenza_strategia, s, usa=True)
        soglia_ok = "CONF_BP_MEDI_0C"
        s.conf.sopravvissute = []
        check("85. una soglia che non ha superato le due prove si rifiuta",
              rifiuta(lambda: vt.scheda(s, None, soglia_ok), "non ha superato le due prove"))
        s.conf.sopravvissute = [soglia_ok]     # per la prova: i numeri del mercato finto non contano qui
        check("86. un filtro diverso dalla 5b si rifiuta; un nome sconosciuto si rifiuta",
              rifiuta(lambda: vt.scheda(s, "F_SERA", soglia_ok), "non è quello della 5b")
              and rifiuta(lambda: vt.scheda(s, None, "CONF_NON_ESISTE"), "Soglia non trovata"))
        diario_1 = len(s.storia.diario)
        tab_c, t_c = parlato(vt.scheda, s, None, soglia_ok)
        tenuti = s.trades_oos
        pos_ing = s.df.index.get_indexer(pd.DatetimeIndex(tenuti["EntryTime"])) - 1
        lati = np.sign(tenuti["Size"].to_numpy())
        valori = np.where(lati > 0, s.conf.conf_long["bp_medi"].to_numpy()[pos_ing],
                          s.conf.conf_short["bp_medi"].to_numpy()[pos_ing])
        check("87. la 6 con la soglia: trade dell'in-sample dalla ricerca delle soglie, ogni trade OOS con confidenza "
              "sopra la soglia al segnale (ricontrollato a mano)",
              s.trades_is.equals(s.conf.fs.trades(soglia_ok)) and len(tenuti) > 0 and (valori > 0).all(),
              f"{len(tenuti)} trade out-of-sample")
        tab_cf = s.tabelle["oos_confidenza"]
        check("88. con e senza confidenza sullo stesso grafico; calibrazione solo dell'out-of-sample; il nome nella scheda",
              list(tab_cf["curva"]) == ["senza confidenza", soglia_ok] and tab_cf["trade"].iloc[1] == len(tenuti)
              and s.filtro == soglia_ok and soglia_ok in t_c and len(s.tabelle["confidenza_calibrazione_oos"]) > 0)
        check("89. una sola apertura del diario, con la voce della confidenza; lo dice se la soglia cambia",
              len(s.storia.diario) == diario_1 + 1 and s.storia.diario[-1]["confidenza"] == soglia_ok
              and "soglia di confidenza" in t_c)
        _, t_senza = parlato(vt.scheda, s, None)
        check("90. tornare senza soglia: i trade di prima, e il diario segnala la differenza dalla prima volta solo "
              "se c'era", s.trades_oos.equals(tr_senza[1]) and "confidenza" not in s.storia.diario[-1]
              and "oos_confidenza" not in s.tabelle)
        muto(vt.scheda, s, None, soglia_ok)
        ver = muto(vt.verifica_trade, s)
        regole = ver["regole"].set_index("Regola")
        check("91. schermate 8a e 8b con la soglia: nessun errore, la soglia e' fra i filtri ricontrollati, nessun "
              "trade da guardare sulle regole dei filtri",
              "CONF_BP_MEDI_0C_L" in vt_verifica._filtri_del_lato(s, "long")
              and "CONF_BP_MEDI_0C_S" in vt_verifica._filtri_del_lato(s, "short")
              and all(regole["Esito"] == "OK") and muto(vt.lente, s, "out-of-sample", 1) is not None,
              str(list(regole["Esito"])))
        mm_t = s.trades_oos.copy()
        check("92. le schermate 7, 8 e 9 ricevono i trade con la confidenza",
              mm_t.equals(s.oos.trades(soglia_ok)) and "CONF_BP_MEDI_0C" in vt._frase_scheda_usata(s))
        filtri_prima = list(s.fs.risultati["filtro"])
        asticella = float(s.fs.soglia_rumore)
        conto_f = dict(s.prove["filtri"])
        muto(vt.trova_strategia, s)
        check("93. rifare la 5 dopo la 5b: gli stessi filtri e la stessa asticella, nessun CONF_ provato, conto uguale",
              list(s.fs.risultati["filtro"]) == filtri_prima and float(s.fs.soglia_rumore) == asticella
              and not any(str(f).startswith("CONF_") for f in filtri_prima)
              and not any(n.startswith("CONF_") for n in vt._tutti_i_filtri()) and dict(s.prove["filtri"]) == conto_f)
        check("94. dopo la 5 rifatta la 5b non vale piu': la soglia si rifiuta",
              rifiuta(lambda: vt.scheda(s, None, soglia_ok), "esegui prima la 5b"))
        s.cella_long = "UNA_CELLA"
        prima_b = conto(s)
        r_b, t_b = parlato(vt.confidenza_strategia, s, usa=True)
        rifiuto_b = rifiuta(lambda: vt._soglia_della_5b(s, [], soglia_ok), "la confidenza si salta")
        s.cella_long = None
        check("95. strada B: la confidenza si salta anche accesa, +0 prove; alla 6 la soglia si rifiuta",
              r_b is None and conto(s) == prima_b and "la confidenza si salta" in t_b and rifiuto_b)
        s.sistema = "Solo long"
        muto(vt.trova_strategia, s)
        tab_l = muto(vt.confidenza_strategia, s, usa=True)
        s.conf.sopravvissute = ["CONF_BP_MEDI_0C_L"]
        muto(vt.scheda, s, None, "CONF_BP_MEDI_0C_L")
        check("96. un lato solo: nomi con _L, entry short spenta, 6 e controllo delle condizioni senza errori",
              list(tab_l["Soglia"])[1:] == ["CONF_BP_MEDI_0C_L", "CONF_BP_MEDI_0.5C_L", "CONF_BP_MEDI_0.8C_L"]
              and s.conf.entry_short is None and (np.sign(s.trades_oos["Size"]) > 0).all()
              and not vt_verifica._filtri_del_lato(s, "short") and muto(vt.verifica_trade, s) is not None)
        s.sistema = None

    def celle_nb(nome):
        return [("".join(c_["source"]), c_["cell_type"]) for c_ in json.load(open(nome, encoding="utf-8"))["cells"]]

    lab = celle_nb("Trading_System_Lab_Crypto.ipynb")
    testi = [t_ for t_, _ in lab]
    i5 = next(i_ for i_, t_ in enumerate(testi) if t_.startswith("#@title 5 · Trova la strategia"))
    i5b = next(i_ for i_, t_ in enumerate(testi) if t_.startswith("#@title 5b · La confidenza"))
    i6 = next(i_ for i_, t_ in enumerate(testi) if t_.startswith("#@title 6 · Scheda strategia"))
    ricerca = [t_ for t_, _ in celle_nb("Trading_Grid_Search_v4_backtesting.ipynb")]
    check("97. Lab: la 5b fra la 5 e la 6, spenta di default, chiama solo la funzione; la 6 passa la soglia",
          i5 < i5b < i6 and lab[i5b - 1][1] == "markdown" and testi[i5b - 1].startswith("## 5b")
          and "usa_confidenza = False" in testi[i5b]
          and "confidenza_strategia(s, usa=usa_confidenza, filtro=filtro);" in testi[i5b]
          and 'soglia_confidenza = ""' in testi[i6] and "scheda(s, filtro=filtro, soglia_confidenza=soglia_confidenza);" in testi[i6]
          and any("confidenza_strategia" in t_ and "from engine.vetrina import" in t_ for t_ in testi))
    check("98. ricerca: la 3.3 legge le stesse soglie, e la 3.1 rifatta non prova i CONF_",
          any("SOGLIE_CONF = SOGLIE_CONFIDENZA" in t_ for t_ in ricerca)
          and any('startswith(("CELLA_", "CONF_"))' in t_ and "filtri_da_provare" in t_ for t_ in ricerca))
    rd.azzera()

    imposta_giornata(GIORNATA_FX)
    imposta_rollover(ROLLOVER_DEFAULT)
    svuota_cache()
    clear_registry()
    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
