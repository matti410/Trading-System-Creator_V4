"""
Suite di validazione di orari e uscite per lato (23/10/2026).

Si lancia da terminale, dalla cartella del progetto:

    python test_orari_uscite.py

Non serve MetaTrader 5 e non serve nessun file di dati: usa un mercato
sintetico aperto 24 ore su 24 (come le crypto) e un perpetual sintetico in
una cartella temporanea. Sezioni:

    A · l'atlante sui trigger scelti fuori catalogo (ORA_LONG_@05:45): misurati,
        nel conto k, confronto con il mercato della cella a qualunque ora,
        «meno di 200» solo quando e' vero
    B · stop, target e regola d'uscita per lato: con un valore solo identici
        al bit, per lato ogni lato come se fosse da solo (ricerca delle
        uscite, ricerca dei filtri, due meta', rischio del money management)
    C · il profilo orario in bp, con i pips accanto; pips identico al bit;
        X_INVERSIONE_TREND sul profilo in bp
    D · la soglia cumulata conta le fasce del profilo con un trigger a orario
    E · l'avviso sulla durata con trigger a orario sui due lati (3b e 4)
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

import condizioni_orarie as co
from engine import registry as reg
from engine.atlante import atlante
from engine.due_meta import due_meta
from engine.exit_search_bt import run_exit_search_bt
from engine.filter_search_bt import run_filter_search_bt
from engine.indicatori import volatilita_durata
from engine.mm_adattatore import tabella_trade
from engine.quarantena import imposta_rollover
from engine.stagionalita import fasce_orarie, profilo_orario, rendimenti_avanti_unita
from test_atlante import H, PIP, Mercato, _deriva_dopo, _indice, _registra_entry

warnings.simplefilter("ignore")


def _muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def _parlato(f, *a, **k):
    """Esegue f e ritorna (risultato, testo stampato)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = f(*a, **k)
    return r, buf.getvalue()


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    imposta_rollover(None)              # mercato 24/7: nessuna quarantena, come gli exchange
    co.imposta_fuso("UTC")
    import engine.exchange as X
    import engine.vetrina as vt

    # =================================================================== A ==
    print("\nA · L'atlante sui trigger scelti fuori catalogo")
    # A1: una deriva messa apposta alle 05:45 (segnale sulla candela delle 05:30) solo in volatilita' alta
    M = Mercato(_indice(giorni=1460), seme=21)
    d0 = M.df()
    n = len(d0)
    ora = co.registra_entry_oraria("ORA_LONG_@05:45")
    segnali = np.flatnonzero(_muto(reg.get_entry(ora), d0).to_numpy())
    segnali = segnali[(segnali > 600) & (segnali < n - 2 * H)]
    # la deriva alza la volatilita' (e la sua mediana): si ripete finche' lo stato delle barre del
    # segnale, letto sul mercato con la deriva, e' lo stesso con cui la deriva e' stata messa
    d = d0
    for _ in range(8):
        vol = volatilita_durata(d).to_numpy()[segnali]
        d = M.df(_deriva_dopo(n, segnali, np.where(vol == 1, 0.0004, 0.0)))
        if np.array_equal(volatilita_durata(d).to_numpy()[segnali], vol):
            break
    stabile = np.array_equal(volatilita_durata(d).to_numpy()[segnali], vol)
    tab = _muto(atlante, d, H, PIP, nomi=[ora], unita="bp", fuso="UTC", qualunque_ora=[ora])
    vt_ = tab[tab["asse"] == "vol_trend"].set_index("cella")
    passa = sorted(vt_.index[vt_["passa"]])
    tab_fascia = _muto(atlante, d, H, PIP, nomi=[ora], unita="bp", fuso="UTC")
    check("1. deriva alle 05:45 solo in volatilità alta, confronto con il mercato della cella a qualunque "
          "ora: sull'asse volatilità × trend passano solo celle a volatilità alta (almeno una), nessuna a "
          "volatilità bassa; con il confronto di sempre (cella e fascia) lo scarto è zero per costruzione "
          "e non passa niente",
          stabile and passa and set(passa) <= {"VOL_ALTA_TREND_CONTRO", "VOL_ALTA_TREND_FAVORE"}
          and not vt_.loc[["VOL_BASSA_TREND_CONTRO", "VOL_BASSA_TREND_FAVORE"], "passa"].any()
          and tab.attrs["qualunque_ora"] == [ora]
          and tab_fascia["scarto_bp"].abs().max() < 1e-9 and not tab_fascia["passa"].any()
          and "qualunque_ora" not in tab_fascia.attrs,
          f"passano {passa}; scarto massimo con la fascia {tab_fascia['scarto_bp'].abs().max():.1e} bp")

    # il Lab su un perpetual sintetico (servono le sezioni A, C, D ed E)
    ML = Mercato(_indice(giorni=400), seme=7)
    ore = ML.idx.hour.to_numpy()
    dl = ML.df(np.where(ore == 10, 0.0003, 0.0))              # un effetto orario messo apposta: le 10 UTC
    dl[["Open", "High", "Low", "Close"]] *= 100.0
    pochi = dl.index[np.random.default_rng(3).choice(np.arange(700, len(dl) - 50), size=50, replace=False)]
    _registra_entry("T_POCHI", 1, pochi)
    orari = pd.date_range(dl.index[0].floor("8h"), dl.index[-1].ceil("8h"), freq="8h")
    fund = X.con_intervalli(pd.DataFrame({"tasso": 0.0001}, index=orari))
    with tempfile.TemporaryDirectory() as tmp:
        X.salva_csv(dl, os.path.join(tmp, "BINANCE_PERP_BTCUSDT_M15.csv"))
        X.salva_funding(fund, X.file_funding("BINANCE_PERP_BTCUSDT", tmp))
        s = _muto(vt.prepara, "BINANCE_PERP_BTCUSDT", H=H, cartella=tmp)
        _muto(vt.esplora, s)
        _, testo_3b = _parlato(vt.scegli_trigger, s, long="ORA_LONG_@05:45, T_POCHI", short="ORA_SHORT_@12:00")
        tl, testo_3c = _parlato(vt.atlante_dei_trigger, s)
        catalogo = vt._trigger_candidati(None)
        senza = _muto(atlante, s.df_is, s.H, s.pip, costi=s.costi, funding=s.funding, nomi=catalogo,
                      unita=s.unita, min_eventi=vt.MIN_TRIGGER, fuso=s.fuso, atr=s.atr)
        righe_ora = tl[tl["candidato"].str.startswith("ORA_")]
        sess = tl[(tl["candidato"] == "ORA_LONG_@05:45") & (tl["asse"] == "sessione")]
        check("2. Lab, schermata 3c: ORA_LONG_@05:45 e ORA_SHORT_@12:00 (fuori catalogo) misurati; k cresce "
              "esattamente delle loro celle misurate; sull'asse delle sessioni una cella sola con occasioni, "
              "le altre grigie («troppo pochi casi»); colonne «a qualunque ora»",
              set(righe_ora["candidato"]) == {"ORA_LONG_@05:45", "ORA_SHORT_@12:00"}
              and tl.attrs["k_misurate"] - senza.attrs["k_misurate"] == int(righe_ora["misurata"].sum())
              and int((sess["eventi"] > 0).sum()) == 1
              and (sess.loc[sess["eventi"] == 0, "motivo"] == "troppo pochi casi").all()
              and any("a qualunque ora" in c for c in s.tabelle["atlante_ORA_LONG_@05:45"].columns),
              f"k {senza.attrs['k_misurate']} -> {tl.attrs['k_misurate']}; sessione con occasioni: "
              f"{list(sess.loc[sess['eventi'] > 0, 'cella'])}")
        check("3. la nota «meno di 200 occasioni» compare solo quando è vera: sì per T_POCHI (50 segnali, una parte nell'out-of-sample), no per "
              "i trigger a orario",
              "T_POCHI: meno di 200 occasioni nell'in-sample (" in testo_3c
              and "ORA_LONG_@05:45: meno di" not in testo_3c and "ORA_SHORT_@12:00: meno di" not in testo_3c,
              [r for r in testo_3c.splitlines() if "meno di" in r][:2])

        # =============================================================== D ==
        print("\nD · La soglia cumulata conta le fasce del profilo")
        k1 = vt._soglia_cumulata_lab(s, np.nan)
        _muto(vt.scegli_trigger, s, long="ORA_LONG_@05:45, T_POCHI", short="ORA_SHORT_@12:00")
        k2 = vt._soglia_cumulata_lab(s, np.nan)
        idx30 = pd.date_range("2024-01-01", periods=48 * 30, freq="30min", tz="UTC")
        check("4. trigger a orario su M15: 96 fasce, contate una volta anche rifacendo la 3b (stesso k); "
              "nella frase; su M30 le fasce sono 48",
              s.prove["fasce"] == 96 and k1["fasce"] == 96 and k2["k"] == k1["k"]
              and "96 fasce del profilo orario" in k1["frase"]
              and vt.n_fasce(fasce_orarie(idx30, "UTC")[1]) == 48,
              f"k {k1['k']}")

        # =============================================================== E ==
        print("\nE · L'avviso sulla durata con trigger a orario sui due lati")
        riga_3b = [r for r in testo_3b.splitlines() if r.startswith("Trigger a orario")]
        riga_100 = vt._durate_orarie(s, 100, 100, "barre impostate")
        check("5. 3b, 05:45 / 12:00 su M15 con H = 8: long e short chiusi dalla scadenza (8 barre); con 100 "
              "barre long al massimo 25 (dalle 05:45 alle 12:00) e short al massimo 71 (dalle 12:00 alle 05:45)",
              len(riga_3b) == 1 and "long 8 barre" in riga_3b[0] and "short 8 barre" in riga_3b[0]
              and "long al massimo 25 barre (dalle 05:45 alle 12:00" in riga_100
              and "short al massimo 71 barre (dalle 12:00 alle 05:45" in riga_100,
              riga_100)
        _, testo_4 = _parlato(vt.imposta_uscite, s, barre_long=10, barre_short=100, sl=(90, 80),
                              tp=0, regola_uscita=("X_ORA_@16:00", "nessuna"))
        riga_4 = [r for r in testo_4.splitlines() if r.startswith("Trigger a orario")]
        check("6. schermata 4 con barre per lato (10 e 100), stop (90, 80) e regola solo long: la riga delle "
              "uscite per lato e l'avviso con le barre impostate (long 10, short al massimo 71)",
              len(riga_4) == 1 and "long 10 barre" in riga_4[0] and "short al massimo 71 barre" in riga_4[0]
              and "long: dopo 10 barre, stop 90° percentile, target spento, regola X_ORA_@16:00" in testo_4
              and "short: dopo 100 barre, stop 80° percentile, target spento, nessuna regola" in testo_4
              and s.uscite["perc_sl"] == (90.0, 80.0) and s.uscite["regola"] == "X_ORA_@16:00 | nessuna",
              riga_4[0] if riga_4 else "nessuna riga")

        # =============================================================== C ==
        print("\nC · Il profilo orario in bp")
        p = _muto(vt.profilo_delle_ore, s)
        p_pips = profilo_orario(s.df_is, s.H, s.pip, fuso=s.fuso)
        fwd_bp = rendimenti_avanti_unita(s.df_is, s.H, "bp", s.pip)
        cod = fasce_orarie(s.df_is.index, s.fuso)[0]
        ok = np.isfinite(fwd_bp)
        glob = fwd_bp[ok].mean()
        a_mano = np.array([fwd_bp[ok & (cod == c)].mean() - glob for c in np.unique(cod[ok])])
        ordine = np.argsort([str(x) for x in p["fascia"]])
        check("7. profilo in bp sul perpetual: scarto in bp = media della fascia meno media di tutte le "
              "barre, rifatta a mano; i pips accanto uguali al profilo in pips",
              p.attrs["unita"] == "bp" and len(p) == 96 and int(p["bh"].sum()) > 0
              and np.allclose(np.sort(p["scarto_bp"].to_numpy()), np.sort(a_mano))
              and np.allclose(p.set_index("fascia")["scarto_pips"].sort_index().to_numpy(),
                              p_pips.set_index("fascia")["scarto_pips"].sort_index().to_numpy())
              and "Long: rispetto a un'ora qualsiasi (pips)" in (s.tabelle.get("profilo", pd.DataFrame(
                  columns=["Long: rispetto a un'ora qualsiasi (pips)"])).columns),
              f"{int(p['bh'].sum())} fasce colorate in bp, {int(p_pips['bh'].sum())} in pips")
        _muto(vt.imposta_uscite, s, regola_uscita="X_INVERSIONE_TREND")
        contro = co.fasce_contro()
        col = p[p["bh"]]
        check("8. X_INVERSIONE_TREND sul perpetual usa il profilo in bp, lo stesso del grafico 2b; sul broker "
              "(pips) il profilo è identico al bit a quello di prima",
              co.profilo_congelato().attrs.get("unita") == "bp" and contro["short"]
              and contro["long"] == list(col.loc[col["scarto_bp"] < 0, "fascia"])
              and contro["short"] == list(col.loc[col["scarto_bp"] > 0, "fascia"])
              and profilo_orario(s.df_is, s.H, s.pip, fuso=s.fuso, unita="pips").equals(p_pips)
              and "unita" not in p_pips.attrs,
              f"chiudono il long {len(contro['long'])} fasce, lo short {len(contro['short'])}")

    # =================================================================== B ==
    print("\nB · Stop, target e regola d'uscita per lato")
    B = Mercato(_indice(giorni=200), seme=5).df()
    rng = np.random.default_rng(9)
    _registra_entry("T_L", 1, B.index[rng.choice(np.arange(600, len(B) - 50), 300, replace=False)])
    _registra_entry("T_S", -1, B.index[rng.choice(np.arange(600, len(B) - 50), 300, replace=False)])
    uscita = co.registra_uscita_oraria("X_ORA_@16:00")
    kw = dict(n_barre=20, commission=0.0, spread=0.0, min_trades=1, verbose=False, inverti_su_opposto=True)

    def trade(es):
        return es.trades(es.risultati["combinazione"].iloc[0])

    def corsa(l, s_, **k):
        return _muto(run_exit_search_bt, B, entry_cols_long=[l], entry_cols_short=[s_], **{**kw, **k})

    uno = corsa("T_L", "T_S", perc_sl=90, perc_tp=80)
    due = corsa("T_L", "T_S", perc_sl=(90, 90), perc_tp=(80, 80))
    misto = corsa("T_L", "T_S", perc_sl=(90, 0), perc_tp=(0, 80))
    lato_l = trade(misto)[trade(misto)["Size"] > 0]
    lato_s = trade(misto)[trade(misto)["Size"] < 0]
    check("9. ricerca delle uscite: (90, 90) / (80, 80) identico al bit a 90 / 80; con stop (90, 0) e target "
          "(0, 80) i long hanno lo stop e non il target, gli short il target e non lo stop; un lato da solo "
          "con la coppia = quel lato da solo con il suo numero",
          trade(uno).equals(trade(due)) and uno.risultati.equals(due.risultati)
          and lato_l["SL"].notna().all() and lato_l["TP"].isna().all()
          and lato_s["SL"].isna().all() and lato_s["TP"].notna().all()
          and trade(corsa("T_L", None, perc_sl=(90, 0))).equals(trade(corsa("T_L", None, perc_sl=90)))
          and trade(corsa(None, "T_S", perc_sl=(90, 0))).equals(trade(corsa(None, "T_S", perc_sl=0))),
          f"{len(lato_l)} long, {len(lato_s)} short")
    per_lato = reg.coppia_per_lato(uscita, None)
    check("10. regola per lato: «X_ORA_@16:00 | nessuna» sul long = X_ORA_@16:00, sullo short = nessuna "
          "regola; la stessa regola sui due lati ritorna la regola di sempre",
          per_lato == "X_ORA_@16:00 | nessuna" and reg.coppia_per_lato(uscita, uscita) == uscita
          and reg.coppia_per_lato("nessuna", None) is None
          and trade(corsa("T_L", None, perc_sl=90, exit_rule_pairs=per_lato)).equals(
              trade(corsa("T_L", None, perc_sl=90, exit_rule_pairs=uscita)))
          and trade(corsa(None, "T_S", perc_sl=90, exit_rule_pairs=per_lato)).equals(
              trade(corsa(None, "T_S", perc_sl=90))))
    fkw = dict(entry_long="T_L", entry_short="T_S", n_barre=20, filtri=[], commission=0.0, spread=0.0,
               verbose=False, inverti_su_opposto=True, min_trades=1)
    fs1 = _muto(run_filter_search_bt, B, perc_sl=90, perc_tp=0, **fkw)
    fs2 = _muto(run_filter_search_bt, B, perc_sl=(90, 90), perc_tp=(0, 0), **fkw)
    dm1 = _muto(due_meta, B, fs1, [None], perc_sl=90, perc_tp=0, commission=0.0, verbose=False)
    dm2 = _muto(due_meta, B, fs2, [None], perc_sl=(90, 90), perc_tp=(0, 0), commission=0.0, verbose=False)
    fsm = _muto(run_filter_search_bt, B, perc_sl=(90, 0), perc_tp=0, **fkw)
    tm = fsm.trades(None)
    tab_m = tabella_trade(tm, B, "BINANCE_PERP_BTCUSDT", PIP, perc_sl=(90, 0), n_barre_long=20,
                          n_barre_short=20, lag=1)
    tab_0 = tabella_trade(tm, B, "BINANCE_PERP_BTCUSDT", PIP, perc_sl=0, n_barre_long=20,
                          n_barre_short=20, lag=1)
    t_ord = tm.sort_values("ExitTime", kind="mergesort")
    vero = (np.abs(t_ord["EntryPrice"] - t_ord["SL"]) / t_ord["EntryPrice"]).to_numpy()
    lungo = tab_m["lato"].to_numpy() > 0
    check("11. ricerca dei filtri e due metà con (90, 90) identiche al bit a 90; rischio del money "
          "management con stop (90, 0): i long dallo stop vero, gli short dallo stop di calcolo",
          fs1.risultati.equals(fs2.risultati) and fs1.trades(None).equals(fs2.trades(None))
          and dm1.tabella.equals(dm2.tabella)
          and np.allclose(tab_m.loc[lungo, "frazione_stop"].to_numpy(), vero[lungo])
          and np.allclose(tab_m.loc[~lungo, "frazione_stop"].to_numpy(), tab_0.loc[~lungo, "frazione_stop"].to_numpy()),
          f"{int(lungo.sum())} long, {int((~lungo).sum())} short")

    reg.clear_registry()
    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
