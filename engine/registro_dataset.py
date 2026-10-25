"""
Il registro per dataset (25/10/2026, docs/68 §9.1, correzione A di Mattia).

A COSA SERVE
------------
Con le uscite consigliate a H barre (docs/68 §5.1), l'orizzonte H e' la
scelta che pesa di piu' su tutta la catena. Rieseguire la schermata 1 con un
altro H creava una sessione nuova: conto delle prove e diario
dell'out-of-sample ripartivano da zero. Era una risalita silenziosa: si prova
un H, si guarda, se ne prova un altro, e il conto non lo sa.

Il registro tiene, per DATASET, quello che deve sopravvivere a un cambio di
H: gli H provati, il conto delle prove, il diario dell'out-of-sample e le
risalite. Il dataset e':

    symbol, timeframe, confine dell'in-sample (la data dell'ultima barra
    in-sample)

Un CSV aggiornato con barre nuove sposta il confine: e' un dataset diverso e
riparte da zero (si scrive). Tornare a un dataset gia' visto nella stessa
sessione del notebook ritrova la sua storia.

    apri(symbol, timeframe, confine, H)   -> (storia, esito)
        esito "nuovo"          primo H su questo dataset
              "stesso_h"       lo stesso H di prima: nessuna prova, nessuna segnalazione
              "h_nuovo"        un H mai provato qui: risalita, la scelta fra gli H si conta
              "h_gia_provato"  si torna a un H gia' provato: risalita segnalata, nessuna
                               prova in piu' (la scelta fra quegli H e' gia' contata)

LIMITE: il registro vive finche' resta aperto il notebook (il kernel di
Python). Riavviarlo lo azzera; salvarlo in un file e' il passo del lavoro 2,
quando il confine dell'in-sample diventera' una data salvata con lo studio.

Modulo ADDITIVO: non modifica nessun file esistente dell'engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .giudizio import prove_trigger_orizzonti


@dataclass
class StoriaDataset:
    """Quello che sopravvive a un cambio di H sullo stesso dataset."""
    chiave: tuple
    h_provati: list = field(default_factory=list)      # in ordine di prova, senza doppioni
    h_corrente: int | None = None
    prove: dict | None = None                          # il conto della catena (Sessione.prove)
    diario: list = field(default_factory=list)         # ogni apertura dell'out-of-sample
    risalite: list = field(default_factory=list)       # ogni scelta rifatta dopo aver visto

    @property
    def oos_visto(self) -> bool:
        return bool(self.diario)

    def voce_trigger(self, k: int, alpha: float = 0.05) -> float:
        """La voce dei trigger nella soglia cumulata: k con un H solo, l'equivalente con piu' H."""
        return prove_trigger_orizzonti(k, self.h_provati, alpha)


_REGISTRO: dict[tuple, StoriaDataset] = {}


def chiave_dataset(symbol: str, timeframe: str, confine) -> tuple:
    """La chiave del dataset: symbol, timeframe e confine dell'in-sample (data, al minuto)."""
    t = pd.Timestamp(confine)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return (str(symbol).upper(), str(timeframe).upper(), t.tz_convert("UTC").isoformat())


def storia(symbol: str, timeframe: str, confine) -> StoriaDataset | None:
    """La storia del dataset, se c'e'."""
    return _REGISTRO.get(chiave_dataset(symbol, timeframe, confine))


def apri(symbol: str, timeframe: str, confine, H: int, nuove_prove=None) -> tuple[StoriaDataset, str]:
    """
    Apre (o riprende) la storia del dataset con l'orizzonte H. `nuove_prove`:
    una funzione senza argomenti che crea il conto vuoto, chiamata solo per un
    dataset nuovo (None = nessun conto, lo mette chi chiama). Ritorna la storia
    e l'esito (vedi il docstring del modulo).
    """
    H = int(H)
    if H < 1:
        raise ValueError("H deve essere almeno 1 barra.")
    chiave = chiave_dataset(symbol, timeframe, confine)
    s = _REGISTRO.get(chiave)
    if s is None:
        s = StoriaDataset(chiave=chiave, h_provati=[H], h_corrente=H,
                          prove=nuove_prove() if nuove_prove is not None else None)
        _REGISTRO[chiave] = s
        return s, "nuovo"
    if H == s.h_corrente:
        return s, "stesso_h"
    esito = "h_gia_provato" if H in s.h_provati else "h_nuovo"
    if esito == "h_nuovo":
        s.h_provati.append(H)
    s.risalite.append({"cosa": "H", "da": s.h_corrente, "a": H, "oos_visto": s.oos_visto})
    s.h_corrente = H
    return s, esito


def annota_oos(s: StoriaDataset, scelte: dict) -> int:
    """Scrive nel diario un'apertura dell'out-of-sample con le scelte di quel momento; ritorna quante sono."""
    s.diario.append({"quando": pd.Timestamp.now(tz="UTC").isoformat(), **dict(scelte)})
    return len(s.diario)


def annota_risalita(s: StoriaDataset, cosa: str, **dettagli) -> None:
    """Una scelta rifatta a monte (trigger, cella, uscite, sistema, ...), con o senza out-of-sample visto."""
    s.risalite.append({"cosa": str(cosa), "oos_visto": s.oos_visto, **dettagli})


def azzera() -> None:
    """Svuota il registro (per i test; nel notebook equivale a riavviare il kernel)."""
    _REGISTRO.clear()
