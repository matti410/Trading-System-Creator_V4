"""
Ricerca delle uscite con `backtesting.py` (motore event-driven).

DOVE SI COLLOCA
---------------
Alternativa a exit_search.py (VectorBT) per lo stesso passo 3 della
pipeline: qui l'uscita a tempo e' ESATTA per costruzione (nessuna
approssimazione da misurare con controllo_durate) e l'ingresso alla open
della barra successiva e' il comportamento nativo della libreria — non
serve nessuno shift manuale del segnale.

LO STOP/TARGET ADATTIVO
------------------------
`soglie_adattive` qui sotto e' IDENTICA, stessa formula e stessa
causalita' gia' corretta il 16/9/2026, a quella di exit_search.py
(VectorBT). E' copiata qui invece che importata per non aggiungere
vectorbt/numba come dipendenza di un motore che non li usa. Se in futuro
exit_search.py entra a far parte dell'engine minimale, si puo' sostituire
questa copia con un import — vanno tenute in sincrono a mano nel
frattempo.

Riassunto della logica (vedi anche il docstring di soglie_adattive):
per ogni barra si misura quanto sarebbe andato in rosso/verde un trade
aperto li' e tenuto n barre; lo stop/target del trade che si apre ora e'
il percentile richiesto di quelle escursioni sulle ultime `finestra`
occorrenze CONCLUSE, lette con un ritardo di n + lag barre per evitare
di guardare nel futuro. Dal 17/9/2026 sono disattivate per default
(perc_sl=0, perc_tp=0): restano disponibili, ma non si attivano da sole.

COME SI APPLICA DENTRO backtesting.py
--------------------------------------
`soglie_adattive` restituisce FRAZIONI di prezzo, non prezzi assoluti.
Quando un trigger scatta a barra t, l'ordine si riempie a Open[t+1]: il
prezzo di ingresso non e' noto finche' l'ordine non e' eseguito. Si
piazza quindi l'ordine SENZA sl/tp; alla barra successiva (quella in cui
il trade e' visibile per la prima volta, `trade.entry_bar` == barra
corrente), si legge la soglia — gia' causale, letta con lag=execution_lag
— e si converte in prezzo assoluto usando `trade.entry_price`,
assegnandola a `trade.sl`/`trade.tp` (proprieta' scrivibili native).

L'USCITA A TEMPO
-----------------
Non e' nativa nella libreria: si tiene a mano confrontando la barra
corrente con `trade.entry_bar`. La chiusura viene richiesta un barra
PRIMA del traguardo (soglia = n_barre - 1), perche' anche la chiusura,
come ogni ordine di mercato, si riempie alla barra successiva: cosi'
`exit_bar - entry_bar` risulta esattamente n_barre, non n_barre + 1.
Resta il paracadute finale anche quando e' attiva una regola di uscita:
se la regola non scatta mai, il trade chiude comunque qui.

L'USCITA A REGOLA — SOLO COPPIE SPECULARI (aggiunta 17/9/2026, ristretta
a coppie lo stesso giorno — MODIFICA NON ADDITIVA dichiarata, stesso file
gia' modificato una volta per lo stop/target adattivo)
--------------------------------------------------------------------
Non due nomi indipendenti per lato: UNA sola etichetta `pair`, presa da
engine.registry.list_exit_pairs() — una condizione long e una short
registrate con lo stesso `pair` (es. "RSI_EXTREME" -> X1_RSI_OVERBOUGHT
lato long, X1_SHORT_RSI_OVERSOLD lato short). Impedisce strutturalmente
di accoppiare per errore una regola long con una short di un'idea
diversa (RSI long con MACD short, per dire).

Perche' solo coppie: in questo passo le ENTRY sono gia' state scelte e
restano fisse — l'unica dimensione che si sta esplorando e' l'uscita.
Un cartesiano libero fra exit long ed exit short moltiplicherebbe le
combinazioni provate senza un motivo economico (perche' mai una regola
long dovrebbe uscire su un segnale MACD mentre lo short esce su RSI?),
aumentando solo il rischio di trovare un vincitore per puro overfitting
sull'In-Sample — che poi crolla in Out-of-Sample. Restringere a coppie
riduce i gradi di liberta' inutili qui; non sostituisce la verifica vera
(due_meta, poi l'Out-of-Sample), che va comunque fatta a valle.

`exit_rule_pairs` accetta un'etichetta, una lista di etichette, o None
(nessuna regola: solo stop/target se attivi e tetto a tempo) — non e'
ancora una griglia annidata con le entry, e' un parametro della griglia
al pari di n_barre.

SEGNALI SCARTATI A INIZIO/FINE SERIE
--------------------------------------
Dove la soglia non e' ancora calcolabile (avvio della serie, finestra non
piena) il segnale di ingresso viene disattivato PRIMA di passare i dati a
backtesting.py — stessa filosofia di exit_search.py: un segnale che non
puo' avere uno stop/target viene ignorato, non tradato senza protezione.
Le regole di uscita non hanno questo problema (non dipendono da una
finestra mobile) e non vengono filtrate.

Modulo ADDITIVO rispetto a registry.py: lo usa in sola lettura, non lo
modifica.
"""
from __future__ import annotations

