"""
Suite di validazione dell'atlante del trigger (22/10/2026, lavoro C, docs/66).

Si lancia da terminale, dalla cartella del progetto:

    python test_atlante.py

Non serve MetaTrader 5 e non serve nessun file di dati: usa un mercato
sintetico aperto 24 ore su 24 (come le crypto), con vantaggi messi apposta
dove il test lo dice. Sezioni:

    A · gli stati delle celle (engine/indicatori.py): identita' su M15 con
        confidenza.py, durate sugli altri timeframe, niente lookahead,
        sessioni con l'ora legale, basis
"""
from __future__ import annotations

import sys
import time
import warnings

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

from engine import registry as reg
from engine.confidenza import asse_volatilita, cella_contesto
from engine.indicatori import (SESSIONI_ATLANTE, barre_per_durata, basis_alta, basis_bp,
                               cella_vol_trend, sessione_ingresso, trend_durata,
                               volatilita_durata)
from engine.livelli import GIORNATA_UTC, imposta_giornata, svuota_cache
from engine.quarantena import imposta_rollover

warnings.simplefilter("ignore")

H = 8
PIP = 0.01


def _indice(inizio="2022-01-03", giorni=730, minuti=15):
    return pd.date_range(inizio, periods=int(giorni * 1440 / minuti), freq=f"{minuti}min", tz="UTC")


class Mercato:
    """Un random walk 24/7 di cui si possono cambiare i rendimenti (le stesse candele per il resto)."""

    def __init__(self, idx, seme=0, sigma=0.0004):
        self.idx = idx
        rng = np.random.default_rng(seme)
        n = len(idx)
        self.rend = rng.normal(0, sigma, n)
        self.alto = np.abs(rng.normal(0, sigma * 0.75, n))
        self.basso = np.abs(rng.normal(0, sigma * 0.75, n))
        self.volume = rng.integers(20, 2000, n).astype(float)
        self.basis = rng.normal(0, 0.0005, n)

    def df(self, extra=None, spot=False):
        r = self.rend if extra is None else self.rend + extra
        close = 100.0 * np.exp(np.cumsum(r))
        op = np.r_[100.0, close[:-1]]
        d = pd.DataFrame({"Open": op, "High": np.maximum(op, close) * (1 + self.alto),
                          "Low": np.minimum(op, close) * (1 - self.basso), "Close": close,
                          "Volume": self.volume}, index=self.idx)
        if spot:
            d["spot_close"] = close * (1 - self.basis)
        return d


def _deriva_dopo(n, pos, quanto):
    """Rendimenti in piu' sulle barre p+1 .. p+H di ogni trigger p (il trade misurato)."""
    extra = np.zeros(n)
    for p, q in zip(pos, quanto):
        extra[p + 1: p + 1 + H] += q
    return extra


