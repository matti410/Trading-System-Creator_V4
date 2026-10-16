"""
Money management — quanto rischiare su ogni trade (16/10/2026, fase 1 di docs/61).

Fonte: Andrea Unger, «The Successful Trader's Guide to Money Management»,
Wiley 2021. Metodo di base: RISCHIO FISSO IN PERCENTUALE (fixed fractional,
cap. 4.1): a ogni trade si rischia la frazione f del capitale di quel momento,

    lotti = capitale x f / (rischio del trade in unita' x valore di 1 unita' per 1 lotto)

arrotondati PER DIFETTO al passo del broker (p. 39-43). La f si sceglie con
il Monte Carlo e una regola del trader sul drawdown (secure f, cap. 4.3 e 6).
Kelly (cap. 2-3) e optimal f (cap. 4.2) sono solo numeri di riferimento.

QUESTO MODULO NON SA NIENTE DI FOREX
------------------------------------
Usa solo numpy e pandas e non importa niente da engine/: si copia identico nel
repo crypto. Lavora su una TABELLA DI TRADE, una riga per trade in ordine di
uscita, con queste colonne (le costruisce l'adattatore del repo, nel V4
engine/mm_adattatore.py):

    pips_netti       risultato del trade con 1 lotto, in unita' del symbol
                     (pip nel forex, punto negli indici, dollaro in BTC), netto
    rischio_pips     rischio del trade nelle stesse unita' (distanza dallo stop
                     piu' i costi), noto PRIMA dell'ingresso. NaN = ignoto:
                     il trade si salta
    valore_entrata   valore di 1 unita' per 1 lotto, nella valuta del conto,
                     al momento della decisione (serve ai lotti)
    valore_uscita    lo stesso all'uscita (serve al guadagno in valuta)
    nozionale_lotto  facoltativa: valore di 1 lotto, nella valuta del conto,
                     al momento della decisione (serve al tetto della leva)

I LIMITI DEI LOTTI (dizionario `limiti`, ogni voce facoltativa)
---------------------------------------------------------------
    minimo   lotto minimo: sotto, il trade si SALTA (libro p. 235-236)
    passo    passo dei lotti: arrotondamento per difetto. None/0 = continuo
    massimo  lotto massimo per ordine: sopra, si taglia al massimo
    leva     leva massima: nozionale <= capitale x leva; se interviene i lotti
             scendono (e se finiscono sotto il minimo il trade si salta)

Con limiti vuoti (o tutti None) i lotti sono continui e nessun trade si salta:
e' il caso dei test di identita' (regola di Mattia del 16/10/2026).

NESSUN LOOKAHEAD: i lotti del trade k usano solo il capitale dopo il trade
k-1 e le colonne «al momento della decisione» del trade k.

Modulo ADDITIVO.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# esito di ogni trade
OK = "ok"
RIDOTTO_LEVA = "ridotto dalla leva"
RIDOTTO_MASSIMO = "tagliato al lotto massimo"
SALTATO_MINIMO = "saltato: sotto il lotto minimo"
SALTATO_LEVA = "saltato: la leva lo porta sotto il minimo"
SALTATO_RISCHIO = "saltato: rischio ignoto"

_CODICI = [OK, RIDOTTO_LEVA, RIDOTTO_MASSIMO, SALTATO_MINIMO, SALTATO_LEVA, SALTATO_RISCHIO]
_SALTATI = (3, 4, 5)
_LEVA = (1, 4)

# griglia delle percentuali di rischio provate da `calibra` (frazioni)
GRIGLIA = tuple(np.round(np.r_[np.arange(0.0025, 0.0501, 0.0025),
                               np.arange(0.055, 0.1001, 0.005)], 6))
COLONNE = ("pips_netti", "rischio_pips", "valore_entrata", "valore_uscita")


# ========================================================================
# 1 · I numeri di riferimento: Kelly e optimal f
# ========================================================================

def kelly(r) -> float:
    """
    Frazione di Kelly (cap. 2, p. 22): K = W - (1 - W) / R, con W la quota di
    trade vincenti e R = vincita media / perdita media. `r` sono i risultati
    dei trade (nel tool in multipli di rischio). NaN senza vincite o perdite.
    """
    x = np.asarray(r, dtype=float)
    x = x[np.isfinite(x)]
    vinc, perd = x[x > 0], x[x <= 0]
    if vinc.size == 0 or perd.size == 0 or perd.mean() == 0:
        return float("nan")
    w = vinc.size / x.size
    rr = vinc.mean() / abs(perd.mean())
    return float(w - (1.0 - w) / rr)


def twr(r, f: float) -> float:
    """Moltiplicatore finale del capitale con frazioni continue (p. 61-63):
    prodotto di (1 + f x r), con r in multipli del rischio. 0 se si azzera."""
    hpr = 1.0 + float(f) * np.asarray(r, dtype=float)
    if (hpr <= 0).any():
        return 0.0
    return float(np.exp(np.log(hpr).sum()))


def optimal_f(r, griglia=None) -> tuple[float, float]:
    """
    Optimal f di Ralph Vince (cap. 4.2): la f che massimizza il TWR, con r in
    multipli del rischio (nel libro: risultato / perdita peggiore). Ritorna
    (f, TWR). `griglia` predefinita: passi di 0,1% fino a dove il trade
    peggiore azzererebbe il conto. (nan, nan) senza perdite; (0, 1) se nessuna
    frazione fa crescere il capitale (TWR mai sopra 1: niente da rischiare).
    """
    x = np.asarray(r, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0 or x.min() >= 0:
        return float("nan"), float("nan")
    if griglia is None:
        tetto = 1.0 / abs(x.min())
        griglia = np.arange(0.001, tetto, 0.001)
    griglia = np.asarray(griglia, dtype=float)
    valori = np.array([twr(x, f) for f in griglia])
    i = int(np.argmax(valori))
    if valori[i] <= 1.0:
        return 0.0, 1.0
    return float(griglia[i]), float(valori[i])


# ========================================================================
# 2 · I lotti di un trade
# ========================================================================

def _limite(limiti, nome):
    v = (limiti or {}).get(nome)
    return None if v is None or (isinstance(v, (int, float)) and v <= 0) else float(v)


def _lotti(capitale, f, rischio_unita, valore, nozionale, limiti):
    """Versione vettoriale (array numpy) di `lotti_rischio_fisso`: (lotti, codice)."""
    capitale = np.asarray(capitale, dtype=float)
    rischio_usd = np.asarray(rischio_unita, dtype=float) * np.asarray(valore, dtype=float)
    minimo, passo = _limite(limiti, "minimo"), _limite(limiti, "passo")
    massimo, leva = _limite(limiti, "massimo"), _limite(limiti, "leva")

    def giu(x):
        if passo is None:
            return x
        return np.round(np.floor(x / passo + 1e-9) * passo, 10)

    ignoto = ~np.isfinite(rischio_usd) | (rischio_usd <= 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        grezzi = np.where(ignoto, 0.0, np.maximum(capitale, 0.0) * float(f) / rischio_usd)
    lotti = giu(grezzi)
    codice = np.zeros(lotti.shape, dtype=np.int8)
    if minimo is not None:
        codice = np.where(lotti < minimo - 1e-12, 3, codice)
    if massimo is not None:
        sopra = (codice == 0) & (lotti > massimo)
        lotti = np.where(sopra, giu(np.full(lotti.shape, massimo)), lotti)
        codice = np.where(sopra, 2, codice)
    if leva is not None and nozionale is not None:
        noz = np.asarray(nozionale, dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            tetto = giu(np.where(noz > 0, np.maximum(capitale, 0.0) * leva / noz, np.inf))
        sopra = (codice != 3) & (lotti > tetto + 1e-12)
        lotti = np.where(sopra, tetto, lotti)
        sotto = sopra & (minimo is not None) & (lotti < (minimo or 0.0) - 1e-12)
        codice = np.where(sopra, np.where(sotto, 4, 1), codice)
    codice = np.where(ignoto, 5, codice)
    lotti = np.where(np.isin(codice, _SALTATI), 0.0, lotti)
    return lotti, codice


def lotti_rischio_fisso(capitale: float, f: float, rischio_unita: float, valore_unita_lotto: float,
                        limiti: dict | None = None, nozionale_lotto: float | None = None
                        ) -> tuple[float, str]:
    """
    I lotti di UN trade col rischio fisso in percentuale (cap. 4.1).

        capitale            capitale prima del trade, nella valuta del conto
        f                   frazione rischiata (0,01 = 1%)
        rischio_unita       rischio del trade in unita' del symbol (es. pips allo stop)
        valore_unita_lotto  valore di 1 unita' per 1 lotto, nella valuta del conto
        limiti              {"minimo", "passo", "massimo", "leva"} (vedi testa del modulo)
        nozionale_lotto     valore di 1 lotto (serve solo se c'e' la leva)

    Ritorna (lotti, esito): esito e' una delle costanti OK, RIDOTTO_LEVA, ...
    Esempio del libro (p. 54): 100.000, 5%, stop 1.250 per contratto, passo 1
    -> 4 contratti.
    """
    lotti, codice = _lotti(np.array([capitale]), f, np.array([rischio_unita]),
                           np.array([valore_unita_lotto]),
                           None if nozionale_lotto is None else np.array([nozionale_lotto]), limiti)
    return float(lotti[0]), _CODICI[int(codice[0])]


# ========================================================================
# 3 · La storia vera: una percentuale applicata alla sequenza dei trade
# ========================================================================

def _controlla_tabella(tabella: pd.DataFrame) -> None:
    mancano = [c for c in COLONNE if c not in tabella.columns]
    if mancano:
        raise ValueError(f"tabella dei trade senza le colonne {mancano} (vedi la testa del modulo).")


def ripercorri(tabella: pd.DataFrame, capitale: float, f: float,
               limiti: dict | None = None) -> pd.DataFrame:
    """
    Applica la frazione f alla sequenza vera dei trade, nell'ordine dato.

    Ritorna una tabella con una riga per trade (stesso indice di `tabella`):
        capitale_prima, lotti, esito, guadagno (valuta del conto),
        capitale_dopo, massimo (capitale massimo fin li'), drawdown_pct,
        perdita_pct_conto (perdita del trade in % del capitale prima)
    Il capitale non scende sotto zero; a zero i trade successivi si saltano.
    """
    _controlla_tabella(tabella)
    pips = tabella["pips_netti"].to_numpy(dtype=float)
    rischio = tabella["rischio_pips"].to_numpy(dtype=float)
    v_in = tabella["valore_entrata"].to_numpy(dtype=float)
    v_out = tabella["valore_uscita"].to_numpy(dtype=float)
    noz = tabella["nozionale_lotto"].to_numpy(dtype=float) if "nozionale_lotto" in tabella else None
    n = len(tabella)
    out = {k: np.empty(n) for k in ("capitale_prima", "lotti", "guadagno", "capitale_dopo",
                                    "massimo", "drawdown_pct", "perdita_pct_conto")}
    esiti = []
    c, picco = float(capitale), float(capitale)
    for i in range(n):
        lt, cod = _lotti(np.array([c]), f, rischio[i:i + 1], v_in[i:i + 1],
                         None if noz is None else noz[i:i + 1], limiti)
        lt, cod = float(lt[0]), int(cod[0])
        g = lt * pips[i] * v_out[i]
        out["capitale_prima"][i] = c
        out["lotti"][i] = lt
        out["guadagno"][i] = g
        out["perdita_pct_conto"][i] = (max(-g, 0.0) / c * 100.0) if c > 0 else 0.0
        c = max(c + g, 0.0)
        picco = max(picco, c)
        out["capitale_dopo"][i] = c
        out["massimo"][i] = picco
        out["drawdown_pct"][i] = (picco - c) / picco * 100.0 if picco > 0 else 0.0
        esiti.append(_CODICI[cod])
    r = pd.DataFrame(out, index=tabella.index)
    r.insert(2, "esito", esiti)
    return r


def sintesi_percorso(percorso: pd.DataFrame, capitale: float) -> dict:
    """I numeri riassuntivi di `ripercorri`."""
    fatti = percorso["lotti"] > 0
    esiti = percorso["esito"]
    finale = float(percorso["capitale_dopo"].iloc[-1]) if len(percorso) else float(capitale)
    return {
        "trade": int(len(percorso)),
        "fatti": int(fatti.sum()),
        "saltati": int(esiti.isin([SALTATO_MINIMO, SALTATO_LEVA, SALTATO_RISCHIO]).sum()),
        "leva_interviene": int(esiti.isin([RIDOTTO_LEVA, SALTATO_LEVA]).sum()),
        "capitale_iniziale": float(capitale),
        "capitale_finale": finale,
        "rendimento_pct": (finale / float(capitale) - 1.0) * 100.0,
        "drawdown_max_pct": float(percorso["drawdown_pct"].max()) if len(percorso) else 0.0,
        "perdita_peggiore_pct": float(percorso["perdita_pct_conto"].max()) if len(percorso) else 0.0,
        "lotti_min": float(percorso.loc[fatti, "lotti"].min()) if fatti.any() else 0.0,
        "lotti_medi": float(percorso.loc[fatti, "lotti"].mean()) if fatti.any() else 0.0,
        "lotti_max": float(percorso.loc[fatti, "lotti"].max()) if fatti.any() else 0.0,
    }


# ========================================================================
# 4 · Monte Carlo con money management (cap. 6)
# ========================================================================

def montecarlo_mm(tabella: pd.DataFrame, capitale: float, frazioni, n_trade: int,
                  n_sim: int = 10_000, limiti: dict | None = None, seed: int = 0,
                  percorsi: bool = False, indici: np.ndarray | None = None) -> dict:
    """
    Migliaia di sequenze di `n_trade` trade ripescati CON reimmissione dalla
    tabella (come engine/montecarlo.py), con il capitale che si moltiplica e i
    lotti ricalcolati a ogni trade. Le stesse sequenze per tutte le frazioni
    (le curve per f restano confrontabili).

    Ritorna {f: dict} con array lunghi n_sim:
        finale, drawdown_pct (massimo della sequenza), saltati, leva,
        bloccato (alla fine il capitale non basta per il lotto minimo con il
        rischio mediano della tabella)
        e se percorsi=True anche "percorsi": capitale dopo ogni trade
        (n_sim x (n_trade + 1)).
    `indici` (facoltativo) fissa le sequenze a mano: serve ai test.
    """
    _controlla_tabella(tabella)
    pips = tabella["pips_netti"].to_numpy(dtype=float)
    rischio = tabella["rischio_pips"].to_numpy(dtype=float)
    v_in = tabella["valore_entrata"].to_numpy(dtype=float)
    v_out = tabella["valore_uscita"].to_numpy(dtype=float)
    noz = tabella["nozionale_lotto"].to_numpy(dtype=float) if "nozionale_lotto" in tabella else None
    if len(tabella) == 0:
        raise ValueError("tabella dei trade vuota.")
    if indici is None:
        rng = np.random.default_rng(seed)
        indici = rng.integers(0, len(tabella), size=(int(n_sim), int(n_trade)))
    indici = np.asarray(indici)
    m, lung = indici.shape
    ok = np.isfinite(rischio) & (rischio > 0)
    rischio_med = float(np.median(rischio[ok] * v_in[ok])) if ok.any() else np.nan
    minimo = _limite(limiti, "minimo")

    risultati = {}
    for f in np.atleast_1d(frazioni):
        f = float(f)
        c = np.full(m, float(capitale))
        picco = c.copy()
        dd = np.zeros(m)
        saltati = np.zeros(m, dtype=int)
        leva = np.zeros(m, dtype=int)
        storia = np.empty((m, lung + 1)) if percorsi else None
        if percorsi:
            storia[:, 0] = c
        for t in range(lung):
            j = indici[:, t]
            lt, cod = _lotti(c, f, rischio[j], v_in[j], None if noz is None else noz[j], limiti)
            c = np.maximum(c + lt * pips[j] * v_out[j], 0.0)
            picco = np.maximum(picco, c)
            with np.errstate(divide="ignore", invalid="ignore"):
                dd = np.maximum(dd, np.where(picco > 0, (picco - c) / picco, 0.0))
            saltati += np.isin(cod, _SALTATI)
            leva += np.isin(cod, _LEVA)
            if percorsi:
                storia[:, t + 1] = c
        if minimo is not None and np.isfinite(rischio_med):
            bloccato = c * f / rischio_med < minimo - 1e-12
        else:
            bloccato = c <= 0
        risultati[f] = {"finale": c, "drawdown_pct": dd * 100.0, "saltati": saltati,
                        "leva": leva, "bloccato": bloccato}
        if percorsi:
            risultati[f]["percorsi"] = storia
    return risultati


def calibra(tabella: pd.DataFrame, capitale: float, drawdown_max_pct: float, n_trade: int,
            frazioni=GRIGLIA, percentile: int = 95, n_sim: int = 10_000,
            limiti: dict | None = None, seed: int = 0) -> tuple[pd.DataFrame, float | None]:
    """
    La scelta della frazione (secure f, cap. 4.3 + Monte Carlo del cap. 6).

    Per ogni frazione della griglia: drawdown mediano e al `percentile`,
    rendimento mediano, probabilita' di chiudere in perdita e di restare
    bloccati, trade saltati e interventi della leva (in % dei trade).

    La frazione scelta e' la piu' alta della griglia il cui drawdown al
    `percentile` resta entro `drawdown_max_pct`, contando dal basso senza
    salti (si ferma alla prima frazione che supera il limite). None se
    nemmeno la prima resta entro il limite.

    Ritorna (tabella, frazione scelta).
    """
    mc = montecarlo_mm(tabella, capitale, frazioni, n_trade, n_sim=n_sim, limiti=limiti, seed=seed)
    righe = []
    for f, r in mc.items():
        rend = (r["finale"] / float(capitale) - 1.0) * 100.0
        righe.append({
            "f": f,
            "drawdown_p50": float(np.percentile(r["drawdown_pct"], 50)),
            f"drawdown_p{int(percentile)}": float(np.percentile(r["drawdown_pct"], percentile)),
            "rendimento_p50": float(np.median(rend)),
            "p_perdita": float((rend < 0).mean() * 100.0),
            "p_bloccato": float(r["bloccato"].mean() * 100.0),
            "saltati_pct": float(r["saltati"].mean() / max(n_trade, 1) * 100.0),
            "leva_pct": float(r["leva"].mean() / max(n_trade, 1) * 100.0),
        })
    t = pd.DataFrame(righe)
    scelta = None
    for _, riga in t.iterrows():
        if riga[f"drawdown_p{int(percentile)}"] <= float(drawdown_max_pct):
            scelta = float(riga["f"])
        else:
            break
    return t, scelta


def banda(tabella: pd.DataFrame, capitale: float, f: float, n_trade: int,
          n_sim: int = 10_000, limiti: dict | None = None, seed: int = 0,
          percentili=(5, 50, 95)) -> pd.DataFrame:
    """
    Il capitale atteso trade dopo trade con la frazione f: percentili delle
    sequenze simulate dopo 0, 1, ..., n_trade trade. Serve a vedere dove cade
    la storia vera (out-of-sample) rispetto al piano fatto sull'in-sample.
    """
    r = montecarlo_mm(tabella, capitale, [f], n_trade, n_sim=n_sim, limiti=limiti,
                      seed=seed, percorsi=True)[float(f)]["percorsi"]
    return pd.DataFrame({f"p{p}": np.percentile(r, p, axis=0) for p in percentili})
