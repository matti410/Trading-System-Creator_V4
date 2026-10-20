# 63 · Proposta: unità di rischio, funding, atlante del trigger, mercato nullo

**Data:** 20 ottobre 2026
**Stato:** APPROVATA da Mattia il 20/10/2026, con correzioni (§10). I §0 e §3–§8 sono stati corretti il 20/10 secondo il §10; il §1 (il controllo), il §2 (le verifiche) e il §9 (le domande) restano come erano, come traccia. Primo lavoro: il perimetro solo crypto (§10.0), fatto sul ramo `perimetro-solo-crypto`.
**Incarico:** `docs/62_ATLANTE_E_FLUSSO.md`.
**Letti:** `CLAUDE.md`, `docs/00`, `docs/02`, `docs/50` (tutto, in particolare §4, §5, §8, §10, §12), `docs/61`, le memorie di progetto (timeframe non solo M15, passaggio alle crypto, niente pooling, notebook allineati); i moduli `engine/event_study.py`, `stagionalita.py`, `rosa.py`, `confidenza.py`, `sessioni.py`, `filter_search_bt.py`, `due_meta.py`, `giudizio.py`, `metriche.py`, `quarantena_trade.py`, `exchange.py`, `indicatori.py` (`atr_giornaliero_chiuso`), `livelli.py` (`giorno_fx`), `vetrina.py`, `scarica_dati_crypto.py`.
**Verifiche fatte il 20/10** (§2): storico del funding e dell'open interest letto con ccxt, solo funzioni pubbliche, nessuna chiave; tempo di un giro della pipeline misurato sul PC. Nessun file del repo modificato, niente salvato in `dati/` (i CSV di prova stanno nella cartella temporanea di Claude).

---

## 0 · In breve

1. **Il controllo con i documenti di progetto** (§1) ha trovato 5 punti del 62 in contrasto (con regole già decise, con un altro punto del 62 o con un fatto tecnico) e 8 da precisare. Nessuno blocca il lavoro; tutti hanno una proposta. I più importanti:
   - l'atlante sui soli trigger della rosa **non può** recuperare i trigger piatti in media, che sono proprio il motivo del lavoro (62 §0 punto 2);
   - la griglia volatilità × trend × sessione **incrociata** dà celle troppo piccole per il minimo di 200 eventi;
   - se la cella scelta passa solo il cancello largo della rosa (Benjamini–Hochberg al 20%), il setup salta la **validazione** del passo 5 (Šidák al 5%, tenuti contro scartati, due metà);
   - le finestre di `confidenza.py` sono in **barre tarate su M15**, mentre il tool ora gira da M5 a H4.
2. **Proposta di flusso** (§3): l'atlante è una **mappa** (propone, come la rosa); la cella scelta diventa un **filtro provato al passo 5** con tenuti contro scartati e due metà. *Corretto il 20/10 (§10.1 punto 1):* le prove non diventano 8–10. La cella è stata scelta fra le circa 480 celle dell'atlante, quindi la soglia di rumore del passo 5 si calcola con **k = celle misurate nell'atlante** (circa 3,87); il giudice finale è il mercato nullo D2.
3. **Funding** (§2, §5): gli storici partono prima delle barre su tutti gli 8 perpetual; le liquidazioni sono alle 00, 08, 16 UTC ma **l'intervallo è cambiato** su SOL nel novembre–dicembre 2022 (2 ore): va letto dai dati, come chiedeva il 62. L'open interest storico **non c'è su Binance** (solo gli ultimi ~30 giorni): si scarta, con il motivo.
4. **Mercato nullo** (§7): un giro della pipeline di oggi dura **circa 65–70 secondi**; 200 giri circa 4 ore, 500 giri una notte. Una correzione al 62: i prezzi rimescolati a blocchi di una giornata **non** distruggono la struttura oraria.
5. **Ordine** (deciso il 20/10, §10.2 domanda 19): perimetro solo crypto → giornata delle crypto a 00:00 UTC → A → B → D1 → C → D2; un ramo per lavoro. Dataset di sviluppo e di identità: BINANCE_PERP_BTCUSDT; giro di controllo: BYBIT_SPOT_ETHUSDT (§10.0).
6. **Le domande per Mattia** sono in §9 (19 domande, ognuna con un consiglio).

---

## 1 · Il controllo: i punti del 62 rispetto alle regole e alle milestone del progetto

*Il controllo è quello del 20/10, fatto prima delle decisioni di Mattia: come si sono chiusi i punti aperti lo dice il §10.*

Legenda: **OK** = coerente; **PRECISARE** = coerente, ma manca una scelta; **CONTRASTO** = va contro una regola o una decisione già presa, oppure contro un altro punto del 62.

