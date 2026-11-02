"""
Suite di collaudo dei trigger intraday E46-E52 (02/11/2026, docs/78 e docs/79):
sette idee, long e short. Moduli: engine/indicatori.py (canale_24h_impulso,
compressione_rottura, pivot_chiusure, massimi_uguali_rottura, livello_sweep,
sweep_reclaim, salto_z, salto_contro, movimento_volume_calo, area_rumore,
area_rumore_uscita), entry_long.py, entry_short.py.

Cosa verifica (docs/50 §7)
--------------------------
A  casi a risultato noto, uno per idea, su serie costruite a mano: il trigger
   scatta sulla barra attesa e solo li'; idea 4: il livello e' l'ultimo minimo
   confermato, tenuto fino al successivo anche se gia' spazzato, e uno sweep
   prima della conferma non scatta; idea 7: il controllo delle HH:30 e' la
   barra che FINISCE alle HH:30 (l'indice e' l'inizio della barra), due uscite
   nella stessa giornata danno due eventi;
B  rifatti a mano con cicli semplici, barra per barra, su 30 barre a caso di
   un mercato inventato: stessi valori delle funzioni;
C  eventi, non stati (prima barra di ogni blocco) e registrazione nei dizionari;
D  verifica_lookahead (troncamento), con quattro trappole nuove (pivot non
   confermato, minimo centrato non spostato, deviazione standard su tutto il
   campione, sigma con la giornata intera): le trappole sono LOOKAHEAD, i 14
   trigger OK; verifica_degenerazione: OK;
E  riscaldamento: dopo la finestra piu' lunga gli eventi non dipendono dal
   punto di partenza dei dati;
F  timeframe: le finestre in barre seguono il timeframe; idea 7 da' gli stessi
   eventi su M5 e M15 (stesse chiusure ai controlli); idee 1, 2, 3 scattano
   alla stessa ora su M5 e M15 nei casi costruiti; fuori dai timeframe ammessi
   la condizione e' tutta falsa e c'e' un avviso.

Come si lancia (da terminale, dalla cartella del progetto):

    python test_trigger_intraday.py

Non serve la rete ne' i dati veri. Alla fine stampa «RISULTATO: N/N test superati».
"""
from __future__ import annotations

import contextlib
import io
import sys
import warnings

import numpy as np
import pandas as pd

warnings.simplefilter("ignore")

import entry_long as EL
import entry_short as ES
from engine import indicatori as ind
from engine import registry as reg
from engine.quarantena import imposta_rollover
from helpers import _evento
from test_atlante import Mercato, _indice

ESITI: list[bool] = []

LONG = {
    1: ("E46_CANALE_24H_IMPULSO_UP", EL.entry_canale_24h_impulso_up),
    2: ("E47_COMPRESSIONE_ROTTURA_UP", EL.entry_compressione_rottura_up),
    3: ("E48_MASSIMI_UGUALI_ROTTURA_UP", EL.entry_massimi_uguali_rottura_up),
    4: ("E49_SWEEP_RECLAIM_MINIMO", EL.entry_sweep_reclaim_minimo),
    5: ("E50_SALTO_GIU_CONTRO", EL.entry_salto_giu_contro),
    6: ("E51_MOVIMENTO_VOLUME_CALO_GIU", EL.entry_movimento_volume_calo_giu),
    7: ("E52_AREA_RUMORE_SOPRA", EL.entry_area_rumore_sopra),
}
SHORT = {
    1: ("E46_SHORT_CANALE_24H_IMPULSO_DOWN", ES.entry_short_canale_24h_impulso_down),
    2: ("E47_SHORT_COMPRESSIONE_ROTTURA_DOWN", ES.entry_short_compressione_rottura_down),
    3: ("E48_SHORT_MINIMI_UGUALI_ROTTURA_DOWN", ES.entry_short_minimi_uguali_rottura_down),
    4: ("E49_SHORT_SWEEP_RECLAIM_MASSIMO", ES.entry_short_sweep_reclaim_massimo),
    5: ("E50_SHORT_SALTO_SU_CONTRO", ES.entry_short_salto_su_contro),
    6: ("E51_SHORT_MOVIMENTO_VOLUME_CALO_SU", ES.entry_short_movimento_volume_calo_su),
    7: ("E52_SHORT_AREA_RUMORE_SOTTO", ES.entry_short_area_rumore_sotto),
}
STATI = {1: ind.canale_24h_impulso, 2: ind.compressione_rottura, 3: ind.massimi_uguali_rottura,
         4: ind.sweep_reclaim, 5: ind.salto_contro, 6: ind.movimento_volume_calo}


