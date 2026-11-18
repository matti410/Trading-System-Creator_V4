"""
Sovrapposizioni e famiglie di condizioni (docs/50 §7.5; docs/00, punto 4).

Due condizioni che scattano quasi sulle stesse barre sono una prova sola
travestita da due. Qui si misura quanto, usando SOLO i segnali (le barre in
cui la condizione e' vera), mai i risultati dei trade: per questo si puo'
usare per decidere cosa aggiungere o togliere senza contare prove in piu'.

Tre funzioni pubbliche, tutte sulle condizioni registrate in engine.registry
(come il collaudo del catalogo):

    sovrapposizioni(dati, tipo)   una riga per coppia: quota di A che cade su B,
                                  e quante volte il caso (regola dei doppioni)
    somiglianze(dati, tipo)       la matrice di somiglianza fra tutte le condizioni
    famiglie(dati, tipo)          le condizioni raggruppate per somiglianza

`dati` e' un DataFrame con gli indicatori (aggiungi_indicatori), oppure un
dizionario {symbol: DataFrame}: con piu' symbol una somiglianza conta solo se
vale su TUTTI. Si passa l'IN-SAMPLE (split_is_oos): l'out-of-sample non si
guarda.

COME SI MISURA
--------------
- Ogni condizione diventa una serie di barre vere. Le entry si allargano di
  `finestra` barre per parte (2 per default: due trigger a una barra di
  distanza vivono le stesse candele); filtri e uscite no (0).
- quota(A dentro B) = barre vere di A che cadono su B allargato / barre vere di A.
- caso(B) = quota di barre coperte da B allargato: e' la quota che A avrebbe
  dentro B se fosse indipendente. lift = quota / caso.
- Regola dei doppioni (§7.5, precisata il 15/10/2026): A e' doppione di B se
  quota >= 70% e lift >= 1,3.
- Somiglianza fra A e B = la quota piu' alta fra i due versi, contata solo se il
  suo lift e' almeno 1,3 (altrimenti 0: contro un filtro largo il 70% si
  raggiunge per caso); con piu' symbol, la piu' bassa fra i symbol.
- Famiglie: raggruppamento gerarchico a legame medio sulla distanza
  1 - somiglianza, tagliato a `soglia`: dentro una famiglia la somiglianza media
  fra i gruppi uniti e' almeno `soglia` (60%, decisione di Mattia del
  17/10/2026).

Modulo ADDITIVO: non modifica nessun file esistente dell'engine.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from engine import registry as _reg

FINESTRA = {"entry": 2, "exit": 0, "filtro": 0}
SOGLIA_DOPPIONE = 0.70
LIFT_MIN = 1.3
SOGLIA_FAMIGLIA = 0.60

_ELENCO = {"entry": _reg.list_entries, "exit": _reg.list_exits, "filtro": _reg.list_filters}
_PRENDI = {"entry": _reg.get_entry, "exit": _reg.get_exit, "filtro": _reg.get_filter}


def _come_dizionario(dati) -> dict[str, pd.DataFrame]:
    return dict(dati) if isinstance(dati, dict) else {"": dati}


def _colonna(df: pd.DataFrame, tipo: str, nome: str) -> np.ndarray:
    """Le barre vere di una condizione (NaN = falso; numerica: != 0)."""
    s = _PRENDI[tipo](nome)(df)
    v = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float) if s.dtype != bool else s.to_numpy()
    return np.nan_to_num(v, nan=0.0) != 0


def _allarga(m: np.ndarray, finestra: int, asse: int = 0) -> np.ndarray:
    """Ogni barra vera allargata di `finestra` barre per parte, lungo l'asse delle barre."""
    w = m.copy()
    for s in range(1, finestra + 1):
        if asse == 0:
            w[s:] |= m[:-s]
            w[:-s] |= m[s:]
        else:
            w[:, s:] |= m[:, :-s]
            w[:, :-s] |= m[:, s:]
    return w


