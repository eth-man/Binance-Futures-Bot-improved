import math

from binance_f import RequestClient
from binance_f.constant.test import *
from binance_f.base.printobject import *
from binance_f.model.constant import *
import talib.abstract as ta
import pandas as pd
import numpy as np
import time
import sys, os
import config as cfg
from decimal import Decimal, getcontext, ROUND_DOWN
import datetime


def getStdOut():
    return sys.stdout


def blockPrint():
    sys.stdout = open(os.devnull, 'w')


# Restore
def enablePrint(std):
    sys.stdout = std


def singlePrint(string, std):
    enablePrint(std)
    print(string)
    blockPrint()


# create a binance request client
def init_client():
    client = RequestClient(api_key=cfg.getPublicKey(), secret_key=cfg.getPrivateKey(), url=cfg.getBotSettings().api_url)
    return client


# Get futures balances. We are interested in USDT by default as this is what we use as margin.
def get_futures_balance(client, _asset="USDT"):
    balances = client.get_balance()
    asset_balance = 0
    for balance in balances:
        if balance.asset == _asset:
            asset_balance = balance.balance
            break

    return asset_balance


# Init the market we want to trade. First we change leverage type
# then we change margin type
def initialise_futures(client, _market="ETHUSDT", _leverage=1, _margin_type="CROSSED"):
    try:
        client.change_initial_leverage(_market, _leverage)
    except Exception as e:
        print(e)

    try:
        client.change_margin_type(_market, _margin_type)
    except Exception as e:
        print(e)


# get all of our open orders in a market
def get_orders(client, _market="ETHUSDT"):
    orders = client.get_open_orders(_market)
    return orders, len(orders)


# get all of our open trades
def get_positions(client):
    positions = client.get_position_v2()
    return positions


# get trades we opened in the market the bot is trading in
def get_specific_positon(client, _market="ETHUSDT"):
    positions = get_positions(client)

    for position in positions:
        if position.symbol == _market:
            break

    return position


# close opened position
def close_position(client, _market="ETHUSDT"):
    position = get_specific_positon(client, _market)
    qty = float(position.positionAmt)

    _side = "BUY"
    if qty > 0.0:
        _side = "SELL"

    if qty < 0.0:
        qty = qty * -1

    qty = str(qty)

    execute_order(client, _market=_market,
                  _qty=qty,
                  _side=_side)


# get the liquidation price of the position we are in. - We don't use this - be careful!
def get_liquidation(client, _market="ETHUSDT"):
    position = get_specific_positon(client, _market)
    price = position.liquidationPrice
    return price


# Get the entry price of the position the bot is in
def get_entry(client, _market="ETHUSDT"):
    position = get_specific_positon(client, _market)
    price = position.entryPrice
    return price


# Execute an order, this can open and close a trade
def execute_order(client, _market="ETHUSDT", _type="MARKET", _side="BUY", _position_side="BOTH", _qty=1.0):
    client.post_order(symbol=_market,
                      ordertype=_type,
                      side=_side,
                      positionSide=_position_side,
                      quantity=_qty)


def execute_market_order(client, _price, _stop_price, _qty, _market, _type, _side="SELL"):
    client.post_order(symbol=_market,
                      ordertype=_type,
                      side=_side,
                      stopPrice=_stop_price,
                      workingType=WorkingType.MARK_PRICE,
                      closePosition=True
                      )


def execute_limit_order(client, _stop_price, _qty, _market="ETHUSDT", _type="LIMIT", _side="SELL",
                        time_in_force=TimeInForce.GTC, reduce_only=True):
    client.post_order(symbol=_market,
                      ordertype=_type,
                      side=_side,
                      quantity=_qty,
                      price=_stop_price,
                      timeInForce=time_in_force,
                      reduceOnly=reduce_only)


def submit_trailing_order(client, _stop_price, _qty=1.0, _market="ETHUSDT", _type="TRAILING_STOP_MARKET", _side="BUY",
         _callbackRate=0.4, time_in_force=TimeInForce.GTC, reduce_only=True):
    client.post_order(symbol=_market,
                      ordertype=_type,
                      side=_side,
                      callbackRate=_callbackRate,
                      quantity=_qty,
                      workingType="CONTRACT_PRICE",
                      activationPrice=_stop_price,
                      timeInForce=time_in_force,
                      reduceOnly=reduce_only)


