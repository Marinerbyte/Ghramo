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

# SSL warnings silent karne ke liye
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
UPLOAD_URL = "https://cdn.chatp.net/post.php"

# --- SETUP ---
def setup(bot_ref):
    global BOT_INSTANCE
    BOT_INSTANCE = bot_ref
    print("[TicTacToe] New Board & TalkinChat Logic Loaded.")

# --- CLEANER THREAD ---
def game_cleanup_loop():
    while True:
        time.sleep(10)
        now = time.time()
        to_remove = []
        with games_lock:
            for room_name, game in games.items():
                if now - game.last_interaction > 90:
                    to_remove.append(room_name)
        for room_name in to_remove:
            if BOT_INSTANCE:
                try: BOT_INSTANCE.send_message(room_name, "⌛ TicTacToe ended due to inactivity.")
                except: pass
            with games_lock:
                if room_name in games: del games[room_name]

if threading.active_count() < 15: 
    threading.Thread(target=game_cleanup_loop, daemon=True).start()

# --- HELPER FUNCTIONS ---
def get_font(size):
    font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "arial.ttf"]
    for path in font_paths:
        try: return ImageFont.truetype(path, size)
        except: continue
    return ImageFont.load_default()

def upload_image(bot, image):
    """TalkinChat CDN Upload"""
    try:
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        files = {'file': ('tic.png', img_byte_arr, 'image/png')}
        r = requests.post(UPLOAD_URL, files=files, timeout=15, verify=False)
        if r.status_code == 200:
            url = r.text.strip()
            if "http" in url: return url
            try: return r.json().get('url')
            except: pass
    except Exception as e:
        bot.log(f"Upload Error: {e}")
    return None

# --- VISUALS (NEW BOARD DESIGN) ---
def draw_board(board_state):
    size = 450
    cell = size // 3
    # Dark modern background
    img = Image.new('RGB', (size, size), color=(18, 18, 24)) 
    d = ImageDraw.Draw(img)
    fnt_num = get_font(50)
    
    # Grid Lines (Neon Grey)
    for i in range(1, 3):
        d.line([(cell * i, 30), (cell * i, size - 30)], fill=(45, 45, 60), width=6)
        d.line([(30, cell * i), (size - 30, cell * i)], fill=(45, 45, 60), width=6)
    
    for i in range(9):
        row, col = i // 3, i % 3
        x, y = col * cell, row * cell
        cx, cy = x + cell // 2, y + cell // 2
        val = board_state[i]
        
        if val is None:
            # Subtle numbers for hints
            d.text((cx-12, cy-30), str(i+1), font=fnt_num, fill=(40, 40, 50)) 
        elif val == 'X':
            # Neon Red X
            off = 40
            d.line([(x+off, y+off), (x+cell-off, y+cell-off)], fill=(255, 65, 108), width=14)
            d.line([(x+cell-off, y+off), (x+off, y+cell-off)], fill=(255, 65, 108), width=14)
        elif val == 'O':
            # Neon Blue O
            off = 40
            d.ellipse([(x+off, y+off), (x+cell-off, y+cell-off)], outline=(0, 242, 255), width=14)
    return img

