# 20 · Condizioni tempo + prezzo — E22, E23, F20, F21, F22
 
**Data:** 22 settembre 2026 · aggiornato 24 settembre 2026 (trappole 4 e 5, F21 corretto)
**Prima di questo:** `00_SCOPO_E_STATO.md` e `11_DATI_QUARANTENA.md`
 
**File:** `engine/livelli.py` (nuovo, corretto due volte il 24/9), `entry_long.py` ed
`entry_short.py` (modificati), `filter_conditions.py` (modificato),
`test_tempo_prezzo.py` (20/20), `test_filtri_tempo.py` (25/25)
 
---
 
## Cosa aggiungono al tool
 
Una **famiglia di condizioni nuova**: il tempo definisce un livello, il prezzo
decide quando lo rompe. Prima il catalogo aveva solo condizioni di puro prezzo
(candlestick, RSI, EMA) e metro di puro tempo.
 
Più l'infrastruttura che le rende possibili, `engine/livelli.py`, che serve a
qualunque condizione futura basata su livelli da finestra temporale.
 
---
 
## `engine/livelli.py` — l'infrastruttura
 
### `range_finestra(df, inizio, fine=None, quarantena=None)`
 
Per ogni barra, i valori dell'**ultima finestra CONCLUSA** fra due momenti del
catalogo sessioni. Cinque colonne: `massimo`, `minimo`, `primo_open`,
`ultimo_close`, `pronto`.
 
- `range_finestra(df, "TOKYO", "LONDRA")` → il range asiatico
- `range_finestra(df, "ROLLOVER")` → la giornata FX intera
- `range_finestra(df, "NEW_YORK", "ROLLOVER")` → la sessione americana
**Confini e valori usano la quarantena in modo DIVERSO**, ed è il punto da
ricordare quando si scrivono condizioni nuove:
 
- **i confini** vengono dal calendario puro. Con la quarantena, `ROLLOVER` non
  scatterebbe mai (le sue barre sono sempre marcate) e la giornata FX non
  esisterebbe;
- **i valori** escludono le barre in quarantena. Un massimo giornaliero segnato
  alle 17:15 di New York può essere un artefatto del bid, e romperlo non
  significherebbe niente.
Conseguenza pratica: la "chiusura della sessione americana" è l'ultima barra
pulita, le **16:30 NY**, non le 16:45.
 
### `giorno_fx(df)`
 
La giornata di contrattazione ancorata al rollover delle 17:00 NY, ricavata
dalla **data FX** (ora di New York più 7 ore, così le 17:00 diventano
mezzanotte).
 
### `al_ultima_apertura(df, sessione, serie)`
 
Fotografa una grandezza sulla barra di apertura di una sessione e la porta
avanti fino all'apertura successiva.
 
### `primo_del_giorno(mask, df)`
 
Tiene solo la prima barra vera di ogni giornata FX.
 
---
 
## Cinque trappole trovate e chiuse — le più utili da ricordare
 
Valgono per qualunque condizione futura, non solo per queste.
 
### 1. La giornata FX si fondeva col weekend
 
Usando `barre_da_apertura(df, "ROLLOVER")` per i confini, la **riapertura della
domenica sera veniva saltata**: quella funzione scarta i giorni non feriali
locali, giustamente per le sessioni di borsa, ma la settimana FX riapre di
domenica.
 
Risultato: venerdì e lunedì si fondevano in un'unica giornata lunga tre giorni,
e "il massimo di ieri" per il martedì era il massimo di venerdì più lunedì.
**1.396 giornate invece di 1.743** su EURUSD.
 
Corretto con la data FX, che regge domeniche, festivi e riaperture tardive.
**Per i confini della giornata si usa `giorno_fx()`, mai `barre_da_apertura`.**
 
### 2. Una condizione può scattare dentro la quarantena senza accorgersene
 
Avendo deciso "E23 vale su tutta la giornata FX", ci eravamo portati dentro
anche la finestra del rollover: **47 trigger su 263 giorni** nascevano dalla
rottura di prezzi bid deformati.
 
**Regola che ne esce:** una condizione che non ha una finestra di sessione
esplicita deve escludere la quarantena a mano. Non succede da solo.
 
### 3. Una grandezza "fotografata" va fotografata davvero
 
Scritta nel modo ovvio, la variazione notturna alle 03:00 di New York avrebbe
usato la chiusura americana **sbagliata** — quella della sera prima invece di
quella precedente ancora — e il risultato sarebbe stato il rendimento
*intraday* del giorno prima **col segno rovesciato**. Nessun errore, nessun
avviso, un numero senza senso per due terzi della giornata.
 
Da qui `al_ultima_apertura()`.
 
