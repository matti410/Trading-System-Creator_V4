"""
Il generatore della fabbrica (docs/82 P3, lavoro L3a; C2, docs/82 §11.3–§11.4): dai blocchi alle teorie dei due turni.

    blocchi = blocchi_da_config(config)
    controllo = ControlloDegenerazione(cache)                    # cache del pezzo di ricerca
    rimaste, tolte = togli_degeneri(blocchi, cache, lati, controllo)
    famiglie, misura = misura_famiglie(blocchi, cache, lati, rimaste)
    tenuti, tabella = un_blocco_per_famiglia(blocchi, misura, controllo, lati, rimaste)
    teorie = teorie_turno_1(config, blocchi, tenuti)             # T+U e T+F+U
    resoconto = resoconto_teorie(config, blocchi, tenuti, rimaste, teorie)   # quante teorie e perché
    teorie_2 = teorie_turno_2(scelte, config, blocchi, tenuti)   # alle T+F scelte si aggiunge un secondo filtro
    st = spazio_teoria(teorie[0], blocchi, rimaste)              # lo spazio del passo 1, sui valori larghi

- Una teoria è un lato, un trigger, da 0 a 2 filtri e un'uscita, senza numeri; il suo id è stabile e leggibile, per
  esempio «L|E47|ADX+F3_VOLUME_ABOVE_AVG|X3». I filtri stanno nell'ordine della config.
- Valori degeneri (07/11): per ogni trigger e filtro con parametri e per ogni combinazione della griglia del passo 1 si
  misura collaudo_catalogo.verifica_degenerazione sul pezzo di ricerca, per lato. Le degeneri escono dalla griglia; un
  blocco senza valori su un lato esce da quel lato. C2 (12/11, scelta A): anche i blocchi del catalogo passano dal
  controllo; uno degenere su un lato esce da quel lato, e uno «STATO» (vero su due barre di fila) esce con il motivo
  STATO_CATALOGO e la ricerca prosegue. Per i blocchi con parametri della fabbrica ERRORE, STATO e NON_BOOLEANA restano
  errori del blocco: si ferma. Le uscite non passano dal controllo.
- Un blocco per famiglia (C2, docs/82 §11.3): le famiglie si MISURANO con famiglie.py sul pezzo di ricerca, ai valori
  centrali, lato per lato, trigger fra trigger e filtri fra filtri, fra i blocchi rimasti dopo i degeneri. In ogni
  famiglia resta un blocco: uno dei 14 di P-L2 se c'è (due o più: quello che scatta più spesso), altrimenti quello che
  scatta più spesso (trigger: segnali; filtri: barre vere), a parità il nome più piccolo. La famiglia dichiarata (solo
  ADX e ATR relativo) non entra nella scelta dei tenuti (D1 = B): vale solo nel generatore, mai nella stessa teoria.
- Le misure registrano condizioni temporanee in un registro isolato e poi lo rimettono com'era, identico.
- Sullo spot solo long, anche se la config dicesse altro. Un blocco senza lato short (E19) sta solo sul long.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import itertools
import math
from dataclasses import dataclass

import pandas as pd

from engine import registry as reg
from engine.collaudo_catalogo import verifica_degenerazione
from engine.exchange import solo_long
from engine.famiglie import famiglie as famiglie_misurate

from .ottimizzatore import Categoria, Intero, Spazio

LATI = {"long": 1, "short": -1}
NOME_LATO = {1: "long", -1: "short"}
ESITI_ERRORE = ("ERRORE", "STATO", "NON_BOOLEANA")       # non sono valori degeneri: è codice sbagliato
# C2 (Mattia, 12/11, scelta A): un blocco del catalogo «STATO» sul pezzo di ricerca esce da quel lato con questo motivo.
STATO_CATALOGO = "vero su due barre di fila: non è un evento su questi dati"
_REGISTRI = ("_ENTRY_REGISTRY", "_EXIT_REGISTRY", "_FILTER_REGISTRY", "_BIDIR_ENTRY_REGISTRY", "_ENTRY_DIRECTION",
             "_FILTER_DIRECTION", "_FILTER_PAIR", "_EXIT_DIRECTION", "_EXIT_PAIR")


@contextlib.contextmanager
def _registro_isolato():
    """Dentro il blocco il registro delle condizioni è vuoto; all'uscita torna identico a prima."""
    copie = {nome: dict(getattr(reg, nome)) for nome in _REGISTRI}
    for nome in _REGISTRI:
        getattr(reg, nome).clear()
    try:
        yield
    finally:
        for nome, copia in copie.items():
            d = getattr(reg, nome)
            d.clear()
            d.update(copia)


