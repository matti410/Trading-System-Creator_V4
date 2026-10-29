"""
Suite di validazione del CONTO DEL NOTEBOOK DI RICERCA nello studio (28/10/2026,
docs/76, PR 1: A1 e A2). Moduli: engine/registro_dataset.py (metti_prova, da_voci)
e le aggiunte di engine/vetrina.py (chiave_celle, chiave_uscite, chiave_filtri,
impostazioni_uscite, trigger_candidati, conta_*, soglia_cumulata_studio).

Cosa verifica
-------------
A  la regola del piu' alto (D1): un numero piu' basso scritto dopo non abbassa il
   conto, ne' in memoria ne' nella rilettura dei giornali; voci semplici e a chiave;
B  le chiavi: la ricerca costruisce, con le stesse impostazioni, le stesse chiavi
   delle schermate 3c, 4 e 5 del Lab (stesso H, stessi assi, stessi trigger);
   la 2.3 e la 3.3 (D2) hanno una chiave loro;
C  lo studio: la ricerca scrive solo le voci cambiate; la stessa ricerca due volte
   non alza il conto; Lab e ricerca sulle stesse chiavi non lo alzano; il riavvio
   ritrova lo stesso conto; la soglia della ricerca e' quella del Lab sullo stesso
   conto; una voce con «visto il» (A3) si rilegge;
D  lo spot (A2): la ricerca misura gli stessi trigger del Lab, nello stesso ordine;
   sullo spot solo i long, sui perpetual tutti;
E  (29/10/2026, docs/77, decisione D2 di Mattia) le situazioni gia' misurate: un
   atlante senza la basis, con lo stesso H e gli stessi trigger di una voce gia'
   contata con la basis, non si conta di nuovo (ne' in memoria ne' nel giornale);
   con un H nuovo o con altri trigger si conta come sempre.

Come si lancia (da terminale, dalla cartella del progetto):

    python test_conto_ricerca.py

Non serve la rete ne' i dati veri. Alla fine stampa «RISULTATO: N/N test superati».
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import warnings
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

warnings.simplefilter("ignore")

from engine import registro_dataset as RD
from engine import studio as ST
from engine import vetrina as vt

ESITI: list[bool] = []


def check(nome, condizione, dettaglio=""):
    ESITI.append(bool(condizione))
    print(f"  [{'OK' if condizione else 'FALLITO'}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""))


def muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def storico(periodi=1300, passo="1h", seme=7):
    """Un random walk 24/7 con OHLC coerenti (lo studio ne legge solo l'indice e l'impronta)."""
    idx = pd.date_range("2024-01-01", periods=periodi, freq=passo, tz="UTC")
    g = np.random.default_rng(seme)
    close = np.round(30000.0 * np.exp(np.cumsum(g.normal(0, 0.01, len(idx)))), 2)
    open_ = np.r_[30000.0, close[:-1]]
    return pd.DataFrame({"Open": open_, "High": np.maximum(open_, close) + 1, "Low": np.minimum(open_, close) - 1,
                         "Close": close, "Volume": 1.0}, index=idx)


def tabella(**attrs):
    t = pd.DataFrame({"x": [1]})
    t.attrs.update(attrs)
    return t


def ricerca(n):
    """Un risultato finto di run_filter_search_bt: la baseline e n filtri."""
    return SimpleNamespace(risultati=pd.DataFrame({"filtro": [vt.BASELINE] + [f"F{i}" for i in range(n)]}))


def sistemi(n):
    """Un risultato finto di run_exit_search_bt: n sistemi."""
    return SimpleNamespace(risultati=pd.DataFrame({"combinazione": [f"S{i}" for i in range(n)]}))


def sezione_a():
    print("\nA · Per ogni chiave il numero piu' alto (D1)")
    p = {"trigger": 0, "uscite": {}}
    RD.metti_prova(p, "trigger", None, 66)
    RD.metti_prova(p, "trigger", None, 32)
    RD.metti_prova(p, "uscite", ("k",), 3)
    RD.metti_prova(p, "uscite", ("k",), 1)
    RD.metti_prova(p, "uscite", ("j",), 2)
    check("A1. in memoria un numero piu' basso non abbassa il conto (voce semplice e a chiave)",
          p == {"trigger": 66, "uscite": {("k",): 3, ("j",): 2}})
    RD.metti_prova(p, "trigger", None, 71)
    check("A2. un numero piu' alto lo alza", p["trigger"] == 71)
    voci = [{"voce": "prova", "dove": "trigger", "chiave": None, "n": 66},
            {"voce": "prova", "dove": "trigger", "chiave": None, "n": 32},
            {"voce": "prova", "dove": "celle", "chiave": [25, ["a", "b"], ["E1"]], "n": 182},
            {"voce": "prova", "dove": "celle", "chiave": [25, ["a", "b"], ["E1"]], "n": 150},
            {"voce": "prova", "dove": "filtri", "chiave": ["X"], "n": 3}]
    s = RD.da_voci(("S", "M15", "t"), voci)
    check("A3. rilettura dei giornali: per ogni chiave il piu' alto, in qualunque ordine",
          s.prove["trigger"] == 66 and s.prove["celle"] == {(25, ("a", "b"), ("E1",)): 182}
          and RD.da_voci(("S", "M15", "t"), voci[::-1]).prove == s.prove)
    crescenti = [{"voce": "prova", "dove": "trigger", "chiave": None, "n": n} for n in (12, 14)]
    check("A4. con numeri che crescono, come prima (vale anche l'ultimo)",
          RD.da_voci(("S", "M15", "t"), crescenti).prove["trigger"] == 14)


def sezione_b():
    print("\nB · Le stesse chiavi del Lab")
    atl = tabella(assi=("vol_trend", "sessione"), k_misurate=182)
    nomi = ["E1", "E2", "E3"]
    p = {"trigger": 0, "uscite": {}, "filtri": {}, "combinazioni": {}}
    storia = SimpleNamespace(prove=p)
    vt.conta_celle(storia, 25, atl, nomi)
    check("B1. celle: la chiave del Lab (H, assi, trigger nell'ordine dell'atlante)",
          p["celle"] == {(25, ("vol_trend", "sessione"), ("E1", "E2", "E3")): 182})
    # una sessione del Lab dopo la 4 (imposta_uscite) e la 4b: stesse impostazioni della ricerca
    lab = SimpleNamespace(trigger_long=("E1", "E2"), trigger_short=(), cella_long="EUROPA", cella_short=None,
                          uscite=vt.impostazioni_uscite(25, 25, 90, 0, None), sistema=None)
    vt.conta_uscite(storia, sistemi(1), ["E1", "E2"], [], 25, 90.0, 0.0, None, "EUROPA", None)
    check("B2. uscite (2.2): la chiave della 4 del Lab", list(p["uscite"]) == [vt._chiave_uscite(lab)],
          str(list(p["uscite"])))
    vt.conta_filtri(storia, ricerca(38), ["E1", "E2"], [], 25, 90.0, 0.0, None, None)
    check("B3. filtri (3.1): la chiave della 5 del Lab, senza la baseline",
          p["filtri"] == {vt._chiave_filtri(lab): 38})
    lab2 = SimpleNamespace(trigger_long=("E1",), trigger_short=("E9",), cella_long=None, cella_short=None,
                           uscite=vt.impostazioni_uscite(25, 25, (90, 80), (0, 0), "A | B"), sistema="Solo long")
    vt.conta_uscite(storia, sistemi(3), ["E1"], ["E9"], 25, (90.0, 80.0), (0.0, 0.0), "A | B")
    vt.conta_filtri(storia, ricerca(5), ["E1"], ["E9"], 25, (90.0, 80.0), (0.0, 0.0), "A | B", "Solo long")
    check("B4. uscite per lato, regola in coppia e sistema della 4b: le chiavi del Lab",
          vt._chiave_uscite(lab2) in p["uscite"] and p["filtri"].get(vt._chiave_filtri(lab2)) == 5)
    vt.conta_uscite(storia, sistemi(30), ["E1", "E2"], [], 25, 90.0, 0.0, ["X1", "X2"], "EUROPA", None)
    k23 = [k for k in p["uscite"] if k[6] == str(("X1", "X2"))]
    check("B5. la 2.3 (tutte le regole, D2): una chiave a parte, con l'elenco delle regole",
          len(k23) == 1 and p["uscite"][k23[0]] == 30 and len(p["uscite"]) == 3)
    vt.conta_filtri(storia, ricerca(3), ["E1", "E2"], [], 25, 90.0, 0.0, None, None,
                    confidenza=([0.0, 0.5, 0.8], "F22"))
    kc = (*vt._chiave_filtri(lab), ("confidenza", (0.0, 0.5, 0.8), "F22"))
    check("B6. la 3.3 (confidenza, D2): una chiave a parte", p["filtri"].get(kc) == 3 and len(p["filtri"]) == 3)
    prima = json.dumps(RD.normale(p), sort_keys=True)
    rim = ricerca(1)
    rim.rimisura = True
    vt.conta_filtri(storia, rim, ["E1"], [], 25, 90.0, 0.0, None, None)
    check("B7. strada B (la cella riprovata): niente, e' gia' fra le celle", json.dumps(RD.normale(p), sort_keys=True)
          == prima)
    vt.conta_fasce(storia, pd.DataFrame(index=pd.date_range("2024-01-01", periods=10, freq="15min", tz="UTC")),
                   "BINANCE_PERP_BTCUSDT", ["E1", "E2"])
    check("B8. fasce: niente senza un trigger a orario", "fasce" not in p)
    vt.conta_fasce(storia, pd.DataFrame(index=pd.date_range("2024-01-01", periods=10, freq="15min", tz="UTC")),
                   "BINANCE_PERP_BTCUSDT", ["E1", "ORA_LONG_@05:45"])
    idx = pd.date_range("2024-01-01", periods=10, freq="15min", tz="UTC")
    attese = vt.n_fasce(vt.fasce_orarie(idx, vt.fuso_profilo("BINANCE_PERP_BTCUSDT"))[1])
    check("B9. fasce: con un trigger a orario, le fasce del profilo come la 3b del Lab",
          p.get("fasce") == attese and attese > 0, f"{attese} fasce")


def sezione_c(radice: Path):
    print("\nC · Lo studio: solo le voci cambiate, nessun doppio conto")
    cg = radice / "c"
    cg.mkdir()
    df = storico()
    i = ST.entra(cg, "BINANCE_PERP_BTCUSDT", "H1", df, "pc", adesso="2026-10-28 09:00")
    dati = SimpleNamespace(ingresso=i, cartella=cg, symbol="BINANCE_PERP_BTCUSDT", timeframe="H1", macchina="pc")
    RD.azzera()
    storia = muto(vt.registro_orizzonte, "BINANCE_PERP_BTCUSDT", "H1", i.df_is, 25, dati=dati)
    giornale = cg / "studio" / i.dataset / "giornale_pc.jsonl"

    def righe():
        return giornale.read_text(encoding="utf-8").splitlines()

    def giro():
        vt.conta_trigger(storia, SimpleNamespace(sintesi=pd.DataFrame(index=range(71))))
        vt.conta_celle(storia, 25, tabella(assi=("vol_trend", "sessione"), k_misurate=500), ["E1", "E2"])
        vt.conta_uscite(storia, sistemi(3), ["E1"], ["E2"], 25, 90.0, 0.0)
        vt.conta_filtri(storia, ricerca(38), ["E1"], ["E2"], 25, 90.0, 0.0)

    n0 = len(righe())
    giro()
    n1 = len(righe())
    check("C1. la ricerca scrive le sue voci nel giornale della macchina", n1 - n0 == 4, f"{n1 - n0} voci")
    voce = json.loads(righe()[-1])
    check("C1b. sono voci «prova» dello studio, con macchina e id dello studio",
          voce["voce"] == "prova" and voce["macchina"] == "pc" and voce["studio"] == i.studio["id"])
    conto = json.dumps(RD.normale(storia.prove), sort_keys=True)
    giro()
    check("C2. la stessa ricerca due volte: nessuna voce nuova, stesso conto",
          len(righe()) == n1 and json.dumps(RD.normale(storia.prove), sort_keys=True) == conto)
    # il Lab sulle stesse chiavi, con il suo codice (metti_prova + _salva_studio)
    lab = SimpleNamespace(trigger_long=("E1",), trigger_short=("E2",), cella_long=None, cella_short=None,
                          uscite=vt.impostazioni_uscite(25, 25, 90, 0, None), sistema=None)
    RD.metti_prova(storia.prove, "trigger", None, 71)
    RD.metti_prova(storia.prove, "uscite", vt._chiave_uscite(lab), 3)
    RD.metti_prova(storia.prove, "filtri", vt._chiave_filtri(lab), 38)
    vt._salva_studio(storia)
    check("C3. il Lab sulle stesse chiavi della ricerca: nessuna voce nuova, stesso conto",
          len(righe()) == n1 and json.dumps(RD.normale(storia.prove), sort_keys=True) == conto)
    RD.metti_prova(storia.prove, "trigger", None, 32)
    vt._salva_studio(storia)
    vt.conta_trigger(storia, SimpleNamespace(sintesi=pd.DataFrame(index=range(30))))
    check("C4. un numero piu' basso (Lab o ricerca) non scrive e non abbassa",
          len(righe()) == n1 and storia.prove["trigger"] == 71)
    RD.azzera()
    rilett, _ = ST.ricostruisci(cg, i.dataset, i.studio)
    check("C5. riavvio simulato: lo stesso conto dai giornali",
          json.dumps(RD.normale(rilett.prove), sort_keys=True) == conto)
    sl = vt.soglia_cumulata_studio(rilett, t=2.5)
    sessione = SimpleNamespace(prove=rilett.prove, storia=rilett, fs=None)
    sb = vt._soglia_cumulata_lab(sessione, 2.5)
    check("C6. la soglia della ricerca e' quella del Lab sullo stesso conto",
          sl["k"] == sb["k"] == 71 + 500 + 3 + 38 and sl["soglia"] == sb["soglia"], f"k = {sl['k']}")
    # una voce di A3: la prova vista prima, con la data in cui e' stata vista
    ST.aggiungi_voce(cg, i.dataset, "pc", i.studio["id"],
                     {"voce": "prova", "dove": "trigger", "chiave": None, "n": 80, "visto_il": "2026-10-25T10:00:00+00:00"})
    RD.azzera()
    r3, _ = ST.ricostruisci(cg, i.dataset, i.studio)
    check("C7. una voce con «visto il» (A3) si rilegge e conta", r3.prove["trigger"] == 80)
    RD.azzera()
    st_mem = muto(vt.registro_orizzonte, "BINANCE_PERP_BTCUSDT", "H1", i.df_is, 25)
    vt.conta_trigger(st_mem, SimpleNamespace(sintesi=pd.DataFrame(index=range(5))))
    check("C8. senza studio (broker, confine 80%): il conto resta in memoria, nessun file",
          st_mem.prove["trigger"] == 5 and len(righe()) == n1 + 1)
    vt.conta_trigger(None, SimpleNamespace(sintesi=pd.DataFrame(index=range(5))))
    check("C9. senza registro (None): nessun errore", True)


def sezione_d():
    print("\nD · Lo spot: gli stessi trigger del Lab (A2)")
    import entry_long
    import entry_short
    from entry_metro import registra_trigger_metro
    muto(registra_trigger_metro)
    muto(entry_long.registra_trigger_long)
    muto(entry_short.registra_trigger_short)
    spot, perp = vt.trigger_candidati("BYBIT_SPOT_ETHUSDT"), vt.trigger_candidati("BINANCE_PERP_BTCUSDT")
    from engine import registry as reg
    check("D1. spot: solo i long, gli stessi del Lab e nello stesso ordine",
          spot == vt._trigger_candidati(1) and all(reg.get_entry_direction(n) == 1 for n in spot) and spot,
          f"{len(spot)} trigger")
    check("D2. perpetual: tutti, gli stessi del Lab", perp == vt._trigger_candidati(None) and len(perp) > len(spot),
          f"{len(perp)} trigger")
    from entry_metro import NOMI_METRO
    vecchi = [n for n in reg.list_entries() if n not in NOMI_METRO]
    check("D3. perpetual: lo stesso elenco di prima (a registro appena caricato)", perp == vecchi)


def sezione_e(radice: Path):
    print("\nE · Le situazioni gia' misurate (docs/77, D2)")
    vecchia = (25, ("vol_trend", "sessione", "basis"), ("E1", "E2"))
    nuova = (25, ("vol_trend", "sessione"), ("E1", "E2"))
    p = {"celle": {vecchia: 558}}
    entrata = RD.metti_prova(p, "celle", nuova, 450)
    check("E1. stesso H, stessi trigger, assi contenuti in una voce contata: non entra, il conto resta 558",
          entrata is False and p["celle"] == {vecchia: 558} and RD.celle_gia_contate(p["celle"], nuova) == vecchia)
    altre = [(16, ("vol_trend", "sessione"), ("E1", "E2")),           # un H nuovo
             (25, ("vol_trend", "sessione"), ("E1", "E2", "E3")),     # un trigger in piu'
             (25, ("vol_trend", "sessione"), ("E2", "E1"))]           # gli stessi trigger in un altro ordine
    entrate = [RD.metti_prova(p, "celle", k, 400) for k in altre]
    check("E2. con un H nuovo, un trigger in piu' o un altro ordine dei trigger: si conta come sempre",
          entrate == [True, True, True] and all(p["celle"][k] == 400 for k in altre) and p["celle"][vecchia] == 558)
    check("E3. le altre voci non cambiano regola: uscite e filtri con chiavi che si somigliano contano come prima",
          RD.metti_prova(p, "uscite", (25, ("a",), ("E1",)), 3) is True
          and RD.metti_prova(p, "uscite", (25, ("a", "b"), ("E1",)), 4) is True and len(p["uscite"]) == 2)
    # nello studio: la voce con la basis gia' nel giornale (come su BTC e XRP), poi l'atlante senza la basis
    cg = radice / "e"
    cg.mkdir()
    i = ST.entra(cg, "BINANCE_PERP_XRPUSDT", "H1", storico(seme=9), "pc", adesso="2026-10-29 09:00")
    dati = SimpleNamespace(ingresso=i, cartella=cg, symbol="BINANCE_PERP_XRPUSDT", timeframe="H1", macchina="pc")
    RD.azzera()
    ST.aggiungi_voce(cg, i.dataset, "pc", i.studio["id"],
                     {"voce": "prova", "dove": "celle", "chiave": RD.normale(list(vecchia)), "n": 541})
    storia = muto(vt.registro_orizzonte, "BINANCE_PERP_XRPUSDT", "H1", i.df_is, 25, dati=dati)
    giornale = cg / "studio" / i.dataset / "giornale_pc.jsonl"
    n0 = len(giornale.read_text(encoding="utf-8").splitlines())
    vt.conta_celle(storia, 25, tabella(assi=("vol_trend", "sessione"), k_misurate=430), ["E1", "E2"])
    n1 = len(giornale.read_text(encoding="utf-8").splitlines())
    RD.azzera()
    rilett, _ = ST.ricostruisci(cg, i.dataset, i.studio)
    check("E4. nello studio: l'atlante senza la basis (ricerca o Lab, stessa funzione) non scrive voci e il conto "
          "delle situazioni resta quello di prima, anche dopo il riavvio",
          n1 == n0 and storia.prove["celle"] == {vecchia: 541} and rilett.prove["celle"] == {vecchia: 541}
          and vt.soglia_cumulata_studio(rilett)["celle"] == 541)
    vt.conta_celle(storia, 16, tabella(assi=("vol_trend", "sessione"), k_misurate=430), ["E1", "E2"])
    check("E5. nello studio, con un H nuovo: la voce si scrive e si conta",
          len(giornale.read_text(encoding="utf-8").splitlines()) == n1 + 1
          and storia.prove["celle"][(16, ("vol_trend", "sessione"), ("E1", "E2"))] == 430)


def esegui() -> int:
    print("=" * 70)
    print("test_conto_ricerca · il conto del notebook di ricerca nello studio (docs/76)")
    print("=" * 70)
    radice = Path(tempfile.mkdtemp(prefix="conto_ricerca_"))
    try:
        sezione_a()
        sezione_b()
        sezione_c(radice)
        sezione_d()
        sezione_e(radice)
    finally:
        RD.azzera()
        shutil.rmtree(radice, ignore_errors=True)
    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
