# 11 · Quarantena e sessioni — gli strati di base del tempo
 
**Data:** 21–22 settembre 2026
**Prima di questo:** `00_SCOPO_E_STATO.md` e `10_DATI_FUSO_BROKER.md`
**A valle:** `20_CONDIZIONI_TEMPO.md`
 
**File:** `engine/quarantena.py`, `engine/sessioni.py`, `entry_metro.py`,
`test_sessioni.py` (20/20), `test_entry_metro.py` (22/22)
 
---
 
## Cosa aggiungono al tool
 
Due strati di base su cui poggia ogni condizione temporale:
 
1. **La quarantena** — quali barre il tool non deve usare, e perché.
2. **Le sessioni** — un catalogo di orari di borsa in ora locale, con due
   primitive (evento e filtro) da cui si costruiscono condizioni.
Più `entry_metro.py`, cinque ingressi puramente temporali che servono da
**righello** per leggere le condizioni vere.
 
---
 
## La colonna `spread`: cosa contiene davvero
 
Su EURUSD M15 solo **7.243 righe su 167.219** (4,3%) hanno `spread != 0`.
Sembrava un dato inutilizzabile. Non lo è: è lo **spread MINIMO della barra**,
e su un conto Raw Spread il minimo è zero quasi sempre.
 
Raggruppando per ora di New York, la concentrazione è netta:
 
| Barra (ora NY) | quota con spread≠0 | spread min mediano |
|---|---|---|
| fino a 16:30 | 0,5–0,9% | 2 punti |
| **16:45** | **22,6%** | 5 punti |
| **17:00** | **91,1%** | 12 punti |
| **17:15** | **92,4%** | 14 punti |
| **17:30** | **92,8%** | 11 punti |
| **17:45** | **92,6%** | 11 punti |
| 18:00 | 1,8% | 2 punti |
 
Per anno la quota sale dal 4,0% (2020) al 5,2% (2026) e lo spread minimo
medio da 9,5 a 21,8 punti.
 
**Trattandosi del minimo, questi numeri sono un limite inferiore.** Nelle
barre 17:00–17:45 lo spread è stato di almeno **1,0–1,25 bp** (11–14 punti)
per *tutti* i 15 minuti.
 
Su BTCUSD lo spread mediano è **895 punti = 8,95 USD**, con il 74,7% di barre
non nulle — un regime diverso, da tenere presente nei costi.
 
### Perché questo diventa una regola del tool
 
Le barre MT5 sono costruite sul **bid**. Al rollover il bid scende per
l'allargamento dello spread e poi risale quando rientra, anche a prezzo di
mercato fermo. Qualunque misura presa lì — un rendimento, un massimo, un
minimo — è deformata.
 
> **Regola: intorno al rollover i prezzi bid non sono affidabili.** Nessun
> segnale deve nascere o chiudersi lì, e nessun livello di prezzo va calcolato
> includendo quelle barre.
 
È il motivo per cui esiste lo strato 1. Il caso storico che l'ha fatta emergere
è `T1_ASIA` della V3, che entrava esattamente alle 17:00 NY.
 
---
 
## Strato 1 — `engine/quarantena.py`
 
### `verifica_indice_utc(df)`
 
Si ferma se l'indice non è UTC vero. Difende dall'**etichetta UTC fantasma**
(problema aperto in `10_DATI_FUSO_BROKER.md`): un indice marcato UTC che
contiene ora server. Non è la rimozione alla fonte, ma impedisce che il
difetto si propaghi.
 
Criterio: le prime barre dopo la pausa del weekend devono cadere **domenica
alle 17:00 NY**. Su EURUSD: 97,2% di 354 riaperture. Sotto l'80% solleva
errore con le istruzioni per correggere. Sui simboli 24/7 avvisa e prosegue.
 
### `quarantena(df, rollover=("16:45","18:00"))`
 
Tre colonne booleane sullo stesso indice: `rollover`, `dopo_interruzione`,
`totale`.
 
La finestra **non è una stima prudente: è misurata** dalla tabella sopra.
Usa la sovrapposizione e non "inizia dentro", così regge qualsiasi timeframe
(su H1 marca anche la barra delle 16:00, che contiene le 16:45).
 
Collaudo su EURUSD 2020–2026: **5,20% delle barre**, di cui 8.691 di rollover
e 357 dopo un'interruzione. La finestra cattura il **94,0%** delle barre con
spread anomalo costando il 5,2% dello storico — prova di coerenza indipendente
fra due misure che non si parlano.
 
---
 
## Strato 2 — `engine/sessioni.py`
 
Sessioni definite in **ora locale di borsa**, con il DST gestito da pandas.
Un filtro scritto in ora server sbaglia di un'ora nelle ~4 settimane l'anno in
cui i DST americano ed europeo sono sfasati: nessun errore, backtest falsato
in silenzio. È il test n. 5 della suite, con controprova.
 
