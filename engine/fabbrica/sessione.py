"""
L'adattatore della Sessione del Lab per la fabbrica (docs/82 P9, lavoro L4b; più monete dal 20/11, §14.4): money
management, stress test e verifica dei trade di una strategia entrata in cassaforte, con le funzioni del Lab, senza
cambiarle.

    esito = cassaforte.esito_cassaforte(cartella_dati, id_ricerca)     # o quello di cassaforte.entra
    with sessioni(esito, id_strategia) as ss:         # {symbol: vetrina.Sessione}, una per moneta (apri_sessione)
        money_management(ss)                          # schermata 7 su tutte le monete insieme (money_management_trade)
        stress_test(ss, mm)                           # schermata 9 su tutte le monete insieme, giorni interi
        verifica_trade(ss)                            # schermata 8a, moneta per moneta
        vetrina_verifica.lente(ss[symbol], mostra_trigger=False)    # 8b, su una moneta
    # all'uscita (anche dopo un errore) le condizioni temporanee escono dal catalogo: chiudi(s)

- In-sample = ricerca + selezione (gli indicatori su quei due pezzi, i trade finiscono all'ultima barra della
  selezione); out-of-sample = la cassaforte, con i trade della cassaforte (cassaforte.EsitoCassaforte.trade) e le barre
  del pezzo di cassaforte, che ha gli indicatori calcolati su tutti e tre i pezzi. Come nel Lab, il money management si
  calibra sull'in-sample e la cassaforte fa da out-of-sample.
- Più monete (docs/82 §14.4): il money management è quello del Lab (vetrina.money_management_trade) sulla tabella dei
  trade di TUTTE le monete, in ordine d'ingresso, con le colonne ingresso, uscita e giorno e i lotti di ogni moneta
  (money_management.py, colonne facoltative): ogni trade prende i lotti dal capitale dei trade già chiusi in quel
  momento, la leva somma le posizioni aperte su tutte le monete, il Monte Carlo pesca giorni interi. La tabella
  della lista si passa alla funzione del Lab sostituendo per il tempo della chiamata le tre funzioni di
  engine/mm_adattatore.py che la costruiscono (_tabelle_lista); il Lab non cambia. Lo stress test pesca giorni interi
  (montecarlo.py, `giorni`) sui bp di tutte le monete. La verifica dei trade è quella del Lab, moneta per moneta.
- La verifica dei trade del Lab cerca trigger e filtri per nome nel catalogo (engine.registry). I blocchi della fabbrica
  si registrano per il tempo della Sessione con nomi FAB_SES_<n>_<blocco>: ogni nome restituisce la maschera già
  calcolata dalla fabbrica, letta per data, così non riparte da zero all'inizio della cassaforte. chiudi(s) li toglie.
- Le finestre in ore della fabbrica: la finestra delle soglie adattive (125 ore) diventa barre del timeframe e va al
  money management (money_management_trade, finestra) e alla verifica (verifica_trade, finestra). Le schermate del Lab
  hanno 500 barre fisse, che sono 125 ore solo su M15.
"""
from __future__ import annotations

import contextlib
import itertools
from types import SimpleNamespace

import numpy as np
import pandas as pd

from engine import registry as reg
from engine.exchange import solo_long
from engine.indicatori import aggiungi_indicatori

from .blocchi import MINUTI_TIMEFRAME, blocchi_da_config
from .cache import LAG_SOGLIE, ORE_FINESTRA_SOGLIE, Cache, barre_da_ore
from .dati import imposta_mercato_crypto
from .selezione import strategia_da_riga
from .valutatore import Costi, Valutatore, trade_completi

PREFISSO = "FAB_SES_"
LIMITE_CACHE_MB = 800
_CONTATORE = itertools.count(1)


def _serie(maschere: list[tuple[pd.Index, object]]) -> pd.Series:
    """Una serie booleana per data dai pezzi (indice, maschera)."""
    return pd.concat([pd.Series(m, index=i, dtype=bool) for i, m in maschere])


