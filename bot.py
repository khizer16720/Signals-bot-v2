import os
import time
import threading
import requests
from flask import Flask

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ---------- RENDER LOGS PAR DEBUG PRINT ----------
print("🔍 ===== DEBUG ENVIRONMENT VARIABLES =====")
print(f"TOKEN exists: {bool(TELEGRAM_BOT_TOKEN)}")
print(f"TOKEN length: {len(TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else 0}")
print(f"CHAT_ID exists: {bool(TELEGRAM_CHAT_ID)}")
print(f"CHAT_ID value: {TELEGRAM_CHAT_ID}")
print("=========================================")

def send_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ CRITICAL: Token or Chat ID is missing in environment!")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    params = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        r = requests.get(url, timeout=10)
        print(f"Status Code: {r.status_code}")
        if r.status_code == 200:
            print("✅ Message sent!")
        else:
            print(f"❌ Error: {r.text}")
    except Exception as e:
        print(f"❌ Exception: {e}")

app = Flask(__name__)

@app.route('/')
def home():
    return "Debug Running"

if __name__ == '__main__':
    # Startup par message bhejein
    send_message("🚀 Debug bot started! Check Render logs.")
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
