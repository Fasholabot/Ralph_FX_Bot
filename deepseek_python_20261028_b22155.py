import logging
import os
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import (
    TELEGRAM_BOT_TOKEN, SUPPORTED_PAIRS, SUPPORTED_TIMEFRAMES,
    DEFAULT_TIMEFRAME, DISCLAIMER, PORT
)
from market_data import MarketData
from analysis import analyze_setup, compute_indicators
from risk_manager import calculate_position_size

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("RalphFX")

md = MarketData()

# ---------- Health server for Render / UptimeRobot ----------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"RalphFX is running")

    def log_message(self, *args, **kwargs):
        pass


def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info(f"Health server running on port {PORT}")
    server.serve_forever()


# ---------- Commands ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *RalphFX Intelligence*\n"
        "_Analyze smarter. Trade with a plan._\n\n"
        "I provide technical analysis for major forex pairs and gold.\n\n"
        "📊 *Commands*\n"
        "/analyze EURUSD [H1] – Full analysis\n"
        "/pairs – Supported instruments\n"
        "/setups – Scan for setups\n"
        "/timeframes – Available timeframes\n"
        "/trend EURUSD [H1] – Trend summary\n"
        "/indicators EURUSD [H1] – Indicators\n"
        "/risk – Risk management\n"
        "/status – Bot status\n"
        "/help – Help\n\n"
        "⚠️ *Analysis only* — I never place trades.\n\n"
        f"_{DISCLAIMER}_"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def analyze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /analyze EURUSD [H1]")
        return

    pair = context.args[0].upper().replace("/", "")
    tf = context.args[1].upper() if len(context.args) > 1 else DEFAULT_TIMEFRAME

    if pair not in SUPPORTED_PAIRS:
        await update.message.reply_text(f"❌ `{pair}` not supported. Use /pairs.")
        return
    if tf not in SUPPORTED_TIMEFRAMES:
        await update.message.reply_text(f"❌ Unsupported timeframe. Use one of: {', '.join(SUPPORTED_TIMEFRAMES)}")
        return

    msg = await update.message.reply_text("⏳ Fetching data and analyzing...")
    df = await md.get_rates(pair, SUPPORTED_TIMEFRAMES[tf], 300)

    if df is None or df.empty:
        await msg.edit_text("❌ Could not retrieve market data. Try again shortly.")
        return
    if not md.is_data_fresh(df, max_age_minutes=180):
        await msg.edit_text("⚠️ Market data appears stale (market may be closed). Try again later.")
        return

    result = analyze_setup(df)

    if not result["valid"]:
        ts = result.get("timestamp")
        ts_str = ts.strftime("%Y-%m-%d %H:%M UTC") if hasattr(ts, "strftime") else str(ts)
        await msg.edit_text(
            f"📊 *{pair} {tf}* — NO VALID SETUP\n\n"
            f"Last candle: {ts_str}\n"
            f"Reason: {result['reason']}",
            parse_mode="Markdown",
        )
        return

    arrow = "🟢" if result["direction"] == "BUY" else "🔴"
    text = (
        f"{arrow} *{result['direction']} SETUP* — {pair} {tf}\n"
        f"Last candle: {result['timestamp'].strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        f"*Theoretical reference levels*\n"
        f"Entry: `{result['entry']:.5f}`\n"
        f"Stop Loss: `{result['sl']:.5f}`\n"
        f"Target 1 (1R): `{result['tp1']:.5f}`\n"
        f"Target 2 (2R): `{result['tp2']:.5f}`\n\n"
        f"*Indicators*\n"
        f"EMA50: `{result['ema_fast']:.5f}`\n"
        f"EMA200: `{result['ema_slow']:.5f}`\n"
        f"RSI14: `{result['rsi']:.1f}`\n"
        f"ATR14: `{result['atr']:.5f}`\n\n"
        f"*Reasons*\n" + "\n".join(f"• {r}" for r in result["reasons"]) + "\n\n"
        f"_{DISCLAIMER}_"
    )
    await msg.edit_text(text, parse_mode="Markdown")


