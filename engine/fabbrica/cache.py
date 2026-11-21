"""
La cache della fabbrica (docs/82 P-L2, lavoro L2): indicatori, maschere e soglie già calcolati su un DataFrame.

    cache = Cache(df, limite_mb=500)
    cache.indicatore("rsi", barre=24)
    cache.soglie_uscita(ore=4, perc_sl=90, perc_tp=None)
    comune = MemoriaComune(limite_mb=1500)            # docs/82 §14.7: una cache sola per la lista, col tetto di oggi
    caches = {m: Cache(df_m, 1500, comune) for m, df_m in ...}

Il limite di memoria si rispetta sempre: quando si supera, si buttano i valori usati meno di recente e, se servono di
nuovo, si ricalcolano. Il risultato non cambia. Gli array restituiti sono in sola lettura: una modifica per sbaglio
sporcherebbe tutte le strategie dopo.

La durata di una barra si legge dall'indice del df, quindi qui non c'è nessuna costante da M15. Le ore diventano barre
arrotondando alla barra più vicina, da M1 a D1: anche la finestra delle soglie (125 ore: 31 barre su H4, 5 su D1).
"""
from __future__ import annotations

import math
from collections import OrderedDict
from typing import Callable

import numpy as np
import pandas as pd
import talib as ta

from engine.exit_search_bt import soglie_adattive
from engine.indicatori import atr_relativo, donchian_massimo, donchian_minimo
from engine.quarantena import passo_barre

ORE_FINESTRA_SOGLIE = 125      # la finestra di soglie_adattive: le 500 barre su M15
LAG_SOGLIE = 1                 # lo stop del motore veloce vale dall'Open della barra d'ingresso: serve lag >= 1


def barre_da_ore(ore: float, minuti_barra: float, minimo: int = 1) -> int:
    """
    Le barre di `ore` ore: la barra più vicina (a metà strada verso l'alto, così il risultato non dipende dal pari o
    dispari), mai sotto `minimo`. Ore zero o negative non sono una durata: si ferma con un errore.
    """
    if not ore > 0:
        raise ValueError(f"{ore} ore non sono una durata: servono più di zero ore.")
    return max(int(minimo), math.floor(float(ore) * 60.0 / float(minuti_barra) + 0.5 + 1e-9))


def _rsi(df: pd.DataFrame, barre: int) -> np.ndarray:
    return ta.RSI(df["Close"].to_numpy(dtype=float), timeperiod=int(barre))


def _adx(df: pd.DataFrame, barre: int) -> np.ndarray:
    return ta.ADX(*(df[c].to_numpy(dtype=float) for c in ("High", "Low", "Close")), timeperiod=int(barre))


def _atr(df: pd.DataFrame, barre: int) -> np.ndarray:
    return ta.ATR(*(df[c].to_numpy(dtype=float) for c in ("High", "Low", "Close")), timeperiod=int(barre))


INDICATORI = {
    "rsi": _rsi,
    "adx": _adx,
    "atr": _atr,
    "atr_relativo": lambda df, breve, lungo: atr_relativo(df, int(breve), int(lungo)),
    "donchian_massimo": lambda df, barre: donchian_massimo(df, int(barre)),
    "donchian_minimo": lambda df, barre: donchian_minimo(df, int(barre)),
}


class MemoriaComune:
    """
    (20/11, docs/82 §14.7) La memoria di più cache insieme, con un tetto solo: le cache delle monete di una lista. Quando
    si supera il tetto si buttano i valori usati meno di recente, di qualunque moneta.
    """

    def __init__(self, limite_mb: float):
        if limite_mb < 0:
            raise ValueError("limite_mb non può essere negativo")
        self.limite_byte = int(limite_mb * 1024 * 1024)
        self.valori: OrderedDict = OrderedDict()
        self.byte = 0
        self._prossima = 0

    def nuova_cache(self) -> int:
        self._prossima += 1
        return self._prossima


