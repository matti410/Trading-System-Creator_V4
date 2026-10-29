# 76 · Incarico: chiudere i problemi aperti di `00`

**Data:** 28 ottobre 2026
**Stato:** chiuso. PR 1 (A1, A2, A3) unita con la PR #89, PR 2 (B1–B4) con la PR #90.
**Da dove nasce:** la tabella «Problemi aperti» di `00`, dopo la PR #88.

---

Testo dell'incarico di Mattia (28/10/2026), così come l'ha scritto:

Ciao, sono Mattia. Nuovo incarico: chiudere i problemi aperti di docs/00. Parti da main dopo la PR #88. Salva questo testo come docs/76_CHIUSURA_PROBLEMI_APERTI.md e scrivimi la proposta in testo, SENZA codice.

COSA SI CHIUDE
- A1: il notebook di ricerca non scrive le sue prove nel giornale: quello che misura non entra nel conto. (tocca i risultati)
- A2: sullo spot la ricerca misura anche gli short, il Lab no: le chiavi non combaciano.
- A3: le prove della ricerca già viste e mai contate (es. BYBIT_SPOT_ETHUSDT del 25/10, 66 trigger).
- B1: strada B: con una situazione scelta e il filtro vuoto, la 6 prova il segnale da solo.
- B2: schermata 4: «short dopo 41 barre» anche con lo short spento.
- B3: schermata 4: «confronta le tre righe» anche con una riga sola.
- B4: il notebook di ricerca su Colab chiede il secret GITHUB_TOKEN.
Fuori: vwap_ops.py (solo broker, sospeso), interruttore sulla curva dei profitti (rimandato).

LE MIE DECISIONI (28/10/2026)
- A1: la ricerca scrive nello studio le stesse voci del Lab (trigger, fasce del profilo, celle dell'atlante, uscite, filtri, combinazioni), con le stesse funzioni e le stesse chiavi del Lab. Una prova già contata dal Lab non si conta due volte, e viceversa. Il conto non scende mai. La soglia cumulata della ricerca legge il conto dallo studio, come il Lab.
- A2: sullo spot la ricerca misura solo i long, come il Lab. Sui perpetual non cambia niente.
- A3: le prove della ricerca già viste e mai contate si registrano adesso, con la loro chiave e la data in cui sono state viste. Prima fai l'ELENCO (dai diari, dagli HTML salvati sul Desktop, dalla storia dei commit) e me lo mandi PRIMA di scrivere nello studio: lo approvo io. Se di una prova non si ricostruisce la chiave con certezza, si conta arrotondando verso più prove, mai meno.
- B1: con una situazione scelta, il predefinito della 6 diventa il segnale dentro la situazione (coerente con le uscite, già costruite così). Senza situazione tutto come oggi.
- B2, B3: si correggono i testi: la riga dello short solo se lo short è acceso; «confronta le tre righe» solo se le righe sono più di una.
- B4: il repo è pubblico: la ricerca su Colab clona senza token e chiede il secret solo se serve davvero.

LA PROPOSTA DEVE DIRE
1. A1: quali voci scrive la ricerca, in quali celle, con quali funzioni dello studio; come garantisci che le chiavi siano identiche a quelle del Lab (stesso H, stessi assi, stesso elenco di trigger).
2. A2: dove cambia l'elenco dei trigger della ricerca sullo spot.
3. A3: come costruisci l'elenco delle prove passate.
4. B1: quali voci del conto cambiano con il predefinito nuovo.
5. Collaudo:
   - la ricerca dà gli stessi numeri di main al bit; cambia solo ciò che scrive nello studio;
   - far girare due volte la stessa ricerca non alza il conto; Lab e ricerca sulle stesse chiavi non lo alzano;
   - B1: senza situazione la 6 identica al bit; con una situazione cambia solo il predefinito;
   - B2–B4: cambiano solo i testi e il clone.
   Prove sui dati veri: sullo studio vero, oppure su una copia solo se mostrano chiavi già contate (regola di docs/75 §7).
6. File e test toccati, con il motivo di ogni test cambiato.

LE DUE PR
- PR 1, il conto della ricerca: A1, A2, A3 (A3 solo dopo che ho approvato l'elenco).
- PR 2, le schermate e Colab: B1, B2, B3, B4.

REGOLE
- Fermati solo per cose che cambiano i risultati, rompono il codice o toccano il conto; i dettagli di forma risolvili e scrivili in una riga nella PR.
- Nessun commento sui risultati dei dati veri.
- Controlla che la PR sia aperta prima di ogni push. Date: oggi è il 28/10/2026. Il merge lo faccio io.

Dopo questo incarico: «dalla fascia al trigger» per M01, M04, M05 e M07, con il processo di docs/50.

---

## 1 · La proposta e le decisioni di Mattia (28/10/2026)

**Indice:** §1 Proposta e decisioni · §2 PR 1: il conto della ricerca (A1, A2) · §3 A3: le prove passate ·
§4 PR 2: le schermate e Colab (B1–B4).

| | proposta | decisione |
|---|---|---|
| D1 | per ogni chiave del conto vale il numero più alto mai scritto, non l'ultimo (la voce «trigger» è un numero solo: con l'ultimo, Lab e ricerca potevano abbassarlo) | sì, nel Lab e nella ricerca; Lab su BTC al bit contro main, riga delle prove compresa |
| D2 | la 2.3 (tutte le regole d'uscita insieme) e la 3.3 (soglie della confidenza) della ricerca, che il Lab non fa, si scrivono con una chiave loro | sì |
| D3 | A3: tutti i giri passati della ricerca sui dataset crypto la cui storia studiata sta dentro quella dello studio di oggi, comprese le prove d'identità sulle copie; quarta fonte i registri delle sessioni di Claude Code sul PC | sì; l'elenco in tabella a Mattia prima di scrivere nello studio |
| ETH 25/10 | la chiave a 71 nomi (long e short) e quella a 36 (solo long, dopo A2) si contano tutte e due | sì |
| B1 | con una situazione scelta, il filtro vuoto alla 6 = il segnale dentro la situazione; nessuna parola nuova per il segnale da solo | sì |
| B4 | prima il repo pubblico, il token solo se serve | sì, anche nel Lab, nella mappa e nel collaudo del catalogo |

**Verifica chiesta da Mattia:** su BYBIT_SPOT_ETHUSDT la chiave dell'atlante della ricerca dopo A2 (H 25,
assi, i 36 trigger long) deve coincidere con quella scritta dal Lab nella PR #87 (H 25, assi
vol_trend e sessione, 36 nomi, 182 celle). Se coincide, la prova della ricerca su ETH si fa su una
copia e il conto non sale. Esito al §2.

