"""
Collaudo del catalogo delle condizioni: LOOKAHEAD e DEGENERAZIONE.

Lavora su TUTTE le condizioni registrate in engine.registry (entry, exit,
filtri, entry bidirezionali), senza conoscerne il contenuto e senza
importare nessun file di condizioni. Una condizione nuova, registrata con
le solite `registra_*()`, viene collaudata senza toccare questo file.

Quattro funzioni pubbliche:

    condizioni_registrate()      cosa c'e' nel registry, in tabella
    tagli_standard(indice)       dove tagliare lo storico
    verifica_lookahead(...)      la condizione guarda il futuro?
    verifica_degenerazione(...)  la condizione distingue qualcosa?

piu' `mercato_sintetico()`, il generatore di dati finti usato dal notebook
di collaudo.


IL LOOKAHEAD, PER TRONCAMENTO
-----------------------------
Una condizione e' pulita se il suo valore alla barra t dipende solo dalle
barre fino a t (l'ingresso avviene a Open[t+1]: usare Close[t] e' lecito).

Il test:
  1. calcola ogni condizione sullo storico intero;
  2. taglia lo storico alla barra t e lo ricalcola DA ZERO, indicatori
     compresi (la funzione `prepara`), poi ricalcola la condizione;
  3. confronta TUTTE le barre fino a t. Se una sola e' diversa, quel
     valore dipendeva da qualcosa che veniva dopo t.

Perche' il troncamento e non "il futuro sostituito con spazzatura":
  - le cache di quarantena usano come chiave (lunghezza, prima, ultima
    barra): con la spazzatura l'indice resta identico e la cache
    restituirebbe la quarantena calcolata sui dati puliti, nascondendo un
    eventuale lookahead. Col troncamento la chiave cambia a ogni taglio;
  - col troncamento spariscono anche i timestamp futuri: si prende anche
    il lookahead del tipo "la barra dopo non c'e', quindi questa e'
    l'ultima prima della pausa".

Dove si taglia, per ogni condizione:
  - tagli COMUNI: uno per ogni quarto d'ora del giorno, su giorni scelti a
    caso, piu' i bordi del weekend. Prendono il lookahead legato
    all'orario;
  - tagli MIRATI: alcune barre scelte fra quelle in cui la condizione e'
    vera sullo storico intero. Un lookahead tipo `shift(-1)` cambia solo
    la barra del taglio, e su un'entry rara un taglio a caso cade quasi
    sempre su una barra falsa, dove non si vede niente. Tagliando dove la
    condizione e' vera, si vede.

Il limite, dichiarato: una condizione mai vera sullo storico non puo'
essere verificata (falsa prima e dopo il taglio non dimostra niente). Il
report la marca NON_ESERCITATA, non OK.

Modulo ADDITIVO: non modifica nessun file esistente dell'engine.
"""
from __future__ import annotations

import os
import sys
from typing import Callable

import numpy as np
import pandas as pd

from engine import registry as _reg

TIPI = ("entry", "exit", "filtro", "bidir")

# cartella del progetto (quella che contiene engine/): solo i moduli che
# stanno qui dentro vengono considerati da _svuota_cache()
_RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# =========================================================================
# Il catalogo
# =========================================================================
def condizioni_registrate() -> pd.DataFrame:
    """
    Tutte le condizioni oggi registrate nel motore, una per riga.

    Colonne: tipo (entry / exit / filtro / bidir), nome, direction, pair.
    Non calcola niente: legge solo il registry.
    """
    righe = []
    for nome in _reg.list_entries():
        righe.append(("entry", nome, _reg.get_entry_direction(nome), None))
    for nome in _reg.list_exits():
        righe.append(("exit", nome, _reg.get_exit_direction(nome), _reg.get_exit_pair(nome)))
    for nome in _reg.list_filters():
        righe.append(("filtro", nome, _reg.get_filter_direction(nome), _reg.get_filter_pair(nome)))
    for nome in _reg.list_bidirectional_entries():
        righe.append(("bidir", nome, None, None))
    return pd.DataFrame(righe, columns=["tipo", "nome", "direction", "pair"])


