"""
La rosa dei trigger su una lista di monete (docs/82 §14.2, 20/11/2026): la rosa del Lab (engine/rosa.py, baseline
oraria) con tutte le monete su un orologio comune in barre e il risultato in ATR. Dal 22/11 (docs/82 §15) al netto del
costo di andata e ritorno di ogni evento, e decide il test individuale.

    basi = {m: base_moneta(cache.df, pip, orizzonti, orologio[m], meta, commissione, passo)}   # una moneta alla volta
    segnali = {m: {gruppo: maschera compressa}}                                                 # un bit per barra
    rose = misura_rosa(basi, segnali, da_misurare, regole, n_orologio, settimana, 1.96, processi)  # {H: tabella}

La regola, una per ogni t (quella che V4 ha già):
- Il contributo di ogni barra è quello di stagionalita.scarto_orario (l'evento contro il mercato della stessa ora
  della SUA moneta), in ATR (l'ATR giornaliero a 5 giornate chiuse noto al segnale; le prime giornate senza ATR non
  entrano), messo sull'orologio comune; poi stagionalita.errore_sovrapposti con H = l'orizzonte, senza correzione_n:
  due eventi di qualunque moneta a meno di H barre contano per intero, anche sulla stessa barra di monete diverse. Se la
  varianza esce zero o negativa, i blocchi di una settimana.
- Al netto (docs/82 §15, 22/11): ogni evento paga il costo di andata e ritorno della sua moneta, commissione taker ×
  (prezzo d'ingresso + prezzo d'uscita) + un passo di prezzo (la formula del valutatore; il funding no), diviso l'ATR
  al segnale. Scarto netto = verso × (rendimento − mercato della stessa ora) − costo; il mercato della stessa ora resta
  lordo. Il costo entra nello scarto, nel contributo di ogni evento al t e nelle due metà. Long e short si misurano
  ognuno per sé (pagano entrambi il costo); i pezzi comuni ai due versi di una maschera si calcolano una volta.
- Le due metà sono le due metà dell'orologio. Si misura chi ha almeno `min_eventi` eventi sommando le monete.
- Chi entra (Mattia, 22/11): t netto >= soglia_t (la soglia del test individuale, 1,96) e scarto netto positivo nelle
  due metà; niente BH. Poi famiglie fra le candidate (famiglie.famiglie): le barre di tutte le monete messe in fila,
  con FINESTRA barre vuote fra una moneta e l'altra (due trigger sono parenti se scattano sulle stesse barre della
  stessa moneta). rho fra quelli dello stesso lato (rosa._gruppo): sulla serie giornaliera LORDA, somma delle monete.
- Con una moneta, a costo zero e con il BH di prima (scegli_rosa con supera = il BH) è la rosa del Lab
  (rosa.rosa_orizzonti_entry con unita="atr"), al bit.

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
from engine.rosa import _gruppo, _ordina
from engine.stagionalita import errore_sovrapposti, fasce_orarie, in_unita, media_per_fascia

try:
    from numba import njit
except Exception:      # numba non installato: la stessa funzione in Python, più lenta
    def njit(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda f: f

GRUPPI_PER_COMPITO = 16
MISURA = ["candidato", "direction", "eventi", "scarto_atr", "costo_atr", "t_netto", "due_meta", "incertezza_blocchi"]
COLONNE = ["candidato", "direction", "eventi", "scarto_atr", "costo_atr", "t_netto", "due_meta", "candidata",
           "famiglia", "nella_rosa", "rho_max", "perche", "incertezza_blocchi"]


# ------------------------------------------------------------------ la base di una moneta
def base_moneta(df: pd.DataFrame, pip: float, orizzonti, pos, meta: int, commissione: float,
                passo_pips: float) -> dict:
    """
    I contributi di ogni barra di una moneta (solo array): per ogni orizzonte il rendimento in ATR, il mercato della
    stessa ora (le stesse formule di rosa._contesto, unità «atr») e il costo di andata e ritorno in ATR di un evento su
    quella barra: commissione × (ingresso + uscita) / pip + passo_pips, in pips, come valutatore.netti (docs/82 §15).
    `pos` = le barre sull'orologio comune; `meta` = la metà dell'orologio (le due metà della rosa). `costo_medio` = il
    costo medio di tutti gli eventi possibili del pezzo, ai tre orizzonti, in ATR e in bp (da leggere, cella 1).
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
    contigue = n > 0 and int(pos[-1]) - int(pos[0]) + 1 == n
    dove = slice(int(pos[0]), int(pos[0]) + n) if contigue else pos        # le barre sull'orologio (slice: più veloce)
    per_h, costi_atr, costi_bp = {}, [], []
    for H in orizzonti:
        H = int(H)
        fwd = np.full(n, np.nan)
        uscita = np.full(n, np.nan)
        if n > H:
            fwd[: n - H] = (close[H:] - ingresso[: n - H]) / pip
            uscita[: n - H] = close[H:]
        valido = np.isfinite(fwd) & np.isfinite(ingresso) & (ingresso > 0)
        f = in_unita(fwd, "atr", pip, prezzo=ingresso, atr=atr)
        usa = valido & pulito & np.isfinite(f)
        media = media_per_fascia(f, codici, usa)
        costo_pips = float(commissione) * (ingresso + uscita) / pip + (0.0 + float(passo_pips))
        k = in_unita(costo_pips, "atr", pip, prezzo=ingresso, atr=atr)
        costi_atr.append(k[usa])
        costi_bp.append(in_unita(costo_pips, "bp", pip, prezzo=ingresso)[usa])
        per_h[H] = dict(f=f, ok=valido & pulito, media=media, k=k,
                        media_meta=(media_per_fascia(f, codici, usa & prima), media_per_fascia(f, codici, usa & ~prima)),
                        barre_fascia=np.bincount(codici, weights=usa.astype(float), minlength=n_cod),
                        resto=np.where(usa, f - media, 0.0),
                        codici_usa=np.where(usa, codici, n_cod).astype(np.int16),    # al più 1.441 fasce (M1)
                        uscita=np.minimum(np.arange(n) + H, n - 1))
    tutti_atr, tutti_bp = np.concatenate(costi_atr), np.concatenate(costi_bp)
    costo_medio = {"atr": float(np.mean(tutti_atr)) if tutti_atr.size else float("nan"),
                   "bp": float(np.mean(tutti_bp)) if tutti_bp.size else float("nan")}
    return dict(n=n, pulito=pulito, codici=codici, pos=pos, dove=dove, prima=prima, giorno=giorno, H=per_h,
                costo_medio=costo_medio)


