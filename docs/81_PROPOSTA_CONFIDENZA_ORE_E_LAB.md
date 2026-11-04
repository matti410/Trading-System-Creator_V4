# 81 · Proposta: confidenza in ore, ancora per timeframe, cella nel Lab

**Data:** 04/11/2026. **Incarico:** `80`. **Stato:** approvata da Mattia il 04/11/2026, con la decisione 3 cambiata
(§2.3, §7); codice sul ramo `confidenza-ore-e-lab`. Misure con uno script usa e getta fuori dal repo, in sola lettura, sull'in-sample dello studio di
BINANCE_PERP_BTCUSDT (02/01/2020–15/06/2025, H1, H4 e D1 ricavate dalle M15): solo finestre e riempimento delle celle.
Nessun segnale, nessun rendimento guardato, niente scritto nello studio: nessuna prova in più.

**Indice:** §0 In breve · §1 Lavoro 1 · §2 Lavoro 2 · §3 Lavoro 3 · §4 Le domande dell'incarico · §5 Collaudo e prove
d'identità · §6 Commit · §7 Decisioni di Mattia

## §0 · In breve

- **Fino a H1 nessun numero cambia per l'ancora.** Le finestre in ore cambiano la confidenza solo su M5, M30, H1 e H4;
  su M15 tutto resta identico al bit.
- **Su H4 cambiano la confidenza e l'atlante** (asse trend). Oggi nessun numero già contato cambia significato: nello
  studio non c'è nessun dataset H4 o D1, e le voci della confidenza stanno solo su dataset M15 (§5).
- **Lab:** una cella nuova, la **5b**, spenta di default. Da spenta, il Lab resta identico al bit e non si conta niente.
- **Tre cose trovate nel codice che l'incarico non dice:** la frase sulle ore di H1 non è esatta (§1), D1 oggi non si
  può aprire nel Lab (§2.2), e una soglia di confidenza registrata entra di nascosto nella ricerca dei filtri se la si
  rifà, già oggi nella ricerca (§3.5).

## §1 · Lavoro 1: la confidenza in ore

`cella_contesto` e `confidenza_rolling` calcolano la cella con `indicatori.cella_vol_trend`. Restano in trade
`finestra_trade=500` e `min_obs=30`.

| timeframe | deviazione | mediana | prima cella calcolabile | durata media dello stato (vol / trend) |
|---|---|---|---|---|
| M5 | 60 barre = 5 ore | 1.500 barre = 125 ore | barra 1.559, 5,4 giorni (calcolata) | — |
| M15 | 20 barre = 5 ore | 500 barre = 125 ore | barra 519, 5,4 giorni | 6,1 / 6,9 ore |
| M30 | **20 barre = 10 ore** | 250 barre = 125 ore | barra 269, 5,6 giorni (calcolata) | — |
| H1 | **20 barre = 20 ore** | 125 barre = 125 ore | barra 144, 6,0 giorni | 18,6 / 9,4 ore |
| H4 | **20 barre = 80 ore** | **210 barre = 5 settimane** (§2.3) | barra 229, 38 giorni (calcolata) | nel resoconto |
| D1 | **20 barre = 20 giorni** | **150 barre = 5 mesi da 30 giorni** (§2.3) | barra 169, 169 giorni (calcolata) | nel resoconto |

**Correzione alla frase dell'incarico** («su M5/H1 le finestre coprono le stesse ore di M15»). Vale per intero su M5. Su
H1 vale per la mediana, non per la deviazione: 5 ore sarebbero 5 barre, e il minimo di 20 la porta a 20 ore. È la regola
già decisa per l'atlante (`66` §2.1), quindi non la cambio: il collaudo verifica questa tabella (decisione 1).

**Modifica non additiva, la dichiaro.** I parametri `finestra` e `finestra_vol` di `cella_contesto` e
`confidenza_rolling` diventano `ore` e `ore_mediana`. Nessuno li usa oggi, né i notebook né i test. `asse_volatilita`
resta com'è: serve da riferimento al collaudo.

**Un test da riscrivere.** La prova 2 di `test_atlante.py` confronta `cella_vol_trend` con `cella_contesto`: dopo il
lavoro sarebbero la stessa funzione e la prova non direbbe più niente. Il riferimento diventa la formula vecchia,
congelata nel test (`asse_volatilita(df, 20, 500)` più il trend con la mediana a 500 barre).

