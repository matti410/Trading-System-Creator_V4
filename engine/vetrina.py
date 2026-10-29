"""
Vetrina — la «facciata» del notebook slim (6/10/2026).

COSA E'
-------
Nove schermate, una funzione ciascuna del notebook di presentazione. Ognuna
richiama i moduli che esistono gia' (event study, ricerca delle uscite,
ricerca dei filtri, due meta', Out-of-Sample, Monte Carlo) e ne mostra il
risultato con un riquadro «Come leggerlo» scritto per un trader.

    s = prepara("EURUSD", H=25)                              1 · Configura
    profilo_delle_ore(s)                                     2a · il mercato ora per ora
    esplora(s)                                               2c · i segnali contro il mercato
    rosa_dei_trigger(s)                                      3a · le casistiche suggerite (+ classifica)
    scegli_casistiche(s, parti_da="la rosa", togli_long="")  3b · le tue casistiche (25/10, docs/68; parti da: docs/73)
    atlante_dei_trigger(s)                                     3c · dove funziona il segnale (22/10, docs/66)
    scegli_cella(s, long="EUROPA")                             3d · scegli una situazione (facoltativa; docs/73 §A.3)
    imposta_uscite(s, regola_uscita="consigliata")           4 · Le uscite (consigliate: H, stop 90, target spento)
    rosa_dei_sistemi(s, sistema="Long + Short")              4b · il sistema da portare al passo 5

Dal 25/10/2026 (docs/68) le schermate 2-4 sono riordinate; restano, per i
test e per chi le usa a mano, classifiche(s) (la classifica di prima, in
pips) e scegli_trigger(s, long=[...], short=[...]) (le casistiche scritte a
mano).
    trova_strategia(s)                                       5 · Trova la strategia
    scheda(s, filtro="F1, F2")                               6 · Scheda strategia
    money_management(s, capitale=10_000, drawdown_max_pct=20) 7 · Money management
    verifica_trade(s)                                        8 · Verifica i trade
    lente(s, numero=12, indicatori="ema20, ema50")           (engine/vetrina_verifica.py)
    stress_test(s, drawdown_max_usd=10_000)                  9 · Stress test

`s` e' la SESSIONE: tiene dati, costi e scelte e passa da una schermata
all'altra. Le schermate vanno eseguite in ordine; se ne salti una la
funzione lo dice.

COSA NON E'
-----------
Non contiene nessun calcolo di trading: nessuna metrica, nessuna soglia,
nessun criterio nuovo. Tutti i numeri vengono dalle funzioni dell'engine,
con gli stessi parametri del notebook di lavoro. Qui ci sono solo la
sequenza delle chiamate, le tabelle rinominate e i testi.

Trigger, filtri e regole di uscita si leggono dal REGISTRO a ogni
esecuzione: aggiungere una condizione ai file del repo la fa comparire qui
senza toccare questo modulo.

Non dipende da Colab: in un notebook mostra tabelle e riquadri in HTML,
altrove li stampa come testo. Le stesse funzioni restituiscono i dati
(tabelle), cosi' un'altra interfaccia puo' riusarle.

I COSTI
-------
`engine/costi.py` sa leggere lo spread dai dati solo con MetaTrader 5
collegato (gli serve la dimensione del «punto» dello strumento). Qui MT5
non c'e', quindi:

  1. se lo strumento e' in SPREAD_LISTINO_PIPS si usano quei valori (conto
     IC Markets Standard: nessuna commissione, tutto nello spread);
  2. altrimenti lo spread si ricava dalla colonna `spread` del CSV, 75°
     percentile come in costi.py, con il «punto» dedotto dai decimali dei
     prezzi. Funziona solo se la colonna e' compilata;
  3. altrimenti errore: va aggiunta una riga alla tabella.

In tutti i casi la conversione nei parametri del backtest la fa
`costi.parametri_backtest`, come nel notebook di lavoro.

Modulo ADDITIVO: nessun file esistente viene modificato.
"""
from __future__ import annotations

import contextlib
import html
import io
import math
import os
from types import SimpleNamespace

import numpy as np
import pandas as pd

from . import registry as reg
from .broker_tz_diagnostic import to_utc_index
from .costi import parametri_backtest
from .due_meta import due_meta
from .equity_plot import plot_equity
from .event_study import deduci_pip, run_event_study
from .simboli import da_exchange, in_tabella, info_symbol, pip_symbol
from .exit_search_bt import barre_per_lato, per_lato, run_exit_search_bt
from .filter_search_bt import BASELINE, run_filter_search_bt
from .motore_veloce import scegli_motore
from .confidenza import congela_filtro
from .giudizio import (CAMPIONE_CORTO, DA_VALUTARE, prove_trigger_orizzonti, scheda_strategia,
                       soglia_rumore)
from . import registro_dataset as _rd
from .indicatori import aggiungi_indicatori, atr_giornaliero_chiuso
from .livelli import GIORNATA_FX, GIORNATA_UTC, imposta_giornata, quarantena_cached
from .metriche import netti_in_unita, pips_per_trade
from .montecarlo import (bp_per_dataset, grafici_montecarlo, montecarlo_completo,
                         pips_per_dataset, sizing, valore_pip_lotto, yardstick)
from .quarantena import ROLLOVER_DEFAULT, imposta_rollover, passo_barre, verifica_indice_utc
from .rosa import Q_ROSA, RHO_MAX, rosa_entry, rosa_sistemi
from .stagionalita import (codice_orario, curva_scarto_orario, descrivi_profilo, fasce_orarie,
                           fuso_profilo, n_fasce, picco_curva, profilo_orario)
from .splitting import split_al_confine, split_is_oos
from . import studio as _st


# ========================================================================
# Parametri fissi della vetrina (gli stessi del notebook di lavoro)
# ========================================================================

# Spread in pips del conto IC Markets Standard, per gli strumenti i cui dati
# non lo contengono. `rollover` e' una stima (vedi 93_QUARANTENA_TRADE_E_COSTI).
#
# 10/10/2026: il notebook principale prende lo spread SOLO da qui
# (`spread_listino`): un symbol senza riga ferma il notebook e il messaggio
# dice la riga esatta da aggiungere (col rollover proposto dai dati).
#
# 11/10/2026: righe degli 8 symbol nuovi, STIME del costo di un conto
# Standard reale (decisione di Mattia: ricerca coi costi Standard, poi verifica
# in demo; il demo IC Markets ha i prezzi del Raw senza commissione e costa
# meno del reale, docs/50 §12). Pips secondo engine/simboli.py (indici: punti).
#   normale, forex e oro = spread Raw medio + commissione Raw equivalente
#            (7 $ per lotto andata e ritorno), arrotondato per eccesso.
#            Spread Raw: medio del sito IC Markets EU o pagato davvero nel demo
#            (tick all'esecuzione, oro: 0,09 $). Commissione: 0,7 pips sulle
#            coppie in USD e sull'oro, 1,1 pips su USDJPY. Per EURUSD da'
#            0,06 + 0,7 = 0,8, il valore di listino Standard.
#   normale, indici e BTCUSD = il piu' alto fra spread medio del sito (uguale
#            per tutti i conti, niente commissione) e spread pagato nel demo.
#   rollover = normale + allargamento misurato nei dati (mediana della colonna
#            spread nelle barre di quarantena meno mediana fuori). Per EURUSD
#            da' 0,8 + 0,7 = 1,5, il valore gia' in tabella. None = nessun
#            allargamento misurabile, nessun costo in piu'.
# Da verificare dal vivo con le prime operazioni sul conto Standard.
SPREAD_LISTINO_PIPS = {
    "EURUSD": {"normale": 0.8, "rollover": 1.5},
    "GBPUSD": {"normale": 1.0, "rollover": 3.3},    # sito Raw 0,26 + 0,7; allargamento 2,3
    "USDJPY": {"normale": 1.3, "rollover": 2.7},    # sito Raw 0,22 + 1,1; allargamento 1,4
    "NZDUSD": {"normale": 0.8, "rollover": 2.5},    # demo 0,05 + 0,7; allargamento 1,7
    "XAUUSD": {"normale": 1.6, "rollover": 1.8},    # demo 0,9 + 0,7; allargamento 0,2
    "US500":  {"normale": 0.5, "rollover": None},   # demo 0,50 (sito 0,36); nessun allargamento
    "USTEC":  {"normale": 1.6, "rollover": 2.6},    # sito 1,57 (demo 1,0); allargamento 1,0
    "DE40":   {"normale": 1.5, "rollover": 6.5},    # sito 1,46 (demo 0,5); allargamento 5,0
    "BTCUSD": {"normale": 12.5, "rollover": 12.8},  # demo 12,5 $ (sito 6,46); allargamento 0,3
}

# Proposta del rollover dai dati: solo se la colonna spread e' significativa
# nelle barre di quarantena (almeno 100 barre, almeno meta' con spread > 0).
ROLLOVER_MIN_BARRE = 100
ROLLOVER_QUOTA_MIN = 0.5

REGOLA_FUSO = "A_US_DST (NY+7h)"   # da ora server IC Markets a UTC
CASH = 10_000_000                  # capitale del backtest: i pips non ne dipendono
MIN_TRIGGER = 200                  # sotto questa soglia un trigger non si misura
MIN_TRADE_GIUDIZIO = 100
P_MAX = 5.0
ALPHA = 0.05
FINESTRA = 500
LAG = 1
ORIZZONTI_MC = (10, 20, 40, 100)


# ========================================================================
# Presentazione: tabelle, riquadri, silenzio
# ========================================================================

def _in_notebook() -> bool:
    try:
        from IPython import get_ipython
        return get_ipython() is not None
    except Exception:
        return False


@contextlib.contextmanager
def _zitto():
    """Trattiene le stampe tecniche dei motori: nella vetrina non servono."""
    with contextlib.redirect_stdout(io.StringIO()):
        yield


_CSS = (
    "<style>"
    ".vt-titolo{font:600 17px/1.3 system-ui,sans-serif;margin:14px 0 6px}"
    ".vt-riga{display:flex;gap:26px;flex-wrap:wrap;align-items:flex-start}"
    ".vt-tab{border-collapse:collapse;font:13px/1.35 system-ui,sans-serif;margin:4px 0 10px}"
    ".vt-tab th{text-align:right;padding:5px 10px;border-bottom:2px solid #8a8a8a;font-weight:600}"
    ".vt-tab td{text-align:right;padding:4px 10px;border-bottom:1px solid rgba(128,128,128,.3)}"
    ".vt-tab th:first-child,.vt-tab td:first-child{text-align:left}"
    ".vt-box{border-left:4px solid #2b7bba;background:rgba(43,123,186,.09);"
    "padding:9px 14px;margin:10px 0 4px;font:13.5px/1.5 system-ui,sans-serif;max-width:900px}"
    ".vt-box b{font-weight:600}"
    ".vt-nota{font:12.5px/1.45 system-ui,sans-serif;opacity:.8;margin:2px 0 8px;max-width:900px}"
    # 25/10/2026 (docs/68 §8, §9): la risalita dopo l'out-of-sample, la riga delle prove, i dettagli
    ".vt-avviso{border-left:4px solid #e07b00;background:rgba(224,123,0,.12);"
    "padding:9px 14px;margin:10px 0 4px;font:13.5px/1.5 system-ui,sans-serif;max-width:900px}"
    ".vt-prove{font:12.5px/1.45 system-ui,sans-serif;margin:8px 0 4px;padding:5px 10px;max-width:900px;"
    "border-top:1px solid rgba(128,128,128,.4)}"
    ".vt-dettaglio summary{cursor:pointer;font:13px/1.4 system-ui,sans-serif;margin:6px 0}"
    "</style>"
)


def _html(corpo: str) -> None:
    from IPython.display import HTML, display
    display(HTML(_CSS + corpo))


def _fmt(v, decimali=2):
    if isinstance(v, (bool, np.bool_)):
        return "sì" if v else "no"
    if v is None or (isinstance(v, (float, np.floating)) and not np.isfinite(v)):
        return "—"
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}".replace(",", ".")
    if isinstance(v, (float, np.floating)):
        return f"{v:,.{decimali}f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return str(v)


def _tabella_html(df: pd.DataFrame, titolo: str | None = None, decimali=None) -> str:
    decimali = decimali or {}
    righe = []
    for _, r in df.iterrows():
        celle = "".join(f"<td>{html.escape(_fmt(r[c], decimali.get(c, 2)))}</td>"
                        for c in df.columns)
        righe.append(f"<tr>{celle}</tr>")
    testa = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    t = f"<div class='vt-titolo'>{html.escape(titolo)}</div>" if titolo else ""
    return (f"<div>{t}<table class='vt-tab'><thead><tr>{testa}</tr></thead>"
            f"<tbody>{''.join(righe)}</tbody></table></div>")


def _mostra(*tabelle, decimali=None) -> None:
    """Una o piu' tabelle affiancate. Ogni voce e' (titolo, DataFrame)."""
    if _in_notebook():
        _html("<div class='vt-riga'>"
              + "".join(_tabella_html(df, t, decimali) for t, df in tabelle) + "</div>")
        return
    for titolo, df in tabelle:
        if titolo:
            print(f"\n{titolo}")
        vista = df.copy()
        for c in vista.columns:
            vista[c] = [_fmt(v, (decimali or {}).get(c, 2)) for v in vista[c]]
        print(vista.to_string(index=False))


def _titolo(testo: str) -> None:
    if _in_notebook():
        _html(f"<div class='vt-titolo'>{html.escape(testo)}</div>")
    else:
        print(f"\n{testo}\n" + "-" * len(testo))


def _nota(testo: str) -> None:
    if _in_notebook():
        _html(f"<div class='vt-nota'>{html.escape(testo)}</div>")
    else:
        print(testo)


def _nota_blocchi(tab: pd.DataFrame, cosa: str) -> None:
    """28/10/2026 (docs/75 §7): la nota, solo se qualche riga ha usato la stima a blocchi di una settimana."""
    if tab is None or "incertezza_blocchi" not in tab.columns:
        return
    n = int(tab["incertezza_blocchi"].astype(bool).sum())
    if n:
        _nota(f"{n} {cosa}: la varianza è uscita zero o negativa e l'incertezza è stimata a blocchi di una "
              "settimana (docs/75).")


def _riquadro(cosa: str, buono: str, adesso: str) -> None:
    """Il riquadro «Come leggerlo»: sempre le stesse tre righe."""
    voci = (("Cosa stai guardando", cosa), ("Come capire se è buono", buono),
            ("Cosa fare adesso", adesso))
    if _in_notebook():
        _html("<div class='vt-box'>" + "<br>".join(
            f"<b>{k}.</b> {html.escape(v)}" for k, v in voci) + "</div>")
    else:
        print()
        for k, v in voci:
            print(f"  {k}: {v}")


def _spiegazione(titolo: str, testo: str) -> None:
    """Un riquadro di spiegazione con un titolo e un testo continuo."""
    if _in_notebook():
        _html(f"<div class='vt-box'><b>{html.escape(titolo)}</b><br>{html.escape(testo)}</div>")
    else:
        print(f"\n  {titolo}\n  {testo}")


def _avviso(testo: str) -> None:
    """Il riquadro arancione (25/10/2026, docs/68 §9): una scelta rifatta dopo aver visto."""
    if _in_notebook():
        _html(f"<div class='vt-avviso'>{html.escape(testo)}</div>")
    else:
        print(f"\n  [ATTENZIONE] {testo}")


def _dettaglio(titolo: str, *tabelle, decimali=None) -> None:
    """Tabelle a scomparsa (25/10/2026, docs/68 §2): chiuse, si aprono con un clic."""
    if _in_notebook():
        _html(f"<details class='vt-dettaglio'><summary>{html.escape(titolo)}</summary>"
              "<div class='vt-riga'>" + "".join(_tabella_html(df, t, decimali) for t, df in tabelle)
              + "</div></details>")
        return
    print(f"\n[dettaglio] {titolo}")
    _mostra(*tabelle, decimali=decimali)


# ========================================================================
# La sessione
# ========================================================================

class Sessione:
    """Dati, costi e scelte, da una schermata all'altra. La crea `prepara`."""

    def __init__(self):
        self.symbol = None
        self.H = None
        self.cartella = "dati"        # dove stanno i CSV (anche quello del cambio); "dati" dal 17/10
        self.df = self.df_is = self.df_oos = None
        self.costi = None
        self.pip = None
        self.spread_pips = self.spread_rollover_pips = None
        self.fonte_spread = ""
        self.ev = None
        self.entry_long = self.entry_short = None
        self.trigger_long = self.trigger_short = ()
        self.uscite = None
        self.es = None
        self.fs = None
        self.dm = None
        self.sopravvissuti = []
        self.filtro = None
        self.filtri_scelti = []
        self.oos = None
        self.trades_is = self.trades_oos = None
        self.controlli = None
        self.mm = None                # 16/10/2026: schermata 7, money management
        self.rosa_trigger = None      # 18/10/2026: la rosa dei candidati (engine/rosa.py)
        self.rosa_sistemi = None
        self.fuso = None              # 18/10/2026: fuso delle fasce orarie (engine/stagionalita.py)
        self.profilo = None
        self.timeframe = "M15"        # 19/10/2026: M5, M15, M30, H1, H4
        self.da_exchange = False      # 19/10/2026: dati da exchange crypto (engine/exchange.py)
        self.solo_long = False        # 19/10/2026: spot, lo short non esiste
        self.atr = None               # 20/10/2026: ATR giornaliero a 5 giornate chiuse (unita' ATR, docs/63 §4)
        self.unita = "pips"           # 20/10/2026 (U2): l'unita' che decide; "bp" sui symbol da exchange
        self.funding = None           # 21/10/2026: storico del funding (perpetual); None = non contato
        self.motore = None            # 21/10/2026 (docs/65): "bt" o "veloce"; None = il predefinito (E3: "veloce")
        self.maschere = {}            # 21/10/2026 (E4, docs/65 §16): maschere dei filtri, una cache per df
        # 22/10/2026 (docs/63 §10.3): le prove della catena, per la soglia cumulata.
        # Ogni prova e' registrata con le sue impostazioni: rifatta uguale non conta due volte
        # (la voce "celle" dell'atlante, 22/10/2026, nasce alla schermata 3c)
        self.prove = {"trigger": 0, "uscite": {}, "filtri": {}, "combinazioni": {}}
        self.atlante = None           # 22/10/2026 (docs/66): l'atlante del trigger, schermata 3c
        self.cella_long = self.cella_short = None   # la cella scelta per lato (3d); None = strada di sempre
        self.tabelle = {}
        # 25/10/2026 (docs/68): il riordino delle schermate 2-4
        self.storia = None            # il registro del dataset (engine/registro_dataset.py, §9.1)
        self.curve_scarto = None      # le curve dello scarto della schermata 2c (§2.1)
        self.casistiche = {}          # "long"/"short" -> trigger, origine, cella (§3.1)
        self.entry_casistica_long = self.entry_casistica_short = None   # con la cella dentro (§3.3)
        self.consigliate = None       # le uscite consigliate e il picco da leggere (§5)
        self.sistema = None           # il sistema scelto alla 4b, portato al passo 5 (§7)

    def __repr__(self):
        return f"<Sessione {self.symbol} {self.timeframe} · H={self.H}>"

    def lati(self) -> tuple:
        """Le direzioni su cui si opera: (1, -1), oppure solo (1,) sullo spot."""
        return (1,) if self.solo_long else (1, -1)

    def _serve(self, attributo: str, schermata: str):
        if getattr(self, attributo) is None:
            raise RuntimeError(f"Manca un passaggio: esegui prima la schermata «{schermata}».")


# ========================================================================
# Costi senza MetaTrader
# ========================================================================

def _punto_da_prezzi(close: pd.Series) -> float:
    """Il «punto» dello strumento (ultima cifra quotata), dai decimali dei prezzi."""
    c = close.dropna().to_numpy(dtype=float)[:20000]
    for d in range(0, 9):
        if np.allclose(np.round(c, d), c, rtol=0, atol=10.0 ** -(d + 3)):
            return 10.0 ** -d
    raise ValueError("impossibile dedurre il punto dello strumento dai prezzi.")


def _punto_symbol(symbol: str, close: pd.Series) -> float:
    """
    Il «punto» MT5 in cui e' espressa la colonna `spread`. Per i symbol di
    engine/simboli.py viene dalle cifre decimali lette da MT5; per gli altri
    dai decimali dei prezzi. 10/10/2026: USTEC ha 2 cifre (punto 0,01) ma
    quota sempre a passi di 0,1, e dai prezzi risultava uno spread 10 volte
    troppo alto.
    """
    if in_tabella(symbol):
        return 10.0 ** -info_symbol(symbol)["cifre"]
    return _punto_da_prezzi(close)


def proposta_rollover(symbol: str, df: pd.DataFrame) -> float | None:
    """
    Spread nel rollover proposto dai dati, in pips: la mediana della colonna
    `spread` nelle barre di quarantena (le stesse su cui il motore addebita il
    costo del rollover), arrotondata a 0,1. None se la colonna non e'
    significativa: meno di ROLLOVER_MIN_BARRE barre di quarantena, o meno di
    ROLLOVER_QUOTA_MIN con spread > 0. La colonna e' lo spread MINIMO della
    barra: la proposta e' un limite inferiore. `df` con indice UTC.
    """
    col = next((c for c in df.columns if c.lower() == "spread"), None)
    if col is None:
        return None
    q = quarantena_cached(df)["totale"].to_numpy(dtype=bool)
    if q.sum() < ROLLOVER_MIN_BARRE:
        return None
    punti = df[col].astype(float).to_numpy()[q]
    if np.mean(punti > 0) < ROLLOVER_QUOTA_MIN:
        return None
    in_pips = punti * _punto_symbol(symbol, df["Close"]) / pip_symbol(symbol)
    return round(float(np.median(in_pips)), 1)


def spread_listino(symbol: str, df: pd.DataFrame) -> dict:
    """
    Spread normale e nel rollover, in pips, dal SOLO listino
    (SPREAD_LISTINO_PIPS). E' la fonte del notebook principale (10/10/2026).

    Symbol senza riga: si ferma, e il messaggio contiene la riga esatta da
    aggiungere, col rollover proposto dai dati (`proposta_rollover`) o con
    l'avviso che la colonna spread non basta. Lo spread normale non viene
    mai ricavato dai dati: la colonna e' il minimo di barra di un feed che sul
    forex vale quasi sempre zero, non lo spread del conto Standard.
    """
    s = symbol.upper()
    if s in SPREAD_LISTINO_PIPS:
        v = SPREAD_LISTINO_PIPS[s]
        return {"normale": float(v["normale"]), "rollover": v.get("rollover"),
                "fonte": "listino del conto Standard"}
    roll = proposta_rollover(s, df)
    if roll is None:
        valore, nota = "None", ("colonna spread non significativa nella quarantena: "
                                "rollover da leggere in MT5 verso le 23:00 italiane")
    else:
        valore, nota = f"{roll:.1f}", ("rollover proposto dai dati: mediana nelle barre di "
                                     "quarantena, limite inferiore")
    chiave = f'"{s}":'
    raise ValueError(
        f"Manca lo spread di listino di {s}. Aggiungi questa riga a SPREAD_LISTINO_PIPS "
        f"in engine/vetrina.py, con lo spread normale del conto Standard in pips "
        f"(indici: punti) al posto di ...:\n\n"
        f'    {chiave:<9} {{"normale": ..., "rollover": {valore}}},   # {nota}\n'
    )


def spread_in_pips(symbol: str, df: pd.DataFrame, percentile: float = 75.0) -> dict:
    """
    Spread normale e nel rollover, in pips, senza MetaTrader.

    Ritorna {"normale", "rollover" (o None), "fonte"}. Vedi «I COSTI» in cima.
    `df` deve avere l'indice gia' in UTC (serve per trovare le barre del rollover).
    """
    s = symbol.upper()
    if s in SPREAD_LISTINO_PIPS:
        v = SPREAD_LISTINO_PIPS[s]
        return {"normale": float(v["normale"]), "rollover": v.get("rollover"),
                "fonte": "listino del conto Standard"}

    col = next((c for c in df.columns if c.lower() == "spread"), None)
    if col is not None:
        punti = df[col].astype(float)
        if float(punti.median()) > 0:
            close = df["Close"].astype(float)
            # 10/10/2026: pip fisso se il symbol e' in engine/simboli.py; uno
            # strumento fuori tabella resta una lettura dai dati, come prima
            pip = pip_symbol(s) if in_tabella(s) else deduci_pip(float(close.mean()))
            in_pips = punti * _punto_symbol(s, close) / pip
            normale = float(np.percentile(in_pips.dropna(), percentile))
            roll = quarantena_cached(df)["rollover"].to_numpy(dtype=bool)
            rollover = (float(np.percentile(in_pips[roll].dropna(), percentile))
                        if roll.sum() >= 100 else None)
            if rollover is not None and rollover <= normale:
                rollover = None      # nessun allargamento misurabile: nessun costo in piu'
            return {"normale": normale, "rollover": rollover,
                    "fonte": f"dati storici ({percentile:.0f}° percentile)"}

    raise ValueError(
        f"Non conosco lo spread di {symbol}: non e' in SPREAD_LISTINO_PIPS "
        f"(engine/vetrina.py) e la colonna 'spread' del CSV non e' utilizzabile. "
        f"Aggiungi una riga alla tabella, in pips.")


# ========================================================================
# 1 · Configura
# ========================================================================

def _registra_condizioni() -> None:
    """Carica nel registro tutte le condizioni dei file del repo."""
    import entry_long
    import entry_short
    import exit_long
    import exit_short
    import filter_conditions
    import vwap_regime_filter_conditions
    with _zitto():
        entry_long.registra_trigger_long()
        entry_short.registra_trigger_short()
        exit_long.registra_exit_long()
        exit_short.registra_exit_short()
        filter_conditions.registra_filtri()
        vwap_regime_filter_conditions.registra_filtri_vwap()


def _e_oraria(nome) -> bool:
    from condizioni_orarie import e_oraria
    return e_oraria(nome)


def _trigger_candidati(direzione: int | None = None) -> list[str]:
    """I trigger veri del registro: senza le composite in OR e senza le metro."""
    esclusi = set()
    try:
        from entry_composita import elenca_composite
        esclusi |= set(elenca_composite())
    except Exception:
        pass
    try:
        from entry_metro import NOMI_METRO
        esclusi |= set(NOMI_METRO)
    except Exception:
        pass
    tutte = set(reg.list_entries())
    # le entry «ENTRY+FILTRO» nascono quando si congela un filtro (schermata 6):
    # sono combinazioni gia' scelte, non trigger da esplorare. Le entry a
    # orario (ORA_LONG_@HH:MM) si registrano solo quando le scegli (19/10/2026)
    return [n for n in reg.list_entries(direzione)
            if n not in esclusi and not ("+" in n and n.split("+")[0] in tutte)
            and not _e_oraria(n)]


def _tutti_i_filtri() -> list[str]:
    # 22/10/2026: senza le celle dell'atlante, registrate su richiesta (strada B, docs/66 §5)
    return [n for n in reg.list_filters(0) + reg.list_filters(1) + reg.list_filters(-1)
            if not n.startswith("CELLA_")]


TIMEFRAMES = ("M5", "M15", "M30", "H1", "H4")    # 19/10/2026: quelli che il Lab accetta


def carica_storico(symbol: str, cartella="dati", timeframe: str = "M15") -> pd.DataFrame:
    """
    Lo storico di `symbol` con indice UTC verificato, dal CSV
    `{cartella}/{symbol}_{timeframe}.csv` (19/10/2026, comune al Lab e al
    notebook di ricerca). Imposta anche la quarantena del rollover per i
    calcoli che seguono:

      broker (SIMBOLI)            ora server -> UTC con REGOLA_FUSO; fuso
                                  verificato sul symbol se e' un forex,
                                  altrimenti su EURUSD M15 della stessa
                                  cartella (la regola e' del server, docs/10);
                                  rollover 16:45-18:00 NY, come sempre;
      exchange (SIMBOLI_EXCHANGE) gia' UTC (engine/exchange.leggi_csv);
                                  nessun rollover (mercato 24/7, prezzi degli
                                  scambi): imposta_rollover(None).
    E l'inizio della giornata (20/10/2026, docs/63 §10.1 punto 3): 17:00 New
    York sul broker, 00:00 UTC sui symbol da exchange (livelli.imposta_giornata).
    """
    info_symbol(symbol)            # si ferma subito se il symbol non e' in engine/simboli.py
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Timeframe {timeframe!r} non previsto: usa uno di {list(TIMEFRAMES)}.")
    percorso = os.path.join(str(cartella), f"{symbol}_{timeframe}.csv")
    if not os.path.exists(percorso):
        aiuto = ("scaricalo con scarica_dati_crypto.py" if da_exchange(symbol)
                 else "scaricalo con scarica_dati.py")
        raise FileNotFoundError(f"Non trovo {percorso}: serve il CSV dello storico {timeframe} di "
                                f"{symbol} ({aiuto}).")
    if da_exchange(symbol):
        from .exchange import leggi_csv
        imposta_rollover(None)
        imposta_giornata(GIORNATA_UTC)
        df = leggi_csv(percorso)                    # indice UTC; niente weekend da controllare
        attesa = pd.Timedelta(timeframe.replace("M", "") + "min") if timeframe.startswith("M") \
            else pd.Timedelta(timeframe[1:] + "h")
        if passo_barre(df.index) != attesa:
            raise ValueError(f"{percorso}: le barre sono da {passo_barre(df.index)}, non da {timeframe}.")
        return df
    imposta_rollover(ROLLOVER_DEFAULT)
    imposta_giornata(GIORNATA_FX)
    with _zitto():
        df = pd.read_csv(percorso, index_col="Date")
        df = to_utc_index(df, REGOLA_FUSO, on_dst_gap="drop")
    if info_symbol(symbol)["classe"] == "forex":
        verifica_indice_utc(df, verbose=False)
    else:
        # indici, oro e cripto riaprono a orari loro: il fuso del server si verifica su EURUSD
        rif = os.path.join(str(cartella), "EURUSD_M15.csv")
        if not os.path.exists(rif):
            raise FileNotFoundError(f"{symbol} non e' un forex: per verificare il fuso del server "
                                    f"serve anche {rif}.")
        with _zitto():
            df_rif = to_utc_index(pd.read_csv(rif, index_col="Date"), REGOLA_FUSO,
                                  on_dst_gap="drop", verbose=False)
        verifica_indice_utc(df_rif, verbose=False)
    return df


def costi_storico(symbol: str, df: pd.DataFrame, funding: pd.DataFrame | None = None,
                  df_prezzo: pd.DataFrame | None = None) -> tuple[dict, dict]:
    """
    I costi del backtest per `symbol` su `df` (19/10/2026, comune al Lab e al
    notebook di ricerca). Ritorna (costi, sp):

      costi  il dizionario da passare con **costi ai motori: spread,
             commission, pip_size, cash, spread_rollover_pips;
      sp     {"normale", "rollover", "fonte"}: lo spread in pips e la sua fonte
             (piu' "taker" e "maker" per i symbol da exchange).

    Broker: spread dal solo listino del conto Standard (`spread_listino`),
    nessuna commissione, come prima. Exchange: commissione taker per lato e
    spread di un passo (engine/exchange.costi_exchange), nessun rollover.
    Si ferma se CASH e' meno di 10 volte il prezzo massimo.

    funding (21/10/2026, docs/63 §5): lo storico di carica_funding. Sui
    perpetual finisce in costi["funding"] e con **costi arriva ai motori, che
    lo contano trade per trade (FundingPips). None = non contato, come prima.

    df_prezzo (25/10/2026, docs/70 §15.3, strada A di Mattia): sui symbol da
    exchange lo spread di un passo diventa una frazione del prezzo con il
    prezzo mediano di `df_prezzo`. Il Lab e il notebook di ricerca passano
    l'IN-SAMPLE: nessun dato dell'out-of-sample nei costi, e l'in-sample resta
    identico quando arrivano barre nuove. None = la mediana di `df`, come prima.
    Il broker (sospeso) non cambia.

    25/10/2026 (docs/71, strada D): sui symbol da exchange lo spread esce dal
    prezzo di fill. costi["spread"] = 0 e costi["spread_passo_pips"] = un
    passo in pips: con **costi arriva ai motori, che lo aggiungono a
    CostoExtraPips di ogni trade; in bp vale passo / prezzo d'ingresso. La
    mediana (df_prezzo) non serve piu' per lo spread: il parametro resta.
    """
    prezzo_max = float(df["High"].max())
    if CASH < 10 * prezzo_max:
        raise ValueError(f"CASH = {CASH:,} e' meno di 10 volte il prezzo massimo di {symbol} "
                         f"({prezzo_max:,.2f}): alza CASH in engine/vetrina.py.")
    if da_exchange(symbol):
        from .exchange import costi_exchange, parti_symbol
        c = costi_exchange(symbol, df if df_prezzo is None else df_prezzo)
        p = parti_symbol(symbol)
        # 25/10/2026 (docs/71): spread fuori dal prezzo di fill, un passo per trade in CostoExtraPips
        costi = {"spread": 0.0, "spread_passo_pips": c["spread_pips"], "commission": c["commission"],
                 "pip_size": c["pip_size"], "cash": CASH, "spread_rollover_pips": None}
        if funding is not None and p["mercato"] == "PERP":
            costi["funding"] = funding
        sp = {"normale": c["spread_pips"], "rollover": None, "taker": c["taker"], "maker": c["maker"],
              "fonte": f"listino {p['exchange'].title()} {p['mercato'].lower()}, livello base"}
        return costi, sp
    sp = spread_listino(symbol, df)
    with _zitto():
        costi = parametri_backtest(symbol, bars=df, valuta_conto="USD", usa_mt5=False,
                                   spread_pips=sp["normale"], commissione_rt=0.0)
    costi["cash"] = CASH
    costi["spread_rollover_pips"] = sp["rollover"]
    return costi, sp


