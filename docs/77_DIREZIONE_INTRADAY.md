# 77 · Direzione della ricerca: edge direzionali intraday

**Incarico del 29/10/2026** (Mattia e il revisore, per Claude Code). Sostituisce la bozza «dalla fascia al trigger» (ramo locale `dalla-fascia-al-trigger`, mai pushato: si butta).
Flusso: proposta in testo senza codice → controllo del revisore → via di Mattia → codice, una PR per lavoro.

**Stato:** decisioni di Mattia il 29/10/2026 (§P4). Lavoro 1 fatto (§P5, PR #91); lavoro 2 fatto (§P6).

**Indice.** Incarico: Cosa cerchiamo · Decisioni · Lavoro 1 · Lavoro 2 · Lavoro 3 · Lavoro 4 · Regole.
Proposta (Claude Code, 29/10/2026): §P1 Lavoro 1, togliere funding e basis · §P2 Lavoro 2, orizzonti
1, 4 e 8 ore · §P3 Decisioni da prendere prima del codice · §P4 Decisioni di Mattia · §P5 Resoconto
del lavoro 1 (*resoconto*) · §P6 Resoconto del lavoro 2 (*resoconto*).

## Cosa cerchiamo (Mattia, 29/10/2026)

Edge **direzionali intraday**, trade aperti **da 1 a 8 ore**, basati sul **prezzo** (e sul volume):
- rotture di livelli e range;
- inversioni dopo eccessi;
- trend e momentum.

Il guadagno viene dal movimento del prezzo e deve coprire i costi e lasciare un guadagno. Nessuna soglia minima di rischio/rendimento, nessuna preferenza sul numero di trade: conta che il sistema sia profittevole.

**Non cerchiamo** edge da meccanica dello strumento (funding, basis, compensazioni, quasi-arbitraggi): briciole.

## Decisioni di Mattia (29/10/2026)

- **Funding e basis: tolti del tutto.** Via il download, le colonne, l'asse «basis» dell'atlante e le schede M01, M04 e M05 dal catalogo della mappa. Le prove già contate restano nello studio: il conto non scende mai. docs/73 e docs/74 restano come storia.
- **M06** (BTC che anticipa le altcoin di circa 1 ora): **resta.**
- **M07** (rendimento a 4 ore estremo, inversione): diventa trigger (long ed short, le due fasce della scheda, stesse soglie), come previsto nella bozza del 29/10.
- **Ordine dei lavori:** 1) togliere funding e basis; 2) orizzonti multipli 1, 4 e 8 ore; 3) trigger M07; 4) volume aggressivo (taker buy volume) come variabile per rotture e momentum.

## Lavoro 1 · Togliere funding e basis

La proposta deve dire:
- file, funzioni, colonne e test che si tolgono; cosa resta nei notebook (Lab, ricerca, mappa);
- cosa cambia nell'atlante dei perpetual senza l'asse «basis» (quante situazioni per lato) e **come entra nel conto**: se le situazioni rimaste sono già state misurate con la stessa chiave o una equivalente, non si contano di nuovo (stessa logica della regola (b) del 29/10); altrimenti contano;
- prove d'identità: sugli spot tutto identico al bit; sui perpetual cambia solo ciò che dipende dall'asse tolto.

## Lavoro 2 · Orizzonti multipli (1, 4, 8 ore)

Già previsto (`68` §13). La proposta deve dire:
- come il Lab e la ricerca misurano lo stesso segnale a più H (su M15: 4, 16, 32 barre) e come si sceglie l'H;
- come entra nel conto (la voce «orizzonte» esiste già): il costo di provare tre H invece di uno, spiegato in parole semplici;
- cosa vedono le schermate (una colonna per H? una scelta alla 1?).

## Lavoro 3 · Trigger M07

Due trigger, E45 long (il rendimento a 4 ore entra nel quintile più basso) ed E45 short (entra nel più alto), con le soglie della scheda, finestra della mappa, nessun parametro nuovo. Test: barre giuste su dati inventati, `verifica_lookahead`, `verifica_degenerazione`, niente dopo un buco nei dati. Conto: +2 trigger per dataset, situazioni con la regola (b).

## Lavoro 4 · Volume aggressivo

Già previsto: taker buy volume di Binance (via ccxt). Proposta a parte, dopo i lavori 1–3.