def _registra(prefisso: str, strategia, cache_is: Cache, cache_tutto: Cache, inizio: int, blocchi: dict) -> dict:
    """Trigger e filtri della strategia nel catalogo, con le maschere della fabbrica lette per data."""
    lato = strategia.lato
    nomi = {}
    df_is, df_tutto = cache_is.df, cache_tutto.df
    for nome_blocco in (strategia.trigger, *strategia.filtri):
        b = blocchi[nome_blocco]
        valori = strategia.valori_di(nome_blocco) or None
        serie = _serie([(df_is.index, b.maschera(cache_is, lato, valori)),
                        (df_tutto.index[inizio:], b.maschera(cache_tutto, lato, valori)[inizio:])])
        nome = f"{prefisso}{nome_blocco}"

        def funzione(d, _s=serie):
            return _s.reindex(d.index, fill_value=False).astype(bool)

        if nome_blocco == strategia.trigger:
            reg.register_entry(nome, direction=lato)(funzione)
        else:
            reg.register_filter(nome, direction=0 if b.neutro else lato)(funzione)
        nomi[nome_blocco] = nome
    return nomi


def chiudi(s) -> None:
    """Toglie dal catalogo le condizioni temporanee della Sessione. Si può chiamare più volte."""
    prefisso = getattr(s, "fabbrica", {}).get("prefisso")
    if prefisso:
        reg.remove_entries(prefisso)
        reg.remove_filters(prefisso)


def in_sample(config: dict, pezzi, strategia, blocchi: dict | None = None) -> SimpleNamespace:
    """
    L'in-sample di una strategia su una moneta (`pezzi` = i Pezzi di quella moneta): ricerca + selezione attaccate, con
    i loro indicatori e i loro costi; i trade del motore completo finiscono all'ultima barra della selezione. Ritorna
    df, cache, costi, trades. La usano la Sessione e la scheda (schede.trade_da_scheda), così i trade sono gli stessi
    al bit.
    """
    from engine.vetrina import costi_storico
    symbol = pezzi.symbol
    blocchi = blocchi or {b.nome: b for b in blocchi_da_config(config)}
    imposta_mercato_crypto()
    grezzo_is = pd.concat([pezzi.ricerca, pezzi.selezione])
    funding_is = [f for f in (pezzi.funding["ricerca"], pezzi.funding["selezione"]) if f is not None]
    costi_is = dict(costi_storico(symbol, grezzo_is, funding=pd.concat(funding_is) if funding_is else None,
                                  df_prezzo=grezzo_is)[0])
    df_is = aggiungi_indicatori(grezzo_is)
    cache_is = Cache(df_is, LIMITE_CACHE_MB)
    v_is = Valutatore(list(blocchi.values()), cache_is, Costi(df_is, costi_is))
    return SimpleNamespace(df=df_is, cache=cache_is, costi=costi_is, trades=trade_completi(strategia, v_is, costi_is))


