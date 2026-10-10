import MetaTrader5
import pandas
import datetime as dt
import pytz
import pandas as pd
#import exceptions


# Function to start Meta Trader 5 (MT5)
def start_mt5(username, password, server, path):
    """
    Initializes and logs into MT5
    :param username: 8 digit integer
    :param password: string
    :param server: string
    :param path: string
    :return: True if successful, Error if not
    """
    # Ensure that all variables are the correct type
    uname = int(username)  # Username must be an int
    pword = str(password)  # Password must be a string
    trading_server = str(server)  # Server must be a string
    filepath = str(path)  # Filepath must be a string

    # Attempt to start MT5
    try:
        metaTrader_init = MetaTrader5.initialize(login=uname, password=pword, server=trading_server, path=filepath)
    except Exception as e:
        print(f"Error initializing MetaTrader: {e}")
        raise exceptions.MetaTraderInitializeError

    # Attempt to login to MT5
    if not metaTrader_init:
        raise exceptions.MetaTraderInitializeError
    else:
        try:
            metaTrader_login = MetaTrader5.login(login=uname, password=pword, server=trading_server)
        except Exception as e:
            print(f"Error loging in to MetaTrader: {e}")
            raise exceptions.MetaTraderLoginError

    # Return True if initialization and login are successful
    if metaTrader_login:
        return True


# Function to initialize a symbol on MT5
def initialize_symbols(symbol_array):
    """
    Function to initialize a symbol on MT5. Note that different brokers have different symbols.
    To read more: https://trading-data-analysis.pro/everything-you-need-to-connect-your-python-trading-bot-to-metatrader-5-de0d8fb80053
    :param symbol_array: List of symbols to be initialized
    :return: True if all symbols enabled
    """
    # Get a list of all symbols supported in MT5
    all_symbols = MetaTrader5.symbols_get()
    # Create a list to store all the symbols
    symbol_names = []
    # Add the retrieved symbols to the list
    for symbol in all_symbols:
        symbol_names.append(symbol.name)

    # Check each provided symbol in symbol_array to ensure it exists
    for provided_symbol in symbol_array:
        if provided_symbol in symbol_names:
            # If it exists, enable
            if MetaTrader5.symbol_select(provided_symbol, True):
                pass
            else:
                # Print the outcome to screen. Custom Logging/Error Handling not yet created
                print(f"Error creating symbol {provided_symbol}. Symbol not enabled.")
                # Return a generic value error. Custom Error Handling not yet created.
                raise exceptions.MetaTraderSymbolUnableToBeEnabledError
        else:
            # Print the outcome to screen. Custom Logging/Error Handling not yet created
            print(f"Symbol {provided_symbol} does not exist in this MT5 implementation. Symbol not enabled.")
            # Return a generic syntax error. Custom Error Handling not yet enabled
            raise exceptions.MetaTraderSymbolDoesNotExistError
    # Return true if all symbols enabled
    return True


# Function to place a trade on MT5
def place_BUY_order(sym, lot_volume, sl, tp):
    request = {"action": MetaTrader5.TRADE_ACTION_DEAL,
               "symbol": sym,
               "volume": lot_volume,  # FLOAT
               "type": MetaTrader5.ORDER_TYPE_BUY,
               "price": MetaTrader5.symbol_info_tick("EURUSD").ask,
               "sl": sl,  # FLOAT
               "tp": tp,  # FLOAT
               "deviation": 20,  # INTERGER
               "magic": 234000,  # INTERGER
               "comment": "python script open",
               "type_time": MetaTrader5.ORDER_TIME_GTC,
               "type_filling": MetaTrader5.ORDER_FILLING_IOC, }

    order = MetaTrader5.order_send(request)
    print(order)

# Function to cancel an order
def cancel_order(order_number):
    """
    Function to cancel an order
    :param order_number: Int
    :return:
    """
    # Create the request
    request = {
        "action": MetaTrader5.TRADE_ACTION_REMOVE,
        "order": order_number,
        "comment": "Order Removed"
    }
    # Send order to MT5
    order_result = MetaTrader5.order_send(request)
    if order_result[0] == 10009:
        return True
    else:
        print(f"Error cancelling order. Details: {order_result}")
        raise exceptions.MetaTraderCancelOrderError


# Function to modify an open position
def modify_position(order_number, symbol, new_stop_loss, new_take_profit):
    """
    Function to modify a position
    :param order_number: Int
    :param symbol: String
    :param new_stop_loss: Float
    :param new_take_profit: Float
    :return: Boolean
    """
    # Create the request
    request = {
        "action": MetaTrader5.TRADE_ACTION_SLTP,
        "symbol": symbol,
        "sl": new_stop_loss,
        "tp": new_take_profit,
        "position": order_number
    }
    # Send order to MT5
    order_result = MetaTrader5.order_send(request)
    if order_result[0] == 10009:
        return True
    else:
        print(f"Error modifying position. Details: {order_result}")
        raise exceptions.MetaTraderModifyPositionError