## Regole

- Fermarsi solo per cose che cambiano i risultati, rompono il codice o toccano il conto.
- Nessun commento sui risultati dei dati veri.
- PR aperta controllata prima di ogni push; date corrette; il merge lo fa Mattia.

---

# Proposta (Claude Code, 29/10/2026)

Solo testo, nessun codice. Nessun risultato sui dati veri.
- **Dallo studio** ho letto solo le **chiavi** del conto e i numeri delle prove: orizzonti provati,
  assi ed elenco dei trigger delle situazioni. Servono a dire come entrano le cose nel conto.
- **I numeri sul costo degli orizzonti** (§P2.3) vengono dalla simulazione su rumore di
  `giudizio.soglia_rumore_orizzonte` (seme fisso), non dai dati.

## P1 · Lavoro 1: togliere funding e basis

### P1.1 Il funding come costo: una distinzione che cambia i risultati

Nel codice il funding fa **due mestieri diversi**.
1. **Un costo del trade.** Dal 21/10 ogni trade su un perpetual paga o incassa il funding delle
   liquidazioni in cui è aperto: colonna `FundingPips`, `docs/63` §5.
   - Lo contano:
     - il motore delle uscite e quello dei filtri;
     - le due metà e la scheda;
     - il money management e il mercato nullo;
     - il netto dell'atlante (`funding_avanti`) e il netto della mappa.
   - Per questo servono il download del funding e il taglio delle barre a dove arriva il funding
     (`studio.taglia_al_funding`).
2. **Una variabile da cui nasce il segnale.** La usano solo le schede M01 e M04 della mappa
   (`funding_segno_prima_pagamento`, `funding_rispetto_al_base`).

L'incarico dice di togliere anche il download. Senza il download sparisce anche il primo mestiere:
- tutti i risultati sui perpetual cambiano;
- il backtest smette di contare un costo che il conto vero paga.

**Propongo di togliere solo il secondo mestiere** e di tenere il funding come costo:
- download, file `<SYMBOL>_FUNDING.csv`, `FundingPips` e taglio delle barre restano come oggi;
- così su ogni perpetual i trade restano identici al bit.

Decisione D1 in §P3.

La basis invece fa un mestiere solo, la variabile: l'asse «basis» dell'atlante e la scheda M05. Si toglie
tutta.

### P1.2 Cosa si toglie (con D1 come consiglio)

Modifiche **non additive**, lo dichiaro: si tolgono funzioni dell'engine.

| dove | cosa si toglie | cosa resta |
|---|---|---|
| `engine/indicatori.py` | `funding_liquidato`, `funding_segno_prima_pagamento`, `funding_rispetto_al_base`, `barre_prima_del_pagamento` e la sua funzione d'appoggio, `ORE_PAGAMENTO_FUNDING`, `FUNDING_BASE`, `FUNDING_TOLLERANZA`, `basis_bp`, `basis_alta` | tutto il resto |
| `engine/exchange.py` | `colonne_perpetual`: aggiunge alle barre `funding_tasso`, `funding_intervallo_ore` e `spot_close`, e serve solo alle variabili tolte | scarico, lettura, controlli e conto del funding come costo (`scarica_funding`, `leggi_funding`, `funding_per_trade`, `aggiungi_funding`, `funding_avanti`, ...) |
| `engine/atlante.py` | l'asse `basis` (`CELLE["basis"]`, `ha_basis`, le etichette `BASIS_ALTA` e `BASIS_BASSA`, il controllo della cella con lo spot); `ASSI` = vol_trend e sessione, ovunque | il netto con il funding |
| `engine/vetrina.py` | `aggancia_spot` e la chiamata in `prepara`, `s.spot_nota`; i testi della 1 («con lo spot della stessa coppia») e della 3c («2 di basis sui perpetual») | il funding nella schermata 1 e nella tabella dei costi |
| `engine/aggiorna_dati.py` | la parte «spot» dell'aggiornamento di un perpetual (`spot_della_coppia`), che scaricava lo spot solo per la basis | candele e funding; gli spot restano dataset a sé, scaricati da `scarica_dati_crypto.py` come oggi |
| `engine/mappa.py` | le variabili `funding_segno_prima_pagamento`, `funding_liquidato`, `funding_rispetto_al_base` e `basis_bp`; in `prepara_df` funding e spot; i controlli «la scheda vuole il funding / lo spot» | BTC per M06; il netto con il funding |
| `engine/ipotesi.py` | le schede M01, M04 e M05 dal catalogo; il campo `serve` perde «funding» e «spot» | M06, M07 e le schede di prova dei test |
| `engine/vetrina_mappa.py` | `_carica_spot`; la riga «Spot della stessa coppia» della schermata 1 | la riga del funding, con il testo «contato come costo» |

