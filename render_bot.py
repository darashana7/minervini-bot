"""
Render-compatible Telegram Bot for Minervini Stock Screener
Uses Webhook mode + Flask for 24/7 uptime on Render free tier
Implements CHUNKED SCANNING with persistent storage for fullscan/scanall
"""
import logging
import json
import os
import sys
import time
from datetime import datetime, timedelta
from flask import Flask, request, Response
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio
from threading import Thread
import threading
import numpy as np

sys.path.append(os.path.dirname(__file__))
from src.minervini_screener import MinerviniScreener
from src.stock_list import get_nse_stock_list
from src.all_nse_stocks import get_all_nse_stocks, get_nse_stock_count

# Configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8557128929:AAFrPNOsb-T_ygpaqu2MI0DbuZYEA2JT1rg")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
PORT = int(os.environ.get("PORT", 10000))

# Scan settings - chunked to avoid timeouts
CHUNK_SIZE = 30  # Stocks per chunk (small to avoid timeout)
SCAN_INTERVAL_SECONDS = 5  # Wait between chunks

# Storage paths
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
SCAN_STATE_FILE = os.path.join(DATA_DIR, 'scan_state.json')
SCAN_RESULTS_FILE = os.path.join(DATA_DIR, 'scan_results.json')

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app for health checks
flask_app = Flask(__name__)

# Initialize screener
screener = MinerviniScreener()

# Telegram application
application = None

# Background scan lock
scan_lock = threading.Lock()
is_scanning = False

# Store the main event loop for thread-safe async calls
main_loop = None


# ============ JSON ENCODER FOR NUMPY TYPES ============

class NumpyEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles numpy types"""
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


# ============ STORAGE FUNCTIONS ============

def load_scan_state():
    """Load current scan state from file"""
    try:
        if os.path.exists(SCAN_STATE_FILE):
            with open(SCAN_STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading scan state: {e}")
    return None


def save_scan_state(state):
    """Save scan state to file"""
    try:
        with open(SCAN_STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2, cls=NumpyEncoder)
    except Exception as e:
        logger.error(f"Error saving scan state: {e}")


def clear_scan_state():
    """Clear scan state file"""
    try:
        if os.path.exists(SCAN_STATE_FILE):
            os.remove(SCAN_STATE_FILE)
    except Exception as e:
        logger.error(f"Error clearing scan state: {e}")


def load_scan_results():
    """Load scan results from file"""
    try:
        if os.path.exists(SCAN_RESULTS_FILE):
            with open(SCAN_RESULTS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading scan results: {e}")
    return {"stocks": [], "scan_type": None, "completed_at": None, "total_scanned": 0}


def save_scan_results(results):
    """Save scan results to file"""
    try:
        with open(SCAN_RESULTS_FILE, 'w') as f:
            json.dump(results, f, indent=2, cls=NumpyEncoder)
    except Exception as e:
        logger.error(f"Error saving scan results: {e}")


def add_to_scan_results(stock_data, scan_type):
    """Add a stock to the results file"""
    results = load_scan_results()
    
    # Check if this is a new scan type - reset if so
    if results.get("scan_type") != scan_type:
        results = {"stocks": [], "scan_type": scan_type, "completed_at": None, "total_scanned": 0}
    
    # Add stock if not already present
    existing_symbols = [s['symbol'] for s in results['stocks']]
    if stock_data['symbol'] not in existing_symbols:
        results['stocks'].append(stock_data)
    
    save_scan_results(results)
    return len(results['stocks'])


# ============ CHUNKED SCANNING ============

async def run_chunked_scan(chat_id, scan_type="fullscan"):
    """Run a scan in chunks with progress updates"""
    global is_scanning
    
    with scan_lock:
        if is_scanning:
            return False
        is_scanning = True
    
    try:
        # Determine stock list
        if scan_type == "scanall":
            all_stocks = get_all_nse_stocks()
            scan_name = "ALL NSE"
        else:
            all_stocks = get_nse_stock_list()
            scan_name = "Nifty 500"
        
        total_stocks = len(all_stocks)
        
        # Load or initialize state
        state = load_scan_state()
        
        if state and state.get('scan_type') == scan_type and state.get('offset', 0) < total_stocks:
            # Resume existing scan
            offset = state.get('offset', 0)
            logger.info(f"Resuming {scan_type} from offset {offset}")
        else:
            # Start new scan
            offset = 0
            # Clear previous results for this scan type
            save_scan_results({"stocks": [], "scan_type": scan_type, "completed_at": None, "total_scanned": 0})
            
            # Send start message
            await application.bot.send_message(
                chat_id=chat_id,
                text=f"🔍 <b>Starting {scan_name} Scan</b>\n\n"
                     f"📊 Total stocks: {total_stocks}\n"
                     f"⏱️ Processing in chunks of {CHUNK_SIZE}\n"
                     f"📝 Results saved automatically\n\n"
                     f"Use /progress to check status\n"
                     f"Use /stop to cancel",
                parse_mode='HTML'
            )
        
        found_count = len(load_scan_results().get('stocks', []))
        
        # Process chunks
        while offset < total_stocks:
            chunk = all_stocks[offset:offset + CHUNK_SIZE]
            chunk_num = (offset // CHUNK_SIZE) + 1
            total_chunks = (total_stocks + CHUNK_SIZE - 1) // CHUNK_SIZE
            
            # Save current state
            save_scan_state({
                'scan_type': scan_type,
                'offset': offset,
                'total': total_stocks,
                'started_at': state.get('started_at', datetime.now().isoformat()) if state else datetime.now().isoformat(),
                'chat_id': chat_id
            })
            
            # Scan this chunk
            try:
                results = screener.scan_stocks(chunk, min_score=9)
                
                for r in results:
                    stock_data = {
                        'symbol': r.symbol,
                        'name': r.name if hasattr(r, 'name') else '',
                        'price': r.current_price,
                        'score': r.score,
                        'found_at': datetime.now().isoformat()
                    }
                    add_to_scan_results(stock_data, scan_type)
                    found_count += 1
                    
                    # Notify user of new find
                    await application.bot.send_message(
                        chat_id=chat_id,
                        text=f"✅ <b>Found: {r.symbol}</b>\n"
                             f"💰 ₹{r.current_price:,.2f} | Score: {r.score}/9\n"
                             f"📊 Progress: {offset + len(chunk)}/{total_stocks}",
                        parse_mode='HTML'
                    )
                
            except Exception as e:
                logger.error(f"Error scanning chunk at offset {offset}: {e}")
            
            # Update offset
            offset += CHUNK_SIZE
            
            # Check if scan was stopped
            current_state = load_scan_state()
            if current_state and current_state.get('stopped'):
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=f"⏹️ <b>Scan Stopped</b>\n\n"
                         f"📊 Scanned: {offset}/{total_stocks}\n"
                         f"✅ Found: {found_count} stocks\n\n"
                         f"Use /resume to continue",
                    parse_mode='HTML'
                )
                return True
            
            # Progress update every 5 chunks
            if chunk_num % 5 == 0:
                pct = (offset / total_stocks) * 100
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=f"📊 <b>Progress: {pct:.1f}%</b>\n"
                         f"Scanned: {offset}/{total_stocks}\n"
                         f"Found: {found_count} qualifying stocks",
                    parse_mode='HTML'
                )
            
            # Small delay between chunks
            await asyncio.sleep(SCAN_INTERVAL_SECONDS)
        
        # Scan complete!
        results = load_scan_results()
        results['completed_at'] = datetime.now().isoformat()
        results['total_scanned'] = total_stocks
        save_scan_results(results)
        clear_scan_state()
        
        # Send completion message
        await application.bot.send_message(
            chat_id=chat_id,
            text=f"🎯 <b>{scan_name} Scan Complete!</b>\n\n"
                 f"📊 Scanned: {total_stocks} stocks\n"
                 f"✅ Found: {len(results['stocks'])} qualifying stocks\n\n"
                 f"Use /list to see all results!",
            parse_mode='HTML'
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Chunked scan error: {e}")
        return False
    finally:
        is_scanning = False


# ============ FLASK ROUTES ============

@flask_app.route('/')
def home():
    """Home page - confirms bot is running"""
    results = load_scan_results()
    state = load_scan_state()
    
    scan_status = "Idle"
    if state and not state.get('stopped'):
        pct = (state.get('offset', 0) / state.get('total', 1)) * 100
        scan_status = f"Scanning: {pct:.1f}% ({state.get('scan_type', 'unknown')})"
    elif results.get('completed_at'):
        scan_status = f"Last scan: {len(results.get('stocks', []))} stocks found"
    
    return f"""
    <html>
    <head><title>Minervini Bot</title></head>
    <body style="font-family: Arial; text-align: center; padding: 50px; background: #1a1a2e; color: white;">
        <h1>🎯 Minervini Stock Screener Bot</h1>
        <p style="color: #00ff88;">✅ Bot is running!</p>
        <p>Telegram: <a href="https://t.me/Minervini_1_bot" style="color: #00d4ff;">@Minervini_1_bot</a></p>
        <hr style="border-color: #333;">
        <p style="color: #ffd700;">📊 Status: {scan_status}</p>
        <p style="color: #888;">Health: <a href="/health" style="color: #00d4ff;">/health</a></p>
    </body>
    </html>
    """


@flask_app.route('/health')
def health():
    """Health check endpoint - ping this to keep bot alive"""
    state = load_scan_state()
    results = load_scan_results()
    
    return Response(
        json.dumps({
            "status": "healthy",
            "bot": "Minervini Scanner",
            "scanning": is_scanning,
            "scan_progress": state.get('offset', 0) if state else 0,
            "scan_total": state.get('total', 0) if state else 0,
            "results_count": len(results.get('stocks', []))
        }),
        status=200,
        mimetype='application/json'
    )


@flask_app.route('/trigger-scan/<scan_type>')
def trigger_scan(scan_type):
    """Trigger a scan via HTTP (for cron jobs)"""
    global main_loop
    
    if scan_type not in ['fullscan', 'scanall']:
        return Response(json.dumps({"error": "Invalid scan type"}), status=400)
    
    state = load_scan_state()
    chat_id = state.get('chat_id') if state else None
    
    if not chat_id:
        return Response(json.dumps({"error": "No chat_id stored. Send /fullscan or /scanall first."}), status=400)
    
    if main_loop:
        # Run scan using the main event loop
        asyncio.run_coroutine_threadsafe(run_chunked_scan(chat_id, scan_type), main_loop)
    
    return Response(json.dumps({"status": "scan_started", "type": scan_type}), status=200)


@flask_app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming Telegram updates via webhook"""
    global application, main_loop
    if application and main_loop:
        update = Update.de_json(request.get_json(force=True), application.bot)
        # Use run_coroutine_threadsafe instead of asyncio.run() to avoid closing event loop
        future = asyncio.run_coroutine_threadsafe(application.process_update(update), main_loop)
        try:
            future.result(timeout=30)  # Wait up to 30 seconds for processing
        except Exception as e:
            logger.error(f"Error processing update: {e}")
    return Response('ok', status=200)


