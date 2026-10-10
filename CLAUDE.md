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
con docs/51_CONSEGNA_A_PARTI_E_REGISTRO_REGIME.md (dove divergono, vale il 51).

## Processo per ogni articolo (docs/50)
1. Leggi la fonte (articolo con Claude in Chrome; se non si apre, l'utente incolla il testo).
2. Scrivi la SCHEDA in testo (modello in docs/50 §3). Nessun codice.
3. ASPETTA il via libera dell'utente, candidato per candidato.
4. Solo dopo: scrivi il codice direttamente nei file e collaudalo (docs/50 §7).
5. Aggiorna il registro (docs/50 §10 / docs/51) con le "prove" aggiunte.
Parametri fissati a priori, mai ottimizzati sui dati. Provare più symbol serve a VERIFICARE
la condizione, non a ritoccare i parametri per ogni symbol.
Se scegli quale condizione tenere in base ai risultati per symbol, conta come prova in più.

## Regole di codice
- Nuovi indicatori solo in engine/indicatori.py.
- Condizioni nei dizionari di entry_long.py, entry_short.py, filter_conditions.py, exit_*.py.
- Modifiche all'engine il più possibile additive; se non lo sono, dichiaralo.
- Nessun lookahead: ogni condizione passa verifica_lookahead e verifica_degenerazione.
- Prima di ogni commit lancia TUTTI i test_*.py: l'ultima riga deve essere
  "RISULTATO: n/n test superati" con n = totale. Se un test fallisce, fermati e spiega.

## Dati e MT5
- I dati scaricati vanno in dati/ (non vanno su GitHub, è nel .gitignore).
- Usa SOLO le funzioni di LETTURA di engine/mt5_interaction.py (start_mt5,
  initialize_symbols, retrieve_candlestick_data_range). MAI inviare, modificare
  o chiudere ordini, MAI cancellare ordini.
- Le credenziali MT5 non vanno mai scritte in file del repo né stampate a schermo:
  si leggono da credenziali_mt5.txt (nel .gitignore) o da MT5 già aperto.
- Dopo ogni download: controlla fuso orario del broker, buchi e barre in quarantena
  (docs/10, docs/11) e riporta il risultato. Costi per symbol: docs/31.

## Git
- Lavora su un ramo per argomento (es. articolo-NN-nome), mai direttamente su main.
- Commit con messaggio chiaro in italiano; mai --force; mai cancellare file senza chiedere.
- Alla fine spiega all'utente cosa cliccare su GitHub (Pull request → Merge).
