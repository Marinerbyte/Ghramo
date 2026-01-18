import threading
import gc
import io
from PIL import Image, ImageDraw, ImageFont
import db
import utils

# --- RANKING SYSTEM ---
RANKS = [
    (0, "👶 NOOB", "#94a3b8"),          # Gray
    (5000, "🔫 HUSTLER", "#3b82f6"),    # Blue
    (20000, "⚔️ WARRIOR", "#8b5cf6"),   # Purple
    (50000, "🛡️ ELITE", "#ef4444"),     # Red
    (100000, "👑 LEGEND", "#fbbf24"),   # Gold
    (500000, "💎 MYTHIC", "#2dd4bf")    # Teal
]

def get_rank_info(score):
    for threshold, title, color in reversed(RANKS):
        if score >= threshold:
            return title, color
    return RANKS[0][1], RANKS[0][2]

def setup(bot):
    bot.log("📊 Advanced Stats & Profile System Loaded")

# ==========================================
# 🖼️ IMAGE GENERATOR: PROFILE CARD
# ==========================================
def draw_profile_card(user_name, icon, score, wins, rank_pos):
    W, H = 600, 350
    canvas = utils.create_canvas(W, H, color=(17, 24, 39))
    utils.draw_gradient_bg(canvas, (17, 24, 39), (31, 41, 55))
    draw = ImageDraw.Draw(canvas)

    # Rank Info
    rank_title, rank_color = get_rank_info(score)

    # 1. Circle Avatar
    utils.draw_circle_avatar(canvas, icon, 40, 50, 180, border_color=rank_color, border_width=5)

    # 2. Text Details
    f_name = utils.get_font("arial.ttf", 40)
    f_stats = utils.get_font("arial.ttf", 25)
    f_rank = utils.get_font("arial.ttf", 22)

    # Name & Rank Title
    draw.text((260, 60), user_name[:15], font=f_name, fill="white")
    draw.text((260, 110), rank_title, font=f_rank, fill=rank_color)

    # Stats Section
    draw.text((260, 170), f"💰 Coins: {score}", font=f_stats, fill="#e2e8f0")
    draw.text((260, 210), f"🏆 Total Wins: {wins}", font=f_stats, fill="#e2e8f0")
    draw.text((260, 250), f"🌎 Global Rank: #{rank_pos}", font=f_stats, fill=rank_color)

    # 3. Progress Bar (Level bar)
    draw.rectangle([260, 300, 550, 315], fill="#374151") # Background bar
    # Logic for next rank progress
    next_threshold = 5000
    for t, t_name, t_col in RANKS:
        if t > score:
            next_threshold = t
            break
    
    progress = min(1.0, score / next_threshold) if next_threshold > 0 else 1.0
    bar_width = int(290 * progress)
    draw.rectangle([260, 300, 260 + bar_width, 315], fill=rank_color)

    return canvas

# ==========================================
# 🧠 COMMAND HANDLER
# ==========================================
def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()
    uid = str(data.get("user_id", user))
    icon = data.get("avatar_url", data.get("icon", data.get("avatar", "")))

    # --- 1. VISUAL PROFILE (!stats / !profile) ---
    if cmd in ["stats", "profile", "me"]:
        def profile_task():
            try:
                conn = db.get_connection()
                cur = conn.cursor()
                ph = "%s" if db.DATABASE_URL.startswith("postgres") else "?"
                
                # Global Stats
                cur.execute(f"SELECT global_score, wins FROM users WHERE user_id = {ph}", (uid,))
                row = cur.fetchone()
                if not row:
                    # Register new user
                    cur.execute(f"INSERT INTO users (user_id, username, global_score, wins) VALUES ({ph}, {ph}, 0, 0)", (uid, user))
                    conn.commit()
                    row = (0, 0)
                
                # Rank Position
                cur.execute(f"SELECT count(*) FROM users WHERE global_score > {ph}", (row[0],))
                rank_pos = cur.fetchone()[0] + 1
                conn.close()

                # Generate Image
                img = draw_profile_card(user, icon, row[0], row[1], rank_pos)
                url = utils.upload_image(img)
                
                if url:
                    bot.send_image(room_name, url)
                else:
                    bot.send_message(room_name, f"👤 **{user}**\n💰 Coins: {row[0]}\n🏆 Wins: {row[1]}\n📍 Rank: #{rank_pos}")
                
                del img; gc.collect()
            except Exception as e:
                print(f"Profile Error: {e}")

        threading.Thread(target=profile_task, daemon=True).start()
        return True

    # --- 2. GLOBAL LEADERBOARD (!top / !lb) ---
    if cmd in ["top", "lb", "leaderboard"]:
        try:
            conn = db.get_connection()
            cur = conn.cursor()
            cur.execute("SELECT username, global_score FROM users ORDER BY global_score DESC LIMIT 10")
            rows = cur.fetchall()
            conn.close()

            if not rows:
                bot.send_message(room_name, "📈 Leaderboard is empty!")
                return True

            msg = "🏆 **GLOBAL LEADERBOARD** 🏆\n"
            msg += "──────────────────\n"
            for i, (name, score) in enumerate(rows):
                medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "🔹"
                msg += f"{medal} `#{i+1}` **{name}**: {score} 💰\n"
            
            bot.send_message(room_name, msg)
            return True
        except: return True

    # --- 3. GAME WISE STATS (!mygame) ---
    if cmd in ["mygame", "records"]:
        try:
            conn = db.get_connection()
            cur = conn.cursor()
            ph = "%s" if db.DATABASE_URL.startswith("postgres") else "?"
            cur.execute(f"SELECT game_name, wins, earnings FROM game_stats WHERE user_id = {ph}", (uid,))
            rows = cur.fetchall()
            conn.close()

            if not rows:
                bot.send_message(room_name, f"❌ @{user}, you haven't played any games yet!")
                return True

            msg = f"🎮 **GAME RECORDS: @{user}**\n"
            msg += "──────────────────\n"
            for gname, wins, earnings in rows:
                emoji = "🎲"
                if "tic" in gname: emoji = "⭕"
                elif "snake" in gname: emoji = "🐍"
                elif "spin" in gname: emoji = "🎡"
                
                msg += f"{emoji} **{gname.upper()}**\n"
                msg += f"   ├ Wins: {wins}\n"
                msg += f"   └ Profit: {earnings} 💰\n\n"
            
            bot.send_message(room_name, msg)
            return True
        except: return True

    return False
