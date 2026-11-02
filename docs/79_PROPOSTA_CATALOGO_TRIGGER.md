# 79 · Proposta: catalogo dei trigger intraday più grande

**Data:** 02/11/2026. **Incarico:** `78`. **Stato:** approvata il 02/11/2026 (decisioni in §5); codice sul ramo `catalogo-trigger-intraday`. Fonti lette per
intero il 02/11/2026 (Claude in Chrome con il login di Mattia; il paper in PDF). Conteggi con uno script usa e getta
fuori dal repo, in sola lettura, sull'in-sample dello studio (confine 15/06/2025 17:30 UTC): BINANCE_PERP_BTCUSDT M15
(5,45 anni) e BYBIT_SPOT_ETHUSDT M15 (3,95 anni, solo long). Nessun rendimento guardato, niente scritto nello studio.

**Indice:** §1 Le schede · §2 Tabella · §3 Codice e collaudo · §4 Conto e ML · §5 Decisioni

## §1 · Le schede (modello di `50` §3, in breve)

Comune a tutte: entry long e short separate, evento con `_evento`, ingresso all'Open dopo (motore), parametri della
fonte senza varianti, nessun buffer. Le percentuali sono la quota di eventi che cade sull'altra condizione (±2 barre,
come `famiglie.py`), con il lift: conto preliminare, il controllo vero è dopo il codice (§3). Occorrenze: media per
anno nell'in-sample, BTC long / BTC short / ETH long.

**Idea 1 · Rottura del canale di 24 ore con impulso** (rotture). PyQuantLab, «Impulse Breakout Trading Strategy»,
Medium, 24/9/2025 (Member-only), BTC/USDC 15 minuti. *Long:* la chiusura supera il massimo dei massimi delle 24 ore
prima (barra corrente esclusa) **e** il rendimento degli ultimi 45 minuti è sopra il proprio 60° percentile sulle
24 ore. *Short:* chiusura sotto il minimo delle 24 ore prima e rendimento sotto il 40° percentile. Setup composto:
una prova per lato. *Traduzioni:* 3 barre da 15 minuti → 45 minuti (sì); vale su M5 e M15, non su M30 e H1 (45
minuti non sono un numero intero di barre). Il percentile nella fonte include la barra corrente: resta così.
*Occorrenze:* 390 / 312 / 422. *Più vicina:* l'85–89% degli eventi di **E23** cade dentro l'idea 1 (lift 16–20),
il 37% dell'idea 1 dentro E23; E40 per il 67–75% dentro l'idea 1. Non è un doppione per la regola (è la vecchia a
stare nella nuova), ma con somiglianza 85% cade nella **famiglia di E23**: va motivata (D4). *Lookahead:* nessuno
(livello spostato di una barra). *Scarti:* uscita a 3 ore e uscita sulla volatilità che si contrae (sono uscite,
non trigger); la percentuale di «colpi» a 3 ore.
*Decorrelazione* (`famiglie.py`, in-sample dello studio, 02/11/2026): famiglia di E23 (con E21); più vicina E23, 84,8% long e 85,8% short; motivo: E23 sta quasi tutta nell'idea 1, ma circa il 63% degli eventi dell'idea 1 non cade su E23 (canale mobile di 24 ore + impulso).

**Idea 2 · Compressione e rottura del canale** (rotture). PyQuantLab, «An Intraday Volatility Breakout Strategy»,
Medium, 25/5/2025, SOL 5 minuti. *Long:* sulla barra prima l'ATR (70 minuti) era sotto 0,8 × la sua media
dell'ultima ora; la chiusura supera il massimo dei massimi delle 3 ore fino alla barra prima. *Short:* lo speculare
sul minimo (della fonte). *Traduzioni* (sì): ATR 14 → 70 minuti, media 12 → 60 minuti, canale 36 → 3 ore; su M15
l'ATR si arrotonda a 5 barre (75 minuti), media 4, canale 12; la rottura della fonte è sul massimo dentro la barra,
qui sulla chiusura. Vale su M5 e M15, non su H1 (un ATR di una barra non si comprime). *Occorrenze:* 84 / 61 / 95.
*Più vicina:* E29 23–25% (lift 2,5–2,9). *Lookahead:* compressione e canale della barra prima. *Scarti:* stop mobile
ad ATR, ingresso al livello.
*Decorrelazione* (`famiglie.py`, in-sample dello studio, 02/11/2026): più vicina E21 al 62% (61,8% long, 61,3% short); con il legame medio non entra nella famiglia E21/E23/E46: famiglia nuova.