**Gli esiti già misurati di M01, M04 e M05** restano:
- nel giornale della mappa (`mappa_pc.jsonl`, dove si aggiunge e basta);
- nel conto, con le loro fasce.

La 2b del Lab e il notebook della mappa li mostrano in fondo alla tabella, con la nota «scheda tolta dal
catalogo il 29/10/2026», senza misurarli di nuovo.

**Notebook** (script JSON che conservano il formato, mai NotebookEdit):
- **Lab Crypto:**
  - cella 10: il testo della 3c diventa «8 situazioni per lato», senza la basis;
  - cella 4: il testo del funding resta, perché il funding resta un costo.
- **Ricerca:**
  - cella 9: via l'import di `aggancia_spot`;
  - cella 18: via la chiamata ad `aggancia_spot` e la sua stampa;
  - cella 44: via la riga «basis» della tabella degli assi.

  Restano `FUNDING = True`, `costi_storico(..., funding=funding)` e `atlante(..., funding=funding)`.
- **Mappa:**
  - cella 2: «sul perpetual anche funding e spot» diventa «sul perpetual anche il funding, per i
    costi»;
  - cella 4: via la riga delle schede del funding e della basis.
- **Collaudo_Catalogo:** niente da cambiare.

**Test che cambiano** (li dichiaro, come da regola):
- `test_funding.py`: via la parte E (funding liquidato e basis). Restano le parti sul funding come
  costo.
- `test_atlante.py`:
  - via il controllo 8 (basis) e la basis dai dati inventati;
  - i controlli sugli assi e sul numero di celle passano da 10 a 8 celle per lato sui perpetual;
  - nuovi controlli:
    - sul perpetual l'atlante ha solo vol_trend e sessione, anche con lo spot nella cartella;
    - la regola del conto del §P1.4.
- `test_mappa.py`:
  - la parte C perde M01 e M04;
  - la D perde il conto di M01 (2 + 96) e tiene M07;
  - la F3 (M05 con la basis zero, M04 con il funding fermo) diventa lo stesso controllo su una scheda
    di prova a quintili con valori uguali. Il controllo «si ferma prima di misurare» resta.
- `test_dati_confine.py`: il controllo alle righe 212–215 dice oggi che l'aggiornamento ha scaricato
  lo spot e che il df ha `spot_close`. Diventa: l'aggiornamento di un perpetual scarica candele e
  funding, niente spot.

### P1.3 L'atlante dei perpetual senza la basis

Gli assi dell'atlante **non si incrociano** (`docs/66` §2): ogni cella si misura da sola, con le sue
barre. Celle per trigger e per lato:

| | vol_trend | sessione | basis | per trigger |
|---|---|---|---|---|
| perpetual, prima | 4 | 4 | 2 | 10 |
| perpetual, dopo | 4 | 4 | — | **8** |
| spot, prima e dopo | 4 | 4 | — | 8 |

Il catalogo di oggi su BTC perp ha 71 trigger: 36 long e 35 short.
- **Long:** il massimo passa da 360 a **288 situazioni**.
- **Short:** il massimo passa da 350 a **280 situazioni**.
- Si contano solo le celle con almeno 200 eventi (`MIN_EVENTI`): il numero vero scende sotto le 558
  di oggi, e la prova d'identità lo stampa.

**Nelle celle rimaste:**
- scarto, solidità (t), due metà e netto di ogni cella vol_trend e sessione **non cambiano**: si
  calcolano con le stesse barre e lo stesso riferimento;
- può cambiare solo il controllo della quota di falsi positivi (Benjamini-Hochberg, colonne `bh` e
  `passa`), che si fa su tutte le celle misurate insieme. Con meno celle il controllo è un po' meno
  severo. È l'unico effetto, e dipende dall'asse tolto.

### P1.4 Come entra nel conto: è il caso «già misurate»