def carica_funding(symbol: str, df: pd.DataFrame, cartella="dati") -> pd.DataFrame | None:
    """
    Lo storico del funding di un perpetual (21/10/2026, docs/63 §5), dal CSV
    `{cartella}/{symbol}_FUNDING.csv` di scarica_dati_crypto.py: tasso e
    intervallo_ore, indice UTC. None sugli altri symbol (CFD, spot): non
    pagano il funding. Comune al Lab e al notebook di ricerca.

    Si ferma, dicendo quale file serve e come scaricarlo, se il CSV manca o non
    copre le barre di `df` (exchange.copertura_funding): nessuno zero al posto
    dei tassi che mancano.
    """
    from .exchange import copertura_funding, file_funding, ha_funding, leggi_funding
    if not ha_funding(symbol):
        return None
    percorso = file_funding(symbol, cartella)
    comando = f"python scarica_dati_crypto.py {symbol}"
    if not os.path.exists(percorso):
        raise FileNotFoundError(
            f"Non trovo {percorso}: serve lo storico del funding di {symbol}, un perpetual. Scaricalo sul PC "
            f"con «{comando}» (aggiorna barre e funding insieme); su Colab caricalo poi su Google Drive, "
            "accanto al CSV delle barre.")
    funding = leggi_funding(percorso)
    motivo = copertura_funding(funding, df)
    if motivo is not None:
        raise ValueError(f"{percorso} non copre le barre di {symbol}: {motivo}. Aggiorna barre e funding "
                         f"insieme con «{comando}» (su Colab: ricarica tutti e due i CSV su Google Drive).")
    return funding


# 29/10/2026 (docs/77, lavoro 1): tolta aggancia_spot (lo spot agganciato al perpetual per la basis
# dell'atlante): la basis non c'e' piu'.


def _frase_funding(s) -> str:
    """La riga «Funding (perpetual)» della schermata 1 (21/10/2026, docs/63 §5.5)."""
    if s.funding is None:
        return "spento: non contato nei risultati (serve solo alla prova di identità)"
    from .exchange import ORE_RIFERIMENTO, liquidazioni_mancanti
    f = s.funding
    dentro = f[(f.index >= s.df_is.index[0]) & (f.index <= s.df_is.index[-1])]
    a8 = (dentro["tasso"] * ORE_RIFERIMENTO / dentro["intervallo_ore"]).replace([np.inf, -np.inf], np.nan).dropna()
    medio = float(a8.mean()) if len(a8) else float("nan")
    chi = ("in media il long paga, lo short incassa" if medio > 0 else
           "in media lo short paga, il long incassa" if medio < 0 else "in media nessuno paga")
    frase = f"contato. Tasso medio dell'in-sample {_fmt(medio * 100, 4)}% ogni 8 ore; {chi}"
    mancanti = int(liquidazioni_mancanti(f).sum())
    if mancanti:
        frase += f" (nello storico mancano {mancanti} liquidazioni: non contate)"
    return frase


# ========================================================================
# 25/10/2026 (docs/70): i dati in locale e lo studio
# ========================================================================
#
# apri_dati    aggiorna i dati (in locale, se richiesto), carica lo storico, fa il reset
#              del confine se richiesto, entra nello studio (il confine unico, l'impronta),
#              taglia le barre al funding se il funding e' meno avanti, carica il funding.
# dividi_dati  in-sample e out-of-sample: al confine dello studio, o all'80% come prima.
# Il registro del dataset (docs/68 §9.1) si ricostruisce dai giornali dello studio e ogni
# cambio (H, conto delle prove, diario, risalite) si aggiunge al giornale di questa macchina.
#
# confine   None       come prima: 80% delle barre a ogni giro, niente studio, nessun
#                      avviso (il predefinito delle funzioni, per i test e gli script)
#           "studio"   il confine unico dello studio (il Lab e il notebook di ricerca)
#           "80%"      la regola di prima, ma dichiarata: confine di collaudo (prove
#                      d'identita'), avviso arancione, niente studio
#           una data   quel confine, di collaudo, niente studio

_CONTESTO_STUDIO: dict = {}     # chiave del registro -> dove scrivere il giornale (cartella, dataset, ...)
_SCRITTO: dict = {}             # chiave del registro -> quello che e' gia' nel giornale


def macchina_predefinita() -> str:
    """«colab» su Colab, «pc» altrove: il nome del giornale di questa macchina (docs/70 §4.3)."""
    try:
        import google.colab  # noqa: F401
        return "colab"
    except ImportError:
        return "pc"


def cartella_drive_locale() -> str | None:
    """
    La cartella dei dati dentro Google Drive per desktop, se c'e' (docs/70 §4.1):
    …/Il mio Drive/Trading-System-Creator_V4/dati (anche «My Drive»), su qualunque
    disco o nella cartella dell'utente. None se non c'e'.
    """
    import string
    from pathlib import Path
    radici = [Path(f"{lettera}:/") for lettera in string.ascii_uppercase] if os.name == "nt" else []
    casa = Path.home()
    radici += [casa, casa / "Google Drive", Path("/Volumes/GoogleDrive")]
    for r in radici:
        for nome in ("Il mio Drive", "My Drive"):
            c = r / nome / "Trading-System-Creator_V4" / "dati"
            try:
                if c.is_dir():
                    return str(c)
            except OSError:
                continue
    return None


def file_da_copiare(da, a) -> list[str]:
    """I file di dati di `da` (CSV) che in `a` mancano o sono piu' vecchi (primo avvio con Drive)."""
    from pathlib import Path
    out = []
    for f in sorted(Path(da).glob("*.csv")):
        g = Path(a) / f.name
        if not g.exists() or f.stat().st_mtime > g.stat().st_mtime + 1:
            out.append(f.name)
    return out


def cartella_dati_avvio(progetto, su_colab: bool, drive_colab, copia_su_drive: bool = False) -> str:
    """
    La cartella dei dati per l'Avvio dei due notebook (docs/70 §1.1, §4.1). Su
    Colab: Drive. In locale: la cartella di Google Drive per desktop se c'e',
    altrimenti dati/ del progetto. Al primo avvio con Drive, se dati/ ha CSV
    piu' recenti, li elenca e li copia solo con copia_su_drive=True.
    """
    import shutil
    if su_colab:
        return str(drive_colab)
    locale = os.path.join(str(progetto), "dati")
    drive = cartella_drive_locale()
    if drive is None:
        print(f"Dati da {locale}. Google Drive per desktop non trovato: se lavori anche su Colab, dopo un "
              "aggiornamento carica su Drive i file che la schermata 1 elenca.")
        return locale
    print(f"Dati dalla cartella di Google Drive per desktop: {drive} (la stessa che vede Colab).")
    if os.path.isdir(locale):
        elenco = file_da_copiare(locale, drive)
        if elenco and copia_su_drive:
            for nome in elenco:
                shutil.copy2(os.path.join(locale, nome), os.path.join(drive, nome))
            print(f"Copiati su Drive {len(elenco)} file da dati/: {', '.join(elenco)}.")
        elif elenco:
            print(f"In dati/ ci sono {len(elenco)} file più recenti di quelli su Drive ({', '.join(elenco[:6])}"
                  f"{' …' if len(elenco) > 6 else ''}). Per copiarli accendi copia_su_drive e riesegui l'Avvio.")
    return drive


def _modo_confine(confine) -> str:
    if confine is None:
        return "vecchio"
    if confine == "studio":
        return "studio"
    if confine == "80%":
        return "collaudo80"
    return "data"


_TEMPI_PRIMO = {"M5": "circa 5 minuti su Binance, fino a 15 su Bybit",
                "M15": "circa 1-2 minuti su Binance, fino a 5 su Bybit",
                "M30": "circa un minuto", "H1": "meno di un minuto", "H4": "pochi secondi"}


def apri_dati(symbol: str, timeframe: str = "M15", cartella="dati", confine=None, aggiorna: bool = False,
              ricalcola_confine: str = "", macchina: str | None = None, quota_in_sample: float = 0.8,
              funding: bool = True, verbose: bool = True) -> SimpleNamespace:
    """
    I dati di un dataset pronti per dividerli (docs/70). Ritorna un oggetto con:
      df, funding           lo storico (gia' tagliato al funding se serve) e il funding (o None)
      modo, confine         "vecchio" / "studio" / "collaudo80" / "data" e il confine (None = 80%)
      ingresso              l'ingresso nello studio (engine/studio.Ingresso), dopo dividi_dati
      aggiornamento, reset  cosa hanno fatto l'aggiornamento e il reset (o None)
      tagliate, fino        barre lasciate fuori perche' il funding e' meno avanti, e l'ultima tenuta
    Con confine=None fa esattamente quello che facevano prima carica_storico e
    carica_funding. L'ingresso nello studio (e il reset) li fa dividi_dati, sulle
    barre che si dividono davvero: quelle dopo gli indicatori, che scartano le
    prime barre di riscaldamento. Cosi' l'80% all'apertura dello studio e'
    esattamente quello di prima.
    """
    macchina = macchina or macchina_predefinita()
    modo = _modo_confine(confine)
    d = SimpleNamespace(symbol=symbol, timeframe=timeframe, cartella=cartella, modo=modo, confine=None,
                        ingresso=None, aggiornamento=None, reset=None, tagliate=0, fino=None, funding=None,
                        df=None, quota=quota_in_sample, macchina=macchina,
                        ricalcola_confine=ricalcola_confine or "")
    if aggiorna:
        if macchina == "colab" or not da_exchange(symbol):
            d.aggiornamento = "non qui"
        else:
            from .aggiorna_dati import aggiorna_per_lab, file_storico
            if not file_storico(symbol, timeframe, cartella).exists():
                _nota(f"Primo download completo di {symbol} {timeframe} dal 2/1/2020"
                      + (" (con il funding)" if "_PERP_" in symbol else "")
                      + f": {_TEMPI_PRIMO.get(timeframe, 'qualche minuto')}. Puoi fermare la cella e rilanciarla: "
                      "riparte dall'ultima barra salvata.")
            d.aggiornamento = aggiorna_per_lab(symbol, timeframe, cartella, verbose=verbose)
    df = carica_storico(symbol, cartella, timeframe)
    d.grezzo = df                       # le barre del CSV, per l'impronta dell'in-sample
    taglio = None                       # il confine che il taglio al funding deve rispettare
    if modo == "studio":
        aperto = _st.leggi_confine(cartella)
        taglio = None if aperto is None else _st._utc(aperto["confine"])
    elif modo == "data":
        c = pd.Timestamp(confine)
        d.confine = taglio = c.tz_localize("UTC") if c.tzinfo is None else c.tz_convert("UTC")
    if funding:
        from .exchange import file_funding, ha_funding, leggi_funding
        if taglio is not None and ha_funding(symbol) and os.path.exists(file_funding(symbol, cartella)):
            df, d.tagliate, d.fino = _st.taglia_al_funding(df, leggi_funding(file_funding(symbol, cartella)),
                                                         taglio, timeframe)
        d.funding = carica_funding(symbol, df, cartella)
    d.df = df
    return d


def dividi_dati(d: SimpleNamespace, df: pd.DataFrame,
                ricalcola_confine: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    In-sample e out-of-sample di `df` (lo storico di `d` dopo gli indicatori, come
    lo dividevano prima il Lab e il notebook di ricerca). Con il confine dello
    studio: prima il reset, se chiesto, poi l'ingresso nello studio (lo apre se
    non c'e', all'80% di `df`: lo stesso confine di prima). Senza studio: all'80%
    o alla data di collaudo. ricalcola_confine: il campo del reset, se lo si scrive
    qui (notebook di ricerca) invece che in apri_dati.
    """
    if ricalcola_confine is not None:
        d.ricalcola_confine = ricalcola_confine
    if d.modo == "studio":
        if d.ricalcola_confine:
            d.reset = _st.reset(d.cartella, d.ricalcola_confine, d.symbol, d.timeframe, df, d.macchina,
                                quota=d.quota)
        d.ingresso = _st.entra(d.cartella, d.symbol, d.timeframe, df, d.macchina, quota=d.quota,
                               df_impronta=getattr(d, "grezzo", None))
        d.confine = d.ingresso.confine
        return d.ingresso.df_is, d.ingresso.df_oos
    if d.confine is None:
        return split_is_oos(df, is_ratio=d.quota)
    return split_al_confine(df, d.confine, _st.passo(d.timeframe))


def _giorno_ora(t) -> str:
    return pd.Timestamp(t).strftime("%d/%m/%Y %H:%M") + " UTC"


def mostra_dati(d: SimpleNamespace) -> None:
    """I riquadri dell'aggiornamento, del reset e dello studio (docs/70 §1.2, §2, §5.3, §6.2)."""
    a = d.aggiornamento
    if a == "non qui":
        _nota("Aggiorna i dati: ignorato qui (su Colab i dati non si scaricano: Binance e Bybit bloccano Colab).")
    elif a:
        righe, fermi = [], []
        for parte in a.values():
            if parte["esito"] == "aggiornato":
                c = parte.get("controlli") or {}
                extra = ("" if "doppie" not in c else
                         f" (controlli sulle barre nuove: {c['doppie']} doppie, {c['buchi']} buchi, "
                         f"{c['ohlc_incoerenti']} OHLC incoerenti, {c['dopo_interruzione']} in quarantena)")
                righe.append(f"{parte['nome']}: +{_fmt(parte['nuove'])}"
                             + (f", fino al {_giorno_ora(parte['al'])}" if parte.get("al") is not None else "") + extra)
            else:
                fermi.append(f"{parte['nome']}: aggiornamento non riuscito ({parte['errore'][:160]}); lavori sui dati "
                             + (f"fino al {_giorno_ora(parte['al'])}." if parte.get("al") is not None
                                else "che ci sono."))
        if righe:
            _nota("Dati aggiornati. " + " — ".join(righe) + "."
                  + (" Tutte le barre nuove sono nell'out-of-sample: il confine non si è mosso."
                     if d.modo == "studio" else ""))
        for f in fermi:
            _avviso(f)
    r = d.reset
    if r:
        e = r["esito"]
        if e == "fatto":
            _nota(f"Confine ricalcolato: dal {_giorno_ora(r['vecchio'])} al {_giorno_ora(r['nuovo'])}. Lo studio di "
                  f"prima è in archivio ({r['archivio']}); il conto delle prove riparte da zero.")
        elif e == "rifiutato_indietro":
            _avviso(r["messaggio"])
        elif e == "data_non_di_oggi":
            _avviso(f"Nel campo ricalcola_confine c'è «{r['campo']}», non la data di oggi: nessun ricalcolo. Svuotalo.")
        elif e == "data_non_valida":
            _avviso(f"Nel campo ricalcola_confine c'è «{r['campo']}»: per ricalcolare scrivi la data di oggi "
                    "(gg/mm/aaaa). Nessun ricalcolo.")
        elif e == "gia_fatto_oggi":
            _nota("Il confine è già stato ricalcolato oggi: nessun ricalcolo nuovo. Svuota il campo ricalcola_confine.")
        elif e == "nessuna_barra_nuova":
            _nota("Il confine ricalcolato sarebbe uguale a quello di adesso: nessun ricalcolo.")
        elif e == "ignorato_colab":
            _nota("Il confine si ricalcola solo sul PC: su Colab il campo ricalcola_confine è ignorato.")
        elif e == "nessuno_studio":
            _nota("Non c'era ancora uno studio: lo apro adesso, niente da ricalcolare.")
    if d.modo in ("collaudo80", "data"):
        _avviso("Confine di collaudo (" + ("regola vecchia, 80% di questo dataset" if d.modo == "collaudo80"
                                          else f"il {_giorno_ora(d.confine)}")
                + "): non è il confine dello studio. Niente di quello che fai qui entra nel diario o nel conto dello "
                "studio.")
    i = d.ingresso
    if i is not None:
        st = i.studio
        if i.aperto_ora:
            _nota(f"Hai aperto lo studio: il confine è il {_giorno_ora(i.confine)} ({st['regola']}). Vale da ora per "
                  "ogni exchange, moneta e timeframe.")
        elif i.esito_impronta == "nuova":
            _nota(f"{i.dataset} entra adesso nello studio, con il confine dello studio ({_giorno_ora(i.confine)}).")
        if st.get("contaminato"):
            _avviso(_frase_contaminato(st["contaminato"]))
        if i.is_corto:
            _avviso(f"L'in-sample di questo dataset è corto ({_fmt(i.quota_is * 100, 1)}% delle barre): i risultati "
                    "hanno poche barre dietro.")
        if i.suggerisci_reset:
            _nota(f"L'out-of-sample è ora il {_fmt((1 - i.quota_is) * 100, 0)}% dei dati di questo dataset: se vuoi "
                  "ricalcolare il confine, vedi il campo ricalcola_confine. Non è obbligatorio.")
    if d.tagliate:
        _nota(f"Il funding arriva fino a dove copre le barre: lavori sulle barre fino al {_giorno_ora(d.fino)}; le altre "
              f"{_fmt(d.tagliate)} restano nel file e si usano quando arriva il funding (sono out-of-sample).")


def _frase_contaminato(c: dict, corta: bool = False) -> str:
    dove = ", ".join(f"{n} {'volta' if n == 1 else 'volte'} su {ds}" for ds, n in c["guardato"].items())
    if corta:
        return (f"In-sample con out-of-sample già guardato: il periodo dal {_giorno_ora(c['dal'])} al "
                f"{_giorno_ora(c['al'])} ({dove}, nello studio precedente).")
    return (f"Il nuovo in-sample contiene il periodo dal {_giorno_ora(c['dal'])} al {_giorno_ora(c['al'])}, che avevi "
            f"già guardato come out-of-sample: {dove}. Le crypto si muovono insieme: su quel periodo i risultati li "
            "conosci già, su ogni dataset. Costruire sopra di esso non è più una prova pulita. Questo avviso resta "
            "su questo studio.")


def _stato_scritto(storia) -> dict:
    import copy
    return {"prove": copy.deepcopy(storia.prove or {}), "diario": len(storia.diario),
            "risalite": len(storia.risalite)}


def _storia_dello_studio(d: SimpleNamespace, H: int, nuove_prove):
    """
    Il registro del dataset dallo studio: ricostruito da tutti i giornali, poi
    aperto con H come sempre (registro_dataset.apri). Un H nuovo (o un ritorno)
    si aggiunge al giornale. Ritorna (storia, esito, info dei giornali).
    """
    i = d.ingresso
    storia, info = _st.ricostruisci(d.cartella, i.dataset, i.studio, nuove_prove=nuove_prove)
    _CONTESTO_STUDIO[storia.chiave] = {"cartella": d.cartella, "dataset": i.dataset, "macchina": d.macchina,
                                       "studio": i.studio}
    storia, esito = _rd.apri(d.symbol, d.timeframe, i.confine, H, nuove_prove=nuove_prove)
    if esito != "stesso_h":
        _st.aggiungi_voce(d.cartella, i.dataset, d.macchina, i.studio["id"], {"voce": "orizzonte", "H": int(H)})
    _SCRITTO[storia.chiave] = _stato_scritto(storia)
    return storia, esito, info


def _salva_studio(storia) -> None:
    """Aggiunge al giornale di questa macchina quello che e' cambiato nel registro (prove, diario, risalite)."""
    if not _nel_studio(storia):
        return
    ctx, fatto = _CONTESTO_STUDIO[storia.chiave], _SCRITTO[storia.chiave]
    voci = _st.voci_prove(fatto["prove"], storia.prove or {})
    voci += [{"voce": "oos", "voce_diario": e} for e in storia.diario[fatto["diario"]:]]
    voci += [{"voce": "risalita", "risalita": r} for r in storia.risalite[fatto["risalite"]:] if r.get("cosa") != "H"]
    for v in voci:
        _st.aggiungi_voce(ctx["cartella"], ctx["dataset"], ctx["macchina"], ctx["studio"]["id"], v)
    _SCRITTO[storia.chiave] = _stato_scritto(storia)


def oos_fresco(storia, df_oos: pd.DataFrame) -> dict | None:
    """
    L'out-of-sample «fresco» (25/10/2026, docs/70 §13): il tratto mai guardato,
    cioe' le barre dopo l'ultima barra out-of-sample gia' aperta su QUALUNQUE
    dataset dello studio. Da chiamare PRIMA di scrivere nel diario l'apertura di
    adesso. Ritorna None senza studio o se l'out-of-sample non e' mai stato
    aperto (e' tutto fresco); altrimenti {"fino", "dove", "barre"}: l'ultima
    barra gia' guardata, le aperture per dataset, le barre nuove di df_oos.
    """
    if not _nel_studio(storia):
        return None
    ctx = _CONTESTO_STUDIO[storia.chiave]
    fino, dove = _st.ultimo_oos_guardato(ctx["cartella"], ctx["studio"])
    if fino is None:
        return None
    return {"fino": fino, "dove": dove, "barre": df_oos.index[df_oos.index > fino]}


def trade_freschi(info: dict | None, trades: pd.DataFrame, df_oos: pd.DataFrame) -> pd.DataFrame | None:
    """
    I trade del tratto mai guardato: quelli ENTRATI dopo l'ultima barra gia'
    guardata (decisione di Mattia del 25/10: un trade a cavallo della data resta
    fuori, il suo ingresso l'avevi gia' visto). EntryBar e' la barra di df_oos.
    """
    if info is None:
        return None
    if trades is None or len(trades) == 0:
        return trades
    ingresso = pd.DatetimeIndex(df_oos.index)[trades["EntryBar"].to_numpy(dtype=int)]
    return trades[np.asarray(ingresso > info["fino"])]


def _frase_fresco(info: dict, n_trade: int, min_trade: int) -> str:
    dove = ", ".join(f"{n} {'volta' if n == 1 else 'volte'} su {ds.replace('_M', ' M').replace('_H', ' H')}"
                     for ds, n in info["dove"].items())
    if len(info["barre"]) == 0:
        return (f"Nessuna barra nuova dall'ultima apertura (fino al {_giorno_ora(info['fino'])}): questo "
                f"out-of-sample l'hai già visto tutto ({dove}).")
    frase = (f"Mai guardato: dal {_giorno_ora(info['barre'][0])}, {_fmt(len(info['barre']))} barre e "
             f"{_fmt(n_trade)} trade. Prima di quella data l'out-of-sample l'hai già visto ({dove}).")
    if n_trade == 0:
        frase += " Nel tratto nuovo non c'è nessun trade."
    elif n_trade < min_trade:
        frase += f" Campione corto (meno di {_fmt(min_trade)} trade): da leggere, non da giudicare."
    return frase


def _nel_studio(storia) -> bool:
    return storia is not None and getattr(storia, "chiave", None) in _CONTESTO_STUDIO


def _note_studio(storia, info: dict | None = None) -> None:
    """Sotto la schermata 1 e sopra la scheda: le aperture su altri dataset e la contaminazione."""
    if not _nel_studio(storia):
        return
    ctx = _CONTESTO_STUDIO[storia.chiave]
    altrove = _st.diario_altrove(ctx["cartella"], ctx["dataset"], ctx["studio"])
    if altrove:
        _nota("Out-of-sample di questo studio già guardato su altri dataset: "
              + ", ".join(f"{n} {'volta' if n == 1 else 'volte'} su {ds}" for ds, n in altrove.items())
              + ". È lo stesso periodo: non è più nuovo nemmeno qui.")
    if info:
        if info.get("altre_id"):
            _nota(f"{info['altre_id']} voci del giornale sono dello studio precedente (scritte dopo il reset da una "
                  "sessione rimasta aperta): non entrano in questo studio.")
        if info.get("copie"):
            _avviso("Nella cartella dello studio ci sono copie di conflitto di Drive (" + ", ".join(info["copie"])
                    + "): le ho lette lo stesso, nessuna voce persa. Non lavorare sullo stesso dataset su PC e Colab "
                    "nello stesso momento.")


def _minuti_barra(timeframe: str) -> int:
    return int(timeframe[1:]) * (1 if timeframe.startswith("M") else 60)


def prepara(symbol: str = "EURUSD", H: int = 25, quota_in_sample: float = 0.8,
            cartella: str = "dati", timeframe: str = "M15", funding: bool = True,
            motore: str | None = None, confine=None, aggiorna: bool = False,
            ricalcola_confine: str = "", macchina: str | None = None) -> Sessione:
    """
    Schermata 1. Carica lo storico dal CSV, calcola costi e indicatori,
    divide in-sample / out-of-sample e carica le condizioni dal registro.

    symbol            nome dello strumento: serve il file `{symbol}_{timeframe}.csv`
    H                 orizzonte di osservazione, in barre (unico per long e short)
    quota_in_sample   parte iniziale dello storico usata per costruire (0.8 = 80%)
    cartella          dove stanno i CSV. Default "dati" (la cartella dati/ del
                      progetto, dal 17/10); il Lab passa DATI_DIR: dati/ in locale, Google
                      Drive su Colab.
    timeframe         19/10/2026: M5, M15 (default, come prima), M30, H1, H4
    funding           21/10/2026: True (default) = sui perpetual il funding e'
                      contato in ogni risultato (carica_funding: si ferma se il
                      file manca o non copre le barre). False = spento: serve
                      solo alla prova di identita' con la versione di prima.
    motore            21/10/2026 (docs/65): "bt" (backtesting.py) o "veloce"
                      (engine/motore_veloce.py, stessi trade). None (default) =
                      il predefinito del tool (motore_veloce.MOTORE_PREDEFINITO).
    confine           25/10/2026 (docs/70 §2): None (default) = come prima, 80% delle
                      barre a ogni giro, niente studio; "studio" = il confine unico
                      dello studio, salvato su file (il Lab); "80%" = la regola di
                      prima dichiarata come collaudo; una data = quel confine, di collaudo
    aggiorna          25/10/2026 (docs/70 §1): True = in locale scarica prima le barre
                      nuove (e spot e funding del perpetual); su Colab ignorato
    ricalcola_confine 25/10/2026 (docs/70 §5): la data di oggi (gg/mm/aaaa) = ricalcola
                      il confine dello studio (solo sul PC); "" = niente
    macchina          25/10/2026 (docs/70 §4.3): il nome del giornale ("pc", "colab");
                      None = "colab" su Colab, "pc" altrove

    11/10/2026, allineata al notebook principale (Trading_Grid_Search_v4):
    symbol solo dalla tabella di engine/simboli.py; spread dal solo listino
    (`spread_listino`: senza riga si ferma con la riga esatta da aggiungere);
    verifica del fuso sul symbol se e' un forex, altrimenti su EURUSD della
    stessa cartella (la regola del fuso e' del server, docs/10); si ferma se
    CASH e' meno di 10 volte il prezzo massimo.

    19/10/2026, versione crypto: i symbol da exchange (engine/simboli.py,
    SIMBOLI_EXCHANGE) si caricano gia' in UTC, senza rollover, con la
    commissione taker dell'exchange e il profilo orario in UTC
    (`carica_storico`, `costi_storico`). Sullo spot si opera solo long.

    Ritorna la sessione da passare alle schermate successive.
    """
    H = int(H)
    if H < 1:
        raise ValueError("H deve essere almeno 1 barra.")
    # 25/10/2026 (docs/70): aggiornamento, studio, reset e taglio al funding; con confine=None
    # apri_dati fa solo quello che facevano prima carica_storico e carica_funding
    dati = apri_dati(symbol, timeframe, cartella, confine=confine, aggiorna=aggiorna,
                     ricalcola_confine=ricalcola_confine, macchina=macchina, quota_in_sample=quota_in_sample,
                     funding=funding)
    df = dati.df
    storico_funding = dati.funding                       # 21/10/2026
    grezzo = df                                          # per i costi, dopo la divisione

    s = Sessione()
    s.dati = dati
    s.funding = storico_funding
    s.motore = scegli_motore(motore)     # 21/10/2026 (docs/65)
    s.symbol, s.H, s.cartella, s.timeframe = symbol, H, cartella, timeframe
    s.da_exchange = da_exchange(symbol)
    if s.da_exchange:
        from .exchange import solo_long
        s.solo_long = solo_long(symbol)
    with _zitto():
        df = aggiungi_indicatori(df)
        s.df_is, s.df_oos = dividi_dati(dati, df)    # 25/10/2026: al confine dello studio, o all'80%
    # 25/10/2026 (docs/70 §15.3, strada A): lo spread si converte con il prezzo mediano dell'in-sample
    costi, sp = costi_storico(symbol, grezzo, funding=storico_funding, df_prezzo=s.df_is)
    s.df, s.costi = df, costi
    s.atr = atr_giornaliero_chiuso(df)   # 20/10/2026: sullo storico intero, noto prima di ogni ingresso
    # 20/10/2026 (docs/63 §4.2, U2): sui symbol da exchange decide il bp in ogni passo; il broker,
    # sospeso (§10.0), resta in pips come prima
    s.unita = "bp" if s.da_exchange else "pips"
    s.pip = costi["pip_size"]      # 10/10/2026: fisso, da engine/simboli.py
    s.fuso = fuso_profilo(symbol)  # 18/10/2026: fissato a priori per symbol (UTC sugli exchange)
    import condizioni_orarie
    condizioni_orarie.imposta_fuso(s.fuso)   # 19/10/2026: entry e uscite a orario
    s.spread_pips, s.spread_rollover_pips, s.fonte_spread = sp["normale"], sp["rollover"], sp["fonte"]
    _registra_condizioni()
    # 25/10/2026 (docs/68 §9.1, correzione A di Mattia): il registro del dataset (symbol, timeframe,
    # confine dell'in-sample). Con lo stesso dataset la sessione nuova riprende il conto delle prove e
    # il diario dell'out-of-sample; un H diverso e' una risalita, e la scelta fra gli H provati si conta
    precedente = _ULTIMO_DATASET.get("chiave")
    info_giornali = None
    if dati.ingresso is not None:
        # 25/10/2026 (docs/70 §3-§4): il registro dai giornali dello studio, e ogni cambio nel giornale
        s.storia, esito, info_giornali = _storia_dello_studio(dati, H, lambda: s.prove)
    else:
        s.storia, esito = _rd.apri(symbol, timeframe, s.df_is.index[-1], H, nuove_prove=lambda: s.prove)
    s.prove = s.storia.prove
    _ULTIMO_DATASET["chiave"] = s.storia.chiave

    def giorno(t):
        return pd.Timestamp(t).strftime("%d/%m/%Y")

    if s.da_exchange:
        costo = (f"commissione {_fmt(sp['taker'] * 100, 3)}% per lato (taker) + spread di "
                 f"{_fmt(sp['normale'], 2)} pips ({sp['fonte']})")
        rollover = "nessun rollover: mercato aperto 24 ore su 24"
    else:
        costo = f"{_fmt(sp['normale'])} pips di spread, nessuna commissione ({sp['fonte']})"
        rollover = (f"{_fmt(sp['rollover'])} pips" if sp["rollover"] is not None
                    else "come il resto della giornata")
    n_short = "lo short non esiste sullo spot" if s.solo_long else f"{len(_trigger_candidati(-1))} short"
    voci = ["Strumento", f"Barre {timeframe}", "Periodo", "In-sample (per costruire)",
            "Out-of-sample (mai visto)", "Costo per trade", "Costo nel rollover",
            "Orizzonte di osservazione", "Trigger disponibili", "Filtri disponibili"]
    valori = [symbol, _fmt(len(df)), f"{giorno(df.index[0])} – {giorno(df.index[-1])}",
              f"{_fmt(len(s.df_is))} barre, fino al {giorno(s.df_is.index[-1])}",
              f"{_fmt(len(s.df_oos))} barre, dal {giorno(s.df_oos.index[0])}",
              costo, rollover,
              f"{H} barre ({_fmt(H * _minuti_barra(timeframe) / 60, 1)} ore)",
              f"{len(_trigger_candidati(1))} long · {n_short}",
              _fmt(len(_tutti_i_filtri()))]
    if s.da_exchange and not s.solo_long:
        voci.append("Funding (perpetual)")
        valori.append(_frase_funding(s))      # 21/10/2026
    if dati.ingresso is not None:             # 25/10/2026 (docs/70 §1.2): da dove viene il confine
        ing = dati.ingresso
        nuove = 0
        if isinstance(dati.aggiornamento, dict) and dati.aggiornamento["candele"]["esito"] == "aggiornato":
            nuove = max(0, int(dati.aggiornamento["candele"]["nuove"]) - int(dati.tagliate))
        valori[voci.index("In-sample (per costruire)")] = (
            f"{_fmt(len(s.df_is))} barre ({_fmt(len(s.df_is) / len(df) * 100, 1)}%), fino al "
            f"{_giorno_ora(ing.confine)} · confine dello studio")
        valori[voci.index("Out-of-sample (mai visto)")] = (
            f"{_fmt(len(s.df_oos))} barre, dal {_giorno_ora(ing.confine)}"
            + (f" (di cui {_fmt(nuove)} arrivate oggi)" if nuove else ""))
        n_qui = len(s.storia.diario)
        altrove = sum(_st.diario_altrove(cartella, ing.dataset, ing.studio).values())
        voci.append("Studio")
        valori.append(f"aperto il {pd.Timestamp(ing.studio['aperto_il']):%d/%m/%Y} su {ing.studio['aperto_su']} · "
                      f"vale per tutti i dataset · out-of-sample guardato: {n_qui} "
                      f"{'volta' if n_qui == 1 else 'volte'} su questo dataset, {altrove} su altri dataset")
    # 20/10/2026 (docs/63 §4): lo stesso costo in punti base del prezzo (1 bp = 0,01%)
    mediana = float(s.df_is["Close"].median())
    spread_bp = sp["normale"] * s.pip / mediana * 10_000
    if s.da_exchange:
        comm_bp = 2 * sp["taker"] * 10_000
        # 25/10/2026 (docs/71, strada D): un passo al prezzo d'ingresso di ogni trade
        from .exchange import spread_bp as _spread_bp
        per_barra = _spread_bp(sp["normale"], s.pip, s.df_is["Close"].to_numpy())
        costo_bp = (f"{_fmt(comm_bp + spread_bp, 1)} bp andata e ritorno al prezzo mediano dell'in-sample: "
                    f"commissione {_fmt(comm_bp, 1)} bp a qualunque prezzo + spread di un passo al prezzo "
                    f"d'ingresso di ogni trade, da {_fmt(float(np.nanmin(per_barra)), 2)} a "
                    f"{_fmt(float(np.nanmax(per_barra)), 2)} bp nell'in-sample (mediana {_fmt(spread_bp, 2)})")
    else:
        costo_bp = f"{_fmt(spread_bp, 2)} bp al prezzo mediano dell'in-sample (lo spread fisso pesa di più a prezzi bassi)"
    voci.insert(voci.index("Costo per trade") + 1, "Costo per trade in bp")
    valori.insert(voci.index("Costo per trade in bp"), costo_bp)
    riepilogo = pd.DataFrame({"": voci, " ": valori})
    s.tabelle["riepilogo"] = riepilogo
    mostra_dati(dati)                         # 25/10/2026 (docs/70): aggiornamento, reset, studio
    _mostra(("Il tuo laboratorio", riepilogo))
    _riquadro(
        "Lo storico su cui lavori, diviso in due: l'in-sample serve a costruire la strategia, "
        "l'out-of-sample resta chiuso in cassaforte fino alla fine."
        + (" Sul perpetual ogni trade paga, o incassa, il funding di ogni liquidazione in cui è aperto, al "
           "prezzo di apertura della barra della liquidazione: l'exchange usa il prezzo «mark», che qui non c'è, "
           "e la differenza è di pochi millesimi sul costo." if s.funding is not None else ""),
        "Qui non c'è ancora niente da giudicare. Controlla solo che strumento, periodo e costi "
        "siano quelli che ti aspetti: ogni risultato che vedrai è già al netto di questi costi. "
        "L'orizzonte è la scelta che pesa di più: è il tempo che dai al movimento e, dalla schermata 4, la "
        "durata consigliata del trade. Sceglilo prima di guardare i risultati.",
        "Vai alla schermata 2 per vedere come si muove il mercato ora per ora e cosa fanno i trigger.")
    if dati.ingresso is not None:
        _nota("Il confine è la data che divide le barre su cui costruisci (prima) da quelle che restano chiuse fino "
              "alla scheda (dopo). È uno solo per tutto lo studio: ogni exchange, moneta e timeframe usa la stessa "
              "data, perché le crypto si muovono insieme e un periodo guardato su BTC non è più nuovo per ETH. L'ha "
              "fissato il primo dataset aperto (80% delle sue barre) e non si muove più: le barre che arrivano dopo "
              "vanno tutte nell'out-of-sample.")
    _nota_dataset(s, esito, precedente)
    _note_studio(s.storia, info_giornali)
    return s


_ULTIMO_DATASET: dict = {}      # 25/10/2026: la chiave dell'ultimo dataset aperto in questo notebook


def _nota_dataset(s: Sessione, esito: str, precedente) -> None:
    """Cosa e' successo al conto delle prove aprendo questo dataset (docs/68 §9.1)."""
    storia = s.storia
    if esito == "nuovo" and _nel_studio(storia):
        # 25/10/2026 (docs/70): il registro e' nello studio, su file
        if precedente is not None and precedente != storia.chiave:
            _nota("Dataset diverso da quello di prima (strumento o timeframe): il conto delle prove e il diario "
                  "dell'out-of-sample sono quelli di questo dataset.")
        _nota("Il conto delle prove e il diario dell'out-of-sample di questo dataset sono salvati nello studio "
              "(nel giornale di questa macchina): restano anche se chiudi il notebook. Cambiare orizzonte su questo "
              "dataset si conta.")
        return
    if esito == "nuovo":
        if precedente is not None and precedente != storia.chiave:
            _nota("Dataset diverso da quello di prima (strumento, timeframe o confine dell'in-sample): il conto "
                  "delle prove e il diario dell'out-of-sample ripartono da zero.")
        _nota("Il conto delle prove e il diario dell'out-of-sample di questo dataset restano finché il notebook "
              "è aperto: rieseguire questa cella, anche con un altro orizzonte, non li azzera. Riavviare il "
              "notebook sì.")
        return
    if esito == "stesso_h":
        return
    r = storia.risalite[-1]
    h = ", ".join(str(x) for x in storia.h_provati)
    testo = (f"Hai già lavorato su questo dataset con H = {r['da']}. Cambiare orizzonte dopo aver visto i "
             f"risultati è una scelta fra orizzonti: si conta. Orizzonti provati su questo dataset: {h}"
             + (" (questo era già fra loro: nessuna prova in più)." if esito == "h_gia_provato" else ".")
             + " Il conto delle prove continua da dove era.")
    if storia.oos_visto:
        testo += (f" Hai anche già guardato l'out-of-sample ({len(storia.diario)} "
                  f"{'volta' if len(storia.diario) == 1 else 'volte'}): la prossima scheda non è più una prova pulita.")
    _avviso(testo)


# ========================================================================
# 2 · Esplora
# ========================================================================

def _favorevoli(s: Sessione, direzione: int) -> pd.DataFrame:
    """
    La sintesi dell'event study di un lato, dal trigger piu' favorevole al meno.

    ATTENZIONE AL SEGNO (corretto il 7/10/2026). `run_event_study` moltiplica
    gia' ogni variazione per la direzione del trigger: curve, `picco_pips` e
    `volte_incertezza` sono «a favore del trade» per ENTRAMBI i lati
    (positivo = il trade guadagna, anche per uno short). Qui quindi NON si
    ribalta nulla: la prima versione lo faceva sugli short e metteva in cima
    alla classifica i peggiori.
    """
    t = s.ev.sintesi[s.ev.sintesi["direction"] == direzione].copy()
    t["a_favore_pips"] = t["picco_pips"]
    t["solidita"] = t["volte_incertezza"]
    oltre = t["oltre_rumore"].astype(bool) if "oltre_rumore" in t.columns else False
    t["rumore"] = np.where(oltre & (t["solidita"] > 0), "sì",
                           np.where(oltre, "sì, ma contro", "no"))
    return t.sort_values("solidita", ascending=False).reset_index(drop=True)


def _grafico_curve(s: Sessione, candidati: list[str], lato: str) -> None:
    """
    Le curve dell'event study di un lato, in pips. Stessi dati di
    `EventStudy.plot`; qui cambiano solo titolo ed etichette, per dire in
    chiaro che l'asse e' il guadagno del trade e non il prezzo.
    """
    import matplotlib.pyplot as plt
    curve = s.ev.in_pips(s.ev.curve)
    mercato = s.ev.in_pips(s.ev.mercato)
    fig, ax = plt.subplots(figsize=(11, 5))
    for c in candidati:
        ax.plot(curve.index, curve[c], lw=1.7, label=c)
    ax.plot(mercato.index, mercato[candidati[0]], color="black", ls="--", lw=1.2,
            label=f"entrando {lato} a caso (tutte le barre)")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("barre dal segnale")
    ax.set_ylabel(f"guadagno medio del trade {lato}  (pips, prima dei costi)")
    ax.set_title(f"Trigger {lato.upper()}: guadagno medio del trade nelle {s.H} barre dopo il segnale"
                 "   (sopra lo zero = guadagna)")
    ax.grid(alpha=.3)
    ax.legend(fontsize=8, loc="best")
    plt.tight_layout()
    plt.show()


def _rosa_sessione(s: Sessione) -> pd.DataFrame:
    """La rosa dei trigger della sessione (rosa_entry), calcolata una volta per orizzonte."""
    r = getattr(s, "rosa_trigger", None)
    if r is None or r.attrs.get("H") != s.H:
        with _zitto():
            s.rosa_trigger = rosa_entry(s.df_is, s.H, s.pip,
                                        nomi=_trigger_candidati(1 if s.solo_long else None),
                                        min_eventi=MIN_TRIGGER, fuso=s.fuso, atr=s.atr, unita=s.unita)
    return s.rosa_trigger


def _curve_scarto(s: Sessione, nomi: list[str], qualunque_ora=()) -> pd.DataFrame:
    """Le curve dello scarto (stagionalita.curva_scarto_orario) dei trigger indicati, nell'unita' che decide."""
    if not nomi:
        return pd.DataFrame(index=pd.RangeIndex(1, s.H + 1, name="barre_dal_trigger"))
    return curva_scarto_orario(s.df_is, list(nomi), s.H, s.pip,
                               fuso=getattr(s, "fuso", None) or fuso_profilo(getattr(s, "symbol", "")),
                               unita=getattr(s, "unita", "pips"), qualunque_ora=qualunque_ora,
                               atr=getattr(s, "atr", None))


def _grafico_scarto(s: Sessione, curve: pd.DataFrame, lato: str) -> None:
    grafico_scarto(curve, s.H, s.unita, lato)


def grafico_scarto(curve: pd.DataFrame, H: int, unita: str, lato: str) -> None:
    """Le curve dello scarto di un lato (25/10/2026, docs/68 §2.1): sopra lo zero = meglio del mercato a quell'ora."""
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 5))
    for c in curve.columns:
        ax.plot(curve.index, curve[c], lw=1.7, label=c)
    ax.axhline(0, color="black", lw=0.8)
    # 26/10/2026 (docs/73 §A.1.3): titoli allineati al testo deciso da Mattia
    ax.set_xlabel("barre dall'ingresso")
    ax.set_ylabel(f"in più o in meno del mercato a quell'ora\n({unita}, prima dei costi)")
    ax.set_title(f"Segnali {lato.upper()}: quanti {unita} guadagnano in più (sopra lo zero) o in meno (sotto lo "
                 "zero) del mercato, barra dopo barra dall'ingresso")
    ax.grid(alpha=.3)
    ax.legend(fontsize=8, loc="best")
    plt.tight_layout()
    plt.show()


