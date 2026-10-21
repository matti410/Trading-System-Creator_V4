# 00 · Scopo del progetto e stato attuale

**Da leggere per primo, insieme a `CLAUDE.md`.** Stato al 21 ottobre 2026.
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
  ATR accanto; totale, drawdown, money management e stress test in pips (`02`,
  «Unità»; `63` §4).
- **Costi:** commissione taker di listino, livello base, più uno spread di un
  passo; sui perpetual il **funding** trade per trade, acceso di default (`63`
  §5). Leva mai oltre il tetto italiano (perpetual 2, spot 1).
- **Motore di backtest:** «veloce» (`engine/motore_veloce.py`, numba) è il
  predefinito; «bt» (`backtesting.py`) resta e fa da oracolo dei test. Stessi
  trade al bit, tranne i sistemi in cui il capitale simulato si esaurisce:
  «veloce» tiene i trade e avvisa con la data (`65`).
- **Mercato nullo sospeso** (`63` §10.3): il codice resta, fermo.
- **Versioni bloccate:** `TA-Lib==0.8.1`, `backtesting==0.6.6`, `numba==0.68.0`.
- **Test:** `python suite_rapida.py` durante il lavoro (le suite del codice
  cambiato, 2–3 minuti); **prima di ogni Pull request** `python suite_rapida.py
  --tutte`, 37 suite, 3 alla volta, circa 11 minuti; alla fine deve stampare
  «SUITE COMPLETA: n/n» con n = totale.
- **Catalogo:** 129 condizioni (71 entry, 38 filtri, 10 uscite, 10
  entry-metro); dalle fonti testuali 53 prove, registro in `50` §10.

## Prossimi lavori, in ordine (Mattia, 21/10), un ramo ciascuno

1. **Correzione dello stop non attivo sulla barra d'ingresso** (comportamento
   della libreria, ~0,2% dei trade, bias a favore del backtest). Parte al via
   di Mattia. Poi la proposta sull'ordinamento di `top()` (oggi per `sharpe`;
   il t nell'unità che decide).
2. **Confidenza in bp:** `engine/confidenza.py` ha ancora le soglie in pips.
3. **Soglia cumulata nel Lab:** Šidák sul totale delle prove della catena,
   solo informativa (`00_ARCHIVIO.md`, «Cosa manca», punto 3).
4. **C · atlante del trigger** (`63` §6). Grande.
5. **Money management P1–P4** e **stress test in bp**. Piccoli, da decidere.

Fonti: una alla volta con il processo di `50`; la coda dei paper è in
`GUIDA_ANALISI_FONTI.md` §11.6.

## Problemi aperti

| cosa | stato |
|---|---|
| stop non attivo sulla barra d'ingresso | prossimo lavoro (punto 1) |
| `ExitSearchBT.top()` ordina per `sharpe`, la regola dice `avg_trade_netto` | proposta dopo il punto 1 |
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
