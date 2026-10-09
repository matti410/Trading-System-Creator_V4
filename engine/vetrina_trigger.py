"""
Vetrina · cosa disegnare per spiegare un trigger (9/10/2026) — schermata 7b.

A COSA SERVE
------------
La lente (engine/vetrina_verifica.py) disegna un trade sul grafico a candele.
Fino ad ora sapeva disegnare solo gli INDICATORI gia' calcolati nei dati
(rsi, ema20, vwap...). Ma molti trigger non sono un indicatore: E21_BELT_HOLD
e' una figura di candele, E22_ASIAN_RANGE_BREAKOUT e' «la chiusura rompe il
massimo del range asiatico». Per questi non c'era nulla da scrivere nel campo
«indicatori», e sul grafico si vedeva solo il triangolo del segnale.

Questo modulo risponde, per ogni trigger scattato su un trade, a quattro
domande, e la lente fa il resto:

    etichetta    il nome del trigger (scritto accanto al triangolo)
    barre        le candele che formano la figura o su cui la regola si basa
                 (evidenziate con una banda colorata)
    livelli      le linee di prezzo che la regola doveva rompere
    indicatori   le colonne dei dati che la regola legge (disegnate come se
                 le avessi scritte tu nel campo «indicatori»), con la linea
                 di soglia dove c'e'

I QUATTRO TIPI DI TRIGGER
-------------------------
1. FIGURE DI CANDELE (E10-E21, lato long e short, anche le «_CONFIRMED»):
   banda sulle candele della figura. Quante sono lo dice la tabella `_FIGURE`.
   Non e' scritta a memoria: `test_vetrina_trigger.py` (sezione A) la misura
   sui dati, spostando una candela alla volta e guardando quando il segnale
   sparisce. Una figura «_CONFIRMED» ha una candela in piu' (la conferma).
2. REGOLE SU PIU' CANDELE (E5, E6, E8, E9): banda sulle candele che la regola
   confronta (`_BARRE`); per E5 anche la linea del massimo/minimo di due
   candele prima, che la chiusura deve rompere.
3. LIVELLI (E22 range asiatico, E23 giornata precedente): la linea del
   livello, letta dalla STESSA funzione che usa il trigger (`range_finestra`),
   non ricalcolata. Si disegna il tratto in cui vale il livello della candela
   del segnale, non quelli dei giorni accanto.
4. INDICATORI (E1, E2, E4, E24, E25, E26): le colonne che la regola legge e,
   dove serve, la linea dello zero o della soglia (RSI 30/70, ciclo 0...).
   Anche qui la tabella `_INDICATORI` e' verificata dal test: le colonne
   elencate sono ESATTAMENTE quelle che il trigger legge.

Tutti gli altri (E3, E7, E27, metro orarie, trigger nuovi aggiunti dopo): solo
nome + banda sulla candela del segnale. Niente errori e niente disegni
inventati: se un trigger nuovo merita un disegno, si aggiunge una riga a una
delle tabelle qui sotto.

Modulo ADDITIVO: non modifica nessun file esistente. Non importa plotly: restituisce
solo dati, cosi' si puo' collaudare senza grafici.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import registry as reg
from .livelli import range_finestra


@dataclass
class Disegno:
    """Cosa disegnare per UN trigger scattato. Le posizioni sono assolute (nel df)."""
    nome: str
    barre: tuple = ()          # posizioni delle candele da evidenziare
    livelli: tuple = ()        # ((testo, valori lungo la finestra), ...) — NaN dove la linea non c'e'
    indicatori: tuple = ()     # colonne del df da disegnare
    soglie: dict = field(default_factory=dict)   # colonna -> valore della linea di riferimento


# ========================================================================
# Le tabelle
# ========================================================================

# 1 · Figure di candele TA-Lib. Valore = quante candele formano la figura,
# compresa quella del segnale (che e' l'ultima). Misurato dal test, sezione A.
_FIGURE = {
    # long
    "E10_HAMMER": 2,
    "E11_INVERTED_HAMMER": 2, "E11_INVERTED_HAMMER_CONFIRMED": 3,
    "E12_ENGULFING": 2, "E12_ENGULFING_CONFIRMED": 3,
    "E13_HARAMI": 2, "E13_HARAMI_CONFIRMED": 3,
    "E14_HARAMI_CROSS": 2, "E14_HARAMI_CROSS_CONFIRMED": 3,
    "E15_PIERCING": 2,
    "E16_MORNING_STAR": 3,
    "E17_THREE_INSIDE": 3,
    "E18_THREE_OUTSIDE": 3,
    "E19_THREE_WHITE_SOLDIERS": 3,
    "E20_MARUBOZU": 1,
    "E21_BELT_HOLD": 1, "E21_BELT_HOLD_CONFIRMED": 2,
    # short
    "E10_SHORT_HANGING_MAN": 2,
    "E11_SHORT_SHOOTING_STAR": 2, "E11_SHORT_SHOOTING_STAR_CONFIRMED": 3,
    "E12_SHORT_ENGULFING": 2, "E12_SHORT_ENGULFING_CONFIRMED": 3,
    "E13_SHORT_HARAMI": 2, "E13_SHORT_HARAMI_CONFIRMED": 3,
    "E14_SHORT_HARAMI_CROSS": 2, "E14_SHORT_HARAMI_CROSS_CONFIRMED": 3,
    "E15_SHORT_DARK_CLOUD_COVER": 2,
    "E16_SHORT_EVENING_STAR": 3,
    "E17_SHORT_THREE_INSIDE": 3,
    "E18_SHORT_THREE_OUTSIDE": 3,
    "E19_SHORT_THREE_BLACK_CROWS": 4,
    "E20_SHORT_MARUBOZU": 1,
    "E21_SHORT_BELT_HOLD": 1, "E21_SHORT_BELT_HOLD_CONFIRMED": 2,
}

# 2 · Regole che confrontano piu' candele, e regole che leggono un indicatore
# ma hanno anche una condizione sulle candele. Valore = distanze dalla candela
# del segnale (0 = la candela del segnale, 1 = quella prima, ...) delle candele
# che la regola legge. () = nessuna banda (il segnale e' un incrocio fra
# indicatori: basta il triangolo). Misurato dal test, sezione A.
_BARRE = {
    "E5_QUICK_PULLBACK": (0, 1, 2), "E5_SHORT_QUICK_PULLBACK": (0, 1, 2),
    "E6_BACK_IN_STYLE": (0, 1, 2, 3), "E6_SHORT_BACK_IN_STYLE": (0, 1, 2, 3),
    "E8_CLOSING_PATTERN_ONLY": (0, 1, 2, 3), "E8_SHORT_CLOSING_PATTERN_ONLY": (0, 1, 2, 3),
    # E9 non legge la candela del segnale: confronta le 5 chiusure precedenti
    "E9_CLOSING_PATTERN_ONLY_II": (1, 2, 3, 4, 5), "E9_SHORT_CLOSING_PATTERN_ONLY_II": (1, 2, 3, 4, 5),
    # livelli: la linea basta, il segnale e' la chiusura che la rompe
    "E22_ASIAN_RANGE_BREAKOUT": (), "E22_SHORT_ASIAN_RANGE_BREAKDOWN": (),
    "E23_PREV_DAY_HIGH_BREAKOUT": (), "E23_SHORT_PREV_DAY_LOW_BREAKDOWN": (),
    # incroci: nessuna banda
    "E1_RSI_CROSS_OVERSOLD": (), "E1_SHORT_RSI_CROSS_OVERBOUGHT": (),
    "E2_ZLEMA_CROSS_UP": (), "E2_SHORT_ZLEMA_CROSS_DOWN": (),
    "E4_EMA_CROSS_UP": (), "E4_SHORT_EMA_CROSS_DOWN": (),
    "E24_CYCLE_TURN_UP": (), "E24_SHORT_CYCLE_TURN_DOWN": (),
    # setup di articolo: due candele concordi (E25), la candela prima (E26)
    "E25_ATC_PVO_SETUP_UP": (0, 1), "E25_SHORT_ATC_PVO_SETUP_DOWN": (0, 1),
    "E26_SUPERTREND_IIX_SETUP_UP": (1,), "E26_SHORT_SUPERTREND_IIX_SETUP_DOWN": (1,),
}

# 3 · Colonne dei dati che il trigger legge (oltre ai prezzi). Il test controlla
# che siano ESATTAMENTE quelle: se una manca o ce n'e' una di troppo, fallisce.
_INDICATORI = {
    "E1_RSI_CROSS_OVERSOLD": ("rsi",), "E1_SHORT_RSI_CROSS_OVERBOUGHT": ("rsi",),
    "E2_ZLEMA_CROSS_UP": ("zlema50",), "E2_SHORT_ZLEMA_CROSS_DOWN": ("zlema50",),
    "E4_EMA_CROSS_UP": ("ema20", "ema50"), "E4_SHORT_EMA_CROSS_DOWN": ("ema20", "ema50"),
    "E24_CYCLE_TURN_UP": ("ciclo_pendenza",), "E24_SHORT_CYCLE_TURN_DOWN": ("ciclo_pendenza",),
    "E25_ATC_PVO_SETUP_UP": ("atc_regime", "pvo_hist"),
    "E25_SHORT_ATC_PVO_SETUP_DOWN": ("atc_regime", "pvo_hist"),
    "E26_SUPERTREND_IIX_SETUP_UP": ("st_dir", "iix"),
    "E26_SHORT_SUPERTREND_IIX_SETUP_DOWN": ("st_dir", "iix"),
}

# Linee di riferimento fisse nei pannelli degli indicatori (la soglia dell'RSI
# invece si legge dal parametro `threshold` del trigger, per non scriverla due volte).
_SOGLIE_FISSE = {"ciclo_pendenza": 0.0, "pvo_hist": 0.0, "iix": 0.0}
_TRIGGER_RSI = ("E1_RSI_CROSS_OVERSOLD", "E1_SHORT_RSI_CROSS_OVERBOUGHT")

# 4 · Livelli di prezzo.
#   da una finestra di sessione: (argomenti di range_finestra, colonna, testo)
_LIVELLI_FINESTRA = {
    "E22_ASIAN_RANGE_BREAKOUT": (("TOKYO", "LONDRA"), "massimo", "massimo del range asiatico"),
    "E22_SHORT_ASIAN_RANGE_BREAKDOWN": (("TOKYO", "LONDRA"), "minimo", "minimo del range asiatico"),
    "E23_PREV_DAY_HIGH_BREAKOUT": (("ROLLOVER",), "massimo", "massimo del giorno prima"),
    "E23_SHORT_PREV_DAY_LOW_BREAKDOWN": (("ROLLOVER",), "minimo", "minimo del giorno prima"),
}
#   da una candela precedente: (colonna dei prezzi, quante candele prima, testo)
_LIVELLI_CANDELA = {
    "E5_QUICK_PULLBACK": ("High", 2, "massimo di 2 candele prima"),
    "E5_SHORT_QUICK_PULLBACK": ("Low", 2, "minimo di 2 candele prima"),
}


def trigger_con_disegno() -> set[str]:
    """I nomi dei trigger che hanno qualcosa in piu' del nome e della candela del segnale."""
    return (set(_FIGURE) | set(_BARRE) | set(_INDICATORI)
            | set(_LIVELLI_FINESTRA) | set(_LIVELLI_CANDELA))


