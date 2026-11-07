"""
La config della fabbrica (docs/82 P2 e §6, lavoro L3a).

    config = leggi_config("…/config.json")       # controlla campi e intervalli, si ferma se manca qualcosa
    impronta_config(config)                       # sha256 del contenuto in forma ordinata, seme compreso
    id_ricerca = salva_config(config, "dati")     # dati/fabbrica/<SYMBOL>_<TIMEFRAME>/<id>/config.json
    config_standard("BINANCE_PERP_BTCUSDT", "M15")

- Stessa impronta = stessa ricerca, che si può riprendere: salva_config ritorna la cartella che c'è già. Impronta
  diversa = ricerca nuova. Un file già scritto non si sovrascrive mai.
- I campi sono quelli di §6, né uno di più né uno di meno. Timeframe da M1 a D1. Sullo spot solo long.
- Il budget non si supera mai: budget_massimo è il conto dei massimi per teoria (§5), e controlla_budget si ferma se
  supera il totale prima di partire. Così non dipende dall'ordine delle teorie.
"""
from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import math
import os

from engine.exchange import simboli_exchange, solo_long

from .blocchi import (FILTRI_CATALOGO, GRIGLIE_NUOVI, GRIGLIE_USCITA, MINUTI_TIMEFRAME, TRIGGER_CATALOGO,
                      USCITE_CATALOGO, blocchi_da_config)
from .dati import Confini

VERSIONE = 1
CAMPI = ("versione", "symbol", "timeframe", "confini", "lati", "blocchi", "modelli", "qualita_1", "qualita_2",
         "altopiano", "test_individuale", "budget", "seme", "processi")
SOTTOCAMPI = {
    "qualita_1": ("trade_min", "ev_min_bp", "peso_max", "totale_su_dd_min"),
    "qualita_2": ("trade_min", "p_ev_neg_max", "peso_max", "totale_su_dd_min"),
    "altopiano": ("variazione_ore", "spostamento_min_barre", "mediana_min", "peggiore_min", "candidati_max",
                  "prove_max"),
    "test_individuale": ("alfa",),
    "budget": ("totale", "per_teoria_passo_1", "teorie_passo_2", "giri_zoom", "prove_per_giro"),
}
FILTRI_MAX = 2                         # i modelli di docs/82 P3: T+U, T+F+U, T+F+F+U
# La prima finestra (docs/82 P1 e §6)
CONFINI_STANDARD = {"inizio": "2020-01-02 00:00", "ricerca_ore": 30624, "selezione_ore": 17177.75,
                    "cassaforte_ore": 11779.5}
BLOCCHI_STANDARD = (*TRIGGER_CATALOGO, "RSI_RIENTRO", "DONCHIAN", *FILTRI_CATALOGO, "ADX", "ATR_RELATIVO",
                    *USCITE_CATALOGO)


def _errore(testo: str):
    raise ValueError(f"config: {testo}")


def _intero(valore, nome: str, minimo: int = 0) -> int:
    if isinstance(valore, bool) or not isinstance(valore, int) or valore < minimo:
        _errore(f"{nome} deve essere un intero >= {minimo}, non {valore!r}")
    return valore


def _numero(valore, nome: str, minimo=-math.inf, massimo=math.inf, aperto_sotto=False) -> float:
    if isinstance(valore, bool) or not isinstance(valore, (int, float)) or not math.isfinite(valore):
        _errore(f"{nome} deve essere un numero, non {valore!r}")
    if valore < minimo or valore > massimo or (aperto_sotto and valore == minimo):
        _errore(f"{nome} = {valore} fuori dall'intervallo ({minimo}, {massimo})")
    return float(valore)


def _campi(d, attesi, nome: str) -> None:
    if not isinstance(d, dict):
        _errore(f"{nome} deve essere un dizionario")
    mancanti, estranei = set(attesi) - set(d), set(d) - set(attesi)
    if mancanti:
        _errore(f"in {nome} mancano {sorted(mancanti)}")
    if estranei:
        _errore(f"in {nome} ci sono campi sconosciuti {sorted(estranei)}")