def apri_sessione(esito, id_strategia: str, moneta: str):
    """
    Una vetrina.Sessione per una strategia entrata in cassaforte, su una moneta della lista (`esito` di cassaforte.entra
    o esito_cassaforte). Campi riempiti: symbol, timeframe, cartella, df, df_is, df_oos, trades_is, trades_oos, pip,
    spread_pips, costi, uscite, fs (pip_size, commission, risultati), filtro, filtri_scelti, trigger_long/short,
    entry_long/short, da_exchange, solo_long, unita, oos, H. In più `s.fabbrica`: prefisso, finestra, lag, strategia,
    id_ricerca, moneta.
    """
    from engine.vetrina import Sessione, impostazioni_uscite

    if id_strategia not in esito.trade:
        raise ValueError(f"la strategia {id_strategia} non è entrata in cassaforte in questo tratto: niente Sessione.")
    config = esito.config
    if moneta not in config["monete"]:
        raise ValueError(f"{moneta} non è nella lista di questa ricerca: {config['monete']}.")
    riga = next(x for e in esito.ingressi for x in e["strategie"] if x["id_strategia"] == id_strategia)
    pezzi, pezzo = esito.pezzi[moneta], esito.pezzo[moneta]
    timeframe = config["timeframe"]
    st = strategia_da_riga(riga, config["monete"], timeframe)
    blocchi = {b.nome: b for b in blocchi_da_config(config)}

    # l'in-sample: ricerca + selezione, i trade finiscono all'ultima barra della selezione
    ins = in_sample(config, pezzi, st, blocchi)
    df_is, cache_is, trades_is = ins.df, ins.cache, ins.trades

    # l'out-of-sample: la cassaforte, con i suoi trade riportati alle barre del suo pezzo
    df_oos = pezzo.df.iloc[pezzo.inizio:]
    trades_oos = esito.trade[id_strategia][moneta].copy()
    for c in ("EntryBar", "ExitBar"):
        trades_oos[c] = trades_oos[c] - pezzo.inizio
    if len(trades_oos) and not (pd.DatetimeIndex(df_oos.index[trades_oos["EntryBar"].to_numpy()])
                                .equals(pd.DatetimeIndex(trades_oos["EntryTime"]))):
        raise ValueError("i trade della cassaforte non tornano con le sue barre.")
    cache_tutto = Cache(pezzo.df, LIMITE_CACHE_MB)

    s = Sessione()
    prefisso = f"{PREFISSO}{next(_CONTATORE)}_"
    finestra = barre_da_ore(ORE_FINESTRA_SOGLIE, MINUTI_TIMEFRAME[timeframe])
    s.fabbrica = {"prefisso": prefisso, "finestra": finestra, "lag": LAG_SOGLIE, "strategia": st,
                  "id_strategia": id_strategia, "id_ricerca": esito.ingressi[0]["id_ricerca"], "tratto": esito.tratto,
                  "moneta": moneta}
    try:
        nomi = _registra(prefisso, st, cache_is, cache_tutto, pezzo.inizio, blocchi)
        s.fabbrica["nomi"] = dict(nomi)          # blocco -> nome temporaneo nel catalogo (L5b: per i nomi brevi)
        u = st.valori_di(st.uscita)
        lato = "long" if st.lato == 1 else "short"
        s.symbol, s.timeframe, s.cartella = moneta, timeframe, pezzi.cartella
        s.df, s.df_is, s.df_oos = pezzo.df, df_is, df_oos
        s.trades_is, s.trades_oos = trades_is, trades_oos
        s.costi = dict(pezzo.costi)
        s.pip = float(pezzo.costi["pip_size"])
        s.spread_pips = 0.0                 # sui symbol da exchange lo spread è fuori dal prezzo di fill (docs/71)
        s.da_exchange, s.solo_long, s.unita = True, solo_long(moneta), "bp"
        s.H = int(u["durata_barre"])
        s.uscite = impostazioni_uscite(s.H, s.H, u["perc_stop"] or 0.0, u["target"] or 0.0, st.uscita)
        trigger = nomi[st.trigger]
        s.trigger_long, s.trigger_short = ((trigger,), ()) if st.lato == 1 else ((), (trigger,))
        s.entry_long, s.entry_short = (trigger, None) if st.lato == 1 else (None, trigger)
        s.filtri_scelti = list(st.filtri)
        s.fs = SimpleNamespace(pip_size=s.pip, commission=float(pezzo.costi["commission"]), risultati=pd.DataFrame({
            "filtro": list(st.filtri),
            "filtro_long": [nomi[f] if lato == "long" else "—" for f in st.filtri],
            "filtro_short": [nomi[f] if lato == "short" else "—" for f in st.filtri]}))
        s.filtro = st.teoria_id
        s.oos = {"fabbrica": True, "tratto": esito.tratto["id"]}
    except Exception:
        chiudi(s)
        raise
    return s


