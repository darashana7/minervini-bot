"""
Simple Polling Bot for LOCAL TESTING
Run this to test /start and other commands locally
"""
import logging
import os
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

sys.path.append(os.path.dirname(__file__))

# Configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8557128929:AAFrPNOsb-T_ygpaqu2MI0DbuZYEA2JT1rg")

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message"""
    welcome = """
🎯 <b>Minervini Stock Screener Bot</b>

Welcome! I can scan NSE stocks using Mark Minervini's Trend Template.

<b>📊 Quick Commands:</b>
/scan - Quick scan (top 50 stocks)
/check SYMBOL - Check specific stock
/autodaily [on/off] - Enable daily scans ⏰

<b>🤖 AI Analysis:</b>
/ai SYMBOL - Get AI entry/stop-loss levels

<b>🔔 Price Alerts:</b>
/alert SYMBOL &gt; PRICE - Alert when above
/alert SYMBOL &lt; PRICE - Alert when below
/alerts - View your active alerts
/delalert ID - Delete an alert

<b>🔄 Full Scans (with progress):</b>
/fullscan - Nifty 500 scan (~500 stocks)
/scanall - ALL NSE stocks (~2000 stocks)
/progress - Check scan progress
/stop - Stop current scan
/resume - Resume stopped scan

<b>📋 Results:</b>
/list - Show latest scan results
/list all - Summary of all scan types
/listquick, /listfull, /listall - Shortcuts

<b>ℹ️ Info:</b>
/nse - Show all available stocks
/help - Show this message

✨ <i>Price alerts checked every 5 minutes!</i>
    """
    await update.message.reply_text(welcome.strip(), parse_mode='HTML')
    logger.info(f"✅ /start command received from user {update.effective_user.id}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help"""
    await start(update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages"""
    text = update.message.text
    logger.info(f"Received message: {text}")
    await update.message.reply_text(
        "💡 Send a stock symbol to check it, or use:\n"
        "/start - Welcome message\n"
        "/scan - Quick scan\n"
        "/help - All commands"
    )


def main():
    """Run bot in polling mode for local testing"""
    print("🚀 Starting Minervini Bot in POLLING MODE (for local testing)...")
    print(f"📡 Bot Token: {BOT_TOKEN[:20]}...")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Bot ready! Send /start in Telegram to test.")
    print("Press Ctrl+C to stop.\n")
    
    # Run in polling mode
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
