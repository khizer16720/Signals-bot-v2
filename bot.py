import os
import requests
import pandas as pd
import pandas_ta as ta
import threading
from flask import Flask

app = Flask(__name__)
REPORT = "<h3>⏳ Backtest process mein hai... 10 seconds baad page refresh karein.</h3>"

def fetch_data(symbol="ETHUSDT", interval="5m", candles=5000):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={candles}"
    try:
        res = requests.get(url, timeout=15).json()
        df = pd.DataFrame(res, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'ct', 'qav', 'nt', 'tb', 'tq', 'ignore'])
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].astype(float)
        return df
    except Exception as e:
        return None

def run_backtest(df):
    # Indicators setup
    df['EMA_9'] = ta.ema(df['close'], length=9)
    df['EMA_21'] = ta.ema(df['close'], length=21)
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    trades = []
    
    # Backtest Loop
    for i in range(22, len(df) - 1):
        if df['EMA_9'][i] > df['EMA_21'][i] and df['EMA_9'][i-1] <= df['EMA_21'][i-1]:
            signal = "LONG"
        elif df['EMA_9'][i] < df['EMA_21'][i] and df['EMA_9'][i-1] >= df['EMA_21'][i-1]:
            signal = "SHORT"
        else:
            continue
            
        entry_price = df['close'][i]
        current_atr = df['ATR'][i]
        
        # Wider targets taake choti movement se trade na katay
        sl_distance = current_atr * 2.0
        tp_distance = current_atr * 4.0
        
        sl = entry_price - sl_distance if signal == "LONG" else entry_price + sl_distance
        tp = entry_price + tp_distance if signal == "LONG" else entry_price - tp_distance
        
        for j in range(i+1, min(i+21, len(df))):
            if (signal == "LONG" and df['low'][j] <= sl) or (signal == "SHORT" and df['high'][j] >= sl):
                trades.append("SL")
                break
            if (signal == "LONG" and df['high'][j] >= tp) or (signal == "SHORT" and df['low'][j] <= tp):
                trades.append("TP")
                break
                
    return trades

def generate_report():
    global REPORT
    df = fetch_data()
    if df is not None:
        results = run_backtest(df)
        tp = results.count("TP")
        sl = results.count("SL")
        total = len(results)
        win_rate = (tp / total * 100) if total > 0 else 0
        
        REPORT = f"""
        <h1>📊 Backtest Results (Wider Targets)</h1>
        <p><b>Win Rate:</b> {win_rate:.2f}%</p>
        <p><b>Total Trades:</b> {total}</p>
        <p>✅ <b>Take Profit (TP):</b> {tp}</p>
        <p>❌ <b>Stop Loss (SL):</b> {sl}</p>
        <p><i>Note: Ismein Risk-Reward 1:2 hai, toh kam win rate bhi profit dega.</i></p>
        """
    else:
        REPORT = "<h3>Error: API data fetch failed.</h3>"

@app.route('/')
def home():
    return REPORT

if __name__ == "__main__":
    threading.Thread(target=generate_report, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
    
