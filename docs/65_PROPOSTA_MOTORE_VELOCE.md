# 65 · Proposta: un motore di backtest veloce al posto di backtesting.py

**Data:** 21 ottobre 2026
**Stato:** APPROVATA da Mattia il 21/10/2026, decisioni nel §13. **E1 + E2 fatti il 21/10** sul ramo `motore-veloce-e1-e2` (§14, PR #45). **E3 fatto il 21/10** sul ramo `motore-veloce-e3`: «veloce» è il predefinito (§15).
**Incarico:** `docs/64_MOTORE_VELOCE.md`.
**Letti:** `CLAUDE.md`, `docs/00`, `docs/21` (sezione D), `docs/63` (§7, §10.3), `docs/64`; i moduli `engine/exit_search_bt.py`, `filter_search_bt.py`, `due_meta.py`, `confidenza.py`, `metriche.py`, `quarantena_trade.py`, `exchange.py`, `vetrina.py`, `vetrina_verifica.py`, `equity_plot.py`, `mm_adattatore.py`, `giudizio.py`, `rosa.py`, `mercato_nullo.py`, `test_velocita.py`; il sorgente di `backtesting.py` 0.6.6 (`Backtest.run`, `_Broker.new_order`, `_Broker._process_orders`, `_close_trade`, `_open_trade`, `Trade`, `_stats.compute_stats`).
**Verifiche fatte il 21/10** (§1, §7): tempi di oggi misurati sul PC; un **prototipo usa e getta**, scritto nella cartella temporanea di Claude (fuori dal repo, niente di committato), confrontato con l'oracolo su 2.000 configurazioni casuali e sul sistema vero di identità. Nessun file del repo modificato, a parte questo documento.

---

## 0 · In breve

- **Si può fare, e con gli stessi trade al centesimo.** Il prototipo (un ciclo compilato con numba, più un «livello dei soldi» calcolato dopo) ha dato **trade identici bit per bit** a `backtesting.py` 0.6.6 con `_StrategiaGenerica` su 1.997 configurazioni casuali su 2.000 (**1.051.695 trade** confrontati: prezzi, barre, stop, target, Size, PnL, commissioni, curva del capitale; e le cinque statistiche che il tool legge, scarto 0). Le 3 restanti sono il caso del §3.2, dove è la libreria a sbagliare; fino a quel punto i trade coincidono anche lì.
- **Velocità del backtest:** sull'in-sample vero di BINANCE_PERP_BTCUSDT (190.420 barre, E23 long + short, uscite predefinite del Lab) un backtest passa da **852 ms a circa 7 ms**: il ciclo dei trade da solo è **237 volte** più veloce, con i soldi e le statistiche circa **120 volte**. L'obiettivo «almeno 50 volte» è superato.
- **Ma la schermata non diventa 100 volte più veloce:** nella ricerca dei filtri, tolto il backtest, restano le **maschere dei 38 filtri** (4,6 s, metà nei 3 filtri VWAP) e il **bootstrap di P(EV<0)** (fino a 0,17 s a riga). La schermata 5 scende da circa 32 s (in sequenza; 19 s con 6 processi) a circa **8 s**; con il passo E4 facoltativo (§8) a circa 3–4 s. Un giro del mercato nullo da circa 137 s a circa 20–25 s (stima, §9).
- **Una scoperta sul tool di oggi (§3.2):** `backtesting.py` simula un capitale che si capitalizza trade dopo trade. Con i sistemi che perdono a lungo il capitale scende sotto il prezzo di **una** unità e da lì la libreria **annulla in silenzio ogni ordine**: i trade spariscono senza errore. Sull'in-sample di BINANCE_PERP_BTCUSDT succede a **8 entry su 71** (con le uscite predefinite del Lab; per esempio E12_SHORT_ENGULFING: 5.656 trade per unità, la libreria ne conta 4.020); su BINANCE_PERP_ETHUSDT a 5 su 71, su BYBIT_SPOT_ETHUSDT a 1 su 36. `avviso_capitale` controlla solo il capitale iniziale e non lo vede. Il motore nuovo lavora per unità e non ha il problema: è l'unica differenza voluta, va decisa (domanda 4).
- **Piano in quattro passi** (§8): E1 il motore e il suo collaudo con l'oracolo (nessun numero del tool cambia); E2 l'interruttore `motore=` nei motori, nel Lab e nel notebook, con la prova di identità; E3 «veloce» diventa il predefinito; E4, facoltativo, le maschere dei filtri in cache e il resto.
- **Dipendenza:** `numba==0.68.0` (è già nell'ambiente del PC, arrivata per caso con vectorbt: va bloccata esplicitamente). Se non si installa, si torna a «bt» con un avviso.
- **`confidenza.py` in bp:** consiglio **subito dopo E, su un ramo a parte** (§10): E deve dimostrare che non cambia nessun numero, la confidenza in bp invece li cambia.

---

## 1 · Dove va il tempo oggi (misurato il 21/10 sul PC)

BINANCE_PERP_BTCUSDT M15, in-sample 190.420 barre, trigger E23 long e short, uscite predefinite del Lab (a tempo dopo 25 barre, stop al 90° percentile, inversione accesa), funding acceso, 38 filtri (30 righe: le coppie long/short contano per una).

| cosa | tempo |
|---|---|
| un backtest (`bt.run`, 1.500 trade) | **852 ms** |
| `run_exit_search_bt` con una combinazione (soglie, segnali, backtest) | 1,33 s |
| `run_filter_search_bt`, 30 righe, in sequenza | circa 31 s |
| la stessa con 6 processi | 18,8 s |
| `due_meta`, sistema base + 5 filtri, in sequenza (12 backtest su metà storico) | 6,3 s |
| schermata 5 del Lab (`trova_strategia`), in uno script, quindi in sequenza | 31,6 s |
| un giro del mercato nullo (prova di D1, `docs/63` §8) | circa 137 s |
| la suite completa dei 36 `test_*.py`, una dopo l'altra | circa 32 minuti (§9 bis) |

**Dentro la ricerca dei filtri** (profilo in sequenza, i tempi del profilo sono gonfiati ma le proporzioni valgono):

| parte | quota |
|---|---|
| `backtesting.py` (`Backtest.run` × 30, statistiche comprese) | circa l'85% |
| maschere dei 38 filtri (`get_filter(nome)(df)`) | circa il 6% (4,6 s misurati a parte; 2,2 s nei 3 filtri VWAP, `regression_trend_fit`) |
| bootstrap di P(EV<0), `p_ev_negativo` | circa il 3% (fino a 0,17 s a riga con 1.500 trade) |
| costo extra, funding, metriche, soglie adattive | sotto l'1% |

Dentro `backtesting.py` il tempo non sta nel calcolo ma nel meccanismo: a ogni barra la libreria accorcia i dati, chiama `next()`, scorre gli ordini, ricalcola proprietà in cache (5,7 milioni di chiamate per 30 backtest). È lavoro dell'interprete Python, barra per barra: lo si toglie solo compilando il ciclo.

---

## 2 · Inventario del comportamento da replicare

Una riga per regola. **Fonte** = dove sta oggi; **prova** = come la verifica il collaudo (§7). «Oracolo» = il confronto trade per trade con `backtesting.py` 0.6.6 + `_StrategiaGenerica` su configurazioni casuali. Tutte le righe sono già replicate dal prototipo e passano l'oracolo.

### 2.1 · Il giro delle barre

| # | regola | fonte | prova |
|---|---|---|---|
| R1 | Il ciclo parte dalla **barra 1**, non dalla 0: `next()` non viene mai chiamato sulla barra 0, quindi un segnale sulla barra 0 si ignora (`start = 1 + warmup`, warmup 0 perché la strategia non usa `self.I`) | `Backtest.run` | caso limite: segnale sulla barra 0 |
| R2 | A ogni barra *i*: prima il **broker** (ordini in coda, poi stop e target, sui prezzi della barra *i*), poi la **strategia** (`next()`, che vede la barra *i* chiusa) | `Backtest.run`, `_Broker.next` | oracolo |
| R3 | Una posizione alla volta (`exclusive_orders=True`, `hedging=False`) | `Backtest(...)` dei due motori | oracolo |

### 2.2 · Ingresso

| # | regola | fonte | prova |
|---|---|---|---|
| E1 | Senza posizione: segnale long e non short → compra; short e non long → vende; **long e short sulla stessa barra: niente** | `_StrategiaGenerica.next`, righe 304–312 | oracolo; `test_inversione.py` |
| E2 | L'ordine si riempie all'**Open della barra dopo** il segnale; `EntryBar` = quella barra | `_process_orders` (ordine a mercato, `trade_on_close=False`) | `docs/21` D1–D3 |
| E3 | **Spread una volta sola, dentro il prezzo d'ingresso:** long Open × (1 + s), short Open × (1 − s) (`copysign`) | `_Broker._adjusted_price` | `docs/21` D2 |
| E4 | **Commissione su entrambi i lati, fuori dal prezzo:** si toglie dal capitale all'apertura (sul prezzo d'ingresso con lo spread) e alla chiusura (sul prezzo d'uscita) | `_open_trade`, `_close_trade` | `docs/21` D1 |
| E5 | Un segnale sull'**ultima barra** non diventa mai un trade (l'ordine resta in coda) | `Backtest.run` | caso limite |
| E6 | A posizione aperta i segnali d'ingresso **non si guardano** (salvo l'inversione, U3) | `next`, ramo `if aperti` | oracolo |
| E7 | Segnali già tolti **prima** del motore, e restano dove sono: soglia non calcolabile (`ok_long_al_segnale`), quarantena (`maschera_segnali_puliti`), filtri in AND | `run_exit_search_bt`, `run_filter_search_bt` | invariati: il motore nuovo riceve le stesse maschere |

