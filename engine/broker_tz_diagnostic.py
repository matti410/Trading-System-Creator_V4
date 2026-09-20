"""
Diagnostica del fuso orario del broker.

Scopo: capire EMPIRICAMENTE quale regola di fuso/DST segue il server del broker,
partendo solo dalle candele M15 (indice naive in ora server).

Idea: il mercato forex apre la domenica alle 17:00 ora di New York e chiude il
venerdi alle 17:00 ora di New York. Questi due istanti sono FISSI in ora di New
York tutto l'anno. Quindi, se convertiamo l'ora server in ora di New York con la
regola GIUSTA, la prima barra di ogni settimana cade sempre alla stessa ora NY.
Con la regola SBAGLIATA, nelle settimane in cui i cambi DST USA ed europei non
coincidono, l'ora NY risulta spostata di un'ora.

La regola vera e' quella per cui l'apertura settimanale cade sull'ora NY ATTESA
(domenica 17:00) nel maggior numero di settimane. Non basta che l'ora sia
costante: un offset fisso sbagliato produce un'ora costante ma spostata.
"""

import pandas as pd

NY = "America/New_York"

# Ipotesi sulla regola del server. Ogni funzione prende un DatetimeIndex naive
# in ora server e restituisce lo stesso indice convertito in UTC.
HYPOTHESES = {
    "A_US_DST (NY+7h)": lambda idx: (
        (idx - pd.Timedelta(hours=7))
        .tz_localize(NY, ambiguous="NaT", nonexistent="NaT")
        .tz_convert("UTC")
    ),
    "B_EU_DST (Europe/Athens)": lambda idx: (
        idx.tz_localize("Europe/Athens", ambiguous="NaT", nonexistent="NaT")
        .tz_convert("UTC")
    ),
    "C_fisso GMT+2": lambda idx: (idx - pd.Timedelta(hours=2)).tz_localize("UTC"),
    "D_fisso GMT+3": lambda idx: (idx - pd.Timedelta(hours=3)).tz_localize("UTC"),
}


def _week_segments(idx, gap_hours=6):
    """Individua l'inizio e la fine di ogni settimana di contrattazione.

    Una nuova settimana inizia dopo un buco di almeno `gap_hours` ore
    (il weekend). Restituisce due liste di posizioni: aperture e chiusure.
    """
    idx = pd.DatetimeIndex(idx)
    gaps = idx.to_series().diff() > pd.Timedelta(hours=gap_hours)
    opens = [0] + [i for i, g in enumerate(gaps) if g]
    closes = [i - 1 for i in opens[1:]] + [len(idx) - 1]
    return opens, closes


