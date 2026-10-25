"""
Il profilo orario e la baseline oraria (18/10/2026, decisioni di Mattia del
18/10/2026).

A COSA SERVE
------------
Il mercato non si muove allo stesso modo a tutte le ore. Misurato
sull'in-sample M15, H = 25: su EURUSD il rendimento medio a 25 barre va da
-1,8 a +2,9 pips a seconda della fascia oraria, quasi 3 volte quanto
spiegherebbe il caso; su XAUUSD da -2,5 a +11,3 pips. Sono le stesse
grandezze dei vantaggi che la rosa riesce a vedere: un trigger che scatta
quasi sempre alla stessa ora puo' sembrare un edge solo per l'ora in cui
scatta, o nasconderne uno.

Due cose:

    profilo_orario(df_is, H, pip, fuso)
        per ogni fascia oraria il rendimento medio a H barre, lo scarto dalla
        media di tutte le barre, la sua incertezza e il controllo della quota
        di falsi positivi sulle fasce. Si guarda; non sceglie niente.

    la BASELINE ORARIA (usata da engine/rosa.py e dall'event study)
        il riferimento di mercato di un trigger diventa la media della SUA
        fascia oraria, non piu' la media di tutte le barre.

LE FASCE
--------
Una fascia e' larga quanto una barra (M5: 288 fasce al giorno, M15: 96,
H1: 24, H4: 6), sull'ora LOCALE della piazza di riferimento: le fasce
restano agganciate all'ora locale anche ai cambi di ora legale. Il fuso e'
fissato a priori per symbol (FUSO_PIAZZA): New York per forex, oro,
cripto e indici americani (per il forex e' l'ora del giorno FX, che cambia
alle 17:00 di New York), Francoforte per DE40. Il giorno della settimana
non entra (decisione di Mattia del 18/10/2026): celle troppo piccole.

Il profilo propone, non sceglie: una finestra scelta guardando il profilo
conta come tante prove quante sono le fasce. Una finestra presa da un paper
(es. il fixing delle 16:00 di Londra) conta come una prova sola.

Si passa SOLO l'in-sample: e' una misura, come la media di tutte le barre
che sostituisce, non un segnale.

Modulo ADDITIVO: non modifica nessun file esistente dell'engine.
"""
from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd

from .quarantena import passo_barre
from .quarantena_trade import maschera_segnali_puliti

FUSO_PREDEFINITO = "America/New_York"
# fissato a priori per symbol: la piazza di riferimento (le borse locali)
FUSO_PIAZZA = {"DE40": "Europe/Berlin"}

_NORMALE = NormalDist()


def fuso_profilo(symbol: str) -> str:
    """
    Il fuso della piazza di riferimento del symbol (New York se non elencato).
    19/10/2026: UTC per i symbol da exchange crypto (engine/simboli.py,
    SIMBOLI_EXCHANGE): la giornata degli exchange e dei paper crypto.
    """
    from .simboli import da_exchange
    if da_exchange(symbol):
        return "UTC"
    return FUSO_PIAZZA.get(str(symbol).upper(), FUSO_PREDEFINITO)


# ========================================================================
# Le fasce
# ========================================================================

def griglia_oraria(index, fuso: str = FUSO_PREDEFINITO) -> tuple[np.ndarray, int, int]:
    """
    I minuti dalla mezzanotte locale dell'inizio di ogni barra, la larghezza
    della barra in minuti (dedotta dall'indice; un giorno al massimo) e lo
    sfasamento della griglia delle candele: il resto piu' frequente di
    minuti / larghezza (19/10/2026). Su M5-H1 e' 0; sulle H4 del broker, che
    partono dalle 17:00 di New York, e' 60 (candele alle 17, 21, 1, 5, 9, 13).

    Serve un indice con fuso (UTC vero: engine.quarantena.verifica_indice_utc).
    """
    idx = pd.DatetimeIndex(index)
    if idx.tz is None:
        raise ValueError("L'indice non ha fuso orario. Serve un indice UTC: "
                         "chiama prima engine.quarantena.verifica_indice_utc().")
    larghezza = int(passo_barre(idx) / pd.Timedelta(minutes=1))
    larghezza = min(max(larghezza, 1), 1440)
    loc = idx.tz_convert(fuso)
    minuti = np.asarray(loc.hour * 60 + loc.minute, dtype=np.int64)
    resti = np.bincount(minuti % larghezza, minlength=larghezza)
    return minuti, larghezza, int(np.argmax(resti))


