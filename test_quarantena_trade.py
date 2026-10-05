"""
Collaudo della quarantena applicata ai trade (5/10/2026).

Si lancia da terminale, nella cartella del repo:

    python test_quarantena_trade.py

Verifica due cose, con casi a risultato noto:
  A-B  i segnali sulla quarantena non aprono trade (nei motori e nell'event study)
  C    i lati di un trade che cadono nel rollover pagano lo spread di quel
       momento, e solo quelli
  D    sui dati veri (EURUSD_M15.csv): zero ingressi in quarantena, e con
       quarantena=False i trade tornano quelli di prima
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.registry import clear_registry, register_entry, register_filter
from engine.exit_search_bt import run_exit_search_bt
from engine.filter_search_bt import run_filter_search_bt
from engine.event_study import run_event_study
from engine.due_meta import due_meta
from engine.quarantena import quarantena
from engine.quarantena_trade import (barre_in_quarantena, maschera_segnali_puliti,
                                     costo_extra_pips)
from engine.metriche import pips_per_trade, metriche_per_trade
from engine import livelli

PIP = 0.0001


def _zitto(f, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = f(*a, **k)
    return out, buf.getvalue()


def _mercato(giorni=6):
    """Prezzo piatto a 1,1000 con barre da 15 minuti, da lunedi' 8 gennaio 2024
    (inverno: il rollover delle 17:00 NY e' alle 22:00 UTC, quarantena
    21:45-23:00 UTC)."""
    idx = pd.date_range("2024-01-08 00:00", periods=96 * giorni, freq="15min", tz="UTC")
    o = np.full(len(idx), 1.1000)
    return pd.DataFrame({"Open": o, "High": o + 0.0003, "Low": o - 0.0003,
                         "Close": o, "Volume": 100.0}, index=idx)


def _segnale_a(df, orari):
    s = pd.Series(False, index=df.index)
    for t in orari:
        s[pd.Timestamp(t, tz="UTC")] = True
    return s


def esegui() -> int:
    esiti = []

    def check(nome, condizione, dettaglio=""):
        esiti.append(bool(condizione))
        print(f"  [{'OK     ' if condizione else 'FALLITO'}] {nome}"
              + (f"  — {dettaglio}" if dettaglio else ""))

    df = _mercato()
    q = quarantena(df, verbose=False)["totale"]

    # ------------------------------------------------------------ maschera --
    print("\nA · La maschera")
    ore_q = sorted({t.strftime("%H:%M") for t in df.index[q.to_numpy()]})
    check("1. la quarantena del mercato di prova e' 21:45-22:45 UTC (16:45-18:00 NY)",
          ore_q == ["21:45", "22:00", "22:15", "22:30", "22:45"], " ".join(ore_q))
    pulito = pd.Series(maschera_segnali_puliti(df, True), index=df.index)
    g = "2024-01-09 "
    check("2. segnale alle 21:15 tradabile; alle 21:30 no (entrerebbe alle 21:45); "
          "alle 22:45 no; alle 23:00 si'",
          pulito[g + "21:15"] and not pulito[g + "21:30"] and not pulito[g + "22:45"]
          and pulito[g + "23:00"])
    check("3. quarantena=False: tutto tradabile", maschera_segnali_puliti(df, False).all())
    check("4. accetta True, il DataFrame di quarantena() e una Series: stesso risultato",
          np.array_equal(maschera_segnali_puliti(df, True),
                         maschera_segnali_puliti(df, quarantena(df, verbose=False)))
          and np.array_equal(maschera_segnali_puliti(df, True), maschera_segnali_puliti(df, q)))
    senza_fuso = df.copy(); senza_fuso.index = senza_fuso.index.tz_localize(None)
    try:
        barre_in_quarantena(senza_fuso, True); errore = False
    except ValueError:
        errore = True
    check("5. indice senza fuso con quarantena=True: errore chiaro, non un silenzio", errore)

    # -------------------------------------------------------------- motori --
    print("\nB · Dentro i motori")
    clear_registry()
    orari = [g + "10:00", g + "21:30", g + "22:15", "2024-01-10 10:00"]
    register_entry("T_Q_LONG", 1)(lambda d: _segnale_a(df, orari).reindex(d.index).fillna(False))
    register_entry("T_Q_SHORT", -1)(lambda d: _segnale_a(df, [g + "22:00", "2024-01-11 10:00"])
                                    .reindex(d.index).fillna(False))
    register_filter("T_Q_SEMPRE", 0)(lambda d: pd.Series(True, index=d.index))
    # n_barre=2: il trade delle 21:45 e' gia' chiuso quando arriva il segnale delle 22:15
    p = dict(n_barre=2, perc_sl=0.0, perc_tp=0.0, spread=0.0, commission=0.0, cash=10_000,
             min_trades=1)

    es, testo = _zitto(run_exit_search_bt, df, entry_cols_long=["T_Q_LONG"], **p)
    t = es.trades()
    ingressi = [x.strftime("%d %H:%M") for x in pd.DatetimeIndex(t["EntryTime"])]
    check("6. run_exit_search_bt: dei 4 segnali restano i 2 fuori quarantena",
          ingressi == ["09 10:15", "10 10:15"], " · ".join(ingressi))
    check("7. ... e lo dice: «segnali scartati per quarantena — T_Q_LONG: 2»",
          "segnali scartati per quarantena — T_Q_LONG: 2" in testo)
    es0, testo0 = _zitto(run_exit_search_bt, df, entry_cols_long=["T_Q_LONG"],
                         quarantena=False, **p)
    check("8. quarantena=False: tutti e 4 i trade, nessun messaggio",
          len(es0.trades()) == 4 and "quarantena" not in testo0, f"{len(es0.trades())} trade")

    fs, testo = _zitto(run_filter_search_bt, df, entry_long="T_Q_LONG", entry_short="T_Q_SHORT",
                       filtri=["T_Q_SEMPRE"], **p)
    check("9. run_filter_search_bt: baseline 3 trade (2 long + 1 short), filtro uguale",
          len(fs.trades()) == 3 and len(fs.trades("T_Q_SEMPRE")) == 3
          and "long 2, short 1" in testo, f"{len(fs.trades())} trade")
    q_bar = q.to_numpy()
    check("10. nessun trade entra su una barra in quarantena",
          not q_bar[fs.trades()["EntryBar"].to_numpy()].any())
    register_entry("T_Q_TANTI", 1)(lambda d: pd.Series(np.arange(len(d)) % 4 == 0, index=d.index))
    ev, testo = _zitto(run_event_study, df, entry_names=["T_Q_TANTI"], horizon=4, min_trades=10)
    ev0, _ = _zitto(run_event_study, df, entry_names=["T_Q_TANTI"], horizon=4, min_trades=10,
                    quarantena=False)
    n, n0 = int(ev.sintesi["trades"].iloc[0]), int(ev0.sintesi["trades"].iloc[0])
    grezzo = pd.Series(np.arange(len(df)) % 4 == 0, index=df.index)
    atteso = int((grezzo & pulito).iloc[:-1].sum())   # l'ultima barra non ha un ingresso
    check("11. event study: i trigger sulla quarantena non si misurano",
          n == atteso and n0 > n and "trigger scartati per quarantena" in testo,
          f"{n} con, {n0} senza")

    # --------------------------------------------------------------- costi --
    print("\nC · Lo spread del rollover")
    # segnale alle 20:45 -> ingresso 21:00, uscita dopo 4 barre alle 22:00 (in quarantena)
    clear_registry()
    register_entry("T_C_DENTRO", 1)(lambda d: _segnale_a(df, [g + "20:45", "2024-01-10 10:00"])
                                    .reindex(d.index).fillna(False))
    spread = 0.8 * PIP / 1.1000          # 0,8 pips al prezzo di 1,1000
    pc = dict(n_barre=4, perc_sl=0.0, perc_tp=0.0, spread=spread, commission=0.0, cash=10_000)
    fc, _ = _zitto(run_filter_search_bt, df, entry_long="T_C_DENTRO", filtri=[],
                   spread_rollover_pips=1.5, **pc)
    t = fc.trades()
    extra = t["CostoExtraPips"].to_numpy()
    uscite = [x.strftime("%H:%M") for x in pd.DatetimeIndex(t["ExitTime"])]
    check("12. il trade che esce alle 22:00 paga (1,5 − 0,8) / 2 = 0,35 pips; l'altro zero",
          uscite == ["22:00", "11:15"] and np.allclose(extra, [0.35, 0.0], atol=1e-3),
          f"uscite {uscite} · extra {np.round(extra, 4).tolist()}")
    lordi, netti = pips_per_trade(t, PIP, 0.0)
    check("13. pips netti = lordi − costo extra; i lordi pagano gia' lo spread normale (−0,8)",
          np.allclose(lordi, [-0.8, -0.8], atol=1e-3) and np.allclose(netti, [-1.15, -0.8], atol=1e-3),
          f"lordi {np.round(lordi.to_numpy(), 3).tolist()} · netti {np.round(netti.to_numpy(), 3).tolist()}")
    r = fc.risultati.iloc[0]
    check("14. avg_trade_netto e costo_pips della tabella lo contengono",
          np.isclose(r["avg_trade_netto"], -0.975, atol=1e-3) and np.isclose(r["costo_pips"], 0.175, atol=1e-3),
          f"avg_trade_netto {r['avg_trade_netto']:.3f} · costo_pips {r['costo_pips']:.3f}")
    fn, _ = _zitto(run_filter_search_bt, df, entry_long="T_C_DENTRO", filtri=[], **pc)
    check("15. senza spread_rollover_pips: colonna a zero, netti = lordi (come prima)",
          (fn.trades()["CostoExtraPips"] == 0).all()
          and np.allclose(*[x.to_numpy() for x in pips_per_trade(fn.trades(), PIP, 0.0)]))
    # ingresso E uscita in quarantena, con la quarantena degli ingressi spenta
    clear_registry()
    register_entry("T_C_DUE", 1)(lambda d: _segnale_a(df, [g + "21:45"]).reindex(d.index).fillna(False))
    f2, _ = _zitto(run_filter_search_bt, df, entry_long="T_C_DUE", filtri=[],
                   spread_rollover_pips=1.5, quarantena=False, **{**pc, "n_barre": 2})
    check("16. quarantena=False non calcola nessun costo extra (motore di prima, per intero)",
          len(f2.trades()) == 1 and (f2.trades()["CostoExtraPips"] == 0).all())
    con_q = costo_extra_pips(f2.trades().drop(columns="CostoExtraPips"), df, True, spread, 1.5, PIP)
    check("17. due lati in quarantena (ingresso 22:00, uscita 22:30) pagano due volte: 0,70 pips",
          np.isclose(con_q["CostoExtraPips"].iloc[0], 0.70, atol=1e-3),
          f"{con_q['CostoExtraPips'].iloc[0]:.3f}")
    basso = costo_extra_pips(f2.trades().drop(columns="CostoExtraPips"), df, True, spread, 0.5, PIP)
    check("18. uno spread di rollover piu' basso del normale non diventa uno sconto",
          (basso["CostoExtraPips"] == 0).all())
    vecchi = f2.trades().drop(columns="CostoExtraPips")
    check("19. trade senza la colonna (formato di prima): pips_per_trade funziona invariato",
          np.allclose(*[x.to_numpy() for x in pips_per_trade(vecchi, PIP, 0.0)])
          and metriche_per_trade(vecchi, PIP, 0.0)["costo_pips"] == 0.0)

    # ---------------------------------------------------------- dati veri --
    print("\nD · Sui dati veri (EURUSD_M15.csv)")
    csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "EURUSD_M15.csv")
    if not os.path.exists(csv):
        print("  [SALTATO] EURUSD_M15.csv non trovato")
    else:
        import entry_long, entry_short
        from engine.broker_tz_diagnostic import to_utc_index
        from engine.indicatori import aggiungi_indicatori
        from engine.splitting import split_is_oos
        clear_registry(); livelli.svuota_cache()
        with contextlib.redirect_stdout(io.StringIO()):
            vero = to_utc_index(pd.read_csv(csv, index_col="Date"), "A_US_DST (NY+7h)", on_dst_gap="drop")
            vero = aggiungi_indicatori(vero)
            d_is, _ = split_is_oos(vero, 0.8)
            entry_long.registra_trigger_long(); entry_short.registra_trigger_short()
        sp = 0.8 * PIP / float(d_is["Close"].median())
        pv = dict(entry_long="E11_INVERTED_HAMMER", entry_short="E4_SHORT_EMA_CROSS_DOWN",
                  n_barre=25, filtri=[], perc_sl=90.0, perc_tp=0.0, spread=sp, commission=0.0,
                  cash=10_000_000)
        con, _ = _zitto(run_filter_search_bt, d_is, spread_rollover_pips=1.5, **pv)
        senza, _ = _zitto(run_filter_search_bt, d_is, quarantena=False, **pv)
        qv = quarantena(d_is, verbose=False)["totale"].to_numpy()
        tc, ts = con.trades(), senza.trades()
        in_q_con = int(qv[tc["EntryBar"].to_numpy()].sum())
        in_q_senza = int(qv[ts["EntryBar"].to_numpy()].sum())
        seg_q = int(qv[tc["EntryBar"].to_numpy() - 1].sum())
        check("20. con la quarantena: zero ingressi e zero segnali su barre in quarantena",
              in_q_con == 0 and seg_q == 0 and in_q_senza > 0,
              f"{len(tc)} trade, 0 in quarantena · senza: {len(ts)} trade, {in_q_senza} in quarantena")
        usc_q = qv[tc["ExitBar"].to_numpy()]
        ex = tc["CostoExtraPips"].to_numpy()
        check("21. pagano il costo extra tutti e soli i trade che escono in quarantena",
              usc_q.sum() > 0 and (ex[usc_q] > 0).all() and (ex[~usc_q] == 0).all()
              and ex.max() < 0.45,
              f"{int(usc_q.sum())} uscite in quarantena, extra medio {ex[usc_q].mean():.3f} pips")
        _, netti = pips_per_trade(tc, PIP, 0.0)
        da_libreria = tc["PnL"].to_numpy() / np.abs(tc["Size"].to_numpy()) / PIP
        check("22. pips netti = PnL della libreria − costo extra, trade per trade",
              np.allclose(netti.to_numpy(), da_libreria - ex, atol=1e-9))
        dm, _ = _zitto(due_meta, d_is, con, [None], perc_sl=90.0, perc_tp=0.0, spread=sp,
                       commission=0.0, cash=10_000_000, spread_rollover_pips=1.5)
        tot = sum(int(qv_.sum()) for qv_ in (
            quarantena(d_is.iloc[:len(d_is) // 2], verbose=False)["totale"].to_numpy()[dm.metà1.trades()["EntryBar"].to_numpy()],
            quarantena(d_is.iloc[len(d_is) // 2:], verbose=False)["totale"].to_numpy()[dm.metà2.trades()["EntryBar"].to_numpy()]))
        check("23. due_meta eredita la quarantena e accetta spread_rollover_pips",
              tot == 0 and "CostoExtraPips" in dm.metà1.trades().columns,
              f"metà1 {len(dm.metà1.trades())} trade, metà2 {len(dm.metà2.trades())}")

    ok = sum(esiti)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{len(esiti)} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == len(esiti) else 1


if __name__ == "__main__":
    sys.exit(esegui())
