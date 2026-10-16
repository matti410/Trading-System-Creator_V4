"""
Suite di validazione di engine/simboli.py e del pip fisso per symbol (10/10/2026).

Il pip era dedotto dal prezzo medio: su US500 valeva 0,01 nella parte
in-sample e 1,0 in quella out-of-sample. Ora e' fisso, da una tabella
scritta a mano, e viaggia nel dizionario dei costi fino ai motori.

  A  la tabella: valori, symbol sconosciuto, nessun bisogno di MT5
  B  US500 sintetico che attraversa 5.000: stesso pip in-sample e out-of-sample
  C  coerenza fra pip e passo di prezzo dei CSV in dati/ (saltato se manca):
     il pip deve essere il passo per una potenza di 10. Non un rapporto
     fisso: USTEC ha 2 cifre in MT5 ma nei dati quota sempre a passi di 0,1
  D  coerenza fra la tabella e MT5: cifre, contratto, valuta (saltato se MT5 manca)
  F  nozionale senza MT5: XAUUSD 100 once, EURUSD come prima (correzione 2)
  G  indici riconosciuti dal nome senza MT5 (correzione 3)
  H  valore di 1 pip per 1 lotto su oro e indici (correzione 4)
  I  spread di listino per il notebook: riga mancante -> messaggio con la riga
     esatta e il rollover proposto dai dati (10/10/2026)
  J  vetrina (Trading_System_Lab) allineata al notebook principale: symbol
     della tabella, cartella dei dati, fuso dei non forex su EURUSD, cambio
     di DE40 (11/10/2026)
  E  identita' su EURUSD e BTCUSD: parametri_backtest, event study,
     run_exit_search_bt e run_filter_search_bt danno numeri identici col pip
     dedotto (il comportamento di prima) e col pip della tabella

Si lancia da terminale, dalla cartella del progetto:

    python test_simboli.py

Usa i CSV EURUSD_M15.csv e BTCUSD_M15.csv della cartella principale (sono nel
repo). MT5 e la cartella dati/ servono solo a C e D, che si saltano da soli.
Richiede backtesting==0.6.6. Dura circa un minuto.
"""
from __future__ import annotations

import contextlib
import io
import shutil
import subprocess
import tempfile
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from engine.broker_tz_diagnostic import to_utc_index
from engine.collaudo_catalogo import mercato_sintetico
from engine.costi import classifica_simbolo, nozionale_senza_mt5, parametri_backtest
from engine.event_study import deduci_pip, run_event_study
from engine.exit_search_bt import run_exit_search_bt
from engine.filter_search_bt import run_filter_search_bt
from engine.montecarlo import valore_pip_lotto
from engine.registry import clear_registry, register_entry, register_filter
from engine.simboli import (LEVA, LOTTI, SIMBOLI, info_symbol, leva_symbol, lotti_symbol,
                            pip_symbol)
from engine import vetrina as _vetrina
from engine.vetrina import _punto_da_prezzi, _punto_symbol, proposta_rollover, spread_listino
from engine.livelli import svuota_cache

warnings.simplefilter("ignore")

QUI = Path(__file__).resolve().parent
# pip / punto MT5 atteso per classe: "10 punti" forex e oro, "100 punti" indici e crypto
MOLTIPLICATORE = {"forex": 10, "metalli": 10, "indici": 100, "crypto": 100}


