"""
Suite di validazione del MERCATO NULLO (21/10/2026, docs/63 §7, lavoro D1):
engine/mercato_nullo.py e registry.remove_entries.

Cosa verifica
-------------
A  trigger casuali (N1): per ogni entry vera, stesso lato, stesso numero di
   eventi utili per fascia oraria, nessun evento in quarantena o sull'ultima
   barra; stesso seme = stessi eventi, seme diverso = eventi diversi; il
   risultato non dipende dall'ordine dei nomi;
B  registro: le entry finte rispondono su qualunque parte dell'indice (una
   meta'), e remove_entries le toglie tutte, comprese le «congelate»;
C  un giro con i trigger VERI riproduce il Lab (rosa, trigger scelti con la
   regola del §7.3, scheda in-sample);
D  tanti giri: una riga per giro, intestazione (catalogo, symbol, timeframe, H,
   unita', funding, modo, strada, data), ripresa da dove si era fermato senza
   rifare i giri, stesso seme = stessa riga, intestazione diversa = errore;
E  soglia empirica (il t superato nel 5% dei giri), riassunto, frase sotto
   la scheda (solo informativa).

Non verifica la taratura statistica (quota di giri promossi su un mercato
senza vantaggio): servono centinaia di giri, la da' il giro vero di 500.

Come si lancia (da terminale, dalla cartella del progetto):

    python test_mercato_nullo.py

Non serve la rete ne' la cartella dati/ (uno storico sintetico in una
cartella temporanea). Alla fine stampa «RISULTATO: N/N test superati».
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import warnings

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")

from engine import exchange as X
from engine import mercato_nullo as MN
from engine import registry as R
from engine.stagionalita import fasce_orarie

ESITI = []


def check(nome, condizione, dettaglio=""):
    ESITI.append(bool(condizione))
    stato = "OK     " if condizione else "FALLITO"
    print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))


def muto(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **k)


def storico_24_7(inizio="2023-01-01", giorni=150, prezzo=30000.0, seme=7):
    idx = pd.date_range(inizio, periods=giorni * 96, freq="15min", tz="UTC", name="Date")
    rng = np.random.default_rng(seme)
    close = prezzo * np.exp(np.cumsum(rng.normal(0, 0.002, len(idx))))
    open_ = np.r_[prezzo, close[:-1]]
    alto = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.001, len(idx))))
    basso = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.001, len(idx))))
    return pd.DataFrame({"Open": open_, "High": alto, "Low": basso, "Close": close,
                         "Volume": rng.uniform(1, 100, len(idx))}, index=idx)


def main() -> int:
    import engine.vetrina as v
    tmp = tempfile.mkdtemp()
    dati = storico_24_7()
    # un buco di 3 ore: le barre dopo la pausa sono in quarantena
    dati = dati.drop(index=dati.index[5_000:5_012])
    X.salva_csv(dati, os.path.join(tmp, "BINANCE_PERP_BTCUSDT_M15.csv"))
    orari = pd.date_range(dati.index[0].floor("8h"), dati.index[-1].ceil("8h"), freq="8h")
    X.salva_funding(X.con_intervalli(pd.DataFrame({"tasso": 0.0001}, index=orari.rename("Date"))),
                    X.file_funding("BINANCE_PERP_BTCUSDT", tmp))
    s = muto(v.prepara, "BINANCE_PERP_BTCUSDT", H=8, cartella=tmp)
    nomi = v._trigger_candidati()

    # ------------------------------------------------------------ trigger casuali --
    print("\nA · Trigger casuali (N1)")
    conteggi = MN.conteggi_veri(s.df_is, nomi, s.fuso)
    m1 = MN.trigger_casuali(s.df_is, nomi, 1, s.fuso, conteggi)
    codici = fasce_orarie(s.df_is.index, s.fuso)[0]
    utili = MN.barre_utili(s.df_is)
    uguali = all(dict(zip(*[x.tolist() for x in np.unique(codici[m1[n]], return_counts=True)])) == conteggi[n][1]
                 for n in nomi)
    check("A1. per ogni entry vera, stessi eventi utili per fascia oraria",
          uguali and set(m1) == set(nomi), f"{len(nomi)} entry, {sum(int(m.sum()) for m in m1.values()):,} eventi finti")
    check("A2. nessun evento finto in quarantena o sull'ultima barra",
          all(not (m & ~utili).any() for m in m1.values()) and (~utili).sum() > 1)
    check("A3. stesso lato del trigger vero",
          all(conteggi[n][0] == R.get_entry_direction(n) for n in nomi))
    m1b = MN.trigger_casuali(s.df_is, nomi, 1, s.fuso, conteggi)
    m2 = MN.trigger_casuali(s.df_is, nomi, 2, s.fuso, conteggi)
    rovescio = MN.trigger_casuali(s.df_is, list(reversed(nomi)), 1, s.fuso, conteggi)
    pieni = [n for n in nomi if m1[n].sum() > 5]
    check("A4. stesso seme = stessi eventi, anche con i nomi in un altro ordine; seme diverso = eventi diversi",
          all((m1[n] == m1b[n]).all() and (m1[n] == rovescio[n]).all() for n in nomi)
          and all((m1[n] != m2[n]).any() for n in pieni))
    vero = R.get_entry(pieni[0])(s.df_is).fillna(False).to_numpy() & utili
    check("A5. gli eventi finti non sono quelli veri (giornate a caso)",
          (m1[pieni[0]] & vero).sum() < 0.5 * vero.sum(), f"{pieni[0]}: {(m1[pieni[0]] & vero).sum()} in comune su {vero.sum()}")

    # ------------------------------------------------------------------ registro --
    print("\nB · Registro")
    finti = MN.registra_finti(m1, conteggi, s.df_is.index)
    meta = s.df_is.iloc[: len(s.df_is) // 2]
    f0 = finti[0]
    check("B1. le entry finte rispondono su una meta' dell'indice con la loro maschera",
          (R.get_entry(f0)(meta).to_numpy() == m1[f0[len(MN.PREFISSO):]][: len(meta)]).all()
          and R.get_entry_direction(f0) == conteggi[f0[len(MN.PREFISSO):]][0])
    R.register_entry(f"{f0}+FILTRO_PROVA", 1)(lambda d: pd.Series(False, index=d.index))
    tolte = R.remove_entries(MN.PREFISSO)
    check("B2. remove_entries toglie tutte le finte, comprese le congelate, e nient'altro",
          tolte == len(finti) + 1 and not any(n.startswith(MN.PREFISSO) for n in R.list_entries())
          and all(n in R.list_entries() for n in nomi))
    ver = MN.versione_catalogo()
    MN.registra_finti(m1, conteggi, s.df_is.index)
    check("B3. la versione del catalogo non conta le entry finte", MN.versione_catalogo() == ver, ver)
    R.remove_entries(MN.PREFISSO)

    # --------------------------------------------------------- giro con il vero --
    print("\nC · Un giro con i trigger veri riproduce il Lab")
    riga = MN.giro_nullo(s, 0, nomi, conteggi, finti=False)
    lab = muto(v.prepara, "BINANCE_PERP_BTCUSDT", H=8, cartella=tmp)
    muto(v.esplora, lab)
    rosa = muto(v.rosa_dei_trigger, lab)
    primo = {d: MN._primi(rosa, d)[0][0] for d in (1, -1)}
    muto(v.scegli_trigger, lab, long=primo[1], short=primo[-1])
    muto(v.imposta_uscite, lab)
    muto(v.trova_strategia, lab)
    filtro = (max(lab.sopravvissuti, key=lambda f: lab.fs.risultati.set_index("filtro").at[f, "t_guadagno"])
              if lab.sopravvissuti else None)
    muto(v.scheda, lab, filtro=filtro)
    from engine.giudizio import scheda_strategia
    k = scheda_strategia(lab.trades_is, lab.fs.pip_size, lab.fs.commission, montecarlo=False, verbose=False,
                         atr=lab.atr, unita=lab.unita)
    check("C1. stessa rosa dei trigger del Lab", s.rosa_trigger.equals(lab.rosa_trigger))
    check("C2. trigger della regola = i primi della rosa del Lab, stesso filtro scelto",
          riga["trigger_long"] == primo[1] and riga["trigger_short"] == primo[-1]
          and riga["filtro"] == (filtro or ""), f"{primo[1]} · {primo[-1]} · filtro {filtro or '—'}")
    check("C3. stessa scheda in-sample del Lab: t, P(EV<0), trade, esito",
          np.isclose(riga["t"], k["t_stat"]) and np.isclose(riga["p_ev_neg"], k["p_ev_neg"])
          and riga["trade"] == k["n_trades"] and riga["esito"] == k["esito"],
          f"t {riga['t']:+.2f}, {riga['trade']} trade, {riga['esito']}")
    check("C4. il migliore dei primi 3: una delle 3 strade, t non inferiore alla regola",
          riga["m3_k"] in (1, 2, 3) and riga["m3_t"] >= riga["t"] - 1e-12)

    # ------------------------------------------------------------- tanti giri --
    print("\nD · Tanti giri, una riga per giro, ripresa")
    t2 = muto(MN.mercato_nullo, "BINANCE_PERP_BTCUSDT", H=8, giri=2, cartella=tmp)
    p = MN.file_nullo("BINANCE_PERP_BTCUSDT", "M15", 8, "A", tmp)
    testa = MN.leggi_intestazione(p)
    check("D1. intestazione: catalogo, symbol, timeframe, H, unita' bp, funding si, modo, strada, data",
          testa.get("versione_catalogo") == MN.versione_catalogo() and testa.get("symbol") == "BINANCE_PERP_BTCUSDT"
          and testa.get("timeframe") == "M15" and testa.get("H") == "8" and testa.get("unita") == "bp"
          and testa.get("funding") == "si" and testa.get("modo") == "N1" and testa.get("strada") == "A"
          and "data" in testa, str({k: testa[k] for k in ("H", "unita", "funding")}))
    check("D2. una riga per giro, con le colonne previste", list(t2["giro"]) == [0, 1]
          and list(t2.columns) == MN.COLONNE)
    t3 = muto(MN.mercato_nullo, "BINANCE_PERP_BTCUSDT", H=8, giri=3, cartella=tmp)
    check("D3. rilanciato con 3 giri: rifa' solo il mancante, i primi due restano uguali",
          list(t3["giro"]) == [0, 1, 2] and t3.iloc[:2].drop(columns="secondi").equals(t2.drop(columns="secondi")))
    riga1 = MN.giro_nullo(s, 1, nomi, conteggi)
    confronto = ["trigger_long", "trigger_short", "filtro", "esito", "trade"]
    check("D4. stesso seme = stesso giro (riproducibile)",
          all(str(riga1[c]) == str(t3.iloc[1][c]) for c in confronto) and np.isclose(riga1["t"], t3.iloc[1]["t"]))
    altro = None
    try:
        muto(MN.mercato_nullo, "BINANCE_PERP_BTCUSDT", H=8, giri=3, cartella=tmp, funding=False, percorso=p)
    except ValueError as e:
        altro = str(e)
    check("D5. un file con un'intestazione diversa (funding no) ferma tutto", altro is not None and "funding" in altro)
    check("D6. nessuna entry finta rimasta nel registro", not any(n.startswith(MN.PREFISSO) for n in R.list_entries()))

    # ----------------------------------------------------------------- lettura --
    print("\nE · Soglia empirica, riassunto, frase sotto la scheda")
    finto = pd.DataFrame({"t": np.arange(1, 101, dtype=float)})
    check("E1. soglia empirica: su t = 1..100 il t superato nel 5% dei giri e' 96",
          MN.soglia_empirica(finto) == 96.0 and MN.soglia_empirica(pd.DataFrame({"t": [np.nan] * 3 + [1.0]}), "t", 0.25) == 1.0)
    rs = MN.riassunto(t3)
    check("E2. riassunto: la regola del §7.3 accanto al migliore dei primi 3",
          list(rs.columns) == ["", "Regola del §7.3", "Migliore dei primi 3"] and "Soglia empirica" in " ".join(rs[""]))
    f_si = MN.frase_mercato_nullo("BINANCE_PERP_BTCUSDT", "M15", 8, 1.0, cartella=tmp)
    f_no = MN.frase_mercato_nullo("BINANCE_PERP_BTCUSDT", "M15", 25, 1.0, cartella=tmp)
    check("E3. frase sotto la scheda: con il file la quota dei giri, senza «non ancora calcolato»; solo informativa",
          "3 giri" in f_si and "informativo" in f_si and "non ancora calcolato" in f_no, f_si[:90])
    R.remove_entries(MN.PREFISSO)

    tot, ok = len(ESITI), sum(ESITI)
    print("\n" + "=" * 70)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(main())
