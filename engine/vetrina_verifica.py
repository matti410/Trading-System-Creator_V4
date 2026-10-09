"""
Vetrina · verifica dei trade (7/10/2026) — schermata 7 del notebook slim.

A COSA SERVE
------------
Dopo la scheda della strategia, prima dello stress test: controllare che il
backtest abbia fatto quello che le regole dicono. Due funzioni.

    verifica_trade(s)     7a · controllo automatico su TUTTI i trade
    lente(s, numero=...)  7b · un trade sul grafico a candele (dal 9/10/2026
                          disegna anche la regola dei trigger scattati:
                          engine/vetrina_trigger.py)

COME CONTROLLA
--------------
`verifica_trade` non si fida del motore: ricalcola trigger e filtri
chiamando direttamente le condizioni del registro (`get_entry`,
`get_filter`), una per una, e li confronta con i trade prodotti dal
backtest. Non passa dalle colonne che il motore ha costruito, ne' dalle
entry composite o «congelate»: se il motore avesse sbagliato barra, lato o
filtro, qui si vedrebbe.

Le regole, per ogni trade:
  1. almeno uno dei trigger scelti era vero sulla barra PRIMA dell'ingresso
  2. tutti i filtri scelti erano veri su quella barra
  3. l'ingresso e' all'apertura della barra successiva al segnale
  4. ne' la barra del segnale ne' quella d'ingresso sono in quarantena
  5. il trade non dura piu' delle barre del suo lato
  6. una posizione alla volta

E al contrario: ogni segnale che NON e' diventato un trade deve avere un
motivo (posizione gia' aperta, filtro falso, rollover, stop non ancora
calcolabile, long e short insieme). Un segnale senza motivo e' un errore.

Nessun numero della strategia cambia: si leggono i trade gia' calcolati
dalla schermata 6 (`s.trades_is`, `s.trades_oos`).

GLI ORARI
---------
In ora italiana (Europe/Rome), come i grafici IC Markets su TradingView.
L'ora di una candela e' quella della sua apertura.

Modulo ADDITIVO: non modifica nessun file esistente; `vetrina.py` lo
importa in fondo per esporre le due funzioni al notebook.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import registry as reg
from . import vetrina as _v
from .exit_search_bt import soglie_per_lato
from .filter_search_bt import BASELINE
from .metriche import pips_per_trade
from .quarantena_trade import barre_in_quarantena
from .vetrina_trigger import descrivi_trigger

FUSO = "Europe/Rome"
PERIODI = {"in-sample": "is", "out-of-sample": "oos"}
_LATI = ((1, "long"), (-1, "short"))
_COLONNE_PREZZO = {"open", "high", "low", "close", "volume", "spread"}

MOTIVI_USCITA = ("a tempo", "stop", "target", "inversione", "regola di uscita")


# ========================================================================
# Ricalcolo indipendente delle condizioni
# ========================================================================

def _periodo(s, periodo: str):
    """(df, trade) del periodo richiesto."""
    chiave = PERIODI.get(str(periodo).strip().lower())
    if chiave is None:
        raise ValueError("periodo dev'essere «in-sample» oppure «out-of-sample».")
    if chiave == "is":
        return s.df_is, s.trades_is
    return s.df_oos, s.trades_oos


def _filtri_del_lato(s, lato: str) -> list[str]:
    """I filtri registrati che la strategia applica a quel lato."""
    ris = s.fs.risultati.set_index("filtro")
    nomi = []
    for etichetta in s.filtri_scelti:
        nome = ris.loc[etichetta, f"filtro_{lato}"]
        if nome not in ("—", None) and isinstance(nome, str):
            nomi.append(nome)
    return nomi


def _ricalcola(s, df: pd.DataFrame) -> dict:
    """
    Le condizioni della strategia ricalcolate dal registro, barra per barra.

    Per ogni lato attivo:
        componenti   {nome del trigger scelto: vettore booleano}
        trigger      almeno un trigger scelto e' vero
        segnale      il trigger come lo vede il motore (per una scelta in OR
                     e' l'evento: la prima barra in cui scatta)
        filtri       {nome del filtro: vettore booleano}
        filtro_ok    tutti i filtri sono veri
        soglia_ok    lo stop/target della barra d'ingresso e' calcolabile
        finale       segnale che il motore puo' tradare
    Piu' `quarantena` (una voce per barra) e `n` (barre).
    """
    n = len(df)
    u = s.uscite
    q = barre_in_quarantena(df, True)
    q = np.zeros(n, dtype=bool) if q is None else np.asarray(q, dtype=bool)
    q_dopo = np.r_[q[1:], False]

    usa_sl, usa_tp = bool(u["perc_sl"]), bool(u["perc_tp"])
    soglie = soglie_per_lato(df, u["n_barre_long"], u["n_barre_short"], _v.FINESTRA,
                             u["perc_sl"], u["perc_tp"], lag=_v.LAG)
    out = {"quarantena": q, "n": n, "soglie": soglie}
    for segno, lato in _LATI:
        scelti = s.trigger_long if segno == 1 else s.trigger_short
        entry = s.entry_long if segno == 1 else s.entry_short
        if not scelti or entry is None:
            continue
        componenti = {nome: reg.get_entry(nome)(df).fillna(False).astype(bool).to_numpy()
                      for nome in scelti}
        trigger = np.logical_or.reduce(list(componenti.values()))
        segnale = reg.get_entry(entry)(df).fillna(False).astype(bool).to_numpy()
        filtri = {nome: reg.get_filter(nome)(df).astype(bool).to_numpy()
                  for nome in _filtri_del_lato(s, lato)}
        filtro_ok = (np.logical_and.reduce(list(filtri.values())) if filtri
                     else np.ones(n, dtype=bool))
        ok = np.ones(n, dtype=bool)
        if usa_sl:
            ok &= ~soglie[f"sl_{lato}"].isna().to_numpy()
        if usa_tp:
            ok &= ~soglie[f"tp_{lato}"].isna().to_numpy()
        soglia_ok = np.r_[ok[1:], False]       # si legge sulla barra d'ingresso
        out[lato] = {"componenti": componenti, "trigger": trigger, "segnale": segnale,
                     "filtri": filtri, "filtro_ok": filtro_ok, "soglia_ok": soglia_ok,
                     "finale": segnale & filtro_ok & soglia_ok & ~q & ~q_dopo}
    return out


# ========================================================================
# Il registro dei trade
# ========================================================================

def _ora(indice: pd.DatetimeIndex, posizioni) -> list[str]:
    locale = indice.tz_convert(FUSO)
    return [locale[int(p)].strftime("%d/%m/%Y %H:%M") for p in posizioni]


def _motivi_uscita(s, trades: pd.DataFrame) -> list[str]:
    """Perche' si e' chiuso ogni trade, nell'ordine in cui il motore decide."""
    u = s.uscite
    lato = np.sign(trades["Size"].to_numpy())
    ent = trades["EntryBar"].to_numpy(dtype=int)
    usc = trades["ExitBar"].to_numpy(dtype=int)
    px = trades["ExitPrice"].to_numpy(dtype=float)
    sl = trades["SL"].to_numpy(dtype=float) if "SL" in trades else np.full(len(trades), np.nan)
    tp = trades["TP"].to_numpy(dtype=float) if "TP" in trades else np.full(len(trades), np.nan)
    ordine = np.argsort(ent, kind="mergesort")
    successivo = {int(ordine[k]): int(ordine[k + 1]) for k in range(len(ordine) - 1)}
    motivi = []
    for i in range(len(trades)):
        limite = u["n_barre_long"] if lato[i] > 0 else u["n_barre_short"]
        tol = abs(px[i]) * 1e-9
        j = successivo.get(i)
        if np.isfinite(sl[i]) and ((lato[i] > 0 and px[i] <= sl[i] + tol)
                                   or (lato[i] < 0 and px[i] >= sl[i] - tol)):
            motivi.append("stop")
        elif np.isfinite(tp[i]) and ((lato[i] > 0 and px[i] >= tp[i] - tol)
                                     or (lato[i] < 0 and px[i] <= tp[i] + tol)):
            motivi.append("target")
        elif j is not None and ent[j] == usc[i] and lato[j] != lato[i]:
            motivi.append("inversione")
        elif usc[i] - ent[i] >= limite:
            motivi.append("a tempo")
        else:
            motivi.append("regola di uscita")
    return motivi


