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

---

## 7. Esito (13–15/10/2026) — report descrittivo

Lavoro sul ramo `indicatori-tradingview`. Collaudo: `test_indicatori_tradingview.py`
(143/143 con pandas 3.0.6), più tutte le suite del progetto. Nessun giudizio sui risultati
di trading: i numeri sotto dicono solo che il codice gira e quante volte scatta ogni condizione.

### 7.1 Decisioni prese strada facendo (Mattia)

| Indicatore | Decisione |
|---|---|
| V1 | come da §3 (indicatore di M. Katsanos, script di LazyBear) |
| V2 | il codice di `ta.relativeVolume` di TradingView non è reperibile: usato **"Relative Volume" di veryfid** (MPL 2.0), solo la riga `volume / media delle 30 barre precedenti`. Non è "at time": non tiene conto dell'ora del giorno |
| M1 | pastebin non raggiungibile: sorgente di TradingView con **una correzione dichiarata**, `dev = mult * stdev` (BB 2.0, non 1.5) |
| M2 | soglia ±60 sostituita da **percentile rolling** (10° / 90°) |
| R1 | KER con segno; trend a ±0,5 (linea "Efficient"); laterale con percentile e isteresi 25°/50° su 500 barre (numeri di F25). Autore: Zorba_the_Buddha |
| R2 | licenza **CC BY-NC-SA 4.0 (non commerciale)**: tradotto per uso personale e di ricerca; la funzione resta sotto la stessa licenza |
| R3 | solo `filter_volatility` e `regime_filter` (MPL 2.0) |
| tutti | finestre dei percentili a **500 barre** (2000 erano 8 anni in D1); doppioni **spenti mettendo tra commenti la riga** del dizionario, regola di docs/50 §7.5 precisata il 15/10 (70% **e** almeno 1,3 volte il caso) |

### 7.2 Condizioni

Test: 1 = lookahead per troncamento (con trappola segnata LOOKAHEAD), 2 = fedeltà a TradingView
(PineTS sul Pine originale, EURUSD/BTCUSD/DE40, 20.000 barre; più riscrittura a mano e casi noti),
3 = esecuzione su M5 (sintetico), M15, H1, D1 di EURUSD/BTCUSD/DE40, 4 = registrazione.

| ID | Ind. | Tipo | Lato | Stato | Test 1-4 | Sovrapposizioni (EURUSD in-sample) |
|---|---|---|---|---|---|---|
| E28_VFI_CROSS_UP / E28_SHORT_VFI_CROSS_DOWN | V1 | trigger | L / S | attivo | OK | nessuna ≥ 70% |
| F28_VFI_POSITIVE / F28_VFI_NEGATIVE | V1 | filtro, coppia VFI_SIGN | +1 / −1 | attivo | OK | solo filtri larghissimi (F2_MID, F22), 1,0× il caso |
| F29_RVOL_LOW | V2 | filtro | neutro | attivo | OK | solo F2_MID (1,08×) |
| F29_RVOL_HIGH | V2 | filtro | neutro | **spento** | OK | 100% dentro F3 (2,2×), 90% dentro F6 |
| E29_SQUEEZE_RELEASE_UP / E29_SHORT_SQUEEZE_RELEASE_DOWN | M1 | trigger | L / S | attivo | OK | nessuna ≥ 70% |
| F30_SQZ_MOM_POSITIVE / NEGATIVE | M1 | filtro, coppia | +1 / −1 | **spento** | OK | 72–76% dentro F4, F8/F9, F16/F17 e viceversa (1,4–1,5×) |
| E30_WAVETREND_CROSS_UP / E30_SHORT_WAVETREND_CROSS_DOWN | M2 | trigger | L / S | attivo | OK | nessuna ≥ 70% |
| F31_WT_ABOVE / BELOW_SIGNAL | M2 | filtro, coppia | +1 / −1 | **spento** | OK | 75% dentro F4 e viceversa (1,5×) |
| F32_KER_RANGE | R1 | filtro | neutro | attivo | OK | solo F2_MID, F22 (1,0×) |
| F32_KER_TREND_UP / DOWN | R1 | filtro, coppia | +1 / −1 | **spento** | OK | 88–96% dentro F4, F8/F9, F16/F17, F30, F31 (1,8–2,7×) |
| F33_HURST_PERSISTENT | R2 | filtro | neutro | attivo | OK | 78% dentro F1_ADX (1,25×: sotto 1,3) |
| F33_HURST_MEAN_REVERTING | R2 | filtro | neutro | attivo | OK | 91% dentro F2_MID (1,21×) |
| F34_JDH_VOLATILITY | R3 | filtro | neutro | **spento** | OK | 75% dentro F3 (1,64×), 72% dentro F6 (1,53×) |
| F35_JDH_REGIME_TREND | R3 | filtro | neutro | attivo | OK | 71% dentro F1_ADX (1,14×) |

