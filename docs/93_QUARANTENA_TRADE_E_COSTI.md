# 93 · Quarantena sui trade e costi del conto Standard (5/10/2026)
 
Chiude i punti 1 e 2 di `92_AUDIT_2026-10-05.md`. Consegnato il 5/10 sera, **da caricare sul repo**.
 
## Decisioni
- **Ingressi:** maschera unica nei motori (opzione A). Un segnale si scarta se la sua barra, o la barra d'ingresso, è in quarantena.
- **Uscite:** restano dove sono (opzione A); il lato di un trade che cade in quarantena paga lo spread del rollover.
- **Costi:** conto IC Markets Standard anche nel notebook principale: EURUSD spread 0,8 pips, commissione 0.
- **Spread nel rollover:** 1,5 pips su EURUSD. È una **stima** (0,8 + 0,7 misurati sui dati Raw), non c'è una misura dal demo: da correggere leggendolo in MT5.
## Cosa è cambiato
| file | modifica |
|---|---|
| `engine/quarantena_trade.py` (nuovo) | `barre_in_quarantena`, `maschera_segnali_puliti`, `costo_extra_pips` |
| `engine/exit_search_bt.py`, `engine/filter_search_bt.py` | parametri `quarantena=True`, `spread_rollover_pips=None`; riga «segnali scartati per quarantena»; colonna `CostoExtraPips` nei trade |
| `engine/event_study.py` | parametro `quarantena=True`; riga «trigger scartati per quarantena» |
| `engine/metriche.py` | `pips_per_trade` sottrae `CostoExtraPips` se la colonna c'è; `costo_pips` = lordi − netti |
| `engine/due_meta.py` | accetta e ripassa `quarantena`, `spread_rollover_pips` |
| `test_portabilita.py` | una riga: `quarantena=False` nei test del capitale (segnali casuali) |
| `test_quarantena_trade.py` (nuovo) | 23 test |
| cella 14 del notebook | costi Standard; `costi["spread_rollover_pips"]` |
 
Modifiche NON additive, dichiarate: i quattro file dell'engine e `metriche.py`. Il default `quarantena=True` cambia i numeri di ogni run; `quarantena=False` ridà quelli di prima.
 
Costo extra per lato in quarantena = `(spread_rollover_pips − spread normale in pips) / 2`, mai negativo. EURUSD: 0,35 pips.
 
## Limiti da sapere
- `CostoExtraPips` entra in `avg_trade_netto`, `t_stat`, scheda, confidenza e Monte Carlo (tutto ciò che passa da `pips_per_trade`). **Non** entra in `pnl_pct`, `sharpe`, `max_dd_pct` né in `plot_equity`, che vengono dal PnL della libreria.
- Con commissione 0, `avg_trade` (lordo) paga già tutto lo spread normale: differisce da `avg_trade_netto` solo per il costo del rollover.
- Lo spread resta una frazione del prezzo: 0,8 pips al prezzo mediano, ~0,84 nell'OOS.
- Gli stop degli short nel rollover restano non visibili (dati solo bid): limite noto, non toccato.
## Collaudo
- 10 suite da terminale, 238/238, con pandas 3.0.5 e 2.2.3.
- Notebook intero rieseguito con la cella 14 nuova, su entrambe le versioni: nessun errore, stessi numeri.
- Regressione: costi vecchi + `quarantena=False` → baseline 2.689 trade / 0,483; F22 2.354 / 0,737 / t 2,455; event study E11 442 trigger / 2,2593 pips. Identici al run salvato.
- Run nuovo, In-Sample, setup del 5/10: 17 righe, 24.732 trade, **0 ingressi e 0 segnali in quarantena**. Baseline 2.615 trade (scartati 109 long + 124 short); 151 uscite in quarantena, tutte e sole con costo extra; media su tutti i trade 0,02 pips.
- Event study: 9.215 trigger scartati su ~180.000; le entry sopra `min_trades=200` passano da 52 a 50.