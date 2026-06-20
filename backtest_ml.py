"""
Walk-forward backtest for the ML scalping bot (bot.py logic).
================================================================

Reuses the SAME feature engineering and model as bot.py:
  - RSI(14), ATR(14), Return (pct_change)
  - RandomForestClassifier(n_estimators=50)
  - Target: did price rise >0.3% within the next 5 candles?

Why "walk-forward" and not just train-once like bot.py currently does:
  bot.py trains on the ENTIRE dataset and then predicts on the most
  recent row from that SAME dataset. That tells you nothing about
  whether the model can predict the FUTURE - it's basically grading
  its own homework. A real backtest must only let the model see data
  that would have been available at that point in time, then check
  what actually happened next. This script does that: it slides
  forward candle by candle (or in steps), retrains using only past
  data, predicts, then checks the real outcome.

Usage:
  pip install -r requirements.txt
  python backtest_ml.py BTCUSDT 5m 5000
  python backtest_ml.py ETHUSDT 3m 5000

Needs internet access (calls Binance public API) - run this on
Termux, your local machine, or anywhere with a connection.
"""

import sys
import time
import requests
import pandas as pd
import pandas_ta as ta
from sklearn.ensemble import RandomForestClassifier


# ---------------------------- Data fetching ----------------------------

def fetch_full_klines(symbol, interval="5m", total=5000):
    """Binance caps each request at 1000 candles, so we page backwards
    using endTime until we have `total` candles."""
    cols = ['time', 'open', 'high', 'low', 'close', 'volume',
            'ct', 'qav', 'nt', 'tb', 'tq', 'ignore']
    all_rows = []
    end_time = None

    while len(all_rows) < total:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=1000"
        if end_time:
            url += f"&endTime={end_time}"
        res = requests.get(url, timeout=15).json()
        if not isinstance(res, list) or not res:
            print(f"Binance response issue: {res}")
            break
        all_rows = res + all_rows
        end_time = res[0][0] - 1
        if len(res) < 1000:
            break
        time.sleep(0.3)  # be nice to the API

    df = pd.DataFrame(all_rows, columns=cols)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    df = df.drop_duplicates(subset='time').sort_values('time').reset_index(drop=True)
    return df.tail(total).reset_index(drop=True)


# ---------------------------- Features (same as bot.py) ----------------------------

def add_features(df, lookahead=5, threshold=0.003):
    df = df.copy()
    df['RSI'] = ta.rsi(df['close'], length=14)
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    df['Return'] = df['close'].pct_change()
    df['Target'] = (df['close'].shift(-lookahead) > df['close'] * (1 + threshold)).astype(int)
    df = df.dropna(subset=['RSI', 'ATR', 'Return']).reset_index(drop=True)
    return df


# ---------------------------- Walk-forward backtest ----------------------------

def walk_forward_backtest(df, lookahead=5, threshold=0.003,
                           min_train=400, retrain_every=10, fee_pct=0.0008):
    """
    min_train      : how many candles needed before the first model is trained
    retrain_every   : retrain the model every N candles (1 = every candle,
                      slower but most accurate; higher = faster, slightly stale model)
    fee_pct         : round-trip fee + slippage estimate
    """
    feats = ['RSI', 'ATR', 'Return']
    n = len(df)
    model = None
    rows = []

    for i in range(min_train, n - lookahead):
        if model is None or (i - min_train) % retrain_every == 0:
            train = df.iloc[:i]
            X_train = train[feats].iloc[:-lookahead]
            y_train = train['Target'].iloc[:-lookahead]
            if y_train.nunique() < 2:
                continue  # can't train on a single class
            model = RandomForestClassifier(n_estimators=50, random_state=42)
            model.fit(X_train, y_train)

        x_now = df[feats].iloc[[i]]
        pred = int(model.predict(x_now)[0])

        entry = df['close'].iloc[i]
        future = df['close'].iloc[i + lookahead]
        actual_return = (future - entry) / entry
        actual_hit = int(actual_return > threshold)

        rows.append({
            "idx": i,
            "pred": pred,
            "actual_hit": actual_hit,
            "actual_return": actual_return,
        })

    return pd.DataFrame(rows)


def summarize(results, fee_pct=0.0008):
    if results.empty:
        print("No results produced - check data length / min_train setting.")
        return

    accuracy = (results['pred'] == results['actual_hit']).mean() * 100
    base_rate = results['actual_hit'].mean() * 100  # how often "hit" happens naturally

    trades = results[results['pred'] == 1].copy()
    print("=" * 55)
    print("CLASSIFICATION QUALITY (does the model predict better than chance?)")
    print("=" * 55)
    print(f"Overall accuracy        : {accuracy:.1f}%")
    print(f"Natural 'hit' base rate : {base_rate:.1f}%  (predicting nothing would still 'hit' this often)")
    print(f"Total candles evaluated : {len(results)}")
    print(f"BUY signals fired       : {len(trades)} ({len(trades)/len(results)*100:.1f}% of candles)")

    if trades.empty:
        print("\nModel never signaled BUY in this period - nothing to simulate.")
        return

    precision = trades['actual_hit'].mean() * 100  # of the BUYs, how many actually hit
    trades['pnl'] = trades['actual_return'] - fee_pct
    win_rate = (trades['pnl'] > 0).mean() * 100
    equity = (1 + trades['pnl']).cumprod()
    total_return = (equity.iloc[-1] - 1) * 100
    running_max = equity.cummax()
    max_dd = ((equity - running_max) / running_max).min() * 100
    gross_win = trades.loc[trades['pnl'] > 0, 'pnl'].sum()
    gross_loss = -trades.loc[trades['pnl'] <= 0, 'pnl'].sum()
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

    print("\n" + "=" * 55)
    print("TRADING SIMULATION (only on candles where model said BUY)")
    print("=" * 55)
    print(f"BUY precision           : {precision:.1f}%  (of BUY signals, % that actually hit +0.3%)")
    print(f"Trade win rate          : {win_rate:.1f}%  (after fees)")
    print(f"Compounded return       : {total_return:.2f}%")
    print(f"Max drawdown            : {max_dd:.2f}%")
    print(f"Profit factor           : {profit_factor:.2f}")
    print("=" * 55)

    if precision <= base_rate + 2:
        print("\n⚠ BUY precision is close to (or below) the natural base rate.")
        print("  This means the model is NOT adding real predictive edge over")
        print("  just guessing based on how often the market moves that way anyway.")
    else:
        print(f"\n✓ Model's BUY precision ({precision:.1f}%) beats the base rate")
        print(f"  ({base_rate:.1f}%) by {precision-base_rate:.1f} points - that's a real signal,")
        print("  but still confirm profit factor > ~1.3-1.5 before trusting it with real money.")


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    interval = sys.argv[2] if len(sys.argv) > 2 else "5m"
    total = int(sys.argv[3]) if len(sys.argv) > 3 else 5000

    print(f"Fetching {total} {interval} candles for {symbol}...")
    raw = fetch_full_klines(symbol, interval, total)
    print(f"Got {len(raw)} candles ({raw['time'].iloc[0]} to {raw['time'].iloc[-1]})")

    df = add_features(raw)
    print(f"Running walk-forward backtest on {len(df)} candles (this may take a minute)...\n")

    results = walk_forward_backtest(df)
    summarize(results)

    results.to_csv(f"/tmp/backtest_{symbol}_{interval}.csv", index=False)
    print(f"\nFull results saved to /tmp/backtest_{symbol}_{interval}.csv")
  
