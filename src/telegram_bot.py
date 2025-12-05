"""
Telegram Bot Module
Sends alerts via Telegram
"""
import requests
from typing import Optional, Dict
import logging
import os
import sys
import ssl
import urllib3

# Disable SSL warnings for problematic certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_CHAT_IDS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TelegramBot:
    """Handles Telegram notifications"""
    
    def __init__(self, token: str = None, chat_ids: list = None):
        self.token = token or TELEGRAM_BOT_TOKEN
        self.chat_ids = chat_ids or TELEGRAM_CHAT_IDS
        self.api_base = f"https://api.telegram.org/bot{self.token}"
    
    def _send_request(self, method: str, data: Dict) -> Dict:
        """Send request to Telegram API"""
        url = f"{self.api_base}/{method}"
        
        try:
            response = requests.post(url, json=data, timeout=30, verify=False)
            result = response.json()
            if not result.get('ok'):
                logger.error(f"Telegram API error: {result}")
            return result
        except Exception as e:
            logger.error(f"Request error: {e}")
            return {'ok': False, 'error': str(e)}
    
    def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """
        Send a message to ALL configured Telegram users
        
        Args:
            message: Message text (supports HTML formatting)
            parse_mode: Parse mode (HTML or Markdown)
            
        Returns:
            True if successful for at least one user
        """
        success = False
        for chat_id in self.chat_ids:
            data = {
                "chat_id": chat_id.strip(),
                "text": message,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            
            try:
                result = self._send_request("sendMessage", data)
                if result.get('ok', False):
                    success = True
                    logger.info(f"Message sent to {chat_id}")
                else:
                    logger.error(f"Failed to send to {chat_id}")
            except Exception as e:
                logger.error(f"Error sending to {chat_id}: {e}")
        
        return success
    
    def send_alert(self, result: Dict) -> bool:
        """
        Send a formatted stock alert
        
        Args:
            result: TrendTemplateResult dictionary
            
        Returns:
            True if successful
        """
        message = self._format_alert_message(result)
        return self.send_message(message)
    
    def _format_alert_message(self, result: Dict) -> str:
        """Format a stock screening result as a Telegram message"""
        
        # Determine emoji based on score
        if result['score'] == 9:
            status_emoji = "🚀"
            status_text = "PERFECT MATCH!"
        elif result['score'] >= 7:
            status_emoji = "⚡"
            status_text = "NEAR MATCH"
        else:
            status_emoji = "📊"
            status_text = "PARTIAL MATCH"
        
        # Build the message
        message = f"""
{status_emoji} <b>MINERVINI ALERT: {result['symbol']}</b>

<b>{result.get('name', result['symbol'])}</b>
{status_text} - Score: {result['score']}/9

💰 <b>Current Price:</b> ₹{result['current_price']:,.2f}

📊 <b>Moving Averages:</b>
• 50-day SMA: ₹{result['metrics']['sma_50']:,.2f}
• 150-day SMA: ₹{result['metrics']['sma_150']:,.2f}
• 200-day SMA: ₹{result['metrics']['sma_200']:,.2f}

📈 <b>52-Week Range:</b>
• High: ₹{result['metrics']['week_52_high']:,.2f} ({result['metrics']['pct_from_52w_high']:.1f}% away)
• Low: ₹{result['metrics']['week_52_low']:,.2f} ({result['metrics']['pct_above_52w_low']:.1f}% above)

<b>Criteria Status:</b>
"""
        # Add criteria status
        criteria_icons = {
            True: "✅",
            False: "❌"
        }
        
        criteria_labels = {
            "1_price_above_150sma": "Price > 150 SMA",
            "2_price_above_200sma": "Price > 200 SMA",
            "3_150sma_above_200sma": "150 SMA > 200 SMA",
            "4_200sma_trending_up": "200 SMA ↗️ Uptrend",
            "5_50sma_above_150sma": "50 SMA > 150 SMA",
            "6_50sma_above_200sma": "50 SMA > 200 SMA",
            "7_price_above_50sma": "Price > 50 SMA",
            "8_price_30pct_above_52w_low": "≥30% above 52W Low",
            "9_price_within_25pct_of_52w_high": "Within 25% of 52W High"
        }
        
        for key, passed in result['criteria'].items():
            icon = criteria_icons[passed]
            label = criteria_labels.get(key, key)
            message += f"{icon} {label}\n"
        
        message += f"\n#Minervini #TrendTemplate #{result['symbol'].replace('.NS', '')}"
        
        return message.strip()
    
    def send_scan_summary(self, results: list, scan_time: str) -> bool:
        """
        Send a summary of the screening scan
        
        Args:
            results: List of stocks that passed
            scan_time: Time of the scan
            
        Returns:
            True if successful
        """
        if not results:
            message = f"""
📊 <b>Minervini Scan Complete</b>

⏰ Scan Time: {scan_time}
📈 Stocks Found: 0

No stocks currently meet all Trend Template criteria.
            """
        else:
            symbols_list = "\n".join([f"• {r['symbol']} (Score: {r['score']}/9)" for r in results[:10]])
            message = f"""
🎯 <b>Minervini Scan Complete</b>

⏰ Scan Time: {scan_time}
📈 Stocks Found: {len(results)}

<b>Top Results:</b>
{symbols_list}

{"..." if len(results) > 10 else ""}

#MinerviniScan #StockAlert
            """
        
        return self.send_message(message.strip())
    
    async def test_connection(self) -> bool:
        """Test the Telegram bot connection"""
        try:
            result = await self._send_request("getMe", {})
            if result.get('ok'):
                bot_info = result.get('result', {})
                logger.info(f"Connected to bot: @{bot_info.get('username')}")
                return True
            return False
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False


def send_test_alert():
    """Send a test alert to verify Telegram setup"""
    bot = TelegramBot()
    
    test_message = """
🧪 <b>Test Alert</b>

Minervini Stock Alert System is working!

✅ Bot connection successful
✅ Message delivery confirmed

Your alerts will be sent to this chat.
    """
    
    success = bot.send_message(test_message.strip())
    
    if success:
        print("✅ Test message sent successfully!")
    else:
        print("❌ Failed to send test message")
    
    return success


if __name__ == "__main__":
    # Test the Telegram bot
    print("Testing Telegram bot connection...")
    send_test_alert()
