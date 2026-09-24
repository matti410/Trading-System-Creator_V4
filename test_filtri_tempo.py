"""
Suite di validazione dei filtri di tempo (F20, F21, F22).

Si lancia da terminale, dalla cartella del progetto:

    python test_filtri_tempo.py

Non serve MetaTrader 5 e non serve nessun file di dati.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from engine.livelli import al_ultima_apertura, svuota_cache
from engine.quarantena import quarantena
from engine.registry import clear_registry, list_filter_pairs, list_filters
from filter_conditions import FILTRI, _variazione_notturna, registra_filtri

NUOVI = [k for k in FILTRI if k.startswith(("F20", "F21", "F22"))]


def esegui() -> int:
    """Esegue la suite. Ritorna 0 se tutto passa, 1 altrimenti."""
    ESITI = []

    def check(nome: str, condizione: bool, dettaglio: str = ""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def mercato(inizio: str, fine: str, seme: int = 0) -> pd.DataFrame:
        idx = pd.date_range(inizio, fine, freq="15min", tz="UTC", inclusive="left")
        ny = idx.tz_convert("America/New_York")
        minuti = ny.hour * 60 + ny.minute
        chiuso = (
            ((ny.dayofweek == 4) & (minuti >= 17 * 60))
            | (ny.dayofweek == 5)
            | ((ny.dayofweek == 6) & (minuti < 17 * 60))
        )
        idx = idx[~chiuso]
        rng = np.random.default_rng(seme)
        close = 1.10 + np.cumsum(rng.normal(0, 0.0004, len(idx)))
        op = np.r_[close[0], close[:-1]]
        salto = np.abs(rng.normal(0, 0.0003, len(idx)))
        return pd.DataFrame(
            {
                "Open": op,
                "High": np.maximum(op, close) + salto,
                "Low": np.minimum(op, close) - salto,
                "Close": close,
            },
            index=idx,
        )

    svuota_cache()
    df = mercato("2024-01-01", "2025-01-01")
    q = quarantena(df, verbose=False)
    ny = df.index.tz_convert("America/New_York")
    valori = {n: FILTRI[n][0](df) for n in NUOVI}

    print("\nFILTRI DI TEMPO — F20, F21, F22\n" + "-" * 70)

    # --- 1. regola 4: nessun filtro degenere ---------------------------
    degeneri = [n for n, s in valori.items() if s.all() or not s.any()]
    check("1. nessun filtro sempre vero o sempre falso", not degeneri, f"{degeneri}")

    # --- 2. copertura in una fascia sensata ----------------------------
    attese = {
        "F20_SESSION_ASIA": (0.20, 0.45),
        "F20_SESSION_EUROPE": (0.20, 0.45),
        "F20_SESSION_US": (0.20, 0.45),
        "F20_SESSION_OVERLAP": (0.08, 0.25),
        "F21_OVERNIGHT_UP": (0.35, 0.65),
        "F21_OVERNIGHT_DOWN": (0.35, 0.65),
        "F22_FAR_FROM_ROLLOVER": (0.65, 0.90),
    }
    for nome, (lo, hi) in attese.items():
        c = float(valori[nome].mean())
        check(f"2. {nome}: copertura fra {lo:.0%} e {hi:.0%}", lo <= c <= hi, f"{c:.1%}")

    # --- 3. mai su barre in quarantena ---------------------------------
    sporchi = {n: int((s & q["totale"]).sum()) for n, s in valori.items()}
    check("3. nessun filtro vero su barre in quarantena", sum(sporchi.values()) == 0,
          f"{ {k: v for k, v in sporchi.items() if v} }")

    # --- 4. OVERLAP contenuto in Europa e in USA -----------------------
    ov = valori["F20_SESSION_OVERLAP"]
    check(
        "4. OVERLAP e' contenuto sia in Europa sia in USA",
        bool((ov <= valori["F20_SESSION_EUROPE"]).all() and (ov <= valori["F20_SESSION_US"]).all()),
    )

    # --- 5. le sessioni agli orari locali giusti -----------------------
    ore_us = set(df.index[valori["F20_SESSION_US"]].tz_convert("America/New_York").hour)
    check("5a. SESSION_US copre solo le 08:00-16:xx di New York",
          ore_us <= set(range(8, 17)), f"ore NY: {sorted(ore_us)}")
    ore_eu = set(df.index[valori["F20_SESSION_EUROPE"]].tz_convert("Europe/London").hour)
    check("5b. SESSION_EUROPE copre solo le 08:00-16:xx di Londra",
          ore_eu <= set(range(8, 17)), f"ore Londra: {sorted(ore_eu)}")

    # --- 5c. anche nelle settimane con i DST sfasati -------------------
    marzo = (df.index >= "2024-03-11") & (df.index < "2024-03-31")
    ore_eu_m = set(
        df.index[valori["F20_SESSION_EUROPE"] & marzo].tz_convert("Europe/London").hour
    )
    check("5c. SESSION_EUROPE corretta nelle settimane con DST sfasati",
          ore_eu_m <= set(range(8, 17)), f"ore Londra: {sorted(ore_eu_m)}")

    # --- 6. F22: la soglia delle 4 ore e' rispettata -------------------
    minuti = ny.hour * 60 + ny.minute
    mancanti = pd.Series((17 * 60 - minuti) % 1440, index=df.index)
    lontano = valori["F22_FAR_FROM_ROLLOVER"]
    check("6a. F22 vero solo se mancano >= 4h al rollover",
          bool((mancanti[lontano] >= 240).all()), f"minimo osservato: {int(mancanti[lontano].min())} min")
    vicino = ~lontano & ~q["totale"]
    check("6b. F22 falso quando mancano < 4h",
          bool((mancanti[vicino] < 240).all()), f"massimo osservato: {int(mancanti[vicino].max())} min")

    # --- 7. F21: la coppia e' disgiunta e simmetrica -------------------
    su, giu = valori["F21_OVERNIGHT_UP"], valori["F21_OVERNIGHT_DOWN"]
    check("7a. UP e DOWN mai veri insieme", int((su & giu).sum()) == 0)
    n_su, n_giu = int(su.sum()), int(giu.sum())
    check("7b. su random walk UP e DOWN sono simmetrici",
          abs(n_su - n_giu) < 0.25 * max(n_su, n_giu), f"su {n_su} vs giu {n_giu}")

    # --- 8. F21 variante (b): il valore resta fermo 24 ore -------------
    v = _variazione_notturna(df)
    cambi = int((v.diff().fillna(0) != 0).sum())
    giorni = len(set(df.index.tz_convert("America/New_York").date))
    check(
        "8a. la variazione notturna cambia una volta al giorno, non di piu'",
        cambi <= giorni + 5,
        f"{cambi} cambi su ~{giorni} giornate",
    )
    # vale anche fuori dalla sessione americana: e' il punto della variante (b)
    notte = pd.Series((ny.hour >= 2) & (ny.hour < 6), index=df.index)
    check(
        "8b. la variazione e' definita anche alle 02:00-06:00 di New York",
        bool(v[notte].notna().mean() > 0.95),
        f"definita sul {v[notte].notna().mean():.1%} delle barre notturne",
    )

    # --- 9. al_ultima_apertura non guarda avanti -----------------------
    rng = np.random.default_rng(3)
    campione = sorted(rng.choice(np.arange(3000, len(df) - 10), size=8, replace=False))
    guasti = []
    pieno = _variazione_notturna(df)
    for t in campione:
        rovinato = df.copy()
        rovinato.iloc[t + 1 :, :4] = rng.normal(0, 50, (len(df) - t - 1, 4)) + 1000
        svuota_cache()
        parziale = _variazione_notturna(rovinato)
        a, b = pieno.iloc[t], parziale.iloc[t]
        if not ((pd.isna(a) and pd.isna(b)) or a == b):
            guasti.append((t, a, b))
    svuota_cache()
    check("9. LOOKAHEAD: il futuro non influenza la variazione notturna",
          not guasti, f"{len(campione)} barre — " + (f"{guasti[:2]}" if guasti else "nessuna differenza"))

    # --- 10. registrazione ---------------------------------------------
    clear_registry()
    registra_filtri()
    registrati = set(list_filters())
    check("10a. tutti i nuovi filtri risultano registrati",
          set(NUOVI) <= registrati, f"mancanti: {set(NUOVI) - registrati}")
    try:
        registra_filtri()
        check("10b. registrare due volte non solleva errore", True)
    except Exception as e:
        check("10b. registrare due volte non solleva errore", False, str(e)[:60])

    coppie = {c[0] for c in list_filter_pairs()}
    check("10c. la coppia OVERNIGHT_RETURN e' riconosciuta",
          "OVERNIGHT_RETURN" in coppie, f"coppie viste: {sorted(coppie)}")

    # --- 11. direction coerenti ----------------------------------------
    from engine.registry import get_filter_direction

    ok_dir = all(get_filter_direction(n) == FILTRI[n][1] for n in NUOVI)
    check("11. direction registrate come dichiarate", ok_dir)

    # --- 12. F21 il lunedi' usa la chiusura del VENERDI' (24/9/2026) ----
    # La chiusura attesa, calcolata a mano: l'ultima barra fra le 08:00 e le
    # 16:30 di New York del giorno di borsa precedente. Prima della
    # correzione di range_finestra il lunedi' usava quella di giovedi'.
    from engine.sessioni import barre_da_apertura

    svuota_cache()
    aperture = barre_da_apertura(df, "NEW_YORK").values
    apertura_usa = df["Open"].values[aperture]
    chiusura_usata = apertura_usa / (_variazione_notturna(df).values[aperture] + 1.0)
    m_ny = ny.hour * 60 + ny.minute
    in_orario = (m_ny >= 8 * 60) & (m_ny <= 16 * 60 + 30) & (ny.dayofweek < 5)
    chiusure_giorno = (
        pd.Series(df["Close"].values[in_orario], index=ny[in_orario])
        .groupby(ny[in_orario].date).last()
    )
    giorni_borsa = np.array(sorted(chiusure_giorno.index))
    precedente = np.searchsorted(giorni_borsa, ny[aperture].date) - 1
    attesa = np.where(
        precedente >= 0,
        chiusure_giorno.reindex(giorni_borsa[np.clip(precedente, 0, None)]).values,
        np.nan,
    )
    confrontabili = ~np.isnan(attesa) & ~np.isnan(chiusura_usata)
    sbagliate = confrontabili & ~np.isclose(attesa, chiusura_usata)
    lunedi = ny[aperture].dayofweek == 0
    check(
        "12. F21 usa la chiusura americana del giorno di borsa precedente (lunedi' -> venerdi')",
        int(sbagliate.sum()) == 0 and int((confrontabili & lunedi).sum()) > 40,
        f"{int(sbagliate.sum())} sbagliate su {int(confrontabili.sum())} aperture, "
        f"di cui {int((confrontabili & lunedi).sum())} di lunedi'",
    )
    svuota_cache()

    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
