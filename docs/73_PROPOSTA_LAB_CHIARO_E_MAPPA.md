# 73 · Proposta: Lab più chiaro (A) e mappa delle anomalie (B)

**Data:** 26 ottobre 2026
**Stato:** PROPOSTA, **senza codice**. Risponde all'incarico `docs/72`. Il codice
si scrive dopo il merge di questa proposta, in due Pull request: prima A, poi B.
**Perimetro:** crypto da exchange; il Lab broker resta sospeso e non si tocca.

**Indice:** §0 In breve · **Parte A** §A.1 Schermata 2 · §A.2 Schermata 3b ·
§A.3 Schermate 3c e 3d · §A.4 Schermata 5 con una situazione scelta · §A.5 Cosa
cambia nel codice, collaudo, identità · **Parte B** §B.1 Il notebook della mappa ·
§B.2 La scheda dell'ipotesi · §B.3 La misura e il verdetto · §B.4 Lo studio e il
conto · §B.5 Il posto 2b del Lab · §B.6 La prima versione: quali meccanismi ·
§B.7 Codice, collaudo, tempi · §6 Le sette domande del `72` · §7 Consegna ·
§8 Decisioni per Mattia · §9 Rischi.

---

## 0 · In breve

**Parte A: il Lab più chiaro.**
- **Schermata 2.** Il testo deciso da Mattia va nella cella del notebook e i titoli,
  i grafici e i riquadri si allineano a quel testo. Sparisce la frase «rispetto a un
  ingresso qualunque alla stessa ora». Nessun numero cambia.
- **3b.** Si aggiunge il campo «parti da», con tre valori: la rosa (predefinito),
  tutte le candidate, niente. Il testo dice che in «aggiungi» va bene qualunque
  trigger del catalogo e dove trovarne i nomi. Non aggiunge prove.
- **3c e 3d.** Il testo deciso; nella 3c le celle si chiamano «situazioni», con i
  nomi in chiaro. Nelle tabelle «Passa» si divide in due colonne, «batte il
  mercato» e «paga i costi». La 3d accetta **qualunque situazione misurata**
  dall'atlante (almeno 200 occasioni) e avvisa se non passa. Nessuna prova in più.
- **Schermata 5 con una situazione scelta.** Il comportamento resta com'è. Il
  testo e la tabella dicono che si misura solo la situazione, e perché gli altri
  filtri non si provano.
- A scelte uguali, numeri uguali: prove d'identità su BINANCE_PERP_BTCUSDT e
  BYBIT_SPOT_ETHUSDT, nei due notebook.

**Parte B: la mappa delle anomalie.**
- Un notebook a parte, `Mappa_Anomalie_Crypto.ipynb`, senza logica nelle celle,
  che chiama un modulo nuovo dell'engine.
- **Prima la scheda, poi i dati.** Ogni ipotesi è una scheda scritta e
  approvata prima di misurare: meccanismo, variabile, fascia attesa con il suo
  segno, orizzonte in ore, mercato di riferimento, portabilità su TradingView. Le
  schede stanno nell'engine, in un dizionario come il catalogo, e in un registro
  in `docs/`.
- **La misura.** La variabile si divide in 5 fasce (quintili su un anno di sole
  barre passate) e per ogni fascia si misura lo scarto dal mercato
  all'orizzonte della scheda, con le stesse formule della rosa. Il verdetto
  guarda solo la fascia dichiarata nel verso dichiarato. Un segno opposto, o una
  fascia non dichiarata, si mostra ma non conta come scoperta.
- **Stesso studio, stesso conto.** Solo in-sample. Le fasce misurate entrano nel
  giornale del dataset e il Lab le vede nella soglia cumulata. Alla 2b, in sola
  lettura, il Lab mostra le schede già misurate.
- **Prima versione:** sette meccanismi, tutti con dati già in casa (§B.6). Restano
  fuori per ora le scadenze delle opzioni (troppo pochi casi), un exchange contro
  l'altro, la distanza dai massimi e la volatilità da sola (che non ha un segno
  atteso).
- **Tempi misurati oggi:** circa 2 secondi per scheda su BTC perp M15 (§B.7).

---

# PARTE A · Lab più chiaro

## A.1 · Schermata 2

### A.1.1 · La cella di testo del notebook

Al posto del testo di oggi («Prima il metro, poi i trigger…») va il testo deciso
da Mattia (`72` §A.1), così com'è:

> **2 · Esplora.** Prima guardiamo il mercato da solo, poi i segnali.
>
> **2a · Il mercato ora per ora.** In alcune ore del giorno il prezzo tende a
> salire o scendere più del solito. Qui vedi quanto, ora per ora. Ci serve come
> termine di paragone: un segnale vale qualcosa solo se fa meglio di quello che
> il mercato fa già da solo a quell'ora.
>
> **2c · I segnali contro il mercato.** Ogni linea è un segnale. Mostra, barra
> dopo barra dall'ingresso, quanti bp guadagna in più (sopra lo zero) o in meno
> (sotto lo zero) del mercato. Una linea che sale e resta sopra lo zero indica
> un segnale che aggiunge qualcosa al mercato.

Sotto, una riga: «La 2b mostra le schede della mappa delle anomalie già misurate
su questo dataset (§B.5). In fondo a ogni schermata la riga **Prove** dice quante
prove hai fatto finora.» Fino alla parte B la 2b resta vuota, e la riga dice
solo: «La 2b è il posto della mappa delle anomalie, in arrivo.»

I titoli delle due celle diventano «2a · Il mercato ora per ora» e «2c · I segnali
contro il mercato».

**Una parola sola nel testo: «segnale».** Il testo deciso dice «segnale». Nei
testi delle schermate 2, 3c, 3d e 5 propongo «segnale». La parola «trigger» resta
dove si parla dell'oggetto tecnico: i nomi del catalogo, i campi della 3b, la rosa
della 3a. Alla prima comparsa nella schermata 2 si scrive «segnale (trigger)».
Decisione D1 del §8.

### A.1.2 · 2a: grafico, tabella, riquadro (bozza)

| oggi | dopo |
|---|---|
| titolo «Se apro un long a quest'ora, guadagno più o meno del solito?» | «Il mercato ora per ora: dopo quest'ora il prezzo sale (verde) o scende (rosso) più del solito?   (grigio = può essere caso)» |
| asse verticale «guadagno di un LONG tenuto H barre, rispetto a un'ora qualsiasi» | «variazione del prezzo nelle H barre dopo, in più o in meno della media di tutte le ore (bp)» |
| asse orizzontale «ora in cui apri il trade (ora di UTC)» | «ora d'ingresso (UTC)» |
| tabella «Le fasce orarie oltre la quota di fortuna» | «Le ore che il caso da solo non spiega (in-sample, H barre, prima dei costi)» |
| colonna «Long: rispetto a un'ora qualsiasi (bp)» | «In più o in meno della media di tutte le ore (bp)», pips accanto come oggi |

