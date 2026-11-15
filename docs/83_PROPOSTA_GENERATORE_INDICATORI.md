# 83 · Proposta: generatore di indicatori e trigger (prezzo + volume)

Proposta senza codice, 15/11/2026. **Approvata da Mattia il 15/11/2026.**
Repo: **V4** (`matti410/Trading-System-Creator_V4`). Lo usano il **ML** (`Trading-System-Pipeline-ML`) e la
**fabbrica** (incarico 81).

## 1 · Perché

Il ML ha pochi record, perché i trigger con occorrenze utili sono pochi. Oggi i trigger nascono a mano: un'idea, un
articolo, una funzione nel catalogo. Le feature e i trigger sul volume sono pochi. Il generatore crea **indicatori
nuovi in automatico**, con le stesse logiche degli indicatori classici, anche combinando prezzo e volume, e ne ricava
dei trigger. Quali servono lo decidono poi gli strumenti che ci sono già (gruppo automatico del ML, avvio della
fabbrica), asset per asset.

## 2 · Decisioni di Mattia (15/11/2026)

1. Generatore **libero** (strada B), con un limite alla lunghezza delle ricette. Si vogliono anche le combinazioni
   prezzo + volume: è il ML a dire se servono.
2. Le ricette **non dipendono dall'asset**: si creano una volta, si salvano con un numero di versione e valgono per
   ogni asset e ogni timeframe da **M1 a D1** (M15 è solo il timeframe di sviluppo).
3. Quali trigger funzionano **lo scelgono in automatico**, per ogni asset, il gruppo automatico del ML e l'avvio della
   fabbrica. Non si rilancia nulla a mano quando si cambia asset.
4. I trigger generati devono poter entrare **anche nella fabbrica** (il genetico).
5. Il codice va in **file Python dentro V4**, e si lancia con un comando o con una cella.
6. **Ogni ricetta contiene sempre almeno un ingrediente di prezzo e uno di volume** (15/11).
7. **Trigger anche dal passaggio da un percentile all'altro** (15/11, §5).
8. **Tutte le finestre in numero di barre**, non in ore (15/11): come negli indicatori classici (RSI 14), la stessa
   ricetta usa le stesse barre su ogni timeframe. Coerente con i valori standard della fabbrica (§12 di `docs/82`) e
   con H in barre del gruppo automatico.

## 3 · Come nasce un indicatore (la ricetta)

Un indicatore è una ricetta: **ingredienti** e **operazioni**, come quelli classici. Esempi: OBV = somma nel tempo di
(segno del rendimento × volume); MFI = RSI su (prezzo tipico × volume); Chaikin Money Flow = media di (posizione della
chiusura × volume) / media del volume.

**Ingredienti (serie di base, da OHLCV):**

| Nome | Cosa è |
|---|---|
| `r` | rendimento della barra (log Close / Close prima) |
| `ar` | rendimento in valore assoluto |
| `rng` | range della barra in rapporto al Close: (High − Low) / Close |
| `pos` | posizione della chiusura nella barra: (Close − Low) / (High − Low), da 0 a 1 (0,5 se High = Low) |
| `corpo` | (Close − Open) / (High − Low), da −1 a 1 |
| `v` | volume relativo: Volume / sua mediana delle ultime 50 barre |
| `sv` | volume con segno: segno di `r` × `v` |
| `tp` | prezzo tipico (High + Low + Close) / 3, solo dentro operazioni che lo rendono un rapporto (delta, z-score, rango) |

Tutte senza unità (rapporti o rendimenti), così la stessa ricetta vale su BTC, ETH, oro e su ogni timeframe.
`tp` e il Close non entrano mai «nudi», perché il loro livello cambia da asset ad asset.

**Operazioni:**
- **nel tempo, con una finestra**: media, somma, massimo, minimo, deviazione, z-score, rango percentile, delta
  (valore − valore di N barre fa), correlazione fra due serie;
- **fra due serie**: per (×), diviso (÷, con protezione dallo zero), meno (−);
- **di forma**: segno, valore assoluto.

**Finestre:** in **barre**, uguali su ogni timeframe. Proposta: **5, 14, 50, 200** (corta, media classica, lunga,
molto lunga). Su M1 200 barre sono poco più di 3 ore, su D1 sono quasi 10 mesi: è voluto, come per gli indicatori
classici.

