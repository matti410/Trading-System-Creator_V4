"""
Vetrina — la «facciata» del notebook slim (6/10/2026).

COSA E'
-------
Sette funzioni, una per schermata del notebook di presentazione. Ognuna
richiama i moduli che esistono gia' (event study, ricerca delle uscite,
ricerca dei filtri, due meta', Out-of-Sample, Monte Carlo) e ne mostra il
risultato con un riquadro «Come leggerlo» scritto per un trader.

    s = prepara("EURUSD", H=25)                              1 · Configura
    esplora(s)                                               2 · Esplora
    classifiche(s)                                           3 · Scegli i trigger
    scegli_trigger(s, long=[...], short=[...])
    imposta_uscite(s, barre_long=10, barre_short=18, sl=90)  4 · Imposta le uscite
    trova_strategia(s)                                       5 · Trova la strategia
    scheda(s, filtro="F1, F2")                               6 · Scheda strategia
    verifica_trade(s)                                        7 · Verifica i trade
    lente(s, numero=12, indicatori="ema20, ema50")           (engine/vetrina_verifica.py)
    stress_test(s, drawdown_max_usd=10_000)                  8 · Stress test

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

import numpy as np
import pandas as pd

from . import registry as reg
from .broker_tz_diagnostic import to_utc_index
from .costi import parametri_backtest
from .due_meta import due_meta
from .equity_plot import plot_equity
from .event_study import deduci_pip, run_event_study
from .exit_search_bt import barre_per_lato, run_exit_search_bt
from .filter_search_bt import BASELINE, run_filter_search_bt
from .confidenza import congela_filtro
from .giudizio import CAMPIONE_CORTO, DA_VALUTARE, scheda_strategia, soglia_rumore
from .indicatori import aggiungi_indicatori
from .livelli import quarantena_cached
from .metriche import pips_per_trade
from .montecarlo import (grafici_montecarlo, montecarlo_completo,
                         pips_per_dataset, sizing, valore_pip_lotto, yardstick)
from .quarantena import verifica_indice_utc
from .splitting import split_is_oos


# ========================================================================
# Parametri fissi della vetrina (gli stessi del notebook di lavoro)
# ========================================================================

# Spread in pips del conto IC Markets Standard, per gli strumenti i cui dati
# non lo contengono. `rollover` e' una stima (vedi 93_QUARANTENA_TRADE_E_COSTI).
SPREAD_LISTINO_PIPS = {
    "EURUSD": {"normale": 0.8, "rollover": 1.5},
}

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


# ========================================================================
# La sessione
# ========================================================================

class Sessione:
    """Dati, costi e scelte, da una schermata all'altra. La crea `prepara`."""

    def __init__(self):
        self.symbol = None
        self.H = None
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
        self.tabelle = {}

    def __repr__(self):
        return f"<Sessione {self.symbol} · H={self.H}>"

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
            pip = deduci_pip(float(close.mean()))
            in_pips = punti * _punto_da_prezzi(close) / pip
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
    # sono combinazioni gia' scelte, non trigger da esplorare
    return [n for n in reg.list_entries(direzione)
            if n not in esclusi and not ("+" in n and n.split("+")[0] in tutte)]


def _tutti_i_filtri() -> list[str]:
    return reg.list_filters(0) + reg.list_filters(1) + reg.list_filters(-1)


