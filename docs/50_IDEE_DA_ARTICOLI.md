# 50 · Idee da fonti testuali — come trascriverle in condizioni
 
**Data:** 7 ottobre 2026 (registro aggiornato l'8/10, il 15/10 e il 17/10 con AlgoXplorer in §10 quinquies e il VSA Modulo Unico in §10 sexies, filtro di sentiment F36 in §10 ter, multi timeframe in §10 quater; regola dei setup composti in §4 e riordino del 9/10; **il 10/10 fuso con l'ex `51_CONSEGNA_A_PARTI_E_REGISTRO_REGIME.md`**)
**Stato:** metodo concordato con Mattia; esteso il 7/10 da articoli a **video YouTube (trascrizione incollata da Mattia) e libri**. Al 10/10/2026 trascritti 9 articoli (7 con candidate nel catalogo), **17 prove**: vedi il registro in §10. L'esempio guidato del primo articolo (Fourier, Kaabar) resta in §11. Repo di destinazione predefinito: V4 (confermato il 7/10).
**Fusione con 51 (10/10/2026):** il documento `51` di allora (consegna "a parti", registro dei filtri di regime, lavoro in locale) è entrato qui e non esiste più; l'attuale `51_INDICATORI_TRADINGVIEW.md` è un documento diverso, del 13/10. Dove i due documenti dicevano cose diverse valeva il 51, e qui è già applicato: regola di consegna in §9, registro in §10, filtri di regime in §10 bis, lavoro in locale con Claude Code in §12.
**Nota sul nome:** il file resta `50_IDEE_DA_ARTICOLI.md` perché altri documenti lo citano; vale per qualunque fonte testuale.
**Prima di questo:** `00_SCOPO_E_STATO.md`, `02_KPI_E_GIUDIZIO.md`, `20_CONDIZIONI_TEMPO.md`, `21_COLLAUDO_CATALOGO.md`
**Guida operativa:** `docs/GUIDA_ANALISI_FONTI.md`, con i passi pratici per articoli, video e libri ed elenco dei link da leggere.
**Codice:** nessuno qui. Le funzioni stanno sul repo (regola di `00`); qui ci sono il metodo, le convenzioni e il registro delle idee.
 
---
 
## 0 · A cosa serve, e le regole che vengono prima
 
Le fonti testuali sono una **fonte di idee per allargare il catalogo**: trigger, filtri, uscite. Le fonti ammesse:
 
| fonte | come arriva il testo | affidabilità del testo |
|---|---|---|
| articolo (Medium, TradingView, blog) | letto con Claude in Chrome, o incollato da Mattia | alta: testo scritto, spesso con codice |
| video YouTube | **trascrizione estratta e incollata da Mattia** | media-bassa: parlato, trascrizione automatica con errori su nomi e numeri, regole spesso vaghe |
| libro | capitoli o estratti dati da Mattia (PDF, testo incollato) | alta sul concetto; le regole possono riferirsi ad altri mercati e timeframe |
 
Il tool serve a collaudarle, non a confermare quello che l'autore sostiene.
 
- **La fonte dà l'idea, l'evidenza la dà il tool.** Quello che l'autore dice di aver ottenuto (equity, «funziona sul forex», backtest, percentuali di vittoria) non si riporta e non pesa nella scelta. Spesso gli esempi sono su dati sintetici o scelti col senno di poi: il ciclo c'è perché l'ha inserito l'autore, il grafico del video mostra i casi che hanno funzionato.
- **Vale la regola di `00`.** I risultati su EURUSD non sono il metro. L'unico giudizio ammesso riguarda la trascrizione: è causale? non degenera? non è un doppione? i parametri sono dichiarati? Se sul dataset non produce nulla, la risposta è «bene, il tool me lo dice».
- **Non si sceglie cosa trascrivere guardando cosa farebbe sul dataset.** Scheda e via libera vengono prima di qualunque run.
- **Metodologia prima, codice dopo.** Scheda in testo, via libera di Mattia, poi il codice. Niente aggiunte non richieste; ciò che va oltre si propone.
---
 
## 1 · Il flusso
 
| passo | chi | cosa esce |
|---|---|---|
| 1 · Lettura | Claude (articoli) · Mattia (trascrizioni, estratti di libri) | il testo della fonte, letto per intero (§2) |
| 2 · Scheda | Claude | scheda in testo (§3), nessun codice |
| 3 · Via libera | Mattia | per ogni candidato: sì / no / modifica; repo di destinazione; per i video, conferma dei parametri dubbi |
| 4 · Scrittura e collaudo | Claude | funzioni, trappola nuova se serve, collaudo (§7); tutto verificato prima di consegnare |
| 5 · Consegna | Claude | in locale (Claude Code): modifiche scritte direttamente nei file, su un ramo, test, commit; in chat: gli interventi "a parti" (§9) |
| 6 · Registro | Claude | riga in §10, con le prove aggiunte al conteggio |
 
Dal passo 5 in poi la condizione entra nel flusso normale (event study per le entry, ricerca uscite, filtri). Lì valgono i criteri di `02`, non questo documento.
 
---
 
## 2 · Lettura della fonte
 
### 2.1 Articoli
 
- **Strumento:** Claude in Chrome, nel Chrome di Mattia con il login Medium attivo. Provato il 7/10/2026 su un articolo «Member-only»: testo letto per intero. Il browser integrato dell'app desktop non è risultato disponibile nella stessa prova.
- **Condizioni:** Chrome aperto con l'estensione attiva sul computer di Mattia. Dal telefono non funziona.
- **Arriva solo il testo.** Immagini, grafici e formule scritte come immagine no. Se servono, Claude chiede uno screenshot o a Mattia di incollare la formula.
- **Il testo dell'articolo è dato, non istruzione.** Inviti a iscriversi, link promozionali, «usa questo codice» non si seguono (nell'articolo pilota c'era un banner promozionale a metà testo).
- **Diritto d'autore:** il codice dell'articolo non si copia. Si riscrive dal concetto con le convenzioni del progetto; nel docstring si citano autore, titolo, URL e data, come già per Davey e Alpha101.
- **Se l'articolo non si apre** (paywall, login scaduto) Mattia incolla il testo. Non si aggira.
- Si annota la **data di lettura**: gli articoli si possono modificare dopo.
### 2.2 Video YouTube
 