# calculate how big a position we can open with the margin we have and the leverage we are using
def calculate_position_size(client, usdt_balance=1.0, _market="ETHUSDT", _leverage=1):
    price = client.get_symbol_price_ticker(_market)
    price = price[0].price

    qty = (float(usdt_balance) / price) * _leverage
    qty = round(qty * 0.40, 8)

    return qty


# check if the position is still active, or if the trailing stop was hit.
def check_in_position(client, _market="ETHUSDT"):
    position = get_specific_positon(client, _market)

    in_position = False

    if float(position.positionAmt) != 0.0:
        in_position = True

    return in_position




# get the current market price
def get_market_price(client, _market="ETHUSDT"):
    price = client.get_symbol_price_ticker(_market)
    price = price[0].price
    return price


# get the precision of the market, this is needed to avoid errors when creating orders
def get_market_precision(client, _market="ETHUSDT"):
    market_data = client.get_exchange_information()
    precision = 3
    for market in market_data.symbols:
        if market.symbol == _market:
            precision = market.quantityPrecision
            break
    return precision


def get_price_precision(client, _market="ETHUSDT"):
    market_data = client.get_exchange_information()
    precision = 2
    for market in market_data.symbols:
        if market.symbol == _market:
            precision = market.pricePrecision
            break
    return precision


# round the position size we can open to the precision of the market
def round_to_precision(_qty, _precision):
    """
    Returns a value rounded down to a specific number of decimal places.
    """
    if not isinstance(_precision, int):
        raise TypeError("decimal places must be an integer")
    elif _precision < 0:
        raise ValueError("decimal places has to be 0 or more")
    elif _precision == 0:
        return math.floor(_qty)

    factor = 10 ** _precision
    return float(math.floor(_qty * factor) / factor)


# convert from client candle data into a set of lists
def convert_candles(candles):
    o = []
    h = []
    l = []
    c = []
    v = []

    for candle in candles:
        o.append(float(candle.open))
        h.append(float(candle.high))
        l.append(float(candle.low))
        c.append(float(candle.close))
        v.append(float(candle.volume))

    return o, h, l, c, v


# convert list candle data into list of heikin ashi candles
def construct_heikin_ashi(o, h, l, c):
    h_o = []
    h_h = []
    h_l = []
    h_c = []

    for i, v in enumerate(o):

        close_price = (o[i] + h[i] + l[i] + c[i]) / 4

        if i == 0:
            open_price = close_price
        else:
            open_price = (h_o[-1] + h_c[-1]) / 2

        high_price = max([h[i], close_price, open_price])
        low_price = min([l[i], close_price, open_price])

        h_o.append(open_price)
        h_h.append(high_price)
        h_l.append(low_price)
        h_c.append(close_price)

    return h_o, h_h, h_l, h_c


def get_str_decimal(count):
    return '.' + '0' * (count - 1) + '1'


def get_decimal_half(value):
    return Decimal(int(value + 0.5))


def get_decimal_value(value, price_precision):
    return Decimal(str(value)).quantize(Decimal(get_str_decimal(price_precision)), rounding=ROUND_DOWN)


