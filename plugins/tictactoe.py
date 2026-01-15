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

# SSL verification warnings silent karne ke liye
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- MASTER DB IMPORT ---
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from db import add_game_result
except Exception as e:
    print(f"[DB Error] Could not import add_game_result: {e}")

# --- GLOBAL STATE ---
games = {} 
games_lock = threading.Lock()
BOT_INSTANCE = None 

# --- SETUP ---
def setup(bot_ref):
    global BOT_INSTANCE
    BOT_INSTANCE = bot_ref
    BOT_INSTANCE.log("🧩 TicTacToe: Expert Plugin Loaded.")

# --- CLEANER THREAD (90s Inactivity) ---
def game_cleanup_loop():
    while True:
        time.sleep(15)
        now = time.time()
        to_remove = []
        with games_lock:
            for room_name, game in games.items():
                if now - game.last_interaction > 90:
                    to_remove.append(room_name)
            for room_name in to_remove:
                if BOT_INSTANCE:
                    BOT_INSTANCE.send_message(room_name, "⌛ TicTacToe ended due to inactivity.")
                del games[room_name]

if threading.active_count() < 15: 
    threading.Thread(target=game_cleanup_loop, daemon=True).start()

# --- HELPER: UPLOAD TO CATBOX ---
def upload_image(bot, image):
    try:
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        files = {
            'reqtype': (None, 'fileupload'),
            'fileToUpload': ('tic_board.png', img_byte_arr, 'image/png')
        }
        r = requests.post('https://catbox.moe/user/api.php', files=files, timeout=15)
        if r.status_code == 200 and "http" in r.text:
            url = r.text.strip()
            bot.log(f"📸 Board Uploaded: {url}")
            return url
        bot.log(f"❌ Upload Failed: {r.text}")
    except Exception as e:
        bot.log(f"❌ Upload Error: {e}")
    return None

# --- VISUALS: MODERN NEON BOARD ---
def draw_board(board_state):
    size = 450
    cell = size // 3
    img = Image.new('RGB', (size, size), color=(15, 17, 26)) 
    d = ImageDraw.Draw(img)
    
    # Fonts
    try:
        fnt_num = ImageFont.truetype("arial.ttf", 40)
        fnt_sym = ImageFont.truetype("arial.ttf", 80)
    except:
        fnt_num = ImageFont.load_default()
        fnt_sym = ImageFont.load_default()

    # Grid Lines
    for i in range(1, 3):
        d.line([(cell*i, 20), (cell*i, size-20)], fill=(50, 50, 70), width=5)
        d.line([(20, cell*i), (size-20, cell*i)], fill=(50, 50, 70), width=5)

    for i in range(9):
        row, col = i // 3, i % 3
        x, y = col * cell, row * cell
        cx, cy = x + cell // 2, y + cell // 2
        val = board_state[i]
        
        if val is None:
            # Box Hint Number
            d.text((cx-10, cy-20), str(i+1), font=fnt_num, fill=(40, 42, 54)) 
        elif val == 'X':
            # Neon Red X
            off = 45
            d.line([(x+off, y+off), (x+cell-off, y+cell-off)], fill=(255, 50, 100), width=15)
            d.line([(x+cell-off, y+off), (x+off, y+cell-off)], fill=(255, 50, 100), width=15)
        elif val == 'O':
            # Neon Blue O
            off = 45
            d.ellipse([(x+off, y+off), (x+cell-off, y+cell-off)], outline=(0, 240, 255), width=15)
    return img

# --- GAME SESSION CLASS ---
class TicTacToeSession:
    def __init__(self, room, p1_id, p1_name):
        self.room = room
        self.p1_id = p1_id
        self.p1_name = p1_name
        self.p2_id = None
        self.p2_name = None
        self.board = [None] * 9
        self.turn = 'X'
        self.state = 'setup_mode' # setup_mode -> setup_bet -> waiting_join -> playing
        self.mode = None # 1: Single, 2: Multi
        self.bet = 0
        self.last_interaction = time.time()

    def touch(self):
        self.last_interaction = time.time()

    def check_win(self):
        wins = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
        for a, b, c in wins:
            if self.board[a] and self.board[a] == self.board[b] == self.board[c]:
                return self.board[a]
        return 'draw' if None not in self.board else None

    def bot_move(self):
        empty = [i for i, x in enumerate(self.board) if x is None]
        if not empty: return None
        for m in empty: # Try to win
            self.board[m] = 'O'
            if self.check_win() == 'O': self.board[m] = None; return m
            self.board[m] = None
        for m in empty: # Try to block
            self.board[m] = 'X'
            if self.check_win() == 'X': self.board[m] = None; return m
            self.board[m] = None
        if 4 in empty: return 4
        return random.choice(empty)