| # | punto del 62 | regola / milestone | esito | proposta |
|---|---|---|---|---|
| 1 | §0 «i risultati collaudano il tool» | `00`, la regola che viene prima di tutte | **OK** | La riga del mercato nullo nella scheda (§7) va scritta come misura del tool, mai come «promosso». |
| 2 | §5 la soglia empirica «è il pezzo che manca a `00` §3» | `00`, «Cosa manca», punto 3 (le prove dei passi non si sommano) | **OK** | È proprio quella milestone. La soglia vale per un symbol, un timeframe, un H e una versione del catalogo: va ricalcolata quando uno dei quattro cambia. |
| 3 | §5 «nel nulla il tool arriva a t ≥ X» | `00` passo 4 e `02`: nessuna soglia automatica decide se un setup ha un vantaggio; il tool automatizza solo la bocciatura | **PRECISARE** | La soglia empirica resta **informativa**: i cancelli di `02` non cambiano. Se un giorno la si vorrà come cancello, potrà solo **bocciare** (domanda 17). |
| 4 | §1.2 e §4 «le stesse definizioni di `confidenza.py`» | memoria del 18/10: il tool lavora su M5, M15, M30, H1, H4, niente costanti da M15 | **CONTRASTO** | `asse_volatilita` usa 20 barre di rendimenti e una mediana su 500 barre (il commento dice «500 ~ 5 giorni in M15»). Su H4 500 barre sono 83 giorni, su M5 meno di 2 giorni. Proposta: definire le finestre come **durate** (5 ore e circa 5 giorni), convertite in barre con `passo_barre`; su M15 danno esattamente i numeri di oggi (§6.2, domanda 8). |
| 5 | §1.2 «fascia oraria per sessioni (`engine/sessioni.py`)» | `sessioni.py`: le sessioni sono **sovrapposte** (Londra–New York 4 ore insieme) e non coprono le 24 ore (circa 2–3 ore fra la chiusura di New York e l'apertura di Tokyo) | **PRECISARE** | Serve una **partizione** fissata prima, costruita dalle sessioni del catalogo: Asia e notte, Europa, Londra + New York, America (§6.2, domanda 9). |
| 6 | §1.2 «sulle crypto in UTC» | `sessioni.py` lavora in ora locale delle piazze, con l'ora legale; `fuso_profilo` usa UTC sui symbol da exchange | **PRECISARE** | Due letture possibili: le stesse sessioni (Tokyo, Londra, New York in ora locale) anche sulle crypto, oppure fasce UTC fisse. Consiglio le stesse sessioni: sono le ore in cui le piazze tradizionali sono aperte, e il motivo economico è quello (domanda 10). |
| 7 | §4 «per ogni trigger **della rosa**» | 62 §0 punto 2: «un trigger che funziona solo in volatilità alta esce piatto nella media e viene scartato prima di essere condizionato» | **CONTRASTO** (interno al 62) | La rosa tiene solo chi è positivo **in media** (t netto > 0, BH, due metà): un trigger piatto in media non ci entra mai, quindi l'atlante non lo vedrebbe. Proposta: l'atlante misura **tutte le entry vere** (lo stesso insieme della rosa prima dei cancelli), con un solo controllo dei falsi positivi su tutte le celle (§6.1). |
| 8 | §4 regola 5 «minimo di eventi per cella, coerente con `MIN_EVENTI`» | `rosa.MIN_EVENTI = 200`; eventi tipici dal registro di `50` §10: 700–3.000 per lato sullo storico intero (E32 716–1.170, E31 1.900–2.650, E35 2.199–3.413), quindi 560–2.400 in-sample | **CONTRASTO** (numerico) | Con 2 × 2 × 4 sessioni = 16 celle per lato (32 con il funding) una entry da 1.000 eventi ha in media 60 eventi per cella: quasi tutto sotto il minimo. Proposta: assi **non tutti incrociati** (griglia di `confidenza` 2 × 2, e sessione a parte): 8 celle, ~250 eventi ciascuna (§6.2, domanda 7). |
| 9 | §4 regola 2 «misura netta dei costi» | `02` e `rosa.py`: la rosa e l'event study sono **lordi** (lo scarto dal mercato non toglie costi) | **PRECISARE** | Due passi vicini con due convenzioni diverse. Consiglio: nell'atlante lo scarto dalla cella è **netto** (costi tolti al trigger; il mercato della cella è un riferimento, non un trade), e la rosa resta com'è; il riquadro lo dice (domanda 11). |
| 10 | §4 «dall'atlante al setup» + §4 «convivenza con il passo 5» | `00` passo 5: un'idea alla volta, **tenuti contro scartati**, soglia di rumore Šidák, due metà; la confidenza (`cella_contesto`) si prova **al passo 5 sopra il filtro scelto** | **CONTRASTO** (se la cella va avanti con il solo cancello della rosa) | La rosa è un cancello per **proporre**, non per validare (`02`). Se la cella scelta dall'atlante passasse direttamente alle uscite, il setup salterebbe la validazione che oggi ha ogni filtro. In più la stessa griglia verrebbe usata due volte (atlante e confidenza). Proposta C4 (§3): la cella scelta si **prova al passo 5 come filtro**, con i cancelli di sempre; la confidenza non si ricostruisce sugli stessi assi. |
| 11 | celle e stati come condizioni | `CLAUDE.md`: condizioni nei dizionari dei file del catalogo; `00`: i filtri `CONF_…` nascono nel notebook | **PRECISARE** | Se i filtri di cella entrassero nel dizionario `FILTRI`, la ricerca dei filtri di oggi ne proverebbe 46 invece di 38: cambierebbero `k`, la soglia e l'identità. Proposta: si registrano **su richiesta**, come `CONF_…` e le condizioni orarie. |
| 12 | §2 unità nuove, «costi in pips con conversione esplicita» | `50` §5 (unità: costi in pips, conversione esplicita); `02`, «Unità» | **OK** | Una nota: «multipli di ATR» non va chiamato «R»: in `02` e `61` R è la distanza dallo stop più il costo. Propongo il nome **ATR** (es. «+0,12 ATR»). La tabella di `02` cita ancora `deduci_pip`: dal 10/10 il pip viene da `simboli.py` (da aggiornare insieme). |
| 13 | §2 «lo stesso ATR giornaliero a 5 giornate chiuse del money management» | `61` §14.7 (giornata FX, 17:00 New York); sulle crypto il profilo orario e E41 usano la **mezzanotte UTC** | **PRECISARE** | Sulle crypto oggi convivono due giornate: 17:00 New York (ATR, `gap_trend`, F36, F39, `giorno_fx`) e mezzanotte UTC (profilo orario, E41). Per l'unità A consiglio l'ATR **identico** al money management; la scelta della giornata sulle crypto è una decisione a parte, che tocca più moduli (domanda 3). |
| 14 | §3 scaricare il funding con ccxt | `CLAUDE.md`: «solo funzioni PUBBLICHE di lettura di ccxt (load_markets, fetch_ohlcv)» | **PRECISARE** | Serve `fetch_funding_rate_history`, pubblica e di sola lettura, ma non è nell'elenco. Il 62 lo autorizza; propongo di aggiungerla all'elenco di `CLAUDE.md` (domanda 4). Per le verifiche del §2 ho usato anche `fetch_open_interest_history` (pubblica, sola lettura). |
| 15 | §3 «colonna di costo come `CostoExtraPips`» | `quarantena_trade.costo_extra_pips`: la colonna è **mai negativa** (è uno spread in più) | **PRECISARE** | Il funding può essere un **incasso** (short con tasso positivo). Proposta: una colonna separata con segno, `FundingPips`, sottratta da `pips_per_trade` come `CostoExtraPips` (§5.2). |
| 16 | §5 «prezzi rimescolati a blocchi di una giornata: distrugge ogni struttura, anche quella oraria» | — (fatto tecnico) | **CONTRASTO** (correzione) | Un blocco di una giornata intera, allineato all'orologio, **porta con sé** il suo andamento ora per ora: il profilo orario resta, sparisce solo il legame fra un giorno e l'altro (trend di più giorni, volatilità che dura). Vedi §7.2. |
| 17 | §4 «gli stessi stati per tutti i symbol» | memoria del 18/10: no al pooling multi-symbol; `CLAUDE.md`: scegliere per symbol in base ai risultati conta come prova in più | **OK** | Stati uguali per tutti non è pooling (i dati non si mescolano). Se si sceglie una cella diversa per ogni symbol, ogni symbol è una prova a sé, e lo dice il conteggio. |
| 18 | §1.3 meta-labeling e ML fuori | `00`: il ramo ML è un altro repo | **OK** | — |
| 19 | §6 un ramo per lavoro, tre notebook insieme | `CLAUDE.md`, memoria «notebook sempre allineati» | **OK** | L'atlante va nei due Lab (via `vetrina.py`) e nel notebook di ricerca; il mercato nullo solo da terminale, nel Lab arriva una riga. Nessuna rinumerazione: l'atlante entra come **3c**, come la rosa è entrata come 3a bis. |
| 20 | prove dell'atlante e del mercato nullo | `50` §10: il registro conta le prove delle **condizioni** entrate dalle fonti | **OK** | Come per il modello del money management (`61` §14.6): le prove dell'atlante si contano nell'atlante stesso (BH) e nel passo 5; il registro di `50` non cambia. |

**Cosa non ho trovato in contrasto:** il principio «parametri fissati prima» (rispettato da tutti e quattro i lavori), l'out-of-sample aperto una volta (atlante e mercato nullo lavorano solo sull'in-sample), il money management (non cambia: lavora già in multipli di rischio e riceve i pips netti, quindi il funding ci entra da solo), il tetto della leva e la regola dello spot solo long.

---

## 2 · Le verifiche sui dati (20/10/2026, sola lettura)

### 2.1 · Storico del funding (ccxt `fetch_funding_rate_history`, nessuna chiave)

| perpetual | funding dal | barre M15 dal | intervallo fra le liquidazioni | tassi estremi |
|---|---|---|---|---|
| Binance BTC | 10/9/2019 | 2/1/2020 | sempre 8 ore | ±0,30% |
| Binance ETH | 27/11/2019 | 2/1/2020 | sempre 8 ore | −0,36% / +0,38% |
| Binance SOL | 13/9/2020 | 14/9/2020 | 8 ore; **4 ore** il 9–10/11/2022 (3 volte) e **2 ore** dal 10 al 18/11/2022 (98 volte) | **−2,00%** il 9–10/11/2022 (crollo di FTX) |
| Binance XRP | 6/1/2020 | 6/1/2020 | sempre 8 ore | ±0,50% |
| Bybit BTC | 25/3/2020 | 25/3/2020 | sempre 8 ore | ±0,375% |
| Bybit ETH | 21/10/2020 | 15/3/2021 | sempre 8 ore | −0,35% / +0,375% |
| Bybit SOL | 29/6/2021 | 15/10/2021 | 8 ore; **2 ore** dal 10/11 al 20/12/2022 | −0,86% |
| Bybit XRP | 13/5/2021 | 13/5/2021 | sempre 8 ore | −0,58% / +0,18% |