def handle_signal(client, std, market="ETHUSDT", leverage=3, order_side="BUY",
                  stop_side="SELL", take_profit=4.0, stop_loss=5.0, _callbackRate=0.4):
    initialise_futures(client, _market=market, _leverage=leverage)

    # close any open trailing stops we have
    client.cancel_all_orders(market)

    # close_position(client, _market=market)

    qty = calculate_position(client, market, _leverage=leverage)

    enablePrint(std)

    """ ******** ENTERING POSITION ********* """
    execute_order(client, _qty=qty, _side=order_side, _market=market)

    blockPrint()

    time.sleep(3)

    entry_price = get_specific_positon(client, market).entryPrice
    price_precision = get_price_precision(client, market)

    side = -1
    if order_side == "BUY":
        side = 1
    else:
        side = -1

    in_position = True

    singlePrint(f"{order_side}: {qty} ${entry_price} using x{leverage} leverage", std)

    time.sleep(3)

    log_trade(_qty=qty, _market=market, _leverage=leverage, _side=side,
              _cause="Signal Change", _trigger_price=0,
              _market_price=entry_price, _type=order_side)

    # Let the order execute and then create a trailing stop market order.
    # submit_trailing_order(client, _market=market, _qty=qty, _side=stop_side,
    #                       _callbackRate=_callbackRate)

    """********* STOP LOSS **********"""
    if order_side == "SELL":
        stop_loss = -stop_loss
    stop_loss_raw = (entry_price * ((100 - stop_loss) / 100))
    stop_loss_price = 0
    entry_price_decimal = 0
    if stop_loss_raw < 1:
        stop_loss_price = get_decimal_value(stop_loss_raw, price_precision)
        entry_price_decimal = get_decimal_value(entry_price, price_precision)
    else:
        stop_loss_price = get_decimal_half(stop_loss_raw)
        entry_price_decimal = get_decimal_half(entry_price)

    execute_market_order(client, entry_price_decimal, stop_loss_price, qty, _market=market,
                         _type="STOP_MARKET", _side=stop_side)

    singlePrint(f"Stop Loss ${stop_loss_price} is created", std)

    time.sleep(3)

    """********* TAKE PROFIT **********"""
    if order_side == "SELL":
        take_profit = -take_profit
    take_profit_raw = (entry_price * ((100 + take_profit) / 100))
    take_profit_price = 0
    if take_profit_raw < 1:
        take_profit_price = get_decimal_value(take_profit_raw, price_precision)
    else:
        take_profit_price = get_decimal_half(take_profit_raw)
   # execute_limit_order(client, take_profit_price, qty, _market=market, _type="LIMIT", _side=stop_side)
    submit_trailing_order(client, take_profit_price, qty, _market=market, _type="TRAILING_STOP_MARKET", _side=stop_side, _callbackRate="0.4")




    singlePrint(f"Take Profit ${take_profit_price} is created", std)

    return qty, side, in_position


# create a dataframe for our candles
def to_dataframe(o, h, l, c, v):
    df = pd.DataFrame()

    df['open'] = o
    df['high'] = h
    df['low'] = l
    df['close'] = c
    df['volume'] = v

    return df


# Exponential moving avg - unused
def ema(s, n):
    s = np.array(s)
    out = []
    j = 1

    # get n sma first and calculate the next n period ema
    sma = sum(s[:n]) / n
    multiplier = 2 / float(1 + n)
    out.append(sma)

    # EMA(current) = ( (Price(current) - EMA(prev) ) x Multiplier) + EMA(prev)
    out.append(((s[n] - sma) * multiplier) + sma)

    # now calculate the rest of the values
    for i in s[n + 1:]:
        tmp = ((i - out[j]) * multiplier) + out[j]
        j = j + 1
        out.append(tmp)

    return np.array(out)


# Avarage true range function used by our trading strat
def avarage_true_range(high, low, close):
    atr = []

    for i, v in enumerate(high):
        if i != 0:
            value = np.max([high[i] - low[i], np.abs(high[i] - close[i - 1]), np.abs(low[i] - close[i - 1])])
            atr.append(value)
    return np.array(atr)


# Our trading strategy - it takes in heikin ashi open, high, low and close data and returns a list of signal values
# signals are -1 for short, 1 for long and 0 for do nothing
def trading_signal(h_o, h_h, h_l, h_c, use_last=False):
    factor = 1
    pd = 1

    hl2 = (np.array(h_h) + np.array(h_l)) / 2
    hl2 = hl2[1:]

    atr = avarage_true_range(h_h, h_l, h_c)

    up = hl2 - (factor * atr)
    dn = hl2 + (factor * atr)

    trend_up = [0]
    trend_down = [0]

    for i, v in enumerate(h_c[1:]):
        if i != 0:

            if h_c[i - 1] > trend_up[i - 1]:
                trend_up.append(np.max([up[i], trend_up[i - 1]]))
            else:
                trend_up.append(up[i])

            if h_c[i - 1] < trend_down[i - 1]:
                trend_down.append(np.min([dn[i], trend_down[i - 1]]))
            else:
                trend_down.append(dn[i])

    trend = []
    last = 0
    for i, v in enumerate(h_c):
        if i != 0:
            if h_c[i] > trend_down[i - 1]:
                tr = 1
                last = tr
            elif h_c[i] < trend_up[i - 1]:
                tr = -1
                last = tr
            else:
                tr = last
            trend.append(tr)

    entry = [0]
    last = 0
    for i, v in enumerate(trend):
        if i != 0:
            if trend[i] == 1 and trend[i - 1] == -1:
                entry.append(1)
                last = 1

            elif trend[i] == -1 and trend[i - 1] == 1:
                entry.append(-1)
                last = -1

            else:
                if use_last:
                    entry.append(last)
                else:
                    entry.append(0)

    return entry