## 2 · PR 1: il conto della ricerca (A1, A2)

**Cosa cambia:**
- `engine/registro_dataset.py`: `metti_prova`, per ogni chiave il numero più alto; `da_voci` lo usa
  (prima valeva la voce più recente). Modifica non additiva: nello studio vero del 28/10 l'ultima voce e
  la più alta coincidono su ogni chiave, quindi il conto di oggi non cambia.
- `engine/vetrina.py`:
  - i sei punti del Lab che contano (2c trigger, 3b fasce, 3c celle, 4 uscite, 5 filtri, 6
    combinazioni) passano da `metti_prova`;
  - le chiavi in funzioni comuni (`chiave_celle`, `chiave_uscite`, `chiave_filtri`,
    `impostazioni_uscite`, `percentile_uscita`), che il Lab usa al posto delle sue: stesse chiavi di prima;
  - per la ricerca: `trigger_candidati` (A2: gli stessi trigger del Lab, sullo spot solo i long),
    `conta_trigger`, `conta_fasce`, `conta_celle`, `conta_uscite`, `conta_filtri` (scrivono nel conto
    del dataset e nel giornale solo le voci cambiate, senza stampare niente), `soglia_cumulata_studio`
    (la soglia letta dal conto, come nel Lab).
- `Trading_Grid_Search_v4_backtesting.ipynb`: 1.1 (elenco dei trigger e conto), casistiche short (le
  fasce), 1.5 (le celle), 2.2 e 2.3 (le uscite), 3.1 e 3.3 (i filtri), 3.1 e 3.3 (la soglia dallo studio).
- `test_conto_ricerca.py` (nuovo, 26 test); `suite_rapida.py` (la sua durata).

**Prove d'identità (28/10/2026)**, dati di Google Drive, tutte su copie temporanee dello studio vero
(lo studio vero non è stato toccato: conto prima e dopo identico):

