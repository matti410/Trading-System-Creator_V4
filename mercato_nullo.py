"""
Mercato nullo (docs/63 §7, lavoro D1): la pipeline del Lab ripetuta su trigger
finti, per sapere quanto si inganna senza nessun vantaggio. Vedi
engine/mercato_nullo.py.

    python mercato_nullo.py BINANCE_PERP_BTCUSDT --giri 10          prova breve e stima del tempo
    python mercato_nullo.py BINANCE_PERP_BTCUSDT --giri 500         i giri mancanti fino a 500
    python mercato_nullo.py BINANCE_PERP_BTCUSDT BINANCE_PERP_ETHUSDT --giri 500
    python mercato_nullo.py BINANCE_PERP_BTCUSDT --riassunto        solo la tabella, senza girare

Opzioni: --tf M15 (timeframe), --H 25 (orizzonte), --strada A (filtri a
tappeto; la B arriva con l'atlante), --senza-funding (solo per confronti).

Ogni giro scrive una riga in dati/nullo/<SYMBOL>_<TF>_H<H>_<strada>.csv (non va
su GitHub): se il comando si interrompe (Ctrl+C, PC spento), rilanciandolo
riprende dal primo giro mancante. Gira sul PC; la ricerca dei filtri usa gia'
tutti i processori, quindi un symbol alla volta.

La soglia empirica e' un PAVIMENTO dell'autoinganno ed e' SOLO INFORMATIVA:
nessun cancello del tool cambia (docs/63 §10.1 punto 5, §10.2 domanda 17).
"""
import argparse
import sys
import warnings

import pandas as pd

warnings.simplefilter("ignore")


def main(argv) -> None:
    p = argparse.ArgumentParser(description="Mercato nullo (docs/63 §7)")
    p.add_argument("symbol", nargs="+")
    p.add_argument("--giri", type=int, default=500)
    p.add_argument("--tf", default="M15")
    p.add_argument("--H", type=int, default=25)
    p.add_argument("--strada", default="A")
    p.add_argument("--senza-funding", action="store_true")
    p.add_argument("--riassunto", action="store_true")
    a = p.parse_args(argv)
    from engine.mercato_nullo import file_nullo, leggi_intestazione, leggi_nullo, mercato_nullo, riassunto
    for symbol in a.symbol:
        symbol = symbol.upper()
        if a.riassunto:
            percorso = file_nullo(symbol, a.tf, a.H, a.strada)
            tab = leggi_nullo(percorso)
            testa = leggi_intestazione(percorso)
        else:
            tab = mercato_nullo(symbol, a.tf, a.H, giri=a.giri, strada=a.strada, funding=not a.senza_funding)
            testa = leggi_intestazione(file_nullo(symbol, a.tf, a.H, a.strada))
        print(f"\n{symbol} · " + " · ".join(f"{k} {v}" for k, v in testa.items() if k not in ("symbol", "nota")))
        with pd.option_context("display.width", 200, "display.max_colwidth", 80):
            print(riassunto(tab).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1:])