def check(nome, condizione, dettaglio=""):
    ESITI.append(bool(condizione))
    print(f"  [{'OK' if condizione else 'FALLITO'}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""))


def muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


# ---------------------------------------------------------------- serie --
def candele(idx, close, open_=None, high=None, low=None, volume=None, margine=0.0):
    """Un DataFrame OHLCV: Open = Close prima se non dato, High/Low = max/min di Open e Close +- margine."""
    close = np.asarray(close, dtype=float)
    op = np.r_[close[0], close[:-1]] if open_ is None else np.asarray(open_, dtype=float)
    hi = np.maximum(op, close) + margine if high is None else np.asarray(high, dtype=float)
    lo = np.minimum(op, close) - margine if low is None else np.asarray(low, dtype=float)
    vol = np.full(len(close), 1000.0) if volume is None else np.asarray(volume, dtype=float)
    return pd.DataFrame({"Open": op, "High": hi, "Low": lo, "Close": close, "Volume": vol}, index=idx)


def a_m15(d5: pd.DataFrame) -> pd.DataFrame:
    """Le barre M15 dalle M5 (indice = inizio della barra, come i CSV)."""
    return d5.resample("15min", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()


def specchio(d: pd.DataFrame) -> pd.DataFrame:
    """La serie capovolta (200 - prezzo): il long dell'originale diventa lo short."""
    return pd.DataFrame({"Open": 200 - d["Open"], "High": 200 - d["Low"], "Low": 200 - d["High"],
                         "Close": 200 - d["Close"], "Volume": d["Volume"]}, index=d.index)


def ore_eventi(s: pd.Series, minuti: int) -> list:
    """Le ore di CHIUSURA delle barre dove la serie e' vera."""
    return list(pd.DatetimeIndex(s.index[s.to_numpy()]) + pd.Timedelta(minutes=minuti))


def caso_idea1_m5(verso=1):
    """Sinusoide di periodo 2 ore su M5, poi un salto sull'ultima barra M5 di un quarto d'ora."""
    n = 4 * 288
    idx = _indice("2024-03-04", giorni=4, minuti=5)
    c = 100 + 0.2 * np.sin(2 * np.pi * np.arange(n) / 24)
    salto = 899                                       # (899 + 1) % 3 == 0: chiude un quarto d'ora
    c[salto] = 100 + verso * 1.5
    return candele(idx, c, margine=0.05), salto


def caso_idea2_m5(verso=1):
    """Barre grandi (range 2), poi 11 barre piccole, poi la rottura sull'ultima M5 di un quarto d'ora."""
    grandi, piccole = 300, 11
    n = grandi + piccole + 1 + 30
    idx = _indice("2024-03-04", giorni=n * 5 / 1440, minuti=5)[:n]
    c = np.full(n, 100.0)
    hi = np.r_[np.full(grandi, 101.0), np.full(n - grandi, 100.01)]
    lo = np.r_[np.full(grandi, 99.0), np.full(n - grandi, 99.99)]
    rottura = grandi + piccole                        # 311: (311 + 1) % 3 == 0
    c[rottura] = 100 + 2 * verso
    hi[rottura], lo[rottura] = max(c[rottura], 100) + 0.1, min(c[rottura], 100) - 0.1
    return candele(idx, c, open_=np.full(n, 100.0), high=hi, low=lo), rottura


def caso_idea3_m5():
    """Chiusure M15 c_j; ogni quarto d'ora su M5 e' (99, 99, c_j): i pivot M5 coincidono con quelli M15."""
    blocchi = [100.0] * 40 + [101.00, 100.0, 101.05, 100.0, 101.02, 100.0, 101.20] + [100.0] * 10
    c5 = np.concatenate([[99.0, 99.0, b] for b in blocchi])
    idx = _indice("2024-03-04", giorni=len(c5) * 5 / 1440 + 1, minuti=5)[:len(c5)]
    rottura = 3 * 46 + 2                              # la terza barra M5 del blocco 101,20
    return candele(idx, c5, margine=0.01), rottura


# ------------------------------------------------------------ sezione A --
def sezione_a():
    print("\nA · Casi a risultato noto (M15)")
    # idea 1
    d5, salto = caso_idea1_m5(1)
    d = a_m15(d5)
    t = pd.DatetimeIndex(d5.index)[salto] + pd.Timedelta(minutes=5)
    el, es = LONG[1][1](d), SHORT[1][1](d)
    d5s, _ = caso_idea1_m5(-1)
    ds = a_m15(d5s)
    check("A1. idea 1: il long scatta solo sulla barra che chiude sopra il canale delle 24 ore con l'impulso; lo "
          "short solo sulla barra speculare",
          ore_eventi(el, 15) == [t] and not es.any() and ore_eventi(SHORT[1][1](ds), 15) == [t]
          and not LONG[1][1](ds).any(), f"{ore_eventi(el, 15)}")
    # idea 2
    d5, rottura = caso_idea2_m5(1)
    d = a_m15(d5)
    t = pd.DatetimeIndex(d5.index)[rottura] + pd.Timedelta(minutes=5)
    d5s, _ = caso_idea2_m5(-1)
    piatto = d.copy()
    piatto.loc[piatto["High"] < 100.5, ["High", "Low"]] = [101.0, 99.0]   # nessuna compressione
    check("A2. idea 2: con la compressione la rottura scatta solo sulla barra attesa (long e short); senza "
          "compressione la stessa rottura non scatta",
          ore_eventi(LONG[2][1](d), 15) == [t] and ore_eventi(SHORT[2][1](a_m15(d5s)), 15) == [t]
          and not SHORT[2][1](d).any() and not LONG[2][1](piatto).any())
    # idea 3
    d5, rottura = caso_idea3_m5()
    d = a_m15(d5)
    t = pd.DatetimeIndex(d5.index)[rottura] + pd.Timedelta(minutes=5)
    lontani = d.copy()
    i_piv = np.flatnonzero(np.isclose(lontani["Close"].to_numpy(), 101.05))
    lontani.iloc[i_piv, lontani.columns.get_loc("Close")] = 101.6           # i tre massimi non stanno nello 0,2%
    check("A3. idea 3: tre massimi uguali confermati (1 barra per lato su M15) e la chiusura >= media x 1,001: "
          "scatta solo li'; con un massimo fuori dalla banda non scatta",
          ore_eventi(LONG[3][1](d), 15) == [t] and not LONG[3][1](lontani).any(),
          f"pivot M15 per lato {ind._barre_di(ind.PIVOT_LATO_MINUTI, 15)}")
    sezione_a4()
    # idea 5
    n = 300
    r = np.where(np.arange(n) % 2 == 0, 0.001, -0.001)
    r[150], r[250] = -0.005, 0.006
    d = candele(_indice("2024-03-04", giorni=4)[:n], 100 * np.exp(np.cumsum(r)))
    check("A5. idea 5: un rendimento di -5 deviazioni standard (delle 15 ore prima) e' il long, +6 lo short, "
          "nient'altro", list(np.flatnonzero(LONG[5][1](d))) == [150] and list(np.flatnonzero(SHORT[5][1](d))) == [250]
          and abs(ind.salto_z(d).iloc[150] + 5) < 0.1)
    # idea 6
    n = 600
    r = np.where(np.arange(n) % 2 == 0, 0.0005, -0.0005)
    r[520:540] = -0.002
    vol = np.full(n, 1000.0)
    vol[520:540] = 500.0
    d = candele(_indice("2024-03-04", giorni=8)[:n], 100 * np.exp(np.cumsum(r)), volume=vol)
    sale = d.copy()
    sale.iloc[520:, sale.columns.get_loc("Volume")] = 1500.0                # il volume sale e resta alto
    su_r = r.copy()
    su_r[520:540] = 0.002
    su = candele(d.index, 100 * np.exp(np.cumsum(su_r)), volume=vol)
    check("A6. idea 6: discesa forte nelle 5 ore con il volume in calo -> long sulla prima barra; con il volume in "
          "salita niente; la salita speculare -> short",
          list(np.flatnonzero(LONG[6][1](d))) == [520] and not LONG[6][1](sale).any()
          and list(np.flatnonzero(SHORT[6][1](su))) == [520] and not SHORT[6][1](d).any())
    sezione_a7()


def sezione_a4():
    k = ind._barre_di(ind.SWEEP_LATO_MINUTI, 15)
    n = 400
    idx = _indice("2024-03-04", giorni=5)[:n]
    low = 99.0 + 0.001 * np.arange(n)                 # crescente: nessun minimo locale
    close = low + 0.5
    s, u = 100, 140                                   # minimo A in s; sweep in u e in u + 8
    low[s] = 98.0
    low[u], close[u] = 97.9, 99.5
    low[u + 8], close[u + 8] = 97.95, 99.5
    v = 250                                           # minimo B in v, spazzato in v + 3 prima della conferma
    low[v] = 98.6
    low[v + 3], close[v + 3] = 98.55, 99.5
    d = candele(idx, close, open_=close, high=close + 0.5, low=low)
    liv = ind.livello_sweep(d, 1)
    el = LONG[4][1](d)
    check("A4a. idea 4: il livello e' l'ultimo minimo confermato, noto 3 ore dopo (NaN prima), e resta lo stesso "
          "anche dopo essere stato spazzato, finche' non se ne conferma uno nuovo",
          liv.iloc[:s + k].isna().all() and liv.iloc[s + k] == 98.0 and (liv.iloc[s + k:u + k] == 98.0).all()
          and liv.iloc[u + 8] == 98.0 and liv.iloc[u + k] == 97.9, f"k = {k} barre")
    check("A4b. idea 4: scatta sullo sweep in u e di nuovo in u + 8 sullo STESSO minimo gia' spazzato (quello "
          "della scheda); lo sweep di un minimo non ancora confermato (v + 3) non scatta",
          list(np.flatnonzero(el)) == [u, u + 8] and liv.iloc[v + 3] == 97.9, f"{list(np.flatnonzero(el))}")
    es = SHORT[4][1](specchio(d))
    check("A4c. idea 4: lo short (traduzione nostra) sulla serie capovolta scatta sulle stesse barre",
          list(np.flatnonzero(es)) == [u, u + 8] and not SHORT[4][1](d).any())


def sezione_a7():
    giorni = 15
    idx = _indice("2024-03-04", giorni=giorni)
    n = len(idx)
    ore = idx.hour * 60 + idx.minute + 15             # minuto di CHIUSURA della barra
    alterna = np.where((np.arange(n) % 2) == 0, 100.2, 99.8)
    close = alterna.copy()
    oggi = idx.floor("D") == idx[-1].floor("D")       # l'ultimo giorno: dentro l'area tranne dove detto
    close[oggi] = 100.1
    def barra(hh, mm):                                # la barra dell'ultimo giorno che FINISCE alle hh:mm
        return int(np.flatnonzero(oggi & (ore == hh * 60 + mm))[0])
    for (hh, mm), v in {(10, 30): 100.3, (12, 30): 100.35, (13, 0): 100.4, (20, 0): 99.7}.items():
        close[barra(hh, mm)] = v
    op = np.r_[100.0, close[:-1]]
    op[idx.hour * 60 + idx.minute == 0] = 100.0       # l'apertura di ogni giornata e' 100
    d = candele(idx, close, open_=op)
    area = ind.area_rumore(d)
    i1030 = barra(10, 30)
    check("A7a. idea 7: il controllo delle 10:30 e' la barra con indice 10:15 (l'indice e' l'INIZIO della barra, "
          "su M15 finisce 15 minuti dopo); la barra con indice 23:45 finisce alle 00:00 del giorno dopo e non e' "
          "un controllo; su M15 i controlli sono le barre :15 e :45",
          idx[i1030].strftime("%H:%M") == "10:15" and bool(area["controllo"].iloc[i1030])
          and not area["controllo"][idx.strftime("%H:%M") == "23:45"].any()
          and set(idx[area["controllo"].to_numpy()].minute) == {15, 45})
    check("A7b. sigma al controllo delle 10:30 = media dei 14 giorni prima del movimento |Close / apertura - 1| "
          "alle 10:30 (0,2%); confini 100 x (1 +- 0,002); prima di 14 giorni nessuna sigma",
          abs(area["sigma"].iloc[i1030] - 0.002) < 1e-12 and abs(area["alto"].iloc[i1030] - 100.2) < 1e-9
          and area["sigma"][idx < idx[0] + pd.Timedelta(days=14)].isna().all())
    el, es = LONG[7][1](d), SHORT[7][1](d)
    check("A7c. due uscite sopra nella stessa giornata (10:30 e 12:30) danno due eventi long; alle 13:00 e' ancora "
          "fuori e non scatta; l'uscita sotto alle 20:00 e' lo short",
          list(np.flatnonzero(el)) == [i1030, barra(12, 30)] and list(np.flatnonzero(es)) == [barra(20, 0)])


# ------------------------------------------------------------ sezione B --
def _quantile(x, q):
    return float(np.quantile(np.asarray(x, dtype=float), q))


def a_mano(d: pd.DataFrame, idea: int, lato: int, i: int) -> bool | None:
    """Lo stato dell'idea alla barra i rifatto con cicli semplici (M15). None se la storia non basta."""
    O, H, L, C, V = (d[c].to_numpy(dtype=float) for c in ("Open", "High", "Low", "Close", "Volume"))
    if idea == 1:
        w, r = 96, 3
        if i < w + r:
            return None
        imp = [C[j] / C[j - r] - 1 for j in range(i - w + 1, i + 1)]
        if lato == 1:
            return C[i] > max(H[i - w:i]) and imp[-1] > _quantile(imp, 0.60)
        return C[i] < min(L[i - w:i]) and imp[-1] < _quantile(imp, 0.40)
    if idea == 2:
        if i < 20:
            return None
        tr = lambda j: max(H[j] - L[j], abs(H[j] - C[j - 1]), abs(L[j] - C[j - 1]))
        atr = lambda j: sum(tr(x) for x in range(j - 4, j + 1)) / 5
        compressa = atr(i - 1) < 0.8 * sum(atr(x) for x in range(i - 4, i)) / 4
        return compressa and (C[i] > max(H[i - 12:i]) if lato == 1 else C[i] < min(L[i - 12:i]))
    if idea == 3:
        k, w = 1, 33
        if i < w:
            return None
        piv = [j for j in range(k, i - k + 1)
               if all((C[j] > C[j - x] and C[j] > C[j + x]) if lato == 1 else (C[j] < C[j - x] and C[j] < C[j + x])
                      for x in range(1, k + 1))]
        if len(piv) < 3 or piv[-3] < i - w + 1:
            return False
        p = [C[j] for j in piv[-3:]]
        if max(p) / min(p) - 1 > 0.002:
            return False
        m = sum(p) / 3
        return C[i] >= m * 1.001 if lato == 1 else C[i] <= m * 0.999
    if idea == 4:
        k, h = 12, 4
        x = L if lato == 1 else H
        livello = None
        for s in range(i - k, k - 1, -1):
            finestra = x[s - k:s + k + 1]
            if x[s] == (finestra.min() if lato == 1 else finestra.max()):
                livello = x[s]
                break
        if livello is None:
            return None
        if lato == 1:
            return min(L[i - h + 1:i + 1]) < livello and C[i] > livello
        return max(H[i - h + 1:i + 1]) > livello and C[i] < livello
    if idea == 5:
        if i < 62:
            return None
        r = np.diff(np.log(C))                       # r[j-1] = rendimento della barra j
        z = r[i - 1] / np.std(r[i - 61:i - 1], ddof=1)
        return z < -3 if lato == 1 else z > 3
    if idea == 6:
        a, lunga = 20, 400
        if i < lunga + a:
            return None
        mossa = [C[j] - C[j - a] for j in range(i - lunga + 1, i + 1)]
        vol_ora = sum(V[i - a + 1:i + 1]) / a
        vol_prima = sum(V[i - 2 * a + 1:i - a + 1]) / a
        ok = abs(mossa[-1]) > np.std(mossa, ddof=1) and vol_ora < vol_prima
        return ok and (mossa[-1] < 0 if lato == 1 else mossa[-1] > 0)
    raise ValueError(idea)


def area_a_mano(d: pd.DataFrame, i: int):
    """(sigma, fuori sopra, fuori sotto) dell'idea 7 alla barra i, giornata per giornata (M15)."""
    t = d.index[i]
    chiude = t + pd.Timedelta(minutes=15)
    if chiude.minute % 30 or chiude.floor("D") != t.floor("D"):
        return None
    mosse = []
    for g in range(1, 15):
        giorno = t.floor("D") - pd.Timedelta(days=g)
        if giorno not in d.index or (giorno + (chiude - t.floor("D")) - pd.Timedelta(minutes=15)) not in d.index:
            return None
        mosse.append(abs(d["Close"][giorno + (chiude - t.floor("D")) - pd.Timedelta(minutes=15)]
                         / d["Open"][giorno] - 1))
    sigma = sum(mosse) / 14
    ap = d["Open"][t.floor("D")]
    return sigma, d["Close"].iloc[i] > ap * (1 + sigma), d["Close"].iloc[i] < ap * (1 - sigma)


def sezione_b():
    print("\nB · Rifatti a mano, barra per barra (30 barre a caso, mercato inventato M15)")
    d = Mercato(_indice("2023-05-01", giorni=40), seme=4).df()
    rng = np.random.default_rng(3)
    for idea in range(1, 7):
        for lato, nome in ((1, LONG[idea][0]), (-1, SHORT[idea][0])):
            stato = STATI[idea](d, lato).to_numpy()
            vere = np.flatnonzero(stato)
            pos = np.r_[rng.choice(np.arange(500, len(d)), 25, replace=False), rng.choice(vere[vere > 500], 5)]
            fatti = [(int(p), a_mano(d, idea, lato, int(p))) for p in pos]
            uguali = all(v is not None and bool(stato[p]) == v for p, v in fatti)
            check(f"B{idea}{'L' if lato == 1 else 'S'}. {nome}: uguale al calcolo a mano", uguali,
                  f"{int(stato.sum())} barre vere")
    area = ind.area_rumore(d)
    el, es = ind.area_rumore_uscita(d, 1).to_numpy(), ind.area_rumore_uscita(d, -1).to_numpy()
    ctrl = np.flatnonzero(area["controllo"].to_numpy() & area["sigma"].notna().to_numpy())
    pos = rng.choice(ctrl, 30, replace=False)
    ok = True
    for p in pos:
        sigma, sopra, sotto = area_a_mano(d, int(p))
        prima = [q for q in ctrl if q < p and d.index[q].floor("D") == d.index[p].floor("D")]
        sopra_prima = area_a_mano(d, prima[-1])[1] if prima else False
        sotto_prima = area_a_mano(d, prima[-1])[2] if prima else False
        ok &= abs(sigma - area["sigma"].iloc[p]) < 1e-12 and el[p] == (sopra and not sopra_prima) \
            and es[p] == (sotto and not sotto_prima)
    check("B7. idea 7: sigma e uscite (long e short) uguali al calcolo a mano giornata per giornata", ok,
          f"{int(el.sum())} long, {int(es.sum())} short")


# ------------------------------------------------------------ sezione C --
def sezione_c():
    print("\nC · Eventi, non stati, e registrazione")
    d = Mercato(_indice("2023-05-01", giorni=40), seme=5).df()
    ok_ev, ok_stato = True, True
    for idea in range(1, 8):
        for lato, (nome, f) in ((1, LONG[idea]), (-1, SHORT[idea])):
            e = f(d)
            ok_ev &= bool(e.any()) and not (e & e.shift(1, fill_value=False)).any()
            if idea < 7:
                ok_stato &= e.equals(_evento(STATI[idea](d, lato)))
    check("C1. i 14 trigger sono eventi: mai due barre di fila, e ognuno scatta", ok_ev)
    check("C2. idee 1-6: l'evento e' la prima barra di ogni blocco dello stato (_evento)", ok_stato)
    accesi = [i for i in LONG if i != 5]
    check("C3. registrati nei dizionari con il loro lato e la loro funzione (12 accesi)",
          all(EL.TRIGGER_LONG.get(LONG[i][0]) is LONG[i][1] for i in accesi)
          and all(ES.TRIGGER_SHORT.get(SHORT[i][0]) is SHORT[i][1] for i in accesi))
    check("C4. E50 e' spento (doppione di E3, docs/79 §5): la riga del dizionario e' un commento, la funzione resta",
          LONG[5][0] not in EL.TRIGGER_LONG and SHORT[5][0] not in ES.TRIGGER_SHORT
          and callable(EL.entry_salto_giu_contro) and callable(ES.entry_short_salto_su_contro))


# ------------------------------------------------------------ sezione D --
def trappole():
    def pivot_non_confermato(d):                 # idea 3 con i pivot di posizione <= t (servono le barre dopo)
        v = d["Close"].to_numpy(dtype=float)
        pos = np.flatnonzero(ind.pivot_chiusure(d["Close"], 1, 1))
        t = np.arange(len(v))
        q = np.searchsorted(pos, t, side="right")
        ok = q >= 3
        qq = np.clip(q, 3, None)
        ult = np.stack([pos[qq - 3 + j] for j in range(3)], axis=1) if len(pos) >= 3 else np.zeros((len(v), 3), int)
        p = v[ult]
        ok &= (p.max(axis=1) / p.min(axis=1) - 1 <= 0.002) & (v >= p.mean(axis=1) * 1.0005)
        return _evento(pd.Series(ok, index=d.index))

    def minimo_centrato(d):                      # idea 4 con il minimo centrato NON spostato
        x = d["Low"]
        liv = x.where(x == x.rolling(25, center=True).min()).ffill()
        return _evento(((x.rolling(4).min() < liv) & (d["Close"] > liv)).fillna(False))

    def deviazione_su_tutto(d):                  # idea 5 con la deviazione di tutto lo storico
        r = np.log(d["Close"]).diff()
        return _evento((r / r.std() < -3).fillna(False))

    def sigma_giornata_intera(d):                # idea 7 con sigma dalla giornata intera, quella in corso compresa
        g = d.index.floor("D")
        ap = d["Open"].groupby(g).transform("first")
        mossa = (d["Close"] / ap - 1).abs()
        sigma = mossa.groupby(g).transform("mean")
        return _evento((d["Close"] > ap * (1 + sigma)).fillna(False))

    return {"TRAPPOLA_PIVOT_NON_CONFERMATO": pivot_non_confermato, "TRAPPOLA_MINIMO_CENTRATO": minimo_centrato,
            "TRAPPOLA_DEVIAZIONE_SU_TUTTO": deviazione_su_tutto, "TRAPPOLA_SIGMA_GIORNATA": sigma_giornata_intera}


def sezione_d():
    print("\nD · verifica_lookahead e verifica_degenerazione")
    from engine.collaudo_catalogo import verifica_degenerazione, verifica_lookahead
    # code grasse (t di Student) e volatilita' tripla nell'ultimo terzo: piu' salti, e una deviazione
    # «su tutto lo storico» che cambia con il taglio
    idx = _indice("2023-05-01", giorni=150)
    rng = np.random.default_rng(12)
    extra = rng.standard_t(3, len(idx)) * 0.0003 * np.where(np.arange(len(idx)) > len(idx) * 2 // 3, 3.0, 1.0)
    d = Mercato(idx, seme=11).df(extra=extra)
    reg.clear_registry()
    for nome, f in trappole().items():
        reg.register_entry(nome, direction=1)(f)
    for nome, f in LONG.values():
        reg.register_entry(nome, direction=1)(f)
    for nome, f in SHORT.values():
        reg.register_entry(nome, direction=-1)(f)
    look = muto(verifica_lookahead, d, prepara=lambda x: x.copy(), verbose=False)
    trap = look[look["nome"].str.startswith("TRAPPOLA")]
    check("D0. le quattro trappole (pivot non confermato, minimo centrato non spostato, deviazione su tutto lo "
          "storico, sigma con la giornata intera) sono LOOKAHEAD: il controllo le vede",
          len(trap) == 4 and (trap["esito"] == "LOOKAHEAD").all(), str(dict(zip(trap["nome"], trap["esito"]))))
    nuovi = look[~look["nome"].str.startswith("TRAPPOLA")]
    check("D1. verifica_lookahead per troncamento: OK su tutti i 14 trigger, con tagli sulle barre dove scattano",
          len(nuovi) == 14 and (nuovi["esito"] == "OK").all() and (nuovi["tagli"] > 5).all(),
          str(nuovi.loc[nuovi["esito"] != "OK", ["nome", "esito"]].to_dict("records")))
    reg.clear_registry()
    for nome, f in LONG.values():
        reg.register_entry(nome, direction=1)(f)
    for nome, f in SHORT.values():
        reg.register_entry(nome, direction=-1)(f)
    deg = muto(verifica_degenerazione, d, verbose=False)
    dr = deg[deg["nome"].isin([n for n, _ in list(LONG.values()) + list(SHORT.values())])]
    check("D2. verifica_degenerazione: OK su tutti i 14 (eventi, non stati; ne' rari ne' sempre veri)",
          len(dr) == 14 and (dr["esito"] == "OK").all(),
          str(dr.loc[dr["esito"] != "OK", ["nome", "esito", "eventi"]].to_dict("records")))
    reg.clear_registry()


# ------------------------------------------------------------ sezione E --
def sezione_e():
    print("\nE · Riscaldamento: stessi eventi da qualunque punto partano i dati")
    d = Mercato(_indice("2023-05-01", giorni=60), seme=6).df()
    taglio = 1000 + 7                                  # a meta' giornata
    dopo = d.index >= d.index[taglio] + pd.Timedelta(days=20)
    ok = True
    for nome, f in list(LONG.values()) + list(SHORT.values()):
        intero, corto = f(d), f(d.iloc[taglio:])
        ok &= intero[dopo].equals(corto[corto.index >= d.index[taglio] + pd.Timedelta(days=20)])
    check("E1. 20 giorni dopo il punto di partenza i 14 trigger sono identici a quelli dello storico intero", ok)


# ------------------------------------------------------------ sezione F --
def sezione_f():
    print("\nF · Timeframe: M5, M15 e fuori dai timeframe ammessi")
    b = ind._barre_di
    check("F1. le finestre in ore diventano barre del timeframe: M5 = 3 x M15 dove la durata e' intera (24 ore "
          "288/96, 45 minuti 9/3, canale 3 ore 36/12, pivot 3/1); arrotondate dove no (ATR 70 minuti 14/5, "
          "finestra pivot 500 minuti 100/33)",
          (b(1440, 5), b(1440, 15), b(45, 5), b(45, 15), b(180, 5), b(180, 15), b(15, 5), b(15, 15))
          == (288, 96, 9, 3, 36, 12, 3, 1) and (b(70, 5), b(70, 15), b(500, 5), b(500, 15)) == (14, 5, 100, 33))
    d5 = Mercato(_indice("2023-05-01", giorni=30, minuti=5), seme=9).df()
    d15 = a_m15(d5)
    uguali = all(ore_eventi(f(d5), 5) == ore_eventi(f(d15), 15) for _, f in (LONG[7], SHORT[7]))
    n_ev = int(LONG[7][1](d15).sum())
    check("F2. idea 7: stessi eventi, alla stessa ora, su M5 e sulle M15 ricavate dalle stesse M5 (stesse chiusure "
          "ai controlli, stessa apertura, stessa sigma)", uguali and n_ev > 20, f"{n_ev} long su M15")
    stessi = []
    for idea, caso in ((1, caso_idea1_m5), (2, caso_idea2_m5)):
        for verso, (nome, f) in ((1, LONG[idea]), (-1, SHORT[idea])):
            c5, _ = caso(verso)
            stessi.append(ore_eventi(f(c5), 5) == ore_eventi(f(a_m15(c5)), 15) and f(c5).sum() == 1)
    c5, _ = caso_idea3_m5()
    stessi.append(ore_eventi(LONG[3][1](c5), 5) == ore_eventi(LONG[3][1](a_m15(c5)), 15) and LONG[3][1](c5).sum() == 1)
    check("F3. idee 1, 2, 3: nei casi costruiti su M5 il trigger scatta su M5 e su M15 alla stessa ora (stesse "
          "finestre in minuti)", all(stessi), str(stessi))

    def avvisi(f, d):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            out = f(d)
        return out, [str(x.message) for x in w]

    h1 = Mercato(_indice("2023-05-01", giorni=60, minuti=60), seme=2).df()
    m30 = Mercato(_indice("2023-05-01", giorni=60, minuti=30), seme=2).df()
    h4 = Mercato(_indice("2023-05-01", giorni=200, minuti=240), seme=2).df()
    ok_h1 = True
    for idea in (1, 2, 3, 7):
        for _, f in (LONG[idea], SHORT[idea]):
            out, msg = avvisi(f, h1)
            ok_h1 &= not out.any() and any("fuori dai timeframe ammessi" in m for m in msg)
    check("F4. su H1 le idee 1, 2, 3 e 7 sono tutte false, con l'avviso", ok_h1)
    ok_m30 = True
    for idea in (1, 2, 3):
        out, msg = avvisi(LONG[idea][1], m30)
        ok_m30 &= not out.any() and bool(msg)
    out7, msg7 = avvisi(LONG[7][1], m30)
    check("F5. su M30 le idee 1, 2, 3 sono false con l'avviso; l'idea 7 vale (controllo ogni mezz'ora) e non avvisa",
          ok_m30 and out7.any() and not any("area_rumore" in m for m in msg7))
    ok_h4 = True
    for idea in (4, 5, 6):
        out, msg = avvisi(LONG[idea][1], h4)
        ok_h4 &= not out.any() and bool(msg)
    out4, msg4 = avvisi(LONG[4][1], h1)
    check("F6. su H4 le idee 4, 5, 6 sono false con l'avviso; su H1 l'idea 4 vale (candela oraria) senza avviso",
          ok_h4 and out4.any() and not msg4)


def esegui() -> int:
    print("=" * 70)
    print("test_trigger_intraday · E46-E52, i trigger intraday di docs/78 e docs/79")
    print("=" * 70)
    imposta_rollover(None)
    try:
        sezione_a()
        sezione_b()
        sezione_c()
        sezione_d()
        sezione_e()
        sezione_f()
    finally:
        reg.clear_registry()
    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
