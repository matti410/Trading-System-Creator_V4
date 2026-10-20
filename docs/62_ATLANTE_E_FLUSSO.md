# 62 · Incarico: dal "guardare" al "costruire" — unità di rischio, funding, atlante, mercato nullo

**Data:** 20 ottobre 2026
**Stato:** INCARICO DI STUDIO. **Nessun codice** prima dell'OK di Mattia.
**Consegna attesa:** `docs/63_PROPOSTA_ATLANTE_E_FLUSSO.md` (proposta con i perché, le firme delle funzioni, cosa si vede nei notebook, il collaudo, le domande).
**Da leggere prima:** `CLAUDE.md`, `docs/00`, `docs/02`, `docs/50` §8 e §12, `docs/61`; i moduli `engine/event_study.py`, `engine/stagionalita.py`, `engine/rosa.py`, `engine/confidenza.py` (`asse_volatilita`, `gap_trend`, `cella_contesto`), `engine/sessioni.py`, `engine/filter_search_bt.py`, `engine/giudizio.py`, `engine/metriche.py`, `engine/exchange.py`, `scarica_dati_crypto.py`, `engine/vetrina.py`.

---

## 0 · Perché questo lavoro

Il tool oggi è un **imbuto a eliminazione**: trigger → uscite → un filtro alla volta → out-of-sample. Ogni passo congela il precedente. L'igiene statistica è buona, ma il tool risponde solo a «questo pezzo regge da solo?». Non risponde a «**in quali condizioni** questo pezzo funziona, e cosa gli metto sopra?».

Tre limiti, in parole semplici:
1. **Le due lenti non si parlano.** Il profilo orario (Lab 2b) e il comportamento dei trigger (Lab 2–3) sono due fotografie separate: nessuna schermata mostra "il trigger X, ora per ora e regime per regime".
2. **Le medie nascondono.** Un trigger che funziona solo in volatilità alta esce piatto nella media e viene scartato prima di essere condizionato.
3. **I filtri si cercano a tappeto** (38 prove sopra un trigger già scelto). La griglia di contesto di `confidenza.py` esiste già, ma arriva per ultima.

**Obiettivo:** inserire nel flusso un metodo per **costruire** un setup condizionato, con la stessa igiene di oggi: parametri fissati prima, controllo dei falsi positivi, due metà, out-of-sample una volta sola. Il metodo deve anche **misurare quanto il tool si inganna** sul rumore.

**La regola di `docs/00` resta valida:** i risultati sui dati collaudano il tool, non sono verdetti.

---

## 1 · Decisioni di Mattia (20/10/2026)

1. Si fanno tre lavori: **A · unità di rischio**, **C · atlante del trigger**, **D · mercato nullo**. In più **B · funding e basis** delle crypto, inserito nella pipeline in modo proprio (non come aggiunta a lato): il flusso delle informazioni deve restare **pulito, coerente e capibile**.
2. Atlante: stati proposti da Claude e approvati. **Volatilità** 2 livelli e **trend** 2 livelli, le stesse definizioni di `confidenza.py` (`asse_volatilita`, `gap_trend`), più la **fascia oraria per sessioni** (`engine/sessioni.py`; sulle crypto in UTC).
3. Meta-labeling e ML: **non qui**. Restano per il repo ML separato.
4. Vanno sistemati i **pips sulle crypto** (vedi §2).
5. Mattia condivide il punto sull'overfitting: l'atlante non è una grid search **se** gli stati sono fissati prima e ogni cella è contata. Il mercato nullo serve a misurare il rischio che resta.

---

## 2 · Lavoro A · Unità di rischio (e i pips sulle crypto)

