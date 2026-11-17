"""
Crea il catalogo generato (docs/83 §6).

    python -m engine.generatore --n 80              le prime 80 ricette diverse -> dati_catalogo/generati_v1.json
    python -m engine.generatore --n 80 --esempi 10  e mostra 10 ricette leggibili

Il tetto --n (numero di ricette) e' obbligatorio: lo sceglie Mattia dopo la misura dei tempi (docs/83 §7).
Stampa: ricette generate, ricette tolte come uguali (per scrittura e sul dataset sintetico), trigger risultanti.
"""
from __future__ import annotations

import argparse
import sys
import time


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m engine.generatore",
                                description="Generatore di indicatori e trigger prezzo + volume (docs/83).")
    p.add_argument("--n", type=int, default=None, help="tetto: quante ricette tenere (obbligatorio, docs/83 §7)")
    p.add_argument("--file", default=None, help="dove salvare (di base dati_catalogo/generati_v<versione>.json)")
    p.add_argument("--esempi", type=int, default=5, help="quante ricette leggibili mostrare (di base 5)")
    a = p.parse_args(argv)
    if a.n is None:
        print("Manca il tetto N. Scegli quante ricette tenere guardando i tempi di docs/83 («Tempi misurati») e "
              "lancia per esempio:\n    python -m engine.generatore --n 80")
        return 2

    from engine.generatore import genera_catalogo, salva_catalogo
    t0 = time.time()
    cat = genera_catalogo(a.n, verbose=True)
    percorso = salva_catalogo(cat, a.file)
    c = cat["conteggi"]
    print(f"\nCatalogo generato, versione {cat['versione']}, tetto {cat['tetto_ricette']} ricette "
          f"({time.time() - t0:.0f} secondi)")
    print(f"  ricette generate (con prezzo e volume):   {c['generate']}")
    print(f"  tolte come uguali per scrittura:          {c['tolte_scrittura']}")
    print(f"  tolte come uguali sul dataset sintetico:  {c['tolte_uguali']}")
    print(f"  tolte perche' non scattano mai:           {c['tolte_senza_trigger']}")
    print(f"  ricette tenute:                           {c['tenute']}")
    print(f"  trigger risultanti (long + short):        {c['trigger']}")
    if "trigger_degeneri_sintetico" in c:
        print(f"  di cui segnalati degeneri sul sintetico:  {c['trigger_degeneri_sintetico']}")
    if c["tenute"] < a.n:
        print(f"  ATTENZIONE: solo {c['tenute']} ricette diverse disponibili, meno del tetto {a.n}")
    print(f"  file: {percorso}")
    if a.esempi > 0:
        print("\nEsempi:")
        for r in cat["ricette"][:a.esempi]:
            print(f"  {r['id']}  {r['ricetta']:<40}  {r['famiglia']:<28}  {len(r['trigger'])} trigger")
    return 0


if __name__ == "__main__":
    sys.exit(main())
