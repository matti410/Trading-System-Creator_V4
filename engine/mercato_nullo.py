"""
Mercato nullo — quanto si inganna la pipeline senza nessun vantaggio (21/10/2026,
docs/63 §7, lavoro D1).

COSA FA
-------
Ripete molte volte la pipeline del Lab (rosa dei trigger, uscite, ricerca dei
filtri con le due meta', scheda) su trigger FINTI, che per costruzione non
sanno niente del futuro, e registra fin dove arriva. Il risultato e' la
distribuzione dei numeri con cui la pipeline arriva in fondo e la SOGLIA
EMPIRICA: «nel nulla, la pipeline arriva a un t >= X nel 5% dei giri».

LA SOGLIA E' UN PAVIMENTO (docs/63 §10.1 punto 5). La regola automatica delle
scelte (sotto) percorre una strada per giro, piu' le due del «migliore dei
primi 3»; nell'uso vero si provano piu' trigger e piu' uscite prima di
scegliere. La soglia e' quindi il MINIMO dell'autoinganno, non la sua misura
esatta. E' SOLO INFORMATIVA (docs/63 §10.2 domanda 17): nessun cancello cambia.

IL NULLA N1 · TRIGGER CASUALI (§7.2)
------------------------------------
Per ogni entry vera del catalogo (le stesse della rosa del Lab) una entry
finta con lo stesso lato, lo stesso numero di eventi utili e la stessa
distribuzione per fascia oraria (stagionalita.fasce_orarie, come la rosa),
messi su giornate scelte a caso fra le barre utili (ne' la barra del segnale
ne' quella d'ingresso in quarantena, non l'ultima barra). Restano veri i
prezzi, i costi (funding compreso), le sessioni, i regimi, la quarantena. I
filtri possono trovare effetti veri del mercato (un'ora, un regime) sopra un
trigger finto: contano come falsa scoperta del trigger, ed e' giusto.
Un limite: i trigger veri arrivano spesso a grappoli, quelli finti molto meno
(l'incertezza della rosa tiene gia' conto dei grappoli: effetto piccolo).

LA REGOLA AUTOMATICA DELLE SCELTE (§7.3), strada A (D1)
--------------------------------------------------------
  1. trigger: per lato, il primo della rosa (nell'ordine della tabella); se la
     rosa del lato e' vuota, quello con il t netto piu' alto;
  2. uscite: quelle predefinite di vetrina.imposta_uscite (a tempo dopo H
     barre, stop adattivo al 90° percentile, niente target, nessuna regola);
  3. passo 5: vetrina.trova_strategia (tutti i filtri, due meta'); il primo
     filtro che «regge» nella classifica (t del miglioramento piu' alto),
     altrimenti il sistema base;
  4. giudizio: la scheda sull'IN-SAMPLE (scheda_strategia, come il Lab):
     esito, t, P(EV<0), trade. L'out-of-sample non si tocca mai.
  5. il «migliore dei primi 3»: le strade k = 1, 2, 3 con il k-esimo trigger
     di ogni lato (i primi 3 della rosa, completati con i t netti piu' alti),
     stesse uscite e stesso passo 5; si registra quella con il t della scheda
     piu' alto (colonne m3_*). La strada k = 1 e' la regola del punto 1.

Ogni giro e' una riga del CSV dati/nullo/<SYMBOL>_<TF>_H<H>_<strada>.csv, con
in testa (righe «# chiave: valore») versione del catalogo, symbol, timeframe,
H, unita', funding, modo, strada e data. Un giro interrotto riprende da dove
si e' fermato: i giri gia' scritti non si rifanno, e un file con
un'intestazione diversa (altro catalogo, altro H...) ferma tutto.

Modulo ADDITIVO.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import os
import time
import zlib

import numpy as np
import pandas as pd

from . import registry as reg
from .quarantena_trade import maschera_segnali_puliti
from .stagionalita import fasce_orarie

PREFISSO = "N1_"                 # nome delle entry finte nel registro
STRADE = ("A",)                  # D1: filtri a tappeto. La strada B (atlante) arriva con il lavoro C
MODI = ("N1",)
QUOTA = 0.05                     # la soglia empirica: il t superato nel 5% dei giri
PRIMI = 3                        # il «migliore dei primi 3» (§10.1 punto 5)

COLONNE = ["giro", "seme", "secondi", "rosa_long", "rosa_short", "trigger_long", "trigger_short",
           "base_trade", "base_t", "promossi", "reggono", "filtro", "esito", "t", "p_ev_neg", "trade",
           "ev_bp", "m3_k", "m3_trigger_long", "m3_trigger_short", "m3_filtro", "m3_esito", "m3_t",
           "m3_p_ev_neg", "m3_trade", "m3_ev_bp"]
CHIAVI_INTESTAZIONE = ("versione_catalogo", "symbol", "timeframe", "H", "unita", "funding", "modo", "strada")


# ========================================================================
# Catalogo e trigger finti
# ========================================================================

def versione_catalogo() -> str:
    """
    La versione del catalogo registrato: numero di entry, filtri e uscite piu'
    un'impronta dei nomi (le entry finte non contano). Se cambia una condizione
    il mercato nullo va rifatto.
    """
    # solo le condizioni che la pipeline usa: le entry vere della rosa (niente metro, composite,
    # congelate, orarie: vetrina._trigger_candidati), i filtri del catalogo (non i CONF_ della
    # confidenza, che nascono nel notebook) e le uscite non orarie (X_ORA_ si registra quando la scegli)
    from .vetrina import _trigger_candidati
    entry = sorted(n for n in _trigger_candidati() if not n.startswith(PREFISSO))
    filtri = sorted(n for n in reg.list_filters(0) + reg.list_filters(1) + reg.list_filters(-1)
                    if not n.startswith("CONF_"))
    uscite = sorted(n for n in reg.list_exits() if not n.startswith(("X_ORA_", "X_INVERSIONE")))
    impronta = hashlib.sha1("|".join(entry + ["#"] + filtri + ["#"] + uscite).encode("utf-8")).hexdigest()[:10]
    return f"{len(entry)} entry, {len(filtri)} filtri, {len(uscite)} uscite · {impronta}"


def barre_utili(df_is: pd.DataFrame) -> np.ndarray:
    """Dove un segnale puo' diventare un trade: ne' il segnale ne' l'ingresso in quarantena, non l'ultima barra."""
    ok = np.asarray(maschera_segnali_puliti(df_is, True), dtype=bool).copy()
    if len(ok):
        ok[-1] = False
    return ok