Riquadro (cosa vedi · come leggerlo · adesso):
- **Cosa vedi.** «Per ogni ora del giorno (UTC): di quanto sale o scende in media
  il prezzo nelle H barre dopo, in più o in meno della media di tutte le ore, in bp.
  Sopra lo zero il prezzo tende a salire più del solito, sotto lo zero a scendere
  più del solito. Le stanghette nere sono l'oscillazione dovuta al caso.»
- **Come leggerlo.** «Verdi e rosse sono le ore che il caso da solo non spiega,
  anche contando che le ore guardate sono tante; grigie le altre. Ore vicine
  raccontano lo stesso fatto: un gruppo colorato è un'idea sola. È una media su
  tutti i giorni dell'in-sample e non dice niente del singolo giorno. È il termine
  di paragone dei segnali: dalla 2c alla 4 ogni segnale si confronta con quello che
  il mercato fa da solo a quell'ora.»
- **Adesso.** «Vai alla 2c. Se vuoi un segnale a orario (es. `ORA_LONG_@12:30`: si
  entra ogni giorno alle 12:30 UTC), lo aggiungi alla 3b. Alla 4 puoi chiudere a
  un orario (`X_ORA_@16:00`), oppure quando arriva un'ora rossa per il long o
  verde per lo short (`X_INVERSIONE_TREND`).»

### A.1.3 · 2c: grafico, nota, dettaglio, riquadro (bozza)

| oggi | dopo |
|---|---|
| titolo «Trigger LONG: quanto fa meglio del mercato alla stessa ora, nelle H barre dopo il segnale (sopra lo zero = meglio)» | «Segnali LONG: quanti bp guadagnano in più (sopra lo zero) o in meno (sotto lo zero) del mercato, barra dopo barra dall'ingresso» |
| asse verticale «trade long: in più del mercato della stessa ora (bp, prima dei costi)» | «in più o in meno del mercato a quell'ora (bp, prima dei costi)» |
| asse orizzontale «barre dal segnale» | «barre dall'ingresso» |
| nota «N trigger misurati su M…» | «N segnali misurati su M (gli altri scattano meno di 200 volte: troppo pochi per fidarsi della media).» |
| dettaglio «Lo stesso confronto con il mercato a qualunque ora (quanto pesa l'ora del segnale)» | «Gli stessi segnali contro il mercato di tutte le ore (per vedere quanto pesa l'ora)» |
| colonna «Trigger» del dettaglio | «Segnale» |

Riquadro:
- **Cosa vedi.** «Ogni linea è un segnale. Barra dopo barra dall'ingresso, quanti bp
  guadagna in più (sopra lo zero) o in meno (sotto lo zero) di quello che il
  mercato fa da solo a quell'ora (il profilo della 2a), prima dei costi. Per long e
  short vale la stessa regola: sopra lo zero il segnale fa meglio del mercato. Sono
  i segnali più solidi della rosa (3a), al massimo 5 per lato.»
- **Come leggerlo.** «Una linea che sale e resta sopra lo zero indica un segnale che
  aggiunge qualcosa al mercato. La curva si legge, non si sceglie: la durata del
  trade resta l'orizzonte H che hai dichiarato alla schermata 1. Nel dettaglio sotto
  il grafico, gli stessi segnali contro il mercato di tutte le ore: serve a vedere
  quanto pesa l'ora.»
- **Adesso.** «Vai alla 3a: i segnali che la rosa suggerisce, con i numeri.»

La riga delle prove resta com'è («Prove · questa schermata: N trigger misurati…»),
con «segnali» al posto di «trigger».

## A.2 · Schermata 3b

### A.2.1 · Il campo «parti da»

| valore | punto di partenza per ogni lato |
|---|---|
| **la rosa** (predefinito) | i trigger «nella rosa», come oggi |
| **tutte le candidate** | tutti i trigger con «candidata = sì» nella rosa (`rosa_entry`: t > 0, quota di falsi positivi, due metà), compresi quelli lasciati fuori per famiglia o per correlazione |
| **niente** | nessuno: le casistiche sono solo quelle scritte in «aggiungi» |

- «Togli» si controlla sul punto di partenza scelto. Con «niente» deve restare
  vuoto, altrimenti la cella si ferma e lo dice.
- Con «tutte le candidate», la colonna «Da dove» della tabella dice per ognuno
  «rosa» oppure «candidata, fuori dalla rosa: famiglia già presente (E…)» o
  «candidata, fuori dalla rosa: correlata con E… (rho …)». È il motivo che la
  rosa scrive già nella colonna `perche`.
- Rosa vuota e «parti da = la rosa»: come oggi, la 3b parte vuota e lo dice.
- **Nessuna prova in più** (`67` §3.5): tutti i trigger del catalogo sono già
  contati alla 2c. La riga delle prove lo scrive come oggi.

### A.2.2 · Il modulo della cella (bozza)

```
#@title 3b · Le tue casistiche
#@markdown **Parti da** · `la rosa`: le casistiche suggerite dalla 3a («Nella rosa: sì») ·
#@markdown `tutte le candidate`: tutti i trigger che passano i controlli della rosa, anche quelli
#@markdown lasciati fuori per famiglia o correlazione · `niente`: scegli tu da zero con «aggiungi».
#@markdown **Togli**: nomi del punto di partenza da lasciare fuori. **Aggiungi**: qualunque trigger
#@markdown del catalogo di quel lato, anche fuori dalla rosa: i nomi sono nella classifica a
#@markdown scomparsa della 3a. Oppure un trigger a orario, es. `ORA_LONG_@12:30` (si entra ogni
#@markdown giorno a quell'ora UTC). Più nomi: separali con una virgola.
#@markdown **Spot: lascia vuoti i campi dello short** (lo short non esiste).
parti_da = "la rosa"  #@param ["la rosa", "tutte le candidate", "niente"]
togli_long = ""  #@param {type:"string"}
aggiungi_long = ""  #@param {type:"string"}
togli_short = ""  #@param {type:"string"}
aggiungi_short = ""  #@param {type:"string"}
```

Nota: oggi su main i quattro campi della 3b non sono vuoti. Contengono
`E21_BELT_HOLD`, `E22_ASIAN_RANGE_BREAKOUT`, `E39_SHORT_HOUR_REVERSAL_DOWN` e
`ORA_SHORT_@23:00`, rimasti dal salvataggio da Colab del 26/10. La PR A li rimette
vuoti, perché il predefinito del Lab è la rosa così com'è.