@contextlib.contextmanager
def sessioni(esito, id_strategia: str):
    """{symbol: Sessione} per tutte le monete della lista, dentro un blocco `with`: all'uscita, anche dopo un errore,
    chiudi(s) per ognuna."""
    aperte = {}
    try:
        for m in esito.config["monete"]:
            aperte[m] = apri_sessione(esito, id_strategia, m)
        yield aperte
    finally:
        for s in aperte.values():
            chiudi(s)


# ------------------------------------------------------------------ money management (schermata 7, §14.4)
def tabella_lista(ss: dict, misura: str, periodo: str) -> pd.DataFrame:
    """
    La tabella dei trade di tutte le monete per money_management.py (engine/mm_adattatore.tabella_trade per ogni moneta,
    con i suoi pip, costi, lotti e ATR sullo storico intero), in ordine d'ingresso (a parità, nell'ordine della lista),
    con le colonne facoltative di §14.4: ingresso, uscita, giorno (UTC) e i lotti della moneta di ogni trade.
    `periodo` = "is" o "oos".
    """
    from engine.indicatori import atr_giornaliero_chiuso
    from engine.simboli import lotti_symbol
    _salva_originali()
    parti = []
    for m, s in ss.items():
        u = s.uscite
        trades, df = (s.trades_is, s.df_is) if periodo == "is" else (s.trades_oos, s.df_oos)
        # l'ATR sullo storico intero della moneta (s.df), come il Lab con storia=s.df
        t = _originali["tabella_trade"](trades, df, symbol=m, pip=s.fs.pip_size, commission=s.fs.commission or 0.0,
                                         spread_pips=0.0, perc_sl=u["perc_sl"], n_barre_long=u["n_barre_long"],
                                         n_barre_short=u["n_barre_short"], finestra=s.fabbrica["finestra"],
                                         lag=s.fabbrica["lag"], cartella=s.cartella, misura=misura,
                                         atr=atr_giornaliero_chiuso(s.df))
        lim = lotti_symbol(m)
        parti.append(t.assign(moneta=m, lotto_minimo=float(lim["minimo"]), lotto_passo=float(lim["passo"]),
                              lotto_massimo=float(lim["massimo"])))
    tab = pd.concat(parti, ignore_index=True) if parti else pd.DataFrame()
    if len(tab):
        tab = tab.sort_values("entrata", kind="mergesort").reset_index(drop=True)
    tab["ingresso"] = tab["entrata"] if len(tab) else pd.Series(dtype="datetime64[ns, UTC]")
    tab["giorno"] = pd.DatetimeIndex(tab["entrata"]).floor("D") if len(tab) else pd.Series(dtype="datetime64[ns, UTC]")
    return tab


_originali: dict = {}


def _salva_originali() -> None:
    from engine import mm_adattatore as ad
    if not _originali:
        _originali.update(tabella_trade=ad.tabella_trade, trade_per_anno=ad.trade_per_anno,
                          limiti_symbol=ad.limiti_symbol)


