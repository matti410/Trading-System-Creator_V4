"""
Suite di validazione dei livelli e delle entry tempo + prezzo.

Si lancia da terminale, dalla cartella del progetto:

    python test_tempo_prezzo.py

Non serve MetaTrader 5 e non serve nessun file di dati.

Il test centrale e' il n. 1: la verifica di LOOKAHEAD a forza bruta.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from engine.livelli import (
    giorno_fx,
    primo_del_giorno,
    range_finestra,
    svuota_cache,
)
from engine.quarantena import quarantena
from entry_long import entry_asian_range_breakout, entry_prev_day_high_breakout
from entry_short import (
    entry_short_asian_range_breakdown,
    entry_short_prev_day_low_breakdown,
)


def esegui() -> int:
    """Esegue la suite. Ritorna 0 se tutto passa, 1 altrimenti."""
    ESITI = []

    def check(nome: str, condizione: bool, dettaglio: str = ""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def mercato(inizio: str, fine: str, seme: int = 0) -> pd.DataFrame:
        """Random walk su indice UTC, weekend forex tolto."""
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

    df = mercato("2024-01-01", "2025-01-01")

    # ===================================================================
    print("\nLOOKAHEAD — il test che conta\n" + "-" * 70)

    # --- 1. forza bruta: il futuro sostituito con spazzatura -----------
    rng = np.random.default_rng(7)
    campione = sorted(rng.choice(np.arange(3000, len(df) - 10), size=12, replace=False))
    finestre = [("TOKYO", "LONDRA"), ("ROLLOVER", None), ("NEW_YORK", None)]

    guasti = []
    for inizio, fine in finestre:
        svuota_cache()
        pieno = range_finestra(df, inizio, fine)
        for t in campione:
            rovinato = df.copy()
            # tutto DOPO la barra t diventa spazzatura: prezzi x1000 e caotici
            coda = slice(t + 1, None)
            rumore = rng.normal(0, 50, (len(df) - t - 1, 4)) + 1000
            rovinato.iloc[coda, :4] = rumore
            svuota_cache()
            parziale = range_finestra(rovinato, inizio, fine)
            for col in ("massimo", "minimo", "primo_open", "ultimo_close"):
                a, b = pieno[col].iloc[t], parziale[col].iloc[t]
                if not ((pd.isna(a) and pd.isna(b)) or a == b):
                    guasti.append((inizio, fine, col, t, a, b))

    check(
        "1. LOOKAHEAD: il futuro non influenza i livelli",
        not guasti,
        f"{len(campione)} barre x {len(finestre)} finestre x 4 colonne — "
        + (f"{len(guasti)} DIFFERENZE: {guasti[:2]}" if guasti else "nessuna differenza"),
    )
    svuota_cache()

    # ===================================================================
    print("\nLIVELLI — engine/livelli.py\n" + "-" * 70)

    # --- 2. il livello resta fermo dentro la finestra ------------------
    r = range_finestra(df, "ROLLOVER")
    g = giorno_fx(df)
    cambi_per_giorno = (
        pd.Series(r["massimo"].values)
        .groupby(g.values)
        .apply(lambda s: int((s.diff().fillna(0) != 0).sum()))
    )
    check(
        "2. il livello non cambia dentro la giornata FX",
        int(cambi_per_giorno.max()) == 0,
        f"massimo cambi in una giornata: {int(cambi_per_giorno.max())}",
    )

    # --- 3. giornata FX: conteggio e ancoraggio ------------------------
    n_giorni = int(g.max()) + 1
    ny = df.index.tz_convert("America/New_York")
    # la prima giornata dello storico e' parziale: comincia dove cominciano
    # i dati, non al rollover. Si esclude.
    prima = df.index[np.flatnonzero(g.diff().fillna(1).values != 0)][1:]
    ore_inizio = set(prima.tz_convert("America/New_York").strftime("%H:%M"))
    check(
        "3a. giornate FX in numero plausibile",
        240 <= n_giorni <= 270,
        f"{n_giorni} giornate su un anno",
    )
    check(
        "3b. ogni giornata FX completa comincia alle 17:00 di New York",
        ore_inizio <= {"17:00"},
        f"orari di inizio: {sorted(ore_inizio)}",
    )
    dom = sum(1 for p in prima.tz_convert("America/New_York") if p.dayofweek == 6)
    check(
        "3c. le riaperture della domenica sono incluse",
        dom > 40,
        f"{dom} giornate FX iniziano di domenica (la riapertura settimanale)",
    )

    # --- 4. la quarantena non entra nei livelli ------------------------
    q = quarantena(df, verbose=False)
    sporco = df.copy()
    picco = float(df["High"].max() * 2)
    sporco.loc[q["rollover"], "High"] = picco
    sporco.loc[q["rollover"], "Low"] = -picco
    svuota_cache()
    r_sporco = range_finestra(sporco, "ROLLOVER")
    svuota_cache()
    r_pulito = range_finestra(df, "ROLLOVER")
    check(
        "4. un picco assurdo dentro la quarantena non entra nei livelli",
        r_sporco["massimo"].equals(r_pulito["massimo"])
        and r_sporco["minimo"].equals(r_pulito["minimo"]),
        f"picco iniettato: {picco:.2f}",
    )

    # --- 5. pronto ------------------------------------------------------
    check(
        "5. `pronto` falso prima della prima finestra conclusa",
        not bool(r_pulito["pronto"].iloc[0]) and bool(r_pulito["pronto"].iloc[-1]),
        f"prima barra {r_pulito['pronto'].iloc[0]}, ultima {r_pulito['pronto'].iloc[-1]}",
    )

    # --- 6. il range asiatico e' contenuto nella giornata --------------
    ra = range_finestra(df, "TOKYO", "LONDRA")
    rg = range_finestra(df, "ROLLOVER")
    valide = ra["pronto"] & rg["pronto"] & ra["massimo"].notna() & rg["massimo"].notna()
    check(
        "6. il range asiatico e' piu' stretto della giornata intera",
        bool(((ra["massimo"] - ra["minimo"]) <= (rg["massimo"] - rg["minimo"]) * 1.5)[valide].mean() > 0.95),
        "coerenza di ampiezza",
    )

    # ===================================================================
    print("\nENTRY — E22 e E23\n" + "-" * 70)

    ENTRY = {
        "E22_ASIAN_RANGE_BREAKOUT": entry_asian_range_breakout,
        "E22_SHORT_ASIAN_RANGE_BREAKDOWN": entry_short_asian_range_breakdown,
        "E23_PREV_DAY_HIGH_BREAKOUT": entry_prev_day_high_breakout,
        "E23_SHORT_PREV_DAY_LOW_BREAKDOWN": entry_short_prev_day_low_breakdown,
    }
    segnali = {nome: f(df) for nome, f in ENTRY.items()}

    # --- 7. un solo trigger al giorno ----------------------------------
    for nome, s in segnali.items():
        per_giorno = s.groupby(g).sum()
        check(
            f"7. {nome}: mai piu' di un trigger al giorno",
            int(per_giorno.max()) <= 1,
            f"{int(s.sum())} trigger, max {int(per_giorno.max())} al giorno",
        )

    # --- 8. long e short mai insieme -----------------------------------
    for coppia in (("E22_ASIAN_RANGE_BREAKOUT", "E22_SHORT_ASIAN_RANGE_BREAKDOWN"),
                   ("E23_PREV_DAY_HIGH_BREAKOUT", "E23_SHORT_PREV_DAY_LOW_BREAKDOWN")):
        insieme = int((segnali[coppia[0]] & segnali[coppia[1]]).sum())
        check(f"8. {coppia[0][:3]}: long e short mai sulla stessa barra", insieme == 0,
              f"{insieme} barre in comune")

    # --- 9. nessuna entry degenere -------------------------------------
    degeneri = [n for n, s in segnali.items() if s.all() or not s.any()]
    check("9. nessuna entry sempre vera o sempre falsa", not degeneri, f"{degeneri}")

    # --- 10. E22 solo nella finestra dichiarata ------------------------
    for nome in ("E22_ASIAN_RANGE_BREAKOUT", "E22_SHORT_ASIAN_RANGE_BREAKDOWN"):
        ore = df.index[segnali[nome]].tz_convert("America/New_York")
        minuti = ore.hour * 60 + ore.minute
        dentro = bool(((minuti >= 3 * 60) & (minuti < 17 * 60)).all())
        check(
            f"10. {nome}: scatta solo fra apertura Londra e chiusura NY",
            dentro,
            f"finestra oraria NY osservata: {minuti.min()//60}:00–{minuti.max()//60}:00",
        )

    # --- 11. mai su barre in quarantena --------------------------------
    sporche = sum(int((s & q["totale"]).sum()) for s in segnali.values())
    check("11. nessun trigger su barre in quarantena", sporche == 0, f"{sporche} barre")

    # --- 12. su random walk i trigger sono pochi e simmetrici ----------
    n_long = int(segnali["E23_PREV_DAY_HIGH_BREAKOUT"].sum())
    n_short = int(segnali["E23_SHORT_PREV_DAY_LOW_BREAKDOWN"].sum())
    check(
        "12. su random walk long e short sono all'incirca simmetrici",
        abs(n_long - n_short) < 0.45 * max(n_long, n_short),
        f"long {n_long} vs short {n_short}",
    )

    # --- 13. primo_del_giorno ------------------------------------------
    sempre = pd.Series(True, index=df.index)
    uno = primo_del_giorno(sempre, df)
    check(
        "13. primo_del_giorno: esattamente un trigger per giornata",
        int(uno.sum()) == n_giorni,
        f"{int(uno.sum())} trigger su {n_giorni} giornate",
    )

    # ===================================================================
    ok, tot = sum(ESITI), len(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
