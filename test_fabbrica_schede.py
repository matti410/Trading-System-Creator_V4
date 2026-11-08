"""
Suite di collaudo delle schede della fabbrica e dei blocchi tolti per timeframe (docs/82 P10 e §6, lavoro L5a).

Si lancia da terminale, dalla cartella del progetto:

    python test_fabbrica_schede.py

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

from engine.fabbrica import registro, sintetici
from engine.fabbrica import schede as sch
from engine.fabbrica import sessione as ses
from engine.fabbrica.blocchi import (APPROSSIMAZIONE_ESCLUSA, LIMITE_LOGICO, MINUTI_TIMEFRAME, MOTIVI_ESCLUSIONE,
                                     SOLO_ELENCO, blocchi_da_config)
from engine.fabbrica.cassaforte import FRASE_CONFERMA, entra
from engine.fabbrica.config import blocchi_esclusi, config_standard, controlla_tipi_rimasti
from engine.fabbrica.ricerca import lancia
from engine.fabbrica.valutatore import Strategia, id_strategia

warnings.simplefilter("ignore")
matplotlib.use("Agg")

PERP, SPOT = "BINANCE_PERP_BTCUSDT", "BYBIT_SPOT_ETHUSDT"
DATA = "20260101"
ORA_FISSA = "2026-01-01T00:00:00+00:00"
CONFINI = {"inizio": "2024-01-01 00:00", "ricerca_ore": 3000, "selezione_ore": 2000, "cassaforte_ore": 500}
CONFINI_H1 = {"inizio": "2024-01-01 00:00", "ricerca_ore": 12000, "selezione_ore": 8000, "cassaforte_ore": 2000}
BLOCCHI = ("DONCHIAN", "RSI_RIENTRO", "F3_VOLUME_ABOVE_AVG", "ADX", "X0", "X3")
ESITI: list[bool] = []

# La tabella decisa da Mattia l'08/11 (diagnosi di E36, E47, E49, E51; F20 su D1)
ATTESI = {
    "M1": {"E47": SOLO_ELENCO, "E49": SOLO_ELENCO, "E51": SOLO_ELENCO},
    "M5": {}, "M15": {},
    "M30": {"E47": APPROSSIMAZIONE_ESCLUSA},
    "H1": {"E36": LIMITE_LOGICO, "E47": LIMITE_LOGICO},
    "H4": {"E36": LIMITE_LOGICO, "E47": LIMITE_LOGICO, "E49": LIMITE_LOGICO, "E51": APPROSSIMAZIONE_ESCLUSA},
    "D1": {"E36": LIMITE_LOGICO, "E47": LIMITE_LOGICO, "E49": LIMITE_LOGICO, "E51": LIMITE_LOGICO,
           "F20_SESSION_OVERLAP": LIMITE_LOGICO},
}
CAMPI_SCHEDA = ("id_strategia", "id_ricerca", "impronta_config", "impronte_dati", "symbol", "timeframe", "lato",
                "blocchi", "uscita", "regole", "esiti", "altopiano", "test_individuale", "prove", "cassaforte", "mm",
                "stress", "software", "blocchi_esclusi", "verifica")


def check(nome: str, ok: bool, dettaglio: str = "") -> None:
    ESITI.append(bool(ok))
    print(f"[{'OK ' if ok else 'KO '}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""))


def errore(funzione, tipo=Exception) -> bool:
    try:
        funzione()
    except tipo:
        return True
    return False


def _zitto(funzione, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return funzione(*a, **k)


def _cfg(symbol, timeframe="M15", confini=CONFINI, blocchi=BLOCCHI):
    cfg = config_standard(symbol, timeframe, seme=0, processi=1)
    cfg["confini"] = dict(confini)
    cfg["blocchi"] = {k: v for k, v in cfg["blocchi"].items() if k in blocchi}
    cfg["qualita_1"]["trade_min"] = 30
    cfg["budget"].update({"teorie_passo_2": 4, "prove_per_giro": 60})
    return cfg


def _mercato(minuti=15, confini=CONFINI):
    n = int((confini["ricerca_ore"] + confini["selezione_ore"] + confini["cassaforte_ore"]) * 60 / minuti) + 100
    return sintetici.mercato_piantato(n, seme=5, minuti=minuti, inizio="2024-01-01", prezzo=2_000.0)


def esegui() -> int:
    t0 = time.perf_counter()
    registro_adesso = registro.adesso
    registro.adesso = lambda: ORA_FISSA
    try:
        _testi()
        _esclusi()
        with tempfile.TemporaryDirectory() as radice:
            _giro(radice, SPOT, "M15", CONFINI)
            _giro(radice, PERP, "H1", CONFINI_H1)
    finally:
        registro.adesso = registro_adesso
    print("\n" + "=" * 70)
    print(f"Durata: {time.perf_counter() - t0:.0f} s")
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


# ------------------------------------------------------------------ i testi dei blocchi
def _testi():
    print("Le regole in parole (docs/82 P10)")
    check("1. ogni blocco della lista di P-L2 ha il suo testo in parole", sch.blocchi_senza_testo() == [],
          f"senza testo: {sch.blocchi_senza_testo()}")
    casi = {(48, 15): "12 ore (48 barre)", (3, 15): "45 minuti (3 barre)", (1, 60): "1 ora (1 barra)",
            (10, 15): "2,5 ore (10 barre)", (5, 1440): "120 ore (5 barre)", (1, 1): "1 minuto (1 barra)"}
    sbagliati = {k: sch.durata(*k) for k, v in casi.items() if sch.durata(*k) != v}
    check("2. le durate in parole, in ore e in barre del timeframe", not sbagliati, f"diversi: {sbagliati}")

    st = Strategia(1, "DONCHIAN", ("F3_VOLUME_ABOVE_AVG",), "X3",
                   (("DONCHIAN", (("canale_barre", 48),)), ("F3_VOLUME_ABOVE_AVG", ()),
                    ("X3", (("durata_barre", 16), ("perc_stop", 90), ("target", None)))))
    righe = sch.regole_in_parole(st, "M15")["righe"]
    attese = [
        "Entra long all'apertura della barra dopo quella in cui il Close supera il massimo degli High delle 12 ore "
        "(48 barre) precedenti.",
        "Solo se il volume della barra è sopra la sua media delle ultime 5 ore (20 barre).",
        "Esce dopo 4 ore (16 barre), oppure quando il MACD scende sotto la sua signal, oppure allo stop: la distanza "
        "che contiene il 90% delle escursioni contrarie dei trade di 4 ore (16 barre) delle ultime 125 ore (500 barre), "
        "quello che arriva prima; target spento."]
    check("3. una strategia nota in parole, frase per frase (Donchian long, filtro sul volume, uscita MACD)",
          righe == attese, f"{righe}")
    st_s = Strategia(-1, "RSI_RIENTRO", ("ADX", "TREND_CONTEXT"), "X0",
                     (("RSI_RIENTRO", (("periodo_barre", 4), ("soglia", 30))),
                      ("ADX", (("periodo_barre", 6), ("soglia", 25))), ("TREND_CONTEXT", ()),
                      ("X0", (("durata_barre", 8), ("perc_stop", 80), ("target", 90)))))
    r_s = sch.regole_in_parole(st_s, "H1")["righe"]
    check("4. lo short su H1: soglia speculare dell'RSI (100 − 30 = 70), due filtri, target acceso",
          r_s[0].startswith("Entra short") and "l'RSI di 4 ore (4 barre) scende sotto 70 da sopra" in r_s[0]
          and "contiene l'80% delle escursioni contrarie" in r_s[2]
          and r_s[1] == "Solo se l'ADX di 6 ore (6 barre) è sopra 25 e se il Close è sotto la media esponenziale di "
                        "50 ore (50 barre)."
          and "al target: la distanza che contiene il 90% delle escursioni favorevoli" in r_s[2]
          and "target spento" not in r_s[2], f"{r_s}")

    rotti = []
    for tf in MINUTI_TIMEFRAME:
        cfg = config_standard(SPOT, tf)
        per_tipo = {"trigger": [], "filtro": [], "uscita": []}
        for b in blocchi_da_config(cfg):
            per_tipo[b.tipo].append(b)
        for lato in (1, -1):
            for i, t in enumerate(per_tipo["trigger"]):
                f = per_tipo["filtro"][i % len(per_tipo["filtro"])]
                u = per_tipo["uscita"][i % len(per_tipo["uscita"])]
                for filtri in ((), (f,)):
                    valori = {b.nome: b.centrali() for b in (t, *filtri, u)}
                    s = Strategia(lato, t.nome, tuple(x.nome for x in filtri), u.nome,
                                  tuple((n, tuple(sorted(v.items()))) for n, v in valori.items()))
                    try:
                        righe = sch.regole_in_parole(s, tf)["righe"]
                        if any("{" in x or "None" in x for x in righe):
                            rotti.append((tf, t.nome, lato))
                    except Exception as e:  # noqa: BLE001
                        rotti.append((tf, t.nome, lato, repr(e)))
        for f in per_tipo["filtro"]:
            for lato in (1, -1):
                t, u = per_tipo["trigger"][0], per_tipo["uscita"][0]
                valori = {b.nome: b.centrali() for b in (t, f, u)}
                s = Strategia(lato, t.nome, (f.nome,), u.nome,
                              tuple((n, tuple(sorted(v.items()))) for n, v in valori.items()))
                try:
                    sch.regole_in_parole(s, tf)
                except Exception as e:  # noqa: BLE001
                    rotti.append((tf, f.nome, lato, repr(e)))
    check("5. ogni blocco ammesso, su ogni timeframe da M1 a D1 e sui due lati, si scrive in parole senza errori",
          not rotti, f"{rotti[:4]}")


# ------------------------------------------------------------------ i blocchi tolti
def _esclusi():
    print("\nI blocchi tolti per timeframe, con il motivo (Mattia, 08/11)")
    trovati = {tf: {e["blocco"]: e["tipo"] for e in blocchi_esclusi(tf)} for tf in MINUTI_TIMEFRAME}
    check("6. i blocchi tolti su ogni timeframe e il tipo di motivo sono quelli decisi (limite logico, approssimazione "
          "esclusa per scelta, escluso solo dall'elenco)", trovati == ATTESI,
          f"diversi: {[tf for tf in ATTESI if trovati[tf] != ATTESI[tf]]}")
    usati = {(b, tf) for tf, d in ATTESI.items() for b in d}
    check("7. nessun blocco esce in silenzio: ogni blocco tolto dalla config standard ha il motivo, e ogni motivo "
          "scritto corrisponde a un blocco tolto", set(MOTIVI_ESCLUSIONE) == usati
          and all(len(m) == 2 and m[1] for m in MOTIVI_ESCLUSIONE.values()))
    cfg = config_standard(SPOT, "D1")
    tolti = sch.esclusi_dalla_config(cfg)
    cfg_r = dict(cfg, blocchi={k: v for k, v in cfg["blocchi"].items() if k != "ADX"})
    tolti_r = {e["blocco"]: e["tipo"] for e in sch.esclusi_dalla_config(cfg_r)}
    check("8. sulla config standard l'elenco della scheda è quello del timeframe; un blocco tolto a mano è «tolto "
          "dalla config»", tolti == blocchi_esclusi("D1") and tolti_r.get("ADX") == sch.TOLTO_DALLA_CONFIG
          and tolti_r.get("F20_SESSION_OVERLAP") == LIMITE_LOGICO)
    senza_t = dict(cfg, blocchi={k: v for k, v in cfg["blocchi"].items() if k not in ("E5", "RSI_RIENTRO", "DONCHIAN")})
    senza_u = dict(cfg, blocchi={k: v for k, v in cfg["blocchi"].items() if k not in ("X0", "X1", "X3")})
    check("9. si ferma solo se non resta un trigger o un'uscita; la config standard di D1 parte",
          errore(lambda: controlla_tipi_rimasti(senza_t)) and errore(lambda: controlla_tipi_rimasti(senza_u))
          and not errore(lambda: controlla_tipi_rimasti(cfg)))


# ------------------------------------------------------------------ la scheda su un giro intero
def _giro(radice, symbol, timeframe, confini):
    n = 10 if timeframe == "M15" else 15
    print(f"\nLa scheda su un giro intero: {symbol} {timeframe} (P10)")
    d = os.path.join(radice, timeframe)
    df = _mercato(MINUTI_TIMEFRAME[timeframe], confini)
    sintetici.scrivi_storico(d, symbol, timeframe, df)
    if symbol == PERP:
        sintetici.scrivi_funding(d, symbol, df, seme=3)
    e = lancia(_cfg(symbol, timeframe, confini), d, verbose=False, data=DATA)
    scelte = list(e.selezione.scelte["id_strategia"])
    if not scelte:
        check(f"{n}. il giro arriva in cassaforte", False, f"nessuna scelta: imbuto {e.imbuto}")
        return
    c = entra(d, e.id_ricerca, scelte, FRASE_CONFERMA)
    id0 = scelte[0]
    sc = sch.componi_scheda(e, c, id0, None)
    md, js = sch.scrivi_scheda(sc, os.path.join(radice, f"schede_{timeframe}"))
    letta = sch.leggi_scheda(js)
    with ses.sessione(c, id0) as s:
        trades_is = s.trades_is.copy()
    rifatti = sch.trade_da_scheda(letta, d)
    check(f"{n}. dalla sola scheda .json gli stessi trade, al bit: in-sample (quelli della Sessione) e cassaforte "
          f"(quelli di entra)", rifatti["in_sample"].equals(trades_is) and rifatti["cassaforte"].equals(c.trade[id0])
          and len(rifatti["cassaforte"]) > 0,
          f"{len(rifatti['in_sample'])} trade in-sample, {len(rifatti['cassaforte'])} in cassaforte")
    check(f"{n + 1}. il .json ha i campi di §6, più i blocchi tolti e la verifica; si rilegge identico",
          all(k in letta for k in CAMPI_SCHEDA) and letta == json.loads(json.dumps(sc)) and letta["mm"] is None
          and letta["verifica"] is None and letta["impronte_dati"]["cassaforte"]
          and [x["passo"] for x in letta["esiti"]] == ["passo 1", "zoom e altopiano", "selezione", "cassaforte"])
    with open(md, encoding="utf-8") as f:
        testo = f.read()
    sezioni = ("## Regole", "## Da dove viene", "## Il cammino", "## Da leggere", "## Verifica dei trade",
               "## Money management e stress test", "## Blocchi tolti su questo timeframe")
    check(f"{n + 2}. il .md ha le sezioni, le regole in parole, «non calcolati» senza la 6, e finisce con la frase "
          f"«{sch.FRASE_FINALE}»", all(x in testo for x in sezioni) and testo.rstrip().endswith(sch.FRASE_FINALE)
          and all(r in testo for r in letta["regole"]) and "esegui la 6" in testo
          and sch.leggi_scheda(md) == letta)
    altra = json.loads(json.dumps(letta))
    chiave = next(iter(altra["strategia"]["valori"][altra["strategia"]["trigger"]]), None)
    if chiave:
        altra["strategia"]["valori"][altra["strategia"]["trigger"]][chiave] += 1
    else:
        altra["strategia"]["lato"] = -altra["strategia"]["lato"]
    impronta_rotta = json.loads(json.dumps(letta))
    impronta_rotta["impronte_dati"]["cassaforte"] = "0" * 64
    non_entrata = json.loads(json.dumps(altra))
    st_nuova = Strategia(int(altra["strategia"]["lato"]), altra["strategia"]["trigger"],
                         tuple(altra["strategia"]["filtri"]), altra["strategia"]["uscita"],
                         tuple((k, tuple(sorted(altra["strategia"]["valori"].get(k, {}).items())))
                               for k in (altra["strategia"]["trigger"], *altra["strategia"]["filtri"],
                                         altra["strategia"]["uscita"])))
    non_entrata["id_strategia"] = id_strategia(st_nuova, symbol, timeframe)
    ferma_entrata = False
    try:
        sch.trade_da_scheda(non_entrata, d)
    except ValueError as x:
        ferma_entrata = "non è entrata" in str(x)
    check(f"{n + 3}. un valore cambiato nella scheda: la strategia non torna (errore); impronte dei dati diverse: "
          f"errore; una strategia mai entrata non riapre la cassaforte",
          errore(lambda: sch.strategia_da_scheda(altra)) and errore(lambda: sch.trade_da_scheda(impronta_rotta, d))
          and ferma_entrata)
    ins = sch.componi_scheda(e, c, id0, {"mm": {"modello": "rischio fisso", "percentuale": 0.01, "deciso": "x",
                                                "sintesi": []},
                                         "stress": None, "verifica": {"regole": [{"Regola": "r", "Esito": "OK"}]},
                                         "parametri": {"capitale": 10000.0, "drawdown_max_pct": 20.0, "anni": 1.0,
                                                       "modello": "rischio fisso", "leva": 0.0}})
    testo_mm = sch.testo_md(ins)
    check(f"{n + 4}. con il riassunto della 6 la scheda porta verifica e money management", ins["verifica"]["regole"]
          and "| r | OK |" in testo_mm and "la massima del symbol" in testo_mm and "Rischio a ogni trade: 1,00 %" in testo_mm)


if __name__ == "__main__":
    sys.exit(esegui())
