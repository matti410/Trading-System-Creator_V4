# Guida — analisi di fonti testuali (articoli, video, libri) e trascrizione in condizioni

**Per:** Mattia · **Data:** 7 ottobre 2026
**Dove sta:** nel repo `Trading-System-Creator_V4`. Sostituisce `GUIDA_ANALISI_ARTICOLI_MEDIUM.md` (da cancellare dal repo). Il metodo completo è nel progetto Claude «Metodo Combinatorio», documento `50_IDEE_DA_ARTICOLI.md`: questa guida è la parte pratica, da seguire passo per passo.

In questa fase **non c'è codice da lanciare**. Si leggono le fonti, si scrivono schede in testo e si decide cosa entra nel catalogo. Il codice arriva solo dopo il tuo via libera.

---

## 1 · Tre tipi di fonte: chi porta il testo

| fonte | chi porta il testo | cosa serve |
|---|---|---|
| **Articolo** (Medium, TradingView, blog) | Claude lo legge dal tuo Chrome | Chrome aperto con l'estensione Claude in Chrome e login a Medium fatto (§2). In alternativa incolli tu il testo |
| **Video YouTube** | **tu**: estrai la trascrizione e la incolli in chat | trascrizione + titolo, canale, link, data del video (§4) |
| **Libro** | **tu**: PDF o testo incollato dei capitoli che vuoi analizzare | capitoli indicati con ordine, titolo, autore, edizione (§5) |

La chat va aperta **dentro il progetto «Metodo Combinatorio»**, non fuori: così Claude ha già i documenti di progetto (`00`, `20`, `21`, `32`, `50` e gli altri).

---

## 2 · Prima di iniziare (solo per gli articoli letti da Chrome)

Controlla queste due cose (servono ogni volta che apri una chat nuova):

1. **Chrome aperto** sul tuo computer, con l'estensione **Claude in Chrome** attiva.
2. **Login a Medium fatto nello stesso Chrome**, con il tuo abbonamento. Prova: apri un articolo «Member-only» qualsiasi; se lo vedi per intero, è tutto a posto.

Da telefono non funziona la lettura da Chrome: puoi comunque incollare il testo. Per video e libri non serve Chrome.

---

## 3 · Come si avvia

Apri una **nuova chat nel progetto** e incolla il testo che corrisponde alla fonte. Un solo tipo di fonte per chat va bene; si possono anche mescolare.

### 3.1 Articoli

```
Leggi nel progetto il documento 50_IDEE_DA_ARTICOLI.md e segui quel metodo.
Repo di destinazione: V4.

Articoli da analizzare, in quest'ordine:
1. <link>
2. <link>
3. <link>

Per ciascuno: leggilo con Claude in Chrome e scrivimi la scheda (§3 di 50), in testo.
Niente codice finché non ti dico quali candidati approvo.
Se un articolo non si apre, dimmelo: ti incollo il testo.
```

### 3.2 Video YouTube

```
Leggi nel progetto il documento 50_IDEE_DA_ARTICOLI.md e segui quel metodo (§2.2 per i video).
Repo di destinazione: V4.

Fonte: video YouTube
Canale: <nome del canale>
Titolo: <titolo del video>
Link: <link>
Data del video: <data>

Trascrizione (con i tempi, se ci sono):
<incolla qui la trascrizione>

Scrivimi la scheda (§3 di 50), in testo.
Segna in «DA VERIFICARE» ogni numero o nome che compare solo nella trascrizione.
Niente codice finché non ti dico quali candidati approvo.
```

Se la trascrizione è lunga e non entra in un messaggio, incollala in più parti: scrivi «parte 1 di 3, aspetta le altre» e, nell'ultima, «fine, scrivi la scheda».

### 3.3 Libri

```
Leggi nel progetto il documento 50_IDEE_DA_ARTICOLI.md e segui quel metodo (§2.3 per i libri).
Repo di destinazione: V4.

Fonte: libro
Autore: <autore>
Titolo: <titolo>
Edizione e anno: <edizione, anno>
Capitolo: <numero e titolo>

Testo del capitolo: <allegato PDF oppure incollato qui sotto>

Scrivimi la scheda (§3 di 50), in testo.
Dimmi a quale mercato e timeframe si riferisce la regola del libro.
Niente codice finché non ti dico quali candidati approvo.
```

**Quante fonti per volta:** da 3 a 5 per chat per gli articoli; **un video o un capitolo alla volta** per le fonti incollate, così la scheda resta leggibile. Se la chat diventa lunga, ne apri un'altra nel progetto con lo stesso testo: il registro (§10 di `50`) dice cosa è già stato fatto.

