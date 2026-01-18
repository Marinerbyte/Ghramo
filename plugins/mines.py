import time
import threading
import random
import gc
import io
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import concurrent.futures

# Local imports
import utils
import db

# --- CONFIGURATION ---
GRID_COLS, GRID_ROWS = 4, 3
CELL_COUNT = 12
IMG_W, IMG_H = 600, 450
CELL_SIZE = 150 
BG_DARK = (12, 14, 22)
RED_BLAST = (255, 69, 0)
ACCENT_GOLD = (255, 200, 40)

mines_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

def setup(bot):
    bot.log("💣 Mines (Full Multi-Mode) Loaded")

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
# 📦 MINES GAME CLASS
# ==========================================
class MinesGame:
    def __init__(self, bot, room, creator_id, creator_name, icon):
        self.bot, self.room, self.creator = bot, room, str(creator_id)
        self.lock = threading.Lock()
        
        self.players = {"P1": self.creator, "P2": None}
        self.names = {"P1": creator_name, "P2": None}
        self.avatars = {"P1": icon, "P2": ""}
        
        self.stats = {
            "P1": {"cookies": 0, "hp": 3},
            "P2": {"cookies": 0, "hp": 3}
        }
        
        # 8 Cookies, 4 Bombs
        tiles = (['C'] * 8) + (['B'] * 4)
        random.shuffle(tiles)
        self.grid = tiles
        self.revealed = [None] * CELL_COUNT 
        
        self.turn = "P1"
        self.status = "MODE_SELECT" 
        self.mode = None # single / multi
        self.bet = 0
        self.timer = None
        
        self.reset_timer(120, "inactivity")
        self.bot.send_message(self.room, "💣 **Mines PvP**\n`1` Single Player (vs Bot)\n`2` Multiplayer (PVP)")

    def reset_timer(self, sec, reason="turn"):
        if self.timer: self.timer.cancel()
        self.timer = threading.Timer(sec, self.timeout_handler, [reason])
        self.timer.daemon = True
        self.timer.start()

    # --- GRAPHICS: BOARD ---
    def draw_board(self):
        canvas = utils.create_canvas(IMG_W, IMG_H, color=BG_DARK)
        draw = ImageDraw.Draw(canvas)
        for i in range(CELL_COUNT):
            col, row = i % GRID_COLS, i // GRID_COLS
            x, y = col * CELL_SIZE, row * CELL_SIZE
            shape = [x+8, y+8, x+CELL_SIZE-8, y+CELL_SIZE-8]
            
            if self.revealed[i] is None:
                draw.rounded_rectangle(shape, radius=15, fill=(30, 35, 50), outline=(60, 70, 90), width=2)
                draw.text((x+60, y+50), str(i+1), font=utils.get_font("arial.ttf", 40), fill=(100, 110, 130))
            else:
                rev_by = self.revealed[i]
                content = self.grid[i]
                tile_color = (40, 120, 80) if content == 'C' else (180, 40, 40)
                draw.rounded_rectangle(shape, radius=15, fill=tile_color, outline="white", width=2)
                icon = "🍪" if content == 'C' else "💥"
                draw.text((x+20, y+85), icon, font=utils.get_font("arial.ttf", 30))
                utils.draw_circle_avatar(canvas, self.avatars[rev_by], x+75, y+45, 65, border_color=(255,255,255), border_width=2)
        return canvas

    # --- GRAPHICS: BLAST CARD ---
    def draw_blast_card(self, blasted_p_sym):
        W, H = 800, 500
        canvas = Image.new("RGB", (W, H), (10, 0, 0))
        draw = ImageDraw.Draw(canvas)
        utils.draw_gradient_bg(canvas, (60, 0, 0), (10, 0, 0))
        cx, cy = W//2, H//2
        utils.draw_circle_avatar(canvas, self.avatars[blasted_p_sym], cx-110, cy-130, 220, border_color=(255,0,0), border_width=8)
        for _ in range(25):
            draw.line([(cx, cy), (cx+random.randint(-350,350), cy+random.randint(-350,350))], fill=RED_BLAST, width=random.randint(3,10))
        f_hit = utils.get_font("arial.ttf", 90)
        draw.text((W//2, 100), "BOOM!", font=f_hit, fill=RED_BLAST, anchor="mm", stroke_width=4, stroke_fill="white")
        return canvas

    # --- GRAPHICS: WINNER CARD ---
    def draw_winner_card(self, winner_sym):
        W, H = 900, 600
        canvas = Image.new("RGB", (W, H), (12, 14, 22))
        draw = ImageDraw.Draw(canvas)
        utils.draw_gradient_bg(canvas, (12, 14, 22), (25, 40, 30))
        # Outer Glow
        utils.draw_rounded_rect(canvas, [50, 50, 850, 550], radius=40, color=(255, 180, 0, 30))
        # Main Panel
        utils.draw_rounded_rect(canvas, [70, 70, 830, 530], radius=30, color=(25, 28, 40))
        
        cx, cy = W//2, H//2 - 20
        utils.draw_circle_avatar(canvas, self.avatars[winner_sym], cx-100, cy-100, 200, border_color=ACCENT_GOLD, border_width=6)
        
        draw.text((W//2, 130), "SURVIVOR WINNER", font=utils.get_font("arial.ttf", 60), fill=ACCENT_GOLD, anchor="mm")
        draw.text((cx, cy + 130), self.names[winner_sym], font=utils.get_font("arial.ttf", 45), fill="white", anchor="mm")
        
        utils.draw_rounded_rect(canvas, [200, 450, 700, 520], radius=20, color=(35, 40, 60))
        draw.text((230, 465), f"🍪 Cookies: {self.stats[winner_sym]['cookies']}", font=utils.get_font("arial.ttf", 28), fill="white")
        draw.text((510, 465), f"💰 Reward: {self.bet if self.mode=='multi' else 1000}", font=utils.get_font("arial.ttf", 28), fill=ACCENT_GOLD)
        return canvas

    # --- LOGIC ---
    def process(self, cmd, uid, name, icon):
        uid = str(uid)
        with self.lock:
            # 1. MODE SELECT
            if self.status == "MODE_SELECT" and uid == self.creator:
                if cmd == "1":
                    self.mode, self.players["P2"], self.names["P2"], self.status = "single", "BOT", "Bot 🤖", "PLAYING"
                    self.avatars["P2"] = "https://robohash.org/minesbot"
                    self.send_update("🎮 **Single Player Started!** Type 1-12.")
                    self.reset_timer(120)
                elif cmd == "2":
                    self.mode, self.status = "multi", "BET_TYPE"
                    self.bot.send_message(self.room, "⚖️ **Multiplayer**\n`1` With Bet\n`2` No Bet")
                return True

            # 2. BET TYPE
            if self.status == "BET_TYPE" and uid == self.creator:
                if cmd == "1": self.status = "BET_AMT"; self.bot.send_message(self.room, "💰 Enter Bet Amount:")
                elif cmd == "2": self.bet, self.status = 0, "WAITING"; self.bot.send_message(self.room, "⚔️ Fun Mode! Type `join`.")
                return True

            # 3. BET AMT
            if self.status == "BET_AMT" and uid == self.creator and cmd.isdigit():
                amt = int(cmd)
                if amt > get_balance(uid): self.bot.send_message(self.room, "❌ Low Balance!"); return True
                self.bet, self.status = amt, "WAITING"
                self.bot.send_message(self.room, f"⚔️ Betting {amt}. Type `join`.")
                return True

            # 4. JOIN
            if self.status == "WAITING" and cmd == "join" and uid != self.creator:
                if self.bet > get_balance(uid): self.bot.send_message(self.room, "❌ Low Balance!"); return True
                self.players["P2"], self.names["P2"], self.avatars["P2"] = uid, name, icon
                self.status = "PLAYING"
                self.send_update(f"⚔️ **Match On!** @{self.names['P1']} vs @{name}")
                self.reset_timer(120)
                return True

            # 5. PLAY
            if self.status == "PLAYING" and cmd.isdigit():
                if uid != self.players[self.turn]: return False
                idx = int(cmd) - 1
                if 0 <= idx < CELL_COUNT and self.revealed[idx] is None:
                    self.revealed[idx] = self.turn
                    content = self.grid[idx]
                    curr_p, opp_p = self.turn, ("P2" if self.turn == "P1" else "P1")
                    
                    if content == 'C':
                        self.stats[curr_p]['cookies'] += 1
                        msg = f"🍪 @{self.names[curr_p]} found a cookie! Safe."
                        self.turn = opp_p
                    else:
                        self.stats[curr_p]['hp'] -= 1
                        self.trigger_blast(curr_p)
                        if self.stats[curr_p]['hp'] <= 0:
                            self.end_game(opp_p)
                            return True
                        msg = f"💥 BOOM! @{self.names[curr_p]} blasted! ({self.stats[curr_p]['hp']} HP left)"
                        self.turn = opp_p

                    # Bot move logic
                    if self.mode == "single" and self.turn == "P2":
                        unrev = [i for i, v in enumerate(self.revealed) if v is None]
                        if unrev:
                            b_idx = random.choice(unrev)
                            self.revealed[b_idx] = "P2"
                            if self.grid[b_idx] == 'C':
                                self.stats["P2"]['cookies'] += 1
                                msg += f"\n🤖 Bot found a cookie! Safe."
                            else:
                                self.stats["P2"]['hp'] -= 1
                                if self.stats["P2"]['hp'] <= 0:
                                    self.end_game("P1")
                                    return True
                                msg += f"\n💥 BOOM! Bot hit a bomb!"
                            self.turn = "P1"

                    self.send_update(f"{msg}\nNext Turn: @{self.names[self.turn]}")
                    self.reset_timer(120)
                    return True
        return False

    def trigger_blast(self, p_sym):
        def task():
            img = self.draw_blast_card(p_sym)
            url = utils.upload_image(img)
            if url: self.bot.send_image(self.room, url)
        threading.Thread(target=task, daemon=True).start()

    def send_update(self, text=""):
        def task():
            img = self.draw_board()
            url = utils.upload_image(img)
            if url: self.bot.send_image(self.room, url)
            if text: self.bot.send_message(self.room, text)
        threading.Thread(target=task, daemon=True).start()

    def end_game(self, winner_sym):
        self.status = "ENDED"
        w_uid, w_name = self.players[winner_sym], self.names[winner_sym]
        amt = self.bet
        if self.mode == "single":
            amt = 1000 if winner_sym == "P1" else 0
            if amt > 0: db.add_game_result(w_uid, w_name, "mines", amt, True)
        else:
            db.add_game_result(w_uid, w_name, "mines", amt, True)
            db.add_game_result(self.players["P2" if winner_sym=="P1" else "P1"], self.names["P2" if winner_sym=="P1" else "P1"], "mines", -amt, False)
        
        def win_task():
            img = self.draw_winner_card(winner_sym)
            url = utils.upload_image(img)
            if url: self.bot.send_image(self.room, url)
            self.bot.send_message(self.room, f"🏆 GAME OVER! @{w_name} is the Survivor!")
            self.cleanup()
        threading.Thread(target=win_task, daemon=True).start()

    def timeout_handler(self, reason):
        with self.lock:
            if self.status == "ENDED": return
            if reason == "inactivity": self.bot.send_message(self.room, "⚠️ Mines game stopped."); self.cleanup()
            else: self.end_game("P2" if self.turn == "P1" else "P1")

    def cleanup(self):
        if self.timer: self.timer.cancel()
        if self.room in active_mines: del active_mines[self.room]
        gc.collect()

# --- HANDLER ---
active_mines = {}
def handle_command(bot, command, room_name, user, args, data):
    cmd, uid = command.lower().strip(), str(data.get("user_id", user))
    icon = data.get("avatar_url", data.get("icon", data.get("avatar", "")))
    if cmd == "mines":
        if args and args[0] == "1":
            if room_name in active_mines: return True
            active_mines[room_name] = MinesGame(bot, room_name, uid, user, icon)
            return True
        if args and args[0] == "0":
            if room_name in active_mines: active_mines[room_name].cleanup(); bot.send_message(room_name, "🛑 Stopped.")
            return True
    if room_name in active_mines:
        return active_mines[room_name].process(cmd, uid, user, icon)
    return False
