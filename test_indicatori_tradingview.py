"""
Suite di validazione degli indicatori tradotti da script TradingView
(docs/51_INDICATORI_TRADINGVIEW.md). Cresce un indicatore alla volta:

    V1  Volume Flow Indicator [LazyBear]   E28 (trigger), F28 (filtri)
    V2  Relative Volume [veryfid]          F29 (filtri neutri)
    M1  Squeeze Momentum [LazyBear]        E29 (trigger), F30 (filtri)
    M2  WaveTrend [LazyBear]               E30 (trigger), F31 (filtri)
    R1  Kaufman Efficiency Ratio           F32 (filtri)
    R2  Hurst Exponent Oscillator [PhenLabs]  F33 (filtri neutri; licenza CC BY-NC-SA)

Per ogni indicatore, i quattro test obbligatori di docs/51 §4:

    1. nessun lookahead (troncamento: verifica_lookahead + confronto diretto
       serie intera / serie tagliata su punti casuali), con una trappola che
       deve risultare LOOKAHEAD;
    2. fedelta' a TradingView: il codice Pine originale fatto girare con
       PineTS sulle stesse barre (cartella strumenti_pinets/), confronto
       barra per barra dopo il riscaldamento; piu' una riscrittura
       indipendente a mano e casi a risultato noto;
    3. esecuzione su piu' symbol e timeframe, con il solo conteggio di
       quante volte scatta ogni condizione (nessun giudizio di trading);
    4. registrazione nel motore.

Si lancia da terminale, dalla cartella del progetto:

    python test_indicatori_tradingview.py

(su Windows: PYTHONIOENCODING=utf-8). Il test di fedelta' con PineTS gira
solo se ci sono Node.js e la cartella strumenti_pinets/node_modules (vedi
strumenti_pinets/LEGGIMI.md); quello multi-symbol solo se ci sono i file di
dati/. Se mancano, quei controlli vengono SALTATI e lo dice. Non serve MT5.
"""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import warnings

import numpy as np
import pandas as pd

warnings.simplefilter(action="ignore", category=FutureWarning)

from engine import registry as R
from engine.collaudo_catalogo import (mercato_sintetico, verifica_degenerazione,
                                      verifica_lookahead)
from engine.indicatori import (COLONNE_INDICATORI, _fine_regressione, aggiungi_indicatori,
                               efficienza_kaufman, hurst_rs, squeeze_momentum, volume_flow,
                               volume_relativo, wavetrend)
from helpers import _ts_rank
from entry_long import TRIGGER_LONG, registra_trigger_long
from entry_short import TRIGGER_SHORT, registra_trigger_short
from filter_conditions import (FILTRI, filter_ker_trend_down, filter_ker_trend_up, filter_rvol_high,
                               filter_sqz_mom_negative, filter_sqz_mom_positive,
                               filter_wt_above_signal, filter_wt_below_signal, registra_filtri)

# filtri scritti ma SPENTI perche' doppioni (docs/50 §7.5, decisione del 15/10/2026)
SPENTI = ("F29_RVOL_HIGH", "F30_SQZ_MOM_POSITIVE", "F30_SQZ_MOM_NEGATIVE", "F31_WT_ABOVE_SIGNAL",
          "F31_WT_BELOW_SIGNAL", "F32_KER_TREND_UP", "F32_KER_TREND_DOWN")

CARTELLA = os.path.dirname(os.path.abspath(__file__))
DATI = os.path.join(CARTELLA, "dati")
PINETS = os.path.join(CARTELLA, "strumenti_pinets")
PINE = os.path.join(CARTELLA, "pine_sources")
SYMBOL_PROVA = ("EURUSD", "BTCUSD", "DE40")
BARRE_PINETS = 20000          # ultime barre M15 di ogni symbol date a PineTS
TOLLERANZA = 1e-6             # |py - pine| <= TOLLERANZA x max(|pine|, mediana di |pine|)

# ---------------------------------------------------------------------------
# Gli indicatori sotto collaudo. Per aggiungerne uno: una voce qui.
#   colonne      colonna di aggiungi_indicatori -> funzione(df) che la calcola
#   pine         file Pine v5 per PineTS e, per ogni colonna, il nome del plot
#   riscaldamento barre dopo le quali il valore e' completo
#   entry/filtri nomi nei dizionari (direction)
#   trappola     la stessa grandezza calcolata con il difetto tipico (guarda
#                avanti): verifica_lookahead la deve segnare LOOKAHEAD
#   funzioni_engine  le funzioni di engine/indicatori.py chiamate da aggiungi_indicatori
#   (facoltativi)
#   confronti    coppie di colonne di cui confrontare con PineTS anche gli incroci
#   convergenza  barre dopo le quali il valore non dipende dal punto di partenza
#                (indicatori ricorsivi, ema); se manca vale `riscaldamento`
#   riscaldamento_condizioni  condizioni con una storia piu' lunga (percentili):
#                dove i dati sono piu' corti, nel test E non si pretende che scattino
#   pinets_ema_10_decimali  PineTS restituisce ta.ema arrotondata a 10 decimali:
#                il confronto "alla PineTS" arrotonda allo stesso modo (solo nel test)
#   pine_trasforma  funzione applicata alla colonna Python prima del confronto
#                (es. valore assoluto, quando lo script non ha il segno)
#   valore_dove_pine_nan  dove Pine da' na (0/0) la colonna Python vale questo
#   possono_mancare  {condizione: (timeframe, motivo)}: dove puo' restare sempre
#                falsa per un limite noto e dichiarato (nel test E e' una nota)
#   soglie       soglie delle condizioni: lo stato sopra/sotto deve coincidere con
#                PineTS, salvo le barre a meno di 1e-6 (relativo) dalla soglia
# ---------------------------------------------------------------------------
def _trappola_vfi(df):
    """Somma del volume col segno del tipico, CENTRATA sulla barra (65 barre avanti)."""
    tip = (df["High"] + df["Low"] + df["Close"]) / 3
    return (np.sign(tip.diff()).fillna(0.0) * df["Volume"]).rolling(130, center=True).sum()


def _trappola_rvol(df):
    """Volume diviso per la media CENTRATA su 31 barre (15 barre avanti)."""
    v = df["Volume"].astype(float)
    return v / v.rolling(31, center=True).mean() - 1.0


