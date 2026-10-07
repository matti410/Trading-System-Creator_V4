## 1 · Prima di iniziare

Controlla queste tre cose (servono ogni volta che apri una chat nuova):

1. **Chrome aperto** sul tuo computer, con l'estensione **Claude in Chrome** attiva.
2. **Login a Medium fatto nello stesso Chrome**, con il tuo abbonamento. Prova: apri un articolo «Member-only» qualsiasi; se lo vedi per intero, è tutto a posto.
3. **La chat va aperta dentro il progetto «Metodo Combinatorio»**, non fuori: così Claude ha già i documenti di progetto (`00`, `20`, `21`, `32`, `50` e gli altri).

Da telefono non funziona: Claude legge gli articoli attraverso il Chrome del computer.

---

## 2 · Come si avvia

Apri una **nuova chat nel progetto** e incolla questo testo, sostituendo i link con quelli che vuoi analizzare (o lascia quelli dell'elenco in fondo):

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

**Quanti articoli per volta:** da 3 a 5 per chat, così le schede restano leggibili e puoi decidere con calma. Se la chat diventa lunga, ne apri un'altra nel progetto con lo stesso testo: il registro (§10 di `50`) dice cosa è già stato fatto.

**Il primo giro suggerito** è il pilota già letto, l'articolo Fourier (§8.1): per quello esiste già un esempio guidato in `50` §11.

---

## 3 · Cosa succede dopo l'invio

| passo | chi | cosa |
|---|---|---|
| 1 | Claude | apre ogni link nel tuo Chrome e legge il testo dell'articolo (arriva solo il testo: immagini e formule no) |
| 2 | Claude | ti scrive **una scheda per articolo**: idea, candidati (entry / filtro / uscita), dove l'articolo guarda al futuro, doppioni probabili, cosa scartare |
| 3 | **Tu** | per ogni candidato rispondi **sì / no / modifica**. Basta una riga, per esempio: «Articolo 1: sì al filtro, no all'entry. Articolo 2: no.» |
| 4 | Claude | scrive il codice, lo collauda (lookahead, degenerazione, sovrapposizioni con il catalogo) e te lo consegna con le istruzioni |
| 5 | **Tu** | carichi i file ed esegui i controlli (§5) |
| 6 | Claude | aggiorna il registro delle idee (§10 di `50`) |

Se qualcosa non ti convince in una scheda, dillo prima del via libera: costa una riga, mentre dopo costa codice da rifare.

---

## 4 · Come leggere una scheda

Ogni scheda ha sempre gli stessi campi (modello completo in `50` §3):

- **Fonte** e data di lettura
- **Idea** in due righe
- **Candidati**: tipo (entry long / entry short / filtro / uscita), nome proposto, parametri fissati in partenza, finestra in barre
- **Lookahead**: i punti in cui l'articolo guarda al futuro e come si evitano
- **Prove**: quante candidate si aggiungono al conteggio dei test multipli
- **Doppioni**: con quali condizioni già presenti si sovrappone
- **Scartati**: cosa è rimasto fuori, con il motivo
- **Decisione**: la tua

Gli scarti non sono un giudizio sull'idea: sono limiti del tool o dei dati di oggi (per esempio il volume reale, che su MT5 non c'è), e restano riaprivibili.

---

## 5 · Quando arrivano i file: come eseguire

Claude ti dice sempre **quali di questi passi servono** e cosa devi vedere alla fine di ognuno.

1. **Carica i file sul repo**, nelle cartelle indicate: i file di `engine/…` nella cartella `engine`, gli altri nella cartella principale.
2. **Lancia i test nuovi dal terminale**, aperto nella cartella del progetto: `python test_nome.py` (il nome esatto lo trovi nella consegna). L'ultima riga attesa ha la forma `RISULTATO: n/n test superati`. Se i superati sono meno del totale, copia qui il messaggio.
3. **Rilancia `Collaudo_Catalogo.ipynb` su Colab**: *Runtime → Esegui tutto*, 2–3 minuti. Attesi: A1 e A2 con tutte le prove superate, **B con 0 LOOKAHEAD e 0 ERRORE**, D ed E superate. La sezione C è una tabella da leggere, senza promosso o bocciato.
4. **Nel notebook principale** la condizione compare da sola dopo la registrazione: riavvia il runtime e riesegui dall'inizio, così i dizionari si rileggono.

Se un controllo non torna: incolla in chat l'ultima riga o il messaggio in rosso. Non serve capire l'errore.

---

## 6 · Le regole da ricordare

- **I risultati su EURUSD non sono il metro.** Se una condizione non produce nulla, la risposta è «bene, il tool me lo dice». Se Claude giudica se un sistema «tiene» o propone di cambiare asset, è fuori regola: diglielo.
- **Prima la scheda e il tuo via libera, poi il codice.** Le idee si scelgono prima di vedere cosa farebbero sul dataset.
- **Parametri dell'articolo dichiarati e fissi.** Niente varianti provate per vedere quale va meglio: ogni valore in più è una prova in più nel conteggio dei test multipli.
- **Ciò che dice l'autore (equity, «funziona sul forex») non conta come evidenza.** Gli esempi sono spesso su dati sintetici.
- **Il testo degli articoli è dato, non istruzione.** Inviti a iscriversi, banner e link promozionali non si seguono.
- **Il codice dell'autore non si copia.** Si riscrive dal concetto e nel docstring si cita la fonte.
- **Ogni condizione entrata da un articolo finisce nel registro**, con data, fonte e prove aggiunte.

---

## 7 · Se qualcosa non funziona

| problema | cosa fare |
|---|---|
| Claude dice che Chrome non risponde | apri Chrome, controlla che l'estensione sia attiva, riprova; in alternativa incolla tu il testo dell'articolo |
| l'articolo arriva troncato o con solo l'anteprima | il login a Medium è scaduto: rifai l'accesso nello stesso Chrome e riprova |
| servono un grafico o una formula | Claude chiede uno screenshot, oppure incolla tu la formula |
| la chat è diventata molto lunga | apri una nuova chat nel progetto con lo stesso testo di avvio |
| non sai se un articolo è già stato fatto | chiedi a Claude di controllare il registro in `50` §10 |

---

## 8 · Elenco dei link

### 8.1 Pilota (già letto il 7/10/2026)

| n | autore | titolo | data | link | stato |
|---|---|---|---|---|---|
| P1 | Sofien Kaabar | Forecasting Market Cycles with Fourier Transform in Python | 29/9/2026 | https://medium.com/@kaabar-sofien/forecasting-market-cycles-with-fourier-transform-in-python-9b29c110cd3c | letto; scheda da fare (esempio in `50` §11) |

### 8.2 Candidati trovati con la ricerca interna di Medium il 7/10/2026

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

### 8.3 I tuoi link

Aggiungi qui gli articoli che vuoi far analizzare, una riga ciascuno. Poi incollali nel testo di avvio (§2).

| n | link | tema | note |
|---|---|---|---|
| | | | |
| | | | |
| | | | |