Nello studio (solo le chiavi) le situazioni contate sui perpetual hanno tutte gli assi vol_trend,
sessione e basis:

| dataset | H | trigger nella chiave | situazioni contate | elenco uguale a quello di oggi |
|---|---|---|---|---|
| BINANCE_PERP_BTCUSDT | 25 | 70 | 558 | no (manca E19) |
| BINANCE_PERP_BTCUSDT | 25 | 71 | 558 | **sì** |
| BINANCE_PERP_BTCUSDT | 25 | 72 | 565 | no (ricerca, un trigger in più) |
| BINANCE_PERP_BTCUSDT | 41 | 71 | 558 | **sì** |
| BINANCE_PERP_XRPUSDT | 25 | 71 | 541 | **sì** |

Gli altri dataset:
- **BINANCE_PERP_ETHUSDT e BYBIT_PERP_SOLUSDT:** nessuna situazione contata;
- **BYBIT_SPOT_ETHUSDT:** le chiavi sono già senza la basis e non cambiano.

**È il caso «già misurate».** Con stessi H e trigger, le celle vol_trend e sessione di un atlante senza
la basis sono esattamente le celle dell'atlante con la basis: prove già fatte e già contate.

**Il problema:** la chiave contiene gli assi. Senza una regola, l'atlante senza basis avrebbe una chiave
nuova e si conterebbe tutto da capo: su BTC circa 450 situazioni in più, per celle già misurate.

**Regola proposta (D2),** con la stessa logica della regola (b): una voce delle situazioni non si conta
di nuovo se una voce già contata ha gli stessi H e trigger e contiene i suoi assi.
- Lab e ricerca scrivono la voce nuova come oggi, con la sua chiave.
- Il conto la salta se una voce già contata la contiene.
- Le voci vecchie restano con il loro numero: 558 resta 558, il conto non scende mai.

**Cosa succede dataset per dataset:**
- **BTC con H 25 o 41, XRP con H 25:** il primo atlante senza la basis **non aggiunge niente**.
- **Con un H nuovo (lavoro 2) o con trigger in più (lavoro 3):** si conta come sempre, con la regola (b)
  per i trigger in più.
- **Sugli altri perpetual:** si conta come oggi, con 8 celle per trigger e lato invece di 10.

**Situazioni scelte con la basis.** Una cella `BASIS_ALTA` o `BASIS_BASSA` scelta alla 3d in una
sessione salvata non si apre più. Il Lab si ferma con la frase «la basis è stata tolta il 29/10/2026:
scegli una situazione di volatilità o di sessione».

### P1.5 Prove d'identità (con D1 come consiglio)

Si confronta prima e dopo la modifica, a parità di barre, nei due notebook vivi.

- **BYBIT_SPOT_ETHUSDT** (giro completo, solo long): tutto **identico al bit**. Vale per event study,
  rosa, atlante, uscite, filtri, trade, scheda, out-of-sample e conto.
- **BINANCE_PERP_BTCUSDT** (H = 25, le scelte delle prove passate):
  - **identici al bit:** event study, rosa, uscite, filtri, trade (`FundingPips` compreso), scheda,
    out-of-sample e conto delle prove;
  - **atlante,** cambia solo per l'asse tolto:
    - spariscono le righe `BASIS_*`;
    - nelle altre righe scarto, t, due metà e netto restano uguali;
    - `bh` e `passa` possono cambiare (§P1.3);
    - `k_misurate` scende;
  - **conto delle situazioni:** resta 558 (§P1.4);
  - **mappa:** M06 e M07 identiche; M01, M04 e M05 non si misurano e i loro esiti restano.
- **Suite completa** (`python suite_rapida.py --tutte`), con i test cambiati elencati sopra.

Se invece si toglie anche il funding come costo (D1, strada b), sui perpetual cambiano tutti i netti, i
trade e le schede. La prova d'identità vale solo per lo spot.

## P2 · Lavoro 2: orizzonti 1, 4 e 8 ore

### P2.1 La griglia

La griglia è **in ore**: 1, 4 e 8. In barre dipende dal timeframe, quindi nel codice non ci sono
costanti da M15:

| timeframe | 1 ora | 4 ore | 8 ore |
|---|---|---|---|
| M5 | 12 | 48 | 96 |
| M15 | **4** | **16** | **32** |
| M30 | 2 | 8 | 16 |
| H1 | 1 | 4 | 8 |
| H4 | — (si salta, con una nota) | 1 | 2 |