def _muto(funzione, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return funzione(*a, **k)


def _uguali(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    try:
        pd.testing.assert_frame_equal(a, b, check_exact=True)
        return True
    except AssertionError:
        return False


def _carica(nome: str, anno: int) -> pd.DataFrame:
    df = pd.read_csv(QUI / nome, index_col="Date")
    df = _muto(to_utc_index, df, "A_US_DST (NY+7h)", on_dst_gap="drop", verbose=False)
    return df[df.index.year == anno]


def _carica_dati(percorso: Path) -> pd.DataFrame:
    df = pd.read_csv(percorso, index_col="Date")
    return _muto(to_utc_index, df, "A_US_DST (NY+7h)", on_dst_gap="drop", verbose=False)


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def saltato(nome, motivo):
        print(f"  [SALTATO] {nome}  — {motivo}")

    # ------------------------------------------------------------ tabella --
    print("\nA · La tabella dei symbol")
    attesi = {"EURUSD": 0.0001, "GBPUSD": 0.0001, "NZDUSD": 0.0001, "USDJPY": 0.01,
              "XAUUSD": 0.10, "US500": 1.0, "USTEC": 1.0, "DE40": 1.0, "BTCUSD": 1.0}
    trovati = {s: pip_symbol(s) for s in attesi}
    check("1. pip dei 9 symbol: forex 0,0001 (JPY 0,01), oro 0,10, indici e BTCUSD 1",
          trovati == attesi, " · ".join(f"{s}={p:g}" for s, p in trovati.items()))
    check("2. il nome si legge anche in minuscolo", pip_symbol("eurusd") == 0.0001)
    try:
        pip_symbol("XYZABC")
        fermo, msg = False, ""
    except KeyError as e:
        fermo, msg = True, str(e)
    check("3. symbol sconosciuto -> errore con l'istruzione, nessun pip indovinato",
          fermo and "Aggiungi una riga" in msg)
    import_pulito = subprocess.run(
        [sys.executable, "-c",
         "import sys, engine.simboli; print('MetaTrader5' in sys.modules)"],
        cwd=QUI, capture_output=True, text=True).stdout.strip() == "False"
    check("4. engine/simboli.py non importa MetaTrader5 (gira su Colab)", import_pulito)
    try:
        _muto(parametri_backtest, "XYZABC", prezzo=1.0, usa_mt5=False, spread_pips=1.0)
        fermo = False
    except KeyError:
        fermo = True
    check("5. parametri_backtest su un symbol fuori tabella si ferma", fermo)

    # 16/10/2026: tabella dei lotti (fase 0 del money management, docs/61)
    attesi_lotti = {"EURUSD": (0.01, 0.01, 200.0), "GBPUSD": (0.01, 0.01, 200.0),
                    "NZDUSD": (0.01, 0.01, 100.0), "USDJPY": (0.01, 0.01, 200.0),
                    "XAUUSD": (0.01, 0.01, 100.0), "US500": (0.1, 0.1, 250.0),
                    "USTEC": (0.1, 0.1, 250.0), "DE40": (0.1, 0.1, 250.0),
                    "BTCUSD": (0.01, 0.01, 10.0)}
    check("5b. LOTTI: stessi symbol di SIMBOLI", set(LOTTI) == set(SIMBOLI))
    check("5c. LOTTI: minimo, passo e massimo dei 9 symbol (letti da MT5 il 16/10)",
          {s: tuple(lotti_symbol(s).values()) for s in attesi_lotti} == attesi_lotti)
    coerenti = all(0 < m <= x and p > 0 and np.isclose(m / p, round(m / p))
                   and np.isclose(x / p, round(x / p)) for m, p, x in LOTTI.values())
    check("5d. LOTTI coerenti: minimo e massimo sono multipli del passo, minimo <= massimo",
          coerenti)
    try:
        lotti_symbol("XYZABC")
        fermo, msg = False, ""
    except KeyError as e:
        fermo, msg = True, str(e)
    check("5e. lotti di un symbol sconosciuto -> errore con l'istruzione",
          fermo and "Aggiungi" in msg)
    check("5g. LEVA: stessi symbol di SIMBOLI, schema retail europeo 30 / 20 / 2",
          set(LEVA) == set(SIMBOLI)
          and {s: leva_symbol(s) for s in LEVA} == {
              "EURUSD": 30, "GBPUSD": 30, "USDJPY": 30, "NZDUSD": 20, "XAUUSD": 20,
              "US500": 20, "USTEC": 20, "DE40": 20, "BTCUSD": 2})
    try:
        leva_symbol("XYZABC")
        fermo = False
    except KeyError:
        fermo = True
    check("5h. leva di un symbol sconosciuto -> errore", fermo)
    check("5f. lotti_symbol legge anche il minuscolo",
          lotti_symbol("de40") == {"minimo": 0.1, "passo": 0.1, "massimo": 250.0})

    # ----------------------------------------------- US500 attraverso 5000 --
    print("\nB · US500 sintetico da 4.000 a 6.000: il pip non cambia con il prezzo")
    df = mercato_sintetico("2024-01-01", "2024-07-01", seme=5, prezzo=4000.0, vol_barra=0.3,
                           gap_open=0.1)
    trend = np.linspace(1.0, 1.5, len(df))
    for col in ("Open", "High", "Low", "Close"):
        df[col] = df[col] * trend
    taglio = int(len(df) * 0.8)
    df_is, df_oos = df.iloc[:taglio], df.iloc[taglio:]
    check("6. prima: il pip dedotto cambiava fra in-sample e out-of-sample",
          deduci_pip(float(df_is["Close"].mean())) == 0.01
          and deduci_pip(float(df_oos["Close"].mean())) == 1.0,
          f"prezzo medio {df_is['Close'].mean():,.0f} e {df_oos['Close'].mean():,.0f}")
    c_is = _muto(parametri_backtest, "US500", bars=df_is, usa_mt5=False, spread_pips=0.5)
    c_oos = _muto(parametri_backtest, "US500", bars=df_oos, usa_mt5=False, spread_pips=0.5)
    check("7. parametri_backtest: pip 1 in tutte e due le parti, nel dizionario dei costi",
          c_is["pip_size"] == 1.0 and c_oos["pip_size"] == 1.0)
    check("8. lo spread di 0,5 pips vale 0,5 punti di indice, non 0,005",
          np.isclose(c_is["spread"] * float(df_is["Close"].median()), 0.5))
    clear_registry()
    segnali = pd.Series(np.random.default_rng(1).random(len(df)), index=df.index)
    register_entry("T_SIM_LONG", 1)(lambda d: segnali.reindex(d.index) < 0.01)
    fs_is = _muto(run_filter_search_bt, df_is, entry_long="T_SIM_LONG", filtri=[],
                  n_barre=8, cash=1e7, min_trades=1, **c_is)
    fs_oos = _muto(run_filter_search_bt, df_oos, entry_long="T_SIM_LONG", filtri=[],
                   n_barre=8, cash=1e7, min_trades=1, **c_oos)
    check("9. run_filter_search_bt con **costi: pip 1 in-sample e out-of-sample",
          fs_is.pip_size == 1.0 and fs_oos.pip_size == 1.0)
    clear_registry()

    # -------------------------------------------- coerenza con i dati CSV --
    print("\nC · Pip e passo di prezzo dei CSV in dati/")
    for sym, (classe, pip, *_resto) in SIMBOLI.items():
        f = QUI / "dati" / f"{sym}_M15.csv"
        if not f.exists():
            saltato(f"C {sym}", "dati/ non c'e' (es. Colab)")
            continue
        close = pd.read_csv(f, usecols=["Close"])["Close"]
        punto = _punto_da_prezzi(close)
        esponente = np.log10(pip / punto)
        check(f"C {sym}: pip = passo di prezzo x una potenza di 10",
              esponente > -1e-9 and np.isclose(esponente, round(esponente)),
              f"pip {pip:g} · passo nei dati {punto:g} · pip = {pip / punto:g} passi")

    # ------------------------------------------------- coerenza con MT5 --
    print("\nD · La tabella contro MT5 (sola lettura: symbol_info)")
    mt5 = None
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            mt5 = None
    except Exception:
        mt5 = None
    if mt5 is None:
        saltato("D", "MT5 non disponibile")
    else:
        try:
            for sym in SIMBOLI:
                i = mt5.symbol_info(sym)
                if i is None:
                    saltato(f"D {sym}", "symbol non presente nel terminale")
                    continue
                t = info_symbol(sym)
                check(f"D {sym}: cifre, contratto, valuta e pip = {MOLTIPLICATORE[t['classe']]} punti",
                      i.digits == t["cifre"]
                      and np.isclose(i.trade_contract_size, t["contratto"])
                      and i.currency_profit == t["valuta"]
                      and np.isclose(t["pip"], MOLTIPLICATORE[t["classe"]] * 10.0 ** -i.digits),
                      f"MT5: {i.digits} cifre · contratto {i.trade_contract_size:g} · {i.currency_profit}")
                lt = lotti_symbol(sym)
                check(f"D {sym}: lotto minimo, passo e massimo come in MT5",
                      np.isclose(i.volume_min, lt["minimo"])
                      and np.isclose(i.volume_step, lt["passo"])
                      and np.isclose(i.volume_max, lt["massimo"]),
                      f"MT5: {i.volume_min:g} / {i.volume_step:g} / {i.volume_max:g}")
        finally:
            mt5.shutdown()      # chiude la connessione di Python, non il terminale

    # ---------------------------------------- identita' EURUSD e BTCUSD --
    print("\nE · EURUSD e BTCUSD: numeri identici prima (pip dedotto) e dopo (pip della tabella)")
    casi = {"EURUSD": ("EURUSD_M15.csv", 0.8, None),   # 7 $ round-turn: passa dal nozionale
            "BTCUSD": ("BTCUSD_M15.csv", 12.58, None)}
    for sym, (nome, spread_pips, comm) in casi.items():
        d = _carica(nome, 2024)
        mediano = float(d["Close"].median())
        prima = _muto(parametri_backtest, sym, bars=d, usa_mt5=False, spread_pips=spread_pips,
                      commissione_rt=comm, pip_size=deduci_pip(mediano))
        dopo = _muto(parametri_backtest, sym, bars=d, usa_mt5=False, spread_pips=spread_pips,
                     commissione_rt=comm)
        check(f"E {sym} 1. parametri_backtest: spread e commission identici al bit",
              prima["spread"] == dopo["spread"] and prima["commission"] == dopo["commission"]
              and dopo["pip_size"] == deduci_pip(float(d["Close"].mean())),
              f"pip {dopo['pip_size']:g} · spread {dopo['spread']:.6e} · commission {dopo['commission']:.6e}")

        clear_registry()
        rng = np.random.default_rng(7)
        s = pd.Series(rng.random(len(d)), index=d.index)
        register_entry("T_ID_LONG", 1)(lambda x, s=s: s.reindex(x.index) < 0.006)
        register_entry("T_ID_SHORT", -1)(lambda x, s=s: s.reindex(x.index) > 0.994)
        register_filter("F_ID_SOPRA_MEDIA")(
            lambda x: x["Close"] > x["Close"].rolling(96, min_periods=96).mean())

        ev_prima = _muto(run_event_study, d, entry_names=["T_ID_LONG", "T_ID_SHORT"],
                         horizon=12, min_trades=0, pip=None, verbose=False)
        ev_dopo = _muto(run_event_study, d, entry_names=["T_ID_LONG", "T_ID_SHORT"],
                        horizon=12, min_trades=0, pip=pip_symbol(sym), verbose=False)
        check(f"E {sym} 2. event study: sintesi identica",
              ev_prima.pip == ev_dopo.pip and _uguali(ev_prima.sintesi, ev_dopo.sintesi))

        costi_prima = {"spread": prima["spread"], "commission": prima["commission"]}
        comuni = dict(cash=1e8, spread_rollover_pips=spread_pips * 2, n_barre=12,
                      perc_sl=90.0, verbose=False)
        es_prima = _muto(run_exit_search_bt, d, entry_cols_long=["T_ID_LONG"],
                         entry_cols_short=["T_ID_SHORT"], **comuni, **costi_prima)
        es_dopo = _muto(run_exit_search_bt, d, entry_cols_long=["T_ID_LONG"],
                        entry_cols_short=["T_ID_SHORT"], **comuni, **dopo)
        check(f"E {sym} 3. run_exit_search_bt: tabella dei risultati identica",
              _uguali(es_prima.risultati, es_dopo.risultati),
              f"{int(es_dopo.risultati['trades'].iat[0])} trade")

        fs_prima = _muto(run_filter_search_bt, d, entry_long="T_ID_LONG", entry_short="T_ID_SHORT",
                         filtri=["F_ID_SOPRA_MEDIA"], **comuni, **costi_prima)
        fs_dopo = _muto(run_filter_search_bt, d, entry_long="T_ID_LONG", entry_short="T_ID_SHORT",
                        filtri=["F_ID_SOPRA_MEDIA"], **comuni, **dopo)
        trade_uguali = all(_uguali(fs_prima.trades(e), fs_dopo.trades(e))
                           for e in (None, "F_ID_SOPRA_MEDIA"))
        check(f"E {sym} 4. run_filter_search_bt: risultati, trade e pip identici",
              fs_prima.pip_size == fs_dopo.pip_size
              and _uguali(fs_prima.risultati, fs_dopo.risultati) and trade_uguali,
              f"pip {fs_dopo.pip_size:g} · {len(fs_dopo.trades())} trade nella baseline")
        clear_registry()

    # ------------------------------------------- nozionale dei metalli --
    print("\nF · Nozionale senza MT5: i metalli non sono piu' trattati come forex")
    check("F1. XAUUSD: nozionale = 100 once x prezzo",
          nozionale_senza_mt5("XAUUSD", 2000.0) == 200_000.0)
    c_oro = _muto(parametri_backtest, "XAUUSD", prezzo=2000.0, usa_mt5=False, spread_pips=1.0)
    costo_rt = c_oro["commission"] * 2 * 2000.0
    check("F2. XAUUSD: 7 $ per lotto = 0,07 $ per oncia = 0,7 pips da 0,10 $",
          np.isclose(costo_rt, 0.07) and np.isclose(costo_rt / c_oro["pip_size"], 0.7),
          f"{costo_rt:.4f} $ di prezzo · {costo_rt / c_oro['pip_size']:.3f} pips")
    check("F3. EURUSD: nozionale invariato (100.000 x prezzo in USD, 100.000 in EUR)",
          nozionale_senza_mt5("EURUSD", 1.1) == 100_000.0 * 1.1
          and nozionale_senza_mt5("EURUSD", 1.1, "EUR") == 100_000.0)
    def _ferma(*a):
        try:
            nozionale_senza_mt5(*a)
            return False
        except ValueError:
            return True
    check("F4. errore chiaro: 6 lettere non forex, metallo fuori tabella, oro con conto EUR",
          _ferma("ABCDEF", 1.0) and _ferma("XAUEUR", 1.0) and _ferma("XAUUSD", 2000.0, "EUR"))

    # ---------------------------------------------------- classe indici --
    print("\nG · Indici riconosciuti dal nome, senza MT5")
    attese = {"US500": "indici", "USTEC": "indici", "DE40": "indici", "EURUSD": "forex",
              "USDJPY": "forex", "BTCUSD": "crypto", "XAUUSD": "metalli",
              "US30": "altro", "ABCDEF": "altro"}
    trovate = {s: classifica_simbolo(s) for s in attese}
    check("G1. US500, USTEC, DE40 -> indici; gli altri come prima; fuori tabella -> altro",
          trovate == attese, " · ".join(f"{s}={c}" for s, c in trovate.items()))
    check("G2. col path di MT5 decide il path, come prima",
          classifica_simbolo("US500", "Indices\\Indices Spot\\US500") == "indici"
          and classifica_simbolo("XAUUSD", "Commodities\\Metals\\XAUUSD") == "metalli")
    c_ind = _muto(parametri_backtest, "US500", prezzo=5000.0, usa_mt5=False, spread_pips=0.5)
    check("G3. US500: commissione zero, come quando era 'altro'", c_ind["commission"] == 0.0)

    # ------------------------------------------ valore del pip per lotto --
    print("\nH · Valore di 1 pip per 1 lotto")
    check("H1. XAUUSD: 100 once x 0,10 $ = 10 $",
          np.isclose(valore_pip_lotto("XAUUSD", pip_symbol("XAUUSD")), 10.0))
    check("H2. US500 e USTEC: contratto 1 x 1 punto = 1 $",
          np.isclose(valore_pip_lotto("US500", 1.0), 1.0)
          and np.isclose(valore_pip_lotto("USTEC", 1.0), 1.0))
    try:
        valore_pip_lotto("DE40", 1.0)
        fermo = False
    except ValueError:
        fermo = True
    check("H3. DE40 quotato in EUR: senza cambio si ferma, con cambio 1,12 vale 1,12 $",
          fermo and np.isclose(valore_pip_lotto("DE40", 1.0, cambio=1.12), 1.12))
    check("H4. EURUSD, BTCUSD, USDJPY: come prima (10 $, 1 $, 100.000 x 0,01 / prezzo)",
          np.isclose(valore_pip_lotto("EURUSD", 0.0001), 10.0)
          and np.isclose(valore_pip_lotto("BTCUSD", 1.0), 1.0)
          and np.isclose(valore_pip_lotto("USDJPY", 0.01, prezzo=150.0), 100_000 * 0.01 / 150))

    # --------------------------------------------- spread di listino --
    print("\nI · Spread di listino per il notebook")
    sl = spread_listino("EURUSD", pd.DataFrame())
    check("I1. EURUSD: 0,8 e 1,5 pips dal listino, come prima",
          (sl["normale"], sl["rollover"]) == (0.8, 1.5))
    sint = mercato_sintetico("2024-08-01", "2024-12-01", seme=3)
    svuota_cache()
    from engine.quarantena import quarantena as _q
    qq = _muto(_q, sint)["totale"].to_numpy()
    sint["spread"] = np.where(qq, 23.0, 0.0)          # 23 punti = 2,3 pips solo in quarantena
    riga_gbp = _vetrina.SPREAD_LISTINO_PIPS.pop("GBPUSD")   # dall'11/10 c'e': la si toglie per la prova
    try:
        spread_listino("GBPUSD", sint)
        msg = ""
    except ValueError as e:
        msg = str(e)
    check("I2. GBPUSD senza riga: si ferma e dice la riga esatta, rollover 2,3 dai dati",
          '"GBPUSD":' in msg and '"normale": ...' in msg and '"rollover": 2.3' in msg
          and "engine/vetrina.py" in msg, msg.strip().splitlines()[-1].strip() if msg else "")
    svuota_cache()
    sint["spread"] = 0.0
    try:
        spread_listino("GBPUSD", sint)
        msg = ""
    except ValueError as e:
        msg = str(e)
    check("I3. colonna spread a zero: rollover None e la spiegazione",
          '"rollover": None' in msg and "non significativa" in msg
          and proposta_rollover("GBPUSD", sint) is None)
    _vetrina.SPREAD_LISTINO_PIPS["GBPUSD"] = riga_gbp
    svuota_cache()
    righe = _vetrina.SPREAD_LISTINO_PIPS
    check("I6. ogni symbol di engine/simboli.py ha la riga di listino, rollover >= normale o None",
          all(s in righe for s in SIMBOLI)
          and all(v["rollover"] is None or v["rollover"] >= v["normale"] for v in righe.values()),
          " · ".join(f"{s} {v['normale']:g}/{v['rollover']}" for s, v in righe.items()))
    check("I7. EURUSD invariato: 0,8 normale e 1,5 rollover",
          righe["EURUSD"] == {"normale": 0.8, "rollover": 1.5})
    check("I4. il punto MT5 viene dalle cifre della tabella (USTEC 0,01 anche se quota a 0,1)",
          _punto_symbol("USTEC", pd.Series([20000.1, 20000.3])) == 0.01
          and _punto_symbol("XXXUSD", pd.Series([1.10123, 1.10456])) == 1e-5)
    f = QUI / "dati" / "USTEC_M15.csv"
    if f.exists():
        d = _carica_dati(f)
        check("I5. USTEC vero: rollover proposto 2 punti (prima, col passo dei prezzi, 20)",
              proposta_rollover("USTEC", d) == 2.0, f"{proposta_rollover('USTEC', d)}")
        svuota_cache()
    else:
        saltato("I5", "dati/ non c'e' (es. Colab)")

    # ------------------------------------------- vetrina multi-symbol --
    print("\nJ · La vetrina (Trading_System_Lab) allineata al notebook principale")
    try:
        _muto(_vetrina.prepara, "GBPAUD", cartella=str(QUI / "dati"))
        fermo = False
    except KeyError:
        fermo = True
    check("J1. strumento fuori da engine/simboli.py: prepara si ferma subito", fermo)
    s_eur = _muto(_vetrina.prepara, "EURUSD", H=25)
    check("J2. EURUSD dalla cartella principale come prima: 0,8 / 1,5 pips, pip 0,0001, nessun cambio",
          (s_eur.spread_pips, s_eur.spread_rollover_pips, s_eur.pip) == (0.8, 1.5, 0.0001)
          and _vetrina._cambio_ultima_barra(s_eur) is None and s_eur.cartella == ".")
    dati = QUI / "dati"
    if (dati / "DE40_M15.csv").exists() and (dati / "EURUSD_M15.csv").exists():
        s_de = _muto(_vetrina.prepara, "DE40", H=25, cartella=str(dati))
        eur = _carica_dati(dati / "EURUSD_M15.csv")
        atteso = float(eur["Close"].loc[:s_de.df.index[-1]].iloc[-1])
        check("J3. DE40 da dati/: listino 1,5 / 6,5 punti, pip 1, cambio EURUSD dell'ultima barra",
              (s_de.spread_pips, s_de.spread_rollover_pips, s_de.pip) == (1.5, 6.5, 1.0)
              and _vetrina._cambio_ultima_barra(s_de) == atteso, f"cambio {atteso:.5f}")
        cartella_sola = Path(tempfile.mkdtemp())
        try:
            shutil.copy(dati / "DE40_M15.csv", cartella_sola)
            try:
                _muto(_vetrina.prepara, "DE40", cartella=str(cartella_sola))
                msg = ""
            except FileNotFoundError as e:
                msg = str(e)
        finally:
            shutil.rmtree(cartella_sola, ignore_errors=True)
        check("J4. DE40 senza EURUSD nella cartella: si ferma e dice che serve EURUSD per il fuso",
              "EURUSD_M15.csv" in msg and "fuso" in msg)
    else:
        saltato("J3-J4", "dati/ non c'e' (es. Colab)")
    svuota_cache()

    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
