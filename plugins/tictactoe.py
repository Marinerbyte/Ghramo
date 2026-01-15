import time
import random
import requests
import io
import sys
import os
import threading
import traceback
from PIL import Image, ImageDraw, ImageFont

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
    print("[TicTacToe] Logic Fully Ported to TalkinChat.")

# --- CLEANER THREAD (Inactivity handling) ---
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
                try: BOT_INSTANCE.send_message(room_name, "⌛ Game closed due to inactivity.")
                except: pass
            with games_lock:
                if room_name in games: del games[room_name]

if threading.active_count() < 15: 
    threading.Thread(target=game_cleanup_loop, daemon=True).start()

# --- HELPER FUNCTIONS ---
def get_font(size):
    # Font paths for Linux (Render/VPS)
    font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "arial.ttf"]
    for path in font_paths:
        try: return ImageFont.truetype(path, size)
        except: continue
    return ImageFont.load_default()

def upload_image(bot, image):
    """TalkinChat specific image upload"""
    try:
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        files = {'file': ('tic.png', img_byte_arr, 'image/png')}
        r = requests.post(UPLOAD_URL, files=files, timeout=15)
        if r.status_code == 200:
            url = r.text.strip()
            if "http" in url: return url
            try: return r.json().get('url')
            except: pass
    except Exception as e:
        bot.log(f"Upload Error: {e}")
    return None

def get_avatar_img(url):
    try:
        if not url: return None
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            img = Image.open(io.BytesIO(res.content)).convert("RGBA")
            img = img.resize((120, 120))
            mask = Image.new('L', (120, 120), 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, 120, 120), fill=255)
            output = Image.new('RGBA', (120, 120), (0,0,0,0))
            output.paste(img, (0,0), mask)
            return output
    except: return None

