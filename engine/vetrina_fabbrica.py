"""
Le funzioni chiamate dalle celle del notebook della fabbrica (docs/82 §7). Nasce in L4b con la sola
sessione_da_strategia (docs/82 §2 e P9); le altre in L5a (08/11), una per cella:

    avvio(cartella_dati, macchina="pc")                     # Avvio: dati trovati, ricerche, ultima cassaforte usata
    conf = configura(cartella_dati, "BINANCE", "PERP", "BTC", "M15")              # 1 · Configura (aggiorna i dati)
    r = ricerca(conf)                                        # 2 · La ricerca (riprende se interrotta)
    imbuto(r)                                                # 3 · L'imbuto
    strategie_rimaste(r)                                     # 4 · Le strategie rimaste (numerate)
    cassaforte(r, strategie="1, 3")                          # 5 · La cassaforte
    mm_e_stress(r, numero=1, capitale=10_000, ...)           # 6 · MM, stress test e verifica dei trade
    schede(r)                                                # 7 · Le schede

- Come il Lab, le celle non hanno codice: chiamano queste funzioni. Nessuna ricalcola niente che la fabbrica non abbia
  già fatto: le regole sono quelle di engine/fabbrica/ (ricerca, selezione, cassaforte, sessione, schede).
- Cella 1 (09/11): a ogni avvio aggiorna i CSV dall'exchange (senza rete: avviso e i CSV che ci sono); confini dal
  02/01/2020 (14/11: o dalla prima mezzanotte UTC con i dati, se il symbol parte dopo) all'ultima mezzanotte UTC chiusa,
  nelle proporzioni della config standard. Timeframe da M1 a D1. I blocchi tolti
  su quel timeframe si elencano con il motivo (limite logico, approssimazione esclusa per scelta, escluso solo
  dall'elenco) e la cella prosegue; si ferma solo se mancano i dati o se non resta un trigger o un'uscita (Mattia,
  08/11). Lo stesso elenco va nel riepilogo della 2 (riepilogo.json) e nelle schede.
- C2 (docs/82 §11.8): la cella 1 mostra i blocchi tenuti e tolti (un blocco per famiglia), le teorie dei due turni,
  le prove massime e la stima del tempo dalla velocità vera delle ricerche del 9 e del 10/11; la 2 dice il turno; la 3
  ha i due turni nell'imbuto. Le celle 4–7 su una ricerca della versione 1 si fermano con «ricerca non trovata» (D5).
- Cella 5 (10/11): i numeri scritti entrano in cassaforte, ogni volta che la cella si lancia, anche se sono già
  entrati; nessuna frase di conferma. Vuoto = nessun ingresso: la cella mostra l'esito di quelle già entrate, se ce
  ne sono.
- Cella 6: money management e stress test, e sempre la verifica dei trade (docs/81 §3 passo 9); la lente su un trade è
  facoltativa. Il riassunto va in <ricerca>/mm/<id_strategia>.json, e da lì nella scheda.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
from dataclasses import dataclass, field

import pandas as pd

from engine.fabbrica import cassaforte as cas_mod
from engine.fabbrica import registro
from engine.fabbrica.sessione import apri_sessione

ORDINE_ESITI = {"scelta": 0, "stessa famiglia": 1, "scartata": 2}
FILE_RIEPILOGO = "riepilogo.json"
# La velocità vera di due ricerche C2 del 14/11, config standard, 3 processi, cella 2 intera (preparazione e selezione
# comprese): (prove, secondi, barre del pezzo di ricerca). BINANCE_PERP_BTCUSDT M15, ricerca 20261114_dbb3724dbe5b: 405
# prove al secondo; BINANCE_PERP_ETHUSDT H1, ricerca 20261114_2bd65fa4db60: 1.339 prove al secondo (Mattia, 14/11; prima
# erano le ricerche del 9 e del 10/11). Serve solo per la stima della cella 1: il tempo vero si vede alla 2.
RICERCHE_VERE = ((288_920, 713.819, 123_752), (245_970, 183.719, 30_938))
PROCESSI_VERI = 3
FATTORE_PROCESSI = {1: 0.7, 2: 0.85}         # docs/82 §5: 380 / 543 valutazioni al secondo con 1 e 3 processi
VERSIONE_1 = "ricerca non trovata: è una ricerca della versione 1, rilancia la cella 2 per una ricerca nuova"

_ESITI_CASSAFORTE: dict = {}                 # id_ricerca -> l'ultimo esito della cassaforte letto in questa sessione


def sessione_da_strategia(cartella_dati, id_ricerca: str, id_strategia: str, esito=None):
    """
    La Sessione del Lab (vetrina.Sessione) per una strategia entrata in cassaforte, per le schermate 7, 9 e 8:
    in-sample = ricerca + selezione, out-of-sample = la cassaforte (engine/fabbrica/sessione.py). `esito` = quello di
    cassaforte.entra, se c'è già; altrimenti si rifà con cassaforte.esito_cassaforte (nessun ingresso nuovo).
    Le condizioni temporanee nel catalogo si tolgono con engine.fabbrica.sessione.chiudi(s).
    """
    if esito is None:
        esito = cas_mod.esito_cassaforte(cartella_dati, id_ricerca)
    return apri_sessione(esito, id_strategia)


# ------------------------------------------------------------------ la presentazione (quella del Lab)
def _v():
    from engine import vetrina
    return vetrina


def _titolo(t):
    _v()._titolo(t)


def _nota(t):
    _v()._nota(t)


def _avviso(t):
    _v()._avviso(t)


def _mostra(*tabelle, decimali=None):
    _v()._mostra(*tabelle, decimali=decimali)


def _dettaglio(titolo, *tabelle):
    _v()._dettaglio(titolo, *tabelle)


def _f(x, d=2):
    return _v()._fmt(x, d)


def _data(t) -> str:
    return pd.Timestamp(t).tz_convert("UTC").strftime("%d/%m/%Y %H:%M") if pd.Timestamp(t).tzinfo else \
        pd.Timestamp(t).strftime("%d/%m/%Y %H:%M")


# ------------------------------------------------------------------ Avvio
def _prima_data_csv(percorso: str) -> pd.Timestamp | None:
    """(14/11) La data della prima barra di un CSV di scarica_dati_crypto.py, leggendo solo l'inizio del file."""
    with open(percorso, encoding="utf-8", errors="replace") as f:
        f.readline()                                    # l'intestazione
        riga = f.readline()
    try:
        return pd.Timestamp(riga.split(",")[0], tz="UTC") if riga.strip() else None
    except ValueError:
        return None


