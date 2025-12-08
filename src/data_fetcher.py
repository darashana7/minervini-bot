"""
Stock Data Fetcher Module
Fetches historical stock data from Yahoo Finance
"""
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config.config import (
    EXCHANGE_SUFFIX, HISTORICAL_DATA_PERIOD, 
    CACHE_DIR, CACHE_DURATION_HOURS
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StockDataFetcher:
    """Fetches and caches stock data from Yahoo Finance"""
    
    def __init__(self):
        self.cache_dir = CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def _get_cache_path(self, symbol: str) -> str:
        """Get cache file path for a symbol"""
        safe_symbol = symbol.replace(".", "_").replace(":", "_")
        return os.path.join(self.cache_dir, f"{safe_symbol}.json")
    
    def _is_cache_valid(self, cache_path: str) -> bool:
        """Check if cache file is still valid"""
        if not os.path.exists(cache_path):
            return False
        
        file_time = datetime.fromtimestamp(os.path.getmtime(cache_path))
        age = datetime.now() - file_time
        return age < timedelta(hours=CACHE_DURATION_HOURS)
    
    def _load_from_cache(self, symbol: str) -> Optional[Dict]:
        """Load data from cache if valid"""
        cache_path = self._get_cache_path(symbol)
        if self._is_cache_valid(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Cache load error for {symbol}: {e}")
        return None
    
    def _save_to_cache(self, symbol: str, data: Dict):
        """Save data to cache"""
        cache_path = self._get_cache_path(symbol)
        try:
            with open(cache_path, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Cache save error for {symbol}: {e}")
    
    def get_nse_symbol(self, symbol: str) -> str:
        """Convert symbol to NSE format for Yahoo Finance"""
        if not symbol.endswith(EXCHANGE_SUFFIX):
            return f"{symbol}{EXCHANGE_SUFFIX}"
        return symbol
    
    def fetch_stock_data(self, symbol: str, period: str = None) -> Optional[pd.DataFrame]:
        """
        Fetch historical OHLCV data for a stock
        
        Args:
            symbol: Stock symbol (e.g., 'RELIANCE' or 'RELIANCE.NS')
            period: Data period (default: 1y)
            
        Returns:
            DataFrame with OHLCV data or None if error
        """
        period = period or HISTORICAL_DATA_PERIOD
        nse_symbol = self.get_nse_symbol(symbol)
        
        try:
            ticker = yf.Ticker(nse_symbol)
            df = ticker.history(period=period)
            
            if df.empty:
                logger.warning(f"No data returned for {nse_symbol}")
                return None
            
            return df
        except Exception as e:
            logger.error(f"Error fetching data for {nse_symbol}: {e}")
            return None
    
    def get_stock_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive stock information including current price,
        52-week high/low, and other metrics
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary with stock info or None if error
        """
        nse_symbol = self.get_nse_symbol(symbol)
        
        # Check cache first
        cached = self._load_from_cache(nse_symbol)
        if cached:
            return cached
        
        # Retry logic for network issues
        max_retries = 3
        for attempt in range(max_retries):
            try:
                ticker = yf.Ticker(nse_symbol)
                info = ticker.info
                
                # Get historical data for calculations
                hist = ticker.history(period="1y")
                
                if hist.empty:
                    logger.warning(f"No historical data for {nse_symbol} (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(1)  # Wait before retry
                        continue
                    return None
                
                # Calculate key values
                current_price = hist['Close'].iloc[-1]
                week_52_high = hist['High'].max()
                week_52_low = hist['Low'].min()
                
                # Calculate SMAs
                sma_50 = hist['Close'].rolling(window=50).mean().iloc[-1] if len(hist) >= 50 else None
                sma_150 = hist['Close'].rolling(window=150).mean().iloc[-1] if len(hist) >= 150 else None
                sma_200 = hist['Close'].rolling(window=200).mean().iloc[-1] if len(hist) >= 200 else None
                
                # Calculate 200-day SMA from 1 month ago
                sma_200_1m_ago = hist['Close'].rolling(window=200).mean().iloc[-22] if len(hist) >= 222 else None
                
                # Convert numpy types to native Python types
                def to_native(val):
                    if val is None:
                        return None
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        return val
                
                result = {
                    "symbol": nse_symbol,
                    "name": info.get("longName", symbol),
                    "current_price": round(to_native(current_price), 2),
                    "week_52_high": round(to_native(week_52_high), 2),
                    "week_52_low": round(to_native(week_52_low), 2),
                    "sma_50": round(to_native(sma_50), 2) if sma_50 is not None else None,
                    "sma_150": round(to_native(sma_150), 2) if sma_150 is not None else None,
                    "sma_200": round(to_native(sma_200), 2) if sma_200 is not None else None,
                    "sma_200_1m_ago": round(to_native(sma_200_1m_ago), 2) if sma_200_1m_ago is not None else None,
                    "percent_from_52w_high": round(to_native((week_52_high - current_price) / week_52_high * 100), 2),
                    "percent_above_52w_low": round(to_native((current_price - week_52_low) / week_52_low * 100), 2),
                    "volume": int(hist['Volume'].iloc[-1]),
                    "avg_volume_20d": int(hist['Volume'].tail(20).mean()),
                    "timestamp": datetime.now().isoformat()
                }
                
                # Cache the result
                self._save_to_cache(nse_symbol, result)
                
                return result
                
            except Exception as e:
                logger.error(f"Error getting info for {nse_symbol} (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(1)  # Wait before retry
                    continue
                return None
        
        return None
    
    def get_historical_prices(self, symbol: str, days: int = 250) -> Optional[pd.DataFrame]:
        """
        Get historical closing prices for SMA calculations
        
        Args:
            symbol: Stock symbol
            days: Number of trading days
            
        Returns:
            DataFrame with date and close price
        """
        nse_symbol = self.get_nse_symbol(symbol)
        
        try:
            ticker = yf.Ticker(nse_symbol)
            # Fetch extra data to ensure we have enough for 200-day SMA
            hist = ticker.history(period="1y")
            
            if hist.empty:
                return None
            
            return hist[['Close', 'High', 'Low', 'Volume']]
            
        except Exception as e:
            logger.error(f"Error getting historical prices for {nse_symbol}: {e}")
            return None


def fetch_all_nse_symbols() -> list:
    """
    Fetch list of all NSE stock symbols
    Uses a combination of sources to get comprehensive list
    """
    symbols = []
    
    # Try to fetch from NSE indices
    indices = ['^NSEI', '^NSEBANK']  # Nifty 50 and Bank Nifty
    
    try:
        # Fetch Nifty 500 components (covers most traded stocks)
        # Since yfinance doesn't directly provide index components,
        # we'll use a predefined list of popular NSE stocks
        
        popular_stocks = [
            # Nifty 50 stocks (sample - full list would be fetched)
            "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
            "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
            "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "TITAN",
            "SUNPHARMA", "ULTRACEMCO", "BAJFINANCE", "WIPRO", "HCLTECH",
            "NESTLEIND", "POWERGRID", "NTPC", "TATAMOTORS", "M&M",
            "ADANIENT", "ADANIPORTS", "BAJAJFINSV", "TATASTEEL", "ONGC",
            "JSWSTEEL", "COALINDIA", "HINDALCO", "GRASIM", "INDUSINDBK",
            "TECHM", "DRREDDY", "CIPLA", "DIVISLAB", "EICHERMOT",
            "BPCL", "HEROMOTOCO", "BRITANNIA", "APOLLOHOSP", "SHREECEM",
            "TATACONSUM", "SBILIFE", "HDFCLIFE", "UPL", "BAJAJ-AUTO"
        ]
        
        symbols.extend(popular_stocks)
        
    except Exception as e:
        logger.error(f"Error fetching NSE symbols: {e}")
    
    return list(set(symbols))


if __name__ == "__main__":
    # Test the data fetcher
    fetcher = StockDataFetcher()
    
    # Test with a popular stock
    print("Testing with RELIANCE...")
    info = fetcher.get_stock_info("RELIANCE")
    if info:
        print(json.dumps(info, indent=2))
    else:
        print("Failed to fetch data")
