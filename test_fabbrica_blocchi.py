"""
Suite di collaudo dei blocchi e della cache della fabbrica (docs/82 P-L2, lavoro L2).

Si lancia da terminale, dalla cartella del progetto:

    python test_fabbrica_blocchi.py

Solo dati sintetici: non servono i file in dati/, MetaTrader 5 o internet.
Stampa una riga per collaudo e alla fine «RISULTATO: n/n test superati».
"""
from __future__ import annotations

import contextlib
import inspect
import io
import itertools
import sys
import time
import warnings

import numpy as np
import pandas as pd
import talib

import entry_long
import entry_short
import exit_long
import exit_short
import filter_conditions
import vwap_regime_filter_conditions
from engine import registry as reg
from engine.collaudo_catalogo import verifica_degenerazione, verifica_lookahead
from engine.exit_search_bt import soglie_adattive
from engine.fabbrica.blocchi import (APPROSSIMAZIONE_ESCLUSA, BARRE_MINIME, FILTRI_CATALOGO, GRIGLIE_NUOVI, LIMITE_LOGICO,
                                     MINUTI_TIMEFRAME, MOTIVI_ESCLUSIONE, SOLO_ELENCO, TRIGGER_CATALOGO, USCITE_CATALOGO,
                                     Blocco, _registra_catalogo, blocchi_da_config)
from engine.fabbrica.cache import ORE_FINESTRA_SOGLIE, Cache, barre_da_ore
from engine.fabbrica.dati import imposta_mercato_crypto
from engine.fabbrica.ottimizzatore import Categoria, Intero, Reale
from engine.indicatori import aggiungi_indicatori, atr_relativo, donchian_massimo, donchian_minimo, indice_choppiness
from helpers import _cross_down, _cross_up, _evento

warnings.simplefilter("ignore")

PREFISSO = "PROVA_FAB_"
NUOVI = tuple(GRIGLIE_NUOVI)
# I 10 blocchi del catalogo di P-L2 (fino all'11/11): i collaudi di L2 restano su questi. Il catalogo intero (C1, 12/11)
# ha la sua sezione in fondo.
ORIGINALI_TRIGGER = ("E5", "E36", "E47", "E49", "E51")
ORIGINALI_FILTRI = ("F2_MID_VOLATILITY", "F3_VOLUME_ABOVE_AVG", "TREND_CONTEXT", "F25_CHOP_TREND", "F20_SESSION_OVERLAP")
TUTTI_CATALOGO = (*ORIGINALI_TRIGGER, *ORIGINALI_FILTRI, *USCITE_CATALOGO)
L, A, S = LIMITE_LOGICO, APPROSSIMAZIONE_ESCLUSA, SOLO_ELENCO
# C1: la tabella D4 di docs/82 §11.12 (approvata da Mattia il 12/11 sera) più le esclusioni dell'08/11:
# (blocco, timeframe) -> tipo di motivo. Ogni altra coppia (blocco del catalogo, timeframe) è ammessa.
ESCLUSI_ATTESI = {
    **{("E36", tf): L for tf in ("H1", "H4", "D1")},
    ("E47", "M1"): S, ("E47", "M30"): A, **{("E47", tf): L for tf in ("H1", "H4", "D1")},
    ("E49", "M1"): S, **{("E49", tf): L for tf in ("H4", "D1")},
    ("E51", "M1"): S, ("E51", "H4"): A, ("E51", "D1"): L,
    ("F20_SESSION_OVERLAP", "D1"): L,
    ("E22", "H4"): A, ("E22", "D1"): L, ("E23", "D1"): L,
    ("E31", "H1"): A, ("E31", "H4"): L, ("E31", "D1"): L,
    **{("E37", tf): L for tf in ("H1", "H4", "D1")},
    **{(b, tf): L for b in ("E38", "E39") for tf in ("H4", "D1")},
    **{("E40", tf): L for tf in ("H1", "H4", "D1")},
    ("E41", "D1"): L, ("E45", "D1"): L,
    ("E46", "M1"): S, ("E46", "M30"): A, **{("E46", tf): L for tf in ("H1", "H4", "D1")},
    ("E48", "M1"): S, **{("E48", tf): L for tf in ("M30", "H1", "H4", "D1")},
    ("E52", "M1"): S, ("E52", "H1"): A, ("E52", "H4"): A, ("E52", "D1"): L,
    **{(f, "D1"): L for f in ("F20_SESSION_ASIA", "F20_SESSION_EUROPE", "F20_SESSION_US", "F22_FAR_FROM_ROLLOVER",
                              "VWAP_GAP_WIDENING", "VWAP_SESSION_CLOSE")},
    ("OVERNIGHT_RETURN", "H4"): A, ("OVERNIGHT_RETURN", "D1"): L,
}
# Ammessi ma muti sui dati del collaudo (9.000 barre, 30.000 su M1), per la lunghezza dei dati e non per la regola: E19 è
# una figura rara (compare solo sulle 30.000 barre di M1); E40, E41 ed E45 chiedono 250, 300 e 365 giornate di storia.
# Sui dati veri li toglie, dove serve, il controllo dei degeneri a ogni avvio (docs/82 §11.12, deciso il 12/11 sera).
NON_SCATTANO_SUL_COLLAUDO = {*(("E19", tf) for tf in ("M5", "M15", "M30", "H1", "H4", "D1")),
                             *((b, tf) for b in ("E40", "E41") for tf in ("M1", "M5", "M15", "M30")),
                             *(("E45", tf) for tf in ("M1", "M5", "M15", "M30", "H1"))}


def _indice(n: int, minuti: int = 15, inizio: str = "2024-01-01") -> pd.DatetimeIndex:
    return pd.date_range(inizio, periods=n, freq=f"{minuti}min", tz="UTC")


def _mercato(n: int = 12_000, seme: int = 0, minuti: int = 15) -> pd.DataFrame:
    """Prezzi a regimi (tendenza, volatilità) con volume che segue la volatilità: i blocchi trovano i loro casi."""
    r = np.random.default_rng(seme)
    drift, vol, i = np.zeros(n), np.zeros(n), 0
    while i < n:
        lung = int(r.integers(40, 400))
        drift[i: i + lung] = r.choice((-1.0, 0.0, 1.0), p=(0.3, 0.4, 0.3)) * r.uniform(0.0002, 0.0012)
        vol[i: i + lung] = r.choice((0.0008, 0.0016, 0.0040), p=(0.4, 0.4, 0.2))
        i += lung
    rendimenti = drift + vol * r.standard_normal(n)

    def tick(x):   # prezzi a 1/64: esatti in binario, così lo specchio K - x non aggiunge errori di arrotondamento
        return np.round(np.asarray(x) * 64.0) / 64.0

    c = tick(100.0 * np.exp(np.cumsum(rendimenti - rendimenti.mean())))
    o = tick(np.r_[c[0], c[:-1]] + 0.1 * vol * c * r.standard_normal(n))
    ampiezza = np.abs(r.standard_normal(n)) * vol * c * 0.8 + 1.0 / 64.0
    h = tick(np.maximum(o, c) + ampiezza)
    l = tick(np.minimum(o, c) - ampiezza * r.uniform(0.5, 1.5, n))
    volume = np.round(1000.0 * (vol / 0.001) * r.lognormal(0.0, 0.5, n), 2)
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": volume}, index=_indice(n, minuti))


def _specchio(df: pd.DataFrame, centro: float) -> pd.DataFrame:
    """Il mercato rovesciato: ogni salita diventa una discesa della stessa ampiezza. Il volume resta."""
    k = 2.0 * centro
    return pd.DataFrame({"Open": k - df["Open"], "High": k - df["Low"], "Low": k - df["High"], "Close": k - df["Close"],
                         "Volume": df["Volume"]}, index=df.index)


def _specchio_proporzionale(df: pd.DataFrame, k: float) -> pd.DataFrame:
    """Il mercato rovesciato in proporzione, K / prezzo: ogni rendimento logaritmico cambia segno esatto."""
    return pd.DataFrame({"Open": k / df["Open"], "High": k / df["Low"], "Low": k / df["High"], "Close": k / df["Close"],
                         "Volume": df["Volume"]}, index=df.index)