def _ultima_data_csv(percorso: str) -> pd.Timestamp | None:
    """La data dell'ultima riga di un CSV di scarica_dati_crypto.py, leggendo solo la coda del file."""
    with open(percorso, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - 4096))
        righe = [r for r in f.read().decode("utf-8", "replace").splitlines() if r.strip()]
    if not righe:
        return None
    try:
        return pd.Timestamp(righe[-1].split(",")[0], tz="UTC")
    except ValueError:
        return None


def avvio(cartella_dati, macchina: str = "pc") -> dict:
    """
    Avvio: il nome della macchina nei file della fabbrica, i dati trovati (symbol, timeframe, ultima barra) e, per
    ogni symbol e timeframe con ricerche, le ricerche fatte e la fine dell'ultima cassaforte usata. Non scarica niente:
    i dati si aggiornano alla cella 1 (09/11). Ritorna {"macchina", "dati", "ricerche"}.
    """
    from engine.exchange import simboli_exchange
    from engine.fabbrica.blocchi import MINUTI_TIMEFRAME
    nome = registro.imposta_macchina(macchina)
    cartella = str(cartella_dati)
    righe = []
    for sym in simboli_exchange():
        for tf in MINUTI_TIMEFRAME:
            p = os.path.join(cartella, f"{sym}_{tf}.csv")
            if os.path.exists(p):
                righe.append({"symbol": sym, "timeframe": tf, "ultima barra (UTC)": _ultima_data_csv(p)})
    dati = pd.DataFrame(righe, columns=["symbol", "timeframe", "ultima barra (UTC)"])
    ricerche = []
    base = os.path.join(cartella, "fabbrica")
    for asset in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        ca = os.path.join(base, asset)
        ids = sorted(d for d in os.listdir(ca) if os.path.isfile(os.path.join(ca, d, "config.json")))
        if not ids:
            continue
        eventi = registro.leggi_registro(ca)
        tratti = cas_mod.tratti_usati(ca)
        for id_r in ids:
            with open(os.path.join(ca, id_r, "config.json"), encoding="utf-8") as f:
                config = json.load(f)
            stato = {}
            ps = os.path.join(ca, id_r, "stato.json")
            if os.path.exists(ps):
                with open(ps, encoding="utf-8") as f:
                    stato = json.load(f)
            entrate = {s["id_strategia"] for e in eventi if e.get("tipo") == cas_mod.INGRESSO
                       and e.get("id_ricerca") == id_r for s in e["strategie"]}
            ricerche.append({"symbol": config["symbol"], "timeframe": config["timeframe"], "ricerca": id_r,
                             "a che punto": {"finita": "finita"}.get(stato.get("fase"), stato.get("fase", "—")),
                             "entrate in cassaforte": len(entrate),
                             "ultima cassaforte usata fino al": _data(tratti[-1][1]) if tratti else "nessuna"})
    ric = pd.DataFrame(ricerche)
    _titolo(f"Fabbrica pronta · macchina «{nome}» · dati da {cartella}")
    if len(dati):
        vista = dati.copy()
        vista["ultima barra (UTC)"] = [_data(t) if t is not None else "—" for t in vista["ultima barra (UTC)"]]
        _mostra((f"Dati trovati: {len(dati)} file", vista))
    else:
        _avviso(f"Nella cartella {cartella} non ci sono ancora CSV dei symbol da exchange: la cella 1 scarica quello "
                "del symbol e del timeframe scelti.")
    if len(ric):
        _mostra(("Ricerche già fatte dalla fabbrica", ric))
    else:
        _nota("Nessuna ricerca della fabbrica in questa cartella.")
    return {"macchina": nome, "dati": dati, "ricerche": ric}


# ------------------------------------------------------------------ 1 · Configura
@dataclass
class Configurazione:
    cartella_dati: str
    config: dict
    id_ricerca: str
    nuova: bool
    limiti: dict
    teorie: int
    budget_massimo: int
    stima_minuti: tuple
    esclusi: list
    barre_ricerca: int
    resoconto: dict = field(default_factory=dict)
    tenuti_tolti: list = field(default_factory=list)
    turno_2_massimo: int = 0


def stima_minuti(budget: int, barre_ricerca: int, processi: int) -> tuple[float, float]:
    """
    (da, a) minuti per `budget` prove, dalla velocità vera delle due ricerche di RICERCHE_VERE (3 processi), in
    proporzione alle barre del pezzo di ricerca; con 1 o 2 processi più lenta (FATTORE_PROCESSI).
    """
    fattore = FATTORE_PROCESSI.get(int(processi), 1.0)
    minuti = [budget / (prove / secondi * barre / max(int(barre_ricerca), 1) * fattore) / 60.0
              for prove, secondi, barre in RICERCHE_VERE]
    return min(minuti), max(minuti)


def _gia_salvata(config: dict, cartella_dati) -> bool:
    from engine.fabbrica.config import cartella_asset, impronta_config
    base = cartella_asset(cartella_dati, config["symbol"], config["timeframe"])
    fine = "_" + impronta_config(config)[:12]
    return os.path.isdir(base) and any(n.endswith(fine) for n in os.listdir(base))


ATTESA_TENTATIVI = 1.0      # secondi fra i tentativi del download (1, 2, 4, 8, 16): senza rete la cella aspetta poco