@contextlib.contextmanager
def _tabelle_lista(ss: dict):
    """
    Per il tempo del blocco, le tre funzioni di engine/mm_adattatore.py che money_management_trade chiama danno la lista
    (§14.4): tabella_trade la tabella di tutte le monete (tabella_lista; il primo argomento è «is» o «oos»),
    trade_per_anno i trade in-sample di tutte le monete diviso gli anni dell'in-sample, limiti_symbol i limiti della
    prima moneta per la leva (i lotti di ogni trade vengono dalle colonne lotto_*). All'uscita tornano quelle di prima.
    """
    from engine import mm_adattatore as ad
    _salva_originali()
    tabelle = {}

    def tabella(trades, df, **k):
        chiave = ("volatilita" if str(k["misura"]).lower().startswith("volatilit") else "stop", trades)
        if chiave not in tabelle:
            tabelle[chiave] = tabella_lista(ss, chiave[0], trades)
        return tabelle[chiave]

    def per_anno(trades, df):
        primo = next(iter(ss.values()))
        anni = (primo.df_is.index[-1] - primo.df_is.index[0]).total_seconds() / (365.25 * 86400)
        n = sum(len(s.trades_is) for s in ss.values())
        return n / anni if anni > 0 else float("nan")

    def limiti(symbol, leva=True, valore_leva=None):
        return _originali["limiti_symbol"](next(iter(ss)), leva=leva, valore_leva=valore_leva)

    ad.tabella_trade, ad.trade_per_anno, ad.limiti_symbol = tabella, per_anno, limiti
    try:
        yield tabelle
    finally:
        ad.tabella_trade = _originali["tabella_trade"]
        ad.trade_per_anno = _originali["trade_per_anno"]
        ad.limiti_symbol = _originali["limiti_symbol"]


def money_management(ss: dict, capitale: float = 10_000.0, drawdown_max_pct: float = 20.0, anni: float = 1.0,
                     modello: str = "volatilità", leva: float | None = None, simulazioni: int | None = None) -> dict:
    """
    Schermata 7 per la fabbrica, su tutte le monete insieme (docs/82 §14.4): vetrina.money_management_trade (la funzione
    che la schermata del Lab chiama) sulla tabella della lista (_tabelle_lista), con la finestra delle soglie in barre
    del timeframe e il lag della fabbrica. Salva in s.mm di ogni Sessione, come il Lab.
    simulazioni: None = quelle del Lab (vetrina.SIMULAZIONI_MM); meno solo nei collaudi.
    """
    from engine.vetrina import SIMULAZIONI_MM, money_management_trade
    if leva is not None and float(leva) == 0:
        leva = None
    primo = next(iter(ss.values()))
    u = primo.uscite
    titolo = f"{', '.join(m.rsplit('_', 1)[1][:-4] for m in ss)} · {primo.filtro}"
    with _tabelle_lista(ss):
        out = money_management_trade(
            primo.symbol, "is", primo.df_is, "oos", primo.df_oos, pip=primo.fs.pip_size,
            commission=primo.fs.commission or 0.0, spread_pips=0.0, perc_sl=u["perc_sl"],
            n_barre_long=u["n_barre_long"], n_barre_short=u["n_barre_short"], finestra=primo.fabbrica["finestra"],
            lag=primo.fabbrica["lag"], cartella=primo.cartella, capitale=capitale, drawdown_max_pct=drawdown_max_pct,
            anni=anni, titolo=titolo, modello=modello, storia=None, leva=leva,
            simulazioni=SIMULAZIONI_MM if simulazioni is None else int(simulazioni))
    for s in ss.values():
        s.mm = out
        s.tabelle["money_management"] = {"rischio": out["rischio"], "sintesi": out["sintesi"]}
    return out


# ------------------------------------------------------------------ stress test (schermata 9, §14.4)
def bp_lista(ss: dict) -> pd.DataFrame:
    """I bp netti di tutti i trade (in-sample poi cassaforte), in ordine d'ingresso, con moneta e giorno d'ingresso."""
    from engine.metriche import bp_per_trade
    righe = []
    for periodo in ("is", "oos"):
        parti = []
        for m, s in ss.items():
            t = s.trades_is if periodo == "is" else s.trades_oos
            if len(t):
                _, netti = bp_per_trade(t, s.fs.pip_size, s.fs.commission or 0.0)
                parti.append(pd.DataFrame({"ingresso": pd.DatetimeIndex(t["EntryTime"]), "moneta": m,
                                           "bp": netti.to_numpy(dtype=float)}))
        if parti:
            righe.append(pd.concat(parti, ignore_index=True).sort_values("ingresso", kind="mergesort"))
    tab = pd.concat(righe, ignore_index=True) if righe else pd.DataFrame(columns=["ingresso", "moneta", "bp"])
    tab = tab[np.isfinite(tab["bp"].to_numpy(dtype=float))].reset_index(drop=True)
    tab["giorno"] = pd.DatetimeIndex(tab["ingresso"]).floor("D")
    return tab