def _registra_entry(nome, direzione, tempi):
    tempi = pd.DatetimeIndex(tempi)

    def entry(d):
        return pd.Series(d.index.isin(tempi), index=d.index)
    reg.register_entry(nome, direction=direzione)(entry)


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    imposta_rollover(None)              # mercato 24/7: nessuna quarantena, come gli exchange
    imposta_giornata(GIORNATA_UTC)      # la giornata delle crypto
    svuota_cache()
    reg.clear_registry()

    # =================================================================== A ==
    print("\nA · Gli stati delle celle (engine/indicatori.py)")
    M = Mercato(_indice(giorni=60), seme=1)
    df = M.df()

    check("1. su M15 volatilita_durata = confidenza.asse_volatilita(20, 500), bit per bit",
          volatilita_durata(df).equals(asse_volatilita(df, 20, 500)))
    check("2. su M15 cella_vol_trend = confidenza.cella_contesto, bit per bit, sui due lati",
          cella_vol_trend(df, 1).equals(cella_contesto(df, 1))
          and cella_vol_trend(df, -1).equals(cella_contesto(df, -1)))

    attese = {5: (60, 1500), 15: (20, 500), 30: (20, 250), 60: (20, 125), 240: (20, 31)}
    trovate = {m: (barre_per_durata(_indice(giorni=3, minuti=m), 5),
                   barre_per_durata(_indice(giorni=3, minuti=m), 125)) for m in attese}
    check("3. durate in barre con almeno 20 rendimenti: M5 60/1500, M15 20/500, M30 20/250, "
          "H1 20/125, H4 20/31", trovate == attese, str(trovate))

    idx_h4 = _indice(giorni=400, minuti=240)
    d4 = Mercato(idx_h4, seme=2).df()
    r = np.log(d4["Close"] / d4["Close"].shift(1)) * 100
    dev = r.rolling(20).std()
    med = dev.rolling(31, min_periods=31).quantile(0.5)
    atteso = pd.Series(np.where(dev > med, 1.0, 0.0), index=d4.index).where(med.notna())
    v4 = volatilita_durata(d4)
    check("4. su H4 la deviazione usa 20 rendimenti (non 1,25) e la mediana 31 barre",
          v4.equals(atteso.rename("vol")) and int(v4.isna().sum()) == 20 + 31 - 1,
          f"NaN iniziali {int(v4.isna().sum())}")

    ds = M.df(spot=True)
    stati = {"volatilità": lambda x: volatilita_durata(x), "trend long": lambda x: trend_durata(x, 1),
             "trend short": lambda x: trend_durata(x, -1), "sessione": sessione_ingresso,
             "basis": basis_alta}
    pieni = {k: f(ds) for k, f in stati.items()}
    diversi = []
    for taglio in (900, 2500, 4100, len(ds) - 7):
        corto = ds.iloc[:taglio]
        svuota_cache()
        for k, f in stati.items():
            a, b = f(corto), pieni[k].iloc[:taglio]
            if not (np.allclose(a.to_numpy(), b.to_numpy(), equal_nan=True, rtol=0, atol=1e-12)):
                diversi.append((k, taglio))
    svuota_cache()
    check("5. nessun lookahead: tagliati i dati alla barra i, gli stati fino a i non cambiano "
          "(volatilità, trend dei due lati, sessione, basis; 4 tagli)", not diversi, str(diversi))

    sess = sessione_ingresso(ds)
    sabato = ds.index.tz_convert("Europe/London").dayofweek >= 5
    prossima = (ds.index + pd.Timedelta(minutes=15))
    fine_sett = np.asarray(prossima.tz_convert("Europe/London").dayofweek >= 5) & \
        np.asarray(prossima.tz_convert("America/New_York").dayofweek >= 5)
    check("6. sessioni: ogni barra in esattamente una cella (0-3, nessun NaN); il fine settimana "
          "è tutto ASIA_NOTTE",
          sess.notna().all() and set(np.unique(sess)) <= {0.0, 1.0, 2.0, 3.0}
          and (sess[fine_sett] == 0).all(), f"celle {dict(sess.value_counts().sort_index())}")

    def cella_a(t):
        i = pd.DatetimeIndex([pd.Timestamp(t, tz="UTC")])
        d = pd.DataFrame(index=i.append(i + pd.Timedelta(minutes=15)))
        return SESSIONI_ATLANTE[int(sessione_ingresso(d).iloc[0])]

    casi = {"2024-02-14 11:45": "EUROPA",      # ingresso 12:00 UTC: Londra 12:00, New York 07:00 (EST)
            "2024-03-13 11:45": "LONDRA_NY",   # New York gia' in ora legale (dal 10/3), Londra no
            "2024-03-13 11:30": "EUROPA",      # ingresso 11:45: New York 07:45, chiusa
            "2024-04-10 11:45": "LONDRA_NY",
            "2024-04-10 16:00": "AMERICA",     # ingresso 16:15 UTC: Londra 17:15, New York 12:15
            "2024-04-10 06:45": "EUROPA",      # ingresso 07:00 UTC: Londra 08:00 (BST)
            "2024-04-10 06:30": "ASIA_NOTTE",
            "2024-04-13 11:45": "ASIA_NOTTE"}  # sabato
    trovati = {t: cella_a(t) for t in casi}
    check("7. sessioni sulla barra d'ingresso (i+1), ora locale con l'ora legale sfasata di marzo",
          trovati == casi, str({t: v for t, v in trovati.items() if v != casi[t]}))

    b = basis_bp(ds)
    spot_buco = ds.copy()
    spot_buco.iloc[3000:3010, spot_buco.columns.get_loc("spot_close")] = np.nan
    ba = basis_alta(spot_buco)
    check("8. basis: (perpetual − spot) / spot × 10.000; NaN dove manca lo spot e per la finestra "
          "che lo contiene; senza spot tutta NaN",
          np.allclose(b, (ds["Close"] - ds["spot_close"]) / ds["spot_close"] * 1e4)
          and ba.iloc[3000:3010 + 500 - 1].isna().all() and ba.iloc[3010 + 500 - 1:].notna().all()
          and basis_alta(df).isna().all() and basis_bp(df).isna().all())

    reg.clear_registry()
    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