**Limite:** al massimo **3 operazioni** per ricetta, così ogni indicatore si legge come uno classico e si può portare
su TradingView in Pine.

## 4 · Regole del generatore

1. **Ordine fisso, dal più semplice.** Il generatore elenca le ricette da 1, poi 2, poi 3 operazioni, sempre nello
   stesso ordine. Non guarda nessun prezzo: lanciato due volte dà lo stesso elenco.
2. **Ricette uguali contate una volta.** Si tolgono:
   - quelle uguali per scrittura (A × B = B × A; −(B − A) = A − B);
   - quelle uguali nei fatti: si calcolano su un **dataset sintetico fisso** (non su dati veri) e, se due ricette danno
     gli stessi trigger, ne resta una (la più corta).
3. **Tetto al numero di ricette** (N), fissato **dopo** la misura dei tempi (§7). Si tengono le prime N nell'ordine
   del punto 1. Il tetto cambia solo con una versione nuova del catalogo.
4. **Vincolo (deciso 15/11):** in ogni ricetta almeno un ingrediente di volume (`v`, `sv`) e almeno uno di prezzo.

## 5 · Da indicatore a trigger

Da ogni indicatore nascono trigger con regole fisse, uguali per tutti. Un evento scatta quando l'indicatore
**attraversa un livello**, verso l'alto o verso il basso:

| Regola | Livello | Esempio |
|---|---|---|
| zero | lo 0 (solo indicatori che vanno da negativo a positivo) | il volume con segno sommato su 14 barre passa da negativo a positivo |
| media | la media mobile dell'indicatore stesso (20 barre) | l'indicatore sale sopra la sua media: accelera rispetto al solito recente |
| percentili | il 10°, 25°, 50°, 75°, 90° percentile mobile | l'indicatore passa dal quarto più basso (sotto il 25°) a sopra il 25° |

- **Ogni attraversamento dà un trigger long e uno short.** Un indicatore generato non ha un significato noto in
  partenza (non si sa se «sale» sia rialzista): decide l'event study / il gruppo automatico quale lato funziona.
- Con 7 livelli × 2 versi × 2 lati nascono fino a **28 trigger per indicatore**. Lo «zero» vale solo per gli indicatori
  con segno.
- **I percentili sono mobili**, calcolati sulle ultime **500 barre**, barra esclusa. Così il trigger
  non dipende da come si taglia il train: è identico nel ML, nella fabbrica, dal vivo e in Pine.
- **Scatta solo la prima barra** in cui la condizione diventa vera (la funzione `_evento` già usata nel catalogo).
- Ogni trigger passa i controlli che V4 ha già: `verifica_lookahead` (non guarda il futuro) e
  `verifica_degenerazione` (non scatta sempre o mai).

## 6 · Cosa produce e chi lo usa

**Il catalogo generato** è un file di dati in V4 (per esempio `dati_catalogo/generati_v1.json`) con, per ogni trigger:
nome (`G0001_…`), ricetta leggibile, regola del §5, lato, **famiglia dichiarata** (in base agli ingredienti: per
esempio «volume-pressione», «volume-conferma», «prezzo-momento»), versione.

I trigger generati hanno **lo stesso formato** di quelli del catalogo (una funzione che riceve il df e restituisce
vero/falso per barra), quindi chi li usa non deve sapere da dove vengono.

- **ML:** il gruppo automatico (`gruppo.py`) pesca dal catalogo ufficiale e, se l'interruttore è acceso, anche da
  quello generato. Le regole del gruppo non cambiano.
- **Fabbrica:** stessa scelta in config (versione nuova della config). All'avvio tiene già un blocco per famiglia,
  quindi trigger generati quasi uguali si riducono a pochi blocchi. Il conto delle prove si somma come già succede, da
  leggere sulla scheda.
- **Interruttore** in config, con due valori: «solo ufficiale» (valore di base) / «ufficiale + generati».
- **Promozione facoltativa:** un trigger generato che vuoi tenere con un nome lo copi nel catalogo ufficiale (E53, E54…),
  con la ricetta come docstring. Serve per leggerlo meglio o portarlo in Pine, non per farlo funzionare.

