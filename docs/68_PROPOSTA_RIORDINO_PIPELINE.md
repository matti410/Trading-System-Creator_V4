# 68 · Proposta: riordino della pipeline del Lab, schermate 2→4

**Data:** 25 ottobre 2026
**Stato:** PROPOSTA, **senza codice**. Risponde all'incarico `docs/67`.
**Decisioni di Mattia del 25/10/2026 al §12**, con le sue due correzioni
(cambiare H, §9.1; nota sul picco, §5.1). Il codice si scrive su un ramo a
parte, dopo il merge di questa proposta.
**Perimetro:** crypto da exchange; il Lab broker resta sospeso e non si tocca.

**Indice:** §0 In breve · §1 Il flusso nuovo · §2 Il metro unico · §3 La
casistica · §4 La scelta delle casistiche (3b) · §5 Le uscite consigliate ·
§6 Il profilo orario · §7 Dalla 4b al passo 5 · §8 Le prove su ogni schermata
· §9 Risalire l'imbuto · §10 Il notebook di ricerca · §11 Collaudo, identità,
tempi · §12 Decisioni di Mattia · §13 Orizzonti multipli (domanda 6 di `67`) ·
§14 Resoconto (*resoconto*).

---

## 0 · In breve

- **Un metro solo dalla 2 alla 4:** lo scarto del trigger dal mercato **della
  stessa ora**, in bp, con i pips accanto. È il metro che la rosa usa già.
  Curve e classifica passano a questo metro; i numeri della catena (rosa,
  atlante, uscite, filtri, scheda) non cambiano.
- **La casistica** diventa l'oggetto che passa da una schermata all'altra:
  lato, trigger (uno o più in OR), cella facoltativa. Con la cella, la
  casistica è un'entry derivata «TRIGGER+CELLA_…», costruita con lo stesso
  meccanismo che oggi congela un filtro (`confidenza.congela_filtro`).
- **La 3b parte dalla rosa:** due campi per lato, «togli» e «aggiungi»;
  niente da copiare a mano.
- **Le uscite consigliate** non costano prove: barre = l'H dichiarato alla
  schermata 1, stop al 90° percentile, target spento; il picco della curva
  della casistica si mostra accanto, solo da leggere. Per i trigger a orario,
  l'ora d'uscita è la stessa scadenza scritta come orario.
- **La riga delle prove** compare su ogni schermata; dopo la scheda (6) ogni
  scelta rifatta a monte è segnalata, anche nella scheda successiva.
- **Cambiare H non azzera niente** sullo stesso dataset: si segnala come
  risalita e la scelta fra gli H provati si conta (§9.1).
- **La 4b sceglie il sistema** (Long + Short, solo long, solo short) e il
  passo 5 usa quello.
- **Engine:** solo aggiunte (una funzione per la curva dello scarto per barra,
  una per il picco da mostrare accanto alle uscite, un parametro facoltativo
  a tre funzioni esistenti: `registra_inversione_trend`, `rosa_dei_sistemi`,
  `soglia_rumore_orizzonte`). L'unico numero che cambia per decisione è quello delle uscite
  costruite con la cella (§3.3).
- **Orizzonti multipli:** consiglio di farli in un lavoro dopo questo; qui si
  lascia il posto (§13).

---

## 1 · Il flusso nuovo

La numerazione delle celle del Lab cambia poco: si tiene «2 · Esplora, 3 ·
Le casistiche, 4 · Le uscite», così i riferimenti nei documenti restano
leggibili.

| schermata | riceve | calcola | decide l'utente | passa avanti | prove (riga su ogni schermata, §8) |
|---|---|---|---|---|---|
| 1 · Configura | — | come oggi | symbol, timeframe, **H = orizzonte atteso, dichiarato prima di vedere i dati** | sessione; il registro del dataset (§9.1) | 0 al primo H; la scelta fra gli H provati se H cambia sullo stesso dataset |
| 2a · Il mercato, ora per ora (oggi 2b) | in-sample, H | profilo orario, in bp | — | `s.profilo`, **riusato** da `X_INVERSIONE_TREND` (§6) | 0 (le fasce si contano solo se si sceglie un trigger a orario) |
| *2b · posto libero* | | *la mappa delle anomalie (lavoro 3), prima della rosa* | | | *le fasce provate* |
| 2c · I trigger contro il mercato della stessa ora (oggi 2) | in-sample, H | event study di tutto il catalogo (per il conto) + **curve dello scarto per barra** dei migliori per lato, in bp | — | `s.ev`, `s.curve_scarto` | i trigger misurati |
| 3a · Le casistiche suggerite (oggi 3a bis) | in-sample | `rosa_entry`, come oggi; in fondo la **classifica a scomparsa** con lo stesso metro (§2.2) | — | `s.rosa_trigger` | — |
| 3b · Le tue casistiche | la rosa | casistiche = rosa − tolte + aggiunte | togli / aggiungi, per lato | `s.casistiche` | fasce, solo se c'è un trigger a orario |
| 3c · Atlante (facoltativo) | casistiche | come oggi | — | `s.atlante` | celle misurate |
| 3d · La cella (facoltativa) | atlante | la cella entra **nella casistica** (§3.3) | una cella per lato | casistiche aggiornate | — |
| 4 · Le uscite | casistiche | **uscite consigliate** (§5) e il sistema base sull'in-sample, come oggi | accetta, o modifica barre / stop / target / regola | `s.uscite`, `s.es` | sistemi provati, a ogni impostazione diversa; la riga dice quante sono modifiche |
| 4b · I sistemi | `s.es` | `rosa_sistemi`, come oggi | **il sistema da portare al passo 5** | `s.sistema` | — (i tre sistemi sono già contati alla 4) |
| 5 → 9 | | come oggi, sul sistema scelto | | | come oggi |

