"""
Suite della mappa delle anomalie, parte engine (27/10/2026, docs/73 §B.7, PR B1):
engine/mappa.py, engine/ipotesi.py, le variabili in engine/indicatori.py e il
file degli esiti in engine/studio.py, su dati sintetici a risultato noto.

    A · le fasce dalle sole barre passate (troncamento, finestra, valori uguali)
    B · la misura: un effetto messo apposta si ritrova; il riferimento; i quattro
        esiti; senza effetto «risponde» non esce piu' di quanto consente q
    C · le variabili delle schede: le schede del funding e della basis (M01, M04,
        M05) tolte il 29/10/2026 (docs/77), M06 (BTC e altcoin per data);
        orizzonti non interi
    D · il conto (le prove gia' viste, M07 5 + 5), la regola dei doppioni (su
        schede di prova), lo studio
    E · le schede approvate coincidono con docs/74
    G · (28/10/2026) l'incertezza della mappa senza sconto e il passaggio ai
        blocchi settimanali; senza effetto, con variabili persistenti come quelle
        vere: a blocchi di 8 ore (come la M04 di allora), lente a quintili (come la
        M05 di allora), e con la
        volatilita' variabile; «risponde» su 1.000 mercati sotto il 15%
    F · (28/10/2026, PR B2) il notebook della mappa (engine/vetrina_mappa.py) su
        file sintetici in una cartella temporanea: non apre lo studio, non scrive
        H, scrive conto ed esito; le fasce degeneri e M06; le schede tolte; la 2b
        del Lab in sola lettura; la soglia con mappa = 0 identica a prima

Si lancia da terminale, dalla cartella del progetto:

    python test_mappa.py

(su Windows: PYTHONIOENCODING=utf-8). Non serve nessun file di dati.
"""
from __future__ import annotations

import dataclasses
import sys
import tempfile
import warnings

import numpy as np
import pandas as pd

warnings.simplefilter("ignore")

import engine.exchange as X
from engine import indicatori as ind
from engine import mappa as mp
from engine import registro_dataset as rd
from engine import studio as st
from engine.ipotesi import QUALUNQUE_ORA, QUINTILI, SCHEDE, SCHEDE_TOLTE, STESSA_ORA, Scheda
from engine.quarantena import imposta_rollover
from engine.stagionalita import fasce_orarie, in_unita, media_per_fascia, rendimenti_avanti
from test_atlante import Mercato, _indice

PIP = 0.01


def _scheda(**k) -> Scheda:
    """Una scheda di prova, a quintili, sopra la M07."""
    return dataclasses.replace(SCHEDE["M07"], id="T", conta_segno_opposto=False, **k)


def _a_categorie(attese=None, ore=4) -> Scheda:
    """Una scheda di prova con le 5 fasce gia' calcolate (categorie 0..4 = Q1..Q5): niente quintili da rifare."""
    return _scheda(tipo="categorie", categorie={float(j): q for j, q in enumerate(QUINTILI)},
                   attese=attese or {"Q5": -1, "Q1": 1}, orizzonte_ore=ore)


def _drift(n, pos, quanto, h):
    """Rendimenti in piu' sulle barre p+1 .. p+h di ogni barra p."""
    extra = np.zeros(n)
    for p in pos:
        extra[p + 1: p + 1 + h] += quanto
    return extra


def _scrivi_dataset(cartella, symbol, mercato_, funding_costante=0.0, seme_funding=5, spot_uguale=0.0):
    """Il CSV del perpetual, quello dello spot della stessa coppia e il funding (00/08/16 UTC), in `cartella`."""
    import os
    df = mercato_.df()
    X.salva_csv(df, os.path.join(cartella, f"{symbol}_M15.csv"))
    spot = df.copy()
    basis = mercato_.basis.copy()
    if spot_uguale:                      # lo spot uguale al perpetual su una quota delle barre: basis zero
        basis[np.random.default_rng(seme_funding + 2).random(len(basis)) < spot_uguale] = 0.0
    for c in ("Open", "High", "Low", "Close"):
        spot[c] = df[c] * (1 - basis)
    X.salva_csv(spot, os.path.join(cartella, symbol.replace("_PERP_", "_SPOT_") + "_M15.csv"))
    ore = pd.date_range(df.index[0].floor("8h"), df.index[-1] + pd.Timedelta(hours=8), freq="8h")
    tasso = np.random.default_rng(seme_funding).normal(1e-4, 1e-4, len(ore))
    if funding_costante:
        tasso[np.random.default_rng(seme_funding + 1).random(len(ore)) < funding_costante] = 1e-4
    X.salva_funding(pd.DataFrame({"tasso": tasso}, index=ore), X.file_funding(symbol, cartella))
    return df


def _righe(percorso) -> int:
    from pathlib import Path
    p = Path(percorso)
    return sum(1 for r in p.read_text(encoding="utf-8").splitlines() if r.strip()) if p.exists() else 0


