"""
Suite di validazione delle condizioni entrate da articoli il 7 e l'8/10/2026
(metodo: 50_IDEE_DA_ARTICOLI.md).

    E24  ciclo dominante che gira        (Kaabar, Fourier)
    F23  ciclo forte
    X1   uscita sul giro del ciclo
    E25  cambio di stato del canale di trend adattivo (MarketStructureLab)
    F24/F25  istogramma del PVO sopra / sotto zero
    F26  due candele di fila nello stesso verso
    E26  cambio di direzione del Supertrend           (8/10, Sayedali Richu)
    F27  Intraday Intensity a 21 barre sopra / sotto zero
    E27  figure VSA d'ingresso                         (8/10, PyQuantLab)
    X2   uscita sulle figure VSA (al posto dell'uscita sulle EMA)

Si lancia da terminale, dalla cartella del progetto:

    python test_idee_articoli.py

Non serve MetaTrader 5 e non serve nessun file di dati. Dura circa un minuto.
"""
from __future__ import annotations

import contextlib
import io
import sys
import warnings

import numpy as np
import pandas as pd

warnings.simplefilter(action="ignore", category=FutureWarning)

from engine import registry as R
from engine.collaudo_catalogo import mercato_sintetico, verifica_lookahead
from engine.indicatori import (COLONNE_INDICATORI, aggiungi_indicatori,
                               canale_adattivo_regime, ciclo_dominante,
                               intraday_intensity, pvo_istogramma,
                               supertrend_direzione)
from helpers import _vsa_figure
from entry_long import TRIGGER_LONG, registra_trigger_long
from entry_short import TRIGGER_SHORT, registra_trigger_short
from exit_long import EXIT_LONG, registra_exit_long
from exit_short import EXIT_SHORT, registra_exit_short
from filter_conditions import FILTRI, registra_filtri

NUOVI_INDICATORI = ("ciclo_quota", "ciclo_pendenza", "atc_regime", "pvo_hist", "st_dir", "iix")


def _indice(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")


def _canale_riferimento(df: pd.DataFrame, n: int = 7, e: int = 2) -> np.ndarray:
    """
    Il canale adattivo riscritto in modo indipendente e ingenuo: una barra
    alla volta, con la retta di regressione calcolata da numpy.polyfit.
    Serve solo da pietra di paragone per la versione dell'engine.
    """
    H, L, C = (df[c].to_numpy() for c in ("High", "Low", "Close"))
    N = len(df)

    def fine_retta(a, i):
        if i - n + 1 < 0:
            return np.nan
        pendenza, intercetta = np.polyfit(np.arange(n), a[i - n + 1:i + 1], 1)
        return intercetta + pendenza * (n - 1)

    rh = np.array([fine_retta(H, i) for i in range(N)])
    rl = np.array([fine_retta(L, i) for i in range(N)])
    rc = np.array([fine_retta(C, i) for i in range(N)])
    esito = np.full(N, np.nan)
    regime, supporto, resistenza = None, np.nan, np.nan
    for i in range(N):
        if i < e - 1 or np.isnan(rh[i - e + 1]):
            continue
        alta, bassa = rh[i - e + 1:i + 1].mean(), rl[i - e + 1:i + 1].mean()
        picco, valle = rh[i - e + 1:i + 1].max(), rl[i - e + 1:i + 1].min()
        if regime is None:
            if i > n:
                regime, supporto = 1, rl[i]
        elif regime == 1:
            supporto = max(supporto, valle)
            if alta < supporto and rc[i] < rl[i - 1]:
                regime, resistenza = -1, rh[i]
        else:
            resistenza = min(resistenza, picco)
            if bassa > resistenza and rc[i] > rh[i - 1]:
                regime, supporto = 1, rl[i]
        if regime is not None:
            esito[i] = regime
    return esito


def _supertrend_riferimento(df: pd.DataFrame, periodo: int = 10, fattore: float = 3.0) -> np.ndarray:
    """
    Il Supertrend riscritto riga per riga dallo script di TradingView
    (ta.supertrend), con un ATR di Wilder calcolato a mano come TA-Lib.
    Restituisce la direzione nella convenzione del progetto (+1 su, -1 giu').
    Serve solo da pietra di paragone.
    """
    H, L, C = (df[c].to_numpy(dtype=float) for c in ("High", "Low", "Close"))
    n = len(df)
    tr = np.full(n, np.nan)
    for i in range(1, n):
        tr[i] = max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1]))
    atr = np.full(n, np.nan)
    if n > periodo:
        atr[periodo] = tr[1:periodo + 1].mean()
        for i in range(periodo + 1, n):
            atr[i] = (atr[i - 1] * (periodo - 1) + tr[i]) / periodo
    esito = np.full(n, np.nan)
    lower_prev = upper_prev = 0.0
    st_prev = np.nan
    for i in range(n):
        if np.isnan(atr[i]):
            continue
        src = (H[i] + L[i]) / 2
        upper, lower = src + fattore * atr[i], src - fattore * atr[i]
        lower = lower if (lower > lower_prev or C[i - 1] < lower_prev) else lower_prev
        upper = upper if (upper < upper_prev or C[i - 1] > upper_prev) else upper_prev
        if i == 0 or np.isnan(atr[i - 1]):
            direction = 1                       # convenzione TradingView: 1 = giu'
        elif st_prev == upper_prev:
            direction = -1 if C[i] > upper else 1
        else:
            direction = 1 if C[i] < lower else -1
        st = lower if direction == -1 else upper
        esito[i] = -direction                   # convenzione del progetto
        lower_prev, upper_prev, st_prev = lower, upper, st
    return esito