def stato_registro() -> dict:
    """Una fotografia del registro delle condizioni: per i collaudi «identico prima e dopo»."""
    return {nome: dict(getattr(reg, nome)) for nome in _REGISTRI}


def _serie(maschera, indice) -> pd.Series:
    return pd.Series(maschera, index=indice)


def _chiave_valori(valori: dict) -> tuple:
    return tuple(sorted(valori.items()))


# ------------------------------------------------------------------ la teoria
@dataclass(frozen=True)
class Teoria:
    lato: int
    trigger: str
    filtri: tuple
    uscita: str

    @property
    def id(self) -> str:
        return f"{'L' if self.lato == 1 else 'S'}|{self.trigger}|{'+'.join(self.filtri) or '-'}|{self.uscita}"

    @property
    def blocchi(self) -> tuple:
        return (self.trigger, *self.filtri, self.uscita)


def seme_teoria(seme_ricerca: int, id_teoria: str) -> int:
    """Seme della ricerca + id della teoria: non dipende dall'ordine né dal numero di processi."""
    testo = f"{int(seme_ricerca)}|{id_teoria}".encode("utf-8")
    return int(hashlib.sha256(testo).hexdigest()[:15], 16)


def lati_config(config: dict) -> list[int]:
    """I lati della config, come 1 e -1; sullo spot solo il long."""
    lati = [LATI[x] for x in config["lati"]]
    return [1] if solo_long(config["symbol"]) else lati


# ------------------------------------------------------------------ la degenerazione
class ControlloDegenerazione:
    """
    collaudo_catalogo.verifica_degenerazione su combinazioni di blocchi, sul df della cache (il pezzo di ricerca).
    Ricorda gli esiti: una combinazione già vista non si rimisura. Solo segnali: non è una prova.
    """

    def __init__(self, cache):
        self.cache = cache
        self._esiti: dict = {}

    def _chiave(self, blocco, lato: int, valori: dict) -> tuple:
        return (blocco.nome, 0 if blocco.neutro else lato, _chiave_valori(valori))

    def esiti(self, richieste) -> list[tuple]:
        """Per ogni (blocco, lato, valori): (esito, quota di barre vere). Misura insieme quelle nuove."""
        nuove = {}
        for b, lato, valori in richieste:
            if b.tipo not in ("trigger", "filtro"):
                raise ValueError(f"{b.nome}: il controllo di degenerazione vale per trigger e filtri, non per le uscite")
            k = self._chiave(b, lato, valori)
            if k not in self._esiti and k not in nuove:
                nuove[k] = (b, lato, dict(valori))
        if nuove:
            df, nomi = self.cache.df, {}
            with _registro_isolato():
                for i, (k, (b, lato, valori)) in enumerate(nuove.items()):
                    nome = f"FAB_DEG_{i}"
                    funzione = (lambda d, _b=b, _l=lato, _v=valori: _serie(_b.maschera(self.cache, _l, _v), d.index))
                    if b.tipo == "trigger":
                        reg.register_entry(nome, direction=lato)(funzione)
                    else:
                        reg.register_filter(nome)(funzione)
                    nomi[nome] = k
                with contextlib.redirect_stdout(io.StringIO()):
                    report = verifica_degenerazione(df, verbose=False)
            for r in report.itertuples():
                k = nomi[r.nome]
                b, lato, valori = nuove[k]
                if r.esito in ESITI_ERRORE and not (r.esito == "STATO" and _del_catalogo(b)):
                    raise ValueError(f"{b.nome} {NOME_LATO[lato]} {valori}: verifica_degenerazione dà {r.esito} "
                                     f"{r.errore}: è un errore del blocco, non un valore da togliere.")
                self._esiti[k] = (str(r.esito), float(r.copertura))
        return [self._esiti[self._chiave(b, lato, valori)] for b, lato, valori in richieste]

    def degenere(self, blocco, lato: int, valori: dict) -> bool:
        return self.esiti([(blocco, lato, valori)])[0][0] != "OK"