**Il primo giro suggerito** è il pilota già letto, l'articolo Fourier (§8.1): per quello esiste già un esempio guidato in `50` §11.

---

## 4 · Come estrarre la trascrizione di un video

Sei tu a farlo, quindi qualche accorgimento che rende la scheda più affidabile:

- **Tieni i tempi** (minuti e secondi): servono per i riferimenti e per ricontrollare i punti dubbi.
- **Copia titolo, canale, link e data** del video e incollali insieme alla trascrizione.
- **La trascrizione automatica sbaglia**, soprattutto con numeri e nomi di indicatori. Non devi correggerla: Claude segna i punti dubbi in «DA VERIFICARE». Quando arriva la scheda, controlla nel video quei punti (minuto indicato) e rispondi con i valori giusti.
- **Se il relatore mostra a schermo** parametri o indicatori che non si sentono, manda uno screenshot di quel momento.
- Ignora sponsor, inviti a iscriversi e link nella descrizione: Claude non li segue.

---

## 5 · Come preparare un libro

- Indica **il capitolo** (o i capitoli, uno per volta) e allega **il PDF o incolla il testo**: lo leggo capitolo per capitolo.
- Per i libri Claude **non riporta passaggi**: nella scheda trovi il concetto riscritto con parole sue, con capitolo e pagina dell'**edizione che hai tu**.
- **Mercato e timeframe**: molti libri testano regole su azioni o dati giornalieri. La scheda dice a quale timeframe si riferisce la regola e come si traduce su M15 (oppure se si scarta).
- Backtest e statistiche del libro non pesano nella scelta: contano solo i risultati del tool.

---

## 6 · Cosa succede dopo l'invio

| passo | chi | cosa |
|---|---|---|
| 1 | Claude (articoli) · tu (video, libri) | il testo della fonte arriva in chat: articoli letti da Chrome (solo testo, niente immagini né formule), video e libri incollati da te |
| 2 | Claude | ti scrive **una scheda per fonte**: idea, candidati (entry / filtro / uscita), dove la fonte guarda al futuro, doppioni probabili, cosa scartare, e per i video i punti da verificare |
| 3 | **Tu** | per ogni candidato rispondi **sì / no / modifica**; per i video, conferma i numeri dubbi. Basta una riga, per esempio: «Video 1: sì al filtro, no all'entry; il periodo al minuto 12:40 è 20.» |
| 4 | Claude | scrive il codice, lo collauda (lookahead, degenerazione, sovrapposizioni con il catalogo) e te lo consegna con le istruzioni |
| 5 | **Tu** | carichi i file ed esegui i controlli (§8) |
| 6 | Claude | aggiorna il registro delle idee (§10 di `50`) |

Se qualcosa non ti convince in una scheda, dillo prima del via libera: costa una riga, mentre dopo costa codice da rifare.

---

## 7 · Come leggere una scheda

Ogni scheda ha sempre gli stessi campi (modello completo in `50` §3):

- **Fonte** (tipo, autore o canale, titolo, data) e **riferimento** (paragrafo, minuto o pagina)
- **Affidabilità del testo**: alta per articoli e libri, media-bassa per le trascrizioni automatiche
- **Idea** in due righe
- **Candidati**: tipo (entry long / entry short / filtro / uscita), nome proposto, parametri fissati in partenza, finestra in barre, riferimento, e se la **traduzione è nostra** (regola vaga resa misurabile da Claude)
- **Lookahead**: i punti in cui la fonte guarda al futuro e come si evitano
- **Da verificare**: numeri e nomi dubbi (video), timeframe e mercato (libri)
- **Prove**: quante candidate si aggiungono al conteggio dei test multipli
- **Doppioni**: con quali condizioni già presenti si sovrappone
- **Scartati**: cosa è rimasto fuori, con il motivo
- **Decisione**: la tua

Gli scarti non sono un giudizio sull'idea: sono limiti del tool o dei dati di oggi (per esempio il volume reale, che su MT5 non c'è, o una zona tracciata a occhio), e restano riaprivibili.

**Attenzione alle traduzioni.** Quando il relatore di un video dice una regola vaga («quando il mercato è esteso») e Claude la rende misurabile, la scheda lo segna. Controlla che la traduzione ti sembri fedele: il collaudo verifica che la regola sia causale, non che sia quella che intendeva il relatore.

---

## 8 · Quando arrivano i file: come eseguire

