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
# FEATURES LIST (shared by live signal + backtest)
# ============================================================
FEATURES = ['RSI', 'ATR', 'Return', 'EMA_diff', 'VWAP_diff']


# ============================================================
# HELPER: Indicators (1H ke liye — EMA 21/55 + VWAP added)
# ============================================================

def add_indicators(df, lookahead=3, threshold=0.01):
    """
    EMA 21/55 + RSI + ATR + Rolling VWAP + Target label.
    lookahead : aage kitni candles check karni hain
    threshold : kitni % growth target hai (0.01 = 1%)
    """
    df = df.copy()

    # RSI & ATR
    df['RSI']    = ta.rsi(df['close'], length=14)
    df['ATR']    = ta.atr(df['high'], df['low'], df['close'], length=14)
    df['Return'] = df['close'].pct_change()

    # EMA 21 & 55 — normalized difference
    df['EMA21']    = ta.ema(df['close'], length=21)
    df['EMA55']    = ta.ema(df['close'], length=55)
    df['EMA_diff'] = (df['EMA21'] - df['EMA55']) / df['close']
    # Positive = bullish trend, Negative = bearish trend

    # Rolling VWAP (24 periods for 1H ≈ daily VWAP)
    df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
    df['VWAP']      = ((df['typical_price'] * df['volume']).rolling(24).sum()
                       / df['volume'].rolling(24).sum())
    df['VWAP_diff'] = (df['close'] - df['VWAP']) / df['close']
    # Positive = price above VWAP (bullish), Negative = below (bearish)

    # Target: next `lookahead` candles mein `threshold` growth hogi?
    df['Target'] = (
        df['close'].shift(-lookahead) > df['close'] * (1 + threshold)
    ).astype(int)

    df = df.dropna(subset=['RSI', 'ATR', 'Return', 'EMA21', 'EMA55', 'VWAP']).reset_index(drop=True)
    return df


# ============================================================
# LIVE SIGNAL — 1H interval
# ============================================================

def get_ml_data(symbol):
    url = (
        f"https://api.binance.com/api/v3/klines"
        f"?symbol={symbol}&interval=1h&limit=500"   # 1H, 500 candles ≈ 20 days
    )
    res = requests.get(url).json()
    df = pd.DataFrame(res, columns=[
        'time', 'open', 'high', 'low', 'close', 'volume',
        'ct', 'qav', 'nt', 'tb', 'tq', 'ignore'
    ])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)

    # 1H ke liye: lookahead=3 candles (3 hrs), target=1%
    return add_indicators(df, lookahead=3, threshold=0.01)


def train_and_signal(df):
    X = df[FEATURES].iloc[:-3]   # last 3 rows reserved (lookahead)
    y = df['Target'].iloc[:-3]
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X, y)
    return model.predict(df[FEATURES].tail(1))[0]


def generate_report():
    global REPORT
    results = []
    for coin in COINS:
        try:
            df     = get_ml_data(coin)
            signal = train_and_signal(df)
            status = "🟢 BUY" if signal == 1 else "🔴 WAIT/SELL"
        except Exception as e:
            status = f"⚠️ Error: {e}"
        results.append(f"<tr><td>{coin}</td><td>{status}</td></tr>")

    REPORT = (
        "<h1>🤖 ML Signals — 1H Chart</h1>"
        "<p><b>Model:</b> EMA 21/55 + RSI + ATR + VWAP &nbsp;|&nbsp; "
        "<b>Lookahead:</b> 3 candles (3 hrs) &nbsp;|&nbsp; "
        "<b>Target:</b> +1%</p>"
        f"<table border='1'><tr><th>Coin</th><th>Signal</th></tr>"
        f"{''.join(results)}</table>"
    )


@app.route('/')
def home():
    return (
        REPORT +
        "<hr>"
        "<p>Backtest karne ke liye: "
        "<a href='/backtest'>/backtest</a> "
        "(params: ?symbols=BTCUSDT,ETHUSDT&interval=1h&candles=1000)</p>"
    )


# ============================================================
# WALK-FORWARD BACKTEST
# ============================================================

DEFAULT_BACKTEST_COINS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT",
    "BNBUSDT", "DOGEUSDT", "XRPUSDT"
]

BACKTEST_STATE = {}
BACKTEST_LOCK  = threading.Lock()


