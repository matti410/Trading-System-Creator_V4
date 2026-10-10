# 00 · Scopo del progetto e stato del tool
 
**Da leggere per primo.** Aggiornato: 25 settembre 2026, sera. Il 7 ottobre 2026 aggiunti: la riga `50` nella tabella dei documenti, il punto 4 di «Cosa manca» (sovrapposizioni) e le righe `30`–`33`, `40`, `92`, `93` nella tabella dei documenti. Le sezioni «Cosa c'è nel tool» e «Dove siamo» restano alla fotografia del 25–26/9: per lo stato dopo il 26/9 si leggono i documenti `30`–`33`, `40`, `92` e `93`.
 
**Repo (pubblico):** `github.com/matti410/Trading-System-Creator_V4`
**Notebook:** `Trading_Grid_Search_v4_backtesting.ipynb` (principale) e
`Collaudo_Catalogo.ipynb` (collaudo del catalogo), girano in Colab.
 
---
 
## Cos'è questo progetto
 
**Uno strumento per scovare strategie di trading.** Una base, che cresce
aggiungendo condizioni di ingresso, filtri, uscite, diagnostiche.
 
Non è la ricerca di un edge su EURUSD. EURUSD M15 è il **dataset di
sviluppo**: fa girare il codice e fa emergere i difetti degli strumenti. È
piatto, ed è utile proprio per questo — fa vedere come appare il nulla.
 
---
 
## LA REGOLA CHE VIENE PRIMA DI TUTTE
 
> **I risultati sui dati non sono il metro di giudizio del progetto.**
 
Quando una condizione non produce nulla su EURUSD, **la risposta corretta è
«bene, il tool funziona e me lo dice»**, non «questa strada è morta».
 
Concretamente, quando si lavora qui:
 
- **Non si commenta se un sistema "tiene" o no**, a meno che non venga chiesto
  esplicitamente.
- **Non si propone di cambiare asset, famiglia di segnali o approccio** perché
  i `t` sono bassi. Quella è una decisione di ricerca, e la prende Mattia.
- **Non si scrivono conclusioni tipo «capitolo chiuso», «non è un edge da
  inseguire», «la pipeline gira a vuoto».** Sono fuori scopo.
- I numeri che escono dai run servono a **collaudare il tool**: dicono che il
  codice gira, che le occorrenze sono plausibili, che i segni sono coerenti.
  Si riportano come collaudo, non come verdetto.
È stato ripetuto molte volte. Se una risposta scivola nel giudizio sui
risultati, è un errore da correggere, non una sfumatura.
 
---
 
## Dove sta cosa
 
**Il codice sta sul repo.** Nella knowledge NON ci vanno file `.py`: due copie
dello stesso file divergono, ed è già successo. Qui ci stanno le **decisioni**,
il perché di una scelta, le trappole trovate, le convenzioni.
 
Ordine di lettura dei documenti:
 
| | documento | cosa contiene |
|---|---|---|
| 00 | questo | scopo, stato, cosa manca |
| 01 | `01_ROADMAP.md` | il metodo: i sette passi e perché in quell'ordine |
| 02 | `02_KPI_E_GIUDIZIO.md` | i criteri di lettura di un risultato, le soglie di rumore |
| 10 | `10_DATI_FUSO_BROKER.md` | la regola del fuso del broker, verificata |
| 11 | `11_DATI_QUARANTENA.md` | quarantena, sessioni, entry-metro |
| 20 | `20_CONDIZIONI_TEMPO.md` | E22, E23, F20–F22 e le trappole trovate |
| 21 | `21_COLLAUDO_CATALOGO.md` | test di lookahead e degenerazione su tutto il catalogo, il difetto trovato in `range_finestra` |
| 30 | `30_ML_LONG_SHORT.md` | ramo ML (repo `Trading-System-Pipeline-ML`, esperimento distinto da V4): due modelli di meta-labeling, uno per lato; split, target, primo modello, backtest OOS |
| 31 | `31_COSTI_SYMBOL.md` | costi per symbol in pips, sul conto IC Markets EU Standard: tabella automatica `costi_symbol.py` (ramo ML, 29/9) |
| 32 | `32_RIORDINO_CONDIZIONI.md` | riordino del 1/10 nel ramo ML: doppioni tolti (filtri da 20 a 12, trigger da 26 a 18 per lato) e `diagnostica.sovrapposizioni` |
| 33 | `33_INVERSIONE_E_OR.md` | repo V4, 5/10: entry in OR e inversione su segnale opposto, una posizione alla volta (`entry_composita`, `inverti_su_opposto`) |
| 40 | `40_NOTEBOOK_SLIM.md` | specifica del notebook «vetrina» da presentare (`engine/vetrina.py`, `Trading_System_Lab.ipynb`), con le correzioni del 7/10 |
| 50 | `50_IDEE_DA_ARTICOLI.md` | come trascrivere le idee degli articoli Medium in condizioni: flusso, scheda, convenzioni, trappole di lookahead, collaudo, registro delle idee |
| 90 | `90_AUDIT_2026-09-19.md` | audit della pipeline, fotografia datata |
| 91 | `91_NOTEBOOK_CELLE.md` | cosa resta da incollare nel notebook principale |
| 92 | `92_AUDIT_2026-10-05.md` | audit del notebook principale V4 del 5/10: cosa è stato verificato e le cose nuove trovate (quarantena sui trade, modello dei costi) |
| 93 | `93_QUARANTENA_TRADE_E_COSTI.md` | quarantena applicata ai trade e costi del conto Standard (5/10): chiude i punti 1 e 2 di `92` |
 
