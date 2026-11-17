"""
Suite di collaudo dei trigger generati nel Lab (17/11/2026, docs/83): il campo «trigger_generati» della schermata 1
(engine/vetrina.py: prepara, carica_trigger_generati, nome_con_ricetta) e «python -m engine.generatore --elenco».

Cosa verifica
-------------
A  i nomi: vuoto = niente; nomi giusti = i trigger del catalogo con il loro lato; nome sbagliato, catalogo mancante,
   short sullo spot = il Lab si ferma con un messaggio che dice cosa fare, senza traceback nel notebook;
B  elenco vuoto = il Lab di prima: stesso registro, stesso event study (2c), stessa rosa (3a), nessuna riga in piu'
   nel riepilogo, anche dopo un giro con i trigger generati;
C  con due trigger generati (long e short): entrano nel registro con il loro lato, la 2c li misura e li conta nelle
   prove, la rosa li vede, la 3b li accetta in «aggiungi», l'atlante (3c) li misura; nei grafici accanto al nome
   la ricetta leggibile;
D  il comando «python -m engine.generatore --elenco»: ricette e nomi dei trigger del catalogo salvato.

Come si lancia (da terminale, dalla cartella del progetto):

    python test_lab_trigger_generati.py

Non serve la rete ne' i dati veri (usa dati_catalogo/generati_v1.json del repo e un mercato inventato).
Alla fine stampa «RISULTATO: N/N test superati».
"""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")

import engine.exchange as X
from engine import registro_dataset as RD
from engine import registry as reg
from engine import vetrina as vt
from engine.generatore.__main__ import main as comando
from engine.generatore.trigger import TriggerGenerato
from engine.quarantena import imposta_rollover
from test_atlante import Mercato, _indice

ESITI: list[bool] = []
SYM = "BINANCE_PERP_BTCUSDT"
SPOT = "BINANCE_SPOT_BTCUSDT"
SCELTI = "G0002_P90_SU, G0002_SHORT_P90_SU"
FIGURA = os.environ.get("TSC_FIGURA_GENERATI")      # se c'e', il grafico della 2c si salva qui (PNG)