| prova | esito |
|---|---|
| Lab, BINANCE_PERP_BTCUSDT, giro completo (lab_btc), main contro il ramo | 290 oggetti su 292 identici al bit, `incertezza_blocchi` compresa; i 2 diversi sono la cartella temporanea. Le 10 righe delle prove, schermata per schermata, identiche |
| Lab, stessa cosa con una situazione scelta (lab_btc_cella) | lo stesso: 290 su 292, 10 righe delle prove identiche |
| ricerca, BINANCE_PERP_BTCUSDT, giro completo | 817 oggetti su 817 identici al bit; in più solo `NOMI_ATLANTE` e le voci nuove del conto. Trigger (70) e situazioni (H 25, 565) erano già nello studio: nessuna voce. Voci nuove nella copia: le uscite della 2.2 (3) e della 2.3 (6, D2), i filtri della 3.1 (29) e della 3.3 (3, D2) — chiavi che la ricerca aveva già misurato nelle prove della PR #87 e che entrano con A3. Cambia anche la frase della soglia cumulata (letta dallo studio) |
| ricerca, BYBIT_SPOT_ETHUSDT, fino all'atlante | **la verifica di Mattia:** la chiave dell'atlante della ricerca (H 25, assi vol_trend e sessione, i 36 trigger long) coincide con quella scritta dal Lab nella PR #87 (182 situazioni), e i trigger misurati sono gli stessi 32: **nessuna voce nuova, il conto non sale**. Le righe long dell'event study sono identiche a main (main misurava anche 32 short: 64 trigger e 359 situazioni) |

Suite: `test_conto_ricerca.py` 26/26; **suite completa 47/47** (19,9 minuti, 28/10/2026).

## 3 · A3: le prove passate della ricerca (scritte il 28/10/2026)

**Fonti.**
- I diari dello studio vero hanno solo voci del Lab. Anche le aperture dell'out-of-sample hanno il formato del Lab, quindi nessun giro della ricerca è stato fatto da Mattia sullo studio.
- Gli HTML sul Desktop sono del Lab e della mappa.
- Nella storia dei commit il notebook di ricerca è salvato solo con le uscite di EURUSD (broker); i salvataggi da Colab sono del Lab.
- Restano le prove d'identità di Claude dal 19/10 al 28/10, circa 60 giri. Sono state trovate nei registri delle sessioni sul PC. Le chiavi vengono dai pickle e dalle uscite delle celle salvate. I giri del 25/10 senza file salvati sono stati rifatti con la stessa versione del codice (`37690da`, `c1625a3`, `900b189`, `2a91bd6`) e gli stessi CSV del 19/10, leggendo solo i conteggi.
- Dal 19/10 al 25/10 mattina la ricerca aveva le stesse scelte predefinite: H 25, OR(E11, E1) long e OR(E9, E4) short, stop al 90° percentile. Quei giri danno le stesse chiavi.

**Approvato da Mattia il 28/10:**
- le righe 1–23, cioè i giri con l'in-sample dentro lo studio;
- i giri con l'in-sample oltre il confine: ETH spot dal 20/10 al 28/10, fino al 29/09/2025; BYBIT_PERP_SOLUSDT il 21/10, fino al 19/10/2025. Hanno la nota nel giornale.

Ogni voce ha `visto_il` e `fonte: "A3, docs/76"`. Tutte le chiavi sono a H 25, stop al 90° percentile, target spento.

| dataset | voci scritte | conto prima → dopo |
|---|---|---|
| BINANCE_PERP_BTCUSDT_M15 | 15 voci (righe 1–15): 4 famiglie di casistiche (OR(E11, E1) / OR(E9, E4); E21 / —; E21 / E39; E22 / E39) con uscite 2.2 e 2.3 e filtri 3.1 e 3.3; più le situazioni con l'elenco del 22-23/10 (558, chiave incerta, contata a parte) | 2.662 → **3.351** |
| BINANCE_PERP_XRPUSDT_M15 (nuovo) | orizzonte 25; trigger 70; situazioni 541; E3 / E36: uscite 3 e 6, filtri 29 e 3 | 0 → **652** |
| BYBIT_SPOT_ETHUSDT_M15 | trigger 64 (giro su main del 28/10) e 66 (giri oltre il confine): vale 66; situazioni a 71 nomi 359 e 370: stessa chiave, vale 370; situazioni con l'elenco del 22-23/10: 370; OR(E11, E1) / OR(E9, E4) e E21 / —: uscite e filtri (41 + 40) | 214 → **1.069** |
| BYBIT_PERP_SOLUSDT_M15 (nuovo) | orizzonte 25; trigger 64; OR(E11, E1) / OR(E9, E4): uscite 3 e 6, filtri 29 e 3 | 0 → **105** |

