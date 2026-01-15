import time, random, requests, io, sys, os, threading, traceback, urllib3
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

def setup(bot_ref):
    global BOT_INSTANCE
    BOT_INSTANCE = bot_ref
    BOT_INSTANCE.log("✅ TicTacToe: Ultimate Graphic Version Loaded.")

# --- HELPER: SAFE FONT ---
def get_font(size):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "arial.ttf"
    ]
    for p in paths:
        try: return ImageFont.truetype(p, size)
        except: continue
    return ImageFont.load_default()

# --- HELPER: CIRCULAR AVATAR ---
def get_circular_avatar(url):
    try:
        if not url or not url.startswith("http"): return None
        resp = requests.get(url, timeout=5, verify=False)
        img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        img = img.resize((180, 180), Image.Resampling.LANCZOS)
        mask = Image.new('L', (180, 180), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, 180, 180), fill=255)
        output = ImageOps.fit(img, (180, 180), centering=(0.5, 0.5))
        output.putalpha(mask)
        return output
    except: return None

# --- HELPER: STABLE UPLOAD (Catbox) ---
def upload_image(bot, image):
    try:
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        buf.seek(0)
        f = {'reqtype': (None, 'fileupload'), 'fileToUpload': ('board.png', buf, 'image/png')}
        r = requests.post('https://catbox.moe/user/api.php', files=f, timeout=10)
        if r.status_code == 200: return r.text.strip()
    except: pass
    return None

# --- VISUALS: MODERN BOARD ---
def draw_board(board_state):
    size = 450
    cell = size // 3
    img = Image.new('RGB', (size, size), color=(15, 15, 20)) 
    d = ImageDraw.Draw(img)
    fnt_hint = get_font(120) # Huge Hint Numbers
    
    # Grid
    for i in range(1, 3):
        d.line([(cell*i, 20), (cell*i, size-20)], fill=(40, 40, 50), width=5)
        d.line([(20, cell*i), (size-20, cell*i)], fill=(40, 40, 50), width=5)

    for i in range(9):
        r, c = i // 3, i % 3
        x, y = c * cell, r * cell
        cx, cy = x + cell // 2, y + cell // 2
        val = board_state[i]
        
        if val is None:
            # Huge Faint Numbers
            d.text((cx-35, cy-70), str(i+1), font=fnt_hint, fill=(25, 25, 32)) 
        elif val == 'X':
            off = 45
            d.line([(x+off, y+off), (x+cell-off, y+cell-off)], fill=(255, 50, 100), width=16)
            d.line([(x+cell-off, y+off), (x+off, y+cell-off)], fill=(255, 50, 100), width=16)
        elif val == 'O':
            off = 45
            d.ellipse([(x+off, y+off), (x+cell-off, y+cell-off)], outline=(0, 240, 255), width=16)
    return img

