import os
import time
import requests
import pandas as pd
import pandas_ta as ta
import threading
from flask import Flask

app = Flask(__name__)

BACKTEST_REPORT = "<h3>⏳ Backtest process mein hai... 15 seconds wait karke page refresh karein.</h3>"

def fetch_historical_data(symbol="ETHUSDT", interval="5m", total_candles=2000):
    url = "https://api.binance.com/api/v3/klines"
    all_candles = []
    end_time = None
    
    # Sirf 2000 candles fetch karna
    params = {"symbol": symbol, "interval": interval, "limit": total_candles}
    try:
        res = requests.get(url, params=params, timeout=15).json()
        all_candles = res
    except Exception as e:
        print(f"Fetch error: {e}")
        return None
        
    df = pd.DataFrame(all_candles, columns=[
        'time', 'open', 'high', 'low', 'close', 'volume', 
        'close_time', 'qav', 'num_trades', 'taker_base', 'taker_quote', 'ignore'
    ])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    return df

def apply_indicators(df):
    df.ta.ema(length=21, append=True)
    df.ta.rsi(length=14, append=True)
    df.ta.bbands(length=20, std=2, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df['SMA_20_Volume'] = df['volume'].rolling(window=20).mean()
    df.ta.atr(length=14, append=True)
    return df

def run_backtest(df):
    trades = []
    # Dynamic column picking
    bbl = [c for c in df.columns if c.startswith('BBL_')][0]
    bbu = [c for c in df.columns if c.startswith('BBU_')][0]
    atr = [c for c in df.columns if c.startswith('ATR_')][0]
    
    for i in range(21, len(df) - 1):
        if df['close'][i] > df['EMA_21'][i] and df['RSI_14'][i] < 35 and df['close'][i] <= df[bbl][i]:
            signal = "LONG"
        elif df['close'][i] < df['EMA_21'][i] and df['RSI_14'][i] > 65 and df['close'][i] >= df[bbu][i]:
            signal = "SHORT"
        else:
            continue
            
        entry = df['open'][i+1]
        sl = entry - (df[atr][i] * 0.5) if signal == "LONG" else entry + (df[atr][i] * 0.5)
        tp = entry + (df[atr][i] * 1.0) if signal == "LONG" else entry - (df[atr][i] * 1.0)
        
        for j in range(i+1, min(i+10, len(df))):
            if (signal == "LONG" and df['low'][j] <= sl) or (signal == "SHORT" and df['high'][j] >= sl):
                trades.append("SL")
                break
            if (signal == "LONG" and df['high'][j] >= tp) or (signal == "SHORT" and df['low'][j] <= tp):
                trades.append("TP")
                break
    return trades

def generate_report():
    global BACKTEST_REPORT
    df = fetch_historical_data()
    if df is not None:
        df = apply_indicators(df)
        results = run_backtest(df)
        tp = results.count("TP")
        sl = results.count("SL")
        win_rate = (tp / (tp + sl) * 100) if (tp + sl) > 0 else 0
        BACKTEST_REPORT = f"<h1>Result: {win_rate:.2f}% Win Rate</h1><p>TP: {tp}, SL: {sl}</p>"
    else:
        BACKTEST_REPORT = "<h3>Error fetching data from Binance.</h3>"

@app.route('/')
def home():
    return BACKTEST_REPORT

if __name__ == "__main__":
    threading.Thread(target=generate_report, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
    