def _trappola_squeeze(df):
    """Retta di regressione del momentum letta 10 barre DOPO la barra corrente."""
    c = df["Close"]
    centro = ((df["High"].rolling(20).max() + df["Low"].rolling(20).min()) / 2 + c.rolling(20).mean()) / 2
    return _fine_regressione(c - centro, 20).shift(-10)


def _trappola_wavetrend(df):
    """WT1 meno WT1 di 3 barre DOPO (usa il futuro)."""
    wt1 = wavetrend(df)["wt1"]
    return wt1 - wt1.shift(-3)


def _trappola_ker(df):
    """KER calcolato verso il futuro: Close fra 10 barre meno Close di oggi."""
    c = df["Close"]
    return (c.shift(-10) - c) / c.diff().abs().rolling(10).sum().shift(-10)


def _trappola_hurst(df):
    """Hurst calcolato sulle 100 barre DOPO la barra corrente."""
    return hurst_rs(df["Close"]).shift(-100) - 0.5


INDICATORI = {
    "V1": dict(
        colonne={"vfi": volume_flow},
        pine=("V1_vfi_v5.pine", {"vfi": "vfi"}),
        riscaldamento=2 * 130 - 1,
        entry={"E28_VFI_CROSS_UP": 1, "E28_SHORT_VFI_CROSS_DOWN": -1},
        filtri={"F28_VFI_POSITIVE": 1, "F28_VFI_NEGATIVE": -1},
        coppie=[("VFI_SIGN", "F28_VFI_POSITIVE", "F28_VFI_NEGATIVE")],
        trappola=_trappola_vfi,
        funzioni_engine=("volume_flow",),
    ),
    "V2": dict(
        colonne={"rvol": lambda d: volume_relativo(d["Volume"])},
        pine=("V2_rvol_veryfid_v5.pine", {"rvol": "rvol"}),
        riscaldamento=30,
        riscaldamento_condizioni={"F29_RVOL_LOW": 530},
        entry={},
        filtri={"F29_RVOL_LOW": 0},      # F29_RVOL_HIGH spento: doppione di F3
        coppie=[],
        trappola=_trappola_rvol,
        funzioni_engine=("volume_relativo",),
    ),
    "M1": dict(
        colonne={"sqz_on": lambda d: squeeze_momentum(d)["sqz_on"],
                 "sqz_mom": lambda d: squeeze_momentum(d)["sqz_mom"]},
        pine=("M1_squeeze_v5.pine", {"sqz_on": "sqzOn", "sqz_mom": "val"}),
        riscaldamento=2 * 20 - 2,
        entry={"E29_SQUEEZE_RELEASE_UP": 1, "E29_SHORT_SQUEEZE_RELEASE_DOWN": -1},
        filtri={},                        # F30 spento: doppione
        coppie=[],
        trappola=_trappola_squeeze,
        funzioni_engine=("squeeze_momentum",),
    ),
    "M2": dict(
        colonne={"wt1": lambda d: wavetrend(d)["wt1"], "wt2": lambda d: wavetrend(d)["wt2"]},
        pine=("M2_wavetrend_v5.pine", {"wt1": "wt1", "wt2": "wt2"}),
        riscaldamento=2 * 10 + 21 - 3 + 3,
        convergenza=600,
        confronti=[("wt1", "wt2")],
        riscaldamento_condizioni={"E30_WAVETREND_CROSS_UP": 541, "E30_SHORT_WAVETREND_CROSS_DOWN": 541},
        pinets_ema_10_decimali=True,
        entry={"E30_WAVETREND_CROSS_UP": 1, "E30_SHORT_WAVETREND_CROSS_DOWN": -1},
        filtri={},                        # F31 spento: doppione
        coppie=[],
        trappola=_trappola_wavetrend,
        funzioni_engine=("wavetrend",),
    ),
    "R1": dict(
        colonne={"ker": lambda d: efficienza_kaufman(d["Close"])},
        pine=("R1_ker.pine", {"ker": "KER"}),
        pine_trasforma={"ker": np.abs},
        valore_dove_pine_nan={"ker": 0.0},
        riscaldamento=10,
        riscaldamento_condizioni={"F32_KER_RANGE": 510},
        entry={},
        filtri={"F32_KER_RANGE": 0},      # F32_KER_TREND spento: doppione
        coppie=[],
        trappola=_trappola_ker,
        funzioni_engine=("efficienza_kaufman",),
    ),
    "R2": dict(
        colonne={"hurst": lambda d: hurst_rs(d["Close"])},
        pine=("R2_hurst.pine", {"hurst": "Hurst Exponent (Smoothed)"}),
        soglie={"hurst": (0.6, 0.4)},
        possono_mancare={"F33_HURST_MEAN_REVERTING": (
            ("D1",), "H < 0,4 e' raro per la distorsione verso l'alto della stima R/S (su un cammino "
                     "casuale ~0,3% delle barre) e in D1 ci sono meno di 2.400 barre")},
        riscaldamento=103,
        convergenza=400,
        entry={},
        filtri={"F33_HURST_PERSISTENT": 0, "F33_HURST_MEAN_REVERTING": 0},
        coppie=[],
        trappola=_trappola_hurst,
        funzioni_engine=("hurst_rs",),
    ),
}

FUNZIONI = {**TRIGGER_LONG, **TRIGGER_SHORT, **{k: v[0] for k, v in FILTRI.items()}}


def _con_colonne(df: pd.DataFrame, chi=INDICATORI) -> pd.DataFrame:
    """Il df grezzo con le sole colonne degli indicatori sotto collaudo (piu' leggero di aggiungi_indicatori)."""
    d = df.copy()
    for spec in chi.values():
        for col, f in spec["colonne"].items():
            d[col] = f(d)
    return d


def _leggi(symbol: str) -> pd.DataFrame | None:
    percorso = os.path.join(DATI, f"{symbol}_M15.csv")
    if not os.path.exists(percorso):
        return None
    df = pd.read_csv(percorso, parse_dates=["Date"], index_col="Date")
    return df[["Open", "High", "Low", "Close", "Volume"]]


def _ricampiona(df: pd.DataFrame, regola: str) -> pd.DataFrame:
    """Barre di timeframe superiore dalle M15 (solo per il test di esecuzione)."""
    return (df.resample(regola, label="left", closed="left")
              .agg({"Open": "first", "High": "max", "Low": "min",
                    "Close": "last", "Volume": "sum"})
              .dropna())