import warnings
from itertools import product

import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy

from .registry import get_entry, get_entry_direction, get_exit, list_exit_pairs
from .event_study import deduci_pip
from .metriche import metriche_per_trade, pips_per_trade
from .giudizio import soglia_rumore, t_stat


# ========================================================================
# 1 · Soglie adattive (identica a exit_search.py — vedi docstring sopra)
# ========================================================================

def soglie_adattive(df, n, finestra=500, perc_sl=90.0, perc_tp=90.0,
                    open_col="Open", high_col="High", low_col="Low", lag=0):
    """
    Soglie di SL e TP, barra per barra, come percentile delle escursioni
    recenti. Identica a exit_search.py — vedi il suo docstring per la
    spiegazione completa della causalita'.

    Ritorna un dict con quattro Series (frazioni del prezzo di ingresso):
    sl_long, tp_long, sl_short, tp_short. NaN dove la finestra non e'
    ancora piena, o dove il percentile richiesto e' disattivato (p<=0).
    """
    o = df[open_col]
    h = df[high_col]
    l = df[low_col]

    ingresso = o.shift(-1)
    max_h = h.rolling(n).max().shift(-n)
    min_l = l.rolling(n).min().shift(-n)

    giu = ((ingresso - min_l) / ingresso).clip(lower=0.0)
    su = ((max_h - ingresso) / ingresso).clip(lower=0.0)

    giu_oss = giu.shift(n + int(lag))
    su_oss = su.shift(n + int(lag))

    def perc(serie, p):
        if p is None or p <= 0:
            return pd.Series(np.nan, index=df.index)
        return serie.rolling(finestra, min_periods=finestra).quantile(p / 100.0)

    return {
        "sl_long": perc(giu_oss, perc_sl),
        "tp_long": perc(su_oss, perc_tp),
        "sl_short": perc(su_oss, perc_sl),
        "tp_short": perc(giu_oss, perc_tp),
    }


# ========================================================================
# 2 · Strategy generica — non conosce nessun trigger specifico
# ========================================================================

