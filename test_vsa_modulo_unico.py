"""
Collaudo delle condizioni del VSA · Modulo Unico (docs/50 §10, riga 14; scheda
approvata da Mattia il 17/10/2026; script Pine v6 di Mattia):

    engine/indicatori.py   vsa_modulo_unico, _percentrank_pine, _percentile_pine
                           (colonne vsa_asta, vsa_bias, vsa_go, vsa_sr)
    E34_VSA_TREND_GO_UP / E34_SHORT_VSA_TREND_GO_DOWN           GO trend, senza sessione
    E35_VSA_STOP_REVERSE_UP / E35_SHORT_VSA_STOP_REVERSE_DOWN   Stop & Reverse

Sezioni (docs/50 §7):

    A  fedelta' a TradingView: il Pine (copia di collaudo pine_sources/
       vsa_modulo_unico_v6.pine: senza grafica, pannello e alert, sessione spenta)
       fatto girare con PineTS sulle stesse barre di EURUSD, BTCUSD e DE40, con i
       prezzi in punti interi (calcoli esatti in entrambi i programmi)
    B  le primitive (rango e percentile come in Pine) contro calcoli a mano;
       stesso risultato con i prezzi veri e con i prezzi in punti interi
    C  proprieta' a risultato noto: specchio dei prezzi (long <-> short), ogni
       GO e ogni S&R rispetta le sue condizioni, il ramo range escluso
    D  lookahead per troncamento (verifica_lookahead) con una trappola tipica
       (rango del corpo su una finestra centrata) che deve risultare LOOKAHEAD
    E  riscaldamento: stesse condizioni da qualunque punto partano i dati
    F  i 9 symbol di dati/ (solo conteggi) e verifica_degenerazione su EURUSD
    G  registrazione nel motore e righe di aggiungi_indicatori invariate

Si lancia da terminale, dalla cartella del progetto:

    python test_vsa_modulo_unico.py

(su Windows: PYTHONIOENCODING=utf-8). Il confronto con PineTS gira solo se ci
sono Node.js, strumenti_pinets/node_modules e il file Pine in pine_sources/
(strumenti_pinets/LEGGIMI.md); le prove sui dati veri solo se ci sono i file di
dati/. Se mancano vengono SALTATE e lo dice. Non serve MT5.
"""
from __future__ import annotations

import contextlib
import csv
import io
import os
import shutil
import subprocess
import sys
import tempfile
import warnings

import numpy as np
import pandas as pd

warnings.simplefilter(action="ignore", category=FutureWarning)

from engine import registry as R
from engine.broker_tz_diagnostic import to_utc_index
from engine.collaudo_catalogo import mercato_sintetico, verifica_degenerazione, verifica_lookahead
from engine.indicatori import (COLONNE_INDICATORI, _percentile_pine, _percentrank_pine,
                               aggiungi_indicatori, vsa_modulo_unico)
from engine.livelli import svuota_cache
from engine.simboli import info_symbol
from entry_long import (TRIGGER_LONG, entry_vsa_stop_reverse_up, entry_vsa_trend_go_up,
                        registra_trigger_long)
from entry_short import (TRIGGER_SHORT, entry_short_vsa_stop_reverse_down,
                         entry_short_vsa_trend_go_down, registra_trigger_short)

CARTELLA = os.path.dirname(os.path.abspath(__file__))
DATI = os.path.join(CARTELLA, "dati")
PINETS = os.path.join(CARTELLA, "strumenti_pinets")
PINE = os.path.join(CARTELLA, "pine_sources", "vsa_modulo_unico_v6.pine")
SYMBOL = ("EURUSD", "GBPUSD", "USDJPY", "NZDUSD", "BTCUSD", "US500", "USTEC", "XAUUSD", "DE40")
ENTRY_NUOVE = {"E34_VSA_TREND_GO_UP": entry_vsa_trend_go_up,
               "E34_SHORT_VSA_TREND_GO_DOWN": entry_short_vsa_trend_go_down,
               "E35_VSA_STOP_REVERSE_UP": entry_vsa_stop_reverse_up,
               "E35_SHORT_VSA_STOP_REVERSE_DOWN": entry_short_vsa_stop_reverse_down}
COLONNE = ("vsa_asta", "vsa_bias", "vsa_go", "vsa_sr")


