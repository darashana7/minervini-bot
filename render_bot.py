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
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
import redis
from pymongo import MongoClient

sys.path.append(os.path.dirname(__file__))
from src.minervini_screener import MinerviniScreener
from src.stock_list import get_nse_stock_list
from src.all_nse_stocks import get_all_nse_stocks, get_nse_stock_count
from src.gemini_analyzer import GeminiStockAnalyzer
from config.config import SCAN_TIMES

# Configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8557128929:AAFrPNOsb-T_ygpaqu2MI0DbuZYEA2JT1rg")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
PORT = int(os.environ.get("PORT", 10000))

# Scan settings - OPTIMIZED for speed
CHUNK_SIZE = 60  # Increased from 30 - parallel fetching handles load
SCAN_INTERVAL_SECONDS = 1  # Reduced from 5 - parallel threads handle timing

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

# Scheduler
scheduler = AsyncIOScheduler()
SETTINGS_FILE = os.path.join(DATA_DIR, 'bot_settings.json')

# Initialize Redis
redis_client = None
REDIS_URL = os.environ.get('REDIS_URL')
if REDIS_URL:
    try:
        redis_client = redis.from_url(REDIS_URL)
        # Test connection
        redis_client.ping()
        logger.info("✅ Redis connected successfully")
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        redis_client = None

# Initialize MongoDB with FREE TIER optimizations
mongo_client = None
mongo_db = None
MONGO_URI = os.environ.get('MONGO_URI')
if MONGO_URI:
    try:
        # Free tier optimizations:
        # - maxPoolSize=5: Limit connections (free tier has limited connections)
        # - serverSelectionTimeoutMS=5000: Don't hang on slow responses
        # - connectTimeoutMS=10000: Timeout for initial connection
        # - retryWrites=true: Retry failed writes
        # - w=1: Acknowledge writes (not 'majority' - faster for free tier)
        mongo_client = MongoClient(
            MONGO_URI,
            maxPoolSize=5,  # Free tier: limit concurrent connections
            minPoolSize=1,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=20000,
            retryWrites=True,
            w=1,  # Faster than 'majority' for free tier
            compressors=['zlib']  # Compress data to save bandwidth
        )
        mongo_db = mongo_client.get_default_database()
        # Test connection
        mongo_client.admin.command('ping')
        logger.info("✅ MongoDB connected successfully (FREE TIER optimized)")
    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {e}")
        mongo_client = None
        mongo_db = None


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


# ============ IN-MEMORY CACHE (Reduces MongoDB reads) ============

class MemoryCache:
    """
    Simple in-memory cache to reduce MongoDB reads
    Free tier has limited IOPS - caching helps a lot!
    """
    def __init__(self, ttl_seconds=60):
        self._cache = {}
        self._timestamps = {}
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
    
    def get(self, key):
        """Get value if exists and not expired"""
        with self._lock:
            if key in self._cache:
                if time.time() - self._timestamps[key] < self._ttl:
                    return self._cache[key]
                else:
                    # Expired - clean up
                    del self._cache[key]
                    del self._timestamps[key]
        return None
    
    def set(self, key, value):
        """Set value with timestamp"""
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time()
    
    def delete(self, key):
        """Remove from cache"""
        with self._lock:
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)
    
    def clear(self):
        """Clear all cache"""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()

# Initialize memory cache (60 second TTL)
memory_cache = MemoryCache(ttl_seconds=60)


# ============ STORAGE FUNCTIONS (with caching) ============

def load_scan_state():
    """Load current scan state - uses cache to reduce MongoDB reads"""
    # Check memory cache first (reduces MongoDB reads)
    cached = memory_cache.get('scan_state')
    if cached is not None:
        return cached
    
    try:
        if mongo_db is not None:
            state = mongo_db.scan_state.find_one({'_id': 'current_state'})
            if state:
                state.pop('_id', None)
                memory_cache.set('scan_state', state)
                return state
        
        if redis_client:
            data = redis_client.get('scan_state')
            if data:
                state = json.loads(data)
                memory_cache.set('scan_state', state)
                return state
        elif os.path.exists(SCAN_STATE_FILE):
            with open(SCAN_STATE_FILE, 'r') as f:
                state = json.load(f)
                memory_cache.set('scan_state', state)
                return state
    except Exception as e:
        logger.error(f"Error loading scan state: {e}")
    return None


