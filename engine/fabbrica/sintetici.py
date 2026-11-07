"""
Dati sintetici per i collaudi della fabbrica (lavori L3 e seguenti), come funzioni_prova.py per L1.

Nessun dato vero, nessuna prova: barre inventate con regimi di tendenza e di volatilità, scritte nei CSV che la
fabbrica legge (stesso formato di scarica_dati_crypto.py), più un funding inventato ogni 8 ore.

    df = mercato(20_000, seme=0, minuti=15, inizio="2024-01-01", prezzo=30_000)
    scrivi_storico(cartella, "BINANCE_PERP_BTCUSDT", "M15", df)
    scrivi_funding(cartella, "BINANCE_PERP_BTCUSDT", df, seme=0)
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from engine.exchange import file_funding, salva_funding


def mercato(n: int = 12_000, seme: int = 0, minuti: int = 15, inizio: str = "2024-01-01", prezzo: float = 100.0,
            spinta=None) -> pd.DataFrame:
    """
    Prezzi a regimi (tendenza, volatilità) con volume che segue la volatilità, indice UTC. Prezzi a 1/64 del livello
    iniziale diviso 100, così restano esatti in binario. `spinta`: rendimento in più barra per barra (array lungo n),
    per piantare un vantaggio noto.
    """
    r = np.random.default_rng(seme)
    drift, vol, i = np.zeros(n), np.zeros(n), 0
    while i < n:
        lung = int(r.integers(40, 400))
        drift[i: i + lung] = r.choice((-1.0, 0.0, 1.0), p=(0.3, 0.4, 0.3)) * r.uniform(0.0002, 0.0012)
        vol[i: i + lung] = r.choice((0.0008, 0.0016, 0.0040), p=(0.4, 0.4, 0.2))
        i += lung
    rendimenti = drift + vol * r.standard_normal(n)
    rendimenti = rendimenti - rendimenti.mean()
    if spinta is not None:
        rendimenti = rendimenti + np.asarray(spinta, dtype=float)
    scala = prezzo / 100.0

    def tick(x):
        return np.round(np.asarray(x) / scala * 64.0) / 64.0 * scala

    c = tick(prezzo * np.exp(np.cumsum(rendimenti)))
    o = tick(np.r_[c[0], c[:-1]] + 0.1 * vol * c * r.standard_normal(n))
    ampiezza = np.abs(r.standard_normal(n)) * vol * c * 0.8 + scala / 64.0
    h = tick(np.maximum(o, c) + ampiezza)
    l = tick(np.minimum(o, c) - ampiezza * r.uniform(0.5, 1.5, n))
    volume = np.round(1000.0 * (vol / 0.001) * r.lognormal(0.0, 0.5, n), 2)
    indice = pd.date_range(inizio, periods=n, freq=f"{minuti}min", tz="UTC")
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": volume}, index=indice)


def scrivi_storico(cartella, symbol: str, timeframe: str, df: pd.DataFrame) -> str:
    """dati/<SYMBOL>_<TIMEFRAME>.csv: Date in UTC senza fuso scritto, Open, High, Low, Close, Volume."""
    os.makedirs(str(cartella), exist_ok=True)
    percorso = os.path.join(str(cartella), f"{symbol}_{timeframe}.csv")
    out = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    out.index = pd.DatetimeIndex(out.index).tz_convert("UTC").tz_localize(None)
    out.index.name = "Date"
    out.to_csv(percorso)
    return percorso


def funding_sintetico(df: pd.DataFrame, seme: int = 0, ore: int = 8) -> pd.DataFrame:
    """Un tasso ogni `ore` ore, alle ore esatte, dalla prima barra a dopo l'ultima: tassi di 1 bp circa, con il segno."""
    r = np.random.default_rng(10_000 + seme)
    idx = pd.DatetimeIndex(df.index)
    istanti = pd.date_range(idx[0].floor(f"{ore}h"), idx[-1] + pd.Timedelta(hours=ore), freq=f"{ore}h", tz="UTC")
    tasso = np.round(r.normal(0.0001, 0.0002, len(istanti)), 8)
    return pd.DataFrame({"tasso": tasso}, index=pd.DatetimeIndex(istanti, name="Date"))


def scrivi_funding(cartella, symbol: str, df: pd.DataFrame, seme: int = 0) -> str:
    percorso = file_funding(symbol, str(cartella))
    salva_funding(funding_sintetico(df, seme), percorso)
    return percorso
