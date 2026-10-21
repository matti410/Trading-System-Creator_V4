# Istruzioni per Claude Code — Trading-System-Creator_V4

L'utente (Mattia) NON è un informatico. Rispondi sempre in italiano e, a ogni passo,
spiega in parole semplici: cosa hai fatto, come eseguire ogni comando, cosa dovrebbe
vedere come risultato. Ragiona come un trader algoritmico esperto.

## Il progetto
Strumento Python per scovare strategie di trading. DAL 20/10/2026 IL PERIMETRO E' SOLO
CRYPTO DA EXCHANGE (Binance, Bybit; spot e perpetual; BTC, ETH, SOL, XRP). Il lato broker
(MT5, CFD, EURUSD e gli altri 8 symbol) e' SOSPESO: il codice resta nel repo, non si
cancella, ma non si sviluppa e non si usa per misurare. Dataset di sviluppo e di
identita': BINANCE_PERP_BTCUSDT (prima era EURUSD). Decisione in docs/63 §10.0.
Leggi PRIMA di lavorare: docs/00_SCOPO_E_STATO.md (regola che viene prima di tutte:
i risultati sui dati NON sono il metro di giudizio del progetto, non fare commenti
tipo "la strategia tiene/non tiene" né proposte di cambiare asset se non richiesti),
docs/02_KPI_E_GIUDIZIO.md e, per il processo, docs/50_IDEE_DA_ARTICOLI.md
(dal 10/10/2026 contiene anche l'ex docs/51: regola di consegna in §9, registro in §10,
filtri di regime in §10 bis, lavoro in locale in §12).

