"""
Le schede delle ipotesi della mappa delle anomalie (27/10/2026, docs/73 §B.2,
registro in docs/74).

A COSA SERVE
------------
Una scheda e' un'ipotesi scritta PRIMA di guardare i dati: il meccanismo, la
variabile, le fasce, quale fascia deve rispondere e in che verso, l'orizzonte,
il mercato di riferimento. engine/mappa.py la misura sull'in-sample dello
studio. Qui entrano solo le schede APPROVATE da Mattia (docs/74): M02 e M03
sono fuori dalla prima versione (nessun segno dal meccanismo). Dal 29/10/2026
(docs/77, lavoro 1) M01, M04 e M05 (funding e basis) sono tolte dal catalogo:
i loro esiti restano nel file della mappa e le loro fasce nel conto (SCHEDE_TOLTE).

Cambiare una scheda dopo averla misurata e' una versione nuova: si alza
`versione`, e il conto la tratta come una prova nuova (docs/73 §B.4).

Modulo ADDITIVO: non modifica nessun file esistente dell'engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field

QUINTILI = ("Q1", "Q2", "Q3", "Q4", "Q5")
STESSA_ORA, QUALUNQUE_ORA = "stessa ora", "qualunque ora"


@dataclass(frozen=True)
class Scheda:
    """Un'ipotesi della mappa (i campi di docs/73 §B.2.1)."""
    id: str
    versione: int
    approvata: str                    # la data dell'approvazione di Mattia
    titolo: str
    meccanismo: str
    idea: str                         # da dove viene l'idea, e cosa e' gia' stato visto sui dati
    variabile: str                    # una funzione di engine/indicatori.py (vedi mappa.VARIABILI)
    tipo: str                         # "quintili" o "categorie"
    attese: dict                      # fascia -> verso atteso (+1 sopra il mercato = long, -1 sotto = short)
    orizzonte_ore: float
    riferimento: str                  # STESSA_ORA o QUALUNQUE_ORA
    portabilita: str                  # su TradingView: "sì", "approssimata (...)", "no"
    serve: tuple = ()                 # dati in piu': "btc" (funding e spot tolti il 29/10/2026)
    mercati: tuple = ("PERP", "SPOT")
    escludi_monete: tuple = ()        # es. ("BTC",) per M06
    finestra_giorni: int = 365        # quintili: la finestra delle sole barre passate (D5)
    categorie: dict = field(default_factory=dict)    # categorie: valore della variabile -> nome della fascia
    prove_extra: int = 0              # fasce gia' viste da contare (M01, tolta: le 96 del profilo 2a)
    conta_segno_opposto: bool = False  # M07: il segno scelto dopo aver visto E39, si conta anche l'opposto
    doppione_di: str | None = None    # se e' doppione di questa scheda, non si misura (M04 fino al 28/10; oggi nessuna)

    @property
    def fasce(self) -> tuple:
        return QUINTILI if self.tipo == "quintili" else tuple(self.categorie.values())


SCHEDE = {s.id: s for s in (
    Scheda(
        id="M06", versione=1, approvata="27/10/2026",
        titolo="BTC che anticipa le altcoin (versione A, 1 ora)",
        meccanismo=("Il prezzo si forma prima su BTC; un'altcoin che in un'ora non ha seguito BTC recupera "
                    "nell'ora dopo. E' la versione lenta del meccanismo, non il ritardo di minuti."),
        idea="Meccanismo della formazione del prezzo. Niente di visto sui dati.",
        variabile="scarto_btc_1h", tipo="quintili",
        attese={"Q5": 1, "Q1": -1}, orizzonte_ore=1, riferimento=STESSA_ORA,
        portabilita="sì", serve=("btc",), escludi_monete=("BTC",)),
    Scheda(
        id="M07", versione=1, approvata="27/10/2026",
        titolo="Rendimento recente estremo (inversione)",
        meccanismo=("Dopo un movimento molto forte in poche ore le liquidazioni a catena spingono il prezzo oltre "
                    "il giusto, poi rientra."),
        idea=("In parte gia' visto: il segno inversione e' stato scelto dopo aver visto E39 (inversione di un'ora) "
              "nella rosa di BTC perp: si conta anche la versione opposta (5 + 5 fasce)."),
        variabile="rendimento_4h", tipo="quintili",
        attese={"Q5": -1, "Q1": 1}, orizzonte_ore=4, riferimento=STESSA_ORA,
        portabilita="sì", conta_segno_opposto=True),
)}

# 29/10/2026 (docs/77, lavoro 1): le schede tolte dal catalogo, con la data. Non si misurano piu';
# i loro esiti restano nel file della mappa (si mostrano con la nota) e le loro fasce nel conto.
SCHEDE_TOLTE = {"M01": "29/10/2026", "M04": "29/10/2026", "M05": "29/10/2026"}