### A.2.3 · Tabella e riquadro (bozza)

Tabella «Le tue casistiche»: Lato · Parti da · Trigger (in OR) · Da dove.

- **Cosa vedi.** «Le tue casistiche, lato per lato: da dove sei partito, cosa hai
  tolto, cosa hai aggiunto. Più trigger sullo stesso lato lavorano insieme: si
  entra quando ne scatta uno qualsiasi.»
- **Come leggerlo.** «Scegliere, togliere o aggiungere non aggiunge prove: tutti
  i trigger del catalogo sono già contati alla 2c. Con «tutte le candidate» entrano
  anche trigger della stessa famiglia o molto correlati: scattano spesso sulle
  stesse candele, quindi aggiungono trade simili più che idee nuove.»
- **Adesso.** «Vuoi provare un trigger alla volta, ciascuno con le sue uscite? È il
  lavoro del portafoglio di sistemi, rimandato. Oggi si fa rieseguendo la 3b con un
  trigger solo, poi con un altro. Ogni giro conta le sue prove alla 4 e alla 5,
  come sempre. Poi vai alla 3c (facoltativa) o alla 4.»

### A.2.4 · Notebook di ricerca

Una variabile `PARTI_DA = "rosa"` (valori `"rosa"`, `"candidate"`, `"niente"`)
nella cella delle casistiche long e la stessa per lo short. Le due celle chiamano
`casistiche_dalla_rosa(rosa, d, TOGLI, AGGIUNGI, parti_da=PARTI_DA)`, la stessa
funzione del Lab.

## A.3 · Schermate 3c e 3d

### A.3.1 · La cella di testo del notebook

Nella cella «3 · Le casistiche» il punto su 3c e 3d diventa il testo deciso
(`72` §A.1):

> **3c · Dove funziona il segnale (facoltativo).** Lo stesso segnale può
> funzionare bene in certe condizioni di mercato e male in altre. L'atlante
> divide la storia in situazioni (volatilità alta o bassa, trend a favore o
> contro, la sessione: Asia, Europa, Londra+New York, America; sui perpetual la
> basis alta o bassa) e mostra per ognuna se il segnale fa meglio del mercato e
> se paga i costi.
>
> **3d · Scegli una situazione (facoltativo).** Se ne scegli una, il segnale
> scatterà solo lì. È una scelta in più fatta sui dati: per questo l'asticella
> della solidità tiene conto di tutte le situazioni che l'atlante ha guardato.

I titoli delle celle diventano «3c · Dove funziona il segnale (facoltativo)» e
«3d · Scegli una situazione (facoltativo)». Nei testi «cella» diventa «situazione»;
nel codice i nomi restano (`scegli_cella`, `cella_long`, `CELLA_…`).

### A.3.2 · I nomi delle situazioni in chiaro

| nome (da scrivere alla 3d) | in chiaro |
|---|---|
| VOL_BASSA_TREND_CONTRO | volatilità bassa, trend contro |
| VOL_BASSA_TREND_FAVORE | volatilità bassa, trend a favore |
| VOL_ALTA_TREND_CONTRO | volatilità alta, trend contro |
| VOL_ALTA_TREND_FAVORE | volatilità alta, trend a favore |
| ASIA_NOTTE | Asia (e fine settimana) |
| EUROPA | Europa (Londra aperta, New York chiusa) |
| LONDRA_NY | Londra + New York |
| AMERICA | America (New York aperta, Londra chiusa) |
| BASIS_ALTA | basis alta (perpetual caro sullo spot) |
| BASIS_BASSA | basis bassa (perpetual a buon mercato sullo spot) |

Le tabelle mostrano tutte e due le colonne: «Situazione» in chiaro e «Nome da
scrivere alla 3d».

### A.3.3 · La tabella di ogni segnale (bozza)

| oggi | dopo |
|---|---|
| Cella | Situazione · Nome da scrivere alla 3d |
| Occasioni | Occasioni |
| Più del mercato della cella (bp) | In più del mercato della situazione (bp), prima dei costi |
| Solidità | Solidità |
| Netto per occasione (bp) | Netto dei costi per occasione (bp) |
| (le due colonne in pips) | come oggi |
| Passa | **Batte il mercato** (sì / no) · **Paga i costi** (sì / no) |
| Perché no | Perché non passa |
| — | **Si può scegliere alla 3d**: «sì» · «sì, ma non passa» · «no: meno di 200 occasioni» |

- «Batte il mercato: sì» vuol dire solidità sopra zero, oltre la quota di colpi
  di fortuna su tutte le situazioni misurate, e positiva in tutte e due le metà
  dell'in-sample. «Paga i costi: sì» vuol dire netto sopra zero. Sono i controlli
  di oggi, divisi in due colonne. «Passa» = tutte e due più almeno 200 occasioni,
  come oggi.
- I motivi in chiaro: «meno di 200 occasioni», «non batte il mercato», «può
  essere fortuna», «non batte il mercato in una delle due metà», «non paga i
  costi». Si traducono in `vetrina.py`; la colonna `motivo` dell'engine non cambia.
- Grafico: titolo «<segnale> · quanto batte il mercato, situazione per situazione
  (solidità)», etichette in chiaro.
- Tabella riassuntiva: «I segnali con almeno una situazione che passa», colonne
  Segnale · Lato · Situazioni che passano · Solidità più alta.

### A.3.4 · Riquadro della 3c (bozza)

- **Cosa vedi.** «Per ogni segnale, una situazione alla volta: volatilità alta o
  bassa con trend a favore o contro (4), la sessione in cui si apre il trade (4:
  Asia, che comprende il fine settimana, Europa, Londra + New York, America), sui
  perpetual la basis alta o bassa (2). In ogni situazione: quanto il segnale batte
  il mercato della stessa situazione e della stessa ora (bp, prima dei costi) e
  quanto resta dopo commissione, spread e funding.»
- **Come leggerlo.** «"Batte il mercato" vuol dire che fa meglio del mercato della
  situazione anche contando tutte le N situazioni misurate, in tutte e due le metà
  dell'in-sample. "Paga i costi" vuol dire che resta positivo dopo i costi. È una
  mappa: dice dove il segnale sembra funzionare, non che funziona.»
- **Adesso.** «Se vuoi, scegli una situazione alla 3d: va bene qualunque
  situazione con almeno 200 occasioni, anche una che non passa. Altrimenti vai alla
  4: la strada di sempre, con tutti i filtri al passo 5.»

### A.3.5 · 3d: qualunque situazione misurata

**Regola** (decisione 3 di `72` §A.3). Su un lato si può scegliere una
situazione se l'atlante l'ha **misurata** (almeno 200 occasioni) per almeno uno dei
trigger del lato. Se il lato ha più trigger in OR, la situazione vale per tutta
la casistica, come oggi.

