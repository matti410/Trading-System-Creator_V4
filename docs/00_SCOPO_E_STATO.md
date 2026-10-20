# 00 · Scopo del progetto e stato del tool

**Da leggere per primo.** Aggiornato: 20 ottobre 2026 (riscritto per intero il
17/10: metodo in sette passi qui dentro, solo documenti che esistono nel repo;
stato aggiornato al 19/10; **perimetro solo crypto dal 20/10**, `63` §10.0).

**Repo (pubblico):** `github.com/matti410/Trading-System-Creator_V4`
**Notebook:**
- `Trading_System_Lab_Crypto.ipynb` — il laboratorio guidato in nove passi sui
  dati da exchange, senza codice nelle celle (chiama `engine/vetrina.py`);
- `Trading_Grid_Search_v4_backtesting.ipynb` — la ricerca completa, usata sui
  symbol da exchange;
- `Collaudo_Catalogo.ipynb` — il collaudo del catalogo delle condizioni;
- `Trading_System_Lab.ipynb` — il laboratorio sul broker CFD: **sospeso dal
  20/10/2026, non mantenuto** (resta nel repo, non si aggiorna e non si collauda).

Girano in locale (dati da `dati/`) e su Colab (dati da Google Drive,
`Il mio Drive/Trading-System-Creator_V4/dati/`). I CSV non sono su GitHub.

---

## Cos'è questo progetto

**Uno strumento per scovare strategie di trading.** Una base, che cresce
aggiungendo condizioni di ingresso, filtri, uscite, diagnostiche.

**Perimetro (decisione di Mattia del 20/10/2026, `63` §10.0): solo crypto da
exchange** — Binance e Bybit, spot e perpetual, BTC, ETH, SOL, XRP. Il lato
broker (MT5, CFD, EURUSD e gli altri 8 symbol) è **sospeso**: codice, test,
notebook e dati restano nel repo e si possono riaprire, ma non si sviluppano e
non si usano per misurare. `scarica_dati.py` (MT5) non si usa.

Non è la ricerca di un edge su un symbol. Il **dataset di sviluppo** e della
prova di identità è **BINANCE_PERP_BTCUSDT** M15 (dal 2/1/2020, long e short):
fa girare il codice e fa emergere i difetti degli strumenti. Il giro completo
«su un symbol diverso» si fa su **BYBIT_SPOT_ETHUSDT** (altro exchange, spot,
solo long, altra moneta). Fino al 19/10 il dataset di sviluppo era EURUSD M15:
le misure citate più sotto su EURUSD sono di quel periodo.

---

## LA REGOLA CHE VIENE PRIMA DI TUTTE

> **I risultati sui dati non sono il metro di giudizio del progetto.**

Quando una condizione non produce nulla su EURUSD, **la risposta corretta è
«bene, il tool funziona e me lo dice»**, non «questa strada è morta».

Concretamente, quando si lavora qui:

- **Non si commenta se un sistema "tiene" o no**, a meno che non venga chiesto
  esplicitamente.
- **Non si propone di cambiare asset, famiglia di segnali o approccio** perché
  i `t` sono bassi. Quella è una decisione di ricerca, e la prende Mattia.
- **Non si scrivono conclusioni tipo «capitolo chiuso», «non è un edge da
  inseguire», «la pipeline gira a vuoto».** Sono fuori scopo.
- I numeri che escono dai run servono a **collaudare il tool**: dicono che il
  codice gira, che le occorrenze sono plausibili, che i segni sono coerenti.
  Si riportano come collaudo, non come verdetto.

È stato ripetuto molte volte. Se una risposta scivola nel giudizio sui
risultati, è un errore da correggere, non una sfumatura.

---

## Il metodo: i sette passi

L'ordine conta: ogni passo riceve **congelato** quello che hanno scelto i
passi prima, e non lo ritocca. Ogni scelta «il migliore fra tanti» è una
prova in più nel conteggio dei test multipli (soglia di rumore, `02`).

| passo | cosa si decide | dove (ricerca · Lab) |
|---|---|---|
| 1 | **Orizzonte**: a quante barre si guarda l'effetto di un trigger (H) | event study · Lab 1–2 |
| 2 | **Ingressi**: quali trigger, long e short come candidati separati; la rosa li suggerisce | event study, `rosa_entry` · Lab 3a–3b |
| 3 | **Uscite**: a tempo (sempre attiva, il paracadute), a regola, stop e target adattivi; la rosa dei sistemi | `exit_search_bt`, `rosa_sistemi` · Lab 4–4b |
| 4 | **Giudizio del sistema base** | `giudizio.py` |
| 5 | **Filtri**, uno alla volta, sopra il sistema base | `filter_search_bt`, `due_meta`, `confidenza` · Lab 5 |
| 6 | **Out-of-sample**: la prova sui dati mai visti | Sessione 4 · Lab 6 |
| 7 | **Monte Carlo, money management e sizing** | `montecarlo`, `money_management` · Lab 7 e 9 |