def save_scan_state(state):
    """Save scan state - updates cache on write"""
    # Update cache immediately
    memory_cache.set('scan_state', state)
    
    try:
        if mongo_db is not None:
            state_copy = state.copy()
            state_copy['_id'] = 'current_state'
            mongo_db.scan_state.replace_one({'_id': 'current_state'}, state_copy, upsert=True)
        
        if redis_client:
            redis_client.set('scan_state', json.dumps(state, cls=NumpyEncoder))
        else:
            with open(SCAN_STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2, cls=NumpyEncoder)
    except Exception as e:
        logger.error(f"Error saving scan state: {e}")


def clear_scan_state():
    """Clear scan state - invalidates cache"""
    # Clear from cache first
    memory_cache.delete('scan_state')
    
    try:
        if mongo_db is not None:
            mongo_db.scan_state.delete_one({'_id': 'current_state'})
            
        if redis_client:
            redis_client.delete('scan_state')
        elif os.path.exists(SCAN_STATE_FILE):
            os.remove(SCAN_STATE_FILE)
    except Exception as e:
        logger.error(f"Error clearing scan state: {e}")


def load_scan_results():
    """Load scan results - uses cache to reduce MongoDB reads"""
    # Check memory cache first
    cached = memory_cache.get('scan_results')
    if cached is not None:
        return cached
    
    try:
        if mongo_db is not None:
            results = mongo_db.scan_results.find_one({'_id': 'latest_results'})
            if results:
                results.pop('_id', None)
                memory_cache.set('scan_results', results)
                return results
                
        if redis_client:
            data = redis_client.get('scan_results')
            if data:
                results = json.loads(data)
                memory_cache.set('scan_results', results)
                return results
        elif os.path.exists(SCAN_RESULTS_FILE):
            with open(SCAN_RESULTS_FILE, 'r') as f:
                results = json.load(f)
                memory_cache.set('scan_results', results)
                return results
    except Exception as e:
        logger.error(f"Error loading scan results: {e}")
    return {"stocks": [], "scan_type": None, "completed_at": None, "total_scanned": 0}


def save_scan_results(results):
    """Save scan results - updates cache on write"""
    # Update cache immediately
    memory_cache.set('scan_results', results)
    
    try:
        if mongo_db is not None:
            results_copy = results.copy()
            results_copy['_id'] = 'latest_results'
            mongo_db.scan_results.replace_one({'_id': 'latest_results'}, results_copy, upsert=True)
            
        if redis_client:
            redis_client.set('scan_results', json.dumps(results, cls=NumpyEncoder))
        else:
            with open(SCAN_RESULTS_FILE, 'w') as f:
                json.dump(results, f, indent=2, cls=NumpyEncoder)
    except Exception as e:
        logger.error(f"Error saving scan results: {e}")
    
    # Also save to type-specific storage
    scan_type = results.get('scan_type')
    if scan_type:
        save_results_by_type(scan_type, results)


def load_results_by_type(scan_type: str):
    """
    Load scan results for a specific scan type.
    This persists results separately for quick, fullscan, and scanall.
    """
    cache_key = f'scan_results_{scan_type}'
    
    # Check memory cache first
    cached = memory_cache.get(cache_key)
    if cached is not None:
        return cached
    
    try:
        if mongo_db is not None:
            doc_id = f'results_{scan_type}'
            results = mongo_db.scan_results.find_one({'_id': doc_id})
            if results:
                results.pop('_id', None)
                memory_cache.set(cache_key, results)
                return results
                
        if redis_client:
            data = redis_client.get(cache_key)
            if data:
                results = json.loads(data)
                memory_cache.set(cache_key, results)
                return results
        else:
            # File-based: each type has its own file
            type_file = os.path.join(DATA_DIR, f'scan_results_{scan_type}.json')
            if os.path.exists(type_file):
                with open(type_file, 'r') as f:
                    results = json.load(f)
                    memory_cache.set(cache_key, results)
                    return results
    except Exception as e:
        logger.error(f"Error loading {scan_type} results: {e}")
    
    return {"stocks": [], "scan_type": scan_type, "completed_at": None, "total_scanned": 0}


