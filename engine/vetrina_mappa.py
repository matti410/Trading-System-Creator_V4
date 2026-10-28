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

LO STUDIO (docs/73 §B.4)
------------------------
La mappa entra nello studio con studio.entra (confine e impronta, come il Lab)
e ricostruisce il registro del dataset dai giornali, ma non chiama prepara:
non scrive nessuna voce «orizzonte», cosi' non tocca gli H provati del Lab.
Non apre lo studio e non ricalcola il confine: quelli si fanno dal Lab.
Il conto di ogni scheda va nel giornale come voce «prova» con dove = "mappa"
(mappa.registra), l'esito nel file della mappa, che la 2b del Lab legge.

Una scheda con le fasce degeneri (mappa.controlla_fasce) o doppione di
un'altra (la regola di Mattia per M04 e M05) non si misura e non scrive niente.

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
        self.costi = self.pip = self.funding = self.spot = None
        self.spot_nota = None
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


def _carica_spot(symbol: str, timeframe: str, cartella) -> tuple[pd.DataFrame | None, str | None]:
    """Lo spot della stessa coppia e dello stesso exchange di un perpetual (per la basis), o (None, motivo)."""
    from .exchange import leggi_csv, parti_symbol
    p = parti_symbol(symbol)
    if p["mercato"] != "PERP":
        return None, None
    spot = f"{p['exchange']}_SPOT_{p['coppia']}"
    percorso = os.path.join(str(cartella), f"{spot}_{timeframe}.csv")
    if not os.path.exists(percorso):
        return None, (f"manca {percorso}: le schede che vogliono lo spot (la basis) non si misurano "
                      f"(scaricalo con «python scarica_dati_crypto.py {spot}»)")
    return leggi_csv(percorso), None


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
    m.spot, m.spot_nota = _carica_spot(symbol, timeframe, cartella)
    _ricostruisci(m)

    i = m.ingresso
    qui = _schede_qui(symbol)
    voci = ["Strumento", f"Barre {timeframe}", "In-sample (si misura qui)", "Out-of-sample (mai visto)",
            "Funding (perpetual)", "Spot della stessa coppia", "Studio", "Schede che si misurano qui"]
    valori = [symbol, _v._fmt(len(d.df)),
              f"{_v._fmt(len(m.df_is))} barre, fino al {_v._giorno_ora(i.confine)} · confine dello studio",
              f"{_v._fmt(len(i.df_oos))} barre, dal {_v._giorno_ora(i.confine)}",
              "sì: le schede del funding si misurano" if m.funding is not None else "no (spot: niente funding)",
              ("sì" if m.spot is not None else (m.spot_nota or "no (spot: la basis non c'è)")),
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
        "Qui non c'è niente da giudicare. Controlla che strumento, confine, funding e spot siano quelli che ti "
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


def _df_scheda(m: SessioneMappa, sch) -> pd.DataFrame:
    if "spot" in sch.serve and m.spot is None:
        raise ValueError(f"{sch.id} vuole lo spot della stessa coppia: {m.spot_nota or "non c'è"}.")
    if "funding" in sch.serve and m.funding is None:
        raise ValueError(f"{sch.id} vuole il funding del perpetual, che qui non c'è.")
    return mp.prepara_df(m.df_is, funding=m.funding if "funding" in sch.serve else None,
                         spot=m.spot if "spot" in sch.serve else None)


def _variabile(m: SessioneMappa, sid: str) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame | None]:
    sch = SCHEDE[sid]
    df = _df_scheda(m, sch)
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
    if tab.attrs.get("fuori_intervallo"):
        _v._nota(f"{_v._fmt(int(tab.attrs['fuori_intervallo']))} pagamenti con un intervallo diverso da 8 ore sono "
                 "rimasti fuori: la scheda parla dei pagamenti delle 00, 08 e 16 UTC.")
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
