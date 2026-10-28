import pandas as pd
import numpy as np
from config import EMA_FAST, EMA_SLOW, RSI_PERIOD, ATR_PERIOD, ATR_STOP_MULTIPLIER

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=RSI_PERIOD, min_periods=RSI_PERIOD).mean()
    avg_loss = loss.rolling(window=RSI_PERIOD, min_periods=RSI_PERIOD).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = tr.rolling(window=ATR_PERIOD, min_periods=ATR_PERIOD).mean()

    return df


def analyze_setup(df: pd.DataFrame) -> dict:
    df = compute_indicators(df)
    if len(df) < EMA_SLOW + 5:
        return {"valid": False, "reason": "Insufficient historical data"}

    row = df.iloc[-1]
    close = float(row["close"])
    ema_f = float(row["ema_fast"])
    ema_s = float(row["ema_slow"])
    rsi = float(row["rsi"])
    atr = float(row["atr"])
    timestamp = row["time"]

    if pd.isna(rsi) or pd.isna(atr) or pd.isna(ema_f) or pd.isna(ema_s):
        return {"valid": False, "reason": "Indicator calculation incomplete"}

    direction = None
    reasons = []

    if ema_f > ema_s and close > ema_f and 50 <= rsi <= 70:
        direction = "BUY"
        reasons.append(f"EMA{EMA_FAST} ({ema_f:.5f}) above EMA{EMA_SLOW} ({ema_s:.5f})")
        reasons.append(f"Close ({close:.5f}) above EMA{EMA_FAST}")
        reasons.append(f"RSI {rsi:.1f} inside bullish momentum zone (50–70)")
    elif ema_f < ema_s and close < ema_f and 30 <= rsi <= 50:
        direction = "SELL"
        reasons.append(f"EMA{EMA_FAST} ({ema_f:.5f}) below EMA{EMA_SLOW} ({ema_s:.5f})")
        reasons.append(f"Close ({close:.5f}) below EMA{EMA_FAST}")
        reasons.append(f"RSI {rsi:.1f} inside bearish momentum zone (30–50)")
    else:
        if ema_f > ema_s:
            reasons.append("EMA trend is bullish but conditions not aligned")
        else:
            reasons.append("EMA trend is bearish but conditions not aligned")
        if rsi > 70:
            reasons.append(f"RSI {rsi:.1f} is overbought (above 70)")
        elif rsi < 30:
            reasons.append(f"RSI {rsi:.1f} is oversold (below 30)")
        else:
            reasons.append(f"RSI {rsi:.1f} outside required momentum zone")
        return {
            "valid": False,
            "reason": "; ".join(reasons),
            "timestamp": timestamp,
            "rsi": rsi,
            "atr": atr,
        }

    stop_distance = atr * ATR_STOP_MULTIPLIER
    entry = close
    if direction == "BUY":
        sl = entry - stop_distance
        tp1 = entry + stop_distance
        tp2 = entry + stop_distance * 2
    else:
        sl = entry + stop_distance
        tp1 = entry - stop_distance
        tp2 = entry - stop_distance * 2

    return {
        "valid": True,
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "ema_fast": ema_f,
        "ema_slow": ema_s,
        "rsi": rsi,
        "atr": atr,
        "timestamp": timestamp,
        "reasons": reasons,
    }
