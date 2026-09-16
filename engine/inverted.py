"""
Inverted — gestire i candidati con segnale invertito senza guardarli al contrario.

Modulo AGGIUNTIVO: non modifica niente, usa solo l'API del registry.


IL PROBLEMA
-----------
Un candidato con `t_stat` negativo non e' un candidato fallito: e' un segnale
che funziona nella direzione OPPOSTA a quella con cui e' stato registrato.
`diagnose_bias` lo etichetta gia' cosi' ("SEGNALE INVERTITO"),
`select_survivors` ordina per |t_stat| e quindi lo tiene, e il gate di
`viability` calcola la sua `direzione_effettiva`.

Ma quando lo si ISPEZIONA, il motore lo esegue come e' registrato — cioe' dal
lato sbagliato. Il risultato e' che curva di equity, PnL, Sharpe e drawdown
sono quelli della versione che non tradereresti mai, e sono capovolti rispetto
a quelli veri. Nessun avviso, nessun errore: solo un grafico che scende dove
dovrebbe salire.

Questo modulo chiude quel buco in due modi, entrambi necessari:

  `direzione_effettiva`  la direzione con cui il candidato va tradato davvero
  `mirror_entry`         registra il gemello speculare, cosi' l'ispezione gira
                         sul lato giusto e i numeri sono quelli veri


PERCHE' UN GEMELLO E NON UN SEGNO CAMBIATO A VALLE
---------------------------------------------------
Ribaltare il PnL moltiplicando per -1 e' sbagliato, e non di poco. I
rendimenti si COMPONGONO: una serie di perdite e la stessa serie di guadagni
non producono curve speculari, e il drawdown men che meno. Su un caso di
prova costruito apposta, lo stesso segnale dava PnL -0.22 dal lato sbagliato
e +0.28 da quello giusto, con drawdown -0.220 contro -0.0016: due ordini di
grandezza. A questo si aggiungono i costi, che si pagano su entrambi i lati
e quindi rompono anche la simmetria di MAE e MFE.

L'unico modo corretto e' rieseguire il backtest dal lato giusto, ed e' quello
che fa `mirror_entry`.


NOTA SUL CONTEGGIO DELLE PROVE
-------------------------------
Ammettere l'inversione RADDOPPIA lo spazio delle ipotesi: ogni entry ha due
occasioni di sembrare buona invece di una. Il numero effettivo di prove
raddoppia e la soglia di `multiple_testing_note` va letta di conseguenza. Non
e' un motivo per non invertire — e' un motivo per alzare l'asticella quando lo
si fa.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .registry import get_entry, get_entry_direction, register_entry, list_entries

SUFFISSO = "__INV"


# ========================================================================
# Leggere la direzione vera
# ========================================================================

def direzione_effettiva(riga, metric: str = "t_stat") -> int:
    """
    Da che lato va tradato davvero un candidato: `direction` dichiarata
    moltiplicata per il segno della metrica. 1 = long, -1 = short.

    Accetta una riga di risultati (Series) o un DataFrame.
    """
    if isinstance(riga, pd.DataFrame):
        segno = np.sign(riga[metric].fillna(0.0)).mask(lambda s: s == 0, 1.0)
        return (riga["direction"] * segno).where(riga[metric].notna()).round().astype("Int64")
    segno = 1 if (pd.isna(riga[metric]) or riga[metric] >= 0) else -1
    return int(riga["direction"]) * segno


def etichetta_direzione(riga, metric: str = "t_stat") -> str:
    """Riga di testo pronta da stampare, che NON nasconde l'inversione."""
    dichiarata = int(riga["direction"])
    effettiva = direzione_effettiva(riga, metric=metric)
    nome = lambda d: "LONG" if d == 1 else "SHORT"
    if effettiva == dichiarata:
        return nome(dichiarata)
    return (f"{nome(effettiva)}  ← SEGNALE INVERTITO "
            f"(l'entry e' registrata {nome(dichiarata)}, ma {metric} e' negativo: "
            f"va tradata dal lato opposto)")


# ========================================================================
# Eseguire dal lato giusto
# ========================================================================

def mirror_entry(entry: str, suffisso: str = SUFFISSO) -> str:
    """
    Registra (una sola volta) il gemello speculare di un'entry: STESSO
    segnale, direzione opposta. Restituisce il nome del gemello.

    Serve a ispezionare e validare un candidato invertito dal lato con cui lo
    tradereresti davvero. Non ribalta i numeri a posteriori: rifa' il backtest,
    che e' l'unica cosa corretta, perche' costi, MAE e MFE non sono simmetrici
    fra long e short.
    """
    nome = f"{entry}{suffisso}"
    if nome in list_entries():
        return nome
    fn = get_entry(entry)
    register_entry(nome, direction=-get_entry_direction(entry))(
        lambda d, _f=fn: _f(d))
    return nome


def mirror_if_inverted(riga, metric: str = "t_stat") -> tuple[str, bool]:
    """
    Restituisce `(nome_entry_da_usare, e_invertito)`.

    Se il candidato non e' invertito restituisce l'entry originale e False,
    quindi si puo' chiamare sempre senza casi particolari.
    """
    if direzione_effettiva(riga, metric=metric) == int(riga["direction"]):
        return str(riga["entry"]), False
    return mirror_entry(str(riga["entry"])), True


def annota_direzione(results: pd.DataFrame, metric: str = "t_stat") -> pd.DataFrame:
    """
    Aggiunge `direzione_effettiva` e `invertito` a una tabella di risultati.
    Da usare sulla tabella di validazione, dove il segno del `t_stat` decide
    da che lato si opera e non deve restare implicito.
    """
    g = results.copy()
    g["direzione_effettiva"] = direzione_effettiva(g, metric=metric)
    g["invertito"] = g["direzione_effettiva"] != g["direction"]
    return g
