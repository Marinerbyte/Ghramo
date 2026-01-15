import time
import random
import requests
import io
import sys
import os
import threading
import traceback
import urllib3
from PIL import Image, ImageDraw, ImageFont

# SSL warnings ko silent karne ke liye
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
UPLOAD_URL = "https://cdn.talkinchat.com/post.php"

# --- SETUP ---
def setup(bot_ref):
    global BOT_INSTANCE
    BOT_INSTANCE = bot_ref
    print("[TicTacToe] SSL Fix Applied.")

# --- CLEANER THREAD ---
def game_cleanup_loop():
    while True:
        time.sleep(10)
        now = time.time()
        to_remove = []
        with games_lock:
            for room_name, game in games.items():
                if now - game.last_interaction > 120:
                    to_remove.append(room_name)
        for room_name in to_remove:
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
    """SSL Bypass ke saath Image Upload"""
    try:
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        files = {'file': ('tic.png', img_byte_arr, 'image/png')}
        
        # verify=False lagaya gaya hai SSL error fix karne ke liye
        r = requests.post(UPLOAD_URL, files=files, timeout=15, verify=False)
        
        if r.status_code == 200:
            url = r.text.strip()
            if "http" in url: return url
            try: return r.json().get('url')
            except: pass
        else:
            bot.log(f"❌ Upload HTTP Error: {r.status_code}")
    except Exception as e:
        bot.log(f"❌ Upload Error: {e}")
    return None

def draw_board(board_state):
    size = 400
    cell = size // 3
    img = Image.new('RGB', (size, size), color=(30, 30, 35)) 
    d = ImageDraw.Draw(img)
    fnt_num = get_font(60)
    
    # Grid
    for i in range(1, 3):
        d.line([(cell * i, 20), (cell * i, size - 20)], fill=(100, 100, 100), width=5)
        d.line([(20, cell * i), (size - 20, cell * i)], fill=(100, 100, 100), width=5)
    
    # Marks
    for i in range(9):
        row, col = i // 3, i % 3
        x, y = col * cell, row * cell
        cx, cy = x + cell // 2, y + cell // 2
        val = board_state[i]
        
        if val is None:
            # Box numbers
            d.text((cx-15, cy-35), str(i+1), font=fnt_num, fill=(60, 60, 70)) 
        elif val == 'X':
            offset = 35
            d.line([(x+offset, y+offset), (x+cell-offset, y+cell-offset)], fill=(255, 60, 60), width=12)
            d.line([(x+cell-offset, y+offset), (x+offset, y+cell-offset)], fill=(255, 60, 60), width=12)
        elif val == 'O':
            offset = 35
            d.ellipse([(x+offset, y+offset), (x+cell-offset, y+cell-offset)], outline=(60, 120, 255), width=12)
    return img

class TicTacToe:
    def __init__(self, room_name, creator_name):
        self.room_name = room_name
        self.p1_name = creator_name
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
        for i1, i2, i3 in wins:
            if self.board[i1] and self.board[i1] == self.board[i2] == self.board[i3]:
                return self.board[i1]
        if None not in self.board: return 'draw'
        return None
    
    def bot_move(self):
        empty = [i for i, x in enumerate(self.board) if x is None]
        if not empty: return None
        # Win
        for m in empty:
            self.board[m] = 'O'
            if self.check_win() == 'O': self.board[m] = None; return m
            self.board[m] = None
        # Block
        for m in empty:
            self.board[m] = 'X'
            if self.check_win() == 'X': self.board[m] = None; return m
            self.board[m] = None
        return random.choice(empty)

