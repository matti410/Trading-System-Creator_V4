"""
Filtri di regime basati su VWAP intraday e regressione lineare cumulata,
adattati dal file `vwap_indicator_features.py` fornito dall'utente.

NON fanno parte del paper "101 Formulaic Alphas" — sono un'estensione
proposta separatamente, tenuta in un file a parte perché richiede
`engine.vwap_ops` e ricalcola una regressione per sessione ad ogni
chiamata: separarla rende evidente il costo. I filtri derivati dal paper
sono invece in `filter_conditions.py`.

Sulla `direction`: vedi la nota in cima a `filter_conditions.py`. Descrive
lo stato di mercato individuato dal filtro, non il verso dell'entry con
cui va accoppiato — su ingressi di inversione l'accoppiamento utile si
rovescia.

Richiedono le colonne `vwap` (engine.vwap_ops.vwap_anchored_daily) e
il fit di regressione per sessione (engine.vwap_ops.regression_trend_fit),
calcolate qui internamente — non serve pre-calcolarle nel notebook, ma se
usate in molte combinazioni conviene valutare la performance (regressione
O(n) per sessione, ricalcolata ad ogni chiamata del filtro).

Adattato allo stile V4 (17-18/9): niente decoratori applicati alla
definizione — la registrazione avviene tramite `registra_filtri_vwap()`,
chiamata a mano nel notebook. Stesso pattern di `registra_filtri()` in
`filter_conditions.py`, tenuta come bridge separato perché il file stesso
resta separato (vedi sopra).

Sulle coppie (`pair`, aggiunte 18/9/2026): stessa logica descritta in
`filter_conditions.py` — VWAP_PRICE_ABOVE/BELOW_FAIR_VALUE e
VWAP_PREVIOUS_SESSION_CLOSED_ABOVE/BELOW sono ciascuna una singola idea a
due facce, raccolte in un'unica riga dalla grid search. Le regole per
aggiungere filtri VWAP nuovi sono le stesse quattro di `filter_conditions.py`
— non ripetute qui per non tenere due copie della stessa regola.
"""
import pandas as pd
from engine.vwap_ops import regression_trend_fit, vwap_gap


def vwap_price_above_fair_value(df: pd.DataFrame) -> pd.Series:
    """
    True quando il fair value stimato per regressione intraday (per
    sessione) è sopra il vwap della sessione — equivalente a
    `feat_vwap_price_position` nel file originale.
    """
    fitted = regression_trend_fit(df["Close"])
    return fitted > df["vwap"]


def vwap_gap_widening(df: pd.DataFrame) -> pd.Series:
    """
    True quando lo scarto tra fair value (regressione) e vwap si sta
    ampliando rispetto alla barra precedente — equivalente a
    `feat_vwap_gap_trend` nel file originale.
    """
    gap = vwap_gap(df, df["vwap"])
    return gap > gap.shift(1)


def vwap_previous_session_closed_above(df: pd.DataFrame) -> pd.Series:
    """
    True quando l'ultima barra della sessione precedente si è chiusa con
    il fair value sopra il vwap — equivalente a `feat_vwap_last_close`
    nel file originale (regime "ereditato" dalla sessione precedente,
    propagato in avanti fino al prossimo aggiornamento).
    """
    gap = vwap_gap(df, df["vwap"])
    date_groups = df.index.date
    last_gap_per_session = gap.groupby(date_groups).last()
    position = (last_gap_per_session > 0)

    position_shifted = position.shift(1).ffill()
    return pd.Series(date_groups, index=df.index).map(position_shifted).fillna(False).astype(bool)


def vwap_price_below_fair_value(df: pd.DataFrame) -> pd.Series:
    """Speculare di VWAP_PRICE_ABOVE_FAIR_VALUE."""
    fitted = regression_trend_fit(df["Close"])
    return fitted < df["vwap"]


def vwap_previous_session_closed_below(df: pd.DataFrame) -> pd.Series:
    """
    Speculare di VWAP_PREVIOUS_SESSION_CLOSED_ABOVE.

    Attenzione al modo in cui è scritto: la condizione è `< 0` sul gap,
    NON la negazione del risultato finale. Il gemello chiude con
    .fillna(False), quindi le sessioni senza dato valgono False lì;
    negando il risultato quelle stesse sessioni diventerebbero True e il
    filtro "sotto" sarebbe vero proprio dove non si sa niente. Le
    sessioni con gap esattamente 0 restano fuori da entrambi, ed è
    corretto: non sono né sopra né sotto.
    """
    gap = vwap_gap(df, df["vwap"])
    date_groups = df.index.date
    last_gap_per_session = gap.groupby(date_groups).last()
    position = (last_gap_per_session < 0)

    position_shifted = position.shift(1).ffill()
    return pd.Series(date_groups, index=df.index).map(position_shifted).fillna(False).astype(bool)


# nome -> (funzione, direction, pair)
FILTRI_VWAP = {
    "VWAP_PRICE_ABOVE_FAIR_VALUE":         (vwap_price_above_fair_value, 1, "VWAP_FAIR_VALUE"),
    "VWAP_GAP_WIDENING":                   (vwap_gap_widening, 0, None),
    "VWAP_PREVIOUS_SESSION_CLOSED_ABOVE":  (vwap_previous_session_closed_above, 1, "VWAP_SESSION_CLOSE"),
    "VWAP_PRICE_BELOW_FAIR_VALUE":         (vwap_price_below_fair_value, -1, "VWAP_FAIR_VALUE"),
    "VWAP_PREVIOUS_SESSION_CLOSED_BELOW":  (vwap_previous_session_closed_below, -1, "VWAP_SESSION_CLOSE"),
}


def registra_filtri_vwap():
    """Vedi registra_filtri() in filter_conditions.py per il comportamento."""
    from engine.registry import register_filter, list_filters

    gia_presenti = set(list_filters())
    nuovi = 0
    for nome, (funzione, direction, pair) in FILTRI_VWAP.items():
        if nome in gia_presenti:
            print(f"[registra_filtri_vwap] '{nome}' gia' registrato, salto.")
            continue
        register_filter(nome, direction=direction, pair=pair)(funzione)
        nuovi += 1
    print(f"[registra_filtri_vwap] {nuovi} filtri registrati "
          f"({len(FILTRI_VWAP) - nuovi} gia' presenti).")
