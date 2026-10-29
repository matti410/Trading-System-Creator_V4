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
25/10/2026 (docs/70 §3-§4): il salvataggio e' in engine/studio.py, in giornali
solo in aggiunta; qui `da_voci` ricostruisce la storia da quelle voci e
`metti` la rimette nel registro. `normale` e `a_tupla` portano le chiavi
composte (tuple) dentro e fuori dal JSON.

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
    if s.h_corrente is None:
        # 25/10/2026 (docs/70): una storia ricostruita da giornali senza nessun H (studio appena aperto,
        # o solo voci d'altro tipo): il primo H e' «nuovo», come sopra; il conto ricostruito resta
        s.h_provati, s.h_corrente = [H], H
        if s.prove is None and nuove_prove is not None:
            s.prove = nuove_prove()
        return s, "nuovo"
    if H == s.h_corrente:
        return s, "stesso_h"
    esito = "h_gia_provato" if H in s.h_provati else "h_nuovo"
    if esito == "h_nuovo":
        s.h_provati.append(H)
    s.risalite.append({"cosa": "H", "da": s.h_corrente, "a": H, "oos_visto": s.oos_visto})
    s.h_corrente = H
    return s, esito


def annota_oos(s: StoriaDataset, scelte: dict, oos_fino_al=None) -> int:
    """
    Scrive nel diario un'apertura dell'out-of-sample con le scelte di quel momento; ritorna quante sono.
    oos_fino_al (25/10/2026, docs/70 §3.2): l'ultima barra out-of-sample di quel momento, per il reset;
    None = non scritto (come prima).
    """
    voce = {"quando": pd.Timestamp.now(tz="UTC").isoformat(), **dict(scelte)}
    if oos_fino_al is not None:
        voce["oos_fino_al"] = pd.Timestamp(oos_fino_al).isoformat()
    s.diario.append(voce)
    return len(s.diario)


def annota_risalita(s: StoriaDataset, cosa: str, **dettagli) -> None:
    """Una scelta rifatta a monte (trigger, cella, uscite, sistema, ...), con o senza out-of-sample visto."""
    s.risalite.append({"cosa": str(cosa), "oos_visto": s.oos_visto, **dettagli})


def azzera() -> None:
    """Svuota il registro (per i test; nel notebook equivale a riavviare il kernel)."""
    _REGISTRO.clear()


# ========================================================================
# 25/10/2026 (docs/70 §3.2): la storia ricostruita dalle voci dei giornali
# ========================================================================

def normale(x):
    """Un valore come esce da JSON: tuple -> liste, numeri e date numpy/pandas -> Python/testo."""
    import numpy as np
    if isinstance(x, dict):
        return {str(k): normale(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [normale(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return float(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, pd.Timestamp):
        return x.isoformat()
    return x


def a_tupla(x):
    """L'inverso di `normale` per le chiavi del conto: liste -> tuple, a ogni livello."""
    if isinstance(x, list):
        return tuple(a_tupla(v) for v in x)
    return x


def _prove_vuote() -> dict:
    return {"trigger": 0, "uscite": {}, "filtri": {}, "combinazioni": {}}


def celle_gia_contate(voci: dict, chiave) -> tuple | None:
    """
    29/10/2026 (docs/77, lavoro 1, decisione D2 di Mattia): la voce delle situazioni gia' contata che
    CONTIENE `chiave`, o None. Una chiave delle situazioni e' (H, assi, trigger): un atlante con lo stesso
    H, gli stessi trigger nello stesso ordine e assi contenuti in quelli di una voce gia' contata misura
    celle gia' misurate (gli assi non si incrociano: ogni cella si misura da sola). Serve all'atlante senza
    la basis, tolta il 29/10/2026, sui dataset dove le situazioni erano gia' contate con la basis.
    """
    if not (isinstance(chiave, tuple) and len(chiave) == 3):
        return None
    H, assi, nomi = chiave
    for k in voci or {}:
        if (isinstance(k, tuple) and len(k) == 3 and k != chiave and k[0] == H and tuple(k[2]) == tuple(nomi)
                and set(assi) < set(k[1])):
            return k
    return None


def metti_prova(prove: dict, dove: str, chiave, n) -> bool:
    """
    Mette una voce nel conto delle prove (28/10/2026, docs/76, D1): per ogni
    chiave vale il numero piu' alto mai scritto, cosi' il conto non scende mai
    (anche quando Lab e ricerca scrivono la stessa chiave con numeri diversi).
    chiave None = voce semplice (trigger, fasce); altrimenti una voce a dizionario.
    29/10/2026 (docs/77, D2): una voce delle situazioni contenuta in una voce gia'
    contata (celle_gia_contate) non entra: ritorna False. Altrimenti True.
    """
    if chiave is None:
        prima = prove.get(dove)
        prove[dove] = n if prima is None else max(prima, n)
    else:
        voci = prove.setdefault(dove, {})
        if dove == "celle" and celle_gia_contate(voci, chiave) is not None:
            return False
        prima = voci.get(chiave)
        voci[chiave] = n if prima is None else max(prima, n)
    return True


def da_voci(chiave: tuple, voci: list, nuove_prove=None) -> StoriaDataset:
    """
    Ricostruisce la storia di un dataset dalle voci dei giornali, gia' in
    ordine di tempo (docs/70 §3.2, §4.3). Le voci:
      {"voce": "orizzonte", "H": 41}                    un H usato: come `apri`
      {"voce": "prova", "dove": "uscite", "chiave": [...] | None, "n": 87}
                                                        una voce del conto; None = voce
                                                        semplice (trigger, fasce)
      {"voce": "oos", "voce_diario": {...}}             un'apertura dell'out-of-sample
      {"voce": "risalita", "risalita": {...}}           una scelta rifatta (non di H)
    Per ogni chiave del conto vale il numero piu' alto (dal 28/10/2026, docs/76;
    prima la voce piu' recente). Le risalite di H nascono
    dalle voci «orizzonte», come in `apri`.
    """
    s = StoriaDataset(chiave=chiave, prove=nuove_prove() if nuove_prove is not None else _prove_vuote())
    for v in voci:
        tipo = v.get("voce")
        if tipo == "orizzonte":
            H = int(v["H"])
            if s.h_corrente is None:
                s.h_provati, s.h_corrente = [H], H
            elif H != s.h_corrente:
                if H not in s.h_provati:
                    s.h_provati.append(H)
                s.risalite.append({"cosa": "H", "da": s.h_corrente, "a": H, "oos_visto": s.oos_visto})
                s.h_corrente = H
        elif tipo == "prova":
            # 28/10/2026 (docs/76, D1): il numero piu' alto mai scritto, non il piu' recente
            metti_prova(s.prove, v["dove"], None if v.get("chiave") is None else a_tupla(v["chiave"]), v["n"])
        elif tipo == "oos":
            s.diario.append(dict(v["voce_diario"]))
        elif tipo == "risalita":
            s.risalite.append(dict(v["risalita"]))
        else:
            raise ValueError(f"Voce del giornale sconosciuta: {tipo!r}")
    return s


def metti(s: StoriaDataset) -> None:
    """Rimette nel registro una storia ricostruita (sostituisce quella che c'era con la stessa chiave)."""
    _REGISTRO[s.chiave] = s
