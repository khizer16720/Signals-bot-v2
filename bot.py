import os
import requests
import pandas as pd
import pandas_ta as ta
import threading
from flask import Flask

app = Flask(__name__)
REPORT = "<h3>⏳ Backtest abhi chal raha hai... 10 second ruk kar refresh karein.</h3>"

def fetch_data(symbol="ETHUSDT", interval="5m", candles=5000):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={candles}"
    try:
        res = requests.get(url, timeout=15).json()
        df = pd.DataFrame(res, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'ct', 'qav', 'nt', 'tb', 'tq', 'ignore'])
        for col in ['open', 'high', 'low', 'close']: df[col] = df[col].astype(float)
        return df
    except: return None

def run_backtest(df):
    df['EMA_9'] = ta.ema(df['close'], length=9)
    df['EMA_21'] = ta.ema(df['close'], length=21)
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    trade_amount = 1000  # Har trade $1000 ki
    net_pnl = 0
    tp_hits = 0
    sl_hits = 0
    
    for i in range(22, len(df) - 1):
        if df['EMA_9'][i] > df['EMA_21'][i] and df['EMA_9'][i-1] <= df['EMA_21'][i-1]:
            signal = "LONG"
        elif df['EMA_9'][i] < df['EMA_21'][i] and df['EMA_9'][i-1] >= df['EMA_21'][i-1]:
            signal = "SHORT"
        else: continue
            
        sl_risk = trade_amount * 0.02  # $20 loss
        tp_gain = trade_amount * 0.04  # $40 profit
        
        entry = df['close'][i]
        sl = entry - (df['ATR'][i] * 2.0) if signal == "LONG" else entry + (df['ATR'][i] * 2.0)
        tp = entry + (df['ATR'][i] * 4.0) if signal == "LONG" else entry - (df['ATR'][i] * 4.0)
        
        for j in range(i+1, min(i+21, len(df))):
            if (signal == "LONG" and df['low'][j] <= sl) or (signal == "SHORT" and df['high'][j] >= sl):
                net_pnl -= sl_risk
                sl_hits += 1
                break
            if (signal == "LONG" and df['high'][j] >= tp) or (signal == "SHORT" and df['low'][j] <= tp):
                net_pnl += tp_gain
                tp_hits += 1
                break
    return tp_hits, sl_hits, net_pnl

def generate_report():
    global REPORT
    df = fetch_data()
    if df is not None:
        tp, sl, pnl = run_backtest(df)
        REPORT = f"""
        <h1>📊 ETHUSDT Performance Report</h1>
        <p><b>Investment Per Trade:</b> $1000</p>
        <p>✅ Total TP Hits: {tp}</p>
        <p>❌ Total SL Hits: {sl}</p>
        <h2 style="color: {'green' if pnl >= 0 else 'red'};">
            Net Profit/Loss: ${pnl:.2f}
        </h2>
        """

@app.route('/')
def home():
    return REPORT

if __name__ == "__main__":
    threading.Thread(target=generate_report, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
    
