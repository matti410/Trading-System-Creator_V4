"""
Confidenza dei segnali — statistica condizionata rolling.

DOVE SI COLLOCA
---------------
Passo 5 della roadmap, prima dell'Out-of-Sample. La confidenza di un segnale
e' l'esito medio dei trade GIA' CONCLUSI che si sono trovati nello stesso
contesto di mercato. Una soglia sulla confidenza diventa un filtro normale e
passa da `run_filter_search_bt`, con tutte le difese che il passo 5 ha gia'
(tenuti vs scartati, soglia di rumore, `due_meta`).

IL CONTESTO: UNA GRIGLIA 2x2
----------------------------
Due assi, ciascuno diviso in due alla mediana rolling (calcolata solo sul
passato, barra corrente compresa):

    volatilita'   std dei rendimenti logaritmici su `finestra_vol` barre,
                  classe da `build_labels` (volatility_features_engineering.py
                  di Mattia, chiamata con q_low = q_high = 0.5)
    trend         `aura_gap` (regressione intraday - VWAP intraday),
                  moltiplicato per la direzione del trade: alto = trend a
                  favore del trade, basso = contro

    cella = 2 x volatilita' + trend

        0  VOL_BASSA·TREND_CONTRO      1  VOL_BASSA·TREND_FAVORE
        2  VOL_ALTA·TREND_CONTRO       3  VOL_ALTA·TREND_FAVORE

La giornata di VWAP e regressione e' la giornata FX (`giorno_fx`, dal
rollover delle 17:00 di New York), non la mezzanotte dell'indice. Per questo
il gap e' ricalcolato qui e non preso da `engine/vwap_ops.py`, che raggruppa
per `df.index.date`: le formule sono le stesse, cambia solo dove si taglia
la giornata.

LA CAUSALITA'
-------------
- La cella di una barra usa solo dati fino alla chiusura di quella barra.
- Un trade entra nella storia della confidenza solo dalla barra in cui e'
  USCITO (ExitBar), non da quella in cui e' entrato.
- Il segnale scatta alla chiusura della barra t, l'ingresso e' all'apertura
  di t+1: la confidenza letta alla barra t usa i trade con ExitBar <= t.
- Un unico calcolo continuo su tutta la serie, senza reset al confine
  In-Sample / Out-of-Sample: dal vivo si avrebbe esattamente quella storia.

LA STORIA VIENE DAL SETUP SENZA FILTRO
-------------------------------------
Gli esiti che alimentano la confidenza sono quelli della BASELINE (il setup
congelato, nessun filtro), fatta girare su tutta la serie. Dal vivo si
possono calcolare anche per i segnali che non si tradano: basta simulare il
setup base accanto a quello reale.

IL FILTRO SCELTO VA CONGELATO PRIMA (25/9)
------------------------------------------
Se al passo 5 si e' scelto un filtro (es. F8_UPTREND_CONTEXT), il setup e'
«entry + filtro»: `congela_filtro(fs, filtro_scelto)` lo mette dentro le
entry, e da li' in poi storia, test e OOS usano quel setup.

Modulo ADDITIVO: legge registry, livelli e metriche, non modifica niente.
Registra solo nomi nuovi (entry derivate, filtri CONF_...).
Richiede `engine/volatility_features_engineering.py` (il file di Mattia,
invariato).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .livelli import giorno_fx
from .metriche import pips_per_trade
from .registry import (get_entry, get_entry_direction, get_filter, list_entries,
                       list_filters, register_entry, register_filter)
from .volatility_features_engineering import (build_labels,
                                              feat_historical_volatility)

ETICHETTE_CELLA = {
    0: "VOL_BASSA·TREND_CONTRO",
    1: "VOL_BASSA·TREND_FAVORE",
    2: "VOL_ALTA·TREND_CONTRO",
    3: "VOL_ALTA·TREND_FAVORE",
}

_FINESTRE_VOL = (5, 20, 50, 200)   # quelle che feat_historical_volatility produce
_METRICHE = ("pips_medi", "win_rate")


# ========================================================================
# 0 · Il filtro scelto, congelato dentro l'entry
# ========================================================================

_VUOTO = "—"   # stesso segnaposto di filter_search_bt.py per "nessun filtro su questo lato"


def congela_filtro(fs, filtro_scelto):
    """
    Congela il filtro scelto al passo 5 dentro le entry, cosi' che il setup
    diventi «entry + filtro» e la confidenza si costruisca e si provi SOPRA.

    `run_filter_search_bt` prova un'idea per riga e la sua baseline e' sempre
    senza filtri: non ha un posto per un filtro fisso. Invece di modificarlo,
    si registra una entry derivata, vera solo dove sono veri entry e filtro.

    fs              il FilterSearchBT della ricerca dei filtri
    filtro_scelto   l'etichetta della riga scelta, come appare in
                    fs.risultati['filtro'] (un filtro singolo o una coppia).
                    None = nessun filtro: restituisce le entry di fs.

    Il filtro di ciascun lato si legge dalla riga (colonne filtro_long /
    filtro_short): si congela esattamente quello che la tabella ha provato.

    Ritorna (entry_long, entry_short): i nomi da passare a
    run_filter_search_bt, None dove il lato non e' attivo. Il nome di una
    entry derivata e' "ENTRY+FILTRO", es. E22_ASIAN_RANGE_BREAKOUT+F8_UPTREND_CONTEXT.
    """
    if filtro_scelto is None:
        return fs.entry_long, fs.entry_short

    r = fs.risultati
    if filtro_scelto not in set(r["filtro"]):
        disponibili = sorted(x for x in r["filtro"] if not str(x).startswith("—"))
        raise ValueError(
            f"'{filtro_scelto}' non e' una riga di fs.risultati. Etichette "
            f"disponibili: {disponibili}"
        )
    riga = r.loc[r["filtro"] == filtro_scelto].iloc[0]

    registrate = set(list_entries())
    nomi = []
    for entry, filtro in ((fs.entry_long, riga["filtro_long"]),
                          (fs.entry_short, riga["filtro_short"])):
        if entry is None:
            nomi.append(None)
            continue
        if filtro is None or filtro == _VUOTO:
            nomi.append(entry)
            continue
        nome = f"{entry}+{filtro}"
        if nome not in registrate:
            def derivata(d, _e=entry, _f=filtro):
                # stesse conversioni di filter_search_bt: .astype(bool) su entrambe
                return (get_entry(_e)(d).astype(bool)
                        & pd.Series(get_filter(_f)(d).astype(bool).to_numpy(), index=d.index))
            register_entry(nome, get_entry_direction(entry))(derivata)
        nomi.append(nome)
    return nomi[0], nomi[1]


# ========================================================================
# 1 · Il contesto
# ========================================================================

def asse_volatilita(df: pd.DataFrame, finestra_vol: int = 20,
                    finestra: int = 500) -> pd.Series:
    """
    Classe di volatilita' di ogni barra: 0 = sotto (o uguale) la mediana
    rolling, 1 = sopra. NaN finche' la finestra non e' piena.

    finestra_vol   barre della std dei rendimenti: 5, 20, 50 o 200
    finestra       barre su cui si calcola la mediana (500 ~ 5 giorni in M15)
    """
    if finestra_vol not in _FINESTRE_VOL:
        raise ValueError(f"finestra_vol deve essere una di {_FINESTRE_VOL}.")
    lavoro = feat_historical_volatility(df[["Close"]].copy())
    lavoro = build_labels(lavoro, vol_col=f"feat_volatility_{finestra_vol}",
                          window=int(finestra), q_low=0.5, q_high=0.5)
    # con q_low = q_high la classe di mezzo resta vuota: escono 0 e 2
    return lavoro["vol_regime"].map({0.0: 0.0, 2.0: 1.0}).rename("vol")


def gap_trend(df: pd.DataFrame) -> pd.Series:
    """
    `aura_gap` = regressione lineare cumulata del Close - VWAP cumulato, tutti
    e due ripartiti da zero a ogni giornata FX.

    Stesse formule di `vwap_indicator_features.py` (VWAP col prezzo tipico,
    regressione incrementale a formule chiuse), scritte in forma vettoriale.
    NaN dove il volume cumulato della giornata e' ancora zero.
    """
    giorno = giorno_fx(df)
    close = df["Close"].astype(float)

    tipico = (df["High"] + df["Low"] + df["Close"]) / 3
    vol = df["Volume"].astype(float)
    cum_tpv = (tipico * vol).groupby(giorno).cumsum()
    cum_vol = vol.groupby(giorno).cumsum()
    vwap = cum_tpv / cum_vol.where(cum_vol > 0)

    i = close.groupby(giorno).cumcount().astype(float)
    somma_y = close.groupby(giorno).cumsum()
    somma_xy = (i * close).groupby(giorno).cumsum()
    n = i + 1
    somma_x = i * (i + 1) / 2
    somma_x2 = i * (i + 1) * (2 * i + 1) / 6
    denom = n * somma_x2 - somma_x ** 2
    pendenza = (n * somma_xy - somma_x * somma_y) / denom.where(denom != 0)
    intercetta = (somma_y - pendenza * somma_x) / n
    fitted = (intercetta + pendenza * i).where(i > 0, close)

    return (fitted - vwap).rename("aura_gap")


def cella_contesto(df: pd.DataFrame, direzione: int, finestra: int = 500,
                   finestra_vol: int = 20) -> pd.Series:
    """
    Cella 0-3 della griglia per il lato indicato (+1 long, -1 short).
    NaN finche' una delle due mediane rolling non e' calcolabile.

    Il trend e' allineato alla direzione: gap x direzione. Sopra la mediana
    rolling = 1 (a favore), sotto o uguale = 0 (contro). Stessa regola del
    lato volatilita'.
    """
    if direzione not in (1, -1):
        raise ValueError("direzione deve essere 1 (long) o -1 (short).")
    vol = asse_volatilita(df, finestra_vol=finestra_vol, finestra=finestra)
    allineato = gap_trend(df) * direzione
    mediana = allineato.rolling(int(finestra), min_periods=int(finestra)).median()
    trend = (allineato > mediana).astype(float).where(mediana.notna() & allineato.notna())
    return (2 * vol + trend).rename("cella")


# ========================================================================
# 2 · Gli esiti dei trade
# ========================================================================

def esiti_trade(trades: pd.DataFrame, df: pd.DataFrame, pip_size: float,
                commission: float = 0.0) -> pd.DataFrame:
    """
    Una riga per trade, con le posizioni riferite all'indice di `df`.

    trades      `stats["_trades"]` di backtesting.py, per esempio
                `fs_base.trades()` della baseline girata su tutta la serie
    df          il DataFrame su cui si calcolera' la confidenza
    pip_size, commission
                gli stessi del backtest (fs.pip_size, costi["commission"])

    Colonne: barra_segnale (= barra d'ingresso - 1), barra_uscita, lato
    (+1 / -1), pips_netti, vinto (1 se pips_netti > 0).
    """
    if len(trades) == 0:
        return pd.DataFrame(columns=["barra_segnale", "barra_uscita", "lato",
                                     "pips_netti", "vinto"])
    indice = pd.DatetimeIndex(df.index)
    pos_in = indice.get_indexer(pd.DatetimeIndex(trades["EntryTime"]))
    pos_out = indice.get_indexer(pd.DatetimeIndex(trades["ExitTime"]))
    if (pos_in < 0).any() or (pos_out < 0).any():
        raise ValueError(
            "Alcuni trade hanno orari di ingresso o uscita che non esistono "
            "nell'indice di df: i trade vanno presi da un backtest su questo "
            "stesso df (o su un suo tratto)."
        )
    if (pos_in < 1).any():
        raise ValueError("Un trade entra sulla prima barra di df: manca la barra del segnale.")
    _, netti = pips_per_trade(trades, pip_size, commission)
    out = pd.DataFrame({
        "barra_segnale": pos_in - 1,
        "barra_uscita": pos_out,
        "lato": np.where(trades["Size"].to_numpy() > 0, 1, -1),
        "pips_netti": netti.to_numpy(dtype=float),
    })
    out["vinto"] = (out["pips_netti"] > 0).astype(int)
    return out.reset_index(drop=True)


# ========================================================================
# 3 · La confidenza
# ========================================================================

def confidenza_rolling(df: pd.DataFrame, esiti: pd.DataFrame, direzione: int,
                       finestra_trade: int = 500, min_obs: int = 30,
                       finestra: int = 500, finestra_vol: int = 20) -> pd.DataFrame:
    """
    La confidenza di ogni barra per un lato, come se su quella barra
    scattasse un segnale.

    Storia: gli ultimi `finestra_trade` trade di quel lato gia' usciti
    (barra_uscita <= barra corrente); se ce ne sono meno, tutti quelli usciti.
    Fra questi si tengono quelli la cui barra di segnale cadeva nella STESSA
    cella della barra corrente.

    Colonne (indice = df.index):
        cella       0-3, NaN nel riscaldamento
        etichetta   nome della cella
        n_storia    trade della stessa cella nella storia
        win_rate    quota di trade vinti fra quelli
        pips_medi   pips netti medi fra quelli
    win_rate e pips_medi sono NaN se n_storia < min_obs.
    """
    if direzione not in (1, -1):
        raise ValueError("direzione deve essere 1 (long) o -1 (short).")
    cella = cella_contesto(df, direzione, finestra=finestra, finestra_vol=finestra_vol)
    celle = cella.to_numpy()
    n_barre = len(df)

    e = esiti[esiti["lato"] == direzione].copy()
    e["cella"] = celle[e["barra_segnale"].to_numpy().astype(int)] if len(e) else []
    e = e.sort_values("barra_uscita", kind="mergesort").reset_index(drop=True)
    uscita = e["barra_uscita"].to_numpy()

    # k(t) = quanti trade di questo lato sono usciti entro la barra t
    k = np.searchsorted(uscita, np.arange(n_barre), side="right")
    k0 = np.maximum(0, k - int(finestra_trade))

    n_storia = np.zeros(n_barre)
    somma_pips = np.zeros(n_barre)
    somma_vinti = np.zeros(n_barre)
    for c in range(4):
        in_c = (e["cella"].to_numpy() == c)
        cum_n = np.r_[0.0, np.cumsum(in_c)]
        cum_p = np.r_[0.0, np.cumsum(np.where(in_c, e["pips_netti"].to_numpy(), 0.0))]
        cum_v = np.r_[0.0, np.cumsum(np.where(in_c, e["vinto"].to_numpy(), 0))]
        qui = celle == c
        n_storia[qui] = (cum_n[k] - cum_n[k0])[qui]
        somma_pips[qui] = (cum_p[k] - cum_p[k0])[qui]
        somma_vinti[qui] = (cum_v[k] - cum_v[k0])[qui]

    valida = ~np.isnan(celle) & (n_storia >= int(min_obs))
    with np.errstate(invalid="ignore", divide="ignore"):
        pips_medi = np.where(valida, somma_pips / n_storia, np.nan)
        win_rate = np.where(valida, somma_vinti / n_storia, np.nan)

    return pd.DataFrame({
        "cella": cella.to_numpy(),
        "etichetta": pd.Series(cella.to_numpy()).map(ETICHETTE_CELLA).to_numpy(),
        "n_storia": np.where(np.isnan(celle), np.nan, n_storia),
        "win_rate": win_rate,
        "pips_medi": pips_medi,
    }, index=df.index)


# ========================================================================
# 4 · La soglia di confidenza come filtro
# ========================================================================

# nome del filtro -> (Series della metrica, soglia): la funzione registrata
# legge da qui, cosi' rieseguire la cella aggiorna i valori senza
# ri-registrare niente.
_DATI_FILTRI: dict[str, tuple[pd.Series, float]] = {}


def _fmt(soglia: float) -> str:
    return f"{soglia:g}".replace("-", "m")


def _funzione_filtro(nome: str):
    def filtro(d: pd.DataFrame) -> pd.Series:
        valori, soglia = _DATI_FILTRI[nome]
        if not d.index.isin(valori.index).all():
            raise ValueError(
                f"{nome}: il df passato contiene barre per cui la confidenza non "
                "e' stata calcolata. Calcola la confidenza sulla serie completa."
            )
        return (valori.reindex(d.index) > soglia).fillna(False).astype(bool)
    return filtro


def registra_filtro_confidenza(soglie, conf_long: pd.DataFrame | None = None,
                               conf_short: pd.DataFrame | None = None,
                               metrica: str = "pips_medi",
                               prefisso: str = "CONF") -> list[str]:
    """
    Registra una soglia di confidenza come filtro, per ogni soglia in `soglie`.

    Con conf_long e conf_short: una COPPIA per soglia (membro +1 al long,
    -1 allo short, stesso `pair`) — la grid search dei filtri ne fa una riga
    sola. Con un solo lato: un filtro direzionale singolo.

    Nomi: CONF_PIPS_MEDI_0.5_L / _S, pair CONF_PIPS_MEDI_0.5.
    Il filtro e' vero dove la metrica e' STRETTAMENTE sopra la soglia; dove
    la confidenza non e' nota (NaN) e' falso: il segnale non si trada.

    Rieseguire con gli stessi nomi aggiorna i valori (niente doppioni nel
    registro). Restituisce la lista dei nomi, da passare a `filtri=`.
    """
    if metrica not in _METRICHE:
        raise ValueError(f"metrica deve essere una di {_METRICHE}.")
    if conf_long is None and conf_short is None:
        raise ValueError("Serve almeno conf_long o conf_short.")
    if isinstance(soglie, (int, float)):
        soglie = [soglie]

    gia = set(list_filters())
    nomi = []
    for s in soglie:
        s = float(s)
        base = f"{prefisso}_{metrica.upper()}_{_fmt(s)}"
        coppia = base if (conf_long is not None and conf_short is not None) else None
        for conf, direzione, suffisso in ((conf_long, 1, "_L"), (conf_short, -1, "_S")):
            if conf is None:
                continue
            nome = base + suffisso
            if nome in gia and nome not in _DATI_FILTRI:
                raise ValueError(f"'{nome}' e' gia' registrato e non e' un filtro di confidenza.")
            _DATI_FILTRI[nome] = (conf[metrica], s)
            if nome not in gia:
                register_filter(nome, direction=direzione, pair=coppia)(_funzione_filtro(nome))
            nomi.append(nome)
    return nomi


# ========================================================================
# 5 · La lettura
# ========================================================================

def report_calibrazione(esiti: pd.DataFrame, df: pd.DataFrame, split,
                        conf_long: pd.DataFrame | None = None,
                        conf_short: pd.DataFrame | None = None,
                        mostra_oos: bool = False) -> pd.DataFrame:
    """
    Confidenza prevista contro esito reale, per lato e per cella.

    Per ogni trade della baseline si legge la confidenza alla sua barra di
    segnale (quello che si sapeva prima di entrare) e la si confronta con
    come e' andato davvero.

    split        il primo istante dell'Out-of-Sample, es. df_oos.index[0]
    mostra_oos   False (default) = solo In-Sample. Si mette True UNA volta,
                 al passo 6, insieme al resto dell'OOS.

    Colonne: parte, lato, cella, trade (quelli con confidenza nota),
    pips_previsti, pips_reali, win_rate_previsto, win_rate_reale.
    """
    split = pd.Timestamp(split)
    righe = []
    for conf, lato in ((conf_long, 1), (conf_short, -1)):
        if conf is None:
            continue
        e = esiti[esiti["lato"] == lato].copy()
        pos = e["barra_segnale"].to_numpy().astype(int)
        e["cella"] = conf["etichetta"].to_numpy()[pos]
        e["pips_previsti"] = conf["pips_medi"].to_numpy()[pos]
        e["wr_previsto"] = conf["win_rate"].to_numpy()[pos]
        e["parte"] = np.where(df.index[pos] < split, "IS", "OOS")
        e = e[e["pips_previsti"].notna()]
        parti = ["IS", "OOS"] if mostra_oos else ["IS"]
        for parte in parti:
            for cella in ETICHETTE_CELLA.values():
                g = e[(e["parte"] == parte) & (e["cella"] == cella)]
                righe.append({
                    "parte": parte, "lato": "long" if lato == 1 else "short",
                    "cella": cella, "trade": len(g),
                    "pips_previsti": g["pips_previsti"].mean() if len(g) else np.nan,
                    "pips_reali": g["pips_netti"].mean() if len(g) else np.nan,
                    "win_rate_previsto": g["wr_previsto"].mean() if len(g) else np.nan,
                    "win_rate_reale": g["vinto"].mean() if len(g) else np.nan,
                })
    return pd.DataFrame(righe)


def _curva_pips(trades: pd.DataFrame, pip_size: float, commission: float) -> pd.Series:
    if len(trades) == 0:
        return pd.Series(dtype=float)
    _, netti = pips_per_trade(trades, pip_size, commission)
    ordine = np.argsort(pd.DatetimeIndex(trades["ExitTime"]).to_numpy(), kind="mergesort")
    return pd.Series(netti.to_numpy()[ordine].cumsum(),
                     index=pd.DatetimeIndex(trades["ExitTime"])[ordine])


def plot_oos_confidenza(trades_senza: pd.DataFrame, trades_con: pd.DataFrame,
                        pip_size: float, commission: float = 0.0,
                        etichetta_con: str = "con confidenza",
                        titolo: str = "Out-of-Sample"):
    """
    Le due equity in pips netti cumulati, sullo stesso grafico:

        senza confidenza   la baseline, `oos.trades()`
        con confidenza     la riga filtrata, `oos.trades("CONF_…")`

    Sono due backtest separati (non la stessa lista tagliata): col filtro
    entrano anche trade che senza erano bloccati da una posizione aperta.

    Restituisce (ax, tabella): trade, avg_trade_netto, pips_totali,
    max_dd_pips per le due curve.
    """
    import matplotlib.pyplot as plt

    righe = []
    fig, ax = plt.subplots(figsize=(11, 5))
    for trades, nome in ((trades_senza, "senza confidenza"), (trades_con, etichetta_con)):
        curva = _curva_pips(trades, pip_size, commission)
        if len(curva):
            ax.plot(curva.index, curva.to_numpy(), label=nome, linewidth=1.4)
            valori = np.r_[0.0, curva.to_numpy()]          # si parte da zero
            dd = float((np.maximum.accumulate(valori) - valori).max())
            media = float(curva.iloc[-1] / len(curva))
            totale = float(curva.iloc[-1])
        else:
            dd = media = totale = np.nan
        righe.append({"curva": nome, "trade": len(curva), "avg_trade_netto": media,
                      "pips_totali": totale, "max_dd_pips": dd})
    ax.axhline(0, color="grey", linewidth=0.8)
    ax.set_title(f"{titolo} · pips netti cumulati")
    ax.set_ylabel("pips netti")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return ax, pd.DataFrame(righe)
