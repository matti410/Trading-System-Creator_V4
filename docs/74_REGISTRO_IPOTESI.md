# 74 · Registro delle ipotesi della mappa delle anomalie

**Data:** 27 ottobre 2026
**Stato:** tutte le schede sono **in bozza, da approvare**. Nessuna è stata misurata.
Nessun codice. Le schede si approvano una per una (`73` §7); solo le approvate
entrano in `engine/ipotesi.py` con la PR B.
**Riferimenti:** `73` §B.2 (i campi), §B.3 (la misura), §B.4 (il conto), §B.6 (la
prima versione), §8 (decisioni di Mattia del 26/10/2026, con la correzione D6).

**Indice:** §1 Come si legge · §2 Quello che abbiamo già visto sui dati · §3 Le
sette schede (M01–M07) · §4 Il registro · §5 Cosa resta da decidere.

---

## 1 · Come si legge

- Ogni scheda ha i campi di `73` §B.2.1. In più ha la riga **prove**: quante fasce
  entrano nel conto del dataset se la scheda si misura.
- Le fasce dei quintili si calcolano sulle sole barre passate, con una finestra di
  365 giorni (D5). Le prime barre, finché la finestra non è piena, non hanno fascia.
- **Riferimento:** il mercato della stessa ora per le variabili non di calendario e
  per le ore del funding con il segno (D6); il mercato a qualunque ora per le
  variabili solo di calendario.
- **Orizzonte** in ore. Su un timeframe dove l'orizzonte non è un numero intero di
  barre (1 ora su H4) la scheda non si misura.
- **Una scheda senza un segno atteso dal meccanismo non si può approvare così com'è**
  (`73` §B.2.1). Qui due schede sono in questo caso (M06, M07): lo scrivo invece di
  sceglierne uno.
- I nomi delle variabili sono proposte: oggi esiste solo `basis_bp` in
  `engine/indicatori.py`; le altre si scrivono con la PR B.

## 2 · Quello che abbiamo già visto sui dati

Le idee qui sotto non nascono tutte a occhi chiusi. Fino al 26/10/2026, sui dati
in-sample dello studio, sono passati sotto gli occhi di Mattia e miei:

| cosa | dove | cosa ha mostrato |
|---|---|---|
| il **profilo orario 2a**, BINANCE_PERP_BTCUSDT M15, H = 41 | giro dei testi del 26/10 (`Lab_testi_nuovi_BTC.html`) | l'ora migliore per un long alle **12:45 UTC** (+7,2 bp sulla media di tutte le ore), la peggiore alle **23:15 UTC** (−8,2 bp); nessuna ora oltre il caso, su 96 |
| la **rosa 3a** e la classifica, BTC perp, H = 25 e 41 | prove d'identità e giro dei testi del 26/10 | nella rosa E21_BELT_HOLD (long) ed E39_SHORT_HOUR_REVERSAL_DOWN (short) |
| l'**atlante 3c** di E21_BELT_HOLD, BTC perp e ETH spot | stessi giri | nessuna situazione passa, comprese basis alta e bassa. Misura E21 dentro la situazione, non la variabile da sola |
| i giri dei lavori precedenti (`66`–`71`) | resoconti | rose, atlanti e profili su BTC perp ed ETH spot con H = 25 e 41 |

Quando una scheda prende l'idea, la fascia o il segno anche solo in parte da qui, lo
dice nel suo campo «da dove viene l'idea», insieme a cosa va contato.

---

## 3 · Le sette schede

### M01 · Ore del funding con il segno del funding