def _del_catalogo(b) -> bool:
    """Un trigger o un filtro del catalogo: senza parametri, la maschera viene dal registro."""
    return b.tipo in ("trigger", "filtro") and not b.parametri and b._calcola is None


def _lati_blocco(b, lati) -> list[int]:
    """I lati della ricerca su cui il blocco esiste (E19 solo long, C1)."""
    return [lato for lato in lati if lato in b.lati]


def _combinazioni(blocco) -> list[dict]:
    """Tutte le combinazioni della griglia del passo 1, nell'ordine della griglia."""
    nomi = list(blocco.griglia)
    return [dict(zip(nomi, c)) for c in itertools.product(*(blocco.griglia[n] for n in nomi))]


def togli_degeneri(blocchi, cache, lati, controllo: ControlloDegenerazione | None = None) -> tuple[dict, list]:
    """
    (rimaste, tolte). rimaste[(nome, lato)] = le combinazioni non degeneri, nell'ordine della griglia, per ogni
    trigger e filtro con parametri; tolte = una riga per combinazione tolta (blocco, lato, valori, esito, quota di
    barre vere). Un filtro neutro si misura una volta e vale per i due lati: nell'elenco il lato è «entrambi».
    C2: un blocco del catalogo degenere (o «STATO») su un lato ha rimaste[(nome, lato)] = () ed è una riga di tolte con
    valori {}; un blocco del catalogo buono non ha la chiave.
    """
    controllo = controllo or ControlloDegenerazione(cache)
    rimaste, tolte = {}, []
    for b in blocchi:
        if b.tipo == "uscita":
            continue
        combinazioni = _combinazioni(b) if b.parametri else [{}]
        suoi = _lati_blocco(b, lati)
        for lato in suoi:
            esiti = controllo.esiti([(b, lato, c) for c in combinazioni])
            if b.parametri:
                rimaste[(b.nome, lato)] = tuple(c for c, (e, _) in zip(combinazioni, esiti) if e == "OK")
            elif esiti[0][0] != "OK":
                rimaste[(b.nome, lato)] = ()
            if b.neutro and lato != suoi[0]:
                continue
            for c, (e, quota) in zip(combinazioni, esiti):
                if e != "OK":
                    tolte.append({"blocco": b.nome, "lato": "entrambi" if b.neutro and len(suoi) > 1 else NOME_LATO[lato],
                                  "valori": dict(c), "esito": e, "quota_vere": quota})
    return rimaste, tolte


def disponibile(nome: str, lato: int, rimaste: dict) -> bool:
    """Un blocco è usabile su un lato se non è stato svuotato dai valori degeneri (o tolto come «STATO»)."""
    return bool(rimaste.get((nome, lato), (None,)))


# ------------------------------------------------------------------ le famiglie
def _maschera_centrale(b, cache, lato):
    return b.maschera(cache, lato, b.centrali() if b.parametri else None)