L'H in barre come oggi (per esempio H = 25) resta possibile, per le prove d'identità e per chi ha già
lavorato così.

### P2.2 Come Lab e ricerca misurano lo stesso segnale a più H

**Il tempo di calcolo.**
- L'event study calcola già la curva di ogni trigger barra per barra fino a 32 barre: leggerla a 4, 16 e
  32 barre non costa niente.
- La rosa (lo scarto **a** H, con quarantena e costi) si rifà per ogni H: tre volte il tempo di oggi.

**I tre H si misurano solo dove si sceglie il trigger:** alla 2c del Lab e alla Sessione 1 della
ricerca. Dalla 3 in poi si lavora solo con l'H scelto:
- atlante e suo conto;
- uscita a tempo della 4 (barre = H, come oggi);
- filtri, scheda e out-of-sample.

Rifare atlante, uscite e filtri a tre H triplicherebbe tutte le voci del conto, non solo quella dei
trigger.

**Come si sceglie l'H (D3).** Ci sono due strade.
- **Scelta dopo aver visto (consigliata).** Alla 2c si vedono i tre H, si sceglie, e la scelta **si
  conta**.
- **H dichiarato prima.** Un H della griglia si fissa alla 1 e gli altri non si mostrano: costa come
  oggi, ma l'H si sceglie senza guardare.

Sconsiglio la terza strada di `68` §13: H dichiarato alla 1 e gli altri «mostrati gratis». Chi ha visto
gli altri H sceglie sapendo, quindi non è gratis.

**Il Lab, schermata per schermata:**
- **1:** il campo «orizzonte» diventa una scelta, con accanto la conversione in barre del timeframe:
  - «1, 4 e 8 ore: scelgo alla 2c» (predefinito);
  - «1 ora», «4 ore» o «8 ore»;
  - oppure un numero di barre, come oggi.
- **2c:** la rosa dei trigger ha un gruppo di colonne per H: per ogni trigger, solidità e guadagno
  netto a 1, 4 e 8 ore.
  - Le casistiche si scelgono come oggi.
  - In più c'è il campo «H scelto», vuoto finché non lo riempi.
  - Con un H solo la 2c è quella di oggi.
- **3a:** la curva dello scarto ha tre segni verticali, uno per H.
- **Dalla 3c alla 6:** come oggi, all'H scelto. La riga in testa dice per esempio «H = 16 barre (4
  ore), scelto alla 2c fra 1, 4 e 8 ore».

**La ricerca:**
- **Sessione 1:**
  - due righe nuove, `ORIZZONTI_ORE = [1, 4, 8]` e `H_SCELTO = None`;
  - la rosa a tre H usa la stessa funzione del Lab, nuova e comune in `vetrina.py`;
  - finché `H_SCELTO` è vuoto la cella si ferma con «scegli H_SCELTO fra 4, 16 e 32».
- **Sessioni 2–4:** usano `H = H_SCELTO`, come oggi usano H.

### P2.3 Come entra nel conto, in parole semplici

**La voce «orizzonte» esiste già.**
- Ogni H usato su un dataset si scrive nel giornale: sono gli «H provati».
- Con più di un H provato, la voce dei trigger non vale più una prova per trigger: vale quanto
  **scegliere il migliore fra quegli H**. Lo calcola `giudizio.prove_trigger_orizzonti`, nel codice
  dal 25/10.
- Con la griglia, i tre H si scrivono tutti e tre appena la 2c li mostra, anche se poi se ne sceglie
  uno solo: li hai visti.

**Perché costa.** Guardare un trigger a 1, 4 e 8 ore e tenere l'orizzonte dove va meglio dà tre
occasioni, non una, di trovare un buon numero per caso. I tre orizzonti si sovrappongono un po', perché
le 4 barre di 1 ora stanno dentro le 16 di 4 ore. Per questo costano meno di tre prove intere, ma non
molto meno.

Simulazione su rumore (`soglia_rumore_orizzonte`, seme fisso, 1.000.000 di giri):

