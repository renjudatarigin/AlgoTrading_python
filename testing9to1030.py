# This code implements a live trading bot that connects to the SmartAPI, subscribes to real-time market data for a predefined set of equity tokens, and executes options trading strategies based on Bollinger Bands and RSI indicators. It also logs all trades to Azure Blob Storage for record-keeping and analysis.
# Key Features:
# - Real-time WebSocket connection to SmartAPI for live market data.    
# - Dynamic calculation of Bollinger Bands and RSI indicators using Pandas.
# - Intelligent trade entry and exit logic based on indicator thresholds and momentum validation.
# - EOD square-off mechanism to close all positions before market close.
# - Robust Azure Blob Storage integration for logging all trade activities in CSV format.
# Note: This code is designed for educational and illustrative purposes. It should be thoroughly tested and reviewed before any real trading deployment. Always be aware of the risks involved in trading and consider using a paper trading environment for testing.   


import os
import datetime
import csv
import pandas as pd
import numpy as np
import threading
import time
import http.client
from azure.storage.blob import BlobServiceClient
from pyotp import TOTP
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
# -----------------------------------------------
# Setup & Configuration
# -----------------------------------------------
PATH = os.path.dirname(os.path.abspath(__file__))
try:
    os.chdir(PATH)
except Exception:
    pass
# Create Log Directories
os.makedirs(os.path.join(PATH, "TRADES_LOG"), exist_ok=True)
os.makedirs(os.path.join(PATH, "LIVE_LOG"), exist_ok=True)
# Azure Configuration
AZURE_CONNECTION_STRING = "DefaultEndpointsProtocol=https;AccountName=storageaccountdatarig;AccountKey=mlqWv0MzjNhM40m0Z26BOH556vg7n2oOEqdNm3BkxjtzBRwFGmSnYBZ+wm0kxY2mYOGe4FFjgSa3+AStN8sb/Q==;EndpointSuffix=core.windows.net"
CONTAINER_NAME = "stockdata"
LOG_FOLDER = "LIVE_LOG" # Updated to match folder creation
# -----------------------------------------------
# Equity Token Mapping
# -----------------------------------------------
# Maps Token (str) -> Symbol Name (str)
TOKEN_SYMBOL_MAP = {
    "11532": "ULTRACEMCO", "10604": "BHARTIARTL", "11536": "TCS", "11630": "NTPC",
    "11723": "JSWSTEEL", "10999": "MARUTI", "11483": "LT", "1232": "GRASIM",
    "1363": "HINDALCO", "1394": "HINDUNILVR", "1660": "ITC", "16669": "BAJAJ-AUTO",
    "157": "APOLLOHOSP", "20374": "COALINDIA", "1964": "TRENT", "1594": "INFY",
    "16675": "BAJAJFINSV", "21808": "SBILIFE", "2475": "ONGC", "1922": "KOTAKBANK",
    "1333": "HDFCBANK", "13538": "TECHM", "3499": "TATASTEEL", "15083": "ADANIPORTS",
    "467": "HDFCLIFE", "17963": "NESTLEIND", "3456": "TATAMOTORS", "910": "EICHERMOT",
    "2031": "M&M", "14977": "POWERGRID", "881": "DRREDDY", "5900": "AXISBANK",
    "1348": "HEROMOTOCO", "236": "ASIANPAINT", "317": "BAJFINANCE", "3351": "SUNPHARMA",
    "3432": "TATACONSUM", "25": "ADANIENT", "694": "CIPLA", "2885": "RELIANCE",
    "383": "BEL", "4963": "ICICIBANK", "526": "BPCL", "547": "BRITANNIA",
    "3787": "WIPRO", "4306": "SHRIRAMFIN", "5258": "INDUSINDBK", "7229": "HCLTECH",
    "3045": "SBIN", "3506": "TITAN"
}
# Global State & Buffers
# -----------------------------------------------
df_options = None
blob_service_client = None
sws = None # Global WebSocket Wrapper Instance
api = None # Global SmartConnect Instance
# Historical Data Buffers (Lists of values for indicators)
# Key: equity_token (str)
price_data = {}  
high_data = {}
low_data = {}
volume_data = {}
# Live Candle Aggregation State
# Key: equity_token (str) -> { 'open': float, 'high': float, ... }
active_candles = {}
# Trading State
trade_positions = {}    # option_token -> entry metadata
trade_cooldowns = {}    # equity_token -> last action datetime
option_positions = {}   # option_token -> option info
# Latest Prices (for Option Simulation)
latest_equity_prices = {} # equity_token -> price
# Latest Position Tracker: equity_token -> active_option_token
active_positions_by_equity = {}
# Option Metadata Cache: option_token -> details
option_metadata = {}
# RSI Watch State Tracker
rsi_watch_state = {}    # equity_token -> 'oversold' | 'overbought' | None
# -----------------------------------------------
# Indicator Parameters
# -----------------------------------------------
BOLLINGER_PERIOD = 20
BOLLINGER_STD_DEV = 2
RSI_PERIOD = 14
TRADE_COOLDOWN_PERIOD = datetime.timedelta(seconds=180)
OPTION_PROFIT_THRESHOLD = 2.0
EOD_SQUARE_OFF_HOUR = 15
EOD_SQUARE_OFF_MINUTE = 15
# -----------------------------------------------
# Helper Functions: Options & Math
# -----------------------------------------------
def load_option_metadata(df):
    global option_metadata
    symbol_to_eq_token = {v: k for k, v in TOKEN_SYMBOL_MAP.items()}
    
    for _, row in df.iterrows():
        try:
            opt_token = str(int(row['token']))
            equity_name = row['name']
            eq_token = symbol_to_eq_token.get(equity_name)
            
            if eq_token:
                opt_type = "CE" if row['symbol'].endswith("CE") else "PE"
                option_metadata[opt_token] = {
                    "strike": float(row['strike']),
                    "type": opt_type,
                    "equity_token": eq_token,
                    "equity_symbol": equity_name,
                    "symbol": row['symbol'],
                    "lotsize": row['lotsize'],
                    "token": opt_token
                }
        except Exception:
            continue
