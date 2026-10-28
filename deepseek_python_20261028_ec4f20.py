import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))
PORT = int(os.getenv("PORT", "8000"))

SUPPORTED_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    "USDCHF", "NZDUSD", "EURJPY", "GBPJPY", "XAUUSD"
]

# Twelve Data uses slash format for FX and XAU/USD
def to_td_symbol(pair: str) -> str:
    pair = pair.upper()
    if pair == "XAUUSD":
        return "XAU/USD"
    return f"{pair[:3]}/{pair[3:]}"

SUPPORTED_TIMEFRAMES = {
    "M15": "15min",
    "M30": "30min",
    "H1": "1h",
    "H4": "4h",
}

DEFAULT_TIMEFRAME = "H1"

EMA_FAST = 50
EMA_SLOW = 200
RSI_PERIOD = 14
ATR_PERIOD = 14
ATR_STOP_MULTIPLIER = 1.5

DISCLAIMER = (
    "⚠️ Disclaimer: This bot is for analysis only, not financial advice. "
    "Forex and gold trading involve substantial risk. Past performance does not guarantee future results."
)