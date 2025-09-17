# import os
# import datetime
# import csv
# import pandas as pd
# from pyotp import TOTP
# from SmartApi import SmartConnect
# from SmartApi.smartWebSocketV2 import SmartWebSocketV2
# import json
# import requests
# # -----------------------------------------------
# # API and WebSocket Setup
# # -----------------------------------------------
# PATH = r"D:\ALGOTRADING"
# os.chdir(PATH)

# # Create necessary directories if they don't exist
# os.makedirs(os.path.join(PATH, "TRADES_LOG"), exist_ok=True)
# os.makedirs(os.path.join(PATH, "ORDERS_LOG"), exist_ok=True)

# # Read API credentials
# with open("key.txt", "r") as f:
#     key_secret = f.read().split()

# # Initialize API session
# api = SmartConnect(api_key=key_secret[0])
# session_data = api.generateSession(key_secret[2], key_secret[3], TOTP(key_secret[4]).now())
# feed_token = api.getfeedToken()

# # Initialize WebSocket connection
# sws = SmartWebSocketV2(
#     session_data["data"]["jwtToken"],
#     key_secret[0],
#     key_secret[2],
#     feed_token
# )

# # -----------------------------------------------
# # Load Option Chain for Multiple Stocks
# # -----------------------------------------------
# option_chain_csv = r"D:\ALGOTRADING\option_chain.csv"
# df_options = pd.read_csv(option_chain_csv)
# df_options["strike"] /= 100  # Adjusting strike price scale

# # -----------------------------------------------
# # Equity Token to Symbol Mapping
# # -----------------------------------------------
# TOKEN_SYMBOL_MAP = {
#     "2031": "M&M",
#     "910": "EICHERMOT" ,   
#     "3456": "TATAMOTORS" ,   
#     "11723": "JSWSTEEL",   
#     "16679": "BAJAJ-AUTO" 
# }

# # -----------------------------------------------
# # Indicator Parameters
# # -----------------------------------------------
# EMA_SHORT_PERIOD = 9
# EMA_LONG_PERIOD = 21
# BOLLINGER_PERIOD = 20
# BOLLINGER_STD_DEV = 2
# RSI_PERIOD = 14
# TRADE_COOLDOWN_PERIOD = datetime.timedelta(seconds=180)
# OPTION_PROFIT_THRESHOLD = 6  # 5.5% profit for options
# STOP_LOSS_PERCENTAGE = 5.0  # 3% stop loss
# TRADE_START_TIME = datetime.time(9, 15)  # 9:15 AM
# TRADE_END_TIME = datetime.time(10, 15)   # 10:15 AM

# # Data Buffers
# price_data = {}
# volume_data = {}
# trade_positions = {}
# trade_cooldowns = {}
# option_positions = {}
# option_ltp_data = {}
# previous_day_data = {}  # Store previous day's high and low

# # -----------------------------------------------
# # Helper Functions
# # -----------------------------------------------
# def fetch_previous_day_data():
#     """Fetch previous day's high and low for all stocks"""
#     global previous_day_data
    
#     # Get yesterday's date
#     yesterday = datetime.datetime.now() - datetime.timedelta(days=7)
#     yesterday_str = yesterday.strftime('%Y-%m-%d')
    
#     for token, symbol in TOKEN_SYMBOL_MAP.items():
#         try:
#             # Fetch historical data for the previous day
#             historical_data = api.getCandleData({
#                 "exchange": "NSE",
#                 "symboltoken": token,
#                 "interval": "ONE_DAY",
#                 "fromdate": yesterday_str + " 09:00",
#                 "todate": yesterday_str + " 15:30"
#             })
            
#             if historical_data and 'data' in historical_data and historical_data['data']:
#                 day_data = historical_data['data'][0]  # Get the first (and only) day's data
#                 previous_day_data[token] = {
#                     'high': float(day_data[3]) / 100,  # Normalize price
#                     'low': float(day_data[4]) / 100    # Normalize price
#                 }
#                 print(f"Previous day data for {symbol}: High={previous_day_data[token]['high']}, Low={previous_day_data[token]['low']}")
#             else:
#                 print(f"Warning: No historical data found for {symbol}")
#                 previous_day_data[token] = {'high': float('inf'), 'low': 0}  # Default values
                
#         except Exception as e:
#             print(f"Error fetching previous day data for {symbol}: {e}")
#             previous_day_data[token] = {'high': float('inf'), 'low': 0}  # Default values

# def is_trading_time():
#     """Check if current time is within trading hours (9:15 to 10:15)"""
#     current_time = datetime.datetime.now().time()
#     return TRADE_START_TIME <= current_time <= TRADE_END_TIME

# def select_itm_options(current_price, token, df):
#     """Selects the nearest ITM Call and Put options dynamically for a given equity token."""
#     stock_name = TOKEN_SYMBOL_MAP.get(token)
#     if not stock_name:
#         print(f"ERROR: No symbol mapping found for equity token {token}")
#         return None, None, None, None

#     stock_options = df[df["name"] == stock_name]

#     if stock_options.empty:
#         print(f"ERROR: No options found for symbol {stock_name}. Check option_chain.csv.")
#         return None, None, None, None

#     print(f"\nChecking ITM Options for {stock_name} at price {current_price}")

#     itm_calls = stock_options[
#         (stock_options["strike"] <= current_price) &
#         (stock_options["symbol"].str.endswith("CE"))
#     ]
#     itm_puts = stock_options[
#         (stock_options["strike"] >= current_price) &
#         (stock_options["symbol"].str.endswith("PE"))
#     ]
    
#     closest_itm_call = itm_calls.loc[itm_calls["strike"].idxmax()] if not itm_calls.empty else None
#     closest_itm_put = itm_puts.loc[itm_puts["strike"].idxmin()] if not itm_puts.empty else None

#     # Return both the option data and their tokens
#     call_token = str(closest_itm_call["token"]) if closest_itm_call is not None else None
#     put_token = str(closest_itm_put["token"]) if closest_itm_put is not None else None
    
#     return closest_itm_call, closest_itm_put, call_token, put_token

# def place_order(option, trade_type):
#     """Place a buy or sell order using the correct trading symbol."""
#     if option is None:
#         print("Error: No valid option provided for order placement.")
#         return None

#     token = str(option["token"])
#     trading_symbol = option["symbol"]
#     lot_size = int(option["lotsize"])

#     try:
#         order_params = {
#             "variety": "NORMAL",
#             "tradingsymbol": trading_symbol,
#             "symboltoken": token,
#             "transactiontype": trade_type,
#             "exchange": "NFO",
#             "ordertype": "MARKET",
#             "producttype": "CARRYFORWARD",
#             "duration": "DAY",
#             "quantity": str(lot_size)
#         }
#         order_response = api.placeOrder(order_params)

#         if isinstance(order_response, str):
#             order_id = order_response.strip()
#             print(f"Order placed successfully: {order_id} for {trading_symbol}")
#             return order_id
#         elif isinstance(order_response, dict) and 'data' in order_response:
#             order_id = order_response['data']['orderid']
#             print(f"Order placed successfully: {order_id} for {trading_symbol}")
#             return order_id

#         print(f"Order placement failed: Unexpected response format: {order_response}")
#         return None
#     except Exception as e:
#         print(f"Error placing order: {e}")
#         return None
    
# def calculate_ema(prices, period):
#     return pd.Series(prices).ewm(span=period, adjust=False).mean().iloc[-1] if len(prices) >= period else None

# def calculate_bollinger_bands(prices, period, std_dev):
#     if len(prices) < period:
#         return None, None
#     rolling_mean = pd.Series(prices).rolling(window=period).mean()
#     rolling_std = pd.Series(prices).rolling(window=period).std()
#     upper_band = rolling_mean.iloc[-1] + (rolling_std.iloc[-1] * std_dev)
#     lower_band = rolling_mean.iloc[-1] - (rolling_std.iloc[-1] * std_dev)
#     return upper_band, lower_band

# def calculate_rsi(prices, period=14):
#     if len(prices) < period:
#         return None
#     delta = pd.Series(prices).diff()
#     gain = delta.where(delta > 0, 0).rolling(window=period).mean()
#     loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
#     rs = gain / loss
#     return 100 - (100 / (1 + rs)).iloc[-1]

# def calculate_percentage_difference(entry_price, current_price):
#     return ((current_price - entry_price) / entry_price) * 100

# def log_trade(timestamp, token, trade_type, equity_price):
#     """Simplified logging: Only logs token, trade type, and equity price."""
#     csv_file = os.path.join(PATH, "TRADES_LOG", f"TRADES_{datetime.datetime.now().strftime('%Y-%m-%d')}.csv")
#     os.makedirs(os.path.dirname(csv_file), exist_ok=True)

#     file_exists = os.path.exists(csv_file)
#     with open(csv_file, mode='a', newline='') as file:
#         writer = csv.writer(file)
#         if not file_exists:
#             writer.writerow(["Timestamp", "Token", "Trade Type", "Equity Price"])
#         writer.writerow([timestamp, token, trade_type, equity_price])

