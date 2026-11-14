"""
La config della fabbrica (docs/82 P2 e §6, lavoro L3a).

    config = leggi_config("…/config.json")       # controlla campi e intervalli, si ferma se manca qualcosa
    impronta_config(config)                       # sha256 del contenuto in forma ordinata, seme compreso, processi esclusi
    id_ricerca = salva_config(config, "dati")     # dati/fabbrica/<SYMBOL>_<TIMEFRAME>/<id>/config.json
    config_standard("BINANCE_PERP_BTCUSDT", "M15")
    confini_standard("M15", ultima_barra, prima_barra)   # (09/11) fino all'ultima mezzanotte UTC chiusa; (14/11) inizio

- Stessa impronta = stessa ricerca, che si può riprendere: salva_config ritorna la cartella che c'è già. Impronta
  diversa = ricerca nuova. Un file già scritto non si sovrascrive mai.
- `processi` non entra nell'impronta (08/11): non cambia i risultati (collaudato: 1 processo = 3 processi), quindi la
  stessa ricerca si può riprendere con un altro numero di processi. Il config.json resta quello del primo salvataggio.
- I campi sono quelli di §6, né uno di più né uno di meno. Timeframe da M1 a D1. Sullo spot solo long.
- Il budget non si supera mai: budget_massimo è il conto dei massimi per teoria (§5), e controlla_budget si ferma se
  supera il totale prima di partire. Così non dipende dall'ordine delle teorie.
- C2 (docs/82 §11, D5 = B): solo la versione 2, una strada sola. In `budget` la chiave `teorie_turno_2` (le teorie T+F
  del turno 1 a cui il turno 2 aggiunge un secondo filtro). Il totale della config standard è il tetto (D6): il
  massimo arrotondato in su ai 10.000 (tetto_budget). La cella 1 lo calcola sui blocchi tenuti del pezzo di ricerca;
  senza dati, config_standard usa il massimo con tutti i blocchi (mai più piccolo). I blocchi standard sono tutto il
  catalogo (C1), più RSI, Donchian, ADX e ATR relativo, e le tre uscite.
"""
from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import math
import os

from engine.exchange import simboli_exchange, solo_long

from .blocchi import GRIGLIE_NUOVI, GRIGLIE_USCITA, MINUTI_TIMEFRAME, MOTIVI_ESCLUSIONE, USCITE_CATALOGO, blocchi_da_config
from .dati import Confini

VERSIONE = 2                           # C2 (D5 = B): le ricerche della versione 1 restano su disco e nel conto
CAMPI = ("versione", "symbol", "timeframe", "confini", "lati", "blocchi", "modelli", "qualita_1", "qualita_2",
         "altopiano", "test_individuale", "budget", "seme", "processi")
SOTTOCAMPI = {
    "qualita_1": ("trade_min", "ev_min_bp", "peso_max", "totale_su_dd_min"),
    "qualita_2": ("trade_min", "p_ev_neg_max", "peso_max", "totale_su_dd_min"),
    "altopiano": ("variazione_ore", "spostamento_min_barre", "mediana_min", "peggiore_min", "candidati_max",
                  "prove_max"),
    "test_individuale": ("alfa",),
    "budget": ("totale", "per_teoria_passo_1", "teorie_turno_2", "teorie_passo_2", "giri_zoom", "prove_per_giro"),
}
FILTRI_MAX = 2                         # i modelli di docs/82 P3: T+U, T+F+U, T+F+F+U
# La prima finestra (docs/82 P1 e §6). Dal 09/11 dà solo l'inizio fisso e le proporzioni dei tre pezzi:
# la cella 1 calcola i confini con confini_standard, fino all'ultima mezzanotte UTC chiusa del CSV.
CONFINI_STANDARD = {"inizio": "2020-01-02 00:00", "ricerca_ore": 30624, "selezione_ore": 17177.75,
                    "cassaforte_ore": 11779.5}
# La lista di P-L2 (docs/82 §8), la config standard fino a C1: i 14 trigger e filtri più le tre uscite.
BLOCCHI_P_L2 = ("E5", "E36", "E47", "E49", "E51", "RSI_RIENTRO", "DONCHIAN", "F2_MID_VOLATILITY", "F3_VOLUME_ABOVE_AVG",
                "TREND_CONTEXT", "F25_CHOP_TREND", "F20_SESSION_OVERLAP", "ADX", "ATR_RELATIVO", "X0", "X3", "X1")
