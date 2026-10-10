# 10 · Fuso orario del broker — conclusione verificata
 
**Data verifica:** 20 settembre 2026
**Dati usati:** EURUSD M15 e BTCUSD M5, IC Markets, 2020 → settembre 2026
**Stato: chiuso.** Regola stabilita, dati validati, `to_utc_index()` operativo.
 
---
 
## Conclusione operativa
 
Il server IC Markets espone i timestamp in **ora di New York + 7 ore, seguendo il
calendario DST statunitense** (non quello europeo).
 
In pratica: GMT+3 quando negli USA è in vigore l'ora legale, GMT+2 altrimenti.
I cambi avvengono la seconda domenica di marzo e la prima domenica di novembre.
 
Regola confermata nel modulo `broker_tz_diagnostic.py` come `"A_US_DST (NY+7h)"`.
 
---
 
## Perché è importante
 
Le sessioni di indici e futures sono definite in **ora locale della borsa**
(NYSE 9:30–16:00 ET, Eurex 9:00–17:30 CET, ecc.), che è fissa tutto l'anno.
L'ora *broker* corrispondente invece **si sposta di un'ora a ogni cambio DST**.
 
Un filtro scritto come "ora broker ≥ 15:30" per intercettare l'apertura di New York
funziona solo per metà anno. Non genera errori, non fa crashare nulla: falsa il
backtest in silenzio. È esattamente il motivo per cui la regola andava provata e
non assunta.
 
---
 
## Risultato della diagnostica
 
Su EURUSD M15, 2020-01-06 → 2026-09-11, 354 settimane.
 
| Ipotesi | Match | Apertura settimanale in ora NY |
|---|---|---|
| **A_US_DST (NY+7h)** | **97.2%** | Sun 17:00 |
| B_EU_DST (Europe/Athens) | 90.4% | Sun 17:00 |
| D_fisso GMT+3 | 65.5% | Sun 17:00 |
| C_fisso GMT+2 | 31.9% | Sun 18:00 |
 
### Come leggere il margine
 
Il margine di A su B è **6.8 punti**, e non è rumore: è la firma attesa.
 
I cambi DST americano ed europeo sono sfasati di ~3 settimane a marzo e ~1 a
ottobre/novembre, cioè ~4 settimane l'anno. Su 6.7 anni fanno ~27 settimane, il
7.6% del campione. Il margine osservato (6.8%) coincide. **Sono proprio quelle
settimane, e solo quelle, a distinguere le due ipotesi.**
 
Conseguenza pratica: con meno di un anno di storico la diagnosi è indistinguibile
tra A e B. Lo script lo rileva e stampa `DIAGNOSI AMBIGUA` invece di dare una
risposta falsamente sicura.
 
---
 
## Insidia metodologica — criterio di scelta
 
Il primo criterio tentato era *"la regola vera è quella che produce l'ora di
apertura più costante"*. **È sbagliato.** Un offset fisso errato produce un'ora
altrettanto costante, solo traslata: vedi ipotesi C, che apre regolarmente a
`Sun 18:00`.
 
Il criterio corretto confronta il **valore atteso** (domenica 17:00 ora di New
York), non la costanza. L'errore è emerso dal test di validazione sintetico, non
dalla lettura del codice.
 
Nota sulle barre MT5: sono etichettate con l'ora di **apertura**, quindi su M15
l'ultima barra del venerdì è `16:45` NY, non `17:00`.
 
---
 
## Anomalie nei dati EURUSD — tutte spiegate
 
Delle 354 settimane, 11 non aprono domenica alle 17:00 NY.
 
**10 sono riaperture dopo Natale e Capodanno.** In 8 casi l'ora NY resta
esattamente `17:00` e cambia solo il giorno della settimana — il che *conferma*
la regola invece di contraddirla. Due settimane festive aprono alle 18:00 NY e
una alle 17:15: ritardo operativo del broker.
 
**1 è un buco reale nello storico:**
 
```
2021-12-02 16:30 (ora server) — gap di 6h15m
```
 
Giovedì qualunque, nessuna festività: mancano ~25 barre M15.
 
**Decisione presa: conviverci.** Un buco isolato di 6 ore su 6 anni e 8 mesi è
irrilevante per la statistica aggregata; tagliare lo storico pre-2022 per
eliminarlo costerebbe due anni di campione. Da ricordare solo se un risultato
anomalo si concentrasse in quella settimana.
 
---
 