## Processo per ogni articolo (docs/50)
1. Leggi la fonte (articolo con Claude in Chrome; se non si apre, l'utente incolla il testo).
2. Scrivi la SCHEDA in testo (modello in docs/50 §3). Nessun codice.
3. ASPETTA il via libera dell'utente, candidato per candidato.
4. Solo dopo: scrivi il codice direttamente nei file e collaudalo (docs/50 §7).
5. Aggiorna il registro (docs/50 §10) con le "prove" aggiunte.
Parametri fissati a priori, mai ottimizzati sui dati. Provare più symbol serve a VERIFICARE
la condizione, non a ritoccare i parametri per ogni symbol.
Se scegli quale condizione tenere in base ai risultati per symbol, conta come prova in più.
In locale scrivi tu le modifiche nei file (docs/50 §9.1); la consegna "a parti"
(docs/50 §9.2) vale solo per le consegne in chat.

## Regole di codice
- Nuovi indicatori solo in engine/indicatori.py.
- Condizioni nei dizionari di entry_long.py, entry_short.py, filter_conditions.py, exit_*.py.
- Modifiche all'engine il più possibile additive; se non lo sono, dichiaralo.
- Nessun lookahead: ogni condizione passa verifica_lookahead e verifica_degenerazione.
- Il pip è FISSO per symbol: l'unica fonte è engine/simboli.py (pip_symbol, info_symbol).
  Mai dedurlo dal prezzo. Un symbol nuovo = una riga in SIMBOLI (classe, pip, contratto,
  valuta di quotazione, cifre, letti da MT5); un symbol fuori tabella deve fermarsi con errore.
  I symbol da exchange crypto stanno in SIMBOLI_EXCHANGE, LOTTI_EXCHANGE, LEVA_EXCHANGE
  (valori letti dall'exchange con ccxt, nome EXCHANGE_MERCATO_COPPIA, es. BINANCE_PERP_BTCUSDT).
- Prima di ogni commit lancia TUTTI i test_*.py (su Windows con PYTHONIOENCODING=utf-8):
  l'ultima riga di ognuno deve essere "RISULTATO: n/n test superati" con n = totale.
  Se un test fallisce, fermati e spiega.
- Dal 21/10/2026: durante il lavoro basta la suite rapida, `python suite_rapida.py`
  (le suite legate al codice cambiato, 2-3 minuti). La completa,
  `python suite_rapida.py --tutte`, e' obbligatoria prima di ogni Pull request.

## Dati e MT5
- SOSPESO DAL 20/10/2026: MT5 e scarica_dati.py non si usano. I dati si scaricano solo con
  scarica_dati_crypto.py (sotto). Le regole su MT5 qui sotto restano valide se un giorno
  si riapre il lato broker.
- ccxt, funzioni ammesse (tutte pubbliche, sola lettura): load_markets, fetch_ohlcv,
  fetch_funding_rate_history. MAI chiavi API, MAI ordini, MAI saldi.
- I dati scaricati vanno in dati/ (non vanno su GitHub, è nel .gitignore).
- Symbol disponibili in dati/ (M15 dal 2/1/2020, scaricati con scarica_dati.py):
  EURUSD, GBPUSD, USDJPY, NZDUSD, BTCUSD, US500, USTEC, XAUUSD, DE40.
  USDCAD è ESCLUSO: il broker lo fornisce in M15 solo da gennaio 2025.
- I notebook leggono dati/{symbol}_{timeframe}.csv: in locale dalla cartella dati/,
  su Colab da Google Drive (Il mio Drive/Trading-System-Creator_V4/dati/).
- Dati da exchange crypto (dal 19/10/2026): scarica_dati_crypto.py, sul PC (Binance e Bybit
  bloccano Colab), 16 symbol = Binance e Bybit x spot e perpetual x BTC, ETH, SOL, XRP, M15
  dal 2/1/2020. Date gia' in UTC, nessun rollover. Solo le funzioni di ccxt ammesse qui sopra,
  MAI chiavi API, MAI funzioni di ordine o di saldo.
  Costi: commissione taker per lato dal listino ufficiale, livello base (COMMISSIONI in
  engine/exchange.py); valori nuovi solo dal listino, con la fonte. Il funding dei perpetual
  e' contato dal 21/10/2026 (dati/<SYMBOL>_FUNDING.csv, docs/63 §5). Leva: mai oltre il
  tetto italiano (perpetual 2, spot 1).
- Spread: solo dal listino del conto Standard, SPREAD_LISTINO_PIPS in engine/vetrina.py,
  commissione zero. Se un symbol non ha la riga NON inventare lo spread: il notebook si
  ferma con la riga esatta da aggiungere (rollover proposto dai dati); lo spread normale
  lo fornisce Mattia.
- Usa SOLO le funzioni di LETTURA di engine/mt5_interaction.py (start_mt5,
  initialize_symbols, retrieve_candlestick_data_range). MAI inviare, modificare
  o chiudere ordini, MAI cancellare ordini. Altre chiamate a MetaTrader5 (es.
  symbol_info) solo in sola lettura e con permesso esplicito di Mattia.
- Le credenziali MT5 non vanno mai scritte in file del repo né stampate a schermo:
  si leggono da credenziali_mt5.txt (nel .gitignore) o da MT5 già aperto.
- Dopo ogni download: controlla fuso orario del broker, buchi e barre in quarantena
  (docs/10, docs/11) e riporta il risultato. Pip e costi per symbol: docs/50 §12.

## I notebook: due vivi, uno sospeso
- Vivi e SEMPRE allineati, nello stesso ramo: Trading_System_Lab_Crypto.ipynb (laboratorio
  guidato, dati da exchange) e Trading_Grid_Search_v4_backtesting.ipynb (ricerca, usato sui
  symbol da exchange). Ogni modifica a dati, symbol, costi, pip, fuso, capitale, lotti o leva
  fatta in uno va portata nell'altro.
- Sospeso dal 20/10/2026: Trading_System_Lab.ipynb (broker CFD). Non si aggiorna e non si
  collauda; in testa ha la riga «sospeso dal 20/10/2026, non mantenuto». Non va cancellato.
- I Lab non hanno codice nelle celle: chiamano le funzioni di engine/vetrina.py. Allineare
  vuol dire di solito modificare vetrina.py. Dati e costi si leggono con carica_storico e
  costi_storico.
- Prova per tutti: identita' su BINANCE_PERP_BTCUSDT a parita' di barre (prima e dopo la
  modifica) nei due notebook vivi, e un giro completo su BYBIT_SPOT_ETHUSDT (altro exchange,
  spot, solo long).
- Tutte le suite test_*.py si lanciano comunque, comprese quelle sui symbol del broker (non
  chiedono MT5): se una si rompe, si e' toccato codice condiviso.

## Git e invio su GitHub (procedura completa)
1. Parti da main aggiornato: `git switch main`, `git fetch origin --prune`,
   `git merge --ff-only origin/main`.
2. Un ramo per argomento (es. articolo-NN-nome): `git switch -c <ramo>`. Mai lavorare su main.
3. Fai le modifiche, lancia TUTTI i test (vedi sopra); se uno fallisce, fermati.
4. Commit con messaggio chiaro in italiano, uno per gruppo di modifiche; mai --force;
   mai cancellare file senza chiedere.
5. Invio: o Mattia clicca Publish Branch in VS Code, o lo fai tu con
   `git push -u origin <ramo>` e `gh pr create --base main` (GitHub CLI è collegato come
   matti410; in una shell aperta prima dell'installazione ricarica il PATH).
6. Spiega a Mattia cosa cliccare su GitHub: Compare & pull request → controlla
   `base: main ← compare: <ramo>` → Create pull request → guarda Files changed →
   Merge pull request → Confirm merge → (facoltativo) Delete branch.
   Il Merge lo fa SEMPRE Mattia.
7. Dopo il merge: `git switch main`, `git fetch origin --prune`,
   `git merge --ff-only origin/main`, `git branch -d <ramo>`.
