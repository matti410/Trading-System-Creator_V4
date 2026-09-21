"""
Strato 2 — le sessioni di mercato, in ora locale di borsa.

Due primitive, e la differenza fra le due e' il punto di tutto il modulo:

    in_sessione(df, "LONDRA")          FILTRO — uno stato, dura ore
    barre_da_apertura(df, "LONDRA")    EVENTO — una barra sola al giorno

Scrivere una finestra oraria come entry invece che come filtro gonfia il
conteggio dei segnali per persistenza multi-barra: una sessione di 9 ore su
M15 sono 36 barre vere, non un trigger.

Perche' in ora locale e non in ora server
-----------------------------------------
Le sessioni sono definite nell'ora locale della borsa (Londra apre alle 8
del mattino di Londra, tutto l'anno). L'ora SERVER corrispondente si sposta
di un'ora a ogni cambio di ora legale.

Il server del broker segue il calendario DST americano. Il DST europeo e'
sfasato di ~3 settimane a marzo e ~1 a ottobre: in quelle ~4 settimane
l'anno un filtro scritto in ora server prende la sessione di Londra
sbagliata di un'ora. Non genera errori: falsa il backtest in silenzio.

Qui l'ora locale la calcola pandas dall'indice UTC, con il DST di ogni
piazza gestito correttamente.

Prerequisito
------------
Indice UTC vero. Chiama prima `engine.quarantena.verifica_indice_utc`.
"""
from __future__ import annotations

import pandas as pd

from engine.quarantena import passo_barre

# Catalogo delle sessioni. Modificabile a mano: aggiungere una riga basta.
#
# Gli orari sono le convenzioni del mercato VALUTARIO, che non coincidono
# con quelle delle borse azionarie. L'unica voce di borsa e' NYSE, indicata
# come tale.
#
# `fine = None` significa ISTANTE: genera eventi ma non puo' fare da filtro.
SESSIONI: dict[str, dict] = {
    "ROLLOVER":   {"tz": "America/New_York", "inizio": "17:00", "fine": None},
    "TOKYO":      {"tz": "Asia/Tokyo",       "inizio": "09:00", "fine": "18:00"},
    "LONDRA":     {"tz": "Europe/London",    "inizio": "08:00", "fine": "17:00"},
    "NEW_YORK":   {"tz": "America/New_York", "inizio": "08:00", "fine": "17:00"},
    "NYSE":       {"tz": "America/New_York", "inizio": "09:30", "fine": "16:00"},
    "FIX_LONDRA": {"tz": "Europe/London",    "inizio": "16:00", "fine": None},
}


def _sessione(nome: str) -> dict:
    if nome not in SESSIONI:
        raise KeyError(
            f"Sessione '{nome}' sconosciuta. Disponibili: {sorted(SESSIONI)}"
        )
    return SESSIONI[nome]


def _minuti(orario: str) -> int:
    ore, minuti = orario.split(":")
    return int(ore) * 60 + int(minuti)


def _locale(df: pd.DataFrame, tz: str) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        raise ValueError(
            "L'indice non ha fuso orario. Serve un indice UTC: "
            "chiama prima engine.quarantena.verifica_indice_utc()."
        )
    return idx.tz_convert(tz)


def _maschera_quarantena(df: pd.DataFrame, quarantena) -> pd.Series:
    """Accetta il DataFrame restituito da quarantena(), una Series, o None."""
    if quarantena is None:
        return pd.Series(False, index=df.index)
    if isinstance(quarantena, pd.DataFrame):
        if "totale" not in quarantena.columns:
            raise ValueError("Il DataFrame di quarantena non ha la colonna 'totale'.")
        serie = quarantena["totale"]
    else:
        serie = quarantena
    return serie.reindex(df.index).fillna(False).astype(bool)