def select_itm_options(current_price, eq_token, df):
    stock_name = TOKEN_SYMBOL_MAP.get(str(eq_token))
    if not stock_name:
        return None, None, None, None
        
    stock_options = df[df["name"] == stock_name]
    if stock_options.empty:
        return None, None, None, None
        
    itm_calls = stock_options[
        (stock_options["strike"] <= current_price) &
        (stock_options["symbol"].str.endswith("CE"))
    ]
    itm_puts = stock_options[
        (stock_options["strike"] >= current_price) &
        (stock_options["symbol"].str.endswith("PE"))
    ]
    
    closest_itm_call = itm_calls.loc[itm_calls["strike"].idxmax()] if not itm_calls.empty else None
    closest_itm_put = itm_puts.loc[itm_puts["strike"].idxmin()] if not itm_puts.empty else None
    
    call_token = str(int(closest_itm_call["token"])) if closest_itm_call is not None else None
    put_token = str(int(closest_itm_put["token"])) if closest_itm_put is not None else None
    
    return closest_itm_call, closest_itm_put, call_token, put_token
def get_actual_option_price(exchange, symbol, token):
    try:
        if api:
            resp = api.ltpData(exchange, symbol, token)
            if resp and resp.get('status') and 'data' in resp:
                return float(resp['data']['ltp'])
    except Exception as e:
        print(f"Error fetching LTP for {symbol}: {e}")
    return None
def subscribe_option_token(token):
    try:
        if sws:
            token_list = [{"exchangeType": 2, "tokens": [str(token)]}]
            sws.subscribe("stream_opt", 1, token_list)
            print(f"Subscribed to Live Ticks for NFO Option {token}")
    except Exception as e:
        print(f"Failed to subscribe to option {token}: {e}")