# ========================================================================
# La funzione che usa la lente
# ========================================================================

def _barre(nome: str, pos: int, n: int) -> tuple:
    if nome in _FIGURE:
        distanze = range(_FIGURE[nome])
    elif nome in _BARRE:
        distanze = _BARRE[nome]
    else:
        distanze = (0,)                      # senza regola nota: la candela del segnale
    return tuple(sorted(pos - d for d in distanze if 0 <= pos - d < n))


def _soglie(nome: str, indicatori: tuple) -> dict:
    soglie = {c: v for c, v in _SOGLIE_FISSE.items() if c in indicatori}
    if nome in _TRIGGER_RSI:
        try:
            soglia = inspect.signature(reg.get_entry(nome)).parameters["threshold"].default
            if isinstance(soglia, (int, float)):
                soglie["rsi"] = float(soglia)
        except Exception:
            pass
    return soglie


def _livelli(nome: str, df: pd.DataFrame, pos: int, inizio: int, fine: int) -> tuple:
    n_finestra = fine - inizio + 1
    if nome in _LIVELLI_FINESTRA:
        argomenti, colonna, testo = _LIVELLI_FINESTRA[nome]
        livelli = range_finestra(df, *argomenti)
        valori = livelli[colonna].to_numpy(dtype=float)[inizio:fine + 1].copy()
        valori[~livelli["pronto"].to_numpy(dtype=bool)[inizio:fine + 1]] = np.nan
        # Il livello cambia da un giorno all'altro. Si disegna solo il tratto in
        # cui vale quello della candela del segnale: gli altri, anche mezzo
        # grafico lontani dal prezzo, stirerebbero la scala e schiaccerebbero le candele.
        p = pos - inizio
        if not 0 <= p < n_finestra or not np.isfinite(valori[p]):
            return ()
        sinistra = destra = p
        while sinistra > 0 and valori[sinistra - 1] == valori[p]:
            sinistra -= 1
        while destra < n_finestra - 1 and valori[destra + 1] == valori[p]:
            destra += 1
        tratto = np.full(n_finestra, np.nan)
        tratto[sinistra:destra + 1] = valori[p]
        return ((testo, tratto),)
    if nome in _LIVELLI_CANDELA:
        colonna, distanza, testo = _LIVELLI_CANDELA[nome]
        origine = pos - distanza
        if origine < 0:
            return ()
        valori = np.full(n_finestra, np.nan)
        # la linea va dalla candela che la fissa fino a quella del segnale
        valori[max(origine, inizio) - inizio:pos - inizio + 1] = float(df[colonna].iloc[origine])
        return ((testo, valori),)
    return ()


def descrivi_trigger(nome: str, df: pd.DataFrame, pos: int, inizio: int, fine: int) -> Disegno:
    """
    Cosa disegnare per il trigger `nome` scattato sulla candela `pos` di `df`.

    inizio, fine   la finestra del grafico, come posizioni nel df (estremi
                   inclusi): i livelli sono vettori lunghi `fine - inizio + 1`,
                   allineati alle candele del grafico.

    Non solleva errori per un trigger sconosciuto: restituisce nome e candela
    del segnale.
    """
    pos = int(pos)
    indicatori = tuple(c for c in _INDICATORI.get(nome, ()) if c in df.columns)
    return Disegno(
        nome=nome,
        barre=_barre(nome, pos, len(df)),
        livelli=_livelli(nome, df, pos, int(inizio), int(fine)),
        indicatori=indicatori,
        soglie=_soglie(nome, indicatori),
    )
