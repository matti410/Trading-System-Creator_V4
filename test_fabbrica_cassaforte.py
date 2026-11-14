"""
Suite di collaudo della cassaforte della fabbrica e dell'adattatore della Sessione (docs/82 P7, P8, P9, lavoro L4b).

Si lancia da terminale, dalla cartella del progetto:

    python test_fabbrica_cassaforte.py

Solo dati sintetici (engine/fabbrica/sintetici.py), scritti in cartelle temporanee: non servono i file in dati/,
MetaTrader 5 o internet. Stampa una riga per collaudo e alla fine «RISULTATO: n/n test superati».
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import os
import sys
import tempfile
import time
import warnings

import matplotlib
import numpy as np
import pandas as pd

from engine import registry as reg
from engine import vetrina, vetrina_verifica
from engine.fabbrica import dati as dati_mod
from engine.fabbrica import registro, sintetici
from engine.fabbrica import sessione as ses
from engine.fabbrica.cassaforte import (INGRESSO, congela, entra, esito_cassaforte, gia_entrata,
                                        strategie_entrate, tratti_usati, tratto)
from engine.fabbrica.blocchi import blocchi_da_config
from engine.fabbrica.cache import Cache
from engine.fabbrica.config import cartella_asset, config_standard
from engine.fabbrica.dati import Confini, carica_pezzi
from engine.fabbrica.generatore import stato_registro
from engine.fabbrica.ricerca import lancia
from engine.fabbrica.selezione import ValutatoreSelezione, strategia_da_riga
from engine.fabbrica.valutatore import Costi
from engine.giudizio import soglia_rumore
from engine.vetrina_fabbrica import sessione_da_strategia

warnings.simplefilter("ignore")
matplotlib.use("Agg")                 # i grafici del Lab senza finestra: un collaudo non aspetta nessuno

PERP, SPOT = "BINANCE_PERP_BTCUSDT", "BYBIT_SPOT_ETHUSDT"
DATA = "20260101"
ORA_FISSA = "2026-01-01T00:00:00+00:00"
CONFINI = {"inizio": "2024-01-01 00:00", "ricerca_ore": 3000, "selezione_ore": 2000, "cassaforte_ore": 500}
BLOCCHI = ("E47", "DONCHIAN", "RSI_RIENTRO", "F3_VOLUME_ABOVE_AVG", "X0")
ESITI: list[bool] = []


def check(nome: str, ok: bool, dettaglio: str = "") -> None:
    ESITI.append(bool(ok))
    print(f"[{'OK ' if ok else 'KO '}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""))


def errore(funzione, tipo=Exception) -> bool:
    try:
        funzione()
    except tipo:
        return True
    return False


def _leggi(percorso):
    with open(percorso, "rb") as f:
        return f.read()


def _fotografia(cartella, solo=None, salta=None):
    """{percorso: sha256} dei file sotto `cartella`; `solo` = solo quella sottocartella, `salta` = tranne quella."""
    out = {}
    for radice, _, nomi in os.walk(cartella):
        primo = os.path.relpath(radice, cartella).split(os.sep)[0]
        if (solo is not None and primo != solo) or (salta is not None and primo == salta):
            continue
        for n in nomi:
            p = os.path.join(radice, n)
            out[os.path.relpath(p, cartella)] = hashlib.sha256(_leggi(p)).hexdigest()
    return out


def _cfg(timeframe="M15", confini=CONFINI, blocchi=BLOCCHI):
    cfg = config_standard(SPOT, timeframe, seme=0, processi=1)
    cfg["confini"] = dict(confini)
    cfg["blocchi"] = {k: v for k, v in cfg["blocchi"].items() if k in blocchi}
    cfg["qualita_1"]["trade_min"] = 30
    cfg["budget"].update({"teorie_turno_2": 4, "teorie_passo_2": 4, "prove_per_giro": 60})
    return cfg


def _mercato(minuti=15, confini=CONFINI):
    n = int((confini["ricerca_ore"] + confini["selezione_ore"] + confini["cassaforte_ore"]) * 60 / minuti) + 100
    return sintetici.mercato_piantato(n, seme=5, minuti=minuti, inizio="2024-01-01", prezzo=2_000.0)


def _zitto(funzione, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return funzione(*a, **k)


def _elenco(ids):
    return [{"id_strategia": i, "teoria": "L|X|-|X0", "valori": {}, "t_selezione": 2.0} for i in ids]


def esegui() -> int:
    t0 = time.perf_counter()
    registro_adesso = registro.adesso
    registro.adesso = lambda: ORA_FISSA          # l'orologio fisso: registri confrontabili al bit
    try:
        with tempfile.TemporaryDirectory() as radice:
            _regole(radice)
            _giro(radice)
    finally:
        registro.adesso = registro_adesso
    print("\n" + "=" * 70)
    print(f"Durata: {time.perf_counter() - t0:.0f} s")
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


# ------------------------------------------------------------------ le regole del registro, senza dati
def _regole(radice):
    print("Le regole della cassaforte sul registro (docs/82 P8)")
    base = os.path.join(radice, "regole")
    c1 = Confini.da_config(CONFINI)
    dove = {"id_ricerca": "r1", "impronta_config": "x"}
    t1 = tratto(SPOT, "M15", c1)
    e = congela(base, c1, SPOT, "M15", _elenco(["aaa", "bbb"]), dove)
    check("1. il primo ingresso scrive l'elenco nel registro; due strategie entrate nel tratto",
          e["tipo"] == INGRESSO and e["tratto"]["id"] == t1 and e["entrate_nel_tratto"] == 2
          and gia_entrata(base, t1, "aaa") and strategie_entrate(base, t1) == 2 and not gia_entrata(base, t1, "ccc"))
    e2 = congela(base, c1, SPOT, "M15", _elenco(["aaa"]), dove)
    check("2. (10/11) la stessa strategia di nuovo nello stesso tratto: entra, un ingresso nuovo nel registro; le "
          "strategie entrate nel tratto restano 2 (ognuna contata una volta)",
          e2["tipo"] == INGRESSO and e2["entrate_nel_tratto"] == 2 and strategie_entrate(base, t1) == 2)
    e3 = congela(base, c1, SPOT, "M15", _elenco(["aaa_parametro_cambiato"]), {**dove, "id_ricerca": "r2"})
    check("3. un parametro cambiato è una strategia nuova: entra nello stesso tratto, il conto sale di uno",
          e3["entrate_nel_tratto"] == 3 and strategie_entrate(base, t1) == 3)
    c2 = Confini.da_config({**CONFINI, "inizio": "2024-01-21 20:00"})        # avanti di 500 ore: tratto nuovo
    t2 = tratto(SPOT, "M15", c2)
    e4 = congela(base, c2, SPOT, "M15", _elenco(["aaa"]), dove)
    check("4. la stessa strategia in un tratto nuovo (finestra scorsa di una cassaforte): entra; il conto del tratto "
          "nuovo parte da 1, quello vecchio non cambia", e4["entrate_nel_tratto"] == 1 and strategie_entrate(base, t2) == 1
          and strategie_entrate(base, t1) == 3 and t2 != t1 and len(tratti_usati(base)) == 2)
    c_mezzo = Confini.da_config({**CONFINI, "inizio": "2024-01-11 10:00"})   # avanti di 250 ore: tocca i due tratti
    t_mezzo = tratto(SPOT, "M15", c_mezzo)
    e5 = congela(base, c_mezzo, SPOT, "M15", _elenco(["zzz", "aaa"]), dove)
    check("5. (10/11) in una cassaforte che si sovrappone a quelle già usate entrano sia una strategia nuova sia una "
          "già entrata", e5["tratto"]["id"] == t_mezzo and gia_entrata(base, t_mezzo, "zzz")
          and gia_entrata(base, t_mezzo, "aaa") and strategie_entrate(base, t_mezzo) == 2)
    congela(base, c1, SPOT, "M15", _elenco(["ddd"]), dove, nome_macchina="colab")
    e6 = congela(base, c1, SPOT, "M15", _elenco(["ddd"]), dove)
    check("6. il conto legge i registri di tutte le macchine: entrata da Colab, rientrata dal PC, contata una volta",
          gia_entrata(base, t1, "ddd") and strategie_entrate(base, t1) == 4 and e6["entrate_nel_tratto"] == 4)
    check("7. elenco vuoto o con una strategia due volte: errore",
          errore(lambda: congela(base, c1, SPOT, "M15", [], dove))
          and errore(lambda: congela(base, c1, SPOT, "M15", _elenco(["eee", "eee"]), dove)))
    percorso = registro.percorso_registro(base)
    buono = _leggi(percorso)
    righe = buono.decode("utf-8").splitlines()
    assert '"entrate_nel_tratto":2' in righe[0]
    righe[0] = righe[0].replace('"entrate_nel_tratto":2', '"entrate_nel_tratto":1')
    with open(percorso, "wb") as f:
        f.write(("\n".join(righe) + "\n").encode("utf-8"))
    cambiata = gia_entrata(base, t1, "aaa") and [e for e in registro.leggi_registro(base)
                                                  if e["macchina"] == registro.macchina()][0]["entrate_nel_tratto"] == 1
    with open(percorso, "wb") as f:
        f.write(("\n".join(buono.decode("utf-8").splitlines()[:1] + buono.decode("utf-8").splitlines()[2:]) + "\n")
                .encode("utf-8"))
    e8 = congela(base, c1, SPOT, "M15", _elenco(["fff"]), dove)
    check("8. (10/11) registro modificato a mano (una riga cambiata, una riga tolta in mezzo): si legge com'è e non "
          "ferma niente; un ingresso nuovo si scrive in fondo", cambiata and e8["tipo"] == INGRESSO
          and gia_entrata(base, t1, "fff"))
    with open(percorso, "wb") as f:
        f.write(buono)


# ------------------------------------------------------------------ il giro completo
def _giro(radice):
    print("\nIl giro completo sul mercato con il vantaggio piantato (spot, M15)")
    cfg = _cfg()
    df_v = _mercato()
    A = os.path.join(radice, "A")
    sintetici.scrivi_storico(A, SPOT, "M15", df_v)
    os.makedirs(os.path.join(A, "studio"))
    for nome, testo in (("confine.json", '{"confine": "2025-06-15 17:30"}\n'), ("diario_pc.jsonl", '{"prova": 1}\n'),
                        ("giornale_pc.jsonl", '{"voce": "trigger"}\n')):
        with open(os.path.join(A, "studio", nome), "w", encoding="utf-8") as fh:
            fh.write(testo)
    foto_studio = _fotografia(A, salta="fabbrica")
    e = lancia(cfg, A, verbose=False, data=DATA)
    scelte = list(e.selezione.scelte["id_strategia"])
    base = cartella_asset(A, SPOT, "M15")
    prove_csv = registro.FileProve(e.cartella).percorso

    def fermo():
        return _leggi(registro.percorso_registro(base)), _leggi(prove_csv)

    stato = fermo()
    altre = list(e.selezione.tabella.loc[e.selezione.tabella["esito"] != "scelta", "id_strategia"])
    check("10. una strategia non scelta in selezione (scartata o della stessa famiglia): errore, niente scritto",
          scelte and altre and all(errore(lambda i=i: entra(A, e.id_ricerca, scelte + [i])) for i in altre)
          and fermo() == stato, f"{len(altre)} non scelte")

    c = entra(A, e.id_ricerca, scelte)
    eventi = registro.leggi_registro(base)
    tipi = [x["tipo"] for x in eventi]
    tab = c.tabella
    prima_c, ultima_c = dati_mod._utc(c.tratto["da"]), dati_mod._utc(c.tratto["a"])
    dentro = all(len(t) == 0 or (t["EntryTime"].min() >= prima_c and t["ExitTime"].max() < ultima_c)
                 for t in c.trade.values())
    check("11. l'elenco va nel registro prima dell'esito; ogni trade sta nella cassaforte",
          tipi == ["avvio_ricerca", "fine_ricerca", "ingresso_cassaforte", "esito_cassaforte"] and dentro
          and [x["id_strategia"] for x in eventi[2]["strategie"]] == scelte)
    primo = tab.iloc[0]
    check("12. decide il test individuale: t in cassaforte >= 1,96; la DONCHIAN piantata passa",
          primo["teoria"].startswith("L|DONCHIAN|") and primo["t"] >= 1.96 and primo["esito"] == "passa"
          and (tab["esito"] == np.where(tab["t"] >= tab["soglia_test"], "passa", "non passa")).all()
          and abs(primo["soglia_test"] - 1.959964) < 1e-6, f"t selezione {primo['t_selezione']:.1f}, cassaforte {primo['t']:.1f}")
    p = c.pezzo
    v = ValutatoreSelezione(blocchi_da_config(cfg), Cache(p.df, 500), Costi(p.df, p.costi), p.inizio)
    uguali = all(np.allclose(v.bp(strategia_da_riga(r, SPOT, "M15")), c.trade[r["id_strategia"]]["BpNetti"].to_numpy(),
                             atol=1e-9, rtol=0) for r in eventi[2]["strategie"])
    check("13. il motore completo sulla cassaforte dà gli stessi bp del percorso corto; il pezzo finisce all'ultima barra "
          "della cassaforte", uguali and p.df.index[-1] < ultima_c and p.df.index[p.inizio] >= prima_c)
    csv = pd.read_csv(prove_csv, dtype=str, keep_default_na=False)
    k = registro.conto_prove(A, SPOT, "M15")
    check("14. ogni strategia entrata è una prova (pezzo «cassaforte»); conto e soglia da leggere; strategie entrate",
          sorted(csv.loc[csv["pezzo"] == "cassaforte", "id_strategia"]) == sorted(scelte) and (tab["prove_asset"] == k).all()
          and np.allclose(tab["soglia_da_leggere"], soglia_rumore(k)) and (tab["entrate_nel_tratto"] == len(scelte)).all()
          and eventi[3]["entrate_nel_tratto"] == len(scelte), f"k = {k}")
    prove_prima = _leggi(prove_csv)
    c_ri = entra(A, e.id_ricerca, scelte[:1])
    tipi_ri = [x["tipo"] for x in registro.leggi_registro(base)]
    check("15. (10/11) la stessa strategia di nuovo nello stesso tratto: entra; un ingresso e un esito in più nel "
          "registro, stessi numeri, nessuna prova nuova",
          tipi_ri[-2:] == ["ingresso_cassaforte", "esito_cassaforte"] and len(tipi_ri) == len(tipi) + 2
          and c_ri.tabella.iloc[0]["t"] == tab.iloc[0]["t"] and _leggi(prove_csv) == prove_prima)
    stato = fermo()
    c_bis = esito_cassaforte(A, e.id_ricerca)
    check("16. l'esito si rifà identico, senza un ingresso nuovo né prove nuove", c_bis.tabella.equals(tab)
          and fermo() == stato)
    check("17. separazione dal Lab, cassaforte compresa: la cartella dello studio e i dati restano identici al bit",
          _fotografia(A, salta="fabbrica") == foto_studio)
    pezzi = carica_pezzi(SPOT, "M15", Confini.da_config(cfg["confini"]), A)
    check("18. Pezzi senza il permesso: errore", errore(lambda: pezzi.apri_cassaforte(None), PermissionError))

    # ------------------------------------------------------------------ il dataset che si rompe alla prima lettura
    print("\nL'elenco si scrive prima di leggere una barra")
    B = os.path.join(radice, "B")
    sintetici.scrivi_storico(B, SPOT, "M15", df_v)
    eb = lancia(cfg, B, verbose=False, data=DATA)
    base_b = cartella_asset(B, SPOT, "M15")
    vera, letture = dati_mod._leggi, []

    def rotta(*a, **k):
        letture.append(a)
        raise OSError("il dataset si rompe alla prima lettura")

    dati_mod._leggi = rotta
    try:
        fermata = errore(lambda: entra(B, eb.id_ricerca, scelte), OSError)
    finally:
        dati_mod._leggi = vera
    ev_b = registro.leggi_registro(base_b)
    check("19. un dataset che si rompe alla prima lettura: l'elenco congelato è già nel registro, senza esito",
          fermata and len(letture) == 1 and [x["tipo"] for x in ev_b][-1] == INGRESSO
          and [x["id_strategia"] for x in ev_b[-1]["strategie"]] == scelte)
    check("20. dopo la rottura le strategie sono entrate: l'esito si completa una volta, senza un ingresso nuovo",
          esito_cassaforte(B, eb.id_ricerca).tabella.equals(tab)
          and [x["tipo"] for x in registro.leggi_registro(base_b)][-2:] == ["ingresso_cassaforte", "esito_cassaforte"]
          and (esito_cassaforte(B, eb.id_ricerca) is not None)
          and [x["tipo"] for x in registro.leggi_registro(base_b)].count("esito_cassaforte") == 1)

    # ------------------------------------------------------------------ il veleno
    print("\nIl test del veleno: la cassaforte non si legge prima del passo 8")
    W = os.path.join(radice, "W")
    velenoso = df_v.copy()
    nella = velenoso.index >= Confini.da_config(CONFINI).tratto_cassaforte[0]
    velenoso.loc[nella, ["Open", "High", "Low", "Close"]] *= 3.0
    velenoso.loc[nella, "Volume"] = 1.0
    sintetici.scrivi_storico(W, SPOT, "M15", velenoso)
    C = os.path.join(radice, "C")
    sintetici.scrivi_storico(C, SPOT, "M15", df_v)
    ec = lancia(cfg, C, verbose=False, data=DATA)
    ew = lancia(cfg, W, verbose=False, data=DATA)
    check("21. passi 1–7 con la cassaforte avvelenata (prezzi × 3, volume 1): ogni file della fabbrica identico al bit, "
          "registro compreso", ew.id_ricerca == ec.id_ricerca
          and _fotografia(W, solo="fabbrica") == _fotografia(C, solo="fabbrica"), f"{len(_fotografia(C, solo='fabbrica'))} file")
    cc = entra(C, ec.id_ricerca, scelte)
    cw = entra(W, ew.id_ricerca, scelte)
    r_c = _leggi(registro.percorso_registro(cartella_asset(C, SPOT, "M15"))).splitlines()
    r_w = _leggi(registro.percorso_registro(cartella_asset(W, SPOT, "M15"))).splitlines()
    check("22. anche l'elenco congelato è identico al bit; solo la valutazione della cassaforte cambia",
          r_c[:3] == r_w[:3] and r_c[3] != r_w[3] and not cc.tabella["t"].equals(cw.tabella["t"]))

    _sessione(radice, A, e, c, cfg)


# ------------------------------------------------------------------ l'adattatore della Sessione (P9)
def _sessione(radice, A, e, c, cfg):
    print("\nL'adattatore della Sessione per le schermate 7, 9 e 8 del Lab (docs/82 P9)")
    id0 = c.tabella["id_strategia"].iloc[0]
    prima = stato_registro()
    s = sessione_da_strategia(A, e.id_ricerca, id0, esito=c)
    prima_c = dati_mod._utc(c.tratto["da"])
    ok_campi = (s.df_is.index[-1] < prima_c and s.trades_is["ExitTime"].max() <= s.df_is.index[-1]
                and pd.DatetimeIndex(s.df_oos.index).equals(pd.DatetimeIndex(c.pezzo.df.index[c.pezzo.inizio:]))
                and (s.trades_oos["EntryTime"].to_numpy() == c.trade[id0]["EntryTime"].to_numpy()).all()
                and (s.df_oos.index[s.trades_oos["EntryBar"].to_numpy()] == s.trades_oos["EntryTime"]).all()
                and s.fabbrica["finestra"] == 500 and s.unita == "bp" and s.da_exchange
                and any(n.startswith(s.fabbrica["prefisso"]) for n in reg.list_entries()))
    check("23. la Sessione: in-sample = ricerca + selezione, out-of-sample = la cassaforte con i suoi trade; trigger e "
          "filtri della strategia nel catalogo con nomi temporanei", ok_campi,
          f"{len(s.trades_is)} trade in-sample, {len(s.trades_oos)} in cassaforte")
    chiamate = []
    vera_mm = vetrina.money_management_trade

    def registra(*a, **k):
        chiamate.append((a, k))
        return {"rischio": None, "sintesi": None}

    vetrina.money_management_trade = registra
    try:
        _zitto(vetrina.money_management, s)              # la schermata 7 del Lab, così com'è
        _zitto(ses.money_management, s)                  # l'adattatore della fabbrica
    finally:
        vetrina.money_management_trade = vera_mm
    lab, fab = chiamate
    fab_k = {k: v for k, v in fab[1].items() if k != "simulazioni"}
    check("24. schermata 7 su M15: l'adattatore passa a money_management_trade gli stessi dati della schermata del Lab "
          "(finestra 125 ore = 500 barre)", len(chiamate) == 2 and lab[0] == fab[0] and lab[1] == fab_k
          and fab[1]["simulazioni"] == vetrina.SIMULAZIONI_MM)
    mm = _zitto(ses.money_management, s, simulazioni=300)
    st = _zitto(vetrina.stress_test, s, simulazioni=2_000)
    check("25. money management (300 simulazioni) e stress test della schermata 9 girano sulla Sessione, in bp",
          s.mm is mm and {"rischio", "sintesi"} <= set(mm) and st["unita"] == "bp"
          and st["sizing"]["lotti_consigliati"] >= 0)
    ver = _zitto(ses.verifica_trade, s)
    lab_v = _zitto(vetrina_verifica.verifica_trade, s)
    check("26. schermata 8 su M15: ogni regola OK; uguale alla verifica del Lab con la sua finestra di 500 barre",
          (ver["regole"]["Esito"] == "OK").all() and all(ver[k].equals(lab_v[k]) for k in ("regole", "uscite", "segnali")),
          "; ".join(f"{r.Regola[:25]}: {r.Esito}" for r in ver["regole"].itertuples()))
    fig = _zitto(vetrina_verifica.lente, s, numero=1, mostra_trigger=False)
    check("27. la lente disegna un trade della cassaforte", fig is not None and len(fig.data) > 0)
    ses.chiudi(s)
    check("28. chiudi: il catalogo torna identico, nessuna condizione temporanea", stato_registro() == prima
          and not any(n.startswith(ses.PREFISSO) for n in reg.list_entries() + reg.list_filters()))
    non_entrata = e.selezione.tabella.loc[e.selezione.tabella["esito"] != "scelta", "id_strategia"].iloc[0]
    check("29. una strategia non entrata in cassaforte: niente Sessione, catalogo pulito",
          errore(lambda: sessione_da_strategia(A, e.id_ricerca, non_entrata, esito=c)) and stato_registro() == prima)
    vera_imp = vetrina.impostazioni_uscite

    def rotta(*a, **k):
        raise RuntimeError("rotta apposta, dopo la registrazione")

    vetrina.impostazioni_uscite = rotta
    try:
        fermata = errore(lambda: ses.apri_sessione(c, id0), RuntimeError)
    finally:
        vetrina.impostazioni_uscite = vera_imp
    pulito_1 = stato_registro() == prima

    def dentro_e_rompi():
        with ses.sessione(c, id0) as s2:
            assert any(n.startswith(s2.fabbrica["prefisso"]) for n in reg.list_entries())
            raise KeyError("errore dentro il blocco")

    check("30. un errore a metà dell'apertura o dentro il blocco with: il catalogo torna identico",
          fermata and pulito_1 and errore(dentro_e_rompi, KeyError) and stato_registro() == prima)

    # ------------------------------------------------------------------ un timeframe diverso
    print("\nLa stessa verifica su H1 (125 ore = 125 barre)")
    confini_h1 = {"inizio": "2024-01-01 00:00", "ricerca_ore": 12000, "selezione_ore": 8000, "cassaforte_ore": 2000}
    H = os.path.join(radice, "H1")
    sintetici.scrivi_storico(H, SPOT, "H1", _mercato(60, confini_h1))
    eh = lancia(_cfg("H1", confini_h1, ("DONCHIAN", "RSI_RIENTRO", "F3_VOLUME_ABOVE_AVG", "X0")), H, verbose=False,
                data=DATA)
    scelte_h = list(eh.selezione.scelte["id_strategia"])
    ch = entra(H, eh.id_ricerca, scelte_h) if scelte_h else None
    ok_h, dettaglio = False, f"imbuto {eh.imbuto}"
    if ch is not None:
        with ses.sessione(ch, scelte_h[0]) as sh:
            ver_h = _zitto(ses.verifica_trade, sh)
            lab_h = _zitto(vetrina_verifica.verifica_trade, sh)
            mm_h = _zitto(ses.money_management, sh, simulazioni=300)
            ok_h = (sh.fabbrica["finestra"] == 125 and (ver_h["regole"]["Esito"] == "OK").all()
                    and ver_h["regole"].equals(lab_h["regole"]) and len(sh.trades_oos) > 0 and {"rischio"} <= set(mm_h))
            dettaglio = (f"{ch.tabella['teoria'].iloc[0]}, {len(sh.trades_oos)} trade in cassaforte; segnali non "
                         f"tradati uguali alle 500 barre del Lab: {ver_h['segnali'].equals(lab_h['segnali'])}")
    check("31. H1: finestra di 125 barre; ogni regola OK; le regole non dipendono dalla finestra; money management gira",
          ok_h, dettaglio)
    check("32. alla fine il catalogo è identico a prima della Sessione", stato_registro() == prima)


if __name__ == "__main__":
    sys.exit(esegui())
