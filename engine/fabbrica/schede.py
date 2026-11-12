"""
Le schede della fabbrica (docs/82 P10 e §6, lavoro L5a): un .json e un .md per ogni strategia entrata in cassaforte.

    sc = componi_scheda(esito_ricerca, esito_cassaforte, id_strategia, mm=riassunto_mm)    # il dizionario del .json
    md, js = scrivi_scheda(sc, cartella)              # <cartella>/<id_strategia>.md e .json
    sc = leggi_scheda(js)
    trade = trade_da_scheda(sc, cartella_dati)        # {"in_sample", "cassaforte"}: gli stessi trade, al bit
    regole_in_parole(strategia, timeframe)            # le regole scritte dal testo di ogni blocco con i suoi valori

- La regola in parole viene dal testo di ogni blocco (TESTI_TRIGGER, TESTI_FILTRI, TESTI_USCITE), con i valori della
  strategia in ore e in barre del timeframe. Un collaudo controlla che ogni blocco della config standard abbia il testo
  per tutti e due i lati.
- Dal solo .json si ricostruisce la strategia (lato, blocchi, valori in barre: l'id deve tornare) e, con i dati del
  symbol, si riottengono i trade in-sample (ricerca + selezione) e in cassaforte, al bit (P10). Le impronte dei tre
  pezzi devono essere quelle della scheda. La cassaforte si rilegge solo per una strategia già entrata nel suo tratto.
- La scheda porta anche i blocchi tolti su quel timeframe, con il motivo (08/11), e l'esito delle regole della verifica
  dei trade (schermata 8 del Lab) quando la cella 6 del notebook è stata eseguita per quella strategia.
- In fondo al .md sempre la frase FRASE_FINALE (Mattia, 08/11).
"""
from __future__ import annotations

import json
import math
import os
import subprocess

from . import registro
from .blocchi import MINUTI_TIMEFRAME, MOTIVI_ESCLUSIONE
from .cache import ORE_FINESTRA_SOGLIE, barre_da_ore
from .valutatore import Strategia, id_strategia

FRASE_FINALE = "La scheda descrive cosa è successo sui dati; la decisione è tua."
VERSIONE_SCHEDA = 1
TOLTO_DALLA_CONFIG = "tolto dalla config"

__all__ = ["FRASE_FINALE", "componi_scheda", "esclusi_dalla_config", "leggi_scheda", "regole_in_parole",
           "scrivi_scheda", "strategia_da_scheda", "testo_md", "trade_da_scheda"]


# ------------------------------------------------------------------ durate in parole
def _numero(x: float) -> str:
    """Un numero all'italiana, senza zeri inutili: 2 -> «2», 2.5 -> «2,5», 0.25 -> «0,25»."""
    if float(x).is_integer():
        return f"{int(x)}"
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _il(perc) -> str:
    """L'articolo davanti a una percentuale: «il 90%», «l'80%», «l'11%»."""
    s = _numero(perc)
    return ("l'" if s.startswith("8") or s in ("1", "11", "18") else "il ") + s + "%"


def durata(barre: int, minuti: int) -> str:
    """Una finestra in parole: «12 ore (48 barre)», «45 minuti (3 barre)», «1 barra» se dura come la barra."""
    barre = int(barre)
    tot = barre * int(minuti)
    tempo = (("1 minuto" if tot == 1 else f"{tot} minuti") if tot < 60
             else ("1 ora" if tot == 60 else f"{_numero(tot / 60)} ore"))
    return f"{tempo} ({barre} {'barra' if barre == 1 else 'barre'})"


# ------------------------------------------------------------------ i testi dei blocchi
# Ogni testo è una funzione (valori, d, lato) -> frase; d(barre) = durata in parole sul timeframe; lato 1 o -1.
def _su(lato, a, b):
    return a if lato == 1 else b


TESTI_TRIGGER = {
    "E5": lambda v, d, l: ("la barra di due barre fa contiene tutta quella di una barra fa (inside bar) e il Close "
                           + _su(l, "supera il massimo", "scende sotto il minimo") + " della barra di due barre fa"),
    "E36": lambda v, d, l: ("sulla candela che finisce alle 16:30 di New York, il prezzo è "
                            + _su(l, "salito", "sceso") + " dalle 17:00 di New York del giorno prima alle 09:30 di oggi"),
    "E47": lambda v, d, l: ("sulla barra prima l'ATR di 70 minuti era sotto 0,8 volte la sua media dell'ultima ora, e "
                            "il Close " + _su(l, "supera il massimo", "scende sotto il minimo")
                            + " delle 3 ore fino alla barra prima (finestre in minuti, convertite nelle barre)"),
    "E49": lambda v, d, l: (_su(l, "nell'ultima ora il Low è sceso sotto l'ultimo minimo confermato (il Low più basso",
                                "nell'ultima ora l'High è salito sopra l'ultimo massimo confermato (l'High più alto")
                            + " fra 3 ore prima e 3 ore dopo, noto 3 ore dopo) e il Close è tornato "
                            + _su(l, "sopra", "sotto")),
    "E51": lambda v, d, l: ("il prezzo è " + _su(l, "sceso", "salito") + " nelle ultime 5 ore più della deviazione "
                            "standard dei movimenti a 5 ore delle ultime 100 ore, e il volume medio delle ultime 5 ore è "
                            "sotto quello delle 5 ore prima"),
    "RSI_RIENTRO": lambda v, d, l: (f"l'RSI di {d(v['periodo_barre'])} "
                                    + _su(l, f"risale sopra {_numero(v['soglia'])} da sotto",
                                          f"scende sotto {_numero(100 - v['soglia'])} da sopra")),
    "DONCHIAN": lambda v, d, l: ("il Close " + _su(l, "supera il massimo degli High", "scende sotto il minimo dei Low")
                                 + f" delle {d(v['canale_barre'])} precedenti"),
}
TESTI_FILTRI = {
    "F2_MID_VOLATILITY": lambda v, d, l: (f"l'ATR di {d(14)} non è sopra il 75° percentile dei suoi valori delle "
                                          f"ultime {d(500)}"),
    "F3_VOLUME_ABOVE_AVG": lambda v, d, l: f"il volume della barra è sopra la sua media delle ultime {d(20)}",
    "TREND_CONTEXT": lambda v, d, l: f"il Close è {_su(l, 'sopra', 'sotto')} la media esponenziale di {d(50)}",
    "F25_CHOP_TREND": lambda v, d, l: (f"il mercato è in tendenza: il Choppiness Index di {d(14)} è sceso sotto il 25° "
                                       f"percentile delle ultime {d(500)} e non è ancora risalito sopra il 50°"),
    "F20_SESSION_OVERLAP": lambda v, d, l: ("Londra e New York sono aperte insieme (dalle 08:00 alle 17:00, ora locale "
                                            "di ciascuna)"),
    "ADX": lambda v, d, l: f"l'ADX di {d(v['periodo_barre'])} è sopra {_numero(v['soglia'])}",
    "ATR_RELATIVO": lambda v, d, l: (f"l'ATR di {d(v['breve_barre'])} diviso l'ATR di {d(v['lungo_barre'])} è sopra "
                                     f"{_numero(v['soglia'])}"),
}
TESTI_USCITE = {                       # la regola d'uscita; None = nessuna regola oltre a durata, stop e target
    "X0": lambda l: None,
    "X3": lambda l: _su(l, "il MACD scende sotto la sua signal", "il MACD sale sopra la sua signal"),
    "X1": lambda l: _su(l, "il ciclo dominante gira al ribasso", "il ciclo dominante gira al rialzo"),
}


