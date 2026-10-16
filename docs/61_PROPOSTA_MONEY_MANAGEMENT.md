# 61 · Proposta: money management nel Trading System Lab

**Data:** 16 ottobre 2026
**Stato:** APPROVATA da Mattia il 16/10/2026 (decisioni in §10). Fase 0 in corso; la fase 1 parte solo dopo un nuovo OK.
**Incarico:** `docs/60_MONEY_MANAGEMENT.md`, punto 2.
**Fonte:** Andrea Unger, *The Successful Trader's Guide to Money Management*, Wiley 2021 (PDF in `dati/libri/`, 313 pagine, letto per intero: 12 capitoli, 4 appendici, indice). Le pagine citate sono quelle del libro stampato.
**Letti nel repo:** `CLAUDE.md`, `docs/00`, `docs/02`, `docs/50`, `docs/60`, `Trading_System_Lab.ipynb`, `Trading_Grid_Search_v4_backtesting.ipynb` (sessioni 4 e 5), `engine/vetrina.py`, `engine/montecarlo.py`, `engine/metriche.py`, `engine/simboli.py`, `engine/exit_search_bt.py` (stop adattivo), `engine/giudizio.py` (R multipli), `engine/splitting.py`.
**Non disponibili:** la trascrizione della Lezione 9 e il notebook `EV_MC_Analysis_Strategy_IP_final.ipynb` non sono in `dati/libri/`. Non servono per decidere: il Monte Carlo del tool che ne deriva l'ho letto in `engine/montecarlo.py`.

---

## 0 · In breve

1. **Il metodo di base è il "rischio fisso in percentuale"** (*fixed fractional*, cap. 4.1): a ogni trade si rischia la stessa percentuale del capitale di quel momento. È il metodo che l'autore usa e preferisce, e si adatta molto bene al tool, perché lo stop adattivo dice già **quanto si rischia su ogni trade prima di entrare**.
2. **La percentuale non si sceglie a occhio:** la sceglie il tool sui dati in-sample, con la regola di Mattia ("accetto al massimo X% di drawdown"), facendo girare il Monte Carlo per ogni percentuale possibile. Nel libro si chiama *secure f* (cap. 4.3, cap. 6). Questo realizza la decisione 3 di `docs/60`.
3. **L'out-of-sample si guarda una volta:** con la percentuale già fissata, il tool mostra cosa sarebbe successo al conto (in dollari e in percentuale) sui dati mai visti, e dove cade rispetto a quanto il Monte Carlo in-sample aveva previsto.
4. **Kelly e optimal f si mostrano solo come "confine da non superare"**, mai come percentuale da usare: l'autore li sconsiglia per operare.
5. Il resto del libro (fixed ratio, volatilità, filtro sulla curva dei profitti, z-score, varianti) lo propongo **dopo**, in fasi facoltative, oppure lo scarto con il motivo scritto.
6. Il codice nuovo sta in **un modulo che non sa niente di forex** (`engine/money_management.py`): riceve una tabella di trade e restituisce lotti e capitale. Si copia così com'è nel repo crypto.

---

## 1 · Le idee del libro in parole semplici

| parola | cosa vuol dire |
|---|---|
| **money management** | per l'autore è solo la scelta di **quanto** mettere su un trade. Dove entrare, dove mettere lo stop e quando uscire sono un'altra cosa (*risk management*). Il money management non trasforma un sistema perdente in uno vincente (p. xv, p. 246, p. 279). |
| **anti-martingala** | si aumenta l'esposizione quando il capitale cresce e la si riduce quando cala. La martingala fa il contrario (raddoppia dopo una perdita) e porta prima o poi a perdere tutto (cap. 1). Rischiare sempre la stessa percentuale del capitale è già anti-martingala: dopo una perdita il capitale è più piccolo, quindi il trade successivo è più piccolo. |
| **f** | la frazione del capitale che si accetta di perdere se il trade va allo stop. f = 2% con 10.000 $ vuol dire: se lo stop scatta, perdo 200 $. |
| **rischio del trade (R)** | quanto si perde con 1 lotto se lo stop scatta. Lotti = (capitale × f) ÷ (R in dollari per lotto). |
| **drawdown in percentuale** | quanto il conto è sceso dal suo massimo, in percentuale di quel massimo. Con il capitale che cresce, l'autore giudica la sofferenza in percentuale, non in dollari (p. 59–60, p. 153). |
| **TWR** | il moltiplicatore finale del capitale: 1,30 vuol dire +30%. È il prodotto dei moltiplicatori dei singoli trade (p. 61–62). |

**La lezione che l'autore ripete in tutto il libro:** più si rischia, più si guadagna, **ma solo fino a un punto**. Oltre quel punto il guadagno finale scende e il drawdown esplode; un punto percentuale in più può bloccare il sistema (p. 75–76: col 10% si arriva in fondo, con l'11% il conto non basta più per un contratto). Per questo la percentuale va scelta guardando il drawdown e le sequenze sfortunate (Monte Carlo), non il guadagno finale.

