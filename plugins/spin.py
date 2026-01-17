import time
import threading
import random
import gc
import io
import math
import concurrent.futures
from PIL import Image, ImageDraw, ImageFont

# Local imports
import utils
import db

# --- CONFIGURATION ---
WHEEL_SIZE = 400
CENTER = WHEEL_SIZE // 2
# Segments: (Multiplier, Color, Label)
SEGMENTS = [
    (2.0, "#22c55e", "2x"),    # Green
    (0.0, "#6b7280", "0x"),    # Gray
    (1.5, "#3b82f6", "1.5x"),  # Blue
    (0.5, "#f59e0b", "0.5x"),  # Orange
    (5.0, "#8b5cf6", "5x"),    # Purple
    (0.0, "#ef4444", "RIP"),   # Red
    (3.0, "#ec4899", "3x"),    # Pink
    (10.0, "#fbbf24", "10x"),  # Gold (JACKPOT)
]

spin_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

def setup(bot):
    bot.log("🎡 Spin & Win Plugin Loaded")

def get_balance(uid):
    try:
        conn = db.get_connection()
        cur = conn.cursor()
        ph = "%s" if db.DATABASE_URL.startswith("postgres") else "?"
        cur.execute(f"SELECT global_score FROM users WHERE user_id = {ph}", (str(uid),))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else 0
    except: return 0

# ==========================================
# 📦 SPIN GAME CLASS
# ==========================================
class SpinGame:
    def __init__(self, bot, room, uid, name, icon):
        self.bot, self.room, self.uid, self.name, self.icon = bot, room, uid, name, icon
        self.status = "BET_WAIT"
        self.bet = 0
        self.lock = threading.Lock()
        self.timer = None
        self.reset_timer(120)
        self.bot.send_message(self.room, f"🎡 **Lucky Spin Started!**\n@{name} Enter bet amount (e.g. 100):")

    def reset_timer(self, sec):
        if self.timer: self.timer.cancel()
        self.timer = threading.Timer(sec, self.cleanup)
        self.timer.daemon = True
        self.timer.start()

    def draw_wheel(self, result_index=None):
        """Wheel draw karne ka math logic"""
        canvas = Image.new("RGB", (WHEEL_SIZE, WHEEL_SIZE), (17, 24, 39))
        draw = ImageDraw.Draw(canvas)
        
        num_seg = len(SEGMENTS)
        angle_per_seg = 360 / num_seg
        
        # Result ke hisab se rotation (Pointer hamesha TOP pe rahega)
        # Agar result_index 0 hai, to 0th segment top pe aana chahiye
        offset = -90 - (result_index * angle_per_seg) if result_index is not None else -90
        
        for i, (mult, color, label) in enumerate(SEGMENTS):
            start_ang = offset + (i * angle_per_seg)
            end_ang = start_ang + angle_per_seg
            
            # Draw Segment Arc
            draw.pieslice([10, 10, 390, 390], start=start_ang, end=end_ang, fill=color, outline="white", width=2)
            
            # Draw Label (Text Mapping)
            rad_angle = math.radians(start_ang + (angle_per_seg / 2))
            tx = CENTER + 130 * math.cos(rad_angle)
            ty = CENTER + 130 * math.sin(rad_angle)
            
            font = utils.get_font("arial.ttf", 20)
            draw.text((tx, ty), label, font=font, fill="white", anchor="mm")

        # 3. Center User DP
        utils.draw_circle_avatar(canvas, self.icon, CENTER-40, CENTER-40, 80, border_color="white", border_width=3)
        
        # 4. Pointer (Top Triangle)
        draw.polygon([(CENTER-15, 0), (CENTER+15, 0), (CENTER, 30)], fill="white")
        
        return canvas

    def process(self, cmd):
        with self.lock:
            if self.status == "BET_WAIT":
                if not cmd.isdigit(): return False
                amt = int(cmd)
                bal = get_balance(self.uid)
                if amt <= 0: return True
                if amt > bal:
                    self.bot.send_message(self.room, f"❌ Low Balance! (Coins: {bal})")
                    return True
                
                self.bet = amt
                self.status = "SPINNING"
                self.start_spin()
                return True
        return False

    def start_spin(self):
        """Background thread me spin process karo"""
        spin_executor.submit(self._spin_task)

    def _spin_task(self):
        try:
            # Result Decide Karo
            res_idx = random.randint(0, len(SEGMENTS)-1)
            multiplier, color, label = SEGMENTS[res_idx]
            win_amt = int(self.bet * multiplier)
            
            # Draw & Upload
            img = self.draw_wheel(res_idx)
            
            # Fast JPEG upload taaki turant dikhe
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=80)
            buf.seek(0)
            
            import uuid
            files = {'reqtype': (None, 'fileupload'), 'fileToUpload': (f'spin_{uuid.uuid4().hex}.jpg', buf, 'image/jpeg')}
            r = requests.post('https://catbox.moe/user/api.php', files=files, timeout=30)
            
            if r.status_code == 200:
                url = r.text.strip()
                self.bot.send_image(self.room, url)
            
            # Final result message
            if multiplier > 1:
                msg = f"🔥 **JACKPOT!** @{self.name} won **{win_amt}** coins! ({label})"
                db.add_game_result(self.uid, self.name, "spin", win_amt - self.bet, True)
            elif multiplier == 1:
                msg = f"😐 **Neutral!** No loss, no gain. ({label})"
            elif multiplier > 0:
                loss = self.bet - win_amt
                msg = f"📉 **Partial Win!** @{self.name} got **{win_amt}** back. ({label})"
                db.add_game_result(self.uid, self.name, "spin", -loss, False)
            else:
                msg = f"💀 **RIP!** @{self.name} lost everything. ({label})"
                db.add_game_result(self.uid, self.name, "spin", -self.bet, False)
            
            self.bot.send_message(self.room, msg)
            
        except Exception as e:
            self.bot.send_message(self.room, "⚠️ Spin failed.")
            print(f"Spin Error: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        if self.timer: self.timer.cancel()
        if self.room in active_spins:
            del active_spins[self.room]
        gc.collect()

# --- GLOBAL HANDLER ---
active_spins = {}

def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()
    uid = str(data.get("user_id", user))
    icon = data.get("avatar_url", data.get("icon", ""))

    if cmd == "spin":
        if args and args[0] == "1":
            if room_name in active_spins: return True
            active_spins[room_name] = SpinGame(bot, room_name, uid, user, icon)
            return True
        if args and args[0] == "0":
            if room_name in active_spins: 
                active_spins[room_name].cleanup()
                bot.send_message(room_name, "🛑 Spin stopped.")
            return True

    if room_name in active_spins:
        return active_spins[room_name].process(cmd)

    return False

import requests # Required for uploader
