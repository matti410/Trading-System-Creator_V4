"""
Collaudo di engine/famiglie.py (sovrapposizioni, somiglianze, famiglie di
condizioni; docs/50 §7.5, decisione di Mattia del 17/10/2026: famiglia a
somiglianza media >= 60%).

Sezioni:

    A  casi a risultato noto su condizioni costruite a mano: copia spostata di
       una barra, sottoinsieme, condizione indipendente, filtro larghissimo
       (il 70% raggiunto per caso non fa somiglianza), spostamento oltre la
       finestra, soglia della famiglia, piu' symbol (vale il minimo)
    B  i numeri contro un conteggio a mano, barra per barra
    C  il catalogo vero su EURUSD in-sample: le famiglie attese per costruzione
       (pattern confermati dentro la base, harami cross dentro harami, volume)

Si lancia da terminale, dalla cartella del progetto:

    python test_famiglie.py

(su Windows: PYTHONIOENCODING=utf-8). La sezione C gira solo se c'e'
dati/EURUSD_M15.csv; se manca viene SALTATA e lo dice. Non serve MT5.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.simplefilter(action="ignore", category=FutureWarning)

from engine import registry as R
from engine.famiglie import famiglie, somiglianze, sovrapposizioni

CARTELLA = os.path.dirname(os.path.abspath(__file__))
DATI = os.path.join(CARTELLA, "dati", "EURUSD_M15.csv")


def _sintetico(seme: int, n: int = 20000) -> pd.DataFrame:
    rng = np.random.default_rng(seme)
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    a = rng.random(n) < 0.02
    meta = a & (rng.random(n) < 0.5)
    b = rng.random(n) < 0.02
    return pd.DataFrame({
        "A": a, "A_SPOSTATA": np.r_[False, a[:-1]], "A_META": meta, "B": b,
        "A_LONTANA": np.r_[[False] * 5, a[:-5]],
        "F_LARGO": rng.random(n) < 0.85, "F_X": rng.random(n) < 0.20,
        "F_DENTRO": np.zeros(n, dtype=bool)}, index=idx)


def _registra_finte():
    R.clear_registry()
    for k in ("A", "A_SPOSTATA", "A_META", "B", "A_LONTANA"):
        R.register_entry(k, 1)(lambda df, k=k: df[k])
    for k in ("F_LARGO", "F_X"):
        R.register_filter(k)(lambda df, k=k: df[k])


def main() -> int:
    ESITI: list[bool] = []

    def check(nome: str, condizione: bool, dettaglio: str = ""):
        ESITI.append(bool(condizione))
        stato = "OK  " if condizione else "FAIL"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def saltato(nome: str, motivo: str):
        print(f"  [SALT] {nome}  — {motivo}")

    # =====================================================================
    print("\nA · CASI A RISULTATO NOTO\n" + "-" * 70)
    df = _sintetico(1)
    _registra_finte()
    fam = famiglie(df, "entry").set_index("nome")
    f = fam["famiglia"]
    check("A1. copia spostata di una barra e sottoinsieme: stessa famiglia della condizione d'origine",
          f["A"] == f["A_SPOSTATA"] == f["A_META"], str(f.to_dict()))
    check("A2. condizione indipendente e copia spostata di 5 barre (oltre la finestra di 2): famiglie proprie",
          len({f["A"], f["B"], f["A_LONTANA"]}) == 3 and fam.loc["B", "membri"] == 1)
    # coppia isolata P, Q: Q prende il 62% degli eventi di P, gli altri suoi eventi lontani da P
    rng = np.random.default_rng(3)
    n = 20000
    p = rng.random(n) < 0.02
    q = p & (rng.random(n) < 0.62)
    vicino_p = np.convolve(p, np.ones(7), mode="same") > 0
    liberi = np.flatnonzero(~vicino_p)
    q[rng.choice(liberi, int(p.sum()) - int(q.sum()), replace=False)] = True
    coppia = pd.DataFrame({"P": p, "Q": q}, index=pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC"))
    R.clear_registry()
    for k in ("P", "Q"):
        R.register_entry(k, 1)(lambda d, k=k: d[k])
    s_pq = float(somiglianze(coppia, "entry").loc["P", "Q"])
    f60 = famiglie(coppia, "entry", soglia=0.60)["famiglia"].nunique()
    f70 = famiglie(coppia, "entry", soglia=0.70)["famiglia"].nunique()
    check("A3. somiglianza fra 60% e 70%: una famiglia sola con soglia 60%, due con soglia 70%",
          0.60 <= s_pq < 0.70 and f60 == 1 and f70 == 2, f"somiglianza {100 * s_pq:.1f}%")
    _registra_finte()
    check("A4. la piu' vicina di A_META e' una copia di A, al 100%",
          fam.loc["A_META", "piu_vicina"] in ("A", "A_SPOSTATA") and fam.loc["A_META", "somiglianza"] == 100.0)
    ff = famiglie(df, "filtro").set_index("nome")
    sv = sovrapposizioni(df, "filtro")
    riga = sv[(sv["contenuta"] == "F_X") & (sv["dentro"] == "F_LARGO")]
    check("A5. filtro dentro un filtro larghissimo all'85% per caso: niente doppione, niente famiglia",
          len(riga) == 1 and riga["quota_min"].iloc[0] > 80 and not riga["doppione"].iloc[0]
          and ff.loc["F_X", "famiglia"] != ff.loc["F_LARGO", "famiglia"] and ff.loc["F_X", "somiglianza"] == 0,
          f"quota {riga['quota_min'].iloc[0] if len(riga) else '-'}%, lift {riga['lift_min'].iloc[0] if len(riga) else '-'}")
    sv_e = sovrapposizioni(df, "entry")
    dop = {(a, b) for a, b in sv_e.loc[sv_e["doppione"], ["contenuta", "dentro"]].itertuples(index=False)}
    check("A6. doppioni: A_META dentro A e A dentro A_SPOSTATA si', A dentro A_META no (solo meta' degli eventi)",
          ("A_META", "A") in dop and ("A", "A_SPOSTATA") in dop and ("A", "A_META") not in dop)
    check("A7. finestra 0 sulle entry: la copia spostata di una barra non e' piu' simile",
          famiglie(df, "entry", finestra=0).set_index("nome")["famiglia"]["A_SPOSTATA"]
          != famiglie(df, "entry", finestra=0).set_index("nome")["famiglia"]["A"])
    # piu' symbol: nel secondo "A_SPOSTATA" e' indipendente -> la somiglianza vale il minimo
    df2 = _sintetico(2)
    df2["A_SPOSTATA"] = np.random.default_rng(9).random(len(df2)) < 0.02
    multi = famiglie({"S1": df, "S2": df2}, "entry").set_index("nome")
    check("A8. due symbol: simili solo se lo sono su entrambi (vale il minimo)",
          multi.loc["A", "famiglia"] != multi.loc["A_SPOSTATA", "famiglia"]
          and multi.loc["A", "famiglia"] == multi.loc["A_META", "famiglia"]
          and {"vere_S1", "vere_S2"} <= set(multi.columns))
    sim = somiglianze(df, "entry")
    check("A9. matrice di somiglianza simmetrica, 1 sulla diagonale, valori fra 0 e 1",
          np.allclose(sim.to_numpy(), sim.to_numpy().T) and (np.diag(sim) == 1).all()
          and sim.to_numpy().min() >= 0 and sim.to_numpy().max() <= 1)
    check("A10. famiglie numerate dalla piu' numerosa e risultato ripetibile",
          fam["membri"].groupby(fam["famiglia"]).first().is_monotonic_decreasing
          and famiglie(df, "entry").equals(famiglie(df, "entry")))
    R.clear_registry()

    # =====================================================================
    print("\nB · I NUMERI CONTRO UN CONTEGGIO A MANO\n" + "-" * 70)
    _registra_finte()
    sv_tutte = sovrapposizioni(df, "entry", mostra_da=0.0).set_index(["contenuta", "dentro"])
    ok = True
    v = {k: df[k].to_numpy() for k in ("A", "B", "A_META", "A_LONTANA")}
    for a, b in (("A_META", "A"), ("A", "B"), ("A_LONTANA", "A_META")):
        intorno = np.zeros(len(df), dtype=bool)
        for i in np.flatnonzero(v[b]):
            intorno[max(i - 2, 0):i + 3] = True
        quota = 100 * (v[a] & intorno).sum() / v[a].sum()
        lift = (quota / 100) / intorno.mean()
        r = sv_tutte.loc[(a, b)]
        ok &= abs(r["quota_min"] - round(quota, 1)) < 0.06 and abs(r["lift_min"] - round(lift, 2)) < 0.006
    check("B1. quota e lift di tre coppie uguali al conteggio barra per barra (finestra di 2 barre)", ok)
    R.clear_registry()

    # =====================================================================
    print("\nC · IL CATALOGO VERO (EURUSD, in-sample)\n" + "-" * 70)
    if not os.path.exists(DATI):
        saltato("C. catalogo vero", "manca dati/EURUSD_M15.csv")
    else:
        from engine.broker_tz_diagnostic import to_utc_index
        from engine.indicatori import aggiungi_indicatori
        from engine.splitting import split_is_oos
        import entry_long, entry_short, filter_conditions
        grezzo = pd.read_csv(DATI, parse_dates=["Date"], index_col="Date")
        grezzo = to_utc_index(grezzo, "A_US_DST (NY+7h)", on_dst_gap="drop", verbose=False)
        df_is, _ = split_is_oos(aggiungi_indicatori(grezzo.tail(60000)), 0.8)
        R.clear_registry()
        with contextlib.redirect_stdout(io.StringIO()):
            entry_long.registra_trigger_long()
            entry_short.registra_trigger_short()
            filter_conditions.registra_filtri()
        fe = famiglie(df_is, "entry").set_index("nome")["famiglia"]
        check("C1. entry: pattern confermati, harami cross e three inside nella famiglia dell'harami",
              fe["E13_HARAMI"] == fe["E13_HARAMI_CONFIRMED"] == fe["E14_HARAMI_CROSS"] == fe["E17_THREE_INSIDE"]
              and fe["E12_ENGULFING"] == fe["E18_THREE_OUTSIDE"] and fe["E21_BELT_HOLD"] == fe["E20_MARUBOZU"])
        check("C2. entry: long e short dello stesso pattern in famiglie diverse; meno famiglie che condizioni",
              fe["E13_HARAMI"] != fe["E13_SHORT_HARAMI"] and fe.nunique() < len(fe),
              f"{len(fe)} entry in {fe.nunique()} famiglie")
        ffl = famiglie(df_is, "filtro").set_index("nome")["famiglia"]
        check("C3. filtri: volume sopra la media a 20 e a 50 barre e climax nella stessa famiglia",
              ffl["F3_VOLUME_ABOVE_AVG"] == ffl["F6_VOLUME_ABOVE_AVG_50"] == ffl["F7_VOLUME_CLIMAX"],
              f"{len(ffl)} filtri in {ffl.nunique()} famiglie")
        sv = sovrapposizioni(df_is, "entry")
        dop = set(sv.loc[sv["doppione"], "contenuta"])
        check("C4. sovrapposizioni: le versioni _CONFIRMED risultano doppioni della base",
              {"E11_INVERTED_HAMMER_CONFIRMED", "E12_ENGULFING_CONFIRMED", "E13_HARAMI_CONFIRMED"} <= dop)
        R.clear_registry()

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(main())