def _vsa_riferimento(df: pd.DataFrame) -> pd.Series:
    """
    Le figure VSA riscritte barra per barra come nel codice della fonte
    (classify_volume, classify_spread, classify_close_position,
    get_trend_direction, detect_vsa_patterns: vince la prima figura in
    ordine). Una stringa per barra, "" se nessuna figura.
    """
    O, H, L, C, V = (df[c].to_numpy(dtype=float) for c in ("Open", "High", "Low", "Close", "Volume"))
    n = len(df)
    sp = H - L
    esito = []
    for i in range(n):
        vma = V[i - 6:i + 1].mean() if i >= 6 else np.nan
        sma = sp[i - 6:i + 1].mean() if i >= 6 else np.nan
        tma = C[i - 29:i + 1].mean() if i >= 29 else np.nan
        if np.isnan(vma) or vma == 0 or V[i] == 0:
            vol = "normal"
        else:
            r = V[i] / vma
            vol = "climax" if r >= 2.0 else "high" if r >= 1.2 else "low" if r <= 0.5 else "normal"
        if np.isnan(sma) or sma == 0 or sp[i] == 0:
            spr = "normal"
        else:
            r = sp[i] / sma
            spr = "wide" if r >= 1.2 else "narrow" if r <= 1 / 1.2 else "normal"
        if sp[i] == 0:
            clo = "middle"
        else:
            cp = (C[i] - L[i]) / sp[i]
            clo = "high" if cp >= 0.7 else "low" if cp <= 0.3 else "middle"
        tr = "sideways" if np.isnan(tma) else "up" if C[i] > tma else "down" if C[i] < tma else "sideways"
        su, giu = C[i] > O[i], C[i] < O[i]
        nome = ""
        if vol == "climax" and spr == "wide" and tr == "down" and giu and clo in ("middle", "high"):
            nome = "stopping_volume"
        elif vol == "low" and spr == "narrow" and tr == "up" and giu and clo == "high":
            nome = "no_supply"
        elif vol == "high" and spr == "narrow" and tr == "up" and su and clo == "high":
            nome = "strength"
        elif vol == "high" and spr == "narrow" and tr == "down" and su and clo in ("middle", "low"):
            nome = "effort_up_reverse"
        elif vol == "climax" and spr == "wide" and tr == "up" and su and clo in ("middle", "low"):
            nome = "climax_sell"
        elif vol == "low" and spr == "narrow" and tr == "down" and su and clo == "low":
            nome = "no_demand"
        elif vol == "high" and spr == "narrow" and tr == "down" and giu and clo == "low":
            nome = "weakness"
        elif vol == "high" and spr == "narrow" and tr == "up" and giu and clo in ("middle", "high"):
            nome = "effort_down_reverse"
        esito.append(nome)
    return pd.Series(esito, index=df.index)