def dictToString(dict):
    return str(dict).replace(', ', '\r\n').replace("u'", "").replace("'", "")[1:-1]


def print_condition(my_dict, ind1, ind2, symbol):
    if isinstance(ind2, str):
        print(
            f"{ind1} {symbol} {ind2} | {my_dict[ind1]} {symbol} {my_dict[ind2]} | {eval(str(my_dict[ind1]) + symbol + str(my_dict[ind2]))}")
    else:
        print(
            f"{ind1} {symbol} {ind2} | {my_dict[ind1]} {symbol} {ind2} | {eval(str(my_dict[ind1]) + symbol + str(ind2))}")


def get_remainder_from_5thMinute():
    return datetime.datetime.now().minute % 5

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def trade(my_dict, std):
    entry = 0
    enablePrint(std)
    print("INDICATOR VALUES:")
    print(dictToString(my_dict))
    print("\n************* Long Position Check *******************")
    # print_condition(my_dict, "ema_uptrendlower", "ema_uptrendhigher", ">")
    print_condition(my_dict, "ma_fiftylow", "current_price", "<")
    print_condition(my_dict, "ma_nineclose", "current_price", "<")
    # print_condition(my_dict, "open", "ema_low", "<")
    # print_condition(my_dict, "macd", "macdsignal", ">")
    # print_condition(my_dict, "adx", 25, ">")
    # print_condition(my_dict, "mfi", 30, "<")
    # print_condition(my_dict, "fastk", 30, "<")
    # print_condition(my_dict, "fastd", 30, "<")
    # print_condition(my_dict, "fastk", "fastd", ">")
    # print_condition(my_dict, "cci", -150, "<")
    # print_condition(my_dict, "macdhist998", 0, "<")
    print_condition(my_dict, "macdhist_current", 0, ">")
    print_condition(my_dict, "macdhist_last", 0, "<")
    # print_condition(my_dict, "macdhist_2ndlast", 0, "<")
    # print_condition(my_dict, "macdhist_last", 0, "<")
    # print_condition(my_dict, "macdhist_current", 0, "<")
    # print_condition(my_dict, "macdhist_current", "macdhist_last", ">")
    # print_condition(my_dict, "macdhist_2ndlast", "macdhist_last", ">")
    # print_condition(my_
    # 'dict, "macdhist996", "macdhist997", "<")
    # Long condition
    if ((my_dict['ma_fiftylow'] < my_dict['current_price']) and
            (my_dict['ma_nineclose'] < my_dict['current_price']) and
            # (my_dict['current_price'] < my_dict['ema_low']) and
            # my_dict['macdhist_2ndlast'] < 0) and
            (my_dict['macdhist_current'] > 0) and
            (my_dict['macdhist_last'] < 0)
            # (my_dict['macdhist_last'] < 0) and
            # (my_dict['macdhist_current'] < 0) and
            # (my_dict['macdhist998'] < 0) and
            # (my_dict['macdhist999'] < 0) and
            # (my_dict['macdhist_2ndlast'] > my_dict['macdhist_last']) and
            # (my_dict['macdhist_current'] > my_dict['macdhist_last'])
            # my_dict['open'] < my_dict['ema_low'] and
            # my_dict['macd'] > my_dict['macdsignal'] and
            # (my_dict['adx'] > 25) and
            # (my_dict['mfi'] < 30) and
            # (my_dict['fastk'] < 30) and
            # (my_dict['fastd'] < 30) and
            # (my_dict['fastk'] > my_dict['fastd']) and
            # (my_dict['cci'] < -150)
    ):
        entry = 1
        print(bcolors.OKGREEN + "************* Long Position Matched *******************" + bcolors.ENDC)
    else:
        print(bcolors.FAIL + "************* Long Position Not Matched *******************" + bcolors.ENDC)

    print("\n************* Short Position Check *******************")
    print_condition(my_dict, "ma_fiftyhigh", "current_price", ">")
    print_condition(my_dict, "ma_nineclose", "current_price", ">")
    # print_condition(my_dict, "ema_high", "open", "<")
    # print_condition(my_dict, "macd", "macdsignal", "<")
    # print_condition(my_dict, "adx", 25, ">")
    # print_condition(my_dict, "mfi", 70, ">")
    # print_condition(my_dict, "fastk", 70, ">")
    # print_condition(my_dict, "fastd", 70, ">")
    # print_condition(my_dict, "fastk", "fastd", "<")
    # print_condition(my_dict, "cci", 150, ">")
    # print_condition(my_dict, "macdhist998", 0, ">")
    # print_condition(my_dict, "macdhist998", 0, ">")
    print_condition(my_dict, "macdhist_current", 0, "<")
    print_condition(my_dict, "macdhist_last", 0, ">")
    # print_condition(my_dict, "macdhist_2ndlast", 0, ">")
    # print_condition(my_dict, "macdhist_last", 0, ">")
    # print_condition(my_dict, "macdhist_current", 0, ">")
    # print_condition(my_dict, "macdhist_2ndlast", "macdhist_last", "<")
    # print_condition(my_dict, "macdhist_current", "macdhist_last", "<")

    # Short Condition
    if ((my_dict['ma_fiftyhigh'] > my_dict['current_price']) and
            (my_dict['ma_nineclose'] > my_dict['current_price']) and
            (my_dict['macdhist_current'] < 0) and
            (my_dict['macdhist_last'] > 0)
            # my_dict['ema_downtrendlower'] < my_dict['ema_downtrendhigher'] and
            # (my_dict['ema_high'] < my_dict['current_price']) and
            # (my_dict['macdhist_2ndlast'] > 0) and
            # (my_dict['macdhist_last'] > 0) and
            # (my_dict['macdhist_current'] > 0) and
            # (my_dict['macdhist999'] > 0) and
            # (my_dict['macdhist_2ndlast'] < my_dict['macdhist_last']) and
            # (my_dict['macdhist_current'] < my_dict['macdhist_last'])
            # (my_dict['ema_high'] < my_dict['open']) and
            # my_dict['macd'] < my_dict['macdsignal'] and
            # (my_dict['adx'] > 25) and
            # (my_dict['mfi'] > 70) and
            # (my_dict['fastk'] > 70) and
            # (my_dict['fastd'] > 70) and
            # (my_dict['fastd'] < my_dict['fastk']) and
            # (my_dict['cci'] > 150)
    ):
        entry = -1
        print(bcolors.OKGREEN + "************* Short Position Matched *******************" + bcolors.ENDC)
    else:
        print(bcolors.FAIL + "************* Short Position Not Matched *******************" + bcolors.ENDC)

    blockPrint()
    return entry