| caso | cosa succede |
|---|---|
| la situazione passa per almeno un trigger del lato | come oggi |
| misurata, ma non passa per nessun trigger del lato | si sceglie, con l'**avviso arancione**: «Nell'in-sample questa situazione non batte il mercato, o non paga i costi: la scegli sapendolo.» Sotto, il motivo per ogni trigger («E21_BELT_HOLD: non paga i costi») |
| non misurata (meno di 200 occasioni per ogni trigger del lato) | la cella si ferma, per esempio: «La situazione EUROPA ha N occasioni per E21_BELT_HOLD nell'in-sample: sotto le 200 l'atlante non la misura, quindi non si può scegliere. Situazioni misurate su questo lato: …» |
| nome sconosciuto | come oggi: l'elenco dei nomi possibili |

- **Nessuna prova in più.** L'atlante conta già tutte le situazioni che misura
  (k_atlante) e il passo 5 usa già quell'asticella. Scegliere fra 10 situazioni
  invece che fra le 2 che passano non cambia il conto. La riga delle prove resta
  «nessuna (le situazioni sono già contate alla 3c)».
- La tabella «La situazione scelta» aggiunge le colonne «Batte il mercato» e
  «Paga i costi».
- Un segnale a orario ha occasioni in una sola sessione: le altre restano non
  misurate e quindi non si possono scegliere. È il comportamento di oggi, scritto
  in chiaro.

Modulo della cella (bozza):

```
#@title 3d · Scegli una situazione (facoltativo)
#@markdown Una situazione misurata dall'atlante per il tuo segnale (colonna «Nome da scrivere alla
#@markdown 3d» della 3c), al massimo una per lato, es. `EUROPA` o `VOL_ALTA_TREND_FAVORE`. Va bene
#@markdown anche una che non passa: lo strumento te lo dice. Sotto le 200 occasioni non si può.
#@markdown Il segnale scatterà solo lì: le uscite (schermata 4) si costruiscono già sul segnale
#@markdown dentro la situazione. Vuoto = nessuna: al passo 5 si provano tutti i filtri, come sempre.
cella_long = ""  #@param {type:"string"}
cella_short = ""  #@param {type:"string"}
```

**Notebook di ricerca:** la cella delle celle scelte (`CELLA_LONG`, `CELLA_SHORT`)
usa la stessa regola, con una funzione comune in `vetrina.py`. Si ferma sotto le
200 occasioni e stampa l'avviso se la situazione non passa.

## A.4 · Schermata 5 con una situazione scelta

Il comportamento non cambia (strada B di `66` §5). Cambiano solo i testi.

**Cella di testo del notebook (bozza):**

> **5 · Trova la strategia.** Lo strumento prova tutti i filtri disponibili sul
> sistema scelto alla 4b, uno alla volta. Richiede circa mezzo minuto.
>
> **Se alla 3d hai scelto una situazione**, qui si misura solo lei: il segnale
> dentro la situazione contro il segnale da solo. Gli altri filtri non si
> provano: la situazione è già un filtro, scelto guardando i dati, e provarne altri
> sopra vorrebbe dire scegliere due volte.

**Riquadro, strada B (bozza):**
- **Cosa vedi.** «Hai scelto una situazione alla 3d (Europa). Qui si misura solo
  lei: lo stesso sistema, con le stesse uscite (quelle della schermata 4), una
  volta con il segnale da solo e una volta con il segnale dentro la situazione. Di
  quanto migliora il guadagno per trade scartando i trade fuori dalla situazione,
  in bp.»
- **Come leggerlo.** «Gli altri filtri non si provano. La situazione è già un
  filtro, e l'hai scelta guardando i dati dell'atlante: provarne altri sopra vorrebbe
  dire scegliere due volte sugli stessi dati. Per lo stesso motivo l'asticella è
  quella di tutte le N situazioni che l'atlante ha guardato, non quella di una prova
  sola. Se la situazione la supera, passa alla seconda prova, sulle due metà.»
- **Adesso.** Come oggi, più una riga: «Per provare i filtri del catalogo, torna alla
  3d e lascia vuota la situazione.»

**Tabella e imbuto, strada B:**

| oggi | dopo |
|---|---|
| riga «Sistema base (nessun filtro)» | «Il segnale da solo (senza la situazione)» |
| riga «CELLA_EUROPA» | «Il segnale dentro la situazione: Europa (CELLA_EUROPA)» |
| imbuto «Filtri provati (una coppia long/short conta per uno)» | «Righe provate: la situazione scelta» |
| imbuto «Migliorano davvero il sistema base» | «Migliora davvero il segnale da solo» |
| imbuto «Reggono su entrambe le metà dello storico» | «Regge su entrambe le metà dello storico» |
| titolo della tabella «I filtri migliori (in-sample, al netto dei costi)» | «Il segnale con e senza la situazione (in-sample, al netto dei costi)» |

Il nome da scrivere nella scheda (schermata 6) resta `CELLA_…`, e la tabella lo
mostra fra parentesi. Senza situazione scelta (strada A) la schermata 5 non cambia.

## A.5 · Cosa cambia nel codice, collaudo, identità

**Codice (tutto additivo, salvo i testi):**
- `engine/vetrina.py`: testi, titoli ed etichette di `profilo_delle_ore`,
  `grafico_scarto`, `esplora`, `_imposta_casistiche`, `atlante_dei_trigger`,
  `grafico_atlante`, `scegli_cella`, `trova_strategia`. Poi il parametro
  `parti_da="rosa"` di `casistiche_dalla_rosa` e `parti_da="la rosa"` di
  `scegli_casistiche`, e una funzione comune per la regola della 3d, usata da Lab e
  ricerca.
- `engine/atlante.py`: due funzioni nuove, `nome_in_chiaro(cella)` e
  `celle_misurate(tab, trigger)`. `etichetta_cella`, `celle_che_passano` e
  `_motivo` non cambiano.
- `Trading_System_Lab_Crypto.ipynb`: le celle di testo 2, 3 e 5; i titoli 2a, 2c,
  3c, 3d; il campo «parti da» e i campi della 3b vuoti; il modulo della 3d. Si
  modifica il JSON con uno script: NotebookEdit rovina il formato.
- `Trading_Grid_Search_v4_backtesting.ipynb`: `PARTI_DA` e la regola della 3d.
- `docs/00`: «44 suite» al posto di «43» (la suite completa oggi ne conta 44); nei
  prossimi lavori l'ordine nuovo (la mappa prima del volume aggressivo, `72` §B.2.5).