async def pairs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 *Supported Instruments*\n\n"
        + "\n".join(f"• {p}" for p in SUPPORTED_PAIRS)
        + "\n\n_All pairs available via Twelve Data free tier._"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def timeframes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "⏱ *Supported Timeframes*\n\n"
        + "\n".join(f"• `{k}`" for k in SUPPORTED_TIMEFRAMES)
        + "\n\nUsage: `/analyze EURUSD H1`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def trend_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /trend EURUSD [H1]")
        return
    pair = context.args[0].upper().replace("/", "")
    tf = context.args[1].upper() if len(context.args) > 1 else DEFAULT_TIMEFRAME

    if pair not in SUPPORTED_PAIRS or tf not in SUPPORTED_TIMEFRAMES:
        await update.message.reply_text("❌ Invalid pair or timeframe.")
        return

    df = await md.get_rates(pair, SUPPORTED_TIMEFRAMES[tf], 300)
    if df is None or df.empty:
        await update.message.reply_text("❌ Data unavailable.")
        return

    df = compute_indicators(df)
    row = df.iloc[-1]
    close, ema_f, ema_s = float(row["close"]), float(row["ema_fast"]), float(row["ema_slow"])

    if ema_f > ema_s and close > ema_f:
        trend = "🟢 BULLISH"
    elif ema_f < ema_s and close < ema_f:
        trend = "🔴 BEARISH"
    else:
        trend = "🟡 MIXED"

    text = (
        f"📈 *{pair} {tf} Trend*\n\n"
        f"Direction: {trend}\n"
        f"Close: `{close:.5f}`\n"
        f"EMA50: `{ema_f:.5f}`\n"
        f"EMA200: `{ema_s:.5f}`\n"
        f"Last candle: {row['time'].strftime('%Y-%m-%d %H:%M UTC')}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def indicators_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /indicators EURUSD [H1]")
        return
    pair = context.args[0].upper().replace("/", "")
    tf = context.args[1].upper() if len(context.args) > 1 else DEFAULT_TIMEFRAME

    if pair not in SUPPORTED_PAIRS or tf not in SUPPORTED_TIMEFRAMES:
        await update.message.reply_text("❌ Invalid pair or timeframe.")
        return

    df = await md.get_rates(pair, SUPPORTED_TIMEFRAMES[tf], 300)
    if df is None or df.empty:
        await update.message.reply_text("❌ Data unavailable.")
        return

    df = compute_indicators(df)
    row = df.iloc[-1]

    text = (
        f"📊 *{pair} {tf} Indicators*\n"
        f"Last candle: {row['time'].strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        f"EMA 50: `{row['ema_fast']:.5f}`\n"
        f"EMA 200: `{row['ema_slow']:.5f}`\n"
        f"RSI 14: `{row['rsi']:.1f}`\n"
        f"ATR 14: `{row['atr']:.5f}`\n\n"
        f"_EMA = trend direction. RSI = momentum (70+ overbought, 30- oversold). ATR = volatility._"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def risk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 4:
        await update.message.reply_text(
            "🛡 *Risk Management*\n\n"
            "Always use a stop-loss. Risk only what you can afford to lose.\n\n"
            "Calculator:\n"
            "`/risk <equity> <risk%> <entry> <stop>`\n"
            "Example: `/risk 1000 1 1.0850 1.0820`",
            parse_mode="Markdown",
        )
        return

    try:
        equity = float(args[0])
        risk_pct = float(args[1])
        entry = float(args[2])
        sl = float(args[3])
    except ValueError:
        await update.message.reply_text("❌ Please enter valid numbers.")
        return

    if risk_pct <= 0 or risk_pct > 10:
        await update.message.reply_text("❌ Risk % should be between 0 and 10.")
        return

    result = calculate_position_size(equity, risk_pct, entry, sl)
    if "error" in result:
        await update.message.reply_text(f"❌ {result['error']}")
        return

    await update.message.reply_text(
        f"🛡 *Position Size Estimate*\n\n"
        f"Risk amount: `${result['risk_amount']}`\n"
        f"Stop distance: `{result['sl_pips']}` pips\n"
        f"Approx. lot size: `{result['lots']}`\n\n"
        f"_{result['note']}_",
        parse_mode="Markdown",
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    df = await md.get_rates("EURUSD", "1h", 5)
    fresh = md.is_data_fresh(df, 180) if df is not None else False
    last = md.last_success()

    text = (
        f"🟢 *Bot Status*\n\n"
        f"Telegram: Running\n"
        f"Data API: {'✅ Reachable' if df is not None else '❌ Unreachable'}\n"
        f"Data Freshness: {'✅ Fresh' if fresh else '⚠️ Stale'}\n"
        f"Last successful fetch: {last.strftime('%Y-%m-%d %H:%M UTC') if last else 'N/A'}\n"
        f"Checked at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *RalphFX Help*\n\n"
        "*Commands*\n"
        "/analyze SYMBOL [TF] — e.g. /analyze EURUSD H1\n"
        "/pairs — Instruments\n"
        "/setups — Scan all pairs (H1)\n"
        "/timeframes — Timeframes\n"
        "/trend SYMBOL [TF] — Trend\n"
        "/indicators SYMBOL [TF] — Values\n"
        "/risk — Position sizing\n"
        "/status — Status\n\n"
        "*Timeframes*: M15, M30, H1, H4\n\n"
        "*Limitations*\n"
        "• Analysis only — no trade execution\n"
        "• Free data provider (Twelve Data) — minor price differences possible\n"
        "• Experimental strategy, not proven profitable\n\n"
        f"_{DISCLAIMER}_"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def setups_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Scanning supported instruments...")
    found = []
    for pair in SUPPORTED_PAIRS:
        df = await md.get_rates(pair, "1h", 300)
        if df is None or not md.is_data_fresh(df, 180):
            continue
        r = analyze_setup(df)
        if r["valid"]:
            found.append((pair, r))

    if not found:
        await msg.edit_text("🔍 No valid setups across supported instruments right now.")
        return

    lines = ["🔍 *Valid Setups (H1)*\n"]
    for sym, r in found:
        arrow = "🟢" if r["direction"] == "BUY" else "🔴"
        lines.append(f"{arrow} *{sym}* — {r['direction']}")
        lines.append(f"Entry: `{r['entry']:.5f}` | SL: `{r['sl']:.5f}`")
        lines.append("")
    lines.append(f"_{DISCLAIMER}_")
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")


# ---------- Entrypoint ----------
def main():
    if not TELEGRAM_BOT_TOKEN or not md.api_key:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN or TWELVE_DATA_API_KEY in environment.")

    threading.Thread(target=run_health_server, daemon=True).start()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analyze", analyze_cmd))
    app.add_handler(CommandHandler("pairs", pairs_cmd))
    app.add_handler(CommandHandler("setups", setups_cmd))
    app.add_handler(CommandHandler("timeframes", timeframes_cmd))
    app.add_handler(CommandHandler("trend", trend_cmd))
    app.add_handler(CommandHandler("indicators", indicators_cmd))
    app.add_handler(CommandHandler("risk", risk_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    logger.info("RalphFX Intelligence starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()