def save_results_by_type(scan_type: str, results):
    """
    Save scan results for a specific scan type.
    Each type (quick, fullscan, scanall) is stored separately.
    """
    cache_key = f'scan_results_{scan_type}'
    
    # Update cache immediately
    memory_cache.set(cache_key, results)
    
    try:
        if mongo_db is not None:
            doc_id = f'results_{scan_type}'
            results_copy = results.copy()
            results_copy['_id'] = doc_id
            mongo_db.scan_results.replace_one({'_id': doc_id}, results_copy, upsert=True)
            
        if redis_client:
            redis_client.set(cache_key, json.dumps(results, cls=NumpyEncoder))
        else:
            # File-based: each type has its own file
            type_file = os.path.join(DATA_DIR, f'scan_results_{scan_type}.json')
            with open(type_file, 'w') as f:
                json.dump(results, f, indent=2, cls=NumpyEncoder)
    except Exception as e:
        logger.error(f"Error saving {scan_type} results: {e}")


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


def load_bot_settings():
    """Load bot settings - uses cache to reduce MongoDB reads"""
    # Check memory cache first
    cached = memory_cache.get('bot_settings')
    if cached is not None:
        return cached
    
    try:
        if mongo_db is not None:
            settings = mongo_db.bot_settings.find_one({'_id': 'global_settings'})
            if settings:
                settings.pop('_id', None)
                memory_cache.set('bot_settings', settings)
                return settings
                
        if redis_client:
            data = redis_client.get('bot_settings')
            if data:
                settings = json.loads(data)
                memory_cache.set('bot_settings', settings)
                return settings
        elif os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                memory_cache.set('bot_settings', settings)
                return settings
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
    return {"daily_scan_enabled": False, "target_chat_id": None, "scan_time_iso": "18:00"}


def save_bot_settings(settings):
    """Save bot settings - updates cache on write"""
    # Update cache immediately
    memory_cache.set('bot_settings', settings)
    
    try:
        if mongo_db is not None:
            settings_copy = settings.copy()
            settings_copy['_id'] = 'global_settings'
            mongo_db.bot_settings.replace_one({'_id': 'global_settings'}, settings_copy, upsert=True)
            
        if redis_client:
            redis_client.set('bot_settings', json.dumps(settings))
        else:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving settings: {e}")


# ============ CHUNKED SCANNING (OPTIMIZED) ============

