"""
engine/due_meta.py — verifica sulle due meta' (Difesa C, Passo 5).

Modulo ADDITIVO: importa `filter_search_bt` e `splitting` in sola
lettura, non li modifica.

COSA VERIFICA
-------------
Non "il sistema e' profittevole in entrambe le meta'" (lo confonderebbe
una baseline gia' positiva da sola per conto suo — vedi V3,
`due_meta_controllato`, dove `coerente = (sharpe_1>0) & (sharpe_2>0)`
guarda lo sharpe assoluto). Qui si verifica se il `guadagno_sharpe` —
quanto un filtro/coppia aggiunge SOPRA la baseline dello stesso periodo,
Difesa A del Passo 5 — regge sia sulla prima sia sulla seconda meta'
dell'In-Sample congelato.

COME
----
Si taglia l'In-Sample in due meta' croniche con `split_is_oos(df_is, 0.5)`
(riusato cosi' com'e', nessuna nuova logica di split), e si rifa' girare
`run_filter_search_bt` due volte, una per meta', con ESATTAMENTE lo
stesso setup congelato gia' usato per costruire `fs`: entry_long,
entry_short, exit_rule_pair, n_barre, min_trades vengono letti da `fs`,
mai ripassati a mano — non e' possibile testare per errore un setup
diverso da quello che `fs` ha gia' prodotto.

Gli altri parametri (soglie adattive, costi, nomi di colonna) NON sono
salvati su `fs`: vanno ripassati identici a quelli della cella che ha
costruito `fs`.

Effetto collaterale noto e accettato: le soglie adattive (dentro
`exit_search_bt.soglie_adattive`) hanno un warmup di `finestra` barre;
tagliando in due, la seconda meta' lo riparte da zero e perde le sue
prime `finestra` barre di segnali, oltre a quelle gia' perse all'inizio
della prima meta'. Su un In-Sample di anni di M15 e' una frazione
trascurabile — non e' un difetto di questo modulo, e' lo stesso
comportamento gia' accettato per la costruzione di `fs`.

due_meta NON ricerca l'uscita ne' i filtri: riceve solo le `etichette'
gia' emerse promettenti da fs.top(), tradotte nei filtri registrati che
le compongono.

None IN etichette — LA RIGA BASELINE COME RIFERIMENTO
--------------------------------------------------------
`None` in `etichette` e' un valore valido a se', non un filtro: significa
"includi anche la riga baseline" — stessa convenzione gia' in uso nel
notebook per `exit_rule_pairs=[..., None]` / `entry_cols_long=[...,
None]`. Non contribuisce alla lista dei filtri passata a
run_filter_search_bt (la baseline e' gia' calcolata automaticamente in
ogni run): serve solo a decidere se tenerla nella tabella finale.

Per la baseline (e per ogni riga) la tabella riporta anche `sharpe_metà1`
/ `sharpe_metà2` (assoluti, non il guadagno sopra baseline, che per la
baseline stessa sarebbe banalmente 0). Motivo: un guadagno_sharpe
positivo in entrambe le meta' NON garantisce che lo sharpe assoluto sia
positivo in entrambe — garantisce solo che batte la baseline in
entrambe, anche se entrambe le meta' sono in perdita. Quando lo sharpe
assoluto di una riga cambia segno tra le due meta', verbose=True lo
segnala esplicitamente, indipendentemente dal verdetto.
"""
from __future__ import annotations

import pandas as pd

from .splitting import split_is_oos
from .filter_search_bt import run_filter_search_bt, BASELINE

__all__ = ["due_meta", "DueMeta"]

_VUOTO = "—"  # stesso placeholder di filter_search_bt.py per filtro_long/filtro_short assenti


