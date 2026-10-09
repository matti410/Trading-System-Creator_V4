"""
Suite di validazione di engine/vetrina_trigger.py e della lente 7b (9/10/2026).

Cosa verifica
-------------
La lente ora disegna, per ogni trigger scattato, il suo nome, le candele della
figura, la linea del livello e gli indicatori che la regola legge. Le tabelle
di engine/vetrina_trigger.py non sono scritte a memoria: qui si MISURANO sui
dati. Cosi' se una tabella e' sbagliata, o se TA-Lib cambia, il test lo dice.

  A · le candele: per ogni figura/regola si spostano le candele una alla volta
      e si guarda quando il segnale sparisce. Le candele dichiarate devono
      farlo sparire sempre; quelle subito prima, quasi mai.
  B · gli indicatori: si spegne (NaN) una colonna alla volta. Le colonne
      dichiarate devono azzerare il trigger; tutte le altre non devono
      cambiare nulla. Le colonne dichiarate sono ESATTAMENTE quelle lette.
  C · i livelli: la linea disegnata e' quella che il trigger ha rotto.
  D · il catalogo: nessun trigger nuovo resta senza una riga nelle tabelle,
      salvo quelli che per scelta hanno solo nome e candela del segnale.
  E · la lente su BTCUSD, dall'inizio alla fine: il tuo caso (E21 + E22) e un
      secondo sistema con trigger di ogni famiglia. Nessun numero della
      strategia cambia, e con la spunta spenta il grafico e' quello di prima.

Come si lancia (da terminale, dalla cartella del progetto):

    python test_vetrina_trigger.py

Su Colab, in una cella:   !python test_vetrina_trigger.py

Servono BTCUSD_M15.csv ed EURUSD_M15.csv nella cartella del progetto (ci sono
gia' nel repo) e plotly. Dura circa cinque minuti (il grosso e' la sezione E,
che costruisce due volte la strategia). Alla fine stampa
«RISULTATO: N/N test superati».
"""
from __future__ import annotations

import contextlib
import io
import sys
import warnings

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")

import engine.registry as reg
import engine.vetrina as v
from engine import vetrina_trigger as vt
from engine.indicatori import COLONNE_INDICATORI
from engine.livelli import range_finestra
from engine.vetrina_verifica import lente, registro_trade

ECCEZIONI_ATTESE = {          # trigger che hanno per scelta solo nome + candela del segnale
    "E3_LONG_INTRABAR_WEAKNESS_FADE", "E3_SHORT_INTRABAR_STRENGTH_FADE",
    "E7_BIG_TAIL_BARS", "E7_SHORT_BIG_TAIL_BARS",
    "E27_VSA_BULLISH", "E27_SHORT_VSA_BEARISH",
}
W = 60                        # candele di contesto per il test delle candele
N_RILEVAZIONI = 40
OHLC = ["Open", "High", "Low", "Close"]


def muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def registra_tutto():
    import entry_long
    import entry_short
    muto(entry_long.registra_trigger_long)
    muto(entry_short.registra_trigger_short)


# ---------------------------------------------------------------- sezione A --
def tassi_candele(nome, df, rng, distanze):
    """
    Per le rilevazioni di `nome`: quota di casi in cui il segnale sparisce
    quando si altera la candela a distanza d dal segnale.
      spostata   la candela e' alzata o abbassata del 5% del prezzo (la sua
                 forma non cambia: sparisce solo se conta il suo POSTO
                 rispetto alle altre)
      qualsiasi  spostata, oppure appiattita (una candela senza corpo)
    """
    f = reg.get_entry(nome)
    ok = f(df).fillna(False).astype(bool).to_numpy()
    det = np.flatnonzero(ok)
    det = det[det > W]
    if len(det) < 5:
        return None
    det = rng.choice(det, size=min(N_RILEVAZIONI, len(det)), replace=False)
    spostata = {d: 0 for d in distanze}
    qualsiasi = {d: 0 for d in distanze}
    for i in det:
        base = df.iloc[i - W:i + 1][OHLC].reset_index(drop=True)
        base["Volume"] = 1.0
        for d in distanze:
            k = W - d
            sparito = {}
            for modo in ("su", "giu", "piatta"):
                x = base.copy()
                if modo == "piatta":
                    x.loc[k, OHLC] = x.loc[k, OHLC].mean()
                else:
                    delta = 0.05 * x.loc[k, "Close"] * (1 if modo == "su" else -1)
                    x.loc[k, OHLC] = x.loc[k, OHLC] + delta
                sparito[modo] = not bool(f(x).fillna(False).astype(bool).iloc[-1])
            spostata[d] += sparito["su"] or sparito["giu"]
            qualsiasi[d] += any(sparito.values())
    n = len(det)
    return {d: spostata[d] / n for d in distanze}, {d: qualsiasi[d] / n for d in distanze}, n


