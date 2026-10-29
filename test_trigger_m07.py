"""
Suite di collaudo del trigger M07 (29/10/2026, docs/77, lavoro 3): E45 long
(il rendimento a 4 ore ENTRA nel quintile piu' basso) ed E45 short (ENTRA nel
piu' alto), con le soglie e la finestra della scheda M07 della mappa.
Moduli: engine/indicatori.py (quintile_rendimento_4h, entra_nel_quintile_r4h),
entry_long.py, entry_short.py; la regola (b) del conto in engine/vetrina.py
(celle_da_contare) e la 2a con la griglia.

Cosa verifica (docs/50 §7)
--------------------------
A  i quintili sono quelli della mappa (stessa funzione, stessa finestra) e,
   rifatti a mano su barre a caso, con le soglie delle sole barre dei 365
   giorni prima;
B  le barre giuste su dati inventati: scatta dove il quintile diventa Q1 (Q5)
   venendo da un altro quintile noto, mai due barre di fila, mai dove la barra
   prima non ha quintile; long e short non scattano mai insieme;
C  niente dopo un buco nei dati: non scatta sulla barra dopo un buco ne' dove
   manca la barra di 4 ore prima;
D  verifica_lookahead (troncamento) e verifica_degenerazione: OK;
E  i doppioni (engine/famiglie.sovrapposizioni, trigger a finestra 2, soglia
   70% e 1,3 volte il caso): E45 non e' dentro E39 ne' E41, e viceversa;
F  la regola (b) del conto: con i trigger in piu' si contano solo le situazioni
   dei trigger nuovi; con un H nuovo, tutte;
G  con la griglia la 2a del Lab mostra il profilo una volta sola, dopo la scelta.

Come si lancia (da terminale, dalla cartella del progetto):

    python test_trigger_m07.py

Non serve la rete ne' i dati veri. Alla fine stampa «RISULTATO: N/N test superati».
"""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")

import entry_long
import entry_short
from engine import indicatori as ind
from engine import mappa as mp
from engine import registry as reg
from engine.ipotesi import SCHEDE
from engine.quarantena import imposta_rollover
from test_atlante import Mercato, _indice

ESITI: list[bool] = []
LONG, SHORT = "E45_RENDIMENTO_4H_ENTRA_Q1", "E45_SHORT_RENDIMENTO_4H_ENTRA_Q5"


