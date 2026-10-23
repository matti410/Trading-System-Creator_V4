# 00 · Scopo del progetto e stato attuale

**Da leggere per primo, insieme a `CLAUDE.md`.** Stato al 23 ottobre 2026 (dopo la PR #55).
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
  è sospeso. Girano in locale (`dati/`) e su Colab (Drive).
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
- **Versioni bloccate:** `TA-Lib==0.8.1`, `backtesting==0.6.6`, `numba==0.68.0`.
- **Test:** `python suite_rapida.py` durante il lavoro (le suite del codice
  cambiato, 2–3 minuti); **prima di ogni Pull request** `python suite_rapida.py
  --tutte`, 40 suite, 3 alla volta, circa 11 minuti; alla fine deve stampare
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

7. **Orari e uscite per lato** — in corso (ramo `orari-e-uscite-per-lato`;
   resoconto in `66` §15). L'atlante misura anche i trigger scelti fuori
   catalogo (quelli a orario contro il mercato della cella a qualunque ora);
   stop, target e regola d'uscita per lato nella schermata 4 e nel notebook
   di ricerca; profilo orario 2b in bp sulle crypto; nella soglia cumulata le
   fasce del profilo con un trigger a orario; avviso sulla durata con trigger
   a orario sui due lati.

Prossimi lavori: ancora da decidere (ordine e contenuto li stabilisce
Mattia).

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
