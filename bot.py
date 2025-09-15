import requests
import datetime
import pytz
import time
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, CallbackContext

# ======================
# API KEYS
# ======================
TELEGRAM_BOT_TOKEN = "7516351236:AAHye1Y2LAp12saImyZp5kcbsm91D2SK_pM"
TELEGRAM_CHAT_ID = "5969642968"
TWELVEDATA_API_KEY = "5be1b12e0de6475a850cc5caeea9ac72"

# Telegram bot init
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Timezone
PKT_TZ = pytz.timezone("Asia/Karachi")

# ======================
# Data Fetch Functions
# ======================
def get_xauusd_data(interval="15min", outputsize=30):
    url = f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval={interval}&outputsize={outputsize}&apikey={TWELVEDATA_API_KEY}"
    r = requests.get(url).json()
    if "values" in r:
        return r["values"]
    return []

def get_btcusd_data(interval="15m", limit=30):
    url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={interval}&limit={limit}"
    r = requests.get(url).json()
    candles = []
    for c in r:
        candles.append({
            "datetime": datetime.datetime.fromtimestamp(c[0]/1000).strftime('%Y-%m-%d %H:%M:%S'),
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4])
        })
    return candles

# ======================
# Candle Pattern Detector
# ======================
def detect_candle_pattern(candle, prev_candle):
    o, h, l, c = float(candle["open"]), float(candle["high"]), float(candle["low"]), float(candle["close"])
    po, ph, pl, pc = float(prev_candle["open"]), float(prev_candle["high"]), float(prev_candle["low"]), float(prev_candle["close"])
    body = abs(c - o)
    wick_up = h - max(o, c)
    wick_down = min(o, c) - l

    # Pin Bar
    if wick_down > body * 2 and body < (h - l) * 0.3:
        return "Bullish Pin Bar"
    if wick_up > body * 2 and body < (h - l) * 0.3:
        return "Bearish Pin Bar"

    # Engulfing
    if c > o and po > pc and c > po and o < pc:
        return "Bullish Engulfing"
    if c < o and po < pc and c < po and o > pc:
        return "Bearish Engulfing"

    # Doji
    if body <= (h - l) * 0.1:
        return "Doji"

    return None

# ======================
# Analysis Function
# ======================
def analyze_market():
    xau_data_15m = get_xauusd_data("15min")
    if not xau_data_15m:
        return "⚠ XAUUSD data fetch failed."
    last_xau, prev_xau = xau_data_15m[0], xau_data_15m[1]
    xau_pattern = detect_candle_pattern(last_xau, prev_xau)
    xau_price = last_xau["close"]

    btc_data_15m = get_btcusd_data("15m")
    if not btc_data_15m:
        return "⚠ BTCUSD data fetch failed."
    last_btc, prev_btc = btc_data_15m[-1], btc_data_15m[-2]
    btc_pattern = detect_candle_pattern(last_btc, prev_btc)
    btc_price = last_btc["close"]

    msg = f"📊 Daily Analysis Update\n\n"
    msg += f"🟡 XAUUSD (Gold)\nPrice: ${xau_price}\nPattern: {xau_pattern if xau_pattern else 'No clear signal'}\nSL=20 | TP=80\n\n"
    msg += f"₿ BTCUSD (Bitcoin)\nPrice: ${btc_price}\nPattern: {btc_pattern if btc_pattern else 'No clear signal'}\nSL=300-400 | TP=1200-1600\n\n"
    msg += "💥 Liquidity Zones:\n- XAUUSD: 3620 & 3670\n- BTCUSD: 115k & 118k\n\n"
    msg += "📌 Plan:\n- Wait 15m/1h confirmation.\n- Focus London & NY session.\n"
    return msg

# ======================
# Telegram Handlers
# ======================
def start(update: Update, context: CallbackContext):
    update.message.reply_text("👋 Commands: /xau /btc /analysis")

def xau(update: Update, context: CallbackContext):
    data = get_xauusd_data("15min")
    if not data:
        update.message.reply_text("⚠ XAUUSD data fetch failed.")
        return
    last, prev = data[0], data[1]
    pattern = detect_candle_pattern(last, prev)
    msg = f"🟡 XAUUSD\nPrice: {last['close']}\nPattern: {pattern if pattern else 'No signal'}\nSL=20 | TP=80"
    update.message.reply_text(msg)

def btc(update: Update, context: CallbackContext):
    data = get_btcusd_data("15m")
    if not data:
        update.message.reply_text("⚠ BTCUSD data fetch failed.")
        return
    last, prev = data[-1], data[-2]
    pattern = detect_candle_pattern(last, prev)
    msg = f"₿ BTCUSD\nPrice: {last['close']}\nPattern: {pattern if pattern else 'No signal'}\nSL=300-400 | TP=1200-1600"
    update.message.reply_text(msg)

def analysis(update: Update, context: CallbackContext):
    update.message.reply_text(analyze_market())

# ======================
# Scheduler
# ======================
def schedule_jobs():
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=analyze_market()),
                      "cron", hour=12, minute=0, timezone=PKT_TZ)
    scheduler.add_job(lambda: bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=analyze_market()),
                      "cron", hour=17, minute=0, timezone=PKT_TZ)
    scheduler.start()

# ======================
# Live Price Monitor
# ======================
XAU_KEY_SUPPORTS = [3620, 3600]
XAU_KEY_RESISTANCES = [3650, 3670]
BTC_KEY_SUPPORTS = [115000]
BTC_KEY_RESISTANCES = [118000]

def live_price_monitor():
    while True:
        try:
            xau_data = get_xauusd_data("1min", outputsize=5)
            if xau_data:
                price = float(xau_data[0]["close"])
                if any(price <= s for s in XAU_KEY_SUPPORTS):
                    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"🚨 XAUUSD Support Break! Price={price}")
                if any(price >= r for r in XAU_KEY_RESISTANCES):
                    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"🚨 XAUUSD Resistance Break! Price={price}")

            btc_data = get_btcusd_data("1m", limit=5)
            if btc_data:
                price = float(btc_data[-1]["close"])
                if any(price <= s for s in BTC_KEY_SUPPORTS):
                    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"🚨 BTCUSD Support Break! Price={price}")
                if any(price >= r for r in BTC_KEY_RESISTANCES):
                    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"🚨 BTCUSD Resistance Break! Price={price}")
        except Exception as e:
            print("Error in live monitor:", e)
        time.sleep(60)

# ======================
# Main
# ======================
if __name__ == "__main__":
    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("xau", xau))
    dp.add_handler(CommandHandler("btc", btc))
    dp.add_handler(CommandHandler("analysis", analysis))

    schedule_jobs()
    threading.Thread(target=live_price_monitor, daemon=True).start()

    updater.start_polling()
    updater.idle()
