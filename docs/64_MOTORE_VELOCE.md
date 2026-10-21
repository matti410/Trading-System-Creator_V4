# 64 · Incarico: un motore di backtest veloce al posto di backtesting.py

**Data:** 21 ottobre 2026
**Stato:** INCARICO DI STUDIO. **Nessun codice** prima dell'OK di Mattia.
**Consegna attesa:** `docs/65_PROPOSTA_MOTORE_VELOCE.md` (inventario del comportamento da replicare, scelta della tecnica con i perché, firme, piano di collaudo, piano di passaggio, tempi misurati, domande).
**Da leggere prima:** `CLAUDE.md`, `docs/00`, `docs/21` (sezione D: i comportamenti di `backtesting.py` su cui si regge il tool), `docs/63` (§7, mercato nullo); i moduli `engine/exit_search_bt.py` (`_StrategiaGenerica`, `soglie_adattive`, `run_exit_search_bt`), `engine/filter_search_bt.py`, `engine/due_meta.py`, `engine/confidenza.py`, `engine/metriche.py`, `engine/quarantena_trade.py`, `engine/exchange.py` (funding), `engine/vetrina.py`, `engine/mercato_nullo.py`, `test_velocita.py`.

---

## 0 · Perché

Il backtest è il collo di bottiglia di tutto il tool:
- la ricerca dei filtri (38 backtest, più le due metà) richiede circa 45 secondi per sistema;
- un giro del mercato nullo richiedeva circa 137 secondi (500 giri × 2 symbol ≈ 37 ore): è il motivo per cui il mercato nullo è stato **sospeso** il 21/10/2026 (`docs/63` §7, §10.3);
- l'atlante (lavoro C) moltiplicherà i backtest al passo 5;
- **ogni lavoro di sviluppo paga questi tempi**: collaudi, identità dei notebook, giri completi. Un backtest lento allunga i tempi di sviluppo, non solo quelli di calcolo. In prospettiva di un prodotto usato da altri, ogni sessione deve restare nell'ordine dei secondi.

**Cosa NON cambia:** il motore sostituisce solo il ciclo che simula i trade. Dati, costi, funding, giornata UTC, unità, indicatori, catalogo, rosa, ricerca dei filtri, due metà, giudizio, money management, schermate del Lab e test esistenti restano com'erano e lavorano sui trade del motore nuovo, che sono gli stessi.

**Obiettivo:** un motore proprio che dia **gli stessi trade** di oggi, almeno **50 volte più veloce**. `backtesting.py` resta installato solo come **riferimento nei test**.

---

## 1 · Vincoli e decisioni già prese