# C1 (docs/82 §11.2, 12/11): i testi dei blocchi del catalogo entrati nella fabbrica, scritti leggendo il codice di ogni
# condizione (entry_long.py, entry_short.py, filter_conditions.py, vwap_regime_filter_conditions.py). Le finestre in barre
# del catalogo restano in barre: d() le dice anche in ore sul timeframe della strategia.
def _cdl(nome_long, nome_short, funzione_long, funzione_short):
    return lambda v, d, l: ("la barra chiude la figura " + _su(l, nome_long, nome_short) + " (TA-Lib "
                            + _su(l, funzione_long, funzione_short) + "; la prima di più barre di fila)")


TESTI_TRIGGER.update({
    "E1": lambda v, d, l: (f"l'RSI di {d(14)} " + _su(l, "scende sotto 30 da sopra (entra in ipervenduto)",
                                                     "sale sopra 70 da sotto (entra in ipercomprato)")),
    "E2": lambda v, d, l: (f"il Close della barra prima ha attraversato la ZLEMA di {d(50)} "
                           + _su(l, "dal basso verso l'alto", "dall'alto verso il basso") + ", e la barra chiude "
                           + _su(l, "sopra", "sotto") + " l'apertura, " + _su(l, "sopra", "sotto")
                           + " il Close della barra prima e ancora " + _su(l, "sopra", "sotto") + " la ZLEMA"),
    "E3": lambda v, d, l: ("il Close è " + _su(l, "nel 15% più basso", "nel 15% più alto") + f" dei Close delle ultime "
                           f"{d(10)} e il rapporto Close / Open della barra è "
                           + _su(l, "nel 15% più basso", "nel 15% più alto") + f" delle ultime {d(20)}"),
    "E4": lambda v, d, l: (f"la media esponenziale di {d(20)} attraversa quella di {d(50)} "
                           + _su(l, "dal basso verso l'alto", "dall'alto verso il basso")),
    "E6": lambda v, d, l: _su(l, "il Low della barra è sopra l'High di tre barre fa e sotto l'High della barra prima, e "
                                 "l'High della barra e quello della barra prima sono sotto l'High di due barre fa",
                              "l'High della barra è sotto il Low di tre barre fa e sopra il Low della barra prima, e il "
                              "Low della barra e quello della barra prima sono sopra il Low di due barre fa"),
    "E7": lambda v, d, l: (f"nelle ultime {d(10)} le barre " + _su(l, "rialziste", "ribassiste") + " a coda lunga "
                           + _su(l, "(chiusura sopra l'apertura, coda sotto più lunga del corpo, nuovo massimo)",
                                 "(chiusura sotto l'apertura, coda sopra più lunga del corpo, nuovo minimo)")
                           + " sono più di quelle " + _su(l, "ribassiste", "rialziste")
                           + f", e il loro numero supera il 90° percentile delle ultime {d(2000)}"),
    "E8": lambda v, d, l: ("il Close della barra prima è " + _su(l, "sopra", "sotto") + " quello di tre barre fa, il "
                           "Close di due barre fa è " + _su(l, "sopra", "sotto") + " quello della barra prima e il "
                           "Close della barra è " + _su(l, "sopra", "sotto") + " quello di due barre fa"),
    "E9": lambda v, d, l: ("il Close della barra prima è " + _su(l, "sotto", "sopra") + " quello di due barre fa, che è "
                           + _su(l, "sotto", "sopra") + " quello di cinque barre fa, che è " + _su(l, "sotto", "sopra")
                           + " quello di tre barre fa, che è " + _su(l, "sotto", "sopra") + " quello di quattro barre fa"),
    "E10": _cdl("hammer", "hanging man", "CDLHAMMER", "CDLHANGINGMAN"),
    "E11": _cdl("inverted hammer", "shooting star", "CDLINVERTEDHAMMER", "CDLSHOOTINGSTAR"),
    "E12": _cdl("engulfing rialzista", "engulfing ribassista", "CDLENGULFING", "CDLENGULFING"),
    "E13": _cdl("harami rialzista", "harami ribassista", "CDLHARAMI", "CDLHARAMI"),
    "E16": _cdl("morning star", "evening star", "CDLMORNINGSTAR", "CDLEVENINGSTAR"),
    "E19": _cdl("three white soldiers", "three white soldiers", "CDL3WHITESOLDIERS", "CDL3WHITESOLDIERS"),
    "E21": _cdl("belt hold rialzista", "belt hold ribassista", "CDLBELTHOLD", "CDLBELTHOLD"),
    "E22": lambda v, d, l: ("fra l'apertura di Londra e la chiusura di New York il Close "
                            + _su(l, "supera il massimo", "scende sotto il minimo") + " del range asiatico (dalle 09:00 "
                            "di Tokyo alle 08:00 di Londra); la prima volta nella giornata"),
    "E23": lambda v, d, l: ("il Close " + _su(l, "supera il massimo", "scende sotto il minimo") + " della giornata "
                            "precedente (da 00:00 a 00:00 UTC); la prima volta nella giornata"),
    "E24": lambda v, d, l: (f"la pendenza del ciclo dominante (trasformata di Fourier sulle ultime {d(300)}) passa da "
                            + _su(l, "negativa a positiva", "positiva a negativa")),
    "E25": lambda v, d, l: ("il canale di trend adattivo passa da " + _su(l, "ribassista a rialzista",
                                                                          "rialzista a ribassista")
                            + ", la barra e quella prima chiudono " + _su(l, "sopra", "sotto") + " l'apertura e "
                            "l'istogramma del PVO (12/26/9 sul volume) è " + _su(l, "sopra", "sotto") + " zero"),
    "E26": lambda v, d, l: ("il Supertrend (ATR 10, moltiplicatore 3) passa da " + _su(l, "ribassista a rialzista",
                                                                                       "rialzista a ribassista")
                            + ", la barra prima chiude " + _su(l, "sopra", "sotto") + f" l'apertura e l'Intraday "
                            f"Intensity di {d(21)} è " + _su(l, "sopra", "sotto") + " zero"),
    "E27": lambda v, d, l: ("la barra è una figura VSA " + _su(l, "rialzista: stopping volume o no supply",
                                                               "ribassista: climax di vendita o no demand")
                            + " (il volume confrontato con l'ampiezza della barra)"),
    "E28": lambda v, d, l: f"il Volume Flow Indicator di {d(130)} passa " + _su(l, "sopra", "sotto") + " lo zero",
    "E29": lambda v, d, l: ("le Bande di Bollinger escono dal canale di Keltner (fine dello squeeze) e il momentum dello "
                            "squeeze è " + _su(l, "sopra", "sotto") + " zero"),
    "E30": lambda v, d, l: ("la linea WT1 del WaveTrend incrocia la WT2 " + _su(l, "dal basso verso l'alto",
                                                                                "dall'alto verso il basso")
                            + " mentre WT1 è " + _su(l, "nel 10% più basso", "nel 10% più alto")
                            + f" dei suoi valori delle ultime {d(500)}"),
    "E31": lambda v, d, l: ("Triple Screen di Elder: la pendenza del MACD-Histogram dell'ultima H4 chiusa è "
                            + _su(l, "in salita", "in discesa") + ", il Force Index dell'ultima H1 chiusa è "
                            + _su(l, "sotto", "sopra") + " zero e il Close " + _su(l, "supera il massimo",
                                                                                 "scende sotto il minimo")
                            + " dell'ultima H1 chiusa"),
    "E32": lambda v, d, l: ("AlgoXplorer, ingresso careful: dopo un segnale " + _su(l, "Buy", "Sell") + " (candela PVSRA "
                            "climax, Heikin Ashi " + _su(l, "sopra la media esponenziale di 50 barre dei massimi",
                                                         "sotto la media esponenziale di 50 barre dei minimi")
                            + "), la prima barra il cui " + _su(l, "massimo Heikin Ashi supera il massimo",
                                                               "minimo Heikin Ashi scende sotto il minimo")
                            + " della candela del segnale"),
    "E33": lambda v, d, l: ("AlgoXplorer, ingresso careful senza la candela PVSRA: dopo un segnale "
                            + _su(l, "Buy", "Sell") + " (Heikin Ashi " + _su(l, "sopra la media esponenziale di 50 barre "
                                                                            "dei massimi",
                                                                            "sotto la media esponenziale di 50 barre "
                                                                            "dei minimi")
                            + "), la prima barra il cui " + _su(l, "massimo Heikin Ashi supera il massimo",
                                                               "minimo Heikin Ashi scende sotto il minimo")
                            + " della candela del segnale"),
    "E34": lambda v, d, l: ("VSA trend following: asta " + _su(l, "rialzista", "ribassista") + " confermata da almeno 2 "
                            "BOS, gamba più forte dell'altra di almeno il 20%, una candela di incongruenza VSA nelle 3 "
                            "barre prima vicina a uno swing, e una candela di conferma " + _su(l, "rialzista", "ribassista")
                            + " con corpo almeno al 50° percentile"),
    "E35": lambda v, d, l: ("VSA stop and reverse: il primo BOS " + _su(l, "rialzista dopo un'asta ribassista",
                                                                        "ribassista dopo un'asta rialzista")
                            + " confermata (CHoCH), chiuso da una candela " + _su(l, "rialzista", "ribassista")
                            + " con corpo almeno al 65° percentile"),
    "E37": lambda v, d, l: ("sulla candela che finisce alle 16:30 di New York, il prezzo è " + _su(l, "salito", "sceso")
                            + " dalle 17:00 di New York del giorno prima alle 09:30 di oggi ed è "
                            + _su(l, "sceso", "salito") + " dalle 16:00 alle 16:30"),
    "E38": lambda v, d, l: ("sulla candela che finisce alle 21:00 UTC, il prezzo è " + _su(l, "salito", "sceso")
                            + " dalle 07:00 alle 08:00 UTC dello stesso giorno"),
    "E39": lambda v, d, l: ("sulla candela che finisce alle 12:00 UTC, il prezzo è " + _su(l, "sceso", "salito")
                            + " dalle 11:00 alle 12:00 UTC"),
    "E40": lambda v, d, l: ("al primo controllo di mezz'ora della giornata (candela che finisce alle :00 o alle :30 di "
                            "New York) in cui il rendimento dalla chiusura di ieri, alle 17:00 di New York, "
                            + _su(l, "supera il 90°", "scende sotto il 10°") + " percentile dei rendimenti giornalieri "
                            "delle ultime 250 giornate"),
    "E41": lambda v, d, l: ("sulla candela che chiude la giornata (mezzanotte UTC), il rendimento della giornata è "
                            + _su(l, "sopra l'80°", "sotto il 20°") + " percentile delle 300 giornate prima"),
    "E45": lambda v, d, l: ("il rendimento delle ultime 4 ore entra nel quintile " + _su(l, "più basso", "più alto")
                            + " dei rendimenti a 4 ore dei 365 giorni prima (la barra prima era in un altro quintile)"),
    "E46": lambda v, d, l: ("il Close " + _su(l, "supera il massimo degli High", "scende sotto il minimo dei Low")
                            + " delle 24 ore prima e il rendimento degli ultimi 45 minuti è "
                            + _su(l, "sopra il 60°", "sotto il 40°") + " percentile delle 24 ore (finestre in minuti, "
                            "convertite nelle barre)"),
    "E48": lambda v, d, l: ("gli ultimi 3 " + _su(l, "massimi", "minimi") + " locali dei Close (15 minuti per lato), "
                            "dentro 500 minuti, stanno entro lo 0,2% e il Close è almeno lo 0,1% "
                            + _su(l, "sopra", "sotto") + " la loro media (finestre in minuti, convertite nelle barre)"),
    "E52": lambda v, d, l: ("a un controllo di mezz'ora (barra che finisce alle :00 o alle :30 UTC) il Close esce "
                            + _su(l, "sopra l'apertura della giornata più", "sotto l'apertura della giornata meno")
                            + " sigma, la media sui 14 giorni prima del movimento assoluto dall'apertura alla stessa ora; "
                            "al controllo prima della stessa giornata non era fuori"),
})
TESTI_FILTRI.update({
    "F1_ADX_ABOVE": lambda v, d, l: f"l'ADX di {d(14)} è sopra 20",
    "F2_HIGH_VOLATILITY": lambda v, d, l: (f"l'ATR di {d(14)} è sopra il 75° percentile dei suoi valori delle ultime "
                                           f"{d(500)}"),
    "F14_LOW_DRIFT_REGIME": lambda v, d, l: (f"quanto si è mossa la media dei Close di {d(100)} nelle ultime {d(100)}, "
                                             f"in rapporto al prezzo, è nel 30% più basso delle ultime {d(500)}"),
    "F15_SHORT_TERM_CONSISTENCY": lambda v, d, l: ("le ultime 3 variazioni del Close vanno nello stesso verso (una può "
                                                   "essere zero)"),
    "F20_SESSION_ASIA": lambda v, d, l: ("la barra si apre dentro la sessione di Tokyo (dalle 09:00 alle 18:00 di Tokyo, "
                                         "nei giorni feriali)"),
    "F20_SESSION_EUROPE": lambda v, d, l: ("la barra si apre dentro la sessione di Londra (dalle 08:00 alle 17:00 di "
                                           "Londra, nei giorni feriali)"),
    "F20_SESSION_US": lambda v, d, l: ("la barra si apre dentro la sessione di New York (dalle 08:00 alle 17:00 di New "
                                       "York, nei giorni feriali)"),
    "F22_FAR_FROM_ROLLOVER": lambda v, d, l: "mancano almeno 4 ore alle 17:00 di New York (il rollover del forex)",
    "F23_CYCLE_STRENGTH": lambda v, d, l: (f"la quota di energia del ciclo dominante (su {d(300)}) è sopra il 70° "
                                           f"percentile delle ultime {d(2000)}"),
    "F25_CHOP_RANGE": lambda v, d, l: (f"il mercato è laterale: il Choppiness Index di {d(14)} è salito sopra il 75° "
                                       f"percentile delle ultime {d(500)} e non è ancora sceso sotto il 50°"),
    "F26_VARIANCE_RATIO_TREND": lambda v, d, l: (f"i rendimenti tendono a ripetersi: il variance ratio a 4 barre su "
                                                 f"{d(192)} è salito sopra il 75° percentile delle ultime {d(1000)} e non "
                                                 "è ancora sceso sotto il 50°"),
    "F29_RVOL_LOW": lambda v, d, l: f"il volume relativo (su {d(30)}) è nel 25% più basso delle ultime {d(500)}",
    "F32_KER_RANGE": lambda v, d, l: (f"il mercato è poco efficiente: l'efficiency ratio di Kaufman di {d(10)}, senza "
                                      f"segno, è sceso sotto il 25° percentile delle ultime {d(500)} e non è ancora "
                                      "risalito sopra il 50°"),
    "F35_JDH_REGIME_TREND": lambda v, d, l: ("la pendenza della curva lisciata (regime di jdehorty) non è scesa più del "
                                             f"10% sotto la sua media esponenziale di {d(200)}"),
    "F39_INSIDE_DAY": lambda v, d, l: ("la giornata chiusa più recente è rimasta dentro il massimo e il minimo di quella "
                                       "prima (inside day)"),
    "VWAP_GAP_WIDENING": lambda v, d, l: ("lo scarto fra il fair value della sessione (regressione dei Close "
                                          "dall'inizio della giornata UTC) e il VWAP della sessione è più grande che "
                                          "sulla barra prima"),
    "MACD_SIGNAL": lambda v, d, l: "il MACD (12/26/9) è " + _su(l, "sopra", "sotto") + " la sua signal",
    "TREND_CONVICTION": lambda v, d, l: (f"la somma dei rendimenti delle ultime {d(350)} è "
                                         + _su(l, "sopra il 70°", "sotto il 30°") + f" percentile delle ultime {d(500)}"),
    "OVERNIGHT_RETURN": lambda v, d, l: ("la notte ha portato il prezzo " + _su(l, "su", "giù") + ": l'apertura di New "
                                         "York di oggi è " + _su(l, "sopra", "sotto") + " la chiusura della sessione di "
                                         "New York precedente"),
    "TWO_BARS": lambda v, d, l: "la barra e quella prima chiudono entrambe " + _su(l, "sopra", "sotto") + " l'apertura",
    "VFI_SIGN": lambda v, d, l: f"il Volume Flow Indicator di {d(130)} è " + _su(l, "sopra", "sotto") + " zero",
    "ALGOX_STATE": lambda v, d, l: "l'ultimo segnale di AlgoXplorer è un " + _su(l, "Buy", "Sell"),
    "VWAP_SESSION_CLOSE": lambda v, d, l: ("la sessione precedente (giornata UTC) ha chiuso con il fair value "
                                           + _su(l, "sopra", "sotto") + " il VWAP"),
})