# ------------------------------------------------------------------ la misura di un trigger
@njit(cache=True)
def _somme_kahan(giorni, valori, primo, quanti):
    """Le somme per giorno, nell'ordine dei valori, con la compensazione di Kahan: il calcolo di pandas
    Series.groupby(level=0).sum() (stessi numeri, al bit; collaudo in test_fabbrica_monete.py), molto più veloce."""
    somma = np.zeros(quanti)
    compensa = np.zeros(quanti)
    conta = np.zeros(quanti, np.int64)
    for i in range(giorni.size):
        g = giorni[i] - primo
        y = valori[i] - compensa[g]
        t = somma[g] + y
        compensa[g] = t - somma[g] - y
        if compensa[g] != compensa[g]:
            compensa[g] = 0.0
        somma[g] = t
        conta[g] += 1
    return somma, conta


def serie_giornaliera(giorni: np.ndarray, valori: np.ndarray) -> pd.Series:
    """La serie giornaliera di rho (rosa._misura_trigger): la somma dei valori per giorno, giorni in ordine."""
    giorni = np.asarray(giorni, dtype=np.int64)
    primo = int(giorni.min())
    somma, conta = _somme_kahan(giorni, np.asarray(valori, dtype=float), primo, int(giorni.max()) - primo + 1)
    c = conta > 0
    return pd.Series(somma[c], index=np.flatnonzero(c).astype(np.int64) + primo)


def _vuota(tot: int) -> dict:
    return {"eventi": tot, "scarto": np.nan, "costo": np.nan, "t": np.nan, "blocchi": False, "meta_ok": False,
            "meta": (np.nan, np.nan), "serie": None}


