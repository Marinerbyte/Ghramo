import time
import threading
import random
import gc
import concurrent.futures
from PIL import Image, ImageDraw, ImageFont

# Local imports
import utils
import db

# --- 🖼️ BOARD SETTINGS ---
# Board image (board.png) should be in the main folder
BOARD_IMG_PATH = "board.png"
B_SIZE = 360  # Base size for mapping (360x360)
S_SIZE = 36   # Each square is 36px

# --- 🐍 USER DEFINED MAPPING (100% CORRECT) ---
LADDERS = {5: 58, 14: 49, 42: 60, 53: 72, 64: 83, 75: 94}
SNAKES = {38: 20, 45: 7, 51: 10, 76: 54, 91: 73, 97: 61}

# Image Worker Pool
sl_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

def setup(bot):
    bot.log("🐍 Snake & Ladders (Custom Mapping) Loaded")

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
# 📦 THE GAME INSTANCE (DABBA)
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
        self.bot.send_message(self.room, "🐍 **Snake & Ladders Started!**\nSelect Mode:\n`1` Single Player\n`2` Multiplayer")

    # --- ZIG-ZAG MAPPING LOGIC ---
    def get_coords(self, pos):
        """Calculates (x, y) for 1-100 serpentine grid."""
        row = (pos - 1) // 10
        col = (pos - 1) % 10
        
        # Zig-Zag: If row is odd (1, 3, 5...), reverse the column
        if row % 2 == 1:
            col = 9 - col
            
        x = col * S_SIZE + (S_SIZE // 2)
        y = (9 - row) * S_SIZE + (S_SIZE // 2)
        return (x, y)

    # --- IMAGE TASKS ---
    def send_game_update(self, text):
        snapshot = {
            'pos': self.pos.copy(),
            'names': self.names.copy(),
            'turn': self.turn
        }
        sl_executor.submit(self._bg_visual_task, snapshot, text)

    def _bg_visual_task(self, snap, text, is_win=False, win_info=None):
        try:
            img = None
            if is_win:
                img = self.draw_winner(win_info)
            else:
                img = self.draw_board(snap)
            
            # Use utils robust uploader (Fresh connection)
            url = utils.upload_image(img)
            
            if url:
                self.bot.send_image(self.room, url)
                self.bot.send_message(self.room, text)
            else:
                self.bot.send_message(self.room, f"{text}\n📍 [P1: {snap['pos']['P1']} | P2: {snap['pos']['P2']}]")
        except Exception as e: print(f"SL Img Error: {e}")
        finally:
            if img: del img
            gc.collect()

    def draw_board(self, snap):
        # Background Board Image
        try:
            canvas = Image.open(BOARD_IMG_PATH).convert("RGB")
            # Resize if necessary to 360x360
            if canvas.size != (B_SIZE, B_SIZE):
                canvas = canvas.resize((B_SIZE, B_SIZE))
        except:
            canvas = utils.create_canvas(B_SIZE, B_SIZE, color=(17,24,39))
            
        draw = ImageDraw.Draw(canvas)
        
        p1_x, p1_y = self.get_coords(snap['pos']['P1'])
        p2_x, p2_y = self.get_coords(snap['pos']['P2'])
        
        # Draw Pawn 1 (Neon Pink)
        draw.ellipse([p1_x-12, p1_y-12, p1_x+12, p1_y+12], fill=(255, 16, 240), outline="white", width=2)
        # Draw Pawn 2 (Neon Green)
        draw.ellipse([p2_x-8, p2_y-8, p2_x+8, p2_y+8], fill=(57, 255, 20), outline="black", width=1)
        
        return canvas

    def draw_winner(self, info):
        canvas = utils.create_canvas(400, 400, color=(17, 24, 39))
        utils.draw_gradient_bg(canvas, (17, 24, 39), (30, 30, 70))
        draw = ImageDraw.Draw(canvas)
        
        # Winner Avatar
        utils.draw_circle_avatar(canvas, info['av'], 125, 50, 150, border_color=(44, 255, 255), border_width=5)
        
        f_m = utils.get_font("arial.ttf", 35)
        f_s = utils.get_font("arial.ttf", 20)
        
        draw.text((200, 230), "👑 SNAKE KING 👑", font=f_s, fill="gold", anchor="mm")
        draw.text((200, 275), info['name'], font=f_m, fill="white", anchor="mm")
        draw.text((200, 320), f"Won {info['amt']} Coins", font=f_s, fill=(44, 255, 255), anchor="mm")
        
        return canvas

    # --- LOGIC HANDLING ---
    def process_input(self, cmd, uid, name, icon):
        with self.lock:
            # 1. Mode Select
            if self.status == "MODE_SELECT" and uid == self.creator:
                if cmd == "1":
                    self.mode = "single"; self.players['P2'] = "BOT"; self.names['P2'] = "Robot 🤖"
                    self.avatars['P2'] = "https://robohash.org/snake.png?set=set4"
                    self.status = "PLAYING"
                    self.send_game_update("🤖 Started! Single player win = 1000 Coins. Type `roll`.")
                    self.reset_timer(30, "turn")
                elif cmd == "2":
                    self.mode = "multi"; self.status = "BET_TYPE"
                    self.bot.send_message(self.room, "⚖️ **Multiplayer**\n`1` With Bet\n`2` No Bet")
                    self.reset_timer(90, "inactivity")
                return True

            # 2. Bet Type
            if self.status == "BET_TYPE" and uid == self.creator:
                if cmd == "1":
                    self.status = "BET_AMT"; self.bot.send_message(self.room, "💰 Enter Bet Amount:")
                elif cmd == "2":
                    self.bet = 0; self.status = "WAITING"; self.bot.send_message(self.room, "⚔️ Fun Mode! Type `join` to start.")
                self.reset_timer(90, "inactivity")
                return True

            # 3. Bet Amt
            if self.status == "BET_AMT" and uid == self.creator and cmd.isdigit():
                amt = int(cmd)
                if amt > get_balance(uid): self.bot.send_message(self.room, "❌ Low Balance!"); return True
                self.bet = amt; self.status = "WAITING"
                self.bot.send_message(self.room, f"⚔️ Waiting for opponent ({amt} coins)... Type `join`.")
                self.reset_timer(90, "inactivity")
                return True

            # 4. Join
            if self.status == "WAITING" and cmd == "join":
                if uid == self.creator:
                    self.bot.send_message(self.room, "❌ You can't join your own game.")
                    return True
                if self.bet > 0 and get_balance(uid) < self.bet: 
                    self.bot.send_message(self.room, "❌ Low Balance!"); return True
                
                self.players['P2'] = uid; self.names['P2'] = name; self.avatars['P2'] = icon
                self.status = "PLAYING"
                self.send_game_update(f"⚔️ Match On! @{self.names['P1']} vs @{name}\nType `roll` to play.")
                self.reset_timer(30, "turn")
                return True

            # 5. Roll Dice
            if self.status == "PLAYING" and cmd == "roll":
                if uid != self.players[self.turn]: return False
                
                dice = random.randint(1, 6)
                old_p = self.pos[self.turn]
                new_p = old_p + dice
                
                log_msg = f"🎲 @{self.names[self.turn]} rolled {dice}."
                
                if new_p > 100:
                    log_msg += " (Too high, wait for next turn!)"
                    new_p = old_p
                else:
                    if new_p in LADDERS:
                        new_p = LADDERS[new_p]
                        log_msg += " 🪜 Ladder! Up you go!"
                    elif new_p in SNAKES:
                        new_p = SNAKES[new_p]
                        log_msg += " 🐍 Ouch! Snake bite!"
                
                self.pos[self.turn] = new_p
                
                # Check Win
                if new_p == 100:
                    self.finalize_game(self.turn)
                    return True
                
                # Swap Turn
                self.turn = "P2" if self.turn == "P1" else "P1"
                
                # Bot Logic
                if self.mode == "single" and self.turn == "P2":
                    b_dice = random.randint(1, 6)
                    b_old = self.pos["P2"]
                    b_new = b_old + b_dice
                    if b_new <= 100:
                        if b_new in LADDERS: b_new = LADDERS[b_new]
                        elif b_new in SNAKES: b_new = SNAKES[b_new]
                        self.pos["P2"] = b_new
                    
                    if self.pos["P2"] == 100:
                        self.finalize_game("P2")
                        return True
                    self.turn = "P1"
                    log_msg += f"\n🤖 Bot rolled {b_dice}. Bot is at {self.pos['P2']}."

                self.send_game_update(f"{log_msg}\nTurn: @{self.names[self.turn]}")
                self.reset_timer(30, "turn")
                return True
        return False

    def finalize_game(self, winner_sym):
        w_uid = self.players[winner_sym]
        amt = self.bet
        if self.mode == "single":
            if winner_sym == "P1":
                amt = 1000
                db.add_game_result(w_uid, self.names[winner_sym], "snake_ladder", amt, True)
        else:
            loser_sym = "P2" if winner_sym == "P1" else "P1"
            db.add_game_result(w_uid, self.names[winner_sym], "snake_ladder", amt, True)
            db.add_game_result(self.players[loser_sym], self.names[loser_sym], "snake_ladder", -amt, False)
        
        info = {'name': self.names[winner_sym], 'av': self.avatars[winner_sym], 'amt': amt}
        sl_executor.submit(self._bg_visual_task, None, f"🏆 {info['name']} reached 100!", True, info)
        self.cleanup()

    def reset_timer(self, sec, res):
        if self.timer: self.timer.cancel()
        self.timer = threading.Timer(sec, self.timeout_handler, [res])
        self.timer.daemon = True
        self.timer.start()

    def cleanup(self):
        self.status = "ENDED"
        if self.timer: self.timer.cancel()
        if self.room in active_sl: del active_sl[self.room]
        gc.collect()

# --- GLOBAL HANDLER ---
active_sl = {}

def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()
    uid = str(data.get("user_id", user))
    # Fix Avatar fetch
    icon = data.get("avatar_url", data.get("icon", data.get("avatar", "")))

    if cmd == "sl":
        if not args: return False
        if args[0] == "1":
            if room_name in active_sl:
                bot.send_message(room_name, "⚠️ Game already running!")
                return True
            active_sl[room_name] = SnakeLadderGame(bot, room_name, uid, user, icon)
            return True
        if args[0] == "0":
            if room_name in active_sl:
                active_sl[room_name].cleanup()
                bot.send_message(room_name, "🛑 Game stopped manually.")
            return True

    if room_name in active_games:
        return active_games[room_name].process_input(cmd, uid, user, icon)

    # Alias check for ROLL command
    if room_name in active_sl:
        return active_sl[room_name].process_input(cmd, uid, user, icon)

    return False
