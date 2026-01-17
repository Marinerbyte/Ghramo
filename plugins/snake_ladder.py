import time
import threading
import random
import gc
import io
import requests
import concurrent.futures
from PIL import Image, ImageDraw, ImageFont

# Local imports
import utils
import db

# --- CONFIG ---
BOARD_URL = "https://www.dropbox.com/scl/fi/q9kp0wa6oswf1uvo4hspx/board.png?rlkey=dvia1wn8838dgf0qtcdych219&st=4h330mdw&dl=1"
B_SIZE = 400
S_SIZE = 40 
BOARD_CACHE = None

# Mapping
LADDERS = {5: 58, 14: 49, 42: 60, 53: 72, 64: 83, 75: 94}
SNAKES = {38: 20, 45: 7, 51: 10, 76: 54, 91: 73, 97: 61}

sl_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

def setup(bot):
    bot.log("🐍 Snake & Ladders Loaded")
    threading.Thread(target=fetch_board, daemon=True).start()

def fetch_board():
    global BOARD_CACHE
    try:
        r = requests.get(BOARD_URL, timeout=15)
        if r.status_code == 200:
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            BOARD_CACHE = img.resize((B_SIZE, B_SIZE), Image.Resampling.LANCZOS)
    except: pass

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

class SnakeLadderGame:
    def __init__(self, bot, room, creator_id, creator_name, icon):
        self.bot = bot
        self.room = room
        self.creator = creator_id
        self.lock = threading.Lock()
        self.players = {"P1": creator_id, "P2": None}
        self.names = {"P1": creator_name, "P2": None}
        self.avatars = {"P1": icon, "P2": ""}
        self.pos = {"P1": 1, "P2": 1}
        self.turn = "P1"
        self.status = "MODE_SELECT"
        self.mode = None 
        self.bet = 0
        self.timer = None
        self.reset_timer(120, "inactivity")
        self.bot.send_message(self.room, "🐍 **Snake & Ladders**\n`1` Single Player\n`2` Multiplayer")

    def get_coords(self, pos, p_num):
        idx = pos - 1
        row, col = idx // 10, idx % 10
        if row % 2 == 1: col = 9 - col
        x, y = col * 40 + 20, (9 - row) * 40 + 20
        if self.pos["P1"] == self.pos["P2"] and pos > 1:
            return (x-8, y-8) if p_num == "P1" else (x+8, y+8)
        return (x, y)

    def send_game_update(self, text):
        snap = {'pos': self.pos.copy(), 'names': self.names.copy(), 'turn': self.turn, 'avatars': self.avatars.copy()}
        sl_executor.submit(self._bg_task, snap, text, False, None)

    def _bg_task(self, snap, text, is_win, info):
        try:
            img = self.draw_winner(info) if is_win else self.draw_board(snap)
            url = utils.upload_image(img)
            if url:
                self.bot.send_image(self.room, url)
                self.bot.send_message(self.room, text)
            else:
                self.bot.send_message(self.room, f"{text}\n[P1: {snap['pos']['P1']} | P2: {snap['pos']['P2']}]")
        except: pass
        finally: gc.collect()

    def draw_board(self, data):
        canvas = BOARD_CACHE.copy() if BOARD_CACHE else utils.create_canvas(B_SIZE, B_SIZE, (30,30,30))
        p1 = self.get_coords(data['pos']['P1'], "P1")
        utils.draw_circle_avatar(canvas, data['avatars']['P1'], p1[0]-14, p1[1]-14, 28, (255,16,240), 2)
        p2 = self.get_coords(data['pos']['P2'], "P2")
        utils.draw_circle_avatar(canvas, data['avatars']['P2'], p2[0]-14, p2[1]-14, 28, (44,255,255), 2)
        return canvas

    def draw_winner(self, info):
        canvas = utils.create_canvas(400, 400, (17,24,39))
        utils.draw_gradient_bg(canvas, (17,24,39), (20,80,20))
        draw = ImageDraw.Draw(canvas)
        utils.draw_circle_avatar(canvas, info['av'], 125, 50, 150, (255,215,0), 5)
        f_m, f_s = utils.get_font("arial.ttf", 35), utils.get_font("arial.ttf", 20)
        draw.text((200, 230), "👑 CHAMPION", font=f_s, fill="gold", anchor="mm")
        draw.text((200, 275), info['name'], font=f_m, fill="white", anchor="mm")
        draw.text((200, 320), f"Coins: +{info['amt']}", font=f_s, fill="cyan", anchor="mm")
        return canvas

    def process_input(self, cmd, uid, name, icon):
        with self.lock:
            if self.status == "MODE_SELECT" and uid == self.creator:
                if cmd == "1":
                    self.mode, self.players['P2'], self.names['P2'], self.status = "single", "BOT", "Bot 🤖", "PLAYING"
                    self.avatars['P2'] = "https://robohash.org/bot"
                    self.send_game_update("🎮 **Match Started!** Type `roll` to play.")
                    self.reset_timer(120, "turn")
                elif cmd == "2":
                    self.mode, self.status = "multi", "BET_TYPE"
                    self.bot.send_message(self.room, "⚖️ **Multiplayer**\n`1` With Bet\n`2` No Bet")
                return True

            if self.status == "BET_TYPE" and uid == self.creator:
                if cmd == "1": self.status = "BET_AMT"; self.bot.send_message(self.room, "💰 Enter Bet Amount:")
                elif cmd == "2": self.bet, self.status = 0, "WAITING"; self.bot.send_message(self.room, "⚔️ Fun Mode! Type `join`.")
                return True

            if self.status == "BET_AMT" and uid == self.creator and cmd.isdigit():
                amt = int(cmd)
                if amt > get_balance(uid): self.bot.send_message(self.room, "❌ Low Balance!"); return True
                self.bet, self.status = amt, "WAITING"
                self.bot.send_message(self.room, f"⚔️ Betting {amt}. Type `join` to play.")
                return True

            if self.status == "WAITING" and cmd == "join":
                if uid == self.creator: return True
                if self.bet > get_balance(uid): self.bot.send_message(self.room, "❌ Low Balance!"); return True
                self.players['P2'], self.names['P2'], self.avatars['P2'], self.status = uid, name, icon, "PLAYING"
                self.send_game_update(f"⚔️ **Match On!** @{self.names['P1']} vs @{name}")
                self.reset_timer(120, "turn")
                return True

            if self.status == "PLAYING" and cmd in ["roll", "!roll"]:
                if uid != self.players[self.turn]: return False
                dice = random.randint(1, 6)
                old = self.pos[self.turn]
                new = old + dice
                msg = f"🎲 @{self.names[self.turn]} rolled {dice}."
                if new > 100: new = old; msg += " (Wait for exact 100)"
                else:
                    if new in LADDERS: new = LADDERS[new]; msg += " 🪜 Ladder!"
                    elif new in SNAKES: new = SNAKES[new]; msg += " 🐍 Snake!"
                self.pos[self.turn] = new
                if new == 100: self.finalize(self.turn); return True
                self.turn = "P2" if self.turn == "P1" else "P1"
                if self.mode == "single" and self.turn == "P2":
                    bd = random.randint(1, 6)
                    bn = self.pos["P2"] + bd
                    if bn <= 100:
                        if bn in LADDERS: bn = LADDERS[bn]
                        elif bn in SNAKES: bn = SNAKES[bn]
                        self.pos["P2"] = bn
                    if self.pos["P2"] == 100: self.finalize("P2"); return True
                    self.turn = "P1"; msg += f"\n🤖 Bot rolled {bd}. Now at {self.pos['P2']}."
                self.send_game_update(f"{msg}\nNext: @{self.names[self.turn]}")
                self.reset_timer(120, "turn")
                return True
        return False

    def finalize(self, win_sym):
        w_uid, amt = self.players[win_sym], self.bet
        if self.mode == "single": amt = 1000 if win_sym == "P1" else 0
        db.add_game_result(w_uid, self.names[win_sym], "snake_ladder", amt, True)
        if self.mode == "multi":
            loser = "P2" if win_sym == "P1" else "P1"
            db.add_game_result(self.players[loser], self.names[loser], "snake_ladder", -amt, False)
        info = {'name': self.names[win_sym], 'av': self.avatars[win_sym], 'amt': amt}
        sl_executor.submit(self._bg_task, None, f"🏆 @{info['name']} reached 100!", True, info)
        self.cleanup()

    def reset_timer(self, sec, res):
        if self.timer: self.timer.cancel()
        self.timer = threading.Timer(sec, self.timeout_task, [res])
        self.timer.daemon = True
        self.timer.start()

    def timeout_task(self, reason):
        with self.lock:
            if self.status == "ENDED": return
            if reason == "inactivity": self.bot.send_message(self.room, "⚠️ Timeout."); self.cleanup()
            else: self.finalize("P2" if self.turn == "P1" else "P1")

    def cleanup(self):
        self.status = "ENDED"
        if self.timer: self.timer.cancel()
        if self.room in active_sl: del active_sl[self.room]

active_sl = {}
def handle_command(bot, command, room_name, user, args, data):
    cmd, uid = command.lower().strip(), str(data.get("user_id", user))
    icon = data.get("avatar_url", data.get("icon", ""))
    if cmd == "sl":
        if args and args[0] == "1":
            if room_name not in active_sl: active_sl[room_name] = SnakeLadderGame(bot, room_name, uid, user, icon)
            return True
        if args and args[0] == "0":
            if room_name in active_sl: active_sl[room_name].cleanup(); bot.send_message(room_name, "🛑 Stopped.")
            return True
    if room_name in active_sl: return active_sl[room_name].process_input(cmd, uid, user, icon)
    return False