def conteggi_veri(df_is: pd.DataFrame, nomi, fuso: str) -> dict:
    """
    Per ogni entry vera: (direzione, {fascia oraria: eventi utili}). Si calcola
    una volta per symbol: i trigger finti di ogni giro ne copiano i numeri.
    """
    codici = fasce_orarie(df_is.index, fuso)[0]
    utili = barre_utili(df_is)
    out = {}
    for nome in nomi:
        vero = reg.get_entry(nome)(df_is).fillna(False).astype(bool).to_numpy() & utili
        fasce, quanti = np.unique(codici[vero], return_counts=True)
        out[nome] = (int(reg.get_entry_direction(nome)), dict(zip(fasce.tolist(), quanti.tolist())))
    return out


def trigger_casuali(df_is: pd.DataFrame, nomi, seme: int, fuso: str, conteggi: dict | None = None) -> dict:
    """
    Le maschere (array booleani allineati a df_is) delle entry finte del giro
    `seme`: per ogni entry vera, in ogni fascia oraria, tanti eventi quanti ne
    ha il vero, su barre utili della stessa fascia scelte a caso senza
    ripetizioni (una barra per fascia e per giornata: giornate a caso). Lo
    stesso seme da' le stesse maschere; ogni entry ha il suo generatore, quindi
    il risultato non dipende dall'ordine dei nomi.
    """
    conteggi = conteggi_veri(df_is, nomi, fuso) if conteggi is None else conteggi
    codici = fasce_orarie(df_is.index, fuso)[0]
    utili = barre_utili(df_is)
    per_fascia = {c: np.flatnonzero(utili & (codici == c)) for c in np.unique(codici)}
    maschere = {}
    for nome in nomi:
        rng = np.random.default_rng([int(seme), zlib.crc32(nome.encode("utf-8"))])
        m = np.zeros(len(df_is), dtype=bool)
        for fascia, k in sorted(conteggi[nome][1].items()):
            vasca = per_fascia.get(fascia, np.array([], dtype=int))
            if len(vasca):
                m[rng.choice(vasca, size=min(int(k), len(vasca)), replace=False)] = True
        maschere[nome] = m
    return maschere


