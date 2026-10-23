"""
La suite RAPIDA dei test (21/10/2026, decisione di Mattia in docs/65 §13).

A cosa serve
------------
Durante il lavoro: in 2-3 minuti fa girare le suite `test_*.py` legate al
codice toccato, invece di tutte. La suite COMPLETA resta obbligatoria prima
di ogni Pull request: `python suite_rapida.py --tutte`. Dal 21/10/2026
(decisione di Mattia in docs/65 §17.5) anche la completa gira 3 suite alla
volta, le piu' lunghe per prime: circa 11 minuti invece di 28. Le suite sono
processi separati e non condividono file, quindi i risultati non cambiano;
cambia solo l'ordine delle righe a schermo (ognuna appare quando la sua suite
finisce).

Come sceglie
------------
1. I file cambiati rispetto a main (commit del ramo, modifiche non ancora
   committate, file nuovi).
2. I moduli che li importano, anche indirettamente (vetrina importa
   exit_search_bt, quindi toccare exit_search_bt tocca anche vetrina).
3. Le suite che usano quei moduli, o che sono cambiate loro stesse: prima
   quelle che usano direttamente un file cambiato, poi le altre; a parita',
   le piu' brevi. Si aggiungono finche' stanno nel tempo (`--secondi`, 150
   di default), girando 3 alla volta. Quelle che restano fuori le elenca.
Se non e' cambiato codice, fa girare le suite piu' brevi come prova generale.

Come si lancia (dalla cartella del progetto; non serve PYTHONIOENCODING)
-----------------------------------------------------------------------
    python suite_rapida.py                     # la rapida
    python suite_rapida.py --tutte             # la completa, 3 suite alla volta
    python suite_rapida.py --tutte --insieme 1 # la completa, una suite dopo l'altra
    python suite_rapida.py test_funding test_unita     # solo quelle indicate
    python suite_rapida.py --motore veloce     # con il motore veloce (TSC_MOTORE)
    python suite_rapida.py --secondi 300       # piu' tempo, piu' suite

Alla fine stampa «SUITE RAPIDA: n/n suite superate» (o «SUITE COMPLETA»).
Una suite e' superata se la sua ultima riga RISULTATO e' «n/n».
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

QUI = Path(__file__).resolve().parent

# secondi di ogni suite, misurati il 21/10/2026 sul PC di Mattia (una alla volta, dopo E4)
DURATE = {
    "test_vetrina": 245, "test_indicatori_tradingview": 215, "test_vetrina_trigger": 207,
    "test_vsa_modulo_unico": 200, "test_salto": 76, "test_idee_articoli": 73,
    "test_momentum_intraday": 70, "test_regime": 64, "test_condizioni_orarie": 54,
    "test_multi_timeframe": 46, "test_sentiment": 45, "test_algoxplorer": 41,
    "test_motore_veloce": 41, "test_rosa": 36, "test_mercato_nullo": 33, "test_ore_utc": 31,
    "test_exchange": 27, "test_stagionalita": 27, "test_simboli": 25, "test_velocita": 19,
    "test_quarantena_trade": 13, "test_quintili": 13, "test_money_management": 11,
    "test_funding": 9, "test_famiglie": 7, "test_confidenza": 6, "test_unita": 4,
    "test_barre_per_lato": 3, "test_giornata_utc": 3, "test_entry_composita": 2,
    "test_filtri_tempo": 2, "test_inversione": 2, "test_montecarlo": 2, "test_portabilita": 2,
    "test_tempo_prezzo": 2, "test_entry_metro": 1, "test_sessioni": 1,
    "test_atlante": 25, "test_mm_stress_bp": 55
}
INSIEME = 3          # suite che girano insieme, nella rapida e nella completa
RISULTATO = re.compile(r"RISULTATO:\s*(\d+)\s*/\s*(\d+)")


def suite_tutte() -> list[str]:
    return sorted(p.stem for p in QUI.glob("test_*.py"))


def file_cambiati(base: str) -> set[str]:
    """Percorsi (con /) cambiati rispetto a `base`: commit, modifiche, file nuovi."""
    comandi = (["git", "diff", "--name-only", f"{base}...HEAD"], ["git", "diff", "--name-only", "HEAD"],
               ["git", "ls-files", "--others", "--exclude-standard"])
    cambiati = set()
    for c in comandi:
        try:
            r = subprocess.run(c, cwd=QUI, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            continue
        cambiati |= {riga.strip() for riga in r.stdout.splitlines() if riga.strip()}
    return cambiati


def _moduli_python() -> dict[str, Path]:
    """nome importabile -> file: engine.x per engine/x.py, x per i file in cima."""
    moduli = {f"engine.{p.stem}": p for p in (QUI / "engine").glob("*.py") if p.stem != "__init__"}
    moduli.update({p.stem: p for p in QUI.glob("*.py")
                   if not p.stem.startswith("test_") and p.stem != "suite_rapida"})
    return moduli


def _importa(testo: str, modulo: str) -> bool:
    """Il testo importa `modulo`? (engine.x: anche «from engine import x» e «from .x import»)."""
    if modulo.startswith("engine."):
        nome = modulo.split(".", 1)[1]
        return bool(re.search(rf"engine\.{nome}\b|from\s+engine\s+import\s+[^\n]*\b{nome}\b"
                              rf"|from\s+\.{nome}\s+import|from\s+\.\s+import\s+[^\n]*\b{nome}\b", testo))
    return bool(re.search(rf"^\s*(import|from)\s+{modulo}\b", testo, re.M))


def scegli(cambiati: set[str], secondi: float) -> tuple[list[str], list[str], str]:
    """(da lanciare, lasciate fuori, perche')."""
    moduli = _moduli_python()
    testi = {m: p.read_text(encoding="utf-8", errors="replace") for m, p in moduli.items()}
    toccati = {m for m, p in moduli.items() if p.relative_to(QUI).as_posix() in cambiati}
    # chi importa un modulo toccato e' toccato anche lui (fino a che non cambia piu' niente)
    indiretti = set(toccati)
    while True:
        nuovi = {m for m, t in testi.items() if m not in indiretti
                 and any(_importa(t, x) for x in indiretti)}
        if not nuovi:
            break
        indiretti |= nuovi
    suite = suite_tutte()
    test_cambiati = {Path(c).stem for c in cambiati if Path(c).name.startswith("test_")}
    if not toccati and not test_cambiati:
        brevi = [s for s in sorted(suite, key=lambda s: DURATE.get(s, 30)) if DURATE.get(s, 30) <= 10]
        return brevi, [], "nessun file di codice cambiato rispetto a main: le suite piu' brevi"
    vicine, lontane = [], []
    for s in suite:
        t = (QUI / f"{s}.py").read_text(encoding="utf-8", errors="replace")
        if s in test_cambiati or any(_importa(t, m) for m in toccati):
            vicine.append(s)
        elif any(_importa(t, m) for m in indiretti):
            lontane.append(s)
    ordinate = (sorted(vicine, key=lambda s: DURATE.get(s, 30))
                + sorted(lontane, key=lambda s: DURATE.get(s, 30)))
    scelte, fuori, somma = [], [], 0.0
    for s in ordinate:
        d = DURATE.get(s, 30)
        if (somma + d) / INSIEME * 1.3 <= secondi:     # 1,3: girando insieme si rallentano un po'
            scelte.append(s)
            somma += d
        else:
            fuori.append(s)
    nomi = sorted(m.replace("engine.", "") for m in toccati)
    return scelte, fuori, f"codice cambiato: {', '.join(nomi) or '—'}"


def lancia(nome: str, ambiente: dict) -> tuple[str, bool, str, float]:
    t0 = time.perf_counter()
    r = subprocess.run([sys.executable, f"{nome}.py"], cwd=QUI, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=ambiente)
    dt = time.perf_counter() - t0
    righe = [m for m in RISULTATO.finditer(r.stdout)]
    if not righe:
        coda = (r.stdout + r.stderr).strip().splitlines()[-3:]
        return nome, False, "nessuna riga RISULTATO · " + " | ".join(coda), dt
    ok, tot = int(righe[-1].group(1)), int(righe[-1].group(2))
    return nome, ok == tot and r.returncode == 0, f"RISULTATO: {ok}/{tot}", dt


def main(argv: list[str]) -> int:
    tutte = "--tutte" in argv
    secondi, motore, base, nomi, insieme = 150.0, None, "main", [], INSIEME
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--secondi":
            secondi = float(argv[i + 1]); i += 1
        elif a == "--motore":
            motore = argv[i + 1]; i += 1
        elif a == "--base":
            base = argv[i + 1]; i += 1
        elif a == "--insieme":
            insieme = max(1, int(argv[i + 1])); i += 1
        elif not a.startswith("--"):
            nomi.append(Path(a).stem)
        i += 1
    ambiente = dict(os.environ, PYTHONIOENCODING="utf-8")
    if motore:
        ambiente["TSC_MOTORE"] = motore
    if tutte:
        # le piu' lunghe per prime: cosi' alla fine non resta una suite lunga da sola
        scelte = sorted(suite_tutte(), key=lambda s: -DURATE.get(s, 30))
        fuori, perche, titolo = [], "tutte le suite", "SUITE COMPLETA"
    elif nomi:
        mancanti = [n for n in nomi if not (QUI / f"{n}.py").exists()]
        if mancanti:
            print(f"suite inesistenti: {mancanti}")
            return 2
        scelte, fuori, perche, titolo = nomi, [], "indicate a mano", "SUITE RAPIDA"
    else:
        scelte, fuori, perche = scegli(file_cambiati(base), secondi)
        titolo = "SUITE RAPIDA"
    stima = sum(DURATE.get(s, 30) for s in scelte) / insieme * (1.3 if insieme > 1 else 1)
    print(f"{titolo} · {perche} · {insieme} alla volta" + (f" · motore {motore}" if motore else ""))
    print(f"{len(scelte)} suite, circa {stima / 60:.1f} minuti: {', '.join(scelte)}")
    if fuori:
        print(f"lasciate alla suite completa ({len(fuori)}): {', '.join(fuori)}")
    print()
    t0 = time.perf_counter()
    esiti = []
    with ThreadPoolExecutor(max_workers=insieme) as ex:
        futuri = [ex.submit(lancia, s, ambiente) for s in scelte]
        for f in as_completed(futuri):          # una riga appena una suite finisce
            nome, ok, riga, dt = f.result()
            esiti.append((nome, ok))
            print(f"  [{'OK ' if ok else 'KO '}] {nome:<32} {riga}  ({dt:.0f} s)", flush=True)
    passate = sum(ok for _, ok in esiti)
    falliti = sorted(nome for nome, ok in esiti if not ok)
    if falliti:
        print(f"\nNON superate: {', '.join(falliti)}")
    print(f"\n{titolo}: {passate}/{len(esiti)} suite superate in {(time.perf_counter() - t0) / 60:.1f} minuti")
    if not tutte:
        print("Prima della Pull request: python suite_rapida.py --tutte")
    return 0 if passate == len(esiti) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
