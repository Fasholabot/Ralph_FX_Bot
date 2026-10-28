import logging
from datetime import datetime, timezone
import aiohttp
import pandas as pd
from config import TWELVE_DATA_API_KEY, to_td_symbol

logger = logging.getLogger(__name__)

BASE_URL = "https://api.twelvedata.com/time_series"

class MarketData:
    def __init__(self, api_key: str = TWELVE_DATA_API_KEY):
        self.api_key = api_key
        self._last_success: datetime | None = None

    async def get_rates(self, pair: str, interval: str, outputsize: int = 300) -> pd.DataFrame | None:
        symbol = to_td_symbol(pair)
        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": str(outputsize),
            "apikey": self.api_key,
            "format": "JSON",
            "order": "ASC",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(BASE_URL, params=params, timeout=15) as resp:
                    data = await resp.json()

            if "values" not in data:
                logger.error(f"TwelveData error for {symbol}: {data}")
                return None

            df = pd.DataFrame(data["values"])
            df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
            for col in ["open", "high", "low", "close"]:
                df[col] = df[col].astype(float)
            df = df.rename(columns={"datetime": "time"})
            df = df[["time", "open", "high", "low", "close"]].reset_index(drop=True)
            self._last_success = datetime.now(timezone.utc)
            return df
        except Exception as e:
            logger.error(f"get_rates exception for {symbol}: {e}")
            return None

    def is_data_fresh(self, df: pd.DataFrame, max_age_minutes: int = 120) -> bool:
        if df is None or df.empty:
            return False
        last_time = df["time"].iloc[-1]
        now = datetime.now(timezone.utc)
        age = (now - last_time).total_seconds() / 60
        return age < max_age_minutes

    def last_success(self) -> datetime | None:
        return self._last_success
