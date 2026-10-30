"""
Le schermate del notebook della mappa delle anomalie (28/10/2026, docs/73 §B.1,
decisione D4: un file a parte per non appesantire vetrina.py).

Mappa_Anomalie_Crypto.ipynb non ha codice nelle celle, come il Lab: chiama
queste funzioni.

    apri_mappa             1 · il dataset nello studio, SENZA orizzonte H
    elenco_schede          2 · le schede approvate e il loro stato
    mappa_di_una_scheda    3 · misura una scheda, la mostra, la scrive nello studio
    tutte_le_schede        4 · le schede non ancora misurate su questo dataset
    dalla_fascia_al_trigger 5 · la bozza in testo del trigger (nessun codice)
    riepilogo_mappa        6 · le schede misurate e la soglia cumulata del dataset

Dal 30/10/2026 il notebook e' semplice e chiama solo tre funzioni (in fondo al
file; le sei qui sopra restano com'erano):

    il_dataset             1 · il dataset, in tre righe
    misura_mappa           2 · ogni scheda: semaforo, numeri, grafico; «Cosa ti porti a casa»
    dettagli_mappa         Dettagli · tutto quello che le schermate 1-6 mostravano

LO STUDIO (docs/73 §B.4)
------------------------
La mappa entra nello studio con studio.entra (confine e impronta, come il Lab)
e ricostruisce il registro del dataset dai giornali, ma non chiama prepara:
non scrive nessuna voce «orizzonte», cosi' non tocca gli H provati del Lab.
Non apre lo studio e non ricalcola il confine: quelli si fanno dal Lab.
Il conto di ogni scheda va nel giornale come voce «prova» con dove = "mappa"
(mappa.registra), l'esito nel file della mappa, che la 2b del Lab legge.

Una scheda con le fasce degeneri (mappa.controlla_fasce) o doppione di
un'altra (`doppione_di` della scheda; dal 28/10/2026 nessuna scheda la usa: la
regola M04/M05 e' caduta con M04 riscritta) non si misura e non scrive niente.

I risultati collaudano il tool: non sono verdetti sul mercato.

Modulo ADDITIVO: usa i pezzi comuni di vetrina.py senza cambiarli.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from . import mappa as mp
from . import studio as _st
from . import vetrina as _v
from .ipotesi import QUINTILI, SCHEDE
from .simboli import da_exchange


class SessioneMappa:
    """Quello che le schermate del notebook della mappa si passano (come la Sessione del Lab)."""

    def __init__(self):
        self.symbol = self.timeframe = self.cartella = self.macchina = None
        self.dati = self.ingresso = self.df_is = self.df = None
        self.storia = self.prove = None
        self.costi = self.pip = self.funding = None
        self.btc = {}                 # symbol di BTC -> in-sample (M06)
        self.fs = None                # come la Sessione del Lab: nessuna ricerca dei filtri
        self.tabelle = {}
        self.misure = {}              # id della scheda -> la tabella delle fasce misurata qui

    def _serve(self, attributo: str, schermata: str):
        if getattr(self, attributo) is None:
            raise RuntimeError(f"Manca un passaggio: esegui prima la schermata «{schermata}».")


def _ricostruisci(m: SessioneMappa) -> None:
    """Il registro del dataset dai giornali dello studio (senza H: nessuna voce scritta)."""
    i = m.ingresso
    m.storia, _ = _st.ricostruisci(m.cartella, i.dataset, i.studio)
    m.prove = m.storia.prove


def _avviso_oos(m: SessioneMappa) -> None:
    """Il riquadro arancione di docs/68 §9: l'out-of-sample del dataset e' gia' stato guardato."""
    if m.storia is not None and m.storia.oos_visto:
        n = len(m.storia.diario)
        _v._avviso(f"Hai già guardato l'out-of-sample di questo dataset ({n} {'volta' if n == 1 else 'volte'}). "
                   "Una scheda scritta dopo averlo guardato non è più una prova pulita: la misura si fa lo stesso, "
                   "e il giornale lo segna.")


def _schede_qui(symbol: str) -> list[str]:
    return [sid for sid, sch in SCHEDE.items() if mp.adatta(sch, symbol) is None]


# ========================================================================
# 1 · Il dataset
# ========================================================================