Le regole che valgono passo per passo:

- **Passi 2 e 3, la rosa (dal 18/10).** Dopo l'event study e dopo la ricerca
  delle uscite il tool **suggerisce** un gruppo di candidati (`engine/rosa.py`):
  t netto con la quota di falsi positivi al 20% (Benjamini–Hochberg), positivo
  sulle due metà dell'in-sample, una famiglia ciascuno e |ρ| ≤ 0,3 sui profitti
  giornalieri. Stesso H, solo in-sample. È un cancello per proporre, non per
  validare: la scelta resta di Mattia e i cancelli dei passi 4–6 non cambiano
  (`02`, «La rosa dei candidati»).
- **Passo 3.** Stop e target **non si ottimizzano**: sono un metodo adattivo
  (percentile delle escursioni recenti, `soglie_adattive`), acceso o spento.
  Spenti di default dal 17/9.
- **Passo 4.** **Nessuna soglia automatica decide se un setup ha un edge
  sfruttabile.** Il tool automatizza solo la bocciatura, che è verificabile
  (EV negativo, `t` sotto il rumore, pochi trade): gli esiti sono SCARTATA,
  CAMPIONE CORTO, DA VALUTARE, e da lì decide chi conduce la ricerca.
- **Passo 5.** Entry e uscita restano congelate; si prova **un'idea alla
  volta** (un filtro, o una coppia long/short con lo stesso `pair`). Decide il
  confronto *tenuti vs scartati* dentro il sistema base, oltre la soglia di
  rumore; chi passa deve reggere su **entrambe le metà** dello storico
  (`due_meta`). Sotto il centinaio di trade filtrati ci si ferma (CAMPIONE
  CORTO). La confidenza dei segnali si costruisce e si prova **sopra il filtro
  scelto** (`congela_filtro`), non sul setup nudo. Le quattro regole dei filtri:
  1. `direction=0` solo se usa davvero la sola magnitudo, mai il segno di una
     grandezza con segno;
  2. la finestra del percentile rolling dev'essere molto più larga della
     finestra del valore che classifica;
  3. mai un filtro in OR su due rami opposti: si tengono separati, uno per
     direzione;
  4. nessun filtro sempre vero o sempre falso.
  La pipeline Trend Following applica il filtro nella stessa direzione
  dell'entry (conferma); una Mean Reverting, se ripartirà, lo userà rovesciato.
- **Passo 6.** L'out-of-sample **si apre una volta sola**, a ricerca
  in-sample conclusa. Se lo guardi, cambi qualcosa e lo riguardi, è diventato
  parte della ricerca: quell'out-of-sample è **speso** per quel setup.
- **Passo 7.** Il money management si calibra sull'**in-sample** e si applica
  all'out-of-sample senza ritocchi (`61`).

---

## Dove sta cosa

**Il codice sta sul repo**, i documenti in `docs/`. Nei documenti ci stanno le
**decisioni**, il perché di una scelta, le trappole trovate, le convenzioni.
Le istruzioni per Claude Code sono in `CLAUDE.md`.