def distanze_dichiarate(nome):
    if nome in vt._FIGURE:
        return tuple(range(vt._FIGURE[nome]))
    return tuple(vt._BARRE[nome])


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    registra_tutto()
    esistenti = set(reg.list_entries())

    # ================================================================== A ==
    print("\nA · Le candele: quante ne servono davvero a ciascun trigger (misurato sui dati)")
    ohlc_soltanto = [n for n in list(vt._FIGURE) + list(vt._BARRE)
                     if n in esistenti and (n in vt._FIGURE or n.split("_")[0] in ("E5", "E6", "E8", "E9"))]
    check("1. ogni trigger delle tabelle esiste nel registro",
          all(n in esistenti for n in list(vt._FIGURE) + list(vt._BARRE) + list(vt._INDICATORI)
              + list(vt._LIVELLI_FINESTRA) + list(vt._LIVELLI_CANDELA)),
          ", ".join(n for n in list(vt._FIGURE) + list(vt._BARRE) + list(vt._INDICATORI)
                    + list(vt._LIVELLI_FINESTRA) + list(vt._LIVELLI_CANDELA) if n not in esistenti) or "tutti presenti")
    rng = np.random.default_rng(7)
    sbagliati_dich, sbagliati_fuori, saltati = [], [], []
    for simbolo in ("BTCUSD", "EURUSD"):
        dati = pd.read_csv(f"{simbolo}_M15.csv", index_col="Date")
        for nome in ohlc_soltanto:
            dich = distanze_dichiarate(nome)
            fuori = [d for d in range(0, max(dich) + 3) if d not in dich]
            r = tassi_candele(nome, dati, rng, list(dich) + fuori)
            if r is None:
                saltati.append(f"{nome}/{simbolo}")
                continue
            spostata, qualsiasi, n = r
            for d in dich:
                if qualsiasi[d] < 0.95:
                    sbagliati_dich.append(f"{nome}/{simbolo} d={d}: {qualsiasi[d]:.0%}")
            for d in fuori:
                if spostata[d] > 0.30:
                    sbagliati_fuori.append(f"{nome}/{simbolo} d={d}: {spostata[d]:.0%}")
        print(f"     · {simbolo} misurato su {len(ohlc_soltanto)} trigger")
    check("2. le candele dichiarate fanno sparire il segnale quando le tocchi (>= 95%)",
          not sbagliati_dich, "; ".join(sbagliati_dich[:6]) or f"{len(ohlc_soltanto)} trigger x 2 strumenti")
    check("3. le candele NON dichiarate lasciano il segnale al suo posto (<= 30% di eccezioni)",
          not sbagliati_fuori,
          "; ".join(sbagliati_fuori[:6]) or "le poche eccezioni sono l'effetto «prima barra di un blocco» di _evento")
    check("4. poche rilevazioni = trigger saltato, ma solo se e' raro (< 5 casi)",
          len(saltati) <= 2, ", ".join(saltati) or "nessun trigger saltato")

    # ================================================================== B ==
    print("\nB · Gli indicatori: le colonne dichiarate sono esattamente quelle che il trigger legge")
    s0 = muto(v.prepara, "BTCUSD", 25)
    df = s0.df
    check("5. i dati hanno tutte le colonne indicatore", all(c in df.columns for c in COLONNE_INDICATORI))
    male_dich, male_altre, zero_det = [], [], []
    for nome, colonne in vt._INDICATORI.items():
        base = reg.get_entry(nome)(df).fillna(False).astype(bool)
        if base.sum() == 0:
            zero_det.append(nome)
            continue
        for c in COLONNE_INDICATORI:
            x = df.copy()
            x[c] = np.nan
            out = reg.get_entry(nome)(x).fillna(False).astype(bool)
            if c in colonne and out.sum() != 0:
                male_dich.append(f"{nome} con {c} spenta: {int(out.sum())} segnali")
            if c not in colonne and not out.equals(base):
                male_altre.append(f"{nome} legge anche {c}")
    check("6. ogni trigger con indicatori ha segnali su BTCUSD per essere provato", not zero_det,
          ", ".join(zero_det) or f"{len(vt._INDICATORI)} trigger")
    check("7. spegnendo una colonna dichiarata il trigger non scatta piu'", not male_dich,
          "; ".join(male_dich[:4]) or "tutte le colonne dichiarate servono")
    check("8. spegnendo una colonna NON dichiarata non cambia niente (nessuna colonna dimenticata)",
          not male_altre, "; ".join(male_altre[:4]) or "nessuna colonna letta e non dichiarata")

    # soglie: le linee di riferimento sono quelle vere
    pos = int(np.flatnonzero(reg.get_entry("E1_RSI_CROSS_OVERSOLD")(df).to_numpy())[100])
    posc = int(np.flatnonzero(reg.get_entry("E1_SHORT_RSI_CROSS_OVERBOUGHT")(df).to_numpy())[100])
    check("9. soglia RSI letta dal trigger: 30 per il long, 70 per lo short",
          vt.descrivi_trigger("E1_RSI_CROSS_OVERSOLD", df, pos, pos - 20, pos + 20).soglie == {"rsi": 30.0}
          and vt.descrivi_trigger("E1_SHORT_RSI_CROSS_OVERBOUGHT", df, posc, posc - 20, posc + 20).soglie == {"rsi": 70.0})
    ok_zero = True
    for nome, colonna, segno in (("E24_CYCLE_TURN_UP", "ciclo_pendenza", 1),
                                 ("E24_SHORT_CYCLE_TURN_DOWN", "ciclo_pendenza", -1),
                                 ("E25_ATC_PVO_SETUP_UP", "pvo_hist", 1),
                                 ("E25_SHORT_ATC_PVO_SETUP_DOWN", "pvo_hist", -1),
                                 ("E26_SUPERTREND_IIX_SETUP_UP", "iix", 1),
                                 ("E26_SHORT_SUPERTREND_IIX_SETUP_DOWN", "iix", -1)):
        det = np.flatnonzero(reg.get_entry(nome)(df).to_numpy())
        ok_zero &= bool((df[colonna].iloc[det].to_numpy() * segno > 0).all())
        ok_zero &= vt._SOGLIE_FISSE[colonna] == 0.0
    check("10. la linea dello zero e' davvero la soglia: sui segnali la colonna e' dal lato giusto dello zero", ok_zero)

    # ================================================================== C ==
    print("\nC · I livelli: la linea disegnata e' quella che il trigger ha rotto")
    male_liv = []
    for nome, (argomenti, colonna, testo) in vt._LIVELLI_FINESTRA.items():
        det = np.flatnonzero(reg.get_entry(nome)(df).to_numpy())
        livello = range_finestra(df, *argomenti)[colonna].to_numpy(dtype=float)
        lungo = "massimo" in colonna
        for pos in det[::max(1, len(det) // 150)]:
            ini, fin = max(0, pos - 40), min(len(df) - 1, pos + 30)
            d = vt.descrivi_trigger(nome, df, pos, ini, fin)
            if len(d.livelli) != 1:
                male_liv.append(f"{nome} pos {pos}: {len(d.livelli)} livelli")
                continue
            y = d.livelli[0][1]
            vero = livello[ini:fin + 1]
            presenti = np.isfinite(y)
            rotto = df["Close"].iloc[pos] > livello[pos] if lungo else df["Close"].iloc[pos] < livello[pos]
            if (len(y) != fin - ini + 1 or not presenti[pos - ini] or not np.allclose(y[presenti], vero[presenti])
                    or not np.allclose(y[presenti], livello[pos]) or not rotto):
                male_liv.append(f"{nome} pos {pos}")
    check("11. E22/E23: il livello disegnato vale quello di range_finestra, la chiusura del segnale lo rompe",
          not male_liv, "; ".join(male_liv[:4]) or "tutti i segnali controllati")

    ok = True
    for nome, (colonna, dist, testo) in vt._LIVELLI_CANDELA.items():
        det = np.flatnonzero(reg.get_entry(nome)(df).to_numpy())
        for pos in det[:200]:
            d = vt.descrivi_trigger(nome, df, pos, pos - 10, pos + 10)
            y = d.livelli[0][1]
            presenti = np.flatnonzero(np.isfinite(y)) + (pos - 10)
            ok &= list(presenti) == [pos - 2, pos - 1, pos] and np.allclose(y[np.isfinite(y)], df[colonna].iloc[pos - dist])
            ok &= (df["Close"].iloc[pos] > df[colonna].iloc[pos - dist]) if colonna == "High" \
                else (df["Close"].iloc[pos] < df[colonna].iloc[pos - dist])
    check("12. E5: la linea e' il massimo/minimo di 2 candele prima e la chiusura lo rompe", ok)
    sul_bordo = vt.descrivi_trigger("E22_ASIAN_RANGE_BREAKOUT", df, 5, 0, 30)
    check("13. segnale vicino all'inizio dei dati: nessun errore", isinstance(sul_bordo, vt.Disegno))

    # ================================================================== D ==
    print("\nD · Il catalogo")
    veri = sorted(n for n in esistenti if n[:1] == "E" and n[1:2].isdigit())
    senza = sorted(set(veri) - vt.trigger_con_disegno())
    check("14. ogni trigger del catalogo ha una riga nelle tabelle, salvo le eccezioni dichiarate",
          set(senza) == ECCEZIONI_ATTESE,
          f"senza disegno dedicato: {', '.join(senza)}" if set(senza) != ECCEZIONI_ATTESE else
          f"{len(veri) - len(senza)} con disegno, {len(senza)} solo nome + candela")
    sconosciuto = vt.descrivi_trigger("TRIGGER_INVENTATO", df, 500, 460, 530)
    check("15. un trigger sconosciuto non da' errore: nome + candela del segnale",
          sconosciuto.barre == (500,) and not sconosciuto.livelli and not sconosciuto.indicatori)
    ok = True
    for nome in veri:
        det = np.flatnonzero(reg.get_entry(nome)(df).fillna(False).to_numpy(dtype=bool))
        if len(det) == 0:
            continue
        pos = int(det[len(det) // 2])
        d = vt.descrivi_trigger(nome, df, pos, pos - 40, pos + 30)
        ok &= all(0 <= b <= pos for b in d.barre) and all(c in df.columns for c in d.indicatori)
    check("16. per ogni trigger scattato: candele non oltre il segnale, indicatori che esistono nei dati", ok)

    # ================================================================== E ==
    print("\nE · La lente su BTCUSD, dall'inizio alla fine")

    def costruisci(trig_long, trig_short, filtro):
        s = muto(v.prepara, "BTCUSD", 25)
        muto(v.esplora, s)
        muto(v.classifiche, s)
        muto(v.scegli_trigger, s, long=trig_long, short=trig_short)
        muto(v.imposta_uscite, s, barre_long=25, barre_short=25, sl=90, tp=0)
        muto(v.trova_strategia, s)
        muto(v.scheda, s, filtro=filtro)
        return s

    # ---- E1: il caso del notebook (E21 + E22) ---------------------------------
    print("  costruisco il sistema E21 + E22 (circa un minuto)...")
    s = costruisci("E21_BELT_HOLD, E22_ASIAN_RANGE_BREAKOUT", "", "F6_VOLUME_ABOVE_AVG_50, F2_HIGH_VOLATILITY")
    oos_prima, is_prima = s.trades_oos.copy(deep=True), s.trades_is.copy(deep=True)
    r = registro_trade(s, "out-of-sample")
    n_e21 = int(r.index[r["Trigger scattato"] == "E21_BELT_HOLD"][0]) + 1
    n_e22 = int(r.index[r["Trigger scattato"] == "E22_ASIAN_RANGE_BREAKOUT"][0]) + 1
    n_due = int(r.index[r["Trigger scattato"] == "E21_BELT_HOLD, E22_ASIAN_RANGE_BREAKOUT"][0]) + 1

    def segnale(fig):
        return [t for t in fig.data if t.name == "segnale"][0]

    def livelli(fig):
        return [t for t in fig.data if t.name and t.name.startswith(("massimo", "minimo"))]

    f21 = muto(lente, s, numero=n_e21, indicatori="")
    f22 = muto(lente, s, numero=n_e22, indicatori="")
    f2 = muto(lente, s, numero=n_due, indicatori="")
    check("17. il triangolo porta il nome del trigger (E21, E22, e tutti e due)",
          segnale(f21).text == ("E21_BELT_HOLD",) and segnale(f22).text == ("E22_ASIAN_RANGE_BREAKOUT",)
          and segnale(f2).text == ("E21_BELT_HOLD, E22_ASIAN_RANGE_BREAKOUT",))
    pos21 = int(r.loc[n_e21 - 1, "barra_segnale"])
    a21 = max(0, pos21 - 40)
    check("18. E21: una banda sola, sulla candela del segnale",
          len(f21.layout.shapes) == 1 and f21.layout.shapes[0].x0 == pos21 - a21 - 0.5
          and f21.layout.shapes[0].x1 == pos21 - a21 + 0.5 and not livelli(f21))
    liv = livelli(f22)
    pos22 = int(r.loc[n_e22 - 1, "barra_segnale"])
    a22 = max(0, pos22 - 40)
    y22 = np.asarray(liv[0].y, dtype=float) if liv else np.array([np.nan])
    chiusura22 = float(s.df_oos["Close"].iloc[pos22])
    finestra22 = s.df_oos.iloc[a22:a22 + len(liv[0].y)] if liv else s.df_oos.iloc[:1]
    check("19. E22: una linea sola, a un livello fisso sotto la chiusura del segnale, dentro la scala delle candele",
          len(liv) == 1 and len(np.unique(y22[np.isfinite(y22)])) == 1 and np.nanmax(y22) < chiusura22
          and finestra22["Low"].min() * 0.97 < np.nanmax(y22) < finestra22["High"].max() * 1.03
          and len(f22.layout.shapes) == 0)
    check("20. E21 + E22 sullo stesso segnale: una linea e una banda (niente bande doppie)",
          len(livelli(f2)) == 1 and len(f2.layout.shapes) == 1)

    f_off = muto(lente, s, numero=n_e22, indicatori="", mostra_trigger=False)
    f_on_ind = muto(lente, s, numero=n_e22, indicatori="rsi")
    f_off_ind = muto(lente, s, numero=n_e22, indicatori="rsi", mostra_trigger=False)
    comuni = [t.name for t in f_off.data if t.name]
    check("21. spunta spenta: scritta «segnale», nessuna banda, nessuna linea di livello",
          segnale(f_off).text == ("segnale",) and len(f_off.layout.shapes) == 0 and not livelli(f_off))
    def valori(fig):
        return {t.name: np.asarray(t.close if t.type == "candlestick" else t.y, dtype=float)
                for t in fig.data if t.name}

    v_off, v_on = valori(f_off), valori(f22)
    uguali = all(np.array_equal(v_off[n], v_on[n], equal_nan=True) for n in comuni)
    check("22. spunta accesa o spenta, candele, ingresso, uscita e stop sono gli stessi", uguali)
    check("23. con l'indicatore scelto a mano (rsi) la lente funziona uguale, in entrambi i modi",
          [t.name for t in f_on_ind.data if t.name == "rsi"] == ["rsi"]
          and [t.name for t in f_off_ind.data if t.name == "rsi"] == ["rsi"])
    check("24. nessun numero della strategia e' cambiato (trade in-sample e out-of-sample identici)",
          s.trades_oos.equals(oos_prima) and s.trades_is.equals(is_prima))

    # ---- E2: un sistema con trigger di ogni famiglia -------------------------
    print("  costruisco il secondo sistema, con trigger di ogni famiglia (circa un minuto)...")
    LONG = ["E12_ENGULFING", "E24_CYCLE_TURN_UP", "E5_QUICK_PULLBACK", "E1_RSI_CROSS_OVERSOLD", "E2_ZLEMA_CROSS_UP"]
    SHORT = ["E17_SHORT_THREE_INSIDE", "E25_SHORT_ATC_PVO_SETUP_DOWN", "E26_SHORT_SUPERTREND_IIX_SETUP_DOWN",
             "E23_SHORT_PREV_DAY_LOW_BREAKDOWN", "E9_SHORT_CLOSING_PATTERN_ONLY_II"]
    s2 = costruisci(", ".join(LONG), ", ".join(SHORT), "")
    r2 = registro_trade(s2, "out-of-sample")
    df2, _ = s2.df_oos, None
    fallite, viste = [], []
    for nome in LONG + SHORT:
        righe = r2.index[r2["Trigger scattato"].str.contains(nome, regex=False)]
        if len(righe) == 0:
            continue
        n = int(righe[0]) + 1
        riga = r2.iloc[n - 1]
        pos = int(riga["barra_segnale"])
        a = max(0, pos - 40)
        b = min(len(df2) - 1, int(riga["barra_uscita"]) + 20)
        try:
            fig = muto(lente, s2, numero=n, indicatori="", barre_prima=40, barre_dopo=20)
        except Exception as e:
            fallite.append(f"{nome}: {type(e).__name__} {str(e)[:80]}")
            continue
        d = vt.descrivi_trigger(nome, df2, pos, a, b)
        finestra = df2.iloc[a:b + 1]
        # gli indicatori della regola sono disegnati
        nomi_traccia = {t.name for t in fig.data}
        if not all(c in nomi_traccia for c in d.indicatori):
            fallite.append(f"{nome}: indicatori mancanti")
        # il nome e' sul triangolo
        if nome not in segnale(fig).text[0]:
            fallite.append(f"{nome}: nome mancante sul triangolo")
        # le linee di livello ci sono e non stirano la scala
        liv = livelli(fig)
        if len(liv) != len(d.livelli):
            fallite.append(f"{nome}: linee {len(liv)} invece di {len(d.livelli)}")
        for t in liv:
            y = np.asarray(t.y, dtype=float)
            if not (finestra["Low"].min() * 0.97 < np.nanmax(y) < finestra["High"].max() * 1.03):
                fallite.append(f"{nome}: la linea esce dalla scala del prezzo")
        # la banda copre la candela del segnale quando la regola la include
        bande = [sh for sh in fig.layout.shapes if sh.type == "rect"]
        if pos in d.barre and not any(sh.x0 <= pos - a <= sh.x1 for sh in bande):
            fallite.append(f"{nome}: banda sulla candela del segnale mancante")
        # linee di soglia dentro i pannelli
        attese = sum(1 for c in d.soglie if c in d.indicatori)
        presenti = len([sh for sh in fig.layout.shapes if sh.type == "line"])
        if presenti < attese:
            fallite.append(f"{nome}: linee di soglia {presenti} invece di {attese}")
        viste.append(nome)
    check(f"25. lente su un trade di ogni trigger scattato ({len(viste)} trigger): nome, banda, linea, indicatori, soglie",
          not fallite and len(viste) >= 8, "; ".join(fallite[:5]) or ", ".join(viste))
    mancano = [n for n in LONG + SHORT if n not in viste]
    check("26. tutte le famiglie provate hanno almeno un trade out-of-sample",
          len(mancano) <= 2, ("senza trade nel periodo: " + ", ".join(mancano)) if mancano else "tutti i trigger hanno trade")

    ok = sum(ESITI)
    print(f"\nRISULTATO: {ok}/{len(ESITI)} test superati")
    return 0 if ok == len(ESITI) else 1


if __name__ == "__main__":
    sys.exit(esegui())