### 2.3 · Stop e target

| # | regola | fonte | prova |
|---|---|---|---|
| S1 | Stop e target sono **frazioni** (`soglie_adattive`, causali con `lag`), lette sulla **barra d'ingresso** e moltiplicate per il prezzo d'ingresso **con lo spread**: long stop = P × (1 − f), target = P × (1 + f); short al contrario | `next`, righe 249–267 | oracolo |
| S2 | Frazione NaN (percentile spento) → quello stop o target non esiste | idem (`if not np.isnan`) | oracolo |
| S3 | **Attivi dalla barra dopo l'ingresso**, mai sulla barra d'ingresso (sono assegnati in `next()`, dopo che il broker ha già processato la barra) | `docs/00`, «Scoperte»; `docs/21` D3 | `docs/21` D3 (discriminante) |
| S4 | Stop long toccato se **Low ≤ stop**, riempito a **min(Open, stop)**: con un gap sotto lo stop si esce all'Open (peggio dello stop). Short: High ≥ stop, a **max(Open, stop)** | `_process_orders`, ramo `stop_price` | dati finti con gap (§7.1) |
| S5 | Target long toccato se **High ≥ target**, riempito a **max(Open, target)**: con un gap oltre il target si esce all'Open (meglio del target). Short: Low ≤ target, a **min(Open, target)** | `_process_orders`, ramo `limit` | dati finti con gap |
| S6 | **Stop e target nella stessa barra: vince lo stop** (l'ordine di stop è in testa alla coda, quello di target in fondo; chiuso il trade, l'altro sparisce) | `new_order` (`insert(0 if trade and stop …)`), `_close_trade` | dati finti, barre larghe |
| S7 | Le colonne `SL` e `TP` dei trade riportano il valore fissato (anche se lo stop è stato superato da un gap). Se nessun trade ha lo stop, la libreria mette `None` (colonna di oggetti), non NaN | `_process_orders` (ripristino di `stop_price`), `Trade.sl` | oracolo sui tipi delle colonne |

### 2.4 · Uscite

| # | regola | fonte | prova |
|---|---|---|---|
| U1 | **Regola d'uscita:** se scatta sulla barra *j* (anche la barra d'ingresso), chiusura all'**Open di *j* + 1** | `next`, righe 289–293 | oracolo |
| U2 | **Uscita a tempo:** la chiusura si chiede quando `j − EntryBar ≥ scadenza − 1`, quindi `ExitBar = EntryBar + scadenza` esatto; scadenza diversa per lato (`n_barre_long`, `n_barre_short`) | `next`, righe 295–301 | `test_barre_per_lato.py`, oracolo |
| U3 | **Inversione** (`inverti_su_opposto`): segnale opposto, e non l'altro insieme → chiude e apre al contrario, tutte e due all'Open dopo; stesso verso → ignorato; **l'inversione prevale** sulla regola e sul tempo della stessa barra; il trade nuovo ha la sua barra d'ingresso, quindi stop e timer ripartono | `next`, righe 269–287 | `test_inversione.py`, oracolo |
| U4 | **Precedenze nella barra di chiusura:** un ordine di chiusura in coda si riempie all'Open **prima** di stop e target, che poi spariscono (`Trade.close` inserisce in testa) | `Trade.close`, `_process_orders` | oracolo |
| U5 | Chiuso un trade con lo stop o il target sulla barra *j*, la strategia di *j* è già senza posizione: un segnale su *j* entra a *j* + 1. Chiuso all'Open di *j* (ordine di chiusura), idem. Il segnale sulla barra in cui si è **chiesta** la chiusura invece si perde | `next` (il `return` dopo la chiusura) | oracolo |
| U6 | Uscita senza spread (prezzo pieno) | `_reduce_trade`, `_close_trade` | `docs/21` D2 |
| U7 | **Trade ancora aperto alla fine dei dati: escluso** dai trade (`finalize_trades=False`); la sua perdita o il suo guadagno non realizzato entra però nella curva del capitale, quindi in `pnl_pct`, `sharpe`, `max_dd_pct` | `Backtest.run`, `exit_search_bt.py` righe 584–590 | caso limite |