### 4. La finestra ancora aperta finiva in quella di ieri (24/9)
 
Trovata dal collaudo del catalogo (`21_COLLAUDO_CATALOGO.md`), **non** dal test
di questo documento.
 
Con una fine dichiarata (`TOKYO→LONDRA`, `NEW_YORK→ROLLOVER`), quando lo storico
finiva dentro una finestra ancora aperta, la finestra veniva scartata ma **le
sue barre no**: finivano nella finestra precedente, già chiusa. Il range di ieri
conteneva i prezzi di oggi. Colpiva E22 e F21; E23 (`ROLLOVER` da solo) era
pulita.
 
Sullo storico intero toccava solo l'ultima giornata; **nel live, dove lo storico
finisce sempre sulla barra corrente, era la situazione normale.** Corretto con
una riga commentata in `range_finestra`: le barre di una finestra senza chiusura
non appartengono a nessuna finestra. Sull'EURUSD del repo nessuna barra di
nessuna condizione cambia.
 
**Regola che ne esce:** un test di lookahead deve anche *togliere* il futuro,
non solo sporcarlo. Con l'indice intatto la finestra si chiude comunque e il
difetto non si vede.
 
### 5. Una finestra che finisce a mercato chiuso non finiva mai (24/9)
 
`NEW_YORK→ROLLOVER` del **venerdì** non trova il rollover delle 17:00: a
quell'ora il mercato è già chiuso. La finestra restava aperta fino al rollover
di **lunedì**, dopo l'apertura americana di lunedì. Risultato: il lunedì F21
confrontava l'apertura con la chiusura di **giovedì**. Su EURUSD: **345 lunedì
su 346**; martedì–venerdì tutti giusti.
 
**Correzione in `range_finestra`** (solo il ramo con fine dichiarata): una
finestra si chiude alla sua fine **oppure alla prima pausa di mercato**, se
viene prima. Pausa = prima barra dopo un buco di più di `PAUSA_MINUTI` (60, la
stessa soglia della quarantena), riconosciuta su quella barra stessa: nessun
lookahead. La stessa regola assorbe la trappola 4: una finestra senza né fine
né pausa è aperta e le sue barre non appartengono a nessuna finestra.
 
Dopo la correzione: lunedì giusti **347 su 347**. Sulle 108 condizioni del
catalogo cambia **solo F21** (~9.400 barre: i lunedì e le ore che si porta
dietro); E22 identica barra per barra. Test di regressione: n. 12 in
`test_filtri_tempo.py`, che **fallisce sul codice vecchio** (52 lunedì
sbagliati su dati sintetici) e passa sul nuovo.
 
**Regola che ne esce:** ogni finestra temporale deve dire cosa succede quando
la sua fine cade a mercato chiuso (weekend, festivo). Vale per qualunque
finestra futura, per esempio `LONDRA→ROLLOVER`.
 
---
 
## Le entry — E22 e E23
 
Aggiunte ai dizionari esistenti `TRIGGER_LONG` e `TRIGGER_SHORT`, 28 per parte
invece di 26. Il notebook non cambia: `registra_trigger_long()` e
`registra_trigger_short()` le trovano da sole.
 
| long | short |
|---|---|
| `E22_ASIAN_RANGE_BREAKOUT` | `E22_SHORT_ASIAN_RANGE_BREAKDOWN` |
| `E23_PREV_DAY_HIGH_BREAKOUT` | `E23_SHORT_PREV_DAY_LOW_BREAKDOWN` |
 
**E22** — range fra apertura di Tokyo e apertura di Londra; il trigger può
scattare dall'apertura di Londra alla chiusura di New York.
 
**E23** — livello della giornata FX precedente; il trigger vale per tutta la
giornata.
 
### Tre convenzioni adottate, valide per le condizioni future
 
1. **Nessun buffer, nessun parametro.** La rottura è `Close > massimo`, non
   `massimo + 0,3 ATR`. Ogni valore di parametro sarebbe una prova in più nel
   conteggio dei test multipli.
2. **Un solo trigger al giorno per condizione**, il primo. Senza, una giornata
   che oscilla attorno al livello gonfia il conteggio e rompe l'indipendenza
   statistica delle osservazioni.
3. **Sono candidate vere, non metro.** Entrano nel conteggio di `k`: la
   griglia passa da 42 a 46 prove, quindi `soglia_rumore(46)`.
### Collaudo su EURUSD, orizzonte 48
 
Il run serve a verificare che il codice giri, che le occorrenze siano
plausibili e che i segni siano coerenti.
 
