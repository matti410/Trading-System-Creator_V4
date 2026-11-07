"""
I dati della fabbrica in tre pezzi (docs/82 P1, lavoro L3a).

    confini = Confini.da_config(config["confini"])
    pezzi = carica_pezzi("BINANCE_PERP_BTCUSDT", "M15", confini, "dati")
    pezzi.ricerca, pezzi.selezione        # OHLCV con indice UTC, già tagliati
    pezzi.funding["ricerca"]              # il funding del pezzo (None sullo spot)
    pezzi.costi("ricerca")                # i costi calcolati sul pezzo tagliato
    pezzi.apri_cassaforte(permesso)       # solo con il permesso che crea cassaforte.py (L4)

- I confini sono una data di inizio e tre durate in ore (docs/82 §6): ricerca, selezione e cassaforte sono intervalli
  di tempo chiusi a sinistra e aperti a destra, gli stessi su ogni timeframe. Una barra sta nel pezzo in cui cade il
  suo inizio. Le barre prima dell'inizio e dopo la fine della cassaforte restano fuori.
- Si legge con exchange.leggi_csv e gli stessi controlli di vetrina.carica_storico, che però accetta solo da M5 a H4:
  la fabbrica va da M1 a D1 (decisione del 07/11, docs/82 §8). Solo symbol da exchange.
- La cassaforte è sigillata: alla lettura le sue barre si buttano subito e in memoria non resta nulla. Si rilegge dal
  disco solo con un PermessoCassaforte, che crea cassaforte.py (L4) dopo aver congelato l'elenco delle strategie.
- Finestra scorrevole (docs/82 P1): una cassaforte nuova non può toccare barre già usate come cassaforte per lo stesso
  asset. Il registro delle cassaforti è di L4: qui c'è il controllo, controlla_cassaforte_nuova.
"""
from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

from engine.exchange import controlla_storico, copertura_funding, ha_funding, leggi_csv
from engine.livelli import GIORNATA_UTC, imposta_giornata
from engine.quarantena import imposta_rollover, passo_barre
from engine.simboli import da_exchange, info_symbol

from .blocchi import MINUTI_TIMEFRAME

PEZZI = ("ricerca", "selezione", "cassaforte")
APERTI = ("ricerca", "selezione")
COLONNE = ("Open", "High", "Low", "Close", "Volume")


def _utc(t) -> pd.Timestamp:
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _durata(ore, nome: str) -> pd.Timedelta:
    if isinstance(ore, bool) or not isinstance(ore, (int, float)) or not math.isfinite(ore) or not ore > 0:
        raise ValueError(f"confini: {nome} deve essere un numero di ore maggiore di zero, non {ore!r}")
    return pd.Timedelta(seconds=round(float(ore) * 3600.0))


@dataclass(frozen=True)
class Confini:
    """Una data di inizio (UTC) e le durate dei tre pezzi, in ore."""
    inizio: pd.Timestamp
    ricerca_ore: float
    selezione_ore: float
    cassaforte_ore: float

    @classmethod
    def da_config(cls, c: dict) -> "Confini":
        attesi = {"inizio", "ricerca_ore", "selezione_ore", "cassaforte_ore"}
        if not isinstance(c, dict) or set(c) != attesi:
            raise ValueError(f"confini: servono esattamente {sorted(attesi)}, non {sorted(c) if isinstance(c, dict) else c!r}")
        try:
            inizio = _utc(c["inizio"])
        except (ValueError, TypeError) as e:
            raise ValueError(f"confini: inizio {c['inizio']!r} non è una data") from e
        for nome in ("ricerca_ore", "selezione_ore", "cassaforte_ore"):
            _durata(c[nome], nome)
        return cls(inizio, float(c["ricerca_ore"]), float(c["selezione_ore"]), float(c["cassaforte_ore"]))

    def limiti(self) -> dict:
        """{pezzo: (da, a)}: ogni pezzo va da `da` compreso ad `a` escluso."""
        a = self.inizio
        b = a + _durata(self.ricerca_ore, "ricerca_ore")
        c = b + _durata(self.selezione_ore, "selezione_ore")
        d = c + _durata(self.cassaforte_ore, "cassaforte_ore")
        return {"ricerca": (a, b), "selezione": (b, c), "cassaforte": (c, d)}

    @property
    def tratto_cassaforte(self) -> tuple:
        return self.limiti()["cassaforte"]