def apri_mappa(symbol: str, timeframe: str = "M15", cartella="dati", aggiorna: bool = False,
               macchina: str | None = None) -> SessioneMappa:
    """
    Schermata 1 della mappa: il dataset entra nello studio (stesso confine e
    stessa impronta del Lab, con apri_dati e dividi_dati), il registro si
    ricostruisce dai giornali. NON scrive nessun H. Si ferma se lo studio non e'
    ancora aperto (lo apre la schermata 1 del Lab) o se il symbol non e' da exchange.
    """
    if not da_exchange(symbol):
        raise ValueError(f"{symbol}: la mappa delle anomalie lavora solo sui symbol da exchange (crypto).")
    if _st.leggi_confine(cartella) is None:
        raise RuntimeError("Lo studio non è ancora aperto: aprilo con la schermata 1 del Lab "
                           "(meglio su BINANCE_PERP_BTCUSDT M15). La mappa usa il suo confine e non lo apre.")
    m = SessioneMappa()
    m.symbol, m.timeframe, m.cartella = symbol, timeframe, cartella
    d = _v.apri_dati(symbol, timeframe, cartella, confine="studio", aggiorna=aggiorna, macchina=macchina)
    m.dati, m.macchina, m.df = d, d.macchina, d.df
    m.df_is, _ = _v.dividi_dati(d, d.df)
    m.ingresso = d.ingresso
    m.funding = d.funding
    m.costi, sp = _v.costi_storico(symbol, d.df, funding=d.funding, df_prezzo=m.df_is)
    m.pip = m.costi["pip_size"]
    _ricostruisci(m)

    i = m.ingresso
    qui = _schede_qui(symbol)
    voci = ["Strumento", f"Barre {timeframe}", "In-sample (si misura qui)", "Out-of-sample (mai visto)",
            "Funding (perpetual)", "Studio", "Schede che si misurano qui"]
    valori = [symbol, _v._fmt(len(d.df)),
              f"{_v._fmt(len(m.df_is))} barre, fino al {_v._giorno_ora(i.confine)} · confine dello studio",
              f"{_v._fmt(len(i.df_oos))} barre, dal {_v._giorno_ora(i.confine)}",
              "sì, contato come costo nel netto" if m.funding is not None else "no (spot: niente funding)",
              f"aperto il {pd.Timestamp(i.studio['aperto_il']):%d/%m/%Y} su {i.studio['aperto_su']} · vale per "
              "tutti i dataset",
              ", ".join(qui) if qui else "nessuna"]
    riepilogo = pd.DataFrame({"": voci, " ": valori})
    m.tabelle["riepilogo"] = riepilogo
    _v.mostra_dati(d)
    _v._mostra(("La mappa su questo dataset", riepilogo))
    _avviso_oos(m)
    _v._riquadro(
        "Il dataset su cui misuri le schede della mappa: solo l'in-sample dello studio, con lo stesso confine del "
        "Lab. Qui non c'è l'orizzonte del Lab: ogni scheda ha il suo, in ore.",
        "Qui non c'è niente da giudicare. Controlla che strumento, confine e funding siano quelli che ti "
        "aspetti.",
        "Vai alla 2 per vedere le schede approvate e quali sono già state misurate.")
    _v._riga_prove(m, "nessuna")
    return m


# ========================================================================
# 2 · Le schede
# ========================================================================

def _altri_dataset(m: SessioneMappa) -> dict:
    """{id della scheda: su quanti ALTRI dataset dello studio e' stata misurata}."""
    out = {}
    radice = _st.cartella_studio(m.cartella)
    if not radice.is_dir():
        return out
    for cartella in sorted(p for p in radice.iterdir() if p.is_dir() and p.name not in (_st.ARCHIVIO,
                                                                                         m.ingresso.dataset)):
        for sid in {e["scheda"] for e in _st.leggi_esiti_mappa(m.cartella, cartella.name, m.ingresso.studio["id"])}:
            out[sid] = out.get(sid, 0) + 1
    return out


def _esiti(m: SessioneMappa) -> list[dict]:
    return _st.leggi_esiti_mappa(m.cartella, m.ingresso.dataset, m.ingresso.studio["id"])


def elenco_schede(m: SessioneMappa) -> pd.DataFrame:
    """Schermata 2: le schede approvate (engine/ipotesi.py, docs/74) e il loro stato su questo dataset."""
    m._serve("df_is", "1 · Il dataset")
    ultimi = {e["scheda"]: e for e in _v.esiti_mappa_ultimi(_esiti(m))}
    altrove = _altri_dataset(m)
    righe = []
    for sid, sch in SCHEDE.items():
        motivo = mp.adatta(sch, m.symbol)
        e = ultimi.get(sid)
        righe.append({
            "Scheda": f"{sid} · {sch.titolo}",
            "Fascia attesa e segno": _v._attese_in_chiaro(sch.attese),
            "Variabile": sch.variabile,
            "Fasce": "quintili (365 giorni di barre passate)" if sch.tipo == "quintili" else ", ".join(sch.fasce),
            "Orizzonte (ore)": _v._fmt(float(sch.orizzonte_ore), 0),
            "Approvata il": sch.approvata,
            "Si misura qui": "sì" if motivo is None else f"no: {motivo}",
            "Su questo dataset": ("mai misurata" if e is None
                                  else f"{e['verdetto']} ({_v._quando_locale(e['quando'])}, versione {e['versione']})"),
            "Su altri dataset": _v._fmt(altrove.get(sid, 0)),
        })
    tab = pd.DataFrame(righe)
    m.tabelle["schede"] = tab
    _v._mostra(("Le schede approvate (docs/74)", tab))
    _v._riquadro(
        "Le ipotesi della mappa, scritte e approvate prima di guardare i dati: per ognuna la variabile, la fascia "
        "in cui il prezzo dovrebbe fare meglio (long) o peggio (short) del mercato e l'orizzonte.",
        "Qui non c'è niente da giudicare: è l'elenco. Una scheda già misurata su questo dataset, se la rimisuri, "
        "non aggiunge prove.",
        "Vai alla 3 e scrivi il nome di una scheda, oppure alla 4 per misurare tutte quelle che mancano.")
    _v._riga_prove(m, "nessuna")
    return tab


# ========================================================================
# 3 · La mappa di una scheda
# ========================================================================

def _df_btc(m: SessioneMappa) -> pd.DataFrame:
    """BTC dello stesso exchange e mercato, tagliato all'ultima barra dell'in-sample (M06)."""
    nome = mp.simbolo_btc(m.symbol)
    if nome not in m.btc:
        percorso = os.path.join(str(m.cartella), f"{nome}_{m.timeframe}.csv")
        if not os.path.exists(percorso):
            raise FileNotFoundError(f"Non trovo {percorso}: la scheda vuole BTC dello stesso exchange e mercato "
                                    f"(scaricalo con «python scarica_dati_crypto.py {nome}»).")
        btc = _v.carica_storico(nome, m.cartella, m.timeframe)
        m.btc[nome] = btc.loc[: m.df_is.index[-1]]
    return m.btc[nome]


def _variabile(m: SessioneMappa, sid: str) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame | None]:
    sch = SCHEDE[sid]
    df = m.df_is          # 29/10/2026 (docs/77): niente piu' colonne del funding e dello spot
    btc = _df_btc(m) if "btc" in sch.serve else None
    return df, mp.variabile(sch, df, btc), btc