def esplora(s: Sessione, quanti: int = 5):
    """
    Schermata 2c (dal 25/10/2026, docs/68 §2.1; prima schermata 2). Misura,
    per ogni trigger del registro, come si muove in media il prezzo nelle H
    barre dopo il segnale (`run_event_study`, sull'in-sample: e' il conto dei
    trigger misurati) e disegna, per i `quanti` trigger con la solidita' netta
    piu' alta della rosa per lato, la CURVA DELLO SCARTO: barra per barra,
    quanto il trade fa meglio del mercato della stessa ora, nell'unita' che
    decide (stagionalita.curva_scarto_orario). E' lo stesso metro della rosa
    (schermata 3a): a k = H la curva coincide con lo scarto della rosa.

    Ritorna l'oggetto EventStudy (anche in `s.ev`); le curve sono in `s.curve_scarto`.
    """
    s._serve("df_is", "1 · Configura")
    _avviso_risalita(s, "rieseguire l'esplorazione")
    candidati = _trigger_candidati(1 if s.solo_long else None)    # spot: solo long (19/10/2026)
    with _zitto():
        s.ev = run_event_study(s.df_is, entry_names=candidati, horizon=s.H,
                               min_trades=MIN_TRIGGER, pip=s.pip, verbose=False)
    misurati = len(s.ev.sintesi)
    _nota_blocchi(s.ev.sintesi, "segnali")
    # 22/10/2026: soglia cumulata (H e' fisso nella sessione); 28/10/2026 (docs/76): il numero piu' alto
    _rd.metti_prova(s.prove, "trigger", None, misurati)
    _nota(f"{misurati} segnali misurati su {len(candidati)} "
          f"(gli altri scattano meno di {MIN_TRIGGER} volte: troppo pochi per fidarsi della media)."
          + (" Spot: solo i segnali long, lo short non esiste." if s.solo_long else ""))
    rosa = _rosa_sessione(s)
    mostrati = []
    for direzione in (1, -1):
        if direzione in s.lati():
            lato = rosa[rosa["direction"] == direzione].sort_values("t_netto", ascending=False)
            mostrati += list(lato["candidato"].head(quanti))
    s.curve_scarto = _curve_scarto(s, mostrati)
    globali = _curve_scarto(s, mostrati, qualunque_ora=mostrati)
    for direzione, nome in ((1, "long"), (-1, "short")):
        nomi = [m for m in mostrati if int(reg.get_entry_direction(m)) == direzione]
        if nomi:
            _grafico_scarto(s, s.curve_scarto[nomi], nome)
    if mostrati:
        punti = sorted({max(1, s.H // 4), max(1, s.H // 2), max(1, (3 * s.H) // 4), s.H})
        tab_g = pd.DataFrame({"Segnale": mostrati,
                              **{f"barra {k} ({s.unita})": [globali.loc[k, m] for m in mostrati] for k in punti}})
        s.tabelle["curve_qualunque_ora"] = tab_g
        _dettaglio("Gli stessi segnali contro il mercato di tutte le ore (per vedere quanto pesa l'ora)",
                   ("In più del mercato di tutte le ore, prima dei costi", tab_g))
    _riquadro(
        f"Ogni linea è un segnale (trigger). Barra dopo barra dall'ingresso, quanti {s.unita} guadagna in più "
        "(sopra lo zero) o in meno (sotto lo zero) di quello che il mercato fa da solo a quell'ora (il profilo "
        "della 2a), prima dei costi. Per long e short vale la stessa regola: sopra lo zero il segnale fa meglio "
        f"del mercato. Sono i segnali più solidi della rosa (3a), al massimo {quanti} per lato.",
        "Una linea che sale e resta sopra lo zero indica un segnale che aggiunge qualcosa al mercato. La curva si "
        "legge, non si sceglie: la durata del trade resta l'orizzonte H che hai dichiarato alla schermata 1. Nel "
        "dettaglio sotto il grafico, gli stessi segnali contro il mercato di tutte le ore: serve a vedere quanto "
        "pesa l'ora.",
        "Vai alla 3a: i segnali che la rosa suggerisce, con i numeri.")
    _riga_prove(s, f"{misurati} trigger misurati")
    return s.ev


def _frasi_profilo(p: pd.DataFrame, u: str, luogo: str) -> list[str]:
    """
    Le frasi sotto il grafico della 2a (26/10/2026, docs/73 §A.1.2, revisione di Mattia): stesse
    informazioni di stagionalita.descrivi_profilo (che resta per il notebook di ricerca), con il
    linguaggio nuovo, i numeri con la virgola e una riga sola sul controllo dei colpi di fortuna.
    """
    if p is None or len(p) == 0:
        return ["Nessuna ora misurabile."]
    ora = "ora UTC" if luogo == "UTC" else f"ora di {luogo}"
    col = f"scarto_{u}"
    alta, bassa = p.loc[p[col].idxmax()], p.loc[p[col].idxmin()]

    def caso(r):
        return " Il caso da solo non lo spiega." if r["bh"] else " Può essere solo caso."

    def quanto(r):
        v = float(r[col])
        return f"{_fmt(abs(v), 1)} {u} {'in più' if v >= 0 else 'in meno'} della media di tutte le ore"

    n_oltre = int(p["bh"].sum())
    return [
        f"Se apri un LONG alle {alta['fascia']} ({ora}) e lo tieni {p.attrs.get('H')} barre, in media il prezzo fa "
        f"{quanto(alta)}: è l'ora migliore per un long." + caso(alta),
        f"Se apri un LONG alle {bassa['fascia']} il prezzo fa {quanto(bassa)}: è l'ora peggiore per un long, e per "
        "uno SHORT aperto a quell'ora vale al contrario." + caso(bassa),
        (f"Ore che il caso da solo non spiega: {n_oltre} su {len(p)}."
         + (" Ore vicine raccontano lo stesso fatto: contale come un'idea sola." if n_oltre > 1 else ""))
        if n_oltre else
        f"Nessuna ora resta fuori da quello che il caso da solo spiega ({len(p)} fasce orarie).",
    ]


def profilo_delle_ore(s: Sessione) -> pd.DataFrame:
    """
    Schermata 2a (dal 25/10/2026, docs/68 §6: prima delle curve; prima era la
    2b). Il profilo orario di engine/stagionalita.py sull'in-sample: per ogni
    fascia oraria (larga una barra, ora locale della piazza di riferimento)
    quanto si muove in media il prezzo nelle H barre dopo, rispetto alla
    media di tutte le barre. E' il metro delle schermate 2c-4 (ogni trigger
    si confronta con il mercato della sua stessa ora), la fonte dei trigger a
    orario e quella di X_INVERSIONE_TREND, che riusa questo stesso profilo.

    23/10/2026: nell'unita' che decide (bp sui symbol da exchange, con i pips
    accanto nella tabella; pips sul broker, come prima).

    Ritorna la tabella del profilo (anche in `s.profilo`).
    """
    import matplotlib.pyplot as plt
    s._serve("df_is", "1 · Configura")
    _avviso_risalita(s, "rieseguire il profilo orario")
    u = s.unita
    with _zitto():
        s.profilo = (profilo_orario(s.df_is, s.H, s.pip, fuso=s.fuso) if u == "pips"
                     else profilo_orario(s.df_is, s.H, s.pip, fuso=s.fuso, unita=u))
    p = s.profilo
    _nota_blocchi(p, "ore")
    luogo = s.fuso.split("/")[-1].replace("_", " ")
    fig, ax = plt.subplots(figsize=(11, 4.5))
    x = np.arange(len(p))
    colori = np.where(p["bh"], np.where(p[f"scarto_{u}"] > 0, "tab:green", "tab:red"), "lightgray")
    ax.bar(x, p[f"scarto_{u}"], color=colori, width=0.85)
    ax.errorbar(x, p[f"scarto_{u}"], yerr=2 * p["incertezza"], fmt="none", ecolor="black",
                elinewidth=0.6, alpha=0.5)
    ax.axhline(0, color="black", lw=0.8)
    passo = max(1, len(p) // 24)
    ax.set_xticks(x[::passo])
    ax.set_xticklabels(p["fascia"].iloc[::passo], rotation=90, fontsize=8)
    # 26/10/2026 (docs/73 §A.1.2): titoli allineati al testo deciso da Mattia
    ax.set_xlabel(f"ora d'ingresso ({luogo})")
    ax.set_ylabel(f"variazione del prezzo nelle {s.H} barre dopo,\nin più o in meno della media di tutte le ore ({u})")
    ax.set_title("Il mercato ora per ora: dopo quest'ora il prezzo sale (verde) o scende (rosso) più del solito?   "
                 "(grigio = può essere caso)")
    ax.grid(alpha=.3, axis="y")
    plt.tight_layout()
    plt.show()
    for frase in _frasi_profilo(p, u, luogo):
        _nota(frase)
    oltre = p[p["bh"]]
    if not oltre.empty:
        tabella = pd.DataFrame({
            "Ora d'ingresso": oltre["fascia"],
            f"In più o in meno della media di tutte le ore ({u})": oltre[f"scarto_{u}"],
            f"Oscillazione casuale ({u})": oltre["incertezza"],
            "Solidità": oltre["t"],
            "Regge sulle due metà": [_si_no(v) for v in oltre["due_meta"]],
        })
        if u != "pips":                             # i pips accanto, solo da leggere
            tabella.insert(3, "In più o in meno della media di tutte le ore (pips)", oltre["scarto_pips"].to_numpy())
        s.tabelle["profilo"] = tabella
        _mostra((f"Le ore che il caso da solo non spiega (in-sample, {s.H} barre, prima dei costi)", tabella),
                decimali={"Solidità": 2})
    _riquadro(
        f"Per ogni ora del giorno ({luogo}): di quanto sale o scende in media il prezzo nelle {s.H} barre dopo, "
        f"in più o in meno della media di tutte le ore, in {u}. Sopra lo zero il prezzo tende a salire più del "
        "solito, sotto lo zero a scendere più del solito. Le stanghette nere sono l'oscillazione dovuta al caso.",
        "Verdi e rosse sono le ore che il caso da solo non spiega, anche contando che le ore guardate sono tante; "
        "grigie le altre. Ore vicine raccontano lo stesso fatto: un gruppo colorato è un'idea sola. È una media "
        "su tutti i giorni dell'in-sample e non dice niente del singolo giorno. È il termine di paragone dei "
        "segnali: dalla 2c alla 4 ogni segnale si confronta con quello che il mercato fa da solo a quell'ora.",
        f"Vai alla 2c. Se vuoi un segnale a orario (es. ORA_LONG_@12:30: si entra ogni giorno alle 12:30, ora "
        f"{luogo}), lo aggiungi alla 3b. Alla 4 puoi chiudere a un orario (X_ORA_@16:00), oppure quando arriva "
        "un'ora rossa per il long o verde per lo short (X_INVERSIONE_TREND).")
    _riga_prove(s, "nessuna (le fasce si contano solo se scegli un trigger a orario)")
    return p


# ========================================================================
# 2b · La mappa delle anomalie (28/10/2026, docs/73 §B.5), in sola lettura
# ========================================================================

def _quando_locale(t) -> str:
    return pd.Timestamp(t).tz_convert("Europe/Rome").strftime("%d/%m/%Y %H:%M")


def _attese_in_chiaro(attese: dict) -> str:
    return " · ".join(f"{f} → {'sopra il mercato (long)' if v > 0 else 'sotto il mercato (short)'}"
                      for f, v in attese.items())


def esiti_mappa_ultimi(esiti: list) -> list[dict]:
    """L'esito piu' recente di ogni scheda (id, versione, orizzonte), nell'ordine della prima misura."""
    ultimi = {}
    for e in esiti:
        ultimi[(e["scheda"], int(e["versione"]), float(e["orizzonte_ore"]))] = e
    return list(ultimi.values())


def tabella_mappa(esiti: list, prove: dict | None) -> pd.DataFrame:
    """
    Le schede della mappa misurate su un dataset (la tabella di docs/73 §B.5):
    l'ultimo esito di ognuna dal file della mappa, le fasce contate dal registro.
    La usano la 2b del Lab e il riepilogo del notebook della mappa.
    """
    from .ipotesi import SCHEDE, SCHEDE_TOLTE
    contate = (prove or {}).get("mappa", {}) or {}
    righe = []
    for e in esiti_mappa_ultimi(esiti):
        sch = SCHEDE.get(e["scheda"])
        n = contate.get((e["scheda"], int(e["versione"]), float(e["orizzonte_ore"])))
        righe.append({
            "Scheda": f"{e['scheda']} · {e['titolo']} (versione {e['versione']})",
            "Meccanismo": (sch.meccanismo if sch is not None and sch.versione == int(e["versione"])
                           # 29/10/2026 (docs/77): gli esiti delle schede tolte restano, con la nota
                           else f"scheda tolta dal catalogo il {SCHEDE_TOLTE[e['scheda']]}"
                           if e["scheda"] in SCHEDE_TOLTE else ""),
            "Fascia attesa e segno": _attese_in_chiaro(e["attese"]),
            "Orizzonte (ore)": _fmt(float(e["orizzonte_ore"]), 0),
            "Esito": e["verdetto"],
            "Misurata il": _quando_locale(e["quando"]),
            "Fasce contate": _fmt(int(n)) if n is not None else "alla prossima schermata 1",
            "TradingView": e["portabilita"],
            "Trigger nato": "—",
        })
    righe.sort(key=lambda r: r["Meccanismo"].startswith("scheda tolta"))   # le schede tolte in fondo (29/10)
    return pd.DataFrame(righe, columns=["Scheda", "Meccanismo", "Fascia attesa e segno", "Orizzonte (ore)", "Esito",
                                        "Misurata il", "Fasce contate", "TradingView", "Trigger nato"])


def mappa_del_dataset(s: Sessione) -> pd.DataFrame:
    """
    Schermata 2b (28/10/2026, docs/73 §B.5): le schede della mappa delle anomalie
    misurate su questo dataset, IN SOLA LETTURA. Legge solo i file
    studio/<dataset>/mappa_*.jsonl: non misura, non scrive, non cambia s.prove.
    Le fasce della mappa sono gia' nel conto del dataset dalla schermata 1 (il
    registro si ricostruisce dai giornali); una scheda misurata dopo entra nel
    conto alla prossima schermata 1. Ritorna la tabella (anche in s.tabelle["mappa"]).
    """
    s._serve("df_is", "1 · Configura")
    storia = getattr(s, "storia", None)
    if not _nel_studio(storia):
        _nota("La mappa delle anomalie vive nello studio: con un confine di collaudo non c'è niente da mostrare.")
        tab = tabella_mappa([], None)
        s.tabelle["mappa"] = tab
        _riga_prove(s, "nessuna")
        return tab
    ctx = _CONTESTO_STUDIO[storia.chiave]
    esiti = _st.leggi_esiti_mappa(ctx["cartella"], ctx["dataset"], ctx["studio"]["id"])
    tab = tabella_mappa(esiti, s.prove)
    s.tabelle["mappa"] = tab
    if tab.empty:
        _nota(f"Nessuna scheda della mappa misurata su questo dataset ({ctx['dataset']}). Le schede si misurano "
              "nel notebook Mappa_Anomalie_Crypto.ipynb.")
    else:
        _mostra((f"Le schede della mappa misurate su {ctx['dataset']} (in-sample dello studio)", tab))
        if (tab["Fasce contate"] == "alla prossima schermata 1").any():
            _nota("Alcune schede sono state misurate dopo la schermata 1 di questa sessione: le loro fasce entrano "
                  "nel conto quando riesegui la schermata 1.")
    _riquadro(
        "Le ipotesi della mappa delle anomalie misurate su questo dataset. Ogni scheda è stata scritta e approvata "
        "prima di guardare i dati: dice in quale fascia di una variabile il prezzo dovrebbe fare meglio o peggio "
        "del mercato, e in quale verso. Si misurano nel notebook della mappa; qui le leggi soltanto.",
        "«Risponde nel verso atteso» vuol dire che la fascia attesa supera gli stessi controlli della rosa (quota "
        "di falsi positivi, due metà, minimi). Non è ancora un trigger: dice dove guardare. «Segno opposto» non "
        "conta come scoperta. Ogni fascia misurata è una prova in più nel conto di questo dataset.",
        "Una scheda che risponde diventa un trigger con il processo degli articoli (scheda, via libera, codice): "
        "la colonna «Trigger nato» lo dirà. Vai alla 2c.")
    _riga_prove(s, "nessuna (le fasce della mappa sono già nel conto del dataset)")
    return tab


# ========================================================================
# 3 · Scegli i trigger
# ========================================================================

_COLONNE_CLASSIFICA = {
    "candidato": "Trigger",
    "a_favore_pips": "Movimento a favore (pips)",
    "barra_picco": "Dopo quante barre",
    "trades": "Occasioni",
    "solidita": "Solidità del segnale",
    "rumore": "Supera il rumore",
}


def classifiche(s: Sessione, quanti: int = 8) -> dict:
    """
    Le due classifiche dei trigger di prima, LONG e SHORT, lette dalla
    sintesi dell'event study (picco lordo in pips, «supera il rumore») e
    ordinate per solidita'. Dal 25/10/2026 (docs/68 §2.2, decisione 5 di
    Mattia) il Lab non la usa piu': la classifica del Lab e' il dettaglio a
    scomparsa della rosa (schermata 3a), con lo stesso metro della rosa.
    Resta per chi la chiama a mano e per i test.

    Ritorna {"long": tabella, "short": tabella}.
    """
    s._serve("ev", "2 · Esplora")
    out, da_mostrare = {}, []
    for direzione, nome in ((1, "long"), (-1, "short")):
        if direzione not in s.lati():          # spot: niente classifica short
            continue
        t = _favorevoli(s, direzione).head(quanti)
        t = t[list(_COLONNE_CLASSIFICA)].rename(columns=_COLONNE_CLASSIFICA)
        out[nome] = t
        if len(t):
            da_mostrare.append((f"Classifica {nome.upper()}", t))
    s.tabelle["classifiche"] = out
    _mostra(*da_mostrare, decimali={"Dopo quante barre": 0})
    _riquadro(
        "Per ogni trigger: il movimento medio più ampio dopo il segnale, in pips e prima dei costi, dopo quante "
        "barre arriva e quante occasioni ci sono state. Positivo = a favore del trade (per uno short: il prezzo "
        "è sceso). Negativo = in media il prezzo è andato contro. La «solidità» dice quante volte il movimento "
        "è più grande della sua normale oscillazione casuale, con lo stesso segno.",
        "Cerca movimento positivo, solidità alta e tante occasioni insieme, e confronta il movimento con il costo "
        "per trade della schermata 1. «Supera il rumore: sì» vuol dire che il risultato è difficile da spiegare "
        "con la sola fortuna, anche tenendo conto di quanti trigger hai messo a confronto. "
        "Solidità fra −2 e 2 circa: potrebbe essere solo caso. Una riga negativa non è un candidato.",
        "Copia nella cella sotto i nomi dei trigger che vuoi portare avanti, uno o più per lato. "
        "Più trigger sullo stesso lato lavorano insieme: si entra quando ne scatta uno qualsiasi.")
    return out


def _si_no(v) -> str:
    return "sì" if bool(v) else "no"


def rosa_dei_trigger(s: Sessione) -> pd.DataFrame:
    """
    Schermata 3a, le casistiche suggerite (18/10/2026; dal 25/10/2026, docs/68
    §2.2 e §4, anche la classifica). La rosa dei candidati di engine/rosa.py
    sui trigger dell'event study: andamento netto positivo che regge il
    controllo della quota di falsi positivi (q = 20%) e le due meta'
    dell'in-sample, e un gruppo suggerito di trigger diversi fra loro (una
    famiglia ciascuno, profitti giornalieri poco correlati). Stesso orizzonte
    H della schermata 1, solo in-sample. I trigger «nella rosa» sono le
    casistiche da cui parte la 3b. Sotto, a scomparsa, la classifica: i primi
    8 per lato con lo stesso metro (scarto dal mercato della stessa ora), con
    la barra del picco della curva, solo da leggere.

    Ritorna la tabella completa di rosa_entry (anche in `s.rosa_trigger`).
    """
    s._serve("ev", "2 · Esplora")
    _avviso_risalita(s, "rileggere le casistiche suggerite")
    r = _rosa_sessione(s)
    _nota_blocchi(r, "trigger")
    vista = r[r["candidata"]]
    if vista.empty:
        _nota(f"Nessun trigger supera i tre controlli della rosa ({len(r)} misurati, orizzonte {s.H} barre). "
              "Sotto, i cinque con la solidità netta più alta, per confronto.")
        vista = r.sort_values("t_netto", ascending=False).head(5)
    u, a = s.unita, _altra_unita(s)
    tabella = pd.DataFrame({
        "Trigger": vista["candidato"],
        "Lato": np.where(vista["direction"] == 1, "long", "short"),
        "Occasioni": vista["eventi"].astype(int),
        f"Più del mercato della stessa ora ({u})": vista[f"scarto_{u}"],
        "Solidità netta": vista["t_netto"],
        f"Più del mercato a qualunque ora ({u})": vista[f"scarto_globale_{u}"],
        f"Più del mercato della stessa ora ({a})": vista[f"scarto_{a}"],
        f"Solidità in {a}": vista[f"t_{a}"],
        "Supera la quota di fortuna": [_si_no(v) for v in vista["bh"]],
        "Regge sulle due metà": [_si_no(v) for v in vista["due_meta"]],
        "Famiglia": vista["famiglia"].astype(int),
        "Nella rosa": [_si_no(v) for v in vista["nella_rosa"]],
        "Perché fuori": vista["perche"],
    })
    s.tabelle["rosa_trigger"] = tabella
    _mostra((f"La rosa dei trigger (in-sample, {s.H} barre, prima dei costi)", tabella),
            decimali={"Solidità netta": 2, f"Solidità in {a}": 2})
    suggerite = {nome: list(r.loc[r["nella_rosa"] & (r["direction"] == d), "candidato"])
                 for d, nome in ((1, "long"), (-1, "short")) if d in s.lati()}
    s.tabelle["casistiche_suggerite"] = suggerite
    _nota("Casistiche suggerite per la 3b · "
          + " · ".join(f"{nome}: {', '.join(v) if v else 'nessuna'}" for nome, v in suggerite.items()) + ".")
    # 25/10/2026 (docs/68 §2.2): la classifica, a scomparsa, con lo stesso metro della rosa
    per_lato, tutti = {}, []
    for d, nome in ((1, "long"), (-1, "short")):
        if d in s.lati():
            per_lato[nome] = r[r["direction"] == d].sort_values("t_netto", ascending=False).head(8)
            tutti += list(per_lato[nome]["candidato"])
    curve = _curve_scarto(s, tutti)
    classi = []
    for nome, t in per_lato.items():
        if t.empty:
            continue
        picchi = [picco_curva(curve[c], s.H) if c in curve else {"barra": None} for c in t["candidato"]]
        classi.append((f"Classifica {nome.upper()}", pd.DataFrame({
            "Trigger": t["candidato"].to_numpy(),
            f"Più del mercato della stessa ora ({u})": t[f"scarto_{u}"].to_numpy(),
            "Solidità netta": t["t_netto"].to_numpy(),
            "Occasioni": t["eventi"].astype(int).to_numpy(),
            "Barra del picco (solo da leggere)": [p["barra"] for p in picchi],
            "Nella rosa": [_si_no(v) for v in t["nella_rosa"]],
        })))
    s.tabelle["classifiche_rosa"] = dict(classi)
    if classi:
        _dettaglio(f"La classifica: i primi 8 per lato, con lo stesso metro (in-sample, {s.H} barre, prima dei costi)",
                   *classi, decimali={"Solidità netta": 2})
    _riquadro(
        "Un gruppo di trigger suggeriti. Ognuno ha un andamento a favore più grande di quello che il mercato "
        "fa da solo nelle stesse ore («più del mercato della stessa ora», il metro del profilo orario della "
        "schermata 2a; accanto, il confronto con tutte le ore), difficile da spiegare con la fortuna anche tenendo conto di quanti trigger "
        f"hai messo a confronto (al massimo il {Q_ROSA:.0%} di colpi di fortuna nella rosa, in media), e positivo "
        "in entrambe le metà dell'in-sample. Dentro la rosa i trigger sono diversi fra loro: famiglie diverse "
        "(non scattano sulle stesse candele) e guadagni giornalieri poco legati "
        f"(correlazione entro ±{_fmt(RHO_MAX, 1)}). Sotto la tabella, a scomparsa, la classifica con lo stesso metro.",
        _frase_unita(s) +
        "È un suggerimento, non una promozione: la verifica vera arriva dopo, con i filtri, le due metà e i dati "
        "mai visti. Un trigger fuori dalla rosa per «famiglia» o «correlata» è buono come quello che lo esclude, "
        "ma ripete la stessa idea. Rosa vuota = nessun trigger si distingue abbastanza dal caso a questo orizzonte.",
        "Vai alla 3b: scegli da dove partire (la rosa, tutte le candidate, niente) e poi togli o aggiungi trigger. "
        "La scelta resta tua.")
    _riga_prove(s, "nessuna (i trigger sono già contati alla 2c)")
    return r


def _durate_orarie(s: Sessione, barre_long: int, barre_short: int, origine: str) -> str | None:
    """
    23/10/2026: con trigger a orario su TUTTI E DUE i lati il segnale opposto chiude
    la posizione aperta. La riga che lo dice, con la durata effettiva di ogni lato:
    il minimo fra le barre di scadenza e la distanza fino al primo orario dell'altro
    lato (sulle crypto esatta: mercato aperto 24 ore su 24). None se non serve.
    """
    import condizioni_orarie
    orari_l = [n.split("@")[1] for n in s.trigger_long if condizioni_orarie.e_oraria(n)]
    orari_s = [n.split("@")[1] for n in s.trigger_short if condizioni_orarie.e_oraria(n)]
    if not orari_l or not orari_s:
        return None
    idx = s.df_is.index
    codice = {o: codice_orario(o, idx, s.fuso)[0] for o in (*orari_l, *orari_s)}
    nf = n_fasce(fasce_orarie(idx, s.fuso)[1])

    def lato(da, a, barre, nome, altro):
        altro = {"long": "il long", "short": "lo short"}[altro]
        distanze = [((codice[y] - codice[x]) % nf, x, y) for x in da for y in a]
        gap, x, y = min(distanze)
        gap = gap or nf                      # stesso orario: l'altro lato torna dopo un giorno intero
        if gap < barre:
            return (f"{nome} al massimo {gap} barre (dalle {x} alle {y}, poi {altro} lo chiude; "
                    f"le barre di scadenza sarebbero {barre})")
        return (f"{nome} {barre} barre, la scadenza ({origine}): dalle {x} alle {y} ce ne sarebbero {gap}")

    return ("Trigger a orario su tutti e due i lati: il segnale opposto chiude la posizione aperta (e apre "
            "quella contraria). Durata effettiva: " + lato(orari_l, orari_s, int(barre_long), "long", "short")
            + "; " + lato(orari_s, orari_l, int(barre_short), "short", "long") + ".")


def _lista_nomi(x) -> tuple:
    """Un nome, piu' nomi separati da virgola, oppure una lista di nomi -> tupla senza vuoti."""
    if x is None:
        return ()
    if isinstance(x, str):
        x = x.split(",")
    return tuple(n.strip() for n in x if isinstance(n, str) and n.strip())


def scegli_trigger(s: Sessione, long=None, short=None) -> None:
    """
    Le casistiche scritte a mano (prima del 25/10/2026 la schermata 3b del
    Lab; dal 25/10 il Lab usa scegli_casistiche, che parte dalla rosa).
    Registra la scelta dei trigger.

    long / short   un nome, piu' nomi separati da virgola o una lista di nomi
                   (lavorano in OR); None o vuoto = quel lato non opera.
                   Almeno un lato deve essere indicato.
    """
    s._serve("ev", "2 · Esplora")
    tl, ts = _lista_nomi(long), _lista_nomi(short)
    _imposta_casistiche(s, tl, ts, {n: "a mano" for n in (*tl, *ts)})


def scegli_casistiche(s: Sessione, togli_long="", aggiungi_long="", togli_short="",
                      aggiungi_short="", parti_da: str = "la rosa") -> pd.DataFrame:
    """
    Schermata 3b, le tue casistiche (25/10/2026, docs/68 §4, decisione 1 di
    Mattia). Si parte dalle casistiche suggerite dalla rosa (i trigger «nella
    rosa» di ogni lato, schermata 3a) e si toglie o si aggiunge: due campi per
    lato, vuoti = la rosa cosi' com'e'. Ogni nome tolto deve essere nel punto
    di partenza di quel lato; ogni nome aggiunto un trigger del catalogo di
    quel lato, o un trigger a orario (ORA_LONG_@HH:MM / ORA_SHORT_@HH:MM). Piu'
    trigger sullo stesso lato lavorano in OR, come prima (decisione 2).

    parti_da   26/10/2026 (docs/73 §A.2): "la rosa" (predefinito, come prima),
               "tutte le candidate" (tutti i trigger che passano i controlli
               della rosa, anche quelli fuori per famiglia o correlazione) o
               "niente" (solo i nomi in «aggiungi»)

    Togliere o aggiungere, e il punto di partenza, non aggiungono prove: i
    trigger sono gia' tutti contati alla schermata 2c. Un trigger a orario
    porta le fasce del profilo.

    Ritorna la tabella delle casistiche.
    """
    s._serve("ev", "2 · Esplora")
    partenza = _partenza(parti_da)
    r = _rosa_sessione(s)
    tl, ts = [], []
    origini = {}
    for d, togli, aggiungi, out in ((1, togli_long, aggiungi_long, tl), (-1, togli_short, aggiungi_short, ts)):
        if d not in s.lati():
            if _lista_nomi(togli) or _lista_nomi(aggiungi):
                raise ValueError(f"{s.symbol} e' spot: lo short non esiste. Lascia vuoti i campi dello short.")
            continue
        nomi, da_dove = casistiche_dalla_rosa(r, d, togli, aggiungi, parti_da=partenza)
        out.extend(nomi)
        origini.update(da_dove)
    if not tl and not ts:
        vuoto = {"rosa": "la rosa è vuota (o l'hai svuotata)",
                 "candidate": "nessun trigger passa i controlli della rosa (o li hai tolti tutti)",
                 "niente": "parti da niente e non hai aggiunto nessun trigger"}[partenza]
        raise ValueError(f"Nessuna casistica: {vuoto}. Aggiungi almeno un trigger, long o short, nei campi "
                         "«aggiungi».")
    return _imposta_casistiche(s, tuple(tl), tuple(ts), origini, parti_da=_PARTI_DA_TESTO[partenza])


# 26/10/2026 (docs/73 §A.2.1): i punti di partenza della 3b, con i nomi del Lab e quelli del notebook di ricerca
_PARTI_DA = {"la rosa": "rosa", "rosa": "rosa", "tutte le candidate": "candidate", "candidate": "candidate",
             "niente": "niente"}
_PARTI_DA_TESTO = {"rosa": "la rosa", "candidate": "tutte le candidate", "niente": "niente"}


def _partenza(parti_da) -> str:
    chiave = _PARTI_DA.get(str(parti_da).strip().lower())
    if chiave is None:
        raise ValueError(f"«parti da» non valido: {parti_da!r}. Scegli fra «la rosa», «tutte le candidate», "
                         "«niente».")
    return chiave


def casistiche_dalla_rosa(rosa: pd.DataFrame, direzione: int, togli=(), aggiungi=(),
                          parti_da: str = "rosa") -> tuple[list, dict]:
    """
    Le casistiche di un lato (25/10/2026, docs/68 §4; anche nel notebook di
    ricerca): i trigger «nella rosa» di quel lato (rosa_entry), meno quelli in
    `togli`, piu' quelli in `aggiungi` (un nome, piu' nomi separati da
    virgola o una lista). Ogni nome tolto deve essere nel punto di partenza
    del lato; ogni nome aggiunto un trigger del catalogo di quel lato o un
    trigger a orario dello stesso lato. Ritorna (nomi, da dove viene ognuno).

    parti_da   26/10/2026 (docs/73 §A.2.1): "rosa" (predefinito, come prima);
               "candidate" = tutti i trigger del lato con `candidata` (t > 0,
               quota di falsi positivi, due meta'), anche quelli fuori dalla
               rosa per famiglia o correlazione, con il motivo in «da dove»;
               "niente" = nessuno, solo i nomi in `aggiungi` (e `togli` vuoto).
               Accetta anche i nomi del Lab («la rosa», «tutte le candidate»).
    """
    import condizioni_orarie
    nome = "long" if direzione == 1 else "short"
    partenza = _partenza(parti_da)
    togli, aggiungi = _lista_nomi(togli), _lista_nomi(aggiungi)
    lato = rosa["direction"] == direzione
    if partenza == "rosa":
        rosa_lato = list(rosa.loc[rosa["nella_rosa"] & lato, "candidato"])
    elif partenza == "candidate":
        rosa_lato = list(rosa.loc[rosa["candidata"].astype(bool) & lato, "candidato"])
    else:
        rosa_lato = []
    if partenza == "niente" and togli:
        raise ValueError(f"Da togliere ({nome}): con «parti da: niente» non c'è niente da togliere. "
                         "Lascia vuoto il campo «togli».")
    fuori = [x for x in togli if x not in rosa_lato]
    if fuori:
        if partenza == "rosa":
            raise ValueError(f"Da togliere ({nome}): {', '.join(fuori)} non è fra le casistiche suggerite. "
                             f"Casistiche suggerite {nome}: {', '.join(rosa_lato) or 'nessuna'}.")
        raise ValueError(f"Da togliere ({nome}): {', '.join(fuori)} non è fra le candidate della rosa. "
                         f"Candidate {nome}: {', '.join(rosa_lato) or 'nessuna'}.")
    catalogo = set(_trigger_candidati(direzione))
    sbagliati = [x for x in aggiungi
                 if not (x in catalogo or (condizioni_orarie.e_oraria(x)
                                           and x.startswith("ORA_LONG_" if direzione == 1 else "ORA_SHORT_")))]
    if sbagliati:
        raise ValueError(f"Da aggiungere ({nome}): {', '.join(sbagliati)} non è un trigger {nome} del catalogo "
                         f"né un trigger a orario {'ORA_LONG_@HH:MM' if direzione == 1 else 'ORA_SHORT_@HH:MM'}. "
                         "Copia il nome dalla rosa o dalla classifica della 3a.")
    nomi, origini = [], {}
    perche = dict(zip(rosa["candidato"], rosa["perche"])) if "perche" in rosa.columns else {}
    nella = set(rosa.loc[rosa["nella_rosa"] & lato, "candidato"])
    for x in rosa_lato:
        if x not in togli:
            nomi.append(x)
            origini[x] = ("rosa" if x in nella
                          else f"candidata, fuori dalla rosa: {perche.get(x) or 'motivo non scritto'}")
    for x in aggiungi:
        if x not in nomi:
            nomi.append(x)
            origini[x] = "aggiunta"
    return nomi, origini


def _imposta_casistiche(s: Sessione, tl: tuple, ts: tuple, origini: dict, parti_da: str | None = None) -> pd.DataFrame:
    """
    Registra le casistiche (trigger in OR per lato) e azzera tutto quello che viene dopo.
    parti_da (26/10/2026, docs/73 §A.2.3): il punto di partenza della 3b, da mostrare nella
    tabella con il riquadro della 3b; None = scelta a mano (scegli_trigger), come prima.
    """
    from entry_composita import risolvi_scelta
    if s.solo_long and ts:
        raise ValueError(f"{s.symbol} e' spot: lo short non esiste. Lascia vuoto il lato short, "
                         "oppure scegli il mercato perpetual (PERP).")
    if not tl and not ts:
        raise ValueError("Scegli almeno un trigger, long o short.")
    prima = (tuple(s.trigger_long), tuple(s.trigger_short))
    if getattr(s, "storia", None) is not None and s.storia.oos_visto and prima != (tl, ts):
        _avviso_risalita(s, "cambiare le casistiche")
        _rd.annota_risalita(s.storia, "casistiche", da=prima, a=(tl, ts))
        _salva_studio(s.storia)       # 25/10/2026 (docs/70): nel giornale dello studio
    with _zitto():
        s.entry_long = risolvi_scelta(list(tl), lato="long") if tl else None
        s.entry_short = risolvi_scelta(list(ts), lato="short") if ts else None
    s.trigger_long, s.trigger_short = tl, ts
    s.casistiche = {lato: {"trigger": t, "origine": {n: origini.get(n, "a mano") for n in t}, "cella": None}
                    for lato, t in (("long", tl), ("short", ts)) if t}
    # una scelta nuova invalida tutto cio' che viene dopo
    s.uscite = s.es = s.fs = s.dm = s.oos = s.rosa_sistemi = None
    s.consigliate = s.sistema = None
    s.sopravvissuti, s.filtro = [], None
    _azzera_cella(s)                  # 22/10/2026: la cella dell'atlante va scelta di nuovo

    scelta = pd.DataFrame({
        "Lato": ["LONG", "SHORT"],
        "Trigger scelti": [" oppure ".join(tl) if tl else "nessuno (lato spento)",
                           " oppure ".join(ts) if ts else "nessuno (lato spento)"],
        "Da dove": [", ".join(f"{n}: {origini.get(n, 'a mano')}" for n in tl) or "—",
                    ", ".join(f"{n}: {origini.get(n, 'a mano')}" for n in ts) or "—"],
    })
    if parti_da is not None:
        scelta.insert(1, "Parti da", parti_da)
    s.tabelle["casistiche"] = scelta
    _mostra(("Le tue casistiche", scelta))
    _nota("Si tiene una posizione alla volta. Se a posizione aperta scatta un trigger del lato opposto, "
          "la posizione si chiude e si apre quella contraria.")
    # 23/10/2026: un trigger a orario e' una delle fasce del profilo orario (schermata 2a, prima 2b): nella soglia
    # cumulata si contano tutte le fasce, una volta sola per sessione
    import condizioni_orarie
    if any(condizioni_orarie.e_oraria(n) for n in (*tl, *ts)):
        _rd.metti_prova(s.prove, "fasce", None, n_fasce(fasce_orarie(s.df_is.index, s.fuso)[1]))
    riga = _durate_orarie(s, s.H, s.H, "l'orizzonte H")
    if riga:
        _nota(riga)
    if parti_da is not None:
        _riquadro(
            "Le tue casistiche, lato per lato: da dove sei partito, cosa hai tolto, cosa hai aggiunto. Più trigger "
            "sullo stesso lato lavorano insieme: si entra quando ne scatta uno qualsiasi.",
            "Scegliere, togliere o aggiungere non aggiunge prove: tutti i trigger del catalogo sono già contati "
            "alla 2c. Con «tutte le candidate» entrano anche trigger della stessa famiglia o molto correlati: "
            "scattano spesso sulle stesse candele, quindi aggiungono trade simili più che idee nuove.",
            "Vuoi provare un trigger alla volta, ciascuno con le sue uscite? È il lavoro del portafoglio di "
            "sistemi, rimandato. Oggi si fa rieseguendo la 3b con un trigger solo, poi con un altro: ogni giro "
            "conta le sue prove alla 4 e alla 5, come sempre. Poi vai alla 3c (facoltativa) o alla 4.")
    orari = any(condizioni_orarie.e_oraria(n) for n in (*tl, *ts))
    _riga_prove(s, "le fasce del profilo orario (trigger a orario)" if orari
                else "nessuna (togliere o aggiungere casistiche non aggiunge prove)")
    return scelta


# ========================================================================
# 3c · L'atlante del trigger (22/10/2026, docs/63 §6 e docs/66)
# ========================================================================

def _azzera_cella(s: Sessione) -> None:
    """
    Toglie la cella scelta (si torna alla strada di sempre) e i suoi filtri dal registro.
    25/10/2026 (docs/68 §3.3): le uscite si costruiscono con la cella dentro la
    casistica, quindi se c'era una cella si azzerano anche uscite e sistemi.
    """
    reg.remove_filters("CELLA_")
    if _strada_b(s):
        s.uscite = s.es = s.rosa_sistemi = None
        s.consigliate = s.sistema = None
    s.cella_long = s.cella_short = None
    s.entry_casistica_long = getattr(s, "entry_long", None)
    s.entry_casistica_short = getattr(s, "entry_short", None)
    for c in (getattr(s, "casistiche", None) or {}).values():
        c["cella"] = None


def _strada_b(s: Sessione) -> bool:
    """True se e' scelta una cella dell'atlante: il passo 5 misura solo quella."""
    return bool(getattr(s, "cella_long", None) or getattr(s, "cella_short", None))


# 26/10/2026 (docs/73 §A.3.3): i motivi di atlante._motivo in parole del Lab (la colonna dell'engine non cambia)
_MOTIVI_IN_CHIARO = {
    "troppo pochi casi": f"meno di {MIN_TRIGGER} occasioni",
    "non fa meglio del mercato della cella": "non batte il mercato",
    "non supera la quota di falsi positivi": "può essere fortuna (quota di falsi positivi)",
    "non positiva in una metà": "non batte il mercato in una delle due metà",
    "non paga i costi": "non paga i costi",
}


def motivo_in_chiaro(motivo: str) -> str:
    """Il motivo per cui una cella dell'atlante non passa, in parole del Lab."""
    return _MOTIVI_IN_CHIARO.get(motivo, motivo)


def _batte_il_mercato(r: pd.DataFrame) -> np.ndarray:
    """Le celle che battono il mercato: misurate, t > 0, quota di falsi positivi e due meta' (senza i costi)."""
    t = pd.to_numeric(r["t"], errors="coerce").to_numpy(dtype=float)
    return (r["misurata"].astype(bool).to_numpy() & (np.nan_to_num(t, nan=-1.0) > 0)
            & r["bh"].astype(bool).to_numpy() & r["due_meta"].astype(bool).to_numpy())


def _si_puo_scegliere(r: pd.DataFrame) -> list[str]:
    return ["sì" if p else ("sì, ma non passa" if m else f"no: meno di {MIN_TRIGGER} occasioni")
            for p, m in zip(r["passa"].astype(bool), r["misurata"].astype(bool))]


def grafico_atlante(tab: pd.DataFrame, trigger: list[str]) -> None:
    """
    La mappa dell'atlante (schermata 3c; anche nel notebook di ricerca): per ogni
    trigger, la solidita' dello scarto di ogni cella, colorata se la cella passa,
    grigia con il motivo se no.
    """
    from .atlante import nome_in_chiaro
    import matplotlib.pyplot as plt
    if not trigger:
        return
    fig, assi = plt.subplots(1, len(trigger), figsize=(6.2 * len(trigger), 5.6), squeeze=False)
    for ax, nome in zip(assi[0], trigger):
        r = tab[tab["candidato"] == nome].iloc[::-1]
        t = r["t"].fillna(0.0).to_numpy()
        colori = np.where(r["passa"], "#1f5f99", "#c8c8c8")
        y = np.arange(len(r))
        ax.barh(y, t, color=colori, height=0.7)
        ax.axvline(0, color="#555555", lw=0.8)
        # 26/10/2026 (docs/73 §A.3.3): situazioni e motivi in chiaro
        ax.set_yticks(y, [nome_in_chiaro(c) for c in r["cella"]], fontsize=9)
        for yi, mot in enumerate(r["motivo"]):
            if mot:
                ax.text(0.01, yi, motivo_in_chiaro(mot), transform=ax.get_yaxis_transform(), va="center",
                        fontsize=7.5, color="#666666")
        ax.set_title(f"{nome} · quanto batte il mercato, situazione per situazione (solidità)", loc="left",
                     fontsize=10)
        ax.set_xlabel("solidità (t)")
    plt.tight_layout()
    plt.show()


def atlante_dei_trigger(s: Sessione) -> pd.DataFrame:
    """
    Schermata 3c, facoltativa (22/10/2026, docs/66). Dopo la scelta dei
    trigger: l'atlante di engine/atlante.py su TUTTE le entry vere
    dell'in-sample, all'orizzonte H. Per ogni entry e cella (4 di volatilita'
    x trend, 4 sessioni; la basis tolta il 29/10/2026, docs/77) lo scarto
    lordo dal mercato della cella, la sua solidita', il netto dei costi e se
    passa i controlli (200 occasioni, quota di falsi positivi, due meta',
    netto > 0). Mostra la mappa dei trigger scelti e la tabella delle entry
    con almeno una cella che passa. Non sceglie niente: la cella si sceglie
    con scegli_cella.

    Ritorna la tabella completa (anche in `s.atlante`). Rifatta con le stesse
    impostazioni non conta due volte nella soglia cumulata; la cella scelta
    prima si azzera.
    """
    s._serve("ev", "2 · Esplora")
    if not (s.trigger_long or s.trigger_short):
        raise RuntimeError("Manca un passaggio: esegui prima la schermata «3b · Le tue casistiche».")
    _avviso_risalita(s, "rifare l'atlante")
    from .atlante import atlante, nome_in_chiaro
    import condizioni_orarie
    mostra = [*s.trigger_long, *s.trigger_short]
    # 23/10/2026: anche i trigger scelti fuori catalogo (es. ORA_LONG_@05:45), che entrano nel conto k;
    # quelli a orario si confrontano con il mercato della cella a qualunque ora (decisione di Mattia)
    catalogo = _trigger_candidati(1 if s.solo_long else None)
    nomi = catalogo + [m for m in mostra if m not in set(catalogo)]
    orari = [m for m in mostra if condizioni_orarie.e_oraria(m)]
    with _zitto():
        tab = atlante(s.df_is, s.H, s.pip, costi=s.costi, funding=s.funding, nomi=nomi, unita=s.unita,
                      min_eventi=MIN_TRIGGER, fuso=s.fuso, mostra=mostra, atr=s.atr,
                      **({"qualunque_ora": orari} if orari else {}))
    s.atlante = tab
    _nota_blocchi(tab, "celle")
    _azzera_cella(s)
    s.fs = s.dm = s.oos = None
    s.sopravvissuti, s.filtro = [], None
    k = int(tab.attrs["k_misurate"])
    # soglia cumulata: le celle misurate, una volta per impostazione (H e assi; le entry sono tutte)
    contata = _rd.metti_prova(s.prove, "celle", chiave_celle(s.H, tab, nomi), k)

    u, a = s.unita, _altra_unita(s)
    poche = dict(tab.attrs.get("scartate", []))
    for nome in mostra:
        r = tab[tab["candidato"] == nome]
        if r.empty:
            if nome in poche:
                _nota(f"{nome}: meno di {MIN_TRIGGER} occasioni nell'in-sample ({poche[nome]}), "
                      "l'atlante non lo misura.")
            else:
                _nota(f"{nome}: l'atlante non l'ha misurato.")
            continue
        # 26/10/2026 (docs/73 §A.3.3): situazioni in chiaro; «passa» diviso in «batte il mercato» e «paga i costi»
        confronto = ("In più del mercato della situazione, a qualunque ora" if nome in orari
                     else "In più del mercato della situazione")
        misurata = r["misurata"].astype(bool)
        vista = pd.DataFrame({
            "Situazione": [nome_in_chiaro(c) for c in r["cella"]],
            "Nome da scrivere alla 3d": r["cella"],
            "Occasioni": r["eventi"].astype(int),
            f"{confronto} ({u}), prima dei costi": r[f"scarto_{u}"],
            "Solidità": r["t"],
            f"Netto dei costi per occasione ({u})": r[f"netto_{u}"],
            f"{confronto} ({a}), prima dei costi": r[f"scarto_{a}"] if f"scarto_{a}" in r else np.nan,
            f"Netto dei costi per occasione ({a})": r[f"netto_{a}"] if f"netto_{a}" in r else np.nan,
            "Batte il mercato": [_si_no(v) for v in _batte_il_mercato(r)],
            "Paga i costi": [(_si_no(n > 0) if m else "—") for n, m in zip(r[f"netto_{u}"], misurata)],
            "Si può scegliere alla 3d": _si_puo_scegliere(r),
            "Perché non passa": [motivo_in_chiaro(m) for m in r["motivo"]],
        })
        s.tabelle[f"atlante_{nome}"] = vista
        _mostra((f"Dove funziona {nome} (in-sample, {s.H} barre)", vista), decimali={"Solidità": 2})
        if nome in orari:
            _nota(f"{nome} è un segnale a orario: scatta tutti i giorni alla stessa ora, quindi coincide con "
                  "il mercato della sua fascia e lo si confronta con il mercato della situazione a qualunque ora. "
                  "Fra le sessioni ha occasioni in una situazione sola; le altre restano grigie e non si possono "
                  "scegliere.")
    grafico_atlante(tab, [m for m in mostra if (tab["candidato"] == m).any()])

    passano = tab[tab["passa"]]
    if passano.empty:
        _nota(f"Nessuna situazione passa tutti i controlli, per nessuno dei {tab['candidato'].nunique()} segnali "
              f"misurati ({k} situazioni misurate).")
        riassunto = pd.DataFrame(columns=["Segnale", "Lato", "Situazioni che passano", "Solidità più alta"])
    else:
        g = passano.groupby("candidato", sort=False)
        riassunto = pd.DataFrame({
            "Segnale": list(g.groups),
            "Lato": ["long" if g.get_group(n)["direction"].iat[0] == 1 else "short" for n in g.groups],
            "Situazioni che passano": [", ".join(nome_in_chiaro(c) for c in g.get_group(n)["cella"])
                                       for n in g.groups],
            "Solidità più alta": [float(g.get_group(n)["t"].max()) for n in g.groups],
        }).sort_values("Solidità più alta", ascending=False).reset_index(drop=True)
        _mostra(("I segnali con almeno una situazione che passa", riassunto), decimali={"Solidità più alta": 2})
    s.tabelle["atlante"] = riassunto
    _riquadro(
        "Per ogni segnale, una situazione alla volta: volatilità alta o bassa con trend a favore o contro (4), la "
        "sessione in cui si apre il trade (4: Asia, che comprende il fine settimana, Europa, Londra + New York, "
        "America)"
        + f". In ogni situazione: quanto il segnale batte il mercato della stessa situazione e della stessa ora "
        f"({u}, prima dei costi) e quanto resta dopo commissione, spread" + (" e funding" if s.funding is not None
                                                                            else "") + ".",
        f"«Batte il mercato» vuol dire che fa meglio del mercato della situazione anche contando tutte le {k} "
        "situazioni misurate, in tutte e due le metà dell'in-sample. «Paga i costi» vuol dire che resta positivo "
        f"dopo i costi" + (" e si giudica in bp, il metro unico: in pips il segno può essere diverso, perché i pips "
                           "pesano di più i trade fatti a prezzi alti" if u == "bp" else "")
        + f". Una situazione passa con tutte e due e almeno {MIN_TRIGGER} occasioni. È una mappa: dice "
        "dove il segnale sembra funzionare, non che funziona.",
        f"Se vuoi, scegli una situazione alla 3d: va bene qualunque situazione con almeno {MIN_TRIGGER} occasioni, "
        "anche una che non passa. Il segnale scatterà solo lì, e al passo 5 l'asticella terrà conto di tutte le "
        f"{k} situazioni guardate (solidità {_fmt(soglia_rumore(max(k, 1), ALPHA))}). Altrimenti vai alla 4: la "
        "strada di sempre, con tutti i filtri al passo 5.")
    _riga_prove(s, f"{k} situazioni misurate" if contata else
                f"nessuna in più ({k} situazioni misurate, già contate in un atlante con la basis, docs/77)")
    return tab


AVVISO_CELLA_NON_PASSA = ("Nell'in-sample questa situazione non batte il mercato, o non paga i costi: "
                          "la scegli sapendolo.")


def controlla_cella(tab: pd.DataFrame, trigger, cella: str, lato: str) -> dict:
    """
    La regola della 3d (26/10/2026, docs/73 §A.3.5, decisione 3 di docs/72 §A.3), comune al Lab e al
    notebook di ricerca: su un lato si puo' scegliere una cella che l'atlante ha MISURATO (almeno
    min_eventi occasioni) per almeno uno dei trigger del lato, anche se non passa. Sotto le occasioni
    minime per tutti i trigger si ferma e dice perche'. Nessuna prova in piu': l'atlante conta gia'
    tutte le celle che misura.

    Ritorna {"passa": True se passa per almeno un trigger del lato, "avviso": il testo da mostrare se
    non passa (None se passa), "motivi": {trigger: motivo in chiaro}}.
    """
    from .atlante import asse_di, celle_misurate, nome_in_chiaro
    asse_di(cella)                                    # nome sconosciuto: si ferma con l'elenco
    trigger = [trigger] if isinstance(trigger, str) else list(trigger)
    righe = tab[tab["candidato"].isin(trigger) & (tab["cella"] == cella)]
    if cella not in celle_misurate(tab, trigger):
        minimo = int(tab.attrs.get("min_eventi", MIN_TRIGGER))
        occasioni = ", ".join(f"{n} per {c}" for c, n in zip(righe["candidato"], righe["eventi"].astype(int))) \
            or "nessuna"
        misurate = ", ".join(f"{c} ({nome_in_chiaro(c)})" for c in celle_misurate(tab, trigger)) or "nessuna"
        raise ValueError(f"La situazione {cella} ({lato}) ha queste occasioni nell'in-sample: {occasioni}. Sotto "
                         f"le {minimo} l'atlante non la misura, quindi non si può scegliere. Situazioni misurate "
                         f"su questo lato: {misurate}.")
    misurate = righe[righe["misurata"].astype(bool)]
    passa = bool(misurate["passa"].astype(bool).any())
    motivi = {c: motivo_in_chiaro(m) for c, m in zip(misurate["candidato"], misurate["motivo"])}
    avviso = None if passa else (AVVISO_CELLA_NON_PASSA + " ("
                                 + "; ".join(f"{c}: {m}" for c, m in motivi.items()) + ")")
    return {"passa": passa, "avviso": avviso, "motivi": motivi}


def scegli_cella(s: Sessione, long: str | None = None, short: str | None = None) -> None:
    """
    Schermata 3d, facoltativa (22/10/2026, docs/66 §4). La cella dell'atlante
    in cui opera ogni lato: al massimo una per lato, solo fra quelle che
    passano per almeno uno dei trigger scelti su quel lato, nessuna cella di
    default (decisioni di Mattia del 22/10/2026). Le celle diventano filtri
    su richiesta (atlante.registra_filtri_cella) e il passo 5 misura solo
    quelli, con l'asticella delle celle dell'atlante (strada B).

    25/10/2026 (docs/68 §3.3, decisione 2 di Mattia): la cella entra nella
    casistica. L'entry della casistica diventa «TRIGGER+CELLA_…» (vera dove
    sono veri il trigger e la cella, come congela_filtro), e le uscite
    (schermata 4) e la rosa dei sistemi (4b) lavorano su quella. Il passo 5
    resta la strada B: trigger senza cella contro trigger con la cella, con le
    uscite della casistica.

    26/10/2026 (docs/73 §A.3.5): si puo' scegliere qualunque cella MISURATA
    dall'atlante (almeno 200 occasioni per un trigger del lato), anche se non
    passa: in quel caso compare l'avviso arancione. Nessuna prova in piu'.

    Senza celle (scegli_cella(s)) si torna alla strada di sempre.
    """
    s._serve("atlante", "3c · Dove funziona il segnale")
    prima = (getattr(s, "cella_long", None), getattr(s, "cella_short", None))
    from .atlante import asse_di, nome_filtro_cella, nome_in_chiaro, registra_filtri_cella

    def pulisci(x):
        if x is None:
            return None
        if not isinstance(x, str) or "," in x:
            raise ValueError("Una cella sola per lato: scrivi un nome, per esempio long='EUROPA'.")
        x = x.strip().replace(" (e fine settimana)", "")
        return x or None

    cl, cs = pulisci(long), pulisci(short)
    if getattr(s, "storia", None) is not None and s.storia.oos_visto and prima != (cl, cs):
        _avviso_risalita(s, "cambiare la cella")
        _rd.annota_risalita(s.storia, "cella", da=prima, a=(cl, cs))
        _salva_studio(s.storia)       # 25/10/2026 (docs/70)
    s.fs = s.dm = s.oos = None
    s.sopravvissuti, s.filtro, s.filtri_scelti = [], None, []
    s.trades_is = s.trades_oos = s.mm = None
    if not cl and not cs:
        _azzera_cella(s)
        _nota("Nessuna situazione scelta: al passo 5 si provano tutti i filtri, come sempre.")
        _riga_prove(s, "nessuna")
        return
    righe, avvisi = [], []
    for lato, cella, trigger in (("long", cl, s.trigger_long), ("short", cs, s.trigger_short)):
        if not cella:
            continue
        asse_di(cella)
        if lato == "short" and s.solo_long:
            raise ValueError(f"{s.symbol} è spot: lo short non esiste, la situazione short non serve.")
        if not trigger:
            raise ValueError(f"Il lato {lato} non ha trigger (schermata 3): la situazione {cella} non ha a cosa "
                             "applicarsi.")
        esito = controlla_cella(s.atlante, trigger, cella, lato)
        if esito["avviso"]:
            avvisi.append(f"{lato.upper()}, {nome_in_chiaro(cella)}: {esito['avviso']}")
        r = s.atlante[s.atlante["candidato"].isin(list(trigger)) & (s.atlante["cella"] == cella)
                      & s.atlante["misurata"].astype(bool)]
        migliore = r.sort_values("t", ascending=False).iloc[0]
        righe.append({"Lato": lato.upper(), "Segnale": " oppure ".join(trigger), "Situazione": nome_in_chiaro(cella),
                      "Occasioni": int(migliore["eventi"]), "Solidità": float(migliore["t"]),
                      f"Netto dei costi per occasione ({s.unita})": float(migliore[f"netto_{s.unita}"]),
                      "Batte il mercato": _si_no(_batte_il_mercato(r).any()),
                      "Paga i costi": _si_no((r[f"netto_{s.unita}"] > 0).any())})
    _azzera_cella(s)                       # le uscite di prima erano costruite senza questa cella
    s.uscite = s.es = s.rosa_sistemi = None
    s.consigliate = s.sistema = None
    with _zitto():
        registra_filtri_cella(s.df, cl, cs)
    s.cella_long, s.cella_short = cl, cs
    # 25/10/2026 (docs/68 §3.3): la cella dentro la casistica, un'entry derivata per lato
    s.entry_casistica_long = _entry_con_cella(s.entry_long, cl, "_L")
    s.entry_casistica_short = _entry_con_cella(s.entry_short, cs, "_S")
    for lato, cella in (("long", cl), ("short", cs)):
        if lato in (s.casistiche or {}):
            s.casistiche[lato]["cella"] = cella
    tabella = pd.DataFrame(righe)
    s.tabelle["cella"] = tabella
    for testo in avvisi:
        _avviso(testo)
    _mostra(("La situazione scelta", tabella), decimali={"Solidità": 2})
    _nota(f"La situazione entra nella casistica: le uscite (schermata 4) si costruiscono sul segnale dentro la "
          f"situazione ({', '.join(e for e in (s.entry_casistica_long, s.entry_casistica_short) if e and '+' in e)}). "
          f"Al passo 5 si prova solo la situazione: la riga si chiamerà {nome_filtro_cella(cl, cs)}, ed è il nome "
          "da scrivere nella scheda (schermata 6). Nessuna prova in più: l'atlante ha già contato tutte le "
          "situazioni che ha misurato.")
    _riga_prove(s, "nessuna (le situazioni sono già contate alla 3c)")


def entry_con_cella(entry: str | None, cella: str | None, suffisso: str) -> str | None:
    """Come _entry_con_cella, per il notebook di ricerca (suffisso "_L" per il long, "_S" per lo short)."""
    return _entry_con_cella(entry, cella, suffisso)


def _entry_con_cella(entry: str | None, cella: str | None, suffisso: str) -> str | None:
    """
    L'entry della casistica con la cella dentro (25/10/2026, docs/68 §3.3):
    «ENTRY+CELLA_<C>_L», vera dove sono veri l'entry e il filtro della cella,
    registrata come le entry derivate di confidenza.congela_filtro. Senza
    cella (o senza entry) l'entry resta quella di prima.
    """
    if entry is None or not cella:
        return entry
    from .atlante import PREFISSO_FILTRI
    filtro = f"{PREFISSO_FILTRI}{cella}{suffisso}"
    nome = f"{entry}+{filtro}"
    if nome not in reg.list_entries():
        def derivata(d, _e=entry, _f=filtro):
            return (reg.get_entry(_e)(d).astype(bool)
                    & pd.Series(reg.get_filter(_f)(d).astype(bool).to_numpy(), index=d.index))
        reg.register_entry(nome, reg.get_entry_direction(entry))(derivata)
    return nome


# ========================================================================
# 4 · Imposta le uscite
# ========================================================================

def _cache_maschere(s: Sessione, quale: str) -> dict:
    """La cache delle maschere dei filtri di un df della sessione (21/10/2026, E4):
    "is", "oos" o "due_meta" (le due meta' dell'in-sample). Vedi
    run_filter_search_bt: se il df cambia, la cache si svuota da sola."""
    if not hasattr(s, "maschere"):               # sessioni finte dei test
        s.maschere = {}
    return s.maschere.setdefault(quale, {})


def _kw_motore(s: Sessione) -> dict:
    """I parametri comuni a ogni backtest della sessione (uscite + costi + unita' che decide)."""
    u = s.uscite
    return dict(n_barre=u["n_barre"], n_barre_long=u["n_barre_long"],
                n_barre_short=u["n_barre_short"], perc_sl=u["perc_sl"],
                perc_tp=u["perc_tp"], finestra=FINESTRA, lag=LAG,
                inverti_su_opposto=True, unita=s.unita,
                motore=getattr(s, "motore", None), **s.costi)


def _altra_unita(s: Sessione) -> str:
    """L'unita' mostrata accanto a quella che decide (20/10/2026, U2)."""
    return "bp" if s.unita == "pips" else "pips"


def _in_unita(s: Sessione, etichetta: str, valore, valore_pips=None) -> dict:
    """
    Una colonna nell'unita' che decide, piu' i pips accanto quando decide il
    bp (20/10/2026, U2): «Guadagno ... (bp)» e «Guadagno ... (pips)».
    """
    voci = {f"{etichetta} ({s.unita})": valore}
    if s.unita != "pips":
        voci[f"{etichetta} (pips)"] = valore_pips
    return voci


def _frase_unita(s: Sessione, colonne: str = "Le due colonne") -> str:
    """La frase del riquadro che dice quale unita' decide (docs/63 §4.4)."""
    if s.unita == "pips":
        return (f"{colonne} in bp (punti base del prezzo, 1 bp = 0,01%) sono solo da leggere, decidono ancora "
                "i pips: i bp pesano allo stesso modo un trade del 2020 e uno del 2025. ")
    return ("Qui decide il bp (punti base del prezzo d'ingresso, 1 bp = 0,01%): pesa allo stesso modo un trade del "
            "2020 e uno del 2025, anche se il prezzo nel frattempo è cambiato di molto. I pips restano accanto: "
            "sono l'unità del conto e del money management. ")


def _nome_sistema(riga) -> str:
    ha_long = isinstance(riga["entry_long"], str)
    ha_short = isinstance(riga["entry_short"], str)
    if ha_long and ha_short:
        return "Long + Short"
    return "Solo long" if ha_long else "Solo short"


def _regola_oraria(s: Sessione, regola):
    """Registra le uscite orarie (19/10/2026) e restituisce l'etichetta da passare al motore."""
    import condizioni_orarie
    if regola is None or str(regola).strip().lower() in ("", "nessuna", "none"):
        return None
    regola = str(regola).strip()
    if regola == condizioni_orarie.INVERSIONE:
        with _zitto():
            u = getattr(s, "unita", "pips")          # sessioni finte dei test: pips, come prima
            # 25/10/2026 (docs/68 §6): un solo calcolo, il profilo della schermata 2a se c'e' (stessi H,
            # fuso e unita': stessi numeri); altrimenti calcolato qui, come prima
            p = getattr(s, "profilo", None)
            stesso = (p is not None and p.attrs.get("H") == s.H and p.attrs.get("fuso") == s.fuso
                      and p.attrs.get("unita", "pips") == u)
            extra = {"profilo": p} if stesso else {}
            if u == "pips":
                return condizioni_orarie.registra_inversione_trend(s.df_is, s.H, s.pip, **extra)
            # 23/10/2026: sulle crypto lo stesso profilo in bp del grafico 2b
            return condizioni_orarie.registra_inversione_trend(s.df_is, s.H, s.pip, unita=u, **extra)
    if regola.startswith("X_ORA_@") or regola[:1].isdigit():
        orario, fuso = condizioni_orarie.orario_uscita(regola)    # "_UTC" in fondo: ora UTC fissa
        condizioni_orarie.codice_orario(orario, s.df_is.index, s.fuso if fuso != "UTC" else "UTC")   # orario valido qui
        return condizioni_orarie.registra_uscita_oraria(regola)
    coppie = {p for p, _, _ in reg.list_exit_pairs()}
    if regola not in coppie:
        raise ValueError(f"Regola di uscita '{regola}' sconosciuta. Usa nessuna, X_ORA_@HH:MM, "
                         f"X_INVERSIONE_TREND o una di: {sorted(coppie)}.")
    return regola


def percentile_uscita(nome: str, v):
    """
    Uno stop o un target in percentile, controllato e nella forma del conto (28/10/2026, docs/76: comune al
    Lab e al notebook di ricerca). 23/10/2026: un numero (i due lati) o una coppia (long, short), come le barre.
    """
    coppia = isinstance(v, (tuple, list))
    valori = per_lato(v) if coppia else (v,)
    for x in valori:
        if x is None or not (0 <= float(x) < 100):
            raise ValueError(f"{nome} è un percentile: da 0 (spento) a 99.")
    if coppia and float(valori[0]) != float(valori[1]):
        return (float(valori[0]), float(valori[1]))
    return float(valori[0])


def impostazioni_uscite(barre_long: int, barre_short: int, sl, tp, regola) -> dict:
    """Le impostazioni delle uscite nella forma di s.uscite del Lab (28/10/2026, docs/76: per le chiavi del conto)."""
    return dict(n_barre=barre_long, n_barre_long=barre_long, n_barre_short=barre_short,
                perc_sl=percentile_uscita("sl", sl), perc_tp=percentile_uscita("tp", tp), regola=regola)


def imposta_uscite(s: Sessione, barre_long: int | None = None,
                   barre_short: int | None = None, sl: float = 90.0,
                   tp: float = 0.0, regola_uscita: str | None = None) -> pd.DataFrame:
    """
    Schermata 4. Fissa le uscite e prova il sistema base sull'in-sample
    (`run_exit_search_bt`), confrontando solo long, solo short ed entrambi.

    barre_long / barre_short   dopo quante barre il trade si chiude comunque
                               (None = l'orizzonte H)
    sl / tp                    percentile dello stop e del target adattivi
                               (0 = spento); un numero vale per i due lati,
                               due valori (long, short) li separano (23/10/2026)
    regola_uscita              25/10/2026 (docs/68 §5): "consigliata" = la regola
                               consigliata per ogni lato (X_ORA_@ = ingresso + H
                               barre se le casistiche del lato sono un trigger a
                               orario, altrimenti nessuna); anche per lato,
                               ("consigliata", "nessuna").
                               None / "nessuna" = solo tempo, stop e target.
                               Dal 19/10/2026: "X_ORA_@HH:MM" chiude il trade
                               alle HH:MM ("X_ORA_@HH:MM_UTC": all'ora UTC
                               fissa, per E38 ed E39); "X_INVERSIONE_TREND" chiude quando
                               arriva un'ora che il profilo orario (congelato
                               sull'in-sample) segna colorata contro il trade.
                               Oppure l'etichetta di un'altra coppia del
                               registro (`engine.registry.list_exit_pairs`).
                               23/10/2026: anche due regole (long, short), una
                               per lato ("nessuna" = quel lato senza regola).

    Le USCITE CONSIGLIATE (25/10/2026, docs/68 §5, decisioni di Mattia): barre
    = H (l'orizzonte dichiarato alla schermata 1), stop al 90° percentile,
    target spento, regola "consigliata". Sono i valori predefiniti: non
    costano prove in piu' delle altre impostazioni (ogni impostazione conta i
    sistemi che prova). Accanto, il picco della curva dello scarto della
    casistica, SOLO DA LEGGERE. Con una cella (3d) le uscite si costruiscono
    sul trigger dentro la cella.

    Ritorna la tabella del confronto.
    """
    if s.entry_long is None and s.entry_short is None:
        raise RuntimeError("Manca un passaggio: esegui prima la schermata «3b · Le tue casistiche».")
    s.consigliate = _uscite_consigliate(s)

    def consigliata(r, lato):
        if isinstance(r, str) and r.strip().lower() == "consigliata":
            c = s.consigliate.get(lato)
            return (c["regola"] if c else None) or "nessuna"
        return r
    if isinstance(regola_uscita, (tuple, list)):
        regola_uscita = tuple(consigliata(r, lato) for r, lato in zip(per_lato(regola_uscita), ("long", "short")))
    elif isinstance(regola_uscita, str) and regola_uscita.strip().lower() == "consigliata":
        rl, rs = consigliata(regola_uscita, "long"), consigliata(regola_uscita, "short")
        # un lato senza casistica non opera: prende la regola dell'altro (una regola sola, come prima)
        if "short" not in s.consigliate:
            rs = rl
        if "long" not in s.consigliate:
            rl = rs
        regola_uscita = rl if rl == rs else (rl, rs)
    bl = s.H if barre_long is None else int(barre_long)
    bs = s.H if barre_short is None else int(barre_short)
    barre_per_lato(bl, bl, bs)                     # controllo dei valori

    sl, tp = percentile_uscita("sl", sl), percentile_uscita("tp", tp)
    if isinstance(regola_uscita, (tuple, list)):
        rl, rs = per_lato(regola_uscita)
        regola_uscita = reg.coppia_per_lato(_regola_oraria(s, rl), _regola_oraria(s, rs))
    else:
        regola_uscita = _regola_oraria(s, regola_uscita)
    s.uscite = impostazioni_uscite(bl, bs, sl, tp, regola_uscita)
    s.fs = s.dm = s.oos = s.rosa_sistemi = None
    s.sistema = None
    s.sopravvissuti, s.filtro = [], None
    chiave = _chiave_uscite(s)
    storia = getattr(s, "storia", None)
    if storia is not None and storia.oos_visto and storia.diario[-1].get("uscite") != chiave:
        _avviso_risalita(s, "cambiare le uscite")
        _rd.annota_risalita(storia, "uscite", a=chiave)
        _salva_studio(storia)         # 25/10/2026 (docs/70)
    _mostra_consigliate(s, bl, bs, sl, tp, regola_uscita)

    el, es_ = _entry_lato(s, 1), _entry_lato(s, -1)      # con la cella dentro, se c'e' (docs/68 §3.3)
    entrambi = el is not None and es_ is not None
    with _zitto():
        s.es = run_exit_search_bt(
            s.df_is,
            entry_cols_long=[el, None] if entrambi else [el],
            entry_cols_short=[es_, None] if entrambi else [es_],
            exit_rule_pairs=regola_uscita, verbose=False, **_kw_motore(s))
    # 22/10/2026: soglia cumulata, i sistemi provati con queste impostazioni
    # (25/10/2026: anche la cella, perche' le uscite si costruiscono con la cella dentro)
    nuova = chiave not in s.prove["uscite"]
    _rd.metti_prova(s.prove, "uscite", chiave, len(s.es.risultati))

    r = s.es.risultati.copy()
    r["Sistema"] = r.apply(_nome_sistema, axis=1)
    ordine = {"Long + Short": 0, "Solo long": 1, "Solo short": 2}
    r = r.sort_values("Sistema", key=lambda c: c.map(ordine)).reset_index(drop=True)
    tabella = pd.DataFrame({
        "Sistema": r["Sistema"],
        "Trade": r["trades"].astype(int),
        **_in_unita(s, "Guadagno medio netto per trade", r["avg_trade_netto"], r.get("avg_trade_netto_pips")),
        "Trade vincenti (%)": r["win_rate_pct"],
        "Solidità": r["t_stat"],
        "Durata media (barre)": r["durata_media"],
    })
    s.tabelle["uscite"] = tabella

    def soglia(p):
        return "spento" if not p else f"{_fmt(p, 0)}° percentile"
    if isinstance(sl, tuple) or isinstance(tp, tuple) or (regola_uscita and " | " in regola_uscita):
        # 23/10/2026: uscite diverse sui due lati
        (sl_l, sl_s), (tp_l, tp_s) = per_lato(sl), per_lato(tp)
        rl, rs = (regola_uscita.split(" | ") if regola_uscita and " | " in regola_uscita
                  else (regola_uscita, regola_uscita))

        def regola_txt(r):
            return f"regola {r}" if r and r != reg.NESSUNA else "nessuna regola"
        # 28/10/2026 (docs/76, B2): solo i lati accesi
        lati = ([f"long: dopo {bl} barre, stop {soglia(sl_l)}, target {soglia(tp_l)}, {regola_txt(rl)}"] if el else [])             + ([f"short: dopo {bs} barre, stop {soglia(sl_s)}, target {soglia(tp_s)}, {regola_txt(rs)}"] if es_ else [])
        _nota("Uscite per lato · " + " · ".join(lati) + " · chiusura e inversione sul segnale opposto.")
    else:
        tempo = ", ".join(([f"long dopo {bl} barre"] if el else []) + ([f"short dopo {bs} barre"] if es_ else []))
        _nota(f"Uscita a tempo: {tempo} · "
              f"stop {soglia(sl)} · target {soglia(tp)} · chiusura e inversione sul segnale opposto"
              + (f" · regola di uscita {regola_uscita}." if regola_uscita else "."))
    riga = _durate_orarie(s, bl, bs, "barre impostate")
    if riga:
        _nota(riga)
    # 28/10/2026 (docs/75 §7.7, D3): sempre visibile
    _nota("X_INVERSIONE_TREND usa le ore colorate del profilo della 2a: il long si chiude all'arrivo di un'ora "
          "rossa, lo short all'arrivo di un'ora verde. Se cambiano le ore colorate della 2a, cambiano anche "
          "queste chiusure.")
    if regola_uscita and "X_INVERSIONE_TREND" in regola_uscita.split(" | "):
        import condizioni_orarie
        contro = condizioni_orarie.fasce_contro()
        _nota("X_INVERSIONE_TREND (profilo congelato sull'in-sample): il long si chiude all'arrivo delle ore "
              + (", ".join(contro["long"]) if contro["long"] else "— nessuna ora rossa: per il long non scatta mai")
              + "; lo short all'arrivo delle ore "
              + (", ".join(contro["short"]) if contro["short"] else "— nessuna ora verde: per lo short non scatta mai")
              + ".")
    _mostra(("Il sistema base (in-sample, al netto dei costi)", tabella),
            decimali={"Durata media (barre)": 1})

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 4.6))
    for _, riga in r.iterrows():
        tr = s.es.trades(riga["combinazione"])
        if len(tr) == 0:
            continue
        _, netti = netti_in_unita(tr, s.pip, s.costi["commission"], s.unita)
        curva = pd.Series(netti.to_numpy(), index=pd.DatetimeIndex(tr["ExitTime"])).sort_index().cumsum()
        ax.plot(curva.index, curva.to_numpy(), lw=2.0 if riga["Sistema"] == "Long + Short" else 1.2,
                label=riga["Sistema"])
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel(f"{s.unita} netti accumulati")
    ax.set_title(f"Sistema base: somma dei {s.unita} netti, trade dopo trade (in-sample)")
    ax.grid(alpha=.3)
    ax.legend()
    plt.tight_layout()
    plt.show()

    _riquadro(
        "Il sistema «nudo»: solo i tuoi trigger e le tue uscite, senza filtri. Lo stop non è un numero fisso "
        "di pips: per ognuna delle ultime 500 barre lo strumento misura di quanto il prezzo si è mosso contro "
        "nelle barre successive, e mette lo stop alla distanza che è stata superata solo poche volte "
        "(90° percentile = 1 volta su 10). Mercato agitato, stop più largo; mercato calmo, stop più stretto.",
        "Il guadagno medio netto per trade deve restare sopra zero dopo i costi, e la curva deve salire con "
        "una certa regolarità, non per un solo periodo fortunato."
        # 28/10/2026 (docs/76, B3): solo se le righe sono piu' di una
        + (" Confronta le tre righe: a volte un lato da solo rende meglio dei due insieme." if len(r) > 1 else ""),
        "Se vuoi, cambia barre o percentili e riesegui la cella: ogni impostazione nuova conta come le altre "
        "(la riga delle prove qui sotto lo dice subito). Poi vai alla 4b per scegliere il sistema da portare al "
        "passo 5.")
    n = len(s.es.risultati)
    if not nuova:
        qui = "nessuna (queste uscite le avevi già provate)"
    elif _sono_consigliate(s, bl, bs, sl, tp, regola_uscita):
        qui = f"{n} {'sistema' if n == 1 else 'sistemi'} con le uscite consigliate"
    else:
        qui = f"{n} {'sistema' if n == 1 else 'sistemi'} (una modifica alle uscite consigliate)"
    _riga_prove(s, qui)
    return tabella


def _entry_lato(s: Sessione, direzione: int) -> str | None:
    """L'entry della casistica di un lato: con la cella dentro se c'e' (docs/68 §3.3), altrimenti il trigger."""
    if direzione == 1:
        return getattr(s, "entry_casistica_long", None) or s.entry_long
    return getattr(s, "entry_casistica_short", None) or s.entry_short


def _uscite_consigliate(s: Sessione) -> dict:
    """
    Le uscite consigliate per lato (25/10/2026, docs/68 §5): barre = H, stop
    al 90° percentile, target spento; con un trigger a orario (tutte le
    casistiche del lato alla stessa ora) la regola X_ORA_@ = ora d'ingresso +
    H barre, che da' gli stessi trade della scadenza in barre (§5.2), se H e'
    meno di un giorno. Accanto, il picco della curva dello scarto della
    casistica (con la cella se c'e'), solo da leggere.
    """
    casistiche = {lato: (_entry_lato(s, d), trigger)
                  for lato, d, trigger in (("long", 1, s.trigger_long), ("short", -1, s.trigger_short))}
    return uscite_consigliate(s.df_is, s.H, s.pip, getattr(s, "fuso", None) or fuso_profilo(getattr(s, "symbol", "")),
                              getattr(s, "unita", "pips"), getattr(s, "timeframe", "M15"), casistiche,
                              atr=getattr(s, "atr", None))


def uscite_consigliate(df_is: pd.DataFrame, H: int, pip: float, fuso: str, unita: str, timeframe: str,
                       casistiche: dict, atr=None) -> dict:
    """
    Le uscite consigliate per lato (25/10/2026, docs/68 §5; anche nel notebook
    di ricerca). `casistiche` = {"long": (entry, trigger), "short": (...)}: l'entry
    da passare al motore (con la cella dentro, se c'e') e i trigger in OR.
    Barre = H, stop al 90° percentile, target spento; con un trigger a orario
    (tutti i trigger del lato alla stessa ora) la regola X_ORA_@ = ora
    d'ingresso + H barre, che da' gli stessi trade della scadenza in barre
    (§5.2), se H e' meno di un giorno. Il picco della curva dello scarto e'
    solo da leggere.
    """
    import condizioni_orarie
    out = {}
    for lato, (entry, trigger) in casistiche.items():
        if entry is None or not trigger:
            continue
        orari = [n for n in trigger if condizioni_orarie.e_oraria(n)]
        tutti_orari = len(orari) == len(trigger)
        regola = None
        if tutti_orari and len({n.split("@")[1] for n in orari}) == 1:
            minuti = int(H) * _minuti_barra(timeframe)
            if minuti < 1440:
                hh, mm = (int(x) for x in orari[0].split("@")[1].split(":"))
                t = (hh * 60 + mm + minuti) % 1440
                regola = f"X_ORA_@{t // 60:02d}:{t % 60:02d}"
        curva = curva_scarto_orario(df_is, [entry], H, pip, fuso=fuso, unita=unita,
                                    qualunque_ora=[entry] if tutti_orari else (), atr=atr)
        picco = picco_curva(curva[entry] if entry in curva else pd.Series(dtype=float), H)
        out[lato] = dict(barre=int(H), sl=90.0, tp=0.0, regola=regola, picco=picco, entry=entry)
    return out


def tabella_uscite_consigliate(consigliate: dict, unita: str) -> pd.DataFrame:
    """La tabella delle uscite consigliate, per il notebook di ricerca (il Lab ha _mostra_consigliate)."""
    return pd.DataFrame([{
        "lato": lato, "entry": x["entry"], "barre": x["barre"], "stop (percentile)": x["sl"],
        "target (percentile)": x["tp"], "regola": x["regola"] or "nessuna",
        "picco: barra (solo da leggere)": x["picco"]["barra"], f"picco ({unita})": x["picco"]["valore"],
        "nota": x["picco"]["nota"]} for lato, x in consigliate.items()])


def entry_del_sistema(sistema, entry_long, entry_short) -> tuple:
    """
    Le entry del passo 5 secondo il sistema scelto (25/10/2026, docs/68 §7; anche
    nel notebook di ricerca): «Long + Short» (o None), «Solo long», «Solo short».
    """
    sistema = (str(sistema).strip() if sistema else "") or "Long + Short"
    if sistema not in SISTEMI:
        raise ValueError(f"Sistema «{sistema}»: usa uno di {', '.join(SISTEMI)}.")
    el = entry_long if sistema in ("Long + Short", "Solo long") else None
    es_ = entry_short if sistema in ("Long + Short", "Solo short") else None
    if el is None and es_ is None:
        raise ValueError(f"Il sistema «{sistema}» non ha nessun lato acceso con queste casistiche.")
    return el, es_


def registro_orizzonte(symbol: str, timeframe: str, df_is: pd.DataFrame, H: int, dati=None):
    """
    Il registro del dataset per il notebook di ricerca (25/10/2026, docs/68
    §9.1): la stessa cosa che fa prepara nel Lab. Da chiamare nella cella
    dove si sceglie H; dice se H e' cambiato sullo stesso dataset (una
    risalita: si conta). Ritorna la storia (h_provati, diario, risalite).

    dati   25/10/2026 (docs/70 §12.4): quello che ritorna apri_dati. Con il
           confine dello studio il registro e' lo stesso del Lab, nei giornali
           dello studio; None = in memoria, come prima.
    """
    precedente = _ULTIMO_DATASET.get("chiave")
    vuote = lambda: {"trigger": 0, "uscite": {}, "filtri": {}, "combinazioni": {}}  # noqa: E731
    info = None
    if dati is not None and getattr(dati, "ingresso", None) is not None:
        storia, esito, info = _storia_dello_studio(dati, H, vuote)
    else:
        storia, esito = _rd.apri(symbol, timeframe, df_is.index[-1], H, nuove_prove=vuote)
    _ULTIMO_DATASET["chiave"] = storia.chiave
    _nota_dataset(SimpleNamespace(storia=storia), esito, precedente)
    _note_studio(storia, info)
    return storia


def mostra_oos_fresco(info: dict | None, oos, df_oos: pd.DataFrame, atr=None) -> pd.DataFrame | None:
    """
    L'out-of-sample «fresco» per il notebook di ricerca (25/10/2026, docs/70 §13):
    `info` e' quello di oos_fresco, calcolato PRIMA di segna_oos; `oos` il
    risultato di run_filter_search_bt sull'out-of-sample. Scrive la riga del
    tratto mai guardato e ritorna una tabella, una riga per filtro (baseline
    compresa): trade, guadagno medio netto e solidita' su tutto l'out-of-sample
    e sul solo tratto mai guardato. None se non c'e' un tratto da mostrare.
    """
    if info is None:
        return None
    unita = getattr(oos, "unita", "pips")
    righe, n_base = [], 0
    for etichetta in oos.risultati["filtro"]:
        nome = None if etichetta == BASELINE else etichetta
        tutti = oos.trades(nome)
        fr = trade_freschi(info, tutti, df_oos)
        if nome is None:
            n_base = len(fr)
        k_t = scheda_strategia(tutti, oos.pip_size, oos.commission or 0.0, montecarlo=False, verbose=False,
                               atr=atr, unita=unita) if len(tutti) else {}
        k_f = scheda_strategia(fr, oos.pip_size, oos.commission or 0.0, montecarlo=False, verbose=False,
                               atr=atr, unita=unita) if len(fr) else {}
        righe.append({"filtro": etichetta, "trade": len(tutti), "trade mai guardati": len(fr),
                      f"guadagno medio ({unita})": k_t.get(f"ev_{unita}", np.nan),
                      f"guadagno medio mai guardato ({unita})": k_f.get(f"ev_{unita}", np.nan),
                      "solidità": k_t.get("t_stat", np.nan), "solidità mai guardato": k_f.get("t_stat", np.nan)})
    _nota(_frase_fresco(info, n_base, int(getattr(oos, "min_trades", 0) or 0)))
    return pd.DataFrame(righe) if len(info["barre"]) else None


def segna_oos(storia, **scelte) -> int:
    """
    Il diario dell'out-of-sample per il notebook di ricerca (25/10/2026, docs/68
    §9): scrive un'apertura con le scelte di quel momento e, dalla seconda,
    lo dice. Ritorna quante aperture ci sono.
    """
    fino = scelte.pop("oos_fino_al", None)       # 25/10/2026 (docs/70 §3.2): per il reset dello studio
    n = _rd.annota_oos(storia, scelte, oos_fino_al=fino if _nel_studio(storia) else None)
    _salva_studio(storia)
    if _nel_studio(storia):
        c = _CONTESTO_STUDIO[storia.chiave]["studio"].get("contaminato")
        if c:
            _avviso(_frase_contaminato(c, corta=True))
        _note_studio(storia)
    if n > 1:
        prima = storia.diario[0]
        cambiate = [k for k in scelte if _rd.normale(prima.get(k)) != _rd.normale(scelte[k])]
        _avviso(f"Out-of-sample già guardato {n} volte. "
                + (f"Scelte cambiate dopo la prima volta: {', '.join(cambiate)}." if cambiate
                   else "Stesse scelte della prima volta.")
                + " Questa verifica non è più una prova pulita.")
    return n


def _sono_consigliate(s: Sessione, bl, bs, sl, tp, regola) -> bool:
    """Le uscite impostate sono quelle consigliate?"""
    c = s.consigliate or {}
    (sl_l, sl_s), (tp_l, tp_s) = per_lato(sl), per_lato(tp)
    rl, rs = (regola.split(" | ") if regola and " | " in regola else (regola, regola))
    ok = True
    for lato, b, sl_, tp_, r in (("long", bl, sl_l, tp_l, rl), ("short", bs, sl_s, tp_s, rs)):
        if lato not in c:
            continue
        r = None if r in (None, reg.NESSUNA) else r
        ok &= (b == c[lato]["barre"] and float(sl_) == c[lato]["sl"] and float(tp_) == c[lato]["tp"]
               and r == c[lato]["regola"])
    return bool(ok)


def _mostra_consigliate(s: Sessione, bl, bs, sl, tp, regola) -> None:
    """La tabella «Uscite consigliate» (25/10/2026, docs/68 §5.3), con la riga «La tua modifica» se diversa."""
    c = s.consigliate or {}
    if not c:
        return
    (sl_l, sl_s), (tp_l, tp_s) = per_lato(sl), per_lato(tp)
    rl, rs = (regola.split(" | ") if regola and " | " in regola else (regola, regola))

    def perc(p):
        return "spento" if not p else f"{_fmt(float(p), 0)}° percentile"

    def reg_txt(r):
        return "nessuna" if r in (None, reg.NESSUNA) else r
    righe = []
    for lato, b, sl_, tp_, r in (("long", bl, sl_l, tp_l, rl), ("short", bs, sl_s, tp_s, rs)):
        if lato not in c:
            continue
        x = c[lato]
        p = x["picco"]
        righe.append({"Lato": lato.upper(), "Quali": "consigliate", "Barre": x["barre"], "Stop": perc(x["sl"]),
                      "Target": perc(x["tp"]), "Regola oraria": reg_txt(x["regola"]),
                      "Picco della curva (solo da leggere)":
                          "—" if p["barra"] is None else f"barra {p['barra']}: {_fmt(p['valore'])} {s.unita}"})
        mie = (b, perc(sl_), perc(tp_), reg_txt(r))
        if mie != (x["barre"], perc(x["sl"]), perc(x["tp"]), reg_txt(x["regola"])):
            righe.append({"Lato": lato.upper(), "Quali": "la tua modifica", "Barre": b, "Stop": mie[1],
                          "Target": mie[2], "Regola oraria": mie[3], "Picco della curva (solo da leggere)": ""})
    tabella = pd.DataFrame(righe)
    s.tabelle["uscite_consigliate"] = tabella
    _mostra(("Uscite consigliate (barre = l'orizzonte H della schermata 1)", tabella))
    for lato, x in c.items():
        if x["picco"]["nota"]:
            _nota(f"{lato.capitalize()}: {x['picco']['nota']}")
    _nota("Il picco è il punto più alto della curva dell'in-sample: si mostra per capire il movimento, non per "
          "scegliere l'uscita. Se cambi le barre, la modifica conta come una prova."
          + (" Con un trigger a orario l'uscita consigliata è la scadenza scritta come orario: stessi trade."
             if any(x["regola"] for x in c.values()) else ""))


SISTEMI = ("Long + Short", "Solo long", "Solo short")


def rosa_dei_sistemi(s: Sessione, sistema: str | None = None) -> pd.DataFrame:
    """
    Schermata 4b (18/10/2026). La rosa di engine/rosa.py sui sistemi
    provati da `imposta_uscite` (solo long, solo short, entrambi), sui trade
    veri dell'in-sample e al netto dei costi: quali hanno un andamento netto
    positivo che regge il controllo della quota di falsi positivi e le due
    meta', e quali sono abbastanza diversi da stare insieme.

    sistema   25/10/2026 (docs/68 §7, decisioni 6 di Mattia): il sistema da
              portare al passo 5, «Long + Short», «Solo long» o «Solo short».
              None = «Long + Short» se c'e' (quello che il passo 5 usava
              sempre), altrimenti l'unico sistema provato. Non e' una prova in
              piu': i sistemi sono gia' contati alla schermata 4.

    Ritorna la tabella completa di rosa_sistemi (anche in `s.rosa_sistemi`).
    """
    s._serve("es", "4 · Imposta le uscite")
    provati = [_nome_sistema(riga) for _, riga in s.es.risultati.iterrows()]
    if sistema is None or str(sistema).strip() == "":
        sistema = "Long + Short" if "Long + Short" in provati else provati[0]
    sistema = str(sistema).strip()
    if sistema not in provati:
        raise ValueError(f"Sistema «{sistema}» non provato alla schermata 4. Sistemi provati: "
                         f"{', '.join(provati)}.")
    if (getattr(s, "storia", None) is not None and s.storia.oos_visto
            and s.storia.diario[-1].get("sistema") not in (None, sistema)):
        _avviso_risalita(s, "cambiare il sistema")
        _rd.annota_risalita(s.storia, "sistema", a=sistema)
        _salva_studio(s.storia)       # 25/10/2026 (docs/70)
    if sistema != getattr(s, "sistema", None):
        s.fs = s.dm = s.oos = None
        s.sopravvissuti, s.filtro = [], None
    s.sistema = sistema
    with _zitto():
        s.rosa_sistemi = rosa_sistemi(s.es, s.df_is, s.pip, commission=s.costi["commission"],
                                      fuso=s.fuso, atr=s.atr, unita=s.unita)
    r = s.rosa_sistemi
    nomi = {riga["combinazione"]: _nome_sistema(riga) for _, riga in s.es.risultati.iterrows()}

    def in_chiaro(testo):
        for comb, nome in nomi.items():
            testo = testo.replace(comb, f"«{nome}»")
        return testo

    u, a = s.unita, _altra_unita(s)
    tabella = pd.DataFrame({
        "Sistema": r["combinazione"].map(nomi),
        "Trade": r["trades"].astype(int),
        f"Più del mercato della stessa ora, per trade ({u} netti)": r[f"scarto_{u}"],
        "Solidità netta": r["t_netto"],
        f"Più del mercato a qualunque ora, per trade ({u} netti)": r[f"scarto_globale_{u}"],
        f"Più del mercato della stessa ora, per trade ({a} netti)": r[f"scarto_{a}"],
        f"Solidità in {a}": r[f"t_{a}"],
        "Supera la quota di fortuna": [_si_no(v) for v in r["bh"]],
        "Regge sulle due metà": [_si_no(v) for v in r["due_meta"]],
        "Nella rosa": [_si_no(v) for v in r["nella_rosa"]],
        "Perché fuori": [in_chiaro(p) for p in r["perche"]],
    })
    s.tabelle["rosa_sistemi"] = tabella
    _mostra(("La rosa dei sistemi (in-sample, al netto dei costi)", tabella),
            decimali={"Solidità netta": 2, f"Solidità in {a}": 2})
    _riquadro(
        "Gli stessi sistemi della schermata 4, letti con i controlli della rosa: guadagno netto per trade "
        "oltre quello che il mercato dà da solo nelle ore in cui il trade resta aperto, difficile da spiegare "
        "con la fortuna, positivo in entrambe le metà dell'in-sample. Due sistemi stanno insieme nella rosa "
        f"solo se i loro guadagni giornalieri sono poco legati (correlazione entro ±{_fmt(RHO_MAX, 1)}).",
        _frase_unita(s) +
        "Di solito «Long + Short» è molto legato ai due lati da soli, e la rosa ne tiene uno. Due lati da soli "
        "entrambi nella rosa vuol dire che si completano. Rosa vuota = nessun sistema si distingue abbastanza "
        "dal caso: non è una bocciatura, i filtri della schermata 5 possono ancora cambiarlo.",
        "È un suggerimento: scegli nel campo «sistema» quale portare alla schermata 5 (adesso: "
        f"«{sistema}»), poi vai alla 5 per cercare un filtro sul sistema base.")
    _nota(f"Al passo 5 va il sistema «{sistema}».")
    _riga_prove(s, "nessuna (i sistemi sono già contati alla schermata 4)")
    return r


def _entry_sistema(s: Sessione) -> tuple:
    """Le entry del passo 5 secondo il sistema scelto alla 4b (docs/68 §7): un lato spento = None."""
    sistema = getattr(s, "sistema", None) or "Long + Short"
    el = s.entry_long if sistema in ("Long + Short", "Solo long") else None
    es_ = s.entry_short if sistema in ("Long + Short", "Solo short") else None
    if el is None and es_ is None:          # il sistema scelto non ha entry (non dovrebbe succedere)
        return s.entry_long, s.entry_short
    return el, es_


# ========================================================================
# 5 · Trova la strategia
# ========================================================================

_ESITO = {DA_VALUTARE: "promosso", CAMPIONE_CORTO: "promosso (pochi trade)"}


def _prima_prova(esito, motivo) -> str:
    """L'esito della prima prova con il motivo, tradotto dal `motivo` del giudizio."""
    if esito in _ESITO:
        return _ESITO[esito]
    m = str(motivo or "")
    if m.startswith("EV netto"):
        perche = "in perdita dopo i costi"
    elif m.startswith("guadagno"):
        perche = "non migliora il sistema base"
    elif "NEGATIVO" in m:
        perche = "peggiora il sistema base"
    elif m.startswith("|t|"):
        perche = "miglioramento sotto l'asticella"
    elif m.startswith("P(EV<0)"):
        perche = "può ancora essere in perdita"
    elif m.startswith("confronto"):
        perche = "non scarta nessun trade"
    else:
        perche = ""
    return "non passa" + (f": {perche}" if perche else "")
_VERDETTO = {"regge": "regge", "non regge": "non regge", "giudizio sospeso": "troppo pochi trade"}


def _grafico_filtri(s: Sessione, filtri: list, promossi: list) -> None:
    """
    Schermata 5, sotto la classifica (19/10/2026, richiesta di Mattia): la somma
    dei pips netti trade dopo trade, IN-SAMPLE, del sistema base e dei filtri
    della classifica. Stessi trade e stessi costi della tabella (s.fs). Serve a
    vedere COME un filtro cambia l'andamento (regolarita', periodi), non a
    sceglierlo dalla curva: la scelta resta alle due prove della tabella.
    """
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 5))
    voci = [(BASELINE, "Sistema base (nessun filtro)", dict(color="black", lw=2.4))]
    for f in filtri:
        if f in s.sopravvissuti:
            voci.append((f, f"{f}  (regge le due prove)", dict(lw=2.0)))
        elif f in promossi:
            voci.append((f, f"{f}  (solo prima prova)", dict(lw=1.4)))
        else:
            voci.append((f, f"{f}  (non promosso)", dict(lw=1.0, alpha=0.7)))
    for nome, etichetta, stile in voci:
        tr = s.fs.trades(nome)
        if tr is None or len(tr) == 0:
            continue
        _, netti = netti_in_unita(tr, s.fs.pip_size, s.fs.commission or 0.0, s.unita)
        curva = pd.Series(netti.to_numpy(), index=pd.DatetimeIndex(tr["ExitTime"])).sort_index().cumsum()
        ax.plot(curva.index, curva.to_numpy(), label=f"{etichetta} · {len(tr)} trade", **stile)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel(f"{s.unita} netti accumulati")
    ax.set_title(f"Sistema base e filtri: somma dei {s.unita} netti, trade dopo trade (in-sample)")
    ax.grid(alpha=.3)
    ax.legend(fontsize=8, loc="best")
    plt.tight_layout()
    plt.show()
    _nota("Ogni linea usa gli stessi costi della tabella. Un filtro che migliora davvero alza la curva in modo "
          "regolare lungo tutto l'in-sample, non per un solo periodo. Le curve servono a capire, non a scegliere: "
          "scegliere il filtro dalla curva più bella conta come una prova in più; la scelta resta alle due prove "
          "della tabella.")


