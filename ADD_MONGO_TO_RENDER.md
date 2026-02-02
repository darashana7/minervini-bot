# 🚀 Quick Guide: Add MongoDB to Render

## ✅ Your MongoDB Connection String (Corrected)

**IMPORTANT:** I removed the angle brackets `< >` from your password!

```
mongodb+srv://darashana32_db_user:avvD8I3I2tLHHs8S@minirvini.jcvbl8x.mongodb.net/?appName=minirvini
```

---

## 📝 Add to Render (3 Steps)

### Step 1: Go to Render Dashboard
1. Visit: [https://dashboard.render.com/](https://dashboard.render.com/)
2. Click on your **minervini-bot** service

### Step 2: Add Environment Variable
1. Click **"Environment"** in the left sidebar
2. Click **"Add Environment Variable"** button
3. Fill in:
   - **Key:** `MONGO_URI`
   - **Value:** `mongodb+srv://darashana32_db_user:avvD8I3I2tLHHs8S@minirvini.jcvbl8x.mongodb.net/?appName=minirvini`
4. Click **"Save Changes"**

### Step 3: Wait for Restart
- Render will automatically restart your service
- This takes ~2-3 minutes
- Check logs for: `✅ MongoDB connected successfully (FREE TIER optimized)`

---

## 🧪 Test the Connection

### In Telegram, send:
```
/db status
```

### Expected Response:
```
🍃 MongoDB Database Status

✅ MongoDB: Connected

📊 Collections:
  • Scan Results: 0 doc(s)
  • Scan State: 0 doc(s)
  • Price Alerts: 0 doc(s)
  • Bot Settings: 0 doc(s)

💾 Size: 0.00 MB / 512 MB (free tier)

🔥 Memory Cache:
  • Active entries: X
```

---

## ✅ Success Confirmation

Once you see "✅ MongoDB: Connected", your data is now **persistent**! 

✨ **No more data loss on Render restarts!**

---

## 🛠️ Troubleshooting

### If you see "Connection Failed"

1. **Check Render Logs:**
   - Dashboard → Your Service → Logs
   - Look for error messages

2. **Verify Password:**
   - Make sure there are NO angle brackets `< >`
   - Password should be: `avvD8I3I2tLHHs8S`

3. **Check MongoDB Network Access:**
   - Atlas Dashboard → Network Access
   - Should have `0.0.0.0/0` entry

4. **Check Database User:**
   - Atlas Dashboard → Database Access
   - User: `darashana32_db_user` should exist

---

## 🎯 Next Steps

After MongoDB is connected:

1. ✅ Run `/scan` - Results will be saved to MongoDB
2. ✅ Run `/db latest` - View saved results
3. ✅ Set alerts with `/alert RELIANCE > 3000` - Alerts persist forever
4. ✅ Enable daily scans with `/autodaily on` - Settings saved to DB

---

Happy deploying! 🚀 Your bot is now production-ready with persistent storage!
