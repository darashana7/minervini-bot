# Mark Minervini Stock Alert System

A Python-based stock screening and alert system implementing Mark Minervini's **SEPA (Specific Entry Point Analysis)** Trend Template criteria to identify high-potential Stage 2 uptrend stocks.

## 🎯 Features

- **Minervini Trend Template Screening**: All 8 criteria implemented
- **Telegram Alerts**: Real-time notifications when stocks qualify
- **Scheduled Scanning**: Automatic hourly scans during market hours
- **NSE Stock Coverage**: 200+ actively traded NSE stocks
- **Smart Alert Management**: Prevents duplicate alerts within 24 hours
- **Near-Miss Detection**: Find stocks close to qualifying

## 📊 Minervini's 8-Point Trend Template

| # | Criterion | Description |
|---|-----------|-------------|
| 1 | Price > 150-day SMA | Current price above 150-day moving average |
| 2 | Price > 200-day SMA | Current price above 200-day moving average |
| 3 | 150 SMA > 200 SMA | 150-day MA above 200-day MA |
| 4 | 200 SMA Uptrend | 200-day MA trending up for 1+ month |
| 5 | 50 SMA > 150 SMA | 50-day MA above 150-day MA |
| 6 | 50 SMA > 200 SMA | 50-day MA above 200-day MA |
| 7 | Price > 50-day SMA | Current price above 50-day MA |
| 8 | ≥30% Above 52W Low | Stock gained significantly from low |
| 9 | Within 25% of 52W High | Stock near its high (strength) |

## 🚀 Quick Start

### 1. Install Dependencies

```powershell
cd d:\Telegram
pip install -r requirements.txt
```

### 2. Test Telegram Connection

```powershell
python main.py --test-telegram
```

### 3. Run a Quick Test

```powershell
python main.py --test
```

### 4. Run Full Scan

```powershell
python main.py --scan
```

### 5. Start Scheduler (24/7 monitoring)

```powershell
python main.py --schedule
```

## 📱 Commands

| Command | Description |
|---------|-------------|
| `--test` | Quick scan on top 20 stocks |
| `--scan` | Full scan of all stocks |
| `--schedule` | Start automated scheduler |
| `--test-telegram` | Test Telegram connection |
| `--near-misses` | Find stocks with score 7-8 |
| `--symbols RELIANCE TCS` | Scan specific stocks |
| `--min-score 8` | Set minimum qualifying score |

## ⏰ Scan Schedule

The system automatically scans at:
- 09:30 (after market open)
- 10:30, 11:30, 12:30, 13:30, 14:30 (hourly)
- 15:45 (after market close)

## 📁 Project Structure

```
d:\Telegram\
├── config/
│   └── config.py           # Configuration settings
├── src/
│   ├── minervini_screener.py   # Core screening logic
│   ├── data_fetcher.py         # Yahoo Finance integration
│   ├── alerts.py               # Alert management
│   ├── telegram_bot.py         # Telegram notifications
│   └── stock_list.py           # NSE stock list
├── data/
│   ├── cache/                  # Cached stock data
│   ├── nse_stocks.csv          # Stock list
│   └── alert_history.json      # Alert history
├── main.py                 # Entry point
├── requirements.txt        # Dependencies
└── README.md               # This file
```

## 🔔 Sample Alert

```
🚀 MINERVINI ALERT: RELIANCE.NS

Reliance Industries Limited
PERFECT MATCH! - Score: 9/9

💰 Current Price: ₹2,456.30

📊 Moving Averages:
• 50-day SMA: ₹2,389.45
• 150-day SMA: ₹2,312.80
• 200-day SMA: ₹2,245.60

📈 52-Week Range:
• High: ₹2,520.00 (2.5% away)
• Low: ₹1,850.00 (32.8% above)

✅ All criteria passed!

#Minervini #TrendTemplate #RELIANCE
```

## ⚙️ Configuration

Edit `config/config.py` to customize:
- Telegram credentials
- Scan schedule
- Alert cooldown period
- Screening thresholds

## 📝 License

MIT License - Feel free to use and modify!

## 🙏 Credits

Based on Mark Minervini's SEPA trading methodology.
