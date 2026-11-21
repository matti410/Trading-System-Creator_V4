"""
La rosa dei trigger su una lista di monete (docs/82 §14.2, 20/11/2026): la rosa del Lab (engine/rosa.py, baseline
oraria) con tutte le monete su un orologio comune in barre e il risultato in ATR.

    basi = {m: base_moneta(cache.df, pip, orizzonti, orologio[m], meta) for m in monete}   # una moneta alla volta
    segnali = {m: {gruppo: maschera compressa}}                                             # un bit per barra
    rose = misura_rosa(basi, segnali, da_misurare, regole, n_orologio, settimana, processi)  # {H: tabella}

La regola, una per ogni t (quella che V4 ha già):
- Il contributo di ogni barra è quello di stagionalita.scarto_orario (l'evento contro il mercato della stessa ora
  della SUA moneta), in ATR (l'ATR giornaliero a 5 giornate chiuse noto al segnale; le prime giornate senza ATR non
  entrano), messo sull'orologio comune; poi stagionalita.errore_sovrapposti con H = l'orizzonte, senza correzione_n:
  due eventi di qualunque moneta a meno di H barre contano per intero, anche sulla stessa barra di monete diverse. Se la
  varianza esce zero o negativa, i blocchi di una settimana.
- Le due metà sono le due metà dell'orologio. Benjamini-Hochberg al q della config su tutti i misurati, long e short
  insieme: un trigger è un test, con 1 o con 5 monete. Si misura chi ha almeno `min_eventi` eventi sommando le monete.
- Famiglie fra le candidate (famiglie.famiglie): le barre di tutte le monete messe in fila, con FINESTRA barre vuote fra
  una moneta e l'altra (due trigger sono parenti se scattano sulle stesse barre della stessa moneta). rho fra quelli
  dello stesso lato (rosa._gruppo): sulla serie giornaliera, somma delle monete.
- Con una moneta è la rosa del Lab (rosa.rosa_orizzonti_entry con unita="atr"), al bit.

La memoria: si prepara una moneta alla volta e si tengono solo i segnali compressi (un bit per barra) e i contributi di
ogni barra; la misura gira in `processi` processi, con i numeri di un processo solo.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from engine.famiglie import FINESTRA, famiglie
from engine.indicatori import atr_giornaliero_chiuso
from engine.quarantena_trade import maschera_segnali_puliti
from engine.rosa import _gruppo, _ordina, _p_una_coda, benjamini_hochberg
from engine.stagionalita import errore_sovrapposti, fasce_orarie, in_unita, media_per_fascia

GRUPPI_PER_COMPITO = 16
COLONNE = ["candidato", "direction", "eventi", "scarto_atr", "t_netto", "p", "bh", "due_meta", "candidata", "famiglia",
           "nella_rosa", "rho_max", "perche", "incertezza_blocchi"]


# ------------------------------------------------------------------ la base di una moneta
def base_moneta(df: pd.DataFrame, pip: float, orizzonti, pos, meta: int) -> dict:
    """
    I contributi di ogni barra di una moneta (solo array): per ogni orizzonte il rendimento in ATR e il mercato della
    stessa ora (le stesse formule di rosa._contesto, unità «atr»). `pos` = le barre sull'orologio comune; `meta` = la
    metà dell'orologio (le due metà della rosa).
    """
    n = len(df)
    pip = float(pip)
    close = df["Close"].to_numpy(dtype=float)
    ingresso = np.full(n, np.nan)
    ingresso[: n - 1] = df["Open"].to_numpy(dtype=float)[1:]
    pulito = maschera_segnali_puliti(df, True)
    codici = fasce_orarie(df.index, "UTC")[0]
    n_cod = int(codici.max()) + 1
    atr = pd.Series(atr_giornaliero_chiuso(df)).reindex(df.index).to_numpy(dtype=float)
    pos = np.asarray(pos, dtype=np.int64)
    prima = pos < int(meta)
    giorno = pd.DatetimeIndex(df.index).as_unit("ns").asi8 // (86_400 * 10 ** 9)      # il giorno UTC, comune a tutte
    per_h = {}
    for H in orizzonti:
        H = int(H)
        fwd = np.full(n, np.nan)
        if n > H:
            fwd[: n - H] = (close[H:] - ingresso[: n - H]) / pip
        valido = np.isfinite(fwd) & np.isfinite(ingresso) & (ingresso > 0)
        f = in_unita(fwd, "atr", pip, prezzo=ingresso, atr=atr)
        usa = valido & pulito & np.isfinite(f)
        media = media_per_fascia(f, codici, usa)
        per_h[H] = dict(f=f, valido=valido, media=media,
                        media_meta=(media_per_fascia(f, codici, usa & prima), media_per_fascia(f, codici, usa & ~prima)),
                        barre_fascia=np.bincount(codici, weights=usa.astype(float), minlength=n_cod),
                        resto=np.where(usa, f - media, 0.0), codici_usa=np.where(usa, codici, n_cod),
                        uscita=np.minimum(np.arange(n) + H, n - 1))
    return dict(n=n, pulito=pulito, codici=codici, pos=pos, prima=prima, giorno=giorno, H=per_h)


# ------------------------------------------------------------------ la misura di un trigger
def _misura(basi: dict, maschere: dict, d: int, H: int, P: dict) -> dict:
    """Un trigger (le sue maschere per moneta) a un orizzonte, nel verso d: la misura di rosa._misura_trigger."""
    eventi = {m: np.flatnonzero(maschere[m] & basi[m]["H"][H]["valido"] & basi[m]["pulito"]) for m in basi}
    tot = int(sum(e.size for e in eventi.values()))
    if tot < max(int(P["min_eventi"]), 2):
        return {"scartata": tot}
    pos = {m: e[np.isfinite(basi[m]["H"][H]["f"][e])] for m, e in eventi.items()}
    n_t = int(sum(p.size for p in pos.values()))
    if n_t < 2:
        return {"eventi": tot, "scarto": np.nan, "t": np.nan, "blocchi": False, "meta_ok": False,
                "meta": (np.nan, np.nan), "serie": None}
    C = {m: basi[m]["H"][H] for m in basi}
    valori = np.concatenate([d * (C[m]["f"][p] - C[m]["media"][p]) for m, p in pos.items()])
    scarto = float(np.mean(valori))
    U = np.zeros(int(P["n_orologio"]))
    for m, p in pos.items():
        c_m = C[m]
        trig_f = np.bincount(basi[m]["codici"][p], minlength=c_m["barre_fascia"].size).astype(float)
        with np.errstate(invalid="ignore", divide="ignore"):
            quota = np.where(c_m["barre_fascia"] > 0, trig_f / c_m["barre_fascia"], 0.0)
        c = np.append(-quota / n_t, 0.0)[c_m["codici_usa"]]
        c[p] += 1.0 / n_t
        r = c_m["resto"].copy()
        r[p] -= d * scarto
        U[basi[m]["pos"]] += c * r
    se, blocchi = errore_sovrapposti(U, H, int(P["settimana"]))
    t = scarto / se if (np.isfinite(se) and se > 0) else np.nan
    a = {m: basi[m]["prima"][p] for m, p in pos.items()}
    meta_ok = bool(any(x.any() for x in a.values()) and any((~x).any() for x in a.values()))
    if meta_ok:          # le due metà guardano solo il segno dello scarto (stagionalita.scarto_orario_medio)
        prima = np.concatenate([d * (C[m]["f"][p[a[m]]] - C[m]["media_meta"][0][p[a[m]]]) for m, p in pos.items()])
        dopo = np.concatenate([d * (C[m]["f"][p[~a[m]]] - C[m]["media_meta"][1][p[~a[m]]]) for m, p in pos.items()])
        meta = (float(np.mean(prima)), float(np.mean(dopo)))
    else:
        meta = (np.nan, np.nan)
    giorni = np.concatenate([basi[m]["giorno"][C[m]["uscita"][p]] for m, p in pos.items()])
    v = np.concatenate([d * C[m]["f"][p] for m, p in pos.items()])
    serie = pd.Series(v, index=giorni).groupby(level=0).sum()
    return {"eventi": tot, "scarto": scarto, "t": t, "blocchi": blocchi, "meta_ok": meta_ok, "meta": meta,
            "serie": serie}


def _opposto(res: dict) -> dict:
    """Lo stesso trigger nel verso opposto (rosa._opposto): scarto, t e due metà col segno cambiato."""
    if "scartata" in res:
        return res
    return dict(res, scarto=-res["scarto"], t=-res["t"], meta=(-res["meta"][0], -res["meta"][1]),
                serie=-res["serie"] if res["serie"] is not None else None)


def _due_meta(res: dict) -> bool:
    return bool(res["meta_ok"] and res["meta"][0] > 0 and res["meta"][1] > 0)


# ------------------------------------------------------------------ i processi
_PROC: dict = {}


def _avvia(basi: dict, segnali: dict, P: dict) -> None:
    _PROC.clear()
    _PROC.update(basi=basi, segnali=segnali, P=P)


def _compito(gruppi: list) -> dict:
    """Un compito: [(gruppo, [(nome, d), ...]), ...] -> {nome: {H: misura}}."""
    basi, segnali, P = _PROC["basi"], _PROC["segnali"], _PROC["P"]
    out = {}
    for gruppo, membri in gruppi:
        maschere = {m: np.unpackbits(segnali[m][gruppo], count=basi[m]["n"]).astype(bool) for m in basi}
        d0 = membri[0][1]
        misure = {H: _misura(basi, maschere, d0, H, P) for H in P["Hs"]}
        for nome, d in membri:
            out[nome] = {H: (x if d == d0 else _opposto(x)) for H, x in misure.items()}
    return out


def _esegui(compiti: list, basi: dict, segnali: dict, P: dict, processi: int) -> dict:
    """I compiti in uno o più processi: stessi numeri."""
    quanti = max(1, min(int(processi or 1), os.cpu_count() or 1, len(compiti) or 1))
    if quanti > 1:
        from concurrent.futures import ProcessPoolExecutor
        from concurrent.futures.process import BrokenProcessPool
        from engine.filter_search_bt import _contesto_processi
        contesto = _contesto_processi(True)
        if contesto is not None:
            try:
                with ProcessPoolExecutor(max_workers=quanti, mp_context=contesto, initializer=_avvia,
                                         initargs=(basi, segnali, P)) as ex:
                    out = {}
                    for r in ex.map(_compito, compiti):
                        out.update(r)
                    return out
            except (BrokenProcessPool, OSError) as e:
                print(f"rosa: processi non disponibili ({type(e).__name__}), si prosegue in un processo solo.")
    _avvia(basi, segnali, P)
    try:
        out = {}
        for c in compiti:
            out.update(_compito(c))
        return out
    finally:
        _PROC.clear()


# ------------------------------------------------------------------ la rosa
def in_fila(maschere) -> np.ndarray:
    """
    Le barre vere di più monete messe in fila, una dopo l'altra, con FINESTRA["entry"] barre vuote fra una moneta e
    l'altra: famiglie.py allarga ogni evento di quelle barre, e così due monete non si toccano (docs/82 §14.2). Con una
    moneta, la sua maschera.
    """
    vuoto = np.zeros(FINESTRA["entry"], dtype=bool)
    pezzi = []
    for k, m in enumerate(maschere):
        if k:
            pezzi.append(vuoto)
        pezzi.append(np.asarray(m, dtype=bool))
    return np.concatenate(pezzi)


def maschere_in_fila(segnali: dict, basi: dict, gruppo: str) -> np.ndarray:
    """Le barre vere di un gruppo su tutte le monete della lista messe in fila (in_fila)."""
    return in_fila([np.unpackbits(segnali[m][gruppo], count=basi[m]["n"]).astype(bool) for m in basi])


def misura_rosa(basi: dict, segnali: dict, da_misurare: dict, regole: dict, n_orologio: int, settimana: int,
                processi: int = 1) -> dict:
    """
    La rosa dei trigger sulla lista (vedi la testa del file). `basi` = {symbol: base_moneta}, nell'ordine della lista;
    `segnali` = {symbol: {gruppo: maschera compressa}}; `da_misurare` = {nome: (gruppo, direzione)} nell'ordine in cui
    si misurano (i nomi della rosa, «E36_short»; due nomi con lo stesso gruppo hanno la stessa maschera e versi
    opposti: si misurano una volta). `regole` = il campo «rosa» della config. Ritorna {H: tabella}, una riga per trigger
    misurato (COLONNE), come la rosa del Lab.
    """
    Hs = [int(h) for h in regole["orizzonti_barre"]]
    P = dict(Hs=Hs, min_eventi=int(regole["min_eventi"]), n_orologio=int(n_orologio), settimana=int(settimana))
    per_gruppo: dict = {}
    for nome, (gruppo, d) in da_misurare.items():
        per_gruppo.setdefault(gruppo, []).append((nome, int(d)))
    voci = list(per_gruppo.items())
    compiti = [voci[i:i + GRUPPI_PER_COMPITO] for i in range(0, len(voci), GRUPPI_PER_COMPITO)]
    risultati = _esegui(compiti, basi, segnali, P, processi)
    nomi = list(da_misurare)
    lunghezza = sum(b["n"] for b in basi.values()) + FINESTRA["entry"] * (len(basi) - 1)
    finto = pd.DataFrame(index=pd.RangeIndex(lunghezza))
    memoria: dict = {}
    rose = {}
    for H in Hs:
        righe, serie = [], {}
        for nome in nomi:
            res = risultati[nome][H]
            if "scartata" in res:
                continue
            gruppo, d = da_misurare[nome]
            righe.append({"candidato": nome, "direction": int(d), "eventi": res["eventi"], "scarto_atr": res["scarto"],
                          "t_netto": res["t"], "p": _p_una_coda(res["t"]), "due_meta": _due_meta(res),
                          "incertezza_blocchi": res["blocchi"]})
            if res["serie"] is not None:
                serie[nome] = res["serie"]
        if not righe:
            vuota = pd.DataFrame(columns=COLONNE)
            vuota.attrs.update(k=0, H=H)
            rose[H] = vuota
            continue
        t = pd.DataFrame(righe)
        t["bh"] = benjamini_hochberg(t["p"].to_numpy(), float(regole["q"]))
        t["candidata"] = (t["t_netto"] > 0) & t["bh"] & t["due_meta"]
        candidate = list(t.loc[t["candidata"], "candidato"])
        for nome in candidate:
            if nome not in memoria:
                memoria[nome] = np.packbits(maschere_in_fila(segnali, basi, da_misurare[nome][0]))
        fam = (famiglie(finto, "entry", nomi=candidate, soglia=float(regole["soglia_famiglia"]), memoria=memoria)
               .set_index("nome")["famiglia"] if candidate else pd.Series(dtype=float))
        t["famiglia"] = t["candidato"].map(fam).astype("Int64")
        t = _ordina(_gruppo(t, serie, float(regole["rho_max"]), per_lato=True))[COLONNE]
        t.attrs.update(k=len(t), H=H)
        rose[H] = t
    return rose
