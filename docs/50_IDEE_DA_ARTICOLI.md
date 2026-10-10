# 50 · Idee da fonti testuali — come trascriverle in condizioni
 
**Data:** 7 ottobre 2026 (registro aggiornato l'8/10; regola dei setup composti in §4 e riordino del 9/10)
**Stato:** metodo concordato con Mattia; esteso il 7/10 da articoli a **video YouTube (trascrizione incollata da Mattia) e libri**. Al 9/10/2026 trascritti 4 articoli, 14 prove: vedi il registro in §10. L'esempio guidato del primo articolo (Fourier, Kaabar) resta in §11. Repo di destinazione predefinito: V4 (confermato il 7/10).
**Nota sul nome:** il file resta `50_IDEE_DA_ARTICOLI.md` perché altri documenti lo citano; vale per qualunque fonte testuale.
**Prima di questo:** `00_SCOPO_E_STATO.md`, `02_KPI_E_GIUDIZIO.md`, `20_CONDIZIONI_TEMPO.md`, `21_COLLAUDO_CATALOGO.md`, `32_RIORDINO_CONDIZIONI.md`
**Guida operativa per la nuova chat:** `GUIDA_ANALISI_FONTI.md` (nel repo, sostituisce `GUIDA_ANALISI_ARTICOLI_MEDIUM.md`), con prompt di avvio per articoli, video e libri ed elenco dei link da leggere.
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
| 5 · Consegna | Claude | file modificati come download, celle di notebook come testo, istruzioni di esecuzione (§9) |
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
| uno **stop** o un **target** | non è una condizione: li ricava il tool con i percentili adattivi (`soglie_adattive`) | si annota come idea di uscita; stop e target non si ottimizzano (`01`, passo 3) |
| un'uscita **a tempo** | non è una condizione: è `n_barre` (o `n_barre_long` / `n_barre_short`) | |
| sizing, gestione del rischio, portafoglio | fuori dal catalogo | passo 7 / livello portafoglio (`33`) |
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
Le quattro regole di `01`, passo 5:
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
- **Unità:** costi in pips, non in bp; se serve la conversione si esplicita.
- **Docstring:** una riga che dice cosa fa, più la fonte: articolo (autore, titolo, URL); video (canale, titolo, URL, minuto); libro (autore, titolo, edizione, capitolo, pagina).
- **Segno nell'event study:** sempre dal punto di vista del trade, mai del prezzo (`40`, §6 bis). Vale anche per le condizioni nuove.
---
 
## 6 · Le trappole di lookahead tipiche delle fonti
 
Gli esempi degli articoli sono scritti per mostrare un'idea, non per girare in tempo reale: molti usano tutto il campione. Video e libri aggiungono altre forme (ultime righe della tabella). Questa tabella è la lista da controllare nella lettura (e da riportare nella scheda).
 
| forma nella fonte | perché guarda al futuro | come si trascrive |
|---|---|---|
| `rolling(center=True)`, filtri non causali (Savitzky-Golay, gaussiano, Hodrick-Prescott, LOWESS, `filtfilt`, smoother di Kalman) | il valore a *t* usa barre dopo *t* | versione in avanti: EMA, filtro di Kalman solo forward, `lfilter` |
| scomposizioni o ricostruzioni sull'intero campione (FFT e inversa, wavelet, EMD, PCA, SVD) | il punto ricostruito a *t* dipende da tutta la serie | finestra mobile **solo sul passato**, si tiene solo l'ultimo punto; attenzione all'effetto di bordo |
| z-score, min-max, scaler, percentili calcolati su tutto il campione | media e deviazione includono il futuro | rolling o expanding |
| pivot, zigzag, swing high/low, `find_peaks`, `argrelextrema`, frattali (barre a destra) | un massimo si conferma solo con barre successive | il segnale esiste dalla barra di **conferma**, non da quella del pivot |
| etichette e target (`shift(-n)`, `pct_change(-n)`) rimasti nel segnale | il segnale conosce l'esito | via dal segnale; il target sta altrove (`target.py` nel ramo ML) |
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
3. **`verifica_degenerazione`** su EURUSD vero: copertura, eventi, `STATO`, `RARA`, `SEMPRE_VERA`. Sotto le 30 occorrenze (entry) o 30 barre vere (filtri e uscite) si segnala, non si promuove né si boccia.
4. **Casi a risultato noto:** serie costruite a mano su cui l'esito è noto (il trigger scatta sulla barra attesa; lo short è lo speculare del long; il filtro cambia stato dove deve).
5. **Sovrapposizioni con il catalogo:** `diagnostica.sovrapposizioni(df, colonne, finestra, soglia)` (`32`), solo su `df_is`, filtri a finestra 0 e trigger a finestra 2, soglia 70. Una condizione contenuta al 70% o più in una già presente, o suo contrario esatto, è un doppione: non si aggiunge, a meno che Mattia lo decida. Funzione presente nel ramo ML dal 1/10; **nel repo V4 va verificata** prima di contarci.
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
 
**Cosa riceve:**
- i file modificati come download (es. `engine/indicatori.py`, `entry_long.py`, `entry_short.py`, `filter_conditions.py`, i file di exit), ognuno con la cartella dove va;
- eventuali test nuovi (`test_*.py`);
- le celle di notebook da incollare, come testo, ciascuna con una cella markdown breve davanti (cosa fa, come leggere l'output, cosa fare dopo).
**Come si esegue:**
1. Caricare i file sul repo, nelle cartelle indicate (`engine/…` nella cartella `engine`, gli altri nella cartella principale).
2. Aprire il terminale **nella cartella del progetto** e lanciare i test nuovi: `python test_nome.py`. L'ultima riga attesa è nel formato `RISULTATO: n/n test superati`; con meno del totale, copiare qui il messaggio.
3. Rilanciare **`Collaudo_Catalogo.ipynb`** su Colab: *Runtime → Esegui tutto*, 2–3 minuti. Attesi: A1 e A2 con tutte le prove superate (il totale sale quando si aggiungono trappole), B con **0 LOOKAHEAD e 0 ERRORE**, D e E superate. La sezione C è una tabella da leggere, senza promosso o bocciato.
4. Nel notebook principale la condizione compare da sola dopo la registrazione (riavviare il runtime e rieseguire dall'inizio, così i dizionari si rileggono).
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
 
**Prove da fonti testuali al 9/10/2026: 14** (articoli 14, video 0, libri 0). Erano 17: il 9/10 i setup degli articoli 2 e 3 sono stati riscritti come entry uniche (§4) e i filtri estratti PVO e IIX sono stati tolti.
 
Per video e libri la colonna «fonte» riporta canale e titolo (video) o autore, titolo e capitolo (libro), più il riferimento (minuto o pagina).
 
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