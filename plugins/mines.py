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
GRID_SIZE = 5
CELL_COUNT = 25
IMG_SIZE = 500
CELL_SIZE = IMG_SIZE // GRID_SIZE # 100px

# Colors
BG_DARK = (12, 14, 22)
NEON_BLUE = (44, 255, 255)
ACCENT_GOLD = (255, 200, 40)

mines_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

def setup(bot):
    bot.log("💣 Mines PvP (Bomb vs Cookie) Loaded")

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
        
        # Stats for Winner Card
        self.stats = {
            "P1": {"cookies": 0, "bombs": 0, "hp": 3},
            "P2": {"cookies": 0, "bombs": 0, "hp": 3}
        }
        
        # Grid Setup: 'C' for Cookie, 'B' for Bomb
        tiles = (['C'] * 15) + (['B'] * 10)
        random.shuffle(tiles)
        self.grid = tiles
        self.revealed = [False] * CELL_COUNT
        
        self.turn = "P1"
        self.status = "WAITING" # WAITING -> PLAYING -> ENDED
        self.timer = None
        
        self.reset_timer(120)
        self.bot.send_message(self.room, "💣 **Mines PvP Started!**\n25 Tiles: Find Cookies 🍪 or Drop Bombs 💣\nType `join` to challenge!")

    def reset_timer(self, sec):
        if self.timer: self.timer.cancel()
        self.timer = threading.Timer(sec, self.cleanup)
        self.timer.daemon = True
        self.timer.start()

    # --- GRAPHICS: BOARD ---
    def draw_board(self):
        canvas = utils.create_canvas(IMG_SIZE, IMG_SIZE, color=BG_DARK)
        draw = ImageDraw.Draw(canvas)
        font = utils.get_font("arial.ttf", 30)
        
        for i in range(CELL_COUNT):
            x = (i % GRID_SIZE) * CELL_SIZE
            y = (i // GRID_SIZE) * CELL_SIZE
            
            # Tile Box
            shape = [x+5, y+5, x+CELL_SIZE-5, y+CELL_SIZE-5]
            if not self.revealed[i]:
                # Hidden Tile (Arcade Style)
                draw.rounded_rectangle(shape, radius=10, fill=(30, 35, 50), outline=(60, 70, 90), width=2)
                draw.text((x+35, y+30), str(i+1), font=font, fill=(100, 110, 130))
            else:
                # Revealed Tile
                content = self.grid[i]
                color = (40, 180, 100) if content == 'C' else (200, 50, 50)
                draw.rounded_rectangle(shape, radius=10, fill=color, outline="white", width=2)
                icon = "🍪" if content == 'C' else "💣"
                draw.text((x+30, y+25), icon, font=font, fill="white")
        return canvas

    # --- GRAPHICS: PREMIUM WINNER CARD ---
    def draw_winner_card(self, winner_p):
        W, H = 900, 600
        winner_name = self.names[winner_p]
        winner_avatar = self.avatars[winner_p]
        cookies = self.stats[winner_p]['cookies']
        bombs = self.stats[winner_p]['bombs']

        # 1. Base
        canvas = Image.new("RGB", (W, H), (12, 14, 22))
        draw = ImageDraw.Draw(canvas)
        utils.draw_gradient_bg(canvas, (12, 14, 22), (25, 30, 50))

        # 2. Outer Glow Frame
        utils.draw_rounded_rect(canvas, [50, 50, 850, 550], radius=40, color=(255, 180, 0, 30))
        
        # 3. Main Card Panel
        utils.draw_rounded_rect(canvas, [70, 70, 830, 530], radius=30, color=(25, 28, 40))

        # 4. Winner Avatar (Big Center)
        cx, cy = W//2, H//2 - 20
        # Avatar Glow
        draw.ellipse([cx-110, cy-110, cx+110, cy+110], outline=ACCENT_GOLD, width=10)
        utils.draw_circle_avatar(canvas, winner_avatar, cx-100, cy-100, 200, border_color="white", border_width=4)

        # 5. Text
        f_title = utils.get_font("arial.ttf", 70)
        f_name = utils.get_font("arial.ttf", 45)
        f_stat = utils.get_font("arial.ttf", 28)

        draw.text((W//2, 130), "WINNER", font=f_title, fill=ACCENT_GOLD, anchor="mm")
        draw.text((cx, cy + 130), winner_name, font=f_name, fill="white", anchor="mm")
        draw.text((cx, cy + 175), "Champion of the Match", font=f_stat, fill=(180, 180, 180), anchor="mm")

        # 6. Stats Bar
        stats_y = 450
        utils.draw_rounded_rect(canvas, [200, stats_y, 700, stats_y+70], radius=20, color=(35, 40, 60))
        draw.text((230, stats_y+18), f"🍪 {cookies} Safe Cookies", font=f_stat, fill="white")
        draw.text((490, stats_y+18), f"💣 {bombs} Bombs Used", font=f_stat, fill=NEON_BLUE)

        return canvas

    # --- LOGIC HANDLING ---
    def process(self, cmd, uid, name, icon):
        with self.lock:
            # 1. Join Logic
            if self.status == "WAITING" and cmd == "join":
                if uid == self.creator: return True
                self.players["P2"], self.names["P2"], self.avatars["P2"] = uid, name, icon
                self.status = "PLAYING"
                self.bot.send_message(self.room, f"⚔️ **Match On!** @{self.names['P1']} vs @{name}\nP1 starts! Pick a number 1-25.")
                self.send_board_update()
                self.reset_timer(120)
                return True

            # 2. Pick Tile Logic
            if self.status == "PLAYING" and cmd.isdigit():
                if uid != self.players[self.turn]: return False
                
                idx = int(cmd) - 1
                if 0 <= idx < CELL_COUNT and not self.revealed[idx]:
                    self.revealed[idx] = True
                    content = self.grid[idx]
                    current_p = self.turn
                    opponent_p = "P2" if current_p == "P1" else "P1"
                    
                    msg = ""
                    if content == 'C':
                        self.stats[current_p]['cookies'] += 1
                        msg = f"🍪 @{self.names[current_p]} found a Safe Cookie!"
                    else:
                        self.stats[current_p]['bombs'] += 1
                        self.stats[opponent_p]['hp'] -= 1
                        msg = f"💣 BOOM! @{self.names[current_p]} triggered a bomb on @{self.names[opponent_p]}!"
                    
                    # Check End Game
                    if self.stats[opponent_p]['hp'] <= 0 or self.revealed.count(True) == CELL_COUNT:
                        self.end_game(current_p, "Victory!")
                        return True
                    
                    # Swap Turn
                    self.turn = opponent_p
                    self.send_board_update(f"{msg}\nNext Turn: @{self.names[self.turn]}")
                    self.reset_timer(120)
                    return True
        return False

    def send_board_update(self, text=""):
        mines_executor.submit(self._bg_task, text)

    def _bg_task(self, text):
        img = self.draw_board()
        url = utils.upload_image(img)
        if url: self.bot.send_image(self.room, url)
        if text: self.bot.send_message(self.room, text)

    def end_game(self, winner_p, reason):
        self.status = "ENDED"
        winner_name = self.names[winner_p]
        
        # Database Score Update
        db.add_game_result(self.players[winner_p], winner_name, "mines", 500, True)
        
        # Winner Card Image
        def win_task():
            img = self.draw_winner_card(winner_p)
            url = utils.upload_image(img)
            if url: self.bot.send_image(self.room, url)
            self.bot.send_message(self.room, f"🎉 @{winner_name} wins the Mines match!")
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
    icon = data.get("avatar_url", data.get("icon", ""))
    
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
