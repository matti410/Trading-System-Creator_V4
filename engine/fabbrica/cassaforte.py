"""
La cassaforte della fabbrica (docs/82 P8, lavoro L4b): le strategie scelte si congelano nel registro, e solo dopo si
legge l'ultimo pezzo di dati. Dal 10/11 (docs/81 §2): ogni strategia entra quante volte si vuole, senza frase di
conferma; il registro degli ingressi resta, solo come annotazione da leggere.

    esito = entra(cartella_dati, id_ricerca, ["id1", "id2"])
    esito.tabella        # una riga per strategia: t di selezione, trade, EV (ATR e bp), t in cassaforte, soglia, esito
    esito.per_moneta     # una riga per strategia e moneta (trade, EV, t): solo da leggere (docs/82 §14.1)
    esito.trade          # {id_strategia: {symbol: trade del motore completo sulla cassaforte}}
    esito_cassaforte(cartella_dati, id_ricerca)    # rifà l'esito delle strategie già entrate (nessun ingresso nuovo)

L'ordine di `entra`, che è la regola (docs/82 P8):
1. senza leggere una barra: config e selezione della ricerca (selezione.json), ogni strategia «scelta» in selezione
   (selezione.controlla_ammessa);
2. l'elenco congelato si scrive nel registro dell'asset (evento «ingresso_cassaforte»): strategie, tratto, ricerca,
   impronta della config, strategie entrate nel tratto fino a quel momento;
3. solo ora il permesso (dati.PermessoCassaforte, uno per moneta) e la lettura dei dati: le impronte di ricerca e
   selezione di ogni moneta devono essere quelle dell'avvio della ricerca;
4. ogni strategia sul pezzo di cassaforte di ogni moneta con il motore completo (valutatore.trade_completi): ricerca,
   selezione e cassaforte attaccate per gli indicatori, i segnali spenti prima della prima barra della cassaforte,
   l'ultima barra è quella della cassaforte e un trade ancora aperto lì resta fuori (motore, U7). Costi e funding del
   pezzo di cassaforte di ogni moneta. I trade di tutte le monete in un solo elenco, in ATR, con il t dei trade
   sovrapposti (docs/82 §14.2). Decide il test individuale: t netto >= selezione.soglia_test(alfa) = 1,96. Ogni
   strategia è una prova (pezzo «cassaforte») nel file delle prove della ricerca; l'esito va nel registro (evento
   «esito_cassaforte»).

- Il tratto è la lista di monete, timeframe, inizio e fine della cassaforte (stesse date per tutte le monete). Una strategia può entrare più volte, nello stesso
  tratto o in altri (10/11): ogni ingresso è un evento nel registro e ha il suo esito. Le prove non crescono: la stessa
  strategia sulla stessa cassaforte è la stessa prova (registro.CHIAVE_PROVA). Un parametro cambiato è una strategia
  nuova (valutatore.id_strategia).
- Le strategie entrate in un tratto (ognuna una volta) sono un numero da leggere, contato su tutte le macchine; non
  decide nulla.
- Il registro è un file di annotazioni, solo in aggiunta (10/11, scelta B): niente catena di impronte, non ferma
  niente (registro.py). PC e Colab che scrivono nello stesso momento, prima che Drive sincronizzi, non si vedono.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import pandas as pd

import numpy as np

from engine.giudizio import soglia_rumore
from engine.indicatori import aggiungi_indicatori
from engine.metriche import pips_per_trade

from . import registro
from .config import cartella_asset, controlla_config, impronta_config, nome_lista
from .dati import Confini, PermessoCassaforte, _utc, carica_pezzi, imposta_mercato_crypto
from .generatore import NOME_LATO
from .selezione import (COLONNE_MONETA, controlla_ammessa, righe_per_moneta, soglia_test, strategia_da_riga,
                        valutatore_lista)
from .valutatore import durata_uscita, id_strategia, in_atr, misure_lista, trade_completi, unisci

PEZZO = "cassaforte"
FASE = "cassaforte"
INGRESSO, ESITO = "ingresso_cassaforte", "esito_cassaforte"
LIMITE_CACHE_MB = 1500

__all__ = ["EsitoCassaforte", "congela", "entra", "esito_cassaforte", "gia_entrata", "id_strategia",
           "strategie_entrate", "tratti_usati", "tratto"]


# ------------------------------------------------------------------ il tratto e il registro
def tratto(monete, timeframe: str, confini: Confini) -> str:
    """L'identità del tratto di cassaforte: la lista di monete (config.nome_lista), timeframe, inizio e fine (UTC)."""
    da, a = confini.tratto_cassaforte
    return f"{nome_lista(monete)}_{timeframe}_{da:%Y%m%dT%H%M}_{a:%Y%m%dT%H%M}"


