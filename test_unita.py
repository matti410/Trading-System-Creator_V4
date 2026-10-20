"""
Suite di validazione delle UNITA' DI RISCHIO bp e ATR (20/10/2026, docs/63 §4,
lavoro A): engine/metriche.py (bp_per_trade, atr_alla_entrata, atr_per_trade),
engine/stagionalita.py (in_unita, rendimenti_avanti_unita), le colonne e
l'unita' che decide di engine/rosa.py (rosa_entry, rosa_sistemi), le voci
ev_bp ed ev_atr di engine/giudizio.scheda_strategia e il riepilogo della
vetrina.

Cosa verifica
-------------
A  casi a mano: lo stesso trade dell'1% a 7.000 e a 70.000 vale 70 e 700
   pips ma 100 bp entrambi; una commissione dello 0,05% per lato vale 10 bp
   a qualunque prezzo; l'ATR si legge alla barra del segnale;
B  i rendimenti a H barre nelle tre unita' (pips identici a prima);
C  rosa_entry: colonne di prima invariate e bp/ATR in coda; scarto in bp
   contro il calcolo a mano; con unita="bp" decide il bp;
D  rosa_sistemi: lo scarto in bp dei trade veri contro il calcolo a mano;
   con unita="bp" decide il bp;
E  scheda_strategia: ev_bp ed ev_atr;
F  vetrina: l'ATR della sessione e il costo per trade in bp nel riepilogo.

Come si lancia (da terminale, dalla cartella del progetto):

    python test_unita.py

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

from engine import registry as R
from engine.exit_search_bt import run_exit_search_bt
from engine.giudizio import scheda_strategia, t_stat
from engine.indicatori import atr_giornaliero_chiuso
from engine.livelli import GIORNATA_UTC, imposta_giornata, svuota_cache
from engine.metriche import atr_alla_entrata, atr_per_trade, bp_per_trade, pips_per_trade
from engine.quarantena import imposta_rollover
from engine.rosa import rosa_entry, rosa_sistemi
from engine.stagionalita import in_unita, rendimenti_avanti, rendimenti_avanti_unita


def muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def storico(giorni=120, da=7_000.0, a=70_000.0, seme=3):
    """24/7 M15 da `da` a `a` (un prezzo che si moltiplica per 10), con rumore."""
    idx = pd.date_range("2023-01-02", periods=giorni * 96, freq="15min", tz="UTC")
    rng = np.random.default_rng(seme)
    tendenza = np.log(a / da) / len(idx)
    close = da * np.exp(np.cumsum(rng.normal(tendenza, 0.003, len(idx))))
    open_ = np.r_[da, close[:-1]]
    alto = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.001, len(idx))))
    basso = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.001, len(idx))))
    return pd.DataFrame({"Open": open_, "High": alto, "Low": basso, "Close": close,
                         "Volume": rng.uniform(1, 100, len(idx))}, index=idx.rename("Date"))


def trades_finti(entrate, uscite, size=1.0, tempi=None, costo_extra=None):
    t = pd.DataFrame({"Size": size, "EntryPrice": np.asarray(entrate, float),
                      "ExitPrice": np.asarray(uscite, float), "EntryBar": 0, "ExitBar": 1})
    if tempi is not None:
        t["EntryTime"] = tempi
    if costo_extra is not None:
        t["CostoExtraPips"] = costo_extra
    return t


def main() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK  " if condizione else "FAIL"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    # ------------------------------------------------------------ a mano --
    print("\nA · Casi a mano")
    tr = trades_finti([7_000.0, 70_000.0], [7_070.0, 70_700.0])
    lp, _ = pips_per_trade(tr, 1.0)
    lb, nb = bp_per_trade(tr, 1.0)
    check("A1. +1% a 7.000 e a 70.000: 70 e 700 pips, 100 bp entrambi",
          np.allclose(lp, [70, 700]) and np.allclose(lb, [100, 100]) and np.allclose(nb, lb))
    piatto = trades_finti([7_000.0, 70_000.0], [7_000.0, 70_000.0])
    _, nb = bp_per_trade(piatto, 1.0, commission=0.0005)
    check("A2. commissione 0,05% per lato = 10 bp andata e ritorno a qualunque prezzo",
          np.allclose(nb, [-10.0, -10.0]))
    corto = trades_finti([70_000.0], [69_300.0], size=-1.0, costo_extra=[7.0])
    lb, nb = bp_per_trade(corto, 1.0)
    check("A3. short +1% = +100 bp; il costo extra (7 pips a 70.000) toglie 1 bp",
          np.isclose(lb.iloc[0], 100.0) and np.isclose(nb.iloc[0], 99.0))
    idx = pd.date_range("2024-01-01", periods=6, freq="15min", tz="UTC")
    atr = pd.Series([np.nan, 50.0, 60.0, 70.0, 80.0, 90.0], index=idx)
    tr = trades_finti([100.0, 100.0, 100.0], [110.0, 110.0, 110.0], tempi=[idx[3], idx[1], idx[0]])
    a = atr_alla_entrata(tr, atr)
    check("A4. ATR letto alla barra del segnale (quella prima dell'ingresso); NaN senza valore",
          a.iloc[0] == 60.0 and np.isnan(a.iloc[1]) and np.isnan(a.iloc[2]))
    la, na = atr_per_trade(tr, atr, 1.0)
    check("A5. risultato in ATR = pips x pip / ATR (+10 su ATR 60 = 0,1667)",
          np.isclose(la.iloc[0], 10 / 60) and np.isnan(la.iloc[1]) and np.allclose(na.iloc[:1], la.iloc[:1]))
    vuoti = bp_per_trade(trades_finti([], []), 1.0)
    check("A6. nessun trade: serie vuote", len(vuoti[0]) == 0 and len(vuoti[1]) == 0)

    # ----------------------------------------------------- rendimenti a H --
    print("\nB · Rendimenti a H barre nelle tre unita'")
    imposta_rollover(None)
    imposta_giornata(GIORNATA_UTC)
    svuota_cache()
    df = storico()
    H, pip = 8, 1.0
    atr_df = atr_giornaliero_chiuso(df)
    fp = rendimenti_avanti_unita(df, H, "pips", pip)
    check("B1. in pips identici a rendimenti_avanti", np.array_equal(fp, rendimenti_avanti(df, H, pip), equal_nan=True))
    ing = df["Open"].to_numpy()[1:]
    fb = rendimenti_avanti_unita(df, H, "bp", pip)
    attesi = (df["Close"].to_numpy()[H:] - ing[: len(df) - H]) / ing[: len(df) - H] * 10_000
    check("B2. in bp = (Close[i+H] - Open[i+1]) / Open[i+1] x 10.000",
          np.allclose(fb[: len(df) - H], attesi) and np.isnan(fb[-H:]).all())
    fa = rendimenti_avanti_unita(df, H, "atr", pip, atr=atr_df)
    check("B3. in ATR = pips / ATR al segnale; NaN nelle prime giornate senza ATR",
          np.allclose(fa, fp * pip / atr_df.to_numpy(), equal_nan=True) and np.isnan(fa[:96 * 5]).all())
    try:
        in_unita(fp, "R", pip)
        err1 = False
    except ValueError:
        err1 = True
    try:
        rendimenti_avanti_unita(df, H, "atr", pip)
        err2 = False
    except ValueError:
        err2 = True
    check("B4. unita' sconosciuta o ATR mancante: si ferma con errore", err1 and err2)

    # ------------------------------------------------------------ rosa_entry --
    print("\nC · rosa_entry nelle tre unita'")
    R.clear_registry()

    @R.register_entry("TEST_LONG_OGNI_ORA", 1)
    def _ogni_ora(d):
        return pd.Series((d.index.minute == 0) & (d.index.hour % 3 == 0), index=d.index)

    @R.register_entry("TEST_SHORT_MEZZORA", -1)
    def _mezzora(d):
        return pd.Series((d.index.minute == 30) & (d.index.hour % 4 == 1), index=d.index)

    nomi = ["TEST_LONG_OGNI_ORA", "TEST_SHORT_MEZZORA"]
    kw = dict(nomi=nomi, min_eventi=50, quarantena=False, baseline="globale", atr=atr_df)
    rp = muto(rosa_entry, df, H, pip, **kw)
    vecchie = ["candidato", "direction", "eventi", "scarto_pips", "t_netto", "p", "bh", "due_meta",
               "candidata", "famiglia", "nella_rosa", "rho_max", "perche"]
    check("C1. unita='pips': colonne di prima in testa, bp e ATR in coda, decide il pips",
          list(rp.columns) == vecchie + [f"{c}_{u}" for u in ("bp", "atr") for c in ("scarto", "t", "due_meta")]
          and rp.attrs["unita"] == "pips")
    riga = rp.set_index("candidato").loc["TEST_LONG_OGNI_ORA"]
    pos = np.flatnonzero(_ogni_ora(df).to_numpy() & np.isfinite(fb))
    a_mano = float(np.mean(fb[pos])) - float(np.nanmean(fb))
    check("C2. scarto in bp (baseline globale) contro il calcolo a mano",
          np.isclose(riga["scarto_bp"], a_mano), f"{riga['scarto_bp']:.3f} bp")
    rb = muto(rosa_entry, df, H, pip, unita="bp", **kw).set_index("candidato")
    rp_i = rp.set_index("candidato")
    check("C3. unita='bp': decide il bp (t_netto = t_bp della prova in pips, due meta' in bp)",
          np.allclose(rb["t_netto"], rp_i.loc[rb.index, "t_bp"])
          and (rb["due_meta"] == rp_i.loc[rb.index, "due_meta_bp"]).all()
          and "scarto_bp" in rb.columns and "scarto_pips" in rb.columns and rb.attrs["unita"] == "bp")
    ro = muto(rosa_entry, df, H, pip, nomi=nomi, min_eventi=50, quarantena=False, atr=atr_df)
    check("C4. con la baseline oraria le colonne in bp e ATR ci sono e sono finite",
          np.isfinite(ro[["scarto_bp", "t_bp", "scarto_atr", "t_atr"]].to_numpy(dtype=float)).all())
    senza = muto(rosa_entry, df, H, pip, nomi=nomi, min_eventi=50, quarantena=False, unita_extra=())
    check("C5. unita_extra vuoto: le colonne di prima e basta", list(senza.columns[:13]) == vecchie
          and not any(c.endswith(("_bp", "_atr")) for c in senza.columns))

    # ----------------------------------------------------------- rosa_sistemi --
    print("\nD · rosa_sistemi nelle tre unita'")
    es = muto(run_exit_search_bt, df, entry_cols_long=["TEST_LONG_OGNI_ORA", None],
              entry_cols_short=["TEST_SHORT_MEZZORA", None], n_barre=H, perc_sl=0.0, perc_tp=0.0,
              spread=0.0, commission=0.0005, cash=10_000_000, pip_size=pip, verbose=False)
    rs = muto(rosa_sistemi, es, df, pip, commission=0.0005, baseline="globale", atr=atr_df)
    comb = es.risultati.iloc[0]["combinazione"]
    trd = es.trades(comb)
    _, netti = pips_per_trade(trd, pip, 0.0005)
    segno = np.where(trd["Size"] > 0, 1, -1)
    deriva = float(np.nanmean(np.diff(df["Open"].to_numpy()))) / pip
    x = netti.to_numpy() - segno * deriva * (trd["ExitBar"] - trd["EntryBar"]).to_numpy()
    xb = x * pip * 10_000 / trd["EntryPrice"].to_numpy()
    r_s = rs.set_index("combinazione").loc[comb]
    check("D1. scarto e t in bp dei trade veri contro il calcolo a mano",
          np.isclose(r_s["scarto_bp"], xb.mean()) and np.isclose(r_s["t_bp"], t_stat(xb)),
          f"{len(trd)} trade, {r_s['scarto_bp']:.3f} bp")
    rsb = muto(rosa_sistemi, es, df, pip, commission=0.0005, baseline="globale", atr=atr_df,
               unita="bp").set_index("combinazione")
    rs_i = rs.set_index("combinazione")
    check("D2. unita='bp': decide il bp (t_netto = t_bp della prova in pips)",
          np.allclose(rsb["t_netto"], rs_i.loc[rsb.index, "t_bp"], equal_nan=True))
    check("D3. con unita='pips' t_netto e scarto_pips come prima (scarto_pips = media di x)",
          np.isclose(r_s["scarto_pips"], x.mean()) and np.isclose(r_s["t_netto"], t_stat(x)))

    # ---------------------------------------------------------------- scheda --
    print("\nE · scheda_strategia")
    k = scheda_strategia(trd, pip, 0.0005, montecarlo=False, verbose=False, n_boot=200)
    k_atr = scheda_strategia(trd, pip, 0.0005, montecarlo=False, verbose=False, n_boot=200, atr=atr_df)
    check("E1. ev_bp = media dei bp netti; ev_atr NaN senza ATR",
          np.isclose(k["ev_bp"], bp_per_trade(trd, pip, 0.0005)[1].mean()) and np.isnan(k["ev_atr"]))
    check("E2. con l'ATR: ev_atr = media dei netti in ATR; ev_pips invariato",
          np.isclose(k_atr["ev_atr"], np.nanmean(atr_per_trade(trd, atr_df, pip, 0.0005)[1]))
          and k_atr["ev_pips"] == k["ev_pips"])
    R.clear_registry()

    # ---------------------------------------------------------------- vetrina --
    print("\nF · Vetrina")
    import engine.vetrina as v
    from engine import exchange as X
    with tempfile.TemporaryDirectory() as tmp:
        X.salva_csv(storico(giorni=200, da=20_000.0, a=60_000.0), os.path.join(tmp, "BINANCE_PERP_BTCUSDT_M15.csv"))
        s = muto(v.prepara, "BINANCE_PERP_BTCUSDT", H=8, cartella=tmp)
    rie = s.tabelle["riepilogo"].set_index("")[" "]
    check("F1. sessione con l'ATR sullo storico intero",
          s.atr is not None and s.atr.index.equals(s.df.index) and s.atr.notna().mean() > 0.9)
    check("F2. riepilogo: «Costo per trade in bp», commissione 10,0 bp, sotto il costo di prima",
          "Costo per trade in bp" in rie.index and "commissione 10,0 bp" in rie["Costo per trade in bp"]
          and list(rie.index).index("Costo per trade in bp") == list(rie.index).index("Costo per trade") + 1,
          rie.get("Costo per trade in bp", ""))
    R.clear_registry()

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(main())
