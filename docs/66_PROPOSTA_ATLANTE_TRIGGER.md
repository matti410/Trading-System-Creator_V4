# 66 · Proposta: l'atlante del trigger (lavoro C)

Stato: **approvata da Mattia il 22/10/2026** (decisioni nel §13). Nessun codice
scritto. Le decisioni di partenza sono in `63` §6 e §10–10.3; qui si dice come
realizzarle. Unità: il bp decide, i pips accanto (`02`, «Unità»).

## Indice

- §0 · In breve
- §1 · Le decisioni già prese (da `63`)
- §2 · Le celle, senza guardare nel futuro
- §3 · La misura in ogni cella
- §4 · Dove si inserisce: Lab e notebook di ricerca
- §5 · Il passo 5 nella strada B
- §6 · La soglia cumulata
- §7 · I costi di calcolo
- §8 · I test a risultato noto
- §9 · Firme (nomi indicativi) e ordine dei commit
- §10 · Da fare nello stesso ramo: la confidenza nella soglia cumulata
- §11 · Rischi
- §12 · Domande per Mattia
- §13 · Decisioni di Mattia (22/10/2026)

---

## 0 · In breve

L'atlante prende **tutte le entry vere** del catalogo (oggi 70 misurabili su
BINANCE_PERP_BTCUSDT, 36 long e 35 short registrate). Per ognuna guarda
**dove** il trigger sembra funzionare, in 10 celle per lato sui perpetual e 8
sugli spot:
- 4 di volatilità × trend;
- 4 di sessione;
- 2 di basis, solo sui perpetual.

Una cella **passa** se il trigger batte il mercato della stessa cella (lordo,
in bp) e paga i costi (netto > 0). Mattia può sceglierne **una per lato**. La
cella scelta non diventa un cancello nuovo: al passo 5 si misura come un
filtro qualsiasi (tenuti contro scartati, due metà). L'asticella però tiene
conto di **tutte le celle che l'atlante ha guardato**: con circa 700 celle la
soglia è circa 3,97. Senza una cella scelta (strada A) tutto resta identico a
oggi.

## 1 · Le decisioni già prese (da `63`)