| | documento | cosa contiene |
|---|---|---|
| 00 | questo | scopo, metodo, stato, cosa manca |
| 02 | `02_KPI_E_GIUDIZIO.md` | i criteri di lettura di un risultato, le soglie di rumore |
| 10 | `10_DATI_FUSO_BROKER.md` | la regola del fuso del broker, verificata |
| 11 | `11_DATI_QUARANTENA.md` | quarantena, sessioni, entry-metro |
| 20 | `20_CONDIZIONI_TEMPO.md` | E22, E23, F20–F22 e le trappole trovate |
| 21 | `21_COLLAUDO_CATALOGO.md` | test di lookahead e degenerazione su tutto il catalogo, comportamenti di `backtesting.py` |
| 50 | `50_IDEE_DA_ARTICOLI.md` | come trascrivere le idee delle fonti in condizioni: flusso, scheda, convenzioni, trappole, collaudo, consegna, registro delle idee, filtri di regime, sentiment, multi timeframe, lavoro in locale (dati, fuso, pip e costi per symbol) |
| 51 | `51_INDICATORI_TRADINGVIEW.md` | specifica dei 7 indicatori TradingView tradotti in condizioni (13–15/10) |
| 60 | `60_MONEY_MANAGEMENT.md` | incarico di studio sul money management (libro di Unger) |
| 61 | `61_PROPOSTA_MONEY_MANAGEMENT.md` | proposta, decisioni e cosa è stato fatto nelle fasi 0–3 del money management |
| 62 | `62_ATLANTE_E_FLUSSO.md` | incarico di studio: unità di rischio, funding dei perpetual, atlante del trigger, mercato nullo (20/10) |
| 63 | `63_PROPOSTA_ATLANTE_E_FLUSSO.md` | la proposta, il controllo con i documenti di progetto e le decisioni di Mattia (perimetro solo crypto in §10.0) |
| 93 | `93_QUARANTENA_TRADE_E_COSTI.md` | quarantena applicata ai trade e costi del conto Standard (5/10) |
| — | `GUIDA_ANALISI_FONTI.md` | guida per Mattia: come portare una fonte (articolo, video, libro) fino al codice |

Le vecchie note tenute su claude.ai (roadmap, ramo ML, audit, celle da
incollare) non servono più: quello che contenevano di ancora valido è qui
sopra (il metodo) o nel codice e nei test. Il ramo ML è un altro repo
(`Trading-System-Pipeline-ML`).

---

## Cosa c'è nel tool

### Dati e tempo — la base

| modulo | cosa fa |
|---|---|
| `scarica_dati_crypto.py` | scarica dagli exchange (ccxt, sola lettura, senza chiavi) i CSV in `dati/` — l'unico scaricatore in uso dal 20/10 |
| `scarica_dati.py` | scarica da MT5 (sola lettura) i CSV M15 in `dati/` — **sospeso dal 20/10/2026** |
| `engine/mt5_interaction.py` | le funzioni di lettura da MT5 usate da `scarica_dati.py` |
| `engine/simboli.py` | **unica fonte** di pip, classe, contratto, valuta, lotti e leva per symbol (`pip_symbol`, `info_symbol`, `lotti_symbol`, `leva_symbol`) |
| `engine/broker_tz_diagnostic.py` | diagnosi del fuso, `to_utc_index()` |
| `engine/quarantena.py` | `verifica_indice_utc()`, `quarantena()` |
| `engine/quarantena_trade.py` | segnali in quarantena scartati nei motori, spread del rollover sui trade |
| `engine/sessioni.py` | catalogo sessioni in ora locale, `in_sessione()`, `barre_da_apertura()` |
| `engine/livelli.py` | `range_finestra()`, `giorno_fx()`, `al_ultima_apertura()`, `primo_del_giorno()` — vedi `20` trappole 4–5 |
| `engine/indicatori.py` | `aggiungi_indicatori(df)` e tutti gli indicatori nuovi (regola: solo qui) |

**Symbol in uso (dal 20/10/2026):** i 16 da exchange di `SIMBOLI_EXCHANGE`
(Binance e Bybit × spot e perpetual × BTC, ETH, SOL, XRP; M15 dal 2/1/2020 o
dalla prima barra disponibile), scaricati con `scarica_dati_crypto.py`.
**Sospesi** (dati ancora in `dati/`, non si usano per misurare): EURUSD,
GBPUSD, USDJPY, NZDUSD, BTCUSD, US500, USTEC, XAUUSD, DE40 del broker. USDCAD
escluso (in M15 solo da gennaio 2025).

### Motore di ricerca

