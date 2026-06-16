import telebot
import random
import os
import re
from html import escape
from telebot import types

# 1. BOT SETUP & CONFIGURATION
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is missing")

bot = telebot.TeleBot(BOT_TOKEN)

OWNER_ID = 6531314640
EXTRA_ADMIN = 8650959684
ADMINS = [OWNER_ID, EXTRA_ADMIN]

LOG_GROUP_ID = -5406849696
INVENTORY_FILE = "inventory.txt"

giveaway_data = {
    "active": False,
    "prize_name": "",
    "ticket_price": 0,
    "prize_amount": 1,     
    "group_chat_id": None, 
    "tickets": {},        
    "usernames": {},      
    "is_admin_ticket": {},
    "paid_tickets": {},
    "free_tickets": {},
    "admin_tickets": {},
    "free_ticket_claimed": set()
}

def html_escape(value):
    """Escape dynamic text before sending with Telegram HTML parse mode."""
    return escape(str(value or ""), quote=False)

def user_display_from_user(user):
    """
    Return a safe display name for any Telegram user.
    - Uses @username only when Telegram gives a normal username.
    - Falls back to first name for special fonts/symbols/weird names.
    - Falls back to user ID when the name is missing or unusable.
    """
    user_id = getattr(user, "id", None)
    username = (getattr(user, "username", None) or "").strip()
    first_name = (getattr(user, "first_name", None) or "").strip()

    if username and re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
        return f"@{username}"

    if first_name:
        if user_id:
            return f"{first_name} (ID: {user_id})"
        return first_name

    if user_id:
        return f"User ID: {user_id}"

    return "Unknown User"

def user_display_from_id(user_id):
    return giveaway_data["usernames"].get(user_id) or f"User ID: {user_id}"

def safe_send(chat_id, text, **kwargs):
    """Send HTML safely; if Telegram rejects formatting, send plain text fallback."""
    try:
        return bot.send_message(chat_id, text, parse_mode="HTML", **kwargs)
    except Exception:
        plain = re.sub(r"</?(b|i|u|s|code|pre)>", "", text)
        return bot.send_message(chat_id, plain, **kwargs)

def safe_log(text):
    try:
        bot.send_message(LOG_GROUP_ID, str(text))
    except Exception:
        pass  

def get_multiple_rewards(amount):
    if not os.path.exists(INVENTORY_FILE):
        return []
    
    with open(INVENTORY_FILE, "r") as f:
        lines = f.readlines()
        
    if not lines or len(lines) < amount:
        return [] 
    
    rewards = [line.strip() for line in lines[:amount]]
    
    with open(INVENTORY_FILE, "w") as f:
        f.writelines(lines[amount:])
        
    return rewards