**Come si lancia:** un comando nel terminale di VS Code (`python -m engine.generatore`), che crea il catalogo e scrive
quante ricette ha generato, quante ne ha tolte come uguali e quanti trigger restano. In alternativa, una cella in un
notebook di V4 che mostra la tabella con alcuni esempi leggibili.

## 7 · Misura dei tempi, prima di fissare N

Prima di fissare il tetto, Claude Code misura, su BTC perp, con 100, 500 e 2.000 trigger generati:
- il tempo di calcolo dei trigger su M1, M5, M15, H1, H4, D1;
- il tempo del gruppo automatico del ML;
- il tempo dell'avvio della fabbrica e di una ricerca completa (M15 e M5).

Mattia sceglie N guardando i tempi. Il tempo dipende soprattutto dal numero di barre del
dataset (M1 ne ha 15 volte M15), non dalle finestre. Se il tempo è troppo, si abbassa N.

## 8 · Cosa non fa

- Non tocca i file del catalogo ufficiale (`entry_long.py`, `entry_short.py`) né i loro test.
- Non sceglie i trigger: la scelta resta al gruppo automatico del ML e all'avvio della fabbrica.
- Non usa dati veri per creare le ricette (solo il sintetico per togliere quelle uguali).
- Non cambia le regole della fabbrica né quelle del gruppo automatico.

## 9 · Decisioni chiuse (15/11)

Finestre 5, 14, 50, 200 barre; percentili mobili su 500 barre; media mobile 20 barre; volume relativo su 50 barre;
ricette sempre con prezzo e volume; livelli 10°, 25°, 50°, 75°, 90°. Ordine: **ora** generatore (V4) e collegamento al
ML; **dopo il primo giro completo della fabbrica** (celle 1–7) il collegamento alla fabbrica, con un incarico a parte.

## 10 · Il rischio da tenere presente

Più trigger si generano, più ne escono «buoni» per caso. Lo limitano: ricette e soglie fisse, mai tarate sui dati; la
scelta fatta solo sul train (ML) o sul pezzo di ricerca (fabbrica); il test del ML e la cassaforte della fabbrica, che
restano puliti e danno il giudizio vero; il numero di trigger provati, scritto e da leggere.

## 11 · Come è fatto (incarico 83, 15/11/2026)

Codice in `engine/generatore/` (ricette.py, trigger.py, catalogo.py), test in `test_generatore.py`. Non tocca
`entry_long.py`, `entry_short.py`, la fabbrica e i loro test.

**Decisioni di Mattia nella chat dell'incarico (15/11):**
- `sv` conta come ingrediente di prezzo **e** di volume: «media(sv, 14)» è una ricetta valida da sola;
- il delta di `tp` è in rapporto: log(tp / tp di N barre fa);
- il comando vuole il tetto: `python -m engine.generatore --n N`; senza `--n` si ferma e lo chiede. Il file
  `dati_catalogo/generati_v1.json` si crea quando N è scelto;
- per la misura dei tempi M1, H1, H4 e D1 di BTC perp scaricati con `scarica_dati_crypto.py` (in `dati/`).

**Scelte di scrittura (dentro le regole dei §3–§5):**
- **ordine fisso**: prima le ricette da 1 operazione, poi da 2, poi da 3; a parità: nel tempo (media, somma, max,
  min, dev, zscore, rango, delta), correlazione, fra due serie (×, ÷, −), di forma (segno, abs); poi gli ingredienti
  nell'ordine della tabella del §3, le finestre dalla più corta. Il catalogo con N più piccolo è l'inizio di quello
  con N più grande (G0001 resta G0001);
- **uguali per scrittura**: A×B = B×A, corr(A, B) = corr(B, A), A−B = −(B−A) (resta un ordine solo); la stessa
  serie due volte (A−A, A÷A, A×A, corr(A, A)); abs di una serie mai negativa; segno o abs di un segno;
  abs(r) = ar, abs(sv) = v, segno(sv) = segno(r);
- **uguali nei fatti**: sul dataset sintetico fisso (6.000 barre da 15 minuti, seme 83) si confronta l'insieme dei
  trigger di ogni ricetta, barra per barra; se è identico a quello di una ricetta già tenuta, resta la prima. Esempi:
  somma(sv, N) = media(sv, N) (cambia solo la scala), ar × v = r × sv. Una ricetta che sul sintetico non scatta
  mai si toglie, contata a parte;
