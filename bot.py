import os
import time
import threading
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import ccxt
from telegram import Bot
from flask import Flask

# ------------------ CONFIG (Render se aayenge) ------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

# ------------------ INITIALIZE ------------------
telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN)
exchange = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_API_SECRET,
    'rateLimit': 1200,
    'enableRateLimit': True,
})

def calculate_indicators(df):
    df['EMA9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['EMA21'] = df['close'].ewm(span=21, adjust=False).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    df['BB_mid'] = df['close'].rolling(20).mean()
    df['BB_upper'] = df['BB_mid'] + 2 * df['close'].rolling(20).std()
    df['BB_lower'] = df['BB_mid'] - 2 * df['close'].rolling(20).std()
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['TR'] = np.maximum(df['high'] - df['low'], 
                          np.maximum(abs(df['high'] - df['close'].shift()), 
                                     abs(df['low'] - df['close'].shift())))
    df['ATR'] = df['TR'].rolling(14).mean()
    df['Avg_Vol'] = df['volume'].rolling(20).mean()
    return df

def get_top_50_coins():
    try:
        tickers = exchange.fetch_tickers()
        usdt_pairs = [s for s in tickers if s.endswith('/USDT')]
        sorted_pairs = sorted(usdt_pairs, key=lambda s: tickers[s]['quoteVolume'] if tickers[s]['quoteVolume'] else 0, reverse=True)
        return sorted_pairs[:50]
    except Exception as e:
        print(f"Error fetching coins: {e}")
        return []

def check_signal(symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, '5m', limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        df = calculate_indicators(df)
        close = df['close'].iloc[-1]
        prev_rsi = df['RSI'].iloc[-2]
        rsi = df['RSI'].iloc[-1]
        vol = df['volume'].iloc[-1]
        avg_vol = df['Avg_Vol'].iloc[-1]
        atr = df['ATR'].iloc[-1]
        vol_ratio = vol / avg_vol if avg_vol > 0 else 1
        mult = 1.5 if vol_ratio > 2.0 else 1.0
        
        # BUY
        if (close > df['EMA21'].iloc[-1]) and (rsi < 35) and (rsi > prev_rsi) and (close <= df['BB_lower'].iloc[-1] * 1.001) and (df['MACD'].iloc[-1] > df['Signal'].iloc[-1]) and (vol > avg_vol):
            entry = close
            sl = round(entry - (atr * 0.3 * mult), 4)
            tp1 = round(entry + (atr * 0.5 * mult), 4)
            tp2 = round(entry + (atr * 1.0 * mult), 4)
            gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            expiry = (datetime.now() + timedelta(minutes=5)).strftime("%H:%M:%S")
            return (f"🟢 BUY: {symbol}\nEntry: ${entry:.4f}\nTP1: ${tp1:.4f} | TP2: ${tp2:.4f}\nSL: ${sl:.4f}\n⏰ {gen_time}\n⏳ Valid till: {expiry}")
        
        # SELL
        elif (close < df['EMA21'].iloc[-1]) and (rsi > 65) and (rsi < prev_rsi) and (close >= df['BB_upper'].iloc[-1] * 0.999) and (df['MACD'].iloc[-1] < df['Signal'].iloc[-1]) and (vol > avg_vol):
            entry = close
            sl = round(entry + (atr * 0.3 * mult), 4)
            tp1 = round(entry - (atr * 0.5 * mult), 4)
            tp2 = round(entry - (atr * 1.0 * mult), 4)
            gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            expiry = (datetime.now() + timedelta(minutes=5)).strftime("%H:%M:%S")
            return (f"🔴 SELL: {symbol}\nEntry: ${entry:.4f}\nTP1: ${tp1:.4f} | TP2: ${tp2:.4f}\nSL: ${sl:.4f}\n⏰ {gen_time}\n⏳ Valid till: {expiry}")
        return None
    except Exception as e:
        print(f"Error checking {symbol}: {e}")
        return None

# ------------------ MAIN BOT LOOP (Heartbeat Added!) ------------------
def run_bot():
    print("🚀 Bot Started with Binance API! (Dynamic TP/SL)")
    last_heartbeat = time.time()  # Initialize heartbeat timer
    
    while True:
        try:
            coins = get_top_50_coins()
            if not coins:
                time.sleep(60)
                continue
            
            for symbol in coins:
                signal = check_signal(symbol)
                if signal:
                    telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=signal)
                    print(f"Signal sent for {symbol}")
                    time.sleep(2)
            
            # ---------- HEARTBEAT LOGIC (Check every 60 minutes) ----------
            current_time = time.time()
            if current_time - last_heartbeat >= 3600:  # 3600 seconds = 1 hour
                hb_msg = "💓 Heartbeat: Bot is alive and scanning Top 50 coins. No signals triggered yet, waiting for market conditions."
                try:
                    telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=hb_msg)
                    print(f"Heartbeat sent at {datetime.now()}")
                except Exception as e:
                    print(f"Heartbeat failed: {e}")
                last_heartbeat = current_time  # Reset timer
            
            time.sleep(60)
            
        except Exception as e:
            print(f"Main loop error: {e}")
            time.sleep(60)

# ------------------ FLASK SERVER (FOR RENDER) ------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot running with Binance API + Heartbeat!"

if __name__ == '__main__':
    thread = threading.Thread(target=run_bot)
    thread.daemon = True
    thread.start()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
