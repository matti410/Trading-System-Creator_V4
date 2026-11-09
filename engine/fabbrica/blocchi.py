"""
I blocchi della fabbrica (docs/82 P-L2, lavoro L2): i mattoncini con cui il generatore di L3 costruisce le teorie.

    blocchi = blocchi_da_config({"timeframe": "M15", "blocchi": {"E47": {}, "RSI_RIENTRO": {}, "X3": {}}})
    b = blocchi[1]
    b.parametri                                     # gli spazi dello zoom, al passo più fine (Intero, Reale, Categoria)
    b.griglia                                       # i valori larghi del passo 1 (P-L2), in barre
    b.maschera(cache, 1, {"periodo_barre": 24, "soglia": 25})
    b.ore_effettive({"periodo_barre": 24, "soglia": 25})    # {"periodo_barre": 6.0}: barre × durata della barra
    b.finestre_ore()                                # le finestre fisse del blocco, in ore, per la scheda

- Trigger: eventi, la prima barra vera. Filtri: stati. Uscite: una regola più durata, stop e target.
- I parametri si scrivono in ORE nella config e diventano barre secondo il timeframe, da M1 a D1: la barra più vicina,
  minimo 1 (2 dove il calcolo la chiede). Nella griglia i valori doppi dopo l'arrotondamento si tolgono. Solo prezzo
  e volume.
- Spazio di un parametro: stesso minimo e massimo della griglia, passo più fine (1 barra, 1 per le soglie intere, 0,1 per
  la soglia di ATR relativo).
- I blocchi del catalogo prendono la condizione dal registro (engine.registry): i dizionari non cambiano. Il loro
  df deve avere le colonne di aggiungi_indicatori. Il catalogo non ha parametri: hanno finestre sue, in barre o in minuti.
  Su un timeframe dove non scatterebbe mai, due casi (08/11):
  - config standard (config.config_standard): il blocco esce dalla config con il suo motivo (MOTIVI_ESCLUSIONE: limite
    logico, approssimazione esclusa per scelta, escluso solo dall'elenco) e la ricerca prosegue;
  - config scritta a mano: un blocco scelto esplicitamente che non scatta ferma la config con un errore che dice quale
    blocco e perché (_non_scatta).
- `famiglia` è quella di P-L2 e P3; il generatore (L3) la controlla con famiglie.py.
"""
from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from engine import registry as reg

from .cache import ORE_FINESTRA_SOGLIE, barre_da_ore
from .ottimizzatore import Categoria, Intero, Reale

MINUTI_TIMEFRAME = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
TIPI = ("trigger", "filtro", "uscita")

# nome del blocco -> (entry long, entry short, famiglia, timeframe su cui il catalogo scatta)
TRIGGER_CATALOGO = {
    "E5": ("E5_QUICK_PULLBACK", "E5_SHORT_QUICK_PULLBACK", "rottura dopo inside bar", tuple(MINUTI_TIMEFRAME)),
    "E36": ("E36_INTRADAY_MOMENTUM_UP", "E36_SHORT_INTRADAY_MOMENTUM_DOWN", "momentum di sessione", ("M1", "M5", "M15", "M30")),
    "E47": ("E47_COMPRESSIONE_ROTTURA_UP", "E47_SHORT_COMPRESSIONE_ROTTURA_DOWN", "rottura dopo compressione", ("M5", "M15")),
    "E49": ("E49_SWEEP_RECLAIM_MINIMO", "E49_SHORT_SWEEP_RECLAIM_MASSIMO", "spazzata e rientro", ("M5", "M15", "M30", "H1")),
    "E51": ("E51_MOVIMENTO_VOLUME_CALO_GIU", "E51_SHORT_MOVIMENTO_VOLUME_CALO_SU", "esaurimento su volume", ("M5", "M15", "M30", "H1")),
}
# nome del blocco -> (filtro long, filtro short, famiglia, finestre in barre del catalogo).
# Lo stesso nome due volte = neutro rispetto al lato.
FILTRI_CATALOGO = {
    "F2_MID_VOLATILITY": ("F2_MID_VOLATILITY", "F2_MID_VOLATILITY", "volatilita", {"atr": 14, "percentile": 500}),
    "F3_VOLUME_ABOVE_AVG": ("F3_VOLUME_ABOVE_AVG", "F3_VOLUME_ABOVE_AVG", "volume", {"media": 20}),
    "TREND_CONTEXT": ("F8_UPTREND_CONTEXT", "F9_DOWNTREND_CONTEXT", "trend", {"ema": 50}),
    "F25_CHOP_TREND": ("F25_CHOP_TREND", "F25_CHOP_TREND", "regime", {"choppiness": 14, "percentile": 500}),
    "F20_SESSION_OVERLAP": ("F20_SESSION_OVERLAP", "F20_SESSION_OVERLAP", "orario", {}),
}
# I filtri che su un timeframe non sono mai veri: F20 guarda l'ora della barra e su D1 la barra è sempre quella delle 00:00.
FILTRI_MAI_VERI = {"F20_SESSION_OVERLAP": ("D1",)}
# Perché un blocco del catalogo resta fuori su un timeframe (L5a, 08/11; diagnosi e decisione di Mattia dell'08/11).
# Tre casi: il limite è nella logica; un'approssimazione della regola esclusa per scelta (sarebbe una variante, non la
# regola); escluso solo dall'elenco dei timeframe del catalogo (la regola in minuti sarebbe la stessa: aprire M1 è un
# lavoro futuro, separato). Un collaudo controlla che ogni blocco tolto dalla config standard abbia qui il suo motivo.
LIMITE_LOGICO = "limite logico"
APPROSSIMAZIONE_ESCLUSA = "approssimazione esclusa per scelta"
SOLO_ELENCO = "escluso solo dall'elenco"
_SOLO_M1 = (SOLO_ELENCO, "la regola in minuti sarebbe la stessa; l'elenco dei timeframe del catalogo parte da M5 "
                         "(aprire M1 è un lavoro futuro, separato)")