| modulo | passo |
|---|---|
| `engine/event_study.py` | 1–2, orizzonti e ingressi |
| `engine/exit_search_bt.py` | 3, uscite; `_StrategiaGenerica` è la strategia di tutti i backtest (dal 17/10 legge le colonne per indice: più veloce, stessi trade) |
| `engine/giudizio.py` | 4, t, P(EV<0), soglia rumore, scheda, verdetto |
| `engine/filter_search_bt.py` | 5, filtri; dal 17/10 i backtest girano su più processi (`processi=None` automatico, `1` in sequenza: stessi risultati, `test_velocita.py`) |
| `engine/due_meta.py` | 5, stabilità sulle due metà |
| `engine/famiglie.py` | collaudo e scelta delle condizioni: sovrapposizioni, somiglianze, famiglie (dal 17/10) |
| `engine/rosa.py` | 2–3, la rosa dei candidati: entry dopo l'event study, sistemi dopo le uscite (dal 18/10) |
| `engine/stagionalita.py` | 1–3, profilo orario e baseline oraria della rosa; fasce larghe una barra, per ogni timeframe (dal 18/10) |
| `condizioni_orarie.py` | 2–3, entry e uscite a orario: `ORA_LONG_@HH:MM`, `ORA_SHORT_@HH:MM`, `X_ORA_@HH:MM`, `X_INVERSIONE_TREND` (dal 19/10) |
| `engine/confidenza.py` | 5, confidenza dei segnali: griglia volatilità × trend, soglia come filtro |
| `engine/volatility_features_engineering.py` | file di Mattia, invariato: `confidenza.py` usa `feat_historical_volatility` e `build_labels` |
| `engine/montecarlo.py` | 7, yardstick 10/20/40/100 trade, Monte Carlo, sizing, grafici |
| `engine/money_management.py` | 7, modulo puro (solo numpy e pandas): rischio fisso, secure f, Kelly e optimal f come riferimento, Monte Carlo moltiplicativo, tabella di controllo, z-score (`61`) |
| `engine/mm_adattatore.py` | 7, dai trade del V4 alla tabella del money management: rischio a stop o a volatilità, valore del pip trade per trade |
| `engine/costi.py` | costi per strumento; lo spread usato dai notebook è il listino del conto Standard (`SPREAD_LISTINO_PIPS` in `vetrina.py`) |
| `engine/exchange.py` | dati e costi da exchange crypto (dal 19/10): commissioni di listino, lettura dei CSV, scaricamento con ccxt in sola lettura, controlli dei dati (`50` §12) |
| `engine/metriche.py` | `avg_trade` / `avg_trade_netto` / `costo_pips` |
| `engine/controlli.py` | `avviso_capitale`: avvisa quando il prezzo supera il capitale |
| `engine/vetrina.py`, `vetrina_verifica.py`, `vetrina_trigger.py` | le nove schermate dei due Lab; `carica_storico` e `costi_storico` leggono dati e costi per tutti e tre i notebook (dal 19/10) |
| `engine/splitting.py`, `equity_plot.py`, `alpha_ops.py`, `vwap_ops.py`, `registry.py`, `collaudo_catalogo.py` | supporto |

Firme utili:

```python
# engine/costi.py
parametri_backtest(symbol, bars=None, valuta_conto="USD", percentile=75.0,
                   spread_pips=None, usa_mt5=True) -> {"spread":…, "commission":…}
deriva_costo_nel_tempo(...)     il costo anno per anno — obbligatorio su BTCUSD

# engine/giudizio.py
t_stat(pips) · t_welch(a, b) · p_ev_negativo(pips) · ic_ev(pips)
soglia_rumore(k, alpha=0.05)    Šidák; k=17 → 2,97 · k=42 → 3,23
tenuti_scartati(...) · drawdown_montecarlo(pips) · scheda_strategia(...) · verdetto(...)

# engine/confidenza.py
congela_filtro(fs, filtro_scelto)                              -> (entry_long, entry_short) con il filtro dentro
congela_confidenza_nota(entry_l, entry_s, conf_l, conf_s)       -> entry ristrette ai segnali a confidenza nota
cella_contesto(df, direzione, finestra=500, finestra_vol=20)   -> 0..3
esiti_trade(trades, df, pip_size, commission)                  -> una riga per trade
confidenza_rolling(df, esiti, direzione, finestra_trade=500, min_obs=30)
registra_filtro_confidenza(soglie, conf_long=, conf_short=, metrica="pips_medi")
report_calibrazione(esiti, df, split, conf_long=, conf_short=, mostra_oos=False)
plot_oos_confidenza(trades_senza, trades_con, pip_size, commission)

# engine/collaudo_catalogo.py
verifica_lookahead(df_grezzo, prepara=aggiungi_indicatori, tagli_per_condizione=5)
verifica_degenerazione(df, min_occorrenze=30, copertura_max=0.95, distanza_grappolo=8)
condizioni_registrate() · tagli_standard(indice) · mercato_sintetico()
```

Sul lato broker (sospeso dal 20/10) il conto di riferimento è il **Standard**:
costo tutto nello spread, commissione zero. Uno spread che manca nel listino non si inventa: il notebook
si ferma e indica la riga da aggiungere (`50` §12). Sui symbol da exchange
(dal 19/10) il costo è la commissione taker per lato del listino dell'exchange,
livello base, più uno spread di un passo; il funding dei perpetual non è
ancora contato (`50` §12, «Dati da exchange crypto»).

