"""
Suite di validazione delle condizioni entrate da articoli il 7 e l'8/10/2026
(metodo: 50_IDEE_DA_ARTICOLI.md).

    E24  ciclo dominante che gira        (Kaabar, Fourier)
    F23  ciclo forte
    X1   uscita sul giro del ciclo
    E25  setup completo: canale adattivo + due candele + PVO   (MarketStructureLab, Sayedali Richu)
    F24  due candele di fila nello stesso verso
    E26  setup completo: Supertrend + candela precedente + IIX (8/10, Sayedali Richu)
    E27  figure VSA d'ingresso                         (8/10, PyQuantLab)
    X2   uscita sulle figure VSA (al posto dell'uscita sulle EMA)

Dal 9/10/2026 E25 ed E26 sono i setup completi degli articoli (regola di
50 §4): i filtri PVO (ex F24/F25) e IIX (ex F27) non ci sono piu', e le due
candele sono diventate F24 (era F26).

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
    zz = pd.DataFrame({"Open": gamba, "High": gamba + 0.00002, "Low": gamba - 0.00002,
                       "Close": gamba, "Volume": 100.0}, index=_indice(len(gamba)))
    regime = canale_adattivo_regime(zz).to_numpy()
    giu = np.flatnonzero((regime[1:] == -1) & (regime[:-1] == 1)) + 1
    su = np.flatnonzero((regime[1:] == 1) & (regime[:-1] == -1)) + 1
    check("B3. salita-discesa-salita: il canale diventa ribassista una volta, poco dopo il massimo (barra 79)",
          len(giu) == 1 and 79 < giu[0] <= 79 + 10, f"barre {[int(x) for x in giu]}")
    check("B4. ... e torna rialzista una volta, poco dopo il minimo (barra 158)",
          len(su) == 1 and 158 < su[0] <= 158 + 10, f"barre {[int(x) for x in su]}")

    # speculare esatto: prezzi cambiati di segno, massimi e minimi scambiati
    specchio = pd.DataFrame({"Open": -mercato["Open"], "High": -mercato["Low"],
                             "Low": -mercato["High"], "Close": -mercato["Close"]},
                            index=mercato.index)
    da = 50          # le prime barre differiscono: entrambi partono rialzisti per convenzione
    check("B5. sul mercato capovolto il canale e' esattamente l'opposto",
          bool((canale_adattivo_regime(specchio).to_numpy()[da:] == -mio[da:]).all()))

    # Il setup E25 costruito a mano sul cambio del canale: si decidono il
    # colore delle due candele (con l'apertura, che il canale non usa) e il
    # volume (che il canale non usa) e si guarda se E25 scatta.
    f_su, f_giu = int(su[0]), int(giu[0])

    def setup25(f, verso, colore_segnale, colore_prima, volume_sale):
        d = zz.copy()
        segno = {"verde": -1, "rossa": +1}
        d.loc[d.index[f], "Open"] = d["Close"].iloc[f] + segno[colore_segnale] * 0.00001
        d.loc[d.index[f - 1], "Open"] = d["Close"].iloc[f - 1] + segno[colore_prima] * 0.00001
        vol = np.full(len(d), 100.0)
        if volume_sale:
            vol[f - 3:] = 400.0
        else:
            vol[:f - 3] = 400.0
        d["Volume"] = vol
        d["atc_regime"] = canale_adattivo_regime(d)
        d["pvo_hist"] = pvo_istogramma(d["Volume"])
        e = (TRIGGER_LONG["E25_ATC_PVO_SETUP_UP"] if verso == "long"
             else TRIGGER_SHORT["E25_SHORT_ATC_PVO_SETUP_DOWN"])(d)
        return [int(x) for x in np.flatnonzero(e.to_numpy())]

    check("B6. E25 long: canale verde + due candele verdi + volumi in accelerazione -> scatta sulla barra del cambio",
          setup25(f_su, "long", "verde", "verde", True) == [f_su])
    check("B7. E25 long non scatta se la candela del segnale e' rossa",
          setup25(f_su, "long", "rossa", "verde", True) == [])
    check("B8. E25 long non scatta se la candela precedente e' rossa",
          setup25(f_su, "long", "verde", "rossa", True) == [])
    check("B9. E25 long non scatta se i volumi rallentano (PVO sotto zero)",
          setup25(f_su, "long", "verde", "verde", False) == [])
    check("B10. E25 short: canale rosso + due candele rosse + volumi in rallentamento -> scatta sulla barra del cambio",
          setup25(f_giu, "short", "rossa", "rossa", False) == [f_giu])
    check("B11. E25 short non scatta se i volumi accelerano (la fonte vuole il PVO rosso)",
          setup25(f_giu, "short", "rossa", "rossa", True) == [])

    # =====================================================================
    print("\nC · PVO (dentro E25) E DUE CANDELE (F24)\n" + "-" * 70)
    n = 600
    costante = pvo_istogramma(pd.Series(500.0, index=_indice(n))).to_numpy()
    check("C1. volume costante: istogramma del PVO a zero",
          bool(np.allclose(costante[40:], 0.0)))
    vol = np.full(n, 500.0)
    vol[200:400] = 1500.0                      # il volume triplica alla barra 200, torna giu' alla 400
    gradino = pvo_istogramma(pd.Series(vol, index=_indice(n))).to_numpy()
    check("C2. il volume sale di colpo: istogramma sopra zero sulle 5 barre successive",
          bool((gradino[200:205] > 0).all()))
    check("C3. il volume scende di colpo: istogramma sotto zero sulle 5 barre successive",
          bool((gradino[400:405] < 0).all()))
    zero = pvo_istogramma(pd.Series(0.0, index=_indice(200)))
    check("C4. volumi tutti a zero: nessun NaN oltre il riscaldamento",
          bool(zero.iloc[40:].notna().all() and (zero.iloc[40:] == 0).all()))

    #            barra:  0     1     2     3     4     5     6     7
    apre = np.array([1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00])
    chiude = np.array([1.01, 1.02, 0.99, 1.01, 1.01, 0.98, 0.97, 1.00])
    candele = pd.DataFrame({"Open": apre, "Close": chiude}, index=_indice(8))
    su2 = FILTRI["F24_TWO_BARS_UP"][0](candele).to_numpy()
    giu2 = FILTRI["F24_TWO_BARS_DOWN"][0](candele).to_numpy()
    check("C5. F24 su: vero solo sulle barre 1 e 4",
          list(np.flatnonzero(su2)) == [1, 4], f"{[int(x) for x in np.flatnonzero(su2)]}")
    check("C6. F24 giu': vero solo sulla barra 6 (la 7 chiude pari: ne' su ne' giu')",
          list(np.flatnonzero(giu2)) == [6], f"{[int(x) for x in np.flatnonzero(giu2)]}")
    check("C7. i filtri PVO e IIX non ci sono piu', le due candele non sono piu' F26",
          not any(k.startswith(("F25", "F26", "F27")) or "PVO" in k or "IIX" in k for k in FILTRI))

    # =====================================================================
    print("\nD · REGISTRAZIONE\n" + "-" * 70)
    R.clear_registry()
    with contextlib.redirect_stdout(io.StringIO()):
        registra_trigger_long(); registra_trigger_short()
        registra_exit_long(); registra_exit_short(); registra_filtri()
    attesi_entry = {"E24_CYCLE_TURN_UP": 1, "E24_SHORT_CYCLE_TURN_DOWN": -1,
                    "E25_ATC_PVO_SETUP_UP": 1, "E25_SHORT_ATC_PVO_SETUP_DOWN": -1,
                    "E26_SUPERTREND_IIX_SETUP_UP": 1, "E26_SHORT_SUPERTREND_IIX_SETUP_DOWN": -1,
                    "E27_VSA_BULLISH": 1, "E27_SHORT_VSA_BEARISH": -1}
    check("D1. le otto entry nuove sono registrate con il lato giusto",
          all(k in R.list_entries() and R.get_entry_direction(k) == v
              for k, v in attesi_entry.items()))
    attesi_filtri = {"F23_CYCLE_STRENGTH": (0, None),
                     "F24_TWO_BARS_UP": (1, "TWO_BARS"), "F24_TWO_BARS_DOWN": (-1, "TWO_BARS")}
    check("D2. i filtri nuovi (F23, F24) sono registrati con direction e pair giusti",
          all(k in R.list_filters() and (R.get_filter_direction(k), R.get_filter_pair(k)) == v
              for k, v in attesi_filtri.items()))
    coppie_f = R.list_filter_pairs()
    check("D3. la coppia TWO_BARS e' riconosciuta dalla ricerca dei filtri; la coppia IIX non c'e' piu'",
          ("TWO_BARS", "F24_TWO_BARS_UP", "F24_TWO_BARS_DOWN") in coppie_f
          and not any(c[0] == "IIX" for c in coppie_f))
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
    st = supertrend_direzione(zz).to_numpy()
    giu = np.flatnonzero((st[1:] == -1) & (st[:-1] == 1)) + 1
    su = np.flatnonzero((st[1:] == 1) & (st[:-1] == -1)) + 1
    check("F3. salita-discesa-salita: il Supertrend gira al ribasso una volta, poco dopo il massimo (barra 79)",
          len(giu) == 1 and 79 < giu[0] <= 79 + 15, f"barre {[int(x) for x in giu]}")
    check("F4. ... e gira al rialzo alla partenza e poco dopo il minimo (barra 158)",
          len(su) == 2 and su[0] < 30 and 158 < su[1] <= 158 + 15, f"barre {[int(x) for x in su]}")
    specchio = pd.DataFrame({"Open": -mercato["Open"], "High": -mercato["Low"],
                             "Low": -mercato["High"], "Close": -mercato["Close"],
                             "Volume": mercato["Volume"]}, index=mercato.index)
    da = 100        # le prime barre differiscono: entrambi partono ribassisti per convenzione
    check("F5. sul mercato capovolto il Supertrend e' esattamente l'opposto",
          bool((supertrend_direzione(specchio).to_numpy()[da:] == -mio[da:]).all()))

    # Il setup E26 costruito a mano. Massimo e minimo asimmetrici attorno
    # alla chiusura decidono il segno dell'IIX (chiusura in alto = positivo);
    # l'apertura decide il colore delle candele, e il Supertrend non la usa.
    def setup26(verso, colore_segnale, colore_prima, iix_positivo):
        sopra, sotto = (0.00001, 0.00003) if iix_positivo else (0.00003, 0.00001)
        d = pd.DataFrame({"Open": gamba, "High": gamba + sopra, "Low": gamba - sotto,
                          "Close": gamba, "Volume": 100.0}, index=_indice(len(gamba)))
        d["st_dir"] = supertrend_direzione(d)
        st = d["st_dir"].to_numpy()
        if verso == "long":
            f = int((np.flatnonzero((st[1:] == 1) & (st[:-1] == -1)) + 1)[-1])
        else:
            f = int((np.flatnonzero((st[1:] == -1) & (st[:-1] == 1)) + 1)[0])
        segno = {"verde": -1, "rossa": +1}
        d.loc[d.index[f], "Open"] = d["Close"].iloc[f] + segno[colore_segnale] * 0.00001
        d.loc[d.index[f - 1], "Open"] = d["Close"].iloc[f - 1] + segno[colore_prima] * 0.00001
        d["iix"] = intraday_intensity(d)
        e = (TRIGGER_LONG["E26_SUPERTREND_IIX_SETUP_UP"] if verso == "long"
             else TRIGGER_SHORT["E26_SHORT_SUPERTREND_IIX_SETUP_DOWN"])(d)
        return f, [int(x) for x in np.flatnonzero(e.to_numpy())]

    f, ev = setup26("long", "rossa", "verde", True)
    check("F6. E26 long: Supertrend su + candela precedente verde + IIX positivo -> scatta (anche con la candela del segnale rossa)",
          ev == [f], f"cambio alla barra {f}, eventi {ev}")
    check("F7. E26 long non scatta se la candela precedente e' rossa",
          setup26("long", "verde", "rossa", True)[1] == [])
    check("F8. E26 long non scatta se l'IIX e' negativo",
          setup26("long", "verde", "verde", False)[1] == [])
    f, ev = setup26("short", "verde", "rossa", False)
    check("F9. E26 short: Supertrend giu' + candela precedente rossa + IIX negativo -> scatta",
          ev == [f], f"cambio alla barra {f}, eventi {ev}")
    check("F10. E26 short non scatta se l'IIX e' positivo",
          setup26("short", "rossa", "rossa", True)[1] == [])
    a = mercato.assign(st_dir=mio, iix=intraday_intensity(mercato))
    b = specchio.assign(st_dir=supertrend_direzione(specchio), iix=intraday_intensity(specchio))
    lungo_a = TRIGGER_LONG["E26_SUPERTREND_IIX_SETUP_UP"](a)
    check("F11. sul mercato capovolto E26 short coincide con E26 long (l'IIX cambia segno con il prezzo)",
          bool(lungo_a.iloc[da:].equals(TRIGGER_SHORT["E26_SHORT_SUPERTREND_IIX_SETUP_DOWN"](b).iloc[da:]))
          and int(lungo_a.sum()) > 10, f"{int(lungo_a.sum())} eventi")

    # =====================================================================
    print("\nG · INTRADAY INTENSITY (dentro E26) E I DUE SETUP COMPLETI\n" + "-" * 70)
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
    ia, ib = intraday_intensity(alti).to_numpy(), intraday_intensity(bassi).to_numpy()
    check("G2. chiusure sempre in alto: IIX positivo dalla barra 21",
          bool(np.isnan(ia[:20]).all() and (ia[20:] > 0).all()))
    check("G3. chiusure sempre in basso: IIX negativo dalla barra 21",
          bool(np.isnan(ib[:20]).all() and (ib[20:] < 0).all()))
    piatte = alti.assign(High=1.0, Low=1.0, Close=1.0)
    ii = intraday_intensity(piatte)
    check("G4. barre piatte (massimo = minimo): valgono zero, nessun NaN dopo 21 barre",
          bool(ii.iloc[20:].notna().all() and (ii.iloc[20:] == 0).all()))

    # i due setup sono l'AND delle loro parti, barra per barra, su dati sintetici
    pieno = aggiungi_indicatori(mercato_sintetico("2024-01-01", "2024-07-01", seme=8))
    v = pieno["Close"] > pieno["Open"]
    r = pieno["Close"] < pieno["Open"]
    reg, std = pieno["atc_regime"], pieno["st_dir"]
    attese = {
        "E25_ATC_PVO_SETUP_UP": (reg == 1) & (reg.shift(1) == -1) & v & v.shift(1, fill_value=False) & (pieno["pvo_hist"] > 0),
        "E25_SHORT_ATC_PVO_SETUP_DOWN": (reg == -1) & (reg.shift(1) == 1) & r & r.shift(1, fill_value=False) & (pieno["pvo_hist"] < 0),
        "E26_SUPERTREND_IIX_SETUP_UP": (std == 1) & (std.shift(1) == -1) & v.shift(1, fill_value=False) & (pieno["iix"] > 0),
        "E26_SHORT_SUPERTREND_IIX_SETUP_DOWN": (std == -1) & (std.shift(1) == 1) & r.shift(1, fill_value=False) & (pieno["iix"] < 0),
    }
    funz = {**TRIGGER_LONG, **TRIGGER_SHORT}
    diverse = {k: int((funz[k](pieno) != a).sum()) for k, a in attese.items()}
    quanti = {k: int(a.sum()) for k, a in attese.items()}
    check("G5. E25 ed E26 coincidono con l'AND delle condizioni dell'articolo, barra per barra",
          not any(diverse.values()) and min(quanti.values()) > 0, f"eventi: {quanti}")

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