def _adesso_strada_b(s: Sessione, righe_cella: list) -> str:
    """
    «Cosa fare adesso» della schermata 5 con una situazione scelta (26/10/2026, revisione di Mattia).
    Quello che succede davvero alla 6: dal 28/10/2026 (docs/76, B1) con il filtro vuoto la scheda prova
    il segnale dentro la situazione (il nome CELLA_… della 5), coerente con le uscite della 4, costruite
    cosi'; prima provava il segnale da solo.
    """
    nome = righe_cella[0] if righe_cella else "il nome CELLA_… della tabella"
    regge = bool(righe_cella) and righe_cella[0] in s.sopravvissuti
    return (("La situazione regge le due prove. " if regge else
             "La situazione non ha superato le due prove: lo strumento non te la consiglia, ma puoi portarla lo "
             "stesso alla scheda. ")
            + f"Alla schermata 6, con il campo del filtro vuoto, si prova il segnale dentro la situazione ({nome}), "
            "con le uscite che la schermata 4 ha costruito proprio così. Per provare il segnale da solo o i filtri "
            "del catalogo, torna alla 3d e lascia vuota la situazione.")


def trova_strategia(s: Sessione, quanti: int = 8) -> pd.DataFrame:
    """
    Schermata 5. Prova tutti i filtri del registro sul sistema base
    (`run_filter_search_bt`, in-sample) e verifica i promossi sulle due meta'
    dello storico (`due_meta`). Mostra l'imbuto e la classifica.

    Ritorna la classifica dei filtri. I sopravvissuti sono in `s.sopravvissuti`.
    """
    s._serve("uscite", "4 · Imposta le uscite")
    _avviso_risalita(s, "rifare la ricerca dei filtri")
    # 22/10/2026 (docs/66 §5): con una cella scelta nell'atlante (strada B) si misura solo la cella,
    # con l'asticella delle celle misurate dall'atlante; altrimenti tutti i filtri, come sempre
    strada_b = _strada_b(s)
    if strada_b:
        filtri = [n for n in reg.list_filters() if n.startswith("CELLA_")]
        k_atlante = int(s.atlante.attrs["k_misurate"])
    else:
        filtri, k_atlante = _tutti_i_filtri(), None
    kw = _kw_motore(s)
    # 25/10/2026 (docs/68 §7): il sistema scelto alla 4b (un lato spento = None); nella strada B
    # il trigger senza cella, con le uscite della casistica (§3.3)
    entry_long, entry_short = _entry_sistema(s)
    with _zitto():
        s.fs = run_filter_search_bt(
            s.df_is, entry_long=entry_long, entry_short=entry_short,
            exit_rule_pair=s.uscite["regola"], filtri=filtri,
            min_trades_giudizio=MIN_TRADE_GIUDIZIO, p_max=P_MAX, alpha=ALPHA,
            verbose=False, cache_maschere=_cache_maschere(s, "is"), k_prove=k_atlante, **kw)
    r = s.fs.risultati
    prove = r[r["filtro"] != BASELINE]
    # 22/10/2026: soglia cumulata, i filtri provati con questi trigger e queste uscite. Nella
    # strada B la cella e' la seconda misura delle celle dell'atlante, gia' contate: non si somma
    if not strada_b:
        _rd.metti_prova(s.prove, "filtri", _chiave_filtri(s), len(prove))
    promossi =prove.loc[prove["esito"].isin([DA_VALUTARE, CAMPIONE_CORTO]), "filtro"].to_list()

    verdetti = {}
    s.dm = None
    if promossi:
        solo_costi = {k: kw[k] for k in ("perc_sl", "perc_tp", "finestra", "lag", "spread",
                                         "commission", "cash", "spread_rollover_pips", "funding",
                                         "spread_passo_pips")     # 25/10/2026 (docs/71)
                      if k in kw}
        with _zitto():
            s.dm = due_meta(s.df_is, s.fs, [None, *promossi], verbose=False,
                            cache_maschere=_cache_maschere(s, "due_meta"), **solo_costi)
        verdetti = s.dm.tabella.set_index("filtro")["verdetto"].to_dict()
    s.sopravvissuti = [f for f in promossi if verdetti.get(f) == "regge"]
    s.filtro = s.oos = s.trades_is = s.trades_oos = None
    s.filtri_scelti = []

    # --- imbuto ---------------------------------------------------------
    # 26/10/2026 (docs/73 §A.4): nella strada B l'imbuto dice che si misura solo la situazione scelta
    tappe = ([("Righe provate: la situazione scelta", len(prove)),
              ("Migliora davvero il segnale da solo", len(promossi)),
              ("Regge su entrambe le metà dello storico", len(s.sopravvissuti))] if strada_b else
             [("Filtri provati (una coppia long/short conta per uno)", len(prove)),
              ("Migliorano davvero il sistema base", len(promossi)),
              ("Reggono su entrambe le metà dello storico", len(s.sopravvissuti))])
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 2.9))
    massimo = max(tappe[0][1], 1)
    for i, (nome, n) in enumerate(tappe):
        larghezza = n / massimo
        if n:
            ax.barh(i, max(larghezza, 0.07), left=(1 - max(larghezza, 0.07)) / 2, height=0.72,
                    color=("#9db8d2", "#5b8fbe", "#1f5f99")[i])
        ax.text(0.5, i, f"{n}", ha="center", va="center", fontsize=14, fontweight="bold",
                color="white" if n else "#1f5f99")
        ax.text(1.03, i, nome, ha="left", va="center", fontsize=11)
    ax.set_xlim(0, 1)
    ax.set_ylim(len(tappe) - 0.5, -0.5)
    ax.axis("off")
    ax.set_title("L'imbuto: quanti filtri superano le prove", loc="left", fontsize=13)
    plt.tight_layout()
    plt.show()

    # --- classifica -----------------------------------------------------
    base = r[r["filtro"] == BASELINE].iloc[0]
    if strada_b:
        from .atlante import PREFISSO_FILTRI, nome_in_chiaro
        situazioni = " · ".join(nome_in_chiaro(c) for c in (s.cella_long, s.cella_short) if c)

        def _etichetta(filtro):
            return (f"Il segnale dentro la situazione: {situazioni} ({filtro})"
                    if str(filtro).startswith(PREFISSO_FILTRI) else filtro)
    else:
        def _etichetta(filtro):
            return filtro
    righe = [{"Filtro": "Il segnale da solo (senza la situazione)" if strada_b else "Sistema base (nessun filtro)",
              "Trade": int(base["trades"]),
              **_in_unita(s, "Guadagno medio netto per trade", base["avg_trade_netto"],
                          base.get("avg_trade_netto_pips")),
              f"Miglioramento sul sistema base ({s.unita})": np.nan,
              "Solidità del miglioramento": np.nan,
              "Prima prova": "—", "Seconda prova (due metà)": "—"}]
    ordinati = prove.assign(_s=prove["filtro"].isin(s.sopravvissuti),
                            _p=prove["filtro"].isin(promossi)
                            ).sort_values(["_s", "_p", "t_guadagno"],
                                          ascending=[False, False, False], na_position="last")
    for _, x in ordinati.head(quanti).iterrows():
        righe.append({
            "Filtro": _etichetta(x["filtro"]), "Trade": int(x["trades"]),
            **_in_unita(s, "Guadagno medio netto per trade", x["avg_trade_netto"],
                        x.get("avg_trade_netto_pips")),
            f"Miglioramento sul sistema base ({s.unita})": x["guadagno_pips"],
            "Solidità del miglioramento": x["t_guadagno"],
            "Prima prova": _prima_prova(x["esito"], x.get("motivo")),
            "Seconda prova (due metà)": _VERDETTO.get(verdetti.get(x["filtro"]), "—"),
        })
    tabella = pd.DataFrame(righe)
    s.tabelle["filtri"] = tabella
    _mostra(("Il segnale con e senza la situazione (in-sample, al netto dei costi)" if strada_b
             else "I filtri migliori (in-sample, al netto dei costi)", tabella))
    if strada_b:
        # 26/10/2026 (revisione di Mattia): il miglioramento non e' la differenza fra le due righe
        _nota(f"«Miglioramento sul sistema base» confronta, fra i trade del segnale da solo (prima riga), quelli "
              "dentro la situazione con quelli fuori. Per questo non è la differenza fra le due righe: la riga con la "
              "situazione è un backtest a sé, con trade diversi (scartare un trade libera il posto ad altri, che "
              "prima erano bloccati da una posizione aperta).")
    _grafico_filtri(s, list(ordinati.head(quanti)["filtro"]), promossi)

    asticella = float(s.fs.soglia_rumore)
    una_prova = soglia_rumore(1, ALPHA)
    s.tabelle["asticella"] = asticella
    if strada_b:
        _spiegazione(
            f"Dove sta l'asticella della prima prova: solidità del miglioramento di almeno {_fmt(asticella)}.",
            f"Qui provi una riga sola, la situazione scelta alla 3d. Ma l'hai scelta guardando {k_atlante} situazioni "
            f"sugli stessi dati dell'in-sample: questa è una seconda misura dello stesso effetto, non una prova nuova. "
            f"Per questo l'asticella è quella di {k_atlante} prove ({_fmt(asticella)}), non quella di una prova sola "
            f"({_fmt(una_prova, 0)}). Se la supera, passa alla seconda prova, sulle due metà dello storico.")
    else:
        _spiegazione(
            f"Dove sta l'asticella della prima prova: solidità del miglioramento di almeno {_fmt(asticella)}.",
            f"Perché non basta essere sopra 1? Solidità 1 vuol dire che il miglioramento è grande quanto la sua normale "
            f"oscillazione casuale: è il livello del puro rumore. Se avessi provato un solo filtro basterebbe circa "
            f"{_fmt(una_prova, 0)}: oltre quel valore un risultato capita per caso meno di 1 volta su 20. "
            f"Qui però i filtri provati sono {len(prove)}, e fra {len(prove)} tentativi il migliore arriva facilmente a "
            f"{_fmt(una_prova, 0)} anche quando nessuno vale davvero qualcosa: è come lanciare i dadi {len(prove)} volte "
            f"e guardare solo il tiro più alto. Per questo l'asticella sale con il numero di filtri provati: "
            f"con {len(prove)} è {_fmt(asticella)}. Chi la supera passa poi alla seconda prova, sulle due metà dello storico.")

    if s.sopravvissuti:
        adesso = ("Scegli uno dei filtri che «reggono» e scrivine il nome nella schermata 6 (puoi indicarne anche "
                  "più di uno, separati da virgola). Lì la strategia affronta i dati che non ha mai visto.")
    else:
        adesso = ("Nessun filtro ha superato entrambe le prove: lo strumento non te ne consiglia nessuno. "
                  "Puoi andare alla schermata 6 con il sistema base (lasciando vuoto il filtro), oppure tornare indietro "
                  "e cambiare trigger o uscite.")
    if strada_b:
        # 26/10/2026 (docs/73 §A.4): si misura solo la situazione, e il testo dice perche'
        _riquadro(
            f"Hai scelto una situazione alla 3d ({situazioni}). Qui si misura solo lei: lo stesso sistema, con le "
            "stesse uscite (quelle della schermata 4), una volta con il segnale da solo e una volta con il segnale "
            f"dentro la situazione. Di quanto migliora il guadagno per trade scartando i trade fuori dalla "
            f"situazione, in {s.unita}.",
            "Gli altri filtri non si provano. La situazione è già un filtro, e l'hai scelta guardando i dati "
            "dell'atlante: provarne altri sopra vorrebbe dire scegliere due volte sugli stessi dati. Per lo stesso "
            f"motivo l'asticella è quella di tutte le {k_atlante} situazioni che l'atlante ha guardato, non quella "
            "di una prova sola. Se la situazione la supera, passa alla seconda prova, sulle due metà.",
            _adesso_strada_b(s, [f for f in prove["filtro"] if str(f).startswith("CELLA_")]))
    else:
        _riquadro(
            "Ogni filtro è una condizione in più per entrare (trend, volatilità, orario…). Lo strumento li prova "
            "tutti, uno alla volta, e misura di quanto migliorano il guadagno per trade del sistema base scartando i "
            f"trade peggiori (in {s.unita}).",
            "Un filtro vale solo se supera due prove. Prima: il miglioramento deve essere più grande di quello che "
            "troveresti per caso provando così tanti filtri. Seconda: deve esserci in entrambe le metà dello "
            "storico, non in una sola. Più cose provi, più è facile trovarne una bella per caso: l'imbuto serve a "
            "questo.",
            adesso)
    _riga_prove(s, "nessuna (la situazione è già contata alla 3c)" if strada_b else f"{len(prove)} filtri")
    return tabella


