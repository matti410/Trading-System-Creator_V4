"""
Il generatore della fabbrica (docs/82 P3, lavoro L3a): dai blocchi alle teorie.

    blocchi = blocchi_da_config(config)
    controllo = ControlloDegenerazione(cache)                    # cache del pezzo di ricerca
    rimaste, tolte = togli_degeneri(blocchi, cache, lati, controllo)
    famiglie, misura = misura_famiglie(blocchi, cache, lati)
    teorie = genera_teorie(config, blocchi, famiglie, rimaste)
    resoconto = resoconto_teorie(config, blocchi, famiglie, rimaste, teorie)   # quante teorie e perché
    st = spazio_teoria(teorie[0], blocchi, rimaste)              # lo spazio del passo 1, sui valori larghi

- Una teoria è un lato, un trigger, da 0 a 2 filtri e un'uscita, senza numeri; il suo id è stabile e leggibile, per
  esempio «L|E47|ADX+F3_VOLUME_ABOVE_AVG|X3». Si scarta una teoria con due filtri della stessa famiglia.
- Famiglie (decisione del 07/11): due blocchi stanno insieme se li unisce famiglie.py sul pezzo di ricerca, ai
  valori centrali, oppure se hanno la stessa famiglia dichiarata nel blocco (ADX e ATR relativo). Si misura per lato,
  perché i filtri a coppia (TREND_CONTEXT) hanno una maschera per lato. Usa solo i segnali: non è una prova.
- Valori degeneri (decisione del 07/11): per ogni trigger e filtro con parametri e per ogni combinazione della griglia
  del passo 1 si misura collaudo_catalogo.verifica_degenerazione sul pezzo di ricerca, per lato. Le degeneri escono
  dalla griglia; un blocco senza valori su un lato esce da quel lato. Le uscite non passano dal controllo: durata,
  stop e target non cambiano la loro maschera. Esiti ERRORE e STATO non sono valori da togliere ma errori: si ferma.
- Le misure registrano condizioni temporanee in un registro isolato e poi lo rimettono com'era, identico.
- Sullo spot solo long, anche se la config dicesse altro.
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
                if r.esito in ESITI_ERRORE:
                    b, lato, valori = nuove[k]
                    raise ValueError(f"{b.nome} {NOME_LATO[lato]} {valori}: verifica_degenerazione dà {r.esito} "
                                     f"{r.errore}: è un errore del blocco, non un valore da togliere.")
                self._esiti[k] = (str(r.esito), float(r.copertura))
        return [self._esiti[self._chiave(b, lato, valori)] for b, lato, valori in richieste]

    def degenere(self, blocco, lato: int, valori: dict) -> bool:
        return self.esiti([(blocco, lato, valori)])[0][0] != "OK"


def _combinazioni(blocco) -> list[dict]:
    """Tutte le combinazioni della griglia del passo 1, nell'ordine della griglia."""
    nomi = list(blocco.griglia)
    return [dict(zip(nomi, c)) for c in itertools.product(*(blocco.griglia[n] for n in nomi))]


def togli_degeneri(blocchi, cache, lati, controllo: ControlloDegenerazione | None = None) -> tuple[dict, list]:
    """
    (rimaste, tolte). rimaste[(nome, lato)] = le combinazioni non degeneri, nell'ordine della griglia, per ogni
    trigger e filtro con parametri; tolte = una riga per combinazione tolta (blocco, lato, valori, esito, quota di
    barre vere). Un filtro neutro si misura una volta e vale per i due lati: nell'elenco il lato è «entrambi».
    """
    controllo = controllo or ControlloDegenerazione(cache)
    rimaste, tolte = {}, []
    for b in blocchi:
        if b.tipo == "uscita" or not b.parametri:
            continue
        combinazioni = _combinazioni(b)
        for lato in lati:
            esiti = controllo.esiti([(b, lato, c) for c in combinazioni])
            rimaste[(b.nome, lato)] = tuple(c for c, (e, _) in zip(combinazioni, esiti) if e == "OK")
            if b.neutro and lato != lati[0]:
                continue
            for c, (e, quota) in zip(combinazioni, esiti):
                if e != "OK":
                    tolte.append({"blocco": b.nome, "lato": "entrambi" if b.neutro and len(lati) > 1 else NOME_LATO[lato],
                                  "valori": dict(c), "esito": e, "quota_vere": quota})
    return rimaste, tolte


def disponibile(nome: str, lato: int, rimaste: dict) -> bool:
    """Un blocco è usabile su un lato se non è stato svuotato dai valori degeneri."""
    return bool(rimaste.get((nome, lato), (None,)))