# Function to retrieve all open orders from MT5
def get_open_orders():
    """
    Function to retrieve a list of open orders from MetaTrader 5
    :return: List of open orders
    """
    orders = MetaTrader5.orders_get()
    order_array = []
    for order in orders:
        order_array.append(order[0])
    return order_array


# Function to retrieve all open positions
def get_open_positions():
    """
    Function to retrieve a list of open orders from MetaTrader 5
    :return: list of positions
    """
    # Get position objects
    positions = MetaTrader5.positions_get()
    # Return position objects
    return positions


# Function to close an open position
def close_position(order_number, symbol, volume, order_type, price, comment):
    """
    Function to close an open position from MetaTrader 5
    :param order_number: int
    :return: Boolean
    """
    # Create the request
    request = {
        'action': MetaTrader5.TRADE_ACTION_DEAL,
        'symbol': symbol,
        'volume': volume,
        'position': order_number,
        'price': price,
        'type_time': MetaTrader5.ORDER_TIME_GTC,
        'type_filling': MetaTrader5.ORDER_FILLING_IOC,
        'comment': comment
    }

    if order_type == "SELL":
        request['type'] = MetaTrader5.ORDER_TYPE_SELL
    elif order_type == "BUY":
        request['type'] = MetaTrader5.ORDER_TYPE_BUY
    else:
        print(f"Incorrect syntax for position close {order_type}")
        raise SyntaxError

    # Place the order
    result = MetaTrader5.order_send(request)
    if result[0] == 10009:
        return True
    else:
        print(f"Error closing position. Details: {result}")
        raise exceptions.MetaTraderClosePositionError


# Function to convert a timeframe string in MetaTrader 5 friendly format
def set_query_timeframe(timeframe):
    # Implement a Pseudo Switch statement. Note that Python 3.10 implements match / case but have kept it this way for
    # backwards integration
    if timeframe == "M1":
        return MetaTrader5.TIMEFRAME_M1
    elif timeframe == "M2":
        return MetaTrader5.TIMEFRAME_M2
    elif timeframe == "M3":
        return MetaTrader5.TIMEFRAME_M3
    elif timeframe == "M4":
        return MetaTrader5.TIMEFRAME_M4
    elif timeframe == "M5":
        return MetaTrader5.TIMEFRAME_M5
    elif timeframe == "M6":
        return MetaTrader5.TIMEFRAME_M6
    elif timeframe == "M10":
        return MetaTrader5.TIMEFRAME_M10
    elif timeframe == "M12":
        return MetaTrader5.TIMEFRAME_M12
    elif timeframe == "M15":
        return MetaTrader5.TIMEFRAME_M15
    elif timeframe == "M20":
        return MetaTrader5.TIMEFRAME_M20
    elif timeframe == "M30":
        return MetaTrader5.TIMEFRAME_M30
    elif timeframe == "H1":
        return MetaTrader5.TIMEFRAME_H1
    elif timeframe == "H2":
        return MetaTrader5.TIMEFRAME_H2
    elif timeframe == "H3":
        return MetaTrader5.TIMEFRAME_H3
    elif timeframe == "H4":
        return MetaTrader5.TIMEFRAME_H4
    elif timeframe == "H6":
        return MetaTrader5.TIMEFRAME_H6
    elif timeframe == "H8":
        return MetaTrader5.TIMEFRAME_H8
    elif timeframe == "H12":
        return MetaTrader5.TIMEFRAME_H12
    elif timeframe == "D1":
        return MetaTrader5.TIMEFRAME_D1
    elif timeframe == "W1":
        return MetaTrader5.TIMEFRAME_W1
    elif timeframe == "MN1":
        return MetaTrader5.TIMEFRAME_MN1
    else:
        print(f"Incorrect timeframe provided. {timeframe}")
        raise ValueError


# Function to convert a timeframe string in minutes friendly format
def set_minutes_timeframe(timeframe):
    # Implement a Pseudo Switch statement. Note that Python 3.10 implements match / case but have kept it this way for
    # backwards integration
    if timeframe == "M1":
        return 1
    elif timeframe == "M2":
        return 2
    elif timeframe == "M3":
        return 3
    elif timeframe == "M4":
        return 4
    elif timeframe == "M5":
        return 5
    elif timeframe == "M6":
        return 6
    elif timeframe == "M10":
        return 10
    elif timeframe == "M12":
        return 12
    elif timeframe == "M15":
        return 15
    elif timeframe == "M20":
        return 20
    elif timeframe == "M30":
        return 30
    elif timeframe == "H1":
        return 60
    elif timeframe == "H2":
        return 120
    elif timeframe == "H3":
        return 180
    elif timeframe == "H4":
        return 240
    elif timeframe == "H6":
        return 360
    elif timeframe == "H8":
        return 480
    elif timeframe == "H12":
        return 720
    elif timeframe == "D1":
        return 1440
    elif timeframe == "W1":
        return 7200
    elif timeframe == "MN1":
        return 28800
    else:
        print(f"Incorrect timeframe provided. {timeframe}")
        raise ValueError