# ========================================================================
# 6 · Scheda strategia
# ========================================================================

_VOCI_SCHEDA = [
    ("n_trades", "Trade", 0),
    ("ev_pips", "Guadagno medio netto per trade (pips)", 2),
    ("ev_bp", "Guadagno medio netto per trade (bp)", 2),        # 20/10/2026, docs/63 §4
    ("ev_atr", "Guadagno medio netto per trade (ATR)", 4),
    ("net_pips", "Totale pips netti", 0),
    ("win_rate", "Trade vincenti (%)", 1),
    ("wr_pareggio", "Vincenti necessari per il pareggio (%)", 1),
    ("reward_risk", "Vincita media / perdita media", 2),
    ("profit_factor", "Profit factor", 2),
    ("t_stat", "Solidità", 2),
    ("p_ev_neg", "Probabilità che in realtà perda (%)", 1),
    ("dd_chiusi_pips", "Drawdown massimo (pips)", 0),
]


def _membri_filtro(s: Sessione, etichetta: str) -> list[str]:
    """I nomi di filtro registrati che compongono una riga di fs.risultati."""
    riga = s.fs.risultati[s.fs.risultati["filtro"] == etichetta].iloc[0]
    return sorted({n for n in (riga["filtro_long"], riga["filtro_short"]) if n not in ("—", None)})


