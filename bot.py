import os
import requests
import pandas as pd
import pandas_ta as ta
import threading
from flask import Flask
from sklearn.ensemble import RandomForestClassifier

app = Flask(__name__)
REPORT = "<h3>⏳ ML Bot Training on data...</h3>"
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

def get_ml_data(symbol):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit=2000"
    res = requests.get(url).json()
    df = pd.DataFrame(res, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'ct', 'qav', 'nt', 'tb', 'tq', 'ignore'])
    for col in ['open', 'high', 'low', 'close']: df[col] = df[col].astype(float)
    df['RSI'] = ta.rsi(df['close'], length=14)
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    df['Return'] = df['close'].pct_change()
    df.dropna(inplace=True)
    # Target: Agli 5 candles mein 0.3% growth
    df['Target'] = (df['close'].shift(-5) > df['close'] * 1.003).astype(int)
    return df

def train_and_signal(df):
    features = ['RSI', 'ATR', 'Return']
    X = df[features].iloc[:-5]
    y = df['Target'].iloc[:-5]
    model = RandomForestClassifier(n_estimators=50)
    model.fit(X, y)
    return model.predict(df[features].tail(1))[0]

def generate_report():
    global REPORT
    results = []
    for coin in COINS:
        df = get_ml_data(coin)
        signal = train_and_signal(df)
        status = "🟢 BUY" if signal == 1 else "🔴 WAIT/SELL"
        results.append(f"<tr><td>{coin}</td><td>{status}</td></tr>")
    
    REPORT = f"<h1>🤖 ML Scalping Signals</h1><table border='1'><tr><th>Coin</th><th>Signal</th></tr>{''.join(results)}</table>"

@app.route('/')
def home(): return REPORT

if __name__ == "__main__":
    threading.Thread(target=generate_report, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
    