**Test nuovi** (in `test_riordino_lab.py` e `test_atlante.py`, a risultato noto):
1. `parti_da`: «la rosa» = come oggi; «tutte le candidate» = tutte e sole le
   righe con `candidata` del lato; «niente» con «togli» pieno si ferma; il conto
   delle prove non cambia in nessuno dei tre casi.
2. Con «tutte le candidate», la colonna «Da dove» riporta il motivo della rosa.
3. 3d: una situazione misurata che non passa si sceglie, compare l'avviso e
   l'entry «TRIGGER+CELLA_…» è la stessa che si avrebbe se passasse.
4. 3d: una situazione con 199 occasioni si ferma con il messaggio giusto; con
   200 si sceglie.
5. 3d con due trigger in OR: misurata per uno solo dei due → si sceglie.
6. Strada B con una situazione che non passa: il passo 5 misura solo lei, con
   l'asticella a k_atlante e senza prove in più.
7. `nome_in_chiaro` copre tutte le celle di `CELLE`.

**Identità** (vincolo di `72` §A.4). A scelte uguali, cioè con la 3b vuota, la
rosa così com'è, nessuna situazione o la stessa che passa, uscite consigliate e
«Long + Short», restano identici al bit event study, profilo, rosa, atlante,
uscite, sistemi, filtri, due metà e scheda. Si verifica su BINANCE_PERP_BTCUSDT
nei due notebook, prima e dopo, con un giro completo su BYBIT_SPOT_ETHUSDT. Cambiano
solo testi, titoli e intestazioni.

**Testi con Mattia:** le bozze sopra si rivedono nella PR A prima del merge, sul
notebook già eseguito.

---

# PARTE B · La mappa delle anomalie

## B.1 · Il notebook della mappa

`Mappa_Anomalie_Crypto.ipynb`, con celle che chiamano solo funzioni dell'engine,
come il Lab.

| cella | cosa fa | decide l'utente |
|---|---|---|
| Avvio | come il Lab (stessa funzione): repo, librerie, cartella dei dati, macchina | aggiorna i dati (solo PC) |
| 1 · Il dataset | apre il dataset nello studio: stesso confine, impronta dell'in-sample, giornali. **Non scrive nessun H**: la mappa non ha l'orizzonte del Lab, ogni scheda ha il suo | symbol, timeframe |
| 2 · Le schede | l'elenco delle schede approvate (§B.2), con lo stato su questo dataset (mai misurata / misurata il …) e su quanti altri dataset è già stata misurata | — |
| 3 · La mappa di una scheda | carica i dataset di appoggio che servono (spot, funding, BTC), calcola le fasce, misura, mostra grafico, tabella e verdetto (§B.3), scrive nel giornale (§B.4) | il nome della scheda |
| 4 · Tutte le schede non ancora misurate (facoltativa) | come la 3, una scheda dopo l'altra | — |
| 5 · Dalla fascia al trigger | per le schede con esito «risponde»: la bozza in testo del trigger da portare nel processo di `50` (§6, domanda 6). Nessun codice | — |
| 6 · Riepilogo | le schede misurate sul dataset, le prove della mappa e la soglia cumulata del dataset, con gli stessi conti del Lab | — |

Ogni schermata ha la riga **Prove**, come il Lab. Se l'out-of-sample del dataset è
già stato guardato, compare il riquadro arancione del `68` §9: una scheda scritta
dopo averlo guardato non è più una prova pulita.

## B.2 · La scheda dell'ipotesi

### B.2.1 · I campi

| campo | contenuto |
|---|---|
| id, versione, data | es. `M01_FUNDING_ESTREMO`, versione 1, la data dell'approvazione |
| meccanismo | chi è costretto a perdere, e perché, in due o tre righe |
| da dove viene l'idea | un paper, un libro, il meccanismo da solo; **oppure qualcosa già visto nei dati** (es. il profilo 2a) e in quel caso lo si dice, e il conto lo tiene (§B.4) |
| variabile | il nome della colonna in `engine/indicatori.py`, nota al Close della barra |
| tipo di fasce | `quintili` (variabile continua: 5 fasce, finestra delle sole barre passate dichiarata, predefinito 365 giorni) oppure `categorie` (calendario: le categorie elencate, es. 7 giorni della settimana) |
| fascia attesa e segno | es. «Q5 → sotto il mercato (short)», «Q1 → sopra il mercato (long)»; una o più fasce, ciascuna con il suo verso |
| orizzonte | in ore, dal meccanismo (es. 24 ore = tre pagamenti di funding) |
| mercato di riferimento | `stessa ora` oppure `qualunque ora` (regola fissa per tipo, §6 domanda 1) |
| serve | dati in più: funding, spot, un altro dataset (es. BINANCE_PERP_BTCUSDT) |
| portabilità su TradingView | sì / approssimata (con cosa) / no |
| dataset | dove ha senso misurarla (es. «solo perpetual», «solo altcoin») |

**Una scheda che non sa dare un segno non si scrive.** È il filtro che tiene fuori
le variabili «interessanti» ma senza un'ipotesi (§B.6, la volatilità).

### B.2.2 · Un esempio, solo per il formato (non approvato, non misurato)

```
M01_FUNDING_ESTREMO · versione 1
meccanismo   Con il funding molto positivo chi è long a leva paga ogni 8 ore e le posizioni
             lunghe sono affollate: a una discesa scattano liquidazioni a catena. Con il funding
             molto negativo, lo stesso sugli short.
idea da      meccanismo (letteratura sul funding dei perpetual); nulla di già visto sui dati
variabile    funding_ultimo: l'ultimo tasso liquidato, noto dall'istante del pagamento
fasce        quintili, finestra 365 giorni di barre passate
attesa       Q5 → sotto il mercato (short) · Q1 → sopra il mercato (long)
orizzonte    24 ore
riferimento  stessa ora
serve        funding (dati/<SYMBOL>_FUNDING.csv)
portabilità  approssimata: TradingView non vede il funding; la basis (perpetual meno spot,
             due symbol che TradingView vede) ne è la parente più vicina
dataset      solo perpetual
```

## B.3 · La misura e il verdetto

**Le fasce, senza guardare nel futuro.** Per una variabile continua, le soglie
dei quintili alla barra i si calcolano sulle barre **prima** di i, dentro la
finestra della scheda. La variabile alla barra i è nota al Close di i. Le prime
barre, finché la finestra non è piena, non hanno fascia: escono solo da questa
scheda, come le celle NaN dell'atlante. Il collaudo è per troncamento (§B.7).

**La misura di una fascia** (stessa convenzione di rosa e atlante: segnale i,
ingresso Open[i+1], misura Close[i+h], quarantena applicata):
- lo **scarto dal mercato** di riferimento, in bp con i pips accanto, nel verso
  della fascia attesa. Si usa `stagionalita.scarto_orario`, che tiene conto dei
  rendimenti sovrapposti e del rumore del riferimento. Le barre di una fascia sono
  spesso di seguito (il funding resta uguale per 8 ore) e l'incertezza lo sa già;
