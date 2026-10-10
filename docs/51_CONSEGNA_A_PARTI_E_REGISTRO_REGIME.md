# 51 · Consegna "a parti" e registro dei filtri di regime (9/10/2026)
 
**Data:** 9 ottobre 2026
**Cosa è:** aggiunta a `50_IDEE_DA_ARTICOLI.md`. **Dove questo documento e 50 dicono cose diverse, vale questo.**
 
---
 
## 1 · Regola di consegna (sostituisce §1 passo 5 e §9 di 50, su richiesta di Mattia del 9/10)
 
**Non si riscrive il file intero.** Per ogni file già esistente nel repo Claude consegna:
- il blocco di codice da aggiungere o sostituire;
- **dove** va (il nome del file, la riga o la funzione "subito prima / dopo", con l'indentazione);
- se è una sostituzione, la riga vecchia da cercare e quella nuova.
Il **file intero** si consegna solo (a) se è un file nuovo (es. `test_*.py`), (b) se le modifiche sono così sparse che le parti sarebbero più rischiose del file. In questo caso Claude lo dice e ne spiega il motivo.
 
Ogni consegna include sempre, per un lettore non informatico: l'elenco numerato degli interventi, il comando per eseguire i test, l'ultima riga attesa (`RISULTATO: n/n test superati`) e cosa fare se il numero non torna (incollare l'output, non modificare niente).
 
**Frase sostitutiva per `GUIDA_ANALISI_FONTI.md` §8, passo 1** (la guida è nel repo: va incollata da Mattia):
> 1. Applica gli interventi indicati da Claude, file per file, nel punto indicato (di norma sono poche righe da aggiungere o sostituire: il file intero si riscrive solo se Claude lo chiede esplicitamente). I file nuovi (es. `test_*.py`) si caricano interi nella cartella principale.
 
---
 
## 2 · Registro: articoli letti il 9/10/2026 (da aggiungere a §10 di 50)
 
| n | tipo | letto il | fonte | idea | candidati | esito |
|---|---|---|---|---|---|---|
| 5 | articolo | 9/10/2026 | PyQuantLab, «Can We Detect a Market Crash Before It Happens? I Tested 5 Regime Filters», 7/9/2026 | Choppiness Index (14 barre, standard di Dreiss, non il 7 dell'articolo) + stato con isteresi (si accende al 25° percentile, si spegne sopra il 50°) | F25_CHOP_TREND, F25_CHOP_RANGE (neutri) | approvata 9/10; superato; 2 prove |
| 6 | articolo | 9/10/2026 | PyQuantLab, «Enhancing Trading Strategies With a Hurst-Based Regime Filter», 6/3/2026 | persistenza del prezzo come filtro; sostituito l'esponente di Hurst (R/S per barra, pesante, rumoroso) col **variance ratio** di Lo–MacKinlay (orizzonte 4, finestra 192) | F26_VARIANCE_RATIO_TREND (neutro) | variante approvata da Mattia; superato; 1 prova |
| 7 | articolo | 9/10/2026 | PyQuantLab, «Regime Filtered Trend Strategy», 12/7/2025 | voto fra misure di regime | idea del voto riusata in F27 | F27 **opzionale**, riga nel dizionario commentata; +1 prova solo se attivata |
| 8 | articolo | 9/10/2026 | Kaabar, VA-RSI (Volatility-Adjusted RSI), Medium/Coinmonks | RSI aggiustato per volatilità | — | **messo da parte** (non scartato): troppo reattivo; la EMA di lisciatura aggiungerebbe ritardo su ritardo |
| 9 | articolo | 9/10/2026 | articolo Mellin (trasformata) | — | — | scartato: FFT per barra, nessuna regola in condizione |
 
Non letti per scelta di Mattia: articoli su HMM / UMAP (modelli addestrati: rischio lookahead e calcolo pesante). Restano in elenco in `GUIDA_ANALISI_FONTI.md` §11.2 (Range Index, Vertical Horizontal Filter, change point bayesiano…).
 
**Prove da fonti testuali:** 14 → **17** (F25 trend, F25 range, F26). **18** se si attiva F27.
 
---
 
## 3 · Come funzionano i tre filtri (per decidere senza codice)
 
- **F25 CHOP (14 barre).** Misura quanto il prezzo va a zig-zag. "Tendenza" = choppiness nel 25% più basso delle ultime 500 barre; "laterale" = nel 25% più alto. Con isteresi: resta acceso finché non rientra sopra il 50° (tendenza) / sotto il 50° (laterale). Mai veri insieme.
- **F26 variance ratio (1 ora, finestra 2 giorni).** Sopra 1 = i movimenti tendono a proseguire. Stato acceso al 75° percentile (ultime 1000 barre), spento sotto il 50°.
- **F27 composito (opzionale).** Almeno 2 voti su 3 fra CHOP-tendenza, VR-persistenza e ADX alto. Le tre misure sono poco correlate (0,02–0,17 su EURUSD): il voto è un consenso fra orizzonti diversi, senza altro ritardo.
**Limiti emersi dalle misure su EURUSD (onesti):**
- CHOP a 14 barre resta reattivo anche con l'isteresi: durata mediana di uno stato ≈ 10 barre (~2,5 ore), circa 10.000 cambi su 167.000 barre.
- Il VR è molto più lento: mediana ≈ 66 barre (~16 ore).
- F27 è dominato da CHOP e ADX (mediana 10 barre).
- Se serve un regime più stabile: variante con CHOP a 48 barre (+1 prova), da decidere.
---
 
## 4 · Collaudo eseguito (9/10/2026)
 
- `test_regime.py` (nuovo): 41/41 con pandas 3.0.5 e con pandas 2.2.3 (indicatori confrontati con riscrittura indipendente barra per barra, due trappole di lookahead riconosciute, isteresi verificata a mano, indipendenza dal punto di partenza dopo 3000 barre).
- Suite esistenti: test_idee_articoli 64/64 (dopo aggiornamento del controllo C7, che vietava i numeri F25–F27 ora riusati), barre_per_lato 24, confidenza 34, entry_composita 39, entry_metro 22, filtri_tempo 25, inversione 25, montecarlo 17, portabilita 13, quarantena_trade 23, sessioni 20, tempo_prezzo 20, vetrina 55, vetrina_trigger 26.
- Sovrapposizioni: `diagnostica.sovrapposizioni` **non esiste in V4**; controllo fatto con uno script a parte. 9 coppie ≥70%, quasi tutte contro filtri molto larghi (F22 80%, F2_MID 75%) con correlazione ≈0: attese per caso.
- Da fare da Mattia: `Collaudo_Catalogo.ipynb` su Colab (riavviare il runtime prima).
---
 
## 5 · Decisioni aperte
 
1. Attivare F27 composito? (+1 prova)
2. Variante CHOP lenta (48 barre)? (+1 prova)
3. Leggere gli articoli VHF / Range Index di `GUIDA_ANALISI_FONTI.md` §11.2?
 