class _StrategiaGenerica(Strategy):
    """
    Legge quale colonna del df usare per il lato long e per il lato short
    da `long_col`/`short_col` (nomi di colonna, o None), e quale colonna
    tiene la regola di uscita per ciascun lato da
    `exit_rule_long_col`/`exit_rule_short_col` (nomi di colonna, o None) —
    impostati a ogni chiamata con bt.run(...). Le due colonne di uscita
    appartengono sempre alla STESSA coppia speculare (vedi run_exit_search_bt).
    """
    long_col = None
    short_col = None
    exit_rule_long_col = None
    exit_rule_short_col = None
    n_barre = 32

    def init(self):
        pass

    def next(self):
        if self.position:
            trade = self.trades[-1]
            barra_corrente = len(self.data) - 1

            if trade.entry_bar == barra_corrente:
                # prima barra in cui il trade e' visibile: e' la barra
                # d'ingresso stessa. La soglia letta qui e' gia' causale
                # (soglie_adattive, lag=execution_lag).
                if trade.is_long:
                    frac_sl, frac_tp = self.data.sl_long[-1], self.data.tp_long[-1]
                    if not np.isnan(frac_sl):
                        trade.sl = trade.entry_price * (1 - frac_sl)
                    if not np.isnan(frac_tp):
                        trade.tp = trade.entry_price * (1 + frac_tp)
                else:
                    frac_sl, frac_tp = self.data.sl_short[-1], self.data.tp_short[-1]
                    if not np.isnan(frac_sl):
                        trade.sl = trade.entry_price * (1 + frac_sl)
                    if not np.isnan(frac_tp):
                        trade.tp = trade.entry_price * (1 - frac_tp)

            # regola di uscita: chiude PRIMA del tetto a tempo se scatta
            col_regola = self.exit_rule_long_col if trade.is_long else self.exit_rule_short_col
            if col_regola is not None and bool(getattr(self.data, col_regola)[-1]):
                self.position.close()
                return

            # chiusura richiesta una barra prima del traguardo: anche lei
            # si riempie alla barra successiva (vedi docstring del modulo)
            if barra_corrente - trade.entry_bar >= self.n_barre - 1:
                self.position.close()
            return

        segnale_long = (self.long_col is not None
                        and bool(getattr(self.data, self.long_col)[-1]))
        segnale_short = (self.short_col is not None
                         and bool(getattr(self.data, self.short_col)[-1]))

        if segnale_long and not segnale_short:
            self.buy()
        elif segnale_short and not segnale_long:
            self.sell()


# ========================================================================
# 3 · Ricerca
# ========================================================================

