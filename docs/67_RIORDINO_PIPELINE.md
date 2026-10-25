# 67 · Incarico: riordino della pipeline del Lab, schermate 2→4

**Data:** 24 ottobre 2026
**Stato:** INCARICO DI STUDIO. **Nessun codice** prima dell'OK di Mattia.
**Consegna attesa:** `docs/68_PROPOSTA_RIORDINO_PIPELINE.md`: il flusso nuovo
schermata per schermata, cosa cambia nel codice e cosa resta, il conto delle
prove, il piano di collaudo e d'identità, l'allineamento del notebook di
ricerca, le risposte alle domande del §5.
**Da leggere prima:** `CLAUDE.md`, `docs/00`; `docs/02` (soglia di rumore,
unità); `docs/66` §4–§6 (atlante, strada B, soglia cumulata);
`engine/vetrina.py` (da `esplora` a `trova_strategia`, `_soglia_da_conti`,
`_soglia_cumulata_lab`); `engine/rosa.py`; `engine/event_study.py`
(`sintesi`, `barra_picco`, `barra_picco_netto`); `engine/giudizio.py`
(`soglia_rumore`, `soglia_rumore_orizzonte`); `engine/atlante.py`;
`engine/condizioni_orarie.py`; le celle 2–5 di
`Trading_System_Lab_Crypto.ipynb` e le Sessioni 1–2 di
`Trading_Grid_Search_v4_backtesting.ipynb`.

---

## 0 · Perché

Dalla schermata 2 (Esplora) alla 4 (Uscite) il Lab funziona, ma è un
miscuglio: gli stessi trigger si leggono tre volte con tre metri diversi, le
schermate non si passano le scelte e le uscite si impostano a mano, senza un
ponte con quello che l'esplorazione ha misurato. Oggi lo capisce solo chi l'ha
costruito, e con fatica. Il Lab deve diventare leggibile per chi non l'ha
costruito, cioè per il futuro utente del tool.

**Il Lab è un imbuto (funnel).** Si parte da tutto il catalogo e ogni tappa
restringe: casistiche, uscite, sistemi, filtri, out-of-sample. Ogni
restringimento fatto sull'in-sample è una prova, e l'utente deve vedere in
ogni momento quante ne ha fatte (§3.9, §3.10).

**Obiettivo:** ogni passo consegna al successivo **una lista corta**:
1. **Esplora → casistiche.** La rosa produce le casistiche che passano le
   soglie: trigger + lato, più la cella dell'atlante se l'utente la sceglie.
2. **Uscite consigliate per ogni casistica**, ricavate dal comportamento del
   trigger. L'utente le accetta o le modifica.
3. **Rosa dei sistemi → passo 5**, poi tutto come oggi.

**Cosa NON cambia:** il metodo in sette passi di `docs/00`, i calcoli del
motore, della rosa, dell'atlante, dei filtri, delle due metà, della scheda,
del money management e dello stress test. Cambiano l'ordine, la
presentazione e il passaggio delle scelte fra le schermate 2–4 (e il punto 6
del §2).

---

## 1 · Il flusso di oggi (mappa verificata con Mattia il 24/10/2026)

