def run_backtest(df):
    trades = []
    
    # Columns safe check ke sath map karna
    ema21 = df['EMA_21']
    rsi = df['RSI_14']
    macd = df['MACD_12_26_9']
    macd_sig = df['MACDs_12_26_9']
    vol = df['volume']
    vol_sma = df['SMA_20_Volume']
    
    # Bollinger Bands column names flexibility check (Error Fix)
    bbl_name = 'BBL_20_2.0' if 'BBL_20_2.0' in df.columns else 'BBL_20_2'
    bbu_name = 'BBU_20_2.0' if 'BBU_20_2.0' in df.columns else 'BBU_20_2'
    
    bb_lower = df[bbl_name]
    bb_upper = df[bbu_name]
    
    # ATR column name flexibility check
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
            entry_price = df.iloc[i+1]['open']
            atr = atr_col[i]
            vol_ratio = vol[i] / vol_sma[i]
            
            m_sl, m_tp1, m_tp2 = (0.45, 0.75, 1.5) if vol_ratio >= 2.0 else (0.3, 0.5, 1.0)
            
            if signal == "LONG":
                sl, tp1, tp2 = entry_price - (atr * m_sl), entry_price + (atr * m_tp1), entry_price + (atr * m_tp2)
            else:
                sl, tp1, tp2 = entry_price + (atr * m_sl), entry_price - (atr * m_tp1), entry_price - (atr * m_tp2)
                
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
    
