# 75 · Incarico: l'incertezza del Lab (rendimenti sovrapposti)

**Data:** 28 ottobre 2026
**Stato:** incarico scritto, **in attesa del via di Mattia**. Nessun codice, nessun numero sui dati
veri. Il collaudo del §3 si fa solo dopo il via.
**Da dove nasce:** il primo dei «Problemi aperti» di `00`. Il collaudo della mappa del 28/10 (sezione
G di `test_mappa.py`, PR #84) ha mostrato che l'incertezza con lo **sconto** (pesi decrescenti)
sottostima l'incertezza dei rendimenti sovrapposti. La mappa ha già la sua correzione; il Lab no.

**Indice:** §0 In breve · §1 Il problema · §2 Dove si usa oggi, e cosa decide · §3 Il collaudo
proposto · §4 Cosa cambierebbe nel Lab, e le prove d'identità · §5 Le decisioni per Mattia · §6
Ordine dei lavori.

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

## 6 · Ordine dei lavori

1. Il via di Mattia su questo documento, con le decisioni del §5.
2. **Collaudo** (PR 1): `test_incertezza_lab.py` e il giro da 1.000 mercati, con il calcolo di oggi e
   quello della mappa affiancati, senza toccare il Lab. I numeri vanno in questo documento.
   Nessuna correzione: si ferma lì.
3. La decisione di Mattia sui numeri.
4. **Correzione** (PR 2): la funzione comune, il calcolo vecchio a richiesta, le prove d'identità
   del §4, `docs/00` (il problema aperto chiuso) e `docs/02`, se cambia la definizione di solidità.
