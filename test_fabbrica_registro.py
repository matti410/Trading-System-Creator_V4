"""
Suite di collaudo del registro della fabbrica (docs/82 P7 e §6, lavoro L3b).

Si lancia da terminale, dalla cartella del progetto:

    python test_fabbrica_registro.py

Scrive solo in una cartella temporanea: non servono i file in dati/, MetaTrader 5 o internet. Stampa una riga per
collaudo e alla fine «RISULTATO: n/n test superati».
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import time

import numpy as np
import pandas as pd

from engine.fabbrica import registro
from engine.fabbrica.config import cartella_asset

PERP = "BINANCE_PERP_BTCUSDT"


def _riga(id_ricerca, id_strategia, t=1.5, fase="passo_1", pezzo="ricerca"):
    return {"id_ricerca": id_ricerca, "pezzo": pezzo, "fase": fase, "teoria": "L|E47|-|X0", "id_strategia": id_strategia,
            "trade": 120, "ev_bp": 3.25, "t": t}


def esegui() -> int:
    ESITI = []
    t0 = time.perf_counter()

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        print(f"[{'OK ' if condizione else 'KO '}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""), flush=True)

    def errore(f, tipo=ValueError) -> bool:
        try:
            f()
        except tipo:
            return True
        return False

    with tempfile.TemporaryDirectory() as dati:
        base = cartella_asset(dati, PERP, "M15")
        ric_a, ric_b = os.path.join(base, "20260101_aaaa"), os.path.join(base, "20260102_bbbb")

        # ------------------------------------------------------------------ il file delle prove
        print("Il file delle prove")
        fp = registro.FileProve(ric_a, "pc")
        n1 = fp.aggiungi([_riga("A", "s1"), _riga("A", "s2"), _riga("A", "s3", t=float("nan"))])
        n2 = fp.aggiungi([_riga("A", "s1"), _riga("A", "s2", fase="zoom_1")])
        check("1. tre prove scritte; le stesse strategie di nuovo (anche da un altro giro) non si contano",
              (n1, n2, len(fp)) == (3, 0, 3), f"{n1}, {n2}, {len(fp)}")
        n3 = registro.aggiungi_prove(ric_a, [_riga("A", "s3"), _riga("A", "s4"), _riga("A", "s4")], "pc")
        check("2. una nuova e una vecchia: solo la nuova; doppia nella stessa chiamata: una volta", n3 == 1)
        con_pezzo = registro.aggiungi_prove(ric_a, [_riga("A", "s1", pezzo="selezione")], "pc")
        check("3. la stessa strategia su un altro pezzo è un'altra prova", con_pezzo == 1)
        letto = pd.read_csv(fp.percorso, dtype=str, keep_default_na=False)
        check("4. intestazione una volta, colonne nell'ordine, 5 righe",
              list(letto.columns) == list(registro.COLONNE_PROVE) and len(letto) == 5)
        x = np.float64(0.1) + np.float64(0.2)
        registro.aggiungi_prove(ric_a, [_riga("A", "s5", t=x)], "pc")
        letto = pd.read_csv(fp.percorso, dtype={"t": float}, float_precision="round_trip")
        check("5. i float si rileggono identici, anche quelli di numpy; NaN resta NaN",
              letto["t"].iloc[-1] == float(x) and math.isnan(letto["t"].iloc[2]), str(letto["t"].tolist()))
        check("6. una riga senza colonne: errore", errore(lambda: registro.aggiungi_prove(ric_a, [{"id_ricerca": "A"}], "pc")))

        with open(fp.percorso, "a", encoding="utf-8") as f:
            f.write("A,ricerca,passo_1,L|E47|-|X0,s9,12")          # il PC si spegne a metà riga
        fp2 = registro.FileProve(ric_a, "pc")
        nuove = fp2.aggiungi([_riga("A", "s9")])
        letto = pd.read_csv(fp.percorso, dtype=str, keep_default_na=False)
        check("7. una riga rimasta a metà si toglie; la prova si riscrive una volta sola",
              nuove == 1 and len(letto) == 7 and list(letto["id_strategia"]).count("s9") == 1)

        # ------------------------------------------------------------------ il conto
        print("\nIl conto delle prove")
        k = registro.conto_prove(dati, PERP, "M15")
        check("8. conto dell'asset = righe del file", k == 7, str(k))
        registro.aggiungi_prove(ric_b, [_riga("B", "s1"), _riga("B", "s2")], "pc")
        check("9. due ricerche si sommano, anche con le stesse strategie", registro.conto_prove(dati, PERP, "M15") == 9)
        registro.aggiungi_prove(ric_b, [_riga("B", "s1"), _riga("B", "s7")], "colab")
        check("10. la stessa ricerca su due macchine: le prove uguali si contano una volta",
              registro.conto_prove(dati, PERP, "M15") == 10)
        check("11. un altro asset ha il suo conto", registro.conto_prove(dati, PERP, "H1") == 0
              and registro.conto_prove(dati, "BYBIT_SPOT_ETHUSDT", "M15") == 0)
        open(os.path.join(ric_b, "prove_vuoto.csv"), "w").close()
        check("12. un file vuoto non conta e non rompe", registro.conto_prove(dati, PERP, "M15") == 10)

        # ------------------------------------------------------------------ il registro dell'asset
        print("\nIl registro dell'asset: annotazioni, solo in aggiunta (10/11, senza catena)")
        e1 = registro.scrivi_evento(base, {"tipo": "avvio_ricerca", "id_ricerca": "A", "x": np.int64(3)}, "pc")
        e2 = registro.scrivi_evento(base, {"tipo": "fine_ricerca", "id_ricerca": "A", "t": float("nan")}, "pc")
        e3 = registro.scrivi_evento(base, {"tipo": "avvio_ricerca", "id_ricerca": "B"}, "pc")
        eventi = registro.leggi_registro(base)
        check("13. tre eventi, numerati, con macchina e data; nessuna impronta della riga prima",
              [e["n"] for e in eventi] == [1, 2, 3] and all("prima" not in e for e in eventi)
              and all(e["macchina"] == "pc" and e["quando"] for e in eventi) and eventi[0]["x"] == 3
              and math.isnan(eventi[1]["t"]) and (e1["n"], e2["n"], e3["n"]) == (1, 2, 3))
        registro.scrivi_evento(base, {"tipo": "avvio_ricerca", "id_ricerca": "B"}, "colab")
        check("14. i registri di due macchine si leggono insieme", len(registro.leggi_registro(base)) == 4)

        percorso = registro.percorso_registro(base, "pc")
        with open(percorso, encoding="utf-8") as f:
            originale = f.read()
        righe = originale.splitlines(keepends=True)

        def letto(testo):
            with open(percorso, "w", encoding="utf-8") as f:
                f.write(testo)
            return [e for e in registro.leggi_registro(base) if e["macchina"] == "pc"]

        cambiata = letto(originale.replace('"id_ricerca":"A"', '"id_ricerca":"Z"', 1))
        check("15. una riga cambiata a mano: si legge com'è, nessun errore",
              [e["id_ricerca"] for e in cambiata] == ["Z", "A", "B"])
        tolta = letto(righe[0] + righe[2])
        e4 = registro.scrivi_evento(base, {"tipo": "y"}, "pc")
        check("16. una riga tolta in mezzo: si leggono le altre; l'evento nuovo prende il numero più alto + 1",
              [e["n"] for e in tolta] == [1, 3] and e4["n"] == 4)
        rovinato = letto(originale + '{"n": 4, "pri')
        e5 = registro.scrivi_evento(base, {"tipo": "z"}, "pc")
        dopo = [e for e in registro.leggi_registro(base) if e["macchina"] == "pc"]
        check("17. una riga a metà in fondo si salta; l'evento dopo va su una riga nuova e si legge",
              len(rovinato) == 3 and [e["n"] for e in dopo] == [1, 2, 3, 4] and e5["n"] == 4
              and dopo[-1]["tipo"] == "z")
        vecchio = "".join(json.dumps({"n": k + 1, "prima": "" if k == 0 else "a" * 64, "macchina": "pc",
                                      "quando": "2026-11-08T00:00:00+00:00", "tipo": "avvio_ricerca"}) + "\n"
                          for k in range(2))
        letto(vecchio)
        e6 = registro.scrivi_evento(base, {"tipo": "w"}, "pc")
        check("18. un registro scritto prima del 10/11, con l'impronta «prima», si legge e si continua",
              [e["n"] for e in registro.leggi_registro(base) if e["macchina"] == "pc"] == [1, 2, 3]
              and e6["n"] == 3)

    print("\n" + "=" * 70)
    print(f"Durata: {time.perf_counter() - t0:.0f} s")
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
