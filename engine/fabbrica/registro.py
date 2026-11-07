"""
Il registro della fabbrica (docs/82 P7 e §6, lavoro L3b).

    prove = FileProve(cartella_ricerca)                # prove_<macchina>.csv della ricerca, solo in aggiunta
    prove.aggiungi(righe)                               # una riga per strategia valutata; quelle già scritte si saltano
    aggiungi_prove(cartella_ricerca, righe)             # lo stesso, in una chiamata
    conto_prove(cartella_dati, symbol, timeframe)       # k: tutte le ricerche e tutte le macchine dell'asset
    scrivi_evento(cartella_asset, evento)               # registro_<macchina>.jsonl: solo in aggiunta, a catena
    leggi_registro(cartella_asset)                      # gli eventi di tutte le macchine, catena controllata

- Una prova è una strategia valutata su un pezzo di dati. La chiave è (id_ricerca, pezzo, id_strategia): la stessa
  strategia in due giri dello zoom, in una ripresa o sulla stessa ricerca lanciata su due macchine si conta una volta;
  due ricerche diverse si sommano (P2). Il conto non decide nulla: si legge, con giudizio.soglia_rumore(k) accanto.
- Il registro dell'asset ha una riga JSON per evento. Ogni riga contiene l'impronta (sha256) della riga prima: se la
  catena è rotta, la lettura si ferma con un errore (P8).
- Il nome della macchina è quello del Lab: vetrina.macchina_predefinita, «pc» o «colab».
- Una riga rimasta a metà (il PC si è spento mentre scriveva) nel file delle prove si toglie alla lettura dopo: la
  teoria si rifà e le sue prove si riscrivono, una volta sola.
"""
from __future__ import annotations

import csv
import datetime as _dt
import glob
import hashlib
import json
import os

import pandas as pd

COLONNE_PROVE = ("id_ricerca", "pezzo", "fase", "teoria", "id_strategia", "trade", "ev_bp", "t")
CHIAVE_PROVA = ("id_ricerca", "pezzo", "id_strategia")


def macchina() -> str:
    from engine.vetrina import macchina_predefinita
    return macchina_predefinita()


def nativo(o):
    """Per json.dumps: i numeri di numpy come numeri di Python."""
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(f"{type(o).__name__} non si scrive in JSON")


def json_riga(oggetto) -> str:
    """Una riga JSON compatta; i float si rileggono identici, NaN e infinito compresi."""
    return json.dumps(oggetto, ensure_ascii=False, separators=(",", ":"), default=nativo)


def _testo(x) -> str:
    """Un valore della riga come testo: i float con il repr di Python, così si rileggono identici."""
    if isinstance(x, float):
        return float.__repr__(float(x))
    if hasattr(x, "item"):
        return _testo(x.item())
    return "" if x is None else str(x)


def togli_riga_rotta(percorso: str) -> None:
    """Se il file non finisce con un a capo, l'ultima riga è rimasta a metà: si toglie."""
    if not os.path.exists(percorso):
        return
    with open(percorso, "rb+") as f:
        dati = f.read()
        if not dati or dati.endswith(b"\n"):
            return
        f.truncate(dati.rfind(b"\n") + 1)


