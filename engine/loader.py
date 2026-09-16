"""
Loader dinamico delle condizioni.

Importa (o re-importa) tutti i moduli .py presenti nella cartella delle
condizioni, cosi' i decorator @register_entry/@register_exit/@register_filter
vengono eseguiti e popolano il registry. Questo e' cio' che permette
all'utente di aggiungere un nuovo file .py in conditions/ in qualunque
momento e vederlo comparire nel motore senza modificare nient'altro.
"""
from __future__ import annotations
import importlib
import pkgutil
import sys
from pathlib import Path

from .registry import clear_registry


def load_conditions(conditions_dir: str = "conditions", reset: bool = True) -> list[str]:
    """
    Importa tutti i moduli .py in `conditions_dir` (non ricorsivo).

    reset=True (default): svuota il registry prima di importare, cosi' una
    ri-esecuzione nel notebook (dopo aver modificato un file) riflette
    esattamente lo stato attuale su disco, senza errori di "nome duplicato".

    Ritorna la lista dei moduli importati (utile per un controllo rapido).
    """
    conditions_path = Path(conditions_dir).resolve()
    if not conditions_path.is_dir():
        raise FileNotFoundError(f"Cartella condizioni non trovata: {conditions_path}")

    if reset:
        clear_registry()

    parent = str(conditions_path.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    package_name = conditions_path.name
    imported = []
    for _finder, module_name, is_pkg in pkgutil.iter_modules([str(conditions_path)]):
        if is_pkg:
            continue
        full_name = f"{package_name}.{module_name}"
        if full_name in sys.modules:
            importlib.reload(sys.modules[full_name])
        else:
            importlib.import_module(full_name)
        imported.append(full_name)
    return imported
