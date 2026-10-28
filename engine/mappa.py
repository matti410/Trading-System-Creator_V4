"""
La mappa delle anomalie (27/10/2026, docs/73 parte B, schede in docs/74).

A COSA SERVE
------------
Il Lab parte dai trigger e chiede se funzionano. La mappa rovescia l'ordine:
una scheda (engine/ipotesi.py) dice PRIMA di guardare i dati dove il mercato
dovrebbe smettere di essere casuale, e qui si misura se la fascia dichiarata
risponde nel verso dichiarato. Solo sull'in-sample dello studio.

LE FASCE (docs/73 §B.3)
-----------------------
Variabile continua: 5 quintili, con le soglie calcolate sulle sole barre
PRIMA della barra i, in una finestra di `finestra_giorni` giorni; finche' la
finestra non e' piena la barra non ha fascia. Variabile di calendario: le
categorie della scheda. La variabile alla barra i e' nota al Close di i.

LA MISURA, stessa convenzione della rosa (engine/rosa.py)
---------------------------------------------------------
Segnale sulla barra i, ingresso a Open[i+1], misura a Close[i+h], quarantena
applicata. Per ogni fascia: lo scarto dal mercato di riferimento (della
stessa ora, o di qualunque ora) con lo stesso modello di stagionalita.scarto_orario
(il rumore del riferimento compreso), ma con l'incertezza dei rendimenti
sovrapposti SENZA lo sconto dei pesi decrescenti (scarto_mappa, decisione di
Mattia del 28/10/2026: lo sconto la sottostimava con le variabili persistenti; dal 28/10
la stessa funzione del Lab, stagionalita.errore_sovrapposti); il t; le due
meta' dell'in-sample; il netto dei costi, solo da leggere. Minimi: 200 barre
e 100 giornate diverse; sotto, la fascia non si misura e non si conta.

IL VERDETTO
-----------
Guarda solo le fasce ATTESE nel verso ATTESO: «risponde» se una supera la
quota di falsi positivi (Benjamini-Hochberg, q = 20%, sulle fasce misurate
della scheda), le due meta' e i minimi. Un segno opposto, o una fascia non
dichiarata, si mostrano ma non contano come scoperta.

IL CONTO (docs/73 §B.4, docs/74)
--------------------------------
Ogni fascia misurata e' una prova, piu' le prove gia' viste della scheda
(M01: le 96 fasce del profilo 2a) e, se il segno e' stato scelto dopo aver
visto i dati (M07), le fasce della versione opposta. La voce va nel giornale
dello studio come «prova» con dove = "mappa": il Lab la ritrova.

I risultati collaudano il tool: non sono verdetti sul mercato.

Modulo ADDITIVO: non modifica nessun file esistente dell'engine.
"""
from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd

from . import indicatori as ind
from .famiglie import LIFT_MIN, SOGLIA_DOPPIONE
from .ipotesi import QUALUNQUE_ORA, QUINTILI, SCHEDE, Scheda
from .quarantena import passo_barre
from .quarantena_trade import maschera_segnali_puliti
from .rosa import MIN_EVENTI, Q_ROSA, benjamini_hochberg
from .stagionalita import errore_sovrapposti, fasce_orarie, in_unita, media_per_fascia, rendimenti_avanti

MIN_BARRE = MIN_EVENTI          # 200, come la rosa e l'atlante
MIN_GIORNATE = 100              # docs/50 §8: sotto circa 100 occorrenze
FUSO = "UTC"                    # le crypto: la giornata e le fasce orarie in UTC

RISPONDE = "risponde nel verso atteso"
NON_RISPONDE = "non risponde"
OPPOSTO = "segno opposto: non conta come scoperta"
POCHI = "troppo pochi casi"
FUORI = "fuori ipotesi"
DOPPIONE = "non misurata: doppione"

_NORMALE = NormalDist()

# le variabili delle schede: nome -> funzione di (df, df_btc)
VARIABILI = {
    "funding_segno_prima_pagamento": lambda df, btc: ind.funding_segno_prima_pagamento(df),
    "funding_liquidato": lambda df, btc: ind.funding_liquidato(df),
    "funding_rispetto_al_base": lambda df, btc: ind.funding_rispetto_al_base(df),   # M04 dal 28/10/2026
    "basis_bp": lambda df, btc: ind.basis_bp(df),
    "rendimento_4h": lambda df, btc: ind.rendimento_4h(df),
    "scarto_btc_1h": lambda df, btc: ind.scarto_btc_1h(df, btc),
}


