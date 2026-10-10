# Istruzioni per Claude Code — Trading-System-Creator_V4

L'utente (Mattia) NON è un informatico. Rispondi sempre in italiano e, a ogni passo,
spiega in parole semplici: cosa hai fatto, come eseguire ogni comando, cosa dovrebbe
vedere come risultato. Ragiona come un trader algoritmico esperto.

## Il progetto
Strumento Python per scovare strategie di trading (EURUSD, BTCUSD e altri symbol, M15).
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
- Prima di ogni commit lancia TUTTI i test_*.py (su Windows con PYTHONIOENCODING=utf-8):
  l'ultima riga di ognuno deve essere "RISULTATO: n/n test superati" con n = totale.
  Se un test fallisce, fermati e spiega.

## Dati e MT5
- I dati scaricati vanno in dati/ (non vanno su GitHub, è nel .gitignore).
- Symbol disponibili in dati/ (M15 dal 2/1/2020, scaricati con scarica_dati.py):
  EURUSD, GBPUSD, USDJPY, NZDUSD, BTCUSD, US500, USTEC, XAUUSD, DE40.
  USDCAD è ESCLUSO: il broker lo fornisce in M15 solo da gennaio 2025.
- Il notebook principale legge dati/{symbol}_M15.csv: in locale dalla cartella dati/,
  su Colab da Google Drive (Il mio Drive/Trading-System-Creator_V4/dati/).
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
