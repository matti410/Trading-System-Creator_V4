"""
Suite di collaudo del valutatore della fabbrica (docs/82 P4, lavoro L3a).

Si lancia da terminale, dalla cartella del progetto:

    python test_fabbrica_valutatore.py

Solo dati sintetici (engine/fabbrica/sintetici.py), scritti in una cartella temporanea: non servono i file in dati/,
MetaTrader 5 o internet. Stampa una riga per collaudo e alla fine «RISULTATO: n/n test superati».

Il collaudo più importante: su 200 strategie casuali, valuta deve dare gli stessi bp di MotoreVeloce.run più
metriche.bp_per_trade (tolleranza 1e-9), funding e spread compresi, su perpetual e su spot.
"""
from __future__ import annotations

import math
import sys
import tempfile
import time
import warnings

import numpy as np
import pandas as pd

from engine import registry as reg
from engine.exit_search_bt import run_exit_search_bt
from engine.fabbrica import sintetici
from engine.fabbrica.blocchi import blocchi_da_config
from engine.fabbrica.cache import ORE_FINESTRA_SOGLIE, Cache, barre_da_ore
from engine.fabbrica.config import BLOCCHI_P_L2, config_standard
from engine.fabbrica.dati import Confini, carica_pezzi
from engine.fabbrica.generatore import (ControlloDegenerazione, Teoria, lati_config, misura_famiglie, teorie_turno_1,
                                        teorie_turno_2, togli_degeneri, un_blocco_per_famiglia)
from engine.fabbrica.ottimizzatore import Categoria
from engine.fabbrica.valutatore import (Costi, Misure, Strategia, Valutatore, id_strategia, misure_da_bp, obiettivo,
                                        qualita_1, trade_completi)
from engine.giudizio import t_stat
from engine.indicatori import aggiungi_indicatori
from engine.metriche import bp_per_trade

warnings.simplefilter("ignore")

PERP, SPOT = "BINANCE_PERP_BTCUSDT", "BYBIT_SPOT_ETHUSDT"
CONFINI = {"inizio": "2024-01-01 00:00", "ricerca_ore": 5000, "selezione_ore": 2000, "cassaforte_ore": 1000}
N_CASUALI = 200
TOLLERANZA = 1e-9
PREFISSO = "PROVA_FAB_VAL_"


def _prepara(cartella, symbol, prezzo, seme):
    df = sintetici.mercato(32_500, seme=seme, minuti=15, inizio="2024-01-01", prezzo=prezzo)
    sintetici.scrivi_storico(cartella, symbol, "M15", df)
    if "_PERP_" in symbol:
        sintetici.scrivi_funding(cartella, symbol, df, seme=seme)
    cfg = config_standard(symbol, "M15")
    cfg["confini"] = dict(CONFINI)
    cfg["blocchi"] = {k: v for k, v in cfg["blocchi"].items() if k in BLOCCHI_P_L2}   # i blocchi di P-L2, come prima
    pezzi = carica_pezzi(symbol, "M15", Confini.da_config(cfg["confini"]), cartella)
    costi = pezzi.costi("ricerca")
    dfi = aggiungi_indicatori(pezzi.ricerca)
    cache = Cache(dfi, 800)
    blocchi = blocchi_da_config(cfg)
    lati = lati_config(cfg)
    controllo = ControlloDegenerazione(cache)
    rimaste, _ = togli_degeneri(blocchi, cache, lati, controllo)
    _, misura = misura_famiglie(blocchi, cache, lati, rimaste)
    tenuti, _ = un_blocco_per_famiglia(blocchi, misura, controllo, lati, rimaste)
    teorie = teorie_turno_1(cfg, blocchi, tenuti)                  # C2: le teorie dei due turni
    teorie += teorie_turno_2([t for t in teorie if len(t.filtri) == 1], cfg, blocchi, tenuti)
    return {"cfg": cfg, "costi": costi, "df": dfi, "cache": cache, "blocchi": blocchi, "teorie": teorie,
            "valutatore": Valutatore(blocchi, cache, Costi(dfi, costi))}


