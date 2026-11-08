"""
La selezione della fabbrica (docs/82 P6 e P7, lavoro L4a): le strategie che reggono l'altopiano, con i parametri
congelati, sul pezzo di selezione.

    sel = seleziona(esito.sopravvissute, pezzi, config, id_ricerca, prove)    # FileProve della ricerca, o None
    sel.tabella          # una riga per strategia: misure, condizione 2, test individuale, famiglia, esito, motivo
    sel.scelte           # le strategie con esito «scelta»: le sole che possono andare oltre (cassaforte, L4b)
    controlla_ammessa(sel.tabella, id_strategia)   # si ferma se la strategia non è fra le scelte

- Il pezzo (pezzo_selezione): ricerca + selezione attaccati, così indicatori e soglie adattive non ripartono da zero;
  finisce all'ultima barra della selezione, nessuna barra della cassaforte. I segnali prima della prima barra della
  selezione si spengono: ogni trade nasce nella selezione. Come in tutto il motore, un trade ancora aperto all'ultima
  barra resta fuori dai trade (motore_veloce, U7): non si chiude con un prezzo inventato. I costi sono quelli del pezzo
  di selezione (Pezzi.costi("selezione")), con il funding dei due pezzi attaccato.
- Condizione di qualità 2 (qualita_2): almeno `trade_min` trade; giudizio.verdetto senza SCARTATA con EV in bp e
  P(EV<0) sotto `p_ev_neg_max` (bootstrap di giudizio.p_ev_negativo, 10.000 ricampionamenti, seme 0, sui bp); il
  trade migliore al massimo `peso_max` dei guadagni; totale / drawdown almeno `totale_su_dd_min`.
- Test individuale, che decide: t netto in bp sulla selezione >= giudizio.soglia_rumore(1, alfa) = 1,96 con alfa 5%.
- Famiglie fra le strategie che passano (famiglie_strategie), lato per lato, sui segnali finali (trigger, filtri,
  quarantena) di ricerca + selezione: solo segnali, non è una prova. Due strategie stanno insieme se famiglie.famiglie
  le unisce (famiglia 60%, lift 1,3) o se famiglie.sovrapposizioni le dà doppioni (quota 70%, lift 1,3). Di ogni
  famiglia resta la strategia con il t di selezione più alto (a parità, l'id più piccolo): esito «scelta»; le altre
  «stessa famiglia». Le strategie temporanee stanno in un registro isolato, che torna identico anche dopo un errore.
- Il conto (P7): ogni strategia valutata sulla selezione è una riga nel file delle prove (pezzo «selezione»). La
  tabella mostra accanto al test individuale la soglia che corrisponderebbe al totale k delle prove dell'asset: solo
  da leggere, nessun esito dipende da k.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from engine import registry as reg
from engine.famiglie import famiglie as famiglie_misurate
from engine.famiglie import sovrapposizioni
from engine.giudizio import SCARTATA, p_ev_negativo, soglia_rumore, verdetto
from engine.indicatori import aggiungi_indicatori

from .blocchi import blocchi_da_config
from .cache import Cache
from .dati import imposta_mercato_crypto
from .generatore import NOME_LATO, Teoria, _registro_isolato, _serie
from .valutatore import Costi, Misure, Strategia, Valutatore, id_strategia, misure_da_bp

PEZZO = "selezione"
FASE = "selezione"
LIMITE_CACHE_MB = 1500
N_BOOT, SEME_BOOT = 10_000, 0                 # P(EV<0) come nel Lab (giudizio.p_ev_negativo)
# Le regole delle famiglie già decise (docs/50 §7.5, docs/82 P6): passate per esteso, anche dove sono i predefiniti.
SOGLIA_FAMIGLIA, QUOTA_DOPPIONE, LIFT_MIN = 0.60, 0.70, 1.3
PREFISSO = "FAB_SEL_"                         # le strategie registrate per il tempo della misura delle famiglie
ESITI = ("scelta", "stessa famiglia", "scartata")


# ------------------------------------------------------------------ il pezzo
@dataclass
class PezzoSelezione:
    """Ricerca + selezione con gli indicatori, la prima barra della selezione e i costi della selezione."""
    df: pd.DataFrame
    inizio: int                      # la posizione della prima barra della selezione in df
    costi: dict


def pezzo_selezione(pezzi) -> PezzoSelezione:
    """Ricerca e selezione attaccate, con gli indicatori; finisce all'ultima barra della selezione."""
    imposta_mercato_crypto()
    ricerca, selezione = pezzi.df("ricerca"), pezzi.df(PEZZO)
    if not ricerca.index[-1] < selezione.index[0]:
        raise ValueError("ricerca e selezione si sovrappongono: i pezzi sono sbagliati.")
    df = aggiungi_indicatori(pd.concat([ricerca, selezione]))      # toglie le barre di riscaldamento in testa
    inizio = int(pd.DatetimeIndex(df.index).searchsorted(selezione.index[0]))
    if not pd.DatetimeIndex(df.index[inizio:]).equals(pd.DatetimeIndex(selezione.index)):
        raise ValueError("il pezzo di selezione ha perso delle barre con gli indicatori: la selezione si ferma.")
    costi = dict(pezzi.costi(PEZZO))
    f_r, f_s = pezzi.funding["ricerca"], pezzi.funding[PEZZO]
    if f_s is not None:
        costi["funding"] = pd.concat([f_r, f_s]) if f_r is not None else f_s
    return PezzoSelezione(df, inizio, costi)