# def log_order(timestamp, token, trade_type, equity_price, order_id, option_type, lot_size, option_price=None):
#     """Log successfully placed orders to a CSV file with option price."""
#     csv_file = os.path.join(PATH, "ORDERS_LOG", f"ORDERS_{datetime.datetime.now().strftime('%Y-%m-%d')}.csv")
#     file_exists = os.path.exists(csv_file)

#     row = df_options[df_options["token"] == int(token)]
#     symbol = row["symbol"].values[0] if not row.empty else "UNKNOWN"
#     with open(csv_file, mode='a', newline='') as file:
#         writer = csv.writer(file)
#         if not file_exists:
#             writer.writerow(["Timestamp", "Token", "Symbol", "Trade Type", "Equity Price", "Option Price", "Order ID", "Option Type", "Lot Size"])
#         writer.writerow([timestamp, token, symbol, trade_type, equity_price, option_price, order_id, option_type, lot_size])

# def fetch_option_ltp(option_token):
#     """Fetch current LTP for an option using SmartConnect API"""
#     try:
#         ltp_data = api.ltpData("NFO", "OPTIDX", option_token)
#         if ltp_data and 'data' in ltp_data and 'ltp' in ltp_data['data']:
#             return float(ltp_data['data']['ltp'])
#         return None
#     except Exception as e:
#         print(f"Error fetching LTP for option {option_token}: {e}")
#         return None
    
# def open_trade(option, trade_type, equity_price, timestamp):
#     """Helper function to open a trade and store the selected strike price."""
#     order_id = place_order(option, trade_type)
#     if order_id and option is not None:
#         token = str(option["token"])
#         # Get current option price
#         option_price = fetch_option_ltp(token)
#         if option_price is None:
#             option_price = 0  # Default value if price can't be fetched
        
#         trade_positions[token] = {
#             "entry_price": equity_price,
#             "entry_time": timestamp,
#             "type": trade_type,
#             "strike": option["strike"],
#             "symbol": option["symbol"],
#             "entry_option_price": option_price
#         }
#         trade_cooldowns[token] = timestamp
#         lot_size = int(option["lotsize"])
#         option_type = "CALL" if "CE" in option["symbol"] else "PUT"
#         log_order(timestamp, token, trade_type, equity_price, order_id, option_type, lot_size, option_price)
#         return True
#     return False

# def close_trade(option, trade_type, equity_price, timestamp):
#     """Helper function to close a trade while ensuring it's the same strike price."""
#     if option is None:
#         print("Error: No valid option provided for closing trade.")
#         return False

#     token = str(option["token"])

#     if token not in trade_positions:
#         print(f"Warning: No active trade found for token {token}")
#         return False

#     entry_symbol = trade_positions[token]["symbol"]

#     if entry_symbol != option["symbol"]:
#         print(f"Skipping closing trade. {entry_symbol} != {option['symbol']}")
#         return False

#     lot_size = int(option["lotsize"])
#     option_type = "CALL" if "CE" in option["symbol"] else "PUT"
    
#     # Get current option price
#     option_price = option_ltp_data.get(token) or fetch_option_ltp(token)
#     if option_price is None:
#         option_price = 0  # Default value if price can't be fetched

#     order_id = place_order(option, trade_type)
#     if order_id:
#         # Log to both order and trade logs with option price
#         log_order(timestamp, token, trade_type, equity_price, order_id, option_type, lot_size, option_price)
#         print(f"Closing trade for token {token} at equity price {equity_price}, option price {option_price}")
#         del trade_positions[token]
#         trade_cooldowns[token] = timestamp
#         return True
#     return False

# def check_stop_loss(token, current_option_ltp):
#     """Check if stop loss is triggered for a position"""
#     if token not in trade_positions:
#         return False
        
#     entry_price = trade_positions[token].get("entry_option_price", 0)
#     if entry_price == 0:
#         return False
        
#     price_diff = calculate_percentage_difference(entry_price, current_option_ltp)
    
#     # Check for stop loss (negative percentage)
#     if price_diff <= -STOP_LOSS_PERCENTAGE:
#         print(f"STOP LOSS TRIGGERED for token {token}: {price_diff:.2f}%")
#         return True
        
#     return False

# def decide_trade(equity_token, prices, volumes, timestamp, itm_call, itm_put):
#     global trade_positions, trade_cooldowns, option_positions, option_ltp_data

#     # Check if within trading time
#     if not is_trading_time():
#         print(f"Outside trading hours ({TRADE_START_TIME} to {TRADE_END_TIME}). Skipping trade decision.")
#         return

#     if len(prices) < max(EMA_LONG_PERIOD, BOLLINGER_PERIOD):
#         return

#     current_price = prices[-1]
#     current_volume = volumes[-1]

#     # Check previous day high/low constraints
#     if equity_token in previous_day_data:
#         prev_high = previous_day_data[equity_token]['high']
#         prev_low = previous_day_data[equity_token]['low']
        
#         print(f"Previous Day: High={prev_high}, Low={prev_low}, Current={current_price}")
        
#         # Trading constraints based on previous day levels
#         if current_price > prev_high:
#             print("Price above yesterday's high - Only SELL trades allowed")
#             # Don't allow BUY trades
#             itm_call = None
#         elif current_price < prev_low:
#             print("Price below yesterday's low - Only BUY trades allowed")
#             # Don't allow SELL trades
#             itm_put = None

#     # Indicators
#     ema_short = calculate_ema(prices, EMA_SHORT_PERIOD)
#     ema_long = calculate_ema(prices, EMA_LONG_PERIOD)
#     upper_band, lower_band = calculate_bollinger_bands(prices, BOLLINGER_PERIOD, BOLLINGER_STD_DEV)
#     rsi = calculate_rsi(prices)

#     print(f"\nToken: {equity_token}, Time: {timestamp}")
#     print(f"  Current Price: {current_price}")
#     print(f"  EMA Short: {ema_short}, EMA Long: {ema_long}")
#     print(f"  Bollinger Bands: Upper: {upper_band}, Lower: {lower_band}")
#     print(f"  RSI: {rsi}")
    
#     if None in [ema_short, ema_long, upper_band, lower_band, rsi]:
#         return

#     # Cooldown check
#     if equity_token in trade_cooldowns and timestamp < trade_cooldowns[equity_token] + TRADE_COOLDOWN_PERIOD:
#         return

#     # EXIT LOGIC (Profit taking and Stop Loss)
#     tokens_to_close = list(option_positions.keys())  # iterate over a copy
#     for token in tokens_to_close:
#         option_info = option_positions[token]
#         option = option_info["option"]
#         option_token = str(option["token"])

#         # Get LTP from WebSocket first, then fallback to HTTP
#         current_option_ltp = option_ltp_data.get(option_token)
#         if current_option_ltp is None:
#             current_option_ltp = fetch_option_ltp(option_token)
#             if current_option_ltp is None:
#                 print(f"Skipping exit: Couldn't fetch option LTP for {option_token}")
#                 continue

#         entry_price = trade_positions.get(token, {}).get("entry_option_price", 0)
#         if entry_price == 0:
#             trade_positions[token]["entry_option_price"] = current_option_ltp
#             entry_price = current_option_ltp

#         option_price_diff = calculate_percentage_difference(entry_price, current_option_ltp)

#         print(f"Exit Check | Option Token: {option_token} | % Change: {option_price_diff:.2f}%")

#         # Check for stop loss first
#         if check_stop_loss(token, current_option_ltp):
#             if close_trade(option, "SELL", current_option_ltp, timestamp):
#                 del trade_positions[token]
#                 del option_positions[token]
#                 trade_cooldowns[token] = timestamp
#         # Then check for profit taking
#         elif option_price_diff >= OPTION_PROFIT_THRESHOLD:
#             if close_trade(option, "SELL", current_option_ltp, timestamp):
#                 del trade_positions[token]
#                 del option_positions[token]
#                 trade_cooldowns[token] = timestamp
    
#     # ENTRY LOGIC
#     if equity_token not in trade_positions:
#         # ENTRY: Buy CALL (bullish) - Only if price is not below yesterday's low
#         if (itm_call is not None and ema_short > ema_long and current_price <= lower_band and rsi < 30):
#             if open_trade(itm_call, "BUY", current_price, timestamp):
#                 trade_positions[equity_token] = {
#                     "entry_price": current_price,
#                     "entry_time": timestamp,
#                     "entry_option_price": 0,
#                     "type": "BUY"
#                 }
#                 option_positions[equity_token] = {
#                     "option": itm_call,
#                     "type": "CALL",
#                     "entry_time": timestamp
#                 }
#                 trade_cooldowns[equity_token] = timestamp
#                 # Subscribe to option token
#                 call_token = str(itm_call["token"])
#                 sws.subscribe("stream_2", 2, [{"exchangeType": 2, "tokens": [call_token]}])