## Simboli 24/7 (cripto) — le barre dei cambi d'ora
 
Verificato il 20/9/2026 su BTCUSD M5 (2020-01-02 → 2026-09), che sollevava
`82 timestamp non convertibili`.
 
### Cosa NON è
 
L'ipotesi iniziale era che MT5 producesse **timestamp duplicati** all'ora ripetuta
di novembre, risolvibili con `ambiguous="infer"`. **Smentita dai dati**: l'indice
reale ha **zero duplicati** e la finestra critica è continua, senza ripetizioni.
 
Il terminale **sovrascrive** l'ora ripetuta invece di conservare entrambe le
passate. Le etichette restano pulite, ma un'ora di mercato reale è persa o fusa.
 
Scartati anche due criteri alternativi, verificati empiricamente:
 
- **"ordine delle righe"** (prima riga = prima passata): sbagliato. Se a mancare
  sono le barre della prima passata, marca come ora legale una barra che è ora
  solare.
- **"monotonia"** (scegliere la lettura che tiene l'UTC crescente): corretto in
  3 scenari su 4, fallisce quando di un timestamp sopravvive una sola barra —
  che è esattamente il caso reale.
### Cosa è
 
Le barre nei cambi d'ora sono **genuinamente indeterminate**: l'informazione non
esiste più nei dati. Due categorie distinte, entrambe irrecuperabili.
 
| | Novembre | Marzo |
|---|---|---|
| Fenomeno | l'ora torna indietro e si ripete | l'ora salta in avanti |
| Effetto | non si sa a quale passata appartiene la barra | l'etichetta punta a un'ora che in ora di borsa non esiste |
| Conteggio (BTCUSD M5) | **esattamente 12/anno** | 1–7/anno, irregolare |
| Natura | sistematico | artefatto del feed del broker |
 
Distribuzione reale, 82 barre su ~700.000 (**0.012%**):
 
```
2021  3: 4    11: 12
2022  3: 2    11: 12
2023  3: 7    11: 12
2024  3: 6    11: 12
2025  3: 1    11: 12
2026  3: 2
```
 
L'irregolarità di marzo indica che attorno al cambio di primavera l'orologio del
server e la marcatura delle barre non sono perfettamente sincronizzati.
 
### Soluzione adottata
 
Parametro `on_dst_gap` di `to_utc_index()`:
 
- `"raise"` (**default**) — solleva un errore invece di perdere dati in silenzio.
- `"drop"` — scarta le barre indeterminate e **stampa quante e quando**, così la
  perdita resta visibile e tracciata.
Motivazione dello scarto: 0.012% delle barre, tutte all'una di notte di New York
di una domenica di novembre o dentro un'ora di marzo che non esiste. Il rischio
residuo è un trade aperto che attraversi quel momento, una volta l'anno — contro
cui comunque non esisterebbe alternativa migliore.
 
`ambiguous="infer"` è stato **rimosso** dal default: su dati reali fallisce, e un
default che fallisce è peggio di nessun default.
 
### Limite noto
 
`diagnose_broker_offset()` **non funziona sui simboli 24/7**: individua le
settimane dal buco del weekend, che sulle cripto non esiste. Non è un problema
pratico — la regola del fuso è una proprietà del *server*, non del simbolo, e si
stabilisce una volta su un simbolo forex.
 
---
 
## Qualità dello storico BTCUSD — verificata e chiusa
 
### Orari di contrattazione cambiati nel tempo
 
Conteggio barre per giorno della settimana:
 
| Anno | sabato | domenica |
|---|---|---|
| 2020 | **0** | 552 |
| 2021 | 3386 | 4807 |
| 2022 | 4597 | 4983 |
| 2023+ | ~4950 | ~5000 |
 
**Nel 2020 BTCUSD non trattava nel weekend.** La contrattazione del sabato è
partita nel 2021 e si è stabilizzata dal 2023.
 
**Conseguenza da ricordare:** qualunque filtro di sessione sulle cripto tarato sui
dati recenti *non descrive* il 2020–2021. Da tenere presente nella validazione
In-Sample / Out-of-Sample: i due periodi hanno strutture temporali diverse.
 
Spiega anche perché novembre 2020 non ha barre indeterminate: quella domenica
notte il mercato era chiuso, come sul forex.
 
> Nel 2026 è emerso un secondo fatto: **BTCUSD non è davvero 24/7 nemmeno oggi**
> — il venerdì alle 17:00 NY la contrattazione si ferma per tre barre. Dettagli in
> `11_DATI_QUARANTENA.md`.
 
### Densità e buchi
 
Copertura oraria uniforme su tutte le 24 ore: ~4380 barre per ora all'anno
(= 365 × 12), coerente con M5 completo.
 
Spaziatura fra barre consecutive:
 
```
00:05:00    660.646     nominale
00:10:00      1.698     barra singola mancante (0.26%)
00:55:00        169     interruzione ~1h
01:15:00         57     interruzione ~1h
07:10:00         56     interruzione ~7h
```
 
**Giudizio: dati integri.** I buchi sono verosimilmente manutenzioni del broker,
in quantità irrilevante per la statistica aggregata. Nessuna azione richiesta.
 
---
 
## Nota — EURUSD nei festivi USA
 
EURUSD presso un broker CFD stampa candele il 4 luglio e a Thanksgiving. Le
quotazioni **non sono sintetiche**: il mercato interbancario valutario è globale
e decentralizzato, e tratta davvero nei festivi americani. Chiudono le borse USA,
non il forex.
 
Quello che cambia è la **liquidità**, che si assottiglia parecchio.
 
Distinzione operativa: essendo prezzi reali ma sottili, escluderli o no è una
decisione di *strategia*, non di pulizia dati.
 
---
 
## Problema aperto — etichetta UTC fantasma
 
Da qualche parte nella pipeline (**non** in `mt5_interaction.py`, che produce
correttamente un indice naive) viene applicato un `tz_localize('UTC')`.
 
L'indice risulta `datetime64[ns, UTC]` ma i valori sono ora server. Prova:
l'ultima barra del venerdì 18/9/2026 è alle `23:30`, coerente con GMT+3;
se fosse davvero UTC sarebbe alle `20:45`.
 
**Finché nessuno converte, è innocuo.** Il giorno in cui un pezzo di codice
facesse `tz_convert('America/New_York')` fidandosi di quell'etichetta,
sposterebbe tutto di 2–3 ore senza errori e senza avvisi.
 
Da individuare e rimuovere alla fonte. Nel frattempo `verifica_indice_utc()` in
`engine/quarantena.py` lo intercetta.
 
---
 
## Procedura per ogni nuovo download
 
MT5 restituisce **sempre** ora server, a ogni download. Non è un difetto: è il
formato grezzo. La conversione va fatta una volta sola, subito dopo il caricamento.
 
```python
from engine.broker_tz_diagnostic import to_utc_index
 
# 1. togli l'etichetta UTC fantasma, se presente
if df.index.tz is not None:
    df.index = df.index.tz_localize(None)
 
# 2. converti in UTC con la regola confermata
df = to_utc_index(df, "A_US_DST (NY+7h)")                      # forex
df = to_utc_index(df, "A_US_DST (NY+7h)", on_dst_gap="drop")   # cripto
 
# 3. controlla che l'indice sia UTC vero
from engine.quarantena import verifica_indice_utc
verifica_indice_utc(df)
```
 
Sul forex il default `"raise"` va bene: in quei momenti il mercato è chiuso e non
c'è nulla da scartare. Sulle cripto serve `"drop"`.
 
Da lì in poi l'indice è UTC reale e l'ora di qualunque borsa si ricava
su richiesta con `df.index.tz_convert("America/New_York")`, con il DST
gestito da pandas.
 
**La diagnostica non va rilanciata a ogni download.** Serve solo se cambi broker,
server, o se il broker modifica la propria politica di fuso.
 
---
 
## File collegati
 
- `engine/broker_tz_diagnostic.py` — diagnostica + `to_utc_index()`
- `test_broker_tz.py` — suite di validazione (12/12 passati, forex + 24/7)
## Prossimi passi
 
1. **Festivi di borsa**: EURUSD stampa candele il 4 luglio e a Thanksgiving, ma
   NYSE è chiusa. Un filtro di sessione basato solo sull'orario accenderebbe
   segnali in giornate senza sessione. Scelta da fare: `pandas_market_calendars`
   (preciso, una dipendenza in più) oppure lista di festivi a mano (zero
   dipendenze, da mantenere). **Ancora aperta.**
2. ~~Due primitive per le condizioni temporali~~ — **fatte**: `in_session_window`
   e `bars_after_open` esistono come `in_sessione()` e `barre_da_apertura()` in
   `engine/sessioni.py`. Vedi `11_DATI_QUARANTENA.md`.