| Sessione | Fuso | Apertura | Chiusura |
|---|---|---|---|
| ROLLOVER | America/New_York | 17:00 | istante |
| TOKYO | Asia/Tokyo | 09:00 | 18:00 |
| LONDRA | Europe/London | 08:00 | 17:00 |
| NEW_YORK | America/New_York | 08:00 | 17:00 |
| NYSE | America/New_York | 09:30 | 16:00 |
| FIX_LONDRA | Europe/London | 16:00 | istante |
 
Orari FX, non di borsa, tranne NYSE. Aggiungere una sessione è una riga nel
dizionario `SESSIONI`.
 
### Le due primitive
 
- `in_sessione(df, nome, quarantena=None)` → **FILTRO**, uno stato che dura
  ore. Le sessioni istantanee sollevano `ValueError`.
- `barre_da_apertura(df, nome, n=0, quarantena=None)` → **EVENTO**, una sola
  barra al giorno.
La distinzione è il punto del modulo: una sessione scritta come entry conta 36
barre M15 invece di 1 trigger, e gonfia il conteggio dei segnali per
persistenza multi-barra.
 
Se la barra dell'evento è in quarantena, quel giorno **non scatta** e non
viene spostata: spostarla produrrebbe un evento a un orario diverso da quello
dichiarato.
 
Collaudo su 6,7 anni: 1.743 eventi per sessione (≈ 260 giorni feriali × 6,7
anni), 0 per ROLLOVER — corretto, le sue barre sono sempre in quarantena.
 
> **Attenzione, difetto scoperto dopo:** `barre_da_apertura(df, "ROLLOVER")`
> **non** va usata per delimitare la giornata FX. Scartando i giorni non
> feriali locali salta la riapertura della domenica, e venerdì e lunedì si
> fondono in una giornata sola. Per i confini della giornata esiste
> `giorno_fx()` in `engine/livelli.py`. Dettagli in `20_CONDIZIONI_TEMPO.md`.
 
---
 
## Entry-metro — `entry_metro.py`
 
Cinque ingressi puramente temporali, **long**, `n=0`: `M_TOKYO`, `M_LONDRA`,
`M_NEW_YORK`, `M_NYSE`, `M_FIX_LONDRA`. ROLLOVER escluso (sempre in
quarantena).
 
**Non sono candidate: sono un righello.** Rispondono a *«il mio pattern di
prezzo fa meglio del semplice entrare a quell'ora?»*.
 
**Solo long** perché il trigger è temporale: scatta sulle stesse barre nei due
versi, e senza costi la curva short è quella long ribaltata di segno.
`anche_short=True` serve al Passo 3, dove lo swap rende i lati diversi.
 
**Non vanno contate fra i test multipli.** `NOMI_METRO` serve a escluderle dal
conteggio di `k` e dalla ricerca delle uscite.
 
**L'ingresso è alla barra dopo il trigger** (regola anti-lookahead del
framework): `M_LONDRA` misura dalle 08:15 di Londra, non dalle 08:00.
 
### Due tecniche di lettura che il collaudo ha prodotto
 
Sono il lascito più utile di questo pezzo, e valgono per qualunque condizione
futura.
 
**1. Il «t netto»: su un asset con deriva il t grezzo non basta.**
`vs_mercato_pct / incertezza_pct` misura lo scostamento dal mercato invece
dell'altezza della curva. È un'approssimazione lecita perché la linea del
mercato è calcolata su 167.000 barre contro ~1.743 trigger, quindi la sua
incertezza è trascurabile nel confronto.
 
Collaudo su due asset opposti, orizzonte 48:
 
| | EURUSD (t grezzo → netto) | BTCUSD (t grezzo → netto) |
|---|---|---|
| `M_FIX_LONDRA` | −3,01 → **−3,16** | 2,68 → **1,66** |
| `M_LONDRA` | −2,63 → **−2,74** | 1,67 → **0,37** |
| `M_NYSE` | −2,45 → **−2,59** | 2,46 → **1,40** |
| `M_TOKYO` | −1,69 → **−1,89** | −1,58 → **−2,51** |
| `M_NEW_YORK` | −1,50 → **−1,62** | 2,59 → **1,45** |
 
Su EURUSD, asset senza deriva, la correzione cambia poco. Su BTCUSD, passato
da 7.100 a 81.000, **dimezza i valori**: la curva grezza saliva da sola. È la
dimostrazione che la correzione serve, e il motivo per cui va automatizzata
(baseline oraria, non ancora costruita).
 
**2. Il conto anno per anno: un `t` aggregato non dice se il segno tiene.**
Rendimento medio a 24 barre su EURUSD, in pips, per un long:
 
| | M_TOKYO | M_LONDRA | M_NEW_YORK | M_NYSE | M_FIX_LONDRA |
|---|---|---|---|---|---|
| 2020 | +2,07 | +0,48 | +0,10 | −0,58 | +0,24 |
| 2021 | −1,39 | −0,49 | −0,33 | −0,24 | −1,03 |
| 2022 | −0,68 | −2,77 | +0,23 | +1,14 | −3,28 |
| 2023 | +0,57 | −2,07 | +0,42 | +1,46 | +1,00 |
| 2024 | −0,97 | −0,16 | −1,90 | −1,12 | +0,32 |
| 2025 | +1,49 | +1,52 | +1,75 | −0,64 | −4,30 |
| 2026 | −0,95 | +1,07 | −0,28 | −2,06 | −3,30 |
 
