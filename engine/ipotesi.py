"""
Le schede delle ipotesi della mappa delle anomalie (27/10/2026, docs/73 §B.2,
registro in docs/74).

A COSA SERVE
------------
Una scheda e' un'ipotesi scritta PRIMA di guardare i dati: il meccanismo, la
variabile, le fasce, quale fascia deve rispondere e in che verso, l'orizzonte,
il mercato di riferimento. engine/mappa.py la misura sull'in-sample dello
studio. Qui entrano solo le schede APPROVATE da Mattia (docs/74): M02 e M03
sono fuori dalla prima versione (nessun segno dal meccanismo).

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
    serve: tuple = ()                 # dati in piu': "funding", "spot", "btc"
    mercati: tuple = ("PERP", "SPOT")
    escludi_monete: tuple = ()        # es. ("BTC",) per M06
    finestra_giorni: int = 365        # quintili: la finestra delle sole barre passate (D5)
    categorie: dict = field(default_factory=dict)    # categorie: valore della variabile -> nome della fascia
    prove_extra: int = 0              # fasce gia' viste da contare (M01: le 96 del profilo 2a)
    conta_segno_opposto: bool = False  # M07: il segno scelto dopo aver visto E39, si conta anche l'opposto
    doppione_di: str | None = None    # se e' doppione di questa scheda, non si misura (M04 fino al 28/10; oggi nessuna)

    @property
    def fasce(self) -> tuple:
        return QUINTILI if self.tipo == "quintili" else tuple(self.categorie.values())


SCHEDE = {s.id: s for s in (
    Scheda(
        id="M01", versione=1, approvata="27/10/2026",
        titolo="Ore del funding con il segno del funding",
        meccanismo=("Chi e' dal lato che paga il funding (i long con il funding positivo, gli short con il "
                    "negativo) chiude poco prima del pagamento delle 00:00, 08:00, 16:00 UTC: nell'ora prima il "
                    "prezzo va contro il lato che paga."),
        idea=("Meccanismo del funding (docs/63 §5). In parte gia' visto: il profilo 2a di BTC perp (H = 41, "
              "26/10) aveva l'ora peggiore per un long alle 23:15 UTC. Si contano le 96 fasce del profilo."),
        variabile="funding_segno_prima_pagamento", tipo="categorie",
        categorie={1.0: "funding positivo", -1.0: "funding negativo"},
        attese={"funding positivo": -1, "funding negativo": 1},
        orizzonte_ore=1, riferimento=STESSA_ORA,
        portabilita="approssimata (l'ora si', il segno del funding con il segno della basis)",
        serve=("funding",), mercati=("PERP",), prove_extra=96),
    Scheda(
        id="M04", versione=1, approvata="28/10/2026",
        titolo="Funding estremo",
        meccanismo=("Con il funding sopra il livello di base i long a leva pagano ogni 8 ore e sono affollati: alla "
                    "prima discesa scattano le liquidazioni. Con il funding sotto zero, lo stesso sugli short."),
        idea=("Meccanismo del funding. Niente di visto sui dati sul funding come variabile. Riscritta da Mattia il "
              "28/10/2026 prima della misura: con i quintili le fasce erano degeneri (Q1 31,1%) per il funding fermo "
              "al livello di base. Categorie dalla regola dell'exchange (0,01% ogni 8 ore); la regola dei doppioni "
              "con M05 cade."),
        variabile="funding_rispetto_al_base", tipo="categorie",
        categorie={-1.0: "funding sotto zero", 0.0: "funding fra zero e il livello di base",
                   1.0: "funding al livello di base", 2.0: "funding sopra il livello di base"},
        attese={"funding sotto zero": 1, "funding sopra il livello di base": -1}, orizzonte_ore=24,
        riferimento=STESSA_ORA,
        portabilita="approssimata (il funding no, la basis si')",
        serve=("funding",), mercati=("PERP",)),
    Scheda(
        id="M05", versione=1, approvata="27/10/2026",
        titolo="Basis estrema",
        meccanismo=("Una basis molto alta vuol dire long a leva affollati sul perpetual (lo stesso meccanismo di "
                    "M04, un istante per volta); molto bassa, lo stesso sugli short."),
        idea=("Meccanismo, come M04. Viste le righe basis dell'atlante di E21_BELT_HOLD (26/10): misurano E21 "
              "dentro la basis, non hanno guidato fascia e segno."),
        variabile="basis_bp", tipo="quintili",
        attese={"Q5": -1, "Q1": 1}, orizzonte_ore=8, riferimento=STESSA_ORA,
        portabilita="sì", serve=("spot",), mercati=("PERP",)),
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