def _scarica(symbol: str, timeframe: str, cartella: str) -> dict:
    """
    Il download della cella 1: engine/aggiorna_dati.aggiorna_per_lab (candele e, sui perpetual, funding), lo stesso
    codice del Lab e di scarica_dati_crypto.py. I collaudi lo sostituiscono con un exchange finto: la suite non va in rete.
    """
    from engine.aggiorna_dati import aggiorna_per_lab
    return aggiorna_per_lab(symbol, timeframe, cartella, verbose=False, attesa=ATTESA_TENTATIVI)


def aggiorna_dati(cartella_dati, symbol: str, timeframe: str) -> dict:
    """
    (09/11) Cella 1, prima della config: aggiorna i CSV dall'exchange e dice fin dove arrivano i dati. Nessun
    interruttore. Se l'exchange non risponde o ccxt manca: un avviso e si usano i CSV fino all'ultimo salvataggio. Si
    ferma (ValueError «La cella si ferma») solo se il CSV non c'è e il download non riesce. Crea la cartella se manca.
    Ritorna {"aggiornati": bool, "ultima_barra": inizio dell'ultima barra chiusa, "fine": la sua chiusura, "esito",
    "prima_barra": inizio della prima barra del CSV (14/11)}.
    """
    from engine.fabbrica.blocchi import MINUTI_TIMEFRAME
    cartella = str(cartella_dati)
    os.makedirs(cartella, exist_ok=True)
    percorso = os.path.join(cartella, f"{symbol}_{timeframe}.csv")
    print(f"Aggiorno {symbol} {timeframe} dall'exchange"
          + ("" if os.path.exists(percorso) else " (il file non c'è: lo scarico tutto dal 02/01/2020, ci vuole un po')")
          + "…", flush=True)
    try:
        esito = _scarica(symbol, timeframe, cartella)
    except FileNotFoundError as e:
        raise ValueError(f"La cella si ferma: {e}") from e
    ultima = _ultima_data_csv(percorso) if os.path.exists(percorso) else None
    if ultima is None:
        raise ValueError(f"La cella si ferma: non riesco a leggere l'ultima barra di {percorso}.")
    fine = ultima + pd.Timedelta(minutes=MINUTI_TIMEFRAME[timeframe])
    candele, funding = esito["candele"], esito.get("funding")
    aggiornati = candele["esito"] == "aggiornato"
    if aggiornati:
        _nota(f"Dati aggiornati fino a {_data(fine)} UTC ({_f(candele.get('nuove', 0))} barre nuove).")
        if funding is not None and funding["esito"] != "aggiornato":
            fino = f" fino al {_data(funding['al'])} UTC" if funding.get("al") is not None else ""
            _avviso(f"Il funding non si è aggiornato: uso quello che c'è{fino}. Motivo: {funding.get('errore')}")
    else:
        _avviso(f"Exchange non raggiungibile: uso i dati fino a {_data(fine)} UTC.")
        _nota(f"Motivo: {candele.get('errore')}")
    return {"aggiornati": aggiornati, "ultima_barra": ultima, "fine": fine, "esito": esito,
            "prima_barra": _prima_data_csv(percorso)}


def configura(cartella_dati, exchange: str, mercato: str, moneta: str, timeframe: str, processi: int = 3,
              config: dict | None = None, data: str | None = None) -> Configurazione:
    """
    Cella 1. Aggiorna i dati (aggiorna_dati), poi la config standard sul symbol e sul timeframe scelti (da M1 a D1), con
    i confini fino all'ultima mezzanotte UTC chiusa (config.confini_standard, 09/11: nello stesso giorno UTC, stessa
    ricerca), controllata e bloccata con l'impronta.
    Si ferma solo se mancano i dati (o non coprono i tre pezzi) o se non resta un trigger o un'uscita; i blocchi tolti
    sul timeframe si elencano con il motivo. `config` (scritta a mano, per i collaudi) prende il posto di quella
    standard e resta com'è, confini compresi.
    """
    from engine.exchange import simboli_exchange
    from engine.fabbrica.blocchi import MINUTI_TIMEFRAME
    from engine.fabbrica.config import (config_standard, confini_standard, controlla_config, controlla_tipi_rimasti,
                                        impronta_config, salva_config, tetto_budget)
    from engine.fabbrica.dati import Confini, carica_pezzi
    from engine.fabbrica.ricerca import prepara
    from engine.fabbrica.schede import esclusi_dalla_config
    symbol = f"{str(exchange).upper()}_{str(mercato).upper()}_{str(moneta).upper()}USDT"
    if symbol not in simboli_exchange():
        raise ValueError(f"{symbol}: non è un symbol da exchange della tabella (engine/simboli.py).")
    if timeframe not in MINUTI_TIMEFRAME:
        raise ValueError(f"timeframe {timeframe!r}: usa uno di {list(MINUTI_TIMEFRAME)}.")
    dati = aggiorna_dati(cartella_dati, symbol, timeframe)
    standard = config is None
    if standard:
        confini_std = confini_standard(timeframe, dati["ultima_barra"], dati["prima_barra"])
        config = config_standard(symbol, timeframe, processi=int(processi), confini=confini_std)
    config = controlla_config(config)
    if (config["symbol"], config["timeframe"]) != (symbol, timeframe):
        raise ValueError(f"la config è di {config['symbol']} {config['timeframe']}, i campi dicono {symbol} {timeframe}.")
    controlla_tipi_rimasti(config)
    esclusi = esclusi_dalla_config(config)
    confini = Confini.da_config(config["confini"])
    try:
        pezzi = carica_pezzi(config["symbol"], config["timeframe"], confini, cartella_dati)
    except (FileNotFoundError, ValueError) as e:
        raise ValueError(f"La cella si ferma: {e}") from e
    prep = prepara(config, pezzi, controlla=not standard)
    if standard:          # D6: il tetto del budget è il massimo sui blocchi tenuti, arrotondato in su ai 10.000
        config = controlla_config(config_standard(symbol, timeframe, processi=int(processi), confini=confini_std,
                                                  totale=tetto_budget(prep.budget_massimo)))
    nuova = not _gia_salvata(config, cartella_dati)
    id_ricerca = salva_config(config, cartella_dati, data)
    conf = Configurazione(str(cartella_dati), config, id_ricerca, nuova, confini.limiti(), len(prep.teorie),
                          prep.budget_massimo, stima_minuti(prep.budget_massimo, len(pezzi.ricerca),
                                                            config["processi"]),
                          esclusi, len(pezzi.ricerca), prep.resoconto, list(prep.tenuti_tolti), prep.turno_2_massimo)
    lim = conf.limiti
    _titolo(f"{config['symbol']} {config['timeframe']} · ricerca {id_ricerca} "
            f"({'nuova' if nuova else 'già esiste: riprende'})")
    _nota(_riga_inizio(config, dati.get("prima_barra")))
    _mostra(("I tre pezzi (UTC)", pd.DataFrame([
        {"pezzo": "ricerca", "da": _data(lim["ricerca"][0]), "a": _data(lim["ricerca"][1]), "stato": "aperto"},
        {"pezzo": "selezione", "da": _data(lim["selezione"][0]), "a": _data(lim["selezione"][1]), "stato": "aperto"},
        {"pezzo": "cassaforte", "da": _data(lim["cassaforte"][0]), "a": _data(lim["cassaforte"][1]),
         "stato": "chiusa"}])))
    _tenuti_tolti(conf.resoconto, conf.tenuti_tolti)
    da, a = conf.stima_minuti
    _nota(f"Turno 1: {_f(conf.teorie)} teorie; turno 2: al massimo {_f(conf.turno_2_massimo)}; al massimo "
          f"{_f(conf.budget_massimo)} prove (tetto {_f(config['budget']['totale'])}), {_minuti_da_a(da, a)} con "
          f"{config['processi']} {'processo' if config['processi'] == 1 else 'processi'} se servono tutte (stima dalla "
          f"velocità delle ricerche vere del 14/11: il tempo vero si vede alla 2). Impronta "
          f"{impronta_config(config)[:12]}.")
    _blocchi_esclusi(esclusi, config["timeframe"])
    _nota("Cambiare le regole dopo vuol dire una ricerca nuova, e le prove si sommano.")
    return conf


