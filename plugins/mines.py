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
    bot.log("💣 Mines (Self-Blast Edition) Loaded")

# ==========================================
# 📦 MINES GAME CLASS
# ==========================================
class MinesGame:
    def __init__(self, bot, room, creator_id, creator_name, icon):
        self.bot, self.room, self.creator = bot, room, creator_id
        self.lock = threading.Lock()
        
        self.players = {"P1": creator_id, "P2": None}
        self.names = {"P1": creator_name, "P2": None}
        self.avatars = {"P1": icon, "P2": ""}
        
        self.stats = {
            "P1": {"cookies": 0, "bombs": 0, "hp": 3},
            "P2": {"cookies": 0, "bombs": 0, "hp": 3}
        }
        
        # 8 Cookies, 4 Bombs
        tiles = (['C'] * 8) + (['B'] * 4)
        random.shuffle(tiles)
        self.grid = tiles
        self.revealed = [None] * CELL_COUNT 
        
        self.turn = "P1"
        self.status = "WAITING" 
        self.timer = None
        self.reset_timer(120)
        self.bot.send_message(self.room, "💣 **Mines: Self-Blast Mode!**\nDon't touch the bombs! 3 Blasts = Game Over.\nType `join` to challenge!")

    def reset_timer(self, sec):
        if self.timer: self.timer.cancel()
        self.timer = threading.Timer(sec, self.cleanup)
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
                # Tile pe hamesha kholne wale ki DP dikhegi
                utils.draw_circle_avatar(canvas, self.avatars[rev_by], x+75, y+45, 65, border_color=(255,255,255), border_width=2)
                    
        return canvas

    # --- GRAPHICS: HIT CARD (BLAST EFFECT) ---
    def draw_hit_card(self, blasted_player_sym):
        W, H = 800, 500
        canvas = Image.new("RGB", (W, H), (10, 0, 0))
        draw = ImageDraw.Draw(canvas)
        utils.draw_gradient_bg(canvas, (60, 0, 0), (10, 0, 0))

        cx, cy = W//2, H//2
        # Blasted Player's BIG Avatar
        utils.draw_circle_avatar(canvas, self.avatars[blasted_player_sym], cx-110, cy-130, 220, border_color=(255,0,0), border_width=8)

        # Blast Particles
        for _ in range(20):
            draw.line([(cx, cy), (cx+random.randint(-300,300), cy+random.randint(-300,300))], fill=RED_BLAST, width=random.randint(2,8))

        f_hit = utils.get_font("arial.ttf", 90)
        draw.text((W//2, 100), "BOOM!", font=f_hit, fill=RED_BLAST, anchor="mm", stroke_width=4, stroke_fill="white")
        draw.text((W//2, 420), f"@{self.names[blasted_player_sym]} BLASTED!", font=utils.get_font("arial.ttf", 40), fill="white", anchor="mm")
        return canvas

    # --- GRAPHICS: FINAL WINNER CARD ---
    def draw_winner_card(self, winner_sym):
        W, H = 900, 600
        canvas = Image.new("RGB", (W, H), (12, 14, 22))
        draw = ImageDraw.Draw(canvas)
        utils.draw_gradient_bg(canvas, (12, 14, 22), (30, 60, 30))

        cx, cy = W//2, H//2 - 20
        utils.draw_circle_avatar(canvas, self.avatars[winner_sym], cx-100, cy-100, 200, border_color=ACCENT_GOLD, border_width=6)

        draw.text((W//2, 120), "SURVIVOR WINNER", font=utils.get_font("arial.ttf", 60), fill=ACCENT_GOLD, anchor="mm")
        draw.text((cx, cy + 130), self.names[winner_sym], font=utils.get_font("arial.ttf", 45), fill="white", anchor="mm")
        
        # Stats Bar
        utils.draw_rounded_rect(canvas, [200, 450, 700, 520], radius=20, color=(35, 40, 60))
        draw.text((230, 465), f"🍪 Cookies: {self.stats[winner_sym]['cookies']}", font=utils.get_font("arial.ttf", 28), fill="white")
        draw.text((500, 465), f"❤️ HP Left: {self.stats[winner_sym]['hp']}", font=utils.get_font("arial.ttf", 28), fill=RED_BLAST)
        return canvas

    # --- LOGIC HANDLING ---
    def process(self, cmd, uid, name, icon):
        with self.lock:
            if self.status == "WAITING" and cmd == "join":
                if uid == self.creator: return True
                self.players["P2"], self.names["P2"], self.avatars["P2"] = uid, name, icon
                self.status = "PLAYING"
                self.send_board_update(f"⚔️ Match On! @{self.names['P1']} vs @{name}\nType 1-12 to eat cookies!")
                return True

            if self.status == "PLAYING" and cmd.isdigit():
                if uid != self.players[self.turn]: return False
                
                idx = int(cmd) - 1
                if 0 <= idx < CELL_COUNT and self.revealed[idx] is None:
                    self.revealed[idx] = self.turn
                    content = self.grid[idx]
                    curr_p = self.turn
                    opp_p = "P2" if curr_p == "P1" else "P1"
                    
                    if content == 'C':
                        self.stats[curr_p]['cookies'] += 1
                        msg = f"🍪 @{self.names[curr_p]} ate a cookie and is safe!"
                        self.turn = opp_p # Turn badlo
                        self.send_board_update(f"{msg}\nNext: @{self.names[self.turn]}")
                    else:
                        # 🔥 SELF BLAST LOGIC
                        self.stats[curr_p]['hp'] -= 1
                        self.stats[curr_p]['bombs'] += 1
                        self.trigger_hit_effect(curr_p)
                        
                        if self.stats[curr_p]['hp'] <= 0:
                            self.end_game(opp_p) # Saamne wala jeeta
                            return True
                        
                        msg = f"💥 BOOM! @{self.names[curr_p]} hit a bomb! ({self.stats[curr_p]['hp']} HP left)"
                        self.turn = opp_p # Turn badlo
                        self.send_board_update(f"{msg}\nNext: @{self.names[self.turn]}")
                    
                    self.reset_timer(120)
                    return True
        return False

    def trigger_hit_effect(self, blasted_p_sym):
        def task():
            img = self.draw_hit_card(blasted_p_sym)
            url = utils.upload_image(img)
            if url: self.bot.send_image(self.room, url)
        threading.Thread(target=task, daemon=True).start()

    def send_board_update(self, text=""):
        def task():
            img = self.draw_board()
            url = utils.upload_image(img)
            if url: self.bot.send_image(self.room, url)
            if text: self.bot.send_message(self.room, text)
        threading.Thread(target=task, daemon=True).start()

    def end_game(self, winner_sym):
        self.status = "ENDED"
        w_name = self.names[winner_sym]
        db.add_game_result(self.players[winner_sym], w_name, "mines", 500, True)
        
        def win_task():
            img = self.draw_winner_card(winner_sym)
            url = utils.upload_image(img)
            if url: self.bot.send_image(self.room, url)
            self.bot.send_message(self.room, f"🏆 @{w_name} is the last survivor!")
            self.cleanup()
        threading.Thread(target=win_task, daemon=True).start()

    def cleanup(self):
        if self.timer: self.timer.cancel()
        if self.room in active_mines: del active_mines[self.room]
        gc.collect()

# --- GLOBAL HANDLER ---
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