def check(nome, condizione, dettaglio=""):
    ESITI.append(bool(condizione))
    print(f"  [{'OK' if condizione else 'FALLITO'}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""))


def muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        out = f(*a, **k)
    import matplotlib.pyplot as plt
    plt.close("all")
    return out


def sezione_a_b_c(df: pd.DataFrame):
    print("\nA · I quintili della scheda M07")
    q = ind.quintile_rendimento_4h(df)
    mappa = mp.codici_fasce(SCHEDE["M07"], mp.variabile(SCHEDE["M07"], df))
    check("A1. gli stessi codici della mappa (scheda M07: rendimento a 4 ore, quintili su 365 giorni)",
          np.array_equal(q.to_numpy(), mappa, equal_nan=True) and SCHEDE["M07"].finestra_giorni == 365)
    r = ind.rendimento_4h(df)
    rng = np.random.default_rng(1)
    pos = rng.choice(np.flatnonzero(np.isfinite(q.to_numpy())), 40, replace=False)
    a_mano = []
    for i in pos:
        t = df.index[i]
        passate = r[(r.index >= t - pd.Timedelta(days=365)) & (r.index < t)].dropna().to_numpy()
        soglie = np.quantile(passate, [0.2, 0.4, 0.6, 0.8])
        a_mano.append(float((r.iloc[i] > soglie).sum()))
    check("A2. rifatti a mano su 40 barre a caso: soglie dalle sole barre dei 365 giorni prima, la barra esclusa",
          np.array_equal(np.array(a_mano), q.to_numpy()[pos]))
    check("A3. prima di 365 giorni di storia nessun quintile", q[q.index < df.index[0] + pd.Timedelta(days=365)].isna().all())

    print("\nB · Le barre giuste")
    el, es = entry_long.entry_r4h_enters_q1(df), entry_short.entry_short_r4h_enters_q5(df)
    v, prima = q.to_numpy(), np.r_[np.nan, q.to_numpy()[:-1]]
    attese_l = (v == 0) & np.isfinite(prima) & (prima != 0)
    attese_s = (v == 4) & np.isfinite(prima) & (prima != 4)
    check("B1. long: scatta esattamente dove il quintile diventa Q1 venendo da un altro quintile noto",
          np.array_equal(el.to_numpy(), attese_l) and el.sum() > 100, f"{int(el.sum())} eventi")
    check("B2. short: esattamente dove diventa Q5 venendo da un altro quintile noto",
          np.array_equal(es.to_numpy(), attese_s) and es.sum() > 100, f"{int(es.sum())} eventi")
    check("B3. eventi, non stati: mai due barre di fila; long e short mai sulla stessa barra; mai dove la barra "
          "prima non ha quintile",
          not (el & el.shift(1, fill_value=False)).any() and not (es & es.shift(1, fill_value=False)).any()
          and not (el & es).any() and not (el.to_numpy() & ~np.isfinite(prima)).any())
    check("B4. registrati nel catalogo con il loro lato",
          entry_long.TRIGGER_LONG.get(LONG) is entry_long.entry_r4h_enters_q1
          and entry_short.TRIGGER_SHORT.get(SHORT) is entry_short.entry_short_r4h_enters_q5)

    print("\nC · Niente dopo un buco nei dati")
    buchi = df.drop(df.index[[30_000, 30_001, 30_002, 33_000]])
    qb = ind.quintile_rendimento_4h(buchi)
    eb = ind.entra_nel_quintile_r4h(buchi, 0) | ind.entra_nel_quintile_r4h(buchi, 4)
    dopo = [buchi.index.get_loc(df.index[30_003]), buchi.index.get_loc(df.index[33_001])]
    t_buco = df.index[33_000]
    senza_4h = (buchi.index > t_buco) & (buchi.index <= t_buco + pd.Timedelta(hours=4))
    check("C1. la barra dopo un buco non scatta mai (anche se il quintile cambia); dove manca la barra di 4 ore "
          "prima non c'e' quintile e non scatta",
          not eb.iloc[dopo].any() and qb[buchi.index == t_buco + pd.Timedelta(hours=4)].isna().all()
          and not eb[senza_4h & qb.isna().to_numpy()].any())
    lontano = buchi.index < df.index[29_000]
    check("C2. lontano dai buchi gli eventi sono gli stessi dello storico senza buchi",
          (eb[lontano] == (entry_long.entry_r4h_enters_q1(df) | entry_short.entry_short_r4h_enters_q5(df))
           .reindex(buchi.index)[lontano]).all())


def sezione_d_e(df: pd.DataFrame):
    print("\nD · verifica_lookahead e verifica_degenerazione")
    from engine.collaudo_catalogo import verifica_degenerazione, verifica_lookahead
    reg.clear_registry()

    def trappola(d):
        # il difetto tipico: le soglie dei quintili da tutto lo storico, futuro compreso
        r = ind.rendimento_4h(d)
        soglie = np.nanquantile(r.to_numpy(), [0.2, 0.4, 0.6, 0.8])
        q = np.where(np.isfinite(r), (r.to_numpy()[:, None] > soglie).sum(axis=1), np.nan)
        prima = np.r_[np.nan, q[:-1]]
        return pd.Series((q == 0) & np.isfinite(prima) & (prima != 0), index=d.index)

    reg.register_entry("TRAPPOLA_QUINTILI_SU_TUTTO", direction=1)(trappola)
    reg.register_entry(LONG, direction=1)(entry_long.entry_r4h_enters_q1)
    reg.register_entry(SHORT, direction=-1)(entry_short.entry_short_r4h_enters_q5)
    grezzo = df[["Open", "High", "Low", "Close", "Volume"]]
    look = muto(verifica_lookahead, grezzo, prepara=lambda d: d.copy(), verbose=False)
    righe = look[look["nome"].isin([LONG, SHORT])]
    trap = look.loc[look["nome"] == "TRAPPOLA_QUINTILI_SU_TUTTO", "esito"]
    check("D0. la trappola (soglie dei quintili da tutto lo storico) e' segnata LOOKAHEAD: il controllo la vede",
          len(trap) == 1 and trap.iloc[0] == "LOOKAHEAD", str(list(trap)))
    check("D1. verifica_lookahead per troncamento: OK sui due lati, con tagli sulle barre dove scattano",
          len(righe) == 2 and (righe["esito"] == "OK").all() and (righe["tagli"] > 20).all(),
          str(righe[["nome", "esito", "tagli"]].to_dict("records")))
    deg = muto(verifica_degenerazione, df, verbose=False)
    dr = deg[deg["nome"].isin([LONG, SHORT])]
    check("D2. verifica_degenerazione: OK sui due lati (eventi, non stati; ne' rari ne' sempre veri)",
          len(dr) == 2 and (dr["esito"] == "OK").all(), str(dr[["nome", "esito", "eventi"]].to_dict("records")))
    reg.clear_registry()

    print("\nE · I doppioni con E39 ed E41")
    from engine.famiglie import LIFT_MIN, SOGLIA_DOPPIONE, sovrapposizioni
    from engine.indicatori import aggiungi_indicatori
    d = muto(aggiungi_indicatori, df)
    for nome, f in ((LONG, entry_long.entry_r4h_enters_q1), ("E39_HOUR_REVERSAL_UP", entry_long.entry_hour_reversal_up),
                    ("E41_DAILY_QUINTILE_UP", entry_long.entry_daily_quintile_up)):
        reg.register_entry(nome, direction=1)(f)
    for nome, f in ((SHORT, entry_short.entry_short_r4h_enters_q5),
                    ("E39_SHORT_HOUR_REVERSAL_DOWN", entry_short.entry_short_hour_reversal_down),
                    ("E41_SHORT_DAILY_QUINTILE_DOWN", entry_short.entry_short_daily_quintile_down)):
        reg.register_entry(nome, direction=-1)(f)
    sov = sovrapposizioni(d, tipo="entry", finestra=2, mostra_da=0.0)
    coppie = sov[(sov["contenuta"].str.startswith("E45") | sov["dentro"].str.startswith("E45"))]
    check("E1. E45 (long e short) non e' doppione di E39 ne' di E41, in nessun verso (finestra 2, 70% e 1,3 volte "
          "il caso)", len(coppie) > 0 and not coppie["doppione"].any() and SOGLIA_DOPPIONE == 0.70 and LIFT_MIN == 1.3,
          f"quota piu' alta {coppie['quota_max'].max() if len(coppie) else 0}%")
    reg.clear_registry()


def sezione_f():
    print("\nF · La regola (b) del conto")
    from engine import vetrina as vt
    vecchi = ("E1", "E2", "E3")
    nuovi = ("E1", "E2", "E45L", "E3", "E45S")
    tab = pd.DataFrame({"candidato": [n for n in nuovi for _ in range(8)],
                        "misurata": [True] * 30 + [False, True] * 5})
    tab.attrs.update(assi=("vol_trend", "sessione"), k_misurate=int(tab["misurata"].sum()))
    prove = {"celle": {(25, ("vol_trend", "sessione", "basis"), vecchi): 60}}
    n, coperta = vt.celle_da_contare(prove, (25, ("vol_trend", "sessione"), nuovi), tab)
    attese = int(tab.loc[tab["candidato"].isin({"E45L", "E45S"}), "misurata"].sum())
    check("F1. trigger in piu', l'elenco vecchio dentro il nuovo nello stesso ordine: si contano solo le situazioni "
          "dei trigger nuovi (righe misurate)", n == attese and coperta == (25, ("vol_trend", "sessione", "basis"), vecchi),
          f"{n} su {tab.attrs['k_misurate']}")
    n16, c16 = vt.celle_da_contare(prove, (16, ("vol_trend", "sessione"), nuovi), tab)
    disordine = ("E2", "E1", "E45L", "E3", "E45S")
    nd, cd = vt.celle_da_contare(prove, (25, ("vol_trend", "sessione"), disordine), tab)
    check("F2. con un H nuovo, o con l'elenco vecchio in un altro ordine, si contano tutte",
          n16 == tab.attrs["k_misurate"] and c16 is None and nd == tab.attrs["k_misurate"] and cd is None)
    prove2 = dict(prove)
    prove2["celle"] = dict(prove["celle"])
    prove2["celle"][(25, ("vol_trend", "sessione"), ("E1", "E2", "E45L", "E3"))] = 7
    n2, c2 = vt.celle_da_contare(prove2, (25, ("vol_trend", "sessione"), nuovi), tab)
    check("F3. fra piu' voci che coprono vale quella con piu' trigger", c2[2] == ("E1", "E2", "E45L", "E3")
          and n2 == int(tab.loc[tab["candidato"] == "E45S", "misurata"].sum()))


def sezione_g(radice: Path):
    print("\nG · La 2a con la griglia: il profilo una volta sola")
    import engine.exchange as X
    from engine import registro_dataset as RD
    from engine import vetrina as vt
    df = Mercato(_indice("2022-01-03", giorni=120), seme=8).df()
    X.salva_csv(df, os.path.join(str(radice), "BINANCE_PERP_BTCUSDT_M15.csv"))
    orari = pd.date_range(df.index[0].floor("8h"), df.index[-1].ceil("8h"), freq="8h")
    X.salva_funding(X.con_intervalli(pd.DataFrame({"tasso": 0.0001}, index=orari)),
                    X.file_funding("BINANCE_PERP_BTCUSDT", radice))
    RD.azzera()
    s = muto(vt.prepara, "BINANCE_PERP_BTCUSDT", H=vt.GRIGLIA, cartella=str(radice))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        prima = vt.profilo_delle_ore(s)
    profilo_prima = s.profilo
    vt._scegli_orizzonte(s, "4 ore")
    dopo = muto(vt.profilo_delle_ore, s)
    s1 = muto(vt.prepara, "BINANCE_PERP_BTCUSDT", H=16, cartella=str(radice))
    fisso = muto(vt.profilo_delle_ore, s1)
    check("G1. con la griglia, prima della scelta la 2a non mostra il profilo: solo la nota (compare nella 2c)",
          prima is None and profilo_prima is None and "compare nella 2c" in buf.getvalue())
    check("G2. dopo la scelta la 2a mostra il profilo all'orizzonte scelto, uguale a quello con H = 16 fisso",
          dopo is not None and dopo.equals(fisso))
    RD.azzera()


def esegui() -> int:
    print("=" * 70)
    print("test_trigger_m07 · E45, il rendimento a 4 ore che entra nel quintile estremo (docs/77)")
    print("=" * 70)
    imposta_rollover(None)
    df = Mercato(_indice("2022-01-03", giorni=420), seme=21).df()
    radice = Path(tempfile.mkdtemp(prefix="trigger_m07_"))
    try:
        sezione_a_b_c(df)
        sezione_d_e(df)
        sezione_f()
        sezione_g(radice)
    finally:
        reg.clear_registry()
        shutil.rmtree(radice, ignore_errors=True)
    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