def registro_trade(s, periodo: str = "out-of-sample") -> pd.DataFrame:
    """
    L'elenco dei trade di un periodo, in ordine di ingresso e numerati da 1.
    Orari in ora italiana. Colonne tecniche in fondo (barre e prezzo dello stop).
    """
    s._serve("oos", "6 · Scheda strategia")
    df, trades = _periodo(s, periodo)
    if trades is None or len(trades) == 0:
        return pd.DataFrame()
    t = trades.copy()
    t["_motivo"] = _motivi_uscita(s, t)
    _, netti = pips_per_trade(t, s.fs.pip_size, s.fs.commission or 0.0)
    t["_pips"] = netti.to_numpy()
    t = t.sort_values("EntryBar", kind="mergesort").reset_index(drop=True)
    cond = _ricalcola(s, df)
    seg = t["EntryBar"].to_numpy(dtype=int) - 1
    scattati = []
    for i, lato_num in enumerate(np.sign(t["Size"].to_numpy())):
        blocco = cond.get("long" if lato_num > 0 else "short", {})
        veri = [nome for nome, v in blocco.get("componenti", {}).items() if v[seg[i]]]
        scattati.append(", ".join(veri) if veri else "—")
    return pd.DataFrame({
        "N.": np.arange(1, len(t) + 1),
        "Lato": np.where(t["Size"] > 0, "LONG", "SHORT"),
        "Segnale": _ora(df.index, seg),
        "Ingresso": _ora(df.index, t["EntryBar"]),
        "Uscita": _ora(df.index, t["ExitBar"]),
        "Prezzo ingresso": t["EntryPrice"].to_numpy(dtype=float),
        "Prezzo uscita": t["ExitPrice"].to_numpy(dtype=float),
        "Uscita per": t["_motivo"].to_numpy(),
        "Pips netti": t["_pips"].to_numpy(),
        "Trigger scattato": scattati,
        "barra_segnale": seg,
        "barra_ingresso": t["EntryBar"].to_numpy(dtype=int),
        "barra_uscita": t["ExitBar"].to_numpy(dtype=int),
        "stop": t["SL"].to_numpy(dtype=float) if "SL" in t else np.nan,
        "target": t["TP"].to_numpy(dtype=float) if "TP" in t else np.nan,
    })


