import os
import requests
import pandas as pd
import pandas_ta as ta
import threading
from flask import Flask

app = Flask(__name__)
REPORT = "<h3>⏳ Scalping Backtest (High Precision) in progress...</h3>"

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
    # Indicators
    df['EMA_200'] = ta.ema(df['close'], length=200)
    df['RSI'] = ta.rsi(df['close'], length=14)
    bb = ta.bbands(df['close'], length=20, std=2)
    df['BBL'] = bb['BBL_20_2.0']
    df['BBU'] = bb['BBU_20_2.0']
    
    pnl = 0
    trade_amt = 1000
    
    for i in range(200, len(df) - 5):
        # Entry Condition: Strong Trend + Over-extended (Bollinger) + RSI Momentum
        long_cond = (df['close'][i] > df['EMA_200'][i]) and (df['close'][i] <= df['BBL'][i]) and (df['RSI'][i] < 40)
        short_cond = (df['close'][i] < df['EMA_200'][i]) and (df['close'][i] >= df['BBU'][i]) and (df['RSI'][i] > 60)
        
        if long_cond or short_cond:
            entry = df['close'][i]
            # Scalping target: 0.5% profit, 0.25% stop loss (2:1 RR)
            tp = entry * 1.005 if long_cond else entry * 0.995
            sl = entry * 0.9975 if long_cond else entry * 1.0025
            
            # Check next 5 candles for outcome
            for j in range(i+1, i+6):
                if (long_cond and df['high'][j] >= tp) or (short_cond and df['low'][j] <= tp):
                    pnl += 5; break # $5 profit (0.5%)
                if (long_cond and df['low'][j] <= sl) or (short_cond and df['high'][j] >= sl):
                    pnl -= 2.5; break # $2.5 loss (0.25%)
    return pnl

def generate_report():
    global REPORT
    results = []
    total_net_pnl = 0
    for coin in COINS:
        df = fetch_data(coin)
        if df is not None:
            pnl = run_scalping_backtest(df)
            total_net_pnl += pnl
            results.append(f"<tr><td>{coin}</td><td>${pnl:.2f}</td></tr>")
    
    REPORT = f"""
    <h1>🚀 Scalping Strategy (High Precision)</h1>
    <table border="1">
        <tr><th>Coin</th><th>P/L ($1000 trade)</th></tr>
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
    
