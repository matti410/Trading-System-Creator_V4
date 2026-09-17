"""
Condizioni di EXIT — lato SHORT. Vedi exit_long.py per la spiegazione del
pattern (funzione semplice, dizionario nome -> (funzione, pair), bridge
verso la registry).
"""
import pandas as pd


def exit_short_rsi_oversold(df: pd.DataFrame, threshold: float = 30.0) -> pd.Series:
    """RSI sotto una soglia (ipervenduto) -> chiudi lo short."""
    return df["rsi"] < threshold


def exit_short_ema_bullish(df: pd.DataFrame) -> pd.Series:
    """EMA veloce torna sopra EMA lenta -> il trend ribassista si esaurisce."""
    return df["ema20"] > df["ema50"]


def exit_short_macd_bullish(df: pd.DataFrame) -> pd.Series:
    """MACD risale sopra la sua signal line -> chiudi lo short."""
    return df["macd"] > df["macd_signal"]


def exit_none_short(df: pd.DataFrame) -> pd.Series:
    """Segnaposto: nessuna regola di uscita, sempre False. Vedi X0_NO_EXIT in exit_long.py."""
    return pd.Series(False, index=df.index)


# nome -> (funzione, pair)
EXIT_SHORT = {
    "X1_SHORT_RSI_OVERSOLD":      (exit_short_rsi_oversold, "RSI_EXTREME"),
    "X2_SHORT_EMA_BULLISH_CROSS": (exit_short_ema_bullish,  "EMA_CROSS"),
    "X3_SHORT_MACD_BULLISH":      (exit_short_macd_bullish, "MACD_CROSS"),
    "X0_SHORT_NO_EXIT":           (exit_none_short,         "NO_EXIT"),
}


def registra_exit_short():
    """Vedi registra_exit_long() in exit_long.py per il comportamento."""
    from engine.registry import register_exit, list_exits

    gia_presenti = set(list_exits())
    nuovi = 0
    for nome, (funzione, pair) in EXIT_SHORT.items():
        if nome in gia_presenti:
            print(f"[registra_exit_short] '{nome}' gia' registrata, salto.")
            continue
        register_exit(nome, direction=-1, pair=pair)(funzione)
        nuovi += 1
    print(f"[registra_exit_short] {nuovi} exit short registrate "
          f"({len(EXIT_SHORT) - nuovi} gia' presenti).")
