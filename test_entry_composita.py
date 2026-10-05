"""
Suite di validazione di entry_composita.py (OR di entry), 5/10/2026.

Si lancia da terminale, dalla cartella del progetto:

    python test_entry_composita.py

Non serve MetaTrader 5 ne' nessun file di dati: le entry sono finte, su una
serie costruita a mano. Dura pochi secondi. Alla fine stampa
«RISULTATO: N/N test superati».
"""
from __future__ import annotations

import io
import sys
import warnings
from contextlib import redirect_stdout

import numpy as np
import pandas as pd

from engine import registry as reg
from entry_composita import componenti, elenca_composite, registra_or
from helpers import _evento

warnings.simplefilter("ignore")


def _df(n=30):
    idx = pd.date_range("2024-01-02 10:00", periods=n, freq="15min", tz="UTC")
    p = 1.10 + 0.0001 * np.arange(n)
    return pd.DataFrame({"Open": p, "High": p + 0.0005, "Low": p - 0.0005,
                         "Close": p + 0.0002, "Volume": 100.0}, index=idx)


def _segnale(n, quando):
    v = np.zeros(n, dtype=bool)
    v[list(quando)] = True
    return v


def _entry(arr):
    """Entry finta CAUSALE: restituisce l'array di segnali fino alla lunghezza del df."""
    return lambda d: pd.Series(arr[:len(d)], index=d.index)