async def run_chunked_scan(chat_id, scan_type="fullscan"):
    """
    Run a scan in chunks with progress updates - OPTIMIZED VERSION
    
    Optimizations applied:
    - Parallel stock fetching (10 stocks at once)
    - Batch database writes (collect in memory, write at end)
    - Progress updates at 25%, 50%, 75% only
    - Reduced inter-chunk delay
    """
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
        
        # Track progress milestones locally (not on function)
        sent_milestones = set()
        
        # Collect ALL results in memory for batch write
        all_found_stocks = []
        
        if state and state.get('scan_type') == scan_type and state.get('offset', 0) < total_stocks:
            # Resume existing scan
            offset = state.get('offset', 0)
            logger.info(f"Resuming {scan_type} from offset {offset}")
            # Load existing results
            existing_results = load_scan_results()
            all_found_stocks = existing_results.get('stocks', [])
        else:
            # Start new scan
            offset = 0
            # Clear previous results for this scan type
            save_scan_results({"stocks": [], "scan_type": scan_type, "completed_at": None, "total_scanned": 0})
            
            # Send start message with optimization info
            await application.bot.send_message(
                chat_id=chat_id,
                text=f"🔍 <b>Starting {scan_name} Scan</b>\n\n"
                     f"📊 Total stocks: {total_stocks}\n"
                     f"⚡ Mode: <b>PARALLEL</b> (10 stocks at once)\n"
                     f"⏱️ Chunk size: {CHUNK_SIZE}\n"
                     f"📝 Results saved at completion\n\n"
                     f"Use /progress to check status\n"
                     f"Use /stop to cancel",
                parse_mode='HTML'
            )
        
        found_count = len(all_found_stocks)
        
        # Process chunks
        while offset < total_stocks:
            chunk = all_stocks[offset:offset + CHUNK_SIZE]
            
            # Save current state for resume capability
            save_scan_state({
                'scan_type': scan_type,
                'offset': offset,
                'total': total_stocks,
                'started_at': state.get('started_at', datetime.now().isoformat()) if state else datetime.now().isoformat(),
                'chat_id': chat_id
            })
            
            # Scan this chunk in parallel (via screener's ThreadPoolExecutor)
            try:
                results = await asyncio.to_thread(screener.scan_stocks, chunk, 9, 10)  # min_score=9, max_workers=10
                
                # Collect results in memory (batch write optimization)
                for r in results:
                    stock_data = {
                        'symbol': r.symbol,
                        'name': r.name if hasattr(r, 'name') else '',
                        'price': r.current_price,
                        'score': r.score,
                        'found_at': datetime.now().isoformat()
                    }
                    all_found_stocks.append(stock_data)
                    found_count += 1
                
            except Exception as e:
                logger.error(f"Error scanning chunk at offset {offset}: {e}")
            
            # Update offset
            offset += CHUNK_SIZE
            
            # Check if scan was stopped
            current_state = load_scan_state()
            if current_state and current_state.get('stopped'):
                # Save partial results before stopping
                save_scan_results({
                    "stocks": all_found_stocks, 
                    "scan_type": scan_type, 
                    "completed_at": None, 
                    "total_scanned": offset
                })
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=f"⏹️ <b>Scan Stopped</b>\n\n"
                         f"📊 Scanned: {offset}/{total_stocks}\n"
                         f"✅ Found: {found_count} stocks\n\n"
                         f"Use /resume to continue",
                    parse_mode='HTML'
                )
                return True
            
            # Progress update at 25%, 50%, 75% milestones only (reduced API calls)
            pct = (offset / total_stocks) * 100
            for milestone in [25, 50, 75]:
                if pct >= milestone and milestone not in sent_milestones:
                    sent_milestones.add(milestone)
                    await application.bot.send_message(
                        chat_id=chat_id,
                        text=f"📊 <b>Progress: {milestone}%</b>\n"
                             f"Scanned: {offset}/{total_stocks}\n"
                             f"Found: {found_count} qualifying stocks",
                        parse_mode='HTML'
                    )
                    break  # Only send one message per chunk
            
            # Minimal delay between chunks (parallel handles timing)
            await asyncio.sleep(SCAN_INTERVAL_SECONDS)
        
        # Scan complete - BATCH WRITE all results at once!
        final_results = {
            "stocks": all_found_stocks,
            "scan_type": scan_type,
            "completed_at": datetime.now().isoformat(),
            "total_scanned": total_stocks
        }
        save_scan_results(final_results)
        clear_scan_state()
        
        # Send completion message with full list
        if all_found_stocks:
            message = f"🎯 <b>{scan_name} Scan Complete!</b>\n\n"
            message += f"📊 Scanned: {total_stocks} stocks\n"
            message += f"✅ Found: {len(all_found_stocks)} qualifying stocks\n\n"
            message += "<b>📋 Qualifying Stocks:</b>\n"
            
            for i, stock in enumerate(all_found_stocks[:30], 1):
                message += f"{i}. <b>{stock['symbol']}</b> | ₹{stock['price']:,.2f}\n"
            
            if len(all_found_stocks) > 30:
                message += f"\n...and {len(all_found_stocks) - 30} more. Use /list to see all."
        else:
            message = f"🎯 <b>{scan_name} Scan Complete!</b>\n\n"
            message += f"📊 Scanned: {total_stocks} stocks\n"
            message += "❌ No stocks currently meet all 9 criteria."
        
        await application.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode='HTML'
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Chunked scan error: {e}")
        return False
    finally:
        is_scanning = False