### 2.5 · Dopo il motore (non cambiano)

| # | regola | fonte |
|---|---|---|
| D1 | `CostoExtraPips` (spread del rollover sui lati in quarantena) | `quarantena_trade.costo_extra_pips`, applicato ai trade del motore |
| D2 | `FundingPips` (funding dei perpetual) | `exchange.aggiungi_funding`, idem |
| D3 | pips, bp, ATR, netti, t, P(EV<0), tenuti contro scartati, soglia di rumore, verdetto | `metriche`, `giudizio`: leggono `Size` (solo il segno), `EntryBar`, `ExitBar`, `EntryPrice`, `ExitPrice`, `SL`, `TP`, `EntryTime`, `ExitTime` |

### 2.6 · Le statistiche della libreria: chi le usa

| voce | colonna | chi la legge | come si replica |
|---|---|---|---|
| `Win Rate [%]` | `win_rate_pct` | **Lab**, tabella delle uscite («Trade vincenti (%)»); notebook | per unità: dipende solo dal segno del PnL netto di commissione |
| `Profit Factor` | `profit_factor` | notebook (tabelle) | per unità: usa `ReturnPct`, che non dipende dalla Size |
| `Return [%]` | `pnl_pct` | notebook, `due_meta` (tabella), test | serve il capitale simulato (§3.1) |
| `Sharpe Ratio` | `sharpe` | **`ExitSearchBT.top()` ordina per sharpe** (notebook di ricerca, celle 44–50); `guadagno_sharpe` dei filtri; `due_meta` | idem |
| `Max. Drawdown [%]` | `max_dd_pct` | notebook | idem |
| `PnL` dei trade | — | `equity_plot.plot_equity` (Lab, schermata 6; notebook) | idem |

Nessuna di queste decide un cancello del metodo (`02`): decidono t, P(EV<0), tenuti contro scartati, due metà. Lo sharpe però **ordina** la classifica delle uscite nel notebook di ricerca (`docs/00`, «Problemi aperti»): per l'identità va replicato al bit, e il prototipo lo fa. Toglierle o sostituirle (per esempio con sharpe e drawdown in bp, per unità) è una decisione a parte, dopo E (domanda 5).

---

## 3 · I soldi simulati da backtesting.py

### 3.1 · Come funzionano (e perché si replicano dopo il ciclo)