def esegui() -> int:
    """Esegue la suite. Ritorna 0 se tutto passa, 1 altrimenti."""
    ESITI = []

    def check(nome: str, condizione: bool, dettaglio: str = ""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    rng = np.random.default_rng(0)

    # =====================================================================
    print("\nA · CICLO DOMINANTE (E24, F23, X1)\n" + "-" * 70)
    # Un ciclo vero, noto: seno di periodo 40 barre sul log-prezzo. 40 non
    # e' un divisore di 300 (300/40 = 7,5): e' il caso piu' difficile, a
    # meta' fra due frequenze della trasformata.
    T, N = 40, 3000
    t = np.arange(N)
    seno = 0.002 * np.sin(2 * np.pi * t / T)
    close_seno = pd.Series(np.exp(np.log(1.10) + seno + np.cumsum(rng.normal(0, 2e-6, N))),
                           index=_indice(N))
    ciclo_seno = ciclo_dominante(close_seno)
    df_seno = pd.DataFrame({"Close": close_seno, **ciclo_seno})

    passeggiata = pd.Series(np.exp(np.log(1.10) + np.cumsum(rng.normal(0, 3e-4, 30_000))),
                            index=_indice(30_000))
    ciclo_rumore = ciclo_dominante(passeggiata)
    df_rumore = pd.DataFrame({"Close": passeggiata, **ciclo_rumore})

    check("A1. le prime 300 barre sono NaN, poi nessun NaN",
          bool(ciclo_seno.iloc[:300].isna().all().all() and ciclo_seno.iloc[300:].notna().all().all()))
    q_seno = float(ciclo_seno["ciclo_quota"].iloc[300:].median())
    q_rumore = float(ciclo_rumore["ciclo_quota"].iloc[300:].median())
    check("A2. ciclo vero: quota di energia sopra 0,90", q_seno > 0.90, f"{q_seno:.2f}")
    check("A3. passeggiata casuale: quota di energia sotto 0,15", q_rumore < 0.15, f"{q_rumore:.3f}")

    # Dove il seno gira davvero: prima barra in cui il rendimento cambia segno.
    r_vero = np.diff(seno, prepend=seno[0])
    minimi = np.flatnonzero((r_vero[1:] > 0) & (r_vero[:-1] <= 0)) + 1
    massimi = np.flatnonzero((r_vero[1:] < 0) & (r_vero[:-1] >= 0)) + 1
    minimi, massimi = minimi[minimi > 301], massimi[massimi > 301]

    e_long = TRIGGER_LONG["E24_CYCLE_TURN_UP"](df_seno)
    e_short = TRIGGER_SHORT["E24_SHORT_CYCLE_TURN_DOWN"](df_seno)
    pos_long = np.flatnonzero(e_long.to_numpy())
    pos_short = np.flatnonzero(e_short.to_numpy())
    pos_long, pos_short = pos_long[pos_long > 301], pos_short[pos_short > 301]

    def scarto_massimo(trovati, veri):
        return int(max(abs(trovati[np.argmin(np.abs(trovati - v))] - v) for v in veri))

    check("A4. E24 long: un evento per ogni minimo del ciclo, entro 1 barra",
          len(pos_long) == len(minimi) and scarto_massimo(pos_long, minimi) <= 1,
          f"{len(pos_long)} eventi, {len(minimi)} minimi, scarto massimo {scarto_massimo(pos_long, minimi)} barre")
    check("A5. E24 short: un evento per ogni massimo del ciclo, entro 1 barra",
          len(pos_short) == len(massimi) and scarto_massimo(pos_short, massimi) <= 1,
          f"{len(pos_short)} eventi, {len(massimi)} massimi, scarto massimo {scarto_massimo(pos_short, massimi)} barre")
    tutti = sorted([(int(p), 1) for p in pos_long] + [(int(p), -1) for p in pos_short])
    alternati = all(x[1] != y[1] for x, y in zip(tutti, tutti[1:]))
    check("A6. minimi e massimi si alternano (mai due long di fila)", bool(alternati))

    # speculare: sul prezzo capovolto lo short e' il long
    capovolto = pd.Series(np.exp(-np.log(passeggiata.to_numpy())), index=passeggiata.index)
    df_cap = pd.DataFrame({"Close": capovolto, **ciclo_dominante(capovolto)})
    l1 = TRIGGER_LONG["E24_CYCLE_TURN_UP"](df_rumore)
    s2 = TRIGGER_SHORT["E24_SHORT_CYCLE_TURN_DOWN"](df_cap)
    diversi = int((l1 != s2).sum())
    check("A7. sul prezzo capovolto E24 short coincide con E24 long (a meno di arrotondamenti)",
          diversi <= 3, f"{diversi} barre diverse su {int(l1.sum())} eventi")

    x_long = EXIT_LONG["X1_CYCLE_TURN_DOWN"][0](df_rumore)
    x_short = EXIT_SHORT["X1_SHORT_CYCLE_TURN_UP"][0](df_rumore)
    check("A8. X1 long (chiudi il long) = giro al ribasso = stesso evento di E24 short",
          bool(x_long.equals(TRIGGER_SHORT["E24_SHORT_CYCLE_TURN_DOWN"](df_rumore))))
    check("A9. X1 short (chiudi lo short) = giro al rialzo = stesso evento di E24 long",
          bool(x_short.equals(l1)))
    check("A10. entry e uscite sono eventi: mai vere su due barre di fila",
          not any(bool((s & s.shift(1, fill_value=False)).any()) for s in (l1, s2, x_long, x_short)))

    f23 = FILTRI["F23_CYCLE_STRENGTH"][0](df_rumore)
    cop = float(f23.iloc[2300:].mean())
    check("A11. F23: falso finche' manca la storia (prime 2299 barre)", not bool(f23.iloc[:2299].any()))
    check("A12. F23: vero circa il 30% delle barre (fra 20% e 40%)", 0.20 <= cop <= 0.40, f"{cop:.1%}")

    piatto = ciclo_dominante(pd.Series(1.10, index=_indice(800)))
    check("A13. prezzo fermo: nessun NaN oltre il riscaldamento, quota e pendenza a zero",
          bool(piatto.iloc[300:].notna().all().all() and (piatto.iloc[300:] == 0).all().all()))

    # =====================================================================
    print("\nB · CANALE DI TREND ADATTIVO (E25)\n" + "-" * 70)
    mercato = mercato_sintetico("2024-01-01", "2024-04-01", seme=3)
    mio = canale_adattivo_regime(mercato).to_numpy()
    rif = _canale_riferimento(mercato)
    uguali = (mio == rif) | (np.isnan(mio) & np.isnan(rif))
    check("B1. identico alla riscrittura indipendente barra per barra",
          bool(uguali.all()), f"{int((~uguali).sum())} barre diverse su {len(mio)}, "
          f"{int((np.diff(mio[9:]) != 0).sum())} cambi di stato")
    check("B2. solo +1 e -1, NaN soltanto nelle prime 8 barre",
          bool(np.isnan(mio[:8]).all() and np.isin(mio[8:], (1.0, -1.0)).all()))

    # salita, discesa, salita: un solo cambio per gamba
    gamba = np.r_[np.linspace(1.1000, 1.1100, 80), np.linspace(1.1100, 1.1000, 80)[1:],
                  np.linspace(1.1000, 1.1100, 80)[1:]]
    # barre strette (0,4 pips) rispetto al passo (1,3 pips): il canale cambia
    # stato solo se la chiusura lisciata supera il minimo lisciato di prima
    zigzag = pd.DataFrame({"Open": gamba, "High": gamba + 0.00002, "Low": gamba - 0.00002,
                           "Close": gamba, "Volume": 100.0}, index=_indice(len(gamba)))
    zigzag["atc_regime"] = canale_adattivo_regime(zigzag)
    giu = np.flatnonzero(TRIGGER_SHORT["E25_SHORT_ADAPTIVE_CHANNEL_DOWN"](zigzag).to_numpy())
    su = np.flatnonzero(TRIGGER_LONG["E25_ADAPTIVE_CHANNEL_UP"](zigzag).to_numpy())
    check("B3. salita-discesa-salita: un solo E25 short, poco dopo il massimo (barra 79)",
          len(giu) == 1 and 79 < giu[0] <= 79 + 10, f"barre {[int(x) for x in giu]}")
    check("B4. salita-discesa-salita: un solo E25 long, poco dopo il minimo (barra 158)",
          len(su) == 1 and 158 < su[0] <= 158 + 10, f"barre {[int(x) for x in su]}")

    # speculare esatto: prezzi cambiati di segno, massimi e minimi scambiati
    specchio = pd.DataFrame({"Open": -mercato["Open"], "High": -mercato["Low"],
                             "Low": -mercato["High"], "Close": -mercato["Close"]},
                            index=mercato.index)
    a = pd.DataFrame({"atc_regime": mio}, index=mercato.index)
    b = pd.DataFrame({"atc_regime": canale_adattivo_regime(specchio)}, index=mercato.index)
    da = 50          # le prime barre differiscono: entrambi partono rialzisti per convenzione
    check("B5. sul mercato capovolto E25 short coincide con E25 long",
          bool(TRIGGER_LONG["E25_ADAPTIVE_CHANNEL_UP"](a).iloc[da:].equals(
              TRIGGER_SHORT["E25_SHORT_ADAPTIVE_CHANNEL_DOWN"](b).iloc[da:])))

    # =====================================================================
    print("\nC · PVO (F24, F25) E DUE CANDELE (F26)\n" + "-" * 70)
    n = 600
    costante = pd.DataFrame({"pvo_hist": pvo_istogramma(pd.Series(500.0, index=_indice(n)))})
    check("C1. volume costante: nessuno dei due filtri e' mai vero",
          not bool(FILTRI["F24_PVO_HIST_POSITIVE"][0](costante).any()
                   or FILTRI["F25_PVO_HIST_NEGATIVE"][0](costante).any()))
    vol = np.full(n, 500.0)
    vol[200:400] = 1500.0                      # il volume triplica alla barra 200, torna giu' alla 400
    gradino = pd.DataFrame({"pvo_hist": pvo_istogramma(pd.Series(vol, index=_indice(n)))})
    pos = FILTRI["F24_PVO_HIST_POSITIVE"][0](gradino).to_numpy()
    neg = FILTRI["F25_PVO_HIST_NEGATIVE"][0](gradino).to_numpy()
    check("C2. il volume sale di colpo: F24 vero sulle 5 barre successive, F25 falso",
          bool(pos[200:205].all() and not neg[200:205].any()))
    check("C3. il volume scende di colpo: F25 vero sulle 5 barre successive, F24 falso",
          bool(neg[400:405].all() and not pos[400:405].any()))
    check("C4. F24 e F25 non sono mai veri insieme", not bool((pos & neg).any()))
    zero = pvo_istogramma(pd.Series(0.0, index=_indice(200)))
    check("C5. volumi tutti a zero: nessun NaN oltre il riscaldamento",
          bool(zero.iloc[40:].notna().all() and (zero.iloc[40:] == 0).all()))

    #            barra:  0     1     2     3     4     5     6     7
    apre = np.array([1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00])
    chiude = np.array([1.01, 1.02, 0.99, 1.01, 1.01, 0.98, 0.97, 1.00])
    candele = pd.DataFrame({"Open": apre, "Close": chiude}, index=_indice(8))
    su2 = FILTRI["F26_TWO_BARS_UP"][0](candele).to_numpy()
    giu2 = FILTRI["F26_TWO_BARS_DOWN"][0](candele).to_numpy()
    check("C6. F26 su: vero solo sulle barre 1 e 4",
          list(np.flatnonzero(su2)) == [1, 4], f"{[int(x) for x in np.flatnonzero(su2)]}")
    check("C7. F26 giu': vero solo sulla barra 6 (la 7 chiude pari: ne' su ne' giu')",
          list(np.flatnonzero(giu2)) == [6], f"{[int(x) for x in np.flatnonzero(giu2)]}")

    # =====================================================================
    print("\nD · REGISTRAZIONE\n" + "-" * 70)
    R.clear_registry()
    with contextlib.redirect_stdout(io.StringIO()):
        registra_trigger_long(); registra_trigger_short()
        registra_exit_long(); registra_exit_short(); registra_filtri()
    attesi_entry = {"E24_CYCLE_TURN_UP": 1, "E24_SHORT_CYCLE_TURN_DOWN": -1,
                    "E25_ADAPTIVE_CHANNEL_UP": 1, "E25_SHORT_ADAPTIVE_CHANNEL_DOWN": -1,
                    "E26_SUPERTREND_UP": 1, "E26_SHORT_SUPERTREND_DOWN": -1,
                    "E27_VSA_BULLISH": 1, "E27_SHORT_VSA_BEARISH": -1}
    check("D1. le otto entry nuove sono registrate con il lato giusto",
          all(k in R.list_entries() and R.get_entry_direction(k) == v
              for k, v in attesi_entry.items()))
    attesi_filtri = {"F23_CYCLE_STRENGTH": (0, None), "F24_PVO_HIST_POSITIVE": (0, None),
                     "F25_PVO_HIST_NEGATIVE": (0, None), "F26_TWO_BARS_UP": (1, "TWO_BARS"),
                     "F26_TWO_BARS_DOWN": (-1, "TWO_BARS"),
                     "F27_IIX_POSITIVE": (1, "IIX"), "F27_IIX_NEGATIVE": (-1, "IIX")}
    check("D2. i sette filtri nuovi sono registrati con direction e pair giusti",
          all(k in R.list_filters() and (R.get_filter_direction(k), R.get_filter_pair(k)) == v
              for k, v in attesi_filtri.items()))
    coppie_f = R.list_filter_pairs()
    check("D3. le coppie TWO_BARS e IIX sono riconosciute dalla ricerca dei filtri",
          ("TWO_BARS", "F26_TWO_BARS_UP", "F26_TWO_BARS_DOWN") in coppie_f
          and ("IIX", "F27_IIX_POSITIVE", "F27_IIX_NEGATIVE") in coppie_f)
    coppie_x = R.list_exit_pairs()
    check("D4. le coppie di uscite CYCLE_TURN e VSA sono riconosciute dalla ricerca delle uscite",
          ("CYCLE_TURN", "X1_CYCLE_TURN_DOWN", "X1_SHORT_CYCLE_TURN_UP") in coppie_x
          and ("VSA", "X2_VSA_BEARISH", "X2_SHORT_VSA_BULLISH") in coppie_x)
    uscite = set(R.list_exits())
    check("D5. uscite: X0 e X3 come prima, X1 sul ciclo, X2 sulla VSA; RSI ed EMA non ci sono piu'",
          {"X0_NO_EXIT", "X0_SHORT_NO_EXIT", "X1_CYCLE_TURN_DOWN", "X1_SHORT_CYCLE_TURN_UP",
           "X2_VSA_BEARISH", "X2_SHORT_VSA_BULLISH", "X3_MACD_BEARISH", "X3_SHORT_MACD_BULLISH"} == uscite,
          f"{sorted(uscite)}")
    check("D6. i sei indicatori nuovi sono nell'elenco che il collaudo verifica",
          set(NUOVI_INDICATORI) <= set(COLONNE_INDICATORI))

    # =====================================================================
    print("\nE · LOOKAHEAD (per troncamento) E RISCALDAMENTO\n" + "-" * 70)
    nuove_uscite = {"X1_CYCLE_TURN_DOWN": 1, "X1_SHORT_CYCLE_TURN_UP": -1,
                    "X2_VSA_BEARISH": 1, "X2_SHORT_VSA_BULLISH": -1}
    nuove = list(attesi_entry) + list(attesi_filtri) + list(nuove_uscite)
    funzioni = {**TRIGGER_LONG, **TRIGGER_SHORT,
                **{k: v[0] for k, v in FILTRI.items()},
                **{k: v[0] for k, v in EXIT_LONG.items()},
                **{k: v[0] for k, v in EXIT_SHORT.items()}}
    R.clear_registry()
    for k, v in attesi_entry.items():
        R.register_entry(k, v)(funzioni[k])
    for k in attesi_filtri:
        R.register_filter(k)(funzioni[k])
    for k, v in nuove_uscite.items():
        R.register_exit(k, v)(funzioni[k])

    # Le trappole: il difetto dell'articolo, messo apposta. Trasformata di
    # Fourier sull'INTERO campione, si tengono le 10 onde piu' forti e si
    # ricostruisce il prezzo "lisciato": ogni punto dipende da tutta la serie.
    def _lisciato_campione_intero(close: pd.Series) -> pd.Series:
        x = close.to_numpy(dtype=float)
        spettro = np.fft.fft(x)
        tieni = np.r_[0, np.argsort(np.abs(spettro[1:]))[-10:] + 1]
        filtrato = np.zeros_like(spettro)
        filtrato[tieni] = spettro[tieni]
        return pd.Series(np.fft.ifft(filtrato).real, index=close.index)

    def t_fft_campione_intero(df):
        return df["Close"] > _lisciato_campione_intero(df["Close"])

    def prepara_con_trappola(df):
        d = aggiungi_indicatori(df)
        d["fft_campione_intero"] = _lisciato_campione_intero(d["Close"])
        return d

    R.register_filter("T_FFT_CAMPIONE_INTERO")(t_fft_campione_intero)
    rep = verifica_lookahead(mercato_sintetico(), prepara=prepara_con_trappola, verbose=False)
    esito = rep.set_index("nome")["esito"]
    check("E1. la trappola (Fourier sull'intero campione) viene segnata LOOKAHEAD",
          esito["T_FFT_CAMPIONE_INTERO"] == "LOOKAHEAD" and esito["fft_campione_intero"] == "LOOKAHEAD")
    non_ok = {k: esito[k] for k in nuove if esito[k] != "OK"}
    check(f"E2. le {len(nuove)} condizioni nuove risultano OK (nessun lookahead, tutte esercitate)",
          not non_ok, f"{non_ok}" if non_ok else "")
    ind_non_ok = {k: esito[k] for k in NUOVI_INDICATORI if esito[k] != "OK"}
    check(f"E3. i {len(NUOVI_INDICATORI)} indicatori nuovi risultano OK", not ind_non_ok, f"{ind_non_ok}" if ind_non_ok else "")
    vecchi = [c for c in COLONNE_INDICATORI if c not in NUOVI_INDICATORI]
    check("E4. gli indicatori di prima risultano ancora OK",
          all(esito[c] == "OK" for c in vecchi))

    # riscaldamento: stessa colonna da qualunque punto partano i dati
    lungo = mercato_sintetico("2023-01-01", "2024-01-01", seme=5)
    intero = aggiungi_indicatori(lungo)
    taglio = 3000
    peggio = {}
    for partenza in (700, 4001, 9050):
        parziale = aggiungi_indicatori(lungo.iloc[partenza:])
        comune = parziale.index[taglio:]
        for k in nuove:
            diverse = int((funzioni[k](intero).loc[comune] != funzioni[k](parziale).loc[comune]).sum())
            peggio[k] = max(peggio.get(k, 0), diverse)
    sporche = {k: v for k, v in peggio.items() if v}
    check(f"E5. dopo {taglio} barre le condizioni non dipendono dal punto di partenza dei dati",
          not sporche, f"{sporche}" if sporche else "")
    R.clear_registry()

    # =====================================================================
    print("\nF · SUPERTREND (E26)\n" + "-" * 70)
    mercato = mercato_sintetico("2024-01-01", "2024-04-01", seme=11)
    mio = supertrend_direzione(mercato).to_numpy()
    rif = _supertrend_riferimento(mercato)
    uguali = (mio == rif) | (np.isnan(mio) & np.isnan(rif))
    check("F1. identico alla riscrittura riga per riga dello script di TradingView",
          bool(uguali.all()), f"{int((~uguali).sum())} barre diverse su {len(mio)}, "
          f"{int((np.diff(mio[10:]) != 0).sum())} cambi di direzione")
    check("F2. solo +1 e -1, NaN soltanto nelle prime 10 barre (ATR a 10)",
          bool(np.isnan(mio[:10]).all() and np.isin(mio[10:], (1.0, -1.0)).all()))
    gamba = np.r_[np.linspace(1.1000, 1.1100, 80), np.linspace(1.1100, 1.1000, 80)[1:],
                  np.linspace(1.1000, 1.1100, 80)[1:]]
    zigzag = pd.DataFrame({"Open": gamba, "High": gamba + 0.00002, "Low": gamba - 0.00002,
                           "Close": gamba, "Volume": 100.0}, index=_indice(len(gamba)))
    zigzag["st_dir"] = supertrend_direzione(zigzag)
    giu = np.flatnonzero(TRIGGER_SHORT["E26_SHORT_SUPERTREND_DOWN"](zigzag).to_numpy())
    su = np.flatnonzero(TRIGGER_LONG["E26_SUPERTREND_UP"](zigzag).to_numpy())
    check("F3. salita-discesa-salita: un E26 short poco dopo il massimo (barra 79)",
          len(giu) == 1 and 79 < giu[0] <= 79 + 15, f"barre {[int(x) for x in giu]}")
    check("F4. salita-discesa-salita: due E26 long, alla partenza e poco dopo il minimo (barra 158)",
          len(su) == 2 and su[0] < 30 and 158 < su[1] <= 158 + 15, f"barre {[int(x) for x in su]}")
    specchio = pd.DataFrame({"Open": -mercato["Open"], "High": -mercato["Low"],
                             "Low": -mercato["High"], "Close": -mercato["Close"]}, index=mercato.index)
    a = pd.DataFrame({"st_dir": mio}, index=mercato.index)
    b = pd.DataFrame({"st_dir": supertrend_direzione(specchio)}, index=mercato.index)
    da = 100        # le prime barre differiscono: entrambi partono ribassisti per convenzione
    check("F5. sul mercato capovolto E26 short coincide con E26 long",
          bool(TRIGGER_LONG["E26_SUPERTREND_UP"](a).iloc[da:].equals(
              TRIGGER_SHORT["E26_SHORT_SUPERTREND_DOWN"](b).iloc[da:])))

    # =====================================================================
    print("\nG · INTRADAY INTENSITY (F27)\n" + "-" * 70)
    mio = intraday_intensity(mercato).to_numpy()
    H, L, C, V = (mercato[c].to_numpy() for c in ("High", "Low", "Close", "Volume"))
    per_barra = [(2 * C[i] - H[i] - L[i]) * V[i] / ((H[i] - L[i]) if H[i] != L[i] else 1.0)
                 for i in range(len(C))]
    rif = np.array([np.nan if i < 20 else sum(per_barra[i - 20:i + 1]) for i in range(len(C))])
    check("G1. uguale allo script di TradingView riscritto barra per barra (somma su 21)",
          bool(np.allclose(mio, rif, rtol=1e-9, atol=1e-12, equal_nan=True)
               and (np.sign(mio[20:]) == np.sign(rif[20:])).all()))
    n = 60
    alti = pd.DataFrame({"Open": 1.0, "High": 1.002, "Low": 1.000, "Close": 1.0019,
                         "Volume": 100.0}, index=_indice(n))
    bassi = alti.assign(Close=1.0001)
    alti["iix"], bassi["iix"] = intraday_intensity(alti), intraday_intensity(bassi)
    pos_a, neg_a = (FILTRI[k][0](alti).to_numpy() for k in ("F27_IIX_POSITIVE", "F27_IIX_NEGATIVE"))
    pos_b, neg_b = (FILTRI[k][0](bassi).to_numpy() for k in ("F27_IIX_POSITIVE", "F27_IIX_NEGATIVE"))
    check("G2. chiusure sempre in alto: F27 positivo vero dalla barra 21, negativo mai",
          bool(not pos_a[:20].any() and pos_a[20:].all() and not neg_a.any()))
    check("G3. chiusure sempre in basso: F27 negativo vero dalla barra 21, positivo mai",
          bool(not neg_b[:20].any() and neg_b[20:].all() and not pos_b.any()))
    piatte = alti.assign(High=1.0, Low=1.0, Close=1.0)
    ii = intraday_intensity(piatte)
    check("G4. barre piatte (massimo = minimo): valgono zero, nessun NaN dopo 21 barre",
          bool(ii.iloc[20:].notna().all() and (ii.iloc[20:] == 0).all()))

    # =====================================================================
    print("\nH · VOLUME SPREAD ANALYSIS (E27, X2)\n" + "-" * 70)
    mercato = mercato_sintetico("2024-01-01", "2024-07-01", seme=4)
    figure = _vsa_figure(mercato)
    rif = _vsa_riferimento(mercato)
    diverse = {k: int((v.to_numpy() != (rif == k).to_numpy()).sum()) for k, v in figure.items()}
    quante = {k: int(v.sum()) for k, v in figure.items()}
    check("H1. le sei figure coincidono con il codice della fonte riscritto barra per barra",
          not any(diverse.values()) and min(quante.values()) > 0, f"barre per figura: {quante}")
    rialziste = figure["stopping_volume"] | figure["no_supply"] | figure["effort_up_reverse"]
    ribassiste = figure["climax_sell"] | figure["no_demand"] | figure["effort_down_reverse"]
    check("H2. nessuna barra e' insieme una figura rialzista e una ribassista",
          not bool((rialziste & ribassiste).any()))
    e_l = TRIGGER_LONG["E27_VSA_BULLISH"](mercato)
    e_s = TRIGGER_SHORT["E27_SHORT_VSA_BEARISH"](mercato)
    x_l = EXIT_LONG["X2_VSA_BEARISH"][0](mercato)
    x_s = EXIT_SHORT["X2_SHORT_VSA_BULLISH"][0](mercato)
    check("H3. ogni E27 long cade su una barra di X2 short (chiudi lo short) e viceversa",
          bool((e_l <= x_s).all() and (e_s <= x_l).all() and e_l.any() and e_s.any()))
    check("H4. E27 sono eventi: mai veri su due barre di fila",
          not bool((e_l & e_l.shift(1, fill_value=False)).any()
                   or (e_s & e_s.shift(1, fill_value=False)).any()))
    specchio = pd.DataFrame({"Open": -mercato["Open"], "High": -mercato["Low"],
                             "Low": -mercato["High"], "Close": -mercato["Close"],
                             "Volume": mercato["Volume"]}, index=mercato.index)
    diverse_s = int((TRIGGER_SHORT["E27_SHORT_VSA_BEARISH"](specchio) != e_l).sum())
    diverse_x = int((EXIT_SHORT["X2_SHORT_VSA_BULLISH"][0](specchio) != x_l).sum())
    check("H5. sul mercato capovolto E27 short = E27 long e X2 short = X2 long (a meno di arrotondamenti)",
          diverse_s <= 2 and diverse_x <= 2, f"{diverse_s} e {diverse_x} barre diverse")
    # uno "stopping volume" costruito a mano: 40 barre in discesa con volume e
    # ampiezza costanti, poi una barra rossa con volume triplo, ampiezza doppia
    # e chiusura a meta' barra
    k = 41
    o = 1.1000 - 0.0001 * np.arange(k)
    c = o - 0.00005
    h, l = o + 0.00005, c - 0.00005
    v = np.full(k, 100.0)
    o[-1], c[-1] = o[-2] - 0.00005, o[-2] - 0.00015
    h[-1], l[-1] = o[-1] + 0.00005, o[-1] - 0.00025      # ampiezza 0,3 contro 0,15 di media
    v[-1] = 300.0
    mano = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": v}, index=_indice(k))
    e_mano = TRIGGER_LONG["E27_VSA_BULLISH"](mano)
    altre = {nome: bool(f.iloc[-1]) for nome, f in _vsa_figure(mano).items() if nome != "stopping_volume"}
    check("H6. stopping volume costruito a mano: E27 long scatta solo sull'ultima barra",
          bool(e_mano.iloc[-1]) and int(e_mano.sum()) == 1 and not any(altre.values()))

    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