def draw_winner_card(username, winner_symbol, avatar_url=None):
    W, H = 400, 400
    bg = (25, 10, 10) if winner_symbol == 'X' else (10, 10, 25)
    img = Image.new('RGB', (W, H), color=bg)
    d = ImageDraw.Draw(img)
    col = (255, 60, 60) if winner_symbol == 'X' else (60, 100, 255)
    d.rectangle([(10, 10), (W-10, H-10)], outline=col, width=6)

    real_avatar = get_avatar_img(avatar_url)
    cx, cy = W//2, 130
    if real_avatar:
        img.paste(real_avatar, (cx - 60, cy - 60), real_avatar)
        d.ellipse([(cx-60, cy-60), (cx+60, cy+60)], outline="white", width=4)
    else:
        rad = 60
        d.ellipse([(cx-rad, cy-rad), (cx+rad, cy+rad)], fill=(60, 60, 60), outline="white", width=4)
        initial = username[0].upper()
        fnt_av = get_font(70)
        d.text((cx-25, cy-45), initial, fill="white", font=fnt_av)

    fnt_name, fnt_title = get_font(40), get_font(30)
    d.text((W//2 - 80, 220), f"@{username}", fill="white", font=fnt_name)
    d.text((W//2 - 95, 290), "🏆 WINNER 🏆", fill="yellow", font=fnt_title)
    return img

def draw_board(board_state):
    size = 400
    cell = size // 3
    img = Image.new('RGB', (size, size), color=(20, 20, 25)) 
    d = ImageDraw.Draw(img)
    fnt_num = get_font(60)
    for i in range(1, 3):
        d.line([(cell * i, 15), (cell * i, size - 15)], fill=(100, 100, 100), width=4)
        d.line([(15, cell * i), (size - 15, cell * i)], fill=(100, 100, 100), width=4)
    for i in range(9):
        row, col = i // 3, i % 3
        x, y = col * cell, row * cell
        cx, cy = x + cell // 2, y + cell // 2
        val = board_state[i]
        if val is None:
            d.text((cx-20, cy-40), str(i+1), font=fnt_num, fill=(50, 50, 60)) 
        elif val == 'X':
            offset = 30
            d.line([(x+offset, y+offset), (x+cell-offset, y+cell-offset)], fill=(255, 50, 50), width=15)
            d.line([(x+cell-offset, y+offset), (x+offset, y+cell-offset)], fill=(255, 50, 50), width=15)
        elif val == 'O':
            offset = 30
            d.ellipse([(x+offset, y+offset), (x+cell-offset, y+cell-offset)], outline=(50, 150, 255), width=15)
    return img

# --- GAME LOGIC CLASS ---
class TicTacToe:
    def __init__(self, room_name, creator_name, creator_avatar=None):
        self.room_name = room_name
        self.p1_name = creator_name
        self.p1_avatar = creator_avatar
        self.p2_name = None
        self.p2_avatar = None
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
        # Win check
        for m in empty:
            self.board[m] = 'O'
            if self.check_win() == 'O': self.board[m] = None; return m
            self.board[m] = None
        # Block check
        for m in empty:
            self.board[m] = 'X'
            if self.check_win() == 'X': self.board[m] = None; return m
            self.board[m] = None
        if 4 in empty: return 4
        return random.choice(empty)

# --- COMMAND HANDLER ---
def handle_command(bot, command, room_name, user, args, data):
    try:
        global games, BOT_INSTANCE
        if BOT_INSTANCE is None: BOT_INSTANCE = bot
        
        avatar_url = data.get("avatar_url") # TalkinChat payload field
        cmd_clean = command.lower().strip()
        with games_lock: current_game = games.get(room_name)

        if cmd_clean == "tic":
            if current_game:
                bot.send_message(room_name, "⚠️ Game running! Type 'stop'.")
                return True
            with games_lock: games[room_name] = TicTacToe(room_name, user, avatar_url)
            bot.send_message(room_name, f"🎮 **Tic-Tac-Toe**\n@{user}, Choose:\n1️⃣ Single\n2️⃣ Multi")
            return True

        if cmd_clean == "stop" and current_game:
            with games_lock: del games[room_name]
            bot.send_message(room_name, "🛑 Stopped.")
            return True

        if current_game:
            game = current_game
            # Identify Players
            if game.state == 'setup_mode' and user == game.p1_name:
                if cmd_clean == "1":
                    game.mode = 1; game.p2_name = "Bot"; game.state = 'setup_bet'; game.touch()
                    bot.send_message(room_name, "💰 Mode?\n1️⃣ Free (Win 500)\n2️⃣ Bet 100 (Win 700)")
                    return True
                elif cmd_clean == "2":
                    game.mode = 2; game.state = 'setup_bet'; game.touch()
                    bot.send_message(room_name, "💰 Bet?\n1️⃣ Fun (No Reward)\n2️⃣ Bet 100 Coins")
                    return True
            
            elif game.state == 'setup_bet' and user == game.p1_name:
                if cmd_clean in ["1", "2"]:
                    game.bet = 0 if cmd_clean == "1" else 100; game.touch()
                    if game.bet > 0: db.add_game_result(game.p1_name, game.p1_name, "tictactoe", -game.bet)
                    
                    if game.mode == 1:
                        game.state = 'playing'
                        img = draw_board(game.board); url = upload_image(bot, img)
                        bot.send_message(room_name, f"🔥 vs Bot 🤖\nType 1-9")
                        if url: bot.send_image(room_name, url)
                    else:
                        game.state = 'waiting_join'
                        bot.send_message(room_name, f"⚔️ Type 'j' to join!")
                    return True
            
            elif game.state == 'waiting_join':
                if cmd_clean in ["j", "join"]:
                    if user == game.p1_name: return True
                    game.p2_name = user; game.p2_avatar = avatar_url; game.touch(); game.state = 'playing'
                    if game.bet > 0: db.add_game_result(user, user, "tictactoe", -game.bet)
                    img = draw_board(game.board); url = upload_image(bot, img)
                    bot.send_message(room_name, f"🥊 @{game.p1_name} vs @{game.p2_name}\n@{game.p1_name} turn!")
                    if url: bot.send_image(room_name, url)
                    return True
            
            elif game.state == 'playing':
                if cmd_clean.isdigit() and 1 <= int(cmd_clean) <= 9:
                    idx = int(cmd_clean) - 1
                    curr_p = game.p1_name if game.turn == 'X' else game.p2_name
                    if user != curr_p: return False
                    if game.board[idx]: return True
                    
                    game.board[idx] = game.turn; game.touch()
                    win = game.check_win()
                    
                    if win:
                        w_nm = game.p1_name if win=='X' else game.p2_name
                        w_av = game.p1_avatar if win=='X' else game.p2_avatar
                        if win == 'draw':
                            bot.send_message(room_name, "🤝 Draw! Coins refunded.")
                            if game.bet > 0:
                                db.add_game_result(game.p1_name, game.p1_name, "tictactoe", game.bet)
                                if game.mode == 2: db.add_game_result(game.p2_name, game.p2_name, "tictactoe", game.bet)
                        else:
                            reward = 0
                            if game.mode == 1: reward = 500 if game.bet == 0 else 700
                            else: reward = game.bet * 2
                            db.add_game_result(w_nm, w_nm, "tictactoe", reward, is_win=True)
                            
                            card = draw_winner_card(w_nm, win, w_av); url = upload_image(bot, card)
                            if url: bot.send_image(room_name, url)
                            bot.send_message(room_name, f"🎉 @{w_nm} WON {reward} coins!")
                        with games_lock: del games[room_name]
                        return True

                    game.turn = 'O' if game.turn == 'X' else 'X'
                    if game.mode == 1 and game.turn == 'O':
                        b_idx = game.bot_move()
                        if b_idx is not None:
                            game.board[b_idx] = 'O'
                            if game.check_win():
                                img = draw_board(game.board); url = upload_image(bot, img)
                                if url: bot.send_image(room_name, url)
                                bot.send_message(room_name, "🤖 Bot Won!")
                                with games_lock: del games[room_name]
                                return True
                            game.turn = 'X'
                    
                    img = draw_board(game.board); url = upload_image(bot, img)
                    if url: bot.send_image(room_name, url)
                    return True
        return False
    except: traceback.print_exc(); return False
