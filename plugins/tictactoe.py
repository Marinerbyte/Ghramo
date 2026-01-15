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
from PIL import Image, ImageDraw, ImageFont, ImageOps

# SSL Warnings silent karein
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- MASTER DB IMPORT ---
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from db import add_game_result
except Exception as e:
    print(f"[DB Error] TicTacToe: {e}")

# --- GLOBAL STATE ---
games = {} 
games_lock = threading.Lock()
BOT_INSTANCE = None 

# --- SETUP ---
def setup(bot_ref):
    global BOT_INSTANCE
    BOT_INSTANCE = bot_ref
    BOT_INSTANCE.log("✅ TicTacToe: Expert Version Loaded.")

# --- CLEANER THREAD (90s Inactivity) ---
def game_cleanup_loop():
    while True:
        time.sleep(15)
        now = time.time()
        to_remove = []
        with games_lock:
            for r_name, g in games.items():
                if now - g.last_interaction > 90: to_remove.append(r_name)
            for r_name in to_remove:
                if BOT_INSTANCE: BOT_INSTANCE.send_message(r_name, "⌛ Match closed due to inactivity.")
                del games[r_name]

if threading.active_count() < 15: 
    threading.Thread(target=game_cleanup_loop, daemon=True).start()

# --- HELPER: SAFE FONT ---
def get_safe_font(size):
    paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "arial.ttf"]
    for p in paths:
        try: return ImageFont.truetype(p, size)
        except: continue
    return ImageFont.load_default()

# --- HELPER: STABLE UPLOAD (Catbox) ---
def upload_image(bot, image):
    try:
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        buf.seek(0)
        f = {'reqtype': (None, 'fileupload'), 'fileToUpload': ('tic.png', buf, 'image/png')}
        r = requests.post('https://catbox.moe/user/api.php', files=f, timeout=10)
        return r.text.strip() if r.status_code == 200 else None
    except: return None

# --- VISUALS: MODERN NEON BOARD ---
def draw_board(board_state):
    size = 450
    cell = size // 3
    img = Image.new('RGB', (size, size), color=(15, 17, 26)) 
    d = ImageDraw.Draw(img)
    fnt_hint = get_safe_font(100) 
    
    # Grid
    for i in range(1, 3):
        d.line([(cell*i, 25), (cell*i, size-25)], fill=(40, 42, 58), width=6)
        d.line([(25, cell*i), (size-25, cell*i)], fill=(40, 42, 58), width=6)

    for i in range(9):
        r, c = i // 3, i % 3
        x, y = c * cell, r * cell
        cx, cy = x + cell // 2, y + cell // 2
        val = board_state[i]
        
        if val is None:
            # Bade lekin faint numbers (User help)
            d.text((cx-30, cy-55), str(i+1), font=fnt_hint, fill=(25, 27, 38)) 
        elif val == 'X':
            off = 45
            d.line([(x+off, y+off), (x+cell-off, y+cell-off)], fill=(255, 46, 99), width=16)
            d.line([(x+cell-off, y+off), (x+off, y+cell-off)], fill=(255, 46, 99), width=16)
        elif val == 'O':
            off = 45
            d.ellipse([(x+off, y+off), (x+cell-off, y+cell-off)], outline=(0, 242, 255), width=16)
    return img

