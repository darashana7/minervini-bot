"""
Google Gemini AI Stock Analyzer
Provides entry/exit level recommendations using Gemini AI
"""
import os
import logging
from google import genai

logger = logging.getLogger(__name__)


class GeminiStockAnalyzer:
    """Analyzes stock data using Google Gemini AI to provide trading recommendations"""
    
    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-3-pro-preview"  # Gemini 3 Pro Preview
    
    def analyze_stock(self, symbol: str, stock_data: dict) -> dict:
        """
        Analyze stock and provide entry/stop-loss levels
        
        Args:
            symbol: Stock symbol (e.g., 'RELIANCE')
            stock_data: Dict with price metrics (current_price, sma_50, sma_150, 
                       sma_200, week_52_high, week_52_low)
        
        Returns:
            Dict with entry_level, stop_loss, target, reasoning
        """
        try:
            prompt = self._build_prompt(symbol, stock_data)
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt
            )
            
            return self._parse_response(response.text)
        except Exception as e:
            logger.error(f"Gemini API error for {symbol}: {e}")
            raise
    
    def _build_prompt(self, symbol: str, data: dict) -> str:
        """Build the analysis prompt for Gemini"""
        return f"""You are a technical stock analyst specializing in Indian NSE stocks. Analyze this stock and provide actionable trading levels.

Stock: {symbol}
Current Price: ₹{data.get('current_price', 0):,.2f}
50-day SMA: ₹{data.get('sma_50', 0):,.2f}
150-day SMA: ₹{data.get('sma_150', 0):,.2f}
200-day SMA: ₹{data.get('sma_200', 0):,.2f}
52-Week High: ₹{data.get('week_52_high', 0):,.2f}
52-Week Low: ₹{data.get('week_52_low', 0):,.2f}

Based on this technical data and Mark Minervini's SEPA methodology, provide:
1. ENTRY_LEVEL: Recommended entry price or range for buying
2. STOP_LOSS: Stop-loss level (typically 7-10% below entry or below key support)
3. TARGET: First profit target (based on risk-reward or resistance)
4. REASONING: Brief 2-3 sentence explanation of your analysis

Format your response EXACTLY like this (use ₹ symbol for prices):
ENTRY_LEVEL: ₹XXXX - ₹XXXX
STOP_LOSS: ₹XXXX
TARGET: ₹XXXX
REASONING: Your brief analysis here."""

    def _parse_response(self, text: str) -> dict:
        """Parse Gemini's response into structured data"""
        result = {
            'entry_level': 'N/A',
            'stop_loss': 'N/A',
            'target': 'N/A',
            'reasoning': 'Unable to parse AI response'
        }
        
        lines = text.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('ENTRY_LEVEL:'):
                result['entry_level'] = line.replace('ENTRY_LEVEL:', '').strip()
            elif line.startswith('STOP_LOSS:'):
                result['stop_loss'] = line.replace('STOP_LOSS:', '').strip()
            elif line.startswith('TARGET:'):
                result['target'] = line.replace('TARGET:', '').strip()
            elif line.startswith('REASONING:'):
                result['reasoning'] = line.replace('REASONING:', '').strip()
        
        return result
