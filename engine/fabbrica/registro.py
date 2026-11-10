"""
Il registro della fabbrica (docs/82 P7 e §6, lavoro L3b).

    prove = FileProve(cartella_ricerca)                # prove_<macchina>.csv della ricerca, solo in aggiunta
    prove.aggiungi(righe)                               # una riga per strategia valutata; quelle già scritte si saltano
    aggiungi_prove(cartella_ricerca, righe)             # lo stesso, in una chiamata
    conto_prove(cartella_dati, symbol, timeframe)       # k: tutte le ricerche e tutte le macchine dell'asset
    scrivi_evento(cartella_asset, evento)               # registro_<macchina>.jsonl: solo in aggiunta
    leggi_registro(cartella_asset)                      # gli eventi di tutte le macchine

- Una prova è una strategia valutata su un pezzo di dati. La chiave è (id_ricerca, pezzo, id_strategia): la stessa
  strategia in due giri dello zoom, in una ripresa o sulla stessa ricerca lanciata su due macchine si conta una volta;
  due ricerche diverse si sommano (P2). Il conto non decide nulla: si legge, con giudizio.soglia_rumore(k) accanto.
- Il registro dell'asset ha una riga JSON per evento: un file di annotazioni, solo in aggiunta (10/11, scelta B). Non
  ferma niente: una riga cambiata o tolta si legge com'è, una riga che non è JSON (a metà, rovinata) si salta. Niente
  più impronta della riga prima; i registri scritti prima, con il campo «prima», si leggono come gli altri. Il numero
  «n» di una riga è il più alto del file + 1: lega l'esito della cassaforte al suo ingresso.
- Il nome della macchina è quello del Lab: vetrina.macchina_predefinita, «pc» o «colab»; dal notebook (L5a) quello
  scritto nell'Avvio, con imposta_macchina (un secondo PC: «pc2»), così due PC con Drive non scrivono lo stesso file.
- Una riga rimasta a metà (il PC si è spento mentre scriveva) nel file delle prove si toglie alla lettura dopo: la
  teoria si rifà e le sue prove si riscrivono, una volta sola.
"""
from __future__ import annotations

import csv
import datetime as _dt
import glob
import json
import os

import pandas as pd

COLONNE_PROVE = ("id_ricerca", "pezzo", "fase", "teoria", "id_strategia", "trade", "ev_bp", "t")
CHIAVE_PROVA = ("id_ricerca", "pezzo", "id_strategia")


_MACCHINA: str | None = None          # il nome scelto nell'Avvio del notebook (L5a); None = quello predefinito


def imposta_macchina(nome: str | None) -> str:
    """
    Il nome di questa macchina nei file della fabbrica (L5a, 08/11), come il campo dell'Avvio del Lab: «pc», «pc2»...
    Su Colab è sempre «colab». Vuoto o None = quello predefinito. Solo lettere minuscole, cifre, «_» e «-».
    """
    global _MACCHINA
    from engine.vetrina import macchina_predefinita
    nome = (nome or "").strip().lower()
    if macchina_predefinita() == "colab" or not nome:
        _MACCHINA = None
        return macchina()
    if not all(c.isascii() and (c.isalnum() or c in "_-") for c in nome):
        raise ValueError(f"nome della macchina {nome!r}: usa solo lettere, cifre, «_» e «-» (per esempio pc2).")
    _MACCHINA = nome
    return nome


def macchina() -> str:
    from engine.vetrina import macchina_predefinita
    return _MACCHINA or macchina_predefinita()


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


def _eventi_file(percorso: str) -> list[dict]:
    """Gli eventi di un registro, nell'ordine; le righe che non si leggono come JSON si saltano (10/11)."""
    if not os.path.exists(percorso):
        return []
    eventi = []
    with open(percorso, encoding="utf-8") as f:
        for riga in f:
            try:
                evento = json.loads(riga)
            except json.JSONDecodeError:
                continue
            if isinstance(evento, dict):
                eventi.append(evento)
    return eventi


def adesso() -> str:
    """L'istante di un evento, in UTC. Una funzione a parte: i collaudi «registro identico al bit» la fissano."""
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def scrivi_evento(cartella_asset, evento: dict, nome_macchina: str | None = None) -> dict:
    """Aggiunge un evento in fondo al registro di questa macchina, con numero e data (10/11: senza impronta)."""
    nome = nome_macchina or macchina()
    percorso = percorso_registro(cartella_asset, nome)
    os.makedirs(str(cartella_asset), exist_ok=True)
    numeri = [e["n"] for e in _eventi_file(percorso) if isinstance(e.get("n"), int) and not isinstance(e["n"], bool)]
    riga = {"n": max(numeri, default=0) + 1, "macchina": nome, "quando": adesso(), **evento}
    a_capo = ""
    if os.path.exists(percorso) and os.path.getsize(percorso):
        with open(percorso, "rb") as f:
            f.seek(-1, os.SEEK_END)
            a_capo = "" if f.read(1) == b"\n" else "\n"      # dopo una riga rimasta a metà, si va a capo
    with open(percorso, "a", encoding="utf-8") as f:
        f.write(a_capo + json_riga(riga) + "\n")
    return riga


def leggi_registro(cartella_asset) -> list[dict]:
    """Gli eventi dei registri di tutte le macchine dell'asset, file per file. Non si ferma mai (10/11)."""
    eventi = []
    for percorso in sorted(glob.glob(os.path.join(str(cartella_asset), "registro_*.jsonl"))):
        eventi.extend(_eventi_file(percorso))
    return eventi
