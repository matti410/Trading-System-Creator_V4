# 21 · Collaudo del tool — lookahead, degenerazione, backtesting.py
 
**Data:** 24 settembre 2026 (sezione D e versioni bloccate aggiunte nel pomeriggio)
**Prima di questo:** `00_SCOPO_E_STATO.md`, `20_CONDIZIONI_TEMPO.md`
 
**File:** `engine/collaudo_catalogo.py` (nuovo), `engine/indicatori.py` (nuovo),
`Collaudo_Catalogo.ipynb` (nuovo, gira in Colab), `engine/livelli.py`
(corretto, vedi sotto)
 
Chiude i punti 1 e 2 di «cosa manca al tool».
 
---
 
## Cosa fa
 
Due controlli automatici su **tutte le condizioni registrate** nel registry
(entry, exit, filtri, bidirezionali), senza conoscerne il contenuto:
 
| funzione | domanda | esiti |
|---|---|---|
| `verifica_lookahead(df_grezzo, prepara=aggiungi_indicatori)` | la condizione guarda il futuro? | `OK` · `LOOKAHEAD` · `NON_ESERCITATA` · `ERRORE` |
| `verifica_degenerazione(df, min_occorrenze=30, copertura_max=0.95, distanza_grappolo=8)` | la condizione distingue qualcosa? | `OK` · `SEMPRE_FALSA` · `SEMPRE_VERA` · `QUASI_SEMPRE_VERA` · `RARA` · `STATO` · `NON_BOOLEANA` · `ERRORE` · `ATTESA` |
 
Più `condizioni_registrate()`, `tagli_standard()` e `mercato_sintetico()`.
 
**Una condizione nuova in un file esistente è coperta da sola.** Un *file* di
condizioni nuovo va aggiunto con una riga alla lista `REGISTRAZIONI`, nella
sezione «1 · Il catalogo» del notebook di collaudo.
 
**Un indicatore nuovo va aggiunto in `engine/indicatori.py`**, non nel notebook
principale: altrimenti il collaudo non lo ricalcola e non lo vede.
 
---
 
## Il notebook `Collaudo_Catalogo.ipynb`
 
In Colab, *Runtime → Esegui tutto*. 2–3 minuti.
 
| sezione | cosa | esito atteso |
|---|---|---|
| A1 | trappole di lookahead costruite apposta | 23/23 — se no il notebook si ferma |
| A2 | casi di degenerazione a risultato noto | 16/16 — se no il notebook si ferma |
| B | lookahead su tutto il catalogo, dati sintetici | promosso solo con 0 `LOOKAHEAD` e 0 `ERRORE` |
| C | degenerazione su EURUSD vero | tabella da leggere, nessun promosso/bocciato |
| D | i tre comportamenti di `backtesting.py` | 12/12 — se no il notebook si ferma |
| E | le soglie di rumore, su entry casuali | 6/6 — se no il notebook si ferma |
 
**Stato al 24/9, dopo la correzione di `range_finestra`:** A1 23/23, A2 16/16,
B 0 LOOKAHEAD · 0 ERRORE · 2 NON_ESERCITATE (le exit `X0_…_NO_EXIT`) · 117 OK.
C su 167.123 barre (6,7 anni): 105 OK, 2 ATTESA, 1 RARA
(`E19_SHORT_THREE_BLACK_CROWS`, 8 eventi). Identico con pandas 3.0 e 2.2;
confermato da Mattia in Colab. D 12/12 ed E 6/6, confermati da Mattia in Colab
il 24/9 sera (E: 2,3% · 1,7% · 6,0% · 4,7%, identici al collaudo qui).
 
---
 
## Decisioni prese, e perché
 
### 1. Troncamento, non spazzatura
 
Il test taglia lo storico alla barra *t*, lo ricalcola **da zero** (indicatori
compresi) e confronta **tutte** le barre fino a *t* con lo storico intero. Se una
sola cambia, dipendeva dal futuro.
 
La vecchia verifica (futuro sostituito con spazzatura, indice intatto) ha due
punti ciechi, entrambi dimostrati:
 
- **le cache sull'indice.** `quarantena_cached` usa come chiave (lunghezza,
  prima, ultima barra): con l'indice intatto restituisce la quarantena calcolata
  sui dati puliti e nasconde un lookahead. Trappola `T_CACHE`;
- **i timestamp futuri.** Con l'indice intatto la finestra successiva «si
  chiude» comunque. È esattamente il motivo per cui `test_tempo_prezzo.py` non
  ha visto il difetto di `range_finestra`.
### 2. Gli indicatori si ricalcolano, quindi stanno in un modulo
 
La cella degli indicatori del notebook principale (oggi la 16) è diventata
`engine/indicatori.py` (`aggiungi_indicatori`). Verificato: risultato identico
alla cella, bit per bit, su EURUSD. Una condizione che legge una colonna già
calcolata non può rivelare un lookahead dentro l'indicatore: trappola
`T_USA_INDICATORE`. Gli 11 indicatori sono verificati anche da soli, come righe
`indicatore` del report.
 
### 3. Tagli comuni più tagli mirati
 