### Catalogo delle condizioni

| file | contenuto |
|---|---|
| `entry_long.py` / `entry_short.py` | 36 entry long e 35 short accese (fino a E41); 21 spente nello sfoltimento del 17/10 |
| `entry_composita.py` | entry composte: più trigger in OR sullo stesso lato |
| `entry_metro.py` | 5 entry-metro temporali per lato (righello, non candidate) |
| `filter_conditions.py` | 35 filtri accesi (fino a F40); 12 spenti nello sfoltimento del 17/10 |
| `vwap_regime_filter_conditions.py` | 5 filtri di regime VWAP |
| `exit_long.py` / `exit_short.py` | 5 uscite a regola per lato |

Con tutto registrato (metro short comprese) il registry contiene **129
condizioni**: 81 entry (71 vere e 10 metro), 38 filtri, 10 uscite (conteggio del
19/10: 117 dopo lo sfoltimento del 17/10, un rappresentante per famiglia, `50`
§10 septies, più le quattro entry del momentum intraday del 18/10 e le quattro
delle coppie di ore UTC e le due del momentum dopo un salto e le due dei quintili giornalieri del 19/10; prima dello
sfoltimento erano 152). Le entry e le uscite a orario (`condizioni_orarie.py`)
e le composite non sono nel conto: si registrano su richiesta. Le condizioni spente hanno la riga del dizionario tra
commenti con il motivo: la funzione resta e si riattiva togliendo il `#`.

I filtri di confidenza (`CONF_…`) non sono nel catalogo: nascono nel notebook,
da `registra_filtro_confidenza`, dopo il sistema base. Non passano dal collaudo
del catalogo (non sono funzioni del solo prezzo); il loro lookahead lo verifica
`test_confidenza.py` troncando l'intera catena backtest → esiti → confidenza.

Non c'è caricamento automatico per scansione di cartella: la registrazione è
esplicita, con funzioni tipo `registra_trigger_long()` che scorrono un
dizionario. **Per aggiungere una condizione servono due cose: la funzione, e la
riga nel dizionario del suo file.** Un *file* di condizioni nuovo va aggiunto
anche alla lista `REGISTRAZIONI` di `Collaudo_Catalogo.ipynb`.

### Collaudo

**Suite da terminale (19/10, dati da exchange crypto): 32 file `test_*.py`, 1227 test, tutti superati**
(pandas 3.0.6, in locale). Si lanciano dalla cartella del progetto, su Windows
con `PYTHONIOENCODING=utf-8`; l'ultima riga di ognuno dev'essere
`RISULTATO: n/n test superati`. Alcune parti leggono i CSV di `dati/` e, se
mancano, si saltano da sole (`test_money_management.py` invece si ferma e lo
dice).

**Notebook `Collaudo_Catalogo.ipynb`** (*Esegui tutto*, 2–3 minuti):
A1 trappole di lookahead · A2 casi di degenerazione · B lookahead sul catalogo
intero (atteso: 0 LOOKAHEAD) · C degenerazione su EURUSD vero · D e E
comportamenti di `backtesting.py`. Dettagli in `21_COLLAUDO_CATALOGO.md`.

**Versioni bloccate:** `TA-Lib==0.8.1`, `backtesting==0.6.6` (cella di avvio dei
tre notebook). Si cambiano solo insieme, poi si rilancia il collaudo: la
sezione D dice se il tool regge.

**Da rilanciare ogni volta che si aggiunge una condizione.**

---

## Cosa manca AL TOOL

In ordine di importanza per uno strumento che deve scovare strategie.

### ~~1. Nessun test di lookahead sull'intero catalogo~~ — FATTO il 24/9

`verifica_lookahead` in `engine/collaudo_catalogo.py`, per troncamento, su ogni
condizione registrata e su ogni indicatore. Al primo giro ha trovato un
lookahead vero in `range_finestra` (E22, F21), corretto. Vedi `21`.

### ~~2. Nessun controllo di degenerazione automatico~~ — FATTO il 24/9

`verifica_degenerazione`, stesso modulo. Si legge sui dati veri, senza
promosso/bocciato. Vedi `21`.

### 3. Il conteggio dei test multipli — fatto per chiamata il 24/9, resta il cumulato

Ogni passo che sceglie «il migliore fra tanti» calcola da sé la soglia di
rumore sulle prove di **quella chiamata** e mette la colonna `oltre_rumore`:

- **event study** (passi 1–2): k = entry misurate, più la scelta del picco
  sull'orizzonte (`soglia_rumore_orizzonte`);
