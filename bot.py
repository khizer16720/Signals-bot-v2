import pandas as pd
import pandas_ta as ta
from sklearn.ensemble import RandomForestClassifier
import requests

def get_ml_data(symbol):
    # Data fetch karna
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit=5000"
    res = requests.get(url).json()
    df = pd.DataFrame(res, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'ct', 'qav', 'nt', 'tb', 'tq', 'ignore'])
    for col in ['open', 'high', 'low', 'close']: df[col] = df[col].astype(float)
    
    # Features banana
    df['RSI'] = ta.rsi(df['close'], length=14)
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    df['Return'] = df['close'].pct_change()
    df.dropna(inplace=True)
    
    # Target: Agar agli 5 candles mein price 0.5% upar jaye toh 1, warna 0
    df['Target'] = (df['close'].shift(-5) > df['close'] * 1.005).astype(int)
    return df

def train_and_predict(df):
    features = ['RSI', 'ATR', 'Return']
    X = df[features]
    y = df['Target']
    
    # Model Train karna
    model = RandomForestClassifier(n_estimators=100)
    model.fit(X[:-5], y[:-5]) # Future data chhupa kar train kiya
    
    # Prediction
    prediction = model.predict(X.tail(1))
    return prediction[0]

# Usage
# df = get_ml_data("BTCUSDT")
# signal = train_and_predict(df)
# if signal == 1: print("ML Signal: BUY")