`buy()` e `sell()` usano la dimensione predefinita, **tutto il capitale** (`_FULL_EQUITY` = 1 − ε): la libreria compra il numero **intero** di unità che il capitale del momento permette,

  Size = ⌊ capitale × leva × (1 − ε) ÷ (prezzo d'ingresso con lo spread + Open × commissione) ⌋,

e il capitale si aggiorna a ogni trade (commissione all'apertura, PnL e commissione alla chiusura). Quindi la Size cambia da un trade all'altro, e con essa `PnL`, `pnl_pct`, `sharpe`, `max_dd_pct`.

Questo **non cambia quali trade si fanno** (finché il capitale basta, §3.2), né i pips e i bp, che sono per unità. Per questo la proposta separa due livelli:
1. **il ciclo per unità** (compilato): decide i trade (barre, prezzi, stop, target);
2. **il livello dei soldi** (compilato anche lui, si scorre trade per trade): Size, `PnL`, `Commission`, `ReturnPct`, curva del capitale barra per barra, e le 5 statistiche con le formule di `_stats.compute_stats` 0.6.6.

Il prototipo rifà le stesse operazioni nello stesso ordine (anche il `(1 − ε) × prezzo × c ÷ (1 − ε)` della libreria, che non è identico a `prezzo × c`): **valori identici al bit**, statistiche comprese.

### 3.2 · Il capitale che si esaurisce: un difetto silenzioso di oggi

Se il capitale simulato scende sotto il costo di **una** unità, `backtesting.py` annulla l'ordine con un avviso (silenziato dai motori) e la strategia continua **senza posizione**: da lì in poi nessun trade si apre più. Con `CASH = 10.000.000` il caso sembrava impossibile (`avviso_capitale` controlla solo il capitale iniziale contro il prezzo), ma il capitale si capitalizza: un sistema con migliaia di trade che costano più di quanto rendono lo porta vicino allo zero.

Misurato sull'in-sample, con le uscite predefinite del Lab, una entry alla volta (sola lettura, prototipo + verifica con `run_exit_search_bt`):

| symbol | entry provate | con ordini annullati | con meno di 10 unità a un certo punto |
|---|---|---|---|
| BINANCE_PERP_BTCUSDT | 71 | **8** | 30 |
| BINANCE_PERP_ETHUSDT | 71 | **5** | 8 |
| BYBIT_SPOT_ETHUSDT (solo long) | 36 | **1** | 9 |

Gli 8 casi su BTC (trade per unità → trade contati oggi da `backtesting.py`, e da quando):

| entry | per unità | backtesting.py | ordini annullati dal |
|---|---|---|---|
| E12_ENGULFING | 5.742 | 5.440 | 15/12/2024 |
| E12_SHORT_ENGULFING | 5.656 | 4.020 | 16/11/2023 |
| E13_SHORT_HARAMI | 4.364 | 3.994 | 04/12/2024 |
| E21_SHORT_BELT_HOLD | 5.251 | 3.925 | 11/01/2024 |
| E24_SHORT_CYCLE_TURN_DOWN | 5.527 | 3.867 | 24/10/2023 |
| E2_SHORT_ZLEMA_CROSS_DOWN | 3.631 | 3.246 | 12/11/2024 |
| E3_SHORT_INTRABAR_STRENGTH_FADE | 5.202 | 3.942 | 11/01/2024 |
| E8_SHORT_CLOSING_PATTERN_ONLY | 3.961 | 3.500 | 29/07/2024 |

Cosa tocca: la ricerca delle uscite, quella dei filtri e la scheda di un sistema che arriva a quel punto lavorano su **un pezzo dello storico** senza dirlo (manca la coda dell'in-sample). Non tocca l'event study e la rosa delle entry (non usano il backtest). Il sistema di identità (E23 su BTC) non ci arriva: scende al minimo a 7 unità.

Lo stesso meccanismo ha un secondo caso, mai osservato: se il capitale simulato va a zero o sotto dentro un trade (solo uno short con il prezzo più che raddoppiato), la libreria chiude tutto e **ferma** la simulazione.

**Proposta (domanda 4):** il motore veloce tiene **tutti** i trade per unità (sono la risposta giusta a «come si comporta questo sistema su tutto lo storico»). Se il capitale simulato si esaurisce, da quel trade in poi la Size è ±1, `pnl_pct`, `sharpe` e `max_dd_pct` della riga diventano NaN, e il motore stampa un avviso con la data, come fa oggi `avviso_capitale`. In quei casi i numeri cambiano rispetto a oggi (più trade): è l'unica differenza dichiarata di E. In tutti gli altri casi, identità al bit.

---

## 4 · La tecnica

### 4.1 · Perché «vettorizzare» non basta

Con una posizione alla volta un segnale diventa un trade **solo se il trade prima è già chiuso**, e quando si chiude dipende da stop, target, regola, tempo e inversione del trade precedente. Ogni trade dipende da quello prima: non esiste un'operazione su tutto l'array che dica in un colpo quali segnali si tradano. È esattamente il difetto che ha fatto togliere VectorBT il 16/9 (l'uscita a tempo costruita come maschera si disallineava quando uno stop chiudeva prima). Si può vettorizzare **tutto il resto**, ed è già così: soglie adattive, maschere dei segnali (entry, filtri, quarantena, validità della soglia), costo extra, funding, metriche.

### 4.2 · Le strade confrontate

| strada | come | velocità (stima o misura) | stessi trade | contro |
|---|---|---|---|---|
| **A · ciclo compilato con numba** (consigliata) | il ciclo delle barre del §2 in una funzione `@njit` su array numpy; tutto il resto resta in numpy/pandas | **misurata**: 3,6 ms il ciclo, circa 7 ms con soldi e statistiche (§0) | sì, al bit (prototipo) | una dipendenza in più; prima compilazione circa 3 s (misurata: 2,0 s il ciclo, 0,8 s i soldi), poi in cache su disco (0,3 s) |
| B · Python puro «da trade a trade» | per ogni trade si cerca con numpy la prima barra che chiude (stop, target, regola, tempo, inversione), poi si salta lì | stimata 20–60 ms: un trade costa qualche ricerca vettoriale | sì, ma la logica delle precedenze (U3, U4, S6) va riscritta in forma di ricerche, più facile sbagliare | nessuna dipendenza; 5–10 volte più lenta di A |
| C · Cython o Rust | come A, compilato prima | come A | sì | serve un compilatore per Windows e per Colab: troppo per questo progetto |
| D · VectorBT o altre librerie | — | — | **no**, tolta il 16/9 | escluso da `docs/64` |

**A** è la più semplice da leggere (il ciclo assomiglia riga per riga a `_StrategiaGenerica.next` più `_process_orders`), la più veloce e già provata. **B** resta il ripiego se numba un giorno non si installasse: si può scrivere dopo, con lo stesso collaudo.

---

## 5 · Firme (nomi indicativi)

```python
# engine/motore_veloce.py  (nuovo)
MOTORE_PREDEFINITO = "bt"            # E3: diventa "veloce" dopo il collaudo di identita'
DISPONIBILE: bool                    # numba importato? altrimenti "veloce" ripiega su "bt" con un avviso

simula_trade(open_, high, low, segnali_long, segnali_short, uscita_long, uscita_short,
             sl_long, tp_long, sl_short, tp_short, n_barre_long, n_barre_short,
             spread, inverti_su_opposto) -> dict di array      # il ciclo per unita' (§2), compilato
                                                                 # + il trade ancora aperto alla fine
soldi(trades_per_unita, open_, close, cash, commission, margin) -> (size, pnl, commissioni,
                                                                     return_pct, equity, esaurito_da)
tabella_trade(df, ...) -> pd.DataFrame       # stesse colonne e tipi di stats["_trades"]:
                                             # Size, EntryBar, ExitBar, EntryPrice, ExitPrice, SL, TP,
                                             # PnL, Commission, ReturnPct, EntryTime, ExitTime, Duration, Tag
statistiche(equity, trades, fine_giornata, giorni_anno) -> dict   # le 5 voci di _VOCI_STATS, stesse chiavi
fine_giornata(index) -> np.ndarray           # una volta per df: l'ultima barra di ogni giorno (per lo sharpe)

esegui(df_bt, run_kw, cash, spread, commission, margin) -> dict   # stesso contratto di filter_search_bt._giro:
                                                                  # {"_trades": ..., "Return [%]": ..., ...}
```

**Dove entra** (modifiche additive, parametro nuovo con il valore di oggi):

```python
# engine/exit_search_bt.py   run_exit_search_bt(..., motore=None)   None = MOTORE_PREDEFINITO
# engine/filter_search_bt.py run_filter_search_bt(..., motore=None); esegui_giri sceglie bt.run o esegui
# engine/due_meta.py          due_meta(..., motore=None)             None = quello di fs (come unita e funding)
# engine/vetrina.py           prepara(..., motore=None) -> s.motore; _kw_motore lo passa a ogni backtest
# notebook di ricerca         MOTORE = "veloce" accanto a UNITA e FUNDING, passato a ogni motore
```

`ExitSearchBT` e `FilterSearchBT` ricordano `.motore` come già ricordano `.unita` e `.funding`. Il contratto di `esegui` è quello di `_giro`, quindi tutto il codice dopo (costi extra, funding, metriche, giudizio, tabelle, Lab) non cambia. La strategia `_StrategiaGenerica` resta com'è: è l'oracolo.

---

## 6 · Casi limite (dove un motore nuovo sbaglia di solito)

| caso | cosa fa la libreria (e quindi il motore nuovo) |
|---|---|
| gap oltre lo stop | esce all'Open (S4) |
| gap oltre il target | esce all'Open (S5) |
| stop e target nella stessa barra | vince lo stop (S6) |
| barra piatta (Open = High = Low = Close = stop) | lo stop scatta (≤, ≥) |
| segnale sulla barra 0 | ignorato (R1) |
| segnale sull'ultima barra | nessun trade (E5) |
| trade aperto alla fine | escluso dai trade, dentro la curva del capitale (U7) |
| scadenza 1 | chiusura chiesta sulla barra d'ingresso, uscita alla barra dopo |
| inversione sulla barra d'ingresso | stop e target fissati, poi chiusura e ingresso opposto all'Open dopo |
| regola d'uscita e inversione sulla stessa barra | vince l'inversione (U3) |
| segnale long e short insieme, a posizione aperta con inversione | niente (U3) |
| stop con frazione ≥ 1 (prezzo ≤ 0) | la libreria si ferma con un errore (`assert 0 < price`); il motore nuovo deve fermarsi anche lui, con un messaggio chiaro |
| capitale simulato sotto una unità | §3.2 |

---

## 7 · Collaudo

### 7.1 · `test_motore_veloce.py` (nuovo)

- **Oracolo, configurazioni casuali:** almeno 2.000, metà su pezzi di dati veri (BINANCE_PERP_BTCUSDT, 20.000 barre da un punto a caso) e metà su dati costruiti apposta (salti forti fra una barra e l'altra, barre piatte, barre larghe che toccano stop e target insieme). A caso: lati (solo long, solo short, entrambi; densità dei segnali dallo 0,2% al 20%), regole d'uscita, percentili di stop e target (spenti, 50°, 90°), scadenze 1–40 per lato, inversione, spread, commissione, finestra. **Uguali al bit:** tutte le colonne dei trade (anche i tipi), la curva del capitale, le 5 statistiche. Il prototipo lo ha già fatto: 2.000 configurazioni, 1.051.695 trade, 0 differenze fuori dal §3.2. Nella suite ne bastano 200, con il seme fisso (circa 30 s); le 2.000 si lanciano a mano, con un'opzione.
- **Casi limite del §6**, uno per uno, su serie di poche barre a prezzi scritti a mano, con il risultato atteso scritto nel test (non solo «uguale all'oracolo»).
- **Il capitale esaurito (§3.2):** su E12_SHORT_ENGULFING di BTC, fino alla barra dell'annullo trade uguali; dopo, il motore veloce ha i trade in più e l'avviso.
- **Sezione D di `docs/21`** (D1 commissione, D2 spread, D3 stop non attivo sulla barra d'ingresso) rifatta con il motore veloce, accanto a quella con la libreria.
- **Dipendenza assente:** con numba non importabile, `motore="veloce"` ripiega su «bt» con l'avviso, senza fermarsi.

### 7.2 · Il resto

- **Tutte le 36 suite** girano due volte in E2 (motore «bt» e «veloce», con una variabile d'ambiente che cambia il predefinito): stessi `RISULTATO n/n`. Le suite che costruiscono `Backtest` a mano (`test_velocita.py`, `test_inversione.py`, …) restano sull'oracolo.
- **Identità dei due notebook vivi** su BINANCE_PERP_BTCUSDT e giro completo su BYBIT_SPOT_ETHUSDT, con «bt» e con «veloce»: ogni tabella, ogni numero, ogni trade uguale (come per A e B, `docs/63` §4–§5).
- **`test_velocita.py` esteso:** tempo di un backtest, della ricerca dei filtri e della schermata 5, «bt» contro «veloce», stampato (non è un test che fallisce: dipende dal PC).

---

## 8 · Piano di passaggio

| passo | cosa | cosa cambia nei numeri |
|---|---|---|
| **E1** | `engine/motore_veloce.py` e `test_motore_veloce.py`. Nessun motore lo usa ancora | niente |
| **E2** | parametro `motore=` in `run_exit_search_bt`, `run_filter_search_bt`, `due_meta`, `prepara` (Lab) e `MOTORE` nel notebook di ricerca; predefinito ancora «bt». Identità dei due notebook con «bt» e «veloce»; `numba==0.68.0` nella cella d'installazione dei tre notebook e prova su Colab (la fa Mattia) | niente (salvo il §3.2, se Mattia sceglie la proposta) |
| **E3** | il predefinito diventa «veloce». Con «veloce» i processi della ricerca dei filtri non servono più (30 backtest in circa 0,25 s; avviare 6 processi su Windows costa di più): con «veloce» si va in sequenza, `processi=` resta per «bt». Misurato prima di decidere | niente |
| **E4** (facoltativo) | quello che resta del tempo (§1): **maschere dei filtri in cache** per lo stesso df nella stessa sessione (la seconda chiamata le riusa: identiche per costruzione; le due metà di `due_meta` hanno le loro); **i 3 filtri VWAP** (`regression_trend_fit`, 2,2 s su 4,6) più veloci con lo stesso risultato; **il bootstrap** di P(EV<0) con gli stessi numeri casuali e una media più veloce, solo se resta identico al bit | niente: ogni pezzo con la sua prova di identità |

Un ramo per passo (`motore-veloce-e1`, …), una PR ciascuno, il merge lo fa Mattia. E1 ed E2 possono stare sullo stesso ramo se Mattia preferisce una PR sola.

---

## 9 · Tempi: prima e dopo

Misure sul PC di Mattia (6 processori), BINANCE_PERP_BTCUSDT, come al §1. «Dopo» è **misurato** sul prototipo per il backtest; per il resto è una **stima** fatta sommando le parti misurate (backtest veloce + maschere + bootstrap + resto).

| cosa | oggi | dopo E1–E3 | dopo E4 |
|---|---|---|---|
| un backtest | 852 ms | **circa 7 ms** (misurato) | — |
| ricerca dei filtri, 30 righe | 31 s in sequenza · 18,8 s con 6 processi | circa 8 s | circa 3–4 s (la prima volta sul df), meno di 3 s le volte dopo |
| `due_meta`, base + 5 filtri | 6,3 s | circa 2–3 s (maschere e bootstrap sulle metà) | circa 1–2 s |
| schermata 5 del Lab | circa 32 s (19 s nel notebook, con i processi) | circa 8–10 s | circa 4–5 s |
| giro del mercato nullo | circa 137 s | circa 20–25 s | circa 12–15 s |
| 500 giri × 2 symbol | circa 37 ore | circa 6–7 ore | circa 3–4 ore |

Il mercato nullo resta **sospeso** (`docs/63` §10.3): la riga serve solo a dare un'idea del guadagno su un lavoro lungo.

### 9 bis · La suite dei test

Misurata il 21/10, una suite dopo l'altra: **36 suite in circa 32 minuti** (1.931 s). Le più lunghe, e quanto pesa il backtest dentro ciascuna (profilo):

| suite | tempo | backtest |
|---|---|---|
| `test_vetrina.py` (il Lab intero su più symbol) | 416 s | quasi tutto |
| `test_vetrina_trigger.py` | 293 s | circa l'85% |
| `test_indicatori_tradingview.py` | 214 s | niente (indicatori e lookahead) |
| `test_vsa_modulo_unico.py` | 198 s | niente |
| `test_mercato_nullo.py` | 83 s | quasi tutto |
| le altre 31 | 727 s | in parte (giri del Lab, ricerche brevi) |

Stima dopo E1–E3: **circa 18–20 minuti**. Il guadagno è minore che sul Lab perché le suite degli indicatori (circa 7 minuti) non usano il backtest, e quelle che costruiscono `Backtest` a mano restano sull'oracolo per scelta; in più `test_motore_veloce.py` aggiunge circa 30 s. Con E4 si scende ancora un po' (maschere dei filtri).

---

## 10 · Dopo il passaggio

- **Processi (`processi=`):** vedi E3. Con «veloce» il costo vero della ricerca dei filtri diventa le maschere (E4), non i backtest.
- **`confidenza.py` in bp** (annotato in `docs/00`): **consiglio subito dopo E, su un ramo a parte.** E si giudica con una prova sola, «nessun numero cambia»; la confidenza in bp invece cambia i numeri della confidenza (soglie in «bp netti medi» invece di «pips netti medi», `esiti_trade` con `netti_in_unita`). Metterli insieme toglierebbe a E la sua prova. È un lavoro piccolo: `esiti_trade`, `confidenza_rolling`, `registra_filtro_confidenza`, `report_calibrazione` prendono `unita`, come i motori dal 20/10.
- **Lo sharpe che ordina le uscite** nel notebook di ricerca e le statistiche in % della libreria (§2.6): con il motore nuovo si possono calcolare per unità e in bp, oppure togliere. Domanda 5, da decidere dopo E.

---

## 11 · Rischi

- **Un comportamento della libreria non visto dall'inventario.** Difesa: l'oracolo su migliaia di configurazioni casuali e su dati costruiti per i casi limite, più l'identità dei notebook. Il prototipo non ha trovato differenze, ma il collaudo va rifatto sul codice vero.
- **numba su Colab.** Colab di solito ha numba già installato; la versione bloccata va provata lì (E2). Se non si installa: «bt», con l'avviso.
- **Prima compilazione.** Circa 3 s alla prima chiamata, la prima volta (poi `cache=True` la tiene su disco, in `__pycache__`, già nel `.gitignore`; su Colab si rifà a ogni sessione nuova).
- **Due motori da tenere allineati.** Ogni modifica futura alla strategia (una regola d'uscita nuova, per esempio) va fatta due volte, in `_StrategiaGenerica` e nel ciclo compilato; l'oracolo dice subito se non coincidono. Per questo `backtesting.py` resta installato e i test lo usano sempre.
- **Il §3.2 cambia alcuni numeri**, se approvato: solo per i sistemi che esauriscono il capitale simulato, e sempre nella direzione di contare tutti i trade.

---

## 12 · Domande per Mattia

1. **Tecnica:** ciclo compilato con numba (strada A, consigliata e già provata con il prototipo)?
2. **Comportamenti discutibili** (stop non attivo sulla barra d'ingresso, stop che vince sul target nella stessa barra, gap riempiti all'Open): si replicano identici adesso e si correggono dopo, in un lavoro a parte (consigliato)?
3. **`confidenza.py` in bp:** subito dopo E, su un ramo a parte (consigliato, §10), o dentro E?
4. **Capitale simulato esaurito (§3.2):** il motore veloce tiene tutti i trade per unità e segna NaN nelle statistiche in % da lì in poi, con un avviso (consigliato)? Oppure replica anche l'annullo degli ordini della libreria, per avere identità anche lì (e il difetto resta)?
5. **Statistiche in % della libreria** (`pnl_pct`, `sharpe`, `max_dd_pct`) e lo sharpe che ordina `es.top()`: si tengono identiche in E (consigliato) e se ne decide dopo?
6. **E4** (maschere in cache, VWAP, bootstrap): dentro questo lavoro, subito dopo E3, o più avanti?
7. **Rami:** E1 ed E2 su un ramo solo (una PR) o separati?

---

## 13 · Decisioni di Mattia (21/10/2026)

| # | decisione |
|---|---|
| 1 | **numba 0.68.0, strada A** (ciclo compilato). |
| 2 | **I comportamenti della libreria si copiano identici** in E. La correzione è un lavoro a parte, **subito dopo E**; per primo lo stop non attivo sulla barra d'ingresso. |
| 3 | **`confidenza.py` in bp subito dopo E**, su un ramo a parte. |
| 4 | **Capitale simulato esaurito:** si tengono **tutti i trade per unità**; le statistiche in % (`pnl_pct`, `sharpe`, `max_dd_pct`) diventano NaN da quel trade in poi, con un **avviso con la data**. È l'**unica differenza dichiarata** di E: la PR elenca i sistemi in cui cambia qualcosa. |
| 5 | **Statistiche in % e sharpe identici in E.** Subito dopo, una proposta per sostituire l'ordinamento per sharpe di `top()` con il **t nell'unità che decide**. |
| 6 | **E4 subito dopo E3**, PR a parte. |
| 7 | **E1 + E2 in una PR, E3 in un'altra.** |

**In più:** una **suite rapida** (un comando solo, 2–3 minuti, le suite legate al codice toccato) da usare durante il lavoro; la **suite completa resta obbligatoria prima di ogni PR**.

**Ordine che ne segue:** E1 + E2 (`motore-veloce-e1-e2`) → E3 → E4 → correzione dei comportamenti della libreria (prima lo stop sulla barra d'ingresso) → `confidenza.py` in bp → proposta sull'ordinamento di `top()`. Poi il resto di `docs/63` §10.3 (soglia cumulata, atlante, money management).

---

## 14 · Fatto: E1 + E2 (21/10/2026, ramo `motore-veloce-e1-e2`)

### 14.1 · Cosa c'è

- **`engine/motore_veloce.py`** (nuovo): `MotoreVeloce`, con la stessa interfaccia di `Backtest` (`MotoreVeloce(df_bt, cash=, spread=, commission=, margin=, exclusive_orders=True).run(...)`); il ciclo per unità `_ciclo` e il livello dei soldi `_soldi`, compilati con numba; `_statistiche` (le cinque voci lette dal tool); `scegli_motore`, `MOTORE_PREDEFINITO` (`"bt"` fino a E3; la variabile d'ambiente `TSC_MOTORE` lo cambia), `DISPONIBILE` (senza numba «veloce» ripiega su «bt» con un avviso). Il risultato di `run` ha anche `_capitale_esaurito` (la data, o None) e `_trade_esaurito` (da quale trade).
- **Parametro `motore=`** (None = il predefinito) in `run_exit_search_bt`, `run_filter_search_bt` (con «veloce» sempre in sequenza: i processi non servono), `due_meta` (None = quello di `fs`), `vetrina.prepara` (`s.motore`, passato a ogni backtest da `_kw_motore`). `ExitSearchBT` e `FilterSearchBT` ricordano `.motore`. Modifiche additive: con «bt» tutto come prima.
- **Notebook di ricerca:** `MOTORE = None` nella cella dei dati (accanto a `UNITA` e `FUNDING`), passato a ogni motore. **Cella d'installazione** dei due notebook vivi e del notebook di collaudo: `numba==0.68.0` accanto alle altre versioni bloccate. Il Lab broker, sospeso, non si tocca.
- **`test_motore_veloce.py`** (nuovo, 30 test, circa 35 s; `--tante` per 2.000 configurazioni, circa 5 minuti): oracolo, casi limite del §6, sezione D di `docs/21`, capitale esaurito, scelta del motore, i tre motori del tool con «bt» e «veloce».
- **`suite_rapida.py`** (nuovo, §13): `python suite_rapida.py` (la rapida, 2–3 minuti), `--tutte` (la completa), `--motore veloce`, nomi di suite a mano, `--secondi`.

### 14.2 · Collaudo

| prova | esito |
|---|---|
| oracolo, 200 configurazioni (nella suite) | 200 identiche al bit, 84.885 trade |
| oracolo, 2.000 configurazioni (`--tante`) | 1.998 identiche al bit (1.002.733 trade); 2 con il capitale esaurito, identiche fino a quel trade |
| casi limite (§6) e sezione D | tutti come atteso, uguali all'oracolo |
| Lab crypto, main contro questo ramo con «bt», BINANCE_PERP_BTCUSDT e BYBIT_SPOT_ETHUSDT (giro completo, nove schermate) | ogni numero identico |
| Lab crypto, «bt» contro «veloce», stessi due symbol | ogni numero identico (il sistema E23 non esaurisce il capitale) |
| notebook di ricerca, main contro «bt», BINANCE_PERP_BTCUSDT | 48 celle su 49 uguali; l'unica diversa stampa la cartella del progetto |
| notebook di ricerca, «bt» contro «veloce», BINANCE_PERP_BTCUSDT, capitale del tool (10 milioni) | 16 celle diverse: tutte per il capitale esaurito, sotto |
| notebook di ricerca, «bt» contro «veloce», capitale 10^15 (nessuno dei due si esaurisce) | **49 celle su 49 uguali** |
| suite completa con «bt» e con «veloce» | §14.4 |

### 14.3 · Dove cambia qualcosa: il capitale esaurito (decisione 4)

**Nel notebook di ricerca** su BINANCE_PERP_BTCUSDT (i trigger predefiniti del notebook sono due composite in OR, con migliaia di trade) il capitale simulato della libreria arriva a −99,5% e in 14 backtest si esaurisce fra febbraio e dicembre 2024: celle 44 e 47 (ricerca delle uscite: 7 combinazioni), 54 (ricerca dei filtri: il sistema base e 4 filtri), 64 (la storia della confidenza), 66 (i filtri di confidenza). Per esempio il sistema base: 4.235 trade con «bt», 5.545 con «veloce». Le celle dopo (classifiche, due metà, money management, stress) cambiano di conseguenza.

**Nel catalogo**, ogni entry da sola con le uscite predefinite del Lab, in-sample, M15, H 25: **48 sistemi su 16 symbol** (11 symbol colpiti; nessuno su BINANCE_SPOT_SOLUSDT, BINANCE_SPOT_XRPUSDT, BINANCE_PERP_XRPUSDT, BYBIT_SPOT_XRPUSDT, BYBIT_PERP_SOLUSDT, BYBIT_PERP_XRPUSDT). In tutti il motore veloce conta più trade (tutto l'in-sample), la libreria meno:

| symbol | sistemi | il caso più grande |
|---|---|---|
| BINANCE_SPOT_BTCUSDT | 10 | E24_CYCLE_TURN_UP: 5.553 contro 3.269 |
| BINANCE_SPOT_ETHUSDT | 2 | E12_ENGULFING: 5.631 contro 4.993 |
| BINANCE_PERP_BTCUSDT | 8 | E24_SHORT_CYCLE_TURN_DOWN: 5.527 contro 3.867 |
| BINANCE_PERP_ETHUSDT | 5 | E3_SHORT_INTRABAR_STRENGTH_FADE: 5.163 contro 4.301 |
| BINANCE_PERP_SOLUSDT | 3 | E24_SHORT_CYCLE_TURN_DOWN: 4.907 contro 3.482 |
| BYBIT_SPOT_BTCUSDT | 8 | E12_ENGULFING: 4.850 contro 2.984 |
| BYBIT_SPOT_ETHUSDT | 1 | E12_ENGULFING: 4.801 contro 4.563 |
| BYBIT_SPOT_SOLUSDT | 1 | E24_CYCLE_TURN_UP: 4.033 contro 3.980 |
| BYBIT_PERP_BTCUSDT | 9 | E12_SHORT_ENGULFING: 6.002 contro 3.413 |
| BYBIT_PERP_ETHUSDT | 1 | E12_SHORT_ENGULFING: 5.063 contro 5.060 |

L'elenco completo, entry per entry, è nella descrizione della Pull request. Qualunque altro sistema (altre uscite, filtri, coppie) può esaurire il capitale: il motore veloce lo dice ogni volta, con la data.

**Una correzione al §3.2:** quando il capitale non basta, la libreria annulla gli ordini **finché il prezzo non scende abbastanza** da tornare a comprare una unità; poi riprende, su un'altra strada. I trade coincidono fino al primo ordine annullato, non oltre.

### 14.4 · Tempi (misurati il 21/10 sul PC)

| cosa | «bt» | «veloce» |
|---|---|---|
| Lab, schermata 4 (uscite), BINANCE_PERP_BTCUSDT, E23 | 3,2 s | 0,8 s |
| Lab, schermata 5 (trova la strategia), in sequenza | 33,2 s | **8,7 s** |
| notebook di ricerca, cella 54 (ricerca dei filtri), in uno script (in sequenza) | 43,1 s | 15,1 s |
| notebook di ricerca, tutte le celle | 128 s | 84 s |
| suite completa (37 suite, una dopo l'altra) | 32,9 min, 37/37 | 28,8 min, 37/37 |

Il resto del tempo della schermata 5 sono le maschere dei filtri e il bootstrap: è il lavoro di E4. La suite completa guadagna poco perché quasi tutto il suo tempo sono indicatori e preparazione, non backtest.

**Suite completa con «veloce»:** al primo giro `test_portabilita` dava 11/13. I test 10 e 11 controllano proprio la differenza dichiarata: con capitale troppo piccolo backtesting.py dà zero trade, il motore veloce li tiene tutti e scrive l'avviso «capitale esaurito». Ora i due test controllano, per ciascun motore, il comportamento giusto: 13/13 con tutti e due. Da fare in E3: l'avviso del tool «i trade SPARISCONO» (controlli.avviso_capitale) vale solo per backtesting.py; quando il veloce diventa il predefinito va riscritto (fatto in E3, §15.1).

## 15 · Fatto: E3 (21/10/2026, ramo `motore-veloce-e3`)

### 15.1 · Cosa cambia

- **«veloce» è il predefinito** (`MOTORE_PREDEFINITO` in `engine/motore_veloce.py`) per Lab, notebook di ricerca (`MOTORE = None`) e motori. «bt» resta: `motore="bt"`, `MOTORE = "bt"` nel notebook, oppure `TSC_MOTORE=bt` per tutto. `backtesting.py` resta l'oracolo dei test. Senza numba si torna da soli a «bt», con un avviso.
- `Sessione.motore`, `ExitSearchBT.motore` e `FilterSearchBT.motore` valgono `None` se nessuno li sceglie (= il predefinito).
- **Ricerca dei filtri con «veloce»: in sequenza.** Misurato prima di decidere, 30 righe su BINANCE_PERP_BTCUSDT: **8,5 s in sequenza, 18,2 s con 6 processi** (con «bt»: 33,1 s e 20,1 s). Con «veloce» un backtest dura millisecondi: nei processi andrebbe solo quello, il resto della riga resta nel processo principale, e avviarli costa di più. `processi=` resta per «bt».
- **Avviso del capitale:** `controlli.avviso_capitale` («i trade SPARISCONO») ha il parametro `motore` e stampa solo con «bt». Con «veloce» non si perde nessun trade: se il capitale simulato si esaurisce, avvisa il motore, con la data e il numero del trade.
- `test_portabilita.py`: le prove sul capitale girano con tutti e due i motori, ognuno col suo comportamento (18 test).

### 15.2 · Identità «bt» contro «veloce»

| prova | esito |
|---|---|
| Lab crypto, giro completo (nove schermate), BINANCE_PERP_BTCUSDT e BYBIT_SPOT_ETHUSDT | ogni numero identico; nessun capitale esaurito |
| notebook di ricerca, BINANCE_PERP_BTCUSDT, capitale del notebook (10 milioni) | 33 celle uguali, 16 diverse: tutte per il capitale esaurito (sotto) |
| notebook di ricerca, BYBIT_SPOT_ETHUSDT, capitale del notebook | 36 celle uguali, 13 diverse: tutte per il capitale esaurito (sotto) |
| notebook di ricerca, tutti e due i symbol, capitale 10^15 (nessuno si esaurisce) | **49 celle su 49 uguali**, nessun avviso |

**I sistemi in cui cambia qualcosa** (capitale esaurito; il motore veloce tiene tutti i trade per unità, la libreria ne annulla una parte da quella data). Le celle dopo queste (classifiche, due metà, Monte Carlo, money management) cambiano di conseguenza.

| symbol | cella | backtest colpiti: esaurito dal (trade k di n, conteggio del veloce) |
|---|---|---|
| BINANCE_PERP_BTCUSDT | 44 · ricerca delle uscite, prima combinazione | 01/03/2024 (4.217 di 5.545) |
| BINANCE_PERP_BTCUSDT | 47 · ricerca delle uscite | 6 combinazioni: 04/03/2024 (4.323 di 5.676), 10/02/2024 (4.986 di 6.623), 07/02/2024 (5.698 di 7.604), 01/03/2024 (4.217 di 5.545), 10/02/2024 (4.328 di 5.749), 01/03/2024 (4.217 di 5.545) |
| BINANCE_PERP_BTCUSDT | 54 · ricerca dei filtri | sistema base 01/03/2024 (4.217 di 5.545) e 4 filtri: 16/12/2024 (3.597 di 3.962), 08/04/2024 (3.750 di 4.807), 14/11/2024 (2.778 di 3.121), 11/11/2024 (3.167 di 3.567) |
| BINANCE_PERP_BTCUSDT | 64 · la storia del setup su tutta la serie | 01/03/2024 (4.217 di 6.919) |
| BINANCE_PERP_BTCUSDT | 66 · filtri di confidenza | 20/05/2024 (4.215 di 5.312) |
| BYBIT_SPOT_ETHUSDT | 44 · ricerca delle uscite, prima combinazione | 12/08/2025 (3.798 di 3.909) |
| BYBIT_SPOT_ETHUSDT | 47 · ricerca delle uscite | 6 combinazioni: 09/08/2025 (3.898 di 4.017), 13/12/2024 (3.856 di 4.768), 16/07/2024 (3.887 di 5.481), 12/08/2025 (3.798 di 3.909), 21/07/2025 (3.884 di 4.061), 12/08/2025 (3.798 di 3.909) |
| BYBIT_SPOT_ETHUSDT | 54 · ricerca dei filtri | sistema base 12/08/2025 (3.798 di 3.909) |
| BYBIT_SPOT_ETHUSDT | 64 · la storia del setup su tutta la serie | 12/08/2025 (3.798 di 4.858) |

Su BINANCE_PERP_BTCUSDT sono gli stessi 14 backtest del §14.3. Per il catalogo vale l'elenco dei 48 sistemi del §14.3 (PR #45).

### 15.3 · Tempi prima / dopo (PC di Mattia, BINANCE_PERP_BTCUSDT)

| cosa | prima («bt») | dopo («veloce») |
|---|---|---|
| un backtest (`run_exit_search_bt`, una combinazione, con metriche e giudizio) | 1,30 s | 0,43 s (il ciclo da solo: millisecondi) |
| Lab, schermata 5 (trova la strategia) | 33,2 s | **8,7 s** |
| suite completa, 37/37 | 32,9 min | 28,7 min (quasi tutto il tempo sono indicatori e preparazione) |