def _ore(barre: int, minuti: int) -> str:
    tot = int(barre) * int(minuti)
    return ("1 minuto" if tot == 1 else f"{tot} minuti") if tot < 60 else ("1 ora" if tot == 60
                                                                             else f"{_numero(tot / 60)} ore")


def nome_breve(blocco: str, valori: dict, timeframe: str) -> str:
    """
    Il nome di un blocco con i suoi valori principali, per le tabelle e la lente (L5b, 08/11): «Donchian 12 ore»,
    «RSI 4 ore, soglia 30», «E47 · rottura dopo compressione». Al posto dei nomi temporanei FAB_SES_… del catalogo.
    """
    from .blocchi import FILTRI_CATALOGO, TRIGGER_CATALOGO, USCITE_CATALOGO
    m = MINUTI_TIMEFRAME[timeframe]
    v = valori or {}
    if blocco == "DONCHIAN":
        return f"Donchian {_ore(v['canale_barre'], m)}"
    if blocco == "RSI_RIENTRO":
        return f"RSI {_ore(v['periodo_barre'], m)}, soglia {_numero(v['soglia'])}"
    if blocco == "ADX":
        return f"ADX {_ore(v['periodo_barre'], m)} sopra {_numero(v['soglia'])}"
    if blocco == "ATR_RELATIVO":
        return f"ATR {_ore(v['breve_barre'], m)} / {_ore(v['lungo_barre'], m)} sopra {_numero(v['soglia'])}"
    for catalogo, i in ((TRIGGER_CATALOGO, 2), (FILTRI_CATALOGO, 2), (USCITE_CATALOGO, 2)):
        if blocco in catalogo:
            return f"{blocco} · {catalogo[blocco][i]}"
    return blocco


