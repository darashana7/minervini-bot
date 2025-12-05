"""
Mark Minervini Trend Template Screener
Implements the 8-point criteria for identifying Stage 2 uptrend stocks
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config.config import (
    MA_PERIODS, MIN_PERCENT_ABOVE_52W_LOW, 
    MAX_PERCENT_FROM_52W_HIGH, MIN_200_SMA_UPTREND_DAYS
)
from src.data_fetcher import StockDataFetcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TrendTemplateResult:
    """Result of Trend Template screening for a stock"""
    symbol: str
    name: str
    passes_all: bool
    current_price: float
    criteria: Dict[str, bool]
    metrics: Dict[str, float]
    score: int  # Number of criteria passed (0-8)
    
    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "passes_all": self.passes_all,
            "current_price": self.current_price,
            "criteria": self.criteria,
            "metrics": self.metrics,
            "score": self.score
        }


class MinerviniScreener:
    """
    Implements Mark Minervini's Trend Template Criteria
    
    The 8 criteria for a stock to be in a Stage 2 uptrend:
    1. Price > 150-day SMA
    2. Price > 200-day SMA
    3. 150-day SMA > 200-day SMA
    4. 200-day SMA trending up for at least 1 month
    5. 50-day SMA > 150-day SMA
    6. 50-day SMA > 200-day SMA
    7. Price > 50-day SMA
    8. Price at least 30% above 52-week low
    9. Price within 25% of 52-week high
    """
    
    def __init__(self):
        self.data_fetcher = StockDataFetcher()
        self.ma_short = MA_PERIODS["short"]    # 50-day
        self.ma_medium = MA_PERIODS["medium"]  # 150-day
        self.ma_long = MA_PERIODS["long"]      # 200-day
    
    def calculate_sma(self, prices: pd.Series, period: int) -> Optional[float]:
        """Calculate Simple Moving Average"""
        if len(prices) < period:
            return None
        return prices.rolling(window=period).mean().iloc[-1]
    
    def calculate_sma_series(self, prices: pd.Series, period: int) -> pd.Series:
        """Calculate SMA as a series for trend analysis"""
        return prices.rolling(window=period).mean()
    
    def is_sma_trending_up(self, prices: pd.Series, sma_period: int, lookback_days: int = 22) -> bool:
        """
        Check if SMA is trending upward over the lookback period
        
        Args:
            prices: Price series
            sma_period: Period for SMA calculation
            lookback_days: Days to look back (default ~1 month of trading days)
        """
        sma_series = self.calculate_sma_series(prices, sma_period)
        
        if len(sma_series) < lookback_days + sma_period:
            return False
        
        # Get SMA values from lookback period ago and now
        current_sma = sma_series.iloc[-1]
        past_sma = sma_series.iloc[-(lookback_days + 1)]
        
        # SMA is trending up if current > past
        return current_sma > past_sma
    
    def check_trend_template(self, symbol: str) -> Optional[TrendTemplateResult]:
        """
        Check if a stock meets all Minervini Trend Template criteria
        
        Args:
            symbol: Stock symbol (e.g., 'RELIANCE')
            
        Returns:
            TrendTemplateResult with detailed pass/fail for each criterion
        """
        # Fetch stock info
        info = self.data_fetcher.get_stock_info(symbol)
        if not info:
            logger.warning(f"Could not fetch data for {symbol}")
            return None
        
        # Get historical data for trend analysis
        hist = self.data_fetcher.get_historical_prices(symbol)
        if hist is None or len(hist) < 200:
            logger.warning(f"Insufficient historical data for {symbol}")
            return None
        
        prices = hist['Close']
        
        # Extract values
        current_price = info['current_price']
        sma_50 = info['sma_50']
        sma_150 = info['sma_150']
        sma_200 = info['sma_200']
        week_52_high = info['week_52_high']
        week_52_low = info['week_52_low']
        
        # Skip if any SMA is missing
        if None in [sma_50, sma_150, sma_200]:
            logger.warning(f"Missing SMA data for {symbol}")
            return None
        
        # Calculate percentages
        pct_above_52w_low = ((current_price - week_52_low) / week_52_low) * 100
        pct_from_52w_high = ((week_52_high - current_price) / week_52_high) * 100
        
        # Check each criterion
        criteria = {
            "1_price_above_150sma": current_price > sma_150,
            "2_price_above_200sma": current_price > sma_200,
            "3_150sma_above_200sma": sma_150 > sma_200,
            "4_200sma_trending_up": self.is_sma_trending_up(prices, 200, MIN_200_SMA_UPTREND_DAYS),
            "5_50sma_above_150sma": sma_50 > sma_150,
            "6_50sma_above_200sma": sma_50 > sma_200,
            "7_price_above_50sma": current_price > sma_50,
            "8_price_30pct_above_52w_low": pct_above_52w_low >= MIN_PERCENT_ABOVE_52W_LOW,
            "9_price_within_25pct_of_52w_high": pct_from_52w_high <= MAX_PERCENT_FROM_52W_HIGH
        }
        
        # Calculate score and check if all pass
        score = sum(criteria.values())
        passes_all = all(criteria.values())
        
        # Collect metrics
        metrics = {
            "current_price": current_price,
            "sma_50": sma_50,
            "sma_150": sma_150,
            "sma_200": sma_200,
            "week_52_high": week_52_high,
            "week_52_low": week_52_low,
            "pct_above_52w_low": round(pct_above_52w_low, 2),
            "pct_from_52w_high": round(pct_from_52w_high, 2),
            "volume": info.get('volume', 0),
            "avg_volume_20d": info.get('avg_volume_20d', 0)
        }
        
        return TrendTemplateResult(
            symbol=symbol,
            name=info.get('name', symbol),
            passes_all=passes_all,
            current_price=current_price,
            criteria=criteria,
            metrics=metrics,
            score=score
        )
    
    def scan_stocks(self, symbols: List[str], min_score: int = 9) -> List[TrendTemplateResult]:
        """
        Scan multiple stocks and return those meeting criteria
        
        Args:
            symbols: List of stock symbols to scan
            min_score: Minimum score to include (default 9 = all criteria)
            
        Returns:
            List of TrendTemplateResult for qualifying stocks
        """
        results = []
        total = len(symbols)
        
        for i, symbol in enumerate(symbols):
            logger.info(f"Scanning {symbol} ({i+1}/{total})...")
            
            try:
                result = self.check_trend_template(symbol)
                if result and result.score >= min_score:
                    results.append(result)
                    logger.info(f"✅ {symbol} PASSES with score {result.score}/9")
            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")
                continue
        
        # Sort by score (highest first)
        results.sort(key=lambda x: (x.score, -x.metrics['pct_from_52w_high']), reverse=True)
        
        return results
    
    def get_near_misses(self, symbols: List[str], min_score: int = 7) -> List[TrendTemplateResult]:
        """
        Find stocks that are close to meeting all criteria (near misses)
        Useful for watchlist building
        
        Args:
            symbols: List of stock symbols
            min_score: Minimum score for near miss (default 7 = failing 2 criteria)
        """
        results = []
        
        for symbol in symbols:
            try:
                result = self.check_trend_template(symbol)
                if result and min_score <= result.score < 9:
                    results.append(result)
            except Exception as e:
                logger.error(f"Error checking {symbol}: {e}")
                continue
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results


def format_result_for_display(result: TrendTemplateResult) -> str:
    """Format a screening result for console display"""
    lines = [
        f"\n{'='*50}",
        f"📈 {result.symbol} - {result.name}",
        f"{'='*50}",
        f"Score: {result.score}/9 {'✅ PASSES' if result.passes_all else '❌ FAILS'}",
        f"\n💰 Price: ₹{result.current_price:,.2f}",
        f"\n📊 Moving Averages:",
        f"   50-day SMA:  ₹{result.metrics['sma_50']:,.2f}",
        f"   150-day SMA: ₹{result.metrics['sma_150']:,.2f}",
        f"   200-day SMA: ₹{result.metrics['sma_200']:,.2f}",
        f"\n📉 52-Week Range:",
        f"   High: ₹{result.metrics['week_52_high']:,.2f} ({result.metrics['pct_from_52w_high']:.1f}% away)",
        f"   Low:  ₹{result.metrics['week_52_low']:,.2f} ({result.metrics['pct_above_52w_low']:.1f}% above)",
        f"\n✓ Criteria Status:"
    ]
    
    criteria_names = {
        "1_price_above_150sma": "Price > 150-day SMA",
        "2_price_above_200sma": "Price > 200-day SMA",
        "3_150sma_above_200sma": "150-day SMA > 200-day SMA",
        "4_200sma_trending_up": "200-day SMA trending up",
        "5_50sma_above_150sma": "50-day SMA > 150-day SMA",
        "6_50sma_above_200sma": "50-day SMA > 200-day SMA",
        "7_price_above_50sma": "Price > 50-day SMA",
        "8_price_30pct_above_52w_low": "Price ≥ 30% above 52-week low",
        "9_price_within_25pct_of_52w_high": "Price within 25% of 52-week high"
    }
    
    for key, passed in result.criteria.items():
        status = "✅" if passed else "❌"
        name = criteria_names.get(key, key)
        lines.append(f"   {status} {name}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Test the screener
    screener = MinerviniScreener()
    
    # Test with sample stocks
    test_symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
    
    print("\n🔍 Minervini Trend Template Screener Test\n")
    
    for symbol in test_symbols:
        result = screener.check_trend_template(symbol)
        if result:
            print(format_result_for_display(result))
        else:
            print(f"\n❌ Could not analyze {symbol}")
