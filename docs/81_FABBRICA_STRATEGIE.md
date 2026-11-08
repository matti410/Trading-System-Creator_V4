# 81 · Fabbrica di strategie (ricerca automatica)

**Incarico del 04/11/2026, aggiornato l'08/11/2026** (Mattia e il revisore), per Claude Code. Lavoro grande: prima la
proposta in testo.

**Flusso:**
1. proposta in `docs/82_PROPOSTA_FABBRICA_STRATEGIE.md`, solo testo, nessun codice;
2. revisione;
3. via di Mattia, lavoro per lavoro (§7);
4. codice su un ramo per lavoro, collaudo, PR;
5. merge fatto da Mattia.

**Da leggere, e solo questo:** `CLAUDE.md`, `docs/00`, questo file. Per i riusi, solo firme e docstring di:
`engine/motore_veloce.py`, `exchange.py`, `costi.py`, `famiglie.py`, `giudizio.py`, `money_management.py`,
`montecarlo.py`, `registry.py`, `registro_dataset.py`, e in `vetrina.py` solo le funzioni chiamate dal Lab Crypto alle
schermate 6–9. `docs/02` (unità e giudizio), `docs/74` (registro ipotesi). Il libro (§8) non serve.

**Indice:** §1 Perché · §2 Parole · §3 Pipeline · §4 Regole · §5 Notebook · §6 La proposta · §7 Lavori · §8 Il libro

## §1 · Perché

Il Lab Crypto guida una casistica alla volta: Mattia sceglie trigger, uscite e filtri. La fabbrica fa il contrario:
Mattia fissa **prima** lo spazio di ricerca e le regole; lo strumento genera, prova e scarta da solo migliaia di
combinazioni; alla fine restano poche **schede**.

Idea presa dal libro di V. Dolzhenko (2024): molte strategie modeste e diverse fra loro invece di poche eccezionali;
teorie generate combinando blocchi, parametri cercati con l'algoritmo genetico, scrematura veloce, poi zoom sui
parametri, poi prova su dati mai usati per scegliere. Quello che il libro non ha e V4 sì: conto delle prove, famiglie,
costi reali.

La fabbrica è un **progetto separato dal Lab**: usa gli stessi file dei dati e le stesse funzioni del motore, in sola
lettura, ma ha regole, registro e conto delle prove suoi.

Si lavora **su un asset alla volta** (symbol e timeframe scelti nella config), su qualsiasi timeframe da M1 a D1:
nulla nel codice è legato a M15. BINANCE_PERP_BTCUSDT M15 serve a costruire e collaudare la pipeline: i suoi
risultati sono collaudo, non verdetto.

Uscita dell'incarico: per ogni strategia sopravvissuta, la scheda con regole esatte e valori dei parametri. Articoli
e indicatore TradingView sono fuori da questo incarico.

## §2 · Parole (le stesse in codice, notebook e docs)

- **Blocco:** un mattoncino (trigger, filtro, uscita) con i suoi parametri e i loro intervalli. Le condizioni del
  catalogo attuale entrano come blocchi a parametri fissi.
- **Modello:** lo schema di una teoria, es. «1 trigger + fino a 2 filtri + 1 uscita», per lato.
- **Teoria:** un modello riempito con blocchi, senza valori.
- **Strategia:** una teoria con tutti i valori.
- **Giro:** una passata dell'ottimizzatore su una teoria, con intervalli e passo dati (la *SubTheory* del libro).
- **Condizione di qualità:** regole sì/no che una strategia deve passare (trade minimi, drawdown, peso massimo di un
  singolo trade, costi inclusi).
- **Budget:** il numero massimo di strategie provate. Ogni strategia provata è una **prova**.
- **Cassaforte:** l'ultimo pezzo di dati dell'asset. Ogni strategia ci entra **una volta per tratto**; strategie
  nuove possono entrarci, e ognuna è registrata.
- **Test individuale:** il t netto della strategia contro la soglia per una prova sola. È il test che decide.

## §3 · La pipeline

1. **Dati in tre pezzi** dello stesso asset: ricerca, selezione, cassaforte, con durate fisse nella config. La finestra scorre in avanti; la
   nuova cassaforte è fatta solo di barre mai usate come cassaforte.
2. **Config scritta e salvata prima del lancio**, con impronta (hash): blocchi ammessi, intervalli, modelli,
   condizioni di qualità, budget, seed. Un rilancio con config diversa è una ricerca nuova: le prove si sommano nel
   conto.
3. **Generatore:** teorie da modelli × blocchi; scarta le teorie con due blocchi della stessa famiglia (`famiglie.py`).
4. **Passo 1, scrematura:** passo largo (circa N valori per parametro), ottimizzatore tarato in ampiezza, sui soli
   dati di ricerca; condizione di qualità 1 → teoria tenuta o scartata.
5. **Passo 2, zoom:** giri successivi, intervalli stretti attorno alle migliori, passo che cala; stop per numero di
   giri, o forza bruta quando lo spazio è piccolo. **Altopiano:** la strategia scelta deve reggere anche con i valori
   vicini (proporre la misura).
6. **Selezione:** sui dati di selezione, parametri congelati, condizione di qualità 2 e test individuale; famiglie fra
   le sopravvissute.
7. **Conto delle prove, da leggere:** ogni strategia valutata è contata; la scheda mostra il totale e la soglia che
   corrisponderebbe a quel totale, accanto al test individuale. Il conto **non decide**.
