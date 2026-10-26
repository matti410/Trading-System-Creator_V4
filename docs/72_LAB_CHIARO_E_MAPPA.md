# 72 · Incarico: Lab più chiaro (A) e mappa delle anomalie (B)

**Data:** 26 ottobre 2026
**Stato:** INCARICO DI STUDIO. **Nessun codice** prima dell'OK di Mattia.
**Consegna attesa:** `docs/73_PROPOSTA_LAB_CHIARO_E_MAPPA.md`, in due parti:
A (le modifiche al Lab, testi in bozza compresi) e B (il notebook della mappa).
Le risposte alle domande del §6. Il codice va in due Pull request, prima A poi B.
**Da leggere prima:** `CLAUDE.md`, `docs/00`; `docs/68` (riordino, casistiche,
posto libero prima della rosa); `docs/70` (studio, confine, giornali);
`docs/66` §4–§6 (atlante, strada B); `docs/50` (processo per le condizioni
nuove, registro delle idee); `engine/vetrina.py` (schermate 2–5);
`engine/rosa.py`; `engine/atlante.py`; `engine/stagionalita.py`;
`engine/event_study.py`; `engine/studio.py`; le celle 2–5 di
`Trading_System_Lab_Crypto.ipynb`.

---

## 0 · Perché

Il tool oggi **valida** bene un'idea: le dice se ci si può costruire una
strategia sopra. Manca il passo prima: **un protocollo per scoprire dove
cercare**. Oggi le idee arrivano una alla volta dalle letture (registro di
`50` §10). Il protocollo è la **mappa delle anomalie** (parte B), in un notebook
suo. Prima però il Lab, che deve ricevere i trigger nati dalla mappa, va reso
più chiaro: oggi è ancora difficile da capire anche per chi l'ha costruito
(parte A).

---

## PARTE A · Lab più chiaro

### A.1 · Testi da riscrivere (decisioni di Mattia del 26/10)

**Schermata 2.** Il testo di oggi confonde, soprattutto la frase «rispetto a
un ingresso qualunque alla stessa ora», che **va tolta**. Testo deciso:

> **2 · Esplora.** Prima guardiamo il mercato da solo, poi i segnali.
>
> **2a · Il mercato ora per ora.** In alcune ore del giorno il prezzo tende a
> salire o scendere più del solito. Qui vedi quanto, ora per ora. Ci serve come
> termine di paragone: un segnale vale qualcosa solo se fa meglio di quello che
> il mercato fa già da solo a quell'ora.
>
> **2c · I segnali contro il mercato.** Ogni linea è un segnale. Mostra, barra
> dopo barra dall'ingresso, quanti bp guadagna in più (sopra lo zero) o in meno
> (sotto lo zero) del mercato. Una linea che sale e resta sopra lo zero indica
> un segnale che aggiunge qualcosa al mercato.

I titoli dei grafici e le note sotto la 2c vanno allineati a questo testo.

**Schermate 3c e 3d (atlante e cella).** Testo deciso:

> **3c · Dove funziona il segnale (facoltativo).** Lo stesso segnale può
> funzionare bene in certe condizioni di mercato e male in altre. L'atlante
> divide la storia in situazioni (volatilità alta o bassa, trend a favore o
> contro, la sessione: Asia, Europa, Londra+New York, America; sui perpetual la
> basis alta o bassa) e mostra per ognuna se il segnale fa meglio del mercato e
> se paga i costi.
>
> **3d · Scegli una situazione (facoltativo).** Se ne scegli una, il segnale
> scatterà solo lì. È una scelta in più fatta sui dati: per questo l'asticella
> della solidità tiene conto di tutte le situazioni che l'atlante ha guardato.

Le intestazioni delle tabelle dell'atlante vanno rese leggibili con lo stesso
linguaggio (nomi delle celle in chiaro, «batte il mercato», «paga i costi»).

**Schermata 5 con una cella scelta.** Il comportamento **resta com'è** (strada
B di `66`): la cella è già un filtro, quindi al passo 5 si misura solo lei
(trigger con la cella contro trigger senza), e gli altri filtri non si provano.
Oggi non è chiaro: il testo della schermata 5 e la sua tabella devono dirlo
esplicitamente, con il perché (la cella è un filtro scelto sui dati: provarne
altri sopra vorrebbe dire scegliere due volte).

### A.2 · La 3b: scegliere davvero le casistiche

Oggi il campo «aggiungi» accetta qualunque trigger del catalogo, ma la
schermata non lo dice. In più la rosa propone una casistica per famiglia, e
spesso ne resta una sola. Decisioni di Mattia:
1. **Un campo «parti da»** con tre scelte:
   - **la rosa**, come oggi (predefinito);
   - **tutte le candidate**, cioè tutte quelle che passano i controlli della
     rosa, anche se escluse per famiglia o correlazione;
   - **niente**, quando si sceglie da zero con «aggiungi».
2. **Il testo dice in chiaro** che in «aggiungi» va bene qualunque trigger del
   catalogo, e dove trovarne i nomi (la classifica a scomparsa della 3a).
3. Togliere, aggiungere o cambiare punto di partenza **non aggiunge prove**
   (`67` §3.5): i trigger sono già contati alla 2c.

Resta com'è: più trigger sullo stesso lato lavorano in OR. Provarli uno alla
volta, ciascuno con le sue uscite, è il lavoro del portafoglio di sistemi
(rimandato). Il testo della 3b lo dice, e dice che oggi si fa rieseguendo la
3b con un trigger diverso.

### A.3 · La 3d: anche celle che non passano la soglia

