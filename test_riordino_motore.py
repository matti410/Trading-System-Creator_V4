"""
Suite del riordino della pipeline, parte motore (25/10/2026, docs/68 §11.1,
PR A). Casi a risultato noto per le aggiunte all'engine:

    A · curva_scarto_orario (docs/68 §2.1): su un mercato costruito apposta la
        curva e' quella attesa barra per barra (pips e bp); un trigger a orario
        contro la stessa ora da' zero, contro qualunque ora la curva della sua
        fascia meno il mercato; a k = H coincide con lo scarto della rosa
    B · picco_curva (docs/68 §5.1): picco a meta', in coda, nelle prime barre,
        curva mai sopra lo zero; e' solo da leggere
    C · soglia_rumore_orizzonte(punti=) e prove equivalenti (docs/68 §9.1, §13):
        un punto = soglia_rumore; senza punti identica alla versione di prima;
        4 orizzonti = 2,44 come la simulazione del §13; prove_equivalenti e'
        l'inversa di soglia_rumore
    D · il registro per dataset (docs/68 §9.1): stesso dataset con H diverso
        riprende conto e diario e segnala la risalita; stesso H non conta;
        dataset diverso riparte da zero
    E · registra_inversione_trend(profilo=): con il profilo gia' calcolato le
        stesse uscite; un profilo con altri H, fuso o unita' si ferma
    F · trigger a orario: uscita X_ORA_@ a «ingresso + H barre» e uscita a H
        barre danno gli stessi trade (docs/68 §5.2)
    G · BINANCE_PERP_BTCUSDT in-sample, catalogo vero: la curva a k = H
        coincide con lo scarto della rosa per ogni trigger (salta se il CSV
        non c'e')

Si lancia da terminale, dalla cartella del progetto:

    python test_riordino_motore.py

(su Windows: PYTHONIOENCODING=utf-8). Non serve MT5.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import warnings

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")

import condizioni_orarie as co
from engine import registro_dataset as rd
from engine import registry as reg
from engine.exit_search_bt import run_exit_search_bt
from engine.giudizio import (_CACHE_ORIZZONTE, prove_equivalenti, prove_trigger_orizzonti,
                             soglia_rumore, soglia_rumore_orizzonte)
from engine.quarantena import imposta_rollover
from engine.rosa import rosa_entry
from engine.stagionalita import curva_scarto_orario, picco_curva, profilo_orario

CARTELLA = os.path.dirname(os.path.abspath(__file__))
PIP = 0.01
H = 8
DELTA = 2.0          # pips in piu' per barra dopo un trigger (giorni pari)


def _muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def _mercato_noto(giorni=120, ora_segnale="10:00"):
    """
    Prezzo piatto a 100. Nei giorni pari, dopo la barra delle `ora_segnale`, il
    prezzo sale di DELTA pips a barra per H barre e poi torna a 100. Un trigger
    sui giorni pari a quell'ora ha rendimento a k barre = DELTA * k; la sua
    fascia, contando tutti i giorni, DELTA * k / 2: lo scarto dalla stessa ora
    e' DELTA * k / 2 a ogni barra (esatto, anche in bp: ingresso sempre a 100).
    """
    idx = pd.date_range("2023-01-02", periods=giorni * 96, freq="15min", tz="UTC")
    close = np.full(len(idx), 100.0)
    segnali = np.flatnonzero(idx.strftime("%H:%M") == ora_segnale)
    pari = segnali[::2]
    for t in pari:
        close[t + 1: t + 1 + H] = 100.0 + DELTA * PIP * np.arange(1, H + 1)
    op = np.r_[100.0, close[:-1]]
    df = pd.DataFrame({"Open": op, "High": np.maximum(op, close), "Low": np.minimum(op, close),
                       "Close": close, "Volume": 1.0}, index=idx)
    return df, pari, segnali


def _vecchia_soglia_orizzonte(k, horizon, alpha=0.05, n_sim=200_000, seme=0):
    """La soglia_rumore_orizzonte di prima del 25/10/2026, copiata, per la prova d'identita'."""
    k = max(1, int(k))
    rng = np.random.default_rng(seme)
    radici = np.sqrt(np.arange(1, horizon + 1))
    blocco = max(1, 2_000_000 // horizon)
    massimi, rimasti = [], int(n_sim)
    while rimasti > 0:
        m = min(blocco, rimasti)
        z = np.cumsum(rng.standard_normal((m, horizon)), axis=1) / radici
        massimi.append(np.abs(z).max(axis=1))
        rimasti -= m
    return float(np.quantile(np.sort(np.concatenate(massimi)), (1.0 - alpha) ** (1.0 / k)))


def esegui() -> int:
    ESITI: list[bool] = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        print(f"  [{'OK  ' if condizione else 'FAIL'}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def errore(f, testo):
        try:
            f()
        except ValueError as e:
            return testo in str(e)
        return False

    imposta_rollover(None)              # mercato 24/7: nessuna quarantena, come gli exchange
    co.imposta_fuso("UTC")

    # =====================================================================
    print("\nA · LA CURVA DELLO SCARTO, BARRA PER BARRA\n" + "-" * 70)
    df, pari, segnali = _mercato_noto()
    reg.clear_registry()
    tempi = df.index[pari]
    reg.register_entry("T_LONG", 1)(lambda d: pd.Series(d.index.isin(tempi), index=d.index))
    reg.register_entry("T_SHORT", -1)(lambda d: pd.Series(d.index.isin(tempi), index=d.index))
    atteso = DELTA * np.arange(1, H + 1) / 2
    for u in ("pips", "bp"):
        c = curva_scarto_orario(df, ["T_LONG", "T_SHORT"], H, PIP, fuso="UTC", unita=u)
        check(f"A1. {u}: long = DELTA·k/2 a ogni barra, short = −DELTA·k/2",
              np.allclose(c["T_LONG"].to_numpy(), atteso, atol=1e-9)
              and np.allclose(c["T_SHORT"].to_numpy(), -atteso, atol=1e-9),
              " ".join(f"{v:.2f}" for v in c["T_LONG"]))
    check("A2. indice 1..H, eventi = i giorni pari (meno l'ultimo se non misurabile), attrs",
          list(c.index) == list(range(1, H + 1)) and c.attrs["eventi"]["T_LONG"] == len(pari)
          and c.attrs["H"] == H and c.attrs["unita"] == "bp")
    ora = co.registra_entry_oraria("ORA_LONG_@10:15")            # segnale sulla barra delle 10:00
    c_stessa = curva_scarto_orario(df, [ora], H, PIP, fuso="UTC", unita="pips")
    c_qualunque = curva_scarto_orario(df, [ora], H, PIP, fuso="UTC", unita="pips", qualunque_ora=[ora])
    # a mano: media dei rendimenti a k barre nella fascia meno la media di tutte le barre
    a_mano = []
    close, op = df["Close"].to_numpy(), df["Open"].to_numpy()
    for k in range(1, H + 1):
        f = np.full(len(df), np.nan)
        f[: len(df) - k] = (close[k:] - op[1: len(df) - k + 1]) / PIP
        a_mano.append(np.nanmean(f[segnali]) - np.nanmean(f))
    check("A3. trigger a orario contro la stessa ora: zero a ogni barra",
          np.allclose(c_stessa[ora].to_numpy(), 0.0, atol=1e-9))
    check("A4. trigger a orario contro qualunque ora: la curva della sua fascia meno il mercato (a mano)",
          np.allclose(c_qualunque[ora].to_numpy(), a_mano, atol=1e-9)
          and c_qualunque.attrs["qualunque_ora"] == [ora],
          " ".join(f"{v:.3f}" for v in a_mano))
    # su un mercato casuale: a k = H coincide con lo scarto della rosa (stessa ora e qualunque ora)
    rng = np.random.default_rng(3)
    n = 40 * 96
    idx = pd.date_range("2023-01-02", periods=n, freq="15min", tz="UTC")
    close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    op = np.r_[100.0, close[:-1]]
    dfc = pd.DataFrame({"Open": op, "High": np.maximum(op, close) * 1.001,
                        "Low": np.minimum(op, close) * 0.999, "Close": close, "Volume": 1.0}, index=idx)
    reg.clear_registry()
    nomi = []
    for j in range(6):
        m = rng.random(n) < 0.03
        nome = f"R_{j}"
        reg.register_entry(nome, 1 if j % 2 == 0 else -1)(lambda d, m=m: pd.Series(m[:len(d)], index=d.index))
        nomi.append(nome)
    for u in ("pips", "bp"):
        r = _muto(rosa_entry, dfc, H, PIP, nomi=nomi, min_eventi=2, fuso="UTC", unita=u).set_index("candidato")
        c = curva_scarto_orario(dfc, nomi, H, PIP, fuso="UTC", unita=u)
        cg = curva_scarto_orario(dfc, nomi, H, PIP, fuso="UTC", unita=u, qualunque_ora=nomi)
        diff = max(abs(c.loc[H, x] - r.loc[x, f"scarto_{u}"]) for x in nomi)
        diffg = max(abs(cg.loc[H, x] - r.loc[x, f"scarto_globale_{u}"]) for x in nomi)
        check(f"A5. {u}: a k = H la curva coincide con la rosa (stessa ora e qualunque ora), 6 trigger",
              diff < 1e-9 and diffg < 1e-9, f"differenza massima {max(diff, diffg):.1e}")
    check("A6. H < 1 e unita' sconosciuta si fermano",
          errore(lambda: curva_scarto_orario(dfc, nomi, 0, PIP), "H deve")
          and errore(lambda: curva_scarto_orario(dfc, nomi, H, PIP, unita="euro"), "sconosciuta"))

    # =====================================================================
    print("\nB · IL PICCO, SOLO DA LEGGERE\n" + "-" * 70)
    Hb = 20
    k = np.arange(1, Hb + 1)
    meta = pd.Series(-((k - 10.0) ** 2) + 50, index=k)
    coda = pd.Series(k * 1.0, index=k)
    presto = pd.Series(np.where(k == 2, 9.0, 1.0), index=k)
    sotto = pd.Series(-k * 1.0, index=k)
    pm, pc, pp, ps = (picco_curva(x, Hb) for x in (meta, coda, presto, sotto))
    check("B1. picco a meta': barra 10, nessuna nota", pm["barra"] == 10 and pm["valore"] == 50
          and not pm["in_coda"] and not pm["presto"] and pm["nota"] == "")
    check("B2. picco in coda (ultimo quarto di H): «continua fino all'orizzonte»",
          pc["barra"] == Hb and pc["in_coda"] and "continua" in pc["nota"])
    check("B3. picco nelle prime barre: la nota parla di rumore e funding, non di commissione",
          pp["barra"] == 2 and pp["presto"] and "rumore" in pp["nota"] and "funding" in pp["nota"]
          and "commission" not in pp["nota"])
    check("B4. curva mai sopra lo zero: lo dice", "mai sopra lo zero" in ps["nota"])
    check("B5. la soglia del quarto: picco a 15 su 20 e' in coda, a 14 no (ceil(0,75·H))",
          picco_curva(pd.Series(np.where(k == 15, 5.0, 0.0), index=k), Hb)["in_coda"]
          and not picco_curva(pd.Series(np.where(k == 14, 5.0, 0.0), index=k), Hb)["in_coda"])

    # =====================================================================
    print("\nC · SOGLIA SUGLI ORIZZONTI PROVATI E PROVE EQUIVALENTI\n" + "-" * 70)
    check("C1. un punto solo = soglia_rumore(k), per k = 1, 7, 50",
          all(soglia_rumore_orizzonte(kk, punti=[41]) == soglia_rumore(kk) for kk in (1, 7, 50)))
    nuovo = soglia_rumore_orizzonte(7, 25, n_sim=200_000)
    vecchio = _vecchia_soglia_orizzonte(7, 25, n_sim=200_000)
    check("C2. senza punti identica alla versione di prima (k = 7, H = 25, stesso seme)",
          nuovo == vecchio and (25, 200_000, 0) in _CACHE_ORIZZONTE, f"{nuovo:.4f}")
    s4 = soglia_rumore_orizzonte(1, punti=[4, 16, 32, 96])
    check("C3. 4 orizzonti (1, 4, 8, 24 ore su M15): 2,44 come la simulazione di docs/68 §13",
          abs(s4 - 2.44) < 0.01, f"{s4:.3f}")
    s2 = soglia_rumore_orizzonte(1, punti=[16, 32])
    check("C4. due orizzonti vicini: fra un punto e due prove indipendenti",
          soglia_rumore(1) < s2 < soglia_rumore(2), f"{soglia_rumore(1):.3f} < {s2:.3f} < {soglia_rumore(2):.3f}")
    check("C5. punti = tutte le barre 1..25 = horizon 25",
          soglia_rumore_orizzonte(7, punti=range(1, 26), n_sim=200_000) == nuovo)
    check("C6. prove_equivalenti e' l'inversa di soglia_rumore (k = 1, 7, 148)",
          all(abs(prove_equivalenti(soglia_rumore(kk)) - kk) < 1e-6 for kk in (1, 7, 148)))
    v1 = prove_trigger_orizzonti(70, [41])
    v2 = prove_trigger_orizzonti(70, [41, 25])
    check("C7. voce dei trigger: con un H e' k; con due H fra k e 2k, dalla soglia sui due punti",
          v1 == 70.0 and 70 < v2 < 140
          and abs(v2 - prove_equivalenti(soglia_rumore_orizzonte(70, punti=[25, 41]))) < 1e-9,
          f"70 trigger, H = 41 e 25: {v2:.1f} prove")
    check("C8. punti non validi e nessun orizzonte si fermano",
          errore(lambda: soglia_rumore_orizzonte(1, punti=[0, 4]), "punti")
          and errore(lambda: soglia_rumore_orizzonte(1), "horizon"))

    # =====================================================================
    print("\nD · IL REGISTRO PER DATASET\n" + "-" * 70)
    rd.azzera()
    confine = pd.Timestamp("2025-05-01 13:45", tz="UTC")
    s1, e1 = rd.apri("BINANCE_PERP_BTCUSDT", "M15", confine, 41, nuove_prove=lambda: {"trigger": 0})
    s1.prove["trigger"] = 139
    s1b, e1b = rd.apri("BINANCE_PERP_BTCUSDT", "M15", confine, 41)
    check("D1. primo H: «nuovo», conto creato; stesso H: «stesso_h», nessuna risalita",
          e1 == "nuovo" and e1b == "stesso_h" and s1b is s1 and s1.risalite == [] and s1.h_provati == [41])
    s2_, e2 = rd.apri("BINANCE_PERP_BTCUSDT", "M15", confine, 25)
    check("D2. stesso dataset, H = 25: «h_nuovo», H provati [41, 25], stesso conto ripreso, risalita segnata",
          e2 == "h_nuovo" and s2_ is s1 and s1.h_provati == [41, 25] and s1.prove["trigger"] == 139
          and s1.risalite[-1] == {"cosa": "H", "da": 41, "a": 25, "oos_visto": False})
    rd.annota_oos(s1, {"trigger_long": ("E1",), "H": 25})
    s3_, e3 = rd.apri("BINANCE_PERP_BTCUSDT", "M15", confine, 41)
    check("D3. dopo l'out-of-sample, ritorno a H = 41: «h_gia_provato», nessun H in piu', diario tenuto",
          e3 == "h_gia_provato" and s1.h_provati == [41, 25] and len(s1.diario) == 1
          and s1.risalite[-1]["oos_visto"] is True and s1.oos_visto)
    s4_, e4 = rd.apri("BINANCE_PERP_BTCUSDT", "H1", confine, 41)
    s5_, e5 = rd.apri("BINANCE_PERP_BTCUSDT", "M15", confine + pd.Timedelta(days=3), 41)
    check("D4. altro timeframe o confine spostato (CSV aggiornato): dataset nuovo, da zero",
          e4 == "nuovo" and e5 == "nuovo" and s4_ is not s1 and s5_ is not s1
          and s4_.prove is None and s4_.diario == [] and s5_.h_provati == [41])
    check("D5. la chiave non dipende da come si scrive il confine (UTC o senza fuso, maiuscole)",
          rd.chiave_dataset("binance_perp_btcusdt", "m15", "2025-05-01 13:45")
          == rd.chiave_dataset("BINANCE_PERP_BTCUSDT", "M15", confine)
          and rd.storia("BINANCE_PERP_BTCUSDT", "M15", "2025-05-01 13:45") is s1)
    check("D6. la voce dei trigger del dataset usa gli H provati",
          s1.voce_trigger(139) == prove_trigger_orizzonti(139, [41, 25]) and s4_.voce_trigger(139) == 139.0)
    rd.annota_risalita(s1, "trigger", da=("E1",), a=("E2",))
    check("D7. una risalita su un'altra scelta porta con se' «oos visto»",
          s1.risalite[-1] == {"cosa": "trigger", "oos_visto": True, "da": ("E1",), "a": ("E2",)})
    rd.azzera()
    check("D8. azzera svuota il registro", rd.storia("BINANCE_PERP_BTCUSDT", "M15", confine) is None)
    check("D9. H < 1 si ferma", errore(lambda: rd.apri("X", "M15", confine, 0), "H deve"))

    # =====================================================================
    print("\nE · X_INVERSIONE_TREND CON IL PROFILO GIA' CALCOLATO\n" + "-" * 70)
    # un mercato con due ore che si muovono davvero: sale dalle 03:00, scende dalle 15:00
    Hp = 6
    nh = 120 * 96
    idx_h = pd.date_range("2023-01-02", periods=nh, freq="15min", tz="UTC")
    ore = idx_h.hour
    rend = rng.normal(0, 0.001, nh) + np.where(ore == 3, 0.0015, 0.0) + np.where(ore == 15, -0.0015, 0.0)
    close_h = 100.0 * np.exp(np.cumsum(rend))
    op_h = np.r_[100.0, close_h[:-1]]
    dfh = pd.DataFrame({"Open": op_h, "High": np.maximum(op_h, close_h) * 1.0005,
                        "Low": np.minimum(op_h, close_h) * 0.9995, "Close": close_h, "Volume": 1.0}, index=idx_h)
    for u in ("pips", "bp"):
        _muto(co.registra_inversione_trend, dfh, Hp, PIP, unita=u)
        uscite_prima = {lato: reg.get_exit(f"X_INVERSIONE_TREND_{lato}")(dfh).to_numpy().copy()
                        for lato in ("LONG", "SHORT")}
        contro_prima = co.fasce_contro()
        prof = _muto(profilo_orario, dfh, Hp, PIP, fuso="UTC", unita=u)
        _muto(co.registra_inversione_trend, dfh, Hp, PIP, unita=u, profilo=prof)
        uguali = all(np.array_equal(uscite_prima[l], reg.get_exit(f"X_INVERSIONE_TREND_{l}")(dfh).to_numpy())
                     for l in ("LONG", "SHORT"))
        check(f"E1. {u}: con il profilo passato le stesse fasce contro e le stesse uscite, barra per barra",
              uguali and co.fasce_contro() == contro_prima and co.profilo_congelato() is prof
              and contro_prima["long"] and contro_prima["short"] and uscite_prima["LONG"].any(),
              f"long chiude alle {', '.join(contro_prima['long'])}; short alle {', '.join(contro_prima['short'])}")
    prof8 = _muto(profilo_orario, dfh, 8, PIP, fuso="UTC", unita="bp")
    check("E2. un profilo con un altro H, o un'altra unita', si ferma",
          errore(lambda: co.registra_inversione_trend(dfh, Hp, PIP, unita="bp", profilo=prof8), "ricalcolalo")
          and errore(lambda: co.registra_inversione_trend(dfh, 8, PIP, unita="pips", profilo=prof8), "ricalcolalo"))

    # =====================================================================
    print("\nF · TRIGGER A ORARIO: USCITA A ORARIO = USCITA A H BARRE\n" + "-" * 70)
    reg.clear_registry()
    co.imposta_fuso("UTC")
    entrata = co.registra_entry_oraria("ORA_LONG_@10:00")
    regola = co.registra_uscita_oraria("X_ORA_@12:00")                 # 10:00 + 8 barre da 15 minuti
    kw = dict(n_barre=8, perc_sl=90.0, perc_tp=0.0, spread=0.0, commission=0.0, cash=10_000_000,
              pip_size=PIP, min_trades=1, verbose=False, inverti_su_opposto=True)
    a = _muto(run_exit_search_bt, dfc, entry_cols_long=[entrata], entry_cols_short=None, **kw)
    b = _muto(run_exit_search_bt, dfc, entry_cols_long=[entrata], entry_cols_short=None,
              exit_rule_pairs=[regola], **kw)
    ta, tb = a.trades(a.risultati.iloc[0]["combinazione"]), b.trades(b.risultati.iloc[0]["combinazione"])
    colonne = ["EntryTime", "ExitTime", "EntryPrice", "ExitPrice"]
    check("F1. long alle 10:00: H = 8 barre e X_ORA_@12:00 danno gli stessi trade",
          len(ta) > 30 and ta[colonne].reset_index(drop=True).equals(tb[colonne].reset_index(drop=True)),
          f"{len(ta)} trade")
    kw_lunghe = dict(kw, n_barre=20)
    c_ = _muto(run_exit_search_bt, dfc, entry_cols_long=[entrata], entry_cols_short=None,
               exit_rule_pairs=[regola], **kw_lunghe)
    tc = c_.trades(c_.risultati.iloc[0]["combinazione"])
    chiusi_a_orario = (pd.DatetimeIndex(tc["ExitTime"]).strftime("%H:%M") == "12:00")
    check("F2. con la scadenza piu' lunga (20 barre) chiude la regola: uscite alle 12:00 o prima (stop)",
          bool(chiusi_a_orario.any()) and bool((pd.DatetimeIndex(tc["ExitTime"]).hour <= 12).all()))
    reg.clear_registry()

    # =====================================================================
    print("\nG · BINANCE_PERP_BTCUSDT, CATALOGO VERO\n" + "-" * 70)
    csv = os.path.join(CARTELLA, "dati", "BINANCE_PERP_BTCUSDT_M15.csv")
    if not os.path.exists(csv):
        print("  [SALT] G · manca dati/BINANCE_PERP_BTCUSDT_M15.csv")
    else:
        from engine import vetrina as v
        s = _muto(v.prepara, "BINANCE_PERP_BTCUSDT", H=41, cartella=os.path.join(CARTELLA, "dati"))
        nomi = v._trigger_candidati(None)
        r = _muto(rosa_entry, s.df_is, s.H, s.pip, nomi=nomi, min_eventi=v.MIN_TRIGGER,
                  fuso=s.fuso, atr=s.atr, unita="bp").set_index("candidato")
        c = curva_scarto_orario(s.df_is, list(r.index), s.H, s.pip, fuso=s.fuso, unita="bp")
        diff = max(abs(c.loc[s.H, x] - r.loc[x, "scarto_bp"]) for x in r.index)
        check(f"G1. {len(r)} trigger del catalogo: a k = 41 la curva coincide con lo scarto della rosa (bp)",
              len(r) > 20 and diff < 1e-9, f"differenza massima {diff:.1e}")
        eventi_ok = all(c.attrs["eventi"][x] == int(r.loc[x, "eventi"]) for x in r.index)
        check("G2. stessi eventi della rosa per ogni trigger", eventi_ok)
        reg.clear_registry()

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