def scalp(dataframe, dataframe1m, current_price, std):
    my_dict = {}
    my_dict['ma_fiftyhigh'] = ta.MA(dataframe, timeperiod=50, price='high')[999]
    my_dict['ma_fiftylow'] = ta.MA(dataframe, timeperiod=50, price='low')[999]
    my_dict['ma_nineclose'] = ta.MA(dataframe, timeperiod=20, price='close')[999]

    my_dict['ema_uptrendhigher'] = ta.EMA(dataframe, timeperiod=200, price='close')[999]
    my_dict['ema_uptrendlower'] = ta.EMA(dataframe, timeperiod=50, price='high')[999]
    my_dict['ema_suptrendhigher'] = ta.EMA(dataframe, timeperiod=9, price='low')[999]
    my_dict['ema_suptrendlower'] = ta.EMA(dataframe, timeperiod=3, price='high')[999]
    my_dict['ema_downtrendhigher'] = ta.EMA(dataframe, timeperiod=200, price='high')[999]
    my_dict['ema_downtrendlower'] = ta.EMA(dataframe, timeperiod=50, price='low')[999]
    my_dict['ema_sdowntrendhigher'] = ta.EMA(dataframe, timeperiod=9, price='high')[999]
    my_dict['ema_sdowntrendlower'] = ta.EMA(dataframe, timeperiod=3, price='low')[999]
    my_dict['ema_high'] = ta.EMA(dataframe, timeperiod=5, price='high')[999]
    my_dict['ema_close'] = ta.EMA(dataframe, timeperiod=5, price='close')[999]
    my_dict['ema_low'] = ta.EMA(dataframe, timeperiod=5, price='low')[999]
    fastk, fastd = ta.STOCHF(dataframe['high'], dataframe['low'], dataframe['close'],
                             fastk_period=5, fastd_period=3, fastd_matype=0)
    my_dict['fastd'] = fastd[999]
    my_dict['fastk'] = fastk[999]
    my_dict['adx'] = ta.ADX(dataframe)[999]
    my_dict['cci'] = ta.CCI(dataframe, timeperiod=20)[999]
    my_dict['rsi'] = ta.RSI(dataframe, timeperiod=14)[999]
    my_dict['mfi'] = ta.MFI(dataframe)[999]

    correction = get_remainder_from_5thMinute() + 1
    # macd = ta.MACD(dataframe1m, fast_period=25, slow_period=30, signal_period=9, price='close')
    # my_dict['macd'] = macd['macd'][999]
    # my_dict['macdsignal'] = macd['macdsignal'][999 - correction]
    # my_dict['macdhist_current'] = macd['macdhist'][999 - correction]
    # my_dict['macdhist_last'] = macd['macdhist'][998 - correction * 2]
    # my_dict['macdhist_2ndlast'] = macd['macdhist'][997 - correction * 3]

    # sma macd
    macd = ta.MACDEXT(dataframe, fast_matype=5, slow_period=7, signal_period=9, price='close')
    my_dict['MACD'] = macd['macd'][999]
    my_dict['macdsignal'] = macd['macdsignal'][999]
    my_dict['macdhist_current'] = macd['macdhist'][999]
    my_dict['macdhist_last'] = macd['macdhist'][998]
    # my_dict['macdhist_2ndlast'] = macd['macdhist'][997 - correction * 3]

    my_dict['open'] = dataframe['open'].iloc[-1]
    my_dict['current_price'] = current_price

    entry = trade(my_dict, std)
    return entry