- **Comuni:** uno per ogni quarto d'ora del giorno (96) più 8 sui bordi del
  weekend. Prendono il lookahead legato all'orario.
- **Mirati:** fino a 5 per condizione, su barre in cui la condizione è **vera**.
  Un `shift(-1)` cambia solo la barra del taglio: su un'entry rara un taglio a
  caso cade quasi sempre su una barra falsa e non vede niente. Trappola
  `T_SHIFT_RARO`. I tagli già in piano si riusano per risparmiare tempo.
### 4. Il limite dichiarato: `NON_ESERCITATA`
 
Una condizione mai vera sui dati del test non è verificabile (falsa prima e dopo
il taglio non dimostra niente). Il report non la dà per `OK`.
 
### 5. Dati sintetici per il lookahead, veri per la degenerazione
 
Il lookahead è una proprietà del codice: si verifica su un random walk di
quattro mesi (ago–dic 2024, ~8.300 barre) con i cambi d'ora d'autunno e la
settimana di sfasamento Europa/USA. `Open` diverso dalla chiusura precedente,
altrimenti alcuni pattern TA-Lib non scattano mai.
 
La degenerazione dipende dal dataset (un pattern raro su EURUSD può non esserlo
altrove): si legge sui dati veri e non ha promosso/bocciato.
 
### 6. Definizioni della degenerazione
 
- **copertura** = quota di barre vere; **eventi** = quante volte la condizione
  *diventa* vera (blocchi separati).
- `RARA`: per le **entry** si contano gli eventi, per **filtri ed exit** le barre
  vere. Un filtro di regime con 20 blocchi lunghi lascia entrare su migliaia di
  barre: contarlo come «20 occorrenze» sarebbe un falso allarme.
- `min_occorrenze=30` = il `min_trades` dei passi 3 e 5.
- `QUASI_SEMPRE_VERA` da `copertura_max=0.95`. Per le entry non scatta mai:
  con `_evento` non possono superare il 50%.
- `STATO`: un'entry vera su barre consecutive, cioè senza `_evento`. Errore di
  scrittura.
- `ATTESA`: `X0_NO_EXIT` e `X0_SHORT_NO_EXIT`, sempre false per costruzione.
### 7. Grappoli: misurati, non vietati
 
Trigger vicini ma separati da barre false (es. 4 trigger su 8 candele) sono
legittimi. Colonne informative, solo per le entry: `grappoli` e
`quota_in_grappolo`, con `distanza_grappolo=8` modificabile nella firma.
 
Perché contano: nei backtest dei passi 3 e 5 non pesano (i trade non sovrapposti
ignorano i trigger successivi). **Nell'event study sì:** misura ogni occorrenza
come indipendente, quindi quattro trigger in due ore stringono la fascia di
incertezza più di quanto dovrebbero. **Corretto il 24/9 sera**: vedi la sezione
E qui sotto.
 
---
 
## Sezione D e versioni bloccate
 
Il tool si regge su tre comportamenti di `backtesting.py`, verificati a mano in
passato. Se una versione nuova ne cambia uno, i numeri cambiano **senza nessun
errore**. Per questo:
 
- **versioni bloccate**: `TA-Lib==0.8.1` e `backtesting==0.6.6`, nella cella 2
  del notebook principale e nella preparazione del notebook di collaudo. Si
  cambiano solo insieme, e dopo si rilancia il collaudo;
- **sezione D**: una serie di 10 barre a prezzi noti, un trade solo, **usando la
  strategia vera dell'engine** (`_StrategiaGenerica`):
| prova | cosa verifica |
|---|---|
| D1 · commissione | fuori dal prezzo di fill, addebitata su entrambi i lati: c × (entrata + uscita). `avg_trade_netto` di `engine/metriche.py` torna al conto a mano. Long e short |
| D2 · spread | una volta sola, dentro il prezzo d'ingresso (long Open×(1+s), short Open×(1−s)); uscita al prezzo pieno. Long e short |
| D3 · stop | assegnato come fa l'engine, non attivo sulla barra d'ingresso (minimo che lo buca: il trade resta aperto); attivo dalla barra dopo |
 
D3 è discriminante: la controprova con lo stop passato nell'ordine
(`buy(sl=...)`), che invece è attivo dalla barra d'ingresso, esce sulla barra
d'ingresso e farebbe fallire la prova.
 
Le prove verificano anche i tempi dell'engine: ingresso all'Open della barra
dopo il segnale, uscita a tempo all'Open della barra `n_barre` dopo l'ingresso.
 
---
 
## Sezione E — soglie di rumore e incertezza dell'event study (24/9 sera)
 
**Cosa c'è di nuovo nel tool.** Nei passi che scelgono «il migliore fra tanti»
la tabella dice da sé oltre quale valore il risultato non è spiegabile col caso:
 
| passo | colonna | soglia | k |
|---|---|---|---|
| event study | `volte_incertezza` → `oltre_rumore` | `soglia_rumore_orizzonte(k, H)` | entry misurate nella chiamata |
| uscite | `t_stat` (pips netti) → `oltre_rumore` | `soglia_rumore(k)` (Šidák) | righe della chiamata |
| filtri | `t_guadagno` → `oltre_rumore` | `soglia_rumore(k)` | righe della chiamata (invariato) |
 