def _misura(basi: dict, maschere: dict, versi, H: int, P: dict) -> dict:
    """
    Una maschera (per moneta) a un orizzonte, nei versi `versi` (1 long, -1 short): {verso: misura}, la misura di
    rosa._misura_trigger al netto del costo di ogni evento (docs/82 §15). Eventi, pesi delle fasce, contributi delle
    barre senza evento e serie lorda sono comuni ai due versi e si calcolano una volta; a costo zero ogni numero è
    quello di prima, al bit.
    """
    C = {m: basi[m]["H"][H] for m in basi}
    eventi = {m: np.flatnonzero(maschere[m] & C[m]["ok"]) for m in basi}
    tot = int(sum(e.size for e in eventi.values()))
    if tot < max(int(P["min_eventi"]), 2):
        return {d: {"scartata": tot} for d in versi}
    pos = {m: e[np.isfinite(C[m]["f"][e])] for m, e in eventi.items()}
    n_t = int(sum(p.size for p in pos.values()))
    if n_t < 2:
        return {d: _vuota(tot) for d in versi}
    lordo = np.concatenate([C[m]["f"][p] - C[m]["media"][p] for m, p in pos.items()])
    costo = np.concatenate([C[m]["k"][p] for m, p in pos.items()])
    # i contributi di ogni barra (rosa._misura_trigger: c × r), comuni ai due versi; degli eventi i pezzi che servono
    pesi = {}
    for m, p in pos.items():
        c_m = C[m]
        trig_f = np.bincount(basi[m]["codici"][p], minlength=c_m["barre_fascia"].size).astype(float)
        with np.errstate(invalid="ignore", divide="ignore"):
            quota = np.where(c_m["barre_fascia"] > 0, trig_f / c_m["barre_fascia"], 0.0)
        c = np.take(np.append(-quota / n_t, 0.0), c_m["codici_usa"])
        c[p] += 1.0 / n_t
        pesi[m] = (c * c_m["resto"], basi[m]["pos"][p], c[p], c_m["resto"][p], c_m["k"][p])
    a = {m: basi[m]["prima"][p] for m, p in pos.items()}
    meta_ok = bool(any(x.any() for x in a.values()) and any((~x).any() for x in a.values()))
    if meta_ok:          # le due metà, lordo e costo di ogni evento (S1: si guarda il segno dello scarto netto)
        meta_pos = [{m: p[a[m]] for m, p in pos.items()}, {m: p[~a[m]] for m, p in pos.items()}]
        meta_lordo = [np.concatenate([C[m]["f"][q] - C[m]["media_meta"][i][q] for m, q in meta_pos[i].items()])
                      for i in (0, 1)]
        meta_costo = [np.concatenate([C[m]["k"][q] for m, q in meta_pos[i].items()]) for i in (0, 1)]
    giorni = np.concatenate([basi[m]["giorno"][C[m]["uscita"][p]] for m, p in pos.items()])
    serie_lorda = serie_giornaliera(giorni, np.concatenate([C[m]["f"][p] for m, p in pos.items()]))
    out = {}
    for d in versi:
        valori = d * lordo - costo
        scarto = float(np.mean(valori))
        U = np.zeros(int(P["n_orologio"]))
        for m, (w, j, cp, rp, kp) in pesi.items():     # sulle barre degli eventi r toglie scarto e costo
            prima_m = U[j]                 # la somma delle monete prima di questa, sulle barre dei suoi eventi
            U[basi[m]["dove"]] += w
            U[j] = prima_m + cp * (rp - d * (scarto + kp))
        se, blocchi = errore_sovrapposti(U, H, int(P["settimana"]))
        t = scarto / se if (np.isfinite(se) and se > 0) else np.nan
        meta = ((float(np.mean(d * meta_lordo[0] - meta_costo[0])), float(np.mean(d * meta_lordo[1] - meta_costo[1])))
                if meta_ok else (np.nan, np.nan))
        out[d] = {"eventi": tot, "scarto": scarto, "costo": float(np.mean(costo)), "t": t, "blocchi": blocchi,
                  "meta_ok": meta_ok, "meta": meta, "serie": serie_lorda if d == 1 else d * serie_lorda}   # S2: lorda
    return out


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
        versi = list(dict.fromkeys(d for _, d in membri))
        misure = {H: _misura(basi, maschere, versi, H, P) for H in P["Hs"]}
        for nome, d in membri:
            out[nome] = {H: x[d] for H, x in misure.items()}
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