| campo | contenuto |
|---|---|
| stato | in bozza, da approvare |
| meccanismo | Sui perpetual il funding si paga alle 00:00, 08:00 e 16:00 UTC. Chi è dal lato che paga (i long con il funding positivo, gli short con il funding negativo) ha un motivo per chiudere poco prima del pagamento. Chi è costretto a perdere è chi resta dall'altra parte del flusso: nell'ora prima del pagamento quei venditori (o compratori) spingono il prezzo contro il lato che paga |
| da dove viene l'idea | Dal meccanismo del funding (`63` §5). **Ma è in parte già visto sui dati:** il profilo 2a di BTC perp con H = 41 (26/10) mostrava l'ora peggiore per un long alle 23:15 UTC, 45 minuti prima del pagamento delle 00:00 (−8,2 bp, «può essere solo caso»). Quell'ora rientra nella finestra che la scheda guarda e va contata: si aggiungono le **96 fasce del profilo**, come per un trigger a orario (`73` §B.4). La correzione D6 (stessa ora) serve proprio a non riscoprire quell'effetto: si misura solo il segno del funding |
| variabile | `funding_segno_prima_pagamento` (nuova): sulle barre dell'ora prima di 00:00, 08:00 e 16:00 UTC, il segno dell'**ultimo tasso già liquidato** (8 ore prima). Il tasso del pagamento che sta per arrivare non è nei nostri dati prima che sia pagato: usarlo sarebbe guardare nel futuro. Il segno del funding cambia di rado da un pagamento al successivo, ma resta un'approssimazione e va detto |
| tipo di fasce | categorie: «ora prima del pagamento, funding positivo», «ora prima del pagamento, funding negativo». Le altre barre non sono in nessuna fascia |
| fascia attesa e segno | funding positivo → **sotto il mercato** (short); funding negativo → **sopra il mercato** (long) |
| orizzonte | 1 ora (dal segnale fino al pagamento) |
| mercato di riferimento | **stessa ora** (D6) |
| cosa serve | `dati/<SYMBOL>_FUNDING.csv` |
| portabilità su TradingView | **approssimata**: le ore sì; il segno del funding no, TradingView non vede il funding. Si approssima con il segno della basis (perpetual meno spot: due symbol che TradingView vede) |
| dataset | solo perpetual (Binance e Bybit, le quattro monete). Su Bybit gli intervalli del funding possono non essere di 8 ore (colonna `intervallo_ore`): la scheda si misura solo dove sono di 8 ore |
| prove | 2 fasce, più le 96 del profilo (idea già vista) |

### M02 · Giorno della settimana e fine settimana

| campo | contenuto |
|---|---|
| stato | in bozza, da approvare. **Senza segno atteso:** così com'è non si può approvare |
| meccanismo | Nel fine settimana i desk istituzionali, il CME e le borse sono chiusi: meno liquidità, chi muove il prezzo è diverso. Il meccanismo dice che il fine settimana è **diverso**, non in che **verso**. Nessuna regola del meccanismo dà un segno al lunedì o alla domenica |
| da dove viene l'idea | Dal meccanismo della liquidità. Niente di visto sui dati per giorno della settimana: il profilo 2a non divide i giorni (decisione del 18/10/2026, `stagionalita.py`), e l'atlante mette il fine settimana dentro ASIA_NOTTE insieme alla notte asiatica. Nessun paper letto nel registro di `50` dà un segno |
| variabile | `giorno_settimana` (nuova): il giorno UTC della barra d'ingresso, 7 categorie; in alternativa `fine_settimana` (2 categorie, sabato e domenica UTC contro gli altri giorni) |
| tipo di fasce | categorie (7, oppure 2) |
| fascia attesa e segno | **nessun segno dal meccanismo.** Per approvarla serve una fonte che lo dia (un paper sulle crypto, con il segno e l'orizzonte) oppure la decisione di Mattia di lasciarla fuori |
| orizzonte | 24 ore (un giorno) |
| mercato di riferimento | **qualunque ora** (variabile solo di calendario) |
| cosa serve | solo le candele |
| portabilità su TradingView | **sì** (il giorno della settimana) |
| dataset | tutti |
| prove | 7 fasce (o 2 con la versione fine settimana) |

### M03 · Apertura USA

| campo | contenuto |
|---|---|
| stato | in bozza, da approvare. **Senza segno atteso:** così com'è non si può approvare |
| meccanismo | Alle 09:30 di New York aprono le borse americane e, dal gennaio 2024, gli ETF spot su BTC ed ETH: arrivano flussi che di notte non ci sono. Il meccanismo dice che **dopo l'apertura il prezzo si muove di più**, non in che verso. Un segno lo darebbe una regola di momentum (l'apertura continua nel verso della notte), ma è già nel catalogo: E36 (Gao et al., la prima mezz'ora dalle 17:00 di New York alle 09:30, `50` §10 riga 15) |
| da dove viene l'idea | Dal meccanismo dei flussi americani, e da `73` §B.6: il profilo 2a è in UTC e vede l'apertura sfocata, perché in UTC si sposta di un'ora con l'ora legale. **In parte già visto sui dati:** il profilo 2a di BTC perp con H = 41 (26/10) mostrava l'ora migliore per un long alle 12:45 UTC, 45 minuti prima dell'apertura nei mesi con l'ora legale (13:30 UTC). Se la scheda prende un segno, quello visto va contato: le **96 fasce del profilo** |
| variabile | `dopo_apertura_usa` (nuova): le barre della prima ora dopo le 09:30 di New York, all'ora di New York |
| tipo di fasce | categorie: «prima ora dopo l'apertura» contro le altre barre |
| fascia attesa e segno | **nessun segno dal meccanismo.** Con il segno di E36 sarebbe un doppione di E36; con il segno visto nel profilo sarebbe un'idea già vista. Decide Mattia: lasciarla fuori, o approvarla con una fonte e il conto delle 96 fasce |
| orizzonte | 1 ora |
| mercato di riferimento | **qualunque ora** (variabile solo di calendario) |
| cosa serve | solo le candele |
| portabilità su TradingView | **sì** (sessione di New York) |
| dataset | tutti |
| prove | 2 fasce, più le 96 del profilo se il segno viene da lì |

### M04 · Funding estremo

| campo | contenuto |
|---|---|
| stato | in bozza, da approvare |
| meccanismo | Con il funding molto positivo chi è long a leva paga ogni 8 ore e le posizioni lunghe sono affollate: alla prima discesa scattano le liquidazioni a catena, e chi è costretto a perdere sono i long a leva. Con il funding molto negativo, lo stesso sugli short |
| da dove viene l'idea | Dal meccanismo del funding (`73` §B.2.2, l'esempio). Niente di visto sui dati sul funding come variabile: l'atlante e le schede hanno usato il funding solo come costo dei trade |
| variabile | `funding_ultimo` (nuova): l'ultimo tasso liquidato, noto dall'istante del pagamento (non prima) |
| tipo di fasce | quintili, finestra 365 giorni di barre passate |
| fascia attesa e segno | **Q5 → sotto il mercato (short)**; **Q1 → sopra il mercato (long)** |
| orizzonte | 24 ore (tre pagamenti) |
| mercato di riferimento | **stessa ora** |
| cosa serve | `dati/<SYMBOL>_FUNDING.csv` |
| portabilità su TradingView | **approssimata**: il funding no; la basis, la sua parente più vicina, sì |
| dataset | solo perpetual |
| prove | 5 fasce |

