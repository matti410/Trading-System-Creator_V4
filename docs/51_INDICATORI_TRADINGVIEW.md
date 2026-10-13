# 51 — Indicatori TradingView da tradurre in Python

Specifica per Claude Code. Obiettivo: tradurre 7 indicatori della community TradingView in
**condizioni di ingresso (trigger LONG/SHORT)** e **filtri** del progetto, rispettando le
convenzioni già in uso nel repo.

Il progetto è un TOOL per scovare strategie: le nuove condizioni vanno solo aggiunte e collaudate.
**Nessun giudizio su "funziona / non funziona"**: i run servono a verificare il codice, non come verdetto.

---

## 0. Regole di lavoro (obbligatorie)

1. **Prima il piano, poi il codice.** Leggi questo file, il registro delle condizioni esistenti,
   `50_IDEE_DA_ARTICOLI.md` e il test `test_idee_articoli.py`. Poi proponi in testo:
   nomi delle funzioni, ID delle condizioni (primi E*/F* liberi), firme, cosa restituiscono,
   in quali file vanno. **Aspetta l'OK dell'utente prima di scrivere codice.**
2. **Solo modifiche additive.** Non toccare i file esistenti dell'engine. Nuovi file o nuove funzioni.
3. **Stessa architettura delle condizioni esistenti:** funzioni stateless `df -> pd.Series[bool]`,
   registrate con i decoratori del progetto (`@register_entry`, `@register_filter`, ecc.),
   caricate dalla scansione della cartella. Usa la convenzione già in uso per i filtri non
   direzionali (validi sia per LONG sia per SHORT).
4. **Trigger = eventi** (transizioni, pattern `_evento()`), **filtri = stati**.
5. **File condivisi:** le condizioni vanno nella posizione condivisa tra progetto principale e
   progetto crypto, così non si perdono pezzi tra i due.
6. **Nessuna aggiunta non richiesta.** Se pensi che serva qualcosa in più, proponilo e aspetta.
7. **Ogni pezzo passa i test (sezione 4) prima della consegna.**
8. Spiega all'utente come lanciare ogni cosa (comando, dove lanciarlo, cosa aspettarsi):
   non è un informatico. Terminologia GitHub semplificata.

## 1. Regole di traduzione Pine → Python

- **Zero lookahead.** Ogni valore alla barra *t* usa solo barre ≤ *t* (barra chiusa).
  Allinea lo `shift` alla convenzione delle condizioni esistenti.
- **Vietati i timeframe superiori fissi** (`request.security` su "W", "D", ecc.). Se lo script li
  usa, segnalalo e proponi l'alternativa prima di procedere.
- **Parametri in barre**, con i default dello script originale. Le funzioni devono funzionare su
  M5, M15, M30, H1, H4, D1 senza modifiche.
- **Riscaldamento:** finché l'indicatore non ha abbastanza storia, la condizione vale `False`
  (niente segnali su NaN).
- **Semantica Pine da replicare con attenzione** (verificala sul codice, non a memoria):
  `ta.rma`, `ta.ema` (inizializzazione), `ta.stdev` (deviazione standard di popolazione),
  `ta.linreg`, `ta.crossover/crossunder`, `nz()`, `ta.tr(true)`, valori `na` iniziali.
- **Volume:** su forex MT5 è tick volume, sulle crypto (ccxt) è volume reale. Il codice non deve
  assumere nessuno dei due; annota nel docstring che V1 e V2 dipendono dalla qualità del volume.
- **Soglie:** dove lo script ha una soglia arbitraria e l'indicatore non ha una scala con
  significato teorico, proponi (non imporre) la versione a percentile rolling già usata nel progetto.
- **Licenza:** copia nel docstring di ogni funzione autore, link e licenza dichiarata nell'header
  del codice Pine. Se la licenza è non commerciale, fermati e segnalalo.

## 2. Sorgenti Pine

L'utente salva il codice Pine di ogni script nella cartella `pine_sources/` del repo:

| File | Script | Dove prendere il codice |
|---|---|---|
| `V1_vfi.pine` | Volume Flow Indicator [LazyBear] | https://www.tradingview.com/script/MhlDpfdS-Volume-Flow-Indicator-LazyBear/ |
| `V2_rvol_at_time.pine` | Relative Volume at Time (indicatore integrato di TradingView) | dal grafico, icona `{}` "Codice sorgente" dell'indicatore |
| `M1_squeeze.pine` | Squeeze Momentum [LazyBear] | **usare il sorgente aggiornato su pastebin** linkato nella pagina (quello mostrato su TradingView ha il moltiplicatore BB bloccato a 1.5): https://www.tradingview.com/script/nqQ1DT5a-Squeeze-Momentum-Indicator-LazyBear/ |
| `M2_wavetrend.pine` | WaveTrend Oscillator [LazyBear] | pagina dello script originale di LazyBear |
| `R1_ker.pine` | Kaufman Efficiency Ratio (KER) | https://www.tradingview.com/script/7imltc5K-Kaufman-Efficiency-Ratio-KER/ |
| `R2_hurst.pine` | Hurst Exponent Oscillator [PhenLabs] | https://www.tradingview.com/script/Cgl8VpCf-Hurst-Exponent-Oscillator-PhenLabs/ |
| `R3_mlextensions.pine` | Libreria MLExtensions [jdehorty] (funzioni `filter_volatility`, `regime_filter`) | pagina della libreria MLExtensions di jdehorty |
| `R3_lorentzian.pine` | Machine Learning: Lorentzian Classification [jdehorty] | serve solo per leggere i default dei filtri |