- la **solidità** (t) e il p a una coda nel verso dichiarato;
- le **due metà** dell'in-sample, con lo scarto nel verso dichiarato in tutte e due;
- il **netto dei costi**, come nell'atlante, **solo da leggere**: il verdetto
  dice se l'anomalia c'è, i costi si giudicano al Lab sul trigger vero.

**I minimi.** Almeno **200 barre** nella fascia (come `MIN_TRIGGER`) e almeno
**100 giornate diverse** (la soglia di circa 100 occorrenze di `50` §8). Il secondo
minimo serve alle variabili di calendario: 200 barre si raggiungono anche con pochi
giorni (22 scadenze trimestrali × 96 barre M15). Sotto i minimi la fascia è
grigia, «troppo pochi casi», e non entra nel conto.

**Il verdetto della scheda.**

| esito | quando |
|---|---|
| **risponde nel verso atteso** | una fascia attesa supera tutti i controlli: scarto nel verso dichiarato, quota di falsi positivi (Benjamini–Hochberg, q = 20%, sulle fasce della scheda), due metà, minimi |
| **non risponde** | nessuna fascia attesa supera i controlli |
| **segno opposto** | una fascia attesa supererebbe i controlli nel verso contrario. Si mostra con la scritta «segno opposto: non conta come scoperta» |
| **troppo pochi casi** | nessuna fascia attesa raggiunge i minimi |

Le fasce non dichiarate si mostrano con i loro numeri e la scritta «fuori
ipotesi». Non producono mai «risponde», e una scheda nuova che le prende come
attese dopo averle viste si dichiara tale (§B.4). Il cancello è lo stesso della rosa
(quota di falsi positivi per proporre). Il conto con Šidák resta quello della
soglia cumulata, solo informativo.

**Cosa si vede.** Un grafico a 5 barre (o una per categoria) con lo scarto e
l'incertezza. Le fasce attese hanno il bordo pieno; il colore indica se passano.
Sotto, la tabella delle fasce (occasioni, giornate, scarto in bp e pips,
solidità, due metà, netto, esito) e il riquadro del verdetto.

## B.4 · Lo studio e il conto

**Un'apertura senza H.** La mappa entra nello studio con `studio.entra` (confine,
impronta) e ricostruisce il registro del dataset dai giornali, ma non chiama
`prepara`: `prepara` scriverebbe una voce «orizzonte» e la mappa sporcherebbe gli
H provati del Lab.

**Il conto, nel giornale che esiste già.** Ogni scheda misurata scrive una voce
«prova» con `dove = "mappa"`, chiave (id, versione, orizzonte in ore) e n = fasce
misurate. È il formato che `registro_dataset.da_voci` legge già: nessun tipo di voce
nuovo, quindi il formato dei giornali non cambia.
- Rimisurare la stessa scheda non conta di nuovo (stessa chiave).
- **Una scheda cambiata dopo averla misurata** è una versione nuova: si conta
  di nuovo e si annota come risalita («scheda M01 cambiata dopo la misura»).
- **Un'idea presa da qualcosa già visto nei dati** porta con sé il conto di quello
  che si è guardato. Esempio: un'ora presa dal profilo 2a porta le fasce del
  profilo, come oggi un trigger a orario (`vetrina._imposta_casistiche`).

**Gli esiti, in un file a parte.** Il verdetto e la tabella di ogni scheda vanno in
`studio/<dataset>/mappa_<macchina>.jsonl`, uno per macchina e solo in aggiunta,
con le stesse regole dei giornali (`70` §4.3). Il Lab li legge per la 2b. Così
`da_voci`, che si ferma su un tipo di voce che non conosce, resta com'è.

**Nel Lab.** `_soglia_da_conti` riceve un parametro nuovo `mappa=0`. La soglia
cumulata e la riga delle prove aggiungono la voce «N fasce della mappa (2b)».
Senza schede misurate il conto è identico a oggi.

## B.5 · Il posto 2b del Lab

Una funzione `mappa_del_dataset(s)`, chiamata dalla cella 2b, **in sola lettura**:

| Scheda | Meccanismo | Fascia attesa e segno | Orizzonte (ore) | Esito | Misurata il | Fasce contate | TradingView | Trigger nato |
|---|---|---|---|---|---|---|---|---|

- Legge solo `mappa_*.jsonl` del dataset: non misura e non scrive niente.
- Riga delle prove: «questa schermata: nessuna (le fasce della mappa sono già nel
  conto del dataset)».
- Il registro si ricostruisce alla schermata 1. Una scheda misurata nel notebook
  della mappa mentre il Lab è aperto compare alla prossima schermata 1, e il
  riquadro della 2b lo dice.
- Senza schede su questo dataset: «Nessuna scheda della mappa misurata su questo
  dataset».

## B.6 · La prima versione: quali meccanismi (tabella B.3 del `72`)

Criteri per la prima versione: **dati già in casa**, causalità semplice da
collaudare, abbastanza casi nell'in-sample, un segno atteso dal meccanismo.