- **uscite** (passo 3): `t_stat` sui pips netti e soglia di Šidák sulle righe;
- **filtri** (passo 5): le soglie di confidenza sono righe di una loro
  chiamata: contano solo fra loro.

Tarate su entry casuali: sezione E del notebook di collaudo, vedi `21`.

**Resta aperto:** le prove dei passi precedenti non si sommano (entry → uscite →
filtri → confidenza). Ogni soglia è un pavimento. Per le idee che arrivano da
fonti testuali il conto cumulato lo tiene a mano il registro di `50` (§10).

### ~~4. Le sovrapposizioni fra condizioni~~ — FATTO il 17/10

`verifica_degenerazione` non dice se **due condizioni scattano quasi sulle
stesse barre**: in quel caso sono una prova sola travestita da due. Dal 17/10
lo misura `engine/famiglie.py`: `sovrapposizioni` (una riga per coppia, quota
e quante volte il caso, regola dei doppioni di `50` §7.5), `somiglianze` e
`famiglie` (condizioni raggruppate a somiglianza media ≥ 60%). Usa solo i
segnali, mai i risultati dei trade. Collaudo: `test_famiglie.py`.

### 5. Portabilità multi-asset — fatta su 9 symbol del broker e 16 da exchange (lato broker sospeso dal 20/10)

Il primo run su BTCUSD (25/9) ha trovato due difetti, corretti e coperti da
`test_portabilita.py`: **prezzo > capitale** (`backtesting.py` non compra
frazioni e scartava gli ordini in silenzio; ora `avviso_capitale` lo dice e il
capitale sta in `costi["cash"]`) e **BTCUSD classificato forex senza MT5**.

Dal 10/10 il tool gira su 9 symbol veri, con lookahead e degenerazione puliti.
Altri difetti trovati e corretti: pip dedotto dal prezzo (su US500 cambiava fra
IS e OOS), contratto dell'oro, indici classificati "altro", valore del pip per
lotto su oro e indici. Ora il pip è **fisso per symbol** (`engine/simboli.py`).
Dettagli in `50` §12.

Resta: strumenti senza weekend e orari diversi provati solo sui dati veri,
mai su asset sintetici costruiti apposta (`mercato_sintetico()` genera solo
forex con weekend, prezzo 1,10).

### 6. Un runner unico dei test

Ventiquattro suite da terminale più un notebook di collaudo, da lanciare a mano.

### 7. Etichetta UTC fantasma — origine non confermata

Da qualche parte un `tz_localize('UTC')` veniva applicato a ore server.
`verifica_indice_utc()` lo intercetta, ma è una difesa, non una cura. La
probabile origine (una riga commentata `pd.to_datetime(df.index, utc=True)` nel
notebook principale) non c'è più.

### 8. Metodologia non ancora costruita

- **Diagnostica delle pause sistematiche** per simbolo
- **Festivi di borsa**: decisione rimandata, serve al filtro NYSE
- **Interruttore sulla curva dei profitti**: rimandato per scelta di Mattia
  (`61` §14.6). Il money management sulle crypto non chiede più un repo
  gemello: dal 19/10 la versione crypto sta in questo repo e usa lo stesso
  modulo (1 lotto = 1 moneta, conto in USDT, leva scelta entro il tetto
  italiano)

Fatti: incertezza dell'event study corretta per i grappoli (24/9), confidenza
dei segnali (25/9), yardstick e sizing (26/9), money management fasi 0–3
(16/10, `61`), profilo orario e baseline oraria (18/10, `02`; il giorno della
settimana lasciato fuori per scelta di Mattia).

---

## Problemi aperti nel codice esistente

| cosa | stato |
|---|---|
| `engine/vwap_ops.py` taglia la giornata a `df.index.date`, cioè a mezzanotte UTC, non al rollover delle 17:00 NY. La colonna `vwap` e i 5 filtri VWAP usano quindi una giornata diversa da `confidenza.py`, che usa `giorno_fx()`. Trovato il 25/9, non toccato | da decidere |
| `ExitSearchBT.top()` ordina per `sharpe`, mentre la regola dice che decide `avg_trade_netto` | da decidere |
| stop non attivo sulla barra d'ingresso (~0,2% dei trade, bias a favore del backtest) | rimandato per scelta |
| il notebook di ricerca clona il repo con il token: senza il secret `GITHUB_TOKEN` si ferma, mentre il Lab prova il repo pubblico | non bloccante |

---

## Scoperte da non perdere

