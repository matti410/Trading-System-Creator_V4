"""
La rosa dei candidati (18/10/2026, decisioni di Mattia del 17/10/2026).

A COSA SERVE
------------
Dopo l'event study, e dopo la ricerca delle uscite, il catalogo propone
decine di candidati. La rosa ne SUGGERISCE un gruppo: quelli con un
andamento positivo che difficilmente e' solo fortuna, e diversi fra loro
(un'idea per famiglia, profitti giornalieri poco correlati). La scelta resta
dell'utente: la rosa non approva niente, e la validazione che viene dopo
(filtri, due meta', out-of-sample una volta sola) non cambia.

DUE CANCELLI PER DUE COMPITI (docs/02)
--------------------------------------
La soglia di rumore della validazione (Sidak) controlla la probabilita' che
fra tutte le prove anche UNA sola sia un colpo di fortuna: e' giusto che sia
severa, ma per proporre candidati lascia passare troppo poco. Qui si usa il
controllo della QUOTA di falsi positivi (Benjamini-Hochberg): in media, nella
rosa, al massimo q dei candidati e' un colpo di fortuna (q = 20%). Prova di
potenza del 17/10/2026, EURUSD, H = 25, 1.000 eventi: con 3 pips di vantaggio
vero a trade la validazione ne trova il 46%, la rosa l'89%, con meno di una
entry finta per giro su 75.

COME SI COSTRUISCE
------------------
1. Per ogni candidato il t NETTO: lo scarto dalla linea del mercato diviso la
   sua incertezza. Per le entry a orizzonte H, con l'incertezza dell'event
   study che tiene conto dei trigger vicini; per i sistemi sui pips netti dei
   trade veri, togliendo a ogni trade la deriva del mercato nelle barre in cui
   e' rimasto aperto. Su un asset che sale da solo (BTCUSD, indici) una long
   «positiva» spesso misura solo la salita: lo scarto la toglie.
2. Benjamini-Hochberg al livello q sul p a UNA coda (solo andamenti positivi).
3. Lo scarto dal mercato deve essere positivo su ENTRAMBE le meta'
   dell'in-sample.
4. Il gruppo: dal t piu' alto in giu', un candidato entra se e' di una
   famiglia non ancora presente (engine/famiglie.py, soglia 60%) e se ha
   |rho| <= rho_max (0,3) con tutti quelli gia' presi, sui profitti
   giornalieri (giornata FX). Per le entry i profitti sono quelli della sola
   entry a H barre (misurato il 17/10/2026: stessa mappa delle correlazioni
   dei trade interi, accordo 0,99, 60 volte piu' veloce); per i sistemi
   quelli dei trade veri.

Si passa SOLO l'in-sample. L'orizzonte H e' quello scelto prima (passo 1 del
notebook di ricerca, passo 2 del Lab): la rosa non sceglie orizzonti.

LA BASELINE ORARIA (18/10/2026, decisione di Mattia)
----------------------------------------------------
Con baseline="oraria" (il predefinito) la linea del mercato di ogni trigger
e' la media della SUA fascia oraria (engine/stagionalita.py), non quella di
tutte le barre: un trigger che scatta sempre alla stessa ora non viene
premiato, o punito, per l'ora. Per i sistemi si toglie a ogni trade la
deriva tipica delle fasce orarie in cui e' rimasto aperto. L'incertezza
include il rumore della media di fascia. Il confronto con la media di tutte
le barre resta visibile (scarto_globale_pips, t_globale); baseline="globale"
ridà esattamente i numeri di prima.
"""
from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd

from . import registry as _reg
from .event_study import _errore_standard_sovrapposti
from .famiglie import SOGLIA_FAMIGLIA, famiglie
from .giudizio import t_stat
from .livelli import giorno_fx
from .metriche import atr_alla_entrata, pips_per_trade
from .quarantena_trade import maschera_segnali_puliti
from .stagionalita import (FUSO_PREDEFINITO, UNITA, deriva_per_barra_oraria, fasce_orarie,
                           in_unita, scarto_orario)

Q_ROSA = 0.20
RHO_MAX = 0.30
MIN_EVENTI = 200