def _lista_filtri(s: Sessione, filtro) -> list[str]:
    """Da «F1, F2» (o da una lista) ai nomi scelti, controllati sulla classifica."""
    if filtro is None:
        voci = []
    elif isinstance(filtro, str):
        voci = filtro.split(",")
    else:
        voci = list(filtro)
    voci = [v.strip() for v in voci if isinstance(v, str) and v.strip()]
    scelti = list(dict.fromkeys(voci))                     # senza doppioni, nell'ordine scritto
    disponibili = [f for f in s.fs.risultati["filtro"] if f != BASELINE]
    mancanti = [f for f in scelti if f not in disponibili]
    if mancanti:
        raise ValueError(f"Filtro non trovato: {', '.join(mancanti)}. Copia i nomi dalla classifica della "
                         f"schermata 5 (più filtri: separali con una virgola), oppure lascia vuoto per il sistema base.")
    return scelti


def _kw_filtri(s: Sessione) -> dict:
    return dict(exit_rule_pair=s.fs.exit_rule_pair, min_trades_giudizio=MIN_TRADE_GIUDIZIO,
                p_max=P_MAX, alpha=ALPHA, verbose=False, **_kw_motore(s))


def _catena_filtri(s: Sessione, scelti: list[str]):
    """
    Applica i filtri uno sopra l'altro, nell'ordine scritto (7/10/2026).

    Il primo filtro e' gia' stato provato nella schermata 5 (`s.fs`). Per ogni
    filtro successivo si «congela» il precedente dentro le entry con
    `confidenza.congela_filtro` (entry AND filtro) e si riesegue
    `run_filter_search_bt` con il solo filtro nuovo: la sua baseline e' il
    passo prima, la sua riga e' il passo prima PIU' il filtro nuovo. Si entra
    quindi solo dove sono veri tutti i filtri. Nessun calcolo nuovo: sono le
    due funzioni dell'engine, usate in sequenza.

    Ritorna (entry_long, entry_short, fs_ultimo, passi): le entry con dentro
    tutti i filtri tranne l'ultimo, la ricerca dell'ultimo passo e le righe
    della tabella dei passi.
    """
    base = s.fs.risultati[s.fs.risultati["filtro"] == BASELINE].iloc[0]
    passi = [{"Passo": "Sistema base", "Trade": int(base["trades"]),
              **_in_unita(s, "Guadagno medio netto per trade", base["avg_trade_netto"],
                          base.get("avg_trade_netto_pips")),
              f"Miglioramento sul passo prima ({s.unita})": np.nan,
              "Solidità del miglioramento": np.nan}]
    entry_long, entry_short, fs_k = s.fs.entry_long, s.fs.entry_short, s.fs
    for k, etichetta in enumerate(scelti):
        if k > 0:
            entry_long, entry_short = congela_filtro(fs_k, scelti[k - 1])
            fs_k = run_filter_search_bt(s.df_is, entry_long=entry_long, entry_short=entry_short,
                                        filtri=_membri_filtro(s, etichetta),
                                        cache_maschere=_cache_maschere(s, "is"), **_kw_filtri(s))
        riga = fs_k.risultati[fs_k.risultati["filtro"] == etichetta].iloc[0]
        passi.append({"Passo": f"+ {etichetta}", "Trade": int(riga["trades"]),
                      **_in_unita(s, "Guadagno medio netto per trade", riga["avg_trade_netto"],
                                  riga.get("avg_trade_netto_pips")),
                      f"Miglioramento sul passo prima ({s.unita})": riga["guadagno_pips"],
                      "Solidità del miglioramento": riga["t_guadagno"]})
    return entry_long, entry_short, fs_k, passi


def _tabella_costi(s: Sessione, tr_is, tr_oos) -> pd.DataFrame | None:
    """
    Il costo medio per trade in tre righe, commissione, spread e funding
    (21/10/2026, docs/63 §5.5), con il segno (+ = pagato, - = incassato), in
    bp e in pips, in-sample e out-of-sample; il funding anche diviso fra long
    e short. Solo sui symbol da exchange. None se non ci sono trade.
    """
    if not s.da_exchange:
        return None
    pip = s.pip
    commissione = float(s.costi.get("commission") or 0.0)
    spread = float(s.costi.get("spread") or 0.0)
    righe = [("Commissione (andata e ritorno)", None), ("Spread", None)]
    con_funding = any(t is not None and "FundingPips" in t.columns for t in (tr_is, tr_oos))
    if con_funding:
        righe += [("Funding, tutti i trade", None), ("Funding dei long", 1), ("Funding degli short", -1)]
    righe.append(("Costo totale", None))

    def voci(t):
        if t is None or len(t) == 0:
            return None
        ent = t["EntryPrice"].to_numpy(dtype=float)
        usc = t["ExitPrice"].to_numpy(dtype=float)
        lato = np.where(t["Size"].to_numpy(dtype=float) > 0, 1, -1)
        c = commissione * (ent + usc) / pip
        sp = spread * ent / pip
        if "CostoExtraPips" in t.columns:
            sp = sp + t["CostoExtraPips"].fillna(0.0).to_numpy(dtype=float)
        fu = t["FundingPips"].fillna(0.0).to_numpy(dtype=float) if "FundingPips" in t.columns else np.zeros(len(t))
        bp = pip * 10_000.0 / ent
        per_riga = {"Commissione (andata e ritorno)": (c, None), "Spread": (sp, None),
                    "Funding, tutti i trade": (fu, None), "Funding dei long": (fu, 1),
                    "Funding degli short": (fu, -1), "Costo totale": (c + sp + fu, None)}
        out = {}
        for nome, (v, quale) in per_riga.items():
            m = np.ones(len(t), dtype=bool) if quale is None else lato == quale
            out[nome] = ((float(np.mean(v[m] * bp[m])), float(np.mean(v[m]))) if m.any()
                         else (np.nan, np.nan))
        return out

    tabella = {"": [nome for nome, _ in righe]}
    for etichetta, t in (("In-sample", tr_is), ("Out-of-sample", tr_oos)):
        v = voci(t)
        tabella[f"{etichetta} (bp)"] = [np.nan if v is None else v[nome][0] for nome, _ in righe]
        tabella[f"{etichetta} (pips)"] = [np.nan if v is None else v[nome][1] for nome, _ in righe]
    return pd.DataFrame(tabella)


def _mostra_costi(s: Sessione, tr_is, tr_oos) -> pd.DataFrame | None:
    """Mostra _tabella_costi con la sua nota (scheda e verifica dei trade)."""
    tabella = _tabella_costi(s, tr_is, tr_oos)
    if tabella is None:
        return None
    s.tabelle["costi"] = tabella
    _mostra(("Il costo medio per trade (+ = pagato, − = incassato)", tabella))
    if "Funding, tutti i trade" in set(tabella[""]):
        _nota("Il funding si paga, o si incassa, a ogni liquidazione in cui il trade è aperto (ingresso < "
              "liquidazione ≤ uscita), al prezzo di apertura della barra della liquidazione: l'exchange usa il "
              "prezzo «mark», che qui non c'è; la differenza è di pochi millesimi sul costo. Con il tasso positivo "
              "il long paga e lo short incassa. Il funding resta fuori dal rischio del money management: si "
              "conosce solo a trade chiuso.")
    elif s.da_exchange and not s.solo_long:
        _nota("Funding spento: non è contato (serve solo alla prova di identità).")
    return tabella


# ------------------------------------------------------------------------
# La soglia cumulata (22/10/2026, docs/63 §10.3, «Cosa manca» punto 3)
# ------------------------------------------------------------------------

def _chiave_filtri(s: Sessione) -> tuple:
    """Le impostazioni di una ricerca dei filtri: i trigger, le uscite e (25/10/2026) il sistema della 4b."""
    return chiave_filtri(s.trigger_long, s.trigger_short, s.uscite, getattr(s, "sistema", None))


# 28/10/2026 (docs/76, A1): le chiavi del conto in funzioni comuni, chiamate dal Lab e dal notebook di
# ricerca: le stesse impostazioni danno la stessa chiave, e la stessa prova non si conta due volte

def chiave_celle(H: int, tab: pd.DataFrame, nomi) -> tuple:
    """La chiave delle celle di un atlante: H, gli assi e i trigger misurati, nell'ordine passato."""
    return (H, tab.attrs["assi"], tuple(nomi))


def chiave_uscite(trigger_long, trigger_short, uscite: dict, cella_long=None, cella_short=None) -> tuple:
    """La chiave di una ricerca delle uscite: casistiche, barre, stop, target, regola e situazioni."""
    return (tuple(trigger_long or ()), tuple(trigger_short or ()), uscite["n_barre_long"], uscite["n_barre_short"],
            uscite["perc_sl"], uscite["perc_tp"], str(uscite["regola"]), cella_long, cella_short)


def chiave_filtri(trigger_long, trigger_short, uscite: dict, sistema=None) -> tuple:
    """La chiave di una ricerca dei filtri: casistiche, uscite e sistema."""
    return (tuple(trigger_long or ()), tuple(trigger_short or ()),
            tuple(sorted((k, str(v)) for k, v in uscite.items())), sistema or "Long + Short")


def _soglia_da_conti(trigger: int, uscite: list, filtri: list, combinazioni: list, t: float,
                     schermate: bool, alpha: float = ALPHA, celle: list = (), rimisura: bool = False,
                     fasce: int = 0, orizzonti=None, mappa: int = 0) -> dict:
    """
    La soglia di Sidak (giudizio.soglia_rumore) sul totale delle prove della
    catena, e la frase da mostrare sotto la scheda. Solo informativa.

    orizzonti      25/10/2026 (docs/68 §9.1): gli H provati sullo stesso dataset. Con
                   piu' di uno, la voce dei trigger diventa il numero di prove
                   equivalente alla scelta del migliore fra quegli H
                   (giudizio.prove_trigger_orizzonti); con uno solo, o None, e' il
                   conto di prima.

    trigger        i trigger misurati dall'event study
    uscite         i sistemi provati, uno per ricerca delle uscite
    filtri         i filtri provati, uno per ricerca dei filtri
    combinazioni   C(n, m) per ogni scelta a mano di m > 1 filtri fra n
    celle          22/10/2026 (docs/66 §6): le celle misurate, una voce per atlante
    rimisura       True se al passo 5 si e' riprovata una cella dell'atlante (strada B):
                   e' gia' fra le celle, la frase lo dice
    fasce          23/10/2026: con un trigger a orario, le fasce del profilo orario (una
                   volta sola: scegliere un'ora e' scegliere fra tutte le fasce)
    mappa          28/10/2026 (docs/73 §B.4): le fasce della mappa delle anomalie contate
                   nello studio per questo dataset (fasce_mappa). 0 = il conto di prima
    """
    u, f, c, ce = int(sum(uscite)), int(sum(filtri)), int(sum(combinazioni)), int(sum(celle))
    h = sorted({int(x) for x in (orizzonti or [])})
    voce_trigger = prove_trigger_orizzonti(trigger, h, alpha) if len(h) > 1 else int(trigger)
    k = voce_trigger + int(fasce) + int(mappa) + ce + u + f + c
    if float(k).is_integer():
        k = int(k)
    soglia = _soglia_sidak(k, alpha) if k else np.nan

    def dove(n):
        return f" (schermata {n})" if schermate else ""

    if len(h) > 1:
        parti = [f"{int(trigger)} trigger misurati con {len(h)} orizzonti provati sullo stesso dataset "
                 f"(H = {', '.join(str(x) for x in h)}), che valgono {_fmt(voce_trigger, 1)} prove{dove('2c')}"]
    elif trigger or not mappa:
        parti = [f"{int(trigger)} trigger misurati{dove('2c')}"]
    else:
        parti = []          # 28/10/2026: solo le fasce della mappa (il notebook della mappa), niente «0 trigger»
    if fasce:
        parti.append(f"{int(fasce)} fasce del profilo orario (trigger a orario){dove('2a')}")
    if mappa:
        parti.append(f"{int(mappa)} fasce della mappa delle anomalie{dove('2b')}")
    if celle:
        # 26/10/2026 (docs/73, D2): «situazioni» nei testi, «celle» nel codice
        parti.append(f"{ce} situazioni dell'atlante" + (f" in {len(celle)} atlanti" if len(celle) > 1 else "")
                     + dove("3c")
                     + (" (la situazione riprovata al passo 5 è una di queste: non conta due volte)" if rimisura
                        else ""))
    if uscite:
        parti.append(f"{u} sistemi provati in {len(uscite)} "
                     f"{'impostazione' if len(uscite) == 1 else 'impostazioni'} delle uscite{dove(4)}")
    if filtri:
        parti.append(f"{f} filtri" + (f" in {len(filtri)} ricerche" if len(filtri) > 1 else "") + dove(5))
    if c:
        parti.append(f"{c} combinazioni di filtri scelte a mano{dove(6)}")
    k_testo = _fmt(k, 1) if isinstance(k, float) else str(k)
    if k:
        frase = (f"Soglia cumulata (solo informativa). Lungo la catena hai fatto {k_testo} prove: "
                 f"{', '.join(parti)}. Con {k_testo} prove il caso da solo arriva fino a una solidità di "
                 f"{_fmt(soglia)} (Šidák, famiglia {alpha:.0%}).")
    else:
        frase = "Soglia cumulata (solo informativa). Nessuna prova contata finora."
    if np.isfinite(t):
        frase += f" La solidità in-sample di questa strategia è {_fmt(t)}."
    frase += (" È un conto prudente: tratta le prove come indipendenti, quindi è un po' più severo del vero. "
              "Non cambia nessun controllo.")
    return {"trigger": int(trigger), "uscite": u, "ricerche_uscite": len(uscite), "filtri": f,
            "ricerche_filtri": len(filtri), "combinazioni": c, "celle": ce, "atlanti": len(celle),
            "fasce": int(fasce), "mappa": int(mappa), "k": k, "soglia": soglia, "alpha": alpha, "t": t, "frase": frase,
            "orizzonti": h, "voce_trigger": voce_trigger}