# --- MAIN COMMAND HANDLER ---
def handle_command(bot, command, room, user, args, data):
    # CRITICAL: Multi-key ID extraction for TalkinChat
    user_id = str(data.get('user_id') or data.get('userid') or data.get('id') or user)
    cmd = command.lower().strip()
    
    global games
    with games_lock:
        game = games.get(room)

        # 1. NEW GAME COMMAND
        if cmd == "tic":
            if game:
                bot.send_message(room, f"⚠️ Match already running here @{user}!")
                return True
            games[room] = TicTacToeSession(room, user_id, user)
            bot.send_message(room, f"🎮 **Tic-Tac-Toe**\n@{user}, choose mode:\n1️⃣ Single (vs Bot)\n2️⃣ Multi (vs Players)")
            return True

        # 2. STOP GAME
        if cmd == "stop" and game:
            if user_id == game.p1_id or user_id == game.p2_id:
                del games[room]
                bot.send_message(room, "🛑 Match cancelled.")
                return True

        if game:
            game.touch()
            # 3. SETUP MODE SELECTION
            if game.state == 'setup_mode' and user_id == game.p1_id:
                if cmd == "1":
                    game.mode = 1; game.p2_name = "Bot"; game.p2_id = "BOT"; game.state = 'setup_bet'
                    bot.send_message(room, "💰 Select Reward:\n1️⃣ Free Match (+500)\n2️⃣ Bet 100 Coins (+700)")
                    return True
                elif cmd == "2":
                    game.mode = 2; game.state = 'setup_bet'
                    bot.send_message(room, "💰 Select Bet:\n1️⃣ Fun (No Coins)\n2️⃣ Bet 100 Coins")
                    return True

            # 4. SETUP BET SELECTION
            elif game.state == 'setup_bet' and user_id == game.p1_id:
                if cmd in ["1", "2"]:
                    game.bet = 0 if cmd == "1" else 100
                    if game.bet > 0:
                        add_game_result(game.p1_id, game.p1_name, "tictactoe", -game.bet, is_win=False)
                    
                    if game.mode == 1:
                        game.state = 'playing'
                        url = upload_image(bot, draw_board(game.board))
                        bot.send_message(room, "🔥 **Match Started!** VS Pro Bot.\nType box number (1-9) to move.")
                        if url: bot.send_image(room, url)
                    else:
                        game.state = 'waiting_join'
                        bot.send_message(room, f"⚔️ **Lobby Open!** Bet: {game.bet}\n@{user} is waiting. Type `join` to play!")
                    return True

            # 5. JOIN MULTIPLAYER
            elif game.state == 'waiting_join' and cmd == "join":
                if user_id == game.p1_id: return True
                game.p2_id = user_id; game.p2_name = user; game.state = 'playing'
                if game.bet > 0:
                    add_game_result(user_id, user, "tictactoe", -game.bet, is_win=False)
                
                url = upload_image(bot, draw_board(game.board))
                bot.send_message(room, f"🥊 Match: @{game.p1_name} vs @{game.p2_name}\n@{game.p1_name} (X) starts!")
                if url: bot.send_image(room, url)
                return True

            # 6. GAMEPLAY (BOX NUMBERS)
            elif game.state == 'playing' and cmd.isdigit():
                idx = int(cmd) - 1
                if not (0 <= idx <= 8): return False
                
                curr_turn_id = game.p1_id if game.turn == 'X' else game.p2_id
                if user_id != curr_turn_id or game.board[idx]: 
                    return True # Wrong turn or box taken

                # Player Move
                game.board[idx] = game.turn
                win = game.check_win()

                if win:
                    handle_finish(bot, room, game, win)
                    return True

                # Switch turn
                game.turn = 'O' if game.turn == 'X' else 'X'

                # Bot Auto Move
                if game.mode == 1 and game.turn == 'O':
                    b_idx = game.bot_move()
                    if b_idx is not None:
                        game.board[b_idx] = 'O'
                        b_win = game.check_win()
                        if b_win:
                            handle_finish(bot, room, game, b_win)
                            return True
                        game.turn = 'X'

                # Send updated board
                url = upload_image(bot, draw_board(game.board))
                if url: bot.send_image(room, url)
                return True

    return False

def handle_finish(bot, room, game, winner):
    """Howdies Logic for finishing game and rewards"""
    img = draw_board(game.board)
    url = upload_image(bot, img)
    if url: bot.send_image(room, url)

    if winner == 'draw':
        bot.send_message(room, "🤝 **Match Draw!** Coins have been refunded.")
        if game.bet > 0:
            add_game_result(game.p1_id, game.p1_name, "tictactoe", game.bet, False)
            if game.mode == 2: add_game_result(game.p2_id, game.p2_name, "tictactoe", game.bet, False)
    else:
        w_nm = game.p1_name if winner == 'X' else game.p2_name
        w_id = game.p1_id if winner == 'X' else game.p2_id
        
        if w_id == "BOT":
            bot.send_message(room, "🤖 **Bot Wins!** Better luck next time.")
        else:
            reward = 0
            if game.mode == 1:
                reward = 500 if game.bet == 0 else 700
            else:
                reward = game.bet * 2
            
            add_game_result(w_id, w_nm, "tictactoe", reward, is_win=True)
            bot.send_message(room, f"🎉🏆 **@{w_nm} WINS!** Received **{reward}** coins.")

    with games_lock:
        if room in games: del games[room]