_NORMALE = NormalDist()


# ========================================================================
# Pezzi comuni
# ========================================================================

def benjamini_hochberg(p, q: float = Q_ROSA) -> np.ndarray:
    """
    Vero per le prove che passano il controllo della quota di falsi positivi
    al livello q (procedura «step-up» di Benjamini-Hochberg): ordinati i p dal
    piu' piccolo, si trova il rango r piu' alto con p_(r) <= q * r / k e
    passano i primi r. I p non finiti contano nelle k prove ma non passano.
    """
    p = np.asarray(p, dtype=float)
    k = p.size
    passa = np.zeros(k, dtype=bool)
    if k == 0:
        return passa
    pp = np.where(np.isfinite(p), p, np.inf)
    ordine = np.argsort(pp, kind="stable")
    ok = pp[ordine] <= q * np.arange(1, k + 1) / k
    if ok.any():
        passa[ordine[: int(np.flatnonzero(ok).max()) + 1]] = True
    return passa


def _p_una_coda(t: float) -> float:
    return 1.0 - _NORMALE.cdf(t) if np.isfinite(t) else np.nan


def _motivo(r) -> str:
    """Il primo controllo che un non candidato non supera."""
    if not np.isfinite(r["t_netto"]):
        return "non misurabile (troppo pochi casi)"
    if r["t_netto"] <= 0:
        return "non fa meglio del mercato"
    if not r["bh"]:
        return "non supera la quota di falsi positivi"
    return "non positiva in una delle due metà"


def _gruppo(tabella: pd.DataFrame, serie: dict, rho_max: float) -> pd.DataFrame:
    """
    Il gruppo suggerito, dal t piu' alto in giu' fra i `candidata`: entra chi
    e' di una famiglia nuova e ha |rho| <= rho_max con tutti i gia' presi.
    Aggiunge le colonne nella_rosa, rho_max (il |rho| piu' alto con gli altri
    membri della rosa) e perche (il motivo, per chi resta fuori).
    """
    t = tabella.copy()
    t["nella_rosa"] = False
    t["rho_max"] = np.nan
    t["perche"] = ""
    giorni = sorted(set().union(*[set(v.index) for v in serie.values()])) if serie else []
    giorni = pd.Index(giorni)
    allineate = {k: v.reindex(giorni, fill_value=0.0) for k, v in serie.items()}

    def rho(a, b):
        x, y = allineate[a].to_numpy(), allineate[b].to_numpy()
        if x.std() == 0 or y.std() == 0:
            return 0.0
        return float(np.corrcoef(x, y)[0, 1])

    presi, famiglie_prese = [], {}
    for i in t.sort_values("t_netto", ascending=False).index:
        r = t.loc[i]
        if not r["candidata"]:
            t.loc[i, "perche"] = _motivo(r)
            continue
        nome = r["candidato"]
        if r["famiglia"] in famiglie_prese:
            t.loc[i, "perche"] = f"famiglia già nella rosa ({famiglie_prese[r['famiglia']]})"
            continue
        rhos = {p: rho(nome, p) for p in presi}
        troppo = {p: v for p, v in rhos.items() if abs(v) > rho_max}
        if troppo:
            p, v = max(troppo.items(), key=lambda kv: abs(kv[1]))
            t.loc[i, "perche"] = f"correlata con {p} (rho {v:+.2f})"
            continue
        presi.append(nome)
        famiglie_prese[r["famiglia"]] = nome
        t.loc[i, "nella_rosa"] = True
    for i in t.index:
        nome = t.loc[i, "candidato"]
        altri = [p for p in presi if p != nome]
        if altri and nome in allineate:
            t.loc[i, "rho_max"] = max(abs(rho(nome, p)) for p in altri)
    return t


def _controlla_baseline(baseline: str) -> str:
    if baseline not in ("oraria", "globale"):
        raise ValueError("baseline deve essere 'oraria' o 'globale'.")
    return baseline


