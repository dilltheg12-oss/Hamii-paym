import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from threading import Thread
import time

# =========================================
# KEEP ALIVE WEB SERVER
# =========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running successfully!"

def run_web():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# =========================================
# ENV VARIABLES
# =========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
UPI_ID = os.getenv("UPI_ID")
CONTACT_USERNAME = os.getenv("CONTACT_USERNAME")

# =========================================
# TELEGRAM BOT
# =========================================
bot = telebot.TeleBot(BOT_TOKEN)

# =========================================
# MONGODB
# =========================================
client = MongoClient(MONGO_URI)

db = client["sub_management"]

channels_col = db["channels"]
users_col = db["users"]

# =========================================
# START COMMAND
# =========================================
@bot.message_handler(commands=['start'])
def start_handler(message):

    user_id = message.from_user.id
    text = message.text.split()

    # =====================================
    # USER JOIN FLOW
    # =====================================
    if len(text) > 1:

        try:

            ch_id = int(text[1])

            ch_data = channels_col.find_one({
                "channel_id": ch_id
            })

            if ch_data:

                markup = InlineKeyboardMarkup()

                for p_time, p_price in ch_data["plans"].items():

                    mins = int(p_time)

                    if mins < 60:
                        label = f"{mins} Minutes"

                    elif mins < 1440:
                        label = f"{mins // 60} Hours"

                    else:
                        label = f"{mins // 1440} Days"

                    markup.add(
                        InlineKeyboardButton(
                            f"💳 {label} - ₹{p_price}",
                            callback_data=f"select_{ch_id}_{p_time}"
                        )
                    )

                markup.add(
                    InlineKeyboardButton(
                        "📞 Contact Admin",
                        url=f"https://t.me/{CONTACT_USERNAME}"
                    )
                )

                bot.send_message(
                    message.chat.id,
                    f"🔥 *Welcome!*\n\n"
                    f"📢 Channel: *{ch_data['name']}*\n\n"
                    f"Select your subscription plan below.",
                    parse_mode="Markdown",
                    reply_markup=markup
                )

                return

        except Exception as e:
            print("Start Error:", e)

    # =====================================
    # ADMIN PANEL
    # =====================================
    if user_id == ADMIN_ID:

        bot.send_message(
            message.chat.id,
            "✅ *Admin Panel*\n\n"
            "/add - Add/Edit Channel\n"
            "/channels - Manage Channels",
            parse_mode="Markdown"
        )

    else:

        bot.send_message(
            message.chat.id,
            "⚠️ Invalid Invite Link."
        )

# =========================================
# SHOW CHANNELS
# =========================================
@bot.message_handler(commands=['channels'])
def list_channels(message):

    if message.from_user.id != ADMIN_ID:
        return

    markup = InlineKeyboardMarkup()

    channels = channels_col.find({
        "admin_id": ADMIN_ID
    })

    count = 0

    for ch in channels:

        markup.add(
            InlineKeyboardButton(
                f"📢 {ch['name']}",
                callback_data=f"manage_{ch['channel_id']}"
            )
        )

        count += 1

    markup.add(
        InlineKeyboardButton(
            "➕ Add New Channel",
            callback_data="add_new"
        )
    )

    if count == 0:

        bot.send_message(
            ADMIN_ID,
            "❌ No channels added yet.",
            reply_markup=markup
        )

    else:

        bot.send_message(
            ADMIN_ID,
            "📂 Your Channels:",
            reply_markup=markup
        )

# =========================================
# ADD CHANNEL
# =========================================
@bot.message_handler(commands=['add'])
def add_channel(message):

    if message.from_user.id != ADMIN_ID:
        return

    msg = bot.send_message(
        ADMIN_ID,
        "📩 Forward any message from your channel."
    )

    bot.register_next_step_handler(msg, get_plans)