#         # ENTRY: Buy PUT (bearish) - Only if price is not above yesterday's high
#         elif (itm_put is not None and ema_short < ema_long and current_price >= upper_band and rsi > 70):
#             log_trade(timestamp, equity_token, "SELL", current_price)
#             if open_trade(itm_put, "BUY", current_price, timestamp):
#                 trade_positions[equity_token] = {
#                     "entry_price": current_price,
#                     "entry_time": timestamp,
#                     "entry_option_price": 0,
#                     "type": "SELL"
#                 }
#                 option_positions[equity_token] = {
#                     "option": itm_put,
#                     "type": "PUT",
#                     "entry_time": timestamp
#                 }
#                 trade_cooldowns[equity_token] = timestamp
#                 # Subscribe to option token
#                 put_token = str(itm_put["token"])
#                 sws.subscribe("stream_2", 2, [{"exchangeType": 2, "tokens": [put_token]}])

# def on_data(wsapp, message):
#     try:
#         # Handle both dictionary and string messages
#         if isinstance(message, str):
#             message = json.loads(message)
        
#         # Process option data
#         if message.get("exchange_type") == 2:  # NFO exchange
#             option_token = str(message.get("token"))
#             ltp = float(message.get("last_traded_price", 0)) / 100  # Normalize
#             option_ltp_data[option_token] = ltp
#             print(f"Updated LTP for option {option_token}: {ltp}")
#             return
        
#         # Process equity messages
#         equity_token = str(message.get("token"))
#         close_price = float(message.get("last_traded_price", 0)) / 100
#         buy_quantity = float(message.get("total_buy_quantity", 0))
#         sell_quantity = float(message.get("total_sell_quantity", 0))
#         timestamp = datetime.datetime.now()

#         net_vol = buy_quantity - sell_quantity

#         if equity_token not in price_data:
#             price_data[equity_token] = []
#             volume_data[equity_token] = []

#         price_data[equity_token].append(close_price)
#         volume_data[equity_token].append(net_vol)

#         # Maintain fixed window size
#         if len(price_data[equity_token]) > max(EMA_LONG_PERIOD, BOLLINGER_PERIOD):
#             price_data[equity_token].pop(0)
#             volume_data[equity_token].pop(0)

#         print(f"Updated Prices for {equity_token}: {price_data[equity_token][-5:]}")  # Print last 5 prices
#         print(f"Price Data Length: {len(price_data[equity_token])}")

#         itm_call, itm_put, call_token, put_token = select_itm_options(close_price, equity_token, df_options)
#         decide_trade(equity_token, price_data[equity_token], volume_data[equity_token], timestamp, itm_call, itm_put)
    
#     except Exception as e:
#         print(f"Error in on_data: {e}")
#         import traceback
#         traceback.print_exc()

# # -----------------------------------------------
# # Main Execution
# # -----------------------------------------------
# if __name__ == "__main__":
#     TOKENS = list(TOKEN_SYMBOL_MAP.keys())
    
#     # Fetch previous day data before starting
#     print("Fetching previous day high/low data...")
#     fetch_previous_day_data()
    
#     def on_open(wsapp):
#         # Subscribe to equity tokens (NSE exchange)
#         sws.subscribe("stream_1", 3, [{"exchangeType": 1, "tokens": TOKENS}])
#         print(f"Subscribed to equity tokens: {TOKENS}")
#         print(f"Trading hours: {TRADE_START_TIME} to {TRADE_END_TIME}")
    
#     sws.on_open = on_open
#     sws.on_data = on_data
#     sws.on_error = lambda wsapp, error: print(f"WebSocket error: {error}")
#     sws.on_close = lambda wsapp: print("WebSocket connection closed")
    
#     try:
#         sws.connect()
#         print("WebSocket connection initiated...")
#     except Exception as e:
#         print(f"Failed to connect to WebSocket: {e}")

# import os
# import datetime
# import csv
# import pandas as pd
# from pyotp import TOTP
# from SmartApi import SmartConnect
# from SmartApi.smartWebSocketV2 import SmartWebSocketV2
# import json
# import requests
# # -----------------------------------------------
# # API and WebSocket Setup
# # -----------------------------------------------
# PATH = r"D:\ALGOTRADING"
# os.chdir(PATH)

# # Create necessary directories if they don't exist
# os.makedirs(os.path.join(PATH, "TRADES_LOG"), exist_ok=True)
# os.makedirs(os.path.join(PATH, "ORDERS_LOG"), exist_ok=True)

# # Read API credentials
# with open("key.txt", "r") as f:
#     key_secret = f.read().split()

# # Initialize API session
# api = SmartConnect(api_key=key_secret[0])
# session_data = api.generateSession(key_secret[2], key_secret[3], TOTP(key_secret[4]).now())
# feed_token = api.getfeedToken()

# # Initialize WebSocket connection
# sws = SmartWebSocketV2(
#     session_data["data"]["jwtToken"],
#     key_secret[0],
#     key_secret[2],
#     feed_token
# )

# # -----------------------------------------------
# # Load Option Chain for Multiple Stocks
# # -----------------------------------------------
# option_chain_csv = r"D:\ALGOTRADING\option_chain.csv"
# df_options = pd.read_csv(option_chain_csv)
# df_options["strike"] /= 100  # Adjusting strike price scale

# # -----------------------------------------------
# # Equity Token to Symbol Mapping
# # -----------------------------------------------
# TOKEN_SYMBOL_MAP = {
#     "2031": "M&M",
#     "910": "EICHERMOT" ,   
#     "3456": "TATAMOTORS" ,   
#     "11723": "JSWSTEEL",   
#     "16679": "BAJAJ-AUTO" 
# }

# # -----------------------------------------------
# # Indicator Parameters
# # -----------------------------------------------
# EMA_SHORT_PERIOD = 9
# EMA_LONG_PERIOD = 21
# BOLLINGER_PERIOD = 20
# BOLLINGER_STD_DEV = 2
# RSI_PERIOD = 14
# TRADE_COOLDOWN_PERIOD = datetime.timedelta(seconds=180)
# OPTION_PROFIT_THRESHOLD = 6  # 5.5% profit for options
# STOP_LOSS_PERCENTAGE = 5.0  # 3% stop loss
# TRADE_START_TIME = datetime.time(9, 15)  # 9:15 AM
# TRADE_END_TIME = datetime.time(10, 15)   # 10:15 AM

# # Data Buffers
# price_data = {}
# volume_data = {}
# trade_positions = {}
# trade_cooldowns = {}
# option_positions = {}
# option_ltp_data = {}
# previous_day_data = {}  # Store previous day's high and low

# # -----------------------------------------------
# # Helper Functions
# # -----------------------------------------------
# def get_previous_trading_day():
#     """Get the previous trading day (skip weekends)"""
#     today = datetime.datetime.now()
#     # Go back up to 3 days to find a trading day (Friday, Thursday, Wednesday)
#     for days_back in range(1, 4):
#         previous_day = today - datetime.timedelta(days=days_back)
#         # Monday to Friday are trading days (0=Monday, 4=Friday)
#         if previous_day.weekday() < 5:
#             return previous_day
#     return today - datetime.timedelta(days=1)  # Fallback

# def fetch_previous_day_data():
#     """Fetch previous trading day's high and low for all stocks"""
#     global previous_day_data
    
#     # Get previous trading day (skip weekends)
#     previous_trading_day = get_previous_trading_day()
#     previous_day_str = previous_trading_day.strftime('%Y-%m-%d')
    
#     print(f"Fetching data for previous trading day: {previous_day_str}")
    
#     for token, symbol in TOKEN_SYMBOL_MAP.items():
#         try:
#             # Fetch historical data for the previous trading day
#             historical_data = api.getCandleData({
#                 "exchange": "NSE",
#                 "symboltoken": token,
#                 "interval": "ONE_DAY",
#                 "fromdate": previous_day_str + " 09:00",
#                 "todate": previous_day_str + " 15:30"
#             })
            
#             if historical_data and 'data' in historical_data and historical_data['data']:
#                 # Find the data for the specific previous trading day
#                 for day_data in historical_data['data']:
#                     data_date = datetime.datetime.fromtimestamp(day_data[0] / 1000)
#                     if data_date.date() == previous_trading_day.date():
#                         previous_day_data[token] = {
#                             'high': float(day_data[3]) / 100,  # Normalize price
#                             'low': float(day_data[4]) / 100    # Normalize price
#                         }
#                         print(f"Previous day data for {symbol}: High={previous_day_data[token]['high']}, Low={previous_day_data[token]['low']}")
#                         break
#                 else:
#                     print(f"Warning: No data found for {symbol} on {previous_day_str}")
#                     previous_day_data[token] = {'high': float('inf'), 'low': 0}
#             else:
#                 print(f"Warning: No historical data found for {symbol}")
#                 previous_day_data[token] = {'high': float('inf'), 'low': 0}
                
#         except Exception as e:
#             print(f"Error fetching previous day data for {symbol}: {e}")
#             previous_day_data[token] = {'high': float('inf'), 'low': 0}