def get_dataframe(candles):
    o, h, l, c, v = convert_candles(candles)
    return to_dataframe(o, h, l, c, v)


# get the data from the market, create heikin ashi candles and then generate signals
# return the signals to the bot
def get_signal(client, _market="ETHUSDT", _period="15m", use_last=False, std=None):
    candles = client.get_candlestick_data(_market, interval=_period, limit=1000)
    candles1m = client.get_candlestick_data(_market, interval="1m", limit=1000)
    current_price = client.get_mark_price(_market).markPrice
    dataframe = get_dataframe(candles)
    dataframe1m = get_dataframe(candles1m)
    entry = scalp(dataframe, dataframe1m, current_price, std)
    return entry


# get signal that is confirmed across multiple time scales
def get_multi_scale_signal(client, _market="ETHUSDT", _periods=["1m"], std=None):
    signal = 0
    use_last = True

    for i, v in enumerate(_periods):
        _signal = get_signal(client, _market, _period=v, use_last=use_last, std=std)
        signal = signal + _signal
        time.sleep(3)

    signal = signal / len(_periods)

    return signal


# calculate a rounded position size for the bot, based on current USDT holding, leverage and market
def calculate_position(client, _market="ETHUSDT", _leverage=1):
    usdt = get_futures_balance(client, _asset="USDT")
    qty = calculate_position_size(client, usdt_balance=usdt, _market=_market, _leverage=_leverage)
    precision = get_market_precision(client, _market=_market)
    qty = round_to_precision(qty, precision)
    qty = get_decimal_value(qty, precision)
    return qty


# function for logging trades to csv for later analysis
def log_trade(_qty=0, _market="ETHUSDT", _leverage=1, _side="long", _cause="signal", _trigger_price=0, _market_price=0,
              _type="exit"):
    df = pd.read_csv("trade_log.csv")
    df2 = pd.DataFrame()
    df2['time'] = [time.time()]
    df2['market'] = [_market]
    df2['qty'] = [_qty]
    df2['leverage'] = [_leverage]
    df2['cause'] = [_cause]
    df2['side'] = [_side]
    df2['trigger_price'] = [_trigger_price]
    df2['market_price'] = [_market_price]
    df2['type'] = [_type]

    df = df.append(df2, ignore_index=True)
    df.to_csv("trade_log.csv", index=False)