def sezione_f(check) -> None:
    """La parte B2: engine/vetrina_mappa.py (le schermate del notebook), la 2b del Lab, il parametro mappa= della soglia."""
    import contextlib
    import copy
    import io
    import os

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from engine import vetrina as vt
    from engine import vetrina_mappa as vm

    def zitto(f, *a, **k):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = f(*a, **k)
        plt.close("all")
        return out, buf.getvalue()

    BTC, ETH = "BINANCE_PERP_BTCUSDT", "BINANCE_PERP_ETHUSDT"
    idx = _indice("2022-01-03", giorni=730)
    with tempfile.TemporaryDirectory() as tmp:
        _scrivi_dataset(tmp, BTC, Mercato(idx, seme=11))
        _scrivi_dataset(tmp, ETH, Mercato(idx, seme=12), funding_costante=0.6, spot_uguale=0.6)
        try:
            zitto(vm.apri_mappa, BTC, "M15", tmp, macchina="pc")
            rifiuta = False
        except RuntimeError as e:
            rifiuta = "Lo studio non è ancora aperto" in str(e)
        d = vt.apri_dati(BTC, "M15", tmp, confine="studio", macchina="pc")
        vt.dividi_dati(d, d.df)                                   # apre lo studio, come la schermata 1 del Lab
        giornale = os.path.join(tmp, "studio", f"{BTC}_M15", "giornale_pc.jsonl")
        m, _ = zitto(vm.apri_mappa, BTC, "M15", tmp, macchina="pc")
        check("F1. il notebook della mappa non apre lo studio (lo apre il Lab) e quando entra non scrive nessun H: "
              "il giornale resta vuoto, gli orizzonti provati del Lab non cambiano",
              rifiuta and _righe(giornale) == 0 and m.storia.h_provati == [] and vt.fasce_mappa(m.storia) == 0
              and m.df_is.index[-1] < m.ingresso.confine)

        tab7, _ = zitto(vm.mappa_di_una_scheda, m, "M07")
        righe_1 = _righe(giornale)
        tab7b, _ = zitto(vm.mappa_di_una_scheda, m, "m07")
        esiti = st.leggi_esiti_mappa(tmp, f"{BTC}_M15", m.ingresso.studio["id"])
        check("F2. una scheda misurata nel notebook: il conto nel giornale (voce prova, dove = mappa) e l'esito nel "
              "file della mappa; rimisurarla non scrive prove, l'esito si aggiunge",
              tab7 is not None and righe_1 == 1 and _righe(giornale) == 1 and len(esiti) == 2
              and m.prove["mappa"] == {("M07", 1, 4.0): tab7.attrs["conto"]}
              and vt.fasce_mappa(m.storia) == tab7.attrs["conto"] and tab7b.attrs["conto"] == tab7.attrs["conto"])

        m_eth, _ = zitto(vm.apri_mappa, ETH, "M15", tmp, macchina="pc")
        giornale_eth = os.path.join(tmp, "studio", f"{ETH}_M15", "giornale_pc.jsonl")
        # 29/10/2026 (docs/77): M04 e M05 sono tolte; le fasce degeneri si provano su una scheda di prova a
        # quintili con il 60% dei valori uguali (come faceva M05 con lo spot uguale al perpetual)
        piatta = np.random.default_rng(3)
        mp.VARIABILI["_prova_piatta"] = lambda d, btc: pd.Series(
            np.where(piatta.random(len(d)) < 0.6, 0.0, piatta.normal(size=len(d))), index=d.index)
        SCHEDE["TQ"] = dataclasses.replace(SCHEDE["M07"], id="TQ", variabile="_prova_piatta", conta_segno_opposto=False)
        try:
            tab_q, testo_q = zitto(vm.mappa_di_una_scheda, m_eth, "TQ")
        finally:
            del SCHEDE["TQ"], mp.VARIABILI["_prova_piatta"]
        tolte = []
        for sid in ("M04", "M05"):
            try:
                zitto(vm.mappa_di_una_scheda, m_eth, sid)
                tolte.append("")
            except ValueError as e:
                tolte.append(str(e))
        check("F3. una scheda a quintili con il 60% dei valori uguali: si ferma prima di misurare, dice le quote delle "
              "fasce, non scrive niente; le schede tolte il 29/10/2026 (M04, M05) non si misurano più",
              tab_q is None and "non sono quintili veri" in testo_q and "Q1 " in testo_q
              and st.leggi_esiti_mappa(tmp, f"{ETH}_M15", m_eth.ingresso.studio["id"]) == []
              and _righe(giornale_eth) == 0 and all("sconosciuta" in t for t in tolte), str(tolte)[:120])

        tab6, testo6 = zitto(vm.mappa_di_una_scheda, m_eth, "M06")
        btc_usato = m_eth.btc[BTC]
        no_btc, testo_no = zitto(vm.mappa_di_una_scheda, m, "M06")
        check("F4. M06 su ETH: BTC dello stesso exchange e mercato, tagliato all'ultima barra dell'in-sample; su BTC "
              "non si misura e lo dice",
              tab6 is not None and len(tab6) == 5 and btc_usato.index[-1] <= m_eth.df_is.index[-1]
              and no_btc is None and "non si misura su BTC" in testo_no)

        # una misura di M05 fatta prima del 29/10 (la scheda di allora: quintili, 8 ore): voce ed esito nello studio
        m05_vecchia = dataclasses.replace(SCHEDE["M07"], id="M05", titolo="Basis estrema", orizzonte_ore=8,
                                          conta_segno_opposto=False)
        mp.registra(tmp, f"{BTC}_M15", "pc", m.ingresso.studio, m05_vecchia, tab7, "M15")
        vm._ricostruisci(m)
        tutte, testo_t = zitto(vm.tutte_le_schede, m)
        bozze, _ = zitto(vm.dalla_fascia_al_trigger, m)
        riep, _ = zitto(vm.riepilogo_mappa, m)
        check("F5. la 4 su BTC perp: M07 già fatta, M06 non si misura qui, le schede tolte non ci sono più: niente da "
              "misurare; la misura vecchia di M05 resta nel conto e nel riepilogo, in fondo, con la nota; la 5 e la 6 "
              "girano",
              tutte == {} and "già state misurate" in testo_t
              and vt.fasce_mappa(m.storia) == 2 * tab7.attrs["conto"]
              and isinstance(bozze, list) and len(riep) == 2 and riep["Scheda"].iloc[-1].startswith("M05")
              and riep["Meccanismo"].iloc[-1] == f"scheda tolta dal catalogo il {SCHEDE_TOLTE['M05']}"
              and riep["Fasce contate"].iloc[-1] == vt._fmt(tab7.attrs["conto"]))

        s = vt.Sessione()
        s.symbol, s.cartella, s.timeframe = BTC, tmp, "M15"
        dl = vt.apri_dati(BTC, "M15", tmp, confine="studio", macchina="pc")
        s.df_is, _ = vt.dividi_dati(dl, dl.df)
        s.storia, _, _ = vt._storia_dello_studio(dl, 41, lambda: s.prove)
        s.prove = s.storia.prove
        prima, righe_prima = copy.deepcopy(s.prove), _righe(giornale)
        tab_2b, _ = zitto(vt.mappa_del_dataset, s)
        soglia = vt._soglia_cumulata_lab(s, np.nan)
        contate = dict(zip(tab_2b["Scheda"].str[:3], tab_2b["Fasce contate"]))
        check("F6. la 2b del Lab, in sola lettura: mostra le schede di mappa_*.jsonl con le fasce contate, non cambia "
              "s.prove e non scrive nel giornale; la voce scritta dalla mappa si ritrova nella soglia del Lab",
              s.prove == prima and _righe(giornale) == righe_prima and len(tab_2b) == 2
              and contate["M07"] == vt._fmt(tab7.attrs["conto"])
              and soglia["mappa"] == vt.fasce_mappa(m.storia)
              and "fasce della mappa delle anomalie (schermata 2b)" in soglia["frase"]
              and "fasce della mappa" in s.tabelle["riga_prove"])

        s_eth = vt.Sessione()
        de = vt.apri_dati(ETH, "M15", tmp, confine="studio", macchina="pc")
        s_eth.df_is, _ = vt.dividi_dati(de, de.df)
        s_eth.storia, _, _ = vt._storia_dello_studio(de, 41, lambda: s_eth.prove)
        s_eth.prove = s_eth.storia.prove
        _, testo_vuoto = zitto(vt.mappa_del_dataset, s_eth)
        st.aggiungi_esito_mappa(tmp, f"{ETH}_M15", "colab", m_eth.ingresso.studio["id"],
                                mp.esito_da_salvare(SCHEDE["M07"], tab7, "M15"))
        tab_dopo, testo_dopo = zitto(vt.mappa_del_dataset, s_eth)
        check("F7. la 2b su un dataset con M06: una scheda misurata dopo la schermata 1 (anche da un'altra "
              "macchina) compare, e la 2b dice che entra nel conto alla prossima schermata 1",
              "M06" in testo_vuoto and len(tab_dopo) == 2
              and (tab_dopo["Fasce contate"] == "alla prossima schermata 1").sum() == 1
              and "riesegui la schermata 1" in testo_dopo)

    a = vt._soglia_da_conti(4, [3], [10], [], np.nan, schermate=True)
    b = vt._soglia_da_conti(4, [3], [10], [], np.nan, schermate=True, mappa=0)
    c = vt._soglia_da_conti(4, [3], [10], [], np.nan, schermate=True, mappa=7)
    r0, r7 = vt.soglia_cumulata(), vt.soglia_cumulata(mappa=7)
    check("F8. la soglia: con mappa = 0 tutto identico a prima (k, soglia, frase); con 7 fasce k sale di 7 e la "
          "frase le elenca; lo stesso nel notebook di ricerca (soglia_cumulata)",
          a["frase"] == b["frase"] and a["k"] == b["k"] == 17 and a["soglia"] == b["soglia"]
          and c["k"] == 24 and "7 fasce della mappa delle anomalie (schermata 2b)" in c["frase"]
          and r0["k"] == 0 and r7["k"] == 7 and "(schermata" not in r7["frase"]
          and vt.fasce_mappa({"mappa": {("M07", 1, 4.0): 10, ("M01", 1, 1.0): 98}}) == 108
          and vt.fasce_mappa({"trigger": 3}) == 0)
    rd.azzera()