def _controlli(m: SessioneMappa, ids: list[str]) -> tuple[dict, dict]:
    """
    Prima di misurare: il controllo delle fasce e la regola dei doppioni
    (mappa.escluse_per_doppione) sulle schede `ids` e su quelle di cui potrebbero
    essere doppioni. Usa solo le variabili: non e' una prova. Ritorna
    ({id: (df, valori, btc)}, {id: motivo per non misurarla}).
    """
    tutte = list(ids) + [SCHEDE[i].doppione_di for i in ids
                         if SCHEDE[i].doppione_di and SCHEDE[i].doppione_di not in ids
                         and mp.adatta(SCHEDE[SCHEDE[i].doppione_di], m.symbol) is None]
    pronte = {sid: _variabile(m, sid) for sid in tutte}
    codici = {sid: mp.codici_fasce(SCHEDE[sid], v) for sid, (_, v, _) in pronte.items()}
    fuori = {sid: motivo for sid, motivo in mp.escluse_per_doppione(codici).items() if sid in ids}
    return pronte, fuori


_COLONNE = {"fascia": "Fascia", "attesa": "Attesa", "barre": "Barre", "giornate": "Giornate",
            "scarto_bp": "Scarto dal mercato (bp)", "scarto_pips": "Scarto dal mercato (pips)", "t": "Solidità",
            "bh": "Supera i falsi positivi", "due_meta": "Regge sulle due metà",
            "incertezza_blocchi": "Incertezza a blocchi di una settimana",
            "netto_bp": "Netto dei costi (bp, solo da leggere)", "esito": "Esito"}

_COLORI_ESITO = {mp.RISPONDE: "tab:green", mp.OPPOSTO: "tab:orange", mp.NON_RISPONDE: "tab:gray",
                 mp.FUORI: "lightgray", mp.POCHI: "whitesmoke"}


