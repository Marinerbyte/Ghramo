import time
import random
import requests
import io
import sys
import os
import threading
import traceback
import urllib3
from PIL import Image, ImageDraw, ImageFont, ImageOps

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- DB IMPORT ---
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from db import add_game_result
except: pass

games = {} 
games_lock = threading.Lock()
BOT_INSTANCE = None 

# --- SETUP ---
def setup(bot_ref):
    global BOT_INSTANCE
    BOT_INSTANCE = bot_ref

# --- HELPER: CIRCULAR AVATAR ---
def get_circular_avatar(url):
    try:
        resp = requests.get(url, timeout=10, verify=False)
        img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        img = img.resize((150, 150), Image.Resampling.LANCZOS)
        
        # Create mask
        mask = Image.new('L', (150, 150), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, 150, 150), fill=255)
        
        output = ImageOps.fit(img, mask.size, centering=(0.5, 0.5))
        output.putalpha(mask)
        return output
    except:
        return None

# --- HELPER: UPLOAD ---
def upload_image(bot, image):
    try:
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        files = {'reqtype': (None, 'fileupload'), 'fileToUpload': ('game.png', img_byte_arr, 'image/png')}
        r = requests.post('https://catbox.moe/user/api.php', files=files, timeout=15)
        return r.text.strip() if r.status_code == 200 else None
    except: return None

# --- VISUALS: BOARD ---
def draw_board(board_state):
    size = 450
    cell = size // 3
    img = Image.new('RGB', (size, size), color=(15, 17, 26)) 
    d = ImageDraw.Draw(img)
    
    try:
        fnt_hint = ImageFont.truetype("arial.ttf", 80) # Bade numbers
        fnt_sym = ImageFont.truetype("arial.ttf", 100)
    except:
        fnt_hint = fnt_sym = ImageFont.load_default()

    # Grid
    for i in range(1, 3):
        d.line([(cell*i, 20), (cell*i, size-20)], fill=(45, 48, 65), width=5)
        d.line([(20, cell*i), (size-20, cell*i)], fill=(45, 48, 65), width=5)

    for i in range(9):
        row, col = i // 3, i % 3
        x, y = col * cell, row * cell
        cx, cy = x + cell // 2, y + cell // 2
        val = board_state[i]
        
        if val is None:
            # Faint large hint numbers
            d.text((cx-25, cy-45), str(i+1), font=fnt_hint, fill=(35, 37, 48)) 
        elif val == 'X':
            off = 45
            d.line([(x+off, y+off), (x+cell-off, y+cell-off)], fill=(255, 46, 99), width=16)
            d.line([(x+cell-off, y+off), (x+off, y+cell-off)], fill=(255, 46, 99), width=16)
        elif val == 'O':
            off = 45
            d.ellipse([(x+off, y+off), (x+cell-off, y+cell-off)], outline=(0, 242, 255), width=16)
    return img

