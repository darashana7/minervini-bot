"""Send formatted stock list to all Telegram users"""
import json
import requests

# Config
BOT_TOKEN = "8550797252:AAG_P9X-9RxOQyIz-N2LAHiGJhnBKzAF5W8"
CHAT_IDS = ["718039423", "651048573", "1417534705"]

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    response = requests.post(url, json=data, verify=False)
    return response.json().get('ok', False)

def send_to_all(text):
    for chat_id in CHAT_IDS:
        if send_message(chat_id, text):
            print(f"✓ Sent to {chat_id}")
        else:
            print(f"✗ Failed for {chat_id}")

# Load data
with open('data/alert_history.json', 'r') as f:
    data = json.load(f)

# Sort by price from high percentage
stocks = []
for symbol, info in data.items():
    details = info['details']
    stocks.append({
        'symbol': symbol,
        'name': details['name'],
        'price': details['current_price'],
        'from_high': details['metrics']['pct_from_52w_high']
    })

# Sort by closest to 52-week high
stocks.sort(key=lambda x: x['from_high'])

# Header
header = f"""🎯 <b>MINERVINI TREND TEMPLATE</b>
<b>Eligible Stocks List</b>
📅 {len(stocks)} stocks qualify

Format: # | Symbol | Name | Price
━━━━━━━━━━━━━━━━━━━━━━━━"""

send_to_all(header)
print("Header sent")

# Send in batches of 20
batch_size = 20
for batch_num in range(0, len(stocks), batch_size):
    batch = stocks[batch_num:batch_num + batch_size]
    
    lines = []
    for i, stock in enumerate(batch, batch_num + 1):
        name_short = stock['name'][:25]
        lines.append(f"{i}. <b>{stock['symbol']}</b> | {name_short} | ₹{stock['price']:,.2f}")
    
    message = "\n".join(lines)
    send_to_all(message)
    print(f"Batch {batch_num//batch_size + 1} sent")

# Footer
footer = f"""━━━━━━━━━━━━━━━━━━━━━━━━
✅ <b>Total: {len(stocks)} stocks</b>
All pass 9/9 Minervini criteria

#Minervini #StockAlert"""

send_to_all(footer)
print(f"\n✅ Complete! Sent {len(stocks)} stocks to all users")