def _funzione(tipo: str, nome: str) -> Callable:
    return {
        "entry": _reg.get_entry,
        "exit": _reg.get_exit,
        "filtro": _reg.get_filter,
        "bidir": _reg.get_bidirectional_entry,
    }[tipo](nome)


def _svuota_cache() -> None:
    """
    Svuota ogni cache del progetto: chiama `svuota_cache()` su ogni modulo
    del progetto gia' caricato che la espone (oggi engine.livelli ed entry_metro). Cosi' anche
    una cache aggiunta domani in un file nuovo viene svuotata.
    """
    for modulo in list(sys.modules.values()):
        percorso = str(getattr(modulo, "__file__", "") or "")
        if not percorso.startswith(_RADICE):
            continue
        f = getattr(modulo, "svuota_cache", None)
        if callable(f):
            try:
                f()
            except Exception:
                pass


def _valuta(tipo: str, nome: str, df: pd.DataFrame):
    """(Series, None) se la condizione gira, (None, messaggio) se no."""
    try:
        s = _funzione(tipo, nome)(df)
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    if not isinstance(s, pd.Series):
        return None, f"restituisce {type(s).__name__}, non una pd.Series"
    if len(s) != len(df) or not s.index.equals(df.index):
        return None, "la Series restituita non ha lo stesso indice del df"
    return s, None


def _attiva(s: pd.Series) -> np.ndarray:
    """Dove la condizione 'scatta': True per i booleani, != 0 per i numerici."""
    v = s.to_numpy()
    if v.dtype == bool:
        return v
    num = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
    return np.nan_to_num(num, nan=0.0) != 0


def _diversi(a: pd.Series, b: pd.Series) -> np.ndarray:
    """Maschera delle barre in cui a e b differiscono (NaN == NaN)."""
    va, vb = a.to_numpy(), b.to_numpy()
    try:
        fa = va.astype(float)
        fb = vb.astype(float)
        uguali = (fa == fb) | (np.isnan(fa) & np.isnan(fb))
    except (TypeError, ValueError):
        uguali = np.array([(x == y) or (pd.isna(x) and pd.isna(y))
                           for x, y in zip(va, vb)], dtype=bool)
    return ~uguali


