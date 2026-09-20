"""
engine/due_meta.py — verifica sulle due meta' (Difesa C, Passo 5).

Modulo ADDITIVO: importa `filter_search_bt` e `splitting` in sola
lettura, non li modifica.

COSA VERIFICA
-------------
Non "il sistema e' profittevole in entrambe le meta'" (lo confonderebbe
una baseline gia' positiva da sola per conto suo — vedi V3,
`due_meta_controllato`, dove `coerente = (sharpe_1>0) & (sharpe_2>0)`
guarda lo sharpe assoluto). Qui si verifica se il GUADAGNO di un
filtro/coppia SOPRA la baseline dello stesso periodo (Difesa A del Passo
5) regge sia sulla prima sia sulla seconda meta' dell'In-Sample congelato.

SU QUALE GRANDEZZA — IL CAMBIO DEL 20/9/2026
----------------------------------------------
Il verdetto guardava `guadagno_sharpe`. Ora guarda `guadagno_pips`, cioe'
la differenza fra i pips netti medi dei trade TENUTI e di quelli SCARTATI
dal filtro (engine/giudizio.py). Non e' una rifinitura: cambia i verdetti
gia' dati.

Misurato su EURUSD M15, F14_LOW_DRIFT_REGIME nella seconda meta':

    guadagno_sharpe  +0.011   -> positivo, quindi "regge"
    guadagno_pips    -0.419   -> NEGATIVO: in quella meta' il filtro
                                 PEGGIORAVA il sistema

Lo Sharpe di equity lo nascondeva, perche' e' una metrica di calendario e
non di trade (vedi engine/giudizio.py). Con la grandezza giusta la regola
"positivo in entrambe le meta'" — che era gia' quella di prima — boccia
F14 da sola: non serviva una soglia nuova, serviva il metro giusto.

`guadagno_sharpe` resta in tabella come riferimento, non decide piu'.

LA REGOLA (opzione A, decisa il 20/9/2026)
--------------------------------------------
Due condizioni, su due campioni diversi e per due ragioni diverse:

  1. STABILITA' — `guadagno_pips` positivo in ENTRAMBE le meta'. E' la
     domanda propria di questo modulo: il vantaggio c'e' da tutte e due
     le parti del periodo, o e' concentrato in una sola?

  2. SIGNIFICATIVITA' — `t_guadagno` sopra `soglia_rumore` sull'INTERO
     In-Sample (letti entrambi da `fs`, non ricalcolati qui).

Perche' la significativita' si giudica sull'intero e non sulle meta': con
~250 trade per meta' il rumore campionario da solo produce oscillazioni
enormi. Misurato sugli stessi dati, VWAP_SESSION_CLOSE va da +0.682 a
+3.912 pips fra le due meta' — quasi sei volte — con t di 0.39 e 2.16,
cioe' due numeri che non dicono niente. Le meta' servono a scoprire un
CAMBIO DI SEGNO o un vantaggio tutto da una parte; per misurare con
precisione serve il campione intero.

Per la stessa ragione NON c'e' una terza soglia sul rapporto fra le due
meta': sarebbe un grado di liberta' in piu' tarato su un numero senza
ancora, e le meta' non hanno la precisione per sostenerlo.

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


def _verdetto(riga, t_intero=None, soglia=None):
    """
    Opzione A (vedi il docstring del modulo): stabilita' sulle due meta'
    con `guadagno_pips`, significativita' sull'intero In-Sample con
    `t_guadagno` contro `soglia_rumore`.

    Ritorna (verdetto, motivo). `motivo` nomina la PRIMA condizione
    fallita — l'informazione utile e' dove guardare.
    """
    if riga["filtro"] == BASELINE:
        return "baseline", ""

    g1 = riga["guadagno_pips_metà1"]
    g2 = riga["guadagno_pips_metà2"]

    if not (pd.notna(g1) and pd.notna(g2)):
        return "non regge", "guadagno non calcolabile in una delle due metà"
    if g1 <= 0 or g2 <= 0:
        debole = "metà1" if g1 <= g2 else "metà2"
        return "non regge", f"guadagno {min(g1, g2):+.3f} pips <= 0 in {debole}"

    # significativita' sull'INTERO In-Sample, letta da fs
    if t_intero is not None and soglia is not None and pd.notna(t_intero):
        if abs(t_intero) < soglia:
            return "non regge", f"|t| {abs(t_intero):.2f} < soglia rumore {soglia:.2f} (In-Sample intero)"
        if t_intero < 0:
            return "non regge", f"t {t_intero:.2f} oltre soglia ma NEGATIVO"

    if bool(riga["pochi_trade_metà1"]) or bool(riga["pochi_trade_metà2"]):
        return "giudizio sospeso", "poche osservazioni in almeno una metà"
    return "regge", ""


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

    cols = ["filtro", "filtro_long", "filtro_short", "trades", "pnl_pct", "sharpe",
            "guadagno_pips", "t_guadagno", "guadagno_sharpe", "guadagno_avg_trade",
            "pochi_trade"]
    r1 = fs1.risultati[cols].copy()
    r2 = fs2.risultati[cols].copy()
    if not includi_baseline:
        r1 = r1[r1["filtro"] != BASELINE]
        r2 = r2[r2["filtro"] != BASELINE]

    m = r1.merge(r2, on=["filtro", "filtro_long", "filtro_short"],
                 suffixes=("_metà1", "_metà2"))

    # t_guadagno e soglia dell'INTERO In-Sample, letti da fs: non si
    # ricalcolano qui, cosi' il numero e' lo stesso che fs.top() mostra.
    t_intero = (fs.risultati.set_index("filtro")["t_guadagno"].to_dict()
                if "t_guadagno" in fs.risultati.columns else {})
    soglia = getattr(fs, "soglia_rumore", None)

    esiti = m.apply(lambda r: _verdetto(r, t_intero.get(r["filtro"]), soglia),
                    axis=1)
    m["verdetto"] = [e[0] for e in esiti]
    m["motivo"] = [e[1] for e in esiti]
    m["t_guadagno_intero"] = m["filtro"].map(t_intero)
    m = m.sort_values("guadagno_pips_metà2", ascending=False,
                      na_position="last").reset_index(drop=True)

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
                print(f"  pnl_pct           metà1={riga['pnl_pct_metà1']:.3f}"
                      f"   metà2={riga['pnl_pct_metà2']:.3f}")
                if riga["filtro"] != BASELINE:
                    print(f"  guadagno_pips     metà1={riga['guadagno_pips_metà1']:+.3f}"
                          f"   metà2={riga['guadagno_pips_metà2']:+.3f}   <-- decide")
                    print(f"  guadagno_sharpe   metà1={riga['guadagno_sharpe_metà1']:+.3f}"
                          f"   metà2={riga['guadagno_sharpe_metà2']:+.3f}   (riferimento)")
                    if pd.notna(riga.get("t_guadagno_intero")):
                        s = f" / soglia {soglia:.2f}" if soglia else ""
                        print(f"  t In-Sample intero {riga['t_guadagno_intero']:+.2f}{s}")
                pochi_flag = "   <-- pochi_trade" if (riga["pochi_trade_metà1"] or riga["pochi_trade_metà2"]) else ""
                print(f"  trade             metà1={riga['trades_metà1']}"
                      f"   metà2={riga['trades_metà2']}{pochi_flag}")
                if riga.get("motivo"):
                    print(f"  motivo            {riga['motivo']}")
                print(bordo)

    # guadagno_pips per primo: e' la colonna che decide. guadagno_sharpe
    # resta piu' a destra come riferimento.
    colonne_finali = ["filtro", "filtro_long", "filtro_short",
                       "trades_metà1", "trades_metà2",
                       "guadagno_pips_metà1", "guadagno_pips_metà2",
                       "t_guadagno_metà1", "t_guadagno_metà2",
                       "t_guadagno_intero",
                       "pnl_pct_metà1", "pnl_pct_metà2",
                       "sharpe_metà1", "sharpe_metà2",
                       "guadagno_sharpe_metà1", "guadagno_sharpe_metà2",
                       "guadagno_avg_trade_metà1", "guadagno_avg_trade_metà2",
                       "pochi_trade_metà1", "pochi_trade_metà2",
                       "verdetto", "motivo"]
    tabella = m[colonne_finali].copy()
    colonne_float = ["guadagno_pips_metà1", "guadagno_pips_metà2",
                      "t_guadagno_metà1", "t_guadagno_metà2", "t_guadagno_intero",
                      "pnl_pct_metà1", "pnl_pct_metà2",
                      "sharpe_metà1", "sharpe_metà2",
                      "guadagno_sharpe_metà1", "guadagno_sharpe_metà2",
                      "guadagno_avg_trade_metà1", "guadagno_avg_trade_metà2"]
    tabella[colonne_float] = tabella[colonne_float].round(3)

    return DueMeta(tabella=tabella, metà1=fs1, metà2=fs2)