def fetch_full_klines(symbol, interval="1h", total=1000):
    """Binance se paged fetch — 1000 candles per request limit handle karta hai."""
    cols = ['time', 'open', 'high', 'low', 'close', 'volume',
            'ct', 'qav', 'nt', 'tb', 'tq', 'ignore']
    all_rows = []
    end_time = None

    while len(all_rows) < total:
        url = (
            f"https://api.binance.com/api/v3/klines"
            f"?symbol={symbol}&interval={interval}&limit=1000"
        )
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
    df = (df.drop_duplicates(subset='time')
            .sort_values('time')
            .reset_index(drop=True))
    return df.tail(total).reset_index(drop=True)


def get_interval_params(interval):
    """
    Interval ke hisaab se automatically sahi parameters set ho jaate hain.
    Backtest URL mein koi bhi interval pass karo — sab handle hoga.
    """
    if interval in ('1h', '2h'):
        return dict(lookahead=3,  threshold=0.01,  min_train=200, retrain_every=10,  fee_pct=0.001)
    elif interval == '4h':
        return dict(lookahead=3,  threshold=0.015, min_train=150, retrain_every=8,   fee_pct=0.001)
    elif interval in ('15m', '30m'):
        return dict(lookahead=5,  threshold=0.005, min_train=300, retrain_every=15,  fee_pct=0.001)
    else:  # 5m, 3m, 1m
        return dict(lookahead=5,  threshold=0.003, min_train=400, retrain_every=20,  fee_pct=0.0008)


def walk_forward_backtest(df, lookahead=3, threshold=0.01,
                           min_train=200, retrain_every=10, fee_pct=0.001):
    n     = len(df)
    model = None
    rows  = []

    for i in range(min_train, n - lookahead):
        # Retrain karo har `retrain_every` steps py
        if model is None or (i - min_train) % retrain_every == 0:
            train    = df.iloc[:i]
            X_train  = train[FEATURES].iloc[:-lookahead]
            y_train  = train['Target'].iloc[:-lookahead]
            if y_train.nunique() < 2:
                continue
            model = RandomForestClassifier(n_estimators=100, random_state=42)
            model.fit(X_train, y_train)

        x_now        = df[FEATURES].iloc[[i]]
        pred         = int(model.predict(x_now)[0])
        entry        = df['close'].iloc[i]
        future       = df['close'].iloc[i + lookahead]
        actual_return = (future - entry) / entry
        actual_hit   = int(actual_return > threshold)

        rows.append({
            "idx": i,
            "pred": pred,
            "actual_hit": actual_hit,
            "actual_return": actual_return
        })

    return pd.DataFrame(rows)


def build_results_html(symbol, interval, candles, results, fee_pct, lookahead, threshold):
    if results.empty:
        return f"<h2>{symbol} ({interval})</h2><p>Not enough data.</p>"

    accuracy  = (results['pred'] == results['actual_hit']).mean() * 100
    base_rate = results['actual_hit'].mean() * 100
    trades    = results[results['pred'] == 1].copy()

    html  = f"<h2>{symbol} — {interval} — {candles} candles</h2>"
    html += (
        f"<p>Features: EMA 21/55 + RSI + ATR + VWAP &nbsp;|&nbsp; "
        f"Lookahead: {lookahead} candles &nbsp;|&nbsp; "
        f"Target: +{threshold*100:.1f}% &nbsp;|&nbsp; Fee: {fee_pct*100:.2f}%</p>"
    )
    html += "<table border='1' cellpadding='6'>"
    html += f"<tr><td>Overall accuracy</td><td>{accuracy:.1f}%</td></tr>"
    html += f"<tr><td>Natural 'hit' base rate</td><td>{base_rate:.1f}%</td></tr>"
    html += f"<tr><td>Candles evaluated</td><td>{len(results)}</td></tr>"
    html += f"<tr><td>BUY signals fired</td><td>{len(trades)} ({len(trades)/len(results)*100:.1f}%)</td></tr>"

    if trades.empty:
        html += "</table><p>Model ne koi BUY signal nahi diya is period mein.</p>"
        return html

    precision = trades['actual_hit'].mean() * 100
    trades    = trades.copy()
    trades['pnl'] = trades['actual_return'] - fee_pct
    win_rate      = (trades['pnl'] > 0).mean() * 100
    equity        = (1 + trades['pnl']).cumprod()
    total_return  = (equity.iloc[-1] - 1) * 100
    running_max   = equity.cummax()
    max_dd        = ((equity - running_max) / running_max).min() * 100
    gross_win     = trades.loc[trades['pnl'] > 0, 'pnl'].sum()
    gross_loss    = -trades.loc[trades['pnl'] <= 0, 'pnl'].sum()
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

    html += f"<tr><td>BUY precision</td><td>{precision:.1f}%</td></tr>"
    html += f"<tr><td>Win rate (after fees)</td><td>{win_rate:.1f}%</td></tr>"
    html += f"<tr><td>Compounded return</td><td>{total_return:.2f}%</td></tr>"
    html += f"<tr><td>Max drawdown</td><td>{max_dd:.2f}%</td></tr>"
    html += f"<tr><td>Profit factor</td><td>{profit_factor:.2f}</td></tr>"
    html += "</table>"

    if precision <= base_rate + 2:
        html += (
            "<p>⚠ BUY precision base rate ke qareeb hai — "
            "model koi real edge nahi de raha.</p>"
        )
    else:
        html += (
            f"<p>✅ BUY precision ({precision:.1f}%) base rate ({base_rate:.1f}%) se "
            f"{precision - base_rate:.1f} points zyada hai. "
            "Profit factor &gt; 1.3 ho to real money try karo.</p>"
        )

    return html