## §2 · Lavoro 2: l'ancora secondo il timeframe

### 2.1 · La regola

Nuova funzione `indicatori.periodo_ancora(df)`, usata solo da `gap_trend`. Dalla durata della barra:

- almeno `MINIMO_RENDIMENTI` barre in una giornata → la giornata, con `giorno_fx` come oggi (M5, M15, M30, H1);
- altrimenti almeno 20 in 7 giorni → la settimana, `id_periodo(df, "W")` (H4: 42 barre, lunedì 00:00 UTC);
- altrimenti almeno 20 in 28 giorni → il mese, `id_periodo(df, "M")` (D1: 28–31 barre);
- altrimenti si ferma con un errore.

`id_periodo` esiste già ed è già collaudato (`test_giornata_utc.py`). Sul broker sospeso la settimana parte domenica
alle 17:00 di New York: non si rompe, e non lo misuro. Tutto il resto che usa la giornata (F36, F38, F39, E23, E31, ATR)
non si tocca. Oggi `gap_trend` lo usano solo la confidenza e l'atlante.

**Perché serve, con un numero.** Su D1 con l'ancora di oggi il gap è esattamente Close meno prezzo tipico su tutte le
1.992 barre: misura dove chiude la barra, non il trend.

**Cosa cambia su H4 e D1, da scrivere nel resoconto:** la confidenza e l'asse volatilità × trend dell'atlante. L'asse
sessione no.

### 2.2 · D1 non si può aprire nel Lab

`TIMEFRAMES` del Lab arriva a H4, non c'è nessun CSV D1, e la griglia di 1, 4 e 8 ore su D1 è vuota (nessuna durata è un
numero intero di barre). **Proposta:** la regola vale anche per D1 e si collauda su una serie sintetica, ma il Lab non
apre D1 in questo lavoro (decisione 2).

### 2.3 · La mediana copre almeno 5 periodi di ancora (decisione di Mattia, 04/11)

Con 125 ore fisse, su M15 la mediana copriva 5,2 giornate, ma su H4 solo 0,74 settimane e su D1 circa 0,65 mesi: a inizio
periodo il gap si confrontava con la coda del periodo prima. Quota di «trend a favore» del long, per terzo del periodo,
misurata **con le 125 ore** (la tabella con la regola nuova va nel resoconto):

| timeframe, ancora | primo terzo | secondo | ultimo |
|---|---|---|---|
| M15, giornata | 48,3% | 49,7% | 51,0% |
| H4, settimana | 45,4% | 51,2% | 50,1% |
| D1, mese | 47,1% | 55,8% | 53,2% |

**La regola, fissa e decisa a priori:** la mediana dell'asse trend e, per coerenza, dell'asse volatilità copre il
**maggiore fra 125 ore e 5 periodi di ancora**. È la stessa proporzione di M15.

| timeframe | ancora | 5 periodi | mediana |
|---|---|---|---|
| M5, M15, M30, H1 | giornata | 120 ore | 125 ore: identico al bit |
| H4 | settimana | 840 ore | 210 barre |
| D1 | mese (per questo calcolo, 30 giorni) | 3.600 ore | 150 barre |

Il mese conta 30 giorni perché la finestra è un numero fisso di barre, mentre il mese solare cambia durata. Vale il
minimo di 20 barre di sempre. Nuova funzione `indicatori.barre_mediana`, usata da `volatilita_durata` e `trend_durata`.

## §3 · Lavoro 3: la cella 5b del Lab

### 3.1 · Cosa fa

`vetrina.confidenza_strategia(s, usa=False, filtro="")`. La cella non ha codice, chiama solo questa funzione.

1. **Spenta:** una riga e basta. Nessun backtest, nessuna prova. **Strada B:** una frase che dice perché si salta (§4).
2. Il filtro scritto nella cella si applica come alla 6 (`_catena_filtri`, poi `congela_filtro`).
3. **La storia:** la baseline di quel setup su tutta la serie, senza mostrare niente dell'OOS, senza scrivere nel diario.
4. `esiti_trade`, `confidenza_rolling` per lato, `registra_filtro_confidenza` con `SOGLIE_CONFIDENZA`,
   `congela_confidenza_nota`, poi `run_filter_search_bt` su `df_is` e `due_meta` sulle soglie promosse: come la 3.3.
