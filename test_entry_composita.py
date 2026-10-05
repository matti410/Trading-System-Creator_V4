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

    print("\n" + "=" * 70)
    ok_, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok_}/{tot} test superati  (pandas {pd.__version__})")
    print("=" * 70)
    return 0 if ok_ == tot else 1


if __name__ == "__main__":
    sys.exit(esegui())