def run_multi_backtest_job(key, symbols, interval, candles):
    state  = BACKTEST_STATE[key]
    params = get_interval_params(interval)   # auto params based on interval

    for symbol in symbols:
        state["progress"][symbol] = "running"
        try:
            raw     = fetch_full_klines(symbol, interval, candles)
            df      = add_indicators(raw,
                                     lookahead=params['lookahead'],
                                     threshold=params['threshold'])
            results = walk_forward_backtest(df, **params)
            state["results"][symbol] = build_results_html(
                symbol, interval, candles, results,
                fee_pct=params['fee_pct'],
                lookahead=params['lookahead'],
                threshold=params['threshold']
            )
            state["progress"][symbol] = "done"
        except Exception as e:
            state["results"][symbol] = f"<h2>{symbol}</h2><p>Error: {e}</p>"
            state["progress"][symbol] = "error"

    state["status"] = "done"


@app.route('/backtest')
def backtest_route():
    symbols_param = request.args.get('symbols')
    symbols  = (
        [s.strip().upper() for s in symbols_param.split(",")]
        if symbols_param else DEFAULT_BACKTEST_COINS
    )
    interval = request.args.get('interval', '1h')    # default: 1h
    candles  = int(request.args.get('candles', 1000)) # default: 1000
    key      = f"{'_'.join(symbols)}_{interval}_{candles}"

    with BACKTEST_LOCK:
        state = BACKTEST_STATE.get(key)
        if state is None:
            state = {
                "status":   "running",
                "progress": {s: "pending" for s in symbols},
                "results":  {}
            }
            BACKTEST_STATE[key] = state
            thread = threading.Thread(
                target=run_multi_backtest_job,
                args=(key, symbols, interval, candles),
                daemon=True
            )
            thread.start()

    icons        = {"pending": "⏳", "running": "🔄", "done": "✅", "error": "❌"}
    progress_html = "<ul>" + "".join(
        f"<li>{icons.get(state['progress'].get(s, 'pending'))} "
        f"{s}: {state['progress'].get(s, 'pending')}</li>"
        for s in symbols
    ) + "</ul>"

    if state["status"] == "running":
        return (
            f"<h2>Backtesting {len(symbols)} coins "
            f"({interval}, {candles} candles each)...</h2>"
            + progress_html +
            f"<p>Process ~{len(symbols)*2}–{len(symbols)*4} min le sakta hai. "
            "Page har 10 sec auto-refresh hoga.</p>"
            "<meta http-equiv='refresh' content='10'>"
        )

    combined  = progress_html + "<hr>"
    combined += "".join(state["results"].get(s, "") for s in symbols)
    combined += (
        "<hr><p><b>URL Examples:</b><br>"
        "<code>/backtest?symbols=BTCUSDT,ETHUSDT&interval=1h&candles=1000</code><br>"
        "<code>/backtest?interval=4h&candles=500</code><br>"
        "<code>/backtest?interval=5m&candles=2000</code></p>"
    )
    return combined


if __name__ == "__main__":
    threading.Thread(target=generate_report, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
    
