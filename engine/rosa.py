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

Modulo ADDITIVO: non modifica nessun file esistente dell'engine.
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
from .metriche import pips_per_trade
from .quarantena_trade import maschera_segnali_puliti

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


def _ordina(t: pd.DataFrame) -> pd.DataFrame:
    return (t.sort_values(["nella_rosa", "candidata", "t_netto"], ascending=False)
            .reset_index(drop=True))


# ========================================================================
# Rosa delle entry (dopo l'event study)
# ========================================================================

def rosa_entry(df_is: pd.DataFrame, H: int, pip: float, nomi=None,
               q: float = Q_ROSA, soglia_famiglia: float = SOGLIA_FAMIGLIA,
               rho_max: float = RHO_MAX, min_eventi: int = MIN_EVENTI,
               quarantena=True) -> pd.DataFrame:
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

    Una riga per entry misurata:
        candidato, direction, eventi
        scarto_pips    media a H barre meno il mercato nello stesso verso, in pips
        t_netto, p     t dello scarto e p a una coda
        bh             passa il controllo della quota di falsi positivi a q
        due_meta       scarto positivo su entrambe le meta' dell'in-sample
        candidata      t > 0, bh e due_meta
        famiglia       numero della famiglia (engine/famiglie.py)
        nella_rosa     nel gruppo suggerito
        rho_max        |rho| piu' alto con gli altri membri della rosa
        perche         perche' e' fuori dalla rosa: il primo controllo non superato,
                       oppure la famiglia o la correlazione con un membro
    In .attrs: k (entry misurate), q, rho_max, H, scartate (sotto min_eventi).
    """
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
    mercato = float(np.nanmean(fwd))
    mercato_meta = (float(np.nanmean(fwd[:meta])), float(np.nanmean(fwd[meta:])))
    giorno = np.asarray(giorno_fx(df_is))
    uscita = np.minimum(np.arange(n) + H, n - 1)

    righe, serie, scartate = [], {}, []
    for nome in nomi:
        d = int(_reg.get_entry_direction(nome))
        m = _reg.get_entry(nome)(df_is).fillna(False).to_numpy(dtype=bool) & valido & pulito
        pos = np.flatnonzero(m)
        if pos.size < max(int(min_eventi), 2):
            scartate.append((nome, int(pos.size)))
            continue
        v = d * fwd[pos]
        se = _errore_standard_sovrapposti(v, pos, H)
        scarto = float(v.mean()) - d * mercato
        t = scarto / se if (np.isfinite(se) and se > 0) else np.nan
        a, b = prima[pos], ~prima[pos]
        dm = bool(a.any() and b.any()
                  and v[a].mean() - d * mercato_meta[0] > 0
                  and v[b].mean() - d * mercato_meta[1] > 0)
        righe.append({"candidato": nome, "direction": d, "eventi": int(pos.size),
                      "scarto_pips": scarto, "t_netto": t, "p": _p_una_coda(t),
                      "due_meta": dm})
        serie[nome] = pd.Series(v, index=giorno[uscita[pos]]).groupby(level=0).sum()

    colonne = ["candidato", "direction", "eventi", "scarto_pips", "t_netto", "p", "bh",
               "due_meta", "candidata", "famiglia", "nella_rosa", "rho_max", "perche"]
    if not righe:
        vuota = pd.DataFrame(columns=colonne)
        vuota.attrs.update(k=0, q=q, rho_max=rho_max, H=H, scartate=scartate)
        return vuota
    t = pd.DataFrame(righe)
    t["bh"] = benjamini_hochberg(t["p"].to_numpy(), q)
    t["candidata"] = (t["t_netto"] > 0) & t["bh"] & t["due_meta"]
    fam = famiglie(df_is, "entry", nomi=list(t["candidato"]), soglia=soglia_famiglia)
    t["famiglia"] = t["candidato"].map(fam.set_index("nome")["famiglia"]).astype(int)
    t = _ordina(_gruppo(t, serie, rho_max))[colonne]
    t.attrs.update(k=len(t), q=q, rho_max=rho_max, H=H, scartate=scartate)
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
    return [n for n in _reg.list_entries() if n not in esclusi]


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
                 rho_max: float = RHO_MAX, min_trades: int | None = None) -> pd.DataFrame:
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

    Lo scarto di ogni trade e' il suo guadagno netto meno la deriva del
    mercato nel suo verso per le barre in cui e' rimasto aperto (deriva = la
    variazione media di una barra sull'in-sample, in pips). I trade di un
    sistema non si sovrappongono (una posizione alla volta): il t e' quello
    classico. Le due meta' si dividono sulla data d'ingresso.

    Colonne come rosa_entry, con `combinazione` al posto di `candidato`,
    `trades` al posto di `eventi` e `famiglia` nella forma «L2·S5·X1».
    """
    if pip is None or not float(pip) > 0:
        raise ValueError("pip obbligatorio: il pip fisso del symbol (engine/simboli.py).")
    pip = float(pip)
    risultati = es.risultati
    min_trades = es.min_trades if min_trades is None else int(min_trades)
    open_ = df_is["Open"].to_numpy(dtype=float)
    deriva = float(np.nanmean(np.diff(open_))) / pip       # pips per barra, verso long
    meta = df_is.index[len(df_is) // 2]
    giorno = pd.Series(np.asarray(giorno_fx(df_is)), index=df_is.index)

    righe, serie = [], {}
    for _, r in risultati.iterrows():
        comb = r["combinazione"]
        tr = es.trades(comb)
        riga = {"candidato": comb, "trades": int(len(tr)), "scarto_pips": np.nan,
                "t_netto": np.nan, "p": 1.0, "due_meta": False}
        if len(tr) >= max(min_trades, 2):
            _, netti = pips_per_trade(tr, pip, commission)
            segno = np.where(tr["Size"].to_numpy() > 0, 1, -1)
            barre = (tr["ExitBar"] - tr["EntryBar"]).to_numpy(dtype=float)
            x = netti.to_numpy(dtype=float) - segno * deriva * barre
            t = t_stat(x)
            ingresso = pd.DatetimeIndex(tr["EntryTime"])
            a, b = x[ingresso < meta], x[ingresso >= meta]
            riga.update(scarto_pips=float(np.mean(x)), t_netto=t, p=_p_una_coda(t),
                        due_meta=bool(a.size and b.size and a.mean() > 0 and b.mean() > 0))
            g = giorno.reindex(pd.DatetimeIndex(tr["ExitTime"])).to_numpy()
            serie[comb] = pd.Series(netti.to_numpy(dtype=float), index=g).groupby(level=0).sum()
        righe.append(riga)

    colonne = ["candidato", "trades", "scarto_pips", "t_netto", "p", "bh", "due_meta",
               "candidata", "famiglia", "nella_rosa", "rho_max", "perche"]
    if not righe:
        vuota = pd.DataFrame(columns=colonne)
        vuota.attrs.update(k=0, q=q, rho_max=rho_max)
        return vuota.rename(columns={"candidato": "combinazione"})
    t = pd.DataFrame(righe)
    t["p"] = t["p"].fillna(1.0)
    t["bh"] = benjamini_hochberg(t["p"].to_numpy(), q)
    t["candidata"] = (t["t_netto"] > 0) & t["bh"] & t["due_meta"]
    t["famiglia"] = _famiglia_sistemi(df_is, risultati, soglia_famiglia).to_numpy()
    t = _ordina(_gruppo(t, serie, rho_max))[colonne]
    t.attrs.update(k=len(t), q=q, rho_max=rho_max)
    return t.rename(columns={"candidato": "combinazione"})
