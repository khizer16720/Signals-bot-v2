import os
import time
import requests
import pandas as pd
import pandas_ta as ta
import threading
from flask import Flask

app = Flask(__name__)

# Global variable jo shuru mein yeh message dikhayegi
BACKTEST_REPORT = "<h3>⏳ Backtest background mein chal raha hai... Please 15-20 seconds baad page refresh (reload) karein.</h3>"

def fetch_historical_data(symbol="ETHUSDT", interval="5m", total_candles=17500):
    url = "https://api.binance.com/api/v3/klines"
    all_candles = []
    end_time = None
    
    # 17,500 candles fetch karne ke liye loop (Binance max 1000 aik baar mein deta hai)
    while len(all_candles) < total_candles:
        limit = min(1000, total_candles - len(all_candles))
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if end_time:
            params["endTime"] = end_time
            
        try:
            res = requests.get(url, params=params, timeout=15).json()
            if not res or len(res) == 0:
                break
            all_candles = res + all_candles
            end_time = res[0][0] - 1
            time.sleep(0.1) # Rate limit se bachne ke liye chota pause
        except Exception as e:
            print(f"Data fetch error: {e}")
            break
        
    df = pd.DataFrame(all_candles, columns=[
        'time', 'open', 'high', 'low', 'close', 'volume', 
        'close_time', 'qav', 'num_trades', 'taker_base', 'taker_quote', 'ignore'
    ])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    return df