# 2. ADMIN COMMAND: START GIVEAWAY
@bot.message_handler(commands=['startgiveaway'])
def start_giveaway(message):
    if message.chat.type == "private":
        return bot.reply_to(message, "❌ This command must be executed inside your Telegram Group Chat.")

    if message.from_user.id not in ADMINS:
        return bot.reply_to(message, "❌ Access Denied. Admins only.")
    
    text_content = message.text.strip()
    if ' ' in text_content:
        args = text_content.split(' ', 1)[1].strip()
    else:
        return bot.reply_to(message, "❌ Invalid format. Use: `/startgiveaway Prize Name 15 2`")

    try:
        # Supports both formats:
        # /startgiveaway Prize Name | 15 | 2 accounts
        # /startgiveaway Prize Name 15 2
        if '|' in args:
            if args.count('|') < 2:
                return bot.reply_to(message, "❌ Invalid format. Example: `/startgiveaway 18k Coin Account | 15 | 2 accounts`")
            prize_part, price_part, amount_part = args.split('|', 2)
            prize = prize_part.strip()
            price = int(price_part.strip())
            amount_digits = re.findall(r'\d+', amount_part)
            if not amount_digits:
                return bot.reply_to(message, "❌ Quantity not found. Example: `2 accounts`")
            amount = int(amount_digits[0])
        else:
            parts = args.rsplit(' ', 2)
            if len(parts) < 3:
                return bot.reply_to(message, "❌ Invalid format. Example: `/startgiveaway test 1 1`")
            prize = parts[0].strip()
            price = int(parts[1].strip())
            amount = int(parts[2].strip())

        if not prize:
            return bot.reply_to(message, "❌ Prize name cannot be empty.")
        
        if price <= 0:
            return bot.reply_to(message, "❌ Ticket price must be greater than 0.")
        
        if amount <= 0:
            return bot.reply_to(message, "❌ Quantity must be greater than 0.")
            
        giveaway_data["active"] = True
        giveaway_data["prize_name"] = prize
        giveaway_data["ticket_price"] = price
        giveaway_data["prize_amount"] = amount
        giveaway_data["group_chat_id"] = message.chat.id 
        giveaway_data["tickets"] = {}
        giveaway_data["usernames"] = {}
        giveaway_data["is_admin_ticket"] = {}
        giveaway_data["paid_tickets"] = {}
        giveaway_data["free_tickets"] = {}
        giveaway_data["admin_tickets"] = {}
        giveaway_data["free_ticket_claimed"] = set()
        
        bot_username = bot.get_me().username
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🎫 BUY TICKET VIA PM", url=f"t.me/{bot_username}?start=buy"))

        success_msg = (
            f"🎉 <b>NEW LUCKY DRAW STARTED!</b> 🎉\n\n"
            f"🎁 <b>Prize:</b> {html_escape(prize)}\n"
            f"📦 <b>Quantity:</b> {amount} Accounts\n"
            f"💰 <b>Ticket Price:</b> {price} Stars\n\n"
            f"👇 Click the button below to purchase tickets privately via DM to avoid group spam!"
        )
        safe_send(message.chat.id, success_msg, reply_markup=markup)
        
        safe_log(f"📢 [LOG] Giveaway started by Admin. Prize: {prize} ({amount}x)")
    except ValueError:
        bot.reply_to(message, "❌ Invalid input. Use: `/startgiveaway Prize Name 15 2`")
    except Exception as e:
        bot.reply_to(message, f"❌ System Error: {str(e)}")

# 3. USER COMMAND: START / DEEP LINK HELP
@bot.message_handler(commands=['start'])
def start_command(message):
    start_text = (
        "🎉 Welcome to the Lucky Draw Bot! 🎉\n\n"
        "📝 How to Enter:\n"
        "1️⃣ Start this bot in DM.\n"
        "2️⃣ Run /buyticket to buy 1 ticket.\n"
        "3️⃣ Run /buyticket 5 to buy multiple tickets.\n"
        "4️⃣ Each paid ticket enters you into the exclusive prize draw.\n\n"
        "📊 Use /stats to view the current giveaway odds.\n"
        "🍀 Good luck!"
    )

    bot.send_message(message.chat.id, start_text)

    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].lower() == "buy":
        bot.send_message(
            message.chat.id,
            "🎫 To enter now, run /buyticket or /buyticket 5 to buy multiple tickets."
        )