def calculate_simulated_option_price(option_token):
    meta = option_metadata.get(option_token)
    if not meta:
        return 100.0
    
    eq_token = meta['equity_token']
    underlying_price = latest_equity_prices.get(eq_token)
    
    if underlying_price is None:
        return 100.0
        
    strike = meta['strike']
    opt_type = meta['type']
    
    intrinsic = 0.0
    if opt_type == "CE":
         intrinsic = max(0, underlying_price - strike)
    else:
         intrinsic = max(0, strike - underlying_price)
         
    time_value = strike * 0.005
    sim_price = intrinsic + time_value
    
    return max(0.05, sim_price)
def calculate_percentage_difference(entry_price, current_price):
    try:
        return ((current_price - entry_price) / entry_price) * 100
    except Exception:
        return 0.0
# -----------------------------------------------
# Technical Indicators (Pandas-based)
# -----------------------------------------------
def calculate_bollinger_bands(prices, period, std_dev):
    if len(prices) < period:
        return None, None
    s = pd.Series(prices)
    mean = s.rolling(window=period).mean().iloc[-1]
    std = s.rolling(window=period).std().iloc[-1]
    upper = mean + (std * std_dev)
    lower = mean - (std * std_dev)
    return upper, lower
def calculate_rsi(prices, period=14):
    if len(prices) < period:
        return None
    delta = pd.Series(prices).diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs)).iloc[-1]
# -----------------------------------------------
# Azure Logging
# -----------------------------------------------
def log_order_to_azure(ts, option, side, price, order_id=None):
    if not blob_service_client:
        print("Azure client not ready, cannot log order.")
        return
    try:
        date_str = ts.strftime("%Y-%m-%d") if isinstance(ts, datetime.datetime) else str(datetime.date.today())
        blob_name = f"{LOG_FOLDER}/Orders_{date_str}.csv"
        
        token = str(option.get('token', ''))
        symbol = str(option.get('symbol', ''))
        lot_size = str(option.get('lotsize', ''))
        
        csv_line = f"{ts},{token},{symbol},{side},{price:.2f},{order_id},{lot_size}\n"
        
        container_client = blob_service_client.get_container_client(CONTAINER_NAME)
        blob_client = container_client.get_blob_client(blob_name)
        
        if blob_client.exists():
            current_data = blob_client.download_blob().readall().decode('utf-8')
            new_data = current_data + csv_line
            blob_client.upload_blob(new_data, overwrite=True)
        else:
            header = "Timestamp,Token,Symbol,Trade Type,Option Price,Order ID,Lot Size\n"
            blob_client.upload_blob(header + csv_line)
            
        print(f"Logged Order to Azure: {symbol} {side} @ {price}")
        
    except Exception as e:
        print(f"Failed to log order to Azure: {e}")
# -----------------------------------------------
# Trading Logic Operations
# -----------------------------------------------
def place_order(option, trade_type, timestamp, price):
    if option is None:
        return None
        
    token = str(int(option["token"]))
    symbol = option.get("symbol")
    lot_size = option.get("lotsize")
    
    order_id = None
    
    try:
        if api:
            orderparams = {
                "variety": "NORMAL",
                "tradingsymbol": symbol,
                "symboltoken": token,
                "transactiontype": trade_type,
                "exchange": "NFO",
                "ordertype": "MARKET",
                "producttype": "INTRADAY",
                "duration": "DAY",
                "price": str(price),
                "quantity": str(lot_size)
            }
            
            order_id = api.placeOrder(orderparams)
            print(f"Executed Order: {trade_type} {symbol} ID: {order_id}")
            
        else:
            print("API not initialized. Cannot place order.")
            return None
            
    except Exception as e:
        print(f"Order Placement Failed: {e}")
        return None
    if order_id:
        log_order_to_azure(timestamp, option, trade_type, price, order_id)
        
    return order_id
