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

from helpers import _evento, _cross_down, _vsa_figure


def exit_cycle_turn_down(df: pd.DataFrame) -> pd.Series:
    """
    Il ciclo dominante gira al ribasso -> chiudi il long.

    E' un evento, non uno stato: vera solo sulla barra in cui
    `ciclo_pendenza` (engine/indicatori.py) passa da positiva a negativa.
    Un long aperto mentre il ciclo sta gia' scendendo non viene chiuso
    subito: aspetta il prossimo giro.

    Dal 7/10/2026 prende il posto di X1_RSI_OVERBOUGHT (uscita di prova).

    Fonte dell'idea: Sofien Kaabar, "Forecasting Market Cycles with Fourier
    Transform in Python", 29/9/2026, https://medium.com/@kaabar-sofien/forecasting-market-cycles-with-fourier-transform-in-python-9b29c110cd3c
    """
    zero = pd.Series(0.0, index=df.index)
    return _evento(_cross_down(df["ciclo_pendenza"], zero))


def exit_vsa_bearish(df: pd.DataFrame) -> pd.Series:
    """
    Compare una figura VSA ribassista -> chiudi il long: "climax",
    "no demand" o "sforzo al ribasso senza risultato" (effort_down_reverse).

    Sono le figure con cui la fonte chiude un long senza il punteggio di
    contesto. Classificazioni in helpers._vsa_figure.

    Dall'8/10/2026 prende il posto di X2_EMA_BEARISH_CROSS (uscita di prova).

    Fonte: PyQuantLab, "Volume Spread Analysis (VSA) Strategy: Quantifying
    Market Action for Trading Signals with Rolling Backtesting", 20/6/2025,
    https://medium.com/@pyquantlab/volume-spread-analysis-vsa-strategy-quantifying-market-action-for-trading-signals-with-rolling-9aa57fb79fe9
    """
    figure = _vsa_figure(df)
    return figure["climax_sell"] | figure["no_demand"] | figure["effort_down_reverse"]


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
    "X1_CYCLE_TURN_DOWN":   (exit_cycle_turn_down, "CYCLE_TURN"),
    "X2_VSA_BEARISH":       (exit_vsa_bearish,     "VSA"),
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