def draw_winner_card(username, winner_symbol):
    W, H = 450, 250
    bg_color = (15, 15, 20)
    img = Image.new('RGB', (W, H), color=bg_color)
    d = ImageDraw.Draw(img)
    
    border_col = (255, 65, 108) if winner_symbol == 'X' else (0, 242, 255)
    d.rectangle([10, 10, W-10, H-10], outline=border_col, width=5)
    
    fnt_name = get_font(45)
    fnt_title = get_font(35)
    
    d.text((W//2 - 100, 60), "🏆 WINNER", fill="yellow", font=fnt_title)
    d.text((W//2 - 80, 130), f"@{username}", fill="white", font=fnt_name)
    return img

# --- GAME LOGIC ---
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
        if None not in self.board: return 'draw'
        return None
    
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

# --- HANDLER ---
def handle_command(bot, command, room, user, args, data):
    try:
        global games
        user_id = data.get("user_id", user)
        cmd = command.lower().strip()
        with games_lock: game = games.get(room)

        if cmd == "tic":
            if game: return True
            with games_lock: games[room] = TicTacToe(room, user_id, user)
            bot.send_message(room, f"🎮 **Tic-Tac-Toe**\n@{user}, Choose:\n1️⃣ Single\n2️⃣ Multi")
            return True

        if cmd == "stop" and game:
            if str(user_id) == str(game.p1_id):
                with games_lock: del games[room]
                bot.send_message(room, "🛑 Game Cancelled.")
            return True

        if game:
            game.touch()
            # 1. SETUP MODE
            if game.state == 'setup_mode' and str(user_id) == str(game.p1_id):
                if cmd == "1":
                    game.mode = 1; game.p2_name = "Bot"; game.p2_id = "BOT"; game.state = 'setup_bet'
                    bot.send_message(room, "💰 Reward?\n1️⃣ Free (Win 500)\n2️⃣ Bet 100 (Win 700)")
                    return True
                elif cmd == "2":
                    game.mode = 2; game.state = 'setup_bet'
                    bot.send_message(room, "💰 Bet Amount?\n1️⃣ Fun (No Coins)\n2️⃣ Bet 100 Coins")
                    return True

            # 2. BET SETUP
            elif game.state == 'setup_bet' and str(user_id) == str(game.p1_id):
                if cmd in ["1", "2"]:
                    game.bet = 0 if cmd == "1" else 100
                    if game.bet > 0: db.add_game_result(game.p1_id, game.p1_name, "tictactoe", -game.bet)
                    
                    if game.mode == 1:
                        game.state = 'playing'
                        img = draw_board(game.board); url = upload_image(bot, img)
                        bot.send_message(room, "🔥 vs Pro Bot! Type 1-9 to move.")
                        if url: bot.send_image(room, url)
                    else:
                        game.state = 'waiting_join'
                        bot.send_message(room, "⚔️ Waiting... Type `join` to play!")
                    return True

            # 3. JOIN MULTI
            elif game.state == 'waiting_join' and cmd == "join":
                if str(user_id) == str(game.p1_id): return True
                game.p2_id = user_id; game.p2_name = user; game.state = 'playing'
                if game.bet > 0: db.add_game_result(user_id, user, "tictactoe", -game.bet)
                img = draw_board(game.board); url = upload_image(bot, img)
                bot.send_message(room, f"🥊 Match: @{game.p1_name} vs @{game.p2_name}\n@{game.p1_name} turn!")
                if url: bot.send_image(room, url)
                return True

            # 4. PLAYING
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
                        bot.send_message(room, "🤝 Draw! Coins back.")
                        if game.bet > 0:
                            db.add_game_result(game.p1_id, game.p1_name, "tictactoe", game.bet)
                            if game.mode == 2: db.add_game_result(game.p2_id, game.p2_name, "tictactoe", game.bet)
                    else:
                        reward = (game.bet * 2) if game.mode == 2 else (500 if game.bet == 0 else 700)
                        db.add_game_result(w_id, w_nm, "tictactoe", reward, is_win=True)
                        card = draw_winner_card(w_nm, win); url = upload_image(bot, card)
                        if url: bot.send_image(room, url)
                        bot.send_message(room, f"🏆 @{w_nm} WON {reward} coins!")
                    with games_lock: del games[room]; return True

                game.turn = 'O' if game.turn == 'X' else 'X'
                if game.mode == 1 and game.turn == 'O':
                    b_idx = game.bot_move()
                    if b_idx is not None:
                        game.board[b_idx] = 'O'
                        if game.check_win():
                            img = draw_board(game.board); url = upload_image(bot, img)
                            if url: bot.send_image(room, url)
                            bot.send_message(room, "🤖 Bot Won!"); del games[room]; return True
                        game.turn = 'X'
                
                img = draw_board(game.board); url = upload_image(bot, img)
                if url: bot.send_image(room, url)
                return True
    except: traceback.print_exc()
    return False
