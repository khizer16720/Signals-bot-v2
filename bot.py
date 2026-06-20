import os
import time
import threading
import requests
import pandas as pd
import pandas_ta as ta
from flask import Flask, request
from sklearn.ensemble import RandomForestClassifier

app = Flask(__name__)
REPORT = "<h3>⏳ ML Bot Training on data...</h3>"
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# ============================================================
# ORIGINAL LIVE SIGNAL CODE - unchanged
# ============================================================

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
def home():
    return REPORT + "<hr><p>Backtest karne ke liye: <a href='/backtest'>/backtest</a> (params: ?symbol=BTCUSDT&interval=5m&candles=3000)</p>"


# ============================================================
# NEW: WALK-FORWARD BACKTEST - results shown on a webpage
# ============================================================

DEFAULT_BACKTEST_COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT", "XRPUSDT"]

BACKTEST_STATE = {}  # key -> {"status": ..., "progress": {symbol: state}, "results": {symbol: html}}
BACKTEST_LOCK = threading.Lock()


def fetch_full_klines(symbol, interval="5m", total=3000):
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
            break
        all_rows = res + all_rows
        end_time = res[0][0] - 1
        if len(res) < 1000:
            break
        time.sleep(0.3)

    df = pd.DataFrame(all_rows, columns=cols)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    df = df.drop_duplicates(subset='time').sort_values('time').reset_index(drop=True)
    return df.tail(total).reset_index(drop=True)


def add_features(df, lookahead=5, threshold=0.003):
    df = df.copy()
    df['RSI'] = ta.rsi(df['close'], length=14)
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    df['Return'] = df['close'].pct_change()
    df['Target'] = (df['close'].shift(-lookahead) > df['close'] * (1 + threshold)).astype(int)
    df = df.dropna(subset=['RSI', 'ATR', 'Return']).reset_index(drop=True)
    return df


def walk_forward_backtest(df, lookahead=5, threshold=0.003,
                           min_train=400, retrain_every=20, fee_pct=0.0008):
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
                continue
            model = RandomForestClassifier(n_estimators=50, random_state=42)
            model.fit(X_train, y_train)

        x_now = df[feats].iloc[[i]]
        pred = int(model.predict(x_now)[0])

        entry = df['close'].iloc[i]
        future = df['close'].iloc[i + lookahead]
        actual_return = (future - entry) / entry
        actual_hit = int(actual_return > threshold)

        rows.append({"idx": i, "pred": pred, "actual_hit": actual_hit, "actual_return": actual_return})

    return pd.DataFrame(rows)


def build_results_html(symbol, interval, candles, results, fee_pct=0.0008):
    if results.empty:
        return f"<h2>{symbol} ({interval})</h2><p>No results - not enough data.</p>"

    accuracy = (results['pred'] == results['actual_hit']).mean() * 100
    base_rate = results['actual_hit'].mean() * 100
    trades = results[results['pred'] == 1].copy()

    html = f"<h2>{symbol} — {interval} — {candles} candles</h2>"
    html += "<table border='1' cellpadding='6'>"
    html += f"<tr><td>Overall accuracy</td><td>{accuracy:.1f}%</td></tr>"
    html += f"<tr><td>Natural 'hit' base rate</td><td>{base_rate:.1f}%</td></tr>"
    html += f"<tr><td>Candles evaluated</td><td>{len(results)}</td></tr>"
    html += f"<tr><td>BUY signals fired</td><td>{len(trades)} ({len(trades)/len(results)*100:.1f}%)</td></tr>"

    if trades.empty:
        html += "</table><p>Model never signaled BUY in this period.</p>"
        return html

    precision = trades['actual_hit'].mean() * 100
    trades['pnl'] = trades['actual_return'] - fee_pct
    win_rate = (trades['pnl'] > 0).mean() * 100
    equity = (1 + trades['pnl']).cumprod()
    total_return = (equity.iloc[-1] - 1) * 100
    running_max = equity.cummax()
    max_dd = ((equity - running_max) / running_max).min() * 100
    gross_win = trades.loc[trades['pnl'] > 0, 'pnl'].sum()
    gross_loss = -trades.loc[trades['pnl'] <= 0, 'pnl'].sum()
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

    html += f"<tr><td>BUY precision</td><td>{precision:.1f}%</td></tr>"
    html += f"<tr><td>Trade win rate (after fees)</td><td>{win_rate:.1f}%</td></tr>"
    html += f"<tr><td>Compounded return</td><td>{total_return:.2f}%</td></tr>"
    html += f"<tr><td>Max drawdown</td><td>{max_dd:.2f}%</td></tr>"
    html += f"<tr><td>Profit factor</td><td>{profit_factor:.2f}</td></tr>"
    html += "</table>"

    if precision <= base_rate + 2:
        html += "<p>⚠ BUY precision is close to (or below) the natural base rate — model is NOT adding real edge over the market's natural behavior.</p>"
    else:
        html += f"<p>✓ BUY precision ({precision:.1f}%) beats base rate ({base_rate:.1f}%) by {precision-base_rate:.1f} points. Still check profit factor &gt; ~1.3-1.5 before trusting it with real money.</p>"

    return html