Se un file manca, chiedilo all'utente: non ricostruire a memoria senza dirlo.

## 3. Cosa produrre per ogni indicatore

Per ogni indicatore: **una funzione di calcolo** (restituisce le serie numeriche dell'indicatore)
+ **le condizioni** costruite sopra. Proposta di partenza, da confermare nel piano:

### V1 — Volume Flow Indicator
- Trigger LONG: VFI incrocia sopra 0. Trigger SHORT: VFI incrocia sotto 0.
- Filtri: VFI > 0 (LONG) / VFI < 0 (SHORT).

### V2 — Relative Volume at Time
- Solo filtri (non dà direzione): RVOL alto / RVOL basso, validi per entrambi i lati.
- Replicare la modalità dello script TradingView (volume cumulato dall'ancora di sessione) per
  poterlo validare. Su D1 o su dati senza fascia oraria ripetibile, segnalare il comportamento
  e proporre come gestirlo.
- Attenzione: crypto 24/7 vs forex con weekend e rollover: le "fasce orarie" e i giorni di storia
  devono essere contati correttamente in entrambi i casi.

### M1 — Squeeze Momentum
- Trigger LONG: rilascio dello squeeze (squeeze attivo alla barra precedente, non attivo ora)
  con momentum > 0. Trigger SHORT: stesso rilascio con momentum < 0.
- Filtri: momentum > 0 (LONG) / < 0 (SHORT).
- Usare l'istogramma a regressione lineare di LazyBear (non il momentum semplice di Carter).

### M2 — WaveTrend
- Trigger LONG: WT1 incrocia sopra WT2 con WT1 sotto il livello di ipervenduto.
  Trigger SHORT: WT1 incrocia sotto WT2 con WT1 sopra il livello di ipercomprato.
- Filtri: WT1 > WT2 (LONG) / WT1 < WT2 (SHORT).

### R1 — Kaufman Efficiency Ratio
- Versione con segno (direzione del movimento netto).
- Filtri: trend rialzista efficiente (LONG), trend ribassista efficiente (SHORT),
  mercato inefficiente/laterale (entrambi i lati).

### R2 — Hurst Exponent
- Filtri non direzionali: regime persistente (H sopra soglia alta) e regime di ritorno alla media
  (H sotto soglia bassa), soglie dello script come default.
- Segnalare nel piano la finestra minima sensata e il bias delle stime R/S su finestre corte.

### R3 — Filtri di jdehorty
- Tradurre **solo** `filter_volatility` e `regime_filter` dalla libreria MLExtensions.
- **Non** tradurre il classificatore Lorentzian.
- **Non** tradurre `filter_adx`: l'ADX è già nel progetto.

## 4. Test obbligatori

1. **Test di non-lookahead (troncamento):** per ogni funzione, il valore alla barra *t* calcolato
   sulla serie completa deve essere identico a quello calcolato sulla serie tagliata a *t*.
   Su più punti casuali.
2. **Test di fedeltà a TradingView** (barra per barra, dopo il riscaldamento):
   - **Opzione A (preferita): PineTS** di LuxAlgo — esegue il codice Pine originale sugli stessi
     dati CSV usati in Python e si confrontano i risultati. Uso solo interno come strumento di
     test (licenza AGPL). Va installato Node.js: spiegare all'utente ogni passo.
     È sperimentale: se uno script non gira, passare all'opzione B per quello script.
   - **Opzione B: CSV esportato da TradingView** con i valori dell'indicatore
     (menu del grafico → "Esporta dati del grafico"), confrontato sulle stesse barre.
   - Tolleranza da proporre nel piano; i segnali booleani devono coincidere.
3. **Test di esecuzione multi-symbol e multi-timeframe:** le condizioni girano senza errori su
   almeno 3 symbol e su M5, M15, H1, D1. Riportare solo **quante volte scatta** ogni condizione
   (controllo che non sia sempre vera/falsa) — nessun commento sui risultati di trading.
4. **Test di registrazione:** le nuove condizioni compaiono nel registro e il test esistente
   (`test_idee_articoli.py`) continua a passare.

## 5. Report finale (solo descrittivo)

Una tabella per condizione: ID, indicatore, tipo (trigger/filtro), lato, esito dei 4 test,
numero di occorrenze per symbol/timeframe, e **sovrapposizione** con le condizioni esistenti
che misurano cose simili (es. R1 vs ADX, M1 vs filtri di volatilità, M2 vs M3 — QQE non incluso
in questo giro). La decisione su cosa tenere spetta all'utente.

## 6. Salvataggio su GitHub

Alla fine, con l'OK dell'utente, salvare il lavoro su GitHub (commit + push) con un messaggio
chiaro, spiegando in parole semplici cosa è stato salvato.
