"""
Load NSE stocks from CSV file - All 2200+ stocks
"""
import csv
import os
import logging

logger = logging.getLogger(__name__)

# Path to CSV file
CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                        "India_Stock_Market_Tracker_v2.0 - Sheet8 (1).csv")

def load_stocks_from_csv():
    """Load all NSE stock symbols from CSV file"""
    symbols = []
    
    try:
        with open(CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if row and row[0]:
                    symbol = row[0].replace('.NS', '').strip()
                    # Skip empty symbols and rights issues
                    if symbol and not symbol.endswith('-RE') and symbol:
                        symbols.append(symbol)
        
        logger.info(f"Loaded {len(symbols)} stocks from CSV")
        return symbols
        
    except FileNotFoundError:
        logger.warning(f"CSV file not found: {CSV_PATH}")
        return []
    except Exception as e:
        logger.error(f"Error loading CSV: {e}")
        return []


def get_all_nse_stocks():
    """Get all NSE stocks from CSV"""
    stocks = load_stocks_from_csv()
    if stocks:
        return stocks
    
    # Fallback to basic list if CSV not found
    from src.stock_list import get_nse_stock_list
    return get_nse_stock_list()


def get_nse_stock_count():
    """Get count of available NSE stocks"""
    return len(get_all_nse_stocks())


def get_stock_info():
    """Get stock symbols with their names"""
    stock_info = {}
    
    try:
        with open(CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if row and len(row) >= 2:
                    symbol = row[0].replace('.NS', '').strip()
                    name = row[1].strip() if row[1] else symbol
                    if symbol and not symbol.endswith('-RE'):
                        stock_info[symbol] = name
        return stock_info
    except:
        return {}


if __name__ == "__main__":
    stocks = get_all_nse_stocks()
    print(f"Total NSE stocks: {len(stocks)}")
    print(f"First 20: {stocks[:20]}")