def registra_finti(maschere: dict, conteggi: dict, indice: pd.DatetimeIndex) -> list[str]:
    """
    Registra le entry finte (PREFISSO + nome vero, stesso lato), dopo aver tolto
    quelle del giro prima (comprese le «congelate» con un filtro). Ogni entry
    restituisce la sua maschera sull'indice che riceve (in-sample o una meta').
    """
    reg.remove_entries(PREFISSO)
    nomi = []
    for nome, m in maschere.items():
        serie = pd.Series(m, index=indice)
        finto = PREFISSO + nome
        reg.register_entry(finto, conteggi[nome][0])(
            lambda d, serie=serie: serie.reindex(d.index, fill_value=False))
        nomi.append(finto)
    return nomi


# ========================================================================
# Un giro
# ========================================================================

def _primi(rosa: pd.DataFrame, direzione: int, k: int = PRIMI) -> tuple[list, int]:
    """I primi k trigger di un lato: quelli nella rosa (in ordine), poi i t netti piu' alti."""
    lato = rosa[rosa["direction"] == direzione]
    nella = lato[lato["nella_rosa"].astype(bool)]
    resto = lato[~lato["nella_rosa"].astype(bool)].sort_values("t_netto", ascending=False, na_position="last")
    return (list(nella["candidato"]) + list(resto["candidato"]))[:k], int(len(nella))


def _percorso(s, long, short) -> dict:
    """Uscite predefinite, passo 5, scheda in-sample: le scelte 2-4 del §7.3."""
    from . import vetrina as v
    from .filter_search_bt import BASELINE
    from .giudizio import scheda_strategia
    import matplotlib.pyplot as plt
    # senza stampe ne' barre di avanzamento della libreria (stderr): 3 strade per giro, centinaia di giri
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        v.scegli_trigger(s, long=long, short=short)
        v.imposta_uscite(s)
        v.trova_strategia(s)
        r = s.fs.risultati.set_index("filtro")
        filtro = max(s.sopravvissuti, key=lambda f: r.at[f, "t_guadagno"]) if s.sopravvissuti else None
        _, _, fs_ultimo, _ = v._catena_filtri(s, [filtro] if filtro else [])
        tr = fs_ultimo.trades(filtro)
        k = scheda_strategia(tr, s.fs.pip_size, s.fs.commission or 0.0, montecarlo=False,
                             verbose=False, atr=s.atr, unita=s.unita)
    plt.close("all")
    base = r.loc[BASELINE]
    prove = s.fs.risultati[s.fs.risultati["filtro"] != BASELINE]
    promossi = int(prove["esito"].isin([v.DA_VALUTARE, v.CAMPIONE_CORTO]).sum())
    return {"trigger_long": long, "trigger_short": short, "base_trade": int(base["trades"]),
            "base_t": float(base["t_stat"]) if "t_stat" in base else np.nan,
            "promossi": promossi, "reggono": len(s.sopravvissuti), "filtro": filtro or "",
            "esito": k.get("esito", ""), "t": float(k.get("t_stat", np.nan)),
            "p_ev_neg": float(k.get("p_ev_neg", np.nan)), "trade": int(k.get("n_trades", 0)),
            "ev_bp": float(k.get("ev_bp", np.nan))}