**I trade filtrati non sono un sottoinsieme del sistema base.** Scartando un
trade il filtro libera il posto e rende tradabili segnali prima bloccati da una
posizione aperta (`exclusive_orders=True`). Misurato: dal 3% al 12% di trade
nuovi per filtro. Rende illecito qualunque test appaiato. Da qui `tenuti vs
scartati`.

**Lo stop non è attivo sulla barra d'ingresso.** `trade.sl` viene assegnato a
trade già aperto, quindi diventa operativo dalla barra dopo. Impatto misurato
con `perc_sl=90`: ~0,2% dei trade. Il bias è sempre a favore del backtest.

**`avg_trade` è LORDO di commissioni.** `backtesting.py` addebita la
commissione alla cassa, non al prezzo di fill. Lo spread invece **è** dentro i
prezzi. Il numero da confrontare con zero è `avg_trade_netto`.

Attenzione alla conversione, è l'errore che raddoppia tutto: `backtesting.py`
addebita `commission` **su entrambi i lati**, quindi
`commission = costo_round_turn / 2`. Lo `spread` si applica una volta sola e ci
va intero.

**Il capitale deve superare il prezzo (25/9).** Sotto quella soglia `backtesting.py`
scarta gli ordini senza errore. Su BTCUSD con `cash=10.000` sparivano l'85% dei
trade. I pips per trade non dipendono dal capitale: si alza `cash` e basta.

**Un test di lookahead che tiene l'indice intatto** non vede i difetti legati
alla *fine* dello storico — che nel live è sempre la barra corrente. Per questo
il collaudo del catalogo tronca invece di sporcare (24/9).

---

## Dove siamo (19/10/2026; perimetro aggiornato il 20/10)

- **Perimetro (20/10):** solo crypto da exchange; lato broker sospeso; dataset
  di sviluppo BINANCE_PERP_BTCUSDT, giro di controllo su BYBIT_SPOT_ETHUSDT
  (`63` §10.0). Notebook vivi e allineati: Lab crypto e ricerca. Le suite
  `test_*.py` si lanciano tutte, comprese quelle sui symbol del broker (non
  chiedono MT5): se una si rompe, si è toccato codice condiviso.
- **Prossimi lavori, approvati il 20/10 (`63` §10):** giornata delle crypto a
  00:00 UTC → unità di rischio (bp e ATR) → funding dei perpetual → mercato
  nullo sulla pipeline di oggi → atlante del trigger → mercato nullo con
  l'atlante. Un ramo ciascuno.
- **Catalogo:** 129 condizioni (71 entry, 38 filtri, 10 uscite, 10
  entry-metro), collaudate (lookahead e degenerazione) su 9 symbol. Dalle fonti
  testuali: 53 prove al 19/10, registro in `50` §10.
- **I notebook** (ricerca, Lab crypto; il Lab broker è sospeso dal 20/10)
  leggono da `dati/` (o da Drive), con pip fisso per symbol, costi di listino,
  fuso controllato. I due vivi si aggiornano sempre insieme (`CLAUDE.md`).
- **Dati da exchange crypto (19/10):** 16 symbol (Binance e Bybit, spot e
  perpetual, BTC ETH SOL XRP), M15 dal 2/1/2020, scaricati con
  `scarica_dati_crypto.py` (ccxt, sola lettura, senza chiavi). Ora UTC, nessun
  rollover, commissione taker di listino, leva al massimo quella italiana
  (perpetual 2, spot 1), spot solo long. Lab dedicato:
  `Trading_System_Lab_Crypto.ipynb`. Timeframe M5–H4 nei Lab e nella ricerca.