# Function to query previous candlestick data from MT5
def get_data(symbol, n, timeframe=MetaTrader5.TIMEFRAME_D1):
    """ Function to import the data of the chosen symbol"""

    # Initialize the connection if there is not
    MetaTrader5.initialize()

    # Current date extract
    utc_from = dt.datetime.now()

    # Import the data into a tuple
    rates = MetaTrader5.copy_rates_from(symbol, timeframe, utc_from, n)

    # Tuple to dataframe
    rates_frame = pd.DataFrame(rates)

    # Convert time in seconds into the datetime format
    rates_frame['time'] = pd.to_datetime(rates_frame['time'], unit='s')

    # Convert the column "time" in the right format
    rates_frame['time'] = pd.to_datetime(rates_frame['time'], format='%Y-%m-%d')

    rates_frame.rename(columns={'time': 'Date', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close',
                                'tick_volume': 'Volume', }, inplace=True)
    rates_frame.set_index('Date', inplace=True)
    #rates_frame.drop(['spread', 'real_volume'], axis=1, inplace=True)
    return rates_frame


# Function to retrieve latest tick for a symbol
def retrieve_latest_tick(symbol):
    """
    Function to retrieve the latest tick for a symbol
    :param symbol: String
    :return: Dictionary object
    """
    # Retrieve the tick information
    tick = MetaTrader5.symbol_info_tick(symbol)._asdict()
    spread = tick['ask'] - tick['bid']
    tick['spread'] = spread
    return tick


# Function to retrieve ticks from a time range
def retrieve_tick_time_range(start_time_utc, finish_time_utc, symbol, dataframe=False):
    # Set option in MT5 terminal for Unlimited bars
    # Check time format of start time
    if type(start_time_utc) != dt.datetime:
        print(f"Time range tick start time is in incorrect format")
        raise ValueError
    # Check time format of finish time
    if type(finish_time_utc) != dt.datetime:
        print(f"Time range tick finish time is in incorrect format")
        raise ValueError
    # Retrieve ticks
    ticks = MetaTrader5.copy_ticks_range(symbol, start_time_utc, finish_time_utc, MetaTrader5.COPY_TICKS_INFO)
    # Convert into dataframe only if Dataframe set to True
    if dataframe:
        # Convert into a dataframe
        ticks_data_frame = pandas.DataFrame(ticks)
        # Add spread
        ticks_data_frame['spread'] = ticks_data_frame['ask'] - ticks_data_frame['bid']
        # Add symbol
        ticks_data_frame['symbol'] = symbol
        # Format integers into signed integers (postgres doesn't support unsigned int)
        ticks_data_frame['time'] = ticks_data_frame['time'].astype('int64')
        ticks_data_frame['volume'] = ticks_data_frame['volume'].astype('int64')
        ticks_data_frame['time_msc'] = ticks_data_frame['time_msc'].astype('int64')
        return ticks_data_frame
    return ticks


# Function to retrieve candlestick data for a specified time range
def retrieve_candlestick_data_range(start_time_utc, finish_time_utc, symbol, timeframe, dataframe=False):
    # Set option in MT5 terminal for Unlimited bars
    # Check time format of start time
    if type(start_time_utc) != dt.datetime:
        print(f"Time range tick start time is in incorrect format")
        raise ValueError
    # Check time format of finish time
    if type(finish_time_utc) != dt.datetime:
        print(f"Time range tick finish time is in incorrect format")
        raise ValueError
    # Convert the timeframe into MT5 compatible format
    timeframe_value = set_query_timeframe(timeframe)
    # Retrieve the data
    candlestick_data = MetaTrader5.copy_rates_range(symbol, timeframe_value, start_time_utc, finish_time_utc)
    if dataframe:
        # Convert to a dataframe
        candlestick_dataframe = pandas.DataFrame(candlestick_data)
        # Add in symbol and timeframe columns
        # candlestick_dataframe['symbol'] = symbol
        # candlestick_dataframe['timeframe'] = timeframe
        # Convert integers into signed integers (postgres doesn't support unsigned int)
        candlestick_dataframe['time'] = pd.to_datetime(candlestick_dataframe['time'], unit='s')
        # Convert the column "time" in the right format
        candlestick_dataframe['time'] = pd.to_datetime(candlestick_dataframe['time'], format='%Y-%m-%d')
        #candlestick_dataframe['time'] = candlestick_dataframe['time'].astype('int64')
        candlestick_dataframe.rename(columns={'time': 'Date', 'open': 'Open', 'high': 'High', 'low': 'Low',
                                              'close': 'Close','tick_volume': 'Volume', }, inplace=True)
        candlestick_dataframe.set_index('Date', inplace=True)
        candlestick_dataframe.drop(['real_volume'], axis=1, inplace=True)
        # Return completed dataframe
        return candlestick_dataframe
    else:
        return candlestick_data