# ============ SCHEDULING ============

async def scheduled_scan_job():
    """Job to run daily scan"""
    logger.info("⏰ Triggering scheduled daily scan...")
    settings = load_bot_settings()
    
    if not settings.get('daily_scan_enabled'):
        logger.info("Daily scan disabled in settings.")
        return
        
    chat_id = settings.get('target_chat_id')
    if not chat_id:
        logger.warning("No target chat ID for daily scan.")
        return
        
    # Send Start Notification
    await application.bot.send_message(
        chat_id=chat_id,
        text="⏰ <b>Scheduled Scan Started</b>\nScanning all NSE stocks...",
        parse_mode='HTML'
    )
    
    # Trigger scan
    await run_chunked_scan(chat_id, "scanall")


def setup_scheduler(settings):
    """Configure scheduler jobs"""
    global scheduler
    
    # Remove existing jobs
    properties = scheduler.get_jobs()
    for job in properties:
        scheduler.remove_job(job.id)
    
    if settings.get('daily_scan_enabled'):
        tz = pytz.timezone('Asia/Kolkata')
        
        # Schedule all times from config
        try:
            scheduled_count = 0
            for i, time_str in enumerate(SCAN_TIMES):
                try:
                    h, m = map(int, time_str.split(':'))
                    scheduler.add_job(
                        scheduled_scan_job,
                        CronTrigger(hour=h, minute=m, timezone=tz),
                        id=f'scan_job_{i}',
                        replace_existing=True
                    )
                    scheduled_count += 1
                except ValueError:
                    logger.warning(f"Invalid time format in config: {time_str}")
            
            logger.info(f"Scheduled {scheduled_count} scans from config")
            
        except Exception as e:
            logger.error(f"Error scheduling from config: {e}")
            # Fallback to 18:00
            scheduler.add_job(
                scheduled_scan_job,
                CronTrigger(hour=18, minute=0, timezone=tz),
                id='daily_scan',
                replace_existing=True
            )


