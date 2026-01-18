import time
import threading
import random
import gc
import io
from PIL import Image, ImageDraw, ImageFont
import concurrent.futures

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
    bot.log("💣 Mines: Revenge (PvP Setup) Loaded")

# ==========================================
# 📦 MINES REVENGE CLASS
# ==========================================
class MinesRevengeGame:
    def __init__(self, bot, room, p1_id, p1_name, p1_icon):
        self.bot, self.room = bot, room
        self.lock = threading.Lock()
        
        self.players = {"P1": str(p1_id), "P2": None}
        self.names = {"P1": p1_name, "P2": None}
        self.avatars = {"P1": p1_icon, "P2": ""}
        
        # Dono players ke liye alag board
        self.boards = {"P1": ['C'] * 12, "P2": ['C'] * 12}
        self.revealed = {"P1": [False] * 12, "P2": [False] * 12}
        self.hp = {"P1": 3, "P2": 3}
        
        # Setup state
        self.setup_state = {"P1": 0, "P2": 0} # 0-3 bombs placed
        
        self.turn = "P1"
        self.status = "WAITING" # WAITING -> SETUP -> PLAYING -> ENDED
        self.timer = None
        self.reset_timer(120)
        self.bot.send_message(self.room, "💣 **Mines: Revenge!**\nPlayers will set bombs for each other in PM.\nType `join` to challenge!")

    def reset_timer(self, sec):
        if self.timer: self.timer.cancel()
        self.timer = threading.Timer(sec, self.cleanup)
        self.timer.daemon = True
        self.timer.start()

    # --- GRAPHICS ---
    def draw_board(self, player_to_show):
        canvas = utils.create_canvas(IMG_W, IMG_H, color=BG_DARK)
        draw = ImageDraw.Draw(canvas)
        
        board_data = self.boards[player_to_show]
        revealed_data = self.revealed[player_to_show]
        
        for i in range(CELL_COUNT):
            col, row = i % GRID_COLS, i // GRID_COLS
            x, y = col * CELL_SIZE, row * CELL_SIZE
            shape = [x+8, y+8, x+CELL_SIZE-8, y+CELL_SIZE-8]
            
            if not revealed_data[i]:
                draw.rounded_rectangle(shape, 15, (30,35,50), (60,70,90), 2)
                draw.text((x+60,y+50), str(i+1), font=utils.get_font("arial.ttf",40), fill=(100,110,130))
            else:
                content = board_data[i]
                color = (40,120,80) if content == 'C' else (180,40,40)
                draw.rounded_rectangle(shape, 15, color, "white", 2)
                icon = "🍪" if content == 'C' else "💥"
                draw.text((x+55,y+45), icon, font=utils.get_font("arial.ttf",50))
        return canvas

    # (Blast card and winner card logic will be similar)

    # --- LOGIC ---
    def process_room(self, cmd, uid, name, icon):
        uid = str(uid)
        with self.lock:
            # JOIN
            if self.status == "WAITING" and cmd == "join" and uid != self.players['P1']:
                self.players["P2"], self.names["P2"], self.avatars["P2"] = uid, name, icon
                self.status = "SETUP"
                self.bot.send_message(self.room, f"⚔️ **Match On!** @{self.names['P1']} vs @{name}\nCheck your PMs to set up the bomb traps!")
                self.start_setup()
                return True

            # PLAY
            if self.status == "PLAYING" and cmd.isdigit():
                if uid != self.players[self.turn]: return False
                
                idx = int(cmd) - 1
                opponent = "P2" if self.turn == "P1" else "P1"
                
                if 0 <= idx < 12 and not self.revealed[opponent][idx]:
                    self.revealed[opponent][idx] = True
                    content = self.boards[opponent][idx]
                    
                    if content == 'C':
                        self.send_board_update(opponent, f"🍪 Safe! @{name} found a cookie.\nNext: @{self.names[opponent]}")
                        self.turn = opponent
                    else:
                        self.hp[self.turn] -= 1
                        # (Blast card effect can be added here)
                        if self.hp[self.turn] <= 0:
                            self.end_game(opponent)
                            return True
                        self.send_board_update(opponent, f"💥 BOOM! @{name} blasted! ({self.hp[self.turn]} HP left)\nNext: @{self.names[opponent]}")
                        self.turn = opponent
                    
                    self.reset_timer(120)
                    return True
        return False

    def process_pm(self, cmd, uid):
        uid = str(uid)
        with self.lock:
            if self.status != "SETUP": return False
            
            player_sym = None
            if uid == self.players["P1"]: player_sym = "P1"
            elif uid == self.players["P2"]: player_sym = "P2"
            else: return False

            if cmd.isdigit():
                idx = int(cmd) - 1
                opponent = "P2" if player_sym == "P1" else "P1"
                
                if 0 <= idx < 12 and self.boards[opponent][idx] == 'C':
                    self.boards[opponent][idx] = 'B'
                    self.setup_state[player_sym] += 1
                    
                    bombs_left = 3 - self.setup_state[player_sym]
                    if bombs_left > 0:
                        self.bot.send_pm_message(uid, f"💣 Bomb placed at {cmd}. Choose {bombs_left} more.")
                    else:
                        self.bot.send_pm_message(uid, "✅ Done! Your traps are set. Waiting for opponent.")
                        self.check_if_ready()
                    return True
        return False
        
    def start_setup(self):
        numbers = "1 2 3 4\n5 6 7 8\n9 10 11 12"
        for p_sym in ["P1", "P2"]:
            uid = self.players[p_sym]
            self.bot.send_pm_message(uid, "🤫 **SECRET MISSION** 🤫\nPlace 3 bombs on your opponent's board.\nChoose your first number (1-12):\n" + numbers)

    def check_if_ready(self):
        if self.setup_state["P1"] == 3 and self.setup_state["P2"] == 3:
            self.status = "PLAYING"
            self.bot.send_message(self.room, "🔥 **Both players are ready! Let the hunt begin!**")
            self.send_board_update("P2", f"Board for @{self.names['P1']} to attack. Pick a number:")

    def send_board_update(self, board_owner_sym, text):
        def task():
            img = self.draw_board(board_owner_sym)
            url = utils.upload_image(img)
            if url: self.bot.send_image(self.room, url)
            if text: self.bot.send_message(self.room, text)
        threading.Thread(target=task, daemon=True).start()

    def end_game(self, winner_sym):
        self.status = "ENDED"
        db.add_game_result(self.players[winner_sym], self.names[winner_sym], "mines_revenge", 500, True)
        self.bot.send_message(self.room, f"🏆 GAME OVER! @{self.names[winner_sym]} is the winner!")
        self.cleanup()

    def cleanup(self):
        if self.timer: self.timer.cancel()
        if self.room in active_revenge: del active_revenge[self.room]
        gc.collect()

# --- GLOBAL HANDLER ---
active_revenge = {}

def handle_command(bot, command, room_name, user, args, data):
    cmd, uid = command.lower().strip(), str(data.get("user_id", user))
    icon = data.get("avatar_url", "")
    
    if cmd == "mines":
        if room_name in active_revenge: return True
        active_revenge[room_name] = MinesRevengeGame(bot, room_name, uid, user, icon)
        return True
            
    if room_name in active_revenge:
        return active_revenge[room_name].process_room(cmd, uid, user, icon)

    return False

def handle_pm(bot, command, user, args, data):
    cmd = command.lower().strip()
    uid = str(data.get("from_id", user)) # Some PMs might have from_id
    
    # Check all active games if this PM is for them
    for game in active_revenge.values():
        if uid in game.players.values():
            return game.process_pm(cmd, uid)
    
    return False