- **Ogni storico del funding copre tutte le barre** del suo perpetual: nessun trade resta senza tasso.
- **Le liquidazioni cadono alle 00:00, 08:00 e 16:00 UTC** (con l'intervallo a 2 ore anche alle ore pari). Binance scrive gli orari con qualche millesimo di secondo in più (08:00:00.005): vanno arrotondati al minuto.
- **L'intervallo è cambiato nel tempo**, quindi non si può supporre: si legge riga per riga.
- **Lezione per lo scaricatore:** Bybit restituisce al massimo 200 tassi per richiesta e lavora all'indietro dalla data finale. La prima prova, con finestre di 66 giorni, ha perso 50 giorni di SOL proprio quando l'intervallo era sceso a 2 ore (la finestra conteneva più di 200 tassi). Rifatta con finestre di 150 ore: storico completo. La finestra va sempre dimensionata sull'intervallo più corto possibile (1 ora).
- **Come è fatto il tasso:** fra il 33% e il 46% delle liquidazioni vale **esattamente 0,01%** (la sola componente d'interesse, senza premio); sopra lo 0,01% il 10–17%, sotto zero il 14–29%. La mediana è quasi sempre 0,01%. Conseguenza: dividere il funding in due livelli «sopra/sotto la mediana mobile» darebbe due metà sbilanciate e piene di pareggi (§6.3).
- **Ordine di grandezza del costo** (calcolato dai tassi, non da un sistema): su Binance BTC il tasso medio è 0,0105% ogni 8 ore. Un long tenuto 25 barre M15 (6 ore e 15 minuti) attraversa in media 0,8 liquidazioni: circa **0,8 punti base**, contro **10 punti base** di commissione taker andata e ritorno. Piccolo ma sistematico, e con il segno: in media il long paga e lo short incassa.

### 2.2 · Open interest storico (ccxt `fetch_open_interest_history`)

- **Binance:** solo gli ultimi ~30 giorni. Con una data di inizio più vecchia l'exchange risponde «parameter 'startTime' is invalid».
- **Bybit:** serie a 1 ora disponibile almeno dal 1/1/2021 (dal 2019 nessun dato).

**Proposta: l'open interest si scarta**, con il motivo: non c'è su uno dei due exchange, e gli stati devono essere gli stessi per tutti i symbol (62 §4 regola 1). Riapribile se si trova una fonte storica per Binance.

### 2.3 · Basis perpetual – spot

I CSV spot ci sono, ma con due limiti: lo spot di **Bybit** parte dopo il perpetual (BTC 5/7/2021 contro 25/3/2020; SOL 21/10/2021), e lo spot di **Binance** ha 15 buchi (153 barre) per manutenzione. Nelle barre senza spot la basis non esiste: quelle barre restano senza cella.

### 2.4 · Tempo di un giro della pipeline (per il mercato nullo)

Misurato sul PC di Mattia (6 processori), con le funzioni del Lab e il sistema base E12 engulfing:

| passo | EURUSD (134.688 barre in-sample) | BINANCE_PERP_BTCUSDT (190.420) |
|---|---|---|
| preparazione (dati, costi, indicatori) | 9,9 s | 13,7 s |
| esplora + rosa dei trigger | 8,3 s | 10,4 s |
| uscite | 3,9 s | 4,5 s |
| ricerca dei filtri + due metà | 53,0 s | 56,1 s |
| **un giro (senza la preparazione)** | **~65 s** | **~71 s** |

---

## 3 · Il flusso proposto, in una pagina

Oggi (`00`, i sette passi):

```
1 orizzonte → 2 trigger (rosa) → 3 uscite (rosa dei sistemi) → 4 giudizio → 5 filtri (38, a tappeto) → 6 out-of-sample → 7 money management
```

Con i quattro lavori:

```
dati ── barre + funding + spot (B), giornata 00:00 UTC
 │
1 orizzonte H
2 trigger ── rosa (scarto lordo dal mercato, in bp dopo U2) ─┐
             atlante 3c (scarto lordo dalla cella          ─┤  si guardano insieme; sceglie Mattia:
                         + guadagno netto in bp > 0)        │  un trigger e, se vuole, UNA cella per lato
3 uscite ── come oggi (netti, funding compreso)
4 giudizio del sistema base ── come oggi
5 filtri ── STRADA A: come oggi (38 filtri, soglia con k = 38)     ← se non si usa l'atlante
            STRADA B: la cella scelta, tenuti contro scartati       ← se si usa: soglia con
                      e due metà                                       k = celle dell'atlante (~3,87)
6 out-of-sample ── una volta sola, come oggi
7 money management ── invariato
                                         + accanto alla scheda: «nel mercato nullo …» (D)
```

**Il perché, in parole semplici.** L'atlante è una **mappa**: dice dove un trigger sembra funzionare. Una mappa propone, non promuove: per questo la cella scelta non va direttamente avanti, ma passa al passo 5 la stessa misura che oggi passa ogni filtro (tenuti contro scartati, due metà). **Corretto il 20/10 (§10.1 punto 1):** il passo 5 riprova la cella sugli stessi dati in-sample su cui è stata scelta, quindi non è una validazione indipendente. Le prove vere sono le circa 480 celle confrontate nell'atlante, e la soglia di rumore del passo 5 si calcola con quel k (Šidák: 3,83 con 400 celle, 3,87 con 480, 3,91 con 560). Il giudice finale è il mercato nullo: D1 e D2 ripetono tutta la catena sul rumore e dicono quale delle due strade si inganna di meno.

Questa è la proposta **C4** del §6.5; le alternative sono lì.

---

## 4 · Lavoro A · Le unità di rischio

### 4.1 · Cosa si fa e perché

Il problema è quello del 62 §2: su BTC, ETH, SOL, XRP (e meno su indici e oro) i pips pesano di più gli anni a prezzo alto. Si aggiungono **due unità accanto ai pips**, per ogni trade e per ogni rendimento a H barre:

- **bp**: il risultato in centesimi di punto percentuale del prezzo d'ingresso. 1 trade da +70 $ su BTC a 7.000 $ = +100 bp; +1.000 $ a 100.000 $ = +100 bp. Pesano uguale.
- **ATR**: il risultato diviso l'ATR giornaliero a 5 giornate chiuse alla barra del segnale (`indicatori.atr_giornaliero_chiuso`, lo stesso del money management, noto prima dell'ingresso).

**I costi nelle nuove unità.** Si convertono trade per trade con il prezzo d'ingresso: costo_bp = costo_pips × pip ÷ prezzo × 10.000. Sulle crypto la commissione taker diventa una costante (Binance perpetual: 2 × 0,05% = 10 bp andata e ritorno, a qualunque prezzo); sui CFD lo spread fisso in pips pesa di più in bp quando il prezzo è basso. I parametri dei costi restano in pips (o in frazione per le crypto), come oggi: la conversione è solo nella misura.

### 4.2 · Quale unità decide: U1, U2, U3

| | come | pro | contro |
|---|---|---|---|
| **U1** | colonne in più; decidono ancora i pips nei passi di oggi; atlante e mercato nullo decidono in bp | additiva, identità garantita su tutto | nella stessa schermata la rosa decide in pips e l'atlante in bp: un trigger può essere nella rosa e avere tutte le celle grigie anche per l'unità |
| **U2** | decide il bp in tutti i passi, per tutti i symbol | una sola unità, confronti onesti fra anni e fra symbol | cambia i numeri anche su EURUSD (di poco); prova di identità da riscrivere; da rifare tutti i test di identità del Lab |
| **U3** | bp solo dove il prezzo cambia molto | EURUSD invariato | due regole nel tool, e una soglia «il prezzo cambia molto» da fissare |

**Decisione del 20/10 (§10.2 domanda 1):** **U1 come primo commit** (colonne in più, identità garantita), **U2 subito dopo** nello stesso lavoro: con il perimetro solo crypto (§10.0) il bp è l'unità che decide in tutti i passi. La tabella di confronto pips contro bp (stessi trade, solo l'unità cambia: t, EV, due metà) si fa su BINANCE_PERP_BTCUSDT e BYBIT_SPOT_ETHUSDT, solo per documentare quanto cambia. U3 non serve più. I pips restano visibili accanto (sulle crypto 1 pip = il passo della tabella `SIMBOLI_EXCHANGE`, es. 1 $ su BTC); i costi delle crypto, in % del prezzo, si mostrano in bp con la conversione in pips accanto.

**Prerequisito (§10.1 punto 3):** prima di A un ramo piccolo porta la giornata dei symbol da exchange a **00:00 UTC** ovunque (ATR, `gap_trend`, F36, F39, `giorno_fx` o la sua versione crypto). L'ATR dell'unità A è quindi quello a 5 giornate UTC chiuse, lo stesso che userà il money management sulle crypto.

