# 69 · Incarico: dati in locale, timeframe a scelta, confine dell'in-sample salvato

**Data:** 25 ottobre 2026
**Stato:** INCARICO DI STUDIO. **Nessun codice** prima dell'OK di Mattia.
**Consegna attesa:** `docs/70_PROPOSTA_DATI_E_CONFINE.md`: il flusso nuovo
(Avvio, schermata 1, file salvati), cosa cambia nel codice e cosa resta, il
piano di collaudo e d'identità, le risposte alle domande del §5.
**Da leggere prima:** `CLAUDE.md`, `docs/00`; `docs/68` §9 e §9.1 (diario
dell'out-of-sample, registro per dataset, il limite del riavvio);
`scarica_dati_crypto.py`; `engine/exchange.py` (`scarica_storico`,
`salva_csv`, `controlla_storico`, funding); `engine/vetrina.py` (`prepara`,
`carica_storico`, `carica_funding`); `engine/splitting.py`;
`engine/registro_dataset.py`; la cella Avvio e la schermata 1 di
`Trading_System_Lab_Crypto.ipynb`; le celle iniziali di
`Trading_Grid_Search_v4_backtesting.ipynb`.

---

## 0 · Perché

Oggi i dati si scaricano a parte con `scarica_dati_crypto.py`, si salvano in
CSV e il Lab li legge. Per questo si lavora quasi solo su M15. Mattia vuole
che in locale il Lab scarichi i dati nuovi a ogni run, con il timeframe
scelto ogni volta.

C'è un rischio da chiudere nello stesso lavoro. Il confine fra in-sample e
out-of-sample oggi è l'80% delle barre del CSV: ogni aggiornamento lo sposta in
avanti, e barre che erano out-of-sample diventano in-sample senza che nessuno
lo dica. In più il registro per dataset (`docs/68` §9.1) vive solo finché il
notebook resta aperto.

**Obiettivo:**
1. in locale, il Lab aggiorna i dati del symbol e del timeframe scelti a ogni
   run, se l'utente lo chiede;
2. il confine dell'in-sample diventa una **data salvata su file** e non si
   muove più da solo;
3. il registro (H provati, conto delle prove, diario dell'out-of-sample,
   risalite) si salva nello stesso posto e sopravvive al riavvio;
4. il confine si può **ricalcolare da zero** su richiesta esplicita.

**Cosa NON cambia:** i calcoli del motore, della rosa, dell'atlante, delle
uscite, dei filtri, della scheda, del money management e dello stress test.
Il volume aggressivo è un lavoro separato, dopo questo.

---

## 1 · Fatti del repo (al 25/10/2026, dopo la PR #65)

- `scarica_dati_crypto.py` scarica candele e funding con le sole funzioni
  pubbliche di ccxt, dal 2/1/2020; **se il CSV c'è già scarica solo le barre
  nuove** e controlla la qualità (doppie, buchi, OHLC incoerenti, quarantena).
  Gira solo sul PC: Binance e Bybit bloccano gli indirizzi degli Stati Uniti,
  dove stanno i server di Colab. I CSV si caricano a mano su Google Drive.
- La cella Avvio distingue Colab (dati da Drive) e locale (cartella `dati/`).
- Timeframe previsti: M5, M15, M30, H1, H4.
- `prepara(..., quota_in_sample=0.8)` → `split_is_oos`: confine all'80% delle
  barre.
- `registro_dataset`: la chiave del dataset è symbol, timeframe e confine
  dell'in-sample; il registro è in memoria e si azzera al riavvio.

---

## 2 · Decisioni di Mattia (25/10/2026)

1. **Niente notebook in più:** un interruttore nella cella Avvio, «aggiorna i
   dati: sì/no». Il timeframe si prende dalla schermata 1.
2. **Barre nuove:** finiscono tutte nell'**out-of-sample**. Il confine salvato
   non si muove.
3. **Reset del confine:** deve esistere un modo esplicito per ricalcolarlo da
   zero, come la prima volta, quando arriva una mole importante di dati nuovi.
4. **Colab:** il download avviene **solo in locale**. Colab continua a leggere
   i CSV da Drive.
5. **Volume aggressivo:** lavoro separato, dopo questo.

---

## 3 · Vincoli del progetto

1. **I risultati sui dati collaudano il tool, non sono verdetti.**
2. **Prove d'identità:** con i CSV di oggi e il confine calcolato come oggi
   (80%), i numeri non cambiano, nei due notebook vivi, su
   BINANCE_PERP_BTCUSDT e BYBIT_SPOT_ETHUSDT.
3. **Modifiche all'engine il più possibile additive**; quelle che non lo sono
   vanno dichiarate.
4. **Notebook vivi sempre allineati.**
5. **Il conto delle prove resta onesto.** Un reset del confine apre uno studio
   nuovo e lo dichiara: lo studio vecchio si archivia, non si cancella, con
   quante volte era stato guardato il suo out-of-sample. Se nel nuovo
   in-sample entrano barre che erano out-of-sample già guardato, il tool lo
   scrive in modo visibile.
6. **Niente lookahead e niente dati sporchi:** l'aggiornamento tiene solo
   barre chiuse e ripete i controlli di qualità che `scarica_dati_crypto.py`
   fa già.
7. **Sola lettura verso gli exchange:** solo funzioni pubbliche, senza chiavi
   API.
8. **Test:** `suite_rapida.py` durante il lavoro, `--tutte` prima della PR;
   ogni pezzo nuovo con un collaudo a risultato noto (gli scaricamenti con un
   exchange finto, senza rete, come fanno già i test di `exchange.py`). I test
   esistenti non si ammorbidiscono.
9. **Spiegazioni per chi non l'ha costruito:** l'Avvio e la schermata 1 dicono
   in parole semplici cosa scaricano, dove salvano e cosa vuol dire il
   confine.

---

## 4 · Cosa chiedo nella proposta

### 4.1 · Il flusso nuovo
L'Avvio e la schermata 1 come li vedrà l'utente, in locale e su Colab:
campi, testo dei riquadri, cosa succede con l'interruttore acceso o spento,
cosa succede se il CSV del timeframe scelto non esiste ancora (primo download
completo dal 2/1/2020: quanto tempo, con quale avviso).

### 4.2 · Il file dello studio
Dove si salva il confine (e con quale nome), cosa contiene oltre alla data
(il registro per dataset del `68` §9.1), come si legge su Colab. Il file deve
arrivare anche su Drive: dire come, senza obbligare Mattia a passaggi che
dimenticherebbe.

### 4.3 · Il reset
Come si chiede (campo, nome, predefinito spento), cosa fa (confine all'80% su
tutti i dati di adesso, studio nuovo, archivio del vecchio), cosa mostra.

### 4.4 · Il funding
Si aggiorna insieme alle candele sui perpetual? Cosa succede se il funding
arriva fino a una data diversa da quella delle candele.

### 4.5 · Collaudo, identità, tempi
Test nuovi (aggiornamento incrementale con exchange finto, confine che non si
muove con barre nuove, reset, registro che sopravvive al riavvio simulato,
Colab senza file dello studio). Piano delle prove d'identità del §3.2. Tempi
del download incrementale e di quello completo per timeframe.

---

## 5 · Domande aperte (la proposta risponde, Mattia decide)

1. **Colab senza il file dello studio** (non ancora caricato su Drive): si
   ferma con un messaggio, oppure calcola l'80% e avvisa che il confine
   potrebbe non essere quello del PC?
2. **Più studi sullo stesso symbol e timeframe:** uno solo attivo alla volta,
   o più studi con un nome?
3. **Una soglia per suggerire il reset?** Per esempio quando l'out-of-sample
   supera una certa quota dei dati. Solo un avviso, mai automatico.
4. **Il notebook di ricerca:** stesso file dello studio e stesso registro del
   Lab, o separati?
5. **I symbol da exchange in elenco:** restano gli attuali, o il lavoro
   prepara già l'aggiunta delle altre monete (lista del 13/10: ETH, XRP, SOL,
   TRX, HYPE, ZEC, XMR, LINK, ADA, DOGE)?
