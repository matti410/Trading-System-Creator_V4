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
# C1 (docs/82 §11.2 e §11.12, 12/11): tutto il resto del catalogo dei trigger. I timeframe sono quelli della tabella
# D4 approvata da Mattia; il motivo di ogni esclusione sta in MOTIVI_ESCLUSIONE. Un trigger senza lato short (E19) ha
# None al posto della condizione short: il blocco esiste solo sul long. L'etichetta di famiglia è diversa per ogni
# blocco: solo ADX e ATR relativo ne condividono una (decisione del 06/11).
_TUTTI = tuple(MINUTI_TIMEFRAME)
_SENZA = lambda *tf: tuple(t for t in MINUTI_TIMEFRAME if t not in tf)   # noqa: E731
TRIGGER_CATALOGO.update({
    "E1": ("E1_RSI_CROSS_OVERSOLD", "E1_SHORT_RSI_CROSS_OVERBOUGHT", "RSI che entra in zona estrema", _TUTTI),
    "E2": ("E2_ZLEMA_CROSS_UP", "E2_SHORT_ZLEMA_CROSS_DOWN", "incrocio della ZLEMA confermato", _TUTTI),
    "E3": ("E3_LONG_INTRABAR_WEAKNESS_FADE", "E3_SHORT_INTRABAR_STRENGTH_FADE", "contro la barra estrema", _TUTTI),
    "E4": ("E4_EMA_CROSS_UP", "E4_SHORT_EMA_CROSS_DOWN", "incrocio EMA 20 / EMA 50", _TUTTI),
    "E6": ("E6_BACK_IN_STYLE", "E6_SHORT_BACK_IN_STYLE", "compressione a quattro barre", _TUTTI),
    "E7": ("E7_BIG_TAIL_BARS", "E7_SHORT_BIG_TAIL_BARS", "barre a coda lunga", _TUTTI),
    "E8": ("E8_CLOSING_PATTERN_ONLY", "E8_SHORT_CLOSING_PATTERN_ONLY", "chiusure in accelerazione", _TUTTI),
    "E9": ("E9_CLOSING_PATTERN_ONLY_II", "E9_SHORT_CLOSING_PATTERN_ONLY_II", "chiusure a dente di sega", _TUTTI),
    "E10": ("E10_HAMMER", "E10_SHORT_HANGING_MAN", "hammer / hanging man", _TUTTI),
    "E11": ("E11_INVERTED_HAMMER", "E11_SHORT_SHOOTING_STAR", "inverted hammer / shooting star", _TUTTI),
    "E12": ("E12_ENGULFING", "E12_SHORT_ENGULFING", "engulfing", _TUTTI),
    "E13": ("E13_HARAMI", "E13_SHORT_HARAMI", "harami", _TUTTI),
    "E16": ("E16_MORNING_STAR", "E16_SHORT_EVENING_STAR", "morning star / evening star", _TUTTI),
    "E19": ("E19_THREE_WHITE_SOLDIERS", None, "three white soldiers", _TUTTI),
    "E21": ("E21_BELT_HOLD", "E21_SHORT_BELT_HOLD", "belt hold", _TUTTI),
    "E22": ("E22_ASIAN_RANGE_BREAKOUT", "E22_SHORT_ASIAN_RANGE_BREAKDOWN", "rottura del range asiatico", _SENZA("H4", "D1")),
    "E23": ("E23_PREV_DAY_HIGH_BREAKOUT", "E23_SHORT_PREV_DAY_LOW_BREAKDOWN", "rottura del massimo o minimo di ieri",
            _SENZA("D1")),
    "E24": ("E24_CYCLE_TURN_UP", "E24_SHORT_CYCLE_TURN_DOWN", "svolta del ciclo dominante", _TUTTI),
    "E25": ("E25_ATC_PVO_SETUP_UP", "E25_SHORT_ATC_PVO_SETUP_DOWN", "cambio del canale adattivo con PVO", _TUTTI),
    "E26": ("E26_SUPERTREND_IIX_SETUP_UP", "E26_SHORT_SUPERTREND_IIX_SETUP_DOWN", "cambio del Supertrend con Intraday "
            "Intensity", _TUTTI),
    "E27": ("E27_VSA_BULLISH", "E27_SHORT_VSA_BEARISH", "figure VSA", _TUTTI),
    "E28": ("E28_VFI_CROSS_UP", "E28_SHORT_VFI_CROSS_DOWN", "VFI che passa lo zero", _TUTTI),
    "E29": ("E29_SQUEEZE_RELEASE_UP", "E29_SHORT_SQUEEZE_RELEASE_DOWN", "rilascio dello squeeze", _TUTTI),
    "E30": ("E30_WAVETREND_CROSS_UP", "E30_SHORT_WAVETREND_CROSS_DOWN", "incrocio WaveTrend in zona estrema", _TUTTI),
    "E31": ("E31_TRIPLE_SCREEN_UP", "E31_SHORT_TRIPLE_SCREEN_DOWN", "Triple Screen di Elder", ("M1", "M5", "M15", "M30")),
    "E32": ("E32_ALGOX_CAREFUL_UP", "E32_SHORT_ALGOX_CAREFUL_DOWN", "AlgoXplorer careful", _TUTTI),
    "E33": ("E33_ALGOX_NOVOL_CAREFUL_UP", "E33_SHORT_ALGOX_NOVOL_CAREFUL_DOWN", "AlgoXplorer careful senza volume",
            _TUTTI),
    "E34": ("E34_VSA_TREND_GO_UP", "E34_SHORT_VSA_TREND_GO_DOWN", "VSA trend following", _TUTTI),
    "E35": ("E35_VSA_STOP_REVERSE_UP", "E35_SHORT_VSA_STOP_REVERSE_DOWN", "VSA stop and reverse", _TUTTI),
    "E37": ("E37_INTRADAY_MOMENTUM_COMBO_UP", "E37_SHORT_INTRADAY_MOMENTUM_COMBO_DOWN", "momentum di sessione combinato",
            ("M1", "M5", "M15", "M30")),
    "E38": ("E38_HOUR_MOMENTUM_UP", "E38_SHORT_HOUR_MOMENTUM_DOWN", "coppia di ore 8~22 UTC", _SENZA("H4", "D1")),
    "E39": ("E39_HOUR_REVERSAL_UP", "E39_SHORT_HOUR_REVERSAL_DOWN", "coppia di ore 12~13 UTC", _SENZA("H4", "D1")),
    "E40": ("E40_JUMP_MOMENTUM_UP", "E40_SHORT_JUMP_MOMENTUM_DOWN", "momentum dopo un salto", ("M1", "M5", "M15", "M30")),
    "E41": ("E41_DAILY_QUINTILE_UP", "E41_SHORT_DAILY_QUINTILE_DOWN", "quintile della giornata", _SENZA("D1")),
    "E45": ("E45_RENDIMENTO_4H_ENTRA_Q1", "E45_SHORT_RENDIMENTO_4H_ENTRA_Q5", "rendimento a 4 ore nel quintile estremo",
            _SENZA("D1")),
    "E46": ("E46_CANALE_24H_IMPULSO_UP", "E46_SHORT_CANALE_24H_IMPULSO_DOWN", "canale di 24 ore con impulso",
            ("M5", "M15")),
    "E48": ("E48_MASSIMI_UGUALI_ROTTURA_UP", "E48_SHORT_MINIMI_UGUALI_ROTTURA_DOWN", "massimi o minimi uguali rotti",
            ("M5", "M15")),
    "E52": ("E52_AREA_RUMORE_SOPRA", "E52_SHORT_AREA_RUMORE_SOTTO", "uscita dall'area di rumore", ("M5", "M15", "M30")),
})
# nome del blocco -> (filtro long, filtro short, famiglia, finestre in barre del catalogo).
# Lo stesso nome due volte = neutro rispetto al lato.
FILTRI_CATALOGO = {
    "F2_MID_VOLATILITY": ("F2_MID_VOLATILITY", "F2_MID_VOLATILITY", "volatilita", {"atr": 14, "percentile": 500}),
    "F3_VOLUME_ABOVE_AVG": ("F3_VOLUME_ABOVE_AVG", "F3_VOLUME_ABOVE_AVG", "volume", {"media": 20}),
    "TREND_CONTEXT": ("F8_UPTREND_CONTEXT", "F9_DOWNTREND_CONTEXT", "trend", {"ema": 50}),
    "F25_CHOP_TREND": ("F25_CHOP_TREND", "F25_CHOP_TREND", "regime", {"choppiness": 14, "percentile": 500}),
    "F20_SESSION_OVERLAP": ("F20_SESSION_OVERLAP", "F20_SESSION_OVERLAP", "orario", {}),
}
# C1 (docs/82 §11.2, 12/11): tutto il resto del catalogo dei filtri, filter_conditions.py e
# vwap_regime_filter_conditions.py, tranne F36 (Fear & Greed, escluso per ora). Le coppie con un verso sono un blocco
# solo, con il nome dell'etichetta della coppia nel registro, come TREND_CONTEXT.
FILTRI_CATALOGO.update({
    "F1_ADX_ABOVE": ("F1_ADX_ABOVE", "F1_ADX_ABOVE", "forza del trend (ADX del catalogo)", {"adx": 14}),
    "F2_HIGH_VOLATILITY": ("F2_HIGH_VOLATILITY", "F2_HIGH_VOLATILITY", "volatilita alta", {"atr": 14, "percentile": 500}),
    "F14_LOW_DRIFT_REGIME": ("F14_LOW_DRIFT_REGIME", "F14_LOW_DRIFT_REGIME", "bassa deriva",
                             {"media": 100, "percentile": 500}),
    "F15_SHORT_TERM_CONSISTENCY": ("F15_SHORT_TERM_CONSISTENCY", "F15_SHORT_TERM_CONSISTENCY",
                                   "coerenza delle ultime variazioni", {"variazioni": 3}),
    "F20_SESSION_ASIA": ("F20_SESSION_ASIA", "F20_SESSION_ASIA", "orario: Tokyo", {}),
    "F20_SESSION_EUROPE": ("F20_SESSION_EUROPE", "F20_SESSION_EUROPE", "orario: Londra", {}),
    "F20_SESSION_US": ("F20_SESSION_US", "F20_SESSION_US", "orario: New York", {}),
    "F22_FAR_FROM_ROLLOVER": ("F22_FAR_FROM_ROLLOVER", "F22_FAR_FROM_ROLLOVER", "lontano dal rollover", {}),
    "F23_CYCLE_STRENGTH": ("F23_CYCLE_STRENGTH", "F23_CYCLE_STRENGTH", "forza del ciclo",
                           {"ciclo": 300, "percentile": 2000}),
    "F25_CHOP_RANGE": ("F25_CHOP_RANGE", "F25_CHOP_RANGE", "regime laterale", {"choppiness": 14, "percentile": 500}),
    "F26_VARIANCE_RATIO_TREND": ("F26_VARIANCE_RATIO_TREND", "F26_VARIANCE_RATIO_TREND", "persistenza dei rendimenti",
                                 {"variance_ratio": 192, "percentile": 1000}),
    "F29_RVOL_LOW": ("F29_RVOL_LOW", "F29_RVOL_LOW", "volume relativo basso", {"rvol": 30, "percentile": 500}),
    "F32_KER_RANGE": ("F32_KER_RANGE", "F32_KER_RANGE", "efficienza bassa", {"ker": 10, "percentile": 500}),
    "F35_JDH_REGIME_TREND": ("F35_JDH_REGIME_TREND", "F35_JDH_REGIME_TREND", "regime di tendenza (jdehorty)",
                             {"media": 200}),
    "F39_INSIDE_DAY": ("F39_INSIDE_DAY", "F39_INSIDE_DAY", "inside day", {}),
    "VWAP_GAP_WIDENING": ("VWAP_GAP_WIDENING", "VWAP_GAP_WIDENING", "scarto dal VWAP che si allarga", {}),
    "MACD_SIGNAL": ("F4_MACD_ABOVE_SIGNAL", "F4_MACD_BELOW_SIGNAL", "MACD rispetto alla signal", {}),
    "TREND_CONVICTION": ("F10_TREND_CONVICTION_UP", "F11_TREND_CONVICTION_DOWN", "deriva di fondo",
                         {"rendimento": 350, "percentile": 500}),
    "OVERNIGHT_RETURN": ("F21_OVERNIGHT_UP", "F21_OVERNIGHT_DOWN", "notte americana", {}),
    "TWO_BARS": ("F24_TWO_BARS_UP", "F24_TWO_BARS_DOWN", "due barre dello stesso colore", {}),
    "VFI_SIGN": ("F28_VFI_POSITIVE", "F28_VFI_NEGATIVE", "segno del VFI", {"vfi": 130}),
    "ALGOX_STATE": ("F40_ALGOX_STATE_LONG", "F40_ALGOX_STATE_SHORT", "stato AlgoXplorer", {}),
    "VWAP_SESSION_CLOSE": ("VWAP_PREVIOUS_SESSION_CLOSED_ABOVE", "VWAP_PREVIOUS_SESSION_CLOSED_BELOW",
                           "chiusura della sessione rispetto al VWAP", {}),
})
# I filtri che su un timeframe restano fuori: F20 guarda l'ora della barra e su D1 la barra è sempre quella delle 00:00.
# C1 (12/11): anche gli altri filtri esclusi della tabella D4 (docs/82 §11.12); il motivo sta in MOTIVI_ESCLUSIONE.
FILTRI_MAI_VERI = {"F20_SESSION_OVERLAP": ("D1",), "F20_SESSION_ASIA": ("D1",), "F20_SESSION_EUROPE": ("D1",),
                   "F20_SESSION_US": ("D1",), "OVERNIGHT_RETURN": ("H4", "D1"), "F22_FAR_FROM_ROLLOVER": ("D1",),
                   "VWAP_GAP_WIDENING": ("D1",), "VWAP_SESSION_CLOSE": ("D1",)}
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
# C1 (12/11): la tabella D4 di docs/82 §11.12, approvata da Mattia il 12/11 sera, con le stesse parole.
_SESSIONE_DI_UNA_BARRA = "la sessione è una barra sola: la regressione intraday della sessione non esiste"
MOTIVI_ESCLUSIONE.update({
    ("E22", "H4"): (APPROSSIMAZIONE_ESCLUSA, "in estate l'apertura di Londra cade dentro una barra e il range asiatico si "
                                             "allunga di un'ora: una variante della regola"),
    ("E22", "D1"): (LIMITE_LOGICO, "la barra giornaliera è sempre quella delle 00:00: le aperture di Tokyo e di Londra "
                                   "non sono l'inizio di una barra"),
    ("E23", "D1"): (LIMITE_LOGICO, "la giornata è una barra sola: «la prima rottura del giorno» è ogni barra che chiude "
                                   "sopra il massimo di ieri, e due giorni di fila fanno uno stato, non un evento"),
    ("E31", "H1"): (APPROSSIMAZIONE_ESCLUSA, "l'ingresso su H1 coincide con lo schermo H1: i tre schermi diventano due"),
    **{("E31", tf): (LIMITE_LOGICO, "le candele H4 e H1 dei tre schermi non sono più larghe della barra")
       for tf in ("H4", "D1")},
    **{("E37", tf): (LIMITE_LOGICO, "le 09:30, le 16:00 e le 16:30 di New York non sono la fine di una candela di questo "
                                    "timeframe") for tf in ("H1", "H4", "D1")},
    **{("E38", tf): (LIMITE_LOGICO, "l'ora dalle 07:00 alle 08:00 UTC e la candela che finisce alle 21:00 sono più corte "
                                    "di una barra") for tf in ("H4", "D1")},
    **{("E39", tf): (LIMITE_LOGICO, "l'ora dalle 11:00 alle 12:00 UTC è più corta di una barra") for tf in ("H4", "D1")},
    **{("E40", tf): (LIMITE_LOGICO, "i controlli di mezz'ora sono più corti di una barra") for tf in ("H1", "H4", "D1")},
    ("E41", "D1"): (LIMITE_LOGICO, "su D1 due giornate di fila nel quintile sono due barre vicine, e _evento ne tiene una "
                                   "sola; su M15 sono due segnali"),
    ("E45", "D1"): (LIMITE_LOGICO, "le 4 ore del rendimento sono più corte di una barra"),
    ("E46", "M1"): _SOLO_M1,
    ("E46", "M30"): (APPROSSIMAZIONE_ESCLUSA, "l'impulso di 45 minuti diventerebbe di 60 (2 barre): una variante della "
                                              "regola"),
    **{("E46", tf): (LIMITE_LOGICO, "i 45 minuti dell'impulso sono più corti di una barra") for tf in ("H1", "H4", "D1")},
    ("E48", "M1"): _SOLO_M1,
    **{("E48", tf): (LIMITE_LOGICO, "i 15 minuti per lato del massimo locale sono più corti di una barra")
       for tf in ("M30", "H1", "H4", "D1")},
    ("E52", "M1"): _SOLO_M1,
    **{("E52", tf): (APPROSSIMAZIONE_ESCLUSA, "i controlli di mezz'ora diventerebbero ogni ora (ogni 4 ore su H4): una "
                                              "variante della regola") for tf in ("H1", "H4")},
    ("E52", "D1"): (LIMITE_LOGICO, "la giornata è una barra sola: nessun controllo dentro la giornata"),
    ("F20_SESSION_ASIA", "D1"): (LIMITE_LOGICO, "la barra giornaliera è sempre quella delle 00:00, sempre dentro la "
                                                "sessione di Tokyo nei giorni feriali: il filtro direbbe solo «giorno "
                                                "feriale»"),
    ("F20_SESSION_EUROPE", "D1"): (LIMITE_LOGICO, "la barra giornaliera è sempre quella delle 00:00: Londra non è mai "
                                                  "aperta"),
    ("F20_SESSION_US", "D1"): (LIMITE_LOGICO, "la barra giornaliera è sempre quella delle 00:00: New York non è mai "
                                              "aperta"),
    ("OVERNIGHT_RETURN", "H4"): (APPROSSIMAZIONE_ESCLUSA, "in inverno l'apertura di New York cade dentro la barra delle "
                                                          "12:00 UTC e la fotografia passa alla barra delle 16:00, 3 ore "
                                                          "dopo: una variante della regola"),
    ("OVERNIGHT_RETURN", "D1"): (LIMITE_LOGICO, "le aperture di New York non sono l'inizio di una barra giornaliera"),
    ("F22_FAR_FROM_ROLLOVER", "D1"): (LIMITE_LOGICO, "la barra giornaliera è sempre quella delle 00:00 UTC, sempre a più "
                                                     "di 4 ore dal rollover: il filtro è sempre vero"),
    ("VWAP_GAP_WIDENING", "D1"): (LIMITE_LOGICO, _SESSIONE_DI_UNA_BARRA),
    ("VWAP_SESSION_CLOSE", "D1"): (LIMITE_LOGICO, _SESSIONE_DI_UNA_BARRA),
})
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
    import vwap_regime_filter_conditions
    with contextlib.redirect_stdout(io.StringIO()):
        entry_long.registra_trigger_long()
        entry_short.registra_trigger_short()
        exit_long.registra_exit_long()
        exit_short.registra_exit_short()
        filter_conditions.registra_filtri()
        vwap_regime_filter_conditions.registra_filtri_vwap()      # C1 (12/11): come vetrina._registra_condizioni


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
    _catalogo: tuple | None = None        # (condizione long, condizione short); short None = solo long (E19)

    @property
    def lati(self) -> tuple:
        """I lati su cui il blocco esiste: (1, -1), oppure (1,) per un trigger del catalogo senza lato short (C1, E19)."""
        return (1,) if self._catalogo is not None and self._catalogo[1] is None else (1, -1)

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
            if nome is None:
                raise ValueError(f"{self.nome} non ha il lato short nel catalogo: esiste solo sul long.")
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
