"""
Collaudo di condizioni_orarie.py: entry e uscite a orario (19/10/2026).

    A  i nomi: ORA_LONG_@HH:MM, ORA_SHORT_@HH:MM, X_ORA_@HH:MM, errori chiari,
       risolvi_scelta li registra da sola e controlla il lato
    B  gli orari esatti su un mercato finto con +3 pips ogni giorno fra le
       15:00 e le 16:00 di Londra: ORA_LONG_@15:00 + X_ORA_@16:00 apre alle
       15:00, chiude alle 16:00 e guadagna ~ +3 pips a trade
    C  l'ora legale: le 09:30 di New York restano le 09:30 tutto l'anno
    D  i timeframe: H1 rifiuta le 12:30; le H4 del broker partono dalle 17:00
       di New York e la griglia lo sa
    E  X_INVERSIONE_TREND: chiude solo all'ARRIVO di un'ora colorata contro,
       e il profilo resta congelato su dati nuovi
    F  lookahead e degenerazione (engine/collaudo_catalogo.py)
    G  il Lab: la regola oraria di imposta_uscite e i trigger da esplorare

Esecuzione:  python test_condizioni_orarie.py   (su Windows: PYTHONIOENCODING=utf-8)
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd

CARTELLA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CARTELLA)

import condizioni_orarie as co                                      # noqa: E402
from engine import registry as R                                    # noqa: E402
from engine.collaudo_catalogo import verifica_degenerazione, verifica_lookahead  # noqa: E402
from engine.exit_search_bt import run_exit_search_bt                # noqa: E402
from engine.stagionalita import codice_orario, griglia_oraria, profilo_orario  # noqa: E402
from entry_composita import risolvi_scelta                          # noqa: E402
from test_stagionalita import LONDRA, _df, _mercato_orario          # noqa: E402

DATI = os.path.join(CARTELLA, "dati", "EURUSD_M15.csv")
PIP = 0.0001


def _backtest(df, long=None, short=None, uscite=(None,), n_barre=40):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return run_exit_search_bt(df, entry_cols_long=[long], entry_cols_short=[short], n_barre=n_barre,
                                  exit_rule_pairs=list(uscite), perc_sl=0, perc_tp=0, spread=0.0,
                                  commission=0.0, cash=1_000_000, pip_size=PIP, verbose=False, min_trades=1)


def _locali(serie, fuso=LONDRA):
    return pd.DatetimeIndex(serie).tz_convert(fuso)


def main() -> int:
    ESITI: list[bool] = []

    def check(nome: str, condizione: bool, dettaglio: str = ""):
        ESITI.append(bool(condizione))
        stato = "OK  " if condizione else "FAIL"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def errore(funzione) -> str:
        try:
            funzione()
        except (ValueError, KeyError) as e:
            return str(e)
        return ""

    rng, idx, passi = _mercato_orario(3)
    df = _df(idx, passi, {})
    df["Volume"] = 100.0

    # =====================================================================
    print("\nA · I NOMI\n" + "-" * 70)
    R.clear_registry()
    co.imposta_fuso(LONDRA)
    check("A1. e_oraria riconosce ORA_LONG_@12:30 e ORA_SHORT_@09:05, non E1_RSI o ORA_L",
          co.e_oraria("ORA_LONG_@12:30") and co.e_oraria("ORA_SHORT_@09:05")
          and not co.e_oraria("E1_RSI_CROSS_OVERSOLD") and not co.e_oraria("ORA_L"))
    with contextlib.redirect_stdout(io.StringIO()):
        nome = risolvi_scelta("ORA_LONG_@15:00", lato="long")
    check("A2. risolvi_scelta registra da sola ORA_LONG_@15:00, direzione long",
          nome == "ORA_LONG_@15:00" and R.get_entry_direction(nome) == 1)
    msg = errore(lambda: risolvi_scelta("ORA_SHORT_@15:00", lato="long"))
    check("A3. ORA_SHORT_@ scelta come long si ferma (controllo del lato)", "SHORT" in msg, msg[:80])
    check("A4. orario impossibile (25:00) o scritto male si ferma con un messaggio chiaro",
          "non valido" in errore(lambda: co.registra_entry_oraria("ORA_LONG_@25:00"))
          and "ORA_LONG_@HH:MM" in errore(lambda: co.registra_entry_oraria("ORA_LONG_12:30")))
    check("A5. X_ORA: accetta 'X_ORA_@16:00' e '16:00', registra una coppia long/short",
          co.registra_uscita_oraria("16:00") == "X_ORA_@16:00"
          and co.registra_uscita_oraria("X_ORA_@16:00") == "X_ORA_@16:00"
          and ("X_ORA_@16:00", "X_ORA_@16:00_LONG", "X_ORA_@16:00_SHORT") in R.list_exit_pairs())

    # =====================================================================
    print("\nB · GLI ORARI ESATTI (effetto +3 pips fra le 15:00 e le 16:00 di Londra)\n" + "-" * 70)
    segnali = R.get_entry("ORA_LONG_@15:00")(df)
    ore = _locali(df.index[segnali.to_numpy()])
    check("B1. il segnale e' sulla candela delle 14:45 (il trade parte alle 15:00), una volta al giorno",
          bool(((ore.hour == 14) & (ore.minute == 45)).all())
          and pd.Series(ore.date).is_unique, f"{len(ore)} segnali")
    es = _backtest(df, long="ORA_LONG_@15:00", uscite=["X_ORA_@16:00", None])
    r = es.risultati.set_index("exit_rule_pair", drop=False)
    tr = es.trades(r.loc["X_ORA_@16:00", "combinazione"])
    ing, usc = _locali(tr["EntryTime"]), _locali(tr["ExitTime"])
    check("B2. i trade si aprono alle 15:00 e si chiudono alle 16:00 (4 candele)",
          bool(((ing.hour == 15) & (ing.minute == 0)).all() and ((usc.hour == 16) & (usc.minute == 0)).all()),
          f"{len(tr)} trade")
    g = float(r.loc["X_ORA_@16:00", "avg_trade_netto"])
    check("B3. guadagno medio a trade ~ +3 pips (l'effetto piazzato)", 2.5 < g < 3.5, f"{g:+.2f} pips")
    es_s = _backtest(df, short="ORA_SHORT_@15:00", uscite=["X_ORA_@16:00"])
    gs = float(es_s.risultati["avg_trade_netto"].iloc[0])
    check("B4. lo short alla stessa ora perde ~ 3 pips (stesso effetto, verso contrario)", -3.5 < gs < -2.5,
          f"{gs:+.2f} pips")

    # =====================================================================
    print("\nC · L'ORA LEGALE\n" + "-" * 70)
    ny = pd.date_range("2024-01-02", "2024-08-30", freq="15min", tz="UTC")
    dny = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0}, index=ny)
    co.imposta_fuso("America/New_York")
    s930 = co.registra_entry_oraria("ORA_LONG_@09:30")
    t = pd.DatetimeIndex(dny.index[R.get_entry(s930)(dny).to_numpy()])
    loc = t.tz_convert("America/New_York")
    inverno, estate = t[t.month == 1], t[t.month == 7]
    check("C1. segnale alle 09:15 di New York tutto l'anno (14:15 UTC d'inverno, 13:15 d'estate)",
          bool(((loc.hour == 9) & (loc.minute == 15)).all())
          and bool((inverno.hour == 14).all()) and bool((estate.hour == 13).all()))
    co.imposta_fuso(LONDRA)

    # =====================================================================
    print("\nD · I TIMEFRAME\n" + "-" * 70)
    h1 = pd.date_range("2024-01-01", periods=2000, freq="1h", tz="UTC")
    msg = errore(lambda: codice_orario("12:30", h1, LONDRA))
    check("D1. H1: le 12:30 non sono l'inizio di una candela, errore con gli orari possibili",
          "Orari possibili" in msg and "00:00" in msg, msg[:90])
    check("D2. H1: le 12:00 vanno bene", codice_orario("12:00", h1, LONDRA)[1] == 24)
    # come il server del broker: 00, 04, 08... ora server = 17, 21, 01... ora di New York tutto l'anno
    h4 = (pd.date_range("2024-01-07 17:00", periods=1500, freq="4h")
          .tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dropna().tz_convert("UTC"))
    _, larg, sfas = griglia_oraria(h4, "America/New_York")
    check("D3. H4 del broker (dalle 17:00 di New York): candele da 240 minuti, griglia sfasata di 60",
          larg == 240 and sfas == 60, f"{larg}, {sfas}")
    check("D4. H4: le 17:00 sono un orario valido, le 16:00 no",
          codice_orario("17:00", h4, "America/New_York")[1] == 6
          and "Orari possibili" in errore(lambda: codice_orario("16:00", h4, "America/New_York")))
    p4 = pd.DataFrame({"Open": np.linspace(1, 2, len(h4)), "Close": np.linspace(1, 2, len(h4)) + 1e-4}, index=h4)
    p4["High"], p4["Low"] = p4[["Open", "Close"]].max(axis=1), p4[["Open", "Close"]].min(axis=1)
    pr4 = profilo_orario(p4, 2, PIP, fuso="America/New_York", quarantena=False)
    check("D5. H4: 6 fasce con le ore vere delle candele (01, 05, 09, 13, 17, 21)",
          sorted(pr4["fascia"]) == ["01:00", "05:00", "09:00", "13:00", "17:00", "21:00"], str(list(pr4["fascia"])))

    # =====================================================================
    print("\nE · X_INVERSIONE_TREND\n" + "-" * 70)
    with contextlib.redirect_stdout(io.StringIO()):
        inv = co.registra_inversione_trend(df, 10, PIP, quarantena=False)
    contro = co.fasce_contro()
    prof = co.profilo_congelato()
    verdi = set(prof.loc[prof["bh"] & (prof["scarto_pips"] > 0), "fascia"])
    rosse = set(prof.loc[prof["bh"] & (prof["scarto_pips"] < 0), "fascia"])
    check("E1. coppia registrata; lo short si chiude all'arrivo delle ore verdi, il long delle rosse",
          inv == "X_INVERSIONE_TREND" and set(contro["short"]) == verdi and set(contro["long"]) == rosse
          and "14:30" in verdi, f"verdi {sorted(verdi)}")
    us = R.get_exit("X_INVERSIONE_TREND_SHORT")(df).to_numpy()
    ore_us = _locali(df.index[us])
    prossime = _locali(df.index[np.flatnonzero(us) + 1])
    check("E2. per lo short l'uscita scatta solo sulla candela prima della PRIMA ora verde di ogni gruppo",
          len(set(zip(ore_us.hour, ore_us.minute))) == 1
          and {f"{h:02d}:{m:02d}" for h, m in zip(prossime.hour, prossime.minute)} == {min(verdi)},
          f"si chiude alle {sorted({f'{h:02d}:{m:02d}' for h, m in zip(prossime.hour, prossime.minute)})}")
    es_i = _backtest(df, short="ORA_SHORT_@11:00" if co.registra_entry_oraria("ORA_SHORT_@11:00") else None,
                     uscite=["X_INVERSIONE_TREND"])
    tri = es_i.trades(es_i.risultati["combinazione"].iloc[0])
    chiusure = {f"{h:02d}:{m:02d}" for h, m in zip(_locali(tri["ExitTime"]).hour, _locali(tri["ExitTime"]).minute)}
    check("E3. short aperti alle 11:00 con X_INVERSIONE_TREND: chiusi all'arrivo della prima ora verde",
          chiusure == {min(verdi)}, str(sorted(chiusure)))
    _, idx2, passi2 = _mercato_orario(8, n=8000, effetto=0.0)
    df2 = _df(idx2, passi2, {})
    us2 = R.get_exit("X_INVERSIONE_TREND_SHORT")(df2).to_numpy()
    prossime2 = _locali(df2.index[np.flatnonzero(us2) + 1])
    check("E4. su dati nuovi (senza effetto) il profilo NON si ricalcola: stesse ore congelate",
          us2.any() and {f"{h:02d}:{m:02d}" for h, m in zip(prossime2.hour, prossime2.minute)} == {min(verdi)})

    # =====================================================================
    print("\nF · LOOKAHEAD E DEGENERAZIONE\n" + "-" * 70)
    nomi = ["ORA_LONG_@15:00", "ORA_SHORT_@11:00", "X_ORA_@16:00_LONG", "X_ORA_@16:00_SHORT",
            "X_INVERSIONE_TREND_LONG", "X_INVERSIONE_TREND_SHORT"]
    grezzo = df[["Open", "High", "Low", "Close", "Volume"]].iloc[:20000]
    with contextlib.redirect_stdout(io.StringIO()):
        rep = verifica_lookahead(grezzo, prepara=lambda d: d.copy(), tagli_per_condizione=6,
                                 riscaldamento=300, verbose=False).set_index("nome")
    esiti = {n: rep.loc[n, "esito"] for n in nomi}
    check("F1. nessun lookahead: le 6 condizioni orarie sono OK (esercitate)",
          all(e == "OK" for e in esiti.values()), str(esiti))
    with contextlib.redirect_stdout(io.StringIO()):
        deg = verifica_degenerazione(df, verbose=False).set_index("nome")
    giudizi = {n: deg.loc[n, "esito"] for n in nomi if n in deg.index}
    check("F2. nessuna condizione oraria degenere (mai vera, sempre vera o rara)",
          len(giudizi) == len(nomi) and all(e == "OK" for e in giudizi.values()), str(giudizi))

    # =====================================================================
    print("\nF bis · I 9 SYMBOL VERI (ultime 20000 barre)\n" + "-" * 70)
    from engine.stagionalita import fuso_profilo
    from test_algoxplorer import _leggi
    simboli = ["EURUSD", "GBPUSD", "USDJPY", "NZDUSD", "BTCUSD", "US500", "USTEC", "XAUUSD", "DE40"]
    for sym in simboli:
        if not os.path.exists(os.path.join(CARTELLA, "dati", f"{sym}_M15.csv")):
            print(f"  [SALT] F3. {sym}  — manca il CSV")
            continue
        with contextlib.redirect_stdout(io.StringIO()):
            vero = _leggi(sym).tail(20000)
            R.clear_registry()
            co.imposta_fuso(fuso_profilo(sym))
            for n in ("ORA_LONG_@10:00", "ORA_SHORT_@14:00"):
                co.registra_entry_oraria(n)
            co.registra_uscita_oraria("X_ORA_@16:00")
            co.registra_inversione_trend(vero, 25, PIP)
            rep = verifica_lookahead(vero[["Open", "High", "Low", "Close", "Volume"]], prepara=lambda d: d.copy(),
                                     tagli_per_condizione=4, riscaldamento=300, verbose=False).set_index("nome")
        esiti = {n: rep.loc[n, "esito"] for n in rep.index}
        # un'inversione senza ore colorate su quel symbol non scatta mai: NON_ESERCITATA, non un errore
        ok_sym = all(e == "OK" or (e == "NON_ESERCITATA" and n.startswith("X_INVERSIONE")) for n, e in esiti.items())
        check(f"F3. {sym}: nessun lookahead nelle condizioni orarie", ok_sym and len(esiti) == 6,
              ", ".join(f"{n.split('_@')[0] if '_@' in n else n}={e}" for n, e in esiti.items() if e != "OK"))
    co.imposta_fuso(LONDRA)
    R.clear_registry()
    with contextlib.redirect_stdout(io.StringIO()):
        co.registra_inversione_trend(df, 10, PIP, quarantena=False)

    # =====================================================================
    print("\nG · IL LAB\n" + "-" * 70)
    from engine import vetrina as V
    s = SimpleNamespace(df_is=df, H=10, pip=PIP, fuso=LONDRA)
    with contextlib.redirect_stdout(io.StringIO()):
        esiti_g = [V._regola_oraria(s, "nessuna"), V._regola_oraria(s, None),
                   V._regola_oraria(s, "X_ORA_@16:00"), V._regola_oraria(s, "X_INVERSIONE_TREND")]
    check("G1. imposta_uscite: «nessuna» = None, X_ORA_@16:00 e X_INVERSIONE_TREND registrate",
          esiti_g == [None, None, "X_ORA_@16:00", "X_INVERSIONE_TREND"])
    check("G2. orario non valido o regola sconosciuta: errore chiaro",
          "Orari possibili" in errore(lambda: V._regola_oraria(s, "X_ORA_@16:07"))
          and "sconosciuta" in errore(lambda: V._regola_oraria(s, "X_INESISTENTE")))
    R.register_entry("E_FINTA", 1)(lambda d: pd.Series(False, index=d.index))
    cand = V._trigger_candidati()
    check("G3. le entry a orario non finiscono fra i trigger da esplorare (si scelgono a mano)",
          "E_FINTA" in cand and not any(co.e_oraria(n) for n in cand))
    R.clear_registry()

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(main())
