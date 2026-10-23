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
 
**Dal 18/10 c'è la versione automatica: la baseline oraria** (sezione sotto).

## La baseline oraria e il profilo orario (dal 18/10)

Il mercato non si muove allo stesso modo a tutte le ore. `engine/stagionalita.py`
divide la giornata in **fasce orarie** larghe quanto una barra: M5 288 fasce, M15
96, M30 48, H1 24, H4 6. Le fasce seguono l'ora locale della piazza, fissata a
priori per symbol (`FUSO_PIAZZA`): New York per forex, oro, cripto, US500 e USTEC
(per il forex è l'ora del giorno FX, che cambia alle 17:00 di New York),
Francoforte per DE40. Restano agganciate all'ora locale anche ai cambi di ora
legale. Il giorno della settimana non entra: con 5 giorni le celle sarebbero
troppo piccole (decisione di Mattia del 18/10/2026).

- **Profilo orario** (`profilo_orario`): per ogni fascia il rendimento medio a H
  barre, lo scarto dalla media di tutte le barre, la sua incertezza (barre vicine
  comprese) e il controllo della quota di falsi positivi sulle fasce (BH 20%, p a
  due code). È una mappa: una finestra scelta guardando il profilo conta come
  tante prove quante sono le fasce. Una finestra presa da un paper conta come una.
- **Baseline oraria:** nella rosa il mercato di riferimento di un trigger è la
  media **della sua fascia**. Lo scarto è la media di `d·(r_i − b_fascia(i))`.
  L'incertezza è quella di una somma pesata su tutte le barre: +1/n sui trigger,
  −(trigger della fascia)/(n · barre della fascia) su ogni barra, con le
  sovrapposizioni delle finestre a H barre. Così include il rumore della media di
  fascia. Per i sistemi, a ogni trade si toglie la somma delle derive per barra
  tipiche delle fasce in cui è rimasto aperto. Il confronto con tutte le ore resta
  visibile (`scarto_globale_pips`, `t_globale`); `baseline="globale"` ridà i
  numeri di prima.
- **Event study:** con `fuso=` la sintesi ha in più `vs_mercato_orario_pct`. La
  classifica non cambia.

**Collaudo** (`test_stagionalita.py`): su un mercato finto con +3 pips ogni giorno
fra le 15:00 e le 16:00 di Londra, un trigger alle 14:00 senza vantaggio proprio
ha t 21,9 con la baseline globale e −1,0 con quella oraria. Una entry con +1,5
pips veri a ore casuali dà lo stesso scarto con le due baseline. Su 60 entry finte,
2 allarmi con |t| > 1,96 (attesi 3).

**Prima misura** (EURUSD in-sample, H = 25, 18/10/2026): 90 fasce misurabili (quelle
del rollover sono in quarantena), scarto da −1,7 a +1,7 pips, 3 fasce oltre la
quota di falsi positivi. Nella rosa lo scarto delle entry cambia in mediana di
0,16 pips, al massimo di 0,85. È un collaudo, non un verdetto.

### Dal 19/10: l'ora è quella in cui si apre il trade, e le condizioni orarie

**Una regola sola per gli orari** (decisione di Mattia del 19/10/2026): ogni ora
scritta è **l'ora in cui il trade si apre** (o si chiude). Il segnale scatta sulla
candela prima e il motore apre o chiude all'Open della successiva. La fascia
«12:30» del profilo vuol quindi dire «se apri il trade alle 12:30»; prima era
etichettata con la candela del segnale, una candela prima.

**Griglia vera delle candele:** le fasce si agganciano all'ora d'inizio reale
delle candele (`griglia_oraria`). Sulle H4 del broker, che partono dalle 17:00 di
New York (17, 21, 1, 5, 9, 13), prima le etichette sarebbero state sbagliate di
un'ora.

**Le condizioni orarie** (`condizioni_orarie.py`):

| condizione | cosa fa |
|---|---|
| `ORA_LONG_@HH:MM` · `ORA_SHORT_@HH:MM` | apre un long / uno short ogni giorno alle HH:MM |
| `X_ORA_@HH:MM` | chiude il trade, long o short, alle HH:MM |
| `X_ORA_@HH:MM_UTC` | lo stesso, all'ora UTC fissa qualunque sia la piazza (dal 19/10, per gli orari dei paper scritti in UTC: E38, E39) |
| `X_INVERSIONE_TREND` | chiude il long all'**arrivo** di un'ora colorata contro (scarto negativo oltre la quota dei colpi di fortuna), lo short all'arrivo di un'ora colorata a favore del long; solo le ore colorate |

`X_INVERSIONE_TREND` usa il profilo calcolato **sull'in-sample e congelato**:
sull'out-of-sample non si ricalcola. Su ogni timeframe l'ora deve essere l'inizio
di una candela, altrimenti la condizione si ferma con gli orari possibili.

**Prove:** ogni ora provata è una prova (registro di `50`). Un'ora presa da un paper
conta come una. Un'ora presa da un gruppo colorato del profilo ha già pagato il
conto delle fasce, ma se ne prende una per gruppo di fasce vicine.
`X_INVERSIONE_TREND` conta una prova per ogni sistema su cui la provi.

**Collaudo** (`test_condizioni_orarie.py`, 33 test). Sul mercato finto con +3 pips
fra le 15:00 e le 16:00 di Londra, `ORA_LONG_@15:00` con `X_ORA_@16:00` apre alle
15:00, chiude alle 16:00 e guadagna +3,11 pips a trade; lo short alla stessa ora
perde −3,11. Le 09:30 di New York restano le 09:30 tutto l'anno, anche col cambio
dell'ora legale. H1 rifiuta le 12:30, H4 accetta le 17:00. Nessun lookahead né
degenerazione sul mercato finto; nessun lookahead sui 9 symbol veri (ultime
20.000 barre).
 
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
 
## La rosa dei candidati — due cancelli per due compiti (dal 18/10)

Le soglie di rumore qui sopra servono a **validare**: controllano la probabilità
che fra tutte le prove anche **una sola** sia un colpo di fortuna (Šidák). È giusto
che siano severe, ma per **proporre** candidati lasciano passare troppo poco.
La rosa (`engine/rosa.py`) è un secondo cancello, più largo, con un compito
diverso: suggerire un gruppo da cui scegliere. Non promuove niente; filtri,
`due_meta` e out-of-sample restano quelli di sempre.

| | validazione | rosa |
|---|---|---|
| domanda | c'è almeno un colpo di fortuna fra i promossi? | quanti colpi di fortuna ci sono, in media, nel gruppo? |
| metodo | `soglia_rumore`, `soglia_rumore_orizzonte` (Šidák, 5%) | Benjamini–Hochberg, q = 20%, sul p a una coda del t netto |
| in più | — | scarto positivo su entrambe le metà dell'in-sample |
| uso | decide chi va avanti | suggerisce, sceglie Mattia |

**Come si costruisce** (decisioni di Mattia del 17/10/2026):

1. **t netto** — lo scarto dal mercato diviso la sua incertezza. Per le entry a
   orizzonte H, con l'incertezza dell'event study (trigger vicini); per i sistemi
   sui pips netti dei trade veri, togliendo a ogni trade la deriva del mercato
   nelle barre in cui è rimasto aperto (vedi «Il t netto»). Dal 18/10 il
   mercato è quello **della stessa ora** (vedi «La baseline oraria»);
2. **Benjamini–Hochberg** al 20%: ordinati i p dal più piccolo, passano i primi r,
   con r il rango più alto per cui p ≤ 0,20 · r / k;
3. **due metà**: scarto positivo in entrambe;
4. **il gruppo**: dal t più alto in giù entra chi è di una **famiglia** nuova
   (`engine/famiglie.py`, soglia 60%) e ha **|ρ| ≤ 0,3** con i già presi, sui
   profitti per giornata FX. Per le entry i profitti della sola entry a H barre
   (accordo 0,99 con i trade interi su EURUSD e BTCUSD, 60 volte più veloce), per
   i sistemi quelli dei trade veri. Un sistema ha per famiglia la terna `L·S·X`
   (famiglia dell'entry long, dell'entry short, della regola d'uscita).

H è quello già scelto (passo 1); si passa solo l'in-sample.

**Prova di potenza** (17/10/2026, EURUSD in-sample, H = 25; un trade oscilla di
27 pips di deviazione standard). 80 entry finte su barre a caso, a 5 delle quali
si aggiunge un vantaggio noto; 60 giri.

| eventi per entry | vantaggio vero a trade | validazione: vere trovate | rosa: vere trovate | rosa: finte per giro (su 75) |
|---|---|---|---|---|
| 300 | 3 pips | 6% | 34% | 0,6 |
| 1.000 | 1 pip | 1% | 3% | 0,2 |
| 1.000 | 2 pips | 8% | 45% | 0,7 |
| 1.000 | 3 pips | 46% | **89%** | 0,8 |
| 3.000 | 1 pip | 3% | 19% | 0,1 |
| 3.000 | 2 pips | 53% | **91%** | 0,4 |
| 3.000 | 3 pips | 100% | 100% | 0,4 |

La validazione lascia passare 0–0,05 finte per giro: è tarata bene, ma severa. La
rosa vede circa il doppio dei vantaggi veri con meno di una finta per giro. Un
vantaggio di 1 pip lordo non lo vede nessuno dei due: è troppo piccolo rispetto
alla dispersione dei trade.

**Dove si usa:** notebook di ricerca, 1.3 (entry, dopo l'event study) e «La rosa
dei sistemi» (dopo la ricerca delle uscite, prima dei filtri); Lab, 3a bis e 4b
(`rosa_dei_trigger`, `rosa_dei_sistemi`). Collaudo: `test_rosa.py` e, per la
baseline oraria, `test_stagionalita.py`.

**Una rosa vuota non è un giudizio.** Vuol dire che a quell'orizzonte nessun
candidato si distingue abbastanza dal caso; la scelta resta libera.

---

## L'atlante del trigger (dal 22/10)

La rosa misura un trigger su tutto l'in-sample. L'atlante (`engine/atlante.py`,
`63` §6, `66`) guarda **dove** funziona: per ogni entry vera e ogni **cella**
del mercato. Le celle, per lato, con assi non incrociati fra loro:

| asse | celle | stato |
|---|---|---|
| volatilità × trend | 4: volatilità alta/bassa × trend a favore/contro | la griglia di `confidenza.py`, con finestre in ore (5 e 125, almeno 20 rendimenti; su M15 = 20 e 500 barre) |
| sessione | 4: ASIA_NOTTE (e fine settimana), EUROPA, LONDRA_NY, AMERICA | la barra d'ingresso (i+1), ora locale di Londra e New York con l'ora legale |
| basis (solo perpetual con lo spot) | 2: alta/bassa | basis perpetual − spot sulla sua mediana di 125 ore |

Ogni stato della barra del segnale usa solo dati fino al suo Close.

**Due domande, due colonne.** Lo **scarto lordo** dal mercato della stessa
cella e della stessa fascia oraria (`scarto_<unità>`, `t`: «aggiunge qualcosa
al mercato della cella?») e il **netto** dopo commissione, spread e funding
(`netto_<unità>`: «paga i costi?»). Una cella **passa** con almeno 200 eventi,
t > 0, il controllo della quota di falsi positivi su **tutte** le celle
misurate (q = 20%), scarto positivo nelle due metà e netto > 0. Le celle
sotto i 200 eventi non si misurano e non contano.

**Strada B.** Si sceglie al massimo una cella per lato, solo fra quelle che
passano. Al passo 5 la cella si misura come un filtro (tenuti contro
scartati, due metà), ma la soglia di rumore usa **k = celle misurate
dall'atlante**: la cella è stata scelta guardando tutte quelle celle, e il
passo 5 è una seconda misura dello stesso effetto. Su BINANCE_PERP_BTCUSDT
sono circa 560 celle, soglia 3,91. Nella soglia cumulata le celle si sommano
ai trigger; la cella riprovata al passo 5 non conta due volte. Nella strada B
la confidenza si salta. Senza una cella (strada A) tutto resta come prima.

**Una mappa, non un cancello.** Che una cella passi non vuol dire che il
trigger funzioni lì: vuol dire che merita la misura del passo 5, con
l'asticella alta. Nessuna cella che passa non è un giudizio sul trigger.

**Dove si usa:** Lab, schermate 3c e 3d (`atlante_dei_trigger`,
`scegli_cella`); notebook di ricerca, sezione 1.5. Collaudo:
`test_atlante.py`.

---

## Unità: punti, pip e bp
 
| Unità | EURUSD | BTCUSD |
|---|---|---|
| **punto** | 0,00001 (quinta cifra) | 0,01 |
| **pip** (dal 10/10 fisso in `engine/simboli.py`, non più `deduci_pip`) | 0,0001 | 1 USD |
 
**Un pip sono 10 punti.** La colonna `spread` del CSV è in **punti**. Su EURUSD a
prezzo 1,1173: 1 pip = 0,895 bp. Un `picco_pips` di 70 su BTCUSD sono 70 dollari, non
70 pips valutari — **è il primo controllo da fare portando il tool su un asset nuovo.**

**bp e ATR accanto ai pips (20/10/2026, `63` §4).** Su un asset il cui prezzo
cambia molto (BTC da 7.000 a 100.000 $) i pips pesano di più gli anni a prezzo
alto. Due unità in più, per trade e per ogni rendimento a H barre:
- **bp** = pips × pip ÷ prezzo d'ingresso × 10.000 (1 bp = 0,01% del prezzo): un
  trade dell'1% vale 100 bp a 7.000 $ come a 70.000 $. I costi si convertono
  trade per trade; sulle crypto la commissione è una costante (perpetual Binance:
  2 × 0,05% = 10 bp andata e ritorno);
- **ATR** = pips × pip ÷ ATR giornaliero a 5 giornate chiuse noto al segnale
  (lo stesso del money management). Non è la «R» del money management, che è la
  distanza dallo stop.

Funzioni: `metriche.bp_per_trade`, `metriche.atr_per_trade`,
`stagionalita.rendimenti_avanti_unita`, parametri `unita` e `unita_extra` di
`rosa_entry` e `rosa_sistemi`, voci `ev_bp` ed `ev_atr` della scheda.

**Quale unità decide (U2, 20/10/2026).** Sui symbol da exchange **decide il bp** in
tutti i passi: rosa dei trigger e dei sistemi, ricerca delle uscite, ricerca dei
filtri (tenuti contro scartati), due metà, scheda (solidità, P(EV<0), verdetto). I
pips restano accanto, e restano l'unità di totale, drawdown e money management
(sono soldi: pips × valore del pip, trade per trade al prezzo di quel trade).

**Lo stress test in bp sulle crypto (23/10/2026, `61` §15).** Sui symbol da
exchange Monte Carlo, drawdown e tabella di controllo dello stress test lavorano
sui **bp netti per trade** (`montecarlo.bp_per_dataset`, funding compreso): è lo
stesso valore in dollari a ogni trade, quindi un trade dell'1% pesa uguale a
10.000 e a 50.000 $. Prima si sommavano i pips a quantità fissa di moneta, e gli
anni a prezzo alto pesavano di più. I lotti consigliati vengono dal drawdown
sfortunato in bp e dal prezzo dell'ultima barra dei dati (1 bp con 1 lotto =
prezzo × contratto ÷ 10.000 $), e una riga dice quale prezzo è stato usato. Sul
broker lo stress test resta in pips, identico a prima. Nella schermata 7 la
«stessa esposizione a ogni trade» del confronto P3 è, sulle crypto, lo stesso
valore in dollari: coerente con il bp. L'event study misurava già in
percentuale del prezzo. Sul broker (sospeso) decidono ancora i pips. Confronto fra
le due unità in `63` §4.7.

**La confidenza in bp (22/10/2026).** Anche `confidenza.py` ha il parametro
`unita`: in bp la confidenza è la media dei bp netti (`bp_medi`, i pips
accanto) e le soglie dei filtri sono **multipli del costo andata e ritorno**
del symbol in bp (commissione di listino più spread, senza funding,
`costo_andata_ritorno_bp`), fissati dal listino e non dai dati:
`CONF_BP_MEDI_0.5C` = sopra mezzo costo (5,0 bp sul perpetual Binance BTC,
10,0 bp sullo spot Bybit ETH). È la stessa idea delle soglie 0,5 e 0,8 pips
su EURUSD, circa metà e quasi tutto il costo di un trade. In pips (broker)
soglie e nomi restano quelli di prima (`CONF_PIPS_MEDI_0.5`). La curva
dell'OOS, il totale e il drawdown restano in pips, con la media in bp accanto.

**Il funding dei perpetual nei netti (21/10/2026, `63` §5).** Sui perpetual
i netti di ogni trade tolgono anche il funding, con il segno: ogni
liquidazione S con ingresso < S ≤ uscita costa lato × tasso × prezzo Open
della barra di S (il long paga se il tasso è positivo, lo short incassa).
Colonna `FundingPips` dei trade (+ = pagato), sottratta da
`metriche.pips_per_trade`: quindi vale in pips e in bp, in ogni passo che
decide. Il rischio del money management (stop + costi) NON contiene il
funding: si conosce solo a trade chiuso. Nella scheda e nella verifica dei
trade il costo medio per trade è diviso in commissione, spread e funding
(anche long e short separati), in bp con i pips accanto.
 
---
 
## Cosa manca ancora ai criteri
 
- **Yardstick dopo 10/20/40/100 trade** (Passo 7): le soglie oltre cui si spegne il
  sistema in live
- **Sizing** dalla distribuzione del drawdown (Passo 7)
- ~~Conteggio automatico di `k`~~ — fatto il 24/9 per ogni chiamata; le prove di
  passi diversi ancora non si sommano
- **Baseline oraria** che automatizzi il «t netto»