---

## 2 · Quali tecniche hanno senso per il tool, e quali no

Legenda: **SÌ** = da costruire (fase 1); **RIF** = solo come numero di riferimento, non per decidere i lotti; **DOPO** = proposta facoltativa per una fase successiva; **NO** = scartata, con il motivo (riapribile se il motivo cade).

| capitolo | tecnica | proposta | perché |
|---|---|---|---|
| 1 | martingala (aumentare dopo le perdite) | **NO** | rischia di più chi ha di meno; con il capitale finito prima o poi azzera il conto. L'autore la usa solo come esempio da evitare. |
| 1 | anti-martingala | **SÌ (principio)** | è la base di tutto il resto; il rischio fisso in percentuale la realizza da solo. |
| 2–3 | formula di Kelly | **RIF** | dà la percentuale "che massimizza il guadagno" con percentuale di vincite e rapporto vincita/perdita. Ma: si basa sul passato, il futuro può essere peggiore; con perdite oltre lo stop (gap) la "perdita media" non è affidabile; nel libro i drawdown con Kelly sono insopportabili (p. 44–48) e Larry Williams l'ha abbandonata (p. 50, p. 249). L'autore sconsiglia anche "metà Kelly" (p. 248). Utile solo come avviso: "la tua percentuale è X volte sotto Kelly". |
| 4.1 | **rischio fisso in percentuale** (*fixed fractional, percent risk*) | **SÌ (il cuore)** | il più usato e il preferito dall'autore (p. 60). Parte da quanto il trader accetta di perdere. Nel tool lo stop adattivo dà R trade per trade, quindi i lotti si adattano da soli alla volatilità del momento. |
| 4.2 | *optimal f* (Ralph Vince) | **RIF** | la percentuale che, col senno di poi, avrebbe dato il capitale finale più alto. L'autore la sconsiglia per operare (p. 65) e la usa come "orlo del precipizio" (p. 67): oltre si rischia la rovina. La mostro come confine. |
| 4.3 | ***secure f*** (Zamansky) | **SÌ (la calibrazione)** | fra tutte le percentuali si prende quella più alta che **non supera il drawdown scelto dal trader**. È esattamente la decisione 3 di `docs/60`. Al posto del drawdown della sola storia vera (una sequenza sola) uso il Monte Carlo (cap. 6), come fa l'autore. |
| 4.3 | perdita massima storica al posto dello stop (Larry Williams) | **SÌ (come controllo)** | lo stop non è la perdita massima: gap, slippage, stop non attivo sulla barra d'ingresso. Il tool mostra quante volte un trade ha perso più di 1 R e di quanto. Il Monte Carlo usa le perdite vere, quindi ne tiene già conto nel drawdown (p. 135–139). |
| 4.3 | "un contratto ogni 10.000" | **NO** | è un rischio fisso mascherato, più rozzo: non guarda il rischio del trade. |
| 4.4 | *fixed ratio* (Ryan Jones) | **DOPO** (consiglio: no) | nasce per i future, dove il contratto non si divide: si parte da 1 contratto e se ne aggiunge uno ogni "delta" di profitto per contratto. Con i lotti da 0,01 il suo vantaggio principale (operare con poco capitale) quasi sparisce (lo dice anche l'appendice III). Non guarda il rischio del trade: con lo stop adattivo darebbe gli stessi lotti a un trade con stop di 10 pips e a uno di 40. Aggiunge un parametro in dollari (delta) da scegliere. **Sul drawdown il libro gli dà ragione su un sistema singolo** (corretto il 16/10 su segnalazione di Mattia): a parità di rendimento ha il drawdown più basso dei tre metodi (fig. 4.26, p. 88: 38,7% e 62,0% contro 46,5% e 71,3% del rischio fisso); nel Monte Carlo con delta 2.500 i drawdown sono nettamente migliori del rischio fisso al 10% (p. 132–133), con delta 5.000 simili al rischio fisso al 5% ma con qualche caso meno grave (p. 128). Sul portafoglio di tre sistemi invece il drawdown supera il 50% (p. 174–177). Resta "dopo" per i motivi sopra (contratto indivisibile, rischio del trade ignorato), non per il drawdown. |
| 4.5 | percentuale di volatilità (Van Tharp: lotti = capitale × % ÷ ATR) | **DOPO**, oppure come rischio con stop spento | con lo stop adattivo acceso è quasi un doppione: lo stop del tool **è già** una misura di volatilità (percentile delle escursioni). Diventa utile proprio quando lo stop è spento (vedi §3.3). |
| 4.6 | tabella "capitale → lotti" | **SÌ (piccola)** | per il live: la formula e un esempio "con il capitale di oggi e uno stop di N pips, i lotti sono…". |
| 5.2 | *reduced f* (percentuale che scende quando il capitale raddoppia) | **NO per ora** | 4–5 soglie e percentuali scelte a mano: parametri liberi che si finirebbe per scegliere guardando il risultato. L'autore stesso dice che i gradini sono esempi. |
| 5.3 | *aggressive ratio* | **NO** | l'autore la prova e conclude che non dà vantaggi (p. 98). |
| 5.4 | *asymmetric ratio* | **NO** | complica i calcoli senza benefici nei test dell'autore (p. 99–100). |
| 5.5 | *timid–bold* (percentuale bassa sul capitale iniziale, alta sui profitti) | **NO** | l'autore mostra che è solo più rischio travestito: con una base più bassa il sistema si blocca (p. 102–103). |
| 5.6 | ***equity curve trading*** (si opera solo se la curva a 1 lotto è sopra la sua media di 30 trade) | **DOPO** (da discutere) | idea seria: freno di emergenza se il sistema "muore" (p. 109, p. 250). Ma **cambia i trade**, quindi è un filtro sul sistema, non solo sizing; su sistemi già filtrati peggiora lo storico (p. 109–110); sceglierla guardando i risultati sarebbe una prova in più. Se si fa: media 30 fissata prima, calcolata sui trade teorici chiusi (nessun lookahead). |
| 5.7 | z-score (dipendenza fra trade consecutivi) | **DOPO**, solo diagnostica | non per decidere i trade (l'autore non ci crede, p. 250). Serve a un'altra cosa: il Monte Carlo del tool tratta i trade come indipendenti; uno z-score molto negativo (perdite a grappoli) avvisa che il drawdown simulato è ottimista. Servono almeno ~300 trade (p. 112). |
| 6 | Monte Carlo con money management (rendimento e drawdown % su migliaia di sequenze; probabilità di finire in perdita e di **restare bloccati**) | **SÌ** | è lo strumento con cui l'autore sceglie davvero. Diverso da quello di oggi: lì si sommano pips, qui il capitale si moltiplica e i lotti si ricalcolano a ogni trade. |
| 6.2 | stop teorico o perdita massima? | **SÌ (come controllo)** | se molti trade perdono oltre lo stop, l'autore consiglia di dimensionare sulla perdita vera (p. 138–139). Il tool lo mostra; la scelta resta di Mattia (domanda 2). |
| 7 | **piano di lavoro** (drawdown e rendimento attesi dopo 1, 2, 3 anni; soglia oltre cui fermarsi) | **DOPO** (fase 2) | è la versione in percentuale della tabella di controllo dello stress test. La rimando perché lo stress test per ora non si tocca (decisione 2). |
| 8 | più sistemi sullo stesso capitale; capitale di riferimento (*core / total / reduced total equity*) | **NO per ora** | il tool tiene una posizione alla volta: il capitale all'ingresso è quello all'ultimo trade chiuso (l'ultimo metodo del cap. 8.3, p. 171). Da riprendere quando ci saranno più sistemi o più symbol insieme. |
| 9 | azioni: commissione fissa per operazione, leva | **SÌ in parte** | la commissione fissa per trade qui non c'è (conto Standard: tutto nello spread, proporzionale ai lotti). **La leva sì**: con uno stop stretto il rischio fisso può chiedere più nozionale di quanto il broker permetta (domanda 4). |
| 10 | stessa quota di capitale per posizione; "percentuale del capitale" | **DOPO** (per il crypto) | nel crypto spot senza leva e senza stop è il modo naturale: "metto il 20% del conto". Lo propongo come alternativa da discutere per il repo gemello. |
| 11 | regolare i lotti durante il trade; aspettare un ritracciamento | **NO** | il motore non scala posizioni aperte e non cambia gli ingressi. Resta valida la regola: se i lotti calcolati sono zero, il trade non si fa (p. 235–236, p. 246). |
| 12 | domande e risposte | **SÌ (regole)** | prelievi e versamenti si trattano come perdite e guadagni (p. 248); il filtro sulla curva si calcola sui trade teorici (p. 250). |
| App. I | ritoccare lo stop della strategia per sfruttare meglio il money management | **NO** | sarebbe ottimizzare la strategia guardando il risultato del sizing: una prova in più non dichiarata. |
| App. II | rischio per giorno o per mese su più sistemi | **NO per ora** | serve a combinare più sistemi (vedi cap. 8). |
| App. III | lotti frazionari = money management più efficace | **SÌ (si sfrutta)** | con passi da 0,01 lotti i lotti seguono il capitale quasi in continuo. Il tool mostrerà quanto conta l'arrotondamento. |

---

## 3 · Come adattare il libro al tool

### 3.1 Da contratti a lotti

Il libro arrotonda i contratti **per difetto** a un numero intero (p. 39–43). Qui la regola diventa: lotti arrotondati per difetto al **passo** del broker (di solito 0,01), mai sotto il **lotto minimo**, mai sopra il **lotto massimo**. Lotto minimo, passo e massimo **non** sono in `engine/simboli.py`: si leggono da MT5 in sola lettura, **solo col permesso di Mattia** (domanda 3). Propongo di metterli in una tabella **nuova e separata** (per esempio `LOTTI` in `simboli.py`), così la tupla di `SIMBOLI` non cambia e nessun codice esistente si rompe (modifica additiva).

**Se i lotti calcolati sono sotto il minimo** il libro dice: il trade non si fa (anche se poi si perde un trade buono; alzare il rischio per non perderlo è "la scelta più imprudente", p. 236). Consiglio questa regola, contando i trade saltati. L'alternativa (arrotondare al minimo) vuol dire rischiare più della percentuale scelta (domanda 5).

### 3.2 Il rischio di ogni trade, con lo stop acceso

Lo stop adattivo del tool è una **frazione del prezzo d'ingresso** calcolata con dati passati (`soglie_adattive`, già collaudata senza lookahead). Quindi la distanza dallo stop è nota **prima** dell'ingresso: R in pips = frazione × prezzo ÷ pip. È lo stesso R che `giudizio.py` usa già per l'"EV in R multipli".

- Il prezzo per calcolare i lotti è la **chiusura della barra del segnale** (l'ingresso avviene all'apertura della barra dopo, che al momento dell'ordine non si conosce). Così nessun numero viene dal futuro.
- R comprende il costo del trade (spread di listino), perché anche quello si perde se lo stop scatta.
- Una perdita può superare 1 R (gap, stop non attivo sulla barra d'ingresso: limite noto di `docs/00`). Il tool la conta e la mostra.

### 3.3 Il rischio di ogni trade, con lo stop spento

Con `stop = 0` non esiste una distanza dallo stop. Quattro strade:

| | come | pro | contro |
|---|---|---|---|
| **A** | **stop "di calcolo"**: la stessa soglia adattiva del tool (90° percentile delle escursioni contrarie), calcolata ma **non** usata per uscire | nessun parametro nuovo; segue la volatilità del momento (come il modello a volatilità del libro, che nei suoi test dà drawdown più bassi del rischio fisso a parità di guadagno, p. 88, p. 179); stessa logica del caso con stop acceso | senza stop vero le perdite possono superare R spesso; il Monte Carlo lo vede nel drawdown, ma la percentuale per trade va letta come "rischio tipico", non massimo |
| **B** | perdita peggiore dell'in-sample, in percentuale del prezzo (Larry Williams) | la scelta del libro (p. 66–67, p. 249); semplice | un solo trade estremo (es. marzo 2020) decide tutti i lotti; non segue la volatilità |
| **C** | ATR come nel modello a volatilità del libro | è il metodo del libro | serve un periodo di ATR su M15 da scegliere (il libro parla di giorni): una traduzione nostra e un parametro in più |
| **D** | il money management richiede lo stop acceso | niente ambiguità | la sezione non funziona per una parte delle strategie |

**Consiglio A**, con B come alternativa. Decide Mattia (domanda 2).

### 3.4 Il valore del pip, trade per trade

Lo stress test di oggi converte il pip in dollari con il prezzo **dell'ultima barra**. Per il money management non basta: su USDJPY il valore del pip nel 2020 era diverso da oggi, e su DE40 conta il cambio EUR/USD di quel giorno. Propongo:

- **per calcolare i lotti:** valore del pip con il prezzo (e il cambio) della chiusura della barra del segnale;
- **per il guadagno in dollari:** valore del pip all'uscita (il profitto in yen o in euro diventa dollari quando il trade si chiude).

Per EURUSD, GBPUSD, NZDUSD, XAUUSD, US500, USTEC e BTCUSD il valore non cambia (dipende solo dal contratto). Lo stress test resta com'è (decisione 2): per un po' convivono le due convenzioni, e lo scrivo nel riquadro.

### 3.5 Il capitale all'ingresso

Una posizione alla volta e trade che non si sovrappongono: il capitale di ogni trade è quello dopo l'ultimo trade chiuso. Con l'inversione sul segnale opposto un trade si chiude e il nuovo si apre allo stesso prezzo d'apertura: il risultato del primo è già noto, quindi entra nel capitale del secondo. Conto in dollari (domanda 6 per il crypto).

### 3.6 Il tetto della leva

Il rischio fisso guarda solo la perdita allo stop. Con uno stop molto stretto i lotti possono superare quello che il margine consente. Propongo un controllo facoltativo: nozionale del trade ÷ capitale ≤ leva massima del conto. Le leve tipiche di un conto retail europeo sono 30 sulle valute principali, 20 su oro e indici principali, 2 sul crypto; vanno confermate per il conto di Mattia (domanda 4).

---

## 4 · Le fasi, in ordine

### Fase 0 · Preparazione (nessuna novità visibile nei notebook)

1. Lettura da MT5 (sola lettura, col permesso di Mattia) di lotto minimo, passo, massimo e leva dei 9 symbol; tabella nuova `LOTTI` in `simboli.py` e righe di collaudo in `test_simboli.py`.
2. Decisioni di Mattia sulle domande del §9.

**Vantaggio:** i lotti che vedrai sono quelli che il broker accetta davvero.

### Fase 1 · La sezione "7 · Money management" (il cuore)

**Cosa vedi nel Lab**, subito dopo la scheda strategia:

1. **Il rischio dei tuoi trade** (una tabellina): stop medio e mediano in pips e in dollari per lotto; quanti trade hanno perso più di 1 R; perdita peggiore in R.
2. **La scelta della percentuale** (tabella + grafico): per ogni percentuale di rischio da 0,25% in su, il drawdown tipico e quello del caso sfortunato (1 su 20), il rendimento tipico, la probabilità di chiudere in perdita e di **restare bloccati** (capitale troppo piccolo per il lotto minimo). Evidenziata la riga scelta dal tool: la percentuale più alta il cui drawdown sfortunato resta sotto il tuo limite. Sul grafico due linee di confine: optimal f e Kelly.
3. **Cosa sarebbe successo out-of-sample** (tabella + grafico): con la percentuale scelta, il conto in dollari trade dopo trade, accanto alla linea a lotti fissi (gli stessi lotti del primo trade per tutto il periodo), dentro la banda che il Monte Carlo in-sample prevedeva per quel numero di trade. Capitale iniziale e finale, rendimento, drawdown massimo in %, trade saltati, lotti minimi, medi e massimi.
4. **Per il live:** la formula dei lotti e un esempio col capitale finale.
5. Il riquadro "Come leggerlo", con l'avviso che l'out-of-sample si guarda una volta e che la percentuale non si ritocca dopo averlo visto.

**Cosa vedi nel notebook di ricerca:** le stesse tabelle e gli stessi grafici, in una sessione nuova fra l'out-of-sample (Sessione 4) e il Monte Carlo (che diventa Sessione 6), sui trade del sistema finale (`fs_conf` / `oos_conf`, come oggi la Sessione 5). Domanda 7.

**Vantaggio concreto:** oggi il tool dice "quanti pips per trade" e "quanti lotti fissi"; con la fase 1 risponde a "**quanto rischiare su ogni trade per non superare il drawdown che accetto**", con una percentuale scelta da una regola tua e dai soli dati in-sample, e ti fa vedere l'effetto sul conto in dollari.

**Rinumerazione** (decisione 1): 7 · Verifica i trade diventa 8, 8 · Stress test diventa 9, in `vetrina.py` (docstring in testa, riquadri "vai alla schermata…", messaggi "esegui prima la schermata…") e nel notebook (titoli e sottotitolo: oggi dice "in sette passi" ma i passi sono già 8; diventerà "in nove passi").

### Fase 2 · Il piano di lavoro e i controlli (facoltativa, dopo aver visto la fase 1)

- Tabella di controllo in percentuale (cap. 7): dopo 3, 6, 12 mesi di trade (contati dalla frequenza in-sample), drawdown tipico e drawdown "da allarme" in %, con la percentuale scelta. È la tabella da tenere accanto al conto dal vivo.
- z-score dei trade in-sample, come avviso sul Monte Carlo (§2).
- Come far convivere stress test e money management (decisione 2): per esempio il "drawdown che accetti" dello stress test ricavato da capitale × drawdown %.

**Vantaggio:** sai in anticipo a che punto un drawdown smette di essere "normale" per la percentuale che usi.

### Fase 3 · Alternative (facoltativa, da discutere una per una)

- modello a volatilità (ATR) al posto dello stop;
- fixed ratio;
- filtro sulla curva dei profitti (30 trade);
- quota fissa del capitale (per il crypto spot).

Ogni alternativa scelta **dopo** aver visto i risultati conta come una prova in più (`docs/50` §8). Per questo la propongo solo se Mattia ne sceglie una **prima** di guardarle.

---

## 5 · Input e output della cella

### Input (Lab, sezione 7)

```
capitale_iniziale_in_dollari   = 10000   # il conto con cui partiresti
drawdown_massimo_accettato_pct = 20      # oltre questo calo dal massimo smetteresti
orizzonte_anni                 = 1       # su quanto tempo vale la regola del drawdown
```

Fissi, scritti in `vetrina.py` come gli altri parametri (non si toccano dalla cella): percentile del "caso sfortunato" 95 (lo stesso dello stress test), 20.000 simulazioni, griglia delle percentuali, regola dei lotti sotto il minimo, lotti minimi/passo/massimi e leva dalla tabella.

**Perché l'orizzonte:** il drawdown cresce con la lunghezza del periodo. L'autore avverte che il drawdown di 6 anni non è quello da aspettarsi nel primo anno (p. 143). La regola "al massimo 20%" va riferita a un periodo; propongo 1 anno, con i trade contati dalla frequenza dell'in-sample (domanda 8).

### Output

Le tabelle e i grafici della fase 1 (§4). La funzione restituisce anche i dati (tabelle e un dizionario con la percentuale scelta, il capitale out-of-sample trade per trade, i lotti di ogni trade), salvati nella sessione come le altre schermate (`s.mm`).

### Come spiegarlo a un trader (bozza del riquadro)

- **Cosa vedi:** quanto rischiare su ogni trade, in percentuale del conto, e cosa avrebbe fatto il conto sui dati mai visti.
- **Cosa è buono:** la percentuale scelta è quella più alta che, in 19 storie simulate su 20, resta sotto il drawdown che hai detto di accettare. Kelly e optimal f sono il bordo del precipizio: stare molto sotto è normale.
- **Cosa fare adesso:** usa la percentuale scelta; non cambiarla dopo aver visto l'out-of-sample. Poi vai alla verifica dei trade e allo stress test.

---

## 6 · Come progettare il modulo perché sia riusabile nel repo crypto

**Due livelli, due file.**

1. **`engine/money_management.py` — il modulo puro.** Usa solo numpy e pandas; non importa niente da `engine/` (né simboli, né costi, né vetrina). Non sa cosa sia un pip, un forex o MT5. Riceve una **tabella di trade** con, per ogni trade: ora di ingresso e di uscita, risultato netto in "unità di prezzo del symbol" (pips), rischio R nelle stesse unità, valore di 1 unità per 1 lotto all'ingresso e all'uscita (nella valuta del conto), e facoltativo il nozionale di 1 lotto all'ingresso. Più i limiti dei lotti (minimo, passo, massimo) e la leva facoltativa.
   Funzioni proposte (nomi indicativi, da approvare):
   - `kelly(...)`, `optimal_f(...)`: i due numeri di riferimento;
   - `lotti_rischio_fisso(...)`: i lotti di un trade (formula del cap. 4.1 con arrotondamento, minimo, massimo, leva);
   - `ripercorri(...)`: applica una percentuale a una sequenza vera di trade e restituisce capitale, lotti, drawdown %, trade saltati, trade per trade;
   - `montecarlo_mm(...)`: migliaia di sequenze ricampionate (con reimmissione, come `montecarlo.py`), con capitale che si moltiplica e lotti ricalcolati;
   - `calibra(...)`: la griglia delle percentuali e la scelta con la regola del drawdown (secure f).
2. **L'adattatore del V4** (in `vetrina.py`, o in un piccolo file a parte usato da entrambi i notebook, così restano allineati per costruzione): costruisce la tabella dei trade da `s.trades_is` / `s.trades_oos` con `pips_per_trade`, `simboli.py`, lo stop adattivo e il cambio EURUSD per DE40.

Nel repo crypto si copia `money_management.py` (e il suo test) identico; si scrive solo il suo adattatore (lì 1 "lotto" può essere 1 BTC e il passo quello dell'exchange). **Modifiche all'engine esistente:** nessuna; solo file nuovi, la tabella `LOTTI` aggiunta e le righe nuove in `vetrina.py`. L'unica modifica non additiva prevista è la rinumerazione dei testi delle schermate 7 e 8 (decisione 1).

---

## 7 · Come collaudare ogni pezzo

Un file nuovo, `test_money_management.py`, con l'ultima riga `RISULTATO: n/n test superati`, più tutte le suite esistenti prima del commit.

**1 · Esempi numerici del libro (risultato noto).** Già rifatti a mano oggi, tornano:

| esempio | pagina | cosa deve uscire |
|---|---|---|
| 10 trade, capitale 100.000, stop 1.250, f da 2,5% a 50% | tab. 4.2 e fig. 4.1, p. 56–57 | contratti trade per trade e capitale finale identici per tutte le 8 percentuali (es. 5%: 4, 3, 4, 4, 3, 3, 4, 5, 4, 4 contratti; 123.150 finale) |
| drawdown % degli stessi trade | fig. 4.2, p. 58 | 3,44% · 7,64% · 12,53% · 16,26% · 24,42% · 69,91% (vedi nota sotto per 20% e 25%) |
| TWR teorici | fig. 4.4, p. 64 | 1,1366 · 1,2732 · 1,4082 · 1,5397 · 1,7857 · 1,9980 · 2,1647 · 2,0726 |
| Kelly | p. 22–29, p. 37–40 | 10% (moneta 1,25:1) · 11,11% e 6,67% (palline) · 10,6265% (sistema del cap. 3) |
| capitale che non basta più | tab. 6.3, p. 116 | con 14.900 e il 10% su stop 1.500: zero contratti, trade saltati |
| formula con prezzo e stop | p. 220–223 (Mediaset, DAX) | 3.636 azioni; 0 contratti DAX (rischio 2.400 > 2.000) |
| fixed ratio (se si farà) | p. 72 | 52.500 → 2 contratti; 57.500 → 3 |
| z-score (se si farà) | p. 112 | 0,2364 |

**Due incongruenze del libro**, trovate rifacendo i conti (i test le dichiarano, non le copiano):
- fig. 4.2, colonne 20% e 25%: alcune righe misurano il drawdown da un massimo sbagliato (es. 15.400 di drawdown su un nuovo massimo). Rifatti, i massimi sono 31,74% e 39,01% invece di 33,64% e 43,41%. Le altre sei colonne tornano esatte.
- optimal f dei 10 trade: il libro scrive 37% con TWR 2,3251. 2,3251 è il TWR al 37%, ma il massimo è al **36%** (2,3260): probabilmente uno slittamento di una colonna nel grafico Excel.

**2 · Nessun lookahead.** Troncamento come nel resto del tool: si cambiano o si tolgono i trade dopo il k-esimo, e lotti e capitale fino al k-esimo devono restare identici. In più: i lotti usano solo la chiusura della barra del segnale (test con un prezzo d'ingresso falsato: i lotti non cambiano).

**3 · Identità con i risultati già validati.** In tutti questi test il **salto dei trade sotto il lotto minimo è disattivato** (lotto minimo e tetto della leva spenti), così nessun trade sparisce e il confronto è esatto. Il salto si prova **a parte**, con casi costruiti apposta (tab. 6.3 del libro; capitale che scende sotto il minimo e poi risale; conteggio dei trade saltati). Regola di Mattia del 16/10.
- il money management **non cambia i trade**: pips netti per trade identici a `pips_per_dataset`; scheda, verifica dei trade e stress test identici prima e dopo;
- con "lotti fissi" (percentuale ignorata, 1 lotto) il guadagno in dollari è esattamente pips × valore del pip;
- con passo zero (lotti continui) il capitale finale è esattamente capitale × TWR;
- il Monte Carlo con una sola sequenza "ricampionata" uguale alla vera dà il risultato di `ripercorri`.

**4 · I due notebook** (`CLAUDE.md`): identità su EURUSD a parità di barre per tutte le schermate che già esistono (prima e dopo), e un giro completo su DE40 (cambio EUR/USD trade per trade, lotti minimi degli indici) e su BTCUSD.

**5 · Casi limite:** zero trade out-of-sample; meno di 30 trade (avviso, come `montecarlo.py`); stop spento (la strada scelta al §3.3); lotti sempre sotto il minimo (tutto saltato, detto in chiaro); USDJPY con prezzo che cambia.

---

## 8 · Rischi e punti dubbi

1. **I numeri in dollari ingannano.** Con l'interesse composto le curve esplodono e il capitale finale può sembrare enorme: l'autore lo ripete in ogni capitolo. Per questo mostro in primo piano percentuali, drawdown e valori **tipici** (mediana), non il caso migliore.
2. **Ottimismo dell'in-sample.** I trade in-sample sono quelli su cui la strategia è stata scelta (trigger e filtri): il drawdown simulato tende a essere migliore del futuro, e la percentuale scelta un po' troppo alta. Il percentile 95 e l'orizzonte aiutano ma non bastano. L'autore suggerisce di fare il Monte Carlo sul sistema **senza** filtri quando è molto filtrato (p. 250). Domanda 9.
3. **Trade trattati come indipendenti** (limite già noto di `montecarlo.py`): con perdite a grappoli il drawdown vero può essere peggiore. Lo z-score della fase 2 lo segnala.
4. **Perdite oltre lo stop:** lo stop non è attivo sulla barra d'ingresso e i gap esistono. Su un singolo trade si può perdere più di f. Il tool lo mostra (perdita peggiore in R e in % del conto).
5. **Leva e margine:** senza tetto il rischio fisso può chiedere lotti che il conto non consente.
6. **Due convenzioni per il valore del pip** (ultima barra nello stress test, barra del segnale nel money management) fino a quando si rivede lo stress test.
7. **Lotti minimi sconosciuti** finché non si leggono da MT5. Su BTCUSD, indici e oro il lotto minimo può pesare molto con un conto piccolo.
8. **Lo swap notturno** non è nel backtest (limite già esistente): con più lotti cresce in proporzione.
9. **Seconda occhiata all'out-of-sample:** la sezione 7 mostra di nuovo i dati out-of-sample. È lecito perché la percentuale è fissata prima, sull'in-sample; non lo è più se si torna indietro a cambiarla. Il riquadro lo dice.
10. **Pochi trade out-of-sample:** l'effetto del money management si vede poco; è un'informazione, non un difetto.
11. **Complessità:** la fase 1 aggiunge un modulo e una schermata; nessun calcolo esistente cambia. Le fasi 2 e 3 si fanno solo se Mattia le vuole dopo aver visto la 1.

---

## 9 · Domande a cui solo Mattia può rispondere

1. **Il piano in fasi** (§4): OK alla fase 0 e alla fase 1 così come sono descritte? Le fasi 2 e 3 le decidiamo dopo?
2. **Rischio con stop spento** (§3.3): A (stop di calcolo, consigliato), B (perdita peggiore in-sample), C (ATR) o D (sezione non disponibile)? E con lo stop acceso: R = distanza dello stop + costo (consigliato), o dimensionare sulla perdita peggiore vista se molti trade perdono oltre lo stop?
3. **MT5:** posso leggere in sola lettura, con `symbol_info`, lotto minimo, passo, massimo e leva/margine dei 9 symbol, e scriverli nella tabella nuova `LOTTI`?
4. **Leva:** il conto è retail europeo (30 / 20 / 2) o professionale? Vuoi il tetto della leva nel calcolo dei lotti?
5. **Lotti sotto il minimo:** saltare il trade (consigliato, come il libro) o arrotondare al minimo?
6. **Valuta del conto:** dollari per il V4. Per il repo crypto: dollari o USDT? (Serve solo all'adattatore, il modulo non cambia.)
7. **Notebook di ricerca:** la sezione nuova diventa "Sessione 5 · Money management" e il Monte Carlo passa a Sessione 6?
8. **Regola del drawdown:** valori predefiniti nella cella (10.000 $, 20%, 1 anno) e percentile 95 come lo stress test: vanno bene?
9. **Su quali trade calibrare:** in-sample della strategia scelta (consigliato, con l'avviso del §8 punto 2) o anche la variante prudente sul sistema base senza filtri?
10. **Kelly e optimal f** come linee di riferimento sul grafico: sì o no?

---

## 10 · Decisioni di Mattia (16/10/2026)

1. Sì alla fase 0 e alla fase 1; le fasi 2 e 3 si decidono dopo.
2. Stop spento: **strada A** (stop di calcolo), letta come "rischio tipico", non massimo. Stop acceso: **R = distanza dello stop + costo**.
3. Lettura da MT5 autorizzata **solo in sola lettura**, con `symbol_info` e `account_info`: lotto minimo, passo, lotto massimo, margine e leva dei 9 symbol. Nessun ordine.
4. Conto retail europeo, ma la leva si legge da MT5. **Sì al tetto della leva**, contando quante volte interviene.
5. Lotti sotto il minimo: **il trade si salta**.
6. Valuta del conto: dollari, per ora.
7. Notebook di ricerca: sessione nuova "Sessione 5 · Money management"; il Monte Carlo passa a Sessione 6.
8. Sì ai valori predefiniti (10.000 $, 20%, 1 anno, percentile 95); da unificare con lo stress test nella fase 2.
9. Calibrazione **solo sull'in-sample della strategia scelta**.
10. Sì a Kelly e optimal f come linee di riferimento sul grafico.

Controlli chiesti prima di partire:
- **A · fixed ratio e drawdown:** il testo del §2 diceva che nel libro il fixed ratio non dà drawdown migliori. Era sbagliato: su un sistema singolo ha il drawdown più basso a parità di rendimento (p. 88, p. 128–133); peggiore solo sul portafoglio (p. 174–177). Corretto il §2; la proposta "dopo" resta, per gli altri motivi.
- **B · test di identità:** salto sotto il lotto minimo e tetto della leva disattivati; il salto si prova a parte. Aggiunto al §7.

---

## 11 · Fase 0: cosa è stato letto da MT5 (16/10/2026)

Lettura in sola lettura (`account_info`, `symbol_info`), terminale già aperto, server ICMarketsEU-Demo. Nessun ordine. Login, nome e credenziali non stampati.

**Conto:** valuta USD; `trade_mode` = 0, cioè **conto demo**; leva del conto **1:100**; margin call al 100%, stop out al 50%.

**Lotti** (scritti nella tabella nuova `LOTTI` di `engine/simboli.py`, controllati in `test_simboli.py`):

| symbol | lotto minimo | passo | lotto massimo | calcolo del margine in MT5 |
|---|---|---|---|---|
| EURUSD | 0,01 | 0,01 | 200 | Forex (contratto ÷ leva) |
| GBPUSD | 0,01 | 0,01 | 200 | Forex |
| USDJPY | 0,01 | 0,01 | 200 | Forex |
| NZDUSD | 0,01 | 0,01 | 100 | Forex |
| XAUUSD | 0,01 | 0,01 | 100 | Forex (100 once) |
| US500 | **0,1** | **0,1** | 250 | CFD |
| USTEC | **0,1** | **0,1** | 250 | CFD |
| DE40 | **0,1** | **0,1** | 250 | CFD |
| BTCUSD | 0,01 | 0,01 | **10** | CFD |

**Leva per symbol: non leggibile con le due funzioni autorizzate.**
- Forex e oro usano la leva del conto (1:100 sul demo).
- Indici e BTCUSD sono "CFD": il loro margine dipende da un tasso per symbol che `symbol_info` non dà (il campo `margin_initial` è 0).
- La leva del demo (1:100) **non è quella di un conto retail europeo reale** (30 sulle valute principali, 20 su oro e indici principali, 2 sul crypto).

**Decisione di Mattia (16/10/2026): schema retail europeo**, scritto a mano nella tabella nuova `LEVA` di `engine/simboli.py`: 30 su EURUSD, GBPUSD, USDJPY; 20 su NZDUSD (coppia non principale), XAUUSD, US500, USTEC, DE40; 2 su BTCUSD. La leva del demo non si usa.
