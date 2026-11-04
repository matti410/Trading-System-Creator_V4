# 80 · Confidenza in ore, ancora per timeframe, cella nel Lab

**Repo:** Trading-System-Creator_V4 (`main · fed5645`). **Tipo:** lavoro grande → prima la proposta in
`docs/81_PROPOSTA_CONFIDENZA_ORE_E_LAB.md`, nessun codice prima del via di Mattia.
**Da leggere:** `CLAUDE.md`, `docs/00`; `engine/confidenza.py`; `engine/indicatori.py` (blocco «DURATE in ore»,
`barre_per_durata`, `cella_vol_trend`); `engine/livelli.py` (`giorno_fx`); `engine/vetrina.py` (righe che usano
`congela_filtro` e la chiave `confidenza`, D2 di `docs/76`); cella 70 di `Trading_Grid_Search_v4_backtesting.ipynb`
(la 3.3); `Trading_System_Lab_Crypto.ipynb` sezioni 5 e 6; `docs/66` §5 (strada B).

## Perché
La confidenza (passo 5, statistica condizionata rolling) diventa l'ultimo filtro prima dell'OOS anche nel Lab. Oggi:
- `confidenza_rolling` conta le finestre in **barre** (`finestra=500`, `finestra_vol=20`): giuste solo su M15. Il
  resto del tool (atlante, orizzonti 1/4/8 ore) lavora in ore.
- `gap_trend` riparte a ogni giornata: su H4 la giornata ha 6 barre, sul daily 1 → l'asse trend non misura il trend.
- Il Lab non ha la confidenza (D2 di `docs/76`: solo la 3.3 della ricerca).

## Lavoro 1 · Confidenza in ore
`confidenza_rolling` (e `cella_contesto`) calcolano la cella con `indicatori.cella_vol_trend` (5 ore volatilità,
125 ore mediana, minimo 20 barre). Restano in trade: `finestra_trade=500`, `min_obs=30`.
**Prova obbligatoria:** su M15 tutto identico al bit (confidenza, filtri CONF_, 3.3 del notebook di ricerca).
Su M5/H1: le finestre coprono le stesse ore di M15.

## Lavoro 2 · Ancora di VWAP e regressione secondo il timeframe
Regola fissa decisa da Mattia, mai tarata sui dati: VWAP e regressione di `gap_trend` ripartono dal periodo più corto
che contiene almeno **20 barre** (lo stesso `MINIMO_RENDIMENTI`):

| timeframe | riparte ogni | barre |
|---|---|---|
| M5, M15, M30, H1 | giornata (00:00 UTC sugli exchange; `giorno_fx` sul broker), come oggi | 288/96/48/24 |
| H4 | settimana (lunedì 00:00 UTC) | 42 |
| D1 | mese solare | ~30 |

Fino a H1 nessun numero cambia (prova). `gap_trend` è usato anche dall'atlante (`cella_vol_trend`): su H4 e D1
cambia anche lì → dichiararlo nella proposta e nel resoconto. Sul broker (sospeso) basta che non si rompa.

## Lavoro 3 · Cella della confidenza nel Lab crypto
Nuova cella fra la 5 (Trova la strategia) e la 6 (Scheda strategia, OOS), come la 3.3 della ricerca:
storia dalla baseline del setup scelto sull'intera serie, `congela_confidenza_nota`, soglie in multipli del costo
(`CONF_BP_MEDI_…C`), tabella tenuti/scartati e calibrazione **solo in-sample**; nella 6, la curva OOS con e senza
confidenza (`plot_oos_confidenza`), guardata una volta.
- **Soglie fissate a priori**, le stesse della 3.3 (indicarle); nessuna soglia scelta guardando i risultati.
- **Conto delle prove:** le soglie entrano nella soglia cumulata Šidák del Lab con la chiave D2 della 3.3.
- **Sempre facoltativa:** un interruttore; se nessuna soglia migliora l'in-sample, si va all'OOS senza.
- La cella del Lab sostituisce l'idea della «fascia di volatilità prima dell'OOS»: la volatilità è già uno dei due
  assi. Nessuna cella separata.
- Markdown breve: cosa fa, come leggere la tabella in linguaggio da trader, cosa scegliere.

## Domande da chiudere nella proposta
1. Strada B (`docs/66` §5): se la strategia usa già una cella dell'atlante (stessa griglia vol × trend) la
   confidenza si salta anche nel Lab, come nella ricerca?
2. Le 3 soglie della 3.3 vanno bene anche nel Lab o servono altri valori (sempre a priori)?
3. Su D1 il mese ha ~30 barre e la mediana di 125 ore scende al minimo di 20 barre: segnalare se il riscaldamento
   (barre senza confidenza nota) diventa troppo lungo sugli storici disponibili.
4. Il motore «veloce»: aggiungere a `test_confidenza.py` una prova con i trade del motore veloce.

## Consegna
Un ramo, test in `test_confidenza.py` (più quelli toccati: atlante, indicatori), tutti i `test_*.py` verdi prima del
commit, `docs/00` aggiornato, resoconto breve. Nel Lab spiegare a Mattia come lanciarlo e cosa deve vedere.