Decisione di Mattia: si può scegliere **qualunque cella misurata
dall'atlante**, anche se non passa la soglia.
- **Nessuna prova in più:** l'atlante conta già tutte le celle che misura.
- **Resta il minimo di 200 occorrenze** nella cella (`MIN_TRIGGER`): sotto, la
  cella non si può scegliere e il messaggio dice perché.
- **Avviso** quando la cella non passa: «nell'in-sample questa situazione non
  batte il mercato, o non paga i costi: la scegli sapendolo».

### A.4 · Vincoli della parte A
- A scelte uguali i numeri non cambiano: prove d'identità sui due notebook,
  BINANCE_PERP_BTCUSDT e BYBIT_SPOT_ETHUSDT.
- Il notebook di ricerca segue le stesse regole della 3b e della 3d.
- I testi si rivedono con Mattia prima del merge.

---

## PARTE B · La mappa delle anomalie

### B.1 · Cos'è

Oggi il tool parte dai trigger (regole già scritte) e chiede se funzionano.
La mappa rovescia l'ordine: chiede **dove il mercato smette di essere
casuale**, e solo dopo si scrive la regola.
1. **Scheda dell'ipotesi, scritta prima di guardare i dati:** meccanismo (chi
   è costretto a perdere, e perché), variabile, **segno atteso**, orizzonte
   atteso (in ore).
2. **La mappa:** la variabile si divide in 5 fasce (quintili calcolati solo
   con dati passati) e per ogni fascia si misura il rendimento futuro contro
   il mercato, all'orizzonte atteso.
3. **Il verdetto della scheda:** la fascia risponde nel verso atteso, oppure
   no. Un segno opposto **non conta come scoperta**.
4. **Il ponte verso il Lab:** la fascia che risponde diventa un trigger del
   catalogo, con il processo di `50`, e da lì segue la catena di sempre.

### B.2 · Decisioni di Mattia (26/10/2026)
1. **Un notebook a parte**, `Mappa_Anomalie_Crypto.ipynb`. Lab = validazione,
   mappa = scoperta: due mestieri diversi. La mappa può aver bisogno di più
   dataset insieme (BTC che anticipa le altcoin, perpetual contro spot).
2. **Nessuna logica nel notebook:** tutto nell'engine, come per Lab e ricerca.
3. **Stesso studio, stesso confine, stessi giornali** (`70`). La mappa lavora
   **solo sull'in-sample**, e le prove che fa entrano nel conto dello studio:
   un trigger nato dalla mappa arriva al Lab con le sue prove già contate.
4. **Nel Lab** il posto libero prima della rosa (`68` §1) mostra, **in sola
   lettura**, le schede già misurate su quel dataset.
5. **Il volume aggressivo** viene **dopo** la mappa, come variabile in più.
6. **Etichetta di portabilità** su ogni variabile e su ogni trigger nato dalla
   mappa: «si porta su TradingView: sì / approssimata / no» (TradingView vede
   prezzo, volume, orari, altri symbol; non vede funding, open interest, book).

### B.3 · I primi meccanismi da mappare (con i dati di oggi)

| meccanismo | variabile, per esempio |
|---|---|
| calendario | ore del funding (00/08/16 UTC), giorno della settimana, weekend, venerdì delle opzioni, scadenze trimestrali, apertura USA |
| posizionamento e leva | funding estremo, basis |
| chi arriva prima | rendimento recente di BTC per le altcoin; perpetual contro spot; un exchange contro l'altro |
| comportamento | rendimento delle ultime ore in fascia estrema; distanza dai massimi o minimi recenti |
| regime | volatilità recente |

La proposta dice quali entrano nella prima versione e quali dopo.

### B.4 · Vincoli della parte B
- Niente lookahead: fasce e variabili al Close della barra, quintili su sole
  finestre passate; collaudo per troncamento, come per l'atlante.
- Il conto delle prove resta onesto: ogni variabile, fascia e orizzonte
  misurati si contano; un orizzonte diverso da quello della scheda è una
  scelta e si conta (logica di `68` §13).
- I risultati collaudano il tool, non sono verdetti sul mercato.
- Unità: bp, pips accanto. Timeframe da M5 a H4, orizzonti in ore.
- Test a risultato noto per ogni pezzo nuovo; suite completa prima di ogni PR.

---

## 5 · Cosa NON cambia
Motore, rosa, uscite, filtri, scheda, money management, stress test, studio
e confine. Il broker resta sospeso.

## 6 · Domande aperte (la proposta risponde, Mattia decide)
1. **Il termine di paragone della mappa:** il mercato della stessa ora (come la
   rosa) o il mercato a qualunque ora? Per le variabili di calendario il primo
   darebbe zero per costruzione.
2. **La misura di una fascia:** scarto in bp, solidità, due metà, controllo
   della quota di falsi positivi (come la rosa)? Quanti eventi minimi?
3. **Dove vivono le schede delle ipotesi:** un file nello studio, un registro
   in `docs/` come `50` §10, o entrambi?
4. **Come si conta:** variabili × fasce × orizzonti, e come si passa il conto
   al Lab quando un trigger nasce dalla mappa.
5. **Le variabili fra dataset** (BTC per le altcoin, spot per il perpetual):
   come si allineano le barre, e cosa succede se un dataset ha storia più corta.
6. **Dalla fascia al trigger:** automatico (il notebook propone il trigger da
   aggiungere al catalogo) o sempre con il processo di `50`?
7. **Tempi** di calcolo per una variabile e per l'intera prima versione.