def giro_nullo(s, seme: int, nomi: list, conteggi: dict, finti: bool = True) -> dict:
    """
    Un giro, con le scelte del §7.3. `s` e' una sessione di vetrina.prepara (gli
    indicatori si calcolano una volta). finti=False usa i trigger veri al posto
    dei finti: serve al collaudo (riproduce il Lab).
    """
    from . import vetrina as v
    from .rosa import rosa_entry
    t0 = time.time()
    if finti:
        candidati = registra_finti(trigger_casuali(s.df_is, nomi, seme, s.fuso, conteggi), conteggi, s.df_is.index)
    else:
        candidati = list(nomi)
    with contextlib.redirect_stdout(io.StringIO()):
        rosa = rosa_entry(s.df_is, s.H, s.pip, nomi=candidati, min_eventi=v.MIN_TRIGGER, fuso=s.fuso,
                          atr=s.atr, unita=s.unita)
    s.rosa_trigger = rosa
    if s.ev is None:
        s.ev = "mercato nullo"          # scegli_trigger chiede la schermata 2: qui la sostituisce la rosa
    lati = s.lati()
    longs, n_long = _primi(rosa, 1) if 1 in lati else ([], 0)
    shorts, n_short = _primi(rosa, -1) if -1 in lati else ([], 0)
    # strada k: il k-esimo trigger di ogni lato (un lato con meno di 3 candidati ripete l'ultimo)
    strade = []
    for k in range(min(PRIMI, max(len(longs), len(shorts)))):
        lo = longs[min(k, len(longs) - 1)] if longs else None
        sh = shorts[min(k, len(shorts) - 1)] if shorts else None
        strade.append(_percorso(s, lo, sh))
    riga = {"giro": None, "seme": int(seme), "rosa_long": n_long, "rosa_short": n_short}
    if strade:
        riga.update(strade[0])
        t_strade = [x["t"] if np.isfinite(x["t"]) else -np.inf for x in strade]
        m = int(np.argmax(t_strade))
        riga.update({f"m3_{c}": strade[m][c] for c in ("trigger_long", "trigger_short", "filtro", "esito",
                                                       "t", "p_ev_neg", "trade", "ev_bp")})
        riga["m3_k"] = m + 1
    riga["secondi"] = round(time.time() - t0, 1)
    if finti:
        reg.remove_entries(PREFISSO)
    return riga


# ========================================================================
# Tanti giri, con ripresa
# ========================================================================

def file_nullo(symbol: str, timeframe: str = "M15", H: int = 25, strada: str = "A", cartella="dati") -> str:
    return os.path.join(str(cartella), "nullo", f"{symbol}_{timeframe}_H{int(H)}_{strada}.csv")


def leggi_intestazione(percorso) -> dict:
    """Le righe «# chiave: valore» in testa al CSV."""
    testa = {}
    with open(percorso, encoding="utf-8") as f:
        for riga in f:
            if not riga.startswith("#"):
                break
            if ":" in riga:
                k, val = riga[1:].split(":", 1)
                testa[k.strip()] = val.strip()
    return testa


def leggi_nullo(percorso) -> pd.DataFrame:
    """I giri gia' scritti (le righe d'intestazione si saltano; un filtro vuoto resta «»)."""
    tab = pd.read_csv(percorso, comment="#")
    for c in ("trigger_long", "trigger_short", "filtro", "esito", "m3_trigger_long", "m3_trigger_short",
              "m3_filtro", "m3_esito"):
        if c in tab.columns:
            tab[c] = tab[c].fillna("").astype(str)
    return tab