async def autodaily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle daily auto-scan"""
    chat_id = update.effective_chat.id
    settings = load_bot_settings()
    
    current_status = settings.get('daily_scan_enabled', False)
    
    # Toggle or set based on args
    if context.args:
        arg = context.args[0].lower()
        if arg in ['on', 'enable', 'yes', 'true']:
            new_status = True
        elif arg in ['off', 'disable', 'no', 'false']:
            new_status = False
        else:
            await update.message.reply_text("Usage: /autodaily [on/off]")
            return
    else:
        # Toggle
        new_status = not current_status
    
    settings['daily_scan_enabled'] = new_status
    settings['target_chat_id'] = chat_id
    save_bot_settings(settings)
    
    # Update scheduler
    setup_scheduler(settings)
    
    status_text = "ENABLED" if new_status else "DISABLED"
    status_icon = "✅" if new_status else "❌"
    
    times_str = ", ".join(SCAN_TIMES)
    await update.message.reply_text(
        f"{status_icon} <b>Scheduled Scanning {status_text}</b>\n\n"
        f"⏰ Times (IST): {times_str}\n"
        f"🎯 Target Chat: {chat_id}\n"
        f"📊 Scope: ALL NSE Stocks (~2000)",
        parse_mode='HTML'
    )


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
/autodaily [on/off] - Enable daily 6PM scan ⏰

<b>🤖 AI Analysis:</b>
/ai SYMBOL - Get AI entry/stop-loss levels

<b>🔄 Full Scans (with progress):</b>
/fullscan - Nifty 500 scan (~500 stocks)
/scanall - ALL NSE stocks (~2000 stocks)
/progress - Check scan progress
/stop - Stop current scan
/resume - Resume stopped scan

<b>📋 Results:</b>
/list - Show latest scan results
/list all - Summary of all scan types
/list quick - Quick scan results only
/list fullscan - Full scan results only
/list scanall - All NSE scan results only
/listquick, /listfull, /listall - Shortcuts

<b>ℹ️ Info:</b>
/nse - Show all available stocks
/help - Show this message

✨ <i>Each scan type saves results separately!</i>
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
        # Offload blocking network call
        result = await asyncio.to_thread(screener.check_trend_template, symbol)
        
        if not result:
            import yfinance as yf
            try:
                # Offload blocking yfinance call
                ticker = await asyncio.to_thread(yf.Ticker, f"{symbol}.NS")
                hist = await asyncio.to_thread(ticker.history, period="1y")
                info = await asyncio.to_thread(lambda: ticker.info)
                
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
        # Offload blocking scan
        results = await asyncio.to_thread(screener.scan_stocks, stocks, min_score=9)
        
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
    """
    Show eligible stocks from stored results.
    Usage:
        /list - Show latest scan results
        /list quick - Show quick scan results
        /list fullscan - Show fullscan results  
        /list scanall - Show scanall results
        /list all - Show summary of all scan types
    """
    # Check for scan type argument
    scan_type = None
    if context.args:
        arg = context.args[0].lower()
        if arg in ['quick', 'scan']:
            scan_type = 'quick'
        elif arg in ['fullscan', 'full']:
            scan_type = 'fullscan'
        elif arg in ['scanall', 'all_nse']:
            scan_type = 'scanall'
        elif arg == 'all':
            # Show summary of all scan types
            await show_all_scan_summaries(update)
            return
    
    # Load results based on type or latest
    if scan_type:
        results = load_results_by_type(scan_type)
    else:
        results = load_scan_results()
    
    await display_results(update, results)


async def show_all_scan_summaries(update: Update):
    """Show summary of all available scan results"""
    message = "📋 <b>All Scan Results Summary</b>\n\n"
    
    scan_types = [
        ('quick', 'Quick Scan (Top 50)', '⚡'),
        ('fullscan', 'Full Scan (Nifty 500)', '📊'),
        ('scanall', 'All NSE (~2000)', '🌐')
    ]
    
    for scan_type, name, icon in scan_types:
        results = load_results_by_type(scan_type)
        stocks = results.get('stocks', [])
        completed = results.get('completed_at', 'Never')
        if completed and len(completed) > 19:
            completed = completed[:10]  # Just the date
        
        if stocks:
            message += f"{icon} <b>{name}</b>\n"
            message += f"   ✅ Found: {len(stocks)} stocks\n"
            message += f"   🕐 Date: {completed}\n\n"
        else:
            message += f"{icon} <b>{name}</b>\n"
            message += f"   ❌ No results yet\n\n"
    
    message += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    message += "<b>Commands:</b>\n"
    message += "/list quick - View quick scan\n"
    message += "/list fullscan - View full scan\n"
    message += "/list scanall - View all NSE scan\n"
    message += "/list - View latest scan"
    
    await update.message.reply_text(message, parse_mode='HTML')


async def display_results(update: Update, results):
    """Helper function to display scan results"""
    stocks = results.get('stocks', [])
    
    if not stocks:
        scan_type = results.get('scan_type', 'unknown')
        await update.message.reply_text(
            f"📋 No results for <b>{scan_type}</b> scan.\n\n"
            f"Run /scan, /fullscan or /scanall first!",
            parse_mode='HTML'
        )
        return
    
    scan_type = results.get('scan_type', 'unknown')
    completed = results.get('completed_at', 'unknown')
    total_scanned = results.get('total_scanned', 0)
    if completed and len(completed) > 19:
        completed = completed[:19]
    
    # Determine scan name for display
    scan_names = {
        'quick': '⚡ Quick Scan (Top 50)',
        'fullscan': '📊 Full Scan (Nifty 500)',
        'scanall': '🌐 All NSE Scan'
    }
    display_name = scan_names.get(scan_type, scan_type)
    
    header = f"""📋 <b>{display_name} Results</b>