def _casuale(teoria: Teoria, blocchi: dict, rng) -> Strategia:
    """Valori a caso: metà dalla griglia del passo 1, metà dallo spazio fine dello zoom."""
    valori = {}
    for nome in teoria.blocchi:
        b = blocchi[nome]
        if not b.parametri:
            continue
        valori[nome] = {}
        for p in b.parametri:
            if isinstance(p, Categoria) or rng.random() < 0.5:
                griglia = b.griglia[p.nome]
                valori[nome][p.nome] = griglia[int(rng.integers(len(griglia)))]
            else:
                valori[nome][p.nome] = p.valore(int(rng.integers(p.n)))
    return Strategia.da_teoria(teoria, valori)


def _confronta(prep, n, seme):
    """(massima differenza, trade, strategie con trade, short, con stop, con target, con funding diverso da zero)."""
    rng = np.random.default_rng(seme)
    blocchi = {b.nome: b for b in prep["blocchi"]}
    v = prep["valutatore"]
    peggio, trade, con_trade, short, stop, target, funding, diversi = 0.0, 0, 0, 0, 0, 0, 0, []
    for _ in range(n):
        s = _casuale(prep["teorie"][int(rng.integers(len(prep["teorie"])))], blocchi, rng)
        corto = v.bp(s)
        completi = trade_completi(s, v, prep["costi"])
        riferimento = bp_per_trade(completi, prep["costi"]["pip_size"], prep["costi"]["commission"])[1].to_numpy()
        if len(corto) != len(riferimento):
            diversi.append((s.teoria_id, len(corto), len(riferimento)))
            continue
        if len(corto):
            peggio = max(peggio, float(np.max(np.abs(corto - riferimento))))
            con_trade += 1
        trade += len(corto)
        short += s.lato == -1
        vu = s.valori_di(s.uscita)
        stop += vu["perc_stop"] not in (None, 0)
        target += vu["target"] not in (None, 0)
        if "FundingPips" in completi.columns and (completi["FundingPips"].abs() > 0).any():
            funding += 1
    return peggio, trade, con_trade, short, stop, target, funding, diversi


def _dal_lab(prep, s: Strategia) -> np.ndarray:
    """La stessa strategia con il percorso del Lab: run_exit_search_bt, che fa da sé quarantena e soglie mancanti."""
    v, c = prep["valutatore"], prep["cache"]
    blocchi = {b.nome: b for b in prep["blocchi"]}
    grezzo = blocchi[s.trigger].maschera(c, s.lato, s.valori_di(s.trigger) or None)
    for f in s.filtri:
        grezzo = grezzo & blocchi[f].maschera(c, s.lato, s.valori_di(f) or None)
    nome = f"{PREFISSO}{abs(hash(s)) % 10**9}"
    reg.register_entry(nome, direction=s.lato)(lambda d, _m=grezzo.copy(): pd.Series(_m, index=d.index))
    try:
        u = blocchi[s.uscita]
        coppia = reg.get_exit_pair(u._catalogo[0])
        vu = s.valori_di(s.uscita)
        costi = dict(prep["costi"])
        lungo, corto = (nome, None) if s.lato == 1 else (None, nome)
        es = run_exit_search_bt(prep["df"], entry_cols_long=[lungo], entry_cols_short=[corto], n_barre=vu["durata_barre"],
                                exit_rule_pairs=[coppia], perc_sl=vu["perc_stop"] or 0, perc_tp=vu["target"] or 0,
                                finestra=barre_da_ore(ORE_FINESTRA_SOGLIE, 15), lag=1, min_trades=1, verbose=False,
                                unita="bp", **costi)
        etichetta = f"L={lungo or '—'} · S={corto or '—'} | X={coppia or '—'}"
        return bp_per_trade(es.trades(etichetta), costi["pip_size"], costi["commission"])[1].to_numpy()
    finally:
        reg.remove_entries(PREFISSO)


def _a_mano():
    """Dieci barre M15 a cavallo della mezzanotte, una liquidazione del funding alle 00:00."""
    indice = pd.date_range("2024-01-01 23:15", periods=10, freq="15min", tz="UTC")
    o = [100.0, 100.5, 103.0, 104.0, 105.0, 104.0, 104.0, 104.0, 104.0, 104.0]
    h = [101.0, 102.5, 103.5, 104.5, 105.5, 104.5, 104.5, 104.5, 104.5, 104.5]
    l = [99.0, 100.0, 102.5, 103.5, 104.0, 103.5, 103.5, 103.5, 103.5, 103.5]
    c = [100.0, 102.0, 103.0, 104.0, 105.0, 104.0, 104.0, 104.0, 104.0, 104.0]
    df = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 1.0}, index=indice)
    funding = pd.DataFrame({"tasso": [0.0001, 0.0001]}, index=pd.DatetimeIndex(
        ["2024-01-01 16:00", "2024-01-02 00:00"], tz="UTC", name="Date"))
    return df, funding