| meccanismo | variabile | prima versione? | perché |
|---|---|---|---|
| calendario | **ore del funding** (00/08/16 UTC), insieme al segno del funding in corso | **sì** | tre volte al giorno, migliaia di casi; il meccanismo dà un segno (chi deve pagare chiude prima del pagamento), quindi la variabile è l'ora **e** il segno del funding |
| calendario | **giorno della settimana, fine settimana** | **sì**, se la scheda trova un segno | circa 280 fine settimana nell'in-sample di BTC. Il fine settimana sta già, mescolato con l'Asia, in ASIA_NOTTE dell'atlante; la mappa lo guarda da solo |
| calendario | **apertura USA** (09:30 di New York) | **sì** | in UTC si sposta di un'ora con l'ora legale, quindi il profilo 2a (in UTC) la vede sfocata per metà anno; la mappa la guarda all'ora di New York |
| calendario | venerdì delle opzioni (scadenza mensile, ultimo venerdì 08:00 UTC) | **dopo** | circa 65 scadenze nell'in-sample: sotto le 100 giornate. Si riapre con più storia |
| calendario | scadenze trimestrali | **dopo** | circa 22 nell'in-sample: troppo poche |
| posizionamento e leva | **funding estremo** | **sì** | i file del funding ci sono per tutti i perpetual; esempio al §B.2.2 |
| posizionamento e leva | **basis** | **sì** | `indicatori.basis_bp` esiste, lo spot è già agganciato ai perpetual (`aggancia_spot`). L'atlante la divide in due (sopra o sotto la mediana); la mappa in quintili. Copre anche «perpetual contro spot» |
| chi arriva prima | **rendimento recente di BTC per le altcoin** | **sì** | è il motivo del notebook a parte: stesso exchange, stessa griglia di barre (§6, domanda 5). Solo su ETH, SOL, XRP |
| chi arriva prima | perpetual contro spot | **sì, con la basis** | la basis è già la distanza fra i due. Chi si muove prima (rendimento recente dello spot meno quello del perpetual) viene dopo, se la basis risponde |
| chi arriva prima | un exchange contro l'altro | **dopo** | le storie Bybit sono più corte (in-sample dal 73% al 79%). A 15 minuti la differenza fra le chiusure di due exchange è fatta soprattutto di rumore di microstruttura. Serve un allineamento fra exchange che la prima versione non ha |
| comportamento | **rendimento delle ultime ore in fascia estrema** | **sì** | solo prezzo. La scheda deve scegliere prima il segno (inversione dopo gli eccessi, o continuazione) e controllare i doppioni con E41 (quintile della giornata) e i trigger di momentum (riga DOPPIONI) |
| comportamento | distanza dai massimi o minimi recenti | **dopo** | la finestra è un parametro libero in più, ed è vicina ai trigger di rottura del catalogo (E22 e simili) |
| regime | volatilità recente | **dopo**, come seconda variabile | da sola non ha un segno atteso sul verso del prezzo: dice quanto si muove, non dove. È già un asse dell'atlante. Torna come condizione di un'altra scheda (es. il rendimento estremo con la volatilità alta) |

**In tutto, prima versione:** 7 schede (ore del funding, giorno della settimana,
apertura USA, funding estremo, basis, BTC per le altcoin, rendimento recente).
Le schede si scrivono in testo dopo il merge di questa proposta e si approvano
una per una, **prima** di qualunque misura (§7). Se si misurano tutte, sono circa 35
fasce nel conto di ogni dataset: 5 per le quattro schede a quintili, più le
categorie di calendario.

**Il volume aggressivo** (decisione 5 di `72` §B.2) entra dopo, come scheda in
più, quando avrà il suo lavoro sui dati.

## B.7 · Codice, collaudo, tempi

**Moduli (tutti nuovi o additivi):**
- `engine/indicatori.py`: le variabili (`funding_ultimo`, `rendimento_recente`,
  il rendimento di BTC allineato, le categorie di calendario), una colonna ciascuna.
- `engine/ipotesi.py`: il dizionario `SCHEDE`, come i dizionari del catalogo.
- `engine/mappa.py`: fasce dalle barre passate, misura, verdetto, voce del conto.
- `engine/studio.py`: lettura e scrittura di `mappa_<macchina>.jsonl`, l'apertura
  senza H.
- `engine/vetrina_mappa.py`: le schermate del notebook della mappa. Un file a
  parte per non appesantire `vetrina.py` (oltre 4.000 righe); usa i suoi pezzi
  comuni (riquadri, riga delle prove). Decisione D4 del §8.
- `engine/vetrina.py`: `mappa_del_dataset(s)` per la 2b e il parametro `mappa=`
  della soglia.
- `test_mappa.py`, con la sua riga in `suite_rapida.py`.

**Test a risultato noto:**
1. Fasce: su una serie costruita, le soglie alla barra i usano solo barre prima
   di i; troncando i dati alla barra i le fasce fino a i non cambiano; finestra non
   piena = nessuna fascia; valori uguali al confine fra due fasce vanno sempre
   nella stessa.
2. Misura: un effetto noto messo apposta in Q5 si ritrova con il segno e la
   grandezza giusti; senza nessun effetto, su 1.000 giri a seme fisso,
   «risponde» non esce più spesso di quanto consente il livello q.
3. Riferimento: una variabile «ora del giorno» misurata contro la stessa ora dà
   zero per costruzione; contro qualunque ora dà il profilo 2a.
4. Verdetto: i quattro esiti, compreso «segno opposto» e la fascia «fuori ipotesi»
   che non dà mai «risponde»; i minimi delle 200 barre e delle 100 giornate.
5. Funding: un tasso liquidato all'istante T entra solo dalle barre che si chiudono
   dopo T (troncamento).
6. Fra dataset: BTC con barre mancanti dà NaN solo lì; BTC più corto accorcia
   l'in-sample della scheda e la schermata lo dice; nessuna barra oltre il confine.
7. Conto: stessa scheda rimisurata = nessuna prova in più; versione nuova = prove
   in più e una risalita; la voce scritta dalla mappa si ritrova nella soglia del Lab.
8. La 2b del Lab non cambia `s.prove` e mostra quello che c'è in `mappa_*.jsonl`.
9. Orizzonte in ore che non è un numero intero di barre (1 ora su H4): la scheda
   non si misura su quel timeframe, con il messaggio.

**Identità:** il Lab senza schede misurate resta identico al bit (la voce della
mappa vale zero). Con schede misurate cambiano solo la soglia cumulata e la riga
delle prove.

**Tempi, misurati il 26/10** sull'in-sample di BINANCE_PERP_BTCUSDT M15
(190.660 barre). Solo tempi, nessun numero sui dati:
- quintili mobili su 30 giorni: 0,5 secondi; su 365 giorni: 0,9 secondi;
- scarto dalla stessa ora con incertezza, 5 fasce per 4 orizzonti: 0,8 secondi.

Stima per scheda, con un orizzonte: circa 2 secondi. In più ci sono il caricamento
dei CSV e degli indicatori che servono, la parte lenta, da 10 a 30 secondi per
dataset, e i dataset di appoggio (spot, BTC). La prima versione intera su un
dataset richiede meno di un minuto. Su M5 le barre sono il triplo: circa 3 volte.

---

## 6 · Le sette domande del `72` (la proposta risponde, Mattia decide)

**1 · Il termine di paragone.** Una regola fissa per tipo di variabile, scritta
nella scheda e non scelta dopo:
- **variabili non di calendario** (funding, basis, rendimenti, BTC): **il mercato
  della stessa ora**, come la rosa. Così la mappa non riscopre il profilo orario
  sotto un altro nome: una fascia che cade spesso in ore «buone» non sembra brava
  per l'ora;
- **variabili di calendario** (ore, giorni, aperture): **il mercato a qualunque
  ora**, come l'atlante per i trigger a orario dal 23/10. Contro la stessa ora
  darebbero zero per costruzione (test 3 del §B.7).

**2 · La misura di una fascia.** Scarto in bp (pips accanto), solidità con i
rendimenti sovrapposti, due metà, quota di falsi positivi a q = 20% sulle fasce
della scheda, come la rosa. Il verdetto guarda solo le fasce attese nel verso
atteso. Minimi: 200 barre e 100 giornate. Il netto dei costi si mostra ma non
decide (§B.3).