- **La rosa dei candidati (18/10):** il tool suggerisce un gruppo di entry
  (dopo l'event study) e di sistemi (dopo le uscite), positivi e diversi fra
  loro; sceglie Mattia (`02`, «La rosa dei candidati»). Dal 18/10 ogni
  candidato si confronta con il mercato **della stessa ora** (baseline oraria),
  e il profilo orario è nel passo 2 del Lab e in 1.2 bis della ricerca.
- **Condizioni orarie (19/10):** le ore del profilo diventano entry
  (`ORA_LONG_@HH:MM`, `ORA_SHORT_@HH:MM`) e uscite (`X_ORA_@HH:MM`,
  `X_INVERSIONE_TREND`); l'ora scritta è sempre quella in cui il trade si apre
  o si chiude (`02`, «La baseline oraria»).
- **Momentum intraday (18/10, primo paper):** E36 ed E37 da Shen, Urquhart,
  Wang (Bitcoin, 2022) e Gao e altri (S&P 500, 2018): alle 16:30 di New York si
  entra nella direzione della mattina e si esce alle 17:00 (`X_ORA_@17:00`);
  registro di `50`, riga 15.
- **Coppie di ore UTC (19/10, secondo paper):** E38 ed E39 da Wen, Bouri, Xu,
  Zhao (crypto, 2022): E38 entra alle 21:00 UTC nel verso dell'ora 07:00→08:00
  UTC ed esce alle 22:00 (`X_ORA_@22:00_UTC`); E39 entra alle 12:00 UTC contro
  il verso dell'ora 11:00→12:00 ed esce alle 13:00 (`X_ORA_@13:00_UTC`). Il
  suffisso `_UTC` tiene l'ora UTC qualunque sia la piazza. Sul broker d'estate
  E38 cade nella quarantena del rollover (orari non adattati). Il primo paper
  della coda (quarti d'ora, Kim e Hansen) è scartato: serve il lato
  dell'aggressore nei primi 10 secondi, riapribile coi dati da exchange.
  Registro di `50`, righe 16 e 17.
- **Momentum dopo un salto (19/10, terzo paper):** E40 da Baltussen, Da,
  Lammers, Martens (JFE 2021): al primo controllo di mezz'ora in cui il
  rendimento dalla chiusura delle 17:00 NY di ieri esce dal 10°–90° percentile
  dei rendimenti giornalieri (ultime 250 giornate) si entra nel verso del salto
  e si esce alle 17:00 (`X_ORA_@17:00`). Registro di `50`, riga 18.
- **Quintili del rendimento giornaliero (19/10, quarto paper, variante di
  Mattia):** E41 da Liu e Tsyvinski (RFS 2021): se la giornata appena chiusa
  (mezzanotte UTC) è nel 5° quintile delle 300 giornate precedenti si va long,
  nel 1° short; l'uscita è quella del sistema. Registro di `50`, riga 19.
- **Lab in nove passi:** configura, esplora, trigger, uscite, trova la
  strategia, scheda (out-of-sample), money management, verifica dei trade,
  stress test.
- **Money management (fasi 0–3, `61`):** limiti dei lotti e leva da MT5,
  rischio fisso in percentuale con secure f, tabella di controllo, z-score,
  modello a volatilità (predefinito) confrontato con il rischio fisso; lo stress
  test prende il drawdown dalla sezione 7.
- **Velocità (17/10):** `trova_strategia` da circa 62 a 26 secondi su Colab,
  risultati identici. Un motore più veloce (simulatore proprio) resta un'opzione
  solo se servirà.

**Aperti, per scelta di Mattia:** interruttore sulla curva dei profitti.
**Aperti nel tool:** runner unico (punto 6); il funding dei perpetual nei
risultati (fase 2 della versione crypto, lavoro B di `63`); Kraken (via API solo le ultime 720
barre spot: servono i suoi CSV trimestrali). **Prossimo, approvato da Mattia il 18/10:** fonti con un
motivo economico, una alla volta con il processo di `50`. Dal 18/10 (Mattia):
si passerà alle crypto, con dati da exchange e non dal broker CFD; quindi
approcci generalisti, niente idee specifiche del forex (i fixing restano fuori).
Fatti il momentum intraday (riga 15 del registro) e i primi quattro paper della
coda (righe 16–19). La coda dei prossimi paper
e degli ebook è in `GUIDA_ANALISI_FONTI.md` §11.6.

---

## Convenzioni di lavoro

- **Metodologia prima, codice dopo.** Le decisioni si risolvono a parole; poi si
  propone il progetto (funzioni, firme, cosa restituisce) e si aspetta il via
  libera.
- **Niente aggiunte non richieste.** Ciò che va oltre la richiesta si propone.
- **Ogni pezzo di codice passa un collaudo prima della consegna**, con casi a
  risultato noto — non «sembra ragionevole».
- **Verifica empirica prima della lettura del codice**: i comportamenti di
  `backtesting.py` si confermano con test discriminanti, non si deducono.
- **Consegna:** in locale Claude Code modifica i file su un ramo, lancia tutti i
  test e apre la Pull request; il merge lo fa sempre Mattia (`CLAUDE.md`,
  `50` §9.1). La consegna "a parti" vale solo per le chat (`50` §9.2).
- **Modifiche all'engine il più possibile additive**; quando non è possibile, la
  modifica va dichiarata.
- **Sempre spiegare come si esegue il codice.** Mattia non è un informatico.
