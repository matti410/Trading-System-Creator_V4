# 74 · Registro delle ipotesi della mappa delle anomalie

**Data:** 27 ottobre 2026 (aggiornato lo stesso giorno con le decisioni di Mattia, §5)
**Stato:**
- **approvate da Mattia il 27/10/2026:** M01, M04, M05, M06 (versione A), M07;
- **fuori dalla prima versione:** M02, M03.

Nessuna è stata misurata. Nessun codice: solo le schede approvate entrano in
`engine/ipotesi.py` con la PR B.
**Riferimenti:** `73` §B.2 (i campi), §B.3 (la misura), §B.4 (il conto), §B.6 (la
prima versione), §8 (decisioni di Mattia del 26/10/2026, con la correzione D6).

**Indice:** §1 Come si legge · §2 Quello che abbiamo già visto sui dati · §3 Le
sette schede (M01–M07) · §4 Il registro · §5 Decisioni di Mattia (27/10/2026).

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
  (`73` §B.2.1). Erano in questo caso M02 e M03: sono fuori dalla prima versione
  (§5, punto 1).
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
| stato | **approvata da Mattia il 27/10/2026** |
| meccanismo | Sui perpetual il funding si paga alle 00:00, 08:00 e 16:00 UTC. Chi è dal lato che paga (i long con il funding positivo, gli short con il funding negativo) ha un motivo per chiudere poco prima del pagamento. Chi è costretto a perdere è chi resta dall'altra parte del flusso: nell'ora prima del pagamento quei venditori (o compratori) spingono il prezzo contro il lato che paga |
| da dove viene l'idea | Dal meccanismo del funding (`63` §5). **In parte già visto sui dati:** il profilo 2a di BTC perp con H = 41 (26/10) mostrava l'ora peggiore per un long alle 23:15 UTC, 45 minuti prima del pagamento delle 00:00 (−8,2 bp, «può essere solo caso»). Quell'ora cade nell'ora che la scheda guarda: si contano le **96 fasce del profilo**, come per un trigger a orario (`73` §B.4; decisione di Mattia, §5 punto 3). La correzione D6 (stessa ora) serve a non riscoprire quell'effetto: si misura solo il segno del funding |
| variabile | `funding_segno_prima_pagamento` (nuova). **Una sola barra per pagamento** (decisione di Mattia, §5 punto 5): quella che **chiude un'ora prima** del pagamento delle 00:00, 08:00 e 16:00 UTC (su M15 le barre delle 22:45, 06:45 e 14:45, che chiudono alle 23:00, 07:00 e 15:00). Su quella barra la variabile è il segno dell'**ultimo tasso già liquidato** (8 ore prima): il tasso del pagamento che sta per arrivare non è nei nostri dati prima che sia pagato, e usarlo sarebbe guardare nel futuro. Il segno del funding cambia di rado da un pagamento al successivo, ma resta un'approssimazione. Le altre barre non sono in nessuna fascia |
| tipo di fasce | categorie, sulla sola barra di ogni pagamento: «funding positivo», «funding negativo» |
| fascia attesa e segno | funding positivo → **sotto il mercato** (short); funding negativo → **sopra il mercato** (long) |
| orizzonte | **1 ora**: segnale al Close della barra, ingresso all'Open della barra dopo (un'ora prima del pagamento), misura al Close della barra che chiude al pagamento. La misura finisce esattamente al pagamento |
| mercato di riferimento | **stessa ora** (D6) |
| da sapere prima di misurare | Su BTC il funding è quasi sempre positivo. Contro il mercato della stessa ora, la fascia «funding positivo» è quasi tutto il riferimento (quasi tutte le barre di quell'ora hanno il funding positivo), quindi il suo scarto sarà **vicino a zero per costruzione**: non dice niente sull'ipotesi. L'informazione sta nella fascia «funding negativo», che ha **pochi casi**. Con una barra per pagamento, quella fascia può restare sotto i minimi (200 occasioni, 100 giornate): in quel caso l'esito è «troppo pochi casi», e lo si sa da adesso |
| cosa serve | `dati/<SYMBOL>_FUNDING.csv` |
| portabilità su TradingView | **approssimata**: l'ora sì; il segno del funding no, TradingView non vede il funding. Si approssima con il segno della basis (perpetual meno spot: due symbol che TradingView vede) |
| dataset | solo perpetual (Binance e Bybit, le quattro monete). Su Bybit gli intervalli del funding possono non essere di 8 ore (colonna `intervallo_ore`): la scheda si misura solo dove sono di 8 ore. Timeframe: M5, M15, M30, H1. Su H4 non c'è una barra che chiude un'ora prima del pagamento: non si misura |
| prove | **98** per dataset: 2 fasce più le 96 del profilo (idea in parte già vista) |

### M02 · Giorno della settimana e fine settimana

| campo | contenuto |
|---|---|
| stato | **fuori dalla prima versione** (decisione di Mattia del 27/10/2026): nessun segno dal meccanismo. Si riapre con una fonte che dia il segno |
| meccanismo | Nel fine settimana i desk istituzionali, il CME e le borse sono chiusi: meno liquidità, chi muove il prezzo è diverso. Il meccanismo dice che il fine settimana è **diverso**, non in che **verso**. Nessuna regola del meccanismo dà un segno al lunedì o alla domenica |
| da dove viene l'idea | Dal meccanismo della liquidità. Niente di visto sui dati per giorno della settimana: il profilo 2a non divide i giorni (decisione del 18/10/2026, `stagionalita.py`), e l'atlante mette il fine settimana dentro ASIA_NOTTE insieme alla notte asiatica. Nessun paper letto nel registro di `50` dà un segno |
| variabile | `giorno_settimana` (nuova): il giorno UTC della barra d'ingresso, 7 categorie; in alternativa `fine_settimana` (2 categorie, sabato e domenica UTC contro gli altri giorni) |
| tipo di fasce | categorie (7, oppure 2) |
| fascia attesa e segno | **nessun segno dal meccanismo** |
| orizzonte | 24 ore (un giorno) |
| mercato di riferimento | **qualunque ora** (variabile solo di calendario) |
| cosa serve | solo le candele |
| portabilità su TradingView | **sì** (il giorno della settimana) |
| dataset | tutti |
| prove | 7 fasce (o 2 con la versione fine settimana), se un giorno si riapre |

### M03 · Apertura USA

| campo | contenuto |
|---|---|
| stato | **fuori dalla prima versione** (decisione di Mattia del 27/10/2026): nessun segno dal meccanismo. Si riapre con una fonte che dia il segno |
| meccanismo | Alle 09:30 di New York aprono le borse americane e, dal gennaio 2024, gli ETF spot su BTC ed ETH: arrivano flussi che di notte non ci sono. Il meccanismo dice che **dopo l'apertura il prezzo si muove di più**, non in che verso. Un segno lo darebbe una regola di momentum (l'apertura continua nel verso della notte), ma è già nel catalogo: E36 (Gao et al., la prima mezz'ora dalle 17:00 di New York alle 09:30, `50` §10 riga 15) |
| da dove viene l'idea | Dal meccanismo dei flussi americani, e da `73` §B.6: il profilo 2a è in UTC e vede l'apertura sfocata, perché in UTC si sposta di un'ora con l'ora legale. **In parte già visto sui dati:** il profilo 2a di BTC perp con H = 41 (26/10) mostrava l'ora migliore per un long alle 12:45 UTC, 45 minuti prima dell'apertura nei mesi con l'ora legale (13:30 UTC). Se un giorno si riapre con un segno, quello visto va contato: le **96 fasce del profilo** |
| variabile | `dopo_apertura_usa` (nuova): le barre della prima ora dopo le 09:30 di New York, all'ora di New York |
| tipo di fasce | categorie: «prima ora dopo l'apertura» contro le altre barre |
| fascia attesa e segno | **nessun segno dal meccanismo.** Con il segno di E36 sarebbe un doppione di E36; con il segno visto nel profilo sarebbe un'idea già vista |
| orizzonte | 1 ora |
| mercato di riferimento | **qualunque ora** (variabile solo di calendario) |
| cosa serve | solo le candele |
| portabilità su TradingView | **sì** (sessione di New York) |
| dataset | tutti |
| prove | 2 fasce, più le 96 del profilo se il segno viene da lì, se un giorno si riapre |

### M04 · Funding estremo

| campo | contenuto |
|---|---|
| stato | **approvata da Mattia il 27/10/2026**, con la regola sui doppioni qui sotto |
| meccanismo | Con il funding molto positivo chi è long a leva paga ogni 8 ore e le posizioni lunghe sono affollate: alla prima discesa scattano le liquidazioni a catena, e chi è costretto a perdere sono i long a leva. Con il funding molto negativo, lo stesso sugli short |
| da dove viene l'idea | Dal meccanismo del funding (`73` §B.2.2, l'esempio). Niente di visto sui dati sul funding come variabile: l'atlante e le schede hanno usato il funding solo come costo dei trade |
| variabile | `funding_ultimo` (nuova): l'ultimo tasso liquidato, noto dall'istante del pagamento (non prima) |
| tipo di fasce | quintili, finestra 365 giorni di barre passate |
| fascia attesa e segno | **Q5 → sotto il mercato (short)**; **Q1 → sopra il mercato (long)** |
| orizzonte | 24 ore (tre pagamenti) |
| mercato di riferimento | **stessa ora** |
| regola sui doppioni (decisa prima di misurare) | Se il controllo DOPPIONI della PR B trova M04 e M05 troppo simili, **si misura solo M05**, perché si porta su TradingView (decisione di Mattia, §5 punto 4). In quel caso M04 non si misura e non entra nel conto |
| cosa serve | `dati/<SYMBOL>_FUNDING.csv` |
| portabilità su TradingView | **approssimata**: il funding no; la basis, la sua parente più vicina, sì |
| dataset | solo perpetual |
| prove | 5 fasce (0 se la regola sui doppioni la esclude) |

