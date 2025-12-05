"""
Alert Management Module
Tracks alert history and prevents duplicate alerts
"""
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config.config import ALERT_HISTORY_FILE, ALERT_COOLDOWN_HOURS, DATA_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AlertManager:
    """Manages alert history and prevents spam"""
    
    def __init__(self, history_file: str = None):
        self.history_file = history_file or ALERT_HISTORY_FILE
        self.cooldown_hours = ALERT_COOLDOWN_HOURS
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Ensure the alert history file exists"""
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        if not os.path.exists(self.history_file):
            self._save_history({})
    
    def _load_history(self) -> Dict:
        """Load alert history from file"""
        try:
            with open(self.history_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    
    def _save_history(self, history: Dict):
        """Save alert history to file"""
        # Convert numpy types to Python native types for JSON serialization
        def convert_to_serializable(obj):
            if isinstance(obj, dict):
                return {k: convert_to_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_to_serializable(i) for i in obj]
            elif hasattr(obj, 'item'):  # numpy types
                return obj.item()
            elif isinstance(obj, bool):
                return bool(obj)
            return obj
        
        serializable_history = convert_to_serializable(history)
        with open(self.history_file, 'w') as f:
            json.dump(serializable_history, f, indent=2, default=str)
    
    def should_alert(self, symbol: str) -> bool:
        """
        Check if we should send an alert for this symbol
        Returns False if we've alerted recently (within cooldown period)
        
        Args:
            symbol: Stock symbol to check
            
        Returns:
            True if alert should be sent, False otherwise
        """
        history = self._load_history()
        
        if symbol not in history:
            return True
        
        last_alert_time = datetime.fromisoformat(history[symbol]['last_alert'])
        time_since_alert = datetime.now() - last_alert_time
        
        return time_since_alert > timedelta(hours=self.cooldown_hours)
    
    def record_alert(self, symbol: str, details: Dict = None):
        """
        Record that an alert was sent for a symbol
        
        Args:
            symbol: Stock symbol
            details: Optional additional details about the alert
        """
        history = self._load_history()
        
        alert_record = {
            'last_alert': datetime.now().isoformat(),
            'alert_count': history.get(symbol, {}).get('alert_count', 0) + 1,
            'details': details or {}
        }
        
        history[symbol] = alert_record
        self._save_history(history)
        
        logger.info(f"Recorded alert for {symbol}")
    
    def get_alert_history(self, symbol: str = None) -> Dict:
        """
        Get alert history for a symbol or all symbols
        
        Args:
            symbol: Optional specific symbol to get history for
            
        Returns:
            Alert history dictionary
        """
        history = self._load_history()
        
        if symbol:
            return history.get(symbol, {})
        return history
    
    def get_recent_alerts(self, hours: int = 24) -> List[Dict]:
        """
        Get all alerts sent in the last N hours
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            List of recent alerts with symbols and timestamps
        """
        history = self._load_history()
        cutoff = datetime.now() - timedelta(hours=hours)
        
        recent = []
        for symbol, data in history.items():
            alert_time = datetime.fromisoformat(data['last_alert'])
            if alert_time > cutoff:
                recent.append({
                    'symbol': symbol,
                    'timestamp': data['last_alert'],
                    'details': data.get('details', {})
                })
        
        # Sort by timestamp (most recent first)
        recent.sort(key=lambda x: x['timestamp'], reverse=True)
        return recent
    
    def clear_old_alerts(self, days: int = 30):
        """
        Remove alerts older than specified days
        
        Args:
            days: Number of days to keep
        """
        history = self._load_history()
        cutoff = datetime.now() - timedelta(days=days)
        
        cleaned = {}
        for symbol, data in history.items():
            alert_time = datetime.fromisoformat(data['last_alert'])
            if alert_time > cutoff:
                cleaned[symbol] = data
        
        removed_count = len(history) - len(cleaned)
        self._save_history(cleaned)
        
        logger.info(f"Cleaned up {removed_count} old alert records")
        return removed_count
    
    def get_statistics(self) -> Dict:
        """Get alert statistics"""
        history = self._load_history()
        
        if not history:
            return {
                'total_symbols_alerted': 0,
                'total_alerts_sent': 0,
                'alerts_last_24h': 0,
                'most_alerted_stocks': []
            }
        
        total_alerts = sum(data.get('alert_count', 0) for data in history.values())
        recent = self.get_recent_alerts(24)
        
        # Get top 5 most alerted stocks
        sorted_by_count = sorted(
            history.items(), 
            key=lambda x: x[1].get('alert_count', 0), 
            reverse=True
        )[:5]
        
        return {
            'total_symbols_alerted': len(history),
            'total_alerts_sent': total_alerts,
            'alerts_last_24h': len(recent),
            'most_alerted_stocks': [
                {'symbol': s, 'count': d.get('alert_count', 0)} 
                for s, d in sorted_by_count
            ]
        }


if __name__ == "__main__":
    # Test the alert manager
    manager = AlertManager()
    
    # Test should_alert
    print("Testing alert manager...")
    
    symbol = "TEST_STOCK"
    
    print(f"Should alert for {symbol}? {manager.should_alert(symbol)}")
    
    # Record an alert
    manager.record_alert(symbol, {"price": 100, "score": 9})
    
    print(f"Should alert again? {manager.should_alert(symbol)}")
    
    # Get statistics
    stats = manager.get_statistics()
    print(f"\nStatistics: {json.dumps(stats, indent=2)}")