def regole_in_parole(strategia: Strategia, timeframe: str) -> dict:
    """
    {"ingresso", "filtri", "uscita", "righe"}: le regole della strategia in parole, dal testo di ogni blocco con i
    suoi valori. `righe` sono le frasi della scheda, nell'ordine.
    """
    minuti = MINUTI_TIMEFRAME[timeframe]

    def d(barre):
        return durata(barre, minuti)

    lato = strategia.lato
    nome_lato = "long" if lato == 1 else "short"
    for nome, testi in [(strategia.trigger, TESTI_TRIGGER), *[(f, TESTI_FILTRI) for f in strategia.filtri],
                        (strategia.uscita, TESTI_USCITE)]:
        if nome not in testi:
            raise ValueError(f"il blocco {nome} non ha il testo in parole (schede.py): la scheda non si scrive.")
    ingresso = TESTI_TRIGGER[strategia.trigger](strategia.valori_di(strategia.trigger), d, lato)
    filtri = [TESTI_FILTRI[f](strategia.valori_di(f), d, lato) for f in strategia.filtri]
    u = strategia.valori_di(strategia.uscita)
    n = int(u["durata_barre"])
    finestra = d(barre_da_ore(ORE_FINESTRA_SOGLIE, minuti))
    modi = [f"dopo {d(n)}"]
    regola = TESTI_USCITE[strategia.uscita](lato)
    if regola:
        modi.append(f"quando {regola}")
    if u.get("perc_stop"):
        modi.append(f"allo stop: la distanza che contiene {_il(u['perc_stop'])} delle escursioni contrarie dei "
                    f"trade di {d(n)} delle ultime {finestra}")
    if u.get("target"):
        modi.append(f"al target: la distanza che contiene {_il(u['target'])} delle escursioni favorevoli dei "
                    f"trade di {d(n)} delle ultime {finestra}")
    uscita = ", oppure ".join(modi) + ", quello che arriva prima" + ("" if u.get("target") else "; target spento")
    righe = [f"Entra {nome_lato} all'apertura della barra dopo quella in cui {ingresso}."]
    righe += ([f"Solo se {' e se '.join(filtri)}."] if filtri else ["Nessun filtro."])
    righe.append(f"Esce {uscita}.")
    return {"ingresso": ingresso, "filtri": filtri, "uscita": uscita, "righe": righe}


