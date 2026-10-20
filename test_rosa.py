"""
Collaudo di engine/rosa.py (la rosa dei candidati, decisioni di Mattia del
17/10/2026: Benjamini-Hochberg q = 20% sul t netto a una coda, positivo su
entrambe le meta' dell'in-sample, una per famiglia, |rho| <= 0,3 sui profitti
giornalieri).

Sezioni:

    A  Benjamini-Hochberg contro un conteggio a mano (anche il caso «step-up»:
       il primo p sopra la sua soglia passa lo stesso perche' passa il secondo)
    B  rosa_entry su un mercato casuale con vantaggi noti: le entry vere
       entrano, le finte quasi mai; la copia spostata di una barra resta fuori
       per famiglia, la gemella sfasata di 4 barre per correlazione; vincoli
       del gruppo; t netto contro un calcolo a mano; risultato ripetibile
    C  deriva del mercato: su un asset che sale da solo una long a caso ha
       media positiva ma scarto dal mercato nullo, e non e' candidata
    D  rosa_sistemi su trade costruiti a mano: t netto, deriva tolta per le
       barre di permanenza, famiglie «L·S·X», correlazione, sistemi con pochi
       trade contati fra le prove
    E  EURUSD in-sample, catalogo vero: la tabella e' completa, i vincoli
       valgono, l'esito e' ripetibile; rosa_sistemi su una ricerca delle
       uscite vera

Si lancia da terminale, dalla cartella del progetto:

    python test_rosa.py

(su Windows: PYTHONIOENCODING=utf-8). La sezione E gira solo se c'e'
dati/EURUSD_M15.csv; se manca viene SALTATA e lo dice. Non serve MT5.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import warnings
from types import SimpleNamespace

import numpy as np
import pandas as pd

warnings.simplefilter(action="ignore", category=FutureWarning)

from engine import registry as R
from engine.event_study import _errore_standard_sovrapposti
from engine.rosa import benjamini_hochberg, rosa_entry, rosa_sistemi

CARTELLA = os.path.dirname(os.path.abspath(__file__))
DATI = os.path.join(CARTELLA, "dati", "EURUSD_M15.csv")
PIP = 0.0001
H = 10


def _mercato(seme: int, n: int = 60000, deriva_pips: float = 0.0):
    """Prezzi a passeggiata casuale (1 pip di deviazione per barra) e i rendimenti per barra."""
    rng = np.random.default_rng(seme)
    passi = rng.normal(deriva_pips, 1.0, n)
    return rng, passi


def _con_vantaggio(passi: np.ndarray, eventi: np.ndarray, verso: int, delta_pips: float):
    """Aggiunge `delta_pips` in tutto, nel verso del trade, alle H barre dopo ogni evento."""
    p = passi.copy()
    for i in eventi:
        p[i + 2: i + 2 + H] += verso * delta_pips / H     # da Open[i+1] a Close[i+H]
    return p


def _df(passi: np.ndarray, colonne: dict) -> pd.DataFrame:
    n = len(passi)
    idx = pd.date_range("2022-01-03", periods=n, freq="15min", tz="UTC")
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


def _caso_b(seme: int = 7):
    """Mercato casuale con 4 entry vere, una copia, una gemella e 40 finte."""
    rng, passi = _mercato(seme)
    n = len(passi)
    libere = np.arange(50, n - 50)
    blocchi = rng.permutation(libere[:: 2 * H])           # barre distanti: entry vere non sovrapposte
    vere = {"VERA_L1": (1, blocchi[0:600]), "VERA_L2": (1, blocchi[600:1200]),
            "VERA_S1": (-1, blocchi[1200:1800]), "VERA_S2": (-1, blocchi[1800:2400])}
    for nome, (d, ev) in vere.items():
        passi = _con_vantaggio(passi, np.sort(ev), d, 1.5)
    colonne = {k: np.sort(ev) for k, (_, ev) in vere.items()}
    direzioni = {k: d for k, (d, _) in vere.items()}
    colonne["COPIA_L1"] = colonne["VERA_L1"] + 1           # stessa idea, una barra dopo
    direzioni["COPIA_L1"] = 1
    colonne["GEMELLA_S1"] = colonne["VERA_S1"] + 4          # stessi movimenti, fuori dalla finestra
    direzioni["GEMELLA_S1"] = -1
    for j in range(40):
        colonne[f"FINTA_{j:02d}"] = np.sort(rng.choice(libere, 600, replace=False))
        direzioni[f"FINTA_{j:02d}"] = 1 if j % 2 == 0 else -1
    return _df(passi, colonne), direzioni


def _fake_es(sistemi: dict, min_trades: int = 30):
    """Un oggetto con .risultati, .trades() e .min_trades come quello di run_exit_search_bt."""
    righe = [{"combinazione": k, "entry_long": v["L"], "entry_short": v["S"],
              "exit_rule_pair": v["X"]} for k, v in sistemi.items()]
    tr = {k: v["trades"] for k, v in sistemi.items()}
    return SimpleNamespace(risultati=pd.DataFrame(righe), trades=lambda c: tr[c],
                           min_trades=min_trades)


def _trades(df: pd.DataFrame, ingressi: np.ndarray, verso: int, pips: np.ndarray, barre: int):
    ingressi = np.asarray(ingressi)
    entrata = df["Open"].to_numpy()[ingressi]
    return pd.DataFrame({
        "Size": np.full(len(ingressi), verso), "EntryBar": ingressi, "ExitBar": ingressi + barre,
        "EntryPrice": entrata, "ExitPrice": entrata + verso * pips * PIP,
        "EntryTime": df.index[ingressi], "ExitTime": df.index[ingressi + barre]})


def main() -> int:
    ESITI: list[bool] = []

    def check(nome: str, condizione: bool, dettaglio: str = ""):
        ESITI.append(bool(condizione))
        stato = "OK  " if condizione else "FAIL"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def saltato(nome: str, motivo: str):
        print(f"  [SALT] {nome}  — {motivo}")

    # =====================================================================
    print("\nA · BENJAMINI-HOCHBERG A MANO\n" + "-" * 70)
    p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.060, 0.074, 0.205, 0.212, 0.216]
    # soglie q*r/k con q = 0,20 e k = 10: 0,02 0,04 ... 0,20; l'ultimo rango sotto e' il 7°
    check("A1. dieci p, q = 20%: passano i primi 7", benjamini_hochberg(p, 0.20).tolist() == [True] * 7 + [False] * 3)
    # q = 5%: soglie 0,005 0,010 0,015 ...: passano i primi 2
    check("A2. stessi p, q = 5%: passano i primi 2", benjamini_hochberg(p, 0.05).sum() == 2)
    check("A3. step-up: p = (0,04; 0,045) con q = 6% passano entrambi (0,04 > 0,03 ma 0,045 <= 0,06)",
          benjamini_hochberg([0.045, 0.04], 0.06).tolist() == [True, True])
    check("A4. un p non finito conta fra le prove ma non passa; nessun p piccolo = nessuno",
          benjamini_hochberg([0.01, np.nan], 0.015).tolist() == [False, False]
          and benjamini_hochberg([0.01, np.nan], 0.04).tolist() == [True, False]
          and not benjamini_hochberg([0.5, 0.6, 0.9], 0.2).any())

    # =====================================================================
    print("\nB · ROSA DELLE ENTRY, VANTAGGI NOTI\n" + "-" * 70)
    df, direzioni = _caso_b()
    _registra(direzioni)
    r = rosa_entry(df, H, PIP, quarantena=False).set_index("candidato")
    vere = ["VERA_L1", "VERA_L2", "VERA_S1", "VERA_S2"]
    finte = [k for k in r.index if k.startswith("FINTA")]
    check("B1. tutte le entry misurate (46), k nella tabella", len(r) == 46 and r.attrs["k"] == 46)
    # VERA_L1 e la sua copia spostata di una barra portano lo stesso vantaggio: nella rosa ne
    # entra una sola, quella col t piu' alto (B4)
    coppia = r.loc[["VERA_L1", "COPIA_L1"]]
    check("B2. le 4 entry vere sono candidate; VERA_L2, VERA_S1, VERA_S2 e una fra VERA_L1 e la copia nella rosa",
          bool(r.loc[vere, "candidata"].all()) and bool(r.loc[vere[1:], "nella_rosa"].all())
          and int(coppia["nella_rosa"].sum()) == 1,
          ", ".join(f"{k} t={r.loc[k, 't_netto']:.1f}" for k in vere + ["COPIA_L1"]))
    nf = int(r.loc[finte, "candidata"].sum())
    check("B3. le finte candidate sono al massimo 2 su 40", nf <= 2, f"{nf} finte candidate")
    fuori = coppia[~coppia["nella_rosa"]]
    check("B4. fra VERA_L1 e la copia spostata di una barra (stessa famiglia), quella col t piu' basso "
          "e' fuori per famiglia",
          bool(coppia["candidata"].all()) and coppia["famiglia"].nunique() == 1 and len(fuori) == 1
          and "famiglia" in fuori["perche"].iloc[0]
          and fuori["t_netto"].iloc[0] <= coppia["t_netto"].max(),
          f"{fuori.index[0]}: {fuori['perche'].iloc[0]}" if len(fuori) else "")
    check("B5. la gemella sfasata di 4 barre e' di un'altra famiglia ma fuori per correlazione",
          bool(r.loc["GEMELLA_S1", "candidata"]) and not r.loc["GEMELLA_S1", "nella_rosa"]
          and r.loc["GEMELLA_S1", "famiglia"] != r.loc["VERA_S1", "famiglia"]
          and "correlata con VERA_S1" in r.loc["GEMELLA_S1", "perche"], r.loc["GEMELLA_S1", "perche"])
    rosa = r[r["nella_rosa"]]
    check("B6. nella rosa: famiglie tutte diverse e |rho| <= 0,3 con gli altri membri",
          rosa["famiglia"].is_unique and bool((rosa["rho_max"].fillna(0) <= 0.30).all()),
          f"{len(rosa)} membri, rho_max {rosa['rho_max'].max():.2f}")
    check("B7. candidata = t > 0, bh e due meta' (anche per le righe fuori); ogni riga fuori ha un perche'",
          bool((r["candidata"] == ((r["t_netto"] > 0) & r["bh"] & r["due_meta"])).all())
          and bool((r.loc[~r["nella_rosa"], "perche"].str.len() > 0).all())
          and bool((r.loc[r["nella_rosa"], "perche"] == "").all()))
    # t netto di VERA_L1 rifatto a mano, senza passare da rosa_entry
    close, open_ = df["Close"].to_numpy(), df["Open"].to_numpy()
    fwd = np.full(len(df), np.nan)
    fwd[: len(df) - H] = (close[H:] - open_[1: len(df) - H + 1]) / PIP
    pos = np.flatnonzero(df["VERA_L1"].to_numpy())
    pos = pos[np.isfinite(fwd[pos])]
    t_mano = (fwd[pos].mean() - np.nanmean(fwd)) / _errore_standard_sovrapposti(fwd[pos], pos, H)
    # 18/10/2026: il conto a mano e' quello della media di tutte le barre (baseline globale):
    # deve tornare identico sia con baseline="globale" sia nella colonna t_globale
    rg = rosa_entry(df, H, PIP, quarantena=False, baseline="globale").set_index("candidato")
    check("B8. t netto contro il calcolo a mano (baseline globale e colonna t_globale)",
          abs(t_mano - rg.loc["VERA_L1", "t_netto"]) < 1e-9
          and abs(t_mano - r.loc["VERA_L1", "t_globale"]) < 1e-9,
          f"{t_mano:.6f} contro {rg.loc['VERA_L1', 't_netto']:.6f}")
    check("B9. vantaggio aggiunto 1,5 pips: lo scarto stimato delle vere fra 1 e 2 pips",
          bool(r.loc[vere, "scarto_pips"].between(1.0, 2.0).all()),
          ", ".join(f"{r.loc[k, 'scarto_pips']:.2f}" for k in vere))
    r2 = rosa_entry(df, H, PIP, quarantena=False).set_index("candidato")
    check("B10. ripetibile: due esecuzioni danno la stessa tabella", r.equals(r2))
    corta = rosa_entry(df, H, PIP, nomi=["VERA_L1", "FINTA_00"], min_eventi=601, quarantena=False)
    check("B11. sotto min_eventi l'entry non si misura e finisce fra le scartate",
          len(corta) == 0 and dict(corta.attrs["scartate"]) == {"VERA_L1": 600, "FINTA_00": 600})
    try:
        rosa_entry(df, H, None)
        ok = False
    except ValueError:
        ok = True
    check("B12. senza pip si ferma (il pip non si deduce dal prezzo)", ok)

    # =====================================================================
    print("\nC · DERIVA DEL MERCATO\n" + "-" * 70)
    rng, passi = _mercato(11, deriva_pips=0.3)
    ev = np.sort(rng.choice(np.arange(50, len(passi) - 50), 2000, replace=False))
    dfd = _df(passi, {"CASO_L": ev, "CASO_S": ev})
    _registra({"CASO_L": 1, "CASO_S": -1})
    rd = rosa_entry(dfd, H, PIP, quarantena=False, baseline="globale").set_index("candidato")
    grezzo = float(np.nanmean((dfd["Close"].to_numpy()[ev + H] - dfd["Open"].to_numpy()[ev + 1]) / PIP))
    check("C1. long a caso su un asset che sale: media grezza ~ +3 pips, scarto dal mercato ~ 0",
          grezzo > 2.0 and abs(rd.loc["CASO_L", "scarto_pips"]) < 0.5,
          f"grezzo {grezzo:.2f}, scarto {rd.loc['CASO_L', 'scarto_pips']:.2f}")
    check("C2. ne' la long ne' la short a caso sono candidate", not rd["candidata"].any())
    ro = rosa_entry(dfd, H, PIP, quarantena=False).set_index("candidato")
    check("C3. baseline oraria: anche contro la media della stessa ora lo scarto della long a caso ~ 0 "
          "e il t entro +-2", abs(ro.loc["CASO_L", "scarto_pips"]) < 0.5 and abs(ro.loc["CASO_L", "t_netto"]) < 2,
          f"scarto {ro.loc['CASO_L', 'scarto_pips']:.2f}, t {ro.loc['CASO_L', 't_netto']:.2f}")

    # =====================================================================
    print("\nD · ROSA DEI SISTEMI, TRADE COSTRUITI A MANO\n" + "-" * 70)
    rng, passi = _mercato(5, n=40000, deriva_pips=0.2)
    dfs = _df(passi, {"EA": [], "EB": np.arange(100, 40000, 97), "EC": np.arange(140, 40000, 211)})
    R.clear_registry()
    for k in ("EA", "EB", "EC"):
        R.register_entry(k, 1)(lambda df, k=k: df[k])
    ingressi = np.arange(100, 39000, 97)[:380]
    base = rng.normal(2.0, 3.0, len(ingressi))
    deriva = float(np.mean(np.diff(dfs["Open"].to_numpy()))) / PIP
    rumore = rng.normal(0.0, 3.0, len(ingressi))
    rumore -= rumore.mean()                                # S_NULLO: esattamente la sola deriva
    sistemi = {
        "S_BUONO": {"L": "EB", "S": None, "X": None,
                    "trades": _trades(dfs, ingressi, 1, base + 0.2 * 20, 20)},
        "S_SIMILE": {"L": "EC", "S": None, "X": None,
                     "trades": _trades(dfs, ingressi, 1, base + rng.normal(0, 0.5, len(ingressi)) + 4, 20)},
        "S_NULLO": {"L": "EC", "S": None, "X": None,
                    "trades": _trades(dfs, ingressi + 30, 1, deriva * 20 + rumore, 20)},
        "S_CORTO": {"L": "EA", "S": None, "X": None,
                    "trades": _trades(dfs, ingressi[:10], 1, np.full(10, 9.0), 20)},
    }
    rs = rosa_sistemi(_fake_es(sistemi), dfs, PIP).set_index("combinazione")
    rsg = rosa_sistemi(_fake_es(sistemi), dfs, PIP, baseline="globale").set_index("combinazione")
    x = base + 0.2 * 20 - deriva * 20
    t_mano = x.mean() / (x.std(ddof=1) / np.sqrt(x.size))
    check("D1. t netto di S_BUONO: pips netti meno deriva x barre, t classico (baseline globale e t_globale)",
          abs(rsg.loc["S_BUONO", "t_netto"] - t_mano) < 1e-9 and abs(rsg.loc["S_BUONO", "scarto_pips"] - x.mean()) < 1e-9
          and abs(rs.loc["S_BUONO", "t_globale"] - t_mano) < 1e-9,
          f"{t_mano:.4f}")
    check("D2. S_NULLO (solo deriva) non e' candidato; S_BUONO si'",
          not rs.loc["S_NULLO", "candidata"] and bool(rs.loc["S_BUONO", "candidata"]))
    check("D3. S_SIMILE: altra famiglia di entry ma fuori per correlazione con S_BUONO",
          bool(rs.loc["S_SIMILE", "candidata"]) and not rs.loc["S_SIMILE", "nella_rosa"]
          and "correlata con S_BUONO" in rs.loc["S_SIMILE", "perche"], rs.loc["S_SIMILE", "perche"])
    check("D4. S_CORTO (10 trade, sotto min_trades) conta fra le prove con p = 1 e non e' candidato",
          rs.attrs["k"] == 4 and rs.loc["S_CORTO", "p"] == 1.0 and not rs.loc["S_CORTO", "candidata"]
          and rs.loc["S_CORTO", "perche"] == "non misurabile (troppo pochi casi)", rs.loc["S_CORTO", "perche"])
    check("D5. famiglia nella forma L·S·X, lato spento e uscita a tempo = «—»",
          rs.loc["S_BUONO", "famiglia"].startswith("L") and rs.loc["S_BUONO", "famiglia"].endswith("·S—·X—"),
          rs.loc["S_BUONO", "famiglia"])

    # =====================================================================
    print("\nE · EURUSD IN-SAMPLE, CATALOGO VERO\n" + "-" * 70)
    if not os.path.exists(DATI):
        saltato("E1-E5", f"manca {DATI}")
    else:
        import entry_long
        import entry_short
        from engine.exit_search_bt import run_exit_search_bt
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
        re_ = rosa_entry(df_is, 25, pip)
        attese = ["candidato", "direction", "eventi", "scarto_pips", "t_netto", "p", "bh",
                  "due_meta", "candidata", "famiglia", "nella_rosa", "rho_max", "perche",
                  "scarto_globale_pips", "t_globale"]
        # 20/10/2026 (docs/63 §4, U1): bp e ATR in coda, colonne di prima invariate
        attese += [f"{c}_{u}" for u in ("bp", "atr") for c in ("scarto", "t", "due_meta")]
        check("E1. tabella completa: colonne (bp e ATR in coda), una riga per entry misurata, nessuna metro",
              list(re_.columns) == attese and re_["candidato"].is_unique
              and not re_["candidato"].str.startswith("M_").any() and len(re_) >= 40,
              f"{len(re_)} entry, {int(re_['candidata'].sum())} candidate, {int(re_['nella_rosa'].sum())} nella rosa")
        rr = re_[re_["nella_rosa"]]
        check("E2. vincoli del gruppo (famiglie diverse, |rho| <= 0,3) e candidata coerente",
              rr["famiglia"].is_unique and bool((rr["rho_max"].fillna(0) <= 0.30).all())
              and bool((re_["candidata"] == ((re_["t_netto"] > 0) & re_["bh"] & re_["due_meta"])).all()))
        check("E3. ripetibile", re_.equals(rosa_entry(df_is, 25, pip)))
        with contextlib.redirect_stdout(io.StringIO()):
            es = run_exit_search_bt(df_is, entry_cols_long=["E1_RSI_CROSS_OVERSOLD", None],
                                    entry_cols_short=["E4_SHORT_EMA_CROSS_DOWN", None],
                                    n_barre=25, perc_sl=90.0, perc_tp=0.0, spread=0.00008,
                                    commission=0.0, cash=10_000_000, pip_size=pip, verbose=False)
        rsv = rosa_sistemi(es, df_is, pip)
        check("E4. rosa_sistemi su una ricerca vera: una riga per combinazione, famiglie L·S·X",
              len(rsv) == len(es.risultati) and set(rsv["combinazione"]) == set(es.risultati["combinazione"])
              and rsv["famiglia"].str.match(r"^L(\d+|—)·S(\d+|—)·X—$").all(),
              ", ".join(rsv["famiglia"]))
        riga = es.risultati.iloc[0]
        tr = es.trades(riga["combinazione"])
        segno = np.where(tr["Size"] > 0, 1, -1)
        netti = (tr["ExitPrice"] - tr["EntryPrice"]).to_numpy() / pip * segno - (tr["CostoExtraPips"].fillna(0).to_numpy() if "CostoExtraPips" in tr else 0.0)
        deriva = float(np.mean(np.diff(df_is["Open"].to_numpy()))) / pip
        xx = netti - segno * deriva * (tr["ExitBar"] - tr["EntryBar"]).to_numpy()
        t_es = rsv.set_index("combinazione").loc[riga["combinazione"], "t_globale"]
        check("E5. t netto (colonna t_globale) di una combinazione vera contro il calcolo a mano",
              abs(xx.mean() / (xx.std(ddof=1) / np.sqrt(xx.size)) - t_es) < 1e-9, f"t = {t_es:.3f}")
        R.clear_registry()

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(main())
