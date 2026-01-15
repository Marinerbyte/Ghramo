import sys
import os
import traceback
import math

# --- DB IMPORT ---
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    import db
except Exception as e:
    print(f"DB Import Error: {e}")

# --- FANCY TEXT CONVERTER ---
def fancy(text):
    normal = "abcdefghijklmnopqrstuvwxyz"
    small  = "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ"
    trans = str.maketrans(normal, small)
    return text.lower().translate(trans)

# --- RANK SYSTEM ---
def get_rank(score):
    if score < 500: return "🥚 ɴᴇᴡʙɪᴇ"
    elif score < 2000: return "💸 ʜᴜsᴛʟᴇʀ"
    elif score < 5000: return "🛡️ ᴡᴀʀʀɪᴏʀ"
    elif score < 10000: return "🎩 ʙᴏss"
    elif score < 50000: return "👑 ᴋɪɴɢ"
    else: return "💎 ᴇᴍᴘᴇʀᴏʀ"

def handle_command(bot, command, room_name, user, args, data):
    # Loader ab '!' hata kar bhej raha hai
    cmd = command.lower().strip()
    
    # TalkinChat uses strings for IDs, but if we have a numeric ID in payload, we use it
    user_id = data.get("user_id", user) 
    ph = "%s" if db.DATABASE_URL.startswith("postgres") else "?"

    # --- 1. VIEW STATS / BALANCE ---
    if cmd in ["score", "bal", "coins", "stats", "profile"]:
        try:
            conn = db.get_connection()
            cur = conn.cursor()

            # Get User Data
            cur.execute(f"SELECT global_score, wins FROM users WHERE user_id = {ph}", (str(user_id),))
            row = cur.fetchone()

            if not row:
                # Auto-register if not found
                cur.execute(f"INSERT INTO users (user_id, username, global_score, wins) VALUES ({ph}, {ph}, 0, 0)", (str(user_id), user))
                conn.commit()
                score, wins = 0, 0
            else:
                score, wins = row

            rank_title = get_rank(score)
            
            msg = f"👤 **{fancy('profile')}: @{user}**\n"
            msg += f"🏷️ **{fancy('rank')}:** {rank_title}\n"
            msg += f"💰 **{fancy('coins')}:** {score}\n"
            msg += f"🏆 **{fancy('total wins')}:** {wins}\n"
            msg += "──────────────────"
            
            bot.send_message(room_name, msg)
            conn.close()
            return True
        except:
            traceback.print_exc()
            return True

    # --- 2. LEADERBOARD ---
    if cmd in ["top", "lb", "leaderboard"]:
        try:
            conn = db.get_connection()
            cur = conn.cursor()
            
            # Get Top 10
            cur.execute("SELECT username, global_score FROM users ORDER BY global_score DESC LIMIT 10")
            rows = cur.fetchall()
            conn.close()

            if not rows:
                bot.send_message(room_name, "📉 Leaderboard is empty.")
                return True

            msg = f"🏆 **{fancy('global leaderboard')}** 🏆\n"
            msg += "──────────────────\n"
            for idx, (name, score) in enumerate(rows):
                medal = "🔹"
                if idx == 0: medal = "🥇"
                elif idx == 1: medal = "🥈"
                elif idx == 2: medal = "🥉"
                msg += f"{medal} `#{idx+1}` **{name}**: {score}\n"
            
            bot.send_message(room_name, msg)
            return True
        except:
            traceback.print_exc()
            return True

    return False
