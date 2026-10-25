# 71 · Proposta: lo spread di un passo al prezzo d'ingresso di ogni trade

**Data:** 26 ottobre 2026
**Stato:** PROPOSTA BREVE. **Nessun codice** prima dell'OK di Mattia.
**Nasce da:** `docs/70` §15.3 (la strada D, valutata in chat il 26/10).
**Decisioni già prese da Mattia (26/10):**
1. lo spread esce dal prezzo di fill;
2. un passo per trade nella colonna `CostoExtraPips`, nei due motori;
3. la confidenza usa il costo del singolo trade;
4. l'effetto su stop e target si dichiara e si misura (quanti trade cambiano
   uscita su BTC e su XRP).

**Indice:** §0 Perché · §1 Come funziona · §2 I consumatori da adattare · §3 Una
domanda: il prezzo della confidenza · §4 Collaudo · §5 Il confronto dichiarato · §6
Tempi · §7 Cosa resta com'è

---

## 0 · Perché

Oggi, sui symbol da exchange, lo spread di un passo diventa una **percentuale fissa**
del prezzo: un passo diviso il prezzo mediano dell'in-sample (`70` §15.3, strada A).
Il passo invece è un importo fisso. In bp vale tanto di più quanto più il prezzo è
basso.

| | passo | percentuale fissa di oggi | vero, in-sample (5°–95° percentile) | vero, out-of-sample (media) |
|---|---|---|---|---|
| BINANCE_PERP_BTCUSDT | 0,1 $ | 0,028 bp | 0,010–0,111 bp | 0,012 bp |
| BINANCE_PERP_XRPUSDT | 0,0001 $ | 1,9 bp | 0,43–5,0 bp (massimo 9,3) | 0,60 bp |
| BYBIT_SPOT_XRPUSDT | 0,0001 $ | 1,7 bp | 0,35–2,9 bp | 0,67 bp |

Le conseguenze su XRP:
- **Out-of-sample:** ogni trade paga circa 1,3 bp di troppo, il 13% della
  commissione andata e ritorno (10 bp).
- **Anni a prezzo basso o alto:** i trade del 2020 (prezzo 0,2 $) pagano 1,9 bp
  invece di 4–5. Quelli a 2–3 $ pagano 1,9 bp invece di 0,4.
- **Confronti per periodo:** le due metà, la confidenza nel tempo e i filtri di
  regime confrontano trade con un costo sbagliato in direzioni opposte.
- **In pips l'errore è al contrario.** La percentuale fissa fa crescere lo spread
  con il prezzo: a 3 $ vale circa 5,7 pips invece di 1. Lo si vede nel totale e nel
  drawdown in pips.

Su BTC lo spread è l'1–4 per mille della commissione: cambia poco, ma la regola è
la stessa.

---

## 1 · Come funziona

- **Nei motori lo spread è zero** sui symbol da exchange. Il prezzo di fill è l'Open
  della barra d'ingresso, senza spread, nel motore veloce come in «bt». I due motori
  restano identici fra loro: «bt» resta l'oracolo.
