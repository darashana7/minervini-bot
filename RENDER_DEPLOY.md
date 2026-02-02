# 🚀 Deploy Minervini Bot to Render.com (Free Tier)

## ⚠️ Important: Free Tier Limitations
- **Spins down after 15 min of no traffic** - We use an external pinger to fix this
- **750 hours/month** - Enough for 24/7 if you keep it alive
- **May timeout on long scans** - `/fullscan` and `/scanall` may timeout

---

## 📝 Step 1: Push to GitHub

First, push your code to a GitHub repository:

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/minervini-bot.git
git push -u origin main
```

---

## 🌐 Step 2: Deploy on Render

### Option A: Blueprint (Recommended)
1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click **"New +"** → **"Blueprint"**
3. Connect your GitHub repo
4. Render will auto-detect `render.yaml` and deploy!

### Option B: Manual Setup
1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Configure:
   - **Name**: `minervini-bot`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python render_bot.py`
   - **Plan**: Free

5. Add Environment Variables:
   - `BOT_TOKEN` = `8557128929:AAFrPNOsb-T_ygpaqu2MI0DbuZYEA2JT1rg`
   - `MONGO_URI` = (Optional but **HIGHLY RECOMMENDED** - Get from [MongoDB Atlas](#-step-45-set-up-mongodb-atlas-free))

6. Click **"Create Web Service"**

---

## 🍃 Step 4.5: Set Up MongoDB Atlas (FREE) 

**⚠️ IMPORTANT:** Without MongoDB, your data (scan results, alerts, settings) will be **deleted every time Render restarts** (~every 15 minutes on free tier).

**✅ Solution:** Use **MongoDB Atlas FREE tier** (512 MB forever free!)

📖 **Detailed Guide:** See [MONGODB_SETUP.md](./MONGODB_SETUP.md) for complete step-by-step instructions.

**Quick Summary:**
1. Create free account at [mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas)
2. Create M0 FREE cluster (512 MB)
3. Create database user + get connection string
4. Add connection string to Render as `MONGO_URI` environment variable

✨ Once configured, all your bot data will persist forever!

---

## 🔔 Step 3: Set Up Keep-Alive Pinger (CRITICAL!)

Without this, your bot will sleep after 15 minutes of inactivity!

### Option 1: UptimeRobot (Recommended - Free)
1. Go to [UptimeRobot.com](https://uptimerobot.com/) and create free account
2. Click **"Add New Monitor"**
3. Configure:
   - **Monitor Type**: HTTP(s)
   - **Friendly Name**: Minervini Bot
   - **URL**: `https://YOUR-APP-NAME.onrender.com/health`
   - **Monitoring Interval**: 5 minutes
4. Save!

### Option 2: cron-job.org (Free)
1. Go to [cron-job.org](https://cron-job.org/)
2. Create account and add new cron job
3. **URL**: `https://YOUR-APP-NAME.onrender.com/health`
4. **Schedule**: Every 14 minutes

---

## ✅ Step 4: Set Telegram Webhook

After deployment, Render will give you a URL like:
`https://minervini-bot-xxxx.onrender.com`

The bot auto-configures the webhook using `RENDER_EXTERNAL_URL` (Render provides this).

If you need to set it manually:
```
https://api.telegram.org/bot8557128929:AAFrPNOsb-T_ygpaqu2MI0DbuZYEA2JT1rg/setWebhook?url=https://YOUR-APP-NAME.onrender.com/webhook
```

---

## 🧪 Test Your Deployment

1. Visit `https://YOUR-APP-NAME.onrender.com/` - Should show bot status page
2. Visit `https://YOUR-APP-NAME.onrender.com/health` - Should return JSON health status
3. Send `/start` to your bot on Telegram - Should respond!

---

## ⚠️ Known Limitations on Free Tier

| Issue | Workaround |
|-------|------------|
| Bot sleeps after 15 min | Use UptimeRobot to ping every 5 min |
| `/fullscan` may timeout | Use `/scan` for quick scans |
| `/scanall` likely timeout | Not recommended on free tier |
| Cold start delay (~30 sec) | First message after sleep is slow |

---

## 🔧 Troubleshooting

### Bot not responding?
1. Check Render logs: Dashboard → Your Service → Logs
2. Verify webhook is set: Visit `/health` endpoint
3. Make sure UptimeRobot is pinging

### Webhook errors?
Run this in browser to reset webhook:
```
https://api.telegram.org/bot8557128929:AAFrPNOsb-T_ygpaqu2MI0DbuZYEA2JT1rg/setWebhook?url=https://YOUR-APP-NAME.onrender.com/webhook
```

### Check webhook status:
```
https://api.telegram.org/bot8557128929:AAFrPNOsb-T_ygpaqu2MI0DbuZYEA2JT1rg/getWebhookInfo
```

---

## 📊 Files Created for Render

| File | Purpose |
|------|---------|
| `render_bot.py` | Webhook-based bot with Flask server |
| `render.yaml` | Render blueprint configuration |
| `requirements.txt` | Updated with Flask & Gunicorn |

---

## 🎯 Commands Available

**Quick Commands:**
- `/start` - Welcome message
- `/help` - Show help
- `/scan` - Quick scan (top 50 stocks) ✅ Works on free tier
- `/check SYMBOL` - Check specific stock ✅ Works on free tier
- `/list` - Show results
- `/nse` - List all stocks

**Full Scans:**
- `/fullscan` - Nifty 500 scan ⚠️ May timeout
- `/scanall` - All 2000 stocks ⚠️ May timeout
- `/progress` - Check scan progress
- `/stop` - Stop scan
- `/resume` - Resume scan

**Price Alerts:**
- `/alert SYMBOL > PRICE` - Set price alert
- `/alerts` - View active alerts
- `/delalert ID` - Delete alert

**Database (MongoDB):**
- `/db status` - Check MongoDB connection & stats 🍃
- `/db latest` - View latest scan data
- `/db alerts` - View stored alerts
- `/db clear` - Clear all data (admin only)

---

Happy deploying! 🚀