def _filtri_da_etichette(fs, etichette):
    """
    Traduce ogni etichetta (una riga di fs.risultati, cosi' come appare
    in fs.top()['filtro']) nei nomi di filtro registrati che la
    compongono (filtro_long / filtro_short, esclusi i placeholder).
    Unisce tutte le etichette richieste in un'unica lista, cosi'
    run_filter_search_bt costruisce UN SOLO Backtest() per meta', non uno
    per etichetta. `None` (richiesta della riga baseline) viene ignorato
    qui: non e' un filtro, non contribuisce alla lista.

    Solleva ValueError, con l'elenco delle etichette disponibili, se una
    richiesta (diversa da None) non esiste in fs.risultati.
    """
    disponibili = sorted(set(fs.risultati["filtro"]) - {BASELINE})
    richieste = [e for e in etichette if e is not None]
    mancanti = [e for e in richieste if e not in disponibili]
    if mancanti:
        raise ValueError(
            f"Etichetta/e non trovata/e in fs.risultati: {mancanti}. "
            f"Disponibili: {disponibili}."
        )

    filtri = []
    for e in richieste:
        riga = fs.risultati.loc[fs.risultati["filtro"] == e].iloc[0]
        for nome in (riga["filtro_long"], riga["filtro_short"]):
            if nome != _VUOTO and nome not in filtri:
                filtri.append(nome)
    return filtri


def _verdetto(riga):
    if riga["filtro"] == BASELINE:
        return "baseline"
    g1 = riga["guadagno_sharpe_metà1"]
    g2 = riga["guadagno_sharpe_metà2"]
    pochi = bool(riga["pochi_trade_metà1"]) or bool(riga["pochi_trade_metà2"])
    if g1 > 0 and g2 > 0:
        return "giudizio sospeso" if pochi else "regge"
    return "non regge"


class DueMeta:
    """Risultato di due_meta(). Vedi .tabella, .metà1, .metà2."""

    def __init__(self, tabella, metà1, metà2):
        self.tabella = tabella
        self.metà1 = metà1
        self.metà2 = metà2

    def __repr__(self):
        return f"<DueMeta: {len(self.tabella)} etichetta/e verificata/e>"


