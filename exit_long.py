"""
Condizioni di EXIT — lato LONG.

Stessa logica delle condizioni di Entry (entry_long.py): funzione(df) ->
Series booleana. Niente decoratori qui, a differenza della versione
completa: la registrazione nel motore (engine.registry) avviene tramite
registra_exit_long(), chiamata a mano nel notebook — stesso pattern di
registra_trigger_long() in entry_long.py.

`pair` (nel dizionario, non nella funzione): etichetta che dichiara
"questa exit long e la short con lo stesso pair sono la stessa idea nelle
due direzioni". Serve solo alle strategie bidirezionali future
(engine.registry.list_exit_pairs()) — oggi non viene ancora usata da
run_exit_search_bt, che prende un nome di exit per volta.
"""
import pandas as pd


def exit_rsi_overbought(df: pd.DataFrame, threshold: float = 70.0) -> pd.Series:
    """RSI sopra una soglia (ipercomprato) -> chiudi il long."""
    return df["rsi"] > threshold


def exit_ema_bearish(df: pd.DataFrame) -> pd.Series:
    """EMA veloce torna sotto EMA lenta -> il trend rialzista si esaurisce."""
    return df["ema20"] < df["ema50"]


def exit_macd_bearish(df: pd.DataFrame) -> pd.Series:
    """MACD scende sotto la sua signal line -> chiudi il long."""
    return df["macd"] < df["macd_signal"]


def exit_none_long(df: pd.DataFrame) -> pd.Series:
    """
    Segnaposto: nessuna regola di uscita, sempre False. Usala quando vuoi
    che la posizione long si chiuda SOLO per stop loss/take profit (se
    attivi) e per il tetto a tempo — mai per una regola.
    """
    return pd.Series(False, index=df.index)


# nome -> (funzione, pair)
EXIT_LONG = {
    "X1_RSI_OVERBOUGHT":    (exit_rsi_overbought, "RSI_EXTREME"),
    "X2_EMA_BEARISH_CROSS": (exit_ema_bearish,    "EMA_CROSS"),
    "X3_MACD_BEARISH":      (exit_macd_bearish,   "MACD_CROSS"),
    "X0_NO_EXIT":           (exit_none_long,      "NO_EXIT"),
}


def registra_exit_long():
    """
    Registra tutte le exit long nel motore (engine.registry), cosi'
    run_exit_search_bt le trova da sola tramite get_exit(nome).

    Va chiamata una volta prima di run_exit_search_bt. E' sicura da
    richiamare piu' volte nella stessa sessione: i nomi gia' registrati
    vengono saltati con un avviso, non sollevano errore.
    """
    from engine.registry import register_exit, list_exits

    gia_presenti = set(list_exits())
    nuovi = 0
    for nome, (funzione, pair) in EXIT_LONG.items():
        if nome in gia_presenti:
            print(f"[registra_exit_long] '{nome}' gia' registrata, salto.")
            continue
        register_exit(nome, direction=1, pair=pair)(funzione)
        nuovi += 1
    print(f"[registra_exit_long] {nuovi} exit long registrate "
          f"({len(EXIT_LONG) - nuovi} gia' presenti).")