# --- VISUALS: WINNER CARD ---
def draw_winner_card(username, avatar_url, symbol):
    size = 450
    img = Image.new('RGB', (size, size), color=(10, 10, 15))
    d = ImageDraw.Draw(img)
    color = (255, 50, 100) if symbol == 'X' else (0, 240, 255)
    d.rectangle([10, 10, 440, 440], outline=color, width=12)

    av = get_circular_avatar(avatar_url)
    if av:
        img.paste(av, (size//2 - 90, 60), av)
        d.ellipse([size//2-92, 58, size//2+92, 242], outline="white", width=4)
    
    fnt_win = get_font(55)
    fnt_name = get_font(40)
    d.text((size//2-115, 270), "WINNER!", fill="yellow", font=fnt_win)
    d.text((size//2-90, 340), f"@{username[:15]}", fill="white", font=fnt_name)
    d.text((size//2-25, 385), "🏆", font=fnt_win)
    return img

class TicSession:
    def __init__(self, room, p1_id, p1_name, p1_av):
        self.room = room
        self.p1_id, self.p1_name, self.p1_av = p1_id, p1_name, p1_av
        self.p2_id = self.p2_name = self.p2_av = None
        self.board = [None] * 9
        self.turn = 'X'
        self.state = 'setup_mode'
        self.mode = None
        self.bet = 0
        self.last_interaction = time.time()
    def touch(self): self.last_interaction = time.time()

# --- HANDLER ---
def handle_command(bot, command, room, user, args, data):
    try:
        uid = str(data.get('user_id') or data.get('from_id') or user)
        av_url = data.get('avatar_url') or ""
        cmd = command.lower().strip()
        
        global games
        with games_lock:
            game = games.get(room)

            if cmd == "tic":
                if game: return True
                games[room] = TicSession(room, uid, user, av_url)
                bot.send_message(room, f"🎮 **Tic-Tac-Toe**\n@{user}, choose:\n1️⃣ Single\n2️⃣ Multi")
                return True

            if game:
                game.touch()
                if cmd == "stop" and uid == game.p1_id:
                    del games[room]; bot.send_message(room, "🛑 Game stopped."); return True

                if game.state == 'setup_mode' and uid == game.p1_id:
                    if cmd in ["1", "2"]:
                        game.mode = int(cmd); game.state = 'setup_bet'
                        if game.mode == 1: game.p2_name, game.p2_id = "Bot", "BOT"
                        bot.send_message(room, "💰 Select Bet:\n1️⃣ Free Match\n2️⃣ Bet 100 Coins")
                        return True

                elif game.state == 'setup_bet' and uid == game.p1_id:
                    if cmd in ["1", "2"]:
                        game.bet = 0 if cmd == "1" else 100
                        if game.bet > 0: add_game_result(game.p1_id, game.p1_name, "tictactoe", -game.bet)
                        game.state = 'playing' if game.mode == 1 else 'waiting_join'
                        if game.mode == 1:
                            url = upload_image(bot, draw_board(game.board))
                            bot.send_message(room, f"🔥 VS Pro Bot! Move (1-9)."); if url: bot.send_image(room, url)
                        else: bot.send_message(room, f"⚔️ Lobby Open! Bet: {game.bet}\nType `join` to play.")
                        return True

                elif game.state == 'waiting_join' and cmd == "join":
                    if uid == game.p1_id: return True
                    game.p2_id, game.p2_name, game.p2_av = uid, user, av_url
                    if game.bet > 0: add_game_result(uid, user, "tictactoe", -game.bet)
                    game.state = 'playing'
                    url = upload_image(bot, draw_board(game.board))
                    bot.send_message(room, f"🥊 Match: @{game.p1_name} vs @{game.p2_name}"); if url: bot.send_image(room, url)
                    return True

                elif game.state == 'playing' and cmd.isdigit():
                    idx = int(cmd) - 1
                    if not (0 <= idx <= 8): return False
                    curr_id = game.p1_id if game.turn == 'X' else game.p2_id
                    if uid != curr_id or game.board[idx]: return True
                    
                    game.board[idx] = game.turn
                    wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
                    winner_found = False
                    for a,b,c in wins:
                        if game.board[a] and game.board[a] == game.board[b] == game.board[c]:
                            finish_game(bot, room, game, game.board[a]); winner_found = True; break
                    
                    if not winner_found and None not in game.board:
                        finish_game(bot, room, game, 'draw'); winner_found = True

                    if not winner_found:
                        game.turn = 'O' if game.turn == 'X' else 'X'
                        if game.mode == 1 and game.turn == 'O':
                            empty = [i for i, x in enumerate(game.board) if x is None]
                            if empty:
                                game.board[random.choice(empty)] = 'O'
                                for a,b,c in wins:
                                    if game.board[a] and game.board[a] == game.board[b] == game.board[c]:
                                        finish_game(bot, room, game, 'O'); winner_found = True; break
                                if not winner_found and None not in game.board:
                                    finish_game(bot, room, game, 'draw'); winner_found = True
                                game.turn = 'X'
                        
                        if not winner_found:
                            url = upload_image(bot, draw_board(game.board))
                            if url: bot.send_image(room, url)
                    return True
    except Exception as e:
        bot.log(f"⚠️ [TicTacToe Error] {e}")
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
            bot.send_message(room, f"🎉🏆 @{w_nm} WON {reward} coins!")
            card = upload_image(bot, draw_winner_card(w_nm, w_av, winner))
            if card: bot.send_image(room, card)
        else:
            bot.send_message(room, "🤖 Bot Wins!"); url = upload_image(bot, draw_board(game.board))
            if url: bot.send_image(room, url)
    
    with games_lock:
        if room in games: del games[room]