**Precisazioni:**
- **ETH:** nella proposta avevo stimato 605 + 823. Il giro del 28/10 e quelli del 25-28/10 oltre il confine hanno però la stessa chiave di situazioni: H 25, vol_trend e sessione, gli stessi 71 nomi. Con la regola del più alto vale 370, non 359 + 370. Il conto vero è 1.069.
- **BTC, 565 e 558:** a H 25 nello studio ci sono due chiavi diverse, contate tutte e due:
  - 558 = l'atlante con i 71 trigger del catalogo;
  - 565 = l'atlante con 72 nomi, perché c'è in più il trigger a orario ORA_LONG_@23:00 o ORA_SHORT_@23:00.

  La riga 5 di A3 (558, elenco del 22-23/10) è una terza chiave, contata a parte perché quell'elenco non si ricostruisce con certezza.
- **L'out-of-sample «fresco»:** vale per tutto lo studio. Parte dopo il 25/10/2026 21:00 (9 aperture nel diario di BTC), quindi copre già il 29/09/2025 (ETH spot) e il 19/10/2025 (SOL perp). Non serve nessuna annotazione nel diario.

## 4 · PR 2: le schermate e Colab (B1–B4, 28/10/2026)

**Cosa cambia:**
- **B1** (`engine/vetrina.py`, `scheda`): con una situazione scelta alla 3d e il campo del filtro vuoto, la 6 prova il segnale dentro la situazione, cioè il nome `CELLA_…` della 5, e lo dice in una nota. Senza situazione tutto come prima. Cambiano di conseguenza il «Cosa fare adesso» della 5 e la riga d'aiuto del campo filtro nel Lab. Il conto non cambia: la situazione è già contata alla 3c e un filtro solo non fa combinazioni. Cambia solo la voce dell'out-of-sample nel diario, che ora ha «filtri: CELLA_…».
- **B2** (schermata 4): la riga delle uscite nomina solo i lati accesi (niente «short dopo 41 barre» con lo short spento).
- **B3** (schermata 4): «Confronta le tre righe» solo se la tabella ha più di una riga.
- **B4**: nei quattro notebook che girano su Colab (Lab, ricerca, mappa, collaudo del catalogo):
  - il repo pubblico si clona senza token;
  - il secret `GITHUB_TOKEN` si legge solo se quel clone non riesce;
  - nel messaggio d'errore il token resta coperto.

  Provato il clone pubblico senza credenziali: riuscito. Nella ricerca il clone è ora `--depth 1`, come negli altri.

**Collaudo:**
- `test_atlante.py`, controlli nuovi:
  - 34b: con la situazione, la 6 a filtro vuoto dà la stessa scheda del nome `CELLA_…` scritto a mano;
  - 34c: senza situazione, sistema base; con il solo long, niente riga dello short e niente «tre righe»;
  - 37b: con long e short, le due righe ci sono.
- Le quattro celle di clone compilano. **Suite completa 47/47** (19,7 minuti).
- Dati veri, su una copia dello studio, con chiavi già contate:
  - Lab BINANCE_PERP_BTCUSDT senza situazione, main contro il ramo: 307 oggetti su 309 identici al bit; i 2 diversi sono la cartella temporanea. Le 10 righe delle prove sono identiche.
  - Ricerca BINANCE_PERP_BTCUSDT: 833 oggetti su 833 identici, nessuna voce nuova (le chiavi sono già contate con A3).
- **Non fatta:** la prova sui dati veri con una situazione scelta. Nello studio non c'è nessuna chiave di uscite con una situazione: la prova ne creerebbe una nuova e aprirebbe l'out-of-sample. Su una copia non è ammessa, sullo studio vero tocca il conto: si fa solo con il via di Mattia.