# ========================================================================
# 7a · Il controllo automatico
# ========================================================================

REGOLE = (
    ("trigger", "Il trigger era vero sulla barra prima dell'ingresso"),
    ("filtri", "Tutti i filtri scelti erano veri su quella barra"),
    ("ingresso", "L'ingresso è all'apertura della barra dopo il segnale"),
    ("rollover", "Né il segnale né l'ingresso cadono nel rollover"),
    ("durata", "Il trade non dura più delle barre del suo lato"),
    ("una_alla_volta", "Una posizione alla volta"),
)

MOTIVI_NON_TRADATO = (
    "posizione già aperta nello stesso verso",
    "filtro falso",
    "barra nel rollover o dopo una pausa",
    "stop non ancora calcolabile (avvio dello storico)",
    "long e short sulla stessa barra",
    "trade ancora aperto a fine storico",
    "ultima barra dello storico",
    "senza spiegazione",
)


def controlla_periodo(s, periodo: str) -> dict:
    """
    Il controllo di un periodo. Ritorna:
        registro      l'elenco dei trade (registro_trade)
        esiti         {regola: vettore booleano, una voce per trade del registro}
        non_tradati   {motivo: quanti segnali}
        segnali       quanti segnali del trigger in tutto
    """
    df, trades = _periodo(s, periodo)
    r = registro_trade(s, periodo)
    cond = _ricalcola(s, df)
    n = cond["n"]
    q = cond["quarantena"]
    non_tradati = {m: 0 for m in MOTIVI_NON_TRADATO}
    if r.empty:
        esiti = {chiave: np.array([], dtype=bool) for chiave, _ in REGOLE}
        segnali = sum(int(cond[l]["segnale"].sum()) for _, l in _LATI if l in cond)
        return {"registro": r, "esiti": esiti, "non_tradati": non_tradati, "segnali": segnali}

    seg = r["barra_segnale"].to_numpy(dtype=int)
    ent = r["barra_ingresso"].to_numpy(dtype=int)
    usc = r["barra_uscita"].to_numpy(dtype=int)
    lato = np.where(r["Lato"] == "LONG", 1, -1)
    apertura = df["Open"].to_numpy(dtype=float)
    spread = float(s.costi.get("spread") or 0.0)
    u = s.uscite

    def del_lato(chiave):
        v = np.zeros(len(r), dtype=bool)
        for segno, nome in _LATI:
            m = lato == segno
            if m.any() and nome in cond:
                v[m] = cond[nome][chiave][seg[m]]
        return v

    # backtesting.py mette lo spread nel prezzo d'ingresso: il long compra
    # sopra l'apertura, lo short vende sotto
    atteso = apertura[ent] * (1.0 + lato * spread)
    limite = np.where(lato > 0, u["n_barre_long"], u["n_barre_short"])
    esiti = {
        "trigger": del_lato("trigger"),
        "filtri": del_lato("filtro_ok"),
        "ingresso": np.abs(r["Prezzo ingresso"].to_numpy(dtype=float) - atteso) <= np.abs(atteso) * 1e-9,
        "rollover": ~q[seg] & ~q[ent],
        "durata": (usc - ent) <= limite,
        "una_alla_volta": np.r_[True, ent[1:] >= usc[:-1]],
    }

    # --- i segnali che non sono diventati trade -------------------------
    segnali = 0
    ultimo_ingresso = int(ent.max())
    for segno, nome in _LATI:
        if nome not in cond:
            continue
        c = cond[nome]
        altro = cond.get("short" if nome == "long" else "long")
        tradati = set(int(x) for x in seg[lato == segno])
        barre = np.flatnonzero(c["segnale"])
        segnali += len(barre)
        for i in barre:
            i = int(i)
            if i in tradati:
                continue
            aperti = np.flatnonzero((ent <= i) & (i < usc))
            if i >= n - 1:
                motivo = "ultima barra dello storico"
            elif not c["filtro_ok"][i]:
                motivo = "filtro falso"
            elif q[i] or q[i + 1]:
                motivo = "barra nel rollover o dopo una pausa"
            elif not c["soglia_ok"][i]:
                motivo = "stop non ancora calcolabile (avvio dello storico)"
            elif altro is not None and altro["finale"][i]:
                motivo = "long e short sulla stessa barra"
            elif len(aperti) and lato[aperti[0]] == segno:
                motivo = "posizione già aperta nello stesso verso"
            elif i >= ultimo_ingresso:
                motivo = "trade ancora aperto a fine storico"
            else:
                motivo = "senza spiegazione"
            non_tradati[motivo] += 1
    return {"registro": r, "esiti": esiti, "non_tradati": non_tradati, "segnali": segnali}