# def is_trading_time():
#     """Check if current time is within trading hours (9:15 to 10:15)"""
#     current_time = datetime.datetime.now().time()
#     return TRADE_START_TIME <= current_time <= TRADE_END_TIME

# def select_itm_options(current_price, token, df):
#     """Selects the nearest ITM Call and Put options dynamically for a given equity token."""
#     stock_name = TOKEN_SYMBOL_MAP.get(token)
#     if not stock_name:
#         print(f"ERROR: No symbol mapping found for equity token {token}")
#         return None, None, None, None

#     stock_options = df[df["name"] == stock_name]

#     if stock_options.empty:
#         print(f"ERROR: No options found for symbol {stock_name}. Check option_chain.csv.")
#         return None, None, None, None

#     print(f"\nChecking ITM Options for {stock_name} at price {current_price}")

#     itm_calls = stock_options[
#         (stock_options["strike"] <= current_price) &
#         (stock_options["symbol"].str.endswith("CE"))
#     ]
#     itm_puts = stock_options[
#         (stock_options["strike"] >= current_price) &
#         (stock_options["symbol"].str.endswith("PE"))
#     ]
    
#     closest_itm_call = itm_calls.loc[itm_calls["strike"].idxmax()] if not itm_calls.empty else None
#     closest_itm_put = itm_puts.loc[itm_puts["strike"].idxmin()] if not itm_puts.empty else None

#     # Return both the option data and their tokens
#     call_token = str(closest_itm_call["token"]) if closest_itm_call is not None else None
#     put_token = str(closest_itm_put["token"]) if closest_itm_put is not None else None
    
#     return closest_itm_call, closest_itm_put, call_token, put_token

# def place_order(option, trade_type):
#     """Place a buy or sell order using the correct trading symbol."""
#     if option is None:
#         print("Error: No valid option provided for order placement.")
#         return None

#     token = str(option["token"])
#     trading_symbol = option["symbol"]
#     lot_size = int(option["lotsize"])

#     try:
#         order_params = {
#             "variety": "NORMAL",
#             "tradingsymbol": trading_symbol,
#             "symboltoken": token,
#             "transactiontype": trade_type,
#             "exchange": "NFO",
#             "ordertype": "MARKET",
#             "producttype": "CARRYFORWARD",
#             "duration": "DAY",
#             "quantity": str(lot_size)
#         }
#         order_response = api.placeOrder(order_params)

#         if isinstance(order_response, str):
#             order_id = order_response.strip()
#             print(f"Order placed successfully: {order_id} for {trading_symbol}")
#             return order_id
#         elif isinstance(order_response, dict) and 'data' in order_response:
#             order_id = order_response['data']['orderid']
#             print(f"Order placed successfully: {order_id} for {trading_symbol}")
#             return order_id

#         print(f"Order placement failed: Unexpected response format: {order_response}")
#         return None
#     except Exception as e:
#         print(f"Error placing order: {e}")
#         return None
    
# def calculate_ema(prices, period):
#     return pd.Series(prices).ewm(span=period, adjust=False).mean().iloc[-1] if len(prices) >= period else None

# def calculate_bollinger_bands(prices, period, std_dev):
#     if len(prices) < period:
#         return None, None
#     rolling_mean = pd.Series(prices).rolling(window=period).mean()
#     rolling_std = pd.Series(prices).rolling(window=period).std()
#     upper_band = rolling_mean.iloc[-1] + (rolling_std.iloc[-1] * std_dev)
#     lower_band = rolling_mean.iloc[-1] - (rolling_std.iloc[-1] * std_dev)
#     return upper_band, lower_band

# def calculate_rsi(prices, period=14):
#     if len(prices) < period:
#         return None
#     delta = pd.Series(prices).diff()
#     gain = delta.where(delta > 0, 0).rolling(window=period).mean()
#     loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
#     rs = gain / loss
#     return 100 - (100 / (1 + rs)).iloc[-1]

# def calculate_percentage_difference(entry_price, current_price):
#     return ((current_price - entry_price) / entry_price) * 100

# def log_trade(timestamp, token, trade_type, equity_price):
#     """Simplified logging: Only logs token, trade type, and equity price."""
#     csv_file = os.path.join(PATH, "TRADES_LOG", f"TRADES_{datetime.datetime.now().strftime('%Y-%m-%d')}.csv")
#     os.makedirs(os.path.dirname(csv_file), exist_ok=True)

#     file_exists = os.path.exists(csv_file)
#     with open(csv_file, mode='a', newline='') as file:
#         writer = csv.writer(file)
#         if not file_exists:
#             writer.writerow(["Timestamp", "Token", "Trade Type", "Equity Price"])
#         writer.writerow([timestamp, token, trade_type, equity_price])

# def log_order(timestamp, token, trade_type, equity_price, order_id, option_type, lot_size, option_price=None):
#     """Log successfully placed orders to a CSV file with option price."""
#     csv_file = os.path.join(PATH, "ORDERS_LOG", f"ORDERS_{datetime.datetime.now().strftime('%Y-%m-%d')}.csv")
#     file_exists = os.path.exists(csv_file)

#     row = df_options[df_options["token"] == int(token)]
#     symbol = row["symbol"].values[0] if not row.empty else "UNKNOWN"
#     with open(csv_file, mode='a', newline='') as file:
#         writer = csv.writer(file)
#         if not file_exists:
#             writer.writerow(["Timestamp", "Token", "Symbol", "Trade Type", "Equity Price", "Option Price", "Order ID", "Option Type", "Lot Size"])
#         writer.writerow([timestamp, token, symbol, trade_type, equity_price, option_price, order_id, option_type, lot_size])

# def fetch_option_ltp(option_token):
#     """Fetch current LTP for an option using SmartConnect API"""
#     try:
#         ltp_data = api.ltpData("NFO", "OPTIDX", option_token)
#         if ltp_data and 'data' in ltp_data and 'ltp' in ltp_data['data']:
#             return float(ltp_data['data']['ltp'])
#         return None
#     except Exception as e:
#         print(f"Error fetching LTP for option {option_token}: {e}")
#         return None
    
# def open_trade(option, trade_type, equity_price, timestamp):
#     """Helper function to open a trade and store the selected strike price."""
#     order_id = place_order(option, trade_type)
#     if order_id and option is not None:
#         token = str(option["token"])
#         # Get current option price
#         option_price = fetch_option_ltp(token)
#         if option_price is None:
#             option_price = 0  # Default value if price can't be fetched
        
#         trade_positions[token] = {
#             "entry_price": equity_price,
#             "entry_time": timestamp,
#             "type": trade_type,
#             "strike": option["strike"],
#             "symbol": option["symbol"],
#             "entry_option_price": option_price
#         }
#         trade_cooldowns[token] = timestamp
#         lot_size = int(option["lotsize"])
#         option_type = "CALL" if "CE" in option["symbol"] else "PUT"
#         log_order(timestamp, token, trade_type, equity_price, order_id, option_type, lot_size, option_price)
#         return True
#     return False

# def close_trade(option, trade_type, equity_price, timestamp):
#     """Helper function to close a trade while ensuring it's the same strike price."""
#     if option is None:
#         print("Error: No valid option provided for closing trade.")
#         return False

#     token = str(option["token"])

#     if token not in trade_positions:
#         print(f"Warning: No active trade found for token {token}")
#         return False

#     entry_symbol = trade_positions[token]["symbol"]

#     if entry_symbol != option["symbol"]:
#         print(f"Skipping closing trade. {entry_symbol} != {option['symbol']}")
#         return False

#     lot_size = int(option["lotsize"])
#     option_type = "CALL" if "CE" in option["symbol"] else "PUT"
    
#     # Get current option price
#     option_price = option_ltp_data.get(token) or fetch_option_ltp(token)
#     if option_price is None:
#         option_price = 0  # Default value if price can't be fetched

#     order_id = place_order(option, trade_type)
#     if order_id:
#         # Log to both order and trade logs with option price
#         log_order(timestamp, token, trade_type, equity_price, order_id, option_type, lot_size, option_price)
#         print(f"Closing trade for token {token} at equity price {equity_price}, option price {option_price}")
#         del trade_positions[token]
#         trade_cooldowns[token] = timestamp
#         return True
#     return False

# def check_stop_loss(token, current_option_ltp):
#     """Check if stop loss is triggered for a position"""
#     if token not in trade_positions:
#         return False
        
#     entry_price = trade_positions[token].get("entry_option_price", 0)
#     if entry_price == 0:
#         return False
        
#     price_diff = calculate_percentage_difference(entry_price, current_option_ltp)
    
#     # Check for stop loss (negative percentage)
#     if price_diff <= -STOP_LOSS_PERCENTAGE:
#         print(f"STOP LOSS TRIGGERED for token {token}: {price_diff:.2f}%")
#         return True
        
#     return False

# def decide_trade(equity_token, prices, volumes, timestamp, itm_call, itm_put):
#     global trade_positions, trade_cooldowns, option_positions, option_ltp_data