def prepara(symbol: str = "EURUSD", H: int = 25, quota_in_sample: float = 0.8,
            cartella: str = ".") -> Sessione:
    """
    Schermata 1. Carica lo storico M15 dal CSV, calcola costi e indicatori,
    divide in-sample / out-of-sample e carica le condizioni dal registro.

    symbol            nome dello strumento: serve il file `{symbol}_M15.csv`
    H                 orizzonte di osservazione, in barre (unico per long e short)
    quota_in_sample   parte iniziale dello storico usata per costruire (0.8 = 80%)

    Ritorna la sessione da passare alle schermate successive.
    """
    H = int(H)
    if H < 1:
        raise ValueError("H deve essere almeno 1 barra.")
    percorso = os.path.join(cartella, f"{symbol}_M15.csv")
    if not os.path.exists(percorso):
        raise FileNotFoundError(f"Non trovo {percorso}: serve il CSV dello storico M15 di {symbol}.")

    s = Sessione()
    s.symbol, s.H = symbol, H
    with _zitto():
        df = pd.read_csv(percorso, index_col="Date")
        df = to_utc_index(df, REGOLA_FUSO, on_dst_gap="drop")
        verifica_indice_utc(df)
        sp = spread_in_pips(symbol, df)
        costi = parametri_backtest(symbol, bars=df, valuta_conto="USD", usa_mt5=False,
                                   spread_pips=sp["normale"], commissione_rt=0.0)
        costi["cash"] = CASH
        costi["spread_rollover_pips"] = sp["rollover"]
        df = aggiungi_indicatori(df)
        s.df_is, s.df_oos = split_is_oos(df, is_ratio=quota_in_sample)
    s.df, s.costi = df, costi
    s.pip = deduci_pip(float(df["Close"].mean()))
    s.spread_pips, s.spread_rollover_pips, s.fonte_spread = sp["normale"], sp["rollover"], sp["fonte"]
    _registra_condizioni()

    def giorno(t):
        return pd.Timestamp(t).strftime("%d/%m/%Y")

    riepilogo = pd.DataFrame({
        "": ["Strumento", "Barre M15", "Periodo", "In-sample (per costruire)",
             "Out-of-sample (mai visto)", "Costo per trade", "Costo nel rollover",
             "Orizzonte di osservazione", "Trigger disponibili", "Filtri disponibili"],
        " ": [symbol, _fmt(len(df)), f"{giorno(df.index[0])} – {giorno(df.index[-1])}",
              f"{_fmt(len(s.df_is))} barre, fino al {giorno(s.df_is.index[-1])}",
              f"{_fmt(len(s.df_oos))} barre, dal {giorno(s.df_oos.index[0])}",
              f"{_fmt(sp['normale'])} pips di spread, nessuna commissione ({sp['fonte']})",
              (f"{_fmt(sp['rollover'])} pips" if sp["rollover"] is not None else "come il resto della giornata"),
              f"{H} barre ({_fmt(H * 15 / 60, 1)} ore)",
              f"{len(_trigger_candidati(1))} long · {len(_trigger_candidati(-1))} short",
              _fmt(len(_tutti_i_filtri()))],
    })
    s.tabelle["riepilogo"] = riepilogo
    _mostra(("Il tuo laboratorio", riepilogo))
    _riquadro(
        "Lo storico su cui lavori, diviso in due: l'in-sample serve a costruire la strategia, "
        "l'out-of-sample resta chiuso in cassaforte fino alla fine.",
        "Qui non c'è ancora niente da giudicare. Controlla solo che strumento, periodo e costi "
        "siano quelli che ti aspetti: ogni risultato che vedrai è già al netto di questi costi.",
        "Vai alla schermata 2 per vedere come si muove il prezzo dopo ogni trigger.")
    return s


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


