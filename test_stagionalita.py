"""
Collaudo di engine/stagionalita.py e della baseline oraria (18/10/2026).

    A  le fasce: ora locale con l'ora legale, larghezza dal timeframe
       (M5, M15, H1, H4), fuso per symbol, indice senza fuso = errore
    B  il profilo su un mercato finto con un effetto noto alle 15:00 di
       Londra (+3 pips in un'ora): la fascia piazzata si vede, le fasce
       lontane dall'effetto restano nella quota attesa di falsi positivi
    C  la rosa delle entry: un trigger che scatta solo a quell'ora, senza
       vantaggio proprio, e' forte contro la media di tutte le barre e nullo
       contro la media della stessa ora; un trigger con vantaggio vero a ore
       casuali da' lo stesso scarto con le due baseline; entry finte a ore
       casuali: falsi allarmi nella quota attesa
    D  la rosa dei sistemi: trade aperti solo nell'ora dell'effetto
    E  l'event study: colonna vs_mercato_orario_pct solo con fuso
    F  EURUSD vero: profilo, rosa oraria, identita' della colonna t_globale

Esecuzione:  python test_stagionalita.py   (su Windows: PYTHONIOENCODING=utf-8)
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd

CARTELLA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CARTELLA)

from engine import registry as R                                    # noqa: E402
from engine.event_study import run_event_study                      # noqa: E402
from engine.rosa import rosa_entry, rosa_sistemi                    # noqa: E402
from engine.stagionalita import (fasce_orarie, fuso_profilo,        # noqa: E402
                                 profilo_orario)

DATI = os.path.join(CARTELLA, "dati", "EURUSD_M15.csv")
PIP = 0.0001
H = 10
LONDRA = "Europe/London"
EFFETTO = 3.0          # pips in piu', spalmati sulle 4 barre fra le 15:00 e le 16:00 di Londra


def _mercato_orario(seme: int, n: int = 60000, freq: str = "15min", effetto: float = EFFETTO):
    """Passeggiata casuale (1 pip per barra) con +effetto pips ogni giorno fra 15:00 e 16:00 di Londra."""
    rng = np.random.default_rng(seme)
    idx = pd.date_range("2022-01-03", periods=n, freq=freq, tz="UTC")
    passi = rng.normal(0.0, 1.0, n)
    loc = idx.tz_convert(LONDRA)
    ora = np.asarray(loc.hour)
    passi[ora == 15] += effetto / 4.0
    return rng, idx, passi


def _df(idx, passi, colonne: dict) -> pd.DataFrame:
    n = len(passi)
    close = 1.1 + np.cumsum(passi) * PIP
    open_ = np.r_[1.1, close[:-1]]
    df = pd.DataFrame({"Open": open_, "High": np.maximum(open_, close),
                       "Low": np.minimum(open_, close), "Close": close}, index=idx)
    for k, v in colonne.items():
        m = np.zeros(n, dtype=bool)
        m[v] = True
        df[k] = m
    return df


def _registra(direzioni: dict):
    R.clear_registry()
    for k, d in direzioni.items():
        R.register_entry(k, d)(lambda df, k=k: df[k])


def main() -> int:
    ESITI: list[bool] = []

    def check(nome: str, condizione: bool, dettaglio: str = ""):
        ESITI.append(bool(condizione))
        stato = "OK  " if condizione else "FAIL"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def saltato(nome: str, motivo: str):
        print(f"  [SALT] {nome}  — {motivo}")

    # =====================================================================
    print("\nA · LE FASCE\n" + "-" * 70)
    inverno = pd.DatetimeIndex(["2024-01-15 13:00", "2024-01-15 13:15"], tz="UTC")
    estate = pd.DatetimeIndex(["2024-07-15 13:00", "2024-07-15 13:15"], tz="UTC")
    ci, li = fasce_orarie(inverno, "America/New_York")
    ce, _ = fasce_orarie(estate, "America/New_York")
    check("A1. M15: 13:00 UTC = 08:00 a New York d'inverno, 09:00 d'estate (fascia larga 15 minuti)",
          li == 15 and ci[0] == 8 * 4 and ce[0] == 9 * 4, f"{ci[0]}, {ce[0]}")
    larghezze = {}
    for freq, attese in (("5min", 288), ("15min", 96), ("30min", 48), ("1h", 24), ("4h", 6)):
        idx = pd.date_range("2024-01-01", periods=3000, freq=freq, tz="UTC")
        c, l = fasce_orarie(idx, "UTC")
        larghezze[freq] = (l, len(np.unique(c)))
    check("A2. la fascia e' larga una barra: M5 288 fasce, M15 96, M30 48, H1 24, H4 6",
          [v[1] for v in larghezze.values()] == [288, 96, 48, 24, 6], str(larghezze))
    check("A3. fuso per symbol: DE40 Francoforte, gli altri New York",
          fuso_profilo("DE40") == "Europe/Berlin" and fuso_profilo("EURUSD") == "America/New_York"
          and fuso_profilo("BTCUSD") == "America/New_York")
    try:
        fasce_orarie(pd.DatetimeIndex(["2024-01-15 13:00", "2024-01-15 13:15"]), "UTC")
        ok = False
    except ValueError:
        ok = True
    check("A4. un indice senza fuso si ferma con errore", ok)

    # =====================================================================
    print("\nB · IL PROFILO, EFFETTO NOTO ALLE 15:00 DI LONDRA\n" + "-" * 70)
    rng, idx, passi = _mercato_orario(3)
    df = _df(idx, passi, {})
    with contextlib.redirect_stdout(io.StringIO()):
        prof = profilo_orario(df, H, PIP, fuso=LONDRA, quarantena=False).set_index("fascia")
    check("B1. una riga per fascia (96), attributi del profilo",
          len(prof) == 96 and prof.attrs["k"] == 96 and prof.attrs["larghezza_min"] == 15
          and prof.attrs["fuso"] == LONDRA)
    # la fascia e' l'ora in cui si apre il trade (19/10/2026): aprendo fra le 14:00 e le 15:00
    # le H = 10 barre contengono tutta l'ora 15
    piene = ["14:00", "14:15", "14:30", "14:45", "15:00"]
    check("B2. le fasce che vedono tutta l'ora dell'effetto: scarto ~ +3 pips, passano il controllo",
          bool(prof.loc[piene, "bh"].all()) and bool(prof.loc[piene, "scarto_pips"].between(2.0, 4.0).all()),
          ", ".join(f"{f} {prof.loc[f, 'scarto_pips']:+.2f}" for f in piene))
    # fasce che non toccano l'ora 15 (ne' da dentro ne' da dopo): 00:00-11:00 e 17:00-23:45
    lontane = [f for f in prof.index if (int(f[:2]) < 11 or int(f[:2]) >= 17) and f != "11:00"]
    # l'effetto alza anche la media di tutte le barre (~ 3 * H / 96 pips): le fasce lontane sono
    # davvero sotto la media generale di quel tanto, ma la loro media assoluta resta ~ 0
    ml = prof.loc[lontane, "media_pips"]
    alzata = EFFETTO * H / 96
    check("B3. le fasce lontane dall'effetto: media ~ 0 e scarto ~ meno l'alzata della media generale",
          abs(float(ml.mean())) < 0.15
          and abs(float(prof.loc[lontane, "scarto_pips"].mean()) + alzata) < 0.15,
          f"media {ml.mean():+.2f}, scarto {prof.loc[lontane, 'scarto_pips'].mean():+.2f} (atteso {-alzata:+.2f})")
    tl = prof.loc[lontane, "t"].to_numpy()
    check("B4. le fasce lontane hanno t compatibili col caso (deviazione standard dei t fra 0,6 e 1,6)",
          0.6 < float(np.std(tl)) < 1.6, f"{np.std(tl):.2f}")
    with contextlib.redirect_stdout(io.StringIO()):
        idx1 = pd.date_range("2022-01-03", periods=20000, freq="1h", tz="UTC")
        p1 = np.random.default_rng(4).normal(0, 2, 20000)
        p1[np.asarray(idx1.tz_convert(LONDRA).hour) == 15] += EFFETTO
        prof1 = profilo_orario(_df(idx1, p1, {}), 3, PIP, fuso=LONDRA, quarantena=False).set_index("fascia")
    check("B5. H1: 24 fasce, l'effetto si vede aprendo il trade alle 14:00 e alle 15:00",
          len(prof1) == 24 and bool(prof1.loc[["14:00", "15:00"], "bh"].all()),
          ", ".join(f"{f} {prof1.loc[f, 'scarto_pips']:+.2f}" for f in ["13:00", "14:00", "15:00", "16:00"]))
    check("B6. le fasce sono in ordine d'orario e la prima e' 00:00 (M15)",
          list(prof.index) == sorted(prof.index) and prof.index[0] == "00:00")

    # =====================================================================
    print("\nC · ROSA DELLE ENTRY, BASELINE ORARIA\n" + "-" * 70)
    loc = idx.tz_convert(LONDRA)
    alle_14 = np.flatnonzero((np.asarray(loc.hour) == 14) & (np.asarray(loc.minute) == 0))
    alle_14 = alle_14[(alle_14 > 50) & (alle_14 < len(idx) - 50)]
    # entry vera: +1,5 pips a ore casuali, barre distanti (come test_rosa)
    libere = np.arange(50, len(idx) - 50)
    vere = np.sort(rng.permutation(libere[:: 2 * H])[:800])
    passi_v = passi.copy()
    for i in vere:
        passi_v[i + 2: i + 2 + H] += 1.5 / H
    colonne = {"ORA_L": alle_14, "VERA_L": vere}
    direzioni = {"ORA_L": 1, "VERA_L": 1}
    for j in range(60):
        colonne[f"FINTA_{j:02d}"] = np.sort(rng.choice(libere, 600, replace=False))
        direzioni[f"FINTA_{j:02d}"] = 1 if j % 2 == 0 else -1
    dfc = _df(idx, passi_v, colonne)
    _registra(direzioni)
    with contextlib.redirect_stdout(io.StringIO()):
        ro = rosa_entry(dfc, H, PIP, quarantena=False, fuso=LONDRA).set_index("candidato")
        rg = rosa_entry(dfc, H, PIP, quarantena=False, baseline="globale").set_index("candidato")
    check("C1. trigger alle 14:00 di Londra senza vantaggio proprio: forte con la baseline globale",
          rg.loc["ORA_L", "scarto_pips"] > 2.0 and bool(rg.loc["ORA_L", "candidata"]),
          f"scarto {rg.loc['ORA_L', 'scarto_pips']:+.2f}, t {rg.loc['ORA_L', 't_netto']:.1f}")
    check("C2. ... e nullo con la baseline oraria (scarto ~ 0, non candidato)",
          abs(ro.loc["ORA_L", "scarto_pips"]) < 0.5 and not ro.loc["ORA_L", "candidata"],
          f"scarto {ro.loc['ORA_L', 'scarto_pips']:+.2f}, t {ro.loc['ORA_L', 't_netto']:.2f}")
    check("C3. la colonna t_globale della rosa oraria e' il t della rosa globale",
          bool(np.allclose(ro["t_globale"], rg.loc[ro.index, "t_netto"], equal_nan=True))
          and bool(np.allclose(ro["scarto_globale_pips"], rg.loc[ro.index, "scarto_pips"], equal_nan=True)))
    check("C4. entry con vantaggio vero (+1,5 pips) a ore casuali: stesso scarto con le due baseline, candidata",
          abs(ro.loc["VERA_L", "scarto_pips"] - rg.loc["VERA_L", "scarto_pips"]) < 0.3
          and bool(ro.loc["VERA_L", "candidata"]),
          f"oraria {ro.loc['VERA_L', 'scarto_pips']:+.2f}, globale {rg.loc['VERA_L', 'scarto_pips']:+.2f}")
    finte = [k for k in ro.index if k.startswith("FINTA")]
    tf = ro.loc[finte, "t_netto"].to_numpy()
    allarmi = int((np.abs(tf) > 1.96).sum())
    check("C5. 60 entry finte a ore casuali: |t| > 1,96 al massimo 8 volte (attese 3) e t con deviazione "
          "standard fra 0,7 e 1,3", allarmi <= 8 and 0.7 < float(np.std(tf)) < 1.3,
          f"{allarmi} allarmi, dev. std {np.std(tf):.2f}")
    check("C6. attributi: baseline e fuso", ro.attrs["baseline"] == "oraria" and ro.attrs["fuso"] == LONDRA
          and rg.attrs["baseline"] == "globale" and "t_globale" not in rg.columns)
    try:
        rosa_entry(dfc, H, PIP, nomi=["VERA_L"], baseline="per_giorno")
        ok = False
    except ValueError:
        ok = True
    check("C7. una baseline sconosciuta si ferma con errore", ok)

    # =====================================================================
    print("\nD · ROSA DEI SISTEMI, TRADE NELL'ORA DELL'EFFETTO\n" + "-" * 70)
    alle_15 = np.flatnonzero((np.asarray(loc.hour) == 15) & (np.asarray(loc.minute) == 0))
    alle_15 = alle_15[(alle_15 > 50) & (alle_15 < len(idx) - 50)]
    caso = np.sort(rng.choice(libere[::8], len(alle_15), replace=False))

    def trades(ingressi, barre):
        o = df["Open"].to_numpy()
        return pd.DataFrame({"Size": 1, "EntryBar": ingressi, "ExitBar": ingressi + barre,
                             "EntryPrice": o[ingressi], "ExitPrice": o[ingressi + barre],
                             "EntryTime": df.index[ingressi], "ExitTime": df.index[ingressi + barre]})
    R.clear_registry()
    for k in ("EA", "EB"):
        R.register_entry(k, 1)(lambda d_, k=k: pd.Series(False, index=d_.index))
    sistemi = {"S_ORA": ("EA", trades(alle_15, 4)), "S_CASO": ("EB", trades(caso, 4))}
    es = SimpleNamespace(
        risultati=pd.DataFrame([{"combinazione": k, "entry_long": v[0], "entry_short": None,
                                 "exit_rule_pair": None} for k, v in sistemi.items()]),
        trades=lambda c: sistemi[c][1], min_trades=30)
    with contextlib.redirect_stdout(io.StringIO()):
        so = rosa_sistemi(es, df, PIP, fuso=LONDRA).set_index("combinazione")
    check("D1. trade aperti solo fra 15:00 e 16:00 di Londra: scarto globale ~ +3 pips, orario ~ 0",
          so.loc["S_ORA", "scarto_globale_pips"] > 2.0 and abs(so.loc["S_ORA", "scarto_pips"]) < 0.5
          and not so.loc["S_ORA", "candidata"],
          f"globale {so.loc['S_ORA', 'scarto_globale_pips']:+.2f}, oraria {so.loc['S_ORA', 'scarto_pips']:+.2f}")
    check("D2. trade a ore casuali: le due baseline danno lo stesso scarto a meno di 0,5 pips",
          abs(so.loc["S_CASO", "scarto_pips"] - so.loc["S_CASO", "scarto_globale_pips"]) < 0.5,
          f"{so.loc['S_CASO', 'scarto_pips']:+.2f} contro {so.loc['S_CASO', 'scarto_globale_pips']:+.2f}")

    # =====================================================================
    print("\nE · EVENT STUDY, IL MERCATO DELLA STESSA ORA\n" + "-" * 70)
    _registra({"ORA_L": 1, "VERA_L": 1})
    with contextlib.redirect_stdout(io.StringIO()):
        e0 = run_event_study(dfc, ["ORA_L", "VERA_L"], horizon=H, pip=PIP, quarantena=False, verbose=False)
        e1 = run_event_study(dfc, ["ORA_L", "VERA_L"], horizon=H, pip=PIP, quarantena=False, verbose=False,
                             fuso=LONDRA)
    s1 = e1.sintesi.set_index("candidato")
    check("E1. senza fuso la sintesi e' quella di prima; con fuso ha una colonna in piu', il resto identico",
          "vs_mercato_orario_pct" not in e0.sintesi.columns
          and e1.sintesi.drop(columns="vs_mercato_orario_pct").equals(e0.sintesi))
    pp = e1.pips_per_pct
    check("E2. trigger alle 14:00: vs_mercato_orario ~ 0, vs_mercato > 2 pips",
          abs(s1.loc["ORA_L", "vs_mercato_orario_pct"] * pp) < 0.6 and s1.loc["ORA_L", "vs_mercato_pct"] * pp > 2.0,
          f"orario {s1.loc['ORA_L', 'vs_mercato_orario_pct'] * pp:+.2f}, globale {s1.loc['ORA_L', 'vs_mercato_pct'] * pp:+.2f} pips")
    R.clear_registry()

    # =====================================================================
    print("\nF · EURUSD IN-SAMPLE\n" + "-" * 70)
    if not os.path.exists(DATI):
        saltato("F1-F3", f"manca {DATI}")
    else:
        import entry_long
        import entry_short
        from engine.indicatori import aggiungi_indicatori
        from engine.simboli import pip_symbol
        from engine.splitting import split_is_oos
        from test_algoxplorer import _leggi
        with contextlib.redirect_stdout(io.StringIO()):
            R.clear_registry()
            entry_long.registra_trigger_long()
            entry_short.registra_trigger_short()
            df_is, _ = split_is_oos(aggiungi_indicatori(_leggi("EURUSD")), 0.8)
        pip = pip_symbol("EURUSD")
        fuso = fuso_profilo("EURUSD")
        pr = profilo_orario(df_is, 25, pip, fuso=fuso)
        check("F1. profilo EURUSD: fino a 96 fasce (quelle del rollover sono in quarantena), barre in totale "
              "come l'in-sample misurabile",
              88 <= len(pr) <= 96 and pr["barre"].sum() <= len(df_is) and pr["barre"].sum() > 0.9 * len(df_is),
              f"{len(pr)} fasce, {int(pr['bh'].sum())} oltre la quota di falsi positivi, "
              f"scarto da {pr['scarto_pips'].min():+.2f} a {pr['scarto_pips'].max():+.2f} pips")
        ro = rosa_entry(df_is, 25, pip, fuso=fuso)
        rg = rosa_entry(df_is, 25, pip, baseline="globale").set_index("candidato")
        check("F2. rosa oraria: la colonna t_globale coincide con la rosa globale (identita')",
              bool(np.allclose(ro.set_index("candidato")["t_globale"], rg.loc[ro["candidato"], "t_netto"],
                               equal_nan=True)))
        d = (ro.set_index("candidato")["scarto_pips"] - ro.set_index("candidato")["scarto_globale_pips"]).abs()
        check("F3. rosa oraria: lo scarto cambia di poco per la maggior parte delle entry (mediana < 1 pip)",
              float(d.median()) < 1.0, f"mediana {d.median():.2f}, massimo {d.max():.2f} pips")
        R.clear_registry()

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(main())