def controlla_config(config: dict) -> dict:
    """Controlla campi e intervalli; si ferma con un errore che dice cosa manca o cosa è fuori posto."""
    _campi(config, CAMPI, "la config")
    if config["versione"] != VERSIONE:
        _errore(f"versione {config['versione']!r}: questa fabbrica legge la versione {VERSIONE}")
    if config["symbol"] not in simboli_exchange():
        _errore(f"symbol {config['symbol']!r} fuori da SIMBOLI_EXCHANGE (engine/simboli.py)")
    if config["timeframe"] not in MINUTI_TIMEFRAME:
        _errore(f"timeframe {config['timeframe']!r} non previsto: {list(MINUTI_TIMEFRAME)}")
    Confini.da_config(config["confini"])
    lati = config["lati"]
    if not isinstance(lati, list) or not lati or len(set(lati)) != len(lati) or not set(lati) <= {"long", "short"}:
        _errore(f"lati deve essere una lista con long e/o short, non {lati!r}")
    if "short" in lati and solo_long(config["symbol"]):
        _errore(f"{config['symbol']} è uno spot: solo long (togli \"short\" dai lati)")
    if not isinstance(config["blocchi"], dict) or not config["blocchi"]:
        _errore("blocchi deve essere un dizionario non vuoto {nome: griglie}")
    blocchi = blocchi_da_config(config)                         # blocchi, parametri e timeframe
    tipi = {b.tipo for b in blocchi}
    if not {"trigger", "uscita"} <= tipi:
        _errore("servono almeno un trigger e un'uscita fra i blocchi")
    if not isinstance(config["modelli"], list) or not config["modelli"]:
        _errore("modelli deve essere una lista non vuota")
    for m in config["modelli"]:
        _campi(m, ("trigger", "filtri", "uscite"), "un modello")
        if m["trigger"] != 1 or m["uscite"] != 1:
            _errore(f"un modello ha un trigger e un'uscita: {m}")
        f = m["filtri"]
        if (not isinstance(f, list) or len(f) != 2 or not all(isinstance(x, int) and not isinstance(x, bool) for x in f)
                or not 0 <= f[0] <= f[1] <= FILTRI_MAX):
            _errore(f"filtri di un modello = [minimo, massimo], da 0 a {FILTRI_MAX}: {f!r}")
    for nome, sotto in SOTTOCAMPI.items():
        _campi(config[nome], sotto, nome)
    q1, q2, alt, bud = config["qualita_1"], config["qualita_2"], config["altopiano"], config["budget"]
    for q, nome in ((q1, "qualita_1"), (q2, "qualita_2")):
        _intero(q["trade_min"], f"{nome}.trade_min", 2)
        _numero(q["peso_max"], f"{nome}.peso_max", 0.0, 1.0, aperto_sotto=True)
        _numero(q["totale_su_dd_min"], f"{nome}.totale_su_dd_min", 0.0)
    _numero(q1["ev_min_bp"], "qualita_1.ev_min_bp")
    _numero(q2["p_ev_neg_max"], "qualita_2.p_ev_neg_max", 0.0, 100.0)
    _numero(alt["variazione_ore"], "altopiano.variazione_ore", 0.0, 1.0, aperto_sotto=True)
    _intero(alt["spostamento_min_barre"], "altopiano.spostamento_min_barre", 1)
    _numero(alt["mediana_min"], "altopiano.mediana_min", 0.0, 1.0)
    _numero(alt["peggiore_min"], "altopiano.peggiore_min", 0.0, 1.0)
    _intero(alt["candidati_max"], "altopiano.candidati_max", 1)
    _intero(alt["prove_max"], "altopiano.prove_max", 0)
    _numero(config["test_individuale"]["alfa"], "test_individuale.alfa", 0.0, 1.0, aperto_sotto=True)
    for k in SOTTOCAMPI["budget"]:
        _intero(bud[k], f"budget.{k}", 1)
    _intero(config["seme"], "seme", 0)
    _intero(config["processi"], "processi", 1)
    if config["processi"] > (os.cpu_count() or 1):
        _errore(f"processi = {config['processi']}, più dei core del PC ({os.cpu_count()})")
    return config


def budget_massimo(n_teorie: int, config: dict) -> int:
    """Il conto dei massimi per teoria (docs/82 §5): passo 1, zoom, altopiano, selezione, cassaforte."""
    b, alt = config["budget"], config["altopiano"]
    t2 = min(b["teorie_passo_2"], n_teorie)
    return (n_teorie * b["per_teoria_passo_1"] + t2 * b["giri_zoom"] * b["prove_per_giro"] + t2 * alt["prove_max"]
            + 2 * t2)