| cosa si sceglie | soglia di un trigger | prove equivalenti, 1 trigger | prove equivalenti, 71 trigger |
|---|---|---|---|
| un H solo | 1,96 | 1 | 71 |
| fra 4, 16 e 32 barre | 2,34 | 2,6 | 203 |
| fra 25 e 41 barre (BTC oggi) | 2,16 | 1,6 | 132 |
| fra 4, 16, 25, 32 e 41 barre (BTC dopo la griglia) | 2,44 | 3,5 | 291 |

**In pratica:**
- con la griglia **la voce dei trigger vale circa tre volte** il numero dei trigger: su un dataset
  nuovo, 71 trigger valgono circa 203 prove invece di 71;
- le altre voci (situazioni, sistemi, filtri) non cambiano, perché si fanno a un H solo.

**Gli H vecchi restano nel conto,** perché il conto non scende mai. Su BTC perp:
- oggi gli H provati sono 25 e 41;
- con la griglia diventano cinque;
- la voce dei trigger passa da circa 132 a circa 291 prove.

**Un H nuovo è un atlante nuovo.**
- La chiave delle situazioni contiene H: la prima 3c a H = 16 su BTC si conta tutta, perché è una
  misura nuova.
- Lo stesso vale per uscite e filtri, che hanno l'H nelle loro impostazioni.

**La riga delle prove lo dice** già oggi, cambiano solo i numeri: «71 trigger misurati con 5 orizzonti
provati sullo stesso dataset (H = 4, 16, 25, 32, 41), che valgono 291,1 prove (schermata 2c)».

### P2.4 Codice, test e identità, dopo il via

**Codice** (additivo):
- `vetrina.py`: la griglia in ore con la conversione in barre, la rosa a più H, i campi della 1 e della
  2c;
- `registro_dataset`: un modo per scrivere più H in una volta, senza una segnalazione di risalita per
  ciascuno;
- notebook: le celle 1 e 2c del Lab, la Sessione 1 della ricerca.

**Test** (`test_orizzonti.py`, nuovo):
- ore → barre per M5, M15, M30, H1 e H4 (1 ora su H4 si salta);
- la rosa a 3 H è uguale a tre rose a un H;
- i tre H finiscono nel registro anche se se ne sceglie uno, e la voce dei trigger è uguale a
  `prove_trigger_orizzonti`;
- l'atlante all'H scelto ha la chiave con quell'H;
- dalla 3c si lavora all'H scelto;
- la 2c si ferma senza un H scelto.

**Identità.** Con l'orizzonte in barre (H = 25) Lab e ricerca restano identici al bit a oggi, su BTC
perp e su ETH spot. Il lavoro 2 si fa dopo il lavoro 1, partendo dal main che lo contiene.

## P3 · Decisioni da prendere prima del codice

1. **D1, il funding come costo** (cambia i risultati):
   - **(a) consigliata:** si toglie il funding come variabile (M01, M04, colonne e funzioni) e resta
     come costo dei trade sui perpetual;
   - **(b):** si toglie tutto, download compreso. Sui perpetual cambiano tutti i risultati e il
     backtest non conta più un costo vero.
2. **D2, il conto delle situazioni senza la basis** (tocca il conto).
   - La regola: una voce con stessi H e trigger, e con assi contenuti in una voce già contata, non si
     conta di nuovo.
   - Con la regola, su BTC (H 25 e 41) e su XRP (H 25) il conto resta com'è.
   - Consiglio sì.
3. **D3, come si sceglie l'H** (tocca il conto):
   - **(a) consigliata:** griglia 1-4-8 ore alla 2c, scelta dopo aver visto, e contata: la voce dei
     trigger vale circa tre volte;
   - **(b):** un H della griglia dichiarato alla 1, gli altri non si mostrano, e costa come oggi.

   Il campo della 1 offre comunque tutte e due le strade. Si decidono due cose: quale è il predefinito,
   e se si abbandona il «mostrati gratis» di `68` §13.
4. **D4, la griglia: 1, 4 e 8 ore,** come dice l'incarico. Su H4 l'ora si salta. Serve una tua
   decisione solo se vuoi anche le 2 ore.

Dettagli di forma che risolvo io e scrivo in una riga nella PR:
- gli esiti delle schede tolte restano visibili, con la nota;
- la frase che ferma il Lab sulle situazioni `BASIS_*`;
- i segni sulla curva della 3a.

## P4 · Decisioni di Mattia (29/10/2026, dopo il revisore)