**Idea 3 · Rottura di massimi uguali** (rotture). F. Ridder, «I Backtested S&R Breakouts in Python», Coinmonks,
25/11/2023, ETH/USD 5 minuti (regola del canale YouTube CodeTrading). *Alla lettura:* i massimi locali sono sulle
**chiusure** (non sui massimi), con 3 barre per lato e confronto stretto; la finestra è 100 barre nella chiamata
della strategia del video (80 è il valore predefinito della funzione; con 3 barre per lato i conteggi sono
identici). *Long:* gli ultimi 3 massimi locali confermati (3 barre dopo) nella finestra stanno entro lo 0,2% e la
chiusura è ≥ la loro media × 1,001. *Short:* lo speculare sui minimi (della fonte). *Traduzioni* (D1): (a) **in
ore**, regola 3 di `78`: 15 minuti per lato, finestra 500 minuti → su M15 il massimo locale ha **1 barra per lato**
e la finestra 33 barre (arrotondato), M5
come la fonte, M30 e H1 no; (b) in barre come la fonte (3 e 100), che porta lei stessa la regola dal giornaliero ai
5 minuti. Consiglio (a). *Occorrenze:* (a) 711 / 668 / 602; (b) 222 / 199 / 166. *Più vicina:* E22 11–18%, E23
7–12%. *Lookahead:* il pivot esiste dalla barra di conferma. *Scarti:* stop, target, pareggio, età massima; i
parametri ottimizzati su 432.000 combinazioni (600/120, 400/80).
*Decorrelazione* (`famiglie.py`, in-sample dello studio, 02/11/2026): famiglia nuova; più vicina E12, 57,5% long e 57,4% short.

**Idea 4 · Sweep & reclaim, la falsa rottura** (inversioni). R. Shu, «Algo Trading Series, Part 3: The Concept —
Hunting for Liquidity», CodeX, 7/1/2026, azioni, giornaliero. *Alla lettura:* il minimo centrato su 7 periodi è già
spostato di 3 nella fonte, quindi causale; si scrive direttamente in forma causale. La fonte scrive **solo il long**.
*Long:* il livello è l'**ultimo minimo locale confermato** (il più basso fra 3 ore prima e 3 ore dopo, noto 3 ore
dopo), tenuto finché non se ne conferma uno nuovo, anche se è già stato spazzato: come la fonte, che lo porta avanti
con `ffill`; nell'ultima ora il minimo è andato sotto quel livello e la chiusura è sopra. Un minimo non ancora
confermato non è un livello: uno sweep sotto di lui non scatta. *Short:* lo speculare sul massimo, **traduzione
nostra** (D5). *Traduzioni:* il giorno diventa la **candela oraria** (sì): 3 ore per lato, candela di un'ora
mobile; su H1 è la regola della fonte, su M5–M30 la stessa misurata più spesso. Motivo: è la scala dei trade da 1 a
8 ore e vale uguale su ogni timeframe. Il minimo dello sweep è della barra chiusa, noto alla chiusura: non serve
riscriverlo sulla chiusura.
*Occorrenze:* 721 / 702 / 659. *Più vicina:* nessuna nel catalogo (§5 di `78`). *Lookahead:* trappola del minimo
centrato senza spostamento. *Scarti:* la struttura (massimi e minimi crescenti) è nella teoria ma non nella regola
del codice: sarebbe un filtro, non si propone; la parte di IA.
*Decorrelazione* (`famiglie.py`, in-sample dello studio, 02/11/2026): famiglia nuova; più vicina E3, 40,0% long e 46,4% short.