def _sintetico_m5(n: int = 30000, seme: int = 11) -> pd.DataFrame:
    """Random walk M5 (non abbiamo dati M5: docs/51 §4.3, in attesa di decisione)."""
    idx = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
    idx = idx[idx.dayofweek < 5]
    rng = np.random.default_rng(seme)
    close = 1.10 * np.exp(np.cumsum(rng.normal(0, 0.0002, len(idx))))
    op = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"Open": op,
                         "High": np.maximum(op, close) + np.abs(rng.normal(0, 0.0001, len(idx))),
                         "Low": np.minimum(op, close) - np.abs(rng.normal(0, 0.0001, len(idx))),
                         "Close": close,
                         "Volume": rng.integers(10, 800, len(idx)).astype(float)}, index=idx)


def _pinets_disponibile() -> bool:
    return (shutil.which("node") is not None
            and os.path.isdir(os.path.join(PINETS, "node_modules", "pinets")))


def _pinets(df: pd.DataFrame, file_pine: str, cartella_tmp: str) -> pd.DataFrame:
    """Fa girare il Pine originale con PineTS sulle barre di df; un DataFrame dei plot."""
    dati = os.path.join(cartella_tmp, "dati.csv")
    uscita = os.path.join(cartella_tmp, "pine.csv")
    df.rename_axis("Date").to_csv(dati, date_format="%Y-%m-%d %H:%M:%S")
    subprocess.run(["node", "esegui_pine.mjs", dati, os.path.join(PINE, file_pine), uscita],
                   cwd=PINETS, check=True, capture_output=True, text=True)
    pine = pd.read_csv(uscita)
    pine.index = df.index
    return pine


# ---------------------------------------------------------------------------
# Riscritture indipendenti, ingenue, barra per barra: solo pietre di paragone
# ---------------------------------------------------------------------------
def _vfi_riferimento(df: pd.DataFrame, n: int = 130, coef: float = 0.2, vcoef: float = 2.5) -> np.ndarray:
    H, L, C, V = (df[c].to_numpy(dtype=float) for c in ("High", "Low", "Close", "Volume"))
    tip = (H + L + C) / 3
    N = len(df)
    inter = np.full(N, np.nan)
    inter[1:] = np.log(tip[1:]) - np.log(tip[:-1])
    vcp = np.zeros(N)
    for i in range(N):
        cutoff = coef * inter[i - 29:i + 1].std() * C[i] if i >= 30 else np.nan
        vave = V[i - n:i].mean() if i >= n else np.nan
        vc = min(V[i], vave * vcoef) if i >= n else np.nan
        mf = tip[i] - tip[i - 1] if i >= 1 else np.nan
        if np.isnan(cutoff):
            vcp[i] = 0.0
        elif mf > cutoff:
            vcp[i] = vc
        elif mf < -cutoff:
            vcp[i] = -vc
        else:
            vcp[i] = 0.0
    esito = np.full(N, np.nan)
    for i in range(2 * n - 1, N):
        esito[i] = vcp[i - n + 1:i + 1].sum() / V[i - n:i].mean()
    return esito


def _squeeze_riferimento(df: pd.DataFrame, n: int = 20, mult: float = 2.0,
                         mult_kc: float = 1.5) -> tuple[np.ndarray, np.ndarray]:
    H, L, C = (df[c].to_numpy(dtype=float) for c in ("High", "Low", "Close"))
    N = len(df)
    tr = np.full(N, np.nan)
    for i in range(1, N):
        tr[i] = max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1]))
    sqz = np.full(N, np.nan)
    scarto = np.full(N, np.nan)          # Close - centro del range
    for i in range(n - 1, N):
        w = C[i - n + 1:i + 1]
        bb_sup, bb_inf = w.mean() + mult * w.std(), w.mean() - mult * w.std()
        if i >= n:
            amp = tr[i - n + 1:i + 1].mean()
            kc_sup, kc_inf = w.mean() + mult_kc * amp, w.mean() - mult_kc * amp
            sqz[i] = float(bb_inf > kc_inf and bb_sup < kc_sup)
        centro = ((H[i - n + 1:i + 1].max() + L[i - n + 1:i + 1].min()) / 2 + w.mean()) / 2
        scarto[i] = C[i] - centro
    mom = np.full(N, np.nan)
    for i in range(2 * n - 2, N):
        pendenza, intercetta = np.polyfit(np.arange(n), scarto[i - n + 1:i + 1], 1)
        mom[i] = intercetta + pendenza * (n - 1)
    return sqz, mom


def _wavetrend_riferimento(df: pd.DataFrame, n1: int = 10, n2: int = 21) -> tuple[np.ndarray, np.ndarray]:
    """WaveTrend con le ema di Pine scritte a mano: partono dalla media semplice delle prime n."""
    def ema(x, n):
        out = np.full(len(x), np.nan)
        ok = np.flatnonzero(np.isfinite(x))
        if len(ok) < n:
            return out
        i0 = ok[0] + n - 1
        out[i0] = x[ok[0]:i0 + 1].mean()
        a = 2.0 / (n + 1)
        for i in range(i0 + 1, len(x)):
            out[i] = a * x[i] + (1 - a) * out[i - 1]
        return out
    ap = ((df["High"] + df["Low"] + df["Close"]) / 3).to_numpy(dtype=float)
    esa = ema(ap, n1)
    d = ema(np.abs(ap - esa), n1)
    wt1 = ema((ap - esa) / (0.015 * d), n2)
    wt2 = np.full(len(wt1), np.nan)
    for i in range(3, len(wt1)):
        wt2[i] = wt1[i - 3:i + 1].mean()
    return wt1, wt2


