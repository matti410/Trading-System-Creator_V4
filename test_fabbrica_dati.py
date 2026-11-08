"""
Suite di collaudo di dati e config della fabbrica (docs/82 P1, P2 e §6, lavoro L3a).

Si lancia da terminale, dalla cartella del progetto:

    python test_fabbrica_dati.py

Solo dati sintetici (engine/fabbrica/sintetici.py), scritti in una cartella temporanea: non servono i file in dati/,
MetaTrader 5 o internet. Stampa una riga per collaudo e alla fine «RISULTATO: n/n test superati».
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import time
import warnings

import numpy as np
import pandas as pd

from engine.fabbrica import sintetici
from engine.fabbrica.config import (CAMPI, budget_massimo, cartella_asset, config_standard, controlla_budget,
                                    controlla_config, impronta_config, leggi_config, salva_config)
from engine.fabbrica.dati import (Confini, PermessoCassaforte, Pezzi, carica_pezzi, controlla_cassaforte_nuova,
                                  impronta_pezzo)
from engine.vetrina import carica_storico, costi_storico

warnings.simplefilter("ignore")

PERP, SPOT = "BINANCE_PERP_BTCUSDT", "BYBIT_SPOT_ETHUSDT"
STANDARD = {"inizio": "2020-01-02 00:00", "ricerca_ore": 30624, "selezione_ore": 17177.75, "cassaforte_ore": 11779.5}
PICCOLI = {"inizio": "2024-01-01 00:00", "ricerca_ore": 300.25, "selezione_ore": 200.5, "cassaforte_ore": 90.75}
T = pd.Timestamp


def _utc(testo: str) -> pd.Timestamp:
    return pd.Timestamp(testo, tz="UTC")


def _dataframe_dentro(oggetto, visti=None):
    """Tutti i DataFrame raggiungibili dagli attributi di un oggetto (per cercare barre della cassaforte)."""
    visti = set() if visti is None else visti
    if id(oggetto) in visti:
        return []
    visti.add(id(oggetto))
    if isinstance(oggetto, pd.DataFrame):
        return [oggetto]
    figli = []
    if isinstance(oggetto, dict):
        figli = list(oggetto.values())
    elif isinstance(oggetto, (list, tuple)):
        figli = list(oggetto)
    elif hasattr(oggetto, "__dict__") and not isinstance(oggetto, (pd.Series, pd.Index, np.ndarray, type)):
        figli = list(vars(oggetto).values())
    out = []
    for f in figli:
        out.extend(_dataframe_dentro(f, visti))
    return out


def esegui() -> int:
    ESITI = []
    t0 = time.perf_counter()

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        print(f"[{'OK ' if condizione else 'KO '}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""), flush=True)

    def errore(f, tipi=(ValueError, KeyError, FileNotFoundError, PermissionError)) -> bool:
        try:
            f()
        except tipi:
            return True
        return False

    base = tempfile.mkdtemp()
    try:
        # ------------------------------------------------------------------ i confini
        print("I confini come durate (docs/82 P1 e §6)")
        conf = Confini.da_config(STANDARD)
        lim = conf.limiti()
        check("1. la prima finestra: ricerca fino al 01/07/2023, selezione fino al 15/06/2025 17:45, cassaforte fino al "
              "19/10/2026 13:15 (esclusi)", lim["ricerca"] == (_utc("2020-01-02"), _utc("2023-07-01"))
              and lim["selezione"] == (_utc("2023-07-01"), _utc("2025-06-15 17:45"))
              and lim["cassaforte"] == (_utc("2025-06-15 17:45"), _utc("2026-10-19 13:15")))
        check("2. confini sbagliati: errore", errore(lambda: Confini.da_config({**STANDARD, "ricerca_ore": 0}))
              and errore(lambda: Confini.da_config({**STANDARD, "cassaforte_ore": -1}))
              and errore(lambda: Confini.da_config({**STANDARD, "inizio": "ieri"}))
              and errore(lambda: Confini.da_config({k: v for k, v in STANDARD.items() if k != "selezione_ore"}))
              and errore(lambda: Confini.da_config({**STANDARD, "fine": "2026-01-01"})))

        # ------------------------------------------------------------------ i pezzi sulla prima finestra, H1
        print("\nI pezzi della prima finestra, su barre H1 sintetiche dal 01/01/2020")
        cart = os.path.join(base, "h1")
        df_h1 = sintetici.mercato(59_700, seme=3, minuti=60, inizio="2020-01-01", prezzo=30_000)
        sintetici.scrivi_storico(cart, PERP, "H1", df_h1)
        sintetici.scrivi_funding(cart, PERP, df_h1)
        p = carica_pezzi(PERP, "H1", conf, cart)
        check("3. ricerca dalle 00:00 del 02/01/2020 alle 23:00 del 30/06/2023; selezione dal 01/07/2023 alle 17:00 del 15/06/2025",
              (p.ricerca.index[0], p.ricerca.index[-1], p.selezione.index[0], p.selezione.index[-1])
              == (_utc("2020-01-02"), _utc("2023-06-30 23:00"), _utc("2023-07-01"), _utc("2025-06-15 17:00")))
        cass = p.apri_cassaforte(PermessoCassaforte(PERP, "H1", conf.tratto_cassaforte))["df"]
        fuori_prima = (df_h1.index < lim["ricerca"][0]).sum()
        fuori_dopo = (df_h1.index >= lim["cassaforte"][1]).sum()
        unione = pd.concat([p.ricerca, p.selezione, cass])
        check("4. i pezzi non si sovrappongono e non lasciano barre fuori fra inizio e fine",
              unione.index.is_monotonic_increasing and not unione.index.duplicated().any()
              and len(unione) + fuori_prima + fuori_dopo == len(df_h1) and cass.index[0] == _utc("2025-06-15 18:00"),
              f"{len(p.ricerca)} + {len(p.selezione)} + {len(cass)} barre, {fuori_prima} prima e {fuori_dopo} dopo")
        check("5. le barre prima dell'inizio e dopo la fine restano fuori", fuori_prima == 24 and fuori_dopo > 0
              and unione.index[-1] < lim["cassaforte"][1])
        frame = _dataframe_dentro(p)
        tocca = [len(f) for f in frame if len(f) and pd.DatetimeIndex(f.index).max() >= lim["cassaforte"][0]]
        check("6. la cassaforte è sigillata: nessuna barra né tasso del funding della cassaforte resta in memoria",
              len(frame) >= 4 and not tocca, f"{len(frame)} tabelle controllate")
        check("7. il funding di ogni pezzo sta dentro il pezzo", all(
              lim[n][0] <= p.funding[n].index.min() and p.funding[n].index.max() < lim[n][1] for n in ("ricerca", "selezione")))
        check("8. senza permesso, o con il permesso di un altro tratto, la cassaforte non si apre",
              errore(lambda: p.apri_cassaforte(None)) and errore(lambda: p.apri_cassaforte("aprimi"))
              and errore(lambda: p.apri_cassaforte(PermessoCassaforte(PERP, "H1", (lim["selezione"][0], lim["selezione"][1]))))
              and errore(lambda: p.apri_cassaforte(PermessoCassaforte(PERP, "M15", conf.tratto_cassaforte))))
        uguale = cass.equals(df_h1[(df_h1.index >= lim["cassaforte"][0]) & (df_h1.index < lim["cassaforte"][1])])
        check("9. con il permesso giusto la cassaforte si rilegge dal disco, uguale al file", uguale)

        # ------------------------------------------------------------------ il veleno, in piccolo
        print("\nLa cassaforte non pesa su ricerca e selezione (il veleno completo è di L4)")
        avvelenato = df_h1.copy()
        dentro = (avvelenato.index >= lim["cassaforte"][0])
        avvelenato.loc[dentro, ["Open", "High", "Low", "Close"]] *= 1000.0
        avvelenato.loc[dentro, "Volume"] = 1e15
        cart_v = os.path.join(base, "h1_veleno")
        sintetici.scrivi_storico(cart_v, PERP, "H1", avvelenato)
        shutil.copy(os.path.join(cart, f"{PERP}_FUNDING.csv"), cart_v)
        p_v = carica_pezzi(PERP, "H1", conf, cart_v)
        costi_a = {k: v for k, v in p.costi("ricerca").items() if k != "funding"}
        costi_b = {k: v for k, v in p_v.costi("ricerca").items() if k != "funding"}
        check("10. cassaforte alterata: ricerca, selezione, impronte, funding, costi e controlli identici",
              p_v.ricerca.equals(p.ricerca) and p_v.selezione.equals(p.selezione) and p_v.impronte == p.impronte
              and p_v.funding["ricerca"].equals(p.funding["ricerca"]) and costi_a == costi_b
              and str(p_v.controlli) == str(p.controlli))

        # ------------------------------------------------------------------ le impronte
        print("\nLe impronte dei pezzi")
        copia = p.ricerca.copy()
        una_barra = copia.copy()
        una_barra.iloc[1000, una_barra.columns.get_loc("Close")] += 0.1
        un_istante = copia.copy()
        un_istante.index = un_istante.index.delete(5).insert(5, un_istante.index[5] + pd.Timedelta(minutes=1))
        check("11. impronta uguale sulla copia, diversa se cambia un prezzo o un istante",
              impronta_pezzo(copia) == p.impronte["ricerca"] and impronta_pezzo(una_barra) != p.impronte["ricerca"]
              and impronta_pezzo(un_istante) != p.impronte["ricerca"])
        p.verifica_impronte()
        p.ricerca.iloc[3, 0] = p.ricerca.iloc[3, 0] + 1.0
        check("12. un pezzo cambiato dopo la lettura: verifica_impronte si ferma", errore(p.verifica_impronte))

        # ------------------------------------------------------------------ costi
        print("\nI costi sul pezzo tagliato")
        p = carica_pezzi(PERP, "H1", conf, cart)
        atteso = costi_storico(PERP, p.ricerca, funding=p.funding["ricerca"], df_prezzo=p.ricerca)[0]
        costi = p.costi("ricerca")
        check("13. costi del pezzo = vetrina.costi_storico sul pezzo, con il funding del pezzo",
              {k: v for k, v in costi.items() if k != "funding"} == {k: v for k, v in atteso.items() if k != "funding"}
              and costi["funding"] is p.funding["ricerca"] and costi["spread"] == 0.0 and costi["commission"] > 0)
        check("14. la cassaforte non ha costi da qui", errore(lambda: p.costi("cassaforte")))

        # ------------------------------------------------------------------ timeframe, symbol, file
        print("\nTimeframe, symbol e file")
        cart_t = os.path.join(base, "tf")
        bar = {}
        for tf, minuti, n in (("M1", 1, 1700), ("M15", 15, 2400), ("D1", 1440, 40)):
            d = sintetici.mercato(n, seme=4, minuti=minuti, inizio="2024-01-01", prezzo=2_000)
            sintetici.scrivi_storico(cart_t, SPOT, tf, d)
            bar[tf] = d
        piccoli_m1 = Confini.da_config({"inizio": "2024-01-01 00:00", "ricerca_ore": 15, "selezione_ore": 8, "cassaforte_ore": 5})
        piccoli_d1 = Confini.da_config({"inizio": "2024-01-01 00:00", "ricerca_ore": 480, "selezione_ore": 240, "cassaforte_ore": 192})
        m1, d1 = carica_pezzi(SPOT, "M1", piccoli_m1, cart_t), carica_pezzi(SPOT, "D1", piccoli_d1, cart_t)
        check("15. M1 e D1 si leggono (vetrina.carica_storico li rifiuta: accetta solo da M5 a H4)",
              len(m1.ricerca) == 900 and len(d1.ricerca) == 20 and len(d1.selezione) == 10
              and errore(lambda: carica_storico(SPOT, cart_t, "M1")) and errore(lambda: carica_storico(SPOT, cart_t, "D1")))
        check("16. spot: nessun funding", m1.funding == {"ricerca": None, "selezione": None} and "funding" not in m1.costi("ricerca"))
        sintetici.scrivi_storico(cart_t, SPOT, "H1", bar["M15"])
        check("17. un file con barre di un altro timeframe: errore", errore(lambda: carica_pezzi(SPOT, "H1", piccoli_m1, cart_t)))
        check("18. symbol fuori tabella o del broker: errore", errore(lambda: carica_pezzi("BINANCE_PERP_DOGEUSDT", "M15", piccoli_m1, cart_t))
              and errore(lambda: carica_pezzi("EURUSD", "M15", piccoli_m1, cart_t)))
        check("19. file mancante o timeframe non previsto: errore", errore(lambda: carica_pezzi(SPOT, "M30", piccoli_m1, cart_t))
              and errore(lambda: carica_pezzi(SPOT, "W1", piccoli_m1, cart_t)))
        oltre = Confini.da_config({"inizio": "2024-01-01 00:00", "ricerca_ore": 15, "selezione_ore": 8, "cassaforte_ore": 50})
        prima = Confini.da_config({"inizio": "2023-12-31 00:00", "ricerca_ore": 15, "selezione_ore": 8, "cassaforte_ore": 5})
        check("20. i dati non coprono la cassaforte, o partono dopo l'inizio: errore", errore(lambda: carica_pezzi(SPOT, "M1", oltre, cart_t))
              and errore(lambda: carica_pezzi(SPOT, "M1", prima, cart_t)))
        pc = carica_pezzi(SPOT, "M15", Confini.da_config(PICCOLI), cart_t)
        check("21. confini a quarti d'ora: la barra delle 12:15 cade nel pezzo che inizia alle 12:15",
              pc.ricerca.index[-1] == _utc("2024-01-13 12:00") and pc.selezione.index[0] == _utc("2024-01-13 12:15"))

        # ------------------------------------------------------------------ il funding
        cart_f = os.path.join(base, "funding")
        d = sintetici.mercato(2400, seme=5, minuti=15, inizio="2024-01-01", prezzo=30_000)
        sintetici.scrivi_storico(cart_f, PERP, "M15", d)
        check("22. perpetual senza il file del funding: errore", errore(lambda: carica_pezzi(PERP, "M15", Confini.da_config(PICCOLI), cart_f)))
        corto = sintetici.funding_sintetico(d.iloc[:500])
        from engine.exchange import file_funding, salva_funding
        salva_funding(corto, file_funding(PERP, cart_f))
        check("23. un funding che non copre i pezzi: errore", errore(lambda: carica_pezzi(PERP, "M15", Confini.da_config(PICCOLI), cart_f)))

        # ------------------------------------------------------------------ la finestra scorrevole
        print("\nLa finestra scorrevole, con un registro finto delle cassaforti")
        registro = [conf.tratto_cassaforte]
        sposta = lambda ore: Confini.da_config({**STANDARD, "inizio": str(T("2020-01-02") + pd.Timedelta(hours=ore))})
        check("24. stessa finestra: la cassaforte è già usata, errore", errore(lambda: controlla_cassaforte_nuova(conf, registro)))
        check("25. spostata di meno della cassaforte: errore", errore(lambda: controlla_cassaforte_nuova(sposta(11_779.5 - 1), registro))
              and errore(lambda: controlla_cassaforte_nuova(sposta(24), registro)))
        controlla_cassaforte_nuova(sposta(11_779.5), registro)
        controlla_cassaforte_nuova(sposta(2 * 11_779.5), registro + [sposta(11_779.5).tratto_cassaforte])
        controlla_cassaforte_nuova(conf, [])
        check("26. spostata della cassaforte o di più, o registro vuoto: si parte", True)
        check("27. una cassaforte nuova fra due vecchie che si toccano: errore",
              errore(lambda: controlla_cassaforte_nuova(sposta(11_779.5 / 2), registro + [sposta(11_779.5).tratto_cassaforte])))

        # ------------------------------------------------------------------ la config
        print("\nLa config (docs/82 P2 e §6)")
        cfg = config_standard(PERP, "M15")
        check("28. la config standard ha i campi di §6 e passa i controlli", tuple(cfg) == CAMPI and controlla_config(cfg) is cfg
              and len(cfg["blocchi"]) == 17 and cfg["lati"] == ["long", "short"] and cfg["confini"] == STANDARD)
        rovesciata = json.loads(json.dumps(cfg, sort_keys=True))
        rovesciata = {k: rovesciata[k] for k in reversed(list(rovesciata))}
        check("29. stesso contenuto con le chiavi in altro ordine: stessa impronta", impronta_config(rovesciata) == impronta_config(cfg))
        diverse = []
        for cambia in (lambda c: c.update(seme=1), lambda c: c["blocchi"]["RSI_RIENTRO"]["soglia"].__setitem__(0, 16),
                       lambda c: c["confini"].update(ricerca_ore=30623), lambda c: c["qualita_1"].update(trade_min=101)):
            c2 = copy.deepcopy(cfg)
            cambia(c2)
            diverse.append(impronta_config(c2) != impronta_config(cfg))
        check("30. un valore cambiato (seme, una griglia, un confine, una condizione): impronta diversa", all(diverse))
        spot = config_standard(SPOT, "M15")
        check("31. spot: solo long; short nei lati: errore", spot["lati"] == ["long"]
              and errore(lambda: controlla_config({**spot, "lati": ["long", "short"]})))
        sbagliate = {
            "un campo che manca": {k: v for k, v in cfg.items() if k != "budget"},
            "un campo in più": {**cfg, "commento": "x"},
            "un sottocampo che manca": {**cfg, "qualita_1": {k: v for k, v in cfg["qualita_1"].items() if k != "peso_max"}},
            "versione": {**cfg, "versione": 2},
            "symbol fuori tabella": {**cfg, "symbol": "BINANCE_PERP_DOGEUSDT"},
            "timeframe": {**cfg, "timeframe": "M2"},
            "blocco sconosciuto": {**cfg, "blocchi": {**cfg["blocchi"], "E99": {}}},
            "parametro sconosciuto": {**cfg, "blocchi": {**cfg["blocchi"], "ADX": {"finto_ore": [1]}}},
            "niente uscite": {**cfg, "blocchi": {"E47": {}, "ADX": {}}},
            "lati vuoti": {**cfg, "lati": []},
            "filtri oltre 2": {**cfg, "modelli": [{"trigger": 1, "filtri": [0, 3], "uscite": 1}]},
            "processi 0": {**cfg, "processi": 0},
            "budget negativo": {**cfg, "budget": {**cfg["budget"], "totale": -1}},
            "peso oltre 1": {**cfg, "qualita_1": {**cfg["qualita_1"], "peso_max": 1.5}},
            "confini": {**cfg, "confini": {**STANDARD, "ricerca_ore": -5}},
            "E47 su H1": {**cfg, "timeframe": "H1"},
        }
        passate = [nome for nome, c in sbagliate.items() if not errore(lambda c=c: controlla_config(c))]
        check(f"32. {len(sbagliate)} config sbagliate: tutte ferme", not passate, f"passate: {passate}")
        ammessi = []
        for tf in ("M1", "M5", "M15", "M30", "H1", "H4", "D1"):
            c = config_standard(PERP, tf)
            controlla_config(c)
            ammessi.append((tf, len(c["blocchi"])))
        d1 = config_standard(PERP, "D1")
        check("33. da M1 a D1 la config standard tiene solo i blocchi che scattano sul timeframe",
              dict(ammessi)["M15"] == 17 and "F20_SESSION_OVERLAP" not in d1["blocchi"] and "E36" not in d1["blocchi"]
              and "E5" in d1["blocchi"], str(ammessi))
        check("34. budget: 1.176 teorie fanno 96.840 prove, sotto le 100.000 (§5)", budget_massimo(1176, cfg) == 96_840
              and controlla_budget(1176, cfg) == 96_840)
        largo = {**cfg, "budget": {**cfg["budget"], "per_teoria_passo_1": 80}}
        check("35. massimi oltre il totale: si ferma prima di partire", errore(lambda: controlla_budget(1176, largo)))

        # ------------------------------------------------------------------ il salvataggio
        print("\nIl salvataggio")
        dati = os.path.join(base, "dati_config")
        id1 = salva_config(cfg, dati, data="20261107")
        percorso = os.path.join(cartella_asset(dati, PERP, "M15"), id1, "config.json")
        with open(percorso, "rb") as f:
            prima_byte = f.read()
        check("36. dati/fabbrica/<SYMBOL>_<TIMEFRAME>/<data>_<impronta>/config.json",
              os.path.exists(percorso) and id1 == "20261107_" + impronta_config(cfg)[:12]
              and os.path.normpath(percorso).split(os.sep)[-4:-2] == ["fabbrica", "BINANCE_PERP_BTCUSDT_M15"])
        id2 = salva_config(rovesciata, dati, data="20261108")
        with open(percorso, "rb") as f:
            dopo_byte = f.read()
        check("37. stessa config un altro giorno: stessa ricerca, nessuna scrittura", id2 == id1 and dopo_byte == prima_byte
              and len(os.listdir(cartella_asset(dati, PERP, "M15"))) == 1)
        check("38. letta dal file è la stessa config", leggi_config(percorso) == json.loads(json.dumps(cfg)))
        id3 = salva_config({**cfg, "seme": 5}, dati, data="20261107")
        check("39. config diversa: ricerca nuova, in una cartella nuova", id3 != id1 and len(os.listdir(cartella_asset(dati, PERP, "M15"))) == 2)
        with open(percorso, "w", encoding="utf-8") as f:
            f.write(json.dumps({**cfg, "seme": 9}))
        check("40. una cartella con la stessa impronta ma un config.json cambiato: errore, nessuna sovrascrittura",
              errore(lambda: salva_config(cfg, dati)) and json.load(open(percorso, encoding="utf-8"))["seme"] == 9)
        check("41. una config sbagliata non si salva", errore(lambda: salva_config({**cfg, "lati": []}, dati)))
        p3 = os.path.join(cartella_asset(dati, PERP, "M15"), id3, "config.json")
        with open(p3, "rb") as f:
            byte_3 = f.read()
        id4 = salva_config({**cfg, "seme": 5, "processi": 1}, dati, data="20261108")
        with open(p3, "rb") as f:
            check("42. processi diversi: stessa impronta, stessa ricerca, config.json intatto (08/11)",
                  impronta_config({**cfg, "processi": 1}) == impronta_config(cfg) and id4 == id3
                  and f.read() == byte_3 and len(os.listdir(cartella_asset(dati, PERP, "M15"))) == 2)
    finally:
        shutil.rmtree(base, ignore_errors=True)

    print("\n" + "=" * 70)
    print(f"Durata: {time.perf_counter() - t0:.0f} s")
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