def stress_test(ss: dict, mm: dict | None = None, drawdown_max_usd: float = 10_000.0,
                simulazioni: int = 20_000) -> dict:
    """
    Schermata 9 per la fabbrica, su tutte le monete insieme (docs/82 §14.4): il Monte Carlo del Lab (montecarlo.py) sui
    bp netti di tutti i trade, in-sample e cassaforte, pescando GIORNI interi (tutti i trade che si aprono quel giorno,
    su qualunque moneta). In bp vuol dire lo stesso valore in dollari a ogni trade: l'esposizione consigliata per trade
    viene dal drawdown sfortunato in bp, e i lotti di ogni moneta dal prezzo della sua ultima barra.
    `mm` = il money management della 7: il drawdown che accetti è capitale × drawdown %.
    Ritorna {"controllo", "montecarlo", "sizing", "drawdown_max_usd", "unita"}.
    """
    from engine import vetrina as v
    from engine.montecarlo import grafici_montecarlo, montecarlo_completo, yardstick
    from engine.simboli import info_symbol, lotti_symbol
    if mm is not None:
        drawdown_max_usd = mm["capitale"] * mm["drawdown_max_pct"] / 100.0
        origine = (f"dal money management qui sopra: {v._fmt(mm['capitale'], 0)} $ × "
                   f"{v._fmt(mm['drawdown_max_pct'], 1)} % = {v._fmt(drawdown_max_usd, 0)} $")
    else:
        origine = f"{v._fmt(float(drawdown_max_usd), 0)} $"
    tab = bp_lista(ss)
    valori, giorni = tab["bp"].to_numpy(dtype=float), tab["giorno"]
    with v._zitto():
        orizzonti = tuple(h for h in v.ORIZZONTI_MC if h <= max(len(valori), 10))
        yard = yardstick(valori, orizzonti=orizzonti, n_sim=simulazioni, giorni=giorni)
        mc = montecarlo_completo(valori, n_sim=simulazioni, giorni=giorni)
    esposizione = float(drawdown_max_usd) / mc["dd_p95"] * 10_000.0 if mc["dd_p95"] > 0 else float("nan")
    lotti = []
    for m, s in ss.items():
        prezzo = float(s.df["Close"].iloc[-1])
        passo = float(lotti_symbol(m)["passo"])
        grezzi = esposizione / (prezzo * float(info_symbol(m)["contratto"])) if np.isfinite(esposizione) else np.nan
        consigliati = (round(np.floor(grezzi / passo + 1e-9) * passo, max(0, int(round(-np.log10(passo))) + 2))
                       if np.isfinite(grezzi) else np.nan)
        lotti.append({"moneta": m, "prezzo dell'ultima barra ($)": prezzo,
                      "ultima barra (UTC)": s.df.index[-1].strftime("%d/%m/%Y %H:%M"), "lotti consigliati": consigliati})
    sz = {"percentile": 95, "dd_bp": mc["dd_p95"], "esposizione_usd": esposizione, "lotti": lotti}
    controllo = pd.DataFrame({
        "Dopo quanti trade": [int(h) for h in yard.index],
        "Risultato tipico (bp)": yard["pnl_p50"].to_numpy(),
        "Drawdown tipico (bp)": yard["dd_p50"].to_numpy(),
        "Drawdown da allarme (bp)": yard["dd_p95"].to_numpy(),
        "Probabilità di essere in perdita (%)": yard["p_pnl_negativo"].to_numpy(),
    })
    sintesi = pd.DataFrame({"": ["Trade simulati", "Giorni con trade", "Drawdown realmente visto", "Drawdown tipico",
                                 "Drawdown nel caso sfortunato (1 su 20)", "Probabilità di chiudere in perdita",
                                 "Drawdown che accetti", "Esposizione consigliata per trade"],
                            " ": [v._fmt(mc["n_trade"]), v._fmt(int(pd.Series(giorni).nunique())),
                                  f"{v._fmt(mc['dd_reale'], 0)} bp", f"{v._fmt(mc['dd_p50'], 0)} bp",
                                  f"{v._fmt(mc['dd_p95'], 0)} bp", f"{v._fmt(mc['p_pnl_negativo'], 1)} %",
                                  f"{v._fmt(float(drawdown_max_usd), 0)} $", f"{v._fmt(esposizione, 0)} $"]})
    for s in ss.values():
        s.tabelle["stress"] = {"controllo": controllo, "sintesi": sintesi}
    v._nota(f"Drawdown che accetti, {origine}.")
    v._nota("Il Monte Carlo lavora sui bp netti di tutti i trade, su tutte le monete: è come mettere lo stesso valore in "
            "dollari a ogni trade. Pesca giorni interi (tutti i trade che si aprono quel giorno, su qualunque moneta): "
            "un giorno brutto su più monete resta un giorno brutto. L'esposizione consigliata viene dal drawdown "
            "sfortunato in bp; i lotti di ogni moneta dal prezzo della sua ultima barra dei dati (il tool non legge il "
            "prezzo dal vivo).")
    v._mostra(("Stress test · in sintesi", sintesi), ("Lotti consigliati per moneta", pd.DataFrame(lotti)),
              ("Tabella di controllo per il live", controllo),
              decimali={"Dopo quanti trade": 0, "Risultato tipico (bp)": 0, "Drawdown tipico (bp)": 0,
                        "Drawdown da allarme (bp)": 0, "Probabilità di essere in perdita (%)": 1})
    grafici_montecarlo(valori, mc=mc, orizzonti=orizzonti, titolo=f"{len(ss)} monete", unita="bp", giorni=giorni)
    import matplotlib.pyplot as plt
    plt.show()
    v._riquadro(
        "Migliaia di storie alternative, costruite ripescando a caso giornate intere della strategia, su tutte le monete. "
        "Il backtest te ne mostra una sola; qui ne vedi migliaia.",
        "Guarda il drawdown nel caso sfortunato: è quello su cui dimensionare il conto, non quello del backtest. "
        "L'esposizione consigliata è calcolata perché quel drawdown resti dentro la cifra che hai detto di accettare.",
        "Dal vivo usa la tabella di controllo: se dopo 20 trade il drawdown supera quello «da allarme» della riga 20, "
        "la strategia sta facendo qualcosa che nelle simulazioni è capitato meno di 1 volta su 20.")
    return {"controllo": controllo, "montecarlo": mc, "sizing": sz, "drawdown_max_usd": float(drawdown_max_usd),
            "unita": "bp"}


# ------------------------------------------------------------------ verifica dei trade (schermata 8)
def verifica_trade(ss: dict) -> dict:
    """
    Schermata 8a per la fabbrica: vetrina_verifica.verifica_trade di ogni moneta, con la finestra delle soglie in barre.
    Ritorna {"regole", "uscite"} con la colonna «moneta», e "per_moneta" = {symbol: l'esito del Lab}.
    """
    from engine import vetrina as v
    from engine.vetrina_verifica import verifica_trade as verifica_lab
    per, regole, uscite = {}, [], []
    for m, s in ss.items():
        if len(ss) > 1:
            v._titolo(f"{m} · verifica dei trade")
        r = verifica_lab(s, finestra=s.fabbrica["finestra"])
        per[m] = r
        regole.append(r["regole"].assign(moneta=m))
        uscite.append(r["uscite"].assign(moneta=m))
    return {"regole": pd.concat(regole, ignore_index=True), "uscite": pd.concat(uscite, ignore_index=True),
            "per_moneta": per}