#     # Check if within trading time
#     if not is_trading_time():
#         print(f"Outside trading hours ({TRADE_START_TIME} to {TRADE_END_TIME}). Skipping trade decision.")
#         return

#     if len(prices) < max(EMA_LONG_PERIOD, BOLLINGER_PERIOD):
#         return

#     current_price = prices[-1]
#     current_volume = volumes[-1]

#     # Check previous day high/low constraints
#     if equity_token in previous_day_data:
#         prev_high = previous_day_data[equity_token]['high']
#         prev_low = previous_day_data[equity_token]['low']
        
#         print(f"Previous Day: High={prev_high}, Low={prev_low}, Current={current_price}")
        
#         # Trading constraints based on previous day levels
#         if current_price > prev_high:
#             print("Price above yesterday's high - Only SELL trades allowed")
#             # Don't allow BUY trades
#             itm_call = None
#         elif current_price < prev_low:
#             print("Price below yesterday's low - Only BUY trades allowed")
#             # Don't allow SELL trades
#             itm_put = None

#     # Indicators
#     ema_short = calculate_ema(prices, EMA_SHORT_PERIOD)
#     ema_long = calculate_ema(prices, EMA_LONG_PERIOD)
#     upper_band, lower_band = calculate_bollinger_bands(prices, BOLLINGER_PERIOD, BOLLINGER_STD_DEV)
#     rsi = calculate_rsi(prices)

#     print(f"\nToken: {equity_token}, Time: {timestamp}")
#     print(f"  Current Price: {current_price}")
#     print(f"  EMA Short: {ema_short}, EMA Long: {ema_long}")
#     print(f"  Bollinger Bands: Upper: {upper_band}, Lower: {lower_band}")
#     print(f"  RSI: {rsi}")
    
#     if None in [ema_short, ema_long, upper_band, lower_band, rsi]:
#         return

#     # Cooldown check
#     if equity_token in trade_cooldowns and timestamp < trade_cooldowns[equity_token] + TRADE_COOLDOWN_PERIOD:
#         return

#     # EXIT LOGIC (Profit taking and Stop Loss)
#     tokens_to_close = list(option_positions.keys())  # iterate over a copy
#     for token in tokens_to_close:
#         option_info = option_positions[token]
#         option = option_info["option"]
#         option_token = str(option["token"])

#         # Get LTP from WebSocket first, then fallback to HTTP
#         current_option_ltp = option_ltp_data.get(option_token)
#         if current_option_ltp is None:
#             current_option_ltp = fetch_option_ltp(option_token)
#             if current_option_ltp is None:
#                 print(f"Skipping exit: Couldn't fetch option LTP for {option_token}")
#                 continue

#         entry_price = trade_positions.get(token, {}).get("entry_option_price", 0)
#         if entry_price == 0:
#             trade_positions[token]["entry_option_price"] = current_option_ltp
#             entry_price = current_option_ltp

#         option_price_diff = calculate_percentage_difference(entry_price, current_option_ltp)

#         print(f"Exit Check | Option Token: {option_token} | % Change: {option_price_diff:.2f}%")

#         # Check for stop loss first
#         if check_stop_loss(token, current_option_ltp):
#             if close_trade(option, "SELL", current_option_ltp, timestamp):
#                 del trade_positions[token]
#                 del option_positions[token]
#                 trade_cooldowns[token] = timestamp
#         # Then check for profit taking
#         elif option_price_diff >= OPTION_PROFIT_THRESHOLD:
#             if close_trade(option, "SELL", current_option_ltp, timestamp):
#                 del trade_positions[token]
#                 del option_positions[token]
#                 trade_cooldowns[token] = timestamp
    
#     # ENTRY LOGIC
#     if equity_token not in trade_positions:
#         # ENTRY: Buy CALL (bullish) - Only if price is not below yesterday's low
#         if (itm_call is not None and ema_short > ema_long and current_price <= lower_band and rsi < 30):
#             if open_trade(itm_call, "BUY", current_price, timestamp):
#                 trade_positions[equity_token] = {
#                     "entry_price": current_price,
#                     "entry_time": timestamp,
#                     "entry_option_price": 0,
#                     "type": "BUY"
#                 }
#                 option_positions[equity_token] = {
#                     "option": itm_call,
#                     "type": "CALL",
#                     "entry_time": timestamp
#                 }
#                 trade_cooldowns[equity_token] = timestamp
#                 # Subscribe to option token
#                 call_token = str(itm_call["token"])
#                 sws.subscribe("stream_2", 2, [{"exchangeType": 2, "tokens": [call_token]}])

#         # ENTRY: Buy PUT (bearish) - Only if price is not above yesterday's high
#         elif (itm_put is not None and ema_short < ema_long and current_price >= upper_band and rsi > 70):
#             log_trade(timestamp, equity_token, "SELL", current_price)
#             if open_trade(itm_put, "BUY", current_price, timestamp):
#                 trade_positions[equity_token] = {
#                     "entry_price": current_price,
#                     "entry_time": timestamp,
#                     "entry_option_price": 0,
#                     "type": "SELL"
#                 }
#                 option_positions[equity_token] = {
#                     "option": itm_put,
#                     "type": "PUT",
#                     "entry_time": timestamp
#                 }
#                 trade_cooldowns[equity_token] = timestamp
#                 # Subscribe to option token
#                 put_token = str(itm_put["token"])
#                 sws.subscribe("stream_2", 2, [{"exchangeType": 2, "tokens": [put_token]}])

# def on_data(wsapp, message):
#     try:
#         # Handle both dictionary and string messages
#         if isinstance(message, str):
#             message = json.loads(message)
        
#         # Process option data
#         if message.get("exchange_type") == 2:  # NFO exchange
#             option_token = str(message.get("token"))
#             ltp = float(message.get("last_traded_price", 0)) / 100  # Normalize
#             option_ltp_data[option_token] = ltp
#             print(f"Updated LTP for option {option_token}: {ltp}")
#             return
        
#         # Process equity messages
#         equity_token = str(message.get("token"))
#         close_price = float(message.get("last_traded_price", 0)) / 100
#         buy_quantity = float(message.get("total_buy_quantity", 0))
#         sell_quantity = float(message.get("total_sell_quantity", 0))
#         timestamp = datetime.datetime.now()

#         net_vol = buy_quantity - sell_quantity

#         if equity_token not in price_data:
#             price_data[equity_token] = []
#             volume_data[equity_token] = []

#         price_data[equity_token].append(close_price)
#         volume_data[equity_token].append(net_vol)

#         # Maintain fixed window size
#         if len(price_data[equity_token]) > max(EMA_LONG_PERIOD, BOLLINGER_PERIOD):
#             price_data[equity_token].pop(0)
#             volume_data[equity_token].pop(0)

#         print(f"Updated Prices for {equity_token}: {price_data[equity_token][-5:]}")  # Print last 5 prices
#         print(f"Price Data Length: {len(price_data[equity_token])}")

#         itm_call, itm_put, call_token, put_token = select_itm_options(close_price, equity_token, df_options)
#         decide_trade(equity_token, price_data[equity_token], volume_data[equity_token], timestamp, itm_call, itm_put)
    
#     except Exception as e:
#         print(f"Error in on_data: {e}")
#         import traceback
#         traceback.print_exc()

# # -----------------------------------------------
# # Main Execution
# # -----------------------------------------------
# if __name__ == "__main__":
#     TOKENS = list(TOKEN_SYMBOL_MAP.keys())
    
#     # Fetch previous day data before starting
#     print("Fetching previous trading day high/low data...")
#     fetch_previous_day_data()
    
#     def on_open(wsapp):
#         # Subscribe to equity tokens (NSE exchange)
#         sws.subscribe("stream_1", 3, [{"exchangeType": 1, "tokens": TOKENS}])
#         print(f"Subscribed to equity tokens: {TOKENS}")
#         print(f"Trading hours: {TRADE_START_TIME} to {TRADE_END_TIME}")
    
#     sws.on_open = on_open
#     sws.on_data = on_data
#     sws.on_error = lambda wsapp, error: print(f"WebSocket error: {error}")
#     sws.on_close = lambda wsapp: print("WebSocket connection closed")
    
#     try:
#         sws.connect()
#         print("WebSocket connection initiated...")
#     except Exception as e:
#         print(f"Failed to connect to WebSocket: {e}")

# import http.client
# from SmartApi import SmartConnect
# from pyotp import TOTP
# import json
# import csv
# import time
# import os
# import datetime
# import pandas as pd

# # Connection to the Angel Broking API
# conn = http.client.HTTPSConnection("apiconnect.angelbroking.com")

