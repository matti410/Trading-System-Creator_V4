"""
Da indicatore a trigger (docs/83 §5).

Un evento scatta quando l'indicatore ATTRAVERSA un livello, verso l'alto (SU) o verso il basso (GIU):

    ZERO      lo 0, solo per gli indicatori con segno
    MEDIA20   la media mobile dell'indicatore stesso, 20 barre (barra compresa)
    P10 ... P90   il 10°, 25°, 50°, 75°, 90° percentile mobile sulle ultime 500 barre, barra ESCLUSA

Attraversare verso l'alto: sopra il livello sulla barra, sotto o uguale sulla barra prima (come helpers._cross_up);
verso il basso al contrario. Scatta solo la prima barra (helpers._evento). Ogni attraversamento da' un trigger long
e uno short, con la stessa serie: quale lato funziona lo decide chi misura.

Un trigger e' un oggetto `TriggerGenerato`, chiamabile come le funzioni di entry_long.py: riceve il df (OHLCV) e
restituisce una Series booleana con lo stesso indice. E' un oggetto (non una funzione annidata) perche' si possa
passare ai processi della fabbrica.

Cache: lo stesso indicatore serve a 24-28 trigger; il valore e i livelli si tengono in memoria per le ultime
`CACHE_RICETTE` ricette e lo stesso df (stessi dati, stesso oggetto). `svuota_cache()` la svuota (la chiama anche
il collaudo del catalogo a ogni taglio).
"""
from __future__ import annotations

import weakref
from collections import OrderedDict

import numpy as np
import pandas as pd

from helpers import _evento

from . import ricette as R

MEDIA_BARRE = 20
PERCENTILI = (10, 25, 50, 75, 90)
PERCENTILI_BARRE = 500
LIVELLI = ("ZERO", "MEDIA20") + tuple(f"P{p}" for p in PERCENTILI)
VERSI = ("SU", "GIU")
CACHE_RICETTE = 2

_CACHE: OrderedDict = OrderedDict()


def svuota_cache() -> None:
    _CACHE.clear()


def _chiave_df(df: pd.DataFrame) -> tuple:
    idx = df.index
    return (id(df), len(idx), idx[0] if len(idx) else None, idx[-1] if len(idx) else None)


def _voce(ricetta: tuple, df: pd.DataFrame) -> dict:
    """La voce di cache della ricetta su questo df: {"x": indicatore, livello: serie del livello}."""
    k = (ricetta, _chiave_df(df))
    v = _CACHE.get(k)
    if v is not None and v["df"]() is df:
        _CACHE.move_to_end(k)
        return v
    v = {"df": weakref.ref(df), "x": R.calcola(ricetta, df)}
    _CACHE[k] = v
    while len(_CACHE) > CACHE_RICETTE:
        _CACHE.popitem(last=False)
    return v


def livello(x: pd.Series, nome: str) -> pd.Series | float:
    """Il livello `nome` dell'indicatore x, barra per barra (ZERO: il numero 0)."""
    if nome == "ZERO":
        return 0.0
    if nome == "MEDIA20":
        return x.rolling(MEDIA_BARRE, min_periods=MEDIA_BARRE).mean()
    if nome.startswith("P") and int(nome[1:]) in PERCENTILI:
        q = int(nome[1:]) / 100.0
        return x.rolling(PERCENTILI_BARRE, min_periods=PERCENTILI_BARRE).quantile(q).shift(1)
    raise ValueError(f"livello sconosciuto: {nome!r}")


def attraversa(x: pd.Series, liv, verso: str) -> pd.Series:
    """Evento: x attraversa il livello verso l'alto (SU) o verso il basso (GIU). Solo la prima barra."""
    lv = liv if isinstance(liv, pd.Series) else pd.Series(liv, index=x.index)
    if verso == "SU":
        m = (x > lv) & (x.shift(1) <= lv.shift(1))
    elif verso == "GIU":
        m = (x < lv) & (x.shift(1) >= lv.shift(1))
    else:
        raise ValueError(f"verso sconosciuto: {verso!r}")
    return _evento(m)


def evento(ricetta: tuple, nome_livello: str, verso: str, df: pd.DataFrame) -> pd.Series:
    """La serie booleana dell'attraversamento, con la cache dell'indicatore e del livello."""
    v = _voce(ricetta, df)
    if nome_livello not in v:
        v[nome_livello] = livello(v["x"], nome_livello)
    return attraversa(v["x"], v[nome_livello], verso)


class TriggerGenerato:
    """
    Un trigger generato: chiamabile come le funzioni di entry_long.py (df -> Series booleana).

    nome      es. «G0003_P25_SU» (long) o «G0003_SHORT_P25_SU» (short)
    ricetta   l'albero della ricetta (engine.generatore.ricette)
    livello   ZERO, MEDIA20, P10, P25, P50, P75, P90
    verso     SU o GIU
    lato      1 = long, -1 = short
    famiglia  la famiglia dichiarata (ricette.famiglia)
    """

    def __init__(self, nome: str, ricetta: tuple, livello: str, verso: str, lato: int, famiglia: str):
        if livello not in LIVELLI or verso not in VERSI or lato not in (1, -1):
            raise ValueError(f"trigger {nome}: livello {livello!r}, verso {verso!r}, lato {lato!r} non validi")
        self.nome, self.ricetta, self.livello, self.verso, self.lato, self.famiglia = (
            nome, ricetta, livello, verso, lato, famiglia)
        self.__name__ = nome
        self.__doc__ = (f"{R.testo(ricetta)}: attraversa {livello} verso {'l alto' if verso == 'SU' else 'il basso'}"
                        f" -> {'long' if lato == 1 else 'short'}")

    def __call__(self, df: pd.DataFrame) -> pd.Series:
        return evento(self.ricetta, self.livello, self.verso, df)

    def __repr__(self) -> str:
        return f"TriggerGenerato({self.nome}: {self.__doc__})"

    def __reduce__(self):
        return (TriggerGenerato, (self.nome, self.ricetta, self.livello, self.verso, self.lato, self.famiglia))


def nome_trigger(id_ricetta: str, livello: str, verso: str, lato: int) -> str:
    return f"{id_ricetta}_{livello}_{verso}" if lato == 1 else f"{id_ricetta}_SHORT_{livello}_{verso}"


def livelli_ricetta(con_segno: bool) -> tuple[str, ...]:
    """I livelli di una ricetta: lo zero solo se l'indicatore ha segno."""
    return LIVELLI if con_segno else LIVELLI[1:]


def ha_segno(x: pd.Series) -> bool:
    """L'indicatore va da negativo a positivo (sul dataset sintetico)."""
    v = x.to_numpy(dtype=float)
    v = v[np.isfinite(v)]
    return bool(len(v) and v.min() < 0 < v.max())
