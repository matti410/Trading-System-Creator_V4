"""
Suite di validazione degli ORIZZONTI MULTIPLI (29/10/2026, docs/77, lavoro 2):
la griglia di 1, 4 e 8 ore in engine/vetrina.py (orizzonti_in_barre,
leggi_orizzonte, rosa_orizzonti, tabella_orizzonti, prepara, esplora, la
ricerca) e in engine/registro_dataset.py (apri_griglia, scegli_h).

Cosa verifica
-------------
A  ore -> barre su M5, M15, M30, H1 e H4 (1 ora su H4 si salta); il campo
   dell'orizzonte: la griglia, un numero di barre, «4 ore»; gli errori;
B  il registro: la griglia entra tutta fra gli H provati (anche dopo H gia'
   provati), una seconda volta non aggiunge niente, l'H scelto diventa quello
   corrente, la voce dei trigger e' prove_trigger_orizzonti sugli H provati,
   la rilettura dei giornali ritrova gli stessi H;
C  il Lab con la griglia, su un mercato inventato: la schermata 1 non sceglie,
   la 2c mostra la rosa ai tre H (uguale a tre rose a un H), le schermate dopo
   si fermano finche' l'H non e' scelto; scelto l'H, event study, rosa, atlante
   (chiave con quell'H) e uscite consigliate lavorano a quell'H;
D  un orizzonte solo in barre: tutto come prima (la griglia non c'e', il campo
   della 2c non conta);
E  lo studio: la griglia e la scelta nel giornale, ritrovate dopo il riavvio;
F  la ricerca: orizzonti_della_ricerca, la 1.3 che si ferma senza H_SCELTO,
   registro_orizzonte con la griglia e con un orizzonte solo.

Come si lancia (da terminale, dalla cartella del progetto):

    python test_orizzonti.py

Non serve la rete ne' i dati veri. Alla fine stampa «RISULTATO: N/N test superati».
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")

import engine.exchange as X
from engine import registro_dataset as RD
from engine import studio as ST
from engine import vetrina as vt
from engine.event_study import run_event_study
from engine.giudizio import prove_trigger_orizzonti
from engine.quarantena import imposta_rollover
from engine.rosa import rosa_entry
from test_atlante import Mercato, _indice

ESITI: list[bool] = []
SYM = "BINANCE_PERP_BTCUSDT"


def check(nome, condizione, dettaglio=""):
    ESITI.append(bool(condizione))
    print(f"  [{'OK' if condizione else 'FALLITO'}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""))


def muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        out = f(*a, **k)
    import matplotlib.pyplot as plt
    plt.close("all")
    return out


def errore(f, testo):
    try:
        muto(f)
    except (ValueError, RuntimeError) as e:
        return testo in str(e)
    return False


def scrivi_dataset(cartella, giorni=200, seme=3):
    df = Mercato(_indice("2022-01-03", giorni=giorni), seme=seme).df()
    X.salva_csv(df, os.path.join(str(cartella), f"{SYM}_M15.csv"))
    orari = pd.date_range(df.index[0].floor("8h"), df.index[-1].ceil("8h"), freq="8h")
    X.salva_funding(X.con_intervalli(pd.DataFrame({"tasso": 0.0001}, index=orari)), X.file_funding(SYM, cartella))
    return df


def sezione_a():
    print("\nA · Ore e barre, il campo dell'orizzonte")
    attese = {"M5": [12, 48, 96], "M15": [4, 16, 32], "M30": [2, 8, 16], "H1": [1, 4, 8], "H4": [1, 2]}
    trovate = {tf: vt.orizzonti_in_barre(tf)[0] for tf in attese}
    check("A1. 1, 4 e 8 ore in barre: M5 12/48/96, M15 4/16/32, M30 2/8/16, H1 1/4/8; su H4 l'ora si salta",
          trovate == attese and vt.orizzonti_in_barre("H4")[1] == [1] and vt.ORIZZONTI_ORE == (1, 4, 8), str(trovate))
    check("A2. il campo: la griglia -> i tre H; un numero (anche come testo) -> quel numero; «4 ore», «1 ora»",
          vt.leggi_orizzonte(vt.GRIGLIA, "M15") == [4, 16, 32] and vt.leggi_orizzonte(41, "M15") == [41]
          and vt.leggi_orizzonte("41", "M15") == [41] and vt.leggi_orizzonte("4 ore", "M15") == [16]
          and vt.leggi_orizzonte("1 ora", "M5") == [12] and vt.leggi_orizzonte("1, 4 e 8 ore", "H1") == [1, 4, 8])
    check("A3. si ferma con un testo che non è un orizzonte, con 0 barre, con 1 ora su H4",
          errore(lambda: vt.leggi_orizzonte("tanto", "M15"), "Orizzonte")
          and errore(lambda: vt.leggi_orizzonte(0, "M15"), "almeno 1")
          and errore(lambda: vt.leggi_orizzonte("1 ora", "H4"), "Orizzonte"))


def sezione_b():
    print("\nB · Il registro: la griglia fra gli H provati")
    RD.azzera()
    s, esito, nuovi = RD.apri_griglia("X", "M15", "2025-01-01", [4, 16, 32], nuove_prove=RD._prove_vuote)
    check("B1. dataset nuovo: i tre H fra gli H provati, l'H corrente provvisorio e' il piu' lungo, nessuna risalita",
          esito == "nuovo" and nuovi == [4, 16, 32] and s.h_provati == [4, 16, 32] and s.h_corrente == 32
          and s.risalite == [])
    s2, esito2, nuovi2 = RD.apri_griglia("X", "M15", "2025-01-01", [4, 16, 32])
    check("B2. la stessa griglia una seconda volta: niente di nuovo", esito2 == "stesso_h" and nuovi2 == [] and s2 is s)
    t, esito_t = RD.apri("Y", "M15", "2025-01-01", 41, nuove_prove=RD._prove_vuote)
    RD.apri("Y", "M15", "2025-01-01", 25)
    t2, esito_g, nuovi_g = RD.apri_griglia("Y", "M15", "2025-01-01", [4, 16, 32])
    check("B3. su un dataset con H 41 e 25 gia' provati la griglia si aggiunge: 41, 25, 4, 16, 32",
          esito_g == "griglia" and t2.h_provati == [41, 25, 4, 16, 32] and nuovi_g == [4, 16, 32])
    cambia, di_nuovo = RD.scegli_h(s, 16), RD.scegli_h(s, 16)
    check("B4. l'H scelto diventa quello corrente (una volta sola); un H fuori dalla griglia si ferma",
          cambia and not di_nuovo and s.h_corrente == 16 and s.h_provati == [4, 16, 32]
          and errore(lambda: RD.scegli_h(s, 25), "non e' fra gli orizzonti"))
    check("B5. la voce dei trigger: prove_trigger_orizzonti sui tre H (71 trigger ≈ 203 prove); con 41 e 25 "
          "gia' provati, sui cinque",
          s.voce_trigger(71) == prove_trigger_orizzonti(71, [4, 16, 32])
          and t2.voce_trigger(71) == prove_trigger_orizzonti(71, [4, 16, 25, 32, 41])
          and 195 < s.voce_trigger(71) < 210, f"{s.voce_trigger(71):.1f} e {t2.voce_trigger(71):.1f}")
    voci = [{"voce": "orizzonte", "H": h} for h in (4, 16, 32, 16)]
    r = RD.da_voci(("Z", "M15", "t"), voci)
    check("B6. rilettura dei giornali (4, 16, 32, poi la scelta 16): stessi H provati, H corrente 16",
          r.h_provati == [4, 16, 32] and r.h_corrente == 16)
    RD.azzera()


def sezione_c_d(radice: Path):
    print("\nC · Il Lab con la griglia (mercato inventato)")
    cg = radice / "lab"
    cg.mkdir()
    scrivi_dataset(cg)
    RD.azzera()
    s = muto(vt.prepara, SYM, H=vt.GRIGLIA, cartella=str(cg))
    rie = s.tabelle["riepilogo"].set_index("")[" "]
    check("C1. schermata 1 con la griglia: H provvisorio 32 (il piu' lungo), niente scelto, i tre H gia' fra gli "
          "H provati; il riepilogo dice che si sceglie alla 2c",
          s.griglia == [4, 16, 32] and s.H == 32 and s.h_scelto is None and s.storia.h_provati == [4, 16, 32]
          and "lo scegli alla 2c" in rie["Orizzonte di osservazione"], rie["Orizzonte di osservazione"])
    muto(vt.esplora, s)
    nomi = vt._trigger_candidati(None)
    diretta = rosa_entry(s.df_is, 4, s.pip, nomi=nomi, min_eventi=vt.MIN_TRIGGER, fuso=s.fuso, atr=s.atr,
                         unita=s.unita)
    tab = s.tabelle["orizzonti"]
    check("C2. la 2c con la griglia: la rosa ai tre H, uguale a una rosa a un H; la tabella ha un gruppo di "
          "colonne per H",
          sorted(s.rose) == [4, 16, 32] and s.rose[4].equals(diretta)
          and all(f"Solidità netta a {o}" in tab.columns for o in ("1 ora", "4 ore", "8 ore")) and len(tab) > 0)
    k_trigger = s.prove["trigger"]
    check("C3. la riga delle prove: i trigger misurati con i tre orizzonti, la voce che conta la scelta",
          "a 3 orizzonti" in s.tabelle["riga_prove"]
          and f"{vt._fmt(prove_trigger_orizzonti(k_trigger, [4, 16, 32]), 1)} trigger" in s.tabelle["riga_prove"]
          and vt._soglia_cumulata_lab(s, np.nan)["voce_trigger"] == prove_trigger_orizzonti(k_trigger, [4, 16, 32])
          and "(H = 4, 16, 32)" in vt._soglia_cumulata_lab(s, np.nan)["frase"],
          s.tabelle["riga_prove"][:150])
    check("C4. senza l'H scelto le schermate dopo la 2c si fermano (3a, 3b, casistiche a mano)",
          errore(lambda: vt.rosa_dei_trigger(s), "scegli l'orizzonte alla 2c")
          and errore(lambda: vt.scegli_casistiche(s), "scegli l'orizzonte alla 2c")
          and errore(lambda: vt.scegli_trigger(s, long=nomi[0]), "scegli l'orizzonte alla 2c"))
    check("C5. un orizzonte fuori dalla griglia si ferma",
          errore(lambda: vt.esplora(s, orizzonte="2 ore"), "scegli uno della griglia"))
    rosa16 = s.rose[16]
    muto(vt.esplora, s, orizzonte="4 ore")
    ev16 = run_event_study(s.df_is, entry_names=nomi, horizon=16, min_trades=vt.MIN_TRIGGER, pip=s.pip,
                           verbose=False)
    check("C6. scelto «4 ore»: H = 16 per la sessione e per il dataset (corrente), nessun H in piu'; l'event study "
          "e la rosa sono quelli a 16 barre",
          s.H == 16 and s.h_scelto == 16 and s.storia.h_corrente == 16 and s.storia.h_provati == [4, 16, 32]
          and s.ev.sintesi.equals(ev16.sintesi) and s.rosa_trigger is rosa16)
    r3a = muto(vt.rosa_dei_trigger, s)
    lungo = r3a[r3a["direction"] == 1].sort_values("t_netto", ascending=False)["candidato"].iloc[0]
    muto(vt.scegli_trigger, s, long=lungo)
    atl = muto(vt.atlante_dei_trigger, s)
    chiavi = list(s.prove.get("celle", {}))
    muto(vt.imposta_uscite, s)
    check("C7. dopo la scelta la 3a gira all'H scelto; l'atlante ha la chiave con H = 16; le uscite consigliate "
          "durano 16 barre",
          r3a.attrs["H"] == 16 and atl.attrs["H"] == 16 and chiavi and all(k[0] == 16 for k in chiavi)
          and s.uscite["n_barre_long"] == 16 and s.uscite["n_barre_short"] == 16)

    print("\nD · Un orizzonte solo in barre: come prima")
    RD.azzera()
    s1 = muto(vt.prepara, SYM, H=41, cartella=str(cg))
    s1s = muto(vt.prepara, SYM, H="41", cartella=str(cg))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        vt.esplora(s1, orizzonte="4 ore")
    import matplotlib.pyplot as plt
    plt.close("all")
    check("D1. H = 41 (anche scritto come testo): niente griglia, H scelto = 41, un H solo fra gli H provati; il "
          "campo della 2c non conta e lo dice",
          s1.griglia is None and s1.h_scelto == 41 and s1.H == 41 and s1s.H == 41
          and s1.storia.h_provati == [41] and "conta solo con" in out.getvalue())
    ev41 = run_event_study(s1.df_is, entry_names=nomi, horizon=41, min_trades=vt.MIN_TRIGGER, pip=s1.pip,
                           verbose=False)
    check("D2. con un orizzonte solo, la 2c e' quella di prima: event study e rosa a 41 barre, nessuna tabella dei "
          "tre orizzonti",
          s1.ev.sintesi.equals(ev41.sintesi) and s1.rosa_trigger.attrs["H"] == 41 and "orizzonti" not in s1.tabelle
          and "orizzonti provati" not in s1.tabelle["riga_prove"])
    RD.azzera()


def sezione_e(radice: Path):
    print("\nE · Lo studio: la griglia e la scelta nel giornale")
    cg = radice / "studio"
    cg.mkdir()
    scrivi_dataset(cg)
    RD.azzera()
    s = muto(vt.prepara, SYM, H=vt.GRIGLIA, cartella=str(cg), confine="studio", macchina="pc")
    giornale = cg / "studio" / f"{SYM}_M15" / "giornale_pc.jsonl"
    voci = [json.loads(r) for r in giornale.read_text(encoding="utf-8").splitlines()]
    orizzonti = [v["H"] for v in voci if v["voce"] == "orizzonte"]
    check("E1. la griglia nello studio: tre voci «orizzonte» (4, 16, 32), nessuna prova", orizzonti == [4, 16, 32]
          and not [v for v in voci if v["voce"] == "prova"], str(orizzonti))
    vt._scegli_orizzonte(s, "1 ora")
    vt._scegli_orizzonte(s, "1 ora")
    orizzonti2 = [json.loads(r)["H"] for r in giornale.read_text(encoding="utf-8").splitlines()
                  if json.loads(r)["voce"] == "orizzonte"]
    RD.azzera()
    r, _ = ST.ricostruisci(cg, f"{SYM}_M15", ST.leggi_confine(cg))
    check("E2. la scelta (1 ora = 4 barre) scrive una voce sola; dopo il riavvio: H provati 4, 16, 32, H corrente 4",
          orizzonti2 == [4, 16, 32, 4] and r.h_provati == [4, 16, 32] and r.h_corrente == 4)
    RD.azzera()
    s2 = muto(vt.prepara, SYM, H=vt.GRIGLIA, cartella=str(cg), confine="studio", macchina="pc")
    righe = len(giornale.read_text(encoding="utf-8").splitlines())
    check("E3. la griglia una seconda volta sullo stesso dataset: nessuna voce nuova, stessi H provati",
          righe == 4 and s2.storia.h_provati == [4, 16, 32])
    RD.azzera()


def sezione_f(radice: Path):
    print("\nF · La ricerca")
    check("F1. orizzonti_della_ricerca: la griglia senza scelta -> l'H piu' lungo; con H_SCELTO (barre o «4 ore») "
          "-> quello; un numero -> un orizzonte solo",
          vt.orizzonti_della_ricerca(vt.GRIGLIA, "M15") == ([4, 16, 32], 32)
          and vt.orizzonti_della_ricerca(vt.GRIGLIA, "M15", 16) == ([4, 16, 32], 16)
          and vt.orizzonti_della_ricerca(vt.GRIGLIA, "M15", "8 ore") == ([4, 16, 32], 32)
          and vt.orizzonti_della_ricerca(25, "M15") == ([25], 25)
          and errore(lambda: vt.orizzonti_della_ricerca(vt.GRIGLIA, "M15", 25), "scegli uno"))
    check("F2. la 1.3 con la griglia si ferma senza H_SCELTO; con H_SCELTO, o con un orizzonte solo, no",
          errore(lambda: vt.ferma_senza_orizzonte([4, 16, 32], None, "M15"), "scrivi H_SCELTO")
          and vt.ferma_senza_orizzonte([4, 16, 32], 16, "M15") is None and vt.ferma_senza_orizzonte([25], None, "M15") is None)
    df = Mercato(_indice("2022-01-03", giorni=30), seme=4).df()
    RD.azzera()
    st1 = muto(vt.registro_orizzonte, SYM, "M15", df, 32, orizzonti=[4, 16, 32])
    st2 = muto(vt.registro_orizzonte, SYM, "M15", df, 16, orizzonti=[4, 16, 32], scelto=16)
    RD.azzera()
    st3 = muto(vt.registro_orizzonte, SYM, "M15", df, 25, orizzonti=[25])
    check("F3. registro_orizzonte: la griglia fra gli H provati, poi l'H scelto corrente; un orizzonte solo come "
          "prima",
          st1.h_provati == [4, 16, 32] and st2 is st1 and st2.h_corrente == 16 and st3.h_provati == [25]
          and st3.h_corrente == 25)
    RD.azzera()


def esegui() -> int:
    print("=" * 70)
    print("test_orizzonti · gli orizzonti 1, 4 e 8 ore (docs/77, lavoro 2)")
    print("=" * 70)
    imposta_rollover(None)
    radice = Path(tempfile.mkdtemp(prefix="orizzonti_"))
    try:
        sezione_a()
        sezione_b()
        sezione_c_d(radice)
        sezione_e(radice)
        sezione_f(radice)
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
