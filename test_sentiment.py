"""
Collaudo del filtro di sentiment F36 (docs/50 §10, riga 11; scheda approvata
da Mattia il 15/10/2026):

    sentiment_giornaliero (engine/indicatori.py)   colonne sentiment_score,
                                                   sentiment_classe
    F36_SENT_EXTREME_FEAR / F36_SENT_EXTREME_GREED coppia "SENTIMENT",
                                                   contrarian (+1 / -1)

Sezioni (docs/50 §7):

    A  la formula contro una riscrittura indipendente, giornata per giornata
    B  casi a risultato noto: valore fermo nella giornata, solo l'ultimo
       giorno chiuso, riscaldamento esatto, quarantena ignorata, crollo e
       euforia costruiti a mano
    C  lookahead per troncamento (verifica_lookahead), con una trappola che
       usa il giorno in corso e deve risultare LOOKAHEAD; tagli a meta' giornata
    D  riscaldamento: stesso valore da qualunque punto partano i dati
    E  i 9 symbol di dati/ (solo conteggi) e verifica_degenerazione su BTCUSD
    F  registrazione nel motore e righe di aggiungi_indicatori invariate

Si lancia da terminale, dalla cartella del progetto:

    python test_sentiment.py

(su Windows: PYTHONIOENCODING=utf-8). Le prove sui dati veri girano solo se
ci sono i file di dati/; se mancano vengono SALTATE e lo dice. Non serve MT5.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.simplefilter(action="ignore", category=FutureWarning)

from engine import registry as R
from engine.broker_tz_diagnostic import to_utc_index
from engine.collaudo_catalogo import mercato_sintetico, verifica_degenerazione, verifica_lookahead
from engine.indicatori import (COLONNE_INDICATORI, _sentiment_per_giorno, aggiungi_indicatori,
                               sentiment_giornaliero)
from engine.livelli import giorno_fx, svuota_cache
from engine.quarantena import quarantena
from filter_conditions import FILTRI, filter_sent_extreme_fear, filter_sent_extreme_greed, registra_filtri

CARTELLA = os.path.dirname(os.path.abspath(__file__))
DATI = os.path.join(CARTELLA, "dati")
SYMBOL = ("EURUSD", "GBPUSD", "USDJPY", "NZDUSD", "BTCUSD", "US500", "USTEC", "XAUUSD", "DE40")
NUOVI = {"F36_SENT_EXTREME_FEAR": (filter_sent_extreme_fear, 1),
         "F36_SENT_EXTREME_GREED": (filter_sent_extreme_greed, -1)}
COLONNE = ("sentiment_score", "sentiment_classe")
M, P = 30, 365                       # giorni della media e del percentile (default)
PRIMO_PUNTEGGIO = M + P - 2          # prima giornata valida con il punteggio (393)
PRIMA_CLASSE = M + 2 * P - 3         # prima giornata valida con la classe (757)


def _leggi(symbol: str) -> pd.DataFrame | None:
    percorso = os.path.join(DATI, f"{symbol}_M15.csv")
    if not os.path.exists(percorso):
        return None
    df = pd.read_csv(percorso, parse_dates=["Date"], index_col="Date")
    df = to_utc_index(df, "A_US_DST (NY+7h)", on_dst_gap="drop", verbose=False)
    return df[["Open", "High", "Low", "Close", "Volume"]]


def _crypto_sintetico(giorni: int = 1300, seme: int = 7, prezzo: float = 30000.0) -> pd.DataFrame:
    """Random walk M15 aperto 7 giorni su 7, con la pausa del venerdi' 17:00-18:00 NY come BTCUSD."""
    idx = pd.date_range("2022-01-03", periods=giorni * 96, freq="15min", tz="UTC")
    ny = idx.tz_convert("America/New_York")
    idx = idx[~((ny.dayofweek == 4) & (ny.hour == 17))]
    rng = np.random.default_rng(seme)
    n = len(idx)
    close = prezzo * np.exp(np.cumsum(rng.normal(0, 0.003, n)))
    op = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"Open": op, "High": np.maximum(op, close) * 1.001,
                         "Low": np.minimum(op, close) * 0.999, "Close": close,
                         "Volume": rng.integers(100, 5000, n).astype(float)}, index=idx)