**3 · Dove vivono le schede.** In tutti e due i posti, con compiti diversi:
- **`engine/ipotesi.py`**, nel repo: la scheda come dato, che il notebook legge.
  Sta su GitHub, quindi la data del commit prova che la scheda è stata scritta
  prima della misura, che sta nel giornale dello studio con la sua ora;
- **un registro in `docs/`**, un file nuovo `docs/74_REGISTRO_IPOTESI.md` con una
  riga per scheda come `50` §10: meccanismo, da dove viene l'idea, data, esito per
  dataset, prove, trigger nato. Lo studio (fuori da GitHub) tiene solo misure e conto.

**4 · Come si conta.** Ogni fascia misurata (sopra i minimi) è una prova: fasce
× orizzonti × schede, nel conto del dataset su cui si misura.
- L'orizzonte della scheda costa 1. Un orizzonte diverso è una versione nuova
  della scheda: si conta e si annota come risalita. La griglia di orizzonti si
  rimanda al lavoro degli orizzonti multipli (`68` §13).
- **Verso il Lab** il conto passa da solo: stesso studio, stesso dataset, stesso
  giornale (§B.4). Il trigger nato dalla mappa, una volta nel catalogo, è anche uno
  dei trigger misurati alla 2c. È un secondo conto dello stesso effetto e lo tengo,
  per prudenza, come per l'atlante sommato ai trigger (`66` §6).
- **Fra dataset** (una scheda misurata su BTC, ETH e SOL): resta per dataset, come
  oggi. Il conto fra dataset è del lavoro dei testimoni (`70` §14). Nel frattempo
  la mappa e la 2b dicono su quanti altri dataset la scheda è già stata misurata.

**5 · Le variabili fra dataset.**
- **Allineamento:** sullo stesso exchange le barre hanno la stessa griglia UTC. La
  barra i di BTC si chiude nello stesso istante della barra i di ETH, quindi il
  suo rendimento è noto al Close di i. Si allinea per data della barra, mai «la
  barra più vicina». Una barra che manca in BTC dà NaN su quella barra, solo per
  quella scheda, come la basis senza spot.
- **Storia più corta:** la scheda si misura sulle barre in cui ci sono tutti e due
  i dataset. La schermata dice da quando e che quota dell'in-sample resta; sotto il
  50% avvisa, come lo studio (`SOGLIA_IS_CORTO`).
- **Confine:** è un istante unico per tutto lo studio. Il dataset di appoggio si
  taglia allo stesso istante e passa il controllo della sua impronta: nessuna barra
  dell'out-of-sample entra da nessuna parte.
- Timeframe diversi fra i due dataset: non nella prima versione.

**6 · Dalla fascia al trigger.** **Sempre con il processo di `50`.** Il notebook
scrive soltanto la **bozza in testo** (cella 5): nome proposto, regola in parole,
lato, orizzonte, portabilità, prove già contate. La scheda di `50` §3, il via di
Mattia, il codice in `entry_long.py` / `entry_short.py` con la variabile in
`indicatori.py`, `verifica_lookahead` e `verifica_degenerazione` restano come oggi.
Un punto di metodo da sapere: la mappa misura uno **stato** (tutte le barre in cui
la variabile è nella fascia), mentre un trigger è un **evento** (`50` §4: un'entry
è sempre una transizione). Il trigger naturale è quindi «la variabile **entra**
nella fascia». Può comportarsi diversamente dalla fascia intera, perché scatta
solo all'inizio, e il Lab lo misura per quello che è. Uno stato può anche diventare
un filtro (`50` §4); con `72` il ponte è il trigger, il filtro resta una
possibilità da decidere caso per caso.

**7 · Tempi.** Misurati oggi (§B.7): circa 2 secondi per scheda su M15, più il
caricamento dei dati (10–30 secondi per dataset). La prima versione intera su un
dataset richiede meno di un minuto; su M5 circa il triplo.

---

## 7 · Consegna

| passo | cosa | prove |
|---|---|---|
| **PR A · Lab più chiaro** | §A.5: vetrina, atlante, i due notebook, test, `docs/00` (44 suite, ordine dei lavori) | suite completa; identità su BTC perp e giro su ETH spot Bybit; i testi rivisti con Mattia |
| **Schede della prima versione** (dopo il merge di A) | le 7 schede in testo, nel registro `docs/74`; il via di Mattia scheda per scheda. Nessuna misura | — |
| **PR B · La mappa** | §B.7: engine, notebook della mappa, 2b del Lab, le schede approvate in `engine/ipotesi.py`, `test_mappa.py` | suite completa; identità del Lab senza schede; un giro di collaudo della mappa su BTC perp |

## 8 · Decisioni per Mattia

| | domanda | proposta |
|---|---|---|
| D1 | «segnale» nei testi delle schermate 2, 3c, 3d, 5 e «trigger» per i nomi del catalogo e i campi | sì |
| D2 | «situazione» al posto di «cella» nei testi (il codice resta «cella») | sì, come nel testo deciso |
| D3 | i nomi in chiaro delle situazioni (§A.3.2) | come in tabella |
| D4 | il notebook della mappa con un `engine/vetrina_mappa.py` a parte | sì |
| D5 | finestra dei quintili predefinita: 365 giorni. Costa il primo anno di ogni dataset (su BTC circa il 18% dell'in-sample); 90 giorni costa meno storia ma segue di più il regime | 365, come F36 |
| D6 | le sette domande del §6 | come scritto |
| D7 | la prima versione del §B.6 (7 schede) | come in tabella |
| D8 | il registro delle ipotesi in un file nuovo `docs/74` | sì |

## 9 · Rischi

- **Schede scritte dopo aver visto i dati.** Sul BTC abbiamo già visto profilo,
  rosa e atlante. Un'idea che nasce da lì non è un'ipotesi scritta prima: il campo
  «da dove viene l'idea» lo dichiara e il conto ne tiene conto (§B.4). Se il campo
  si riempie male, il conto è troppo ottimista.
- **Troppe schede.** Ogni scheda alza l'asticella di tutto il dataset, Lab
  compreso. La prima versione è piccola apposta.
- **Stato e evento.** Una fascia che risponde non dice che il trigger «entra nella
  fascia» risponderà: il Lab lo rimisura (§6, domanda 6).
- **Due notebook aperti sullo stesso dataset.** La 2b vede le schede nuove solo
  alla prossima schermata 1; il riquadro lo dice.
- **Testi lunghi.** Le bozze della parte A sono più lunghe di oggi in alcuni
  riquadri; nella revisione con Mattia si accorciano dove serve.
