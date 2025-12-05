"""Generate formatted stock list"""
import json

# Load alert history
with open('data/alert_history.json', 'r') as f:
    data = json.load(f)

# Print formatted table
print("\n" + "=" * 100)
print("MINERVINI TREND TEMPLATE - QUALIFYING STOCKS (Score 9/9)")
print("Date: 2025-12-05")
print("=" * 100)
print(f"{'#':<4} {'SYMBOL':<15} {'COMPANY NAME':<42} {'PRICE':>10} {'FROM HIGH':>12} {'ABOVE LOW':>12}")
print("-" * 100)

for i, (symbol, info) in enumerate(data.items(), 1):
    details = info['details']
    name = details['name'][:41]
    price = details['current_price']
    from_high = details['metrics']['pct_from_52w_high']
    above_low = details['metrics']['pct_above_52w_low']
    
    print(f"{i:<4} {symbol:<15} {name:<42} ₹{price:>8,.2f} {from_high:>10.1f}% {above_low:>10.1f}%")

print("-" * 100)
print(f"TOTAL: {len(data)} stocks pass all 9 Minervini Trend Template criteria")
print("=" * 100)