5. **Si mostra:** riga del riscaldamento (§4, domanda 3), valore in bp di ogni soglia, tabella tenuti/scartati,
   calibrazione in-sample, riga delle prove. Se nessuna soglia supera le due prove, lo dice: si va alla 6 senza.

**Le soglie:** `CONF_BP_MEDI_0C`, `0.5C`, `0.8C`. Valgono circa 0, 5 e 8 bp sul perpetual Binance BTC, circa 0, 10 e
16 bp sullo spot Bybit ETH (più il passo di spread). Una costante sola, `confidenza.SOGLIE_CONFIDENZA = (0.0, 0.5, 0.8)`,
letta anche dalla cella 72 della ricerca.

### 3.2 · Le due celle del Lab

```
#@title 5b · La confidenza (facoltativa) { display-mode: "form" }
usa_confidenza = False  #@param {type:"boolean"}
#@markdown Lo stesso filtro che porterai alla 6. Vuoto = sistema base.
filtro = ""  #@param {type:"string"}
confidenza_strategia(s, usa=usa_confidenza, filtro=filtro);
```

Alla 6 si aggiunge un campo, `soglia_confidenza = ""`: vuoto = senza confidenza, altrimenti il nome copiato dalla 5b.
Da vuoto, la 6 segue il codice di oggi, riga per riga.

**Il testo sopra la cella:**

> ## 5b · La confidenza (facoltativa)
> **Cosa fa.** Prima di entrare guarda com'è andato il tuo sistema negli ultimi trade già chiusi nello stesso contesto
> di mercato: volatilità alta o bassa, trend a favore o contro. Se in quel contesto ha reso poco, il trade si salta.
>
> **Come leggere la tabella.** Ogni riga è una soglia: «entro solo se in questo contesto i trade passati hanno reso più
> di…». 0C vuol dire che hanno guadagnato al netto dei costi, 0.5C più di mezzo costo di un trade, 0.8C quasi un costo
> intero. Più alta la soglia, meno trade. La prima riga è il sistema senza soglia, solo sui trade che hanno già una
> confidenza. Si legge come la tabella della 5: conta quanto migliora e se regge sulle due metà. La seconda tabella
> confronta, per ogni contesto, quanto la confidenza prevedeva con quanto i trade hanno reso davvero.
>
> **Cosa scegliere.** Una soglia che supera le due prove, scritta alla 6. Se nessuna le supera, alla 6 lasci il campo
> vuoto. Le soglie sono fisse, le stesse per tutti: non si cambiano guardando la tabella.

### 3.3 · La 6 con una soglia scelta

- Il filtro scritto alla 6 deve essere quello della 5b, altrimenti si ferma e lo dice: la confidenza è costruita su
  quel setup.
- **Scheda:** in-sample dalla ricerca delle soglie, OOS con la stessa soglia sulle entry a confidenza nota.
- **Sotto la scheda, una volta sola:** `plot_oos_confidenza` (con e senza, due backtest separati) e la calibrazione OOS.
- **Diario:** una sola apertura, con la voce `confidenza` in più solo se c'è una soglia. I diari vecchi restano validi.
- **Schermate 7, 8, 9:** ricevono i trade con la confidenza, come `SISTEMA_FINALE = CONF_SCELTA` nella ricerca.

### 3.4 · Il conto delle prove

La voce è quella della 3.3: `(*chiave_filtri, ("confidenza", soglie, filtro))`, costruita da una funzione sola usata da
`conta_filtri` e dal Lab. Le chiavi già nello studio non cambiano.

- Stesso setup nel Lab e nella ricerca: conta una volta. Rifatta uguale: +0. Altro filtro: +3. Strada B e cella spenta: +0.
- Con più filtri in catena la 5b scrive anche la voce delle combinazioni, con la chiave che usa già la 6.

### 3.5 · Quattro punti del codice che vanno sistemati, o la cella darebbe numeri sbagliati

1. **Le soglie entrano nella ricerca dei filtri rifatta.** `_tutti_i_filtri` del Lab e la cella 59 della ricerca prendono
   tutti i filtri registrati e tolgono solo i `CELLA_`. Dopo la confidenza, rifare il passo 5 proverebbe anche i `CONF_`:
   asticella più alta, conto più alto. **Nella ricerca succede già oggi**, se si riesegue la 3.1 dopo la 3.3 senza
   riavviare. Tolgo i `CONF_` da tutti e due (decisione 6). Con un giro dall'alto in basso non cambia niente.
