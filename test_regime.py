"""
Suite di validazione dei filtri di regime entrati da articoli il 9/10/2026
(metodo: 50_IDEE_DA_ARTICOLI.md).

    F25  choppiness: tendenza (CHOP_TREND) e laterale (CHOP_RANGE)   (PyQuantLab, 7/9/2026)
    F26  variance ratio: persistenza                                  (proposta del 9/10/2026)
    F27  regime di tendenza composito, a voti                         (OPZIONALE)
    --   stato con isteresi (_stato_isteresi)

Si lancia da terminale, dalla cartella del progetto:

    python test_regime.py

Non serve MetaTrader 5 e non serve nessun file di dati. Dura meno di un minuto.
"""
from __future__ import annotations

import math
import sys
import warnings

import numpy as np
import pandas as pd

warnings.simplefilter(action="ignore", category=FutureWarning)

from engine import registry as R
from engine.collaudo_catalogo import mercato_sintetico, verifica_lookahead
from engine.indicatori import (COLONNE_INDICATORI, aggiungi_indicatori,
                               indice_choppiness, variance_ratio)
from filter_conditions import (FILTRI, _adx_forte, _stato_isteresi, filter_chop_range,
                               filter_chop_trend, filter_regime_trend_composite,
                               filter_variance_ratio_trend, registra_filtri)


def _indice(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")


def _ohlc(close: np.ndarray, mezza_barra: float = 0.0, indice=None) -> pd.DataFrame:
    """Barre costruite a mano: Open = chiusura prima, massimo e minimo a `mezza_barra` dai bordi."""
    close = np.asarray(close, dtype=float)
    op = np.r_[close[0], close[:-1]]
    return pd.DataFrame(
        {"Open": op,
         "High": np.maximum(op, close) + mezza_barra,
         "Low": np.minimum(op, close) - mezza_barra,
         "Close": close,
         "Volume": 100.0},
        index=_indice(len(close)) if indice is None else indice,
    )


def _chop_riferimento(df: pd.DataFrame, n: int = 14) -> np.ndarray:
    """Il Choppiness Index riscritto barra per barra, a mano. Solo pietra di paragone."""
    H, L, C = (df[c].to_numpy(dtype=float) for c in ("High", "Low", "Close"))
    tr = np.full(len(df), np.nan)
    for i in range(1, len(df)):
        tr[i] = max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1]))
    esito = np.full(len(df), np.nan)
    for i in range(n, len(df)):
        somma = tr[i - n + 1:i + 1].sum()
        ampiezza = H[i - n + 1:i + 1].max() - L[i - n + 1:i + 1].min()
        esito[i] = 100.0 * math.log10(somma / ampiezza) / math.log10(n) if ampiezza > 0 else 100.0
    return esito


def _vr_riferimento(close: np.ndarray, q: int = 4, w: int = 192) -> np.ndarray:
    """Il variance ratio riscritto barra per barra, con numpy.var. Solo pietra di paragone."""
    lp = np.log(np.asarray(close, dtype=float))
    r1 = np.r_[np.nan, np.diff(lp)]
    rq = np.full(len(lp), np.nan)
    rq[q:] = lp[q:] - lp[:-q]
    esito = np.full(len(lp), np.nan)
    for i in range(w + q - 1, len(lp)):
        v1 = r1[i - w + 1:i + 1].var(ddof=1)
        vq = rq[i - w + 1:i + 1].var(ddof=1)
        esito[i] = vq / (q * v1) if v1 > 0 else 1.0
    return esito


def _passeggiata_ar(phi: float, n: int, seme: int) -> pd.DataFrame:
    """Prezzo i cui rendimenti seguono un AR(1) con coefficiente `phi` (vero valore noto del VR)."""
    rng = np.random.default_rng(seme)
    e = rng.normal(0, 3e-4, n)
    r = np.zeros(n)
    for i in range(1, n):
        r[i] = phi * r[i - 1] + e[i]
    return _ohlc(1.10 * np.exp(np.cumsum(r)), mezza_barra=1e-5)


def _cambi(s: pd.Series) -> int:
    m = s.to_numpy(dtype=bool)
    return int((m[1:] != m[:-1]).sum())