### M05 · Basis estrema

| campo | contenuto |
|---|---|
| stato | **approvata da Mattia il 27/10/2026**, con la regola sui doppioni qui sotto |
| meccanismo | La basis è quanto il perpetual costa più dello spot. Una basis molto alta vuole dire che chi compra a leva sul perpetual paga caro per entrare: posizioni lunghe affollate, lo stesso meccanismo di M04 visto un istante per volta invece che come media su 8 ore. Con la basis molto bassa, lo stesso sugli short |
| da dove viene l'idea | Dal meccanismo, come M04. **Da sapere:** l'atlante ha già una situazione basis alta / bassa (sopra o sotto la mediana di 125 ore), e nei giri del 26/10 si sono viste le righe basis di E21_BELT_HOLD su BTC perp: nessuna passa. Misurano E21 dentro la basis, non la basis da sola, e non hanno guidato la scelta della fascia né del segno; le situazioni dell'atlante sono già nel conto di quel dataset |
| variabile | `basis_bp` (esiste, `engine/indicatori.py`) |
| tipo di fasce | quintili, finestra 365 giorni di barre passate |
| fascia attesa e segno | **Q5 → sotto il mercato (short)**; **Q1 → sopra il mercato (long)** |
| orizzonte | 8 ore (un intervallo di funding) |
| mercato di riferimento | **stessa ora** |
| regola sui doppioni (decisa prima di misurare) | Probabile doppione di M04: su Binance il funding si calcola dalla differenza fra perpetual e indice spot. Se il controllo DOPPIONI le trova troppo simili, **si misura solo M05** (§5 punto 4) |
| cosa serve | lo spot della stessa coppia (`aggancia_spot`) |
| portabilità su TradingView | **sì**: perpetual e spot sono due symbol che TradingView vede |
| dataset | solo perpetual, dove c'è lo spot (lo spot Bybit parte dal 2021) |
| prove | 5 fasce |