# =========================================
# ADD NEW CALLBACK
# =========================================
@bot.callback_query_handler(func=lambda call: call.data == "add_new")
def add_new_callback(call):

    bot.answer_callback_query(call.id)

    msg = bot.send_message(
        ADMIN_ID,
        "📩 Forward any message from your channel."
    )

    bot.register_next_step_handler(msg, get_plans)

# =========================================
# GET PLANS
# =========================================
def get_plans(message):

    if message.forward_from_chat:

        ch_id = message.forward_from_chat.id
        ch_name = message.forward_from_chat.title

        msg = bot.send_message(
            ADMIN_ID,
            f"✅ Channel Detected: *{ch_name}*\n\n"
            f"Send plans like:\n\n"
            f"`1440:99, 43200:199`\n\n"
            f"1440 = 1 Day\n"
            f"43200 = 30 Days",
            parse_mode="Markdown"
        )

        bot.register_next_step_handler(
            msg,
            finalize_channel,
            ch_id,
            ch_name
        )

    else:

        bot.send_message(
            ADMIN_ID,
            "❌ Forwarded message not detected."
        )

# =========================================
# SAVE CHANNEL
# =========================================
def finalize_channel(message, ch_id, ch_name):

    try:

        raw_plans = message.text.split(',')

        plans_dict = {}

        for plan in raw_plans:

            t, p = plan.strip().split(':')

            plans_dict[t] = p

        channels_col.update_one(
            {
                "channel_id": ch_id
            },
            {
                "$set": {
                    "name": ch_name,
                    "plans": plans_dict,
                    "admin_id": ADMIN_ID
                }
            },
            upsert=True
        )

        bot_username = bot.get_me().username

        bot.send_message(
            ADMIN_ID,
            f"✅ *Channel Saved Successfully!*\n\n"
            f"🔗 Invite Link:\n"
            f"`https://t.me/{bot_username}?start={ch_id}`",
            parse_mode="Markdown"
        )

    except Exception as e:

        print("Plan Error:", e)

        bot.send_message(
            ADMIN_ID,
            "❌ Invalid format."
        )

# =========================================
# USER PAYMENT
# =========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_"))
def user_payment(call):

    _, ch_id, mins = call.data.split('_')

    ch_data = channels_col.find_one({
        "channel_id": int(ch_id)
    })

    price = ch_data["plans"][mins]

    qr_url = (
        f"https://api.qrserver.com/v1/create-qr-code/"
        f"?size=300x300&data="
        f"upi://pay?pa={UPI_ID}%26am={price}%26cu=INR"
    )

    markup = InlineKeyboardMarkup()

    markup.add(
        InlineKeyboardButton(
            "✅ I Have Paid",
            callback_data=f"paid_{ch_id}_{mins}"
        )
    )

    markup.add(
        InlineKeyboardButton(
            "📞 Contact Admin",
            url=f"https://t.me/{CONTACT_USERNAME}"
        )
    )

    bot.send_photo(
        call.message.chat.id,
        qr_url,
        caption=
        f"💳 Plan: {mins} Minutes\n"
        f"💰 Amount: ₹{price}\n"
        f"🏦 UPI ID: `{UPI_ID}`\n\n"
        f"After payment click below button.",
        parse_mode="Markdown",
        reply_markup=markup
    )

# =========================================
# PAYMENT REQUEST TO ADMIN
# =========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("paid_"))
def payment_request(call):

    _, ch_id, mins = call.data.split('_')

    user = call.from_user

    ch_data = channels_col.find_one({
        "channel_id": int(ch_id)
    })

    price = ch_data["plans"][mins]

    markup = InlineKeyboardMarkup()

    markup.add(
        InlineKeyboardButton(
            "✅ Approve",
            callback_data=f"app_{user.id}_{ch_id}_{mins}"
        )
    )

    markup.add(
        InlineKeyboardButton(
            "❌ Reject",
            callback_data=f"rej_{user.id}"
        )
    )

    bot.send_message(
        ADMIN_ID,
        f"🔔 *Payment Verification*\n\n"
        f"👤 User: {user.first_name}\n"
        f"🆔 ID: `{user.id}`\n"
        f"📢 Channel: {ch_data['name']}\n"
        f"⏳ Plan: {mins} Minutes\n"
        f"💰 Amount: ₹{price}",
        parse_mode="Markdown",
        reply_markup=markup
    )

    bot.send_message(
        call.message.chat.id,
        "✅ Payment request sent to admin.\nPlease wait for approval."
    )