# --- VISUALS: WINNER CARD ---
def draw_winner_card(username, avatar_url, symbol):
    size = 450
    img = Image.new('RGB', (size, size), color=(10, 12, 18))
    d = ImageDraw.Draw(img)
    
    # Neon Border
    color = (255, 46, 99) if symbol == 'X' else (0, 242, 255)
    d.rectangle([10, 10, size-10, size-10], outline=color, width=8)

    # Avatar
    av = get_circular_avatar(avatar_url)
    if av:
        img.paste(av, (size//2 - 75, 50), av)
        d.ellipse([size//2-77, 48, size//2+77, 202], outline="white", width=3)
    
    try:
        fnt_win = ImageFont.truetype("arial.ttf", 50)
        fnt_name = ImageFont.truetype("arial.ttf", 35)
    except:
        fnt_win = fnt_name = ImageFont.load_default()

    # Text
    d.text((size//2 - 100, 220), "WINNER!", fill="yellow", font=fnt_win)
    d.text((size//2 - 80, 300), f"@{username}", fill="white", font=fnt_name)
    d.text((size//2 - 30, 360), "🏆", font=fnt_win)
    
    return img

class TicTacToeSession:
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
        wins = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
        for a, b, c in wins:
            if self.board[a] and self.board[a] == self.board[b] == self.board[c]: return self.board[a]
        return 'draw' if None not in self.board else None

# --- HANDLER ---
def handle_command(bot, command, room, user, args, data):
    uid = str(data.get('user_id') or data.get('id') or user)
    av_url = data.get('avatar_url')
    cmd = command.lower().strip()
    
    global games
    with games_lock:
        game = games.get(room)

        if cmd == "tic":
            if game: return True
            games[room] = TicTacToeSession(room, uid, user, av_url)
            bot.send_message(room, f"🎮 **Tic-Tac-Toe**\n@{user}, choose:\n1️⃣ Single\n2️⃣ Multi")
            return True

        if game:
            game.touch()
            # Mode Setup
            if game.state == 'setup_mode' and uid == game.p1_id:
                if cmd in ["1", "2"]:
                    game.mode = int(cmd); game.state = 'setup_bet'
                    if game.mode == 1: game.p2_name, game.p2_id = "Bot", "BOT"
                    bot.send_message(room, "💰 Select Bet:\n1️⃣ Free\n2️⃣ Bet 100")
                    return True

            # Bet Setup
            elif game.state == 'setup_bet' and uid == game.p1_id:
                if cmd in ["1", "2"]:
                    game.bet = 0 if cmd == "1" else 100
                    if game.bet > 0: add_game_result(game.p1_id, game.p1_name, "tictactoe", -game.bet)
                    game.state = 'playing' if game.mode == 1 else 'waiting_join'
                    if game.mode == 1:
                        url = upload_image(bot, draw_board(game.board))
                        bot.send_message(room, "🔥 Match Started!"); if url: bot.send_image(room, url)
                    else: bot.send_message(room, f"⚔️ Lobby Open! Bet: {game.bet}\nType `join` to play.")
                    return True

            # Join
            elif game.state == 'waiting_join' and cmd == "join":
                if uid == game.p1_id: return True
                game.p2_id, game.p2_name, game.p2_av = uid, user, av_url
                if game.bet > 0: add_game_result(uid, user, "tictactoe", -game.bet)
                game.state = 'playing'
                url = upload_image(bot, draw_board(game.board))
                bot.send_message(room, f"🥊 Match: @{game.p1_name} vs @{game.p2_name}"); if url: bot.send_image(room, url)
                return True

            # Move
            elif game.state == 'playing' and cmd.isdigit():
                idx = int(cmd) - 1
                if not (0 <= idx <= 8): return False
                curr_turn_id = game.p1_id if game.turn == 'X' else game.p2_id
                if uid != curr_turn_id or game.board[idx]: return True
                
                game.board[idx] = game.turn
                win = game.check_win()
                if win:
                    finish_game(bot, room, game, win)
                    return True

                game.turn = 'O' if game.turn == 'X' else 'X'
                # Bot move logic (kept simple for brevity, same as previous)
                if game.mode == 1 and game.turn == 'O':
                    empty = [i for i, x in enumerate(game.board) if x is None]
                    if empty:
                        game.board[random.choice(empty)] = 'O'
                        b_win = game.check_win()
                        if b_win: finish_game(bot, room, game, b_win); return True
                        game.turn = 'X'

                url = upload_image(bot, draw_board(game.board))
                if url: bot.send_image(room, url)
                return True
    return False

def finish_game(bot, room, game, winner):
    if winner == 'draw':
        bot.send_message(room, "🤝 Draw! Coins refunded.")
        if game.bet > 0:
            add_game_result(game.p1_id, game.p1_name, "tictactoe", game.bet)
            if game.mode == 2: add_game_result(game.p2_id, game.p2_name, "tictactoe", game.bet)
    else:
        w_nm = game.p1_name if winner == 'X' else game.p2_name
        w_id = game.p1_id if winner == 'X' else game.p2_id
        w_av = game.p1_av if winner == 'X' else game.p2_av
        
        if w_id != "BOT":
            reward = (500 if game.bet == 0 else 700) if game.mode == 1 else game.bet * 2
            add_game_result(w_id, w_nm, "tictactoe", reward, True)
            bot.send_message(room, f"🎉 @{w_nm} wins {reward} coins!")
            card = draw_winner_card(w_nm, w_av, winner)
            url = upload_image(bot, card)
            if url: bot.send_image(room, url)
        else:
            bot.send_message(room, "🤖 Bot wins!")
    
    with games_lock:
        if room in games: del games[room]