Più le tre lezioni del corso di Matteo Conti, caricate a parte, e il notebook di
Mattia `EV_MC_Analysis_Strategy_IP_final.ipynb` (Monte Carlo, punto di partenza
del passo 7).
 
---
 
## Cosa c'è nel tool
 
### Dati e tempo — la base
 
| modulo | cosa fa |
|---|---|
| `engine/broker_tz_diagnostic.py` | diagnosi del fuso, `to_utc_index()` |
| `engine/quarantena.py` | `verifica_indice_utc()`, `quarantena()` |
| `engine/sessioni.py` | catalogo sessioni in ora locale, `in_sessione()`, `barre_da_apertura()` |
| `engine/livelli.py` | `range_finestra()`, `giorno_fx()`, `al_ultima_apertura()`, `primo_del_giorno()` — corretto due volte il 24/9 (lookahead a fine storico; finestre che finiscono a mercato chiuso), vedi `20` trappole 4–5 |
| `engine/indicatori.py` | `aggiungi_indicatori(df)`: gli indicatori della cella del notebook (oggi la 16), in un posto solo |
 
### Motore di ricerca
 
| modulo | passo |
|---|---|
| `engine/event_study.py` | 1–2, orizzonti e ingressi |
| `engine/exit_search_bt.py` | 3, uscite |
| `engine/filter_search_bt.py` | 5, filtri |
| `engine/due_meta.py` | 5, stabilità sulle due metà |
| `engine/confidenza.py` | 5, confidenza dei segnali: griglia volatilità × trend, soglia come filtro (dal 25/9, vedi `01` passo 5) |
| `engine/volatility_features_engineering.py` | file di Mattia, invariato: `confidenza.py` usa `feat_historical_volatility` e `build_labels` |
| `engine/giudizio.py` | t, P(EV<0), soglia rumore, Monte Carlo, scheda, verdetto |
| `engine/montecarlo.py` | 7, yardstick 10/20/40/100 trade, Monte Carlo completo, sizing, grafici (dal 26/9) |
| `engine/costi.py` | costi per strumento dalle specifiche broker |
| `engine/metriche.py` | `avg_trade` / `avg_trade_netto` / `costo_pips` |
| `engine/controlli.py` | `avviso_capitale`: avvisa quando il prezzo supera il capitale (dal 25/9, richiamato dai due motori di backtest) |
| `engine/splitting.py`, `equity_plot.py`, `alpha_ops.py`, `vwap_ops.py`, `registry.py` | supporto |
 
Firme utili:
 