1. **Stessi trade, al centesimo.** Il motore nuovo è un sostituto, non una versione nuova della strategia: entrata, uscita, prezzi, lato, stop e target devono coincidere trade per trade con `_StrategiaGenerica` su `backtesting==0.6.6`. I comportamenti discutibili (per esempio lo stop non attivo sulla barra d'ingresso, `docs/00`) **si replicano identici**. Si correggono, se Mattia lo decide, solo dopo, in un lavoro a parte e dichiarato.
2. **Niente VectorBT.** È stato tolto il 16/9/2026 perché l'uscita a tempo si disallineava quando uno stop chiudeva prima un trade (`exit_search_bt.py`, docstring).
3. **«Vettorizzare» in senso stretto non basta**, e la proposta deve spiegarlo: con una posizione alla volta (`exclusive_orders=True`) un segnale apre un trade solo se il precedente è già chiuso, quindi ogni trade dipende da quello prima. La strada attesa è un **ciclo compilato** (per esempio con numba) sugli array numpy, con le parti indipendenti (soglie adattive, maschere dei segnali, costi, funding) calcolate in modo vettoriale fuori dal ciclo. Se la proposta trova una strada migliore, la confronta con questa.
4. **Il motore lavora per 1 unità**, i risultati sono in pips, bp e ATR come oggi. Cassa, margine e dimensione della posizione di `backtesting.py` servivano solo alla libreria: il problema «prezzo > capitale» (`docs/00`, 25/9) sparisce.
5. **Modifica additiva nel passaggio:** parametro `motore="veloce" | "bt"` in `run_exit_search_bt`, `run_filter_search_bt`, `due_meta` e nel Lab. Il predefinito diventa «veloce» solo dopo il collaudo di identità.
6. **Perimetro:** crypto da exchange (`docs/63` §10.0). Il lato broker sospeso deve però continuare a passare i suoi test: il motore è condiviso.

---

## 2 · Cosa chiedo nella proposta

### 2.1 · Inventario del comportamento da replicare
Una tabella, una riga per regola, con la fonte (riga di `_StrategiaGenerica` o di `backtesting.py` 0.6.6) e il test che la verifica. Almeno:
- ingresso all'Open della barra dopo il segnale; segnale long e short sulla stessa barra: nessun ingresso;
- spread dentro il prezzo d'ingresso, una volta sola; commissione su entrambi i lati, fuori dal prezzo (`docs/21` D1, D2);
- stop e target fissati alla barra d'ingresso dalle soglie adattive, **attivi dalla barra dopo** (D3);
- come `backtesting.py` riempie stop e target dentro la barra: gap oltre lo stop (fill all'Open?), stop e target toccati nella stessa barra (chi vince?);
- uscita a regola: chiusura all'Open della barra dopo; uscita a tempo all'Open della barra `n_barre` dopo l'ingresso, scadenza diversa per lato;
- inversione su segnale opposto (`inverti_su_opposto`) e le sue precedenze;
- segnali in quarantena (`quarantena_trade`), `CostoExtraPips`, `FundingPips`;
- trade ancora aperto alla fine dei dati: cosa fa la libreria oggi;
- le statistiche che oggi vengono dalla libreria (`pnl_pct`, `sharpe`, `max_dd_pct`): chi le usa ancora, e se vanno ricalcolate o tolte (`docs/00` segnala che `top()` ordina ancora per `sharpe`).

### 2.2 · Firme (nomi indicativi)
Una funzione che riceve gli array (Open, High, Low, Close, maschere dei segnali long e short, colonne di uscita, soglie sl/tp per lato, scadenze, spread, commissione, interruttore dell'inversione) e restituisce la tabella dei trade **con le stesse colonne** che usa oggi il resto del tool (`Size`, `EntryBar`, `ExitBar`, `EntryPrice`, `ExitPrice`, `EntryTime`, `ExitTime`, `SL`, `TP` e le altre lette da `metriche`, `confidenza`, `mm_adattatore`, `vetrina_verifica`). Così nessun modulo a valle cambia.

### 2.3 · Collaudo
- **Oracolo:** `backtesting.py` 0.6.6 con `_StrategiaGenerica`. Migliaia di configurazioni casuali (lati, scadenze, stop e target accesi o spenti, regole di uscita, inversione, quarantena, spread e commissione) su dati veri e su dati costruiti apposta per i casi limite (gap, stop e target nella stessa barra, segnale sull'ultima barra). Trade identici, uno per uno.
- La sezione D di `docs/21` rifatta sul motore nuovo.
- Identità dei due notebook vivi su BINANCE_PERP_BTCUSDT e giro completo su BYBIT_SPOT_ETHUSDT, con motore «bt» e «veloce»: stessi numeri.
- `test_velocita.py` esteso: tempi prima e dopo.

### 2.4 · Tempi da misurare sul PC di Mattia
Un backtest singolo, la ricerca dei filtri con le due metà, la schermata 5 del Lab, un giro del mercato nullo, la suite completa dei test. Prima e dopo, con la stima dei 500 giri × 2 symbol.

### 2.5 · Dipendenze
Versione bloccata della libreria nuova (per esempio numba) come `TA-Lib` e `backtesting`; prova che si installa su Windows e su Colab. Cosa succede se non si installa: si ripiega su «bt» con un avviso, non si ferma il notebook.

### 2.6 · Dopo il passaggio
- Cosa fare dei motori paralleli su più processi della ricerca dei filtri (`processi=`): con backtest da millisecondi probabilmente non servono più. Misurarlo.
- Allineare `confidenza.py` all'unità che decide (bp sulle crypto), annotato in `docs/00`: può entrare in questo lavoro o subito dopo. Va proposto.

---

## 3 · Domande per Mattia (da completare nella proposta)
1. Tecnica: ciclo compilato con numba (consigliato) o altra?
2. I comportamenti discutibili si replicano identici adesso e si correggono dopo, in un lavoro a parte (consigliato)?
3. `confidenza.py` in bp dentro questo lavoro o subito dopo?