| schermata | riceve | calcola | decide l'utente | passa avanti | prove nella soglia cumulata |
|---|---|---|---|---|---|
| 2 · Esplora | in-sample, H | event study di tutti i trigger: curva lorda **in pips** contro l'ingresso a caso a qualunque ora | — | `s.ev` | i trigger misurati |
| 2b · Profilo orario | in-sample, H | scarto per fascia oraria di un long tenuto H barre, in bp | — | `s.profilo`, **non usato** a valle (rosa, `ORA_`, `X_INVERSIONE_TREND` rifanno il calcolo) | le fasce, solo con un trigger a orario |
| 3a · Classifiche | `s.ev` | primi 8 per lato: picco **in pips**, barra del picco, solidità, «supera il rumore» (`soglia_rumore_orizzonte`) | — | niente | — |
| 3a bis · Rosa dei trigger | in-sample | `rosa_entry`: scarto dal mercato della **stessa ora**, in bp, BH 20%, due metà, famiglie, correlazione | — | niente | — |
| 3b · Scelta | testo libero | `risolvi_scelta` | trigger long e short, anche fuori dalla rosa | trigger; azzera il seguito | fasce, se c'è un trigger a orario |
| 3c · Atlante (facoltativo) | trigger scelti | tutte le entry × 8–10 celle | — | `s.atlante` | celle misurate |
| 3d · Cella (facoltativa) | atlante | filtro `CELLA_…` | una cella per lato | il filtro, **solo al passo 5** | — (al passo 5 non conta due volte) |
| 4 · Uscite | trigger | `run_exit_search_bt`: solo long, solo short, entrambi | barre, stop/target a percentile e regola, per lato, **a mano** (predefiniti fissi 40/25 barre, stop 90, target spento) | `s.uscite`, `s.es` | sistemi provati, a ogni impostazione |
| 4b · Rosa dei sistemi | `s.es` | `rosa_sistemi` | — | niente: il passo 5 usa **sempre** tutti i lati scelti | — |

I sei punti del miscuglio:
1. tre letture degli stessi trigger con metri diversi (2 e 3a contro il
   mercato a qualunque ora, in pips; 3a bis contro il mercato della stessa
   ora, in bp);
2. unità miste: sulle crypto decide il bp, ma 2 e 3a sono in pips;
3. le rose non passano niente: la 3b si scrive a mano e il passo 5 ignora la 4b;
4. la cella si sceglie prima delle uscite, ma le uscite si costruiscono senza
   la cella, che entra solo al passo 5;
5. le uscite non hanno un ponte con l'esplorazione, e l'utente vede quante
   prove ha fatto solo alla schermata 6;
6. il profilo 2b è usato in tre modi diversi, nessuno dichiarato sullo schermo.

---

## 2 · Decisioni di Mattia (24/10/2026)

1. **Classifiche:** diventano un dettaglio a scomparsa, **con lo stesso metro
   della rosa** (bp, scarto dal mercato della stessa ora).
2. **Atlante:** resta facoltativo. Se l'utente sceglie una cella, la cella
   **diventa parte della casistica** e **le uscite si costruiscono già con la
   cella**, non più solo al passo 5.
3. **Uscite consigliate:** **una proposta unica per casistica**: barre dal
   picco della curva, stop e target al percentile standard (punto 8), ora
   d'uscita solo se il trigger è a orario. La proposta conta come una prova
   per casistica. Le modifiche dell'utente si contano come prove, e **il conto
   si vede subito alla schermata 4**, non solo alla 6.
4. **Notebook di ricerca:** stesso flusso, **nello stesso ramo**.
5. **Rosa dei trigger:** un consiglio precompilato. La 3b parte con le
   casistiche della rosa, e l'utente può toglierne o aggiungerne.
6. **Rosa dei sistemi:** la scelta della 4b (solo long, solo short, tutti e
   due) **passa al passo 5**.