def _riga_inizio(config: dict, prima_barra) -> str:
    """(14/11) L'inizio usato; se non è il 02/01/2020, il perché in una riga (i dati del symbol partono dopo)."""
    from engine.fabbrica.config import CONFINI_STANDARD
    inizio = pd.Timestamp(config["confini"]["inizio"], tz="UTC")
    testo = f"Inizio della ricerca: {inizio:%d/%m/%Y %H:%M} UTC."
    if config["confini"]["inizio"] != CONFINI_STANDARD["inizio"] and prima_barra is not None:
        testo += (f" {config['symbol']}: dati dal {_data(prima_barra)} UTC, la ricerca parte dal {inizio:%d/%m/%Y}, la "
                  "prima mezzanotte UTC con i dati.")
    return testo


def _minuti_da_a(da: float, a: float) -> str:
    """«circa 15–18 minuti»; se arrotondati sono uguali, come _minuti."""
    if round(da) == round(a) or a < 1.5:
        return _minuti(a)
    return f"circa {_f(da, 0)}–{_f(a, 0)} minuti"


def _tenuti_tolti(resoconto: dict, tabella: list) -> None:
    """Cella 1 (docs/82 §11.8): una riga per lato, poi la tabella dei tolti; quella completa in una sezione chiusa."""
    for lato, b in resoconto.get("blocchi", {}).items():
        t, f = b["trigger"], b["filtro"]
        _nota(f"{lato}: {t['blocchi']} trigger → {t['tenuti']} tenuti, {f['blocchi']} filtri → {f['tenuti']} tenuti "
              "(un blocco per famiglia).")
    if not tabella:
        return
    tab = pd.DataFrame(tabella)
    tab["scatta"] = [f"{_f(int(n))} {'segnali' if tipo == 'trigger' else 'barre vere'}"
                     for n, tipo in zip(tab["scatta"], tab["tipo"])]
    tolti = tab[tab["esito"] == "tolto"][["lato", "tipo", "blocco", "motivo", "scatta"]]
    if len(tolti):
        _mostra((f"Blocchi tolti ({len(tolti)}): un blocco per famiglia, e i blocchi che sul pezzo di ricerca non "
                 "scattano come serve", tolti.reset_index(drop=True)))
    _dettaglio(f"Tutti i blocchi, tenuti e tolti ({len(tab)} righe)",
               ("", tab[["lato", "tipo", "famiglia", "blocco", "esito", "motivo", "scatta", "piu_simile",
                         "somiglianza"]].astype(str)))


def _minuti(m: float) -> str:
    """«circa 8 minuti», «circa un minuto», «meno di un minuto»."""
    if m < 0.75:
        return "meno di un minuto"
    if m < 1.5:
        return "circa un minuto"
    return f"circa {_f(m, 0)} minuti"


def _blocchi_esclusi(esclusi: list, timeframe: str) -> None:
    if esclusi:
        _mostra((f"Blocchi tolti su {timeframe} ({len(esclusi)})", pd.DataFrame(esclusi)))
    else:
        _nota(f"Su {timeframe} ci sono tutti i blocchi della lista.")


# ------------------------------------------------------------------ 2 · La ricerca
def _stampa_avanzamento():
    """La riga che si aggiorna: fase, teoria n di N, prove, minuti che mancano al massimo (dal ritmo di adesso)."""
    v = _v()
    maniglia = [None]

    def avanza(a: dict):
        ritmo = a["prove_ora"] / a["secondi"] if a["secondi"] > 0 and a["prove_ora"] > 0 else None
        manca = (f"mancano al massimo {_minuti(max(a['budget_massimo'] - a['prove'], 0) / ritmo / 60)}"
                 if ritmo else "")
        testo = (f"{a['fase']}: teoria {_f(a['numero'])} di {_f(a['totale'])} · {_f(a['prove'])} prove"
                 + (f" · {manca}" if manca else ""))
        if v._in_notebook():
            from IPython.display import display
            if maniglia[0] is None:
                maniglia[0] = display(testo, display_id=True)
            else:
                maniglia[0].update(testo)
        elif a["numero"] % 50 == 0 or a["numero"] == a["totale"]:
            print("  " + testo, flush=True)

    return avanza


