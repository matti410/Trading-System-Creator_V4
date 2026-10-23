"""
Suite di validazione dell'atlante del trigger (22/10/2026, lavoro C, docs/66).

Si lancia da terminale, dalla cartella del progetto:

    python test_atlante.py

Non serve MetaTrader 5 e non serve nessun file di dati: usa un mercato
sintetico aperto 24 ore su 24 (come le crypto), con vantaggi messi apposta
dove il test lo dice. Sezioni:

    A · gli stati delle celle (engine/indicatori.py): identita' su M15 con
        confidenza.py, durate sugli altri timeframe, niente lookahead,
        sessioni con l'ora legale, basis
    B · l'atlante (engine/atlante.py): casi a risultato noto, conto a mano,
        minimo di eventi, mercato senza vantaggi
    C · le celle come filtri del passo 5 (strada B): registrazione, coppie,
        k_prove e rimisura nella ricerca dei filtri
    D · il Lab (engine/vetrina.py): spot agganciato ai perpetual, schermate 3c e
        3d, strada B al passo 5, celle nella soglia cumulata, strada A identica
"""
from __future__ import annotations

import sys
import time
import warnings

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

from engine import registry as reg
from engine.confidenza import asse_volatilita, cella_contesto
from engine.indicatori import (SESSIONI_ATLANTE, barre_per_durata, basis_alta, basis_bp,
                               cella_vol_trend, sessione_ingresso, trend_durata,
                               volatilita_durata)
from engine.livelli import GIORNATA_UTC, imposta_giornata, svuota_cache
from engine.quarantena import imposta_rollover

warnings.simplefilter("ignore")

H = 8
PIP = 0.01


def _indice(inizio="2022-01-03", giorni=730, minuti=15):
    return pd.date_range(inizio, periods=int(giorni * 1440 / minuti), freq=f"{minuti}min", tz="UTC")


class Mercato:
    """Un random walk 24/7 di cui si possono cambiare i rendimenti (le stesse candele per il resto)."""

    def __init__(self, idx, seme=0, sigma=0.0004):
        self.idx = idx
        rng = np.random.default_rng(seme)
        n = len(idx)
        self.rend = rng.normal(0, sigma, n)
        self.alto = np.abs(rng.normal(0, sigma * 0.75, n))
        self.basso = np.abs(rng.normal(0, sigma * 0.75, n))
        self.volume = rng.integers(20, 2000, n).astype(float)
        self.basis = rng.normal(0, 0.0005, n)

    def df(self, extra=None, spot=False):
        r = self.rend if extra is None else self.rend + extra
        close = 100.0 * np.exp(np.cumsum(r))
        op = np.r_[100.0, close[:-1]]
        d = pd.DataFrame({"Open": op, "High": np.maximum(op, close) * (1 + self.alto),
                          "Low": np.minimum(op, close) * (1 - self.basso), "Close": close,
                          "Volume": self.volume}, index=self.idx)
        if spot:
            d["spot_close"] = close * (1 - self.basis)
        return d


def _deriva_dopo(n, pos, quanto):
    """Rendimenti in piu' sulle barre p+1 .. p+H di ogni trigger p (il trade misurato)."""
    extra = np.zeros(n)
    for p, q in zip(pos, quanto):
        extra[p + 1: p + 1 + H] += q
    return extra


