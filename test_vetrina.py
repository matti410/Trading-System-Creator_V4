"""
Suite di validazione della VETRINA (engine/vetrina.py, 6/10/2026).

Cosa verifica
-------------
La vetrina e' solo una facciata: non deve cambiare nessun numero. Qui si
esegue il percorso delle sette schermate su EURUSD e si confronta ogni
risultato con quello che danno le funzioni dell'engine chiamate
direttamente, come nel notebook di lavoro, con le stesse scelte.
Poi i casi particolari: un lato solo, schermate saltate, nomi sbagliati,
costi senza MetaTrader, lettura delle condizioni dal registro.

Come si lancia (da terminale, dalla cartella del progetto):

    python test_vetrina.py

Su Colab, in una cella:   !python test_vetrina.py

Serve il file EURUSD_M15.csv nella cartella del progetto (c'e' gia' nel repo).
Dura uno-due minuti. Alla fine stampa «RISULTATO: N/N test superati».
"""
from __future__ import annotations

import contextlib
import io
import sys
import warnings

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")

import engine.registry as reg
import engine.vetrina as v
from engine.due_meta import due_meta
from engine.exit_search_bt import run_exit_search_bt
from engine.filter_search_bt import BASELINE, run_filter_search_bt
from engine.event_study import run_event_study
from engine.montecarlo import montecarlo_completo, pips_per_dataset

LONG = ["E11_INVERTED_HAMMER", "E1_RSI_CROSS_OVERSOLD"]
SHORT = ["E9_SHORT_CLOSING_PATTERN_ONLY_II", "E4_SHORT_EMA_CROSS_DOWN"]
H, BL, BS, SL, TP = 25, 10, 18, 90.0, 0.0


