"""
Livelli di riferimento ricavati da finestre temporali.

Serve alle entry che combinano TEMPO e PREZZO: il tempo definisce una
finestra, la finestra produce un livello, il prezzo decide quando lo rompe.

Due funzioni pubbliche:

    range_finestra(df, inizio, fine=None, quarantena=None)
    giorno_fx(df)

Il principio: niente futuro
---------------------------
Il valore alla barra `i` viene sempre da una finestra CHIUSA prima di `i`.
Finche' la finestra e' in corso, il livello resta quello precedente. E'
verificato per forza bruta nei test: sostituendo con spazzatura tutti i dati
dopo una barra, il valore in quella barra non cambia.

Confini e valori usano la quarantena in modo DIVERSO
----------------------------------------------------
- **I confini** della finestra vengono dal calendario puro, senza quarantena.
  Altrimenti `ROLLOVER` non scatterebbe mai (le sue barre sono sempre in
  quarantena) e la giornata FX non esisterebbe.

- **I valori** — massimo, minimo, prima apertura, ultima chiusura — escludono
  le barre in quarantena. E' il motivo per cui esiste lo strato 1: un massimo
  giornaliero segnato alle 17:15 di New York puo' essere un artefatto
  dell'allargamento dello spread sul bid, e romperlo non significherebbe
  niente.

Conseguenza concreta: la "chiusura della sessione americana" non e' la barra
delle 16:45, che e' in quarantena, ma l'ultima barra pulita, le 16:30 NY.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.quarantena import quarantena as _calcola_quarantena
from engine.sessioni import barre_da_apertura

# Cache: queste funzioni vengono chiamate una volta per entry, su df identici.
# La chiave e' l'identita' dell'indice (lunghezza, prima e ultima barra):
# se cambi dati, la cache si rinnova da sola.
_CACHE_Q: dict[tuple, pd.DataFrame] = {}
_CACHE_R: dict[tuple, pd.DataFrame] = {}


def _chiave(idx: pd.DatetimeIndex) -> tuple:
    return (len(idx), idx[0], idx[-1])


def quarantena_cached(df: pd.DataFrame) -> pd.DataFrame:
    """La quarantena di questo storico, calcolata una volta sola."""
    k = _chiave(pd.DatetimeIndex(df.index))
    if k not in _CACHE_Q:
        _CACHE_Q[k] = _calcola_quarantena(df, verbose=False)
    return _CACHE_Q[k]


def svuota_cache() -> None:
    """Forza il ricalcolo di quarantena e finestre."""
    _CACHE_Q.clear()
    _CACHE_R.clear()


# --------------------------------------------------------------- giorno FX --
def _data_fx(idx: pd.DatetimeIndex) -> np.ndarray:
    """
    La "data FX" di ogni barra: il giorno di contrattazione che inizia al
    rollover delle 17:00 di New York.

    Il trucco e' sommare 7 ore all'ora di New York, cosi' le 17:00 diventano
    la mezzanotte del giorno dopo e la data cambia esattamente al rollover.
    """
    return (idx.tz_convert("America/New_York") + pd.Timedelta(hours=7)).date


def _aperture_giorno_fx(df: pd.DataFrame) -> np.ndarray:
    """
    Indici delle barre che aprono una giornata FX: la prima barra di ogni
    data FX presente nello storico.

    NON si usa `barre_da_apertura(df, "ROLLOVER")` per i confini della
    giornata. Quella funzione scarta i giorni non feriali locali, e la
    riapertura settimanale cade la DOMENICA alle 17:00 di New York: verrebbe
    saltata, e il venerdi' si fonderebbe col lunedi' in un'unica giornata
    lunga tre giorni. Misurato sullo storico EURUSD: 1.396 giornate invece
    di 1.770.

    Il criterio per data FX regge anche festivi, buchi e riaperture tardive:
    quale che sia la prima barra di quella giornata, e' quella.
    """
    date = _data_fx(pd.DatetimeIndex(df.index))
    cambio = np.empty(len(date), dtype=bool)
    cambio[0] = True
    cambio[1:] = date[1:] != date[:-1]
    return np.flatnonzero(cambio)


def giorno_fx(df: pd.DataFrame) -> pd.Series:
    """
    Numero progressivo della giornata FX di ogni barra.

    La giornata FX va da un rollover al successivo (17:00 New York), non da
    mezzanotte a mezzanotte: e' il giorno di contrattazione vero del forex.

    Serve a imporre "un solo trigger al giorno": senza, una giornata che
    oscilla attorno a un livello produce molti segnali e l'indipendenza
    statistica delle osservazioni salta.
    """
    inizio = np.zeros(len(df), dtype=np.int64)
    inizio[_aperture_giorno_fx(df)] = 1
    return pd.Series(inizio.cumsum() - 1, index=df.index)


# ------------------------------------------------------------ range finestra --
def range_finestra(
    df: pd.DataFrame,
    inizio: str,
    fine: str | None = None,
    quarantena=None,
) -> pd.DataFrame:
    """
    Massimo, minimo, prima apertura e ultima chiusura dell'ULTIMA FINESTRA
    CONCLUSA, riportati su ogni barra.

    Parametri
    ---------
    inizio : nome di sessione del catalogo (`engine.sessioni.SESSIONI`). La
        finestra parte dalla sua barra di apertura.
    fine : nome di sessione dove la finestra si chiude, ESCLUSA la sua barra.
        `None` significa "fino alla prossima occorrenza di `inizio`", cioe'
        una finestra che copre l'intero ciclo.
    quarantena : il DataFrame di `quarantena()`, una Series, o None per
        calcolarla da sola (con cache).

    Esempi
    ------
        range_finestra(df, "TOKYO", "LONDRA")   il range asiatico
        range_finestra(df, "ROLLOVER")          la giornata FX intera
        range_finestra(df, "NEW_YORK")          la sessione americana

    Restituisce
    -----------
    DataFrame con lo stesso indice e cinque colonne:

        massimo        il massimo degli High della finestra
        minimo         il minimo dei Low
        primo_open     l'Open della prima barra utile
        ultimo_close   il Close dell'ultima barra utile
        pronto         False finche' non esiste una finestra conclusa

    Una finestra senza nessuna barra utile (tutte in quarantena, o un buco
    nello storico) produce NaN: non si inventa un livello che non c'e'.
    """
    idx = pd.DatetimeIndex(df.index)
    chiave = (_chiave(idx), inizio, fine, id(quarantena))
    if chiave in _CACHE_R:
        return _CACHE_R[chiave]

    n = len(idx)
    posizioni = np.arange(n)

    # --- confini: dal calendario PURO, senza quarantena ------------------
    # ROLLOVER e' un caso a se': i suoi confini sono le giornate FX, non gli
    # eventi di sessione, perche' la riapertura settimanale cade di domenica.
    if inizio == "ROLLOVER":
        i_start = _aperture_giorno_fx(df)
    else:
        i_start = np.flatnonzero(barre_da_apertura(df, inizio).values)
    if len(i_start) < 2:
        raise ValueError(
            f"Servono almeno due aperture di '{inizio}' per avere una "
            f"finestra conclusa; trovate {len(i_start)}."
        )

    ultimo_start = np.searchsorted(i_start, posizioni, side="right") - 1

    if fine is None:
        dentro = ultimo_start >= 0
        # la finestra k si chiude quando parte la k+1
        chiusure = i_start[1:]
        n_finestre = len(i_start) - 1
    else:
        i_fine = np.flatnonzero(barre_da_apertura(df, fine).values)
        if len(i_fine) == 0:
            raise ValueError(f"Nessuna apertura di '{fine}' trovata.")
        ultimo_fine = np.searchsorted(i_fine, posizioni, side="right") - 1
        # dentro se l'ultima chiusura vista e' PRIMA dell'ultima apertura
        dentro = (ultimo_start >= 0) & (
            (ultimo_fine < 0)
            | (i_fine[np.clip(ultimo_fine, 0, None)] < i_start[np.clip(ultimo_start, 0, None)])
        )
        # per ogni apertura, la prima chiusura successiva
        j = np.searchsorted(i_fine, i_start, side="right")
        valide = j < len(i_fine)
        # FIX (24/9/2026): le barre di una finestra ancora APERTA (la sua
        # chiusura non c'e' ancora nello storico) non appartengono a nessuna
        # finestra. Senza questa riga, quando lo storico finiva dentro una
        # finestra aperta, le sue barre venivano assegnate alla finestra
        # PRECEDENTE, gia' chiusa: il livello di ieri conteneva i prezzi di
        # oggi. Sullo storico intero toccava solo l'ultima giornata; nel live,
        # dove lo storico finisce sempre sulla barra corrente, era la
        # situazione normale. Trovato da engine/collaudo_catalogo.py
        # (verifica_lookahead per troncamento) su E22 e F21.
        dentro = dentro & np.where(
            ultimo_start >= 0, valide[np.clip(ultimo_start, 0, None)], False
        )
        chiusure = i_fine[j[valide]]
        i_start = i_start[valide]
        ultimo_start = np.searchsorted(i_start, posizioni, side="right") - 1
        dentro = dentro & (ultimo_start >= 0)
        n_finestre = len(chiusure)

    if n_finestre == 0:
        raise ValueError("Nessuna finestra conclusa nello storico.")

    gruppo = np.where(dentro, ultimo_start, -1)

    # --- valori: le barre in quarantena NON contribuiscono ---------------
    if quarantena is None:
        q = quarantena_cached(df)["totale"].values
    elif isinstance(quarantena, pd.DataFrame):
        q = quarantena["totale"].reindex(idx).fillna(False).values.astype(bool)
    else:
        q = pd.Series(quarantena).reindex(idx).fillna(False).values.astype(bool)

    utile = (gruppo >= 0) & ~q
    g = gruppo[utile]

    agg = pd.DataFrame(
        {
            "g": g,
            "High": df["High"].values[utile],
            "Low": df["Low"].values[utile],
            "Open": df["Open"].values[utile],
            "Close": df["Close"].values[utile],
        }
    ).groupby("g")

    vuoto = np.full(n_finestre, np.nan)
    v_max, v_min = vuoto.copy(), vuoto.copy()
    v_open, v_close = vuoto.copy(), vuoto.copy()

    presenti = agg["High"].max()
    dentro_range = presenti.index[presenti.index < n_finestre]
    v_max[dentro_range] = presenti.loc[dentro_range].values
    v_min[dentro_range] = agg["Low"].min().loc[dentro_range].values
    v_open[dentro_range] = agg["Open"].first().loc[dentro_range].values
    v_close[dentro_range] = agg["Close"].last().loc[dentro_range].values

    # --- propagazione: alla barra i vale l'ultima finestra CHIUSA --------
    k = np.searchsorted(chiusure, posizioni, side="right") - 1
    pronto = k >= 0
    k_safe = np.clip(k, 0, n_finestre - 1)

    out = pd.DataFrame(
        {
            "massimo": np.where(pronto, v_max[k_safe], np.nan),
            "minimo": np.where(pronto, v_min[k_safe], np.nan),
            "primo_open": np.where(pronto, v_open[k_safe], np.nan),
            "ultimo_close": np.where(pronto, v_close[k_safe], np.nan),
            "pronto": pronto,
        },
        index=idx,
    )

    _CACHE_R[chiave] = out
    return out


# ------------------------------------------------------------- utilita' ----
def al_ultima_apertura(df: pd.DataFrame, sessione: str, serie: pd.Series) -> pd.Series:
    """
    Il valore di `serie` letto sull'ULTIMA barra di apertura della sessione,
    e portato avanti fino all'apertura successiva.

    Serve a "fotografare" una grandezza al momento dell'apertura e tenerla
    ferma per tutto il ciclo. Senza questo, una grandezza che si aggiorna da
    sola cambia significato a meta' giornata: la variazione notturna
    calcolata alle 03:00 di New York userebbe la chiusura americana
    sbagliata e diventerebbe il rendimento intraday del giorno prima, con
    il segno rovesciato. Nessun errore, numero senza senso.

    Non c'e' lookahead: si legge solo su barre gia' passate.
    """
    aperture = barre_da_apertura(df, sessione).values  # confini: niente quarantena
    fotografia = pd.Series(np.nan, index=df.index)
    fotografia[aperture] = pd.Series(serie).reindex(df.index).values[aperture]
    return fotografia.ffill()


def primo_del_giorno(mask: pd.Series, df: pd.DataFrame) -> pd.Series:
    """
    Tiene solo la PRIMA barra vera di ogni giornata FX.

    Trasforma una condizione che puo' ripetersi in un evento a singola
    occorrenza giornaliera.
    """
    mask = mask.fillna(False).astype(bool)
    giorno = giorno_fx(df)
    progressivo = mask.groupby(giorno).cumsum()
    return mask & (progressivo == 1) & (giorno >= 0)