2. **La cache delle maschere.** Si ricorda i filtri per nome: un `CONF_BP_MEDI_0C` rifatto su un altro setup leggerebbe
   la maschera vecchia. Le ricerche con le soglie si fanno senza cache, come nella 3.3.
3. **Le schermate 8a e 8b.** `vetrina_verifica._filtri_del_lato` cerca i filtri in `s.fs.risultati`, dove le soglie non
   ci sono: si fermerebbe con un errore. Aggiungo le soglie scelte alla lista dei filtri da ricontrollare.
4. **Il trade a cavallo del confine.** Ha il segnale nell'in-sample ma l'esito dipende da barre dell'OOS. La 5b lo toglie
   dalla calibrazione, che così è davvero solo in-sample; la ricerca resta com'è. Differenza dichiarata: al massimo un
   trade per lato.

Inoltre: la 5b vale solo per la ricerca dei filtri da cui è nata. Se si rifà la 5 o si torna più indietro, va rifatta, e
la 6 lo dice. Con zero segnali a confidenza nota nell'in-sample, la cella lo dice e si ferma senza errori.

## §4 · Le domande dell'incarico

**1. Strada B: la confidenza si salta anche nel Lab?** **Sì, sempre**, non solo con una cella volatilità × trend. L'ha
già deciso Mattia il 22/10 (`66` §13, decisione 5) e la ricerca fa così: anche con una cella di sessione sarebbe una
seconda scelta di contesto sopra la prima.

**2. Le 3 soglie vanno bene anche nel Lab?** **Sì, le stesse.** Sono fissate dal listino e non dai dati (`02`: circa metà
e quasi tutto il costo di un trade). Valori diversi darebbero chiavi diverse, e Lab e ricerca non si parlerebbero più.
Un limite da sapere: il costo non dipende dal timeframe, mentre i movimenti tipici sì. Su H4 le stesse soglie sono più
vicine fra loro, rispetto al trade, che su M5. Non propongo di cambiarle.

**3. Il riscaldamento è troppo lungo?** Le **finestre** poco, anche con la regola del §2.3: su H4 sono 229 barre su almeno
8.000 di in-sample, meno del 3%; su D1 sono 169 su almeno 1.333, circa il 13%. A pesare è **`min_obs=30` per cella e per lato**: con quattro celle di peso simile (22–28% delle barre) servono circa
120 trade per lato prima che tutte siano note, a qualunque timeframe.

| trade all'anno, per lato | anni di riscaldamento |
|---|---|
| 200 | 0,6 |
| 100 | 1,2 |
| 50 | 2,4 |
| 32 | 3,75 |
| 20 | 6,0 |

L'in-sample va da 3,7 anni (Bybit SOL) a 5,5 (Binance BTC). Sotto i 32 trade all'anno il dataset più corto non si
riscalda del tutto. Sotto circa 65 (44 sul più lungo) il riscaldamento mangia tutta la prima metà, e la prova delle due
metà ha poco su cui lavorare. **È un limite di frequenza dei trade, più che di timeframe:** diventa probabile su D1 e
possibile su H4. **Proposta:** `min_obs` resta 30. La 5b scrive «confidenza nota: n trade su m, dal gg/mm/aaaa» e avvisa
se la data cade oltre la metà dell'in-sample o se i trade noti sono meno di 100, senza bloccare.

**4. Una prova con i trade del motore veloce?** **Sì.** Le prove 14 e 15 di `test_confidenza.py` girano già sul veloce,
perché è il predefinito, anche se il titolo della sezione dice `backtesting.py`. Il titolo si corregge. Manca quello che
il veloce ha di diverso:

- `motore="veloce"` scritto per esteso, con il taglio dello storico per il lookahead;
- con `comportamento_vecchio()` la confidenza dal veloce è identica al bit a quella da «bt»;
- un trade che esce sulla barra d'ingresso entra nella storia da quella barra, non prima;
- `CostoExtraPips` e il funding entrano nei netti, in pips e in bp.

## §5 · Collaudo e prove d'identità

**`test_confidenza.py`, sezioni nuove:**

- **Ore:** M15 identico al bit alla formula vecchia congelata, per celle, confidenza e filtri `CONF_`; la tabella del §1
  su serie M5, M30, H1, H4, D1; niente lookahead per taglio su M5 e H4.