class Cache:
    """
    Vedi la testa del file. `calcoli` conta i calcoli veri, `presi` quelli evitati. `comune` (20/11, docs/82 §14.7):
    la MemoriaComune della lista; senza, la cache ha la sua, con il tetto `limite_mb`.
    """

    def __init__(self, df: pd.DataFrame, limite_mb: float, comune: MemoriaComune | None = None):
        if limite_mb < 0:
            raise ValueError("limite_mb non può essere negativo")
        self.df = df
        self._m = comune if comune is not None else MemoriaComune(limite_mb)
        self._id = self._m.nuova_cache()
        self.minuti_barra = passo_barre(pd.DatetimeIndex(df.index)) / pd.Timedelta(minutes=1)
        self.calcoli = 0
        self.presi = 0

    @property
    def limite_byte(self) -> int:
        return self._m.limite_byte

    @property
    def memoria_byte(self) -> int:
        """I byte tenuti da questa cache."""
        return sum(a.nbytes for (i, _), a in self._m.valori.items() if i == self._id)

    @property
    def _valori(self) -> dict:
        """I valori tenuti da questa cache, per chiave (per i collaudi)."""
        return {k: a for (i, k), a in self._m.valori.items() if i == self._id}

    def barre(self, ore: float) -> int:
        return barre_da_ore(ore, self.minuti_barra)

    def ore(self, barre: int) -> float:
        """Le ore effettive di `barre` barre."""
        return int(barre) * self.minuti_barra / 60.0

    def _metti(self, chiave: tuple, valore) -> np.ndarray:
        a = np.array(valore)
        a.flags.writeable = False
        m = self._m
        if a.nbytes <= m.limite_byte:
            m.valori[(self._id, chiave)] = a
            m.byte += a.nbytes
            while m.byte > m.limite_byte:
                _, vecchio = m.valori.popitem(last=False)
                m.byte -= vecchio.nbytes
        return a

    def _guarda(self, chiave: tuple) -> np.ndarray | None:
        k = (self._id, chiave)
        a = self._m.valori.get(k)
        if a is not None:
            self._m.valori.move_to_end(k)
            self.presi += 1
        return a

    def prendi(self, chiave: tuple, calcola: Callable[[], np.ndarray]) -> np.ndarray:
        """Il valore di `chiave`: dalla cache se c'è, altrimenti lo calcola e lo tiene se ci sta."""
        a = self._guarda(chiave)
        if a is not None:
            return a
        self.calcoli += 1
        return self._metti(chiave, calcola())

    def indicatore(self, nome: str, **valori) -> np.ndarray:
        """Un indicatore di INDICATORI, con i suoi periodi in barre."""
        if nome not in INDICATORI:
            raise ValueError(f"indicatore {nome!r} sconosciuto: {sorted(INDICATORI)}")
        chiave = ("indicatore", nome, tuple(sorted(valori.items())))
        return self.prendi(chiave, lambda: INDICATORI[nome](self.df, **valori))

    def _coppia(self, tipo: str, barre: int, perc, lag: int) -> dict:
        """Una soglia per i due lati. `tipo` è "sl" o "tp"; percentile None o 0 = spenta (NaN)."""
        if perc in (None, 0):
            spenta = self._guarda(("soglia_spenta",))
            if spenta is None:
                spenta = self._metti(("soglia_spenta",), np.full(len(self.df), np.nan))
            return {"long": spenta, "short": spenta}
        chiavi = {lato: ("soglia", tipo, barre, float(perc), lag, lato) for lato in ("long", "short")}
        valori = {lato: self._guarda(chiave) for lato, chiave in chiavi.items()}
        if all(v is not None for v in valori.values()):
            return valori
        self.calcoli += 1
        s = soglie_adattive(self.df, barre, finestra=self.barre(ORE_FINESTRA_SOGLIE), perc_sl=perc if tipo == "sl" else 0,
                            perc_tp=perc if tipo == "tp" else 0, lag=lag)
        return {lato: self._metti(chiavi[lato], s[f"{tipo}_{lato}"].to_numpy(dtype=float)) for lato in chiavi}

    def soglie_uscita(self, ore: float, perc_sl, perc_tp, lag: int = LAG_SOGLIE) -> dict:
        """
        Le soglie di exit_search_bt.soglie_adattive, finestra di ORE_FINESTRA_SOGLIE ore: un dizionario con sl_long,
        tp_long, sl_short, tp_short (array, frazioni del prezzo). Stop e target si tengono separati: una combinazione
        nuova ricalcola solo la parte che manca. Con lag < 1 si ferma.
        """
        if int(lag) < 1:
            raise ValueError(f"lag={lag}: stop e target valgono dall'Open della barra d'ingresso, serve lag >= 1.")
        barre = self.barre(ore)
        sl, tp = self._coppia("sl", barre, perc_sl, int(lag)), self._coppia("tp", barre, perc_tp, int(lag))
        return {"sl_long": sl["long"], "tp_long": tp["long"], "sl_short": sl["short"], "tp_short": tp["short"]}