def open_trade(option, trade_type, eq_price, timestamp):
    if option is None:
        return False
        
    token = str(int(option["token"]))
    meta = option_metadata.get(token)
    if not meta:
        return False
        
    eq_token = meta.get('equity_token')
    
    if eq_token in active_positions_by_equity:
        print(f"REJECTED: Already in position for {TOKEN_SYMBOL_MAP.get(eq_token)} ({eq_token})")
        return False
    ltp = get_actual_option_price("NFO", option.get("symbol"), token)
    if ltp is None:
        print(f"Falling back to simulated price for {option.get('symbol')}")
        ltp = calculate_simulated_option_price(token)
    
    order_id = place_order(option, trade_type, timestamp, ltp)
    if not order_id:
        return False
        
    subscribe_option_token(token)
    
    trade_positions[token] = {
        "entry_price": eq_price,
        "entry_time": timestamp,
        "entry_option_price": ltp,
        "symbol": option.get("symbol")
    }
    
    option_positions[token] = {
        "option": option,
        "entry_time": timestamp
    }
    
    active_positions_by_equity[eq_token] = token
    trade_cooldowns[eq_token] = timestamp
            
    return True
def close_trade(option, trade_type, timestamp):
    if option is None:
        return False
        
    token = str(int(option["token"]))
    ltp = get_actual_option_price("NFO", option.get("symbol"), token)
    if ltp is None:
        ltp = calculate_simulated_option_price(token)
    
    order_id = place_order(option, trade_type, timestamp, ltp)
    
    meta = option_metadata.get(token)
    if meta:
        eq_token = meta.get('equity_token')
        if eq_token and active_positions_by_equity.get(eq_token) == token:
            del active_positions_by_equity[eq_token]
            trade_cooldowns[eq_token] = timestamp
    if token in trade_positions:
        del trade_positions[token]
    if token in option_positions:
        del option_positions[token]
             
    return True
def check_position_exit(token, current_ltp, timestamp, source="candle"):
    if token not in option_positions:
        return
        
    option_info = option_positions[token]
    opt = option_info["option"]
    
    entry_data = trade_positions.get(token)
    if not entry_data:
        return
        
    entry_price = entry_data.get("entry_option_price", 0)
    if entry_price == 0:
        return
        
    option_price_diff = calculate_percentage_difference(entry_price, current_ltp)
    
    if option_price_diff >= OPTION_PROFIT_THRESHOLD:
        print(f"TARGET HIT ({source.upper()}) for {opt.get('symbol')}: {option_price_diff:.2f}% (Current LTP: {current_ltp})")
        close_trade(opt, "SELL", timestamp)
def execute_eod_square_off(timestamp):
    tokens_to_close = list(option_positions.keys())
    for token in tokens_to_close:
        if token in option_positions:
            opt = option_positions[token]["option"]
            print(f"EOD SQUARE-OFF TRIGGERED for {opt.get('symbol')} at {timestamp}")
            close_trade(opt, "SELL", timestamp)
