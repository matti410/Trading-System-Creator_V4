"""
Motore di backtest veloce (docs/64, proposta e decisioni in docs/65).

COSA FA
-------
Lo stesso lavoro di `backtesting.py` 0.6.6 con `_StrategiaGenerica`
(engine/exit_search_bt.py), con gli STESSI trade al bit, circa 100 volte piu'
veloce. `backtesting.py` resta installato: e' l'oracolo dei test
(test_motore_veloce.py) e il motore "bt", che si sceglie con `motore="bt"`.

DUE LIVELLI
-----------
1. Il ciclo per unita' (`_ciclo`, compilato con numba): decide i trade, barra
   per barra, con le regole di docs/65 §2 (ingresso all'Open dopo il segnale,
   spread nel prezzo d'ingresso, stop e target attivi dalla barra dopo
   l'ingresso, stop che vince sul target nella stessa barra, gap riempiti
   all'Open, regola d'uscita, uscita a tempo, inversione, trade aperto alla
   fine escluso).
2. Il livello dei soldi (`_soldi`, compilato): il capitale che
   `backtesting.py` simula trade dopo trade (Size intera = tutto il capitale,
   commissione all'apertura e alla chiusura), la curva del capitale barra per
   barra e le cinque statistiche che il tool legge (`Return [%]`,
   `Sharpe Ratio`, `Max. Drawdown [%]`, `Win Rate [%]`, `Profit Factor`), con
   le stesse operazioni nello stesso ordine della libreria.

L'UNICA DIFFERENZA DICHIARATA (docs/65 §3.2 e §13, decisione 4)
------------------------------------------------------------------
`backtesting.py` annulla in silenzio gli ordini quando il capitale simulato
non compra piu' una unita' (e ferma tutto se va a zero): da li' i trade
spariscono, finche' il prezzo non scende abbastanza da tornare a comprarne
una, e poi la libreria prosegue su un'altra strada. Il motore veloce tiene TUTTI i trade per unita'; da quel trade in
poi la Size e' +-1, `Return [%]`, `Sharpe Ratio` e `Max. Drawdown [%]` sono
NaN, e stampa un avviso con la data (su stderr: si vede anche dentro il Lab).

COME SI USA
-----------
Come `Backtest`: `MotoreVeloce(df_bt, cash=, spread=, commission=, margin=,
exclusive_orders=True).run(long_col=..., ...)` restituisce un dizionario con
`_trades` (stesse colonne e tipi di stats["_trades"]) e le cinque statistiche.
I motori lo scelgono con il parametro `motore` (None = MOTORE_PREDEFINITO).

Modulo NUOVO, additivo: non modifica la libreria ne' la strategia.
"""
from __future__ import annotations

import os
import sys
from math import copysign

import numpy as np
import pandas as pd

try:
    from numba import njit
    DISPONIBILE = True