**Il picco sull'orizzonte è una scelta in più.** L'event study sceglie per ogni
entry la barra migliore delle H. Le barre sono correlate: su rumore puro 25 barre
valgono ~7 prove, 48 ~10. Per questo la soglia si ottiene per simulazione
(1.000.000 di passeggiate casuali, seme fisso, ±0,02). Esempi: k=52, H=25 → 3,92
(contro 3,29 contando solo le entry); con H=1 coincide con `soglia_rumore`.
 
**Il difetto trovato collaudando la soglia.** L'incertezza dell'event study
contava ogni trigger come prova indipendente. Due trigger vicini però vivono le
stesse candele. Falsi allarmi misurati su entry casuali, con la formula vecchia:
 
| trigger | falsi allarmi (atteso ~5%) |
|---|---|
| distanti (> H barre) | 2–3% |
| uno ogni ~25 barre | **14%** |
| a grappoli (4 in 8 candele) | **93%** |
 
**Correzione** (`_errore_standard_sovrapposti` in `engine/event_study.py`): la
covarianza fra due trade è proporzionale alle candele condivise,
w = max(0, 1 − distanza/k). Senza sovrapposizioni coincide con la formula
classica (prova E2). Con la correzione: 2%, 2%, 6%.
 
Effetto su EURUSD In-Sample, H=25: l'incertezza delle entry frequenti cresce fino
al +56% (`E12_SHORT_ENGULFING`, ~13.700 trigger); le entry rare restano identiche.
Cambiano `incertezza_pct`, `volte_incertezza` e la fascia scura di
`plot_singola`.
 
**Le prove della sezione E:**
 
| prova | cosa | esito il 24/9 |
|---|---|---|
| E1 | con orizzonte 1 la soglia nuova = `soglia_rumore(k)` | ✓ |
| E2 | trigger distanti → incertezza = formula classica | ✓ |
| E3 | falsi allarmi, trigger distanti (300 giri × 20 entry) | 2,3% |
| E4 | falsi allarmi, trigger frequenti | 1,7% |
| E5 | falsi allarmi, grappoli | 6,0% |
| E6 | `t` delle uscite su rumore: \|t\| > 1,96 | 4,7% di 750 righe |
 
Accettati fra 1% e 10% (E3–E5) e fra 2,5% e 8% (E6). **E4 ed E5 sono
discriminanti:** con la formula vecchia escono al 13,7% e 92,7% e la sezione
fallisce.
 
**Limite:** ogni soglia conta le prove di una chiamata. Le prove dei passi
precedenti non si sommano: è un pavimento.
 
---
 
## Il difetto trovato: `range_finestra` con fine dichiarata
 
**Il primo giro del collaudo ha trovato un lookahead vero** in
`engine/livelli.py`, corretto il 24/9 (una riga, commentata nel codice).
 
**Il meccanismo.** Quando lo storico finiva dentro una finestra ancora aperta
(es. alle 06:30 UTC, Tokyo aperta e Londra no), la finestra senza chiusura
veniva scartata ma **le sue barre no**: finivano nella finestra precedente, già
chiusa. Il range di ieri conteneva i prezzi di oggi.
 
Esempio verificato: col taglio al 7/8 06:30, il minimo e l'ultima chiusura del
range asiatico del 6/8 diventavano quelli del 7/8.
 
- **Colpiti:** le finestre con fine dichiarata (`TOKYO→LONDRA`,
  `NEW_YORK→ROLLOVER`), quindi E22 long/short e F21 up/down. Puliti: E23
  (`ROLLOVER` da solo) e tutto il resto.
- **Backtest:** sullo storico intero toccava solo l'ultima giornata.
  Sull'EURUSD del repo, che finisce venerdì sera, nessuna barra cambia.
- **Live:** lo storico finisce sempre sulla barra corrente, quindi era la
  situazione normale.
**Collaudo della correzione:** sezione B 0 LOOKAHEAD; le 4 suite esistenti
86/86; le 108 condizioni sull'EURUSD vero, prima e dopo, identiche barra per
barra.
 
**Lezione generale:** un test di lookahead che tiene l'indice intatto non vede i
difetti legati alla *fine* dello storico, che sono proprio quelli del live.
 
Nel pomeriggio dello stesso giorno `range_finestra` è stata corretta di nuovo
per F21 il lunedì (finestra chiusa anche dalla pausa di mercato): vedi
`20_CONDIZIONI_TEMPO.md`, trappola 5. La nuova regola assorbe questa.
 
---
 
## Tempi e limiti noti
 
- Sezione B: ~2 minuti (107–109 tagli per condizione, 232 tagli distinti).
- I dati sintetici coprono solo i cambi d'ora **d'autunno**. Quelli di
  primavera (3 settimane di sfasamento USA/Europa) non sono nel test.
- Il test garantisce la causalità rispetto alla barra *t*. Che l'ingresso
  avvenga a `Open[t+1]` è una proprietà dell'engine (`event_study`, `lag=1`),
  non di questo test.