# # List of symbol tokens
# symbol_tokens = [
#     13786, 1964, 11403, 9552, 3150, 4684, 1901, 17963, 13, 3103, 3518, 7929,
#     11195, 2303, 1406, 6545, 24184, 13611, 10099, 15380, 19913, 4745, 8479,
#     1232, 10440, 526, 694, 22377, 15083, 25780, 14309, 1270, 16675, 15141,
#     4244, 10604, 3351, 3220, 1624, 17400, 2142, 10666, 312, 547, 9819, 21770,
#     4306, 685, 10447, 2277, 21808, 10940, 2181, 11703, 2664, 25, 22, 20374,
#     13285, 11373, 20242, 14592, 1633, 11532, 23650, 15355, 3563, 11184, 275,
#     10753, 2535, 14418, 760, 881, 438, 17094, 9590, 10217, 7229, 14732, 1023,
#     4668, 21238, 11536, 1660, 9599, 212, 14413, 3411, 2029, 10243, 13751,
#     5900, 2885, 1997, 9480, 910, 772, 317, 2144, 404, 157, 467, 17029,
#     14299, 3506, 236, 8075, 21690, 1363, 18652, 2043, 3812, 958, 3045, 11723,
#     4963, 3787, 18564, 11630, 422, 4749, 20302, 3721, 13538, 739, 1394, 17875,
#     11915, 2475, 6066, 305, 17818, 10794, 18921, 21614, 30108, 17971, 2031,
#     1186, 1922, 1348, 383, 4067, 14672, 17438, 3273, 371, 11483, 1333, 13750,
#     13404, 19943, 10999, 11543, 11262, 16965, 509, 3456, 5373, 6733, 11654,
#     16713, 11287, 11351, 17869, 18365, 5258, 2963, 8110, 3063, 18096, 3718,
#     14977, 19234, 1594, 1512, 14366, 335, 4503, 6656, 16669, 6705, 2263, 2412,
#     3426, 9683, 3499, 10599, 4717, 1008, 15332, 8596, 163, 24948, 4204, 29135,
#     5097, 3432, 3405
# ]

# # Initialize SmartConnect with your credentials
# obj = SmartConnect('4GznkDiG')
# data = obj.generateSession('R103352', 7020, TOTP('RV62S7GJBGHGWKRAYSQ6SRTPVM').now())

# # Define headers for the API request
# headers = {
#     'X-PrivateKey': '4GznkDiG',
#     'Accept': 'application/json',
#     'X-SourceID': 'WEB',
#     'X-ClientLocalIP': 'CLIENT_LOCAL_IP',
#     'X-ClientPublicIP': 'CLIENT_PUBLIC_IP',
#     'X-MACAddress': 'MAC_ADDRESS',
#     'X-UserType': 'USER',
#     'Authorization': data["data"]["jwtToken"],
#     'Content-Type': 'application/json'
# }

# # Define date range for the data
# from_date = "2018-01-01 09:15"
# to_date = "2024-01-01 15:30"

# # Directory where CSV files will be saved
# output_directory = r"C:\Users\hp\Desktop\HIstorical_data"

# # Create the directory if it doesn't exist
# os.makedirs(output_directory, exist_ok=True)

# # Dictionary to store previous day data for each token
# previous_day_data = {}

# def fetch_previous_day_data(token):
#     """Fetch previous day's high and low for a specific token"""
#     try:
#         # Get yesterday's date
#         yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
#         yesterday_str = yesterday.strftime('%Y-%m-%d')
        
#         # Fetch historical data for the previous day
#         payload = {
#             "exchange": "NSE",
#             "symboltoken": token,
#             "interval": "ONE_DAY",
#             "fromdate": yesterday_str + " 09:00",
#             "todate": yesterday_str + " 15:30"
#         }
        
#         conn.request("POST", "/rest/secure/angelbroking/historical/v1/getCandleData", json.dumps(payload), headers)
#         res = conn.getresponse()
#         response_data = res.read().decode("utf-8")
#         json_data = json.loads(response_data)
        
#         if json_data and 'data' in json_data and json_data['data']:
#             day_data = json_data['data'][0]  # Get the first (and only) day's data
#             previous_day_data[token] = {
#                 'high': float(day_data[2]),  # High price
#                 'low': float(day_data[3])    # Low price
#             }
#             print(f"Previous day data for token {token}: High={previous_day_data[token]['high']}, Low={previous_day_data[token]['low']}")
#         else:
#             print(f"Warning: No historical data found for token {token}")
#             previous_day_data[token] = {'high': float('inf'), 'low': 0}  # Default values
            
#     except Exception as e:
#         print(f"Error fetching previous day data for token {token}: {e}")
#         previous_day_data[token] = {'high': float('inf'), 'low': 0}  # Default values

# for symbol_token in symbol_tokens:
#     # Fetch previous day data for this token
#     fetch_previous_day_data(symbol_token)
    
#     # Define the file path for each token's data
#     file_path = os.path.join(output_directory, f'{symbol_token}.csv')

#     with open(file_path, mode='w', newline='') as file:
#         writer = csv.writer(file)
#         writer.writerow(['Token', 'Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume', 'PrevDayHigh', 'PrevDayLow'])

#         payload = {
#             "exchange": "NSE",
#             "symboltoken": symbol_token,
#             "interval": "ONE_DAY",
#             "fromdate": from_date,
#             "todate": to_date
#         }

#         while True:
#             try:
#                 conn.request("POST", "/rest/secure/angelbroking/historical/v1/getCandleData", json.dumps(payload), headers)
#                 res = conn.getresponse()
#                 response_data = res.read().decode("utf-8")
#                 json_data = json.loads(response_data)

#                 for record in json_data['data']:
#                     # Add previous day high and low to each record
#                     prev_high = previous_day_data.get(symbol_token, {}).get('high', 0)
#                     prev_low = previous_day_data.get(symbol_token, {}).get('low', 0)
#                     writer.writerow([symbol_token] + record + [prev_high, prev_low])

#                 print(f"Token: {symbol_token} - Data written to {file_path}")
#                 print("------------------------------------------")
#                 break
#             except Exception as e:
#                 print(f"Exception: {e}")
#                 print("Retrying after 3 seconds...")
#                 time.sleep(3)

# conn.close()


import os
import datetime
import csv
import pandas as pd
from pyotp import TOTP
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import json
import http.client
import time

# -----------------------------------------------
# API and WebSocket Setup
# -----------------------------------------------
PATH = r"D:\ALGOTRADING"
os.chdir(PATH)

# Create necessary directories if they don't exist
os.makedirs(os.path.join(PATH, "TRADES_LOG"), exist_ok=True)
os.makedirs(os.path.join(PATH, "ORDERS_LOG"), exist_ok=True)

# Read API credentials
with open("key.txt", "r") as f:
    key_secret = f.read().split()

# Initialize API session
api = SmartConnect(api_key=key_secret[0])
session_data = api.generateSession(key_secret[2], key_secret[3], TOTP(key_secret[4]).now())
feed_token = api.getfeedToken()

# Initialize WebSocket connection
sws = SmartWebSocketV2(
    session_data["data"]["jwtToken"],
    key_secret[0],
    key_secret[2],
    feed_token
)

# -----------------------------------------------
# Load Option Chain for Multiple Stocks
# -----------------------------------------------
option_chain_csv = r"D:\ALGOTRADING\option_chain.csv"
df_options = pd.read_csv(option_chain_csv)
df_options["strike"] /= 100  # Adjusting strike price scale

# -----------------------------------------------
# Equity Token to Symbol Mapping
# -----------------------------------------------
TOKEN_SYMBOL_MAP = {
    "10999": "MARUTI",
    "317": "BAJFINANCE",   
    "383": "BEL",   
    "11483": "LT",   
    "1922": "KOTAKBANK" 
}

# -----------------------------------------------
# Indicator Parameters
# -----------------------------------------------
EMA_SHORT_PERIOD = 27
EMA_LONG_PERIOD = 42
BOLLINGER_PERIOD = 30
BOLLINGER_STD_DEV = 3
RSI_PERIOD = 52
TRADE_COOLDOWN_PERIOD = datetime.timedelta(seconds=180)
OPTION_PROFIT_THRESHOLD = 5.5  # profit for options
STOP_LOSS_PERCENTAGE = 4 # stop loss

# Data Buffers
price_data = {}
volume_data = {}
trade_positions = {}
trade_cooldowns = {}
option_positions = {}
option_ltp_data = {}        

# Store previous day high/low
previous_day_data = {}
        