def run_exit_search_bt(
    df,
    entry_cols_long=None,
    entry_cols_short=None,
    n_barre=32,
    exit_rule_pairs=None,
    perc_sl=0.0,
    perc_tp=0.0,
    finestra=500,
    lag=1,
    spread=0.0,
    commission=0.00007,
    cash=10_000.0,
    margin=1.0,
    min_trades=30,
    close_col="Close", open_col="Open", high_col="High", low_col="Low",
    verbose=True,
    alpha=0.05,
):
    """
    Cerca, per una griglia di trigger long/short (entry FISSE, gia' scelte
    al passo precedente) e una griglia di coppie di uscita a regola,
    la combinazione migliore con uscita a tempo esatta (n_barre) +
    stop/target adattivi (se attivi), usando backtesting.py.

    entry_cols_long / entry_cols_short
        Liste di nomi di condizioni registrate. Un elemento puo' essere
        None (significa "nessun ingresso su questo lato per questa
        combinazione"): utile per confrontare, nella stessa tabella, un
        sistema bidirezionale con la sua versione solo long o solo short.
        L'intero parametro puo' anche essere None: equivale a [None].
        Le combinazioni (None, None) — nessun ingresso — sono scartate a
        prescindere dalla coppia di uscita scelta.

    n_barre
        UN SOLO orizzonte di uscita forzata (a differenza di
        exit_search.py, qui non e' una lista: e' il primo passo di una
        griglia sulle entry, non ancora sugli orizzonti). Resta il
        paracadute finale anche quando una coppia di uscita e' attiva.

    exit_rule_pairs
        Un'etichetta `pair` (str), una lista di etichette, o None. Ogni
        etichetta viene risolta con engine.registry.list_exit_pairs() in
        UNA condizione Exit long + UNA Exit short registrate con lo
        stesso `pair` — mai un lato scelto indipendentemente dall'altro
        (vedi il docstring del modulo per il perche'). None nella lista
        equivale a "nessuna regola di uscita" per quella riga. Etichette
        non trovate fra le coppie disponibili sollevano ValueError con
        l'elenco di quelle valide.

    perc_sl / perc_tp
        Percentili delle escursioni per stop e target adattivi. Default
        0 (disattivati): la protezione, se la vuoi, va accesa a mano. 0 o
        None disattiva quella soglia (il trade resta protetto solo
        dall'altra, dalla regola di uscita e/o dalla scadenza a tempo).

    spread / commission
        Come in backtesting.py: spread applicato una volta all'ingresso,
        commission applicata sia in entrata che in uscita. Nessuno
        slippage esplicito: la libreria non lo prevede come parametro a
        se stante.

    margin
        Leva del conto (1.0 = nessuna leva, come una posizione
        interamente coperta dal cash disponibile; es. margin=1/30 = leva
        30:1). Incide su quanti contratti si aprono per volta e quindi
        su pnl_pct/max_dd_pct/equity — NON su avg_trade, che e' calcolato
        in pips dal solo prezzo di ingresso/uscita ed e' quindi
        leverage-invariant, la metrica giusta per confrontare i trigger
        fra loro a prescindere da come verranno poi dimensionati.

    alpha
        Famiglia della soglia di rumore (default 5%). La tabella ha la
        colonna `t_stat` (t sui pips NETTI per trade) e `oltre_rumore`:
        True se |t_stat| supera la soglia di Sidak per le k righe di
        questa chiamata. Conta solo le prove di questa chiamata: e' un
        pavimento.

    Ritorna un oggetto ExitSearchBT: .risultati (tabella), .top(),
    .trades(combinazione), .soglia_rumore, .k.
    """
    n_barre = int(n_barre)
    if n_barre < 1:
        raise ValueError("n_barre deve essere >= 1 (la scadenza e' sempre attiva in questo step).")

    def normalizza(lista):
        if lista is None:
            return [None]
        if isinstance(lista, str):
            return [lista]
        return list(lista)

    long_list = normalizza(entry_cols_long)
    short_list = normalizza(entry_cols_short)
    pair_list = normalizza(exit_rule_pairs)

    # --- risoluzione delle coppie di uscita ------------------------------
    pairs_disponibili = {p: (el, es) for p, el, es in list_exit_pairs()}
    pair_richieste = {p for p in pair_list if p is not None}
    mancanti = pair_richieste - set(pairs_disponibili)
    if mancanti:
        raise ValueError(
            f"Coppia/e di uscita non trovata/e: {sorted(mancanti)}. "
            f"Disponibili: {sorted(pairs_disponibili)}."
        )

    combinazioni_entry = [(l, s) for l, s in product(long_list, short_list)
                          if not (l is None and s is None)]
    if not combinazioni_entry:
        raise ValueError(
            "Nessuna combinazione valida: entry_cols_long ed entry_cols_short "
            "non possono essere entrambi None (o liste di soli None)."
        )
    combinazioni = [(l, s, p) for (l, s), p in product(combinazioni_entry, pair_list)]

    scartate = len(long_list) * len(short_list) * len(pair_list) - len(combinazioni)
    if verbose and scartate:
        print(f"{scartate} combinazione/i (None, None, *) scartata/e: nessun ingresso.")

    if verbose:
        for nome in long_list:
            if nome is not None and get_entry_direction(nome) != 1:
                print(f"nota: '{nome}' e' registrata short ed e' tradata long (segnale invertito).")
        for nome in short_list:
            if nome is not None and get_entry_direction(nome) != -1:
                print(f"nota: '{nome}' e' registrata long ed e' tradata short (segnale invertito).")

    # --- soglie adattive, una volta sola (n_barre e' unico in questo step)
    usa_sl = perc_sl not in (None, 0)
    usa_tp = perc_tp not in (None, 0)
    soglie = soglie_adattive(df, n_barre, finestra, perc_sl, perc_tp,
                             open_col, high_col, low_col, lag=lag)

    ok_long = pd.Series(True, index=df.index)
    ok_short = pd.Series(True, index=df.index)
    if usa_sl:
        ok_long &= ~soglie["sl_long"].isna()
        ok_short &= ~soglie["sl_short"].isna()
    if usa_tp:
        ok_long &= ~soglie["tp_long"].isna()
        ok_short &= ~soglie["tp_short"].isna()
    # il segnale nasce alla barra del trigger, la soglia si legge sulla
    # barra d'ingresso (una dopo): la validita' va controllata li'
    ok_long_al_segnale = ok_long.shift(-1, fill_value=False)
    ok_short_al_segnale = ok_short.shift(-1, fill_value=False)

    # --- costruzione delle colonne per backtesting.py -------------------
    df_bt = df.copy()
    df_bt["sl_long"] = soglie["sl_long"]
    df_bt["tp_long"] = soglie["tp_long"]
    df_bt["sl_short"] = soglie["sl_short"]
    df_bt["tp_short"] = soglie["tp_short"]

    ignorati = {}
    for nome in {n for n in long_list if n is not None}:
        grezzo = get_entry(nome)(df).astype(bool)
        finale = grezzo & ok_long_al_segnale
        ignorati[nome] = int((grezzo & ~ok_long_al_segnale).sum())
        df_bt[f"__long__{nome}"] = finale.to_numpy()
    for nome in {n for n in short_list if n is not None}:
        grezzo = get_entry(nome)(df).astype(bool)
        finale = grezzo & ok_short_al_segnale
        ignorati[nome] = int((grezzo & ~ok_short_al_segnale).sum())
        df_bt[f"__short__{nome}"] = finale.to_numpy()

    if verbose and any(ignorati.values()):
        dettaglio = ", ".join(f"{k}: {v}" for k, v in ignorati.items() if v)
        print(f"segnali ignorati per soglia non calcolabile — {dettaglio}")

    # colonne delle coppie di uscita: una volta per pair unica, nessun
    # filtro di validita' (non dipendono da una finestra mobile)
    pair_cols = {None: (None, None)}
    for pair in {p for p in pair_list if p is not None}:
        nome_long, nome_short = pairs_disponibili[pair]
        col_long = f"__exit_long__{pair}"
        col_short = f"__exit_short__{pair}"
        df_bt[col_long] = get_exit(nome_long)(df).astype(bool).to_numpy()
        df_bt[col_short] = get_exit(nome_short)(df).astype(bool).to_numpy()
        pair_cols[pair] = (col_long, col_short)

    # --- backtest, una sola costruzione, riusata per ogni combinazione --
    bt = Backtest(df_bt, _StrategiaGenerica, cash=cash, spread=spread,
                 commission=commission, margin=margin, exclusive_orders=True)

    prezzo_medio = float(df[close_col].mean())
    pip_size = deduci_pip(prezzo_medio)

    righe = []
    trades_per_combo = {}
    for l, s, pair in combinazioni:
        long_col = f"__long__{l}" if l is not None else None
        short_col = f"__short__{s}" if s is not None else None
        exit_rule_long_col, exit_rule_short_col = pair_cols[pair]
        # L'eventuale trade ancora aperto sull'ultima barra della serie
        # viene escluso dai risultati (default di backtesting.py,
        # finalize_trades=False): non si e' mai concluso secondo le
        # nostre regole, chiuderlo forzatamente all'ultimo prezzo
        # disponibile sarebbe un'uscita artificiale. L'avviso che la
        # libreria stampa per questo a ogni run viene silenziato perche'
        # e' previsto, testando molte combinazioni capita spesso.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            stats = bt.run(long_col=long_col, short_col=short_col, n_barre=n_barre,
                           exit_rule_long_col=exit_rule_long_col,
                           exit_rule_short_col=exit_rule_short_col)

        trades = stats["_trades"]
        etichetta = f"L={l or '—'} · S={s or '—'} | X={pair or '—'}"

        # avg_trade (lordo, invariato), avg_trade_netto e costo_pips: il
        # calcolo sta in engine/metriche.py, unico per i due motori.
        m = metriche_per_trade(trades, pip_size, commission)
        n_t = m["n_trades"]
        # t sui pips NETTI per trade: il numero da confrontare con la soglia
        # di rumore (i trade non si sovrappongono, exclusive_orders=True)
        _, netti = pips_per_trade(trades, pip_size, commission)

        righe.append({
            "combinazione": etichetta,
            "entry_long": l,
            "entry_short": s,
            "exit_rule_pair": pair,
            "trades": n_t,
            "pnl_pct": float(stats["Return [%]"]),
            "sharpe": float(stats["Sharpe Ratio"]),
            "max_dd_pct": float(stats["Max. Drawdown [%]"]),
            "win_rate_pct": float(stats["Win Rate [%]"]),
            "profit_factor": float(stats["Profit Factor"]),
            "avg_trade": m["avg_trade"],
            "avg_trade_netto": m["avg_trade_netto"],
            "t_stat": t_stat(netti),
            "costo_pips": m["costo_pips"],
            "durata_media": m["durata_media"],
            "durata_max": m["durata_max"],
            "pochi_trade": n_t < min_trades,
        })
        trades_per_combo[etichetta] = trades

    risultati = (pd.DataFrame(righe)
                .sort_values("sharpe", ascending=False)
                .reset_index(drop=True))

    # --- soglia di rumore (24/9/2026) -----------------------------------
    # Si sceglie la combinazione migliore fra k righe: oltre questo |t| il
    # risultato non e' piu' spiegabile dal caso. k = righe di QUESTA
    # chiamata, comprese quelle con pochi trade (sono state provate).
    k = len(risultati)
    soglia = soglia_rumore(k, alpha) if k else np.nan
    if k:
        risultati["oltre_rumore"] = risultati["t_stat"].abs() > soglia

    if verbose:
        print(f"{len(combinazioni)} combinazioni · n_barre={n_barre} · "
              f"coppie di uscita: {[p or '—' for p in pair_list]} · "
              f"stop adattivo {perc_sl}°/{perc_tp}° pct (finestra {finestra}) · "
              f"spread {spread:.5f} · commission {commission:.5f} · margin {margin}")
        if k:
            print(f"soglia di rumore per {k} righe (Sidak, famiglia {alpha:.0%}): "
                  f"|t_stat| > {soglia:.2f}  —  righe oltre: {int(risultati['oltre_rumore'].sum())}. "
                  f"Conta solo le prove di questa chiamata, e' un pavimento")

    return ExitSearchBT(risultati=risultati, trades_per_combo=trades_per_combo,
                        n_barre=n_barre, perc_sl=perc_sl, perc_tp=perc_tp,
                        finestra=finestra, spread=spread, commission=commission,
                        margin=margin, min_trades=min_trades,
                        soglia_rumore=soglia, k=k, alpha=alpha)