# ------------------------------------------------------------------ le famiglie
def _maschera_centrale(b, cache, lato):
    return b.maschera(cache, lato, b.centrali() if b.parametri else None)


def misura_famiglie(blocchi, cache, lati) -> tuple[dict, pd.DataFrame]:
    """
    ({lato: {blocco: famiglia}}, misura). La famiglia è il nome più piccolo del gruppo: due blocchi stanno insieme se
    famiglie.py li unisce sul df della cache (ai valori centrali) o se hanno la stessa famiglia dichiarata. Solo
    trigger e filtri, per lato; le uscite sono sempre in una famiglia loro.
    """
    righe, finali = [], {}
    for lato in lati:
        genitore = {b.nome: b.nome for b in blocchi}

        def radice(x):
            while genitore[x] != x:
                genitore[x] = genitore[genitore[x]]
                x = genitore[x]
            return x

        def unisci(a, c):
            ra, rc = radice(a), radice(c)
            if ra != rc:
                genitore[max(ra, rc)] = min(ra, rc)

        for tipo, tipo_reg in (("trigger", "entry"), ("filtro", "filtro")):
            gruppo = [b for b in blocchi if b.tipo == tipo]
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
            numero = {r.nome[len("FAB_FAM_"):]: int(r.famiglia) for r in tabella.itertuples()}
            vicina = {r.nome[len("FAB_FAM_"):]: (r.piu_vicina[len("FAB_FAM_"):] if isinstance(r.piu_vicina, str) else None,
                                                 float(r.somiglianza)) for r in tabella.itertuples()}
            for a, c in itertools.combinations(gruppo, 2):
                if numero[a.nome] == numero[c.nome] or a.famiglia == c.famiglia:
                    unisci(a.nome, c.nome)
            for b in gruppo:
                righe.append({"lato": NOME_LATO[lato], "tipo": tipo, "blocco": b.nome, "dichiarata": b.famiglia,
                              "gruppo_misurato": numero[b.nome], "piu_vicina": vicina[b.nome][0],
                              "somiglianza": vicina[b.nome][1]})
        finali[lato] = {b.nome: radice(b.nome) for b in blocchi}
    misura = pd.DataFrame(righe)
    if len(misura):
        misura["famiglia"] = [finali[LATI[r.lato]][r.blocco] for r in misura.itertuples()]
    return finali, misura


# ------------------------------------------------------------------ le teorie
def _per_tipo(blocchi, tipo):
    return [b.nome for b in blocchi if b.tipo == tipo]


def genera_teorie(config: dict, blocchi, famiglie: dict, rimaste: dict) -> list[Teoria]:
    """Tutte le teorie, sempre nello stesso ordine: lato, trigger, filtri, uscita, nell'ordine della config."""
    teorie = {}
    for lato in lati_config(config):
        trigger = [n for n in _per_tipo(blocchi, "trigger") if disponibile(n, lato, rimaste)]
        filtri = [n for n in _per_tipo(blocchi, "filtro") if disponibile(n, lato, rimaste)]
        uscite = _per_tipo(blocchi, "uscita")
        for modello in config["modelli"]:
            minimo, massimo = modello["filtri"]
            for t in trigger:
                for k in range(minimo, massimo + 1):
                    for scelta in itertools.combinations(filtri, k):
                        if len({famiglie[lato][f] for f in scelta}) < len(scelta):
                            continue
                        for u in uscite:
                            teoria = Teoria(lato, t, tuple(scelta), u)
                            teorie.setdefault(teoria.id, teoria)
    return list(teorie.values())


def resoconto_teorie(config: dict, blocchi, famiglie: dict, rimaste: dict, teorie) -> dict:
    """Per il registro: quante teorie per lato e perché (blocchi usciti, coppie di filtri della stessa famiglia)."""
    out = {"teorie": len(teorie), "per_lato": {}, "blocchi_usciti": [], "coppie_stessa_famiglia": []}
    for lato in lati_config(config):
        out["per_lato"][NOME_LATO[lato]] = sum(t.lato == lato for t in teorie)
        for b in blocchi:
            if not disponibile(b.nome, lato, rimaste):
                out["blocchi_usciti"].append({"blocco": b.nome, "lato": NOME_LATO[lato],
                                              "perche": "tutte le combinazioni della griglia sono degeneri"})
        filtri = [n for n in _per_tipo(blocchi, "filtro") if disponibile(n, lato, rimaste)]
        for a, c in itertools.combinations(filtri, 2):
            if famiglie[lato][a] == famiglie[lato][c]:
                out["coppie_stessa_famiglia"].append({"lato": NOME_LATO[lato], "filtri": [a, c],
                                                      "famiglia": famiglie[lato][a]})
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
