"""
Suite di validazione delle condizioni entrate da articoli il 7/10/2026
(metodo: 50_IDEE_DA_ARTICOLI.md).

    E24  ciclo dominante che gira        (Kaabar, Fourier)
    F23  ciclo forte
    X1   uscita sul giro del ciclo
    E25  cambio di stato del canale di trend adattivo (MarketStructureLab)
    F24/F25  istogramma del PVO sopra / sotto zero
    F26  due candele di fila nello stesso verso

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
                               pvo_istogramma)
from entry_long import TRIGGER_LONG, registra_trigger_long
from entry_short import TRIGGER_SHORT, registra_trigger_short
from exit_long import EXIT_LONG, registra_exit_long
from exit_short import EXIT_SHORT, registra_exit_short
from filter_conditions import FILTRI, registra_filtri

NUOVI_INDICATORI = ("ciclo_quota", "ciclo_pendenza", "atc_regime", "pvo_hist")


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
                    "E25_ADAPTIVE_CHANNEL_UP": 1, "E25_SHORT_ADAPTIVE_CHANNEL_DOWN": -1}
    check("D1. le quattro entry sono registrate con il lato giusto",
          all(k in R.list_entries() and R.get_entry_direction(k) == v
              for k, v in attesi_entry.items()))
    attesi_filtri = {"F23_CYCLE_STRENGTH": (0, None), "F24_PVO_HIST_POSITIVE": (0, None),
                     "F25_PVO_HIST_NEGATIVE": (0, None), "F26_TWO_BARS_UP": (1, "TWO_BARS"),
                     "F26_TWO_BARS_DOWN": (-1, "TWO_BARS")}
    check("D2. i cinque filtri sono registrati con direction e pair giusti",
          all(k in R.list_filters() and (R.get_filter_direction(k), R.get_filter_pair(k)) == v
              for k, v in attesi_filtri.items()))
    check("D3. la coppia TWO_BARS e' riconosciuta dalla ricerca dei filtri",
          ("TWO_BARS", "F26_TWO_BARS_UP", "F26_TWO_BARS_DOWN") in R.list_filter_pairs())
    check("D4. la coppia di uscite CYCLE_TURN e' riconosciuta dalla ricerca delle uscite",
          ("CYCLE_TURN", "X1_CYCLE_TURN_DOWN", "X1_SHORT_CYCLE_TURN_UP") in R.list_exit_pairs())
    uscite = set(R.list_exits())
    check("D5. X1 e' la nuova uscita; X0, X2 e X3 sono rimaste; la vecchia X1 (RSI) non c'e' piu'",
          {"X1_CYCLE_TURN_DOWN", "X1_SHORT_CYCLE_TURN_UP", "X0_NO_EXIT", "X0_SHORT_NO_EXIT",
           "X2_EMA_BEARISH_CROSS", "X3_MACD_BEARISH"} <= uscite
          and not {"X1_RSI_OVERBOUGHT", "X1_SHORT_RSI_OVERSOLD"} & uscite)
    check("D6. i quattro indicatori nuovi sono nell'elenco che il collaudo verifica",
          set(NUOVI_INDICATORI) <= set(COLONNE_INDICATORI))

    # =====================================================================
    print("\nE · LOOKAHEAD (per troncamento) E RISCALDAMENTO\n" + "-" * 70)
    nuove = list(attesi_entry) + list(attesi_filtri) + ["X1_CYCLE_TURN_DOWN", "X1_SHORT_CYCLE_TURN_UP"]
    funzioni = {**TRIGGER_LONG, **TRIGGER_SHORT,
                **{k: v[0] for k, v in FILTRI.items()},
                **{k: v[0] for k, v in EXIT_LONG.items()},
                **{k: v[0] for k, v in EXIT_SHORT.items()}}
    R.clear_registry()
    for k, v in attesi_entry.items():
        R.register_entry(k, v)(funzioni[k])
    for k in attesi_filtri:
        R.register_filter(k)(funzioni[k])
    R.register_exit("X1_CYCLE_TURN_DOWN", 1)(funzioni["X1_CYCLE_TURN_DOWN"])
    R.register_exit("X1_SHORT_CYCLE_TURN_UP", -1)(funzioni["X1_SHORT_CYCLE_TURN_UP"])

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
    check("E2. le 11 condizioni nuove risultano OK (nessun lookahead, tutte esercitate)",
          not non_ok, f"{non_ok}" if non_ok else "")
    ind_non_ok = {k: esito[k] for k in NUOVI_INDICATORI if esito[k] != "OK"}
    check("E3. i 4 indicatori nuovi risultano OK", not ind_non_ok, f"{ind_non_ok}" if ind_non_ok else "")
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

    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