def misura_famiglie(blocchi, cache, lati, rimaste: dict | None = None) -> tuple[dict, pd.DataFrame]:
    """
    ({lato: {blocco: famiglia}}, misura). C2 (D1 = B): la famiglia è solo quella MISURATA da famiglie.py sul df della
    cache, ai valori centrali, lato per lato, trigger fra trigger e filtri fra filtri; il nome della famiglia è il nome
    più piccolo del gruppo. Si misurano i blocchi che sul lato esistono e non sono usciti con i valori degeneri
    (`rimaste`). La famiglia dichiarata sta nella colonna «dichiarata» e vale solo nel generatore. Le uscite non si
    misurano. misura: lato, tipo, blocco, dichiarata, gruppo_misurato, piu_vicina, somiglianza (%), vere (segnali o
    barre vere, da famiglie.py), famiglia.
    """
    rimaste = rimaste or {}
    righe, finali = [], {}
    for lato in lati:
        finali[lato] = {}
        for tipo, tipo_reg in (("trigger", "entry"), ("filtro", "filtro")):
            gruppo = [b for b in blocchi if b.tipo == tipo and lato in b.lati and disponibile(b.nome, lato, rimaste)]
            if not gruppo:
                continue
            maschere = {b.nome: _maschera_centrale(b, cache, lato) for b in gruppo}   # prima: il catalogo si registra
            with _registro_isolato():
                for b in gruppo:
                    nome = f"FAB_FAM_{b.nome}"
                    funzione = (lambda d, _m=maschere[b.nome]: _serie(_m, d.index))
                    if tipo == "trigger":
                        reg.register_entry(nome, direction=lato)(funzione)
                    else:
                        reg.register_filter(nome)(funzione)
                tabella = famiglie_misurate(cache.df, tipo=tipo_reg, nomi=[f"FAB_FAM_{b.nome}" for b in gruppo])
            per_nome = {r["nome"][len("FAB_FAM_"):]: r for r in tabella.to_dict("records")}
            membri: dict = {}
            for b in gruppo:
                membri.setdefault(int(per_nome[b.nome]["famiglia"]), []).append(b.nome)
            for nomi in membri.values():
                for n in nomi:
                    finali[lato][n] = min(nomi)
            for b in gruppo:
                r = per_nome[b.nome]
                vicina = r["piu_vicina"]
                righe.append({"lato": NOME_LATO[lato], "tipo": tipo, "blocco": b.nome, "dichiarata": b.famiglia,
                              "gruppo_misurato": int(r["famiglia"]),
                              "piu_vicina": vicina[len("FAB_FAM_"):] if isinstance(vicina, str) else None,
                              "somiglianza": float(r["somiglianza"]), "vere": int(r.get("vere", 0)),
                              "famiglia": finali[lato][b.nome]})
    colonne = ["lato", "tipo", "blocco", "dichiarata", "gruppo_misurato", "piu_vicina", "somiglianza", "vere", "famiglia"]
    return finali, pd.DataFrame(righe, columns=colonne)


# ------------------------------------------------------------------ un blocco per famiglia (C2, docs/82 §11.3)
# I 14 trigger e filtri della lista di P-L2 (docs/82 §8): in una famiglia misurata hanno la precedenza.
QUATTORDICI = ("E5", "E36", "E47", "E49", "E51", "RSI_RIENTRO", "DONCHIAN", "F2_MID_VOLATILITY", "F3_VOLUME_ABOVE_AVG",
               "TREND_CONTEXT", "F25_CHOP_TREND", "F20_SESSION_OVERLAP", "ADX", "ATR_RELATIVO")
TENUTO, TOLTO = "tenuto", "tolto"
_DEGENERI_IN_PAROLE = {"SEMPRE_FALSA": "mai vero", "SEMPRE_VERA": "sempre vero",
                       "QUASI_SEMPRE_VERA": "vero su almeno il 95% delle barre", "RARA": "scatta meno di 30 volte"}
COLONNE_TENUTI = ["lato", "tipo", "famiglia", "blocco", "esito", "motivo", "scatta", "quota_barre", "piu_simile",
                  "somiglianza"]


def _scatta(b, lato: int, controllo: ControlloDegenerazione) -> tuple[int, float]:
    """(segnali o barre vere, quota di barre vere) dal controllo dei degeneri, ai valori centrali per i blocchi con
    parametri: nessun calcolo nuovo. Per un trigger le barre vere sono i segnali (un evento è una barra sola)."""
    valori = b.centrali() if b.parametri else {}
    _, quota = controllo.esiti([(b, lato, valori)])[0]
    return int(round(quota * len(controllo.cache.df))), float(quota)


def _n(x: int) -> str:
    return f"{int(x):,}".replace(",", ".")


