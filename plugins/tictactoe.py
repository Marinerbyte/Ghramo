import time
import random
import requests
import io
import sys
import os
import threading
import traceback
import urllib3
import uuid
from PIL import Image, ImageDraw, ImageFont

# SSL warnings disable karne ke liye
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- DB IMPORT ---
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    import db
except Exception as e:
    print(f"DB Import Error: {e}")

# --- GLOBAL STATE ---
games = {} 
games_lock = threading.Lock()
BOT_INSTANCE = None 

# ✅ STABLE UPLOADER: Catbox.moe (Direct Link)
def upload_image(bot, image):
    """Board ko Catbox par upload karke direct link leta hai"""
    try:
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        files = {
            'reqtype': (None, 'fileupload'),
            'fileToUpload': ('board.png', img_byte_arr, 'image/png')
        }
        
        r = requests.post('https://catbox.moe/user/api.php', files=files, timeout=15)
        
        if r.status_code == 200 and "http" in r.text:
            url = r.text.strip()
            bot.log(f"✅ Board Uploaded (Catbox): {url}")
            return url
        else:
            bot.log(f"❌ Upload Failed: {r.text}")
    except Exception as e:
        bot.log(f"❌ Upload Error: {e}")
    return None

# --- VISUALS (NEON BOARD DESIGN) ---
def draw_board(board_state):
    size = 450
    cell = size // 3
    # Modern dark background
    img = Image.new('RGB', (size, size), color=(15, 17, 26)) 
    d = ImageDraw.Draw(img)
    
    # Grid Lines
    for i in range(1, 3):
        d.line([(cell * i, 20), (cell * i, size - 20)], fill=(45, 48, 65), width=6)
        d.line([(20, cell * i), (size - 20, cell * i)], fill=(45, 48, 65), width=6)
    
    try:
        font_large = ImageFont.truetype("arial.ttf", 70)
        font_small = ImageFont.truetype("arial.ttf", 40)
    except:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    for i in range(9):
        row, col = i // 3, i % 3
        x, y = col * cell, row * cell
        cx, cy = x + cell // 2, y + cell // 2
        val = board_state[i]
        
        if val is None:
            # Hint numbers
            d.text((cx-15, cy-25), str(i+1), font=font_small, fill=(40, 42, 54)) 
        elif val == 'X':
            # Neon Pink/Red X
            off = 45
            d.line([(x+off, y+off), (x+cell-off, y+cell-off)], fill=(255, 46, 99), width=15)
            d.line([(x+cell-off, y+off), (x+off, y+cell-off)], fill=(255, 46, 99), width=15)
        elif val == 'O':
            # Neon Cyan Blue O
            off = 45
            d.ellipse([(x+off, y+off), (x+cell-off, y+cell-off)], outline=(0, 242, 255), width=15)
    return img

class TicTacToe:
    def __init__(self, room, p1_id, p1_name):
        self.room = room
        self.p1_id = p1_id
        self.p1_name = p1_name
        self.p2_id = None
        self.p2_name = None
        self.board = [None]*9
        self.turn = 'X'
        self.state = 'setup_mode'
        self.mode = None
        self.bet = 0
        self.last_interaction = time.time()
    def touch(self): self.last_interaction = time.time()
    
    def check_win(self):
        wins = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
        for a, b, c in wins:
            if self.board[a] and self.board[a] == self.board[b] == self.board[c]:
                return self.board[a]
        return 'draw' if None not in self.board else None
    
    def bot_move(self):
        empty = [i for i, x in enumerate(self.board) if x is None]
        if not empty: return None
        for m in empty:
            self.board[m] = 'O'
            if self.check_win() == 'O': self.board[m] = None; return m
            self.board[m] = None
        for m in empty:
            self.board[m] = 'X'
            if self.check_win() == 'X': self.board[m] = None; return m
            self.board[m] = None
        return random.choice(empty)

# --- CLEANER ---
def game_cleanup():
    while True:
        time.sleep(15)
        now = time.time()
        to_remove = []
        with games_lock:
            for r, g in games.items():
                if now - g.last_interaction > 90: to_remove.append(r)
            for r in to_remove:
                if BOT_INSTANCE: BOT_INSTANCE.send_message(r, "⌛ TicTacToe closed (inactivity).")
                del games[r]

threading.Thread(target=game_cleanup, daemon=True).start()