# ============ BOT HANDLERS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message"""
    welcome = """
🎯 <b>Minervini Stock Screener Bot</b>

Welcome! I can scan NSE stocks using Mark Minervini's Trend Template.

<b>📊 Quick Commands:</b>
/scan - Quick scan (top 50 stocks)
/check SYMBOL - Check specific stock

<b>🔄 Full Scans (with progress):</b>
/fullscan - Nifty 500 scan (~500 stocks)
/scanall - ALL NSE stocks (~2000 stocks)
/progress - Check scan progress
/stop - Stop current scan
/resume - Resume stopped scan

<b>📋 Results:</b>
/list - Show all qualifying stocks

<b>ℹ️ Info:</b>
/nse - Show all available stocks
/help - Show this message

✨ <i>Full scans run in background and save results automatically!</i>
    """
    await update.message.reply_text(welcome.strip(), parse_mode='HTML')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help"""
    await start(update, context)


async def progress_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check scan progress"""
    state = load_scan_state()
    results = load_scan_results()
    
    if not state:
        if results.get('completed_at'):
            await update.message.reply_text(
                f"✅ <b>Last Scan Complete</b>\n\n"
                f"📊 Type: {results.get('scan_type', 'unknown')}\n"
                f"✅ Found: {len(results.get('stocks', []))} stocks\n"
                f"🕐 Completed: {results.get('completed_at', 'unknown')[:19]}\n\n"
                f"Use /list to see results!",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text("📊 No scan in progress. Use /fullscan or /scanall to start.")
        return
    
    offset = state.get('offset', 0)
    total = state.get('total', 1)
    pct = (offset / total) * 100
    found = len(results.get('stocks', []))
    
    status = "⏸️ Paused" if state.get('stopped') else "🔄 Running"
    
    await update.message.reply_text(
        f"📊 <b>Scan Progress</b>\n\n"
        f"Status: {status}\n"
        f"Type: {state.get('scan_type', 'unknown')}\n"
        f"Progress: {offset}/{total} ({pct:.1f}%)\n"
        f"Found: {found} qualifying stocks\n"
        f"Started: {state.get('started_at', 'unknown')[:19]}\n\n"
        f"{'Use /resume to continue' if state.get('stopped') else 'Use /stop to pause'}",
        parse_mode='HTML'
    )


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop current scan"""
    state = load_scan_state()
    if not state:
        await update.message.reply_text("📊 No scan in progress.")
        return
    
    state['stopped'] = True
    save_scan_state(state)
    
    await update.message.reply_text(
        "⏹️ <b>Stopping scan...</b>\n\n"
        "The scan will stop after the current chunk.\n"
        "Use /resume to continue later.",
        parse_mode='HTML'
    )


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resume a stopped scan"""
    state = load_scan_state()
    if not state:
        await update.message.reply_text("📊 No scan to resume. Use /fullscan or /scanall to start.")
        return
    
    if not state.get('stopped'):
        await update.message.reply_text("📊 Scan is already running. Use /progress to check.")
        return
    
    state['stopped'] = False
    save_scan_state(state)
    
    chat_id = update.effective_chat.id
    scan_type = state.get('scan_type', 'fullscan')
    
    await update.message.reply_text(
        f"▶️ <b>Resuming {scan_type}...</b>\n\n"
        f"Progress: {state.get('offset', 0)}/{state.get('total', 0)}",
        parse_mode='HTML'
    )
    
    # Run in background
    asyncio.create_task(run_chunked_scan(chat_id, scan_type))


async def nse_stocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show total NSE stocks available"""
    all_stocks = get_all_nse_stocks()
    nifty500 = get_nse_stock_list()
    
    header = f"""📊 <b>NSE Stocks Available</b>

<b>Total stocks in database: {len(all_stocks)}</b>

<b>Scan Options:</b>
• /scan - Quick scan (top 50) ⚡
• /fullscan - Nifty 500 ({len(nifty500)} stocks) 📊
• /scanall - ALL NSE ({len(all_stocks)} stocks) 🌐

✨ Full scans run in background with progress updates!
"""
    await update.message.reply_text(header, parse_mode='HTML')


async def scan_all_nse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start chunked scan of ALL NSE stocks"""
    global is_scanning
    
    if is_scanning:
        await update.message.reply_text(
            "⚠️ A scan is already running!\n"
            "Use /progress to check status\n"
            "Use /stop to cancel",
            parse_mode='HTML'
        )
        return
    
    chat_id = update.effective_chat.id
    
    # Start scan in background
    asyncio.create_task(run_chunked_scan(chat_id, "scanall"))


async def full_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start chunked scan of Nifty 500"""
    global is_scanning
    
    if is_scanning:
        await update.message.reply_text(
            "⚠️ A scan is already running!\n"
            "Use /progress to check status\n"
            "Use /stop to cancel",
            parse_mode='HTML'
        )
        return
    
    chat_id = update.effective_chat.id
    
    # Start scan in background
    asyncio.create_task(run_chunked_scan(chat_id, "fullscan"))


async def check_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check a specific stock"""
    if not context.args:
        await update.message.reply_text("❌ Please provide a stock symbol.\nExample: /check RELIANCE")
        return
    
    symbol = context.args[0].upper()
    await update.message.reply_text(f"🔍 Checking {symbol}...")
    
    try:
        result = screener.check_trend_template(symbol)
        
        if not result:
            import yfinance as yf
            try:
                ticker = yf.Ticker(f"{symbol}.NS")
                hist = ticker.history(period="1y")
                info = ticker.info
                
                if not hist.empty:
                    current_price = hist['Close'].iloc[-1]
                    high_52w = hist['High'].max()
                    low_52w = hist['Low'].min()
                    days_data = len(hist)
                    
                    message = f"""📊 <b>{symbol}</b>

<b>⚠️ Limited Data</b>
Only {days_data} days available (need 200+)

💰 Price: ₹{current_price:,.2f}
📈 52W High: ₹{high_52w:,.2f}
📉 52W Low: ₹{low_52w:,.2f}

Company: {info.get('shortName', symbol)}"""
                    await update.message.reply_text(message, parse_mode='HTML')
                    return
            except:
                pass
            
            await update.message.reply_text(f"❌ Could not fetch data for {symbol}")
            return
        
        status = "✅ PASSES" if result.passes_all else "❌ FAILS"
        
        message = f"""📊 <b>{symbol}</b> - {result.name}

<b>Score: {result.score}/9 {status}</b>

💰 Price: ₹{result.current_price:,.2f}

📊 <b>Moving Averages:</b>
• 50 SMA: ₹{result.metrics['sma_50']:,.2f}
• 150 SMA: ₹{result.metrics['sma_150']:,.2f}
• 200 SMA: ₹{result.metrics['sma_200']:,.2f}

📈 <b>52-Week:</b>
• High: ₹{result.metrics['week_52_high']:,.2f} ({result.metrics['pct_from_52w_high']:.1f}% away)
• Low: ₹{result.metrics['week_52_low']:,.2f} ({result.metrics['pct_above_52w_low']:.1f}% above)
"""
        
        criteria_labels = {
            "1_price_above_150sma": "Price > 150 SMA",
            "2_price_above_200sma": "Price > 200 SMA",
            "3_150sma_above_200sma": "150 > 200 SMA",
            "4_200sma_trending_up": "200 SMA Uptrend",
            "5_50sma_above_150sma": "50 > 150 SMA",
            "6_50sma_above_200sma": "50 > 200 SMA",
            "7_price_above_50sma": "Price > 50 SMA",
            "8_price_30pct_above_52w_low": "≥30% above Low",
            "9_price_within_25pct_of_52w_high": "Within 25% of High"
        }
        
        message += "<b>Criteria:</b>\n"
        for key, passed in result.criteria.items():
            icon = "✅" if passed else "❌"
            label = criteria_labels.get(key, key)
            message += f"{icon} {label}\n"
        
        await update.message.reply_text(message.strip(), parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error checking {symbol}: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def quick_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Run quick scan on top 50 stocks"""
    await update.message.reply_text("🔍 Quick scan on top 50 stocks...\nThis takes 2-3 minutes.")
    
    try:
        stocks = get_nse_stock_list()[:50]
        results = screener.scan_stocks(stocks, min_score=9)
        
        if not results:
            await update.message.reply_text("📊 No stocks currently meet all 9 criteria.")
            return
        
        # Save to results file
        save_scan_results({
            "stocks": [
                {"symbol": r.symbol, "name": getattr(r, 'name', ''), "price": r.current_price, "score": r.score}
                for r in results
            ],
            "scan_type": "quick",
            "completed_at": datetime.now().isoformat(),
            "total_scanned": 50
        })
        
        message = f"🎯 <b>Quick Scan Results</b>\n\n"
        message += f"📊 Found {len(results)} qualifying stocks:\n\n"
        
        for i, r in enumerate(results[:20], 1):
            message += f"{i}. <b>{r.symbol}</b> | ₹{r.current_price:,.2f}\n"
        
        if len(results) > 20:
            message += f"\n...and {len(results) - 20} more. Use /list to see all."
        
        message += "\n\n✅ All pass 9/9 criteria"
        
        await update.message.reply_text(message, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Scan error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def list_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show ALL eligible stocks from stored results"""
    results = load_scan_results()
    stocks = results.get('stocks', [])
    
    if not stocks:
        await update.message.reply_text("📋 No results yet. Run /scan, /fullscan or /scanall first!")
        return
    
    scan_type = results.get('scan_type', 'unknown')
    completed = results.get('completed_at', 'unknown')
    if completed and len(completed) > 19:
        completed = completed[:19]
    
    header = f"""📋 <b>Scan Results</b>

📊 Type: {scan_type}
✅ Found: {len(stocks)} stocks
🕐 Completed: {completed}
━━━━━━━━━━━━━━━━━━━━━━━━"""
    await update.message.reply_text(header, parse_mode='HTML')
    
    # Send in batches
    batch_size = 25
    for i in range(0, len(stocks), batch_size):
        batch = stocks[i:i + batch_size]
        message = ""
        for j, s in enumerate(batch, i + 1):
            name = s.get('name', '')[:20]
            price = s.get('price', 0)
            message += f"{j}. <b>{s['symbol']}</b> | {name} | ₹{price:,.2f}\n"
        await update.message.reply_text(message, parse_mode='HTML')
    
    footer = f"━━━━━━━━━━━━━━━━━━━━━━━━\n✅ <b>Total: {len(stocks)} stocks pass 9/9 criteria</b>"
    await update.message.reply_text(footer, parse_mode='HTML')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages"""
    text = update.message.text.upper()
    
    if text.isalpha() and len(text) <= 20:
        context.args = [text]
        await check_stock(update, context)
    else:
        await update.message.reply_text(
            "💡 Send a stock symbol to check it, or use:\n"
            "/scan - Quick scan\n"
            "/check SYMBOL - Check stock\n"
            "/help - All commands"
        )


# ============ SETUP AND RUN ============

async def setup_webhook():
    """Set up the webhook for Telegram"""
    global application
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("nse", nse_stocks))
    application.add_handler(CommandHandler("check", check_stock))
    application.add_handler(CommandHandler("scan", quick_scan))
    application.add_handler(CommandHandler("fullscan", full_scan))
    application.add_handler(CommandHandler("scanall", scan_all_nse))
    application.add_handler(CommandHandler("list", list_results))
    application.add_handler(CommandHandler("progress", progress_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("resume", resume_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    await application.initialize()
    
    if RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL}/webhook"
        await application.bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook set to: {webhook_url}")
    else:
        logger.warning("No RENDER_EXTERNAL_URL set")
    
    return application


def run_flask():
    """Run Flask"""
    flask_app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False, threaded=True)


def run_async_loop(loop):
    """Run the async event loop in a separate thread"""
    asyncio.set_event_loop(loop)
    loop.run_forever()


if __name__ == "__main__":
    print("🚀 Starting Minervini Bot for Render...")
    print(f"📡 Port: {PORT}")
    
    # Create and store the main event loop in the module's global scope
    _main_loop = asyncio.new_event_loop()
    globals()['main_loop'] = _main_loop
    asyncio.set_event_loop(_main_loop)
    
    # Setup webhook (initialize application)
    _main_loop.run_until_complete(setup_webhook())
    
    print("✅ Bot ready with chunked scanning!")
    print(f"🌐 Health: http://localhost:{PORT}/health")
    
    # Run the event loop in a background thread so it stays alive
    loop_thread = Thread(target=run_async_loop, args=(_main_loop,), daemon=True)
    loop_thread.start()
    
    # Run Flask in the main thread (blocking)
    run_flask()
