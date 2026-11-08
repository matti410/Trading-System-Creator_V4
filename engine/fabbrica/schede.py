"""
Le schede della fabbrica (docs/82 P10 e §6, lavoro L5a): un .json e un .md per ogni strategia entrata in cassaforte.

    sc = componi_scheda(esito_ricerca, esito_cassaforte, id_strategia, mm=riassunto_mm)    # il dizionario del .json
    md, js = scrivi_scheda(sc, cartella)              # <cartella>/<id_strategia>.md e .json
    sc = leggi_scheda(js)
    trade = trade_da_scheda(sc, cartella_dati)        # {"in_sample", "cassaforte"}: gli stessi trade, al bit
    regole_in_parole(strategia, timeframe)            # le regole scritte dal testo di ogni blocco con i suoi valori

- La regola in parole viene dal testo di ogni blocco (TESTI_TRIGGER, TESTI_FILTRI, TESTI_USCITE), con i valori della
  strategia in ore e in barre del timeframe. Un collaudo controlla che ogni blocco della config standard abbia il testo
  per tutti e due i lati.
- Dal solo .json si ricostruisce la strategia (lato, blocchi, valori in barre: l'id deve tornare) e, con i dati del
  symbol, si riottengono i trade in-sample (ricerca + selezione) e in cassaforte, al bit (P10). Le impronte dei tre
  pezzi devono essere quelle della scheda. La cassaforte si rilegge solo per una strategia già entrata nel suo tratto.
- La scheda porta anche i blocchi tolti su quel timeframe, con il motivo (08/11), e l'esito delle regole della verifica
  dei trade (schermata 8 del Lab) quando la cella 6 del notebook è stata eseguita per quella strategia.
- In fondo al .md sempre la frase FRASE_FINALE (Mattia, 08/11).
"""
from __future__ import annotations

import json
import math
import os
import subprocess

from . import registro
from .blocchi import MINUTI_TIMEFRAME, MOTIVI_ESCLUSIONE
from .cache import ORE_FINESTRA_SOGLIE, barre_da_ore
from .valutatore import Strategia, id_strategia

FRASE_FINALE = "La scheda descrive cosa è successo sui dati; la decisione è tua."
VERSIONE_SCHEDA = 1
TOLTO_DALLA_CONFIG = "tolto dalla config"

__all__ = ["FRASE_FINALE", "componi_scheda", "esclusi_dalla_config", "leggi_scheda", "regole_in_parole",
           "scrivi_scheda", "strategia_da_scheda", "testo_md", "trade_da_scheda"]


# ------------------------------------------------------------------ durate in parole
def _numero(x: float) -> str:
    """Un numero all'italiana, senza zeri inutili: 2 -> «2», 2.5 -> «2,5», 0.25 -> «0,25»."""
    if float(x).is_integer():
        return f"{int(x)}"
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _il(perc) -> str:
    """L'articolo davanti a una percentuale: «il 90%», «l'80%», «l'11%»."""
    s = _numero(perc)
    return ("l'" if s.startswith("8") or s in ("1", "11", "18") else "il ") + s + "%"


def durata(barre: int, minuti: int) -> str:
    """Una finestra in parole: «12 ore (48 barre)», «45 minuti (3 barre)», «1 barra» se dura come la barra."""
    barre = int(barre)
    tot = barre * int(minuti)
    tempo = (("1 minuto" if tot == 1 else f"{tot} minuti") if tot < 60
             else ("1 ora" if tot == 60 else f"{_numero(tot / 60)} ore"))
    return f"{tempo} ({barre} {'barra' if barre == 1 else 'barre'})"


# ------------------------------------------------------------------ i testi dei blocchi
# Ogni testo è una funzione (valori, d, lato) -> frase; d(barre) = durata in parole sul timeframe; lato 1 o -1.
def _su(lato, a, b):
    return a if lato == 1 else b