# I blocchi della config standard (C2, docs/82 §11.2), scritti per intero: tutti i trigger del catalogo in ordine di
# numero, RSI e Donchian; i filtri del catalogo (F36 escluso; le coppie con un verso nel posto del loro primo numero, i
# due VWAP in fondo), ADX e ATR relativo; le tre uscite. L'ordine è quello delle teorie e dei filtri nell'id della teoria.
BLOCCHI_STANDARD = (
    "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10", "E11", "E12", "E13", "E16", "E19", "E21", "E22", "E23",
    "E24", "E25", "E26", "E27", "E28", "E29", "E30", "E31", "E32", "E33", "E34", "E35", "E36", "E37", "E38", "E39", "E40",
    "E41", "E45", "E46", "E47", "E48", "E49", "E51", "E52", "RSI_RIENTRO", "DONCHIAN",
    "F1_ADX_ABOVE", "F2_MID_VOLATILITY", "F2_HIGH_VOLATILITY", "F3_VOLUME_ABOVE_AVG", "MACD_SIGNAL", "TREND_CONTEXT",
    "TREND_CONVICTION", "F14_LOW_DRIFT_REGIME", "F15_SHORT_TERM_CONSISTENCY", "F20_SESSION_ASIA", "F20_SESSION_EUROPE",
    "F20_SESSION_US", "F20_SESSION_OVERLAP", "OVERNIGHT_RETURN", "F22_FAR_FROM_ROLLOVER", "F23_CYCLE_STRENGTH", "TWO_BARS",
    "F25_CHOP_TREND", "F25_CHOP_RANGE", "F26_VARIANCE_RATIO_TREND", "VFI_SIGN", "F29_RVOL_LOW", "F32_KER_RANGE",
    "F35_JDH_REGIME_TREND", "F39_INSIDE_DAY", "ALGOX_STATE", "VWAP_GAP_WIDENING", "VWAP_SESSION_CLOSE", "ADX",
    "ATR_RELATIVO",
    "X0", "X3", "X1")
TETTO_ARROTONDA = 10_000               # D6: il tetto è il massimo arrotondato in su ai 10.000


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
        _errore(f"versione {config['versione']!r}: questa fabbrica legge solo la versione {VERSIONE} (docs/82 §11, "
                "D5): una ricerca della versione 1 resta su disco e nel conto, rilancia la cella 2 per una ricerca nuova")
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


def budget_massimo(n_teorie: int, config: dict, teorie_tf: int = 0, filtri_lato_max: int = 0) -> int:
    """
    Il conto dei massimi per teoria (docs/82 §5 e §11.5): turno 1 (`n_teorie` × prove per teoria), turno 2
    (min(`teorie_turno_2`, `teorie_tf`) × (`filtri_lato_max` − 1) × prove per teoria, se i modelli ammettono due
    filtri), poi zoom, altopiano, selezione e cassaforte sulle `teorie_passo_2` (non più delle teorie dei due turni).
    `teorie_tf` = le teorie T+F del turno 1; `filtri_lato_max` = i filtri tenuti del lato che ne ha di più.
    """
    b, alt = config["budget"], config["altopiano"]
    due = any(m["filtri"][1] >= 2 for m in config["modelli"])
    turno_2 = min(b["teorie_turno_2"], teorie_tf) * max(filtri_lato_max - 1, 0) if due else 0
    t2 = min(b["teorie_passo_2"], n_teorie + turno_2)
    return ((n_teorie + turno_2) * b["per_teoria_passo_1"] + t2 * b["giri_zoom"] * b["prove_per_giro"]
            + t2 * alt["prove_max"] + 2 * t2)


def tetto_budget(massimo: int) -> int:
    """D6: il massimo arrotondato in su ai 10.000 (370.200 → 380.000)."""
    return int(math.ceil(int(massimo) / TETTO_ARROTONDA) * TETTO_ARROTONDA)


def controlla_budget(n_teorie: int, config: dict, teorie_tf: int = 0, filtri_lato_max: int = 0) -> int:
    """Si ferma prima di partire se i massimi superano il totale: così il budget non si supera mai."""
    massimo = budget_massimo(n_teorie, config, teorie_tf, filtri_lato_max)
    if massimo > config["budget"]["totale"]:
        _errore(f"con {n_teorie} teorie al turno 1 i massimi fanno {massimo} prove, oltre il totale di "
                f"{config['budget']['totale']}: riduci blocchi o prove per teoria")
    return massimo