def verifica_trade(s) -> dict:
    """
    Schermata 7a. Controlla tutti i trade della strategia scelta, in-sample e
    out-of-sample, contro le condizioni ricalcolate dal registro. Mostra le
    regole (rispettata in X trade su N), come si sono chiusi i trade e dove
    sono finiti i segnali non tradati.

    Ritorna {"regole", "uscite", "segnali"} (tabelle) e "da_guardare": per
    ogni periodo i numeri dei trade che violano una regola (per la lente).
    """
    s._serve("oos", "6 · Scheda strategia")
    if s.trades_is is None:
        raise RuntimeError("Manca un passaggio: esegui prima la schermata «6 · Scheda strategia».")
    controlli = {p: controlla_periodo(s, p) for p in PERIODI}
    s.controlli = controlli
    totale = sum(len(c["registro"]) for c in controlli.values())

    righe, da_guardare = [], {p: [] for p in PERIODI}
    for chiave, testo in REGOLE:
        ok = sum(int(c["esiti"][chiave].sum()) for c in controlli.values())
        violano = []
        for p, c in controlli.items():
            numeri = [int(x) for x in c["registro"]["N."].to_numpy()[~c["esiti"][chiave]]] if len(c["registro"]) else []
            da_guardare[p].extend(numeri)
            violano += [f"{p} n. {x}" for x in numeri[:5]]
        righe.append({"Regola": testo, "Rispettata in": f"{_v._fmt(ok)} trade su {_v._fmt(totale)}",
                      "Esito": "OK" if ok == totale else "DA GUARDARE",
                      "Trade da guardare": ", ".join(violano) if violano else "—"})
    senza = sum(c["non_tradati"]["senza spiegazione"] for c in controlli.values())
    n_segnali = sum(c["segnali"] for c in controlli.values())
    righe.append({"Regola": "Ogni segnale non tradato ha un motivo",
                  "Rispettata in": f"{_v._fmt(n_segnali - senza)} segnali su {_v._fmt(n_segnali)}",
                  "Esito": "OK" if senza == 0 else "DA GUARDARE", "Trade da guardare": "—"})
    regole = pd.DataFrame(righe)
    da_guardare = {p: sorted(set(v)) for p, v in da_guardare.items()}

    uscite = pd.DataFrame({"Uscita per": list(MOTIVI_USCITA)})
    for p, c in controlli.items():
        conta = c["registro"]["Uscita per"].value_counts() if len(c["registro"]) else {}
        uscite[p.capitalize()] = [int(conta.get(m, 0)) for m in MOTIVI_USCITA]
    uscite = uscite[(uscite.drop(columns="Uscita per").sum(axis=1) > 0)].reset_index(drop=True)

    segn = pd.DataFrame({"Che fine ha fatto il segnale": ["è diventato un trade", *MOTIVI_NON_TRADATO]})
    for p, c in controlli.items():
        fatti = c["segnali"] - sum(c["non_tradati"].values())
        segn[p.capitalize()] = [fatti, *[c["non_tradati"][m] for m in MOTIVI_NON_TRADATO]]
    tieni = (segn.drop(columns="Che fine ha fatto il segnale").sum(axis=1) > 0) | (segn.index == 0)
    segn = segn[tieni].reset_index(drop=True)

    s.tabelle["verifica"] = {"regole": regole, "uscite": uscite, "segnali": segn}
    tutto_ok = bool((regole["Esito"] == "OK").all())
    _v._mostra((f"Controllo automatico · {_v._fmt(totale)} trade verificati uno per uno", regole))
    _v._mostra(("Come si sono chiusi i trade", uscite), ("Che fine hanno fatto i segnali del trigger", segn))
    _v._riquadro(
        "Lo strumento ha ricalcolato per conto suo trigger e filtri, barra per barra, e li ha confrontati con ogni "
        "trade del backtest. La prima tabella dice in quanti trade ogni regola è rispettata. La terza segue i segnali "
        "del trigger: quanti sono diventati un trade e, per gli altri, perché no.",
        "Ogni riga della prima tabella deve dire OK: vuol dire che il backtest è entrato esattamente dove le tue regole "
        "dicono di entrare, una barra dopo il segnale, mai prima. È normale che molti segnali non diventino trade: "
        "si tiene una posizione alla volta, e un filtro serve proprio a scartarne una parte.",
        ("Tutto torna. Apri la lente qui sotto per vedere un trade sul grafico, poi vai alla schermata 8." if tutto_ok
         else "Qualcosa non torna: apri con la lente i trade indicati nella colonna «Trade da guardare»."))
    return {"regole": regole, "uscite": uscite, "segnali": segn, "da_guardare": da_guardare}