**Idea 5 · Salto di volatilità, contro** (inversioni). A. Murtazin, «Intraday Volatility Jump Mean-Reversion
(Trading) Strategy for BTC-USD in Python», DEV Community. *Alla lettura:* la versione a 15 minuti (`…-d39`) è
stata **tolta dall'autore** e non è in archivio. Le tre versioni rimaste (10, 13 e 16/4/2026) hanno soglia 3 e
finestre diverse: 60 barre da 1 ora; 24 barre da 1 ora con la media tolta e la barra corrente esclusa; 60 barre da
1 minuto. *Regola proposta (quella del §5 di `78`):* rendimento logaritmico della barra diviso la deviazione
standard delle 60 barre da 15 minuti prima (15 ore); sotto −3 long, sopra +3 short (della fonte). *Traduzioni:*
finestra in ore (sì); il salto resta il rendimento di una barra. *Occorrenze:* 363 / 341 / 362. *Più vicina:* E45
40% (lift 2,9), E7 2% (conto preliminare). *Lookahead:* trappola della deviazione standard su tutto il campione.
*Scarti:* tenuta fino al segnale dopo o per N barre (uscita a tempo). **SPENTA** (02/11/2026): doppione di E3 dello
stesso lato (88,6–91,7%, lift ≥ 2,9 su tutti i dataset; a differenza di E31–E33 è la stessa scommessa). Le due righe
del dizionario sono commenti, come F27; la funzione e i test restano.
*Decorrelazione* (`famiglie.py`, in-sample dello studio, 02/11/2026): doppione di E3 dello stesso lato (sopra): spenta.

**Idea 6 · Movimento forte con volume in calo** (inversioni). A. K. Ghosh, «Quantitative Trading — Volume Reversal
Strategy», Medium, 25/9/2023 (Member-only), azioni, giornaliero. *Long:* il movimento delle ultime 5 ore, in valore
assoluto, supera la deviazione standard dei movimenti a 5 ore delle ultime 100 ore, è negativo, e il volume medio
delle ultime 5 ore è sotto quello delle 5 ore prima. *Short:* movimento positivo, il resto uguale. *Traduzioni:*
**tutta nostra**, periodo orario al posto del giorno (sì); il testo dice 5 giorni, il codice misura 4 periodi fino a
ieri: si segue il testo, alla chiusura della barra. *Occorrenze:* 346 / 453 / 363. *Più vicina:* E45 29–37%
(lift 2,4–2,7): famiglia diversa. *Lookahead:* nessuno. *Scarti:* uscita al 5° periodo o al segnale contrario.
È l'idea più debole: Mattia l'ha voluta (D3).
*Decorrelazione* (`famiglie.py`, in-sample dello studio, 02/11/2026): famiglia nuova; più vicina E3, 42,5% long e 51,6% short.

**Idea 7 · Area di rumore** (momentum). Zarattini, Aziz, Barbon, «Beat the Market…», SFI WP 24-97, versione
3/2/2025, SPY 1 minuto, 43 pagine. *Long:* a un controllo di mezz'ora (HH:00 o HH:30 UTC, dalle 00:30 alle 23:30)
la chiusura è sopra apertura della giornata × (1 + σ), dove σ è la media sui 14 giorni prima del movimento assoluto
dall'apertura alla stessa ora; al controllo prima della stessa giornata non lo era. *Short:* sotto apertura × (1 − σ).
Moltiplicatore 1, 14 giorni (parametri base del paper; 90 giorni e 1,5 sono i migliori col senno di poi, scartati).
*Traduzioni:* apertura alle 00:00 UTC e chiusura di ieri coincidono, la correzione per il gap sparisce (no);
controllo ogni mezz'ora come nel paper: vale su M5, M15 e M30, non su H1. *Occorrenze:* 496 / 485 / 496.
*Più vicina:* E40 35–36% dentro l'idea 7 (lift 5), E36 6%. *Lookahead:* σ solo dai giorni chiusi (trappola: σ con
il giorno corrente). *Scarti:* stop sulla banda e sul VWAP e chiusura a fine giornata (uscite), dimensione per
volatilità, VIX, gamma, schemi giornalieri, giorni della settimana.
*Decorrelazione* (`famiglie.py`, in-sample dello studio, 02/11/2026): famiglia nuova; più vicina E21, 56,0% long e 56,7% short.

