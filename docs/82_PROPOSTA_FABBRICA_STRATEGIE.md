# 82 · Proposta: la fabbrica di strategie

**Data:** 5 novembre 2026, aggiornata l'8 novembre. **Risponde a:** `81_FABBRICA_STRATEGIE.md`, versione del 06/11 (qui «l'incarico»).
**Stato:** L1–L5b scritti (L5b, il notebook, il 09/11); collaudati solo su dati sintetici. Revisione chiusa con Mattia il 05/11, il 06/11, il 07/11 e l'08/11 (§8). Il codice parte con il via di Mattia, lavoro per lavoro. **11/11:** proposta nuova in §11 (catalogo intero e ricerca in due turni), solo testo, rivista la sera dell'11/11, in attesa del via.

**Indice:** §0 In breve · §1 Le regole del progetto toccate · §2 I file nuovi · §3 La pipeline, punto per punto ·
§4 L'ottimizzatore · §5 La velocità · §6 Config e scheda · §7 Il notebook · §8 Decisioni di Mattia (05/11) · §9 I lavori e i tempi ·
§10 Cosa ho letto · §11 Catalogo intero e ricerca in due turni (proposta dell'11/11)

---

## §0 · In breve

La fabbrica prende uno spazio di ricerca deciso prima di guardare i dati, prova circa **100.000 strategie** su **un asset alla volta**, scarta da sola e consegna poche schede. Una ricerca dovrebbe durare **circa 15 minuti** sul PC di Mattia (stima in §5).

- **Che cosa decide:** il **test individuale**, cioè il t netto della strategia contro la soglia per una prova sola (1,96), in selezione e in cassaforte.
- **Il conto delle prove** della fabbrica e la soglia che gli corrisponde stanno sulla scheda, solo da leggere.
- **La fabbrica è separata dal Lab:** non legge e non scrive il conto del Lab né il diario dello studio. Ha solo il suo registro.
- **La cassaforte:** le strategie si congelano e si scrivono nel registro prima di leggere una barra. Ogni strategia entra quante volte si vuole, senza frase di conferma (10/11); il registro degli ingressi resta, solo come annotazione da leggere.

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
| `engine/fabbrica/dati.py` | i tre pezzi di dati e il sigillo sulla cassaforte | L3a |
| `engine/fabbrica/config.py` | lettura, controllo e impronta della config | L3a |
| `engine/fabbrica/generatore.py` | teorie da modelli × blocchi, famiglie, valori degeneri | L3a |
| `engine/fabbrica/valutatore.py` | da una strategia ai bp netti e alle misure | L3a |
| `engine/fabbrica/sintetici.py` | barre e funding inventati per i collaudi, come `funzioni_prova.py` (aggiunto in L3a); in L3b il mercato con il vantaggio piantato | L3a, L3b |
| `engine/fabbrica/ricerca.py` | passi 1 e 2, altopiano, ripresa | L3b |
| `engine/fabbrica/registro.py` | registro delle ricerche (annotazioni solo in aggiunta, senza catena dal 10/11) e conto delle prove: una prova = (ricerca, pezzo, strategia), contata una volta | L3b |
| `engine/fabbrica/selezione.py` | condizione 2, test individuale, famiglie | L4a |
| `engine/fabbrica/cassaforte.py` | strategie congelate, ingresso, registro della cassaforte | L4b |
| `engine/fabbrica/sessione.py` | l'adattatore della Sessione: nomi temporanei nel catalogo, chiusura, schermate 7 e 8 con la finestra in ore | L4b |
| `engine/fabbrica/schede.py` | scheda `.md` e `.json`, regole in parole, trade rifatti dalla sola scheda | L5a |
| `engine/vetrina_fabbrica.py` | le funzioni chiamate dalle celle | L4b (`sessione_da_strategia`), L5a (le altre) |
| `Fabbrica_Strategie_Crypto.ipynb` | il notebook | L5b |
| `test_fabbrica_*.py` | una suite per lavoro, ultima riga «RISULTATO: n/n» | L1–L5 |

**Modifiche additive a file esistenti, dichiarate:** `engine/indicatori.py` (L2, indicatori nuovi); `suite_rapida.py` (L1, solo se serve per legare le suite nuove al codice; in L2 e L3a le durate delle suite nuove); `CLAUDE.md` e `docs/00` (L5, terzo notebook); `engine/vetrina_verifica.py` (L4b, 08/11: parametro facoltativo `finestra` di `verifica_trade`, `controlla_periodo`, `registro_trade`, `_ricalcola`, predefinito la `FINESTRA` del Lab, 500: il Lab non cambia); `engine/fabbrica/registro.py` (L4b: l'ora degli eventi da `adesso()`, che i collaudi fissano; L5a: `imposta_macchina`, il nome della macchina scritto nell'Avvio). L5a, 08/11, tutte additive: `engine/fabbrica/ricerca.py` (parametro facoltativo `avanzamento` di `lancia`, che non cambia la ricerca); `engine/fabbrica/blocchi.py` (`MOTIVI_ESCLUSIONE`); `engine/fabbrica/config.py` (`blocchi_esclusi`, `controlla_tipi_rimasti`); `engine/fabbrica/cassaforte.py` (`trade_entrata`); `engine/fabbrica/sessione.py` (`in_sample`, il calcolo dell'in-sample tolto da `apri_sessione` senza cambiarlo, usato anche dalla scheda); `suite_rapida.py` (le durate delle due suite nuove). L5b, 09/11: `engine/fabbrica/blocchi.py` (`_non_scatta`, l'errore di una config scritta a mano dice quale blocco e perché); `engine/fabbrica/schede.py` (`nome_breve`); `engine/fabbrica/sessione.py` (`s.fabbrica["nomi"]`); `engine/vetrina_fabbrica.py` (i testi della cella 6); `CLAUDE.md` e `docs/00` (il terzo notebook); `suite_rapida.py` (la durata di `test_notebook_fabbrica`).
Nessun pacchetto nuovo per il codice: numpy, pandas, numba e TA-Lib ci sono già. Per eseguire il notebook sul PC e per il suo collaudo con nbclient serve `ipykernel`, installato nella `.venv` del progetto il 09/11 con il via di Mattia (7.4.0); nbclient e nbformat c'erano già.

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
- **Confini standard sui dati di oggi** (decisione di Mattia, 09/11; al posto della finestra scorrevole del 06/11): a ogni avvio la cella 1 aggiorna i CSV dall'exchange; l'inizio resta fisso (02/01/2020 00:00 UTC), la fine è l'ultima mezzanotte UTC chiusa del CSV (su D1 coincide con la chiusura dell'ultima barra). Così nella stessa giornata UTC la cella 1 rilanciata dà la stessa ricerca, anche con barre nuove, e la cella 2 la riprende; dal giorno dopo è una ricerca nuova. I tre pezzi stanno nelle proporzioni della tabella qui sopra (30624 : 17177,75 : 11779,5 ore, circa 51% / 29% / 20%), con i confini all'inizio di una barra del timeframe; le ore risultanti vanno nella config (`config.confini_standard`). Una config scritta a mano resta com'è. Ogni tratto di cassaforte ha il suo conto delle strategie entrate.

**Si riusa.** `exchange.leggi_csv` con gli stessi controlli di `vetrina.carica_storico` (che accetta solo da M5 a H4: la fabbrica va da M1 a D1; 07/11, §8), `vetrina.costi_storico`, `vetrina.carica_funding`, `exchange.leggi_funding`, `exchange.controlla_storico`, `exchange.copertura_funding`,
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

**Scelte del 07/11 (§8).**
- **Le uscite non passano dal controllo di degenerazione:** durata, stop e target non cambiano la loro maschera (X0 è mai vera per costruzione), quindi il controllo darebbe lo stesso esito per tutte le combinazioni.
- **I valori degeneri si tolgono per lato:** una combinazione degenere sul long e non sullo short esce solo dal long. Un filtro neutro ha la stessa maschera sui due lati ed esce da tutti e due.
- **Famiglie, misura o dichiarazione:** due blocchi stanno nella stessa famiglia se li unisce `famiglie.py` sul pezzo di ricerca, ai valori centrali, oppure se sono dichiarati insieme (ADX e ATR relativo). Le teorie della lista di P-L2 sono quindi al massimo 1.176; il registro dice quante sono e perché.

**Si riusa.** `famiglie.famiglie` e, per registrare i blocchi per il tempo della misura, `registry.register_entry`, `remove_entries`, `remove_filters`.

**Nuovo** (`generatore.py`).
- `genera_teorie(config, famiglie_blocchi) -> list[Teoria]`, ognuna con un id stabile.
- `spazio_teoria(teoria) -> Spazio`: i parametri e i loro valori per l'ottimizzatore.

**Collaudo.** Conteggio esatto su una lista piccola fatta a mano; nessuna teoria con due blocchi della stessa famiglia; nessuna teoria short sullo spot; stesso ordine a ogni giro; registro delle condizioni identico prima e dopo la misura.

### P-L2 · I blocchi (lista approvata, §8)

Scelti **per meccanismo diverso, senza guardare i risultati**. Tenuti fuori di proposito i trigger che `74` §2 segna come già visti in cima alla rosa (E21, E39) e quello nato da una scheda della mappa (E45). Dal C2 (14/11, §11) la config standard ha tutto il catalogo: E21, E39 ed E45 non sono più tenuti fuori.
Il meccanismo qui sotto è stato **confermato in L2 leggendo le condizioni**: E5 e X3 erano diversi da come li avevo dedotti dai nomi e sono stati rietichettati (§8), le liste non cambiano. Il controllo con `famiglie.py`, che guarda solo i segnali e non conta prove, non ha trovato doppioni.