def _controlla_unita(unita: str, unita_extra) -> tuple[str, list[str]]:
    """L'unita' che decide e le altre da mostrare accanto (20/10/2026, docs/63 §4)."""
    if unita not in UNITA:
        raise ValueError(f"unita deve essere una di {UNITA}.")
    if unita_extra is None:                     # le altre due, nell'ordine di UNITA
        unita_extra = [u for u in UNITA if u != unita]
    extra = [u for u in unita_extra if u != unita]
    for u in extra:
        if u not in UNITA:
            raise ValueError(f"unita_extra: {u!r} non e' una di {UNITA}.")
    return unita, extra


def _atr_su(df_is: pd.DataFrame, atr) -> np.ndarray:
    """L'ATR giornaliero a 5 giornate chiuse allineato a df_is (None = calcolato su df_is)."""
    if atr is None:
        from .indicatori import atr_giornaliero_chiuso
        atr = atr_giornaliero_chiuso(df_is)
    return pd.Series(atr).reindex(df_is.index).to_numpy(dtype=float)


def _ordina(t: pd.DataFrame) -> pd.DataFrame:
    return (t.sort_values(["nella_rosa", "candidata", "t_netto"], ascending=False)
            .reset_index(drop=True))


# ========================================================================
# Rosa delle entry (dopo l'event study)
# ========================================================================

