import time
import threading
import random
import gc
from PIL import Image, ImageDraw, ImageFont
import concurrent.futures

import utils
import db

# --- CONFIG ---
CELL_COUNT = 12
IMG_W, IMG_H = 600, 450
CELL_SIZE = 150 
BG_DARK = (12, 14, 22)

mines_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

def setup(bot):
    bot.log("💣 Mines: Revenge (Final Logic v5) Loaded")

# ==========================================
# 📦 MINES GAME CLASS
# ==========================================
class MinesRevengeGame:
    def __init__(self, bot, room, p1_id, p1_name, p1_icon):
        self.bot, self.room = bot, room
        self.lock = threading.Lock()
        self.players = {"P1": str(p1_id), "P2": None}
        self.names = {"P1": p1_name, "P2": None}
        self.avatars = {"P1": p1_icon, "P2": ""}
        self.boards = {"P1": ['C'] * 12, "P2": ['C'] * 12}
        self.revealed = {"P1": [False] * 12, "P2": [False] * 12}
        self.hp = {"P1": 3, "P2": 3}
        self.setup_state = {"P1": 0, "P2": 0}
        self.turn = "P1"
        self.status = "WAITING"
        self.timer = None
        self.reset_timer(120)
        self.bot.send_message(self.room, "💣 **Mines: Revenge!** Type `join` to challenge!")

    def reset_timer(self, sec):
        if self.timer: self.timer.cancel()
        self.timer = threading.Timer(sec, self.cleanup)
        self.timer.daemon = True
        self.timer.start()

    # --- GRAPHICS ---
    def draw_board(self, player_to_show):
        canvas = utils.create_canvas(IMG_W, IMG_H, color=BG_DARK)
        draw = ImageDraw.Draw(canvas)
        board_data = self.boards[player_to_show]; revealed_data = self.revealed[player_to_show]
        for i in range(CELL_COUNT):
            col, row = i % 4, i // 4; x, y = col * CELL_SIZE, row * CELL_SIZE
            shape = [x+8,y+8,x+CELL_SIZE-8,y+CELL_SIZE-8]
            if not revealed_data[i]:
                draw.rounded_rectangle(shape, 15, (30,35,50), (60,70,90), 2)
                draw.text((x+60,y+50), str(i+1), font=utils.get_font("arial.ttf",40), fill=(100,110,130))
            else:
                content = board_data[i]; color = (40,120,80) if content == 'C' else (180,40,40)
                draw.rounded_rectangle(shape, 15, color, "white", 2)
                draw.text((x+55,y+45), "🍪" if content == 'C' else "💥", font=utils.get_font("arial.ttf",50))
        return canvas

    # --- LOGIC ---
    def process_room(self, cmd, uid, name, icon):
        uid = str(uid)
        with self.lock:
            # JOIN
            if self.status == "WAITING" and cmd.lower() == "join" and uid != self.players['P1']:
                self.players["P2"], self.names["P2"], self.avatars["P2"] = uid, name, icon
                self.status = "SETUP"
                self.bot.send_message(self.room, f"⚔️ **Match On!** @{self.names['P1']} vs @{name}\n**==> Check PMs to set traps! <==**")
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
                        msg = f"🍪 Safe! @{name} found a cookie."
                    else:
                        self.hp[self.turn] -= 1
                        msg = f"💥 BOOM! @{name} blasted! ({self.hp[self.turn]} HP left)"
                    
                    self.turn = opponent
                    self.send_board_update(opponent, f"{msg}\nNext Turn: @{self.names[opponent]}")
                    
                    if self.hp[self.turn] <= 0:
                        self.end_game(opponent); return True
                        
                    self.reset_timer(120)
                    return True
        return False

    def process_pm(self, cmd, user_id):
        user_id = str(user_id)
        with self.lock:
            if self.status != "SETUP": return False
            player_sym = "P1" if user_id == self.players["P1"] else "P2" if user_id == self.players["P2"] else None
            if player_sym and cmd.isdigit():
                idx = int(cmd) - 1
                opponent = "P2" if player_sym == "P1" else "P1"
                if 0 <= idx < 12 and self.boards[opponent][idx] == 'C' and self.setup_state[player_sym] < 3:
                    self.boards[opponent][idx] = 'B'
                    self.setup_state[player_sym] += 1
                    bombs_left = 3 - self.setup_state[player_sym]
                    if bombs_left > 0:
                        self.bot.send_pm_message(user_id, f"💣 Bomb placed at {cmd}. Choose {bombs_left} more.")
                    else:
                        self.bot.send_pm_message(user_id, "✅ Done! Your traps are set. Waiting for opponent."); self.check_if_ready()
                    return True
        return False
        
    def start_setup(self):
        msg = "🤫 **SECRET MISSION** 🤫\nPlace 3 bombs on opponent's board.\nChoose your first number (1-12):\n1 2 3 4 | 5 6 7 8 | 9 10 11 12"
        for p in ["P1", "P2"]:
            if self.players[p]: self.bot.send_pm_message(self.players[p], msg)

    def check_if_ready(self):
        if self.setup_state["P1"] == 3 and self.setup_state["P2"] == 3:
            self.status = "PLAYING"
            self.bot.send_message(self.room, "🔥 **Traps are set! The game begins!**")
            # Player 1 starts by attacking Player 2's board
            self.send_board_update("P2", f"Board for @{self.names['P1']} to attack. Pick a box (1-12):")

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

# --- GLOBAL HANDLER ---
active_revenge = {}

def handle_command(bot, command, room_name, user, args, data):
    cmd, uid = command.lower().strip(), str(data.get("user_id", user))
    icon = data.get("avatar_url", "")
    
    if cmd == "mines":
        if room_name not in active_revenge:
            active_revenge[room_name] = MinesRevengeGame(bot, room_name, uid, user, icon)
        return True
            
    if room_name in active_revenge:
        return active_revenge[room_name].process_room(cmd, uid, user, icon)
    return False

def handle_pm(bot, command, user, args, data):
    cmd, uid = command.lower().strip(), str(data.get("from_id", user)) # Use from_id for PM
    for game in list(active_revenge.values()):
        if uid in game.players.values():
            if game.process_pm(cmd, uid):
                return True
    return False