def massimo_senza_dati(config: dict) -> int:
    """
    Il massimo con tutti i blocchi della config, come se nessuno uscisse per i valori degeneri o per le famiglie: non
    è mai più piccolo di quello della ricerca vera. Serve a config_standard quando non ha i dati.
    """
    from .generatore import _filtri_modelli, lati_config
    blocchi = blocchi_da_config(config)
    k = _filtri_modelli(config) & {0, 1}
    uscite = sum(1 for b in blocchi if b.tipo == "uscita")
    n1 = tf = f_max = 0
    for lato in lati_config(config):
        t = sum(1 for b in blocchi if b.tipo == "trigger" and lato in b.lati)
        f = sum(1 for b in blocchi if b.tipo == "filtro")
        n1 += t * ((0 in k) + (f if 1 in k else 0)) * uscite
        tf += t * (f if 1 in k else 0) * uscite
        f_max = max(f_max, f)
    return budget_massimo(n1, config, tf, f_max)


def leggi_config(percorso) -> dict:
    with open(percorso, encoding="utf-8") as f:
        config = json.load(f)
    return controlla_config(config)


def _testo(config: dict) -> str:
    return json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


FUORI_IMPRONTA = ("processi",)       # campi che non cambiano i risultati (docs/82 §6, 08/11)


def impronta_config(config: dict) -> str:
    """sha256 del contenuto in forma ordinata (chiavi in ordine), seme compreso, senza i campi di FUORI_IMPRONTA."""
    contenuto = {k: v for k, v in config.items() if k not in FUORI_IMPRONTA}
    return hashlib.sha256(_testo(contenuto).encode("utf-8")).hexdigest()


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


def inizio_dati(prima_barra=None) -> str:
    """
    (14/11, Mattia, scelta B) L'inizio della ricerca: il 02/01/2020 00:00 UTC (CONFINI_STANDARD), oppure la prima
    mezzanotte UTC che ha già i dati, se viene dopo (un symbol nato dopo, per esempio XRP perp: dati dal 06/01/2020
    08:15, la ricerca parte dal 07/01/2020). `prima_barra` = l'inizio della prima barra del CSV (UTC).
    """
    import pandas as pd
    if prima_barra is None:
        return CONFINI_STANDARD["inizio"]
    fisso = pd.Timestamp(CONFINI_STANDARD["inizio"], tz="UTC")
    t = pd.Timestamp(prima_barra)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    mezzanotte = t.ceil("D")
    return CONFINI_STANDARD["inizio"] if mezzanotte <= fisso else mezzanotte.strftime("%Y-%m-%d %H:%M")