# ========================================================================
# 7b · La lente sul trade
# ========================================================================

def indicatori_disponibili(s) -> list[str]:
    """Gli indicatori gia' calcolati che la lente puo' disegnare."""
    return [c for c in s.df.columns
            if c.lower() not in _COLONNE_PREZZO and not c.startswith("__")
            and pd.api.types.is_numeric_dtype(s.df[c])]


def _lista_indicatori(s, indicatori) -> list[str]:
    if indicatori is None:
        voci = []
    elif isinstance(indicatori, str):
        voci = indicatori.split(",")
    else:
        voci = list(indicatori)
    voci = list(dict.fromkeys(v.strip() for v in voci if isinstance(v, str) and v.strip()))
    disponibili = indicatori_disponibili(s)
    mancanti = [v for v in voci if v not in disponibili]
    if mancanti:
        raise ValueError(f"Indicatore non trovato: {', '.join(mancanti)}. "
                         f"Disponibili: {', '.join(disponibili)}.")
    return voci


def _scegli_trade(registro: pd.DataFrame, numero, data) -> int:
    """La riga del registro da mostrare: per numero, per data o a caso."""
    if numero not in (None, 0, ""):
        numero = int(numero)
        if not 1 <= numero <= len(registro):
            raise ValueError(f"Il trade n. {numero} non esiste: in questo periodo vanno da 1 a {len(registro)}.")
        return numero - 1
    if data not in (None, ""):
        try:
            giorno = pd.to_datetime(str(data).strip(), dayfirst=True)
        except Exception:
            raise ValueError("La data va scritta come giorno/mese/anno, per esempio 15/03/2026.") from None
        quando = pd.to_datetime(registro["Segnale"], format="%d/%m/%Y %H:%M")
        dopo = np.flatnonzero(quando >= giorno)
        if len(dopo) == 0:
            raise ValueError(f"Nessun trade dal {giorno:%d/%m/%Y} in poi in questo periodo "
                             f"(l'ultimo è del {registro['Segnale'].iloc[-1][:10]}).")
        return int(dopo[0])
    return int(np.random.default_rng().integers(len(registro)))


