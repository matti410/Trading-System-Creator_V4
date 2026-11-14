# 00 · Scopo del progetto e stato attuale

**Da leggere per primo, insieme a `CLAUDE.md`.** Stato al 4 novembre 2026 (dopo il catalogo
dei trigger intraday, `79`, PR #97, e con la confidenza in ore e la 5b del Lab, `81`).
Questo file è solo lo **stato attuale**, in 1–2 pagine. Riferimenti completi e
storia (regole del metodo passo per passo, moduli e firme, catalogo, «Cosa
manca AL TOOL» punti 1–8, scoperte, il resoconto «Dove siamo» fino al 21/10)
stanno in `00_ARCHIVIO.md`: si apre solo se il lavoro lo richiede. Le proposte delle fasi chiuse `71`, `73`, `79`,
`81` stanno in `docs/archivio/`; ogni rimando a quei numeri vale per quella cartella.

**Incarico in corso (05/11/2026): `81_FABBRICA`** (`81_FABBRICA_STRATEGIE.md`), la fabbrica di strategie. Proposta in
`82_PROPOSTA_FABBRICA_STRATEGIE.md`, un ramo per lavoro (L1–L5b, `82` §9). Il suo notebook,
`Fabbrica_Strategie_Crypto.ipynb` (L5b), è lanciato sui dati veri dal 09/11. Stato al 10/11 (PR #109, #110 e
registro senza catena): la cella 1 aggiorna i dati dall'exchange a ogni avvio, pezzi fino all'ultima mezzanotte UTC
chiusa; la cassaforte non ha limiti di ingresso e la cella 5 non chiede frasi; il registro è un file di annotazioni,
senza catena di impronte. Dal 14/11 (C1, PR #113; C2, `82` §11): la config standard ha tutto il catalogo (45 trigger,
30 filtri, 3 uscite; versione 2, le ricerche della versione 1 restano su disco e nel conto); all'avvio un blocco per
famiglia misurata; il passo 1 in due turni (turno 1: al massimo un filtro; turno 2: un secondo filtro alle 150 migliori);
tetto del budget = il massimo arrotondato in su ai 10.000; la cella 1 stima il tempo dalla velocità delle ricerche vere.
Regola di progetto: la pipeline il più semplice possibile (`CLAUDE.md`). **Eccezione: in
`engine/fabbrica/` i parametri si ottimizzano (`docs/81_FABBRICA`).** Il catalogo dei trigger intraday (`78`, `79`) è unito (PR #97): 12 trigger nuovi
E46–E52, E50 spento come doppione di E3.

## Il progetto

- **Uno strumento per scovare strategie di trading**: una base che cresce con
  condizioni di ingresso, filtri, uscite, diagnostiche. Non è la ricerca di un
  edge su un symbol.
- **Perimetro, dal 20/10 (`63` §10.0): solo crypto da exchange** — Binance e
  Bybit, spot e perpetual, BTC, ETH, SOL, XRP, M15 dal 2/1/2020 (anche M5–H4).
  Il lato broker (MT5, CFD, i 9 symbol del broker) è **sospeso**: resta nel
  repo, non si sviluppa e non si usa per misurare.
- **Dataset di sviluppo e di identità:** BINANCE_PERP_BTCUSDT. **Giro di
  controllo:** BYBIT_SPOT_ETHUSDT (altro exchange, spot, solo long).
- **Notebook vivi, sempre allineati:** `Trading_System_Lab_Crypto.ipynb` (Lab
  guidato, nove schermate, chiama `engine/vetrina.py`) e
  `Trading_Grid_Search_v4_backtesting.ipynb` (ricerca). Il collaudo del
  catalogo è in `Collaudo_Catalogo.ipynb`. La fabbrica ha il suo notebook, separato e non allineato agli altri,
  `Fabbrica_Strategie_Crypto.ipynb` (chiama `engine/vetrina_fabbrica.py`). La mappa delle anomalie ha il suo notebook,
  `Mappa_Anomalie_Crypto.ipynb` (chiama `engine/vetrina_mappa.py`; il Lab ne mostra gli
  esiti alla 2b). `archivio/Trading_System_Lab.ipynb` (broker) è sospeso. Girano in locale e su Colab (Drive); in locale i dati stanno nella cartella
  di Google Drive per desktop se c'è (streaming, offline solo la cartella del progetto),
  altrimenti in `dati/`.
- **Repo (pubblico):** `github.com/matti410/Trading-System-Creator_V4`.

## LA REGOLA CHE VIENE PRIMA DI TUTTE

> **I risultati sui dati non sono il metro di giudizio del progetto.**

Servono a collaudare il tool (il codice gira, le occorrenze sono plausibili, i
segni coerenti) e si riportano come collaudo, non come verdetto. Non si
commenta se un sistema «tiene», non si propone di cambiare asset, famiglia di
segnali o approccio, non si scrivono conclusioni tipo «capitolo chiuso». La
decisione di ricerca è di Mattia.

## Il metodo in sette passi

Ogni passo riceve **congelato** quello che hanno scelto i passi prima; ogni
scelta «il migliore fra tanti» è una prova in più (soglia di rumore, `02`).
Regole complete di ogni passo: `00_ARCHIVIO.md`, «Il metodo».

| passo | cosa si decide | dove (ricerca · Lab) |
|---|---|---|
| 1 | orizzonte H | event study · Lab 1–2 |
| 2 | ingressi (la rosa li suggerisce) | event study, `rosa_entry` · Lab 3a–3b |
| 3 | uscite; stop e target adattivi, mai ottimizzati | `exit_search_bt`, `rosa_sistemi` · Lab 4–4b |
| 4 | giudizio: il tool automatizza solo la bocciatura | `giudizio.py` |
| 5 | filtri, un'idea alla volta, tenuti contro scartati, due metà | `filter_search_bt`, `due_meta`, `confidenza` · Lab 5 e 5b |
| 6 | out-of-sample, aperto una volta sola | Sessione 4 · Lab 6 |
| 7 | Monte Carlo, money management (calibrato sull'in-sample) | `montecarlo`, `money_management` · Lab 7 e 9 |

## Cosa vale oggi

- **Giornata delle crypto da 00:00 a 00:00 UTC** (`63` §10.1); gli orari presi
  dalle fonti restano alle 17:00 di New York.
- **Unità che decide: il bp** sui symbol da exchange (parametro `unita`); pips e
  ATR accanto; totale, drawdown e money management in pips, stress test in bp
  sulle crypto, in pips sul broker (PR #55) (`02`, «Unità»; `63` §4).
- **Costi:** commissione taker di listino, livello base, più uno spread di un
  passo **per trade** (`71`, 25/10): fuori dal prezzo di fill, un passo in
  `CostoExtraPips` nei due motori, fisso in pips, passo / prezzo d'ingresso in bp; la
  confidenza usa il costo della barra del segnale (Close); sui perpetual il **funding** trade per trade, acceso di default (`63`
  §5). Leva mai oltre il tetto italiano (perpetual 2, spot 1).
- **Motore di backtest:** «veloce» (`engine/motore_veloce.py`, numba) è il
  predefinito; «bt» (`backtesting.py`) resta e fa da oracolo dei test. Due
  differenze dichiarate: con «veloce» stop e target sono attivi già sulla
  barra d'ingresso (serve `lag` ≥ 1), e quando il capitale simulato si
  esaurisce «veloce» tiene i trade e avvisa con la data (`65`). Nei test,
  `comportamento_vecchio()` riporta «veloce» identico al bit a «bt».
- **Mercato nullo sospeso** (`63` §10.3): il codice resta, fermo.
- **Lab, schermate 2→4 riordinate** (`67`, `68`, 25/10): un metro solo dalla 2 alla 4
  (scarto dal mercato della stessa ora, in bp); 2a profilo orario, 2c curve dello
  scarto, 3a rosa con la classifica a scomparsa, 3b casistiche dalla rosa («togli» /
  «aggiungi»), la cella dentro la casistica, 4 uscite consigliate (barre = H, stop 90,
  target spento, picco solo da leggere), 4b il sistema che va al passo 5. Riga delle
  prove su ogni schermata; dopo la scheda le scelte rifatte si segnalano.
- **L'orizzonte H lo dichiara l'utente prima di guardare i dati.** Il 41 che il Lab
  propone (e il 25 del notebook di ricerca) è un valore di collaudo messo da Mattia
  senza motivazione: serve solo alle prove d'identità, non è una scelta di ricerca.
- **Rosa dei trigger** (25/10): la correlazione (|rho| ≤ 0,3) si controlla solo fra
  trigger dello stesso lato; un long e uno short legati in negativo non sono doppioni
  e la loro convivenza si misura alla 4b, sui trade veri. Notebook di ricerca:
  `X_INVERSIONE_TREND` con il profilo nell'unità che decide (bp sulle crypto), come il Lab.
- **Dati in locale** (`70`, 25/10): l'interruttore «aggiorna i dati» dell'Avvio
  scarica, solo sul PC, le barre nuove del symbol e del timeframe scelti alla
  schermata 1 (con il funding del perpetual; lo spot della stessa coppia non più dal 29/10, `77`); su Colab si leggono i file di Drive.
  Stesso codice di `scarica_dati_crypto.py` (`engine/aggiorna_dati.py`).
- **Il confine dell'in-sample è dello studio** (`70` §2): una data sola per tutti gli
  exchange, le monete e i timeframe, fissata dal primo dataset aperto all'80% delle sue
  barre e salvata in `studio/confine.json` accanto ai dati. Non si muove più: le barre
  nuove vanno tutte nell'out-of-sample. Si ricalcola solo scrivendo la data di oggi in
  `ricalcola_confine` (solo sul PC; lo studio va in archivio; indietro solo su uno
  studio dove non si è ancora misurato né guardato niente). Un'impronta controlla che
  le barre dell'in-sample non cambino. Il notebook di ricerca usa lo stesso studio sui
  symbol da exchange; `confine="80%"` è la regola di prima, solo per le prove d'identità.
- **Registro per dataset** (`68` §9.1): symbol, timeframe e confine dell'in-sample.
  Cambiare H sullo stesso dataset non azzera conto e diario dell'out-of-sample, si
  segnala e si conta (`soglia_rumore_orizzonte` sugli H provati). Dal 25/10 (`70` §3-§4)
  si salva nei giornali dello studio, uno per macchina e solo in aggiunta (PC e Colab
  non scrivono mai lo stesso file): resta anche dopo il riavvio.
- **Mappa delle anomalie** (`73` parte B, schede in `74`; PR #82 engine, PR successiva
  notebook): una scheda dice prima di guardare i dati in quale fascia di una variabile il
  prezzo dovrebbe fare meglio o peggio del mercato della stessa ora, e in che verso. Si
  misura sull'in-sample dello studio nel notebook della mappa, con lo stesso cancello
  della rosa (falsi positivi q = 20%, due metà, 200 barre in 100 giornate). Prima della
  misura il controllo delle fasce (quintili fra il 10% e il 30%); M04, fermata da quel
  controllo, è stata riscritta a categorie del funding il 28/10 prima di misurarla. Dal 29/10 (`77`, lavoro 1) le schede del
  funding e della basis (M01, M04, M05) sono tolte: restano M06 e M07; gli esiti già misurati restano visibili con la
  nota e le loro fasce nel conto. Ogni fascia misurata è una prova nel conto del dataset (voce «prova» con
  dove = "mappa" nel giornale): il Lab la conta nella soglia cumulata e nella riga delle
  prove, e la mostra alla 2b in sola lettura. Il notebook della mappa non scrive H e non
  apre lo studio. Dal 28/10 la mappa ha la sua incertezza (`mappa.errore_sovrapposti`): le coppie di
  barre più vicine dell'orizzonte pesano per intero, senza lo sconto di `scarto_orario`, che il Lab
  continua a usare (sezione G di `test_mappa.py`). Dal 30/10 il notebook della mappa è semplice (solo
  presentazione, i calcoli sono gli stessi): 1 · Il dataset (tre righe), 2 · Misura (per ogni scheda nome in
  chiaro, semaforo, una frase con i numeri per fascia attesa, grafico; poi «Cosa ti porti a casa» con il trigger
  da usare nel Lab), Dettagli facoltativa con tutto quello di prima. La 2 misura una scheda solo la prima volta,
  poi mostra l'ultimo esito: premere ▶ due volte non aggiunge prove (sezione H di `test_mappa.py`).
- **Il conto delle prove** (`76`, 28/10): per ogni chiave vale il numero più alto mai scritto, nel Lab e
  nella ricerca. Il notebook di ricerca scrive nello studio le stesse voci del Lab (trigger, fasce,
  situazioni, uscite, filtri; la 2.3 e la 3.3 con una chiave loro), con le stesse chiavi, e la sua soglia
  cumulata legge il conto dallo studio. Sullo spot misura solo i long, come il Lab.
- **Le prove d'identità** (Mattia, 29/10/2026, `77` §P8): una prova conta da quando se ne vede il risultato.
  Le prove d'identità che mostrano risultati con chiavi nuove (un trigger nuovo, un H mai provato sul dataset,
  un atlante con trigger in più) si fanno sullo **studio vero**, mai su una copia. Su una copia solo i giri che
  mostrano chiavi già contate.
- **La griglia volatilità × trend** (`81`, 04/11/2026), una sola per la confidenza e per l'atlante
  (`indicatori.cella_vol_trend`). Finestre in ore: 5 ore la deviazione, almeno 20 barre; la mediana dei due assi copre il
  maggiore fra 125 ore e 5 periodi di ancora. VWAP e regressione di `gap_trend` ripartono dal periodo più corto con almeno
  20 barre: fino a H1 la giornata, su H4 la settimana (lunedì 00:00 UTC), su D1 il mese. Su M15 tutto come prima, al bit;
  su M5, M30 e H1 cambia la confidenza; su H4 la confidenza e l'atlante. D1 non si apre nel Lab.
- **La confidenza nel Lab, schermata 5b** (`81`): facoltativa, spenta di default (nessun calcolo, nessuna prova), saltata
  nella strada B. Soglie fisse `SOGLIE_CONFIDENZA` (0, 0,5 e 0,8 volte il costo), le stesse della 3.3 con la stessa chiave
  del conto. Solo in-sample; alla 6 si scrive una soglia che supera le due prove, con lo stesso filtro della 5b, e la scheda
  mostra anche la curva out-of-sample con e senza confidenza. Le schermate 7, 8 e 9 ricevono i trade con la confidenza.
- **Versioni bloccate:** `TA-Lib==0.8.1`, `backtesting==0.6.6`, `numba==0.68.0`.
- **Test:** `python suite_rapida.py` durante il lavoro (le suite del codice
  cambiato, 2–3 minuti); **prima di ogni Pull request** `python suite_rapida.py
  --tutte`, 62 suite, 3 alla volta, circa 28 minuti; alla fine deve stampare
  «SUITE COMPLETA: n/n» con n = totale.
- **Catalogo:** 143 condizioni (85 entry, 38 filtri, 10 uscite, 10
  entry-metro); dalle fonti testuali 65 prove (+12 dei trigger intraday E46–E52, 02/11, `79`), dalla mappa 2 (E45,
  scheda M07, 29/10), registro in `50` §10. Doppioni con `famiglie.py` sull'in-sample dello studio dei dataset crypto
  (`50` §7 punto 5).

## Prossimi lavori, in ordine (Mattia, 21/10), un ramo ciascuno

1. **Stop e target sulla barra d'ingresso** — fatto (PR #49): con il motore
   veloce stop e target sono attivi dall'Open della barra d'ingresso; «bt»
   resta l'oracolo del comportamento vecchio.
2. **`confidenza.py` in bp** — fatto (PR #50): parametro
   `unita`; in bp le soglie sono multipli del costo andata e ritorno
   (`CONF_BP_MEDI_0.5C`), in pips tutto come prima (`02`, «Unità»).
3. **`top()` ordinato per il t nell'unità che decide** — fatto (PR #51): la tabella delle uscite e `top()` ordinate per `t_stat`
   (bp sulle crypto, pips sul broker), `sharpe` solo informativo.
4. **Soglia cumulata nel Lab** — fatto (PR #52): Šidák
   sul totale delle prove della catena (trigger, uscite, filtri,
   combinazioni di filtri), sotto la scheda al posto della riga del mercato
   nullo; solo informativa. Anche nel notebook di ricerca
   (`vetrina.soglia_cumulata`).
5. **C · atlante del trigger** — fatto (PR #53; lo stato aggiornato in
   questo file con la PR #54, solo testo; proposta e decisioni in `66`).
   Per ogni entry vera, 8 celle per lato (10 sui perpetual con lo spot fino al 29/10, poi la basis è tolta, `77`): scarto lordo dal mercato della cella e netto dei costi (`02`,
   «L'atlante del trigger»). Lab 3c–3d, ricerca 1.5. Con una cella scelta
   (strada B) il passo 5 prova solo la cella, con la soglia a k = celle
   dell'atlante; senza cella tutto come prima.
6. **Money management P1–P4 e stress test in bp** — fatto (PR #55;
   resoconto in `61` §15). P1: la percentuale rispetta
   il limite di drawdown anche sui tratti di storia vera in-sample lunghi
   quanto l'orizzonte; P2: avviso oltre Kelly; P3: confronto con la stessa
   esposizione a ogni trade a parità di drawdown sfortunato; P4: decimali
   dei lotti dal passo dell'exchange. Stress test delle crypto in bp per
   trade, lotti dal prezzo dell'ultima barra; broker in pips come prima.

7. **Orari e uscite per lato** — fatto (PR #57; resoconto in `66` §15). L'atlante misura anche i trigger scelti fuori
   catalogo (quelli a orario contro il mercato della cella a qualunque ora);
   stop, target e regola d'uscita per lato nella schermata 4 e nel notebook
   di ricerca; profilo orario 2b in bp sulle crypto; nella soglia cumulata le
   fasce del profilo con un trigger a orario; avviso sulla durata con trigger
   a orario sui due lati.

8. **Riordino della pipeline del Lab, schermate 2→4** — fatto (PR #63, motore e
   test; PR successiva, Lab e notebook di ricerca). Incarico `67`, proposta e
   resoconto in `68`.

9. **Dati in locale e confine dello studio** — fatto (PR #69, engine e test; PR
   successiva, `prepara`, Lab e notebook di ricerca). Incarico `69`, proposta,
   decisioni e resoconto in `70`.

L'out-of-sample «fresco» (`70` §13) è fatto (25/10): la scheda e la Sessione 4 della ricerca
mostrano anche i numeri del solo tratto mai guardato (dopo l'ultima apertura del diario, su
qualunque dataset dello studio; i trade a cavallo della data restano fuori).

Prossimi lavori, in ordine (Mattia, 26/10, `72` §B.2): il Lab più chiaro (parte A di `73`) — fatto
(PR #77, #78); poi la mappa delle anomalie (parte B di `73`: un notebook a parte, il posto 2b del Lab in
sola lettura) — fatta (PR #82 e la successiva, primo giro sullo studio il 28/10); il volume aggressivo
dopo la mappa, come variabile in più. Orizzonti multipli in un lavoro a parte (`68` §13). Il conto
delle prove fra dataset si decide nel lavoro dei testimoni.

**Direzione dal 29/10/2026 (`77`):** edge direzionali intraday sul prezzo (e sul volume), trade da 1 a
8 ore; niente edge da meccanica dello strumento (funding, basis). Lavori in ordine: 1) togliere funding e basis
come variabili; 2) orizzonti 1, 4 e 8 ore; 3) trigger M07; 4) volume aggressivo. Proposta in `77` §P1–§P3,
decisioni di Mattia in `77` §P4. Lavoro 1 fatto (29/10, `77` §P5): il funding resta solo come costo dei trade sui
perpetual; via il funding come variabile, l'asse basis dell'atlante e le schede M01, M04, M05. Le situazioni già
misurate con la basis non si contano di nuovo. Lavoro 2 fatto (29/10, `77` §P6): l'orizzonte predefinito è la
griglia di 1, 4 e 8 ore (in barre secondo il timeframe); la 2c del Lab (la 1.3 della ricerca) mostra i trigger ai tre
orizzonti e l'H si sceglie dopo averli visti. I tre H entrano subito fra gli H provati del dataset: la voce dei
trigger vale la scelta fra loro (circa tre volte il numero dei trigger). Un orizzonte solo, in barre, resta
possibile (prove d'identità: 41 nel Lab, 25 nella ricerca). Lavoro 3 fatto (29/10, `77` §P7): il trigger M07,
E45 long (il rendimento a 4 ore entra nel quintile più basso) e short (nel più alto), con le soglie della scheda;
le situazioni dell'atlante con la regola (b) (si contano solo quelle dei trigger nuovi). Con la griglia la 2a mostra
il profilo una volta sola, dopo la scelta dell'orizzonte.

Fonti: una alla volta con il processo di `50`; la coda dei paper è in
`GUIDA_ANALISI_FONTI.md` §11.6.

## Problemi aperti

| cosa | stato |
|---|---|
| rosa, atlante e 2c usano l'incertezza di `scarto_orario` con lo sconto (pesi decrescenti) sui rendimenti sovrapposti: può sottostimarla per i trigger con ingressi vicini e orizzonti lunghi (vedi collaudo della mappa del 28/10) | risolto (docs/75, PR della correzione, 28/10): un calcolo solo, quello della mappa |
| il notebook di ricerca non scrive le sue prove nel giornale dello studio (solo l'ingresso del dataset, l'orizzonte e le aperture dell'out-of-sample): quello che misura non entra nel conto. Esempio: la prova su BYBIT_SPOT_ETHUSDT del 25/10 (66 trigger) non è nel conto | risolto per le prove nuove (docs/76, PR 1, 28/10): la ricerca scrive le stesse voci del Lab, con le stesse chiavi; per ogni chiave vale il numero più alto. Le prove passate (A3) scritte nello studio il 28/10, approvate da Mattia (docs/76 §3) |
| sullo spot il notebook di ricerca misura anche i trigger short e il Lab no: le chiavi dei due notebook (trigger e celle) non combaciano | risolto (docs/76, PR 1, 28/10): sullo spot la ricerca misura solo i long, gli stessi trigger del Lab |
| strada B: con il filtro vuoto la schermata 6 prova il segnale da solo con le uscite costruite sul segnale dentro la situazione; proposta da decidere: con una situazione scelta il predefinito della 6 diventa il segnale dentro la situazione | risolto (docs/76, PR 2, 28/10): con una situazione il filtro vuoto alla 6 è il segnale dentro la situazione |
| stop e target non attivi sulla barra d'ingresso | risolto (PR #49) |
| `ExitSearchBT.top()` ordina per `sharpe`: va ordinato per il t nell'unità che decide | risolto (PR #51) |
| `vwap_ops.py` taglia la giornata a mezzanotte UTC: sulle crypto coincide con la giornata, sul broker (sospeso) no | da decidere se si riapre il broker |
| il notebook di ricerca su Colab chiede il secret `GITHUB_TOKEN` | risolto (docs/76, PR 2, 28/10): i quattro notebook clonano il repo pubblico, il token solo se serve |
| interruttore sulla curva dei profitti | rimandato da Mattia |
| schermata 4: la tabella dice «short dopo 41 barre» anche con lo short spento | risolto (docs/76, PR 2, 28/10) |
| schermata 4: «confronta le tre righe» anche quando la tabella ne ha una sola | risolto (docs/76, PR 2, 28/10) |

## Convenzioni di lavoro

- **Metodologia prima, codice dopo.** I lavori grandi: proposta in `docs/`,
  via libero di Mattia, poi codice. **I lavori piccoli: niente proposta in
  `docs/`**, una descrizione breve in chat, il via, poi il codice.
- **Niente aggiunte non richieste**: ciò che va oltre si propone.
- **Ogni pezzo di codice passa un collaudo** con casi a risultato noto.
- **Modifiche all'engine il più possibile additive**; se non lo sono, si dice.
- **Consegna:** ramo, test, Pull request; il merge lo fa sempre Mattia.
- **Sempre spiegare come si esegue.** Mattia non è un informatico.