def ricerca(conf: Configurazione, data: str | None = None):
    """
    Cella 2. Lancia la ricerca (turno 1, turno 2, zoom, altopiano, selezione) o la riprende da dove era. Alla fine il
    riepilogo, che si scrive anche in <ricerca>/riepilogo.json con i blocchi tolti sul timeframe. Interrotta (■),
    dice di rilanciare la cella e ritorna None.
    """
    from engine.fabbrica.ricerca import lancia
    try:
        r = lancia(conf.config, conf.cartella_dati, verbose=False, data=data, avanzamento=_stampa_avanzamento())
    except KeyboardInterrupt:
        _avviso("Ricerca interrotta. Rilancia questa cella: riparte da dove era, senza rifare le teorie già finite.")
        return None
    riepilogo = {"id_ricerca": r.id_ricerca, "symbol": conf.config["symbol"], "timeframe": conf.config["timeframe"],
                 "finita": r.finita, "durata_s": r.durata_s, "prove": r.prove, "budget_massimo": r.budget_massimo,
                 "imbuto": r.imbuto, "conto": r.conto, "blocchi_esclusi": conf.esclusi,
                 "tenuti_tolti": r.tenuti_tolti,
                 "valori_degeneri_avvio": len(r.degeneri_avvio), "valori_degeneri_zoom": len(r.degeneri_zoom)}
    with open(os.path.join(r.cartella, FILE_RIEPILOGO + ".tmp"), "w", encoding="utf-8") as f:
        f.write(registro.json_riga(riepilogo) + "\n")
    os.replace(os.path.join(r.cartella, FILE_RIEPILOGO + ".tmp"), os.path.join(r.cartella, FILE_RIEPILOGO))
    _titolo(f"Ricerca {r.id_ricerca}: {'finita' if r.finita else 'non finita'}")
    _nota(f"{_f(r.prove)} prove in questa ricerca (massimo {_f(r.budget_massimo)}), {_f(r.durata_s / 60, 1)} minuti "
          f"in questa chiamata. Valori degeneri tolti all'avvio: {_f(len(r.degeneri_avvio))}; combinazioni degeneri "
          f"scartate da zoom e altopiano: {_f(len(r.degeneri_zoom))}.")
    if r.degeneri_avvio:
        _dettaglio("Valori degeneri tolti all'avvio", ("", pd.DataFrame(r.degeneri_avvio).astype(str)))
    _blocchi_esclusi(conf.esclusi, conf.config["timeframe"])
    r.esclusi = conf.esclusi
    return r


# ------------------------------------------------------------------ 3 · L'imbuto
def _cassaforte_dal_registro(r) -> dict:
    """Entrate e passate in cassaforte di questa ricerca, dal registro (la cassaforte non si riapre)."""
    base = os.path.dirname(r.cartella)
    eventi = registro.leggi_registro(base)
    entrate = list(dict.fromkeys(s["id_strategia"] for e in eventi if e.get("tipo") == cas_mod.INGRESSO
                                 and e.get("id_ricerca") == r.id_ricerca for s in e["strategie"]))
    esiti = {x["id_strategia"]: x["esito"] for e in eventi if e.get("tipo") == cas_mod.ESITO
             and e.get("id_ricerca") == r.id_ricerca for x in e["risultati"]}
    return {"entrate": entrate, "passano": [i for i in entrate if esiti.get(i) == "passa"],
            "date": {s["id_strategia"]: e.get("quando") for e in eventi if e.get("tipo") == cas_mod.INGRESSO
                     and e.get("id_ricerca") == r.id_ricerca for s in e["strategie"]}}


def imbuto(r) -> pd.DataFrame:
    """Cella 3. Quante strategie restano a ogni passo, con la figura; i motivi di scarto in una sezione chiusa."""
    import matplotlib.pyplot as plt
    i = r.imbuto
    c = _cassaforte_dal_registro(r)
    passi = [("turno 1: teorie", i["turno_1"]), ("turno 1: tenute", i["turno_1_tenute"]),
             ("turno 2: teorie", i["turno_2"]), ("turno 2: tenute", i["turno_2_tenute"]),
             ("zoom: teorie", i["passo_2"]), ("altopiano: reggono", i["altopiano"]),
             ("selezione: passano", i.get("selezione", 0)), ("scelte (una per famiglia)", i.get("scelte", 0)),
             ("cassaforte: entrate", len(c["entrate"])), ("cassaforte: passano", len(c["passano"]))]
    tab = pd.DataFrame(passi, columns=["passo", "quante"])
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.barh(tab["passo"][::-1], tab["quante"][::-1], color="#2b7bba")
    for y, q in enumerate(tab["quante"][::-1]):
        ax.text(q, y, f" {_f(int(q))}", va="center", fontsize=9)
    ax.set_xscale("symlog")
    ax.set_title(f"L'imbuto · ricerca {r.id_ricerca}")
    ax.set_xlabel("quante (scala logaritmica)")
    plt.tight_layout()
    plt.show()
    _mostra(("", tab))
    _nota("Un imbuto che resta vuoto non è un errore: è una risposta.")
    scarti = []
    for turno in (1, 2):
        p1 = r.passo_1[r.passo_1["turno"] == turno] if len(r.passo_1) else r.passo_1
        if len(p1):
            scarti.append({"passo": f"turno {turno}", "motivo": "nessuna strategia passa la condizione 1",
                           "quante": int((~p1["tenuta"].astype(bool)).sum())})
    if len(r.passo_2):
        for m, n in r.passo_2[r.passo_2["esito"] != "regge"]["motivo"].value_counts().items():
            scarti.append({"passo": "altopiano", "motivo": m, "quante": int(n)})
    if r.selezione is not None:
        t = r.selezione.tabella
        for m, n in t[t["esito"] == "scartata"]["motivo"].value_counts().items():
            scarti.append({"passo": "selezione", "motivo": m, "quante": int(n)})
    _dettaglio("I motivi di scarto", ("", pd.DataFrame(scarti, columns=["passo", "motivo", "quante"])))
    return tab