def esplora(s: Sessione, quanti: int = 5):
    """
    Schermata 2. Misura, per ogni trigger del registro, come si muove in
    media il prezzo nelle H barre dopo il segnale (`run_event_study`,
    sull'in-sample) e disegna le curve dei `quanti` piu' solidi per lato.

    Ritorna l'oggetto EventStudy (anche in `s.ev`).
    """
    s._serve("df_is", "1 · Configura")
    candidati = _trigger_candidati()
    with _zitto():
        s.ev = run_event_study(s.df_is, entry_names=candidati, horizon=s.H,
                               min_trades=MIN_TRIGGER, verbose=False)
    misurati = len(s.ev.sintesi)
    _nota(f"{misurati} trigger misurati su {len(candidati)} "
          f"(gli altri scattano meno di {MIN_TRIGGER} volte: troppo pochi per fidarsi della media).")
    for direzione, nome in ((1, "LONG"), (-1, "SHORT")):
        lato = _favorevoli(s, direzione)
        if lato.empty:
            continue
        _grafico_curve(s, list(lato["candidato"].head(quanti)), nome.lower())
    _riquadro(
        "Ogni linea è un trigger: quanto guadagna in media un trade aperto su quel segnale, in pips e prima "
        "dei costi, barra dopo barra. Vale la stessa regola per long e short: la linea sale quando il trade "
        "guadagna. Per uno short «sale» vuol dire che il prezzo sta scendendo. "
        "La tratteggiata è quello che otterresti entrando a caso nella stessa direzione.",
        "Un trigger interessante sta sopra lo zero e sopra la tratteggiata, e ci arriva presto. "
        "Una linea che scende sotto lo zero è un segnale che in media ti porta dalla parte sbagliata. "
        "Guarda anche dove la curva smette di salire: è la durata naturale del movimento, "
        "ti servirà per scegliere dopo quante barre uscire.",
        "Vai alla schermata 3: trovi gli stessi trigger in classifica, con i numeri.")
    return s.ev


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
    Schermata 3 (prima parte). Le due classifiche dei trigger, LONG e SHORT,
    lette dalla sintesi dell'event study e ordinate per solidita'.

    Ritorna {"long": tabella, "short": tabella}.
    """
    s._serve("ev", "2 · Esplora")
    out, da_mostrare = {}, []
    for direzione, nome in ((1, "long"), (-1, "short")):
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


def scegli_trigger(s: Sessione, long=None, short=None) -> None:
    """
    Schermata 3 (seconda parte). Registra la scelta dei trigger.

    long / short   un nome, piu' nomi separati da virgola o una lista di nomi
                   (lavorano in OR); None o vuoto = quel lato non opera.
                   Almeno un lato deve essere indicato.
    """
    s._serve("ev", "2 · Esplora")
    from entry_composita import risolvi_scelta

    def lista(x):
        # un nome, piu' nomi separati da virgola, oppure una lista di nomi
        if x is None:
            return ()
        if isinstance(x, str):
            x = x.split(",")
        return tuple(n.strip() for n in x if isinstance(n, str) and n.strip())

    tl, ts = lista(long), lista(short)
    if not tl and not ts:
        raise ValueError("Scegli almeno un trigger, long o short.")
    with _zitto():
        s.entry_long = risolvi_scelta(list(tl), lato="long") if tl else None
        s.entry_short = risolvi_scelta(list(ts), lato="short") if ts else None
    s.trigger_long, s.trigger_short = tl, ts
    # una scelta nuova invalida tutto cio' che viene dopo
    s.uscite = s.es = s.fs = s.dm = s.oos = None
    s.sopravvissuti, s.filtro = [], None

    scelta = pd.DataFrame({
        "Lato": ["LONG", "SHORT"],
        "Trigger scelti": [" oppure ".join(tl) if tl else "nessuno (lato spento)",
                           " oppure ".join(ts) if ts else "nessuno (lato spento)"],
    })
    _mostra(("La tua scelta", scelta))
    _nota("Si tiene una posizione alla volta. Se a posizione aperta scatta un trigger del lato opposto, "
          "la posizione si chiude e si apre quella contraria.")


# ========================================================================
# 4 · Imposta le uscite
# ========================================================================

def _kw_motore(s: Sessione) -> dict:
    """I parametri comuni a ogni backtest della sessione (uscite + costi)."""
    u = s.uscite
    return dict(n_barre=u["n_barre"], n_barre_long=u["n_barre_long"],
                n_barre_short=u["n_barre_short"], perc_sl=u["perc_sl"],
                perc_tp=u["perc_tp"], finestra=FINESTRA, lag=LAG,
                inverti_su_opposto=True, **s.costi)


def _nome_sistema(riga) -> str:
    ha_long = isinstance(riga["entry_long"], str)
    ha_short = isinstance(riga["entry_short"], str)
    if ha_long and ha_short:
        return "Long + Short"
    return "Solo long" if ha_long else "Solo short"


def imposta_uscite(s: Sessione, barre_long: int | None = None,
                   barre_short: int | None = None, sl: float = 90.0,
                   tp: float = 0.0, regola_uscita: str | None = None) -> pd.DataFrame:
    """
    Schermata 4. Fissa le uscite e prova il sistema base sull'in-sample
    (`run_exit_search_bt`), confrontando solo long, solo short ed entrambi.

    barre_long / barre_short   dopo quante barre il trade si chiude comunque
                               (None = l'orizzonte H)
    sl / tp                    percentile dello stop e del target adattivi
                               (0 = spento); gli stessi per i due lati
    regola_uscita              etichetta di una coppia di regole di uscita del
                               registro (`engine.registry.list_exit_pairs`).
                               Predisposta: nella versione slim resta None.

    Ritorna la tabella del confronto.
    """
    if s.entry_long is None and s.entry_short is None:
        raise RuntimeError("Manca un passaggio: esegui prima la schermata «3 · Scegli i trigger».")
    bl = s.H if barre_long is None else int(barre_long)
    bs = s.H if barre_short is None else int(barre_short)
    barre_per_lato(bl, bl, bs)                     # controllo dei valori
    for nome, v in (("sl", sl), ("tp", tp)):
        if v is None or not (0 <= float(v) < 100):
            raise ValueError(f"{nome} è un percentile: da 0 (spento) a 99.")
    s.uscite = dict(n_barre=bl, n_barre_long=bl, n_barre_short=bs,
                    perc_sl=float(sl), perc_tp=float(tp), regola=regola_uscita)
    s.fs = s.dm = s.oos = None
    s.sopravvissuti, s.filtro = [], None

    entrambi = s.entry_long is not None and s.entry_short is not None
    with _zitto():
        s.es = run_exit_search_bt(
            s.df_is,
            entry_cols_long=[s.entry_long, None] if entrambi else [s.entry_long],
            entry_cols_short=[s.entry_short, None] if entrambi else [s.entry_short],
            exit_rule_pairs=regola_uscita, verbose=False, **_kw_motore(s))

    r = s.es.risultati.copy()
    r["Sistema"] = r.apply(_nome_sistema, axis=1)
    ordine = {"Long + Short": 0, "Solo long": 1, "Solo short": 2}
    r = r.sort_values("Sistema", key=lambda c: c.map(ordine)).reset_index(drop=True)
    tabella = pd.DataFrame({
        "Sistema": r["Sistema"],
        "Trade": r["trades"].astype(int),
        "Guadagno medio netto per trade (pips)": r["avg_trade_netto"],
        "Trade vincenti (%)": r["win_rate_pct"],
        "Solidità": r["t_stat"],
        "Durata media (barre)": r["durata_media"],
    })
    s.tabelle["uscite"] = tabella

    def soglia(p):
        return "spento" if not p else f"{_fmt(p, 0)}° percentile"
    _nota(f"Uscita a tempo: long dopo {bl} barre, short dopo {bs} barre · "
          f"stop {soglia(sl)} · target {soglia(tp)} · chiusura e inversione sul segnale opposto.")
    _mostra(("Il sistema base (in-sample, al netto dei costi)", tabella),
            decimali={"Durata media (barre)": 1})

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 4.6))
    for _, riga in r.iterrows():
        tr = s.es.trades(riga["combinazione"])
        if len(tr) == 0:
            continue
        _, netti = pips_per_trade(tr, s.pip, s.costi["commission"])
        curva = pd.Series(netti.to_numpy(), index=pd.DatetimeIndex(tr["ExitTime"])).sort_index().cumsum()
        ax.plot(curva.index, curva.to_numpy(), lw=2.0 if riga["Sistema"] == "Long + Short" else 1.2,
                label=riga["Sistema"])
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("pips netti accumulati")
    ax.set_title("Sistema base: somma dei pips netti, trade dopo trade (in-sample)")
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
        "una certa regolarità, non per un solo periodo fortunato. Confronta le tre righe: a volte un lato "
        "da solo rende meglio dei due insieme.",
        "Se vuoi, cambia barre o percentili e riesegui la cella. Quando il sistema base ti convince, "
        "vai alla schermata 5 per cercare un filtro che lo migliori.")
    return tabella


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


def trova_strategia(s: Sessione, quanti: int = 8) -> pd.DataFrame:
    """
    Schermata 5. Prova tutti i filtri del registro sul sistema base
    (`run_filter_search_bt`, in-sample) e verifica i promossi sulle due meta'
    dello storico (`due_meta`). Mostra l'imbuto e la classifica.

    Ritorna la classifica dei filtri. I sopravvissuti sono in `s.sopravvissuti`.
    """
    s._serve("uscite", "4 · Imposta le uscite")
    filtri = _tutti_i_filtri()
    kw = _kw_motore(s)
    with _zitto():
        s.fs = run_filter_search_bt(
            s.df_is, entry_long=s.entry_long, entry_short=s.entry_short,
            exit_rule_pair=s.uscite["regola"], filtri=filtri,
            min_trades_giudizio=MIN_TRADE_GIUDIZIO, p_max=P_MAX, alpha=ALPHA,
            verbose=False, **kw)
    r = s.fs.risultati
    prove = r[r["filtro"] != BASELINE]
    promossi = prove.loc[prove["esito"].isin([DA_VALUTARE, CAMPIONE_CORTO]), "filtro"].to_list()

    verdetti = {}
    s.dm = None
    if promossi:
        solo_costi = {k: kw[k] for k in ("perc_sl", "perc_tp", "finestra", "lag", "spread",
                                         "commission", "cash", "spread_rollover_pips")}
        with _zitto():
            s.dm = due_meta(s.df_is, s.fs, [None, *promossi], verbose=False, **solo_costi)
        verdetti = s.dm.tabella.set_index("filtro")["verdetto"].to_dict()
    s.sopravvissuti = [f for f in promossi if verdetti.get(f) == "regge"]
    s.filtro = s.oos = s.trades_is = s.trades_oos = None
    s.filtri_scelti = []

    # --- imbuto ---------------------------------------------------------
    tappe = [("Filtri provati (una coppia long/short conta per uno)", len(prove)),
             ("Migliorano davvero il sistema base", len(promossi)),
             ("Reggono su entrambe le metà dello storico", len(s.sopravvissuti))]
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
    righe = [{"Filtro": "Sistema base (nessun filtro)", "Trade": int(base["trades"]),
              "Guadagno medio netto per trade (pips)": base["avg_trade_netto"],
              "Miglioramento sul sistema base (pips)": np.nan,
              "Solidità del miglioramento": np.nan,
              "Prima prova": "—", "Seconda prova (due metà)": "—"}]
    ordinati = prove.assign(_s=prove["filtro"].isin(s.sopravvissuti),
                            _p=prove["filtro"].isin(promossi)
                            ).sort_values(["_s", "_p", "t_guadagno"],
                                          ascending=[False, False, False], na_position="last")
    for _, x in ordinati.head(quanti).iterrows():
        righe.append({
            "Filtro": x["filtro"], "Trade": int(x["trades"]),
            "Guadagno medio netto per trade (pips)": x["avg_trade_netto"],
            "Miglioramento sul sistema base (pips)": x["guadagno_pips"],
            "Solidità del miglioramento": x["t_guadagno"],
            "Prima prova": _prima_prova(x["esito"], x.get("motivo")),
            "Seconda prova (due metà)": _VERDETTO.get(verdetti.get(x["filtro"]), "—"),
        })
    tabella = pd.DataFrame(righe)
    s.tabelle["filtri"] = tabella
    _mostra(("I filtri migliori (in-sample, al netto dei costi)", tabella))

    asticella = float(s.fs.soglia_rumore)
    una_prova = soglia_rumore(1, ALPHA)
    s.tabelle["asticella"] = asticella
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
    _riquadro(
        "Ogni filtro è una condizione in più per entrare (trend, volatilità, orario…). Lo strumento li prova "
        "tutti, uno alla volta, e misura di quanti pips per trade migliorano il sistema base scartando i trade peggiori.",
        "Un filtro vale solo se supera due prove. Prima: il miglioramento deve essere più grande di quello che "
        "troveresti per caso provando così tanti filtri. Seconda: deve esserci in entrambe le metà dello storico, "
        "non in una sola. Più cose provi, più è facile trovarne una bella per caso: l'imbuto serve a questo.",
        adesso)
    return tabella


# ========================================================================
# 6 · Scheda strategia
# ========================================================================

_VOCI_SCHEDA = [
    ("n_trades", "Trade", 0),
    ("ev_pips", "Guadagno medio netto per trade (pips)", 2),
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
              "Guadagno medio netto per trade (pips)": base["avg_trade_netto"],
              "Miglioramento sul passo prima (pips)": np.nan,
              "Solidità del miglioramento": np.nan}]
    entry_long, entry_short, fs_k = s.fs.entry_long, s.fs.entry_short, s.fs
    for k, etichetta in enumerate(scelti):
        if k > 0:
            entry_long, entry_short = congela_filtro(fs_k, scelti[k - 1])
            fs_k = run_filter_search_bt(s.df_is, entry_long=entry_long, entry_short=entry_short,
                                        filtri=_membri_filtro(s, etichetta), **_kw_filtri(s))
        riga = fs_k.risultati[fs_k.risultati["filtro"] == etichetta].iloc[0]
        passi.append({"Passo": f"+ {etichetta}", "Trade": int(riga["trades"]),
                      "Guadagno medio netto per trade (pips)": riga["avg_trade_netto"],
                      "Miglioramento sul passo prima (pips)": riga["guadagno_pips"],
                      "Solidità del miglioramento": riga["t_guadagno"]})
    return entry_long, entry_short, fs_k, passi


def scheda(s: Sessione, filtro=None) -> pd.DataFrame:
    """
    Schermata 6. La scheda della strategia scelta: in-sample accanto alla
    prova out-of-sample (stesso setup, rieseguito sui dati mai visti), e
    l'equity out-of-sample contro il buy & hold.

    filtro   il nome di un filtro della classifica, oppure piu' nomi separati
             da virgola (o una lista): si entra solo dove sono veri TUTTI.
             None o vuoto = sistema base.

    Con piu' filtri mostra anche la tabella dei passi (base, + primo filtro,
    + secondo ...). Ritorna la tabella della scheda.
    """
    s._serve("fs", "5 · Trova la strategia")
    scelti = _lista_filtri(s, filtro)
    ultimo = scelti[-1] if scelti else None
    kw = _kw_motore(s)
    kw["margin"] = 1.0
    with _zitto():
        entry_long, entry_short, fs_ultimo, passi = _catena_filtri(s, scelti)
        s.oos = run_filter_search_bt(
            s.df_oos, entry_long=entry_long, entry_short=entry_short,
            exit_rule_pair=s.fs.exit_rule_pair,
            filtri=_membri_filtro(s, ultimo) if ultimo else [],
            min_trades=s.fs.min_trades, verbose=False, **kw)
        tr_is, tr_oos = fs_ultimo.trades(ultimo), s.oos.trades(ultimo)
        k_is = scheda_strategia(tr_is, s.fs.pip_size, s.fs.commission or 0.0,
                                montecarlo=False, verbose=False)
        k_oos = scheda_strategia(tr_oos, s.fs.pip_size, s.fs.commission or 0.0,
                                 montecarlo=False, verbose=False)
    s.filtri_scelti = scelti
    s.filtro = " + ".join(scelti) if scelti else None
    s.trades_is, s.trades_oos = tr_is, tr_oos

    if len(scelti) > 1:
        tab_passi = pd.DataFrame(passi)
        s.tabelle["passi"] = tab_passi
        _mostra(("Un filtro sopra l'altro (in-sample, al netto dei costi)", tab_passi))
        n_prove = int((s.fs.risultati["filtro"] != BASELINE).sum())
        combinazioni = math.comb(n_prove, len(scelti))
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
    s.tabelle["scheda"] = tabella
    nome = s.filtro or "sistema base"
    _mostra((f"Scheda strategia · {s.symbol} · {nome}", tabella))

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
        "Vai alla schermata 7 per controllare che i trade siano entrati dove dicono le tue regole; poi, se la strategia tiene, alla 8 per capire quanto drawdown aspettarti e con quanti lotti partire. "
        "L'out-of-sample si guarda una volta sola: se torni indietro a ritoccare finché non ti piace, smette di essere una prova.")
    return tabella


# ========================================================================
# 8 · Stress test
# ========================================================================

def stress_test(s: Sessione, drawdown_max_usd: float = 10_000.0,
                simulazioni: int = 20_000) -> dict:
    """
    Schermata 8. Monte Carlo sui trade della strategia scelta (in-sample +
    out-of-sample), tabella di controllo per il live e lotti consigliati.

    drawdown_max_usd   il drawdown massimo che accetti sul conto, in dollari

    Ritorna {"controllo": tabella, "montecarlo": dict, "sizing": dict}.
    """
    s._serve("oos", "6 · Scheda strategia")
    pips = pips_per_dataset(s.trades_is, s.trades_oos,
                            s.fs.pip_size, s.fs.commission or 0.0, dataset="FULL")
    with _zitto():
        orizzonti = tuple(h for h in ORIZZONTI_MC if h <= max(len(pips), 10))
        yard = yardstick(pips, orizzonti=orizzonti, n_sim=simulazioni)
        mc = montecarlo_completo(pips, n_sim=simulazioni)
        valore_pip = valore_pip_lotto(s.symbol, s.fs.pip_size, prezzo=float(s.df["Close"].iloc[-1]))
        sz = sizing(mc, drawdown_max_usd, valore_pip, percentile=95)

    controllo = pd.DataFrame({
        "Dopo quanti trade": [int(h) for h in yard.index],
        "Risultato tipico (pips)": yard["pnl_p50"].to_numpy(),
        "Drawdown tipico (pips)": yard["dd_p50"].to_numpy(),
        "Drawdown da allarme (pips)": yard["dd_p95"].to_numpy(),
        "Probabilità di essere in perdita (%)": yard["p_pnl_negativo"].to_numpy(),
    })
    sintesi = pd.DataFrame({
        "": ["Trade simulati", "Drawdown realmente visto", "Drawdown tipico",
             "Drawdown nel caso sfortunato (1 su 20)", "Probabilità di chiudere in perdita",
             "Valore di 1 pip con 1 lotto", "Drawdown che accetti", "Lotti consigliati"],
        " ": [_fmt(mc["n_trade"]), f"{_fmt(mc['dd_reale'], 0)} pips", f"{_fmt(mc['dd_p50'], 0)} pips",
              f"{_fmt(mc['dd_p95'], 0)} pips", f"{_fmt(mc['p_pnl_negativo'], 1)} %",
              f"{_fmt(valore_pip)} $", f"{_fmt(float(drawdown_max_usd), 0)} $",
              _fmt(sz["lotti_consigliati"])],
    })
    s.tabelle["stress"] = {"controllo": controllo, "sintesi": sintesi}
    _mostra(("Stress test · in sintesi", sintesi), ("Tabella di controllo per il live", controllo),
            decimali={"Dopo quanti trade": 0, "Risultato tipico (pips)": 0, "Drawdown tipico (pips)": 0,
                      "Drawdown da allarme (pips)": 0, "Probabilità di essere in perdita (%)": 1})
    grafici_montecarlo(pips, mc=mc, orizzonti=orizzonti, titolo=f"{s.symbol} · {s.filtro or 'sistema base'}")
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
    return {"controllo": controllo, "montecarlo": mc, "sizing": sz}


# ========================================================================
# 7 · Verifica i trade (in un modulo a parte: engine/vetrina_verifica.py)
# ========================================================================
# In fondo, perche' quel modulo usa gli strumenti di presentazione definiti qui.
from .vetrina_verifica import (indicatori_disponibili, lente, registro_trade,  # noqa: E402
                               verifica_trade)