def _grafico(sch, tab: pd.DataFrame, symbol: str) -> None:
    import matplotlib.pyplot as plt
    x = np.arange(len(tab))
    y = tab["scarto_bp"].to_numpy(dtype=float)
    t = tab["t"].to_numpy(dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        err = np.where(np.isfinite(t) & (t != 0), np.abs(y / t), np.nan)
    fig, ax = plt.subplots(figsize=(max(6, 1.4 * len(tab) + 3), 4))
    attese = np.array([f in sch.attese for f in tab["fascia"]])
    ax.bar(x, np.nan_to_num(y), color=[_COLORI_ESITO.get(e, "lightgray") for e in tab["esito"]],
           edgecolor=np.where(attese, "black", "none"), linewidth=np.where(attese, 2.0, 0.0), width=0.7)
    ax.errorbar(x, y, yerr=2 * err, fmt="none", ecolor="black", elinewidth=0.8, alpha=0.6)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(tab["fascia"])
    ax.set_ylabel(f"scarto dal mercato ({sch.riferimento})\n"
                  f"nelle {_v._fmt(float(sch.orizzonte_ore), 0)} ore dopo (bp, verso long)")
    ax.set_title(f"{sch.id} · {sch.titolo} · {symbol}   (bordo nero = fascia attesa; verde = risponde, arancione = "
                 "segno opposto, grigio = no)", fontsize=9)
    ax.grid(alpha=.3, axis="y")
    plt.tight_layout()
    plt.show()


def _frase_conto(sch, tab: pd.DataFrame) -> str:
    a = tab.attrs
    extra = []
    if sch.conta_segno_opposto:
        extra.append("il doppio, perché il segno è stato scelto dopo aver visto i dati: si conta anche la versione "
                     "opposta")
    if sch.prove_extra:
        extra.append(f"più {sch.prove_extra} prove già viste (docs/74)")
    return (f"Fasce misurate: {a['misurate']} su {len(tab)}. Nel conto del dataset: {a['conto']}"
            + (f" ({'; '.join(extra)})" if extra else "") + ".")


def _mostra_misura(m: SessioneMappa, sch, tab: pd.DataFrame, valori: pd.Series, codici: np.ndarray) -> None:
    _v._titolo(f"{sch.id} · {sch.titolo} (versione {sch.versione}) · {m.symbol} {m.timeframe}")
    _grafico(sch, tab, m.symbol)
    mostra = tab.reindex(columns=list(_COLONNE)).rename(columns=_COLONNE)
    mostra["Supera i falsi positivi"] = [_v._si_no(v) for v in tab["bh"]]
    mostra["Regge sulle due metà"] = [_v._si_no(v) if mis else "—" for v, mis in zip(tab["due_meta"], tab["misurata"])]
    mostra["Incertezza a blocchi di una settimana"] = [_v._si_no(v) if mis else "—"
                                                       for v, mis in zip(tab["incertezza_blocchi"], tab["misurata"])]
    m.tabelle[f"misura_{sch.id}"] = mostra
    _v._mostra((f"Le fasce di {sch.id} (in-sample dello studio, orizzonte {_v._fmt(float(sch.orizzonte_ore), 0)} "
                f"ore = {tab.attrs['H']} barre, riferimento: {sch.riferimento})", mostra),
               decimali={"Solidità": 2})
    con_valore = float(np.isfinite(valori.to_numpy(dtype=float)).mean()) if len(valori) else 0.0
    con_fascia = float(np.isfinite(codici).mean()) if len(codici) else 0.0
    _v._nota(f"La variabile {sch.variabile} c'è sul {_v._fmt(con_valore * 100, 1)}% delle barre dell'in-sample; "
             f"una fascia l'ha il {_v._fmt(con_fascia * 100, 1)}%"
             + (" (le prime barre non hanno fascia finché la finestra di 365 giorni non è piena)."
                if sch.tipo == "quintili" else "."))
    _v._riquadro(
        f"Verdetto: {tab.attrs['verdetto']}. " + _frase_conto(sch, tab)
        + " Per ogni fascia, di quanto il prezzo fa meglio (sopra lo zero) o peggio (sotto) del mercato di "
        "riferimento nelle ore dopo, in bp, con l'oscillazione dovuta al caso (le stanghette).",
        "Conta solo la fascia attesa nel verso atteso: deve superare la quota di falsi positivi (q = 20%, fra le "
        "fasce di questa scheda), reggere sulle due metà dell'in-sample e avere almeno 200 barre in 100 giornate. "
        "Un segno opposto, o una fascia non dichiarata, si mostrano ma non contano come scoperta. Il netto dei "
        "costi è solo da leggere: i costi si giudicano al Lab, sul trigger vero.",
        "Se risponde, la 5 scrive la bozza del trigger da portare nel processo degli articoli. Altrimenti passa a "
        "un'altra scheda.")


def _misura_e_registra(m: SessioneMappa, sid: str, pronta: tuple) -> pd.DataFrame:
    sch = SCHEDE[sid]
    df, valori, btc = pronta
    codici = mp.codici_fasce(sch, valori)
    tab = mp.misura(sch, df, m.pip, valori=valori, df_btc=btc, costi=m.costi, funding=m.funding)
    scritte = mp.registra(m.cartella, m.ingresso.dataset, m.macchina, m.ingresso.studio, sch, tab, m.timeframe,
                          oos_visto=bool(m.storia is not None and m.storia.oos_visto))
    m.misure[sid] = tab
    _ricostruisci(m)
    _mostra_misura(m, sch, tab, valori, codici)
    if not any(v.get("voce") == "prova" for v in scritte):
        _v._nota(f"{sid} era già nel conto di questo dataset con almeno {tab.attrs['conto']} prove: rimisurarla "
                 "non aggiunge prove (il conto non scende mai).")
    if any(v.get("voce") == "risalita" for v in scritte):
        _v._avviso(f"{sid} era già stata misurata con un'altra versione o un altro orizzonte: è una scheda cambiata "
                   "dopo la misura. Si conta di nuovo, e il giornale lo segna.")
    return tab


def mappa_di_una_scheda(m: SessioneMappa, scheda: str) -> pd.DataFrame | None:
    """
    Schermata 3: misura UNA scheda sull'in-sample del dataset e la scrive nello
    studio (voce del conto nel giornale, esito nel file della mappa). Prima il
    controllo delle fasce e quello dei doppioni: se la scheda non passa, non si
    misura e non si scrive niente. Ritorna la tabella delle fasce (None se non misurata).
    """
    m._serve("df_is", "1 · Il dataset")
    sid = (scheda or "").strip().upper()
    if sid not in SCHEDE:
        raise ValueError(f"Scheda {scheda!r} sconosciuta. Le schede approvate: {', '.join(SCHEDE)}.")
    motivo = mp.adatta(SCHEDE[sid], m.symbol)
    if motivo:
        _v._nota(f"{motivo}. Niente da misurare qui.")
        _v._riga_prove(m, "nessuna")
        return None
    _avviso_oos(m)
    pronte, fuori = _controlli(m, [sid])
    if sid in fuori:
        _v._avviso(fuori[sid] + " Nessuna misura, nessuna prova.")
        _v._riga_prove(m, "nessuna")
        return None
    prima = _v.fasce_mappa(m.prove)
    tab = _misura_e_registra(m, sid, pronte[sid])
    nuove = _v.fasce_mappa(m.prove) - prima
    _v._riga_prove(m, f"{nuove} {'fascia' if nuove == 1 else 'fasce'} della mappa" if nuove else "nessuna in più")
    return tab


# ========================================================================
# 4 · Tutte le schede non ancora misurate
# ========================================================================

def tutte_le_schede(m: SessioneMappa) -> dict:
    """
    Schermata 4 (facoltativa): come la 3, una scheda dopo l'altra, per le schede
    che si misurano su questo dataset e non sono ancora state misurate qui (con
    la stessa versione e lo stesso orizzonte). Il controllo delle fasce e quello
    dei doppioni si fanno prima, su tutte insieme. Ritorna {id: tabella o motivo}.
    """
    m._serve("df_is", "1 · Il dataset")
    _avviso_oos(m)
    fatte = {(e["scheda"], int(e["versione"]), float(e["orizzonte_ore"])) for e in _esiti(m)}
    da_fare = [sid for sid in _schede_qui(m.symbol)
               if (sid, SCHEDE[sid].versione, float(SCHEDE[sid].orizzonte_ore)) not in fatte]
    if not da_fare:
        _v._nota("Tutte le schede che si misurano su questo dataset sono già state misurate.")
        _v._riga_prove(m, "nessuna")
        return {}
    pronte, fuori = _controlli(m, da_fare)
    prima = _v.fasce_mappa(m.prove)
    out = {}
    for sid in da_fare:
        if sid in fuori:
            _v._avviso(fuori[sid] + " Nessuna misura, nessuna prova.")
            out[sid] = fuori[sid]
        else:
            out[sid] = _misura_e_registra(m, sid, pronte[sid])
    nuove = _v.fasce_mappa(m.prove) - prima
    _v._riga_prove(m, f"{nuove} {'fascia' if nuove == 1 else 'fasce'} della mappa" if nuove else "nessuna in più")
    return out


# ========================================================================
# 5 · Dalla fascia al trigger
# ========================================================================

def dalla_fascia_al_trigger(m: SessioneMappa) -> list[str]:
    """
    Schermata 5: per ogni fascia che risponde nel verso atteso (l'ultimo esito di
    ogni scheda su questo dataset), la bozza IN TESTO del trigger da portare nel
    processo degli articoli (docs/50: scheda, via libera di Mattia, codice).
    Nessun codice, nessuna prova. Ritorna le bozze.
    """
    m._serve("df_is", "1 · Il dataset")
    bozze = []
    for e in _v.esiti_mappa_ultimi(_esiti(m)):
        sch = SCHEDE.get(e["scheda"])
        for r in e.get("fasce") or []:
            if r.get("esito") != mp.RISPONDE:
                continue
            lato = "long" if e["attese"].get(r["fascia"], 0) > 0 else "short"
            quando = (f"la variabile {sch.variabile if sch else '?'} è nella fascia {r['fascia']} (soglie dei "
                      f"quintili sulle barre dei {sch.finestra_giorni if sch else 365} giorni prima)"
                      if r["fascia"] in QUINTILI else f"la barra è nella categoria «{r['fascia']}»")
            bozze.append(f"{e['scheda']} · {e['titolo']} → trigger {lato.upper()}: alla chiusura di una barra in cui "
                         f"{quando}, entra {lato} all'apertura della barra dopo; orizzonte "
                         f"{_v._fmt(float(e['orizzonte_ore']), 0)} ore. Su TradingView: {e['portabilita']}.")
    m.tabelle["bozze"] = bozze
    if bozze:
        for b in bozze:
            _v._nota(b)
    else:
        _v._nota("Nessuna fascia risponde nel verso atteso su questo dataset: nessuna bozza di trigger.")
    _v._riquadro(
        "La bozza in testo del trigger che nasce da una fascia che risponde: cosa guarda, quando entra, quanto "
        "resta. Non è codice e non è ancora un trigger del catalogo.",
        "Una fascia che risponde dice dove il prezzo si comporta diversamente dal mercato, prima dei costi. Se "
        "diventa un trigger che regge i costi lo dice solo il Lab.",
        "Porta la bozza nel processo degli articoli (docs/50): scheda in testo, via libera di Mattia, poi il codice "
        "in entry_long.py o entry_short.py. Dopo, il trigger si prova nel Lab come gli altri.")
    _v._riga_prove(m, "nessuna")
    return bozze


# ========================================================================
# 6 · Riepilogo
# ========================================================================

def riepilogo_mappa(m: SessioneMappa) -> pd.DataFrame:
    """Schermata 6: le schede misurate sul dataset (la tabella della 2b del Lab) e la soglia cumulata."""
    m._serve("df_is", "1 · Il dataset")
    tab = _v.tabella_mappa(_esiti(m), m.prove)
    m.tabelle["riepilogo_mappa"] = tab
    if tab.empty:
        _v._nota(f"Nessuna scheda della mappa misurata su {m.ingresso.dataset}.")
    else:
        _v._mostra((f"Le schede misurate su {m.ingresso.dataset} (le vedi anche alla 2b del Lab)", tab))
    conti = _v._soglia_cumulata_lab(m, np.nan)
    m.tabelle["soglia_cumulata"] = conti
    _v._nota(conti["frase"])
    _v._riquadro(
        "Le schede misurate su questo dataset e il conto di tutte le prove fatte sul dataset, nel Lab e nella mappa.",
        "La soglia cumulata dice fin dove arriva il caso da solo con tutte quelle prove: è solo informativa.",
        "Nel Lab, alla 2b, ritrovi questa stessa tabella; le fasce della mappa entrano nel conto alla schermata 1.")
    _v._riga_prove(m, "nessuna")
    return tab

# ========================================================================
# 30/10/2026 · Il notebook semplice: tre celle (Il dataset, Misura, Dettagli)
# ========================================================================
# Solo presentazione: le misure sono quelle di prima (mappa.misura, mappa.registra, gli
# stessi argomenti di _misura_e_registra). Le funzioni qui sopra restano com'erano; il
# notebook chiama queste. La cella 2 misura una scheda solo se su questo dataset non c'e'
# ancora un esito con la stessa versione e lo stesso orizzonte: altrimenti mostra l'ultimo,
# cosi' premere ▶ due volte non cambia il conto delle prove.

from .ipotesi import STESSA_ORA  # noqa: E402

PRIMA_IL_LAB = "Prima apri il Lab (schermata 1) su BINANCE_PERP_BTCUSDT M15: la mappa usa gli stessi dati."
PRIMA_LA_1 = "Prima premi ▶ sulla cella 1 · Il dataset."
NESSUNA_VERDE = "Nessuna fascia risponde su questo dataset."
NESSUN_TRIGGER = "nessun trigger nel catalogo: si crea col processo docs/50"

# il nome in chiaro di ogni scheda (il codice va tra parentesi)
NOMI_IN_CHIARO = {"M06": "BTC anticipa le altcoin", "M07": "Inversione dopo 4 ore estreme"}

# la condizione in parole da trader, per le fasce attese ({moneta}: la moneta del dataset)
CONDIZIONI = {
    ("M06", "Q5"): "nell'ultima ora BTC ha fatto molto meglio di {moneta} (il 20% dei casi più alti dell'ultimo anno)",
    ("M06", "Q1"): "nell'ultima ora BTC ha fatto molto peggio di {moneta} (il 20% dei casi più bassi dell'ultimo anno)",
    ("M07", "Q1"): "il rendimento delle ultime 4 ore è fra il 20% più basso dell'ultimo anno (una discesa forte)",
    ("M07", "Q5"): "il rendimento delle ultime 4 ore è fra il 20% più alto dell'ultimo anno (una salita forte)",
}

# scheda -> fascia -> il trigger del catalogo (entry_long.TRIGGER_LONG, entry_short.TRIGGER_SHORT)
TRIGGER_DELLE_SCHEDE = {"M07": {"Q1": "E45_RENDIMENTO_4H_ENTRA_Q1", "Q5": "E45_SHORT_RENDIMENTO_4H_ENTRA_Q5"}}

# il semaforo: il colore viene dal verdetto gia' calcolato da mappa.misura
SEMAFORO = {mp.RISPONDE: ("verde", "Risponde nel verso atteso"),
            mp.NON_RISPONDE: ("grigio", "Non si distingue dal caso"),
            mp.OPPOSTO: ("arancione", "Va nel verso opposto"),
            mp.POCHI: ("grigio chiaro", "Troppi pochi casi per dirlo"),
            mp.FUORI: ("grigio chiaro", "Troppi pochi casi per dirlo")}
_TINTE = {"verde": "#2e9e44", "grigio": "#8a8a8a", "arancione": "#e07b00", "grigio chiaro": "#d4d4d4"}


def semaforo(verdetto: str | None) -> tuple[str, str]:
    """(colore, testo) del semaforo di una scheda, dal verdetto di mappa.misura."""
    return SEMAFORO.get(verdetto, ("grigio chiaro", "Troppi pochi casi per dirlo"))


def nome_in_chiaro(sid: str) -> str:
    sch = SCHEDE.get(sid)
    return NOMI_IN_CHIARO.get(sid, sch.titolo if sch else sid)


def _moneta(symbol: str) -> str:
    from .exchange import parti_symbol
    return parti_symbol(symbol)["base"]


def condizione(sch, fascia: str, symbol: str) -> str:
    """La condizione di una fascia in parole: dal dizionario, altrimenti generica."""
    testo = CONDIZIONI.get((sch.id, fascia))
    if testo:
        return testo.format(moneta=_moneta(symbol)) if "{moneta}" in testo else testo
    if sch.tipo == "quintili" and fascia in QUINTILI:
        j = QUINTILI.index(fascia)
        return f"{sch.variabile} è fra il {20 * j}% e il {20 * (j + 1)}% dei valori dell'ultimo anno"
    return f"la barra è nella categoria «{fascia}»"


def _ore_dopo(sch) -> str:
    ore = float(sch.orizzonte_ore)
    return "nell'ora dopo" if ore == 1 else f"nelle {_v._fmt(ore, 0)} ore dopo"


def _il_mercato(sch) -> str:
    return "il mercato della stessa ora" if sch.riferimento == STESSA_ORA else "il mercato"


_LATI = {1: ("LONG", "del long", "il long"), -1: ("SHORT", "dello short", "lo short")}


def frase_fascia(sch, riga: dict, symbol: str) -> str:
    """
    La frase con i numeri di una fascia. Lo scarto di mappa.misura e' nel verso
    long (+ = il prezzo fa meglio del mercato): «sopra» o «sotto» descrive il
    prezzo; per una fascia attesa si dice anche se e' a favore del trade o contro.
    """
    fascia = riga["fascia"]
    quando = f"Quando {condizione(sch, fascia, symbol)}"
    casi = f"{_v._fmt(int(riga['barre']))} casi in {_v._fmt(int(riga['giornate']))} giornate"
    if not riga.get("misurata"):
        return (f"{quando}: troppi pochi casi per dirlo ({casi}; ne servono almeno {mp.MIN_BARRE} in "
                f"{mp.MIN_GIORNATE} giornate).")
    x = float(riga["scarto_bp"])
    if x == 0:
        frase = f"{quando}, {_ore_dopo(sch)} il prezzo ha fatto in media come {_il_mercato(sch)} (su {casi})"
    else:
        frase = (f"{quando}, {_ore_dopo(sch)} il prezzo ha fatto in media {_v._fmt(abs(x), 1)} bp (1 bp = 0,01%) "
                 f"{'sopra' if x > 0 else 'sotto'} {_il_mercato(sch)} (su {casi})")
    lato = sch.attese.get(fascia, 0)
    if lato and x != 0:
        _, del_lato, il_lato = _LATI[lato]
        frase += f": a favore {del_lato}" if x * lato > 0 else f": contro {il_lato}"
    return frase + "."


def trigger_della_fascia(sid: str, fascia: str) -> str:
    return TRIGGER_DELLE_SCHEDE.get(sid, {}).get(fascia) or NESSUN_TRIGGER


def cosa_ti_porti_a_casa(risultati: dict, symbol: str) -> list[str]:
    """Una riga per ogni fascia verde (esito «risponde»): lato, condizione, orizzonte, scarto nel verso del trade, trigger."""
    righe = []
    for sid, tab in risultati.items():
        sch = SCHEDE[sid]
        for r in tab.to_dict("records"):
            if r.get("esito") != mp.RISPONDE:
                continue
            lato = sch.attese.get(r["fascia"], 0)
            if not lato:
                continue
            ore = float(sch.orizzonte_ore)
            righe.append(f"{_LATI[lato][0]} quando {condizione(sch, r['fascia'], symbol)}; tieni "
                         f"{_v._fmt(ore, 0)} {'ora' if ore == 1 else 'ore'}; scarto medio "
                         f"{_v._fmt(lato * float(r['scarto_bp']), 1)} bp (1 bp = 0,01%) a favore del trade, prima dei "
                         f"costi (i costi li giudica il Lab). Trigger da usare nel Lab: "
                         f"{trigger_della_fascia(sid, r['fascia'])}.")
    return righe


def _testo(testo: str, stile: str) -> None:
    if _v._in_notebook():
        _v._html(f"<div style='{stile}'>{_html_escape(testo)}</div>")
    else:
        print(testo)


def _html_escape(testo: str) -> str:
    import html
    return html.escape(testo)


def _grande(testo: str) -> None:
    if _v._in_notebook():
        _testo(testo, "font:600 21px/1.3 system-ui,sans-serif;margin:24px 0 6px")
    else:
        print(f"\n{testo}\n" + "=" * len(testo))


def _mostra_semaforo(verdetto) -> None:
    colore, testo = semaforo(verdetto)
    if _v._in_notebook():
        _v._html(f"<div style='font:600 15px/1.4 system-ui,sans-serif;margin:2px 0 6px'>"
                 f"<span style='display:inline-block;width:14px;height:14px;border-radius:50%;"
                 f"background:{_TINTE[colore]};border:1px solid #777;vertical-align:-2px;margin-right:8px'></span>"
                 f"{_html_escape(testo)}</div>")
    else:
        print(f"[{colore.upper()}] {testo}")


def _non_qui(motivo: str) -> None:
    _testo(f"Non si misura su questo dataset: {motivo}", "font:14px/1.5 system-ui,sans-serif;opacity:.75;margin:2px 0 8px")


def _riga_grigia(testo: str) -> None:
    _testo(testo, "font:12.5px/1.45 system-ui,sans-serif;color:#8a8a8a;margin:14px 0 4px;"
                  "border-top:1px solid rgba(128,128,128,.4);padding-top:5px")


def il_dataset(symbol: str, timeframe: str = "M15", cartella="dati", aggiorna: bool = False,
               macchina: str | None = None) -> SessioneMappa | None:
    """
    Cella 1 del notebook semplice: apri_mappa senza stampare niente, poi al
    massimo tre righe (strumento e timeframe, periodo dei dati, se il Lab ha gia'
    diviso i dati). Quello che apri_mappa stampa resta per la cella Dettagli.
    Senza lo studio aperto: la frase che dice di aprire il Lab, e None.
    """
    if _st.leggi_confine(cartella) is None:
        print(PRIMA_IL_LAB)
        return None
    from IPython.utils.capture import capture_output
    with capture_output() as uscita:
        m = apri_mappa(symbol, timeframe, cartella, aggiorna=aggiorna, macchina=macchina)
    m.uscita_1 = uscita
    i = m.ingresso
    print(f"{symbol} · {timeframe}")
    print(f"Dati dal {m.df.index[0]:%d/%m/%Y} al {m.df.index[-1]:%d/%m/%Y}: la mappa misura solo le barre fino al "
          f"{_v._giorno_ora(i.confine)}; le altre restano per l'out-of-sample del Lab.")
    riga = (f"Pronto: i dati sono già divisi dal Lab (dal {pd.Timestamp(i.studio['aperto_il']):%d/%m/%Y}), la mappa "
            "usa la stessa divisione.")
    if m.storia is not None and m.storia.oos_visto:
        n = len(m.storia.diario)
        riga += (f" Attenzione: l'out-of-sample di questo dataset l'hai già guardato ({n} "
                 f"{'volta' if n == 1 else 'volte'}).")
    print(riga)
    return m


def _tabella_da_esito(m: SessioneMappa, e: dict) -> pd.DataFrame:
    """La tabella delle fasce dall'ultimo esito salvato (le stesse colonne di mappa.misura, senza ricalcolare)."""
    tab = pd.DataFrame(e.get("fasce") or [])
    for c in ("scarto_bp", "scarto_pips", "t", "p", "netto_bp"):
        tab[c] = pd.to_numeric(tab[c], errors="coerce") if c in tab.columns else np.nan
    for c in ("misurata", "bh", "due_meta", "incertezza_blocchi"):
        tab[c] = tab[c].fillna(False).astype(bool) if c in tab.columns else False
    try:
        H = mp.barre_orizzonte(e["orizzonte_ore"], m.df_is.index)
    except ValueError:
        H = None
    tab.attrs.update(scheda=e["scheda"], versione=int(e["versione"]), verdetto=e.get("verdetto"), H=H,
                     orizzonte_ore=float(e["orizzonte_ore"]), riferimento=e.get("riferimento"),
                     misurate=int(tab["misurata"].sum()) if len(tab) else 0, conto=int(e.get("conto") or 0))
    return tab


def _misura_scheda(m: SessioneMappa, sid: str) -> pd.DataFrame | str:
    """Come _misura_e_registra, senza mostrare niente: la tabella, o il motivo per cui non si misura."""
    sch = SCHEDE[sid]
    try:
        pronte, fuori = _controlli(m, [sid])
        if sid in fuori:
            return fuori[sid]
        df, valori, btc = pronte[sid]
        tab = mp.misura(sch, df, m.pip, valori=valori, df_btc=btc, costi=m.costi, funding=m.funding)
    except (FileNotFoundError, ValueError) as e:
        return str(e)
    scritte = mp.registra(m.cartella, m.ingresso.dataset, m.macchina, m.ingresso.studio, sch, tab, m.timeframe,
                          oos_visto=bool(m.storia is not None and m.storia.oos_visto))
    m.misure[sid] = tab
    _ricostruisci(m)
    if any(v.get("voce") == "risalita" for v in scritte):
        _v._avviso(f"{sid} era già stata misurata con un'altra versione o un altro orizzonte: è una scheda cambiata "
                   "dopo la misura. Si conta di nuovo.")
    return tab


def _ultimi_qui(m: SessioneMappa) -> dict:
    """{id: ultimo esito} delle schede del catalogo con la stessa versione e lo stesso orizzonte, su questo dataset."""
    ultimi = {}
    for e in _v.esiti_mappa_ultimi(_esiti(m)):
        sch = SCHEDE.get(e["scheda"])
        if sch and (int(e["versione"]), float(e["orizzonte_ore"])) == (sch.versione, float(sch.orizzonte_ore)):
            ultimi[e["scheda"]] = e
    return ultimi


def _grafico_semplice(sch, tab: pd.DataFrame, symbol: str) -> None:
    """Il grafico di _grafico, con il nome in chiaro e la legenda."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    x = np.arange(len(tab))
    y = tab["scarto_bp"].to_numpy(dtype=float)
    t = tab["t"].to_numpy(dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        err = np.where(np.isfinite(t) & (t != 0), np.abs(y / t), np.nan)
    fig, ax = plt.subplots(figsize=(max(6, 1.4 * len(tab) + 3) + 3, 4))
    attese = np.array([f in sch.attese for f in tab["fascia"]])
    ax.bar(x, np.nan_to_num(y), color=[_COLORI_ESITO.get(e, "lightgray") for e in tab["esito"]],
           edgecolor=np.where(attese, "black", "none"), linewidth=np.where(attese, 2.0, 0.0), width=0.7)
    ax.errorbar(x, y, yerr=2 * err, fmt="none", ecolor="black", elinewidth=0.8, alpha=0.6)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(tab["fascia"])
    if sch.tipo == "quintili":
        ax.set_xlabel("Q1 = barre col valore più basso, Q5 = più alto")
    ax.set_ylabel(f"scarto dal {_il_mercato(sch)[3:]}, {_ore_dopo(sch)}\n"
                  "(bp, 1 bp = 0,01%; sopra zero = il prezzo fa meglio)")
    ax.set_title(f"{nome_in_chiaro(sch.id)} ({sch.id}) · {symbol}", fontsize=10)
    legenda = [Patch(facecolor=_COLORI_ESITO[mp.RISPONDE], label="risponde nel verso atteso"),
               Patch(facecolor=_COLORI_ESITO[mp.OPPOSTO], label="va nel verso opposto"),
               Patch(facecolor=_COLORI_ESITO[mp.NON_RISPONDE], label="non si distingue dal caso"),
               Patch(facecolor=_COLORI_ESITO[mp.FUORI], label="fascia senza attesa"),
               Patch(facecolor=_COLORI_ESITO[mp.POCHI], edgecolor="lightgray", label="troppi pochi casi"),
               Patch(facecolor="white", edgecolor="black", linewidth=2, label="bordo nero = fascia attesa"),
               Line2D([0], [0], color="black", lw=0.8, label="stanghetta = quanto può fare il caso")]
    ax.legend(handles=legenda, fontsize=8, loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False)
    ax.grid(alpha=.3, axis="y")
    plt.tight_layout()
    plt.show()


def misura_mappa(m: SessioneMappa | None, solo=None) -> dict:
    """
    Cella 2 del notebook semplice: per ogni scheda del catalogo, il nome, il
    semaforo, una frase con i numeri per ogni fascia attesa e il grafico; poi
    «Cosa ti porti a casa» e il numero di prove contate sul dataset. Misura (e
    scrive nello studio, come la schermata 3) solo le schede senza un esito
    qui con la stessa versione e lo stesso orizzonte; per le altre mostra
    l'ultimo esito. `solo`: le schede da guardare (prove d'identita'), None = tutte.
    Ritorna {id: tabella delle fasce}.
    """
    if m is None:
        print(PRIMA_LA_1)
        return {}
    m._serve("df_is", "1 · Il dataset")
    ultimi = _ultimi_qui(m)
    risultati = {}
    for sid, sch in SCHEDE.items():
        if solo is not None and sid not in solo:
            continue
        _grande(f"{nome_in_chiaro(sid)} ({sid})")
        motivo = mp.adatta(sch, m.symbol)
        if motivo:
            _non_qui(motivo)
            continue
        tab = _tabella_da_esito(m, ultimi[sid]) if sid in ultimi else _misura_scheda(m, sid)
        if isinstance(tab, str):
            _non_qui(tab)
            continue
        risultati[sid] = tab
        _mostra_semaforo(tab.attrs.get("verdetto"))
        righe = {r["fascia"]: r for r in tab.to_dict("records")}
        for fascia in sch.attese:
            if fascia in righe:
                r = righe[fascia]
                esito = f" Questa fascia: {semaforo(r.get('esito'))[1].lower()}." if r.get("misurata") else ""
                _testo(frase_fascia(sch, r, m.symbol) + esito, "font:14px/1.5 system-ui,sans-serif;margin:2px 0 4px")
        _grafico_semplice(sch, tab, m.symbol)
    m.ultime = risultati

    _grande("Cosa ti porti a casa")
    righe = cosa_ti_porti_a_casa(risultati, m.symbol)
    for r in righe or [NESSUNA_VERDE]:
        _testo(r, "font:14px/1.5 system-ui,sans-serif;margin:3px 0")
    k = _v._soglia_cumulata_lab(m, np.nan)["k"]
    _riga_grigia(f"Prove contate su questo dataset finora (Lab e mappa): {_v._fmt(k, 1) if isinstance(k, float) else _v._fmt(k)}.")
    return risultati


def dettagli_mappa(m: SessioneMappa | None) -> None:
    """
    Cella Dettagli (facoltativa): quello che la cella 1 non stampa, l'elenco delle
    schede, la tabella completa di ogni scheda guardata alla 2 (colonne, nota,
    riquadro), le bozze dei trigger, il riepilogo con la soglia cumulata. Non misura niente.
    """
    if m is None:
        print(PRIMA_LA_1)
        return
    m._serve("df_is", "1 · Il dataset")
    uscita = getattr(m, "uscita_1", None)
    if uscita is not None:
        _v._titolo("Il dataset, in dettaglio")
        uscita.show()
    elenco_schede(m)
    tabelle = getattr(m, "ultime", None)
    if tabelle is None:
        tabelle = {sid: _tabella_da_esito(m, e) for sid, e in _ultimi_qui(m).items()
                   if mp.adatta(SCHEDE[sid], m.symbol) is None}
    for sid, tab in tabelle.items():
        sch = SCHEDE[sid]
        _, valori, _ = _variabile(m, sid)
        _mostra_misura(m, sch, tab, valori, mp.codici_fasce(sch, valori))
    dalla_fascia_al_trigger(m)
    riepilogo_mappa(m)