def controlla_budget(n_teorie: int, config: dict) -> int:
    """Si ferma prima di partire se i massimi superano il totale: così il budget non si supera mai."""
    massimo = budget_massimo(n_teorie, config)
    if massimo > config["budget"]["totale"]:
        _errore(f"con {n_teorie} teorie i massimi fanno {massimo} prove, oltre il totale di "
                f"{config['budget']['totale']}: riduci blocchi o prove per teoria")
    return massimo


def leggi_config(percorso) -> dict:
    with open(percorso, encoding="utf-8") as f:
        config = json.load(f)
    return controlla_config(config)


def _testo(config: dict) -> str:
    return json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def impronta_config(config: dict) -> str:
    """sha256 del contenuto in forma ordinata (chiavi in ordine), seme compreso."""
    return hashlib.sha256(_testo(config).encode("utf-8")).hexdigest()


def cartella_asset(cartella_dati, symbol: str, timeframe: str) -> str:
    """dati/fabbrica/<SYMBOL>_<TIMEFRAME>: l'unico posto dove la fabbrica scrive (docs/82 §6)."""
    return os.path.join(str(cartella_dati), "fabbrica", f"{symbol}_{timeframe}")


def salva_config(config: dict, cartella_dati, data: str | None = None) -> str:
    """
    Scrive config.json in una cartella nuova e ritorna l'id della ricerca (data + inizio dell'impronta). Se una
    ricerca con la stessa impronta c'è già, ritorna il suo id senza scrivere: è una ripresa. Non sovrascrive mai.
    """
    controlla_config(config)
    impronta = impronta_config(config)
    base = cartella_asset(cartella_dati, config["symbol"], config["timeframe"])
    os.makedirs(base, exist_ok=True)
    for nome in sorted(os.listdir(base)):
        if nome.endswith("_" + impronta[:12]) and os.path.isdir(os.path.join(base, nome)):
            percorso = os.path.join(base, nome, "config.json")
            if os.path.exists(percorso):
                with open(percorso, encoding="utf-8") as f:
                    if impronta_config(json.load(f)) != impronta:
                        raise ValueError(f"config: {percorso} ha un'altra impronta: non si sovrascrive.")
                return nome
    data = data or _dt.date.today().strftime("%Y%m%d")
    id_ricerca = f"{data}_{impronta[:12]}"
    cartella = os.path.join(base, id_ricerca)
    os.makedirs(cartella, exist_ok=False)
    with open(os.path.join(cartella, "config.json"), "x", encoding="utf-8") as f:
        f.write(json.dumps(config, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False))
    return id_ricerca


def config_standard(symbol: str, timeframe: str = "M15", seme: int = 0, processi: int = 3) -> dict:
    """
    La config di §6 con tutti i blocchi di P-L2 ammessi sul timeframe e le loro griglie. I blocchi del catalogo che
    su quel timeframe non scattano restano fuori (blocchi.py li fermerebbe).
    """
    blocchi = {}
    for nome in BLOCCHI_STANDARD:
        try:
            blocchi_da_config({"timeframe": timeframe, "blocchi": {nome: {}}})
        except ValueError:
            continue
        # griglie scritte per intero: se un giorno cambia una griglia nel codice, cambia anche l'impronta
        griglie = GRIGLIE_NUOVI.get(nome, GRIGLIE_USCITA if nome in USCITE_CATALOGO else {})
        blocchi[nome] = copy.deepcopy({k: list(v) for k, v in griglie.items()})
    return {
        "versione": VERSIONE, "symbol": symbol, "timeframe": timeframe,
        "confini": dict(CONFINI_STANDARD),
        "lati": ["long"] if solo_long(symbol) else ["long", "short"],
        "blocchi": blocchi,
        "modelli": [{"trigger": 1, "filtri": [0, 2], "uscite": 1}],
        "qualita_1": {"trade_min": 100, "ev_min_bp": 0, "peso_max": 0.10, "totale_su_dd_min": 1.0},
        "qualita_2": {"trade_min": 50, "p_ev_neg_max": 5.0, "peso_max": 0.15, "totale_su_dd_min": 0.5},
        "altopiano": {"variazione_ore": 0.15, "spostamento_min_barre": 1, "mediana_min": 0.7, "peggiore_min": 0.4,
                      "candidati_max": 3, "prove_max": 60},
        "test_individuale": {"alfa": 0.05},
        "budget": {"totale": 100000, "per_teoria_passo_1": 40, "teorie_passo_2": 150, "giri_zoom": 3,
                   "prove_per_giro": 90},
        "seme": seme, "processi": processi,
    }