def fetch_previous_day_data():
    """Fetch previous day's high and low for all stocks using HTTP connection"""
    global previous_day_data
    
    # Initialize SmartConnect with your credentials
    obj = SmartConnect('4GznkDiG')
    data = obj.generateSession('R103352', 7020, TOTP('RV62S7GJBGHGWKRAYSQ6SRTPVM').now())
    
    # Define headers for the API request
    headers = {
        'X-PrivateKey': '4GznkDiG',
        'Accept': 'application/json',
        'X-SourceID': 'WEB',
        'X-ClientLocalIP': 'CLIENT_LOCAL_IP',
        'X-ClientPublicIP': 'CLIENT_PUBLIC_IP',
        'X-MACAddress': 'MAC_ADDRESS',
        'X-UserType': 'USER',
        'Authorization': data["data"]["jwtToken"],
        'Content-Type': 'application/json'
    }
    
    # Get previous trading day (skip weekends)
    today = datetime.datetime.now()
    for days_back in range(1, 4):
        previous_day = today - datetime.timedelta(days=days_back)
        if previous_day.weekday() < 5:  # Monday to Friday are trading days
            break
    
    previous_day_str = previous_day.strftime('%Y-%m-%d')
    oneday_ago = datetime.datetime.now() - datetime.timedelta(days=2)
    oneday_ago_str = oneday_ago.strftime('%Y-%m-%d')
    
    print(f"Fetching previous trading day data for: {previous_day_str}")
    
    # Create HTTP connection
    conn = http.client.HTTPSConnection("apiconnect.angelbroking.com")
    
    for token, symbol in TOKEN_SYMBOL_MAP.items():
        try:
            # Prepare payload for historical data
            payload = {
                "exchange": "NSE",
                "symboltoken": token,
                "interval": "ONE_DAY",
                "fromdate": oneday_ago_str + " 09:00",
                "todate": previous_day_str + " 15:30"
            }
            
            # Make API request
            conn.request("POST", "/rest/secure/angelbroking/historical/v1/getCandleData", 
                        json.dumps(payload), headers)
            
            res = conn.getresponse()
            response_data = res.read().decode("utf-8")
            json_data = json.loads(response_data)
            
            if json_data and 'data' in json_data and json_data['data']:
                day_data = json_data['data'][0]  # Get the first day's data
                previous_day_data[token] = {
                    'high': float(day_data[2]),  # High price (index 2)
                    'low': float(day_data[3])    # Low price (index 3)
                }
                print(f"Previous day data for {symbol}: High={previous_day_data[token]['high']}, Low={previous_day_data[token]['low']}")
            else:
                print(f"Warning: No historical data found for {symbol}")
                previous_day_data[token] = {'high': float('inf'), 'low': 0}
                
        except Exception as e:
            print(f"Error fetching previous day data for {symbol}: {e}")
            previous_day_data[token] = {'high': float('inf'), 'low': 0}
    
    # Close the connection
    conn.close()
# -----------------------------------------------
# Helper Functions
# -----------------------------------------------
def select_itm_options(current_price, token, df):
    """Selects the nearest ITM Call and Put options dynamically for a given equity token."""
    stock_name = TOKEN_SYMBOL_MAP.get(token)
    if not stock_name:
        print(f"ERROR: No symbol mapping found for equity token {token}")
        return None, None, None, None

    stock_options = df[df["name"] == stock_name]

    if stock_options.empty:
        print(f"ERROR: No options found for symbol {stock_name}. Check option_chain.csv.")
        return None, None, None, None

    print(f"\nChecking ITM Options for {stock_name} at price {current_price}")

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

    # Return both the option data and their tokens
    call_token = str(closest_itm_call["token"]) if closest_itm_call is not None else None
    put_token = str(closest_itm_put["token"]) if closest_itm_put is not None else None
    
    return closest_itm_call, closest_itm_put, call_token, put_token

def place_order(option, trade_type):
    """Place a buy or sell order using the correct trading symbol."""
    if option is None:
        print("Error: No valid option provided for order placement.")
        return None

    token = str(option["token"])
    trading_symbol = option["symbol"]
    lot_size = int(option["lotsize"])

    try:
        order_params = {
            "variety": "NORMAL",
            "tradingsymbol": trading_symbol,
            "symboltoken": token,
            "transactiontype": trade_type,
            "exchange": "NFO",
            "ordertype": "MARKET",
            "producttype": "CARRYFORWARD",
            "duration": "DAY",
            "quantity": str(lot_size)
        }
        order_response = api.placeOrder(order_params)

        if isinstance(order_response, str):
            order_id = order_response.strip()
            print(f"Order placed successfully: {order_id} for {trading_symbol}")
            return order_id
        elif isinstance(order_response, dict) and 'data' in order_response:
            order_id = order_response['data']['orderid']
            print(f"Order placed successfully: {order_id} for {trading_symbol}")
            return order_id

        print(f"Order placement failed: Unexpected response format: {order_response}")
        return None
    except Exception as e:
        print(f"Error placing order: {e}")
        return None
    
def calculate_ema(prices, period):
    return pd.Series(prices).ewm(span=period, adjust=False).mean().iloc[-1] if len(prices) >= period else None

def calculate_bollinger_bands(prices, period, std_dev):
    if len(prices) < period:
        return None, None
    rolling_mean = pd.Series(prices).rolling(window=period).mean()
    rolling_std = pd.Series(prices).rolling(window=period).std()
    upper_band = rolling_mean.iloc[-1] + (rolling_std.iloc[-1] * std_dev)
    lower_band = rolling_mean.iloc[-1] - (rolling_std.iloc[-1] * std_dev)
    return upper_band, lower_band

def calculate_zlma(prices, period):
    """Calculate Zero Lag Moving Average (ZLMA)."""
    if len(prices) < period:
        return None
    series = pd.Series(prices)
    ema1 = series.ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    diff = ema1 - ema2
    zlma = ema1 + diff  # Zero Lag correction
    return zlma.iloc[-1]

def calculate_rsi(prices, period=14):
    if len(prices) < period:
        return None
    delta = pd.Series(prices).diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs)).iloc[-1]

def calculate_percentage_difference(entry_price, current_price):
    return ((current_price - entry_price) / entry_price) * 100

def log_trade(timestamp, token, trade_type, equity_price):
    """Simplified logging: Only logs token, trade type, and equity price."""
    csv_file = os.path.join(PATH, "TRADES_LOG", f"TRADES_{datetime.datetime.now().strftime('%Y-%m-%d')}.csv")
    os.makedirs(os.path.dirname(csv_file), exist_ok=True)

    file_exists = os.path.exists(csv_file)
    with open(csv_file, mode='a', newline='') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Timestamp", "Token", "Trade Type", "Equity Price"])
        writer.writerow([timestamp, token, trade_type, equity_price])

def log_order(timestamp, token, trade_type, equity_price, order_id, option_type, lot_size, option_price=None):
    """Log successfully placed orders to a CSV file with option price."""
    csv_file = os.path.join(PATH, "Order_LOG", f"ORDERS_{datetime.datetime.now().strftime('%Y-%m-%d')}.csv")
    os.makedirs(os.path.dirname(csv_file), exist_ok=True)
    file_exists = os.path.exists(csv_file)

    row = df_options[df_options["token"] == int(token)]
    symbol = row["symbol"].values[0] if not row.empty else "UNKNOWN"
    with open(csv_file, mode='a', newline='') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Timestamp", "Token", "Symbol", "Trade Type", "Equity Price", "Option Price", "Order ID", "Option Type", "Lot Size"])
        writer.writerow([timestamp, token, symbol, trade_type, equity_price, option_price, order_id, option_type, lot_size])

def fetch_option_ltp(option_token):
    """Fetch current LTP for an option using SmartConnect API"""
    try:
        ltp_data = api.ltpData("NFO", "OPTIDX", option_token)
        if ltp_data and 'data' in ltp_data and 'ltp' in ltp_data['data']:
            return float(ltp_data['data']['ltp'])
        return None
    except Exception as e:
        print(f"Error fetching LTP for option {option_token}: {e}")
        return None
    
def open_trade(option, trade_type, equity_price, timestamp):
    """Helper function to open a trade and store the selected strike price."""
    order_id = place_order(option, trade_type)
    if order_id and option is not None:
        token = str(option["token"])
        # Get current option price
        option_price = fetch_option_ltp(token)
        if option_price is None:
            option_price = 0  # Default value if price can't be fetched
        
        trade_positions[token] = {
            "entry_price": equity_price,
            "entry_time": timestamp,
            "type": trade_type,
            "strike": option["strike"],
            "symbol": option["symbol"],
            "entry_option_price": option_price
        }
        trade_cooldowns[token] = timestamp
        lot_size = int(option["lotsize"])
        option_type = "CALL" if "CE" in option["symbol"] else "PUT"
        log_order(timestamp, token, trade_type, equity_price, order_id, option_type, lot_size, option_price)
        return True
    return False

def close_trade(option, trade_type, equity_price, timestamp):
    """Helper function to close a trade while ensuring it's the same strike price."""
    if option is None:
        print("Error: No valid option provided for closing trade.")
        return False

    token = str(option["token"])

    if token not in trade_positions:
        print(f"Warning: No active trade found for token {token}")
        return False

    entry_symbol = trade_positions[token]["symbol"]

    if entry_symbol != option["symbol"]:
        print(f"Skipping closing trade. {entry_symbol} != {option['symbol']}")
        return False

    lot_size = int(option["lotsize"])
    option_type = "CALL" if "CE" in option["symbol"] else "PUT"
    
    # Get current option price
    option_price = option_ltp_data.get(token) or fetch_option_ltp(token)
    if option_price is None:
        option_price = 0  # Default value if price can't be fetched

    order_id = place_order(option, trade_type)
    if order_id:
        # Log to both order and trade logs with option price
        log_order(timestamp, token, trade_type, equity_price, order_id, option_type, lot_size, option_price)
        print(f"Closing trade for token {token} at equity price {equity_price}, option price {option_price}")
        del trade_positions[token]
        trade_cooldowns[token] = timestamp
        return True
    return False