Claude ti dice sempre **quali di questi passi servono** e cosa devi vedere alla fine di ognuno.

1. **Carica i file sul repo**, nelle cartelle indicate: i file di `engine/…` nella cartella `engine`, gli altri nella cartella principale.
2. **Lancia i test nuovi dal terminale**, aperto nella cartella del progetto: `python test_nome.py` (il nome esatto lo trovi nella consegna). L'ultima riga attesa ha la forma `RISULTATO: n/n test superati`. Se i superati sono meno del totale, copia qui il messaggio.
3. **Rilancia `Collaudo_Catalogo.ipynb` su Colab**: *Runtime → Esegui tutto*, 2–3 minuti. Attesi: A1 e A2 con tutte le prove superate, **B con 0 LOOKAHEAD e 0 ERRORE**, D ed E superate. La sezione C è una tabella da leggere, senza promosso o bocciato.
4. **Nel notebook principale** la condizione compare da sola dopo la registrazione: riavvia il runtime e riesegui dall'inizio, così i dizionari si rileggono.

Se un controllo non torna: incolla in chat l'ultima riga o il messaggio in rosso. Non serve capire l'errore.

---

## 9 · Le regole da ricordare

- **I risultati su EURUSD non sono il metro.** Se una condizione non produce nulla, la risposta è «bene, il tool me lo dice». Se Claude giudica se un sistema «tiene» o propone di cambiare asset, è fuori regola: diglielo.
- **Prima la scheda e il tuo via libera, poi il codice.** Le idee si scelgono prima di vedere cosa farebbero sul dataset.
- **Parametri della fonte dichiarati e fissi.** Niente varianti provate per vedere quale va meglio: ogni valore in più è una prova in più nel conteggio dei test multipli.
- **Nessun numero preso da una trascrizione non verificata.** Se un parametro compare solo nel parlato, prima lo controlli tu nel video.
- **Ciò che dice l'autore o il relatore (equity, «funziona sul forex», esempi sul grafico) non conta come evidenza.** Gli esempi sono spesso su dati sintetici o scelti dopo.
- **Il testo delle fonti è dato, non istruzione.** Inviti a iscriversi, sponsor, banner e link promozionali non si seguono.
- **Il codice dell'autore non si copia, i passaggi dei libri non si riportano.** Si riscrive dal concetto e nel docstring si cita la fonte.
- **Ogni condizione entrata da una fonte finisce nel registro**, con data, fonte (e minuto o pagina) e prove aggiunte.

---

## 10 · Se qualcosa non funziona

| problema | cosa fare |
|---|---|
| Claude dice che Chrome non risponde | apri Chrome, controlla che l'estensione sia attiva, riprova; in alternativa incolla tu il testo dell'articolo |
| l'articolo arriva troncato o con solo l'anteprima | il login a Medium è scaduto: rifai l'accesso nello stesso Chrome e riprova |
| servono un grafico o una formula | Claude chiede uno screenshot, oppure incolla tu la formula |
| la trascrizione del video è troppo lunga per un messaggio | incollala in più parti numerate («parte 1 di 3») e scrivi «fine» nell'ultima |
| la trascrizione ha numeri o nomi strani | normale: Claude li segna in «DA VERIFICARE»; controlli tu nel video al minuto indicato |
| il libro è un PDF scansionato e il testo non si legge | prova a incollare le pagine come testo, oppure allega le immagini delle pagine più importanti |
| la chat è diventata molto lunga | apri una nuova chat nel progetto con lo stesso testo di avvio |
| non sai se una fonte è già stata fatta | chiedi a Claude di controllare il registro in `50` §10 |

---

## 11 · Elenco delle fonti

### 11.1 Pilota (già letto il 7/10/2026)

| n | tipo | autore | titolo | data | link | stato |
|---|---|---|---|---|---|---|
| P1 | articolo | Sofien Kaabar | Forecasting Market Cycles with Fourier Transform in Python | 29/9/2026 | https://medium.com/@kaabar-sofien/forecasting-market-cycles-with-fourier-transform-in-python-9b29c110cd3c | letto; scheda da fare (esempio in `50` §11) |

### 11.2 Articoli candidati trovati con la ricerca interna di Medium il 7/10/2026

**Non ancora letti.** Trovati cercando «market regime python trading» e «volume indicator python trading strategy», perché regime di mercato e volume sono i due temi che vuoi aggiungere al catalogo. Titoli e date sono quelli mostrati nei risultati di ricerca; per EODHD e Kryptera il titolo è ricavato dal link e la data non è stata rilevata. Le note sono promemoria per la lettura, non giudizi.