- **Un passo per trade nella colonna `CostoExtraPips`**, dopo il motore, come il
  funding (`exchange.aggiungi_funding`) e il rollover del broker
  (`quarantena_trade`):

  ```
  spread in pips = SPREAD_PASSI × passo_prezzo / pip         (0,1 su BTC ed ETH, 0,01 su BINANCE_SPOT_BTCUSDT, 1 su SOL e XRP)
  ```

  In pips è un numero fisso. In bp `metriche.bp_per_trade` lo converte già trade per
  trade con il prezzo d'ingresso: `passo / prezzo d'ingresso × 10.000`.
  Si paga una volta, all'ingresso, come oggi.
- **Nei costi** (`costi_storico`): `costi["spread"] = 0.0` più una voce nuova,
  `costi["spread_passo_pips"]`. `run_exit_search_bt` e `run_filter_search_bt` la
  ricevono con `**costi` (parametro nuovo, additivo; `None` = come prima) e la
  aggiungono a `CostoExtraPips`.
- **Stop e target.** Oggi si misurano dal prezzo d'ingresso che contiene lo spread;
  con questa strada si misurano dall'Open. Il livello si sposta di circa un passo e
  qualche trade può uscire in un punto diverso: lo si **dichiara e lo si misura**
  (§5).
- **La commissione** si calcola sul prezzo di fill, che si abbassa di un passo: una
  differenza di qualche milionesimo, che si dichiara.
- **Il broker (sospeso) non cambia:** spread di listino dentro il prezzo, come oggi.

---

## 2 · I consumatori da adattare

| dove | oggi | con la strada D |
|---|---|---|
| `vetrina.costi_storico` | `spread` = passo / mediana dell'in-sample | `spread = 0`, `spread_passo_pips` = passo / pip; resta `sp["normale"]` (in pips, già giusto) |
| `exit_search_bt`, `filter_search_bt` (e `due_meta`, che li chiama) | spread nel prezzo di fill | parametro `spread_passo_pips`, aggiunto a `CostoExtraPips` dopo `costo_extra_pips` |
| `vetrina` 2754 (`solo_costi`, le chiavi che passano ai motori) | `spread`, `commission`, ... | più `spread_passo_pips` |
| `atlante` (il netto di ogni evento) | `spread × ingresso / pip` | `spread_passo_pips`, fisso in pips (in bp segue il prezzo dell'evento) |
| `confidenza.costo_andata_ritorno_bp` e le soglie `CONF_BP_MEDI_xC` | un costo solo: (2 × commissione + spread) × 10.000 | il costo del singolo trade: 2 × commissione + passo / prezzo (§3); le soglie restano multipli del costo, trade per trade |
| `mm_adattatore` (il rischio del money management) | `spread_pips + (lordi − netti)` | **niente `spread_pips` in più**: con la strada D lo spread è già in `lordi − netti`, e altrimenti si conterebbe due volte |
| `vetrina._mostra_costi` (tabella dei costi) | `spread × ingresso / pip + CostoExtraPips` | si adatta da sola (`spread = 0`, il passo sta in `CostoExtraPips`); cambia solo il testo della riga |
| `vetrina_verifica` (il fill atteso) | `Open × (1 ± spread)` | si adatta da sola (`spread = 0`: il fill è l'Open) |
| riepilogo della schermata 1 («Costo per trade in bp») | spread al prezzo mediano dell'in-sample | «spread di un passo al prezzo d'ingresso: da x a y bp nell'in-sample (mediana z)» |
| `montecarlo`, `giudizio`, `rosa_sistemi`, stress test | usano i pips netti dei trade | si adattano da soli |
| notebook di ricerca: cella 72 (`COSTO_RT_BP`, confidenza) e cella 83 (money management, `spread_pips=`) | il costo unico | le stesse funzioni nuove; allineato al Lab |
| `test_exchange` F2, `test_confidenza`, `test_motore_veloce`, ... | la regola di oggi | i test che verificano la regola vecchia passano alla nuova (dichiarato, come F2 nella PR #71); nessuno si ammorbidisce |

Restano identici perché non usano i costi: event study, profilo orario, curve dello
scarto, rosa dei trigger, classifiche e conto delle prove.

---

## 3 · Una domanda: il prezzo della confidenza

Mattia ha deciso il costo del singolo trade, «il prezzo d'ingresso è noto al
momento del trade». C'è un dettaglio da decidere.

Il filtro di confidenza si valuta sulla **barra del segnale**, e il trade entra
all'Open della barra dopo. Se la soglia usasse quell'Open, il valore del filtro
nella barra del segnale dipenderebbe dalla barra dopo: `verifica_lookahead` lo
segnalerebbe, giustamente.

**Proposta: la soglia usa il Close della barra del segnale**, l'ultimo prezzo noto
quando si decide. Rispetto all'Open dopo differisce al più per il salto fra le due
barre, cioè di qualche millesimo del costo. Il bp netto del trade, quello che la
confidenza media nel tempo, resta invece calcolato con il vero prezzo d'ingresso.

Decide Mattia: Close della barra del segnale (raccomandato) oppure Open della barra
d'ingresso, con il filtro spostato di una barra.

---

## 4 · Collaudo (test a risultato noto)

1. **Un trade a mano:** long all'Open 100, passo 0,01, pip 0,01 → `CostoExtraPips` =
   1 pip, 1 bp. Lo stesso trade all'Open 200 → 1 pip, 0,5 bp.
2. **I due motori:** spread zero e passo in `CostoExtraPips` danno trade identici al
   bit (fill, uscite, `CostoExtraPips`, pips netti), long e short, con e senza stop.
3. **La somma torna:** sui trade con la stessa uscita, netti_D − netti_oggi =
   (spread_oggi × Entry_oggi − passo) / pip, più il pezzetto di commissione, a meno
   di 1e-9.
4. **Atlante:** il costo di un evento è passo / pip in pips, passo / prezzo in bp.
5. **Confidenza:** due trade con la stessa media mobile e prezzi diversi; la soglia a
   1C fa passare quello a prezzo alto e non quello a prezzo basso. La soglia della
   barra usa il Close della barra (`verifica_lookahead`).
6. **Money management:** il costo del rischio contiene lo spread una volta sola.
7. **Il broker non cambia:** EURUSD, costi e trade identici a prima.
8. **Riepilogo:** la riga del costo dice l'intervallo in bp.

---

## 5 · Il confronto dichiarato (al posto dell'identità)

I numeri cambiano su tutti i symbol da exchange, quindi non si chiede l'identità con
main. Si chiede un **confronto dichiarato**: main contro ramo, CSV del 19/10, con la
copia di main e le cartelle delle prove del `70` (tenute per questo). Lab e notebook
di ricerca su:
- **BINANCE_PERP_BTCUSDT** (il dataset di sviluppo);
- **BINANCE_PERP_XRPUSDT** (dove l'effetto è grande);
- **BYBIT_SPOT_ETHUSDT** (il giro di controllo, solo long).

Si riporta:

| cosa | atteso |
|---|---|
| event study, profilo, curve, rosa dei trigger, conto delle prove | **identici** |
| spread medio in bp, in-sample e out-of-sample | come nella tabella del §0 |
| **trade che cambiano uscita** (barra o prezzo d'uscita diversi) | quanti e in percentuale, per BTC e XRP, separati fra stop, target e uscita a H barre |
| trade con la stessa uscita | la somma del §4 punto 3 torna |
| guadagno medio netto (bp e pips), totale, solidità, in-sample e out-of-sample | prima → dopo |
| confidenza: quanti segnali cambiano lato della soglia | prima → dopo |
| rosa dei sistemi, atlante netto, scheda, money management, stress test | prima → dopo, senza giudizi |

I numeri sono un collaudo del tool, non un verdetto.

---

## 6 · Tempi

| cosa | tempo |
|---|---|
| Codice (engine additivo, consumatori del §2, i due notebook) e test del §4 | una PR, un giorno di lavoro |
| Suite completa | circa 13 minuti |
| Confronto dichiarato: 3 symbol × 2 notebook × main e ramo = 12 giri, 3 alla volta | circa 40 minuti di macchina |
| Resoconto in questo documento | a fine PR |

Prima della PR resta la suite completa.

---

## 7 · Cosa resta com'è

- L'ipotesi che lo spread sia **un passo** (`SPREAD_PASSI = 1`): cambia solo come lo si
  converte.
- La commissione taker di listino e il funding.
- Il confine dello studio e la mediana dell'in-sample per tutto ciò che non è
  spread.
- Il broker.
