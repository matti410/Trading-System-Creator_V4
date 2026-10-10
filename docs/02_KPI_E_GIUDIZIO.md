# 02 · Scheda KPI — come si legge un risultato
 
Una pagina, da tenere aperta accanto al notebook.
Aggiornata 24/9/2026 (soglie di rumore in tutti i passi, incertezza dell'event study).
 
---
 
## Come si legge un verdetto
 
```
fs.top(20)          la griglia filtri, ordinata per t_guadagno
fs.scheda()         la scheda completa della baseline
fs.scheda("NOME")   la scheda di una riga filtrata
```
 
**Tre esiti.** Bocciare è oggettivo, approvare no.
 
| esito | significa |
|---|---|
| `SCARTATA` | un criterio oggettivo è fallito — la colonna `motivo` dice quale |
| `CAMPIONE CORTO` | nessun criterio fallito, ma meno di 100 trade |
| `DA VALUTARE` | tutti i criteri superati — **ora la decisione è tua** |
 
`DA VALUTARE` non vuol dire buona. Vuol dire che i cancelli automatici sono passati
e resta da decidere se il drawdown è tollerabile e se la logica economica sta in piedi.
 
---
 
## I cancelli automatici
 
| criterio | soglia | parametro |
|---|---|---|
| EV netto per trade | > 0 | `ev_min` |
| il filtro aggiunge | `guadagno_pips` > 0 | — |
| oltre il rumore | `\|t_guadagno\|` > `soglia_rumore(k)` | `alpha=0.05` |
| P(EV<0) | < 5 % | `p_max` |
| campione | ≥ 100 trade | `min_trades_giudizio` |
 
Sono tutte parametriche: se cambi idea su una soglia la passi a
`run_filter_search_bt`, non riscrivi il modulo.
 
**La soglia di rumore è un pavimento.** Conta solo le prove di *quella*
chiamata. Le entry provate nella Sessione 1 e ogni rilancio della griglia si
sommano a quel conto, ma il tool non li somma.
 
---
 
## La soglia di rumore, passo per passo (dal 24/9)
 
Ogni tabella che sceglie «il migliore fra tanti» stampa la propria soglia e ha la
colonna `oltre_rumore`. `k` lo conta il tool, sulle righe di quella chiamata.
 
| passo | numero confrontato | soglia | esempi |
|---|---|---|---|
| 1–2 event study | `\|volte_incertezza\|` | `soglia_rumore_orizzonte(k, H)`: k entry **e** la scelta del picco fra H barre | 52 entry, H=25 → **3,92** |
| 3 uscite | `\|t_stat\|` (pips netti) | `soglia_rumore(k)`, Šidák | 4 righe → 2,49 |
| 5 filtri | `\|t_guadagno\|` | `soglia_rumore(k)`, Šidák | 17 → 2,97 · 25 → 3,08 |
 
**Perché all'event study la soglia è più alta.** Per ogni entry si prende la barra
migliore delle H: è già un «migliore fra tanti». Le barre sono correlate, quindi 25
barre valgono ~7 prove e 48 ~10, non 25 o 48. La vecchia regola «sotto 2 il picco
non si distingue dal rumore» vale per UNA entry a UNA barra fissa decisa prima.
 
**Le metro** (`M_*`) restano fuori dal conto perché la cella dell'event study
passa solo le entry vere. **Una coppia di filtri** con `pair` vale una riga sola:
già così nella ricerca dei filtri.
 
Tarate su entry casuali (circa 5 falsi allarmi su 100): sezione E del notebook di
collaudo, `21_COLLAUDO_CATALOGO.md`.
 
---
 
## I KPI della scheda
 
### Scoperta — c'è un vantaggio?
 
| KPI | come si legge |
|---|---|
| `EV netto per trade` | in pips, al netto delle commissioni. **Il numero da confrontare con zero.** |
| *cuscinetto sui costi* | è lo stesso numero: quanto attrito in più regge prima di azzerarsi. EV di 0,25 pips su un costo round-turn di 0,80 = sopravvive a un terzo di giro di costi in più |
| `EV in R multipli` | pips diviso la distanza dallo stop *di quel trade*. Con stop adattivo è più onesto dei pips |
| `t-stat` | l'EV si distingue da zero? Strumento di classifica, non p-value esatto |
| `P(EV<0)` | bootstrap, non assume normalità. **< 5 % ok · < 1 % molto buono · > 5 % in-sample è un campanello** |
| `IC 95 % dell'EV` | se contiene lo zero, il vantaggio non è dimostrato |
 
### Rischio — quanto può andare male?
 
| KPI | come si legge |
|---|---|
| `max DD a trade chiusi` | in pips. È quello che serve al sizing |
| `Monte Carlo shuffle` | stessi trade, ordine rimescolato. Il 99° percentile è il peggio che una sequenza sfortunata produce |
| `win rate` vs `pareggio` | il pareggio è `1/(1+avg_win/avg_loss)`, un'identità calcolata dai tuoi trade. Un margine di 0,9 punti vuol dire che il vantaggio non ha cuscino |
| `reward:risk`, `profit factor` | diagnosi, non cancelli |
| scomposizione `long` / `short` | se una gamba ha EV negativo, va rivista o rimossa |
 
**Il drawdown non è un cancello automatico:** è tolleranza al rischio, e la decidi tu.
 
---
 
## L'incertezza dell'event study e i trigger vicini (dal 24/9)
 
`incertezza_pct` è quanto balla la media della curva. Due trigger a poche barre
di distanza vivono le stesse candele: non sono due prove. Fino al 24/9 contavano
come indipendenti e l'incertezza delle entry frequenti era **sottostimata**: su
entry casuali, falsi allarmi al 14% (un trigger ogni ~25 barre) e al 93% (grappoli)
invece del 5%. Ora la covarianza fra due trade è proporzionale alle candele
condivise.
 
Effetto su EURUSD In-Sample, H=25: incertezza fino a +56% per le entry con migliaia
di trigger; identica per quelle rare. **Tabelle dell'event study salvate prima del
24/9 sera non sono confrontabili** su `incertezza_pct` e `volte_incertezza`.
 
---
 
## Il «t netto» — quando l'asset ha deriva
 
Sull'event study, `volte_incertezza` è calcolato sulla **curva grezza**. Su un asset
con deriva forte quella curva sale da sola, e il `t` misura la deriva invece del
segnale.
 
Il correttivo è `vs_mercato_pct / incertezza_pct`: lo scostamento dalla linea del
mercato invece dell'altezza. È lecito perché la linea del mercato è calcolata su
tutte le barre, quindi la sua incertezza è trascurabile nel confronto.
 
Misurato su due asset opposti: su EURUSD la correzione cambia poco, su BTCUSD
**dimezza** i valori. Dettagli e tabelle in `11_DATI_QUARANTENA.md`.
 
Oggi va fatto a mano. La versione automatica è la **baseline oraria**, non ancora
costruita.
 
---
 
## Il conto anno per anno
 
Un `t` aggregato sopra soglia non dice se il segno tiene nel tempo. Una riga con
`t` netto −3,16 può fare tre anni positivi e quattro negativi: il valore aggregato
nasce da due o tre annate.
 
È lo stesso cambio di segno che `due_meta` intercetta, ma si vede con sette righe e
prima di arrivare al passo 5. **Vale la pena farlo di routine su qualunque
candidato.** Non è automatizzato.
 
---
 
## Perché non più `guadagno_sharpe`
 
Lo Sharpe di `backtesting.py` è calcolato sull'**equity giornaliera**, non sui trade.
Dipende da quanto stai a mercato e da quanti trade fai, non solo dalla qualità del
vantaggio. Un filtro che taglia i trade da 995 a 500 muove numeratore e denominatore
per ragioni estranee al segnale.
 
Misurato: su una serie sintetica, *aggiungere* la commissione fa **salire** lo Sharpe
da 24,49 a 27,16.
 
Resta in `.risultati` come riferimento. Non decide più.
 
---
 
## Perché il confronto è `tenuti vs scartati`
 
I trade del sistema filtrato **non sono un sottoinsieme** della baseline: scartando un
trade il filtro libera il posto e rende tradabili segnali prima bloccati da una
posizione aperta. Misurato su EURUSD M15: dal 3 % al 12 % di trade nuovi per filtro
(colonna `trade_nuovi`).
 
Quindi niente test appaiato, e niente confronto diretto filtrato-vs-baseline (si
sovrappongono all'88-97 %). Si partiziona la **sola baseline** in trade tenuti e
trade scartati — disgiunti per costruzione — e si confrontano con Welch, solo sul lato
su cui il filtro agisce.
 
Due domande distinte, due colonne:
 
- `t_stat` → il sistema filtrato realizzato guadagna?
- `t_guadagno` → il filtro seleziona i trade migliori? **È questa che decide.**
---
 
## `due_meta` — la verifica sulle due metà
 
Due condizioni, su due campioni diversi e per due ragioni diverse:
 
1. **Stabilità** — `guadagno_pips` positivo in **entrambe** le metà. È la domanda
   propria di `due_meta`: il vantaggio c'è da tutte e due le parti del periodo, o è
   concentrato in una sola?
2. **Significatività** — `t_guadagno` sopra soglia sull'**intero** In-Sample.
La significatività si giudica sull'intero perché con ~250 trade per metà il rumore
produce da solo oscillazioni enormi: misurato, `VWAP_SESSION_CLOSE` va da +0,68 a
+3,91 pips fra le metà, con t di 0,39 e 2,16 — due numeri che non dicono niente.
Le metà servono a scoprire un **cambio di segno**, non a misurare con precisione.
 
Per la stessa ragione non c'è una soglia sul rapporto fra le metà: un calo non è di
per sé una condanna.
 
| verdetto | quando |
|---|---|
| `regge` | guadagno positivo in entrambe le metà **e** t sopra soglia sull'intero |
| `giudizio sospeso` | come sopra, ma poche osservazioni in una metà |
| `non regge` | tutto il resto — `motivo` dice quale condizione è caduta |
 
---
 
## Unità: punti, pip e bp
 
| Unità | EURUSD | BTCUSD |
|---|---|---|
| **punto** | 0,00001 (quinta cifra) | 0,01 |
| **pip** (`deduci_pip`) | 0,0001 | 1 USD |
 
**Un pip sono 10 punti.** La colonna `spread` del CSV è in **punti**. Su EURUSD a
prezzo 1,1173: 1 pip = 0,895 bp. Un `picco_pips` di 70 su BTCUSD sono 70 dollari, non
70 pips valutari — **è il primo controllo da fare portando il tool su un asset nuovo.**
 
---
 
## Cosa manca ancora ai criteri
 
- **Yardstick dopo 10/20/40/100 trade** (Passo 7): le soglie oltre cui si spegne il
  sistema in live
- **Sizing** dalla distribuzione del drawdown (Passo 7)
- ~~Conteggio automatico di `k`~~ — fatto il 24/9 per ogni chiamata; le prove di
  passi diversi ancora non si sommano
- **Baseline oraria** che automatizzi il «t netto»