"""
L'adattatore della Sessione del Lab per la fabbrica (docs/82 P9, lavoro L4b): money management, stress test e verifica
dei trade di una strategia entrata in cassaforte, con le funzioni del Lab, senza cambiarle.

    esito = cassaforte.esito_cassaforte(cartella_dati, id_ricerca)     # o quello di cassaforte.entra
    with sessione(esito, id_strategia) as s:          # una vetrina.Sessione riempita (vedi apri_sessione)
        money_management(s)                           # schermata 7: vetrina.money_management_trade, finestra in ore
        vetrina.stress_test(s)                        # schermata 9, la funzione del Lab così com'è
        verifica_trade(s)                             # schermata 8a: vetrina_verifica.verifica_trade(s, finestra)
        vetrina_verifica.lente(s, mostra_trigger=False)    # 8b
    # all'uscita (anche dopo un errore) le condizioni temporanee escono dal catalogo: chiudi(s)

- In-sample = ricerca + selezione (gli indicatori su quei due pezzi, i trade finiscono all'ultima barra della
  selezione); out-of-sample = la cassaforte, con i trade della cassaforte (cassaforte.EsitoCassaforte.trade) e le barre
  del pezzo di cassaforte, che ha gli indicatori calcolati su tutti e tre i pezzi. Come nel Lab, il money management si
  calibra sull'in-sample e la cassaforte fa da out-of-sample.
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

import pandas as pd

from engine import registry as reg
from engine.exchange import solo_long
from engine.indicatori import aggiungi_indicatori

from .blocchi import MINUTI_TIMEFRAME, blocchi_da_config
from .cache import LAG_SOGLIE, ORE_FINESTRA_SOGLIE, Cache, barre_da_ore
from .dati import imposta_mercato_crypto
from .selezione import ValutatoreSelezione, strategia_da_riga
from .valutatore import Costi, trade_completi

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


def apri_sessione(esito, id_strategia: str):
    """
    Una vetrina.Sessione per una strategia entrata in cassaforte (`esito` di cassaforte.entra o esito_cassaforte).
    Campi riempiti: symbol, timeframe, cartella, df, df_is, df_oos, trades_is, trades_oos, pip, spread_pips, costi,
    uscite, fs (pip_size, commission, risultati), filtro, filtri_scelti, trigger_long/short, entry_long/short,
    da_exchange, solo_long, unita, oos, H. In più `s.fabbrica`: prefisso, finestra, lag, strategia, id_ricerca.
    """
    from engine.vetrina import Sessione, costi_storico, impostazioni_uscite

    if id_strategia not in esito.trade:
        raise ValueError(f"la strategia {id_strategia} non è entrata in cassaforte in questo tratto: niente Sessione.")
    riga = next(x for e in esito.ingressi for x in e["strategie"] if x["id_strategia"] == id_strategia)
    config, pezzi, pezzo = esito.config, esito.pezzi, esito.pezzo
    symbol, timeframe = config["symbol"], config["timeframe"]
    st = strategia_da_riga(riga, symbol, timeframe)
    blocchi = {b.nome: b for b in blocchi_da_config(config)}
    imposta_mercato_crypto()

    # l'in-sample: ricerca + selezione, i trade finiscono all'ultima barra della selezione
    grezzo_is = pd.concat([pezzi.ricerca, pezzi.selezione])
    funding_is = [f for f in (pezzi.funding["ricerca"], pezzi.funding["selezione"]) if f is not None]
    costi_is = dict(costi_storico(symbol, grezzo_is, funding=pd.concat(funding_is) if funding_is else None,
                                  df_prezzo=grezzo_is)[0])
    df_is = aggiungi_indicatori(grezzo_is)
    cache_is = Cache(df_is, LIMITE_CACHE_MB)
    v_is = ValutatoreSelezione(list(blocchi.values()), cache_is, Costi(df_is, costi_is), 0)
    trades_is = trade_completi(st, v_is, costi_is)

    # l'out-of-sample: la cassaforte, con i suoi trade riportati alle barre del suo pezzo
    df_oos = pezzo.df.iloc[pezzo.inizio:]
    trades_oos = esito.trade[id_strategia].copy()
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
                  "id_strategia": id_strategia, "id_ricerca": esito.ingressi[0]["id_ricerca"], "tratto": esito.tratto}
    try:
        nomi = _registra(prefisso, st, cache_is, cache_tutto, pezzo.inizio, blocchi)
        u = st.valori_di(st.uscita)
        lato = "long" if st.lato == 1 else "short"
        s.symbol, s.timeframe, s.cartella = symbol, timeframe, pezzi.cartella
        s.df, s.df_is, s.df_oos = pezzo.df, df_is, df_oos
        s.trades_is, s.trades_oos = trades_is, trades_oos
        s.costi = dict(pezzo.costi)
        s.pip = float(pezzo.costi["pip_size"])
        s.spread_pips = 0.0                 # sui symbol da exchange lo spread è fuori dal prezzo di fill (docs/71)
        s.da_exchange, s.solo_long, s.unita = True, solo_long(symbol), "bp"
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
def sessione(esito, id_strategia: str):
    """apri_sessione dentro un blocco `with`: all'uscita, anche dopo un errore, chiudi(s)."""
    s = apri_sessione(esito, id_strategia)
    try:
        yield s
    finally:
        chiudi(s)


def money_management(s, capitale: float = 10_000.0, drawdown_max_pct: float = 20.0, anni: float = 1.0,
                     modello: str = "volatilità", leva: float | None = None, simulazioni: int | None = None) -> dict:
    """
    Schermata 7 per la fabbrica: vetrina.money_management_trade (la funzione che la schermata del Lab chiama), con la
    finestra delle soglie in barre del timeframe e il lag della fabbrica. Salva in s.mm, come il Lab.
    simulazioni: None = quelle del Lab (vetrina.SIMULAZIONI_MM); meno solo nei collaudi.
    """
    from engine.vetrina import SIMULAZIONI_MM, money_management_trade
    if leva is not None and float(leva) == 0:
        leva = None
    u = s.uscite
    out = money_management_trade(
        s.symbol, s.trades_is, s.df_is, s.trades_oos, s.df_oos, pip=s.fs.pip_size, commission=s.fs.commission or 0.0,
        spread_pips=s.spread_pips, perc_sl=u["perc_sl"], n_barre_long=u["n_barre_long"],
        n_barre_short=u["n_barre_short"], finestra=s.fabbrica["finestra"], lag=s.fabbrica["lag"], cartella=s.cartella,
        capitale=capitale, drawdown_max_pct=drawdown_max_pct, anni=anni, titolo=f"{s.symbol} · {s.filtro}",
        modello=modello, storia=s.df, leva=leva, simulazioni=SIMULAZIONI_MM if simulazioni is None else int(simulazioni))
    s.mm = out
    s.tabelle["money_management"] = {"rischio": out["rischio"], "sintesi": out["sintesi"]}
    return out


def verifica_trade(s) -> dict:
    """Schermata 8a per la fabbrica: vetrina_verifica.verifica_trade con la finestra delle soglie in barre."""
    from engine.vetrina_verifica import verifica_trade as verifica_lab
    return verifica_lab(s, finestra=s.fabbrica["finestra"])