Una riga con `t` netto −3,16 fa tre anni positivi e quattro negativi. È il
cambio di segno che `due_meta` esiste per intercettare, visibile con sette
righe e prima di arrivarci. **Vale la pena farlo di routine su qualunque
candidato**, ed è un pezzo di diagnostica che il tool non ha ancora
automatizzato.
 
### Trappola risolta: i file di test inquinavano il notebook
 
Prima versione: entrambe le suite definivano `df` a livello di modulo. Un
`%run test_entry_metro.py` dal notebook sostituiva i dati veri con un mercato
sintetico a prezzo costante 1,0 e un anno solo — e l'event study restituiva
zeri e `NaN` senza segnalare nulla.
 
Corretto: tutto dentro `esegui()`, sotto `if __name__ == "__main__"`.
Importare i file non esegue niente e non definisce variabili. **Vale per ogni
suite futura.**
 
**Le tre impronte per riconoscere il problema se ricapita:**
 
| Spia | Sintetico | EURUSD vero |
|---|---|---|
| `prezzo medio` | 1.00 | **1.12** |
| `trades` per metro | 262 | **~1743** |
| `volte_incertezza` | `NaN` (0/0) | un numero |
 
---
 
## BTCUSD — collaudo di portabilità, 21/9/2026
 
Primo run dei moduli su un secondo asset (BTCUSD M15, 221.608 barre). Serviva a
vedere se il tool regge fuori da EURUSD. Ha retto, e ha fatto emergere due
proprietà dei dati.
 
### Il controllo dell'indice copre solo il 2020
 
`verifica_indice_utc` ha riportato *100% di 54 riaperture*. Delle 54, **52
sono del 2020 e 2 del 2021**, nessuna dopo: sono le settimane in cui BTCUSD
non trattava nel weekend.
 
Il controllo è genuino ma certifica **quell'era soltanto**. Non è un problema:
la regola del fuso è una proprietà del *server*, non del simbolo, ed è
stabilita su EURUSD. **Da ricordare portando il tool su altri 24/7.**
 
### BTCUSD non è davvero 24/7
 
Barre per orario NY × giorno della settimana, 2023 in poi:
 
| Orario NY | lun | mar | mer | gio | **ven** | sab | dom |
|---|---|---|---|---|---|---|---|
| 16:45 | 194 | 194 | 194 | 194 | **194** | 192 | 194 |
| 17:00 | 194 | 193 | 194 | 194 | **0** | 190 | 193 |
| 17:15 | 194 | 193 | 194 | 193 | **0** | 192 | 193 |
| 17:30 | 194 | 193 | 194 | 193 | **0** | 192 | 194 |
| 17:45 | 194 | 193 | 194 | 194 | **179** | 192 | 194 |
| 18:00 | 194 | 193 | 194 | 194 | **186** | 192 | 193 |
 
Il venerdì alle 17:00 NY la contrattazione **si ferma per tre barre**. C'è una
pausa settimanale del broker, e cade sul rollover.
 
### I conti tornano — il modulo misura, non sbaglia
 
Su un 24/7 pieno la quarantena dovrebbe marcare 5 barre su 96 = 5,21%.
Osservato: **5,21% nel 2020**, **~4,76% dal 2021**. La differenza sono proprio
le 3 barre mancanti del venerdì: 32 su 35 = 91,4%, e 4,76 / 5,21 = 0,914.
 
### Conseguenza operativa
 
**2020–2021 e 2023+ hanno strutture temporali diverse** — non solo il sabato,
anche la pausa del venerdì. Uno split In-Sample / Out-of-Sample a cavallo di
quel cambio confronterebbe due mercati diversi. Su BTCUSD conviene partire dal
2023.
 
Questo episodio è anche l'origine dell'idea di una **diagnostica delle pause
sistematiche** per simbolo: la pausa del venerdì è saltata fuori per caso da un
controllo di coerenza, e meglio vederle tutte in anticipo.
 
---
 
## `time_conditions.py` della V3 — archiviato
 
Sostituito da `entry_metro.py`. Non è nel repo V4 e non può registrarsi da
solo. I suoi difetti, utili come promemoria di cosa non rifare:
 
- legge `df.index.hour` assumendo ora server: su indice UTC i blocchi
  slittano di 2–3 ore senza errori;
- i nomi non corrispondono alle sessioni (T4 si chiamava "ROLLOVER" ma il
  rollover vero era l'inizio di T1);
- `_apertura` scattava anche sulla riapertura del lunedì;
- le 8 entry temporali venivano contate fra i 60 candidati della griglia:
  sono un metro, non candidati.