# ----------------------------------------------------------------- FILTRO --
def in_sessione(df: pd.DataFrame, nome: str, quarantena=None) -> pd.Series:
    """
    FILTRO: True sulle barre che si aprono dentro la sessione.

    E' uno STATO, non un evento: resta vero per tutta la durata della
    sessione. Va usato come filtro (in AND su un'entry), mai come entry.

    Regole
    ------
    - Vale solo nei giorni feriali LOCALI: non esiste una sessione di Londra
      di sabato, nemmeno su un simbolo che tratta 24/7.
    - Una finestra che attraversa la mezzanotte locale funziona lo stesso.
    - Con `quarantena`, le barre in quarantena valgono False.
    - Le sessioni istantanee (fine=None) sollevano ValueError: un istante non
      e' uno stato.
    """
    s = _sessione(nome)
    if s["fine"] is None:
        raise ValueError(
            f"'{nome}' e' un istante, non una finestra: non puo' fare da filtro.\n"
            f"Per usarlo come evento: barre_da_apertura(df, '{nome}')."
        )

    locale = _locale(df, s["tz"])
    minuti = locale.hour * 60 + locale.minute
    inizio, fine = _minuti(s["inizio"]), _minuti(s["fine"])

    if inizio < fine:
        dentro = (minuti >= inizio) & (minuti < fine)
    else:  # la finestra attraversa la mezzanotte locale
        dentro = (minuti >= inizio) | (minuti < fine)

    feriale = locale.dayofweek < 5
    out = pd.Series(dentro & feriale, index=df.index)
    return out & ~_maschera_quarantena(df, quarantena)


# ----------------------------------------------------------------- EVENTO --
def barre_da_apertura(
    df: pd.DataFrame, nome: str, n: int = 0, quarantena=None
) -> pd.Series:
    """
    EVENTO: True su UNA sola barra per giorno locale — la n-esima a partire
    dall'apertura della sessione. Con n=0 e' la barra di apertura.

    Regole
    ------
    - `n` conta BARRE, non minuti.
    - Se la barra dell'apertura manca (festivo, buco), l'evento scatta sulla
      prima barra disponibile dopo, purche' nello stesso giorno locale e
      dentro la sessione.
    - Se la barra dell'evento e' in quarantena, quel giorno l'evento NON
      scatta. Non viene spostato alla barra dopo: spostarlo produrrebbe un
      evento a un orario diverso da quello dichiarato, che e' proprio la cosa
      che questo modulo esiste per evitare.
    - Solo giorni feriali locali.

    Conseguenza voluta: con la quarantena attiva, `barre_da_apertura(df,
    "ROLLOVER")` non scatta mai — la barra delle 17:00 NY e' sempre in
    quarantena. E' corretto: su dati BID quel prezzo non e' affidabile.
    ROLLOVER resta a catalogo perche' serve ai filtri di calendario
    ("chiudi prima del rollover"), non come ingresso.
    """
    if n < 0:
        raise ValueError("n dev'essere >= 0 (0 = barra di apertura).")

    s = _sessione(nome)
    locale = _locale(df, s["tz"])
    minuti = locale.hour * 60 + locale.minute
    inizio = _minuti(s["inizio"])

    dopo_apertura = minuti >= inizio
    if s["fine"] is not None:
        fine = _minuti(s["fine"])
        if inizio < fine:
            dopo_apertura = dopo_apertura & (minuti < fine)
        else:
            # Finestra a cavallo della mezzanotte: le barre candidate
            # restano quelle dal momento dell'apertura a fine giornata
            # locale, cosi' l'evento appartiene a un solo giorno.
            pass

    candidate = pd.Series(dopo_apertura & (locale.dayofweek < 5), index=df.index)

    # n-esima barra candidata di ogni giornata locale
    giorno = pd.Series(locale.date, index=df.index)
    progressivo = candidate.groupby(giorno).cumsum()
    evento = candidate & (progressivo == n + 1)

    return evento & ~_maschera_quarantena(df, quarantena)


def elenco_sessioni() -> pd.DataFrame:
    """Il catalogo in forma di tabella, per averlo sott'occhio nel notebook."""
    righe = []
    for nome, s in SESSIONI.items():
        righe.append({
            "sessione": nome,
            "fuso": s["tz"],
            "apertura": s["inizio"],
            "chiusura": s["fine"] if s["fine"] else "— (istante)",
            "usabile come": "evento" if s["fine"] is None else "evento + filtro",
        })
    return pd.DataFrame(righe).set_index("sessione")