# --- HANDLER ---
def handle_command(bot, command, room, user, args, data):
    try:
        global BOT_INSTANCE, games
        BOT_INSTANCE = bot
        user_id = data.get("user_id", user)
        cmd = command.lower().strip()
        with games_lock: game = games.get(room)

        if cmd == "tic":
            if game: return True
            with games_lock: games[room] = TicTacToe(room, user_id, user)
            bot.send_message(room, f"🎮 **Tic-Tac-Toe**\n@{user}, Choose:\n1️⃣ Single (vs Bot)\n2️⃣ Multi (vs Player)")
            return True

        if cmd == "stop" and game:
            if str(user_id) == str(game.p1_id):
                with games_lock: del games[room]
                bot.send_message(room, "🛑 Game Stopped.")
            return True

        if game:
            game.touch()
            # 1. Choose Mode
            if game.state == 'setup_mode' and str(user_id) == str(game.p1_id):
                if cmd == "1":
                    game.mode = 1; game.p2_name = "Bot"; game.p2_id = "BOT"; game.state = 'setup_bet'
                    bot.send_message(room, "💰 Mode?\n1️⃣ Free (+500 coins)\n2️⃣ Bet 100 (+700 coins)")
                    return True
                elif cmd == "2":
                    game.mode = 2; game.state = 'setup_bet'
                    bot.send_message(room, "💰 Bet?\n1️⃣ Fun (No coins)\n2️⃣ Bet 100 (Pot 200)")
                    return True

            # 2. Choose Bet
            elif game.state == 'setup_bet' and str(user_id) == str(game.p1_id):
                if cmd in ["1", "2"]:
                    game.bet = 0 if cmd == "1" else 100
                    if game.bet > 0: db.add_game_result(game.p1_id, game.p1_name, "tictactoe", -game.bet)
                    
                    if game.mode == 1:
                        game.state = 'playing'
                        url = upload_image(bot, draw_board(game.board))
                        bot.send_message(room, f"🔥 VS Bot! Type 1-9."); if url: bot.send_image(room, url)
                    else:
                        game.state = 'waiting_join'
                        bot.send_message(room, "⚔️ Waiting... Type `join` to play!")
                    return True

            # 3. Join Match
            elif game.state == 'waiting_join' and cmd == "join":
                if str(user_id) == str(game.p1_id): return True
                game.p2_id = user_id; game.p2_name = user; game.state = 'playing'
                if game.bet > 0: db.add_game_result(user_id, user, "tictactoe", -game.bet)
                url = upload_image(bot, draw_board(game.board))
                bot.send_message(room, f"🥊 Match: @{game.p1_name} vs @{game.p2_name}"); if url: bot.send_image(room, url)
                return True

            # 4. Gameplay Move
            elif game.state == 'playing' and cmd.isdigit():
                idx = int(cmd) - 1
                if not (0 <= idx <= 8): return False
                curr_id = game.p1_id if game.turn == 'X' else game.p2_id
                if str(user_id) != str(curr_id) or game.board[idx]: return True
                
                game.board[idx] = game.turn; win = game.check_win()
                
                if win:
                    w_nm = game.p1_name if win == 'X' else game.p2_name
                    w_id = game.p1_id if win == 'X' else game.p2_id
                    if win == 'draw':
                        bot.send_message(room, "🤝 Draw! Refunded.")
                        if game.bet > 0:
                            db.add_game_result(game.p1_id, game.p1_name, "tictactoe", game.bet)
                            if game.mode == 2: db.add_game_result(game.p2_id, game.p2_name, "tictactoe", game.bet)
                    else:
                        reward = (game.bet * 2) if game.mode == 2 else (500 if game.bet == 0 else 700)
                        db.add_game_result(w_id, w_nm, "tictactoe", reward, is_win=True)
                        bot.send_message(room, f"🏆 @{w_nm} WON {reward} coins!")
                        url = upload_image(bot, draw_board(game.board)); if url: bot.send_image(room, url)
                    with games_lock: del games[room]; return True

                game.turn = 'O' if game.turn == 'X' else 'X'
                if game.mode == 1 and game.turn == 'O':
                    m = game.bot_move()
                    if m is not None:
                        game.board[m] = 'O'
                        if game.check_win():
                            bot.send_message(room, "🤖 Bot Won!"); url = upload_image(bot, draw_board(game.board))
                            if url: bot.send_image(room, url)
                            with games_lock: del games[room]; return True
                        game.turn = 'X'
                
                url = upload_image(bot, draw_board(game.board)); if url: bot.send_image(room, url)
                return True
    except: traceback.print_exc()
    return False