def misura_trigger(basi: dict, segnali: dict, da_misurare: dict, regole: dict, n_orologio: int, settimana: int,
                   processi: int = 1) -> dict:
    """
    La misura di ogni trigger sulla lista, al netto dei costi (vedi la testa del file), senza ancora scegliere chi
    entra. `basi` = {symbol: base_moneta}, nell'ordine della lista; `segnali` = {symbol: {gruppo: maschera compressa}};
    `da_misurare` = {nome: (gruppo, direzione)} nell'ordine in cui si misurano (i nomi della rosa, «E36_short»; due nomi
    con lo stesso gruppo hanno la stessa maschera e versi opposti: i pezzi comuni si calcolano una volta). `regole` = il
    campo «rosa» della config. Ritorna {H: (tabella, serie)}: una riga per trigger misurato (MISURA) e le serie
    giornaliere lorde per rho.
    """
    Hs = [int(h) for h in regole["orizzonti_barre"]]
    P = dict(Hs=Hs, min_eventi=int(regole["min_eventi"]), n_orologio=int(n_orologio), settimana=int(settimana))
    per_gruppo: dict = {}
    for nome, (gruppo, d) in da_misurare.items():
        per_gruppo.setdefault(gruppo, []).append((nome, int(d)))
    voci = list(per_gruppo.items())
    compiti = [voci[i:i + GRUPPI_PER_COMPITO] for i in range(0, len(voci), GRUPPI_PER_COMPITO)]
    risultati = _esegui(compiti, basi, segnali, P, processi)
    out = {}
    for H in Hs:
        righe, serie = [], {}
        for nome, (gruppo, d) in da_misurare.items():
            res = risultati[nome][H]
            if "scartata" in res:
                continue
            righe.append({"candidato": nome, "direction": int(d), "eventi": res["eventi"], "scarto_atr": res["scarto"],
                          "costo_atr": res["costo"], "t_netto": res["t"], "due_meta": _due_meta(res),
                          "incertezza_blocchi": res["blocchi"]})
            if res["serie"] is not None:
                serie[nome] = res["serie"]
        out[H] = (pd.DataFrame(righe, columns=MISURA), serie)
    return out


def scegli_rosa(tabella: pd.DataFrame, serie: dict, supera, basi: dict, segnali: dict, da_misurare: dict,
                regole: dict, memoria: dict | None = None) -> pd.DataFrame:
    """
    Chi entra, sulla tabella di misura_trigger a un orizzonte: candidata = t netto > 0, `supera` (il test) e le due
    metà; poi uno per famiglia e |rho| <= rho_max con quelli già presi dello stesso lato (rosa._gruppo, per_lato). La
    rosa della fabbrica passa supera = t netto >= soglia_t; il collaudo «come la rosa di prima» passa il BH. Ritorna la
    tabella con le colonne della rosa del Lab (`bh` = supera). `memoria` = le maschere in fila già fatte, fra orizzonti.
    """
    memoria = {} if memoria is None else memoria
    t = tabella.copy()
    t["bh"] = np.asarray(supera, dtype=bool)
    t["candidata"] = (t["t_netto"] > 0) & t["bh"] & t["due_meta"]
    candidate = list(t.loc[t["candidata"], "candidato"])
    for nome in candidate:
        if nome not in memoria:
            memoria[nome] = np.packbits(maschere_in_fila(segnali, basi, da_misurare[nome][0]))
    lunghezza = sum(b["n"] for b in basi.values()) + FINESTRA["entry"] * (len(basi) - 1)
    fam = (famiglie(pd.DataFrame(index=pd.RangeIndex(lunghezza)), "entry", nomi=candidate,
                    soglia=float(regole["soglia_famiglia"]), memoria=memoria).set_index("nome")["famiglia"]
           if candidate else pd.Series(dtype=float))
    t["famiglia"] = t["candidato"].map(fam).astype("Int64")
    return _ordina(_gruppo(t, serie, float(regole["rho_max"]), per_lato=True))


def _motivo(r, soglia_t: float) -> str:
    """Il primo controllo che un trigger fuori dalle candidate non supera (docs/82 §15)."""
    if not np.isfinite(r["t_netto"]):
        return "non misurabile (troppo pochi casi)"
    if r["t_netto"] < soglia_t:
        return f"t netto sotto {soglia_t:.2f}".replace(".", ",")
    return "non positiva al netto in una delle due metà"


def misura_rosa(basi: dict, segnali: dict, da_misurare: dict, regole: dict, n_orologio: int, settimana: int,
                soglia_t: float, processi: int = 1) -> dict:
    """
    La rosa dei trigger sulla lista (vedi la testa del file): misura_trigger, poi scegli_rosa con il test individuale
    (t netto >= soglia_t). Ritorna {H: tabella}, una riga per trigger misurato (COLONNE).
    """
    memoria: dict = {}
    rose = {}
    for H, (t, serie) in misura_trigger(basi, segnali, da_misurare, regole, n_orologio, settimana, processi).items():
        if not len(t):
            vuota = pd.DataFrame(columns=COLONNE)
            vuota.attrs.update(k=0, H=H)
            rose[H] = vuota
            continue
        s = scegli_rosa(t, serie, (t["t_netto"] >= float(soglia_t)).to_numpy(), basi, segnali, da_misurare, regole,
                        memoria)
        fuori = ~s["candidata"].to_numpy(dtype=bool)
        s.loc[fuori, "perche"] = [_motivo(r, float(soglia_t)) for _, r in s.loc[fuori].iterrows()]
        s = s[COLONNE]
        s.attrs.update(k=len(s), H=H)
        rose[H] = s
    return rose