def _riferimento(df: pd.DataFrame) -> pd.DataFrame:
    """
    Riscrittura indipendente, con cicli espliciti e senza rolling di pandas:
    una riga per giornata FX (numerate come giorno_fx), stesse colonne di
    _sentiment_per_giorno.
    """
    q = quarantena(df, verbose=False)["totale"].to_numpy()
    data = (df.index.tz_convert("America/New_York") + pd.Timedelta(hours=7)).date
    giornate, corrente = [], [0]
    for i in range(1, len(df)):
        if data[i] != data[i - 1]:
            giornate.append(corrente)
            corrente = []
        corrente.append(i)
    giornate.append(corrente)
    c, v = df["Close"].to_numpy(dtype=float), df["Volume"].to_numpy(dtype=float)
    valide = []                                   # (numero giornata, close, vol, volume)
    for k, pos in enumerate(giornate):
        utili = [i for i in pos if not q[i]]
        if not utili:
            continue
        rend = [np.log(c[b] / c[a]) for a, b in zip(utili[:-1], utili[1:])]
        if len(rend) < 2:
            continue
        chiusura, volume = c[utili[-1]], float(np.mean(v[utili]))
        if chiusura > 0 and volume > 0:
            valide.append((k, chiusura, float(np.std(rend, ddof=1)), volume))
    n = len(valide)
    cl = np.array([x[1] for x in valide]); vo = np.array([x[2] for x in valide])
    vm = np.array([x[3] for x in valide])
    grezze = {nome: np.full(n, np.nan) for nome in ("v1", "v2", "v3", "v4")}
    for j in range(M - 1, n):
        w = slice(j - M + 1, j + 1)
        grezze["v1"][j] = vo[j] / vo[w].mean()
        grezze["v2"][j] = cl[j] / cl[w].max() - 1.0
        grezze["v3"][j] = cl[j] / cl[w].mean() - 1.0
        grezze["v4"][j] = np.sign(np.log(cl[j] / cl[j - 1])) * vm[j] / vm[w].mean()

    def pct(x: np.ndarray) -> np.ndarray:
        """Percentile medio (come rank(pct=True)) sugli ultimi P valori definiti."""
        esito = np.full(len(x), np.nan)
        definiti = np.flatnonzero(np.isfinite(x))
        for a in range(P - 1, len(definiti)):
            finestra = x[definiti[a - P + 1:a + 1]]
            val = x[definiti[a]]
            esito[definiti[a]] = ((finestra < val).sum() + ((finestra == val).sum() + 1) / 2.0) / P
        return esito

    comp = {"sent_volatilita": 1.0 - pct(grezze["v1"]), "sent_drawdown": pct(grezze["v2"]),
            "sent_momentum": pct(grezze["v3"]), "sent_volume": pct(grezze["v4"])}
    punteggio = 100.0 * np.mean(np.vstack(list(comp.values())), axis=0)
    rango = pct(punteggio)
    classe = np.where(np.isnan(rango), np.nan, np.ceil(np.round(rango * 5, 12)).clip(1, 5))
    esito = pd.DataFrame({**comp, "sentiment_score": punteggio, "sentiment_classe": classe},
                         index=[x[0] for x in valide])
    return esito.reindex(np.arange(len(giornate)))


def _uguali(a, b, tol: float = 1e-9) -> bool:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return a.shape == b.shape and bool(np.all((np.isnan(a) & np.isnan(b)) | (np.abs(a - b) <= tol)))


def _trappola_giorno_in_corso(df: pd.DataFrame) -> pd.Series:
    """classe della giornata IN CORSO (manca lo spostamento di un giorno)"""
    per_g = _sentiment_per_giorno(df)
    return pd.Series(per_g["sentiment_classe"].to_numpy()[giorno_fx(df).to_numpy()], index=df.index)