# =========================================================================
# Dove tagliare
# =========================================================================
def tagli_standard(indice: pd.DatetimeIndex, seme: int = 0,
                   riscaldamento: int = 3000, n_weekend: int = 8) -> list[int]:
    """
    Le posizioni (0, 1, 2, ...) delle barre in cui tagliare lo storico.

    - una barra per ogni orario del giorno presente nell'indice (96 su M15,
      in ora UTC), ciascuna su un giorno scelto a caso;
    - `n_weekend` barre sui bordi delle pause lunghe (ultima barra prima,
      prima barra dopo), meta' e meta';
    - mai nelle prime `riscaldamento` barre: servono agli indicatori e alle
      finestre lunghe (E7 usa 2000 barre).
    """
    idx = pd.DatetimeIndex(indice)
    rng = np.random.default_rng(seme)
    pos = np.arange(riscaldamento, len(idx) - 1)
    if len(pos) == 0:
        raise ValueError(
            f"Storico troppo corto: {len(idx)} barre, riscaldamento {riscaldamento}."
        )

    tagli = set()
    orari = idx[pos].strftime("%H:%M")
    for orario in np.unique(orari):
        candidati = pos[orari == orario]
        tagli.add(int(rng.choice(candidati)))

    salto = pd.Series(idx).diff().dt.total_seconds().to_numpy()
    dopo = np.flatnonzero(salto > 6 * 3600)          # prima barra dopo la pausa
    dopo = dopo[(dopo > riscaldamento) & (dopo < len(idx) - 1)]
    prima = dopo - 1                                  # ultima barra prima
    for gruppo in (prima, dopo):
        if len(gruppo):
            k = min(len(gruppo), n_weekend // 2)
            tagli.update(int(x) for x in rng.choice(gruppo, size=k, replace=False))
    return sorted(tagli)


# =========================================================================
# LOOKAHEAD
# =========================================================================
def verifica_lookahead(
    df_grezzo: pd.DataFrame,
    prepara: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
    tagli: list[int] | None = None,
    tagli_per_condizione: int = 5,
    seme: int = 0,
    riscaldamento: int = 3000,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Verifica di lookahead per troncamento su tutto il catalogo registrato e
    su tutti gli indicatori creati da `prepara`.

    Parametri
    ---------
    df_grezzo : i dati GREZZI (Open, High, Low, Close, Volume), indice UTC,
        senza indicatori: vengono ricalcolati a ogni taglio.
    prepara : funzione df_grezzo -> df con indicatori. Default:
        engine.indicatori.aggiungi_indicatori.
    tagli : posizioni dei tagli comuni. Default: tagli_standard().
    tagli_per_condizione : tagli mirati, per ogni condizione, su barre in
        cui la condizione e' vera sullo storico intero.

    Restituisce
    -----------
    Un DataFrame, una riga per condizione e una per indicatore:

        tipo                entry / exit / filtro / bidir / indicatore
        nome
        esito               OK · LOOKAHEAD · NON_ESERCITATA · ERRORE
        tagli               quanti tagli sono stati provati
        tagli_con_differenze
        barre_diverse       somma, su tutti i tagli, delle barre cambiate
        vere_nel_pieno      barre in cui la condizione scatta sullo storico
        primo_caso          la prima differenza trovata, in chiaro
        errore              il messaggio, se la condizione non gira

    Ordine degli esiti: ERRORE, poi LOOKAHEAD, poi NON_ESERCITATA, poi OK.
    """
    if prepara is None:
        from engine.indicatori import aggiungi_indicatori as prepara

    grezzo = df_grezzo
    _svuota_cache()
    pieno = prepara(grezzo)
    _svuota_cache()

    indicatori = [c for c in pieno.columns if c not in grezzo.columns]
    catalogo = condizioni_registrate()
    chiavi = list(zip(catalogo["tipo"], catalogo["nome"]))

    # --- valori sullo storico intero -------------------------------------
    valori_pieni, errori = {}, {}
    for chiave in chiavi:
        s, err = _valuta(*chiave, pieno)
        if err:
            errori[chiave] = err
        else:
            valori_pieni[chiave] = s

    # --- piano dei tagli: posizione -> condizioni da valutare ------------
    if tagli is None:
        tagli = tagli_standard(grezzo.index, seme=seme, riscaldamento=riscaldamento)
    comuni = [int(t) for t in tagli]
    piano: dict[int, set] = {t: set(valori_pieni) | {"__indicatori__"} for t in comuni}
    n_tagli = {k: len(comuni) for k in valori_pieni}

    # Tagli mirati. Per risparmiare tempo si riusano i tagli gia' in piano:
    # se la condizione e' vera su una barra dove qualcun altro taglia gia',
    # basta valutarla anche li'. Si parte dalle condizioni piu' rare, cosi'
    # le frequenti trovano gia' molti tagli da riusare.
    pos_grezzo = pd.Series(np.arange(len(grezzo)), index=grezzo.index)
    rng = np.random.default_rng(seme + 1)
    posizioni_vere = {}
    for chiave, s in valori_pieni.items():
        vere = s.index[_attiva(s)]
        pos = pos_grezzo.reindex(vere).dropna().astype(int).to_numpy()
        posizioni_vere[chiave] = pos[(pos >= riscaldamento) & (pos < len(grezzo) - 1)]
    set_comuni = set(comuni)
    for chiave in sorted(posizioni_vere, key=lambda c: len(posizioni_vere[c])):
        pos = posizioni_vere[chiave]
        if len(pos) == 0:
            continue
        gia = [int(t) for t in pos if int(t) in piano]
        mirati = [t for t in gia if t in set_comuni]      # gia' valutata li'
        for t in gia:
            if len(mirati) >= tagli_per_condizione:
                break
            if t not in set_comuni:
                piano[t].add(chiave)
                mirati.append(t)
        resto = np.setdiff1d(pos, np.array(gia, dtype=int))
        mancano = tagli_per_condizione - len(mirati)
        if mancano > 0 and len(resto):
            for t in rng.choice(resto, size=min(len(resto), mancano), replace=False):
                piano.setdefault(int(t), set()).add(chiave)
                mirati.append(int(t))
        n_tagli[chiave] += len([t for t in mirati if t not in set_comuni])

    # --- esecuzione ------------------------------------------------------
    diff_tagli = {k: 0 for k in list(valori_pieni) + [("indicatore", c) for c in indicatori]}
    diff_barre = dict.fromkeys(diff_tagli, 0)
    primo = {}
    righe_diverse = []    # prepara ha prodotto righe diverse: lookahead nel prepara

    def _annota(chiave, a_pieno, a_tagliato, t_ts):
        mask = _diversi(a_pieno, a_tagliato)
        n = int(mask.sum())
        if n:
            diff_tagli[chiave] += 1
            diff_barre[chiave] += n
            if chiave not in primo:
                i = int(np.flatnonzero(mask)[0])
                primo[chiave] = (
                    f"barra {a_pieno.index[i]}: storico intero {a_pieno.iloc[i]}, "
                    f"tagliato {a_tagliato.iloc[i]} (taglio a {t_ts})"
                )

    ordine = sorted(piano)
    for k, t in enumerate(ordine, 1):
        if verbose and (k == 1 or k % 25 == 0 or k == len(ordine)):
            print(f"[verifica_lookahead] taglio {k}/{len(ordine)}", flush=True)
        t_ts = grezzo.index[t]
        # la cache si svuota una volta per taglio: dentro lo stesso taglio le
        # condizioni condividono la quarantena del PREFISSO, che e' corretta
        _svuota_cache()
        try:
            parziale = prepara(grezzo.iloc[: t + 1])
        except Exception as e:
            for chiave in piano[t]:
                if chiave != "__indicatori__":
                    errori.setdefault(chiave, f"prepara fallisce sul taglio {t_ts}: {e}")
            continue
        _svuota_cache()

        # righe prodotte da prepara: devono essere quelle dello storico intero fino a t
        attese = pieno.index[pieno.index <= t_ts]
        if not parziale.index.equals(attese):
            righe_diverse.append(t_ts)
        comuni_idx = parziale.index.intersection(pieno.index)

        if "__indicatori__" in piano[t]:
            for c in indicatori:
                _annota(("indicatore", c), pieno[c].loc[comuni_idx],
                        parziale[c].loc[comuni_idx], t_ts)

        for chiave in piano[t]:
            if chiave == "__indicatori__" or chiave in errori:
                continue
            s, err = _valuta(*chiave, parziale)
            if err:
                errori[chiave] = f"sul taglio {t_ts}: {err}"
                continue
            _annota(chiave, valori_pieni[chiave].loc[comuni_idx], s.loc[comuni_idx], t_ts)

    # --- tabella ---------------------------------------------------------
    righe = []
    for chiave in chiavi:
        tipo, nome = chiave
        s = valori_pieni.get(chiave)
        vere = int(_attiva(s).sum()) if s is not None else np.nan
        if chiave in errori:
            esito = "ERRORE"
        elif diff_tagli[chiave]:
            esito = "LOOKAHEAD"
        elif vere == 0:
            esito = "NON_ESERCITATA"
        else:
            esito = "OK"
        righe.append({
            "tipo": tipo, "nome": nome, "esito": esito,
            "tagli": n_tagli.get(chiave, 0),
            "tagli_con_differenze": diff_tagli.get(chiave, 0),
            "barre_diverse": diff_barre.get(chiave, 0),
            "vere_nel_pieno": vere,
            "primo_caso": primo.get(chiave, ""),
            "errore": errori.get(chiave, ""),
        })
    for c in indicatori:
        chiave = ("indicatore", c)
        righe.append({
            "tipo": "indicatore", "nome": c,
            "esito": "LOOKAHEAD" if diff_tagli[chiave] else "OK",
            "tagli": len(comuni),
            "tagli_con_differenze": diff_tagli[chiave],
            "barre_diverse": diff_barre[chiave],
            "vere_nel_pieno": np.nan,
            "primo_caso": primo.get(chiave, ""),
            "errore": "",
        })
    if righe_diverse:
        righe.append({
            "tipo": "indicatore", "nome": "(righe prodotte da prepara)",
            "esito": "LOOKAHEAD", "tagli": len(ordine),
            "tagli_con_differenze": len(righe_diverse), "barre_diverse": np.nan,
            "vere_nel_pieno": np.nan,
            "primo_caso": f"sul taglio {righe_diverse[0]} prepara tiene righe diverse "
                          f"da quelle dello storico intero (es. dropna che guarda avanti)",
            "errore": "",
        })

    report = pd.DataFrame(righe)
    ordine_esiti = {"ERRORE": 0, "LOOKAHEAD": 1, "NON_ESERCITATA": 2, "OK": 3}
    report = (report.assign(_o=report["esito"].map(ordine_esiti))
              .sort_values(["_o", "tipo", "nome"], kind="stable")
              .drop(columns="_o").reset_index(drop=True))
    if verbose:
        conta = report["esito"].value_counts()
        print(
            f"[verifica_lookahead] {len(report)} righe · "
            f"LOOKAHEAD: {conta.get('LOOKAHEAD', 0)} · ERRORE: {conta.get('ERRORE', 0)} · "
            f"NON_ESERCITATE: {conta.get('NON_ESERCITATA', 0)} · OK: {conta.get('OK', 0)}"
        )
    return report


# =========================================================================
# DEGENERAZIONE
# =========================================================================
def verifica_degenerazione(
    df: pd.DataFrame,
    min_occorrenze: int = 30,
    copertura_max: float = 0.95,
    distanza_grappolo: int = 8,
    attese: tuple = ("X0_NO_EXIT", "X0_SHORT_NO_EXIT"),
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Una condizione e' degenere quando non distingue niente. Tre modi:
    mai vera, (quasi) sempre vera, troppo rara per misurare qualcosa.

    Parametri
    ---------
    df : dati CON indicatori (quelli su cui gira la ricerca).
    min_occorrenze : sotto questa soglia la condizione e' RARA. Per le entry
        si contano gli eventi; per filtri ed exit le barre vere (per un
        filtro un'occorrenza e' una barra in cui lascia entrare).
    copertura_max : a questa quota di barre vere, o sopra, la condizione e'
        QUASI_SEMPRE_VERA: non scarta quasi niente.
    distanza_grappolo : due eventi di un'entry a distanza <= di queste barre
        appartengono allo stesso grappolo. Solo informativo.
    attese : condizioni degeneri per costruzione (le exit "nessuna uscita"):
        marcate ATTESA invece che segnalate.

    Restituisce
    -----------
    Un DataFrame, una riga per condizione:

        tipo, nome, direction
        barre_vere          barre in cui la condizione e' vera
        eventi              quante volte DIVENTA vera (blocchi separati)
        eventi_anno
        copertura           quota di barre vere (0-1)
        barre_consecutive   solo entry: barre vere subito dopo un'altra vera
        grappoli            solo entry: gruppi di eventi vicini
        quota_in_grappolo   solo entry: eventi che cadono in un gruppo gia' aperto
        esito               OK · SEMPRE_FALSA · SEMPRE_VERA · QUASI_SEMPRE_VERA
                            · RARA · STATO · NON_BOOLEANA · ERRORE · ATTESA
        errore

    STATO: un'entry vera su barre consecutive. La convenzione del progetto
    vuole le entry come eventi (`_evento`): e' un errore di scrittura.
    I grappoli (eventi vicini ma separati da barre false) invece sono
    legittimi e non cambiano l'esito.
    """
    n = len(df)
    anni = (df.index[-1] - df.index[0]).total_seconds() / (365.25 * 86400) if n > 1 else np.nan
    righe = []
    _svuota_cache()
    for _, r in condizioni_registrate().iterrows():
        tipo, nome = r["tipo"], r["nome"]
        riga = {"tipo": tipo, "nome": nome, "direction": r["direction"],
                "barre_vere": np.nan, "eventi": np.nan, "eventi_anno": np.nan,
                "copertura": np.nan, "barre_consecutive": np.nan,
                "grappoli": np.nan, "quota_in_grappolo": np.nan,
                "esito": "", "errore": ""}
        s, err = _valuta(tipo, nome, df)
        if err:
            riga.update(esito="ERRORE", errore=err)
            righe.append(riga)
            continue

        booleana = s.dtype == bool
        m = _attiva(s)
        inizio = m & ~np.r_[False, m[:-1]]
        vere, eventi = int(m.sum()), int(inizio.sum())
        riga.update(barre_vere=vere, eventi=eventi,
                    eventi_anno=eventi / anni if anni else np.nan,
                    copertura=vere / n if n else np.nan)

        is_entry = tipo in ("entry", "bidir")
        if is_entry:
            riga["barre_consecutive"] = vere - eventi
            pos = np.flatnonzero(inizio)
            if len(pos):
                grappoli = 1 + int((np.diff(pos) > distanza_grappolo).sum())
                riga["grappoli"] = grappoli
                riga["quota_in_grappolo"] = (len(pos) - grappoli) / len(pos)
            else:
                riga["grappoli"] = 0

        occorrenze = eventi if is_entry else vere
        if nome in attese:
            esito = "ATTESA"
        elif not booleana and tipo != "bidir":
            esito = "NON_BOOLEANA"
        elif vere == 0:
            esito = "SEMPRE_FALSA"
        elif vere == n:
            esito = "SEMPRE_VERA"
        elif is_entry and vere > eventi:
            esito = "STATO"
        elif vere / n >= copertura_max:
            esito = "QUASI_SEMPRE_VERA"
        elif occorrenze < min_occorrenze:
            esito = "RARA"
        else:
            esito = "OK"
        riga["esito"] = esito
        righe.append(riga)

    report = pd.DataFrame(righe)
    if verbose and len(report):
        conta = report["esito"].value_counts()
        print(f"[verifica_degenerazione] {len(report)} condizioni su {n:,} barre "
              f"({anni:.1f} anni) · " + " · ".join(f"{k}: {v}" for k, v in conta.items()))
    return report


# =========================================================================
# Dati sintetici
# =========================================================================
def mercato_sintetico(inizio: str = "2024-08-01", fine: str = "2024-12-01",
                      seme: int = 0, prezzo: float = 1.10,
                      vol_barra: float = 0.0004, gap_open: float = 0.0001) -> pd.DataFrame:
    """
    Random walk M15 su indice UTC, con il weekend forex tolto (da venerdi'
    17:00 a domenica 17:00 di New York). Il default (quattro mesi, circa
    8.500 barre) copre i cambi d'ora d'autunno, Europa il 27/10 e USA il
    3/11, con la settimana in cui i due orari sono sfasati.

    Colonne: Open, High, Low, Close, Volume.

    `gap_open`: deviazione standard dello scarto fra Open e Close della
    barra prima. Se Open fosse sempre uguale alla chiusura precedente,
    alcuni pattern TA-Lib non potrebbero mai scattare e resterebbero non
    verificabili.
    """
    idx = pd.date_range(inizio, fine, freq="15min", tz="UTC", inclusive="left")
    ny = idx.tz_convert("America/New_York")
    minuti = ny.hour * 60 + ny.minute
    chiuso = (
        ((ny.dayofweek == 4) & (minuti >= 17 * 60))
        | (ny.dayofweek == 5)
        | ((ny.dayofweek == 6) & (minuti < 17 * 60))
    )
    idx = idx[~chiuso]
    rng = np.random.default_rng(seme)
    n = len(idx)
    close = prezzo * np.exp(np.cumsum(rng.normal(0, vol_barra / prezzo, n)))
    op = np.r_[close[0], close[:-1]] + rng.normal(0, gap_open, n)
    salto_h = np.abs(rng.normal(0, vol_barra * 0.75, n))
    salto_l = np.abs(rng.normal(0, vol_barra * 0.75, n))
    return pd.DataFrame(
        {
            "Open": op,
            "High": np.maximum(op, close) + salto_h,
            "Low": np.minimum(op, close) - salto_l,
            "Close": close,
            "Volume": rng.integers(20, 2000, n).astype(float),
        },
        index=idx,
    )