class ValutatoreSelezione(Valutatore):
    """Il valutatore della fabbrica con i segnali spenti prima della barra `inizio`: ogni trade nasce dopo."""

    def __init__(self, blocchi, cache, costi: Costi, inizio: int):
        super().__init__(blocchi, cache, costi)
        self.inizio = int(inizio)
        self._utili = self._utili.copy()
        self._utili[: self.inizio] = False


# ------------------------------------------------------------------ le regole
def qualita_2(m: Misure, p_neg: float, q: dict) -> tuple[bool, str]:
    """Condizione di qualità 2 (docs/82 P6): (passa, motivo). Il motivo è vuoto se passa."""
    if m.trade < q["trade_min"]:
        return False, f"{m.trade} trade, meno di {q['trade_min']}"
    v = verdetto(ev=m.ev_bp, p_neg=p_neg, n_trades=m.trade, p_max=q["p_ev_neg_max"], min_trades=q["trade_min"],
                 ev_min=0.0)
    if v["esito"] == SCARTATA:
        return False, f"verdetto SCARTATA: {v['motivo'].replace('pips', 'bp')}"
    if not m.peso_max <= q["peso_max"]:
        return False, f"il trade migliore pesa il {100 * m.peso_max:.1f}% dei guadagni, oltre il {100 * q['peso_max']:.0f}%"
    if not m.totale_su_dd >= q["totale_su_dd_min"]:
        return False, f"totale / drawdown {m.totale_su_dd:.2f}, sotto {q['totale_su_dd_min']}"
    return True, ""


def soglia_test(alfa: float) -> float:
    """La soglia del test individuale: una prova sola (k = 1), 1,96 con alfa 5%."""
    return soglia_rumore(1, alfa)


def giudica(bp, config: dict) -> dict:
    """Le misure di una strategia sulla selezione e il giudizio: condizione 2, poi il test individuale, che decide."""
    m = misure_da_bp(bp)
    p_neg = p_ev_negativo(np.asarray(bp, dtype=float), n_boot=N_BOOT, seed=SEME_BOOT) if m.trade else math.nan
    passa_q2, motivo_q2 = qualita_2(m, p_neg, config["qualita_2"])
    soglia = soglia_test(config["test_individuale"]["alfa"])
    passa_t = bool(m.t == m.t and m.t >= soglia)
    if not passa_q2:
        motivo = f"condizione 2: {motivo_q2}"
    elif not passa_t:
        motivo = (f"test individuale: t {m.t:.2f} sotto {soglia:.2f}" if m.t == m.t
                  else "test individuale: t non calcolabile")
    else:
        motivo = ""
    return {**m.come_dict(), "p_ev_neg": p_neg, "qualita_2": passa_q2, "motivo_q2": motivo_q2,
            "soglia_test": soglia, "test": passa_t, "passa": passa_q2 and passa_t, "motivo": motivo}


# ------------------------------------------------------------------ le strategie
def teoria_da_id(id_teoria: str) -> Teoria:
    """«L|E47|ADX+F3_VOLUME_ABOVE_AVG|X3» -> Teoria (l'inverso di Teoria.id)."""
    lato, trigger, filtri, uscita = id_teoria.split("|")
    return Teoria(1 if lato == "L" else -1, trigger, tuple(f for f in filtri.split("+") if f and f != "-"), uscita)


def strategia_da_riga(riga, symbol: str, timeframe: str) -> Strategia:
    """La strategia di una riga delle sopravvissute (teoria, valori in JSON); si ferma se l'impronta non torna."""
    valori = riga["valori"] if isinstance(riga["valori"], dict) else json.loads(riga["valori"])
    s = Strategia.da_teoria(teoria_da_id(riga["teoria"]), valori)
    if id_strategia(s, symbol, timeframe) != riga["id_strategia"]:
        raise ValueError(f"la strategia {riga['id_strategia']} non torna dai suoi valori: le sopravvissute sono cambiate.")
    return s


