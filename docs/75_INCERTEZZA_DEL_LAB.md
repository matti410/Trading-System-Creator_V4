# 75 · Incarico: l'incertezza del Lab (rendimenti sovrapposti)

**Data:** 28 ottobre 2026
**Stato:** collaudo fatto (PR #86, §3); correzione in corso (PR 2, piano al §7, via di Mattia del
28/10/2026).
**Da dove nasce:** il primo dei «Problemi aperti» di `00`. Il collaudo della mappa del 28/10 (sezione
G di `test_mappa.py`, PR #84) ha mostrato che l'incertezza con lo **sconto** (pesi decrescenti)
sottostima l'incertezza dei rendimenti sovrapposti. La mappa ha già la sua correzione; il Lab no.

**Indice:** §0 In breve · §1 Il problema · §2 Dove si usa oggi, e cosa decide · §3 Il collaudo
proposto · §4 Cosa cambierebbe nel Lab, e le prove d'identità · §5 Le decisioni per Mattia · §6
Ordine dei lavori · §7 Il piano della correzione.

---

## 0 · In breve

- Quattro punti del Lab calcolano l'incertezza di una media di rendimenti a H barre che si
  sovrappongono, e tutti e quattro usano lo **sconto**:
  1. l'event study della 2c;
  2. la rosa della 3a;
  3. l'atlante della 3c;
  4. il profilo orario della 2a.
- Da quell'incertezza dipendono la **solidità** (t), la **quota di falsi positivi** e quindi le
  promozioni: quali trigger sono nella rosa, quali situazioni dell'atlante passano, quali ore del
  profilo sono colorate.
- La proposta è collaudare prima i quattro punti su mercati inventati senza effetto, con il calcolo
  di oggi e con quello della mappa, come per la mappa. La correzione si fa dopo, in un lavoro a
  parte, con le decisioni del §5.

## 1 · Il problema

Un rendimento a H barre che parte alla barra i e uno che parte alla barra j, con d = |i − j| < H,
hanno H − d candele in comune. La loro covarianza è già proporzionale alle candele in comune:
(1 − d/H) volte la varianza.

Il calcolo di oggi somma i prodotti fra coppie vicine, ma li moltiplica **ancora** per (1 − d/H):

    varianza = somma u_i^2 + 2 · somma_{d < H} (1 − d/H) · u_i · u_(i+d)

Lo sconto si applica due volte. Quando le barre che contano sono vicine per molte barre di fila,
l'incertezza esce più piccola del vero, la solidità più grande, e il caso promuove più spesso del
dovuto. Le barre sono vicine così in due casi:
- un trigger che scatta spesso;
- una fascia che dura giorni.

Con eventi distanti almeno H barre fra loro non ci sono coppie vicine: i due calcoli coincidono.

**Cosa si è già visto, solo su mercati inventati** (sezione G di `test_mappa.py`, 1.000 mercati
senza effetto per variante):

| variante | «risponde» con lo sconto | senza sconto (la mappa oggi) |
|---|---|---|
| fascia a blocchi di 8 ore, 24 ore (come M04) | 187 | 118 |
| fascia lenta a quintili, 8 ore (come M05) | 108 | 67 |
| la stessa, con la volatilità variabile | 115 | 66 |

**La correzione della mappa** (`mappa.errore_sovrapposti`) fa due cose:
- ogni coppia più vicina di H barre pesa per intero;
- se la varianza esce zero o negativa (senza i pesi può succedere), usa la stima a blocchi di una
  settimana e lo segna in una colonna.

## 2 · Dove si usa oggi, e cosa decide

| dove | funzione | schermata (Lab) · cella (ricerca) | cosa decide l'incertezza |
|---|---|---|---|
| **event study** | `event_study._errore_standard_sovrapposti` (coppie di trigger a meno di H barre, peso 1 − d/H) | 2c (`esplora` lancia `run_event_study`); classifica a scomparsa della 3a · ricerca, celle 16 e 28 | la «solidità» (`volte_incertezza`) e «Supera il rumore» (`oltre_rumore`, contro `giudizio.soglia_rumore_orizzonte`); l'ordine della classifica. Lo usa anche la rosa per il t «globale», solo da leggere |
| **rosa dei trigger** | `stagionalita.scarto_orario` → `errore_standard_pesato` | 3a (`rosa_entry`) · ricerca, cella 32 | `t_netto`, `p`, la quota di falsi positivi (BH, q = 20%), quindi «candidata» e «nella rosa». Da lì vengono: le casistiche suggerite e il punto di partenza della 3b («la rosa»), e quali curve mostra la 2c (le più solide della rosa) |
| **atlante** | `atlante._somme_per_cella` (numba): la stessa formula di `errore_standard_pesato`, una cella alla volta | 3c (`atlante_dei_trigger`), 3d · ricerca, cella 45 | `t`, `p`, la quota di falsi positivi, quindi «passa», le colonne «Batte il mercato» e «Si può scegliere alla 3d», l'avviso della 3d (`controlla_cella`) e quali celle si propongono come filtri al passo 5 |
| **profilo orario** | `stagionalita.profilo_orario` → `errore_standard_pesato` | 2a · ricerca, cella 26; `condizioni_orarie` (uscita `X_INVERSIONE_TREND`) | l'«oscillazione casuale», la solidità e le **ore colorate** (bh). Le ore colorate decidono anche quando esce un trade con `X_INVERSIONE_TREND` (schermata 4) |
| curve dello scarto | `stagionalita.curva_scarto_orario` | 2c · ricerca, cella 34 | **niente**: disegna solo lo scarto medio, senza incertezza. Non cambia |
| rosa dei sistemi | `rosa.rosa_sistemi` (t dei trade) | 4, 4b · ricerca, cella 55 | non usa le sovrapposizioni: i trade di un sistema non si sovrappongono sullo stesso lato. Fuori da questo lavoro |
| mercato nullo | `mercato_nullo` (usa `rosa_entry`) | sospeso dal 21/10 | cambierebbe con la rosa; resta sospeso |
| mappa | `mappa.scarto_mappa` | notebook della mappa | **già corretta** (PR #84) |

Non dipendono da questa incertezza:
- gli scarti medi (bp e pips), le curve e il netto dei costi;
- i trade e la scheda di un sistema fissato, l'out-of-sample, il Monte Carlo e il money
  management;
- il conto delle prove e la soglia cumulata, che contano le prove e non le misurano.

## 3 · Il collaudo proposto (dopo il via, solo mercati inventati)

**I mercati.** Random walk senza nessun effetto, M15, 800 giorni (come la sezione G), con la
quarantena spenta come sugli exchange. Due varianti di prezzo:
- volatilità costante;
- **volatilità variabile**: la stessa volatilità stocastica della variante c della mappa, con
  periodi agitati e calmi.

Per variante: 1.000 mercati a seme fisso.

**I trigger finti**, indipendenti dai prezzi per costruzione, con H = 41 (il valore delle prove
d'identità):

| trigger | come scatta | perché |
|---|---|---|
| **F · frequente** | circa 15.000 volte nell'in-sample (come E21), **a grappoli**: uno stato acceso/spento che dura qualche ora | tante coppie a meno di H barre: il caso peggiore per lo sconto |
| **R · raro** | circa 300 volte, sempre a più di H barre di distanza | **il riferimento**: senza coppie vicine i due calcoli coincidono, quindi è il livello «giusto» del caso |
| **M · medio** | circa 3.000 volte, sparse a caso | il caso intermedio |

Per la rosa e l'atlante serve una famiglia di trigger, perché la quota di falsi positivi si
calcola fra tutti. Si misurano insieme 10 trigger finti: 4 frequenti, 4 medi, 2 rari, metà long e
metà short.

**Cosa si conta**, per ogni mercato, con il **calcolo di oggi** e con **quello della mappa**:

| punto | «promosso per caso» |
|---|---|
| rosa (3a) | il trigger è «candidata» (t > 0, quota di falsi positivi, due metà). Si contano per tipo (F, M, R) e «almeno uno nella rosa» |
| atlante (3c) | la situazione «passa». Si contano per tipo di trigger, sulle 8 situazioni per lato (i mercati inventati non hanno lo spot, quindi niente basis) |
| event study (2c) | «Supera il rumore» a favore del trade |
| profilo (2a) | quante delle 96 ore sono colorate |

**Il criterio** (da decidere, §5 D4). La proposta è che, con il calcolo nuovo, il tasso per caso
dei trigger frequenti e medi stia al livello del trigger raro, entro un margine dichiarato prima
(es. 3 punti), e in ogni caso sotto il 20% della quota di falsi positivi. Il profilo deve restare
nel livello di q.

**Dove va il codice del collaudo** (§5 D6):
- una suite nuova, `test_incertezza_lab.py`, con meno mercati (es. 200) per stare nei tempi della
  suite completa;
- il giro da 1.000 mercati una volta sola, con i numeri scritti in questo documento.

**Tempi stimati:**
- la rosa su 75.000 barre e 10 trigger richiede circa mezzo secondo;
- l'atlante è di più (8 situazioni per lato, numba);
- in tutto, il giro da 1.000 mercati è di decine di minuti.

**Aggiunte dopo il primo giro da 200 (Mattia, 28/10/2026).**
- Il raro (300 ingressi) nell'atlante non si misura mai: circa 37 ingressi per situazione, sotto
  il minimo di 200. Il riferimento dell'atlante è un quinto tipo, **D · raro denso**: circa 1.800
  ingressi, a distanze casuali di 41 o 42 barre (mai due a meno di H), indipendente dai prezzi. Per
  rosa ed event study il riferimento resta il raro. Il test conta le situazioni misurate dei
  riferimenti e si ferma con un errore se sono zero.
- Nella rosa il riferimento resta il raro con il calcolo nuovo, senza tolleranza sulle quote.
- **Profilo:** con il calcolo nuovo il profilo colora ore per caso circa il doppio di prima (dal 5%
  al 10–11% dei mercati inventati), sempre sotto q = 20%, e queste ore decidono `X_INVERSIONE_TREND`.

**La scomposizione dell'incertezza (28/10/2026, sezione C del test).** L'incertezza della rosa e
dell'atlante è una somma su tutte le barre di pesi per rendimenti: +1/n sulle barre del trigger,
meno la quota della media del mercato della stessa ora su ogni barra. Si divide esattamente in tre
parti: **(1)** la parte del trigger, **(2)** quella del mercato della stessa ora, **(3)** quella
incrociata. I due calcoli cambiano solo il peso delle coppie di barre a meno di H: se gli ingressi
del trigger sono tutti a H barre o più, la (1) non ha coppie e deve coincidere. Su 3 mercati
inventati (rosa con il raro, atlante con il raro denso), valori divisi per la (1):

| mercato · punto | oggi (2) | oggi (3) | **oggi totale** | mappa (2) | mappa (3) | **mappa totale** |
|---|---|---|---|---|---|---|
| volatilità costante · rosa | 0,113 | −0,224 | 0,889 | 0,167 | −0,338 | 0,828 |
| volatilità costante · atlante (8 situazioni) | 0,354 | −0,712 | 0,643 | 0,444 | −0,894 | 0,550 |
| volatilità variabile 1 · rosa | 0,088 | −0,204 | 0,884 | 0,127 | −0,292 | 0,835 |
| volatilità variabile 1 · atlante | 0,434 | −0,835 | 0,599 | 0,559 | −1,091 | 0,468 |
| volatilità variabile 2 · rosa | 0,099 | −0,237 | 0,862 | 0,149 | −0,360 | 0,789 |
| volatilità variabile 2 · atlante | 0,394 | −0,824 | 0,569 | 0,517 | −1,068 | 0,449 |

- Con la stessa formula la (1) coincide al bit nei due calcoli in tutte le 27 misure (3 rose, 24
  situazioni): la differenza fra i calcoli sta tutta in (2) e (3). Le tre parti sommate danno
  l'incertezza di ciascun calcolo; la riserva a blocchi qui non scatta.
- Con le funzioni dell'engine la (1) coincide al bit nella rosa. Nell'atlante coincide al bit in 3
  situazioni su 24; nelle altre la differenza massima osservata è 7,6·10⁻¹⁶ in relativo (5 unità
  sull'ultima cifra). Viene dall'ordine delle somme: il motore dell'atlante (numba) somma i quadrati
  in fila, mappa.errore_sovrapposti (numpy) a coppie. Il test (C1b) accetta fino a 10⁻¹² in
  relativo (Mattia, 28/10/2026).
- La parte incrociata è negativa: il trigger e il mercato della stessa ora hanno pesi di segno
  opposto sulle stesse candele. Contare per intero le coppie vicine fa crescere sia la (2) sia la
  (3), la (3) di più: per questi riferimenti l'incertezza nuova è un po' più piccola di quella di
  oggi.

**La densità degli scatti (28/10/2026).** Per confronto con un trigger vero, le stesse tre cifre
per E21 su BINANCE_PERP_BTCUSDT M15: **solo i tempi di scatto, nell'in-sample** (fino al confine
dello studio, 15/06/2025 17:30 UTC), senza prezzi dopo l'ingresso, senza rendimenti né esiti. Non è
una prova e non va nel conto. Grappolo = barre accese una dopo l'altra; finti = media sui trigger
del giro da 200.

| trigger | ingressi | grappolo medio | coppie consecutive a meno di 41 barre | ingressi ogni 1.000 barre |
|---|---|---|---|---|
| F · frequente finto (76.800 barre) | 15.626 | 16,2 barre | 96,7% | 203 |
| M · medio finto | 3.000 | 1,04 barre | 79,8% | 39 |
| E21_BELT_HOLD, long (191.206 barre) | 15.041 | 1,0 barre | 96,8% | 79 |
| E21_SHORT_BELT_HOLD, short | 14.895 | 1,0 barre | 96,5% | 78 |

Il frequente finto è più denso di E21 (circa 2,6 volte gli ingressi per barra, a grappoli): non si
aggiunge un «frequente denso» (Mattia, 28/10/2026).

### I risultati del collaudo (28/10/2026, PR 1 del §6)

Promozioni per caso, in %, senza nessun effetto, H = 41. Riferimento: R nella rosa e nell'event
study, D nell'atlante (R nell'atlante non si misura). Il criterio D4 si legge sulle righe «mappa».

**Giro da 200 (la suite: 100 + 100 mercati), 11/11 test superati, 13 minuti.**

| volatilità · calcolo | rosa F | M | R | D | atlante F | M | **D** | es F | M | R | D | profilo |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| costante · oggi | 2,8 | 3,8 | 1,5 | 0,0 | 1,3 | 0,8 | 0,6 | 0,5 | 0,0 | 0,0 | 0,0 | 5,0 |
| costante · mappa | 1,5 | 3,5 | **2,0** | 4,0 | 0,5 | 0,6 | **0,8** | 0,2 | 0,0 | **0,0** | 0,0 | 11,0 |
| variabile · oggi | 2,8 | 2,5 | 2,5 | 0,0 | 0,9 | 0,3 | 0,3 | 0,0 | 0,2 | 0,5 | 0,0 | 5,0 |
| variabile · mappa | 2,8 | 2,8 | **3,5** | 3,5 | 0,5 | 0,2 | **0,5** | 0,0 | 0,2 | **0,5** | 0,0 | 10,0 |

- **D4 rispettato** in tutte e due le varianti: F e M entro 3 punti dal riferimento e sotto il 20%;
  il profilo (mercati con almeno un'ora colorata) sotto q.
- Situazioni misurate dei riferimenti, in ogni variante e in tutti e due i calcoli: rosa (R) 200,
  atlante (D) 1.600, event study (R) 200.
- Il trigger raro ha la stessa solidità dell'event study nei due calcoli, al bit.
- Profilo: incertezza della mappa / incertezza di oggi, in media sulle ore, 0,896 (costante) e
  0,895 (variabile).
- Riserva dei blocchi di una settimana (calcolo della mappa), costante / variabile: rosa 298 su
  12.656 / 542 su 12.578, **tutte del raro denso** (298 su 2.135 / 542 su 2.092); atlante 0 su
  8.000 / 4 su 8.000; profilo 0 su 9.600 in tutte e due; event study 0 su 49.200 in tutte e due.
- Solo da scrivere, non sono criteri:
  - raro denso nella rosa: 0,0% oggi, 4,0% / 3,5% con la mappa; nell'event study 0,0% nei due
    calcoli; riserva a blocchi nella rosa come sopra, nell'event study 0 su 8.200;
  - raro nella rosa: incertezza della mappa / incertezza di oggi media 0,970 (minimo 0,956, massimo
    0,989) a volatilità costante, 0,971 (minimo 0,903, massimo 1,044) a volatilità variabile;
    promozioni solo con il calcolo di oggi 0 e 0, solo con quello della mappa 1 e 2.
- Rispetto al primo giro da 200 le quote del raro cambiano un po' (es. rosa R 2,0 → 1,5 a
  volatilità costante, calcolo di oggi): il raro denso è entrato nella famiglia, e la quota di falsi
  positivi si calcola fra tutti.

**Giro da 1.000 (1.000 + 1.000 mercati, una volta sola), 11/11 test superati, 2 ore e 9 minuti.**

| volatilità · calcolo | rosa F | M | R | D | atlante F | M | **D** | es F | M | R | D | profilo |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| costante · oggi | 3,4 | 2,4 | 1,6 | 0,0 | 1,0 | 0,6 | 0,2 | 0,1 | 0,2 | 0,0 | 0,0 | 4,5 |
| costante · mappa | 2,1 | 2,4 | **1,8** | 2,6 | 0,6 | 0,5 | **0,5** | 0,0 | 0,0 | **0,0** | 0,0 | 9,7 |
| variabile · oggi | 3,6 | 2,1 | 1,8 | 0,0 | 0,7 | 0,4 | 0,1 | 0,1 | 0,0 | 0,2 | 0,1 | 4,8 |
| variabile · mappa | 2,3 | 2,1 | **2,1** | 2,0 | 0,5 | 0,4 | **0,5** | 0,0 | 0,0 | **0,2** | 0,1 | 8,5 |

- **D4 rispettato** in tutte e due le varianti; il profilo sotto q.
- Situazioni misurate dei riferimenti, in ogni variante e in tutti e due i calcoli: rosa (R) 2.000,
  atlante (D) 16.000, event study (R) 2.000.
- Il trigger raro ha la stessa solidità dell'event study nei due calcoli, al bit. Scomposizione
  (sezione C): uguale a quella sopra; nell'atlante differenza massima 7,6·10⁻¹⁶.
- Profilo: incertezza della mappa / incertezza di oggi, in media sulle ore, 0,895 in tutte e due
  le varianti.
- Riserva dei blocchi di una settimana (calcolo della mappa), costante / variabile: rosa 3.873 su
  125.961 / 5.577 su 125.845, **tutte del raro denso** (3.873 su 21.040 / 5.577 su 21.043); atlante
  0 su 80.000 / 54 su 80.000; profilo 0 su 96.000 in tutte e due; event study 0 su 492.000 in tutte
  e due.
- Solo da scrivere, non sono criteri:
  - raro denso nella rosa: 0,0% oggi, 2,6% / 1,9% con la mappa; nell'event study 0,1% nei due
    calcoli, in tutte e due le varianti; riserva a blocchi nella rosa come sopra, nell'event study 0
    su 82.000;
  - raro nella rosa: incertezza della mappa / incertezza di oggi media 0,970 (minimo 0,947, massimo
    0,995) a volatilità costante, 0,971 (minimo 0,879, massimo 1,067) a volatilità variabile;
    promozioni solo con il calcolo di oggi 2 e 0, solo con quello della mappa 7 e 4 (su 2.000
    misure per variante).

## 4 · Cosa cambierebbe nel Lab, e le prove d'identità

**Quali numeri si spostano.** Le medie restano uguali; cambiano l'incertezza e tutto quello che
ne dipende, cioè la solidità, il p, la quota di falsi positivi e le promozioni:

| schermata | cosa cambia | cosa resta uguale |
|---|---|---|
| 2a | oscillazione casuale, solidità, ore colorate (e quindi `X_INVERSIONE_TREND` alla 4) | lo scarto di ogni ora |
| 2c | solidità, «Supera il rumore», quali 5 curve si mostrano | le curve |
| 3a | `t_netto`, `p`, bh, «candidata», «nella rosa», l'ordine della classifica | scarti, eventi, famiglie, correlazioni |
| 3b | il punto di partenza «la rosa», se la rosa cambia | — |
| 3c, 3d | `t`, `p`, bh, «passa», «Batte il mercato», l'avviso della 3d | scarti e netto delle celle |
| 4–9 | solo se cambiano i trigger scelti, la cella o l'uscita a orario | tutto, a parità di scelte |

Il verso dell'effetto è prevedibile. L'incertezza cresce, e la solidità scende, per i trigger
frequenti e a grappolo con H lungo. Resta uguale per i trigger con ingressi distanti almeno H
barre. In casi rari una varianza negativa passa ai blocchi settimanali, come nella mappa.

**Le prove d'identità non possono più essere «identiche al bit»** sulle schermate 2–3. La
proposta è sostituirle con un confronto prima/dopo spiegato, in tre passi:

1. **Il calcolo vecchio a richiesta.** Un parametro, come `comportamento_vecchio()` del motore:
   con il calcolo di oggi, il codice nuovo dà gli stessi oggetti di main, al bit, su
   BINANCE_PERP_BTCUSDT e BYBIT_SPOT_ETHUSDT. Prova che non è cambiato altro.
2. **Con il calcolo nuovo**, sugli stessi giri, il confronto elenca gli oggetti diversi. Ci si
   aspetta che siano **solo** le colonne del §4 (incertezza, t, p, bh, promozioni) e quello che ne
   discende. Gli scarti, gli eventi e i conti devono restare identici. Ogni differenza fuori da
   quell'elenco ferma il lavoro.
3. **A scelte fissate** (trigger, cella e uscite scritti a mano, non presi dalla rosa), le
   schermate dalla 4 alla 9 devono restare identiche al bit. Così si separa «è cambiata la rosa» da
   «è cambiato il backtest».

Accanto ci sarà una tabella del confronto: per ogni trigger e ogni cella, l'incertezza prima e
dopo, e chi entra o esce dalla rosa e dall'atlante. I nomi sì, i numeri sui dati veri solo come
collaudo.

**Lo studio.** Il conto delle prove e i giornali non cambiano: non salvano né t né bh. Le scelte
già fatte nel Lab (rose e atlanti guardati) restano nel conto. Non si rifanno.

## 5 · Le decisioni per Mattia

| # | domanda | proposta |
|---|---|---|
| D1 | Quale calcolo? | Lo stesso della mappa: le coppie a meno di H barre per intero, e i blocchi di una settimana se la varianza esce zero o negativa, con una colonna che lo dice. Una funzione sola, usata da mappa, rosa, atlante, profilo ed event study |
| D2 | Quali punti correggere? | Tutti e quattro (event study, rosa, atlante, profilo) in un lavoro solo, perché usano la stessa formula. In alternativa, prima rosa e atlante, che decidono le promozioni |
| D3 | Il profilo 2a rientra? | Sì. Cambia le ore colorate e quindi `X_INVERSIONE_TREND`: va detto alla 4 |
| D4 | Il criterio del collaudo | Calcolo nuovo: trigger frequenti e medi al livello del raro, entro un margine fissato prima (es. 3 punti), e sotto il 20%. Profilo entro q |
| D5 | Il calcolo vecchio a richiesta (§4, passo 1) | Sì, come parametro: serve alle prove d'identità. Da decidere se resta per sempre o si toglie dopo il merge |
| D6 | Dove vanno i test | Una suite nuova `test_incertezza_lab.py` (200 mercati), più il giro da 1.000 mercati una volta sola, con i numeri qui |
| D7 | La funzione della mappa | Si sposta in `stagionalita.py` e la mappa la usa da lì, con i numeri della mappa identici al bit (`test_mappa` invariato) |
| D8 | La soglia dell'event study (`soglia_rumore_orizzonte`) | Non si tocca: è una simulazione che suppone l'incertezza giusta. Con l'incertezza corretta torna coerente |
| D9 | Il notebook di ricerca | Usa le stesse funzioni: si allinea da solo. Il confronto del §4 si fa anche lì, su BINANCE_PERP_BTCUSDT |

### Decisioni di Mattia (28/10/2026, via sul documento, PR #85)

- **D1 sì:** un calcolo solo, quello della mappa, con i blocchi settimanali se la varianza esce zero o
  negativa.
- **D2 sì:** tutti e quattro i punti insieme (event study, rosa, atlante, profilo).
- **D3 sì:** il profilo 2a rientra. Alla schermata 4 una riga dice che le ore colorate della 2a decidono
  `X_INVERSIONE_TREND`.
- **D4 sì, margine fissato adesso, prima del collaudo:** con il calcolo nuovo, trigger frequenti e medi
  entro **3 punti** dal raro, e sotto il **20%**; il profilo entro q.
- **D5 sì, ma solo per le prove d'identità:** il calcolo vecchio a richiesta si toglie nella PR dopo la
  correzione.
- **D6, D7, D8, D9 sì.**

## 6 · Ordine dei lavori

1. Il via di Mattia su questo documento, con le decisioni del §5.
2. **Collaudo** (PR 1): `test_incertezza_lab.py` e il giro da 1.000 mercati, con il calcolo di oggi e
   quello della mappa affiancati, senza toccare il Lab. I numeri vanno in questo documento.
   Nessuna correzione: si ferma lì.
3. La decisione di Mattia sui numeri.
4. **Correzione** (PR 2): la funzione comune, il calcolo vecchio a richiesta, le prove d'identità
   del §4, `docs/00` (il problema aperto chiuso) e `docs/02`, se cambia la definizione di solidità.

## 7 · Il piano della correzione (PR 2; via di Mattia e del revisore, 28/10/2026)

**7.1 · La funzione unica (D1, D7).** `errore_sovrapposti(u, H, barre_settimana, pos=None,
fattore_n=1.0) -> (errore, a_blocchi)` si sposta da `mappa.py` a `stagionalita.py`.
- `pos=None`: `u` su tutte le barre (mappa, profilo, rosa contro la stessa ora, atlante). È il codice
  della mappa spostato riga per riga: la mappa resta identica al bit (`test_mappa.py` invariato).
- `pos` dato: `u` sono i valori dei soli ingressi, `pos` le loro barre (event study, `t_globale` della
  rosa). È il calcolo collaudato nella PR #86 (`_es_senza_sconto`), con `fattore_n = n/(n-1)` sulla
  diagonale e sulla riserva a blocchi, esattamente come nel collaudo.
- Le coppie a meno di H barre contano per intero; se la varianza esce zero o negativa, blocchi di
  una settimana (`a_blocchi = True`). Le barre in una settimana si ricavano dal passo delle barre.

**7.2 · Event study e rosa.** `event_study._errore_standard_sovrapposti` resta come funzione di comodo
e chiama la funzione unica con `pos`. Entra `_es_senza_sconto` (Mattia, 28/10): con ingressi tutti a
H barre o più il risultato è quello di oggi, al bit. La sezione D di `test_incertezza_lab.py`
dimostra l'uguaglianza al bit con il calcolo collaudato, sui mercati inventati della PR #86.

**7.3 · L'atlante.** Resta il motore numba: accanto a `_somme_per_cella` (con lo sconto, solo per il
calcolo vecchio) nasce `_somme_per_cella_piene` (le coppie per intero). Le celle misurate con somma
zero o negativa si ricalcolano con la funzione unica (blocchi di una settimana). Il motore somma in
fila, il collaudo a coppie: la sezione D confronta entro 1e-12 in relativo. Una colonna
`incertezza_blocchi` in atlante, rosa, profilo e sintesi dell'event study.

**7.4 · Il calcolo vecchio a richiesta (D5).** `with stagionalita.calcolo_vecchio():` rimette le
formule di oggi nei quattro punti del Lab (la mappa mai). Solo per le prove d'identità e per il test
B; un controllo verifica che all'uscita dal blocco, anche con un errore dentro, torni sempre il
calcolo nuovo. Si toglie nella PR dopo questa.

**7.5 · Le prove d'identità in tre passi** (Lab: `lab_btc`, `lab_btc_cella`, `lab_eth`; ricerca:
`ric_btc`, `ric_eth`).
1. **Calcolo vecchio a richiesta**, su una copia temporanea dei dati: gli stessi oggetti di main, al bit.
2. **Calcolo nuovo, sullo studio vero**, fermandosi alle misure: profilo (2a), event study (2c), rosa
   (3a), atlante (3c/3d), più le scelte che queste fanno da sole (trigger con numero=1, cella di
   `lab_btc_cella`, ore di X_INVERSIONE_TREND, `curve_scarto`). Le schermate 4–9 non girano; nella
   ricerca non gira niente dopo l'atlante. Possono cambiare solo (più la colonna nuova):
   - profilo: `incertezza`, `t`, `p`, `bh`;
   - event study: tutta la tabella `incertezza`; nella sintesi `incertezza_pct`, `volte_incertezza`,
     `oltre_rumore` e l'ordine delle righe;
   - rosa: `t_netto`, `t_globale`, `p`, `bh`, `candidata`, `nella_rosa`, `rho_max`, `perche`, l'ordine;
   - atlante: `t`, `p`, `bh`, `passa`, `motivo`;
   - le scelte fatte da queste misure, e quello che ne discende fino all'atlante.
   Curve, mercato, bande, scarti, eventi, celle misurate, famiglie e `rosa_sistemi` devono restare
   identici. Ogni differenza fuori elenco, o non spiegata da una scelta cambiata, ferma il lavoro.
