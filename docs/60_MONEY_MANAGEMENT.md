# 60 · Money management nel Trading System Lab — incarico di studio

**Data:** 16 ottobre 2026
**Stato:** DA STUDIARE. Nessuna decisione sul "come" è stata presa: la proposta la fai tu (agente), Mattia dà l'OK.

---

## 1. Obiettivo

Aggiungere una sezione di **money management (MM)** al notebook `Trading_System_Lab.ipynb`, subito dopo la
sezione **"6 · Scheda strategia"** (quella che esegue la strategia sui dati out-of-sample), e portare la stessa sezione
anche in `Trading_Grid_Search_v4_backtesting.ipynb`.

Il MM va costruito sulle conoscenze del libro **Andrea Unger, "The Successful Trader's Guide to Money Management" (2021)**.
Si fa prima di passare alla versione crypto del progetto, quindi quello che nasce qui deve poter essere riusato così com'è
nel repository gemello crypto (file condivisi, nessun legame con il forex).

## 2. Cosa si chiede in questa fase

**Solo studio e proposta. Nessun codice.**

1. Leggi tutto il libro, per intero, e leggi il repo (vedi §5 e §6).
2. Scrivi la proposta in `docs/61_PROPOSTA_MONEY_MANAGEMENT.md`, in italiano, in parole semplici (Mattia non è un informatico).
3. Fermati e aspetta l'OK di Mattia, punto per punto. Il codice si scrive solo dopo, candidato per candidato
   (stessa regola di `docs/50`).

La proposta deve contenere, con il **perché** di ogni scelta:

- quali tecniche del libro hanno senso per questo tool e quali no, e le ragioni (anche per quelle scartate);
- come procedere: in quali fasi e in che ordine, e per ogni fase **cosa vedrebbe Mattia** nel notebook e **quale vantaggio concreto** gli porta;
- gli input che l'utente dovrebbe scrivere nella cella e quello che ottiene in uscita;
- come collaudare ogni pezzo (test, confronti con esempi numerici del libro, identità con i risultati già validati);
- i rischi e i punti dubbi;
- le domande a cui solo Mattia può rispondere.

Se esistono alternative ragionevoli, presentale con pro e contro e indica quale consigli.

## 3. Decisioni già prese da Mattia (non rimetterle in discussione)

1. **Posizione:** la sezione MM va dopo la 6. Le attuali 7 e 8 diventano 8 e 9. Vanno aggiornati anche i testi che citano i numeri delle schermate
   (riquadri in `engine/vetrina.py`, docstring, titolo/sottotitolo del notebook).
2. **Stress test (sezione 8 attuale):** per ora resta com'è. Come convivere con i suoi "lotti consigliati" si rivede dopo la prima fase.
3. **Calibrazione:** i parametri del MM si scelgono con i dati in-sample e con una regola dell'utente (ad esempio il drawdown che accetta).
   L'out-of-sample serve solo a mostrare cosa sarebbe successo, si guarda una volta e non si ritocca.
4. **Notebook:** la sezione va mantenuta in **entrambi** i notebook, come da `CLAUDE.md`.

## 4. Fatti trovati nel repo (informazioni, non decisioni)

- `scheda(s, filtro)` (sezione 6) salva in sessione `s.trades_is` e `s.trades_oos`, cioè i trade nel formato di backtesting.py.
- Il motore lavora in **pips netti per trade** e non dipende da capitale o lotti (`CASH` enorme, `margin=1.0`). I pips netti si ricavano con `engine/metriche.pips_per_trade`.
- La colonna `SL` dei trade esiste solo se lo stop adattivo è acceso (`perc_sl` > 0). Con stop a 0 il rischio per trade non è definito.
- `engine/montecarlo.py` ha già `valore_pip_lotto` e `sizing`. Lo stress test usa il prezzo dell'**ultima barra** per convertire il pip in dollari:
  su USDJPY il valore del pip cambia col prezzo, e per DE40 serve anche il cambio EUR/USD.
- `engine/simboli.py` non contiene lotto minimo, passo del lotto e lotto massimo. Si leggono da MT5 solo in **sola lettura** e **solo con il permesso esplicito di Mattia** (regola di `CLAUDE.md`).
- I trade sono non sovrapposti e c'è una sola posizione alla volta: il capitale all'ingresso di ogni trade è ben definito.
- Il libro è ragionato in contratti (futures). Il tool lavora con lotti frazionari su forex/CFD e, in futuro, con crypto: l'adattamento è parte dello studio.

## 5. Vincoli del progetto

- Mattia **non è un informatico**: ogni passo spiegato in parole semplici, con come eseguire i comandi e cosa dovrebbe vedere.
- Ha il timore che aggiungere complessità trascini errori: ogni fase va spiegata con il vantaggio concreto che porta.
- Niente aggiunte non richieste: ciò che va oltre la richiesta si propone e si discute, non si consegna.
- Modifiche all'engine **additive** (nuovi moduli, default retrocompatibili). Se una modifica non lo è, dichiaralo.
- **Nessun lookahead**: i lotti di un trade usano solo ciò che si sapeva al suo ingresso.
- Il pip viene da `engine/simboli.py`, mai dedotto dal prezzo.
- Ogni pezzo di codice passa un test di validazione prima di essere consegnato. Prima di ogni commit si lanciano **tutti** i `test_*.py`
  (l'ultima riga di ognuno: "RISULTATO: n/n test superati").
- Il Lab non ha codice nelle celle: chiama funzioni di `engine/vetrina.py`. I due notebook restano sempre allineati.
- Regola di `docs/00_SCOPO_E_STATO.md`: i risultati sui dati non sono il metro di giudizio del progetto. Niente commenti
  tipo "la strategia tiene/non tiene" né proposte di cambiare asset.
- Procedura Git di `CLAUDE.md`: un ramo per argomento, mai lavorare su `main`, il merge lo fa sempre Mattia.

## 6. Fonti da leggere

- Il libro (PDF): `dati/libri/The Successful Traders Guide to Money Management 2021.pdf` (cartella ignorata da Git, non va pubblicata).
- `CLAUDE.md`, `docs/00_SCOPO_E_STATO.md`, `docs/02_KPI_E_GIUDIZIO.md`, `docs/50_IDEE_DA_ARTICOLI.md`.
- `Trading_System_Lab.ipynb`, `engine/vetrina.py`, `engine/montecarlo.py`, `engine/metriche.py`, `engine/simboli.py`.
- Facoltativi, se Mattia li mette in `dati/libri/`: la trascrizione "Lesson 9 – Improve, Validate & Size Your Strategy" e il notebook `EV_MC_Analysis_Strategy_IP_final.ipynb`, da cui è nato il Monte Carlo del tool.

## 7. Domande aperte da portare nella proposta (nessuna risposta già data)

- Quali tecniche del libro adottare, in che ordine e perché.
- Come adattare al tool i modelli pensati per i contratti, usando lotti frazionari.
- Che rischio per trade usare quando lo stop è spento.
- Quali input chiedere all'utente (capitale iniziale, rischio, drawdown accettato, altro) e come tenerli coerenti con lo stress test.
- Cosa mostrare in uscita nel notebook e come spiegarlo a un trader.
- Come progettare il modulo perché sia riusabile senza modifiche nel repo crypto.