class PermessoCassaforte:
    """
    Il permesso di leggere la cassaforte di un tratto. Lo crea solo cassaforte.py (L4), dopo che l'elenco delle
    strategie che entrano è congelato e scritto nel registro. Qui serve solo a riconoscerlo.
    """

    def __init__(self, symbol: str, timeframe: str, tratto: tuple):
        self.symbol, self.timeframe, self.tratto = symbol, timeframe, (_utc(tratto[0]), _utc(tratto[1]))


def impronta_pezzo(df: pd.DataFrame) -> str:
    """L'impronta (sha256) di un pezzo: istanti delle barre e prezzi OHLCV, byte per byte."""
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(pd.DatetimeIndex(df.index).as_unit("ns").asi8).tobytes())
    for col in COLONNE:
        h.update(col.encode("utf-8"))
        h.update(np.ascontiguousarray(df[col].to_numpy(dtype=np.float64)).tobytes())
    return h.hexdigest()


def _taglia(df: pd.DataFrame, da: pd.Timestamp, a: pd.Timestamp) -> pd.DataFrame:
    idx = pd.DatetimeIndex(df.index)
    return df.iloc[idx.searchsorted(da, side="left"): idx.searchsorted(a, side="left")].copy()


def imposta_mercato_crypto() -> None:
    """Mercato 24/7, prezzi degli scambi: nessun rollover e giornata delle 00:00 UTC. Sono impostazioni globali del
    motore: ogni processo della ricerca le rifà da sé, se no quarantena e livelli cambierebbero con i processi."""
    imposta_rollover(None)
    imposta_giornata(GIORNATA_UTC)


def percorso_storico(symbol: str, timeframe: str, cartella) -> str:
    return os.path.join(str(cartella), f"{symbol}_{timeframe}.csv")


def _leggi(symbol: str, timeframe: str, cartella) -> pd.DataFrame:
    """Lo storico intero, con i controlli di vetrina.carica_storico per i symbol da exchange."""
    if not da_exchange(symbol):
        raise ValueError(f"{symbol!r} non è un symbol da exchange (SIMBOLI_EXCHANGE in engine/simboli.py): "
                         "la fabbrica lavora solo sulle crypto da exchange.")
    info_symbol(symbol)
    if timeframe not in MINUTI_TIMEFRAME:
        raise ValueError(f"timeframe {timeframe!r} non previsto: {sorted(MINUTI_TIMEFRAME)}")
    percorso = percorso_storico(symbol, timeframe, cartella)
    if not os.path.exists(percorso):
        raise FileNotFoundError(f"Non trovo {percorso}: serve il CSV dello storico {timeframe} di {symbol} "
                                "(scaricalo con scarica_dati_crypto.py).")
    imposta_mercato_crypto()
    df = leggi_csv(percorso)
    attesa = pd.Timedelta(minutes=MINUTI_TIMEFRAME[timeframe])
    if len(df) < 2 or passo_barre(df.index) != attesa:
        raise ValueError(f"{percorso}: le barre non sono da {timeframe}.")
    return df


def _funding(symbol: str, df: pd.DataFrame, da: pd.Timestamp, a: pd.Timestamp, cartella) -> pd.DataFrame | None:
    """Il funding che copre le barre di `df`, tagliato al pezzo (da `da` compreso ad `a` escluso): None sullo spot."""
    if not ha_funding(symbol):
        return None
    from engine.vetrina import carica_funding
    f = carica_funding(symbol, df, cartella)
    istanti = pd.DatetimeIndex(f.index)
    f = f[(istanti >= da) & (istanti < a)].copy()
    motivo = copertura_funding(f, df)
    if motivo is not None:
        raise ValueError(f"il funding di {symbol} non copre il pezzo: {motivo}")
    return f


