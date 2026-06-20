import os
import requests
import pandas as pd
import pandas_ta as ta
import threading
from flask import Flask

app = Flask(__name__)
REPORT = "<h3>⏳ Optimizing Strategy (Slope Filter)...</h3>"

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

def fetch_data(symbol, candles=10000):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit={candles}"
    try:
        res = requests.get(url, timeout=15).json()
        df = pd.DataFrame(res, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'ct', 'qav', 'nt', 'tb', 'tq', 'ignore'])
        for col in ['open', 'high', 'low', 'close']: df[col] = df[col].astype(float)
        return df
    except: return None

def run_backtest(df):
    df['EMA9'] = ta.ema(df['close'], length=9)
    df['EMA21'] = ta.ema(df['close'], length=21)
    df['RSI'] = ta.rsi(df['close'], length=14)
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    stats = {"LONG_TP": 0, "LONG_SL": 0, "SHORT_TP": 0, "SHORT_SL": 0, "PNL": 0}
    
    for i in range(22, len(df) - 1):
        # Slope check: EMA9 ka trend up ya down hona chahiye
        ema_slope = df['EMA9'][i] - df['EMA9'][i-2]
        
        # RSI aur Slope ka confluence
        if not (35 < df['RSI'][i] < 65): continue
        
        signal = None
        if df['EMA9'][i] > df['EMA21'][i] and ema_slope > 0: signal = "LONG"
        elif df['EMA9'][i] < df['EMA21'][i] and ema_slope < 0: signal = "SHORT"
        
        if signal:
            entry = df['close'][i]
            # Wider SL (2.5 ATR) to avoid noise, Wider TP (5 ATR) for better RRR
            sl = entry - (df['ATR'][i] * 2.5) if signal == "LONG" else entry + (df['ATR'][i] * 2.5)
            tp = entry + (df['ATR'][i] * 5.0) if signal == "LONG" else entry - (df['ATR'][i] * 5.0)
            
            for j in range(i+1, min(i+25, len(df))):
                if (signal == "LONG" and df['low'][j] <= sl) or (signal == "SHORT" and df['high'][j] >= sl):
                    stats[f"{signal}_SL"] += 1; stats["PNL"] -= 20; break
                if (signal == "LONG" and df['high'][j] >= tp) or (signal == "SHORT" and df['low'][j] <= tp):
                    stats[f"{signal}_TP"] += 1; stats["PNL"] += 40; break
    return stats

def generate_report():
    global REPORT
    res_list = []
    for coin in COINS:
        df = fetch_data(coin)
        if df is not None:
            s = run_backtest(df)
            res_list.append(f"<tr><td>{coin}</td><td>{s['LONG_TP']}/{s['LONG_SL']}</td><td>{s['SHORT_TP']}/{s['SHORT_SL']}</td><td>${s['PNL']}</td></tr>")
    
    REPORT = f"""
    <h1>📊 Optimized Slope-Filter Report</h1>
    <table border="1">
        <tr><th>Coin</th><th>Long (TP/SL)</th><th>Short (TP/SL)</th><th>Total PNL ($)</th></tr>
        {"".join(res_list)}
    </table>
    """

@app.route('/')
def home():
    return REPORT

if __name__ == "__main__":
    threading.Thread(target=generate_report, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
    
