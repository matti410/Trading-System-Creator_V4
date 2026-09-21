"""
Suite di validazione degli strati 1 e 2 (quarantena + sessioni).

Si lancia da terminale, dalla cartella del progetto:

    python test_sessioni.py

Non serve MetaTrader 5 e non serve nessun file di dati: tutti gli scenari
sono costruiti a mano, con i cambi di ora legale VERI di ogni piazza.

Ogni test stampa OK o FALLITO. In fondo il totale.
"""
from __future__ import annotations

import sys

import pandas as pd

from engine.quarantena import quarantena, verifica_indice_utc
from engine.sessioni import barre_da_apertura, in_sessione



def esegui() -> int:
    """Esegue la suite. Ritorna 0 se tutto passa, 1 altrimenti."""
    ESITI = []


    def check(nome: str, condizione: bool, dettaglio: str = ""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))


    def mercato(inizio: str, fine: str, passo: str = "15min") -> pd.DataFrame:
        """Indice UTC continuo, prezzi fittizi (qui non contano)."""
        idx = pd.date_range(inizio, fine, freq=passo, tz="UTC", inclusive="left")
        return pd.DataFrame({"Close": 1.0}, index=idx)


    def solo_feriali_fx(df: pd.DataFrame) -> pd.DataFrame:
        """
        Toglie il weekend come fa il forex: dalle 17:00 NY del venerdi' alle
        17:00 NY della domenica.
        """
        ny = df.index.tz_convert("America/New_York")
        minuti = ny.hour * 60 + ny.minute
        chiuso = (
            ((ny.dayofweek == 4) & (minuti >= 17 * 60))
            | (ny.dayofweek == 5)
            | ((ny.dayofweek == 6) & (minuti < 17 * 60))
        )
        return df[~chiuso]


    # ===========================================================================
    print("\nSTRATO 1 — quarantena\n" + "-" * 70)

    # --- 1. cinque barre di rollover al giorno, inverno e estate ---------------
    for stagione, giorno in (("inverno", "2024-01-10"), ("estate", "2024-07-10")):
        df = mercato(f"{giorno} 00:00", f"{pd.Timestamp(giorno) + pd.Timedelta(days=1):%Y-%m-%d} 00:00")
        q = quarantena(df, verbose=False)
        n = int(q["rollover"].sum())
        ore = sorted(
            df.index[q["rollover"]].tz_convert("America/New_York").strftime("%H:%M")
        )
        check(
            f"1. rollover: 5 barre M15 ({stagione})",
            n == 5 and ore == ["16:45", "17:00", "17:15", "17:30", "17:45"],
            f"trovate {n}: {ore}",
        )

    # --- 1b. anche nelle settimane con i DST sfasati ---------------------------
    # 15 marzo 2024: USA gia' in ora legale (dal 10), Europa ancora no (dal 31).
    df = mercato("2024-03-15 00:00", "2024-03-16 00:00")
    q = quarantena(df, verbose=False)
    ore = sorted(df.index[q["rollover"]].tz_convert("America/New_York").strftime("%H:%M"))
    check(
        "1b. rollover corretto nella settimana con DST sfasati",
        ore == ["16:45", "17:00", "17:15", "17:30", "17:45"],
        f"{ore}",
    )

    # --- 2. buco di 6 ore -----------------------------------------------------
    df = mercato("2024-01-08 00:00", "2024-01-09 00:00")
    buco = (df.index >= "2024-01-08 10:00") & (df.index < "2024-01-08 16:00")
    df_buco = df[~buco]
    q = quarantena(df_buco, verbose=False)
    prima_dopo = df_buco.index[q["dopo_interruzione"]]
    check(
        "2. la barra dopo un buco di 6h e' marcata",
        len(prima_dopo) == 1 and prima_dopo[0] == pd.Timestamp("2024-01-08 16:00", tz="UTC"),
        f"{list(prima_dopo)}",
    )

    # --- 3. su H1 la finestra marca le barre giuste ---------------------------
    df = mercato("2024-01-10 00:00", "2024-01-11 00:00", passo="1h")
    q = quarantena(df, verbose=False)
    ore = sorted(df.index[q["rollover"]].tz_convert("America/New_York").strftime("%H:%M"))
    check(
        "3. H1: marcate 16:00 (contiene le 16:45) e 17:00",
        ore == ["16:00", "17:00"],
        f"{ore}",
    )

    # --- 4. verifica_indice_utc ------------------------------------------------
    df_fx = solo_feriali_fx(mercato("2024-01-01", "2024-06-01"))
    try:
        verifica_indice_utc(df_fx, verbose=False)
        check("4a. passa su indice UTC corretto", True)
    except Exception as e:
        check("4a. passa su indice UTC corretto", False, str(e)[:60])

    # L'etichetta fantasma: ora server marcata UTC.
    fantasma = df_fx.copy()
    fantasma.index = (
        df_fx.index.tz_convert("Europe/Athens").tz_localize(None).tz_localize("UTC")
    )
    try:
        verifica_indice_utc(fantasma, verbose=False)
        check("4b. si ferma sull'etichetta UTC fantasma", False, "non ha sollevato errore")
    except ValueError as e:
        check("4b. si ferma sull'etichetta UTC fantasma", "non sembra UTC vero" in str(e))

    naive = df_fx.copy()
    naive.index = df_fx.index.tz_localize(None)
    try:
        verifica_indice_utc(naive, verbose=False)
        check("4c. si ferma su indice senza fuso", False, "non ha sollevato errore")
    except ValueError as e:
        check("4c. si ferma su indice senza fuso", "ore SERVER" in str(e))

    cripto = mercato("2024-01-01", "2024-04-01")  # 24/7, nessuna pausa
    try:
        verifica_indice_utc(cripto, verbose=False)
        check("4d. avvisa e prosegue su simbolo 24/7", True)
    except Exception as e:
        check("4d. avvisa e prosegue su simbolo 24/7", False, str(e)[:60])


    # ===========================================================================
    print("\nSTRATO 2 — sessioni\n" + "-" * 70)

    df = solo_feriali_fx(mercato("2024-01-01", "2025-01-01"))
    q = quarantena(df, verbose=False)

    # --- 5. IL TEST DECISIVO: Londra sempre alle 08:00 di Londra --------------
    ev = barre_da_apertura(df, "LONDRA")
    ore_londra = set(
        df.index[ev].tz_convert("Europe/London").strftime("%H:%M")
    )
    check(
        "5. LONDRA apre sempre alle 08:00 ora di Londra (tutto l'anno)",
        ore_londra == {"08:00"},
        f"orari distinti trovati: {sorted(ore_londra)}",
    )

    # La stessa cosa in ora server: deve mostrare DUE orari. E' l'errore che il
    # modulo elimina, e serve che il test lo veda davvero.
    ore_server = set(
        df.index[ev].tz_convert("America/New_York")
        .map(lambda t: t + pd.Timedelta(hours=7))
        .strftime("%H:%M")
    )
    check(
        "5b. controprova: in ora SERVER gli orari sono due",
        len(ore_server) == 2,
        f"{sorted(ore_server)} — e' il bug che il modulo elimina",
    )

    # Le settimane sfasate: fine marzo, USA in DST ed Europa no.
    sfasate = df.index[ev]
    sfasate = sfasate[(sfasate >= "2024-03-11") & (sfasate < "2024-03-31")]
    ore_sfasate = set(sfasate.tz_convert("Europe/London").strftime("%H:%M"))
    check(
        "5c. corretto anche nelle ~3 settimane di marzo con DST sfasati",
        ore_sfasate == {"08:00"},
        f"{sorted(ore_sfasate)} su {len(sfasate)} giorni",
    )

    # --- 6. Tokyo non ha ora legale -> sempre stessa ora UTC ------------------
    ev_tokyo = barre_da_apertura(df, "TOKYO")
    ore_utc = set(df.index[ev_tokyo].strftime("%H:%M"))
    check(
        "6. TOKYO (nessun DST) cade sempre alla stessa ora UTC",
        ore_utc == {"00:00"},
        f"{sorted(ore_utc)}",
    )

    # --- 7. barra di apertura mancante ----------------------------------------
    giorno = mercato("2024-06-03 00:00", "2024-06-04 00:00")
    manca = giorno.index.tz_convert("Europe/London").strftime("%H:%M") == "08:00"
    giorno_buco = giorno[~manca]
    ev_b = barre_da_apertura(giorno_buco, "LONDRA")
    scattata = giorno_buco.index[ev_b].tz_convert("Europe/London").strftime("%H:%M")
    check(
        "7. apertura mancante -> evento sulla prima barra disponibile",
        list(scattata) == ["08:15"],
        f"{list(scattata)}",
    )

    # --- 8. finestra a cavallo della mezzanotte -------------------------------
    from engine.sessioni import SESSIONI  # noqa: E402

    SESSIONI["_TEST_NOTTE"] = {"tz": "Europe/London", "inizio": "22:00", "fine": "02:00"}
    f_notte = in_sessione(giorno, "_TEST_NOTTE")
    ore_vere = sorted(
        set(giorno.index[f_notte].tz_convert("Europe/London").strftime("%H"))
    )
    check(
        "8. finestra 22:00-02:00 attraversa la mezzanotte",
        ore_vere == ["00", "01", "22", "23"],
        f"ore coperte: {ore_vere}",
    )
    del SESSIONI["_TEST_NOTTE"]

    # --- 9. quarantena e weekend ----------------------------------------------
    ev_roll = barre_da_apertura(df, "ROLLOVER", quarantena=q)
    check(
        "9a. nessun evento su barre in quarantena (ROLLOVER)",
        int(ev_roll.sum()) == 0,
        f"eventi: {int(ev_roll.sum())}",
    )

    ev_roll_senza = barre_da_apertura(df, "ROLLOVER")
    check(
        "9b. controprova: senza quarantena ROLLOVER scatta",
        int(ev_roll_senza.sum()) > 200,
        f"eventi: {int(ev_roll_senza.sum())}",
    )

    f_londra = in_sessione(df, "LONDRA")
    gg = set(df.index[f_londra].tz_convert("Europe/London").dayofweek)
    check("9c. nessuna barra di sessione nel weekend locale", gg <= {0, 1, 2, 3, 4}, f"{sorted(gg)}")

    # --- 10. un solo evento al giorno -----------------------------------------
    giorni = pd.Series(
        df.index[ev].tz_convert("Europe/London").date
    ).value_counts()
    check(
        "10. un solo evento per giorno per sessione",
        giorni.max() == 1,
        f"massimo eventi in un giorno: {giorni.max()} su {len(giorni)} giorni",
    )

    # --- extra: il filtro dura, l'evento no -----------------------------------
    check(
        "extra. il filtro copre molte barre, l'evento una sola",
        int(f_londra.sum()) > 30 * int(ev.sum()) * 0.8,
        f"filtro {int(f_londra.sum())} barre vs evento {int(ev.sum())} barre",
    )

    # ===========================================================================
    ok, tot = sum(ESITI), len(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati")
    print("=" * 70)
    return (0 if ok == tot else 1)



if __name__ == "__main__":
    sys.exit(esegui())
