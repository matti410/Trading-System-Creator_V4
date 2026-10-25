# 70 · Proposta: dati in locale, timeframe a scelta, confine dell'in-sample salvato

**Data:** 25 ottobre 2026
**Stato:** PROPOSTA APPROVATA da Mattia il 25/10/2026, con le decisioni del §14.
Il codice va in due Pull request: A (engine e test) e B (`prepara`, Lab, notebook di ricerca).
**Risponde a:** `docs/69_DATI_E_CONFINE.md` (l'incarico), con le indicazioni di
Mattia del 25/10 sulla bozza: Drive per desktop raccomandato, ma senza
conflitti fra PC e Colab; reset con la data nel campo; **un confine unico per
tutto lo studio**, cioè per tutti gli exchange, le monete e i timeframe.
**Letti:** `CLAUDE.md`, `docs/00`, `docs/68` §9 e §9.1, `scarica_dati_crypto.py`,
`engine/exchange.py`, `engine/vetrina.py` (`prepara`, `carica_storico`,
`carica_funding`, `aggancia_spot`, `registro_orizzonte`, `segna_oos`,
`_diario_oos`), `engine/splitting.py`, `engine/registro_dataset.py`, la cella
Avvio e la schermata 1 del Lab crypto, le celle 4, 11, 20 e 24 del notebook di
ricerca.

**Indice:** §0 In breve · §1 Il flusso nuovo · §2 Il confine unico · §3 I file
dello studio · §4 PC e Colab senza conflitti · §5 Il reset · §6 Funding e spot
· §7 Cosa cambia nel codice e cosa resta · §8 Collaudo · §9 Identità · §10 Tempi
· §11 Rischi · §12 Le domande del `69` §5 · §13 Fuori incarico · §14 Decisioni
di Mattia · §15 Resoconto

---

## 0 · In breve

- **Avvio:** un interruttore «aggiorna i dati». In locale, se è acceso, la
  schermata 1 scarica le barre nuove del symbol e del timeframe scelti (più il
  funding e lo spot del perpetual) prima di caricarle. Su Colab l'interruttore
  non fa niente e lo dice.
- **Un confine unico per tutto lo studio**: una data e un'ora, uguali per
  Binance e Bybit, spot e perpetual, tutte le monete e tutti i timeframe. Le
  crypto si muovono insieme: un out-of-sample guardato su BTC dice già qualcosa
  su ETH nello stesso periodo. Il confine lo fissa il primo dataset aperto,
  all'80% delle sue barre; poi è scritto in un file e non si muove più. Le barre
  nuove finiscono tutte nell'out-of-sample.
- **Il registro del `68` §9.1** (H provati, conto delle prove, diario
  dell'out-of-sample, risalite) resta per dataset e si salva su file, così
  sopravvive al riavvio. Ogni macchina (il PC, Colab) scrive **solo il suo
  giornale e solo in aggiunta**: due macchine non scrivono mai lo stesso file
  (§4).
- **Un'impronta dell'in-sample** per dataset controlla a ogni avvio che le barre
  dell'in-sample siano ancora quelle con cui il dataset è entrato nello studio.
- **Il reset** si chiede scrivendo la data di oggi in un campo della schermata
  1. Ricalcola il confine unico e manda in archivio lo studio intero. Se il
  nuovo in-sample contiene un periodo già guardato come out-of-sample (su
  qualunque dataset), il tool lo scrive in arancione, e la scritta resta.
- **Per Drive** la raccomandazione è Google Drive per desktop, che oggi sul PC
  non c'è (§4).
- **Prove d'identità:** su BINANCE_PERP_BTCUSDT il confine unico coincide con
  quello di oggi, quindi i numeri sono identici al bit. Su BYBIT_SPOT_ETHUSDT
  il confine unico è diverso; per l'identità c'è un parametro che forza il
  confine vecchio (§2.4, §9).

---

## 1 · Il flusso nuovo

### 1.1 · L'Avvio

Il form dell'Avvio ha un campo in più:

```
aggiorna_dati = True   #@param {type:"boolean"}
```

Il testo del riquadro sopra la cella diventa:

> **Avvio.** Da eseguire una volta sola, all'inizio. Richiede circa un minuto.
>
> **Aggiorna i dati** (solo sul PC). Se è acceso, alla schermata 1 il Lab
> chiede all'exchange le barre chiuse dopo l'ultima che ha già e le aggiunge al
> file. Sul perpetual aggiorna anche il funding e lo spot della stessa coppia.
> Usa solo le funzioni pubbliche di lettura di Binance e Bybit, senza chiavi:
> nessun ordine è possibile. Su Colab i dati non si scaricano, perché Binance e
> Bybit bloccano i server di Colab, che sono negli Stati Uniti: il Lab legge i
> file che trova su Drive.
>
> **Dove stanno i dati.** Sul PC nella cartella di Drive, se c'è Google Drive per
> desktop (§4), altrimenti in `dati/`; su Colab in
> `Il mio Drive/Trading-System-Creator_V4/dati/`.
>
> **Drive per desktop:** usalo in modalità **streaming** e rendi disponibile
> offline solo la cartella `Trading-System-Creator_V4`. Mai il mirroring di
> tutto il Drive: copierebbe sul PC ogni file che hai su Drive.

Cosa fa la cella:
- in locale scrive `AGGIORNA_DATI = aggiorna_dati`;
- su Colab scrive `AGGIORNA_DATI = False`, con una riga che dice che
  l'interruttore è ignorato;
- in locale, con l'interruttore acceso, controlla che `ccxt` ci sia e, se manca,
  dice il comando per installarlo (`pip install ccxt==4.5.78 truststore==0.10.1`)
  senza installarlo da sola;
- in locale cerca la cartella di Drive (§4.1).

Il download non avviene qui, perché il timeframe si sceglie alla schermata 1
(decisione 1 di Mattia).

### 1.2 · La schermata 1

Il form ha un campo in più, il reset (§5):

```
ricalcola_confine = ""   #@param {type:"string"}
```

Con l'interruttore acceso, prima della tabella «Il tuo laboratorio» compare il
riquadro dell'aggiornamento:

> **Dati aggiornati.** BINANCE_PERP_BTCUSDT M15: +562 barre nuove, dal
> 19/10/2026 13:30 al 25/10/2026 09:45 UTC. Controlli sulle barre nuove: 0
> doppie, 0 buchi, 0 OHLC incoerenti, 0 in quarantena. Funding: +18 tassi, fino
> al 25/10/2026 08:00. Spot BINANCE_SPOT_BTCUSDT M15: +563 barre. Tutte le
> barre nuove sono nell'out-of-sample: il confine non si è mosso.

Nella tabella «Il tuo laboratorio» le righe dell'in-sample dicono da dove viene
il confine (numeri d'esempio su ETH spot di Bybit):

| | |
|---|---|
| In-sample (per costruire) | 137.412 barre (74%), fino al 10/06/2025 01:00 UTC · **confine dello studio** |
| Out-of-sample (mai visto) | 48.230 barre, dal 10/06/2025 01:00 (di cui 563 arrivate oggi) |
| Studio | aperto il 25/10/2026 su BINANCE_PERP_BTCUSDT M15 · vale per tutti i dataset · out-of-sample guardato: 0 volte su questo dataset, 2 su altri dataset |

Il riquadro sotto la tabella spiega il confine in parole semplici:

> Il confine è la data che divide le barre su cui costruisci (prima) da quelle
> che restano chiuse fino alla scheda (dopo). È **uno solo per tutto lo
> studio**: ogni exchange, moneta e timeframe usa la stessa data, perché le
> crypto si muovono insieme e un periodo guardato su BTC non è più nuovo per
> ETH. L'ha fissato il primo dataset aperto (80% delle sue barre) e non si muove
> più: le barre che arrivano dopo vanno tutte nell'out-of-sample. Il conto
> delle prove e il diario dell'out-of-sample stanno in un file e restano anche
> se chiudi il notebook.

La frase di oggi («restano finché il notebook è aperto … riavviare il notebook
sì») sparisce dal testo della schermata 1 e da `_nota_dataset`.

### 1.3 · I casi

| caso | cosa succede |
|---|---|
| interruttore spento, CSV c'è | come oggi: legge il CSV, nessuna rete |
| interruttore acceso, CSV c'è | scarica solo le barre dopo l'ultima (pochi secondi), fa i controlli, salva, prosegue |
| interruttore acceso, CSV non c'è | **primo download completo** dal 2/1/2020. Prima di partire, un riquadro dice cosa scarica, quanto tempo serve (§10) e che la cella si può fermare e rilanciare senza perdere niente (vedi sotto). Ogni 50 blocchi stampa una riga di avanzamento, come oggi lo script |
| interruttore spento, CSV non c'è | si ferma, come oggi, e dice di accendere l'interruttore (in locale) o di caricare il file su Drive (su Colab) |
| exchange irraggiungibile (rete, manutenzione) | **non si ferma**: avviso arancione «aggiornamento non riuscito: lavori sui dati fino al …», e prosegue con il CSV che c'è. Si ferma solo se il CSV non esiste |
| nessuno studio aperto (primo avvio in assoluto, sul PC) | si apre lo studio: il confine è l'80% delle barre di questo dataset (§2.1) |
| dataset nuovo in uno studio già aperto | il dataset entra nello studio con il confine unico e la sua impronta (§3.2) |

**Ripresa del download completo.** Oggi lo script salva il CSV solo alla fine,
e un primo M5 completo dura minuti (§10). La proposta salva il CSV ogni 100
blocchi: se la cella si ferma, il giro dopo riparte dall'ultima barra salvata,
con la stessa logica incrementale di oggi.

### 1.4 · Su Colab

- L'Avvio monta Drive, come oggi.
- La schermata 1 legge da Drive i CSV e i file dello studio.
- Se lo studio non c'è, si ferma (domanda 1, §12.1).
- Il diario e il conto delle prove scritti su Colab vanno nel giornale di
  Colab, su Drive (§4). Il PC li ritrova se legge la stessa cartella, cioè con
  Drive per desktop.

---

## 2 · Il confine unico

### 2.1 · Cos'è e chi lo fissa

Il confine è **un istante**: la fine dell'ultima barra in-sample. Per BTC perp
M15, sui CSV di oggi, è il 10/06/2025 alle 01:00 UTC: l'ultima barra
in-sample è quella delle 00:45, che si chiude all'01:00.

Su ogni dataset l'in-sample sono le barre che **si chiudono** entro il confine,
l'out-of-sample le altre. Con «si chiudono» la regola vale uguale per M5 e per
H4: una barra H4 delle 00:00 si chiude alle 04:00, quindi è out-of-sample.
Nessuna barra dell'in-sample contiene un minuto oltre il confine.

**Il primo dataset aperto** fissa il confine, all'80% delle sue barre, con la
regola di oggi (`split_is_oos`). La schermata 1 lo dice in un riquadro: «Hai
aperto lo studio: il confine è il 10/06/2025 01:00 UTC (80% delle barre di
BINANCE_PERP_BTCUSDT M15). Vale da ora per ogni exchange, moneta e timeframe.»
È raccomandato aprire lo studio sul dataset di sviluppo, BINANCE_PERP_BTCUSDT M15.

### 2.2 · Quanto pesa l'in-sample sugli altri dataset

Con il confine del 10/06/2025 01:00, sui CSV M15 di oggi:

| dataset | prima barra | in-sample |
|---|---|---|
| Binance perp BTC, ETH, XRP; Binance spot BTC, ETH, XRP | 2/1/2020 (XRP perp 6/1/2020) | 80,0% |
| Binance perp SOL | 14/09/2020 | 77,7% |
| Binance spot SOL | 11/08/2020 | 78,0% |
| Bybit perp BTC | 25/03/2020 | 79,3% |
| Bybit perp ETH, XRP | 15/03/2021, 13/05/2021 | 75,7%, 75,0% |
| Bybit spot BTC, ETH, XRP | luglio 2021 | 74,2%, 74,2%, 74,0% |
| Bybit perp e spot SOL | ottobre 2021 | 72,9%, 72,7% |

L'out-of-sample è lo stesso periodo per tutti (circa 47.670 barre M15). A
cambiare è solo quanta storia c'è prima: i dataset che partono più tardi hanno
un in-sample più corto. La schermata 1 mostra la quota accanto alle barre.
Se l'in-sample scende sotto il 50% (una moneta quotata da poco), aggiunge un
avviso: «l'in-sample di questo dataset è corto: i risultati hanno poche barre
dietro».

### 2.3 · Cosa resta per dataset

- **Il registro** (H provati, conto delle prove, diario, risalite) resta per
  dataset (symbol e timeframe), come nel `68` §9.1. La chiave del registro
  diventa symbol, timeframe e confine unico.
- **Il diario si legge anche fra dataset.** La scheda e la schermata 1 dicono
  quante volte l'out-of-sample dello studio è stato guardato su questo dataset
  e quante su altri: «out-of-sample già guardato 2 volte su
  BINANCE_PERP_BTCUSDT M15». È la ragione del confine unico: lo stesso periodo
  visto altrove non è più nuovo. Non blocca niente.
- **Il conto delle prove** resta per dataset, come oggi. Contare insieme le
  prove fatte su dataset diversi (cercare su più monete e scegliere la
  migliore) è una domanda di metodo più larga, che questo lavoro non tocca. La
  segnalo in §13.

### 2.4 · Il parametro che forza il confine vecchio

`prepara(..., confine="studio")` è il predefinito: il confine unico. I valori
possibili sono tre:

| `confine=` | cosa fa | scrive nello studio? |
|---|---|---|
| `"studio"` | il confine unico (lo crea se lo studio non c'è) | sì |
| `"80%"` | **la regola di oggi**: l'80% delle barre di questo dataset, calcolato a ogni giro | **no**: il registro resta in memoria, come oggi |
| una data, es. `"2025-09-29 00:00"` | quel confine, per un collaudo | no |

Con un valore diverso da `"studio"`, la schermata 1 mostra in arancione:
«Confine di collaudo (regola vecchia, 80% di questo dataset): non è il confine
dello studio. Niente di quello che fai qui entra nel diario o nel conto dello
studio.»

Serve alle prove d'identità su BYBIT_SPOT_ETHUSDT (§9) e ai test vecchi. Nel
notebook di ricerca è la variabile `CONFINE = "studio"` della cella 20.

---

## 3 · I file dello studio

### 3.1 · La cartella

```
<DATI_DIR>/studio/
    confine.json                              il confine unico (si scrive solo all'apertura e al reset)
    BINANCE_PERP_BTCUSDT_M15/
        impronta.json                         l'impronta dell'in-sample (si scrive una volta)
        giornale_pc.jsonl                     le voci scritte dal PC, solo in aggiunta
        giornale_colab.jsonl                  le voci scritte da Colab, solo in aggiunta
    BYBIT_SPOT_ETHUSDT_M15/
        ...
    archivio/
        2026-10-25_fino_2025-06-10/           lo studio intero, com'era al reset
```

- La cartella sta accanto ai dati. `dati/` è nel `.gitignore`, quindi lo studio
  non va su GitHub.
- I file sono testo leggibile con un editor qualunque.
- `confine.json` e `impronta.json` si scrivono in modo sicuro: prima un file
  temporaneo, poi lo si mette al posto del vecchio, così un'interruzione a metà
  non lascia mai un file rotto.

### 3.2 · Cosa contengono

**`confine.json`**

```json
{
  "versione": 1,
  "id": "2026-10-25T10:12:00Z",
  "confine": "2025-06-10T01:00:00+00:00",
  "aperto_il": "2026-10-25T10:12:00+00:00",
  "aperto_su": "BINANCE_PERP_BTCUSDT M15",
  "regola": "80% delle 238.326 barre di BINANCE_PERP_BTCUSDT M15 presenti il 25/10/2026",
  "contaminato": null,
  "studio_precedente": null
}
```

`id` è il nome dello studio: ogni voce dei giornali lo porta con sé (§4.3).

**`impronta.json`** (una per dataset)

```json
{"studio": "2026-10-25T10:12:00Z", "barre": 190660,
 "prima": "2020-01-02T00:00:00+00:00", "ultima": "2025-06-10T00:45:00+00:00",
 "codice": "sha256:…"}
```

L'impronta si scrive la prima volta che il dataset entra nello studio. A ogni
avvio la schermata 1 la ricalcola; se non torna (CSV sostituito, scaricato da
zero, corretto dall'exchange), **si ferma** e dice cosa è diverso: quante
barre, quali date, codice diverso. Le due strade d'uscita sono rimettere il
CSV di prima oppure il reset. Il contenuto dipende solo dal CSV, quindi se PC e
Colab la scrivessero insieme, scriverebbero la stessa cosa.

**`giornale_<macchina>.jsonl`**: una riga per voce, solo in aggiunta.

```
{"studio": "2026-10-25T10:12:00Z", "quando": "2026-10-25T10:12:05Z", "voce": "orizzonte", "H": 41}
{"studio": "...", "quando": "...", "voce": "prova", "dove": "uscite", "chiave": [...], "n": 87}
{"studio": "...", "quando": "...", "voce": "oos", "oos_fino_al": "2026-10-25T09:45:00+00:00", "scelte": {...}}
{"studio": "...", "quando": "...", "voce": "risalita", "cosa": "cella", "da": ..., "a": ...}
```

Quattro tipi di voce coprono tutto lo `StoriaDataset` del `68` §9.1:

| voce | cosa registra |
|---|---|
| `orizzonte` | un H usato (da qui H provati e H corrente) |
| `prova` | una voce del conto delle prove: trigger, uscite, filtri, combinazioni o fasce, con la sua chiave e il numero |
| `oos` | un'apertura dell'out-of-sample, con le scelte e `oos_fino_al`, l'ultima barra out-of-sample di quel momento (serve al reset) |
| `risalita` | una scelta rifatta |

Il conto delle prove ha chiavi composte (per esempio le uscite per chiave), che
JSON non accetta come chiavi: nel giornale ogni chiave è un elenco, e alla
lettura si ricostruisce identica.

### 3.3 · Quando si scrive

- Si aggiunge una riga al giornale solo quando cambia qualcosa: un H nuovo,
  una voce del conto diversa da quella già scritta, un'apertura
  dell'out-of-sample, una risalita.
- Rieseguire una schermata senza cambiare niente non aggiunge righe.
- `confine.json` si scrive solo all'apertura dello studio e al reset;
  `impronta.json` una volta per dataset.

---

## 4 · PC e Colab senza conflitti

### 4.1 · Google Drive per desktop (raccomandato)

Google Drive per desktop è il programma gratuito di Google che fa comparire «Il
mio Drive» come una cartella del PC e la tiene sincronizzata. Si installa una
volta. Poi l'Avvio, in locale, cerca da solo
`…/Il mio Drive/Trading-System-Creator_V4/dati` (anche `My Drive`, su
qualunque disco) e, se la trova, usa quella come cartella dei dati al posto di
`dati/`.

PC e Colab leggono e scrivono così gli stessi CSV, lo stesso funding e lo
stesso studio. Non c'è niente da caricare a mano, e il diario scritto su Colab
torna sul PC.

Al primo avvio con la cartella trovata, se `dati/` ha CSV più recenti di quelli
su Drive, l'Avvio li elenca e li copia solo se lo si conferma nel form, con il
campo `copia_su_drive`, spento di predefinito.

Oggi sul PC Drive per desktop non c'è (controllato il 25/10: dischi C, D ed E,
nessun processo di Google Drive). Finché non c'è, il tool lavora in `dati/` e
la schermata 1 elenca i file da caricare su Drive per Colab. È il ripiego, non
la strada consigliata.

### 4.2 · Il problema

Drive per desktop sincronizza dei file, non delle righe. Se il PC e Colab
modificano **lo stesso file** a pochi minuti di distanza, Drive non unisce le
modifiche: ne tiene una e salva l'altra come copia a parte, per esempio
`giornale (1).jsonl`, che il tool non leggerebbe. Una voce di diario si
perderebbe in silenzio, cioè proprio un'apertura dell'out-of-sample non
contata.

### 4.3 · La soluzione: un giornale per macchina, solo in aggiunta

1. **Ogni macchina scrive solo il suo file.** Il PC scrive `giornale_pc.jsonl`,
   Colab scrive `giornale_colab.jsonl`. Due macchine non scrivono mai lo stesso
   file, quindi Drive non ha niente da riconciliare. Il nome della macchina lo
   decide l'Avvio: `colab` su Colab, `pc` in locale. Un secondo PC può usare
   `pc2`, con il campo `nome_macchina` del form.
2. **Solo in aggiunta.** Una riga scritta non si cambia e non si cancella. Il
   registro (H provati, conto, diario, risalite) si ricostruisce a ogni avvio
   **leggendo tutti i giornali** del dataset e rimettendo le voci in ordine di
   tempo. Due aperture dell'out-of-sample fatte una sul PC e una su Colab sono
   due righe in due file: tutte e due contano.
3. **Le regole di unione** sono fisse e danno lo stesso risultato in qualunque
   ordine arrivino i file:
   - H provati è l'unione, in ordine di tempo, e H corrente è l'ultimo;
   - per ogni chiave del conto vale la riga più recente;
   - diario e risalite sono tutte le righe, in ordine di tempo.
4. **I file scritti una volta sola** (`confine.json` e `impronta.json`) si
   scrivono così:
   - il confine si apre e si resetta **solo sul PC**, che è dove arrivano i
     dati. Colab lo legge e basta: se manca, si ferma (§12.1);
   - l'impronta dipende solo dal CSV, quindi due scritture uguali non sono un
     conflitto.
5. **Ogni riga porta l'`id` dello studio.** Dopo un reset, una sessione di
   Colab rimasta aperta con lo studio vecchio potrebbe scrivere ancora. Le sue
   righe hanno l'`id` vecchio: non entrano nello studio nuovo e la schermata 1
   lo dice («3 voci scritte da Colab per lo studio precedente: messe in
   archivio»).
6. **Le copie di conflitto** di Drive (`… (1).jsonl`) non dovrebbero esistere.
   Se la schermata 1 ne trova una, la legge come un giornale in più e lo
   segnala. Così nessuna voce si perde, nemmeno nel caso imprevisto.

**Il limite che resta.** La sincronizzazione non è istantanea, ci vogliono
secondi o qualche minuto. Se apri l'out-of-sample su Colab e subito dopo sul PC,
la seconda scheda potrebbe non sapere ancora della prima. La voce però non si
perde: compare alla schermata successiva. Lo scrive il riquadro dell'Avvio:
«meglio non lavorare sullo stesso dataset su PC e Colab nello stesso momento».

---

## 5 · Il reset

### 5.1 · Come si chiede (decisione di Mattia del 25/10)

È il campo `ricalcola_confine` della schermata 1, vuoto di predefinito. Il
testo accanto dice: «Per ricalcolare il confine da zero scrivi qui la data di
oggi (gg/mm/aaaa). Il confine vale per tutto lo studio: lo studio intero va in
archivio e se ne apre uno nuovo.»

Una casella sì/no lasciata accesa rifarebbe il reset a ogni giro. Con la data:

- la data di oggi, con un reset non ancora fatto oggi: reset;
- la stessa data rieseguita: nessun reset nuovo («reset già fatto oggi alle 10:12»);
- una data diversa da oggi (il campo dimenticato pieno): nessun reset, con
  l'avviso «nel campo c'è il 25/10/2026, non la data di oggi: svuotalo».

Il reset si fa **solo sul PC** (§4.3 punto 4). Su Colab il campo è ignorato e lo
si dice.

### 5.2 · Cosa fa

1. Sposta l'intera cartella `studio/` (confine, impronte, giornali di tutti i
   dataset) in `studio/archivio/<oggi>_fino_<confine vecchio>/`. Non si cancella
   niente.
2. Calcola il confine nuovo all'**80% delle barre di adesso del dataset su cui
   lo si chiede**, con la stessa regola dell'apertura.
3. Apre lo studio nuovo, con un `id` nuovo. In `studio_precedente` scrive
   confine, data di apertura e, per ogni dataset, H provati, quante volte era
   stato guardato l'out-of-sample e quando.
4. **La contaminazione si misura su tutto lo studio.** Si prende il più tardo
   `oos_fino_al` dei diari di **tutti** i dataset. Il periodo fra il confine
   vecchio e il più piccolo fra quella data e il confine nuovo è out-of-sample
   già guardato che ora è nell'in-sample. `confine.json` lo scrive in
   `contaminato`, con:
   - il periodo, dal … al …;
   - su quali dataset era stato guardato e quante volte.

   Per la stessa ragione del confine unico, vale per ogni dataset dello studio
   nuovo, anche per quelli su cui quel periodo non era mai stato guardato.
5. Se il confine nuovo coincide con il vecchio (nessuna barra nuova), non fa
   niente e lo dice.

### 5.3 · Cosa mostra

Una tabella «Studio vecchio → studio nuovo» con:
- il confine, vecchio e nuovo;
- per ogni dataset: barre in-sample e out-of-sample, H provati e quante volte è
  stato guardato l'out-of-sample.

Se c'è contaminazione, il riquadro arancione (numeri d'esempio):

> Il nuovo in-sample contiene il periodo dal 10/06/2025 al 18/03/2026, che
> avevi già guardato come out-of-sample: 3 volte su BINANCE_PERP_BTCUSDT M15, 1
> su BYBIT_SPOT_ETHUSDT M15. Le crypto si muovono insieme: su quel periodo i
> risultati li conosci già, su ogni dataset. Costruire sopra di esso non è più
> una prova pulita. Questo avviso resta su questo studio.

La stessa frase, più corta, compare in ogni schermata 1 e sopra ogni scheda
dello studio nuovo, su ogni dataset. Non blocca niente. Il conto delle prove
riparte da zero (vincolo 5 del `69`): la storia dello studio vecchio sta in
archivio e nell'avviso, non nei numeri.

---

## 6 · Funding e spot

### 6.1 · Il funding si aggiorna con le candele

Sì. Sui perpetual, con l'interruttore acceso, si aggiorna anche
`<SYMBOL>_FUNDING.csv`, nello stesso giro e con la stessa logica incrementale
di oggi (`aggiorna_funding` dello script). Il funding è uno per symbol e vale
per ogni timeframe. Il confronto con le barre, che oggi lo script fa sempre su
M15, si fa sul timeframe scelto.

### 6.2 · Se il funding arriva fino a una data diversa

| caso | cosa succede |
|---|---|
| funding più avanti delle candele | nessun problema: i tassi dopo l'ultima barra non si usano |
| funding più indietro delle candele (download non riuscito, o l'exchange lo pubblica in ritardo) | oggi `carica_funding` si ferma. La proposta invece **taglia le barre di questo giro** all'ultima barra coperta dal funding (`copertura_funding`, stessa regola di oggi) e lo dice: «il funding arriva fino al 25/10 08:00: lavori sulle barre fino alle 15:45; le altre 31 barre restano nel file e si usano quando arriva il funding». Il CSV non si tocca, e le barre tagliate sono sempre out-of-sample, perché il confine è più indietro |
| il funding non copre l'**in-sample** | la schermata si ferma, come oggi |

È una modifica non additiva di `prepara` (oggi si ferma, domani taglia), e si
dichiara. Con i file di oggi il funding copre le barre, quindi i numeri non
cambiano.

### 6.3 · Lo spot del perpetual

Lo spot della stessa coppia dà la basis all'atlante (`aggancia_spot`). Se si
aggiornasse il perpetual e non lo spot, le barre nuove resterebbero senza
basis. Per questo, con l'interruttore acceso, si aggiorna anche lo spot dello
stesso timeframe. Se manca del tutto, il primo download completo lo scarica
insieme al perpetual, e il tempo si raddoppia (§10).

### 6.4 · Solo barre chiuse, stessi controlli

`scarica_storico` scarta già la barra in corso. Dopo l'aggiornamento girano
sulle barre nuove gli stessi controlli dello script (`controlla_storico`):
- doppie;
- fuori griglia;
- buchi;
- OHLC incoerenti;
- volume zero;
- quarantena.

Il riepilogo è quello del §1.2. Come oggi, le barre che non passano un
controllo si segnalano e non si tolgono. Le barre fuori griglia fermano già
`carica_storico`.

---

## 7 · Cosa cambia nel codice e cosa resta

### 7.1 · Nuovo (additivo)

- **`engine/aggiorna_dati.py`**
  - `aggiorna_storico(symbol, timeframe, cartella, ex=None)` e
    `aggiorna_funding(symbol, cartella, timeframe, ex=None)`, spostate da
    `scarica_dati_crypto.py` con la logica di oggi, più il salvataggio ogni 100
    blocchi.
  - `aggiorna_per_lab(symbol, timeframe, cartella)`: aggiorna candele, spot del
    perpetual e funding, e ritorna il riepilogo del §1.2. Un errore di rete non
    ferma niente (§1.3).
  - Usa solo `load_markets`, `fetch_ohlcv` e `fetch_funding_rate_history`.
- **`engine/studio.py`**
  - `cartella_studio`;
  - `leggi_confine` e `apri_confine` (solo sul PC);
  - `impronta(df_is)`;
  - `aggiungi_voce(dataset, macchina, voce)`, solo in aggiunta;
  - `ricostruisci(dataset)`, che legge tutti i giornali, li unisce con le
    regole del §4.3 e ritorna lo `StoriaDataset`;
  - `diario_altrove(dataset)`, le aperture dell'out-of-sample sugli altri
    dataset;
  - `dividi(df, confine)`, che ritorna `df_is, df_oos` con le barre che si
    chiudono entro il confine;
  - `reset(oggi, dataset, df)` e `archivia`.
- **`engine/splitting.py`**: `split_al_confine(df, confine)`, accanto a
  `split_is_oos`, che resta.
- **`engine/registro_dataset.py`**: `da_voci(voci) -> StoriaDataset`;
  `annota_oos` accetta anche `oos_fino_al`.
- **`test_dati_confine.py`**, la suite nuova (§8), e la sua riga in `DURATE` di
  `suite_rapida.py`.

### 7.2 · Modificato (dichiarato)

- **`vetrina.prepara`**: due parametri nuovi, `aggiorna=False` e
  `ricalcola_confine=""`, più `confine="studio"` (§2.4). Con `"studio"` il
  confine viene dal file (o lo crea sul PC) e la divisione è al confine. Con
  `"80%"` tutto come oggi: 80% a ogni giro e niente file.
  `quota_in_sample` resta, e conta solo all'apertura dello studio e al reset.
- **`vetrina.registro_orizzonte`, `segna_oos`, `_diario_oos`, le chiamate ad
  `annota_risalita` e il conto delle prove**: con il confine dello studio, ogni
  cambio aggiunge la riga al giornale della macchina. `_nota_dataset` ha i
  testi nuovi (§1.2) e conta le aperture su altri dataset (§2.3).
- **`prepara` e il funding**: il taglio del §6.2 al posto dello stop, solo
  sull'out-of-sample.
- **`scarica_dati_crypto.py`**: importa le funzioni da `engine/aggiorna_dati.py`
  invece di averle dentro. Comandi e stampe restano gli stessi. Lo script usa
  la stessa cartella dei dati che trova l'Avvio (§4.1).
- **Lab**: l'Avvio (interruttore, cartella di Drive, nome della macchina, testo)
  e la schermata 1 (campo del reset, testo), nel markdown e nel form.
- **Notebook di ricerca** (domanda 4, §12.4):
  - cella 4: la cartella di Drive e il nome della macchina, come l'Avvio;
  - cella 11: `AGGIORNA_DATI` e l'aggiornamento prima di `carica_storico`;
  - cella 20: lo studio al posto di `split_is_oos`, con `CONFINE = "studio"`
    e `RICALCOLA_CONFINE = ""`;
  - cella 24: `registro_orizzonte` legge e scrive il giornale.

### 7.3 · Cosa resta com'è

Il motore, la rosa, l'atlante, le uscite, i filtri, la scheda, il money
management, lo stress test, `split_is_oos`, `carica_storico`, `leggi_csv`,
`scarica_storico`, i costi, il lato broker (sospeso) e i symbol in elenco
(domanda 5).

---

## 8 · Collaudo (test a risultato noto, senza rete)

Tutto in `test_dati_confine.py`, con un exchange finto (come i test di
`exchange.py`) e cartelle temporanee:

1. **Incrementale:** un CSV di 1.000 barre e un exchange finto con 1.300 →
   il CSV ne ha 1.300, le prime 1.000 identiche al bit, nessuna doppia; una
   seconda chiamata subito dopo non aggiunge niente.
2. **Solo barre chiuse:** l'exchange finto ha anche la barra in corso → non entra.
3. **Ripresa:** il download completo si interrompe (eccezione) dopo 250
   blocchi → il CSV ha le barre dei primi 200 salvati; il giro dopo
   completa, e il risultato è identico a un download senza interruzioni.
4. **Rete giù:** l'exchange finto alza un errore → avviso, CSV invariato, la
   funzione ritorna «non aggiornato»; senza CSV, si ferma.
5. **Confine fisso:** studio aperto su 1.000 barre (confine alla fine della barra
   800), poi +300 barre → `df_is` identico al bit, `df_oos` = 500 barre.
6. **Confine = posizione:** sui CSV veri di BTC perp ed ETH spot, il confine
   dell'80% di ciascuno dà gli stessi due DataFrame di `split_is_oos(df, 0.8)`.
7. **Confine unico fra timeframe:** confine alle 01:00 → in M15 l'ultima barra
   in-sample è quella delle 00:45, in H1 quella delle 00:00, in H4 quella delle
   20:00 del giorno prima; nessuna barra in-sample si chiude dopo il confine.
8. **Confine unico fra dataset:** lo studio aperto sul dataset A (80%), poi un
   dataset B che parte più tardi → B usa la stessa data, e la quota del B è
   quella calcolata a mano; sotto il 50% compare l'avviso.
9. **Impronta:** si cambia un Close dell'in-sample → si ferma; si cambia un
   Close dell'out-of-sample → nessun effetto.
10. **CSV più corto del confine** (per esempio la copia vecchia su Drive): si ferma.
11. **Riavvio simulato:** si scrivono H provati [41, 25], un conto delle prove
    con chiavi composte, due voci di diario e una risalita; si svuota il
    registro (`azzera`) e si ricostruisce dai giornali → tutto identico,
    chiavi composte comprese. La seconda apertura dell'out-of-sample dopo la
    rilettura riconosce «stesse scelte» (le liste del JSON confrontate con le
    tuple di prima).
12. **Due macchine:** voci alternate scritte da `pc` e `colab` sullo stesso
    dataset → la ricostruzione ha tutte le voci; leggere i due file in ordine
    inverso dà lo stesso registro; nessuna scrittura tocca il file dell'altra
    macchina.
13. **Copia di conflitto:** un `giornale_pc (1).jsonl` in più → letto e segnalato.
14. **`id` vecchio:** dopo un reset, righe con l'`id` dello studio precedente
    → non entrano nello studio nuovo e si segnalano.
15. **Diario fra dataset:** due aperture su A, una su B → la schermata di B
    dice «1 volta su questo dataset, 2 su A».
16. **Reset:**
    - con la data di oggi → cartella archiviata intera, confine nuovo = 80%
      delle barre di adesso, conto a zero, `studio_precedente` pieno;
    - rieseguito con la stessa data → nessun reset nuovo;
    - con un'altra data → nessun reset e avviso;
    - senza barre nuove → nessun reset;
    - su Colab → ignorato.
17. **Contaminazione su tutto lo studio:** diario di A con `oos_fino_al` alla
    barra 1.100, nessuna apertura su B, reset a 1.300 barre (confine nuovo alla
    1.040) → `contaminato` dalla fine della barra 800 alla fine della 1.040, e
    l'avviso compare anche su B. Senza diari → `contaminato` vuoto.
18. **Colab senza studio:** si ferma con il messaggio del §12.1.
19. **`confine="80%"` e una data:** stessi numeri della regola di oggi (o del
    confine dato); nessun file scritto.
20. **Funding più indietro delle candele:** le barre di questo giro si tagliano
    all'ultima coperta; se il funding non copre l'in-sample → si ferma.
21. **Scrittura sicura:** un errore a metà scrittura di `confine.json` lascia
    il file di prima intatto.
22. **Sola lettura verso l'exchange:** l'exchange finto registra le funzioni
    chiamate → solo `fetch_ohlcv` e `fetch_funding_rate_history` (più
    `load_markets` all'apertura).

I test esistenti restano com'erano. `test_vetrina.py` e `test_riordino_lab.py`
chiamano `prepara` senza studio: dove il test parla del registro gli passo una
cartella temporanea, così il registro su file viene provato anche lì;
altrove `confine="80%"`.

---

## 9 · Identità (vincolo 2 del `69`)

Si lavora come nel `68` §11.2: degli script eseguono i notebook cella per
cella, main contro ramo, e confrontano le variabili. I CSV di oggi si copiano
in una cartella temporanea, con lo studio vuoto e l'interruttore spento.

1. **BINANCE_PERP_BTCUSDT, confine dello studio.** È il primo dataset aperto,
   quindi il confine unico è il suo 80%. Lab (tutti gli oggetti delle schermate
   e il conto delle prove) e notebook di ricerca (tutte le variabili) devono
   essere identici a main.
2. **Secondo giro, sulla stessa cartella.** Lo studio ora c'è e si rilegge dal
   file, e i risultati devono essere di nuovo identici.
3. **BYBIT_SPOT_ETHUSDT con `confine="80%"`**, giro completo dei due notebook:
   identici a main. È il parametro che forza il confine vecchio.
4. **BYBIT_SPOT_ETHUSDT con il confine dello studio** (aperto da BTC perp, al
   10/06/2025 01:00), fuori dal confronto con main. Il confine passa dal
   28/09/2025 al 10/06/2025, e l'in-sample dall'80% al 74,2% (137.412 barre
   invece di 148.063). I numeri cambiano: li riporto nel resoconto come
   collaudo, non come verdetto.
5. **Barre nuove**, fuori dal confronto con main:
   - al CSV di BTC si aggiungono le barre dal 19/10 a oggi, scaricate davvero
     con l'interruttore acceso;
   - l'in-sample resta identico al bit, e i risultati in-sample (rosa, uscite,
     filtri) sono identici al giro 1;
   - cambia solo l'out-of-sample, più lungo.

---

## 10 · Tempi

Stime dagli orari dei file scaricati il 19/10 (M15 dal 2/1/2020, circa 238.000
barre, 1.000 per richiesta), da misurare durante il lavoro e scrivere nel resoconto.

| timeframe | barre dal 2020 | primo download, Binance | primo download, Bybit |
|---|---|---|---|
| M5 | ~715.000 | ~5 minuti | ~6–15 minuti |
| M15 | ~238.000 | ~1,5–2 minuti | ~2–5 minuti |
| M30 | ~119.000 | ~1 minuto | ~1–3 minuti |
| H1 | ~60.000 | ~30 secondi | ~1 minuto |
| H4 | ~15.000 | pochi secondi | pochi secondi |

- **Perpetual:** al primo download il tempo si raddoppia, perché c'è anche lo
  spot. Il funding completo aggiunge circa un minuto, ma solo la prima volta,
  perché vale per tutti i timeframe.
- **Download incrementale:** una richiesta ogni 1.000 barre nuove; una settimana
  di M15 sono 672 barre, cioè una richiesta. In pratica 2–5 secondi per
  candele, spot e funding insieme.
- **Schermata 1 senza aggiornamento:** come oggi. Leggere confine e giornali
  richiede meno di un decimo di secondo; calcolare l'impronta su 190.000 barre
  circa 0,1 secondi.
- **La suite nuova:** sotto il minuto (nessuna rete).

---

## 11 · Rischi

- **Lo studio aperto sul dataset sbagliato.** Il confine unico lo fissa il primo
  dataset aperto: un primo avvio su una moneta quotata da poco darebbe un
  confine più tardo per tutti. Il riquadro di apertura (§2.1) lo dice e
  raccomanda BTC perp M15. Se serve, un reset nello stesso giorno rimedia,
  perché non c'è ancora niente di guardato.
- **Senza Drive per desktop** ci sono due copie dei dati, sul PC e su Drive, e il
  giornale di Colab non torna sul PC. È la ragione della raccomandazione del §4.1.
- **Correzioni dell'exchange** sulle barre vecchie: un download da zero può
  dare barre diverse. L'impronta se ne accorge e si ferma, invece di cambiare
  l'in-sample in silenzio.
- **Il campo del reset dimenticato** è coperto dalla data (§5.1).
- **Il ritardo della sincronizzazione** è il limite del §4.3: una voce può
  arrivare dopo, ma non si perde.
- **ccxt in locale:** se manca o cambia versione, con l'interruttore acceso la
  schermata si ferma e dà il comando per installare la versione bloccata
  (4.5.78).

---

## 12 · Le domande del `69` §5 (risposte; decide Mattia)

### 12.1 · Colab senza lo studio
**Proposta: si ferma.** Il messaggio dice: «Su Drive non c'è lo studio
(`studio/confine.json`). Il confine dell'in-sample sta lì: senza, Colab
calcolerebbe un confine suo, diverso da quello del PC. Apri prima lo studio
sul PC (schermata 1); con Drive per desktop arriva qui da solo, altrimenti
carica la cartella `dati/studio/` in `Il mio Drive/Trading-System-Creator_V4/dati/`.»
Calcolare l'80% con un avviso creerebbe due studi con due confini, cioè proprio
il confine che si muove da solo. Con lo studio aperto sul PC, un dataset nuovo
può invece entrare nello studio anche da Colab, perché il confine c'è già.

### 12.2 · Più studi
**Proposta: uno studio attivo alla volta**, con un confine solo per tutto (decisione di Mattia
del 25/10). Più studi con un nome renderebbero il confine di nuovo una scelta,
cioè una prova in più non contata. Il reset archivia lo studio intero, e
l'archivio resta leggibile.

### 12.3 · Una soglia per suggerire il reset
**Proposta: sì, solo un avviso.** Quando l'out-of-sample supera il **30%**
delle barre del dataset aperto (all'inizio, su BTC perp, è il 20%), la
schermata 1 scrive: «L'out-of-sample è ora il 31% dei dati di questo dataset:
se vuoi ricalcolare il confine, vedi il campo ricalcola_confine. Non è
obbligatorio.»
Su BTC perp, con il confine di oggi, l'avviso compare verso ottobre 2027. Sui
dataset di Bybit, che hanno meno storia prima del confine, compare prima.

### 12.4 · Il notebook di ricerca
**Proposta: stesso studio e stessi giornali del Lab.** È lo stesso dataset: un
out-of-sample guardato nella ricerca è guardato anche per il Lab, e il conto
delle prove è uno solo. Le voci del conto sono già le stesse nei due notebook
(`trigger`, `uscite`, `filtri`, `combinazioni`).
Effetto da sapere: se il Lab lavora con H = 41 e la ricerca con H = 25 sullo
stesso dataset, passare dall'uno all'altro segnala ogni volta il cambio di H
(«già provato», nessuna prova in più). È corretto: sono due orizzonti provati
sugli stessi dati.

### 12.5 · I symbol in elenco
**Proposta: restano gli attuali in questo lavoro.** Il codice nuovo non elenca
monete: lavora su qualunque symbol di `SIMBOLI_EXCHANGE`. Aggiungere le monete
della lista del 13/10 resta il lavoro di sempre: una riga in
`SIMBOLI_EXCHANGE`, `LOTTI_EXCHANGE` e `LEVA_EXCHANGE` con i valori letti
dall'exchange, più la voce nel form del Lab, in un ramo a parte quando Mattia
lo chiede. Con il confine unico, una moneta nuova entra nello studio con la
stessa data, e il primo download completo lo fa il Lab.

---

## 13 · Fuori incarico (solo proposte, nessun codice)

- **Il conto delle prove fra dataset.** Il confine unico rende visibile che
  l'out-of-sample è uno solo per tutte le crypto. Lo stesso vale, in parte, per
  le prove: provare la stessa idea su BTC, ETH e SOL e tenere la moneta dove
  va meglio è una scelta fra prove. Oggi il conto è per dataset. Contare anche
  i dataset provati con la stessa idea è una domanda di metodo per Mattia, da
  fare in un lavoro a parte se la vuole.
- **L'out-of-sample «fresco».** Con le barre che arrivano, l'out-of-sample
  contiene un tratto già guardato e uno mai visto (le barre arrivate dopo
  l'ultima apertura del diario, su qualunque dataset). La scheda potrebbe
  mostrare anche i numeri del solo tratto mai visto, con quante barre ci sono.

---

## 14 · Decisioni di Mattia (25/10/2026)

La proposta è approvata, con le indicazioni sulla bozza riportate in testa:
- Drive per desktop raccomandato, con un giornale per macchina, solo in aggiunta;
- reset con la data nel campo;
- confine unico per tutto lo studio, con `confine="80%"` per le prove d'identità.

**Domande del §12**

| | decisione |
|---|---|
| 12.1 · Colab senza lo studio | **si ferma**, con il messaggio del §12.1 |
| 12.2 · Più studi | **uno studio attivo alla volta** |
| 12.3 · Soglia per suggerire il reset | **avviso al 30%** di out-of-sample, mai automatico |
| 12.4 · Notebook di ricerca | **Lab e ricerca nello stesso studio**, con gli stessi giornali |
| 12.5 · Symbol in elenco | **le monete attuali**; le altre in un ramo a parte |

**Fuori incarico (§13)**

| proposta | decisione |
|---|---|
| L'out-of-sample «fresco» | **lavoro piccolo dopo questo**; fatto il 25/10: nella scheda e nella Sessione 4 della ricerca, i trade a cavallo della data restano fuori (decisione di Mattia) |
| Il conto delle prove fra dataset | **si decide nel lavoro dei testimoni**, più avanti |

**Riquadro dell'Avvio (§1.1)**

Una riga in più: con Drive per desktop si usa la modalità streaming e si rende
disponibile offline solo la cartella `Trading-System-Creator_V4`, mai il
mirroring di tutto il Drive.

**Consegna del codice**

Due Pull request, come per il riordino (`68`).

| PR | contenuto | prove |
|---|---|---|
| **A · Engine e test** | `engine/aggiorna_dati.py`; `engine/studio.py`; `split_al_confine` in `engine/splitting.py`; `da_voci` e `oos_fino_al` in `engine/registro_dataset.py`; `test_dati_confine.py` con la sua riga in `suite_rapida.py`; `scarica_dati_crypto.py` che importa le funzioni spostate | `test_dati_confine.py` (§8) |
| **B · Il resto** (dopo il merge di A) | `vetrina.prepara` e le funzioni del registro; l'Avvio e la schermata 1 del Lab crypto; le celle 4, 11, 20 e 24 del notebook di ricerca | le prove d'identità del §9 |

Prima di ognuna, la suite completa.


---

## 15 · Resoconto (*resoconto*, 25/10/2026)

**Consegna.**
- **PR #69 (A):** `engine/aggiorna_dati.py`, `engine/studio.py`, `split_al_confine`,
  `da_voci`, `test_dati_confine.py`; `scarica_dati_crypto.py` usa le funzioni spostate.
- **PR successiva (B):** `prepara` con lo studio, Lab crypto, notebook di ricerca,
  `docs/00`. In apertura c'è la correzione di Mattia sul reset all'indietro.

### 15.1 · Scelte fatte nel codice, da sapere

1. **Il reset all'indietro** (correzione di Mattia del 25/10). Un confine nuovo più
   indietro del vecchio è ammesso solo se lo studio vecchio non ha voci «prova»,
   «oos» o «risalita». La voce «orizzonte» non conta: la schermata 1 la scrive
   appena si apre lo studio, prima di qualunque misura, e con lei il rimedio del
   §11 sarebbe sempre bloccato. Altrimenti il reset si rifiuta, con un messaggio
   che spiega perché. Test D22, D22b, D22c.
2. **L'80% all'apertura si calcola sulle barre che si dividono davvero**, cioè dopo
   gli indicatori, che scartano le prime barre di riscaldamento: sono le stesse
   che dividevano prima il Lab e la ricerca. Così il confine è esattamente quello
   di prima.
   - Su BINANCE_PERP_BTCUSDT M15 è il **10/06/2025 alle 16:00 UTC**, non alle 01:00
     come nel §2. Il §2 lo aveva calcolato sulle barre grezze del CSV.
   - L'impronta invece resta calcolata sulle barre del CSV (`entra(...,
     df_impronta=)`).
3. **`prepara` senza `confine` fa come prima** (80% a ogni giro, niente studio). Il
   Lab e la ricerca passano `confine="studio"` in modo esplicito. Col predefinito
   «studio», i test e gli script che chiamano `prepara` su `dati/` avrebbero
   aperto lo studio vero.
4. **La ricerca usa lo studio solo sui symbol da exchange.** Sul broker (sospeso)
   resta l'80%: il notebook parte con `symbol = "EURUSD"`, e lo studio si sarebbe
   aperto su un symbol del broker.
5. **Il taglio al funding** (§6.2) si fa al confine dello studio già aperto. Al
   primo avvio, quando il confine non c'è ancora, un funding meno avanti delle
   candele ferma la schermata come prima (test E9a).
6. **I CSV veri si rileggono identici al bit.** `read_csv` non rilegge al bit i
   numeri con molti decimali; i prezzi dei CSV veri hanno pochi decimali e si
   rileggono identici (test B6c). Su questo poggia l'impronta.

### 15.2 · Identità (§9)

Main contro ramo, CSV del 19/10 in cartelle temporanee, interruttore spento.

| giro | risultato |
|---|---|
| Lab, BTC perp, confine dello studio (si apre) | oggetti 10/10 identici, conto delle prove identico |
| Lab, BTC perp, secondo giro (studio riletto dal file) | oggetti 10/10 identici; il diario ha 2 aperture (la prima letta dal giornale) |
| Lab, ETH spot Bybit, `confine="80%"` | oggetti 10/10 identici, conto identico |
| Ricerca, BTC perp, confine dello studio | variabili 93/93 identiche |
| Ricerca, ETH spot, `confine="80%"` | variabili 85/85 identiche |

Le tabelle del Lab che cambiano sono quelle attese:
- `riepilogo`: la riga «Studio» e il testo dell'in-sample e dell'out-of-sample;
  le barre sono le stesse, 190.420 e 47.606;
- `diario_oos`: l'ora e il campo nuovo `oos_fino_al`, scelte identiche;
- `lente`: apre un trade a caso, come nel `68`.

**ETH spot con il confine dello studio** (aperto su BTC perp), collaudo e non verdetto:
- in-sample da 147.823 a 137.172 barre (74,2%) e out-of-sample da 36.956 a 47.607;
- trigger misurati da 33 a 32 e celle da 186 a 182;
- la rosa resta E21_BELT_HOLD;
- trade da 2.100 a 1.942 nell'in-sample e da 548 a 706 nell'out-of-sample.

**Barre nuove, scaricate davvero** (sola lettura) sul BTC del giro 1, il 25/10:
- candele +593, spot +594, funding +14, controlli puliti;
- il confine non si è mosso e l'out-of-sample è passato da 708 a 717 trade;
- l'in-sample però **non è identico al bit** (§15.3).

### 15.3 · Un punto aperto: lo spread si converte con la mediana di tutto lo storico

Sui symbol da exchange lo spread di un passo diventa una frazione del prezzo con
il **prezzo mediano di tutto lo storico** (`exchange.costi_exchange`, chiamata da
`prepara` sul `df` intero, out-of-sample compreso). Era così anche prima di questo
lavoro.

Con il confine fisso lo si vede: quando arrivano barre nuove, la mediana cambia di
un soffio e con lei il costo di ogni trade in-sample. Sul BTC del 25/10:
- lo spread passa da 0,0226 a 0,0225 bp per trade;
- il totale in-sample passa da −78.508 a −78.507 pips;
- il funding in-sample resta identico.

Sono numeri che non spostano niente, ma un dato dell'out-of-sample entra nel costo
dei trade in-sample. Tre strade, decide Mattia:
- **A · mediana dell'in-sample** (fino al confine). Nessun dato dell'out-of-sample
  nei costi, e l'in-sample resta identico con le barre nuove. Rispetto a main
  cambia lo spread di tutti i trade, di qualche millesimo di bp: è una modifica di
  calcolo dichiarata.
- **B · mediana congelata nello studio** al primo ingresso del dataset. Identità con
  main e in-sample fermo, ma è un valore legato al giorno di apertura.
- **C · lasciare com'è.**

Raccomandazione: A.

**Decisione di Mattia (25/10): A**, come lavoro piccolo subito dopo la PR #70.
`costi_storico(..., df_prezzo=)`: il Lab e il notebook di ricerca passano
l'in-sample. Con le barre nuove del 25/10 l'in-sample di BTC ora è identico al bit:
uscite, filtri, trade, rosa e atlante. Rispetto a prima, sui CSV del 19/10, lo
spread di BTC passa da 0,0226 a 0,0275 bp per trade e il guadagno medio in-sample
da −3,11 a −3,15 bp. Da valutare (solo proposta): la strada D, lo spread di un
passo al prezzo d'ingresso di ogni trade.

### 15.4 · Tempi misurati

Con la rete vera, il 25/10 (parte A), su BINANCE_PERP_BTCUSDT:
- H4 completo: 10 secondi;
- M15 completo: 83 secondi;
- incrementale di 6 giorni (candele, spot e funding): 10 secondi.

Il Lab completo con l'aggiornamento acceso ha girato in 118 secondi, contro i
128–142 dei giri senza aggiornamento: la differenza sta nella variabilità fra un
giro e l'altro.

`test_dati_confine.py`: 77 test.
