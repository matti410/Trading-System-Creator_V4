# 71 · Proposta: lo spread di un passo al prezzo d'ingresso di ogni trade

**Data:** 25 ottobre 2026
**Stato:** PROPOSTA BREVE, approvata; codice fatto (resoconto al §8).
**Nasce da:** `docs/70` §15.3 (la strada D, valutata in chat il 25/10).
**Decisioni già prese da Mattia (25/10):**
1. lo spread esce dal prezzo di fill;
2. un passo per trade nella colonna `CostoExtraPips`, nei due motori;
3. la confidenza usa il costo del singolo trade;
4. l'effetto su stop e target si dichiara e si misura (quanti trade cambiano
   uscita su BTC e su XRP).

**Indice:** §0 Perché · §1 Come funziona · §2 I consumatori da adattare · §3 Una
domanda: il prezzo della confidenza · §4 Collaudo · §5 Il confronto dichiarato · §6
Tempi · §7 Cosa resta com'è · §8 Resoconto

---

## 0 · Perché

Oggi, sui symbol da exchange, lo spread di un passo diventa una **percentuale fissa**
del prezzo: un passo diviso il prezzo mediano dell'in-sample (`70` §15.3, strada A).
Il passo invece è un importo fisso. In bp vale tanto di più quanto più il prezzo è
basso.

| | passo | percentuale fissa di oggi | vero, in-sample (5°–95° percentile) | vero, out-of-sample (media) |
|---|---|---|---|---|
| BINANCE_PERP_BTCUSDT | 0,1 $ | 0,028 bp | 0,010–0,111 bp | 0,012 bp |
| BINANCE_PERP_XRPUSDT | 0,0001 $ | 1,9 bp | 0,43–5,0 bp (massimo 9,3) | 0,60 bp |
| BYBIT_SPOT_XRPUSDT | 0,0001 $ | 1,7 bp | 0,35–2,9 bp | 0,67 bp |

Le conseguenze su XRP:
- **Out-of-sample:** ogni trade paga circa 1,3 bp di troppo, il 13% della
  commissione andata e ritorno (10 bp).
- **Anni a prezzo basso o alto:** i trade del 2020 (prezzo 0,2 $) pagano 1,9 bp
  invece di 4–5. Quelli a 2–3 $ pagano 1,9 bp invece di 0,4.
- **Confronti per periodo:** le due metà, la confidenza nel tempo e i filtri di
  regime confrontano trade con un costo sbagliato in direzioni opposte.
- **In pips l'errore è al contrario.** La percentuale fissa fa crescere lo spread
  con il prezzo: a 3 $ vale circa 5,7 pips invece di 1. Lo si vede nel totale e nel
  drawdown in pips.

Su BTC lo spread è l'1–4 per mille della commissione: cambia poco, ma la regola è
la stessa.

---

## 1 · Come funziona

- **Nei motori lo spread è zero** sui symbol da exchange. Il prezzo di fill è l'Open
  della barra d'ingresso, senza spread, nel motore veloce come in «bt». I due motori
  restano identici fra loro: «bt» resta l'oracolo.