def mercato_nullo(symbol: str, timeframe: str = "M15", H: int = 25, giri: int = 500, strada: str = "A",
                  modo: str = "N1", cartella="dati", funding: bool = True, seme_iniziale: int = 0,
                  percorso: str | None = None, verbose: bool = True) -> pd.DataFrame:
    """
    I giri da 0 a giri-1 (seme = seme_iniziale + giro) sul symbol, scritti una
    riga per giro. Quelli gia' nel file non si rifanno: lanciare di nuovo con
    lo stesso comando riprende da dove si era fermato, e con `giri` piu' alto
    aggiunge i mancanti. Ritorna la tabella di tutti i giri del file.
    """
    import matplotlib
    matplotlib.use("Agg")
    from . import vetrina as v
    if strada not in STRADE:
        raise ValueError(f"strada {strada!r}: per ora solo {STRADE} (la strada B arriva con l'atlante, lavoro C).")
    if modo not in MODI:
        raise ValueError(f"modo {modo!r}: per ora solo {MODI} (N2 dopo, se servira': docs/63 §7.2).")
    with contextlib.redirect_stdout(io.StringIO()):
        s = v.prepara(symbol, H=H, cartella=cartella, timeframe=timeframe, funding=funding)
    reg.remove_entries(PREFISSO)
    nomi = v._trigger_candidati(1 if s.solo_long else None)
    testa = {"versione_catalogo": versione_catalogo(), "symbol": symbol, "timeframe": timeframe,
             "H": str(int(H)), "unita": s.unita, "funding": "si" if s.funding is not None else "no",
             "modo": modo, "strada": strada}
    percorso = percorso or file_nullo(symbol, timeframe, H, strada, cartella)
    os.makedirs(os.path.dirname(percorso) or ".", exist_ok=True)
    fatti = set()
    if os.path.exists(percorso):
        vecchia = leggi_intestazione(percorso)
        diverse = [k for k in CHIAVI_INTESTAZIONE if vecchia.get(k) != testa[k]]
        if diverse:
            raise ValueError(f"{percorso} e' di un altro mercato nullo ({', '.join(f'{k}: {vecchia.get(k)!r} contro {testa[k]!r}' for k in diverse)}). "
                             "Spostalo o rinominalo per ripartire da zero.")
        fatti = set(leggi_nullo(percorso)["giro"].astype(int))
    else:
        with open(percorso, "w", encoding="utf-8", newline="") as f:
            for k in CHIAVI_INTESTAZIONE:
                f.write(f"# {k}: {testa[k]}\n")
            f.write(f"# data: {pd.Timestamp.now():%Y-%m-%d %H:%M}\n")
            f.write("# nota: la soglia empirica e' un pavimento (docs/63 §10.1 punto 5) e solo informativa "
                    "(domanda 17); N1 = trigger casuali, piu' sparsi dei veri (meno grappoli)\n")
            f.write(",".join(COLONNE) + "\n")
    conteggi = conteggi_veri(s.df_is, nomi, s.fuso)
    da_fare = [g for g in range(int(giri)) if g not in fatti]
    if verbose:
        print(f"{symbol} {timeframe} H={H} · {testa['versione_catalogo']} · unita' {s.unita} · funding "
              f"{testa['funding']} · {len(nomi)} entry vere · {len(fatti)} giri gia' fatti, {len(da_fare)} da fare",
              flush=True)
    durate = []
    for n, g in enumerate(da_fare, 1):
        riga = giro_nullo(s, seme_iniziale + g, nomi, conteggi)
        riga["giro"] = g
        pd.DataFrame([riga]).reindex(columns=COLONNE).to_csv(percorso, mode="a", header=False, index=False)
        durate.append(riga["secondi"])
        if verbose:
            resto = (len(da_fare) - n) * float(np.mean(durate))
            print(f"  giro {g}: {riga['secondi']:.0f} s · t {riga.get('t', np.nan):+.2f} · esito "
                  f"{riga.get('esito', '')} · filtro {riga.get('filtro') or '—'} · mancano circa "
                  f"{resto / 3600:.1f} ore", flush=True)
    return leggi_nullo(percorso)


# ========================================================================
# Lettura
# ========================================================================

