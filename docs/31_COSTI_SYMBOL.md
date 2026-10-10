# 30 · ML Long/Short — obiettivo, split e stato del notebook
 
**Repo (pubblico):** `github.com/matti410/Trading-System-Pipeline-ML`
**Notebook:** `TS-Pipeline-ML.ipynb`
 
Esperimento distinto dal progetto principale (`Trading-System-Creator_V4`),
in un repo a sé. Riusa gli stessi principi già collaudati lì (event study,
percentile rolling, split IS/OOS) ma con un obiettivo diverso: non un
sistema a regole, ma due modelli ML.
 
---
 
## Obiettivo
 
**Due modelli ML separati, uno per direzione**, non uno unico/multiclasse:
un modello LONG e un modello SHORT, addestrati e valutati in modo
indipendente.
 
**Meta-labeling.** I modelli non decidono da soli quando entrare: decidono
se un trigger già scattato (uno dei pattern selezionati con l'event study)
vale la pena di essere preso. Il modello vede solo le barre in cui un
trigger del suo lato è vero — mai le barre senza trigger, per non fargli
imparare rumore.
 
---
 
## Dati
 
Il notebook oggi gira su **EURUSD M15**, ma la pipeline è pensata per
qualunque symbol: la fonte è **CSV** (storico scaricato in precedenza) o
**MT5 in live** (`retrieve_candlestick_data_range`), a seconda di quale
cella di caricamento è attiva nel notebook — sono intercambiabili, cambia
solo `symbol` e la sorgente dati, non il resto della pipeline. Cambiando
symbol cambia anche `soglia_costi` nel target (spread e commissione dello
strumento). Dal 28/9 il target è in rendimento relativo, quindi la soglia
resta una frazione (bp) anche su symbol con prezzi alti (BTCUSD).
 
---
 
## Split dei dati
 
- **`df_is`** (80% dello storico): diviso **80/20 in train/test** per
  tempo (`split.py`), per lo sviluppo e il tuning dei modelli.
- **`df_oos`** (20% dello storico, non ancora toccato): riservato **solo
  alla conferma finale**, dopo che i modelli sono già decisi. Non si usa
  per scegliere niente — né feature, né soglie, né iperparametri.
`TARGET_LONG/SHORT` sono calcolati su `df` intero: i trigger delle ultime H
barre di `df_is` hanno l'etichetta calcolata con prezzi OOS e vengono
esclusi (purge); i trigger di train la cui finestra entra nel test vengono
esclusi (embargo). Entrambi fatti da `split_train_test`.
 
---
 
## Pipeline del notebook (fino a qui)
 
1. **Dati**: caricamento da CSV o da MT5 live, M15. Run corrente su
   EURUSD, 167.219 barre grezze, 2020–2026.
2. **Feature engineering**: `aggiungi_indicatori(df)` — indicatori + colonne
   `F*` (contesto) + colonne `E*` (trigger).
3. **Taglio del riscaldamento** (dal 28/9): `df = df.iloc[RISCALDAMENTO:]`
   con `RISCALDAMENTO = 2100` barre. Motivo: un confronto con NaN dà False,
   non NaN, quindi `dropna()` non toglieva nulla e le prime barre avevano
   E*/F* falsi per mancanza di storia. La finestra più lunga del catalogo è
   E7 (percentile su 2000 barre); verificato che dopo 2100 barre tutte le
   72 colonne E*/F* sono identiche a prescindere dal punto di partenza dei
   dati. Se si aggiunge una condizione con finestra più lunga, va alzato.
4. **Split IS/OOS 80/20** su `df` → `df_is`, `df_oos`.
5. **Event study su `df_is`** (`H=25`, `MIN_TRADES=200`) → `ev.sintesi`.
6. **Selezione dei trigger per lato**, dalle code della distribuzione dei
   picchi in `ev.sintesi`:
   - `l1` = migliori del pool LONG nativo (coda positiva, `direction=1`)
   - `l2` = migliori del pool SHORT nativo (coda negativa, `direction=-1`)
   - `s1` = short falliti (coda positiva su `direction=-1`) → bullish
   - `s2` = long falliti (coda negativa su `direction=1`) → bearish
   - `entry_long_selected_feat = l1[:2] + s1[:2]`
   - `entry_short_selected_feat = l2[:2] + s2[:2]`
7. **`df_LONG` / `df_SHORT`**: OHLCV + i 4 trigger del lato + tutte le `F*`,
   su `df` intero.
8. **`costruisci_target()`** (`target.py`): una riga per barra trigger,
   ingresso Open barra successiva, uscita Close a 25 barre dal trigger,
   `gain = (exit/entry - 1) * direction` confrontato con `soglia_costi`
   (niente barriera TP/SL).
9. **`TARGET_LONG` / `TARGET_SHORT`**: Series 0/1 sulle sole righe trigger.
10. **Split train/test** (`split_train_test`) → `idx_train_L/idx_test_L`,
    `idx_train_S/idx_test_S`.
11. **Matrici X** (`costruisci_X`) → `X_LONG`, `X_SHORT`: 4 trigger E* del
    lato + 20 F*, in 0/1, allineate ai target. Mai OHLCV.
---
 
## Funzioni principali
 
| funzione | dove | cosa fa |
|---|---|---|
| `entry_long.aggiungi_trigger_long(df)` | repo | aggiunge le colonne `E*` long |
| `entry_short.aggiungi_trigger_short(df)` | repo | aggiunge le colonne `E*` short |
| `filter_conditions.FILTRI` | repo | dizionario che aggiunge le colonne `F*` di contesto |
| `engine.event_study.run_event_study(df, entry_names, horizon, min_trades)` | repo | produce `ev.sintesi` |
| `target.costruisci_target(df_lato, colonne_trigger, direction, horizon=25, soglia_costi=0.65e-4)` | repo (corretto il 28/9) | Series target 0/1 per un lato, solo righe trigger |
| `split.split_train_test(target, df_is, horizon=25, quota=0.8)` | consegnato il 29/9, da caricare sul repo | `(idx_train, idx_test)`: split per tempo dentro `df_is`, con purge ed embargo |
| `split.costruisci_X(df_lato, target, colonne_trigger)` | repo (29/9) | matrice feature 0/1, allineata al target |
| `modello.rendimenti_trigger(df_lato, indice, direction, horizon=25)` | consegnato il 29/9, da caricare sul repo | guadagno di ogni trigger, stessa formula del target |
| `modello.addestra(X, y, idx_train, idx_test, parametri=None, pesi=None)` | consegnato il 29/9 (parametro `pesi` aggiunto lo stesso giorno, default invariato) | LightGBM con `PARAMETRI_BASE`, solo righe di train (si ferma se il train non precede il test); `pesi` = interruttore dei pesi di unicità |
| `oos.indici_oos(target, df_is)` | consegnato il 29/9, da caricare sul repo | trigger successivi a `df_is` |
| `oos.valuta_oos(modello, X, y, rend, idx_test, idx_oos, fasce=5, n_fasce=5)` | consegnato il 29/9 | soglia dai quantili delle probabilità del test (fascia singola o intervallo, es. `(4, 5)`), applicata tale e quale all'OOS; tabella test/OOS selezionati vs tutti |
| `backtest_oos.trigger_in_fascia(modello, X, idx_test, idx_oos, fasce=5)` | consegnato il 29/9, da caricare sul repo | trigger OOS nella fascia operativa (stessa soglia di `valuta_oos`) |
| `backtest_oos.esegui_backtest(df_periodo, trigger_long, trigger_short, horizon=25, unita=100_000, capitale=150_000, costo_rt=0.65e-4)` | consegnato il 29/9 | VectorBT `from_orders`: ingresso Open barra dopo, uscita Close a 25 barre, un trade alla volta per lato, lotto fisso; portafogli LONG / SHORT / COMBINATO |
| `backtest_oos.tabella_metriche(scenari)` / `grafico_equity(scenari, capitale)` | consegnato il 29/9 | metriche per lato e scenario; equity OOS modello vs tutti i trigger |
| `pesi.pesi_unicita(indice, df_lato, horizon=25)` | consegnato il 29/9, da caricare sul repo | peso di unicità per trigger (media di 1/finestre aperte sulle sue 25 barre), normalizzato a media 1; si calcola su `idx_train` |
| `modello.valuta(modello, X, y, rend, idx_train, idx_test, n_fasce=5)` | consegnato il 29/9 | AUC e distribuzione probabilità train/test + tabella del test per quintili di probabilità con riga "tutti" |
| `modello.importanza(modello, X)` | consegnato il 29/9 | peso % di ogni feature (gain) |
 
---
 
## Correzioni del 28/9 (check del notebook)
 
- **Target in rendimento relativo**: prima era `exit - entry` in unità di
  prezzo confrontato con una soglia in frazione (0,65 bp). Su EURUSD
  cambiava 9 etichette LONG e 7 SHORT; su BTCUSD avrebbe annullato la
  soglia costi. Test: etichette identiche moltiplicando i prezzi ×50.000.
- **F2_MID_VOLATILITY**: era `atr <= p75`, cioè il contrario di F2_HIGH e
  conteneva F2_LOW. Ora `p35 < atr <= p75` (parametri `low_percentile`,
  `high_percentile`). Test: LOW/MID/HIGH si spartiscono le barre
  (35% / 40% / 25%), ogni barra in una sola fascia.
- **Taglio del riscaldamento** a 2100 barre (vedi pipeline, passo 3).
Conteggi dopo le correzioni (EURUSD, selezione trigger invariata):
**LONG 6.790 trigger, 48,5% classe 1 · SHORT 3.426 trigger, 48,1%.**
(Prima: 6.869 / 3.453.)
 
---
 
## Sovrapposizione dei trigger — decisione (A), in due tempi
 
Il 64% dei trigger LONG e il 37% degli SHORT scattano entro 25 barre dal
precedente: le finestre d'esito si sovrappongono e le etichette non sono
indipendenti. Misurato il 29/9: 6.790 righe LONG equivalgono a ~4.150
trade indipendenti (3.426 SHORT a ~2.740).
 
Decisione del 28/9: **opzione A** — tenere tutti i trigger e dare a
ciascuno un **peso di unicità** (media di 1/n. finestre aperte sulle sue
25 barre). Scartate: (B) diradare, (C) nessun peso.
 
Sequenza concordata il 29/9, per non accumulare complessità non verificata:
1. prima split + purge + embargo + X (la parte necessaria) → `split.py` ✔
2. primo modello **senza pesi** = base di riferimento
3. pesi aggiunti dopo come interruttore (`usa_pesi=True/False`) con test
   proprio; si tengono solo se migliorano il test rispetto alla base.
---
 
## Split train/test — run del 29/9 (EURUSD)
 
Confine train/test: 2024-04-30 22:30 UTC (barra 105.614 di 132.018 di `df_is`).
 
| lato | train | test | tolti purge | tolti embargo |
|---|---|---|---|---|
| LONG | 4.428 (48,1% cl.1), 2020-02 → 2024-04 | 1.034 (49,0%), 2024-05 → 2025-05 | 2 | 1 |
| SHORT | 2.215 (47,7%) | 538 (46,1%) | 0 | 0 |
 
Trigger in OOS non usati: 1.325 LONG, 673 SHORT. Test di validazione
superati, inclusi due test di leakage (prezzi OOS / del test stravolti →
etichette train e test invariate).
 
---
 
## Primo modello — run del 29/9 (EURUSD, LightGBM base, senza pesi)
 
Scelte: LightGBM con `PARAMETRI_BASE` prudenti e non ottimizzati
(200 alberi, lr 0,05, profondità 3, 7 foglie, min 50 righe/foglia, seed 42).
Niente soglie di probabilità fisse: le probabilità possono stringersi in un
intervallo molto stretto a seconda del symbol, quindi si legge per **fasce
(quintili)**; la soglia operativa sarà il limite inferiore della fascia
scelta, fissato sul test di `df_is` e applicato tale e quale all'OOS.
 
| lato | AUC train | AUC test | prob. test p10–p90 |
|---|---|---|---|
| LONG | 0,610 | 0,516 | 0,402–0,551 |
| SHORT | 0,665 | 0,497 | 0,352–0,562 |
 
Fasce del test non in ordine crescente (vincenti% e bp non salgono dalla 1
alla 5); differenze fra fasce entro il rumore di campionamento (~±3,5 punti %
di vincenti con ~200 trade per fascia LONG, ~±5 con ~108 SHORT). Distanza
fra AUC train e test = il modello impara regole specifiche del train. Feature
più usate: soprattutto F* di contesto (F10/F11 trend conviction, F5 tall
candle, F2 volatilità, F16 VWAP). Letture di collaudo, non verdetti.
 
---
 
## Pesi di unicità — confronto del 29/9 (EURUSD)
 
| lato | AUC train/test base | AUC train/test con pesi | vincenti% train semplice → pesata |
|---|---|---|---|
| LONG | 0,610 / 0,516 | 0,604 / 0,517 | 48,1% → 50,8% |
| SHORT | 0,665 / 0,497 | 0,667 / 0,494 | 47,7% → 48,3% |
 
Pesi train: LONG da 0,31 a 1,65 (mediana 0,93), SHORT da 0,33 a 1,25.
Con i pesi le probabilità LONG si spostano in alto (p50 test 0,487 → 0,515)
perché i trigger ammassati del train erano più spesso perdenti: pesandoli
meno, la quota di vincenti "vista" dal modello sale. AUC praticamente
invariate, distanza train/test invariata, fasce del test ancora non in
ordine crescente. Lettura di collaudo: l'interruttore funziona, su questi
dati non cambia la capacità di ordinare. Decisione da prendere: se tenerli.
 
---
 
## Decisioni per l'OOS (29/9) e primo run
 
- **Pesi di unicità: attivi.**
- **Fascia operativa: 5** (20% più alto), con possibilità di intervallo
  (`FASCE_OPERATIVE = (4, 5)`).
- **Modello per l'OOS: (a)** quello addestrato sul solo train, stessa scala
  di probabilità da cui viene la soglia.
- L'OOS può essere eseguito più volte: il progetto è una pipeline, non una
  strategia (decisione di Mattia), quindi "bruciarlo" non è un problema.
Run del 29/9 (EURUSD, OOS 2025-05 → 2026-09, modelli pesati):
 
| | soglia (dal test) | OOS presi | OOS vincenti% sel. / tutti | OOS bp lordi sel. / tutti | AUC OOS |
|---|---|---|---|---|---|
| LONG fascia 5 | ≥ 0,563 | 300 (22,6%) | 53,3 / 49,1 | 1,83 / 0,83 | 0,548 |
| SHORT fascia 5 | ≥ 0,530 | 150 (22,3%) | 46,7 / 51,1 | −0,95 / 0,31 | 0,457 |
| LONG fasce 4-5 | ≥ 0,531 | 551 (41,6%) | 53,9 / 49,1 | 2,38 / 0,83 | |
| SHORT fasce 4-5 | ≥ 0,497 | 285 (42,3%) | 48,4 / 51,1 | 0,20 / 0,31 | |
 
Letture di collaudo: la distribuzione delle probabilità OOS è quasi uguale
a quella del test, quindi la soglia fissata sul test prende nell'OOS una
quota simile (22-23% contro il 20% atteso) — il meccanismo della soglia è
portabile nel tempo. LONG e SHORT si muovono in versi opposti rispetto a
"tutti"; con 300/150 trade l'incertezza sulla % vincenti è ~±2,9 / ±4,1
punti. Coerente con il test: ordine del modello non stabile.
 
---
 
## Backtest OOS (VectorBT) — decisioni e run del 29/9
 
Decisioni: VectorBT (coerenza esatta con il target: ingresso Open barra
successiva, uscita Close a 25 barre); **(a) un trade alla volta per lato**
(i trigger con posizione aperta si saltano e si contano); **lotto fisso**
(1 lotto = 100.000 unità, capitale 150.000 perché VectorBT open-source non
gestisce il margine — il backtest si ferma se il capitale non copre il
controvalore); commissione 0,65 bp round-turn, spread escluso. Money
management: step successivo, a pipeline completa.
Selezione feature per importanza: valutata il 29/9 — l'importanza sul train
non coincide con quella sul test (correlazione ~0); se si aggiunge, va
scelta con importanza misurata sul test e confermata sull'OOS.
 
| lato | scenario | trade | saltati | vincenti% netti | trade medio bp netti | PF | max DD % |
|---|---|---|---|---|---|---|---|
| LONG | modello fascia 5 | 227 | 73 | 49,8 | +0,32 | 1,04 | −1,90 |
| SHORT | modello fascia 5 | 143 | 7 | 46,9 | −1,82 | 0,78 | −2,85 |
| COMBINATO | modello fascia 5 | 370 | 80 | 48,7 | −0,51 | 0,93 | −3,27 |
| LONG | tutti i trigger | 653 | 672 | 46,7 | −0,44 | 0,94 | −3,44 |
| SHORT | tutti i trigger | 462 | 211 | 52,4 | +0,10 | 1,02 | −2,46 |
| COMBINATO | tutti i trigger | 1115 | 883 | 49,1 | −0,21 | 0,97 | −2,98 |
 
Test del backtest superati: prezzi di ingresso/uscita, PnL a mano, somma
PnL = equity finale, % vincenti lordi = target, COMBINATO = LONG + SHORT,
errore con capitale insufficiente.
 
---
 
## Stato parametri
 
| dove | valore |
|---|---|
| simbolo | `EURUSD`, M15 (pipeline multi-symbol) |
| `H` (event study e target) | 25 barre |
| `MIN_TRADES` | 200 |
| `RISCALDAMENTO` | 2100 barre |
| trigger selezionati per lato | 4 (2 coda migliore + 2 falliti opposti) |
| `soglia_costi` (target) | 0,65 bp — commissione IC Markets EU Raw Spread su EURUSD. Da ricalcolare se cambia symbol |
| entry / exit price (target) | Open barra successiva / Close a 25 barre dal trigger |
| barriera TP/SL nel target | nessuna |
| split train/test in `df_is` | 80/20 per barre, con purge ed embargo di H |
 
---
 
## Modelli ML — candidati allo studio
 
Idea di partenza di Mattia, non ancora decisa/testata:
 
- **Alberi in ensemble**: XGBoost, LightGBM, AdaBoost — niente scalatura,
  gestiscono feature booleane.
- **MLP**: richiede standardizzazione degli input.
---
 
## Prossimi passi (da stabilire insieme)
 
- Money management (dopo aver completato la pipeline)
- Dopo la chiusura del modello: inserire filtri (F*) e trigger (E*) più
  efficienti — in lista di Mattia
- Confronto con altri modelli (XGBoost, AdaBoost, MLP) sullo stesso
  sistema di misura
- Conferma finale su `df_oos`, solo a modelli già fissati