# ------------------------------------------------------------------ 4 · Le strategie rimaste
def _controlla_versione(r) -> None:
    """Celle 4–7 (D5 = B): una ricerca della versione 1 si ferma con «ricerca non trovata» e dice di rilanciare la 2."""
    from engine.fabbrica.config import VERSIONE
    if _config_ricerca(r).get("versione") != VERSIONE:
        raise ValueError(VERSIONE_1)


def numerate(r) -> pd.DataFrame:
    """La tabella della selezione numerata: prima le scelte, poi «stessa famiglia», poi le scartate; t più alto prima."""
    _controlla_versione(r)
    if r.selezione is None:
        raise ValueError("la ricerca non è finita: rilancia la 2 fino in fondo.")
    t = r.selezione.tabella.copy()
    t["_o"] = t["esito"].map(ORDINE_ESITI)
    t = t.sort_values(["_o", "t", "id_strategia"], ascending=[True, False, True]).drop(columns="_o")
    t.insert(0, "numero", range(1, len(t) + 1))
    return t.reset_index(drop=True)


def _regola_breve(riga, config) -> str:
    from engine.fabbrica.schede import regole_in_parole
    from engine.fabbrica.selezione import strategia_da_riga
    st = strategia_da_riga(riga, config["symbol"], config["timeframe"])
    return " ".join(regole_in_parole(st, config["timeframe"])["righe"])