# ------------------------------------------------------------------ le famiglie
def famiglie_strategie(maschere: dict, df: pd.DataFrame, lato: int, punteggi: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    (famiglie, sovrapposizioni) fra le strategie di un lato. `maschere` = {id: segnale finale su df}; `punteggi` =
    {id: t di selezione}. Una riga per strategia: famiglia (l'id della migliore del gruppo), membri, piu_vicina,
    somiglianza, migliore (è lei la scelta della famiglia). Il registro delle condizioni torna com'era, anche se la
    misura si ferma con un errore.
    """
    ids = sorted(maschere)
    vuota = pd.DataFrame(columns=["contenuta", "dentro", "quota_min", "quota_max", "lift_min", "doppione"])
    if not ids:
        return pd.DataFrame(columns=["id_strategia", "lato", "famiglia", "membri", "piu_vicina", "somiglianza",
                                     "migliore"]), vuota
    genitore = {i: i for i in ids}

    def radice(x):
        while genitore[x] != x:
            genitore[x] = genitore[genitore[x]]
            x = genitore[x]
        return x

    vicina = {i: (None, 0.0) for i in ids}
    sov = vuota
    if len(ids) > 1:
        nomi = [PREFISSO + i for i in ids]
        with _registro_isolato():
            for i, nome in zip(ids, nomi):
                reg.register_entry(nome, direction=lato)(lambda d, _m=maschere[i]: _serie(_m, d.index))
            tabella = famiglie_misurate(df, tipo="entry", nomi=nomi, soglia=SOGLIA_FAMIGLIA, lift_min=LIFT_MIN)
            sov = sovrapposizioni(df, tipo="entry", nomi=nomi, soglia=QUOTA_DOPPIONE, lift_min=LIFT_MIN)
        togli = len(PREFISSO)
        numero = {r.nome[togli:]: int(r.famiglia) for r in tabella.itertuples()}
        for r in tabella.itertuples():
            vicina[r.nome[togli:]] = (r.piu_vicina[togli:] if isinstance(r.piu_vicina, str) else None,
                                      float(r.somiglianza))
        for a in ids:
            for b in ids:
                if a < b and numero[a] == numero[b]:
                    genitore[max(radice(a), radice(b))] = min(radice(a), radice(b))
        for r in sov.itertuples():
            if r.doppione:
                a, b = radice(r.contenuta[togli:]), radice(r.dentro[togli:])
                if a != b:
                    genitore[max(a, b)] = min(a, b)
        sov = sov.assign(contenuta=sov["contenuta"].str[togli:], dentro=sov["dentro"].str[togli:])
    gruppi: dict = {}
    for i in ids:
        gruppi.setdefault(radice(i), []).append(i)
    righe = []
    for membri in gruppi.values():
        migliore = sorted(membri, key=lambda i: (-punteggi[i], i))[0]
        for i in membri:
            righe.append({"id_strategia": i, "lato": NOME_LATO[lato], "famiglia": migliore, "membri": len(membri),
                          "piu_vicina": vicina[i][0], "somiglianza": vicina[i][1], "migliore": i == migliore})
    return pd.DataFrame(righe).sort_values(["famiglia", "id_strategia"]).reset_index(drop=True), sov


# ------------------------------------------------------------------ la selezione
@dataclass
class Selezione:
    tabella: pd.DataFrame
    famiglie: pd.DataFrame
    sovrapposizioni: pd.DataFrame
    conto: dict = field(default_factory=dict)

    @property
    def scelte(self) -> pd.DataFrame:
        return self.tabella[self.tabella["esito"] == "scelta"].reset_index(drop=True)


COLONNE = ["teoria", "id_strategia", "lato", "trade", "totale_bp", "ev_bp", "t", "dd_bp", "peso_max", "totale_su_dd",
           "p_ev_neg", "qualita_2", "motivo_q2", "soglia_test", "test", "famiglia", "esito", "motivo", "valori"]


def _righe_prove(id_ricerca: str, tabella: pd.DataFrame) -> list[dict]:
    return [{"id_ricerca": id_ricerca, "pezzo": PEZZO, "fase": FASE, "teoria": r.teoria, "id_strategia": r.id_strategia,
             "trade": r.trade, "ev_bp": r.ev_bp, "t": r.t} for r in tabella.itertuples()]


def seleziona(sopravvissute: pd.DataFrame, pezzi, config: dict, id_ricerca: str = "", prove=None) -> Selezione:
    """
    Le sopravvissute dell'altopiano (righe con teoria, id_strategia, valori) sul pezzo di selezione: una riga per
    strategia con misure, condizione 2, test individuale, famiglia, esito e motivo (vedi la testa del file). Con
    `prove` (registro.FileProve della ricerca) ogni strategia valutata diventa una riga del file delle prove.
    """
    symbol, timeframe = config["symbol"], config["timeframe"]
    if not len(sopravvissute):
        return Selezione(pd.DataFrame(columns=COLONNE), *famiglie_strategie({}, pd.DataFrame(), 1, {}))
    p = pezzo_selezione(pezzi)
    blocchi = [b for b in blocchi_da_config(config)]
    cache = Cache(p.df, LIMITE_CACHE_MB)
    costi = Costi(p.df, p.costi)
    valutatore = ValutatoreSelezione(blocchi, cache, costi, p.inizio)
    tutto = Valutatore(blocchi, cache, costi)          # per i segnali delle famiglie: ricerca + selezione
    righe, strategie = [], {}
    for r in sopravvissute.to_dict("records"):
        s = strategia_da_riga(r, symbol, timeframe)
        i = r["id_strategia"]
        if i in strategie:
            continue
        strategie[i] = s
        g = giudica(valutatore.bp(s), config)
        righe.append({"teoria": r["teoria"], "id_strategia": i, "lato": NOME_LATO[s.lato], **g,
                      "valori": json.dumps(s.come_dict()["valori"], ensure_ascii=False, sort_keys=True)})
    tabella = pd.DataFrame(righe)
    if prove is not None:
        prove.aggiungi(_righe_prove(id_ricerca, tabella))
    tabella["famiglia"] = None
    tabella["esito"] = np.where(tabella["passa"], "scelta", "scartata")
    fam, sov = [], []
    for lato in (1, -1):
        passano = tabella[tabella["passa"] & (tabella["lato"] == NOME_LATO[lato])]
        maschere = {i: tutto.segnali(strategie[i])["segnale"] for i in passano["id_strategia"]}
        f, o = famiglie_strategie(maschere, p.df, lato, dict(zip(passano["id_strategia"], passano["t"])))
        fam.append(f)
        sov.append(o)
    famiglie = pd.concat([f for f in fam if len(f)], ignore_index=True) if any(len(f) for f in fam) else fam[0]
    sovr = pd.concat([o for o in sov if len(o)], ignore_index=True) if any(len(o) for o in sov) else sov[0]
    per_id = {r.id_strategia: r for r in famiglie.itertuples()}
    for k, r in tabella.iterrows():
        f = per_id.get(r["id_strategia"])
        if f is None:
            continue
        tabella.at[k, "famiglia"] = f.famiglia
        if not f.migliore:
            tabella.at[k, "esito"] = "stessa famiglia"
            tabella.at[k, "motivo"] = f"stessa famiglia di {f.famiglia}, che ha il t di selezione più alto"
    tabella = tabella.drop(columns=["passa"])[COLONNE]
    return Selezione(tabella, famiglie, sovr)


def controlla_ammessa(tabella: pd.DataFrame, id_strat: str) -> None:
    """Si ferma se la strategia non ha l'esito «scelta» in selezione: una scartata non compare ai passi dopo."""
    riga = tabella[tabella["id_strategia"] == id_strat]
    if not len(riga):
        raise ValueError(f"la strategia {id_strat} non è passata dalla selezione di questa ricerca.")
    esito = riga["esito"].iloc[0]
    if esito != "scelta":
        raise ValueError(f"la strategia {id_strat} ha esito «{esito}» in selezione ({riga['motivo'].iloc[0]}): "
                         "non può andare oltre.")


def ammesse(tabella: pd.DataFrame) -> list[str]:
    """Gli id delle strategie con esito «scelta», nell'ordine della tabella."""
    return [i for i in tabella.loc[tabella["esito"] == "scelta", "id_strategia"]]


def con_conto(sel: Selezione, conto: dict) -> Selezione:
    """La tabella con il conto delle prove accanto al test individuale: solo da leggere (P7)."""
    t = sel.tabella.copy()
    pos = t.columns.get_loc("test") + 1
    t.insert(pos, "prove_asset", conto.get("asset"))
    t.insert(pos + 1, "soglia_da_leggere", conto.get("soglia_da_leggere"))
    return Selezione(t, sel.famiglie, sel.sovrapposizioni, dict(conto))