**Coppie fra le idee nuove** (regola 8 di `78`): 1–7 37% (lift 5), 4–5 25% (lift 2,5); anche 1–2, 1–3, 2–3 sotto il
28%. Nessuna supera il 60%.

## §2 · Tabella riassuntiva

| # | famiglia | trigger (long / short) | prove | occorrenze per anno (BTC L / BTC S / ETH L) | più vicina |
|---|---|---|---|---|---|
| 1 | rotture | E46 / E46_SHORT, canale 24 h + impulso | 2 | 390 / 312 / 422 | E23 (85–89% di E23 dentro), E40 |
| 2 | rotture | E47 / E47_SHORT, compressione + canale 3 h | 2 | 84 / 61 / 95 | E29 (23–25%) |
| 3 | rotture | E48 / E48_SHORT, massimi uguali | 2 | (a) 711 / 668 / 602 · (b) 222 / 199 / 166 | E22 (≤18%) |
| 4 | inversioni | E49 / E49_SHORT, sweep & reclaim | 2 | 721 / 702 / 659 | nessuna |
| 5 | inversioni | E50 / E50_SHORT, salto contro: **spenta**, doppione di E3 | 0 | 363 / 341 / 362 | E3 (88,6–91,7%) |
| 6 | inversioni | E51 / E51_SHORT, movimento e volume | 2 | 346 / 453 / 363 | E45 (≤37%) |
| 7 | momentum | E52 / E52_SHORT, area di rumore | 2 | 496 / 485 / 496 | E40 (36%) |

Totale 12 prove sul perpetual, 6 sullo spot (l'idea 5 è spenta come doppione). Tutte sopra le ~100 occorrenze;
nessuna richiede il taker buy volume, quindi nessuna è in attesa per quel motivo.

## §3 · Codice previsto e collaudo (dopo il via)

- **Indicatori nuovi** in `engine/indicatori.py`, uno per idea, con le finestre in minuti convertite in barre dal
  timeframe (come `orizzonti_in_barre`); fuori dai timeframe ammessi la colonna è falsa e un avviso lo dice. Entry
  E46–E52 in `entry_long.py` ed `entry_short.py`, fonte nel docstring. Modifiche additive.
- **Collaudo `50` §7** in `test_trigger_intraday.py`: casi a risultato noto per ogni idea; `verifica_lookahead` con
  le trappole nuove (minimo centrato non spostato, deviazione standard su tutto il campione, σ con il giorno
  corrente); `verifica_degenerazione`; riscaldamento; stesso evento su M5 e M15 dove la regola lo promette; pandas
  2.2 e 3.0; `Collaudo_Catalogo.ipynb`.
- **Doppioni (`50` §7 punto 5).** `famiglie.py` non cambia: accetta già un dizionario di in-sample e i nomi.
  Proposta: solo sull'in-sample dello studio, i long su BINANCE_PERP_BTCUSDT, BYBIT_SPOT_ETHUSDT e
  BYBIT_PERP_SOLUSDT (M15), gli short sui due perpetual. Cambia solo il testo di `50` §7 punto 5. Usa solo i
  segnali: non è una prova (D6).

## §4 · Peso sul conto e ML

- **Conto.** +12 trigger sul perpetual, +6 sullo spot (E50 spento): BINANCE_PERP_BTCUSDT_M15 da 72 a 84;
  BYBIT_SPOT_ETHUSDT_M15 da 66 a 72. La voce dei trigger
  si moltiplica per gli H provati sul dataset (circa ×3 con la griglia di 1, 4 e 8 ore). Atlante con la regola (b):
  8 celle per trigger e per H, quindi +96 situazioni per H sul perpetual e +48 sullo spot. Tutto entra nel conto
  solo quando se ne vede il primo risultato (`77` §P8), e le prove d'identità con i trigger nuovi si fanno sullo
  studio vero.
- **ML.** Legge i dizionari di V4: nessuna modifica lì. Da controllare dal revisore: il riscaldamento del ML
  (2.100 barre) è più corto della finestra dell'idea 7 su M5 (15 giorni = 4.320 barre), come già per E40 (250
  giornate) ed E41 (300).