- **Un passo per trade nella colonna `CostoExtraPips`**, dopo il motore, come il
  funding (`exchange.aggiungi_funding`) e il rollover del broker
  (`quarantena_trade`):

  ```
  spread in pips = SPREAD_PASSI × passo_prezzo / pip         (0,1 su BTC ed ETH, 0,01 su BINANCE_SPOT_BTCUSDT, 1 su SOL e XRP)
  ```

  In pips è un numero fisso. In bp `metriche.bp_per_trade` lo converte già trade per
  trade con il prezzo d'ingresso: `passo / prezzo d'ingresso × 10.000`.
  Si paga una volta, all'ingresso, come oggi.
- **Nei costi** (`costi_storico`): `costi["spread"] = 0.0` più una voce nuova,
  `costi["spread_passo_pips"]`. `run_exit_search_bt` e `run_filter_search_bt` la
  ricevono con `**costi` (parametro nuovo, additivo; `None` = come prima) e la
  aggiungono a `CostoExtraPips`.
- **Stop e target.** Oggi si misurano dal prezzo d'ingresso che contiene lo spread;
  con questa strada si misurano dall'Open. Il livello si sposta di circa un passo e
  qualche trade può uscire in un punto diverso: lo si **dichiara e lo si misura**
  (§5).
- **La commissione** si calcola sul prezzo di fill, che si abbassa di un passo: una
  differenza di qualche milionesimo, che si dichiara.
- **Il broker (sospeso) non cambia:** spread di listino dentro il prezzo, come oggi.

---

## 2 · I consumatori da adattare

| dove | oggi | con la strada D |
|---|---|---|
| `vetrina.costi_storico` | `spread` = passo / mediana dell'in-sample | `spread = 0`, `spread_passo_pips` = passo / pip; resta `sp["normale"]` (in pips, già giusto) |
| `exit_search_bt`, `filter_search_bt` (e `due_meta`, che li chiama) | spread nel prezzo di fill | parametro `spread_passo_pips`, aggiunto a `CostoExtraPips` dopo `costo_extra_pips` |
| `vetrina` 2754 (`solo_costi`, le chiavi che passano ai motori) | `spread`, `commission`, ... | più `spread_passo_pips` |
| `atlante` (il netto di ogni evento) | `spread × ingresso / pip` | `spread_passo_pips`, fisso in pips (in bp segue il prezzo dell'evento) |
| `confidenza.costo_andata_ritorno_bp` e le soglie `CONF_BP_MEDI_xC` | un costo solo: (2 × commissione + spread) × 10.000 | il costo del singolo trade: 2 × commissione + passo / prezzo (§3); le soglie restano multipli del costo, trade per trade |
| `mm_adattatore` (il rischio del money management) | `spread_pips + (lordi − netti)` | **niente `spread_pips` in più**: con la strada D lo spread è già in `lordi − netti`, e altrimenti si conterebbe due volte |
| `vetrina._mostra_costi` (tabella dei costi) | `spread × ingresso / pip + CostoExtraPips` | si adatta da sola (`spread = 0`, il passo sta in `CostoExtraPips`); cambia solo il testo della riga |
| `vetrina_verifica` (il fill atteso) | `Open × (1 ± spread)` | si adatta da sola (`spread = 0`: il fill è l'Open) |
| riepilogo della schermata 1 («Costo per trade in bp») | spread al prezzo mediano dell'in-sample | «spread di un passo al prezzo d'ingresso: da x a y bp nell'in-sample (mediana z)» |
| `montecarlo`, `giudizio`, `rosa_sistemi`, stress test | usano i pips netti dei trade | si adattano da soli |
| notebook di ricerca: cella 72 (`COSTO_RT_BP`, confidenza) e cella 83 (money management, `spread_pips=`) | il costo unico | le stesse funzioni nuove; allineato al Lab |
| `test_exchange` F2, `test_confidenza`, `test_motore_veloce`, ... | la regola di oggi | i test che verificano la regola vecchia passano alla nuova (dichiarato, come F2 nella PR #71); nessuno si ammorbidisce |

Restano identici perché non usano i costi: event study, profilo orario, curve dello
scarto, rosa dei trigger, classifiche e conto delle prove.

---

## 3 · Una domanda: il prezzo della confidenza

Mattia ha deciso il costo del singolo trade, «il prezzo d'ingresso è noto al
momento del trade». C'è un dettaglio da decidere.

Il filtro di confidenza si valuta sulla **barra del segnale**, e il trade entra
all'Open della barra dopo. Se la soglia usasse quell'Open, il valore del filtro
nella barra del segnale dipenderebbe dalla barra dopo: `verifica_lookahead` lo
segnalerebbe, giustamente.

**Proposta: la soglia usa il Close della barra del segnale**, l'ultimo prezzo noto
quando si decide. Rispetto all'Open dopo differisce al più per il salto fra le due
barre, cioè di qualche millesimo del costo. Il bp netto del trade, quello che la
confidenza media nel tempo, resta invece calcolato con il vero prezzo d'ingresso.

Decide Mattia: Close della barra del segnale (raccomandato) oppure Open della barra
d'ingresso, con il filtro spostato di una barra.

---

## 4 · Collaudo (test a risultato noto)

1. **Un trade a mano:** long all'Open 100, passo 0,01, pip 0,01 → `CostoExtraPips` =
   1 pip, 1 bp. Lo stesso trade all'Open 200 → 1 pip, 0,5 bp.
2. **I due motori:** spread zero e passo in `CostoExtraPips` danno trade identici al
   bit (fill, uscite, `CostoExtraPips`, pips netti), long e short, con e senza stop.
3. **La somma torna:** sui trade con la stessa uscita, netti_D − netti_oggi =
   (spread_oggi × Entry_oggi − passo) / pip, più il pezzetto di commissione, a meno
   di 1e-9.
4. **Atlante:** il costo di un evento è passo / pip in pips, passo / prezzo in bp.
5. **Confidenza:** due trade con la stessa media mobile e prezzi diversi; la soglia a
   1C fa passare quello a prezzo alto e non quello a prezzo basso. La soglia della
   barra usa il Close della barra (`verifica_lookahead`).
6. **Money management:** il costo del rischio contiene lo spread una volta sola.
7. **Il broker non cambia:** EURUSD, costi e trade identici a prima.
8. **Riepilogo:** la riga del costo dice l'intervallo in bp.

---

## 5 · Il confronto dichiarato (al posto dell'identità)

I numeri cambiano su tutti i symbol da exchange, quindi non si chiede l'identità con
main. Si chiede un **confronto dichiarato**: main contro ramo, CSV del 19/10, con la
copia di main e le cartelle delle prove del `70` (tenute per questo). Lab e notebook
di ricerca su:
- **BINANCE_PERP_BTCUSDT** (il dataset di sviluppo);
- **BINANCE_PERP_XRPUSDT** (dove l'effetto è grande);
- **BYBIT_SPOT_ETHUSDT** (il giro di controllo, solo long).

Si riporta:

| cosa | atteso |
|---|---|
| event study, profilo, curve, rosa dei trigger, conto delle prove | **identici** |
| spread medio in bp, in-sample e out-of-sample | come nella tabella del §0 |
| **trade che cambiano uscita** (barra o prezzo d'uscita diversi) | quanti e in percentuale, per BTC e XRP, separati fra stop, target e uscita a H barre |
| trade con la stessa uscita | la somma del §4 punto 3 torna |
| guadagno medio netto (bp e pips), totale, solidità, in-sample e out-of-sample | prima → dopo |
| confidenza: quanti segnali cambiano lato della soglia | prima → dopo |
| rosa dei sistemi, atlante netto, scheda, money management, stress test | prima → dopo, senza giudizi |

I numeri sono un collaudo del tool, non un verdetto.

---

## 6 · Tempi

| cosa | tempo |
|---|---|
| Codice (engine additivo, consumatori del §2, i due notebook) e test del §4 | una PR, un giorno di lavoro |
| Suite completa | circa 13 minuti |
| Confronto dichiarato: 3 symbol × 2 notebook × main e ramo = 12 giri, 3 alla volta | circa 40 minuti di macchina |
| Resoconto in questo documento | a fine PR |

Prima della PR resta la suite completa.

---

## 7 · Cosa resta com'è

- L'ipotesi che lo spread sia **un passo** (`SPREAD_PASSI = 1`): cambia solo come lo si
  converte.
- La commissione taker di listino e il funding.
- Il confine dello studio e la mediana dell'in-sample per tutto ciò che non è
  spread.
- Il broker.


---

## 8 · Resoconto (*resoconto*, 25/10/2026)

**Decisione di Mattia sul §3:** la soglia della confidenza usa il **Close della barra
del segnale**.

### 8.1 · Cosa è stato fatto
- **`engine/exchange.py`:** `aggiungi_spread_passo` mette un passo in `CostoExtraPips`;
  `spread_bp` lo converte in bp.
- **`costi_storico` (exchange):** `spread = 0` e `spread_passo_pips` = un passo.
- **`run_exit_search_bt`, `run_filter_search_bt`:** il parametro `spread_passo_pips`,
  additivo, aggiunto ai trade nei due motori. `due_meta` lo riprende da `fs`.
- **Atlante:** un passo per evento nel netto.
- **Confidenza:**
  - `costo_andata_ritorno_bp(costi, prezzi)` dà una Series, barra per barra, al
    Close della barra del segnale;
  - soglie per barra nei filtri;
  - `soglie_confidenza` con mediana, minimo e massimo.
- **Money management:** sui symbol da exchange lo spread non si aggiunge al rischio,
  perché è già nei netti.
- **Riepilogo della schermata 1:** «spread di un passo al prezzo d'ingresso, da x a
  y bp nell'in-sample».
- **Notebook di ricerca:** la cella della confidenza.
- **Test:**
  - `test_spread_per_trade.py`, 27 test a risultato noto (§4);
  - `test_confidenza` 39–41 e `test_exchange` F2 portati alla regola nuova
    (dichiarato).
- **Il broker non cambia.**

### 8.2 · Il confronto dichiarato (§5)

Main contro ramo, CSV del 19/10, `confine="80%"` per tutti e due: stessa divisione,
cambia solo lo spread. Su XRP la rosa dei trigger è vuota e il Lab si ferma alla 3b,
su main come sul ramo. Per collaudare il resto della catena si è aggiunto a mano
E21_BELT_HOLD, lo stesso trigger di BTC: è una scelta di collaudo, non di ricerca.

**Identici, come atteso, sui tre symbol:** event study, profilo orario, curve dello
scarto, rosa dei trigger, conto delle prove.

**Spread medio per trade, in bp** (dalla tabella dei costi del Lab):

| | main, in-sample | ramo, in-sample | main, out-of-sample | ramo, out-of-sample |
|---|---|---|---|---|
| BTC perp | 0,0275 | 0,0404 (da 0,009 a 0,192) | 0,0275 | 0,0120 |
| XRP perp | 1,904 | 2,124 (da 0,31 a 7,29) | 1,904 | 0,604 |
| ETH spot Bybit | 0,0408 | 0,0448 | 0,0408 | 0,0424 |

In pips lo spread ora è un passo fisso. Prima su XRP valeva 1,43 pips nell'in-sample
e 3,58 nell'out-of-sample, invece di 1.

**Trade che cambiano uscita** (stessi trade abbinati per barra d'ingresso e lato):

| | trade | stessa uscita | stessa barra, prezzo dello stop spostato di un soffio | barra d'uscita diversa | trade solo da una parte |
|---|---|---|---|---|---|
| BTC in-sample | 2.756 | 2.396 | 359 | **1** (0,04%): da uscita a H barre a stop | 0 |
| BTC out-of-sample | 708 | 617 | 91 | **0** | 0 |
| XRP in-sample | 2.607 | 2.254 | 342 | **10** (0,38%): 5 da uscita a H a stop, 5 da stop a stop in un'altra barra | 1 e 1 |
| XRP out-of-sample | 688 → 687 | 584 | 96 | **7** (1,02%): 1 da uscita a H a stop, 6 da stop a stop | 1 |
| ETH spot in-sample | 2.100 | 1.814 | 286 | **0** | 0 |
| ETH spot out-of-sample | 548 | 475 | 73 | **0** | 0 |

- **«Stessa barra, prezzo spostato»:** sono i trade chiusi dallo stop. Lo stop si
  misura dal prezzo d'ingresso, che ora è l'Open senza spread, quindi il livello si
  sposta di circa un passo.
- **«Barra diversa»:** sono i trade in cui lo stop, spostato, viene toccato o non
  toccato in un'altra barra.
- **«Trade solo da una parte»:** un'uscita diversa libera la posizione in un altro
  momento, e il trade dopo cambia.

**La scheda (Lab), prima → dopo:**

| | guadagno medio netto (bp), in-sample | out-of-sample | totale pips netti, in-sample | out-of-sample | solidità, in-sample | out-of-sample |
|---|---|---|---|---|---|---|
| BTC perp | −3,15 → −3,14 | −11,55 → −11,54 | −78.798 → −78.561 | −75.329 → −75.250 | −0,80 → −0,80 | −2,15 → −2,15 |
| XRP perp (E21, collaudo) | −1,66 → −1,93 | −23,52 → −22,35 | −17.677 → −16.522 | −34.111 → −32.595 | −0,23 → −0,26 | −2,78 → −2,63 |
| ETH spot Bybit | −13,38 → −13,39 | −23,59 → −23,60 | −99.644 → −99.665 | −37.532 → −37.539 | −2,51 → −2,52 | −2,68 → −2,69 |

**Il resto, prima → dopo:**
- **Rosa dei sistemi:** stesso esito su tutti e tre i symbol. Lo scarto cambia di
  qualche centesimo di bp su BTC e di 0,15 bp su XRP.
- **Atlante:** netto medio delle celle da −7,416 a −7,404 pips (BTC), da −4,636 a
  −4,221 (XRP), da −32,097 a −32,093 (ETH). Celle che passano: 0 prima e dopo.
- **Confidenza (ricerca):** segnali dei trade che cambiano lato della soglia.
  - BTC: 3, 1 e 8 su 7.817 (soglie 0C, 0,5C, 0,8C);
  - **XRP: 170, 111 e 90 su 6.731**;
  - ETH: 2, 0 e 0 su 5.104.

  A 0C cambia anche la media della confidenza stessa, perché i bp netti dei trade
  passati cambiano.
- **Money management e stress test:** cambiano di poco su BTC ed ETH. Su XRP il
  drawdown realmente visto passa da 25.640 a 24.309 bp.
- **Notebook di ricerca:** girano senza errori su tutti e tre i symbol. Cambiano 16–17
  variabili su 91–99, tutte a valle dei costi (costo per barra, atlante, confidenza,
  Monte Carlo, money management, trade finali).

I numeri sono un collaudo del tool, non un verdetto.

### 8.3 · Tempi
- Codice e test: una PR.
- Confronto: 12 giri di notebook più 2 di nuovo su XRP, circa 40 minuti di macchina.
- Suite completa: circa 13 minuti.