1. **D1:** il funding resta come **costo** dei trade sui perpetual (backtest identici); si toglie solo il funding
   come variabile da cui nascono segnali, con tutta la basis, come proposto.
2. **D2:** sì alla regola «già misurate»: stesso orizzonte, stessi trigger e assi contenuti in una voce già
   contata, non si contano di nuovo. Nel test del conto.
3. **D3:** (a), la griglia alla 2c, scelta dopo aver visto i tre orizzonti, e contata. Alla schermata 1 resta
   possibile fissare un orizzonte solo, in barre: serve alle prove d'identità contro main (41 nel Lab, 25 nella
   ricerca).
4. **D4:** griglia 1, 4 e 8 ore, niente 2 ore.
5. Niente push del solo documento: il lavoro 1 è una PR a sé, il lavoro 2 un'altra.

## P5 · Resoconto del lavoro 1 (*resoconto*, 29/10/2026)

**Cosa si e' tolto** (modifiche non additive, dichiarate):
- `engine/indicatori.py`: `funding_liquidato`, `basis_bp`, `basis_alta`, `barre_prima_del_pagamento`,
  `funding_segno_prima_pagamento`, `funding_rispetto_al_base` e le loro costanti;
- `engine/exchange.py`: `colonne_perpetual`; il funding come costo resta tutto;
- `engine/atlante.py`: l'asse `basis` (`ASSI` = vol_trend e sessione); una cella `BASIS_*` si ferma con la frase
  «la basis è stata tolta il 29/10/2026 ... scegli una situazione di volatilità o di sessione»;
- `engine/vetrina.py`: `aggancia_spot` e la riga «Spot (perpetual)» della schermata 1;
- `engine/aggiorna_dati.py`: lo scarico dello spot di un perpetual (`spot_della_coppia`);
- `engine/mappa.py`, `engine/ipotesi.py`, `engine/vetrina_mappa.py`: le variabili del funding e della basis,
  `prepara_df`, le schede M01, M04 e M05 (ora in `SCHEDE_TOLTE`, con la data). I loro esiti si mostrano in
  fondo alla tabella della 2b e del riepilogo della mappa, con la nota «scheda tolta dal catalogo il 29/10/2026».

**Cosa si e' aggiunto:** `registro_dataset.celle_gia_contate` e la regola D2 in `metti_prova` (una voce delle
situazioni contenuta in una gia' contata non entra; `metti_prova` ritorna False). La riga delle prove della 3c
lo dice: «nessuna in più (N situazioni misurate, già contate in un atlante con la basis)».

**Test cambiati:**
- `test_funding` 42/42: la parte E (stati del funding e basis) diventa un controllo solo, «tolti»;
- `test_atlante` 42/42: i controlli 5, 8, 10, 18, 23, 25, 28, 31, 36 senza la basis;
- `test_mappa` 34/34 (prima 39): tolti C2-C5 e C10 (M01, M04), C1 nuovo (schede tolte), F3 su una scheda di
  prova con i valori uguali, F5 con una misura vecchia di M05 che resta con la nota; la parte G usa schede di
  prova con i campi di M04 e M05 e da' gli stessi numeri di main (118/135, 67/73, 66/53);
