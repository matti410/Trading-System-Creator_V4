"""
Strato 1 — le barre di cui NON ci fidiamo.

Due funzioni, da usare in quest'ordine subito dopo il caricamento dei dati:

    verifica_indice_utc(df)   si ferma se l'indice non e' UTC vero
    q = quarantena(df)        marca le barre non affidabili

Perche' esiste questo modulo
----------------------------
Le barre MT5 sono costruite sul prezzo BID. Intorno al rollover delle 17:00
di New York lo spread si allarga: l'ask sale, il bid scende, poi lo spread
rientra e il bid risale anche se il prezzo di mercato non si e' mosso.

Un minimo di quelle barre puo' essere un minimo del BID, non del mercato.
Un long aperto li' incassa il rientro dello spread senza che il prezzo si
sia mosso. E' la spiegazione piu' probabile del vecchio "segnale" T1_ASIA.

La finestra di default NON e' una stima prudente: e' misurata. Sulla colonna
`spread` di EURUSD M15 (IC Markets, 2020-2026), che riporta lo spread MINIMO
della barra, la quota di barre con spread diverso da zero e':

    16:30 NY    0.9%      <- pulito
    16:45 NY   22.6%      <- inizia l'allargamento
    17:00 NY   91.1%      \\
    17:15 NY   92.4%       |  spread minimo mediano 11-14 punti (1.1-1.4 bp)
    17:30 NY   92.8%       |  per TUTTA la barra, non solo per un istante
    17:45 NY   92.6%      /
    18:00 NY    1.8%      <- rientrato

Da cui 16:45 -> 18:00, cioe' 5 barre M15 al giorno (~5% delle barre).

Trattandosi del MINIMO della barra, quei numeri sono un limite inferiore:
lo spread vero in quella finestra e' piu' largo, non piu' stretto.

Chi usa questo modulo
---------------------
`engine/sessioni.py`, che non fa scattare eventi su barre in quarantena.
"""
from __future__ import annotations

import pandas as pd

# Finestra del rollover, in ora locale di New York. Vedi docstring sopra.
ROLLOVER_DEFAULT = ("16:45", "18:00")
TZ_ROLLOVER = "America/New_York"


# --------------------------------------------------------------- utility --
def _minuti(orario: str) -> int:
    """'16:45' -> 1005 (minuti dalla mezzanotte locale)."""
    ore, minuti = orario.split(":")
    return int(ore) * 60 + int(minuti)


def passo_barre(index: pd.DatetimeIndex) -> pd.Timedelta:
    """
    Durata di una barra, dedotta dall'indice (la differenza piu' frequente).

    Si usa la moda e non la mediana perche' con molti buchi la mediana
    resta corretta ma la moda e' piu' robusta ai timeframe irregolari.
    """
    diff = pd.Series(index).diff().dropna()
    if diff.empty:
        raise ValueError("Indice troppo corto per dedurre il timeframe.")
    return pd.Timedelta(diff.mode().iloc[0])


def _sovrappone(inizio_min, durata_min: int, win_inizio: int, win_fine: int):
    """
    True dove la barra [inizio, inizio+durata) si sovrappone alla finestra
    giornaliera [win_inizio, win_fine), entrambe in minuti dalla mezzanotte
    locale.

    Si usa la sovrapposizione e non "inizia dentro la finestra" perche' su
    timeframe piu' larghi di M15 una barra puo' contenere il rollover senza
    iniziare dentro la finestra: su H1 la barra delle 16:00 contiene le
    16:45 e va marcata.

    La finestra viene provata anche traslata di +/- un giorno, cosi' il
    codice regge anche una finestra che attraversa la mezzanotte.
    """
    fine_min = inizio_min + durata_min
    dentro = None
    for offset in (-1440, 0, 1440):
        colpo = (inizio_min < win_fine + offset) & (fine_min > win_inizio + offset)
        dentro = colpo if dentro is None else (dentro | colpo)
    return dentro