```python
# engine/costi.py
parametri_backtest(symbol, bars=None, valuta_conto="USD", percentile=75.0,
                   spread_pips=None, usa_mt5=True) -> {"spread":…, "commission":…}
deriva_costo_nel_tempo(...)     il costo anno per anno — obbligatorio su BTCUSD
COMMISSIONE_RT                  USD 7,00 · EUR 6,50 · GBP 5,50 · AUD 9,00
 
# engine/giudizio.py
t_stat(pips) · t_welch(a, b) · p_ev_negativo(pips) · ic_ev(pips)
soglia_rumore(k, alpha=0.05)    Šidák; k=17 → 2,97 · k=42 → 3,23
tenuti_scartati(...) · drawdown_montecarlo(pips) · scheda_strategia(...) · verdetto(...)
 
# engine/confidenza.py
congela_filtro(fs, filtro_scelto)                              -> (entry_long, entry_short) con il filtro dentro
congela_confidenza_nota(entry_l, entry_s, conf_l, conf_s)       -> entry ristrette ai segnali a confidenza nota
cella_contesto(df, direzione, finestra=500, finestra_vol=20)   -> 0..3
esiti_trade(trades, df, pip_size, commission)                  -> una riga per trade
confidenza_rolling(df, esiti, direzione, finestra_trade=500, min_obs=30)
registra_filtro_confidenza(soglie, conf_long=, conf_short=, metrica="pips_medi")
report_calibrazione(esiti, df, split, conf_long=, conf_short=, mostra_oos=False)
plot_oos_confidenza(trades_senza, trades_con, pip_size, commission)
 
# engine/collaudo_catalogo.py
verifica_lookahead(df_grezzo, prepara=aggiungi_indicatori, tagli_per_condizione=5)
verifica_degenerazione(df, min_occorrenze=30, copertura_max=0.95, distanza_grappolo=8)
condizioni_registrate() · tagli_standard(indice) · mercato_sintetico()
```
 
Commissione solo su **forex e metalli**; indici, crypto e azioni hanno il costo
tutto nello spread. Su BTCUSD la commissione è zero e conta solo lo spread, che
varia di **5 volte** al variare del prezzo.
 
### Catalogo delle condizioni
 
| file | contenuto |
|---|---|
| `entry_long.py` / `entry_short.py` | 28 entry per lato (E1–E23) |
| `entry_metro.py` | 5 entry-metro temporali (righello, non candidate); 10 con `anche_short=True` |
| `filter_conditions.py` | 29 filtri (F1–F22) |
| `vwap_regime_filter_conditions.py` | 5 filtri di regime VWAP |
| `exit_long.py` / `exit_short.py` | 4 uscite a regola per lato |
 
Con tutto registrato (metro short comprese) il registry contiene **108
condizioni**: 66 entry, 34 filtri, 8 exit, 0 bidirezionali.
 
I filtri di confidenza (`CONF_…`) non sono nel catalogo: nascono nel notebook,
da `registra_filtro_confidenza`, dopo la baseline. Non passano dal collaudo del
catalogo (non sono funzioni del solo prezzo); il loro lookahead lo verifica
`test_confidenza.py` troncando l'intera catena backtest → esiti → confidenza.
 
Non c'è caricamento automatico per scansione di cartella: la registrazione è
esplicita, con funzioni tipo `registra_trigger_long()` che scorrono un
dizionario. **Per aggiungere una condizione servono due cose: la funzione, e la
riga nel dizionario del suo file.** Un *file* di condizioni nuovo va aggiunto
anche alla lista `REGISTRAZIONI` di `Collaudo_Catalogo.ipynb`.
 
### Collaudo
 
**Suite da terminale:** `test_sessioni.py` (20), `test_entry_metro.py` (22),
`test_tempo_prezzo.py` (20), `test_filtri_tempo.py` (25), `test_confidenza.py`
(34, dal 25/9), `test_portabilita.py` (13, dal 25/9), `test_montecarlo.py` (17, dal 26/9). **151 su 151**, verificati il 25/9 con pandas 3.0 e 2.2. Si
lanciano da terminale, mai dal notebook.
 
**Notebook `Collaudo_Catalogo.ipynb`** (Colab, *Esegui tutto*, 2–3 minuti):
A1 23/23 trappole di lookahead · A2 16/16 casi di degenerazione · B lookahead
sul catalogo intero: **0 LOOKAHEAD** · C degenerazione su EURUSD vero · D 12/12 · E 6/6
comportamenti di `backtesting.py`. Dettagli in `21_COLLAUDO_CATALOGO.md`.
 
**Versioni bloccate:** `TA-Lib==0.8.1`, `backtesting==0.6.6` (cella 2 del
notebook principale e preparazione del notebook di collaudo). Si cambiano solo
insieme, poi si rilancia il collaudo: la sezione D dice se il tool regge.
 
**Da rilanciare ogni volta che si aggiunge una condizione.**
 
---
 
## Cosa manca AL TOOL
 
In ordine di importanza per uno strumento che deve scovare strategie.
 
### ~~1. Nessun test di lookahead sull'intero catalogo~~ — FATTO il 24/9
 
