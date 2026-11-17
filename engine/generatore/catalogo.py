"""
Il catalogo generato (docs/83 §4, §6).

    cat = genera_catalogo(n=80)                    # le prime 80 ricette diverse, nell'ordine fisso
    salva_catalogo(cat)                            # dati_catalogo/generati_v1.json
    cat = carica_catalogo()                        # dal file
    lunghi, corti = trigger_del_catalogo(cat)      # {nome: TriggerGenerato}, come TRIGGER_LONG / TRIGGER_SHORT
    registra_trigger_generati(cat)                 # nel motore (engine.registry), come registra_trigger_long
    segnala_degeneri(df, cat)                      # verifica_degenerazione sui soli trigger generati

Come si tolgono le ricette uguali (docs/83 §4.2):
- per scrittura: le regole di ricette._regola_scrittura (A×B = B×A, A−B = −(B−A), abs di una serie mai negativa...);
- nei fatti: ogni ricetta si calcola sul DATASET SINTETICO FISSO (`dataset_sintetico`, mai dati veri) e se l'insieme
  dei suoi trigger e' identico, barra per barra, a quello di una ricetta gia' tenuta, resta la prima (la piu'
  corta, perche' l'ordine va dalle piu' semplici). Una ricetta che sul sintetico non scatta mai e' uguale alla
  ricetta vuota: si toglie anche lei, contata a parte.
Il tetto N (`n`) lo sceglie Mattia dopo la misura dei tempi (docs/83 §7): qui non c'e' un valore di base.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import ricette as R
from . import trigger as T

VERSIONE = 1
CARTELLA = Path(__file__).resolve().parents[2] / "dati_catalogo"
SEME_SINTETICO = 83
BARRE_SINTETICO = 6000


def percorso_catalogo(versione: int = VERSIONE) -> Path:
    return CARTELLA / f"generati_v{versione}.json"


# ------------------------------------------------------------ sintetico ----
def dataset_sintetico(barre: int = BARRE_SINTETICO, seme: int = SEME_SINTETICO) -> pd.DataFrame:
    """
    Il mercato inventato, fisso, su cui si confrontano le ricette (mai dati veri). Barre da 15 minuti dal 2/1/2020 UTC:
    volatilita' a grappoli, code grasse, volume legato al movimento, qualche barra piatta (High = Low).
    """
    rng = np.random.default_rng(seme)
    idx = pd.date_range("2020-01-02", periods=barre, freq="15min", tz="UTC")
    logvol = np.zeros(barre)
    for i in range(1, barre):
        logvol[i] = 0.98 * logvol[i - 1] + 0.15 * rng.standard_normal()
    sigma = 0.002 * np.exp(logvol)
    r = sigma * rng.standard_t(4, barre) / np.sqrt(2.0)
    piatte = rng.random(barre) < 0.005
    r[piatte] = 0.0
    close = 100.0 * np.exp(np.cumsum(r))
    open_ = np.r_[100.0, close[:-1]] * np.exp(0.0001 * rng.standard_normal(barre) * ~piatte)
    open_[piatte] = close[piatte]
    alto = np.maximum(open_, close) * np.exp(np.abs(rng.standard_normal(barre)) * sigma * 0.6 * ~piatte)
    basso = np.minimum(open_, close) * np.exp(-np.abs(rng.standard_normal(barre)) * sigma * 0.6 * ~piatte)
    volume = 1000.0 * np.exp(0.4 * rng.standard_normal(barre) + 0.8 * logvol + 0.3 * np.abs(r) / sigma)
    return pd.DataFrame({"Open": open_, "High": alto, "Low": basso, "Close": close, "Volume": volume}, index=idx)


def _firma(e: tuple, df: pd.DataFrame, memo: dict) -> tuple[frozenset, bool, int]:
    """(insieme delle impronte dei trigger, indicatore con segno, eventi totali) della ricetta sul df."""
    x = R.calcola(e, df, memo)
    con_segno = T.ha_segno(x)
    impronte, eventi = set(), 0
    for nome in T.livelli_ricetta(con_segno):
        liv = T.livello(x, nome)
        for verso in T.VERSI:
            s = T.attraversa(x, liv, verso).to_numpy()
            eventi += int(s.sum())
            impronte.add(hashlib.sha1(np.packbits(s).tobytes()).hexdigest())
    return frozenset(impronte), con_segno, eventi


# ------------------------------------------------------------- generatore ----
def voce_ricetta(id_r: str, e: tuple, con_segno: bool | None = None) -> dict:
    """La voce di catalogo di una ricetta, con i suoi trigger (con_segno None: si decide sul dataset sintetico)."""
    if con_segno is None:
        con_segno = T.ha_segno(R.calcola(e, dataset_sintetico()))
    trig = [{"nome": T.nome_trigger(id_r, liv, verso, lato), "lato": "long" if lato == 1 else "short",
             "livello": liv, "verso": verso}
            for lato in (1, -1) for liv in T.livelli_ricetta(con_segno) for verso in T.VERSI]
    return {"id": id_r, "ricetta": R.testo(e), "albero": e, "operazioni": R.n_operazioni(e),
            "ingredienti": [i for i in R.INGREDIENTI + (R.TP,) if i in R.ingredienti(e)],
            "finestre": R.finestre(e), "famiglia": R.famiglia(e), "con_segno": con_segno, "trigger": trig}


def genera_catalogo(n: int, versione: int = VERSIONE, max_operazioni: int = R.MAX_OPERAZIONI,
                    degeneri: bool = True, verbose: bool = False) -> dict:
    """
    Il catalogo con le prime `n` ricette diverse nell'ordine fisso (docs/83 §4). Non guarda nessun dato vero:
    due lanci danno lo stesso catalogo. Con degeneri=True ogni trigger porta l'esito di verifica_degenerazione sul
    dataset sintetico (solo da leggere: i degeneri restano, segnalati).
    """
    if isinstance(n, bool) or not isinstance(n, (int, np.integer)) or n < 1:
        raise ValueError(f"il tetto n deve essere un intero >= 1, non {n!r}")
    df = dataset_sintetico()
    memo: dict = {}
    viste: dict[frozenset, str] = {}
    conti = {"generate": 0, "tolte_scrittura": 0, "tolte_uguali": 0, "tolte_senza_trigger": 0}
    ricette, uguali = [], []
    for e, motivo in R.elenca(max_operazioni):
        if not R.rispetta_vincolo(e):
            continue
        conti["generate"] += 1
        if motivo is not None:
            conti["tolte_scrittura"] += 1
            continue
        firma, con_segno, eventi = _firma(e, df, memo)
        if eventi == 0:
            conti["tolte_senza_trigger"] += 1
            continue
        if firma in viste:
            conti["tolte_uguali"] += 1
            uguali.append({"ricetta": R.testo(e), "uguale_a": viste[firma]})
            continue
        id_r = f"G{len(ricette) + 1:04d}"
        viste[firma] = id_r
        ricette.append(voce_ricetta(id_r, e, con_segno))
        if verbose and len(ricette) % 50 == 0:
            print(f"[generatore] {len(ricette)} ricette tenute su {conti['generate']} generate", flush=True)
        if len(ricette) >= n:
            break
    conti["tenute"] = len(ricette)
    conti["trigger"] = sum(len(r["trigger"]) for r in ricette)
    cat = {
        "versione": versione,
        "tetto_ricette": int(n),
        "parametri": {"max_operazioni": max_operazioni, "finestre": list(R.FINESTRE),
                      "mediana_volume_barre": R.MEDIANA_VOLUME, "media_barre": T.MEDIA_BARRE,
                      "percentili": list(T.PERCENTILI), "percentili_barre": T.PERCENTILI_BARRE,
                      "sintetico": {"seme": SEME_SINTETICO, "barre": BARRE_SINTETICO}},
        "conteggi": conti,
        "ricette": ricette,
        "tolte_uguali": uguali,
    }
    if degeneri and ricette:
        esiti = segnala_degeneri(df, cat)
        per_nome = dict(zip(esiti["nome"], esiti["esito"]))
        for r in ricette:
            for t in r["trigger"]:
                t["esito_sintetico"] = per_nome.get(t["nome"], "")
        conti["trigger_degeneri_sintetico"] = int((esiti["esito"] != "OK").sum())
    return cat


# ------------------------------------------------------------ file e uso ----
def _in_json(x):
    if isinstance(x, tuple):
        return [_in_json(y) for y in x]
    if isinstance(x, list):
        return [_in_json(y) for y in x]
    if isinstance(x, dict):
        return {k: _in_json(v) for k, v in x.items()}
    return x


def salva_catalogo(cat: dict, percorso: str | Path | None = None) -> Path:
    """Scrive il catalogo in JSON (dati_catalogo/generati_v<versione>.json se il percorso non e' dato)."""
    p = Path(percorso) if percorso is not None else percorso_catalogo(cat["versione"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_in_json(cat), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return p


def carica_catalogo(percorso: str | Path | None = None, versione: int = VERSIONE) -> dict:
    p = Path(percorso) if percorso is not None else percorso_catalogo(versione)
    if not p.exists():
        raise FileNotFoundError(f"{p} non c'e': crealo con «python -m engine.generatore --n N» (docs/83 §6)")
    cat = json.loads(p.read_text(encoding="utf-8"))
    for r in cat["ricette"]:
        r["albero"] = R.da_json(r["albero"])
    return cat


def trigger_del_catalogo(cat: dict) -> tuple[dict, dict]:
    """({nome: trigger long}, {nome: trigger short}), nell'ordine del catalogo, come TRIGGER_LONG e TRIGGER_SHORT."""
    lunghi, corti = {}, {}
    for r in cat["ricette"]:
        albero = r["albero"] if isinstance(r["albero"], tuple) else R.da_json(r["albero"])
        for t in r["trigger"]:
            lato = 1 if t["lato"] == "long" else -1
            f = T.TriggerGenerato(t["nome"], albero, t["livello"], t["verso"], lato, r["famiglia"])
            (lunghi if lato == 1 else corti)[t["nome"]] = f
    return lunghi, corti


def famiglie_del_catalogo(cat: dict) -> dict:
    """{nome del trigger: famiglia dichiarata}."""
    return {t["nome"]: r["famiglia"] for r in cat["ricette"] for t in r["trigger"]}


def registra_trigger_generati(cat: dict) -> int:
    """Registra i trigger generati nel motore (engine.registry); salta quelli gia' registrati. Quanti ne ha aggiunti."""
    from engine import registry as reg
    gia = set(reg.list_entries())
    lunghi, corti = trigger_del_catalogo(cat)
    nuovi = 0
    for lato, gruppo in ((1, lunghi), (-1, corti)):
        for nome, f in gruppo.items():
            if nome not in gia:
                reg.register_entry(nome, direction=lato)(f)
                nuovi += 1
    return nuovi


@contextlib.contextmanager
def registro_solo_generati(cat: dict):
    """Dentro il blocco il registro del motore contiene SOLO i trigger del catalogo; poi torna com'era."""
    from engine import registry as reg
    nomi = ("_ENTRY_REGISTRY", "_EXIT_REGISTRY", "_FILTER_REGISTRY", "_BIDIR_ENTRY_REGISTRY", "_ENTRY_DIRECTION",
            "_FILTER_DIRECTION", "_FILTER_PAIR", "_EXIT_DIRECTION", "_EXIT_PAIR")
    copia = {k: dict(getattr(reg, k)) for k in nomi}
    reg.clear_registry()
    try:
        registra_trigger_generati(cat)
        yield
    finally:
        reg.clear_registry()
        for k in nomi:
            getattr(reg, k).update(copia[k])


def segnala_degeneri(df: pd.DataFrame, cat: dict, **opzioni) -> pd.DataFrame:
    """
    verifica_degenerazione (engine/collaudo_catalogo.py) sui soli trigger del catalogo, sul df dato (OHLCV).
    Una riga per trigger con l'esito (OK, SEMPRE_FALSA, RARA, QUASI_SEMPRE_VERA, STATO...). Non toglie niente.
    """
    import contextlib as _c
    import io

    from engine.collaudo_catalogo import verifica_degenerazione
    with registro_solo_generati(cat), _c.redirect_stdout(io.StringIO()):
        return verifica_degenerazione(df, verbose=False, **opzioni)


def calcola_trigger(df: pd.DataFrame, trigger: dict) -> pd.DataFrame:
    """Tutti i trigger dati ({nome: TriggerGenerato}) sul df: un DataFrame booleano, una colonna per trigger."""
    return pd.DataFrame({nome: f(df) for nome, f in trigger.items()}, index=df.index)