# =========================================
# APPROVE USER
# =========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("app_"))
def approve_user(call):

    try:

        _, u_id, ch_id, mins = call.data.split('_')

        u_id = int(u_id)
        ch_id = int(ch_id)
        mins = int(mins)

        expiry_time = datetime.now() + timedelta(minutes=mins)

        expiry_timestamp = int(expiry_time.timestamp())

        link = bot.create_chat_invite_link(
            ch_id,
            member_limit=1,
            expire_date=expiry_timestamp
        )

        users_col.update_one(
            {
                "user_id": u_id,
                "channel_id": ch_id
            },
            {
                "$set": {
                    "expiry": expiry_time.timestamp()
                }
            },
            upsert=True
        )

        bot.send_message(
            u_id,
            f"🥳 *Payment Approved!*\n\n"
            f"⏳ Subscription: {mins} Minutes\n\n"
            f"🔗 Join Link:\n{link.invite_link}\n\n"
            f"⚠️ Access expires automatically.",
            parse_mode="Markdown"
        )

        bot.edit_message_text(
            f"✅ Approved User {u_id}",
            call.message.chat.id,
            call.message.message_id
        )

    except Exception as e:

        print("Approval Error:", e)

        bot.send_message(
            ADMIN_ID,
            f"❌ Error:\n{e}"
        )

# =========================================
# REJECT USER
# =========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("rej_"))
def reject_user(call):

    user_id = int(call.data.split('_')[1])

    bot.send_message(
        user_id,
        "❌ Your payment was rejected.\nPlease contact admin."
    )

    bot.edit_message_text(
        "❌ Payment Rejected",
        call.message.chat.id,
        call.message.message_id
    )

# =========================================
# MANAGE CHANNEL
# =========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("manage_"))
def manage_channel(call):

    ch_id = int(call.data.split('_')[1])

    ch_data = channels_col.find_one({
        "channel_id": ch_id
    })

    bot_username = bot.get_me().username

    link = f"https://t.me/{bot_username}?start={ch_id}"

    bot.edit_message_text(
        f"⚙️ *Channel Settings*\n\n"
        f"📢 Name: {ch_data['name']}\n\n"
        f"🔗 Link:\n`{link}`\n\n"
        f"To edit prices use /add again.",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown"
    )

# =========================================
# REMOVE EXPIRED USERS
# =========================================
def kick_expired_users():

    now = datetime.now().timestamp()

    expired_users = users_col.find({
        "expiry": {
            "$lte": now
        }
    })

    bot_username = bot.get_me().username

    for user in expired_users:

        try:

            bot.ban_chat_member(
                user["channel_id"],
                user["user_id"]
            )

            bot.unban_chat_member(
                user["channel_id"],
                user["user_id"]
            )

            rejoin_url = (
                f"https://t.me/{bot_username}"
                f"?start={user['channel_id']}"
            )

            markup = InlineKeyboardMarkup()

            markup.add(
                InlineKeyboardButton(
                    "🔄 Renew Subscription",
                    url=rejoin_url
                )
            )

            bot.send_message(
                user["user_id"],
                "⚠️ Your subscription expired.",
                reply_markup=markup
            )

            users_col.delete_one({
                "_id": user["_id"]
            })

        except Exception as e:

            print("Kick Error:", e)

