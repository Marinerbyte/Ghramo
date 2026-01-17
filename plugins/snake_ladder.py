import time
import threading
import random
import gc
import concurrent.futures
from PIL import Image, ImageDraw, ImageFont

# Local imports
import utils
import db

# --- 🖼️ BOARD MAPPING ---
BOARD_IMG_PATH = "board.png" # Make sure this is the 400x400 one
B_SIZE = 400
S_SIZE = 40 

# --- 🐍 SNAKES & LADDERS ---
LADDERS = {5: 58, 14: 49, 42: 60, 53: 72, 64: 83, 75: 94}
SNAKES = {38: 20, 45: 7, 51: 10, 76: 54, 91: 73, 97: 61}

sl_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

def setup(bot):
    bot.log("🐍 Snake & Ladders (Avatar Pawns) Loaded")

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
# 📦 GAME CLASS
# ==========================================
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
        
        self.reset_timer(90, "inactivity")
        self.bot.send_message(self.room, "🐍 **Snake & Ladders Setup**\nSelect Mode:\n`1` Single Player\n`2` Multiplayer")

    # --- COORDINATE LOGIC ---
    def get_coords(self, pos, player_num):
        idx = pos - 1
        row = idx // 10
        col = idx % 10
        
        # Zig-Zag (Boustrophedon) path
        if row % 2 == 1:
            col = 9 - col
            
        # Box center
        x = col * S_SIZE + 20
        y = (9 - row) * S_SIZE + 20
        
        # 🔥 SAME SQUARE OFFSET: Agar dono same box pe hon to thoda hat ke dikhein
        if self.pos["P1"] == self.pos["P2"]:
            if player_num == "P1": return (x - 7, y - 7)
            else: return (x + 7, y + 7)
            
        return (x, y)

    # --- VISUAL TASKS ---
    def send_game_update(self, text_msg):
        snapshot = {
            'pos': self.pos.copy(),
            'names': self.names.copy(),
            'turn': self.turn,
            'avatars': self.avatars.copy() # DP URLs ka snapshot
        }
        sl_executor.submit(self._bg_image_task, snapshot, text_msg, False, None)

    def _bg_image_task(self, snap, text, is_win, win_info):
        try:
            img = None
            if is_win:
                img = self.draw_winner(win_info)
            else:
                img = self.draw_board(snap)
            
            url = utils.upload_image(img)
            if url:
                self.bot.send_image(self.room, url)
                self.bot.send_message(self.room, text)
            else:
                self.bot.send_message(self.room, f"{text}\n📍 P1: {snap['pos']['P1']} | P2: {snap['pos']['P2']}")
        except Exception as e:
            print(f"SL Visual Error: {e}")
        finally:
            if 'img' in locals(): del img
            gc.collect()

    def draw_board(self, data):
        # 1. Background Board Image
        canvas = Image.open(BOARD_IMG_PATH).convert("RGB")
        
        # 2. Player 1 DP (Pink Border)
        p1_coords = self.get_coords(data['pos']['P1'], "P1")
        utils.draw_circle_avatar(
            canvas, 
            data['avatars']['P1'], 
            x=p1_coords[0]-14, # Center pawn (28x28 size)
            y=p1_coords[1]-14, 
            size=28, 
            border_color=(255, 16, 240), 
            border_width=2
        )
        
        # 3. Player 2 DP (Blue Border)
        p2_coords = self.get_coords(data['pos']['P2'], "P2")
        utils.draw_circle_avatar(
            canvas, 
            data['avatars']['P2'], 
            x=p2_coords[0]-14, 
            y=p2_coords[1]-14, 
            size=28, 
            border_color=(44, 255, 255), 
            border_width=2
        )
        
        return canvas

    def draw_winner(self, info):
        canvas = utils.create_canvas(400, 400, color=(17, 24, 39))
        utils.draw_gradient_bg(canvas, (17, 24, 39), (30, 30, 80))
        draw = ImageDraw.Draw(canvas)
        utils.draw_circle_avatar(canvas, info['av'], 125, 50, 150, border_color=(255, 215, 0), border_width=5)
        f_main = utils.get_font("arial.ttf", 35)
        f_sub = utils.get_font("arial.ttf", 20)
        draw.text((200, 230), "👑 SNAKE CHAMP 👑", font=f_sub, fill="gold", anchor="mm")
        draw.text((200, 275), info['name'], font=f_main, fill="white", anchor="mm")
        draw.text((200, 320), f"Coins: +{info['amt']}", font=f_sub, fill=(44, 255, 255), anchor="mm")
        return canvas

    # --- LOGIC HANDLING ---
    def process_input(self, cmd, uid, user_name, icon):
        with self.lock:
            # 1. Mode Select
            if self.status == "MODE_SELECT" and uid == self.creator:
                if cmd == "1":
                    self.mode = "single"; self.players['P2'] = "BOT"; self.names['P2'] = "Bot 🤖"
                    self.avatars['P2'] = "https://robohash.org/snake_bot.png?set=set1"
                    self.status = "PLAYING"
                    self.send_game_update("🤖 Started! Your DP vs Bot. Type `roll`.")
                    self.reset_timer(30, "turn")
                elif cmd == "2":
                    self.mode = "multi"; self.status = "BET_TYPE"
                    self.bot.send_message(self.room, "⚖️ **Multiplayer**\n`1` With Bet, `2` No Bet")
                    self.reset_timer(90, "inactivity")
                return True

            # 2. Bet Type
            if self.status == "BET_TYPE" and uid == self.creator:
                if cmd == "1": self.status = "BET_AMT"; self.bot.send_message(self.room, "💰 Enter Bet Amount:")
                elif cmd == "2": self.bet = 0; self.status = "WAITING"; self.bot.send_message(self.room, "⚔️ Fun Mode! Type `join`.")
                return True

            # 3. Bet Amt
            if self.status == "BET_AMT" and uid == self.creator and cmd.isdigit():
                amt = int(cmd); bal = get_balance(uid)
                if amt > bal: self.bot.send_message(self.room, f"❌ Balance: {bal}"); return True
                self.bet = amt; self.status = "WAITING"
                self.bot.send_message(self.room, f"⚔️ Waiting for opponent ({amt})... Type `join`.")
                return True

            # 4. Join
            if self.status == "WAITING" and cmd == "join":
                if uid == self.creator: return True
                if self.bet > 0 and get_balance(uid) < self.bet: self.bot.send_message(self.room, "❌ Low Balance!"); return True
                self.players['P2'] = uid; self.names['P2'] = user_name; self.avatars['P2'] = icon
                self.status = "PLAYING"
                self.send_game_update(f"⚔️ Match On! @{self.names['P1']} vs @{user_name}")
                self.reset_timer(30, "turn")
                return True

            # 5. Roll Dice
            if self.status == "PLAYING" and (cmd == "roll" or cmd == "!roll"):
                if uid != self.players[self.turn]: return False
                
                dice = random.randint(1, 6)
                old_pos = self.pos[self.turn]
                new_pos = old_pos + dice
                event = f"🎲 @{self.names[self.turn]} rolled {dice}."
                
                if new_pos > 100: new_pos = old_pos; event += " (Too high!)"
                else:
                    if new_pos in LADDERS: new_pos = LADDERS[new_pos]; event += " 🪜 Ladder!"
                    elif new_pos in SNAKES: new_pos = SNAKES[new_pos]; event += " 🐍 Snake!"
                
                self.pos[self.turn] = new_pos
                if new_pos == 100: self.finalize_game(self.turn); return True
                
                self.turn = "P2" if self.turn == "P1" else "P1"
                
                if self.mode == "single" and self.turn == "P2":
                    b_dice = random.randint(1, 6)
                    b_new = self.pos["P2"] + b_dice
                    if b_new <= 100:
                        if b_new in LADDERS: b_new = LADDERS[b_new]
                        elif b_new in SNAKES: b_new = SNAKES[b_new]
                        self.pos["P2"] = b_new
                    if self.pos["P2"] == 100: self.finalize_game("P2"); return True
                    self.turn = "P1"; event += f"\n🤖 Bot rolled {b_dice}."

                self.send_game_update(f"{event}\nTurn: @{self.names[self.turn]}")
                self.reset_timer(30, "turn")
                return True
        return False

    def finalize_game(self, winner_sym):
        w_uid = self.players[winner_sym]
        amt = self.bet
        if self.mode == "single" and winner_sym == "P1":
            amt = 1000
            db.add_game_result(w_uid, self.names[winner_sym], "snake_ladder", amt, True)
        elif self.mode == "multi":
            db.add_game_result(w_uid, self.names[winner_sym], "snake_ladder", amt, True)
            db.add_game_result(self.players["P2" if winner_sym=="P1" else "P1"], self.names["P2" if winner_sym=="P1" else "P1"], "snake_ladder", -amt, False)
        
        info = {'name': self.names[winner_sym], 'av': self.avatars[winner_sym], 'amt': amt}
        sl_executor.submit(self._bg_image_task, None, f"🏆 @{info['name']} Wins!", True, info)
        self.cleanup()

    def reset_timer(self, sec, res):
        if self.timer: self.timer.cancel()
        self.timer = threading.Timer(sec, self.timeout_handler, [res])
        self.timer.daemon = True
        self.timer.start()

    def timeout_handler(self, reason):
        with self.lock:
            if self.status == "ENDED": return
            if reason == "inactivity": self.bot.send_message(self.room, "⚠️ Timeout."); self.cleanup()
            else: self.finalize_game("P2" if self.turn == "P1" else "P1")

    def cleanup(self):
        self.status = "ENDED"
        if self.timer: self.timer.cancel()
        if self.room in active_sl: del active_sl[self.room]
        gc.collect()

active_sl = {}
def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()
    uid = str(data.get("user_id", user))
    icon = data.get("avatar_url", data.get("icon", data.get("avatar", "")))
    if cmd == "sl":
        if args and args[0] == "1":
            if room_name in active_sl: return True
            active_sl[room_name] = SnakeLadderGame(bot, room_name, uid, user, icon)
            return True
        if args and args[0] == "0":
            if room_name in active_sl: active_sl[room_name].cleanup(); bot.send_message(room_name, "🛑 Stopped.")
            return True
    if room_name in active_sl: return active_sl[room_name].process_input(cmd, uid, user, icon)
    return False