def _registra_entry(nome, direzione, tempi):
    tempi = pd.DatetimeIndex(tempi)

    def entry(d):
        return pd.Series(d.index.isin(tempi), index=d.index)
    reg.register_entry(nome, direction=direzione)(entry)


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    imposta_rollover(None)              # mercato 24/7: nessuna quarantena, come gli exchange
    imposta_giornata(GIORNATA_UTC)      # la giornata delle crypto
    svuota_cache()
    reg.clear_registry()

    # =================================================================== A ==
    print("\nA · Gli stati delle celle (engine/indicatori.py)")
    M = Mercato(_indice(giorni=60), seme=1)
    df = M.df()

    check("1. su M15 volatilita_durata = confidenza.asse_volatilita(20, 500), bit per bit",
          volatilita_durata(df).equals(asse_volatilita(df, 20, 500)))
    check("2. su M15 cella_vol_trend = confidenza.cella_contesto, bit per bit, sui due lati",
          cella_vol_trend(df, 1).equals(cella_contesto(df, 1))
          and cella_vol_trend(df, -1).equals(cella_contesto(df, -1)))

    attese = {5: (60, 1500), 15: (20, 500), 30: (20, 250), 60: (20, 125), 240: (20, 31)}
    trovate = {m: (barre_per_durata(_indice(giorni=3, minuti=m), 5),
                   barre_per_durata(_indice(giorni=3, minuti=m), 125)) for m in attese}
    check("3. durate in barre con almeno 20 rendimenti: M5 60/1500, M15 20/500, M30 20/250, "
          "H1 20/125, H4 20/31", trovate == attese, str(trovate))

    idx_h4 = _indice(giorni=400, minuti=240)
    d4 = Mercato(idx_h4, seme=2).df()
    r = np.log(d4["Close"] / d4["Close"].shift(1)) * 100
    dev = r.rolling(20).std()
    med = dev.rolling(31, min_periods=31).quantile(0.5)
    atteso = pd.Series(np.where(dev > med, 1.0, 0.0), index=d4.index).where(med.notna())
    v4 = volatilita_durata(d4)
    check("4. su H4 la deviazione usa 20 rendimenti (non 1,25) e la mediana 31 barre",
          v4.equals(atteso.rename("vol")) and int(v4.isna().sum()) == 20 + 31 - 1,
          f"NaN iniziali {int(v4.isna().sum())}")

    ds = M.df(spot=True)
    stati = {"volatilità": lambda x: volatilita_durata(x), "trend long": lambda x: trend_durata(x, 1),
             "trend short": lambda x: trend_durata(x, -1), "sessione": sessione_ingresso,
             "basis": basis_alta}
    pieni = {k: f(ds) for k, f in stati.items()}
    diversi = []
    for taglio in (900, 2500, 4100, len(ds) - 7):
        corto = ds.iloc[:taglio]
        svuota_cache()
        for k, f in stati.items():
            a, b = f(corto), pieni[k].iloc[:taglio]
            if not (np.allclose(a.to_numpy(), b.to_numpy(), equal_nan=True, rtol=0, atol=1e-12)):
                diversi.append((k, taglio))
    svuota_cache()
    check("5. nessun lookahead: tagliati i dati alla barra i, gli stati fino a i non cambiano "
          "(volatilità, trend dei due lati, sessione, basis; 4 tagli)", not diversi, str(diversi))

    sess = sessione_ingresso(ds)
    sabato = ds.index.tz_convert("Europe/London").dayofweek >= 5
    prossima = (ds.index + pd.Timedelta(minutes=15))
    fine_sett = np.asarray(prossima.tz_convert("Europe/London").dayofweek >= 5) & \
        np.asarray(prossima.tz_convert("America/New_York").dayofweek >= 5)
    check("6. sessioni: ogni barra in esattamente una cella (0-3, nessun NaN); il fine settimana "
          "è tutto ASIA_NOTTE",
          sess.notna().all() and set(np.unique(sess)) <= {0.0, 1.0, 2.0, 3.0}
          and (sess[fine_sett] == 0).all(), f"celle {dict(sess.value_counts().sort_index())}")

    def cella_a(t):
        i = pd.DatetimeIndex([pd.Timestamp(t, tz="UTC")])
        d = pd.DataFrame(index=i.append(i + pd.Timedelta(minutes=15)))
        return SESSIONI_ATLANTE[int(sessione_ingresso(d).iloc[0])]

    casi = {"2024-02-14 11:45": "EUROPA",      # ingresso 12:00 UTC: Londra 12:00, New York 07:00 (EST)
            "2024-03-13 11:45": "LONDRA_NY",   # New York gia' in ora legale (dal 10/3), Londra no
            "2024-03-13 11:30": "EUROPA",      # ingresso 11:45: New York 07:45, chiusa
            "2024-04-10 11:45": "LONDRA_NY",
            "2024-04-10 16:00": "AMERICA",     # ingresso 16:15 UTC: Londra 17:15, New York 12:15
            "2024-04-10 06:45": "EUROPA",      # ingresso 07:00 UTC: Londra 08:00 (BST)
            "2024-04-10 06:30": "ASIA_NOTTE",
            "2024-04-13 11:45": "ASIA_NOTTE"}  # sabato
    trovati = {t: cella_a(t) for t in casi}
    check("7. sessioni sulla barra d'ingresso (i+1), ora locale con l'ora legale sfasata di marzo",
          trovati == casi, str({t: v for t, v in trovati.items() if v != casi[t]}))

    b = basis_bp(ds)
    spot_buco = ds.copy()
    spot_buco.iloc[3000:3010, spot_buco.columns.get_loc("spot_close")] = np.nan
    ba = basis_alta(spot_buco)
    check("8. basis: (perpetual − spot) / spot × 10.000; NaN dove manca lo spot e per la finestra "
          "che lo contiene; senza spot tutta NaN",
          np.allclose(b, (ds["Close"] - ds["spot_close"]) / ds["spot_close"] * 1e4)
          and ba.iloc[3000:3010 + 500 - 1].isna().all() and ba.iloc[3010 + 500 - 1:].notna().all()
          and basis_alta(df).isna().all() and basis_bp(df).isna().all())

    # =================================================================== B ==
    print("\nB · L'atlante (engine/atlante.py)")
    from engine.atlante import CELLE, _stato, atlante, celle_atlante, registra_filtri_cella
    from engine.stagionalita import fasce_orarie, in_unita, scarto_orario

    M = Mercato(_indice(giorni=730), seme=5)
    d0 = M.df()
    n = len(d0)
    rng = np.random.default_rng(11)
    pos = np.sort(rng.choice(np.arange(600, n - 2 * H), size=n // 40, replace=False))
    vol0 = volatilita_durata(d0).to_numpy()
    e = 0.0001                                       # 1 bp a barra, 8 bp a evento
    alta = vol0[pos] == 1
    extra = _deriva_dopo(n, pos, np.where(alta, e, np.where(vol0[pos] == 0, -e, 0.0)))
    d1 = M.df(extra)
    _registra_entry("T_VOL_ALTA", 1, d1.index[pos])
    t0 = time.time()
    a1 = atlante(d1, H, PIP, nomi=["T_VOL_ALTA"], fuso="UTC")
    durata = time.time() - t0
    passano = sorted(a1.loc[a1["passa"], "cella"])
    check("9. vantaggio solo in volatilità alta (trigger piatto in media): passano solo le 2 celle "
          "a volatilità alta, nessuna sessione",
          passano == ["VOL_ALTA_TREND_CONTRO", "VOL_ALTA_TREND_FAVORE"], f"passano {passano}")
    check("10. senza lo spot l'atlante ha 8 celle per entry (niente basis)",
          len(a1) == 8 and set(a1["asse"]) == {"vol_trend", "sessione"})

    # una deriva del mercato solo in EUROPA, trigger senza vantaggio che scatta soprattutto li'
    sess0 = sessione_ingresso(d0).to_numpy()
    eu = sess0 == 1
    deriva = np.where(np.r_[eu[1:], False], 0.00015, 0.0)
    d2 = M.df(deriva)
    p_trig = np.where(eu, 1 / 15, 1 / 300)
    pos2 = np.flatnonzero(rng.random(n) < p_trig)
    pos2 = pos2[(pos2 > 600) & (pos2 < n - 2 * H)]
    _registra_entry("T_ORA_EUROPA", 1, d2.index[pos2])
    a2 = atlante(d2, H, PIP, nomi=["T_ORA_EUROPA"], fuso="UTC")
    r_eu = a2[a2["cella"] == "EUROPA"].iloc[0]
    # lo stesso trigger contro il mercato di tutte le ore: la rosa con la baseline globale
    from engine.rosa import rosa_entry
    globale = float(rosa_entry(d2, H, PIP, nomi=["T_ORA_EUROPA"], baseline="globale", fuso="UTC",
                               unita="bp", unita_extra=[])["t_netto"].iat[0])
    check("11. deriva del mercato solo in EUROPA, trigger senza vantaggio: con il mercato della "
          "cella lo scarto è circa zero e la cella non passa; contro il mercato di tutte le ore "
          "sembrerebbe un vantaggio",
          abs(r_eu["t"]) < 2.5 and not r_eu["passa"] and globale > 4,
          f"t di cella {r_eu['t']:+.2f}, t contro tutte le ore {globale:+.1f}")

    sess_trig = sess0[pos]
    quota_eu = float((sess_trig == 1).mean())
    q3 = np.where(sess_trig == 1, e, -e * quota_eu / (1 - quota_eu))
    d3 = M.df(_deriva_dopo(n, pos, q3))
    _registra_entry("T_EUROPA", 1, d3.index[pos])
    # solo l'asse delle sessioni: la deriva messa dopo i trigger sposta anche il trend dei
    # trigger che vengono dopo (gap_trend e' della giornata), quindi sul mercato finto
    # sessione e trend non sono piu' indipendenti e le celle del trend ricevono una parte del vantaggio
    a3 = atlante(d3, H, PIP, nomi=["T_EUROPA"], fuso="UTC", assi=("sessione",))
    passano3 = sorted(a3.loc[a3["passa"], "cella"])
    check("12. vantaggio solo in EUROPA (compensato nelle altre sessioni): fra le sessioni passa solo EUROPA",
          passano3 == ["EUROPA"], f"passano {passano3}")

    costi = {"commission": 0.0005, "spread": 0.0}     # 10 bp andata e ritorno, piu' del vantaggio (8 bp)
    a4 = atlante(d1, H, PIP, costi=costi, nomi=["T_VOL_ALTA"], fuso="UTC")
    va = a4["cella"].str.startswith("VOL_ALTA")
    check("13. vantaggio lordo più piccolo del costo andata e ritorno: le celle a volatilità alta "
          "non passano, «non paga i costi»; il lordo non cambia",
          (a4.loc[va, "motivo"] == "non paga i costi").all() and not a4["passa"].any()
          and np.allclose(a4["scarto_bp"], a1["scarto_bp"], equal_nan=True),
          f"netto {a4.loc[va, 'netto_bp'].round(2).tolist()} bp")

    ore = pd.date_range(d1.index[0].floor("D"), d1.index[-1] + pd.Timedelta(days=1), freq="8h", tz="UTC")
    funding = pd.DataFrame({"tasso": 0.005, "intervallo_ore": 8.0}, index=ore)
    a5 = atlante(d1, H, PIP, funding=funding, nomi=["T_VOL_ALTA"], fuso="UTC")
    _registra_entry("T_VOL_ALTA_SHORT", -1, d1.index[pos])
    a5s = atlante(M.df(-extra), H, PIP, funding=funding, nomi=["T_VOL_ALTA_SHORT"], fuso="UTC")
    a0s = atlante(M.df(-extra), H, PIP, nomi=["T_VOL_ALTA_SHORT"], fuso="UTC")
    vs = a5s["cella"].str.startswith("VOL_ALTA")
    check("14. perpetual finto, funding alto: il long con vantaggio lordo non paga il funding "
          "(«non paga i costi», lordo invariato); lo short lo incassa e il suo netto sale",
          (a5.loc[va, "motivo"] == "non paga i costi").all()
          and np.allclose(a5["scarto_bp"], a1["scarto_bp"], equal_nan=True)
          and (a5s.loc[vs, "netto_bp"].to_numpy() > a0s.loc[vs, "netto_bp"].to_numpy() + 5).all()
          and a5s.loc[vs, "passa"].all(),
          f"long netto {a5.loc[va, 'netto_bp'].round(1).tolist()} bp, short "
          f"{a0s.loc[vs, 'netto_bp'].round(1).tolist()} → {a5s.loc[vs, 'netto_bp'].round(1).tolist()} bp")

    # il conto a mano di una cella
    r = a1[(a1["cella"] == "EUROPA")].iloc[0]
    cel = _stato(d1, "sessione", 1).to_numpy()
    fas = fasce_orarie(d1.index, "UTC")[0]
    ing1 = np.r_[d1["Open"].to_numpy()[1:], np.nan]
    f1 = np.full(n, np.nan)
    f1[:n - H] = (d1["Close"].to_numpy()[H:] - ing1[:n - H]) / PIP
    fb = in_unita(f1, "bp", PIP, prezzo=ing1)
    usa = np.isfinite(fb)
    cod = fas * 4 + cel.astype(int)
    pe1 = pos[(cel[pos] == 1) & usa[pos]]
    sc, se = scarto_orario(fb, cod, usa, pe1, 1, H)
    medie = {c: fb[usa & (cod == c)].mean() for c in np.unique(cod[pe1])}
    a_mano = np.mean([fb[p] - medie[cod[p]] for p in pe1])
    check("15. una cella fatta a mano: eventi, scarto (media meno il mercato della cella e della "
          "fascia) e t uguali a scarto_orario e all'atlante",
          r["eventi"] == pe1.size and np.isclose(r["scarto_bp"], a_mano, rtol=1e-9)
          and np.isclose(r["scarto_bp"], sc, rtol=1e-9) and np.isclose(r["t"], sc / se, rtol=1e-9),
          f"{pe1.size} eventi, scarto {a_mano:+.4f} bp, t {sc / se:+.3f}")
    netto_mano = np.mean([fb[p] - 0.0005 * (ing1[p] + d1['Close'].iat[p + H]) / ing1[p] * 1e4 for p in pe1])
    r4 = a4[a4["cella"] == "EUROPA"].iloc[0]
    check("16. il netto fatto a mano: rendimento meno la commissione sui due lati (come i trade)",
          np.isclose(r4["netto_bp"], netto_mano, rtol=1e-9), f"{netto_mano:+.4f} bp")

    soglia = int(a1["eventi"].sort_values().iloc[2]) + 1
    a6 = atlante(d1, H, PIP, nomi=["T_VOL_ALTA"], fuso="UTC", min_eventi=soglia)
    sotto = a6["eventi"] < soglia
    check("17. minimo di eventi: una cella sotto il minimo è «troppo pochi casi», senza t, e non "
          "conta in k_misurate",
          sotto.sum() >= 3 and (a6.loc[sotto, "motivo"] == "troppo pochi casi").all()
          and a6.loc[sotto, "t"].isna().all() and a6.attrs["k_misurate"] == int((~sotto).sum())
          and a1.attrs["k_misurate"] == 8,
          f"minimo {soglia}: {int(sotto.sum())} celle fuori, k = {a6.attrs['k_misurate']}")

    dspot = M.df(extra, spot=True)
    dspot.iloc[20_000:30_000, dspot.columns.get_loc("spot_close")] = np.nan     # un buco dello spot
    a7 = atlante(dspot, H, PIP, nomi=["T_VOL_ALTA"], fuso="UTC")
    eventi_basis = a7.loc[a7["asse"] == "basis", "eventi"].sum()
    validi = int(np.isfinite(celle_atlante(dspot, 1)["basis"].to_numpy()[pos]).sum())
    check("18. con lo spot agganciato 10 celle (basis alta e bassa); gli eventi della basis sono "
          "quelli con lo stato calcolabile",
          len(a7) == 10 and eventi_basis == validi and validi < pos.size - 200
          and a7.loc[a7["asse"] != "basis", "eventi"].sum() == 2 * pos.size,
          f"{eventi_basis} eventi su {pos.size}")

    # mercato senza vantaggi: 60 entry casuali, 10 mercati
    con_celle = 0
    celle_passate = 0
    tempi, t_nulli = [], []
    for seme in range(10):
        Mn = Mercato(_indice(giorni=365), seme=100 + seme)
        dn = Mn.df()
        rn = np.random.default_rng(200 + seme)
        nomi = []
        for i in range(60):
            p = np.sort(rn.choice(np.arange(600, len(dn) - 2 * H), size=len(dn) // 12, replace=False))
            nome = f"NULLA_{seme}_{i}"
            _registra_entry(nome, 1 if i % 2 == 0 else -1, dn.index[p])
            nomi.append(nome)
        t0 = time.time()
        an = atlante(dn, H, PIP, nomi=nomi, fuso="UTC")
        tempi.append(time.time() - t0)
        t_nulli += list(an.loc[an["misurata"], "t"])
        k = int(an["passa"].sum())
        celle_passate += k
        con_celle += k > 0
        reg.remove_entries("NULLA_")
    t_nulli = np.asarray(t_nulli)
    check("19. mercato senza vantaggi: la solidità delle celle si comporta come il caso "
          "(deviazione fra 0,9 e 1,1, |t| > 1,96 fra il 3% e il 7% delle celle)",
          t_nulli.size > 4000 and 0.9 < t_nulli.std() < 1.1 and 0.03 < np.mean(np.abs(t_nulli) > 1.96) < 0.07,
          f"{t_nulli.size} celle misurate, deviazione {t_nulli.std():.3f}, "
          f"|t| > 1,96 nel {np.mean(np.abs(t_nulli) > 1.96):.1%}")
    check("20. mercato senza vantaggi, 60 entry × 8 celle, 10 mercati: con q = 20% in media al massimo "
          "2 mercati su 10 hanno una cella che passa (tutte finte); ne accettiamo fino a 4",
          con_celle <= 4, f"mercati con almeno una cella che passa: {con_celle} su 10, celle in tutto "
          f"{celle_passate} su 4.800; {np.mean(tempi):.1f} s per atlante da 480 celle")

    dc = M.df(extra)
    cl = celle_atlante(dc, 1)
    check("21. celle_atlante: una colonna per asse, codici nell'ordine di CELLE",
          list(cl.columns) == ["vol_trend", "sessione"]
          and set(np.unique(cl["vol_trend"].dropna())) <= {0.0, 1.0, 2.0, 3.0}
          and cl["sessione"].equals(pd.Series(sessione_ingresso(dc).to_numpy(), index=dc.index, name="sessione")))
    print(f"  (atlante di 8 celle su {n} barre: {durata:.2f} s)")

    # =================================================================== C ==
    print("\nC · Le celle come filtri del passo 5 (strada B)")
    from engine.atlante import nome_filtro_cella
    from engine.filter_search_bt import BASELINE, run_filter_search_bt
    from engine.giudizio import soglia_rumore

    dfc = M.df(extra, spot=True)
    nomi_c = registra_filtri_cella(dfc, "EUROPA", "EUROPA")
    coppie = {p: (u, g) for p, u, g in reg.list_filter_pairs()}
    sess_c = sessione_ingresso(dfc)
    check("22. stessa cella sui due lati: CELLA_EUROPA_L (+1) e CELLA_EUROPA_S (−1), una coppia "
          "CELLA_EUROPA; vere dove la barra del segnale è in EUROPA",
          nomi_c == ["CELLA_EUROPA_L", "CELLA_EUROPA_S"]
          and coppie.get("CELLA_EUROPA") == ("CELLA_EUROPA_L", "CELLA_EUROPA_S")
          and nome_filtro_cella("EUROPA", "EUROPA") == "CELLA_EUROPA"
          and reg.get_filter("CELLA_EUROPA_L")(dfc).equals(sess_c == 1)
          and reg.get_filter("CELLA_EUROPA_S")(dfc).equals(sess_c == 1))

    nomi_d = registra_filtri_cella(dfc, "VOL_ALTA_TREND_FAVORE", "BASIS_BASSA")
    coppie = {p: (u, g) for p, u, g in reg.list_filter_pairs()}
    etichetta = nome_filtro_cella("VOL_ALTA_TREND_FAVORE", "BASIS_BASSA")
    m_l = reg.get_filter(nomi_d[0])(dfc)
    m_s = reg.get_filter(nomi_d[1])(dfc)
    check("23. celle diverse sui due lati: una coppia con il nome delle due celle; il long usa il "
          "trend del long, lo short la basis; le celle di prima tolte dal registro",
          etichetta == "CELLA_VOL_ALTA_TREND_FAVORE_L_BASIS_BASSA_S"
          and coppie.get(etichetta) == tuple(nomi_d)
          and m_l.equals(cella_vol_trend(dfc, 1) == 3) and m_s.equals(basis_alta(dfc) == 0)
          and not any(n.startswith("CELLA_EUROPA") for n in reg.list_filters()))

    corto = dfc.iloc[:5000]
    check("24. il filtro su un pezzo dello storico (in-sample, metà, out-of-sample) dà gli stessi valori "
          "dello storico intero; non è mai sempre vero o sempre falso",
          reg.get_filter(nomi_d[0])(corto).equals(m_l.iloc[:5000])
          and 0.05 < m_l.mean() < 0.95 and 0.05 < m_s.mean() < 0.95)

    errori = []
    for celle in (("VOL_ALTA", None), ("BASIS_ALTA", None), (None, None)):
        try:
            registra_filtri_cella(df if celle[0] == "BASIS_ALTA" else dfc, *celle)
            errori.append(None)
        except ValueError as e:
            errori.append(str(e)[:40])
    check("25. si ferma con una cella sconosciuta, con la basis senza lo spot e senza celle",
          all(errori), str(errori))

    nomi_c = registra_filtri_cella(dfc, "EUROPA", "EUROPA")
    _registra_entry("T_LONG_C", 1, dfc.index[pos])
    _registra_entry("T_SHORT_C", -1, dfc.index[pos + 3])
    kw = dict(entry_long="T_LONG_C", entry_short="T_SHORT_C", n_barre=H, filtri=nomi_c,
              commission=0.0005, spread=0.0, cash=1e6, pip_size=PIP, unita="bp", verbose=False,
              quarantena=False)
    fs_a = run_filter_search_bt(dfc, **kw)
    fs_b = run_filter_search_bt(dfc, k_prove=480, **kw)
    uguali = fs_a.risultati.drop(columns=["oltre_rumore", "esito", "motivo"]).equals(
        fs_b.risultati.drop(columns=["oltre_rumore", "esito", "motivo"]))
    check("26. ricerca dei filtri con k_prove = 480 (le celle dell'atlante): soglia = Šidák a 480 prove, "
          "segnata come rimisura; senza k_prove soglia delle righe (1) come prima; il resto identico",
          np.isclose(fs_b.soglia_rumore, soglia_rumore(480)) and fs_b.rimisura
          and np.isclose(fs_a.soglia_rumore, soglia_rumore(1)) and not fs_a.rimisura and uguali
          and list(fs_b.risultati["filtro"]) .count("CELLA_EUROPA") == 1
          and len(fs_b.risultati) == 2,
          f"soglia {fs_a.soglia_rumore:.2f} → {fs_b.soglia_rumore:.2f}")
    try:
        run_filter_search_bt(dfc, k_prove=0, **kw)
        ferma = False
    except ValueError:
        ferma = True
    check("27. k_prove = 0 si ferma con un errore", ferma)

    # =================================================================== D ==
    print("\nD · Il Lab: schermate 3c e 3d, strada B al passo 5, soglia cumulata")
    import contextlib
    import io
    import os
    import tempfile
    import engine.exchange as X
    import engine.vetrina as vt

    def muto(f, *a, **k):
        with contextlib.redirect_stdout(io.StringIO()):
            return f(*a, **k)

    def errore(f, testo):
        try:
            muto(f)
        except (ValueError, RuntimeError) as e:
            return testo in str(e)
        return False

    ML = Mercato(_indice(giorni=400), seme=7)
    dl0 = ML.df()
    nl = len(dl0)
    rl = np.random.default_rng(17)
    posl = np.sort(rl.choice(np.arange(600, nl - 2 * H), size=nl // 30, replace=False))
    vl = volatilita_durata(dl0).to_numpy()[posl]
    el = 0.0004                                      # 32 bp a evento: piu' dei costi del perpetual Binance
    dl = ML.df(_deriva_dopo(nl, posl, np.where(vl == 1, el, np.where(vl == 0, -el, 0.0))))
    _registra_entry("T_LAB_VOL_ALTA", 1, dl.index[posl])
    spot = dl.copy()
    spot[["Open", "High", "Low", "Close"]] = spot[["Open", "High", "Low", "Close"]].mul(1 - ML.basis, axis=0)
    orari = pd.date_range(dl.index[0].floor("8h"), dl.index[-1].ceil("8h"), freq="8h")
    fund = X.con_intervalli(pd.DataFrame({"tasso": 0.0001}, index=orari))
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as senza:
        for cartella in (tmp, senza):
            X.salva_csv(dl, os.path.join(cartella, "BINANCE_PERP_BTCUSDT_M15.csv"))
            X.salva_funding(fund, X.file_funding("BINANCE_PERP_BTCUSDT", cartella))
        X.salva_csv(spot, os.path.join(tmp, "BINANCE_SPOT_BTCUSDT_M15.csv"))
        s = muto(vt.prepara, "BINANCE_PERP_BTCUSDT", H=H, cartella=tmp)
        s0 = muto(vt.prepara, "BINANCE_PERP_BTCUSDT", H=H, cartella=senza)
        rie = s.tabelle["riepilogo"].set_index("")[" "]
        check("28. prepara sul perpetual aggancia lo spot della stessa coppia (riga «Spot» nel "
              "riepilogo); senza il file dello spot non si ferma e dice quale file serve",
              "spot_close" in s.df.columns and "BINANCE_SPOT_BTCUSDT" in rie["Spot (perpetual)"]
              and "spot_close" not in s0.df.columns and "manca" in s0.spot_nota
              and "scarica_dati_crypto.py BINANCE_SPOT_BTCUSDT" in s0.spot_nota)

        check("29. l'atlante vuole i trigger scelti (schermata 3)",
              errore(lambda: vt.atlante_dei_trigger(s), "Esplora"))
        muto(vt.esplora, s)
        muto(vt.esplora, s0)
        check("30. scegli_cella vuole l'atlante (schermata 3c)",
              errore(lambda: vt.scegli_cella(s, long="EUROPA"), "3c"))
        muto(vt.scegli_trigger, s, long="T_LAB_VOL_ALTA")
        tab = muto(vt.atlante_dei_trigger, s)
        k = int(tab.attrs["k_misurate"])
        passano = sorted(tab.loc[(tab["candidato"] == "T_LAB_VOL_ALTA") & tab["passa"], "cella"])
        check("31. schermata 3c: tutte le entry vere, 10 celle per entry con la basis; per il trigger "
              "scelto le colonne in pips accanto; passano solo celle a volatilità alta (con lo spread di un passo a prezzo 100 non sempre tutte e due)",
              set(tab.attrs["assi"]) == {"vol_trend", "sessione", "basis"}
              and (tab.groupby("candidato").size() == 10).all()
              and tab["candidato"].nunique() == len(vt._trigger_candidati(None)) - len(tab.attrs["scartate"])
              and tab.loc[tab["candidato"] == "T_LAB_VOL_ALTA", "scarto_pips"].notna().any()
              and tab.loc[tab["candidato"] != "T_LAB_VOL_ALTA", "scarto_pips"].isna().all()
              and passano and set(passano) <= {"VOL_ALTA_TREND_CONTRO", "VOL_ALTA_TREND_FAVORE"},
              f"k = {k}, passano {passano}")
        cella_no = next(c for c in tab.loc[tab["candidato"] == "T_LAB_VOL_ALTA", "cella"] if c not in passano)
        check("32. scegli_cella si ferma: cella sconosciuta, cella che non passa (con l'elenco di quelle che "
              "passano), lato senza trigger, due celle sullo stesso lato",
              errore(lambda: vt.scegli_cella(s, long="VOL_ALTA"), "sconosciuta")
              and errore(lambda: vt.scegli_cella(s, long=cella_no), "VOL_ALTA_TREND_FAVORE")
              and errore(lambda: vt.scegli_cella(s, short="EUROPA"), "non ha trigger")
              and errore(lambda: vt.scegli_cella(s, long="EUROPA, AMERICA"), "Una cella sola"))
        muto(vt.scegli_cella, s, long="VOL_ALTA_TREND_FAVORE")
        muto(vt.imposta_uscite, s, barre_long=H, sl=90)
        muto(vt.trova_strategia, s)
        r = s.fs.risultati
        check("33. strada B al passo 5: si prova solo la cella (una riga), asticella = Šidák sulle k celle "
              "dell'atlante, ricerca segnata come rimisura e non contata fra i filtri",
              list(r["filtro"]) .count("CELLA_VOL_ALTA_TREND_FAVORE_L") == 1 and len(r) == 2
              and np.isclose(s.fs.soglia_rumore, soglia_rumore(k)) and s.fs.rimisura
              and s.prove["filtri"] == {},
              f"asticella {s.fs.soglia_rumore:.2f} con k = {k}")
        muto(vt.scheda, s, filtro="CELLA_VOL_ALTA_TREND_FAVORE_L")
        sc = s.tabelle["soglia_cumulata"]
        check("34. soglia cumulata sotto la scheda: trigger + celle dell'atlante + uscite; la cella "
              "riprovata al passo 5 non conta due volte",
              sc["celle"] == k and sc["filtri"] == 0 and sc["k"] == sc["trigger"] + k + sc["uscite"]
              and np.isclose(sc["soglia"], soglia_rumore(sc["k"])) and "celle dell'atlante (schermata 3c" in sc["frase"]
              and "non conta due volte" in sc["frase"], sc["frase"][:150])
        muto(vt.atlante_dei_trigger, s)
        check("35. atlante rifatto uguale: le celle non contano due volte; la cella scelta si azzera e "
              "i suoi filtri escono dal registro",
              list(s.prove["celle"].values()) == [k] and s.cella_long is None
              and not any(n.startswith("CELLA_") for n in reg.list_filters()))
        muto(vt.scegli_cella, s, long="VOL_ALTA_TREND_FAVORE")
        muto(vt.scegli_cella, s)
        muto(vt.imposta_uscite, s, barre_long=H, sl=90)
        muto(vt.trova_strategia, s)
        muto(vt.scegli_trigger, s0, long="T_LAB_VOL_ALTA")
        muto(vt.imposta_uscite, s0, barre_long=H, sl=90)
        muto(vt.trova_strategia, s0)
        check("36. strada A (nessuna cella): tutti i filtri del catalogo, nessuna cella; risultati identici "
              "al bit con e senza lo spot agganciato",
              not s.fs.rimisura and not any(f.startswith("CELLA_") for f in s.fs.risultati["filtro"])
              and s.fs.risultati.equals(s0.fs.risultati) and s.es.risultati.equals(s0.es.risultati)
              and s.df_is.drop(columns="spot_close").equals(s0.df_is),
              f"{len(s.fs.risultati) - 1} filtri")
        sc_n = vt.soglia_cumulata(ev=s.ev, es=s.es, fs=[s.fs, s.fs], atlante=[tab, tab],
                                  t=1.5)
        check("37. soglia_cumulata per il notebook: atlante=… conta le celle una volta; una ricerca con "
              "rimisura non si conta",
              sc_n["celle"] == k and sc_n["filtri"] == len(s.fs.risultati) - 1
              and vt.soglia_cumulata(fs=fs_b)["filtri"] == 0 and vt.soglia_cumulata(fs=fs_a)["filtri"] == 1)

    reg.clear_registry()
    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