def _corta() -> pd.DataFrame:
    """La serie corta dei conti a mano."""
    return pd.DataFrame({"Open": [9.0, 9.5, 10.5, 11.5, 11.0, 12.5], "High": [10.0, 11.0, 12.0, 11.5, 13.0, 12.5],
                         "Low": [9.0, 10.0, 10.5, 10.5, 11.5, 11.0], "Close": [9.5, 10.5, 11.5, 11.0, 12.5, 11.5],
                         "Volume": [1.0] * 6}, index=_indice(6))


def _config(*nomi, timeframe="M15") -> dict:
    return {"timeframe": timeframe, "blocchi": {n: {} for n in nomi}}


def _uno(nome: str, timeframe="M15", **griglie) -> Blocco:
    return blocchi_da_config({"timeframe": timeframe, "blocchi": {nome: griglie}})[0]


def _combinazioni(b: Blocco, tutte: bool = False) -> list[dict]:
    """Estremi e centro di ogni parametro, tutte le combinazioni; con tutte=True, l'intera griglia."""
    assi = []
    for nome, valori in b.griglia.items():
        scelti = valori if tutte else dict.fromkeys((valori[0], valori[len(valori) // 2], valori[-1]))
        assi.append([(nome, v) for v in scelti])
    return [dict(c) for c in itertools.product(*assi)]


def _etichetta(b: Blocco, valori: dict, lato=None) -> str:
    resto = "_".join(f"{k}{v}" for k, v in valori.items())
    return f"{PREFISSO}{b.nome}_{resto}" + ("" if lato is None else ("_L" if lato == 1 else "_S"))


def _registra_nuovi(timeframe: str = "M15", tutte: bool = False) -> list[str]:
    """I blocchi nuovi come condizioni del registro, agli estremi e al centro (o tutta la griglia): così passano dai collaudi del catalogo."""
    reg.clear_registry()
    nomi = []
    for b in blocchi_da_config(_config(*NUOVI, timeframe=timeframe)):
        for valori in _combinazioni(b, tutte):
            if b.tipo == "trigger":
                for lato in (1, -1):
                    nome = _etichetta(b, valori, lato)
                    reg.register_entry(nome, direction=lato)(
                        lambda df, _b=b, _v=valori, _l=lato: pd.Series(_b.maschera(Cache(df, 20), _l, _v), index=df.index))
                    nomi.append(nome)
            else:
                nome = _etichetta(b, valori)
                reg.register_filter(nome)(
                    lambda df, _b=b, _v=valori: pd.Series(_b.maschera(Cache(df, 20), 1, _v), index=df.index))
                nomi.append(nome)
    return nomi


def esegui() -> int:
    ESITI = []
    t0 = time.perf_counter()

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        print(f"[{'OK ' if condizione else 'KO '}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""), flush=True)

    def errore(f) -> bool:
        try:
            f()
        except ValueError:
            return True
        return False

    # ------------------------------------------------------------------ ore e barre
    print("Ore e barre")
    check("1. M15: 1 ora = 4 barre, 9 ore = 36", barre_da_ore(1, 15) == 4 and barre_da_ore(9, 15) == 36)
    check("2. H1: 1 ora = 1 barra, 9 ore = 9", barre_da_ore(1, 60) == 1 and barre_da_ore(9, 60) == 9)
    check("3. M5 e M30: 1 ora = 12 e 2 barre", barre_da_ore(1, 5) == 12 and barre_da_ore(1, 30) == 2)
    check("4. ore zero o negative non sono una durata: errore", errore(lambda: barre_da_ore(0, 15)) and errore(lambda: barre_da_ore(-1, 15))
          and errore(lambda: barre_da_ore(float("nan"), 15)))
    rsi_m15, rsi_h1 = _uno("RSI_RIENTRO"), _uno("RSI_RIENTRO", "H1")
    check("5. stesso blocco, M15 e H1: griglia convertita", rsi_m15.griglia["periodo_barre"] == (8, 16, 24, 36, 48)
          and rsi_h1.griglia["periodo_barre"] == (5, 6, 9, 12))
    check("6. arrotonda alla barra più vicina, a metà verso l'alto, minimo 1", barre_da_ore(9, 240) == 2 and barre_da_ore(6, 240) == 2
          and barre_da_ore(10, 240) == 3 and barre_da_ore(11, 240) == 3 and barre_da_ore(2, 240) == 1 and barre_da_ore(0.1, 15) == 1
          and barre_da_ore(1, 1440) == 1 and barre_da_ore(96, 1440) == 4)
    check("7. ore frazionarie: stesse barre di prima dove erano intere", _uno("DONCHIAN", canale_ore=(1.25, 3.5)).griglia["canale_barre"] == (5, 14))
    check("8. la finestra delle soglie è di 125 ore: 500 barre su M15, 125 su H1, 1500 su M5, 7500 su M1, 31 su H4, 5 su D1", ORE_FINESTRA_SOGLIE == 125
          and [barre_da_ore(ORE_FINESTRA_SOGLIE, m) for m in (15, 60, 5, 1, 240, 1440)] == [500, 125, 1500, 7500, 31, 5])

    # ------------------------------------------------------------------ la forma dei blocchi
    print("\nLa forma dei blocchi")
    tutti = blocchi_da_config(_config(*TUTTI_CATALOGO, *NUOVI))      # i blocchi di P-L2
    check("9. 7 trigger, 7 filtri, 3 uscite", [sum(b.tipo == t for b in tutti) for t in ("trigger", "filtro", "uscita")] == [7, 7, 3])
    check("10. ogni blocco ha nome, tipo, famiglia", all(isinstance(b, Blocco) and b.nome and b.tipo and b.famiglia for b in tutti))
    tipi_ok = all(isinstance(p, (Intero, Reale, Categoria)) for b in tutti for p in b.parametri)
    in_griglia = all(any(abs(p.valore(i) - v) < 1e-9 for i in range(p.n)) for b in tutti for p in b.parametri
                     if not isinstance(p, Categoria) for v in b.griglia[p.nome])
    check("11. i parametri sono tipi dell'ottimizzatore e contengono i valori del passo 1", tipi_ok and in_griglia)
    u = _uno("X3")
    check("12. uscita: durata in barre, percentile, target spento o 90", u.griglia == {"durata_barre": (4, 8, 16, 32),
          "perc_stop": (70, 80, 90, 95), "target": (None, 90)} and isinstance(u.parametri[0], Intero)
          and isinstance(u.parametri[2], Categoria))
    check("13. i parametri in ore sono Intero in barre", all(isinstance(p, Intero) for b in tutti for p in b.parametri
                                                              if p.nome.endswith("_barre")))
    check("14. il catalogo non ha parametri", all(not b.parametri for b in blocchi_da_config(_config(*TRIGGER_CATALOGO, *FILTRI_CATALOGO))))
    check("15. blocco sconosciuto, parametro sconosciuto, parametri al catalogo: errore", errore(lambda: _uno("E99"))
          and errore(lambda: _uno("ADX", finto_ore=(1,))) and errore(lambda: _uno("E47", periodo_ore=(1,))))
    check("16. catalogo su un timeframe dove non scatta: errore", errore(lambda: _uno("E47", "H1"))
          and errore(lambda: _uno("E36", "H1")) and errore(lambda: _uno("E49", "D1")) and _uno("E49", "H1").nome == "E49")
    df = _mercato(3000)
    c = Cache(df, 50)
    b = _uno("ADX")
    check("17. valori sbagliati, lato sbagliato: errore", errore(lambda: b.maschera(c, 1, {"soglia": 20}))
          and errore(lambda: b.maschera(c, 0, b.centrali())) and errore(lambda: b.maschera(c, 1, {"periodo_barre": 5.5, "soglia": 20}))
          and errore(lambda: b.maschera(c, 1, {"periodo_barre": 1, "soglia": 20})))

    # ------------------------------------------------------------------ i conti a mano
    nan = float("nan")
    # controprove con cicli semplici, barra per barra, su una serie più lunga
    lungo = _mercato(800, seme=3)
    h, l, cl = (lungo[k].to_numpy(float) for k in ("High", "Low", "Close"))

    def adx_a_mano(n):
        out, pdi, mdi, trs, somma, conta = [nan] * len(cl), 0.0, 0.0, 0.0, 0.0, 0
        adx = None
        for i in range(1, len(cl)):
            su, giu = h[i] - h[i - 1], l[i - 1] - l[i]
            piu = su if su > 0 and su > giu else 0.0
            meno = giu if giu > 0 and giu > su else 0.0
            tr = max(h[i] - l[i], abs(h[i] - cl[i - 1]), abs(l[i] - cl[i - 1]))
            if i < n:
                pdi, mdi, trs = pdi + piu, mdi + meno, trs + tr
                continue
            pdi, mdi, trs = pdi - pdi / n + piu, mdi - mdi / n + meno, trs - trs / n + tr
            dx = 100.0 * abs(pdi - mdi) / (pdi + mdi) if pdi + mdi > 0 else 0.0
            if adx is None:
                somma += dx
                conta += 1
                if conta == n:
                    adx = somma / n
                    out[i] = adx
            else:
                adx = (adx * (n - 1) + dx) / n
                out[i] = adx
        return np.array(out)

    def rsi_a_mano(n):
        out, g, p = [nan] * len(cl), 0.0, 0.0
        for i in range(1, len(cl)):
            d_ = cl[i] - cl[i - 1]
            su, giu = max(d_, 0.0), max(-d_, 0.0)
            if i <= n:
                g, p = g + su / n, p + giu / n
                if i == n:
                    out[i] = 100.0 * g / (g + p)
            else:
                g, p = (g * (n - 1) + su) / n, (p * (n - 1) + giu) / n
                out[i] = 100.0 * g / (g + p)
        return np.array(out)

    def atr_a_mano(n):
        out, atr = [nan] * len(cl), 0.0
        for i in range(1, len(cl)):
            tr = max(h[i] - l[i], abs(h[i] - cl[i - 1]), abs(l[i] - cl[i - 1]))
            if i <= n:
                atr += tr / n
                if i == n:
                    out[i] = atr
            else:
                atr = (atr * (n - 1) + tr) / n
                out[i] = atr
        return np.array(out)

    def donchian_a_mano(n):
        return np.array([nan if i < n else h[i - n: i].max() for i in range(len(h))]), np.array([nan if i < n else l[i - n: i].min() for i in range(len(l))])

    print("\nI conti a mano (M15)")
    corta = _corta()
    c = Cache(corta, 5)
    def vicini(a, attesi):
        return all((np.isnan(x) and np.isnan(y)) or abs(x - y) < 1e-3 for x, y in zip(a, attesi)) and len(a) == len(attesi)
    check("18. RSI a 2 barre", vicini(c.indicatore("rsi", barre=2), [nan, nan, 100.0, 66.667, 88.889, 47.059]))
    check("19. ATR a 2 barre", vicini(c.indicatore("atr", barre=2), [nan, nan, 1.5, 1.25, 1.625, 1.5625]))
    check("20. ADX a 2 barre", vicini(c.indicatore("adx", barre=2), [nan, nan, nan, 100.0, 100.0, 65.217]))
    check("21. ATR relativo 2 su 3", vicini(c.indicatore("atr_relativo", breve=2, lungo=3), [nan, nan, nan, 0.9375, 1.04464, 1.01657]))
    check("22. Donchian a 2 barre: massimi e minimi precedenti", vicini(c.indicatore("donchian_massimo", barre=2), [nan, nan, 11.0, 12.0, 12.0, 13.0])
          and vicini(c.indicatore("donchian_minimo", barre=2), [nan, nan, 9.0, 10.0, 10.5, 10.5]))
    d = _uno("DONCHIAN", canale_ore=(0.5,))
    m = d.maschera(c, 1, {"canale_barre": 2})
    check("23. Donchian long: segnali alle barre attese", m.tolist() == [False, False, True, False, True, False])
    check("24. la barra corrente fa il massimo e dà segnale: High 13, Close 12,5, massimo prima 12",
          bool(m[4]) and corta["High"].iloc[4] == corta["High"].max() and corta["Close"].iloc[4] < corta["High"].iloc[4])
    check("25. Donchian short: chiusura sotto il minimo precedente", d.maschera(c, -1, {"canale_barre": 2}).tolist()
          == [False] * 6)
    # RSI a 5 barre, a mano. Cinque salite di 1: guadagno medio 1, perdita media 0, RSI 100 alla barra 5. Poi, con la media
    # di Wilder: discesa 0,8/0,2 = 80; discesa 0,64/0,36 = 64; discesa 0,512/0,488 = 51,2; salita 0,6096/0,3904 = 60,96.
    chiusure = np.array([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 14.0, 13.0, 12.0, 13.0])
    c_rsi = Cache(pd.DataFrame({"Open": chiusure, "High": chiusure + 0.5, "Low": chiusure - 0.5, "Close": chiusure, "Volume": 1.0}, index=_indice(10)), 5)
    r = _uno("RSI_RIENTRO")
    check("26. RSI rientro short a 5 barre: scende sotto 100 - 30 da sopra, alla barra 7 (80, poi 64)", r.maschera(c_rsi, -1, {"periodo_barre": 5, "soglia": 30}).tolist()
          == [False] * 7 + [True, False, False] and vicini(c_rsi.indicatore("rsi", barre=5), [nan] * 5 + [100.0, 80.0, 64.0, 51.2, 60.96]))
    check("27. RSI rientro long a 5 barre: risale sopra 55 da sotto, alla barra 9 (51,2, poi 60,96)", r.maschera(c_rsi, 1, {"periodo_barre": 5, "soglia": 55}).tolist()
          == [False] * 9 + [True])
    c_lungo = Cache(lungo, 20)
    a = _uno("ADX")
    atteso = adx_a_mano(5) > 40
    m = a.maschera(c_lungo, 1, {"periodo_barre": 5, "soglia": 40})
    check("28. filtro ADX a 5 barre = ciclo a mano: stato, non evento; NaN = falso", (m == atteso).all() and 0 < m.sum() < len(m)
          and (m[:-1] & m[1:]).any() and not m[:9].any())
    t = _uno("ATR_RELATIVO")
    atteso = atr_a_mano(2) / atr_a_mano(5) > 1.0
    m = t.maschera(c_lungo, 1, {"breve_barre": 2, "lungo_barre": 5, "soglia": 1.0})
    check("29. filtro ATR relativo 2 su 5 = ciclo a mano: stato; NaN = falso", (m == atteso).all() and 0 < m.sum() < len(m)
          and (m[:-1] & m[1:]).any() and not m[:5].any())

    c = Cache(lungo, 20)
    uguali = lambda a, b_: np.allclose(a, b_, rtol=1e-8, atol=1e-8, equal_nan=True)
    check("30. RSI a 14 barre = ciclo a mano", uguali(c.indicatore("rsi", barre=14), rsi_a_mano(14)))
    check("31. ATR a 14 barre = ciclo a mano", uguali(c.indicatore("atr", barre=14), atr_a_mano(14)))
    check("32. ADX a 9 barre = ciclo a mano", uguali(c.indicatore("adx", barre=9), adx_a_mano(9)))
    alti, bassi = donchian_a_mano(16)
    check("33. Donchian a 16 barre = ciclo a mano", uguali(c.indicatore("donchian_massimo", barre=16), alti)
          and uguali(c.indicatore("donchian_minimo", barre=16), bassi))
    check("34. ATR relativo = ATR breve / ATR lungo", uguali(c.indicatore("atr_relativo", breve=8, lungo=24),
          atr_a_mano(8) / atr_a_mano(24)))

    # ------------------------------------------------------------------ come il catalogo
    print("\nEventi e stati, come il catalogo")
    df = _mercato()
    c = Cache(df, 200)
    serie = pd.Series(c.indicatore("rsi", barre=24), index=df.index)
    rsi_b, don = _uno("RSI_RIENTRO"), _uno("DONCHIAN")
    v = {"periodo_barre": 24, "soglia": 25}
    check("35. RSI rientro = _cross_up e _cross_down di helpers", (rsi_b.maschera(c, 1, v) == _cross_up(serie, pd.Series(25.0, index=df.index)).to_numpy()).all()
          and (rsi_b.maschera(c, -1, v) == _cross_down(serie, pd.Series(75.0, index=df.index)).to_numpy()).all())
    v = {"canale_barre": 96}
    atteso = _evento(df["Close"] > df["High"].rolling(96).max().shift(1)).to_numpy()
    check("36. Donchian = _evento di helpers", (don.maschera(c, 1, v) == atteso).all())
    stati = (don.maschera(c, 1, v) & np.r_[False, don.maschera(c, 1, v)[:-1]]).sum() + (rsi_b.maschera(c, 1, {"periodo_barre": 24, "soglia": 25})
             & np.r_[False, rsi_b.maschera(c, 1, {"periodo_barre": 24, "soglia": 25})[:-1]]).sum()
    check("37. i trigger nuovi sono eventi: mai due barre vere di fila", stati == 0)
    f = _uno("ADX").maschera(c, 1, {"periodo_barre": 24, "soglia": 20})
    check("38. i filtri nuovi sono stati: barre vere di fila", (f & np.r_[False, f[:-1]]).sum() > 0)
    check("39. i filtri nuovi non dipendono dal lato", (f == _uno("ADX").maschera(c, -1, {"periodo_barre": 24, "soglia": 20})).all())
    solo_prezzi = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    avvelenato = solo_prezzi.assign(funding=np.random.default_rng(1).random(len(df)), basis_bp=1.0)
    uguali_v = all((b_.maschera(Cache(solo_prezzi, 10), l_, x) == b_.maschera(Cache(avvelenato, 10), l_, x)).all()
                   for b_ in blocchi_da_config(_config(*NUOVI)) for l_ in (1, -1) for x in [b_.centrali()])
    check("40. i blocchi nuovi girano con solo OHLCV; funding e basis nel df non cambiano nulla", uguali_v)

    # ------------------------------------------------------------------ i blocchi del catalogo
    print("\nI blocchi del catalogo = le condizioni del catalogo")
    reg.clear_registry()
    grezzo = _mercato(6000, seme=1)
    df_ind = aggiungi_indicatori(grezzo)
    c = Cache(df_ind, 200)
    pulito = lambda s: (s.fillna(False).astype(bool) if s.dtype != bool else s).to_numpy()
    con = {**entry_long.TRIGGER_LONG, **entry_short.TRIGGER_SHORT, **{k: v[0] for k, v in filter_conditions.FILTRI.items()},
           **{k: v[0] for k, v in exit_long.EXIT_LONG.items()}, **{k: v[0] for k, v in exit_short.EXIT_SHORT.items()}}
    tot, diversi, mai = 0, [], []
    for b in blocchi_da_config(_config(*TUTTI_CATALOGO)):
        for lato, nome in zip((1, -1), b._catalogo):
            valori = b.centrali() if b.parametri else None
            mascherata = b.maschera(c, lato, valori)
            tot += 1
            if not (mascherata == pulito(con[nome](df_ind))).all():
                diversi.append(nome)
            if not mascherata.any() and b.nome != "X0":
                mai.append(nome)
    check("41. ogni blocco del catalogo dà la stessa maschera della condizione", not diversi and tot == 26, f"{tot} confronti {diversi}")
    check("42. e sui dati del collaudo ogni condizione scatta (X0 per costruzione no)", not mai, str(mai))
    nomi_catalogo = set(entry_long.TRIGGER_LONG) | set(entry_short.TRIGGER_SHORT)
    check("43. il registro contiene solo le condizioni dei dizionari", set(reg.list_entries()) == nomi_catalogo)
    check("44. il blocco legge dal registro: la condizione è quella registrata", reg.get_entry("E5_QUICK_PULLBACK") is entry_long.entry_quick_pullback)
    reg.clear_registry()
    ricaricata = _uno("E5").maschera(Cache(df_ind, 1), 1)
    check("45. a registro vuoto si ricarica da solo", "E5_QUICK_PULLBACK" in reg.list_entries()
          and (ricaricata == pulito(entry_long.entry_quick_pullback(df_ind))).all())

    # ------------------------------------------------------------------ specchio
    print("\nLo short è lo specchio del long")
    centro = float(grezzo["Close"].max()) + 1.0
    specchio = _specchio(grezzo, centro)
    df_spe = aggiungi_indicatori(specchio)
    cm = Cache(df_spe, 200)
    check("46. lo specchio rovescia i prezzi e tiene le barre", df_spe.index.equals(df_ind.index) and (specchio["High"] >= specchio["Low"]).all()
          and (specchio["Close"] > 0).all())
    for b in blocchi_da_config(_config(*NUOVI)):
        scarti = 0
        # stesso df base degli indicatori: confronto su tutte le barre del df grezzo
        ca, cb = Cache(grezzo, 200), Cache(specchio, 200)
        for valori in _combinazioni(b):
            scarti += int((b.maschera(ca, 1, valori) != b.maschera(cb, -1, valori)).sum())
            if not b.neutro:
                scarti += int((b.maschera(ca, -1, valori) != b.maschera(cb, 1, valori)).sum())
        check(f"47. {b.nome}: maschera long sul mercato = maschera short sullo specchio", scarti == 0, f"{scarti} barre diverse")
    for nome in (*ORIGINALI_TRIGGER, *ORIGINALI_FILTRI):
        b = _uno(nome)
        scarti = int((b.maschera(c := Cache(df_ind, 50), 1) != b.maschera(cm, -1)).sum()) + int((b.maschera(c, -1) != b.maschera(cm, 1)).sum())
        check(f"48. {nome}: specchio", scarti == 0, f"{scarti} barre diverse su {len(df_ind)}")
    for nome in ("X0", "X3"):
        b = _uno(nome)
        v = b.centrali()
        scarti = int((b.maschera(Cache(df_ind, 50), 1, v) != b.maschera(cm, -1, v)).sum())
        check(f"49. uscita {nome}: specchio", scarti == 0, f"{scarti} barre diverse su {len(df_ind)}")
    # X1 lavora sui rendimenti logaritmici: il suo specchio è quello in proporzione, K / prezzo
    df_pro = aggiungi_indicatori(_specchio_proporzionale(grezzo, 10_000.0))
    b = _uno("X1")
    v = b.centrali()
    scarti = int((b.maschera(Cache(df_ind, 50), 1, v) != b.maschera(Cache(df_pro, 50), -1, v)).sum())
    check("50. uscita X1: specchio in proporzione, perché lavora sui rendimenti logaritmici", scarti == 0 and df_pro.index.equals(df_ind.index),
          f"{scarti} barre diverse su {len(df_ind)}")

    # ------------------------------------------------------------------ la cache
    print("\nLa cache")
    df = _mercato()
    grande, zero, stretta = Cache(df, 500), Cache(df, 0), Cache(df, 1)
    valori_tutti = [(b, l_, x) for b in blocchi_da_config(_config(*NUOVI)) for x in _combinazioni(b) for l_ in (1, -1)]
    diversi = sum(not (b.maschera(grande, l_, x) == b.maschera(zero, l_, x)).all()
                  or not (b.maschera(grande, l_, x) == b.maschera(stretta, l_, x)).all() for b, l_, x in valori_tutti)
    check("51. con la cache o senza, stessa maschera; anche con pochissima memoria", diversi == 0, f"{len(valori_tutti)} confronti")
    # in ordine a caso e ripetuto, il risultato non cambia
    r_ = np.random.default_rng(0)
    diversi = 0
    per_zero = {}
    for i in r_.integers(0, len(valori_tutti), 300).tolist():
        b, l_, x = valori_tutti[i]
        per_zero.setdefault(i, b.maschera(Cache(df, 0), l_, x))
        diversi += not (b.maschera(stretta, l_, x) == per_zero[i]).all()
    check("52. in ordine a caso, con la memoria stretta, stesso risultato", diversi == 0)
    limite = 1 * 1024 * 1024
    stretta2, massimo = Cache(df, 1), 0
    for b, l_, x in valori_tutti:
        b.maschera(stretta2, l_, x)
        massimo = max(massimo, stretta2.memoria_byte)
    vera = sum(a.nbytes for a in stretta2._valori.values())
    check("53. il limite di memoria si rispetta sempre", massimo <= limite and vera == stretta2.memoria_byte, f"massimo {massimo} byte su {limite}")
    check("54. limite zero: non tiene niente", zero.memoria_byte == 0 and not zero._valori)
    piccola = Cache(df, 0.1)   # sta un solo array da 96 KB
    a1 = piccola.indicatore("rsi", barre=24)
    a2 = piccola.indicatore("rsi", barre=48)
    check("55. oltre il limite si buttano i meno recenti", ("indicatore", "rsi", (("barre", 24),)) not in piccola._valori
          and ("indicatore", "rsi", (("barre", 48),)) in piccola._valori and (a1 == Cache(df, 0).indicatore("rsi", barre=24))[50:].all())
    bassa = Cache(df, 0.001)   # niente ci sta
    check("56. un valore più grande del limite si restituisce ma non si tiene", bassa.indicatore("rsi", barre=24).shape == (len(df),) and bassa.memoria_byte == 0)
    ricalcoli = Cache(df, 50)
    x1 = ricalcoli.indicatore("adx", barre=24)
    x2 = ricalcoli.indicatore("adx", barre=24)
    check("57. un valore già calcolato non si ricalcola", x1 is x2 and ricalcoli.calcoli == 1 and ricalcoli.presi == 1)
    b = _uno("ADX")
    neutra = Cache(df, 50)
    b.maschera(neutra, 1, b.centrali())
    calcoli = neutra.calcoli
    b.maschera(neutra, -1, b.centrali())
    check("58. un filtro neutro non si ricalcola per l'altro lato", neutra.calcoli == calcoli)
    def scrivi():
        x1[0] = 1.0
    check("59. i valori della cache sono in sola lettura", errore(scrivi))
    check("60. indicatore sconosciuto, limite negativo: errore", errore(lambda: ricalcoli.indicatore("finto", barre=2)) and errore(lambda: Cache(df, -1)))
    check("61. la cache legge il timeframe dall'indice", Cache(_mercato(100, minuti=60), 1).barre(9) == 9
          and Cache(_mercato(100, minuti=15), 1).barre(9) == 36 and Cache(_mercato(100, minuti=1440), 1).barre(96) == 4
          and Cache(_mercato(100, minuti=1), 1).barre(2) == 120)

    # ------------------------------------------------------------------ le soglie
    print("\nLe soglie delle uscite")
    c = Cache(df, 200)
    diretta = soglie_adattive(df, 16, finestra=500, perc_sl=90, perc_tp=90, lag=1)
    mie = c.soglie_uscita(4, 90, 90)
    check("62. stesse soglie di exit_search_bt.soglie_adattive, finestra 500 su M15, lag 1", all(
        np.array_equal(mie[k], diretta[k].to_numpy(), equal_nan=True) for k in diretta))
    spento = c.soglie_uscita(4, 90, None)
    check("63. target spento: NaN; lo stop non cambia", np.isnan(spento["tp_long"]).all() and np.isnan(spento["tp_short"]).all()
          and np.array_equal(spento["sl_long"], mie["sl_long"], equal_nan=True))
    check("64. lag sotto 1: errore", errore(lambda: c.soglie_uscita(4, 90, None, lag=0)))
    conti = Cache(df, 200)
    for perc in (70, 80, 90, 95):
        conti.soglie_uscita(4, perc, None)
        conti.soglie_uscita(4, perc, 90)
    check("65. stop e target separati: 4 stop e 1 target fanno 5 calcoli, non 8", conti.calcoli == 5, f"{conti.calcoli}")
    usc = _uno("X3")
    v = {"durata_barre": 16, "perc_stop": 90, "target": None}
    s = usc.soglie(c, -1, v)
    check("66. il blocco dà durata, stop e target del lato giusto", s["barre"] == 16 and np.array_equal(s["sl"], spento["sl_short"], equal_nan=True)
          and np.isnan(s["tp"]).all())
    check("67. soglie su un blocco che non è un'uscita: errore", errore(lambda: _uno("ADX").soglie(c, 1, {"periodo_barre": 16, "soglia": 20})))
    check("68. la regola di X0 non scatta mai, X3 sì", not _uno("X0").maschera(Cache(df_ind, 5), 1, usc.centrali()).any()
          and usc.maschera(Cache(df_ind, 5), 1, usc.centrali()).any())
    k = _uno("X0", "M15", durata_ore=(0.75, 8))
    check("69. una durata non in griglia (3 barre) funziona: serve ai vicini dell'altopiano",
          k.soglie(c, 1, {"durata_barre": 3, "perc_stop": 80, "target": None})["barre"] == 3)
    errori_taglio, tagli_ok = 0, 0
    for t in (2500, 5000, 7777, len(df) - 2):
        corto = df.iloc[: t + 1]
        cc = Cache(corto, 50)
        pieno, tagliato = c.soglie_uscita(4, 90, 90), cc.soglie_uscita(4, 90, 90)
        for chiave in pieno:
            tagli_ok += 1
            errori_taglio += not np.array_equal(pieno[chiave][: t + 1], tagliato[chiave], equal_nan=True)
    check("70. le soglie non guardano il futuro: tagliando lo storico le barre prima non cambiano", errori_taglio == 0 and tagli_ok == 16)

    # ------------------------------------------------------------------ lookahead e degenerazione
    print("\nverifica_lookahead e verifica_degenerazione, agli estremi e al centro di ogni parametro")
    nomi = _registra_nuovi()
    silenzio = io.StringIO()
    df = _mercato(36_000)      # i valori estremi di RSI (12 ore, soglia 15) sono rari: serve storia per contarne 30
    with contextlib.redirect_stdout(silenzio):
        deg = verifica_degenerazione(df, verbose=False)
    deg = deg[deg["nome"].str.startswith(PREFISSO)]
    non_ok = deg.loc[deg["esito"] != "OK", ["nome", "esito", "eventi", "copertura"]]
    check("71. verifica_degenerazione: OK su tutti i blocchi nuovi", len(deg) == len(nomi) and non_ok.empty,
          f"{len(nomi)} condizioni; " + non_ok.to_string(index=False, header=False)[:600] if len(non_ok) else f"{len(nomi)} condizioni")
    reg.register_entry(PREFISSO + "TRAPPOLA", direction=1)(lambda d_: _evento(d_["Close"].shift(-1) > d_["Close"] * 1.002))
    with contextlib.redirect_stdout(silenzio):
        look = verifica_lookahead(df, prepara=lambda x: x.copy(), riscaldamento=3000, tagli_per_condizione=3, verbose=False)
    trappola = look[look["nome"] == PREFISSO + "TRAPPOLA"]
    check("72. la trappola con il futuro è vista dal controllo", (trappola["esito"] == "LOOKAHEAD").all() and len(trappola) == 1)
    look = look[look["nome"].isin(nomi)]
    non_ok = look.loc[look["esito"] != "OK", ["nome", "esito", "tagli_con_differenze"]]
    check("73. verifica_lookahead: OK su tutti i blocchi nuovi", len(look) == len(nomi) and non_ok.empty,
          f"{len(nomi)} condizioni, da {int(look['tagli'].min())} a {int(look['tagli'].max())} tagli" if non_ok.empty else non_ok.to_string(index=False)[:600])
    reg.clear_registry()
    check("74. registro pulito alla fine", not reg.list_entries() and not reg.list_filters())
    check("75. gli indicatori nuovi non cambiano le colonne del catalogo", "donchian_massimo" not in aggiungi_indicatori(_mercato(1500)).columns)
    check("76. funzioni in indicatori: Donchian esclude la barra corrente", np.isnan(donchian_massimo(corta, 2).iloc[1]) and donchian_minimo(corta, 2).iloc[2] == 9.0
          and abs(atr_relativo(corta, 2, 3).iloc[5] - 1.01657) < 1e-4 and talib.RSI(corta["Close"].to_numpy(float), 2)[2] == 100.0)

    # ------------------------------------------------------------------ lo zoom a passo fine
    print("\nLo zoom a passo fine (decisione del 06/11)")
    errati, fuori, estremi = [], [], []
    for tf in MINUTI_TIMEFRAME:
        for nome in (*NUOVI, *USCITE_CATALOGO):
            b = _uno(nome, tf)
            for p in b.parametri:
                if isinstance(p, Categoria):
                    continue
                atteso = 0.1 if (nome, p.nome) == ("ATR_RELATIVO", "soglia") else 1
                if p.passo != atteso or isinstance(p, Reale) != (atteso == 0.1):
                    errati.append((tf, nome, p.nome, p.passo))
                griglia = b.griglia[p.nome]
                if p.minimo != griglia[0] or p.massimo != griglia[-1]:
                    estremi.append((tf, nome, p.nome))
                spazio = {p.valore(i) for i in range(p.n)}
                if not set(griglia) <= spazio:
                    fuori.append((tf, nome, p.nome))
    check("77. passo dello spazio: 1 barra, 1 per le soglie intere, 0,1 per la soglia di ATR relativo, su ogni timeframe", not errati, str(errati[:4]))
    check("78. minimo e massimo dello spazio = quelli della griglia", not estremi, str(estremi[:4]))
    check("79. i valori della griglia stanno tutti nello spazio, esatti", not fuori, str(fuori[:4]))
    r = _uno("RSI_RIENTRO")
    a = _uno("ATR_RELATIVO")
    x = _uno("X3")
    spazi = {p.nome: p.n for b_ in (r, a, x) for p in b_.parametri}
    check("80. su M15 lo zoom passa da ogni barra e da ogni soglia", r.parametri[0].n == 41 and r.parametri[1].n == 21
          and a.parametri[0].n == 9 and a.parametri[1].n == 289 and a.parametri[2].n == 8 and x.parametri[0].n == 29 and x.parametri[1].n == 26, str(spazi))
    check("81. la griglia resta quella larga del passo 1", r.griglia == {"periodo_barre": (8, 16, 24, 36, 48), "soglia": (15, 20, 25, 30, 35)}
          and a.griglia == {"breve_barre": (8, 16), "lungo_barre": (96, 192, 384), "soglia": (0.8, 1.0, 1.2, 1.5)})
    check("82. la soglia di ATR relativo resta a 0,1 anche con soli interi in config", isinstance(_uno("ATR_RELATIVO", soglia=(1, 2)).parametri[2], Reale)
          and _uno("ATR_RELATIVO", soglia=(1, 2)).parametri[2].n == 11)
    check("83. soglia con la virgola dove è intera, ATR relativo non multiplo di 0,1: errore", errore(lambda: _uno("RSI_RIENTRO", soglia=(17.5, 20)))
          and errore(lambda: _uno("X3", perc_stop=(72.5, 90))) and errore(lambda: _uno("ATR_RELATIVO", soglia=(0.85, 1.0))))

    # ------------------------------------------------------------------ da M1 a D1
    print("\nTimeframe da M1 a D1 (decisione del 06/11)")
    check("84. i timeframe sono M1, M5, M15, M30, H1, H4, D1; gli altri si fermano", MINUTI_TIMEFRAME == {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
          and errore(lambda: _uno("X0", "M2")))
    griglia = lambda nome, tf, p: _uno(nome, tf).griglia[p]
    check("85. M1: conversione", griglia("RSI_RIENTRO", "M1", "periodo_barre") == (120, 240, 360, 540, 720) and griglia("X0", "M1", "durata_barre") == (60, 120, 240, 480))
    check("86. H4: arrotondamento e doppi tolti", griglia("X0", "H4", "durata_barre") == (1, 2) and griglia("DONCHIAN", "H4", "canale_barre") == (1, 2, 3, 6, 12, 24)
          and griglia("ATR_RELATIVO", "H4", "breve_barre") == (1,) and griglia("ATR_RELATIVO", "H4", "lungo_barre") == (6, 12, 24))
    d1 = _uno("X3", "D1")
    check("87. D1: le uscite a 1, 2, 4 e 8 ore diventano una sola, 1 barra", d1.griglia["durata_barre"] == (1,) and d1.parametri[0].n == 1
          and (d1.parametri[0].minimo, d1.parametri[0].massimo) == (1, 1))
    check("88. D1: anche il canale di Donchian toglie i doppi", griglia("DONCHIAN", "D1", "canale_barre") == (1, 2, 4))
    check("89. RSI e ADX non scendono sotto 5 barre, l'ATR lungo nemmeno", griglia("RSI_RIENTRO", "H4", "periodo_barre") == (5,) and griglia("RSI_RIENTRO", "D1", "periodo_barre") == (5,)
          and griglia("ADX", "H4", "periodo_barre") == (5,) and griglia("ADX", "D1", "periodo_barre") == (5,) and griglia("ATR_RELATIVO", "D1", "lungo_barre") == (5,))
    def scoppia(f, *a_, **k_):
        try:
            f(*a_, **k_)
        except Exception:
            return True
        return False
    check("90. TA-Lib rifiuta RSI e ADX a 1 barra: il minimo di 5 copre anche questo", scoppia(talib.RSI, _mercato(100)["Close"].to_numpy(float), 1)
          and scoppia(talib.ADX, *(_mercato(100)[k].to_numpy(float) for k in ("High", "Low", "Close")), 1))
    check("91. ore effettive: 2 barre H4 = 8 ore; 1 barra D1 = 24 ore; 8 barre M15 = 2 ore", _uno("X0", "H4").ore_effettive({"durata_barre": 2, "perc_stop": 90, "target": None}) == {"durata_barre": 8.0}
          and d1.griglia_ore() == {"durata_barre": (24.0,)} and _uno("RSI_RIENTRO").ore_effettive({"periodo_barre": 8, "soglia": 25}) == {"periodo_barre": 2.0})
    check("92. finestra delle soglie, sul blocco e in ore effettive: 31 barre H4 = 124 ore, 5 barre D1 = 120 ore", _uno("X0", "H4").finestre_barre == {"soglie_adattive": 31}
          and _uno("X0", "H4").finestre_ore() == {"soglie_adattive": 124.0} and d1.finestre_barre == {"soglie_adattive": 5} and d1.finestre_ore() == {"soglie_adattive": 120.0})
    f2_m15, f2_d1 = _uno("F2_MID_VOLATILITY"), _uno("F2_MID_VOLATILITY", "D1")
    check("93. i filtri del catalogo espongono le finestre in ore: F2 su M15 125 ore, su D1 12.000", f2_m15.finestre_ore() == {"atr": 3.5, "percentile": 125.0}
          and f2_d1.finestre_ore() == {"atr": 336.0, "percentile": 12000.0} and _uno("F3_VOLUME_ABOVE_AVG", "H1").finestre_ore() == {"media": 20.0}
          and _uno("TREND_CONTEXT", "M1").finestre_barre == {"ema": 50} and _uno("F20_SESSION_OVERLAP").finestre_ore() == {})
    predefinito = lambda f, p: inspect.signature(f).parameters[p].default
    check("94. e sono quelle vere delle condizioni", predefinito(filter_conditions.filter_mid_volatility, "window") == FILTRI_CATALOGO["F2_MID_VOLATILITY"][3]["percentile"]
          and predefinito(filter_conditions.filter_volume_above_avg, "window") == FILTRI_CATALOGO["F3_VOLUME_ABOVE_AVG"][3]["media"]
          and predefinito(filter_conditions.filter_chop_trend, "rank_window") == FILTRI_CATALOGO["F25_CHOP_TREND"][3]["percentile"]
          and predefinito(indice_choppiness, "barre") == FILTRI_CATALOGO["F25_CHOP_TREND"][3]["choppiness"])
    # su ogni timeframe: dove la config è ammessa il blocco scatta, dove si ferma non scatterebbe mai
    reg.clear_registry()
    sbagliati, per_tf = [], {}
    for tf, minuti in MINUTI_TIMEFRAME.items():
        # su M1 più barre: E36 scatta una volta al giorno, e 9.000 barre M1 sono solo 6 giorni
        per_tf[tf] = dfi = aggiungi_indicatori(_mercato(30_000 if tf == "M1" else 9000, seme=2, minuti=minuti))
        cache_tf = Cache(dfi, 100)
        if cache_tf.minuti_barra != minuti:
            sbagliati.append((tf, "minuti", cache_tf.minuti_barra))
        for nome in (*ORIGINALI_TRIGGER, *ORIGINALI_FILTRI):
            ammesso = not errore(lambda: _uno(nome, tf))
            ((lungo, corto), tipo) = (TRIGGER_CATALOGO[nome][:2], "trigger") if nome in TRIGGER_CATALOGO else (FILTRI_CATALOGO[nome][:2], "filtro")
            fonte = {**entry_long.TRIGGER_LONG, **entry_short.TRIGGER_SHORT} if tipo == "trigger" else {k: v_[0] for k, v_ in filter_conditions.FILTRI.items()}
            scatta = all(pulito(fonte[n](dfi)).any() for n in (lungo, corto))
            if ammesso != scatta:
                sbagliati.append((tf, nome, f"ammesso {ammesso}, scatta {scatta}"))
    check("95. ogni trigger e filtro del catalogo è ammesso solo dove scatta davvero, da M1 a D1", not sbagliati, str(sbagliati[:6]))
    check("96. F20 su D1 si ferma: la barra è sempre quella delle 00:00; su H4 resta", errore(lambda: _uno("F20_SESSION_OVERLAP", "D1")) and _uno("F20_SESSION_OVERLAP", "H4").neutro)
    sbagliati = []
    for tf in ("M1", "H1", "H4", "D1"):
        dfi, cache_tf = per_tf[tf], Cache(per_tf[tf], 100)
        for b in blocchi_da_config(_config(*NUOVI, timeframe=tf)):
            for valori in _combinazioni(b):
                for lato in (1, -1):
                    m = b.maschera(cache_tf, lato, valori)
                    if m.shape != (len(dfi),) or m.dtype != bool:
                        sbagliati.append((tf, b.nome, valori))
    check("97. i blocchi nuovi girano su M1, H1, H4 e D1, agli estremi e al centro", not sbagliati, str(sbagliati[:3]))
    sbagliati = []
    for tf, (ore, barre_attese, finestra) in {"M1": (2, 120, 7500), "H4": (8, 2, 31), "D1": (8, 1, 5)}.items():
        dfi = per_tf[tf]
        mie = Cache(dfi, 100).soglie_uscita(ore, 90, 90)
        diretta = soglie_adattive(dfi, barre_attese, finestra=finestra, perc_sl=90, perc_tp=90, lag=1)
        if not all(np.array_equal(mie[k], diretta[k].to_numpy(), equal_nan=True) for k in diretta):
            sbagliati.append(tf)
    check("98. soglie su M1, H4 e D1: stessa funzione, finestra e durata arrotondate alla barra", not sbagliati, str(sbagliati))
    u_d1 = _uno("X0", "D1")
    s = u_d1.soglie(Cache(per_tf["D1"], 100), 1, {"durata_barre": 1, "perc_stop": 90, "target": None})
    validi = int(np.isfinite(s["sl"]).sum())
    check("99. su D1 il blocco dà durata 1 barra e soglie vere", s["barre"] == 1 and validi > len(per_tf["D1"]) - 20, f"{validi} barre con soglia su {len(per_tf['D1'])}")
    reg.clear_registry()

    # ------------------------------------------------------------------ etichette e famiglie
    print("\nEtichette e famiglie (decisioni del 06/11)")
    check("100. E5 è «rottura dopo inside bar», X3 è «MACD sotto la signal (stato)»", _uno("E5").famiglia == "rottura dopo inside bar"
          and _uno("X3").famiglia == "MACD sotto la signal (stato)")
    check("101. le liste di P-L2 non cambiano: in testa ai dizionari, con le stesse condizioni", tuple(TRIGGER_CATALOGO)[:5] == ORIGINALI_TRIGGER and tuple(USCITE_CATALOGO) == ("X0", "X3", "X1")
          and tuple(FILTRI_CATALOGO)[:5] == ORIGINALI_FILTRI and TRIGGER_CATALOGO["E47"][:2] == ("E47_COMPRESSIONE_ROTTURA_UP", "E47_SHORT_COMPRESSIONE_ROTTURA_DOWN")
          and FILTRI_CATALOGO["TREND_CONTEXT"][:2] == ("F8_UPTREND_CONTEXT", "F9_DOWNTREND_CONTEXT")
          and TRIGGER_CATALOGO["E5"][:2] == ("E5_QUICK_PULLBACK", "E5_SHORT_QUICK_PULLBACK") and USCITE_CATALOGO["X3"][:2] == ("X3_MACD_BEARISH", "X3_SHORT_MACD_BULLISH"))
    filtri = [b for b in blocchi_da_config(_config(*ORIGINALI_FILTRI, *NUOVI)) if b.tipo == "filtro"]
    coppie = [(x_, y_) for x_, y_ in itertools.combinations(filtri, 2) if x_.famiglia != y_.famiglia]
    trigger = [b for b in blocchi_da_config(_config(*ORIGINALI_TRIGGER, *NUOVI)) if b.tipo == "trigger"]
    check("102. ADX e ATR relativo stanno nella stessa famiglia; nessun'altra coppia di filtri", _uno("ADX").famiglia == _uno("ATR_RELATIVO").famiglia
          and len({b.famiglia for b in filtri}) == 6 and len(filtri) == 7)
    check("103. le teorie sono 1.176: 7 trigger × (1 + 7 + 20 scelte di filtri) × 3 uscite × 2 lati", len(coppie) == 20 and len(trigger) == 7
          and len(trigger) * (1 + len(filtri) + len(coppie)) * len(USCITE_CATALOGO) * 2 == 1176)

    # ------------------------------------------------------------------ il minimo di 5 barre
    print("\nMinimo di 5 barre per periodo di RSI e ADX e ATR lungo (decisione del 07/11)")
    griglie = lambda tf: (griglia("RSI_RIENTRO", tf, "periodo_barre"), griglia("ADX", tf, "periodo_barre"),
                          griglia("ATR_RELATIVO", tf, "breve_barre"), griglia("ATR_RELATIVO", tf, "lungo_barre"))
    check("104. il minimo è 5 per periodo e ATR lungo; niente minimo per l'ATR breve", BARRE_MINIME == {"periodo_barre": 5, "lungo_barre": 5})
    check("105. su M15 le griglie non cambiano", griglie("M15") == ((8, 16, 24, 36, 48), (16, 24, 36), (8, 16), (96, 192, 384))
          and griglia("X0", "M15", "durata_barre") == (4, 8, 16, 32) and griglia("DONCHIAN", "M15", "canale_barre") == (16, 32, 48, 96, 192, 384))
    check("106. H1: 2 e 4 ore di RSI e 4 ore di ADX salgono a 5, i doppi si tolgono", griglie("H1") == ((5, 6, 9, 12), (5, 6, 9), (2, 4), (24, 48, 96)))
    check("107. H4: RSI e ADX restano a 5; ATR breve 1; ATR lungo già sopra", griglie("H4") == ((5,), (5,), (1,), (6, 12, 24)))
    check("108. D1: RSI, ADX e ATR lungo restano a 5; ATR breve 1", griglie("D1") == ((5,), (5,), (1,), (5,)))
    check("109. M1 e M5 non cambiano; su M30 solo le 2 ore di RSI, da 4 barre a 5", griglie("M1") == ((120, 240, 360, 540, 720), (240, 360, 540), (120, 240), (1440, 2880, 5760))
          and griglie("M5") == ((24, 48, 72, 108, 144), (48, 72, 108), (24, 48), (288, 576, 1152)) and griglie("M30") == ((5, 8, 12, 18, 24), (8, 12, 18), (4, 8), (48, 96, 192)))
    spazio_h1, spazio_d1 = _uno("RSI_RIENTRO", "H1").parametri[0], _uno("RSI_RIENTRO", "D1").parametri[0]
    check("110. lo spazio parte dal minimo: H1 da 5 a 12 a passo 1; D1 solo 5", (spazio_h1.minimo, spazio_h1.massimo, spazio_h1.passo, spazio_h1.n) == (5, 12, 1, 8)
          and (spazio_d1.minimo, spazio_d1.massimo, spazio_d1.n) == (5, 5, 1))
    c_d1 = Cache(per_tf["D1"], 100)
    rsi_d1, adx_d1, atr_d1 = _uno("RSI_RIENTRO", "D1"), _uno("ADX", "D1"), _uno("ATR_RELATIVO", "D1")
    check("111. sotto il minimo la maschera si ferma: periodo o ATR lungo a 4 barre", errore(lambda: rsi_d1.maschera(c_d1, 1, {"periodo_barre": 4, "soglia": 25}))
          and errore(lambda: adx_d1.maschera(c_d1, 1, {"periodo_barre": 4, "soglia": 25})) and errore(lambda: atr_d1.maschera(c_d1, 1, {"breve_barre": 1, "lungo_barre": 4, "soglia": 1.0})))
    check("112. a 5 barre gira; ATR breve, durata e canale di Donchian possono stare a 1 barra", atr_d1.maschera(c_d1, 1, {"breve_barre": 1, "lungo_barre": 5, "soglia": 1.0}).any()
          and rsi_d1.maschera(c_d1, 1, {"periodo_barre": 5, "soglia": 25}).any() and adx_d1.maschera(c_d1, 1, {"periodo_barre": 5, "soglia": 25}).any()
          and griglia("X0", "D1", "durata_barre") == (1,) and griglia("DONCHIAN", "D1", "canale_barre")[0] == 1)
    # su M15 il periodo 5 non è in griglia: lookahead e degenerazione si rifanno su tutta la griglia di D1.
    # Le combinazioni degeneri sono ammesse solo se dichiarate qui: all'avvio di ogni ricerca escono dalla griglia (docs/82 P-L2, §8).
    nomi = _registra_nuovi("D1", tutte=True)
    df = _mercato(12_000, minuti=1440)
    with contextlib.redirect_stdout(silenzio):
        deg = verifica_degenerazione(df, verbose=False)
        look = verifica_lookahead(df, prepara=lambda x: x.copy(), riscaldamento=3000, tagli_per_condizione=3, verbose=False)
    deg, look = deg[deg["nome"].isin(nomi)], look[look["nome"].isin(nomi)]
    degeneri_dichiarati = {f"{PREFISSO}ADX_periodo_barre5_soglia{s}" for s in (15, 20, 25)}
    non_ok = deg.loc[deg["esito"] != "OK"]
    elenco = "; ".join(f"{r.nome[len(PREFISSO):]} {r.esito} {r.copertura:.1%}" for r in non_ok.itertuples())
    check("113. verifica_degenerazione su tutta la griglia di D1: degeneri solo le combinazioni dichiarate, ogni altra OK", len(deg) == len(nomi)
          and set(non_ok["nome"]) == degeneri_dichiarati and (non_ok["esito"] == "QUASI_SEMPRE_VERA").all(), f"{len(nomi)} condizioni; degeneri: {elenco}")
    non_ok = look.loc[look["esito"] != "OK", ["nome", "esito"]]
    check("114. verifica_lookahead sulla griglia di D1: OK su tutti i blocchi nuovi", len(look) == len(nomi) and non_ok.empty,
          f"{len(nomi)} condizioni" if non_ok.empty else non_ok.to_string(index=False)[:600])
    reg.clear_registry()

    # ------------------------------------------------------------------ C1: il catalogo intero
    print("\nC1: il catalogo intero nei blocchi (docs/82 §11.2, §11.7 «Blocchi», §11.12)")
    lunghi = {v[0] for v in TRIGGER_CATALOGO.values()}
    corti = {v[1] for v in TRIGGER_CATALOGO.values() if v[1] is not None}
    filtri_cat = {c for v in FILTRI_CATALOGO.values() for c in v[:2]}
    attesi_f = (set(filter_conditions.FILTRI) | set(vwap_regime_filter_conditions.FILTRI_VWAP)) - {
        "F36_SENT_EXTREME_FEAR", "F36_SENT_EXTREME_GREED"}
    check("115. ogni trigger e filtro del catalogo è un blocco, VWAP compresi, F36 escluso", lunghi == set(entry_long.TRIGGER_LONG)
          and corti == set(entry_short.TRIGGER_SHORT) and filtri_cat == attesi_f,
          f"trigger long {len(lunghi)}, short {len(corti)}, condizioni dei filtri {len(filtri_cat)}")
    tutti_c1 = blocchi_da_config(_config(*TRIGGER_CATALOGO, *FILTRI_CATALOGO, *NUOVI, *USCITE_CATALOGO))
    tr = [b for b in tutti_c1 if b.tipo == "trigger"]
    fi = [b for b in tutti_c1 if b.tipo == "filtro"]
    conti = (len(tr), sum(-1 in b.lati for b in tr), len(fi), sum(b.neutro for b in fi), sum(not b.neutro for b in fi),
             sum(b.tipo == "uscita" for b in tutti_c1))
    check("116. su M15: 45 trigger (44 sullo short), 30 filtri (22 neutri compresi ADX e ATR relativo, 8 coppie), 3 uscite",
          conti == (45, 44, 30, 22, 8, 3), str(conti))
    e19 = _uno("E19")
    check("117. E19 esiste solo long: lo short si ferma con un errore; tutti gli altri blocchi hanno i due lati",
          e19.lati == (1,) and errore(lambda: e19.maschera(Cache(df_ind, 10), -1))
          and all(b.lati == (1, -1) for b in tutti_c1 if b.nome != "E19"))
    con = {**entry_long.TRIGGER_LONG, **entry_short.TRIGGER_SHORT, **{k: v[0] for k, v in filter_conditions.FILTRI.items()},
           **{k: v[0] for k, v in vwap_regime_filter_conditions.FILTRI_VWAP.items()}}
    c = Cache(df_ind, 200)
    tot, diversi = 0, []
    for b in tr + fi:
        if b._catalogo is None:
            continue
        for lato, nome in zip((1, -1), b._catalogo):
            if nome is None:
                continue
            tot += 1
            if not (b.maschera(c, lato) == pulito(con[nome](df_ind))).all():
                diversi.append(nome)
    check("118. ogni blocco del catalogo dà la maschera della sua condizione, sui due lati", not diversi and tot == 43 + 42 + 2 * 28,
          f"{tot} confronti {diversi[:5]}")
    trovati, senza_motivo = {}, []
    for nome in (*TRIGGER_CATALOGO, *FILTRI_CATALOGO):
        for tf in MINUTI_TIMEFRAME:
            if errore(lambda: _uno(nome, tf)):
                if (nome, tf) not in MOTIVI_ESCLUSIONE:
                    senza_motivo.append((nome, tf))
                else:
                    trovati[(nome, tf)] = MOTIVI_ESCLUSIONE[(nome, tf)][0]
    check("119. le coppie (blocco, timeframe) escluse e il tipo di motivo sono quelli della tabella D4 (§11.12)",
          trovati == ESCLUSI_ATTESI and not senza_motivo,
          f"in più {sorted(set(trovati) - set(ESCLUSI_ATTESI))[:4]}, in meno {sorted(set(ESCLUSI_ATTESI) - set(trovati))[:4]}, "
          f"senza motivo {senza_motivo[:4]}")
    check("120. ogni motivo scritto corrisponde a una coppia esclusa, con una frase",
          set(MOTIVI_ESCLUSIONE) == set(trovati) and all(len(m) == 2 and m[1] for m in MOTIVI_ESCLUSIONE.values()))
    # la fabbrica gira sempre in modalità crypto (nessun rollover, giornata delle 00:00 UTC): i dati del collaudo, anche
    imposta_mercato_crypto()
    per_tf_c = {tf: aggiungi_indicatori(_mercato(30_000 if tf == "M1" else 9000, seme=2, minuti=m))
                for tf, m in MINUTI_TIMEFRAME.items()}
    non_scattano = []
    for nome in (*TRIGGER_CATALOGO, *FILTRI_CATALOGO):
        for tf in MINUTI_TIMEFRAME:
            if (nome, tf) in ESCLUSI_ATTESI:
                continue
            b, ct = _uno(nome, tf), Cache(per_tf_c[tf], 100)
            if not any(b.maschera(ct, lato).any() for lato in b.lati):
                non_scattano.append((nome, tf))
    check("121. ogni blocco ammesso scatta sui dati del collaudo, tranne quelli a cui servono più storia o più barre "
          "(il controllo dei degeneri li toglie a ogni avvio, §11.12)", set(non_scattano) == NON_SCATTANO_SUL_COLLAUDO,
          f"diversi: {sorted(set(non_scattano) ^ NON_SCATTANO_SUL_COLLAUDO)}")
    etichette = [b.famiglia for b in tr + fi if b.nome not in ("ADX", "ATR_RELATIVO")]
    check("122. ogni blocco nuovo ha la sua etichetta di famiglia: solo ADX e ATR relativo ne condividono una",
          len(set(etichette)) == len(etichette) and _uno("ADX").famiglia == _uno("ATR_RELATIVO").famiglia
          and _uno("ADX").famiglia not in etichette)
    reg.clear_registry()
    vwap = _uno("VWAP_SESSION_CLOSE").maschera(Cache(df_ind, 10), -1)
    _registra_catalogo()
    check("123. la fabbrica registra anche i filtri VWAP, come il Lab", "VWAP_PREVIOUS_SESSION_CLOSED_BELOW" in reg.list_filters()
          and "VWAP_GAP_WIDENING" in reg.list_filters() and vwap.dtype == bool and len(vwap) == len(df_ind))
    reg.clear_registry()

    print("\n" + "=" * 70)
    print(f"Durata: {time.perf_counter() - t0:.0f} s")
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