| tema | decisione | dove |
|---|---|---|
| su quali trigger | tutte le entry vere (niente metro, composite, orarie), in-sample, all'H già scelto | §6.1, domanda 15 |
| celle | 2 × 2 volatilità × trend (come `confidenza.py`) + 4 sessioni, assi **non** incrociati fra loro; sui perpetual + basis alta/bassa | §6.2, §6.3, domande 7, 12 |
| durate | finestre in ore, non in barre, con almeno 20 rendimenti; su M15 = 20 e 500 barre | §6.2, §10.1 punto 2 |
| sessioni | ASIA_NOTTE, EUROPA, LONDRA_NY, AMERICA, in ora locale con l'ora legale, anche sulle crypto | §6.2, domande 9, 10 |
| giornata crypto | 00:00 UTC (per `gap_trend`) | §10.1 punto 3, fatta (#39) |
| misura | due colonne: scarto lordo dal mercato della cella (decide t, BH, due metà) e guadagno netto > 0 | §6.4, §10.1 punto 4 |
| minimo | 200 eventi per cella | §6.2 |
| scelta | al massimo una cella per lato | §6.5, domanda 13 |
| convivenza | C4: l'atlante propone, il passo 5 misura la cella come filtro, con k = celle misurate dall'atlante | §6.5, §10.1 punto 1 |
| confidenza | nella strada B non si costruisce sulla stessa griglia | §6.5 |
| mercato nullo | sospeso: al suo posto la soglia cumulata | §10.3 |

## 2 · Le celle, senza guardare nel futuro

**La regola generale.** Il segnale è sulla barra i e l'ingresso è all'Open
della barra i+1. Ogni stato della barra i usa solo dati fino al Close della
barra i. Le mediane mobili comprendono la barra i e le precedenti, mai le
successive. Dove uno stato non si può ancora calcolare (inizio dello storico,
spot mancante), la cella è NaN e l'evento esce **solo da quell'asse**. Il
collaudo (§8) lo verifica per troncamento: si tagliano i dati alla barra i e
gli stati fino a i non devono cambiare.

### 2.1 · Volatilità × trend (4 celle per lato)

- **Volatilità alta / bassa:** deviazione dei rendimenti Close su Close
  nelle ultime 5 ore, confrontata con la sua mediana mobile delle ultime
  125 ore. Sopra la mediana è «alta», uguale o sotto è «bassa». Le 125 ore
  (circa 5,2 giorni) sono le 500 barre di M15: così su M15 la serie è
  identica, bit per bit, a `asse_volatilita(df, 20, 500)` di `confidenza.py`.
- **Trend a favore / contro:** `gap_trend` (la regressione della giornata
  meno il VWAP della giornata, giornata da 00:00 UTC), moltiplicato per il
  verso del trade. Sopra la sua mediana mobile delle ultime 125 ore è «a
  favore». Resta la nota di onestà di `63` §6.2: «a favore» vuol dire «nella
  metà alta degli ultimi giorni», non «il prezzo sta salendo». È calcolabile
  al Close di i perché la giornata si cumula fino a i.
- **Durate convertite in barre, con almeno 20 rendimenti:**

| timeframe | deviazione (5 ore) | mediana (125 ore) |
|---|---|---|
| M5 | 60 | 1.500 |
| M15 | 20 | 500 |
| M30 | 10 → **20** | 250 |
| H1 | 5 → **20** | 125 |
| H4 | 1,25 → **20** | 31 |

  `asse_volatilita` accetta solo 5, 20, 50 o 200 barre, perché è il file di
  Mattia, che non si tocca. Su M5 ne servono 60: la deviazione si calcola con
  la stessa formula in `engine/indicatori.py` (`volatilita_durata`). Il test
  ne verifica l'identità su M15.

### 2.2 · Sessione (4 celle, uguali per i due lati)

- Partizione costruita con `sessioni.in_sessione` (LONDRA e NEW_YORK, ora
  locale con l'ora legale): EUROPA = Londra sì, New York no; LONDRA_NY =
  tutte e due; AMERICA = New York sì, Londra no; ASIA_NOTTE = nessuna delle
  due.
- **L'ora è quella della barra in cui si apre il trade (i+1)**, come le
  condizioni orarie dal 19/10 (`02`). Non è uno sguardo nel futuro: l'orario
  della barra i+1 si conosce dal calendario (inizio della barra i più la
  durata di una barra), anche se quella barra mancasse nei dati.
- **Fine settimana:** `in_sessione` vale solo nei giorni feriali locali,
  quindi sulle crypto sabato e domenica finiscono **tutti in ASIA_NOTTE**. È
  quello che dice la definizione già decisa («Londra e New York chiuse»), ma
  rende la cella mista: notte asiatica più fine settimana. Domanda 1.

### 2.3 · Basis (2 celle, solo perpetual)

- `indicatori.basis_bp` (esiste dal lavoro B): (Close del perpetual − Close
  dello spot) ÷ Close dello spot × 10.000, sulla stessa barra. È alta o bassa
  rispetto alla sua mediana mobile delle ultime 125 ore. È nota al Close di i.
- **Serve lo spot.** Oggi il Lab non lo carica: la colonna `spot_close` si
  aggiunge con `exchange.colonne_perpetual`, che esiste ma non è usata da
  `vetrina.py`. Proposta: sui perpetual, `carica_storico` aggancia lo spot
  dello stesso exchange (es. BINANCE_SPOT_BTCUSDT) dopo gli indicatori.
  - Se il file dello spot manca, l'asse della basis non c'è e il Lab lo
    scrive, senza fermarsi.
  - Le barre senza spot (spot Bybit dal 2021, buchi dello spot Binance)
    sono NaN solo su questo asse.
  - Una colonna in più non deve cambiare nessun numero: lo verifica la prova
    di identità (§8, test 12).

## 3 · La misura in ogni cella

Per ogni entry e ogni cella misurabile, con la convenzione dell'event study
(segnale i, ingresso Open[i+1], misura al Close[i+H], quarantena applicata):

1. **Scarto lordo dal mercato della cella, in bp.** Il riferimento è il
   mercato della **stessa cella e della stessa fascia oraria**. Si usa
   `stagionalita.scarto_orario` di oggi con i codici «fascia × cella» al
   posto di «fascia». L'incertezza comprende quindi già le barre vicine
   (sovrapposizioni a H barre) e il rumore del riferimento. Da qui escono t e
   p a una coda.
   - Sull'asse delle sessioni la fascia oraria sta già dentro la sessione:
     lo scarto è quello della rosa, ristretto agli eventi della sessione.
2. **Guadagno netto del trigger nella cella, in bp.** È il rendimento a H
   barre meno i costi, convertiti al prezzo d'ingresso di ogni evento come
   per i trade:
   - commissione di listino andata e ritorno;
   - spread di un passo;
   - sui perpetual, il funding di ogni evento (`exchange.funding_avanti`,
     che esiste: conta le liquidazioni fra l'ingresso e la misura, col
     segno del lato).
3. **Una cella passa** se ha:
   - almeno 200 eventi;
   - t > 0;
   - il controllo della quota di falsi positivi (Benjamini–Hochberg,
     q = 20%, `rosa.benjamini_hochberg`) su **tutte** le celle misurate;
   - scarto positivo in **tutte e due le metà** dell'in-sample;
   - **guadagno netto > 0**.

   Una cella con meno di 200 eventi è grigia («troppo pochi casi») e non
   entra nel conto delle celle misurate (domanda 4).

Il conto delle celle misurate, **k_atlante**, è il numero che serve al passo
5 (§5) e alla soglia cumulata (§6).

## 4 · Dove si inserisce: Lab e notebook di ricerca

### 4.1 · Lab (`Trading_System_Lab_Crypto.ipynb`, tutto in `vetrina.py`)

| schermata | oggi | con l'atlante |
|---|---|---|
| 3a · rosa dei trigger | invariata | invariata |
| 3b · `scegli_trigger` | invariata | invariata; se si rifà, la cella scelta si azzera |
| **3c · `atlante_dei_trigger(s)`** | — | **nuova, facoltativa**: per i trigger scelti, la mappa delle celle; sotto, la tabella di tutte le entry con almeno una cella che passa |
| **3d · `scegli_cella(s, long=None, short=None)`** | — | **nuova, facoltativa**: al massimo una cella per lato, solo fra quelle che passano per il trigger scelto (altrimenti si ferma e dice perché) |
| 4 · uscite, 4b · rosa dei sistemi | invariate | invariate: le uscite si costruiscono sul trigger da solo (con C4 la cella è un filtro, non fa parte dell'ingresso) |
| 5 · `trova_strategia` | tutti i filtri | **strada B** se c'è una cella scelta: prova solo i filtri della cella (§5); strada A altrimenti, come oggi |
| 6 · scheda | invariata | il filtro si chiama come la cella; sotto, la soglia cumulata con le celle (§6) |

- Rispetto alle firme indicative di `63` §6.6 c'è una differenza: la cella
  si sceglie con una funzione a parte (`scegli_cella`) invece che con due
  parametri in più di `scegli_trigger`. Così `scegli_trigger` resta com'è.
- Se l'atlante mostra una cella interessante su un altro trigger, si torna
  alla 3b e si sceglie quel trigger: una scelta fatta guardando l'atlante,
  già contata nelle sue k celle.
- La mappa è a colori:
  - righe = le celle;
  - colore = solidità (t) dello scarto lordo;
  - accanto, lo scarto e il guadagno netto in bp, con i pips a fianco;
  - le celle che non passano sono grigie, con il motivo: «troppo pochi
    casi», «non supera la quota di falsi positivi», «non positiva in una
    metà», «non paga i costi».

  C'è anche il riquadro «Come leggerlo» di `63` §6.7.

### 4.2 · Notebook di ricerca (`Trading_Grid_Search_v4_backtesting.ipynb`)

- **Sezione nuova «1.3 ter · Atlante del trigger»**, dopo la rosa delle
  entry, con tre celle:
  - il calcolo: `atl = atlante(df_is, H, ...)`, con gli stessi parametri del
    Lab tramite una funzione comune in `vetrina.py`;
  - la mappa per i trigger scelti;
  - le costanti `CELLA_SCELTA_LONG = None` e `CELLA_SCELTA_SHORT = None`.
    Con None si va per la strada A e tutto resta come oggi.
- **Alla cella della ricerca dei filtri**, con una cella scelta, i filtri da
  provare sono solo quelli della cella e la soglia usa `k = k_atlante` (§5).
- **Alla riga della soglia cumulata**, si passa anche `atlante=atl` (§6) e
  `fs=[fs, fs_conf]` (§10).
- I due notebook restano allineati perché il conto sta tutto in `vetrina.py`
  e in `engine/atlante.py`.

## 5 · Il passo 5 nella strada B

- **I filtri della cella** si registrano **su richiesta**, non nel
  dizionario `FILTRI`, quindi il catalogo e i suoi 129 nomi non cambiano.
  Nomi: `CELLA_VT_<VOL>_<TREND>_L/_S`, `CELLA_SESS_<NOME>`,
  `CELLA_BASIS_<ALTA|BASSA>`. Seguono le regole del passo 5:
  - sessione e basis sono neutre (`direction=0`: dicono quando, non in che
    verso);
  - volatilità × trend è direzionale (contiene il trend nel verso del
    trade), con il suo `pair` long/short;
  - nessuna è sempre vera o sempre falsa: passano `verifica_lookahead` e
    `verifica_degenerazione`.
- **La soglia di rumore.** `run_filter_search_bt` riceve un parametro nuovo,
  `k_prove=None`, additivo. Con None si comporta come oggi (k = righe
  provate). Nella strada B vale k_atlante: con circa 700 celle la soglia è
  circa 3,97 invece dei 2,24 di 2 righe. La ricerca dei filtri lo ricorda in
  un attributo, `rimisura=True`, che serve alla soglia cumulata (§6).
- **Due metà:** come oggi (`due_meta`).
- **Confidenza:** nella strada B non si costruisce sulla griglia volatilità ×
  trend (`63` §6.5). Il Lab e il notebook la saltano con una frase che dice
  perché (domanda 5).
- **Filtri del catalogo sopra la cella:** non nella prima versione. Se un
  giorno si vorranno, si conteranno come prove in più (`63` §6.5, C4).

## 6 · La soglia cumulata

Oggi la soglia conta trigger, uscite, filtri e combinazioni
(`vetrina._soglia_da_conti`). Con l'atlante si aggiunge una voce:

- **«N celle dell'atlante (schermata 3c)»**, con N = k_atlante. Si somma ai
  trigger della rosa (prudente: sono due sguardi diversi sugli stessi dati,
  domanda 4).
- **La ricerca dei filtri della strada B non si aggiunge**, perché è la
  seconda misura delle celle già contate (`63` §10.1 punto 1). Il Lab non la
  conta; nel notebook `soglia_cumulata` salta ogni ricerca con
  `rimisura=True`.
- **Stesse regole del lavoro 4.** Rifare l'atlante con le stesse
  impostazioni non conta due volte. Rifarlo con impostazioni diverse (un
  altro H, altri assi) si somma. Con un symbol, un timeframe o un H nuovi
  (schermata 1) il conto riparte da zero.
- Esempio indicativo su BINANCE_PERP_BTCUSDT: 70 trigger + 700 celle + 3
  sistemi delle uscite = 773 prove, soglia 3,99. Senza atlante sarebbero 73
  prove e 3,39.
- Nel notebook: `soglia_cumulata(ev=..., es=..., fs=[fs, fs_conf],
  atlante=atl, t=...)`, con il nuovo parametro `atlante=None`.

## 7 · I costi di calcolo

**Misure di oggi** su BINANCE_PERP_BTCUSDT M15, in-sample di 190.420 barre,
su questo PC:

| passo | tempo |
|---|---|
| `prepara` | 14,1 s |
| `esplora` | 4,7 s |
| `rosa_dei_trigger` (70 entry, bp più pips e ATR accanto) | 16,8 s |
| stati volatilità × trend, due lati (`cella_contesto`) | 1,05 s |
| quattro sessioni (`in_sessione`) | 0,23 s |
| basis e la sua mediana | 0,01 s |
| una chiamata a `scarto_orario` | 27 ms |

**Il conto ingenuo** è 70 entry × 10 celle × 3 misure (in-sample intero e
due metà) × 27 ms, cioè circa 57 s, più le unità accanto. È troppo per una
schermata.

**Come si resta veloci** (obiettivo: **atlante intero sotto 20 s** su BTC
M15, circa quanto la rosa):
1. **Gli stati si calcolano una volta per sessione** e si tengono in cache,
   come oggi le maschere dei filtri. Non si ricalcolano per ogni entry.
2. **Un passaggio per asse, non uno per cella.** Con i codici «fascia ×
   cella» i pesi di una cella sono diversi da zero solo sulle barre di
   quella cella. Le celle di un asse si dividono le barre, quindi le 4 celle
   di un asse costano circa quanto una misura sulle barre intere. Per ogni
   entry: 3 assi invece di 10 celle.
3. **Il mercato di riferimento** (media per fascia × cella) non dipende
   dall'entry: si calcola una volta per asse e per metà.
4. **Solo il bp decide.** Pips e ATR accanto si calcolano solo per i
   trigger mostrati nella mappa, non per tutte le 700 celle (domanda 6).
5. **Se non basta**, l'errore standard con le sovrapposizioni si passa a
   numba, che è già nel progetto e bloccato a 0.68.0.

- Il collaudo misura e riporta i tempi.
- Un test sul tempo non c'è, perché darebbe esiti diversi da un PC
  all'altro. Se l'obiettivo non si raggiunge, ci si ferma e si dice.
- Su M5 le barre sono il triplo, quindi il tempo cresce circa 3 volte.
- Il passo 5 della strada B prova 2 filtri invece di circa 40: è più veloce
  di oggi.

## 8 · I test a risultato noto

Una suite nuova, `test_atlante.py`, più delle sezioni in `test_vetrina.py` e
`test_filter_search*.py`. Nessun test esistente si allenta.

| # | caso | risultato atteso |
|---|---|---|
| 1 | mercato finto, vantaggio messo solo in volatilità alta; il trigger è piatto in media | passano solo le 2 celle a volatilità alta; sessioni e basis no |
| 2 | deriva solo in una sessione, trigger senza vantaggio | con il riferimento di cella lo scarto è circa 0 e la cella non passa; con il riferimento globale sarebbe positivo (lo si mostra) |
| 3 | vantaggio solo in EUROPA | passa solo EUROPA |
| 4 | vantaggio lordo positivo ma più piccolo del costo andata e ritorno | la cella non passa: «non paga i costi» |
| 5 | perpetual finto, long con vantaggio lordo ma funding alto in basis alta | basis alta non passa per il funding, il lordo resta positivo |
| 6 | 60 entry casuali senza vantaggio × 8 celle, 20 semi | celle che passano: in media non oltre q delle promosse; il numero si riporta |
| 7 | un conto fatto a mano (media, t) su una cella di 300 eventi | uguale all'uscita dell'atlante |
| 8 | lookahead per troncamento su tutti gli stati (volatilità, trend per lato, sessione, basis) e sui filtri `CELLA_…` | stessi valori fino al taglio; `verifica_lookahead` e `verifica_degenerazione` passano |
| 9 | identità su M15 | `volatilita_durata` = `asse_volatilita(20, 500)` bit per bit; cella volatilità × trend = `cella_contesto` |
| 10 | finestre su H4, M30, M5 | 20 rendimenti minimi su H4 e M30, 60 / 1.500 su M5 |
| 11 | sessioni | ogni barra in esattamente una cella; i giorni di marzo e ottobre con l'ora legale sfasata fra Londra e New York; sabato = ASIA_NOTTE (o la quinta cella, domanda 1) |
| 12 | basis | NaN dove manca lo spot, l'evento esce solo da quell'asse; sugli spot 8 celle, niente basis; con la colonna `spot_close` in più i numeri della strada A non cambiano |
| 13 | minimo 200 eventi | una cella con 199 eventi è grigia e non entra in k_atlante |
| 14 | passo 5 strada B | soglia = `soglia_rumore(k_atlante)`, non quella delle righe; con `k_prove=None` è identico a oggi |
| 15 | soglia cumulata | le celle si contano, una volta sola se si rifà uguale; la ricerca con `rimisura=True` non si conta; `fs=[fs, fs_conf]` conta tutte e due |
| 16 | una cella per lato | una seconda cella sullo stesso lato o una cella che non passa: errore con la spiegazione |
| 17 | notebook | strada A identica bit per bit a oggi nei due notebook vivi su BINANCE_PERP_BTCUSDT; giro completo strada B su BINANCE_PERP_BTCUSDT e su BYBIT_SPOT_ETHUSDT (solo long, senza basis) |

Prima della Pull request: `python suite_rapida.py --tutte`, con la suite
nuova (38/38).

## 9 · Firme (nomi indicativi) e ordine dei commit

```python
# engine/indicatori.py  (additivo)
volatilita_durata(df, ore=5, ore_mediana=125, minimo=20) -> pd.Series   # su M15 = asse_volatilita(df, 20, 500)
sessione_principale(df, all_ingresso=True) -> pd.Series                 # ASIA_NOTTE / EUROPA / LONDRA_NY / AMERICA

# engine/atlante.py  (nuovo)
celle_atlante(df, direzione, assi=("vol_trend", "sessione", "basis")) -> pd.DataFrame
        # una colonna di codici per asse; NaN dove lo stato non si calcola
atlante(df_is, H, pip, costi, funding=None, nomi=None, assi=..., unita="bp",
        min_eventi=200, q=0.20, fuso=..., mostra=None) -> pd.DataFrame
        # una riga per entry × cella: eventi, scarto_bp, t, p, bh, due_meta,
        # netto_bp, passa, motivo; attributo k_misurate
registra_filtri_cella(celle) -> list[str]        # i filtri CELLA_… su richiesta

# engine/filter_search_bt.py  (additivo)
run_filter_search_bt(..., k_prove=None)          # None = come oggi

# engine/vetrina.py
atlante_dei_trigger(s)          # schermata 3c
scegli_cella(s, long=None, short=None)   # schermata 3d
soglia_cumulata(..., atlante=None)       # parametro in più
```

Un ramo (`atlante-trigger`), commit in quest'ordine, con le suite dopo
ognuno:
1. gli stati in `indicatori.py`, con i test 8–12;
2. `engine/atlante.py`, con i test 1–7 e 13;
3. `k_prove` e `rimisura` nella ricerca dei filtri (test 14);
4. il Lab: schermate 3c e 3d, la strada B al passo 5, la soglia cumulata e
   lo spot agganciato sui perpetual (test 15–16);
5. il notebook di ricerca, compreso il punto del §10;
6. i documenti: `02` («Unità» e una sezione «L'atlante»), `00`,
   `00_ARCHIVIO`.

Prove di identità complete (§8, test 17), perché si tocca il calcolo.

## 10 · Da fare nello stesso ramo: la confidenza nella soglia cumulata

**Annotazione richiesta da Mattia (22/10/2026).** Nel notebook di ricerca la
riga della soglia cumulata conta solo la ricerca dei filtri `fs`. Le soglie
della confidenza sono anche loro filtri provati sullo stesso in-sample
(ricerca `fs_conf`). Quindi la riga diventa `soglia_cumulata(ev=ev,
es=[es_trigger, es], fs=[fs, fs_conf], t=...)`.
- `soglia_cumulata` accetta già una lista e conta una volta sola lo stesso
  oggetto passato due volte (lavoro 4): non serve codice nuovo in `vetrina.py`.
- Se la cella della confidenza non è stata eseguita, `fs_conf` non esiste:
  la riga deve funzionare lo stesso, contando solo `fs`.
- Test: la sezione S di `test_vetrina.py` con due ricerche diverse.

## 11 · Rischi

- **Poca potenza.** Con circa 700 celle la soglia del passo 5 è circa 3,97:
  un vantaggio di cella piccolo non si vedrà. È il prezzo di guardare 700
  posti. Il mercato nullo, che misurerebbe quanto la stima è prudente, è
  sospeso (`63` §10.3). La difesa indipendente resta l'out-of-sample aperto
  una volta sola.
- **La tentazione di guardare tante mappe.** Rifare l'atlante con
  impostazioni diverse si somma nella soglia cumulata: lo si vede scritto.
- **Lo spot nel perpetual.** Agganciare lo spot è l'unica modifica che tocca
  i dati di tutti i perpetual. La prova di identità della strada A lo
  controlla.
- **Complessità.** Due schermate, un modulo e un parametro nuovi. Con la
  strada A tutto resta come oggi.

## 12 · Domande per Mattia

| # | domanda | proposta |
|---|---|---|
| 1 | Sulle crypto il fine settimana finisce tutto in ASIA_NOTTE (Londra e New York chiuse). Va bene così, o una quinta cella FINE_SETTIMANA? | **Così**, con il nome «ASIA_NOTTE (e fine settimana)»: è la definizione già decisa, e una cella in più è una prova in più. La quinta cella si può decidere adesso, prima di guardare, se pensi che il fine settimana sia un mercato a parte. |
| 2 | La cella di sessione si legge sulla barra in cui si apre il trade (i+1), come le condizioni orarie. Confermi? | **Sì.** |
| 3 | La cella si sceglie con `scegli_cella` (schermata 3d), solo fra quelle che passano per il trigger già scelto. Il Lab non propone una cella di default. Va bene? | **Sì.** Se passano più celle, sceglie Mattia: è una scelta guardando l'atlante, già contata nelle k celle. |
| 4 | Nella soglia cumulata si sommano i trigger della rosa (70) e le celle dell'atlante (circa 700); le celle sotto i 200 eventi non si contano. Va bene? | **Sì**: è il conto prudente, coerente con «tratta le prove come indipendenti». |
| 5 | Confidenza nella strada B: si salta sempre, o solo quando la cella scelta è di volatilità × trend? | **Sempre**: con una cella di sessione o di basis, la griglia volatilità × trend sarebbe un'altra scelta di contesto sopra la prima. |
| 6 | Pips e ATR accanto al bp solo per i trigger mostrati nella mappa, non per tutte le celle? | **Sì**: decide il bp, e così l'atlante resta veloce. |
| 7 | Lo spot si aggancia ai perpetual sempre (in `carica_storico`), o solo quando si apre l'atlante? | **Sempre**, dopo gli indicatori: un solo modo di caricare i dati, controllato dalla prova di identità. |

## 13 · Decisioni di Mattia (22/10/2026)

Proposta approvata. Risposte alle domande del §12:

| # | decisione |
|---|---|
| 1 | Il fine settimana resta dentro ASIA_NOTTE, con il nome «ASIA_NOTTE (e fine settimana)». Niente quinta cella. |
| 2 | Sì: la sessione si legge sulla barra d'ingresso (i+1). |
| 3 | Sì: `scegli_cella` solo fra le celle che passano, senza una cella di default. |
| 4 | Sì: nella soglia cumulata si sommano trigger e celle; le celle sotto i 200 eventi non si contano. |
| 5 | Sì: nella strada B la confidenza si salta sempre. |
| 6 | Sì: pips e ATR solo per i trigger mostrati. |
| 7 | Sì: lo spot si aggancia sempre ai perpetual; la prova di identità della strada A deve restare identica al bit. |

Codice sul ramo `atlante-trigger` (che comprende il commit di questa
proposta), commit nell'ordine del §9 con le suite dopo ognuno. Obiettivo di
tempo: atlante sotto i 20 s su BTC M15; se non si raggiunge, ci si ferma e
lo si dice. Prove di identità complete. Prima della Pull request: `python
suite_rapida.py --tutte` (38/38).