def rosa_entry(df_is: pd.DataFrame, H: int, pip: float, nomi=None,
               q: float = Q_ROSA, soglia_famiglia: float = SOGLIA_FAMIGLIA,
               rho_max: float = RHO_MAX, min_eventi: int = MIN_EVENTI,
               quarantena=True, baseline: str = "oraria",
               fuso: str = FUSO_PREDEFINITO, unita: str = "pips",
               unita_extra=None, atr=None) -> pd.DataFrame:
    """
    La rosa delle entry sull'in-sample, a orizzonte H. Stessa convenzione
    dell'event study: trigger sulla barra i, ingresso a Open[i+1], misura a
    Close[i+H], ogni occorrenza contata, quarantena applicata.

    df_is        l'IN-SAMPLE con gli indicatori (split_is_oos)
    H            l'orizzonte gia' scelto (non si sceglie qui)
    pip          il pip fisso del symbol (engine/simboli.py, pip_symbol)
    nomi         le entry da considerare; None = tutte le registrate tranne
                 le metro e le composite in OR
    min_eventi   sotto questa soglia l'entry non si misura (come MIN_TRADES
                 dell'event study)
    baseline     "oraria" (predefinito): il mercato e' la media della fascia
                 oraria di ogni trigger; "globale": la media di tutte le barre
    fuso         il fuso delle fasce (engine/stagionalita.fuso_profilo(symbol))
    unita        l'unita' che DECIDE (20/10/2026, docs/63 §4): "pips" (come
                 prima), "bp" (punti base del prezzo d'ingresso) o "atr"
                 (multipli dell'ATR giornaliero noto al segnale)
    unita_extra  le unita' misurate accanto, solo da mostrare: colonne
                 scarto_<u>, t_<u>, due_meta_<u>; None = le altre due
    atr          la serie di indicatori.atr_giornaliero_chiuso (meglio sullo
                 storico intero); None = calcolata su df_is

    Con unita="pips" i numeri delle colonne di prima sono identici.

    Una riga per entry misurata:
        candidato, direction, eventi
        scarto_<unita> media a H barre meno il mercato nello stesso verso
        t_netto, p     t dello scarto e p a una coda
        bh             passa il controllo della quota di falsi positivi a q
        due_meta       scarto positivo su entrambe le meta' dell'in-sample
        candidata      t > 0, bh e due_meta
        famiglia       numero della famiglia (engine/famiglie.py)
        nella_rosa     nel gruppo suggerito
        rho_max        |rho| piu' alto con gli altri membri della rosa
        perche         perche' e' fuori dalla rosa: il primo controllo non superato,
                       oppure la famiglia o la correlazione con un membro
        scarto_globale_<unita>, t_globale
                       (solo con baseline oraria) lo stesso confronto con la media
                       di tutte le barre, per vedere quanto conta l'ora
    In .attrs: k (entry misurate), q, rho_max, H, scartate (sotto min_eventi),
    baseline, fuso, unita.
    """
    oraria = _controlla_baseline(baseline) == "oraria"
    unita, extra = _controlla_unita(unita, unita_extra)
    H = int(H)
    if H < 1:
        raise ValueError("H deve essere almeno 1 barra.")
    if pip is None or not float(pip) > 0:
        raise ValueError("pip obbligatorio: il pip fisso del symbol (engine/simboli.py).")
    pip = float(pip)
    if nomi is None:
        nomi = _entry_vere()
    nomi = list(nomi)

    n = len(df_is)
    close = df_is["Close"].to_numpy(dtype=float)
    open_ = df_is["Open"].to_numpy(dtype=float)
    ingresso = np.full(n, np.nan)
    ingresso[: n - 1] = open_[1:]
    fwd = np.full(n, np.nan)                      # rendimento long a H barre, in pips
    if n > H:
        fwd[: n - H] = (close[H:] - ingresso[: n - H]) / pip
    valido = np.isfinite(fwd) & np.isfinite(ingresso) & (ingresso > 0)
    pulito = maschera_segnali_puliti(df_is, quarantena)
    meta = n // 2
    prima = np.arange(n) < meta
    giorno = np.asarray(giorno_fx(df_is))
    uscita = np.minimum(np.arange(n) + H, n - 1)
    codici = fasce_orarie(df_is.index, fuso)[0] if oraria else None
    atr_is = _atr_su(df_is, atr) if "atr" in (unita, *extra) else None

    def mercato_in(u: str) -> dict:
        """Rendimenti, mercato e barre utili nell'unita' u."""
        f = in_unita(fwd, u, pip, prezzo=ingresso, atr=atr_is)
        usa = valido & pulito & np.isfinite(f)
        return dict(fwd=f, mercato=float(np.nanmean(f)),
                    mercato_meta=(float(np.nanmean(f[:meta])), float(np.nanmean(f[meta:]))),
                    usa=usa, usa_meta=(usa & prima, usa & ~prima))

    def misura(M: dict, pos: np.ndarray, d: int) -> dict:
        """Scarto, t e due meta' di un trigger nell'unita' di M (stesse formule di prima)."""
        f = M["fwd"]
        pos = pos[np.isfinite(f[pos])]          # in ATR: niente valore nelle prime giornate
        if pos.size < 2:
            return dict(scarto=np.nan, t=np.nan, due_meta=False, globale=np.nan,
                        t_globale=np.nan, v=None, pos=pos)
        v = d * f[pos]
        se = _errore_standard_sovrapposti(v, pos, H)
        scarto = float(v.mean()) - d * M["mercato"]
        t = scarto / se if (np.isfinite(se) and se > 0) else np.nan
        a, b = prima[pos], ~prima[pos]
        out = dict(globale=scarto, t_globale=t, v=v, pos=pos)
        if oraria:
            scarto, se_o = scarto_orario(f, codici, M["usa"], pos, d, H)
            t = scarto / se_o if (np.isfinite(se_o) and se_o > 0) else np.nan
            dm = bool(a.any() and b.any()
                      and scarto_orario(f, codici, M["usa_meta"][0], pos[a], d, H)[0] > 0
                      and scarto_orario(f, codici, M["usa_meta"][1], pos[b], d, H)[0] > 0)
        else:
            dm = bool(a.any() and b.any()
                      and v[a].mean() - d * M["mercato_meta"][0] > 0
                      and v[b].mean() - d * M["mercato_meta"][1] > 0)
        out.update(scarto=scarto, t=t, due_meta=dm)
        return out

    mercati = {u: mercato_in(u) for u in (unita, *extra)}

    righe, serie, scartate = [], {}, []
    for nome in nomi:
        d = int(_reg.get_entry_direction(nome))
        m = _reg.get_entry(nome)(df_is).fillna(False).to_numpy(dtype=bool) & valido & pulito
        pos = np.flatnonzero(m)
        if pos.size < max(int(min_eventi), 2):
            scartate.append((nome, int(pos.size)))
            continue
        r = misura(mercati[unita], pos, d)
        riga = {"candidato": nome, "direction": d, "eventi": int(pos.size)}
        if oraria:
            riga.update({f"scarto_globale_{unita}": r["globale"], "t_globale": r["t_globale"]})
        riga.update({f"scarto_{unita}": r["scarto"], "t_netto": r["t"], "p": _p_una_coda(r["t"]),
                     "due_meta": r["due_meta"]})
        for u in extra:
            x = misura(mercati[u], pos, d)
            riga.update({f"scarto_{u}": x["scarto"], f"t_{u}": x["t"], f"due_meta_{u}": x["due_meta"]})
        righe.append(riga)
        if r["v"] is not None:
            serie[nome] = pd.Series(r["v"], index=giorno[uscita[r["pos"]]]).groupby(level=0).sum()

    colonne = ["candidato", "direction", "eventi", f"scarto_{unita}", "t_netto", "p", "bh",
               "due_meta", "candidata", "famiglia", "nella_rosa", "rho_max", "perche"]
    if oraria:
        colonne += [f"scarto_globale_{unita}", "t_globale"]
    for u in extra:
        colonne += [f"scarto_{u}", f"t_{u}", f"due_meta_{u}"]
    info = dict(q=q, rho_max=rho_max, H=H, scartate=scartate,
                baseline=baseline, fuso=fuso if oraria else None, unita=unita)
    if not righe:
        vuota = pd.DataFrame(columns=colonne)
        vuota.attrs.update(k=0, **info)
        return vuota
    t = pd.DataFrame(righe)
    t["bh"] = benjamini_hochberg(t["p"].to_numpy(), q)
    t["candidata"] = (t["t_netto"] > 0) & t["bh"] & t["due_meta"]
    fam = famiglie(df_is, "entry", nomi=list(t["candidato"]), soglia=soglia_famiglia)
    t["famiglia"] = t["candidato"].map(fam.set_index("nome")["famiglia"]).astype(int)
    t = _ordina(_gruppo(t, serie, rho_max))[colonne]
    t.attrs.update(k=len(t), **info)
    return t