def _config_ricerca(r) -> dict:
    with open(os.path.join(r.cartella, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def strategie_rimaste(r) -> pd.DataFrame:
    """
    Cella 4. Una riga per strategia, numerata (il numero serve alla 5 e alla 6), con la regola in parole e i numeri
    di ricerca e selezione. Le scartate stanno in una sezione chiusa. Accanto, da leggere, il conto delle prove.
    """
    _controlla_versione(r)
    config = _config_ricerca(r)
    t = numerate(r)
    p2 = r.passo_2.set_index("teoria")
    righe = []
    for x in t.to_dict("records"):
        ric = p2.loc[x["teoria"]] if x["teoria"] in p2.index else {}
        righe.append({"numero": x["numero"], "lato": x["lato"], "regola": _regola_breve(x, config),
                      "trade ricerca": ric.get("trade"), "EV ricerca (bp)": ric.get("ev_bp"),
                      "t ricerca": ric.get("t"), "trade selezione": x["trade"], "EV selezione (bp)": x["ev_bp"],
                      "t selezione": x["t"], "esito": x["esito"], "motivo": x["motivo"],
                      "id_strategia": x["id_strategia"]})
    tab = pd.DataFrame(righe)
    vive = tab[tab["esito"] != "scartata"].drop(columns=["motivo", "id_strategia"])
    _titolo(f"Le strategie rimaste · ricerca {r.id_ricerca}")
    if len(vive):
        _mostra(("", vive))
    else:
        _nota("Nessuna strategia è arrivata viva alla fine della selezione.")
    soglia = float(t["soglia_test"].iloc[0]) if len(t) else None
    _nota(f"Decide il t di selezione contro {_f(soglia)}. Da leggere: {_f(r.conto.get('asset'))} prove su questo "
          f"asset, soglia corrispondente {_f(r.conto.get('soglia_da_leggere'))}. «Stessa famiglia»: entrano quasi "
          "negli stessi momenti di una scelta, che le rappresenta.")
    scartate = tab[tab["esito"] == "scartata"].drop(columns=["id_strategia"])
    if len(scartate):
        _dettaglio(f"Le scartate ({len(scartate)})", ("", scartate))
    return tab


# ------------------------------------------------------------------ 5 · La cassaforte
def numeri_strategie(r, testo: str) -> list[str]:
    """Dal campo della 5 agli id: «» = nessuna; «tutte le scelte»; oppure numeri della 4 separati da virgole."""
    t = numerate(r)
    testo = (testo or "").strip().lower()
    if not testo:
        return []
    if testo in ("tutte", "tutte le scelte"):
        return list(t[t["esito"] == "scelta"]["id_strategia"])
    pezzi = [p for p in re.split(r"[,\s;]+", testo) if p]
    if not all(p.isdigit() for p in pezzi):
        raise ValueError(f"strategie {testo!r}: scrivi i numeri della 4 separati da virgole (es. «1, 3»), oppure "
                         "«tutte le scelte».")
    numeri = [int(p) for p in pezzi]
    fuori = [n for n in numeri if not 1 <= n <= len(t)]
    if fuori:
        raise ValueError(f"numeri {fuori}: la tabella della 4 va da 1 a {len(t)}.")
    return list(dict.fromkeys(t.set_index("numero").loc[n, "id_strategia"] for n in numeri))


def esito_cassaforte(r):
    """L'esito della cassaforte di questa ricerca (quello già letto in questa sessione, o rifatto senza ingressi)."""
    c = _ESITI_CASSAFORTE.get(r.id_ricerca)
    if c is None:
        c = cas_mod.esito_cassaforte(_cartella_dati(r), r.id_ricerca)
        _ESITI_CASSAFORTE[r.id_ricerca] = c
    return c


def _cartella_dati(r) -> str:
    """dati/fabbrica/<SYMBOL>_<TF>/<id> -> dati."""
    return os.path.dirname(os.path.dirname(os.path.dirname(r.cartella)))


def cassaforte(r, strategie: str = ""):
    """
    Cella 5. Le strategie scelte (numeri della 4 o «tutte le scelte») entrano in cassaforte e si provano sull'ultimo
    pezzo, anche se erano già entrate (10/11): ogni lancio è un ingresso nel registro, da leggere. Vuoto = nessun
    ingresso: si mostra l'esito di quelle già entrate, se ce ne sono. La tabella ha tutte le strategie entrate in
    questa ricerca, una riga ciascuna.
    """
    _controlla_versione(r)
    cartella = _cartella_dati(r)
    ids = numeri_strategie(r, strategie)
    gia = _cassaforte_dal_registro(r)
    if not ids and not gia["entrate"]:
        _nota("Nessuna strategia scelta: in cassaforte non è entrato niente.")
        return None
    if ids:
        c = cas_mod.entra(cartella, r.id_ricerca, ids)
        if set(gia["entrate"]) - set(ids):
            c = cas_mod.esito_cassaforte(cartella, r.id_ricerca)
    else:
        c = cas_mod.esito_cassaforte(cartella, r.id_ricerca)
    _ESITI_CASSAFORTE[r.id_ricerca] = c
    num = numerate(r).set_index("id_strategia")["numero"]
    tab = c.tabella
    vista = pd.DataFrame({"numero": [num.get(i) for i in tab["id_strategia"]], "lato": tab["lato"],
                          "t selezione": tab["t_selezione"], "EV selezione (bp)": tab["ev_bp_selezione"],
                          "trade cassaforte": tab["trade"], "EV cassaforte (bp)": tab["ev_bp"],
                          "t cassaforte": tab["t"], "esito": tab["esito"]})
    _titolo(f"La cassaforte · tratto {c.tratto['id']}")
    _mostra(("", vista.sort_values("numero")))
    _nota(f"Decide il t in cassaforte contro {_f(float(tab['soglia_test'].iloc[0]))}. Da leggere: strategie entrate "
          f"finora in questo tratto {_f(c.conto.get('entrate_nel_tratto'))}; prove su questo asset "
          f"{_f(c.conto.get('asset'))}, soglia corrispondente {_f(c.conto.get('soglia_da_leggere'))}.")
    return c


# ------------------------------------------------------------------ 6 · MM, stress test e verifica dei trade
# I riquadri del Lab rimandano alle sue schermate; nella fabbrica quelle schermate non ci sono (Mattia, 08/11, nota per
# L5b). Durante la cella 6 i testi passano da qui: rimandi riscritti, nomi temporanei FAB_SES_… al posto del nome breve
# del blocco. Il Lab non cambia: le sue funzioni sono le stesse, si sostituisce solo il testo che mostrano, e solo
# dentro _testi_fabbrica.
RIMANDI = (
    (r"Poi vai alla schermata 8 \(verifica dei trade\) e alla 9 \(stress test\)\.",
     "In questa cella seguono lo stress test e la verifica dei trade."),
    (r"Usa la scheda della 6 di adesso: ([^,]+ trade in-sample e [^,]+ out-of-sample), .*?Se rifai la 6, rifai anche "
     r"questa schermata\.", r"Usa i trade della strategia: \1 (in-sample = ricerca + selezione, out-of-sample = "
                            r"cassaforte)."),
    (r"Drawdown che accetti, dalla schermata 7:", "Drawdown che accetti, dal money management qui sopra:"),
    (r"Apri la lente qui sotto per vedere un trade sul grafico, poi vai alla schermata 9\.",
     "Per vedere un trade sul grafico scrivi il suo numero in «trade da vedere» e rilancia la cella; poi vai alla 7."),
    (r"Cambia numero o data per guardare altri trade, o lascia il numero a 0 per pescarne uno a caso\.",
     "Per guardare un altro trade cambia il numero in «trade da vedere» e rilancia la cella."),
    (r"[Pp]oi vai alla schermata \d+\.", "Poi vai alla 7 · Le schede."),
    (r"[^.;]*\bschermat[ae]\b[^.;]*[.;]", ""),          # ogni altra frase che rimanda a una schermata del Lab
)
_AIUTANTI = ("_riquadro", "_nota", "_avviso", "_spiegazione", "_titolo", "_mostra", "_dettaglio")


def _riscrivi(testo, nomi: dict):
    """Un testo del Lab con i nomi brevi dei blocchi e i rimandi della fabbrica (vedi RIMANDI)."""
    if not isinstance(testo, str):
        return testo
    prima = testo
    for vecchio in sorted(nomi, key=len, reverse=True):
        testo = testo.replace(vecchio, nomi[vecchio])
    for schema, nuovo in RIMANDI:
        testo = re.sub(schema, nuovo, testo)
    return testo if testo == prima else re.sub(r" {2,}", " ", testo).strip()


def _riscrivi_tabella(df, nomi: dict):
    if not isinstance(df, pd.DataFrame):
        return df
    out = df.copy()
    out.columns = [_riscrivi(c, nomi) for c in out.columns]
    for c in out.columns:
        if out[c].dtype == object or pd.api.types.is_string_dtype(out[c]):
            out[c] = [_riscrivi(x, nomi) for x in out[c]]
    return out


@contextlib.contextmanager
def _testi_fabbrica(s):
    """Dentro il blocco, i testi che le funzioni del Lab mostrano sono quelli della fabbrica (vedi RIMANDI)."""
    from engine.fabbrica.schede import nome_breve
    v = _v()
    st = s.fabbrica["strategia"]
    nomi = {temp: nome_breve(blocco, st.valori_di(blocco), s.timeframe) for blocco, temp in
            s.fabbrica.get("nomi", {}).items()}
    nomi[s.filtro] = " + ".join(nome_breve(b, st.valori_di(b), s.timeframe) for b in st.blocchi)
    orig = {n: getattr(v, n) for n in _AIUTANTI}

    def testo(nome):
        return lambda *a, **k: orig[nome](*[_riscrivi(x, nomi) for x in a], **k)

    def tabelle(nome, prime: int):
        def f(*a, **k):
            a = list(a)
            for i in range(prime):
                if i < len(a):
                    a[i] = _riscrivi(a[i], nomi)
            a[prime:] = [(_riscrivi(t, nomi), _riscrivi_tabella(df, nomi)) for t, df in a[prime:]]
            return orig[nome](*a, **k)
        return f

    for n in ("_riquadro", "_nota", "_avviso", "_spiegazione", "_titolo"):
        setattr(v, n, testo(n))
    v._mostra, v._dettaglio = tabelle("_mostra", 0), tabelle("_dettaglio", 1)
    try:
        yield nomi
    finally:
        for n, f in orig.items():
            setattr(v, n, f)

def _riassunto(x):
    from engine.fabbrica.schede import _pulito
    return _pulito(x)


def mm_e_stress(r, numero: int, capitale: float = 10_000.0, drawdown_max_pct: float = 20.0, anni: float = 1.0,
                modello: str = "rischio fisso", leva: float = 0, trade_da_vedere: str = "",
                simulazioni: int | None = None, simulazioni_stress: int | None = None) -> dict:
    """
    Cella 6. Per la strategia `numero` della 4, entrata in cassaforte: money management (schermata 7 del Lab, calibrato
    su ricerca + selezione), stress test (schermata 9) e sempre la verifica dei trade (schermata 8). `trade_da_vedere`
    (facoltativo): «3» = il trade 3 della cassaforte, «in-sample 5» = il trade 5 dell'in-sample, sulla lente.
    Il riassunto va in <ricerca>/mm/<id_strategia>.json per la scheda. simulazioni*: meno solo nei collaudi.
    """
    from engine import vetrina, vetrina_verifica
    from engine.fabbrica import sessione as ses
    _controlla_versione(r)
    t = numerate(r).set_index("numero")
    if int(numero) not in t.index:
        raise ValueError(f"numero {numero}: la tabella della 4 va da 1 a {len(t)}.")
    id_s = t.loc[int(numero), "id_strategia"]
    c = esito_cassaforte(r)
    if id_s not in c.trade:
        raise ValueError(f"la strategia {numero} non è entrata in cassaforte: falla entrare alla 5.")
    vista = None
    testo = (trade_da_vedere or "").strip().lower()
    if testo:
        m = re.fullmatch(r"(in-sample\s+)?(\d+)", testo)
        if not m:
            raise ValueError(f"trade da vedere {trade_da_vedere!r}: scrivi un numero (es. «3»), o «in-sample 5».")
        vista = ("in-sample" if m.group(1) else "out-of-sample", int(m.group(2)))
    with ses.sessione(c, id_s) as s, _testi_fabbrica(s):
        _titolo(f"Strategia {numero} · money management")
        mm = ses.money_management(s, capitale=capitale, drawdown_max_pct=drawdown_max_pct, anni=anni,
                                  modello=modello, leva=leva, simulazioni=simulazioni)
        _titolo(f"Strategia {numero} · stress test")
        st = (vetrina.stress_test(s) if simulazioni_stress is None
              else vetrina.stress_test(s, simulazioni=int(simulazioni_stress)))
        _titolo(f"Strategia {numero} · verifica dei trade")
        ver = ses.verifica_trade(s)
        if vista is not None:
            vetrina_verifica.lente(s, periodo=vista[0], numero=vista[1], mostra_trigger=False)
    riassunto = {
        "quando": registro.adesso(), "id_strategia": id_s,
        "parametri": {"capitale": float(capitale), "drawdown_max_pct": float(drawdown_max_pct), "anni": float(anni),
                      "modello": modello, "leva": float(leva)},
        "mm": {"modello": mm["modello"], "percentuale": mm["f"], "deciso": mm.get("riga_deciso"),
               "sintesi": _sintesi(mm.get("sintesi"))},
        "stress": {"drawdown_max_usd": st.get("drawdown_max_usd"), "unita": st.get("unita"),
                   "sizing": st.get("sizing"), "controllo": st.get("controllo")},
        "verifica": {"regole": ver["regole"], "uscite": ver["uscite"]},
    }
    riassunto = _riassunto(riassunto)
    cartella = os.path.join(r.cartella, "mm")
    os.makedirs(cartella, exist_ok=True)
    percorso = os.path.join(cartella, f"{id_s}.json")
    with open(percorso + ".tmp", "w", encoding="utf-8") as f:
        json.dump(riassunto, f, ensure_ascii=False, indent=2, allow_nan=False)
    os.replace(percorso + ".tmp", percorso)
    _nota(f"Riassunto salvato per la scheda: {percorso}")
    return {"mm": mm, "stress": st, "verifica": ver, "riassunto": riassunto, "percorso": percorso}


def _sintesi(t):
    """La tabella di sintesi del money management con nomi di colonna stabili (la prima è senza nome)."""
    if t is None:
        return None
    t = t.copy()
    t.columns = ["voce", *[str(c) for c in t.columns[1:]]]
    return t


def leggi_mm(r, id_s: str) -> dict | None:
    """Il riassunto della cella 6 per una strategia, se c'è."""
    p = os.path.join(r.cartella, "mm", f"{id_s}.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ 7 · Le schede
def schede(r) -> list[tuple[str, str]]:
    """Cella 7. Un .md e un .json in <ricerca>/schede/ per ogni strategia entrata in cassaforte; mostra la prima."""
    from engine.fabbrica.schede import componi_scheda, scrivi_scheda, testo_md
    _controlla_versione(r)
    entrate = _cassaforte_dal_registro(r)["entrate"]
    if not entrate:
        _nota("Nessuna strategia è entrata in cassaforte: nessuna scheda.")
        return []
    c = esito_cassaforte(r)
    cartella = os.path.join(r.cartella, "schede")
    num = numerate(r).set_index("id_strategia")["numero"]
    fatte, prima = [], None
    for id_s in sorted(c.trade, key=lambda i: num.get(i, 0)):
        sc = componi_scheda(r, c, id_s, leggi_mm(r, id_s))
        fatte.append(scrivi_scheda(sc, cartella))
        prima = prima or sc
    _titolo(f"Le schede · {len(fatte)} strategie")
    _mostra(("", pd.DataFrame([{"numero": num.get(os.path.basename(m)[:-3]), "scheda": m} for m, _ in fatte])))
    if _v()._in_notebook():
        from IPython.display import Markdown, display
        display(Markdown(testo_md(prima)))
    else:
        print(testo_md(prima))
    return fatte