def _soglia_sidak(k, alpha: float = ALPHA) -> float:
    """
    soglia_rumore anche per un numero di prove non intero (25/10/2026, docs/68
    §9.1: la scelta fra orizzonti sovrapposti vale un numero equivalente di
    prove). Con k intero e' esattamente soglia_rumore(k).
    """
    if float(k).is_integer():
        return soglia_rumore(int(k), alpha)
    from statistics import NormalDist
    per_prova = 1.0 - (1.0 - alpha) ** (1.0 / float(k))
    return float(NormalDist().inv_cdf(1.0 - per_prova / 2.0))


def _lista(x) -> list:
    """None -> [], un oggetto -> [oggetto], una lista -> la lista senza doppioni (stesso oggetto)."""
    if x is None:
        return []
    voci = list(x) if isinstance(x, (list, tuple)) else [x]
    viste, unici = set(), []
    for v in voci:
        if v is not None and id(v) not in viste:
            viste.add(id(v))
            unici.append(v)
    return unici


def soglia_cumulata(ev=None, es=None, fs=None, combinazioni: int = 0, t: float = np.nan,
                    alpha: float = ALPHA, atlante=None, fasce: int = 0, orizzonti=None, mappa: int = 0) -> dict:
    """
    La soglia cumulata per il notebook di ricerca (22/10/2026), con gli
    stessi conti del Lab:

        ev             l'event study dei trigger (run_event_study): conta
                       i trigger misurati, len(ev.sintesi)
        es             una ricerca delle uscite o una lista (le celle 2.2 e
                       2.3): conta le righe di ciascuna
        fs             una ricerca dei filtri o una lista: conta le righe
                       senza la baseline
        combinazioni   C(n, m) se si sono scelti a mano m > 1 filtri fra n
        t              la solidita' in-sample della strategia, da mostrare accanto
        atlante        22/10/2026 (docs/66 §6): la tabella di atlante.atlante, o una
                       lista: conta le celle misurate (attrs["k_misurate"]). Una
                       ricerca dei filtri fatta sulla cella scelta (k_prove,
                       .rimisura) non si conta: e' la seconda misura delle celle
        fasce          23/10/2026: se si e' scelto un trigger a orario, le fasce del
                       profilo orario (profilo.attrs["k"]), contate una volta
        orizzonti      25/10/2026 (docs/68 §9.1): gli H provati sullo stesso dataset
                       (registro_orizzonte(...).h_provati); con piu' di uno la voce dei
                       trigger conta la scelta fra quegli H
        mappa          28/10/2026 (docs/73 §B.4): le fasce della mappa delle anomalie
                       contate nello studio per il dataset, fasce_mappa(STORIA)

    Lo stesso oggetto passato due volte conta una volta sola (la stessa
    ricerca rieseguita non e' una prova in piu'). Solo informativa: non
    boccia e non blocca niente. Ritorna il dizionario dei conti, con la
    frase in "frase".
    """
    trigger = len(ev.sintesi) if ev is not None else 0
    uscite = [len(e.risultati) for e in _lista(es)]
    ricerche = _lista(fs)
    filtri = [int((f.risultati["filtro"] != BASELINE).sum()) for f in ricerche
              if not getattr(f, "rimisura", False)]
    celle = [int(a.attrs["k_misurate"]) for a in _lista(atlante)]
    return _soglia_da_conti(trigger, uscite, filtri, [int(combinazioni)] if combinazioni else [],
                            float(t), schermate=False, alpha=alpha, celle=celle,
                            rimisura=any(getattr(f, "rimisura", False) for f in ricerche),
                            fasce=int(fasce), orizzonti=orizzonti, mappa=int(mappa))


def fasce_mappa(storia_o_prove) -> int:
    """
    Le fasce della mappa delle anomalie nel conto del dataset (28/10/2026, docs/73
    §B.4): la somma delle voci «prova» con dove = "mappa" che il registro ha letto
    dai giornali dello studio, una per scheda, versione e orizzonte. Accetta la
    storia del dataset (registro_orizzonte, s.storia) o il suo dizionario delle prove.
    """
    prove = getattr(storia_o_prove, "prove", storia_o_prove) or {}
    voci = prove.get("mappa", {})
    return int(sum(int(n) for n in voci.values())) if isinstance(voci, dict) else int(voci or 0)


def _soglia_dal_conto(p: dict, storia, t: float, schermate: bool, rimisura: bool) -> dict:
    """La soglia cumulata di un conto delle prove (quello della sessione del Lab o della storia del dataset)."""
    return _soglia_da_conti(p.get("trigger", 0), list(p.get("uscite", {}).values()),
                            list(p.get("filtri", {}).values()), list(p.get("combinazioni", {}).values()), t,
                            schermate=schermate, celle=list(p.get("celle", {}).values()), rimisura=rimisura,
                            fasce=int(p.get("fasce", 0)),
                            orizzonti=storia.h_provati if storia is not None else None, mappa=fasce_mappa(p))


def _soglia_cumulata_lab(s: Sessione, t: float) -> dict:
    """La soglia cumulata delle prove registrate nella sessione (schermate 2, 4, 5, 6)."""
    return _soglia_dal_conto(s.prove, getattr(s, "storia", None), t, schermate=True,
                             rimisura=bool(getattr(s, "fs", None) is not None and getattr(s.fs, "rimisura", False)))


# ========================================================================
# 28/10/2026 (docs/76, A1-A2): il conto del notebook di ricerca nello studio
# ========================================================================
# Ogni cella della ricerca che misura chiama una di queste funzioni: la voce va nel conto del
# dataset (registro_orizzonte) con la stessa chiave che userebbe il Lab, e il giornale dello studio
# riceve solo le voci cambiate (_salva_studio). Per ogni chiave vale il numero piu' alto
# (registro_dataset.metti_prova): la stessa prova, fatta dal Lab o dalla ricerca, conta una volta.
# Non stampano niente: i numeri della ricerca restano quelli di prima.

def trigger_candidati(symbol: str) -> list[str]:
    """I trigger che la ricerca misura, gli stessi del Lab e nello stesso ordine: sullo spot solo i long (A2)."""
    from .exchange import solo_long
    return _trigger_candidati(1 if solo_long(symbol) else None)


def _conta(storia, dove: str, chiave, n) -> None:
    if storia is None:
        return
    _rd.metti_prova(storia.prove, dove, chiave, int(n))
    _salva_studio(storia)


def conta_trigger(storia, ev) -> None:
    """Sessione 1.1: i trigger misurati dall'event study (la 2c del Lab)."""
    _conta(storia, "trigger", None, len(ev.sintesi))


def conta_fasce(storia, df_is: pd.DataFrame, symbol: str, scelti) -> None:
    """Le fasce del profilo orario, se fra i trigger scelti c'e' un trigger a orario (la 3b del Lab)."""
    import condizioni_orarie
    if any(n and condizioni_orarie.e_oraria(n) for n in scelti):
        _conta(storia, "fasce", None, n_fasce(fasce_orarie(df_is.index, fuso_profilo(symbol))[1]))


def conta_celle(storia, H: int, atl: pd.DataFrame, nomi) -> None:
    """Sessione 1.5: le celle misurate dall'atlante (la 3c del Lab), con H, assi e trigger passati all'atlante."""
    _conta(storia, "celle", chiave_celle(H, atl, nomi), atl.attrs["k_misurate"])


def _regola_chiave(regola):
    """La regola d'uscita nella chiave: un elenco di regole (la 2.3 della ricerca, D2) diventa una tupla."""
    return tuple(regola) if isinstance(regola, list) else regola


def conta_uscite(storia, es, casistiche_long, casistiche_short, H: int, sl, tp, regola=None,
                 cella_long=None, cella_short=None) -> None:
    """
    Sessione 2.2 e 2.3: i sistemi provati da una ricerca delle uscite (la 4 del Lab). regola: quella
    passata al motore; nella 2.3 l'elenco di tutte le regole provate (docs/76, D2).
    """
    u = impostazioni_uscite(H, H, sl, tp, _regola_chiave(regola))
    _conta(storia, "uscite", chiave_uscite(casistiche_long, casistiche_short, u, cella_long, cella_short),
           len(es.risultati))


def conta_filtri(storia, fs, casistiche_long, casistiche_short, H: int, sl, tp, regola=None, sistema=None,
                 confidenza=None) -> None:
    """
    Sessione 3.1: i filtri provati (la 5 del Lab), senza la baseline. Nella strada B (la cella riprovata,
    fs.rimisura) niente: la cella e' gia' fra le celle dell'atlante. confidenza (docs/76, D2): nella 3.3
    (soglie, filtro congelato), una chiave a parte.
    """
    if getattr(fs, "rimisura", False):
        return
    chiave = chiave_filtri(casistiche_long, casistiche_short, impostazioni_uscite(H, H, sl, tp, regola), sistema)
    if confidenza is not None:
        soglie, filtro = confidenza
        chiave = (*chiave, ("confidenza", tuple(float(x) for x in soglie), filtro))
    _conta(storia, "filtri", chiave, int((fs.risultati["filtro"] != BASELINE).sum()))


def soglia_cumulata_studio(storia, t: float = np.nan, rimisura: bool = False) -> dict:
    """
    La soglia cumulata della ricerca letta dal conto del dataset (28/10/2026, docs/76, A1), come il Lab: le
    prove della ricerca, del Lab e della mappa su questo dataset. rimisura: True nella strada B (la cella
    riprovata alla 3.1 e' gia' fra le celle). Solo informativa.
    """
    return _soglia_dal_conto(storia.prove or {}, storia, float(t), schermate=False, rimisura=bool(rimisura))


def _riga_prove(s: Sessione, qui: str) -> dict:
    """
    La riga delle prove in fondo a ogni schermata dalla 2 alla 6 (25/10/2026,
    docs/68 §8): quante prove ha fatto questa schermata (`qui`, gia' scritto) e
    quante in tutto fin qui, con la soglia del caso. Gli stessi conti della
    scheda (_soglia_cumulata_lab). Solo informativa.
    """
    _salva_studio(getattr(s, "storia", None))   # 25/10/2026 (docs/70): il conto nel giornale dello studio
    conti = _soglia_cumulata_lab(s, np.nan)
    k = conti["k"]
    k_testo = _fmt(k, 1) if isinstance(k, float) else _fmt(k)
    voci = [(("trigger", "trigger"), conti["voce_trigger"]), (("fascia oraria", "fasce orarie"), conti["fasce"]),
            (("fascia della mappa", "fasce della mappa"), conti["mappa"]),
            (("situazione", "situazioni"), conti["celle"]), (("sistema", "sistemi"), conti["uscite"]),
            (("filtro", "filtri"), conti["filtri"]), (("combinazione", "combinazioni"), conti["combinazioni"])]
    dettaglio = ", ".join(f"{_fmt(v, 1) if isinstance(v, float) and not float(v).is_integer() else _fmt(int(v))} "
                          f"{nome[0] if v == 1 else nome[1]}" for nome, v in voci if v)
    testo = (f"Prove · questa schermata: {qui} · finora: {k_testo}"
             + (f" ({dettaglio})" if dettaglio else "")
             + (f" · con {k_testo} prove il caso arriva fino a una solidità di {_fmt(conti['soglia'])}."
                if k else "."))
    if _in_notebook():
        _html(f"<div class='vt-prove'>{html.escape(testo)}</div>")
    else:
        print(testo)
    s.tabelle["riga_prove"] = testo
    return conti


def _avviso_risalita(s: Sessione, cosa: str) -> None:
    """
    Il riquadro arancione delle schermate 2-5 rieseguite dopo aver guardato
    l'out-of-sample (25/10/2026, docs/68 §9). Non blocca niente.
    """
    storia = getattr(s, "storia", None)
    if storia is None or not storia.oos_visto:
        return
    quando = pd.Timestamp(storia.diario[0]["quando"]).tz_convert("Europe/Rome").strftime("%d/%m %H:%M")
    _avviso(f"Hai già guardato l'out-of-sample ({len(storia.diario)} "
            f"{'volta' if len(storia.diario) == 1 else 'volte'}, la prima il {quando}). Le scelte che fai adesso "
            f"({cosa}) le fai sapendo come è andata: la prossima scheda non è più una prova pulita.")


def _chiave_uscite(s: Sessione) -> tuple:
    """Le impostazioni delle uscite della schermata 4, con le casistiche e la cella (docs/68 §5.4)."""
    return chiave_uscite(s.trigger_long, s.trigger_short, s.uscite, getattr(s, "cella_long", None),
                         getattr(s, "cella_short", None))


_NOMI_SCELTE = {"H": "orizzonte H", "trigger_long": "casistiche long", "trigger_short": "casistiche short",
                "cella": "cella", "uscite": "uscite", "sistema": "sistema", "filtri": "filtri"}


def _diario_oos(s: Sessione, scelti: list) -> None:
    """
    Scrive nel diario del dataset un'apertura dell'out-of-sample con le scelte di quel
    momento (25/10/2026, docs/68 §9). Dalla seconda apertura dice quante sono e quali
    scelte sono cambiate dopo la prima. Non blocca niente.
    """
    storia = getattr(s, "storia", None)
    if storia is None:
        return
    scelte = {"H": s.H, "trigger_long": tuple(s.trigger_long), "trigger_short": tuple(s.trigger_short),
              "cella": (getattr(s, "cella_long", None), getattr(s, "cella_short", None)),
              "uscite": _chiave_uscite(s), "sistema": getattr(s, "sistema", None) or "Long + Short",
              "filtri": tuple(scelti)}
    # 25/10/2026 (docs/70 §3.2): nello studio anche l'ultima barra out-of-sample di adesso, per il reset
    n = _rd.annota_oos(storia, scelte, oos_fino_al=s.df_oos.index[-1] if _nel_studio(storia) else None)
    _salva_studio(storia)
    if _nel_studio(storia):
        c = _CONTESTO_STUDIO[storia.chiave]["studio"].get("contaminato")
        if c:
            _avviso(_frase_contaminato(c, corta=True))
        _note_studio(storia)
    if n > 1:
        prima = storia.diario[0]
        # 25/10/2026: confronto nella forma del JSON (un diario riletto dal giornale ha liste, non tuple)
        cambiate = [_NOMI_SCELTE[k] for k in scelte if _rd.normale(prima.get(k)) != _rd.normale(scelte[k])]
        _avviso(f"Out-of-sample già guardato {n} volte. "
                + (f"Scelte cambiate dopo la prima volta: {', '.join(cambiate)}." if cambiate
                   else "Stesse scelte della prima volta.")
                + " Questa scheda non è più una prova pulita: i numeri a destra li hai già visti.")
    s.tabelle["diario_oos"] = list(storia.diario)


def scheda(s: Sessione, filtro=None) -> pd.DataFrame:
    """
    Schermata 6. La scheda della strategia scelta: in-sample accanto alla
    prova out-of-sample (stesso setup, rieseguito sui dati mai visti), e
    l'equity out-of-sample contro il buy & hold.

    filtro   il nome di un filtro della classifica, oppure piu' nomi separati
             da virgola (o una lista): si entra solo dove sono veri TUTTI.
             None o vuoto = sistema base; con una situazione scelta alla 3d
             (strada B) = il segnale dentro la situazione (28/10/2026, docs/76, B1).

    Con piu' filtri mostra anche la tabella dei passi (base, + primo filtro,
    + secondo ...). Ritorna la tabella della scheda.
    """
    s._serve("fs", "5 · Trova la strategia")
    scelti = _lista_filtri(s, filtro)
    if not scelti and _strada_b(s):
        # 28/10/2026 (docs/76, B1): con una situazione scelta il predefinito e' il segnale dentro la situazione,
        # coerente con le uscite della 4 (costruite cosi'); prima era il segnale da solo
        scelti = [f for f in s.fs.risultati["filtro"] if str(f).startswith("CELLA_")][:1]
        if scelti:
            _nota(f"Filtro vuoto con una situazione scelta: si prova il segnale dentro la situazione ({scelti[0]}).")
    ultimo = scelti[-1] if scelti else None
    kw = _kw_motore(s)
    kw["margin"] = 1.0
    with _zitto():
        entry_long, entry_short, fs_ultimo, passi = _catena_filtri(s, scelti)
        s.oos = run_filter_search_bt(
            s.df_oos, entry_long=entry_long, entry_short=entry_short,
            exit_rule_pair=s.fs.exit_rule_pair,
            filtri=_membri_filtro(s, ultimo) if ultimo else [],
            min_trades=s.fs.min_trades, verbose=False,
            cache_maschere=_cache_maschere(s, "oos"), **kw)
        tr_is, tr_oos = fs_ultimo.trades(ultimo), s.oos.trades(ultimo)
        k_is = scheda_strategia(tr_is, s.fs.pip_size, s.fs.commission or 0.0,
                                montecarlo=False, verbose=False, atr=s.atr, unita=s.unita)
        k_oos = scheda_strategia(tr_oos, s.fs.pip_size, s.fs.commission or 0.0,
                                 montecarlo=False, verbose=False, atr=s.atr, unita=s.unita)
        # 25/10/2026 (docs/70 §13): il tratto mai guardato, prima di scrivere l'apertura di adesso nel diario
        fresco = oos_fresco(getattr(s, "storia", None), s.df_oos)
        tr_fr = trade_freschi(fresco, tr_oos, s.df_oos)
        k_fr = (scheda_strategia(tr_fr, s.fs.pip_size, s.fs.commission or 0.0, montecarlo=False, verbose=False,
                                 atr=s.atr, unita=s.unita)
                if tr_fr is not None and len(tr_fr) and len(fresco["barre"]) else None)
    s.filtri_scelti = scelti
    s.filtro = " + ".join(scelti) if scelti else None
    s.trades_is, s.trades_oos = tr_is, tr_oos
    s.mm = None                     # 16/10/2026: la schermata 7 va rifatta sulla scheda nuova
    _diario_oos(s, scelti)          # 25/10/2026 (docs/68 §9): ogni apertura dell'out-of-sample

    if len(scelti) > 1:
        tab_passi = pd.DataFrame(passi)
        s.tabelle["passi"] = tab_passi
        _mostra(("Un filtro sopra l'altro (in-sample, al netto dei costi)", tab_passi))
        n_prove = int((s.fs.risultati["filtro"] != BASELINE).sum())
        combinazioni = math.comb(n_prove, len(scelti))
        # 22/10/2026: soglia cumulata, la famiglia «m filtri fra n» conta una volta
        _rd.metti_prova(s.prove, "combinazioni", (_chiave_filtri(s), len(scelti)), combinazioni)
        _salva_studio(s.storia)       # 25/10/2026 (docs/70)
        _spiegazione(
            "Combinazione scelta a mano: non è passata dall'imbuto.",
            f"Ogni riga aggiunge un filtro a quella sopra: si entra solo quando sono veri tutti. Guarda quanti trade "
            f"toglie ogni passo e quanto migliora il guadagno medio. Se due filtri misurano la stessa cosa, il secondo "
            f"toglie pochi trade e aggiunge poco. Attenzione all'asticella: scegliendo {len(scelti)} filtri fra "
            f"{n_prove} le combinazioni possibili sono {_fmt(combinazioni)}, e fra così tanti tentativi una che sembra "
            f"buona si trova sempre. Come ordine di grandezza, per fidarsi di una combinazione scelta a occhio la "
            f"solidità dovrebbe superare {_fmt(soglia_rumore(combinazioni, ALPHA))}. "
            f"La prova che conta resta la colonna out-of-sample qui sotto.")
    else:
        s.tabelle.pop("passi", None)

    tabella = pd.DataFrame({
        "": [nome for _, nome, _ in _VOCI_SCHEDA],
        "In-sample": [_fmt(k_is.get(k, np.nan), d) for k, _, d in _VOCI_SCHEDA],
        "Out-of-sample": [_fmt(k_oos.get(k, np.nan), d) for k, _, d in _VOCI_SCHEDA],
    })
    if k_fr is not None:                  # 25/10/2026 (docs/70 §13): accanto, il solo tratto mai guardato
        tabella["Out-of-sample mai guardato"] = [_fmt(k_fr.get(k, np.nan), d) for k, _, d in _VOCI_SCHEDA]
    s.tabelle["scheda"] = tabella
    s.tabelle["oos_fresco"] = (None if fresco is None else
                               {**fresco, "trade": 0 if tr_fr is None else len(tr_fr)})
    nome = s.filtro or "sistema base"
    if fresco is not None:
        _nota(_frase_fresco(fresco, 0 if tr_fr is None else len(tr_fr), int(s.fs.min_trades)))
    _mostra((f"Scheda strategia · {s.symbol} · {nome}", tabella))
    if s.unita != "pips":
        _nota(f"Decide il {s.unita}: solidità, probabilità che in realtà perda, trade vincenti, vincita media / "
              f"perdita media e profit factor sono calcolati sui {s.unita} netti di ogni trade. Totale e drawdown "
              "restano in pips: sono i soldi del conto.")
    _mostra_costi(s, tr_is, tr_oos)       # 21/10/2026: commissione, spread, funding
    # 22/10/2026 (docs/63 §10.3): la soglia cumulata al posto della riga del mercato
    # nullo (sospeso, il codice resta). Solo informativa: nessun cancello cambia
    s.tabelle["soglia_cumulata"] = _soglia_cumulata_lab(s, float(k_is.get("t_stat", np.nan)))
    _nota(s.tabelle["soglia_cumulata"]["frase"])

    if len(tr_oos):
        plot_equity(tr_oos, s.df_oos, cash=CASH, etichetta=nome, figsize=(11, 4.8))
        import matplotlib.pyplot as plt
        plt.tight_layout()
        plt.show()
    else:
        _nota("Nessun trade nel periodo out-of-sample: non c'è un'equity da disegnare.")

    _riquadro(
        "La stessa strategia su due periodi: a sinistra i dati su cui l'hai costruita, a destra quelli che non "
        "ha mai visto. Il grafico mostra il conto out-of-sample contro chi avesse semplicemente comprato e tenuto.",
        "Conta la colonna di destra. Una strategia cucita su misura sul passato brilla in-sample e si spegne "
        "out-of-sample; una che ha colto qualcosa di vero tiene numeri simili, anche se un po' più bassi. "
        "Guarda guadagno medio per trade, probabilità che in realtà perda (meglio sotto il 5%) e drawdown.",
        "Vai alla schermata 7 per scegliere quanto rischiare su ogni trade, alla 8 per controllare che i trade siano entrati dove dicono le tue regole e alla 9 per capire quanto drawdown aspettarti e con quanti lotti partire. "
        "L'out-of-sample si guarda una volta sola: se torni indietro a ritoccare finché non ti piace, smette di essere una prova.")
    return tabella


# ========================================================================
# 7 · Money management (16/10/2026, fase 1 di docs/61)
# ========================================================================

SIMULAZIONI_MM = 10_000
MESI_CONTROLLO = (3, 6, 12)        # fase 2: periodi della tabella di controllo (docs/61 §13.6)
PERCENTILE_MM = 95                 # lo stesso «caso sfortunato» dello stress test


def _lettura_z(zs: dict) -> str:
    """La riga dello z-score: il numero e cosa vuol dire per il Monte Carlo."""
    z = zs["z"]
    if not np.isfinite(z):
        return "—"
    if z < -1.96:
        testo = "perdite a grappoli: il drawdown vero può essere peggiore di quello simulato"
    elif z > 1.96:
        testo = "vincite e perdite si alternano più del caso"
    else:
        testo = "nessuna dipendenza fra trade consecutivi"
    nota = " (poco affidabile: meno di 300 trade)" if zs["n"] < 300 else ""
    return f"{_fmt(z, 2)} · {testo}{nota}"


def _pct(v, decimali=2):
    return "—" if v is None or not np.isfinite(v) else f"{_fmt(v * 100, decimali)} %"


MODELLI_MM = {"volatilita": "volatilità", "stop": "rischio fisso"}


def _modello(modello: str) -> str:
    """Da «volatilità» / «rischio fisso» alla misura dell'adattatore."""
    m = str(modello or "").strip().lower()
    if m.startswith("volatilit"):
        return "volatilita"
    if m in ("rischio fisso", "rischio_fisso", "stop", "fisso"):
        return "stop"
    raise ValueError(f"modello sconosciuto: {modello!r}. Usa «volatilità» oppure «rischio fisso».")


def _cifre_lotti(passo) -> int:
    """P4 (23/10/2026): i decimali con cui si scrivono i lotti, dal passo del
    symbol: 2 sul broker (passo 0,01, come prima), 3 su BTC (passo 0,001)."""
    if passo is None or not np.isfinite(float(passo)) or float(passo) <= 0:
        return 2
    return max(2, int(round(-np.log10(float(passo)))))


def _righe_mostrate(cal: pd.DataFrame, col_dd: str, dd_max: float) -> int:
    """Quante righe della calibrazione mostra la tabella della scelta: fino a 3 oltre la prima
    percentuale che supera il limite nel Monte Carlo, e almeno 6 (come la tabella stessa)."""
    sopra = cal[col_dd].to_numpy() > dd_max
    oltre = int(np.argmax(sopra)) if sopra.any() else len(cal)
    return min(len(cal), max(6, oltre + 3))


def _riga_ha_deciso(storia: dict, tab_is: pd.DataFrame, dd_max: float) -> str:
    """P1 (23/10/2026): la riga che dice chi ha deciso la percentuale, con le
    date del tratto peggiore della storia vera quando decide lei."""
    t = storia["tabella"]
    fm, f = storia["f_montecarlo"], storia["f"]
    lung = storia["lunghezza"]

    def tratto(riga):
        a = tab_is["entrata"].iloc[int(riga["inizio"])] if "entrata" in tab_is else tab_is.index[int(riga["inizio"])]
        b = tab_is["uscita"].iloc[int(riga["fine"])] if "uscita" in tab_is else tab_is.index[int(riga["fine"])]
        return f"dal {pd.Timestamp(a):%d/%m/%Y} al {pd.Timestamp(b):%d/%m/%Y}"

    def riga_di(x):
        return t.iloc[int(np.argmin(np.abs(t["f"].to_numpy() - x)))]

    if fm is None:
        return ("Ha deciso: il Monte Carlo (nessuna percentuale della griglia rispetta il limite nel caso "
                "sfortunato; la storia vera non è stata usata per scegliere).")
    if storia["deciso"] == "Monte Carlo":
        r = riga_di(fm)
        return (f"Ha deciso: il Monte Carlo. Con il {_fmt(fm * 100)} % anche la storia vera resta entro il limite: "
                f"il tratto peggiore di {lung} trade dell'in-sample ({tratto(r)}) arriva al "
                f"{_fmt(float(r['drawdown_storia']), 1)} % di drawdown, limite {_fmt(dd_max, 1)} %.")
    r = riga_di(fm)
    testo = (f"Ha deciso: la storia vera. Il Monte Carlo permetteva il {_fmt(fm * 100)} %, ma con quella "
             f"percentuale il tratto peggiore di {lung} trade dell'in-sample ({tratto(r)}) arriva al "
             f"{_fmt(float(r['drawdown_storia']), 1)} % di drawdown, oltre il limite del {_fmt(dd_max, 1)} %")
    if f is None:
        return testo + ": nessun gradino della griglia lo rispetta, nemmeno il più basso."
    r2 = riga_di(f)
    return (testo + f"; scesa al {_fmt(f * 100)} %, con cui il tratto peggiore ({tratto(r2)}) arriva al "
            f"{_fmt(float(r2['drawdown_storia']), 1)} %.")


def _avviso_kelly(f, k) -> str | None:
    """P2 (23/10/2026): la riga d'avviso quando la percentuale scelta supera
    il Kelly dell'in-sample. Avvisa e basta. None = niente da dire."""
    if f is None:
        return None
    if k is None or not np.isfinite(k):
        return ("Kelly dell'in-sample non calcolabile (servono trade vincenti e perdenti): il confronto con la "
                f"percentuale scelta ({_pct(f)}) non si può fare.")
    if k <= 0:
        return (f"Attenzione: il Kelly dell'in-sample è ≤ 0 ({_pct(k)}): sui trade in-sample nessuna percentuale "
                f"positiva è giustificata dal Kelly, e la percentuale scelta è {_pct(f)}.")
    if f > k:
        return (f"Attenzione: la percentuale scelta ({_pct(f)}) supera il Kelly dell'in-sample ({_pct(k)}).")
    return None


def _tabella_esposizione_fissa(fissa: pd.DataFrame, crypto: bool, cifre: int) -> pd.DataFrame:
    """P3: la tabellina da mostrare."""
    col = [c for c in fissa.columns if c.startswith("drawdown_p") and c != "drawdown_p50"][0]
    perc, fisso = float(fissa["esposizione"].iloc[0]), float(fissa["esposizione"].iloc[1])
    esp = [f"{_fmt(perc * 100)} % del conto a ogni trade",
           (f"{_fmt(fisso, 0)} $ di nozionale a ogni trade" if crypto
            else f"{_fmt(fisso, cifre)} lotti a ogni trade") if np.isfinite(fisso) else "—"]
    return pd.DataFrame({
        "Modo": ["Rischio in percentuale", "Stessa esposizione a ogni trade"],
        "Esposizione": esp,
        "Rendimento tipico (%)": fissa["rendimento_p50"].to_numpy(),
        "Drawdown tipico (%)": fissa["drawdown_p50"].to_numpy(),
        "Drawdown nel caso sfortunato, 1 su 20 (%)": fissa[col].to_numpy(),
    })


