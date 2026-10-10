# 31 · Costi per symbol — tabella automatica (29/9/2026)
 
Aggiorna `30_ML_LONG_SHORT.md`: `soglia_costi = 0.65 bp` e `COSTO_RT` non esistono più.
 
## Decisioni
- Operatività di riferimento: **conto IC Markets EU Standard** (demo oggi; eventuale real con gli stessi costi dopo il demo trade). Nessuna commissione, costo = spread.
- Costi in **pips**, come nella documentazione IC Markets; letti automaticamente in base a `symbol`.
- Opzione A: tabella in un file (`costi_symbol.py`). Opzione B (script MT5 che misura lo spread dai tick, anche per ora del giorno) rimandata.
- `UNITA` del backtest = 1 lotto del symbol, dalla tabella. `CAPITALE` resta manuale.
## Tabella (`costi_symbol.COSTI_SYMBOL`)
| symbol | pip_size | spread_pips | commissione_pips | lotto |
|---|---|---|---|---|
| EURUSD | 0.0001 | 0.80 | 0 | 100.000 |
| BTCUSD | 1.0 (convenzione: 1 pip = 1 $) | 6.46 — **da verificare in MT5** | 0 | 1 |
 
Fonti: pagina spreads-and-swaps e account overview di icmarkets.eu; scheda crypto EU. Commissione 0 e dimensioni dei lotti confermate dal report MT5 del conto demo (367 posizioni, 11 strumenti, commissioni tutte a 0).
Limite: vale per strumenti quotati in USD (conto in USD); coppie come GBPJPY richiederebbero conversione del PnL.
 
## Funzioni
| funzione | cosa fa |
|---|---|
| `costi_symbol.costi(symbol)` | dict con pip_size, spread_pips, commissione_pips, lotto, costo_pips; errore chiaro se il symbol manca |
| `target.costruisci_target(df_lato, colonne_trigger, direction, horizon=25, *, costo_pips, pip_size)` | classe 1 se `(uscita − ingresso) × direction > costo_pips × pip_size` (equivale al rendimento relativo > costo/prezzo di ingresso); pareggio esatto → 0; costi obbligatori, niente valori nascosti |
| `backtest_oos.esegui_backtest(df_periodo, trigger_long, trigger_short, horizon=25, *, unita, capitale, costo_pips, pip_size)` | costo fisso per trade `costo_pips × pip_size × unita` (VectorBT `fixed_fees`, metà in ingresso e metà in uscita): EURUSD 1 lotto = 8 $ |
 
Nel notebook: cella `COSTI = costi(symbol)` subito dopo il caricamento dati; target e backtest leggono da `COSTI`.
 
## Collaudo (EURUSD)
- Etichette cambiate rispetto a 0,65 bp: LONG 22 (tutte 1→0, classe 1 48,5% → 48,2%), SHORT 10 (48,1% → 47,8%).
- Trovato e corretto un caso limite: i trade che guadagnano esattamente 8 punti (= 0,8 pips) finivano a caso in 0 o 1 per arrotondamento; ora il confronto è in unità di prezzo e il pareggio vale 0 (18 casi LONG, 7 SHORT).
- Test superati: tabella ed errore su symbol assente; etichette = (guadagno in punti interi > 8) su tutti i trigger; invarianza di scala ×50.000; costo per trade 8 $ e totale = n. trade × 8; PnL a mano; somma PnL = equity; COMBINATO = LONG + SHORT; capitale insufficiente → errore; vecchia chiamata con `COSTO_RT` → errore; BTCUSD sintetico 1 BTC e 6,46 $ a trade; leakage (prezzi OOS stravolti → etichette train/test invariate).