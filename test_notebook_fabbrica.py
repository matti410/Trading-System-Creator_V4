"""
Suite di collaudo del notebook della fabbrica, Fabbrica_Strategie_Crypto.ipynb (docs/82 §7, lavoro L5b).

Si lancia da terminale, dalla cartella del progetto:

    python test_notebook_fabbrica.py

Prima controlla il file (celle, testi, chiamate); poi esegue il notebook intero con nbclient, due volte di fila, su
una cartella di dati SINTETICI e una config ridotta. Le impostano i collaudi su una copia del notebook, cambiando i
valori dei campi e la cartella dei dati: il notebook vero non ha campi in più e non viene modificato. Servono
nbclient e un kernel di Jupyter (ipykernel). Stampa una riga per collaudo e alla fine «RISULTATO: n/n test superati».

    python test_notebook_fabbrica.py --copia [cartella]

non fa collaudi: prepara in `cartella` (predefinita: collaudo_fabbrica nella cartella temporanea) i dati sintetici e
la copia di collaudo del notebook, da aprire in VS Code e lanciare cella per cella.
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
import tempfile
import time
import warnings

import pandas as pd

from engine.fabbrica import registro, sintetici
from engine.fabbrica.cassaforte import ESITO, INGRESSO
from engine.fabbrica.config import cartella_asset, config_standard
from engine.fabbrica.schede import FRASE_FINALE

warnings.simplefilter("ignore")

QUI = os.path.dirname(os.path.abspath(__file__))
NOTEBOOK = os.path.join(QUI, "Fabbrica_Strategie_Crypto.ipynb")
SPOT = "BYBIT_SPOT_ETHUSDT"
CONFINI = {"inizio": "2024-01-01 00:00", "ricerca_ore": 3000, "selezione_ore": 2000, "cassaforte_ore": 500}
BLOCCHI = ("DONCHIAN", "RSI_RIENTRO", "F3_VOLUME_ABOVE_AVG", "ADX", "X0", "X3")
FUNZIONI = {"configura", "ricerca", "imbuto", "strategie_rimaste", "cassaforte", "mm_e_stress", "schede"}
TITOLI = ["Avvio", "1 · Configura", "2 · La ricerca", "3 · L'imbuto", "4 · Le strategie rimaste", "5 · La cassaforte",
          "6 · MM, stress test e verifica dei trade", "7 · Le schede"]
ESITI: list[bool] = []
# (09/11) La cella 1 aggiorna i dati a ogni avvio: nella copia di collaudo l'exchange non risponde (nessuna rete) e la
# cella usa il CSV sintetico, con l'avviso. Stesso aggiorna_per_lab, con un exchange finto.
SENZA_RETE = (
    "import engine.vetrina_fabbrica as _vf, engine.aggiorna_dati as _ad, engine.exchange as _ex   # collaudo: senza rete\n"
    "class _Giu:\n"
    "    def __getattr__(self, nome):\n"
    "        raise ConnectionError('NetworkError: exchange irraggiungibile (collaudo)')\n"
    "_vf._scarica = lambda s, t, c: _ad.aggiorna_per_lab(s, t, c, aperti={k: _Giu() for k in set(_ex.CCXT_ID.values())},\n"
    "                                                    verbose=False, attesa=0.0)\n")


def check(nome: str, ok: bool, dettaglio: str = "") -> None:
    ESITI.append(bool(ok))
    print(f"[{'OK ' if ok else 'KO '}] {nome}" + (f"  ({dettaglio})" if dettaglio else ""))


def _leggi():
    import nbformat
    return nbformat.read(NOTEBOOK, as_version=4)


def _titolo(cella) -> str | None:
    m = re.match(r"#@title (.+?) \{", cella.source)
    return m.group(1) if m else None


def esegui() -> int:
    t0 = time.perf_counter()
    nb = _leggi()
    _file(nb)
    _esecuzione(nb)
    print("\n" + "=" * 70)
    print(f"Durata: {time.perf_counter() - t0:.0f} s")
    ok, tot = sum(ESITI), len(ESITI)
    print(f"RISULTATO: {ok}/{tot} test superati  (pandas {pd.__version__})")
    return 0 if ok == tot else 1


# ------------------------------------------------------------------ il file
def _file(nb):
    print("Il file del notebook (docs/82 §7, docs/81 §5)")
    codice = [c for c in nb.cells if c.cell_type == "code"]
    check("1. formato valido, nessun output salvato, link di Colab a questo notebook",
          not errore_validazione(nb) and all(not c.outputs and c.execution_count is None for c in codice)
          and "blob/main/Fabbrica_Strategie_Crypto.ipynb" in nb.cells[0].source)
    check("2. le celle di codice sono Avvio e le schermate da 1 a 7, in ordine", [_titolo(c) for c in codice] == TITOLI,
          f"{[_titolo(c) for c in codice]}")
    corti, lunghi = [], []
    for i, c in enumerate(nb.cells):
        if c.cell_type != "code":
            continue
        sopra = nb.cells[i - 1]
        righe = [x for x in sopra.source.splitlines() if x.strip()]
        ok = (sopra.cell_type == "markdown" and righe[0].startswith("## ") and len(righe) <= 6
              and all(k in sopra.source for k in ("**Cosa fa:**", "**Come leggere:**", "**Poi:**")))
        (corti if ok else lunghi).append(_titolo(c))
        if not re.search(r"\d", sopra.source.split("**Come leggere:**")[1].split("**Poi:**")[0]):
            lunghi.append(f"{_titolo(c)}: nessun esempio numerico")
    check("3. sopra ogni cella di codice una cella di testo di al massimo 6 righe: Cosa fa, Come leggere con un esempio "
          "numerico, Poi", not lunghi, f"da rivedere: {lunghi}")
    glossario = next(c.source for c in nb.cells if c.cell_type == "markdown" and c.source.startswith("## Glossario"))
    sigle = ("**bp", "**EV:**", "**MM", "**t:**", "**Drawdown:**", "**Funding:**", "**Zoom:**", "**In-sample",
             "**Asset:**", "**Cassaforte:**", "**Famiglia:**", "**Altopiano:**", "**Imbuto:**")
    check("4. il glossario in testa spiega le sigle e le parole usate nelle celle", all(s in glossario for s in sigle),
          f"mancano: {[s for s in sigle if s not in glossario]}")
    chiamate = []
    for c in codice[1:]:
        corpo = "\n".join(x for x in c.source.splitlines() if x.strip() and not x.lstrip().startswith("#")
                          and "#@param" not in x)
        albero = ast.parse(corpo)
        ok = (len(albero.body) == 1 and isinstance(albero.body[0], (ast.Assign, ast.Expr))
              and isinstance(albero.body[0].value, ast.Call) and albero.body[0].value.func.id in FUNZIONI)
        chiamate.append(ok)
    check("5. nelle celle da 1 a 7 solo i campi e una chiamata a una funzione di engine/vetrina_fabbrica.py",
          all(chiamate) and len(chiamate) == 7)
    testi = "\n".join(c.source for c in nb.cells)
    cella5 = next(nb.cells[i - 1].source + nb.cells[i].source for i, c in enumerate(nb.cells)
                  if c.cell_type == "code" and _titolo(c) == "5 · La cassaforte")
    check("6. (10/11) la 5 non ha frase di conferma né avviso «una volta sola»; nessun rimando alle schermate del Lab; "
          "timeframe da M1 a D1 nella 1", "UNA VOLTA SOLA" not in cella5 and "frase" not in cella5.lower()
          and "schermata" not in testi.lower()
          and '["M1", "M5", "M15", "M30", "H1", "H4", "D1"]' in testi)


def errore_validazione(nb) -> str:
    import nbformat
    try:
        nbformat.validate(nb)
        return ""
    except Exception as e:  # noqa: BLE001
        return repr(e)


# ------------------------------------------------------------------ l'esecuzione
def _cambia(sorgente: str, vecchio: str, nuovo: str) -> str:
    if sorgente.count(vecchio) != 1:
        raise AssertionError(f"nel notebook non trovo una volta sola: {vecchio!r}")
    return sorgente.replace(vecchio, nuovo)


def _copia_di_collaudo(nb, dati: str):
    """La copia che gira: campi di collaudo, cartella sintetica, config ridotta e meno simulazioni."""
    import copy
    cfg = config_standard(SPOT, "M15", seme=0, processi=2)
    cfg["confini"] = dict(CONFINI)
    cfg["blocchi"] = {k: v for k, v in cfg["blocchi"].items() if k in BLOCCHI}
    cfg["qualita_1"]["trade_min"] = 30
    cfg["budget"].update({"teorie_passo_2": 4, "prove_per_giro": 60})
    nb = copy.deepcopy(nb)
    per = {_titolo(c): c for c in nb.cells if c.cell_type == "code"}
    a = per["Avvio"]
    a.source = _cambia(a.source, 'nome_macchina = "pc"', 'nome_macchina = "collaudo"')
    a.source = _cambia(a.source, 'warnings.simplefilter("ignore")',
                       'warnings.simplefilter("ignore")' + "\n" + f"os.chdir({QUI!r})      # copia di collaudo: il progetto")
    a.source = _cambia(a.source, "DATI_DIR = cartella_dati_avvio(os.getcwd(), False, DATI_DRIVE, False)",
                       f"DATI_DIR = {dati!r}")
    a.source = _cambia(a.source, "pronto = avvio(", SENZA_RETE + "pronto = avvio(")
    c1 = per["1 · Configura"]
    for v, n in (('exchange = "BINANCE"', 'exchange = "BYBIT"'), ('mercato = "PERP"', 'mercato = "SPOT"'),
                 ('moneta = "BTC"', 'moneta = "ETH"'), ("processi = 3", "processi = 2")):
        c1.source = _cambia(c1.source, v, n)
    c1.source = _cambia(c1.source, "processi=processi)",
                        f"processi=processi, config=__import__('json').loads({json.dumps(cfg)!r}), data='20260101')")
    c5 = per["5 · La cassaforte"]
    c5.source = _cambia(c5.source, 'strategie = ""', 'strategie = "tutte le scelte"')
    c6 = per["6 · MM, stress test e verifica dei trade"]
    c6.source = _cambia(c6.source, 'trade_da_vedere = ""', 'trade_da_vedere = "1"')
    c6.source = _cambia(c6.source, "trade_da_vedere=trade_da_vedere)",
                        "trade_da_vedere=trade_da_vedere, simulazioni=300, simulazioni_stress=500)")
    return nb


def _testo_uscite(cella) -> str:
    parti = []
    for o in cella.get("outputs", []):
        if o.get("output_type") == "stream":
            parti.append(o.get("text", ""))
        elif o.get("output_type") in ("display_data", "execute_result"):
            d = o.get("data", {})
            parti.append(d.get("text/html", "") if "text/html" in d else d.get("text/plain", ""))
            if "text/markdown" in d:
                parti.append(d["text/markdown"])
        elif o.get("output_type") == "error":
            parti.append("ERRORE " + o.get("ename", "") + ": " + o.get("evalue", ""))
    return "\n".join(x if isinstance(x, str) else "".join(x) for x in parti)


def _gira(nb):
    from nbclient import NotebookClient
    client = NotebookClient(nb, timeout=900, kernel_name="python3", resources={"metadata": {"path": QUI}})
    client.execute()
    return {_titolo(c): c for c in nb.cells if c.cell_type == "code"}


def _esecuzione(nb):
    print("\nIl notebook intero con nbclient, su dati sintetici")
    try:
        from jupyter_client.kernelspec import KernelSpecManager
        kernel = "python3" in KernelSpecManager().find_kernel_specs() or _ha_ipykernel()
    except Exception:  # noqa: BLE001
        kernel = _ha_ipykernel()
    if not kernel:
        check("7. c'è un kernel di Jupyter per eseguire il notebook (ipykernel)", False,
              "manca ipykernel: pip install ipykernel")
        return
    with tempfile.TemporaryDirectory() as dati:
        _dati_sintetici(dati)
        copia = _copia_di_collaudo(nb, dati)
        try:
            uscite = _gira(copia)
        except Exception as e:  # noqa: BLE001
            check("7. il notebook gira dall'inizio alla fine senza errori", False, f"{type(e).__name__}: {e}"[:400])
            return
        t = {k: _testo_uscite(c) for k, c in uscite.items()}
        check("7. il notebook gira dall'inizio alla fine senza errori",
              not any("ERRORE" in x for x in t.values()))
        check("8. Avvio: fabbrica pronta con la macchina scritta nel campo, il file sintetico trovato",
              "Fabbrica pronta" in t["Avvio"] and "collaudo" in t["Avvio"] and SPOT in t["Avvio"])
        check("9. 1 · Configura: ricerca nuova, i tre pezzi, la cassaforte chiusa, i blocchi tolti",
              "(nuova)" in t["1 · Configura"] and "chiusa" in t["1 · Configura"]
              and "Blocchi tolti" in t["1 · Configura"])
        check("10. 2 · La ricerca: finita, con le prove e i valori degeneri", "finita" in t["2 · La ricerca"]
              and "prove in questa ricerca" in t["2 · La ricerca"])
        immagine = any("image/png" in o.get("data", {}) for o in uscite["3 · L'imbuto"].get("outputs", []))
        check("11. 3 · L'imbuto: la figura e la tabella dei passi", immagine and "cassaforte: entrate" in t["3 · L'imbuto"])
        check("12. 4 · Le strategie rimaste: la tabella con le regole in parole",
              "Le strategie rimaste" in t["4 · Le strategie rimaste"] and "Entra long" in t["4 · Le strategie rimaste"])
        check("13. 5 · La cassaforte: le scelte entrano e si vede l'esito", "La cassaforte · tratto" in t["5 · La cassaforte"]
              and ("passa" in t["5 · La cassaforte"]))
        sei = t["6 · MM, stress test e verifica dei trade"]
        check("14. 6: money management, stress test, verifica e lente; nessun rimando alle schermate del Lab, nessun "
              "FAB_SES", "money management" in sei and "stress test" in sei and "Controllo automatico" in sei
              and "Trigger scattato" in sei and "schermat" not in sei.lower() and "FAB_SES" not in sei)
        check("15. 7 · Le schede: la prima scheda è mostrata e finisce con la frase", FRASE_FINALE in t["7 · Le schede"]
              and "## Regole" in t["7 · Le schede"])
        base = cartella_asset(dati, SPOT, "M15")
        prima = {k: _eventi(base, k) for k in (INGRESSO, ESITO)}
        id_r = next(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))
        prove_prima = _righe(os.path.join(base, id_r, "prove_collaudo.csv"))
        try:
            di_nuovo = {k: _testo_uscite(c) for k, c in _gira(_copia_di_collaudo(nb, dati)).items()}
        except Exception as e:  # noqa: BLE001
            check("16. il notebook rilanciato da capo gira", False, f"{type(e).__name__}: {e}"[:400])
            return
        check("16. rilanciato da capo: stessa ricerca (riprende), nessuna prova in più; la 5 con gli stessi numeri fa "
              "un ingresso nuovo in cassaforte (10/11), con il suo esito",
              "già esiste: riprende" in di_nuovo["1 · Configura"]
              and "La cassaforte · tratto" in di_nuovo["5 · La cassaforte"]
              and {k: _eventi(base, k) for k in (INGRESSO, ESITO)} == {k: v + 1 for k, v in prima.items()}
              and _righe(os.path.join(base, id_r, "prove_collaudo.csv")) == prove_prima,
              f"{prima[INGRESSO]} ingressi, {prove_prima} righe di prove")
        schede = os.listdir(os.path.join(base, id_r, "schede"))
        check("17. le schede .md e .json sono nella cartella della ricerca, il notebook vero è rimasto senza output",
              any(x.endswith(".md") for x in schede) and any(x.endswith(".json") for x in schede)
              and all(not c.outputs for c in _leggi().cells if c.cell_type == "code"))


def _dati_sintetici(dati: str) -> None:
    n = int(sum(CONFINI[k] for k in ("ricerca_ore", "selezione_ore", "cassaforte_ore")) * 4) + 100
    sintetici.scrivi_storico(dati, SPOT, "M15",
                             sintetici.mercato_piantato(n, seme=5, minuti=15, inizio="2024-01-01", prezzo=2000.0))


def prepara_copia(cartella: str) -> str:
    """
    --copia: una cartella con dati sintetici e la copia di collaudo del notebook, da aprire in VS Code e lanciare
    cella per cella (stessi valori del collaudo). Il notebook vero non cambia.
    """
    import nbformat
    cartella = os.path.abspath(cartella)
    if os.path.exists(cartella) and os.listdir(cartella):
        raise SystemExit(f"{cartella} esiste e non è vuota: scegli un'altra cartella (non cancello niente).")
    dati = os.path.join(cartella, "dati_sintetici")
    os.makedirs(dati)
    _dati_sintetici(dati)
    percorso = os.path.join(cartella, "Fabbrica_collaudo_sintetico.ipynb")
    nbformat.write(_copia_di_collaudo(_leggi(), dati), percorso)
    print(f"Pronto. Apri in VS Code: {percorso}")
    print(f"Dati sintetici in: {dati}")
    return percorso


def _ha_ipykernel() -> bool:
    import importlib.util
    return importlib.util.find_spec("ipykernel") is not None


def _eventi(base: str, tipo: str) -> int:
    return sum(1 for e in registro.leggi_registro(base) if e.get("tipo") == tipo)


def _righe(percorso: str) -> int:
    with open(percorso, encoding="utf-8") as f:
        return sum(1 for _ in f)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--copia":
        prepara_copia(sys.argv[2] if len(sys.argv) > 2 else os.path.join(tempfile.gettempdir(), "collaudo_fabbrica"))
        sys.exit(0)
    sys.exit(esegui())