def money_management_trade(symbol: str, trades_is, df_is, trades_oos, df_oos, pip: float,
                           commission: float = 0.0, spread_pips: float = 0.0,
                           perc_sl: float = 90.0, n_barre_long: int = 25, n_barre_short: int = 25,
                           finestra: int = FINESTRA, lag: int = LAG, cartella="dati",
                           capitale: float = 10_000.0, drawdown_max_pct: float = 20.0,
                           anni: float = 1.0, simulazioni: int = SIMULAZIONI_MM,
                           titolo: str = "", modello: str = "volatilità",
                           storia: pd.DataFrame | None = None, leva: float | None = None) -> dict:
    """
    La sezione «Money management» con gli argomenti espliciti: la usa il
    notebook di ricerca (Sessione 5); il Lab passa da `money_management(s)`.
    Stesso codice per i due notebook.

    1. tabella dei trade (engine/mm_adattatore.py) in-sample e out-of-sample,
       per i DUE modelli: rischio fisso (stop + costi) e volatilita' (ATR
       giornaliero a 5 giornate chiuse; fase 3, docs/61 §14);
    2. calibrazione SOLO sull'in-sample, per ciascun modello: per ogni
       percentuale il Monte Carlo su `anni` di trade, scelta la piu' alta il
       cui drawdown al 95° percentile resta entro `drawdown_max_pct`; tabella
       di confronto dei due modelli (scelta V2 di Mattia);
    3. con il `modello` scelto e la sua percentuale: storia vera in-sample e
       out-of-sample, banda prevista, tabella di controllo.

    storia   lo storico completo (df) per calcolare l'ATR senza ripartire da
             zero all'inizio dell'out-of-sample. None = ogni parte per conto suo.
    leva     19/10/2026: la leva massima da usare (nozionale <= capitale x leva).
             None = la massima del symbol, come prima; un numero fra 1 e la
             massima concessa in Italia (engine/simboli.leva_scelta), oltre si ferma.

    Ritorna un dict: modello, confronto, f, calibrazione, rischio, sintesi,
    percorso_is, percorso_oos, banda, tabella_is, tabella_oos, kelly,
    optimal_f, n_trade, controllo, zscore, percentile_oos, capitale,
    drawdown_max_pct.
    """
    from . import money_management as mm
    from .indicatori import atr_giornaliero_chiuso
    from .mm_adattatore import limiti_symbol, tabella_trade, trade_per_anno

    if da_exchange(symbol):
        # 25/10/2026 (docs/71, strada D): sui symbol da exchange lo spread e' gia' nei pips netti dei
        # trade (CostoExtraPips), quindi gia' in «lordi - netti» del costo del rischio: aggiungerlo
        # qui lo conterebbe due volte
        spread_pips = 0.0
    scelto = _modello(modello)
    limiti = limiti_symbol(symbol, valore_leva=leva)       # si ferma subito se la leva non e' ammessa
    kw = dict(symbol=symbol, pip=pip, commission=commission, spread_pips=spread_pips,
              perc_sl=perc_sl, n_barre_long=n_barre_long, n_barre_short=n_barre_short,
              finestra=finestra, lag=lag, cartella=cartella)
    atr = atr_giornaliero_chiuso(storia) if storia is not None else None
    tabelle = {}
    for misura in MODELLI_MM:
        extra = dict(misura=misura, atr=atr)
        t_is = tabella_trade(trades_is, df_is, **kw, **extra)
        t_oos = tabella_trade(trades_oos, df_oos, **kw, **extra) if trades_oos is not None else t_is.iloc[:0]
        tabelle[misura] = (t_is, t_oos)
    tab_is, tab_oos = tabelle[scelto]
    if len(tab_is) < 5:
        raise ValueError(f"Servono almeno 5 trade in-sample per il money management (ce ne sono {len(tab_is)}).")
    freq = trade_per_anno(trades_is, df_is)                 # trade all'anno, in-sample
    n_trade = max(10, int(round(freq * float(anni))))
    dd_max = float(drawdown_max_pct)
    col_dd = f"drawdown_p{PERCENTILE_MM}"

    # --- la scelta della percentuale, per i due modelli (solo in-sample) ---
    calibrazioni = {}
    with _zitto():
        for misura, (t_is, _) in tabelle.items():
            calibrazioni[misura] = mm.calibra(t_is, capitale, dd_max, n_trade, percentile=PERCENTILE_MM,
                                              n_sim=simulazioni, limiti=limiti)
        # P1 (23/10/2026): la percentuale deve rispettare il limite anche sui tratti di storia vera
        # in-sample lunghi quanto l'orizzonte; per i due modelli, cosi' il confronto usa la stessa regola
        # (solo i gradini che servono: tutti quelli fino alla scelta del Monte Carlo e quelli che la tabella
        # mostra; la storia vera costa un Monte Carlo con un tratto per ogni trade in-sample)
        storie = {misura: mm.controlla_storia(tabelle[misura][0], capitale, dd_max, n_trade, fm, limiti=limiti,
                                              frazioni=c["f"].to_numpy()[:_righe_mostrate(c, col_dd, dd_max)])
                  for misura, (c, fm) in calibrazioni.items()}
    cal, f_mc = calibrazioni[scelto]
    storia_vera = storie[scelto]
    f = storia_vera["f"]
    dd_storia = np.full(len(cal), np.nan)                   # i gradini non calcolati restano vuoti
    dd_storia[:len(storia_vera["tabella"])] = storia_vera["tabella"]["drawdown_storia"].to_numpy()
    righe_conf = []
    for misura, (c, _) in calibrazioni.items():
        fm = storie[misura]["f"]
        riga = c.iloc[int(np.argmin(np.abs(c["f"].to_numpy() - fm)))] if fm is not None else None
        righe_conf.append({
            "Modello": MODELLI_MM[misura] + ("  ◀ in uso" if misura == scelto else ""),
            "Percentuale scelta (%)": fm * 100 if fm is not None else np.nan,
            "Ha deciso": storie[misura]["deciso"],
            "Drawdown tipico (%)": riga["drawdown_p50"] if riga is not None else np.nan,
            "Drawdown nel caso sfortunato, 1 su 20 (%)": riga[col_dd] if riga is not None else np.nan,
            "Rendimento tipico (%)": riga["rendimento_p50"] if riga is not None else np.nan,
            "Probabilità di chiudere in perdita (%)": riga["p_perdita"] if riga is not None else np.nan,
            "Trade saltati (%)": riga["saltati_pct"] if riga is not None else np.nan,
        })
    tab_confronto = pd.DataFrame(righe_conf)

    # --- il rischio dei trade (in-sample, modello in uso) --------------
    ok = np.isfinite(tab_is["rischio_pips"]) & (tab_is["rischio_pips"] > 0)
    r = (tab_is["pips_netti"] / tab_is["rischio_pips"])[ok].to_numpy()
    k = mm.kelly(r)
    f_opt, _ = mm.optimal_f(r)
    rischio_usd = (tab_is["rischio_pips"] * tab_is["valore_entrata"])[ok]
    zs = mm.zscore(tab_is["pips_netti"])               # fase 2 (docs/61 §13.2): solo avviso
    stop_acceso = any(bool(v and v > 0) for v in per_lato(perc_sl))     # 23/10/2026: anche per lato
    vol = scelto == "volatilita"
    unita = "ATR" if vol else "R"
    tab_rischio = pd.DataFrame({
        "": ["Trade in-sample",
             "Volatilità mediana per trade (ATR a 5 giornate, pips)" if vol
             else "Rischio mediano per trade (pips, stop + costi)",
             "Volatilità media per trade (pips)" if vol else "Rischio medio per trade (pips)",
             "Volatilità mediana con 1 lotto ($)" if vol else "Rischio mediano con 1 lotto ($)",
             f"Trade che hanno perso più di 1 {unita} (%)", f"Perdita peggiore (in {unita})",
             "Trade senza misura (saltati)",
             "Kelly (riferimento)", "Optimal f (riferimento)",
             "Trade a grappoli? (z-score)"],
        " ": [_fmt(len(tab_is)), _fmt(float(tab_is.loc[ok, "rischio_pips"].median()), 1),
              _fmt(float(tab_is.loc[ok, "rischio_pips"].mean()), 1), f"{_fmt(float(rischio_usd.median()))} $",
              _fmt(float((r < -1).mean() * 100), 1), _fmt(float(r.min()), 2) if r.size else "—",
              _fmt(int((~ok).sum())),
              _pct(k), _pct(f_opt), _lettura_z(zs)],
    })
    tab_cal = pd.DataFrame({
        "Rischio per trade (%)": cal["f"] * 100,
        "Drawdown tipico (%)": cal["drawdown_p50"],
        "Drawdown nel caso sfortunato, 1 su 20 (%)": cal[col_dd],
        "Drawdown della storia vera, tratto peggiore (%)": dd_storia,
        "Rendimento tipico (%)": cal["rendimento_p50"],
        "Probabilità di chiudere in perdita (%)": cal["p_perdita"],
        "Probabilità di restare bloccati (%)": cal["p_bloccato"],
        "Trade saltati (%)": cal["saltati_pct"],
        "Lotti ridotti dalla leva (%)": cal["leva_pct"],
    })
    if f is not None:
        i = int(np.argmin(np.abs(cal["f"].to_numpy() - f)))
        tab_cal.insert(0, "Scelta", ["◀" if j == i else "" for j in range(len(tab_cal))])
        oltre = int(np.argmax(cal[col_dd].to_numpy() > dd_max)) if (cal[col_dd] > dd_max).any() else len(cal)
        tab_cal_vista = tab_cal.iloc[: min(len(cal), max(oltre + 3, i + 3))]
    else:
        tab_cal_vista = tab_cal.head(6)

    suff = f" · {titolo}" if titolo else ""
    cifre = _cifre_lotti(limiti["passo"])                   # P4: BTC 0,006 lotti, non «0,01» o «0,00»
    if vol:
        misura_txt = ("modello a volatilità: lotti = capitale × percentuale ÷ (ATR giornaliero a 5 giornate chiuse × "
                      "valore di 1 pip); lo stop non entra nel calcolo.")
    elif stop_acceso:
        misura_txt = "rischio fisso: rischio = distanza dallo stop + costi."
    else:
        misura_txt = ("rischio fisso: rischio = stop di calcolo (stop spento: la soglia al 90° percentile, letta come "
                      "rischio tipico) + costi.")
    _nota(f"Capitale iniziale {_fmt(float(capitale), 0)} $ · drawdown accettato {_fmt(dd_max, 1)} % "
          f"su {_fmt(float(anni), 1)} anni = circa {n_trade} trade (dalla frequenza in-sample) · "
          f"caso sfortunato al {PERCENTILE_MM}° percentile · {_fmt(simulazioni)} storie simulate · "
          f"lotti da {_fmt(limiti['minimo'], cifre)} a passi di {_fmt(limiti['passo'], cifre)}, "
          f"massimo {_fmt(limiti['massimo'], 0)}, "
          f"leva massima {limiti['leva']} · in uso il {misura_txt}")
    _mostra(("I due modelli a confronto (Monte Carlo sull'in-sample, stessa regola sul drawdown)", tab_confronto),
            decimali={"Percentuale scelta (%)": 2, "Drawdown tipico (%)": 1,
                      "Drawdown nel caso sfortunato, 1 su 20 (%)": 1, "Rendimento tipico (%)": 1,
                      "Probabilità di chiudere in perdita (%)": 1, "Trade saltati (%)": 1})
    _nota("Il confronto usa solo l'in-sample. Scegli il modello qui, prima di guardare l'out-of-sample qui sotto: "
          "cambiarlo dopo averlo visto smette di essere una prova. Scegliere guardando questa tabella conta come una "
          "prova in più.")
    _mostra((f"Il rischio dei tuoi trade (in-sample, {MODELLI_MM[scelto]})", tab_rischio),
            (f"La scelta della percentuale (Monte Carlo e storia vera sull'in-sample, {MODELLI_MM[scelto]})",
             tab_cal_vista),
            decimali={"Rischio per trade (%)": 2, "Drawdown tipico (%)": 1,
                      "Drawdown nel caso sfortunato, 1 su 20 (%)": 1,
                      "Drawdown della storia vera, tratto peggiore (%)": 1, "Rendimento tipico (%)": 1,
                      "Probabilità di chiudere in perdita (%)": 1, "Probabilità di restare bloccati (%)": 1,
                      "Trade saltati (%)": 1, "Lotti ridotti dalla leva (%)": 1})
    riga_deciso = _riga_ha_deciso(storia_vera, tab_is, dd_max)
    _nota(riga_deciso)
    avviso_k = _avviso_kelly(f, k)                          # P2: avvisa e basta
    if avviso_k:
        _nota(avviso_k)
    tab_fissa = None
    if f is not None:                                        # P3: solo da leggere
        with _zitto():
            fissa = mm.confronto_esposizione_fissa(tab_is, capitale, f, n_trade, n_sim=simulazioni,
                                                   limiti=limiti, per_nozionale=da_exchange(symbol),
                                                   percentile=PERCENTILE_MM)
        tab_fissa = _tabella_esposizione_fissa(fissa, da_exchange(symbol), cifre)
        _mostra((f"Rischio in percentuale contro stessa esposizione a ogni trade, a parità di drawdown "
                 f"sfortunato (in-sample, {n_trade} trade)", tab_fissa),
                decimali={"Rendimento tipico (%)": 1, "Drawdown tipico (%)": 1,
                          "Drawdown nel caso sfortunato, 1 su 20 (%)": 1})
        _nota("Solo da leggere, non decide niente. Le due righe sono tarate sullo stesso drawdown sfortunato, "
              "sulle stesse storie simulate. "
              + ("«Stessa esposizione» vuol dire lo stesso valore in dollari a ogni trade, come nello stress test "
                 "in bp. " if da_exchange(symbol) else "«Stessa esposizione» vuol dire gli stessi lotti a ogni trade. ")
              + "L'esposizione fissa è continua: niente passo, lotto minimo o leva.")

    import matplotlib.pyplot as plt
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.4))
    x = cal["f"].to_numpy() * 100
    a1.plot(x, cal[col_dd], lw=2, label="drawdown nel caso sfortunato (1 su 20)")
    a1.plot(x, cal["drawdown_p50"], lw=1.2, label="drawdown tipico")
    a1.plot(x, dd_storia, lw=1.2, ls="--", color="#c26a1b",
            label="storia vera, tratto peggiore")
    a1.axhline(dd_max, color="red", ls="--", lw=1, label="il tuo limite")
    a2.plot(x, cal["rendimento_p50"], lw=2, color="#1f5f99", label="rendimento tipico")
    for ax in (a1, a2):
        if f is not None:
            ax.axvline(f * 100, color="black", lw=1.4, label=f"scelta: {_fmt(f * 100)} %")
        for nome, v, stile in (("Kelly", k, ":"), ("optimal f", f_opt, "-.")):
            if v is not None and np.isfinite(v) and 0 < v * 100 <= x.max():
                ax.axvline(v * 100, color="grey", ls=stile, lw=1.2, label=f"{nome}: {_fmt(v * 100)} %")
        ax.set_xlabel("rischio per trade (% del capitale)")
        ax.grid(alpha=.3)
        ax.legend(fontsize=8)
    a1.set_ylabel("drawdown (%)")
    a1.set_title(f"Drawdown su {n_trade} trade{suff}")
    a2.set_ylabel("rendimento (%)")
    a2.set_title(f"Rendimento tipico su {n_trade} trade{suff}")
    plt.tight_layout()
    plt.show()

    out = {"modello": MODELLI_MM[scelto], "confronto": tab_confronto,
           "f": f, "calibrazione": cal, "rischio": tab_rischio, "tabella_is": tab_is,
           "tabella_oos": tab_oos, "kelly": k, "optimal_f": f_opt, "n_trade": n_trade,
           "limiti": limiti, "sintesi": None, "percorso_is": None, "percorso_oos": None,
           "banda": None, "zscore": zs, "controllo": None, "percentile_oos": None,
           "capitale": float(capitale), "drawdown_max_pct": dd_max,
           "f_montecarlo": f_mc, "deciso": storia_vera["deciso"], "storia_vera": storia_vera,
           "riga_deciso": riga_deciso, "avviso_kelly": avviso_k, "esposizione_fissa": tab_fissa}
    if f is None:
        piu_bassa = _fmt(float(cal['f'].iloc[0]) * 100)
        storia_no = storia_vera["tabella"]["drawdown_storia"].iloc[0] > dd_max
        if f_mc is not None:
            causa = (f"Il Monte Carlo permetteva il {_fmt(f_mc * 100)} %, ma sulla storia vera nessuna percentuale "
                     f"della griglia, nemmeno la più bassa ({piu_bassa} %), tiene il tratto peggiore sotto il "
                     f"{_fmt(dd_max, 1)} %")
        elif storia_no:
            causa = (f"Nessuna percentuale della griglia (la più bassa è {piu_bassa} %) tiene il drawdown sotto il "
                     f"{_fmt(dd_max, 1)} %, né nel caso sfortunato del Monte Carlo né nel tratto peggiore della "
                     "storia vera")
        else:
            causa = (f"Nessuna percentuale della griglia (la più bassa è {piu_bassa} %) tiene il drawdown "
                     f"sfortunato del Monte Carlo sotto il {_fmt(dd_max, 1)} %")
        _riquadro(
            "Per ogni percentuale di rischio, migliaia di storie simulate con i trade in-sample, e la storia vera "
            "tagliata in tratti lunghi quanto l'orizzonte.",
            f"{causa}: con questi trade e questo capitale il limite che hai scelto non si può rispettare.",
            "Puoi alzare il drawdown accettato, il capitale o l'orizzonte, oppure tornare alla scheda strategia. "
            "Lo stress test (schermata 9) resta disponibile.")
        return out

    # --- la storia vera con la percentuale fissata ---------------------
    p_is = mm.ripercorri(tab_is, capitale, f, limiti)
    p_oos = mm.ripercorri(tab_oos, capitale, f, limiti) if len(tab_oos) else None
    s_is = mm.sintesi_percorso(p_is, capitale)
    s_oos = mm.sintesi_percorso(p_oos, capitale) if p_oos is not None else None
    voci = [("trade", "Trade", 0), ("fatti", "Trade fatti", 0), ("saltati", "Trade saltati", 0),
            ("leva_interviene", "Volte in cui interviene la leva", 0),
            ("capitale_iniziale", "Capitale iniziale ($)", 0), ("capitale_finale", "Capitale finale ($)", 0),
            ("rendimento_pct", "Rendimento (%)", 1), ("drawdown_max_pct", "Drawdown massimo (%)", 1),
            ("perdita_peggiore_pct", "Perdita peggiore su un trade (% del conto)", 2),
            ("lotti_min", "Lotti minimi", cifre), ("lotti_medi", "Lotti medi", cifre),
            ("lotti_max", "Lotti massimi", cifre)]
    sintesi = pd.DataFrame({
        "": [n for _, n, _ in voci],
        "In-sample (storia vera)": [_fmt(s_is[c], d) for c, _, d in voci],
        "Out-of-sample": [_fmt(s_oos[c], d) if s_oos else "—" for c, _, d in voci],
    })
    _mostra((f"Con il {_fmt(f * 100)} % di rischio per trade", sintesi))
    out.update(sintesi=sintesi, percorso_is=p_is, percorso_oos=p_oos)

    if p_oos is not None:
        with _zitto():
            bd = mm.banda(tab_is, capitale, f, len(tab_oos), n_sim=simulazioni, limiti=limiti)
        out["banda"] = bd
        fatti = p_oos["lotti"] > 0
        lotti0 = float(p_oos.loc[fatti, "lotti"].iloc[0]) if fatti.any() else 0.0
        fissi = capitale + np.cumsum(lotti0 * tab_oos["pips_netti"] * tab_oos["valore_uscita"])
        n = np.arange(len(tab_oos) + 1)
        fig, ax = plt.subplots(figsize=(11, 4.6))
        ax.fill_between(n, bd["p5"], bd["p95"], alpha=.2, label="banda prevista sull'in-sample (5°–95°)")
        ax.plot(n, bd["p50"], lw=1, color="grey", label="previsione tipica")
        ax.plot(n, np.r_[capitale, p_oos["capitale_dopo"].to_numpy()], lw=2, color="#1f5f99",
                label=f"out-of-sample, {_fmt(f * 100)} % per trade")
        ax.plot(n, np.r_[capitale, fissi.to_numpy()], lw=1.2, ls="--", color="#c26a1b",
                label=f"out-of-sample, {_fmt(lotti0, cifre)} lotti fissi")
        ax.axhline(capitale, color="black", lw=.8)
        ax.set_xlabel("trade out-of-sample")
        ax.set_ylabel("capitale ($)")
        ax.set_title(f"Il conto sui dati mai visti{suff}")
        ax.grid(alpha=.3)
        ax.legend(fontsize=8)
        plt.tight_layout()
        plt.show()
        capitale_live = s_oos["capitale_finale"]
        with _zitto():
            out["percentile_oos"] = mm.percentile_drawdown(tab_is, capitale, f, len(tab_oos),
                                                           s_oos["drawdown_max_pct"],
                                                           n_sim=simulazioni, limiti=limiti)
    else:
        _nota("Nessun trade out-of-sample: non c'è una storia da mostrare.")
        capitale_live = s_is["capitale_finale"]

    # --- la tabella di controllo per il live (fase 2, docs/61 §13.1) ------
    orizzonti = {f"{m} mesi": max(1, int(round(freq * m / 12))) for m in MESI_CONTROLLO}
    with _zitto():
        ctrl = mm.tabella_controllo(tab_is, capitale, f, orizzonti, n_sim=simulazioni, limiti=limiti)
    out["controllo"] = ctrl
    tab_ctrl = pd.DataFrame({
        "Dopo": ctrl["periodo"], "Trade (circa)": ctrl["trade"],
        "Drawdown tipico (%)": ctrl["drawdown_p50"],
        "Drawdown da allarme, 1 su 20 (%)": ctrl["drawdown_p95"],
        "Drawdown da fermarsi, 1 su 100 (%)": ctrl["drawdown_p99"],
        "Rendimento sfortunato, 1 su 20 (%)": ctrl["rendimento_p5"],
        "Rendimento tipico (%)": ctrl["rendimento_p50"],
        "Probabilità di essere in perdita (%)": ctrl["p_perdita"],
    })
    _mostra((f"Tabella di controllo per il live, con il {_fmt(f * 100)} % per trade", tab_ctrl),
            decimali={"Trade (circa)": 0, "Drawdown tipico (%)": 1, "Drawdown da allarme, 1 su 20 (%)": 1,
                      "Drawdown da fermarsi, 1 su 100 (%)": 1, "Rendimento sfortunato, 1 su 20 (%)": 1,
                      "Rendimento tipico (%)": 1, "Probabilità di essere in perdita (%)": 1})
    if out["percentile_oos"] is not None:
        mesi = (df_oos.index[-1] - df_oos.index[0]).total_seconds() / (365.25 * 86400) * 12
        q = out["percentile_oos"]
        zona = ("oltre la soglia «da fermarsi»" if q > 99 else
                "nella zona «da allarme»" if q > 95 else "dentro il normale")
        _nota(f"Dove cade l'out-of-sample: {len(tab_oos)} trade in circa {_fmt(mesi, 0)} mesi, drawdown massimo "
              f"{_fmt(s_oos['drawdown_max_pct'], 1)} %. Nelle storie simulate della stessa lunghezza un drawdown "
              f"uguale o più basso capita nel {_fmt(q, 1)} % dei casi: {zona} (allarme oltre il 95 %, "
              f"fermarsi oltre il 99 %).")

    rischio_tipico = float(tab_is.loc[ok, "rischio_pips"].median())
    valore_tipico = float(tab_is.loc[ok, "valore_entrata"].median())
    lotti_es, _ = mm.lotti_rischio_fisso(capitale_live, f, rischio_tipico, valore_tipico,
                                         {k2: v for k2, v in limiti.items() if k2 != "leva"})
    nome_misura = "ATR giornaliero a 5 giornate chiuse" if vol else "rischio del trade"
    parola = "un ATR" if vol else "un rischio"
    _nota(f"Per il live: lotti = capitale × {_fmt(f * 100)} % ÷ ({nome_misura} in pips × valore di 1 pip con "
          f"1 lotto), arrotondati per difetto al passo di {_fmt(limiti['passo'], cifre)}. Esempio: con "
          f"{_fmt(capitale_live, 0)} $ e {parola} di {_fmt(rischio_tipico, 1)} pips "
          f"({_fmt(valore_tipico)} $ per pip) sono {_fmt(lotti_es, cifre)} lotti. Sotto {_fmt(limiti['minimo'], cifre)} lotti il "
          f"trade si salta; il nozionale non supera {limiti['leva']} volte il capitale.")
    _riquadro(
        "Quanto rischiare su ogni trade, in percentuale del conto. Due modi di misurare il rischio: «rischio fisso» "
        "guarda dove sta lo stop, «volatilità» guarda quanto si è mosso il mercato negli ultimi 5 giorni (ATR) e si "
        "ferma da solo quando è troppo agitato per il capitale. Per ciascuno lo strumento prova ogni percentuale su "
        "migliaia di storie costruite con i soli trade in-sample, con il conto che cresce e cala e i lotti "
        "ricalcolati a ogni trade, e sceglie la più alta che resta sotto il drawdown che hai detto di accettare. Poi, "
        "con il modello in uso e la sua percentuale già fissata, mostra cosa avrebbe fatto il conto sui dati mai visti.",
        "Kelly e optimal f sono il bordo del precipizio: la percentuale che col senno di poi avrebbe reso di più, "
        "e oltre la quale il drawdown esplode. Stare molto sotto è normale. Nel grafico del conto guarda se la linea "
        "blu resta dentro la banda prevista: fuori dal basso vuol dire che i dati mai visti sono andati peggio del "
        "piano. La linea tratteggiata mostra lo stesso periodo con i lotti fermi a quelli del primo trade.",
        "Annota la percentuale scelta e non cambiarla dopo aver visto l'out-of-sample: se la ritocchi finché il conto "
        "ti piace, smette di essere una prova. Dal vivo tieni accanto la tabella di controllo: se dopo 3, 6 o 12 mesi "
        "il drawdown supera la colonna «da allarme» riduci o metti in pausa, oltre «da fermarsi» fermati e ristudia "
        "la strategia. Poi vai alla schermata 8 (verifica dei trade) e alla 9 (stress test). "
        "Lo stress test prende capitale e drawdown da qui; i suoi lotti consigliati sono fissi e rispondono a "
        "un'altra domanda: quanti lotti, sempre uguali, per non superare quel drawdown su tutto lo storico.")
    _nota("Limiti da conoscere: le storie simulate trattano i trade come indipendenti; con lo stop spento il rischio "
          "è quello tipico, non il massimo; un trade può perdere più di 1 R (gap, stop non attivo sulla barra "
          "d'ingresso); i costi di swap non sono nel backtest.")
    return out


def money_management(s: Sessione, capitale: float = 10_000.0, drawdown_max_pct: float = 20.0,
                     anni: float = 1.0, modello: str = "volatilità",
                     leva: float | None = None) -> dict:
    """
    Schermata 7. Quanto rischiare su ogni trade (rischio fisso in percentuale,
    docs/61): la percentuale si sceglie sull'in-sample con la tua regola sul
    drawdown, poi si guarda una volta l'out-of-sample.

    capitale           il conto con cui partiresti, in dollari
    drawdown_max_pct   il calo massimo dal massimo che accetti, in %
    anni               su quanto tempo vale la regola del drawdown
    modello            «volatilità» (predefinito, decisione di Mattia del 16/10)
                       oppure «rischio fisso»: i due si confrontano comunque
                       sull'in-sample
    leva               19/10/2026: la leva massima da usare. None o 0 = la massima
                       concessa in Italia per il symbol (engine/simboli.py);
                       oltre quella si ferma con un errore

    Ritorna il dict di `money_management_trade`, salvato anche in `s.mm`.
    """
    s._serve("oos", "6 · Scheda strategia")
    if leva is not None and float(leva) == 0:
        leva = None
    u = s.uscite
    out = money_management_trade(
        s.symbol, s.trades_is, s.df_is, s.trades_oos, s.df_oos, pip=s.fs.pip_size,
        commission=s.fs.commission or 0.0, spread_pips=s.spread_pips, perc_sl=u["perc_sl"],
        n_barre_long=u["n_barre_long"], n_barre_short=u["n_barre_short"], finestra=FINESTRA,
        lag=LAG, cartella=s.cartella, capitale=capitale, drawdown_max_pct=drawdown_max_pct,
        anni=anni, titolo=f"{s.symbol} · {s.filtro or 'sistema base'}", modello=modello, storia=s.df,
        leva=leva)
    s.mm = out
    s.tabelle["money_management"] = {"rischio": out["rischio"], "sintesi": out["sintesi"]}
    return out


# ========================================================================
# 9 · Stress test
# ========================================================================

def passo_lotti(symbol: str) -> float:
    """
    Il passo a cui lo stress test arrotonda i lotti consigliati (19/10/2026):
    0,01 per i symbol del broker, come prima; il passo dell'exchange per i
    symbol da exchange (engine/simboli.py, LOTTI_EXCHANGE).
    """
    if da_exchange(symbol):
        from .simboli import lotti_symbol
        return float(lotti_symbol(symbol)["passo"])
    return 0.01


def _cambio_ultima_barra(s: Sessione) -> float | None:
    """
    Indici e metalli non quotati in USD (oggi DE40, in EUR): il cambio della
    loro valuta in dollari all'ultima barra, dal CSV `{valuta}USD_M15.csv`
    della stessa cartella. None per tutti gli altri symbol. 11/10/2026, come
    la cella dei lotti del notebook principale.
    """
    info = info_symbol(s.symbol)
    if info["classe"] not in ("indici", "metalli") or info["valuta"] == "USD":
        return None
    f = os.path.join(s.cartella, f"{info['valuta']}USD_M15.csv")
    with _zitto():
        cambi = to_utc_index(pd.read_csv(f, index_col="Date"), REGOLA_FUSO,
                             on_dst_gap="drop", verbose=False)
    return float(cambi["Close"].loc[:s.df.index[-1]].iloc[-1])


def stress_test(s: Sessione, drawdown_max_usd: float = 10_000.0,
                simulazioni: int = 20_000) -> dict:
    """
    Schermata 9. Monte Carlo sui trade della strategia scelta (in-sample +
    out-of-sample), tabella di controllo per il live e lotti consigliati.

    drawdown_max_usd   il drawdown massimo che accetti sul conto, in dollari.
                       16/10/2026 (docs/61 §13.3, scelta C1 di Mattia): se la
                       schermata 7 e' stata eseguita su questa scheda, il
                       drawdown viene da li' (capitale x drawdown %) e questo
                       valore non si usa; altrimenti si usa questo, come prima.

    23/10/2026: sui symbol da exchange Monte Carlo, drawdown e tabella di
    controllo sono in BP per trade (lo stesso valore in dollari a ogni
    trade), e i lotti consigliati vengono dal drawdown in bp e dal prezzo
    dell'ultima barra (1 bp con 1 lotto = prezzo / 10.000 $). Sul broker
    tutto in pips, come prima.

    Ritorna {"controllo": tabella, "montecarlo": dict, "sizing": dict,
    "drawdown_max_usd", "unita", e sulle crypto "prezzo" e "data_prezzo"}.
    """
    s._serve("oos", "6 · Scheda strategia")
    if s.mm is not None:
        drawdown_max_usd = s.mm["capitale"] * s.mm["drawdown_max_pct"] / 100.0
        origine = (f"dalla schermata 7: {_fmt(s.mm['capitale'], 0)} $ × {_fmt(s.mm['drawdown_max_pct'], 1)} % "
                   f"= {_fmt(drawdown_max_usd, 0)} $")
    else:
        origine = f"dal campo di questa schermata: {_fmt(float(drawdown_max_usd), 0)} $ (schermata 7 non eseguita)"
    u = "bp" if s.da_exchange else "pips"                 # 23/10/2026: bp sulle crypto
    if s.da_exchange:
        valori = bp_per_dataset(s.trades_is, s.trades_oos,
                                s.fs.pip_size, s.fs.commission or 0.0, dataset="FULL")
    else:
        valori = pips_per_dataset(s.trades_is, s.trades_oos,
                                  s.fs.pip_size, s.fs.commission or 0.0, dataset="FULL")
    prezzo, data_prezzo = float(s.df["Close"].iloc[-1]), s.df.index[-1]
    with _zitto():
        orizzonti = tuple(h for h in ORIZZONTI_MC if h <= max(len(valori), 10))
        yard = yardstick(valori, orizzonti=orizzonti, n_sim=simulazioni)
        mc = montecarlo_completo(valori, n_sim=simulazioni)
        if s.da_exchange:
            valore_unita = prezzo * float(info_symbol(s.symbol)["contratto"]) / 10_000.0   # 1 bp con 1 lotto
        else:
            valore_unita = valore_pip_lotto(s.symbol, s.fs.pip_size, prezzo=prezzo,
                                            cambio=_cambio_ultima_barra(s))
        passo = passo_lotti(s.symbol)
        sz = sizing(mc, drawdown_max_usd, valore_unita, percentile=95, passo=passo)
    cifre_lotti = _cifre_lotti(passo)                      # BTC: 0,006 lotti, non «0,01»

    controllo = pd.DataFrame({
        "Dopo quanti trade": [int(h) for h in yard.index],
        f"Risultato tipico ({u})": yard["pnl_p50"].to_numpy(),
        f"Drawdown tipico ({u})": yard["dd_p50"].to_numpy(),
        f"Drawdown da allarme ({u})": yard["dd_p95"].to_numpy(),
        "Probabilità di essere in perdita (%)": yard["p_pnl_negativo"].to_numpy(),
    })
    voci = ["Trade simulati", "Drawdown realmente visto", "Drawdown tipico",
            "Drawdown nel caso sfortunato (1 su 20)", "Probabilità di chiudere in perdita",
            f"Valore di 1 {'bp' if s.da_exchange else 'pip'} con 1 lotto", "Drawdown che accetti",
            "Lotti consigliati"]
    valori_txt = [_fmt(mc["n_trade"]), f"{_fmt(mc['dd_reale'], 0)} {u}", f"{_fmt(mc['dd_p50'], 0)} {u}",
                  f"{_fmt(mc['dd_p95'], 0)} {u}", f"{_fmt(mc['p_pnl_negativo'], 1)} %",
                  f"{_fmt(valore_unita)} $", f"{_fmt(float(drawdown_max_usd), 0)} $",
                  _fmt(sz["lotti_consigliati"], cifre_lotti)
                  + (f" ({info_symbol(s.symbol)['valuta']}: 1 lotto = 1 moneta)" if s.da_exchange else "")]
    if s.da_exchange:
        voci.insert(5, "Prezzo usato per i lotti")
        valori_txt.insert(5, f"{_fmt(prezzo)} $, chiusura dell'ultima barra ({data_prezzo:%d/%m/%Y %H:%M} UTC)")
    sintesi = pd.DataFrame({"": voci, " ": valori_txt})
    s.tabelle["stress"] = {"controllo": controllo, "sintesi": sintesi}
    _nota(f"Drawdown che accetti, {origine}.")
    if s.da_exchange:
        _nota("Sulle crypto il Monte Carlo lavora sui bp netti per trade: è come mettere lo stesso valore in "
              "dollari a ogni trade, così un trade dell'1 % pesa uguale a qualunque prezzo. I lotti consigliati "
              f"vengono dal drawdown sfortunato in bp e dal prezzo dell'ultima barra dei dati ({_fmt(prezzo)} $): "
              "il tool non legge il prezzo dal vivo.")
    _mostra(("Stress test · in sintesi", sintesi), ("Tabella di controllo per il live", controllo),
            decimali={"Dopo quanti trade": 0, f"Risultato tipico ({u})": 0, f"Drawdown tipico ({u})": 0,
                      f"Drawdown da allarme ({u})": 0, "Probabilità di essere in perdita (%)": 1})
    grafici_montecarlo(valori, mc=mc, orizzonti=orizzonti, titolo=f"{s.symbol} · {s.filtro or 'sistema base'}",
                       unita=u)
    import matplotlib.pyplot as plt
    plt.show()

    _riquadro(
        "Migliaia di storie alternative, costruite ripescando a caso i trade della strategia. Ogni linea del "
        "ventaglio è una sequenza che poteva capitare. Il backtest te ne mostra una sola; qui ne vedi migliaia.",
        "Guarda il drawdown nel caso sfortunato: è quello su cui dimensionare il conto, non quello del backtest. "
        "I lotti consigliati sono calcolati perché quel drawdown resti dentro la cifra che hai detto di accettare.",
        "Dal vivo usa la tabella di controllo: se dopo 20 trade il drawdown supera quello «da allarme» della riga 20, "
        "la strategia sta facendo qualcosa che nelle simulazioni è capitato meno di 1 volta su 20. "
        "È il segnale per ridurre i lotti o fermarsi.")
    _nota("Limite da conoscere: le simulazioni trattano i trade come indipendenti e non possono inventare "
          "un trade peggiore del peggiore già visto. Se le perdite arrivano a grappoli, la realtà può essere un po' più dura.")
    out = {"controllo": controllo, "montecarlo": mc, "sizing": sz,
           "drawdown_max_usd": float(drawdown_max_usd), "unita": u}
    if s.da_exchange:
        out.update(prezzo=prezzo, data_prezzo=data_prezzo)
    return out


# ========================================================================
# 8 · Verifica i trade (in un modulo a parte: engine/vetrina_verifica.py)
# ========================================================================
# In fondo, perche' quel modulo usa gli strumenti di presentazione definiti qui.
from .vetrina_verifica import (indicatori_disponibili, lente, registro_trade,  # noqa: E402
                               verifica_trade)
