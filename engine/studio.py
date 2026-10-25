"""
Lo studio: il confine unico dell'in-sample, l'impronta e i giornali (26/10/2026, docs/70).

A COSA SERVE
------------
Fino al 25/10 il confine fra in-sample e out-of-sample era l'80% delle barre
del CSV: ogni aggiornamento lo spostava in avanti, e barre gia' guardate
come out-of-sample diventavano in-sample senza che nessuno lo dicesse. E il
registro del dataset (H provati, conto delle prove, diario
dell'out-of-sample, risalite; docs/68 §9.1) si azzerava al riavvio.

Ora c'e' uno STUDIO, una cartella accanto ai dati:

    <DATI_DIR>/studio/
        confine.json                     il confine unico: uno solo per tutti gli exchange,
                                         le monete e i timeframe (decisione di Mattia del
                                         25/10: le crypto si muovono insieme). Lo fissa il
                                         primo dataset aperto, all'80% delle sue barre.
        <SYMBOL>_<TF>/impronta.json      l'impronta dell'in-sample del dataset
        <SYMBOL>_<TF>/giornale_<macchina>.jsonl
                                         le voci del registro, una riga per voce, SOLO IN
                                         AGGIUNTA, un file per macchina (pc, colab): con
                                         Google Drive per desktop PC e Colab non scrivono
                                         mai lo stesso file (docs/70 §4)
        archivio/                        gli studi chiusi dal reset

    entra(cartella, symbol, timeframe, df, macchina)    -> Ingresso: il confine (lo apre
        se non c'e', solo sul PC), df_is e df_oos al confine, l'impronta controllata
    aggiungi_voce(...) / ricostruisci(...)              il registro su file
    reset(cartella, campo, symbol, timeframe, df, macchina)
                                                        il confine ricalcolato a richiesta,
                                                        con la data di oggi nel campo (§5)

Regola del confine (docs/70 §2.1): un istante, la FINE dell'ultima barra
in-sample. In-sample = le barre che si chiudono entro il confine.

Modulo ADDITIVO: non modifica nessun file esistente dell'engine.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import registro_dataset as _rd
from .splitting import confine_da_quota, split_al_confine

CARTELLA = "studio"
ARCHIVIO = "archivio"
VERSIONE = 1
SOGLIA_IS_CORTO = 0.5       # sotto, l'in-sample del dataset e' corto: si avvisa (§2.2)
SOGLIA_RESET = 0.30         # oltre, si suggerisce il reset: solo un avviso (§12.3, decisione di Mattia)
COLONNE = ["Open", "High", "Low", "Close", "Volume"]
_MACCHINA = re.compile(r"^[a-z0-9_-]{1,40}$")
_GIORNALE = re.compile(r"^giornale_([a-z0-9_-]{1,40})\.jsonl$")

MESSAGGIO_COLAB = (
    "Su Drive non c'è lo studio (studio/confine.json). Il confine dell'in-sample sta lì: senza, Colab "
    "calcolerebbe un confine suo, diverso da quello del PC. Apri prima lo studio sul PC (schermata 1); con "
    "Drive per desktop arriva qui da solo, altrimenti carica la cartella dati/studio/ in "
    "Il mio Drive/Trading-System-Creator_V4/dati/.")


# ========================================================================
# Cartelle, nomi, scrittura sicura
# ========================================================================

def cartella_studio(cartella_dati) -> Path:
    return Path(cartella_dati) / CARTELLA


def nome_dataset(symbol: str, timeframe: str) -> str:
    return f"{str(symbol).upper()}_{str(timeframe).upper()}"


def passo(timeframe: str) -> pd.Timedelta:
    """La durata di una barra: M5, M15, M30, H1, H4 (anche M1)."""
    tf = str(timeframe).upper()
    if tf.startswith("M") and tf[1:].isdigit():
        return pd.Timedelta(minutes=int(tf[1:]))
    if tf.startswith("H") and tf[1:].isdigit():
        return pd.Timedelta(hours=int(tf[1:]))
    raise ValueError(f"Timeframe {timeframe!r} non previsto.")


def _controlla_macchina(macchina: str) -> str:
    if not _MACCHINA.match(str(macchina)):
        raise ValueError(f"Nome della macchina {macchina!r} non valido: minuscole, cifre, - e _ (es. pc, colab).")
    return str(macchina)


def _utc(t) -> pd.Timestamp:
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _adesso(adesso=None) -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC") if adesso is None else _utc(adesso)


def scrivi_sicuro(percorso, testo: str) -> None:
    """
    Scrive `testo` in `percorso` senza mai lasciare un file a meta': prima un
    file temporaneo accanto, poi lo si mette al posto del vecchio (os.replace).
    Se qualcosa va storto, il file di prima resta com'era.
    """
    percorso = Path(percorso)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    tmp = percorso.with_name(percorso.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(testo)
        os.replace(tmp, percorso)
    finally:
        if tmp.exists():
            tmp.unlink()


def _json(oggetto) -> str:
    return json.dumps(_rd.normale(oggetto), ensure_ascii=False, indent=2) + "\n"


# ========================================================================
# Il confine unico
# ========================================================================

def leggi_confine(cartella_dati) -> dict | None:
    """Il contenuto di studio/confine.json, o None se lo studio non c'e'."""
    f = cartella_studio(cartella_dati) / "confine.json"
    if not f.exists():
        return None
    with open(f, encoding="utf-8") as fh:
        return json.load(fh)


def apri_confine(cartella_dati, symbol: str, timeframe: str, df: pd.DataFrame, macchina: str,
                 quota: float = 0.8, adesso=None, **altro) -> dict:
    """
    Apre lo studio: il confine all'80% (quota) delle barre di `df`, con la
    regola di sempre (split_is_oos), scritto in studio/confine.json. Solo sul PC
    (docs/70 §4.3 punto 4): su Colab si ferma. Si ferma anche se lo studio c'e' gia'.
    `altro` finisce nel file (il reset ci mette contaminato e studio_precedente).
    """
    if _controlla_macchina(macchina) == "colab":
        raise FileNotFoundError(MESSAGGIO_COLAB)
    f = cartella_studio(cartella_dati) / "confine.json"
    if f.exists():
        raise FileExistsError(f"Lo studio c'è già: {f}. Per un confine nuovo usa il reset (ricalcola_confine).")
    t = _adesso(adesso)
    confine = confine_da_quota(df, passo(timeframe), quota)
    contenuto = {
        "versione": VERSIONE,
        "id": t.isoformat(),
        "confine": confine.isoformat(),
        "aperto_il": t.isoformat(),
        "aperto_su": f"{str(symbol).upper()} {str(timeframe).upper()}",
        "regola": (f"{quota:.0%} delle {len(df):,} barre di {str(symbol).upper()} {str(timeframe).upper()} "
                   f"presenti il {t:%d/%m/%Y}").replace(",", "."),
        "contaminato": None,
        "studio_precedente": None,
    }
    contenuto.update(altro)
    scrivi_sicuro(f, _json(contenuto))
    return contenuto


# ========================================================================
# L'impronta dell'in-sample
# ========================================================================

def impronta(df_is: pd.DataFrame) -> dict:
    """
    Quante barre, prima e ultima, e un codice SHA-256 calcolato sulle date e
    sui prezzi OHLCV dell'in-sample (le altre colonne, come gli indicatori, non
    entrano). Due in-sample con la stessa impronta hanno le stesse barre.
    """
    idx = pd.DatetimeIndex(df_is.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(idx.as_unit("ns").asi8, dtype=np.int64).tobytes())
    h.update(np.ascontiguousarray(df_is[COLONNE].to_numpy(dtype=np.float64)).tobytes())
    return {"barre": int(len(df_is)), "prima": idx[0].isoformat() if len(idx) else None,
            "ultima": idx[-1].isoformat() if len(idx) else None, "codice": "sha256:" + h.hexdigest()}


def controlla_impronta(cartella_dati, dataset: str, df_is: pd.DataFrame, id_studio: str) -> str:
    """
    "nuova" se il dataset entra ora nello studio (l'impronta si scrive), "ok"
    se e' quella di prima. Se e' diversa si ferma (ValueError) e dice cosa e'
    cambiato: le barre dell'in-sample non sono piu' quelle con cui il dataset
    e' entrato nello studio.
    """
    f = cartella_studio(cartella_dati) / dataset / "impronta.json"
    adesso = {"studio": id_studio, **impronta(df_is)}
    if not f.exists():
        scrivi_sicuro(f, _json(adesso))
        return "nuova"
    with open(f, encoding="utf-8") as fh:
        prima = json.load(fh)
    if prima.get("studio") != id_studio:
        raise ValueError(f"{f} è di un altro studio ({prima.get('studio')}): non dovrebbe succedere. "
                         "Sposta la cartella del dataset in studio/archivio/ e riesegui.")
    if prima == adesso:
        return "ok"
    diverso = [f"{k}: {prima.get(k)} → {adesso.get(k)}" for k in ("barre", "prima", "ultima")
               if prima.get(k) != adesso.get(k)] or ["stesse barre e stesse date, prezzi diversi"]
    raise ValueError(
        f"Le barre dell'in-sample di {dataset} non sono più quelle con cui il dataset è entrato nello studio "
        f"({'; '.join(diverso)}). Il CSV è stato sostituito, scaricato da zero o corretto dall'exchange. "
        "Due strade: rimetti il CSV di prima, oppure ricalcola il confine (campo ricalcola_confine).")


# ========================================================================
# Entrare nello studio con un dataset
# ========================================================================

@dataclass
class Ingresso:
    """Quello che la schermata 1 riceve dallo studio (docs/70 §1.2, §2)."""
    studio: dict
    confine: pd.Timestamp
    df_is: pd.DataFrame
    df_oos: pd.DataFrame
    dataset: str
    aperto_ora: bool          # True: lo studio si e' aperto adesso, su questo dataset
    esito_impronta: str       # "nuova" (il dataset entra ora) o "ok"
    quota_is: float
    is_corto: bool            # in-sample sotto SOGLIA_IS_CORTO
    suggerisci_reset: bool    # out-of-sample oltre SOGLIA_RESET (solo un avviso)


def entra(cartella_dati, symbol: str, timeframe: str, df: pd.DataFrame, macchina: str,
          quota: float = 0.8, adesso=None, df_impronta: pd.DataFrame | None = None) -> Ingresso:
    """
    Il dataset (symbol, timeframe) entra nello studio. Se lo studio non c'e',
    lo apre su questo dataset (solo sul PC; su Colab si ferma con il messaggio
    del docs/70 §12.1). Divide `df` al confine unico e controlla l'impronta
    dell'in-sample. Si ferma se il CSV finisce prima del confine (copia vecchia)
    o comincia dopo (nessuna barra in-sample).

    df_impronta  (26/10/2026) lo storico del CSV su cui calcolare l'impronta
                 dell'in-sample, quando `df` e' gia' passato dagli indicatori
                 (che scartano le prime barre di riscaldamento): l'impronta
                 resta quella delle barre del CSV. None = `df`.
    """
    _controlla_macchina(macchina)
    studio = leggi_confine(cartella_dati)
    aperto_ora = studio is None
    if aperto_ora:
        studio = apri_confine(cartella_dati, symbol, timeframe, df, macchina, quota=quota, adesso=adesso)
    confine = _utc(studio["confine"])
    p = passo(timeframe)
    ds = nome_dataset(symbol, timeframe)
    if len(df) == 0 or df.index[-1] + p <= confine:
        raise ValueError(f"I dati di {ds} finiscono prima del confine dello studio ({confine:%d/%m/%Y %H:%M} UTC): "
                         "è una copia vecchia del CSV? Aggiornala (su Colab: ricaricala su Drive).")
    df_is, df_oos = split_al_confine(df, confine, p)
    if len(df_is) == 0:
        raise ValueError(f"{ds} comincia dopo il confine dello studio ({confine:%d/%m/%Y %H:%M} UTC): "
                         "nessuna barra per costruire.")
    base = df_is if df_impronta is None else split_al_confine(df_impronta, confine, p)[0]
    esito = controlla_impronta(cartella_dati, ds, base, studio["id"])
    quota_is = len(df_is) / len(df)
    return Ingresso(studio=studio, confine=confine, df_is=df_is, df_oos=df_oos, dataset=ds,
                    aperto_ora=aperto_ora, esito_impronta=esito, quota_is=quota_is,
                    is_corto=quota_is < SOGLIA_IS_CORTO, suggerisci_reset=(1 - quota_is) > SOGLIA_RESET)


# ========================================================================
# I giornali: solo in aggiunta, un file per macchina (docs/70 §4.3)
# ========================================================================

def aggiungi_voce(cartella_dati, dataset: str, macchina: str, id_studio: str, voce: dict,
                  quando=None) -> dict:
    """
    Aggiunge una riga a studio/<dataset>/giornale_<macchina>.jsonl. Una riga
    scritta non si cambia e non si cancella. Ritorna la riga scritta.
    """
    _controlla_macchina(macchina)
    riga = {"studio": id_studio, "quando": _adesso(quando).isoformat(), "macchina": macchina,
            **_rd.normale(voce)}
    f = cartella_studio(cartella_dati) / dataset / f"giornale_{macchina}.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(riga, ensure_ascii=False) + "\n")
    return riga


def leggi_voci(cartella_dati, dataset: str, id_studio: str | None) -> tuple[list, dict]:
    """
    Tutte le voci del dataset per lo studio `id_studio`, da TUTTI i giornali,
    in ordine di tempo (a parita': macchina, poi ordine nel file). Ritorna
    (voci, info) con info:
        altre_id   quante righe sono di un altro studio (scritte dopo un reset da
                   una sessione rimasta aperta con lo studio vecchio): non entrano
        copie      i file che non sono un giornale normale (copie di conflitto di
                   Drive, es. «giornale_pc (1).jsonl»): si leggono lo stesso
    id_studio None = tutte le voci, di qualunque studio.
    """
    cartella = cartella_studio(cartella_dati) / dataset
    voci, altre, copie = [], 0, []
    if not cartella.is_dir():
        return [], {"altre_id": 0, "copie": []}
    for f in sorted(cartella.glob("giornale*.jsonl")):
        if not _GIORNALE.match(f.name):
            copie.append(f.name)
        with open(f, encoding="utf-8") as fh:
            for n, testo in enumerate(fh):
                testo = testo.strip()
                if not testo:
                    continue
                riga = json.loads(testo)
                if id_studio is not None and riga.get("studio") != id_studio:
                    altre += 1
                    continue
                voci.append((riga["quando"], riga.get("macchina", ""), f.name, n, riga))
    voci.sort(key=lambda x: x[:4])
    return [v[-1] for v in voci], {"altre_id": altre, "copie": copie}


def chiave_registro(dataset: str, studio: dict) -> tuple:
    """La chiave del registro (registro_dataset.chiave_dataset): symbol, timeframe e confine unico."""
    symbol, tf = dataset.rsplit("_", 1)
    return _rd.chiave_dataset(symbol, tf, studio["confine"])


def ricostruisci(cartella_dati, dataset: str, studio: dict, nuove_prove=None):
    """
    La storia del dataset (registro_dataset.StoriaDataset) ricostruita da tutti
    i giornali e rimessa nel registro in memoria. Ritorna (storia, info) con
    l'info di leggi_voci.
    """
    voci, info = leggi_voci(cartella_dati, dataset, studio["id"])
    s = _rd.da_voci(chiave_registro(dataset, studio), voci, nuove_prove=nuove_prove)
    _rd.metti(s)
    return s, info


def voci_prove(scritte: dict, attuali: dict) -> list[dict]:
    """
    Le voci «prova» da aggiungere al giornale perche' il conto scritto
    (`scritte`) diventi quello attuale: solo quelle cambiate. Le voci semplici
    (trigger, fasce) hanno chiave None; quelle a dizionario una voce per chiave.
    """
    out = []
    for dove, val in attuali.items():
        prima = scritte.get(dove)
        if isinstance(val, dict):
            prima = prima if isinstance(prima, dict) else {}
            for k, n in val.items():
                if k not in prima or _rd.normale(prima[k]) != _rd.normale(n):
                    out.append({"voce": "prova", "dove": dove, "chiave": k, "n": n})
        elif prima is None or _rd.normale(prima) != _rd.normale(val):
            out.append({"voce": "prova", "dove": dove, "chiave": None, "n": val})
    return out


def diario_altrove(cartella_dati, dataset: str, studio: dict) -> dict:
    """Le aperture dell'out-of-sample sugli ALTRI dataset dello studio: {dataset: quante}."""
    out = {}
    radice = cartella_studio(cartella_dati)
    if not radice.is_dir():
        return out
    for d in sorted(p for p in radice.iterdir() if p.is_dir() and p.name != ARCHIVIO and p.name != dataset):
        n = sum(1 for v in leggi_voci(cartella_dati, d.name, studio["id"])[0] if v.get("voce") == "oos")
        if n:
            out[d.name] = n
    return out


# ========================================================================
# Il reset (docs/70 §5)
# ========================================================================

def _data_campo(campo: str):
    try:
        return pd.Timestamp(pd.to_datetime(str(campo).strip(), format="%d/%m/%Y")).date()
    except (ValueError, TypeError):
        return None


def reset(cartella_dati, campo: str, symbol: str, timeframe: str, df: pd.DataFrame, macchina: str,
          quota: float = 0.8, oggi=None, adesso=None) -> dict:
    """
    Il confine ricalcolato a richiesta, scrivendo la data di oggi (gg/mm/aaaa)
    nel campo ricalcola_confine. Ritorna {"esito": ...} con esito:
        "vuoto"                il campo e' vuoto: niente da fare
        "ignorato_colab"       il reset si fa solo sul PC
        "data_non_valida"      il campo non e' una data gg/mm/aaaa
        "data_non_di_oggi"     una data diversa da oggi (campo dimenticato pieno)
        "nessuno_studio"       non c'e' uno studio da ricalcolare (lo apre entra)
        "gia_fatto_oggi"       il reset con questa data e' gia' stato fatto
        "nessuna_barra_nuova"  il confine nuovo coincide con il vecchio
        "rifiutato_indietro"   il confine nuovo e' piu' indietro del vecchio e nello studio
                               vecchio c'e' gia' qualcosa di misurato o guardato (messaggio)
        "fatto"                studio archiviato, confine nuovo; piu' vecchio, nuovo,
                               archivio, contaminato
    Il confine nuovo e' all'80% (quota) delle barre di adesso di `df`, il
    dataset su cui lo si chiede. Lo studio intero (confine, impronte, giornali di
    tutti i dataset) va in studio/archivio/; non si cancella niente.

    Confine piu' INDIETRO del vecchio (26/10/2026, correzione di Mattia; docs/70
    §11, «studio aperto sul dataset sbagliato»): ammesso solo se lo studio
    vecchio non ha ancora niente di misurato ne' guardato, cioe' nessuna voce
    «prova», «oos» o «risalita» nei giornali di nessun dataset. Le voci
    «orizzonte» non contano: la schermata 1 scrive H appena si apre lo studio,
    prima di qualunque misura. Altrimenti si rifiuta: barre su cui si e' gia'
    costruito diventerebbero out-of-sample.
    """
    campo = "" if campo is None else str(campo).strip()
    if not campo:
        return {"esito": "vuoto"}
    if _controlla_macchina(macchina) == "colab":
        return {"esito": "ignorato_colab"}
    data = _data_campo(campo)
    if data is None:
        return {"esito": "data_non_valida", "campo": campo}
    oggi = pd.Timestamp.now().date() if oggi is None else pd.Timestamp(oggi).date()
    if data != oggi:
        return {"esito": "data_non_di_oggi", "campo": campo}
    vecchio = leggi_confine(cartella_dati)
    if vecchio is None:
        return {"esito": "nessuno_studio"}
    if vecchio.get("reset_il") == campo:
        return {"esito": "gia_fatto_oggi", "alle": vecchio.get("aperto_il")}
    c_vecchio = _utc(vecchio["confine"])
    c_nuovo = confine_da_quota(df, passo(timeframe), quota)
    if c_nuovo == c_vecchio:
        return {"esito": "nessuna_barra_nuova", "confine": c_vecchio}
    radice = cartella_studio(cartella_dati)
    if c_nuovo < c_vecchio:
        fatte = {"prova": 0, "oos": 0, "risalita": 0}
        for d in (p for p in radice.iterdir() if p.is_dir() and p.name != ARCHIVIO):
            for v in leggi_voci(cartella_dati, d.name, vecchio["id"])[0]:
                if v.get("voce") in fatte:
                    fatte[v["voce"]] += 1
        if any(fatte.values()):
            return {"esito": "rifiutato_indietro", "vecchio": c_vecchio, "nuovo": c_nuovo, "voci": fatte,
                    "messaggio": (
                        f"Il confine nuovo ({c_nuovo:%d/%m/%Y %H:%M} UTC) è più indietro di quello dello studio "
                        f"({c_vecchio:%d/%m/%Y %H:%M} UTC), e in questo studio hai già lavorato: "
                        f"{fatte['prova']} voci del conto delle prove, {fatte['oos']} aperture dell'out-of-sample, "
                        f"{fatte['risalita']} scelte rifatte. Le barre fra i due confini, su cui hai già costruito, "
                        "diventerebbero out-of-sample: un out-of-sample che conosci già non è più una prova pulita. "
                        "Il confine si può riportare indietro solo su uno studio in cui non hai ancora misurato né "
                        "guardato niente. Nessun reset fatto.")}
    # cosa c'era nello studio vecchio, dataset per dataset
    precedenti, visti = {}, []
    for d in sorted(p for p in radice.iterdir() if p.is_dir() and p.name != ARCHIVIO):
        voci, _ = leggi_voci(cartella_dati, d.name, vecchio["id"])
        oos = [v for v in voci if v.get("voce") == "oos"]
        h = []
        for v in voci:
            if v.get("voce") == "orizzonte" and int(v["H"]) not in h:
                h.append(int(v["H"]))
        precedenti[d.name] = {"h_provati": h, "oos_guardato": len(oos), "quando": [v["quando"] for v in oos]}
        for v in oos:
            fino = v.get("voce_diario", {}).get("oos_fino_al")
            if fino is not None:
                visti.append((d.name, _utc(fino)))
    contaminato = None
    if visti:
        ultimo = max(t for _, t in visti)
        if ultimo > c_vecchio:
            per_dataset = {}
            for d, _ in visti:
                per_dataset[d] = per_dataset.get(d, 0) + 1
            contaminato = {"dal": c_vecchio.isoformat(), "al": min(ultimo, c_nuovo).isoformat(),
                           "guardato": per_dataset}
    # l'archivio: lo studio intero, com'era
    t = _adesso(adesso)
    dest = radice / ARCHIVIO / f"{oggi:%Y-%m-%d}_fino_{c_vecchio:%Y-%m-%d}"
    k = 2
    while dest.exists():
        dest = radice / ARCHIVIO / f"{oggi:%Y-%m-%d}_fino_{c_vecchio:%Y-%m-%d}_{k}"
        k += 1
    dest.mkdir(parents=True)
    for p in list(radice.iterdir()):
        if p.name != ARCHIVIO:
            shutil.move(str(p), str(dest / p.name))
    precedente = {"id": vecchio["id"], "confine": vecchio["confine"], "aperto_il": vecchio.get("aperto_il"),
                  "aperto_su": vecchio.get("aperto_su"), "archivio": str(dest.relative_to(radice)).replace("\\", "/"),
                  "dataset": precedenti}
    nuovo = apri_confine(cartella_dati, symbol, timeframe, df, macchina, quota=quota, adesso=t,
                         contaminato=contaminato, studio_precedente=precedente, reset_il=campo)
    return {"esito": "fatto", "vecchio": c_vecchio, "nuovo": _utc(nuovo["confine"]), "archivio": dest,
            "contaminato": contaminato, "studio": nuovo}


# ========================================================================
# Il funding che arriva meno avanti delle candele (docs/70 §6.2)
# ========================================================================

def taglia_al_funding(df: pd.DataFrame, funding: pd.DataFrame, confine, timeframe: str):
    """
    Se il funding finisce prima delle candele, tiene le barre coperte e lascia
    fuori le altre, che sono out-of-sample (il CSV non si tocca). Coperta = la
    barra comincia prima della liquidazione dopo l'ultimo tasso (ultimo tasso +
    il suo intervallo), la stessa regola di exchange.copertura_funding.
    Ritorna (df, tagliate, fino): `tagliate` barre lasciate fuori, `fino` l'ultima
    tenuta. Si ferma se il funding non copre l'in-sample.
    """
    from .exchange import ORE_RIFERIMENTO
    f = funding.dropna(subset=["tasso"])
    if f.empty:
        raise ValueError("Il file del funding non ha tassi.")
    passi = f["intervallo_ore"].dropna()
    prossima = f.index[-1] + pd.Timedelta(hours=float(passi.iloc[-1]) if len(passi) else ORE_RIFERIMENTO)
    tenute = df.index < prossima
    n = int(tenute.sum())
    if n == len(df):
        return df, 0, df.index[-1]
    if df.index[n] + passo(timeframe) <= _utc(confine):   # la prima barra lasciata fuori e' in-sample
        raise ValueError(f"Il funding arriva fino al {f.index[-1]:%d/%m/%Y %H:%M} UTC e non copre l'in-sample "
                         "(il confine dello studio è più avanti): aggiorna barre e funding insieme.")
    return df.iloc[:n], len(df) - n, df.index[n - 1]