# ========================================================================
# 4 · Contenitore
# ========================================================================

class ExitSearchBT:
    """Risultato di run_exit_search_bt. Vedi .risultati, .top(), .trades()."""

    def __init__(self, risultati, trades_per_combo, n_barre, perc_sl,
                 perc_tp, finestra, spread, commission, margin, min_trades,
                 soglia_rumore=np.nan, k=0, alpha=0.05):
        self.risultati = risultati
        self._trades_per_combo = trades_per_combo
        self.n_barre = n_barre
        self.perc_sl = perc_sl
        self.perc_tp = perc_tp
        self.finestra = finestra
        self.spread = spread
        self.commission = commission
        self.margin = margin
        self.min_trades = min_trades
        # soglia di rumore della tabella (vedi run_exit_search_bt)
        self.soglia_rumore = soglia_rumore
        self.k = k
        self.alpha = alpha

    def __repr__(self):
        return f"<ExitSearchBT: {len(self.risultati)} combinazioni, n_barre={self.n_barre}>"

    def top(self, n=10, solo_valide=True, per="sharpe"):
        """Le migliori combinazioni. `solo_valide` toglie quelle con pochi trade."""
        r = self.risultati
        if solo_valide:
            r = r[~r["pochi_trade"]]
        # avg_trade_netto accanto al lordo: e' quello da confrontare con
        # zero. costo_pips resta solo in .risultati (e' quasi costante fra
        # le righe, in tabella sarebbe rumore).
        colonne = ["combinazione", "trades", "pnl_pct", "sharpe", "max_dd_pct",
                   "win_rate_pct", "profit_factor", "avg_trade", "avg_trade_netto",
                   "t_stat", "oltre_rumore", "durata_media", "durata_max"]
        return r.sort_values(per, ascending=False).head(n)[colonne].round(3)

    def trades(self, combinazione=None):
        """Trade grezzi (DataFrame nativo di backtesting.py) di una combinazione."""
        if combinazione is None:
            combinazione = self.top(1).iloc[0]["combinazione"]
        return self._trades_per_combo[combinazione]
