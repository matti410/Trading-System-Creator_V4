"""
Il generatore di indicatori e trigger, prezzo + volume (docs/83).

Crea indicatori nuovi da ricette fisse (ingredienti e operazioni, al massimo 3), sempre con almeno un ingrediente di
prezzo e uno di volume, e ne ricava trigger long e short che attraversano livelli fissi (zero, media 20 barre,
percentili mobili su 500 barre). Non guarda dati veri: le ricette uguali si tolgono su un dataset sintetico fisso.

Si lancia dal terminale, dalla cartella del progetto:

    python -m engine.generatore --n 80          # crea dati_catalogo/generati_v1.json con le prime 80 ricette

Moduli: ricette.py (ricette ed elenco), trigger.py (da indicatore a trigger), catalogo.py (catalogo e file).
Modulo ADDITIVO: non tocca entry_long.py, entry_short.py, la fabbrica e i loro test.
"""
from .catalogo import (VERSIONE, calcola_trigger, carica_catalogo, dataset_sintetico, famiglie_del_catalogo,
                       genera_catalogo, percorso_catalogo, registra_trigger_generati, salva_catalogo,
                       segnala_degeneri, trigger_del_catalogo)
from .trigger import TriggerGenerato, svuota_cache

__all__ = ["VERSIONE", "TriggerGenerato", "calcola_trigger", "carica_catalogo", "dataset_sintetico",
           "famiglie_del_catalogo", "genera_catalogo", "percorso_catalogo", "registra_trigger_generati",
           "salva_catalogo", "segnala_degeneri", "svuota_cache", "trigger_del_catalogo"]