**Comandi, dopo il codice:** `python test_trigger_intraday.py` → ultima riga «RISULTATO: n/n test superati»;
`python suite_rapida.py` durante il lavoro; `python suite_rapida.py --tutte` prima della PR → «SUITE COMPLETA: n/n»;
`Collaudo_Catalogo.ipynb` → sezione B con 0 LOOKAHEAD e 0 ERRORE.

## §5 · Decisioni

**Decise (Mattia e il revisore, 02/11/2026; revisione senza bloccanti).** Sì a tutte e 7 le idee, E46–E52; poi l'idea 5 è spenta come doppione (§5).
- **D1** idea 3: finestre in ore, opzione (a); su M15 il massimo locale ha 1 barra per lato.
- **Idea 5 (E50): spenta**, doppione di E3 dello stesso lato (88,6–91,7%, lift ≥ 2,9 su tutti i dataset; a
  differenza di E31–E33 è la stessa scommessa). Le righe del dizionario sono commenti; D2 non serve più.
- **D3** idea 6: dentro.
- **D4** idea 1: dentro. DECORRELAZIONE: famiglia di E23; motivo: E23 sta quasi tutta nell'idea 1, ma circa il 63%
  degli eventi dell'idea 1 non cade su E23 (canale mobile di 24 ore + impulso).
- **D5** idea 4: short dentro, segnato «traduzione nostra»; il livello è l'ultimo minimo (massimo) confermato,
  tenuto fino al successivo, come nella fonte.
- **D6** sì: `famiglie.py` sull'in-sample dei tre dataset crypto del §3.
- Idea 7: evento a ogni controllo in cui la chiusura esce dall'area di rumore (non solo il primo della giornata).

## §6 · Resoconto del codice (*resoconto*, 02/11/2026)

- **File:** `engine/indicatori.py` (sette funzioni in coda, fuori da `aggiungi_indicatori`: le colonne del catalogo
  non cambiano), `entry_long.py`, `entry_short.py` (E46–E52; E50 tra commenti), `test_trigger_intraday.py` (nuovo),
  `test_vetrina_trigger.py` (i 12 trigger nuovi fra quelli con solo nome e candela nella lente, come E45),
  `suite_rapida.py` (durata del test nuovo). Modifiche additive.
- **Convenzione dell'indice:** l'indice è l'INIZIO della barra; il controllo delle HH:30 dell'idea 7 è la barra che
  finisce alle HH:30 (su M15 l'indice HH:15).
- **Collaudo:** `test_trigger_intraday.py` 38/38 (pandas 3.0.6): casi a risultato noto per ogni idea, ricalcolo a
  mano barra per barra, eventi, quattro trappole viste come LOOKAHEAD, lookahead OK e degenerazione OK sui 14,
  riscaldamento, timeframe. Idea 7: stessi eventi su M5 e M15; idee 1, 2, 3: stessa ora su M5 e M15 nei casi
  costruiti (sui dati veri gli eventi non coincidono: percentili, ATR e massimi locali si calcolano barra per barra,
  le finestre in minuti sì). Sezione B del collaudo rifatta in locale: 143 condizioni, 0 LOOKAHEAD, 0 ERRORE; E52 è
  NON_ESERCITATA sul mercato sintetico del notebook, che ha buchi (mai 14 giorni pieni di fila). Pandas 2.2: con il
  notebook su Colab.
- **Conteggi sui dati veri:** uguali a quelli del §1, ottenuti con lo script della proposta.
