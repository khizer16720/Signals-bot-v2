import os
import requests
import pandas as pd
import pandas_ta as ta
import threading
from flask import Flask

app = Flask(__name__)
REPORT = "<h3>⏳ Filtered Backtest chal raha hai... 30-40 seconds wait karein.</h3>"

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "DOGEUSDT", "LINKUSDT"]

def fetch_data(symbol, candles=10000):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit={candles}"
    try:
        res = requests.get(url, timeout=15).json()
        df = pd.DataFrame(res, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'ct', 'qav', 'nt', 'tb', 'tq', 'ignore'])
        for col in ['open', 'high', 'low', 'close']: df[col] = df[col].astype(float)
        return df
    except: return None

def run_backtest_for_coin(df):
    # Indicators
    df['EMA_9'] = ta.ema(df['close'], length=9)
    df['EMA_21'] = ta.ema(df['close'], length=21)
    df['EMA_200'] = ta.ema(df['close'], length=200) # Trend Filter
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    trade_amount = 1000
    pnl = 0
    
    for i in range(201, len(df) - 1):
        signal = None
        
        # TREND FILTER: Agar price EMA 200 ke upar hai toh sirf LONG, niche hai toh sirf SHORT
        if df['close'][i] > df['EMA_200'][i]:
            if df['EMA_9'][i] > df['EMA_21'][i] and df['EMA_9'][i-1] <= df['EMA_21'][i-1]:
                signal = "LONG"
        elif df['close'][i] < df['EMA_200'][i]:
            if df['EMA_9'][i] < df['EMA_21'][i] and df['EMA_9'][i-1] >= df['EMA_21'][i-1]:
                signal = "SHORT"
        
        if not signal: continue
            
        sl_risk = trade_amount * 0.02
        tp_gain = trade_amount * 0.04
        entry = df['close'][i]
        
        sl = entry - (df['ATR'][i] * 2.0) if signal == "LONG" else entry + (df['ATR'][i] * 2.0)
        tp = entry + (df['ATR'][i] * 4.0) if signal == "LONG" else entry - (df['ATR'][i] * 4.0)
        
        for j in range(i+1, min(i+21, len(df))):
            if (signal == "LONG" and df['low'][j] <= sl) or (signal == "SHORT" and df['high'][j] >= sl):
                pnl -= sl_risk; break
            if (signal == "LONG" and df['high'][j] >= tp) or (signal == "SHORT" and df['low'][j] <= tp):
                pnl += tp_gain; break
    return pnl

def generate_report():
    global REPORT
    results = []
    total_net_pnl = 0
    for coin in COINS:
        df = fetch_data(coin)
        if df is not None:
            pnl = run_backtest_for_coin(df)
            total_net_pnl += pnl
            results.append(f"<tr><td>{coin}</td><td>${pnl:.2f}</td></tr>")
    
    REPORT = f"""
    <h1>📊 Filtered Strategy Report (EMA 200 Trend Filter)</h1>
    <table border="1">
        <tr><th>Coin</th><th>Profit/Loss ($1000 trade)</th></tr>
        {"".join(results)}
    </table>
    <h2>Total Net Profit: ${total_net_pnl:.2f}</h2>
    """

@app.route('/')
def home():
    return REPORT

if __name__ == "__main__":
    threading.Thread(target=generate_report, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
    
