# 82 · Proposta: la fabbrica di strategie

**Data:** 5 novembre 2026, aggiornata il 7 novembre. **Risponde a:** `81_FABBRICA_STRATEGIE.md`, versione del 06/11 (qui «l'incarico»).
**Stato:** L1 e L2 scritti; il resto è testo. Revisione chiusa con Mattia il 05/11, il 06/11 e il 07/11 (§8). Il codice parte con il via di Mattia, lavoro per lavoro.

**Indice:** §0 In breve · §1 Le regole del progetto toccate · §2 I file nuovi · §3 La pipeline, punto per punto ·
§4 L'ottimizzatore · §5 La velocità · §6 Config e scheda · §7 Il notebook · §8 Decisioni di Mattia (05/11) · §9 I lavori e i tempi ·
§10 Cosa ho letto

---

## §0 · In breve

La fabbrica prende uno spazio di ricerca deciso prima di guardare i dati, prova circa **100.000 strategie** su **un asset alla volta**, scarta da sola e consegna poche schede. Una ricerca dovrebbe durare **circa 15 minuti** sul PC di Mattia (stima in §5).

- **Che cosa decide:** il **test individuale**, cioè il t netto della strategia contro la soglia per una prova sola (1,96), in selezione e in cassaforte.
- **Il conto delle prove** della fabbrica e la soglia che gli corrisponde stanno sulla scheda, solo da leggere.
- **La fabbrica è separata dal Lab:** non legge e non scrive il conto del Lab né il diario dello studio. Ha solo il suo registro.
- **La cassaforte:** le strategie si congelano e si scrivono nel registro prima di leggere una barra. Ogni strategia entra una volta per tratto di cassaforte; strategie nuove possono entrare, e il registro tiene quante sono entrate in ogni tratto.

BINANCE_PERP_BTCUSDT M15 serve a costruire e collaudare la pipeline: i suoi risultati sono collaudo, non verdetto.

---

## §1 · Le regole del progetto toccate

| regola di oggi | cosa chiede l'incarico | come si fa |
|---|---|---|
| «Parametri fissati a priori, mai ottimizzati sui dati» (`CLAUDE.md`); stop e target «mai ottimizzati» (`docs/00`) | ottimizzare i parametri | eccezione **solo** dentro `engine/fabbrica/`, stop e target compresi, con ogni valutazione contata. Catalogo e Lab restano come sono |
| «Condizioni nei dizionari di `entry_long.py`…» | blocchi in `engine/fabbrica/` | i blocchi parametrici non entrano nei dizionari: cambierebbero la rosa del Lab, `versione_catalogo` e il conteggio delle 143 condizioni |
| «Nuovi indicatori solo in `engine/indicatori.py`» | codice nuovo in `engine/fabbrica/` | gli indicatori nuovi (Donchian, ATR relativo) vanno in `indicatori.py`, solo aggiunte; in `fabbrica/` solo le regole che li usano |

---

## §2 · I file nuovi

Tutti additivi. **Il motore non si modifica**, quindi niente prove d'identità: bastano le suite (`CLAUDE.md`). Lab Crypto e Grid Search restano identici; le uniche righe che toccano file esistenti sono elencate sotto.

| file | contenuto | lavoro |
|---|---|---|
| `engine/fabbrica/ottimizzatore.py` | griglia a passo largo, algoritmo genetico; non sa nulla di trading | L1 |
| `engine/fabbrica/funzioni_prova.py` | Rastrigin, Sphere, Rosenbrock, Ackley | L1 |
| `engine/fabbrica/blocchi.py` | i blocchi con parametri e intervalli | L2 |
| `engine/fabbrica/cache.py` | indicatori e maschere già calcolati | L2 |
| `engine/fabbrica/dati.py` | i tre pezzi di dati e il sigillo sulla cassaforte | L3 |
| `engine/fabbrica/config.py` | lettura, controllo e impronta della config | L3 |
| `engine/fabbrica/generatore.py` | teorie da modelli × blocchi | L3 |
| `engine/fabbrica/valutatore.py` | da una strategia ai bp netti e alle misure | L3 |
| `engine/fabbrica/ricerca.py` | passi 1 e 2, altopiano, ripresa | L3 |
| `engine/fabbrica/registro.py` | registro delle ricerche e conto delle prove | L3 |
| `engine/fabbrica/selezione.py` | condizione 2, test individuale, famiglie | L4 |
| `engine/fabbrica/cassaforte.py` | strategie congelate, ingresso, registro della cassaforte | L4 |
| `engine/fabbrica/schede.py` | scheda `.md` e `.json` | L5 |
| `engine/vetrina_fabbrica.py` | le funzioni chiamate dalle celle | L5 |
| `Fabbrica_Strategie_Crypto.ipynb` | il notebook | L5 |
| `test_fabbrica_*.py` | una suite per lavoro, ultima riga «RISULTATO: n/n» | L1–L5 |

**Modifiche additive a file esistenti, dichiarate:** `engine/indicatori.py` (L2, indicatori nuovi); `suite_rapida.py` (L1, solo se serve per legare le suite nuove al codice); `CLAUDE.md` e `docs/00` (L5, terzo notebook).
Nessun pacchetto nuovo da installare: numpy, pandas, numba e TA-Lib ci sono già.

---

## §3 · La pipeline, punto per punto

### P1 · I dati in tre pezzi

**Come si fa.** Una ricerca lavora su un solo asset, symbol e timeframe scelti nella config. I confini stanno nella config come una data di inizio e tre durate (§6), le stesse su ogni asset. La prima finestra è:

| pezzo | da | a | barre BTC perp M15 (circa) | quota |
|---|---|---|---|---|
| ricerca | 02/01/2020 | 30/06/2023 | 122.500 | 51% |
| selezione | 01/07/2023 | 15/06/2025 17:30 | 68.700 | 29% |
| cassaforte | dopo il 15/06/2025 17:30 | 19/10/2026 13:00 (ultima barra comune a tutti i symbol) | 47.200 | 20% |

- Il 15/06/2025 17:30 coincide con il confine dello studio, ma nasce dalla config: la fabbrica non legge i file dello studio.
- La scelta del 30/06/2023 è solo una proporzione circa 64/36 fra ricerca e selezione, decisa senza guardare i risultati.
- Le barre dopo la data finale restano fuori dalla ricerca.
- **Finestra scorrevole** (decisione di Mattia, 06/11; il codice è di L3): ricerca, selezione e cassaforte hanno durata fissa (nella config) e si spostano in avanti insieme. Uno spostamento è ammesso solo se la nuova cassaforte è fatta di barre mai usate come cassaforte per quell'asset (spostamento ≥ durata della cassaforte); altrimenti la config si ferma con un errore. Ogni tratto di cassaforte ha il suo conto delle strategie entrate.

**Si riusa.** `vetrina.carica_storico`, `vetrina.costi_storico`, `exchange.leggi_funding`, `exchange.controlla_storico`, `exchange.copertura_funding`,
`exchange.solo_long`, `vetrina.cartella_dati_avvio`. I costi si calcolano sul pezzo tagliato, non sul file intero
(`costi_exchange` usa il prezzo mediano del `df` che riceve).

**Nuovo** (`dati.py`).
- `carica_pezzi(symbol, timeframe, confini, cartella) -> Pezzi`: legge, taglia subito e restituisce ricerca e selezione; la cassaforte resta sigillata.
- `Pezzi.apri_cassaforte(permesso) -> DataFrame`: senza il permesso creato da `cassaforte.py` si ferma con un errore.
- `impronta_pezzo(df) -> str`: impronta (hash) dei prezzi; se cambia fra ricerca e selezione, tutto si ferma.

**Collaudo.** Il test del veleno, sotto il passo P8. Inoltre: pezzi che non si sovrappongono e non lasciano barre fuori; symbol fuori tabella fermo con errore;
impronta che cambia se cambia una barra.

### P2 · La config

**Come si fa.** Un file JSON (§6) scritto dal notebook prima del lancio. L'impronta si calcola sul contenuto in forma ordinata, seme compreso.
Stessa impronta = stessa ricerca, che si può riprendere. Impronta diversa = ricerca nuova, con le prove che si sommano.

**Si riusa.** `exchange.simboli_exchange` per controllare il symbol; `registro_dataset.chiave_dataset` (solo la funzione che compone la chiave).

**Nuovo** (`config.py`).
- `leggi_config(percorso) -> dict`: controlla campi e intervalli e si ferma se manca qualcosa.
- `impronta_config(config) -> str`.
- `salva_config(config, cartella) -> str`: scrive solo in una cartella nuova; ritorna l'id della ricerca.

**Collaudo.** Stesso contenuto con le chiavi in altro ordine = stessa impronta; un valore cambiato = impronta diversa; salvataggio che non sovrascrive; campi mancanti che fermano tutto.

### P3 · Il generatore

**Come si fa.** Per ogni lato e per ogni modello, tutte le combinazioni di blocchi. Si scarta una teoria con due blocchi della stessa famiglia.
La famiglia dei blocchi del catalogo si misura con `famiglie.py` sul solo pezzo di ricerca (usa i segnali e non i risultati, quindi non è una prova);
per i blocchi parametrici è dichiarata nel blocco e controllata sui valori centrali. Sullo spot, solo long.

**La misura decide (06/11).** Il controllo di L2 mette **ADX e ATR relativo nella stessa famiglia** (ATR relativo sta per il 62,5% dentro ADX, oltre il 60%): non stanno mai nella stessa teoria.

**Quante teorie**, con la lista di P-L2 qui sotto e i modelli T+U, T+F+U, T+F+F+U: 7 trigger × (1 + 7 + 20 coppie di filtri ammesse) × 3 uscite = **588 per lato, 1.176 sui perpetual**.

**I valori degeneri (07/11).** All'avvio di ogni ricerca, per ogni blocco con parametri e per ogni combinazione della griglia del passo 1, si misura `verifica_degenerazione` sul solo pezzo di ricerca (solo segnali, non è una prova e non entra nel conto). Le combinazioni degeneri escono dalla griglia, e i minimi e massimi dello spazio dello zoom seguono la griglia rimasta. Se un blocco resta senza valori, esce dalla config. L'elenco dei valori tolti, con la quota di barre vere, va nel registro della ricerca e su ogni scheda.

**Si riusa.** `famiglie.famiglie` e, per registrare i blocchi per il tempo della misura, `registry.register_entry`, `remove_entries`, `remove_filters`.

**Nuovo** (`generatore.py`).
- `genera_teorie(config, famiglie_blocchi) -> list[Teoria]`, ognuna con un id stabile.
- `spazio_teoria(teoria) -> Spazio`: i parametri e i loro valori per l'ottimizzatore.

**Collaudo.** Conteggio esatto su una lista piccola fatta a mano; nessuna teoria con due blocchi della stessa famiglia; nessuna teoria short sullo spot; stesso ordine a ogni giro; registro delle condizioni identico prima e dopo la misura.

### P-L2 · I blocchi (lista approvata, §8)

Scelti **per meccanismo diverso, senza guardare i risultati**. Tenuti fuori di proposito i trigger che `74` §2 segna come già visti in cima alla rosa (E21, E39) e quello nato da una scheda della mappa (E45).
Il meccanismo qui sotto è stato **confermato in L2 leggendo le condizioni**: E5 e X3 erano diversi da come li avevo dedotti dai nomi e sono stati rietichettati (§8), le liste non cambiano. Il controllo con `famiglie.py`, che guarda solo i segnali e non conta prove, non ha trovato doppioni.

**Timeframe da M1 a D1.** Intervalli in **ore**, convertiti in barre secondo il timeframe: niente costanti da M15.
- Un valore diventa la **barra più vicina**, a metà strada verso l'alto, **minimo 1 barra**. Ore zero o negative si fermano con un errore.
- **Minimo di 5 barre (07/11)** per periodo di RSI, periodo di ADX e ATR lungo: i valori sotto salgono a 5. L'ATR breve resta con minimo 1 barra, come durate e canale di Donchian.
- Nella griglia i **valori doppi dopo l'arrotondamento si tolgono**: su D1 le uscite a 1, 2, 4 e 8 ore diventano una sola, 1 barra.
- Le **ore effettive** (barre × durata della barra) si leggono dal blocco, per la scheda: `ore_effettive`, `griglia_ore`, `finestre_ore`.
- I blocchi del catalogo restano come sono: un blocco su un timeframe dove non scatterebbe mai ferma la config con un errore (E5 da M1 a D1; E36 da M1 a M30; E47 M5 e M15; E49 ed E51 da M5 a H1; F20 fino a H4, su D1 ferma la config perché la barra è sempre quella delle 00:00). I filtri con finestre in barre (F2, F3, trend, F25) restano così, e il blocco espone le loro finestre in ore.

**Griglia e spazio.** La **griglia** contiene i valori larghi del passo 1. Lo **spazio** di ogni parametro ha lo stesso minimo e massimo della griglia e il **passo più fine**: 1 barra per i parametri in ore, 1 per le soglie intere (RSI, ADX, percentile dello stop), 0,1 per la soglia di ATR relativo. Lo zoom (P5) si muove nello spazio.

**Le griglie in barre su H1, H4 e D1.** Su M1, M5 e M15 il minimo di 5 barre non cambia nulla; su M30 solo le 2 ore di RSI, da 4 barre a 5.

| parametro | valori in ore | H1 | H4 | D1 |
|---|---|---|---|---|
| durata dell'uscita | 1, 2, 4, 8 | 1, 2, 4, 8 | 1, 2 | 1 |
| periodo RSI | 2, 4, 6, 9, 12 | 5, 6, 9, 12 | 5 | 5 |
| periodo ADX | 4, 6, 9 | 5, 6, 9 | 5 | 5 |
| canale di Donchian | 4, 8, 12, 24, 48, 96 | 4, 8, 12, 24, 48, 96 | 1, 2, 3, 6, 12, 24 | 1, 2, 4 |
| ATR breve | 2, 4 | 2, 4 | 1 | 1 |
| ATR lungo | 24, 48, 96 | 24, 48, 96 | 6, 12, 24 | 5 |

Dove il minimo solleva il valore, le ore effettive escono dall'intervallo in ore: 5 barre di RSI o ADX sono 20 ore su H4 e 120 su D1; 5 barre di ATR lungo su D1 sono 120 ore. La scheda riporta le ore effettive.

**I valori degeneri (07/11).** All'avvio di ogni ricerca, per ogni blocco con parametri e per ogni combinazione della griglia del passo 1, si misura `verifica_degenerazione` sul solo pezzo di ricerca (solo segnali, non è una prova e non entra nel conto). Le combinazioni degeneri escono dalla griglia, e i minimi e massimi dello spazio dello zoom seguono la griglia rimasta. Se un blocco resta senza valori, esce dalla config. L'elenco dei valori tolti, con la quota di barre vere, va nel registro della ricerca e su ogni scheda. Il codice è di L3; in L2 il collaudo dichiara le combinazioni degeneri sulla griglia di D1 con barre sintetiche, e ogni altro esito deve essere OK.

Solo prezzo e volume, niente funding né basis come segnale (`77`).

| tipo | blocco | meccanismo | parametri (valori del passo 1) |
|---|---|---|---|
| trigger, catalogo | E5 (short: E5_SHORT) | rottura dopo inside bar | — |
| trigger, catalogo | E36 (short: E36_SHORT) | momentum di sessione | — |
| trigger, catalogo | E47 (short: E47_SHORT) | rottura dopo compressione | — |
| trigger, catalogo | E49 (short: E49_SHORT) | spazzata e rientro | — |
| trigger, catalogo | E51 (short: E51_SHORT) | esaurimento su volume | — |
| trigger, nuovo | RSI che rientra dalla zona estrema | inversione | periodo 2, 4, 6, 9, 12 ore; soglia 15, 20, 25, 30, 35 (lo short usa 100 − soglia) |
| trigger, nuovo | rottura del canale di Donchian: chiusura sopra il massimo delle N ore precedenti, barra corrente esclusa (short: chiusura sotto il minimo delle N ore precedenti, barra corrente esclusa) | rottura | N = 4, 8, 12, 24, 48, 96 ore |
| filtro, catalogo | F2_MID_VOLATILITY | volatilità | — |
| filtro, catalogo | F3_VOLUME_ABOVE_AVG | volume | — |
| filtro, catalogo | coppia TREND_CONTEXT (F8, F9) | trend | — |
| filtro, catalogo | F25_CHOP_TREND | regime | — |
| filtro, catalogo | F20_SESSION_OVERLAP | orario | — |
| filtro, nuovo | ADX sopra soglia | forza del trend | periodo 4, 6, 9 ore; soglia 15, 20, 25, 30 |
| filtro, nuovo | ATR breve / ATR lungo sopra soglia | volatilità relativa | breve 2, 4 ore; lungo 24, 48, 96 ore; soglia 0,8, 1, 1,2, 1,5 |
| uscita, catalogo | X0 (nessuna regola), X3 (MACD sotto la signal, stato), X1 (svolta del ciclo) | — | i tre parametri qui sotto |

ADX e ATR relativo hanno meccanismi diversi ma stanno nella stessa famiglia, decisa dalla misura (P3).

**Parametri di ogni uscita:** dopo quante ore si esce (1, 2, 4, 8, come `77`); percentile dello stop adattivo (70, 80, 90, 95); target spento o al 90. La finestra delle soglie adattive è di **125 ore**, arrotondata alla barra: 500 barre su M15, 31 su H4 (124 ore), 5 su D1 (120 ore).

**Si riusa.** I dizionari del catalogo tramite `registry`; `aggiungi_indicatori`; `exit_search_bt.soglie_adattive` con `lag` ≥ 1 (`motore_veloce.controlla_lag`); `collaudo_catalogo.verifica_lookahead` e `verifica_degenerazione`.

**Nuovo** (`blocchi.py`, `cache.py`, e in `indicatori.py` solo gli indicatori che mancano).
- `Blocco`: nome, tipo, famiglia, parametri, e `maschera(cache, lato, valori) -> array booleano`.
- `blocchi_da_config(config) -> list[Blocco]`.
- `Cache(df, limite_mb)`: `indicatore(nome, **valori)`, `soglie_uscita(ore, perc_sl, perc_tp)`, con memoria limitata (i meno usati si buttano).

**Collaudo.** Ogni blocco nuovo passa `verifica_lookahead` e `verifica_degenerazione` ai valori estremi e centrali di ogni parametro. Blocco del catalogo = stessa maschera della condizione. Lo short specchio del long su una serie specchiata. Con la cache o senza, stesso risultato. Valori noti calcolati a mano per RSI, ADX, Donchian su una serie corta; per Donchian, una barra che chiude sopra il massimo delle N ore precedenti deve dare segnale anche quando il massimo più alto è il suo: se la barra corrente entrasse nel canale, il segnale non ci sarebbe. Su M1, H4 e D1: conversione, arrotondamento, doppi tolti. Minimo di 5 barre: su M15 le griglie non cambiano; su H1, H4 e D1 i valori sotto salgono a 5 e i doppi si tolgono; `verifica_lookahead` e `verifica_degenerazione` anche su tutta la griglia di D1, perché su M15 il periodo 5 non c'è: lookahead OK su tutto, degenerazione OK tranne le combinazioni dichiarate nel collaudo. Su ogni timeframe, un blocco del catalogo è ammesso solo dove scatta davvero. Per ogni parametro il passo dello spazio è quello fine, e i valori della griglia stanno tutti nello spazio.

### P4 · Passo 1, la scrematura

**Come si fa.** Sul solo pezzo di ricerca, una teoria alla volta.
- Numero da massimizzare: il **t netto in bp** (`giudizio.t_stat`), l'unità che decide sulle crypto (`02`).
- Tetto di **40 prove per teoria**, sui valori larghi della griglia (P-L2). Se fanno fino a 40 punti, griglia completa; se no, algoritmo genetico tarato in ampiezza (molta mutazione, poca eredità).
- **Condizione di qualità 1:** almeno 100 trade; EV netto > 0; il trade migliore pesa al massimo il 10% del totale dei guadagni; totale / drawdown ≥ 1.
- Teoria tenuta se almeno una sua strategia passa. Passano al passo 2 le 150 teorie con il t più alto.

Costi come nel Lab: commissione taker, spread di un passo per trade, funding sui perpetual. Leva dentro il tetto solo nel money management: qui si lavora in bp per trade.

**Si riusa.** `motore_veloce._ciclo`, la parte del motore veloce che decide i trade; `montecarlo.drawdown_da_zero`; `exchange.spread_bp`, `exchange.funding_per_trade`; `giudizio.t_stat`; `mercato_nullo.barre_utili` per la quarantena.

**Nuovo.**
- `valutatore.valuta(strategia, cache, costi) -> Misure`: bp netti, trade, t, EV, drawdown, peso massimo. Non costruisce le tabelle del motore completo: è 6-7 volte più veloce (§5).
- `valutatore.trade_completi(strategia, df, costi) -> DataFrame`: gli stessi trade con `MotoreVeloce.run`, per il passo 9.
- `ricerca.passo_1(config, teorie, pezzi, registro) -> DataFrame`: una riga per teoria.

**Collaudo.**
- **Il più importante:** su 200 strategie casuali, `valuta` deve dare gli stessi bp di `MotoreVeloce.run` più `metriche.bp_per_trade` (tolleranza 1e-9), funding e spread compresi, su perpetual e spot.
- Una strategia su dati fatti a mano con trade e bp noti.
- Ogni valutazione è una riga nel registro, anche se scartata subito: conteggio esatto.

### P5 · Passo 2, lo zoom e l'altopiano

**Come si fa.** Per ogni teoria tenuta, **3 giri da 90 prove**: ogni giro riparte attorno alle 5 strategie migliori del giro prima, con intervalli più stretti e passo più piccolo, fino al passo più fine dello spazio (P-L2): 1 barra, 1 per le soglie intere, 0,1 per la soglia di ATR relativo. Per esempio il periodo da 8-16-24 barre a 12-14-16 barre, poi a 13-14-15. Se lo spazio ristretto ha meno punti del budget del giro: forza bruta.

**La stessa strategia in due giri.** Si riconosce dall'impronta (id_strategia, P8): non si rivaluta e si conta una volta sola nel conto delle prove (P7).

**Altopiano, la misura.** Per la strategia scelta si prova ogni parametro numerico, uno alla volta, con i suoi vicini.

*I vicini:*
- **Parametri in ore:** valore ±15%, arrotondato alla barra più vicina, con spostamento minimo di 1 barra. Sotto il minimo del parametro (1 barra; 5 per il periodo di RSI e ADX e per l'ATR lungo) il vicino non esiste e resta l'altro. Esempi:

| valore | M15, in barre | vicini in barre | H1, in barre | vicini in barre |
|---|---|---|---|---|
| 1 ora | 4 | 3 e 5 | 1 | 2 |
| 2 ore | 8 | 7 e 9 | 2 | 1 e 3 |
| 4 ore | 16 | 14 e 18 | 4 | 3 e 5 |
| 8 ore | 32 | 27 e 37 | 8 | 7 e 9 |

- **Altri parametri numerici** (soglie di RSI, ADX, rapporto ATR; percentile dello stop): il valore adiacente nella griglia di P-L2, sopra e sotto. Se lo zoom ha scelto un valore fra due della griglia, i vicini sono quei due. Al bordo della griglia resta un vicino solo. Le griglie delle soglie non cambiano con il timeframe.
- **Target spento o al 90** è un interruttore, non un numero: non ha vicini.

*La strategia regge se:*
- la mediana del t dei vicini è almeno 0,7 volte il suo t;
- il vicino peggiore ha t almeno 0,4 volte il suo t;
- tutti i vicini hanno EV netto > 0.

Le soglie stanno nella config; anche i vicini sono prove, al massimo 60 per teoria (nel caso più largo 9 parametri numerici × 2 vicini × 3 candidate = 54). Se la migliore non regge, si passa alla seconda, fino a 3, poi la teoria esce.

**Si riusa.** L'ottimizzatore di L1 e il valutatore di P4.

**Nuovo** (`ricerca.py`).
- `zoom(teoria, partenza, config, ...) -> Giro`.
- `vicini(strategia, griglia, timeframe) -> list[Strategia]`: la regola qui sopra.
- `altopiano(strategia, spazio, soglie, ...) -> dict`: t del centro, mediana, peggiore, esito.

**Ripresa.** Il seme di ogni teoria nasce da seme della ricerca + id della teoria: il risultato non dipende dall'ordine né dal numero di processi. A ogni teoria finita si scrive su disco; alla ripresa si saltano le teorie già scritte.

**Collaudo.**
- **Picco stretto:** una funzione il cui t crolla già a ±15% sulle ore, o al valore adiacente sulle soglie, non passa l'altopiano.
- **Picco largo:** una funzione il cui t a ±15% e al valore adiacente resta sopra le soglie, passa.
- **I vicini:** la tabella qui sopra rifatta a mano su M15 e H1, più H4 e D1, spostamento minimo compreso; bordo della griglia; valore fra due punti della griglia; nessun vicino per il target.
- **Stessa strategia in due giri dello zoom:** una sola valutazione, una sola riga nel conto.
- Fermata a metà e ripresa = stesso risultato, bit per bit, stesso conto delle prove. 1 processo o 3 = stesso risultato. Seme fisso = stesso risultato. Budget mai superato.

### P6 · La selezione

**Come si fa.** Le sopravvissute si valutano, parametri congelati, sul pezzo di selezione. Gli indicatori si calcolano su ricerca + selezione e poi si taglia, così non partono da zero.
- **Condizione di qualità 2:** almeno 50 trade; `giudizio.verdetto` senza SCARTATA, con EV in bp e P(EV<0) sotto il 5%; il trade migliore pesa al massimo il 15%; totale / drawdown ≥ 0,5.
- **Test individuale, che decide:** t netto sul pezzo di selezione ≥ `giudizio.soglia_rumore(1)` = **1,96**.
- **Famiglie fra le sopravvissute:** dalla stessa famiglia si tiene una sola strategia, quella con il t di selezione più alto. Anche questa è una scelta fra tante, già compresa nel conto del passo 7.

**Si riusa.** `giudizio.scheda_strategia` con `unita="bp"`, `giudizio.verdetto`, `giudizio.soglia_rumore`, `famiglie.famiglie` e `famiglie.sovrapposizioni` con regole già decise (quota 70%, lift 1,3, famiglia 60%).

**Nuovo** (`selezione.py`). `seleziona(sopravvissute, pezzi, config) -> DataFrame`: una riga per strategia, con esito e motivo. `famiglie_strategie(strategie, df) -> DataFrame`: registra le strategie come entry temporanee con un prefisso e poi le toglie.

**Collaudo.** Una strategia con il segnale noto su dati fatti a mano passa o non passa secondo la regola; un t appena sotto e uno appena sopra 1,96; due strategie identiche finiscono nella stessa famiglia e ne resta una; una strategia scartata qui non può più comparire ai passi dopo; registro delle condizioni pulito alla fine.

**Vantaggio piantato, il collaudo di tutta la pipeline:** su un mercato finto con un vantaggio inserito a parametri noti, una ricerca piccola trova quel blocco con valori vicini a quelli giusti e lo porta oltre la selezione. Sta nella suite.

### P7 · Il conto delle prove, da leggere

**Come si fa.** Ogni strategia valutata è una riga nel file delle prove, anche se scartata subito: passo 1, zoom, vicini dell'altopiano, selezione, cassaforte. La stessa strategia uscita in due giri dello zoom si riconosce dall'impronta, non si rivaluta e si conta una volta sola. Il conto **k** è il totale di quelle righe per l'asset (symbol + timeframe), sommando tutte le ricerche della fabbrica e tutte le macchine. La scheda mostra k e la soglia corrispondente, `giudizio.soglia_rumore(k)`, accanto al test individuale. Con 100.000 prove la soglia è **5,02** (10.000: 4,56; 1.000.000: 5,45).

Il conto **non decide**: nessun esito dipende da k.

**Si riusa.** `giudizio.soglia_rumore`.

**Nuovo** (`registro.py`).
- `aggiungi_prove(cartella, righe) -> None`.
- `conto_prove(cartella, symbol, timeframe) -> int`.

**Collaudo.**
- Conteggio esatto su una ricerca piccola; due ricerche si sommano; una ripresa non conta due volte; la stessa strategia in due giri dello zoom conta una volta.
- Stessa ricerca con il conto alterato: stessi esiti, cambia solo il numero sulla scheda.
- **Separazione dal Lab:** una ricerca completa, cassaforte compresa, lascia identica al bit una cartella dello studio di prova.

### P8 · La cassaforte

**Come si fa.**
- Si scelgono le strategie che entrano, fra quelle rimaste dopo la selezione. L'elenco si congela e si scrive nel registro **prima** di leggere una sola barra.
- Si valutano sulla cassaforte con il motore completo. **Decide il test individuale:** t netto sulla cassaforte ≥ **1,96**. L'esito si aggiunge al registro; si tiene la scheda di tutte.
- **Una strategia entra una volta per tratto di cassaforte.** Nello stesso tratto non rientra mai: si ferma con un errore. In un tratto nuovo (finestra scorsa, P1) può entrare. Il tratto è identificato da symbol, timeframe, inizio e fine della cassaforte. L'identità di una strategia è un'impronta di symbol, timeframe, lato, blocchi e valori in barre, quindi **un parametro cambiato è una strategia nuova**.
- **Strategie nuove possono entrare**, anche da ricerche successive. Il registro tiene quante strategie sono entrate in ogni tratto: è un numero da leggere, sulla schermata 5 e sulla scheda, e non decide.
- Il registro dice data, id della ricerca, impronta della config, tratto, strategie, esito, strategie entrate in quel tratto fino a quel momento. Non si modifica a mano: ogni riga contiene l'impronta della riga prima, e se la catena è rotta tutto si ferma con un errore.
- I controlli leggono i registri di tutte le macchine.

**Limiti dichiarati.** Il file sta sul disco di Mattia: togliere le ultime righe non rompe la catena. Se PC e Colab fanno entrare la stessa strategia nello stesso momento, prima che Drive sincronizzi, i due non si vedono.

**Si riusa.** `motore_veloce.MotoreVeloce`, `exchange.aggiungi_funding`, `aggiungi_spread_passo`, `metriche.bp_per_trade`, `giudizio.scheda_strategia`, `giudizio.soglia_rumore`.

**Nuovo** (`cassaforte.py`).
- `id_strategia(strategia, symbol, timeframe) -> str`.
- `tratto(symbol, timeframe, confini) -> str`: l'identità del tratto di cassaforte.
- `gia_entrata(cartella, tratto, id_strategia) -> bool`: guarda solo quel tratto.
- `entra(id_ricerca, strategie, conferma) -> dict`: `conferma` deve essere la frase scritta a mano nel notebook.
- `strategie_entrate(cartella, tratto) -> int`: il conto di quel tratto.
- `verifica_registro(cartella) -> None`: si ferma se la catena delle impronte è rotta.

**Collaudo: «la cassaforte non si legge prima del passo 8».**
- **Il test del veleno:** stessa ricerca due volte, passi 1–7, la seconda con le barre della cassaforte alterate o riempite di valori assurdi: **risultati e registro identici, bit per bit**. Se un solo calcolo legge la cassaforte, il test fallisce.
- **Stessa strategia di nuovo nello stesso tratto:** errore.
- **Stessa strategia in un tratto nuovo:** entra; il conto del tratto nuovo parte da 1 e quello del tratto vecchio non cambia.
- **Registro modificato a mano:** errore.
- Stessa strategia con un parametro cambiato, stesso tratto: entra, e il numero delle strategie entrate sale di uno.
- `Pezzi` senza permesso: errore.
- Elenco delle strategie scritto prima della lettura: controllato con un dataset che si rompe alla prima lettura.

### P9 · Money management, stress test, verifica dei trade

**Come si fa.** Si riusano le schermate 7, 9 e 8 del Lab. La percentuale si calibra su ricerca + selezione (l'«in-sample») e la cassaforte fa da «out-of-sample», come nel Lab; leva mai oltre il tetto (perpetual 2, spot 1).

**Si riusa.** `vetrina.money_management`, `vetrina.stress_test`, `vetrina_verifica.verifica_trade`, `vetrina_verifica.lente`. Queste funzioni leggono una `Sessione` (campi usati: `trades_is`, `trades_oos`, `df`, `df_is`, `df_oos`, `symbol`, `pip`, `spread_pips`, `uscite`, `da_exchange`, `filtro`, `fs`, `tabelle`, `mm`, `controlli`, `cartella`).

**Nuovo** (`vetrina_fabbrica.py`). `sessione_da_strategia(strategia, pezzi) -> Sessione`. Riempie quei campi con i trade del motore completo, senza cambiare una riga delle funzioni del Lab.

**Rischio da verificare in L4:** ho visto i nomi dei campi, non come vengono usati. Se `fs` è troppo legato al Lab, il ripiego è chiamare le funzioni sotto (`money_management_trade`, `montecarlo.*`).

**Collaudo.** Su un sistema costruito nel Lab e rifatto a mano nella fabbrica, stessi trade e stessi numeri delle schermate 7, 9 e 8.

### P10 · La scheda

**Come si fa.** Un `.md` e un `.json` per strategia (§6): blocchi, regole in parole, valori, dati usati, prove contate, esito di ogni passo. La regola in parole è costruita dal testo di ogni blocco con i valori inseriti.

**Si riusa.** I numeri di `giudizio.scheda_strategia`; le uscite di P9.

**Nuovo** (`schede.py`). `scrivi_scheda(strategia, esiti, cartella) -> tuple[str, str]`; `leggi_scheda(percorso) -> dict`.

**Collaudo.** Dalla sola scheda `.json` si ricostruisce la strategia e si riottengono gli stessi trade, bit per bit. Questa è la prova che la scheda basta da sola.

---

## §4 · L'ottimizzatore (L1)

Separato: riceve una funzione e uno spazio, restituisce valori. Non importa niente del trading; un test lo controlla.

- `griglia_larga(spazio, punti_max, seme) -> list[punto]`: griglia completa se ci sta, altrimenti punti sparsi in modo uniforme.
- `genetico(funzione, spazio, budget, seme, opzioni, stato=None) -> Esito`: elitismo, torneo, incrocio uniforme, mutazione; `stato` serve a riprendere.
- `Esito`: punti provati, valori, migliore, valutazioni fatte, stato. Massimizza; NaN = «scartata». Un punto già valutato non si rivaluta e non si conta due volte.

**Collaudo (funzioni di prova con minimo noto).**

| prova | richiesta |
|---|---|
| Rastrigin 2 e 5 dimensioni, Sphere, Rosenbrock, Ackley | vicino al minimo noto in almeno 45 semi su 50 |
| confronto con la ricerca a caso, stesso budget | meglio in media, su ognuna |
| budget | mai superato |
| seme | stesso seme, stessi punti, bit per bit |
| ripresa | a metà e poi avanti = tutto in una volta |
| spazi con interi, categorie e NaN | nessun errore, nessun valore fuori intervallo |

I parametri predefiniti dell'algoritmo si tarano **qui**, sulle funzioni di prova, mai sul mercato.

---

## §5 · La velocità

**Come ho misurato.** Sul PC di Mattia (i5-9400F, 6 core, 16 GB), con **barre sintetiche**: stesso numero di barre del file, nessun dato vero, nessuna prova. Trigger su circa l'1% delle barre. Script nella cartella temporanea, non nel repo.

| misura | 238.933 barre (tutto BTC perp M15) | 122.500 barre (pezzo di ricerca) |
|---|---|---|
| `MotoreVeloce.run` completo | 51,2 ms (2.050 trade) | 24,6 ms (1.023 trade) |
| percorso corto: ciclo + bp + t | 8,2 ms | 3,7 ms |
| RSI / ATR / ADX | 1,4 / 4,2 / 3,7 ms | 0,7 / 0,4 / 1,7 ms |
| Donchian | 11,6 ms | 5,3 ms |
| `soglie_adattive` | 313 ms | 161 ms |

**A regime, con il percorso corto più maschere e drawdown, sul pezzo di ricerca:**

| processi | valutazioni al secondo |
|---|---|
| 1 | 380 |
| 3 | 543 |
| 5 | 532 |
| 6 | 540 |

**Oltre 3 processi non si guadagna**, probabilmente per il limite della memoria. Bastano 3, e il PC resta usabile.

**Stima per una ricerca standard (100.000 prove).** Il funding, le scritture su disco e le maschere dei filtri non sono nella misura: per prudenza calcolo con **250 valutazioni al secondo**.

| voce | tempo |
|---|---|
| 100.000 prove a 250 al secondo | circa 7 minuti |
| con `MotoreVeloce.run` completo a 1 processo, per confronto | circa 40 minuti |
| preparazione (indicatori del catalogo, stop adattivi) | **non misurata**, stima pochi minuti; si misura in L2 |
| **tempo obiettivo, passi 1–6** | **15 minuti** |

Dentro la preparazione, ogni combinazione nuova di ore, stop e target chiede una chiamata a `soglie_adattive`, poi resta in cache: 32 combinazioni al passo 1, di più con lo zoom e con i vicini in barre dell'altopiano.

Il budget si divide così (massimi, fissati per teoria, così il risultato non dipende dall'ordine):

| voce | conto | prove |
|---|---|---|
| passo 1 | 1.176 teorie × 40 | 47.040 |
| passo 2 | 150 teorie × 270 | 40.500 |
| altopiano | 150 teorie × 60 | 9.000 |
| selezione | al massimo | 150 |
| cassaforte | al massimo | 150 |
| **totale** | sotto il tetto di 100.000 | **96.840** |

Il primo giro di L3 misura il tempo vero; se manca l'obiettivo di oltre il doppio, si torna da Mattia prima di andare avanti. M5 costa circa 3 volte M15, a parità di prove.

---

## §6 · Config e scheda

**Dove stanno.** Nella cartella dei dati, che non va su GitHub, in `fabbrica/<SYMBOL>_<TIMEFRAME>/`, fuori da `studio/`:
- `registro_<macchina>.jsonl`: il registro dell'asset, solo in aggiunta;
- `<id>/`: una cartella per ricerca (id = data + inizio dell'impronta), con `config.json`, `prove_<macchina>.csv` (una riga per prova), `stato.json` (a che punto è), `schede/`.

**Config.**

```json
{
  "versione": 1,
  "symbol": "BINANCE_PERP_BTCUSDT",
  "timeframe": "M15",
  "confini": {"inizio": "2020-01-02 00:00", "ricerca_ore": 30624, "selezione_ore": 17177.75, "cassaforte_ore": 11779.5},
  "lati": ["long", "short"],
  "blocchi": {"E47": {}, "RSI_RIENTRO": {"periodo_ore": [2, 4, 6, 9, 12], "soglia": [15, 20, 25, 30, 35]}},
  "modelli": [{"trigger": 1, "filtri": [0, 2], "uscite": 1}],
  "qualita_1": {"trade_min": 100, "ev_min_bp": 0, "peso_max": 0.10, "totale_su_dd_min": 1.0},
  "qualita_2": {"trade_min": 50, "p_ev_neg_max": 5.0, "peso_max": 0.15, "totale_su_dd_min": 0.5},
  "altopiano": {"variazione_ore": 0.15, "spostamento_min_barre": 1, "mediana_min": 0.7, "peggiore_min": 0.4,
                "candidati_max": 3, "prove_max": 60},
  "test_individuale": {"alfa": 0.05},
  "budget": {"totale": 100000, "per_teoria_passo_1": 40, "teorie_passo_2": 150, "giri_zoom": 3, "prove_per_giro": 90},
  "seme": 0,
  "processi": 3
}
```

I confini sono **durate**, in ore, così non dipendono dal timeframe. Sopra c'è la prima finestra (P1). Una finestra scorsa ha le stesse tre durate e un `inizio` più avanti di almeno `cassaforte_ore`; altrimenti la config si ferma con un errore.

**Scheda `.json`**: `id_strategia`, `id_ricerca`, `impronta_config`, `impronte_dati`, `symbol`, `timeframe`, `lato`, `blocchi` (nome e valori), `uscita`, `regole` (testo), `esiti` (per ogni passo: pezzo, trade, EV in bp, t, drawdown, condizione, esito, motivo), `altopiano`, `test_individuale` (t e soglia in selezione e in cassaforte), `prove` (di questa ricerca, totale della fabbrica sull'asset, soglia corrispondente), `cassaforte` (data, tratto, esito, strategie entrate in quel tratto), `mm`, `stress`, `software` (commit del repo).

**Scheda `.md`**, la stessa cosa in parole: **Regole** (per esempio «long quando…, solo se…, stop…, esce dopo…») · **Da dove viene** (ricerca, dati) · **Il cammino** (una riga per passo, con il test individuale) · **Da leggere** (prove contate e soglia corrispondente, strategie entrate in cassaforte) · **Money management e stress test**. In fondo sempre la frase: «Questo è il risultato di un collaudo dello strumento; la decisione è tua.»

---

## §7 · Il notebook `Fabbrica_Strategie_Crypto.ipynb`

Come il Lab: nelle celle solo la chiamata a una funzione di `engine/vetrina_fabbrica.py`. Numeri qui sotto: **esempi inventati**, solo per il testo.

**Glossario in testa.**

- **Long / short:** guadagni se il prezzo sale / se scende.
- **bp (punto base):** un centesimo dell'1%. Un trade che guadagna l'1% fa 100 bp.
- **Costo:** quello che paghi all'exchange per ogni trade (commissione, spread, funding). Tutti i numeri sono già al netto.
- **Funding:** il pagamento periodico fra chi è long e chi è short sui perpetual. Può essere un costo o un incasso.
- **Drawdown:** il calo massimo dal punto più alto del conto.
- **t:** quanto il guadagno medio per trade si distingue dal caso. Più è alto, meno è probabile che sia fortuna.
- **Test individuale:** il t della strategia contro la soglia per una prova sola (1,96). È il test che decide.
- **MM (money management):** quanto rischiare a ogni trade.
- **Blocco:** un mattoncino: un trigger (quando entrare), un filtro (quando è permesso entrare), un'uscita.
- **Modello:** lo schema, per esempio «1 trigger + 1 filtro + 1 uscita». **Teoria:** un modello con i blocchi scelti, senza numeri. **Strategia:** una teoria con tutti i numeri.
- **Giro:** una passata di ricerca su una teoria. **Prova:** ogni strategia provata, anche se scartata subito. **Budget:** quante prove al massimo.
- **Condizione di qualità:** regole sì/no che una strategia deve passare.
- **Cassaforte:** l'ultimo pezzo di dati. In ogni tratto di cassaforte una strategia entra una volta sola.

**Avvio.** *Cosa fa:* prepara il notebook e trova i dati. *Come leggere:* deve dire da quale cartella legge e che cosa ha trovato, per esempio «16 symbol, ultima barra 19/10/2026». *Poi:* vai alla 1.

**1 · Configura.** *Cosa fa:* scrive le regole della ricerca, sul symbol e sul timeframe che scegli, e le blocca con un'impronta. *Come leggere:* conta teorie e prove previste, per esempio «1.176 teorie, 97.000 prove, circa 15 minuti». *Poi:* se ti va bene, passa alla 2. **Cambiare le regole dopo vuol dire una ricerca nuova, e le prove si sommano.**

**2 · La ricerca.** *Cosa fa:* prova le strategie (lancio, avanzamento, ripresa). *Come leggere:* la barra dice a che punto è, per esempio «teoria 590 di 1.176, 47.000 prove, mancano 8 minuti». *Poi:* se si interrompe, rilancia la stessa cella: riparte da dove era. Quando finisce, alla 3.

**3 · L'imbuto.** *Cosa fa:* mostra quante strategie sopravvivono a ogni passo, la figura principale. *Come leggere:* per esempio «teorie 1.176 → passo 1: 150 → passo 2: 40 → selezione: 6 → cassaforte: da aprire». Un imbuto che resta vuoto non è un errore: è una risposta. *Poi:* guarda le strategie alla 4.

**4 · Le strategie rimaste.** *Cosa fa:* una riga per strategia, con regole in parole e numeri sui due pezzi aperti. *Come leggere:* EV è il guadagno medio per trade: EV 8 bp vuol dire 0,08% a trade, già al netto dei costi. Decide il t contro 1,96, per esempio t 2,4 passa. Accanto, solo da leggere, il conto delle prove e la soglia corrispondente, per esempio 97.000 prove e 5,02. *Poi:* decidi quali strategie far entrare in cassaforte. Puoi anche non farne entrare nessuna.

**5 · La cassaforte.** *Cosa fa:* scrive nel registro le strategie scelte, poi le prova sull'ultimo pezzo di dati. *Come leggere:* per ogni strategia il risultato accanto a quello della selezione; per esempio EV 8 bp in selezione e 2 bp in cassaforte vuol dire che il guadagno medio per trade è un quarto. Decide il t contro 1,96. Da leggere: quante strategie sono entrate finora in questa cassaforte, per esempio 6. *Poi:* passa alla 6.
**ATTENZIONE: in questo tratto di cassaforte una strategia entra UNA VOLTA SOLA. Non si annulla. Un parametro cambiato è una strategia nuova. Per procedere scrivi la frase richiesta nel campo.**

**6 · MM e stress test.** *Cosa fa:* dice quanto rischiare a ogni trade e quanto può andare male. *Come leggere:* per esempio «rischio 0,5% a trade: nel 95% delle storie simulate il calo resta sotto il 20%». *Poi:* vai alla 7.

**7 · Le schede.** *Cosa fa:* scrive un file `.md` e uno `.json` per ogni strategia. *Come leggere:* il `.md` si legge, il `.json` serve a rifare la strategia. La scheda dice anche quante prove ci sono volute. *Poi:* la decisione è tua: la scheda è un collaudo, non un verdetto.

---

## §8 · Decisioni di Mattia (05/11)

- Parametri ottimizzati solo in `engine/fabbrica/`, stop e target compresi.
- Condizioni di qualità e soglie dell'altopiano come scritti, fissati prima del primo lancio.
- Lista dei blocchi di P-L2 approvata.
- Budget: 100.000 prove.
- Lati separati.
- Nomi dei file invariati; si cita sempre `81_FABBRICA`.
- Confini (06/11): finestra scorrevole di durata fissa, spostamento ≥ durata della cassaforte, un conto delle strategie entrate per ogni tratto (P1).
- Cassaforte (06/11): una strategia entra una volta per tratto di cassaforte; nello stesso tratto non rientra mai; in un tratto nuovo (finestra scorsa) può entrare (P8).
- Zoom (06/11): al passo di 1 barra, 1 per le soglie intere, 0,1 per la soglia di ATR relativo; minimo e massimo sono quelli della griglia (P-L2, P5).
- Timeframe (06/11): da M1 a D1, parametri arrotondati alla barra più vicina, minimo 1 barra, valori doppi tolti; vale anche per la finestra delle soglie (P-L2).
- Etichette (06/11): E5 è «rottura dopo inside bar», X3 è «MACD sotto la signal (stato)»; le liste non cambiano (P-L2).
- Famiglie (06/11): ADX e ATR relativo nella stessa famiglia, decisa dalla misura; le teorie sono 1.176 (P3).
- Minimo di barre (07/11): almeno 5 barre per periodo di RSI, periodo di ADX e ATR lungo; ATR breve con minimo 1. Su M15 le griglie non cambiano; dove un valore sale a 5, i doppi si tolgono (P-L2, P5).
- F20 su D1 (07/11): ferma la config, come i trigger (P-L2).
- Valori degeneri (07/11): all'avvio di ogni ricerca le combinazioni della griglia di ogni blocco con parametri passano da `verifica_degenerazione` sul solo pezzo di ricerca (solo segnali, non è una prova); le degeneri escono dalla griglia, lo spazio dello zoom segue la griglia rimasta, un blocco senza valori esce dalla config; l'elenco va nel registro e su ogni scheda (P3, P-L2).

---

## §9 · I lavori e i tempi

Un ramo e una PR per ciascuno, in quest'ordine. Il via è di Mattia, lavoro per lavoro. Sessioni di lavoro stimate, non misurate; la suite completa gira in ognuna.

| lavoro | contenuto | dipende da | sessioni | cosa vedrà Mattia |
|---|---|---|---|---|
| **L1** | ottimizzatore, funzioni di prova, suite | — | 1 | l'ultima riga della suite |
| **L2** | blocchi, cache, indicatori nuovi; controllo dei doppioni | — | 1–2 | tabella dei doppioni (solo segnali) |
| **L3** | dati, config, generatore, valutatore, passi 1–2 con l'altopiano, registro; **primo tempo vero** | L1, L2 | 2–3 | tempo misurato su dati sintetici |
| **L4** | selezione, famiglie, conto delle prove, cassaforte, test del veleno, adattatore della Sessione | L3 | 2–3 | i collaudi del veleno e del vantaggio piantato |
| **L5** | notebook, vetrina, schede, allineamento di `docs/00` e `CLAUDE.md` | L4 | 2 | il notebook su dati veri, se e quando dici tu |

**Fino a L5 tutti i collaudi girano su dati sintetici.** Nessun lancio sui dati veri senza il tuo via: il primo lancio vero conta le prove della fabbrica e non si torna indietro.

**Dopo, incarico a parte:** price action come blocchi (BOS, CHoCH, FVG, massimo e minimo del giorno prima, order block).

---

## §10 · Cosa ho letto

**Dall'elenco dell'incarico:** `CLAUDE.md`, `docs/00`, l'incarico nella versione del 05/11, firme e docstring dei moduli elencati, le funzioni delle schermate 6–9 (firma e docstring; per `verifica_trade` e `lente` solo i campi della Sessione), `docs/02` (giudizio e unità), `docs/74`.

**Fuori elenco, perché servivano e solo per questo:**
- corpo di `MotoreVeloce.run` e docstring di `soglie_adattive`, per misurare la velocità;
- corpo di `giudizio.soglia_rumore`, per i valori della soglia (k = 1: 1,96);
- `mercato_nullo.barre_utili`, per la quarantena;
- nomi nei dizionari del catalogo, per la lista di P-L2 (solo i nomi);
- `studio/confine.json` e, dei giornali, **solo** tipo di voce e date;
- primo e ultimo rigo e numero di righe dei CSV M15;
- in `engine/vetrina.py` una ricerca per nome delle scritture nel diario e nel conto, per controllare che le funzioni riusate non le facciano; la conferma vera è il collaudo di separazione in P7.

**Non letti:** `engine/studio.py` salvo il nome della cartella, il libro, `GUIDA_AVVIO_FABBRICA.md` e `REVISORE_FABBRICA.md`. I risultati nei giornali non sono stati letti.
