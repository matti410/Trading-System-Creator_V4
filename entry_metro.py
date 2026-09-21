"""
Entry-METRO: ingressi puramente temporali, senza nessuna condizione di prezzo.

NON SONO STRATEGIE. Sono un righello.

Ogni metro entra all'apertura di una sessione e basta. Servono a rispondere
alla domanda: «il mio pattern di prezzo fa meglio del semplice entrare a
quell'ora?». Un pattern che non batte il proprio metro non sta aggiungendo
informazione di prezzo: sta scegliendo l'orologio.

Le cinque entry, tutte long, tutte n=0 (la barra di apertura):

    M_TOKYO        09:00 Asia/Tokyo
    M_LONDRA       08:00 Europe/London
    M_NEW_YORK     08:00 America/New_York
    M_NYSE         09:30 America/New_York
    M_FIX_LONDRA   16:00 Europe/London

ROLLOVER e' escluso di proposito: e' sempre in quarantena (i prezzi bid sono
deformati dall'allargamento dello spread) e non scatterebbe mai.

Perche' solo LONG
-----------------
Il trigger e' puramente temporale: scatta sulle stesse identiche barre per
long e short. Nell'event study, dove non ci sono costi, la curva short e'
quella long ribaltata di segno — esattamente, non approssimativamente.
Registrare anche le speculari raddoppierebbe le righe senza aggiungere
un'informazione.

L'asimmetria vera compare al Passo 3, dove lo swap long e short sono diversi.
Se serve li': `registra_trigger_metro(anche_short=True)`.

ATTENZIONE AI TEST MULTIPLI
---------------------------
Le metro NON vanno contate fra le prove. Sono un riferimento, non candidati:
non le sceglieresti mai come sistema da tradare. Quando passi `k` a
`soglia_rumore`, passa il numero di entry VERE, non il numero di righe della
tabella. La costante `NOMI_METRO` serve proprio a escluderle.

Come si leggono
---------------
La curva sale se il prezzo mediamente sale da li' in avanti. Ma quello che
conta e' lo SCOSTAMENTO dalla linea nera del mercato, non l'altezza: su un
asset con deriva la curva grezza sale da sola.

E se una metro esce con t alto, non e' un edge: e' deriva intraday dell'asset.
"""
from __future__ import annotations

import pandas as pd

from engine.quarantena import quarantena
from engine.sessioni import barre_da_apertura

# Sessione di provenienza di ogni metro. Aggiungere una riga qui basta:
# le funzioni, il dizionario e la registrazione si generano da questa mappa.
SESSIONI_METRO = {
    "M_TOKYO": "TOKYO",
    "M_LONDRA": "LONDRA",
    "M_NEW_YORK": "NEW_YORK",
    "M_NYSE": "NYSE",
    "M_FIX_LONDRA": "FIX_LONDRA",
}

NOMI_METRO = tuple(SESSIONI_METRO)


# ------------------------------------------------------------------ cache --
# Le condizioni sono stateless (df -> Series), quindi la quarantena va
# calcolata dentro. Ricalcolarla a ogni chiamata costa ~100 ms: con 5 metro
# sono ~0.5 s sprecati a ogni giro di event study. Questa cache la calcola
# una volta per storico.
#
# La chiave e' l'identita' dell'indice (lunghezza, prima e ultima barra):
# se cambi dati, la cache si rinnova da sola. Nessuno stato da configurare
# a mano, quindi nessun rischio di ritrovarsi una quarantena vecchia.
_CACHE: dict[tuple, pd.DataFrame] = {}


def _chiave(idx: pd.DatetimeIndex) -> tuple:
    return (len(idx), idx[0], idx[-1])


def quarantena_cached(df: pd.DataFrame) -> pd.DataFrame:
    """La quarantena di questo storico, calcolata una volta sola."""
    idx = pd.DatetimeIndex(df.index)
    k = _chiave(idx)
    if k not in _CACHE:
        _CACHE[k] = quarantena(df, verbose=False)
    return _CACHE[k]


def svuota_cache() -> None:
    """Forza il ricalcolo della quarantena. Serve solo se cambi i parametri
    di `quarantena()` e vuoi che le metro li vedano."""
    _CACHE.clear()


# ----------------------------------------------------------- le condizioni --
def _metro(df: pd.DataFrame, sessione: str) -> pd.Series:
    """Evento: la barra di apertura della sessione, esclusa la quarantena."""
    return barre_da_apertura(df, sessione, n=0, quarantena=quarantena_cached(df))


def _crea(sessione: str):
    def funzione(df: pd.DataFrame) -> pd.Series:
        return _metro(df, sessione)

    funzione.__name__ = f"entry_metro_{sessione.lower()}"
    funzione.__doc__ = (
        f"Long sulla barra di apertura della sessione {sessione}. "
        f"Metro temporale, non una strategia."
    )
    return funzione


TRIGGER_METRO = {nome: _crea(sessione) for nome, sessione in SESSIONI_METRO.items()}


# -------------------------------------------------------- funzioni d'uso --
def aggiungi_trigger_metro(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcola tutte le metro e le aggiunge come colonne al df.
    Non modifica il df originale: ne restituisce una copia.
    """
    df = df.copy()
    for nome, funzione in TRIGGER_METRO.items():
        df[nome] = funzione(df)
    return df


def registra_trigger_metro(anche_short: bool = False):
    """
    Registra le metro nel motore (engine.registry), cosi' run_event_study le
    trova da sola. Va chiamata prima di run_event_study.

    E' sicura da richiamare piu' volte: i nomi gia' registrati vengono
    saltati con un avviso, non sollevano errore.

    anche_short : registra anche le speculari `M_*_SHORT` (direction=-1).
        Di norma non servono — nell'event study la curva short e' quella long
        ribaltata. Utili solo al Passo 3, dove lo swap rende i due lati
        davvero diversi.
    """
    from engine.registry import list_entries, register_entry

    gia_presenti = set(list_entries())
    nuovi = 0

    for nome, funzione in TRIGGER_METRO.items():
        if nome in gia_presenti:
            print(f"[registra_trigger_metro] '{nome}' gia' registrata, salto.")
        else:
            register_entry(nome, direction=1)(funzione)
            nuovi += 1

        if anche_short:
            nome_s = f"{nome}_SHORT"
            if nome_s in gia_presenti:
                print(f"[registra_trigger_metro] '{nome_s}' gia' registrata, salto.")
            else:
                register_entry(nome_s, direction=-1)(funzione)
                nuovi += 1

    attese = len(TRIGGER_METRO) * (2 if anche_short else 1)
    print(
        f"[registra_trigger_metro] {nuovi} metro registrate "
        f"({attese - nuovi} gia' presenti)."
    )
    print(
        "    Sono un RIFERIMENTO, non candidati: escludile dal conteggio dei "
        "test multipli (k) e dalla ricerca delle uscite. Usa NOMI_METRO."
    )