### 4.3 · Firme (nomi indicativi)

```python
# engine/metriche.py  (additivo)
bp_per_trade(trades, pip_size, commission=0.0) -> (lordi_bp, netti_bp)
        # netti_bp = netti_pips × pip_size ÷ EntryPrice × 10_000; FundingPips e CostoExtraPips compresi
atr_per_trade(trades, atr, pip_size, commission=0.0) -> (lordi_atr, netti_atr)
        # atr: la serie di atr_giornaliero_chiuso sullo storico intero; si legge alla barra del segnale

# engine/stagionalita.py  (additivo)
rendimenti_avanti_unita(df, H, unita="bp", pip=None, atr=None) -> np.ndarray
        # stessa convenzione di rendimenti_avanti (segnale i, ingresso Open[i+1], misura Close[i+H])

# engine/rosa.py, engine/giudizio.py  (parametri nuovi con valore di oggi)
rosa_entry(..., unita_extra=("bp", "atr"))   # colonne scarto_bp, t_bp, scarto_atr, t_atr
scheda_strategia(...)                         # voci ev_bp, ev_atr accanto a ev_pips
```

### 4.4 · Cosa si vede nei notebook

- Schermata 1 (riepilogo): «Costo per trade» anche in bp.
- Rosa dei trigger e dei sistemi: con U1 due colonne in più, «Scarto (bp)» e «Solidità in bp»; con U2 il bp passa in prima posizione e decide, i pips restano accanto (sono l'unità del live).
- Scheda strategia: «Guadagno medio netto per trade» in bp, ATR e pips, su tre righe.
- Riquadro «Come leggerlo»: una frase sola, «i bp pesano allo stesso modo un trade del 2020 e uno del 2025».

### 4.5 · Collaudo

- Casi a mano: lo stesso trade dell'1% su prezzi 7.000 e 70.000 dà 70 e 700 pips ma 100 bp entrambi; costo di una commissione dello 0,05% per lato = 10 bp a qualunque prezzo.
- ATR: troncamento (la giornata in corso non entra); lo stesso valore usato da `mm_adattatore`.
- Identità (§10.0): con U1 ogni numero esistente identico nei due notebook vivi, su BINANCE_PERP_BTCUSDT a parità di barre; giro completo su BYBIT_SPOT_ETHUSDT. Con U2 la differenza attesa è documentata dalla tabella di confronto. Tutte le suite `test_*.py`, comprese quelle sui symbol del broker, devono continuare a passare.

### 4.6 · Rischi

Tre colonne invece di una possono confondere: il riquadro dice sempre quale decide. Con U1 il rischio di errore è basso (nessun calcolo esistente cambia); con U2 cambiano i numeri che decidono, e per questo U1 e U2 sono due commit separati.

---

## 5 · Lavoro B · Funding e basis dei perpetual

### 5.1 · Dati

- `scarica_dati_crypto.py` scarica anche il funding dei soli perpetual, nello stesso giro delle barre: `dati/<SYMBOL>_FUNDING.csv`, colonne `Date` (UTC, arrotondata al minuto), `tasso`, `intervallo_ore` (dalla liquidazione precedente). Se il file c'è già, scarica solo le righe nuove.
- Controlli a fine corsa, come per le barre: primo tasso rispetto alla prima barra; intervalli per anno; **liquidazioni mancanti** (un intervallo più lungo di quello delle righe vicine); tassi oltre il tetto dell'exchange.
- Solo `fetch_funding_rate_history`, pubblica, senza chiavi (ammessa in `CLAUDE.md` dal 20/10). Finestre di Bybit dimensionate su un intervallo di 1 ora (§2.1).

### 5.2 · Costi

**La regola:** si paga (o si incassa) il funding di ogni liquidazione **in cui la posizione è aperta**. Il motore entra ed esce all'apertura di una barra, cioè un istante **dopo** l'inizio della barra; la misura a H barre chiude alla chiusura della barra, cioè un istante **prima** della fine. Quindi:
- trade del motore: contano le liquidazioni S con `ingresso < S ≤ uscita`;
- rendimento a H barre (atlante): contano le liquidazioni con `inizio della barra i+1 < S < fine della barra i+H`.

**L'importo** di una liquidazione, in pips: `lato × tasso × prezzo in S ÷ pip`, con lato +1 per il long (paga se il tasso è positivo) e −1 per lo short. Il prezzo in S è l'Open della barra che inizia in S. L'exchange usa il prezzo «mark», che non abbiamo: è un'approssimazione dichiarata, di pochi millesimi sul costo.

```python
# engine/exchange.py  (additivo)
scarica_funding(symbol, da="2020-01-02", a=None, ex=None) -> DataFrame[tasso, intervallo_ore]
leggi_funding(percorso) -> DataFrame
controlla_funding(funding, df) -> dict
funding_per_trade(trades, df, funding, pip_size) -> pd.Series      # FundingPips, + = pagato
funding_avanti(df, H, funding, pip_size) -> np.ndarray             # per l'atlante, verso long

# engine/metriche.py  (additivo): pips_per_trade toglie anche FundingPips se la colonna c'è
# engine/exit_search_bt.py, engine/filter_search_bt.py (additivo): parametro funding=None;
#     dove oggi si chiama costo_extra_pips, si aggiunge FundingPips se funding non è None
# engine/vetrina.py: costi_storico mette il funding nei costi dei perpetual; carica_storico lo legge
```

Con `funding=None` (CFD, spot, notebook vecchi) tutto è identico a oggi.

### 5.3 · Stati (per l'atlante)

```python
# engine/indicatori.py  (additivo, fuori da aggiungi_indicatori: le colonne del catalogo non cambiano)
funding_liquidato(df) -> pd.Series   # ultimo tasso già liquidato prima dell'inizio della barra,
                                     # riportato a 8 ore (tasso × 8 ÷ intervallo_ore)
basis_bp(df) -> pd.Series            # (Close perpetual − Close spot) ÷ Close spot × 10.000, stessa barra
```

Le colonne grezze (`funding_tasso`, `spot_close`) le aggiunge `carica_storico` al DataFrame dei perpetual; le due funzioni le leggono. Così il collaudo di lookahead per troncamento funziona come per ogni altro indicatore. Sui dati senza quelle colonne (CFD, spot, mercato sintetico del collaudo) le funzioni danno NaN e le celle non esistono.

### 5.4 · Orari con un motivo

Le liquidazioni (00:00, 08:00, 16:00 UTC; le ore pari nei periodi a 2 ore) diventano un'informazione del profilo orario: nella tabella del profilo dei perpetual una colonna «liquidazione del funding» segna le fasce che la contengono o la precedono. Non si crea nessuna condizione nuova: chi vuole provare un'ora intorno alla liquidazione usa le condizioni orarie che ci sono (`ORA_LONG_@07:45` con `X_ORA_@08:15_UTC`…), e conta come **una** prova, perché l'ora ha una causa scritta (`02`, «Prove»).

### 5.5 · Cosa si vede

- Schermata 1: la riga «Funding (perpetual): non ancora contato» diventa «Funding (perpetual): contato. Tasso medio dell'in-sample X% ogni 8 ore; in media il long paga, lo short incassa».
- Scheda e verifica dei trade: il costo diviso in tre righe, commissione, spread, funding (medio per trade, con il segno).
- Money management e stress test: nessun cambio di schermata; i pips netti contengono già il funding.

### 5.6 · Collaudo

- Casi costruiti a mano: trade che attraversa 0, 1, 2 liquidazioni; long e short; tasso positivo e negativo; ingresso esattamente su una liquidazione (non paga), uscita esattamente su una liquidazione (paga); intervallo che passa da 8 a 2 ore.
- Stati: troncamento (il tasso della liquidazione in corso non si vede prima che avvenga); riporto a 8 ore.
- Scaricatore: exchange finto senza rete, come `test_exchange.py`, con una risposta di Bybit più lunga di 200 righe (la trappola del §2.1).
- Identità: spot (BYBIT_SPOT_ETHUSDT) identico a oggi; perpetual (BINANCE_PERP_BTCUSDT) identico a oggi con `funding=None`; le suite sui symbol del broker continuano a passare (codice condiviso, §10.0).

### 5.7 · Rischi

Il prezzo «mark» approssimato con l'Open; un tasso eccezionale (−2% su SOL il 9/11/2022) pesa molto su pochi trade: la verifica dei trade lo mostra. Il funding non cambia i trade, solo il loro risultato: nessun rischio di trade diversi fra prima e dopo.

---

## 6 · Lavoro C · L'atlante del trigger

### 6.1 · Su quali trigger

**Tutte le entry vere** del catalogo (le stesse che la rosa misura: niente metro, niente composite, niente orarie), sull'in-sample, all'orizzonte H già scelto. È l'unico modo di vedere un trigger piatto in media (punto 7 del §1). Il conto delle prove è esplicito: k = entry misurabili × celle misurabili (un lato per entry, come nel catalogo). Con circa 60 entry e 8 celle, k ≈ 480: lo gestisce lo stesso controllo della quota di falsi positivi della rosa (Benjamini–Hochberg, q = 20%).

Nella schermata si mostrano in dettaglio i trigger scelti da Mattia e quelli con almeno una cella che passa; il resto sta nella tabella.

### 6.2 · Le celle (fissate adesso, prima di guardare)

**Asse 1 · volatilità × trend: la griglia 2 × 2 di `confidenza.py`** (4 celle per lato), con le sue definizioni:
- volatilità alta / bassa: deviazione dei rendimenti su 5 ore rispetto alla sua mediana degli ultimi ~5 giorni (su M15: 20 e 500 barre, identiche a `asse_volatilita`);
- trend a favore / contro: `gap_trend` (regressione della giornata meno il VWAP della giornata) nel verso del trade, sopra o sotto la sua mediana degli ultimi ~5 giorni. Sui symbol da exchange la giornata è quella da 00:00 UTC (§10.1 punto 3). **Nota di onestà sul nome:** «a favore» vuol dire «nella metà alta degli ultimi giorni», non «il prezzo sta salendo».

**Asse 2 · sessione** (4 celle), partizione costruita dalle sessioni di `sessioni.py`, in ora locale con l'ora legale:

| cella | quando |
|---|---|
| ASIA_NOTTE | Londra e New York chiuse (Tokyo aperta, o nessuna piazza) |
| EUROPA | Londra aperta, New York chiusa |
| LONDRA_NY | Londra e New York aperte insieme |
| AMERICA | New York aperta, Londra chiusa |

**Asse 3, solo perpetual** (2 celle, dopo il lavoro B, scelto adesso fra i due): vedi §6.3.

**Perché gli assi non sono incrociati fra loro:** con 4 × 4 = 16 celle per lato, una entry da 1.000 eventi in-sample avrebbe in media 60 eventi per cella; con assi separati ne ha circa 250 nelle celle volatilità × trend e 250 nelle sessioni (meno di notte). La griglia 2 × 2 resta incrociata perché è già così in `confidenza.py` e ha senso economico (lo stesso trend vale diverso a volatilità alta o bassa).

**Durate, non barre** (punto 4 del §1; deciso il 20/10 con la correzione del §10.1 punto 2): finestre di 5 ore e di circa 5 giorni, convertite nel numero di barre del timeframe, **con un minimo di 20 rendimenti** per ciascuna. Su M15 sono esattamente 20 e 500 barre, quindi identiche a `confidenza.py`; su H1 e H4 «5 ore» darebbe 5 e poco più di 1 rendimento, e la finestra si allunga fino a 20. `asse_volatilita` accetta solo 5, 20, 50 o 200 barre (vincolo del file di Mattia `volatility_features_engineering.py`, invariato): per gli altri timeframe la deviazione si calcola in `engine/indicatori.py` con la stessa formula, e il collaudo verifica che su M15 dia la stessa serie di `asse_volatilita` (domanda 8).

**Minimo di eventi per cella: 200** (deciso il 20/10), come `MIN_EVENTI` della rosa. Una cella sotto il minimo è grigia con la scritta «troppo pochi casi».

**Sessioni anche sulle crypto** (deciso il 20/10): le stesse quattro, in ora locale delle piazze con l'ora legale, non fasce UTC fisse.

### 6.3 · La variabile dei perpetual: funding o basis

| | funding (ultimo tasso liquidato) | basis perpetual – spot |
|---|---|---|
| motivo economico | il prezzo che pagano i long per la leva: alto = long affollati | lo stesso fatto visto barra per barra (il funding è in pratica la media della basis nelle 8 ore) |
| storico | Binance dal 2019–2020, Bybit dal 2020–2021: copre tutte le barre | Binance dal 2020; Bybit solo da luglio–ottobre 2021; buchi dello spot Binance |
| divisione in 2 livelli | la mediana mobile non funziona: 33–46% dei valori sono esattamente 0,01%. Si può usare una soglia con un significato: «premio positivo» (tasso > 0,01%) contro il resto, ma le celle sono sbilanciate (10–17% contro 83–90%) | continua: la mediana mobile funziona come negli altri assi, due metà bilanciate |
| si aggiorna | 3 volte al giorno | ogni barra |

**Decisione del 20/10: la basis**, divisa alla mediana mobile degli ultimi ~5 giorni come gli altri assi (basis alta / bassa), perché due celle bilanciate si leggono e due celle 15/85 quasi mai. Il funding resta comunque nei costi. Sui perpetual Bybit l'asse esiste solo dove c'è lo spot.

### 6.4 · La misura in ogni cella

Per ogni entry e ogni cella, con la convenzione dell'event study, **due domande e due colonne** (deciso il 20/10, §10.1 punto 4; niente convenzioni mescolate in un solo numero):
1. **scarto dal mercato della cella, lordo, in bp** — «il trigger aggiunge qualcosa al mercato?». Stessa convenzione della rosa. Il riferimento è **il mercato della stessa cella e della stessa fascia oraria** (la baseline oraria della rosa, ristretta alla cella): così l'atlante misura il trigger, non la deriva del regime o dell'ora. Tecnicamente è la funzione `stagionalita.scarto_orario` di oggi, con codici «fascia × cella» invece di «fascia»: nessuna statistica nuova da inventare, e l'incertezza tiene già conto delle barre vicine e del rumore del riferimento. Su questo numero si calcolano t, p a una coda, il controllo BH su tutte le k celle e le **due metà** (scarto positivo su entrambe);
2. **guadagno netto del trigger nella cella, in bp** — «paga i costi?»: rendimento a H barre con commissione, spread e (sui perpetual) funding tolti. Cancello in più: **maggiore di zero**.

Una cella **passa** se: almeno 200 eventi, t > 0, BH, due metà **e** guadagno netto > 0.

### 6.5 · Dall'atlante al setup, e la convivenza con il passo 5

**Regola di scelta, scritta prima (decisa il 20/10):** al massimo **una cella per lato**; il setup è «trigger dentro quella cella». Più celle in OR costerebbero più prove e la regola diventerebbe meno chiara.

**Come convivono atlante e passo 5:**

| | come | pro | contro |
|---|---|---|---|
| **C1** | se si usa l'atlante, il passo 5 non c'è: trigger@cella → uscite → giudizio → out-of-sample | il flusso più corto | la cella non passa la validazione dei filtri (tenuti contro scartati, Šidák, due metà): contrasta con `00` passo 5 e `02` (punto 10 del §1) |
| **C2** | il passo 5 resta intero sopra trigger@cella, e le prove si sommano | nessuna rinuncia | due scelte di contesto una sopra l'altra; le prove raddoppiano |
| **C3** | come C2, ma senza i filtri che usano gli stessi assi (volatilità, trend, sessione) | meno doppioni | la lista dei filtri esclusi è una scelta in più, da fare a mano |
| **C4** | l'atlante **propone** la cella; il passo 5 **la misura come filtro** (tenuti contro scartati, due metà), con la soglia di rumore calcolata su **k = celle misurate nell'atlante** | stessa misura dei filtri di oggi; il conto delle prove resta quello vero dell'atlante; nessun cancello nuovo; il mercato nullo confronta due strade pulite | i filtri del catalogo non si provano sopra il setup dell'atlante, a meno di sceglierlo (e allora si contano) |

**Decisione del 20/10: C4** (§10.1 punto 1, §10.2 domanda 14). **Correzione rispetto alla prima stesura:** avevo scritto che al passo 5 le prove diventano 8–10 (le righe provate) e che l'asticella scende a 2,73–2,80 «senza perdere severità». Era sbagliato: la cella è stata scelta guardando l'atlante, che ha confrontato circa 480 celle sugli stessi dati in-sample; il passo 5 è una seconda misura dello stesso effetto, non una prova nuova. Quindi nella strada B la soglia del passo 5 si calcola con k = celle misurate nell'atlante (circa 3,87 con 480), e il giudice finale di quanto si inganna la strada B è il mercato nullo D2, che ripete tutta la catena atlante + passo 5. Due dettagli:
- le celle diventano filtri registrati **su richiesta** (non nel dizionario `FILTRI`, punto 11 del §1), con le regole del passo 5: volatilità e sessione neutre (`direction=0`, solo magnitudo o ora), trend direzionale con il suo `pair`; nessuna sempre vera o sempre falsa;
- con la strada B la **confidenza** del passo 5 non si costruisce sulla stessa griglia volatilità × trend (sarebbe la stessa domanda fatta due volte).

### 6.6 · Firme (nomi indicativi)

```python
# engine/atlante.py  (nuovo)
celle_atlante(df, direzione, assi=("vol_trend", "sessione"), extra=None) -> pd.DataFrame
        # una colonna di codici per asse; NaN dove lo stato non è ancora calcolabile
atlante(df_is, H, pip, costi, nomi=None, assi=..., extra=None, unita="bp",
        min_eventi=200, q=0.20, fuso=...) -> pd.DataFrame
        # una riga per entry × cella: eventi, scarto, t, p, bh, due_meta, passa, motivo
registra_filtri_cella(assi=..., extra=None) -> list[str]
        # i filtri CELLA_… per il passo 5, su richiesta

# engine/indicatori.py  (additivo)
volatilita_durata(df, ore=5, giorni=5) -> pd.Series     # su M15 = asse_volatilita(df, 20, 500)
sessione_principale(df) -> pd.Series                     # ASIA_NOTTE / EUROPA / LONDRA_NY / AMERICA

# engine/vetrina.py
atlante_dei_trigger(s)                 # schermata 3c
scegli_trigger(s, long=..., short=..., cella_long=None, cella_short=None)   # parametri in più
trova_strategia(s)                     # se c'è una cella scelta: strada B (solo celle)
```

### 6.7 · Cosa si vede (Lab, schermata 3c; ricerca, 1.3 ter)

- Per ogni trigger mostrato, una **mappa a colori**: righe = celle (4 volatilità × trend, 4 sessioni, 2 basis sui perpetual), colore = solidità dello scarto lordo dalla cella, in bp; accanto, il guadagno netto in bp. Le celle che passano tutti i controlli sono colorate; le altre grigie con il motivo («troppo pochi casi», «non supera la quota di falsi positivi», «non positiva in una metà», «non paga i costi»).
- Una tabella con tutte le entry che hanno almeno una cella che passa.
- Riquadro «Come leggerlo»: «Questa è una mappa: ti dice dove il trigger sembra funzionare, non che funziona. Se scegli una cella, al passo 5 verrà misurata come un filtro, con un'asticella alta perché tiene conto di tutte le celle che l'atlante ha guardato.»

### 6.8 · Collaudo

- Mercato finto con un vantaggio messo apposta solo in volatilità alta: il trigger è piatto in media, l'atlante accende quella cella e non le altre.
- Mercato finto con una deriva solo in una sessione e un trigger senza vantaggio: con il riferimento di cella lo scarto è nullo (come il collaudo della baseline oraria in `02`).
- 60 entry finte senza vantaggio su 8 celle: quante celle passano (atteso: in media al massimo q delle promosse sono finte).
- Lookahead per troncamento di tutte le colonne di stato; identità su M15 con `asse_volatilita` e `cella_contesto` (con la giornata UTC sui symbol da exchange); il minimo di 20 rendimenti su H4.
- Strada A identica a oggi nei due notebook vivi su BINANCE_PERP_BTCUSDT; giro completo con la strada B su BINANCE_PERP_BTCUSDT e BYBIT_SPOT_ETHUSDT (solo long).
- Soglia del passo 5 nella strada B: calcolata con il k dell'atlante, non con le righe del passo 5.

### 6.9 · Rischi

- **Poca potenza:** con k ≈ 480 il controllo dei falsi positivi è più severo della rosa, e al passo 5 la soglia è circa 3,87; un vantaggio condizionato piccolo non si vedrà. È il prezzo di non cercare a tappeto. Il mercato nullo (D2) e una prova di potenza come quella della rosa (`02`) lo misurano.
- **La tentazione di guardare tante mappe:** la regola «una cella, scelta con la regola scritta» e il riquadro servono a questo.
- **Complessità:** una schermata e un modulo nuovi. Con la strada A tutto resta come oggi.

---

## 7 · Lavoro D · Il mercato nullo

### 7.1 · Cosa produce

Per un symbol, un timeframe e un H: la distribuzione, su molti giri senza vantaggio, dei numeri con cui la pipeline arriva in fondo (t netto, P(EV<0), esito della scheda, filtro che «regge», celle che passano), e la **soglia empirica**: «nel nulla, la pipeline arriva a un t ≥ X nel 5% dei giri». Due serie di giri: **D1** con la strada A (filtri a tappeto), **D2** con la strada B (atlante).

### 7.2 · I due modi di costruire il nulla

| | come | cosa resta del mercato vero | pro | contro |
|---|---|---|---|---|
| **N1 · trigger casuali** | per ogni entry vera del catalogo, una entry finta con lo stesso numero di eventi, lo stesso lato e la stessa distribuzione per fascia oraria, su giornate scelte a caso | tutto: prezzi, costi, sessioni, regimi, quarantena | indicatori calcolati una volta sola (veloce); misura proprio «quanto il tool scambia la struttura del mercato per un trigger» | i filtri possono trovare effetti veri del mercato (un'ora, un regime) sopra un trigger finto: contano come «falsa scoperta del trigger», ed è giusto, ma va detto |
| **N2 · prezzi rimescolati a blocchi di una giornata** | le giornate (come candele M15 relative alla chiusura del giorno prima) si rimescolano con reinserimento | l'andamento **dentro** la giornata, profilo orario compreso (correzione al 62, §1 punto 16); spariscono trend di più giorni e volatilità che dura giorni | nessun vantaggio di più giorni può sopravvivere | indicatori, quarantena e calendario da ricostruire a ogni giro (+10–14 s); weekend e festivi del broker da trattare; i filtri a 500 barre vedono un mercato senza regimi, quindi più facile del vero |

**Decisione del 20/10: N1** per D1 e D2: risponde alla domanda pratica (il tool, sul mercato vero, quanto si inganna sui trigger?) ed è il più semplice. N2 dopo, se servirà. (Sulle crypto, 24/7, il problema di weekend e festivi del broker per N2 non c'è più.)

**Un limite di N1:** i trigger veri arrivano spesso a grappoli; quelli finti, su giornate a caso, molto meno. L'incertezza della rosa tiene già conto dei grappoli, quindi l'effetto è piccolo, ma lo scrivo nel risultato.

### 7.3 · La regola automatica delle scelte (al posto di Mattia, scritta adesso)

1. **Trigger:** il primo della rosa per lato; se la rosa è vuota (nel nulla succederà spesso), quello con il t netto più alto. È quello che farebbe un utente che va avanti comunque («la scelta resta libera», `02`).
2. **Uscite:** quelle predefinite di `imposta_uscite` (a tempo dopo H barre, stop adattivo al 90° percentile), nessuna regola d'uscita.
3. **Passo 5:** D1, il primo filtro che «regge» nella classifica, altrimenti il sistema base. D2, la cella proposta dall'atlante con la regola del §6.5 provata al passo 5; altrimenti il sistema base.
4. **Giudizio:** la scheda sull'in-sample; si registrano esito, t, P(EV<0), numero di trade. L'out-of-sample non si tocca mai.
5. **In più, il «migliore dei primi 3»** (§10.1 punto 5): nello stesso giro, anche il migliore fra i primi 3 trigger della rosa (stesse uscite, stesso passo 5), registrato in colonne a parte. Mostra quanto pesa provare più strade prima di scegliere.

**Come si legge (§10.1 punto 5): è un pavimento.** La regola automatica percorre una o tre strade per giro; nell'uso vero si provano più trigger e più uscite prima di scegliere. La soglia empirica è quindi il **minimo** dell'autoinganno, non la sua misura esatta.

### 7.4 · Quanti giri e quanto tempo

| giri | precisione della quota al 5% (± 1 errore standard) | tempo stimato N1 (65–70 s a giro, §2.4) | N2 (+10–14 s) |
|---|---|---|---|
| 200 | ± 1,5 punti | circa 4 ore | circa 4 ore e mezza |
| 500 | ± 1,0 punti | circa 9–10 ore (una notte) | circa 11–12 ore |

La ricerca dei filtri usa già i 6 processori: far girare più giri insieme non accelera. **Decisione del 20/10: 500 giri**, di notte, per D1 e D2 su **BINANCE_PERP_BTCUSDT e BINANCE_PERP_ETHUSDT** (due monete, così le soglie non si tarano su una sola; niente EURUSD). I tempi della tabella sono misurati su BINANCE_PERP_BTCUSDT (§2.4); il «migliore dei primi 3» aggiunge le uscite e il passo 5 di altri due trigger, quindi un giro dura circa il triplo: 500 giri per symbol e per strada diventano più notti, e si possono fare a tappe (ogni giro scrive una riga, si riprende da dove si è fermato). D1 su BTC può girare mentre si fa il lavoro B, ma senza il funding nei costi: si rifà dopo B.

### 7.5 · Firme e comando

```python
# engine/mercato_nullo.py  (nuovo)
trigger_casuali(df_is, nomi, seme) -> dict[str, np.ndarray]
prezzi_rimescolati(df, seme, blocco="giorno") -> pd.DataFrame        # N2, se approvato
giro_nullo(sessione_base, strada="A", seme=0) -> dict                # un giro, le scelte del §7.3
mercato_nullo(symbol, timeframe="M15", H=25, giri=500, strada="A", modo="N1") -> pd.DataFrame
soglia_empirica(tabella, colonna="t", quota=0.05) -> float
```

```
python mercato_nullo.py BINANCE_PERP_BTCUSDT --giri 500 --strada A
python mercato_nullo.py BINANCE_PERP_ETHUSDT --giri 500 --strada B
```

Risultato in `dati/nullo/<SYMBOL>_<TF>_H<H>_<strada>.csv` (non va su GitHub), con in testa la versione del catalogo (numero di condizioni) e la data.

### 7.6 · Cosa si vede

- Dal terminale: una tabella riassuntiva (quanti giri arrivano a «DA VALUTARE», la soglia empirica di t, il confronto D1 contro D2, la regola del §7.3 accanto al «migliore dei primi 3»).
- Nel Lab crypto e nella ricerca, sotto la scheda strategia, **una riga**: «Nel mercato nullo di questo symbol (500 giri, strada B), un t così alto capita almeno nel N% dei giri.» (la soglia è un pavimento, §7.3; resta informativa, §10.2 domanda 17) Se il file non c'è, o il catalogo è cambiato: «mercato nullo non ancora calcolato per questo symbol e questo catalogo».

### 7.7 · Collaudo

- Trigger casuali: stesso numero di eventi, stessa distribuzione oraria e di lato del trigger vero; nessun evento in quarantena.
- Su un mercato finto senza vantaggio e con le soglie note, la quota di giri «promossi» torna con quella attesa (`21`, sezione E, entry casuali: circa 5 su 100 alla soglia di rumore).
- Riproducibilità: stesso seme, stessi giri.
- Un giro nullo con il trigger vero al posto di quello finto riproduce esattamente il Lab.

### 7.8 · Rischi

Il tempo di calcolo; la tentazione di leggere la soglia empirica come una promozione (resta informativa, §1 punto 3) o come la misura esatta dell'autoinganno (è un pavimento, §7.3); il nulla N1 non è il nulla assoluto (lo dice il §7.2).

---

## 8 · Ordine, rami, documenti

Ordine deciso il 20/10 (§10.2 domanda 19):

0. **Perimetro** · ramo `perimetro-solo-crypto` — `CLAUDE.md`, `docs/00`, riga «sospeso» in testa al Lab broker (§10.0). **Fatto il 20/10.**
1. **Giornata delle crypto a 00:00 UTC** · ramo piccolo a parte (§10.1 punto 3) — ATR, `gap_trend`, F36, F39, `giorno_fx` sui symbol da exchange. Cambiano i numeri del Lab crypto, money management compreso; sul broker nulla.
2. **A** · ramo `unita-di-rischio` — U1, poi U2 (§4.2).
3. **B** · ramo `funding-perpetual` — costi giusti prima di misurare sulle crypto; la basis serve all'atlante.
4. **D1** · ramo `mercato-nullo` — la taratura della pipeline di oggi (su BTC può girare di notte mentre si fa B; si rifà dopo B).
5. **C** · ramo `atlante-trigger`.
6. **D2** · sullo stesso ramo del mercato nullo o su uno nuovo — il confronto.

Ogni lavoro: OK di Mattia → codice → collaudo → tutti i `test_*.py` (anche quelli del broker) → identità dei due notebook vivi su BINANCE_PERP_BTCUSDT e giro su BYBIT_SPOT_ETHUSDT → commit → Pull request (il Merge lo fa Mattia).

**Documenti da aggiornare con i lavori:** `00` (metodo: passo 2 con l'atlante, passo 5 con le due strade; «Cosa manca» punto 3); `02` (le unità, una sezione sull'atlante e una sul mercato nullo; la riga `deduci_pip` superata); `50` §12 (funding nei dati e nei costi). `CLAUDE.md` (la funzione di ccxt in più) è già aggiornato con il perimetro.

---

## 9 · Domande per Mattia

**Unità (A)**
1. **U1 adesso** e U2 da decidere dopo la tabella di confronto pips/bp su EURUSD e BTC (consigliato), oppure U2 subito? U3 lo sconsiglio.
2. Il nome della seconda unità: «ATR» (consigliato, per non confonderla con R del money management)?
3. Sulle crypto la giornata è oggi 17:00 New York in ATR, `gap_trend`, F36, F39, e mezzanotte UTC nel profilo orario ed E41. Per ora si tiene così (consigliato: l'ATR resta quello del money management), e la scelta della giornata crypto si decide a parte?

**Funding (B)**
4. Posso aggiungere `fetch_funding_rate_history` (pubblica, sola lettura) all'elenco delle funzioni ccxt ammesse in `CLAUDE.md`?
5. Regola del pagamento: liquidazioni con `ingresso < S ≤ uscita` per i trade, prezzo in S = Open della barra (consigliato)?
6. Open interest scartato (non c'è su Binance), riapribile: d'accordo?

**Atlante (C)**
7. Celle: griglia volatilità × trend 2 × 2 **più** sessione a parte (8 celle per lato; consigliato), oppure tutto incrociato (16, quasi sempre sotto il minimo)? Minimo 200 eventi per cella (come la rosa; consigliato) o 100?
8. Finestre come **durate** (5 ore, ~5 giorni), identiche a `confidenza.py` su M15 (consigliato)?
9. Le quattro sessioni del §6.2 (ASIA_NOTTE, EUROPA, LONDRA_NY, AMERICA) vanno bene?
10. Sulle crypto le stesse sessioni in ora locale (consigliato) o fasce UTC fisse?
11. Scarto **netto** dei costi nell'atlante, con la rosa che resta lorda (consigliato), oppure lordo anche nell'atlante, per avere una sola convenzione?
12. Variabile dei perpetual: **basis** alta/bassa alla mediana mobile (consigliato) o funding con la soglia «premio positivo»?
13. Regola di scelta: **una cella per lato** (consigliato) o tutte le celle che passano dello stesso asse?
14. Convivenza con il passo 5: **C4** (consigliato), C1, C2 o C3?
15. L'atlante misura tutte le entry vere (consigliato, §6.1), e non solo quelle della rosa: d'accordo?

**Mercato nullo (D)**
16. Modo **N1** (trigger casuali; consigliato) e N2 dopo, se lo vuoi? **500 giri** (consigliato) o 200? Symbol: EURUSD e BINANCE_PERP_BTCUSDT?
17. La soglia empirica resta **solo informativa** (consigliato), oppure in futuro potrà anche bocciare?
18. La regola automatica delle scelte del §7.3 va bene?

**Ordine**
19. Ordine A, B, D1, C, D2 con un ramo per lavoro (consigliato)? Si comincia da A?

## 10 · Decisioni di Mattia (20/10/2026)

Rilettura della proposta con Claude (chat del Project, 20/10). Prima la decisione sul perimetro (§10.0), poi le correzioni di metodo (§10.1) e le risposte alle 19 domande (§10.2).

### 10.0 · Perimetro: solo crypto ed exchange (decisione del 20/10)

**MT5 e il lato broker (CFD) si sospendono, per ora.** Il tool si concentra solo sui symbol da exchange (Binance, Bybit; spot e perpetual).
- **Niente si cancella:** codice, test, notebook e dati del broker restano nel repo e si possono riaprire.
- **Congelati:** `Trading_System_Lab.ipynb` (broker) e i download da MT5 (`scarica_dati.py`). Non si aggiornano più insieme agli altri due notebook. In testa al Lab broker va una riga: «sospeso dal 20/10/2026, non mantenuto».
- **Restano vivi e allineati:** `Trading_System_Lab_Crypto.ipynb` e il notebook di ricerca, usato sui dati da exchange.
- **Dataset di sviluppo e prova di identità:** non più EURUSD. Il riferimento diventa **BINANCE_PERP_BTCUSDT** (storico più lungo, dal 2/1/2020, long e short). Il giro completo «su un symbol diverso» diventa **BYBIT_SPOT_ETHUSDT**: altro exchange, spot (solo long), altra moneta, quindi copre i casi che il primo non copre.
- **Le suite `test_*.py` si lanciano tutte, come prima.** Quelle sui symbol del broker non chiedono MT5 e devono continuare a passare: se una modifica le rompe, è un segnale che si è toccato codice condiviso.
- Si aggiornano `CLAUDE.md` e `docs/00` (scopo, dataset di sviluppo, symbol in uso).

### 10.1 · Correzioni alla proposta

**1 · Strada B (C4): le prove non diventano 8–10.** La cella si sceglie guardando l'atlante, che sull'in-sample ha confrontato circa 480 celle. Il passo 5 la riprova **sugli stessi dati**: non è una validazione indipendente, ma una seconda misura dello stesso effetto. Le prove vere sono quelle dell'atlante, non le 8–10 del passo 5. Quindi:
- C4 resta il flusso (l'atlante propone, il passo 5 misura con tenuti contro scartati e due metà);
- nella strada B la soglia di rumore del passo 5 si calcola con **k = celle misurate nell'atlante** (con k ≈ 480 la soglia di Šidák è circa 3,87), non con le 8–10 righe del passo 5 (2,73–2,80). La frase del §3 «senza perdere severità, perché le prove sono davvero di meno» va tolta;
- il giudice finale di quanto si inganna la strada B è il mercato nullo D2, che ripete **tutta** la catena atlante + passo 5.

**2 · Finestre come durate: serve un minimo di barre.** Su H1 «5 ore» sono 5 rendimenti, su H4 poco più di 1: la deviazione non si calcola, o è solo rumore. Regola: durata **con un minimo di 20 rendimenti** (su M15 restano esattamente 20 e 500 barre; su H1 e H4 la finestra si allunga fino al minimo). Il collaudo verifica l'identità su M15 e il minimo su H4.

**3 · La giornata delle crypto si decide adesso, non dopo.** Unità ATR (lavoro A) e asse del trend dell'atlante (`gap_trend`, giornata del VWAP) dipendono dalla giornata. Sulle crypto le 17:00 di New York non hanno un motivo di mercato (24/7, funding alle 00:00 UTC, candele giornaliere degli exchange a mezzanotte UTC). Decisione: **sui symbol da exchange la giornata è 00:00 UTC ovunque** (ATR, `gap_trend`, F36, F39, `giorno_fx` o la sua versione crypto). È un ramo piccolo a parte, **prima di A**. Cambiano i numeri del Lab crypto (money management compreso): va bene, è nato il 19/10. Sui symbol del broker non cambia niente: il codice resta, sospeso (§10.0).

**4 · Atlante: due domande, due colonne.** Domanda 11 risolta così:
- **scarto dal mercato della cella, lordo**: stessa convenzione della rosa, risponde a «il trigger aggiunge qualcosa al mercato?». Decide BH e due metà;
- **guadagno netto del trigger nella cella, in bp** (costi e funding tolti): risponde a «paga i costi?». Cancello in più: deve essere maggiore di zero.
Una cella passa se supera tutte e due. Niente convenzioni mescolate in un solo numero.

**5 · Mercato nullo: è un pavimento.** La regola automatica (§7.3) percorre una sola strada per giro. Nell'uso vero si provano più trigger e più uscite prima di scegliere. La soglia empirica va quindi letta come il **minimo** dell'autoinganno. Da aggiungere al risultato: oltre alla strada del §7.3, il migliore fra i primi 3 trigger della rosa (stesse uscite), così si vede quanto pesa provare più strade.

### 10.2 · Risposte alle domande

| # | decisione |
|---|---|
| 1 | **U1 come primo commit** (identità), **U2 subito dopo**: con il perimetro solo crypto (§10.0) il bp è l'unità che decide. La tabella di confronto pips/bp si fa su BINANCE_PERP_BTCUSDT e BYBIT_SPOT_ETHUSDT, solo per documentare quanto cambia. U3 non serve più. I pips restano visibili accanto (sulle crypto 1 pip = il passo della tabella `SIMBOLI_EXCHANGE`, es. 1 $ su BTC). I costi delle crypto sono in % del prezzo: si mostrano in bp con la conversione in pips accanto. |
| 2 | Sì, «ATR». |
| 3 | No al rinvio: vedi §10.1 punto 3 (00:00 UTC sui symbol da exchange, ramo prima di A). |
| 4 | Sì, `fetch_funding_rate_history` va nell'elenco di `CLAUDE.md`. `fetch_open_interest_history` non serve più (punto 6). |
| 5 | Sì: `ingresso < S ≤ uscita`, prezzo in S = Open della barra, approssimazione del prezzo «mark» dichiarata. |
| 6 | Sì, open interest scartato, riapribile. |
| 7 | 2 × 2 più sessione a parte (8 celle per lato). Minimo 200 eventi. |
| 8 | Sì, durate, con il minimo di 20 rendimenti (§10.1 punto 2). |
| 9 | Sì, ASIA_NOTTE, EUROPA, LONDRA_NY, AMERICA. |
| 10 | Stesse sessioni in ora locale anche sulle crypto. |
| 11 | Vedi §10.1 punto 4: scarto lordo + guadagno netto > 0, due cancelli. |
| 12 | Basis alta/bassa alla mediana mobile. |
| 13 | Una cella per lato. |
| 14 | C4, con la soglia del passo 5 a k = celle dell'atlante (§10.1 punto 1). |
| 15 | Sì, tutte le entry vere. |
| 16 | N1, 500 giri, **BINANCE_PERP_BTCUSDT e BINANCE_PERP_ETHUSDT** (due monete, così le soglie non si tarano su una sola). Niente EURUSD. N2 dopo, se serve. |
| 17 | Solo informativa. |
| 18 | Sì, più il «migliore dei primi 3» (§10.1 punto 5). |
| 19 | Ordine: **perimetro** (§10.0: `CLAUDE.md`, `docs/00`, riga in testa al Lab broker) → **giornata crypto** → A → B → D1 → C → D2, un ramo ciascuno. D1 su BTC può girare di notte mentre si fa B (i costi del funding non ci sono ancora: si rifà dopo B). Si comincia dal perimetro. |