**Il problema, verificato il 20/10.**
- L'event study lavora in **percentuale** (`event_study.py`, curve in %, convertite in pips solo per la lettura): va bene.
- Il profilo orario (`stagionalita.rendimenti_avanti`), la rosa delle entry (`rosa.rosa_entry`, `scarto_pips`, `t_netto`), le uscite, i filtri, `giudizio.py` e la scheda misurano in **pips** = differenza di prezzo assoluta ÷ pip fisso.
- Sul forex il prezzo cambia poco nei 6 anni e pips e % sono quasi proporzionali. Su BTC il prezzo va da circa 7.000 (2020) a oltre 100.000 (2025): un movimento dell'1% vale 70 pips nel 2020 e 1.000 nel 2025. Medie, t, confronto *tenuti vs scartati* e due metà sono quindi **dominati dagli ultimi anni**, e la prima metà dell'in-sample pesa poco. Vale anche per ETH, SOL, XRP e, in misura minore, per gli indici e l'oro.
- **Come contabilità dei costi i pips restano coerenti:** la commissione in % diventa pips trade per trade al prezzo del trade (`metriche.costo_pips_per_trade`), lo spread è un passo di prezzo. Il problema è solo statistico.

**Cosa chiedo di proporre.**
1. Due unità nuove accanto ai pips, per ogni trade e per ogni rendimento a H barre:
   - **bp del prezzo d'ingresso** (rendimento in centesimi di punto percentuale, netto dei costi);
   - **multipli di ATR** (lo stesso ATR giornaliero a 5 giornate chiuse del money management, `indicatori.atr_giornaliero_chiuso`, noto prima dell'ingresso).
2. Quale unità **decide** nei passi che scelgono (rosa, uscite, filtri, giudizio). Tre strade, con pro e contro:
   - **U1** solo colonne in più, decide ancora il pips; le unità nuove le usano soltanto atlante e mercato nullo. Additiva, identità garantita.
   - **U2** decide il bp per tutti i symbol. Coerente, ma cambia i numeri anche su EURUSD (di poco): prova di identità da riscrivere.
   - **U3** decide il bp solo dove il prezzo cambia molto (crypto, indici). Due regole nel tool.
   Consiglio di partire da U1 e valutare U2 dopo aver visto le differenze su EURUSD e BTC. La decisione resta di Mattia.
3. Nelle schermate i pips restano visibili, perché sono l'unità del live e dei costi (preferenza di Mattia), con la conversione esplicita accanto.
4. Il money management non cambia: lavora già in multipli di rischio.

**Vantaggio:** ogni trade pesa uguale indipendentemente dal prezzo del momento; i confronti fra anni, fra metà dell'in-sample e fra symbol diventano onesti.

---

## 3 · Lavoro B · Funding e basis nei perpetual

**Principio di Mattia:** il flusso delle informazioni deve essere pulito, coerente, capibile. Il funding entra quindi nella pipeline **a ogni livello in cui conta**, sempre nello stesso posto in cui entrano le informazioni analoghe dei CFD:

| livello | cosa | analogo che esiste già |
|---|---|---|
| **dati** | storico dei tassi di funding per i perpetual, scaricato con ccxt in **sola lettura** (funzioni pubbliche, nessuna chiave API), CSV in `dati/` accanto alle barre | `scarica_dati_crypto.py`, `fetch_ohlcv` |
| **costi** | funding pagato o incassato da ogni trade: somma dei funding delle liquidazioni che cadono mentre la posizione è aperta, con il segno del lato (long paga se il tasso è positivo); colonna di costo come `CostoExtraPips`, così entra nei pips netti di tutti i passi | rollover dei CFD (`quarantena_trade.py`, `CostoExtraPips`) |
| **stati** | due variabili di contesto nuove: **livello del funding** (ultimo tasso già liquidato) e **basis** perp–spot dello stesso exchange (prezzo del perpetual meno spot, in bp, alla chiusura della barra; i CSV spot ci sono già) | `asse_volatilita`, `gap_trend` |
| **orari** | le liquidazioni del funding come **orari con un motivo** per il profilo orario e per le condizioni a orario (se il profilo mostra qualcosa intorno alle liquidazioni, ha una causa scritta) | `condizioni_orarie.py` |
| **schede** | la riga «Funding (perpetual): non ancora contato» della schermata 1 diventa il costo contato, separato da commissione e spread | `vetrina.py` riga 658 |

**Da verificare, non da supporre:**
- intervallo delle liquidazioni per ogni symbol ed exchange, e se è cambiato nel tempo (letto dai dati);
- da che data partono gli storici di funding con ccxt su Binance e Bybit;
- se l'open interest storico è disponibile abbastanza indietro (sulle API pubbliche spesso solo pochi giorni): se no, si scarta con il motivo scritto;
- nessun lookahead: come **stato** si usa solo il tasso già liquidato prima della barra; come **costo** il tasso effettivo della liquidazione attraversata dal trade.

**Collaudo da prevedere:** costo del funding su casi costruiti a mano (trade che attraversa 0, 1, 2 liquidazioni; long e short; tasso positivo e negativo); troncamento per gli stati; spot (nessun funding) identico a oggi; identità di tutti i symbol non perpetual.

**Vantaggio:** i risultati dei perpetual diventano netti di un costo che oggi manca; in più due variabili di stato tipiche del mercato crypto, con un motivo economico, a disposizione dell'atlante.

---

## 4 · Lavoro C · L'atlante del trigger

**Cosa è.** Per ogni trigger della rosa (Lab 3), una mappa del rendimento a H barre (stesso H, stessa convenzione dell'event study: segnale sulla barra i, ingresso a Open[i+1], misura a Close[i+H]) divisa per **celle di contesto fissate prima**:
- volatilità: alta / bassa (`asse_volatilita`);
- trend: a favore / contro il lato (`gap_trend`, come in `cella_contesto`);
- sessione (`engine/sessioni.py`; sulle crypto in UTC).
Sui perpetual, dopo il lavoro B, si può aggiungere **una** variabile fra funding e basis, decisa prima di guardare l'atlante.

**Le regole che lo tengono lontano dall'overfitting** (da rispettare tutte):
1. stati e soglie **fissati prima**, gli stessi per tutti i symbol; nessuna soglia scelta guardando l'atlante;
2. misura in **unità di rischio** (lavoro A), netta dei costi;
3. confronto con il **mercato nella stessa cella** (baseline di cella, come la baseline oraria della rosa), così l'atlante misura il trigger e non la deriva del regime;
4. **ogni cella è una prova**: k = trigger × celle × lati; controllo dei falsi positivi (Benjamini–Hochberg, la stessa q della rosa) su tutte insieme;
5. minimo di eventi per cella (da proporre, coerente con `MIN_EVENTI`), sotto il quale la cella non si legge;
6. segno giusto su **entrambe le metà** dell'in-sample;
7. solo in-sample.

**Cosa vede Mattia.** Una schermata nuova fra la scelta dei trigger e le uscite: una mappa a colori per trigger (celle che passano i cancelli evidenziate, le altre in grigio con il motivo), più una tabella. Il riquadro «Come leggerlo» spiega che la scelta della cella conta come una prova.

**Dall'atlante al setup.** Il setup = trigger + cella (o celle) scelte, con una **regola di scelta scritta prima**: per esempio «tutte le celle che passano i cancelli» oppure «al massimo una cella». Il setup continua nel flusso normale: uscite, giudizio, out-of-sample una volta.

**Domanda di metodo da trattare nella proposta:** come convivono l'atlante e la ricerca dei filtri del passo 5. Per esempio l'atlante sostituisce il passo 5 quando lo si usa, oppure il passo 5 resta disponibile e la prova si somma. In ogni caso il conto delle prove dev'essere esplicito.

**Vantaggio:** è il metodo per "cucire sopra": il contesto del trigger non si cerca fra 38 filtri, si **legge** dove il trigger funziona, con poche prove dichiarate.

---

## 5 · Lavoro D · Il mercato nullo

**Cosa è.** Far girare **tutta** la pipeline in-sample (rosa → uscite → filtro o atlante → giudizio) molte volte su un mercato **senza vantaggio**, con le scelte di Mattia sostituite da una regola automatica scritta prima (per esempio: il primo della rosa, le uscite predefinite, il filtro primo in classifica). Si conta quante volte arriva in fondo qualcosa di "promosso" e con quali numeri.

**Due modi di costruire il nulla** (pro e contro nella proposta):
- **trigger casuali sul prezzo vero:** stesso numero di eventi, stessa distribuzione oraria e di lato dei trigger veri, date a caso. Il mercato resta vero, il segnale no.
- **prezzi rimescolati a blocchi** (block bootstrap dei rendimenti, blocchi di una giornata). Distrugge ogni struttura, anche quella oraria.

**Cosa produce:**
- la distribuzione, nel nulla, dei numeri che il tool mostra in fondo (t netto, solidità, P(EV<0), celle promosse dall'atlante);
- la **soglia empirica**: «nel nulla il tool arriva a t ≥ X nel 5% dei giri». È il pezzo che manca a `docs/00` §3: oggi le prove dei passi non si sommano, questo le misura tutte insieme;
- due giri da confrontare: **D1** sulla pipeline di oggi (filtri a tappeto) e **D2** con l'atlante. Mostra con un numero se l'atlante riduce le false scoperte.

**Da curare:** il tempo di calcolo (la ricerca dei filtri richiede circa 30 secondi a giro). Stimare quanti giri servono (almeno 200) e quanto durano in locale, usando i processi paralleli che esistono già. È uno strumento da lanciare dal terminale o dal notebook di ricerca, non dal Lab. Al Lab arriva solo il risultato: una riga nella scheda del tipo «nel mercato nullo un t così capita nel N% dei giri».

**Vantaggio:** ogni scoperta successiva ha accanto la misura di quanto il tool, da solo, trova nel rumore. È ciò che rende credibile un risultato.

---

## 6 · Ordine proposto (da confermare nella proposta)

1. **A** (unità) — la base: atlante e mercato nullo la usano.
2. **B** (funding e basis) — i costi dei perpetual devono essere giusti prima di misurare qualunque cosa sulle crypto; gli stati servono all'atlante.
3. **D1** (mercato nullo sulla pipeline di oggi) — la taratura di partenza.
4. **C** (atlante).
5. **D2** (mercato nullo con l'atlante) — il confronto.

Ogni lavoro: proposta → OK di Mattia → codice → collaudo → identità dei **tre notebook** (`CLAUDE.md`: ricerca, Lab, Lab crypto, aggiornati insieme nello stesso ramo) → commit. Un ramo per lavoro.

---

## 7 · Vincoli (da `CLAUDE.md` e dalle preferenze di Mattia)

- Modifiche all'engine additive; se non lo sono, dichiararlo.
- Indicatori e variabili di stato nuove solo in `engine/indicatori.py`.
- Nessun lookahead: troncamento come nel collaudo del catalogo.
- Exchange: solo funzioni pubbliche di lettura di ccxt; mai chiavi API, ordini o saldi.
- Costi impostati in pips nei parametri, con la conversione pips ↔ bp esplicitata.
- Parametri fissati a priori, mai ottimizzati sui dati; ogni scelta «il migliore fra tanti» va contata.
- Ogni fase nuova spiegata in modo semplice, con il vantaggio concreto: Mattia teme che la complessità aggiunta ingrandisca l'errore.
- Spiegare sempre come si esegue (comandi, dove, cosa si deve vedere).
- Nessun giudizio sui risultati dei run: servono a collaudare.

---

## 8 · Cosa deve contenere `docs/63`

1. Per ogni lavoro (A, B, C, D): cosa si fa, perché, firme delle funzioni (nomi indicativi), file nuovi e file toccati, cosa si vede nei notebook, collaudo, rischi.
2. Le scelte aperte con pro e contro e un consiglio: U1/U2/U3; variabile crypto dell'atlante (funding o basis); regola di scelta delle celle; convivenza atlante / passo 5; modo del mercato nullo e regola automatica delle scelte; numero di giri.
3. Le verifiche sui dati di funding (§3, «Da verificare»), fatte in sola lettura prima di proporre.
4. Le domande per Mattia, numerate.