def _leggi(symbol: str) -> pd.DataFrame | None:
    percorso = os.path.join(DATI, f"{symbol}_M15.csv")
    if not os.path.exists(percorso):
        return None
    df = pd.read_csv(percorso, parse_dates=["Date"], index_col="Date")
    df = to_utc_index(df, "A_US_DST (NY+7h)", on_dst_gap="drop", verbose=False)
    return df[["Open", "High", "Low", "Close", "Volume"]]


def _con_colonne(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    m = vsa_modulo_unico(d)
    for k in ("asta", "bias", "go", "sr"):
        d[f"vsa_{k}"] = m[k]
    return d


def _in_punti(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Prezzi in punti interi (1,12119 -> 112119): lo script usa solo confronti e rapporti."""
    k = 10 ** info_symbol(symbol)["cifre"]
    return df.assign(**{c: np.round(df[c] * k) for c in ("Open", "High", "Low", "Close")})


def _pinets_disponibile() -> bool:
    return (shutil.which("node") is not None
            and os.path.isdir(os.path.join(PINETS, "node_modules", "pinets")) and os.path.exists(PINE))


def _pinets(df: pd.DataFrame, cartella_tmp: str) -> pd.DataFrame:
    dati = os.path.join(cartella_tmp, "dati.csv")
    uscita = os.path.join(cartella_tmp, "pine.csv")
    df.tz_localize(None).rename_axis("Date").to_csv(dati, date_format="%Y-%m-%d %H:%M:%S")
    subprocess.run(["node", "esegui_pine.mjs", dati, PINE, uscita],
                   cwd=PINETS, check=True, capture_output=True, text=True)
    with open(uscita, newline="") as f:
        righe = list(csv.reader(f))
    k = next((i for i, x in enumerate(righe[0]) if x.startswith("__")), len(righe[0]))
    pine = pd.DataFrame([r[:k] for r in righe[1:]], columns=righe[0][:k]).set_index("Date")
    pine = pine.apply(pd.to_numeric, errors="coerce")
    pine.index = df.index
    return pine


def _specchio(df: pd.DataFrame) -> pd.DataFrame:
    """Prezzi rovesciati attorno a una costante: i rialzi diventano ribassi, i corpi restano."""
    k = float(df["High"].max() + df["Low"].min())
    return pd.DataFrame({"Open": k - df["Open"], "High": k - df["Low"], "Low": k - df["High"],
                         "Close": k - df["Close"], "Volume": df["Volume"]}, index=df.index)


def _trappola_rango_centrato(df: pd.DataFrame) -> pd.Series:
    """rango del corpo su 101 barre CENTRATE sulla barra (50 dopo): guarda il futuro"""
    corpo = (df["Close"] - df["Open"]).abs()
    return corpo.rolling(101, center=True).rank(pct=True)


def _prepara(df: pd.DataFrame) -> pd.DataFrame:
    d = _con_colonne(df)
    d["t_rango_centrato"] = _trappola_rango_centrato(d)
    return d


def main() -> int:
    ESITI: list[bool] = []

    def check(nome: str, condizione: bool, dettaglio: str = ""):
        ESITI.append(bool(condizione))
        stato = "OK  " if condizione else "FAIL"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def saltato(nome: str, motivo: str):
        print(f"  [SALT] {nome}  — {motivo}")

    reali = {s: _leggi(s) for s in SYMBOL}
    forex = mercato_sintetico("2024-01-01", "2024-05-01", seme=4)

    # =====================================================================
    print("\nA · FEDELTA' A TRADINGVIEW (PineTS sul Pine dello script)\n" + "-" * 70)
    if not _pinets_disponibile():
        saltato("A. confronto con PineTS", "mancano Node.js, strumenti_pinets/node_modules o il file in pine_sources/")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            for symbol in ("EURUSD", "BTCUSD", "DE40"):
                if reali[symbol] is None:
                    saltato(f"A. {symbol}", "manca il file di dati")
                    continue
                dati = _in_punti(reali[symbol].head(40000), symbol)
                p = _pinets(dati, tmp)
                m = vsa_modulo_unico(dati)
                corpo = (dati["Close"] - dati["Open"]).abs().to_numpy()
                med = _percentile_pine(corpo, 100, 50)
                check(f"A1. {symbol}: mediana dei corpi identica a ta.percentile_linear_interpolation",
                      bool(np.array_equal(np.isnan(med), np.isnan(p["med"].to_numpy()))
                           and np.nanmax(np.abs(med - p["med"].to_numpy())) < 1e-9))
                diverse = {mio: int((m[mio].to_numpy() != p[suo].to_numpy()).sum())
                           for mio, suo in (("asta", "auct"), ("bias", "bias"), ("go", "go_trend"), ("sr", "sr"))}
                eventi = {k: int((m[k] != 0).sum()) for k in ("go", "sr")}
                check(f"A2. {symbol}: asta, bias VSA, GO trend e Stop & Reverse identici su {len(dati)} barre",
                      not any(diverse.values()) and eventi["go"] > 50 and eventi["sr"] > 500,
                      f"eventi {eventi}" + (f", diverse {diverse}" if any(diverse.values()) else ""))

    # =====================================================================
    print("\nB · PRIMITIVE E SCALA DEI PREZZI\n" + "-" * 70)
    rng = np.random.default_rng(5)
    x = rng.integers(0, 20, 400).astype(float)          # tanti pareggi, come i corpi veri
    pr = _percentrank_pine(x, 100)
    a_mano = np.array([np.nan] * 100 + [100.0 * sum(x[j] <= x[i] for j in range(i - 100, i)) / 100
                                        for i in range(100, 400)])
    check("B1. rango come ta.percentrank: quota delle 100 barre PRECEDENTI <= della corrente (anche coi pareggi)",
          bool(np.array_equal(np.isnan(pr), np.isnan(a_mano)) and np.nanmax(np.abs(pr - a_mano)) < 1e-12))
    ok_p = True
    for perc in (10, 30, 50, 65, 90):
        pp = _percentile_pine(x, 100, perc)
        for i in (99, 250, 399):
            s = np.sort(x[i - 99:i + 1])
            pos = min(max(100 * perc / 100 - 0.5, 0), 99)
            att = s[int(pos)] + (pos - int(pos)) * (s[min(int(pos) + 1, 99)] - s[int(pos)])
            ok_p &= abs(pp[i] - att) < 1e-12
    check("B2. percentile come ta.percentile_linear_interpolation (posizione n x p - 0,5, verificata con PineTS)", ok_p)
    for symbol in ("EURUSD", "BTCUSD"):
        if reali[symbol] is None:
            saltato(f"B3. {symbol}", "manca il file di dati")
            continue
        dati = reali[symbol].tail(30000)
        vero, punti = vsa_modulo_unico(dati), vsa_modulo_unico(_in_punti(dati, symbol))
        diverse = {k: int((vero[k] != punti[k]).sum()) for k in ("asta", "bias", "go", "sr")}
        check(f"B3. {symbol}: prezzi veri e prezzi in punti interi danno gli stessi segnali (arrotondamento a 10 decimali)",
              not any(diverse.values()), str(diverse) if any(diverse.values()) else "")

    # =====================================================================
    print("\nC · PROPRIETA' A RISULTATO NOTO\n" + "-" * 70)
    base_grezza = reali["EURUSD"].tail(40000) if reali["EURUSD"] is not None else forex
    base = _con_colonne(base_grezza)
    # lo specchio sui prezzi in punti interi: "costante - prezzo" in decimali aggiunge rumore
    punti = _con_colonne(_in_punti(base_grezza, "EURUSD"))
    spec = _con_colonne(_specchio(_in_punti(base_grezza, "EURUSD")))
    dopo = base.index[2000:]
    check("C1. specchio dei prezzi: GO long e short si scambiano (dopo 2000 barre di avvio)",
          entry_vsa_trend_go_up(punti).loc[dopo].equals(entry_short_vsa_trend_go_down(spec).loc[dopo])
          and entry_short_vsa_trend_go_down(punti).loc[dopo].equals(entry_vsa_trend_go_up(spec).loc[dopo]),
          f"{int(entry_vsa_trend_go_up(punti).sum())} long, {int(entry_short_vsa_trend_go_down(punti).sum())} short")
    check("C2. specchio dei prezzi: Stop & Reverse long e short si scambiano, l'asta cambia segno",
          entry_vsa_stop_reverse_up(punti).loc[dopo].equals(entry_short_vsa_stop_reverse_down(spec).loc[dopo])
          and bool((punti["vsa_asta"].loc[dopo] == -spec["vsa_asta"].loc[dopo]).all()))
    o, c = base["Open"].to_numpy(), base["Close"].to_numpy()
    corpo = np.round(np.abs(np.round(c, 10) - np.round(o, 10)), 10)
    rango = np.nan_to_num(_percentrank_pine(corpo, 100), nan=-1)
    asta, bias, go, sr = (base[k].to_numpy() for k in COLONNE)
    i_go = np.flatnonzero(go != 0)
    ok_go = all(asta[i] == go[i] and np.sign(c[i] - o[i]) == go[i] and rango[i] >= 50
                and any(bias[j] == go[i] and asta[j] == go[i] for j in range(max(i - 3, 0), i))
                for i in i_go)
    check("C3. ogni GO: asta nel verso, candela di conferma del colore giusto con corpo >= 50°, "
          "incongruenza VSA allineata nelle 3 barre prima", ok_go and len(i_go) > 50, f"{len(i_go)} GO")
    i_sr = np.flatnonzero(sr != 0)
    ok_sr = all(asta[i - 1] == -sr[i] and asta[i] == 0 and np.sign(c[i] - o[i]) == sr[i] and rango[i] >= 65
                for i in i_sr)
    check("C4. ogni S&R: alla barra prima asta contraria, alla barra del segnale asta azzerata (CHoCH), "
          "candela del verso nuovo con corpo >= 65°", ok_sr and len(i_sr) > 500, f"{len(i_sr)} S&R")
    i_b = np.flatnonzero(bias != 0)
    check("C5. il bias VSA e' sempre contrario al colore della candela (assorbimento ed esaurimento 'Reversal')",
          bool(len(i_b) > 100 and (bias[i_b] == -np.sign(c[i_b] - o[i_b])).all()))
    # il ramo range non c'e': con i default la conferma chiederebbe bias == verso e candela del verso
    check("C6. ramo range escluso a ragione: nessuna barra ha bias VSA nel verso della propria candela",
          not bool(((bias != 0) & (bias == np.sign(c - o))).any()))
    eventi = base["vsa_go"].to_numpy()
    consecutivi = int(((eventi != 0) & (np.r_[0, eventi[:-1]] == eventi)).sum())
    check("C7. E34 e' un evento: tiene solo la prima barra di GO consecutivi",
          int(entry_vsa_trend_go_up(base).sum() + entry_short_vsa_trend_go_down(base).sum())
          == int((eventi != 0).sum()) - consecutivi, f"{consecutivi} GO su barre consecutive")

    # =====================================================================
    print("\nD · LOOKAHEAD PER TRONCAMENTO\n" + "-" * 70)
    R.clear_registry()
    for k, f in ENTRY_NUOVE.items():
        R.register_entry(k, -1 if "SHORT" in k else 1)(f)
    R.register_filter("T_RANGO_CENTRATO")(lambda df: df["t_rango_centrato"] > 0.65)
    insiemi_d = [("forex sintetico", forex)]
    for s in ("EURUSD", "BTCUSD"):
        if reali[s] is not None:
            insiemi_d.append((f"{s} vero, ultime 20000 barre", reali[s].tail(20000)))
    for nome, dati in insiemi_d:
        rep = verifica_lookahead(dati, prepara=_prepara, tagli_per_condizione=8, riscaldamento=500,
                                 verbose=False).set_index("nome")
        check(f"D1. {nome}: la trappola (rango del corpo su finestra centrata) e' segnata LOOKAHEAD",
              rep.loc["T_RANGO_CENTRATO", "esito"] == "LOOKAHEAD",
              f"colonna della trappola: {rep.loc['t_rango_centrato', 'esito']}")
        esiti = {k: rep.loc[k, "esito"] for k in list(ENTRY_NUOVE) + list(COLONNE)}
        check(f"D2. {nome}: condizioni e colonne nuove OK (esercitate, nessun lookahead)",
              all(e == "OK" for e in esiti.values()), "" if all(e == "OK" for e in esiti.values()) else str(esiti))
    R.clear_registry()

    # =====================================================================
    print("\nE · RISCALDAMENTO: stesse condizioni da qualunque punto partano i dati\n" + "-" * 70)
    lungo = reali["EURUSD"].tail(40000) if reali["EURUSD"] is not None else mercato_sintetico("2023-01-01", "2024-03-01", seme=9)
    intero = _con_colonne(lungo)
    for partenza in (333, 7001):
        parziale = _con_colonne(lungo.iloc[partenza:])
        comune = parziale.index[3000:]
        sporche = {k: int((f(intero).loc[comune] != f(parziale).loc[comune]).sum()) for k, f in ENTRY_NUOVE.items()}
        sporche = {k: v for k, v in sporche.items() if v}
        check(f"E. partenza alla barra {partenza}: dopo 3000 barre condizioni identiche ({len(comune)} barre)",
              not sporche and len(comune) > 20000, str(sporche) if sporche else "")

    # =====================================================================
    print("\nF · I 9 SYMBOL DI dati/ (solo conteggi)\n" + "-" * 70)
    righe, tutte_ok = [], True
    for symbol, df in reali.items():
        if df is None:
            saltato(f"F. {symbol}", "manca il file di dati")
            continue
        d = _con_colonne(df)
        riga = {"symbol": symbol, "barre": len(d)}
        for k, f in ENTRY_NUOVE.items():
            s = f(d)
            riga[k.replace("_VSA", "").replace("_SHORT", " S")] = int(s.sum())
            tutte_ok &= bool(100 <= s.sum() < len(s) * 0.05)
        righe.append(riga)
    if righe:
        with pd.option_context("display.width", 220, "display.max_columns", 20):
            print("  (numero di eventi sullo storico intero)")
            print(pd.DataFrame(righe).set_index("symbol").to_string())
        check("F1. gira su tutti i symbol presenti; almeno 100 eventi per condizione", tutte_ok)
    if reali["EURUSD"] is not None:
        R.clear_registry()
        for k, f in ENTRY_NUOVE.items():
            R.register_entry(k, -1 if "SHORT" in k else 1)(f)
        deg = verifica_degenerazione(_con_colonne(reali["EURUSD"]), verbose=False).set_index("nome")
        nostri = deg.loc[[k for k in ENTRY_NUOVE if k in deg.index]]
        print(nostri[["esito"]].T.to_string())
        check("F2. verifica_degenerazione su EURUSD M15: tutte OK", len(nostri) == len(ENTRY_NUOVE)
              and (nostri["esito"] == "OK").all(), str(nostri["esito"].to_dict()))
        R.clear_registry()
    else:
        saltato("F2. verifica_degenerazione", "manca il file di dati")

    # =====================================================================
    print("\nG · REGISTRAZIONE\n" + "-" * 70)
    R.clear_registry()
    with contextlib.redirect_stdout(io.StringIO()):
        registra_trigger_long()
        registra_trigger_short()
    check("G1. E34 ed E35 nei dizionari dei trigger, con le funzioni giuste, e registrati nel motore",
          all((TRIGGER_SHORT if "SHORT" in k else TRIGGER_LONG).get(k) is f for k, f in ENTRY_NUOVE.items())
          and all(k in R.list_entries() for k in ENTRY_NUOVE))
    check("G2. le colonne nuove sono nell'elenco che il collaudo verifica", set(COLONNE) <= set(COLONNE_INDICATORI))
    R.clear_registry()
    if reali["EURUSD"] is not None:
        import engine.indicatori as I
        pezzo = reali["EURUSD"].head(6000)
        svuota_cache()
        con = aggiungi_indicatori(pezzo)
        originale = I.vsa_modulo_unico
        try:   # senza le colonne nuove: le righe devono essere le stesse
            I.vsa_modulo_unico = lambda df: pd.DataFrame(0.0, index=df.index, columns=["asta", "bias", "go", "sr"])
            svuota_cache()
            senza = I.aggiungi_indicatori(pezzo)
        finally:
            I.vsa_modulo_unico = originale
        altre = [c for c in senza.columns if c not in COLONNE]
        check("G3. aggiungi_indicatori: le colonne VSA non tolgono righe e non cambiano le altre",
              con.index.equals(senza.index) and all(c in con.columns for c in COLONNE)
              and con[altre].equals(senza[altre]), f"{len(con)} righe contro {len(senza)}")
    else:
        saltato("G3. righe di aggiungi_indicatori", "manca il file di dati")

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(main())