def _ingressi(eventi, id_tratto: str | None = None) -> list[dict]:
    return [e for e in eventi if e.get("tipo") == INGRESSO and (id_tratto is None or e["tratto"]["id"] == id_tratto)]


def _entrate(eventi, id_tratto: str) -> list[str]:
    """Gli id delle strategie entrate nel tratto, nell'ordine, una volta ciascuno (tutte le macchine)."""
    return list(dict.fromkeys(s["id_strategia"] for e in _ingressi(eventi, id_tratto) for s in e["strategie"]))


def gia_entrata(cartella_asset_, id_tratto: str, id_strat: str) -> bool:
    """La strategia è già entrata in questo tratto? Guarda solo quel tratto, su tutte le macchine."""
    return id_strat in _entrate(registro.leggi_registro(cartella_asset_), id_tratto)


def strategie_entrate(cartella_asset_, id_tratto: str) -> int:
    """Il conto delle strategie entrate nel tratto: da leggere, non decide."""
    return len(_entrate(registro.leggi_registro(cartella_asset_), id_tratto))


def congela(cartella_asset_, confini: Confini, monete, timeframe: str, strategie: list[dict], dove: dict,
            nome_macchina: str | None = None) -> dict:
    """
    Il passo 2 di `entra`, da solo: controlli sul registro e scrittura dell'elenco. `strategie` = righe con
    id_strategia (e teoria, valori, t_selezione); `dove` = id_ricerca e impronta_config. Ritorna l'evento scritto.
    """
    eventi = registro.leggi_registro(cartella_asset_)
    id_tratto = tratto(monete, timeframe, confini)
    da, a = confini.tratto_cassaforte
    ids = [s["id_strategia"] for s in strategie]
    if not ids:
        raise ValueError("nessuna strategia da far entrare.")
    if len(set(ids)) != len(ids):
        raise ValueError("una strategia compare due volte nell'elenco.")
    gia = _entrate(eventi, id_tratto)                # (10/11) una strategia già entrata può rientrare
    evento = {"tipo": INGRESSO, **dove,
              "tratto": {"id": id_tratto, "monete": list(monete), "timeframe": timeframe, "da": da.isoformat(),
                         "a": a.isoformat()},
              "strategie": strategie, "entrate_nel_tratto": len(set(gia) | set(ids))}
    return registro.scrivi_evento(cartella_asset_, evento, nome_macchina)


# ------------------------------------------------------------------ la ricerca da cui vengono le strategie
def _ricerca(cartella_dati, id_ricerca: str) -> tuple[dict, str, str, pd.DataFrame]:
    """(config, cartella dell'asset, cartella della ricerca, tabella della selezione), senza leggere barre."""
    trovate = []
    base_fabbrica = os.path.join(str(cartella_dati), "fabbrica")
    if os.path.isdir(base_fabbrica):
        for asset in sorted(os.listdir(base_fabbrica)):
            if os.path.isfile(os.path.join(base_fabbrica, asset, id_ricerca, "config.json")):
                trovate.append(os.path.join(base_fabbrica, asset, id_ricerca))
    if len(trovate) != 1:
        raise ValueError(f"ricerca {id_ricerca!r} non trovata in {base_fabbrica} (o trovata due volte).")
    cartella = trovate[0]
    with open(os.path.join(cartella, "config.json"), encoding="utf-8") as f:
        config = controlla_config(json.load(f))
    percorso = os.path.join(cartella, "selezione.json")
    if not os.path.exists(percorso):
        raise ValueError(f"la ricerca {id_ricerca} non ha ancora la selezione: lanciala fino in fondo.")
    with open(percorso, encoding="utf-8") as f:
        tabella = pd.DataFrame(json.loads(f.read())["tabella"])
    return config, cartella_asset(cartella_dati, config["monete"], config["timeframe"]), cartella, tabella