def un_blocco_per_famiglia(blocchi, misura: pd.DataFrame, controllo: ControlloDegenerazione, lati,
                           rimaste: dict | None = None) -> tuple[dict, list[dict]]:
    """
    (tenuti, tabella). tenuti = {lato: [nomi dei trigger e filtri tenuti, nell'ordine della config]}. tabella = una
    riga per blocco e lato (COLONNE_TENUTI): famiglia misurata, tenuto o tolto, motivo, quanto scatta (segnali per i
    trigger, barre vere per i filtri, e la quota di barre), il blocco più simile e quanto gli somiglia (%). I blocchi
    usciti con i valori degeneri (o «STATO») sono righe «tolto» con il loro motivo e senza famiglia.
    Regola (docs/82 §11.3): in ogni famiglia resta uno dei 14 di P-L2 se c'è; se ce ne sono due o più, quello che
    scatta più spesso; senza i 14, quello che scatta più spesso; a parità il nome più piccolo.
    """
    rimaste = rimaste or {}
    misurati = {(r["lato"], r["blocco"]): r for r in misura.to_dict("records")} if len(misura) else {}
    ordine = {b.nome: i for i, b in enumerate(blocchi)}
    tenuti, tabella = {}, []
    for lato in lati:
        nl = NOME_LATO[lato]
        tenuti[lato] = []
        for tipo in ("trigger", "filtro"):
            unita = "segnali" if tipo == "trigger" else "barre vere"
            gruppo = [b for b in blocchi if b.tipo == tipo and lato in b.lati]
            vivi = [b for b in gruppo if disponibile(b.nome, lato, rimaste)]
            conta = {b.nome: _scatta(b, lato, controllo) for b in gruppo}
            famiglie: dict = {}
            for b in vivi:
                famiglie.setdefault(misurati[(nl, b.nome)]["famiglia"], []).append(b.nome)
            scelto = {}
            for fam, membri in famiglie.items():
                dei14 = [n for n in membri if n in QUATTORDICI]
                scelto[fam] = sorted(dei14 or membri, key=lambda n: (-conta[n][0], n))[0]
            for b in gruppo:
                n = b.nome
                riga = {"lato": nl, "tipo": tipo, "famiglia": None, "blocco": n, "esito": TOLTO, "motivo": "",
                        "scatta": conta[n][0], "quota_barre": conta[n][1], "piu_simile": None, "somiglianza": None}
                if not disponibile(n, lato, rimaste):
                    if b.parametri:
                        riga["motivo"] = "tutte le combinazioni della griglia sono degeneri"
                    else:
                        esito = controllo.esiti([(b, lato, {})])[0][0]
                        riga["motivo"] = (STATO_CATALOGO if esito == "STATO" else
                                          f"degenere sul pezzo di ricerca ({_DEGENERI_IN_PAROLE.get(esito, esito)})")
                    tabella.append(riga)
                    continue
                m = misurati[(nl, n)]
                fam = m["famiglia"]
                membri = famiglie[fam]
                t = scelto[fam]
                dei14 = [x for x in membri if x in QUATTORDICI]
                riga.update(famiglia=fam, piu_simile=m["piu_vicina"], somiglianza=float(m["somiglianza"]))
                if n == t:
                    riga["esito"] = TENUTO
                    riga["motivo"] = ("solo nella sua famiglia" if len(membri) == 1 else
                                      "uno dei 14 di oggi" if len(dei14) == 1 else
                                      "dei 14 di oggi, scatta più spesso" if dei14 else "scatta più spesso")
                elif t in QUATTORDICI and n not in QUATTORDICI:
                    riga["motivo"] = f"stessa famiglia di {t}, che è uno dei 14 di oggi"
                else:
                    riga["motivo"] = (f"stessa famiglia di {t}, che scatta più spesso ({_n(conta[t][0])} {unita} "
                                      f"contro {_n(conta[n][0])})")
                tabella.append(riga)
            tenuti[lato] += [b.nome for b in vivi if scelto[misurati[(nl, b.nome)]["famiglia"]] == b.nome]
        tenuti[lato] = sorted(tenuti[lato], key=ordine.get)
    return tenuti, tabella


# ------------------------------------------------------------------ le teorie dei due turni
def _per_tipo(blocchi, tipo):
    return [b.nome for b in blocchi if b.tipo == tipo]


def _filtri_modelli(config: dict) -> set:
    """Quanti filtri ammettono i modelli della config (0, 1, 2)."""
    return {k for m in config["modelli"] for k in range(m["filtri"][0], m["filtri"][1] + 1)}