def decide_trade(eq_token, prices, highs, lows, volumes, timestamp):
    min_required = max(BOLLINGER_PERIOD, RSI_PERIOD) + 5
    if len(prices) < min_required:
        return
    current_price = prices[-1]
    
    upper_band, lower_band = calculate_bollinger_bands(prices, BOLLINGER_PERIOD, BOLLINGER_STD_DEV)
    rsi = calculate_rsi(prices, RSI_PERIOD)
    
    if None in (upper_band, lower_band, rsi):
        return
    # EOD Block: Do not take new entries closely before market close (15:00)
    if timestamp.hour >= 15:
        return
    print(f"DEBUG {TOKEN_SYMBOL_MAP.get(eq_token)}: P={current_price:.1f} RSI={rsi:.1f} LowerBB={lower_band:.1f} UpperBB={upper_band:.1f}")
    # Track RSI Watch State with Bollinger Bands requirement for Oversold/Overbought
    if rsi < 32 and current_price <= lower_band:
        if rsi_watch_state.get(eq_token) != 'oversold':
            print(f"WATCH: OVERSOLD DETECTED for {TOKEN_SYMBOL_MAP.get(eq_token)} (RSI: {rsi:.1f}, Price: {current_price:.1f} <= LowerBB: {lower_band:.1f})")
        rsi_watch_state[eq_token] = 'oversold'
    elif rsi > 67 and current_price >= upper_band:
        if rsi_watch_state.get(eq_token) != 'overbought':
            print(f"WATCH: OVERBOUGHT DETECTED for {TOKEN_SYMBOL_MAP.get(eq_token)} (RSI: {rsi:.1f}, Price: {current_price:.1f} >= UpperBB: {upper_band:.1f})")
        rsi_watch_state[eq_token] = 'overbought'
    # Dynamic State Reset: Invalidate the state if it enters the neutral zone 
    # without taking a trade to prevent "Dangling State" bugs.
    if rsi_watch_state.get(eq_token) == 'oversold' and rsi >= 50:
        rsi_watch_state[eq_token] = None
        print(f"WATCH: OVERSOLD INVALIDATED for {TOKEN_SYMBOL_MAP.get(eq_token)} (RSI Crossed Neutral)")
    elif rsi_watch_state.get(eq_token) == 'overbought' and rsi <= 50:
        rsi_watch_state[eq_token] = None
        print(f"WATCH: OVERBOUGHT INVALIDATED for {TOKEN_SYMBOL_MAP.get(eq_token)} (RSI Crossed Neutral)")
    # --- EXIT LOGIC (RSI reaching 50) ---
    if eq_token in active_positions_by_equity:
        opt_token = active_positions_by_equity[eq_token]
        if opt_token in option_positions:
            opt = option_positions[opt_token]["option"]
            opt_type = opt.get("symbol", "").endswith("CE")
            
            # If Call (CE), we exit when RSI >= 50. If Put (PE), exit when RSI <= 50.
            if (opt_type and rsi >= 50) or (not opt_type and rsi <= 50):
                print(f"RSI EXIT TRIGGERED for {opt.get('symbol')} at RSI: {rsi:.1f}")
                close_trade(opt, "SELL", timestamp)
        return  # Already in position, stop evaluating entries
    if eq_token in trade_cooldowns:
        last_action = trade_cooldowns[eq_token]
        if timestamp < last_action + TRADE_COOLDOWN_PERIOD:
            return
    
    # Calculate previous RSI for momentum validation
    prev_rsi = calculate_rsi(prices[:-1], RSI_PERIOD)
    if prev_rsi is None:
        prev_rsi = rsi
    itm_call, itm_put, call_token, put_token = select_itm_options(current_price, eq_token, df_options)
    
    # RSI Reversal Logic
    if rsi_watch_state.get(eq_token) == 'oversold' and rsi >= 32 and prev_rsi < rsi:
        if itm_call is not None:
            print(f"SIGNAL BUY CALL: {TOKEN_SYMBOL_MAP.get(eq_token)} @ {current_price}")
            call_dict = itm_call.to_dict()
            if open_trade(call_dict, "BUY", current_price, timestamp):
                rsi_watch_state[eq_token] = None # Reset state after entry
            
    elif rsi_watch_state.get(eq_token) == 'overbought' and rsi <= 67 and prev_rsi > rsi:
        if itm_put is not None:
            print(f"SIGNAL BUY PUT: {TOKEN_SYMBOL_MAP.get(eq_token)} @ {current_price}")
            put_dict = itm_put.to_dict()
            if open_trade(put_dict, "BUY", current_price, timestamp):
                rsi_watch_state[eq_token] = None # Reset state after entry