# =========================================
# MAIN
# =========================================
if __name__ == "__main__":

    keep_alive()

    scheduler = BackgroundScheduler()

    scheduler.add_job(
        kick_expired_users,
        'interval',
        minutes=1
    )

    scheduler.start()

    bot.remove_webhook()

    print("Bot Started Successfully!")

    while True:

        try:

            bot.infinity_polling(
                timeout=20,
                long_polling_timeout=10
            )

        except Exception as e:

            print("Polling Error:", e)

            time.sleep(5)    if user_id == ADMIN_ID:
        bot.send_message(message.chat.id, "✅ Admin Panel Active!\n\n/add - Add/Edit Channel & Prices\n/channels - Manage Existing Channels")
    else:
        bot.send_message(message.chat.id, "Welcome! To join a channel, please use the link provided by the Admin.")

@bot.message_handler(commands=['channels'], func=lambda m: m.from_user.id == ADMIN_ID)
def list_channels(message):
    markup = InlineKeyboardMarkup()
    # Fetch all channels managed by this admin
    cursor = channels_col.find({"admin_id": ADMIN_ID})
    count = 0
    for ch in cursor:
        markup.add(InlineKeyboardButton(f"Channel: {ch['name']}", callback_data=f"manage_{ch['channel_id']}"))
        count += 1
    
    markup.add(InlineKeyboardButton("➕ Add New Channel", callback_data="add_new"))
    
    if count == 0:
        bot.send_message(ADMIN_ID, "No channels found. Click below to add one.", reply_markup=markup)
    else:
        bot.send_message(ADMIN_ID, "Your Managed Channels:", reply_markup=markup)

@bot.message_handler(commands=['add'], func=lambda m: m.from_user.id == ADMIN_ID)
def add_channel_start(message):
    msg = bot.send_message(ADMIN_ID, "Please ensure the bot is an Admin in your channel, then FORWARD any message from that channel here.")
    bot.register_next_step_handler(msg, get_plans)