def main() -> int:
    ESITI: list[bool] = []

    def check(nome: str, condizione: bool, dettaglio: str = ""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def saltato(nome: str, motivo: str):
        print(f"  [SALTATO] {nome}  — {motivo}")

    mercato = mercato_sintetico("2024-01-01", "2024-07-01", seme=3)
    reali = {s: _leggi(s) for s in SYMBOL_PROVA}

    # =====================================================================
    print("\nA · V1 VOLUME FLOW: FORMULA E CASI A RISULTATO NOTO\n" + "-" * 70)
    vfi = volume_flow(mercato)
    rif = _vfi_riferimento(mercato)
    ok = np.isnan(rif) == vfi.isna().to_numpy()
    check("A1. NaN esattamente nelle prime 259 barre (2 x 130 - 1)",
          bool(vfi.iloc[:259].isna().all() and vfi.iloc[259:].notna().all() and ok.all()))
    scarto = np.nanmax(np.abs(vfi.to_numpy() - rif))
    check("A2. uguale alla riscrittura indipendente barra per barra", scarto < 1e-9, f"scarto massimo {scarto:.1e}")

    # salita regolare e poi discesa regolare, volume costante
    salita, discesa = 400, 200
    passi = np.r_[np.full(salita, 1.0005), np.full(discesa, 1 / 1.0005)]
    close = 1.10 * np.cumprod(passi)
    noto = pd.DataFrame({"Open": np.r_[close[0], close[:-1]], "High": close, "Low": close,
                         "Close": close, "Volume": 100.0},
                        index=pd.date_range("2024-01-01", periods=len(close), freq="15min", tz="UTC"))
    v = volume_flow(noto)
    check("A3. salita regolare a volume costante: VFI = 130 (tutto il volume e' 'in salita')",
          bool(np.allclose(v.iloc[300:salita], 130.0)))
    giu = FUNZIONI["E28_SHORT_VFI_CROSS_DOWN"](noto.assign(vfi=v))
    attesa = salita + 65          # 66a barra di discesa: 64 in salita - 66 in discesa < 0
    check("A4. l'incrocio sotto lo zero scatta alla 66a barra di discesa, una volta sola",
          list(np.flatnonzero(giu.to_numpy())) == [attesa], f"{list(np.flatnonzero(giu.to_numpy()))} attesa [{attesa}]")
    su = FUNZIONI["E28_VFI_CROSS_UP"](noto.assign(vfi=-v))
    check("A5. il long e' lo speculare dello short (stessa barra a segno rovesciato)",
          list(np.flatnonzero(su.to_numpy())) == [attesa])
    d = mercato.assign(vfi=vfi)
    pos, neg = FUNZIONI["F28_VFI_POSITIVE"](d), FUNZIONI["F28_VFI_NEGATIVE"](d)
    check("A6. filtri: mai veri insieme, falsi nel riscaldamento",
          not (pos & neg).any() and not pos.iloc[:259].any() and not neg.iloc[:259].any())
    piatto = noto.assign(Volume=0.0)
    check("A7. dati senza volume: VFI = 0 dopo il riscaldamento (nessun NaN)",
          bool((volume_flow(piatto).iloc[259:] == 0).all()))

    # =====================================================================
    print("\nA · V2 RELATIVE VOLUME: FORMULA E CASI A RISULTATO NOTO\n" + "-" * 70)
    rv = volume_relativo(mercato["Volume"])
    V = mercato["Volume"].to_numpy(dtype=float)
    rif_rv = np.full(len(V), np.nan)
    for i in range(30, len(V)):
        rif_rv[i] = V[i] / V[i - 30:i].mean()
    check("A17. NaN nelle prime 30 barre, poi uguale a volume / media delle 30 precedenti (a mano)",
          bool(rv.iloc[:30].isna().all()) and np.allclose(rv.to_numpy()[30:], rif_rv[30:], rtol=1e-14, atol=0))
    costante = pd.Series(100.0, index=pd.date_range("2024-01-01", periods=80, freq="15min", tz="UTC"))
    picco = costante.copy()
    picco.iloc[50] = 1000.0
    r = volume_relativo(picco)
    check("A18. volume costante: 1; picco di 10 volte: 10 sulla barra, 1/1,3 sulla successiva "
          "(il picco entra nella media), di nuovo 1 dopo 30 barre",
          bool(np.allclose(volume_relativo(costante).iloc[30:], 1.0)) and np.isclose(r.iloc[50], 10.0)
          and np.isclose(r.iloc[51], 1 / 1.3) and np.isclose(r.iloc[79], 1 / 1.3) and np.isclose(r.iloc[49], 1.0))
    check("A19. dati senza volume: 1 (normale) dopo il riscaldamento, nessun NaN",
          bool((volume_relativo(costante * 0).iloc[30:] == 1.0).all()))
    d = mercato.assign(rvol=rv)
    alto, basso = filter_rvol_high(d), FUNZIONI["F29_RVOL_LOW"](d)
    rango = _ts_rank(rv, 500)
    check("A20. F29: alto = rango >= 0,75, basso = rango <= 0,25 sulle ultime 500 barre; mai veri insieme; "
          "falsi nelle prime 529 barre",
          bool((alto == (rango >= 0.75)).all() and (basso == (rango <= 0.25)).all()
               and not (alto & basso).any() and not (alto | basso).iloc[:529].any()),
          f"alto {alto.mean():.0%}, basso {basso.mean():.0%} delle barre")

    # =====================================================================
    print("\nA · M1 SQUEEZE MOMENTUM: FORMULA E CASI A RISULTATO NOTO\n" + "-" * 70)
    sq = squeeze_momentum(mercato)
    rif_on, rif_mom = _squeeze_riferimento(mercato)
    check("A8. sqz_on dalla barra 20, sqz_mom dalla barra 38, poi nessun NaN",
          bool(sq["sqz_on"].iloc[:20].isna().all() and sq["sqz_on"].iloc[20:].notna().all()
               and sq["sqz_mom"].iloc[:38].isna().all() and sq["sqz_mom"].iloc[38:].notna().all()))
    scarto_mom = np.nanmax(np.abs(sq["sqz_mom"].to_numpy() - rif_mom))
    check("A9. uguale alla riscrittura indipendente (np.std, np.polyfit) barra per barra",
          np.array_equal(sq["sqz_on"].to_numpy(), rif_on, equal_nan=True) and scarto_mom < 1e-12,
          f"scarto massimo del momentum {scarto_mom:.1e}")

    # 200 barre ferme (oscillazione minima: Bollinger strette, squeeze acceso),
    # poi 60 barre in salita (o in discesa) forte: lo squeeze si spegne
    def _quiete_poi(passo):
        c = np.r_[1.1 + 0.00005 * (np.arange(200) % 2), 1.10005 + passo * np.arange(1, 61)]
        return pd.DataFrame({"Open": np.r_[c[0], c[:-1]], "High": c + 0.00005, "Low": c - 0.00005,
                             "Close": c, "Volume": 100.0},
                            index=pd.date_range("2024-01-01", periods=len(c), freq="15min", tz="UTC"))
    for verso, passo, lato, opposto in (("salita", 0.001, "E29_SQUEEZE_RELEASE_UP", "E29_SHORT_SQUEEZE_RELEASE_DOWN"),
                                        ("discesa", -0.001, "E29_SHORT_SQUEEZE_RELEASE_DOWN", "E29_SQUEEZE_RELEASE_UP")):
        d = _quiete_poi(passo)
        d = d.join(squeeze_momentum(d))
        ev = list(np.flatnonzero(FUNZIONI[lato](d).to_numpy()))
        check(f"A10. quiete poi {verso}: squeeze acceso nella quiete, {lato} scatta una volta sola "
              f"entro 5 barre dall'inizio del movimento, {opposto} mai",
              bool(d["sqz_on"].iloc[60:200].eq(1).all()) and len(ev) == 1 and 200 <= ev[0] < 205
              and not FUNZIONI[opposto](d).any(), f"evento alla barra {ev}")
    d = mercato.join(sq)
    pos, neg = filter_sqz_mom_positive(d), filter_sqz_mom_negative(d)
    ril = (d["sqz_on"].shift(1) == 1) & (d["sqz_on"] == 0)
    su, giu = FUNZIONI["E29_SQUEEZE_RELEASE_UP"](d), FUNZIONI["E29_SHORT_SQUEEZE_RELEASE_DOWN"](d)
    check("A11. filtri mai veri insieme; ogni rilascio e' un long o uno short secondo il segno del momentum",
          not (pos & neg).any() and not (su & giu).any()
          and ((su | giu) == (ril & d["sqz_mom"].notna() & (d["sqz_mom"] != 0))).all())

    # =====================================================================
    print("\nA · M2 WAVETREND: FORMULA E CASI A RISULTATO NOTO\n" + "-" * 70)
    wt = wavetrend(mercato)
    rif1, rif2 = _wavetrend_riferimento(mercato)
    check("A12. wt1 dalla barra 38, wt2 dalla 41, poi nessun NaN",
          bool(wt["wt1"].iloc[:38].isna().all() and wt["wt1"].iloc[38:].notna().all()
               and wt["wt2"].iloc[:41].isna().all() and wt["wt2"].iloc[41:].notna().all()))
    s1 = np.nanmax(np.abs(wt["wt1"].to_numpy() - rif1))
    s2 = np.nanmax(np.abs(wt["wt2"].to_numpy() - rif2))
    check("A13. uguale alla riscrittura a mano (ema di Pine barra per barra)",
          s1 < 1e-9 and s2 < 1e-9 and np.array_equal(np.isnan(rif1), wt["wt1"].isna().to_numpy()),
          f"scarto massimo {max(s1, s2):.1e}")
    # prezzo specchiato (C - prezzo, massimo e minimo scambiati): WT cambia
    # segno, quindi il long sul prezzo specchiato e' lo short sull'originale
    lungo_m = mercato_sintetico("2023-06-01", "2024-07-01", seme=8)
    k = 2 * float(lungo_m["Close"].mean())
    specchio = pd.DataFrame({"Open": k - lungo_m["Open"], "High": k - lungo_m["Low"],
                             "Low": k - lungo_m["High"], "Close": k - lungo_m["Close"],
                             "Volume": lungo_m["Volume"]}, index=lungo_m.index)
    d_o, d_s = lungo_m.join(wavetrend(lungo_m)), specchio.join(wavetrend(specchio))
    lo, ls = FUNZIONI["E30_WAVETREND_CROSS_UP"](d_s), FUNZIONI["E30_SHORT_WAVETREND_CROSS_DOWN"](d_o)
    diverse = int((lo != ls).sum())
    check("A14. il long sul prezzo specchiato coincide con lo short sull'originale (salvo pareggi nei ranghi)",
          int(ls.sum()) > 30 and diverse <= max(2, int(0.02 * ls.sum())),
          f"{int(ls.sum())} short, {diverse} barre diverse")
    rango = _ts_rank(d_o["wt1"], 500)
    su = FUNZIONI["E30_WAVETREND_CROSS_UP"](d_o)
    incrocio_su = (d_o["wt1"] > d_o["wt2"]) & (d_o["wt1"].shift(1) <= d_o["wt2"].shift(1))
    check("A15. ogni long: incrocio di WT1 sopra WT2 con WT1 nel 10% piu' basso delle ultime 500 barre; "
          "nessun segnale nelle prime 540 barre",
          bool(su.sum() > 30 and (incrocio_su & (rango <= 0.10))[su].all() and not su.iloc[:540].any()
               and (su == (incrocio_su & (rango <= 0.10))).all()), f"{int(su.sum())} long")
    sopra, sotto = filter_wt_above_signal(d_o), filter_wt_below_signal(d_o)
    check("A16. filtri F31 mai veri insieme, falsi nel riscaldamento", not (sopra & sotto).any()
          and not sopra.iloc[:41].any() and not sotto.iloc[:41].any())

    # =====================================================================
    print("\nA · R1 KAUFMAN EFFICIENCY RATIO: FORMULA E CASI A RISULTATO NOTO\n" + "-" * 70)
    ker = efficienza_kaufman(mercato["Close"])
    C = mercato["Close"].to_numpy(dtype=float)
    rif_k = np.full(len(C), np.nan)
    for i in range(10, len(C)):
        cammino = np.abs(np.diff(C[i - 10:i + 1])).sum()
        rif_k[i] = (C[i] - C[i - 10]) / cammino if cammino > 0 else 0.0
    check("A21. NaN nelle prime 10 barre, poi uguale alla riscrittura a mano (con il segno)",
          bool(ker.iloc[:10].isna().all()) and np.allclose(ker.to_numpy()[10:], rif_k[10:], rtol=1e-12, atol=1e-15))
    idx = pd.date_range("2024-01-01", periods=40, freq="15min", tz="UTC")
    retta = pd.Series(1.1 + 0.001 * np.arange(40), index=idx)
    zigzag = pd.Series(1.1 + 0.001 * (np.arange(40) % 2), index=idx)
    check("A22. salita in linea retta: +1; discesa: -1; zig-zag: 0; prezzo fermo: 0",
          bool(np.allclose(efficienza_kaufman(retta).iloc[10:], 1.0)
               and np.allclose(efficienza_kaufman(2.2 - retta).iloc[10:], -1.0)
               and np.allclose(efficienza_kaufman(zigzag).iloc[10:], 0.0)
               and (efficienza_kaufman(retta * 0 + 1.1).iloc[10:] == 0).all()))
    # cammino casuale, poi 60 barre di zig-zag (laterale), poi 60 di salita
    base = mercato_sintetico("2024-01-01", "2024-02-15", seme=4)["Close"].iloc[:1500]
    ultimo = float(base.iloc[-1])
    seq = np.r_[base.to_numpy(), ultimo + 0.0004 * (np.arange(1, 61) % 2), ultimo + 0.0004 + 0.0008 * np.arange(1, 61)]
    prezzo = pd.Series(seq, index=pd.date_range("2024-01-01", periods=len(seq), freq="15min", tz="UTC"))
    dk = pd.DataFrame({"Close": prezzo}).assign(ker=efficienza_kaufman(prezzo))
    lat, su_k, giu_k = FUNZIONI["F32_KER_RANGE"](dk), filter_ker_trend_up(dk), filter_ker_trend_down(dk)
    check("A23. laterale acceso in tutto lo zig-zag (dalla barra 11), spento nella salita; "
          "trend su acceso nella salita, trend giu' mai insieme al trend su",
          bool(lat.iloc[1511:1560].all() and not lat.iloc[1570:].any() and su_k.iloc[1575:].all()
               and not (su_k & giu_k).any()))
    check("A24. laterale falso nelle prime 509 barre (percentile su 500 barre di |KER|)",
          not FUNZIONI["F32_KER_RANGE"](mercato.assign(ker=ker)).iloc[:509].any())

    # =====================================================================
    print("\nA · R2 HURST (R/S): FORMULA E CASI A RISULTATO NOTO\n" + "-" * 70)
    corto = mercato.iloc[:1500]
    hu = hurst_rs(corto["Close"])
    Cc = corto["Close"].to_numpy(dtype=float)
    r = np.r_[0.0, np.log(Cc[1:] / Cc[:-1])]
    grezzo = np.full(len(r), np.nan)
    for i in range(99, len(r)):
        w = list(r[i - 99:i + 1])
        media = sum(w) / 100
        s = (sum((x - media) ** 2 for x in w) / 100) ** 0.5
        cum, profilo = 0.0, []
        for x in w:
            cum += x - media
            profilo.append(cum)
        rs = (max(profilo) - min(profilo)) / s if s > 1e-9 else 0.0
        grezzo[i] = np.log(rs) / np.log(100) if s > 1e-9 and rs > 1e-9 else 0.5
    rif_h = np.full(len(r), np.nan)
    rif_h[103] = grezzo[99:104].mean()
    for i in range(104, len(r)):
        rif_h[i] = 2 / 6 * grezzo[i] + 4 / 6 * rif_h[i - 1]
    scarto_h = np.nanmax(np.abs(hu.to_numpy() - rif_h))
    check("A25. NaN nelle prime 103 barre, poi uguale alla riscrittura a mano (cicli puri, ema di Pine)",
          bool(hu.iloc[:103].isna().all() and hu.iloc[103:].notna().all()) and scarto_h < 1e-12,
          f"scarto massimo {scarto_h:.1e}")
    idx = pd.date_range("2024-01-01", periods=300, freq="15min", tz="UTC")
    fermo = hurst_rs(pd.Series(1.1, index=idx))
    alterno = hurst_rs(pd.Series(1.1 * np.exp(0.001 * (np.arange(300) % 2)), index=idx))
    # rendimenti +x per 50 barre e -x per 50: profilo a triangolo, R = 50x,
    # S = x, R/S = 50, H = log 50 / log 100 = 0,849 su ogni finestra di 100
    passi = np.where((np.arange(1, 400) // 50) % 2 == 0, 0.001, -0.001)
    blocchi = hurst_rs(pd.Series(1.1 * np.exp(np.r_[0.0, np.cumsum(passi)]),
                                 index=pd.date_range("2024-01-01", periods=400, freq="15min", tz="UTC")))
    teorico = np.log(50) / np.log(100)
    check("A26. prezzo fermo: 0,5 (deviazione nulla); zig-zag perfetto: molto sotto 0,4; "
          "50 barre su e 50 giu': vicino a log 50 / log 100 = 0,85 (persistente)",
          bool(np.allclose(fermo.iloc[103:], 0.5) and (alterno.iloc[200:] < 0.4).all()
               and (blocchi.iloc[200:] > 0.6).all() and abs(float(blocchi.iloc[200:].median()) - teorico) < 0.02),
          f"zig-zag {float(alterno.iloc[-1]):.2f}, blocchi mediana {float(blocchi.iloc[200:].median()):.3f} "
          f"(teorico {teorico:.3f})")
    lungo_h = hurst_rs(mercato_sintetico("2023-01-01", "2025-01-01", seme=2)["Close"]).dropna()
    print(f"      (solo informativo) cammino casuale: H medio {lungo_h.mean():.3f}, "
          f"sopra 0,6 nel {(lungo_h > 0.6).mean():.1%}, sotto 0,4 nel {(lungo_h < 0.4).mean():.1%} delle barre "
          "(distorsione della stima R/S su 100 barre)")
    dh = mercato.assign(hurst=hurst_rs(mercato["Close"]))
    per, rit = FUNZIONI["F33_HURST_PERSISTENT"](dh), FUNZIONI["F33_HURST_MEAN_REVERTING"](dh)
    check("A27. F33: persistente = hurst > 0,6, ritorno = hurst < 0,4, mai veri insieme, falsi nel riscaldamento",
          bool((per == (dh["hurst"] > 0.6)).all() and (rit == (dh["hurst"] < 0.4)).all()
               and not (per & rit).any() and not (per | rit).iloc[:103].any()))

    # =====================================================================
    print("\nB · FEDELTA' A TRADINGVIEW (PineTS sul codice Pine originale)\n" + "-" * 70)
    if not _pinets_disponibile():
        saltato("B. confronto con PineTS", "manca Node.js o strumenti_pinets/node_modules")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            for chiave, spec in INDICATORI.items():
                file_pine, plot_di = spec["pine"]
                w = spec["riscaldamento"]
                for symbol, df in reali.items():
                    if df is None:
                        saltato(f"B. {chiave} su {symbol}", "manca il file di dati")
                        continue
                    pezzo = df.tail(BARRE_PINETS)
                    pine = _pinets(pezzo, file_pine, tmp)
                    esatto = {c: f(pezzo) for c, f in spec["colonne"].items()}
                    py_tutto = esatto
                    if spec.get("pinets_ema_10_decimali"):
                        import engine.indicatori as I
                        originale = I._ema_pine
                        try:
                            I._ema_pine = lambda s, n: originale(s, n).round(10)
                            py_tutto = {c: f(pezzo) for c, f in spec["colonne"].items()}
                        finally:
                            I._ema_pine = originale
                    trasforma = spec.get("pine_trasforma", {})
                    py_tutto = {c: trasforma.get(c, lambda x: x)(s) for c, s in py_tutto.items()}
                    esatto = {c: trasforma.get(c, lambda x: x)(s) for c, s in esatto.items()} \
                        if py_tutto is not esatto else py_tutto
                    pine = pine.copy()
                    for c, valore in spec.get("valore_dove_pine_nan", {}).items():
                        buchi = pine[plot_di[c]].isna() & (np.arange(len(pine)) >= w)
                        check(f"B. {chiave} {c} su {symbol}: dove Pine da' na (0/0, {int(buchi.sum())} barre) "
                              f"il Python vale {valore}", bool((py_tutto[c][buchi] == valore).all()))
                        pine.loc[buchi, plot_di[c]] = valore
                    serie = [(col, py_tutto[col], pine[plot_di[col]]) for col in spec["colonne"]]
                    serie += [(f"{a}-{b}", py_tutto[a] - py_tutto[b], pine[plot_di[a]] - pine[plot_di[b]])
                              for a, b in spec.get("confronti", [])]
                    for col, py, pn in serie:
                        py, pn = py.iloc[w:], pn.iloc[w:]
                        nan_diversi = int((py.isna() != pn.isna()).sum())
                        scala = np.maximum(pn.abs(), float(pn.abs().median()) or 1.0)
                        scarto = float(((py - pn).abs() / scala).max())
                        segni = int(((py > 0) != (pn > 0)).sum() + ((py < 0) != (pn < 0)).sum())
                        zero = pd.Series(0.0, index=py.index)
                        incroci = int((((py > zero) & (py.shift(1) <= zero)) !=
                                       ((pn > zero) & (pn.shift(1) <= zero))).iloc[1:].sum()
                                      + (((py < zero) & (py.shift(1) >= zero)) !=
                                         ((pn < zero) & (pn.shift(1) >= zero))).iloc[1:].sum())
                        modo = " (ema arrotondate come PineTS)" if spec.get("pinets_ema_10_decimali") else ""
                        check(f"B. {chiave} {col} su {symbol}{modo} ({len(py)} barre dopo il riscaldamento)",
                              nan_diversi == 0 and scarto <= TOLLERANZA and segni == 0 and incroci == 0,
                              f"scarto rel. max {scarto:.1e}, segni diversi {segni}, incroci diversi {incroci}")
                    for col, valori in spec.get("soglie", {}).items():
                        py, pn = py_tutto[col].iloc[w:], pine[plot_di[col]].iloc[w:]
                        diversi, vicini = 0, 0
                        for s in valori:
                            diverso = (py > s) != (pn > s)
                            pareggio = (pn - s).abs() <= TOLLERANZA * abs(s)
                            diversi += int((diverso & ~pareggio).sum())
                            vicini += int(pareggio.sum())
                        check(f"B. {chiave} {col} su {symbol}: sopra/sotto le soglie {valori} come PineTS",
                              diversi == 0, f"{diversi} barre diverse, {vicini} barre a meno di 1e-6 da una soglia")
                    if spec.get("pinets_ema_10_decimali"):
                        for col in spec["colonne"]:
                            pn = pine[plot_di[col]].iloc[w:]
                            scala = np.maximum(pn.abs(), float(pn.abs().median()) or 1.0)
                            print(f"      (solo informativo) {col} a precisione piena contro PineTS: scarto rel. max "
                                  f"{float(((esatto[col].iloc[w:] - pn).abs() / scala).max()):.1e}")

    # =====================================================================
    print("\nC · LOOKAHEAD (per troncamento)\n" + "-" * 70)
    nuove_entry = {k: v for s in INDICATORI.values() for k, v in s["entry"].items()}
    nuovi_filtri = {k: v for s in INDICATORI.values() for k, v in s["filtri"].items()}
    nuove_colonne = [c for s in INDICATORI.values() for c in s["colonne"]]

    trappole = {f"T_{k}": s["trappola"] for k, s in INDICATORI.items()}

    R.clear_registry()
    for k, v in nuove_entry.items():
        R.register_entry(k, v)(FUNZIONI[k])
    for k, v in nuovi_filtri.items():
        R.register_filter(k, direction=v)(FUNZIONI[k])
    for nome, f in trappole.items():
        R.register_filter(nome)(lambda df, f=f: f(df) > 0)

    def prepara(df):
        d = aggiungi_indicatori(df)
        for nome, f in trappole.items():
            d[nome.lower()] = f(d)
        return d

    for nome_dati, dati in [("mercato sintetico", mercato),
                            ("EURUSD vero, ultime 12000 barre", None if reali["EURUSD"] is None
                             else reali["EURUSD"].tail(12000))]:
        if dati is None:
            saltato(f"C. lookahead su {nome_dati}", "manca il file di dati")
            continue
        rep = verifica_lookahead(dati, prepara=prepara, verbose=False).set_index("nome")["esito"]
        for nome in trappole:
            check(f"C. {nome_dati}: la trappola {nome} ({trappole[nome].__doc__.strip()}) e' segnata LOOKAHEAD",
                  rep[nome] == "LOOKAHEAD" and rep[nome.lower()] == "LOOKAHEAD")
        non_ok = {k: rep[k] for k in list(nuove_entry) + list(nuovi_filtri) + nuove_colonne if rep[k] != "OK"}
        check(f"C. {nome_dati}: condizioni e colonne nuove OK (esercitate, nessun lookahead)",
              not non_ok, str(non_ok) if non_ok else "")
        vecchi = [c for c in COLONNE_INDICATORI if c not in nuove_colonne]
        check(f"C. {nome_dati}: gli indicatori di prima restano OK", all(rep[c] == "OK" for c in vecchi))

    rng = np.random.default_rng(0)
    for symbol, df in reali.items():
        if df is None:
            continue
        pezzo = df.tail(15000)
        for spec in INDICATORI.values():
            for col, f in spec["colonne"].items():
                intero = f(pezzo)
                punti = rng.integers(spec["riscaldamento"] + 10, len(pezzo), 20)
                diversi = 0
                for t in punti:
                    tagliato = f(pezzo.iloc[:t + 1])
                    a, b = intero.iloc[:t + 1].to_numpy(), tagliato.to_numpy()
                    diversi += int((~np.isclose(a, b, rtol=1e-12, atol=0, equal_nan=True)).sum())
                check(f"C. {col} su {symbol}: serie intera = serie tagliata, 20 punti casuali", diversi == 0,
                      f"{diversi} barre diverse" if diversi else "")

    # =====================================================================
    print("\nD · RISCALDAMENTO: lo stesso valore da qualunque punto partano i dati\n" + "-" * 70)
    lungo = mercato_sintetico("2023-01-01", "2024-01-01", seme=5)
    for spec in INDICATORI.values():
        for col, f in spec["colonne"].items():
            intero = f(lungo)
            peggio = 0.0
            for partenza in (700, 4001, 9050):
                parziale = f(lungo.iloc[partenza:])
                da = partenza + spec.get("convergenza", spec["riscaldamento"])
                peggio = max(peggio, float((parziale.loc[lungo.index[da:]] - intero.iloc[da:]).abs().max()))
            check(f"D. {col}: identico dopo {spec.get('convergenza', spec['riscaldamento'])} barre da 3 partenze diverse",
                  peggio < 1e-9, f"scarto massimo {peggio:.1e}")

    # =====================================================================
    print("\nE · ESECUZIONE SU PIU' SYMBOL E TIMEFRAME (solo conteggi)\n" + "-" * 70)
    insiemi = [("SINTETICO", "M5", _sintetico_m5())]
    for symbol, df in reali.items():
        if df is None:
            saltato(f"E. {symbol}", "manca il file di dati")
            continue
        insiemi += [(symbol, "M15", df), (symbol, "H1", _ricampiona(df, "1h")),
                    (symbol, "D1", _ricampiona(df, "1D"))]
    righe = []
    tutte_ok = True
    storia = {k: v for s in INDICATORI.values() for k, v in s.get("riscaldamento_condizioni", {}).items()}
    non_esercitabili = []
    mancare = {k: v for s in INDICATORI.values() for k, v in s.get("possono_mancare", {}).items()}
    for symbol, tf, df in insiemi:
        try:
            d = _con_colonne(df)
            riga = {"symbol": symbol, "tf": tf, "barre": len(d)}
            for nome in list(nuove_entry) + list(nuovi_filtri):
                s = FUNZIONI[nome](d).fillna(False).astype(bool)
                riga[nome] = int(s.sum())
                if len(d) < storia.get(nome, 0) + 100:
                    non_esercitabili.append(f"{nome} su {symbol} {tf}: storia piu' corta del riscaldamento "
                                            f"({len(d)} barre, ne servono {storia[nome]})")
                    tutte_ok &= bool(s.sum() == 0)
                elif nome in mancare and tf in mancare[nome][0] and s.sum() == 0:
                    non_esercitabili.append(f"{nome} su {symbol} {tf}: sempre falsa ({mancare[nome][1]})")
                elif nome in nuove_entry:
                    tutte_ok &= bool(s.sum() > 0 and not (s & s.shift(1, fill_value=False)).any())
                else:
                    tutte_ok &= bool(0 < s.sum() < len(s))
            righe.append(riga)
        except Exception as e:  # noqa: BLE001
            tutte_ok = False
            print(f"  ERRORE su {symbol} {tf}: {e}")
    tabella = pd.DataFrame(righe).set_index(["symbol", "tf"])
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(tabella.to_string())
    for riga in non_esercitabili:
        print(f"  nota: {riga}")
    check("E. gira ovunque; entry sono eventi e scattano; filtri ne' sempre veri ne' sempre falsi "
          "(salvo storia piu' corta del riscaldamento e limiti dichiarati: vedi le note)",
          tutte_ok and len(righe) == len(insiemi))
    if reali["EURUSD"] is not None:
        R.clear_registry()
        for k, v in nuove_entry.items():
            R.register_entry(k, v)(FUNZIONI[k])
        for k, v in nuovi_filtri.items():
            R.register_filter(k, direction=v)(FUNZIONI[k])
        deg = verifica_degenerazione(aggiungi_indicatori(reali["EURUSD"]), verbose=False).set_index("nome")
        print(deg[["esito"]].T.to_string())
        check("E. verifica_degenerazione su EURUSD M15: tutte OK",
              (deg["esito"] == "OK").all(), str(deg["esito"].to_dict()))

    # =====================================================================
    print("\nF · REGISTRAZIONE\n" + "-" * 70)
    R.clear_registry()
    with contextlib.redirect_stdout(io.StringIO()):
        registra_trigger_long()
        registra_trigger_short()
        registra_filtri()
    entries, filtri = set(R.list_entries()), set(R.list_filters())
    check("F1. le entry nuove sono registrate con il lato giusto",
          all(k in entries and k in R.list_entries(direction=v) for k, v in nuove_entry.items()))
    check("F2. i filtri nuovi sono registrati con la direction giusta",
          all(k in filtri and k in R.list_filters(direction=v) for k, v in nuovi_filtri.items()))
    coppie = R.list_filter_pairs()
    check("F3. le coppie di filtri sono riconosciute dalla ricerca dei filtri",
          all(c in coppie for s in INDICATORI.values() for c in s["coppie"]))
    check("F3b. i doppioni spenti non sono registrati: " + ", ".join(SPENTI),
          not any(k in filtri or k in FILTRI for k in SPENTI))
    check("F4. le colonne nuove sono nell'elenco che il collaudo verifica",
          set(nuove_colonne) <= set(COLONNE_INDICATORI))
    if reali["EURUSD"] is not None:
        import engine.indicatori as I
        pezzo = reali["EURUSD"].head(5000)
        con = aggiungi_indicatori(pezzo)
        originali = {nome: getattr(I, nome) for s in INDICATORI.values() for nome in s["funzioni_engine"]}
        try:   # le funzioni nuove senza NaN: le righe che toglierebbero gli indicatori di prima
            for nome, f in originali.items():
                setattr(I, nome, lambda *a, f=f, **k: f(*a, **k).fillna(0.0))
            senza = I.aggiungi_indicatori(pezzo)
        finally:
            for nome, f in originali.items():
                setattr(I, nome, f)
        check("F5. le righe tolte dal riscaldamento non cambiano con le colonne nuove",
              con.index.equals(senza.index), f"{len(con)} righe contro {len(senza)}")

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(main())