- **zero**: vale per le ricette che sul sintetico hanno valori negativi e positivi (28 trigger), le altre ne hanno 24;
- **calcoli**: tutto con la barra e quelle prima; dev e z-score con la deviazione della popolazione (come Pine);
  rango = quota della finestra (barra compresa) sotto il valore, pari a metà; ÷ dà NaN dove il denominatore è zero;
  v = Volume / mediana delle ultime 50 barre (barra compresa); pos = 0,5 e corpo = 0 se High = Low;
- **attraversare**: sopra il livello sulla barra e sotto o uguale sulla barra prima (verso il basso al contrario),
  poi `_evento`. I percentili vogliono tutte le 500 barre prima valide;
- **nomi**: `G0001_P25_SU` (long), `G0001_SHORT_P25_SU` (short); livelli ZERO, MEDIA20, P10–P90; versi SU, GIU;
- **famiglia dichiarata**, dagli ingredienti di prezzo: «volume-pressione» (r, sv, corpo, pos: la direzione della
  barra, tipo OBV, MFI, Chaikin), «volume-conferma» (ar, rng: sforzo e risultato), «volume-momento» (tp); più
  gruppi si uniscono con «+», es. «volume-pressione+conferma»;
- **degeneri**: segnalati, non tolti. Ogni trigger del file porta l'esito di `verifica_degenerazione` sul sintetico
  (`esito_sintetico`); su dati veri si rifà con `segnala_degeneri(df, catalogo)`;
- i trigger sono oggetti `TriggerGenerato` (df → Series booleana, come le funzioni di `entry_long.py`), che si
  possono passare ai processi della fabbrica; `registra_trigger_generati(catalogo)` li registra nel motore.

**Quante ricette ci sono** (prezzo + volume, dopo le uguali): con 1 operazione **112** ricette, 2.984 trigger.
Fino a 2 operazioni **14.049** ricette (112 da 1, 13.937 da 2), 378.800 trigger: in quell'elenco 26.031 generate,
9.416 tolte per scrittura, 2.468 uguali sul sintetico, 98 che non scattano mai. Con N ≤ 112 il catalogo ha solo
ricette da 1 operazione. Le ricette da 3 operazioni non sono state contate (qualche milione da provare).

## 12 · Tempi misurati (15/11/2026)

BINANCE_PERP_BTCUSDT, dal 2/1/2020, sul PC di Mattia, un processo solo, a macchina libera. Tempo per **calcolare**
i primi K trigger del catalogo (nell'ordine fisso, ricetta per ricetta, long e short), con la cache di una ricetta
(indicatore e livelli calcolati una volta per i suoi 24–28 trigger). Non comprende il gruppo del ML né la fabbrica
(§7, da misurare quando si collegano).

| timeframe | barre | 100 trigger (4 ricette) | 500 trigger (20 ricette) | 2.000 trigger (76 ricette) |
|---|---:|---:|---:|---:|
| M1  | 3.614.206 | 48 s | 3 min 47 s | 15 min 43 s |
| M5  |   719.580 | 10 s | 45 s | 3 min 4 s |
| M15 |   238.326 | 3 s | 15 s | 61 s |
| H1  |    60.237 | 0,8 s | 3,7 s | 15 s |
| H4  |    15.059 | 0,2 s | 1,2 s | 4,8 s |
| D1  |     2.509 | 0,1 s | 0,4 s | 1,8 s |

- Il tempo cresce in proporzione alle barre e ai trigger: circa 0,13 microsecondi per barra e per trigger
  (M1: 943 s / 3,6 milioni di barre / 2.000 trigger). Da qui si stima ogni altro N.
- Quasi tutto il tempo va nei 5 percentili mobili su 500 barre (circa 2 s ciascuno su M1, per ricetta).
- Dati: M1, H1, H4, D1 scaricati il 15/11 con `scarica_dati_crypto.py` (nessun buco; su M1 182 barre a volume zero,
  segnalate); M5 dal Drive (fino al 4/11); M15 da `dati/` (fino al 19/10).
