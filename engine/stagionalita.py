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
# Il profilo orario
# ========================================================================

def profilo_orario(df_is: pd.DataFrame, H: int, pip: float, fuso: str = FUSO_PREDEFINITO,
                   q: float | None = None, quarantena=True) -> pd.DataFrame:
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
    """
    from .rosa import Q_ROSA, benjamini_hochberg
    q = Q_ROSA if q is None else float(q)
    H = int(H)
    if H < 1:
        raise ValueError("H deve essere almeno 1 barra.")
    if pip is None or not float(pip) > 0:
        raise ValueError("pip obbligatorio: il pip fisso del symbol (engine/simboli.py).")
    fwd = rendimenti_avanti(df_is, H, pip)
    usa = np.isfinite(fwd) & maschera_segnali_puliti(df_is, quarantena)
    fwd0 = np.where(usa, fwd, 0.0)
    codici, larghezza = fasce_orarie(df_is.index, fuso)
    _, _, sfasamento = griglia_oraria(df_is.index, fuso)
    nf = n_fasce(larghezza)
    n = len(df_is)
    prima = np.arange(n) < n // 2
    globale = float(fwd[usa].mean())
    glob_meta = (float(fwd[usa & prima].mean()), float(fwd[usa & ~prima].mean()))

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
        righe.append({"fascia": etichetta_fascia((f + 1) % nf, larghezza, sfasamento), "barre": int(pos.size),
                      "media_pips": float(x.mean()), "scarto_pips": scarto,
                      "incertezza": se, "t": t,
                      "p": 2.0 * (1.0 - _NORMALE.cdf(abs(t))) if np.isfinite(t) else np.nan,
                      "due_meta": dm})
    tab = pd.DataFrame(righe)
    if len(tab):
        tab["bh"] = benjamini_hochberg(tab["p"].to_numpy(), q)
        tab = (tab[["fascia", "barre", "media_pips", "scarto_pips", "incertezza", "t", "p",
                    "bh", "due_meta"]].sort_values("fascia").reset_index(drop=True))
    tab.attrs.update(fuso=fuso, larghezza_min=larghezza, H=H, k=len(tab), q=q,
                     media_pips=globale)
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
    alta = profilo.loc[profilo["scarto_pips"].idxmax()]
    bassa = profilo.loc[profilo["scarto_pips"].idxmin()]
    righe = [
        f"Se apri un LONG alle {alta['fascia']} (ora di {luogo}) e lo tieni {H} barre, in media guadagni "
        f"{alta['scarto_pips']:+.1f} {pip_nome} rispetto a un'ora qualsiasi"
        + (" — supera il controllo dei colpi di fortuna." if alta["bh"] else " — ma può essere solo caso."),
        f"Se apri un LONG alle {bassa['fascia']} il risultato è {bassa['scarto_pips']:+.1f} {pip_nome} rispetto a "
        f"un'ora qualsiasi: per uno SHORT aperto a quell'ora vale al contrario"
        + (" — supera il controllo dei colpi di fortuna." if bassa["bh"] else " — ma può essere solo caso."),
    ]
    n_oltre = int(profilo["bh"].sum())
    righe.append(f"Fasce che superano il controllo dei colpi di fortuna: {n_oltre} su {len(profilo)}."
                 + (" Fasce vicine raccontano lo stesso fatto: contale come un'idea sola." if n_oltre > 1 else ""))
    return righe