Cosa cambia in `vetrina.py` (nomi indicativi):

| oggi | dopo |
|---|---|
| `profilo_delle_ore` | resta, va prima di `esplora`; salva il profilo che `imposta_uscite` riusa |
| `esplora` | resta; le curve diventano curve dello scarto, in bp (§2.1) |
| `classifiche` | si fonde in `rosa_dei_trigger` come dettaglio a scomparsa (`<details>` HTML, funziona su Colab e in VS Code); la funzione resta per compatibilità e chiama la nuova |
| `rosa_dei_trigger` | resta; prepara le casistiche suggerite |
| `scegli_trigger` | diventa `scegli_casistiche(s, togli_long, aggiungi_long, togli_short, aggiungi_short)`; `scegli_trigger(s, long, short)` resta come scorciatoia (scrive le casistiche a mano, come oggi) e la usano i test e la prova d'identità |
| `atlante_dei_trigger`, `scegli_cella` | restano; `scegli_cella` aggiorna le casistiche invece di registrare un filtro per il passo 5 (§3.3) |
| `imposta_uscite` | i parametri restano; `None` (il nuovo predefinito delle celle del Lab) = la proposta consigliata; mostra la proposta accanto a quello che si prova |
| `rosa_dei_sistemi` | aggiunge il parametro `sistema` |
| nuove | `_riga_prove(s, tappa)` (§8), `_avviso_risalita(s)` (§9) |

---

## 2 · Il metro unico

### 2.1 · Le curve della schermata 2c (domanda 5 di `67`)

Oggi le curve sono la variazione media del trade, lorda, in pips, con accanto
la linea dell'ingresso a caso a qualunque ora. Con un asset che sale (BTC dal
2020) una curva long «sale» quasi sempre: misura il mercato, non il trigger.

**Proposta:** la curva principale è lo **scarto per barra** dal mercato della
stessa ora: per ogni barra k = 1..H, la media dei rendimenti a k barre del
trigger meno la media delle barre della stessa fascia oraria, nel verso del
trade, in bp. È la stessa misura di `rosa_entry` (a k = H coincide con
`scarto_bp` della rosa, ed è un test di collaudo), solo distesa su tutte le
barre. Sopra lo zero = il trigger fa meglio del mercato a quell'ora.