# ========================================================================
# Dati, variabile, fasce
# ========================================================================

def prepara_df(df_is: pd.DataFrame, funding: pd.DataFrame | None = None,
               spot: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    L'in-sample con le colonne del funding e dello spot (exchange.colonne_perpetual).
    I tassi e i prezzi spot si agganciano solo alle barre di `df_is`: niente di
    quello che viene dopo l'ultima barra dell'in-sample entra (test 14 di test_mappa).
    """
    from .exchange import colonne_perpetual
    if funding is None and spot is None:
        return df_is
    return colonne_perpetual(df_is, funding=funding, spot=spot)


def barre_orizzonte(ore: float, index) -> int:
    """Le barre del timeframe in `ore` ore; si ferma se non sono un numero intero (1 ora su H4)."""
    minuti = passo_barre(pd.DatetimeIndex(index)) / pd.Timedelta(minutes=1)
    barre = float(ore) * 60.0 / minuti
    if barre < 1 or not float(barre).is_integer():
        raise ValueError(f"Orizzonte di {ore} ore su barre da {minuti:g} minuti: non è un numero intero di barre. "
                         "La scheda non si misura su questo timeframe.")
    return int(barre)


def adatta(scheda: Scheda, symbol: str) -> str | None:
    """None se la scheda si misura su `symbol`, altrimenti il motivo (mercato, moneta)."""
    from .exchange import parti_symbol
    p = parti_symbol(symbol)
    if p["mercato"] not in scheda.mercati:
        return f"{scheda.id} si misura solo su {' e '.join(scheda.mercati)}: {symbol} è {p['mercato']}"
    if p["base"] in scheda.escludi_monete:
        return f"{scheda.id} non si misura su {p['base']}"
    return None


def simbolo_btc(symbol: str) -> str:
    """BTC dello stesso exchange e dello stesso mercato (M06: perpetual con perpetual, spot con spot)."""
    from .exchange import parti_symbol
    p = parti_symbol(symbol)
    if p["base"] == "BTC":
        raise ValueError(f"{symbol} è già BTC: la scheda di BTC che anticipa le altcoin non si misura qui.")
    return f"{p['exchange']}_{p['mercato']}_BTC{p['quotata']}"


def variabile(scheda: Scheda, df: pd.DataFrame, df_btc: pd.DataFrame | None = None) -> pd.Series:
    """La variabile della scheda sulle barre di `df` (gia' preparato con prepara_df)."""
    if scheda.variabile not in VARIABILI:
        raise ValueError(f"{scheda.id}: variabile {scheda.variabile!r} sconosciuta (mappa.VARIABILI).")
    if "btc" in scheda.serve and df_btc is None:
        raise ValueError(f"{scheda.id} vuole il dataset di BTC dello stesso exchange e mercato (df_btc).")
    if "funding" in scheda.serve and "funding_tasso" not in df.columns:
        raise ValueError(f"{scheda.id} vuole il funding: prepara_df(df_is, funding=...).")
    if "spot" in scheda.serve and "spot_close" not in df.columns:
        raise ValueError(f"{scheda.id} vuole lo spot della stessa coppia: prepara_df(df_is, spot=...).")
    if scheda.variabile == "funding_segno_prima_pagamento" and not ind.barre_prima_del_pagamento(df.index).any():
        raise ValueError(f"{scheda.id}: su questo timeframe nessuna barra chiude un'ora prima di un pagamento del "
                         "funding (00:00, 08:00, 16:00 UTC). La scheda non si misura.")
    return VARIABILI[scheda.variabile](df, df_btc)


def fasce_quintili(serie: pd.Series, giorni: int = 365) -> np.ndarray:
    """
    Il codice del quintile (0 = Q1 ... 4 = Q5) di ogni barra, con le soglie dei
    quintili calcolate sulle barre degli ultimi `giorni` giorni PRIMA della
    barra (la barra stessa esclusa). NaN dove la variabile manca o la finestra
    non e' ancora piena. Un valore uguale a una soglia va nella fascia sotto.
    """
    s = pd.Series(serie.to_numpy(dtype=float), index=pd.DatetimeIndex(serie.index))
    r = s.rolling(f"{int(giorni)}D", closed="left")
    soglie = np.column_stack([r.quantile(q).to_numpy() for q in (0.2, 0.4, 0.6, 0.8)])
    v = s.to_numpy()
    codice = (v[:, None] > soglie).sum(axis=1).astype(float)
    pieno = (s.index >= s.index[0] + pd.Timedelta(days=int(giorni))) if len(s) else np.zeros(0, bool)
    ok = np.isfinite(v) & np.isfinite(soglie).all(axis=1) & np.asarray(pieno)
    return np.where(ok, codice, np.nan)


QUOTA_FASCIA_MIN, QUOTA_FASCIA_MAX = 0.10, 0.30     # quintili: ogni fascia fra il 10% e il 30% (Mattia, 27/10)


class FasceDegeneri(ValueError):
    """Le fasce a quintili di una scheda non sono quintili veri: la scheda non si misura."""


def controlla_fasce(scheda: Scheda, codici: np.ndarray) -> str | None:
    """
    Il controllo delle fasce (correzione di Mattia del 27/10/2026, PR #82): per
    le schede a quintili ogni fascia deve avere fra il 10% e il 30% delle barre
    che hanno una fascia. Con tanti valori uguali (il funding di Binance fermo al
    livello di base) le soglie coincidono, e le fasce non sono piu' quelle
    dell'ipotesi approvata. None se va bene, altrimenti il motivo con la quota di
    ogni fascia. Usa solo la variabile, non i rendimenti: non e' una prova e non
    entra nel conto. Le schede a categorie non si controllano.
    """
    if scheda.tipo != "quintili":
        return None
    c = codici[np.isfinite(codici)].astype(int)
    if c.size == 0:
        return f"{scheda.id}: nessuna barra ha una fascia (variabile mancante o finestra mai piena)."
    quote = np.bincount(c, minlength=len(scheda.fasce)) / c.size
    if ((quote < QUOTA_FASCIA_MIN) | (quote > QUOTA_FASCIA_MAX)).any():
        dettaglio = ", ".join(f"{f} {q:.1%}" for f, q in zip(scheda.fasce, quote))
        return (f"{scheda.id}: le fasce non sono quintili veri ({dettaglio}; ognuna dovrebbe stare fra il "
                f"{QUOTA_FASCIA_MIN:.0%} e il {QUOTA_FASCIA_MAX:.0%}). Succede con tanti valori uguali: le soglie "
                "coincidono. La scheda non si misura così com'è.")
    return None


def codici_fasce(scheda: Scheda, valori: pd.Series) -> np.ndarray:
    """Il codice della fascia della scheda (indice in scheda.fasce) di ogni barra, NaN se in nessuna."""
    if scheda.tipo == "quintili":
        return fasce_quintili(valori, scheda.finestra_giorni)
    v = valori.to_numpy(dtype=float)
    out = np.full(v.size, np.nan)
    for j, valore in enumerate(scheda.categorie):
        out[np.isclose(v, float(valore))] = j
    return out


# ========================================================================
# La misura
# ========================================================================

# ========================================================================
# L'incertezza della mappa (decisione di Mattia del 28/10/2026)
# ========================================================================

# errore_sovrapposti (le coppie di barre a meno di H per intero, i blocchi di una
# settimana se la varianza esce zero o negativa) dal 28/10/2026 sta in
# stagionalita.py, una funzione sola per la mappa e per il Lab (docs/75 §7):
# stesso codice, numeri della mappa identici al bit.


def scarto_mappa(fwd: np.ndarray, codici: np.ndarray, usa: np.ndarray, pos: np.ndarray, H: int,
                 barre_settimana: int) -> tuple[float, float, bool]:
    """
    Lo scarto medio delle barre `pos` dalla media della loro fascia di riferimento
    (verso long) e la sua incertezza: lo stesso modello di
    stagionalita.scarto_orario (pesi +1/n sulle barre della fascia, meno la quota
    della media di riferimento su ogni barra), con la stessa errore_sovrapposti.
    Ritorna (scarto, errore, a_blocchi).
    """
    b = media_per_fascia(fwd, codici, usa)
    scarto = float(np.mean(fwd[pos] - b[pos]))
    n_t = pos.size
    n_cod = int(codici.max()) + 1
    trig_f = np.bincount(codici[pos], minlength=n_cod).astype(float)
    barre_f = np.bincount(codici, weights=usa.astype(float), minlength=n_cod)
    with np.errstate(invalid="ignore", divide="ignore"):
        quota = np.where(barre_f > 0, trig_f / barre_f, 0.0)
    c = np.where(usa, -quota[codici] / n_t, 0.0)
    c[pos] += 1.0 / n_t
    r = np.where(usa, fwd - b, 0.0)
    r[pos] -= scarto
    se, a_blocchi = errore_sovrapposti(c * r, H, barre_settimana)
    return scarto, se, a_blocchi


def _p(t: float) -> float:
    return 1.0 - _NORMALE.cdf(t) if np.isfinite(t) else np.nan


def _verso(segno: int) -> str:
    return "sopra il mercato (long)" if segno > 0 else "sotto il mercato (short)"


def misura(scheda: Scheda, df: pd.DataFrame, pip: float, valori: pd.Series | None = None,
           df_btc: pd.DataFrame | None = None, costi: dict | None = None,
           funding: pd.DataFrame | None = None, q: float = Q_ROSA, quarantena=True) -> pd.DataFrame:
    """
    Misura la scheda sull'IN-SAMPLE `df` (gia' preparato con prepara_df).

    pip      il pip fisso del symbol (engine/simboli.py)
    valori   la variabile gia' calcolata; None = mappa.variabile(scheda, df, df_btc)
    costi    vetrina.costi_storico (commission, spread, spread_passo_pips): il netto
             dei costi, SOLO DA LEGGERE; None = netto senza costi
    funding  lo storico del funding, per il netto sui perpetual; None = non contato

    Una riga per fascia: fascia, attesa, barre, giornate, misurata, scarto_bp,
    scarto_pips (dal mercato di riferimento, verso long: + = il prezzo fa meglio
    del mercato), t, p (nel verso atteso; per le fasce non attese, il verso piu'
    favorevole), bh, due_meta (scarto nel verso atteso, o long, positivo nelle due
    meta'), incertezza_blocchi (True se la varianza dei rendimenti sovrapposti e'
    uscita zero o negativa e si e' usata la stima a blocchi di una settimana),
    netto_bp, esito. In .attrs: scheda, versione, verdetto, H (barre),
    misurate, conto, riferimento.
    """
    if pip is None or not float(pip) > 0:
        raise ValueError("pip obbligatorio: il pip fisso del symbol (engine/simboli.py).")
    pip = float(pip)
    if valori is None:
        valori = variabile(scheda, df, df_btc)
    H = barre_orizzonte(scheda.orizzonte_ore, df.index)
    codici = codici_fasce(scheda, valori)
    motivo = controlla_fasce(scheda, codici)
    if motivo:
        raise FasceDegeneri(motivo)
    n = len(df)
    idx = pd.DatetimeIndex(df.index)
    ingresso = np.full(n, np.nan)
    ingresso[: n - 1] = df["Open"].to_numpy(dtype=float)[1:]
    uscita = np.full(n, np.nan)
    if n > H:
        uscita[: n - H] = df["Close"].to_numpy(dtype=float)[H:]
    fwd = {"pips": rendimenti_avanti(df, H, pip)}
    fwd["bp"] = in_unita(fwd["pips"], "bp", pip, prezzo=ingresso)
    valido = (np.isfinite(fwd["pips"]) & np.isfinite(fwd["bp"])
              & maschera_segnali_puliti(df, quarantena))
    rif = (np.zeros(n, dtype=np.int64) if scheda.riferimento == QUALUNQUE_ORA
           else fasce_orarie(idx, FUSO)[0].astype(np.int64))
    prima = np.arange(n) < n // 2
    giorno = np.asarray(idx.tz_convert(FUSO).floor("D").asi8)
    settimana = int(round(pd.Timedelta(days=7) / passo_barre(idx)))

    costi = costi or {}
    commissione = float(costi.get("commission") or 0.0)
    spread = float(costi.get("spread") or 0.0)
    passo = float(costi.get("spread_passo_pips") or 0.0)
    with np.errstate(invalid="ignore"):
        costo = (commissione * (ingresso + uscita) + spread * ingresso) / pip + passo
    if funding is not None:
        from .exchange import funding_avanti
        fondo = np.nan_to_num(funding_avanti(df, H, funding, pip))
    else:
        fondo = np.zeros(n)

    righe = []
    for j, nome in enumerate(scheda.fasce):
        attesa = scheda.attese.get(nome, 0)
        d = attesa or 1
        pos = np.flatnonzero((codici == j) & valido)
        barre, giornate = int(pos.size), int(np.unique(giorno[pos]).size)
        misurata = barre >= MIN_BARRE and giornate >= MIN_GIORNATE
        riga = {"fascia": nome, "attesa": _verso(attesa) if attesa else "", "barre": barre,
                "giornate": giornate, "misurata": misurata}
        if misurata:
            for u in ("bp", "pips"):
                s, se, a_blocchi = scarto_mappa(fwd[u], rif, valido, pos, H, settimana)
                riga[f"scarto_{u}"] = s
                if u == "bp":
                    riga["t"] = s / se if (np.isfinite(se) and se > 0) else np.nan
                    riga["incertezza_blocchi"] = a_blocchi
            meta = []
            for m in (prima, ~prima):
                b = media_per_fascia(fwd["bp"], rif, valido & m)
                pm = pos[m[pos]]
                meta.append(float(np.mean(d * (fwd["bp"][pm] - b[pm]))) if pm.size else np.nan)
            riga["due_meta"] = bool(all(np.isfinite(x) and x > 0 for x in meta))
            riga["due_meta_opposto"] = bool(all(np.isfinite(x) and x < 0 for x in meta))
            netto = in_unita(d * fwd["pips"] - costo - d * fondo, "bp", pip, prezzo=ingresso)
            riga["netto_bp"] = float(np.nanmean(netto[pos]))
        righe.append(riga)

    tab = pd.DataFrame(righe)
    for c in ("scarto_bp", "scarto_pips", "t", "netto_bp"):
        if c not in tab.columns:
            tab[c] = np.nan
    for c in ("due_meta", "due_meta_opposto", "incertezza_blocchi"):
        tab[c] = tab[c].fillna(False).astype(bool) if c in tab.columns else False
    segno = np.array([scheda.attese.get(f, 0) for f in tab["fascia"]])
    t_verso = np.where(segno != 0, segno * tab["t"].to_numpy(dtype=float), np.abs(tab["t"].to_numpy(dtype=float)))
    mis = tab["misurata"].to_numpy(dtype=bool)
    p = np.array([_p(x) for x in t_verso])
    bh = np.zeros(len(tab), dtype=bool)
    bh[mis] = benjamini_hochberg(p[mis], q)
    # il segno opposto: le fasce attese, con il verso girato
    p_opp = np.where(segno != 0, [_p(-x) for x in t_verso], p)
    bh_opp = np.zeros(len(tab), dtype=bool)
    bh_opp[mis] = benjamini_hochberg(p_opp[mis], q)
    tab["p"], tab["bh"] = p, bh

    esiti = []
    for i in range(len(tab)):
        if not mis[i]:
            esiti.append(POCHI)
        elif segno[i] == 0:
            esiti.append(FUORI)
        elif t_verso[i] > 0 and bh[i] and tab["due_meta"].iat[i]:
            esiti.append(RISPONDE)
        elif t_verso[i] < 0 and bh_opp[i] and tab["due_meta_opposto"].iat[i]:
            esiti.append(OPPOSTO)
        else:
            esiti.append(NON_RISPONDE)
    tab["esito"] = esiti
    attese = segno != 0
    if (tab["esito"] == RISPONDE).any():
        verdetto = RISPONDE
    elif (tab["esito"] == OPPOSTO).any():
        verdetto = OPPOSTO
    elif not mis[attese].any():
        verdetto = POCHI
    else:
        verdetto = NON_RISPONDE
    misurate = int(mis.sum())
    tab = tab.drop(columns="due_meta_opposto")
    tab.attrs.update(scheda=scheda.id, versione=scheda.versione, verdetto=verdetto, H=H,
                     orizzonte_ore=scheda.orizzonte_ore, riferimento=scheda.riferimento,
                     misurate=misurate, conto=conto(scheda, misurate), q=q,
                     **({"fuori_intervallo": valori.attrs.get("fuori_intervallo")}
                        if "fuori_intervallo" in getattr(valori, "attrs", {}) else {}))
    return tab


def conto(scheda: Scheda, misurate: int) -> int:
    """
    Le prove della scheda nel conto del dataset (docs/74): le fasce misurate,
    il doppio se il segno e' stato scelto dopo aver visto i dati (M07), piu' le
    prove gia' viste (M01: le 96 fasce del profilo 2a).
    """
    return int(misurate) * (2 if scheda.conta_segno_opposto else 1) + int(scheda.prove_extra)


# ========================================================================
# I doppioni (regola di Mattia del 27/10/2026, docs/74 §5 punto 4; dal 28/10 nessuna scheda la usa: M04
# riscritta, la regola M04/M05 e' caduta. Il meccanismo resta per le schede future)
# ========================================================================

def _quota_contenuta(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """La quota di `a` dentro `b` e quante volte e' sopra il caso (la copertura di b)."""
    na, cop = int(a.sum()), float(b.mean()) if b.size else 0.0
    if na == 0 or cop == 0:
        return 0.0, 0.0
    quota = float((a & b).sum()) / na
    return quota, quota / cop


def doppione(scheda_a: Scheda, codici_a: np.ndarray, scheda_b: Scheda, codici_b: np.ndarray) -> dict:
    """
    Il controllo DOPPIONI fra due schede, con le regole di docs/50 §7 punto 5
    (engine/famiglie.py): due fasce sono doppioni se una sta dentro l'altra per
    almeno il 70% e almeno 1,3 volte il caso. Le due schede sono doppioni se
    lo sono TUTTE le fasce attese della prima, ciascuna con la fascia della
    seconda con lo stesso nome e lo stesso verso. Si guardano solo le barre in
    cui tutte e due le variabili hanno una fascia. Usa solo le fasce, non i
    rendimenti: non e' una prova.

    Ritorna {"doppione": bool, "fasce": {nome: (quota, volte il caso)}}.
    """
    comuni = np.isfinite(codici_a) & np.isfinite(codici_b)
    dettagli, tutte = {}, True
    for nome, verso in scheda_a.attese.items():
        if scheda_b.attese.get(nome) != verso or nome not in scheda_b.fasce:
            tutte = False
            continue
        a = comuni & (codici_a == scheda_a.fasce.index(nome))
        b = comuni & (codici_b == scheda_b.fasce.index(nome))
        migliore = max(_quota_contenuta(a, b), _quota_contenuta(b, a))
        dettagli[nome] = migliore
        tutte &= migliore[0] >= SOGLIA_DOPPIONE and migliore[1] >= LIFT_MIN
    return {"doppione": bool(tutte and dettagli), "fasce": dettagli}


def escluse_per_doppione(codici: dict) -> dict:
    """
    Le schede da NON misurare per la regola dei doppioni (`doppione_di` della
    scheda, decisa prima di misurare): {id: frase}. `codici` = {id: codici_fasce}
    delle schede che si stanno per misurare sullo stesso dataset.

    Prima del confronto, il controllo delle fasce (controlla_fasce): una scheda
    con le fasce degeneri esce con il suo motivo, e non si confronta con nessuna.
    """
    fuori = {sid: m for sid, cod in codici.items() if (m := controlla_fasce(SCHEDE[sid], cod))}
    for sid, cod in codici.items():
        altra = SCHEDE[sid].doppione_di
        if sid not in fuori and altra and altra in codici and altra not in fuori:
            esito = doppione(SCHEDE[sid], cod, SCHEDE[altra], codici[altra])
            if esito["doppione"]:
                dett = ", ".join(f"{f} {q:.0%} ({lift:.1f} volte il caso)" for f, (q, lift) in esito["fasce"].items())
                fuori[sid] = (f"{sid} è un doppione di {altra} ({dett}): per la regola decisa prima di misurare "
                              f"si misura solo {altra}.")
    return fuori


# ========================================================================
# Lo studio: il conto nel giornale, gli esiti nel file della mappa
# ========================================================================

def chiave_conto(scheda: Scheda) -> list:
    return [scheda.id, int(scheda.versione), float(scheda.orizzonte_ore)]


def voci_da_scrivere(voci: list, scheda: Scheda, n: int, oos_visto: bool = False) -> list[dict]:
    """
    Le voci del giornale per una scheda misurata (docs/73 §B.4): la «prova» con
    dove = "mappa" se la chiave (id, versione, orizzonte) e' nuova o il numero
    e' PIU' ALTO di quello gia' scritto (il conto non scende mai: una rimisura con
    meno fasce misurate lascia il numero di prima, correzione di Mattia del
    27/10/2026); una «risalita» se la stessa scheda era gia' stata misurata con
    un'altra versione o un altro orizzonte (cambiata dopo la misura).
    """
    chiave = chiave_conto(scheda)
    scritte = {}
    for v in voci:
        if v.get("voce") == "prova" and v.get("dove") == "mappa" and v.get("chiave"):
            k = tuple(v["chiave"])
            scritte[k] = max(int(v["n"]), scritte.get(k, 0))
    out = []
    if tuple(chiave) not in scritte or int(n) > scritte[tuple(chiave)]:
        out.append({"voce": "prova", "dove": "mappa", "chiave": chiave, "n": int(n)})
    altre = [list(k) for k in scritte if k[0] == scheda.id and list(k) != chiave]
    if altre and tuple(chiave) not in scritte:
        out.append({"voce": "risalita", "risalita": {"cosa": f"scheda {scheda.id}", "da": altre[-1], "a": chiave,
                                                       "oos_visto": bool(oos_visto)}})
    return out


def esito_da_salvare(scheda: Scheda, tab: pd.DataFrame, timeframe: str, nota: str | None = None) -> dict:
    """L'esito di una scheda come riga del file della mappa (lo legge la 2b del Lab)."""
    colonne = ["fascia", "attesa", "barre", "giornate", "misurata", "scarto_bp", "scarto_pips", "t", "p", "bh",
               "due_meta", "incertezza_blocchi", "netto_bp", "esito"]
    righe = [{c: (None if isinstance(v, float) and not np.isfinite(v) else v) for c, v in r.items()}
             for r in tab.reindex(columns=colonne).to_dict("records")] if len(tab) else []
    return {"scheda": scheda.id, "versione": int(scheda.versione), "titolo": scheda.titolo,
            "orizzonte_ore": float(scheda.orizzonte_ore), "timeframe": timeframe,
            "riferimento": scheda.riferimento, "portabilita": scheda.portabilita,
            "attese": {k: int(v) for k, v in scheda.attese.items()},
            "verdetto": tab.attrs.get("verdetto", DOPPIONE if nota else None),
            "conto": int(tab.attrs.get("conto", 0)), "nota": nota, "fasce": righe}


def registra(cartella_dati, dataset: str, macchina: str, studio: dict, scheda: Scheda, tab: pd.DataFrame,
             timeframe: str, nota: str | None = None, oos_visto: bool = False, quando=None) -> list[dict]:
    """
    Scrive nello studio la misura di una scheda: le voci del conto nel giornale
    della macchina (solo se cambiano) e l'esito nel file della mappa (sempre).
    Ritorna le voci del giornale scritte.
    """
    from . import studio as st
    voci, _ = st.leggi_voci(cartella_dati, dataset, studio["id"])
    nuove = voci_da_scrivere(voci, scheda, int(tab.attrs.get("conto", 0)), oos_visto)
    for v in nuove:
        st.aggiungi_voce(cartella_dati, dataset, macchina, studio["id"], v, quando=quando)
    st.aggiungi_esito_mappa(cartella_dati, dataset, macchina, studio["id"],
                            esito_da_salvare(scheda, tab, timeframe, nota), quando=quando)
    return nuove
