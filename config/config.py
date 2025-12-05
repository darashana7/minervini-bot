"""
Configuration settings for Mark Minervini Stock Alert System
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8550797252:AAG_P9X-9RxOQyIz-N2LAHiGJhnBKzAF5W8")
# Support multiple chat IDs (comma-separated in env, or list here)
TELEGRAM_CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS", "718039423,651048573,1417534705").split(",")
TELEGRAM_CHAT_ID = TELEGRAM_CHAT_IDS[0]  # Primary for backward compatibility

# Stock Market Configuration
EXCHANGE_SUFFIX = ".NS"  # NSE suffix for Yahoo Finance
MARKET_OPEN_TIME = "09:15"
MARKET_CLOSE_TIME = "15:30"

# Minervini Trend Template Parameters
MA_PERIODS = {
    "short": 50,
    "medium": 150,
    "long": 200
}

# Screening Thresholds
MIN_PERCENT_ABOVE_52W_LOW = 30  # Stock should be at least 30% above 52-week low
MAX_PERCENT_FROM_52W_HIGH = 25  # Stock should be within 25% of 52-week high
MIN_200_SMA_UPTREND_DAYS = 22   # 200-day SMA should be trending up for ~1 month

# Scan Schedule
SCAN_TIMES = [
    "09:30",  # First scan after market opens
    "10:30",
    "11:30",
    "12:30",
    "13:30",
    "14:30",
    "15:45",  # End of day scan after market close
]

# Data Settings
HISTORICAL_DATA_PERIOD = "1y"  # 1 year of data for calculations
CACHE_DURATION_HOURS = 1       # Cache stock data for 1 hour

# Alert Settings
ALERT_COOLDOWN_HOURS = 24      # Don't re-alert for same stock within 24 hours

# File Paths
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
STOCK_LIST_FILE = os.path.join(DATA_DIR, "nse_stocks.csv")
ALERT_HISTORY_FILE = os.path.join(DATA_DIR, "alert_history.json")

# Create directories if they don't exist
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
