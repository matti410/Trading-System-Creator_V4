"""
Suite di validazione delle entry-metro.

Si lancia da terminale, dalla cartella del progetto:

    python test_entry_metro.py

Non serve MetaTrader 5 e non serve nessun file di dati.
"""
from __future__ import annotations

import sys

import pandas as pd

from engine.registry import clear_registry, get_entry_direction, list_entries
from entry_metro import (
    NOMI_METRO,
    TRIGGER_METRO,
    aggiungi_trigger_metro,
    quarantena_cached,
    registra_trigger_metro,
    svuota_cache,
)

ESITI = []


def check(nome: str, condizione: bool, dettaglio: str = ""):
    ESITI.append(bool(condizione))
    stato = "OK     " if condizione else "FALLITO"
    print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))


def mercato(inizio: str, fine: str) -> pd.DataFrame:
    idx = pd.date_range(inizio, fine, freq="15min", tz="UTC", inclusive="left")
    ny = idx.tz_convert("America/New_York")
    minuti = ny.hour * 60 + ny.minute
    chiuso = (
        ((ny.dayofweek == 4) & (minuti >= 17 * 60))
        | (ny.dayofweek == 5)
        | ((ny.dayofweek == 6) & (minuti < 17 * 60))
    )
    idx = idx[~chiuso]
    return pd.DataFrame({"Open": 1.0, "Close": 1.0}, index=idx)


ORARI_ATTESI = {
    "M_TOKYO": ("Asia/Tokyo", "09:00"),
    "M_LONDRA": ("Europe/London", "08:00"),
    "M_NEW_YORK": ("America/New_York", "08:00"),
    "M_NYSE": ("America/New_York", "09:30"),
    "M_FIX_LONDRA": ("Europe/London", "16:00"),
}

df = mercato("2024-01-01", "2025-01-01")
q = quarantena_cached(df)
colonne = aggiungi_trigger_metro(df)

print("\nENTRY-METRO\n" + "-" * 70)

# --- 1. una sola occorrenza per giorno feriale ----------------------------
for nome in NOMI_METRO:
    ev = colonne[nome]
    tz = ORARI_ATTESI[nome][0]
    giorni = pd.Series(df.index[ev].tz_convert(tz).date).value_counts()
    ok = 200 <= int(ev.sum()) <= 270 and giorni.max() == 1
    check(
        f"1. {nome}: una occorrenza per giorno feriale",
        ok,
        f"{int(ev.sum())} occorrenze, max {giorni.max()} al giorno",
    )

# --- 2. sempre all'ora locale dichiarata ----------------------------------
for nome, (tz, atteso) in ORARI_ATTESI.items():
    ore = set(df.index[colonne[nome]].tz_convert(tz).strftime("%H:%M"))
    check(f"2. {nome}: sempre alle {atteso} ora locale", ore == {atteso}, f"{sorted(ore)}")

# --- 2b. anche nelle settimane con i DST sfasati --------------------------
marzo = (df.index >= "2024-03-11") & (df.index < "2024-03-31")
ore = set(
    df.index[colonne["M_LONDRA"] & marzo].tz_convert("Europe/London").strftime("%H:%M")
)
check("2b. M_LONDRA corretta nelle settimane con DST sfasati", ore == {"08:00"}, f"{sorted(ore)}")

# --- 3. nessuna occorrenza in quarantena ----------------------------------
sporche = sum(int((colonne[n] & q["totale"]).sum()) for n in NOMI_METRO)
check("3. nessuna occorrenza su barre in quarantena", sporche == 0, f"{sporche} barre sporche")

# --- 4. nessuna sovrapposizione fra metro ---------------------------------
somma = sum(colonne[n].astype(int) for n in NOMI_METRO)
check("4. due metro non scattano mai sulla stessa barra", int(somma.max()) <= 1,
      f"massimo metro simultanee: {int(somma.max())}")

# --- 5. la short scatta sulle identiche barre della long ------------------
clear_registry()
registra_trigger_metro(anche_short=True)
from engine.registry import get_entry  # noqa: E402

uguali = all(
    get_entry(n)(df).equals(get_entry(f"{n}_SHORT")(df)) for n in NOMI_METRO
)
direzioni = all(
    get_entry_direction(n) == 1 and get_entry_direction(f"{n}_SHORT") == -1
    for n in NOMI_METRO
)
check("5a. la short scatta sulle identiche barre della long", uguali)
check("5b. direction corrette (+1 long, -1 short)", direzioni)

# --- 6. la cache ----------------------------------------------------------
a = TRIGGER_METRO["M_LONDRA"](df)
b = TRIGGER_METRO["M_LONDRA"](df)
check("6a. due chiamate sullo stesso df danno lo stesso risultato", a.equals(b))

df2 = mercato("2023-01-01", "2023-07-01")
q2 = quarantena_cached(df2)
check("6b. un df diverso ricalcola la quarantena", len(q2) == len(df2) and len(q2) != len(q))

svuota_cache()
c = TRIGGER_METRO["M_LONDRA"](df)
check("6c. dopo svuota_cache il risultato non cambia", a.equals(c))

# --- 7. registrazione ripetuta --------------------------------------------
clear_registry()
registra_trigger_metro()
prima = set(list_entries())
try:
    registra_trigger_metro()
    check("7a. registrare due volte non solleva errore", True)
except Exception as e:
    check("7a. registrare due volte non solleva errore", False, str(e)[:60])
check("7b. solo long registrate di default", prima == set(NOMI_METRO), f"{sorted(prima)}")

# --- 8. nessuna metro degenere --------------------------------------------
degeneri = [n for n in NOMI_METRO if colonne[n].all() or not colonne[n].any()]
check("8. nessuna metro sempre vera o sempre falsa", not degeneri, f"degeneri: {degeneri}")

# --- 9. ROLLOVER non e' fra le metro --------------------------------------
check(
    "9. ROLLOVER escluso dal catalogo delle metro",
    not any("ROLLOVER" in n for n in NOMI_METRO),
    f"{list(NOMI_METRO)}",
)

# ===========================================================================
ok, tot = sum(ESITI), len(ESITI)
print("\n" + "=" * 70)
print(f"RISULTATO: {ok}/{tot} test superati")
print("=" * 70)
sys.exit(0 if ok == tot else 1)