def esegui() -> int:
    ESITI = []
    t0 = time.perf_counter()

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        print(f"[{'OK ' if condizione else 'KO '}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""), flush=True)

    def errore(f) -> bool:
        try:
            f()
        except (ValueError, KeyError):
            return True
        return False

    with tempfile.TemporaryDirectory() as cartella:
        # ------------------------------------------------------------------ il collaudo più importante
        print("valuta = MotoreVeloce.run + metriche.bp_per_trade, su strategie casuali")
        perp = _prepara(cartella, PERP, 30_000.0, seme=1)
        peggio, trade, con_trade, short, stop, target, funding, diversi = _confronta(perp, N_CASUALI, seme=11)
        check(f"1. perpetual: {N_CASUALI} strategie, stessi trade e stessi bp (tolleranza {TOLLERANZA:g})",
              not diversi and peggio <= TOLLERANZA,
              f"differenza massima {peggio:.2e}, {trade} trade, {con_trade} strategie con trade; diversi {diversi[:3]}")
        check("2. perpetual: dentro ci sono short, stop, target e funding", short >= 50 and stop >= 50 and target >= 50
              and funding >= 50 and con_trade >= 150, f"short {short}, con stop {stop}, con target {target}, "
              f"con funding {funding}")
        spot = _prepara(cartella, SPOT, 2_000.0, seme=2)
        peggio_s, trade_s, con_trade_s, short_s, _, _, funding_s, diversi_s = _confronta(spot, N_CASUALI, seme=12)
        check(f"3. spot: {N_CASUALI} strategie, stessi trade e stessi bp", not diversi_s and peggio_s <= TOLLERANZA,
              f"differenza massima {peggio_s:.2e}, {trade_s} trade, {con_trade_s} strategie con trade")
        check("4. spot: solo long, nessun funding", short_s == 0 and funding_s == 0 and all(t.lato == 1 for t in spot["teorie"])
              and spot["valutatore"].costi.funding is None)

        # ------------------------------------------------------------------ il percorso del Lab
        print("\nLa stessa strategia con run_exit_search_bt (quarantena e soglie mancanti fatte dal Lab)")
        rng = np.random.default_rng(21)
        blocchi = {b.nome: b for b in perp["blocchi"]}
        uguali, provate = 0, 0
        for prep in (perp, spot):
            b_prep = {b.nome: b for b in prep["blocchi"]}
            for _ in range(6):
                s = _casuale(prep["teorie"][int(rng.integers(len(prep["teorie"])))], b_prep, rng)
                corto, lab = prep["valutatore"].bp(s), _dal_lab(prep, s)
                provate += 1
                uguali += len(corto) == len(lab) and (not len(corto) or float(np.max(np.abs(corto - lab))) <= TOLLERANZA)
        check("5. 12 strategie, perpetual e spot: stessi bp del percorso del Lab", uguali == provate, f"{uguali}/{provate}")
        nomi_dopo = [n for n in reg.list_entries() if n.startswith(PREFISSO)]
        check("6. registro pulito dopo la controprova", not nomi_dopo)

        # ------------------------------------------------------------------ segnale, quarantena, soglie
        print("\nIl segnale")
        v = perp["valutatore"]
        teoria = Teoria(1, "DONCHIAN", ("ADX",), "X3")
        s = Strategia.da_teoria(teoria, {"DONCHIAN": {"canale_barre": 48}, "ADX": {"periodo_barre": 24, "soglia": 20},
                                         "X3": {"durata_barre": 16, "perc_stop": 90, "target": 90}})
        g = v.segnali(s)
        c = perp["cache"]
        atteso = (blocchi["DONCHIAN"].maschera(c, 1, {"canale_barre": 48}) & blocchi["ADX"].maschera(c, 1, {"periodo_barre": 24, "soglia": 20}))
        check("7. il segnale sta dentro trigger e filtro", not (g["segnale"] & ~atteso).any() and g["segnale"].sum() > 0)
        soglie = blocchi["X3"].soglie(c, 1, {"durata_barre": 16, "perc_stop": 90, "target": 90})
        senza = np.r_[np.isnan(soglie["sl"][1:]) | np.isnan(soglie["tp"][1:]), False]
        check("8. nessun segnale dove stop o target mancano alla barra d'ingresso", not (g["segnale"] & senza).any()
              and (atteso & senza).any())
        check("9. l'ultima barra non dà mai segnale", not g["segnale"][-1])
        spento = Strategia.da_teoria(teoria, {"DONCHIAN": {"canale_barre": 48}, "ADX": {"periodo_barre": 24, "soglia": 20},
                                              "X3": {"durata_barre": 16, "perc_stop": 0, "target": None}})
        check("10. con stop e target spenti contano tutti i segnali (salvo quarantena e ultima barra)",
              v.segnali(spento)["segnale"].sum() >= g["segnale"].sum() and np.isnan(v.segnali(spento)["sl"]).all())

        # ------------------------------------------------------------------ a mano
        print("\nUn trade fatto a mano")
        df_m, funding_m = _a_mano()
        costi_m = {"spread": 0.0, "commission": 0.0005, "pip_size": 1.0, "spread_passo_pips": 0.1, "funding": funding_m,
                   "cash": 10_000_000}
        cfg_m = {"timeframe": "M15", "blocchi": {"DONCHIAN": {"canale_ore": [0.25]}, "X0": {}}}
        b_m = blocchi_da_config(cfg_m)
        v_m = Valutatore(b_m, Cache(df_m, 5), Costi(df_m, costi_m))
        s_m = Strategia.da_teoria(Teoria(1, "DONCHIAN", (), "X0"), {"DONCHIAN": {"canale_barre": 1},
                                                                     "X0": {"durata_barre": 2, "perc_stop": 0, "target": None}})
        lato, eb, xb, ep, xp = v_m.trade(s_m)
        check("11. segnale alla barra 1 (Close 102 sopra il massimo 101), ingresso all'Open della 2, uscita all'Open della 4",
              list(eb) == [2] and list(xb) == [4] and list(ep) == [103.0] and list(xp) == [105.0] and list(lato) == [1])
        # lordi 2 pips; commissione 0,0005 × (103 + 105) = 0,104; spread di un passo 0,1; funding alle 00:00 (dentro il trade,
        # ingresso alle 23:45): 0,0001 × Open delle 00:00 (104) = 0,0104 pips. Netti 1,7856 pips = 1,7856 / 103 × 10.000 bp
        atteso_bp = (2.0 - 0.104 - 0.1 - 0.0104) / 103.0 * 10_000.0
        bp_m = v_m.bp(s_m)
        check("12. bp netti a mano: 2 − 0,104 − 0,1 − 0,0104 pips = 173,36 bp", len(bp_m) == 1 and abs(bp_m[0] - atteso_bp) < 1e-9,
              f"{bp_m[0]:.6f} contro {atteso_bp:.6f}" if len(bp_m) else "nessun trade")
        senza_f = Valutatore(b_m, Cache(df_m, 5), Costi(df_m, {**costi_m, "funding": None})).bp(s_m)
        check("13. senza funding il trade guadagna 0,0104 pips in più", abs((senza_f[0] - bp_m[0]) - 0.0104 / 103.0 * 10_000.0) < 1e-9)
        check("14. e il motore completo dà lo stesso", abs(trade_completi(s_m, v_m, costi_m)["BpNetti"].iloc[0] - atteso_bp) < 1e-9)

        # ------------------------------------------------------------------ misure e qualità
        print("\nMisure e condizione di qualità 1")
        m = misure_da_bp([10.0, -5.0, 20.0, -30.0, 40.0])
        # curva 0, 10, 5, 25, -5, 35: drawdown 25 - (-5) = 30; peso 40 / (10 + 20 + 40)
        check("15. misure a mano: 5 trade, totale 35, EV 7, drawdown 30, peso 4/7, totale/drawdown 35/30",
              (m.trade, m.totale_bp, m.ev_bp, m.dd_bp) == (5, 35.0, 7.0, 30.0) and abs(m.peso_max - 40 / 70) < 1e-12
              and abs(m.totale_su_dd - 35 / 30) < 1e-12 and m.t == t_stat([10.0, -5.0, 20.0, -30.0, 40.0]))
        vuote = misure_da_bp([])
        check("16. nessun trade: t e EV NaN, l'obiettivo è NaN", vuote.trade == 0 and math.isnan(vuote.t) and math.isnan(obiettivo(vuote)))
        check("17. un solo trade o tutti uguali: t non calcolabile, obiettivo NaN", math.isnan(obiettivo(misure_da_bp([5.0])))
              and math.isnan(obiettivo(misure_da_bp([3.0, 3.0, 3.0]))))
        pochi = misure_da_bp([5.0, 7.0, -1.0])
        check("18. l'obiettivo è il t anche se la condizione di qualità non passa (decisione del 07/11)",
              obiettivo(pochi) == pochi.t and not qualita_1(pochi, perp["cfg"]["qualita_1"])[0])
        q = {"trade_min": 4, "ev_min_bp": 0, "peso_max": 0.5, "totale_su_dd_min": 1.0}
        casi = {"trade": [1.0, 2.0, 3.0], "ev": [1.0, -2.0, 1.0, -1.0], "peso": [10.0, 1.0, 1.0, -1.0],
                "dd": [1.0, -5.0, 1.0, 1.0, 1.0, 3.0], "passa": [2.0, 3.0, -1.0, 2.0, 3.0]}
        motivi = {k: qualita_1(misure_da_bp(x), q) for k, x in casi.items()}
        check("19. ogni motivo di scarto della condizione 1, e una che passa", not motivi["trade"][0] and "trade" in motivi["trade"][1]
              and not motivi["ev"][0] and "EV" in motivi["ev"][1] and not motivi["peso"][0] and "pesa" in motivi["peso"][1]
              and not motivi["dd"][0] and "drawdown" in motivi["dd"][1] and motivi["passa"] == (True, ""), str(motivi))

        # ------------------------------------------------------------------ l'impronta
        print("\nL'impronta della strategia")
        a = Strategia.da_teoria(teoria, {"ADX": {"soglia": 20, "periodo_barre": 24}, "DONCHIAN": {"canale_barre": 48},
                                         "X3": {"target": 90, "perc_stop": 90, "durata_barre": 16}})
        b2 = Strategia.da_teoria(teoria, {"DONCHIAN": {"canale_barre": np.int64(48)}, "ADX": {"periodo_barre": 24, "soglia": 20},
                                          "X3": {"durata_barre": 16, "perc_stop": 90, "target": 90}})
        check("20. stessa strategia da due strade (ordine delle chiavi, interi di numpy): stessa impronta",
              id_strategia(a, PERP, "M15") == id_strategia(s, PERP, "M15") == id_strategia(b2, PERP, "M15") and a == s)
        cambiata = Strategia.da_teoria(teoria, {"DONCHIAN": {"canale_barre": 49}, "ADX": {"periodo_barre": 24, "soglia": 20},
                                                "X3": {"durata_barre": 16, "perc_stop": 90, "target": 90}})
        check("21. un parametro cambiato, un altro symbol o timeframe, un altro lato: impronta diversa",
              len({id_strategia(s, PERP, "M15"), id_strategia(cambiata, PERP, "M15"), id_strategia(s, SPOT, "M15"),
                   id_strategia(s, PERP, "H1"), id_strategia(Strategia(-1, s.trigger, s.filtri, s.uscita, s.valori), PERP, "M15")}) == 5)
        check("22. valori per un blocco che la teoria non ha: errore", errore(lambda: Strategia.da_teoria(teoria, {"E47": {}})))
        check("23. Misure si scrive come dizionario", isinstance(m, Misure) and set(m.come_dict()) == {
            "trade", "totale_bp", "ev_bp", "t", "dd_bp", "peso_max", "totale_su_dd"})

        # ------------------------------------------------------------------ la velocità, da leggere
        n = 300
        rng = np.random.default_rng(31)
        strategie = [_casuale(perp["teorie"][int(rng.integers(len(perp["teorie"])))], blocchi, rng) for _ in range(n)]
        for x in strategie:
            v.valuta(x)                                  # prima passata: le soglie e le maschere entrano in cache
        t1 = time.perf_counter()
        for x in strategie:
            v.valuta(x)
        al_secondo = n / (time.perf_counter() - t1)
        check("24. velocità del percorso corto, cache calda (da leggere)", al_secondo > 0,
              f"{al_secondo:.0f} valutazioni al secondo su {len(perp['df']):,} barre".replace(",", "."))

    print("\n" + "=" * 70)
    print(f"Durata: {time.perf_counter() - t0:.0f} s")
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