8. **Cassaforte:** le strategie scelte si congelano e si scrivono nel registro **prima** di leggere una barra; poi si
   valutano sulla cassaforte con il test individuale. Il registro (data, strategie, esito) non si modifica a mano e
   tiene il numero di strategie entrate in quella cassaforte (da leggere). Nello stesso tratto una strategia già entrata non rientra; un
   parametro cambiato è una strategia nuova.
9. **MM, stress test, verifica dei trade:** riuso di quanto fa il Lab alle schermate 7, 9 e 8.
10. **Scheda:** un `.md` e un `.json` per strategia: blocchi, regole in parole, valori, dati usati, prove contate,
    esito di ogni passo.

## §4 · Regole

- Vale la regola di `docs/00`: i risultati servono a collaudare lo strumento, non sono un verdetto.
- Riuso prima di tutto. Codice nuovo in `engine/fabbrica/` (file nuovi). Altri file solo con modifiche additive,
  dichiarate. Lab Crypto e Grid Search devono restare identici (prova di identità se si tocca il motore).
- La fabbrica non legge e non scrive nulla del Lab: né il suo conto delle prove, né il diario dello studio.
- L'ottimizzatore è separato e non sa nulla di trading (funzione → numero). Si collauda su funzioni di prova note
  (es. Rastrigin) prima che sul mercato.
- Nessun lookahead: ogni blocco nuovo passa `verifica_lookahead` e `verifica_degenerazione`. Nessuna statistica
  (percentili, normalizzazioni) calcolata su tutto il periodo.
- Nessun valore legato a un timeframe: i parametri si scrivono in ore e diventano barre, arrotondate alla barra più
  vicina (minimo 1; minimo 5 per periodo di RSI, periodo di ADX e ATR lungo); il calcolo è tutto in barre, al passo di 1 barra.
- Ogni strategia valutata è una prova, anche se scartata subito.
- La cassaforte non si legge prima del passo 8: un test lo garantisce.
- Seed fisso → stessi risultati. Una ricerca interrotta deve poter riprendere.
- Velocità: nella proposta, stima del tempo per backtest × budget su BINANCE_PERP_BTCUSDT M15, e un tempo obiettivo
  per una ricerca standard sul PC di Mattia. Nessun calcolo che chieda ore a ogni ricerca.
- Solo dati già presenti (OHLCV e funding). Niente download nuovi in questo incarico.

## §5 · Il notebook `Fabbrica_Strategie_Crypto.ipynb`

- Come il Lab: nelle celle solo la chiamata a una funzione di `engine/vetrina_fabbrica.py`.
- Schermate proposte: Avvio · 1 Configura · 2 La ricerca (lancio, avanzamento, ripresa) · 3 L'imbuto · 4 Le
  strategie rimaste · 5 La cassaforte · 6 MM e stress test · 7 Le schede.
- **L'imbuto è la figura principale:** teorie generate → passo 1 → passo 2 → selezione → cassaforte, con il numero a
  ogni passo.
- **Testi per un novizio del trading:**
  - in testa un glossario di circa 10 righe (§2, più long/short, bp, costo, funding, drawdown, t, MM);
  - ogni cella di codice è preceduta da una cella di massimo 6 righe: **Cosa fa** (una frase), **Come leggere**
    (cosa guardare, con un esempio numerico), **Poi** (cosa fare);
  - nessuna sigla senza spiegarla la prima volta;
  - avvisi evidenti solo per ciò che non si può annullare (es. «una strategia entra in un tratto di cassaforte una volta sola»).

## §6 · Cosa contiene la proposta (`docs/82`)

Per ogni punto di §3: come si fa, cosa si riusa (file e funzione), cosa è nuovo (file, funzioni con firma e cosa
restituiscono), come si collauda. Inoltre: la stima di velocità; il formato di config e scheda; le schermate del
notebook con la bozza delle celle markdown; le domande aperte per Mattia, ognuna con un consiglio; i lavori di §7
con i tempi stimati.

## §7 · Lavori (un ramo e una PR ciascuno, in quest'ordine)

- **L1** ottimizzatore (griglia a passo largo e algoritmo genetico), collaudo sulle funzioni di prova.
- **L2** blocchi parametrici e cache degli indicatori, per una lista corta da proporre (es. 5 trigger, 5 filtri,
  3 uscite del catalogo, più RSI, ATR, ADX, Donchian).
- **L3** generatore, passi 1–2, config e registro delle ricerche.
- **L4** selezione, famiglie, conto delle prove, cassaforte.
- **L5** notebook e schede.
- **Dopo, incarico a parte:** price action come blocchi (BOS e CHoCH autonomi, FVG, massimo/minimo del giorno
  prima, order block).

## §8 · Il libro

V. Dolzhenko, *Algorithmic Trading Systems and Strategies: A New Approach*, Apress 2024. Non serve leggerlo: la
struttura utile è in questo file. È protetto da copyright e **non va nel repo**. Se è in `fonti/` (nel
`.gitignore`), consultare solo se serve: cap. 3 (pp. 69–116: teoria, strategia, SubTheory, i tre passi) e cap. 6–7
(pp. 215–325: operatori dell'algoritmo genetico, funzioni di prova). Il codice del libro è C#: non va tradotto.
