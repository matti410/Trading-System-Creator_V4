"""
engine/controlli.py — controlli automatici sui risultati di una ricerca.

Modulo ADDITIVO: non modifica `exit_search.py` ne' gli altri file
dell'engine. Si limita a leggere la tabella dei risultati e ad alzare la
voce quando trova qualcosa che non torna.

PERCHE' ESISTE
--------------
Il difetto piu' grave trovato finora nella ricerca delle uscite (trade da
47 barre su un tetto di 32, e in un caso limite una posizione mai chiusa
su tutta la serie) e' stato scoperto guardando a occhio una colonna
diagnostica. Un difetto che si vede solo se qualcuno lo guarda, prima o
poi torna. Qui diventa un controllo che parla da solo.

COSA CONTROLLA
--------------
`durata_max > n_richiesto`, in senso stretto. Un trade che apre alla barra
`i` e chiude alla `i+n` dura esattamente n barre: e' il comportamento
corretto, non una violazione. Si viola solo andando OLTRE il tetto.

Le righe "senza scadenza" (n_barre = 0) non hanno un tetto temporale:
vengono escluse dal controllo, non promosse.

Caso estremo segnalato a parte: posizione mai chiusa, cioe' durata_max
paragonabile alla lunghezza dell'intera serie. E' il sintomo peggiore
perche' falsa tutte le metriche della riga, non solo la durata.

COSA NON CONTROLLA
------------------
Il fatto che i trade chiudano PRIMA del tetto non e' un difetto: con SL/TP
attivi e' il comportamento atteso, ed e' esattamente quello che misura
`controllo_durate()`. Questo modulo guarda solo lo sforamento.

USO
---
    import engine as eng

    es = eng.ricerca_uscite(df_is, entry_long="...", n_barre=(16, 32))
    # il controllo scatta da solo; il dettaglio resta in es.scadenze

oppure, su un risultato gia' in mano:

    eng.verifica_scadenze(es)
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .exit_search import run_exit_search, due_meta   # noqa: F401

__all__ = ["verifica_scadenze", "ricerca_uscite", "due_meta_controllato"]


# l'etichetta di colonna e' del tipo "SOLO_TEMPO · 32 barre"
_RE_N_BARRE = re.compile(r"·\s*(\d+)\s*barre")


def _estrai_n(etichetta) -> float:
    """Orizzonte richiesto letto dall'etichetta. NaN se la riga non ha
    scadenza temporale."""
    if not isinstance(etichetta, str):
        return np.nan
    trovato = _RE_N_BARRE.search(etichetta)
    return float(trovato.group(1)) if trovato else np.nan


def _scompatta(oggetto):
    """Accetta un ExitSearch oppure direttamente la tabella dei risultati.
    Restituisce (risultati, lunghezza_serie_o_None)."""
    ris = getattr(oggetto, "risultati", oggetto)
    if not isinstance(ris, pd.DataFrame):
        raise TypeError(
            "verifica_scadenze vuole un ExitSearch (quello che torna da "
            "run_exit_search) oppure la sua tabella .risultati."
        )
    mancanti = {"combinazione", "durata_max"} - set(ris.columns)
    if mancanti:
        raise ValueError(f"Colonne assenti nella tabella: {sorted(mancanti)}")

    lunghezza = None
    pf = getattr(oggetto, "portfolio", None)
    if pf is not None:
        try:
            lunghezza = int(len(pf.wrapper.index))
        except Exception:
            lunghezza = None
    return ris, lunghezza


def verifica_scadenze(oggetto, verbose=True, etichetta_run=""):
    """
    L'uscita a tempo e' stata rispettata da TUTTE le combinazioni?

    Parametri
    ---------
    oggetto : ExitSearch o DataFrame
        Il risultato di `run_exit_search`, o la sua tabella `.risultati`.
    verbose : bool
        Se True stampa l'esito. Con violazioni la stampa e' rumorosa
        apposta: questo controllo esiste per farsi notare.
    etichetta_run : str
        Testo aggiuntivo nell'intestazione (utile in `due_meta`, dove i
        run sono due).

    Ritorna
    -------
    DataFrame delle sole righe fuori norma, ordinate per gravita'.
    Vuoto (len == 0) quando e' tutto in regola: si puo' usare
    direttamente come condizione, `if len(esito):`.
    """
    ris, lunghezza = _scompatta(oggetto)

    r = ris.copy()
    r["n_richiesto"] = r["combinazione"].map(_estrai_n)
    con_tetto = r[r["n_richiesto"].notna()].copy()

    fuori = con_tetto[con_tetto["durata_max"] > con_tetto["n_richiesto"]].copy()
    fuori["esubero_barre"] = fuori["durata_max"] - fuori["n_richiesto"]
    fuori["esubero_x"] = fuori["durata_max"] / fuori["n_richiesto"]

    # posizione mai chiusa: durata paragonabile all'intera serie
    if lunghezza:
        fuori["mai_chiusa"] = fuori["durata_max"] >= 0.9 * lunghezza
    else:
        fuori["mai_chiusa"] = False

    colonne = ["combinazione", "n_richiesto", "durata_max", "esubero_barre",
               "esubero_x", "mai_chiusa", "trades"]
    colonne = [c for c in colonne if c in fuori.columns]
    fuori = fuori[colonne].sort_values("esubero_x", ascending=False)

    if verbose:
        testa = f" [{etichetta_run}]" if etichetta_run else ""
        n_tot = len(con_tetto)
        if n_tot == 0:
            print(f"controllo scadenze{testa}: nessuna riga con tetto "
                  f"temporale (tutte 'senza scadenza') — niente da verificare.")
        elif len(fuori) == 0:
            print(f"controllo scadenze{testa}: OK — {n_tot} combinazioni "
                  f"con tetto temporale, nessuno sforamento.")
        else:
            riga = "=" * 68
            print(riga)
            print(f"  ATTENZIONE{testa}: SCADENZA TEMPORALE SFORATA in "
                  f"{len(fuori)} combinazioni su {n_tot}")
            print(riga)
            for _, x in fuori.iterrows():
                extra = "  <-- POSIZIONE MAI CHIUSA" if x.get("mai_chiusa") else ""
                print(f"  {x['combinazione']:<34} tetto {int(x['n_richiesto']):>4} "
                      f"· durata_max {int(x['durata_max']):>5} "
                      f"({x['esubero_x']:.1f}x){extra}")
            print(riga)
            print("  Le metriche di queste righe NON sono attendibili: il")
            print("  trade e' rimasto aperto oltre l'orizzonte che stai")
            print("  misurando. Causa tipica: un ingresso e un'uscita sulla")
            print("  stessa barra, con l'uscita ignorata dal motore.")
            print("  Dettaglio completo nella tabella restituita.")
            print(riga)

    return fuori


def ricerca_uscite(df, **kwargs):
    """
    Come `run_exit_search`, ma esegue da sola la verifica delle scadenze.

    Stessi parametri e stesso oggetto di ritorno, con in piu'
    `es.scadenze`: la tabella delle righe fuori norma (vuota se tutto a
    posto).

    E' la porta d'ingresso da usare di default: il controllo non dipende
    piu' dal fatto che qualcuno si ricordi di lanciarlo.
    """
    es = run_exit_search(df, **kwargs)
    es.scadenze = verifica_scadenze(es, verbose=kwargs.get("verbose", True))
    return es


def due_meta_controllato(df, **kwargs):
    """
    Come `due_meta`, con la verifica delle scadenze su ciascuna meta'.

    Ritorna (tabella_affiancata, scadenze_meta1, scadenze_meta2).
    """
    meta = len(df) // 2
    kw = dict(kwargs)
    kw.setdefault("verbose", False)

    es1 = run_exit_search(df.iloc[:meta], **kw)
    es2 = run_exit_search(df.iloc[meta:], **kw)
    s1 = verifica_scadenze(es1, verbose=True, etichetta_run="prima meta'")
    s2 = verifica_scadenze(es2, verbose=True, etichetta_run="seconda meta'")

    cols = ["combinazione", "trades", "pnl_pct", "sharpe", "max_dd_pct",
            "profit_factor"]
    m = es1.risultati[cols].merge(es2.risultati[cols], on="combinazione",
                                  suffixes=("_1", "_2"))
    m["coerente"] = ((m["sharpe_1"] > 0) & (m["sharpe_2"] > 0) &
                     (np.sign(m["pnl_pct_1"]) == np.sign(m["pnl_pct_2"])))
    return m.sort_values("sharpe_2", ascending=False).round(3), s1, s2