# ---------------------------------------------------- verifica dell'indice --
def verifica_indice_utc(df: pd.DataFrame, verbose: bool = True) -> None:
    """
    Si ferma se l'indice non e' UTC vero. Non restituisce nulla.

    Difende dall'"etichetta UTC fantasma": un indice marcato UTC che in
    realta' contiene ora server. Non provoca errori da solo, ma il giorno in
    cui qualcuno converte in ora di borsa sposta tutto di 2-3 ore in
    silenzio. Va chiamata PRIMA di qualunque codice basato sul tempo.

    Il criterio usa solo i timestamp: la riapertura settimanale del forex
    cade la domenica alle 17:00 ora di New York. Se l'indice e' UTC vero,
    le prime barre dopo la pausa del weekend ci cadono sopra.

    Non verifica i prezzi e non verifica la regola del fuso del broker:
    quella si stabilisce una volta sola con `diagnose_broker_offset`.

    Simboli 24/7 (cripto): non esistendo la pausa del weekend il controllo
    non e' possibile. Stampa un avviso e prosegue.
    """
    idx = pd.DatetimeIndex(df.index)

    if idx.tz is None:
        raise ValueError(
            "L'indice non ha fuso orario: sono ancora ore SERVER.\n"
            "Convertilo prima con:\n"
            "    from engine.broker_tz_diagnostic import to_utc_index\n"
            "    df = to_utc_index(df, 'A_US_DST (NY+7h)')"
        )

    if str(idx.tz) not in ("UTC", "utc"):
        raise ValueError(
            f"L'indice e' in fuso {idx.tz}, non UTC. Questo modulo si aspetta UTC."
        )

    passo = passo_barre(idx)
    salto = pd.Series(idx).diff()
    # Una pausa del weekend dura ~48h; 12h separa il weekend da ogni altro buco.
    riaperture = idx[(salto > pd.Timedelta(hours=12)).fillna(False).values]

    if len(riaperture) < 10:
        if verbose:
            print(
                "[verifica_indice_utc] nessuna pausa di weekend trovata: "
                "simbolo 24/7. Il controllo non e' possibile, proseguo.\n"
                "  La correttezza dell'indice va verificata su un simbolo forex."
            )
        return

    ny = riaperture.tz_convert(TZ_ROLLOVER)
    atteso = (ny.dayofweek == 6) & (ny.hour == 17) & (ny.minute == 0)
    quota = float(atteso.mean())

    if quota < 0.80:
        sbagliate = ny[~atteso]
        raise ValueError(
            f"L'indice e' etichettato UTC ma non sembra UTC vero.\n"
            f"Solo il {quota:.1%} delle {len(ny)} riaperture settimanali cade "
            f"la domenica alle 17:00 di New York (atteso: oltre il 95%).\n"
            f"Primi casi anomali (ora di New York): {list(sbagliate[:3])}\n\n"
            "Causa tipica: un tz_localize('UTC') applicato a ore SERVER.\n"
            "Rimedio:\n"
            "    df.index = df.index.tz_localize(None)\n"
            "    df = to_utc_index(df, 'A_US_DST (NY+7h)')"
        )

    if verbose:
        print(
            f"[verifica_indice_utc] OK — {quota:.1%} delle {len(ny)} riaperture "
            f"cade domenica 17:00 New York. Barre da {passo}."
        )


# ------------------------------------------------------------- quarantena --
def quarantena(
    df: pd.DataFrame,
    rollover: tuple[str, str] | None = ROLLOVER_DEFAULT,
    soglia_interruzione_min: int = 60,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Marca le barre non affidabili. Da calcolare UNA volta dopo il caricamento
    e passare a chi ne ha bisogno.

    Parametri
    ---------
    rollover : ("16:45", "18:00") in ora locale di New York, oppure None per
        disattivare la finestra. Il default e' misurato sui dati: vedi la
        docstring del modulo.
    soglia_interruzione_min : sopra questo distacco fra due barre consecutive,
        la barra successiva e' marcata. 60 minuti separa i weekend, i festivi
        e i buchi veri (come il 2021-12-02) dalla normale spaziatura M15.

    Restituisce
    -----------
    Un DataFrame con lo stesso indice di `df` e tre colonne booleane:

        rollover            la barra si sovrappone alla finestra del rollover
        dopo_interruzione   e' la prima barra dopo una pausa (weekend,
                            festivo, buco nello storico)
        totale              una delle due -> NON usare questa barra

    Nota su `dopo_interruzione`: la prima barra dopo una pausa ha gap di
    prezzo e spread largo. Marcarla e' prudenza, non un difetto dei dati.
    """
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        raise ValueError(
            "quarantena() richiede un indice UTC. Chiama prima verifica_indice_utc()."
        )

    q = pd.DataFrame(index=idx.copy())

    # --- finestra del rollover -------------------------------------------
    if rollover is None:
        q["rollover"] = False
    else:
        inizio, fine = _minuti(rollover[0]), _minuti(rollover[1])
        locale = idx.tz_convert(TZ_ROLLOVER)
        inizio_min = locale.hour * 60 + locale.minute
        durata_min = int(passo_barre(idx).total_seconds() // 60)
        q["rollover"] = _sovrappone(inizio_min, durata_min, inizio, fine)

    # --- prima barra dopo una pausa --------------------------------------
    salto = pd.Series(idx).diff()
    soglia = pd.Timedelta(minutes=soglia_interruzione_min)
    # La prima barra in assoluto ha diff NaT: non e' "dopo una pausa",
    # e' l'inizio dello storico. Resta non marcata.
    q["dopo_interruzione"] = (salto > soglia).fillna(False).values

    q["totale"] = q["rollover"] | q["dopo_interruzione"]

    if verbose:
        n = len(q)
        print(f"[quarantena] {n} barre esaminate")
        for col in ("rollover", "dopo_interruzione", "totale"):
            k = int(q[col].sum())
            print(f"    {col:<20} {k:>7}  ({k / n:.2%})")
        if rollover is not None:
            print(f"    finestra rollover: {rollover[0]}-{rollover[1]} ora di New York")

    return q