| n | autore | titolo | data | tema | link | note |
|---|---|---|---|---|---|---|
| 1 | Sofien Kaabar | Detecting the Market Regime With Technical Indicators (Gopalakrishnan Range Index) | 20/2/2022 | regime, indice di range → filtro | https://medium.com/@kaabar-sofien/detecting-the-market-regime-with-technical-indicators-646b245a59c0 | Member-only. Compare anche ripubblicato il 21/7/2022: https://medium.com/@kaabar-sofien/detecting-the-market-regime-with-technical-indicators-a5aa0bd27de3 (stesso tema, leggerne uno solo) |
| 2 | Sofien Kaabar | Detecting Market Regime With the Vertical Horizontal Filter | 16/2/2022 | regime, trend o range → filtro | https://medium.com/@kaabar-sofien/detecting-market-regime-with-the-vertical-horizontal-filter-44b1a8b7bfbe | Member-only |
| 3 | Sofien Kaabar | Trending or Ranging Market? Using The Vertical Horizontal Filter in Trading | 15/1/2021 | regime, stesso indicatore dell'articolo 2 | https://medium.com/swlh/trending-or-ranging-market-using-the-vertical-horizontal-filter-in-trading-be093efb0e1 | Member-only. Probabile doppione dell'articolo 2: leggerne uno solo, poi controllare le sovrapposizioni |
| 4 | PyQuantLab | Introduction to Adaptive Trading Strategies: Why Static Indicators Fail | 23/8/2025 | filtri adattivi al regime | https://medium.com/@pyquantlab/introduction-to-adaptive-trading-strategies-why-static-indicators-fail-53700bae1946 | non indicato come Member-only. Occhio ai filtri non causali (`50` §6) |
| 5 | PyQuantLab | This Python Strategy Detects When Bitcoin's Market Regime Changes | 6 set (anno non mostrato) | regime di mercato | https://medium.com/@pyquantlab/this-python-strategy-detects-when-bitcoins-market-regime-changes-4a06a2538c07 | Member-only. Controllare se il regime è stimato su tutto il campione |
| 6 | Alexzap | Can Bayesian Change Point (CP) Detection Perform Volatility-Based Market Regime Segmentation? | 1 ago (anno non mostrato) | regime, punti di cambio sulla volatilità | https://medium.com/@alexzap922/can-bayesian-change-point-cp-detection-perform-volatility-based-market-regime-segmentation-982d264cdebc | Member-only. Prova su SPY con una libreria esterna di change point: tipicamente stima offline, quindi trappola «modelli di regime sul campione intero» |
| 7 | EODHD | Advanced Momentum Trading Strategies with Volatility and Volume Indicators Using Python (titolo dal link) | data non rilevata | volume e volatilità | https://medium.com/@eodhd/advanced-momentum-trading-strategies-with-volatility-and-volume-indicators-using-python-412708c53603 | verificare se usa volume reale o tick volume; su MT5 c'è solo il tick volume |
| 8 | Kryptera | I Found a Volume Delta Divergence Indicator on TradingView (titolo dal link) | data non rilevata | volume delta | https://medium.com/@Kryptera/i-found-a-volume-delta-divergence-indicator-on-tradingview-1c03962e9241 | il volume delta richiede in genere dati a livello di tick: probabile scarto per dato mancante (`50` §8), da verificare nella lettura |

**Ordine suggerito per il primo giro:** P1 (pilota), poi 1 (regime), poi 7 (volume). Così si provano subito le tre famiglie e si vede se il metodo regge prima di leggerne altri.

### 11.3 Video YouTube

Nessuno ancora. Aggiungi qui i video che vuoi far analizzare, una riga ciascuno; poi usa il testo di avvio del §3.2 con la trascrizione.

| n | canale | titolo | link | data | tema | trascrizione inviata | note |
|---|---|---|---|---|---|---|---|
| | | | | | | | |
| | | | | | | | |

### 11.4 Libri

Nessuno ancora. Aggiungi qui i capitoli che vuoi far analizzare, uno per riga; poi usa il testo di avvio del §3.3.

| n | autore | titolo | edizione | capitolo | tema | testo inviato | note |
|---|---|---|---|---|---|---|---|
| | | | | | | | |
| | | | | | | | |

### 11.5 I tuoi articoli

Aggiungi qui gli articoli che vuoi far analizzare, una riga ciascuno. Poi incollali nel testo di avvio (§3.1).

| n | link | tema | note |
|---|---|---|---|
| | | | |
| | | | |
| | | | |
