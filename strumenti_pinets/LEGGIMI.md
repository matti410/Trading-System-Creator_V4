# strumenti_pinets — collaudo di fedeltà a TradingView

Serve solo a `test_indicatori_tradingview.py` (docs/51 §4.2): fa girare il codice Pine
originale con **PineTS** (LuxAlgo, licenza AGPL-3.0, uso solo interno come strumento di
test) sulle stesse barre su cui gira il Python, e il test confronta i valori.

- `esegui_pine.mjs`: `node esegui_pine.mjs <dati.csv> <script.pine> <uscita.csv>`
- gli script Pine (anche i porting a v5, `*_v5.pine`) stanno in `pine_sources/`,
  che non va su GitHub (codice di terzi).

## Installazione (una volta sola)

1. Node.js (già installato su questo PC: `node --version` dà v24).
2. Nel terminale di VS Code, dalla cartella del progetto:

       cd strumenti_pinets
       npm install

   Crea `node_modules/` (esclusa da GitHub). Senza, il test salta il confronto e lo dice.