def diagnose_broker_offset(df, gap_hours=6, drop_edges=True, verbose=True,
                           expected_open="Sun 17:00", expected_close="Fri 16:45"):
    """Confronta le ipotesi di fuso del broker sui dati M15 forniti.

    Parametri
    ---------
    df : DataFrame con indice DatetimeIndex naive in ora server del broker.
    gap_hours : ore di buco minime per considerare chiusa la settimana.
    drop_edges : scarta la prima e l'ultima settimana (spesso tagliate a meta').
    verbose : stampa il riepilogo.
    expected_open / expected_close : ora NY attesa della prima e dell'ultima
        barra della settimana. Le barre MT5 sono etichettate con l'ora di
        APERTURA, quindi su M15 l'ultima barra del venerdi' e' 16:45, non 17:00.

    Ritorna
    -------
    (summary, detail) : due DataFrame.
      summary  -> una riga per ipotesi, con la quota di settimane che cadono
                  sull'ora NY attesa (colonna `match`, piu' alta = meglio).
      detail   -> una riga per settimana, con l'ora NY dell'apertura sotto
                  ciascuna ipotesi (utile per ispezionare le settimane strane).
    """
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        raise ValueError(
            "L'indice e' gia' tz-aware. Questa diagnostica vuole l'indice naive "
            "cosi' come arriva da MetaTrader 5."
        )
    if not idx.is_monotonic_increasing:
        raise ValueError("L'indice non e' ordinato in modo crescente.")

    open_pos, close_pos = _week_segments(idx, gap_hours=gap_hours)
    if drop_edges and len(open_pos) > 2:
        open_pos, close_pos = open_pos[1:-1], close_pos[1:-1]
    if len(open_pos) < 4:
        raise ValueError(
            f"Trovate solo {len(open_pos)} settimane complete: troppo poche "
            "per una diagnosi. Servono almeno alcuni mesi di dati."
        )

    opens_naive = idx[open_pos]
    closes_naive = idx[close_pos]

    detail = pd.DataFrame({"apertura_server": opens_naive,
                           "chiusura_server": closes_naive})
    rows = []

    for name, to_utc in HYPOTHESES.items():
        ny_open = to_utc(opens_naive).tz_convert(NY)
        ny_close = to_utc(closes_naive).tz_convert(NY)

        lab_open = pd.Series(
            [f"{t.day_name()[:3]} {t:%H:%M}" if pd.notna(t) else "NaT"
             for t in ny_open]
        )
        lab_close = pd.Series(
            [f"{t.day_name()[:3]} {t:%H:%M}" if pd.notna(t) else "NaT"
             for t in ny_close]
        )
        detail[f"NY_open::{name}"] = lab_open.values

        vc_open = lab_open.value_counts()
        vc_close = lab_close.value_counts()
        match_open = float((lab_open == expected_open).mean())
        match_close = float((lab_close == expected_close).mean())
        rows.append({
            "ipotesi": name,
            "match": round((match_open + match_close) / 2, 3),
            "match_open": round(match_open, 3),
            "match_close": round(match_close, 3),
            "orari_open_distinti": int(vc_open.size),
            "open_piu_frequente": vc_open.index[0],
            "close_piu_frequente": vc_close.index[0],
        })

    summary = (pd.DataFrame(rows)
               .sort_values(["match", "orari_open_distinti"],
                            ascending=[False, True])
               .reset_index(drop=True))

    if verbose:
        print(f"Settimane analizzate: {len(open_pos)}  "
              f"({opens_naive[0]:%Y-%m-%d} -> {closes_naive[-1]:%Y-%m-%d})\n")
        print(summary.to_string(index=False))
        best = summary.iloc[0]
        if summary.iloc[1]["match"] == best["match"]:
            tied = summary.loc[summary["match"] == best["match"], "ipotesi"].tolist()
            print("\n>>> DIAGNOSI AMBIGUA: queste regole sono indistinguibili "
                  f"sui dati forniti:\n    {tied}")
            print("    Serve uno storico che copra i cambi DST di marzo e "
                  "ottobre/novembre (almeno 1 anno pieno): e' solo in quelle "
                  "settimane che le regole divergono.")
            return summary, detail
        print(f"\n>>> Regola piu' probabile: {best['ipotesi']}")
        print(f"    Apertura settimanale in ora NY: {best['open_piu_frequente']} "
              f"(atteso {expected_open}) — match complessivo {best['match']:.1%}")
        if best["match"] < 0.90:
            print("    ATTENZIONE: match basso. O il broker segue una regola non "
                  "prevista, o i dati hanno buchi. Ispeziona il DataFrame di "
                  "dettaglio prima di procedere.")
        elif best["orari_open_distinti"] > 1:
            print("    Nota: qualche settimana fuori riga. Di solito sono festivi "
                  "(Natale, Capodanno, Pasqua), non un errore di fuso: "
                  "controlla nel DataFrame di dettaglio.")

    return summary, detail


def to_utc_index(df, rule="A_US_DST (NY+7h)"):
    """Converte l'indice naive in ora server verso UTC, secondo la regola scelta.

    Non modifica il df originale: ne restituisce una copia con indice tz-aware UTC.
    Da usare SOLO dopo che diagnose_broker_offset ha confermato la regola.
    """
    if rule not in HYPOTHESES:
        raise ValueError(f"Regola sconosciuta: {rule}. Scegli fra {list(HYPOTHESES)}")
    out = df.copy()
    out.index = HYPOTHESES[rule](pd.DatetimeIndex(df.index))
    n_bad = out.index.isna().sum()
    if n_bad:
        raise ValueError(
            f"{n_bad} timestamp non convertibili (ora inesistente o ambigua "
            "nel cambio DST). Vanno ispezionati prima di procedere."
        )
    return out