def _ar1(rng, m: int, phi: float) -> np.ndarray:
    """Un AR(1) a varianza 1: x_t = phi x_(t-1) + rumore."""
    from scipy.signal import lfilter
    return lfilter([1.0], [1.0, -phi], rng.normal(size=m)) * np.sqrt(1.0 - phi ** 2)


def _prezzi(idx, rng, sigma=0.0015, volatilita_variabile=False) -> pd.DataFrame:
    """Un random walk senza nessun effetto; con volatilita_variabile, periodi agitati e calmi (volatilita' stocastica)."""
    n = len(idx)
    r = rng.normal(0.0, sigma, n)
    if volatilita_variabile:
        lv = 0.8 * _ar1(rng, n, 0.999)                 # log della volatilita', mezza vita circa 700 barre (7 giorni su M15)
        r = r * np.exp(lv - 0.32)                      # 0.32 = 0.8^2 / 2: la stessa varianza media
    close = 100.0 * np.exp(np.cumsum(r))
    op = np.r_[100.0, close[:-1]]
    return pd.DataFrame({"Open": op, "High": np.maximum(op, close) * 1.0005, "Low": np.minimum(op, close) * 0.9995,
                         "Close": close, "Volume": 1.0}, index=idx)


def sezione_g(check) -> None:
    """
    Senza nessun effetto, con variabili PERSISTENTI come quelle vere (richiesta di
    Mattia del 28/10/2026, prima di qualunque trigger dalla mappa): 1.000 mercati a
    seme fisso per variante (10 variabili x 100 mercati), M15 su 800 giorni. Con
    l'incertezza dei rendimenti sovrapposti senza sconto (mappa.errore_sovrapposti,
    decisione di Mattia del 28/10) «risponde» deve restare sotto il 15%. Con lo
    sconto di stagionalita.errore_standard_pesato la variante a dava 187 su 1.000.
    """
    u_neg = np.tile([1.0, -1.0], 50)                    # a lag 1 i prodotti sono tutti -1: varianza negativa
    se_neg, blocchi_neg = mp.errore_sovrapposti(u_neg, 2, 7)
    somme = np.r_[u_neg[:98].reshape(-1, 7).sum(axis=1), u_neg[98:].sum()]
    u_pos = np.array([1.0, 2.0, 0.5, -1.0, 3.0])
    atteso_pos = np.sqrt((u_pos ** 2).sum() + 2 * sum((u_pos[d:] * u_pos[:-d]).sum() for d in (1, 2)))
    se_pos, blocchi_pos = mp.errore_sovrapposti(u_pos, 3, 7)
    check("G1. l'incertezza della mappa: le coppie a meno di H barre pesano per intero (nessun peso decrescente); "
          "con la varianza negativa si passa ai blocchi di una settimana e lo si segna",
          blocchi_neg and np.isclose(se_neg, np.sqrt((somme ** 2).sum()))
          and not blocchi_pos and np.isclose(se_pos, atteso_pos),
          f"varianza a coppie {100 - 2 * 99} -> blocchi {se_neg:.2f}")
    idx = _indice("2022-01-03", giorni=800, minuti=15)
    n = len(idx)
    otto_ore = pd.date_range(idx[0], idx[-1], freq="8h")
    # 29/10/2026 (docs/77): M04 e M05 sono tolte; le stesse schede come schede di prova (fasce, attese, orizzonte
    # e riferimento di allora: gli stessi numeri di prima)
    m04 = _scheda(tipo="categorie", orizzonte_ore=24,              # categorie, 24 ore, stessa ora
                  categorie={-1.0: "funding sotto zero", 0.0: "funding fra zero e il livello di base",
                             1.0: "funding al livello di base", 2.0: "funding sopra il livello di base"},
                  attese={"funding sotto zero": 1, "funding sopra il livello di base": -1})
    m05_cat = _scheda(tipo="categorie", orizzonte_ore=8,
                      categorie={float(j): q for j, q in enumerate(QUINTILI)})   # 8 ore, fasce gia' fatte

    def variabile_a(rng):
        # costante a blocchi di 8 ore, AR(1) molto persistente sui pagamenti (mezza vita circa 11 giorni),
        # 4 categorie come M04: 15% sotto zero, 35% fra zero e il base, 35% al base, 15% sopra
        x8 = _ar1(rng, len(otto_ore), 0.98)
        soglie = np.quantile(x8, [0.15, 0.50, 0.85])
        cat8 = np.select([x8 < soglie[0], x8 < soglie[1], x8 < soglie[2]], [-1.0, 0.0, 1.0], 2.0)
        return pd.Series(cat8, index=otto_ore).reindex(idx, method="ffill")

    def variabile_b(rng):
        # AR(1) molto persistente sulle barre M15 (mezza vita circa 1.400 barre, 14 giorni), quintili sulle
        # barre dei 365 giorni prima, come M05
        cod = mp.fasce_quintili(pd.Series(_ar1(rng, n, 0.9995), index=idx), 365)
        return pd.Series(cod, index=idx)

    varianti = (("a", "variabile a blocchi di 8 ore, che cambia lentamente; 4 categorie come M04, orizzonte 24 ore",
                 m04, variabile_a, False),
                ("b", "variabile lenta sulle barre M15, quintili come M05, orizzonte 8 ore", m05_cat, variabile_b, False),
                ("c", "come b, con prezzi a volatilità variabile (periodi agitati e calmi)", m05_cat, variabile_b, True))
    for nome, testo, sch, fai_variabile, vv in varianti:
        risponde = opposto = 0
        for v in range(10):
            valori = fai_variabile(np.random.default_rng(7000 + 100 * ord(nome) + v))
            for k in range(100):
                rng = np.random.default_rng(50_000 + 10_000 * ord(nome) + 100 * v + k)
                verdetto = mp.misura(sch, _prezzi(idx, rng, volatilita_variabile=vv), PIP,
                                     valori=valori).attrs["verdetto"]
                risponde += verdetto == mp.RISPONDE
                opposto += verdetto == mp.OPPOSTO
        check(f"G{nome}. senza effetto, {testo}: «risponde» su 1.000 mercati sotto il 15%",
              risponde / 1000 < 0.15, f"«risponde» {risponde} su 1.000, «segno opposto» {opposto}")


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

    imposta_rollover(None)                       # mercato 24/7: nessuna quarantena, come gli exchange
    rng = np.random.default_rng(3)

    # =================================================================== A ==
    print("\nA · LE FASCE DALLE SOLE BARRE PASSATE\n" + "-" * 70)
    idx = _indice(giorni=500, minuti=60)
    s = pd.Series(rng.normal(size=len(idx)), index=idx)
    c = mp.fasce_quintili(s, 365)
    tagli = [len(idx) // 2, len(idx) - 500, len(idx) - 1]
    trunc_ok = all(np.array_equal(mp.fasce_quintili(s.iloc[: k + 1], 365), c[: k + 1], equal_nan=True) for k in tagli)
    s2 = s.copy()
    i = len(idx) - 100
    s2.iloc[i] = 1e9
    c2 = mp.fasce_quintili(s2, 365)
    check("A1. troncamento: tagliati i dati alla barra i, le fasce fino a i non cambiano; il valore della barra i "
          "non entra nelle sue soglie (un valore enorme va in Q5, le fasce prima restano uguali)",
          trunc_ok and c2[i] == 4 and np.array_equal(c2[:i], c[:i], equal_nan=True))
    pieno = idx >= idx[0] + pd.Timedelta(days=365)
    check("A2. finestra non piena = nessuna fascia; poi ogni barra ha una fascia; le 5 fasce quasi uguali",
          np.isnan(c[~pieno]).all() and np.isfinite(c[pieno]).all()
          and np.allclose(np.bincount(c[pieno].astype(int)) / pieno.sum(), 0.2, atol=0.03))
    piatta = pd.Series(1.0, index=idx[:9000])
    piatta.iloc[-2], piatta.iloc[-1] = 1.0, 1.0001
    cp = mp.fasce_quintili(piatta, 365)
    check("A3. un valore uguale alla soglia va sempre nella fascia sotto (Q1 se tutto il passato vale uguale)",
          cp[-2] == 0 and cp[-1] == 4)

    # =================================================================== B ==
    print("\nB · LA MISURA\n" + "-" * 70)
    idx_h = _indice(giorni=800, minuti=60)
    n = len(idx_h)
    var = pd.Series(rng.normal(size=n), index=idx_h)
    cod = mp.fasce_quintili(var, 365)
    h = 4
    q5 = np.flatnonzero(cod == 4)
    q3 = np.flatnonzero(cod == 2)
    M = Mercato(idx_h, seme=21)
    d_giu = M.df(_drift(n, q5, -0.0003, h))
    sch = _scheda(orizzonte_ore=4)
    tab = mp.misura(sch, d_giu, PIP, valori=var)
    ingresso = np.r_[d_giu["Open"].to_numpy()[1:], np.nan]
    fwd = in_unita(rendimenti_avanti(d_giu, h, PIP), "bp", PIP, prezzo=ingresso)
    ok = np.isfinite(fwd)
    rif = fasce_orarie(idx_h, "UTC")[0]
    b = media_per_fascia(fwd, rif, ok)
    pos = np.flatnonzero((cod == 4) & ok)
    a_mano = float(np.mean(fwd[pos] - b[pos]))
    r5 = tab.set_index("fascia").loc["Q5"]
    check("B1. un effetto noto in Q5 (giù) si ritrova: scarto dalla stessa ora uguale al conto a mano, negativo; "
          "Q5 risponde nel verso atteso; il verdetto della scheda è «risponde»",
          abs(r5["scarto_bp"] - a_mano) < 1e-9 and r5["scarto_bp"] < 0 and r5["esito"] == mp.RISPONDE
          and tab.attrs["verdetto"] == mp.RISPONDE and tab.attrs["H"] == 4,
          f"scarto Q5 {r5['scarto_bp']:.2f} bp, t {r5['t']:.1f}")
    d_su = M.df(_drift(n, q5, 0.0003, h))
    tab_o = mp.misura(sch, d_su, PIP, valori=var)
    check("B2. lo stesso effetto con il segno contrario: Q5 «segno opposto», che non conta come scoperta",
          tab_o.set_index("fascia").loc["Q5", "esito"] == mp.OPPOSTO and tab_o.attrs["verdetto"] == mp.OPPOSTO)
    d_q3 = M.df(_drift(n, q3, 0.0003, h))
    tab_f = mp.misura(_scheda(orizzonte_ore=4, attese={"Q5": 1}), d_q3, PIP, valori=var)
    check("B3. un effetto in una fascia non dichiarata (Q3): «fuori ipotesi», e non dà mai «risponde»",
          tab_f.set_index("fascia").loc["Q3", "esito"] == mp.FUORI and tab_f.attrs["verdetto"] != mp.RISPONDE)
    rare = pd.Series(np.nan, index=idx_h)
    rare.iloc[np.arange(9000, 9000 + 150 * 24, 24)] = 1.0          # 150 barre in 150 giorni
    fitte = pd.Series(np.nan, index=idx_h)
    fitte.iloc[9000: 9000 + 50 * 24: 4] = 1.0                       # 300 barre in 50 giorni
    sc_c = _scheda(tipo="categorie", categorie={1.0: "dentro"}, attese={"dentro": 1}, orizzonte_ore=4)
    t_r, t_f = mp.misura(sc_c, d_giu, PIP, valori=rare), mp.misura(sc_c, d_giu, PIP, valori=fitte)
    check("B4. i minimi: 150 barre (sotto 200) e 300 barre in 50 giornate (sotto 100) danno «troppo pochi casi», "
          "non misurate e non contate",
          t_r.attrs["verdetto"] == mp.POCHI and t_f.attrs["verdetto"] == mp.POCHI
          and t_r.attrs["misurate"] == 0 and t_f.attrs["misurate"] == 0
          and int(t_f["barre"].iat[0]) == 300 and int(t_f["giornate"].iat[0]) == 50)
    ora = pd.Series(idx_h.hour.astype(float), index=idx_h)
    sc_ora = _scheda(tipo="categorie", categorie={float(o): f"{o:02d}" for o in range(24)}, attese={"12": 1},
                     orizzonte_ore=4)
    tab_s = mp.misura(sc_ora, d_giu, PIP, valori=ora)
    tab_q = mp.misura(dataclasses.replace(sc_ora, riferimento=QUALUNQUE_ORA), d_giu, PIP, valori=ora)
    profilo = np.array([fwd[ok & (idx_h.hour == o)].mean() - fwd[ok].mean() for o in range(24)])
    check("B5. il riferimento: l'ora del giorno contro la stessa ora dà zero per costruzione; contro qualunque ora "
          "dà il profilo orario (media dell'ora meno media di tutte le barre)",
          np.allclose(tab_s["scarto_bp"].to_numpy(dtype=float), 0.0, atol=1e-9)
          and np.allclose(tab_q["scarto_bp"].to_numpy(dtype=float), profilo, atol=1e-9))
    # 27/10/2026 (correzione di Mattia, PR #82): fasce degeneri, come il funding fermo al livello di base
    piatto = var.copy()
    piatto.iloc[rng.choice(n, size=n // 2, replace=False)] = 0.0001
    c_piatto = mp.fasce_quintili(piatto, 365)
    motivo = mp.controlla_fasce(sch, c_piatto)
    try:
        mp.misura(sch, d_giu, PIP, valori=piatto)
        fermata = ""
    except mp.FasceDegeneri as e:
        fermata = str(e)
    check("B7. fasce degeneri: una variabile con metà dei valori uguali (le soglie coincidono) non si misura, e il "
          "messaggio dà la quota di ogni fascia; una variabile continua passa il controllo; le categorie non si "
          "controllano",
          motivo is not None and fermata == motivo and "Q1" in fermata and "%" in fermata
          and mp.controlla_fasce(sch, cod) is None and mp.controlla_fasce(sc_c, mp.codici_fasce(sc_c, rare)) is None,
          fermata[:110])
    # senza effetto: 1.000 mercati a seme fisso, le stesse fasce gia' calcolate (categorie 0..4)
    nulla = _a_categorie()
    valori0 = pd.Series(cod, index=idx_h)
    falsi = 0
    for seme in range(1000):
        if mp.misura(nulla, Mercato(idx_h, seme=1000 + seme).df(), PIP, valori=valori0).attrs["verdetto"] == mp.RISPONDE:
            falsi += 1
    check("B6. senza nessun effetto, su 1.000 mercati a seme fisso, «risponde» esce non più spesso del livello q "
          "(20%)", falsi / 1000 <= mp.Q_ROSA, f"{falsi} su 1.000")

    # =================================================================== C ==
    print("\nC · LE VARIABILI DELLE SCHEDE, IL CONFINE, GLI ORIZZONTI\n" + "-" * 70)
    idx15 = _indice(giorni=60, minuti=15)
    df15 = Mercato(idx15, seme=5).df()
    vecchie = ("funding_segno_prima_pagamento", "funding_liquidato", "funding_rispetto_al_base", "basis_bp")
    check("C1. le schede del funding e della basis (M01, M04, M05) sono tolte dal catalogo il 29/10/2026 (docs/77) e "
          "segnate in SCHEDE_TOLTE; le loro variabili non ci sono più, né prepara_df",
          not set(SCHEDE_TOLTE) & set(SCHEDE) and set(SCHEDE_TOLTE) == {"M01", "M04", "M05"}
          and not any(v in mp.VARIABILI for v in vecchie) and not hasattr(mp, "prepara_df")
          and all(s_.serve in ((), ("btc",)) for s_ in SCHEDE.values()))
    confine = idx15[3000]
    df_is = df15[df15.index < confine]
    btc = Mercato(idx15, seme=6).df()
    btc_buchi = btc.drop(btc.index[[1000, 2000]])
    btc_corto = btc[btc.index >= idx15[500]]
    sc = ind.scarto_btc_1h(df15, btc)
    r = lambda d: d["Close"] / d["Close"].shift(4) - 1                        # griglia piena: 4 barre = 1 ora
    a_mano6 = (r(btc) - r(df15)) * 10_000
    sb, sk = ind.scarto_btc_1h(df15, btc_buchi), ind.scarto_btc_1h(df15, btc_corto)
    buchi = {1000, 1004, 2000, 2004}
    check("C6. M06: lo scarto è il rendimento di BTC meno quello dell'altcoin nella stessa ora, rifatto a mano; una "
          "barra mancante in BTC dà NaN solo dove serve (la barra e quella un'ora dopo); un BTC più corto dà NaN "
          "prima del suo inizio",
          np.allclose(sc.to_numpy(), a_mano6.to_numpy(), equal_nan=True)
          and set(np.flatnonzero(sb.isna().to_numpy() & sc.notna().to_numpy())) == buchi
          and sk.iloc[:504].isna().all() and np.allclose(sk.iloc[504:], sc.iloc[504:]))
    sc_lungo = ind.scarto_btc_1h(df_is, btc)
    sc_corto = ind.scarto_btc_1h(df_is, btc[btc.index < confine])
    check("C7. M06: BTC dello stesso exchange e mercato (perpetual con perpetual, spot con spot); su BTC non si "
          "misura; le barre di BTC dopo il confine non cambiano niente nell'in-sample",
          mp.simbolo_btc("BINANCE_PERP_ETHUSDT") == "BINANCE_PERP_BTCUSDT"
          and mp.simbolo_btc("BYBIT_SPOT_SOLUSDT") == "BYBIT_SPOT_BTCUSDT"
          and errore(lambda: mp.simbolo_btc("BINANCE_PERP_BTCUSDT"), "è già BTC")
          and mp.adatta(SCHEDE["M06"], "BINANCE_PERP_BTCUSDT") is not None
          and mp.adatta(SCHEDE["M06"], "BYBIT_SPOT_XRPUSDT") is None
          and sc_lungo.equals(sc_corto))
    idx_h4 = _indice(giorni=30, minuti=240)
    check("C8. orizzonte che non è un numero intero di barre (1 ora su H4): la scheda non si misura, con il "
          "messaggio",
          errore(lambda: mp.barre_orizzonte(1, idx_h4), "non è un numero intero di barre")
          and mp.barre_orizzonte(4, idx_h4) == 1)
    check("C9. una scheda senza i dati che le servono si ferma e dice quali",
          errore(lambda: mp.variabile(SCHEDE["M06"], df15), "df_btc"))

    # =================================================================== D ==
    print("\nD · IL CONTO, I DOPPIONI, LO STUDIO\n" + "-" * 70)
    tab7 = mp.misura(dataclasses.replace(SCHEDE["M07"], orizzonte_ore=4), d_giu, PIP, valori=var)
    check("D1. il conto: una scheda con prove già viste le aggiunge (2 fasce + 96 = 98, come M01 prima del 29/10); "
          "M07 misura 5 fasce e ne conta 10 (il segno scelto dopo aver visto E39), e il verdetto guarda solo le "
          "fasce dell'inversione",
          mp.conto(_scheda(prove_extra=96), 2) == 98 and tab7.attrs["misurate"] == 5 and tab7.attrs["conto"] == 10
          and set(tab7.loc[tab7["attesa"] != "", "fascia"]) == {"Q5", "Q1"}
          and mp.conto(_scheda(), 4) == 4)
    base = pd.Series(rng.normal(size=n), index=idx_h)
    quasi = base + rng.normal(scale=0.05, size=n)
    altro = pd.Series(rng.normal(size=n), index=idx_h)
    c_base, c_quasi, c_altro = (mp.fasce_quintili(x, 365) for x in (base, quasi, altro))
    # la regola dei doppioni resta nel codice per le schede future: si prova su due schede di prova (TA doppione di TB)
    SCHEDE["TA"] = dataclasses.replace(_scheda(), id="TA", doppione_di="TB")
    SCHEDE["TB"] = dataclasses.replace(_scheda(), id="TB")
    try:
        fuori_d = mp.escluse_per_doppione({"TA": c_quasi, "TB": c_base})
        diverse = mp.escluse_per_doppione({"TA": c_altro, "TB": c_base})
        piatto_d = base.copy()
        piatto_d.iloc[rng.choice(n, size=n // 2, replace=False)] = 0.0001
        fuori_p = mp.escluse_per_doppione({"TA": mp.fasce_quintili(piatto_d, 365), "TB": c_base})
        fuori_p5 = mp.escluse_per_doppione({"TA": c_quasi, "TB": mp.fasce_quintili(piatto_d, 365)})
    finally:
        del SCHEDE["TA"], SCHEDE["TB"]
    check("D2. la regola dei doppioni (nella scheda, doppione_di): quasi uguali = la scheda non si misura (e lo dice); "
          "diverse = si misurano tutte e due. Nessuna scheda del catalogo la usa",
          set(fuori_d) == {"TA"} and "si misura solo TB" in fuori_d["TA"] and diverse == {}
          and all(s_.doppione_di is None for s_ in SCHEDE.values()))
    check("D2b. il controllo delle fasce viene prima dei doppioni: la scheda con le fasce degeneri esce con il suo "
          "motivo (non come doppione); se le fasce degeneri sono dell'altra, non si confronta con lei",
          set(fuori_p) == {"TA"} and "non sono quintili veri" in fuori_p["TA"]
          and set(fuori_p5) == {"TB"} and "non sono quintili veri" in fuori_p5["TB"])
    sch1 = dataclasses.replace(SCHEDE["M07"], orizzonte_ore=4)
    v1 = mp.voci_da_scrivere([], sch1, 10)
    v_rif = mp.voci_da_scrivere(v1, sch1, 10)
    sch2 = dataclasses.replace(sch1, versione=2)
    v2 = mp.voci_da_scrivere(v1, sch2, 10)
    check("D3. il conto nel giornale: la prima misura scrive la voce «prova» (dove = mappa); rimisurare uguale non "
          "scrive niente; una versione nuova della scheda scrive la prova e una risalita",
          [v["voce"] for v in v1] == ["prova"] and v1[0]["dove"] == "mappa" and v1[0]["n"] == 10
          and v_rif == [] and [v["voce"] for v in v2] == ["prova", "risalita"]
          and v2[1]["risalita"]["da"] == ["M07", 1, 4.0] and v2[1]["risalita"]["a"] == ["M07", 2, 4.0])
    with tempfile.TemporaryDirectory() as tmp:
        studio = {"id": "2026-10-27T00:00:00Z", "confine": "2025-06-10T16:00:00+00:00"}
        ds = "BINANCE_PERP_BTCUSDT_M15"
        scritte = mp.registra(tmp, ds, "pc", studio, sch1, tab7, "M15")
        di_nuovo = mp.registra(tmp, ds, "pc", studio, sch1, tab7, "M15")
        storia, _ = st.ricostruisci(tmp, ds, studio)
        esiti = st.leggi_esiti_mappa(tmp, ds, studio["id"])
        altro_studio = st.leggi_esiti_mappa(tmp, ds, "un altro studio")
        check("D4. lo studio: il conto si ritrova nel registro del dataset (prove['mappa']); rimisurare non conta "
              "di nuovo; ogni misura resta nel file degli esiti (mappa_pc.jsonl), con le fasce e il verdetto",
              len(scritte) == 1 and di_nuovo == []
              and storia.prove.get("mappa") == {("M07", 1, 4.0): 10}
              and len(esiti) == 2 and esiti[0]["scheda"] == "M07" and esiti[0]["conto"] == 10
              and len(esiti[0]["fasce"]) == 5 and esiti[0]["verdetto"] == tab7.attrs["verdetto"]
              and altro_studio == [])
        tab_meno = tab7.copy()
        tab_meno.attrs.update(tab7.attrs, misurate=4, conto=8)     # rimisura con una fascia sotto i minimi
        meno = mp.registra(tmp, ds, "pc", studio, sch1, tab_meno, "M15")
        storia2, _ = st.ricostruisci(tmp, ds, studio)
        check("D5. il conto non scende mai: una rimisura con una fascia in meno (8 invece di 10) non scrive niente "
              "nel giornale e il conto resta 10; l'esito nuovo resta nel file degli esiti",
              meno == [] and mp.voci_da_scrivere(v1, sch1, 8) == []
              and storia2.prove.get("mappa") == {("M07", 1, 4.0): 10}
              and len(st.leggi_esiti_mappa(tmp, ds, studio["id"])) == 3)
    rd.azzera()

    # =================================================================== E ==
    print("\nE · LE SCHEDE APPROVATE (docs/74; dal 29/10 senza M01, M04, M05)\n" + "-" * 70)
    attese = {"M06": (1, STESSA_ORA, "quintili", 0, False), "M07": (4, STESSA_ORA, "quintili", 0, True)}
    coerenti = all((s_.orizzonte_ore, s_.riferimento, s_.tipo, s_.prove_extra, s_.conta_segno_opposto) == attese[k]
                   and s_.approvata == "27/10/2026" and s_.variabile in mp.VARIABILI
                   and set(s_.attese) <= set(s_.fasce) for k, s_ in SCHEDE.items())
    check("E1. in engine/ipotesi.py le schede approvate rimaste (M06, M07), con orizzonte, riferimento, fasce e conto "
          "di docs/74 (M02 e M03 fuori; M01, M04 e M05 tolte il 29/10/2026)", set(SCHEDE) == set(attese) and coerenti
          and SCHEDE["M06"].escludi_monete == ("BTC",) and SCHEDE["M06"].variabile == "scarto_btc_1h"
          and SCHEDE["M07"].attese == {"Q5": -1, "Q1": 1} and SCHEDE["M06"].attese == {"Q5": 1, "Q1": -1})

    # =================================================================== F ==
    print("\nF · IL NOTEBOOK DELLA MAPPA, LA 2b DEL LAB, LA SOGLIA (PR B2)\n" + "-" * 70)
    sezione_f(check)

    # =================================================================== G ==
    print("\nG · SENZA EFFETTO, CON VARIABILI PERSISTENTI (28/10/2026)\n" + "-" * 70)
    sezione_g(check)

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
