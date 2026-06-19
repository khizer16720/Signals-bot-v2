import os
import time
import requests
import pandas as pd
import pandas_ta as ta
import threading
from flask import Flask

app = Flask(__name__)

BACKTEST_REPORT = "<h3>⏳ Backtest process mein hai...</h3>"

def fetch_historical_data(symbol="ETHUSDT", interval="5m", total_candles=5000):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": total_candles}
    try:
        res = requests.get(url, params=params, timeout=15).json()
        df = pd.DataFrame(res, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base', 'taker_quote', 'ignore'])
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].astype(float)
        return df
    except Exception as e:
        return None

def run_backtest(df):
    # EMA 9 aur 21 ka crossover check karenge
    df['EMA9'] = ta.ema(df['close'], length=9)
    df['EMA21'] = ta.ema(df['close'], length=21)
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    trades = []
    for i in range(22, len(df) - 1):
        # Bahot Simple Rule: EMA9 jab EMA21 ko cross kare
        if df['EMA9'][i] > df['EMA21'][i] and df['EMA9'][i-1] <= df['EMA21'][i-1]:
            signal = "LONG"
        elif df['EMA9'][i] < df['EMA21'][i] and df['EMA9'][i-1] >= df['EMA21'][i-1]:
            signal = "SHORT"
        else:
            continue
            
        entry = df['close'][i]
        sl = entry - (df['ATR'][i] * 1.5) if signal == "LONG" else entry + (df['ATR'][i] * 1.5)
        tp = entry + (df['ATR'][i] * 3.0) if signal == "LONG" else entry - (df['ATR'][i] * 3.0)
        
        # Agli 10 candles mein check karo SL ya TP
        for j in range(i+1, min(i+11, len(df))):
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
        results = run_backtest(df)
        tp = results.count("TP")
        sl = results.count("SL")
        win_rate = (tp / len(results) * 100) if len(results) > 0 else 0
        BACKTEST_REPORT = f"<h1>📊 Simple EMA Crossover Results</h1><p><b>Win Rate: {win_rate:.2f}%</b></p><p>Total Trades: {len(results)}</p><p>✅ TP: {tp} | ❌ SL: {sl}</p>"

@app.route('/')
def home():
    return BACKTEST_REPORT

if __name__ == "__main__":
    threading.Thread(target=generate_report, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
    