`verifica_lookahead` in `engine/collaudo_catalogo.py`, per troncamento, su ogni
condizione registrata e su ogni indicatore. Al primo giro ha trovato un
lookahead vero in `range_finestra` (E22, F21), corretto. Vedi `21`.
 
### ~~2. Nessun controllo di degenerazione automatico~~ — FATTO il 24/9
 
`verifica_degenerazione`, stesso modulo. Si legge sui dati veri, senza
promosso/bocciato. Vedi `21`.
 
### 3. Il conteggio dei test multipli — fatto per chiamata il 24/9, resta il cumulato
 
Ogni passo che sceglie «il migliore fra tanti» ora calcola da sé la soglia di
rumore sulle prove di **quella chiamata** e mette la colonna `oltre_rumore`:
 
- **event study** (passi 1–2): k = entry misurate, più la scelta del picco
  sull'orizzonte (`soglia_rumore_orizzonte`). Le metro restano fuori perché la
  cella 22 passa solo le entry vere;
- **uscite** (passo 3): `t_stat` sui pips netti e soglia di Šidák sulle righe;
- **filtri** (passo 5): come prima. Le soglie di confidenza sono righe di una
  loro chiamata: contano solo fra loro.
Tarate su entry casuali: sezione E del notebook di collaudo, vedi `21`.
 
**Resta aperto:** le prove dei passi precedenti non si sommano (entry → uscite →
filtri → confidenza). Ogni soglia è un pavimento. Per le idee che arrivano da
articoli il conto cumulato lo tiene a mano il registro di `50` (§10).
 
### 4. Il catalogo è ispezionabile solo in parte — sovrapposizioni fatte nel ramo ML l'1/10
 
`verifica_degenerazione` risponde a *quante occorrenze, che copertura, che
direzione, quali sono degeneri, quanto sono a grappolo*.
 
**Sovrapposizioni (due entry che scattano quasi sulle stesse barre sono una
prova sola travestita da due, e pesano sul conteggio di `k`):** il 1/10 è nata
`diagnostica.sovrapposizioni(df, colonne, finestra=0, soglia=0)` nel ramo ML
(vedi `32`): una riga per coppia, con contenimento reciproco e correlazione. Ha
già portato a togliere i doppioni (filtri da 20 a 12, trigger da 26 a 18 per
lato). **Resta aperto:** verificare che la funzione sia anche nel repo V4 e
rifarla a ogni condizione aggiunta (`50`, §7).
 
### 5. Portabilità multi-asset — primi difetti trovati e corretti il 25/9
 
Il primo run completo su BTCUSD (25/9) ha trovato due difetti, corretti e coperti da
`test_portabilita.py`:
 
