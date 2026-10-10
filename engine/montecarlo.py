"""
Monte Carlo, yardstick e sizing — Passo 7 della roadmap (26/9/2026).

Punto di partenza: il notebook di Mattia `EV_MC_Analysis_Strategy_IP_final.ipynb`
(Lezione 9 del corso). Stesse domande, dentro il tool:

    yardstick          dopo 10 / 20 / 40 / 100 trade, che drawdown e che P&L
                       aspettarsi, percentile per percentile. Dal vivo: «dopo 20
                       trade ho X pips di drawdown: in che percentile sono?»
    montecarlo_completo
                       lo stesso sull'intera lunghezza del campione
    sizing             quanti lotti, dal drawdown al 95° percentile e dal peggior
                       trade (i due metodi della Lezione 9)

DECISIONI (Mattia, 26/9)
------------------------
- l'unita' e' il PIP NETTO per trade (lo stesso di avg_trade_netto): non dipende
  da leva e capitale. I dollari entrano solo nel sizing.
- ricampionamento CON reimmissione dei trade singoli, come nel notebook del corso.
  Niente bootstrap a blocchi: i trade sono trattati come indipendenti. Se le
  perdite arrivano a grappoli gli yardstick sono un po' ottimisti.
- su quali trade: parametro "IS" / "OOS" / "FULL" (pips_per_dataset).
- sizing al 95° percentile del drawdown.

IL DRAWDOWN PARTE DA ZERO
-------------------------
Ogni sequenza simulata comincia da equity zero: una perdita sui primi trade e'
drawdown. Il notebook del corso (e giudizio.py fino al 26/9) partiva dal primo
trade e la perdeva: con trade -5, -3 misurava 3 invece di 8. Sugli yardstick a
10-20 trade la differenza e' grande.

Modulo ADDITIVO. Usa engine/metriche.py (pips netti) in sola lettura.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .metriche import pips_per_trade

PERCENTILI = (50, 75, 90, 95, 99)
ORIZZONTI = (10, 20, 40, 100)
_BLOCCO = 2_000          # simulazioni per blocco: tiene bassa la memoria


# ========================================================================
# 1 · I trade da simulare
# ========================================================================

def pips_per_dataset(trades_is: pd.DataFrame | None, trades_oos: pd.DataFrame | None,
                     pip_size: float, commission: float = 0.0,
                     dataset: str = "FULL") -> np.ndarray:
    """
    Pips netti per trade, in ordine di uscita, del dataset scelto.

    trades_is, trades_oos   `.trades(...)` dei due backtest (IS e OOS) dello
                            STESSO sistema finale
    dataset                 "IS", "OOS" o "FULL" (IS seguito da OOS)
    """
    d = str(dataset).upper()
    if d not in ("IS", "OOS", "FULL"):
        raise ValueError("dataset deve essere 'IS', 'OOS' o 'FULL'.")
    parti = {"IS": [("IS", trades_is)], "OOS": [("OOS", trades_oos)],
             "FULL": [("IS", trades_is), ("OOS", trades_oos)]}[d]
    pezzi = []
    for nome, t in parti:
        if t is None:
            raise ValueError(f"dataset='{d}' richiede i trade {nome}.")
        if len(t) == 0:
            continue
        _, netti = pips_per_trade(t, pip_size, commission)
        ordine = np.argsort(pd.DatetimeIndex(t["ExitTime"]).to_numpy(), kind="mergesort")
        pezzi.append(netti.to_numpy(dtype=float)[ordine])
    x = np.concatenate(pezzi) if pezzi else np.array([], dtype=float)
    return x[np.isfinite(x)]


# ========================================================================
# 2 · Il nucleo: drawdown e P&L di sequenze simulate
# ========================================================================

def drawdown_da_zero(pips) -> float:
    """Drawdown massimo di UNA sequenza di trade, con la curva che parte da zero."""
    x = np.asarray(pips, dtype=float)
    if x.size == 0:
        return 0.0
    eq = np.r_[0.0, np.cumsum(x)]
    return float((np.maximum.accumulate(eq) - eq).max())


def _simula(x: np.ndarray, lunghezza: int, n_sim: int, rng) -> tuple[np.ndarray, np.ndarray]:
    """n_sim sequenze di `lunghezza` trade, pescati con reimmissione.
    Ritorna (drawdown massimi, P&L finali), in pips."""
    dd = np.empty(n_sim)
    pnl = np.empty(n_sim)
    fatte = 0
    while fatte < n_sim:
        m = min(_BLOCCO, n_sim - fatte)
        cammini = rng.choice(x, size=(m, lunghezza), replace=True)
        eq = np.concatenate([np.zeros((m, 1)), np.cumsum(cammini, axis=1)], axis=1)
        dd[fatte:fatte + m] = (np.maximum.accumulate(eq, axis=1) - eq).max(axis=1)
        pnl[fatte:fatte + m] = eq[:, -1]
        fatte += m
    return dd, pnl


def _controlla(pips) -> np.ndarray:
    x = np.asarray(pips, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 5:
        raise ValueError(f"servono almeno 5 trade per il Monte Carlo (ne ho {x.size}).")
    if x.size < 30:
        print(f"[montecarlo] attenzione: solo {x.size} trade, i percentili sono instabili.")
    return x


# ========================================================================
# 3 · Yardstick e Monte Carlo completo
# ========================================================================

def yardstick(pips, orizzonti=ORIZZONTI, percentili=PERCENTILI,
              n_sim: int = 20_000, seed: int = 0) -> pd.DataFrame:
    """
    La tabella degli yardstick: per ogni orizzonte (numero di trade) i
    percentili del drawdown massimo e del P&L, e la probabilita' di essere in
    perdita. Tutto in pips netti.

    Come si legge dal vivo: dopo N trade il drawdown reale e' Y pips. Se Y
    supera la colonna dd_p95 di quella riga, solo il 5% delle sequenze simulate
    ha fatto peggio: e' un segnale da guardare (la Lezione 9 parla di ridurre la
    size, mettere in pausa o fermare il sistema oltre il 95°-99°).

    Colonne: orizzonte, dd_p50 ... dd_p99, pnl_p50 ... pnl_p99, p_pnl_negativo (%).
    """
    x = _controlla(pips)
    rng = np.random.default_rng(seed)
    righe = []
    for h in orizzonti:
        dd, pnl = _simula(x, int(h), int(n_sim), rng)
        riga = {"orizzonte": int(h)}
        for p, v in zip(percentili, np.percentile(dd, percentili)):
            riga[f"dd_p{p}"] = float(v)
        for p, v in zip(percentili, np.percentile(pnl, percentili)):
            riga[f"pnl_p{p}"] = float(v)
        riga["p_pnl_negativo"] = float((pnl < 0).mean() * 100.0)
        righe.append(riga)
    return pd.DataFrame(righe).set_index("orizzonte")


def montecarlo_completo(pips, n_sim: int = 20_000, percentili=PERCENTILI,
                        soglia_dd: float | None = None, seed: int = 0) -> dict:
    """
    Monte Carlo sull'intera lunghezza del campione (tanti trade quanti ce ne
    sono). Ritorna un dict con:

        n_trade, dd_reale (drawdown della sequenza vera), dd_p50 ... dd_p99,
        pnl_p50 ... pnl_p99, p_pnl_negativo (%), e se c'e' soglia_dd anche
        p_dd_oltre_soglia (%): quante sequenze superano quel drawdown
        _dd, _pnl: le distribuzioni complete (per i grafici)
    """
    x = _controlla(pips)
    rng = np.random.default_rng(seed)
    dd, pnl = _simula(x, x.size, int(n_sim), rng)
    out = {"n_trade": int(x.size), "dd_reale": drawdown_da_zero(x)}
    for p, v in zip(percentili, np.percentile(dd, percentili)):
        out[f"dd_p{p}"] = float(v)
    for p, v in zip(percentili, np.percentile(pnl, percentili)):
        out[f"pnl_p{p}"] = float(v)
    out["p_pnl_negativo"] = float((pnl < 0).mean() * 100.0)
    if soglia_dd is not None:
        out["p_dd_oltre_soglia"] = float((dd >= float(soglia_dd)).mean() * 100.0)
    out["_dd"], out["_pnl"] = dd, pnl
    return out


# ========================================================================
# 4 · Sizing
# ========================================================================

CONTRATTO_FOREX = 100_000.0


def valore_pip_lotto(symbol: str, pip_size: float, prezzo: float | None = None,
                     contratto: float | None = None, cambio: float | None = None) -> float:
    """
    Valore in dollari di 1 pip per 1 lotto.

        forex quotato in USD (EURUSD, GBPUSD ...)   contratto 100.000 x pip -> 10 $
        crypto (BTCUSD, ETHUSD ...)                  1 lotto = 1 unita' -> pip_size $
        forex con USD base (USDJPY, USDCHF ...)      serve il prezzo: 100.000 x pip / prezzo

    Per altri strumenti passa `contratto` (unita' per lotto) a mano: il valore e'
    contratto x pip_size (in valuta quotata, che deve essere USD).

    Metalli e indici (10/10/2026): contratto dalla tabella di engine/simboli.py.

        XAUUSD (100 once)                            100 x 0,10 -> 10 $
        US500, USTEC (contratto 1, quotati in USD)   1 x 1 punto -> 1 $
        DE40 (contratto 1, quotato in EUR)           1 x 1 punto -> 1 EUR: serve
                                                     cambio= (dollari per 1 EUR,
                                                     cioe' il prezzo di EURUSD)

    Una valuta di quotazione diversa da USD senza `cambio` e' un errore: il
    valore non viene indovinato.
    """
    from .costi import classifica_simbolo
    s = (symbol or "").upper()
    if contratto is not None:
        return float(contratto) * float(pip_size)
    classe = classifica_simbolo(s)
    if classe == "crypto":
        return 1.0 * float(pip_size)
    if classe == "forex":
        if s.endswith("USD"):
            return CONTRATTO_FOREX * float(pip_size)
        if s.startswith("USD"):
            if prezzo is None:
                raise ValueError(f"{s}: serve prezzo= per convertire il pip in dollari.")
            return CONTRATTO_FOREX * float(pip_size) / float(prezzo)
    from .simboli import in_tabella, info_symbol
    if classe in ("metalli", "indici") and in_tabella(s):
        t = info_symbol(s)
        valore = t["contratto"] * float(pip_size)          # in valuta di quotazione
        if t["valuta"] == "USD":
            return valore
        if cambio is None:
            raise ValueError(
                f"{s} e' quotato in {t['valuta']}: passa cambio= (dollari per 1 "
                f"{t['valuta']}, es. il prezzo di {t['valuta']}USD)."
            )
        return valore * float(cambio)
    raise ValueError(
        f"{s}: non so il contratto per lotto. Passa contratto= (unita' per lotto)."
    )


def sizing(yardstick_o_mc, dd_accettabile_usd: float, valore_pip: float,
           percentile: int = 95, perdita_max_trade_usd: float | None = None,
           peggior_trade_pips: float | None = None) -> dict:
    """
    Lotti per il live, con i due metodi della Lezione 9.

    yardstick_o_mc          il dict di montecarlo_completo (usa il suo dd al
                            `percentile`), oppure un numero: il drawdown in pips
    dd_accettabile_usd      il drawdown massimo che accetti sul conto, in $
    valore_pip              valore_pip_lotto(...): $ per pip per lotto
    percentile              95 (decisione del 26/9)
    perdita_max_trade_usd, peggior_trade_pips
                            metodo del peggior trade (facoltativo): perdita
                            massima accettata su UN trade, e il peggior trade del
                            backtest in pips (numero positivo o negativo)

    Ritorna: dd_pips (usato), lotti_drawdown, lotti_peggior_trade (o NaN),
    lotti_consigliati (il piu' prudente dei due, arrotondato per difetto a 0,01).
    """
    if isinstance(yardstick_o_mc, dict):
        chiave = f"dd_p{int(percentile)}"
        if chiave not in yardstick_o_mc:
            raise ValueError(f"il Monte Carlo non ha il percentile {percentile}.")
        dd_pips = float(yardstick_o_mc[chiave])
    else:
        dd_pips = float(yardstick_o_mc)
    if dd_pips <= 0 or valore_pip <= 0:
        raise ValueError("drawdown e valore del pip devono essere positivi.")

    lotti_dd = float(dd_accettabile_usd) / (dd_pips * float(valore_pip))
    lotti_pt = np.nan
    if perdita_max_trade_usd is not None and peggior_trade_pips is not None:
        peggiore = abs(float(peggior_trade_pips))
        if peggiore > 0:
            lotti_pt = float(perdita_max_trade_usd) / (peggiore * float(valore_pip))
    candidati = [v for v in (lotti_dd, lotti_pt) if np.isfinite(v)]
    consigliati = np.floor(min(candidati) * 100) / 100
    return {"percentile": int(percentile), "dd_pips": dd_pips,
            "dd_usd_per_lotto": dd_pips * float(valore_pip),
            "lotti_drawdown": lotti_dd, "lotti_peggior_trade": lotti_pt,
            "lotti_consigliati": float(consigliati)}


# ========================================================================
# 5 · Grafici
# ========================================================================

def grafici_montecarlo(pips, mc: dict | None = None, orizzonti=ORIZZONTI,
                       n_sim_grafici: int = 5_000, n_spaghetti: int = 100,
                       titolo: str = "", seed: int = 0):
    """
    I grafici del notebook del corso, in pips netti:

        1. distribuzione del drawdown massimo sull'intero campione
        2. drawdown e P&L per orizzonte (due righe di istogrammi)
        3. n_spaghetti curve di equity simulate
        4. mediana con la banda 5°-95°
    """
    import matplotlib.pyplot as plt

    x = _controlla(pips)
    rng = np.random.default_rng(seed + 1)
    suff = f" · {titolo}" if titolo else ""

    if mc is None:
        mc = montecarlo_completo(x, n_sim=n_sim_grafici, seed=seed)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.hist(mc["_dd"], bins=60)
    ax.axvline(mc["dd_p95"], color="red", linestyle="--", label="95° percentile")
    ax.axvline(mc["dd_reale"], color="black", linewidth=1.5, label="drawdown reale")
    ax.set_xlabel("drawdown massimo (pips)")
    ax.set_title(f"Drawdown massimo su {mc['n_trade']} trade{suff}")
    ax.legend()
    fig.tight_layout()

    fig2, assi = plt.subplots(2, len(orizzonti), figsize=(4.5 * len(orizzonti), 7))
    assi = np.atleast_2d(assi)
    for j, h in enumerate(orizzonti):
        dd, pnl = _simula(x, int(h), n_sim_grafici, rng)
        assi[0, j].hist(dd, bins=50)
        assi[0, j].set_title(f"drawdown dopo {h} trade")
        assi[1, j].hist(pnl, bins=50)
        assi[1, j].axvline(0, color="red", linestyle="--")
        assi[1, j].set_title(f"P&L dopo {h} trade")
        assi[1, j].set_xlabel("pips")
    fig2.suptitle(f"Yardstick per orizzonte{suff}")
    fig2.tight_layout()

    cammini = np.concatenate(
        [np.zeros((n_sim_grafici, 1)),
         np.cumsum(rng.choice(x, size=(n_sim_grafici, x.size), replace=True), axis=1)],
        axis=1)
    fig3, (a1, a2) = plt.subplots(2, 1, figsize=(10, 9))
    a1.plot(cammini[:n_spaghetti].T, linewidth=0.6, alpha=0.6)
    a1.plot(np.r_[0.0, np.cumsum(x)], color="black", linewidth=1.8, label="sequenza reale")
    a1.set_title(f"{n_spaghetti} curve simulate{suff}")
    a1.set_xlabel("trade")
    a1.set_ylabel("pips netti")
    a1.legend()
    passi = np.arange(cammini.shape[1])
    a2.plot(passi, np.median(cammini, axis=0), label="mediana")
    a2.fill_between(passi, np.percentile(cammini, 5, axis=0),
                    np.percentile(cammini, 95, axis=0), alpha=0.25, label="5°-95°")
    a2.axhline(0, color="grey", linewidth=0.8)
    a2.set_title(f"Mediana e banda 5°-95°{suff}")
    a2.set_xlabel("trade")
    a2.legend()
    fig3.tight_layout()
    return fig, fig2, fig3