def _entry_vere() -> list[str]:
    """Le entry del registro senza le metro e senza le composite in OR."""
    esclusi = set()
    try:
        from entry_metro import NOMI_METRO
        esclusi |= set(NOMI_METRO)
    except ImportError:
        pass
    try:
        from entry_composita import elenca_composite
        esclusi |= set(elenca_composite())
    except ImportError:
        pass
    # le entry a orario (ORA_LONG_@HH:MM, 19/10/2026) si registrano solo su richiesta
    from condizioni_orarie import e_oraria
    return [n for n in _reg.list_entries() if n not in esclusi and not e_oraria(n)]


# ========================================================================
# Rosa dei sistemi (dopo la ricerca delle uscite, prima dei filtri)
# ========================================================================

def _famiglia_sistemi(df_is, risultati: pd.DataFrame, soglia: float) -> pd.Series:
    """
    La famiglia di un sistema e' la terna (famiglia dell'entry long, famiglia
    dell'entry short, famiglia della regola di uscita): due sistemi sono la
    stessa idea se coincidono tutte e tre. Lato spento o uscita solo a tempo
    = «—». Restituisce un'etichetta per riga, es. «L2·S5·X1».
    """
    def per_tipo(nomi, tipo):
        nomi = sorted({x for x in nomi if isinstance(x, str)})
        if not nomi:
            return {}
        f = famiglie(df_is, tipo, nomi=nomi, soglia=soglia)
        return f.set_index("nome")["famiglia"].to_dict()

    entrate = per_tipo(list(risultati["entry_long"]) + list(risultati["entry_short"]), "entry")
    coppie = {p: el for p, el, _ in _reg.list_exit_pairs()}
    uscite_l = {p: coppie.get(p) for p in risultati["exit_rule_pair"] if isinstance(p, str)}
    fam_u = per_tipo([x for x in uscite_l.values() if x], "exit")

    def etichetta(r):
        el = entrate.get(r["entry_long"]) if isinstance(r["entry_long"], str) else None
        es = entrate.get(r["entry_short"]) if isinstance(r["entry_short"], str) else None
        p = r["exit_rule_pair"]
        x = fam_u.get(uscite_l.get(p)) if isinstance(p, str) else None
        return "·".join(f"{c}{v if v is not None else '—'}" for c, v in (("L", el), ("S", es), ("X", x)))

    return risultati.apply(etichetta, axis=1)


