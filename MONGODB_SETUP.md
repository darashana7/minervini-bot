# 🍃 MongoDB Atlas Setup Guide (Free Tier)

This guide walks you through setting up a **FREE MongoDB Atlas cluster** for persistent data storage with your Minervini Telegram Bot on Render.

---

## 🎯 Why MongoDB Atlas?

- ✅ **512 MB storage FREE forever**
- ✅ **No credit card required**
- ✅ **Works perfectly with Render free tier**
- ✅ **Automatic backups**
- ✅ **Your data persists even when Render restarts**

Without MongoDB, your bot's data (scan results, alerts, settings) will be **deleted every time Render restarts** (every ~15 minutes on free tier).

---

## 📝 Step 1: Create a Free MongoDB Atlas Account

1. Go to [mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas)
2. Click **"Try Free"** or **"Sign Up"**
3. Sign up with:
   - Google account (easiest), OR
   - Email + password

---

## 🏗️ Step 2: Create a Free Cluster

1. After logging in, click **"Build a Database"**
2. Choose **"M0 FREE"** tier:
   - **Provider:** AWS (recommended) or Google Cloud
   - **Region:** Choose closest to your location (e.g., Mumbai for India, Singapore for Asia)
   - **Cluster Name:** Leave as default or name it `minervini-bot`
3. Click **"Create Deployment"**

⏱️ **Wait 1-3 minutes** for the cluster to be created.

---

## 🔐 Step 3: Create Database User

1. A popup will appear: **"Create a database user"**
2. **Username:** `bot_user` (or any name you like)
3. **Password:** Click **"Autogenerate Secure Password"** and **COPY IT** (save it somewhere safe!)
   - Example: `Xy9kP2mQ7vR8`
4. Click **"Create Database User"**

---

## 🌐 Step 4: Whitelist IP Address

1. In the same popup, scroll to **"Where would you like to connect from?"**
2. Select **"Cloud Environment"**
3. Click **"Add Entry"**
4. In the IP Address field, enter: `0.0.0.0/0`
   - This allows connections from anywhere (safe because you have username/password)
5. Click **"Add Entry"**
6. Click **"Finish and Close"**

---

## 🔗 Step 5: Get Your Connection String

1. In your Atlas dashboard, click **"Connect"** button on your cluster
2. Choose **"Drivers"**
3. Select:
   - **Driver:** Python
   - **Version:** 3.12 or later
4. **Copy the connection string** - it looks like this:

```
mongodb+srv://bot_user:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
```

5. **IMPORTANT:** Replace `<password>` with your actual password from Step 3!

**Example:**
```
mongodb+srv://bot_user:Xy9kP2mQ7vR8@cluster0.abc123.mongodb.net/?retryWrites=true&w=majority
```

---

## 🚀 Step 6: Add to Render Environment Variables

1. Go to your [Render Dashboard](https://dashboard.render.com/)
2. Click on your **minervini-bot** service
3. Go to **"Environment"** tab (left sidebar)
4. Click **"Add Environment Variable"**
5. Add:
   - **Key:** `MONGO_URI`
   - **Value:** Paste your connection string (with password filled in)
6. Click **"Save Changes"**

🔄 **Render will automatically restart your service** with the new environment variable.

---

## ✅ Step 7: Verify Connection

1. In Telegram, send `/start` to your bot
2. Check Render logs (Dashboard → Your Service → Logs)
3. You should see:
   ```
   ✅ MongoDB connected successfully (FREE TIER optimized)
   ```

4. Test the database with `/db status` command in Telegram:
   ```
   /db status
   ```
   
   You should see:
   ```
   🍃 MongoDB: ✅ Connected
   📊 Collections:
   - scan_results: X documents
   - scan_state: X documents
   - price_alerts: X documents
   ```

---

## 🖥️ Bonus: View Your Data with MongoDB Compass (GUI)

MongoDB Compass is a **free graphical tool** to view and manage your database.

### Download & Install
1. Download from: [mongodb.com/try/download/compass](https://www.mongodb.com/try/download/compass)
2. Install it (Windows/Mac/Linux)

### Connect to Your Database
1. Open MongoDB Compass
2. Click **"New Connection"**
3. Paste your connection string (same one from Step 5)
4. Click **"Connect"**

### View Your Data
- You'll see your database (usually named after your cluster)
- Click on collections like:
  - `scan_results` - See all stock scan results
  - `price_alerts` - View active alerts
  - `bot_settings` - Check scheduled scan settings

📸 **Screenshot:** You can now see all your bot's data in a beautiful GUI!

---

## 🛠️ Troubleshooting

### "MongoServerError: bad auth"
- ❌ Wrong password in connection string
- ✅ Copy the exact password from Step 3 and replace `<password>`

### "Connection timeout"
- ❌ IP not whitelisted
- ✅ Add `0.0.0.0/0` in Network Access (Step 4)

### Bot still uses JSON files
- ❌ `MONGO_URI` not set or has typo
- ✅ Check Environment Variables in Render (exact key: `MONGO_URI`)

### Check Render Logs
```
Dashboard → Your Service → Logs
```
Look for:
- ✅ `MongoDB connected successfully`
- ❌ `MongoDB connection failed: [error message]`

---

## 📊 What Gets Stored in MongoDB?

Your bot stores these collections:

| Collection | Description | Size Est. |
|------------|-------------|-----------|
| `scan_results` | Latest scan results (quick/fullscan/scanall) | ~50-500 KB |
| `scan_state` | Current scan progress (for resume) | ~1 KB |
| `price_alerts` | User price alerts | ~10 KB |
| `bot_settings` | Daily scan schedule settings | ~1 KB |

**Total:** Under 1 MB for typical usage (Free tier: 512 MB! 🎉)

---

## 🔒 Security Best Practices

1. ✅ **Never commit** your `MONGO_URI` to GitHub
2. ✅ Use strong, auto-generated passwords
3. ✅ Keep your connection string in Render Environment Variables only
4. ✅ Regularly check Atlas **"Metrics"** tab for unusual activity

---

## 🎓 Learn More

- [MongoDB Atlas Documentation](https://docs.atlas.mongodb.com/)
- [MongoDB Compass Guide](https://www.mongodb.com/docs/compass/current/)
- [Python PyMongo Tutorial](https://pymongo.readthedocs.io/)

---

## 🆘 Need Help?

**Atlas Dashboard:** [cloud.mongodb.com](https://cloud.mongodb.com/)

**Support:**
- MongoDB Community Forums: [mongodb.com/community/forums](https://www.mongodb.com/community/forums/)
- Render Support: [render.com/docs](https://render.com/docs)

---

Happy deploying! 🚀 Your data is now safe and persistent!