def esegui() -> int:
    """Esegue la suite. Ritorna 0 se tutto passa, 1 altrimenti."""
    ESITI = []

    def check(nome: str, condizione: bool, dettaglio: str = ""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    mercato = mercato_sintetico("2024-01-01", "2024-07-01", seme=3)

    # =====================================================================
    print("\nA · CHOPPINESS INDEX (indice_choppiness)\n" + "-" * 70)
    chop = indice_choppiness(mercato)
    check("A1. le prime 14 barre sono NaN, poi nessun NaN",
          bool(chop.iloc[:14].isna().all() and chop.iloc[14:].notna().all()))
    rif = _chop_riferimento(mercato)
    massimo = float(np.nanmax(np.abs(chop.to_numpy() - rif)))
    check("A2. identico alla riscrittura indipendente barra per barra",
          bool(np.allclose(chop.to_numpy(), rif, equal_nan=True, atol=1e-9)), f"scarto massimo {massimo:.1e}")

    # salita costante a barre strette: il percorso e' quasi uguale all'ampiezza
    retta = _ohlc(np.linspace(1.10, 1.11, 200), mezza_barra=2e-6)
    c_retta = float(indice_choppiness(retta).iloc[14:].max())
    check("A3. prezzo che sale in linea retta: CHOP sotto 10", c_retta < 10, f"massimo {c_retta:.1f}")
    # avanti e indietro fra due livelli: il percorso e' n volte l'ampiezza, CHOP = 100
    zigzag = _ohlc(np.tile([1.1000, 1.1010], 100))
    c_zz = indice_choppiness(zigzag).iloc[14:]
    check("A4. prezzo che va avanti e indietro fra due livelli: CHOP = 100",
          bool(np.allclose(c_zz, 100.0, atol=1e-6)), f"da {c_zz.min():.4f} a {c_zz.max():.4f}")
    fermo = _ohlc(np.full(100, 1.10))
    c_fermo = indice_choppiness(fermo)
    check("A5. mercato fermo: CHOP = 100 e nessun NaN dopo le prime 14 barre (niente buchi nei dati)",
          bool((c_fermo.iloc[14:] == 100.0).all() and c_fermo.iloc[14:].notna().all()))
    specchio = pd.DataFrame({"Open": -mercato["Open"], "High": -mercato["Low"], "Low": -mercato["High"],
                             "Close": -mercato["Close"], "Volume": mercato["Volume"]}, index=mercato.index)
    check("A6. sul mercato capovolto CHOP e' identico (misura la magnitudine, non il verso)",
          bool(np.allclose(indice_choppiness(specchio), chop, equal_nan=True, atol=1e-9)))
    corto = indice_choppiness(mercato.iloc[:200]).iloc[:150]
    check("A7. calcolato su meno dati, le barre gia' note non cambiano (solo passato)",
          bool(np.allclose(corto, chop.iloc[:150], equal_nan=True, atol=1e-12)))

    # =====================================================================
    print("\nB · VARIANCE RATIO (variance_ratio)\n" + "-" * 70)
    vr = variance_ratio(mercato["Close"])
    check("B1. le prime 195 barre (192 + 4 - 1) sono NaN, poi nessun NaN",
          bool(vr.iloc[:195].isna().all() and vr.iloc[195:].notna().all()))
    rif_vr = _vr_riferimento(mercato["Close"].to_numpy())
    massimo_vr = float(np.nanmax(np.abs(vr.to_numpy() - rif_vr)))
    check("B2. identico alla riscrittura indipendente barra per barra",
          bool(np.allclose(vr.to_numpy(), rif_vr, equal_nan=True, atol=1e-9)), f"scarto massimo {massimo_vr:.1e}")

    casuale = variance_ratio(_passeggiata_ar(0.0, 30_000, seme=0)["Close"]).dropna()
    check("B3. passeggiata casuale: VR mediano vicino a 1 (fra 0,90 e 1,05)",
          0.90 <= float(casuale.median()) <= 1.05, f"{casuale.median():.3f}")
    check("B4. passeggiata casuale: scarto tipico fra 0,10 e 0,18 (formula di Lo e MacKinlay: 0,135)",
          0.10 <= float(casuale.std()) <= 0.18, f"{casuale.std():.3f}")
    # AR(1) con phi = +0,5: VR(4) teorico = 2,06; con phi = -0,5: 0,44
    pers = variance_ratio(_passeggiata_ar(+0.5, 30_000, seme=1)["Close"]).dropna()
    anti = variance_ratio(_passeggiata_ar(-0.5, 30_000, seme=2)["Close"]).dropna()
    check("B5. rendimenti che si ripetono (AR phi=+0,5, teorico 2,06): VR mediano fra 1,6 e 2,4",
          1.6 <= float(pers.median()) <= 2.4, f"{pers.median():.2f}")
    check("B6. rendimenti che rimbalzano (AR phi=-0,5, teorico 0,44): VR mediano fra 0,3 e 0,6",
          0.3 <= float(anti.median()) <= 0.6, f"{anti.median():.2f}")
    v_fermo = variance_ratio(pd.Series(1.10, index=_indice(400)))
    check("B7. prezzo fermo: VR = 1 e nessun NaN dopo il riscaldamento (niente buchi nei dati)",
          bool((v_fermo.iloc[195:] == 1.0).all() and v_fermo.iloc[195:].notna().all()))
    check("B8. moltiplicando il prezzo per 1000 il VR non cambia (lavora sui rendimenti)",
          bool(np.allclose(variance_ratio(mercato["Close"] * 1000), vr, equal_nan=True, atol=1e-9)))
    reciproco = variance_ratio(1.0 / mercato["Close"])
    check("B9. sul prezzo rovesciato (1/prezzo) il VR e' identico (misura la persistenza, non il verso)",
          bool(np.allclose(reciproco, vr, equal_nan=True, atol=1e-9)))
    corto_vr = variance_ratio(mercato["Close"].iloc[:600]).iloc[:450]
    check("B10. calcolato su meno dati, le barre gia' note non cambiano (solo passato)",
          bool(np.allclose(corto_vr, vr.iloc[:450], equal_nan=True, atol=1e-12)))

    # =====================================================================
    print("\nC · STATO CON ISTERESI (_stato_isteresi)\n" + "-" * 70)
    x = pd.Series([0.6, 0.3, 0.2, 0.4, 0.45, 0.55, 0.3, 0.1, np.nan, 0.2])
    basso = _stato_isteresi(x, entra=0.25, esce=0.50, basso=True).tolist()
    atteso_basso = [False, False, True, True, True, False, False, True, False, True]
    check("C1. basso=True a mano: si accende a 0,25, resta acceso fino a sopra 0,50, il NaN lo spegne",
          basso == atteso_basso, f"{basso}")
    y = 1.0 - x
    alto = _stato_isteresi(y, entra=0.75, esce=0.50, basso=False).tolist()
    check("C2. basso=False e' lo specchio esatto (stessa sequenza sul percentile rovesciato)",
          alto == atteso_basso, f"{alto}")
    rng = np.random.default_rng(7)
    casuali = pd.Series(rng.uniform(0, 1, 5000))
    semplice = _stato_isteresi(casuali, entra=0.25, esce=0.25, basso=True)
    check("C3. con soglia di entrata = soglia di uscita diventa la soglia semplice (rango <= soglia)",
          bool(semplice.equals(casuali <= 0.25)))
    rumore = pd.Series(0.25 + rng.normal(0, 0.05, 3000))
    s_isteresi = _stato_isteresi(rumore, 0.25, 0.50, True)
    s_semplice = _stato_isteresi(rumore, 0.25, 0.25, True)
    check("C4. valore che gira attorno alla soglia: l'isteresi cambia stato almeno 10 volte meno",
          _cambi(s_isteresi) * 10 <= _cambi(s_semplice), f"{_cambi(s_isteresi)} cambi contro {_cambi(s_semplice)}")
    pieno = _stato_isteresi(casuali, 0.25, 0.50, True)
    troncamenti = all(_stato_isteresi(casuali.iloc[:t + 1], 0.25, 0.50, True).equals(pieno.iloc[:t + 1])
                      for t in (50, 400, 1999, 4000))
    check("C5. causale: tagliando i dati alla barra t le barre fino a t restano uguali", bool(troncamenti))
    lontano = max(
        int((_stato_isteresi(casuali.iloc[a:], 0.25, 0.50, True).iloc[60:]
             != pieno.iloc[a:].iloc[60:]).sum())
        for a in (1, 500, 1234, 3000))
    check("C6. partendo da punti diversi gli stati coincidono dopo 60 barre (rango casuale)",
          lontano == 0, f"{lontano} barre diverse")

    # =====================================================================
    print("\nD · FILTRI F25, F26, F27: struttura e registrazione\n" + "-" * 70)
    attesi = ("F25_CHOP_TREND", "F25_CHOP_RANGE", "F26_VARIANCE_RATIO_TREND")
    check("D1. F25 (due filtri) e F26 sono in FILTRI, neutri (direction 0, nessuna coppia)",
          all(k in FILTRI and FILTRI[k][1] == 0 and FILTRI[k][2] is None for k in attesi))
    check("D2. F27 composito: o non c'e' (opzionale) o e' neutro e senza coppia",
          ("F27_REGIME_TREND_COMPOSITE" not in FILTRI)
          or (FILTRI["F27_REGIME_TREND_COMPOSITE"][1] == 0 and FILTRI["F27_REGIME_TREND_COMPOSITE"][2] is None))
    R.clear_registry()
    registra_filtri()
    reg = set(R.list_filters())
    check("D3. dopo registra_filtri() i tre filtri sono nel motore, neutri e senza coppia",
          all(k in reg and R.get_filter_direction(k) == 0 and R.get_filter_pair(k) is None for k in attesi))
    check("D4. nessuna coppia nuova: le coppie di prima non sono cambiate",
          {c[0] for c in R.list_filter_pairs()} == {"MACD_SIGNAL", "TREND_CONTEXT", "TREND_CONVICTION",
                                                   "EXTENDED_FROM_MEAN", "VWAP_POSITION", "RANGE_POSITION",
                                                   "OVERNIGHT_RETURN", "TWO_BARS"},
          f"{sorted(c[0] for c in R.list_filter_pairs())}")

    # =====================================================================
    print("\nE · FILTRI su dati sintetici: copertura e consistenza\n" + "-" * 70)
    lungo = mercato_sintetico("2023-01-01", "2024-06-01", seme=1)
    df = aggiungi_indicatori(lungo)
    check("E1. aggiungi_indicatori ha le colonne nuove e toglie ancora solo le prime 300 righe (ciclo dominante)",
          bool({"chop", "vr"} <= set(df.columns) and {"chop", "vr"} <= set(COLONNE_INDICATORI)
               and len(df) == len(lungo) - 300), f"{len(lungo)} -> {len(df)}")
    f_trend, f_range = filter_chop_trend(df), filter_chop_range(df)
    f_vr, f_comp = filter_variance_ratio_trend(df), filter_regime_trend_composite(df)
    check("E2. falsi finche' manca la storia del percentile (prime 499 barre dopo il riscaldamento)",
          not bool(f_trend.iloc[:499].any() or f_range.iloc[:499].any()))
    check("E3. falsi finche' manca la storia del percentile del VR (prime 999 barre)",
          not bool(f_vr.iloc[:999].any()))
    cop = {k: float(s.iloc[1000:].mean()) for k, s in
           (("F25_TREND", f_trend), ("F25_RANGE", f_range), ("F26", f_vr), ("F27", f_comp))}
    check("E4. nessuno sempre vero o sempre falso: copertura fra 15% e 60%",
          all(0.15 <= v <= 0.60 for v in cop.values()), " ".join(f"{k} {v:.0%}" for k, v in cop.items()))
    check("E5. F25 tendenza e laterale non sono mai veri insieme",
          not bool((f_trend & f_range).any()))
    check("E6. tutti i filtri sono booleani con lo stesso indice del df",
          all(s.dtype == bool and s.index.equals(df.index) for s in (f_trend, f_range, f_vr, f_comp)))

    # =====================================================================
    print("\nF · F27 COMPOSITO (opzionale)\n" + "-" * 70)
    adx = _adx_forte(df)
    voti = f_trend.astype(int) + f_vr.astype(int) + adx.astype(int)
    check("F1. F27 = almeno 2 voti su 3 fra tendenza (CHOP), persistenza (VR) e ADX, ricalcolato a mano",
          bool(f_comp.equals(voti >= 2)))
    tre = filter_regime_trend_composite(df, voti_minimi=3)
    uno = filter_regime_trend_composite(df, voti_minimi=1)
    check("F2. con 3 voti = AND dei tre stati; con 1 = OR; e 3 voti <= 2 voti <= 1 voto",
          bool(tre.equals(f_trend & f_vr & adx) and uno.equals(f_trend | f_vr | adx)
               and (tre <= f_comp).all() and (f_comp <= uno).all()))
    corr = {"CHOP~VR": float(np.corrcoef(f_trend, f_vr)[0, 1]),
            "ADX~CHOP": float(np.corrcoef(adx, f_trend)[0, 1]),
            "ADX~VR": float(np.corrcoef(adx, f_vr)[0, 1])}
    print("  [info   ] correlazione fra gli stati (su dati sintetici): "
          + ", ".join(f"{k} {v:.2f}" for k, v in corr.items()))

    # =====================================================================
    print("\nG · LOOKAHEAD (per troncamento) E RISCALDAMENTO\n" + "-" * 70)
    nuovi_filtri = {"F25_CHOP_TREND": filter_chop_trend, "F25_CHOP_RANGE": filter_chop_range,
                    "F26_VARIANCE_RATIO_TREND": filter_variance_ratio_trend,
                    "F27_REGIME_TREND_COMPOSITE": filter_regime_trend_composite}

    # Le trappole: il difetto tipico delle fonti, messo apposta.
    #  1. finestra centrata: il valore alla barra t usa anche n/2 barre dopo t;
    #  2. varianza di normalizzazione calcolata su tutto il campione.
    def _chop_centrato(d: pd.DataFrame, n: int = 14) -> pd.Series:
        cp = d["Close"].shift(1)
        tr = pd.concat([d["High"] - d["Low"], (d["High"] - cp).abs(), (d["Low"] - cp).abs()],
                       axis=1).max(axis=1, skipna=False)
        amp = d["High"].rolling(n, center=True).max() - d["Low"].rolling(n, center=True).min()
        return 100.0 * np.log10(tr.rolling(n, center=True).sum() / amp.where(amp > 0)) / np.log10(n)

    def _vr_varianza_intera(close: pd.Series, q: int = 4, w: int = 192) -> pd.Series:
        lp = np.log(close)
        return lp.diff(q).rolling(w).var() / (q * lp.diff().var())

    def prepara_con_trappole(d):
        out = aggiungi_indicatori(d)
        out["chop_centrato"] = _chop_centrato(out)
        out["vr_varianza_intera"] = _vr_varianza_intera(out["Close"])
        return out

    R.clear_registry()
    for k, f in nuovi_filtri.items():
        R.register_filter(k)(f)
    R.register_filter("T_CHOP_CENTRATO")(lambda d: d["chop_centrato"] < 50.0)
    R.register_filter("T_VR_VARIANZA_INTERA")(lambda d: d["vr_varianza_intera"] > 1.0)

    rep = verifica_lookahead(mercato_sintetico(), prepara=prepara_con_trappole, verbose=False)
    esito = rep.set_index("nome")["esito"]
    check("G1. trappola 1 (CHOP a finestra centrata): condizione e indicatore segnati LOOKAHEAD",
          esito["T_CHOP_CENTRATO"] == "LOOKAHEAD" and esito["chop_centrato"] == "LOOKAHEAD")
    check("G2. trappola 2 (VR con varianza di tutto il campione): condizione e indicatore segnati LOOKAHEAD",
          esito["T_VR_VARIANZA_INTERA"] == "LOOKAHEAD" and esito["vr_varianza_intera"] == "LOOKAHEAD")
    non_ok = {k: esito[k] for k in nuovi_filtri if esito[k] != "OK"}
    check(f"G3. i {len(nuovi_filtri)} filtri nuovi risultano OK (nessun lookahead, tutti esercitati)",
          not non_ok, f"{non_ok}" if non_ok else "")
    check("G4. gli indicatori chop e vr risultano OK", esito["chop"] == "OK" and esito["vr"] == "OK",
          f"chop {esito['chop']}, vr {esito['vr']}")
    check("G5. tutti gli indicatori di prima risultano ancora OK",
          all(esito[c] == "OK" for c in COLONNE_INDICATORI))

    # riscaldamento: stessa colonna da qualunque punto partano i dati
    lungo2 = mercato_sintetico("2023-01-01", "2024-01-01", seme=5)
    intero = aggiungi_indicatori(lungo2)
    taglio = 3000
    peggio = {}
    for partenza in (700, 4001, 9050):
        parziale = aggiungi_indicatori(lungo2.iloc[partenza:])
        comune = parziale.index[taglio:]
        for k, f in nuovi_filtri.items():
            diverse = int((f(intero).loc[comune] != f(parziale).loc[comune]).sum())
            peggio[k] = max(peggio.get(k, 0), diverse)
    sporche = {k: v for k, v in peggio.items() if v}
    check(f"G6. dopo {taglio} barre i filtri (isteresi compresa) non dipendono dal punto di partenza dei dati",
          not sporche, f"{sporche}" if sporche else "")

    print("\n" + "=" * 70)
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
