"""
Suite di collaudo delle funzioni delle celle del notebook della fabbrica (engine/vetrina_fabbrica.py, docs/82 §7,
lavoro L5a): ogni cella su una cartella sintetica, rieseguita, con campi sbagliati.

Si lancia da terminale, dalla cartella del progetto:

    python test_vetrina_fabbrica.py

Solo dati sintetici (engine/fabbrica/sintetici.py), scritti in cartelle temporanee: non servono i file in dati/,
MetaTrader 5 o internet. Stampa una riga per collaudo e alla fine «RISULTATO: n/n test superati».
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import time
import warnings

import matplotlib
import pandas as pd

from engine import vetrina
from engine import vetrina_fabbrica as vf
from engine.fabbrica import registro, sintetici
from engine.fabbrica.blocchi import LIMITE_LOGICO
from engine.fabbrica.cassaforte import ESITO, INGRESSO
from engine.fabbrica.config import cartella_asset, config_standard
from engine.fabbrica.generatore import stato_registro
from engine.fabbrica.ricerca import lancia

warnings.simplefilter("ignore")
matplotlib.use("Agg")

SPOT = "BYBIT_SPOT_ETHUSDT"
DATA = "20260101"
ORA_FISSA = "2026-01-01T00:00:00+00:00"
CONFINI = {"inizio": "2024-01-01 00:00", "ricerca_ore": 3000, "selezione_ore": 2000, "cassaforte_ore": 500}
BLOCCHI = ("DONCHIAN", "RSI_RIENTRO", "F3_VOLUME_ABOVE_AVG", "ADX", "X0", "X3")
ESITI: list[bool] = []


def check(nome: str, ok: bool, dettaglio: str = "") -> None:
    ESITI.append(bool(ok))
    print(f"[{'OK ' if ok else 'KO '}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""))


def errore(funzione, tipo=Exception, testo: str | None = None) -> bool:
    try:
        funzione()
    except tipo as e:
        return testo is None or testo in str(e)
    return False


def _zitto(funzione, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return funzione(*a, **k)


def _cfg(timeframe="M15", confini=CONFINI, blocchi=BLOCCHI):
    cfg = config_standard(SPOT, timeframe, seme=0, processi=1)
    cfg["confini"] = dict(confini)
    cfg["blocchi"] = {k: v for k, v in cfg["blocchi"].items() if k in blocchi}
    cfg["qualita_1"]["trade_min"] = 30
    cfg["budget"].update({"teorie_turno_2": 4, "teorie_passo_2": 4, "prove_per_giro": 60})
    return cfg


def _mercato(minuti=15, confini=CONFINI, extra=100):
    n = int((confini["ricerca_ore"] + confini["selezione_ore"] + confini["cassaforte_ore"]) * 60 / minuti) + extra
    return sintetici.mercato_piantato(n, seme=5, minuti=minuti, inizio="2024-01-01", prezzo=2_000.0)


class _Exchange:
    """
    Un exchange come ccxt, senza rete (09/11): con `df` dà le sue barre da `since` in avanti; senza, non risponde
    (ogni richiesta fallisce). La cella 1 aggiorna i dati a ogni avvio: nella suite passa sempre da qui.
    """

    def __init__(self, df=None):
        self.df, self.chiamate = df, 0

    def load_markets(self):
        return {}

    def fetch_ohlcv(self, simbolo, tf, since=None, limit=1000):
        self.chiamate += 1
        if self.df is None:
            raise ConnectionError("NetworkError: exchange irraggiungibile (collaudo)")
        ms = pd.DatetimeIndex(self.df.index).as_unit("ns").asi8 // 1_000_000
        v = self.df[["Open", "High", "Low", "Close", "Volume"]].to_numpy()
        dentro = [k for k in range(len(ms)) if ms[k] >= since][:limit]
        return [[int(ms[k]), *map(float, v[k])] for k in dentro]

    def fetch_funding_rate_history(self, simbolo, since=None, limit=None, params=None):
        self.chiamate += 1
        raise ConnectionError("NetworkError: exchange irraggiungibile (collaudo)")


def _con_exchange(ex):
    """Il download della cella 1 (vf._scarica) con l'exchange finto `ex`: lo stesso aggiorna_per_lab, nessuna rete."""
    from engine.aggiorna_dati import aggiorna_per_lab
    from engine.exchange import CCXT_ID

    def scarica(symbol, timeframe, cartella):
        return aggiorna_per_lab(symbol, timeframe, cartella, aperti={k: ex for k in set(CCXT_ID.values())},
                                verbose=False, attesa=0.0)
    return scarica