MOTIVI_ESCLUSIONE = {
    **{("E36", tf): (LIMITE_LOGICO, "le 09:30 e le 16:30 di New York non sono la fine di una candela di questo "
                                    "timeframe") for tf in ("H1", "H4", "D1")},
    ("E47", "M1"): _SOLO_M1,
    ("E47", "M30"): (APPROSSIMAZIONE_ESCLUSA, "l'ATR di 70 minuti diventerebbe di 60 (2 barre): una variante della "
                                              "regola"),
    **{("E47", tf): (LIMITE_LOGICO, "ATR e sua media sarebbero di una barra sola: l'ATR non può stare sotto 0,8 volte "
                                    "sé stesso") for tf in ("H1", "H4", "D1")},
    ("E49", "M1"): _SOLO_M1,
    **{("E49", tf): (LIMITE_LOGICO, "le 3 ore per lato e la candela di un'ora sono più corte di una barra")
       for tf in ("H4", "D1")},
    ("E51", "M1"): _SOLO_M1,
    ("E51", "H4"): (APPROSSIMAZIONE_ESCLUSA, "il movimento di 5 ore diventerebbe di 4 (1 barra): una variante della "
                                             "regola"),
    ("E51", "D1"): (LIMITE_LOGICO, "le 5 ore del movimento sono più corte di una barra"),
    ("F20_SESSION_OVERLAP", "D1"): (LIMITE_LOGICO, "la barra giornaliera è sempre quella delle 00:00: Londra e New York "
                                                   "non sono mai aperte insieme"),
}
# nome del blocco -> (uscita long, uscita short, famiglia)
USCITE_CATALOGO = {
    "X0": ("X0_NO_EXIT", "X0_SHORT_NO_EXIT", "nessuna regola"),
    "X3": ("X3_MACD_BEARISH", "X3_SHORT_MACD_BULLISH", "MACD sotto la signal (stato)"),
    "X1": ("X1_CYCLE_TURN_DOWN", "X1_SHORT_CYCLE_TURN_UP", "svolta del ciclo"),
}
# I valori del passo 1 (docs/82 P-L2). Le chiavi che finiscono in _ore si convertono in barre.
GRIGLIE_USCITA = {"durata_ore": (1, 2, 4, 8), "perc_stop": (70, 80, 90, 95), "target": (None, 90)}
GRIGLIE_NUOVI = {
    "RSI_RIENTRO": {"periodo_ore": (2, 4, 6, 9, 12), "soglia": (15, 20, 25, 30, 35)},
    "DONCHIAN": {"canale_ore": (4, 8, 12, 24, 48, 96)},
    "ADX": {"periodo_ore": (4, 6, 9), "soglia": (15, 20, 25, 30)},
    "ATR_RELATIVO": {"breve_ore": (2, 4), "lungo_ore": (24, 48, 96), "soglia": (0.8, 1.0, 1.2, 1.5)},
}
# Il passo delle soglie non intere; tutte le altre soglie sono intere, a passo 1.
PASSI_REALI = {("ATR_RELATIVO", "soglia"): 0.1}
# Il minimo in barre di periodo di RSI e ADX e di ATR lungo, deciso da Mattia il 07/11 (docs/82 §8): i valori sotto salgono
# a 5 e i doppi si tolgono. Altrove il minimo è 1 barra, ATR breve compreso.
BARRE_MINIME = {"periodo_barre": 5, "lungo_barre": 5}


