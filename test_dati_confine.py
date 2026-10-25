"""
Suite di validazione dei DATI IN LOCALE e del CONFINE DELLO STUDIO (26/10/2026,
docs/70, parte A: engine e test). Moduli: engine/aggiorna_dati.py,
engine/studio.py, le aggiunte di engine/splitting.py (confine_da_quota,
split_al_confine) e di engine/registro_dataset.py (da_voci, metti, normale,
a_tupla, annota_oos con oos_fino_al), scarica_dati_crypto.py che usa le
funzioni spostate.

Cosa verifica (i numeri sono quelli del docs/70 §8)
-------------
A  l'aggiornamento con un exchange FINTO (nessuna rete): incrementale (1), solo
   barre chiuse (2), ripresa dopo un'interruzione (3), rete giu' (4), lo script
   e il Lab danno lo stesso file, funding e spot del perpetual, sola lettura (22);
B  il confine: fisso con barre nuove (5), uguale alla regola dell'80% sui CSV
   veri (6), unico fra timeframe (7) e fra dataset (8), l'impronta (9), il CSV
   piu' corto del confine (10), Colab senza studio (18), il taglio al funding (20);
C  i giornali: il riavvio simulato (11), due macchine (12), le copie di
   conflitto di Drive (13), l'id dello studio (14), il diario fra dataset (15);
D  il reset (16), la contaminazione su tutto lo studio (17), la scrittura
   sicura (21), il confine riportato indietro solo su uno studio intatto (22,
   correzione del 26/10).
Il punto 19 (prepara con confine="80%") e' della parte B.

Come si lancia (da terminale, dalla cartella del progetto):

    python test_dati_confine.py

Non serve la rete. Il punto 6 usa i CSV veri di dati/ se ci sono.
Alla fine stampa «RISULTATO: N/N test superati».
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.simplefilter("ignore")

from engine import aggiorna_dati as AD
from engine import exchange as X
from engine import registro_dataset as RD
from engine import studio as ST
from engine.splitting import confine_da_quota, split_al_confine, split_is_oos

QUI = os.path.dirname(os.path.abspath(__file__))
DATI = os.path.join(QUI, "dati")
H4 = pd.Timedelta(hours=4)


def muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def storico(inizio, fine=None, periodi=None, passo="4h", prezzo=30000.0, seme=7):
    """Un random walk 24/7 con OHLC coerenti e volume > 0."""
    if periodi is None:
        idx = pd.date_range(inizio, fine, freq=passo, tz="UTC")
    else:
        idx = pd.date_range(inizio, periods=periodi, freq=passo, tz="UTC")
    # un generatore per colonna: con piu' barre, le prime restano identiche (storici che «crescono»)
    g = [np.random.default_rng(seme * 10 + k) for k in range(4)]
    close = prezzo * np.exp(np.cumsum(g[0].normal(0, 0.01, len(idx))))
    open_ = np.r_[prezzo, close[:-1]]
    alto = np.maximum(open_, close) * (1 + np.abs(g[1].normal(0, 0.002, len(idx))))
    basso = np.minimum(open_, close) * (1 - np.abs(g[2].normal(0, 0.002, len(idx))))
    # 2 decimali sui prezzi, 3 sul volume, come i CSV veri: con decimali lunghi read_csv non rilegge
    # al bit quello che ha scritto (sui CSV veri si', controllo B6c)
    return pd.DataFrame({"Open": open_.round(2), "High": alto.round(2), "Low": basso.round(2),
                         "Close": close.round(2), "Volume": g[3].uniform(1, 100, len(idx)).round(3)},
                        index=idx.rename("Date"))


class Finto:
    """
    Un exchange come ccxt, senza rete: fetch_ohlcv (dal `since` in avanti, al
    massimo `limit` barre), fetch_funding_rate_history (in avanti da since,
    come Binance) e load_markets. Registra ogni funzione chiamata. guasto_dopo:
    dalla chiamata N+1 di fetch_ohlcv ogni richiesta fallisce.
    """
    def __init__(self, df, ident="binanceusdm", funding=None, guasto_dopo=None, sempre_giu=False):
        self.id = ident
        self.ms = (pd.DatetimeIndex(df.index).as_unit("ns").asi8 // 1_000_000).astype(np.int64)
        self.v = df[["Open", "High", "Low", "Close", "Volume"]].to_numpy()
        self.funding = funding
        self.guasto_dopo, self.sempre_giu = guasto_dopo, sempre_giu
        self.chiamate, self.funzioni = 0, []

    def load_markets(self):
        self.funzioni.append("load_markets")
        return {}

    def fetch_ohlcv(self, simbolo, tf, since=None, limit=1000):
        self.funzioni.append("fetch_ohlcv")
        self.chiamate += 1
        if self.sempre_giu or (self.guasto_dopo is not None and self.chiamate > self.guasto_dopo):
            raise RuntimeError("NetworkError: exchange irraggiungibile")
        i = int(np.searchsorted(self.ms, since))
        return [[int(self.ms[k]), *map(float, self.v[k])] for k in range(i, min(i + limit, len(self.ms)))]

    def fetch_funding_rate_history(self, simbolo, since=None, limit=None, params=None):
        self.funzioni.append("fetch_funding_rate_history")
        if self.sempre_giu:
            raise RuntimeError("NetworkError: exchange irraggiungibile")
        ms = (pd.DatetimeIndex(self.funding.index).as_unit("ns").asi8 // 1_000_000).astype(np.int64)
        sel = np.flatnonzero(ms >= since)[: int(limit)]
        return [{"timestamp": int(ms[k]), "fundingRate": float(self.funding["tasso"].iloc[k])} for k in sel]


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def saltato(nome, motivo):
        print(f"  [SALTATO] {nome}  — {motivo}")

    def errore(f, tipo=Exception, testo=""):
        try:
            muto(f)
        except tipo as e:
            return testo in str(e)
        return False

    radice = Path(tempfile.mkdtemp(prefix="test_dati_confine_"))

    def cartella(nome):
        p = radice / nome
        p.mkdir(parents=True, exist_ok=True)
        return p

    adesso = pd.Timestamp.now(tz="UTC")
    # la fonte H4 dal 2/1/2020 fino alla barra in corso compresa (che NON deve entrare)
    fonte = storico("2020-01-02", adesso.floor("4h").tz_convert(None))
    chiuse = fonte[fonte.index + H4 <= adesso]
    SYM = "BINANCE_PERP_BTCUSDT"

    try:
        # ----------------------------------------------------- aggiornamento --
        print("\nA · L'aggiornamento, con un exchange finto (nessuna rete)")
        c1 = cartella("a1")
        X.salva_csv(chiuse.iloc[:1000], c1 / f"{SYM}_H4.csv")
        prima = X.leggi_csv(c1 / f"{SYM}_H4.csv")
        r = muto(AD.aggiorna_storico, SYM, "H4", c1, aperti={"binanceusdm": Finto(fonte)}, limite=100,
                 salva_ogni=5)
        dopo = X.leggi_csv(c1 / f"{SYM}_H4.csv")
        check("A1. incrementale: il CSV ha tutte le barre chiuse della fonte, nessuna doppia",
              len(dopo) == len(chiuse) and dopo.index.equals(chiuse.index) and dopo.index.is_unique
              and r["nuove"] == len(chiuse) - 1000, f"{len(dopo):,} barre, +{r['nuove']:,}")
        check("A1b. le prime 1.000 barre identiche al bit a quelle di prima",
              dopo.iloc[:1000].equals(prima))
        check("A1c. i prezzi sono quelli della fonte",
              np.allclose(dopo.to_numpy(), chiuse.to_numpy(), rtol=1e-12, atol=0))
        r2 = muto(AD.aggiorna_storico, SYM, "H4", c1, aperti={"binanceusdm": Finto(fonte)}, limite=100)
        check("A1d. una seconda chiamata subito dopo non aggiunge niente",
              r2["nuove"] == 0 and X.leggi_csv(c1 / f"{SYM}_H4.csv").equals(dopo))
        check("A2. solo barre chiuse: la barra in corso non entra",
              dopo.index[-1] + H4 <= adesso and fonte.index[-1] not in dopo.index,
              f"ultima {dopo.index[-1]:%d/%m/%Y %H:%M}")

        # una tappa = 20 blocchi da 100 barre = 2.000 barre; guasto alla chiamata 51
        c3 = cartella("a3")
        rotto = Finto(fonte, guasto_dopo=50)
        check("A3. ripresa: un guasto a meta' del download completo fa salire l'errore",
              errore(lambda: AD.aggiorna_storico(SYM, "H4", c3, aperti={"binanceusdm": rotto}, limite=100,
                                                 salva_ogni=20, attesa=0.001), RuntimeError, "irraggiungibile"))
        parziale = X.leggi_csv(c3 / f"{SYM}_H4.csv")
        check("A3b. ... ma le tappe finite sono gia' nel file (2 tappe = 4.000 barre)",
              len(parziale) == 4000 and parziale.index.equals(chiuse.index[:4000]), f"{len(parziale):,} barre")
        muto(AD.aggiorna_storico, SYM, "H4", c3, aperti={"binanceusdm": Finto(fonte)}, limite=100, salva_ogni=20)
        intero = cartella("a3b")
        muto(AD.aggiorna_storico, SYM, "H4", intero, aperti={"binanceusdm": Finto(fonte)}, limite=100,
             salva_ogni=20)
        check("A3c. il giro dopo completa: identico a un download senza interruzioni",
              (c3 / f"{SYM}_H4.csv").read_bytes() == (intero / f"{SYM}_H4.csv").read_bytes())
        un_colpo = X.scarica_storico(SYM, "H4", da=AD.INIZIO, ex=Finto(fonte), limite=100, verbose=False)
        check("A3d. a tappe o in una richiesta sola, le stesse barre",
              X.leggi_csv(intero / f"{SYM}_H4.csv").index.equals(un_colpo.index))

        # lo script usa le funzioni dell'engine: stesso file
        import scarica_dati_crypto as SDC
        c_script = cartella("script")
        vecchia = SDC.CARTELLA
        try:
            SDC.CARTELLA = c_script
            muto(SDC.aggiorna, SYM, "H4", {"binanceusdm": Finto(fonte)})
        finally:
            SDC.CARTELLA = vecchia
        c_lab = cartella("lab_h4")
        muto(AD.aggiorna_storico, SYM, "H4", c_lab, aperti={"binanceusdm": Finto(fonte)})
        check("A3e. scarica_dati_crypto.py e il Lab scrivono lo stesso CSV",
              (c_script / f"{SYM}_H4.csv").read_bytes() == (c_lab / f"{SYM}_H4.csv").read_bytes())

        # il Lab con l'interruttore acceso: candele, spot e funding del perpetual
        orari = pd.date_range("2019-12-25", adesso.tz_convert(None), freq="8h", tz="UTC")
        funding = pd.DataFrame({"tasso": np.random.default_rng(3).normal(1e-4, 5e-5, len(orari))}, index=orari)
        c_per = cartella("perp")
        X.salva_csv(chiuse.iloc[:-30], c_per / f"{SYM}_H4.csv")
        X.salva_csv(chiuse.iloc[:-30], c_per / "BINANCE_SPOT_BTCUSDT_H4.csv")
        X.salva_funding(X.con_intervalli(funding.iloc[:-20]), c_per / f"{SYM}_FUNDING.csv")
        perp, spot = Finto(fonte, funding=funding), Finto(fonte, ident="binance")
        rep = muto(AD.aggiorna_per_lab, SYM, "H4", c_per, aperti={"binanceusdm": perp, "binance": spot})
        check("A4. aggiorna_per_lab: candele +30, spot +30, funding aggiornato, controlli sulle barre nuove",
              rep["candele"]["esito"] == "aggiornato" and rep["candele"]["nuove"] == 30
              and rep["spot"]["nuove"] == 30 and rep["funding"]["esito"] == "aggiornato"
              and rep["funding"]["nuove"] > 0 and rep["candele"]["controlli"]["barre"] == 31
              and rep["candele"]["controlli"]["buchi"] == 0,
              f"funding +{rep['funding']['nuove']}")
        giu = Finto(fonte, sempre_giu=True)
        prima_b = (c_per / f"{SYM}_H4.csv").read_bytes()
        rep_g = muto(AD.aggiorna_per_lab, SYM, "H4", c_per,
                     aperti={"binanceusdm": giu, "binance": Finto(fonte, ident="binance", sempre_giu=True)},
                     attesa=0.001)
        check("A4b. rete giu': non si ferma, ogni parte «non aggiornato» con il motivo, CSV invariato",
              all(v["esito"] == "non aggiornato" and "irraggiungibile" in v["errore"] for v in rep_g.values())
              and (c_per / f"{SYM}_H4.csv").read_bytes() == prima_b)
        check("A4c. rete giu' e CSV che non c'e': si ferma e dice perche'",
              errore(lambda: AD.aggiorna_per_lab(SYM, "M15", c_per, aperti={"binanceusdm": giu}, attesa=0.001),
                     FileNotFoundError, "non sono riuscito a scaricarlo"))
        consentite = {"load_markets", "fetch_ohlcv", "fetch_funding_rate_history"}
        usate = set(perp.funzioni) | set(spot.funzioni) | set(giu.funzioni)
        check("A22. sola lettura: solo fetch_ohlcv e fetch_funding_rate_history (e load_markets)",
              usate <= consentite and "fetch_ohlcv" in usate, ", ".join(sorted(usate)))
        check("A23. lo spot di un perpetual e' della stessa coppia e dello stesso exchange; spot -> None",
              AD.spot_della_coppia("BYBIT_PERP_ETHUSDT") == "BYBIT_SPOT_ETHUSDT"
              and AD.spot_della_coppia("BYBIT_SPOT_ETHUSDT") is None)

        # ------------------------------------------------------------ confine --
        print("\nB · Il confine dello studio")
        h1 = storico("2024-01-01", periodi=1000, passo="1h")
        cb = cartella("b5")
        ing = ST.entra(cb, "BINANCE_PERP_BTCUSDT", "H1", h1, "pc", adesso="2026-10-26 10:00")
        check("B5. lo studio si apre al primo dataset: confine = fine della barra 800 (80%)",
              ing.aperto_ora and ing.confine == h1.index[799] + pd.Timedelta(hours=1)
              and len(ing.df_is) == 800 and ing.esito_impronta == "nuova", f"{ing.confine}")
        piu = storico("2024-01-01", periodi=1300, passo="1h")
        ing2 = ST.entra(cb, "BINANCE_PERP_BTCUSDT", "H1", piu, "pc")
        check("B5b. +300 barre: in-sample identico al bit, out-of-sample 500 barre, confine fermo",
              not ing2.aperto_ora and ing2.df_is.equals(ing.df_is) and len(ing2.df_oos) == 500
              and ing2.confine == ing.confine and ing2.esito_impronta == "ok")
        for s_vero in ("BINANCE_PERP_BTCUSDT", "BYBIT_SPOT_ETHUSDT"):
            f = os.path.join(DATI, f"{s_vero}_M15.csv")
            if not os.path.exists(f):
                saltato(f"B6. {s_vero}", "il CSV non c'e' in dati/")
                continue
            df = X.leggi_csv(f)
            a, b = split_is_oos(df, 0.8)
            c, d = split_al_confine(df, confine_da_quota(df, "15min", 0.8), "15min")
            check(f"B6. {s_vero} M15 vero: il confine dell'80% da' gli stessi pezzi di split_is_oos",
                  a.equals(c) and b.equals(d), f"confine {a.index[-1] + pd.Timedelta('15min')}")
            copia = radice / f"{s_vero}.csv"
            X.salva_csv(df, copia)
            check(f"B6c. {s_vero}: salvare e rileggere il CSV vero non cambia un bit (l'impronta regge agli aggiornamenti)",
                  X.leggi_csv(copia).equals(df) and ST.impronta(X.leggi_csv(copia)) == ST.impronta(df))
        conf = pd.Timestamp("2024-01-10 01:00", tz="UTC")
        ultime = {tf: split_al_confine(storico("2024-01-01", periodi=n, passo=p), conf, p)[0].index[-1]
                  for tf, n, p in (("M15", 2000, "15min"), ("H1", 500, "1h"), ("H4", 200, "4h"))}
        check("B7. confine alle 01:00: ultima barra in-sample M15 00:45, H1 00:00, H4 20:00 del giorno prima",
              ultime == {"M15": pd.Timestamp("2024-01-10 00:45", tz="UTC"),
                         "H1": pd.Timestamp("2024-01-10 00:00", tz="UTC"),
                         "H4": pd.Timestamp("2024-01-09 20:00", tz="UTC")})
        dopo_b = storico("2024-01-20", periodi=1300 - 19 * 24, passo="1h", seme=9)
        ing_b = ST.entra(cb, "BYBIT_SPOT_ETHUSDT", "H1", dopo_b, "pc")
        attesa_q = (800 - 19 * 24) / len(dopo_b)
        check("B8. un dataset che parte piu' tardi usa lo stesso confine; quota calcolata a mano",
              ing_b.confine == ing.confine and np.isclose(ing_b.quota_is, attesa_q)
              and len(ing_b.df_is) == 800 - 19 * 24, f"in-sample {ing_b.quota_is:.1%}")
        tardi = storico("2024-01-30", periodi=1300 - 29 * 24, passo="1h", seme=11)
        ing_t = ST.entra(cb, "BYBIT_SPOT_SOLUSDT", "H1", tardi, "pc")
        check("B8b. in-sample sotto il 50%: avviso «corto»; out-of-sample oltre il 30%: suggerisce il reset",
              ing_t.is_corto and ing_t.suggerisci_reset and not ing2.is_corto and ing2.suggerisci_reset
              and not ing.suggerisci_reset, f"{ing_t.quota_is:.1%}")
        toccato = piu.copy()
        toccato.iloc[100, toccato.columns.get_loc("Close")] *= 1.0001
        check("B9. impronta: un Close dell'in-sample cambiato -> si ferma e dice cosa",
              errore(lambda: ST.entra(cb, "BINANCE_PERP_BTCUSDT", "H1", toccato, "pc"), ValueError,
                     "non sono più quelle"))
        fuori = piu.copy()
        fuori.iloc[1200, fuori.columns.get_loc("Close")] *= 1.01
        check("B9b. un Close dell'out-of-sample cambiato -> nessun effetto",
              ST.entra(cb, "BINANCE_PERP_BTCUSDT", "H1", fuori, "pc").esito_impronta == "ok")
        check("B10. CSV piu' corto del confine (copia vecchia) -> si ferma",
              errore(lambda: ST.entra(cb, "BINANCE_PERP_BTCUSDT", "H1", h1.iloc[:700], "pc"), ValueError,
                     "finiscono prima del confine"))
        vuota = cartella("b18")
        check("B18. Colab senza studio -> si ferma con il messaggio del docs/70 §12.1",
              errore(lambda: ST.entra(vuota, "BINANCE_PERP_BTCUSDT", "H1", h1, "colab"), FileNotFoundError,
                     "Su Drive non c'è lo studio") and not (vuota / "studio").exists())
        ing_c = ST.entra(cb, "BINANCE_SPOT_XRPUSDT", "H1", piu, "colab")
        check("B18b. con lo studio aperto sul PC, un dataset nuovo entra anche da Colab",
              ing_c.confine == ing.confine and ing_c.esito_impronta == "nuova")

        fh = X.con_intervalli(pd.DataFrame({"tasso": [1e-4] * 9},
                                           index=pd.date_range("2024-01-01", periods=9, freq="8h", tz="UTC")))
        barre = storico("2024-01-01", periodi=100, passo="1h")
        tenuto, tagliate, fino = ST.taglia_al_funding(barre, fh, "2024-01-02 00:00", "H1")
        check("B20. funding fino al 3/1 16:00 (ogni 8 ore): si tengono le barre fino alle 23:00, 28 fuori",
              len(tenuto) == 72 and tagliate == 28 and fino == pd.Timestamp("2024-01-03 23:00", tz="UTC"))
        check("B20b. funding che copre tutto: nessun taglio",
              ST.taglia_al_funding(barre.iloc[:60], fh, "2024-01-02 00:00", "H1")[1] == 0)
        check("B20c. il funding non copre l'in-sample -> si ferma",
              errore(lambda: ST.taglia_al_funding(barre, fh, "2024-01-04 06:00", "H1"), ValueError,
                     "non copre l'in-sample"))

        # ----------------------------------------------------------- giornali --
        print("\nC · I giornali: solo in aggiunta, un file per macchina")
        cg = cartella("c11")
        st = ST.entra(cg, "BINANCE_PERP_BTCUSDT", "H1", piu, "pc", adesso="2026-10-26 09:00").studio
        ds = "BINANCE_PERP_BTCUSDT_H1"
        RD.azzera()
        t0 = pd.Timestamp("2026-10-26 10:00", tz="UTC")
        n = [0]

        def scrivi(voce, macchina="pc"):
            n[0] += 1
            ST.aggiungi_voce(cg, ds, macchina, st["id"], voce, quando=t0 + pd.Timedelta(seconds=n[0]))

        s, _ = RD.apri("BINANCE_PERP_BTCUSDT", "H1", st["confine"], 41,
                       nuove_prove=lambda: {"trigger": 0, "uscite": {}, "filtri": {}, "combinazioni": {}})
        scrivi({"voce": "orizzonte", "H": 41})
        scritte = {"trigger": 0, "uscite": {}, "filtri": {}, "combinazioni": {}}
        s.prove["trigger"] = 12
        s.prove["uscite"][(("E21",), (), 41, 41, 90, None, "barre", None, None)] = 87
        s.prove.setdefault("celle", {})[(41, ("ora", "basis"), ("C1", "C2"))] = 16
        for v in ST.voci_prove(scritte, s.prove):
            scrivi(v)
        scelte = {"H": 41, "trigger_long": ("E21",), "trigger_short": (), "cella": (None, None),
                  "uscite": ("E21", 41, None), "sistema": "Long + Short", "filtri": ("F1", "F2")}
        RD.annota_oos(s, scelte, oos_fino_al=piu.index[-1])
        scrivi({"voce": "oos", "voce_diario": s.diario[-1]})
        RD.apri("BINANCE_PERP_BTCUSDT", "H1", st["confine"], 25)
        scrivi({"voce": "orizzonte", "H": 25}, "colab")
        RD.annota_risalita(s, "cella", da=(None, None), a=("CELLA_X_L", None))
        scrivi({"voce": "risalita", "risalita": s.risalite[-1]}, "colab")
        prima_p = {k: (dict(v) if isinstance(v, dict) else v) for k, v in s.prove.items()}
        s.prove["uscite"][(("E21",), (), 25, 25, 90, None, "barre", None, None)] = 87
        s.prove["trigger"] = 14
        for v in ST.voci_prove(prima_p, s.prove):
            scrivi(v, "colab")
        RD.annota_oos(s, scelte, oos_fino_al=piu.index[-1])
        scrivi({"voce": "oos", "voce_diario": s.diario[-1]})
        RD.azzera()
        r_s, info = ST.ricostruisci(cg, ds, st)
        check("C11. riavvio simulato: H provati, H corrente e conto delle prove identici (chiavi composte comprese)",
              r_s.h_provati == [41, 25] and r_s.h_corrente == 25 and r_s.prove == s.prove,
              f"{len(s.prove['uscite'])} uscite, {len(s.prove['celle'])} celle")
        check("C11b. diario e risalite identici (nella forma del JSON), anche la risalita di H",
              RD.normale(r_s.diario) == RD.normale(s.diario) and RD.normale(r_s.risalite) == RD.normale(s.risalite)
              and [r["cosa"] for r in r_s.risalite] == ["H", "cella"])
        check("C11c. la storia ricostruita torna nel registro in memoria",
              RD.storia("BINANCE_PERP_BTCUSDT", "H1", st["confine"]) is r_s)
        rilette = {k: v for k, v in r_s.diario[0].items() if k not in ("quando", "oos_fino_al")}
        check("C11d. dopo la rilettura «stesse scelte» si riconosce (liste del JSON = tuple di prima, normalizzate)",
              rilette == RD.normale(scelte) and rilette != scelte)
        check("C11e. voci_prove scrive solo cio' che e' cambiato",
              ST.voci_prove(s.prove, s.prove) == [] and len(ST.voci_prove(prima_p, s.prove)) == 2)

        file_pc = (cg / "studio" / ds / "giornale_pc.jsonl").read_text(encoding="utf-8").splitlines()
        file_colab = (cg / "studio" / ds / "giornale_colab.jsonl").read_text(encoding="utf-8").splitlines()
        check("C12. due macchine: ogni file ha solo le righe della sua macchina",
              all(json.loads(x)["macchina"] == "pc" for x in file_pc)
              and all(json.loads(x)["macchina"] == "colab" for x in file_colab) and len(file_colab) == 4)
        # gli stessi giornali scritti in un altro ordine (prima tutto Colab, poi il PC) in un altro studio
        cg2 = cartella("c12")
        shutil.copytree(cg / "studio", cg2 / "studio")
        g = cg2 / "studio" / ds
        (g / "giornale_pc.jsonl").unlink()
        (g / "giornale_colab.jsonl").unlink()
        for nome, righe in (("giornale_colab.jsonl", file_colab[::-1]), ("giornale_pc.jsonl", file_pc[::-1])):
            (g / nome).write_text("\n".join(righe) + "\n", encoding="utf-8")
        r2_s, _ = ST.ricostruisci(cg2, ds, st)
        check("C12b. righe in un altro ordine nei file: lo stesso registro",
              r2_s.prove == r_s.prove and r2_s.h_provati == r_s.h_provati
              and RD.normale(r2_s.diario) == RD.normale(r_s.diario))
        extra = json.loads(file_pc[0])
        extra.update({"voce": "prova", "dove": "filtri", "chiave": ["X"], "n": 3,
                      "quando": (t0 + pd.Timedelta(minutes=5)).isoformat()})
        (g / "giornale_pc (1).jsonl").write_text(json.dumps(extra) + "\n", encoding="utf-8")
        r3_s, info3 = ST.ricostruisci(cg2, ds, st)
        check("C13. una copia di conflitto di Drive si legge lo stesso e si segnala",
              info3["copie"] == ["giornale_pc (1).jsonl"] and r3_s.prove["filtri"] == {("X",): 3})
        check("C13b. nome della macchina non valido -> si ferma",
              errore(lambda: ST.aggiungi_voce(cg, ds, "PC di Mattia", st["id"], {"voce": "orizzonte", "H": 1}),
                     ValueError, "non valido"))
        ST.entra(cg, "BYBIT_SPOT_ETHUSDT", "H1", piu, "pc")
        ST.aggiungi_voce(cg, "BYBIT_SPOT_ETHUSDT_H1", "pc", st["id"], {"voce": "oos", "voce_diario": {"H": 41}})
        check("C15. il diario fra dataset: su ETH «2 aperture su BTC», su BTC «1 su ETH»",
              ST.diario_altrove(cg, "BYBIT_SPOT_ETHUSDT_H1", st) == {"BINANCE_PERP_BTCUSDT_H1": 2}
              and ST.diario_altrove(cg, ds, st) == {"BYBIT_SPOT_ETHUSDT_H1": 1})

        # -------------------------------------------------------------- reset --
        print("\nD · Il reset")
        oggi, campo = "2026-10-26", "26/10/2026"
        check("D16. campo vuoto, Colab, data non valida, data non di oggi: nessun reset",
              ST.reset(cg, "", "BINANCE_PERP_BTCUSDT", "H1", piu, "pc", oggi=oggi)["esito"] == "vuoto"
              and ST.reset(cg, campo, "BINANCE_PERP_BTCUSDT", "H1", piu, "colab", oggi=oggi)["esito"] == "ignorato_colab"
              and ST.reset(cg, "26-10", "BINANCE_PERP_BTCUSDT", "H1", piu, "pc", oggi=oggi)["esito"] == "data_non_valida"
              and ST.reset(cg, "25/10/2026", "BINANCE_PERP_BTCUSDT", "H1", piu, "pc", oggi=oggi)["esito"]
              == "data_non_di_oggi" and ST.leggi_confine(cg)["id"] == st["id"])
        check("D16b. senza studio: niente da ricalcolare (lo apre entra)",
              ST.reset(cartella("d16"), campo, "BINANCE_PERP_BTCUSDT", "H1", piu, "pc", oggi=oggi)["esito"]
              == "nessuno_studio")
        check("D16c. senza barre nuove (confine nuovo = vecchio): nessun reset",
              ST.reset(cb, campo, "BINANCE_PERP_BTCUSDT", "H1", h1, "pc", oggi=oggi)["esito"]
              == "nessuna_barra_nuova")
        # lo studio cg e' aperto su `piu` (1.300 barre): confine alla fine della barra 1.040.
        # Con 1.600 barre il confine nuovo e' alla fine della barra 1.280
        ancora = storico("2024-01-01", periodi=1600, passo="1h")
        vecchio_c = ST.leggi_confine(cg)
        rr = ST.reset(cg, campo, "BINANCE_PERP_BTCUSDT", "H1", ancora, "pc", oggi=oggi, adesso="2026-10-26 11:00")
        nuovo_c = ST.leggi_confine(cg)
        arch = rr["archivio"]
        check("D16d. reset: confine nuovo = 80% delle barre di adesso, id nuovo, data del reset scritta",
              rr["esito"] == "fatto" and rr["nuovo"] == ancora.index[1279] + pd.Timedelta(hours=1)
              and nuovo_c["id"] != vecchio_c["id"] and nuovo_c["reset_il"] == campo, f"{rr['nuovo']}")
        check("D16e. lo studio intero e' in archivio (confine, dataset, giornali), niente cancellato",
              (arch / "confine.json").exists() and (arch / ds / "giornale_pc.jsonl").exists()
              and (arch / ds / "giornale_colab.jsonl").exists() and (arch / "BYBIT_SPOT_ETHUSDT_H1").is_dir()
              and json.loads((arch / "confine.json").read_text(encoding="utf-8"))["id"] == vecchio_c["id"]
              and sorted(p.name for p in (cg / "studio").iterdir()) == ["archivio", "confine.json"])
        prec = nuovo_c["studio_precedente"]
        check("D16f. studio_precedente: confine, H provati e out-of-sample guardato per dataset",
              prec["confine"] == vecchio_c["confine"] and prec["dataset"][ds]["h_provati"] == [41, 25]
              and prec["dataset"][ds]["oos_guardato"] == 2 and prec["dataset"]["BYBIT_SPOT_ETHUSDT_H1"]["oos_guardato"] == 1)
        r_n, _ = ST.ricostruisci(cg, ds, nuovo_c)
        check("D16g. lo studio nuovo riparte da zero (conto, diario, H provati)",
              r_n.h_provati == [] and r_n.diario == [] and r_n.prove["trigger"] == 0)
        check("D16h. la stessa data rieseguita: nessun reset nuovo",
              ST.reset(cg, campo, "BINANCE_PERP_BTCUSDT", "H1", storico("2024-01-01", periodi=2000, passo="1h"),
                       "pc", oggi=oggi)["esito"] == "gia_fatto_oggi" and ST.leggi_confine(cg)["id"] == nuovo_c["id"])
        ST.aggiungi_voce(cg, ds, "colab", vecchio_c["id"], {"voce": "oos", "voce_diario": {"H": 25}})
        r_v, info_v = ST.ricostruisci(cg, ds, nuovo_c)
        check("C14. una riga con l'id dello studio vecchio (Colab rimasto aperto) non entra e si conta",
              info_v["altre_id"] == 1 and r_v.diario == [])

        # contaminazione: A aperto su 1.000 barre (confine fine barra 800), diario fino alla barra 1.100,
        # B senza aperture; reset su 1.300 barre -> confine nuovo fine barra 1.040
        cd = cartella("d17")
        mille = storico("2024-01-01", periodi=1000, passo="1h")
        sd = ST.entra(cd, "BINANCE_PERP_BTCUSDT", "H1", mille, "pc").studio
        ST.entra(cd, "BYBIT_SPOT_ETHUSDT", "H1", mille, "pc")
        ST.aggiungi_voce(cd, "BYBIT_SPOT_ETHUSDT_H1", "pc", sd["id"], {"voce": "orizzonte", "H": 41})
        tredici = storico("2024-01-01", periodi=1300, passo="1h")
        for _ in range(3):
            ST.aggiungi_voce(cd, "BINANCE_PERP_BTCUSDT_H1", "pc", sd["id"],
                             {"voce": "oos", "voce_diario": {"H": 41, "oos_fino_al": tredici.index[1099].isoformat()}})
        rc = ST.reset(cd, campo, "BINANCE_PERP_BTCUSDT", "H1", tredici, "pc", oggi=oggi)
        ora = pd.Timedelta(hours=1)
        check("D17. contaminazione: dalla fine della barra 800 alla fine della 1.040, guardata 3 volte su BTC",
              rc["contaminato"] == {"dal": (tredici.index[799] + ora).isoformat(),
                                    "al": (tredici.index[1039] + ora).isoformat(),
                                    "guardato": {"BINANCE_PERP_BTCUSDT_H1": 3}}
              and ST.leggi_confine(cd)["contaminato"] == RD.normale(rc["contaminato"]))
        ce = cartella("d17b")
        ST.entra(ce, "BINANCE_PERP_BTCUSDT", "H1", mille, "pc")
        check("D17b. senza aperture dell'out-of-sample: nessuna contaminazione",
              ST.reset(ce, campo, "BINANCE_PERP_BTCUSDT", "H1", tredici, "pc", oggi=oggi)["contaminato"] is None)

        # studio aperto sul dataset sbagliato (docs/70 §11, correzione del 26/10): SOL parte il 20/1 e il suo
        # 80% cade alla fine della barra 675 (17/02 03:00); BTC dal 1/1, 1.300 barre: 80% alla fine della barra 1.040
        # (13/02 08:00), piu' indietro. Le due storie finiscono alla stessa ora
        sol = storico("2024-01-20", periodi=1300 - 19 * 24, passo="1h", seme=5)
        for nome, voce in (("d22a", None), ("d22b", {"voce": "prova", "dove": "trigger", "chiave": None, "n": 12}),
                           ("d22c", {"voce": "oos", "voce_diario": {"H": 41}})):
            cz = cartella(nome)
            sz = ST.entra(cz, "BYBIT_SPOT_SOLUSDT", "H1", sol, "pc").studio
            ST.aggiungi_voce(cz, "BYBIT_SPOT_SOLUSDT_H1", "pc", sz["id"], {"voce": "orizzonte", "H": 41})
            if voce is not None:
                ST.aggiungi_voce(cz, "BYBIT_SPOT_SOLUSDT_H1", "pc", sz["id"], voce)
            esiti_z = ST.reset(cz, campo, "BINANCE_PERP_BTCUSDT", "H1", tredici, "pc", oggi=oggi)
            if voce is None:
                check("D22. confine piu' indietro su uno studio senza niente di misurato (solo H dichiarato): "
                      "reset fatto, confine = 80% di BTC",
                      esiti_z["esito"] == "fatto" and esiti_z["nuovo"] < esiti_z["vecchio"]
                      and esiti_z["vecchio"] == sol.index[674] + ora
                      and esiti_z["nuovo"] == tredici.index[1039] + ora
                      and ST.leggi_confine(cz)["aperto_su"] == "BINANCE_PERP_BTCUSDT H1"
                      and esiti_z["contaminato"] is None,
                      f"{esiti_z['vecchio']:%d/%m %H:%M} -> {esiti_z['nuovo']:%d/%m %H:%M}")
            else:
                check(f"D22{'b' if voce['voce'] == 'prova' else 'c'}. confine piu' indietro con una voce "
                      f"«{voce['voce']}» nello studio: rifiutato, con il perche'; studio intatto, niente archivio",
                      esiti_z["esito"] == "rifiutato_indietro"
                      and "diventerebbero out-of-sample" in esiti_z["messaggio"]
                      and esiti_z["voci"][voce["voce"]] == 1 and ST.leggi_confine(cz)["id"] == sz["id"]
                      and not (ST.cartella_studio(cz) / "archivio").exists())

        f = ST.cartella_studio(cd) / "confine.json"
        prima_t = f.read_bytes()
        originale = os.replace

        def guasto(*a, **k):
            raise OSError("disco pieno")
        try:
            os.replace = guasto
            esploso = errore(lambda: ST.scrivi_sicuro(f, "{rotto"), OSError, "disco pieno")
        finally:
            os.replace = originale
        check("D21. scrittura sicura: un errore a meta' lascia il file di prima intatto, nessun file temporaneo",
              esploso and f.read_bytes() == prima_t and not any(p.suffix == ".tmp" for p in f.parent.iterdir()))
        check("D21b. aprire uno studio che c'e' gia' -> si ferma (il confine si cambia solo con il reset)",
              errore(lambda: ST.apri_confine(cd, "BINANCE_PERP_BTCUSDT", "H1", mille, "pc"), FileExistsError,
                     "reset"))
        st_ = RD.StoriaDataset(chiave=("X",))
        RD.annota_oos(st_, {"H": 1})
        check("D21c. annota_oos senza oos_fino_al resta come prima (nessuna chiave in piu')",
              sorted(st_.diario[-1]) == ["H", "quando"])
    finally:
        RD.azzera()
        shutil.rmtree(radice, ignore_errors=True)

    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