def muto(f, *a, **k):
    """Esegue una schermata senza stamparne l'output."""
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def uguali(a: pd.DataFrame, b: pd.DataFrame, chiave: str) -> bool:
    a = a.sort_values(chiave).reset_index(drop=True)
    b = b.sort_values(chiave).reset_index(drop=True)
    return a.equals(b)


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def errore(f, tipo=Exception):
        try:
            muto(f)
        except tipo:
            return True
        return False

    print("\nA · I costi senza MetaTrader")
    check("1. punto dedotto dai prezzi: 5 decimali -> 0.00001",
          v._punto_da_prezzi(pd.Series([1.10123, 1.10456, 1.09871])) == 1e-5)
    check("2. punto dedotto dai prezzi: 2 decimali -> 0.01",
          v._punto_da_prezzi(pd.Series([51670.18, 60210.5, 43000.07])) == 0.01)
    idx = pd.date_range("2024-01-01", periods=3000, freq="15min", tz="UTC")
    finto = pd.DataFrame({"Open": 50000.0, "High": 50010.0, "Low": 49990.0,
                          "Close": np.round(50000 + np.arange(3000) * 0.37, 2),
                          "spread": 800.0}, index=idx)
    sp = v.spread_in_pips("XXXUSD", finto)
    check("3. strumento fuori tabella: spread letto dai dati (800 punti x 0.01 = 8 pips)",
          abs(sp["normale"] - 8.0) < 1e-9 and "dati" in sp["fonte"], f"{sp['normale']:.2f} pips")
    check("4. strumento fuori tabella con colonna spread a zero -> errore chiaro",
          errore(lambda: v.spread_in_pips("XXXUSD", finto.assign(spread=0.0)), ValueError))
    sp = v.spread_in_pips("EURUSD", finto)
    check("5. EURUSD: valori di listino del conto Standard (0.8 e 1.5 pips)",
          (sp["normale"], sp["rollover"]) == (0.8, 1.5))

    print("\nB · Le sette schermate su EURUSD, contro l'engine chiamato direttamente")
    s = muto(v.prepara, "EURUSD", H)
    check("6. prepara: dati divisi 80/20, indice UTC, costi pronti",
          len(s.df_is) + len(s.df_oos) == len(s.df) and str(s.df.index.tz) == "UTC"
          and abs(len(s.df_is) / len(s.df) - 0.8) < 0.001
          and s.costi["commission"] == 0.0 and s.costi["spread_rollover_pips"] == 1.5,
          f"{len(s.df_is):,} + {len(s.df_oos):,} barre")
    # il prezzo di riferimento e' la mediana dello storico completo, prima che
    # gli indicatori tolgano le barre di avvio: come nel notebook di lavoro
    grezzo = pd.read_csv("EURUSD_M15.csv", index_col="Date")
    with contextlib.redirect_stdout(io.StringIO()):
        from engine.broker_tz_diagnostic import to_utc_index
        grezzo = to_utc_index(grezzo, v.REGOLA_FUSO, on_dst_gap="drop")
    check("7. prepara: lo spread passato al backtest vale 0.8 pips",
          abs(s.costi["spread"] * float(grezzo["Close"].median()) / s.pip - 0.8) < 1e-9)

    ev = muto(v.esplora, s)
    with contextlib.redirect_stdout(io.StringIO()):
        ev_rif = run_event_study(s.df_is, entry_names=v._trigger_candidati(), horizon=H,
                                 min_trades=200, verbose=False)
    check("8. esplora: sintesi identica a run_event_study", ev.sintesi.equals(ev_rif.sintesi),
          f"{len(ev.sintesi)} trigger")
    cl = muto(v.classifiche, s)
    sint = ev.sintesi
    ok = True
    for nome, d in (("long", 1), ("short", -1)):
        t = cl[nome]
        rif = sint.set_index("candidato").loc[t["Trigger"]]
        ok &= bool((rif["direction"] == d).all())
        # nessun ribaltamento: la sintesi e' gia' «a favore del trade» per i due lati
        ok &= np.allclose(t["Movimento a favore (pips)"].to_numpy(), rif["picco_pips"].to_numpy())
        ok &= np.allclose(t["Solidità del segnale"].to_numpy(), rif["volte_incertezza"].to_numpy())
        ok &= t["Solidità del segnale"].is_monotonic_decreasing
    check("9. classifiche: ogni lato ha solo i suoi trigger, numeri della sintesi senza ribaltamenti, "
          "ordine per solidita'", ok)

    muto(v.scegli_trigger, s, long=", ".join(LONG), short=SHORT)
    from entry_composita import risolvi_scelta
    with contextlib.redirect_stdout(io.StringIO()):
        L, S = risolvi_scelta(LONG, lato="long"), risolvi_scelta(SHORT, lato="short")
    check("10. scegli_trigger: stringa con virgole o lista, stesso nome di risolvi_scelta",
          (s.entry_long, s.entry_short) == (L, S), f"{s.entry_long}")

    muto(v.imposta_uscite, s, BL, BS, SL, TP)
    comuni = dict(n_barre=BL, n_barre_long=BL, n_barre_short=BS, perc_sl=SL, perc_tp=TP,
                  inverti_su_opposto=True, verbose=False, **s.costi)
    with contextlib.redirect_stdout(io.StringIO()):
        es = run_exit_search_bt(s.df_is, entry_cols_long=[L, None], entry_cols_short=[S, None], **comuni)
    check("11. imposta_uscite: tabella identica a run_exit_search_bt (3 sistemi)",
          uguali(s.es.risultati, es.risultati, "combinazione") and len(es.risultati) == 3)
    t = s.tabelle["uscite"]
    check("12. imposta_uscite: le tre righe sono Long + Short, Solo long, Solo short",
          list(t["Sistema"]) == ["Long + Short", "Solo long", "Solo short"])
    riga = es.risultati[es.risultati["entry_long"].notna() & es.risultati["entry_short"].notna()].iloc[0]
    check("13. imposta_uscite: trade e guadagno netto della riga mostrata = quelli del motore",
          int(t.iloc[0]["Trade"]) == int(riga["trades"])
          and abs(t.iloc[0]["Guadagno medio netto per trade (pips)"] - riga["avg_trade_netto"]) < 1e-12)

    filtri = reg.list_filters(0) + reg.list_filters(1) + reg.list_filters(-1)
    muto(v.trova_strategia, s)
    with contextlib.redirect_stdout(io.StringIO()):
        fs = run_filter_search_bt(s.df_is, entry_long=L, entry_short=S, exit_rule_pair=None,
                                  filtri=filtri, min_trades_giudizio=100, p_max=5.0, alpha=0.05,
                                  **comuni)
    check("14. trova_strategia: tabella identica a run_filter_search_bt su tutti i filtri del registro",
          uguali(s.fs.risultati, fs.risultati, "filtro"), f"{len(filtri)} filtri, {len(fs.risultati)} righe")
    promossi = fs.risultati.loc[fs.risultati["esito"].isin(["DA VALUTARE", "CAMPIONE CORTO"]), "filtro"].to_list()
    if promossi:
        with contextlib.redirect_stdout(io.StringIO()):
            dm = due_meta(s.df_is, fs, [None, *promossi], perc_sl=SL, perc_tp=TP, verbose=False, **s.costi)
        attesi = dm.tabella.loc[dm.tabella["verdetto"] == "regge", "filtro"].to_list()
        check("15. trova_strategia: sopravvissuti = verdetto «regge» di due_meta",
              sorted(s.sopravvissuti) == sorted(attesi) and s.dm.tabella.equals(dm.tabella))
    else:
        check("15. trova_strategia: nessun promosso -> nessun sopravvissuto, due_meta non eseguita",
              s.sopravvissuti == [] and s.dm is None)

    # la scheda si prova su una riga filtrata (una coppia) e sul sistema base
    etichetta = next(f for f in fs.risultati["filtro"] if f != BASELINE
                     and fs.risultati.set_index("filtro").loc[f, "filtro_long"] != "—"
                     and fs.risultati.set_index("filtro").loc[f, "filtro_short"] != "—")
    for n, filtro in ((16, etichetta), (17, None)):
        tab = muto(v.scheda, s, filtro)
        membri = v._membri_filtro(s, filtro) if filtro else []
        with contextlib.redirect_stdout(io.StringIO()):
            oos = run_filter_search_bt(s.df_oos, entry_long=L, entry_short=S, exit_rule_pair=None,
                                       filtri=membri, finestra=500, lag=1, margin=1.0,
                                       min_trades=fs.min_trades, **comuni)
        check(f"{n}. scheda ({filtro or 'sistema base'}): out-of-sample identico a run_filter_search_bt",
              uguali(s.oos.risultati, oos.risultati, "filtro")
              and s.oos.trades(filtro).equals(oos.trades(filtro))
              and tab.iloc[0]["Out-of-sample"] == v._fmt(len(oos.trades(filtro))),
              f"{len(oos.trades(filtro))} trade")

    r = muto(v.stress_test, s, 10_000)
    pips = pips_per_dataset(fs.trades(None), oos.trades(None), fs.pip_size, fs.commission or 0.0, "FULL")
    mc = montecarlo_completo(pips, n_sim=20_000)
    check("18. stress_test: Monte Carlo identico a montecarlo_completo sui trade IS + OOS",
          all(r["montecarlo"][k] == mc[k] for k in mc if not k.startswith("_")),
          f"{mc['n_trade']} trade")
    check("19. stress_test: lotti = drawdown accettato / (drawdown al 95° x valore del pip)",
          abs(r["sizing"]["lotti_drawdown"] - 10_000 / (mc["dd_p95"] * 10.0)) < 1e-9)

    print("\nC · Casi particolari")
    muto(v.scegli_trigger, s, long=None, short=SHORT[0])
    check("20. scegliere di nuovo i trigger azzera le schermate successive",
          s.uscite is None and s.fs is None and s.oos is None)
    check("21. schermata saltata -> messaggio che dice quale eseguire",
          errore(lambda: v.trova_strategia(s), RuntimeError)
          and errore(lambda: v.scheda(s), RuntimeError)
          and errore(lambda: v.stress_test(s), RuntimeError))
    t = muto(v.imposta_uscite, s, None, 12, 80, 70)
    check("22. un lato solo: una riga «Solo short», barre non indicate = H",
          list(t["Sistema"]) == ["Solo short"] and s.uscite["n_barre_long"] == H
          and s.uscite["n_barre_short"] == 12)
    check("23. nessun trigger / nome inesistente / lato sbagliato -> errore",
          errore(lambda: v.scegli_trigger(s, long="", short=None), ValueError)
          and errore(lambda: v.scegli_trigger(s, long="E99_NON_ESISTE"), ValueError)
          and errore(lambda: v.scegli_trigger(s, long=SHORT[0]), ValueError))
    check("24. percentile fuori scala / barre a zero -> errore",
          errore(lambda: v.imposta_uscite(s, 10, 10, 120, 0), ValueError)
          and errore(lambda: v.imposta_uscite(s, 0, 10, 90, 0), ValueError))
    muto(v.imposta_uscite, s, None, 12, 80, 70)
    muto(v.trova_strategia, s)
    check("25. filtro inesistente nella scheda -> errore",
          errore(lambda: v.scheda(s, "F99_NON_ESISTE"), ValueError))
    prima = len(s.fs.risultati)
    reg.register_filter("T_FILTRO_NUOVO", 0)(
        lambda d: pd.Series(np.arange(len(d)) % 2 == 0, index=d.index))
    muto(v.trova_strategia, s)
    check("26. un filtro aggiunto al registro viene provato senza toccare la vetrina",
          len(s.fs.risultati) == prima + 1 and "T_FILTRO_NUOVO" in set(s.fs.risultati["filtro"]))
    check("27. le composite in OR non rientrano fra i trigger da esplorare",
          not any(n.startswith("OR(") for n in v._trigger_candidati()))

    print("\nD · Il segno, verificato in modo indipendente (7/10/2026)")
    # Trigger finti costruiti GUARDANDO IL FUTURO (solo qui, per il test): si sa
    # in partenza quale guadagna. Uno short «buono» scatta dove il prezzo poi
    # SCENDE, uno «cattivo» dove poi SALE; lo stesso, a specchio, per i long.
    def finto(verso_prezzo):
        def f(d):
            dopo = d["Close"].shift(-10) / d["Open"].shift(-1) - 1.0
            soglia = dopo.abs().quantile(0.80)
            scelti = (dopo * verso_prezzo > soglia) & (np.arange(len(d)) % 7 == 0)
            return scelti.fillna(False)
        return f
    reg.register_entry("T_SHORT_BUONO", -1)(finto(-1))
    reg.register_entry("T_SHORT_CATTIVO", -1)(finto(+1))
    reg.register_entry("T_LONG_BUONO", 1)(finto(+1))
    reg.register_entry("T_LONG_CATTIVO", 1)(finto(-1))
    s2 = muto(v.prepara, "EURUSD", 12)
    muto(v.esplora, s2)
    cl = muto(v.classifiche, s2, 1000)
    for n, lato in ((28, "short"), (29, "long")):
        t = cl[lato].set_index("Trigger")
        buono, cattivo = f"T_{lato.upper()}_BUONO", f"T_{lato.upper()}_CATTIVO"
        check(f"{n}. {lato}: il trigger che guadagna e' positivo e primo in classifica, quello che perde "
              f"negativo e ultimo",
              t.loc[buono, "Movimento a favore (pips)"] > 0 and t.loc[cattivo, "Movimento a favore (pips)"] < 0
              and t.index[0] == buono and t.index[-1] == cattivo,
              f"{t.loc[buono, 'Movimento a favore (pips)']:+.1f} / {t.loc[cattivo, 'Movimento a favore (pips)']:+.1f} pips")
    check("30. «supera il rumore» distingue a favore da contro",
          cl["short"].set_index("Trigger").loc["T_SHORT_BUONO", "Supera il rumore"] == "sì"
          and cl["short"].set_index("Trigger").loc["T_SHORT_CATTIVO", "Supera il rumore"] == "sì, ma contro")
    # stessa lettura nel backtest: il segno della classifica e quello della
    # schermata 4 devono dire la stessa cosa
    esiti = {}
    for nome in ("T_SHORT_BUONO", "T_SHORT_CATTIVO"):
        muto(v.scegli_trigger, s2, long=None, short=nome)
        t = muto(v.imposta_uscite, s2, None, 10, 0, 0)
        esiti[nome] = float(t.iloc[0]["Guadagno medio netto per trade (pips)"])
    check("31. backtest solo short: lo short «buono» guadagna, il «cattivo» perde (stesso segno della classifica)",
          esiti["T_SHORT_BUONO"] > 0 > esiti["T_SHORT_CATTIVO"],
          f"{esiti['T_SHORT_BUONO']:+.1f} / {esiti['T_SHORT_CATTIVO']:+.1f} pips netti per trade")

    print("\nE · Piu' filtri insieme e l'asticella della prima prova (7/10/2026)")
    from engine.giudizio import soglia_rumore
    muto(v.scegli_trigger, s, long=LONG, short=SHORT)
    muto(v.imposta_uscite, s, BL, BS, SL, TP)
    muto(v.trova_strategia, s)
    n_prove = int((s.fs.risultati["filtro"] != BASELINE).sum())
    check("32. l'asticella mostrata e' la soglia di rumore per il numero di filtri provati",
          abs(s.tabelle["asticella"] - soglia_rumore(n_prove, 0.05)) < 1e-12 and s.tabelle["asticella"] > 1.96,
          f"{n_prove} filtri -> {s.tabelle['asticella']:.2f}")
    tf = s.tabelle["filtri"]
    check("33. chi non passa la prima prova ha scritto il perche'",
          all(x == "—" or x.startswith("promosso") or x.startswith("non passa: ") for x in tf["Prima prova"]),
          str(sorted(set(tf["Prima prova"]))[:3]))

    # due filtri neutri e una coppia long/short, presi dal registro
    ris = s.fs.risultati.set_index("filtro")
    neutri = [f for f in ris.index if f != BASELINE and ris.loc[f, "filtro_long"] == ris.loc[f, "filtro_short"]]
    coppie = [f for f in ris.index if f != BASELINE and ris.loc[f, "filtro_long"] != ris.loc[f, "filtro_short"]
              and "—" not in (ris.loc[f, "filtro_long"], ris.loc[f, "filtro_short"])]
    A, B, C = neutri[0], neutri[1], coppie[0]

    # riferimento INDIPENDENTE: un filtro unico «A e B» registrato a mano e
    # passato al motore come un filtro qualsiasi
    fa, fb = reg.get_filter(A), reg.get_filter(B)
    reg.register_filter("T_A_E_B", 0)(lambda d: fa(d).astype(bool) & fb(d).astype(bool))
    comuni = dict(n_barre=BL, n_barre_long=BL, n_barre_short=BS, perc_sl=SL, perc_tp=TP,
                  inverti_su_opposto=True, verbose=False, **s.costi)
    with contextlib.redirect_stdout(io.StringIO()):
        rif_is = run_filter_search_bt(s.df_is, entry_long=s.entry_long, entry_short=s.entry_short,
                                      filtri=["T_A_E_B"], **comuni).trades("T_A_E_B")
        rif_oos = run_filter_search_bt(s.df_oos, entry_long=s.entry_long, entry_short=s.entry_short,
                                       filtri=["T_A_E_B"], margin=1.0, **comuni).trades("T_A_E_B")
    colonne = ["Size", "EntryBar", "ExitBar", "EntryPrice", "ExitPrice", "PnL"]
    muto(v.scheda, s, f"{A}, {B}")
    ab_is, ab_oos = s.trades_is.copy(), s.trades_oos.copy()
    check("34. due filtri: i trade sono quelli del filtro unico «A e B» (in-sample e out-of-sample)",
          ab_is[colonne].reset_index(drop=True).equals(rif_is[colonne].reset_index(drop=True))
          and ab_oos[colonne].reset_index(drop=True).equals(rif_oos[colonne].reset_index(drop=True)),
          f"{A} + {B}: {len(ab_is)} trade IS, {len(ab_oos)} OOS")
    tp = s.tabelle["passi"]
    check("35. tabella dei passi: base, + A, + B; il primo passo ha i numeri della classifica",
          list(tp["Passo"]) == ["Sistema base", f"+ {A}", f"+ {B}"]
          and int(tp.iloc[1]["Trade"]) == int(ris.loc[A, "trades"])
          and abs(tp.iloc[1]["Solidità del miglioramento"] - ris.loc[A, "t_guadagno"]) < 1e-12
          and int(tp.iloc[2]["Trade"]) == len(ab_is) <= int(tp.iloc[1]["Trade"]),
          f"trade {list(tp['Trade'])}")
    muto(v.scheda, s, [B, A])
    check("36. l'ordine in cui scrivi i filtri non cambia i trade finali",
          s.trades_is[colonne].reset_index(drop=True).equals(ab_is[colonne].reset_index(drop=True))
          and s.trades_oos[colonne].reset_index(drop=True).equals(ab_oos[colonne].reset_index(drop=True)))
    muto(v.scheda, s, f"{A}, {C}, {B}")
    abc_is = s.trades_is.copy()
    muto(v.scheda, s, f"{C}, {B}, {A}, {B}")
    check("37. tre filtri con una coppia long/short, in un altro ordine e con un doppione: stessi trade",
          s.trades_is[colonne].reset_index(drop=True).equals(abc_is[colonne].reset_index(drop=True))
          and len(abc_is) <= len(ab_is) and s.filtri_scelti == [C, B, A] and len(s.tabelle["passi"]) == 4,
          f"{len(abc_is)} trade")
    r = muto(v.stress_test, s, 10_000)
    check("38. lo stress test usa i trade della combinazione",
          r["montecarlo"]["n_trade"] == len(s.trades_is) + len(s.trades_oos))
    muto(v.scheda, s, A)
    check("39. un filtro solo: stessi trade della riga della classifica, nessuna tabella dei passi",
          s.trades_is.equals(s.fs.trades(A)) and "passi" not in s.tabelle and s.filtro == A)
    check("40. un nome sbagliato in mezzo agli altri -> errore che lo nomina",
          errore(lambda: v.scheda(s, f"{A}, F99_NON_ESISTE"), ValueError))
    check("41. le entry con un filtro congelato non rientrano fra i trigger da esplorare",
          any("+" in n for n in reg.list_entries()) and not any("+" in n for n in v._trigger_candidati()))

    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