Sovrapposizioni chieste da §5: R1 contro ADX → KER_TREND al 75–77% dentro F1 (spento per F4/F8/F16);
correlazione |KER|–ADX 0,18, |KER|–CHOP −0,57. M1 contro i filtri di volatilità: nessuna
sovrapposizione dei trigger E29. Hurst contro F26 (variance ratio): nessuna ≥ 70%, correlazione 0,39.

### 7.3 Occorrenze (eventi per i trigger, barre vere per i filtri)

| Condizione | EURUSD M15 / H1 / H4 / D1 | BTCUSD M15 / H1 / H4 / D1 | DE40 M15 / H1 / H4 / D1 |
|---|---|---|---|
| E28 long | 3035 / 791 / 154 / 24 | 4545 / 1027 / 270 / 37 | 2682 / 677 / 188 / 19 |
| E28 short | 3035 / 790 / 155 / 25 | 4543 / 1028 / 270 / 37 | 2682 / 677 / 188 / 18 |
| E29 long | 2837 / 697 / 158 / 27 | 4162 / 1024 / 240 / 31 | 2622 / 685 / 164 / 25 |
| E29 short | 2805 / 733 / 144 / 29 | 3873 / 912 / 245 / 38 | 2295 / 524 / 128 / 27 |
| E30 long | 2032 / 506 / 130 / 18 | 2772 / 703 / 163 / 21 | 1912 / 476 / 112 / 16 |
| E30 short | 2063 / 485 / 119 / 18 | 2701 / 657 / 167 / 19 | 1922 / 483 / 124 / 13 |
| F28 + | 82951 / 20908 / 4641 / 629 | 113755 / 28625 / 7306 / 1118 | 83787 / 21631 / 5598 / 765 |
| F28 − | 85447 / 21004 / 5647 / 870 | 109636 / 27216 / 6544 / 987 | 72690 / 17456 / 4504 / 703 |
| F29 basso | 41887 / 10493 / 2481 / 296 | 55929 / 14008 / 3430 / 446 | 39468 / 9655 / 2424 / 271 |
| F32 laterale | 63572 / 15650 / 3832 / 463 | 83271 / 20979 / 5108 / 695 | 58993 / 14667 / 3682 / 493 |
| F33 persistente | 8265 / 759 / 319 / 6 | 7965 / 888 / 572 / 18 | 7348 / 2282 / 438 / 62 |
| F33 ritorno alla media | 638 / 163 / 14 / **0** | 777 / 84 / 32 / **0** | 669 / 42 / 33 / 3 |
| F35 regime di tendenza | 57338 / 14315 / 3672 / 514 | 71740 / 17627 / 4643 / 756 | 53936 / 13707 / 3704 / 525 |

F33 ritorno alla media è quasi sempre falso su D1: la stima R/S su 100 barre è distorta verso
l'alto (su un cammino casuale H medio 0,525, sotto 0,4 nello 0,3% delle barre). Dichiarato nel test.

### 7.4 Cose scoperte nel collaudo

- **PineTS arrotonda a 10 decimali** i risultati di `ta.ema` e di altre funzioni interne. Su
  EURUSD, dove le differenze di prezzo sono piccole, l'arrotondamento si amplifica (WaveTrend,
  regime di jdehorty): il codice del progetto resta a precisione piena e il test lo dichiara
  (WaveTrend confrontato anche con le ema arrotondate; regime confrontato sopra/sotto soglia).
- **`ta.ema` e `ta.rma` di Pine partono dalla media semplice** delle prime n barre, non dal primo
  valore come `ewm` di pandas: `_ema_pine` e `_rma_pine` in `engine/indicatori.py`.
- **Somme mobili rifatte da capo** (VFI, KER): la somma mobile di pandas lascia residui di 1e-16
  dove la somma vera è zero, e il segno deciderebbe a caso.
- **Regime di jdehorty:** `klmf` parte da 0 per via di `nz()` e il salto iniziale pesa sulla media
  a 200 per ~1000 barre dall'inizio dei dati.
- `test_regime.py` (D4) e `test_vetrina_trigger.py` (14) aggiornati per ammettere la coppia
  VFI_SIGN e i trigger E28–E30 senza disegno dedicato nella lente del Lab.

**Prove aggiunte: 12** (E28 2, E29 2, E30 2, F28 1, F29_LOW 1, F32_RANGE 1, F33 2, F35 1).
Riattivando i doppioni: +5 (F29_HIGH, F30, F31, F32_TREND, F34: una per coppia o filtro).