# ------------------------------------------------------------------ il catalogo, dal registro
def _registra_catalogo() -> None:
    """Le stesse registrazioni del Lab: i nomi già presenti vengono saltati, i dizionari non cambiano."""
    import entry_long
    import entry_short
    import exit_long
    import exit_short
    import filter_conditions
    with contextlib.redirect_stdout(io.StringIO()):
        entry_long.registra_trigger_long()
        entry_short.registra_trigger_short()
        exit_long.registra_exit_long()
        exit_short.registra_exit_short()
        filter_conditions.registra_filtri()


def _dal_registro(tipo: str, nome: str) -> Callable:
    prendi = {"trigger": reg.get_entry, "filtro": reg.get_filter, "uscita": reg.get_exit}[tipo]
    try:
        return prendi(nome)
    except KeyError:
        _registra_catalogo()
        return prendi(nome)


def _booleana(s: pd.Series) -> np.ndarray:
    """Da condizione a array booleano: NaN = falso, come famiglie.py."""
    if s.dtype == bool:
        return s.to_numpy()
    return np.nan_to_num(pd.to_numeric(s, errors="coerce").to_numpy(dtype=float), nan=0.0) != 0


# ------------------------------------------------------------------ i blocchi nuovi
def _evento(stato: np.ndarray) -> np.ndarray:
    """La prima barra di ogni blocco di barre vere, come helpers._evento."""
    return stato & ~np.r_[False, stato[:-1]]


def _rsi_rientro(cache, lato: int, v: dict) -> np.ndarray:
    """Long: l'RSI risale sopra la soglia da sotto. Short: scende sotto 100 - soglia da sopra."""
    r = cache.indicatore("rsi", barre=v["periodo_barre"])
    m = np.zeros(len(r), dtype=bool)
    if lato == 1:
        m[1:] = (r[1:] > v["soglia"]) & (r[:-1] <= v["soglia"])
    else:
        livello = 100.0 - v["soglia"]
        m[1:] = (r[1:] < livello) & (r[:-1] >= livello)
    return m


def _donchian(cache, lato: int, v: dict) -> np.ndarray:
    """Long: chiusura sopra il massimo delle N ore precedenti, barra corrente esclusa. Short: speculare, sul minimo."""
    c = cache.df["Close"].to_numpy(dtype=float)
    if lato == 1:
        return _evento(c > cache.indicatore("donchian_massimo", barre=v["canale_barre"]))
    return _evento(c < cache.indicatore("donchian_minimo", barre=v["canale_barre"]))


def _adx(cache, lato: int, v: dict) -> np.ndarray:
    """Stato: ADX sopra la soglia."""
    return cache.indicatore("adx", barre=v["periodo_barre"]) > v["soglia"]


def _atr_relativo(cache, lato: int, v: dict) -> np.ndarray:
    """Stato: ATR breve / ATR lungo sopra la soglia."""
    return cache.indicatore("atr_relativo", breve=v["breve_barre"], lungo=v["lungo_barre"]) > v["soglia"]


# ADX e ATR relativo hanno la stessa famiglia: decisa dalla misura di famiglie.py (docs/82 P3, decisione del 06/11).
FAMIGLIA_ADX_ATR = "forza del trend e volatilita relativa"
CALCOLI_NUOVI = {
    "RSI_RIENTRO": ("trigger", "inversione", _rsi_rientro),
    "DONCHIAN": ("trigger", "rottura", _donchian),
    "ADX": ("filtro", FAMIGLIA_ADX_ATR, _adx),
    "ATR_RELATIVO": ("filtro", FAMIGLIA_ADX_ATR, _atr_relativo),
}


