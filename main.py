"""
Mark Minervini Stock Alert System
Main entry point with scheduler
"""
import schedule
import time
import argparse
from datetime import datetime
import logging
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(__file__))

from config.config import SCAN_TIMES, MARKET_OPEN_TIME, MARKET_CLOSE_TIME
from src.minervini_screener import MinerviniScreener, format_result_for_display
from src.alerts import AlertManager
from src.telegram_bot import TelegramBot, send_test_alert
from src.stock_list import get_nse_stock_list, load_stock_list, update_stock_list

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('minervini_scanner.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MinerviniAlertSystem:
    """Main alert system coordinating all components"""
    
    def __init__(self):
        self.screener = MinerviniScreener()
        self.alert_manager = AlertManager()
        self.telegram = TelegramBot()
        self.stocks = []
        self._load_stocks()
    
    def _load_stocks(self):
        """Load stock list"""
        try:
            self.stocks = load_stock_list()
            if not self.stocks:
                self.stocks = get_nse_stock_list()
            logger.info(f"Loaded {len(self.stocks)} stocks for scanning")
        except Exception as e:
            logger.error(f"Error loading stocks: {e}")
            self.stocks = get_nse_stock_list()
    
    def run_scan(self, min_score: int = 9, send_alerts: bool = True) -> list:
        """
        Run a complete scan of all stocks
        
        Args:
            min_score: Minimum score to qualify (default 9 = all criteria)
            send_alerts: Whether to send Telegram alerts
            
        Returns:
            List of qualifying stocks
        """
        scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
        logger.info(f"Starting Minervini scan at {scan_time}...")
        logger.info(f"Scanning {len(self.stocks)} stocks...")
        
        # Run the screener
        results = self.screener.scan_stocks(self.stocks, min_score=min_score)
        
        logger.info(f"Found {len(results)} stocks meeting criteria")
        
        # Process results
        new_alerts = []
        for result in results:
            result_dict = result.to_dict()
            
            # Check if we should alert
            if send_alerts and self.alert_manager.should_alert(result.symbol):
                # Send individual alert
                if self.telegram.send_alert(result_dict):
                    self.alert_manager.record_alert(result.symbol, result_dict)
                    new_alerts.append(result_dict)
                    logger.info(f"Alert sent for {result.symbol}")
                else:
                    logger.error(f"Failed to send alert for {result.symbol}")
        
        # Send scan summary
        if send_alerts:
            self.telegram.send_scan_summary(
                [r.to_dict() for r in results],
                scan_time
            )
        
        logger.info(f"Scan complete. Sent {len(new_alerts)} new alerts.")
        
        return [r.to_dict() for r in results]
    
    def run_quick_scan(self, symbols: list = None) -> list:
        """
        Run a quick scan on specific symbols
        
        Args:
            symbols: List of symbols to scan (default: first 10 stocks)
        """
        if symbols is None:
            symbols = self.stocks[:10]
        
        results = []
        for symbol in symbols:
            result = self.screener.check_trend_template(symbol)
            if result:
                results.append(result)
                print(format_result_for_display(result))
        
        return results
    
    def get_near_misses(self, min_score: int = 7) -> list:
        """Find stocks that nearly meet all criteria"""
        return self.screener.get_near_misses(self.stocks, min_score=min_score)


def setup_schedule():
    """Set up the scanning schedule"""
    system = MinerviniAlertSystem()
    
    # Schedule scans at specified times
    for scan_time in SCAN_TIMES:
        schedule.every().day.at(scan_time).do(system.run_scan)
        logger.info(f"Scheduled scan at {scan_time}")
    
    return system


def run_scheduler():
    """Run the scheduler loop"""
    logger.info("Starting Minervini Alert System scheduler...")
    system = setup_schedule()
    
    # Send startup notification
    system.telegram.send_message(
        "🚀 <b>Minervini Alert System Started</b>\n\n"
        f"📊 Monitoring {len(system.stocks)} NSE stocks\n"
        f"⏰ Scan times: {', '.join(SCAN_TIMES)}\n\n"
        "System is now active."
    )
    
    # Run scheduler
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Minervini Stock Alert System')
    parser.add_argument('--test', action='store_true', help='Run test scan with sample stocks')
    parser.add_argument('--scan', action='store_true', help='Run full scan immediately')
    parser.add_argument('--quick', action='store_true', help='Run quick scan (top 20 stocks)')
    parser.add_argument('--schedule', action='store_true', help='Start scheduled scanning')
    parser.add_argument('--test-telegram', action='store_true', help='Test Telegram connection')
    parser.add_argument('--near-misses', action='store_true', help='Find stocks close to qualifying')
    parser.add_argument('--min-score', type=int, default=9, help='Minimum score to qualify')
    parser.add_argument('--symbols', nargs='+', help='Specific symbols to scan')
    parser.add_argument('--update-stocks', action='store_true', help='Update stock list')
    
    args = parser.parse_args()
    
    if args.test_telegram:
        print("Testing Telegram connection...")
        send_test_alert()
        return
    
    if args.update_stocks:
        print("Updating stock list...")
        stocks = update_stock_list()
        print(f"Updated with {len(stocks)} stocks")
        return
    
    system = MinerviniAlertSystem()
    
    if args.test or args.quick:
        print("\n" + "="*60)
        print("🔍 MINERVINI TREND TEMPLATE SCANNER - QUICK TEST")
        print("="*60)
        
        # Quick scan with top stocks
        symbols = args.symbols or [
            "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
            "BHARTIARTL", "ITC", "SBIN", "LT", "AXISBANK",
            "MARUTI", "TITAN", "SUNPHARMA", "BAJFINANCE", "KOTAKBANK",
            "WIPRO", "HCLTECH", "TATAMOTORS", "M&M", "ADANIENT"
        ]
        
        system.run_quick_scan(symbols)
        return
    
    if args.scan:
        print("\n" + "="*60)
        print("🔍 MINERVINI TREND TEMPLATE SCANNER - FULL SCAN")
        print("="*60)
        
        results = system.run_scan(min_score=args.min_score)
        
        print(f"\n✅ Scan complete! Found {len(results)} qualifying stocks.")
        return
    
    if args.near_misses:
        print("\n" + "="*60)
        print("🔍 FINDING NEAR MISSES (Score 7-8)")
        print("="*60)
        
        results = system.get_near_misses(min_score=7)
        
        for result in results:
            print(format_result_for_display(result))
        
        print(f"\n📊 Found {len(results)} near-miss stocks")
        return
    
    if args.schedule:
        run_scheduler()
        return
    
    # Default: show help
    parser.print_help()
    print("\n" + "="*60)
    print("📋 QUICK START EXAMPLES:")
    print("="*60)
    print("  Test Telegram:     python main.py --test-telegram")
    print("  Quick test:        python main.py --test")
    print("  Full scan:         python main.py --scan")
    print("  Start scheduler:   python main.py --schedule")
    print("  Near misses:       python main.py --near-misses")
    print("  Specific stocks:   python main.py --test --symbols RELIANCE TCS")


if __name__ == "__main__":
    main()