def lente(s, periodo: str = "out-of-sample", numero=None, data=None, indicatori="",
          barre_prima: int = 40, barre_dopo: int = 20, mostra_trigger: bool = True):
    """
    Schermata 7b. Un trade sul grafico a candele, con segnale, ingresso,
    uscita, stop e gli indicatori scelti.

    periodo      «in-sample» oppure «out-of-sample»
    numero       il numero del trade nel periodo (da 1); vuoto o 0 = a caso
    data         in alternativa: il primo trade da quel giorno (gg/mm/aaaa)
    indicatori   nomi separati da virgola fra quelli gia' calcolati
                 (`indicatori_disponibili(s)`). Quelli sulla scala del prezzo
                 vanno sulle candele, gli altri in un pannello sotto.
    barre_prima / barre_dopo   quanto allargare la finestra
    mostra_trigger   True (default): accanto al triangolo il nome del trigger
                 scattato, una banda sulle candele che formano la figura, la
                 linea del livello che la regola rompe e gli indicatori che la
                 regola legge (engine/vetrina_trigger.py). False: la lente di
                 prima, con la scritta «segnale».

    Ritorna la figura plotly (in un notebook la mostra).
    """
    s._serve("oos", "6 · Scheda strategia")
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError as e:
        raise ImportError("La lente usa plotly. Su Colab c'è già; altrove: pip install plotly") from e

    df, _ = _periodo(s, periodo)
    registro = registro_trade(s, periodo)
    if registro.empty:
        raise ValueError(f"Nessun trade nel periodo {periodo}.")
    scelti = _lista_indicatori(s, indicatori)
    t = registro.iloc[_scegli_trade(registro, numero, data)]
    long = t["Lato"] == "LONG"
    seg, ent, usc = int(t["barra_segnale"]), int(t["barra_ingresso"]), int(t["barra_uscita"])

    a = max(0, seg - int(barre_prima))
    b = min(len(df) - 1, usc + int(barre_dopo))
    finestra = df.iloc[a:b + 1]
    x = np.arange(len(finestra))
    ore = finestra.index.tz_convert(FUSO)
    etichette = [o.strftime("%d/%m %H:%M") for o in ore]
    decimali = max(0, int(round(-np.log10(s.pip))) + 1)

    # --- le regole dei trigger scattati su questo segnale ------------------
    # Sono quelli scritti nella colonna «Trigger scattato» del registro: i
    # trigger scelti che erano veri sulla candela del segnale.
    scattati = [n for n in str(t["Trigger scattato"]).split(", ") if n and n != "—"]
    disegni = [descrivi_trigger(n, df, seg, a, b) for n in scattati] if mostra_trigger else []
    for d in disegni:                    # gli indicatori che la regola legge si aggiungono ai tuoi
        for nome in d.indicatori:
            if nome in finestra.columns and nome not in scelti:
                scelti.append(nome)

    # indicatori: sul prezzo se stanno nella fascia dei prezzi, altrimenti in
    # un pannello sotto, raggruppati per ordine di grandezza
    basso, alto = float(finestra["Low"].min()), float(finestra["High"].max())
    sul_prezzo, pannelli = [], {}
    for nome in scelti:
        v = finestra[nome].astype(float)
        if v.notna().any() and v.min() >= basso * 0.9 and v.max() <= alto * 1.1:
            sul_prezzo.append(nome)
        else:
            mediana = float(v.abs().median()) if v.notna().any() else 0.0
            ordine = int(np.floor(np.log10(mediana))) if mediana > 0 else 0
            pannelli.setdefault(ordine, []).append(nome)
    gruppi = list(pannelli.values())
    righe = 1 + len(gruppi)
    fig = make_subplots(rows=righe, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[0.62] + [0.38 / len(gruppi)] * len(gruppi) if gruppi else [1.0])

    fig.add_trace(go.Candlestick(
        x=x, open=finestra["Open"], high=finestra["High"], low=finestra["Low"], close=finestra["Close"],
        name="prezzo", showlegend=False, hoverinfo="text",
        text=[f"{e}<br>apertura {o:.{decimali}f}<br>massimo {h:.{decimali}f}<br>minimo {l:.{decimali}f}"
              f"<br>chiusura {c:.{decimali}f}"
              for e, o, h, l, c in zip(etichette, finestra["Open"], finestra["High"],
                                       finestra["Low"], finestra["Close"])],
        increasing_line_color="#2a9d8f", decreasing_line_color="#c8553d"), row=1, col=1)
    tavolozza = ["#1f77b4", "#ff7f0e", "#9467bd", "#8c564b", "#e377c2", "#17becf", "#7f7f7f", "#bcbd22"]
    colore = {nome: tavolozza[k % len(tavolozza)] for k, nome in enumerate(scelti)}
    for nome in sul_prezzo:
        fig.add_trace(go.Scatter(x=x, y=finestra[nome], mode="lines", name=nome,
                                 line=dict(width=1.4, color=colore[nome]),
                                 hovertemplate=f"{nome} %{{y:.{decimali}f}}<extra></extra>"), row=1, col=1)
    for k, gruppo in enumerate(gruppi):
        for nome in gruppo:
            fig.add_trace(go.Scatter(x=x, y=finestra[nome], mode="lines", name=nome,
                                     line=dict(width=1.4, color=colore[nome]),
                                     hovertemplate=f"{nome} %{{y:.4g}}<extra></extra>"), row=2 + k, col=1)
        fig.update_yaxes(title_text=", ".join(gruppo), row=2 + k, col=1)

    verde, rosso, blu = "#1b7f3b", "#b3261e", "#1f5f99"

    # --- le regole dei trigger: banda sulle candele, livelli, soglie --------
    riga_di = {nome: 1 for nome in sul_prezzo}
    for k, gruppo in enumerate(gruppi):
        for nome in gruppo:
            riga_di[nome] = 2 + k
    soglie_gia = set()
    corse = []                                   # candele consecutive = una banda sola
    for p in sorted(set().union(*[d.barre for d in disegni])):
        if corse and p == corse[-1][1] + 1:
            corse[-1][1] = p
        else:
            corse.append([p, p])
    for ini, fin in corse:                       # l'unione dei trigger: niente bande sovrapposte
        fig.add_vrect(x0=ini - a - 0.5, x1=fin - a + 0.5, fillcolor=verde if long else rosso,
                      opacity=0.13, layer="below", line_width=0, row="all", col=1)
    for d in disegni:
        for testo, valori in d.livelli:
            fig.add_trace(go.Scatter(
                x=x, y=valori, mode="lines", name=testo, connectgaps=False,
                line=dict(width=1.8, color="#b8860b"),
                hovertemplate=f"{testo} %{{y:.{decimali}f}}<extra></extra>"), row=1, col=1)
        for nome, valore in d.soglie.items():
            riga = riga_di.get(nome)
            if riga and riga > 1 and (riga, valore) not in soglie_gia:
                soglie_gia.add((riga, valore))
                fig.add_hline(y=valore, line=dict(width=1, dash="dot", color="gray"),
                              annotation_text=f"{valore:g}", annotation_position="top left",
                              row=riga, col=1)

    # --- il trade ---------------------------------------------------------
    scarto = (alto - basso) * 0.035
    y_segnale = (float(df["Low"].iloc[seg]) - scarto) if long else (float(df["High"].iloc[seg]) + scarto)
    nome_segnale = ", ".join(scattati) if (mostra_trigger and scattati) else "segnale"
    fig.add_trace(go.Scatter(
        x=[seg - a], y=[y_segnale], mode="markers+text", name="segnale",
        marker=dict(symbol="triangle-up" if long else "triangle-down", size=15,
                    color=verde if long else rosso, line=dict(width=1, color="white")),
        text=[nome_segnale], textposition="bottom center" if long else "top center",
        **(dict(textfont=dict(size=11), cliponaxis=False) if nome_segnale != "segnale" else {}),
        hovertemplate=f"SEGNALE {t['Lato']}<br>{t['Segnale']}<br>{t['Trigger scattato']}<extra></extra>"),
        row=1, col=1)
    fig.add_trace(go.Scatter(
        x=[ent - a], y=[t["Prezzo ingresso"]], mode="markers", name="ingresso",
        marker=dict(symbol="triangle-right", size=13, color=blu, line=dict(width=1, color="white")),
        hovertemplate=f"INGRESSO {t['Lato']}<br>{t['Ingresso']}<br>prezzo {t['Prezzo ingresso']:.{decimali}f}"
                      "<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=[usc - a], y=[t["Prezzo uscita"]], mode="markers", name=f"uscita ({t['Uscita per']})",
        marker=dict(symbol="x", size=11, color="black", line=dict(width=2, color="black")),
        hovertemplate=f"USCITA: {t['Uscita per']}<br>{t['Uscita']}<br>prezzo {t['Prezzo uscita']:.{decimali}f}"
                      f"<br>{t['Pips netti']:+.1f} pips netti<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=[ent - a, usc - a], y=[t["Prezzo ingresso"], t["Prezzo uscita"]], mode="lines",
        line=dict(width=1.3, dash="dot", color=verde if t["Pips netti"] > 0 else rosso),
        showlegend=False, hoverinfo="skip"), row=1, col=1)
    for chiave, nome, tinta in (("stop", "stop", rosso), ("target", "target", verde)):
        livello = t[chiave]
        if np.isfinite(livello):
            fig.add_trace(go.Scatter(
                x=[ent - a, usc - a], y=[livello, livello], mode="lines", name=nome,
                line=dict(width=1.2, dash="dash", color=tinta),
                hovertemplate=f"{nome} {livello:.{decimali}f}<extra></extra>"), row=1, col=1)

    passo = max(1, len(x) // 10)
    fig.update_xaxes(tickmode="array", tickvals=list(x[::passo]), ticktext=etichette[::passo],
                     rangeslider_visible=False, showgrid=True, gridcolor="rgba(128,128,128,.2)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,.2)")
    fig.update_yaxes(title_text=f"{s.symbol} · prezzo", row=1, col=1)
    fig.update_layout(
        title=dict(text=f"Trade n. {int(t['N.'])} · {t['Lato']} · {periodo} · {t['Pips netti']:+.1f} pips netti"
                        f"<br><sup>ora italiana · l'ora di una candela è quella della sua apertura</sup>"),
        height=520 + 150 * len(gruppi), hovermode="x unified", template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1.0),
        margin=dict(l=60, r=30, t=90, b=40))

    filtri = _filtri_del_lato(s, "long" if long else "short")
    scheda = pd.DataFrame({
        "": ["Trade", "Trigger scattato", "Filtri veri sul segnale", "Segnale (sulla candela delle)",
             "Ingresso (all'apertura della candela delle)", "Uscita", "Risultato"],
        " ": [f"n. {int(t['N.'])} di {len(registro)} · {t['Lato']} · {periodo}", t["Trigger scattato"],
              ", ".join(filtri) if filtri else "nessun filtro",
              t["Segnale"], f"{t['Ingresso']} a {t['Prezzo ingresso']:.{decimali}f}",
              f"{t['Uscita']} a {t['Prezzo uscita']:.{decimali}f} · {t['Uscita per']}",
              f"{t['Pips netti']:+.1f} pips netti"],
    })
    s.tabelle["lente"] = scheda
    if _v._in_notebook():
        fig.show()
    _v._mostra(("Il trade in chiaro", scheda))
    _v._nota("Indicatori disponibili: " + ", ".join(indicatori_disponibili(s)) + ".")
    spiega_regola = ""
    if disegni:
        spiega_regola = (" Accanto al triangolo c'è il nome del trigger scattato. La banda colorata copre le candele "
                         "che formano la figura o che la regola confronta; la linea dorata è il livello che la regola "
                         "doveva rompere; gli indicatori che la regola legge sono sul grafico o nei pannelli sotto.")
    _v._riquadro(
        "Un trade vero del backtest. Il triangolo colorato è la candela su cui è scattato il segnale; il triangolo "
        "blu è l'ingresso, all'apertura della candela dopo; la croce è l'uscita. La linea tratteggiata rossa è lo stop."
        + spiega_regola,
        "Il segnale deve stare proprio dove la tua regola dice: per un incrocio di medie accendi le due medie e "
        "guarda che si incrocino sulla candela del triangolo. L'ingresso deve essere sempre una candela dopo, mai "
        "sulla stessa: è la garanzia che il backtest non usa informazioni che dal vivo non avresti.",
        "Cambia numero o data per guardare altri trade, o lascia il numero a 0 per pescarne uno a caso. "
        "Puoi confrontare orari e prezzi con il grafico M15 di IC Markets su TradingView. Poi vai alla schermata 8.")
    return fig