### M05 · Basis estrema

| campo | contenuto |
|---|---|
| stato | in bozza, da approvare |
| meccanismo | La basis è quanto il perpetual costa più dello spot. Una basis molto alta vuole dire che chi compra a leva sul perpetual paga caro per entrare: posizioni lunghe affollate, lo stesso meccanismo di M04 visto un istante per volta invece che come media su 8 ore. Con la basis molto bassa, lo stesso sugli short |
| da dove viene l'idea | Dal meccanismo, come M04. **Da sapere:** l'atlante ha già una situazione basis alta / bassa (sopra o sotto la mediana di 125 ore), e nei giri del 26/10 si sono viste le righe basis di E21_BELT_HOLD su BTC perp: nessuna passa. Misurano E21 dentro la basis, non la basis da sola, e non hanno guidato la scelta della fascia né del segno; le situazioni dell'atlante sono già nel conto di quel dataset. **Doppione probabile con M04:** su Binance il funding si calcola dalla differenza fra perpetual e indice spot. Se si approvano tutte e due, la riga DOPPIONI della PR B le confronta prima di misurarle |
| variabile | `basis_bp` (esiste, `engine/indicatori.py`) |
| tipo di fasce | quintili, finestra 365 giorni di barre passate |
| fascia attesa e segno | **Q5 → sotto il mercato (short)**; **Q1 → sopra il mercato (long)** |
| orizzonte | 8 ore (un intervallo di funding) |
| mercato di riferimento | **stessa ora** |
| cosa serve | lo spot della stessa coppia (`aggancia_spot`) |
| portabilità su TradingView | **sì**: perpetual e spot sono due symbol che TradingView vede |
| dataset | solo perpetual, dove c'è lo spot (lo spot Bybit parte dal 2021) |
| prove | 5 fasce |

### M06 · BTC che anticipa le altcoin