**Timeframe da M1 a D1.** Intervalli in **ore**, convertiti in barre secondo il timeframe: niente costanti da M15.
- Un valore diventa la **barra più vicina**, a metà strada verso l'alto, **minimo 1 barra**. Ore zero o negative si fermano con un errore.
- **Minimo di 5 barre (07/11)** per periodo di RSI, periodo di ADX e ATR lungo: i valori sotto salgono a 5. L'ATR breve resta con minimo 1 barra, come durate e canale di Donchian.
- Nella griglia i **valori doppi dopo l'arrotondamento si tolgono**: su D1 le uscite a 1, 2, 4 e 8 ore diventano una sola, 1 barra.
- Le **ore effettive** (barre × durata della barra) si leggono dal blocco, per la scheda: `ore_effettive`, `griglia_ore`, `finestre_ore`.
- I blocchi del catalogo restano come sono e scattano solo su alcuni timeframe: E5 da M1 a D1; E36 da M1 a M30; E47 M5 e M15; E49 ed E51 da M5 a H1; F20 fino a H4 (su D1 la barra è sempre quella delle 00:00). Su un timeframe dove un blocco non scatterebbe mai, due casi (08/11):
  - **config standard:** il blocco esce dalla config con il suo motivo (limite logico, approssimazione esclusa, escluso solo dall'elenco) e la ricerca prosegue;
  - **config scritta a mano:** un blocco scelto esplicitamente che non scatta ferma la config con un errore che dice quale blocco e perché. I filtri con finestre in barre (F2, F3, trend, F25) restano così, e il blocco espone le loro finestre in ore.

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
- **L'obiettivo dell'algoritmo (07/11, come nel libro, cap. 3):** il genetico massimizza il t di ogni strategia calcolabile; la condizione di qualità non entra nell'obiettivo e decide solo alla fine (la teoria è tenuta se almeno una strategia passa; si sceglie la migliore fra quelle che passano). NaN solo quando il t non si può calcolare. La riga nel conto resta per tutte. Un punto degenere (P3) o già visto non consuma una delle 40 prove.

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

**Le 5 da cui riparte un giro (07/11, risposta di Mattia).** Si scelgono per t fra tutte le strategie calcolabili della teoria provate fino a quel giro, passo 1 compreso, che passino o no la condizione di qualità. La condizione di qualità decide solo alla fine: si tiene la migliore fra quelle che passano; se nessuna passa, la teoria esce.

**L'intervallo di un giro (07/11).** Per ogni parametro, l'intervallo va dal minimo al massimo delle 5 migliori, allargato del passo del giro prima da ogni lato (al primo giro: il buco più largo della griglia), dentro i confini dello spazio. Quell'intervallo si prova con il passo nuovo: al primo giro metà del buco più largo della griglia, al secondo un intermedio (la media geometrica fra quella metà e il passo fine, arrotondata al passo fine), al terzo il passo fine (1 barra, 1, 0,1). Per esempio un buco di 8 barre dà i passi 4, 2, 1; uno di 96 barre 48, 7, 1. **Collaudo:** ogni intero fra due punti della griglia larga è raggiungibile in 3 giri.
*Come è scritto in L3b (dettagli che la regola non fissava):*
- passi arrotondati a metà strada verso l'alto, mai sotto il passo fine; con un numero di giri diverso da 3, una scala geometrica dalla metà del buco al passo fine;
- il reticolo del giro parte dal minimo delle 5, così le 5 ci stanno;
- il buco più largo e i confini sono quelli della griglia rimasta dopo i valori degeneri;
- il target è un interruttore: nel giro restano i valori che hanno le 5;
- spazio del giro con al massimo `prove_per_giro` punti: si prova tutto; se no, il genetico di L1 con le opzioni predefinite, con un seme che nasce da seme della ricerca + id della teoria + giro.

**Altopiano, dettagli di L3b.** Un vicino degenere si scarta e si annota, come nello zoom: non è un vicino e non conta. Un vicino già visto non si rivaluta. Se le prove dell'altopiano finiscono (`prove_max`) prima del giudizio, la teoria esce con quel motivo.

**La stessa strategia in due giri.** Si riconosce dall'impronta (id_strategia, P8): non si rivaluta e si conta una volta sola nel conto delle prove (P7).

**Le combinazioni nuove (07/11).** Ogni combinazione nuova proposta dallo zoom o dall'altopiano passa da `verifica_degenerazione` (solo segnali, sul pezzo di ricerca) prima di essere valutata: se è degenere si scarta, si annota e non conta come prova.

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

*Come è scritto in L4a (08/11, scelte di Mattia in §8 e dettagli che la regola non fissava):*
- **Il pezzo:** ricerca e selezione attaccate, con gli indicatori; finisce all'ultima barra della selezione, nessuna barra della cassaforte. `aggiungi_indicatori` toglie le barre di riscaldamento in testa, quindi la prima barra della selezione si trova per data, e se una barra della selezione manca tutto si ferma. I segnali prima di quella barra si spengono: ogni trade nasce nella selezione.
- **Il trade ancora aperto all'ultima barra resta fuori**, come in tutto il motore (`motore_veloce`, U7) e come al passo 1 sul pezzo di ricerca: non si chiude con un prezzo inventato e non legge barre della cassaforte.
- **I costi** sono quelli del pezzo di selezione (`Pezzi.costi("selezione")`), con il funding dei due pezzi attaccato.
- **P(EV<0):** `giudizio.p_ev_negativo` (10.000 ricampionamenti, seme 0) sui bp di selezione; il verdetto è `giudizio.verdetto` con EV e P(EV<0) in bp. La scheda completa (`scheda_strategia`) resta per L5.
- **Ordine dei giudizi:** prima la condizione 2, poi il test individuale; il motivo dice la prima regola che non passa.
- **Famiglie:** sui segnali finali (trigger, filtri, quarantena) di ricerca + selezione, lato per lato. Due strategie stanno insieme se `famiglie.famiglie` le unisce (famiglia 60%, lift 1,3) **o** se `famiglie.sovrapposizioni` le dà doppioni (quota 70%, lift 1,3): le regole sono passate per esteso, anche dove sono già quelle predefinite. Resta la strategia con il t di selezione più alto, a parità l'id più piccolo. Esiti: «scelta», «stessa famiglia», «scartata». Solo le «scelte» possono andare oltre (`controlla_ammessa` si ferma con le altre).
- **Su disco:** `selezione.json` nella cartella della ricerca, scritto una volta e riletto alla ripresa; la fine della ricerca nel registro porta l'esito di ogni strategia. Accanto al test individuale, `prove_asset` e `soglia_da_leggere` (P7).

### P7 · Il conto delle prove, da leggere

**Come si fa.** Ogni strategia valutata è una riga nel file delle prove, anche se scartata subito: passo 1, zoom, vicini dell'altopiano, selezione, cassaforte. La stessa strategia uscita in due giri dello zoom si riconosce dall'impronta, non si rivaluta e si conta una volta sola; lo stesso per una strategia che rientra in cassaforte (10/11). Il conto **k** è il totale di quelle righe per l'asset (symbol + timeframe), sommando tutte le ricerche della fabbrica e tutte le macchine. La scheda mostra k e la soglia corrispondente, `giudizio.soglia_rumore(k)`, accanto al test individuale. Con 100.000 prove la soglia è **5,02** (10.000: 4,56; 1.000.000: 5,45).

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
- **Ingressi senza limiti** (10/11): ogni strategia può entrare quante volte si vuole, nello stesso tratto o in altri; ogni ingresso è un evento nel registro, con il suo esito. La stessa strategia sulla stessa cassaforte è la stessa prova: il conto non cresce. Il tratto è identificato da symbol, timeframe, inizio e fine della cassaforte. L'identità di una strategia è un'impronta di symbol, timeframe, lato, blocchi e valori in barre, quindi **un parametro cambiato è una strategia nuova**.
- **Strategie nuove possono entrare**, anche da ricerche successive. Il registro tiene quante strategie sono entrate in ogni tratto: è un numero da leggere, sulla schermata 5 e sulla scheda, e non decide.
- Il registro dice data, id della ricerca, impronta della config, tratto, strategie, esito, strategie entrate in quel tratto fino a quel momento. Dal 10/11 (scelta B) è un file di annotazioni, solo in aggiunta: niente impronta della riga prima, niente controllo; una riga cambiata o tolta si legge com'è e non ferma niente. I registri scritti prima, con l'impronta, si leggono come gli altri.
- I controlli leggono i registri di tutte le macchine.

**Limiti dichiarati.** Il file sta sul disco di Mattia e si può cambiare a mano: il registro annota, non protegge. Se PC e Colab fanno entrare la stessa strategia nello stesso momento, prima che Drive sincronizzi, i due non si vedono.

**Si riusa.** `motore_veloce.MotoreVeloce`, `exchange.aggiungi_funding`, `aggiungi_spread_passo`, `metriche.bp_per_trade`, `giudizio.scheda_strategia`, `giudizio.soglia_rumore`.

**Nuovo** (`cassaforte.py`).
- `id_strategia(strategia, symbol, timeframe) -> str`.
- `tratto(symbol, timeframe, confini) -> str`: l'identità del tratto di cassaforte.
- `gia_entrata(cartella, tratto, id_strategia) -> bool`: guarda solo quel tratto.
- `entra(id_ricerca, strategie) -> dict` (dal 10/11 senza la frase di conferma).
- `strategie_entrate(cartella, tratto) -> int`: il conto di quel tratto.

**Collaudo: «la cassaforte non si legge prima del passo 8».**
- **Il test del veleno:** stessa ricerca due volte, passi 1–7, la seconda con le barre della cassaforte alterate o riempite di valori assurdi: **risultati e registro identici, bit per bit**. Se un solo calcolo legge la cassaforte, il test fallisce.
- **(10/11) Stessa strategia di nuovo nello stesso tratto:** entra, un ingresso e un esito in più, nessuna prova nuova.
- **Stessa strategia in un tratto che non si sovrappone:** entra; il conto del tratto nuovo parte da 1 e quello del tratto vecchio non cambia.
- **(10/11) In una cassaforte sovrapposta** entrano sia una strategia nuova sia una già entrata.
- **Registro modificato a mano** (10/11): si legge com'è, non ferma niente.
- Stessa strategia con un parametro cambiato, stesso tratto: entra, e il numero delle strategie entrate sale di uno.
- `Pezzi` senza permesso: errore.
- Elenco delle strategie scritto prima della lettura: controllato con un dataset che si rompe alla prima lettura.

*Come è scritto in L4b (08/11):*
- **L'ordine di `entra(cartella_dati, id_ricerca, strategie)`.** Prima, senza leggere nessun file di barre, nemmeno ricerca e selezione: config e `selezione.json` della ricerca, ogni strategia «scelta» in selezione (dal 10/11 niente catena dei registri, niente frase di conferma né controlli sugli ingressi già fatti). Poi l'elenco nel registro (evento `ingresso_cassaforte`, con le strategie entrate nel tratto fino a quel momento). Solo dopo il permesso e la lettura dei dati; le impronte di ricerca e selezione devono essere quelle dell'avvio. L'esito va nel registro come `esito_cassaforte`.
- **Il tratto** è `<SYMBOL>_<TIMEFRAME>_<inizio>_<fine>` della cassaforte. `congela` fa la parte del registro da sola (la usano i collaudi delle regole).
- **Il pezzo di cassaforte:** ricerca, selezione e cassaforte attaccate per gli indicatori; i segnali prima della prima barra della cassaforte sono spenti; il trade ancora aperto all'ultima barra resta fuori, come nel motore. Motore completo (`trade_completi`). Costi del pezzo di cassaforte, con il prezzo mediano della cassaforte (P1: «i costi si calcolano sul pezzo tagliato»; il Lab usa invece l'in-sample per l'out-of-sample).
- **Decide il test individuale:** t netto in cassaforte ≥ 1,96. Ogni strategia entrata è una prova (pezzo «cassaforte»); accanto, il conto dell'asset, la soglia da leggere e le strategie entrate nel tratto.
- **Un'interruzione fra l'ingresso e la lettura:** le strategie restano entrate; `esito_cassaforte(cartella_dati, id_ricerca)` rifà la valutazione delle strategie già entrate, senza un ingresso nuovo, e scrive l'esito una volta sola.

### P9 · Money management, stress test, verifica dei trade

**Come si fa.** Si riusano le schermate 7, 9 e 8 del Lab. La percentuale si calibra su ricerca + selezione (l'«in-sample») e la cassaforte fa da «out-of-sample», come nel Lab; leva mai oltre il tetto (perpetual 2, spot 1).

**Si riusa.** `vetrina.money_management`, `vetrina.stress_test`, `vetrina_verifica.verifica_trade`, `vetrina_verifica.lente`. Queste funzioni leggono una `Sessione` (campi usati: `trades_is`, `trades_oos`, `df`, `df_is`, `df_oos`, `symbol`, `pip`, `spread_pips`, `uscite`, `da_exchange`, `filtro`, `fs`, `tabelle`, `mm`, `controlli`, `cartella`).

**Nuovo** (`vetrina_fabbrica.py`). `sessione_da_strategia(strategia, pezzi) -> Sessione`. Riempie quei campi con i trade del motore completo, senza cambiare una riga delle funzioni del Lab.

**Rischio da verificare in L4:** ho visto i nomi dei campi, non come vengono usati. Se `fs` è troppo legato al Lab, il ripiego è chiamare le funzioni sotto (`money_management_trade`, `montecarlo.*`).

**Collaudo.** Su un sistema costruito nel Lab e rifatto a mano nella fabbrica, stessi trade e stessi numeri delle schermate 7, 9 e 8.

*Come è scritto in L4b (08/11, scelta di Mattia in §8):*
- **Dove:** `engine/fabbrica/sessione.py` (`apri_sessione`, `sessione` per il blocco `with`, `chiudi`, `money_management`, `verifica_trade`); `engine/vetrina_fabbrica.py` nasce con la sola `sessione_da_strategia`.
- **In-sample** = ricerca + selezione, con i loro indicatori e i loro costi; i trade finiscono all'ultima barra della selezione. **Out-of-sample** = la cassaforte, con i trade di `entra` riportati alle barre del suo pezzo. Una Sessione si apre solo per una strategia entrata in cassaforte.
- **I nomi temporanei:** trigger e filtri della strategia si registrano nel catalogo come `FAB_SES_<n>_<blocco>`; ogni nome restituisce la maschera già calcolata dalla fabbrica, letta per data, così non riparte da zero all'inizio della cassaforte. `chiudi(s)` li toglie, anche dopo un errore a metà dell'apertura o dentro il blocco `with`.
- **Schermata 7:** `money_management_trade` (la funzione sotto la schermata del Lab) con la finestra delle soglie di 125 ore in barre e il lag della fabbrica; `simulazioni` facoltativo (predefinito quello del Lab, 10.000).
- **Schermata 8:** `vetrina_verifica.verifica_trade(s, finestra)` con la stessa finestra; `lente(s, mostra_trigger=False)`, perché i disegni delle figure del Lab non conoscono i nomi temporanei. **Schermata 9:** `vetrina.stress_test(s)` così com'è.
- **Il collaudo fatto al posto del «sistema rifatto a mano».** Il Lab calcola in-sample e out-of-sample ognuno da sé, con gli indicatori che ripartono da zero, la fabbrica no: i trade vicini all'inizio dell'out-of-sample non sarebbero gli stessi. Si controlla quindi l'adattatore: su M15 la schermata 7 del Lab e l'adattatore passano a `money_management_trade` gli stessi argomenti; la verifica dell'adattatore è uguale a quella del Lab con le sue 500 barre; su H1 la finestra è di 125 barre e ogni regola resta OK.

### P10 · La scheda

**Come si fa.** Un `.md` e un `.json` per strategia (§6): blocchi, regole in parole, valori, dati usati, prove contate, esito di ogni passo. La regola in parole è costruita dal testo di ogni blocco con i valori inseriti.

**Si riusa.** I numeri di `giudizio.scheda_strategia`; le uscite di P9.

**Nuovo** (`schede.py`). `scrivi_scheda(strategia, esiti, cartella) -> tuple[str, str]`; `leggi_scheda(percorso) -> dict`.

**Collaudo.** Dalla sola scheda `.json` si ricostruisce la strategia e si riottengono gli stessi trade, bit per bit. Questa è la prova che la scheda basta da sola.

*Come è scritto in L5a (08/11, versione approvata da Mattia):*
- **Per quali strategie:** una scheda per ogni strategia entrata in cassaforte (`schede(r)`, cella 7), in `<ricerca>/schede/<id_strategia>.md` e `.json`. Rieseguita, la cella le riscrive: vengono dai calcoli, il registro non cambia.
- **Le regole in parole** (`regole_in_parole`): ogni blocco ha un testo per il long e uno per lo short (`TESTI_TRIGGER`, `TESTI_FILTRI`, `TESTI_USCITE`), scritto leggendo il codice del blocco; i valori entrano in ore e in barre del timeframe, per esempio «il Close supera il massimo degli High delle 12 ore (48 barre) precedenti». L'uscita dice durata, regola, stop e target («la distanza che contiene il 90% delle escursioni contrarie dei trade di 4 ore delle ultime 125 ore»).
- **La verifica dei trade** (schermata 8 del Lab) gira sempre nella cella 6; l'esito delle sue regole (le sei sui trade e quella sui segnali non tradati) va nella scheda, `.md` e `.json`, con money management e stress test. Il riassunto della 6 sta in `<ricerca>/mm/<id_strategia>.json`; senza la 6 la scheda dice «non calcolati: esegui la 6».
- **I blocchi tolti** su quel timeframe, con il motivo, sono nella scheda e in `riepilogo.json` della ricerca (§8, 08/11).
- **In fondo al `.md`** la frase «La scheda descrive cosa è successo sui dati; la decisione è tua.» (Mattia, 08/11).
- **Il collaudo P10** (`test_fabbrica_schede.py`): dalla sola scheda `.json` (`trade_da_scheda`) gli stessi trade al bit, in-sample (quelli della Sessione) e in cassaforte (quelli di `entra`), su BYBIT_SPOT_ETHUSDT M15 e su BINANCE_PERP_BTCUSDT H1 con il funding. Un valore cambiato nella scheda non torna con l'id; impronte dei dati diverse fermano; una strategia mai entrata non riapre la cassaforte (`cassaforte.trade_entrata`).

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

Il primo giro di L3 misura il tempo vero; se manca l'obiettivo di oltre il doppio, si torna da Mattia prima di andare avanti.
**Misurato in L3b (07/11),** su barre sintetiche lunghe come lo storico di BTC perp M15 (122.496 barre nel pezzo di ricerca), config standard, 3 processi: passi 1–2 con l'altopiano in **222 secondi (3,7 minuti)**, con 82.343 prove (passo 1 43.200, zoom 38.179, altopiano 964). Preparazione 8 s, passo 1 61 s, passo 2 e altopiano 151 s. M5 costa circa 3 volte M15, a parità di prove.

---

## §6 · Config e scheda

**Dove stanno.** Nella cartella dei dati, che non va su GitHub, in `fabbrica/<SYMBOL>_<TIMEFRAME>/`, fuori da `studio/`:
- `registro_<macchina>.jsonl`: il registro dell'asset, annotazioni solo in aggiunta (dal 10/11 senza catena di impronte);
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

**`processi` non entra nell'impronta (08/11):** non cambia i risultati (collaudato: 1 processo = 3 processi), quindi la stessa ricerca si riprende anche con un numero di processi diverso; il `config.json` resta quello del primo salvataggio.

I confini sono **durate**, in ore, così non dipendono dal timeframe. Sopra c'è la prima finestra (P1). Dal 09/11 la config standard non ha più queste ore fisse: la cella 1 le calcola con `confini_standard`, dall'inizio fisso all'ultima mezzanotte UTC chiusa, nelle proporzioni della prima finestra (P1).

**Scheda `.json`**: `id_strategia`, `id_ricerca`, `impronta_config`, `impronte_dati`, `symbol`, `timeframe`, `lato`, `blocchi` (nome e valori), `uscita`, `regole` (testo), `esiti` (per ogni passo: pezzo, trade, EV in bp, t, drawdown, condizione, esito, motivo), `altopiano`, `test_individuale` (t e soglia in selezione e in cassaforte), `prove` (di questa ricerca, totale della fabbrica sull'asset, soglia corrispondente), `cassaforte` (data, tratto, esito, strategie entrate in quel tratto), `mm`, `stress`, `software` (commit del repo). In L5a (08/11) anche: `verifica` (le regole della verifica dei trade), `parametri_mm`, `blocchi_esclusi` (con il motivo), `strategia` e `config_strategia` (quello che serve a rifare i trade dalla sola scheda), `versione_scheda`.

**Scheda `.md`**, la stessa cosa in parole: **Regole** (per esempio «long quando…, solo se…, stop…, esce dopo…») · **Da dove viene** (ricerca, dati) · **Il cammino** (una riga per passo, con il test individuale) · **Da leggere** (prove contate e soglia corrispondente, strategie entrate in cassaforte) · **Money management e stress test**. In fondo sempre la frase: «La scheda descrive cosa è successo sui dati; la decisione è tua.» (Mattia, 08/11).

---

## §7 · Il notebook `Fabbrica_Strategie_Crypto.ipynb`

Come il Lab: nelle celle solo la chiamata a una funzione di `engine/vetrina_fabbrica.py` (scritte in L5a; il notebook è L5b). Ogni cella di codice ha sopra una cella di testo di al massimo 6 righe, nel formato di `docs/81` §5: **Cosa fa** · **Come leggere**, con un esempio numerico · **Poi**; nessuna sigla senza spiegarla. Numeri qui sotto: **esempi inventati**, solo per il testo. Versione approvata da Mattia l'08/11; i testi li rivede in L5b.

**Glossario in testa.**

- **Long / short:** guadagni se il prezzo sale / se scende.
- **Perpetual:** un contratto sulla moneta senza scadenza; si può andare long o short. **Spot:** compri la moneta vera, solo long.
- **Spread:** la differenza fra il prezzo a cui compri e quello a cui vendi nello stesso momento.
- **bp (punto base):** un centesimo dell'1%. Un trade che guadagna l'1% fa 100 bp.
- **Costo:** quello che paghi all'exchange per ogni trade (commissione, spread, funding). Tutti i numeri sono già al netto.
- **Funding:** il pagamento periodico fra chi è long e chi è short sui perpetual. Può essere un costo o un incasso.
- **EV:** il guadagno medio per trade, al netto dei costi.
- **Drawdown:** il calo massimo dal punto più alto del conto.
- **t:** quanto il guadagno medio per trade si distingue dal caso. Più è alto, meno è probabile che sia fortuna.
- **Test individuale:** il t della strategia contro la soglia per una prova sola (1,96). È il test che decide.
- **MM (money management):** quanto rischiare a ogni trade.
- **Blocco:** un mattoncino: un trigger (quando entrare), un filtro (quando è permesso entrare), un'uscita.
- **Modello:** lo schema, per esempio «1 trigger + 1 filtro + 1 uscita». **Teoria:** un modello con i blocchi scelti, senza numeri. **Strategia:** una teoria con tutti i numeri.
- **Giro:** una passata di ricerca su una teoria. **Prova:** ogni strategia provata, anche se scartata subito. **Budget:** quante prove al massimo.
- **Condizione di qualità:** regole sì/no che una strategia deve passare.
- **Altopiano:** la strategia regge anche con i parametri un po' spostati.
- **Selezione:** il secondo pezzo di dati, dove decide il test individuale.
- **Famiglia:** strategie che entrano quasi negli stessi momenti; se ne tiene una sola.
- **Imbuto:** quante strategie restano a ogni passo.
- **Cassaforte:** l'ultimo pezzo di dati, mai usato per costruire le strategie.

**Avvio** (`avvio(cartella_dati, macchina)`). Campo: il nome di questa macchina (`pc`, un secondo PC `pc2`; su Colab è sempre `colab`), così due PC con Drive non scrivono lo stesso file. Non scarica dati: dal 09/11 si aggiornano alla cella 1. Se la cartella dei dati non c'è, la crea.
*Cosa fa:* prepara il notebook e trova i dati. *Come leggere:* la cartella, i symbol con l'ultima barra (per esempio «16 file, ultima barra 19/10/2026»); per ogni ricerca già fatta, a che punto è, le strategie entrate e la fine dell'ultima cassaforte usata (09/11: le «barre dopo» non ci sono più, la finestra scorrevole è superata). *Poi:* vai alla 1.

**1 · Configura** (`configura(cartella_dati, exchange, mercato, moneta, timeframe, processi)`). Campi: exchange, mercato, moneta, timeframe da M1 a D1, processi (3 sul PC, 2 su Colab). Il resto è la config standard di §6; il seme non è un campo.
*Cosa fa:* aggiorna i dati dall'exchange (09/11: `engine/aggiorna_dati.aggiorna_per_lab`, candele e, sui perpetual, funding; nessun interruttore; senza rete o senza ccxt un avviso e i CSV fino all'ultimo salvataggio), poi scrive le regole della ricerca e le salva: per questa ricerca non si possono più cambiare. *Come leggere:* «dati aggiornati fino a <data>» oppure «exchange non raggiungibile: uso i dati fino a <data>»; le date dei tre pezzi, dall'inizio fisso all'ultima mezzanotte UTC chiusa (P1; la cassaforte «chiusa»), teorie e prove previste, una stima grezza del tempo (per esempio «1.176 teorie, 96.840 prove, circa 15 minuti»); i blocchi tolti su quel timeframe, ognuno con il motivo (limite logico, approssimazione esclusa per scelta, escluso solo dall'elenco). *Poi:* passa alla 2. **Cambiare le regole dopo vuol dire una ricerca nuova, e le prove si sommano.**
Si ferma solo se mancano i dati (il CSV non c'è e il download non riesce, o i dati non coprono i tre pezzi) o se non resta un trigger o un'uscita. Rieseguita nello stesso giorno UTC dà la stessa ricerca, anche con barre nuove; dal giorno dopo i confini cambiano, quindi è una ricerca nuova (09/11).

**2 · La ricerca** (`ricerca(conf)`).
*Cosa fa:* prova le strategie; se si interrompe, riparte da dove era. *Come leggere:* la riga dice a che punto è, per esempio «passo 1: teoria 590 di 1.176 · 47.000 prove · mancano al massimo circa 8 minuti». Alla fine prove, durata, valori degeneri tolti e gli stessi blocchi tolti della 1 (anche in `riepilogo.json`). *Poi:* se si interrompe, rilancia la stessa cella. Quando finisce, alla 3.

**3 · L'imbuto** (`imbuto(r)`).
*Cosa fa:* mostra quante strategie restano a ogni passo, la figura principale. *Come leggere:* per esempio «teorie 1.176 → passo 1: 900 → zoom: 150 → altopiano: 40 → selezione: 6 → scelte: 4 → cassaforte: da aprire». Un imbuto che resta vuoto non è un errore: è una risposta. I motivi di scarto in una sezione chiusa. *Poi:* guarda le strategie alla 4.

**4 · Le strategie rimaste** (`strategie_rimaste(r)`).
*Cosa fa:* una riga per strategia, numerata, prima le «scelte», con le regole in parole e i numeri di ricerca e selezione. *Come leggere:* EV 8 bp vuol dire 0,08% a trade, già al netto dei costi. Decide il t di selezione contro 1,96: t 2,4 passa. Accanto, da leggere, le prove sull'asset e la soglia corrispondente (per esempio 97.000 e 5,02): è il t che servirebbe se ogni prova fatta contasse come un tentativo; è solo da leggere, non decide. *Poi:* decidi quali far entrare in cassaforte; anche nessuna.

**5 · La cassaforte** (`cassaforte(r, strategie)`). Campo: i numeri della 4 («1, 3») oppure «tutte le scelte» (dal 10/11 niente frase di conferma).
*Cosa fa:* scrive nel registro le strategie scelte, poi le prova sull'ultimo pezzo di dati. *Come leggere:* selezione e cassaforte affiancate; per esempio EV 8 bp in selezione e 2 bp in cassaforte vuol dire un quarto del guadagno medio. Decide il t contro 1,96. Da leggere: quante strategie sono entrate in questo tratto (per esempio 6). *Poi:* passa alla 6. Puoi rilanciare la cella quante volte vuoi: ogni lancio con dei numeri è un ingresso nuovo, annotato nel registro.
Vuoto = nessun ingresso: la cella mostra l'esito delle strategie già entrate, se ce ne sono. Rieseguita con dei numeri: quelle strategie entrano di nuovo, anche se erano già entrate (10/11).

**6 · MM, stress test e verifica dei trade** (`mm_e_stress(r, numero, capitale, drawdown_max_pct, anni, modello, leva, trade_da_vedere)`). Campi: il numero della 4 (solo fra le entrate) e quelli delle schermate 7 e 9 del Lab; «trade da vedere», vuoto per default.
*Nota per L5b (Mattia, 08/11):* i riquadri del Lab non devono rimandare a schermate che nella fabbrica non esistono (per esempio «poi vai alla schermata 9»), e la lente mostra il nome del blocco (per esempio «Donchian 12 ore»), non `FAB_SES_…`; senza cambiare il Lab.
*Come è scritto in L5b (09/11):* durante la cella 6 gli aiutanti di presentazione del Lab (`vetrina._riquadro`, `_nota`, `_avviso`, `_spiegazione`, `_titolo`, `_mostra`, `_dettaglio`) sono sostituiti per il tempo della cella da versioni che riscrivono il testo prima di passarlo all'originale (`vetrina_fabbrica._testi_fabbrica`, regole in `RIMANDI`); all'uscita, anche dopo un errore, tornano gli stessi oggetti di prima (collaudo n. 22 di `test_vetrina_fabbrica.py`). La lente e le tabelle mostrano il nome breve del blocco (`schede.nome_breve`, per esempio «Donchian 12 ore»).
*Cosa fa:* dice quanto rischiare a ogni trade e quanto può andare male, e controlla ogni trade contro le regole. *Come leggere:* per esempio «rischio 0,5% a trade: nel 95% delle storie simulate il calo resta sotto il 20%»; ogni regola della verifica deve dire OK. Con un numero in «trade da vedere» quel trade sul grafico. *Poi:* vai alla 7.

**7 · Le schede** (`schede(r)`).
*Cosa fa:* scrive un file `.md` e uno `.json` per ogni strategia entrata in cassaforte. *Come leggere:* il `.md` si legge (regole, cammino, prove, verifica, MM, blocchi tolti), il `.json` serve a rifare la strategia. *Poi:* la scheda descrive cosa è successo sui dati; la decisione è tua.

*Il notebook in L5b (09/11):* `Fabbrica_Strategie_Crypto.ipynb`, costruito da queste celle; nel glossario in più asset, zoom, in-sample / out-of-sample. L'Avvio è quello del Lab (Colab con Drive, oppure il PC con `cartella_dati_avvio`); installa TA-Lib, backtesting e numba solo se mancano o hanno un'altra versione. Collaudo: `test_notebook_fabbrica.py` controlla il file (testi di al massimo 6 righe con un esempio numerico, una chiamata per cella, glossario, avviso della 5) ed esegue il notebook intero con nbclient, due volte, su dati sintetici con una config ridotta, impostate su una copia; la seconda volta non aggiunge prove né ingressi. `python test_notebook_fabbrica.py --copia [cartella]` prepara i dati sintetici e la copia di collaudo da aprire in VS Code.

---

## §8 · Decisioni di Mattia (05/11)

**Regola di progetto (Mattia, 10/11): la pipeline deve essere IL PIÙ SEMPLICE POSSIBILE, mantenendo il livello di qualità dei risultati più alto possibile. Niente blocchi, conferme o meccanismi non richiesti: si propongono a Mattia e si decidono insieme.**

- Parametri ottimizzati solo in `engine/fabbrica/`, stop e target compresi.
- Condizioni di qualità e soglie dell'altopiano come scritti, fissati prima del primo lancio.
- Lista dei blocchi di P-L2 approvata. Superata con C2 (14/11): vedi Catalogo intero e due turni; i 14 trigger e filtri di P-L2 restano quelli che in una famiglia misurata hanno la precedenza.
- Budget: 100.000 prove. Superato con C2 (14/11): il tetto è il massimo arrotondato in su ai 10.000 (D6).
- Lati separati.
- Nomi dei file invariati; si cita sempre `81_FABBRICA`.
- Confini (06/11): finestra scorrevole di durata fissa, spostamento ≥ durata della cassaforte, un conto delle strategie entrate per ogni tratto (P1). Superata il 09/11: vedi Dati e confini a ogni avvio.
- Cassaforte (06/11): una strategia entra una volta per tratto di cassaforte; nello stesso tratto non rientra mai; in un tratto nuovo (finestra scorsa) può entrare (P8). Superata il 09/11: vedi Cassaforte sovrapposta.
- Zoom (06/11): al passo di 1 barra, 1 per le soglie intere, 0,1 per la soglia di ATR relativo; minimo e massimo sono quelli della griglia (P-L2, P5).
- Timeframe (06/11): da M1 a D1, parametri arrotondati alla barra più vicina, minimo 1 barra, valori doppi tolti; vale anche per la finestra delle soglie (P-L2).
- Etichette (06/11): E5 è «rottura dopo inside bar», X3 è «MACD sotto la signal (stato)»; le liste non cambiano (P-L2).
- Famiglie (06/11): ADX e ATR relativo nella stessa famiglia, decisa dalla misura; le teorie sono 1.176 (P3). Il numero di teorie è superato con C2 (14/11): dipende dai blocchi tenuti sul pezzo di ricerca (§11.4).
- Minimo di barre (07/11): almeno 5 barre per periodo di RSI, periodo di ADX e ATR lungo; ATR breve con minimo 1. Su M15 le griglie non cambiano; dove un valore sale a 5, i doppi si tolgono (P-L2, P5).
- F20 su D1 (07/11): ferma la config, come i trigger (P-L2). Superata l'08/11: vedi Timeframe nella cella 1.
- Valori degeneri (07/11): all'avvio di ogni ricerca le combinazioni della griglia di ogni blocco con parametri passano da `verifica_degenerazione` sul solo pezzo di ricerca (solo segnali, non è una prova); le degeneri escono dalla griglia, lo spazio dello zoom segue la griglia rimasta, un blocco senza valori esce dalla config; l'elenco va nel registro e su ogni scheda (P3, P-L2).
- Combinazioni nuove (07/11): ogni combinazione nuova proposta dallo zoom o dall'altopiano passa da `verifica_degenerazione` (solo segnali, sul pezzo di ricerca) prima di essere valutata: se è degenere si scarta, si annota e non conta come prova (P5).
- Divisione di L3 (07/11): L3a dati, config, generatore con le combinazioni degeneri, valutatore; poi L3b passi 1–2, altopiano, registro, tempo vero (§9).
- Scelte di L3 (07/11): le uscite non passano dal controllo di degenerazione; i valori degeneri si tolgono per lato; famiglie per misura o per dichiarazione, il registro dice quante teorie e perché (P3); il genetico massimizza il t di ogni strategia calcolabile e la condizione di qualità decide solo alla fine; un punto degenere o già visto non consuma una prova (P4); intervallo e passo di ogni giro dello zoom come in P5.
- Zoom (07/11, via a L3b): le 5 da cui riparte un giro si scelgono per t fra tutte le strategie calcolabili; la condizione di qualità decide solo alla fine, si tiene la migliore fra quelle che passano e, se nessuna passa, la teoria esce (P5).
- Dati (07/11): letti con `exchange.leggi_csv` e gli stessi controlli di `vetrina.carica_storico`, che accetta solo da M5 a H4; la cassaforte si rilegge dal disco solo con il permesso (P1).
- Impronta della config (08/11): `processi` esce dall'impronta, perché non cambia i risultati; stessa ricerca con 1 o 3 processi (§6).
- Divisione di L4 (08/11): L4a selezione e conto delle prove (P6, P7); L4b cassaforte e Sessione (P8, P9) (§9).
- Verifica dei trade nella fabbrica (08/11, P9): strada 1, le funzioni del Lab con trigger e filtri della strategia registrati con nomi temporanei; la finestra di 500 barre della voce «stop non ancora calcolabile» diventa un parametro della funzione del Lab, con 500 come predefinito; la fabbrica passa le sue 125 ore in barre.
- L5 (08/11): diviso in L5a (schede, funzioni delle celle, collaudi) e L5b (il notebook, il collaudo del notebook intero, `CLAUDE.md` e `docs/00`). Schede solo per le strategie entrate in cassaforte; la 5 rieseguita mostra l'esito, i numeri nuovi entrano come ingresso nuovo (dal 10/11 entrano anche quelli già entrati); il nome della macchina nell'Avvio, come nel Lab; l'Avvio non scarica dati e mostra le barre dopo l'ultima cassaforte usata (superato il 09/11: i dati si aggiornano alla cella 1, le «barre dopo» non ci sono più); la verifica dei trade gira sempre nella 6 (`docs/81` §3 passo 9), la lente è facoltativa; frase finale della scheda «La scheda descrive cosa è successo sui dati; la decisione è tua.»; testi delle celle nel formato di `docs/81` §5, rivisti in L5b (§7).
- Timeframe nella cella 1 (08/11, dopo la diagnosi di E36, E47, E49, E51): da M1 a D1. La cella mostra i blocchi tolti con il motivo e prosegue; si ferma solo se mancano i dati o se non resta un trigger o un'uscita. Gli elenchi del catalogo non cambiano: i limiti logici restano (E36 da H1 in su, E47 da H1 in su, E49 su H4 e D1, E51 su D1, F20 su D1); E47 su M30 ed E51 su H4 restano esclusi, perché sarebbero approssimazioni, cioè varianti della regola; E47, E49 ed E51 su M1 sono esclusi solo dall'elenco (lavoro futuro, §9). L'elenco va anche nel riepilogo della ricerca e nelle schede (`blocchi.MOTIVI_ESCLUSIONE`).
- Dati e confini a ogni avvio (09/11): la cella 1, dopo symbol, timeframe e mercato, aggiorna i CSV con `aggiorna_dati.aggiorna_per_lab` (candele e, sui perpetual, funding), senza interruttore; se l'exchange non risponde o ccxt manca, un avviso e i CSV fino all'ultimo salvataggio; si ferma solo se il CSV non c'è e il download non riesce; se la cartella dei dati non c'è, la crea. Il Lab non cambia. Confini standard: inizio fisso 02/01/2020 00:00 UTC, fine = l'ultima mezzanotte UTC chiusa del CSV (correzione del 09/11 sulla PR #109, prima era la chiusura dell'ultima barra: nella stessa giornata la cella 1 dà la stessa ricerca e la 2 la riprende; su D1 non cambia nulla), tre pezzi nelle proporzioni 30624 : 17177,75 : 11779,5 ore, confini all'inizio di una barra; le ore risultanti nella config; una config scritta a mano resta com'è. La cella mostra «dati aggiornati fino a <data>» oppure «exchange non raggiungibile: uso i dati fino a <data>» e le date dei tre pezzi (P1, §7).
- Cassaforte sovrapposta (09/11): tolta la regola «cassaforte nuova solo su barre mai usate». Una strategia nuova entra sempre; una strategia già entrata (stesso `id_strategia`) non entra in una cassaforte che si sovrappone a una in cui è già entrata, stesso symbol e timeframe: si ferma con il motivo. Il conto delle prove non cambia (P8). Superata il 10/11: vedi Cassaforte senza limiti di ingresso.
- Cassaforte senza limiti di ingresso (10/11): tolto il blocco «una strategia già entrata non rientra» (stesso tratto e tratti sovrapposti): ogni strategia della 4 può entrare in cassaforte quante volte si vuole. Tolti dalla cella 5 la frase di conferma e l'avviso «una volta sola»: il campo resta solo per i numeri. Resta tutto il sigillo (la cassaforte non si legge prima della cella 5, test del veleno invariato) e il registro degli ingressi, solo come annotazione da leggere. Il conto delle prove non cambia (P8, §7).
- Registro senza catena di impronte (10/11, scelta B): `registro_<macchina>.jsonl` resta un file di annotazioni, solo in aggiunta, che non ferma più nulla se una riga è cambiata o tolta; i registri già scritti con l'impronta si leggono come gli altri. Non cambiano il file e il conto delle prove, il sigillo della cassaforte e il test del veleno (P7, P8, §6).
- Selezione (08/11, scelte di L4a): famiglie misurate sui segnali finali di ricerca + selezione, lato per lato; P(EV<0) con il bootstrap di `p_ev_negativo` (10.000 ricampionamenti, seme 0) sui bp di selezione; il pezzo passato alla selezione finisce all'ultima barra della selezione, senza barre della cassaforte (P6).
- Catalogo intero e due turni (11/11, dopo la diagnosi delle famiglie; rivista la sera dell'11/11 sulla PR #112): blocchi = tutto il catalogo dei trigger, i filtri di `filter_conditions.py` e di `vwap_regime_filter_conditions.py` (VWAP_GAP_WIDENING neutro e la coppia VWAP_SESSION_CLOSE in un blocco solo, come TREND_CONTEXT), più RSI, Donchian, ADX e ATR relativo; E21, E39 ed E45 inclusi; F36 (Fear & Greed) escluso per ora; uscite le 3 di oggi (X0, X3, X1). I trigger del catalogo sono 43 long e 42 short (E19 solo long). Un blocco per famiglia, in automatico all'avvio di ogni ricerca sul pezzo di ricerca, solo sui segnali (`famiglie.py`, stessa soglia, trigger e filtri lato per lato): si tiene il blocco fra i 14 di oggi se c'è, altrimenti quello che scatta più spesso (D2: per i filtri, vero sul maggior numero di barre); l'elenco dei tenuti e dei tolti, con il motivo, va nel riepilogo della cella 1 e sulla scheda. D1 = B: per scegliere i tenuti contano solo le famiglie misurate; ADX e ATR relativo restano tutti e due, e la loro famiglia dichiarata vale solo nel generatore (mai nella stessa teoria, anche al turno 2). Se due dei 14 finiscono nella stessa famiglia misurata, resta quello che scatta più spesso; a parità, il nome più piccolo (Mattia, 12/11, scelta A). Ricerca in due turni (la parola «giro» resta solo dell'ottimizzatore e dello zoom), tutta sul pezzo di ricerca: turno 1 tutte le teorie T+U e T+F+U; turno 2 alle 150 teorie T+F con il t più alto (D3: come la scelta del passo 2) si aggiunge un secondo filtro, tutti quelli compatibili; poi le teorie dei due turni insieme e le 150 migliori allo zoom come oggi; ogni prova dei due turni entra nel conto (fase `passo_1_turno_2`, file `turno_2.jsonl`, chiave `teorie_turno_2`). D4: la tabella da approvare elenca solo i blocchi che restano fuori su qualche timeframe da M1 a D1, con il motivo. D5 = B: solo la config versione 2, una strada sola; le ricerche vecchie restano su disco e nel conto, e le celle 4–7 su una di esse si fermano come «ricerca non trovata» con la riga che dice di rilanciare la cella 2. D6: il tetto del budget è il massimo nuovo arrotondato in su ai 10.000. La stima del tempo della cella 1 usa la velocità vera delle ricerche del 9 e del 10/11 (146–167 prove al secondo con 3 processi), in C2. D4 (12/11 sera, §11.12): le coppie (blocco, timeframe) escluse sono nella tabella di §11.12, con il motivo; in più E41 su D1 (limite logico), E31 su H1, E22 e OVERNIGHT_RETURN su H4 (approssimazioni escluse per scelta); F20_SESSION_ASIA, F20_SESSION_EUROPE, F20_SESSION_US e F22 restano su H4 (scelta B); nessuna esclusione per le finestre in barre lunghe (ci pensa il controllo dei degeneri), VWAP tenuti su H4, E40 ed E41 tenuti su M1. Un blocco del catalogo che sul pezzo di ricerca risulta «STATO» esce da quel lato con il motivo «vero su due barre di fila: non è un evento su questi dati» e la ricerca prosegue, come un degenere (scelta A); il catalogo non cambia; per i blocchi con parametri della fabbrica «STATO» resta un errore che ferma la ricerca. Il ricontrollo degli eventi su H4 e D1 non aggiunge righe. Proposta in §11. Codice: C1 (PR #113) e C2 (ramo `fabbrica-C2-turni`, §11.9); con C2 questa voce prende il posto di «Lista dei blocchi di P-L2 approvata», di «Budget: 100.000 prove» e del numero di teorie (1.176) di «Famiglie (06/11)».

---

## §9 · I lavori e i tempi

Un ramo e una PR per ciascuno, in quest'ordine. Il via è di Mattia, lavoro per lavoro. Sessioni di lavoro stimate, non misurate; la suite completa gira in ognuna.

| lavoro | contenuto | dipende da | sessioni | cosa vedrà Mattia |
|---|---|---|---|---|
| **L1** | ottimizzatore, funzioni di prova, suite | — | 1 | l'ultima riga della suite |
| **L2** | blocchi, cache, indicatori nuovi; controllo dei doppioni | — | 1–2 | tabella dei doppioni (solo segnali) |
| **L3** | dati, config, generatore, valutatore, passi 1–2 con l'altopiano, registro; **primo tempo vero** | L1, L2 | 2–3 | tempo misurato su dati sintetici |
| **L4a** | selezione, famiglie, conto delle prove, vantaggio piantato fino alla selezione | L3 | 1 | il vantaggio piantato oltre la selezione |
| **L4b** | cassaforte, registro (a catena fino al 10/11), test del veleno, adattatore della Sessione | L4a | 1–2 | il collaudo del veleno |
| **L5a** | schede, funzioni delle celle (`vetrina_fabbrica.py`), blocchi tolti per timeframe, collaudi | L4 | 1 | le due suite e una scheda su dati sintetici |
| **L5b** | il notebook, il suo collaudo intero, allineamento di `docs/00` e `CLAUDE.md` (fatto il 09/11, solo dati sintetici) | L5a | 1 | il notebook su dati veri, se e quando dici tu |

**Fino a L5 tutti i collaudi girano su dati sintetici.** Nessun lancio sui dati veri senza il tuo via: il primo lancio vero conta le prove della fabbrica e non si torna indietro.

**Dopo, incarico a parte:** price action come blocchi (BOS, CHoCH, FVG, massimo e minimo del giorno prima, order block).
**Possibile lavoro futuro, separato (08/11):** aprire M1 per E47, E49 ed E51 (oggi esclusi solo dall'elenco dei timeframe del catalogo: la regola in minuti sarebbe la stessa).

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

---

## §11 · Catalogo intero e ricerca in due turni (proposta dell'11/11)

**Stato:** proposta approvata; C1 unito (PR #113), C2 scritto (§11.9). Rivista con Mattia la sera dell'11/11 (PR #112); decisioni in §8
(«Catalogo intero e due turni»). Il codice parte con il via, lavoro per lavoro (§11.9).

**Parole.** Le due ricerche del passo 1 si chiamano **turno 1** e **turno 2**, ovunque: testo, celle, config, file, scheda.
«Giro» resta solo dell'ottimizzatore e dello zoom (§2).

**Indice:** §11.1 In breve · §11.2 I blocchi · §11.3 Un blocco per famiglia · §11.4 I due turni · §11.5 Budget e tempo ·
§11.6 Cosa cambia, file per file · §11.7 I collaudi · §11.8 Come si vede nel notebook · §11.9 I lavori · §11.10 Le
decisioni sulle domande · §11.11 Visto a parte · §11.12 D4: i blocchi esclusi per timeframe

I numeri su BINANCE_PERP_BTCUSDT M15 vengono dalla misura dell'11/11 sera: pezzo di ricerca della config standard (dal
02/01/2020 al 12/07/2023, 123.254 barre), **solo segnali**, nessuna prova, nessun conto. Sono un esempio di cosa fa la
regola, non un esito: all'avvio di ogni ricerca la misura si rifà sul suo pezzo di ricerca.

### §11.1 · In breve

- **Blocchi:** tutto il catalogo dei trigger; i filtri dei due file del catalogo, `filter_conditions.py` e
  `vwap_regime_filter_conditions.py`, come li carica il Lab; più RSI, Donchian, ADX e ATR relativo. E21, E39 ed E45 inclusi;
  F36 escluso. Uscite: X0, X3, X1, come oggi.
- **Un blocco per famiglia,** all'avvio di ogni ricerca, sul pezzo di ricerca: prima i valori degeneri (come oggi), poi le
  famiglie **misurate** con `famiglie.py` (soglia 60%), trigger e filtri lato per lato. In ogni famiglia resta un blocco:
  quello fra i 14 di oggi se c'è, altrimenti quello che scatta più spesso. ADX e ATR relativo restano tutti e due: la loro
  famiglia dichiarata vale solo nel generatore, mai nella stessa teoria.
- **Due turni al passo 1:** turno 1 tutte le teorie T+U e T+F+U; turno 2 le 150 teorie T+F con il t più alto, ognuna con un
  secondo filtro (tutti quelli compatibili). Poi le teorie dei due turni insieme: le 150 migliori vanno allo zoom, come oggi.
  Ogni prova dei due turni entra nel conto.
- **Su BTC perp M15:** 36 trigger e 21 filtri tenuti sul long, 36 e 22 sullo short → **4.860 teorie al turno 1**, al
  massimo **3.150 al turno 2**; budget massimo **370.200 prove**, tetto **380.000**; tempo stimato **33–41 minuti**, fino a
  circa **61** nel caso pesante (§11.5).

### §11.2 · I blocchi

| tipo | oggi | con la proposta |
|---|---|---|
| trigger | 7: E5, E36, E47, E49, E51, RSI, Donchian | **45**: i 43 del catalogo più RSI e Donchian. Sono 45 blocchi sul long e 44 sullo short, perché E19 c'è solo long |
| filtri | 7: F2_MID, F3, TREND_CONTEXT, F25_CHOP_TREND, F20_OVERLAP, ADX, ATR relativo | **30**: 20 neutri, 8 coppie long/short, ADX e ATR relativo |
| uscite | X0, X3, X1 | le stesse |

**I trigger del catalogo** (registro di main; nella fabbrica il blocco ha il nome corto, per esempio «E12»). Sono **43
long e 42 short**, cioè le 85 entry del catalogo di `docs/00`; lo short ha gli stessi numeri tranne E19.
- E1 RSI_CROSS_OVERSOLD (short: RSI_CROSS_OVERBOUGHT) · E2 ZLEMA_CROSS · E3 INTRABAR_WEAKNESS_FADE (short: STRENGTH_FADE) ·
  E4 EMA_CROSS · E5 QUICK_PULLBACK · E6 BACK_IN_STYLE · E7 BIG_TAIL_BARS · E8 CLOSING_PATTERN_ONLY · E9
  CLOSING_PATTERN_ONLY_II
- E10 HAMMER (short: HANGING_MAN) · E11 INVERTED_HAMMER (short: SHOOTING_STAR) · E12 ENGULFING · E13 HARAMI · E16
  MORNING_STAR (short: EVENING_STAR) · E19 THREE_WHITE_SOLDIERS (solo long) · E21 BELT_HOLD
- E22 ASIAN_RANGE_BREAKOUT · E23 PREV_DAY_HIGH_BREAKOUT (short: LOW_BREAKDOWN) · E24 CYCLE_TURN · E25 ATC_PVO_SETUP · E26
  SUPERTREND_IIX_SETUP · E27 VSA_BULLISH (short: BEARISH) · E28 VFI_CROSS · E29 SQUEEZE_RELEASE · E30 WAVETREND_CROSS
- E31 TRIPLE_SCREEN · E32 ALGOX_CAREFUL · E33 ALGOX_NOVOL_CAREFUL · E34 VSA_TREND_GO · E35 VSA_STOP_REVERSE · E36
  INTRADAY_MOMENTUM · E37 INTRADAY_MOMENTUM_COMBO · E38 HOUR_MOMENTUM · E39 HOUR_REVERSAL · E40 JUMP_MOMENTUM · E41
  DAILY_QUINTILE
- E45 RENDIMENTO_4H_ENTRA_Q1 (short: Q5) · E46 CANALE_24H_IMPULSO · E47 COMPRESSIONE_ROTTURA · E48 MASSIMI_UGUALI_ROTTURA
  (short: MINIMI_UGUALI) · E49 SWEEP_RECLAIM_MINIMO (short: MASSIMO) · E51 MOVIMENTO_VOLUME_CALO · E52 AREA_RUMORE

**I filtri.**
- **20 neutri:** F1_ADX_ABOVE, F2_MID_VOLATILITY, F2_HIGH_VOLATILITY, F3_VOLUME_ABOVE_AVG, F14_LOW_DRIFT_REGIME,
  F15_SHORT_TERM_CONSISTENCY, F20_SESSION_ASIA, F20_SESSION_EUROPE, F20_SESSION_US, F20_SESSION_OVERLAP, F22_FAR_FROM_ROLLOVER,
  F23_CYCLE_STRENGTH, F25_CHOP_TREND, F25_CHOP_RANGE, F26_VARIANCE_RATIO_TREND, F29_RVOL_LOW, F32_KER_RANGE,
  F35_JDH_REGIME_TREND, F39_INSIDE_DAY, VWAP_GAP_WIDENING.
- **8 coppie con un verso, un blocco ciascuna** come TREND_CONTEXT oggi: il membro long sul lato long, quello short sullo
  short. Il nome del blocco è l'etichetta della coppia nel registro: MACD_SIGNAL (F4), TREND_CONTEXT (F8/F9),
  TREND_CONVICTION (F10/F11), OVERNIGHT_RETURN (F21), TWO_BARS (F24), VFI_SIGN (F28), ALGOX_STATE (F40), VWAP_SESSION_CLOSE
  (VWAP_PREVIOUS_SESSION_CLOSED_ABOVE / BELOW). SENTIMENT (F36) resta fuori.
- **Il caricamento:** la fabbrica registra anche `vwap_regime_filter_conditions.py` (`registra_filtri_vwap`), come
  `vetrina._registra_condizioni` del Lab; oggi registra solo `filter_conditions.py`.

**Regole comuni.**
- **I blocchi del catalogo restano senza parametri**, come oggi: la maschera è la condizione del catalogo, letta dal
  registro. I file del catalogo non cambiano, quindi Lab e Grid Search restano identici.
- **Un trigger con un lato solo** (E19, solo long) sta solo sul lato long.
- **Famiglia dichiarata:** solo ADX e ATR relativo ne condividono una, e vale solo nel generatore (§11.3). Ogni altro
  blocco ha un'etichetta sua; altrimenti due filtri con la stessa parola (per esempio «volatilità» per F2_MID e F2_HIGH)
  non potrebbero mai stare nella stessa teoria.
- **Timeframe:** la fabbrica va da M1 a D1, e ogni blocco del catalogo è ammesso solo dove scatta davvero, con il motivo
  quando resta fuori (`MOTIVI_ESCLUSIONE`, decisione dell'08/11). La diagnosi è il primo passo di C1 (§11.10, D4). Su M15
  scattano tutti: nessun degenere nella misura dell'11/11.
- **Regole in parole:** ogni blocco nuovo ha il suo testo, long e short (`TESTI_TRIGGER`, `TESTI_FILTRI` in `schede.py`),
  scritto leggendo il codice: 38 trigger e 23 filtri. Senza testo la scheda non si scrive (il collaudo
  `blocchi_senza_testo` lo controlla già).

### §11.3 · Un blocco per famiglia

**Quando:** all'avvio di ogni ricerca (`prepara`), sul solo pezzo di ricerca, prima di generare le teorie. Usa solo i
segnali: non è una prova e non entra nel conto.

**In che ordine:**
1. **Valori degeneri e STATO:**
   - i valori degeneri come oggi (P3): per lato, per ogni combinazione della griglia dei blocchi con parametri; un blocco del
     catalogo degenere su un lato esce da quel lato;
   - un blocco del catalogo che sul pezzo di ricerca risulta «STATO» (vero su due barre di fila) esce da quel lato con il
     motivo «vero su due barre di fila: non è un evento su questi dati», come un degenere, e la ricerca prosegue; il catalogo
     non cambia (Mattia, 12/11, scelta A). Per i blocchi con parametri della fabbrica resta com'è oggi: «STATO» è un errore
     del blocco e la ricerca si ferma.
2. **Famiglie misurate:** per lato, i trigger fra loro e i filtri fra loro, ai valori centrali, `famiglie.py` con soglia 60%
   e lift 1,3. **La dichiarazione non unisce le famiglie** (D1 = B): ADX sta con F1, ATR relativo con F2_HIGH, ognuna con il
   suo tenuto.
3. **In ogni famiglia di ogni lato resta un blocco:**
   - se la famiglia contiene uno dei 14 blocchi di oggi, resta quello;
   - se ne contiene due o più, resta quello che scatta più spesso, a parità il nome più piccolo (decisione del 12/11,
     scelta A);
   - altrimenti resta quello che scatta più spesso: per i trigger il numero di segnali, per i filtri le barre in cui sono veri
     (D2);
   - a parità, il nome più piccolo, così l'esito non cambia da un lancio all'altro.

«Scatta più spesso» si legge dal controllo dei degeneri, che conta già le barre vere di ogni blocco: non serve un calcolo
nuovo. Un blocco con parametri conta ai valori centrali, come nella misura delle famiglie.

**Lato per lato:** lo stesso blocco può restare su un lato e uscire sull'altro. Per esempio TWO_BARS esce sul long (sta con
VWAP_GAP_WIDENING) e resta sullo short (è solo); E3 sul long sta con E1, sullo short con E27.

**Il generatore** usa solo i blocchi tenuti. La famiglia dichiarata vale lì, come oggi: ADX e ATR relativo **mai nella stessa
teoria**, nemmeno al turno 2.

**Cosa resta scritto:** una tabella dei tenuti e dei tolti, una riga per blocco e lato: famiglia, blocco, tenuto o tolto,
motivo, quanto scatta (segnali o quota di barre), blocco più simile e quanto gli somiglia. Va nell'evento di avvio del
registro, in `riepilogo.json`, nella cella 1 e sulla scheda.

**Su BTC perp M15, lato long** (misura dell'11/11 sera, solo segnali): le famiglie con più di un blocco.

| famiglia | tenuto | tolti | motivo |
|---|---|---|---|
| Donchian (1.347 segnali), E21 (9.621), E46 (1.338), E23 (553) | Donchian | E21, E46, E23 | Donchian è uno dei 14 di oggi |
| E12 (11.241), E8 (5.305) | E12 | E8 | scatta più spesso |
| E3 (5.798), E1 (1.498) | E3 | E1 | scatta più spesso |
| E2 (3.748), E25 (778) | E2 | E25 | scatta più spesso |
| RSI (174), E30 (1.520) | RSI | E30 | uno dei 14 |
| E33 (1.047), E32 (727) | E33 | E32 | scatta più spesso |
| E36 (665), E37 (336) | E36 | E37 | uno dei 14 |
| TREND_CONTEXT (52% delle barre), ALGOX_STATE (54%), VFI_SIGN (50%), TREND_CONVICTION (36%) | TREND_CONTEXT | gli altri 3 | uno dei 14 |
| F20_OVERLAP (12%), F20 Europa (27%), F20 USA (27%) | F20_OVERLAP | gli altri 2 | uno dei 14 |
| ADX (32%), F1 (66%) | ADX | F1 | uno dei 14 |
| VWAP_GAP_WIDENING (51%), TWO_BARS (24%) | VWAP_GAP_WIDENING | TWO_BARS | scatta più spesso |
| ATR relativo (19%), F2_HIGH (25%) | ATR relativo | F2_HIGH | uno dei 14 |
| F3 (35%), F35 (32%) | F3 | F35 | uno dei 14 |

Gli altri 29 trigger e 15 filtri del lato long sono soli nella loro famiglia e restano tutti: **36 trigger e 21 filtri**.
Sullo short le famiglie sono le stesse, con tre differenze: E3 sta con E27, E1 ed E25 sono soli, TWO_BARS è solo:
**36 trigger e 22 filtri**. La tabella completa, con i due lati, è in `dati/prove/famiglie_catalogo_20261111_v2/`.

### §11.4 · I due turni

**Turno 1.** Per ogni lato, tutte le teorie T+U e T+F+U con i blocchi tenuti: trigger × (1 + filtri) × 3 uscite. Su BTC perp
M15: long 36 × 22 × 3 = 2.376, short 36 × 23 × 3 = 2.484, **4.860** in tutto (216 T+U e 4.644 T+F+U). Il passo 1 è quello di
oggi (P4): al massimo 40 prove per teoria, griglia completa o genetico; la condizione di qualità 1 decide solo alla fine; il
t della teoria è quello della sua migliore strategia che passa.

**Turno 2.**
- Fra le teorie T+F del turno 1 tenute (almeno una strategia passa la condizione 1), le **150 con il t più alto**: il t
  della migliore strategia che passa, i due lati insieme, a parità l'id più piccolo. È la stessa regola con cui oggi si
  scelgono le 150 del passo 2 (D3). Se le T+F tenute sono meno di 150, vanno tutte.
- A ognuna si aggiunge **un secondo filtro, tutti quelli compatibili:** i filtri tenuti dello stesso lato, tranne il suo; con
  ADX mai ATR relativo, e viceversa. Stesso trigger, stessa uscita. Su BTC perp M15 fanno da 19 a 21 filtri per teoria,
  quindi al massimo 150 × 21 = **3.150** teorie.
- Una teoria che nasce da due teorie del turno 1 (T+F1 e T+F2 entrambe fra le 150 danno T+F1+F2) si prova una volta sola. I
  filtri stanno nell'ordine della config, così l'id della teoria è uno.
- Il passo 1 del turno 2 è identico a quello del turno 1.

**Dopo i due turni.** Tutte le teorie tenute dei due turni insieme: le 150 con il t più alto vanno allo zoom e all'altopiano,
come oggi (P5). Selezione, cassaforte, MM e schede non cambiano.

**Il conto.** Ogni prova dei due turni è una riga nel file delle prove: fase `passo_1` per il turno 1, `passo_1_turno_2` per
il turno 2. La scelta delle 150 del turno 2 guarda i t del pezzo di ricerca: fa parte della ricerca, e ogni teoria del turno
1 è già nel conto.

**Ripresa.** Le teorie del turno 2 nascono solo dai risultati del turno 1, che sono su disco: alla ripresa si ricalcolano
uguali. Il turno 2 si scrive in un file suo (`turno_2.jsonl`), una teoria alla volta come il turno 1. Fermata a metà e
ripresa danno lo stesso risultato, bit per bit, e 1 processo dà lo stesso risultato di 3.

### §11.5 · Budget e tempo

**Budget massimo** (i massimi per teoria, come in §5, così il risultato non dipende dall'ordine):

| voce | conto | prove al massimo |
|---|---|---|
| turno 1 | 4.860 teorie × 40 | 194.400 |
| turno 2 | 150 × 21 filtri × 40 | 126.000 |
| zoom | 150 × 270 | 40.500 |
| altopiano | 150 × 60 | 9.000 |
| selezione e cassaforte | 150 + 150 | 300 |
| **totale** | | **370.200** |

**Tetto (D6):** il massimo arrotondato in su ai 10.000, quindi **380.000**. Il massimo si calcola prima di partire: turno 1
× 40, più `teorie_turno_2` × (filtri tenuti del lato più largo − 1) × 40, più zoom, altopiano, selezione e cassaforte come
oggi. Se supera il tetto, la cella 1 si ferma, come oggi.

**Prove attese**, sotto il massimo:
- **Turno 1:** circa **161.000**, in media 33,1 per teoria. Una teoria con soli blocchi del catalogo ha 32 punti (4 durate
  × 4 stop × 2 target) e li prova tutti; con RSI, Donchian, ADX o ATR relativo ne prova 40.
- **Turno 2:** da circa **101.000 a 126.000**, secondo quante delle 150 hanno blocchi con parametri (3.150 teorie da 32 a 40
  prove).
- **Zoom, altopiano e selezione:** circa **39.000** (oggi circa 260 per teoria).
- **Totale:** da circa **301.000 a 326.000**.

**Velocità.**
- **Quella vera** delle due ricerche del 9 e del 10/11 sul PC (3 processi): **146–167 prove al secondo** (circa 78.000 prove
  in 8–9 minuti, preparazione compresa).
- **Trigger che scattano più spesso,** misurati su barre sintetiche (123.254 barre M15, nessun dato vero, nessuna prova; solo
  tempi, 1 processo). I 7 trigger di oggi costano 1,1–1,5 ms per strategia (circa 1,3 in media). I più frequenti del catalogo
  (E12, E24, E3, E13, E8, E21, da 4.000 a 8.000 segnali) costano 1,4–2,0 ms (circa 1,7). Il costo cresce poco con i segnali:
  il grosso è il passaggio sulle barre.
- **Il mix su BTC perp M15:** dei 36 trigger tenuti per lato, 6 hanno più di 4.000 segnali, gli altri sono come quelli di
  oggi. In media circa 1,1 volte il costo di oggi.

| caso | prove al secondo | prove | tempo |
|---|---|---|---|
| tipico (1,1 volte oggi) | 133–152 | 301.000–326.000 | **33–41 minuti** |
| budget pieno | 133 | 370.200 | circa **46 minuti** |
| pesante (tutti i trigger come E12, 1,45 volte oggi) | 101–115 | 301.000–370.200 | **44–61 minuti** |

Più la preparazione (degeneri e famiglie su 75 blocchi sul long e 74 sullo short), stimata in 1–2 minuti.

**Il conto da leggere** cresce con la ricerca: circa 315.000 prove danno una soglia da leggere di 5,24 (oggi 5,02 con
97.000); con le 155.661 prove già fatte su BTC perp M15 l'asset arriverebbe a circa 470.000, soglia 5,31. Il conto non decide
(P7).

### §11.6 · Cosa cambia, file per file

**Non si toccano:** il motore, i file del catalogo (`entry_long.py`, `entry_short.py`, `filter_conditions.py`,
`vwap_regime_filter_conditions.py`, uscite), `famiglie.py`, `collaudo_catalogo.py`, il Lab e la Grid Search. Quindi niente
prove d'identità: bastano le suite (`CLAUDE.md`).

| file | cosa cambia | additivo? |
|---|---|---|
| `engine/fabbrica/blocchi.py` | `TRIGGER_CATALOGO` e `FILTRI_CATALOGO` con tutto il catalogo (F36 escluso, i due VWAP dentro), con i timeframe di D4 e i loro motivi in `MOTIVI_ESCLUSIONE`; un trigger può avere un lato solo (E19); un'etichetta di famiglia diversa per ogni blocco nuovo; `_registra_catalogo` registra anche `registra_filtri_vwap` | sì, righe nuove; i 10 blocchi del catalogo di oggi restano come sono |
| `engine/fabbrica/generatore.py` | nuove: `un_blocco_per_famiglia(blocchi, misura, controllo, lati) -> (tenuti, tabella)`, `teorie_turno_1(...)`, `teorie_turno_2(scelte, ...)`; `misura_famiglie` dà le famiglie misurate per scegliere i tenuti e, a parte, la dichiarata per il generatore; `genera_teorie` lascia il posto ai due turni | no: il generatore cambia |
| `engine/fabbrica/config.py` | solo la versione 2 (D5): in `budget` la chiave nuova `teorie_turno_2` (150) e il tetto calcolato (D6); `BLOCCHI_STANDARD` con tutto il catalogo; `budget_massimo` con il turno 2 | no: le ricerche nuove hanno un'impronta nuova |
| `engine/fabbrica/ricerca.py` | una strada sola: `prepara` con un blocco per famiglia; `lancia` con il turno 2 dopo il turno 1, il file `turno_2.jsonl`, la fase `passo_1_turno_2`, le 150 dello zoom scelte dai due turni; tenuti e tolti nell'evento di avvio e nel riepilogo | no, `lancia` cambia |
| `engine/fabbrica/schede.py` | i testi dei blocchi nuovi; sulla scheda il turno da cui viene la teoria e la tabella dei tenuti e dei tolti | sì |
| `engine/vetrina_fabbrica.py` | cella 1: tenuti e tolti, teorie dei due turni, prove massime; la stima del tempo con la velocità vera delle ricerche del 9 e del 10/11 (146–167 prove al secondo con 3 processi) al posto di quella di L3b; cella 2: avanzamento per turno; cella 3: imbuto con i due turni; celle 4–7: una ricerca della versione 1 si ferma come «ricerca non trovata» (D5) | modifica delle celle 1–7 |
| `Fabbrica_Strategie_Crypto.ipynb` | glossario con «Turno»; i testi sopra le celle 1, 2 e 3, con gli esempi nuovi | testi |
| `docs/81_FABBRICA_STRATEGIE.md` | §2 glossario con «Turno»; §3 punto 4 (la scrematura in due turni); §7 L2 senza «lista corta» | testo |
| `test_fabbrica_blocchi.py`, `test_fabbrica_generatore.py`, `test_fabbrica_ricerca.py`, `test_fabbrica_schede.py`, `test_vetrina_fabbrica.py`, `test_notebook_fabbrica.py` | i collaudi di §11.7 | sì |
| `docs/00`, `docs/82` | a lavoro finito: lo stato, il «come è scritto», e in P-L2 E21, E39 ed E45 non più tenuti fuori | testo |

**Si riusa:** `misura_famiglie` e quindi `famiglie.famiglie`; `ControlloDegenerazione.esiti` per sapere quanto scatta ogni
blocco; il registro delle condizioni per le maschere del catalogo; il passo 1 di oggi (`_Lavoro.passo_1`) per i due turni,
senza cambiarlo; `_in_ordine_di_t` per scegliere le 150; zoom, altopiano, selezione, cassaforte, sessione e MM così come sono.

**Le ricerche vecchie (D5 = B).** Le ricerche della versione 1 (quelle del 9 e del 10/11) restano su disco e nel conto delle
prove. Se le celle 4–7 ne aprono una, si fermano con «ricerca non trovata» e una riga: «è una ricerca della versione 1:
rilancia la cella 2 per una ricerca nuova».

### §11.7 · I collaudi

- **Blocchi** (`test_fabbrica_blocchi.py`):
  - ogni trigger e filtro del catalogo, tranne F36, è un blocco, VWAP compresi;
  - la maschera di un blocco del catalogo è quella della condizione, sui due lati;
  - E19 non ha teorie short;
  - su ogni timeframe un blocco è ammesso solo dove scatta, e ogni blocco tolto ha il suo motivo;
  - solo ADX e ATR relativo hanno la stessa famiglia dichiarata;
  - `blocchi_senza_testo()` è vuoto.
- **Un blocco per famiglia** (`test_fabbrica_generatore.py`), con maschere fatte a mano dall'esito noto:
  - una famiglia con uno dei 14 tiene quello;
  - una famiglia senza i 14 tiene quello che scatta più spesso;
  - due dei 14 nella stessa famiglia misurata tengono quello che scatta più spesso;
  - ADX e ATR relativo molto simili ma in famiglie misurate diverse: restano tutti e due;
  - a parità di frequenza, il nome più piccolo;
  - lo stesso blocco tenuto su un lato e tolto sull'altro;
  - la tabella dei tenuti e dei tolti con il motivo giusto;
  - il registro delle condizioni identico prima e dopo.
- **STATO** (`test_fabbrica_generatore.py`): un trigger del catalogo vero su due barre di fila esce da quel lato con il
  motivo «vero su due barre di fila: non è un evento su questi dati» e la ricerca prosegue; un blocco con parametri della
  fabbrica in «STATO» ferma ancora la ricerca.
- **I due turni** (`test_fabbrica_generatore.py`):
  - turno 1 con il conto esatto, trigger × (1 + filtri) × uscite;
  - turno 2 da un elenco dato di teorie T+F: il conto esatto, mai ADX con ATR relativo, stesso lato, trigger e uscita, i
    doppi tolti, lo stesso ordine a ogni lancio;
  - sullo spot solo long.
- **La ricerca** (`test_fabbrica_ricerca.py`, dati sintetici):
  - una ricerca piccola in due turni: le prove del turno 2 nel conto con la fase `passo_1_turno_2`, le 150 dello zoom scelte
    dai due turni;
  - fermata a metà del turno 2 e ripresa = stesso risultato, bit per bit;
  - 1 processo = 3 processi; budget mai superato; il budget massimo con la formula nuova e il tetto arrotondato;
  - il vantaggio piantato e il test del veleno restano verdi.
- **Schede e celle** (`test_fabbrica_schede.py`, `test_vetrina_fabbrica.py`, `test_notebook_fabbrica.py`):
  - tenuti e tolti e il turno sulla scheda `.md` e `.json`, e in `riepilogo.json`;
  - la cella 1 li mostra, con la stima del tempo dalla velocità vera;
  - una ricerca della versione 1 aperta dalle celle 4–7 si ferma con «ricerca non trovata»;
  - il notebook intero gira due volte su dati sintetici.
- **Prima della PR:** la suite completa, `python suite_rapida.py --tutte`.

### §11.8 · Come si vede nel notebook

Numeri qui sotto: per le celle 1 e 2 gli esempi di BTC perp M15 di §11.3 e §11.5; quelli dell'imbuto sono inventati, solo
per il testo.

- **Glossario:** una riga nuova, «**Turno:** una delle due ricerche del passo 1. Il turno 1 prova le teorie con al massimo un
  filtro; il turno 2 aggiunge un secondo filtro alle 150 migliori».
- **1 · Configura:** dopo le date dei tre pezzi, una riga per lato, per esempio «long: 45 trigger → 36 tenuti, 30 filtri → 21
  tenuti (un blocco per famiglia)». Poi la tabella dei tolti, una riga per blocco: «E23 · tolto · stessa famiglia di Donchian
  (simile all'85%), che è uno dei 14 di oggi» oppure «E8 · tolto · stessa famiglia di E12, che scatta più spesso (11.241
  segnali contro 5.305)». La tabella completa, con i tenuti, in una sezione chiusa. Poi: «turno 1: 4.860 teorie; turno 2: al
  massimo 3.150; al massimo 370.200 prove, circa 33–41 minuti».
- **2 · La ricerca:** la riga di avanzamento dice il turno, per esempio «turno 1: teoria 2.000 di 4.860 · 66.000 prove»,
  poi «turno 2: teoria 300 di 3.150», poi «zoom: teoria 50 di 150».
- **3 · L'imbuto:** per esempio «turno 1: 4.860 teorie → 600 tenute · turno 2: 3.150 → 400 tenute · zoom: 150 → altopiano:
  90 → selezione → scelte».
- **4–7:** come oggi. Su una ricerca della versione 1: «ricerca non trovata: è una ricerca della versione 1, rilancia la cella
  2 per una ricerca nuova».
- **Scheda:** «Da dove viene» dice il turno (1 o 2); una sezione «Blocchi tenuti e tolti» con la stessa tabella della cella 1.

Il testo sopra le celle 1, 2 e 3 cambia solo negli esempi; formato e lunghezza restano quelli di `docs/81` §5.

### §11.9 · I lavori

Un ramo e una PR ciascuno, in quest'ordine; il via è di Mattia, lavoro per lavoro.

| lavoro | contenuto | sessioni | cosa vedrà Mattia |
|---|---|---|---|
| **C1** | prima la diagnosi dei timeframe (D4), una tabella da approvare; poi i blocchi del catalogo (VWAP compresi), i timeframe con i motivi, i testi delle regole, i collaudi | 1–2 | la tabella dei blocchi esclusi, poi l'ultima riga delle suite |
| **C2** | un blocco per famiglia, i due turni, config versione 2, budget e tetto, stima del tempo dalla velocità vera, celle 1–7, scheda, notebook e glossario, `docs/81`, collaudi; tempo misurato solo su dati sintetici | 1–2 | il notebook su dati sintetici; su dati veri solo con il tuo via |

**Stato (12/11): C1 scritto** (ramo `fabbrica-C1-catalogo`, PR #113), con il via di Mattia sulla tabella D4.
- `engine/fabbrica/blocchi.py`, righe aggiunte: `TRIGGER_CATALOGO` con i 43 trigger del catalogo (E19 solo long: la
  condizione short è `None`, `Blocco.lati` è `(1,)` e la maschera short si ferma con un errore), `FILTRI_CATALOGO` con 28
  filtri (20 neutri, 8 coppie; F36 escluso; i due VWAP dentro), i timeframe e i motivi della tabella di §11.12 in
  `MOTIVI_ESCLUSIONE` e `FILTRI_MAI_VERI`, un'etichetta di famiglia per ogni blocco nuovo; `_registra_catalogo` registra
  anche `registra_filtri_vwap`. I 10 blocchi del catalogo di prima non cambiano.
- `engine/fabbrica/schede.py`: i testi long e short dei 38 trigger e dei 23 filtri nuovi; `blocchi_senza_testo` controlla
  tutto il catalogo.
- `engine/fabbrica/config.py`, **non additivo, dichiarato:** `BLOCCHI_STANDARD` è scritto per intero, con gli stessi 17
  blocchi nello stesso ordine; prima si costruiva dai dizionari del catalogo e sarebbe cresciuto con loro. La config
  standard resta quella di main finché C2 non la cambia.
- Collaudi: `test_fabbrica_blocchi.py` n. 115–123 (§11.7 «Blocchi»; i collaudi di L2 restano sui 10 blocchi di P-L2);
  `test_fabbrica_schede.py` n. 1b; `test_fabbrica_ricerca.py` n. 41, una ricerca piccola con la config standard su dati
  sintetici identica a main, bit per bit (impronta, teorie, prove).
- Per C2: il generatore deve saltare il lato short di un blocco che non lo ha (`Blocco.lati`, oggi solo E19); con il
  generatore di oggi una config scritta a mano con E19 e lo short si ferma all'avvio con l'errore del blocco.

**Stato (14/11): C2 scritto** (ramo `fabbrica-C2-turni`), come in §11.3–§11.8 e §11.10–§11.12.
- `engine/fabbrica/generatore.py`, **non additivo, dichiarato:** `togli_degeneri` controlla anche i blocchi del catalogo
  (degenere su un lato: esce da quel lato; «STATO»: esce con il motivo `STATO_CATALOGO`, la ricerca prosegue; per i blocchi
  con parametri «STATO» resta un errore); `misura_famiglie(blocchi, cache, lati, rimaste)` dà solo le famiglie misurate,
  fra i blocchi rimasti dopo i degeneri (prima univa anche quella dichiarata); nuove `un_blocco_per_famiglia`,
  `teorie_turno_1`, `teorie_turno_2`, `filtri_compatibili`; `genera_teorie` è tolta; `resoconto_teorie` riceve i tenuti e
  dice, per lato, quanti trigger e filtri c'erano e quanti sono tenuti. La famiglia dichiarata (ADX e ATR relativo) vale
  solo in `filtri_compatibili`. E19 sta solo sul long (`Blocco.lati`).
- `engine/fabbrica/config.py`, **non additivo, dichiarato:** `VERSIONE = 2` (una config della versione 1 si ferma con un
  messaggio che dice di rilanciare la cella 2); `budget.teorie_turno_2` (150); `BLOCCHI_STANDARD` con tutto il catalogo,
  scritto per intero (45 trigger, 30 filtri, 3 uscite; la lista di prima resta come `BLOCCHI_P_L2`);
  `budget_massimo(n_teorie, config, teorie_tf, filtri_lato_max)` con il turno 2; nuove `tetto_budget` (D6) e
  `massimo_senza_dati` (il totale di `config_standard` quando non ha i dati: il massimo con tutti i blocchi, mai più piccolo
  di quello vero); `config_standard(..., totale=None)`.
- `engine/fabbrica/ricerca.py`, **non additivo, dichiarato:** `prepara` fa un blocco per famiglia e le teorie del turno 1
  (`controlla=False` per la cella 1, che calcola il tetto dal massimo); `lancia` fa turno 1 (`passo_1.jsonl`, fase
  `passo_1`), turno 2 (`turno_2.jsonl`, fase `passo_1_turno_2`), poi lo zoom sulle `teorie_passo_2` migliori dei due turni;
  l'imbuto ha le chiavi `turno_1`, `turno_1_tenute`, `turno_2`, `turno_2_tenute`, `passo_2`, `altopiano` (prima `teorie` e
  `passo_1_tenute`); la tabella `passo_1` ha la colonna `turno`; l'avanzamento dice «turno 1», «turno 2», «zoom»; tenuti e
  tolti nell'evento di avvio (controllati alla ripresa), in `EsitoRicerca.tenuti_tolti` e nel riepilogo. `_Lavoro.passo_1`
  ha in più solo il parametro della fase.
- `engine/vetrina_fabbrica.py`: cella 1 con una riga per lato («long: 45 trigger → 36 tenuti, …»), la tabella dei tolti e
  quella completa in una sezione chiusa, le teorie dei due turni, le prove massime, il tetto e la stima in minuti «da–a»
  dalla velocità vera delle ricerche del 9 e del 10/11 (`RICERCHE_VERE`: 167 e 146 prove al secondo con 3 processi, in
  proporzione alle barre del pezzo di ricerca; su BTC perp M15, 370.200 prove fanno circa 37–42 minuti); cella 2 per turno;
  cella 3 con i due turni; celle 4–7 su una ricerca della versione 1: «ricerca non trovata: è una ricerca della versione 1,
  rilancia la cella 2 per una ricerca nuova». **Non additivo:** `Configurazione.stima_minuti` è una coppia (da, a).
- `engine/fabbrica/schede.py`: sulla scheda il turno («Da dove viene» e il cammino) e la sezione «Blocchi tenuti e tolti»;
  nel .json `turno` e `blocchi_tenuti_tolti`.
- Notebook: la riga «Turno» nel glossario, gli esempi sopra le celle 1, 2 e 3.
- Collaudi: `test_fabbrica_generatore.py` riscritto (turno 1 e turno 2 a mano, un blocco per famiglia con maschere fatte a
  mano dall'esito noto, STATO, E19, spot); `test_fabbrica_ricerca.py` n. 14–42 sulla ricerca in due turni (ripresa a metà
  del turno 1, del turno 2 e dello zoom) e n. 43–66 su barre sintetiche M15, M5, H1 e uno spot con la config standard
  intera: esclusioni per timeframe, famiglie e tenuti, turni, conto, ripresa, 1 processo = 3, test del veleno;
  `test_vetrina_fabbrica.py` n. 32–35; le altre suite della fabbrica adattate (budget e imbuto nuovi).

### §11.10 · Le decisioni sulle domande (Mattia, 11/11 sera)

- **D1 = B.** ADX e ATR relativo restano tutti e due. Per scegliere i tenuti contano solo le famiglie misurate; la
  dichiarazione vale solo nel generatore: mai nella stessa teoria, anche al turno 2.
- **D2:** per i filtri, «scatta più spesso» vuol dire vero sul maggior numero di barre del pezzo di ricerca; a parità il nome
  più piccolo.
- **D3:** le 150 del turno 2 si scelgono come quelle del passo 2: fra le T+F tenute, il t della migliore strategia che passa
  la condizione 1, i due lati insieme. Se sono meno di 150, vanno tutte.
- **D4:** per ogni blocco nuovo e ogni timeframe da M1 a D1, si legge il codice (finestre in minuti o in ore, orari fissi) e
  si controlla che scatti su barre sintetiche del timeframe. La tabella da approvare elenca **solo i blocchi che restano fuori
  su qualche timeframe**, con il motivo (`MOTIVI_ESCLUSIONE`: limite logico, approssimazione esclusa, escluso solo
  dall'elenco). Arriva a Mattia prima del codice di C1.
- **D5 = B.** Solo la config versione 2: nella ricerca una strada sola. Le ricerche vecchie restano su disco e nel conto;
  le celle 4–7 su una di esse si fermano come «ricerca non trovata», con la riga che dice di rilanciare la cella 2.
- **D6:** il tetto del budget è il massimo nuovo arrotondato in su ai 10.000: 380.000 su BTC perp M15 (§11.5).
- **Due dei 14 nella stessa famiglia misurata (Mattia, 12/11, scelta A):** resta quello che scatta più spesso; a parità,
  il nome più piccolo. Vale per ogni asset e timeframe; ADX e ATR relativo oggi stanno in famiglie misurate diverse (D1 = B).

### §11.11 · Visto a parte (non entra nel lavoro, si decide insieme)

- F22_FAR_FROM_ROLLOVER conta le ore al rollover delle 17:00 di New York del broker: sulle crypto è solo un filtro d'orario.
- La famiglia di un blocco con parametri si misura ai valori centrali anche quando proprio quella combinazione è degenere.

### §11.12 · D4: i blocchi del catalogo esclusi per timeframe (diagnosi del 12/11)

**Come.** Per ogni blocco del catalogo che oggi non è nella fabbrica (38 trigger, 23 filtri compresi i due VWAP) e per ogni
timeframe da M1 a D1:
- ho letto il codice: finestre in barre, minuti od ore, orari fissi, colonne di `aggiungi_indicatori`, e le liste dei
  timeframe ammessi che E46, E48 ed E52 hanno già in `engine/indicatori.py`;
- ho controllato che il blocco scatti su barre sintetiche di quel timeframe (`sintetici.mercato`, lunghe come il pezzo di
  ricerca; M1 tagliato a circa 417 giorni), con `verifica_degenerazione`. Nessun dato vero, nessuna prova.

Script ed esiti in `dati/prove/d4_timeframe_20261112/`, fuori dal repo.

**Da approvare: le coppie (blocco, timeframe) che restano fuori**, con il motivo nello stile di `MOTIVI_ESCLUSIONE`.

| blocco | timeframe | tipo di motivo | motivo |
|---|---|---|---|
| E22 | H4 | approssimazione esclusa per scelta | in estate l'apertura di Londra cade dentro una barra e il range asiatico si allunga di un'ora: una variante della regola |
| E22 | D1 | limite logico | la barra giornaliera è sempre quella delle 00:00: le aperture di Tokyo e di Londra non sono l'inizio di una barra |
| E23 | D1 | limite logico | la giornata è una barra sola: «la prima rottura del giorno» è ogni barra che chiude sopra il massimo di ieri, e due giorni di fila fanno uno stato, non un evento |
| E31 | H1 | approssimazione esclusa per scelta | l'ingresso su H1 coincide con lo schermo H1: i tre schermi diventano due |
| E31 | H4, D1 | limite logico | le candele H4 e H1 dei tre schermi non sono più larghe della barra |
| E37 | H1, H4, D1 | limite logico | le 09:30, le 16:00 e le 16:30 di New York non sono la fine di una candela di questo timeframe |
| E38 | H4, D1 | limite logico | l'ora dalle 07:00 alle 08:00 UTC e la candela che finisce alle 21:00 sono più corte di una barra |
| E39 | H4, D1 | limite logico | l'ora dalle 11:00 alle 12:00 UTC è più corta di una barra |
| E40 | H1, H4, D1 | limite logico | i controlli di mezz'ora sono più corti di una barra |
| E41 | D1 | limite logico | su D1 due giornate di fila nel quintile sono due barre vicine, e `_evento` ne tiene una sola; su M15 sono due segnali |
| E45 | D1 | limite logico | le 4 ore del rendimento sono più corte di una barra |
| E46 | M1 | escluso solo dall'elenco | la regola in minuti sarebbe la stessa; l'elenco dei timeframe del catalogo parte da M5 (aprire M1 è un lavoro futuro, separato) |
| E46 | M30 | approssimazione esclusa per scelta | l'impulso di 45 minuti diventerebbe di 60 (2 barre): una variante della regola |
| E46 | H1, H4, D1 | limite logico | i 45 minuti dell'impulso sono più corti di una barra |
| E48 | M1 | escluso solo dall'elenco | la regola in minuti sarebbe la stessa; l'elenco dei timeframe del catalogo parte da M5 (aprire M1 è un lavoro futuro, separato) |
| E48 | M30, H1, H4, D1 | limite logico | i 15 minuti per lato del massimo locale sono più corti di una barra |
| E52 | M1 | escluso solo dall'elenco | la regola in minuti sarebbe la stessa; l'elenco dei timeframe del catalogo parte da M5 (aprire M1 è un lavoro futuro, separato) |
| E52 | H1, H4 | approssimazione esclusa per scelta | i controlli di mezz'ora diventerebbero ogni ora (ogni 4 ore su H4): una variante della regola |
| E52 | D1 | limite logico | la giornata è una barra sola: nessun controllo dentro la giornata |
| F20_SESSION_ASIA | D1 | limite logico | la barra giornaliera è sempre quella delle 00:00, sempre dentro la sessione di Tokyo nei giorni feriali: il filtro direbbe solo «giorno feriale» |
| F20_SESSION_EUROPE | D1 | limite logico | la barra giornaliera è sempre quella delle 00:00: Londra non è mai aperta |
| F20_SESSION_US | D1 | limite logico | la barra giornaliera è sempre quella delle 00:00: New York non è mai aperta |
| OVERNIGHT_RETURN (F21) | H4 | approssimazione esclusa per scelta | in inverno l'apertura di New York cade dentro la barra delle 12:00 UTC e la fotografia passa alla barra delle 16:00, 3 ore dopo: una variante della regola |
| OVERNIGHT_RETURN (F21) | D1 | limite logico | le aperture di New York non sono l'inizio di una barra giornaliera |
| F22_FAR_FROM_ROLLOVER | D1 | limite logico | la barra giornaliera è sempre quella delle 00:00 UTC, sempre a più di 4 ore dal rollover: il filtro è sempre vero |
| VWAP_GAP_WIDENING | D1 | limite logico | la sessione è una barra sola: la regressione intraday della sessione non esiste |
| VWAP_SESSION_CLOSE | D1 | limite logico | la sessione è una barra sola: la regressione intraday della sessione non esiste |

**Scattano su tutti i timeframe, da M1 a D1:**
- **trigger:** E1, E2, E3, E4, E6, E7, E8, E9, E10, E11, E12, E13, E16, E19, E21, E24, E25, E26, E27, E28, E29, E30, E32,
  E33, E34, E35;
- **filtri:** F1, F2_HIGH, F14, F15, F23, F25_CHOP_RANGE, F26, F29, F32, F35, F39, e le coppie MACD_SIGNAL,
  TREND_CONVICTION, TWO_BARS, VFI_SIGN, ALGOX_STATE.

Gli altri (E22, E23, E31, E37–E41, E45, E46, E48, E52, F20, OVERNIGHT_RETURN, F22, i due VWAP) scattano su tutti i
timeframe che non sono in tabella.

**Il ricontrollo su H4 e D1 (12/11 sera).** Per ogni trigger nuovo tenuto su H4 (29: E1, E2, E3, E4, E6–E13, E16, E19,
E21, E23–E30, E32–E35, E41, E45) e su D1 (26: gli stessi senza E23, E41 ed E45), lato long e short, sulle stesse barre
sintetiche e con M15 come riferimento:
- gli eventi del trigger contro i segnali della regola prima di `_evento`: su barre sintetiche la dinamica per barra non
  dipende dal timeframe, quindi una regola scritta in barre perde la stessa quota su M15, H4 e D1, e una quota che cresce su
  H4 o D1 segnala una regola scritta in tempo;
- per le regole scritte in giornate, gli eventi attesi contati dalla regola: E41 (le giornate nel quintile), E23 (le giornate
  con una rottura), E45 (le barre in cui il rendimento a 4 ore entra nel quintile).

Esito: su H4 e D1 nessun trigger perde eventi più che su M15. E41 ed E45 su H4 hanno tutti gli eventi della regola (E41
253 e 157, E45 637 e 809); le quote perse di E3, E7, E21 ed E34 sono vicine a quelle di M15 (regole scritte in barre: per esempio
E7 74% su M15 e su H4, E3 long 9,4% su M15 e 8,3% su D1). Nessuna riga nuova in tabella dal ricontrollo. Da sapere: E23 su H4 ha tutte le
giornate della regola (434 su 434), ma nel 2,8% delle giornate la rottura cade sull'ultima barra e quella del giorno dopo
sulla prima, cioè su due barre di fila (su M15 lo 0,2%): con la decisione A (§11.3) E23 esce da quel lato, con il motivo,
sui dati dove succede.

Script ed esiti in `dati/prove/d4_timeframe_20261112/` (`d4_sintetici.py`, `d4_ricontrollo_eventi.py`).

**Deciso il 12/11 sera (Mattia):**
- **Finestre in barre lunghe su H4 e D1** (F10, F14, F23, F26, E7, E30 short mai veri sui sintetici di D1; molti blocchi
  «RARA» su H4 e D1): nessuna esclusione. Il controllo dei degeneri a ogni avvio li toglie dove non scattano abbastanza, con
  il motivo nella tabella dei tenuti e dei tolti (§11.3).
- **STATO:** scelta A, in §11.3 e §11.7.
- **E31 su H1:** esce, in tabella.
- **Orari di sessione su H4:** scelta B. F20_SESSION_ASIA, F20_SESSION_EUROPE, F20_SESSION_US e F22 restano su H4, come
  F20_SESSION_OVERLAP; OVERNIGHT_RETURN ed E22 escono su H4, in tabella.
- **VWAP su H4:** restano.
- **E40 ed E41 su M1:** restano (sui sintetici di M1, tagliati a circa 417 giorni, mancava la storia di 250 e 300
  giornate).
- **E41 su D1:** esce, in tabella.
