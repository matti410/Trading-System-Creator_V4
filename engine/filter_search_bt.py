"""
Ricerca dei filtri con `backtesting.py` — Passo 5, pipeline Trend Following.

Modulo ADDITIVO rispetto a `exit_search_bt.py`: lo importa in sola lettura
(stesso motore `backtesting.py`, stessa `soglie_adattive`, stessa strategia
generica `_StrategiaGenerica`), non lo modifica.

L'ENTRY E L'USCITA RESTANO CONGELATE
--------------------------------------
`entry_long`, `entry_short` e `exit_rule_pair` sono UN SOLO nome ciascuno
(o None), non liste: qui non si ricerca ne' l'entry ne' l'uscita, si
ricevono gia' scelte dai passi precedenti (vedi ROADMAP_RICERCA.md, Passo
5, "L'uscita resta congelata"). L'unica dimensione esplorata e' `filtri`.

COME SI APPLICA UN FILTRO — LA DIRECTION DECIDE IL LATO
----------------------------------------------------------
Ogni filtro ha una `direction` (`get_filter_direction`): +1, -1, o 0.
Pipeline Trend Following (vedi ROADMAP_RICERCA.md, Passo 5):

    direction == 0   si applica in AND su ENTRAMBI i lati attivi
    direction == +1  si applica in AND SOLO sul lato long
    direction == -1  si applica in AND SOLO sul lato short

COPPIE DI FILTRI (`get_filter_pair` / `list_filter_pairs`, 18/9/2026)
------------------------------------------------------------------------
Due filtri con lo stesso `pair` (uno +1, uno -1 — es. F12_EXTENDED_UP /
F13_EXTENDED_DOWN) NON producono due righe indipendenti: sono la stessa
idea ("il sistema richiede estensione coerente con la propria direzione")
e vengono raccolte in UNA riga, che applica il membro +1 al lato long e il
membro -1 al lato short, nella stessa riga — stessa logica gia' in uso per
`exit_rule_pairs`. Una coppia entra in gioco solo se ENTRAMBI i suoi membri
sono nella lista `filtri` passata alla funzione: se ne chiedi solo uno, resta
un filtro singolo (comportamento standalone, sotto).

Filtri senza `pair` (neutri, o direzionali senza uno speculare dichiarato)
restano righe singole, come prima di questa aggiunta.

TRIGGER A UN SOLO LATO (solo entry_long o solo entry_short)
---------------------------------------------------------------
Se il setup ha un solo lato attivo, una coppia si riduce al solo membro
compatibile con quel lato — l'altro membro non ha nessun ingresso a cui
applicarsi, esattamente come un filtro standalone il cui lato non e'
attivo. In questo caso la riga NON si etichetta con il nome della coppia
(implicherebbe che entrambe le direzioni sono state messe alla prova): si
etichetta con il nome del singolo membro davvero testato. Nessun errore,
nessuna riga inventata per il lato assente.

UN FILTRO ALLA VOLTA
---------------------
Ogni riga applica UNA sola idea (un filtro singolo, o una coppia trattata
come un'unica idea) — mai la combinazione di due idee diverse insieme. La
prima riga e' sempre la BASELINE (nessun filtro): il setup congelato cosi'
com'e', per il confronto.

due_meta NON E' QUI
---------------------
La verifica sulle due meta' (Difesa C, Passo 5) non e' in questo modulo:
si richiama a parte, in una cella separata del notebook, sui filtri che
qui risultano promettenti — decisione presa il 18/9/2026 (vedi
RIEPILOGO_CHAT_BACKTESTING_PY.md).
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from backtesting import Backtest

from .registry import (get_entry, get_exit, get_filter, get_filter_direction,
                        list_exit_pairs, list_filter_pairs)
from .event_study import deduci_pip
from .exit_search_bt import soglie_adattive, _StrategiaGenerica
from .metriche import metriche_per_trade, pips_per_trade
from .giudizio import (RIFERIMENTO, p_ev_negativo, soglia_rumore, t_stat,
                       tenuti_scartati, verdetto)

BASELINE = "— baseline —"


def run_filter_search_bt(
    df,
    entry_long=None,
    entry_short=None,
    exit_rule_pair=None,
    n_barre=32,
    filtri=None,
    perc_sl=0.0,
    perc_tp=0.0,
    finestra=500,
    lag=1,
    spread=0.0,
    commission=0.00007,
    cash=10_000.0,
    margin=1.0,
    min_trades=30,
    min_trades_giudizio=100,
    p_max=5.0,
    alpha=0.05,
    n_boot=10_000,
    seed=0,
    close_col="Close", open_col="Open", high_col="High", low_col="Low",
    verbose=True,
):
    """
    Testa una lista di filtri, un'idea alla volta, in AND sull'entry (o
    sulle entry) gia' scelte — con uscita e orizzonte anch'essi gia'
    scelti e congelati. Confronta ogni riga con la baseline (nessun
    filtro) sulla colonna `guadagno_sharpe`.

    entry_long / entry_short
        Un solo nome di entry registrata ciascuno (o None). Almeno uno dei
        due deve essere specificato.

    exit_rule_pair
        Una sola etichetta `pair` di uscita (o None). Risolta con
        engine.registry.list_exit_pairs().

    n_barre
        Tetto a tempo, esatto per costruzione. Uguale per baseline e per
        ogni riga (l'uscita resta congelata, non si ricerca qui).

    filtri
        Lista di nomi di filtri registrati. Due filtri con lo stesso
        `pair` (get_filter_pair) diventano una riga sola (vedi il
        docstring del modulo); tutti gli altri restano righe singole, con
        get_filter_direction a decidere il lato. Un filtro il cui lato non
        e' attivo viene saltato.

    perc_sl / perc_tp, spread, commission, margin, min_trades
        Stesso significato di run_exit_search_bt.

    min_trades_giudizio, p_max, alpha
        Soglie del verdetto (vedi engine/giudizio.py). `min_trades_giudizio`
        separa CAMPIONE CORTO da DA VALUTARE — default 100, la regola gia'
        scritta in ROADMAP_RICERCA.md, Passo 5 ("sotto il centinaio di
        trigger filtrati ci si ferma"). `p_max` e' la soglia su P(EV<0),
        default 5% (Lezione 9). `alpha` e' il rischio di famiglia della
        soglia sui test multipli. Tutte parametriche: se cambi idea su una
        soglia la passi qui, non riscrivi il modulo.

    n_boot, seed
        Ricampionamenti del bootstrap di P(EV<0), e seme per renderlo
        riproducibile.

    Ritorna un oggetto FilterSearchBT: .risultati (tabella), .top(),
    .trades(filtro).
    """
    n_barre = int(n_barre)
    if n_barre < 1:
        raise ValueError("n_barre deve essere >= 1.")
    if entry_long is None and entry_short is None:
        raise ValueError(
            "Serve almeno un entry_long o un entry_short (setup congelato "
            "dal Passo 3/Passo 4)."
        )

    filtri = list(filtri) if filtri else []

    # --- risoluzione dell'unica coppia di uscita --------------------------
    exit_long_nome = exit_short_nome = None
    if exit_rule_pair is not None:
        pairs_uscita = {p: (el, es) for p, el, es in list_exit_pairs()}
        if exit_rule_pair not in pairs_uscita:
            raise ValueError(
                f"Coppia di uscita non trovata: {exit_rule_pair!r}. "
                f"Disponibili: {sorted(pairs_uscita)}."
            )
        exit_long_nome, exit_short_nome = pairs_uscita[exit_rule_pair]

    # --- soglie adattive, una volta sola (n_barre unico in questo step) --
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
    ok_long_al_segnale = ok_long.shift(-1, fill_value=False)
    ok_short_al_segnale = ok_short.shift(-1, fill_value=False)

    # --- ingressi grezzi (una volta sola) ---------------------------------
    grezzo_long = get_entry(entry_long)(df).astype(bool) if entry_long is not None else None
    grezzo_short = get_entry(entry_short)(df).astype(bool) if entry_short is not None else None
    base_long = (grezzo_long & ok_long_al_segnale) if grezzo_long is not None else None
    base_short = (grezzo_short & ok_short_al_segnale) if grezzo_short is not None else None

    # --- piano delle righe: baseline + coppie complete + filtri singoli --
    # ogni riga: (etichetta, filtro_da_applicare_al_long_o_None,
    #             filtro_da_applicare_allo_short_o_None)
    richiesti = set(filtri)
    usati = set()
    piano = [(BASELINE, None, None)]

    for pair_label, nome_up, nome_down in list_filter_pairs():
        if nome_up not in richiesti or nome_down not in richiesti:
            continue  # coppia non richiesta per intero: i due membri restano standalone
        usati.add(nome_up)
        usati.add(nome_down)
        f_long = nome_up if base_long is not None else None
        f_short = nome_down if base_short is not None else None
        # entry_long o entry_short is None e' l'unico modo per cui
        # entrambi risulterebbero None, ma allora la funzione avrebbe gia'
        # sollevato ValueError sopra: qui almeno uno dei due c'e' sempre.
        etichetta = pair_label if (f_long is not None and f_short is not None) else (f_long or f_short)
        piano.append((etichetta, f_long, f_short))

    saltati = []
    for nome in filtri:
        if nome in usati:
            continue
        direction = get_filter_direction(nome)
        applica_long = base_long is not None and direction in (0, 1)
        applica_short = base_short is not None and direction in (0, -1)
        if not applica_long and not applica_short:
            saltati.append(nome)
            continue
        piano.append((nome, nome if applica_long else None, nome if applica_short else None))

    if verbose and saltati:
        print(f"{len(saltati)} filtro/i saltato/i (nessun lato attivo per "
              f"quella direction): {saltati}")

    # --- costruzione di TUTTE le colonne PRIMA di Backtest() -------------
    # Backtest() legge il DataFrame alla costruzione: una colonna aggiunta
    # dopo non e' visibile a bt.run(), va quindi tutto precalcolato qui.
    df_bt = df.copy()
    df_bt["sl_long"] = soglie["sl_long"]
    df_bt["tp_long"] = soglie["tp_long"]
    df_bt["sl_short"] = soglie["sl_short"]
    df_bt["tp_short"] = soglie["tp_short"]
    if exit_long_nome is not None:
        df_bt["__exit_long__"] = get_exit(exit_long_nome)(df).astype(bool).to_numpy()
    if exit_short_nome is not None:
        df_bt["__exit_short__"] = get_exit(exit_short_nome)(df).astype(bool).to_numpy()

    # Le maschere GREZZE dei filtri (non quelle gia' messe in AND con
    # l'entry) servono dopo, per partizionare i trade della baseline in
    # tenuti/scartati — vedi engine/giudizio.py. Si calcolano una volta
    # sola qui, insieme alle colonne.
    piano_colonne = []  # (etichetta, f_long, f_short, col_long, col_short, m_long, m_short)
    cache_maschere = {}

    def maschera(nome):
        if nome not in cache_maschere:
            cache_maschere[nome] = get_filter(nome)(df).astype(bool).to_numpy()
        return cache_maschere[nome]

    for etichetta, filtro_long, filtro_short in piano:
        col_long = col_short = None
        m_long = m_short = None
        if base_long is not None:
            m = base_long
            if filtro_long is not None:
                m_long = maschera(filtro_long)
                m = m & pd.Series(m_long, index=df.index)
            col_long = f"__long_f__{etichetta}"
            df_bt[col_long] = m.to_numpy()
        if base_short is not None:
            m = base_short
            if filtro_short is not None:
                m_short = maschera(filtro_short)
                m = m & pd.Series(m_short, index=df.index)
            col_short = f"__short_f__{etichetta}"
            df_bt[col_short] = m.to_numpy()
        piano_colonne.append((etichetta, filtro_long, filtro_short,
                              col_long, col_short, m_long, m_short))

    # --- backtest, una sola costruzione, riusata per ogni riga ------------
    bt = Backtest(df_bt, _StrategiaGenerica, cash=cash, spread=spread,
                 commission=commission, margin=margin, exclusive_orders=True)

    prezzo_medio = float(df[close_col].mean())
    pip_size = deduci_pip(prezzo_medio)

    righe = []
    trades_per_filtro = {}
    maschere_per_filtro = {}
    for (etichetta, filtro_long, filtro_short, col_long, col_short,
         m_long, m_short) in piano_colonne:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            stats = bt.run(
                long_col=col_long, short_col=col_short, n_barre=n_barre,
                exit_rule_long_col="__exit_long__" if exit_long_nome is not None else None,
                exit_rule_short_col="__exit_short__" if exit_short_nome is not None else None,
            )

        trades = stats["_trades"]

        # stesso calcolo di exit_search_bt: engine/metriche.py, un posto solo.
        m = metriche_per_trade(trades, pip_size, commission)
        n_t = m["n_trades"]

        # il sistema filtrato realizzato guadagna? (t e P(EV<0) sui suoi
        # pips netti). Domanda distinta da "il filtro aggiunge qualcosa",
        # che si misura piu' sotto su tenuti vs scartati.
        if n_t:
            _, netti = pips_per_trade(trades, pip_size, commission)
            netti = netti.to_numpy()
            t_riga = t_stat(netti)
            p_riga = p_ev_negativo(netti, n_boot=n_boot, seed=seed)
        else:
            t_riga = p_riga = np.nan

        righe.append({
            "filtro": etichetta,
            "filtro_long": filtro_long or "—",
            "filtro_short": filtro_short or "—",
            "trades": n_t,
            "pnl_pct": float(stats["Return [%]"]),
            "sharpe": float(stats["Sharpe Ratio"]),
            "max_dd_pct": float(stats["Max. Drawdown [%]"]),
            "win_rate_pct": float(stats["Win Rate [%]"]),
            "profit_factor": float(stats["Profit Factor"]),
            "avg_trade": m["avg_trade"],
            "avg_trade_netto": m["avg_trade_netto"],
            "costo_pips": m["costo_pips"],
            "t_stat": t_riga,
            "p_ev_neg": p_riga,
            "durata_media": m["durata_media"],
            "durata_max": m["durata_max"],
            "pochi_trade": n_t < min_trades,
        })
        trades_per_filtro[etichetta] = trades
        maschere_per_filtro[etichetta] = (m_long, m_short)

    risultati = pd.DataFrame(righe)
    base_row = risultati.loc[risultati["filtro"] == BASELINE].iloc[0]
    risultati["guadagno_sharpe"] = risultati["sharpe"] - base_row["sharpe"]
    risultati["guadagno_avg_trade"] = risultati["avg_trade"] - base_row["avg_trade"]

    # --- il confronto che decide: tenuti vs scartati dentro la baseline --
    # I trade filtrati NON sono un sottoinsieme della baseline (scartare un
    # trade libera il posto e ne abilita altri, prima bloccati da una
    # posizione aperta). Vedi engine/giudizio.py per il perche' questo
    # rende illecito ogni test appaiato.
    base_trades = trades_per_filtro[BASELINE]
    if len(base_trades):
        _, base_netti = pips_per_trade(base_trades, pip_size, commission)
        base_netti = base_netti.to_numpy()
        base_chiavi = set(zip(base_trades["EntryBar"].to_numpy(),
                              np.sign(base_trades["Size"].to_numpy())))
    else:
        base_netti, base_chiavi = np.array([]), set()

    k = max(1, len(piano_colonne) - 1)          # quante prove, baseline esclusa
    soglia = soglia_rumore(k, alpha=alpha)

    extra = []
    for _, r in risultati.iterrows():
        et = r["filtro"]
        if et == BASELINE:
            extra.append({"n_tenuti": np.nan, "n_scartati": np.nan,
                          "guadagno_pips": np.nan, "t_guadagno": np.nan,
                          "trade_nuovi": np.nan, "oltre_rumore": False,
                          "esito": RIFERIMENTO, "motivo": ""})
            continue
        m_long, m_short = maschere_per_filtro[et]
        ts = tenuti_scartati(base_trades, base_netti, m_long, m_short)

        fs_trades = trades_per_filtro[et]
        nuovi = (len(fs_trades) - len(
            set(zip(fs_trades["EntryBar"].to_numpy(),
                    np.sign(fs_trades["Size"].to_numpy()))) & base_chiavi)
        ) if len(fs_trades) else 0

        v = verdetto(ev=r["avg_trade_netto"], p_neg=r["p_ev_neg"],
                     n_trades=int(r["trades"]), t=ts["t_guadagno"],
                     soglia_t=soglia, guadagno=ts["guadagno_pips"],
                     p_max=p_max, min_trades=min_trades_giudizio)
        extra.append({
            "n_tenuti": ts["n_tenuti"], "n_scartati": ts["n_scartati"],
            "guadagno_pips": ts["guadagno_pips"], "t_guadagno": ts["t_guadagno"],
            "trade_nuovi": int(nuovi),
            "oltre_rumore": bool(np.isfinite(ts["t_guadagno"])
                                 and abs(ts["t_guadagno"]) > soglia),
            "esito": v["esito"], "motivo": v["motivo"],
        })

    risultati = pd.concat([risultati.reset_index(drop=True),
                           pd.DataFrame(extra)], axis=1)
    # la colonna che decide e' t_guadagno, non piu' guadagno_sharpe
    # (che resta in .risultati come riferimento).
    risultati = (risultati.sort_values("t_guadagno", ascending=False,
                                       na_position="last")
                .reset_index(drop=True))

    if verbose:
        print(f"{len(piano_colonne)} righe (baseline + {k} "
              f"filtri/coppie) · n_barre={n_barre} · exit_rule_pair={exit_rule_pair or '—'} "
              f"· stop adattivo {perc_sl}°/{perc_tp}° pct (finestra {finestra}) · "
              f"spread {spread:.5f} · commission {commission:.5f} · margin {margin}")
        print(f"soglia di rumore per {k} prove (Sidak, famiglia {alpha:.0%}): "
              f"|t_guadagno| > {soglia:.2f}  —  conta solo le prove di questa "
              "chiamata, e' un pavimento")

    return FilterSearchBT(risultati=risultati, trades_per_filtro=trades_per_filtro,
                          entry_long=entry_long, entry_short=entry_short,
                          exit_rule_pair=exit_rule_pair, n_barre=n_barre,
                          min_trades=min_trades, soglia_rumore=soglia,
                          pip_size=pip_size, commission=commission)


class FilterSearchBT:
    """Risultato di run_filter_search_bt. Vedi .risultati, .top(), .trades()."""

    def __init__(self, risultati, trades_per_filtro, entry_long, entry_short,
                 exit_rule_pair, n_barre, min_trades, soglia_rumore=None,
                 pip_size=None, commission=None):
        self.risultati = risultati
        self._trades_per_filtro = trades_per_filtro
        self.entry_long = entry_long
        self.entry_short = entry_short
        self.exit_rule_pair = exit_rule_pair
        self.n_barre = n_barre
        self.min_trades = min_trades
        self.soglia_rumore = soglia_rumore
        self.pip_size = pip_size
        self.commission = commission

    def __repr__(self):
        return f"<FilterSearchBT: {len(self.risultati)} righe (baseline + filtri)>"

    def top(self, n=10, solo_valide=True, includi_baseline=True):
        """
        Le migliori righe per `guadagno_sharpe` (quanto la riga aggiunge
        rispetto alla baseline, non il valore assoluto — Difesa A, Passo
        5). `solo_valide` toglie le righe con pochi trade (la baseline non
        viene mai tolta da questo filtro).
        """
        r = self.risultati
        if solo_valide:
            r = r[(~r["pochi_trade"]) | (r["filtro"] == BASELINE)]
        if not includi_baseline:
            r = r[r["filtro"] != BASELINE]
        # Tabella stretta e leggibile: la decisione sta in t_guadagno e
        # esito. Tutto il resto (sharpe, guadagno_sharpe, costo_pips,
        # max_dd_pct, durate, filtro_long/short) resta in .risultati.
        colonne = ["filtro", "trades", "avg_trade_netto", "t_stat", "p_ev_neg",
                   "guadagno_pips", "t_guadagno", "oltre_rumore",
                   "esito", "motivo"]
        return (r.sort_values("t_guadagno", ascending=False, na_position="last")
                .head(n)[colonne].round(3))

    def scheda(self, filtro=None, **kwargs):
        """
        La scheda KPI completa di una riga (default: la baseline).
        Vedi engine.giudizio.scheda_strategia.
        """
        from .giudizio import scheda_strategia
        nome = BASELINE if filtro is None else filtro
        return scheda_strategia(self.trades(nome), self.pip_size,
                                self.commission or 0.0, **kwargs)

    def trades(self, filtro=None):
        """Trade grezzi (DataFrame nativo di backtesting.py) di un filtro (o della baseline)."""
        if filtro is None:
            filtro = BASELINE
        return self._trades_per_filtro[filtro]