TESTI_TRIGGER = {
    "E5": lambda v, d, l: ("la barra di due barre fa contiene tutta quella di una barra fa (inside bar) e il Close "
                           + _su(l, "supera il massimo", "scende sotto il minimo") + " della barra di due barre fa"),
    "E36": lambda v, d, l: ("sulla candela che finisce alle 16:30 di New York, il prezzo è "
                            + _su(l, "salito", "sceso") + " dalle 17:00 di New York del giorno prima alle 09:30 di oggi"),
    "E47": lambda v, d, l: ("sulla barra prima l'ATR di 70 minuti era sotto 0,8 volte la sua media dell'ultima ora, e "
                            "il Close " + _su(l, "supera il massimo", "scende sotto il minimo")
                            + " delle 3 ore fino alla barra prima (finestre in minuti, convertite nelle barre)"),
    "E49": lambda v, d, l: (_su(l, "nell'ultima ora il Low è sceso sotto l'ultimo minimo confermato (il Low più basso",
                                "nell'ultima ora l'High è salito sopra l'ultimo massimo confermato (l'High più alto")
                            + " fra 3 ore prima e 3 ore dopo, noto 3 ore dopo) e il Close è tornato "
                            + _su(l, "sopra", "sotto")),
    "E51": lambda v, d, l: ("il prezzo è " + _su(l, "sceso", "salito") + " nelle ultime 5 ore più della deviazione "
                            "standard dei movimenti a 5 ore delle ultime 100 ore, e il volume medio delle ultime 5 ore è "
                            "sotto quello delle 5 ore prima"),
    "RSI_RIENTRO": lambda v, d, l: (f"l'RSI di {d(v['periodo_barre'])} "
                                    + _su(l, f"risale sopra {_numero(v['soglia'])} da sotto",
                                          f"scende sotto {_numero(100 - v['soglia'])} da sopra")),
    "DONCHIAN": lambda v, d, l: ("il Close " + _su(l, "supera il massimo degli High", "scende sotto il minimo dei Low")
                                 + f" delle {d(v['canale_barre'])} precedenti"),
}
TESTI_FILTRI = {
    "F2_MID_VOLATILITY": lambda v, d, l: (f"l'ATR di {d(14)} non è sopra il 75° percentile dei suoi valori delle "
                                          f"ultime {d(500)}"),
    "F3_VOLUME_ABOVE_AVG": lambda v, d, l: f"il volume della barra è sopra la sua media delle ultime {d(20)}",
    "TREND_CONTEXT": lambda v, d, l: f"il Close è {_su(l, 'sopra', 'sotto')} la media esponenziale di {d(50)}",
    "F25_CHOP_TREND": lambda v, d, l: (f"il mercato è in tendenza: il Choppiness Index di {d(14)} è sceso sotto il 25° "
                                       f"percentile delle ultime {d(500)} e non è ancora risalito sopra il 50°"),
    "F20_SESSION_OVERLAP": lambda v, d, l: ("Londra e New York sono aperte insieme (dalle 08:00 alle 17:00, ora locale "
                                            "di ciascuna)"),
    "ADX": lambda v, d, l: f"l'ADX di {d(v['periodo_barre'])} è sopra {_numero(v['soglia'])}",
    "ATR_RELATIVO": lambda v, d, l: (f"l'ATR di {d(v['breve_barre'])} diviso l'ATR di {d(v['lungo_barre'])} è sopra "
                                     f"{_numero(v['soglia'])}"),
}
TESTI_USCITE = {                       # la regola d'uscita; None = nessuna regola oltre a durata, stop e target
    "X0": lambda l: None,
    "X3": lambda l: _su(l, "il MACD scende sotto la sua signal", "il MACD sale sopra la sua signal"),
    "X1": lambda l: _su(l, "il ciclo dominante gira al ribasso", "il ciclo dominante gira al rialzo"),
}


def regole_in_parole(strategia: Strategia, timeframe: str) -> dict:
    """
    {"ingresso", "filtri", "uscita", "righe"}: le regole della strategia in parole, dal testo di ogni blocco con i
    suoi valori. `righe` sono le frasi della scheda, nell'ordine.
    """
    minuti = MINUTI_TIMEFRAME[timeframe]

    def d(barre):
        return durata(barre, minuti)

    lato = strategia.lato
    nome_lato = "long" if lato == 1 else "short"
    for nome, testi in [(strategia.trigger, TESTI_TRIGGER), *[(f, TESTI_FILTRI) for f in strategia.filtri],
                        (strategia.uscita, TESTI_USCITE)]:
        if nome not in testi:
            raise ValueError(f"il blocco {nome} non ha il testo in parole (schede.py): la scheda non si scrive.")
    ingresso = TESTI_TRIGGER[strategia.trigger](strategia.valori_di(strategia.trigger), d, lato)
    filtri = [TESTI_FILTRI[f](strategia.valori_di(f), d, lato) for f in strategia.filtri]
    u = strategia.valori_di(strategia.uscita)
    n = int(u["durata_barre"])
    finestra = d(barre_da_ore(ORE_FINESTRA_SOGLIE, minuti))
    modi = [f"dopo {d(n)}"]
    regola = TESTI_USCITE[strategia.uscita](lato)
    if regola:
        modi.append(f"quando {regola}")
    if u.get("perc_stop"):
        modi.append(f"allo stop: la distanza che contiene {_il(u['perc_stop'])} delle escursioni contrarie dei "
                    f"trade di {d(n)} delle ultime {finestra}")
    if u.get("target"):
        modi.append(f"al target: la distanza che contiene {_il(u['target'])} delle escursioni favorevoli dei "
                    f"trade di {d(n)} delle ultime {finestra}")
    uscita = ", oppure ".join(modi) + ", quello che arriva prima" + ("" if u.get("target") else "; target spento")
    righe = [f"Entra {nome_lato} all'apertura della barra dopo quella in cui {ingresso}."]
    righe += ([f"Solo se {' e se '.join(filtri)}."] if filtri else ["Nessun filtro."])
    righe.append(f"Esce {uscita}.")
    return {"ingresso": ingresso, "filtri": filtri, "uscita": uscita, "righe": righe}