def check_stop_loss(token, current_option_ltp):
    """Check if stop loss is triggered for a position"""
    if token not in trade_positions:
        return False
        
    entry_price = trade_positions[token].get("entry_option_price", 0)
    if entry_price == 0:
        return False
        
    price_diff = calculate_percentage_difference(entry_price, current_option_ltp)
    
    # Check for stop loss (negative percentage)
    if price_diff <= -STOP_LOSS_PERCENTAGE:
        print(f"STOP LOSS TRIGGERED for token {token}: {price_diff:.2f}%")
        return True
        
    return False

def decide_trade(equity_token, prices, volumes, timestamp, itm_call, itm_put):
    global trade_positions, trade_cooldowns, option_positions, option_ltp_data

    if len(prices) < max(EMA_LONG_PERIOD, BOLLINGER_PERIOD):
        return

    current_price = prices[-1]
    current_volume = volumes[-1]

    # Check previous day high/low constraints
    if equity_token in previous_day_data:
        prev_high = previous_day_data[equity_token]['high']
        prev_low = previous_day_data[equity_token]['low']
        
        print(f"Previous Day: High={prev_high}, Low={prev_low}, Current={current_price}")
        
        # Trading constraints based on previous day levels
        if current_price > prev_high:
            print("Price above yesterday's high - Only SELL trades allowed")
            # Don't allow BUY trades
            itm_call = None
        elif current_price < prev_low:
            print("Price below yesterday's low - Only BUY trades allowed")
            # Don't allow SELL trades
            itm_put = None

    
    # ema_short = calculate_zlma(prices, EMA_SHORT_PERIOD)
    # ema_long = calculate_zlma(prices, EMA_LONG_PERIOD)
    # Indicators
    ema_short = calculate_ema(prices, EMA_SHORT_PERIOD)
    ema_long = calculate_ema(prices, EMA_LONG_PERIOD)
    upper_band, lower_band = calculate_bollinger_bands(prices, BOLLINGER_PERIOD, BOLLINGER_STD_DEV)
    rsi = calculate_rsi(prices)

    print(f"\nToken: {equity_token}, Time: {timestamp}")
    print(f"  Current Price: {current_price}")
    print(f"  EMA Short: {ema_short}, EMA Long: {ema_long}")
    print(f"  Bollinger Bands: Upper: {upper_band}, Lower: {lower_band}")
    print(f"  RSI: {rsi}")
    
    if None in [ema_short, ema_long, upper_band, lower_band, rsi]:
        return

    # Cooldown check
    if equity_token in trade_cooldowns and timestamp < trade_cooldowns[equity_token] + TRADE_COOLDOWN_PERIOD:
        return

    # EXIT LOGIC (Profit taking and Stop Loss)
    tokens_to_close = list(option_positions.keys())  # iterate over a copy
    for token in tokens_to_close:
        option_info = option_positions[token]
        option = option_info["option"]
        option_token = str(option["token"])

        # Get LTP from WebSocket first, then fallback to HTTP
        current_option_ltp = option_ltp_data.get(option_token)
        if current_option_ltp is None:
            current_option_ltp = fetch_option_ltp(option_token)
            if current_option_ltp is None:
                print(f"Skipping exit: Couldn't fetch option LTP for {option_token}")
                continue

        entry_price = trade_positions.get(token, {}).get("entry_option_price", 0)
        if entry_price == 0:
            trade_positions[token]["entry_option_price"] = current_option_ltp
            entry_price = current_option_ltp

        option_price_diff = calculate_percentage_difference(entry_price, current_option_ltp)

        print(f"Exit Check | Option Token: {option_token} | % Change: {option_price_diff:.2f}%")

        # Check for stop loss first
        # if check_stop_loss(token, current_option_ltp):
        #     if close_trade(option, "SELL", current_option_ltp, timestamp):
        #         del trade_positions[token]
        #         del option_positions[token]
        #         trade_cooldowns[token] = timestamp
        # Then check for profit taking
        if option_price_diff >= OPTION_PROFIT_THRESHOLD:
            if close_trade(option, "SELL", current_option_ltp, timestamp):
                del trade_positions[token]
                del option_positions[token]
                trade_cooldowns[token] = timestamp
    
    prev_high = previous_day_data.get(equity_token, {}).get("high", float('inf'))
    prev_low = previous_day_data.get(equity_token, {}).get("low", 0)

    # ENTRY LOGIC with yesterday's high/low filter
    if equity_token not in trade_positions:
        # ✅ Only BUY (Call) allowed if price > yesterday's low
        if ema_short > ema_long and current_price <= lower_band and rsi < 30:
            if current_price <= prev_high:  # Do not buy above yesterday's high
                if open_trade(itm_call, "BUY", current_price, timestamp):
                    trade_positions[equity_token] = {
                        "entry_price": current_price,
                        "entry_time": timestamp,
                        "entry_option_price": 0,
                        "type": "BUY"
                    }
                    option_positions[equity_token] = {"option": itm_call, "type": "CALL", "entry_time": timestamp}
                    trade_cooldowns[equity_token] = timestamp
                    call_token = str(itm_call["token"])
                    sws.subscribe("stream_2", 2, [{"exchangeType": 2, "tokens": [call_token]}])
            else:
                print(f"BUY blocked: price {current_price} > yesterday's high {prev_high}")

        # ✅ Only SELL (Put) allowed if price < yesterday's high
        elif ema_short < ema_long and current_price >= upper_band and rsi > 70:
            if current_price >= prev_low:  # Do not sell below yesterday's low
                if open_trade(itm_put, "BUY", current_price, timestamp):
                    trade_positions[equity_token] = {
                        "entry_price": current_price,
                        "entry_time": timestamp,
                        "entry_option_price": 0,
                        "type": "SELL"
                    }
                    option_positions[equity_token] = {"option": itm_put, "type": "PUT", "entry_time": timestamp}
                    trade_cooldowns[equity_token] = timestamp
                    put_token = str(itm_put["token"])
                    sws.subscribe("stream_2", 2, [{"exchangeType": 2, "tokens": [put_token]}])
            else:
                print(f"SELL blocked: price {current_price} < yesterday's low {prev_low}")


def on_data(wsapp, message):
    try:
        # Handle both dictionary and string messages
        if isinstance(message, str):
            message = json.loads(message)
        
        # Process option data
        if message.get("exchange_type") == 2:  # NFO exchange
            option_token = str(message.get("token"))
            ltp = float(message.get("last_traded_price", 0)) / 100  # Normalize
            option_ltp_data[option_token] = ltp
            print(f"Updated LTP for option {option_token}: {ltp}")
            return
        
        # Process equity messages
        equity_token = str(message.get("token"))
        close_price = float(message.get("last_traded_price", 0)) / 100
        buy_quantity = float(message.get("total_buy_quantity", 0))
        sell_quantity = float(message.get("total_sell_quantity", 0))
        timestamp = datetime.datetime.now()

        net_vol = buy_quantity - sell_quantity

        if equity_token not in price_data:
            price_data[equity_token] = []
            volume_data[equity_token] = []

        price_data[equity_token].append(close_price)
        volume_data[equity_token].append(net_vol)

        # Maintain fixed window size
        if len(price_data[equity_token]) > max(EMA_LONG_PERIOD, BOLLINGER_PERIOD):
            price_data[equity_token].pop(0)
            volume_data[equity_token].pop(0)

        print(f"Updated Prices for {equity_token}: {price_data[equity_token][-5:]}")  # Print last 5 prices
        print(f"Price Data Length: {len(price_data[equity_token])}")

        itm_call, itm_put, call_token, put_token = select_itm_options(close_price, equity_token, df_options)
        decide_trade(equity_token, price_data[equity_token], volume_data[equity_token], timestamp, itm_call, itm_put)
    
    except Exception as e:
        print(f"Error in on_data: {e}")
        import traceback
        traceback.print_exc()

# -----------------------------------------------
# Main Execution
# -----------------------------------------------
if __name__ == "__main__":
    TOKENS = list(TOKEN_SYMBOL_MAP.keys())
    
    # Fetch previous day data before starting
    print("Fetching previous day high/low data...")
    fetch_previous_day_data()
    
    def on_open(wsapp):
        # Subscribe to equity tokens (NSE exchange)
        sws.subscribe("stream_1", 3, [{"exchangeType": 1, "tokens": TOKENS}])
        print(f"Subscribed to equity tokens: {TOKENS}")
    
    sws.on_open = on_open
    sws.on_data = on_data
    sws.on_error = lambda wsapp, error: print(f"WebSocket error: {error}")
    sws.on_close = lambda wsapp: print("WebSocket connection closed")
    
    try:
        sws.connect()
        print("WebSocket connection initiated...")
    except Exception as e:
        print(f"Failed to connect to WebSocket: {e}")