def _impronte_avvio(eventi, id_ricerca: str) -> dict:
    for e in eventi:
        if e.get("tipo") == "avvio_ricerca" and e.get("id_ricerca") == id_ricerca:
            return e["impronte_dati"]
    raise ValueError(f"nel registro non c'è l'avvio della ricerca {id_ricerca}.")


# ------------------------------------------------------------------ il pezzo e la valutazione
@dataclass
class PezzoCassaforte:
    """Ricerca + selezione + cassaforte con gli indicatori, la prima barra della cassaforte e i costi della cassaforte."""
    df: pd.DataFrame
    inizio: int
    costi: dict


def pezzo_cassaforte(pezzi, aperta: dict) -> PezzoCassaforte:
    """I tre pezzi attaccati, con gli indicatori; finisce all'ultima barra della cassaforte."""
    from engine.vetrina import costi_storico
    imposta_mercato_crypto()
    cas = aperta["df"]
    if not len(cas) or not pezzi.selezione.index[-1] < cas.index[0]:
        raise ValueError("la cassaforte è vuota o si sovrappone alla selezione.")
    df = aggiungi_indicatori(pd.concat([pezzi.ricerca, pezzi.selezione, cas]))
    inizio = int(pd.DatetimeIndex(df.index).searchsorted(cas.index[0]))
    if not pd.DatetimeIndex(df.index[inizio:]).equals(pd.DatetimeIndex(cas.index)):
        raise ValueError("il pezzo di cassaforte ha perso delle barre con gli indicatori: si ferma.")
    costi = dict(costi_storico(pezzi.symbol, cas, funding=aperta["funding"], df_prezzo=cas)[0])
    if aperta["funding"] is not None:
        costi["funding"] = pd.concat([f for f in (pezzi.funding["ricerca"], pezzi.funding["selezione"],
                                                  aperta["funding"]) if f is not None])
    return PezzoCassaforte(df, inizio, costi)


@dataclass
class EsitoCassaforte:
    tratto: dict
    tabella: pd.DataFrame
    trade: dict = field(default_factory=dict)          # {id_strategia: {symbol: trade}}
    ingressi: list = field(default_factory=list)
    conto: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    pezzi: object = None              # dati.PezziLista: ricerca e selezione di ogni moneta
    pezzo: dict = field(default_factory=dict)          # {symbol: PezzoCassaforte}: i tre pezzi attaccati (passo 9)
    per_moneta: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=COLONNE_MONETA))


def misure_trade(trade_per_moneta: dict, valutatore, H: int):
    """
    Le misure dei trade del motore completo di ogni moneta ({symbol: trade}): netto in ATR al segnale e in bp, barra
    d'ingresso sull'orologio comune; ritorna (Misure della lista, {symbol: Misure}).
    """
    per = {}
    for m, t in trade_per_moneta.items():
        v = valutatore.per_moneta[m]
        _, netti = pips_per_trade(t, v.costi.pip, v.costi.commission)
        eb = t["EntryBar"].to_numpy(dtype=np.int64)
        per[m] = {"pos": valutatore.orologi[m][eb], "atr": in_atr(netti.to_numpy(dtype=float), v.costi.pip,
                                                                  valutatore.atr[m][eb - 1]),
                  "bp": t["BpNetti"].to_numpy(dtype=float)}
    u = unisci(per)
    tutti = misure_lista(u["atr"], u["bp"], u["pos"], H, valutatore.settimana)
    return tutti, {m: misure_lista(x["atr"], x["bp"], x["pos"], H, valutatore.settimana) for m, x in per.items()}