- **Ancora:** la regola del §2.1 per ogni timeframe; fino a H1 identico al bit al `gap_trend` di oggi; su H4 si riparte al
  lunedì 00:00 UTC e su D1 il giorno 1 del mese, contro la regressione a ciclo di riferimento; il taglio per il
  lookahead; sul broker H4 e D1 non si rompono.
- **Veloce:** i quattro punti del §4.
- **Lab:** spenta = nessun backtest e nessuna voce; strada B = +0; rifatta = +0; niente date dell'OOS nelle tabelle e
  diario invariato alla 5b; rifare la 5 dopo la 5b prova gli stessi filtri con la stessa asticella; la 6 senza soglia è
  identica; la 6 con la soglia usa i trade giusti; 8a e 8b non si fermano; filtro diverso e soglia bocciata sono rifiutati.

**Altri test:** `test_atlante.py` (riferimento congelato; fino a H1 identico, H4 diverso per costruzione),
`test_conto_ricerca.py` (Lab e ricerca, stessa chiave), `test_giornata_utc.py` (l'ancora con la giornata UTC).

**Prove d'identità**, perché il lavoro tocca i calcoli:

| giro | cosa deve risultare |
|---|---|
| Lab e ricerca, BINANCE_PERP_BTCUSDT M15, a parità di barre, 5b spenta | identici al bit, 3.3 e 4.2 comprese; nessuna voce nuova |
| Giro completo, BYBIT_SPOT_ETHUSDT M15 | gira fino in fondo; identico al bit |
| H4 | nessun confronto: cambia per costruzione. Lo mostrano i test |

Le voci della confidenza nei giornali stanno solo su quattro dataset, tutti M15 (BTC, XRP, SOL Bybit, ETH Bybit spot): M5
non ne ha. Nessuna voce esistente cambia significato. Prima dei giri controllo che le chiavi siano già contate, altrimenti
il giro si fa sullo studio vero (`00`, «Le prove d'identità»).

**Il primo giro con la 5b accesa conta davvero.** Sono fino a 3 prove nello studio vero, e 1 apertura del diario se poi si
fa la 6. Propongo che lo lanci Mattia, quando vuole e sul setup che vuole (decisione 7). Io collaudo la cella accesa con i
test sui dati sintetici.

## §6 · Commit, su un ramo solo

1. Incarico e proposta (`80`, `81`), con le decisioni.
2. Lavori 1 e 2: `indicatori.py`, `confidenza.py`, test.
3. Lavoro 3: `vetrina.py`, `vetrina_verifica.py`, Lab (celle 5b e 6), ricerca (celle 59 e 72), test.
4. `00`, `02`, resoconto breve con cosa è cambiato su H4 e D1, e come lanciare la cella e cosa deve vedere Mattia.

Prima della Pull request: `python suite_rapida.py --tutte`, con «SUITE COMPLETA: n/n».

## §7 · Decisioni di Mattia

Esiti del 04/11/2026.

| # | decisione | proposta | esito |
|---|---|---|---|
| 1 | Su M30, H1, H4 la deviazione copre più di 5 ore, per il minimo di 20 barre | resta così, come l'atlante | ok |
| 2 | D1: la regola c'è, il Lab non lo apre in questo lavoro | sì | ok |
| 3 | Su H4 e D1 la mediana è più corta del periodo di ancora | resta così | **cambiata:** la mediana dei due assi copre il maggiore fra 125 ore e 5 periodi di ancora (§2.3); tabella rimisurata nel resoconto |
| 4 | Il filtro va scritto già alla 5b, e la 6 deve avere lo stesso | sì | ok |
| 5 | Una soglia che non supera le due prove, scritta alla 6 | rifiutata con un messaggio: è il caso «si va all'OOS senza» dell'incarico. Un filtro bocciato invece oggi passa | ok |
| 6 | Togliere i `CONF_` dai filtri da provare, Lab e cella 59 della ricerca | sì, corregge un difetto che c'è già | ok |
| 7 | Primo giro vero con la 5b accesa | lo lancia Mattia, io solo i test sintetici | ok |
| 8 | La cella 5b spenta di default | sì: non conta prove se non la vuoi | ok |
| 9 | Domande 1–4 dell'incarico | come al §4 | ok |
