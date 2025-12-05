"""
Validate all NSE stocks from CSV against Yahoo Finance
Keep only stocks that have data available
"""
import csv
import yfinance as yf
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

CSV_FILE = "India_Stock_Market_Tracker_v2.0 - Sheet8 (1).csv"
OUTPUT_FILE = "data/valid_nse_stocks.json"

def check_stock(symbol):
    """Check if stock has data on Yahoo Finance"""
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        hist = ticker.history(period="5d")
        if not hist.empty and len(hist) > 0:
            return symbol, True, hist['Close'].iloc[-1]
        return symbol, False, None
    except Exception as e:
        return symbol, False, None

def load_stocks_from_csv():
    """Load all symbols from CSV"""
    symbols = []
    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if row and row[0]:
                symbol = row[0].replace('.NS', '').strip()
                if symbol and not symbol.endswith('-RE'):
                    symbols.append(symbol)
    return symbols

def main():
    print("Loading stocks from CSV...")
    all_stocks = load_stocks_from_csv()
    print(f"Total stocks in CSV: {len(all_stocks)}")
    
    valid_stocks = []
    invalid_stocks = []
    
    print("\nValidating stocks with Yahoo Finance...")
    print("This will take some time...\n")
    
    batch_size = 50
    total = len(all_stocks)
    
    for i in range(0, total, batch_size):
        batch = all_stocks[i:i+batch_size]
        print(f"Checking batch {i//batch_size + 1}/{(total//batch_size)+1} ({i+1}-{min(i+batch_size, total)}/{total})...")
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(check_stock, symbol): symbol for symbol in batch}
            
            for future in as_completed(futures):
                symbol, is_valid, price = future.result()
                if is_valid:
                    valid_stocks.append(symbol)
                else:
                    invalid_stocks.append(symbol)
        
        # Show progress
        print(f"  ✓ Valid: {len(valid_stocks)}, ✗ Invalid: {len(invalid_stocks)}")
        time.sleep(1)  # Rate limiting
    
    # Save valid stocks
    result = {
        "total_csv": len(all_stocks),
        "valid_count": len(valid_stocks),
        "invalid_count": len(invalid_stocks),
        "valid_stocks": sorted(valid_stocks),
        "invalid_stocks": sorted(invalid_stocks)
    }
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\n" + "="*50)
    print(f"VALIDATION COMPLETE!")
    print(f"="*50)
    print(f"Total stocks in CSV:     {len(all_stocks)}")
    print(f"Valid (have data):       {len(valid_stocks)}")
    print(f"Invalid (no data):       {len(invalid_stocks)}")
    print(f"\nResults saved to: {OUTPUT_FILE}")
    
    # Show some invalid stocks
    print(f"\nSample invalid stocks: {invalid_stocks[:20]}")

if __name__ == "__main__":
    main()