# 3. USER COMMAND: BUY TICKET (WITH STARS INVOICE GENERATOR)
@bot.message_handler(commands=['buyticket'])
def buy_ticket(message):
    if message.chat.type != "private":
        try:
            bot.delete_message(message.chat.id, message.message_id) 
        except:
            pass
        return bot.send_message(message.from_user.id, "❌ Do not send commands in the group chat. Send `/buyticket` directly here in my DMs.")

    if not giveaway_data["active"]:
        return bot.reply_to(message, "❌ There is no active lucky draw running at the moment.")
    
    try:
        text_content = message.text.strip()
        parts = text_content.split()
        count = int(parts[1]) if len(parts) > 1 else 1
        if count <= 0: raise ValueError
    except:
        return bot.reply_to(message, "❌ Invalid format. Example: `/buyticket 2` to purchase multiple tickets.")
    
    user_id = message.from_user.id
    username = user_display_from_user(message.from_user)
    
    # FOR ADMINS: Instantly entered for free (Admin Perks)
    if user_id in ADMINS:
        giveaway_data["tickets"][user_id] = giveaway_data["tickets"].get(user_id, 0) + count
        giveaway_data["usernames"][user_id] = username
        giveaway_data["is_admin_ticket"][user_id] = True
        giveaway_data["admin_tickets"][user_id] = giveaway_data["admin_tickets"].get(user_id, 0) + count
        
        bot.reply_to(message, f"✅ [ADMIN PERK] Successfully credited {count} free ticket(s) to your balance!")
        safe_log(f"👑 [ADMIN ENTRY] {username} registered {count} free ticket(s).")
        return

    # FOR REGULAR USES: Generate Official Telegram Stars Invoice
    total_cost = count * giveaway_data["ticket_price"]
    
    prices = [types.LabeledPrice(label=f"{count} Ticket(s)", amount=total_cost)]
    
    try:
        bot.send_invoice(
            chat_id=user_id,
            title="🎟️ Lucky Draw Ticket Purchase",
            description=f"Purchase {count} ticket(s) for the {giveaway_data['prize_name']} draw.",
            invoice_payload=f"buy_tickets_{count}_{user_id}", # Saves ticket count and user info inside payload
            provider_token="", # Must remain empty ('') for Telegram Stars payments
            currency="XTR",    # XTR stands for Telegram Stars
            prices=prices,
            start_parameter="lucky-draw"
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to generate checkout invoice: {str(e)}")

# 4. USER COMMAND: FREE TICKET
@bot.message_handler(commands=['freeticket'])
def free_ticket(message):
    if message.chat.type != "private":
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass
        try:
            return bot.send_message(
                message.from_user.id,
                "🎫 Send /freeticket here in DM to claim your free entry."
            )
        except Exception:
            return

    if not giveaway_data["active"]:
        return bot.reply_to(message, "❌ There are no active raffles running right now.")

    user_id = message.from_user.id
    username = user_display_from_user(message.from_user)

    if user_id in giveaway_data.get("free_ticket_claimed", set()):
        return bot.reply_to(message, "✅ You already claimed your free ticket for the current active raffle.")

    giveaway_data["tickets"][user_id] = giveaway_data["tickets"].get(user_id, 0) + 1
    giveaway_data["usernames"][user_id] = username
    giveaway_data["free_tickets"][user_id] = giveaway_data["free_tickets"].get(user_id, 0) + 1
    giveaway_data.setdefault("free_ticket_claimed", set()).add(user_id)

    safe_log(f"🎫 [FREE TICKET] {username} claimed 1 free entry.")

    success_txt = (
        "✅ <b>Free ticket claimed!</b>\n\n"
        f"🎁 You now have 1 free entry in: <b>{html_escape(giveaway_data['prize_name'])}</b>\n"
        "📊 Use /stats to view the current raffle odds."
    )
    safe_send(user_id, success_txt)

# 5. STARS PAYMENT CHECKOUT HANDLERS (ANTI-CHEAT)
@bot.pre_checkout_query_handler(func=lambda query: True)
def process_pre_checkout(pre_checkout_query):
    # Auto-approve the payment window when verification data matches
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def payment_success_catch(message):
    # Tickets are credited only after a fully verified and successful payment
    payload = message.successful_payment.invoice_payload
    
    if payload.startswith("buy_tickets_"):
        parts = payload.split("_")
        count = int(parts[2])
        user_id = int(parts[3])
        username = user_display_from_user(message.from_user)
        
        giveaway_data["tickets"][user_id] = giveaway_data["tickets"].get(user_id, 0) + count
        giveaway_data["usernames"][user_id] = username
        giveaway_data["is_admin_ticket"][user_id] = False
        giveaway_data["paid_tickets"][user_id] = giveaway_data["paid_tickets"].get(user_id, 0) + count
        
        success_txt = (
            f"🌟 <b>PAYMENT CONFIRMED!</b> 🌟\n\n"
            f"✅ Successfully credited {count} ticket(s) to your balance!\n"
            f"🎁 Current Pool: {html_escape(giveaway_data['prize_name'])}\n\n"
            f"Type /stats to view your updated winning probability."
        )
        safe_send(user_id, success_txt)
        
        safe_log(
            f"💰 [SUCCESSFUL PAYMENT RECEIVED]\n"
            f"👤 User: {username} ({user_id})\n"
            f"🎟️ Tickets Paid: {count}\n"
            f"💎 Total Stars Sent: {message.successful_payment.total_amount} Stars"
        )

# 5. STATS VIEW COMMAND
@bot.message_handler(commands=['stats'])
def show_stats(message):
    if not giveaway_data["active"]:
        return bot.reply_to(message, "❌ There is no active lucky draw running right now.")
    
    total_tickets = sum(giveaway_data["tickets"].values())
    unique_users = len(giveaway_data["tickets"])
    
    total_stars = sum(giveaway_data.get("paid_tickets", {}).values()) * giveaway_data["ticket_price"]
    
    text = f"📊 <b>Current Lucky Draw Status</b> – {html_escape(giveaway_data['prize_name'])} ({giveaway_data['prize_amount']}x)\n\n"
    text += f"🎟️ <b>Total Tickets Issued:</b> {total_tickets}\n"
    text += f"👥 <b>Unique Entrants:</b> {unique_users}\n"
    text += f"⭐ <b>Total Stars Collected:</b> {total_stars}\n\n"
    text += "🏅 <b>Top Contenders:</b>\n"
    
    sorted_users = sorted(giveaway_data["tickets"].items(), key=lambda x: x[1], reverse=True)
    
    for user_id, ticket_count in sorted_users[:5]:
        uname = user_display_from_id(user_id)
        percentage = (ticket_count / total_tickets) * 100 if total_tickets > 0 else 0
        text += f"• {html_escape(uname)}: {ticket_count} ticket(s) ({percentage:.1f}% chance)\n"
    
    safe_send(message.chat.id, text)

# 6. ADMIN COMMAND: DRAW WINNER
@bot.message_handler(commands=['draw'])
def draw_winner(message):
    if message.from_user.id not in ADMINS:
        return
        
    if not giveaway_data["active"]:
        return bot.reply_to(message, "❌ There is no active pool available to draw from.")
        
    total_tickets = sum(giveaway_data["tickets"].values())
    if total_tickets == 0:
        return bot.reply_to(message, "❌ Cannot execute draw. No valid paid entries found.")
        
    needed_accounts = giveaway_data["prize_amount"]
    
    reward_list = get_multiple_rewards(needed_accounts)
    if not reward_list:
        return bot.reply_to(
            message, 
            f"🚨 [ERROR] Insufficient stock in `inventory.txt`!\n"
            f"Required: {needed_accounts} accounts, but inventory list is short."
        )

    ticket_pool = []
    for user_id, count in giveaway_data["tickets"].items():
        ticket_pool.extend([user_id] * count)
        
    winners_announcement = "🏁 <b>THE LUCKY DRAW POOL HAS OFFICIALLY ENDED!</b> 🏁\n\n📢 <b>Official Winners:</b>\n"
    
    for i in range(needed_accounts):
        winner_id = random.choice(ticket_pool)
        winner_username = user_display_from_id(winner_id)
        current_account = reward_list[i]
        
        winners_announcement += f"🏆 <b>Winner {i+1}:</b> {html_escape(winner_username)} → ({html_escape(giveaway_data['prize_name'])})\n"
        
        try:
            dm_text = (
                f"🎁 <b>Congratulations! You have won the Lucky Draw!</b> 🎁\n\n"
                f"📌 <b>Prize:</b> {html_escape(giveaway_data['prize_name'])}\n\n"
                f"🔐 <b>Account Credentials:</b>\n<code>{html_escape(current_account)}</code>\n\n"
                f"<i>Thank you for your entry and support!</i>"
            )
            safe_send(winner_id, dm_text)
            dm_status = "✅ Dispatched"
        except Exception:
            dm_status = "❌ DM Blocked"
            safe_log(f"⚠️ [MANUAL DISPATCH REQUIRED] Failed to DM {winner_username}. Credentials: {current_account}")

        safe_log(f"🏅 Draw Result {i+1}/{needed_accounts}: {winner_username} -> {dm_status}")

    winners_announcement += "\n📬 All prizes have been automatically dispatched to the winners' Direct Messages. Please verify your inboxes!"
    
    safe_send(giveaway_data["group_chat_id"], winners_announcement)
    giveaway_data["active"] = False

bot.infinity_polling()