def teorie_turno_1(config: dict, blocchi, tenuti: dict) -> list[Teoria]:
    """
    Turno 1 (docs/82 §11.4): per ogni lato, con i blocchi tenuti, tutte le teorie T+U e T+F+U che i modelli ammettono,
    sempre nello stesso ordine: lato, trigger, filtro, uscita, nell'ordine della config.
    """
    teorie, ammessi = {}, _filtri_modelli(config) & {0, 1}
    uscite = _per_tipo(blocchi, "uscita")
    for lato in lati_config(config):
        suoi = set(tenuti.get(lato, ()))
        trigger = [n for n in _per_tipo(blocchi, "trigger") if n in suoi]
        filtri = [n for n in _per_tipo(blocchi, "filtro") if n in suoi]
        scelte = ([()] if 0 in ammessi else []) + ([(f,) for f in filtri] if 1 in ammessi else [])
        for t in trigger:
            for scelta in scelte:
                for u in uscite:
                    teoria = Teoria(lato, t, scelta, u)
                    teorie.setdefault(teoria.id, teoria)
    return list(teorie.values())


def filtri_compatibili(filtro: str, lato: int, blocchi, tenuti: dict) -> list[str]:
    """I filtri tenuti dello stesso lato che possono stare con `filtro`: non lui, e mai la stessa famiglia dichiarata
    (ADX con ATR relativo, D1 = B). Nell'ordine della config."""
    per_nome = {b.nome: b for b in blocchi}
    suoi = set(tenuti.get(lato, ()))
    return [n for n in _per_tipo(blocchi, "filtro")
            if n in suoi and n != filtro and per_nome[n].famiglia != per_nome[filtro].famiglia]


def teorie_turno_2(scelte, config: dict, blocchi, tenuti: dict) -> list[Teoria]:
    """
    Turno 2 (docs/82 §11.4): a ogni teoria T+F di `scelte` (in quell'ordine) si aggiunge un secondo filtro, tutti quelli
    compatibili (filtri_compatibili); stesso lato, trigger e uscita. I due filtri stanno nell'ordine della config, così
    T+F1 e T+F2 danno la stessa T+F1+F2, che si prova una volta sola. Nessuna teoria se i modelli non ammettono due
    filtri.
    """
    if 2 not in _filtri_modelli(config):
        return []
    posto = {n: i for i, n in enumerate(_per_tipo(blocchi, "filtro"))}
    teorie = {}
    for s in scelte:
        if len(s.filtri) != 1:
            raise ValueError(f"turno 2: {s.id} non è una teoria T+F")
        for f2 in filtri_compatibili(s.filtri[0], s.lato, blocchi, tenuti):
            filtri = tuple(sorted((s.filtri[0], f2), key=posto.get))
            teoria = Teoria(s.lato, s.trigger, filtri, s.uscita)
            teorie.setdefault(teoria.id, teoria)
    return list(teorie.values())


def resoconto_teorie(config: dict, blocchi, tenuti: dict, rimaste: dict, teorie) -> dict:
    """
    Per il registro: le teorie del turno 1 per lato; per lato quanti trigger e filtri c'erano e quanti sono tenuti; i
    blocchi usciti con i valori degeneri; le coppie di filtri tenuti con la stessa famiglia dichiarata (mai insieme).
    """
    out = {"teorie": len(teorie), "per_lato": {}, "blocchi": {}, "blocchi_usciti": [], "coppie_stessa_famiglia": []}
    per_nome = {b.nome: b for b in blocchi}
    for lato in lati_config(config):
        nl = NOME_LATO[lato]
        out["per_lato"][nl] = sum(t.lato == lato for t in teorie)
        suoi = set(tenuti.get(lato, ()))
        out["blocchi"][nl] = {tipo: {"blocchi": sum(1 for b in blocchi if b.tipo == tipo and lato in b.lati),
                                     "tenuti": sum(1 for b in blocchi if b.tipo == tipo and b.nome in suoi)}
                              for tipo in ("trigger", "filtro")}
        for b in blocchi:
            if b.tipo != "uscita" and lato in b.lati and not disponibile(b.nome, lato, rimaste):
                out["blocchi_usciti"].append({"blocco": b.nome, "lato": nl,
                                              "perche": "tutte le combinazioni della griglia sono degeneri"
                                              if b.parametri else "degenere o «STATO» sul pezzo di ricerca"})
        filtri = [n for n in _per_tipo(blocchi, "filtro") if n in suoi]
        for a, c in itertools.combinations(filtri, 2):
            if per_nome[a].famiglia == per_nome[c].famiglia:
                out["coppie_stessa_famiglia"].append({"lato": nl, "filtri": [a, c], "famiglia": per_nome[a].famiglia})
    if solo_long(config["symbol"]):
        out["solo_long"] = "spot: lo short non esiste"
    return out


