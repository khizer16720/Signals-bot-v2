import os
import time
import requests
import pandas as pd
import pandas_ta as ta
import threading
from flask import Flask

app = Flask(__name__)

BACKTEST_REPORT = "<h3>⏳ Backtest process mein hai... 15 seconds wait karke page refresh karein.</h3>"

def fetch_historical_data(symbol="ETHUSDT", interval="5m", total_candles=5000):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": total_candles}
    try:
        res = requests.get(url, params=params, timeout=15).json()
        df = pd.DataFrame(res, columns=[
            'time', 'open', 'high', 'low', 'close', 'volume', 
            'close_time', 'qav', 'num_trades', 'taker_base', 'taker_quote', 'ignore'
        ])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df
    except Exception as e:
        print(f"Fetch error: {e}")
        return None

def apply_indicators(df):
    df.ta.ema(length=21, append=True)
    df.ta.rsi(length=14, append=True)
    df.ta.bbands(length=20, std=2, append=True)
    df.ta.atr(length=14, append=True)
    return df

def run_backtest(df):
    trades = []
    try:
        bbl = [c for c in df.columns if 'BBL' in c][0]
        bbu = [c for c in df.columns if 'BBU' in c][0]
        atr = [c for c in df.columns if 'ATR' in c][0]
    except IndexError:
        raise Exception("Indicators calculate nahi ho sake!")
    
    for i in range(21, len(df) - 1):
        # Loose Conditions (Zyada signals ke liye)
        if df['close'][i] > df['EMA_21'][i] and df['RSI_14'][i] < 45 and df['close'][i] <= (df[bbl][i] * 1.02):
            signal = "LONG"
        elif df['close'][i] < df['EMA_21'][i] and df['RSI_14'][i] > 55 and df['close'][i] >= (df[bbu][i] * 0.98):
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
    try:
        df = fetch_historical_data()
        if df is not None:
            df = apply_indicators(df)
            results = run_backtest(df)
            tp = results.count("TP")
            sl = results.count("SL")
            win_rate = (tp / (tp + sl) * 100) if (tp + sl) > 0 else 0
            BACKTEST_REPORT = f"<h1>📊 Strategy Performance</h1><p><b>Win Rate: {win_rate:.2f}%</b></p><p>Total Trades: {len(results)}</p><p>✅ TP: {tp} | ❌ SL: {sl}</p>"
        else:
            BACKTEST_REPORT = "<h3>Error: Data nahi mil saka.</h3>"
    except Exception as e:
        BACKTEST_REPORT = f"<h3>Error: {str(e)}</h3>"

@app.route('/')
def home():
    return BACKTEST_REPORT

if __name__ == "__main__":
    threading.Thread(target=generate_report, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
    