class Pezzi:
    """Ricerca e selezione aperte, la cassaforte sigillata (vedi la testa del file)."""

    def __init__(self, symbol, timeframe, confini: Confini, cartella, ricerca, selezione, funding, controlli):
        self.symbol, self.timeframe, self.confini, self.cartella = symbol, timeframe, confini, str(cartella)
        self.ricerca, self.selezione = ricerca, selezione
        self.funding = funding
        self.controlli = controlli
        self.impronte = {nome: impronta_pezzo(getattr(self, nome)) for nome in APERTI}

    def df(self, nome: str) -> pd.DataFrame:
        if nome not in APERTI:
            raise ValueError(f"pezzo {nome!r}: aperti sono solo {APERTI}; la cassaforte si apre con apri_cassaforte")
        return getattr(self, nome)

    def costi(self, nome: str) -> dict:
        """I costi del pezzo, calcolati sul pezzo tagliato (vetrina.costi_storico con df_prezzo = il pezzo)."""
        from engine.vetrina import costi_storico
        df = self.df(nome)
        return costi_storico(self.symbol, df, funding=self.funding[nome], df_prezzo=df)[0]

    def verifica_impronte(self) -> None:
        """Si ferma se un pezzo aperto è cambiato dopo la lettura."""
        for nome in APERTI:
            if impronta_pezzo(getattr(self, nome)) != self.impronte[nome]:
                raise ValueError(f"il pezzo {nome} è cambiato dopo la lettura: la ricerca si ferma.")

    def apri_cassaforte(self, permesso) -> dict:
        """{"df", "funding"} della cassaforte, riletti dal disco. Senza il permesso del tratto giusto si ferma."""
        if not isinstance(permesso, PermessoCassaforte):
            raise PermissionError("la cassaforte si apre solo con il permesso creato da cassaforte.py (docs/82 P8).")
        if (permesso.symbol, permesso.timeframe, permesso.tratto) != (self.symbol, self.timeframe,
                                                                        self.confini.tratto_cassaforte):
            raise PermissionError("il permesso è di un'altra cassaforte (symbol, timeframe o tratto diversi).")
        da, a = self.confini.tratto_cassaforte
        df = _taglia(_leggi(self.symbol, self.timeframe, self.cartella), da, a)
        return {"df": df, "funding": _funding(self.symbol, df, da, a, self.cartella)}


def carica_pezzi(symbol: str, timeframe: str, confini: Confini, cartella="dati") -> Pezzi:
    """
    Legge lo storico, lo taglia subito e restituisce ricerca e selezione con il loro funding; la cassaforte resta
    sigillata. Si ferma se i dati non coprono tutti e tre i pezzi.
    """
    df = _leggi(symbol, timeframe, cartella)
    limiti = confini.limiti()
    idx = pd.DatetimeIndex(df.index)
    passo = pd.Timedelta(minutes=MINUTI_TIMEFRAME[timeframe])
    inizio, fine = limiti["ricerca"][0], limiti["cassaforte"][1]
    if idx[0] > inizio + passo:
        raise ValueError(f"i dati partono il {idx[0]:%d/%m/%Y %H:%M}, dopo l'inizio della ricerca "
                         f"({inizio:%d/%m/%Y %H:%M} UTC).")
    if idx[-1] < fine - passo:
        raise ValueError(f"la cassaforte finisce il {fine:%d/%m/%Y %H:%M} UTC, i dati il {idx[-1]:%d/%m/%Y %H:%M}: "
                         "aggiorna lo storico o accorcia i confini.")
    pezzi = {nome: _taglia(df, *limiti[nome]) for nome in APERTI}
    del df, idx                       # la cassaforte non resta in memoria
    for nome, p in pezzi.items():
        if len(p) < 2:
            raise ValueError(f"il pezzo {nome} è vuoto: controlla i confini.")
    funding = {nome: _funding(symbol, pezzi[nome], *limiti[nome], cartella) for nome in APERTI}
    controlli = {nome: controlla_storico(pezzi[nome], timeframe) for nome in APERTI}
    return Pezzi(symbol, timeframe, confini, cartella, pezzi["ricerca"], pezzi["selezione"], funding, controlli)


def controlla_cassaforte_nuova(confini: Confini, tratti_usati) -> None:
    """
    Finestra scorrevole (docs/82 P1): si ferma se la cassaforte di `confini` tocca un tratto già usato come cassaforte
    per lo stesso asset. `tratti_usati` = coppie (da, a) del registro delle cassaforti (L4).
    """
    da, a = confini.tratto_cassaforte
    for vecchio in tratti_usati:
        v_da, v_a = _utc(vecchio[0]), _utc(vecchio[1])
        if da < v_a and a > v_da:
            raise ValueError(f"la cassaforte nuova ({da:%d/%m/%Y %H:%M} – {a:%d/%m/%Y %H:%M} UTC) tocca barre già usate "
                             f"come cassaforte ({v_da:%d/%m/%Y %H:%M} – {v_a:%d/%m/%Y %H:%M}): sposta l'inizio di almeno "
                             "la durata della cassaforte.")