# -----------------------------------------------
# WebSocket & Data Processing
# -----------------------------------------------
def process_tick(token, price, volume, timestamp):
    if timestamp.hour > EOD_SQUARE_OFF_HOUR or (timestamp.hour == EOD_SQUARE_OFF_HOUR and timestamp.minute >= EOD_SQUARE_OFF_MINUTE):
        if len(option_positions) > 0:
            execute_eod_square_off(timestamp)
    token = str(token)
    if token not in TOKEN_SYMBOL_MAP:
        if token in option_positions:
            check_position_exit(token, price, timestamp, source="option_tick")
        return
    latest_equity_prices[token] = price
    
    flattened_minute = (timestamp.minute // 5) * 5
    current_interval = timestamp.replace(minute=flattened_minute, second=0, microsecond=0)
    
    if token not in active_candles:
        active_candles[token] = {
            'minute': current_interval,
            'open': price,
            'high': price,
            'low': price,
            'close': price,
            'volume': 0 
        }
        if volume is not None:
             active_candles[token]['last_cum_vol'] = volume
             active_candles[token]['volume'] = 0
             
    candle = active_candles[token]
    
    if current_interval > candle['minute']:
        c = candle
        if token not in price_data:
            price_data[token] = []
            high_data[token] = []
            low_data[token] = []
            volume_data[token] = []
            
        price_data[token].append(c['close'])
        high_data[token].append(c['high'])
        low_data[token].append(c['low'])
        volume_data[token].append(c['volume'])
        
        MAX_LEN = 100
        if len(price_data[token]) > MAX_LEN:
            price_data[token].pop(0)
            high_data[token].pop(0)
            low_data[token].pop(0)
            volume_data[token].pop(0)
            
        decide_trade(token, price_data[token], high_data[token], low_data[token], volume_data[token], candle['minute'])
        
        symbol = TOKEN_SYMBOL_MAP.get(token, token)
        print(f"Candle closed for {symbol} ({token}): Close={c['close']}, Vol={c['volume']}")
        
        vol_start = 0
        current_cum_vol = volume if volume is not None else 0
        prev_cum_vol = candle.get('last_cum_vol', 0)
        
        if volume is not None:
             vol_start = current_cum_vol - prev_cum_vol
             if vol_start < 0: vol_start = 0
             
        active_candles[token] = {
            'minute': current_interval,
            'open': price,
            'high': price,
            'low': price,
            'close': price,
            'volume': vol_start,
            'last_cum_vol': current_cum_vol
        }
    else:
        candle['close'] = price
        candle['high'] = max(candle['high'], price)
        candle['low'] = min(candle['low'], price)
        
        if volume is not None and 'last_cum_vol' in candle:
             diff_vol = volume - candle['last_cum_vol']
             if diff_vol >= 0:
                 candle['volume'] += diff_vol
             candle['last_cum_vol'] = volume
# -----------------------------------------------
# WebSocket Callbacks
# -----------------------------------------------
def on_data(wsapp, msg):
    timestamp = datetime.datetime.now(datetime.timezone.utc).astimezone()
    
    ticks = []
    if isinstance(msg, dict):
        if 'token' in msg:
            ticks.append(msg)
    elif isinstance(msg, list):
        ticks = msg
        
    for tick in ticks:
        try:
            token = tick.get('token')
            price = tick.get('last_traded_price') 
            if price is None:
                price = tick.get('ltp')
                
            volume = tick.get('vol_traded')
            if volume is None:
                 volume = tick.get('volume')
            
            if price:
                price = float(price) / 100.0
            if volume:
                volume = float(volume)
                
            if token and price:
                 process_tick(token, price, volume, timestamp)
                 
        except Exception as e:
            print(f"Error processing tick: {e}")
def on_open(wsapp):
    print("on open")
    tokens_to_sub = [str(t) for t in TOKEN_SYMBOL_MAP.keys() if t]
    tokens_to_sub = list(set(tokens_to_sub))
    
    print(f"Subscribing to {len(tokens_to_sub)} tokens: {tokens_to_sub}")
    
    correlation_id = "stream_1"
    mode = 1 
    
    token_list = [
        {
            "exchangeType": 1,
            "tokens": tokens_to_sub
        }
    ]
    
    try:
        if sws:
            sws.subscribe(correlation_id, mode, token_list)
            print("Subscription requested.")
        else:
            print("Error: Global sws instance is None in on_open")
            
    except Exception as e:
        print(f"Error subscribing: {e}")
def on_error(wsapp, error):
    print("on error:", error)
def on_close(wsapp):
    print("on close")
# -----------------------------------------------
# Historical Data Fetch
# -----------------------------------------------
def fetch_historic_data():
    print("Fetching historical data to warm up indicators...")
    
    to_date = datetime.datetime.now()
    from_date = to_date - datetime.timedelta(days=5)
    
    from_date_str = from_date.strftime("%Y-%m-%d %H:%M")
    to_date_str = to_date.strftime("%Y-%m-%d %H:%M")
    
    for token, symbol in TOKEN_SYMBOL_MAP.items():
        try:
            historicParam = {
                "exchange": "NSE",
                "symboltoken": token,
                "interval": "FIVE_MINUTE",
                "fromdate": from_date_str,
                "todate": to_date_str
            }
            
            data = api.getCandleData(historicParam)
            
            if data and 'data' in data and isinstance(data['data'], list):
                candles = data['data']
                raw_candles = candles[-100:]
                
                p_list = []
                h_list = []
                l_list = []
                v_list = []
                
                for c in raw_candles:
                    h_list.append(float(c[2]))
                    l_list.append(float(c[3]))
                    p_list.append(float(c[4]))
                    v_list.append(float(c[5]))
                    
                price_data[token] = p_list
                high_data[token] = h_list
                low_data[token] = l_list
                volume_data[token] = v_list
                
                print(f"Loaded {len(p_list)} candles for {symbol}")
            else:
                print(f"No history found for {symbol}")
                
            time.sleep(0.55) 
            
        except Exception as e:
            print(f"Failed to fetch history for {symbol}: {e}")
# -----------------------------------------------
# Main Setup
# -----------------------------------------------
def main():
    global df_options, blob_service_client, sws, api
    
    try:
        with open("key.txt", "r") as f:
            key_secret = f.read().split()
    except Exception as e:
        print(f"Error reading key.txt: {e}")
        return
        
    api_key = key_secret[0]
    client_code = key_secret[2]
    password = key_secret[3]
    totp_key = key_secret[4]
    
    try:
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
        print("Azure Blob Service Client initialized.")
    except Exception as e:
        print(f"Failed to initialize Azure Client: {e}")
        return
        
    vm_option_chain_path = "/home/azureuser/algo_trading/place_order/option_chain.csv"
    local_option_chain_path = "option_chain.csv"
    
    option_chain_csv = vm_option_chain_path if os.path.exists(vm_option_chain_path) else local_option_chain_path
    
    if os.path.exists(option_chain_csv):
        df_options = pd.read_csv(option_chain_csv)
        if not df_options.empty and df_options["strike"].max() > 10000:
             df_options["strike"] = df_options["strike"] / 100
        
        load_option_metadata(df_options)
        print(f"Loaded {len(df_options)} options from {option_chain_csv}.")
    else:
        print(f"Warning: option_chain.csv not found at {option_chain_csv}. Options logic will fail.")
        df_options = pd.DataFrame()
        
    api = SmartConnect(api_key=api_key)
    session_data = api.generateSession(client_code, password, TOTP(totp_key).now())
    
    if session_data['status'] == False:
        print(f"Login Failed: {session_data}")
        return
        
    auth_token = session_data['data']['jwtToken']
    feed_token = api.getfeedToken()
    
    print("SmartAPI Connected & Logged In.")
    
    fetch_historic_data()
    
    sws = SmartWebSocketV2(auth_token, api_key, client_code, feed_token)
    
    sws.on_open = on_open
    sws.on_data = on_data
    sws.on_error = on_error
    sws.on_close = on_close
    
    print("Starting WebSocket Connection...")
    sws.connect()
if __name__ == "__main__":
    main()