def _valuta(config, pezzi, aperte: dict, righe_sel: pd.DataFrame):
    monete = config["monete"]
    p = {m: pezzo_cassaforte(pezzi[m], aperte[m]) for m in monete}
    v = valutatore_lista(config, p)
    soglia = soglia_test(config["test_individuale"]["alfa"])
    righe, trade, per_moneta = [], {}, []
    for r in righe_sel.to_dict("records"):
        s = strategia_da_riga(r, monete, config["timeframe"])
        t = {m: trade_completi(s, v.per_moneta[m], p[m].costi) for m in monete}
        mis, per = misure_trade(t, v, durata_uscita(s))
        passa = bool(mis.t == mis.t and mis.t >= soglia)
        righe.append({"teoria": r["teoria"], "id_strategia": r["id_strategia"], "lato": NOME_LATO[s.lato],
                      "t_selezione": r["t"], "ev_atr_selezione": r["ev_atr"], **mis.come_dict(), "soglia_test": soglia,
                      "esito": "passa" if passa else "non passa",
                      "motivo": "" if passa else (f"t {mis.t:.2f} sotto {soglia:.2f}" if mis.t == mis.t
                                                  else "t non calcolabile")})
        per_moneta += righe_per_moneta(r["id_strategia"], per)
        trade[r["id_strategia"]] = t
    return pd.DataFrame(righe), trade, p, pd.DataFrame(per_moneta, columns=COLONNE_MONETA)


def _apri_e_valuta(cartella_dati, config, base, cartella, id_ricerca, ingressi: list[dict], tabella_sel,
                   scrivi: bool) -> EsitoCassaforte:
    """Passi 3 e 4: permesso, lettura, valutazione, prove ed esito nel registro (una volta per ingresso)."""
    monete, timeframe = config["monete"], config["timeframe"]
    confini = Confini.da_config(config["confini"])
    pezzi = carica_pezzi(monete, timeframe, confini, cartella_dati)
    eventi = registro.leggi_registro(base)
    if pezzi.impronte != _impronte_avvio(eventi, id_ricerca):
        raise ValueError("i dati di ricerca o selezione sono cambiati dall'avvio della ricerca: la cassaforte non si "
                         "valuta.")
    aperte = {m: pezzi[m].apri_cassaforte(PermessoCassaforte(m, timeframe, confini.tratto_cassaforte)) for m in monete}
    ids = list(dict.fromkeys(s["id_strategia"] for e in ingressi for s in e["strategie"]))
    righe_sel = tabella_sel.set_index("id_strategia").loc[ids].reset_index()
    tab, trade, pezzo, per_moneta = _valuta(config, pezzi, aperte, righe_sel)
    prove = registro.FileProve(cartella)
    prove.aggiungi([{"id_ricerca": id_ricerca, "pezzo": PEZZO, "fase": FASE, "teoria": r.teoria,
                     "id_strategia": r.id_strategia, "trade": r.trade, "ev_atr": r.ev_atr, "t": r.t}
                    for r in tab.itertuples()])
    k = registro.conto_prove(cartella_dati, monete, timeframe)
    id_tratto = ingressi[0]["tratto"]["id"]
    eventi = registro.leggi_registro(base)
    conto = {"asset": k, "soglia_da_leggere": soglia_rumore(k, config["test_individuale"]["alfa"]) if k else None,
             "entrate_nel_tratto": len(_entrate(eventi, id_tratto))}
    tab["prove_asset"], tab["soglia_da_leggere"] = conto["asset"], conto["soglia_da_leggere"]
    tab["entrate_nel_tratto"] = conto["entrate_nel_tratto"]
    if scrivi:
        fatti = {(e["ingresso"]["macchina"], e["ingresso"]["n"]) for e in eventi if e.get("tipo") == ESITO}
        for e in ingressi:
            if (e["macchina"], e["n"]) in fatti:
                continue
            mie = [s["id_strategia"] for s in e["strategie"]]
            sotto = tab.set_index("id_strategia").loc[mie].reset_index()
            registro.scrivi_evento(base, {
                "tipo": ESITO, "id_ricerca": id_ricerca, "tratto": e["tratto"],
                "ingresso": {"macchina": e["macchina"], "n": e["n"]},
                "risultati": sotto[["id_strategia", "trade", "ev_atr", "ev_bp", "t", "soglia_test", "esito"]]
                .to_dict("records"),
                "prove": {"asset": conto["asset"], "soglia_da_leggere": conto["soglia_da_leggere"]},
                "entrate_nel_tratto": conto["entrate_nel_tratto"]})
    return EsitoCassaforte(ingressi[0]["tratto"], tab, trade, ingressi, conto, config, pezzi, pezzo, per_moneta)


