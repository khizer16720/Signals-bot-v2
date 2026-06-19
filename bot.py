import os
import requests
import pandas as pd
import pandas_ta as ta
import threading
from flask import Flask

app = Flask(__name__)
REPORT = "<h3>⏳ Scalping Backtest (ATR Optimized) chal raha hai...</h3>"

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

def fetch_data(symbol, candles=5000):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit={candles}"
    try:
        res = requests.get(url, timeout=10).json()
        df = pd.DataFrame(res, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'ct', 'qav', 'nt', 'tb', 'tq', 'ignore'])
        for col in ['open', 'high', 'low', 'close']: df[col] = df[col].astype(float)
        return df
    except: return None

def run_scalping_backtest(df):
    df['EMA_200'] = ta.ema(df['close'], length=200)
    df['RSI'] = ta.rsi(df['close'], length=14)
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    bb = ta.bbands(df['close'], length=20, std=2)
    df['BBL'] = bb.iloc[:, 0]
    df['BBU'] = bb.iloc[:, 2]
    
    pnl = 0
    
    for i in range(200, len(df) - 5):
        # Entry Condition
        long_cond = (df['close'][i] > df['EMA_200'][i]) and (df['close'][i] <= df['BBL'][i]) and (df['RSI'][i] < 40)
        short_cond = (df['close'][i] < df['EMA_200'][i]) and (df['close'][i] >= df['BBU'][i]) and (df['RSI'][i] > 60)
        
        if long_cond or short_cond:
            entry = df['close'][i]
            # Dynamic SL based on ATR, TP based on 2x Risk
            sl_dist = df['ATR'][i] * 1.5 
            tp_dist = df['ATR'][i] * 3.0
            
            sl = entry - sl_dist if long_cond else entry + sl_dist
            tp = entry + tp_dist if long_cond else entry - tp_dist
            
            for j in range(i+1, i+10): # Thoda zyada time diya
                if (long_cond and df['high'][j] >= tp) or (short_cond and df['low'][j] <= tp):
                    pnl += 12; break # $12 profit
                if (long_cond and df['low'][j] <= sl) or (short_cond and df['high'][j] >= sl):
                    pnl -= 6; break  # $6 loss
    return pnl

# ... [generate_report aur flask app ka code wahi rahega]