def run_multi_backtest_job(key, symbols, interval, candles):
    state = BACKTEST_STATE[key]
    for symbol in symbols:
        state["progress"][symbol] = "running"
        try:
            raw = fetch_full_klines(symbol, interval, candles)
            df = add_features(raw)
            results = walk_forward_backtest(df)
            state["results"][symbol] = build_results_html(symbol, interval, candles, results)
            state["progress"][symbol] = "done"
        except Exception as e:
            state["results"][symbol] = f"<h2>{symbol}</h2><p>Error: {e}</p>"
            state["progress"][symbol] = "error"
    state["status"] = "done"


@app.route('/backtest')
def backtest_route():
    symbols_param = request.args.get('symbols')
    symbols = [s.strip().upper() for s in symbols_param.split(",")] if symbols_param else DEFAULT_BACKTEST_COINS
    interval = request.args.get('interval', '5m')
    candles = int(request.args.get('candles', 2000))
    key = f"{'_'.join(symbols)}_{interval}_{candles}"

    with BACKTEST_LOCK:
        state = BACKTEST_STATE.get(key)
        if state is None:
            state = {"status": "running", "progress": {s: "pending" for s in symbols}, "results": {}}
            BACKTEST_STATE[key] = state
            thread = threading.Thread(target=run_multi_backtest_job, args=(key, symbols, interval, candles), daemon=True)
            thread.start()

    icons = {"pending": "⏳", "running": "🔄", "done": "✅", "error": "❌"}
    progress_html = "<ul>" + "".join(
        f"<li>{icons.get(state['progress'].get(s, 'pending'))} {s}: {state['progress'].get(s, 'pending')}</li>"
        for s in symbols
    ) + "</ul>"

    if state["status"] == "running":
        return (
            f"<h2>Backtesting {len(symbols)} coins ({interval}, {candles} candles each)...</h2>"
            + progress_html +
            "<p>Coins ek-ek karke chalte hain (Render free tier ki limited CPU ki wajah se). "
            f"Pura process ~{len(symbols)*1}-{len(symbols)*3} min le sakta hai. Page har 10 sec auto-refresh hoga.</p>"
            "<meta http-equiv='refresh' content='10'>"
        )

    combined = progress_html + "<hr>" + "".join(state["results"].get(s, "") for s in symbols)
    combined += "<hr><p>Sirf specific coins test karne ho: <code>/backtest?symbols=BTCUSDT,ETHUSDT</code> | 3m timeframe: <code>/backtest?interval=3m</code></p>"
    return combined


if __name__ == "__main__":
    threading.Thread(target=generate_report, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
    