# Callback for Add New button
@bot.callback_query_handler(func=lambda call: call.data == "add_new")
def cb_add_new(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(ADMIN_ID, "Please FORWARD any message from your channel here.")
    bot.register_next_step_handler(msg, get_plans)

def get_plans(message):
    if message.forward_from_chat:
        ch_id = message.forward_from_chat.id
        ch_name = message.forward_from_chat.title
        msg = bot.send_message(ADMIN_ID, 
            f"Channel Detected: *{ch_name}*\n\nEnter plans in format (Minutes:Price):\n`Min:Price, Min:Price` \n\n"
            "Example:\n`1440:99, 43200:199` (1 Day and 30 Days)", parse_mode="Markdown")
        bot.register_next_step_handler(msg, finalize_channel, ch_id, ch_name)
    else:
        bot.send_message(ADMIN_ID, "❌ Error: Message was not forwarded. Use /add to try again.")

def finalize_channel(message, ch_id, ch_name):
    try:
        raw_plans = message.text.split(',')
        plans_dict = {}
        for p in raw_plans:
            t, pr = p.strip().split(':')
            plans_dict[t] = pr
        
        channels_col.update_one({"channel_id": ch_id}, {"$set": {"name": ch_name, "plans": plans_dict, "admin_id": ADMIN_ID}}, upsert=True)
        bot_username = bot.get_me().username
        bot.send_message(ADMIN_ID, f"✅ Setup Successful!\n\nInvite Link for users:\n`https://t.me/{bot_username}?start={ch_id}`", parse_mode="Markdown")
    except:
        bot.send_message(ADMIN_ID, "❌ Invalid format. Please use `Min:Price, Min:Price`. Use /add to retry.")

# --- USER: PAYMENT FLOW ---

@bot.callback_query_handler(func=lambda call: call.data.startswith('select_'))
def user_pays(call):
    _, ch_id, mins = call.data.split('_')
    ch_data = channels_col.find_one({"channel_id": int(ch_id)})
    price = ch_data['plans'][mins]
    
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=upi://pay?pa={UPI_ID}%26am={price}%26cu=INR"
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ I Have Paid", callback_data=f"paid_{ch_id}_{mins}"))
    markup.add(InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{CONTACT_USERNAME}"))
    
    bot.send_photo(call.message.chat.id, qr_url, 
                   caption=f"Plan: {mins} Minutes\nPrice: ₹{price}\nUPI ID: `{UPI_ID}`\n\nPlease complete the payment and click 'I Have Paid'.", 
                   reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('paid_'))
def admin_notify(call):
    _, ch_id, mins = call.data.split('_')
    user = call.from_user
    ch_data = channels_col.find_one({"channel_id": int(ch_id)})
    price = ch_data['plans'][mins]
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ Approve", callback_data=f"app_{user.id}_{ch_id}_{mins}"))
    markup.add(InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user.id}"))
    
    bot.send_message(ADMIN_ID, f"🔔 *Payment Verification Required!*\n\nUser: {user.first_name}\nChannel: {ch_data['name']}\nPlan: {mins} Mins\nPrice: ₹{price}", 
                     reply_markup=markup, parse_mode="Markdown")
    
    u_markup = InlineKeyboardMarkup().add(InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{CONTACT_USERNAME}"))
    bot.send_message(call.message.chat.id, "✅ Your payment request has been sent. Please wait for Admin approval.", reply_markup=u_markup)

# --- APPROVAL & EXPIRY ---

@bot.callback_query_handler(func=lambda call: call.data.startswith('app_'))
def approve_now(call):
    _, u_id, ch_id, mins = call.data.split('_')
    u_id, ch_id, mins = int(u_id), int(ch_id), int(mins)
    
    try:
        expiry_datetime = datetime.now() + timedelta(minutes=mins)
        expiry_ts = int(expiry_datetime.timestamp())

        # Link expires when sub ends
        link = bot.create_chat_invite_link(ch_id, member_limit=1, expire_date=expiry_ts)
        
        users_col.update_one({"user_id": u_id, "channel_id": ch_id}, {"$set": {"expiry": expiry_datetime.timestamp()}}, upsert=True)
        
        bot.send_message(u_id, f"🥳 *Payment Approved!*\n\nSubscription: {mins} Minutes\n\nJoin Link: {link.invite_link}\n\n⚠️ Note: This link and your access will expire in {mins} minutes.", parse_mode="Markdown")
        bot.edit_message_text(f"✅ Approved user {u_id} for {mins} mins.", call.message.chat.id, call.message.message_id)
        
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('manage_'))
def manage_ch(call):
    ch_id = int(call.data.split('_')[1])
    ch_data = channels_col.find_one({"channel_id": ch_id})
    bot_username = bot.get_me().username
    link = f"https://t.me/{bot_username}?start={ch_id}"
    
    bot.edit_message_text(f"Settings for: *{ch_data['name']}*\n\nYour Link: `{link}`\n\nTo edit prices, use /add and forward a message from this channel again.", 
                          call.message.chat.id, call.message.message_id, parse_mode="Markdown")

# Automate Kicking
def kick_expired_users():
    now = datetime.now().timestamp()
    expired_users = users_col.find({"expiry": {"$lte": now}})
    bot_username = bot.get_me().username

    for user in expired_users:
        try:
            bot.ban_chat_member(user['channel_id'], user['user_id'])
            bot.unban_chat_member(user['channel_id'], user['user_id'])
            
            rejoin_url = f"https://t.me/{bot_username}?start={user['channel_id']}"
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔄 Re-join / Renew", url=rejoin_url))
            
            bot.send_message(user['user_id'], "⚠️ Your subscription has expired.\n\nTo join again or renew, please click the button below:", reply_markup=markup)
            users_col.delete_one({"_id": user['_id']})
        except: pass

# --- STARTUP ---
if __name__ == '__main__':
    keep_alive()
    scheduler = BackgroundScheduler()
    scheduler.add_job(kick_expired_users, 'interval', minutes=1)
    scheduler.start()
    bot.remove_webhook()
    print("Bot is running...")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