### M06 · BTC che anticipa le altcoin

| campo | contenuto |
|---|---|
| stato | **approvata da Mattia il 27/10/2026**, **versione A** (finestra 1 ora, orizzonte 1 ora). A misura la versione lenta del meccanismo (un'altcoin che in un'ora non ha seguito BTC), non il ritardo di minuti: il risultato lo dirà |
| meccanismo | Il prezzo si forma prima su BTC, il mercato più liquido; le altcoin lo seguono con un ritardo, perché i market maker e gli arbitraggisti aggiornano prima BTC. Chi perde è chi scambia l'altcoin al prezzo vecchio |
| da dove viene l'idea | Dal meccanismo della formazione del prezzo (`73` §B.6, «chi arriva prima»). Niente di visto sui dati: nessun giro ha mai messo BTC accanto a un'altcoin. Nessun paper letto nel registro di `50` |
| variabile | `scarto_btc_1h` (nuova): il rendimento di BTC nell'ultima ora **meno** il rendimento dell'altcoin nella stessa ora, stesso exchange e stesso mercato (perpetual con perpetual, spot con spot), barre allineate per data. Si usa lo scarto e non il solo rendimento di BTC: quello di BTC si muove quasi insieme a quello dell'altcoin, e la scheda finirebbe per misurare il rendimento recente dell'altcoin (M07) |
| tipo di fasce | quintili, finestra 365 giorni di barre passate |
| fascia attesa e segno | **Q5 (BTC è salita più dell'altcoin) → sopra il mercato (long)**; **Q1 → sotto il mercato (short)** |
| finestra e orizzonte | **versione A, scelta da Mattia il 27/10/2026:** finestra 1 ora, orizzonte **1 ora**. Su H4 la scheda non si misura (1 ora non è un numero intero di barre) |
| perché 1 ora (versione A, scelta) | Il meccanismo parla di un ritardo di minuti, ma un ritardo di minuti finisce dentro una barra M15: al Close della barra lo scarto è già in parte chiuso, e l'ingresso è all'Open della barra dopo. Con le candele M15 quel ritardo **non si vede**: servirebbero barre da un minuto o i singoli scambi. Quello che le M15 possono vedere è una versione **più lenta** dello stesso meccanismo: un'altcoin che in un'ora intera non ha seguito BTC (le meno liquide, o lo spot Bybit) e recupera nell'ora dopo. La versione A misura questa, ed è un'ipotesi diversa da quella dei minuti: va detto nel risultato |
| alternativa non scelta (versione B: finestra 1 barra M15, orizzonte 15 minuti) | Lo scarto nell'ultima barra da 15 minuti e la misura nei 15 minuti dopo: è la cosa più vicina ai minuti che i nostri dati vedono. Anche B non vede un ritardo più corto di una barra, per lo stesso motivo. Da sapere: un orizzonte di 15 minuti paga la stessa commissione di un trade di un'ora, quindi un trigger nato da B dovrà pagare i costi con un movimento più breve. Sui timeframe più lunghi di M15 (M30, H1, H4) B non si misura; su M5 sono 3 barre |
| mercato di riferimento | **stessa ora** (il mercato dell'altcoin) |
| cosa serve | il CSV di BTC dello stesso exchange e mercato; alla schermata 1 della mappa, entrambi nello studio (impronta), lo stesso confine |
| portabilità su TradingView | **sì** (un altro symbol) |
| dataset | ETH, SOL, XRP, perpetual e spot, Binance e Bybit. Non BTC |
| prove | **5** fasce per dataset (solo la versione A; la B non si misura) |

### M07 · Rendimento recente estremo

| campo | contenuto |
|---|---|
| stato | **approvata da Mattia il 27/10/2026**, segno **inversione** |
| meccanismo | Dopo una salita o una discesa molto forte in poche ore le liquidazioni a catena spingono il prezzo oltre il giusto, poi rientra: perde chi è stato liquidato al prezzo peggiore (**inversione**). Il meccanismo opposto, chi segue il trend ed entra dopo (continuazione), esiste ma non è l'ipotesi di questa scheda |
| da dove viene l'idea | Da `73` §B.6 («comportamento»). **In parte già visto sui dati:** nella rosa di BTC perp dei giri del 26/10 c'era E39_SHORT_HOUR_REVERSAL_DOWN, un'inversione di un'ora (paper Wen et al., `50` §10 riga 17). Il segno «inversione» è stato scelto dopo averla vista, fra due segni che il meccanismo permetteva. Il catalogo ha anche E41 (Liu e Tsyvinski, `50` §10 riga 19), un momentum sul rendimento della giornata: un'altra fonte, con il segno opposto, a un altro orizzonte. **Doppioni da controllare** nella PR B: E39 ed E41 |
| conto dell'idea già vista | Il segno è una scelta fra due fatta dopo aver visto E39: si conta come se si fossero misurate **tutte e due le versioni** (inversione e continuazione), cioè **5 + 5 = 10 fasce**. Le 5 della continuazione si contano anche se non si misurano |
| variabile | `rendimento_4h` (nuova): il rendimento delle ultime 4 ore, al Close della barra |
| tipo di fasce | quintili, finestra 365 giorni di barre passate |
| fascia attesa e segno | **inversione: Q5 → sotto il mercato (short)**; **Q1 → sopra il mercato (long)** |
| orizzonte | 4 ore |
| mercato di riferimento | **stessa ora** |
| cosa serve | solo le candele |
| portabilità su TradingView | **sì** (solo prezzo) |
| dataset | tutti |
| prove | **10** per dataset (5 misurate + 5 della versione opposta, per il segno scelto dopo aver visto E39) |

---

## 4 · Il registro

Una riga per scheda. Le colonne degli esiti si riempiono solo dopo la misura, con la
PR B; i risultati collaudano il tool, non sono verdetti sul mercato.

| scheda | stato | segno | idea già vista sui dati | prove previste per dataset | misurata su | esito | trigger nato |
|---|---|---|---|---|---|---|---|
| M01 ore del funding con il segno | approvata 27/10 | sì (positivo → short, negativo → long) | sì, profilo 2a (23:15 UTC): + 96 fasce | 2 + 96 = 98 | — | — | — |
| M02 giorno della settimana | fuori dalla prima versione | **no** | no | — | — | — | — |
| M03 apertura USA | fuori dalla prima versione | **no** | sì, profilo 2a (12:45 UTC) | — | — | — | — |
| M04 funding estremo | approvata 27/10 | sì (Q5 → short, Q1 → long) | no | 5 (0 se doppione di M05) | — | — | — |
| M05 basis estrema | approvata 27/10 | sì (Q5 → short, Q1 → long) | no (righe basis di E21 viste, non usate) | 5 | — | — | — |
| M06 BTC che anticipa le altcoin | approvata 27/10, versione A (1 ora) | sì (Q5 → long, Q1 → short) | no | 5 (solo altcoin) | — | — | — |
| M07 rendimento recente estremo | approvata 27/10 | sì, inversione (Q5 → short, Q1 → long) | sì, rosa (E39): + 5 della versione opposta | 5 + 5 = 10 | — | — | — |

**Conto della prima versione, per dataset**, se si misura tutto quello che è
approvato (M01, M04, M05, M06, M07):

| dataset | schede | fasce |
|---|---|---|
| perpetual BTC | M01 98 + M04 5 + M05 5 + M07 10 | **118** (113 se M04 è doppione) |
| perpetual ETH, SOL, XRP | M01 98 + M04 5 + M05 5 + M06 5 + M07 10 | **123** (118 se M04 è doppione) |
| spot BTC | M07 10 | **10** |
| spot ETH, SOL, XRP | M06 5 + M07 10 | **15** |

M05 si misura solo dove c'è lo spot della stessa coppia; dove manca, 5 fasce in meno.

## 5 · Decisioni di Mattia (27/10/2026)

1. **M02 e M03:** fuori dalla prima versione, perché il meccanismo non dà un segno.
   Si riaprono con una fonte che dia il segno.
2. **M07:** segno **inversione** (Q5 → sotto il mercato, Q1 → sopra), dichiarato come
   in parte già visto (E39 nella rosa). Il conto è preciso: 10 fasce (§3, M07).
3. **M01:** si contano le 96 fasce del profilo.
4. **M04 e M05:** si tengono tutte e due. Regola decisa prima di misurare: se il
   controllo DOPPIONI le trova troppo simili, si misura solo M05, che si porta su
   TradingView.
5. **Orizzonti:**
   - **M01:** una sola barra per pagamento, quella che chiude un'ora prima di 00:00,
     08:00 e 16:00 UTC, con orizzonte 1 ora, così la misura finisce al pagamento.
     Variabile, fasce e prove aggiornate (§3, M01).
   - **M06:** **versione A** (finestra 1 ora, orizzonte 1 ora), decisa da Mattia il
     27/10/2026 dopo aver letto la riga «perché 1 ora». La scheda dice che A misura la
     versione lenta del meccanismo (un'altcoin che in un'ora non ha seguito BTC), non
     il ritardo di minuti. La versione B (una barra M15) resta descritta come
     alternativa non scelta. Variabile `scarto_btc_1h`, prove 5 per dataset.
6. **M01:** scritto nella scheda che su BTC il funding è quasi sempre positivo: la
   fascia «funding positivo» è quasi il riferimento e il suo scarto sarà vicino a
   zero per costruzione; l'informazione sta nella fascia «funding negativo», con
   pochi casi.