# 18/11/2026 (decisione di Mattia): la matrice delle barre vere si tiene compressa (1 bit per barra) e i conteggi
# si fanno a pezzi di barre, cosi' la memoria resta sotto 1 GB anche con 3.000 condizioni su M5. I numeri sono
# quelli di prima, al bit: i conteggi sono interi esatti (in float32 fino a 2^24 per pezzo, poi in float64) e
# quota, caso e lift si ricavano con le stesse divisioni.
BYTE_PER_PEZZO = 64_000_000        # la memoria di una matrice di pezzo (float32)


def _misure(df: pd.DataFrame, tipo: str, nomi: list[str], finestra: int) -> dict:
    n, k = len(df), len(nomi)
    compressa = np.zeros((k, (n + 7) // 8), dtype=np.uint8)       # riga i = barre vere della condizione i
    for i, nome in enumerate(nomi):
        compressa[i] = np.packbits(_colonna(df, tipo, nome))
    conti = np.zeros((k, k))           # conti[i, j] = barre vere di i che cadono su j allargato
    vere = np.zeros(k)
    larghe = np.zeros(k)               # barre coperte da j allargato
    passo = min(max(8, (BYTE_PER_PEZZO // (4 * max(k, 1))) // 8 * 8), 2 ** 24)
    for p0 in range(0, n, passo):
        p1 = min(n, p0 + passo)
        q0, q1 = max(0, p0 - finestra), min(n, p1 + finestra)   # il margine per allargare ai bordi del pezzo
        bit = np.unpackbits(compressa[:, q0 // 8:(q1 + 7) // 8], axis=1, count=None)
        m = bit[:, q0 % 8:q0 % 8 + (q1 - q0)].astype(bool)
        w = _allarga(m, finestra, asse=1)[:, p0 - q0:p1 - q0]
        a = m[:, p0 - q0:p1 - q0].astype(np.float32)
        b = w.astype(np.float32)
        conti += a @ b.T
        vere += a.sum(axis=1, dtype=np.float64)
        larghe += b.sum(axis=1, dtype=np.float64)
        del bit, m, w, a, b
    with np.errstate(invalid="ignore", divide="ignore"):
        quota = np.where(vere[:, None] > 0, conti / vere[:, None], 0.0)   # [i, j] = i dentro j
        caso = larghe / n
        lift = np.where(caso[None, :] > 0, quota / caso[None, :], 0.0)
    return {"quota": quota, "lift": lift, "vere": vere, "copertura": vere / n}


def _prepara(dati, tipo: str, nomi, finestra):
    if tipo not in FINESTRA:
        raise ValueError(f"tipo deve essere uno di {tuple(FINESTRA)}, non {tipo!r}")
    nomi = list(_ELENCO[tipo]()) if nomi is None else list(nomi)
    finestra = FINESTRA[tipo] if finestra is None else int(finestra)
    dati = _come_dizionario(dati)
    return nomi, finestra, {s: _misure(df, tipo, nomi, finestra) for s, df in dati.items()}


def sovrapposizioni(dati, tipo: str = "entry", nomi=None, finestra: int | None = None,
                    soglia: float = SOGLIA_DOPPIONE, lift_min: float = LIFT_MIN,
                    mostra_da: float = 0.60) -> pd.DataFrame:
    """
    Una riga per coppia ordinata (A, B) in cui A sta dentro B per almeno
    `mostra_da` su almeno un symbol. Colonne: contenuta, dentro, quota_min e
    quota_max (in %, fra i symbol), lift_min, una coppia quota/lift per symbol
    e `doppione`: vero se quota >= `soglia` e lift >= `lift_min` su TUTTI i
    symbol. Ordinata per doppione, poi quota_min.
    """
    nomi, _, mis = _prepara(dati, tipo, nomi, finestra)
    simboli = list(mis)
    righe = []
    for i, a in enumerate(nomi):
        for j, b in enumerate(nomi):
            if i == j:
                continue
            q = [mis[s]["quota"][i, j] for s in simboli]
            l = [mis[s]["lift"][i, j] for s in simboli]
            if max(q) < mostra_da:
                continue
            riga = {"contenuta": a, "dentro": b, "quota_min": round(100 * min(q), 1),
                    "quota_max": round(100 * max(q), 1), "lift_min": round(min(l), 2),
                    "doppione": bool(min(q) >= soglia and min(l) >= lift_min)}
            for s, qq, ll in zip(simboli, q, l):
                etichetta = f"_{s}" if s else ""
                riga[f"quota{etichetta}"] = round(100 * qq, 1)
                riga[f"lift{etichetta}"] = round(ll, 2)
            righe.append(riga)
    colonne = ["contenuta", "dentro", "quota_min", "quota_max", "lift_min", "doppione"]
    if not righe:
        return pd.DataFrame(columns=colonne)
    return (pd.DataFrame(righe).sort_values(["doppione", "quota_min"], ascending=False)
            .reset_index(drop=True))


def _somiglianza(mis: dict, lift_min: float) -> np.ndarray:
    sim = None
    for m in mis.values():
        x = np.where(m["lift"] >= lift_min, m["quota"], 0.0)
        x = np.maximum(x, x.T)
        sim = x if sim is None else np.minimum(sim, x)
    np.fill_diagonal(sim, 1.0)
    return sim


def somiglianze(dati, tipo: str = "entry", nomi=None, finestra: int | None = None,
                lift_min: float = LIFT_MIN) -> pd.DataFrame:
    """La matrice di somiglianza (0..1, simmetrica, 1 sulla diagonale) fra le condizioni."""
    nomi, _, mis = _prepara(dati, tipo, nomi, finestra)
    return pd.DataFrame(_somiglianza(mis, lift_min), index=nomi, columns=nomi)


def famiglie(dati, tipo: str = "entry", nomi=None, finestra: int | None = None,
             soglia: float = SOGLIA_FAMIGLIA, lift_min: float = LIFT_MIN) -> pd.DataFrame:
    """
    Le condizioni raggruppate in famiglie, una riga per condizione:

        famiglia     numero (1 = la famiglia piu' numerosa)
        membri       quante condizioni ha la famiglia
        piu_vicina   la condizione piu' simile fuori da se'
        somiglianza  quanto le somiglia, in % (0 se nessuna oltre il caso)
        vere_<sym>   eventi (entry) o barre vere (filtri, uscite) per symbol

    Una condizione con `membri` = 1 apre una famiglia sua: porta un'idea che
    nel catalogo non c'e'. Ordinata per famiglia, poi per nome.
    """
    nomi, _, mis = _prepara(dati, tipo, nomi, finestra)
    if not nomi:
        return pd.DataFrame(columns=["nome", "famiglia", "membri", "piu_vicina", "somiglianza"])
    sim = _somiglianza(mis, lift_min)
    if len(nomi) == 1:
        etichette = np.array([1])
    else:
        legami = linkage(squareform(1.0 - sim, checks=False), method="average")
        etichette = fcluster(legami, t=1.0 - soglia, criterion="distance")
    gruppi: dict[int, list[str]] = {}
    for n, e in zip(nomi, etichette):
        gruppi.setdefault(int(e), []).append(n)
    ordine = sorted(gruppi.values(), key=lambda g: (-len(g), min(g)))
    numero = {n: k + 1 for k, g in enumerate(ordine) for n in g}
    righe = []
    for i, n in enumerate(nomi):
        altre = sim[i].copy()
        altre[i] = -1.0
        j = int(np.argmax(altre)) if len(nomi) > 1 else i
        riga = {"nome": n, "famiglia": numero[n], "membri": len(ordine[numero[n] - 1]),
                "piu_vicina": nomi[j] if altre[j] > 0 else None,
                "somiglianza": round(100 * max(altre[j], 0.0), 1)}
        for s, m in mis.items():
            riga[f"vere_{s}" if s else "vere"] = int(m["vere"][i])
        righe.append(riga)
    return pd.DataFrame(righe).sort_values(["famiglia", "nome"]).reset_index(drop=True)