def esegui() -> int:
    ESITI = []

    def check(nome, condizione, dettaglio=""):
        ESITI.append(bool(condizione))
        stato = "OK     " if condizione else "FALLITO"
        print(f"  [{stato}] {nome}" + (f"  — {dettaglio}" if dettaglio else ""))

    def errore(fn, parte=""):
        try:
            with redirect_stdout(io.StringIO()):
                fn()
        except (ValueError, KeyError) as e:
            return parte in str(e)
        return False

    d = _df()
    n = len(d)
    a = _segnale(n, [3, 10, 20])
    b = _segnale(n, [6, 10, 21])
    c = _segnale(n, [15])
    reg.clear_registry()
    reg.register_entry("A_LONG", 1)(_entry(a))
    reg.register_entry("B_LONG", 1)(_entry(b))
    reg.register_entry("C_LONG", 1)(_entry(c))
    reg.register_entry("S_SHORT", -1)(_entry(a))

    print("\nA · La logica OR")
    with redirect_stdout(io.StringIO()):
        registra_or("C1_A_OR_B", ["A_LONG", "B_LONG"])
    f = reg.get_entry("C1_A_OR_B")
    atteso = _evento(pd.Series(a | b, index=d.index)).to_numpy()
    check("1. composita == _evento(A OR B), barra per barra", np.array_equal(f(d).to_numpy(), atteso))
    check("2. i segnali di A (3, 20) e di B (6, 10) sono tutti presenti",
          all(f(d).iloc[i] for i in (3, 6, 10, 20)))
    check("3. dove non scatta nessuna delle due, e' falsa", not f(d).iloc[15] and not f(d).iloc[0])
    check("4. A a t=20 e B a t=21: un solo evento, a t=20 (documentato)",
          bool(f(d).iloc[20]) and not bool(f(d).iloc[21]))
    check("5. la composita e' un EVENTO, non uno stato (mai due True consecutivi)",
          not (f(d).to_numpy()[1:] & f(d).to_numpy()[:-1]).any())
    check("6. restituisce booleani con lo stesso indice del df",
          f(d).dtype == bool and f(d).index.equals(d.index))

    with redirect_stdout(io.StringIO()):
        registra_or("C2_TRE", ["A_LONG", "B_LONG", "C_LONG"])
    f3 = reg.get_entry("C2_TRE")
    check("7. tre entry in OR: include anche la terza", bool(f3(d).iloc[15]))

    print("\nB · Nessun lookahead")
    ok = True
    for t in range(2, n):
        if bool(f(d.iloc[:t + 1]).iloc[-1]) != bool(f(d).iloc[t]):
            ok = False
    check("8. il valore alla barra t non cambia togliendo le barre future", ok)

    print("\nC · Registrazione e controlli")
    check("9. ha la direzione delle entry di base (long = 1)", reg.get_entry_direction("C1_A_OR_B") == 1)
    check("10. e' elencata fra le entry long e non fra le short",
          "C1_A_OR_B" in reg.list_entries(1) and "C1_A_OR_B" not in reg.list_entries(-1))
    check("11. componenti() restituisce le entry di base",
          componenti("C1_A_OR_B") == ("A_LONG", "B_LONG")
          and elenca_composite()["C2_TRE"] == ("A_LONG", "B_LONG", "C_LONG"))
    check("12. errore se meno di 2 entry", errore(lambda: registra_or("X1", ["A_LONG"]), "almeno 2"))
    check("13. errore se entry ripetute", errore(lambda: registra_or("X2", ["A_LONG", "A_LONG"]), "ripetute"))
    check("14. errore se un nome non e' registrato",
          errore(lambda: registra_or("X3", ["A_LONG", "NON_ESISTE"]), "NON_ESISTE"))
    check("15. errore se direzioni miste",
          errore(lambda: registra_or("X4", ["A_LONG", "S_SHORT"]), "Direzioni miste"))
    check("16. errore se si passa una stringa invece di una lista",
          errore(lambda: registra_or("X5", "A_LONG"), "lista"))
    check("17. nessuna delle prove errate ha lasciato registrazioni",
          not any(x in reg.list_entries() for x in ("X1", "X2", "X3", "X4", "X5")))

    buf = io.StringIO()
    with redirect_stdout(buf):
        registra_or("C1_A_OR_B", ["A_LONG", "B_LONG"])
    check("18. stessa definizione richiamata due volte: saltata con avviso, nessun errore",
          "gia' registrata" in buf.getvalue())
    check("19. stesso nome con definizione diversa: errore",
          errore(lambda: registra_or("C1_A_OR_B", ["A_LONG", "C_LONG"]), "gia' registrato"))
    check("20. un nome gia' usato da una entry di base non puo' diventare composita",
          errore(lambda: registra_or("A_LONG", ["B_LONG", "C_LONG"]), "gia' registrato"))

    print("\nD · Dentro il motore (con l'inversione)")
    from engine.exit_search_bt import run_exit_search_bt
    rng = np.random.default_rng(11)
    m = 6000
    close = 1.10 * np.exp(np.cumsum(rng.normal(0, 0.0004, m)))
    ap = np.r_[close[0], close[:-1]]
    mk = pd.DataFrame({"Open": ap, "High": np.maximum(ap, close) * 1.0002,
                       "Low": np.minimum(ap, close) * 0.9998, "Close": close, "Volume": 100.0},
                      index=pd.date_range("2024-01-01", periods=m, freq="15min", tz="UTC"))
    reg.clear_registry()
    sl1, sl2, ss = (rng.random(m) < 0.01 for _ in range(3))
    reg.register_entry("L1", 1)(_entry(sl1))
    reg.register_entry("L2", 1)(_entry(sl2))
    reg.register_entry("S1", -1)(_entry(ss))
    with redirect_stdout(io.StringIO()):
        registra_or("CL", ["L1", "L2"])
    kw = dict(entry_cols_short=["S1"], n_barre=8, verbose=False)
    solo1 = run_exit_search_bt(mk, entry_cols_long=["L1"], **kw).risultati
    comp = run_exit_search_bt(mk, entry_cols_long=["CL"], **kw).risultati
    comp_inv = run_exit_search_bt(mk, entry_cols_long=["CL"], inverti_su_opposto=True, **kw).risultati
    check("21. la composita gira nel motore e produce piu' trade della sola L1",
          int(comp["trades"].iloc[0]) > int(solo1["trades"].iloc[0]),
          f"L1 {int(solo1['trades'].iloc[0])} · L1 OR L2 {int(comp['trades'].iloc[0])}")
    check("22. composita + inversione: gira e cambia i trade rispetto a senza inversione",
          int(comp_inv["trades"].iloc[0]) != int(comp["trades"].iloc[0]),
          f"senza {int(comp['trades'].iloc[0])} · con {int(comp_inv['trades'].iloc[0])}")
    reg.clear_registry()

    print("\nE · risolvi_scelta: una condizione o una lista, con il lato dichiarato")
    from entry_composita import risolvi_scelta
    from engine.filter_search_bt import run_filter_search_bt
    reg.clear_registry()
    reg.register_entry("E1_RSI_L", 1)(_entry(sl1))
    reg.register_entry("E4_EMA_L", 1)(_entry(sl2))
    reg.register_entry("E9_SHORT_X", -1)(_entry(ss))
    reg.register_entry("E4_SHORT_Y", -1)(_entry(rng.random(m) < 0.01))

    check("23. stringa singola: restituisce lo stesso nome, nessuna composita creata",
          risolvi_scelta("E1_RSI_L", lato="long") == "E1_RSI_L" and not elenca_composite().get("E1_RSI_L"))
    check("24. lista di una sola entry: restituisce quel nome",
          risolvi_scelta(["E1_RSI_L"], lato="long") == "E1_RSI_L")
    check("25. None: lato non attivo", risolvi_scelta(None, lato="short") is None)
    with redirect_stdout(io.StringIO()):
        nome_l = risolvi_scelta(["E4_EMA_L", "E1_RSI_L"], lato="long")
    check("26. lista di due: nome automatico, entry in ordine alfabetico",
          nome_l == "OR(E1_RSI_L|E4_EMA_L)", nome_l)
    check("27. la composita e' registrata, long, con le due entry di base",
          reg.get_entry_direction(nome_l) == 1 and componenti(nome_l) == ("E1_RSI_L", "E4_EMA_L"))
    buf = io.StringIO()
    with redirect_stdout(buf):
        nome_l2 = risolvi_scelta(["E1_RSI_L", "E4_EMA_L"], lato="long")   # ordine diverso
    check("28. stessa lista in ordine diverso: stesso nome, nessun errore",
          nome_l2 == nome_l and "gia' registrata" in buf.getvalue())
    buf = io.StringIO()
    with redirect_stdout(buf):
        nome_s = risolvi_scelta(("E9_SHORT_X", "E4_SHORT_Y"), lato="short")   # anche una tupla
    check("29. lato short: composita short, e lo scrive a video",
          reg.get_entry_direction(nome_s) == -1 and "short" in buf.getvalue(), buf.getvalue().strip())
    check("30. entry short in una scelta LONG: errore che dice quali",
          errore(lambda: risolvi_scelta(["E1_RSI_L", "E9_SHORT_X"], lato="long"), "E9_SHORT_X"))
    check("31. entry long in una scelta SHORT: errore",
          errore(lambda: risolvi_scelta("E1_RSI_L", lato="short"), "LONG"))
    check("32. consenti_invertite=True: accettata",
          risolvi_scelta("E1_RSI_L", lato="short", consenti_invertite=True) == "E1_RSI_L")
    check("33. lato sbagliato (scritto male): errore", errore(lambda: risolvi_scelta("E1_RSI_L", lato="lungo"), "lato"))
    check("34. nome inesistente: errore con i nomi simili",
          errore(lambda: risolvi_scelta("E1_RSI_LL", lato="long"), "simili registrate: E1_RSI_L"))
    check("35. lista vuota: errore", errore(lambda: risolvi_scelta([], lato="long"), "vuota"))
    check("36. elementi non stringa: errore", errore(lambda: risolvi_scelta(["E1_RSI_L", 3], lato="long"), "stringhe"))

    # il nome automatico (con | e parentesi) attraversa davvero i due motori
    r1 = run_exit_search_bt(mk, entry_cols_long=[nome_l, None], entry_cols_short=[nome_s, None],
                            n_barre=8, verbose=False).risultati
    check("37. run_exit_search_bt con [nome composito, None]: gira, 3 combinazioni (solo L, solo S, L+S)",
          len(r1) == 3 and r1["trades"].min() > 0, f"{len(r1)} righe")
    check("38. l'etichetta della combinazione contiene il nome composito",
          r1["combinazione"].str.contains(nome_l, regex=False).any())
    reg.register_filter("T_SEMPRE", 0)(lambda d: pd.Series(True, index=d.index))
    f1 = run_filter_search_bt(mk, entry_long=nome_l, entry_short=nome_s, n_barre=8,
                              filtri=["T_SEMPRE"], verbose=False, n_boot=100,
                              inverti_su_opposto=True).risultati
    check("39. run_filter_search_bt con entry composite + inversione: gira",
          len(f1) == 2 and int(f1["trades"].iloc[0]) > 0 and int(f1["trades"].iloc[0]) == int(f1["trades"].iloc[1]))
    reg.clear_registry()

    print("\n" + "=" * 70)
    ok_, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok_}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok_ == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