| campo | contenuto |
|---|---|
| stato | in bozza, da approvare |
| meccanismo | Il prezzo si forma prima su BTC, il mercato più liquido; le altcoin lo seguono con un ritardo, perché i market maker e gli arbitraggisti aggiornano prima BTC. Chi perde è chi scambia l'altcoin al prezzo vecchio |
| da dove viene l'idea | Dal meccanismo della formazione del prezzo (`73` §B.6, «chi arriva prima»). Niente di visto sui dati: nessun giro ha mai messo BTC accanto a un'altcoin. Nessun paper letto nel registro di `50` |
| variabile | `scarto_btc_1h` (nuova): il rendimento di BTC nell'ultima ora **meno** il rendimento dell'altcoin nella stessa ora, stesso exchange e stesso mercato (perpetual con perpetual, spot con spot), barre allineate per data. Si usa lo scarto e non il solo rendimento di BTC: quello di BTC si muove quasi insieme a quello dell'altcoin, e la scheda finirebbe per misurare il rendimento recente dell'altcoin (M07) |
| tipo di fasce | quintili, finestra 365 giorni di barre passate |
| fascia attesa e segno | **Q5 (BTC è salita più dell'altcoin) → sopra il mercato (long)**; **Q1 → sotto il mercato (short)** |
| orizzonte | 1 ora |
| mercato di riferimento | **stessa ora** (il mercato dell'altcoin) |
| cosa serve | il CSV di BTC dello stesso exchange e mercato; alla schermata 1 della mappa, entrambi nello studio (impronta), lo stesso confine |
| portabilità su TradingView | **sì** (un altro symbol) |
| dataset | ETH, SOL, XRP, perpetual e spot, Binance e Bybit. Non BTC |
| prove | 5 fasce per dataset |

### M07 · Rendimento recente estremo

| campo | contenuto |
|---|---|
| stato | in bozza, da approvare. **Il segno va deciso da Mattia:** il meccanismo ne dà due |
| meccanismo | Dopo una salita o una discesa molto forte in poche ore ci sono due meccanismi opposti. **Inversione:** le liquidazioni a catena spingono il prezzo oltre il giusto, poi rientra; perde chi è stato liquidato al prezzo peggiore. **Continuazione:** chi segue il trend entra dopo, e il movimento prosegue. Il meccanismo da solo non dice quale dei due prevale a 4 ore |
| da dove viene l'idea | Da `73` §B.6 («comportamento»). **In parte già visto sui dati:** nella rosa di BTC perp dei giri del 26/10 c'era E39_SHORT_HOUR_REVERSAL_DOWN, un'inversione di un'ora (paper Wen et al., `50` §10 riga 17). Una scelta del segno «inversione» potrebbe essere stata suggerita da lì. Il catalogo ha anche E41 (Liu e Tsyvinski, `50` §10 riga 19), che è un momentum sul rendimento della giornata: un'altra fonte, con il segno opposto, a un altro orizzonte. **Doppioni da controllare:** E39 ed E41 |
| variabile | `rendimento_4h` (nuova): il rendimento delle ultime 4 ore, al Close della barra |
| tipo di fasce | quintili, finestra 365 giorni di barre passate |
| fascia attesa e segno | **da decidere prima della misura**, una delle due: inversione (Q5 → sotto il mercato, Q1 → sopra) oppure continuazione (Q5 → sopra, Q1 → sotto). Misurarle tutte e due vale due schede e due conti |
| orizzonte | 4 ore |
| mercato di riferimento | **stessa ora** |
| cosa serve | solo le candele |
| portabilità su TradingView | **sì** (solo prezzo) |
| dataset | tutti |
| prove | 5 fasce (10 se si misurano i due segni) |

---

## 4 · Il registro

Una riga per scheda. Le colonne degli esiti si riempiono solo dopo la misura, con la
PR B; i risultati collaudano il tool, non sono verdetti sul mercato.

| scheda | stato | segno | idea già vista sui dati | prove previste per dataset | misurata su | esito | trigger nato |
|---|---|---|---|---|---|---|---|
| M01 ore del funding con il segno | bozza | sì | sì, profilo 2a (23:15 UTC) | 2 + 96 | — | — | — |
| M02 giorno della settimana | bozza | **no** | no | 7 (o 2) | — | — | — |
| M03 apertura USA | bozza | **no** | sì, profilo 2a (12:45 UTC), se il segno viene da lì | 2 (+ 96) | — | — | — |
| M04 funding estremo | bozza | sì | no | 5 | — | — | — |
| M05 basis estrema | bozza | sì | no (righe basis di E21 viste, non usate) | 5 | — | — | — |
| M06 BTC che anticipa le altcoin | bozza | sì | no | 5 | — | — | — |
| M07 rendimento recente estremo | bozza | **da decidere** | forse, rosa (E39) | 5 (o 10) | — | — | — |

## 5 · Cosa resta da decidere (Mattia)

1. **M02 e M03, senza segno:** lasciarle fuori dalla prima versione, oppure
   approvarle con una fonte che dia il segno (e, per M03, il conto delle 96 fasce se
   il segno viene dal profilo).
2. **M07:** inversione o continuazione, prima di qualunque misura.
3. **M01 e M03:** confermare che l'idea vista nel profilo 2a si conta con le 96
   fasce del profilo.
4. **M04 e M05:** se tenerle tutte e due, sapendo che sono probabilmente doppioni.
5. **Gli orizzonti** (1, 24, 1, 24, 8, 1, 4 ore): li ho presi dal meccanismo di ogni
   scheda. Cambiarli dopo la misura è una versione nuova della scheda e si conta.