| candidato | trades | barra picco | picco pips | t grezzo | t netto |
|---|---|---|---|---|---|
| `E22_ASIAN_RANGE_BREAKOUT` | 1104 | 15 | −1,31 | −1,64 | −1,72 |
| `E23_SHORT_PREV_DAY_LOW_BREAKDOWN` | 780 | 27 | −1,85 | −1,62 | −1,54 |
| `E22_SHORT_ASIAN_RANGE_BREAKDOWN` | 1136 | 24 | −1,04 | −1,08 | −1,00 |
| `E23_PREV_DAY_HIGH_BREAKOUT` | 771 | 45 | −1,04 | −0,74 | −0,84 |
 
**Cosa dice il collaudo:** le occorrenze sono nell'ordine atteso (~1.100 per
E22 su 1.743 giornate, ~775 per E23), long e short sono confrontabili, nessuna
condizione degenera. Il pezzo funziona ed è pronto per essere usato.
 
Le correzioni del 24/9 (trappole 4 e 5) non cambiano nessuna barra di E22 ed
E23 sullo storico del repo, quindi questa tabella resta valida.
 
---
 
## I filtri — F20, F21, F22
 
Aggiunti a `FILTRI` in `filter_conditions.py`, da 22 a 29.
 
| filtro | direction | pair | copertura EURUSD |
|---|---|---|---|
| `F20_SESSION_ASIA` | 0 | — | 37,5% |
| `F20_SESSION_EUROPE` | 0 | — | 37,5% |
| `F20_SESSION_US` | 0 | — | 36,4% |
| `F20_SESSION_OVERLAP` | 0 | — | 17,0% |
| `F21_OVERNIGHT_UP` | +1 | `OVERNIGHT_RETURN` | 46,7% (era 45,7% prima della trappola 5) |
| `F21_OVERNIGHT_DOWN` | −1 | `OVERNIGHT_RETURN` | 48,0% (era 49,0%) |
| `F22_FAR_FROM_ROLLOVER` | 0 | — | 80,2% |
 
Le coperture sono il collaudo: tutte in fascia sensata, nessun filtro degenere.
 
**F20** — direction 0 perché stare dentro una sessione non dice niente su
rialzo o ribasso. `OVERLAP` è un AND fra due stati, non un OR fra rami opposti.
 
**F21** — la variazione fra la chiusura pulita della sessione americana
precedente e l'apertura di quella corrente. **Sul forex non è un "gap":** il
mercato ha trattato, c'erano Londra e l'Asia. È il rendimento overnight.
 
Fotografata all'apertura americana e portata avanti **24 ore**, così vale anche
durante l'Asia e l'Europa del giorno dopo. Scelta deliberata: la variante che
valeva solo durante la sessione americana avrebbe fatto anche da filtro di
sessione, e il risultato avrebbe mescolato due effetti senza poterli separare.
 
Su EURUSD ha mediana assoluta di 16,7 pips, novantesimo percentile a 48 (misurati il 24/9 dopo la
correzione; prima erano 21 e 63, gonfiati dai lunedì che misuravano da giovedì).
 
Essendo una coppia, la grid search la testa come **una riga sola**.
 
> **Il lunedì** F21 usa la chiusura del **venerdì**, come dichiarato. Fino al
> 24/9 usava quella di giovedì: vedi trappola 5.
 
**F22** — mancano almeno 4 ore al rollover. **Le 4 ore sono un parametro, ed è
dichiarato:** vengono dai picchi dell'event study (barre 15–30, cioè 4–8 ore),
scelte a priori una volta, mai provate in varianti.
 
### Scartati in questo giro, e perché
 
- **Fine mese:** "quanti giorni" è un parametro senza ancoraggio naturale.
- **Giorno del payroll:** ~80 occorrenze su 6,7 anni, sotto il centinaio che la
  roadmap indica come minimo. Il complemento toglierebbe il 5% e sarebbe un
  filtro degenere.
Entrambi restano aggiungibili se si decide una regola per il parametro.
 
---
 
## I test
 
`test_tempo_prezzo.py` 20/20 e `test_filtri_tempo.py` 25/25. Si lanciano da
**terminale**, mai dal notebook.
 
Il loro test centrale è la **verifica di lookahead a forza bruta con la
spazzatura**: si prende un campione di barre, si sostituiscono con spazzatura
*tutti* i dati successivi (prezzi attorno a 1000 invece di 1,10) e si controlla
che il valore in quella barra non cambi di una virgola.
 
**Questo schema non ha visto la trappola 4**, perché tiene l'indice intatto.
Dal 24/9 la verifica generale su tutto il catalogo è in
`Collaudo_Catalogo.ipynb`, per troncamento: vedi `21_COLLAUDO_CATALOGO.md`. Le
due suite restano valide per tutto il resto che controllano.