- La linea «a qualunque ora» resta come dettaglio a scomparsa (serve a
  vedere quanto pesa l'ora).
- **Trigger a orario (`ORA_…`):** per costruzione coincidono con il mercato
  della loro fascia, quindi lo scarto dalla stessa ora è zero. Per loro la
  curva usa il mercato a qualunque ora, come già fa l'atlante dal 23/10. Il
  grafico lo scrive.
- **Engine, aggiunta:** `stagionalita.curva_scarto_orario(df_is, maschere, H,
  pip, fuso, unita, qualunque_ora=())` → tabella barre × trigger. Riusa
  `media_per_fascia` e `in_unita`, nessuna funzione esistente cambia.

### 2.2 · La classifica a scomparsa

La stessa tabella della rosa, ordinata per «solidità netta», i primi 8 per
lato, con «barra del picco» presa dalla curva del §2.1. La colonna «supera il
rumore» dell'event study (picco lordo, `soglia_rumore_orizzonte`) sparisce
dal Lab: due controlli diversi sugli stessi trigger confondono, ed è uno dei
punti del miscuglio. Resta nel notebook di ricerca (1.2).

---

## 3 · La casistica

### 3.1 · Definizione

Una casistica è: **lato** (long o short) + **trigger** (uno, o più in OR come
oggi) + **cella** facoltativa (al massimo una per lato, come deciso in `66`).
Vive in `s.casistiche`, una per lato in questo lavoro (la domanda 2 del §12
dice perché e cosa resta aperto), con: i nomi, l'entry da passare al motore,
da dove viene («rosa», «aggiunta», «a mano») e la cella.

### 3.2 · Cosa si azzera

Come oggi: cambiare le casistiche azzera tutto quello che viene dopo (uscite,
sistemi, filtri, scheda). Cambiare la cella azzera uscite e seguito. Nuovo: il
registro delle risalite dopo la scheda **non** si azzera mai (§9).

### 3.3 · La cella dentro la casistica (decisione 2 di `67`)

- Con la cella, l'entry della casistica è «TRIGGER+CELLA_X», vera dove sono
  veri il trigger e la cella. Si registra come oggi `congela_filtro` registra
  «ENTRY+FILTRO»; gli stati della cella si calcolano sullo storico completo
  senza lookahead (`atlante.registra_filtri_cella`, invariato).
- **Le uscite (4) e la rosa dei sistemi (4b) lavorano sulla casistica con la
  cella.** Questo è il numero che cambia per decisione: con una cella scelta,
  il sistema base della schermata 4 ha meno trade e uscite proprie. Senza
  cella, tutto identico.
- **Il passo 5 con una cella (strada B) resta come in `66`:** si prova solo
  la cella, con l'asticella a k = celle dell'atlante. Si confrontano il
  trigger senza cella e il trigger con la cella, **con le uscite della
  casistica**. La cella non si conta due volte.
- Le occorrenze minime con la cella (domanda 5 di `67`): una cella passa
  l'atlante solo con almeno 200 occasioni (`MIN_TRIGGER`), quindi la curva
  della casistica ha sempre almeno 200 occorrenze. Non serve una soglia nuova.

---

## 4 · La scelta delle casistiche (3b)

Un modulo di Colab non si riempie da solo con l'uscita di una cella prima.
Le strade:

| strada | come | pro | contro |
|---|---|---|---|
| A · parola chiave | `trigger_long = "rosa, +E5_X, -E7_Y"` | un campo per lato | una sintassi da imparare; un segno sbagliato è un errore silenzioso se non si controlla bene |
| **B · due campi per lato (consigliata)** | `togli_long = ""`, `aggiungi_long = ""`; vuoti = la rosa così com'è | niente sintassi; la scelta resta scritta nel notebook (si rilegge e si rifà uguale) | quattro campi invece di due |
| C · caselle (ipywidgets) | una casella per trigger della rosa | la più comoda | la scelta non resta scritta nel notebook; si perde rieseguendo la cella; Colab e VS Code si comportano in modo diverso |

**Consiglio B.** Ogni nome tolto deve stare nella rosa e ogni nome aggiunto
nel catalogo (o essere un trigger `ORA_…`): altrimenti la cella si ferma e
dice i nomi possibili. La schermata stampa le casistiche risultanti, con da
dove viene ognuna. Rosa vuota su un lato: la 3b parte vuota e lo dice; si
aggiunge a mano o il lato resta spento.

Togliere o aggiungere **non aggiunge prove** (decisione di `67` §3.5): i
trigger sono già tutti contati alla 2c. Un trigger `ORA_…` aggiunto porta le
fasce del profilo, come oggi.

---

## 5 · Le uscite consigliate

### 5.1 · La proposta, per casistica (decisioni 3 e 8 di `67`)

| voce | regola, fissata prima di vedere i dati |
|---|---|
| barre | **l'H scelto alla schermata 1**, uguale per long e short: l'orizzonte dichiarato prima di vedere i dati, quello su cui rosa e atlante hanno misurato la casistica. Nessuna prova in più (decisione di Mattia del 25/10) |
| stop / target | stop al 90° percentile, target spento |
| regola oraria | nessuna, tranne per le casistiche con un trigger a orario (§5.2) |

**Il picco, solo da leggere.** Accanto alla proposta, per ogni lato, la
schermata mostra la barra del picco della curva dello scarto della casistica
(§2.1, con la cella se c'è), con il suo valore in bp e una frase che dice cosa
non è: «È il punto più alto della curva dell'in-sample: si mostra per capire
il movimento, non per scegliere l'uscita. Se cambi le barre, la modifica
conta come una prova». Due casi con una nota in più:
- picco nell'ultimo quarto di H (la stessa regola di `picco_in_coda`
  dell'event study): «il movimento continua fino all'orizzonte che hai
  dichiarato»;
- picco nelle prime barre: «il movimento finisce presto: dopo il picco il
  trade resta aperto fino a H barre, esposto al rumore del prezzo e, sui
  perpetual, al funding, che cresce con la durata». (La commissione si paga
  una volta sola, all'ingresso e all'uscita, qualunque sia la durata: non è
  lei che pesa di più su un trade lungo.)

**Engine, aggiunta:** `picco_curva(curva, H)` → barra, valore e nota (una
funzione pura, facile da collaudare su curve costruite apposta). Non decide
niente.

### 5.2 · Trigger a orario

Un trigger `ORA_LONG_@12:00` apre tutti i giorni alle 12:00, quindi chiudere
«dopo H barre» e chiudere «alle 12:00 + H barre» danno **gli stessi trade**.
L'ora d'uscita consigliata è quindi la stessa scadenza scritta come orario
(`X_ORA_@hh:mm`), più leggibile per chi la porta su TradingView. Non è una
prova in più (un test lo verifica: stessi trade). Il profilo 2a non serve a
sceglierla. Per un trigger a orario la curva **è** l'andamento del mercato da
quell'ora in poi, quindi il suo picco, mostrato accanto come per gli altri, è
il punto in cui la deriva si gira: anche qui solo da leggere.
`X_INVERSIONE_TREND` resta una scelta a mano, diversa: chiude all'arrivo di
un'ora colorata contro.

### 5.3 · Come si mostra

In cima alla schermata 4 una tabella «Uscite consigliate», una riga per lato,
con la regola applicata e, in una colonna a parte, il picco della curva
(§5.1, solo da leggere). Sotto, i campi del modulo: **vuoto = consigliata**
(il predefinito nuovo delle celle del Lab, al posto di 40/25 fissi). Ogni
valore scritto a mano compare in una seconda riga «La tua modifica» accanto a
quella consigliata.

### 5.4 · Il conto delle uscite

Il conto resta quello di oggi: ogni impostazione diversa conta i sistemi che
prova (1, o 3 con i due lati). La proposta consigliata è la prima
impostazione; ogni modifica è un'impostazione in più. Rifare la stessa
impostazione non conta. La riga (§8) lo scrive così: «uscite: 3 sistemi
(consigliata) + 6 (2 modifiche)».

**Perché le barre sono H e non il picco (decisione di Mattia del 25/10).**
La barra del picco è scelta fra H barre guardando la curva dell'in-sample:
`soglia_rumore_orizzonte` dice che questa scelta vale circa 10 prove con H =
41 (soglia 2,78 contro 1,96), non una. Con barre = H la proposta non sceglie
niente sui dati e non costa prove. Se l'utente porta le barre al picco
scrivendolo nel campo, è una modifica come le altre e si conta come le altre.

---

## 6 · Il profilo orario

- Va **prima** delle curve (2a): è il metro, e chi legge le curve deve averlo
  già visto. Il riquadro dice i suoi tre usi: riferimento della rosa e delle
  curve, fonte dei trigger `ORA_…`, fonte di `X_INVERSIONE_TREND`.
- **Un solo calcolo:** `registra_inversione_trend` riceve un parametro
  facoltativo `profilo=None`; il Lab gli passa `s.profilo`, calcolato con gli
  stessi argomenti (stessa H, stesso fuso, stessa unità), quindi stessi numeri.
  `None` = come oggi. La rosa non usa la tabella del profilo ma la stessa
  definizione di fascia (`fasce_orarie`): resta com'è.

---

## 7 · Dalla 4b al passo 5

La cella 4b ha un campo `sistema` con «Long + Short», «Solo long», «Solo
short». Il predefinito è **«Long + Short»**, cioè quello che il passo 5 usa
oggi (identità). La tabella della rosa dei sistemi resta un consiglio. Scegliere
il sistema dopo averne visti tre non è una prova in più: i tre sono già
contati alla 4. `trova_strategia` e la scheda usano `s.sistema` (un lato
spento = la sua entry a `None`), senza tornare alla 3b. Nel notebook di
ricerca la stessa scelta è una variabile `SISTEMA` letta dalla Sessione 3.

---

## 8 · Le prove su ogni schermata (vincolo 9 di `67`)

Una riga fissa in fondo a ogni schermata dalla 2 alla 6, da
`_riga_prove(s, tappa)`. Esempio con numeri inventati:

> **Prove** · questa schermata: 3 sistemi · finora: 148 (139 trigger, 6
> celle, 3 sistemi) · con 148 prove il caso arriva fino a una solidità di
> 3,58.

Si costruisce con i conti che la sessione già tiene (`s.prove`) e la stessa
formula della scheda (`_soglia_da_conti`), quindi la riga della scheda e
quella delle schermate dicono sempre lo stesso numero. Solo informativa, come
oggi.

---

## 9 · Risalire l'imbuto (vincolo 10 di `67`)

- La scheda (6) scrive nella sessione un **diario dell'out-of-sample**: ogni
  volta che si apre, con trigger, cella, uscite, sistema e filtri di quel
  momento. Il diario non si azzera con le scelte; riparte da zero solo
  quando cambia il dataset (§9.1). Oggi le scelte nuove azzerano `s.oos` e
  l'informazione si perde: è il motivo per cui serve un registro a parte.
- Da quel momento, ogni schermata 2→5 rieseguita mostra in testa un
  **riquadro arancione**: «Hai già guardato l'out-of-sample il …. Le scelte che
  fai adesso le fai sapendo come è andata: la prossima scheda non è più una
  prova pulita.» Non blocca niente.
- La scheda successiva scrive, sopra la tabella: «Out-of-sample già guardato
  N volte. Scelte cambiate dopo la prima volta: trigger, uscite …».
- Notebook di ricerca: le stesse due funzioni, chiamate dalla Sessione 4 e
  dalle celle di scelta.

### 9.1 · Cambiare H (correzione di Mattia del 25/10)

Con barre consigliate = H (§5.1), l'H è la scelta che pesa di più su tutta la
catena. Oggi rieseguire la schermata 1 con un altro H crea una sessione nuova:
conto delle prove e diario dell'out-of-sample ripartono da zero. È una
risalita silenziosa: si prova un H, si guarda, se ne prova un altro, e il
conto non lo sa.

**Cosa cambia.**
- **Il dataset** è: symbol, timeframe e confine dell'in-sample (la data
  dell'ultima barra in-sample, che oggi viene dall'80% delle barre del CSV).
  `prepara` tiene un registro, per dataset, fuori dalla sessione: H provati,
  conto delle prove, diario dell'out-of-sample.
- **Stesso dataset, H diverso:** `prepara` crea la sessione nuova ma **riprende
  dal registro** conto e diario; aggiunge l'H alla lista degli H provati;
  mostra la segnalazione di risalita: «Hai già lavorato su questo dataset con
  H = 41. Cambiare orizzonte dopo aver visto i risultati è una scelta fra
  orizzonti: si conta». Se l'out-of-sample è già stato guardato, il riquadro è
  quello arancione del §9.
- **Stesso dataset, stesso H:** nessuna prova in più, nessuna segnalazione
  (si è solo rieseguita la cella).
- **Dataset diverso** (altro symbol, timeframe o confine, per esempio un CSV
  aggiornato con barre nuove): `prepara` riparte da zero, come oggi, e lo
  scrive.

**Il conto.** La scelta fra gli H provati si conta con la logica del §13:
`soglia_rumore_orizzonte` ristretta ai **punti provati** (parametro
facoltativo nuovo `punti=`, additivo). Per k trigger misurati con gli H
provati h₁…hₘ, la soglia è quella di k entry, ciascuna con il massimo preso
sui soli punti h₁…hₘ. Nella soglia cumulata la voce dei trigger diventa il
**numero di prove equivalente** a quella soglia (quante prove indipendenti
danno la stessa soglia con Šidák), al posto dei soli k: non si sommano i
trigger una volta per H, perché orizzonti vicini si sovrappongono. Le altre
voci (celle, uscite, filtri) fatte con gli H di prima restano nel conto: sono
prove fatte. Con un H solo, la soglia è esattamente `soglia_rumore(k)` (come
oggi `soglia_rumore_orizzonte` con un orizzonte di una barra), quindi il conto
di chi non cambia H resta identico.

**Un limite da sapere.** Il registro vive finché resta aperto il notebook:
riavviare il kernel (o Colab che si disconnette) lo azzera. Salvarlo in un
file accanto ai dati è il passo naturale del lavoro 2, quando il confine
dell'in-sample diventerà una data salvata con lo studio. Qui lo si scrive
nel riquadro della schermata 1.

**Notebook di ricerca:** la cella dove si scrive `H = …` chiama la stessa
funzione del registro, con symbol, timeframe e confine dell'in-sample.

---

## 10 · Il notebook di ricerca (decisione 4 di `67`)

- Stesso ordine nella Sessione 1: profilo orario prima delle curve, curve
  dello scarto, rosa, casistiche con «togli / aggiungi», atlante e cella. La
  Sessione 2 parte dalle uscite consigliate; la scelta del sistema passa alla
  Sessione 3.
- **Niente logica doppia:** le parti nuove stanno nell'engine (§2.1, §5.1) e
  in poche funzioni di `vetrina.py` che il notebook di ricerca chiama già
  (come `soglia_cumulata`). Le celle mostrano tabelle grezze, come oggi.
- Restano dove sono le parti che ha solo lui (domanda 7 di `67`): entry-metro,
  la griglia delle uscite a regola (TEST 2), la confidenza 3.3.
- Nota, non da cambiare qui: il notebook di ricerca ha `H = 25`, il Lab parte
  da 41. Le prove d'identità si fanno con l'H di ciascuno.

---

## 11 · Collaudo, identità, tempi

### 11.1 · Test nuovi (casi a risultato noto)

1. `curva_scarto_orario`: a k = H coincide con `scarto_bp` di `rosa_entry`;
   un trigger costruito con uno scarto noto a ogni barra dà quella curva; un
   trigger `ORA_…` misurato contro la stessa ora dà zero, contro qualunque ora
   dà la curva della fascia.
2. `picco_curva`: curve costruite con il picco a metà, in coda, alla prima
   barra; le uscite consigliate hanno sempre barre = H, qualunque sia il
   picco.
3. Casistiche: rosa − togli + aggiungi; nomi sbagliati fermano con il messaggio
   giusto; togliere o aggiungere non cambia `s.prove`.
4. Cella nella casistica: l'entry «TRIGGER+CELLA_X» è l'AND delle due
   maschere; il passo 5 con la cella non somma prove.
5. Trigger a orario: uscita `X_ORA_@` consigliata e uscita a barre danno gli
   stessi trade.
6. Conto delle uscite: consigliata + 2 modifiche = tre impostazioni; rifarne
   una non conta; portare le barre al picco conta come una modifica.
7. 4b → passo 5: «Solo long» fa girare il passo 5 con l'entry short a `None`.
8. Diario: scheda, poi `scegli_casistiche`, poi scheda = due aperture, una
   risalita segnalata.
9. La riga delle prove della schermata 4 e quella della scheda danno lo
   stesso numero.
10. Cambiare H (§9.1), su dati costruiti apposta:
    - `prepara` con H = 41 e poi H = 25 sullo stesso CSV: H provati = [41,
      25], conto e diario ripresi, risalita segnalata;
    - di nuovo H = 25: nessuna prova in più, nessuna segnalazione;
    - stesso CSV con un altro timeframe, o con il confine spostato (barre in
      più): registro da zero;
    - `soglia_rumore_orizzonte(k, punti=[H])` è uguale a `soglia_rumore(k)`;
      `soglia_rumore_orizzonte(1, punti=[4, 16, 32, 96])` è 2,44 (±0,01, seme
      fisso), il valore della simulazione del §13; con due punti la soglia
      sta fra quella di un punto e quella di due prove indipendenti;
    - la voce dei trigger nella soglia cumulata, con due H, è il numero
      equivalente atteso, e la soglia della scheda torna con la formula.

I test esistenti non cambiano: quelli che chiamano `scegli_trigger`
(`test_vetrina.py`, `test_exchange.py`) continuano a farlo, perché la
funzione resta.

### 11.2 · Identità

A scelte uguali (gli stessi trigger scritti a mano con `scegli_trigger`,
nessuna cella, le uscite scritte uguali, «Long + Short») restano identici al
bit: event study, profilo, rosa, atlante, uscite, rosa dei sistemi, filtri,
due metà, scheda. Su BINANCE_PERP_BTCUSDT nei due notebook vivi, prima e
dopo; giro completo su BYBIT_SPOT_ETHUSDT. Cambiano solo, per decisione:
le curve e la classifica (presentazione, nessun numero a valle), i
predefiniti delle celle (consigliate al posto di 40/25) e i numeri con la
cella dentro la casistica.

### 11.3 · Tempi

Le curve dello scarto costano H passate sulle barre per i trigger mostrati
(stima: pochi secondi); le uscite consigliate nulla. Il resto è come oggi
(l'atlante circa dieci secondi). Si misurano prima e dopo sul PC.

### 11.4 · Rischi

- Due nomi per la stessa cosa durante il passaggio (`scegli_trigger` e
  `scegli_casistiche`): la prima resta solo come scorciatoia documentata.
- Un riquadro arancione che compare troppo spesso perde valore: compare solo
  dopo la prima scheda, mai prima.

---

## 12 · Decisioni di Mattia (25/10/2026)

1. **3b:** sì, due campi per lato, «togli» e «aggiungi» (strada B, §4).
2. **Più casistiche sullo stesso lato:** sì, **in OR come oggi**, per ora.
   *Criterio di `67`, per dopo:* i sistemi separati per casistica sono la
   strada verso il portafoglio; la struttura della casistica (§3.1) è pronta
   a diventare «un sistema per casistica» in un lavoro successivo, con le sue
   uscite, e la rosa dei sistemi diventerà la scelta del portafoglio.
3. **Il picco mostrato accanto:** sì, dalla curva dello scarto dalla stessa
   ora, con le due note del §5.1 (la seconda riscritta: correzione B qui
   sotto).
4. **Barre consigliate = H**, picco solo da leggere; se si cambia il campo,
   la modifica si conta come le altre (§5.1, §5.4).
5. **Classifica:** sì, sparisce dal Lab la colonna «supera il rumore» del
   picco lordo (§2.2); resta nel notebook di ricerca.
6. **4b:** sì, predefinito «Long + Short», come oggi (§7).
7. **Trigger a orario:** sì, uscita consigliata scritta come orario `X_ORA_@`,
   stessi trade della scadenza in barre (§5.2).
8. **Orizzonti multipli:** sì, in un lavoro dopo questo, con il posto
   lasciato alla schermata 1 (§13).

**Correzioni di Mattia, entrate nella proposta:**
- **A · Cambiare H** non è più una risalita silenziosa: sullo stesso dataset
  (symbol, timeframe, confine dell'in-sample) diario e conto non si azzerano,
  il cambio si segnala e la scelta fra gli H provati si conta con
  `soglia_rumore_orizzonte` sui punti provati; `prepara` riparte da zero solo
  se cambia il dataset (§9.1, test 10 del §11.1).
- **B · Nota «picco nelle prime barre»:** la commissione si paga una volta
  sola; la nota parla del rumore e, sui perpetual, del funding, che crescono
  con la durata (§5.1).

---

## 13 · Orizzonti multipli (domanda 6 di `67`)

**Cosa si è verificato.** `soglia_rumore_orizzonte` simula una passeggiata
casuale e prende il massimo di |S_t / √t| su tutte le barre da 1 a H: è il
costo di scegliere la barra del picco. Ristretta ai soli punti di una
griglia, la stessa simulazione dà il costo di scegliere fra quegli orizzonti.
Simulazione fatta il 25/10 (400.000 giri, seme fisso):

| cosa si sceglie | soglia (famiglia 5%) | vale circa |
|---|---|---|
| un orizzonte solo, dichiarato prima | 1,96 | 1 prova |
| fra 4, 16 barre (1 e 4 ore su M15) | 2,22 | 2 prove |
| fra 4, 16, 32, 96 barre (1, 4, 8, 24 ore) | 2,44 | 4 prove |
| la barra del picco fra 1 e 96 | 2,87 | 13 prove |

Gli orizzonti di una griglia larga sono poco legati fra loro (fra 4 e 16
barre la correlazione è √(4/16) = 0,5), quindi **la sovrapposizione fa
risparmiare poco**: scegliere fra 4 orizzonti costa quasi come 4 prove
indipendenti. Vale per trigger che non si sovrappongono; con trigger a
grappolo è un pavimento, come oggi.

**Proposta.**
- L'orizzonte atteso si dichiara alla schermata 1 (già oggi H si sceglie
  prima di vedere i dati). Gli altri orizzonti della griglia si **mostrano
  soltanto** (una tabella della rosa per orizzonte, a scomparsa) e non
  costano niente finché decide l'orizzonte dichiarato.
- Se l'utente passa a un orizzonte non dichiarato, la sessione conta la
  scelta fra tutti gli orizzonti della griglia, con la tabella sopra (e la
  stessa simulazione con i punti della griglia, un parametro facoltativo
  `punti=` di `soglia_rumore_orizzonte`), e la riga lo dice.
- Ore e barre: la griglia è in ore e si converte con il timeframe; un'ora che
  non è un numero intero di barre (1 ora su H4) si salta, con una nota.
- Rosa e atlante misurano lo scarto **a** H, non il picco: rifatti per ogni
  orizzonte della griglia costano 4 volte il tempo (l'atlante circa 40
  secondi).

**Consiglio:** un lavoro dopo questo. Qui si lascia il posto: la schermata 1
tiene l'orizzonte dichiarato, e `s.prove` ha già la voce in cui contare la
scelta fra orizzonti.

---

## 14 · Resoconto (*resoconto*, 25/10/2026)

Due Pull request, come chiesto da Mattia.

**A · motore e test (PR #63, unita).** Solo aggiunte: `curva_scarto_orario` e
`picco_curva` (`engine/stagionalita.py`); `punti=`, `prove_equivalenti`,
`prove_trigger_orizzonti` (`engine/giudizio.py`); `engine/registro_dataset.py`;
`profilo=` in `registra_inversione_trend`. `test_riordino_motore.py` 37/37.
Identità main contro ramo su BINANCE_PERP_BTCUSDT, H = 41: event study, soglia di
rumore, profilo, `X_INVERSIONE_TREND`, uscite, rosa dei sistemi e 3.954 trade
identici.

**B · Lab e notebook di ricerca.**
- `engine/vetrina.py`: le schermate 2a, 2c, 3a, 3b, 3c, 3d, 4, 4b come nel §1;
  `scegli_casistiche`; la cella nella casistica (`entry_con_cella`); le uscite
  consigliate; `rosa_dei_sistemi(sistema=)` e il passo 5 sul sistema scelto; la
  riga delle prove su ogni schermata; il registro del dataset in `prepara`; il
  diario dell'out-of-sample nella scheda e il riquadro arancione delle risalite.
  Per il notebook di ricerca, funzioni pubbliche che usano la stessa logica:
  `casistiche_dalla_rosa`, `uscite_consigliate`, `tabella_uscite_consigliate`,
  `entry_del_sistema`, `registro_orizzonte`, `segna_oos`, `grafico_scarto`.
  `classifiche` e `scegli_trigger` restano (test e uso a mano).
- `Trading_System_Lab_Crypto.ipynb`: celle 2a/2c scambiate, 3a classifiche tolta
  (è il dettaglio a scomparsa della 3a), 3b con «togli / aggiungi», 4 con le uscite
  consigliate (barre 0 = H, regola «consigliata»), 4b con il campo «sistema».
- `Trading_Grid_Search_v4_backtesting.ipynb`: H e registro in testa alla Sessione 1,
  1.0 profilo orario prima delle curve, 1.3 bis curve dello scarto, casistiche dalla
  rosa (`TOGLI_*`, `AGGIUNGI_*`), cella nella casistica (`LONG_casistica`),
  uscite consigliate alla 2.2, `SISTEMA` alla Sessione 3, orizzonti provati nella
  soglia cumulata, diario dell'out-of-sample alla Sessione 4. Restano entry-metro,
  la griglia delle uscite (TEST 2) e la confidenza.
- **Un test esistente cambiato, per la correzione A di Mattia:** `test_vetrina.py`
  test 66 diceva «prepara (symbol, timeframe o H nuovi): il conto riparte da zero»;
  ora dice «prepara sullo stesso dataset riprende il conto; con un dataset diverso
  riparte da zero». Prima dei test 60-65, che misurano il conto da zero, il test
  svuota il registro (come un riavvio del kernel): i loro controlli non cambiano.
- `test_riordino_lab.py` 28/28: registro e soglia con due H, 2a/2c/3a, 3b, uscite
  consigliate e conto delle impostazioni, trigger a orario (`X_ORA_@` = stessi
  trade), cella nella casistica (forzata solo nel test), 4b → passo 5, diario e
  risalite.

**Prove d'identità (collaudo, non verdetto).** I due notebook vivi eseguiti cella
per cella, `main` contro ramo, a scelte uguali (nel ramo: la rosa tolta e i trigger
di `main` aggiunti, barre 40/25, regola «nessuna», sistema predefinito):
- BINANCE_PERP_BTCUSDT: Lab, event study, uscite, filtri, out-of-sample, trade,
  rosa, atlante e conto delle prove identici; tabelle 14/16 identiche: la soglia
  cumulata ha due voci in più (`orizzonti`, `voce_trigger`) con tutti i valori di
  prima uguali (dopo i giri, la frase dice «schermata 2c» al posto di «schermata 2»: solo testo), la lente apre un trade a caso a ogni esecuzione (n. 77 contro
  n. 117 di 145). Ricerca: 78/78 variabili identiche.
- BYBIT_SPOT_ETHUSDT: lo stesso esito (Lab 10/10 oggetti, tabelle 13/15 con le
  stesse due differenze; ricerca 76/76).
- Giro completo del Lab con i valori predefiniti nuovi su BTC perp ed ETH spot: in
  fondo senza errori (casistica suggerita, uscite consigliate a H = 41, scheda,
  money management, verifica, stress test).

**Trovato strada facendo, non cambiato (decide Mattia):**
- nel notebook di ricerca `X_INVERSIONE_TREND` (1.4) usa il profilo in pips, il Lab
  in bp dal 23/10: allinearlo cambia i numeri della ricerca (in `docs/00`, problemi
  aperti);
- la rosa tiene insieme due candidati solo con |rho| ≤ 0,3 sui guadagni
  giornalieri: un long e uno short che scattano spesso hanno guadagni legati in
  verso opposto (il mercato li muove al contrario), e la rosa ne tiene uno solo.
  È il comportamento scritto in `engine/rosa.py`; lo si nota ora perché la 3b
  parte dalla rosa.