# ------------------------------------------------------------------ le prove
class FileProve:
    """Il file delle prove di una ricerca su questa macchina. Ricorda le chiavi già scritte."""

    def __init__(self, cartella_ricerca, nome_macchina: str | None = None):
        self.percorso = os.path.join(str(cartella_ricerca), f"prove_{nome_macchina or macchina()}.csv")
        self.chiavi: set = set()
        togli_riga_rotta(self.percorso)
        if os.path.exists(self.percorso) and os.path.getsize(self.percorso):
            with open(self.percorso, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    self.chiavi.add(tuple(r[c] for c in CHIAVE_PROVA))

    def aggiungi(self, righe) -> int:
        """Scrive le righe nuove, in ordine; ritorna quante. Ogni riga ha le COLONNE_PROVE."""
        nuove = []
        for r in righe:
            mancano = set(COLONNE_PROVE) - set(r)
            if mancano:
                raise ValueError(f"riga di prova senza {sorted(mancano)}")
            k = tuple(_testo(r[c]) for c in CHIAVE_PROVA)
            if k not in self.chiavi:
                self.chiavi.add(k)
                nuove.append(r)
        if not nuove:
            return 0
        os.makedirs(os.path.dirname(self.percorso), exist_ok=True)
        intestazione = not os.path.exists(self.percorso) or os.path.getsize(self.percorso) == 0
        with open(self.percorso, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            if intestazione:
                w.writerow(COLONNE_PROVE)
            for r in nuove:
                w.writerow([_testo(r[c]) for c in COLONNE_PROVE])
        return len(nuove)

    def __len__(self) -> int:
        return len(self.chiavi)


def aggiungi_prove(cartella_ricerca, righe, nome_macchina: str | None = None) -> int:
    return FileProve(cartella_ricerca, nome_macchina).aggiungi(righe)


def file_prove_asset(cartella_dati, symbol: str, timeframe: str) -> list[str]:
    from .config import cartella_asset
    return sorted(glob.glob(os.path.join(cartella_asset(cartella_dati, symbol, timeframe), "*", "prove_*.csv")))


def conto_prove(cartella_dati, symbol: str, timeframe: str) -> int:
    """k: le prove dell'asset, tutte le ricerche e tutte le macchine, ognuna una volta (chiave CHIAVE_PROVA)."""
    chiavi = set()
    for percorso in file_prove_asset(cartella_dati, symbol, timeframe):
        if not os.path.getsize(percorso):
            continue
        df = pd.read_csv(percorso, usecols=list(CHIAVE_PROVA), dtype=str, keep_default_na=False)
        chiavi.update(df.itertuples(index=False, name=None))
    return len(chiavi)


# ------------------------------------------------------------------ il registro dell'asset
def percorso_registro(cartella_asset, nome_macchina: str | None = None) -> str:
    return os.path.join(str(cartella_asset), f"registro_{nome_macchina or macchina()}.jsonl")


def _impronta(riga: str) -> str:
    return hashlib.sha256(riga.encode("utf-8")).hexdigest()


def _righe_verificate(percorso: str) -> list[str]:
    """Le righe del registro, dopo aver controllato numero e catena delle impronte."""
    if not os.path.exists(percorso):
        return []
    with open(percorso, encoding="utf-8") as f:
        testo = f.read()
    if testo and not testo.endswith("\n"):
        raise ValueError(f"{percorso}: l'ultima riga è a metà, il registro non si tocca a mano: la ricerca si ferma.")
    righe = testo.splitlines()
    for i, riga in enumerate(righe):
        try:
            evento = json.loads(riga)
        except json.JSONDecodeError as e:
            raise ValueError(f"{percorso}, riga {i + 1}: non è JSON, il registro è stato modificato.") from e
        attesa = _impronta(righe[i - 1]) if i else ""
        if evento.get("n") != i + 1 or evento.get("prima") != attesa:
            raise ValueError(f"{percorso}, riga {i + 1}: la catena delle impronte è rotta (riga tolta, aggiunta o "
                             "modificata a mano): la ricerca si ferma.")
    return righe


def scrivi_evento(cartella_asset, evento: dict, nome_macchina: str | None = None) -> dict:
    """Aggiunge un evento in fondo al registro di questa macchina, con numero, data e impronta della riga prima."""
    nome = nome_macchina or macchina()
    percorso = percorso_registro(cartella_asset, nome)
    os.makedirs(str(cartella_asset), exist_ok=True)
    righe = _righe_verificate(percorso)
    riga = {"n": len(righe) + 1, "prima": _impronta(righe[-1]) if righe else "", "macchina": nome,
            "quando": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"), **evento}
    with open(percorso, "a", encoding="utf-8") as f:
        f.write(json_riga(riga) + "\n")
    return riga


def leggi_registro(cartella_asset) -> list[dict]:
    """Gli eventi dei registri di tutte le macchine dell'asset, catena controllata, file per file."""
    eventi = []
    for percorso in sorted(glob.glob(os.path.join(str(cartella_asset), "registro_*.jsonl"))):
        eventi.extend(json.loads(r) for r in _righe_verificate(percorso))
    return eventi