- **prezzo > capitale.** `backtesting.py` non compra frazioni: con `cash=10.000` e
  bitcoin sopra 10.000 $ gli ordini venivano scartati in silenzio (120 trade
  in-sample invece di 814, zero nella seconda metà e nell'OOS). Ora
  `avviso_capitale` lo dice in chiaro in `run_exit_search_bt` e
  `run_filter_search_bt`; nel notebook il capitale sta in `costi["cash"] = CASH`.
- **BTCUSD classificato forex senza MT5** (bastavano 6 lettere). Ora forex solo se
  sono due valute ufficiali; crypto per sigla; senza commissione il nozionale non
  viene più chiesto. Numeri di EURUSD invariati.
Modifiche NON additive, dichiarate: `costi.py` (`classifica_simbolo`, strada senza
MT5), una riga in `exit_search_bt.py` e una in `filter_search_bt.py`.
 
Resta: il tool ha visto solo EURUSD e BTCUSD. Prezzi di
ordini di grandezza diversi, strumenti senza weekend, orari diversi: mai
provati su asset sintetici costruiti apposta. `mercato_sintetico()` è un punto
di partenza (oggi genera solo forex con weekend, prezzo 1,10).
 
### 6. Un runner unico dei test
 
Sette suite da terminale più un notebook di collaudo, da lanciare a mano.
 
### 7. Etichetta UTC fantasma — origine ancora ignota
 
Da qualche parte un `tz_localize('UTC')` viene applicato a ore server.
`verifica_indice_utc()` lo intercetta, ma è una difesa, non una cura.
Probabile origine trovata il 24/9: la riga commentata
`#df.index = pd.to_datetime(df.index, utc=True)` nella cella 7 del notebook
principale. Oggi è commentata e non fa danni: va cancellata.
 
### 8. Metodologia non ancora costruita
 
- **Baseline oraria nell'event study** — automatizza il «t netto» oggi fatto a mano
- ~~**Incertezza dell'event study corretta per i grappoli**~~ — **fatto il 24/9**:
  i trigger vicini condividono candele e ora non contano più come prove
  indipendenti. Senza, i falsi allarmi erano al 14% (trigger frequenti) e al 93%
  (grappoli) invece del 5%. Vedi `21`
- ~~**Confidenza dei segnali**~~ — **fatto il 25/9**, `engine/confidenza.py`
- **Profilo stagionale** ora × giorno della settimana
- **Diagnostica delle pause sistematiche** per simbolo
- ~~**Yardstick e sizing**~~ — **fatto il 26/9**, `engine/montecarlo.py`
- **Festivi di borsa**: decisione rimandata, serve al filtro NYSE
---
 
## Problemi aperti nel codice esistente
 
| | cosa | dove |
|---|---|---|
| | cella 39: oggi `es.top().iloc[2][0]` (va su pandas 2.2, si rompe su 3.0). `es.top().iloc[2]["combinazione"]` va su entrambe | non bloccante |
| | 4 markdown descrivono ancora `guadagno_sharpe` come colonna decisiva — da ricontrollare, il notebook è cambiato | `91_NOTEBOOK_CELLE.md` §2 |
| | la cella 4 clona il repo con un token, ma il repo è pubblico: se il secret manca il notebook si ferma senza motivo | non bloccante |
| | la cella 7 contiene, commentata, `pd.to_datetime(df.index, utc=True)`: applicata a ore server è esattamente l'«etichetta UTC fantasma» (punto 7). Da cancellare | non bloccante |
| | `engine/vwap_ops.py` taglia la giornata a `df.index.date`, cioè a mezzanotte UTC, non al rollover delle 17:00 NY. La colonna `vwap` e i 5 filtri VWAP usano quindi una giornata diversa da `confidenza.py`, che usa `giorno_fx()`. Trovato il 25/9, non toccato | da decidere |
| | `ExitSearchBT.top()` ordina per `sharpe`, mentre la regola dice che decide `avg_trade_netto` | da decidere |
| | stop non attivo sulla barra d'ingresso (~0,2%, bias a favore del backtest) | rimandato per scelta |
| | copertura dati: il notebook principale oggi carica tutto il CSV, **6,7 anni** (gen 2020 – set 2026). I «3,7 anni» erano il taglio 2023–2026 usato fino al 22/9 (`01` §Copertura) | chiarito |
| | docstring di `ExitSearchBT` promette `.equity()` che non esiste | non bloccante |
 
---
 
## Tre scoperte da non perdere
 
**I trade filtrati non sono un sottoinsieme della baseline.** Scartando un
trade il filtro libera il posto e rende tradabili segnali prima bloccati da una
posizione aperta (`exclusive_orders=True`). Misurato: dal 3% al 12% di trade
nuovi per filtro. Rende illecito qualunque test appaiato. Da qui `tenuti vs
scartati`.
 
**Lo stop non è attivo sulla barra d'ingresso.** `trade.sl` viene assegnato a
trade già aperto, quindi diventa operativo dalla barra dopo. Impatto misurato
con `perc_sl=90`: ~0,2% dei trade. Il bias è sempre a favore del backtest.
 
**`avg_trade` è LORDO di commissioni.** `backtesting.py` addebita la
commissione alla cassa, non al prezzo di fill. Lo spread invece **è** dentro i
prezzi. Il numero da confrontare con zero è `avg_trade_netto`.
 
Attenzione alla conversione, è l'errore che raddoppia tutto: `backtesting.py`
addebita `commission` **su entrambi i lati**, quindi
`commission = costo_round_turn / 2`. Lo `spread` si applica una volta sola e ci
va intero.
 
**Il capitale deve superare il prezzo (25/9).** Sotto quella soglia `backtesting.py`
scarta gli ordini senza errore. Su BTCUSD con `cash=10.000` sparivano l'85% dei
trade. I pips per trade non dipendono dal capitale: si alza `cash` e basta.
 
**In più, dal 24/9:** un test di lookahead che tiene l'indice intatto non vede i
difetti legati alla *fine* dello storico — che nel live è sempre la barra
corrente. Per questo il collaudo del catalogo tronca invece di sporcare.
 
---
 
## Dove siamo (25/9/2026)
 
**Sul repo e collaudato** (notebook di collaudo in Colab: A1 23/23 · A2 16/16 ·
B 0 LOOKAHEAD · C letta · D 12/12 · E 6/6; suite da terminale 87/87):
 
- test di lookahead e di degenerazione su tutto il catalogo (`21`)
- `range_finestra` corretta due volte: lookahead a fine storico, finestre che
  finiscono a mercato chiuso (F21 il lunedì) (`20`, trappole 4–5)
- versioni di TA-Lib e backtesting.py bloccate, con la verifica dei tre
  comportamenti su cui si regge il tool (sezione D)
- soglia di rumore calcolata dal tool in event study, uscite e filtri, e
  incertezza dell'event study corretta per i trigger vicini (sezione E, `02`)
**Consegnato il 25/9, da caricare sul repo:** la confidenza dei segnali —
`engine/confidenza.py`, `engine/volatility_features_engineering.py` (file di
Mattia, invariato), `test_confidenza.py` (30/30 con pandas 3.0 e 2.2). Nel pomeriggio aggiunto
`congela_filtro`: la confidenza si costruisce e si prova SOPRA il filtro scelto
(`filtro_scelto`), non sul setup nudo. Celle corrette in `91` §1. Metodo in `01`,
passo 5.
 
**Consegnato il 25/9 sera, da caricare sul repo:** `engine/controlli.py` (nuovo),
`engine/costi.py`, `engine/exit_search_bt.py`, `engine/filter_search_bt.py`,
`test_portabilita.py` (13/13 con pandas 3.0 e 2.2), e 4 celle corrette (`91` §1).
Il notebook su BTCUSD con le celle corrette gira intero senza errori (pandas 2.2):
814 trade in-sample su tutti gli anni, entrambe le metà popolate, OOS con trade.
`filtro_scelto` e `CONF_SCELTA` vanno ridecisi sulle tabelle nuove.
 
**Verificato sul repo il 25/9 alle 21:21:** file dell'engine identici ai consegnati,
notebook eseguito dall'inizio su sessione nuova, nessun errore e nessun avviso di
capitale. Conteggi coerenti con il run di controllo di Claude (814 trade IS, F8 811,
storia 997, metà 419/395). Eseguita anche la Sessione 4: l'OOS di BTCUSD per il
setup E22 (+F8) è da considerare speso (vedi `01`, passo 6).
 
**26/9 mattina:** run su EURUSD. Trovato un difetto nel confronto delle soglie di
confidenza (scartati mescolati col riscaldamento), corretto con
`congela_confidenza_nota`; cella 10 torna allo spread di listino su EURUSD. Celle in
`91` §1. Verificato sul repo alle 10:20: notebook eseguito intero senza errori, conteggi
coerenti (baseline a confidenza nota 965 = 805 tenuti + 160 scartati; OOS 275 = 191 + 84).
L'OOS di EURUSD per il setup E7 inv. + E9 + RSI_EXTREME + F6 è da considerare speso.
 
**26/9 pomeriggio: passo 7 consegnato.** `engine/montecarlo.py` (nuovo),
`engine/giudizio.py` (drawdown da zero, modifica dichiarata), `test_montecarlo.py`
(17/17 con pandas 3.0 e 2.2), celle della Sessione 5 in `91` §1. Eseguite sul setup
EURUSD: girano intere.
 
**Dopo, in ordine:** collaudo multi-asset (punto 5), baseline oraria (punto 8),
runner unico (punto 6). Le condizioni doppione (punto 4) sono fatte nel ramo ML;
resta da portare o verificare su V4.
 
---
 
## Convenzioni di lavoro
 
- **Metodologia prima, codice dopo.** Le decisioni si risolvono a parole; poi si
  propone il progetto (funzioni, firme, cosa restituisce) e si aspetta il via
  libera.
- **Niente aggiunte non richieste.** Ciò che va oltre la richiesta si propone.
- **Ogni pezzo di codice passa un collaudo prima della consegna**, con casi a
  risultato noto — non «sembra ragionevole».
- **Verifica empirica prima della lettura del codice**: i comportamenti di
  `backtesting.py` si confermano con test discriminanti, non si deducono.
- **Consegna:** Claude modifica e testa i file e li consegna come download; le
  celle di notebook arrivano come testo da incollare. Mattia gestisce il
  notebook da sé e carica i file sul repo.
- **Collaudo con due versioni di pandas**: quella di Colab (2.x) e la 3.0.
- **Modifiche all'engine il più possibile additive**; quando non è possibile, la
  modifica va dichiarata.
- **Sempre spiegare come si esegue il codice.** Mattia non è un informatico.
 