def _prepara(df: pd.DataFrame) -> pd.DataFrame:
    """Solo le colonne del sentiment (e la trappola): aggiungi_indicatori intero e' troppo lento qui."""
    d = df.copy()
    s = sentiment_giornaliero(d)
    for c in COLONNE:
        d[c] = s[c]
    d["t_sent_oggi"] = _trappola_giorno_in_corso(d)
    return d


def main() -> int:
    ESITI: list[bool] = []

    def check(nome: str, condizione: bool, dettaglio: str = ""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def saltato(nome: str, motivo: str):
        print(f"  [SALTATO] {nome}  — {motivo}")

    forex = mercato_sintetico("2021-01-01", "2025-03-01", seme=4)
    crypto = _crypto_sintetico()
    reali = {s: _leggi(s) for s in SYMBOL}
    btc = reali["BTCUSD"]

    # =====================================================================
    print("\nA · FORMULA CONTRO UNA RISCRITTURA INDIPENDENTE\n" + "-" * 70)
    insiemi_a = [("forex sintetico", forex), ("crypto sintetico", crypto)]
    if btc is not None:
        insiemi_a.append(("BTCUSD vero", btc))
    for nome, dati in insiemi_a:
        svuota_cache()
        mio, rif = _sentiment_per_giorno(dati), _riferimento(dati)
        stesse = mio.index.equals(rif.index)
        check(f"A1. {nome}: stesse giornate FX ({len(rif)})", stesse)
        for c in rif.columns:
            check(f"A2. {nome}: {c} uguale giornata per giornata",
                  stesse and _uguali(mio[c], rif[c]),
                  f"{int(np.isfinite(rif[c]).sum())} giornate con il valore")

    # =====================================================================
    print("\nB · CASI A RISULTATO NOTO\n" + "-" * 70)
    for nome, dati in [("forex sintetico", forex), ("crypto sintetico", crypto)]:
        svuota_cache()
        s, per_g, g = sentiment_giornaliero(dati), _sentiment_per_giorno(dati), giorno_fx(dati)
        fermo = all(s[c].groupby(g).nunique(dropna=False).max() == 1 for c in COLONNE)
        check(f"B1. {nome}: il valore e' fermo dentro ogni giornata FX", fermo)
        ieri = per_g.reindex(g.to_numpy() - 1)
        check(f"B2. {nome}: ogni barra vede la giornata CHIUSA precedente (prima giornata: NaN)",
              all(_uguali(s[c], ieri[c]) for c in COLONNE) and s.loc[g == 0].isna().all().all())
        cambia = s["sentiment_score"].ne(s["sentiment_score"].shift()) & s["sentiment_score"].notna()
        prime = g.ne(g.shift())
        check(f"B3. {nome}: il valore cambia solo sulla prima barra di una giornata", not (cambia & ~prime).any())
        valide = per_g.loc[_giornate_valide(dati)]
        check(f"B4. {nome}: punteggio dalla giornata valida {PRIMO_PUNTEGGIO}, classe dalla {PRIMA_CLASSE}",
              valide["sentiment_score"].notna().to_numpy().argmax() == PRIMO_PUNTEGGIO
              and valide["sentiment_classe"].notna().to_numpy().argmax() == PRIMA_CLASSE
              and valide["sentiment_score"].iloc[:PRIMO_PUNTEGGIO].isna().all()
              and valide["sentiment_classe"].iloc[:PRIMA_CLASSE].isna().all())
        d = dati.assign(**{c: s[c] for c in COLONNE})
        paura, avidita = filter_sent_extreme_fear(d), filter_sent_extreme_greed(d)
        check(f"B5. {nome}: paura = classe 1, avidita' = classe 5, mai insieme, false nel riscaldamento",
              paura.equals(d["sentiment_classe"] == 1) and avidita.equals(d["sentiment_classe"] == 5)
              and not (paura & avidita).any() and not (paura | avidita)[d["sentiment_classe"].isna()].any()
              and paura.any() and avidita.any())
        quote = per_g["sentiment_classe"].value_counts(normalize=True)
        check(f"B6. {nome}: le 5 classi compaiono tutte, ognuna fra il 10% e il 30% delle giornate",
              set(quote.index) == {1.0, 2.0, 3.0, 4.0, 5.0} and quote.between(0.10, 0.30).all(),
              ", ".join(f"{int(k)}: {v:.0%}" for k, v in quote.sort_index().items()))

    # quarantena: prezzi e volumi delle barre in quarantena non contano
    svuota_cache()
    q = quarantena(forex, verbose=False)["totale"]
    sporco = forex.copy()
    sporco.loc[q, ["Open", "High", "Low", "Close"]] *= 1.07
    sporco.loc[q, "Volume"] *= 50
    svuota_cache()
    a = _sentiment_per_giorno(forex)
    svuota_cache()
    b = _sentiment_per_giorno(sporco)
    check(f"B7. sporcare le {int(q.sum())} barre in quarantena non cambia nulla",
          all(_uguali(a[c], b[c], 0) for c in a.columns))

    # crollo ed euforia costruiti a mano, sull'ultima giornata del crypto sintetico
    svuota_cache()
    g = giorno_fx(crypto)
    ultimo = int(g.iloc[-1])
    base = crypto.loc[g < ultimo - 1]                     # finisce con una giornata intera
    giorno_caso = crypto.loc[g == ultimo - 1].copy()      # la giornata da modificare
    dopo = crypto.loc[g == ultimo].copy()                 # la giornata che la "vede"
    n = len(giorno_caso)
    for caso, passo, rumore, molt_vol in [("crollo", -0.25, 0.01, 5.0), ("euforia", +0.30, 0.0, 3.0)]:
        rng = np.random.default_rng(1)
        c0 = float(base["Close"].iloc[-1])
        traiettoria = c0 * np.exp(np.linspace(0, np.log(1 + passo), n + 1)[1:]
                                  + rumore * rng.standard_normal(n))
        gc = giorno_caso.copy()
        gc["Close"] = traiettoria
        gc["Open"] = np.r_[c0, traiettoria[:-1]]
        gc["High"] = gc[["Open", "Close"]].max(axis=1)
        gc["Low"] = gc[["Open", "Close"]].min(axis=1)
        gc["Volume"] = base["Volume"].tail(30 * 96).mean() * molt_vol
        dp = dopo.copy()
        dp[["Open", "High", "Low", "Close"]] *= traiettoria[-1] / float(dopo["Open"].iloc[0])
        dati = pd.concat([base, gc, dp])
        svuota_cache()
        s = sentiment_giornaliero(dati)
        d = dati.assign(**{c: s[c] for c in COLONNE})
        sul_giorno, il_dopo = d.loc[gc.index], d.loc[dp.index]
        svuota_cache()
        s_prima = sentiment_giornaliero(pd.concat([base, gc.iloc[:1]]))
        if caso == "crollo":
            check("B8. crollo con volume alto: il giorno dopo paura estrema (classe 1), punteggio sotto 5",
                  bool(filter_sent_extreme_fear(il_dopo).all() and (il_dopo["sentiment_score"] < 5).all()),
                  f"punteggio {il_dopo['sentiment_score'].iloc[0]:.1f}")
        else:
            check("B9. salita regolare con volume alto: il giorno dopo avidita' estrema (classe 5), punteggio sopra 95",
                  bool(filter_sent_extreme_greed(il_dopo).all() and (il_dopo["sentiment_score"] > 95).all()),
                  f"punteggio {il_dopo['sentiment_score'].iloc[0]:.1f}")
        check(f"B10. {caso}: durante la giornata stessa il filtro vede ancora il giorno prima",
              _uguali(sul_giorno["sentiment_score"], np.full(n, s_prima["sentiment_score"].iloc[-1])))

    # =====================================================================
    print("\nC · LOOKAHEAD PER TRONCAMENTO\n" + "-" * 70)
    R.clear_registry()
    for k, (f, direzione) in NUOVI.items():
        R.register_filter(k, direction=direzione)(f)
    R.register_filter("T_SENT_OGGI")(lambda df: df["t_sent_oggi"] == 1)
    insiemi_c = [("crypto sintetico", crypto)]
    if btc is not None:
        insiemi_c.append(("BTCUSD vero, ultime 90000 barre", btc.tail(90000)))
    else:
        saltato("C. lookahead su BTCUSD vero", "manca il file di dati")
    for nome, dati in insiemi_c:
        rep = verifica_lookahead(dati, prepara=_prepara, tagli_per_condizione=8,
                                 verbose=False).set_index("nome")
        check(f"C1. {nome}: la trappola (classe del giorno in corso) e' segnata LOOKAHEAD",
              rep.loc["T_SENT_OGGI", "esito"] == "LOOKAHEAD" and rep.loc["t_sent_oggi", "esito"] == "LOOKAHEAD")
        esiti = {k: rep.loc[k, "esito"] for k in list(NUOVI) + list(COLONNE)}
        check(f"C2. {nome}: F36 e colonne del sentiment OK (esercitate, nessun lookahead)",
              all(e == "OK" for e in esiti.values()), str(esiti))
        # tagli a meta' giornata, scelti apposta: la giornata in corso non deve contare
        svuota_cache()
        intero = sentiment_giornaliero(dati)
        g = giorno_fx(dati).to_numpy()
        rng = np.random.default_rng(3)
        pronti = np.flatnonzero(intero["sentiment_classe"].notna().to_numpy())
        meta = pronti[(np.r_[g[1:] != g[:-1], True] == False)[pronti]]   # noqa: E712 (non ultima del giorno)
        diversi = 0
        for t in rng.choice(meta, 30, replace=False):
            svuota_cache()
            tagliato = sentiment_giornaliero(dati.iloc[:t + 1])
            diversi += sum(int((~((intero[c].iloc[:t + 1].isna() & tagliato[c].isna())
                                  | (intero[c].iloc[:t + 1] == tagliato[c]))).sum()) for c in COLONNE)
        check(f"C3. {nome}: 30 tagli a meta' giornata, serie tagliata = serie intera", diversi == 0,
              f"{diversi} valori diversi" if diversi else "")

    # =====================================================================
    print("\nD · RISCALDAMENTO: stesso valore da qualunque punto partano i dati\n" + "-" * 70)
    lungo = btc if btc is not None else _crypto_sintetico(1500, seme=9)
    svuota_cache()
    intero = sentiment_giornaliero(lungo)
    for partenza in (3001, 20000):
        svuota_cache()
        parziale = sentiment_giornaliero(lungo.iloc[partenza:])
        da = partenza + (M + 2 * P + 2) * 96
        confronto = lungo.index[da:]
        check(f"D. partenza alla barra {partenza}: identico dopo {M + 2 * P + 2} giornate"
              f" ({len(confronto)} barre confrontate)",
              len(confronto) > 10000 and all(_uguali(parziale[c].loc[confronto], intero[c].loc[confronto], 0)
                                             for c in COLONNE))

    # =====================================================================
    print("\nE · I 9 SYMBOL DI dati/ (solo conteggi)\n" + "-" * 70)
    righe, tutte_ok = [], True
    for symbol, df in reali.items():
        if df is None:
            saltato(f"E. {symbol}", "manca il file di dati")
            continue
        svuota_cache()
        s = sentiment_giornaliero(df)
        d = df.assign(**{c: s[c] for c in COLONNE})
        paura, avidita = filter_sent_extreme_fear(d), filter_sent_extreme_greed(d)
        pronte = d["sentiment_classe"].notna()
        righe.append({"symbol": symbol, "barre": len(d), "giornate": int(giorno_fx(df).iloc[-1]) + 1,
                      "classe dal": d.index[pronte.to_numpy().argmax()].date() if pronte.any() else None,
                      "F36 paura": int(paura.sum()), "F36 avidita'": int(avidita.sum()),
                      "% paura": round(100 * paura[pronte].mean(), 1),
                      "% avidita'": round(100 * avidita[pronte].mean(), 1)})
        tutte_ok &= bool(0 < paura.sum() < pronte.sum() and 0 < avidita.sum() < pronte.sum()
                         and 0.10 < paura[pronte].mean() < 0.30 and 0.10 < avidita[pronte].mean() < 0.30)
    if righe:
        with pd.option_context("display.width", 200, "display.max_columns", 20):
            print(pd.DataFrame(righe).set_index("symbol").to_string())
        check("E1. gira su tutti i symbol presenti; F36 ne' sempre vero ne' sempre falso, 10-30% delle barre pronte",
              tutte_ok)
    if btc is not None:
        R.clear_registry()
        for k, (f, direzione) in NUOVI.items():
            R.register_filter(k, direction=direzione)(f)
        svuota_cache()
        s = sentiment_giornaliero(btc)
        deg = verifica_degenerazione(btc.assign(**{c: s[c] for c in COLONNE}), verbose=False).set_index("nome")
        print(deg[["esito"]].T.to_string())
        check("E2. verifica_degenerazione su BTCUSD M15: tutte OK", (deg["esito"] == "OK").all(),
              str(deg["esito"].to_dict()))

    # =====================================================================
    print("\nF · REGISTRAZIONE\n" + "-" * 70)
    R.clear_registry()
    with contextlib.redirect_stdout(io.StringIO()):
        registra_filtri()
    check("F1. i filtri nuovi sono registrati con la direction giusta (paura +1, avidita' -1)",
          all(k in R.list_filters(direction=d) for k, (_, d) in NUOVI.items()))
    check("F2. la coppia SENTIMENT e' riconosciuta dalla ricerca dei filtri",
          ("SENTIMENT", "F36_SENT_EXTREME_FEAR", "F36_SENT_EXTREME_GREED") in R.list_filter_pairs())
    check("F3. le colonne nuove sono nell'elenco che il collaudo verifica", set(COLONNE) <= set(COLONNE_INDICATORI))
    check("F4. nel dizionario FILTRI con funzione, direction e pair giusti",
          all(FILTRI[k] == (f, d, "SENTIMENT") for k, (f, d) in NUOVI.items()))
    if reali["EURUSD"] is not None:
        import engine.indicatori as I
        pezzo = reali["EURUSD"].head(6000)
        svuota_cache()
        con = aggiungi_indicatori(pezzo)
        originale = I.sentiment_giornaliero
        try:   # senza il sentiment: le righe devono essere le stesse
            I.sentiment_giornaliero = lambda df, *a, **k: pd.DataFrame(0.0, index=df.index, columns=list(COLONNE))
            senza = I.aggiungi_indicatori(pezzo)
        finally:
            I.sentiment_giornaliero = originale
        check("F5. aggiungi_indicatori: il riscaldamento del sentiment (NaN) non toglie righe",
              con.index.equals(senza.index) and con["sentiment_score"].isna().all(),
              f"{len(con)} righe contro {len(senza)}")
    else:
        saltato("F5. righe di aggiungi_indicatori", "manca il file di dati")

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


def _giornate_valide(df: pd.DataFrame) -> list:
    """Giornate con almeno 3 barre utili (2 rendimenti), chiusura e volume positivi: entrano nelle finestre."""
    q = quarantena(df, verbose=False)["totale"].to_numpy()
    g = giorno_fx(df).to_numpy()
    tab = pd.DataFrame({"g": g[~q], "c": df["Close"].to_numpy()[~q], "v": df["Volume"].to_numpy()[~q]})
    conta = tab.groupby("g").agg(n=("c", "size"), c=("c", "last"), v=("v", "mean"))
    return list(conta.index[(conta["n"] >= 3) & (conta["c"] > 0) & (conta["v"] > 0)])


if __name__ == "__main__":
    sys.exit(main())
