"""
Suite di collaudo dei blocchi e della cache della fabbrica (docs/82 P-L2, lavoro L2).

Si lancia da terminale, dalla cartella del progetto:

    python test_fabbrica_blocchi.py

Solo dati sintetici: non servono i file in dati/, MetaTrader 5 o internet.
Stampa una riga per collaudo e alla fine «RISULTATO: n/n test superati».
"""
from __future__ import annotations

import contextlib
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
from engine import registry as reg
from engine.collaudo_catalogo import verifica_degenerazione, verifica_lookahead
from engine.exit_search_bt import soglie_adattive
from engine.fabbrica.blocchi import (FILTRI_CATALOGO, GRIGLIE_NUOVI, TRIGGER_CATALOGO, USCITE_CATALOGO, Blocco,
                                     blocchi_da_config)
from engine.fabbrica.cache import ORE_FINESTRA_SOGLIE, Cache, barre_da_ore
from engine.fabbrica.ottimizzatore import Categoria, Intero, Reale
from engine.indicatori import aggiungi_indicatori, atr_relativo, donchian_massimo, donchian_minimo
from helpers import _cross_down, _cross_up, _evento

warnings.simplefilter("ignore")

PREFISSO = "PROVA_FAB_"
NUOVI = tuple(GRIGLIE_NUOVI)
TUTTI_CATALOGO = (*TRIGGER_CATALOGO, *FILTRI_CATALOGO, *USCITE_CATALOGO)


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


def _combinazioni(b: Blocco) -> list[dict]:
    """Estremi e centro di ogni parametro, tutte le combinazioni."""
    assi = []
    for nome, valori in b.griglia.items():
        assi.append([(nome, v) for v in dict.fromkeys((valori[0], valori[len(valori) // 2], valori[-1]))])
    return [dict(c) for c in itertools.product(*assi)]


def _etichetta(b: Blocco, valori: dict, lato=None) -> str:
    resto = "_".join(f"{k}{v}" for k, v in valori.items())
    return f"{PREFISSO}{b.nome}_{resto}" + ("" if lato is None else ("_L" if lato == 1 else "_S"))


def _registra_nuovi() -> list[str]:
    """I blocchi nuovi come condizioni del registro, agli estremi e al centro: così passano dai collaudi del catalogo."""
    reg.clear_registry()
    nomi = []
    for b in blocchi_da_config(_config(*NUOVI)):
        for valori in _combinazioni(b):
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
    check("4. ore che non fanno barre intere: errore", errore(lambda: barre_da_ore(0.1, 15)) and errore(lambda: barre_da_ore(1.5, 60))
          and errore(lambda: barre_da_ore(2, 240)) and errore(lambda: barre_da_ore(0, 15)) and errore(lambda: barre_da_ore(-1, 15)))
    rsi_m15, rsi_h1 = _uno("RSI_RIENTRO"), _uno("RSI_RIENTRO", "H1")
    check("5. stesso blocco, M15 e H1: griglia convertita", rsi_m15.griglia["periodo_barre"] == (8, 16, 24, 36, 48)
          and rsi_h1.griglia["periodo_barre"] == (2, 4, 6, 9, 12))
    check("6. griglia con ore non intere sul timeframe: la config si ferma", errore(lambda: _uno("RSI_RIENTRO", "H4"))
          and errore(lambda: _uno("DONCHIAN", "H1", canale_ore=(1.5,))) and errore(lambda: _uno("X0", "H4")))
    check("7. ore frazionarie che fanno barre intere: ammesse", _uno("DONCHIAN", canale_ore=(1.25, 3.5)).griglia["canale_barre"] == (5, 14))
    check("8. la finestra delle soglie è di 125 ore: 500 barre su M15, 125 su H1, 1500 su M5", ORE_FINESTRA_SOGLIE == 125
          and barre_da_ore(ORE_FINESTRA_SOGLIE, 15) == 500 and barre_da_ore(ORE_FINESTRA_SOGLIE, 60) == 125
          and barre_da_ore(ORE_FINESTRA_SOGLIE, 5) == 1500)

    # ------------------------------------------------------------------ la forma dei blocchi
    print("\nLa forma dei blocchi")
    tutti = blocchi_da_config(_config(*TUTTI_CATALOGO, *NUOVI))
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
    check("14. il catalogo non ha parametri", all(not b.parametri for b in tutti if b.nome in (*TRIGGER_CATALOGO, *FILTRI_CATALOGO)))
    check("15. blocco sconosciuto, parametro sconosciuto, parametri al catalogo: errore", errore(lambda: _uno("E99"))
          and errore(lambda: _uno("ADX", finto_ore=(1,))) and errore(lambda: _uno("E47", periodo_ore=(1,))))
    check("16. catalogo su un timeframe dove non scatta: errore", errore(lambda: _uno("E47", "H1"))
          and errore(lambda: _uno("E36", "H1")) and _uno("E49", "H1").nome == "E49")
    df = _mercato(3000)
    c = Cache(df, 50)
    b = _uno("ADX")
    check("17. valori sbagliati, lato sbagliato: errore", errore(lambda: b.maschera(c, 1, {"soglia": 20}))
          and errore(lambda: b.maschera(c, 0, b.centrali())) and errore(lambda: b.maschera(c, 1, {"periodo_barre": 2.5, "soglia": 20})))

    # ------------------------------------------------------------------ i conti a mano
    print("\nI conti a mano, su sei barre (M15)")
    corta = _corta()
    c = Cache(corta, 5)
    def vicini(a, attesi):
        return all((np.isnan(x) and np.isnan(y)) or abs(x - y) < 1e-3 for x, y in zip(a, attesi)) and len(a) == len(attesi)
    nan = float("nan")
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
    r = _uno("RSI_RIENTRO", periodo_ore=(0.5,))
    check("26. RSI rientro short: scende sotto 100 - 50 da sopra, alla barra 5", r.maschera(c, -1, {"periodo_barre": 2, "soglia": 50}).tolist()
          == [False] * 5 + [True])
    check("27. RSI rientro long: risale sopra 70 da sotto, alla barra 4", r.maschera(c, 1, {"periodo_barre": 2, "soglia": 70}).tolist()
          == [False] * 4 + [True, False])
    a = _uno("ADX", periodo_ore=(0.5,))
    check("28. filtro ADX: stato, non evento", a.maschera(c, 1, {"periodo_barre": 2, "soglia": 50}).tolist() == [False] * 3 + [True] * 3
          and a.maschera(c, 1, {"periodo_barre": 2, "soglia": 70}).tolist() == [False] * 3 + [True, True, False])
    t = _uno("ATR_RELATIVO", breve_ore=(0.5,), lungo_ore=(0.75,))
    check("29. filtro ATR relativo: stato, NaN = falso", t.maschera(c, 1, {"breve_barre": 2, "lungo_barre": 3, "soglia": 1.0}).tolist()
          == [False] * 4 + [True, True])

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
    for nome in (*TRIGGER_CATALOGO, *FILTRI_CATALOGO):
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
          and Cache(_mercato(100, minuti=15), 1).barre(9) == 36 and errore(lambda: Cache(_mercato(100, minuti=60), 1).barre(0.5)))

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

    print("\n" + "=" * 70)
    print(f"Durata: {time.perf_counter() - t0:.0f} s")
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