def rosa_sistemi(es, df_is: pd.DataFrame, pip: float, commission: float = 0.0,
                 q: float = Q_ROSA, soglia_famiglia: float = SOGLIA_FAMIGLIA,
                 rho_max: float = RHO_MAX, min_trades: int | None = None,
                 baseline: str = "oraria", fuso: str = FUSO_PREDEFINITO,
                 unita: str = "pips", unita_extra=None, atr=None) -> pd.DataFrame:
    """
    La rosa dei sistemi completi, sui trade veri di una ricerca delle uscite
    (`run_exit_search_bt` sull'IN-SAMPLE). Ogni combinazione e' un sistema.

    es           il risultato di run_exit_search_bt (sull'in-sample)
    df_is        lo stesso in-sample (serve per la deriva del mercato, le
                 famiglie e le giornate FX)
    pip          il pip fisso del symbol
    commission   come nei costi del backtest (i pips sono NETTI)
    min_trades   sotto questa soglia il sistema non si misura (conta comunque
                 fra le prove, con p = 1); None = quella della ricerca
    baseline     "oraria" (predefinito): la deriva tolta a ogni trade e' quella
                 tipica delle fasce orarie in cui e' rimasto aperto; "globale":
                 la variazione media di una barra, uguale a ogni ora
    fuso         il fuso delle fasce (engine/stagionalita.fuso_profilo(symbol))
    unita, unita_extra, atr
                 come rosa_entry (20/10/2026, docs/63 §4): lo scarto di ogni
                 trade in pips si converte nell'unita' col SUO prezzo
                 d'ingresso (bp) o con l'ATR alla barra del segnale (atr).
                 Con unita="pips" i numeri di prima sono identici.

    Lo scarto di ogni trade e' il suo guadagno netto meno la deriva del
    mercato nel suo verso per le barre in cui e' rimasto aperto (deriva = la
    variazione media di una barra sull'in-sample, in pips). I trade di un
    sistema non si sovrappongono (una posizione alla volta): il t e' quello
    classico. Le due meta' si dividono sulla data d'ingresso.

    Colonne come rosa_entry, con `combinazione` al posto di `candidato`,
    `trades` al posto di `eventi` e `famiglia` nella forma «L2·S5·X1».
    """
    oraria = _controlla_baseline(baseline) == "oraria"
    unita, extra = _controlla_unita(unita, unita_extra)
    if pip is None or not float(pip) > 0:
        raise ValueError("pip obbligatorio: il pip fisso del symbol (engine/simboli.py).")
    pip = float(pip)
    risultati = es.risultati
    atr_is = (pd.Series(_atr_su(df_is, atr), index=df_is.index)
              if "atr" in (unita, *extra) else None)

    def fattore(tr, u: str) -> np.ndarray:
        """Da pips all'unita' u, trade per trade (NaN dove l'ATR non c'e')."""
        if u == "pips":
            return np.ones(len(tr))
        if u == "bp":
            return pip * 10_000.0 / tr["EntryPrice"].to_numpy(dtype=float)
        a = atr_alla_entrata(tr, atr_is).to_numpy(dtype=float)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(a > 0, pip / a, np.nan)
    min_trades = es.min_trades if min_trades is None else int(min_trades)
    open_ = df_is["Open"].to_numpy(dtype=float)
    deriva = float(np.nanmean(np.diff(open_))) / pip       # pips per barra, verso long
    if oraria:
        # deriva cumulata per fascia oraria: D[j] = somma delle derive delle barre < j
        cumulata = np.concatenate([[0.0], np.cumsum(deriva_per_barra_oraria(df_is, pip, fuso))])
    meta = df_is.index[len(df_is) // 2]
    giorno = pd.Series(np.asarray(giorno_fx(df_is)), index=df_is.index)

    def misura(x_glob, x, f, ingresso) -> dict:
        """Scarto, t e due meta' nell'unita' del fattore f (stesse formule di prima)."""
        ok = np.isfinite(f)
        xg, xo, ing = x_glob[ok] * f[ok], x[ok] * f[ok], ingresso[ok]
        if xo.size < 2:
            return dict(globale=np.nan, t_globale=np.nan, scarto=np.nan, t=np.nan, due_meta=False)
        a, b = xo[ing < meta], xo[ing >= meta]
        return dict(globale=float(np.mean(xg)), t_globale=t_stat(xg), scarto=float(np.mean(xo)),
                    t=t_stat(xo), due_meta=bool(a.size and b.size and a.mean() > 0 and b.mean() > 0))

    righe, serie = [], {}
    for _, r in risultati.iterrows():
        comb = r["combinazione"]
        tr = es.trades(comb)
        riga = {"candidato": comb, "trades": int(len(tr)), f"scarto_{unita}": np.nan,
                "t_netto": np.nan, "p": 1.0, "due_meta": False}
        if oraria:
            riga.update({f"scarto_globale_{unita}": np.nan, "t_globale": np.nan})
        for u in extra:
            riga.update({f"scarto_{u}": np.nan, f"t_{u}": np.nan, f"due_meta_{u}": False})
        if len(tr) >= max(min_trades, 2):
            _, netti = pips_per_trade(tr, pip, commission)
            segno = np.where(tr["Size"].to_numpy() > 0, 1, -1)
            barre = (tr["ExitBar"] - tr["EntryBar"]).to_numpy(dtype=float)
            x_glob = netti.to_numpy(dtype=float) - segno * deriva * barre
            x = x_glob
            if oraria:
                ing = tr["EntryBar"].to_numpy(dtype=int)
                usc = tr["ExitBar"].to_numpy(dtype=int)
                x = netti.to_numpy(dtype=float) - segno * (cumulata[usc] - cumulata[ing])
            ingresso = pd.DatetimeIndex(tr["EntryTime"])
            f = fattore(tr, unita)
            m = misura(x_glob, x, f, ingresso)
            if oraria:
                riga.update({f"scarto_globale_{unita}": m["globale"], "t_globale": m["t_globale"]})
            riga.update({f"scarto_{unita}": m["scarto"], "t_netto": m["t"], "p": _p_una_coda(m["t"]),
                         "due_meta": m["due_meta"]})
            for u in extra:
                mu = misura(x_glob, x, fattore(tr, u), ingresso)
                riga.update({f"scarto_{u}": mu["scarto"], f"t_{u}": mu["t"], f"due_meta_{u}": mu["due_meta"]})
            g = giorno.reindex(pd.DatetimeIndex(tr["ExitTime"])).to_numpy()
            ok = np.isfinite(f)
            serie[comb] = pd.Series((netti.to_numpy(dtype=float) * f)[ok], index=g[ok]).groupby(level=0).sum()
        righe.append(riga)

    colonne = ["candidato", "trades", f"scarto_{unita}", "t_netto", "p", "bh", "due_meta",
               "candidata", "famiglia", "nella_rosa", "rho_max", "perche"]
    if oraria:
        colonne += [f"scarto_globale_{unita}", "t_globale"]
    for u in extra:
        colonne += [f"scarto_{u}", f"t_{u}", f"due_meta_{u}"]
    info = dict(q=q, rho_max=rho_max, baseline=baseline, fuso=fuso if oraria else None, unita=unita)
    if not righe:
        vuota = pd.DataFrame(columns=colonne)
        vuota.attrs.update(k=0, **info)
        return vuota.rename(columns={"candidato": "combinazione"})
    t = pd.DataFrame(righe)
    t["p"] = t["p"].fillna(1.0)
    t["bh"] = benjamini_hochberg(t["p"].to_numpy(), q)
    t["candidata"] = (t["t_netto"] > 0) & t["bh"] & t["due_meta"]
    t["famiglia"] = _famiglia_sistemi(df_is, risultati, soglia_famiglia).to_numpy()
    t = _ordina(_gruppo(t, serie, rho_max))[colonne]
    t.attrs.update(k=len(t), **info)
    return t.rename(columns={"candidato": "combinazione"})