✅ Found: {len(stocks)} qualifying stocks
📊 Scanned: {total_scanned} stocks
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


async def list_quick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shortcut to list quick scan results"""
    context.args = ['quick']
    await list_results(update, context)


async def list_full(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shortcut to list fullscan results"""
    context.args = ['fullscan']
    await list_results(update, context)


async def list_all_nse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shortcut to list scanall results"""
    context.args = ['scanall']
    await list_results(update, context)


async def ai_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get AI-powered entry/stop-loss analysis using Google Gemini"""
    if not context.args:
        await update.message.reply_text("❌ Please provide a stock symbol.\nExample: /ai RELIANCE")
        return
    
    symbol = context.args[0].upper()
    await update.message.reply_text(f"🤖 Analyzing {symbol} with AI...")
    
    try:
        # Get stock data first using the screener
        result = screener.check_trend_template(symbol)
        if not result:
            await update.message.reply_text(f"❌ Could not fetch data for {symbol}")
            return
        
        # Prepare data for AI analysis
        stock_data = {
            'current_price': float(result.current_price),
            'sma_50': float(result.metrics['sma_50']),
            'sma_150': float(result.metrics['sma_150']),
            'sma_200': float(result.metrics['sma_200']),
            'week_52_high': float(result.metrics['week_52_high']),
            'week_52_low': float(result.metrics['week_52_low'])
        }
        
        # Get AI analysis from Gemini
        analyzer = GeminiStockAnalyzer()
        analysis = analyzer.analyze_stock(symbol, stock_data)
        
        # Format response
        trend_status = "✅ PASSES" if result.passes_all else "❌ FAILS"
        
        message = f"""🤖 <b>AI Analysis: {symbol}</b>

💰 Current Price: ₹{result.current_price:,.2f}
📊 Minervini Score: {result.score}/9 {trend_status}

<b>🎯 AI Recommendations:</b>
📈 Entry Level: {analysis['entry_level']}
🛑 Stop Loss: {analysis['stop_loss']}
🎖️ Target: {analysis['target']}

<b>💡 Analysis:</b>
{analysis['reasoning']}

⚠️ <i>AI suggestions for educational purposes only. Do your own research.</i>"""
        
        await update.message.reply_text(message, parse_mode='HTML')
        
    except ValueError as e:
        if "GEMINI_API_KEY" in str(e):
            await update.message.reply_text("❌ Gemini API not configured. Contact admin to set GEMINI_API_KEY.")
        else:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    except Exception as e:
        logger.error(f"AI analysis error for {symbol}: {e}")
        await update.message.reply_text(f"❌ AI analysis failed: {str(e)}")


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
    application.add_handler(CommandHandler("ai", ai_analysis))
    application.add_handler(CommandHandler("scan", quick_scan))
    application.add_handler(CommandHandler("fullscan", full_scan))
    application.add_handler(CommandHandler("scanall", scan_all_nse))
    application.add_handler(CommandHandler("list", list_results))
    application.add_handler(CommandHandler("listquick", list_quick))
    application.add_handler(CommandHandler("listfull", list_full))
    application.add_handler(CommandHandler("listall", list_all_nse))
    application.add_handler(CommandHandler("progress", progress_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("resume", resume_command))
    application.add_handler(CommandHandler("autodaily", autodaily_command))
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
    
    # Initialize and start scheduler
    try:
        settings = load_bot_settings()
        setup_scheduler(settings)
        if not scheduler.running:
            scheduler.start()
            logger.info("✅ Scheduler started in background thread")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        
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
