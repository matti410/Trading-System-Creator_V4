"""
Suite di validazione del FUNDING DEI PERPETUAL (21/10/2026, docs/63 §5,
lavoro B): engine/exchange.py (scarica_funding, salva/leggi_funding,
controlla_funding, copertura_funding, funding_per_trade, aggiungi_funding,
funding_avanti, colonne_perpetual), engine/metriche.pips_per_trade (toglie
FundingPips), i motori (parametro funding), due_meta, il money management
(il funding NON entra nel rischio), gli stati di engine/indicatori.py
(funding_liquidato, basis_bp) e la vetrina (carica_funding, prepara, la
tabella dei costi).

Cosa verifica
-------------
A  casi a mano: trade che attraversa 0, 1, 2 liquidazioni; long e short;
   tasso positivo e negativo; ingresso esattamente su una liquidazione (non
   paga); uscita esattamente su una liquidazione (paga); intervallo che passa
   da 8 a 2 ore; prezzo = Open della barra che inizia nella liquidazione;
   pips netti e bp con il funding dentro;
B  i motori: FundingPips nei trade, avg_trade_netto spostato del funding
   medio; tassi a zero = identico a funding=None; due meta' con il funding di fs;
C  money management: rischio e costo identici con e senza funding, pips netti
   con il funding;
D  funding_avanti (rendimenti a H barre): casi a mano e calcolo a forza bruta;
E  stati: funding_liquidato (nessuna liquidazione vista prima che avvenga,
   riporto a 8 ore), basis_bp (NaN senza spot), prova di lookahead per
   troncamento;
F  scaricatore con un exchange finto, senza rete: Bybit all'indietro con 200
   tassi al massimo e liquidazioni ogni ora (piu' di 200 in 200 ore), finestra
   troppo larga -> errore; Binance in avanti con i millesimi di secondo;
   salvataggio e lettura; controlli (mancanti, anomali segnalati e tenuti,
   intervalli per anno, copertura);
G  vetrina: funding acceso di default sui perpetual, spento a richiesta, file
   mancante o corto -> errore chiaro; spot senza funding; costo in tre righe.

Come si lancia (da terminale, dalla cartella del progetto):

    python test_funding.py

Non serve la rete ne' la cartella dati/.
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

from engine import exchange as X
from engine import registry as R
from engine.exit_search_bt import run_exit_search_bt
from engine.indicatori import basis_bp, funding_liquidato
from engine.metriche import bp_per_trade, pips_per_trade

ESITI = []


def check(nome, condizione, dettaglio=""):
    ESITI.append(bool(condizione))
    stato = "OK     " if condizione else "FALLITO"
    print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))


def muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def errore(f, tipo=Exception, testo=""):
    try:
        muto(f)
    except tipo as e:
        return testo in str(e)
    return False


def barre(giorni=3, inizio="2024-01-01"):
    """M15 24/7 con Open = 1000 + numero della barra (prezzi facili da leggere)."""
    idx = pd.date_range(inizio, periods=giorni * 96, freq="15min", tz="UTC", name="Date")
    o = 1000.0 + np.arange(len(idx))
    return pd.DataFrame({"Open": o, "High": o + 2, "Low": o - 1, "Close": o + 0.5,
                         "Volume": 1.0}, index=idx)


def tabella(orari, tassi):
    idx = pd.DatetimeIndex(pd.to_datetime(orari), name="Date").tz_localize("UTC").as_unit("ns")
    return X.con_intervalli(pd.DataFrame({"tasso": np.asarray(tassi, dtype=float)}, index=idx))


def trade(df, entrata, uscita, size=1.0):
    """Un trade del motore: entra all'Open della barra `entrata`, esce all'Open della barra `uscita`."""
    i, j = df.index.get_loc(pd.Timestamp(entrata, tz="UTC")), df.index.get_loc(pd.Timestamp(uscita, tz="UTC"))
    return {"Size": size, "EntryBar": i, "ExitBar": j, "EntryPrice": df["Open"].iloc[i],
            "ExitPrice": df["Open"].iloc[j], "EntryTime": df.index[i], "ExitTime": df.index[j]}


def storico_24_7(inizio="2023-01-01", giorni=200, prezzo=30000.0, seme=7):
    idx = pd.date_range(inizio, periods=giorni * 96, freq="15min", tz="UTC", name="Date")
    rng = np.random.default_rng(seme)
    close = prezzo * np.exp(np.cumsum(rng.normal(0, 0.002, len(idx))))
    open_ = np.r_[prezzo, close[:-1]]
    alto = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.001, len(idx))))
    basso = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.001, len(idx))))
    return pd.DataFrame({"Open": open_, "High": alto, "Low": basso, "Close": close,
                         "Volume": rng.uniform(1, 100, len(idx))}, index=idx)


def funding_sintetico(df, seme=11):
    """Liquidazioni alle 00, 08, 16 UTC che coprono tutte le barre, tassi intorno a 0,01%."""
    orari = pd.date_range(df.index[0].floor("8h"), df.index[-1].ceil("8h"), freq="8h")
    rng = np.random.default_rng(seme)
    tassi = 0.0001 + rng.normal(0, 0.0002, len(orari))
    return tabella(orari.tz_localize(None), tassi)


class FundingFinto:
    """fetch_funding_rate_history come ccxt. indietro=True: Bybit (gli ultimi `limit`
    prima di endTime); False: Binance (i primi `limit` da since in avanti)."""

    def __init__(self, ident, orari, tassi, indietro, millesimi=0):
        self.id = ident
        self.ms = (pd.DatetimeIndex(orari).as_unit("ns").asi8 // 1_000_000).astype(np.int64)
        self.tassi = np.asarray(tassi, dtype=float)
        self.indietro, self.millesimi, self.chiamate = indietro, int(millesimi), 0

    def fetch_funding_rate_history(self, simbolo, since=None, limit=None, params=None):
        self.chiamate += 1
        if self.indietro:
            fine = (params or {})["endTime"]
            sel = np.flatnonzero((self.ms >= since) & (self.ms <= fine))[-int(limit):]
        else:
            sel = np.flatnonzero(self.ms + self.millesimi >= since)[: int(limit)]
        return [{"timestamp": int(self.ms[k]) + self.millesimi, "fundingRate": float(self.tassi[k])}
                for k in sel]


def main() -> int:
    # --------------------------------------------------------- casi a mano --
    print("\nA · Il funding di un trade, casi a mano (pip 1, Open = 1000 + barra)")
    df = barre()
    O = lambda t: float(df.at[pd.Timestamp(t, tz="UTC"), "Open"])
    f8 = tabella(["2024-01-01 00:00", "2024-01-01 08:00", "2024-01-01 16:00", "2024-01-02 00:00"],
                 [0.0001, 0.0003, -0.0002, 0.0005])
    casi = pd.DataFrame([trade(df, "2024-01-01 01:00", "2024-01-01 07:45"),           # 0 liquidazioni
                         trade(df, "2024-01-01 07:00", "2024-01-01 09:00"),           # 1 (08:00)
                         trade(df, "2024-01-01 07:00", "2024-01-01 16:30"),           # 2 (08:00, 16:00)
                         trade(df, "2024-01-01 07:00", "2024-01-01 09:00", -1.0),     # short, 1
                         trade(df, "2024-01-01 15:00", "2024-01-01 17:00"),           # long, tasso negativo
                         trade(df, "2024-01-01 08:00", "2024-01-01 10:00"),           # ingresso su S
                         trade(df, "2024-01-01 07:00", "2024-01-01 08:00")])          # uscita su S
    fp = X.funding_per_trade(casi, df, f8, 1.0).to_numpy()
    a08, a16 = 0.0003 * O("2024-01-01 08:00"), -0.0002 * O("2024-01-01 16:00")
    check("A1. nessuna liquidazione dentro il trade: zero", fp[0] == 0.0)
    check("A2. una liquidazione: tasso x Open della barra delle 08:00 / pip, il long paga",
          np.isclose(fp[1], a08) and fp[1] > 0, f"{fp[1]:.4f} pips")
    check("A3. due liquidazioni (08:00 e 16:00): la somma", np.isclose(fp[2], a08 + a16), f"{fp[2]:.4f}")
    check("A4. short con tasso positivo: incassa (stesso importo, segno opposto)", np.isclose(fp[3], -a08))
    check("A5. long con tasso negativo: incassa", np.isclose(fp[4], a16) and fp[4] < 0)
    check("A6. ingresso esattamente su una liquidazione: non paga", fp[5] == 0.0)
    check("A7. uscita esattamente su una liquidazione: paga", np.isclose(fp[6], a08))
    f2 = tabella(["2024-01-01 00:00", "2024-01-01 08:00", "2024-01-01 10:00", "2024-01-01 12:00",
                  "2024-01-01 14:00", "2024-01-01 16:00", "2024-01-02 00:00"],
                 [0.0001, 0.0002, 0.0004, 0.0004, 0.0004, 0.0001, 0.0001])
    t2 = pd.DataFrame([trade(df, "2024-01-01 07:00", "2024-01-01 15:00")])
    atteso = sum(r * O(t) for r, t in ((0.0002, "2024-01-01 08:00"), (0.0004, "2024-01-01 10:00"),
                                       (0.0004, "2024-01-01 12:00"), (0.0004, "2024-01-01 14:00")))
    check("A8. intervallo da 8 a 2 ore: quattro liquidazioni (08, 10, 12, 14), intervalli letti riga per riga",
          np.isclose(X.funding_per_trade(t2, df, f2, 1.0).iloc[0], atteso)
          and np.allclose(f2["intervallo_ore"].to_numpy()[1:], [8, 2, 2, 2, 2, 8])
          and np.isnan(f2["intervallo_ore"].iloc[0]))
    buco = df.drop(index=[pd.Timestamp("2024-01-01 08:00", tz="UTC")])
    tb = pd.DataFrame([trade(buco, "2024-01-01 07:00", "2024-01-01 09:00")])
    check("A9. barra della liquidazione mancante: prezzo = Open della prima barra dopo (08:15)",
          np.isclose(X.funding_per_trade(tb, buco, f8, 1.0).iloc[0], 0.0003 * O("2024-01-01 08:15")))
    con = X.aggiungi_funding(casi, df, f8, 1.0)
    lordi, netti = pips_per_trade(con, 1.0, 0.0005)
    _, netti_senza = pips_per_trade(casi, 1.0, 0.0005)
    check("A10. pips_per_trade toglie FundingPips, con il segno (un incasso alza i netti)",
          np.allclose(netti.to_numpy(), netti_senza.to_numpy() - fp) and netti.iloc[3] > netti_senza.iloc[3])
    _, nb = bp_per_trade(con, 1.0, 0.0005)
    check("A11. in bp il funding entra da solo: bp = pips netti x pip / prezzo d'ingresso x 10.000",
          np.allclose(nb.to_numpy(), netti.to_numpy() * 10_000.0 / con["EntryPrice"].to_numpy()))
    check("A12. funding=None: i trade tornano come sono, senza la colonna",
          X.aggiungi_funding(casi, df, None, 1.0) is casi and "FundingPips" not in casi.columns)

    # -------------------------------------------------------------- motori --
    print("\nB · I motori: la colonna FundingPips e i netti")
    R.clear_registry()

    @R.register_entry("TEST_LONG_OGNI_3_ORE", 1)
    def _long(d):
        return pd.Series((d.index.minute == 0) & (d.index.hour % 3 == 0), index=d.index)

    @R.register_entry("TEST_SHORT_MEZZORA", -1)
    def _short(d):
        return pd.Series((d.index.minute == 30) & (d.index.hour % 4 == 1), index=d.index)

    @R.register_filter("TEST_FILTRO_MATTINA", 0)
    def _mattina(d):
        return pd.Series(d.index.hour < 12, index=d.index)

    sd = storico_24_7(giorni=60)
    fs_ = funding_sintetico(sd)
    zero = fs_.assign(tasso=0.0)
    kw = dict(entry_cols_long=["TEST_LONG_OGNI_3_ORE"], entry_cols_short=["TEST_SHORT_MEZZORA"], n_barre=12,
              perc_sl=90.0, perc_tp=0.0, spread=0.0, commission=0.0005, cash=10_000_000, pip_size=1.0,
              verbose=False, unita="bp")
    es0 = muto(run_exit_search_bt, sd, **kw)
    es1 = muto(run_exit_search_bt, sd, funding=fs_, **kw)
    esz = muto(run_exit_search_bt, sd, funding=zero, **kw)
    comb = es0.risultati["combinazione"].iloc[0]
    t0, t1 = es0.trades(comb), es1.trades(comb)
    check("B1. funding=None: nessuna colonna nuova nei trade, es.funding None",
          "FundingPips" not in t0.columns and es0.funding is None)
    check("B2. con il funding: stessi trade, FundingPips = funding_per_trade",
          len(t1) == len(t0) and (t1["EntryBar"].to_numpy() == t0["EntryBar"].to_numpy()).all()
          and np.allclose(t1["FundingPips"].to_numpy(), X.funding_per_trade(t0, sd, fs_, 1.0).to_numpy())
          and es1.funding is fs_, f"{len(t1)} trade, funding medio {t1['FundingPips'].mean():+.3f} pips")
    r0, r1 = es0.risultati.set_index("combinazione").loc[comb], es1.risultati.set_index("combinazione").loc[comb]
    fbp = (t1["FundingPips"] * 10_000.0 / t1["EntryPrice"]).mean()
    check("B3. avg_trade_netto (in bp) scende del funding medio in bp; pnl_pct e sharpe della libreria uguali",
          np.isclose(r0["avg_trade_netto"] - r1["avg_trade_netto"], fbp)
          and np.isclose(r0["avg_trade_netto_pips"] - r1["avg_trade_netto_pips"], t1["FundingPips"].mean())
          and r0["sharpe"] == r1["sharpe"], f"{r0['avg_trade_netto']:+.3f} -> {r1['avg_trade_netto']:+.3f} bp")
    num = lambda r: r.drop(labels=[c for c in r.index if not isinstance(r[c], (int, float, np.number))])
    check("B4. tassi tutti a zero: ogni numero identico a funding=None",
          np.allclose(num(es0.risultati.set_index("combinazione").loc[comb]).astype(float),
                      num(esz.risultati.set_index("combinazione").loc[comb]).astype(float), equal_nan=True))
    from engine.due_meta import due_meta
    from engine.filter_search_bt import BASELINE, run_filter_search_bt
    kwf = dict(entry_long="TEST_LONG_OGNI_3_ORE", entry_short="TEST_SHORT_MEZZORA", n_barre=12,
               filtri=["TEST_FILTRO_MATTINA"], perc_sl=90.0, perc_tp=0.0, spread=0.0, commission=0.0005,
               cash=10_000_000, pip_size=1.0, verbose=False, unita="bp", processi=1)
    ff0 = muto(run_filter_search_bt, sd, **kwf)
    ff1 = muto(run_filter_search_bt, sd, funding=fs_, **kwf)
    tb1 = ff1.trades(None)
    check("B5. ricerca dei filtri: FundingPips nei trade, avg_trade_netto della baseline spostato",
          "FundingPips" in tb1.columns and ff1.funding is fs_
          and not np.isclose(ff0.risultati.set_index("filtro").loc[BASELINE, "avg_trade_netto"],
                             ff1.risultati.set_index("filtro").loc[BASELINE, "avg_trade_netto"]))
    dm = muto(due_meta, sd, ff1, [None, "TEST_FILTRO_MATTINA"], perc_sl=90.0, spread=0.0, commission=0.0005,
              cash=10_000_000, verbose=False)
    dm0 = muto(due_meta, sd, ff0, [None, "TEST_FILTRO_MATTINA"], perc_sl=90.0, spread=0.0, commission=0.0005,
               cash=10_000_000, verbose=False)
    check("B6. due meta': le due ricerche contano il funding di fs (nessun parametro in piu')",
          "FundingPips" in dm.metà1.trades(None).columns and "FundingPips" in dm.metà2.trades(None).columns
          and "FundingPips" not in dm0.metà1.trades(None).columns)

    # ---------------------------------------------------- money management --
    print("\nC · Money management: il funding resta fuori dal rischio")
    from engine.mm_adattatore import tabella_trade
    kmm = dict(symbol="BINANCE_PERP_BTCUSDT", pip=1.0, commission=0.0005, spread_pips=0.1, perc_sl=90.0,
               n_barre_long=12, n_barre_short=12)
    for misura in ("stop", "volatilita"):
        a = tabella_trade(t1, sd, misura=misura, **kmm)
        b = tabella_trade(t1.drop(columns="FundingPips"), sd, misura=misura, **kmm)
        fu = t1.sort_values("ExitTime", kind="mergesort")["FundingPips"].to_numpy()
        check(f"C{1 if misura == 'stop' else 2}. misura «{misura}»: rischio e costo identici senza funding, "
              "pips netti con il funding",
              np.allclose(a["rischio_pips"], b["rischio_pips"], equal_nan=True)
              and np.allclose(a["costo_pips"], b["costo_pips"])
              and np.allclose(a["pips_netti"].to_numpy(), b["pips_netti"].to_numpy() - fu))
    neg = t1.copy()
    neg["FundingPips"] = -50.0            # un incasso grande: il rischio non deve scendere
    check("C3. un incasso non abbassa il rischio del trade",
          np.allclose(tabella_trade(neg, sd, **kmm)["rischio_pips"], tabella_trade(t1, sd, **kmm)["rischio_pips"]))
    R.clear_registry()

    # ---------------------------------------------------- funding_avanti --
    print("\nD · Il funding nei rendimenti a H barre (per l'atlante)")
    H = 4
    fa = X.funding_avanti(df, H, f8, 1.0)
    pos = lambda t: df.index.get_loc(pd.Timestamp(t, tz="UTC"))
    check("D1. segnale alle 07:00: ingresso 07:15, misura alla chiusura delle 08:00 -> conta la liquidazione delle 08:00",
          np.isclose(fa[pos("2024-01-01 07:00")], a08))
    check("D2. segnale alle 07:45 (ingresso alle 08:00, un istante dopo) e alle 06:45 (misura alle 08:00, "
          "un istante prima): zero",
          fa[pos("2024-01-01 07:45")] == 0.0 and fa[pos("2024-01-01 06:45")] == 0.0)
    check("D3. ultime H barre: NaN (la misura non esiste)", np.isnan(fa[-H:]).all() and np.isfinite(fa[:-H]).all())
    fl = X.funding_avanti(sd, 25, fs_, 1.0)
    S = pd.DatetimeIndex(fs_.index)
    prezzo_S = sd["Open"].reindex(S).to_numpy()
    rng = np.random.default_rng(0)
    campione = rng.integers(0, len(sd) - 25, 300)
    passo = pd.Timedelta("15min")
    forza = [sum(fs_["tasso"].iloc[k] * prezzo_S[k] for k in range(len(S))
                 if sd.index[i + 1] < S[k] < sd.index[i + 25] + passo) for i in campione]
    check("D4. contro il calcolo a forza bruta su 300 barre (H = 25)", np.allclose(fl[campione], forza))

    # -------------------------------------------------------------- stati --
    print("\nE · Gli stati: funding liquidato e basis")
    dfc = X.colonne_perpetual(df, f2)
    fl_ = funding_liquidato(dfc)
    v = lambda t: fl_.at[pd.Timestamp(t, tz="UTC")]
    check("E1. la liquidazione delle 08:00 non si vede alle 07:45, si vede dalle 08:00 (riportata a 8 ore)",
          np.isnan(v("2024-01-01 07:45")) and np.isclose(v("2024-01-01 08:00"), 0.0002)
          and np.isclose(v("2024-01-01 09:45"), 0.0002), "prima del primo intervallo noto: NaN")
    check("E2. riporto a 8 ore: 0,04% ogni 2 ore vale 0,16% ogni 8 ore",
          np.isclose(v("2024-01-01 10:00"), 0.0016) and np.isclose(v("2024-01-01 15:45"), 0.0016)
          and np.isclose(v("2024-01-01 16:00"), 0.0001 * 8 / 2))
    spot = df[["Close"]] * 0.999
    spot = spot.drop(index=spot.index[100:120])
    dfs = X.colonne_perpetual(df, f2, spot)
    bb = basis_bp(dfs)
    check("E3. basis in bp sulla stessa barra; NaN dove manca lo spot",
          np.isclose(bb.iloc[0], (1 - 0.999) / 0.999 * 10_000) and bb.iloc[100:120].isna().all()
          and bb.drop(index=bb.index[100:120]).notna().all())
    check("E4. senza le colonne grezze (CFD, spot, mercato sintetico): NaN",
          funding_liquidato(df).isna().all() and basis_bp(df).isna().all())
    piena_f, piena_b = funding_liquidato(X.colonne_perpetual(sd, fs_, sd[["Close"]] * 1.0002)), None
    piena_b = basis_bp(X.colonne_perpetual(sd, fs_, sd[["Close"]] * 1.0002))
    tagli = [500, 2_000, 3_333, len(sd) - 7]
    ok_f = ok_b = True
    for k in tagli:
        corto = X.colonne_perpetual(sd.iloc[:k], fs_[fs_.index <= sd.index[k - 1]], sd[["Close"]].iloc[:k] * 1.0002)
        ok_f &= np.allclose(funding_liquidato(corto).to_numpy(), piena_f.iloc[:k].to_numpy(), equal_nan=True)
        ok_b &= np.allclose(basis_bp(corto).to_numpy(), piena_b.iloc[:k].to_numpy(), equal_nan=True)
    check("E5. lookahead per troncamento: tagliando lo storico (e il funding) i valori gia' calcolati non cambiano",
          ok_f and ok_b, f"tagli {tagli}")
    check("E6. funding liquidato = l'ultimo tasso con S <= inizio della barra, sul campione intero",
          all(np.isclose(piena_f.iloc[i], fs_["tasso"][fs_.index <= sd.index[i]].iloc[-1] * 8
                         / fs_["intervallo_ore"][fs_.index <= sd.index[i]].iloc[-1])
              for i in rng.integers(100, len(sd), 200)))

    # -------------------------------------------------------- scaricatore --
    print("\nF · Lo scaricatore (exchange finto, senza rete)")
    orari = pd.date_range("2024-01-01", periods=1000, freq="h", tz="UTC")
    tassi = np.linspace(-0.001, 0.001, 1000)
    by = FundingFinto("bybit", orari, tassi, indietro=True)
    giu = X.scarica_funding("BYBIT_PERP_SOLUSDT", da="2024-01-01", a="2024-03-01", ex=by, verbose=False)
    check("F1. Bybit, liquidazioni ogni ora (1.000 in 1.000 ore, piu' di 200 per finestra larga): "
          "finestre di 150 ore, nessun tasso perso",
          len(giu) == 1000 and np.allclose(giu["tasso"], tassi) and (giu["intervallo_ore"].iloc[1:] == 1).all(),
          f"{len(giu)} tassi in {by.chiamate} richieste")
    check("F2. una finestra troppo larga (300 ore: 200 tassi, il massimo) si ferma invece di perdere tassi",
          errore(lambda: X.scarica_funding("BYBIT_PERP_SOLUSDT", da="2024-01-01", a="2024-03-01",
                                           ex=FundingFinto("bybit", orari, tassi, True), finestra_ore=300,
                                           verbose=False), RuntimeError, "potrebbe mancare"))
    o8 = pd.date_range("2022-01-01", periods=3000, freq="8h", tz="UTC")
    bn = FundingFinto("binanceusdm", o8, np.full(3000, 0.0001), indietro=False, millesimi=5)
    giu_b = X.scarica_funding("BINANCE_PERP_BTCUSDT", da="2022-01-01", a="2025-01-01", ex=bn, verbose=False)
    check("F3. Binance in avanti a blocchi di 1.000, orari con 5 millesimi arrotondati al minuto",
          len(giu_b) == 3000 and pd.DatetimeIndex(giu_b.index).equals(o8.as_unit("ns"))
          and bn.chiamate <= 5, f"{bn.chiamate} richieste")
    check("F4. funding solo sui perpetual: lo spot si ferma con errore",
          errore(lambda: X.scarica_funding("BYBIT_SPOT_ETHUSDT", ex=by), ValueError, "perpetual"))
    with tempfile.TemporaryDirectory() as tmp:
        p = X.file_funding("BYBIT_PERP_SOLUSDT", tmp)
        X.salva_funding(giu, p)
        letto = X.leggi_funding(p)
        testa = open(p, encoding="utf-8").readline().strip()
    check("F5. salva e rileggi: Date, tasso, intervallo_ore; stessi valori, indice UTC",
          testa == "Date,tasso,intervallo_ore" and np.allclose(letto["tasso"], giu["tasso"])
          and letto.index.equals(giu.index) and str(letto.index.tz) == "UTC")
    regimi = pd.DatetimeIndex(list(pd.date_range("2022-11-01", "2022-11-09 16:00", freq="8h"))
                              + list(pd.date_range("2022-11-09 18:00", "2022-11-18", freq="2h"))
                              + list(pd.date_range("2022-11-18 08:00", "2022-12-31", freq="8h")))
    tt = np.full(len(regimi), 0.0001)
    tt[60] = -0.02                                                       # il -2% (vero, si tiene)
    sol = X.scarica_funding("BYBIT_PERP_SOLUSDT", da="2022-11-01", a="2023-01-01",
                            ex=FundingFinto("bybit", regimi, tt, True), verbose=False)
    tolto = sol.drop(index=sol.index[200])                               # una liquidazione persa
    c = X.controlla_funding(X.con_intervalli(tolto))
    check("F6. periodo a 2 ore (come SOL a novembre 2022): completo e letto riga per riga",
          len(sol) == len(regimi) and set(np.round(sol["intervallo_ore"].dropna().unique(), 2)) == {8.0, 2.0})
    check("F7. controlli: una liquidazione mancante, il -2% segnalato e tenuto, intervalli per anno",
          c["mancanti"] == 1 and c["anomali"] == 1 and c["elenco_anomali"][0][1] == -0.02
          and (tolto["tasso"] == -0.02).sum() == 1 and 2.0 in c["intervalli_per_anno"].columns
          and c["fuori_orario"] == 0, f"mancante {c['elenco_mancanti']}")
    check("F8. un cambio di regime (8 -> 2 -> 8 ore) non e' una mancanza",
          X.controlla_funding(sol)["mancanti"] == 0)
    bars = storico_24_7(inizio="2024-01-01", giorni=20)
    fb = funding_sintetico(bars)
    tardi = fb[fb.index > bars.index[0] + pd.Timedelta(hours=9)]
    corto = fb[fb.index < bars.index[-1] - pd.Timedelta(hours=9)]
    check("F9. copertura: completa = None; parte tardi o finisce presto = il motivo",
          X.copertura_funding(fb, bars) is None and "inizio" in X.copertura_funding(tardi, bars)
          and "meno aggiornato" in X.copertura_funding(corto, bars))
    sorgente = (open(X.__file__, encoding="utf-8").read()
                + open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "scarica_dati_crypto.py"),
                       encoding="utf-8").read())
    check("F10. solo dati pubblici: nessuna chiave API, nessuna funzione di ordine o di saldo",
          not any(k in sorgente for k in ("apiKey", "secret", "create_order", "cancel_order",
                                          "edit_order", "fetch_balance")))

    # ------------------------------------------------------------ vetrina --
    print("\nG · Vetrina")
    import engine.vetrina as vt
    with tempfile.TemporaryDirectory() as tmp:
        dati = storico_24_7(giorni=200)
        for nome in ("BINANCE_PERP_BTCUSDT", "BINANCE_SPOT_BTCUSDT", "BYBIT_PERP_BTCUSDT"):
            X.salva_csv(dati, os.path.join(tmp, f"{nome}_M15.csv"))
        fd = funding_sintetico(dati)
        X.salva_funding(fd, X.file_funding("BINANCE_PERP_BTCUSDT", tmp))
        X.salva_funding(fd[fd.index < dati.index[-1] - pd.Timedelta(days=3)],
                        X.file_funding("BYBIT_PERP_BTCUSDT", tmp))
        s = muto(vt.prepara, "BINANCE_PERP_BTCUSDT", H=8, cartella=tmp)
        rie = s.tabelle["riepilogo"].set_index("")[" "]
        check("G1. perpetual: funding acceso di default, nei costi dei motori, «contato» nel riepilogo",
              s.funding is not None and s.costi.get("funding") is s.funding
              and vt._kw_motore(type("S", (), {"uscite": dict(n_barre=8, n_barre_long=8, n_barre_short=8,
                                                              perc_sl=90.0, perc_tp=0.0), "unita": "bp",
                                               "costi": s.costi})())["funding"] is s.funding
              and rie["Funding (perpetual)"].startswith("contato") and "ogni 8 ore" in rie["Funding (perpetual)"],
              rie["Funding (perpetual)"])
        s0 = muto(vt.prepara, "BINANCE_PERP_BTCUSDT", H=8, cartella=tmp, funding=False)
        check("G2. funding=False (solo per la prova di identita'): niente funding, riga «spento»",
              s0.funding is None and "funding" not in s0.costi
              and s0.tabelle["riepilogo"].set_index("")[" "]["Funding (perpetual)"].startswith("spento"))
        ss = muto(vt.prepara, "BINANCE_SPOT_BTCUSDT", H=8, cartella=tmp)
        check("G3. spot: nessun funding, nessuna voce nei costi", ss.funding is None and "funding" not in ss.costi)
        check("G4. file del funding mancante: si ferma, dice il file e come scaricarlo",
              errore(lambda: vt.carica_funding("BINANCE_PERP_ETHUSDT", dati, tmp), FileNotFoundError,
                     "scarica_dati_crypto.py BINANCE_PERP_ETHUSDT"))
        check("G5. funding che non copre le barre: si ferma, niente zeri",
              errore(lambda: vt.prepara("BYBIT_PERP_BTCUSDT", H=8, cartella=tmp), ValueError, "non copre"))
        muto(vt.esplora, s)
        muto(vt.scegli_trigger, s, long="E1_RSI_CROSS_OVERSOLD", short="E4_SHORT_EMA_CROSS_DOWN")
        muto(vt.imposta_uscite, s, barre_long=8, barre_short=8, sl=90)
        entrambi = s.es.risultati[s.es.risultati["entry_long"].notna() & s.es.risultati["entry_short"].notna()]
        tr = s.es.trades(entrambi["combinazione"].iloc[0])             # long + short
        tab = vt._tabella_costi(s, tr, tr.iloc[:0]).set_index("")
        lato = np.where(tr["Size"] > 0, 1, -1)
        bp = 10_000.0 * s.pip / tr["EntryPrice"].to_numpy()
        fu = tr["FundingPips"].to_numpy()
        check("G6. costo in tre righe (commissione, spread, funding), in bp con i pips accanto; "
              "funding diviso fra long e short",
              {"Commissione (andata e ritorno)", "Spread", "Funding, tutti i trade", "Funding dei long",
               "Funding degli short", "Costo totale"} <= set(tab.index)
              and np.isclose(tab.at["Funding, tutti i trade", "In-sample (pips)"], fu.mean())
              and np.isclose(tab.at["Funding dei long", "In-sample (bp)"], (fu * bp)[lato == 1].mean())
              and np.isclose(tab.at["Commissione (andata e ritorno)", "In-sample (bp)"],
                             (0.0005 * (tr["EntryPrice"] + tr["ExitPrice"]).to_numpy() * bp).mean())
              and np.isclose(tab.at["Costo totale", "In-sample (pips)"],
                             tab.loc[["Commissione (andata e ritorno)", "Spread", "Funding, tutti i trade"],
                                     "In-sample (pips)"].sum()))
    R.clear_registry()

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(main())