def due_meta(df_is, fs, etichette,
             perc_sl=0.0, perc_tp=0.0, finestra=500, lag=1,
             spread=0.0, commission=0.00007, cash=10_000.0, margin=1.0,
             close_col="Close", open_col="Open", high_col="High", low_col="Low",
             verbose=True):
    """
    Verifica sulle due meta' (Difesa C, Passo 5) per le `etichette`
    indicate.

    df_is
        Lo stesso In-Sample gia' usato per costruire `fs`. Mai l'OOS.
    fs
        Il FilterSearchBT gia' calcolato (Sessione 3). entry_long,
        entry_short, exit_rule_pair, n_barre, min_trades vengono letti da
        qui, non ripassati.
    etichette
        Lista di nomi cosi' come appaiono in fs.top()['filtro'] (un
        filtro singolo o una coppia). Puo' contenere anche `None`: include
        la riga baseline nella tabella, come riferimento (vedi il
        docstring del modulo).
    perc_sl, perc_tp, finestra, lag, spread, commission, cash, margin,
    close_col, open_col, high_col, low_col
        Stessi valori usati per costruire `fs` — vanno ripassati identici
        a quelli della cella di Sessione 3 (non sono salvati su fs).
    verbose
        Stampa il riepilogo dello split e un blocco esplicito per ogni
        etichetta che non regge o resta sospesa.

    Ritorna un oggetto DueMeta: .tabella (una riga per etichetta),
    .metà1 e .metà2 (i due FilterSearchBT interi, per ispezionare i trade
    di una singola meta' con .trades(...) se serve).
    """
    filtri = _filtri_da_etichette(fs, etichette)
    includi_baseline = None in etichette

    metà1_df, metà2_df = split_is_oos(df_is, is_ratio=0.5)

    if verbose:
        print(f"metà 1: {len(metà1_df)} barre, dal {metà1_df.index.min()} al {metà1_df.index.max()}")
        print(f"metà 2: {len(metà2_df)} barre, dal {metà2_df.index.min()} al {metà2_df.index.max()}")

    kwargs = dict(entry_long=fs.entry_long, entry_short=fs.entry_short,
                  exit_rule_pair=fs.exit_rule_pair, n_barre=fs.n_barre,
                  filtri=filtri, perc_sl=perc_sl, perc_tp=perc_tp,
                  finestra=finestra, lag=lag, spread=spread,
                  commission=commission, cash=cash, margin=margin,
                  min_trades=fs.min_trades, close_col=close_col,
                  open_col=open_col, high_col=high_col, low_col=low_col,
                  verbose=False)

    fs1 = run_filter_search_bt(metà1_df, **kwargs)
    fs2 = run_filter_search_bt(metà2_df, **kwargs)

    cols = ["filtro", "filtro_long", "filtro_short", "trades", "sharpe",
            "guadagno_sharpe", "guadagno_avg_trade", "pochi_trade"]
    r1 = fs1.risultati[cols].copy()
    r2 = fs2.risultati[cols].copy()
    if not includi_baseline:
        r1 = r1[r1["filtro"] != BASELINE]
        r2 = r2[r2["filtro"] != BASELINE]

    m = r1.merge(r2, on=["filtro", "filtro_long", "filtro_short"],
                 suffixes=("_metà1", "_metà2"))
    m["verdetto"] = m.apply(_verdetto, axis=1)
    m = m.sort_values("guadagno_sharpe_metà2", ascending=False).reset_index(drop=True)

    if verbose:
        for _, riga in m.iterrows():
            cambia_segno = (riga["sharpe_metà1"] > 0) != (riga["sharpe_metà2"] > 0)
            # si stampa un blocco per ogni riga che non regge / resta
            # sospesa, e ANCHE per una riga che regge (o e' la baseline)
            # se lo sharpe assoluto cambia segno tra le due meta': il
            # guadagno_sharpe positivo non lo garantisce (vedi docstring).
            if riga["verdetto"] not in ("regge", "baseline") or cambia_segno:
                bordo = "=" * 68
                print(bordo)
                etichetta_stampa = "BASELINE" if riga["filtro"] == BASELINE else riga["verdetto"].upper()
                print(f"  {etichetta_stampa}: {riga['filtro']}")
                print(f"  sharpe assoluto   metà1={riga['sharpe_metà1']:.3f}"
                      f"   metà2={riga['sharpe_metà2']:.3f}"
                      + ("   <-- cambia segno tra le due metà" if cambia_segno else ""))
                if riga["filtro"] != BASELINE:
                    print(f"  guadagno_sharpe   metà1={riga['guadagno_sharpe_metà1']:.3f}"
                          f"   metà2={riga['guadagno_sharpe_metà2']:.3f}")
                pochi_flag = "   <-- pochi_trade" if (riga["pochi_trade_metà1"] or riga["pochi_trade_metà2"]) else ""
                print(f"  trade             metà1={riga['trades_metà1']}"
                      f"   metà2={riga['trades_metà2']}{pochi_flag}")
                print(bordo)

    colonne_finali = ["filtro", "filtro_long", "filtro_short",
                       "trades_metà1", "trades_metà2",
                       "sharpe_metà1", "sharpe_metà2",
                       "guadagno_sharpe_metà1", "guadagno_sharpe_metà2",
                       "guadagno_avg_trade_metà1", "guadagno_avg_trade_metà2",
                       "pochi_trade_metà1", "pochi_trade_metà2", "verdetto"]
    tabella = m[colonne_finali].copy()
    colonne_float = ["sharpe_metà1", "sharpe_metà2",
                      "guadagno_sharpe_metà1", "guadagno_sharpe_metà2",
                      "guadagno_avg_trade_metà1", "guadagno_avg_trade_metà2"]
    tabella[colonne_float] = tabella[colonne_float].round(3)

    return DueMeta(tabella=tabella, metà1=fs1, metà2=fs2)