# --- VISUALS: WINNER CARD ---
def draw_winner_card(username, av_url, symbol):
    size = 450
    img = Image.new('RGB', (size, size), color=(12, 14, 20))
    d = ImageDraw.Draw(img)
    
    # Border
    color = (255, 46, 99) if symbol == 'X' else (0, 242, 255)
    d.rectangle([10, 10, 440, 440], outline=color, width=10)

    # Avatar Crop logic
    try:
        if av_url:
            resp = requests.get(av_url, timeout=5, verify=False)
            av_img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
            av_img = av_img.resize((180, 180), Image.Resampling.LANCZOS)
            mask = Image.new('L', (180, 180), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 180, 180), fill=255)
            img.paste(av_img, (size//2-90, 60), mask)
            d.ellipse([size//2-92, 58, size//2+92, 242], outline="white", width=4)
    except: pass
    
    fnt_win = get_safe_font(55)
    fnt_name = get_safe_font(38)
    d.text((size//2-110, 265), "WINNER!", fill="yellow", font=fnt_win)
    d.text((size//2-80, 335), f"@{username}", fill="white", font=fnt_name)
    d.text((size//2-30, 385), "🏆", font=fnt_win)
    return img

# --- SESSION CLASS ---
class GameSession:
    def __init__(self, room, p1_id, p1_name, p1_av):
        self.room = room
        self.p1_id, self.p1_name, self.p1_av = p1_id, p1_name, p1_av
        self.p2_id = self.p2_name = self.p2_av = None
        self.board = [None] * 9
        self.turn = 'X'
        self.state = 'setup_mode'
        self.mode = None # 1: Single, 2: Multi
        self.bet = 0
        self.last_interaction = time.time()
    def touch(self): self.last_interaction = time.time()
    def check_win(self):
        wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
        for a,b,c in wins:
            if self.board[a] and self.board[a] == self.board[b] == self.board[c]: return self.board[a]
        return 'draw' if None not in self.board else None

# --- HANDLER ---
def handle_command(bot, command, room, user, args, data):
    uid = str(data.get('user_id') or data.get('id') or user)
    av = data.get('avatar_url') or ""
    cmd = command.lower().strip()
    
    global games
    with games_lock:
        game = games.get(room)

        if cmd == "tic":
            if game: return True
            games[room] = GameSession(room, uid, user, av)
            bot.send_message(room, f"🎮 **Tic-Tac-Toe**\n@{user}, Choose:\n1️⃣ Single\n2️⃣ Multi")
            return True

        if game:
            game.touch()
            # 1. Mode Setup
            if game.state == 'setup_mode' and uid == game.p1_id:
                if cmd in ["1", "2"]:
                    game.mode = int(cmd); game.state = 'setup_bet'
                    if game.mode == 1: game.p2_name, game.p2_id = "Bot", "BOT"
                    bot.send_message(room, "💰 Select Bet:\n1️⃣ Free\n2️⃣ Bet 100")
                    return True

            # 2. Bet Setup
            elif game.state == 'setup_bet' and uid == game.p1_id:
                if cmd in ["1", "2"]:
                    game.bet = 0 if cmd == "1" else 100
                    if game.bet > 0: add_game_result(game.p1_id, game.p1_name, "tictactoe", -game.bet)
                    game.state = 'playing' if game.mode == 1 else 'waiting_join'
                    if game.mode == 1:
                        url = upload_image(bot, draw_board(game.board))
                        bot.send_message(room, "🔥 vs Bot! Type 1-9"); if url: bot.send_image(room, url)
                    else: bot.send_message(room, f"⚔️ Lobby Open! Bet: {game.bet}\nType `join` to play.")
                    return True

            # 3. Join Match
            elif game.state == 'waiting_join' and cmd == "join":
                if uid == game.p1_id: return True
                game.p2_id, game.p2_name, game.p2_av = uid, user, av
                if game.bet > 0: add_game_result(uid, user, "tictactoe", -game.bet)
                game.state = 'playing'
                url = upload_image(bot, draw_board(game.board))
                bot.send_message(room, f"🥊 Match: @{game.p1_name} vs @{game.p2_name}"); if url: bot.send_image(room, url)
                return True

            # 4. Gameplay
            elif game.state == 'playing' and cmd.isdigit():
                idx = int(cmd) - 1
                if not (0 <= idx <= 8): return False
                curr_turn_id = game.p1_id if game.turn == 'X' else game.p2_id
                if uid != curr_turn_id or game.board[idx]: return True
                
                game.board[idx] = game.turn
                res = game.check_win()
                if res:
                    finish_game(bot, room, game, res)
                    return True

                # Switch turn
                game.turn = 'O' if game.turn == 'X' else 'X'
                if game.mode == 1 and game.turn == 'O':
                    # Simple Bot Move
                    empty = [i for i, x in enumerate(game.board) if x is None]
                    if empty:
                        game.board[random.choice(empty)] = 'O'
                        bres = game.check_win()
                        if bres: finish_game(bot, room, game, bres); return True
                        game.turn = 'X'
                
                url = upload_image(bot, draw_board(game.board))
                if url: bot.send_image(room, url)
                return True
    return False

def finish_game(bot, room, game, res):
    if res == 'draw':
        bot.send_message(room, "🤝 Draw! Coins refunded.")
        if game.bet > 0:
            add_game_result(game.p1_id, game.p1_name, "tictactoe", game.bet)
            if game.mode == 2: add_game_result(game.p2_id, game.p2_name, "tictactoe", game.bet)
    else:
        w_nm = game.p1_name if res == 'X' else game.p2_name
        w_id = game.p1_id if res == 'X' else game.p2_id
        w_av = game.p1_av if res == 'X' else game.p2_av
        
        if w_id != "BOT":
            reward = (500 if game.bet == 0 else 700) if game.mode == 1 else game.bet * 2
            add_game_result(w_id, w_nm, "tictactoe", reward, True)
            bot.send_message(room, f"🎉 @{w_nm} WON {reward} coins!")
            card = draw_winner_card(w_nm, w_av, res)
            url = upload_image(bot, card); if url: bot.send_image(room, url)
        else:
            bot.send_message(room, "🤖 Bot Wins!"); url = upload_image(bot, draw_board(game.board))
            if url: bot.send_image(room, url)
            
    with games_lock:
        if room in games: del games[room]