def soglia_empirica(tabella: pd.DataFrame, colonna: str = "t", quota: float = QUOTA) -> float:
    """
    Il t che la pipeline raggiunge o supera nel `quota` dei giri (5%): il piu'
    basso dei ceil(quota x giri) t piu' alti (su 500 giri, il 25° dall'alto).
    Un giro senza t (nessun trade) conta come «non arrivato». NaN senza giri.
    """
    x = pd.to_numeric(tabella[colonna], errors="coerce").to_numpy(dtype=float)
    if len(x) == 0:
        return np.nan
    x = np.sort(np.where(np.isfinite(x), x, -np.inf))
    k = max(len(x) - int(np.ceil(float(quota) * len(x))), 0)
    return float(x[k])


def riassunto(tabella: pd.DataFrame) -> pd.DataFrame:
    """La tabella del terminale (§7.6): la regola del §7.3 accanto al «migliore dei primi 3»."""
    from .giudizio import DA_VALUTARE
    n = len(tabella)

    def quota(cond) -> str:
        return f"{100.0 * float(np.mean(cond)):.1f}%" if n else "—"

    righe = [("Giri", str(n), str(n)),
             ("Esito della scheda «DA VALUTARE»", quota(tabella["esito"] == DA_VALUTARE),
              quota(tabella["m3_esito"] == DA_VALUTARE)),
             ("Un filtro regge le due prove", quota(tabella["filtro"].fillna("") != ""),
              quota(tabella["m3_filtro"].fillna("") != "")),
             ("t della scheda, mediana", f"{np.nanmedian(tabella['t']):+.2f}" if n else "—",
              f"{np.nanmedian(tabella['m3_t']):+.2f}" if n else "—"),
             (f"Soglia empirica: t superato nel {QUOTA:.0%} dei giri (pavimento)",
              f"{soglia_empirica(tabella, 't'):+.2f}", f"{soglia_empirica(tabella, 'm3_t'):+.2f}"),
             ("Rosa vuota, lato long / short", f"{quota(tabella['rosa_long'] == 0)} / {quota(tabella['rosa_short'] == 0)}",
              ""),
             ("Secondi per giro, media", f"{tabella['secondi'].mean():.0f}" if n else "—", "")]
    return pd.DataFrame(righe, columns=["", "Regola del §7.3", "Migliore dei primi 3"])


def frase_mercato_nullo(symbol: str, timeframe: str, H: int, t: float, cartella="dati", strada: str = "A") -> str:
    """
    La riga sotto la scheda (§7.6), solo informativa: quante volte, nel mercato
    nullo dello stesso symbol, timeframe e H, la pipeline e' arrivata a un t
    almeno cosi' alto. Se il file manca o il catalogo e' cambiato, lo dice.
    """
    p = file_nullo(symbol, timeframe, H, strada, cartella)
    if not os.path.exists(p):
        return (f"Mercato nullo non ancora calcolato per {symbol} {timeframe}, H = {int(H)}, strada {strada} "
                "(python mercato_nullo.py).")
    if leggi_intestazione(p).get("versione_catalogo") != versione_catalogo():
        return "Mercato nullo calcolato con un altro catalogo di condizioni: va rifatto (python mercato_nullo.py)."
    tab = leggi_nullo(p)
    if not len(tab) or not np.isfinite(t):
        return "Mercato nullo: nessun confronto possibile (nessun giro o nessun t)."
    x = pd.to_numeric(tab["t"], errors="coerce").to_numpy(dtype=float)
    quota = float(np.mean(np.where(np.isfinite(x), x, -np.inf) >= t))
    t_testo = f"{t:+.2f}".replace(".", ",")
    return (f"Nel mercato nullo di questo symbol ({len(tab)} giri, strada {strada}), la pipeline arriva a un t "
            f"almeno così alto ({t_testo}) nel {quota:.0%} dei giri. È un pavimento dell'autoinganno ed è solo "
            "informativo: non cambia nessun cancello.")