- `test_dati_confine` 84/84: A4, A23, E6 (lo spot non si scarica piu');
- `test_conto_ricerca` 31/31: la parte E nuova, la regola D2 in memoria e nello studio.

**Prove d'identita'** (main contro ramo, a parita' di barre, copia dello studio):
- BYBIT_SPOT_ETHUSDT, Lab e ricerca, giro completo: identici (283/285 e 449/449 oggetti; le differenze sono
  la cartella temporanea e l'attributo `spot_nota` che non c'e' piu');
- BINANCE_PERP_BTCUSDT, Lab (H = 41) e ricerca (H = 25): tutto identico tranne l'atlante (700 righe -> 560:
  via le 140 righe della basis; nelle altre tutte le colonne identiche al bit, compresi `bh` e `passa`;
  `k_misurate` 558 -> 429) e la colonna `spot_close` che non c'e' piu' (il resto del df identico). Nessuna voce
  nuova delle situazioni nel giornale; la riga della 3c dice «nessuna in più»; il conto resta 3.410,6;
- la mappa sui dati veri, senza scrivere: M07 su BTC perp e M06 su ETH perp, tabelle e attributi identici.

**Conto per dataset nello studio vero, letto con main e con il ramo:** identico.

| dataset | k | situazioni |
|---|---|---|
| BINANCE_PERP_BTCUSDT_M15 | 3.410,6 | 2.804 |
| BINANCE_PERP_ETHUSDT_M15 | 5 | 0 |
| BINANCE_PERP_XRPUSDT_M15 | 652 | 541 |
| BYBIT_PERP_SOLUSDT_M15 | 105 | 0 |
| BYBIT_SPOT_ETHUSDT_M15 | 1.069 | 922 |
| BINANCE_PERP_BTCUSDT_M5 | 0 | 0 |

## P6 · Resoconto del lavoro 2 (*resoconto*, 29/10/2026)

**Cosa c'e' di nuovo** (modifiche additive):
- `engine/vetrina.py`: `ORIZZONTI_ORE = (1, 4, 8)` e `GRIGLIA`; `orizzonti_in_barre` (ore -> barre del
  timeframe, le ore non intere si saltano: 1 ora su H4), `leggi_orizzonte` (la griglia, un numero di barre,
  «4 ore»), `rosa_orizzonti` e `tabella_orizzonti` (comuni a Lab e ricerca), `orizzonti_della_ricerca`,
  `ferma_senza_orizzonte`; `prepara(H=GRIGLIA)`; `esplora(s, orizzonte=...)`; `registro_orizzonte(...,
  orizzonti=, scelto=)`; `grafico_scarto(..., punti=)` per segnare i tre H.
- `engine/registro_dataset.py`: `apri_griglia` (i tre H entrano subito fra gli H provati, senza una risalita
  per ciascuno) e `scegli_h` (l'H scelto diventa quello corrente).
- Lab: alla 1 il campo `orizzonte` ha come predefinito la griglia (si puo' scrivere un numero di barre: 41 per
  le prove d'identita'); alla 2c il campo `orizzonte_scelto`. Al primo giro la 2c mostra l'event study fino
  all'H piu' lungo, la rosa ai tre H (tabella con un gruppo di colonne per H) e le curve con i tre H segnati; le
  schermate dalla 3a si fermano finche' l'H non e' scelto. Scelto l'H, la 2c rifa' event study e rosa a
  quell'H e tutto il Lab lavora li'. La 2a, prima della scelta, e' all'H piu' lungo, con una nota.
- Ricerca: `ORIZZONTE = GRIGLIA` e `H_SCELTO` nella cella della Sessione 1; la 1.3 mostra la rosa ai tre H e si
  ferma finche' `H_SCELTO` non e' scritto.

**Il conto.** I tre H si scrivono fra gli H provati gia' alla schermata 1 (dettaglio di forma: chi sceglie la
griglia li vede alla 2c; contarli una schermata prima e' solo piu' prudente). La voce dei trigger diventa la
scelta fra tutti gli H provati sul dataset (`prove_trigger_orizzonti`, gia' nel codice). Nello studio vero,
se si usasse la griglia (simulazione su rumore, nessun dato): BTC perp da 129,6 a 287,3 (H 41, 25, 4, 16, 32),
XRP perp da 70 a 234,9, SOL perp da 64 a 217,2, ETH spot da 66 a 222.

**Test:** `test_orizzonti.py` nuovo, 24/24 (sezioni A-F), in `suite_rapida.py`. Suite completa 48/48.

**Prove d'identita'** (main contro ramo, stesse barre, copia dello studio):
- Lab BTC perp con `orizzonte = 41`, ricerca BTC perp con `ORIZZONTE = 25`, Lab e ricerca ETH spot (41 e 25):
  identici al bit (oggetti e voci del giornale); in piu' solo i nomi nuovi (`s.griglia`, `s.h_scelto`,
  `ORIZZONTI`...).
- Su dati inventati (non sui veri: la griglia sarebbe una prova nuova non contata): Lab con la griglia e la
  scelta «4 ore» contro Lab con 16 barre fisse, e ricerca con la griglia e `H_SCELTO = 16` contro 16 fisso:
  stessi numeri (trade, filtri, scheda); cambiano solo gli H provati (4, 16, 32) e quindi la voce dei trigger,
  e nel Lab il profilo della 2a non tenuto (era all'H provvisorio).

**Conto per dataset nello studio vero, letto con main e con il ramo:** identico (come in §P5).