def _eventi(d, tipo):
    return [e for e in registro.leggi_registro(cartella_asset(d, SPOT, "M15")) if e.get("tipo") == tipo]


def _registro_bytes(d):
    base = cartella_asset(d, SPOT, "M15")
    out = {}
    for n in sorted(os.listdir(base)):
        if n.startswith("registro_"):
            with open(os.path.join(base, n), "rb") as f:
                out[n] = f.read()
    return out


def esegui() -> int:
    t0 = time.perf_counter()
    registro_adesso = registro.adesso
    registro.adesso = lambda: ORA_FISSA
    scarica_vero = vf._scarica
    vf._scarica = _con_exchange(_Exchange())          # la suite non va in rete: l'exchange non risponde
    try:
        with tempfile.TemporaryDirectory() as radice:
            r, conf = _celle(radice)
            _d1(radice)
            _dati_e_confini(radice)
            _c2(radice, r, conf)
    finally:
        registro.adesso = registro_adesso
        vf._scarica = scarica_vero
        registro.imposta_macchina(None)
    print("\n" + "=" * 70)
    print(f"Durata: {time.perf_counter() - t0:.0f} s")
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


def _celle(radice):
    print("Avvio e 1 · Configura")
    d = os.path.join(radice, "M15")
    df = _mercato()
    sintetici.scrivi_storico(d, SPOT, "M15", df)
    a = _zitto(vf.avvio, d, "PC2")
    check("1. Avvio: il nome della macchina scritto nel campo (pc2) è quello dei file; trova il CSV e la sua ultima "
          "barra; nessuna ricerca ancora", a["macchina"] == "pc2" and registro.macchina() == "pc2"
          and len(a["dati"]) == 1 and a["dati"]["ultima barra (UTC)"].iloc[0] == df.index[-1] and len(a["ricerche"]) == 0)
    check("2. un nome della macchina con caratteri non ammessi: errore", errore(lambda: vf.avvio(d, "pc 2/x")))

    vuota = os.path.join(radice, "vuota")
    os.makedirs(vuota)
    cfg = _cfg()
    ferma = errore(lambda: _zitto(vf.configura, vuota, "BYBIT", "SPOT", "ETH", "M15", 1, cfg, DATA), ValueError,
                   "La cella si ferma")
    corta = os.path.join(radice, "corta")
    sintetici.scrivi_storico(corta, SPOT, "M15", df.iloc[: len(df) // 2])
    ferma_corta = errore(lambda: _zitto(vf.configura, corta, "BYBIT", "SPOT", "ETH", "M15", 1, cfg, DATA), ValueError,
                         "La cella si ferma")
    check("3. senza dati, o con dati che non coprono la cassaforte: la cella si ferma e dice perché; nessuna cartella "
          "di ricerca scritta", ferma and ferma_corta and _nessuna_ricerca(vuota) and _nessuna_ricerca(corta))
    check("4. un symbol fuori tabella o un timeframe non previsto: errore",
          errore(lambda: vf.configura(d, "KRAKEN", "SPOT", "ETH", "M15")) and errore(
              lambda: vf.configura(d, "BYBIT", "SPOT", "ETH", "M2")))

    conf = _zitto(vf.configura, d, "BYBIT", "SPOT", "ETH", "M15", 1, cfg, DATA)
    conf2 = _zitto(vf.configura, d, "BYBIT", "SPOT", "ETH", "M15", 1, cfg, "20270101")
    check("5. Configura: ricerca nuova, poi la stessa cella rieseguita (anche un altro giorno) dà la stessa ricerca",
          conf.nuova and not conf2.nuova and conf.id_ricerca == conf2.id_ricerca and conf.teorie > 0
          and conf.budget_massimo > 0 and 0 < conf.stima_minuti[0] <= conf.stima_minuti[1]
          and len(conf.esclusi) == 78 - 6)
    senza_u = dict(cfg, blocchi={k: v for k, v in cfg["blocchi"].items() if k not in ("X0", "X3")})
    check("6. se non resta un'uscita la cella si ferma", errore(
        lambda: _zitto(vf.configura, d, "BYBIT", "SPOT", "ETH", "M15", 1, senza_u, DATA), ValueError, "un'uscita"))

    print("\n2 · La ricerca")
    righe = []
    vero = vf._stampa_avanzamento

    def spia():
        f = vero()

        def avanza(x):
            righe.append(x)
            f(x)
        return avanza

    vf._stampa_avanzamento = spia
    try:
        r = _zitto(vf.ricerca, conf)
    finally:
        vf._stampa_avanzamento = vero
    with open(os.path.join(r.cartella, vf.FILE_RIEPILOGO), encoding="utf-8") as f:
        riep = json.load(f)
    check("7. la ricerca finisce; l'avanzamento arriva teoria per teoria (turno 1, turno 2, zoom, prove che crescono)",
          r.finita and righe and [x["fase"] for x in righe] == (["turno 1"] * r.imbuto["turno_1"]
                                                                + ["turno 2"] * r.imbuto["turno_2"]
                                                                + ["zoom"] * r.imbuto["passo_2"])
          and r.imbuto["turno_2"] > 0
          and [x["prove"] for x in righe] == sorted(x["prove"] for x in righe)
          and righe[-1]["prove"] + r.imbuto["altopiano"] == r.prove
          and max(x["numero"] for x in righe if x["fase"] == "turno 1") == r.imbuto["turno_1"],
          "le ultime prove sono quelle della selezione, una per sopravvissuta")
    check("8. riepilogo.json: imbuto, prove, lo stesso elenco dei blocchi tolti della cella 1 e la tabella dei tenuti e "
          "dei tolti", riep["imbuto"] == r.imbuto and riep["prove"] == r.prove and riep["blocchi_esclusi"] == conf.esclusi
          and riep["finita"] and riep["tenuti_tolti"] == json.loads(registro.json_riga(conf.tenuti_tolti))
          and len(riep["tenuti_tolti"]) == 2 + 2)
    righe.clear()
    r2 = _zitto(vf.ricerca, conf)
    check("9. rieseguita: riprende da dove era, nessuna prova in più, stesso imbuto",
          r2.prove == r.prove and r2.imbuto == r.imbuto and not righe)
    e_ref = lancia(cfg, os.path.join(radice, "senza_avanzamento"), verbose=False, data=DATA) if _copia(
        d, os.path.join(radice, "senza_avanzamento")) else None
    check("10. avanzamento non cambia la ricerca: la stessa senza avanzamento ha le stesse tabelle",
          e_ref is not None and e_ref.passo_1.equals(r.passo_1) and e_ref.passo_2.equals(r.passo_2)
          and e_ref.selezione.tabella.equals(r.selezione.tabella))

    print("\n3 · L'imbuto e 4 · Le strategie rimaste")
    imb = _zitto(vf.imbuto, r)
    check("11. l'imbuto ha i passi della ricerca, con i due turni, e la cassaforte ancora a zero",
          list(imb["quante"])[:8] == [r.imbuto[k] for k in ("turno_1", "turno_1_tenute", "turno_2", "turno_2_tenute",
                                                              "passo_2", "altopiano", "selezione", "scelte")]
          and list(imb["passo"])[:4] == ["turno 1: teorie", "turno 1: tenute", "turno 2: teorie", "turno 2: tenute"]
          and list(imb["quante"])[8:] == [0, 0])
    tab = _zitto(vf.strategie_rimaste, r)
    ordine = [vf.ORDINE_ESITI[x] for x in tab["esito"]]
    check("12. le strategie rimaste numerate da 1, prima le scelte; ogni riga ha la regola in parole",
          list(tab["numero"]) == list(range(1, len(tab) + 1)) and ordine == sorted(ordine)
          and all(x.startswith("Entra ") for x in tab["regola"]))

    print("\n5 · La cassaforte")
    prima = _registro_bytes(d)
    vuoto = _zitto(vf.cassaforte, r, "")
    check("13. campo vuoto: non entra niente, il registro non cambia", vuoto is None and _registro_bytes(d) == prima)
    import inspect
    check("14. (10/11) nessuna frase di conferma: la cella 5 ha solo il campo dei numeri",
          list(inspect.signature(vf.cassaforte).parameters) == ["r", "strategie"] and not hasattr(vf, "FRASE_CONFERMA"))
    fam = tab[tab["esito"] != "scelta"]
    non_scelta = (errore(lambda: _zitto(vf.cassaforte, r, str(int(fam["numero"].iloc[0]))))
                  if len(fam) else True)
    check("15. numeri sbagliati (lettere, fuori tabella) o una strategia non «scelta»: errore; il registro non cambia",
          errore(lambda: vf.cassaforte(r, "uno")) and errore(lambda: vf.cassaforte(r, "99")) and non_scelta and _registro_bytes(d) == prima)
    c = _zitto(vf.cassaforte, r, "tutte le scelte")
    scelte = list(tab[tab["esito"] == "scelta"]["id_strategia"])
    n_ingressi = len(_eventi(d, INGRESSO))
    check("16. «tutte le scelte»: entrano le scelte, un ingresso e un esito nel registro",
          c is not None and sorted(c.trade) == sorted(scelte) and n_ingressi == 1 and len(_eventi(d, ESITO)) == 1)
    c2 = _zitto(vf.cassaforte, r, "tutte le scelte")
    dopo = _registro_bytes(d)
    c3 = _zitto(vf.cassaforte, r, "")
    check("17. (10/11) rieseguita con i numeri: un ingresso e un esito in più, stesso esito; con il campo vuoto: "
          "nessun ingresso, registro identico, stesso esito",
          len(_eventi(d, INGRESSO)) == 2 and len(_eventi(d, ESITO)) == 2 and c2.tabella.equals(c.tabella)
          and _registro_bytes(d) == dopo and c3.tabella.equals(c.tabella))
    imb2 = _zitto(vf.imbuto, r)
    check("18. l'imbuto legge la cassaforte dal registro: entrate e passate",
          list(imb2["quante"])[8] == len(scelte) and list(imb2["quante"])[9] == int((c.tabella["esito"] == "passa").sum()))

    print("\n6 · MM, stress test e verifica dei trade")
    catalogo = stato_registro()
    numero = int(tab[tab["id_strategia"] == scelte[0]]["numero"].iloc[0])
    check("19. un trade da vedere scritto male, o una strategia non entrata: errore prima di ogni calcolo",
          errore(lambda: vf.mm_e_stress(r, numero, trade_da_vedere="tre")) and (
              errore(lambda: vf.mm_e_stress(r, int(fam["numero"].iloc[0]))) if len(fam) else True)
          and stato_registro() == catalogo)
    lab_prima = _testi_lab()
    aiutanti = {n: getattr(vetrina, n) for n in vf._AIUTANTI}
    schermo = io.StringIO()
    with contextlib.redirect_stdout(schermo):
        out = vf.mm_e_stress(r, numero, simulazioni=200, simulazioni_stress=500, trade_da_vedere="1")
    visto = schermo.getvalue()
    with open(out["percorso"], encoding="utf-8") as f:
        salvato = json.load(f)
    check("20. money management, stress test e sempre la verifica: le regole tutte OK; il riassunto è salvato; il "
          "catalogo torna com'era", (out["verifica"]["regole"]["Esito"] == "OK").all()
          and salvato["verifica"]["regole"] and salvato["mm"]["percentuale"] == out["mm"]["f"]
          and salvato["stress"]["controllo"] and stato_registro() == catalogo,
          f"{len(out['verifica']['regole'])} regole")
    check("21. nella 6 nessun rimando alle schermate del Lab e nessun nome FAB_SES_…: la lente dice il nome del blocco",
          "schermat" not in visto.lower() and "FAB_SES" not in visto and "Trigger scattato" in visto
          and any(x in visto for x in ("Donchian", "RSI ", "E5 ·")) and "poi vai alla 7" in visto.lower())
    vero_stress = vetrina.stress_test

    def rotto(*a, **k):
        raise RuntimeError("errore a metà della cella 6")

    vetrina.stress_test = rotto
    try:
        fermata = errore(lambda: _zitto(vf.mm_e_stress, r, numero, simulazioni=200), RuntimeError)
    finally:
        vetrina.stress_test = vero_stress
    check("22. dopo la 6, anche fermata da un errore a metà, le funzioni del Lab sono le stesse e stampano esattamente "
          "i testi di prima; il catalogo è pulito", fermata and all(getattr(vetrina, n) is f for n, f in aiutanti.items())
          and _testi_lab() == lab_prima and stato_registro() == catalogo)

    print("\n7 · Le schede")
    fatte = _zitto(vf.schede, r)
    testi = {}
    for m, j in fatte:
        with open(m, encoding="utf-8") as f:
            testi[os.path.basename(m)[:-3]] = f.read()
    con_mm = testi.get(scelte[0], "")
    check("23. una scheda .md e .json per ogni strategia entrata; quella con la 6 porta verifica e money management, "
          "le altre dicono «esegui la 6»", len(fatte) == len(scelte) and "Rischio a ogni trade" in con_mm
          and "esegui la 6" not in con_mm.split("## Blocchi")[0]
          and all("esegui la 6" in t for k, t in testi.items() if k != scelte[0]))
    a2 = _zitto(vf.avvio, d, "pc2")
    riga = a2["ricerche"].iloc[0]
    check("24. Avvio dopo la cassaforte: la ricerca, le strategie entrate e la fine dell'ultima cassaforte usata "
          "(09/11: niente più «barre dopo», la finestra scorrevole non c'è più)",
          riga["ricerca"] == r.id_ricerca and riga["entrate in cassaforte"] == len(scelte)
          and riga["ultima cassaforte usata fino al"] == vf._data(c.tratto["a"])
          and "barre dopo" not in a2["ricerche"].columns, riga["ultima cassaforte usata fino al"])
    check("25. i file di questa macchina hanno il nome scritto nell'Avvio (registro_pc2.jsonl, prove_pc2.csv)",
          os.path.exists(os.path.join(cartella_asset(d, SPOT, "M15"), "registro_pc2.jsonl"))
          and os.path.exists(os.path.join(r.cartella, "prove_pc2.csv")))
    return r, conf


def _testi_lab() -> str:
    """Quello che stampano gli aiutanti del Lab con testi che la fabbrica riscriverebbe (rimandi e nomi FAB_SES_…)."""
    t = "Poi vai alla schermata 9. Trigger FAB_SES_1_DONCHIAN; drawdown dalla schermata 7."
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        vetrina._riquadro(t, t, t)
        vetrina._nota(t)
        vetrina._avviso(t)
        vetrina._spiegazione(t, t)
        vetrina._titolo(t)
        vetrina._mostra((t, pd.DataFrame({"a": [t]})))
        vetrina._dettaglio(t, (t, pd.DataFrame({"a": [t]})))
    return buf.getvalue()


def _nessuna_ricerca(cartella) -> bool:
    base = cartella_asset(cartella, SPOT, "M15")
    return not os.path.isdir(base) or not os.listdir(base)


def _copia(da, a) -> bool:
    """Lo stesso CSV in un'altra cartella, per una ricerca da capo."""
    os.makedirs(a, exist_ok=True)
    with open(os.path.join(da, f"{SPOT}_M15.csv"), "rb") as f, open(os.path.join(a, f"{SPOT}_M15.csv"), "wb") as g:
        g.write(f.read())
    return True


def _d1(radice):
    print("\nD1: mostra i blocchi tolti e prosegue")
    d = os.path.join(radice, "D1")
    confini = {"inizio": "2024-01-01 00:00", "ricerca_ore": 24 * 700, "selezione_ore": 24 * 300,
               "cassaforte_ore": 24 * 100}
    sintetici.scrivi_storico(d, SPOT, "D1", _mercato(1440, confini, extra=5))
    cfg = config_standard(SPOT, "D1", seme=0, processi=1)
    cfg["confini"] = confini
    conf = _zitto(vf.configura, d, "BYBIT", "SPOT", "ETH", "D1", 1, cfg, DATA)
    tolti = {e["blocco"]: e["tipo"] for e in conf.esclusi}
    check("26. D1 con la config standard: la cella elenca i 24 blocchi tolti con il motivo (F20 limite logico) e "
          "prosegue: la ricerca è configurata", conf.teorie > 0 and len(tolti) == 24
          and tolti.get("F20_SESSION_OVERLAP") == LIMITE_LOGICO and "F20_SESSION_OVERLAP" not in conf.config["blocchi"],
          f"{conf.teorie} teorie")


def _parlato(funzione, *a, **k):
    """(risultato, testo stampato); se si ferma, (l'errore, testo stampato)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            return funzione(*a, **k), buf.getvalue()
        except Exception as e:  # noqa: BLE001
            return e, buf.getvalue()


def _dati_e_confini(radice):
    print("\n1 · Configura: i dati a ogni avvio e i confini sull'ultima barra (09/11)")
    from engine.fabbrica.config import confini_standard
    d = os.path.join(radice, "giu")
    df = _mercato()
    p = sintetici.scrivi_storico(d, SPOT, "M15", df)
    with open(p, "rb") as f:
        prima = f.read()
    giu = _Exchange()
    vf._scarica = _con_exchange(giu)
    conf, testo = _parlato(vf.configura, d, "BYBIT", "SPOT", "ETH", "M15", 1, _cfg(), DATA)
    with open(p, "rb") as f:
        dopo = f.read()
    fino = vf._data(df.index[-1] + pd.Timedelta(minutes=15))
    check("27. exchange irraggiungibile: avviso «exchange non raggiungibile: uso i dati fino a …» con la chiusura "
          "dell'ultima barra, il CSV resta quello di prima ed è letto: la ricerca è configurata",
          isinstance(conf, vf.Configurazione) and giu.chiamate > 0 and dopo == prima and conf.barre_ricerca > 0
          and f"Exchange non raggiungibile: uso i dati fino a {fino} UTC" in testo, fino)

    nuova = os.path.join(radice, "nuova", "dati")             # la cartella non c'è: la cella la crea
    _, testo_n = _parlato(vf.configura, nuova, "BYBIT", "SPOT", "ETH", "M15", 1, _cfg(), DATA)
    check("28. cartella dei dati che non c'è e exchange irraggiungibile: la cartella si crea, la cella si ferma perché "
          "il CSV non c'è e non si scarica", os.path.isdir(nuova) and isinstance(_, ValueError)
          and "La cella si ferma" in str(_) and not os.listdir(nuova))

    print("\nD1 dal 02/01/2020, l'exchange dà 6 barre nuove; config standard (confini calcolati)")
    d1 = os.path.join(radice, "D1_standard")
    tutto = sintetici.mercato_piantato(2_500, seme=7, minuti=1440, inizio="2020-01-02", prezzo=2_000.0)
    sintetici.scrivi_storico(d1, SPOT, "D1", tutto.iloc[:-6])
    vf._scarica = _con_exchange(_Exchange(tutto))
    conf, testo = _parlato(vf.configura, d1, "BYBIT", "SPOT", "ETH", "D1", 1, None, DATA)
    ultima = tutto.index[-1]
    attesi = confini_standard("D1", ultima)
    lim = conf.limiti if isinstance(conf, vf.Configurazione) else {}
    check("29. dati aggiornati: «dati aggiornati fino a …» con la chiusura dell'ultima barra nuova; i confini della "
          "config sono quelli calcolati su quella barra, con le ore nella config; la cella mostra le date dei tre pezzi",
          isinstance(conf, vf.Configurazione) and conf.config["confini"] == attesi
          and lim["cassaforte"][1] == ultima + pd.Timedelta(days=1)
          and f"Dati aggiornati fino a {vf._data(ultima + pd.Timedelta(days=1))} UTC (6 barre nuove)" in testo
          and all(vf._data(lim[x][0]) in testo for x in ("ricerca", "selezione", "cassaforte")),
          f"{attesi}" if isinstance(conf, vf.Configurazione) else repr(conf)[:300])
    a_mano = dict(_cfg("D1"), confini={"inizio": "2020-01-02 00:00", "ricerca_ore": 24 * 1200,
                                       "selezione_ore": 24 * 700, "cassaforte_ore": 24 * 400})
    vf._scarica = _con_exchange(_Exchange())
    conf_m, _t = _parlato(vf.configura, d1, "BYBIT", "SPOT", "ETH", "D1", 1, a_mano, DATA)
    check("30. una config scritta a mano resta com'è, confini compresi",
          isinstance(conf_m, vf.Configurazione) and conf_m.config["confini"] == a_mano["confini"],
          repr(conf_m)[:200] if not isinstance(conf_m, vf.Configurazione) else "")

    print("\nH4: due lanci della cella 1 nello stesso giorno UTC, con barre nuove in mezzo (09/11, correzione PR #109)")
    from engine.fabbrica.config import impronta_config
    h4 = os.path.join(radice, "H4_stesso_giorno")
    ultima = pd.Timestamp("2026-11-05 16:00", tz="UTC")                 # chiude alle 20:00: stesso giorno
    n = int((ultima - pd.Timestamp("2020-01-02", tz="UTC")) / pd.Timedelta(hours=4)) + 1
    tutto = sintetici.mercato_piantato(n, seme=11, minuti=240, inizio="2020-01-02", prezzo=2_000.0)
    sintetici.scrivi_storico(h4, SPOT, "H4", tutto.iloc[:-3])           # fino alla barra delle 04:00
    vf._scarica = _con_exchange(_Exchange())                            # primo lancio: exchange irraggiungibile
    primo, _t1 = _parlato(vf.configura, h4, "BYBIT", "SPOT", "ETH", "H4", 1, None, DATA)
    vf._scarica = _con_exchange(_Exchange(tutto))                       # secondo: arrivano le barre fino alle 16:00
    secondo, t2 = _parlato(vf.configura, h4, "BYBIT", "SPOT", "ETH", "H4", 1, None, DATA)
    ok = isinstance(primo, vf.Configurazione) and isinstance(secondo, vf.Configurazione)
    check("31. stesso giorno UTC, barre nuove fra i due lanci: stessi confini (fine alla mezzanotte del 05/11), stessa "
          "impronta, stessa ricerca: il secondo lancio riprende",
          ok and "(3 barre nuove)" in t2 and impronta_config(primo.config) == impronta_config(secondo.config)
          and primo.id_ricerca == secondo.id_ricerca and primo.nuova and not secondo.nuova
          and secondo.limiti["cassaforte"][1] == pd.Timestamp("2026-11-05", tz="UTC"),
          f"{primo.id_ricerca} e {secondo.id_ricerca}" if ok else f"{primo!r} {secondo!r}"[:300])
    vf._scarica = _con_exchange(_Exchange())



def _c2(radice, r, conf):
    print("\nC2: un blocco per famiglia e i due turni nelle celle; la stima del tempo; le ricerche della versione 1")
    da, a = vf.stima_minuti(370_200, 123_254, 3)
    check("32. la stima della cella 1 viene dalla velocità vera delle ricerche del 9 e del 10/11 (167 e 146 prove al "
          "secondo con 3 processi): 370.200 prove su 123.254 barre fanno circa 37–42 minuti; con 1 processo di più, "
          "con meno barre di meno", round(da) == 37 and round(a) == 42
          and vf.stima_minuti(370_200, 123_254, 1)[0] > da and vf.stima_minuti(370_200, 123_254 // 4, 3)[1] < a / 3,
          f"{da:.1f}–{a:.1f} minuti")
    d = os.path.join(radice, "M15")
    _, testo = _parlato(vf.configura, d, "BYBIT", "SPOT", "ETH", "M15", 1, _cfg(), DATA)
    check("33. la cella 1 mostra, per lato, quanti trigger e filtri e quanti tenuti (un blocco per famiglia), le teorie "
          "dei due turni, le prove massime e la stima in minuti", "long: 2 trigger → " in testo
          and "tenuti (un blocco per famiglia)" in testo and f"Turno 1: {conf.teorie} teorie; turno 2: al massimo" in testo
          and "minut" in testo and "Tutti i blocchi, tenuti e tolti" in testo and conf.turno_2_massimo > 0,
          testo[testo.find("long:"):][:160])
    import dataclasses
    vecchia = os.path.join(cartella_asset(d, SPOT, "M15"), "20261109_versione1")
    os.makedirs(vecchia)
    with open(os.path.join(r.cartella, "config.json"), encoding="utf-8") as f:
        cfg_v1 = dict(json.load(f), versione=1)
    with open(os.path.join(vecchia, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg_v1, f)
    r1 = dataclasses.replace(r, cartella=vecchia, id_ricerca="20261109_versione1")
    ferme = [errore(lambda f=f: _zitto(f, r1, *a), ValueError, vf.VERSIONE_1)
             for f, a in ((vf.strategie_rimaste, ()), (vf.cassaforte, ("1",)), (vf.mm_e_stress, (1,)), (vf.schede, ()))]
    check("34. una ricerca della versione 1 aperta dalle celle 4–7 si ferma con «ricerca non trovata: è una ricerca della "
          "versione 1, rilancia la cella 2 per una ricerca nuova»", all(ferme)
          and vf.VERSIONE_1 == "ricerca non trovata: è una ricerca della versione 1, rilancia la cella 2 per una "
                               "ricerca nuova", str(ferme))
    from engine.fabbrica.config import controlla_config
    check("35. la config versione 1 non si rilancia: la ricerca ha una strada sola (D5 = B)",
          errore(lambda: controlla_config(cfg_v1), ValueError, "versione 1"))


if __name__ == "__main__":
    sys.exit(esegui())
