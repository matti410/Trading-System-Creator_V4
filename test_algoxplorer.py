"""
Collaudo delle condizioni AlgoXplorer 0.1c (docs/50 §10, riga 13; scheda
approvata da Mattia il 17/10/2026; script Pine di Mattia e di un amico):

    engine/indicatori.py   heikin_ashi, pvsra_climax, algoxplorer
                           (colonne ha_open, ha_high, ha_low, ha_close, pvsra,
                           algox_segnale, algox_stato, algox_careful, algox_nv_careful)
    E32_ALGOX_CAREFUL_UP / E32_SHORT_ALGOX_CAREFUL_DOWN               con PVSRA
    E33_ALGOX_NOVOL_CAREFUL_UP / E33_SHORT_ALGOX_NOVOL_CAREFUL_DOWN   senza PVSRA
    X4_ALGOX_SELL / X4_SHORT_ALGOX_BUY                                coppia "ALGOX"
    F40_ALGOX_STATE_LONG / F40_ALGOX_STATE_SHORT                      coppia "ALGOX_STATE"

Sezioni (docs/50 §7):

    A  fedelta' a TradingView: il Pine (copia di collaudo, pine_sources/
       algoxplorer_0_1c_v5.pine e _forex_v5.pine) fatto girare con PineTS sulle
       stesse barre di EURUSD, BTCUSD e DE40, con e senza PVSRA
    B  le colonne contro una riscrittura indipendente e ingenua, barra per barra,
       con le variabili dello script (status, high_buy, massimi...)
    C  casi a risultato noto: candele costruite a mano (Buy, careful, Sell),
       PVSRA a mano, proprieta' della macchina (alternanza, un ingresso per ciclo)
    D  lookahead per troncamento (verifica_lookahead) con una trappola che sa gia'
       al Buy se l'ingresso careful arrivera' (le etichette ridisegnate dello
       script) e deve risultare LOOKAHEAD
    E  riscaldamento: stesse condizioni da qualunque punto partano i dati
    F  i 9 symbol di dati/ (solo conteggi) e verifica_degenerazione su EURUSD
    G  registrazione nel motore e righe di aggiungi_indicatori invariate

Si lancia da terminale, dalla cartella del progetto:

    python test_algoxplorer.py

(su Windows: PYTHONIOENCODING=utf-8). Il confronto con PineTS gira solo se ci
sono Node.js, strumenti_pinets/node_modules e i file Pine in pine_sources/
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
from engine.indicatori import (COLONNE_INDICATORI, aggiungi_indicatori, algoxplorer, heikin_ashi,
                               pvsra_climax)
from engine.livelli import svuota_cache
from entry_long import (TRIGGER_LONG, entry_algox_careful_up, entry_algox_novol_careful_up,
                        registra_trigger_long)
from entry_short import (TRIGGER_SHORT, entry_short_algox_careful_down,
                         entry_short_algox_novol_careful_down, registra_trigger_short)
from exit_long import EXIT_LONG, exit_algox_sell, registra_exit_long
from exit_short import EXIT_SHORT, exit_short_algox_buy, registra_exit_short
from filter_conditions import (FILTRI, filter_algox_state_long, filter_algox_state_short,
                               registra_filtri)

CARTELLA = os.path.dirname(os.path.abspath(__file__))
DATI = os.path.join(CARTELLA, "dati")
PINETS = os.path.join(CARTELLA, "strumenti_pinets")
PINE = os.path.join(CARTELLA, "pine_sources")
PINE_FILE = {True: "algoxplorer_0_1c_v5.pine", False: "algoxplorer_0_1c_forex_v5.pine"}
SYMBOL = ("EURUSD", "GBPUSD", "USDJPY", "NZDUSD", "BTCUSD", "US500", "USTEC", "XAUUSD", "DE40")
ENTRY_NUOVE = {"E32_ALGOX_CAREFUL_UP": entry_algox_careful_up,
               "E32_SHORT_ALGOX_CAREFUL_DOWN": entry_short_algox_careful_down,
               "E33_ALGOX_NOVOL_CAREFUL_UP": entry_algox_novol_careful_up,
               "E33_SHORT_ALGOX_NOVOL_CAREFUL_DOWN": entry_short_algox_novol_careful_down}
EXIT_NUOVE = {"X4_ALGOX_SELL": (exit_algox_sell, 1), "X4_SHORT_ALGOX_BUY": (exit_short_algox_buy, -1)}
FILTRI_NUOVI = {"F40_ALGOX_STATE_LONG": (filter_algox_state_long, 1, "ALGOX_STATE"),
                "F40_ALGOX_STATE_SHORT": (filter_algox_state_short, -1, "ALGOX_STATE")}
COLONNE = ("ha_open", "ha_high", "ha_low", "ha_close", "pvsra",
           "algox_segnale", "algox_stato", "algox_careful", "algox_nv_careful")


def _leggi(symbol: str) -> pd.DataFrame | None:
    percorso = os.path.join(DATI, f"{symbol}_M15.csv")
    if not os.path.exists(percorso):
        return None
    df = pd.read_csv(percorso, parse_dates=["Date"], index_col="Date")
    df = to_utc_index(df, "A_US_DST (NY+7h)", on_dst_gap="drop", verbose=False)
    return df[["Open", "High", "Low", "Close", "Volume"]]


def _con_colonne(df: pd.DataFrame) -> pd.DataFrame:
    """Solo le colonne AlgoXplorer, come le crea aggiungi_indicatori (prima del taglio)."""
    d = df.copy()
    for k, v in heikin_ashi(d).items():
        d[k] = v
    d["pvsra"] = pvsra_climax(d)
    a = algoxplorer(d)
    d["algox_segnale"], d["algox_stato"], d["algox_careful"] = a["segnale"], a["stato"], a["careful"]
    d["algox_nv_careful"] = algoxplorer(d, con_volume=False)["careful"]
    return d


# ---------------------------------------------------------------- PineTS --
def _pinets_disponibile() -> bool:
    return (shutil.which("node") is not None
            and os.path.isdir(os.path.join(PINETS, "node_modules", "pinets"))
            and all(os.path.exists(os.path.join(PINE, f)) for f in PINE_FILE.values()))


def _pinets(df: pd.DataFrame, file_pine: str, cartella_tmp: str) -> pd.DataFrame:
    """Il Pine con PineTS sulle barre di df; i plot (le colonne interne __labels__ & c. si scartano)."""
    dati = os.path.join(cartella_tmp, "dati.csv")
    uscita = os.path.join(cartella_tmp, "pine.csv")
    df.tz_localize(None).rename_axis("Date").to_csv(dati, date_format="%Y-%m-%d %H:%M:%S")
    subprocess.run(["node", "esegui_pine.mjs", dati, os.path.join(PINE, file_pine), uscita],
                   cwd=PINETS, check=True, capture_output=True, text=True)
    with open(uscita, newline="") as f:
        righe = list(csv.reader(f))
    k = next((i for i, x in enumerate(righe[0]) if x.startswith("__")), len(righe[0]))
    pine = pd.DataFrame([r[:k] for r in righe[1:]], columns=righe[0][:k]).set_index("Date")
    pine = pine.replace("", np.nan)
    pine.index = df.index
    return pine


# ------------------------------------------------ riscrittura indipendente --
def _riferimento(df: pd.DataFrame, con_volume: bool = True, barre_ema: int = 50) -> pd.DataFrame:
    """Lo script barra per barra, con i suoi nomi di variabile; nessuna funzione del progetto."""
    O, H, L, C, V = (df[k].to_numpy(dtype=float) for k in ("Open", "High", "Low", "Close", "Volume"))
    n = len(df)
    alfa = 2.0 / (barre_ema + 1)
    out = {k: np.zeros(n) for k in ("ha_open", "ha_high", "ha_low", "ha_close", "pvsra",
                                    "segnale", "stato", "careful")}
    haO = haC = haH = haL = None
    ema_h = ema_l = None
    status, high_buy, low_sell, massimi, minimi = "", None, None, None, None
    for i in range(n):
        prevH, prevL = haH, haL
        haC_n = (O[i] + H[i] + L[i] + C[i]) / 4
        haO = (O[i] + C[i]) / 2 if haO is None else (haO + haC) / 2
        haC = haC_n
        haH, haL = max(H[i], haO, haC), min(L[i], haO, haC)
        # ta.ema: media semplice delle prime barre_ema, poi la ricorsione
        if i == barre_ema - 1:
            ema_h, ema_l = sum(H[:barre_ema]) / barre_ema, sum(L[:barre_ema]) / barre_ema
        elif i >= barre_ema:
            ema_h, ema_l = alfa * H[i] + (1 - alfa) * ema_h, alfa * L[i] + (1 - alfa) * ema_l
        colore = 0
        if i >= 9:
            av = sum(V[i - 9:i + 1]) / 10
            v2 = [V[j] * (H[j] - L[j]) for j in range(i - 9, i + 1)]
            if V[i] >= av * 2 or v2[-1] >= max(v2):
                colore = 1 if C[i] > O[i] else -1
        buy = (ema_h is not None and prevH is not None and haC > ema_h and haH > haC and haC > prevH)
        sell = (ema_l is not None and prevL is not None and haC < ema_l and haH == haO and haC < prevL)
        if con_volume:
            buy, sell = buy and colore == 1, sell and colore == -1
        status_1 = status
        if buy and status_1 != "long":
            high_buy, low_sell, massimi, status = haH, None, 1, "long"
            out["segnale"][i] = 1
        if sell and status_1 != "short":
            low_sell, high_buy, minimi, status = haL, None, 1, "short"
            out["segnale"][i] = -1
        if high_buy is not None and haH > high_buy and status_1 == "long":
            massimi += 1
            if massimi == 2:
                out["careful"][i] = 1
        if low_sell is not None and haL < low_sell and status_1 == "short":
            minimi += 1
            if minimi == 2:
                out["careful"][i] = -1
        out["stato"][i] = 1 if status == "long" else (-1 if status == "short" else 0)
        out["ha_open"][i], out["ha_high"][i], out["ha_low"][i], out["ha_close"][i] = haO, haH, haL, haC
        out["pvsra"][i] = colore
    return pd.DataFrame(out, index=df.index)


def _trappola_entra_poi(df: pd.DataFrame) -> pd.Series:
    """Sulla barra del Buy sa gia' se il careful arrivera' prima del Sell ('Not enter' o 'Max profit')."""
    seg, car = df["algox_segnale"].to_numpy(), df["algox_careful"].to_numpy()
    esito = np.zeros(len(df), dtype=bool)
    for i in np.flatnonzero(seg == 1):
        j = i + 1
        while j < len(df) and seg[j] != -1:
            if car[j] == 1:
                esito[i] = True
                break
            j += 1
    return pd.Series(esito, index=df.index)


def _prepara(df: pd.DataFrame) -> pd.DataFrame:
    d = _con_colonne(df)
    d["t_entra_poi"] = _trappola_entra_poi(d).astype(float)
    return d


def _barre(righe, inizio="2024-01-08 08:00") -> pd.DataFrame:
    idx = pd.date_range(inizio, periods=len(righe), freq="15min", tz="UTC")
    return pd.DataFrame(righe, columns=["Open", "High", "Low", "Close", "Volume"], index=idx, dtype=float)


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
        saltato("A. confronto con PineTS", "mancano Node.js, strumenti_pinets/node_modules o i file in pine_sources/")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            for symbol in ("EURUSD", "BTCUSD", "DE40"):
                if reali[symbol] is None:
                    saltato(f"A. {symbol}", "manca il file di dati")
                    continue
                dati = reali[symbol].head(20000)
                ha = heikin_ashi(dati)
                pv = pvsra_climax(dati)
                for con_volume in (True, False):
                    p = _pinets(dati, PINE_FILE[con_volume], tmp)
                    num = {k: pd.to_numeric(p[k], errors="coerce").to_numpy(dtype=float) for k in p.columns}
                    versione = "con PVSRA" if con_volume else "senza PVSRA"
                    scarto = max(float(np.nanmax(np.abs(ha[k].to_numpy() - num[k]) / np.abs(num[k])))
                                 for k in ("ha_open", "ha_high", "ha_low", "ha_close"))
                    if con_volume:
                        check(f"A1. {symbol}: candele Heikin Ashi uguali a quelle di PineTS (scarto relativo < 1e-9)",
                              scarto < 1e-9, f"scarto massimo {scarto:.1e} (PineTS arrotonda a 10 decimali)")
                        check(f"A2. {symbol}: colore PVSRA identico su tutte le barre",
                              bool((pv.to_numpy() == num["pvsra"]).all()))
                    a = algoxplorer(dati, con_volume=con_volume)
                    mio = {"buy": a["segnale"].eq(1), "sell": a["segnale"].eq(-1), "stato": a["stato"],
                           "careful_long": a["careful"].eq(1), "careful_short": a["careful"].eq(-1)}
                    diverse = np.zeros(len(dati), dtype=bool)
                    for k, s in mio.items():
                        diverse |= s.astype(float).to_numpy() != num[k]
                    eventi = int(a["segnale"].ne(0).sum() + a["careful"].ne(0).sum())
                    if not diverse.any():
                        check(f"A3. {symbol} {versione}: Buy, Sell, stato e ingressi careful identici",
                              eventi > 100, f"{eventi} eventi su {len(dati)} barre")
                        continue
                    # una discordanza e' ammessa solo se nasce da un pareggio numerico (< 1e-9)
                    i = int(np.flatnonzero(diverse)[0])
                    margini = [abs(ha["ha_close"].iloc[i] - ha["ha_high"].iloc[i - 1]),
                               abs(ha["ha_close"].iloc[i] - ha["ha_low"].iloc[i - 1]),
                               abs(ha["ha_high"].iloc[i] - ha["ha_close"].iloc[i]),
                               abs(ha["ha_high"].iloc[i] - ha["ha_open"].iloc[i]),
                               abs(ha["ha_close"].iloc[i] - float(num["ema_high"][i])),
                               abs(ha["ha_close"].iloc[i] - float(num["ema_low"][i]))]
                    for livello, prezzo in (("#0", "ha_high"), ("#1", "ha_low")):
                        if livello in num and np.isfinite(num[livello][i]):
                            margini.append(abs(ha[prezzo].iloc[i] - num[livello][i]))
                    pareggio = min(margini) < 1e-9 * float(dati["Close"].iloc[i])
                    check(f"A3. {symbol} {versione}: identici salvo un pareggio numerico (< 1e-9) e le barre "
                          "che ne seguono", pareggio and diverse.sum() <= 0.01 * eventi,
                          f"{int(diverse.sum())} barre diverse su {eventi} eventi, la prima {dati.index[i]} "
                          f"(margine {min(margini):.1e})")

    # =====================================================================
    print("\nB · LE COLONNE CONTRO UNA RISCRITTURA INDIPENDENTE\n" + "-" * 70)
    insiemi_b = [("forex sintetico", forex)]
    for s in ("EURUSD", "BTCUSD"):
        if reali[s] is not None:
            insiemi_b.append((f"{s} vero, ultime 15000 barre", reali[s].tail(15000)))
        else:
            saltato(f"B. {s} vero", "manca il file di dati")
    for nome, dati in insiemi_b:
        d = _con_colonne(dati)
        for con_volume in (True, False):
            rif = _riferimento(dati, con_volume=con_volume)
            if con_volume:
                ha_ok = all(np.array_equal(d[k].to_numpy(), rif[k].to_numpy())
                            for k in ("ha_open", "ha_high", "ha_low", "ha_close", "pvsra"))
                check(f"B1. {nome}: candele HA e PVSRA identiche alla riscrittura", ha_ok)
                mio = d[["algox_segnale", "algox_stato", "algox_careful"]].to_numpy()
            else:
                mio = algoxplorer(dati, con_volume=False)[["segnale", "stato", "careful"]].to_numpy()
            uguale = np.array_equal(mio, rif[["segnale", "stato", "careful"]].to_numpy())
            check(f"B2. {nome} {'con' if con_volume else 'senza'} PVSRA: segnali, stato e careful identici",
                  uguale and (rif["segnale"] != 0).sum() > 10,
                  f"{int((rif['segnale'] != 0).sum())} segnali, {int((rif['careful'] != 0).sum())} ingressi")
        check(f"B3. {nome}: la colonna algox_nv_careful e' la versione senza PVSRA",
              np.array_equal(d["algox_nv_careful"].to_numpy(), _riferimento(dati, con_volume=False)["careful"].to_numpy()))

    # =====================================================================
    print("\nC · CASI A RISULTATO NOTO\n" + "-" * 70)
    piatto = [[1.0, 1.0005, 0.9995, 1.0, 100]] * 60
    storia = piatto + [
        [1.000, 1.020, 1.000, 1.015, 1000],   # 60: Buy (climax lime, rompe il massimo HA, sopra la EMA)
        [1.015, 1.018, 1.012, 1.016, 100],    # 61: massimo HA 1.018 sotto il livello 1.020: niente
        [1.016, 1.030, 1.015, 1.028, 100],    # 62: massimo HA 1.030 > 1.020: ingresso careful long
        [1.028, 1.035, 1.026, 1.034, 100],    # 63: gia' entrato: niente
        [1.000, 1.000, 0.950, 0.955, 2000],   # 64: Sell (climax rosso, nessuna ombra superiore HA)
        [0.955, 0.960, 0.940, 0.945, 100],    # 65: minimo HA 0.94 sotto il livello: ingresso careful short
    ]
    caso = _con_colonne(_barre(storia))
    seg = caso["algox_segnale"].to_numpy()[60:]
    car = caso["algox_careful"].to_numpy()[60:]
    sta = caso["algox_stato"].to_numpy()[60:]
    check("C1. candele a mano: Buy alla 60, Sell alla 64, nient'altro",
          list(seg) == [1, 0, 0, 0, -1, 0] and (caso["algox_segnale"].to_numpy()[:60] == 0).all(), str(list(seg)))
    check("C2. careful: long alla 62 (prima rottura del massimo HA del Buy), short alla 65",
          list(car) == [0, 0, 1, 0, 0, -1], str(list(car)))
    check("C3. stato: long dal Buy, short dal Sell; F40 e X4 seguono",
          list(sta) == [1, 1, 1, 1, -1, -1]
          and filter_algox_state_long(caso).to_numpy()[60:].tolist() == [True] * 4 + [False] * 2
          and exit_algox_sell(caso).to_numpy()[60:].tolist() == [False] * 4 + [True, False]
          and exit_short_algox_buy(caso).to_numpy()[60:].tolist() == [True] + [False] * 5)
    check("C4. le entry E32 leggono la colonna careful (long alla 62, short alla 65)",
          np.flatnonzero(entry_algox_careful_up(caso).to_numpy()).tolist() == [62]
          and np.flatnonzero(entry_short_algox_careful_down(caso).to_numpy()).tolist() == [65])
    # senza volume climax il Buy non c'e', senza PVSRA si'
    muto = [r[:4] + [100] for r in storia]
    muto[60] = [1.000, 1.020, 1.000, 1.015, 100]
    muto[59] = [1.0, 1.0005, 0.9995, 1.0, 100000]          # una barra prima con volume x range enorme
    mc = _con_colonne(_barre(muto))
    check("C5. Buy senza climax PVSRA: nessun segnale con PVSRA, segnale e careful senza PVSRA",
          mc["algox_segnale"].iloc[60] == 0 and mc["algox_careful"].iloc[62] == 0
          and algoxplorer(mc, con_volume=False)["segnale"].iloc[60] == 1
          and mc["algox_nv_careful"].iloc[62] == 1,
          f"pvsra alla 60: {mc['pvsra'].iloc[60]}")
    # "Not enter": il prezzo non supera il livello prima del Sell
    mai = storia[:62] + [[1.016, 1.019, 1.010, 1.012, 100], storia[64]]
    nm = _con_colonne(_barre(mai))
    check("C6. 'Not enter': senza rottura del livello prima del Sell, nessun ingresso long",
          nm["algox_careful"].to_numpy()[60:].tolist() == [0, 0, 0, 0] and nm["algox_segnale"].iloc[63] == -1)
    # PVSRA a mano
    pv = [[1.0, 1.001, 1.0, 1.0005, 100]] * 20 + [[1.0, 1.0005, 1.0, 1.0004, 150],
                                                [1.0, 1.0005, 1.0, 1.0004, 250],
                                                [1.0004, 1.0005, 1.0, 1.0001, 250]]
    pvc = pvsra_climax(_barre(pv)).to_numpy()
    check("C7. PVSRA a mano: 150 su media 105 no; 250 su media 120 si' (rialzista); poi volume x range al massimo delle 10, pareggio compreso (ribassista)",
          pvc[20] == 0 and pvc[21] == 1 and pvc[22] == -1 and (pvc[:9] == 0).all(), str(pvc[19:].tolist()))
    # proprieta' della macchina su dati veri (o sintetici)
    grande = _con_colonne(reali["EURUSD"].tail(40000) if reali["EURUSD"] is not None else forex)
    for col_seg, col_car, nome in (("algox_segnale", "algox_careful", "con PVSRA"),):
        s, c, st = grande[col_seg].to_numpy(), grande[col_car].to_numpy(), grande["algox_stato"].to_numpy()
        nz = s[s != 0]
        alterna = bool(len(nz) > 10 and (nz[1:] != nz[:-1]).all())
        cicli_ok, prima_ok = True, True
        posizioni = np.flatnonzero(s != 0)
        for a, b in zip(posizioni, np.r_[posizioni[1:], len(s)]):
            entrate = np.flatnonzero(c[a:b] != 0)
            if len(entrate) > 1 or (len(entrate) and (entrate[0] == 0 or c[a + entrate[0]] != s[a])):
                cicli_ok = False
            if len(entrate):           # e' la PRIMA rottura del livello
                livello = grande["ha_high"].iloc[a] if s[a] == 1 else grande["ha_low"].iloc[a]
                tratto = grande["ha_high"].iloc[a + 1:a + entrate[0] + 1] if s[a] == 1 else -grande["ha_low"].iloc[a + 1:a + entrate[0] + 1]
                soglia = livello if s[a] == 1 else -livello
                rotte = np.flatnonzero(tratto.to_numpy() > soglia)
                prima_ok &= bool(len(rotte) and rotte[0] == entrate[0] - 1)
        check(f"C8. {nome}: i segnali si alternano Buy/Sell", alterna, f"{len(nz)} segnali")
        check(f"C9. {nome}: al massimo un ingresso careful per ciclo, nel verso del segnale, mai sulla barra del segnale",
              cicli_ok)
        check(f"C10. {nome}: l'ingresso e' la prima rottura del livello", prima_ok)
        senza = int(sum(1 for a, b in zip(posizioni, np.r_[posizioni[1:], len(s)]) if not (c[a:b] != 0).any()))
        check(f"C11. {nome}: ci sono cicli 'Not enter' e lo stato coincide col segno dell'ultimo segnale",
              senza > 0 and bool((st[posizioni[0]:] == pd.Series(np.where(s != 0, s, np.nan)).ffill().to_numpy()[posizioni[0]:]).all()),
              f"{senza} cicli senza ingresso su {len(posizioni)}")
    sell = grande["algox_segnale"] == -1
    check("C12. sulle barre del Sell il massimo HA e' l'apertura HA (lo short non e' lo speculare del long)",
          bool((grande.loc[sell, "ha_high"] == grande.loc[sell, "ha_open"]).all()
               and (grande.loc[grande["algox_segnale"] == 1, "ha_high"] > grande.loc[grande["algox_segnale"] == 1, "ha_close"]).all()))

    # =====================================================================
    print("\nD · LOOKAHEAD PER TRONCAMENTO\n" + "-" * 70)
    R.clear_registry()
    for k, (f, direzione, coppia) in FILTRI_NUOVI.items():
        R.register_filter(k, direction=direzione, pair=coppia)(f)
    for k, f in ENTRY_NUOVE.items():
        R.register_entry(k, -1 if "SHORT" in k else 1)(f)
    for k, (f, direzione) in EXIT_NUOVE.items():
        R.register_exit(k, direction=direzione, pair="ALGOX")(f)
    R.register_filter("T_ENTRA_POI")(lambda df: df["t_entra_poi"] > 0)
    insiemi_d = [("forex sintetico", forex)]
    if reali["EURUSD"] is not None:
        insiemi_d.append(("EURUSD vero, ultime 20000 barre", reali["EURUSD"].tail(20000)))
    if reali["BTCUSD"] is not None:
        insiemi_d.append(("BTCUSD vero, ultime 20000 barre", reali["BTCUSD"].tail(20000)))
    for nome, dati in insiemi_d:
        rep = verifica_lookahead(dati, prepara=_prepara, tagli_per_condizione=8, riscaldamento=500,
                                 verbose=False).set_index("nome")
        # la colonna della trappola si prova solo sui tagli comuni, che possono non cadere su un Buy
        # in attesa (su EURUSD succede): decide la condizione, che ha anche i tagli mirati
        check(f"D1. {nome}: la trappola (sapere al Buy se il careful arrivera') e' segnata LOOKAHEAD",
              rep.loc["T_ENTRA_POI", "esito"] == "LOOKAHEAD",
              f"colonna della trappola: {rep.loc['t_entra_poi', 'esito']}")
        nomi = list(FILTRI_NUOVI) + list(ENTRY_NUOVE) + list(EXIT_NUOVE) + list(COLONNE)
        esiti = {k: rep.loc[k, "esito"] for k in nomi}
        check(f"D2. {nome}: condizioni e colonne nuove OK (esercitate, nessun lookahead)",
              all(e == "OK" for e in esiti.values()), "" if all(e == "OK" for e in esiti.values()) else str(esiti))
    R.clear_registry()

    # =====================================================================
    print("\nE · RISCALDAMENTO: stesse condizioni da qualunque punto partano i dati\n" + "-" * 70)
    lungo = reali["EURUSD"].tail(40000) if reali["EURUSD"] is not None else mercato_sintetico("2023-01-01", "2024-03-01", seme=9)
    intero = _con_colonne(lungo)
    condizioni = {**ENTRY_NUOVE, **{k: f for k, (f, _) in EXIT_NUOVE.items()},
                  **{k: f for k, (f, _, _) in FILTRI_NUOVI.items()}}
    for partenza in (333, 7001):
        parziale = _con_colonne(lungo.iloc[partenza:])
        # dopo il primo segnale comune la macchina e' la stessa; le candele HA e la EMA convergono prima
        comune = parziale.index[3000:]
        sporche = {k: int((f(intero).loc[comune] != f(parziale).loc[comune]).sum()) for k, f in condizioni.items()}
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
        for k, f in condizioni.items():
            s = f(d).fillna(False)
            breve = k.replace("_ALGOX", "").replace("_CAREFUL", "").replace("_STATE", "")
            riga[breve] = round(100 * s.mean(), 1) if k in FILTRI_NUOVI else int(s.sum())
            tetto = 0.7 if k in FILTRI_NUOVI else 0.02
            tutte_ok &= bool(100 <= s.sum() < len(s) * tetto)
        righe.append(riga)
    if righe:
        with pd.option_context("display.width", 220, "display.max_columns", 20):
            print("  (F40: % di barre vere; entry e uscite: numero di eventi)")
            print(pd.DataFrame(righe).set_index("symbol").to_string())
        check("F1. gira su tutti i symbol presenti; almeno 100 eventi e nessuna condizione quasi sempre vera", tutte_ok)
    if reali["EURUSD"] is not None:
        R.clear_registry()
        for k, (f, direzione, coppia) in FILTRI_NUOVI.items():
            R.register_filter(k, direction=direzione, pair=coppia)(f)
        for k, f in ENTRY_NUOVE.items():
            R.register_entry(k, -1 if "SHORT" in k else 1)(f)
        for k, (f, direzione) in EXIT_NUOVE.items():
            R.register_exit(k, direction=direzione, pair="ALGOX")(f)
        deg = verifica_degenerazione(_con_colonne(reali["EURUSD"]), verbose=False).set_index("nome")
        nostri = deg.loc[[k for k in condizioni if k in deg.index]]
        print(nostri[["esito"]].T.to_string())
        check("F2. verifica_degenerazione su EURUSD M15: tutte OK", len(nostri) == len(condizioni)
              and (nostri["esito"] == "OK").all(), str(nostri["esito"].to_dict()))
        R.clear_registry()
    else:
        saltato("F2. verifica_degenerazione", "manca il file di dati")

    # =====================================================================
    print("\nG · REGISTRAZIONE\n" + "-" * 70)
    R.clear_registry()
    with contextlib.redirect_stdout(io.StringIO()):
        registra_filtri()
        registra_trigger_long()
        registra_trigger_short()
        registra_exit_long()
        registra_exit_short()
    check("G1. F40 registrato come coppia ALGOX_STATE (+1 / -1)",
          all(k in R.list_filters(direction=d) and R.get_filter_pair(k) == p for k, (_, d, p) in FILTRI_NUOVI.items())
          and ("ALGOX_STATE", "F40_ALGOX_STATE_LONG", "F40_ALGOX_STATE_SHORT") in R.list_filter_pairs())
    check("G2. X4 registrata come coppia ALGOX",
          ("ALGOX", "X4_ALGOX_SELL", "X4_SHORT_ALGOX_BUY") in R.list_exit_pairs())
    check("G3. E32 ed E33 nei dizionari dei trigger, con le funzioni giuste",
          all((TRIGGER_SHORT if "SHORT" in k else TRIGGER_LONG).get(k) is f for k, f in ENTRY_NUOVE.items())
          and all(k in R.list_entries() for k in ENTRY_NUOVE))
    check("G4. nei dizionari: F40 e X4 con funzione, direzione e coppia giuste",
          all(FILTRI[k] == v for k, v in FILTRI_NUOVI.items())
          and EXIT_LONG["X4_ALGOX_SELL"] == (exit_algox_sell, "ALGOX")
          and EXIT_SHORT["X4_SHORT_ALGOX_BUY"] == (exit_short_algox_buy, "ALGOX"))
    check("G5. le colonne nuove sono nell'elenco che il collaudo verifica", set(COLONNE) <= set(COLONNE_INDICATORI))
    R.clear_registry()
    if reali["EURUSD"] is not None:
        import engine.indicatori as I
        pezzo = reali["EURUSD"].head(6000)
        svuota_cache()
        con = aggiungi_indicatori(pezzo)
        originali = I.heikin_ashi, I.pvsra_climax, I.algoxplorer
        try:   # senza le colonne nuove: le righe devono essere le stesse
            I.heikin_ashi = lambda df: pd.DataFrame(0.0, index=df.index, columns=["ha_open", "ha_high", "ha_low", "ha_close"])
            I.pvsra_climax = lambda df: pd.Series(0.0, index=df.index)
            I.algoxplorer = lambda df, **k: pd.DataFrame(0.0, index=df.index, columns=["segnale", "stato", "careful"])
            svuota_cache()
            senza = I.aggiungi_indicatori(pezzo)
        finally:
            I.heikin_ashi, I.pvsra_climax, I.algoxplorer = originali
        altre = [c for c in senza.columns if c not in COLONNE]
        check("G6. aggiungi_indicatori: le colonne AlgoXplorer non tolgono righe e non cambiano le altre",
              con.index.equals(senza.index) and all(c in con.columns for c in COLONNE)
              and con[altre].equals(senza[altre]), f"{len(con)} righe contro {len(senza)}")
    else:
        saltato("G6. righe di aggiungi_indicatori", "manca il file di dati")

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(main())
