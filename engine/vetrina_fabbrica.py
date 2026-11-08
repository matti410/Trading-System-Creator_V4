"""
Le funzioni chiamate dalle celle del notebook della fabbrica (docs/82 §7). Nasce in L4b con la sola
sessione_da_strategia (docs/82 §2 e P9); le altre arrivano in L5, con il notebook.
"""
from __future__ import annotations

from engine.fabbrica import cassaforte
from engine.fabbrica.sessione import apri_sessione


def sessione_da_strategia(cartella_dati, id_ricerca: str, id_strategia: str, esito=None):
    """
    La Sessione del Lab (vetrina.Sessione) per una strategia entrata in cassaforte, per le schermate 7, 9 e 8:
    in-sample = ricerca + selezione, out-of-sample = la cassaforte (engine/fabbrica/sessione.py). `esito` = quello di
    cassaforte.entra, se c'è già; altrimenti si rifà con cassaforte.esito_cassaforte (nessun ingresso nuovo).
    Le condizioni temporanee nel catalogo si tolgono con engine.fabbrica.sessione.chiudi(s).
    """
    if esito is None:
        esito = cassaforte.esito_cassaforte(cartella_dati, id_ricerca)
    return apri_sessione(esito, id_strategia)