7. **Unità:** bp ovunque, pips accanto (sui symbol da exchange; sul broker
   sospeso resta tutto com'è).
8. **Percentile standard delle uscite consigliate:** stop al 90° percentile e
   target spento, come i predefiniti di oggi.

---

## 3 · Vincoli del progetto

1. **I risultati sui dati collaudano il tool, non sono verdetti.** Niente
   giudizi sui trigger o sui sistemi nella proposta né nelle schermate.
2. **Prove d'identità:** a scelte uguali, i numeri non cambiano. Su
   BINANCE_PERP_BTCUSDT, prima e dopo, nei due notebook vivi: event study,
   rosa, atlante, uscite, filtri, scheda. Giro completo su BYBIT_SPOT_ETHUSDT
   (spot, solo long). Dove il numero cambia per decisione di Mattia (uscite
   costruite con la cella, metro della classifica), la proposta lo dichiara e
   dice come si verifica.
3. **Modifiche all'engine il più possibile additive**; quelle che non lo sono
   vanno dichiarate.
4. **Notebook vivi sempre allineati**: il Lab passa da `vetrina.py`. Il
   notebook di ricerca oggi chiama l'engine direttamente nelle Sessioni 1–2:
   la proposta dice come gli si dà lo stesso flusso senza duplicare la logica.
5. **Il conto delle prove resta onesto.** Ogni scelta fatta sull'in-sample
   che non è già contata è una prova: la cella (le celle misurate
   dall'atlante), le uscite provate, ogni modifica dell'utente alle uscite.
   **Togliere o aggiungere casistiche rispetto alla rosa non aggiunge prove**:
   alla schermata 2 sono già contati tutti i trigger misurati. Una stessa
   misura rifatta non conta due volte. La soglia cumulata resta solo
   informativa.
6. **Niente costanti legate a M15:** il timeframe va da M5 a H4.
7. **Test:** `suite_rapida.py` durante il lavoro, `--tutte` prima della PR.
   Ogni pezzo nuovo con un collaudo a risultato noto. I test esistenti non si
   ammorbidiscono.
8. **Spiegazioni per chi non l'ha costruito:** ogni schermata dice in parole
   semplici cosa riceve, cosa mostra, cosa decide l'utente e cosa passa avanti
   (lo stile dei riquadri di oggi).
9. **Ogni tappa dell'imbuto dichiara le sue prove:** quante ne ha fatte lei e
   quante in tutto fin lì. La riga si vede su **ogni schermata**, non solo
   sotto la scheda.
10. **Non si risale in silenzio.** Se dopo la scheda (schermata 6, dove si
    apre l'out-of-sample) l'utente cambia trigger, cella o uscite, il tool
    non lo impedisce ma lo **segnala in modo visibile**: da quel momento
    l'out-of-sample è già stato guardato, e la segnalazione lo dice anche
    nella scheda successiva.
11. **Il flusso lascia due posti liberi**, per lavori successivi:
    - una **schermata prima della rosa**, per la mappa delle anomalie
      (scansione degli stati di una variabile, lavoro 3 dell'ordine dei
      lavori del 24/10);
    - un **orizzonte atteso dichiarato prima** di guardare i dati, collegato
      alla domanda 6 del §5.
    La proposta dice dove si inseriscono senza rifare il flusso di nuovo.

---

## 4 · Cosa chiedo nella proposta

### 4.1 · Il flusso nuovo
La tabella del §1 rifatta per il flusso nuovo, con le stesse colonne, e per
ogni schermata il testo del riquadro in bozza e la riga delle prove (§3.9).
Dire quali funzioni di `vetrina.py` restano, cambiano, si fondono o si
aggiungono, e cosa succede alle celle del Lab (numero, titoli, campi del
modulo). Mostrare dove stanno i due posti liberi del §3.11.

### 4.2 · La casistica
Una definizione precisa: trigger (o più trigger in OR), lato, cella
facoltativa. Dove vive nella sessione, come si mostra, cosa si azzera
quando cambia. Come si costruisce la lista precompilata dalla rosa, e come
l'utente toglie o aggiunge casistiche in un modulo di Colab, che non può
riempirsi da solo con l'uscita di una cella precedente: proporre una o più
soluzioni con i pro e i contro.

### 4.3 · Le uscite consigliate
- **Barre:** da quale curva si prende il picco (oggi `barra_picco` è sulla
  curva lorda in pips; c'è anche `barra_picco_netto`): nel metro nuovo (bp,
  stessa ora) e, con la cella, solo sulle occorrenze dentro la cella. Cosa
  fare se il picco è all'ultima barra di H o vicino all'inizio.
- **Stop e target:** stop al 90° percentile, target spento (§2.8).
- **Ora d'uscita:** solo per i trigger a orario. Dire da dove la si ricava
  (il profilo 2b, il punto in cui la deriva si gira) e come si distingue da
  `X_INVERSIONE_TREND`.
- Come si mostra la proposta accanto ai campi modificabili, e come si
  contano le modifiche (§3.5) nella riga delle prove della schermata 4.

### 4.4 · Il profilo orario 2b
Dove si colloca nel flusso nuovo, e come si rende visibile che fa da
riferimento della rosa, da fonte dei trigger `ORA_` e da fonte delle uscite
orarie. Un solo calcolo, riusato, se si può fare senza cambiare i numeri.

### 4.5 · Dalla 4b al passo 5
Come la scelta del lato (o dei lati) passa a `trova_strategia` e alla
Sessione 3 del notebook di ricerca, senza tornare alla 3b.

### 4.6 · Risalire l'imbuto
Come il tool si accorge che una scelta a monte è cambiata dopo la scheda
(§3.10), cosa mostra e dove, e cosa resta scritto nella scheda successiva.

### 4.7 · Collaudo e identità
Elenco dei test nuovi (casi a risultato noto: proposta d'uscita su una curva
costruita apposta, conto delle prove con modifiche alle uscite e con
casistiche tolte o aggiunte, passaggio della 4b, segnalazione della risalita
dopo la scheda) e piano delle prove d'identità del §3.2.

### 4.8 · Tempi
Quanto costa in secondi il flusso nuovo rispetto a oggi, soprattutto se le
uscite si costruiscono per ogni casistica.

---

## 5 · Domande aperte (la proposta risponde, Mattia decide)

1. **Precompilazione della 3b:** quale meccanismo (§4.2)?
2. **Le casistiche della rosa sono più di una per lato:** si portano avanti
   tutte, in OR come oggi, o una casistica diventa un sistema a sé con le sue
   uscite? Cosa cambia per la rosa dei sistemi e per il passo 5?
   *Criterio, non decisione:* i sistemi separati per casistica sono la strada
   verso il portafoglio di sistemi poco correlati (lavoro futuro). La proposta
   dica quanto ciascuna risposta avvicina o allontana quel lavoro.
3. **Picco della curva:** quale curva e quale regola (§4.3)?
4. **Con la cella:** la proposta d'uscita si ricalcola sulle sole occorrenze
   della cella? Con quante occorrenze minime?
5. **Le curve della schermata 2** mostrano anche il mercato della stessa ora,
   così il metro è uno solo dalla 2 alla 4? Cosa cambia nel grafico e nel
   suo riquadro, e il confronto con il mercato a qualunque ora resta accanto?
6. **Orizzonti multipli.** Oggi la sessione ha un solo H, scelto alla
   schermata 1. Idea di Mattia, da studiare:
   - una griglia piccola **in ore** (per esempio 1, 4, 8, 24 ore), convertita
     in barre per il timeframe scelto (su M15 sono 4, 16, 32, 96; dire cosa
     succede quando un'ora non è un numero intero di barre, per esempio 1 ora
     su H4);
   - un **orizzonte atteso dichiarato prima** di guardare i dati, che decide
     (il posto libero del §3.11);
   - **niente scelta del migliore fra tutti**;
   - un conto delle prove che tenga conto della **sovrapposizione**:
     orizzonti diversi sullo stesso trigger condividono quasi tutte le barre
     e non valgono come prove indipendenti. Verificare
     `giudizio.soglia_rumore_orizzonte`: oggi simula la scelta della barra
     del picco fra 1 e H su una passeggiata casuale (25 barre valgono circa 7
     prove, 48 circa 10) e combina le k entry con Šidák; vale per trigger che
     non si sovrappongono, altrimenti è un pavimento. Dire se la stessa
     simulazione, ristretta ai soli punti della griglia, dà il conto giusto
     per i trigger, per la rosa (che misura lo scarto a H, non il picco) e
     per l'atlante.
   La proposta dice se gli orizzonti multipli entrano in questo lavoro o in uno
   successivo, e cosa costano in tempo e in prove.
7. **Notebook di ricerca:** le parti che ha solo lui (entry-metro, confidenza
   3.3) restano dove sono?