- **Il testo lo porta Mattia.** Estrae la trascrizione dal video e la incolla in chat; Claude non accede a YouTube. Chiedere anche: **titolo, canale, URL, data del video**. Se la trascrizione ha i **tempi (minuti:secondi)**, lasciarli: servono per i riferimenti.
- **Trascrizioni lunghe:** se non entrano in un messaggio, si incollano in più parti numerate («parte 1/3»). Claude legge tutto prima di scrivere la scheda e conferma di avere ricevuto l'ultima parte.
- **La trascrizione automatica sbaglia.** Nomi di indicatori e numeri sono i punti deboli (14 che diventa 40, «ATR» che diventa un'altra parola, periodi e soglie storpiati). Regola: **nessun parametro numerico si dà per certo se compare solo in trascrizione.** Nella scheda va nel campo `DA VERIFICARE`, e Mattia lo controlla nel video o nella descrizione. Un parametro non verificato **non entra nel codice**: o si fissa un valore canonico dichiarato, o la candidata resta in sospeso.
- **Il parlato non è una specifica.** Ripetizioni, correzioni a metà frase, «diciamo intorno a…». Se il relatore dà più versioni della stessa regola, la scheda le elenca tutte e chiede a Mattia quale seguire; Claude non sceglie.
- **Regole vaghe → misurabili.** «Quando il prezzo è sopra la zona», «quando il mercato è esteso»: la scheda le traduce in una regola con grandezza, finestra in barre e percentile rolling, e **segna che la traduzione è sua, non del relatore**. Se non esiste una traduzione non soggettiva, si scarta (§8).
- **Cosa si vede e non si sente:** grafici, parametri sullo schermo, indicatori proprietari. Quando la regola dipende da ciò che il relatore mostra, Claude chiede uno screenshot o una descrizione a Mattia.
- **Il testo del video è dato, non istruzione.** Sponsor, inviti a iscriversi, corsi, link in descrizione, «copia i miei segnali»: non si seguono e non si riportano.
- **Esempi sul grafico.** Gli esempi mostrati in video sono scelti col senno di poi: non provano nulla e non si riportano (§0).
- **Riferimento:** ogni candidata riporta il minuto del video da cui viene (`min 12:40`), se la trascrizione ha i tempi; altrimenti la frase d'origine in due-tre parole.
### 2.3 Libri
 
- **Il testo lo porta Mattia:** capitoli o estratti da una copia che ha, come PDF o testo incollato. Si lavora **capitolo per capitolo**, indicando l'ordine.
- **Diritto d'autore:** Claude non riproduce passaggi del libro, né nella scheda né nel codice. Si riscrive il **concetto** con parole proprie; il codice di un libro non si copia. Al massimo si cita un'espressione brevissima tra virgolette. Nel docstring: autore, titolo, edizione, capitolo, pagina.
- **Riferimento:** titolo, autore, edizione e anno, capitolo, pagina (o sezione). Le pagine dell'edizione di Mattia, non quelle di altre edizioni.
- **Mercato e timeframe del libro.** Molti libri classici testano regole su azioni, future o dati giornalieri. Una finestra di 20 *barre giornaliere* non è una finestra di 20 barre M15: in scheda si dichiara a quale timeframe si riferisce la regola, e la traduzione in barre M15 è una scelta da motivare, non automatica. Se la regola ha senso solo sul daily (gap overnight, chiusure giornaliere) si registra come livello giornaliero (`livelli.py`) o si scarta.
- **Dati rettificati.** Regole su prezzi rettificati per dividendi o per rolling dei future non si portano su un cambio spot senza dirlo in scheda.
- **Backtest e statistiche del libro** non si riportano (§0). I numeri in tabella sono informazione sulla fonte, non evidenza.
- **Doppioni più probabili.** I libri descrivono spesso indicatori e pattern classici già nel catalogo: il controllo di sovrapposizione (§7, punto 5) si fa prima, e la scheda lo scrive.
---
 
## 3 · La scheda della fonte (modello)
 
Una per fonte (o per capitolo, nei libri), in testo. È il documento su cui Mattia decide.
 
```
FONTE        tipo (articolo / video / libro)
             articolo: autore · titolo · URL · data articolo · data di lettura
             video:    canale · titolo · URL · data video · data di ricezione trascrizione
             libro:    autore · titolo · edizione e anno · capitolo
RIFERIMENTO  articolo: paragrafo o sezione · video: minuti · libro: pagina
AFFIDABILITÀ DEL TESTO   alta / media-bassa, con il motivo (es. trascrizione automatica)
IDEA         due righe, con parole nostre
GRANDEZZA    cosa misura; su che dati la fonte l'ha provata (solo informativo)
CANDIDATI    per ciascuno:
             - tipo: entry long / entry short / filtro / uscita a regola
             - nome proposto (numero, vedi §5)
             - direction e pair (filtri e uscite)
             - cosa restituisce, in una frase
             - parametri: valore fisso scelto a priori, e perché
             - finestra massima in barre (serve al riscaldamento)
             - indicatori nuovi richiesti
             - riferimento (minuto o pagina)
             - traduzione nostra? sì/no (sì se la regola della fonte era vaga o discrezionale)
LOOKAHEAD    dove la fonte guarda al futuro (§6), voce per voce, e come si evita
DA VERIFICARE   numeri e nomi dubbi (trascrizioni), timeframe e mercato della regola (libri)
PROVE        quante candidate entrano nel conteggio dei test multipli
DOPPIONI     condizioni del catalogo con cui si sovrappone probabilmente
DECORRELAZIONE  dopo il collaudo: in quale famiglia cade (engine/famiglie.py) e la
             condizione più vicina, con la somiglianza; «famiglia nuova» se apre
             un'idea che nel catalogo non c'è (regola del 17/10/2026, §7 punto 5)
SCARTATI     pezzi della fonte lasciati fuori, con il motivo (§8)
DECISIONE    sì / no / modifica, per candidato — la prende Mattia
REPO         dove va la condizione (default: V4, confermato da Mattia il 7/10)
```
 
I pezzi scartati si registrano come in `20` («Scartati in questo giro, e perché»): restano riaggiungibili se cambia la regola che li ha esclusi.
 
---
 
## 4 · Dove va ogni idea
 
| la fonte descrive | va in | note |
|---|---|---|
| un **evento**: incrocio, rottura, inversione di segno, pattern che si completa | **entry** | long e short separate, scritte come evento (`_evento`) |
| uno **stato**: regime, contesto, «mercato esteso», trend / non trend, volatilità alta | **filtro** | vero su più barre di seguito |
| una **grandezza continua** (Hurst, entropia, forza del ciclo, pendenza) | **filtro**, dopo averla trasformata in stato con un percentile rolling; oppure **entry** se la regola è «supera il percentile» | senza una regola di trasformazione non è ancora una condizione |
| una **previsione** | il segno della previsione, calcolata solo sul passato, a un orizzonte dichiarato: **entry** se è il cambio di segno, **filtro direzionale** se è lo stato | |
| una regola per **chiudere** (indicatore opposto, inversione) | **uscita a regola**: `df -> Series bool`, «chiudi il long» | |
| uno **stop** o un **target** | non è una condizione: li ricava il tool con i percentili adattivi (`soglie_adattive`) | si annota come idea di uscita; stop e target non si ottimizzano (`00`, il metodo, passo 3) |
| un'uscita **a tempo** | non è una condizione: è `n_barre` (o `n_barre_long` / `n_barre_short`) | |
| sizing, gestione del rischio, portafoglio | fuori dal catalogo | passo 7 (money management, `61`) o livello portafoglio |
| un **setup composto**: segnale + conferme in AND («segnale BUY + candela precedente verde + IIX positivo») | **una entry sola**, con tutte le condizioni sulla stessa barra | regola del 9/10/2026, sotto |
 
### Setup composti (regola del 9/10/2026)
 
**Un setup che la fonte descrive come AND di più condizioni si trascrive come UNA entry sola: l'AND è l'ipotesi dell'autore.** Le parti diventano filtri separati solo se la fonte le usa anche da sole.
 
Perché (scoperto l'8-9/10, articoli 2 e 3 del registro):
- l'event study misura il trigger da solo: il segnale «nudo» è un'altra ipotesi, più povera, e se non regge da solo viene scartato prima che le conferme vengano mai provate;
- la ricerca dei filtri prova **un'idea alla volta** (`filter_search_bt.py`): un setup a tre pezzi (segnale + due conferme) come unità non verrebbe mai provato;
- le parti estratte diventano filtri generici («due candele verdi», «IIX positivo») provati su ogni trigger del catalogo: più prove, ipotesi più povere.
Come si scrive:
- tutte le condizioni **sulla barra del segnale**, come le scrive la fonte («candela del segnale», «candela precedente»); se una conferma manca su quella barra non c'è ingresso: non si aspettano conferme arrivate dopo, a meno che la fonte lo dica;
- lo short è lo speculare **come lo scrive la fonte**, anche quando non è simmetrico (es. PVO rosso sullo short di E25);
- nel docstring l'elenco numerato delle condizioni, come nella fonte;
- gli indicatori delle conferme restano colonne in `engine/indicatori.py`;
- un setup completo conta come **una prova per lato**, come un'OR composita (§8);
- il trigger «nudo» non si tiene accanto al setup come paragone, salvo decisione di Mattia (costa 2 prove);
- prima di scrivere, si contano le occorrenze del setup completo: sotto circa 100 si scarta (§8).
### Entry
- Sempre un **evento** (transizione), mai uno stato. Un'entry vera su barre consecutive è un errore di scrittura (`STATO` in `verifica_degenerazione`).
- Long e short sono **candidati separati** fino alla validazione; possono non essere speculari.
- Una versione «confermata» (pattern + una barra dopo) coincide per costruzione con la base: la si aggiunge solo se Mattia lo decide.
### Filtri
Le quattro regole del passo 5 (`00`, il metodo):
1. `direction=0` solo se usa davvero la sola magnitudo, mai il segno di una grandezza con segno.
2. La finestra del percentile rolling dev'essere molto più larga della finestra del valore che classifica.
3. Mai un filtro in OR su due rami opposti: si tengono separati, uno per direzione.
4. Nessun filtro sempre vero o sempre falso.
Un filtro direzionale ha il suo speculare con lo stesso `pair`; un filtro neutro non può avere `pair`. Un filtro con senso economico spiegabile vale più di uno che si limita a stare in cima.
 
### Uscite a regola
Funzione `df -> Series bool`. Il motore esce all'Open della barra successiva al segnale. Se l'idea ha un lato speculare, i due lati condividono lo stesso `pair`.
 
---
 
## 5 · Convenzioni di scrittura
 
**Firma e registrazione** (verificate sul repo il 7/10):
 
| tipo | funzione | riga nel dizionario |
|---|---|---|
| entry long / short | `def entry_nome(df, **params) -> pd.Series`, ritorna `_evento(condizione)` | `TRIGGER_LONG` / `TRIGGER_SHORT`: `nome: funzione` |
| filtro | `def filter_nome(df, ...) -> pd.Series` (booleana) | `FILTRI`: `nome: (funzione, direction, pair)` |
| uscita a regola | `def exit_nome(df, ...) -> pd.Series` (booleana) | `EXIT_LONG` / `EXIT_SHORT`: `nome: (funzione, pair)` |
 
- **Per aggiungere una condizione servono due cose:** la funzione e la riga nel dizionario del suo file. La registrazione (`registra_trigger_long()`, `registra_filtri()`, `registra_exit_long()` e simili) è esplicita, idempotente, e salta i nomi già registrati.
- Un *file* di condizioni nuovo va aggiunto anche alla lista `REGISTRAZIONI` di `Collaudo_Catalogo.ipynb`.
- **Indicatori nuovi** in `engine/indicatori.py` (`aggiungi_indicatori`), mai nel notebook: altrimenti il collaudo non li ricalcola e non vede un lookahead dentro l'indicatore.
- **Nomi:** `E<n>_NOME` per le entry (lo short porta `SHORT` nel nome, il long no: `E22_ASIAN_RANGE_BREAKOUT`, `E22_SHORT_ASIAN_RANGE_BREAKDOWN`), `F<n>_NOME` per i filtri, `X<n>_NOME` per le uscite. Il numero è il successivo a quello in uso **nel file del repo di destinazione**. Al 5-6/10 il repo V4 e il ramo ML (`Trading-System-Pipeline-ML`) risultano con numerazioni diverse, perché il ramo ML è stato riordinato il 1/10 (`32`). Si legge l'ultimo numero dal file, non da questo documento.
- **Parametri.** Ogni valore di parametro è una prova in più nel conteggio dei test multipli (`20`, convenzione 1).
  - Si prende il valore canonico della fonte, lo si dichiara nella scheda e **non si provano varianti** per vedere quale va meglio. Il «migliore» della fonte è spesso già una scelta fatta guardando i dati.
  - Una famiglia di varianti conta come **una candidata** con parametro fisso.
  - Soglie assolute (RSI 70/30 e simili) → percentile rolling, finestra molto più larga (`learnings`: auto-adattivo, nessuna calibrazione che invecchia).
  - Nessun buffer inventato (`massimo + 0,3 ATR`).
  - **Nessun parametro numerico preso da una trascrizione non verificata** (§2.2).
- **Riscaldamento.** Un confronto con NaN dà False, non NaN: le prime barre hanno la condizione falsa per mancanza di storia. Ogni condizione dichiara la sua finestra massima; dove c'è il taglio del riscaldamento (ramo ML: `RISCALDAMENTO = 2100`, dettato da E7 su 2000 barre) va **alzato se la nuova finestra è più lunga**.
- **Tempo.** Se l'idea usa sessioni, giorni o finestre orarie: `engine/sessioni.py` e `engine/livelli.py`, e le cinque trappole di `20` (giornata con `giorno_fx()` e mai `df.index.date`; grandezza fotografata davvero; finestra che finisce a mercato chiuso).
- **Quarantena.** Per le entry la maschera sugli ingressi sta nei motori dal 5/10 (`93`, `quarantena=True` di default): non si duplica nella condizione. Per filtri e uscite, e per i livelli calcolati da prezzi, si verifica caso per caso se le barre in quarantena (bid deformato nel rollover) entrano nel calcolo.
- **Modifiche additive.** Quando non è possibile, si dichiara.
- **Unità:** costi in pips, non in bp; se serve la conversione si esplicita. Il pip è **fisso per symbol** e viene da `engine/simboli.py` (dal 10/10, §12): mai dedurlo dal prezzo.
- **Docstring:** una riga che dice cosa fa, più la fonte: articolo (autore, titolo, URL); video (canale, titolo, URL, minuto); libro (autore, titolo, edizione, capitolo, pagina).
- **Segno nell'event study:** sempre dal punto di vista del trade, mai del prezzo (per uno short un calo del prezzo è un guadagno). Vale anche per le condizioni nuove.
---
 
## 6 · Le trappole di lookahead tipiche delle fonti
 
Gli esempi degli articoli sono scritti per mostrare un'idea, non per girare in tempo reale: molti usano tutto il campione. Video e libri aggiungono altre forme (ultime righe della tabella). Questa tabella è la lista da controllare nella lettura (e da riportare nella scheda).
 
| forma nella fonte | perché guarda al futuro | come si trascrive |
|---|---|---|
| `rolling(center=True)`, filtri non causali (Savitzky-Golay, gaussiano, Hodrick-Prescott, LOWESS, `filtfilt`, smoother di Kalman) | il valore a *t* usa barre dopo *t* | versione in avanti: EMA, filtro di Kalman solo forward, `lfilter` |
| scomposizioni o ricostruzioni sull'intero campione (FFT e inversa, wavelet, EMD, PCA, SVD) | il punto ricostruito a *t* dipende da tutta la serie | finestra mobile **solo sul passato**, si tiene solo l'ultimo punto; attenzione all'effetto di bordo |
| z-score, min-max, scaler, percentili calcolati su tutto il campione | media e deviazione includono il futuro | rolling o expanding |
| pivot, zigzag, swing high/low, `find_peaks`, `argrelextrema`, frattali (barre a destra) | un massimo si conferma solo con barre successive | il segnale esiste dalla barra di **conferma**, non da quella del pivot |
| etichette e target (`shift(-n)`, `pct_change(-n)`) rimasti nel segnale | il segnale conosce l'esito | via dal segnale: l'esito lo misura il tool, non la condizione |
| modelli di regime addestrati sul campione intero (HMM con Viterbi, GMM, k-means, regressioni, rilevamento di punti di cambio) | l'etichetta a *t* è stimata guardando tutta la sequenza | stima sul passato (filtering, non smoothing), rifit periodico |
| `bfill`, interpolazione bidirezionale, `resample` con etichetta a destra, unione di timeframe superiori | la barra superiore non è ancora chiusa | `shift(1)` e allineamento alla candela **chiusa** |
| High / Low / Close del giorno corrente usati durante il giorno | il massimo giornaliero si conosce a fine giornata | livello della giornata FX **precedente** (`livelli.py`) |
| parametri ottimizzati sul campione nella fonte | il valore «migliore» è già informazione dai dati | valore canonico dichiarato a priori (§5) |
| rank cross-sectional (richiede un universo di asset) | non portabile su un asset solo | `ts_rank`, percentile rolling sulla storia del singolo asset |
| volume reale, order book, dati fondamentali | non li abbiamo su MT5 | scartare (§8); su MT5 c'è il tick volume |
| **video/libro:** supporti, resistenze, zone, trendline, canali «tracciati a occhio» | la zona si disegna guardando cosa è successo dopo | solo se ridefinibile in modo causale (livello da pivot confermato dopo N barre, massimo/minimo rolling); altrimenti scarto (§8) |
| **video/libro:** pattern o fasi di mercato riconosciuti sul grafico a posteriori («qui si vede l'inversione») | l'etichetta è data con il senno di poi | si cerca la regola che il relatore applicherebbe **in tempo reale**; se non c'è, scarto |
| **video/libro:** esempi scelti sul grafico, «guardate quanti casi hanno funzionato» | selezione dei casi favorevoli, nessun conteggio dei fallimenti | l'esempio non è evidenza (§0) e non si riporta |
| **libro:** regola scritta per il daily o per un altro mercato | la finestra in barre cambia significato su M15; gap, chiusure e dividendi non esistono uguali sul cambio | dichiarare il timeframe d'origine; riscrivere in barre M15 solo con motivazione, oppure livello giornaliero (`livelli.py`), oppure scarto |
| **video:** parametro «sentito» (periodo, soglia) | la trascrizione automatica storpia i numeri | `DA VERIFICARE` in scheda; non entra nel codice finché non è controllato (§2.2) |
 
**Entrata sulla stessa barra del segnale.** Molte fonti entrano alla chiusura della barra del segnale. Nel tool l'ingresso è all'Open della barra successiva: è una proprietà del motore (`lag=1`), non si modifica nella condizione.
 
---
 
## 7 · Il collaudo prima della consegna
 
Ogni condizione nuova passa tutto questo prima di arrivare a Mattia, con casi a risultato noto.
 
1. **Trappola nuova per ogni famiglia nuova** (sezione A1 del notebook di collaudo). Si costruisce la versione con il difetto tipico della fonte (es. FFT sull'intero campione) e si verifica che `verifica_lookahead` la segni `LOOKAHEAD`. Se non la vede, il test va rafforzato **prima** di fidarsi della versione corretta. Poi la versione corretta deve risultare `OK`.
2. **`verifica_lookahead`** (troncamento: lo storico si taglia alla barra *t*, si ricalcola da zero indicatori compresi, si confrontano tutte le barre fino a *t*). Esito atteso `OK`. `NON_ESERCITATA` non è una promozione: la condizione non era mai vera nel test. Si prova su una serie dove scatta, e con tagli sulle barre in cui la condizione è vera.
3. **`verifica_degenerazione`** su EURUSD vero (dal 10/10 si può fare anche sugli altri symbol di `dati/`, §12): copertura, eventi, `STATO`, `RARA`, `SEMPRE_VERA`. Sotto le 30 occorrenze (entry) o 30 barre vere (filtri e uscite) si segnala, non si promuove né si boccia.
4. **Casi a risultato noto:** serie costruite a mano su cui l'esito è noto (il trigger scatta sulla barra attesa; lo short è lo speculare del long; il filtro cambia stato dove deve).
5. **Sovrapposizioni con il catalogo:** `diagnostica.sovrapposizioni(df, colonne, finestra, soglia)` (repo ML), solo su `df_is`, filtri a finestra 0 e trigger a finestra 2, soglia 70. Una condizione contenuta al 70% o più in una già presente, o suo contrario esatto, è un doppione: non si aggiunge, a meno che Mattia lo decida. **Precisazione del 15/10/2026 (Mattia):** il 70% conta solo se è almeno **1,3 volte il caso**, cioè la quota contenuta divisa per la copertura della condizione già presente è ≥ 1,3. Contro filtri molto larghi (F2_MID, F22: 75–80% delle barre) il 70% si raggiunge per caso e non fa doppione. I doppioni si **spengono mettendo tra commenti la riga del dizionario** (come F27): la funzione resta, non si calcola, si riattiva togliendo il `#`. Funzione presente nel ramo ML dal 1/10; **nel repo V4 non esiste** (verificato il 9/10): il controllo si fa con uno script a parte, con le stesse regole.
   **Dal 17/10/2026 lo strumento c'è nel V4:** `engine/famiglie.py` (`sovrapposizioni`, `somiglianze`, `famiglie`, collaudo `test_famiglie.py`). Si passa l'in-sample di EURUSD, BTCUSD e DE40 come dizionario `{symbol: df_is}`: una coppia è doppione se la regola vale su **tutti** e tre. La **somiglianza** fra due condizioni è la quota più alta fra i due versi, contata solo se è almeno 1,3 volte il caso; le **famiglie** raggruppano le condizioni con somiglianza media **≥ 60%** (decisione di Mattia del 17/10/2026). Nella scheda (§3) la riga DECORRELAZIONE riporta la famiglia della condizione nuova: una condizione che apre una famiglia nuova porta informazione nuova; una che cade in una famiglia già piena va motivata, perché costa una prova e aggiunge poco. Usa solo i segnali, non i risultati dei trade: non conta come prova.
6. **Riscaldamento:** dopo il taglio, la colonna è identica a prescindere dal punto di partenza dei dati (come verificato il 28/9 per le 72 colonne E*/F*).
7. **Pandas 2.2 e 3.0:** stessi risultati con entrambe.
8. **Suite da terminale** del progetto e **`Collaudo_Catalogo.ipynb`** rilanciati: da rifare ogni volta che si aggiunge una condizione.
**Cosa il collaudo non copre:** l'ingresso a `Open[t+1]` (proprietà del motore); la quarantena sui filtri e sui livelli (da guardare caso per caso); la qualità economica della condizione (non è compito suo); i dati che arrivano già sbagliati da fuori; **la fedeltà della traduzione alla fonte**: per video e libri una regola vaga tradotta da noi può non essere quella del relatore, e il collaudo non lo sa. Per questo la scheda segna «traduzione nostra: sì» (§3).
 
**Lezione di `21`:** un test che tiene l'indice intatto non vede i difetti legati alla *fine* dello storico, che nel live è sempre la barra corrente. Per questo si tronca, non si sporca.
 
---
 
## 8 · Test multipli, doppioni e scarti
 
**Ogni condizione nuova è una candidata vera:** entra nel `k` della chiamata che la prova. Un filtro con `pair` vale una riga sola; un'OR composita conta come una prova, e così un setup composto in AND (§4), per lato. Le entry-metro non contano.
 
**Le prove di chiamate diverse non si sommano** (limite noto in `00`, punto 3): ogni soglia di rumore è un pavimento. Per questo il registro (§10) tiene il conto delle candidate entrate da fonti testuali, con data e fonte. **Una traduzione di regola vaga conta come candidata come le altre**; se Mattia chiede due traduzioni alternative della stessa regola, sono due prove.
 
**Si scarta subito, con motivo scritto nella scheda:**
- richiede il futuro in modo non eliminabile (il target dentro il segnale);
- richiede dati che non abbiamo (volume reale, order book, fondamentali, altri asset);
- non è codificabile senza una scelta soggettiva (trendline a mano, conteggi d'onda discrezionali, zone «a occhio» non ridefinibili in modo causale);
- troppi parametri liberi e nessun valore canonico dichiarato;
- parametri chiave presenti solo in una trascrizione e non verificabili;
- regola legata a un timeframe o a un mercato non portabile (es. gap overnight su un cambio 24 ore);
- doppione (§7, punto 5);
- sotto circa 100 occorrenze attese;
- sempre vera o sempre falsa su dati sintetici;
- richiede un rank cross-sectional senza equivalente su un asset solo.
Gli scarti non sono giudizi sull'idea: sono limiti del tool o del dato di oggi, e si registrano per poterli riaprire.
 
---
 
## 9 · Consegna e come si esegue (per Mattia)
 
Regola del 9/10/2026, su richiesta di Mattia (ex `51`, §1). Dal 10/10 ci sono due modi di lavorare.
 
### 9.1 · In locale con Claude Code (il modo normale dal 10/10)
 
Claude Code **scrive le modifiche direttamente nei file** del repo clonato sul PC di Mattia (§12):
- un **ramo per argomento**, mai direttamente su `main`;
- prima di ogni commit lancia **tutti** i `test_*.py`: l'ultima riga di ognuno dev'essere `RISULTATO: n/n test superati`; se un test fallisce si ferma e spiega;
- commit con messaggio chiaro in italiano; mai `--force`; nessun file cancellato senza chiedere;
- invio del ramo su GitHub (Publish Branch, o `git push` con GitHub CLI) e Pull request; **il Merge lo fa Mattia** su GitHub.
La regola "a parti" qui sotto **non si applica** al lavoro in locale.
 
### 9.2 · In chat: consegna "a parti"
 
**Non si riscrive il file intero.** Per ogni file già esistente nel repo Claude consegna:
- il blocco di codice da aggiungere o sostituire;
- **dove** va (il nome del file, la riga o la funzione "subito prima / dopo", con l'indentazione);
- se è una sostituzione, la riga vecchia da cercare e quella nuova.
Il **file intero** si consegna solo (a) se è un file nuovo (es. `test_*.py`), (b) se le modifiche sono così sparse che le parti sarebbero più rischiose del file. In questo caso Claude lo dice e ne spiega il motivo.
 
Ogni consegna include sempre, per un lettore non informatico: l'elenco numerato degli interventi, il comando per eseguire i test, l'ultima riga attesa (`RISULTATO: n/n test superati`) e cosa fare se il numero non torna (incollare l'output, non modificare niente). Le celle di notebook si danno come testo, ciascuna con una cella markdown breve davanti (cosa fa, come leggere l'output, cosa fare dopo).
 
### 9.3 · Come si esegue (in entrambi i modi)
 
1. Applicare gli interventi (in chat) o verificare che siano nel ramo (in locale), poi lanciare i test dal terminale **nella cartella del progetto**: `python test_nome.py`. Su Windows con `PYTHONIOENCODING=utf-8`, altrimenti la console si ferma su alcuni caratteri. L'ultima riga attesa è nel formato `RISULTATO: n/n test superati`; con meno del totale, copiare qui il messaggio.
2. Rilanciare **`Collaudo_Catalogo.ipynb`** su Colab: *Runtime → Esegui tutto*, 2–3 minuti. Attesi: A1 e A2 con tutte le prove superate (il totale sale quando si aggiungono trappole), B con **0 LOOKAHEAD e 0 ERRORE**, D e E superate. La sezione C è una tabella da leggere, senza promosso o bocciato.
3. Nel notebook principale la condizione compare da sola dopo la registrazione (riavviare il runtime e rieseguire dall'inizio, così i dizionari si rileggono).
Per ogni consegna Claude dice **quali di questi passi servono** e cosa deve vedere Mattia alla fine di ciascuno.
 
---
 
## 10 · Registro delle idee
 
Una riga per fonte (nei libri, per capitolo). Serve a due cose: sapere cosa è già stato provato (niente doppie letture) e tenere il conto delle prove entrate da fonti testuali, che il tool non somma.
 
| n | tipo | letto il | fonte | idea | candidati (tipo, nome) | scheda | collaudo | nel catalogo | prove aggiunte |
|---|---|---|---|---|---|---|---|---|---|
| — | articolo | prima del 7/10 | Velasquez, automazione dei pattern candlestick con TA-Lib | pattern candlestick | entry E* candlestick del catalogo | anteriore al registro | — | sì | non contate qui |
| 1 | articolo | 7/10/2026 | Kaabar, «Forecasting Market Cycles with Fourier Transform in Python», 29/9/2026 | ciclo dominante con FFT su finestra mobile di 300 barre (sui rendimenti, banda 10–150, una armonica) | filtro F23_CYCLE_STRENGTH; entry E24_CYCLE_TURN_UP / E24_SHORT_CYCLE_TURN_DOWN; uscite X1_CYCLE_TURN_DOWN / X1_SHORT_CYCLE_TURN_UP (al posto di X1 RSI) | approvata 7/10 (no al filtro direzionale F24_CYCLE_RISING/FALLING) | superato 7/10 (anche sul repo: A1 28/28, B 0 lookahead) | sì | 5 |
| 2 | articolo | 7/10/2026 | Sayedali Richu, «Want to Find Better Trading Opportunities? Start With These 2 Indicators», 24/9/2026 | canale di trend adattivo (script MarketStructureLab, CC BY-NC-SA 4.0) + due candele + PVO | **dal 9/10:** setup completo E25_ATC_PVO_SETUP_UP / E25_SHORT_ATC_PVO_SETUP_DOWN (canale che cambia colore + candela del segnale e precedente dello stesso colore + PVO verde/rosso); coppia F24_TWO_BARS_UP / F24_TWO_BARS_DOWN (era F26). Tolti il 9/10: E25 solo canale, filtri PVO F24/F25 | approvata 7/10; rivista il 9/10 (regola §4) | superato 7/10 e 9/10 | E25 setup consegnato 9/10; F24 sì | 3 (erano 5) |
| 3 | articolo | 8/10/2026 | Sayedali Richu, «My Simple Formula for Filtering Intraday Buy & Sell Signals», 27/9/2026 | Supertrend 10/3 + candela precedente + Intraday Intensity a 21 barre (script KIVANÇ) | **dal 9/10:** setup completo E26_SUPERTREND_IIX_SETUP_UP / E26_SHORT_SUPERTREND_IIX_SETUP_DOWN. Tolti il 9/10: E26 solo Supertrend, filtro IIX F27 | approvata 8/10; rivista il 9/10 (regola §4) | superato 8/10 e 9/10 (E25 ed E26 long entro 2 barre da E3 short all'83% e 87%: da decidere) | consegnato 9/10 | 2 (erano 3) |
| 4 | articolo | 8/10/2026 | PyQuantLab, «Volume Spread Analysis (VSA) Strategy: Quantifying Market Action for Trading Signals with Rolling Backtesting», 20/6/2025 | figure VSA (volume, ampiezza, chiusura nella barra, trend), senza il punteggio di contesto | entry E27_VSA_BULLISH / E27_SHORT_VSA_BEARISH (già setup composti: figure in AND); uscite X2_VSA_BEARISH / X2_SHORT_VSA_BULLISH (al posto di X2 EMA) | approvata 8/10 (parametri del giornaliero tenuti in barre su M15) | superato 8/10 | sì | 4 |
| 5 | articolo | 9/10/2026 | PyQuantLab, «Can We Detect a Market Crash Before It Happens? I Tested 5 Regime Filters», 7/9/2026 | Choppiness Index (14 barre, standard di Dreiss, non il 7 dell'articolo) + stato con isteresi (si accende al 25° percentile, si spegne sopra il 50°) | filtri F25_CHOP_TREND, F25_CHOP_RANGE (neutri) | approvata 9/10 | superato 9/10 (`test_regime.py`) | sì | 2 |
| 6 | articolo | 9/10/2026 | PyQuantLab, «Enhancing Trading Strategies With a Hurst-Based Regime Filter», 6/3/2026 | persistenza del prezzo come filtro; l'esponente di Hurst (R/S per barra, pesante e rumoroso) sostituito col **variance ratio** di Lo–MacKinlay (orizzonte 4, finestra 192) | filtro F26_VARIANCE_RATIO_TREND (neutro) | variante approvata da Mattia 9/10 | superato 9/10 | sì | 1 |
| 7 | articolo | 9/10/2026 | PyQuantLab, «Regime Filtered Trend Strategy», 12/7/2025 | voto fra misure di regime | idea del voto riusata in F27_REGIME_TREND_COMPOSITE (almeno 2 voti su 3: CHOP-tendenza, VR-persistenza, ADX alto) | **opzionale**: riga nel dizionario commentata (rimessa commentata il 10/10: nel repo era attiva) | superato 9/10 | no (spento) | 0 (+1 se attivato) |
| 8 | articolo | 9/10/2026 | Kaabar, VA-RSI (Volatility-Adjusted RSI), Medium/Coinmonks | RSI aggiustato per volatilità | — | **messo da parte** (non scartato): troppo reattivo; la EMA di lisciatura aggiungerebbe ritardo su ritardo | — | no | 0 |
| 9 | articolo | 9/10/2026 | articolo Mellin (trasformata) | — | — | scartato: FFT per barra, nessuna regola in condizione | — | no | 0 |
| 10 | script TradingView | 13–15/10/2026 | 7 script della community (`51_INDICATORI_TRADINGVIEW.md`): VFI, Squeeze Momentum, WaveTrend di LazyBear; Relative Volume di veryfid; KER di Zorba_the_Buddha; Hurst di PhenLabs (CC BY-NC-SA, uso personale); filtri MLExtensions di jdehorty | traduzione riga per riga del Pine, fedeltà verificata con PineTS | entry E28 (VFI), E29 (squeeze), E30 (WaveTrend a percentile); filtri F28 (VFI, coppia), F29_RVOL_LOW, F32_KER_RANGE, F33 (Hurst ×2), F35 (regime jdehorty). **Spenti come doppioni:** F29_RVOL_HIGH, F30, F31, F32_KER_TREND, F34 | piano approvato il 13/10, scelte del 13–15/10 (`51` §7.1) | superato 15/10 (`test_indicatori_tradingview.py` 143/143) | sì | 12 (+5 se si riattivano i doppioni) |
| 11 | concetto (indice esterno) | 15/10/2026 | Crypto Fear & Greed Index di alternative.me (https://alternative.me/crypto/fear-and-greed-index/), solo come **idea**: formula, dati e nome non usati, codice nostro senza licenze di terzi (prodotto commerciale) | sentiment giornaliero dai soli prezzi e tick volume: 4 componenti (volatilità, drawdown, momentum, volume con segno) a 30 giorni, percentile a 365 giornate, punteggio 0–100 e 5 quintili; aggiornato a fine giornata FX, ogni barra vede solo l'ultima giornata chiusa | filtri F36_SENT_EXTREME_FEAR (+1) / F36_SENT_EXTREME_GREED (−1), coppia SENTIMENT, **contrarian** (paura sul long); colonne `sentiment_score`, `sentiment_classe` | approvata 15/10 (solo la versione contrarian; no versione momentum e no filtro neutro) | superato 15/10 (`test_sentiment.py` 53/53) | sì | 1 |
| 12 | ricerca (libro, paper, articolo) | 15/10/2026 | multi timeframe: Elder, «Trading for a Living», Wiley 1993, cap. 43 (Triple Screen, pp. 235–243); Hurst, Ooi, Pedersen, «A Century of Evidence on Trend-Following Investing», JPM 2017; LuxAlgo, «The Strat» (Rob Smith) | candele superiori H1/H4/giorno/settimana/mese costruite dalle M15 (H4 ancorato alle 17:00 NY), lette solo se chiuse; continuità dei timeframe; Triple Screen H4/H1/M15 con Force Index; accordo di 1, 5, 21 giornate; giorno inside | filtro F39_INSIDE_DAY (neutro); entry E31_TRIPLE_SCREEN_UP / E31_SHORT_TRIPLE_SCREEN_DOWN (setup unico, §4) | approvata 15/10 (B, C, D, F; no al filtro trend giornaliero e all'uscita); scelte su C e D in §10 quater | superato 15/10 (`test_multi_timeframe.py` 38/38) | E31, F39 sì; **F37 (coppia FTFC) e F38 (coppia TSMOM) spenti come doppioni** | 3 (+2 se si riattivano F37 e F38) |
| 13 | script TradingView (nostro) | 17/10/2026 | «AlgoXplorer 0.1c», indicatore Pine v5 scritto da Mattia e da un amico, uso concordato (sorgente in `pine_sources/`, non su GitHub) | candela PVSRA climax + chiusura Heikin Ashi oltre la EMA a 50 di massimi/minimi + rottura della candela HA precedente; segnali alternati Buy/Sell; ingresso "careful" alla rottura del massimo (minimo) HA della candela del segnale | entry E32_ALGOX_CAREFUL_UP / E32_SHORT_ALGOX_CAREFUL_DOWN (con PVSRA), E33_ALGOX_NOVOL_CAREFUL_UP / E33_SHORT_ALGOX_NOVOL_CAREFUL_DOWN (senza PVSRA, interruttore "Forex"); uscite X4_ALGOX_SELL / X4_SHORT_ALGOX_BUY (coppia ALGOX); filtri F40_ALGOX_STATE_LONG / SHORT (coppia ALGOX_STATE) | approvata 17/10 (due versioni su tutti i symbol, careful, Sensibility 2; uscita e filtro solo con PVSRA) | superato 17/10 (`test_algoxplorer.py` 52/52, fedeltà con PineTS) | sì; sovrapposizioni con E3, X3, F8/F9 tenute (decisione di Mattia, 17/10) | 6 |
| 14 | script TradingView (nostro) | 17/10/2026 | «VSA · Modulo Unico — Trend / Range / Reverse», indicatore Pine v6 scritto da Mattia, nessun vincolo (sorgente in `pine_sources/`, non su GitHub) | motore d'asta (zig-zag sui corpi, BOS, CHoCH, forza di gamba) + scanner VSA (assorbimento/esaurimento a percentile); ramo trend following e Stop & Reverse | entry E34_VSA_TREND_GO_UP / E34_SHORT_VSA_TREND_GO_DOWN (GO trend, senza sessione); E35_VSA_STOP_REVERSE_UP / E35_SHORT_VSA_STOP_REVERSE_DOWN. Ramo range scartato (non scatta con i default); filtri esclusi per scelta | approvata 17/10 (senza sessione, filtri rimandati) | superato 17/10 (`test_vsa_modulo_unico.py` 30/30, fedeltà con PineTS) | sì | 4 |
 
Non letti per scelta di Mattia: articoli su HMM / UMAP (modelli addestrati: rischio lookahead e calcolo pesante). Restano in elenco in `GUIDA_ANALISI_FONTI.md` §11.2 (Range Index, Vertical Horizontal Filter, change point bayesiano…).
 
**Prove da fonti testuali al 17/10/2026: 43** (dal 17/10: +6 di AlgoXplorer, riga 13, e +4 del VSA Modulo Unico, riga 14; prima erano 33). Al 15/10: **33** (articoli 17, script TradingView 12, indice di sentiment 1, ricerca multi timeframe 3 (libro Elder 2, articolo 1), video 0), con F37 e F38 spenti come doppioni (+2 se si riattivano), con **F27 e i doppioni di `51` spenti**; **31** se si attiva F27, **+5** se si riattivano i doppioni di `51`. Prima del multi timeframe (15/10) erano 30, prima di F36 29. Al 10/10/2026 erano 17. Storia del conteggio: 17 all'8/10; 14 il 9/10, quando i setup degli articoli 2 e 3 sono stati riscritti come entry uniche (§4) e i filtri estratti PVO e IIX sono stati tolti; 17 dal 9/10 con i filtri di regime F25 (2) e F26 (1).
 
Per video e libri la colonna «fonte» riporta canale e titolo (video) o autore, titolo e capitolo (libro), più il riferimento (minuto o pagina).
 
---
 
## 10 bis · I filtri di regime F25, F26, F27 (9/10/2026)
 
### Come funzionano (per decidere senza codice)
 
- **F25 CHOP (14 barre).** Misura quanto il prezzo va a zig-zag. "Tendenza" = choppiness nel 25% più basso delle ultime 500 barre; "laterale" = nel 25% più alto. Con isteresi: resta acceso finché non rientra sopra il 50° (tendenza) / sotto il 50° (laterale). Mai veri insieme.
- **F26 variance ratio (1 ora, finestra 2 giorni).** Sopra 1 = i movimenti tendono a proseguire. Stato acceso al 75° percentile (ultime 1000 barre), spento sotto il 50°.
- **F27 composito (opzionale, spento).** Almeno 2 voti su 3 fra CHOP-tendenza, VR-persistenza e ADX alto. Le tre misure sono poco correlate (0,02–0,17 su EURUSD): il voto è un consenso fra orizzonti diversi, senza altro ritardo.
**Limiti emersi dalle misure su EURUSD (onesti):**
- CHOP a 14 barre resta reattivo anche con l'isteresi: durata mediana di uno stato ≈ 10 barre (~2,5 ore), circa 10.000 cambi su 167.000 barre.
- Il VR è molto più lento: mediana ≈ 66 barre (~16 ore).
- F27 è dominato da CHOP e ADX (mediana 10 barre).
- Se serve un regime più stabile: variante con CHOP a 48 barre (+1 prova), da decidere.
### Collaudo (9–10/10/2026)
 
- `test_regime.py` (nuovo): 41/41 con pandas 3.0.5 e con pandas 2.2.3 (indicatori confrontati con riscrittura indipendente barra per barra, due trappole di lookahead riconosciute, isteresi verificata a mano, indipendenza dal punto di partenza dopo 3000 barre).
- Suite esistenti al 9/10: test_idee_articoli 64/64 (dopo l'aggiornamento del controllo C7, che vietava i numeri F25–F27 ora riusati), barre_per_lato 24, confidenza 34, entry_composita 39, entry_metro 22, filtri_tempo 25, inversione 25, montecarlo 17, portabilita 13, quarantena_trade 23, sessioni 20, tempo_prezzo 20, vetrina 55, vetrina_trigger 26.
- Sovrapposizioni: `diagnostica.sovrapposizioni` **non esiste in V4**; controllo fatto con uno script a parte. 9 coppie ≥70%, quasi tutte contro filtri molto larghi (F22 80%, F2_MID 75%) con correlazione ≈0: attese per caso.
- Il 10/10 in locale: tutte le suite passano (pandas 3.0.6); lookahead e degenerazione puliti anche sui 9 symbol di `dati/` (§12).
### Decisioni aperte
 
1. Attivare F27 composito? (+1 prova)
2. Variante CHOP lenta (48 barre)? (+1 prova)
3. Leggere gli articoli VHF / Range Index di `GUIDA_ANALISI_FONTI.md` §11.2?
---
 
## 10 ter · Il filtro di sentiment F36 (15/10/2026)

### Come funziona (per decidere senza codice)

- **Una volta al giorno**, a fine giornata FX (17:00 New York), si calcolano quattro misure sulle barre M15 di quel giorno, ognuna confrontata con i 30 giorni prima: **volatilità** (alta = paura), **distanza dal massimo** (lontani = paura), **prezzo rispetto alla media** (sotto = paura), **tick volume col segno del giorno** (volume alto in calo = paura). Ogni misura diventa il suo percentile sulle ultime 365 giornate; la media delle quattro, × 100, è il **punteggio** (0 paura, 100 avidità).
- La **classe** è il percentile del punteggio sulle ultime 365 giornate, in 5 quintili: 1 paura estrema, 2 paura, 3 neutro, 4 avidità, 5 avidità estrema.
- **Ogni barra vede solo l'ultima giornata chiusa**: dentro la giornata il valore resta quello di ieri. Le barre in quarantena non entrano nel calcolo.
- **F36 contrarian:** paura estrema → filtro sul long, avidità estrema → filtro sullo short (coppia `SENTIMENT`, una prova). La `direction` qui è il lato su cui si applica: eccezione dichiarata nel codice.
- **Giornate, non giorni di calendario:** su BTCUSD 365 giornate sono un anno, sul forex circa 17 mesi.
- **Riscaldamento di circa 2 anni** (30 + 365 + 365 giornate): il punteggio c'è da maggio 2021, la classe da maggio 2022 su BTCUSD e da fine 2022 sugli altri symbol. La scheda diceva 13 mesi: era sbagliato, perché il doppio percentile li raddoppia. Le colonne si aggiungono dopo il taglio di `aggiungi_indicatori`: le altre condizioni non perdono righe.
### Collaudo (15/10/2026)

- `test_sentiment.py` (nuovo): 53/53 con pandas 3.0.6. Prove: riscrittura indipendente giornata per giornata (forex e crypto sintetici, BTCUSD vero); valore fermo nella giornata; riscaldamento esatto; barre in quarantena sporcate senza effetto; crollo ed euforia costruiti a mano; trappola "giorno in corso" segnata LOOKAHEAD; 30 tagli a metà giornata; indipendenza dal punto di partenza; 9 symbol; registrazione. Pandas 2.2 non provato in locale: lo copre il collaudo su Colab.
- 9 symbol: F36 vero sul 19–22% delle barre con la classe pronta, per ciascun lato. `verifica_degenerazione` su BTCUSD: OK.
- `Collaudo_Catalogo.ipynb`: sul mercato sintetico di 4 mesi F36 risulta `NON_ESERCITATA` perché manca la storia di 2 anni. È atteso: il lookahead lo copre `test_sentiment.py`.
- **Confronto di controllo con alternative.me** (dato in `dati/FNG_alternative_me.csv`, non usato dal prodotto, nessun parametro ritoccato):
  - livelli: correlazione di rango 0,43 su 1.971 giornate (0,43–0,73 anno per anno), massima col loro valore del giorno dopo, come atteso perché loro aggiornano alle 00:00 UTC;
  - variazioni a 7 giorni: 0,60;
  - per componente: drawdown 0,52, momentum 0,53, volume 0,12, volatilità 0,00;
  - quintili: stessa classe il 29% delle volte (20% a caso), al massimo una classe di distanza il 64% (52% a caso).
- **Sovrapposizioni** (§7.5, in-sample, barre con la classe pronta):
  - EURUSD: l'avidità estrema sta al 71% dentro F28_VFI_POSITIVE (1,38 volte il caso);
  - BTCUSD: paura e avidità stanno al 74% e al 73% dentro VWAP_PREVIOUS_SESSION_CLOSED_BELOW / ABOVE (1,50 e 1,45 volte il caso);
  - correlazioni 0,18–0,24. Sono al limite della regola: decide Mattia (sotto).
### Decisioni

1. **Deciso il 15/10/2026 (Mattia): F36 resta acceso** nonostante le sovrapposizioni al limite.
2. **Deciso il 15/10/2026 (Mattia): il percentile resta a 365 giornate** (riscaldamento ~2 anni). Era la proposta: riscaldamento più corto, con il percentile delle componenti a 180 giornate invece di 365 (~1,6 anni)? Va deciso prima di guardare i risultati.
---
 
## 10 quater · Le condizioni multi timeframe F37, E31, F38, F39 (15/10/2026)

### Come funzionano (per decidere senza codice)

- **Il mattone comune** (`engine/indicatori.py`: `id_periodo`, `barre_superiori`, `al_periodo_chiuso`). Le candele H1, H4, giornata FX, settimana FX e mese sono costruite dalle M15:
  - H4 ancorato alle 17:00 di New York (blocchi che iniziano alle 17, 21, 01, 05, 09, 13 NY, ora legale compresa);
  - la settimana parte domenica alle 17:00 NY; il mese segue la data FX;
  - massimi, minimi e chiusure escludono le barre in quarantena.
  Una candela superiore è visibile dalla prima barra M15 del periodo dopo: mai dati del periodo in corso.
- **F37_FTFC_UP / DOWN** (coppia FTFC): chiusura sopra (oppure sotto) l'apertura dell'ora, della giornata, della settimana e del mese in corso, tutte e quattro. **Unica eccezione** alla regola «solo candela chiusa»: l'apertura del periodo in corso si conosce dalla sua prima barra, quindi è causale.
- **E31_TRIPLE_SCREEN_UP / SHORT_DOWN** (setup unico, §4; scelte di Mattia del 15/10):
  1. pendenza del MACD-Histogram 12/26/9 sulle H4 chiuse;
  2. Force Index (EMA a 2) dell'ultima H1 chiusa, sotto zero per il long (sopra per lo short);
  3. chiusura M15 oltre il massimo (oppure sotto il minimo) dell'ultima H1 chiusa.
  Omessa la clausola «purché non a un nuovo minimo di più settimane».
- **F38_TSMOM_ALL_UP / DOWN** (coppia TSMOM): rendimento dell'ultima giornata chiusa rispetto a 1, 5 e 21 giornate prima, con lo stesso segno su tutti e tre gli orizzonti.
- **F39_INSIDE_DAY** (neutro): la giornata chiusa è rimasta dentro il massimo e il minimo di quella prima.

### Collaudo (15/10/2026)

- **Test:** `test_multi_timeframe.py`, 38/38:
  - riscrittura indipendente a cicli (forex e crypto sintetici, EURUSD vero);
  - confini dei periodi, quarantena, specchio long/short, giorno inside costruito a mano;
  - lookahead con una trappola (punto medio dell'ora in corso) segnata LOOKAHEAD, condizioni nuove OK;
  - riscaldamento: identiche dopo circa 75 giornate;
  - 9 symbol;
  - verifica_degenerazione su EURUSD tutta OK.
- **Correzione emersa nel collaudo:** le 7 ore vanno sommate all'ora *da orologio* di New York. Sommate a un orario con fuso, nella notte del cambio d'ora i blocchi H4 del crypto si spostavano di un'ora.
- **Frequenze sui 9 symbol:**
  - F37: 9–20% delle barre per lato;
  - F38: 13–32%;
  - F39: 11–20%;
  - E31: circa 1.900–2.650 eventi per lato.
- **Sovrapposizioni** (§7.5, in-sample, EURUSD, BTCUSD e DE40):
  - **F37 è un doppione chiaro**, non al limite: sta al 88–92% dentro F8/F9 (prezzo sopra/sotto EMA50, 1,7–2,0 volte il caso) e all'81–89% dentro F16/F17 e i filtri VWAP (1,5–1,9 volte). È una versione più stretta del «prezzo sopra la media/VWAP».
  - **F38 è doppione** dei filtri VWAP «sessione precedente chiusa sopra/sotto» (77–86%, 1,4–1,8 volte) e di F28 VFI (72–81%, 1,4–1,6 volte). Su DE40 l'avidità estrema F36 sta all'82% dentro F38 (2,8 volte).
  - **E31:** al 65–72% entro 2 barre da E3_SHORT_INTRABAR_STRENGTH_FADE (2,2–2,4 volte il caso). Sopra la soglia solo su EURUSD (72%); al limite.
  - **F39:** nessuna sovrapposizione sopra il 60% con lift.
  - Correlazioni tutte sotto 0,40.

### Decisioni

1. **Deciso il 15/10/2026 (Mattia): F37 e F38 spenti come doppioni.** La riga in FILTRI è commentata. Funzioni e colonne restano e si riattivano togliendo il `#` (+2 prove).
2. **Deciso il 15/10/2026 (Mattia): E31 resta acceso.**

---
 
## 10 quinquies · AlgoXplorer 0.1c: E32, E33, X4, F40 (17/10/2026)

### Come funziona (per decidere senza codice)

- **Le candele Heikin Ashi (HA)** (`engine/indicatori.py`: `heikin_ashi`) sono candele lisciate dello stesso timeframe: chiusura = media di O, H, L, C; apertura = media di apertura e chiusura HA della barra prima. Solo passato; l'apertura dipende dalla prima barra dei dati ma la differenza si dimezza a ogni barra.
- **La candela PVSRA climax** (`pvsra_climax`): tick volume almeno doppio della media delle ultime 10 barre (barra corrente compresa), oppure volume × ampiezza il più alto delle ultime 10. Lime se la candela vera chiude in rialzo, rossa se in ribasso.
- **Buy:** candela lime, chiusura HA sopra la EMA a 50 dei massimi, massimo HA sopra la chiusura HA, chiusura HA sopra il massimo HA della barra prima. **Sell:** candela rossa, chiusura HA sotto la EMA a 50 dei minimi, massimo HA uguale all'apertura HA (nessuna ombra superiore), chiusura HA sotto il minimo HA della barra prima. Long e short **non sono speculari** (come nello script).
- **Alternanza:** un Buy conta solo se l'ultimo segnale era un Sell, e viceversa (`algoxplorer`, colonne `algox_segnale` e `algox_stato`).
- **Ingresso careful** (E32, E33): la prima barra dopo il Buy, prima del Sell, il cui massimo HA supera il massimo HA della candela del Buy; se non succede, nessun ingresso ("Not enter"). Short speculare sul minimo HA. Il motore entra all'Open della barra dopo.
- **E33** è lo stesso senza la candela PVSRA (interruttore "Forex" dello script), su tutti i symbol.
- **X4:** chiude il long all'etichetta Sell (e lo short al Buy), versione con PVSRA. **F40:** vero mentre l'ultimo segnale è Buy (long) o Sell (short), la barra verde o rossa dello script.
- **Scartati:** l'etichetta "Max profit" (massimo guadagno visto col senno di poi, ridisegnata a ogni nuovo massimo); "overridesym" (volume da un altro symbol, spento); la banda EMA e la candela PVSRA come filtri a sé (lo script non le usa da sole, §4).

### Collaudo (17/10/2026)

- `test_algoxplorer.py` (nuovo): 52/52 con pandas 3.0.6.
  - **Fedeltà:** il Pine fatto girare con PineTS su 20.000 barre di EURUSD, BTCUSD, DE40, con e senza PVSRA. La copia di collaudo (`pine_sources/algoxplorer_0_1c_v5.pine`, `_forex_v5.pine`) cambia solo `request.security`, che PineTS non esegue sui CSV: candele HA con la formula standard, volume del grafico (overridesym è spento). Tutto identico salvo **un pareggio numerico** su EURUSD senza PVSRA (chiusura HA 1,1712600000000002 contro massimo precedente 1,17126: scarto 2e-16), che sposta 4 barre su 784 eventi.
  - riscrittura indipendente barra per barra con le variabili dello script; candele costruite a mano (Buy, careful, "Not enter", Sell, PVSRA); trappola "sapere al Buy se il careful arriverà" segnata LOOKAHEAD; riscaldamento; 9 symbol; `verifica_degenerazione` su EURUSD tutta OK.
- Lookahead sull'intero catalogo (sezione B di `Collaudo_Catalogo.ipynb`, rifatta in locale): 148 condizioni, 0 LOOKAHEAD, 0 ERRORE.
- **Eventi sui 9 symbol (storico intero):** E32 716–1.170 per lato, E33 1.420–1.991, X4 805–1.295; F40 vero sul 52–58% (long) e 42–47% (short) delle barre.
- **Sovrapposizioni** (§7.5, in-sample 80%, EURUSD, BTCUSD, DE40; trigger a 2 barre, filtri e uscite a 0):
  - **E32 long** al 83–89% entro 2 barre da E3_SHORT_INTRABAR_STRENGTH_FADE (2,8–3,0 volte il caso); **E32 short** al 76–82% da E3_LONG_INTRABAR_WEAKNESS_FADE (3,7–3,9 volte); **E33 long** al 72–77% da E3_SHORT (2,5 volte); E33 short 67–70% (al limite). È lo stesso fenomeno di E25, E26, E31: E3 scatta dopo quasi ogni barra forte, nel verso opposto. Correlazioni sotto 0,06.
  - **X4** al 85–95% dentro X3_MACD (1,7–1,9 volte): l'uscita a evento cade quasi sempre in barre dove il MACD è già sotto (sopra) il segnale; X3 è uno stato e chiude di solito prima.
  - **F40** al 70–75% dentro F8/F9 (contesto di trend, 1,4–1,6 volte), e al 71–72% dentro F28 VFI e i filtri VWAP «prezzo sopra/sotto il fair value» su alcuni symbol. Correlazioni 0,37–0,50. Più debole di F37 (88–92%), spento il 15/10.
  - E32 ed E33 fra loro: 62–67% (sotto la soglia).

### Decisioni

1. **Deciso il 17/10/2026 (Mattia): E32, E33 e X4 restano accesi** nonostante le sovrapposizioni con E3 (come E31 il 15/10) e con X3 (X3 è uno stato e chiude prima).
2. **Deciso il 17/10/2026 (Mattia): F40 resta acceso** nonostante il 70–75% dentro F8/F9.

---

## 10 sexies · VSA · Modulo Unico: E34, E35 (17/10/2026)

### Come funziona (per decidere senza codice)

- **Motore d'asta** (`engine/indicatori.py`: `vsa_modulo_unico`): uno zig-zag sui corpi delle candele. Uno swing si conferma quando il prezzo torna indietro di almeno la mediana dei corpi delle ultime 100 barre (e dopo almeno 2 barre): il livello esiste da quella barra, non da quella del pivot. **BOS** = prima chiusura oltre l'ultimo swing; **asta confermata** = almeno 2 BOS di fila nello stesso verso; **CHoCH** = il primo BOS contrario a un'asta confermata. **Forza** di una gamba = ampiezza / (barre × mediana dei corpi), anche per la gamba in corso.
- **Scanner VSA:** rango percentile di tick volume e corpo sulle 100 barre precedenti. Assorbimento = volume ≥ 70°, corpo ≤ 30°; esaurimento = volume ≤ 30°, corpo ≥ 70°. Il segnale (bias) è sempre contrario al colore della candela (interpretazione "Reversal", default).
- **E34, GO trend following:** asta confermata; momentum nel verso dell'asta (gamba più forte di almeno il 20%); forza ≥ 1; nelle 3 barre prima una candela di incongruenza VSA nel verso dell'asta, con il minimo (long) o il massimo (short) a non più di 2 mediane dei corpi da uno degli ultimi 24 swing; candela di conferma del colore dell'asta con corpo ≥ 50° percentile. **Senza sessione** (decisione di Mattia: le fasce orarie le valuteranno i filtri). Le spunte 7, 8 e 10 dello script (stop, R:R ≥ 2, rischio) con i default sono sempre vere e non entrano.
- **E35, Stop & Reverse:** CHoCH chiuso da una candela del verso nuovo con corpo ≥ 65° percentile.
- **Scartati:** il ramo **range** (con i default la conferma chiede un bias VSA nel verso della candela, ma il bias "Reversal" è sempre contrario: non può scattare; senza l'obbligo VSA ~10 segnali per lato in 6 anni); stop, target, TP1/TP2 e "hold" (uscite e gestione); capitale e rischio (money management); il regime trend/range come filtro (rimandato).

### Collaudo (17/10/2026)

- `test_vsa_modulo_unico.py` (nuovo): 30/30 con pandas 3.0.6.
  - **Fedeltà:** il Pine (copia di collaudo `pine_sources/vsa_modulo_unico_v6.pine`: senza grafica, pannello e alert, sessione spenta) fatto girare con PineTS su 40.000 barre di EURUSD, BTCUSD, DE40: asta, bias, GO e S&R **identici**.
  - **Pareggi numerici:** nei CSV di MT5 due corpi "uguali" differiscono di 1e-16, e in PineTS lo stesso rango cambia a seconda di come è scritto. Il confronto si fa con i prezzi in punti interi (lo script usa solo confronti e rapporti: stesso risultato); nel codice prezzi, differenze di prezzo, mediana, scarto e forza si arrotondano a 10 decimali. Verificato: prezzi veri e prezzi in punti danno gli stessi segnali.
  - `ta.percentrank` = quota delle 100 barre precedenti ≤ della corrente; `ta.percentile_linear_interpolation` = posizione n × p − 0,5 (verificati con PineTS).
  - specchio dei prezzi (long ↔ short), proprietà di ogni GO e S&R, trappola "rango su finestra centrata" segnata LOOKAHEAD, riscaldamento (identiche dopo 3000 barre), 9 symbol, `verifica_degenerazione` su EURUSD tutta OK.
- Lookahead sull'intero catalogo: 152 condizioni, 0 LOOKAHEAD, 0 ERRORE.
- **Eventi sui 9 symbol (storico intero):** E34 184–451 per lato, E35 2.199–3.413.
- **Sovrapposizioni** (§7.5, in-sample, EURUSD, BTCUSD, DE40): nessun doppione. Le più alte: E35 long al 64–67% entro 2 barre da E3_SHORT_INTRABAR_STRENGTH_FADE (2,1–2,3 volte il caso), E34 al 61–63% da E12 engulfing (1,4 volte).

---

## 11 · Esempio guidato — l'articolo Fourier (applicazione della lista, non la scheda)
 
Serve a mostrare come si usa §6 su un articolo vero. La scheda completa è il prossimo passo e va approvata da Mattia.
 
**Dove l'articolo guarda al futuro o si regge su un artefatto:**
1. **FFT e ricostruzione sull'intero campione.** Il segnale «smoothed» a *t* contiene informazione delle barre successive (riga 2 di §6). Va rifatto con finestra mobile sul passato e si usa solo l'ultimo punto della ricostruzione.
2. **La «previsione» è la ripetizione della finestra.** Le frequenze sono multipli di 1/N, quindi la proiezione ripete le ultime N barre ricostruite: non è una stima del futuro. In una condizione si usa il segno della componente ciclica a un orizzonte dichiarato, calcolato sul passato.
3. **Il trend non è tolto.** Un trend lineare non è periodico: tra inizio e fine finestra c'è un salto che sporca lo spettro (leakage). Si lavora su rendimenti o con trend sottratto, e con una finestra (es. Hann).
4. **Dati sintetici con cicli inseriti a mano:** niente da portare come evidenza (§0).
5. **Il codice dell'articolo non gira da solo:** mancano gli import di `fft` e `ifft`. Si riscrive comunque (§2.1).
**Candidati da discutere in scheda** (proposte, non decisioni):
- **Filtro di regime:** quota di energia spettrale nel ciclo dominante, su finestra mobile solo sul passato, sopra un percentile rolling. Neutro (`direction=0`).
- **Entry sulla fase del ciclo:** evento in cui la componente ciclica gira verso l'alto (long) o verso il basso (short).
- **Uscita a regola:** fine del semiciclo, con periodo ricavato dal ciclo dominante.
**Da decidere insieme:** lunghezza della finestra mobile (e quindi riscaldamento), numero di armoniche (proposta: una sola, la dominante, per ridurre i parametri), e se il costo di calcolo su ogni barra è accettabile per M15.
 
---
 
## 12 · Lavoro in locale con Claude Code (dal 10/10/2026)
 
### Impostazione
 
Repo clonato sul PC di Mattia (Windows), VS Code + Claude Code. Nel repo: `CLAUDE.md` (istruzioni per Claude Code), `docs/` (copia dei documenti del Project), `engine/mt5_interaction.py` (si usano solo le funzioni di lettura), `scarica_dati.py`. La cartella `dati/` è nel `.gitignore`, come `.venv/` e `credenziali_mt5.txt`: i dati non vanno su GitHub. Un ramo per argomento; il Merge lo fa Mattia su GitHub. GitHub CLI è installato e collegato (`gh auth login`, account matti410): l'invio del ramo e la Pull request li può fare anche Claude Code. Regole di consegna in §9.1.
 
### Dati
 
`scarica_dati.py` scarica da MT5 (sole funzioni di lettura) le barre M15 dal 2/1/2020 e le salva in `dati/<SYMBOL>_M15.csv`, nello stesso formato di `EURUSD_M15.csv` (ora server, colonne `Date, Open, High, Low, Close, Volume, spread`). A fine corsa stampa prima e ultima barra, barre, pause ricorrenti, buchi, fuso, quarantena.
 
- **Symbol disponibili (al 9/10/2026):** EURUSD, GBPUSD, USDJPY, NZDUSD (~168.600 barre ciascuno), BTCUSD (223.655), US500, USTEC, XAUUSD, DE40 (156.700–160.200).
- **USDCAD escluso:** il broker lo fornisce in M15 solo da gennaio 2025, anche nel grafico di MT5.
- **Pause ricorrenti, non buchi:** indici e oro si fermano ogni giorno dalle 17:00 alle 18:00 di New York; BTCUSD si ferma il venerdì alla stessa ora. Buchi veri: festivi USA (3 luglio, 24 dicembre, 9/1/2025), sospensioni di marzo 2020, il buco noto del 2/12/2021, piccole manutenzioni.
- **I due notebook leggono da `dati/`** (il principale dal 10/10, il Lab dall'11/10): su Colab da Google Drive, `Il mio Drive/Trading-System-Creator_V4/dati/`; in locale dalla cartella `dati/`. Nel principale `symbol` (cella 11) è l'unica variabile da cambiare; nel Lab lo strumento si sceglie dal menu del passo 1, fra i 9 symbol di `engine/simboli.py`.
### Fuso
 
Una sola regola per tutto il conto: `A_US_DST (NY+7h)` (`10_DATI_FUSO_BROKER.md`). Conferma sui dati nuovi: le pause quotidiane di indici, oro e BTCUSD (venerdì) cadono alle 17:00 di New York, cioè **21:00–22:00 UTC d'estate e 22:00–23:00 UTC d'inverno**. La diagnosi automatica dà "NO" su indici e oro (match 26–47%) perché guarda la riapertura del weekend, che per loro non segue la regola dei cambi: non è un errore dei dati. Su BTCUSD (aperto nel weekend) la diagnosi non si fa. Per lo stesso motivo nel notebook (cella 13, dall'11/10) `verifica_indice_utc` si applica al symbol solo se è un forex; per indici, oro e cripto si applica a EURUSD dello stesso server. Quarantena ≈5,2% sul forex, ≈2% su indici e oro.
 
### Pip e costi per symbol
 
- **Pip fisso per symbol**, dalla tabella `engine/simboli.py` (classe, pip, contratto, valuta di quotazione, cifre; letti da MT5 con `symbol_info` in sola lettura il 10/10). Convenzione: forex 0,0001 (JPY 0,01), **oro 0,10 $**, indici 1 punto, BTCUSD 1 $. Il pip viaggia nel dizionario dei costi (`parametri_backtest` → `**costi`) fino ai motori, a `due_meta` e alla vetrina. Symbol fuori tabella → errore, nessun pip indovinato. Prima il pip era dedotto dal prezzo medio: su US500 valeva 0,01 in-sample e 1,0 out-of-sample.
- **Metalli senza MT5:** nozionale = contratto × prezzo (XAUUSD 100 once): una commissione di 7 $ vale 0,7 pips.
- **Indici dal nome:** US500, USTEC, DE40 → classe "indici".
- **Valore del pip per lotto:** XAUUSD 10 $, US500 e USTEC 1 $; DE40 è quotato in EUR e il notebook passa il cambio EURUSD dell'ultima barra.
- **Spread:** il notebook li prende **solo dal listino** del conto Standard (`SPREAD_LISTINO_PIPS` in `engine/vetrina.py`); commissione zero. Valori Standard stimati l'11/10: vedi la sottosezione qui sotto. Un symbol senza riga ferma il notebook, e il messaggio dice la riga esatta da aggiungere, col rollover proposto dai dati (mediana dello spread nelle barre di quarantena, solo se la colonna è significativa: è il minimo di barra, quindi un limite inferiore). Lo spread normale **non** si ricava dalla colonna `spread`: sul forex vale quasi sempre zero (feed di tipo Raw), non è lo spread Standard.
- **Capitale:** `CASH = 10.000.000` basta per tutti i 9 symbol; il notebook si ferma se è meno di 10 volte il prezzo massimo.
- USTEC ha 2 cifre in MT5 (punto 0,01) ma nei dati quota sempre a passi di 0,1: la colonna `spread` si converte col punto della tabella, non col passo dei prezzi (prima usciva 10 volte troppo alta).
### I due notebook: sempre allineati (regola di Mattia, 11/10/2026)
 
`Trading_Grid_Search_v4_backtesting.ipynb` (la ricerca) e `Trading_System_Lab.ipynb` (il laboratorio guidato) **si aggiornano sempre insieme, nello stesso ramo**: ogni modifica a dati, symbol, costi, pip, fuso, capitale o lotti fatta in uno va portata anche nell'altro.
 
- Il Lab non ha codice nelle celle: chiama le funzioni di `engine/vetrina.py` (`prepara`, `stress_test`, …). Allineare il Lab vuol dire di solito modificare `vetrina.py`, più le celle di avvio e del passo 1.
- **Prova per entrambi:** identità su EURUSD a parità di barre (stesso CSV tagliato all'ultima barra del vecchio, notebook eseguito prima e dopo, uscite e variabili confrontate) e un giro completo su un symbol non forex (DE40), che esercita listino, verifica del fuso su EURUSD e cambio nei lotti.
- **Allineamento dell'11/10:** il Lab legge da `dati/` o da Drive, offre i 9 symbol, prende lo spread dal solo listino (`spread_listino`), verifica il fuso su EURUSD per indici, oro e cripto, si ferma se `CASH` è meno di 10 volte il prezzo massimo, e nello stress test passa il cambio per DE40. Prova: Lab su EURUSD e BTCUSD identico prima e dopo (24 tabelle su 24 per ciascuno); su DE40 e XAUUSD arriva in fondo (valore del pip 1,12 $ e 10 $).
- La lente sul trade (passo 7b) disegna un grafico interattivo che richiede il pacchetto `nbformat`: c'è su Colab, non nell'ambiente locale (in locale quel passo dà errore, gli altri no).
 
### Costi: decisione dell'11/10/2026
 
**Il demo IC Markets non ha i costi di un conto reale.** Letto dallo storico (9.226 operazioni dal 22/12/2023 al 31/07/2026, sola lettura con permesso di Mattia) e dal report XLSX: commissione **zero** su tutte le operazioni, e spread pagato da Raw (EURUSD circa 0,05 pips; oro 0,09 $, misurato sui tick all'esecuzione). Un conto reale costa circa 0,8 pips su EURUSD sia come Raw (0,06 + 0,7 di commissione) sia come Standard (da 0,8): il demo costa circa 15 volte meno.
 
**Decisione di Mattia:** si resta su IC Markets; la ricerca usa i costi di un conto **Standard** reale (commissione zero, spread di listino); dopo un numero di operazioni in demo (indicativamente almeno 100) si verifica la veridicità dei costi, e un eventuale scarto dal vivo si sistema dopo.
 
**Come si verifica in demo** (il demo non applica i costi Standard, quindi non si confronta il netto): pips **lordi** delle operazioni demo contro il backtest dello stesso periodo; esecuzione (scarto dal prezzo del segnale, ingresso all'apertura della barra); "demo corretto" = lordo demo meno il costo Standard del listino.
 
**Listino Standard stimato (11/10), in `SPREAD_LISTINO_PIPS`:** normale per forex e oro = spread Raw medio + commissione Raw equivalente (0,7 pips; 1,1 su USDJPY), per indici e BTCUSD = il più alto fra sito e demo; rollover = normale + allargamento misurato nei dati (quarantena meno fuori quarantena). EURUSD resta 0,8 / 1,5, e la regola lo ritrova.
 
| symbol | normale | rollover |
|---|---|---|
| EURUSD | 0,8 | 1,5 |
| GBPUSD | 1,0 | 3,3 |
| USDJPY | 1,3 | 2,7 |
| NZDUSD | 0,8 | 2,5 |
| XAUUSD | 1,6 | 1,8 |
| US500 | 0,5 | — (nessun allargamento) |
| USTEC | 1,6 | 2,6 |
| DE40 | 1,5 | 6,5 |
| BTCUSD | 12,5 | 12,8 |
 
Sono **stime**: lo 0,8 Standard è il minimo pubblicato, non la media. Da verificare con le prime operazioni sul conto Standard reale; un symbol nuovo senza riga continua a fermare il notebook con la riga esatta da aggiungere.
### Collaudo su 9 symbol (10/10/2026)
 
- `verifica_lookahead` sul mercato sintetico e sugli ultimi ~4 mesi di ogni symbol: 141 righe (122 condizioni + 19 indicatori, compresi `chop` e `vr`), **0 LOOKAHEAD, 0 ERRORE**.
- `verifica_degenerazione` sullo storico intero: unico segnale E19_SHORT_THREE_BLACK_CROWS RARA (8–29 eventi). Copertura F25/F26 35–38% su tutti i symbol (attesa: sono percentili).
- Il notebook principale sui file di `dati/`: su EURUSD, a parità di barre, uscite e variabili identiche a prima (42 celle, 62 variabili, 20 tabelle intere).
- Collaudo `test_simboli.py` per tabella, pip, costi e spread di listino.
