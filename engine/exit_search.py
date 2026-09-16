"""
Exit Search — ricerca delle condizioni di uscita con backtest VectorBT.

DOVE SI COLLOCA
---------------
event_study.py MISURA un segnale (nessun capitale, nessuna posizione).
Questo modulo costruisce un SISTEMA: si sceglie una entry (long, short o
entrambe) e si cerca il modo di uscire. Da qui in poi ci sono trade veri,
un conto, costi, drawdown.

COSA CONFRONTA
--------------
Per ogni combinazione di:
  - regola di uscita (una fra quelle registrate, oppure nessuna)
  - orizzonte temporale n (uscita forzata dopo n barre)
si esegue un backtest completo. Stop loss e take profit non sono parametri
da ottimizzare: sono un METODO adattivo (vedi sotto), attivabile o meno.

LO STOP ADATTIVO (il punto centrale del modulo)
-----------------------------------------------
Una soglia fissa in percentuale non e' trasferibile: 0.15% e' uno stop
larghissimo su EURUSD e strettissimo su BTCUSD. Qui SL e TP si ricavano
dalla distribuzione delle escursioni recenti dello strumento:

  Per ogni barra i si misura l'escursione dell'ipotetico trade aperto a
  Open[i+1] e tenuto n barre:
      escursione sfavorevole (long)  = (Open[i+1] - min Low[i+1..i+n]) / Open[i+1]
      escursione favorevole  (long)  = (max High[i+1..i+n] - Open[i+1]) / Open[i+1]
  Per lo short le due si scambiano: cio' che e' sfavorevole per un long e'
  favorevole per uno short e viceversa — quindi le serie da calcolare sono
  due, non quattro.

  Lo stop di un trade aperto alla barra t e' il percentile richiesto di
  quelle escursioni sulle ultime `finestra` occorrenze CONCLUSE.

CAUSALITA' (la parte che, se sbagliata, rende finto tutto il resto)
-------------------------------------------------------------------
L'escursione di un'occorrenza partita alla barra i si conosce solo alla
barra i+n. Se alla barra t si calcolasse il percentile sulle ultime 500
occorrenze *partite*, le piu' recenti non sarebbero ancora concluse: si
userebbero prezzi futuri per fissare lo stop di un trade aperto adesso, e
lo stop risulterebbe miracolosamente tarato sulla volatilita' in arrivo.

Qui la serie delle escursioni viene traslata di n barre PRIMA di calcolare
il percentile mobile: alla barra t entrano solo occorrenze partite entro
t-n, tutte concluse e osservabili. La finestra e' quindi piena ma spostata
all'indietro di n barre.

Attenzione a DOVE si legge lo stop. Il segnale nasce sulla barra t, ma il
trade apre a Open[t+1] e lo stop viene letto sulla barra d'ingresso t+1.
A quell'istante High e Low di t+1 non sono ancora noti. Per questo la
traslazione e' n + lag, dove lag e' il numero di barre fra segnale e
ingresso (execution_lag, di norma 1). Con la sola traslazione di n,
l'ultima occorrenza della finestra includeva High/Low della barra
d'ingresso: un'occhiata di una barra nel futuro (corretto il 16/09/2026).

AVVIO DELLA SERIE
-----------------
Nelle prime finestra + n + lag barre lo stop non e' calcolabile (valore
mancante). VectorBT leggerebbe un valore mancante come "stop disattivato"
e aprirebbe trade senza stop: un sistema diverso da quello dichiarato, e
con n = 0 (nessuna scadenza) una posizione che non si chiude mai. Per
questo, con stop/target attivi, i segnali che cadono dove una soglia
RICHIESTA non e' ancora disponibile vengono ignorati, e il loro numero
viene stampato. Una soglia spenta per scelta (perc = 0) non blocca nulla.

Il valore dello stop si FISSA all'apertura del trade e non cambia piu': e'
il dato di riferimento a variare barra per barra, non lo stop di una
posizione gia' aperta. E' il comportamento nativo di VectorBT.

L'USCITA A TEMPO — limite noto, misurato e non nascosto
--------------------------------------------------------
VectorBT open-source non ha un parametro di uscita a tempo: va costruita
come maschera di segnali. La maschera si ricava simulando le posizioni
barra per barra (regola di uscita + scadenza a n barre). Quando pero' sono
attivi anche SL/TP, VectorBT puo' chiudere un trade PRIMA di quanto la
simulazione prevedeva: da li' in poi gli ingressi reali e quelli simulati
si disallineano, e un segnale di scadenza "vecchio" puo' chiudere in
anticipo un trade successivo.

Per questo la tabella dei risultati riporta sempre `durata_media` e
`durata_max`: se si chiede un'uscita a 32 barre e i trade durano davvero
~32 barre, la riga e' affidabile; se durano molto meno, quella riga va
letta sapendo che il time-stop non e' stato rispettato. Il controllo
definitivo e' rieseguire il vincitore con un motore event-driven
(backtesting.py), dove l'uscita a tempo e' esatta per costruzione.

Modulo ADDITIVO: usa registry.py in sola lettura, non modifica nulla.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import vectorbt as vbt
from numba import njit

from .registry import (get_entry, get_entry_direction, get_exit,
                       get_exit_direction, get_exit_pair, list_exit_pairs,
                       list_exits)
from .event_study import deduci_pip


# ========================================================================
# 1 · Escursioni e soglie adattive
# ========================================================================

def soglie_adattive(df, n, finestra=500, perc_sl=90.0, perc_tp=90.0,
                    open_col="Open", high_col="High", low_col="Low", lag=0):
    """
    Soglie di SL e TP, barra per barra, come percentile delle escursioni
    recenti. Vedi il docstring del modulo per la logica e la causalita'.

    lag
        Barre fra il segnale e la barra su cui la soglia viene LETTA.
        0 = la soglia si legge sulla barra del segnale (usa dati fino alla
        sua chiusura). run_exit_search passa execution_lag, perche' legge
        lo stop sulla barra d'ingresso, di cui all'apertura non si
        conoscono High e Low.

    Ritorna un dict con quattro Series (frazioni del prezzo di ingresso):
    sl_long, tp_long, sl_short, tp_short. Valori NaN dove la finestra non
    e' ancora piena: li' non si opera.
    """
    o = df[open_col]
    h = df[high_col]
    l = df[low_col]

    ingresso = o.shift(-1)                      # Open[i+1]
    max_h = h.rolling(n).max().shift(-n)        # max High[i+1..i+n]
    min_l = l.rolling(n).min().shift(-n)        # min Low[i+1..i+n]

    # due serie bastano: lo sfavorevole del long e' il favorevole dello short
    giu = (ingresso - min_l) / ingresso         # quanto e' sceso sotto l'ingresso
    su = (max_h - ingresso) / ingresso          # quanto e' salito sopra l'ingresso
    giu = giu.clip(lower=0.0)
    su = su.clip(lower=0.0)

    # CAUSALITA': l'escursione partita in i e' osservabile solo alla
    # chiusura di i+n; letta lag barre dopo il segnale, serve n + lag
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
# 2 · Uscita a tempo (simulazione delle posizioni)
# ========================================================================

@njit(cache=True)
def _maschere_uscita(ent_l, ent_s, rex_l, rex_s, n):
    """
    Simula le posizioni barra per barra e produce QUATTRO maschere: gli
    ingressi effettivamente aperti e le uscite corrispondenti.

    Perche' anche gli ingressi: se su una stessa barra cadono un segnale di
    uscita e uno di ingresso, VectorBT deve risolvere il conflitto, e
    qualunque regola scelga una delle due parti viene persa — se vince
    l'ingresso l'uscita sparisce e il trade sfonda la scadenza temporale
    (osservato in produzione: trade da 47 barre su un tetto di 32, e in un
    caso limite una posizione mai chiusa). Restituendo gli ingressi
    EFFETTIVI il conflitto non si presenta proprio: VectorBT riceve
    esattamente le posizioni che la simulazione ha deciso.

    Convenzione: dopo un'uscita non si rientra sulla stessa barra NELLA
    STESSA DIREZIONE (sarebbe il conflitto descritto sopra). Un ingresso di
    direzione opposta sulla barra dell'uscita e' invece legittimo — per
    VectorBT non e' un conflitto — e viene preso: chiudere un long e aprire
    uno short sulla stessa apertura e' una normale inversione.
    """
    m = len(ent_l)
    in_l = np.zeros(m, np.bool_)
    in_s = np.zeros(m, np.bool_)
    out_l = np.zeros(m, np.bool_)
    out_s = np.zeros(m, np.bool_)
    stato = 0          # 0 flat, 1 long, -1 short
    barra = 0
    for i in range(m):
        uscito = 0            # 0 nessuna, 1 chiuso un long, -1 chiuso uno short
        if stato == 1:
            if rex_l[i] or (i - barra) >= n:
                out_l[i] = True
                stato = 0
                uscito = 1
        elif stato == -1:
            if rex_s[i] or (i - barra) >= n:
                out_s[i] = True
                stato = 0
                uscito = -1
        if stato == 0:
            if ent_l[i] and not ent_s[i] and uscito != 1:
                stato = 1
                barra = i
                in_l[i] = True
            elif ent_s[i] and not ent_l[i] and uscito != -1:
                stato = -1
                barra = i
                in_s[i] = True
    return in_l, in_s, out_l, out_s


# ========================================================================
# 3 · Ricerca
# ========================================================================

def run_exit_search(
    df,
    entry_long=None,
    entry_short=None,
    n_barre=(8, 16, 32, 64, 96),
    exit_rules=None,
    perc_sl=90.0,
    perc_tp=90.0,
    finestra=500,
    fees=0.0,
    slippage=0.0,
    init_cash=10_000.0,
    freq="15min",
    pip=None,
    min_trades=30,
    execution_lag=1,
    close_col="Close",
    open_col="Open",
    high_col="High",
    low_col="Low",
    verbose=True,
):
    """
    Cerca la combinazione (regola di uscita, orizzonte) migliore per una
    entry data, con backtest VectorBT completo.

    entry_long / entry_short
        Nomi delle condizioni di ingresso. Indipendenti: si puo' compilarne
        una sola (sistema unidirezionale) o entrambe (sistema unico, una
        sola equity). Non devono essere speculari.

    n_barre
        Orizzonti di uscita forzata da provare.

    exit_rules
        Lista di etichette `pair` delle regole di uscita (es. "RSI_EXTREME").
        None = tutte quelle registrate. La riga "SOLO_TEMPO" (nessuna
        regola) e' sempre inclusa come termine di paragone.

    perc_sl / perc_tp
        Percentili delle escursioni per stop e target. 0 o None = disattivato.
        Con entrambi a 0 si esce solo per regola e/o per scadenza temporale.

    fees
        Costo per operazione come frazione del controvalore (es. 0.00007 =
        0.7 bp). Include commissione e spread. Una tabella a costi zero e'
        una classifica di illusioni: va riempito.

    min_trades
        Le combinazioni con meno trade di cosi' vengono marcate, non tolte.
    """
    if entry_long is None and entry_short is None:
        raise ValueError("Serve almeno una fra entry_long ed entry_short.")
    # comodita': n_barre=96 e exit_rules="MACD_CROSS" sono accettati come
    # se fossero (96,) e ["MACD_CROSS"]
    if isinstance(n_barre, (int, np.integer)):
        n_barre = (int(n_barre),)
    n_barre = [0 if x is None else int(x) for x in n_barre]
    if not n_barre:
        raise ValueError("n_barre e' vuoto: serve almeno un orizzonte.")
    if isinstance(exit_rules, str):
        exit_rules = [exit_rules]

    # n = 0 (o None) significa "nessuna scadenza temporale": si esce solo per
    # regola e/o per SL/TP. Se pero' non resta NESSUN modo di uscire, il
    # trade non si chiude mai e la riga sarebbe priva di senso.
    senza_scadenza = any(x <= 0 for x in n_barre)
    stop_attivi = (perc_sl not in (None, 0)) or (perc_tp not in (None, 0))
    if senza_scadenza and not stop_attivi and (exit_rules is None or
                                               len(exit_rules) == 0):
        raise ValueError(
            "n_barre=0 toglie la scadenza temporale, ma senza regole di "
            "uscita e senza SL/TP il trade non si chiuderebbe mai. "
            "Attiva perc_sl/perc_tp oppure passa delle exit_rules."
        )
    # La direzione con cui una condizione e' registrata dice solo come si
    # legge quel pattern per convenzione, NON come vada tradato. Un pattern
    # registrato short che l'event study mostra funzionare al contrario va
    # messo nello slot long, ed e' giusto cosi': e' il modo corretto di
    # tradare un segnale invertito (vedi inverted.py — ribaltare il PnL a
    # valle sarebbe sbagliato, perche' i rendimenti si compongono e il
    # drawdown non e' speculare). Qui si segnala e si procede.
    invertite = []
    for nome, atteso in ((entry_long, 1), (entry_short, -1)):
        if nome is not None and get_entry_direction(nome) != atteso:
            invertite.append((nome, "long" if atteso == 1 else "short"))
    if invertite and verbose:
        for nome, slot in invertite:
            print(f"nota: '{nome}' e' registrata nella direzione opposta ed "
                  f"e' tradata {slot} (segnale invertito).")

    idx = df.index
    m = len(df)
    close = df[close_col]
    op = df[open_col]

    def segnale(nome, direzione):
        if nome is None:
            return pd.Series(False, index=idx)
        s = get_entry(nome)(df).astype(bool)
        return s.shift(execution_lag).fillna(False).astype(bool)

    ent_l = segnale(entry_long, 1)
    ent_s = segnale(entry_short, -1)
    conflitti = int((ent_l & ent_s).sum())
    if conflitti and verbose:
        print(f"ATTENZIONE: {conflitti} barre con ingresso long e short "
              f"insieme — scartate (direzione ambigua).")

    # --- regole di uscita disponibili -------------------------------
    coppie = {}
    for pair, nome_l, nome_s in list_exit_pairs():
        coppie[pair] = (nome_l, nome_s)
    if exit_rules is None:
        exit_rules = [p for p in coppie if p != "NO_EXIT"]
    else:
        mancanti = [p for p in exit_rules if p not in coppie]
        if mancanti:
            raise ValueError(f"Regole di uscita non registrate: {mancanti}. "
                             f"Disponibili: {sorted(coppie)}")
    regole = ["SOLO_TEMPO"] + list(exit_rules)

    cache_regole = {}
    for pair in exit_rules:
        nl, ns = coppie[pair]
        rl = get_exit(nl)(df).astype(bool) if nl else pd.Series(False, index=idx)
        rs = get_exit(ns)(df).astype(bool) if ns else pd.Series(False, index=idx)
        cache_regole[pair] = (
            rl.shift(execution_lag).fillna(False).astype(bool).to_numpy(),
            rs.shift(execution_lag).fillna(False).astype(bool).to_numpy(),
        )
    vuoto = np.zeros(m, bool)

    # --- soglie adattive, una volta per ogni n ----------------------
    usa_stop = (perc_sl not in (None, 0)) or (perc_tp not in (None, 0))
    soglie = {}
    for n in n_barre:
        # con n=0 (nessuna scadenza) le escursioni si misurano comunque su
        # una finestra di riferimento: si usa il piu' lungo degli orizzonti
        # richiesti, o 96 barre se non ce ne sono altri
        n_rif = n if n > 0 else max([x for x in n_barre if x > 0] + [96])
        soglie[n] = soglie_adattive(df, n_rif, finestra, perc_sl, perc_tp,
                                    open_col, high_col, low_col,
                                    lag=execution_lag) if usa_stop else None

    # --- costruzione delle colonne ----------------------------------
    el = ent_l.to_numpy()
    es = ent_s.to_numpy()
    valide = ~(el & es)
    el = el & valide
    es = es & valide

    # con stop/target attivi l'etichetta lo dichiara: "SOLO_TEMPO" da solo
    # deve voler dire sempre la stessa cosa, in qualunque run
    usa_sl = perc_sl not in (None, 0)
    usa_tp = perc_tp not in (None, 0)
    suffisso = ("+SL/TP" if (usa_sl and usa_tp) else
                "+SL" if usa_sl else "+TP" if usa_tp else "")
    ignorati = {}    # orizzonte -> segnali ignorati per stop non calcolabile

    colonne, LE, SE_, LX, SX, SL, TP = [], [], [], [], [], [], []
    for pair in regole:
        rl, rs = (vuoto, vuoto) if pair == "SOLO_TEMPO" else cache_regole[pair]
        for n in n_barre:
            etich = f"{n} barre" if n > 0 else "senza scadenza"
            colonne.append(f"{pair}{suffisso} · {etich}")

            if not usa_stop:
                # Nessuno stop: la simulazione conosce esattamente quando
                # ogni posizione si chiude, quindi puo' produrre ingressi e
                # uscite perfettamente allineati con quello che fara'
                # VectorBT. Scadenza temporale rispettata al 100%.
                n_eff = int(n) if n > 0 else m + 1
                il, is_, ux, sx = _maschere_uscita(el, es, rl, rs, n_eff)
            else:
                # Con SL/TP attivi la simulazione NON puo' sapere quando una
                # posizione si chiude: uno stop puo' scattare in qualsiasi
                # momento. Se si insistesse a simulare, si crederebbe dentro
                # a una posizione che VectorBT ha gia' chiuso e si
                # sopprimerebbero gli ingressi successivi — al limite (senza
                # scadenza) un solo trade su tutta la serie.
                # Quindi qui si lascia decidere a VectorBT, che lo stato
                # delle posizioni lo conosce davvero: gli ingressi passano
                # tutti, e la scadenza diventa un segnale di uscita n barre
                # dopo ogni segnale di ingresso. E' un'approssimazione, ed e'
                # esattamente cio' che `controllo_durate` misura.
                if n > 0:
                    tl = np.zeros(m, bool); tl[int(n):] = el[:m - int(n)]
                    ts = np.zeros(m, bool); ts[int(n):] = es[:m - int(n)]
                else:
                    tl = np.zeros(m, bool); ts = np.zeros(m, bool)
                ux, sx = (rl | tl), (rs | ts)
                # niente ingresso e uscita sulla stessa barra nella stessa
                # direzione: sarebbe un conflitto, e VectorBT ne perderebbe uno
                il, is_ = el & ~ux, es & ~sx
                # nessun ingresso dove una soglia RICHIESTA manca ancora
                # (avvio della serie): vedi "AVVIO DELLA SERIE" in cima
                s = soglie[n]
                ok_l = np.ones(m, bool)
                ok_s = np.ones(m, bool)
                if usa_sl:
                    ok_l &= ~np.isnan(s["sl_long"].to_numpy())
                    ok_s &= ~np.isnan(s["sl_short"].to_numpy())
                if usa_tp:
                    ok_l &= ~np.isnan(s["tp_long"].to_numpy())
                    ok_s &= ~np.isnan(s["tp_short"].to_numpy())
                ignorati[n] = int((el & ~ok_l).sum() + (es & ~ok_s).sum())
                il, is_ = il & ok_l, is_ & ok_s
            LE.append(il)
            SE_.append(is_)
            LX.append(ux)
            SX.append(sx)
            if usa_stop:
                s = soglie[n]
                # il valore letto all'ingresso dipende dalla direzione
                sl = np.where(is_, s["sl_short"].to_numpy(), s["sl_long"].to_numpy())
                tp = np.where(is_, s["tp_short"].to_numpy(), s["tp_long"].to_numpy())
                SL.append(sl)
                TP.append(tp)

    cols = pd.Index(colonne, name="combinazione")
    f = lambda lst: pd.DataFrame(np.column_stack(lst), index=idx, columns=cols)
    long_entries, short_entries = f(LE), f(SE_)
    long_exits, short_exits = f(LX), f(SX)
    sl_stop = f(SL) if usa_stop else np.nan
    tp_stop = f(TP) if usa_stop else np.nan

    if verbose and ignorati and max(ignorati.values()) > 0:
        dettaglio = ", ".join(f"{'senza scadenza' if k <= 0 else str(k)}: {v}"
                              for k, v in ignorati.items())
        print(f"segnali ignorati a inizio serie, stop non ancora "
              f"calcolabile — per orizzonte: {dettaglio}")
    if verbose:
        print(f"{len(colonne)} combinazioni "
              f"({len(regole)} regole × {len(n_barre)} orizzonti) · "
              f"fees {fees:.5f} · "
              f"stop {'adattivo ' + str(perc_sl) + '°/' + str(perc_tp) + '° pct' if usa_stop else 'disattivato'}")

    pf = vbt.Portfolio.from_signals(
        close, long_entries, long_exits,
        short_entries=short_entries, short_exits=short_exits,
        open=op, high=df[high_col], low=df[low_col],
        price=op,                      # esecuzione all'apertura della barra
        sl_stop=sl_stop, tp_stop=tp_stop,
        fees=fees, slippage=slippage,
        init_cash=init_cash, freq=freq,
    )

    ris = _metriche(pf, cols, m, df, pip, min_trades)
    if verbose:
        print(f"fatto · {int(ris['trades'].sum()):,} trade totali")
    return ExitSearch(risultati=ris, portfolio=pf, n_barre=tuple(n_barre),
                      regole=regole, perc_sl=perc_sl, perc_tp=perc_tp,
                      finestra=finestra, fees=fees, min_trades=min_trades)


# ========================================================================
# 4 · Metriche
# ========================================================================

def _metriche(pf, cols, m, df, pip, min_trades):
    r = pf.trades.records
    prezzo_medio = float(df["Close"].mean())
    pip_size = float(pip) if pip is not None else deduci_pip(prezzo_medio)

    conteggio = pf.trades.count()
    win_rate = pf.trades.win_rate()
    profit_factor = pf.trades.profit_factor()
    expectancy = pf.trades.expectancy()
    sharpe = pf.sharpe_ratio()
    sortino = pf.sortino_ratio()
    calmar = pf.calmar_ratio()
    maxdd = pf.max_drawdown()
    tot_ret = pf.total_return()

    righe = []
    for j, nome in enumerate(cols):
        t = r[r["col"] == j]
        n_t = int(len(t))
        if n_t:
            dur = (t["exit_idx"] - t["entry_idx"]).to_numpy()
            ret = t["return"].to_numpy()
            vinc, perd = ret[ret > 0], ret[ret < 0]
            esposizione = float(dur.sum()) / m
            avg_win = float(vinc.mean()) * 100 if vinc.size else np.nan
            avg_loss = float(perd.mean()) * 100 if perd.size else np.nan
            avg_trade = float(ret.mean()) * 100
            avg_pips = avg_trade / 100 * prezzo_medio / pip_size
            worst = float(ret.min()) * 100
            best = float(ret.max()) * 100
            dur_media, dur_max = float(dur.mean()), int(dur.max())
        else:
            esposizione = avg_win = avg_loss = avg_trade = avg_pips = np.nan
            worst = best = dur_media = np.nan
            dur_max = 0

        righe.append({
            "combinazione": nome,
            "trades": n_t,
            "pnl_pct": float(tot_ret.iloc[j]) * 100,
            "sharpe": float(sharpe.iloc[j]),
            "sortino": float(sortino.iloc[j]),
            "calmar": float(calmar.iloc[j]),
            "max_dd_pct": float(maxdd.iloc[j]) * 100,
            "win_rate_pct": float(win_rate.iloc[j]) * 100,
            "profit_factor": float(profit_factor.iloc[j]),
            "avg_trade_pct": avg_trade,
            "avg_trade_pips": avg_pips,
            "expectancy": float(expectancy.iloc[j]),
            "avg_win_pct": avg_win,
            "avg_loss_pct": avg_loss,
            "worst_trade_pct": worst,
            "best_trade_pct": best,
            "durata_media": dur_media,
            "durata_max": dur_max,
            "esposizione_pct": esposizione * 100,
            "pochi_trade": n_t < min_trades,
        })
    return (pd.DataFrame(righe)
            .sort_values("sharpe", ascending=False)
            .reset_index(drop=True))


# ========================================================================
# 5 · Contenitore
# ========================================================================

class ExitSearch:
    """Risultato di run_exit_search. Vedi .risultati, .top(), .equity()."""

    def __init__(self, risultati, portfolio, n_barre, regole, perc_sl,
                 perc_tp, finestra, fees, min_trades):
        self.risultati = risultati
        self.portfolio = portfolio
        self.n_barre = n_barre
        self.regole = regole
        self.perc_sl = perc_sl
        self.perc_tp = perc_tp
        self.finestra = finestra
        self.fees = fees
        self.min_trades = min_trades

    def __repr__(self):
        return (f"<ExitSearch: {len(self.risultati)} combinazioni, "
                f"fees={self.fees}>")

    def top(self, n=10, solo_valide=True, per="sharpe"):
        """Le migliori combinazioni. `solo_valide` toglie quelle con pochi
        trade, che affollano la cima di qualunque classifica."""
        r = self.risultati
        if solo_valide:
            r = r[~r["pochi_trade"]]
        colonne = ["combinazione", "trades", "pnl_pct", "sharpe", "max_dd_pct",
                   "win_rate_pct", "profit_factor", "avg_trade_pips",
                   "durata_media", "esposizione_pct"]
        return r.sort_values(per, ascending=False).head(n)[colonne].round(3)

    def controllo_durate(self):
        """
        L'uscita a tempo e' stata rispettata? Confronta la durata media
        osservata con l'orizzonte richiesto. Vedi il docstring del modulo:
        con SL/TP attivi il time-stop puo' chiudere in anticipo.
        """
        r = self.risultati.copy()
        r["n_richiesto"] = (r["combinazione"].str.extract(r"· (\d+) barre")[0]
                            .astype(float))   # NaN sulle righe senza scadenza
        r["rapporto"] = r["durata_media"] / r["n_richiesto"]
        out = r[["combinazione", "n_richiesto", "durata_media", "durata_max",
                 "rapporto", "trades"]].sort_values("rapporto")
        print("rapporto vicino a 1 = il time-stop e' stato rispettato")
        print("rapporto molto < 1  = i trade chiudono prima (SL/TP o regola)")
        return out.round(3)

    def equity(self, combinazione=None, figsize=(11, 5)):
        """Curva di equity di una combinazione (default: la migliore)."""
        import matplotlib.pyplot as plt

        if combinazione is None:
            combinazione = self.top(1).iloc[0]["combinazione"]
        val = self.portfolio.value()[combinazione]
        fig, ax = plt.subplots(figsize=figsize)
        ax.plot(val.index, val.values, lw=1.4)
        ax.set_title(f"Equity · {combinazione}")
        ax.set_ylabel("valore del conto")
        ax.grid(alpha=.3)
        plt.tight_layout()
        plt.show()


# ========================================================================
# 6 · Verifica sulle due meta' dell'In-Sample
# ========================================================================

def due_meta(df, **kwargs):
    """
    Riesegue la stessa ricerca sulle due meta' dell'In-Sample e affianca i
    risultati. Serve contro l'illusione da griglia: con decine di
    combinazioni qualcuna sembra ottima per fortuna, e il modo piu'
    economico di smascherarla e' chiedere che funzioni su due periodi
    diversi. L'Out-of-Sample resta chiuso.

    Le colonne _1 e _2 sono le due meta'. Guarda `coerente`: True quando
    entrambe hanno Sharpe positivo e lo stesso segno di PnL.
    """
    meta = len(df) // 2
    kwargs.setdefault("verbose", False)
    r1 = run_exit_search(df.iloc[:meta], **kwargs).risultati
    r2 = run_exit_search(df.iloc[meta:], **kwargs).risultati

    cols = ["combinazione", "trades", "pnl_pct", "sharpe", "max_dd_pct",
            "profit_factor"]
    m = (r1[cols].merge(r2[cols], on="combinazione", suffixes=("_1", "_2")))
    m["coerente"] = ((m["sharpe_1"] > 0) & (m["sharpe_2"] > 0) &
                     (np.sign(m["pnl_pct_1"]) == np.sign(m["pnl_pct_2"])))
    return m.sort_values("sharpe_2", ascending=False).round(3)