# ------------------------------------------------------------------ le funzioni pubbliche
def entra(cartella_dati, id_ricerca: str, strategie) -> EsitoCassaforte:
    """
    Fa entrare in cassaforte le strategie (id) di una ricerca finita, nell'ordine della testa del file. Senza frase
    di conferma e anche se sono già entrate (10/11).
    """
    config, base, cartella, tabella = _ricerca(cartella_dati, id_ricerca)
    ids = list(strategie)
    for i in ids:
        controlla_ammessa(tabella, i)
    per_id = tabella.set_index("id_strategia")
    elenco = [{"id_strategia": i, "teoria": per_id.loc[i, "teoria"], "valori": json.loads(per_id.loc[i, "valori"]),
               "t_selezione": float(per_id.loc[i, "t"])} for i in ids]
    evento = congela(base, Confini.da_config(config["confini"]), config["monete"], config["timeframe"], elenco,
                     {"id_ricerca": id_ricerca, "impronta_config": impronta_config(config)})
    return _apri_e_valuta(cartella_dati, config, base, cartella, id_ricerca, [evento], tabella, scrivi=True)


def esito_cassaforte(cartella_dati, id_ricerca: str) -> EsitoCassaforte:
    """
    Le strategie di questa ricerca già entrate nel suo tratto, rivalutate (stessi numeri, nessun ingresso nuovo); scrive
    l'esito degli ingressi che non l'hanno ancora (per esempio dopo un'interruzione fra l'ingresso e la lettura).
    """
    config, base, cartella, tabella = _ricerca(cartella_dati, id_ricerca)
    id_tratto = tratto(config["monete"], config["timeframe"], Confini.da_config(config["confini"]))
    ingressi = [e for e in _ingressi(registro.leggi_registro(base), id_tratto) if e.get("id_ricerca") == id_ricerca]
    if not ingressi:
        raise ValueError(f"nessuna strategia della ricerca {id_ricerca} è entrata in cassaforte.")
    return _apri_e_valuta(cartella_dati, config, base, cartella, id_ricerca, ingressi, tabella, scrivi=True)


def trade_entrata(cartella_dati, config: dict, riga: dict, impronte: dict | None = None) -> tuple:
    """
    (L5a, per la scheda, docs/82 P10) I trade sulla cassaforte di una strategia GIÀ ENTRATA nel tratto della config,
    rifatti da capo: stesso pezzo, stessi costi, stesso motore di `entra`, quindi gli stessi trade al bit. Nessun
    ingresso nuovo, nessuna prova, niente nel registro. Si ferma se la strategia non è entrata in quel tratto e, con
    `impronte` ({symbol: {ricerca, selezione, cassaforte}}), se i dati non sono più quelli. `config` basta che abbia
    monete, timeframe, confini e i blocchi della strategia; `riga` = teoria, valori, id_strategia.
    Ritorna ({symbol: trade}, impronte dei tre pezzi di ogni moneta).
    """
    from .dati import impronta_pezzo
    monete, timeframe = config["monete"], config["timeframe"]
    confini = Confini.da_config(config["confini"])
    base = cartella_asset(cartella_dati, monete, timeframe)
    if not gia_entrata(base, tratto(monete, timeframe, confini), riga["id_strategia"]):
        raise ValueError(f"la strategia {riga['id_strategia']} non è entrata nel tratto di cassaforte della scheda: "
                         "i suoi trade di cassaforte non si rifanno.")
    pezzi = carica_pezzi(monete, timeframe, confini, cartella_dati)
    aperte = {m: pezzi[m].apri_cassaforte(PermessoCassaforte(m, timeframe, confini.tratto_cassaforte)) for m in monete}
    trovate = {m: {**pezzi[m].impronte, "cassaforte": impronta_pezzo(aperte[m]["df"])} for m in monete}
    if impronte is not None and dict(impronte) != trovate:
        raise ValueError("i dati non sono più quelli della scheda (impronte diverse): i trade non si rifanno.")
    p = {m: pezzo_cassaforte(pezzi[m], aperte[m]) for m in monete}
    v = valutatore_lista(config, p)
    s = strategia_da_riga(riga, monete, timeframe)
    return {m: trade_completi(s, v.per_moneta[m], p[m].costi) for m in monete}, trovate


def tratti_usati(cartella_asset_) -> list[tuple]:
    """I tratti di cassaforte già usati per l'asset, come (da, a) in UTC."""
    return sorted({(_utc(e["tratto"]["da"]), _utc(e["tratto"]["a"])) for e in _ingressi(registro.leggi_registro(
        cartella_asset_))})