def n_fasce(larghezza: int) -> int:
    return max(1, -(-1440 // int(larghezza)))


def fasce_orarie(index, fuso: str = FUSO_PREDEFINITO) -> tuple[np.ndarray, int]:
    """
    Il codice della fascia oraria di ogni barra e la larghezza della fascia
    in minuti. Codice = (minuti dalla mezzanotte locale - sfasamento della
    griglia) // larghezza, da 0 a n_fasce - 1: una fascia per candela del
    giorno, agganciata alla griglia vera delle candele (griglia_oraria).
    """
    minuti, larghezza, scarto = griglia_oraria(index, fuso)
    return ((minuti - scarto) % 1440) // larghezza, larghezza


def etichetta_fascia(codice: int, larghezza: int, scarto: int = 0) -> str:
    """L'ora d'inizio della candela della fascia `codice`, «HH:MM»."""
    m = (int(codice) * int(larghezza) + int(scarto)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def codice_orario(orario: str, index, fuso: str = FUSO_PREDEFINITO) -> tuple[int, int]:
    """
    Il codice della fascia la cui candela comincia all'ora locale `orario`
    («HH:MM») e il numero di fasce del giorno. Si ferma con errore se, su
    questo timeframe, `orario` non e' l'inizio di una candela.
    """
    try:
        ore, minuti = str(orario).strip().split(":")
        m = int(ore) * 60 + int(minuti)
        if not (0 <= int(ore) < 24 and 0 <= int(minuti) < 60):
            raise ValueError
    except ValueError:
        raise ValueError(f"Orario '{orario}' non valido: scrivilo come HH:MM, es. 12:30.") from None
    _, larghezza, scarto = griglia_oraria(index, fuso)
    if (m - scarto) % larghezza:
        esempi = ", ".join(etichetta_fascia(c, larghezza, scarto) for c in range(min(n_fasce(larghezza), 8)))
        raise ValueError(f"Su candele da {larghezza} minuti l'orario {orario} non e' l'inizio di una "
                         f"candela (ora di {fuso}). Orari possibili: {esempi}...")
    return ((m - scarto) % 1440) // larghezza, n_fasce(larghezza)


def segnale_prima_di(df: pd.DataFrame, orario: str, fuso: str = FUSO_PREDEFINITO) -> pd.Series:
    """
    Vera sulla candela che precede quella delle `orario` (ora locale di
    `fuso`): il motore apre o chiude all'Open della candela successiva al
    segnale, quindi il trade si apre (o si chiude) alle `orario` esatte.

    Senza lookahead: usa solo l'ora d'inizio della candela del segnale (la
    candela che verra' dopo e' quella successiva sulla griglia). Una volta al
    giorno al massimo.
    """
    codici, larghezza = fasce_orarie(df.index, fuso)
    bersaglio, n = codice_orario(orario, df.index, fuso)
    return pd.Series((codici + 1) % n == bersaglio, index=df.index)


def rendimenti_avanti(df: pd.DataFrame, H: int, pip: float) -> np.ndarray:
    """
    Il rendimento long a H barre di ogni barra, in pips, con la convenzione
    dell'event study: segnale sulla barra i, ingresso a Open[i+1], misura a
    Close[i+H]. NaN dove non misurabile.
    """
    n = len(df)
    close = df["Close"].to_numpy(dtype=float)
    open_ = df["Open"].to_numpy(dtype=float)
    ingresso = np.full(n, np.nan)
    ingresso[: n - 1] = open_[1:]
    fwd = np.full(n, np.nan)
    if n > H:
        fwd[: n - H] = (close[H:] - ingresso[: n - H]) / float(pip)
    fwd[~(np.isfinite(ingresso) & (ingresso > 0))] = np.nan
    return fwd


UNITA = ("pips", "bp", "atr")       # 20/10/2026, docs/63 §4


def in_unita(valori_pips: np.ndarray, unita: str, pip: float, prezzo=None, atr=None) -> np.ndarray:
    """
    Da pips all'unita' scelta, barra per barra (20/10/2026, docs/63 §4):
      pips  invariati;
      bp    pips x pip / prezzo x 10.000 (prezzo = quello d'ingresso);
      atr   pips x pip / atr (l'ATR giornaliero noto al segnale).
    NaN dove prezzo o ATR mancano o non sono positivi.
    """
    v = np.asarray(valori_pips, dtype=float)
    if unita == "pips":
        return v
    if unita == "bp":
        p = np.asarray(prezzo, dtype=float)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(p > 0, v * float(pip) * 10_000.0 / p, np.nan)
    if unita == "atr":
        a = np.asarray(atr, dtype=float)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(a > 0, v * float(pip) / a, np.nan)
    raise ValueError(f"unita' {unita!r} sconosciuta: usa una di {UNITA}")


def rendimenti_avanti_unita(df: pd.DataFrame, H: int, unita: str = "bp", pip: float = None,
                            atr=None) -> np.ndarray:
    """
    Come rendimenti_avanti (segnale i, ingresso Open[i+1], misura Close[i+H]),
    nell'unita' scelta: "pips", "bp" (sul prezzo d'ingresso) o "atr" (sull'ATR
    alla barra del segnale; `atr` = indicatori.atr_giornaliero_chiuso, una
    serie allineata a df). NaN dove non misurabile.
    """
    if pip is None or not float(pip) > 0:
        raise ValueError("pip obbligatorio: il pip fisso del symbol (engine/simboli.py).")
    fwd = rendimenti_avanti(df, H, pip)
    ingresso = np.full(len(df), np.nan)
    ingresso[:-1] = df["Open"].to_numpy(dtype=float)[1:]
    if unita == "atr":
        if atr is None:
            raise ValueError("unita' 'atr': serve la serie dell'ATR (indicatori.atr_giornaliero_chiuso).")
        atr = pd.Series(atr).reindex(df.index).to_numpy(dtype=float) if isinstance(atr, pd.Series) \
            else np.asarray(atr, dtype=float)
    return in_unita(fwd, unita, pip, prezzo=ingresso, atr=atr)


def media_per_fascia(valori: np.ndarray, codici: np.ndarray, usa: np.ndarray) -> np.ndarray:
    """
    Per ogni barra, la media di `valori` sulle barre `usa` della sua stessa
    fascia. NaN dove la fascia non ha barre utili.
    """
    v = np.where(usa, valori, 0.0)
    n_cod = int(codici.max()) + 1 if codici.size else 0
    somma = np.bincount(codici, weights=v, minlength=n_cod)
    conta = np.bincount(codici, weights=usa.astype(float), minlength=n_cod)
    with np.errstate(invalid="ignore", divide="ignore"):
        media = np.where(conta > 0, somma / conta, np.nan)
    return media[codici]


def errore_standard_pesato(u: np.ndarray, H: int) -> float:
    """
    Errore standard di una somma pesata di rendimenti a H barre su TUTTE le
    barre, sum_j c_j r_j, con u_j = c_j * r_j (r = scarti dal modello). Due
    barre a d < H barre di distanza condividono H - d candele su H: stessa
    covarianza di engine/event_study._errore_standard_sovrapposti, qui con un
    peso per barra (serve quando il riferimento e' la media della fascia,
    stimata anch'essa sui dati).
    """
    u = np.nan_to_num(np.asarray(u, dtype=float))
    tot = float((u ** 2).sum())
    for d in range(1, min(int(H), u.size)):
        tot += 2.0 * (1.0 - d / H) * float((u[d:] * u[:-d]).sum())
    return float(np.sqrt(max(tot, 0.0)))


def scarto_orario(fwd: np.ndarray, codici: np.ndarray, usa: np.ndarray,
                  pos: np.ndarray, direzione: int, H: int) -> tuple[float, float]:
    """
    Lo scarto medio dei trigger in `pos` dalla media della loro fascia
    oraria, nel verso `direzione`, e la sua incertezza. L'incertezza include
    il rumore della media di fascia (stimata sulle barre `usa`, trigger
    compresi) e le sovrapposizioni fra barre vicine.
    """
    b = media_per_fascia(fwd, codici, usa)
    x = direzione * (fwd[pos] - b[pos])
    scarto = float(np.mean(x))
    n_t = pos.size
    # pesi: +1/n_t sui trigger, -(trigger della fascia)/(n_t * barre della fascia) su ogni barra
    n_cod = int(codici.max()) + 1
    trig_f = np.bincount(codici[pos], minlength=n_cod).astype(float)
    barre_f = np.bincount(codici, weights=usa.astype(float), minlength=n_cod)
    with np.errstate(invalid="ignore", divide="ignore"):
        quota = np.where(barre_f > 0, trig_f / barre_f, 0.0)
    c = np.where(usa, -quota[codici] / n_t, 0.0)
    c[pos] += 1.0 / n_t
    r = np.where(usa, fwd - b, 0.0)
    r[pos] -= direzione * scarto       # il modello: fascia + vantaggio del trigger
    return scarto, errore_standard_pesato(c * r, H)


def deriva_per_barra_oraria(df: pd.DataFrame, pip: float,
                            fuso: str = FUSO_PREDEFINITO) -> np.ndarray:
    """
    Per ogni barra j, la variazione media Open[j+1] - Open[j] (in pips, verso
    long) delle barre della sua stessa fascia oraria. Somma su [EntryBar,
    ExitBar) = la deriva tipica delle ore in cui un trade e' rimasto aperto.
    """
    open_ = df["Open"].to_numpy(dtype=float)
    diff = np.full(len(open_), np.nan)
    diff[:-1] = np.diff(open_) / float(pip)
    codici, _ = fasce_orarie(df.index, fuso)
    usa = np.isfinite(diff)
    return np.nan_to_num(media_per_fascia(np.nan_to_num(diff), codici, usa))


# ========================================================================
# La curva dello scarto, barra per barra (25/10/2026, docs/68 §2.1)
# ========================================================================

def curva_scarto_orario(df_is: pd.DataFrame, nomi, H: int, pip: float,
                        fuso: str = FUSO_PREDEFINITO, unita: str = "pips",
                        quarantena=True, qualunque_ora=(), atr=None) -> pd.DataFrame:
    """
    Per ogni trigger, lo scarto medio dal mercato della stessa ora a ogni
    barra k = 1..H: la misura della rosa (engine/rosa.py, baseline oraria)
    distesa su tutte le barre invece che solo a H. Stessa convenzione:
    segnale sulla barra i, ingresso a Open[i+1], misura a Close[i+k], nel
    verso del trade (sopra lo zero = il trigger fa meglio del mercato a
    quell'ora). Gli eventi sono gli stessi a ogni barra: quelli che la rosa
    misura a H, quindi a k = H la curva coincide con `scarto_<unita>` di
    `rosa_entry`.

    nomi           entry del registro (o un dict nome -> maschera booleana, per i test)
    unita          "pips", "bp" o "atr" (come rosa_entry; atr = la serie dell'ATR)
    qualunque_ora  nomi da confrontare con il mercato a qualunque ora invece
                   che della stessa ora: i trigger a orario (ORA_…), che per
                   costruzione coincidono con il mercato della loro fascia
                   (lo stesso confronto della rosa con baseline="globale")

    Ritorna una tabella: indice barre 1..H, una colonna per trigger misurato.
    In .attrs: eventi (per trigger), unita, H, qualunque_ora. I trigger
    senza eventi non hanno colonna. Modulo additivo: nessuna funzione
    esistente cambia.
    """
    from . import registry as _reg
    H = int(H)
    if H < 1:
        raise ValueError("H deve essere almeno 1 barra.")
    if pip is None or not float(pip) > 0:
        raise ValueError("pip obbligatorio: il pip fisso del symbol (engine/simboli.py).")
    if unita not in UNITA:
        raise ValueError(f"unita' {unita!r} sconosciuta: usa una di {UNITA}")
    pip = float(pip)
    n = len(df_is)
    close = df_is["Close"].to_numpy(dtype=float)
    open_ = df_is["Open"].to_numpy(dtype=float)
    ingresso = np.full(n, np.nan)
    ingresso[: n - 1] = open_[1:]
    ok_ing = np.isfinite(ingresso) & (ingresso > 0)
    atr_v = None
    if unita == "atr":
        if atr is None:
            from .indicatori import atr_giornaliero_chiuso
            atr = atr_giornaliero_chiuso(df_is)
        atr_v = pd.Series(atr).reindex(df_is.index).to_numpy(dtype=float)
    pulito = maschera_segnali_puliti(df_is, quarantena)
    codici = fasce_orarie(df_is.index, fuso)[0]

    def avanti(k):
        """Rendimento long a k barre nell'unita' (NaN dove non misurabile) e barre utili."""
        f = np.full(n, np.nan)
        if n > k:
            f[: n - k] = (close[k:] - ingresso[: n - k]) / pip
        f = in_unita(f, unita, pip, prezzo=ingresso, atr=atr_v)
        return f, np.isfinite(f) & ok_ing

    # gli eventi: quelli che la rosa misura a H (rendimento a H misurabile, quarantena)
    f_H, valido_H = avanti(H)
    if isinstance(nomi, dict):
        maschere = {k: (np.asarray(v, dtype=bool), 1) for k, v in nomi.items()}
    else:
        maschere = {k: (_reg.get_entry(k)(df_is).fillna(False).to_numpy(dtype=bool),
                        int(_reg.get_entry_direction(k))) for k in nomi}
    orari = set(qualunque_ora or ())
    eventi, pos_d = {}, {}
    for nome, (m, d) in maschere.items():
        pos = np.flatnonzero(m & valido_H & pulito)
        if pos.size:
            pos_d[nome] = (pos, d)
            eventi[nome] = int(pos.size)

    curva = pd.DataFrame(index=pd.RangeIndex(1, H + 1, name="barre_dal_trigger"), dtype=float)
    valori = {nome: np.full(H, np.nan) for nome in pos_d}
    for k in range(1, H + 1):
        f, valido = (f_H, valido_H) if k == H else avanti(k)
        usa = valido & pulito
        b = media_per_fascia(np.nan_to_num(f), codici, usa)
        mercato = float(np.nanmean(f)) if np.isfinite(f).any() else np.nan
        for nome, (pos, d) in pos_d.items():
            if nome in orari:
                valori[nome][k - 1] = float(np.mean(d * f[pos])) - d * mercato
            else:
                valori[nome][k - 1] = float(np.mean(d * (f[pos] - b[pos])))
    for nome in pos_d:
        curva[nome] = valori[nome]
    curva.attrs.update(eventi=eventi, unita=unita, H=H, qualunque_ora=sorted(orari & set(pos_d)))
    return curva


def picco_curva(curva: pd.Series, H: int | None = None) -> dict:
    """
    Il picco di una curva dello scarto (curva_scarto_orario), SOLO DA LEGGERE
    (25/10/2026, docs/68 §5.1, decisione di Mattia): le uscite consigliate
    usano H, non questa barra. Ritorna barra, valore, in_coda (picco
    nell'ultimo quarto di H, la regola di picco_in_coda dell'event study),
    presto (picco nel primo quarto) e la nota da mostrare accanto.
    """
    c = pd.Series(curva, dtype=float).dropna()
    H = int(H if H is not None else (c.index.max() if len(c) else 0))
    if c.empty or H < 1:
        return dict(barra=None, valore=np.nan, in_coda=False, presto=False,
                    nota="Curva non misurabile.")
    barra = int(c.idxmax())
    valore = float(c.loc[barra])
    in_coda = barra >= int(np.ceil(H * 0.75))
    presto = (not in_coda) and barra <= max(1, H // 4)
    if valore <= 0:
        nota = "La curva non va mai sopra lo zero: il trigger non fa meglio del mercato a nessuna barra."
    elif in_coda:
        nota = "Il movimento continua fino all'orizzonte che hai dichiarato."
    elif presto:
        nota = ("Il movimento finisce presto: dopo il picco il trade resta aperto fino a H barre, esposto al "
                "rumore del prezzo e, sui perpetual, al funding, che cresce con la durata.")
    else:
        nota = ""
    return dict(barra=barra, valore=valore, in_coda=bool(in_coda), presto=bool(presto), nota=nota)


# ========================================================================
# Il profilo orario
# ========================================================================

def profilo_orario(df_is: pd.DataFrame, H: int, pip: float, fuso: str = FUSO_PREDEFINITO,
                   q: float | None = None, quarantena=True, unita: str = "pips") -> pd.DataFrame:
    """
    Il profilo orario sull'in-sample: una riga per fascia (larga una barra,
    ora locale di `fuso`).

        fascia        l'ora in cui SI APRE il trade, ora locale «HH:MM» (19/10/2026,
                      regola di Mattia: il segnale e' sulla candela prima, il
                      trade parte all'Open di questa candela; stessa regola di
                      ORA_LONG_@HH:MM e delle uscite orarie)
        barre         barre misurate in quella fascia
        media_pips    rendimento long medio a H barre aprendo il trade a quell'ora
        scarto_pips   media_pips meno la media di tutte le barre
        incertezza    quanto balla lo scarto per il caso (barre vicine comprese)
        t, p          t dello scarto e p a DUE code (una fascia negativa e'
                      un'informazione quanto una positiva)
        bh            passa il controllo della quota di falsi positivi a q (sulle fasce)
        due_meta      scarto con lo stesso segno su entrambe le meta' dell'in-sample

    In .attrs: fuso, larghezza_min, H, k (fasce), q, media_pips (di tutte le barre).

    unita (23/10/2026): l'unita' che DECIDE, "pips" (come sempre) o "bp"
    (symbol da exchange: pips x pip / prezzo d'ingresso x 10.000). In bp
    media_bp, scarto_bp, incertezza, t, p, bh e due_meta sono in bp, e
    media_pips / scarto_pips restano accanto, da leggere. In .attrs anche
    unita (e media_bp).
    """
    from .rosa import Q_ROSA, benjamini_hochberg
    q = Q_ROSA if q is None else float(q)
    H = int(H)
    if H < 1:
        raise ValueError("H deve essere almeno 1 barra.")
    if pip is None or not float(pip) > 0:
        raise ValueError("pip obbligatorio: il pip fisso del symbol (engine/simboli.py).")
    if unita not in ("pips", "bp"):
        raise ValueError(f"unita' del profilo {unita!r}: usa 'pips' o 'bp'.")
    fwd = rendimenti_avanti(df_is, H, pip)
    fwd_pips = fwd
    if unita == "bp":
        fwd = rendimenti_avanti_unita(df_is, H, "bp", pip)    # decide il bp; i pips restano accanto
    usa = np.isfinite(fwd) & maschera_segnali_puliti(df_is, quarantena)
    fwd0 = np.where(usa, fwd, 0.0)
    codici, larghezza = fasce_orarie(df_is.index, fuso)
    _, _, sfasamento = griglia_oraria(df_is.index, fuso)
    nf = n_fasce(larghezza)
    n = len(df_is)
    prima = np.arange(n) < n // 2
    globale = float(fwd[usa].mean())
    glob_meta = (float(fwd[usa & prima].mean()), float(fwd[usa & ~prima].mean()))
    globale_pips = float(fwd_pips[usa].mean())

    righe = []
    for f in np.unique(codici[usa]):
        dentro = usa & (codici == f)
        pos = np.flatnonzero(dentro)
        if pos.size < 2:
            continue
        x = fwd[pos]
        scarto = float(x.mean()) - globale
        # incertezza: pesi +1/n_f nella fascia, -1/N su tutte le barre
        c = np.where(usa, -1.0 / usa.sum(), 0.0)
        c[pos] += 1.0 / pos.size
        r = np.where(usa, fwd0 - globale, 0.0)
        r[pos] -= scarto
        se = errore_standard_pesato(c * r, H)
        t = scarto / se if se > 0 else np.nan
        a, b = pos[prima[pos]], pos[~prima[pos]]
        dm = bool(a.size and b.size
                  and np.sign(fwd[a].mean() - glob_meta[0]) == np.sign(scarto)
                  and np.sign(fwd[b].mean() - glob_meta[1]) == np.sign(scarto))
        riga = {"fascia": etichetta_fascia((f + 1) % nf, larghezza, sfasamento), "barre": int(pos.size),
                f"media_{unita}": float(x.mean()), f"scarto_{unita}": scarto,
                "incertezza": se, "t": t,
                "p": 2.0 * (1.0 - _NORMALE.cdf(abs(t))) if np.isfinite(t) else np.nan,
                "due_meta": dm}
        if unita != "pips":
            riga["media_pips"] = float(fwd_pips[pos].mean())
            riga["scarto_pips"] = float(fwd_pips[pos].mean()) - globale_pips
        righe.append(riga)
    tab = pd.DataFrame(righe)
    colonne = ["fascia", "barre", f"media_{unita}", f"scarto_{unita}", "incertezza", "t", "p", "bh", "due_meta"]
    if unita != "pips":
        colonne += ["media_pips", "scarto_pips"]
    if len(tab):
        tab["bh"] = benjamini_hochberg(tab["p"].to_numpy(), q)
        tab = tab[colonne].sort_values("fascia").reset_index(drop=True)
    if unita == "pips":
        tab.attrs.update(fuso=fuso, larghezza_min=larghezza, H=H, k=len(tab), q=q,
                         media_pips=globale)
    else:
        tab.attrs.update(fuso=fuso, larghezza_min=larghezza, H=H, k=len(tab), q=q,
                         media_pips=globale_pips, media_bp=globale, unita=unita)
    return tab


def descrivi_profilo(profilo: pd.DataFrame, pip_nome: str = "pips") -> list[str]:
    """
    Il profilo in parole, per chi lo vede la prima volta (19/10/2026): la
    fascia migliore e la peggiore per un long, con il loro numero vero, e
    quante fasce superano il controllo dei colpi di fortuna.
    """
    if profilo is None or len(profilo) == 0:
        return ["Nessuna fascia misurabile."]
    H = profilo.attrs.get("H")
    luogo = str(profilo.attrs.get("fuso", "")).split("/")[-1].replace("_", " ")
    u = profilo.attrs.get("unita", "pips")              # 23/10/2026: l'unita' che decide
    if u != "pips":
        pip_nome = u
    colonna = f"scarto_{u}"
    alta = profilo.loc[profilo[colonna].idxmax()]
    bassa = profilo.loc[profilo[colonna].idxmin()]
    righe = [
        f"Se apri un LONG alle {alta['fascia']} (ora di {luogo}) e lo tieni {H} barre, in media guadagni "
        f"{alta[colonna]:+.1f} {pip_nome} rispetto a un'ora qualsiasi"
        + (" — supera il controllo dei colpi di fortuna." if alta["bh"] else " — ma può essere solo caso."),
        f"Se apri un LONG alle {bassa['fascia']} il risultato è {bassa[colonna]:+.1f} {pip_nome} rispetto a "
        f"un'ora qualsiasi: per uno SHORT aperto a quell'ora vale al contrario"
        + (" — supera il controllo dei colpi di fortuna." if bassa["bh"] else " — ma può essere solo caso."),
    ]
    n_oltre = int(profilo["bh"].sum())
    righe.append(f"Fasce che superano il controllo dei colpi di fortuna: {n_oltre} su {len(profilo)}."
                 + (" Fasce vicine raccontano lo stesso fatto: contale come un'idea sola." if n_oltre > 1 else ""))
    return righe