def apply_indicators(df):
    # Technical Indicators calculate karna
    df.ta.ema(length=9, append=True)
    df.ta.ema(length=21, append=True)
    df.ta.rsi(length=14, append=True)
    df.ta.bbands(length=20, std=2, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df['SMA_20_Volume'] = df['volume'].rolling(window=20).mean()
    df.ta.atr(length=14, append=True)
    return df

def run_backtest(df):
    trades = []
    
    # Columns safe check ke sath map karna
    ema21 = df['EMA_21']
    rsi = df['RSI_14']
    bb_lower = df['BBL_20_2.0']
    bb_upper = df['BBU_20_2.0']
    macd = df['MACD_12_26_9']
    macd_sig = df['MACDs_12_26_9']
    vol = df['volume']
    vol_sma = df['SMA_20_Volume']
    
    # ATR column name flexibilty check
    atr_name = 'ATRr_14' if 'ATRr_14' in df.columns else 'ATR_14'
    atr_col = df[atr_name]
    
    # Poore data par loops chalana signals dhoondne ke liye
    for i in range(21, len(df) - 1):
        curr_close = df.iloc[i]['close']
        
        # BUY / LONG Conditions
        buy_cond = (
            curr_close > ema21[i] and 
            rsi[i] < 35 and (rsi[i] > rsi[i-1]) and 
            curr_close <= (bb_lower[i] * 1.001) and 
            macd[i] > macd_sig[i] and 
            vol[i] > vol_sma[i]
        )
        
        # SELL / SHORT Conditions
        sell_cond = (
            curr_close < ema21[i] and 
            rsi[i] > 65 and (rsi[i] < rsi[i-1]) and 
            curr_close >= (bb_upper[i] * 0.999) and 
            macd[i] < macd_sig[i] and 
            vol[i] > vol_sma[i]
        )
        
        signal = "LONG" if buy_cond else "SHORT" if sell_cond else None
        
        if signal:
            entry_price = df.iloc[i+1]['open'] # Entry agli candle ke open par
            atr = atr_col[i]
            vol_ratio = vol[i] / vol_sma[i]
            
            # Volume ke mutabik dynamic multipliers
            m_sl, m_tp1, m_tp2 = (0.45, 0.75, 1.5) if vol_ratio >= 2.0 else (0.3, 0.5, 1.0)
            
            if signal == "LONG":
                sl, tp1, tp2 = entry_price - (atr * m_sl), entry_price + (atr * m_tp1), entry_price + (atr * m_tp2)
            else:
                sl, tp1, tp2 = entry_price + (atr * m_sl), entry_price - (atr * m_tp1), entry_price - (atr * m_tp2)
                
            # Agli 5 candles (5-min time valid) tak outcome track karna
            trade_result = "EXPIRED"
            for j in range(i+1, min(i+6, len(df))):
                future_high = df.iloc[j]['high']
                future_low = df.iloc[j]['low']
                
                if signal == "LONG":
                    if future_low <= sl: trade_result = "HIT_SL"; break
                    elif future_high >= tp2: trade_result = "HIT_TP2"; break
                    elif future_high >= tp1: trade_result = "HIT_TP1"
                else:
                    if future_high >= sl: trade_result = "HIT_SL"; break
                    elif future_low <= tp2: trade_result = "HIT_TP2"; break
                    elif future_low <= tp1: trade_result = "HIT_TP1"

            trades.append({"result": trade_result})
            
    return trades

def generate_report_thread():
    global BACKTEST_REPORT
    print("Background backtest started for 2 months...")
    
    try:
        # 17500 candles = Approx 60 Days (2 Mahine) on 5m chart
        df = fetch_historical_data("ETHUSDT", "5m", 17500)
        df = apply_indicators(df)
        trades = run_backtest(df)
        
        total_trades = len(trades)
        if total_trades == 0:
            BACKTEST_REPORT = "<h3 style='color: white;'>Grand Report: Pichle 2 mahine mein koi signal nahi mila. Conditions bohot strict hain.</h3>"
            return
            
        sl_hits = sum(1 for t in trades if t['result'] == 'HIT_SL')
        tp1_hits = sum(1 for t in trades if t['result'] == 'HIT_TP1')
        tp2_hits = sum(1 for t in trades if t['result'] == 'HIT_TP2')
        expired = sum(1 for t in trades if t['result'] == 'EXPIRED')
        win_rate = ((tp1_hits + tp2_hits) / total_trades) * 100

        # HTML design update
        BACKTEST_REPORT = f"""
        <html>
        <head><title>Backtest Results</title></head>
        <body style="font-family: Arial, sans-serif; background-color: #121212; color: #ffffff; padding: 30px; line-height: 1.6;">
            <h2 style="color: #00e676; border-bottom: 2px solid #333; padding-bottom: 10px;">📊 Grand Strategy Backtest Report (ETH/USDT)</h2>
            <p style="font-size: 16px;"><b>Period:</b> Pichle 2 Mahine (~60 Days) | <b>Timeframe:</b> 5 Minutes (5m)</p>
            <hr style="border-color: #333; margin-y: 20px;">
            
            <div style="background-color: #1e1e1e; padding: 20px; border-radius: 8px; max-width: 500px;">
                <p style="font-size: 18px; margin-top: 0;"><b>Total Signals Generated:</b> <span style="color: #ffb300;">{total_trades}</span></p>
                <p style="color: #ff4d4d; font-size: 16px; margin: 8px 0;">❌ Stop Loss Hit: <b>{sl_hits}</b></p>
                <p style="color: #4da6ff; font-size: 16px; margin: 8px 0;">🎯 Target 1 Hit: <b>{tp1_hits}</b></p>
                <p style="color: #00e676; font-size: 16px; margin: 8px 0;">🔥 Target 2 Hit: <b>{tp2_hits}</b></p>
                <p style="color: #b3b3b3; font-size: 16px; margin: 8px 0;">⏰ Expired (5 Min Over): <b>{expired}</b></p>
            </div>
            
            <hr style="border-color: #333; margin-top: 20px;">
            <h2 style="color: #00e676; margin-top: 15px;">📈 Overall Win Rate (TP1 or TP2): {win_rate:.2f}%</h2>
            <p style="color: #888; font-size: 12px; margin-top: 25px;">Note: Yeh data cloud memory se instantly load hua hai.</p>
        </body>
        </html>
        """
        print("Background backtest completed successfully!")
    except Exception as e:
        BACKTEST_REPORT = f"<h3 style='color: red;'>Error during backtest calculation: {str(e)}</h3>"

@app.route('/')
def home():
    # Yeh user ko instantly report server memory se show karega bina timeout ke
    return BACKTEST_REPORT

if __name__ == "__main__":
    # Server chalte hi backtest background mein shuru ho jaye ga
    backtest_thread = threading.Thread(target=generate_report_thread)
    backtest_thread.daemon = True
    backtest_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
    