3. **A scelte fissate** (trigger, cella e uscite del passo 1 scritti a mano), su una copia
   temporanea: le schermate 4–9, e nella ricerca tutto quello che viene dopo la rosa, identiche al
   bit al passo 1. Se il passo 1 o il passo 3 mostrassero qualcosa con una chiave nuova del conto,
   ci si ferma.

**7.6 · Il conto delle prove (Mattia, 28/10).** Le stesse cose rimisurate sugli stessi dati lasciano
il conto uguale; le scelte nuove sono chiavi nuove e contano; il conto non scende mai; nessuna voce
speciale per la correzione (niente +70). Nella PR, per ogni dataset degli scenari, il conto prima e
dopo il passo 2 e le chiavi nuove entrate.

**7.7 · La riga alla schermata 4 (D3).** Sempre visibile, sotto la riga delle uscite: «X_INVERSIONE_TREND
usa le ore colorate del profilo della 2a: il long si chiude all'arrivo di un'ora rossa, lo short
all'arrivo di un'ora verde. Se cambiano le ore colorate della 2a, cambiano anche queste chiusure.»

**7.8 · File e test.** Cambiano `engine/stagionalita.py`, `mappa.py`, `event_study.py`, `rosa.py`,
`atlante.py`, `vetrina.py`, `test_incertezza_lab.py` (B: calcolo vecchio a richiesta contro calcolo
nuovo; D: uguaglianza con il calcolo collaudato; A3: il ritorno al calcolo nuovo), `docs/75`,
`docs/00`. I notebook no (D9). I test esistenti che misurano effetti o il caso non si toccano: se uno
fallisce ci si ferma, senza allargare soglie.