def confini_standard(timeframe: str, ultima_barra, prima_barra=None) -> dict:
    """
    (09/11, decisioni di Mattia) I confini standard sui dati di oggi: inizio fisso (CONFINI_STANDARD), fine = l'ultima
    mezzanotte UTC chiusa, cioè la mezzanotte alla chiusura dell'ultima barra chiusa del CSV o quella prima
    (`ultima_barra` = il suo inizio, UTC; su D1 è la chiusura stessa). Così nella stessa giornata UTC la cella 1 dà la
    stessa ricerca anche con barre nuove. I tre pezzi stanno nelle proporzioni di CONFINI_STANDARD (30624 : 17177,75 :
    11779,5 ore); ogni confine cade all'inizio di una barra del timeframe, la più vicina (a metà strada verso l'alto).
    Ritorna il dizionario «confini» della config, con le ore risultanti.
    (14/11, scelta B) Con `prima_barra` (la prima barra del CSV) l'inizio è inizio_dati(prima_barra): il 02/01/2020, o la
    prima mezzanotte UTC con i dati se viene dopo; le proporzioni dei tre pezzi si calcolano da lì. Senza, o con dati dal
    02/01/2020 o prima, tutto come prima: stessi confini, stessa impronta.
    """
    import pandas as pd
    if timeframe not in MINUTI_TIMEFRAME:
        raise ValueError(f"timeframe {timeframe!r} non previsto: {list(MINUTI_TIMEFRAME)}")
    passo = pd.Timedelta(minutes=MINUTI_TIMEFRAME[timeframe])
    testo_inizio = inizio_dati(prima_barra)
    inizio = pd.Timestamp(testo_inizio, tz="UTC")
    t = pd.Timestamp(ultima_barra)
    chiusura = (t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")) + passo
    if (chiusura - inizio) % passo != pd.Timedelta(0):
        raise ValueError(f"l'ultima barra ({t}) non cade all'inizio di una barra {timeframe} contata dal "
                         f"{testo_inizio} UTC.")
    fine = chiusura.floor("D")                   # l'ultima mezzanotte UTC chiusa (09/11)
    barre = (fine - inizio) // passo
    ore = [float(CONFINI_STANDARD[k]) for k in ("ricerca_ore", "selezione_ore", "cassaforte_ore")]
    totale = sum(ore)
    b1 = math.floor(barre * ore[0] / totale + 0.5)
    b2 = math.floor(barre * (ore[0] + ore[1]) / totale + 0.5)
    if not 0 < b1 < b2 < barre:
        raise ValueError(f"dal {testo_inizio} UTC all'ultima barra ci sono {barre} barre {timeframe}: "
                         "troppo poche per tre pezzi.")
    def in_ore(n):        # intere come intero (30624, non 30624.0): stessa config, stessa impronta di CONFINI_STANDARD
        v = round(n * MINUTI_TIMEFRAME[timeframe] / 60.0, 6)
        return int(v) if v == int(v) else v

    return {"inizio": testo_inizio, "ricerca_ore": in_ore(b1), "selezione_ore": in_ore(b2 - b1),
            "cassaforte_ore": in_ore(barre - b2)}


def config_standard(symbol: str, timeframe: str = "M15", seme: int = 0, processi: int = 3,
                    confini: dict | None = None, totale: int | None = None) -> dict:
    """
    La config di §6, versione 2 (C2), con tutti i blocchi di BLOCCHI_STANDARD ammessi sul timeframe e le loro griglie. I
    blocchi del catalogo che su quel timeframe non scattano restano fuori (blocchi.py li fermerebbe). `confini` (09/11):
    quelli calcolati da confini_standard sui dati; senza, la prima finestra (CONFINI_STANDARD). `totale`: il tetto del
    budget calcolato dalla cella 1 sui blocchi tenuti (D6); senza, il tetto del massimo con tutti i blocchi.
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
    config = {
        "versione": VERSIONE, "symbol": symbol, "timeframe": timeframe,
        "confini": dict(CONFINI_STANDARD if confini is None else confini),
        "lati": ["long"] if solo_long(symbol) else ["long", "short"],
        "blocchi": blocchi,
        "modelli": [{"trigger": 1, "filtri": [0, 2], "uscite": 1}],
        "qualita_1": {"trade_min": 100, "ev_min_bp": 0, "peso_max": 0.10, "totale_su_dd_min": 1.0},
        "qualita_2": {"trade_min": 50, "p_ev_neg_max": 5.0, "peso_max": 0.15, "totale_su_dd_min": 0.5},
        "altopiano": {"variazione_ore": 0.15, "spostamento_min_barre": 1, "mediana_min": 0.7, "peggiore_min": 0.4,
                      "candidati_max": 3, "prove_max": 60},
        "test_individuale": {"alfa": 0.05},
        "budget": {"totale": 0, "per_teoria_passo_1": 40, "teorie_turno_2": 150, "teorie_passo_2": 150,
                   "giri_zoom": 3, "prove_per_giro": 90},
        "seme": seme, "processi": processi,
    }
    config["budget"]["totale"] = int(totale) if totale is not None else tetto_budget(massimo_senza_dati(config))
    return config


def blocchi_esclusi(timeframe: str) -> list[dict]:
    """
    I blocchi standard che config_standard lascia fuori su `timeframe`, con il motivo (L5a, 08/11): blocco, tipo del
    motivo (limite logico, approssimazione esclusa per scelta, escluso solo dall'elenco) e spiegazione. Si ferma se un
    blocco tolto non ha il suo motivo in blocchi.MOTIVI_ESCLUSIONE: nessun blocco esce in silenzio.
    """
    if timeframe not in MINUTI_TIMEFRAME:
        raise ValueError(f"timeframe {timeframe!r} non previsto: {sorted(MINUTI_TIMEFRAME)}")
    dentro = config_standard("BINANCE_PERP_BTCUSDT", timeframe)["blocchi"]
    out = []
    for nome in BLOCCHI_STANDARD:
        if nome in dentro:
            continue
        if (nome, timeframe) not in MOTIVI_ESCLUSIONE:
            raise ValueError(f"{nome} esce dalla config su {timeframe} senza un motivo in MOTIVI_ESCLUSIONE.")
        tipo, motivo = MOTIVI_ESCLUSIONE[(nome, timeframe)]
        out.append({"blocco": nome, "tipo": tipo, "motivo": motivo})
    return out


def controlla_tipi_rimasti(config: dict) -> None:
    """Si ferma se nella config non resta almeno un trigger e almeno un'uscita (L5a, cella 1 del notebook)."""
    tipi = {b.tipo for b in blocchi_da_config(config)}
    for tipo, nome in (("trigger", "un trigger"), ("uscita", "un'uscita")):
        if tipo not in tipi:
            raise ValueError(f"su {config['timeframe']} non resta {nome} dopo le esclusioni: la ricerca non può partire.")