# ------------------------------------------------------------------ il blocco
@dataclass(frozen=True)
class Blocco:
    """
    nome, tipo (trigger, filtro, uscita), famiglia.
    minuti_barra    la durata di una barra del timeframe della config.
    parametri       Intero, Reale, Categoria dell'ottimizzatore: lo spazio dello zoom, al passo più fine, periodi in barre.
    griglia         nome del parametro -> i valori larghi del passo 1, in barre.
    neutro          un filtro che non dipende dal lato.
    finestre_barre  le finestre fisse del blocco: quelle del catalogo per i filtri, quella delle soglie per le uscite.
    Le uscite hanno anche `soglie`: durata, stop e target.
    """
    nome: str
    tipo: str
    famiglia: str
    minuti_barra: int
    parametri: tuple = ()
    griglia: dict = field(default_factory=dict)
    neutro: bool = False
    finestre_barre: dict = field(default_factory=dict)
    _calcola: Callable | None = None      # (cache, lato, valori) -> array, per i blocchi nuovi
    _catalogo: tuple | None = None        # (condizione long, condizione short)

    def centrali(self) -> dict:
        """I valori centrali della griglia: l'elemento di mezzo, o quello subito sopra se sono pari."""
        return {nome: valori[len(valori) // 2] for nome, valori in self.griglia.items()}

    def _in_ore(self, barre: int) -> float:
        return int(barre) * self.minuti_barra / 60.0

    def ore_effettive(self, valori: dict) -> dict:
        """Per la scheda: i parametri in barre di `valori`, in ore effettive (barre × durata della barra)."""
        return {nome: self._in_ore(v) for nome, v in valori.items() if nome.endswith("_barre")}

    def griglia_ore(self) -> dict:
        """Per la scheda: i valori del passo 1 dei parametri in barre, in ore effettive."""
        return {nome: tuple(self._in_ore(v) for v in valori) for nome, valori in self.griglia.items() if nome.endswith("_barre")}

    def finestre_ore(self) -> dict:
        """Per la scheda: le finestre fisse del blocco, in ore effettive."""
        return {nome: self._in_ore(barre) for nome, barre in self.finestre_barre.items()}

    def _controlla(self, lato: int, valori: dict | None) -> dict:
        if lato not in (1, -1):
            raise ValueError(f"lato deve essere 1 (long) o -1 (short), non {lato!r}")
        valori = {} if valori is None else dict(valori)
        attesi = {p.nome for p in self.parametri}
        if set(valori) != attesi:
            raise ValueError(f"{self.nome}: servono i valori di {sorted(attesi)}, non {sorted(valori)}")
        for nome, v in valori.items():
            if nome.endswith("_barre") and (int(v) != v or v < BARRE_MINIME.get(nome, 1)):
                raise ValueError(f"{self.nome}: {nome} deve essere un numero intero di barre, almeno "
                                 f"{BARRE_MINIME.get(nome, 1)}, non {v!r}")
        return valori

    def maschera(self, cache, lato: int, valori: dict | None = None) -> np.ndarray:
        """Array booleano lungo come il df della cache. Per un'uscita è la regola: non dipende da durata, stop e target."""
        valori = self._controlla(lato, valori)
        if self._catalogo is not None:
            nome = self._catalogo[0 if lato == 1 else 1]
            return cache.prendi(("catalogo", nome), lambda: _booleana(_dal_registro(self.tipo, nome)(cache.df)))
        lato_chiave = 0 if self.neutro else lato
        chiave = ("maschera", self.nome, lato_chiave, tuple(sorted(valori.items())))
        return cache.prendi(chiave, lambda: self._calcola(cache, lato, valori))

    def soglie(self, cache, lato: int, valori: dict) -> dict:
        """Solo per le uscite: {"barre", "sl", "tp"}; sl e tp sono array di frazioni del prezzo, NaN se spenti."""
        if self.tipo != "uscita":
            raise ValueError(f"{self.nome} non è un'uscita")
        valori = self._controlla(lato, valori)
        s = cache.soglie_uscita(cache.ore(valori["durata_barre"]), valori["perc_stop"], valori["target"])
        verso = "long" if lato == 1 else "short"
        return {"barre": int(valori["durata_barre"]), "sl": s[f"sl_{verso}"], "tp": s[f"tp_{verso}"]}


# ------------------------------------------------------------------ dalla config ai blocchi
def _parametro(blocco: str, chiave: str, valori, minuti: int):
    """
    Da una riga di griglia allo spazio dello zoom e ai valori del passo 1. Lo spazio ha minimo e massimo della griglia e
    il passo più fine: 1 barra, 1 per le soglie intere, PASSI_REALI per le altre. I valori doppi si tolgono.
    """
    valori = list(valori)
    if not valori:
        raise ValueError(f"{blocco}: {chiave} non ha valori")
    if chiave == "target":
        return Categoria("target", tuple(valori)), tuple(valori)
    if chiave.endswith("_ore"):
        nome = chiave[: -len("_ore")] + "_barre"
        barre = sorted({barre_da_ore(o, minuti, BARRE_MINIME.get(nome, 1)) for o in valori})
        return Intero(nome, barre[0], barre[-1], 1), tuple(barre)
    passo = PASSI_REALI.get((blocco, chiave))
    if passo is None:
        if not all(float(v).is_integer() for v in valori):
            raise ValueError(f"{blocco}: {chiave} vuole valori interi, non {valori}")
        interi = sorted({int(v) for v in valori})
        return Intero(chiave, interi[0], interi[-1], 1), tuple(interi)
    if any(abs(float(v) / passo - round(float(v) / passo)) > 1e-9 for v in valori):
        raise ValueError(f"{blocco}: {chiave} vuole multipli di {passo}, non {valori}")
    reali = sorted({round(float(v), 10) for v in valori})
    return Reale(chiave, reali[0], reali[-1], passo), tuple(reali)


def _parametri(nome: str, griglie: dict, config_blocco: dict, minuti: int) -> tuple[tuple, dict]:
    estranei = set(config_blocco) - set(griglie)
    if estranei:
        raise ValueError(f"{nome}: parametri sconosciuti {sorted(estranei)}; ammessi {sorted(griglie)}")
    parametri, griglia = [], {}
    for chiave, predefiniti in griglie.items():
        parametro, valori = _parametro(nome, chiave, config_blocco.get(chiave, predefiniti), minuti)
        parametri.append(parametro)
        griglia[parametro.nome] = valori
    return tuple(parametri), griglia


def _non_scatta(nome: str, timeframe: str, di_base: str) -> ValueError:
    """L'errore di una config scritta a mano con un blocco che su quel timeframe non scatta: quale blocco e perché."""
    tipo, motivo = MOTIVI_ESCLUSIONE.get((nome, timeframe), (None, None))
    perche = f"{tipo}: {motivo}" if tipo else di_base
    return ValueError(f"il blocco {nome} non scatta su {timeframe} ({perche}). Toglilo dalla config, oppure usa la "
                      "config standard, che lo lascia fuori da sola con il suo motivo.")


def _blocco(nome: str, config_blocco: dict, timeframe: str) -> Blocco:
    minuti = MINUTI_TIMEFRAME[timeframe]
    if nome in TRIGGER_CATALOGO or nome in FILTRI_CATALOGO:
        if config_blocco:
            raise ValueError(f"{nome} è del catalogo e non ha parametri: {sorted(config_blocco)}")
    if nome in TRIGGER_CATALOGO:
        lungo, corto, famiglia, ammessi = TRIGGER_CATALOGO[nome]
        if timeframe not in ammessi:
            raise _non_scatta(nome, timeframe, f"sul catalogo scatta solo su {', '.join(ammessi)}")
        return Blocco(nome, "trigger", famiglia, minuti, _catalogo=(lungo, corto))
    if nome in FILTRI_CATALOGO:
        if timeframe in FILTRI_MAI_VERI.get(nome, ()):
            raise _non_scatta(nome, timeframe, "sul catalogo non è mai vero su questo timeframe")
        lungo, corto, famiglia, finestre = FILTRI_CATALOGO[nome]
        return Blocco(nome, "filtro", famiglia, minuti, neutro=lungo == corto, finestre_barre=dict(finestre), _catalogo=(lungo, corto))
    if nome in USCITE_CATALOGO:
        lungo, corto, famiglia = USCITE_CATALOGO[nome]
        parametri, griglia = _parametri(nome, GRIGLIE_USCITA, config_blocco, minuti)
        finestre = {"soglie_adattive": barre_da_ore(ORE_FINESTRA_SOGLIE, minuti)}
        return Blocco(nome, "uscita", famiglia, minuti, parametri, griglia, finestre_barre=finestre, _catalogo=(lungo, corto))
    if nome in CALCOLI_NUOVI:
        tipo, famiglia, calcola = CALCOLI_NUOVI[nome]
        parametri, griglia = _parametri(nome, GRIGLIE_NUOVI[nome], config_blocco, minuti)
        return Blocco(nome, tipo, famiglia, minuti, parametri, griglia, neutro=tipo == "filtro", _calcola=calcola)
    noti = sorted([*TRIGGER_CATALOGO, *FILTRI_CATALOGO, *USCITE_CATALOGO, *CALCOLI_NUOVI])
    raise ValueError(f"blocco {nome!r} sconosciuto: {noti}")


def blocchi_da_config(config: dict) -> list[Blocco]:
    """I blocchi di config["blocchi"] ({nome: griglie, {} = quelle di P-L2}), sul timeframe di config["timeframe"]."""
    timeframe = config["timeframe"]
    if timeframe not in MINUTI_TIMEFRAME:
        raise ValueError(f"timeframe {timeframe!r} non previsto: {sorted(MINUTI_TIMEFRAME)}")
    return [_blocco(nome, config_blocco or {}, timeframe) for nome, config_blocco in config["blocchi"].items()]