def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()
    global games
    
    try:
        with games_lock:
            game = games.get(room_name)

            if cmd == "tic":
                if game: return True
                games[room_name] = TicTacToe(room_name, user)
                bot.send_message(room_name, f"🎮 **Tic-Tac-Toe**\n@{user}, Choose:\n1️⃣ Single\n2️⃣ Multi")
                return True

            if cmd == "stop" and game:
                del games[room_name]
                bot.send_message(room_name, "🛑 Game Stopped.")
                return True

            if game:
                game.touch()
                # Mode Selection
                if game.state == 'setup_mode' and user == game.p1_name:
                    if cmd == "1":
                        game.mode = 1; game.p2_name = "Bot"; game.state = 'setup_bet'
                        bot.send_message(room_name, "💰 Reward Mode?\n1️⃣ Free (Win 500)\n2️⃣ Bet 100 (Win 700)")
                        return True
                    elif cmd == "2":
                        game.mode = 2; game.state = 'setup_bet'
                        bot.send_message(room_name, "💰 Bet Amount?\n1️⃣ Fun (No Reward)\n2️⃣ Bet 100 Coins")
                        return True
                
                # Bet Selection
                elif game.state == 'setup_bet' and user == game.p1_name:
                    if cmd in ["1", "2"]:
                        game.bet = 0 if cmd == "1" else 100
                        if game.bet > 0: db.add_game_result(user, user, "tictactoe", -game.bet)
                        
                        if game.mode == 1:
                            game.state = 'playing'
                            img = draw_board(game.board); url = upload_image(bot, img)
                            bot.send_message(room_name, f"🔥 vs Bot 🤖\nType 1-9 to play.")
                            if url: bot.send_image(room_name, url)
                        else:
                            game.state = 'waiting_join'
                            bot.send_message(room_name, f"⚔️ Waiting for player...\nType `join` to play!")
                        return True
                
                # Join Multi
                elif game.state == 'waiting_join' and cmd == "join":
                    if user == game.p1_name: return True
                    game.p2_name = user; game.state = 'playing'
                    if game.bet > 0: db.add_game_result(user, user, "tictactoe", -game.bet)
                    img = draw_board(game.board); url = upload_image(bot, img)
                    bot.send_message(room_name, f"🥊 Match: @{game.p1_name} vs @{game.p2_name}\n@{game.p1_name} turn!")
                    if url: bot.send_image(room_name, url)
                    return True
                
                # Gameplay
                elif game.state == 'playing' and cmd.isdigit():
                    idx = int(cmd) - 1
                    if not (0 <= idx <= 8): return False
                    curr_p = game.p1_name if game.turn == 'X' else game.p2_name
                    if user != curr_p: return False
                    if game.board[idx]: return True
                    
                    game.board[idx] = game.turn
                    win = game.check_win()
                    
                    if win:
                        w_nm = game.p1_name if win=='X' else game.p2_name
                        if win == 'draw':
                            bot.send_message(room_name, "🤝 Draw! Coins Refunded.")
                            if game.bet > 0:
                                db.add_game_result(game.p1_name, game.p1_name, "tictactoe", game.bet)
                                if game.mode == 2: db.add_game_result(game.p2_name, game.p2_name, "tictactoe", game.bet)
                        else:
                            reward = (game.bet * 2) if game.mode == 2 else (500 if game.bet == 0 else 700)
                            db.add_game_result(w_nm, w_nm, "tictactoe", reward, is_win=True)
                            bot.send_message(room_name, f"🏆 @{w_nm} WON {reward} coins!")
                            img = draw_board(game.board); url = upload_image(bot, img)
                            if url: bot.send_image(room_name, url)
                        del games[room_name]
                        return True

                    game.turn = 'O' if game.turn == 'X' else 'X'
                    if game.mode == 1 and game.turn == 'O':
                        b_idx = game.bot_move()
                        if b_idx is not None:
                            game.board[b_idx] = 'O'
                            if game.check_win():
                                bot.send_message(room_name, "🤖 Bot Won!")
                                img = draw_board(game.board); url = upload_image(bot, img)
                                if url: bot.send_image(room_name, url)
                                del games[room_name]; return True
                            game.turn = 'X'
                    
                    img = draw_board(game.board); url = upload_image(bot, img)
                    if url: bot.send_image(room_name, url)
                    return True

    except:
        traceback.print_exc()
    return False