# ------------------------------------------------------------------ i blocchi tolti
def esclusi_dalla_config(config: dict) -> list[dict]:
    """
    I blocchi di P-L2 che non sono nella config, con il motivo (08/11): quelli tolti sul timeframe hanno il motivo di
    blocchi.MOTIVI_ESCLUSIONE (limite logico, approssimazione esclusa per scelta, escluso solo dall'elenco); gli altri
    sono «tolto dalla config». Sulla config standard è config.blocchi_esclusi(timeframe).
    """
    from .config import BLOCCHI_STANDARD
    tf = config["timeframe"]
    out = []
    for nome in BLOCCHI_STANDARD:
        if nome in config["blocchi"]:
            continue
        tipo, motivo = MOTIVI_ESCLUSIONE.get((nome, tf), (TOLTO_DALLA_CONFIG, "non è nella config di questa ricerca"))
        out.append({"blocco": nome, "tipo": tipo, "motivo": motivo})
    return out


# ------------------------------------------------------------------ la scheda
def _pulito(x):
    """Per il .json: numeri di numpy in numeri di Python, NaN e infiniti in None, tabelle in liste di righe."""
    import numpy as np
    import pandas as pd
    if isinstance(x, pd.DataFrame):
        return [_pulito(r) for r in x.to_dict("records")]
    if isinstance(x, dict):
        return {str(k): _pulito(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_pulito(v) for v in x]
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return float(x) if math.isfinite(float(x)) else None
    if isinstance(x, pd.Timestamp):
        return x.isoformat()
    return x


def commit_software() -> str:
    """Il commit del repo da cui gira il codice; «sconosciuto» se git non c'è (per esempio una copia senza .git)."""
    radice = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=radice, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or "sconosciuto"
    except (OSError, subprocess.SubprocessError):
        return "sconosciuto"


def _riga(tabella, colonna: str, valore) -> dict | None:
    if tabella is None or not len(tabella) or colonna not in tabella.columns:
        return None
    r = tabella[tabella[colonna] == valore]
    return r.iloc[0].to_dict() if len(r) else None


def _altopiano(cartella_ricerca: str, teoria: str, id_strat: str) -> dict | None:
    """Il giudizio dell'altopiano della strategia scelta (passo_2.jsonl della ricerca)."""
    from .ricerca import FILE_PASSO_2, _leggi_jsonl
    for r in _leggi_jsonl(os.path.join(cartella_ricerca, FILE_PASSO_2)):
        if r["teoria"] == teoria:
            for g in r["altopiano"]:
                if g.get("candidata") == id_strat:
                    return g
    return None


def componi_scheda(esito_ricerca, esito_cas, id_strat: str, mm: dict | None = None) -> dict:
    """
    Il contenuto del .json di §6 per una strategia entrata in cassaforte. `esito_ricerca` = ricerca.lancia (finita),
    `esito_cas` = cassaforte.entra o esito_cassaforte, `mm` = il riassunto salvato dalla cella 6 (money management,
    stress test, verifica dei trade), None se la cella 6 non è stata eseguita per questa strategia.
    """
    from .config import impronta_config
    from .dati import impronta_pezzo
    from .selezione import strategia_da_riga
    if id_strat not in esito_cas.trade:
        raise ValueError(f"la strategia {id_strat} non è entrata in cassaforte: niente scheda.")
    config = esito_cas.config
    symbol, timeframe = config["symbol"], config["timeframe"]
    ingresso = next(e for e in esito_cas.ingressi if any(x["id_strategia"] == id_strat for x in e["strategie"]))
    riga = next(x for x in ingresso["strategie"] if x["id_strategia"] == id_strat)
    st = strategia_da_riga(riga, symbol, timeframe)
    teoria = st.teoria_id
    p = esito_cas.pezzo
    impronte = {**esito_cas.pezzi.impronte, "cassaforte": impronta_pezzo(p.df.iloc[p.inizio:])}

    p1 = _riga(esito_ricerca.passo_1, "teoria", teoria) or {}
    p2 = _riga(esito_ricerca.passo_2, "teoria", teoria) or {}
    sel = _riga(esito_ricerca.selezione.tabella, "id_strategia", id_strat) or {}
    cas = _riga(esito_cas.tabella, "id_strategia", id_strat) or {}
    esiti = [
        {"passo": "passo 1", "pezzo": "ricerca", "trade": None, "ev_bp": None, "t": p1.get("t"), "dd_bp": None,
         "condizione": "qualità 1", "esito": "tenuta" if p1.get("tenuta") else "fuori",
         "motivo": f"la migliore della teoria al passo 1 ({p1.get('prove')} prove)"},
        {"passo": "zoom e altopiano", "pezzo": "ricerca", "trade": p2.get("trade"), "ev_bp": p2.get("ev_bp"),
         "t": p2.get("t"), "dd_bp": None, "condizione": "qualità 1 e altopiano", "esito": p2.get("esito"),
         "motivo": p2.get("motivo") or f"{p2.get('prove_zoom')} prove di zoom, {p2.get('prove_altopiano')} di altopiano"},
        {"passo": "selezione", "pezzo": "selezione", "trade": sel.get("trade"), "ev_bp": sel.get("ev_bp"),
         "t": sel.get("t"), "dd_bp": sel.get("dd_bp"), "condizione": "qualità 2 e test individuale",
         "esito": sel.get("esito"), "motivo": sel.get("motivo") or sel.get("motivo_q2") or ""},
        {"passo": "cassaforte", "pezzo": "cassaforte", "trade": cas.get("trade"), "ev_bp": cas.get("ev_bp"),
         "t": cas.get("t"), "dd_bp": cas.get("dd_bp"), "condizione": "test individuale", "esito": cas.get("esito"),
         "motivo": cas.get("motivo") or ""},
    ]
    soglia = cas.get("soglia_test", sel.get("soglia_test"))
    sc = {
        "versione_scheda": VERSIONE_SCHEDA,
        "id_strategia": id_strat, "id_ricerca": esito_ricerca.id_ricerca, "impronta_config": impronta_config(config),
        "impronte_dati": impronte, "symbol": symbol, "timeframe": timeframe,
        "lato": "long" if st.lato == 1 else "short",
        "blocchi": [{"nome": n, "tipo": _tipo(n), "valori": st.valori_di(n)} for n in st.blocchi],
        "uscita": {"nome": st.uscita, **st.valori_di(st.uscita)},
        "regole": regole_in_parole(st, timeframe)["righe"],
        "strategia": {**st.come_dict(), "teoria": teoria},
        "config_strategia": {"symbol": symbol, "timeframe": timeframe, "confini": dict(config["confini"]),
                             "blocchi": {n: config["blocchi"][n] for n in st.blocchi},
                             "test_individuale": dict(config["test_individuale"])},
        "esiti": esiti,
        "altopiano": _altopiano(esito_ricerca.cartella, teoria, p2.get("id_strategia") or id_strat),
        "test_individuale": {"soglia": soglia, "selezione": sel.get("t"), "cassaforte": cas.get("t")},
        "prove": {"questa_ricerca": esito_ricerca.conto.get("questa_ricerca"), "asset": esito_cas.conto.get("asset"),
                  "soglia_da_leggere": esito_cas.conto.get("soglia_da_leggere")},
        "cassaforte": {"data": ingresso.get("quando"), "tratto": esito_cas.tratto, "esito": cas.get("esito"),
                       "entrate_nel_tratto": esito_cas.conto.get("entrate_nel_tratto")},
        "blocchi_esclusi": esclusi_dalla_config(config),
        "mm": (mm or {}).get("mm"), "stress": (mm or {}).get("stress"), "verifica": (mm or {}).get("verifica"),
        "parametri_mm": (mm or {}).get("parametri"),
        "software": commit_software(),
    }
    return _pulito(sc)


def _tipo(nome: str) -> str:
    if nome in TESTI_TRIGGER:
        return "trigger"
    return "uscita" if nome in TESTI_USCITE else "filtro"


# ------------------------------------------------------------------ il testo .md
def _f(x, decimali: int = 2) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    if isinstance(x, bool):
        return "sì" if x else "no"
    if isinstance(x, int):
        return f"{x:,}".replace(",", ".")
    if isinstance(x, float):
        return f"{x:,.{decimali}f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return str(x)


def _tabella_md(righe: list[dict], colonne: list[str] | None = None) -> list[str]:
    if not righe:
        return ["(nessuna riga)"]
    colonne = colonne or list(righe[0])
    out = ["| " + " | ".join(colonne) + " |", "|" + "---|" * len(colonne)]
    for r in righe:
        out.append("| " + " | ".join(_f(r.get(c)).replace("|", "/") for c in colonne) + " |")
    return out


def _quando(iso) -> str:
    """Una data ISO del registro o della scheda in «27/07/2024 08:00 UTC»."""
    if not iso:
        return "—"
    import pandas as pd
    t = pd.Timestamp(iso)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return t.strftime("%d/%m/%Y %H:%M") + " UTC"


def testo_md(sc: dict) -> str:
    """La scheda in parole (§6): Regole · Da dove viene · Il cammino · Da leggere · Verifica, MM e stress test ·
    Blocchi tolti; in fondo la frase finale."""
    t = sc["test_individuale"]
    pr, cas = sc["prove"], sc["cassaforte"]
    da, a = cas["tratto"]["da"], cas["tratto"]["a"]
    righe = [f"# Strategia {sc['id_strategia']} · {sc['symbol']} {sc['timeframe']} · {sc['lato']}", "",
             "## Regole", *[f"- {r}" for r in sc["regole"]], "",
             "## Da dove viene",
             f"- Ricerca {sc['id_ricerca']}, config {sc['impronta_config'][:12]}.",
             f"- Dati: dal {_quando(sc['config_strategia']['confini']['inizio'])}; ricerca "
             f"{_numero(float(sc['config_strategia']['confini']['ricerca_ore']))} ore, selezione "
             f"{_numero(float(sc['config_strategia']['confini']['selezione_ore']))} ore, cassaforte dal {_quando(da)} "
             f"al {_quando(a)}.",
             f"- Software: commit {sc['software']}.", "",
             "## Il cammino",
             *_tabella_md(sc["esiti"], ["passo", "pezzo", "trade", "ev_bp", "t", "dd_bp", "esito", "motivo"]),
             "",
             f"Decide il test individuale: t contro {_f(t['soglia'])}. In selezione t {_f(t['selezione'])}, in "
             f"cassaforte t {_f(t['cassaforte'])}.", "",
             "## Da leggere",
             f"- Prove di questa ricerca: {_f(pr['questa_ricerca'])}; su questo asset: {_f(pr['asset'])}; soglia "
             f"corrispondente: {_f(pr['soglia_da_leggere'])}.",
             f"- Strategie entrate in questo tratto di cassaforte: {_f(cas['entrate_nel_tratto'])} (entrata il "
             f"{_quando(cas['data'])}).", ""]
    righe.append("## Verifica dei trade")
    if sc.get("verifica"):
        righe += _tabella_md(sc["verifica"]["regole"])
    else:
        righe.append("Non calcolata: esegui la 6 per questa strategia.")
    righe += ["", "## Money management e stress test"]
    if sc.get("mm"):
        par = sc.get("parametri_mm") or {}
        righe += [f"Capitale {_f(par.get('capitale'))} $, drawdown massimo {_f(par.get('drawdown_max_pct'))} %, "
                  f"{_numero(par.get('anni') or 0)} anni, modello «{sc['mm'].get('modello')}», leva "
                  f"{_numero(par['leva']) if par.get('leva') else 'la massima del symbol'}.",
                  f"Rischio a ogni trade: {_f((sc['mm'].get('percentuale') or 0) * 100)} %. "
                  f"{sc['mm'].get('deciso') or ''}", ""]
        righe += _tabella_md(sc["mm"].get("sintesi") or [])
        if sc.get("stress"):
            righe += ["", f"Stress test (drawdown massimo {_f(sc['stress'].get('drawdown_max_usd'))} $, in "
                          f"{sc['stress'].get('unita')}):", ""]
            righe += _tabella_md(sc["stress"].get("controllo") or [])
    else:
        righe.append("Non calcolati: esegui la 6 per questa strategia.")
    righe += ["", "## Blocchi tolti su questo timeframe"]
    if sc["blocchi_esclusi"]:
        righe += [f"- {e['blocco']} ({e['tipo']}): {e['motivo']}." for e in sc["blocchi_esclusi"]]
    else:
        righe.append("Nessuno: c'erano tutti i blocchi della lista.")
    righe += ["", FRASE_FINALE, ""]
    return "\n".join(righe)


# ------------------------------------------------------------------ scrivere e leggere
def scrivi_scheda(sc: dict, cartella) -> tuple[str, str]:
    """Scrive <cartella>/<id_strategia>.md e .json (riscritti se ci sono già: la scheda viene dai calcoli)."""
    os.makedirs(str(cartella), exist_ok=True)
    base = os.path.join(str(cartella), sc["id_strategia"])
    testo_json = json.dumps(sc, ensure_ascii=False, indent=2, sort_keys=False, allow_nan=False,
                            default=registro.nativo)
    for percorso, testo in ((base + ".json", testo_json + "\n"), (base + ".md", testo_md(sc))):
        with open(percorso + ".tmp", "w", encoding="utf-8") as f:
            f.write(testo)
        os.replace(percorso + ".tmp", percorso)
    return base + ".md", base + ".json"


def leggi_scheda(percorso) -> dict:
    """Il dizionario di una scheda .json (o del .json accanto a un .md)."""
    percorso = str(percorso)
    if percorso.endswith(".md"):
        percorso = percorso[:-3] + ".json"
    with open(percorso, encoding="utf-8") as f:
        sc = json.load(f)
    if sc.get("versione_scheda") != VERSIONE_SCHEDA:
        raise ValueError(f"{percorso}: versione della scheda {sc.get('versione_scheda')!r}, attesa {VERSIONE_SCHEDA}.")
    return sc


def strategia_da_scheda(sc: dict) -> Strategia:
    """La strategia dalla sola scheda: si ferma se l'id non torna dai valori scritti."""
    s = sc["strategia"]
    st = Strategia(int(s["lato"]), s["trigger"], tuple(s["filtri"]), s["uscita"],
                   tuple((n, tuple(sorted(s["valori"].get(n, {}).items()))) for n in (s["trigger"], *s["filtri"],
                                                                                        s["uscita"])))
    if id_strategia(st, sc["symbol"], sc["timeframe"]) != sc["id_strategia"]:
        raise ValueError(f"la scheda {sc['id_strategia']}: la strategia non torna dai suoi valori.")
    return st


def trade_da_scheda(sc: dict, cartella_dati) -> dict:
    """
    I trade della strategia rifatti dalla sola scheda (P10): {"in_sample": trade su ricerca + selezione,
    "cassaforte": trade sulla cassaforte}. Servono i CSV del symbol; si ferma se le impronte dei pezzi non sono quelle
    della scheda o se la strategia non è entrata nel tratto di cassaforte della scheda.
    """
    from .blocchi import blocchi_da_config
    from .cassaforte import trade_entrata
    from .dati import APERTI, Confini, carica_pezzi
    from .sessione import in_sample
    st = strategia_da_scheda(sc)
    config = sc["config_strategia"]
    riga = {"teoria": st.teoria_id, "valori": {n: dict(v) for n, v in st.valori}, "id_strategia": sc["id_strategia"]}
    trade_cas, impronte = trade_entrata(cartella_dati, config, riga, sc["impronte_dati"])
    pezzi = carica_pezzi(config["symbol"], config["timeframe"], Confini.da_config(config["confini"]), cartella_dati)
    if {k: pezzi.impronte[k] for k in APERTI} != {k: impronte[k] for k in APERTI}:
        raise ValueError("i dati sono cambiati fra due letture: i trade non si rifanno.")
    ins = in_sample(config, pezzi, st, {b.nome: b for b in blocchi_da_config(config)})
    return {"in_sample": ins.trades, "cassaforte": trade_cas}


# controlli di coerenza dei testi, usati dai collaudi
def blocchi_senza_testo() -> list[str]:
    """I blocchi di P-L2 senza testo in parole (deve essere vuota)."""
    from .config import BLOCCHI_STANDARD
    testi = {**TESTI_TRIGGER, **TESTI_FILTRI, **TESTI_USCITE}
    return [n for n in BLOCCHI_STANDARD if n not in testi]