def check(nome, condizione, dettaglio=""):
    ESITI.append(bool(condizione))
    print(f"  [{'OK' if condizione else 'FALLITO'}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""))


def muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        out = f(*a, **k)
    plt.close("all")
    return out


def fermo(f, *frammenti) -> bool:
    """La funzione si ferma con LabFermo, il messaggio contiene i frammenti e il notebook non mostra il traceback."""
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            f()
    except vt.LabFermo as e:
        righe = e._render_traceback_()
        return all(x in str(e) for x in frammenti) and len(righe) == 1 and "Traceback" not in righe[0]
    except Exception:
        return False
    return False


def scrivi_dataset(cartella, symbol=SYM, giorni=200, seme=3):
    df = Mercato(_indice("2022-01-03", giorni=giorni), seme=seme).df()
    X.salva_csv(df, os.path.join(str(cartella), f"{symbol}_M15.csv"))
    if "PERP" in symbol:
        orari = pd.date_range(df.index[0].floor("8h"), df.index[-1].ceil("8h"), freq="8h")
        X.salva_funding(X.con_intervalli(pd.DataFrame({"tasso": 0.0001}, index=orari)), X.file_funding(symbol, cartella))
    return df


def generati_nel_registro() -> list[str]:
    return [n for n in reg.list_entries() if isinstance(reg.get_entry(n), TriggerGenerato)]


# ------------------------------------------------------------ sezione A --
def sezione_a(radice: Path):
    print("\nA · I nomi e i messaggi")
    check("A1. campo vuoto (o solo spazi e virgole) = nessun trigger generato",
          vt.carica_trigger_generati("") == {} and vt.carica_trigger_generati(" , ") == {}
          and vt.carica_trigger_generati(None) == {} and vt.carica_trigger_generati([]) == {})
    g = vt.carica_trigger_generati(SCELTI)
    check("A2. due nomi giusti: i trigger del catalogo, long e short, nell'ordine scritto; anche come lista",
          list(g) == ["G0002_P90_SU", "G0002_SHORT_P90_SU"] and g["G0002_P90_SU"].lato == 1
          and g["G0002_SHORT_P90_SU"].lato == -1
          and list(vt.carica_trigger_generati(["G0002_P90_SU", "G0002_P90_SU"])) == ["G0002_P90_SU"])
    check("A3. nome sbagliato: si ferma, dice quale nome e come trovare l'elenco (--elenco), senza traceback",
          fermo(lambda: vt.carica_trigger_generati("G0002_P90_SU, G9999_P90_SU"), "G9999_P90_SU", "--elenco",
                "trigger_generati") and not fermo(lambda: vt.carica_trigger_generati("G0002_P90_SU")))
    check("A4. catalogo mancante: si ferma e dice come crearlo (python -m engine.generatore --n) o di lasciare vuoto",
          fermo(lambda: vt.carica_trigger_generati("G0002_P90_SU", percorso=radice / "non_c_e.json"),
                "python -m engine.generatore --n", "lascia vuoto"))
    check("A5. sullo spot uno short generato: si ferma e dice di tenere solo i long",
          fermo(lambda: vt.carica_trigger_generati(SCELTI, solo_long=True), "spot", "G0002_SHORT_P90_SU")
          and list(vt.carica_trigger_generati("G0002_P90_SU", solo_long=True)) == ["G0002_P90_SU"])
    cs = radice / "spot"
    cs.mkdir()
    scrivi_dataset(cs, SPOT, giorni=30)
    reg.clear_registry()
    RD.azzera()
    check("A6. la schermata 1 si ferma prima di caricare i dati, e il registro resta com'era",
          fermo(lambda: vt.prepara(SYM, H=16, cartella=str(radice / "vuota"), trigger_generati="G0002_XX"), "G0002_XX")
          and fermo(lambda: vt.prepara(SPOT, H=16, cartella=str(cs), trigger_generati=SCELTI), "spot")
          and reg.list_entries() == [])
    RD.azzera()


# ---------------------------------------------------------- sezioni B, C --
def sessione(cartella, generati=""):
    s = muto(vt.prepara, SYM, H=16, cartella=str(cartella), trigger_generati=generati)
    ev = muto(vt.esplora, s)
    return s, ev, vt._rosa_sessione(s).copy()


def sezione_b_c(radice: Path):
    print("\nB · Elenco vuoto = il Lab di prima")
    c = radice / "lab"
    c.mkdir()
    scrivi_dataset(c)
    reg.clear_registry()
    RD.azzera()
    s0, ev0, rosa0 = sessione(c)
    nomi0 = reg.list_entries()
    trig0 = s0.prove.get("trigger")
    with contextlib.redirect_stdout(io.StringIO()):
        vt._registra_condizioni()
    check("B1. con il campo vuoto il registro e' quello del solo catalogo (nessun trigger generato), e il riepilogo "
          "non ha righe in piu'",
          not generati_nel_registro() and s0.trigger_generati == ()
          and "Trigger generati (docs/83)" not in list(s0.tabelle["riepilogo"].iloc[:, 0]))
    print("\nC · Con due trigger generati, long e short")
    s1, ev1, rosa1 = sessione(c, SCELTI)
    dirs = {n: reg.get_entry_direction(n) for n in generati_nel_registro()}
    check("C1. entrano nel registro con il loro lato; il riepilogo li elenca con la ricetta",
          dirs == {"G0002_P90_SU": 1, "G0002_SHORT_P90_SU": -1} and s1.trigger_generati == tuple(dirs)
          and any("media(sv, 14): attraversa P90 verso l'alto" in str(x) for x in s1.tabelle["riepilogo"].iloc[:, 1]))
    sint1 = ev1.sintesi
    del_catalogo = sint1[~sint1["candidato"].str.startswith("G0002")].reset_index(drop=True)
    check("C2. la 2c (event study) li misura insieme al catalogo, e le righe dei trigger del catalogo non cambiano",
          {"G0002_P90_SU", "G0002_SHORT_P90_SU"} <= set(sint1["candidato"]) and len(sint1) == len(ev0.sintesi) + 2
          and del_catalogo.equals(ev0.sintesi), f"{len(sint1)} righe contro {len(ev0.sintesi)}")
    check("C3. il conto delle prove: la voce dei trigger sale di 2", s1.prove.get("trigger") == trig0 + 2,
          f"{trig0} -> {s1.prove.get('trigger')}")
    check("C4. la rosa (3a) li vede come candidati, con lo stesso metro",
          {"G0002_P90_SU", "G0002_SHORT_P90_SU"} <= set(rosa1["candidato"]))
    tab = muto(vt.scegli_casistiche, s1, parti_da="niente", aggiungi_long="G0002_P90_SU",
               aggiungi_short="G0002_SHORT_P90_SU")
    check("C5. la 3b li accetta in «aggiungi», come un trigger del catalogo",
          s1.entry_long == "G0002_P90_SU" and s1.entry_short == "G0002_SHORT_P90_SU" and len(tab) == 2,
          f"{s1.entry_long}, {s1.entry_short}")
    titoli = []
    vecchio_show = plt.show
    plt.show = lambda *a, **k: titoli.extend(ax.get_title(loc="left") for f in map(plt.figure, plt.get_fignums())
                                             for ax in f.axes)
    try:
        muto(vt.atlante_dei_trigger, s1)
    finally:
        plt.show = vecchio_show
    check("C6. l'atlante (3c) li misura; nel titolo del grafico accanto al nome la ricetta",
          any(t.startswith("G0002_P90_SU · media(sv, 14): attraversa P90 verso l'alto") for t in titoli)
          and any(t.startswith("G0002_SHORT_P90_SU · media(sv, 14): attraversa P90 verso l'alto") for t in titoli),
          str(titoli)[:200])
    curve = vt._curve_scarto(s1, ["G0002_P90_SU", "E1_RSI_CROSS_OVERSOLD"])
    etichette = []
    plt.show = lambda *a, **k: etichette.extend(plt.gca().get_legend_handles_labels()[1])
    try:
        vt.grafico_scarto(curve, s1.H, s1.unita, "long")
        if FIGURA:
            plt.gcf().savefig(FIGURA, dpi=110)
    finally:
        plt.show = vecchio_show
        plt.close("all")
    check("C7. 2c: nella legenda del grafico accanto al nome la ricetta; i trigger del catalogo restano come sono",
          etichette == ["G0002_P90_SU · media(sv, 14): attraversa P90 verso l'alto", "E1_RSI_CROSS_OVERSOLD"],
          str(etichette))
    g = vt.carica_trigger_generati("G0001_ZERO_GIU, G0002_SHORT_MEDIA20_SU")
    for n, f in g.items():
        reg.register_entry(n, direction=f.lato)(f)
    check("C8. nome_con_ricetta: lo zero e la media in chiaro, il verso il basso; i nomi del catalogo e quelli fuori "
          "registro restano come sono",
          vt.nome_con_ricetta("G0001_ZERO_GIU") == "G0001_ZERO_GIU · media(sv, 5): attraversa lo zero verso il basso"
          and vt.nome_con_ricetta("G0002_SHORT_MEDIA20_SU")
          == "G0002_SHORT_MEDIA20_SU · media(sv, 14): attraversa la sua media di 20 barre verso l'alto"
          and vt.nome_con_ricetta("NON_REGISTRATO") == "NON_REGISTRATO"
          and vt.nome_con_ricetta("E1_RSI_CROSS_OVERSOLD") == "E1_RSI_CROSS_OVERSOLD")

    print("\nB · (segue) Dopo un giro con i trigger generati, di nuovo il campo vuoto")
    s2, ev2, rosa2 = sessione(c)
    check("B2. il campo vuoto toglie i trigger generati del giro prima: registro identico al primo giro",
          reg.list_entries() == nomi0 and not generati_nel_registro())
    check("B3. stesso event study (2c) e stessa rosa (3a) del primo giro, numero per numero",
          ev2.sintesi.equals(ev0.sintesi) and rosa2.equals(rosa0))
    check("B4. il conto delle prove non scende (per ogni voce vale il numero piu' alto, docs/76)",
          s2.prove.get("trigger") == trig0 + 2)
    reg.clear_registry()
    RD.azzera()


# ------------------------------------------------------------ sezione D --
def sezione_d(radice: Path):
    print("\nD · python -m engine.generatore --elenco")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        codice = comando(["--elenco"])
    t = out.getvalue()
    check("D1. stampa ricette e nomi dei trigger del catalogo salvato: G0002 media(sv, 14), long e short",
          codice == 0 and "G0002  media(sv, 14)" in t and "G0002_P90_SU" in t and "G0002_SHORT_P90_SU" in t
          and "112 ricette" in t and t.count("   long:  ") == 112)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        codice = comando(["--elenco", "--file", str(radice / "non_c_e.json")])
    check("D2. senza catalogo dice come crearlo", codice == 2 and "python -m engine.generatore --n" in out.getvalue())


def esegui() -> int:
    print("=" * 70)
    print("test_lab_trigger_generati · i trigger generati nel Lab (docs/83)")
    print("=" * 70)
    imposta_rollover(None)
    radice = Path(tempfile.mkdtemp(prefix="lab_generati_"))
    try:
        sezione_a(radice)
        sezione_b_c(radice)
        sezione_d(radice)
    finally:
        reg.clear_registry()
        RD.azzera()
        shutil.rmtree(radice, ignore_errors=True)
    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