# ------------------------------------------------------------------ lo spazio del passo 1
class SpazioTeoria:
    """
    Lo spazio del passo 1 di una teoria, sui valori larghi della griglia (docs/82 P4): un parametro dell'ottimizzatore
    per ogni parametro di ogni blocco, chiamato «BLOCCO.parametro». I numeri sono indici sulla lista dei valori larghi
    (in ordine), il target è una Categoria. Dopo i valori degeneri ogni parametro tiene solo i valori che compaiono in
    almeno una combinazione rimasta; una combinazione tolta resta nello spazio ma `ammesso` la rifiuta.
    """

    def __init__(self, teoria: Teoria, blocchi, rimaste: dict):
        per_nome = {b.nome: b for b in blocchi}
        self.teoria = teoria
        self._valori, self._ammesse, self._categorie, parametri = {}, {}, set(), []
        for nome in teoria.blocchi:
            b = per_nome[nome]
            combinazioni = rimaste.get((nome, teoria.lato))
            if combinazioni is not None:
                self._ammesse[nome] = {_chiave_valori(c) for c in combinazioni}
            for p in b.parametri:
                valori = b.griglia[p.nome]
                if combinazioni is not None:
                    usati = {c[p.nome] for c in combinazioni}
                    valori = tuple(v for v in valori if v in usati)
                chiave = f"{nome}.{p.nome}"
                self._valori[chiave] = tuple(valori)
                if isinstance(p, Categoria):
                    self._categorie.add(chiave)
                    parametri.append(Categoria(chiave, tuple(valori)))
                else:
                    parametri.append(Intero(chiave, 0, len(valori) - 1, 1))
        self.spazio = Spazio(parametri)

    @property
    def griglie(self) -> dict:
        """«BLOCCO.parametro» -> i valori larghi rimasti dopo i valori degeneri, in ordine (i confini dello zoom)."""
        return dict(self._valori)

    def quanti_ammessi(self) -> int:
        """I punti ammessi, senza elencarli: le combinazioni rimaste dei blocchi misurati per gli altri valori."""
        n = 1
        for nome in self.teoria.blocchi:
            if nome in self._ammesse:
                n *= len(self._ammesse[nome])
            else:
                n *= math.prod(len(v) for k, v in self._valori.items() if k.split(".", 1)[0] == nome)
        return n

    def valori(self, punto: dict) -> dict:
        """Da un punto dell'ottimizzatore a {blocco: {parametro: valore}}, per tutti i blocchi della teoria."""
        out = {nome: {} for nome in self.teoria.blocchi}
        for chiave, x in punto.items():
            nome, parametro = chiave.split(".", 1)
            # Spazio.punto dà l'indice per gli Intero e il valore per le Categoria
            out[nome][parametro] = x if chiave in self._categorie else self._valori[chiave][x]
        return out

    def ammesso(self, valori: dict) -> bool:
        """False se un blocco ha una combinazione tolta come degenere."""
        return all(_chiave_valori(valori[nome]) in ammesse for nome, ammesse in self._ammesse.items())

    def punti_ammessi(self) -> list[dict]:
        """Tutti i punti ammessi, nell'ordine della griglia: per la griglia completa quando ci sta."""
        nomi = [p.nome for p in self.spazio.parametri]
        punti = []
        for indici in itertools.product(*(range(p.n) for p in self.spazio.parametri)):
            punto = self.spazio.punto(indici)
            if self.ammesso(self.valori(punto)):
                punti.append(dict(zip(nomi, (punto[n] for n in nomi))))
        return punti


def spazio_teoria(teoria: Teoria, blocchi, rimaste: dict) -> SpazioTeoria:
    return SpazioTeoria(teoria, blocchi, rimaste)