except Exception:      # numba non installato: il motore "veloce" ripiega su "bt"
    DISPONIBILE = False

    def njit(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda f: f

MOTORI = ("bt", "veloce")
# Il motore usato quando non se ne indica uno. "bt" fino al passo E3 di
# docs/65 §8; la variabile d'ambiente TSC_MOTORE lo cambia (serve a far girare
# tutte le suite con l'uno o con l'altro).
MOTORE_PREDEFINITO = os.environ.get("TSC_MOTORE", "bt")
if MOTORE_PREDEFINITO not in MOTORI:
    raise ValueError(f"TSC_MOTORE={MOTORE_PREDEFINITO!r}: usa uno di {MOTORI}.")

# la dimensione predefinita di buy()/sell() in backtesting.py: tutto il capitale
_FULL_EQUITY = 1 - sys.float_info.epsilon
_VOCI_STATS = ("Return [%]", "Sharpe Ratio", "Max. Drawdown [%]", "Win Rate [%]", "Profit Factor")
_avvisato_numba = False


def scegli_motore(motore=None) -> str:
    """
    Il motore da usare: "bt" (backtesting.py) o "veloce". None = il
    predefinito. "veloce" senza numba installato ripiega su "bt" con un
    avviso, una volta sola: il notebook non si ferma.
    """
    global _avvisato_numba
    m = MOTORE_PREDEFINITO if motore is None else motore
    if m not in MOTORI:
        raise ValueError(f"motore {m!r}: usa uno di {MOTORI}.")
    if m == "veloce" and not DISPONIBILE:
        if not _avvisato_numba:
            print("motore veloce non disponibile (numba non installato): si usa backtesting.py.",
                  file=sys.stderr)
            _avvisato_numba = True
        return "bt"
    return m


# ========================================================================
# 1 · Il ciclo per unita' (docs/65 §2)
# ========================================================================

@njit(cache=True)
def _ciclo(o, h, l, seg_l, seg_s, usc_l, usc_s, sl_l, tp_l, sl_s, tp_s,
           n_long, n_short, spread, inverti):
    """
    I trade chiusi (lato, barre, prezzi, stop, target), il trade ancora aperto
    alla fine (lato 0 = nessuno) e la barra di un eventuale errore (-1 = nessuno).
    I commenti R/E/S/U rimandano alle righe dell'inventario di docs/65 §2.
    """
    N = o.shape[0]
    lato = np.zeros(N, np.int64)
    eb = np.zeros(N, np.int64)
    xb = np.zeros(N, np.int64)
    ep = np.zeros(N)
    xp = np.zeros(N)
    slv = np.full(N, np.nan)
    tpv = np.full(N, np.nan)
    k = 0
    pos = 0                  # 0 nessuna posizione, 1 long, -1 short
    t_eb = 0
    t_ep = 0.0
    t_sl = np.nan
    t_tp = np.nan
    chiudi = False           # ordine di chiusura in coda: si riempie all'Open dopo
    entra = 0                # ordine d'ingresso in coda: 1 long, -1 short
    errore = -1
    for i in range(1, N):    # R1: next() non gira mai sulla barra 0
        # --- broker, barra i (R2): prima gli ordini in coda --------------
        if pos != 0:
            uscita = np.nan
            if chiudi:                       # U4: la chiusura in coda prima di stop e target
                uscita = o[i]
            else:
                if not np.isnan(t_sl):       # S4, S6: lo stop e' in testa alla coda
                    if pos == 1 and l[i] <= t_sl:
                        uscita = min(o[i], t_sl)
                    elif pos == -1 and h[i] >= t_sl:
                        uscita = max(o[i], t_sl)
                if np.isnan(uscita) and not np.isnan(t_tp):     # S5
                    if pos == 1 and h[i] >= t_tp:
                        uscita = max(o[i], t_tp)
                    elif pos == -1 and l[i] <= t_tp:
                        uscita = min(o[i], t_tp)
            if not np.isnan(uscita):
                lato[k] = pos
                eb[k] = t_eb
                xb[k] = i
                ep[k] = t_ep
                xp[k] = uscita               # U6: uscita senza spread
                slv[k] = t_sl
                tpv[k] = t_tp
                k += 1
                pos = 0
        chiudi = False
        if entra != 0:                       # E2, E3: Open della barra, spread dentro il prezzo
            pos = entra
            t_eb = i
            t_ep = o[i] * (1 + copysign(spread, entra))
            t_sl = np.nan
            t_tp = np.nan
            entra = 0
        # --- strategia, barra i (_StrategiaGenerica.next) ------------------
        if pos != 0:
            if t_eb == i:                    # S1, S2, S3: fissati sulla barra d'ingresso
                if pos == 1:
                    if not np.isnan(sl_l[i]):
                        t_sl = t_ep * (1 - sl_l[i])
                    if not np.isnan(tp_l[i]):
                        t_tp = t_ep * (1 + tp_l[i])
                else:
                    if not np.isnan(sl_s[i]):
                        t_sl = t_ep * (1 + sl_s[i])
                    if not np.isnan(tp_s[i]):
                        t_tp = t_ep * (1 - tp_s[i])
                # la libreria si ferma (assert 0 < price < inf): qui si segnala
                if not np.isnan(t_sl) and not (0.0 < t_sl < np.inf):
                    errore = i
                    break
                if not np.isnan(t_tp) and not (0.0 < t_tp < np.inf):
                    errore = i
                    break
            if inverti:                      # U3: l'inversione prevale su regola e tempo
                if pos == 1 and seg_s[i] and not seg_l[i]:
                    chiudi = True
                    entra = -1
                    continue
                if pos == -1 and seg_l[i] and not seg_s[i]:
                    chiudi = True
                    entra = 1
                    continue
            if (usc_l[i] if pos == 1 else usc_s[i]):     # U1
                chiudi = True
                continue
            scad = n_long if pos == 1 else n_short       # U2
            if i - t_eb >= scad - 1:
                chiudi = True
            continue
        if seg_l[i] and not seg_s[i]:        # E1
            entra = 1
        elif seg_s[i] and not seg_l[i]:
            entra = -1
    aperto = np.array([float(pos), float(t_eb), t_ep])   # U7: escluso dai trade
    return (lato[:k], eb[:k], xb[:k], ep[:k], xp[:k], slv[:k], tpv[:k], aperto, errore)


# ========================================================================
# 2 · Il livello dei soldi (docs/65 §3.1)
# ========================================================================

@njit(cache=True)
def _soldi(o, c, lato, eb, xb, ep, xp, aperto, cash, commission, leva, full):
    """
    Size, PnL, Commission, ReturnPct e curva del capitale, con le operazioni di
    backtesting.py nello stesso ordine (_Broker._process_orders, _open_trade,
    _close_trade, Trade.pl e pl_pct, equity). `esaurito` = indice del primo
    trade da cui il capitale simulato non basta piu' (-1 = mai), `barra` = la
    barra in cui la libreria se ne accorge.
    """
    N = o.shape[0]
    n = lato.shape[0]
    equity = np.full(N, np.nan)
    size = np.zeros(n, np.int64)
    pnl = np.zeros(n)
    com = np.zeros(n)
    rp = np.zeros(n)
    contanti = cash
    fine = 1                       # prima barra dell'equity non ancora scritta
    esaurito = -1
    barra = -1
    tot = n + (1 if aperto[0] != 0 else 0)
    for j in range(tot):
        if j < n:
            s = lato[j]
            e = eb[j]
            x = xb[j]
            pe = ep[j]
            px = xp[j]
        else:                      # il trade ancora aperto: solo nella curva del capitale
            s = int(aperto[0])
            e = int(aperto[1])
            x = -1
            pe = aperto[2]
            px = np.nan
        if esaurito < 0:
            for i in range(fine, e):
                equity[i] = contanti
            # _process_orders: Size = tutto il capitale disponibile, intera
            per_unita = pe + (0 + abs(full) * o[e] * commission) / abs(full)
            disponibile = max(0.0, contanti)       # margin_available: nessun trade aperto
            q = int((disponibile * leva * abs(full)) // per_unita)
            if q == 0 or q * per_unita > disponibile * leva:
                esaurito = j       # la libreria annullerebbe l'ordine
                barra = e
        if esaurito >= 0:          # da qui: per unita', curva del capitale non calcolabile
            if j < n:
                sz = 1 if s > 0 else -1
                pl_lordo = sz * (px - pe)
                cm = (0 + abs(sz) * px * commission) + (0 + abs(sz) * pe * commission)
                size[j] = sz
                pnl[j] = pl_lordo - cm
                com[j] = cm
                rp[j] = (1.0 if sz > 0 else -1.0) * (px / pe - 1) - cm / (abs(sz) * pe)
            continue
        sz = q if s > 0 else -q
        contanti -= 0 + abs(sz) * pe * commission              # _open_trade
        fino = N if x < 0 else x
        for i in range(e, fino):
            equity[i] = contanti + (c[i] * sz - sz * pe)
            if equity[i] <= 0:     # _Broker.next: la libreria chiude tutto e si ferma
                esaurito = j
                barra = i
                break
        if esaurito >= 0:
            # il trade j resta per unita' (la libreria lo chiuderebbe a Close[i])
            sz = 1 if s > 0 else -1
            if j < n:
                pl_lordo = sz * (px - pe)
                cm = (0 + abs(sz) * px * commission) + (0 + abs(sz) * pe * commission)
                size[j] = sz
                pnl[j] = pl_lordo - cm
                com[j] = cm
                rp[j] = (1.0 if sz > 0 else -1.0) * (px / pe - 1) - cm / (abs(sz) * pe)
            continue
        if x < 0:
            fine = N
            break
        pl_lordo = sz * (px - pe)                               # Trade.pl prima delle commissioni
        com_usc = 0 + abs(sz) * px * commission
        contanti += pl_lordo - 0 - com_usc                      # _close_trade
        cm = com_usc + (0 + abs(sz) * pe * commission)
        size[j] = sz
        pnl[j] = pl_lordo - cm
        com[j] = cm
        rp[j] = (1.0 if sz > 0 else -1.0) * (px / pe - 1) - cm / (abs(sz) * pe)
        fine = x
        if contanti <= 0:          # capitale a zero dopo la chiusura: la libreria si ferma
            esaurito = j + 1
            barra = x
    if esaurito < 0:
        for i in range(fine, N):
            equity[i] = contanti
        # pd.Series(equity).bfill().fillna(cash): la barra 0 prende la 1
        for i in range(N - 2, -1, -1):
            if np.isnan(equity[i]):
                equity[i] = equity[i + 1]
        for i in range(N):
            if np.isnan(equity[i]):
                equity[i] = contanti
    return size, pnl, com, rp, equity, esaurito, barra


# ========================================================================
# 3 · Le statistiche (backtesting/_stats.py 0.6.6, le cinque voci lette dal tool)
# ========================================================================

def _media_geometrica(rendimenti: pd.Series) -> float:
    r = rendimenti.fillna(0) + 1
    if np.any(r <= 0):
        return 0
    return np.exp(np.log(r).sum() / (len(r) or np.nan)) - 1


class _Calendario:
    """Quello che le statistiche leggono dall'indice: si calcola una volta per df."""

    def __init__(self, index):
        self.index = index
        self.datetime = isinstance(index, pd.DatetimeIndex)
        if not self.datetime:
            return
        periodo = pd.Series(index[-100:]).diff().dropna().median()   # _util._data_period
        giorni = periodo.days
        weekend = index.dayofweek.to_series().between(5, 6).mean() > 2 / 7 * .6
        self.annuali = (52 if giorni == 7 else 12 if giorni == 31 else 1 if giorni == 365
                        else (365 if weekend else 252))
        self.freq = {7: 'W', 31: 'ME', 365: 'YE'}.get(giorni, 'D')
        if self.freq == 'D':
            # l'ultima barra di ogni giorno: e' resample('D').last().dropna()
            g = index.normalize().asi8
            self.ultime = np.flatnonzero(np.r_[g[1:] != g[:-1], True])

    def rendimenti_giornalieri(self, equity: np.ndarray) -> pd.Series:
        if self.freq == 'D':
            fine = pd.Series(equity[self.ultime])
        else:
            fine = pd.Series(equity, index=self.index).resample(self.freq).last().dropna()
        return fine.pct_change().dropna()


def _statistiche(equity: np.ndarray, pnl: np.ndarray, rp: np.ndarray,
                 cal: _Calendario, esaurito: bool) -> dict:
    pl = pd.Series(pnl)
    rendimenti = pd.Series(rp)
    n = len(pl)
    win = np.nan if not n else (pl > 0).mean()
    pf = rendimenti[rendimenti > 0].sum() / (abs(rendimenti[rendimenti < 0].sum()) or np.nan)
    if esaurito:
        return {"Return [%]": np.nan, "Sharpe Ratio": np.nan, "Max. Drawdown [%]": np.nan,
                "Win Rate [%]": win * 100, "Profit Factor": pf}
    dd = 1 - equity / np.maximum.accumulate(equity)
    ritorno = (equity[-1] - equity[0]) / equity[0] * 100
    g = 0
    giornalieri = np.array(np.nan)
    annuali = np.nan
    if cal.datetime:
        annuali = cal.annuali
        giornalieri = cal.rendimenti_giornalieri(equity)
        g = _media_geometrica(giornalieri)
    annuo = (1 + g) ** annuali - 1
    vol = np.sqrt((giornalieri.var(ddof=int(bool(giornalieri.shape))) + (1 + g) ** 2) ** annuali
                  - (1 + g) ** (2 * annuali)) * 100
    sharpe = (annuo * 100 - 0.0 * 100) / (vol or np.nan)
    return {"Return [%]": ritorno, "Sharpe Ratio": sharpe,
            "Max. Drawdown [%]": -np.nan_to_num(dd.max()) * 100,
            "Win Rate [%]": win * 100, "Profit Factor": pf}


# ========================================================================
# 4 · Il motore, con l'interfaccia di Backtest
# ========================================================================

class MotoreVeloce:
    """
    Al posto di `Backtest(df_bt, _StrategiaGenerica, cash=, spread=,
    commission=, margin=, exclusive_orders=True)`: stessi argomenti, e
    `.run(**parametri della strategia)` restituisce un dizionario con
    `_trades` e le cinque statistiche lette dal tool.
    """

    def __init__(self, data: pd.DataFrame, *, cash=10_000, spread=.0, commission=.0,
                 margin=1., exclusive_orders=True):
        if not exclusive_orders:
            raise ValueError("MotoreVeloce replica solo exclusive_orders=True (una posizione alla volta).")
        if not isinstance(commission, (int, float)) or isinstance(commission, bool):
            raise TypeError("MotoreVeloce: commission dev'essere un numero (frazione per lato).")
        if not 0 < margin <= 1:
            raise ValueError(f"margin should be between 0 and 1, is {margin}")
        if cash <= 0:
            raise ValueError(f"cash should be > 0, is {cash}")
        prezzi = data[["Open", "High", "Low", "Close"]]
        if prezzi.isnull().values.any():
            raise ValueError('Some OHLC values are missing (NaN). '
                             'Please strip those lines with `df.dropna()` or '
                             'fill them in with `df.interpolate()` or whatever.')
        self._data = data
        self._o = np.ascontiguousarray(data["Open"].to_numpy(np.float64))
        self._h = np.ascontiguousarray(data["High"].to_numpy(np.float64))
        self._l = np.ascontiguousarray(data["Low"].to_numpy(np.float64))
        self._c = np.ascontiguousarray(data["Close"].to_numpy(np.float64))
        self._cash = float(cash)
        self._spread = float(spread)
        self._commission = float(commission)
        self._leva = 1 / margin
        self._cal = _Calendario(data.index)
        self._colonne = {}
        self._falso = np.zeros(len(data), np.bool_)

    def _bool(self, nome):
        if nome is None:
            return self._falso
        if nome not in self._colonne:
            self._colonne[nome] = np.ascontiguousarray(np.asarray(self._data[nome]).astype(np.bool_))
        return self._colonne[nome]

    def _float(self, nome):
        if nome not in self._colonne:
            self._colonne[nome] = np.ascontiguousarray(self._data[nome].to_numpy(np.float64))
        return self._colonne[nome]

    def run(self, long_col=None, short_col=None, exit_rule_long_col=None, exit_rule_short_col=None,
            n_barre=32, n_barre_long=None, n_barre_short=None, inverti_su_opposto=False) -> dict:
        nl = n_barre if n_barre_long is None else n_barre_long
        ns = n_barre if n_barre_short is None else n_barre_short
        (lato, eb, xb, ep, xp, slv, tpv, aperto, errore) = _ciclo(
            self._o, self._h, self._l, self._bool(long_col), self._bool(short_col),
            self._bool(exit_rule_long_col), self._bool(exit_rule_short_col),
            self._float("sl_long"), self._float("tp_long"), self._float("sl_short"),
            self._float("tp_short"), int(nl), int(ns), self._spread, bool(inverti_su_opposto))
        if errore >= 0:
            raise ValueError(f"MotoreVeloce: stop o target non positivo alla barra {errore} "
                             f"({self._data.index[errore]}): la frazione delle soglie adattive e' >= 1. "
                             "backtesting.py si fermerebbe con un errore.")
        size, pnl, com, rp, equity, esaurito, barra = _soldi(
            self._o, self._c, lato, eb, xb, ep, xp, aperto, self._cash, self._commission,
            self._leva, _FULL_EQUITY)
        if esaurito >= 0:
            quando = self._data.index[barra]
            print(f"!!! motore veloce: capitale simulato esaurito dal {quando} (trade {esaurito + 1} "
                  f"di {len(lato)}). backtesting.py da qui annullerebbe gli ordini: qui si tengono tutti "
                  "i trade per unita', Return, Sharpe e Max. Drawdown sono NaN (docs/65 §3.2).",
                  file=sys.stderr)
        stats = _statistiche(equity, pnl, rp, self._cal, esaurito >= 0)
        stats["_trades"] = self._tabella(size, eb, xb, ep, xp, slv, tpv, pnl, com, rp)
        stats["_capitale_esaurito"] = None if esaurito < 0 else self._data.index[barra]
        # da quale trade (indice da 0): i trade prima sono identici a quelli di backtesting.py
        stats["_trade_esaurito"] = None if esaurito < 0 else int(esaurito)
        return stats

    def _tabella(self, size, eb, xb, ep, xp, slv, tpv, pnl, com, rp) -> pd.DataFrame:
        """Costruita come _stats.compute_stats: liste Python, cosi' i tipi coincidono."""
        idx = self._data.index
        nan_a_none = lambda a: [None if np.isnan(v) else float(v) for v in a]
        t = pd.DataFrame({
            'Size': size.tolist(),
            'EntryBar': eb.tolist(),
            'ExitBar': xb.tolist(),
            'EntryPrice': ep.tolist(),
            'ExitPrice': xp.tolist(),
            'SL': nan_a_none(slv),
            'TP': nan_a_none(tpv),
            'PnL': pnl.tolist(),
            'Commission': com.tolist(),
            'ReturnPct': rp.tolist(),
            'EntryTime': [idx[i] for i in eb],
            'ExitTime': [idx[i] for i in xb],
        })
        t['Duration'] = t['ExitTime'] - t['EntryTime']
        t['Tag'] = [None] * len(t)
        return t
