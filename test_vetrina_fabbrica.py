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
    cfg["budget"].update({"teorie_passo_2": 4, "prove_per_giro": 60})
    return cfg


def _mercato(minuti=15, confini=CONFINI, extra=100):
    n = int((confini["ricerca_ore"] + confini["selezione_ore"] + confini["cassaforte_ore"]) * 60 / minuti) + extra
    return sintetici.mercato_piantato(n, seme=5, minuti=minuti, inizio="2024-01-01", prezzo=2_000.0)


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
    try:
        with tempfile.TemporaryDirectory() as radice:
            _celle(radice)
            _d1(radice)
    finally:
        registro.adesso = registro_adesso
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
          and conf.budget_massimo > 0 and conf.stima_minuti > 0 and len(conf.esclusi) == 11)
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
    check("7. la ricerca finisce; l'avanzamento arriva teoria per teoria (passo 1 e passo 2, prove che crescono)",
          r.finita and righe and {x["fase"] for x in righe} == {"passo 1", "passo 2"}
          and [x["prove"] for x in righe] == sorted(x["prove"] for x in righe)
          and righe[-1]["prove"] + r.imbuto["altopiano"] == r.prove
          and max(x["numero"] for x in righe if x["fase"] == "passo 1") == r.imbuto["teorie"],
          "le ultime prove sono quelle della selezione, una per sopravvissuta")
    check("8. riepilogo.json: imbuto, prove e lo stesso elenco dei blocchi tolti della cella 1",
          riep["imbuto"] == r.imbuto and riep["prove"] == r.prove and riep["blocchi_esclusi"] == conf.esclusi
          and riep["finita"])
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
    check("11. l'imbuto ha i passi della ricerca e la cassaforte ancora a zero",
          list(imb["quante"])[:6] == [r.imbuto[k] for k in ("teorie", "passo_1_tenute", "passo_2", "altopiano",
                                                              "selezione", "scelte")]
          and list(imb["quante"])[6:] == [0, 0])
    tab = _zitto(vf.strategie_rimaste, r)
    ordine = [vf.ORDINE_ESITI[x] for x in tab["esito"]]
    check("12. le strategie rimaste numerate da 1, prima le scelte; ogni riga ha la regola in parole",
          list(tab["numero"]) == list(range(1, len(tab) + 1)) and ordine == sorted(ordine)
          and all(x.startswith("Entra ") for x in tab["regola"]))

    print("\n5 · La cassaforte")
    prima = _registro_bytes(d)
    vuoto = _zitto(vf.cassaforte, r, "", "")
    check("13. campo vuoto: non entra niente, il registro non cambia", vuoto is None and _registro_bytes(d) == prima)
    sbagliata = errore(lambda: _zitto(vf.cassaforte, r, "tutte le scelte", "confermo"), ValueError,
                       vf.FRASE_CONFERMA)
    check("14. frase sbagliata: errore con la frase da scrivere; il registro non cambia",
          sbagliata and _registro_bytes(d) == prima)
    fam = tab[tab["esito"] != "scelta"]
    non_scelta = (errore(lambda: _zitto(vf.cassaforte, r, str(int(fam["numero"].iloc[0])), vf.FRASE_CONFERMA))
                  if len(fam) else True)
    check("15. numeri sbagliati (lettere, fuori tabella) o una strategia non «scelta»: errore; il registro non cambia",
          errore(lambda: vf.cassaforte(r, "uno", vf.FRASE_CONFERMA)) and errore(
              lambda: vf.cassaforte(r, "99", vf.FRASE_CONFERMA)) and non_scelta and _registro_bytes(d) == prima)
    c = _zitto(vf.cassaforte, r, "tutte le scelte", vf.FRASE_CONFERMA)
    scelte = list(tab[tab["esito"] == "scelta"]["id_strategia"])
    n_ingressi = len(_eventi(d, INGRESSO))
    check("16. «tutte le scelte» con la frase: entrano le scelte, un ingresso e un esito nel registro",
          c is not None and sorted(c.trade) == sorted(scelte) and n_ingressi == 1 and len(_eventi(d, ESITO)) == 1)
    dopo = _registro_bytes(d)
    c2 = _zitto(vf.cassaforte, r, "tutte le scelte", "")
    c3 = _zitto(vf.cassaforte, r, "", "")
    check("17. rieseguita (con o senza numeri, senza frase): nessun ingresso nuovo, registro identico, stesso esito",
          _registro_bytes(d) == dopo and c2.tabella.equals(c.tabella) and c3.tabella.equals(c.tabella))
    imb2 = _zitto(vf.imbuto, r)
    check("18. l'imbuto legge la cassaforte dal registro: entrate e passate",
          list(imb2["quante"])[6] == len(scelte) and list(imb2["quante"])[7] == int((c.tabella["esito"] == "passa").sum()))

    print("\n6 · MM, stress test e verifica dei trade")
    catalogo = stato_registro()
    numero = int(tab[tab["id_strategia"] == scelte[0]]["numero"].iloc[0])
    check("19. un trade da vedere scritto male, o una strategia non entrata: errore prima di ogni calcolo",
          errore(lambda: vf.mm_e_stress(r, numero, trade_da_vedere="tre")) and (
              errore(lambda: vf.mm_e_stress(r, int(fam["numero"].iloc[0]))) if len(fam) else True)
          and stato_registro() == catalogo)
    out = _zitto(vf.mm_e_stress, r, numero, simulazioni=200, simulazioni_stress=500, trade_da_vedere="1")
    with open(out["percorso"], encoding="utf-8") as f:
        salvato = json.load(f)
    check("20. money management, stress test e sempre la verifica: le regole tutte OK; il riassunto è salvato; il "
          "catalogo torna com'era", (out["verifica"]["regole"]["Esito"] == "OK").all()
          and salvato["verifica"]["regole"] and salvato["mm"]["percentuale"] == out["mm"]["f"]
          and salvato["stress"]["controllo"] and stato_registro() == catalogo,
          f"{len(out['verifica']['regole'])} regole")

    print("\n7 · Le schede")
    fatte = _zitto(vf.schede, r)
    testi = {}
    for m, j in fatte:
        with open(m, encoding="utf-8") as f:
            testi[os.path.basename(m)[:-3]] = f.read()
    con_mm = testi.get(scelte[0], "")
    check("21. una scheda .md e .json per ogni strategia entrata; quella con la 6 porta verifica e money management, "
          "le altre dicono «esegui la 6»", len(fatte) == len(scelte) and "Rischio a ogni trade" in con_mm
          and "esegui la 6" not in con_mm.split("## Blocchi")[0]
          and all("esegui la 6" in t for k, t in testi.items() if k != scelte[0]))
    a2 = _zitto(vf.avvio, d, "pc2")
    riga = a2["ricerche"].iloc[0]
    attese = int((df.index >= c.tratto["a"]).sum())
    check("22. Avvio dopo la cassaforte: la ricerca, le strategie entrate, le barre dopo l'ultima cassaforte e quante "
          "ne servono per un tratto nuovo", riga["ricerca"] == r.id_ricerca and riga["entrate in cassaforte"] == len(scelte)
          and riga["barre dopo"] == attese and riga["servono per un tratto nuovo"] == 2000,
          f"{attese} barre dopo, ne servono 2000")
    check("23. i file di questa macchina hanno il nome scritto nell'Avvio (registro_pc2.jsonl, prove_pc2.csv)",
          os.path.exists(os.path.join(cartella_asset(d, SPOT, "M15"), "registro_pc2.jsonl"))
          and os.path.exists(os.path.join(r.cartella, "prove_pc2.csv")))


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
    check("24. D1 con la config standard: la cella elenca i 5 blocchi tolti con il motivo (F20 limite logico) e "
          "prosegue: la ricerca è configurata", conf.teorie > 0 and len(tolti) == 5
          and tolti.get("F20_SESSION_OVERLAP") == LIMITE_LOGICO and "F20_SESSION_OVERLAP" not in conf.config["blocchi"],
          f"{conf.teorie} teorie")


if __name__ == "__main__":
    sys.exit(esegui())
