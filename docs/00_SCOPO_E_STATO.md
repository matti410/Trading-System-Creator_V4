# 00 · Scopo del progetto e stato attuale

**Da leggere per primo, insieme a `CLAUDE.md`.** Stato al 26 ottobre 2026 (dopo i dati in
locale e il confine dello studio, `70`, PR #69 e la successiva).
Questo file è solo lo **stato attuale**, in 1–2 pagine. Riferimenti completi e
storia (regole del metodo passo per passo, moduli e firme, catalogo, «Cosa
manca AL TOOL» punti 1–8, scoperte, il resoconto «Dove siamo» fino al 21/10)
stanno in `00_ARCHIVIO.md`: si apre solo se il lavoro lo richiede.

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
  catalogo è in `Collaudo_Catalogo.ipynb`. `Trading_System_Lab.ipynb` (broker)
  è sospeso. Girano in locale e su Colab (Drive); in locale i dati stanno nella cartella
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
| 5 | filtri, un'idea alla volta, tenuti contro scartati, due metà | `filter_search_bt`, `due_meta`, `confidenza` · Lab 5 |
| 6 | out-of-sample, aperto una volta sola | Sessione 4 · Lab 6 |
| 7 | Monte Carlo, money management (calibrato sull'in-sample) | `montecarlo`, `money_management` · Lab 7 e 9 |

## Cosa vale oggi

- **Giornata delle crypto da 00:00 a 00:00 UTC** (`63` §10.1); gli orari presi
  dalle fonti restano alle 17:00 di New York.
- **Unità che decide: il bp** sui symbol da exchange (parametro `unita`); pips e
  ATR accanto; totale, drawdown e money management in pips, stress test in bp
  sulle crypto, in pips sul broker (PR #55) (`02`, «Unità»; `63` §4).
- **Costi:** commissione taker di listino, livello base, più uno spread di un
  passo; sui perpetual il **funding** trade per trade, acceso di default (`63`
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
- **Rosa dei trigger** (26/10): la correlazione (|rho| ≤ 0,3) si controlla solo fra
  trigger dello stesso lato; un long e uno short legati in negativo non sono doppioni
  e la loro convivenza si misura alla 4b, sui trade veri. Notebook di ricerca:
  `X_INVERSIONE_TREND` con il profilo nell'unità che decide (bp sulle crypto), come il Lab.
- **Dati in locale** (`70`, 26/10): l'interruttore «aggiorna i dati» dell'Avvio
  scarica, solo sul PC, le barre nuove del symbol e del timeframe scelti alla
  schermata 1 (con spot e funding del perpetual); su Colab si leggono i file di Drive.
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
  segnala e si conta (`soglia_rumore_orizzonte` sugli H provati). Dal 26/10 (`70` §3-§4)
  si salva nei giornali dello studio, uno per macchina e solo in aggiunta (PC e Colab
  non scrivono mai lo stesso file): resta anche dopo il riavvio.
- **Versioni bloccate:** `TA-Lib==0.8.1`, `backtesting==0.6.6`, `numba==0.68.0`.
- **Test:** `python suite_rapida.py` durante il lavoro (le suite del codice
  cambiato, 2–3 minuti); **prima di ogni Pull request** `python suite_rapida.py
  --tutte`, 43 suite, 3 alla volta, circa 13 minuti; alla fine deve stampare
  «SUITE COMPLETA: n/n» con n = totale.
- **Catalogo:** 129 condizioni (71 entry, 38 filtri, 10 uscite, 10
  entry-metro); dalle fonti testuali 53 prove, registro in `50` §10.

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
   Per ogni entry vera, 8 celle per lato (10 sui perpetual con lo spot): scarto lordo dal mercato della cella e netto dei costi (`02`,
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

Prossimi lavori, in ordine (Mattia, 24 e 25/10): l'out-of-sample «fresco» (lavoro
piccolo, `70` §13), il volume aggressivo; poi la mappa delle anomalie (il posto
libero 2b del Lab). Orizzonti multipli in un lavoro a parte (`68` §13). Il conto
delle prove fra dataset si decide nel lavoro dei testimoni.

Fonti: una alla volta con il processo di `50`; la coda dei paper è in
`GUIDA_ANALISI_FONTI.md` §11.6.

## Problemi aperti

| cosa | stato |
|---|---|
| stop e target non attivi sulla barra d'ingresso | risolto (PR #49) |
| `ExitSearchBT.top()` ordina per `sharpe`: va ordinato per il t nell'unità che decide | risolto (PR #51) |
| `vwap_ops.py` taglia la giornata a mezzanotte UTC: sulle crypto coincide con la giornata, sul broker (sospeso) no | da decidere se si riapre il broker |
| il notebook di ricerca su Colab chiede il secret `GITHUB_TOKEN` | non bloccante |
| interruttore sulla curva dei profitti | rimandato da Mattia |

## Convenzioni di lavoro

- **Metodologia prima, codice dopo.** I lavori grandi: proposta in `docs/`,
  via libero di Mattia, poi codice. **I lavori piccoli: niente proposta in
  `docs/`**, una descrizione breve in chat, il via, poi il codice.
- **Niente aggiunte non richieste**: ciò che va oltre si propone.
- **Ogni pezzo di codice passa un collaudo** con casi a risultato noto.
- **Modifiche all'engine il più possibile additive**; se non lo sono, si dice.
- **Consegna:** ramo, test, Pull request; il merge lo fa sempre Mattia.
- **Sempre spiegare come si esegue.** Mattia non è un informatico.