# ------------------------------------------------------------------ i blocchi tolti
def esclusi_dalla_config(config: dict) -> list[dict]:
    """
    I blocchi di P-L2 che non sono nella config, con il motivo (08/11): quelli tolti sul timeframe hanno il motivo di
    blocchi.MOTIVI_ESCLUSIONE (limite logico, approssimazione esclusa per scelta, escluso solo dall'elenco); gli altri
    sono «tolto dalla config». Sulla config standard è config.blocchi_esclusi(timeframe).
    """
    from .config import BLOCCHI_STANDARD
    tf = config["timeframe"]
    out = []
    for nome in BLOCCHI_STANDARD:
        if nome in config["blocchi"]:
            continue
        tipo, motivo = MOTIVI_ESCLUSIONE.get((nome, tf), (TOLTO_DALLA_CONFIG, "non è nella config di questa ricerca"))
        out.append({"blocco": nome, "tipo": tipo, "motivo": motivo})
    return out


# ------------------------------------------------------------------ la scheda
def _pulito(x):
    """Per il .json: numeri di numpy in numeri di Python, NaN e infiniti in None, tabelle in liste di righe."""
    import numpy as np
    import pandas as pd
    if isinstance(x, pd.DataFrame):
        return [_pulito(r) for r in x.to_dict("records")]
    if isinstance(x, dict):
        return {str(k): _pulito(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_pulito(v) for v in x]
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return float(x) if math.isfinite(float(x)) else None
    if isinstance(x, pd.Timestamp):
        return x.isoformat()
    return x


def commit_software() -> str:
    """Il commit del repo da cui gira il codice; «sconosciuto» se git non c'è (per esempio una copia senza .git)."""
    radice = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=radice, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or "sconosciuto"
    except (OSError, subprocess.SubprocessError):
        return "sconosciuto"


def _riga(tabella, colonna: str, valore) -> dict | None:
    if tabella is None or not len(tabella) or colonna not in tabella.columns:
        return None
    r = tabella[tabella[colonna] == valore]
    return r.iloc[0].to_dict() if len(r) else None


def _altopiano(cartella_ricerca: str, teoria: str, id_strat: str) -> dict | None:
    """Il giudizio dell'altopiano della strategia scelta (passo_2.jsonl della ricerca)."""
    from .ricerca import FILE_PASSO_2, _leggi_jsonl
    for r in _leggi_jsonl(os.path.join(cartella_ricerca, FILE_PASSO_2)):
        if r["teoria"] == teoria:
            for g in r["altopiano"]:
                if g.get("candidata") == id_strat:
                    return g
    return None


def componi_scheda(esito_ricerca, esito_cas, id_strat: str, mm: dict | None = None) -> dict:
    """
    Il contenuto del .json di §6 per una strategia entrata in cassaforte. `esito_ricerca` = ricerca.lancia (finita),
    `esito_cas` = cassaforte.entra o esito_cassaforte, `mm` = il riassunto salvato dalla cella 6 (money management,
    stress test, verifica dei trade), None se la cella 6 non è stata eseguita per questa strategia.
    """
    from .config import impronta_config
    from .dati import impronta_pezzo
    from .selezione import strategia_da_riga
    if id_strat not in esito_cas.trade:
        raise ValueError(f"la strategia {id_strat} non è entrata in cassaforte: niente scheda.")
    config = esito_cas.config
    symbol, timeframe = config["symbol"], config["timeframe"]
    ingresso = next(e for e in esito_cas.ingressi if any(x["id_strategia"] == id_strat for x in e["strategie"]))
    riga = next(x for x in ingresso["strategie"] if x["id_strategia"] == id_strat)
    st = strategia_da_riga(riga, symbol, timeframe)
    teoria = st.teoria_id
    p = esito_cas.pezzo
    impronte = {**esito_cas.pezzi.impronte, "cassaforte": impronta_pezzo(p.df.iloc[p.inizio:])}

    p1 = _riga(esito_ricerca.passo_1, "teoria", teoria) or {}
    p2 = _riga(esito_ricerca.passo_2, "teoria", teoria) or {}
    sel = _riga(esito_ricerca.selezione.tabella, "id_strategia", id_strat) or {}
    cas = _riga(esito_cas.tabella, "id_strategia", id_strat) or {}
    esiti = [
        {"passo": "passo 1", "pezzo": "ricerca", "trade": None, "ev_bp": None, "t": p1.get("t"), "dd_bp": None,
         "condizione": "qualità 1", "esito": "tenuta" if p1.get("tenuta") else "fuori",
         "motivo": f"la migliore della teoria al passo 1 ({p1.get('prove')} prove)"},
        {"passo": "zoom e altopiano", "pezzo": "ricerca", "trade": p2.get("trade"), "ev_bp": p2.get("ev_bp"),
         "t": p2.get("t"), "dd_bp": None, "condizione": "qualità 1 e altopiano", "esito": p2.get("esito"),
         "motivo": p2.get("motivo") or f"{p2.get('prove_zoom')} prove di zoom, {p2.get('prove_altopiano')} di altopiano"},
        {"passo": "selezione", "pezzo": "selezione", "trade": sel.get("trade"), "ev_bp": sel.get("ev_bp"),
         "t": sel.get("t"), "dd_bp": sel.get("dd_bp"), "condizione": "qualità 2 e test individuale",
         "esito": sel.get("esito"), "motivo": sel.get("motivo") or sel.get("motivo_q2") or ""},
        {"passo": "cassaforte", "pezzo": "cassaforte", "trade": cas.get("trade"), "ev_bp": cas.get("ev_bp"),
         "t": cas.get("t"), "dd_bp": cas.get("dd_bp"), "condizione": "test individuale", "esito": cas.get("esito"),
         "motivo": cas.get("motivo") or ""},
    ]
    soglia = cas.get("soglia_test", sel.get("soglia_test"))
    sc = {
        "versione_scheda": VERSIONE_SCHEDA,
        "id_strategia": id_strat, "id_ricerca": esito_ricerca.id_ricerca, "impronta_config": impronta_config(config),
        "impronte_dati": impronte, "symbol": symbol, "timeframe": timeframe,
        "lato": "long" if st.lato == 1 else "short",
        "blocchi": [{"nome": n, "tipo": _tipo(n), "valori": st.valori_di(n)} for n in st.blocchi],
        "uscita": {"nome": st.uscita, **st.valori_di(st.uscita)},
        "regole": regole_in_parole(st, timeframe)["righe"],
        "strategia": {**st.come_dict(), "teoria": teoria},
        "config_strategia": {"symbol": symbol, "timeframe": timeframe, "confini": dict(config["confini"]),
                             "blocchi": {n: config["blocchi"][n] for n in st.blocchi},
                             "test_individuale": dict(config["test_individuale"])},
        "esiti": esiti,
        "altopiano": _altopiano(esito_ricerca.cartella, teoria, p2.get("id_strategia") or id_strat),
        "test_individuale": {"soglia": soglia, "selezione": sel.get("t"), "cassaforte": cas.get("t")},
        "prove": {"questa_ricerca": esito_ricerca.conto.get("questa_ricerca"), "asset": esito_cas.conto.get("asset"),
                  "soglia_da_leggere": esito_cas.conto.get("soglia_da_leggere")},
        "cassaforte": {"data": ingresso.get("quando"), "tratto": esito_cas.tratto, "esito": cas.get("esito"),
                       "entrate_nel_tratto": esito_cas.conto.get("entrate_nel_tratto")},
        "blocchi_esclusi": esclusi_dalla_config(config),
        "mm": (mm or {}).get("mm"), "stress": (mm or {}).get("stress"), "verifica": (mm or {}).get("verifica"),
        "parametri_mm": (mm or {}).get("parametri"),
        "software": commit_software(),
    }
    return _pulito(sc)


def _tipo(nome: str) -> str:
    if nome in TESTI_TRIGGER:
        return "trigger"
    return "uscita" if nome in TESTI_USCITE else "filtro"


# ------------------------------------------------------------------ il testo .md
def _f(x, decimali: int = 2) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    if isinstance(x, bool):
        return "sì" if x else "no"
    if isinstance(x, int):
        return f"{x:,}".replace(",", ".")
    if isinstance(x, float):
        return f"{x:,.{decimali}f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return str(x)


def _tabella_md(righe: list[dict], colonne: list[str] | None = None) -> list[str]:
    if not righe:
        return ["(nessuna riga)"]
    colonne = colonne or list(righe[0])
    out = ["| " + " | ".join(colonne) + " |", "|" + "---|" * len(colonne)]
    for r in righe:
        out.append("| " + " | ".join(_f(r.get(c)).replace("|", "/") for c in colonne) + " |")
    return out


def _quando(iso) -> str:
    """Una data ISO del registro o della scheda in «27/07/2024 08:00 UTC»."""
    if not iso:
        return "—"
    import pandas as pd
    t = pd.Timestamp(iso)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return t.strftime("%d/%m/%Y %H:%M") + " UTC"


def testo_md(sc: dict) -> str:
    """La scheda in parole (§6): Regole · Da dove viene · Il cammino · Da leggere · Verifica, MM e stress test ·
    Blocchi tolti; in fondo la frase finale."""
    t = sc["test_individuale"]
    pr, cas = sc["prove"], sc["cassaforte"]
    da, a = cas["tratto"]["da"], cas["tratto"]["a"]
    righe = [f"# Strategia {sc['id_strategia']} · {sc['symbol']} {sc['timeframe']} · {sc['lato']}", "",
             "## Regole", *[f"- {r}" for r in sc["regole"]], "",
             "## Da dove viene",
             f"- Ricerca {sc['id_ricerca']}, config {sc['impronta_config'][:12]}.",
             f"- Dati: dal {_quando(sc['config_strategia']['confini']['inizio'])}; ricerca "
             f"{_numero(float(sc['config_strategia']['confini']['ricerca_ore']))} ore, selezione "
             f"{_numero(float(sc['config_strategia']['confini']['selezione_ore']))} ore, cassaforte dal {_quando(da)} "
             f"al {_quando(a)}.",
             f"- Software: commit {sc['software']}.", "",
             "## Il cammino",
             *_tabella_md(sc["esiti"], ["passo", "pezzo", "trade", "ev_bp", "t", "dd_bp", "esito", "motivo"]),
             "",
             f"Decide il test individuale: t contro {_f(t['soglia'])}. In selezione t {_f(t['selezione'])}, in "
             f"cassaforte t {_f(t['cassaforte'])}.", "",
             "## Da leggere",
             f"- Prove di questa ricerca: {_f(pr['questa_ricerca'])}; su questo asset: {_f(pr['asset'])}; soglia "
             f"corrispondente: {_f(pr['soglia_da_leggere'])}.",
             f"- Strategie entrate in questo tratto di cassaforte: {_f(cas['entrate_nel_tratto'])} (entrata il "
             f"{_quando(cas['data'])}).", ""]
    righe.append("## Verifica dei trade")
    if sc.get("verifica"):
        righe += _tabella_md(sc["verifica"]["regole"])
    else:
        righe.append("Non calcolata: esegui la 6 per questa strategia.")
    righe += ["", "## Money management e stress test"]
    if sc.get("mm"):
        par = sc.get("parametri_mm") or {}
        righe += [f"Capitale {_f(par.get('capitale'))} $, drawdown massimo {_f(par.get('drawdown_max_pct'))} %, "
                  f"{_numero(par.get('anni') or 0)} anni, modello «{sc['mm'].get('modello')}», leva "
                  f"{_numero(par['leva']) if par.get('leva') else 'la massima del symbol'}.",
                  f"Rischio a ogni trade: {_f((sc['mm'].get('percentuale') or 0) * 100)} %. "
                  f"{sc['mm'].get('deciso') or ''}", ""]
        righe += _tabella_md(sc["mm"].get("sintesi") or [])
        if sc.get("stress"):
            righe += ["", f"Stress test (drawdown massimo {_f(sc['stress'].get('drawdown_max_usd'))} $, in "
                          f"{sc['stress'].get('unita')}):", ""]
            righe += _tabella_md(sc["stress"].get("controllo") or [])
    else:
        righe.append("Non calcolati: esegui la 6 per questa strategia.")
    righe += ["", "## Blocchi tolti su questo timeframe"]
    if sc["blocchi_esclusi"]:
        righe += [f"- {e['blocco']} ({e['tipo']}): {e['motivo']}." for e in sc["blocchi_esclusi"]]
    else:
        righe.append("Nessuno: c'erano tutti i blocchi della lista.")
    righe += ["", FRASE_FINALE, ""]
    return "\n".join(righe)


# ------------------------------------------------------------------ scrivere e leggere
def scrivi_scheda(sc: dict, cartella) -> tuple[str, str]:
    """Scrive <cartella>/<id_strategia>.md e .json (riscritti se ci sono già: la scheda viene dai calcoli)."""
    os.makedirs(str(cartella), exist_ok=True)
    base = os.path.join(str(cartella), sc["id_strategia"])
    testo_json = json.dumps(sc, ensure_ascii=False, indent=2, sort_keys=False, allow_nan=False,
                            default=registro.nativo)
    for percorso, testo in ((base + ".json", testo_json + "\n"), (base + ".md", testo_md(sc))):
        with open(percorso + ".tmp", "w", encoding="utf-8") as f:
            f.write(testo)
        os.replace(percorso + ".tmp", percorso)
    return base + ".md", base + ".json"


def leggi_scheda(percorso) -> dict:
    """Il dizionario di una scheda .json (o del .json accanto a un .md)."""
    percorso = str(percorso)
    if percorso.endswith(".md"):
        percorso = percorso[:-3] + ".json"
    with open(percorso, encoding="utf-8") as f:
        sc = json.load(f)
    if sc.get("versione_scheda") != VERSIONE_SCHEDA:
        raise ValueError(f"{percorso}: versione della scheda {sc.get('versione_scheda')!r}, attesa {VERSIONE_SCHEDA}.")
    return sc


def strategia_da_scheda(sc: dict) -> Strategia:
    """La strategia dalla sola scheda: si ferma se l'id non torna dai valori scritti."""
    s = sc["strategia"]
    st = Strategia(int(s["lato"]), s["trigger"], tuple(s["filtri"]), s["uscita"],
                   tuple((n, tuple(sorted(s["valori"].get(n, {}).items()))) for n in (s["trigger"], *s["filtri"],
                                                                                        s["uscita"])))
    if id_strategia(st, sc["symbol"], sc["timeframe"]) != sc["id_strategia"]:
        raise ValueError(f"la scheda {sc['id_strategia']}: la strategia non torna dai suoi valori.")
    return st


def trade_da_scheda(sc: dict, cartella_dati) -> dict:
    """
    I trade della strategia rifatti dalla sola scheda (P10): {"in_sample": trade su ricerca + selezione,
    "cassaforte": trade sulla cassaforte}. Servono i CSV del symbol; si ferma se le impronte dei pezzi non sono quelle
    della scheda o se la strategia non è entrata nel tratto di cassaforte della scheda.
    """
    from .blocchi import blocchi_da_config
    from .cassaforte import trade_entrata
    from .dati import APERTI, Confini, carica_pezzi
    from .sessione import in_sample
    st = strategia_da_scheda(sc)
    config = sc["config_strategia"]
    riga = {"teoria": st.teoria_id, "valori": {n: dict(v) for n, v in st.valori}, "id_strategia": sc["id_strategia"]}
    trade_cas, impronte = trade_entrata(cartella_dati, config, riga, sc["impronte_dati"])
    pezzi = carica_pezzi(config["symbol"], config["timeframe"], Confini.da_config(config["confini"]), cartella_dati)
    if {k: pezzi.impronte[k] for k in APERTI} != {k: impronte[k] for k in APERTI}:
        raise ValueError("i dati sono cambiati fra due letture: i trade non si rifanno.")
    ins = in_sample(config, pezzi, st, {b.nome: b for b in blocchi_da_config(config)})
    return {"in_sample": ins.trades, "cassaforte": trade_cas}


# controlli di coerenza dei testi, usati dai collaudi
def blocchi_senza_testo() -> list[str]:
    """I blocchi senza testo in parole (deve essere vuota): quelli di P-L2 e, dal 12/11 (C1), tutto il catalogo."""
    from .blocchi import CALCOLI_NUOVI, FILTRI_CATALOGO, TRIGGER_CATALOGO, USCITE_CATALOGO
    from .config import BLOCCHI_STANDARD
    testi = {**TESTI_TRIGGER, **TESTI_FILTRI, **TESTI_USCITE}
    tutti = dict.fromkeys((*BLOCCHI_STANDARD, *TRIGGER_CATALOGO, *FILTRI_CATALOGO, *CALCOLI_NUOVI, *USCITE_CATALOGO))
    return [n for n in tutti if n not in testi]

