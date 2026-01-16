import time, random, threading, sys, os, traceback, gc
from PIL import Image, ImageDraw, ImageFont
import utils # Hamara Advanced Toolkit

# --- DB IMPORT ---
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from db import add_game_result
except: pass

# --- GLOBAL STATE ---
games = {} 
games_lock = threading.Lock()
BOT_INSTANCE = None 

def setup(bot_ref):
    global BOT_INSTANCE
    BOT_INSTANCE = bot_ref
    BOT_INSTANCE.log("✅ TicTacToe Expert Edition: Logic & Visuals Loaded.")

# --- CLEANER THREAD (90s Inactivity + Refund) ---
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
                game = games[room_name]
                # Refund Bet if Multiplayer and match was active
                if game.bet > 0:
                    add_game_result(game.p1_id, game.p1_name, "tictactoe", game.bet, False)
                    if game.p2_id and game.p2_id != "BOT":
                        add_game_result(game.p2_id, game.p2_name, "tictactoe", game.bet, False)
                
                if BOT_INSTANCE:
                    BOT_INSTANCE.send_message(room_name, "⌛ Match ended due to inactivity. (Refunded if bet)")
                del games[room_name]
                gc.collect()

threading.Thread(target=game_cleanup_loop, daemon=True).start()

# --- VISUAL ENGINE (Premium Board) ---

def build_board(board_state):
    # 1. Dark Premium Canvas
    canv = utils.create_canvas(450, 450, color=(15, 15, 20))
    d = ImageDraw.Draw(canv)
    
    # 2. Neon Grid
    grid_col = (50, 50, 65)
    for i in range(1, 3):
        d.line([(150*i, 30), (150*i, 420)], fill=grid_col, width=5)
        d.line([(30, 150*i), (420, 150*i)], fill=grid_col, width=5)

    # 3. Hint Numbers & Moves
    hint_fnt = utils.get_font("arial.ttf", 100)
    for i, val in enumerate(board_state):
        r, c = i // 3, i % 3
        bx, by = c * 150, r * 150
        cx, cy = bx + 75, by + 75
        
        if val is None:
            # Faint hint numbers
            d.text((cx-30, cy-65), str(i+1), font=hint_fnt, fill=(28, 30, 38))
        elif val == "X":
            # Neon Red X
            off = 45
            d.line([(bx+off, by+off), (bx+150-off, by+150-off)], fill=(255, 65, 108), width=16)
            d.line([(bx+150-off, by+off), (bx+off, by+150-off)], fill=(255, 65, 108), width=16)
        elif val == "O":
            # Neon Cyan O
            off = 45
            d.ellipse([bx+off, by+off, bx+150-off, by+150-off], outline=(0, 242, 255), width=16)
            
    return canv

def build_winner_card(username, av_url, symbol):
    # 450x450 Ratio as requested
    canv = utils.create_base_canvas(450, 450)
    utils.draw_gradient_bg(canv, (25, 25, 40), (10, 10, 15))
    
    color = (255, 65, 108) if symbol == "X" else (0, 242, 255)
    utils.draw_rounded_rect(canv, [15, 15, 435, 435], 25, color, width=12)
    
    # Rounded Avatar
    utils.draw_circle_avatar(canv, av_url, 135, 60, 180, border_color=color)
    
    # Winner Text
    fnt_win = utils.get_font("impact.ttf", 60)
    fnt_name = utils.get_font("bebas-neue.ttf", 45)
    
    d = ImageDraw.Draw(canv)
    d.text((120, 270), "WINNER!", font=fnt_win, fill="yellow")
    d.text((140, 345), f"@{username[:12]}", font=fnt_name, fill="white")
    
    return canv

# --- SESSION LOGIC ---
class TicGame:
    def __init__(self, room, p1_id, p1_name, p1_av):
        self.room = room
        self.p1_id, self.p1_name, self.p1_av = p1_id, p1_name, p1_av
        self.p2_id = self.p2_name = self.p2_av = None
        self.board = [None] * 9
        self.turn = 'X'; self.state = 'setup_mode'; self.mode = None; self.bet = 0
        self.last_interaction = time.time()
    def touch(self): self.last_interaction = time.time()

# --- HELPERS ---
def check_win(b):
    w = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
    for a,x,c in w:
        if b[a] and b[a] == b[x] == b[c]: return b[a]
    return 'draw' if None not in b else None

def bot_move(board):
    empty = [i for i, x in enumerate(board) if x is None]
    if not empty: return None
    # 1. Win
    for m in empty:
        board[m] = 'O'
        if check_win(board) == 'O': board[m] = None; return m
        board[m] = None
    # 2. Block
    for m in empty:
        board[m] = 'X'
        if check_win(board) == 'X': board[m] = None; return m
        board[m] = None
    return random.choice(empty)

# --- HANDLER ---
def handle_command(bot, command, room, user, args, data):
    uid = str(data.get('user_id') or data.get('userid') or user)
    av = data.get('avatar_url') or ""
    cmd = command.lower().strip()
    
    global games
    with games_lock:
        game = games.get(room)

        # START
        if cmd == "tic":
            if game: return True
            games[room] = TicGame(room, uid, user, av)
            bot.send_message(room, f"🎮 **Tic-Tac-Toe**\n@{user}, Choose Mode:\n1️⃣ Single (Bot)\n2️⃣ Multi (Player)")
            return True

        if game:
            game.touch()
            # 1. MODE SELECTION
            if game.state == 'setup_mode' and uid == game.p1_id:
                if cmd == "1":
                    game.mode = 1; game.p2_name, game.p2_id = "Bot", "BOT"
                    game.state = 'playing' # Single player start immediately (Fixed 500 reward)
                    url = utils.upload_image(build_board(game.board))
                    bot.send_message(room, "🔥 **VS PRO BOT**\nWin: 500 Coins. Move (1-9):")
                    if url: bot.send_image(room, url)
                    return True
                elif cmd == "2":
                    game.mode = 2; game.state = 'setup_bet'
                    bot.send_message(room, "💰 **Betting?**\n1️⃣ Fun (No Bet, Win 500)\n2️⃣ Bet 100 (Pot 200)")
                    return True

            # 2. BET SELECTION (Multiplayer Only)
            elif game.state == 'setup_bet' and uid == game.p1_id:
                if cmd in ["1", "2"]:
                    game.bet = 0 if cmd == "1" else 100
                    if game.bet > 0: add_game_result(game.p1_id, game.p1_name, "tictactoe", -game.bet)
                    game.state = 'waiting_join'
                    bot.send_message(room, f"⚔️ **Lobby Open!** Bet: {game.bet}\nType `join` to enter match.")
                    return True

            # 3. JOIN
            elif game.state == 'waiting_join' and cmd == "join":
                if uid == game.p1_id: return True
                game.p2_id, game.p2_name, game.p2_av = uid, user, av
                if game.bet > 0: add_game_result(uid, user, "tictactoe", -game.bet)
                game.state = 'playing'
                url = utils.upload_image(build_board(game.board))
                bot.send_message(room, f"🥊 Match: @{game.p1_name} vs @{game.p2_name}\n@{game.p1_name} turn!")
                if url: bot.send_image(room, url)
                return True

            # 4. MOVES
            elif game.state == 'playing' and cmd.isdigit():
                idx = int(cmd) - 1
                curr_turn_id = game.p1_id if game.turn == 'X' else game.p2_id
                if uid != curr_turn_id or not (0 <= idx <= 8) or game.board[idx]: return True
                
                game.board[idx] = game.turn
                res = check_win(game.board)
                if res: finish_match(bot, room, game, res); return True

                # Switch
                game.turn = 'O' if game.turn == 'X' else 'X'
                
                # BOT MOVE
                if game.mode == 1 and game.turn == 'O':
                    m = bot_move(game.board)
                    if m is not None:
                        game.board[m] = 'O'
                        res = check_win(game.board)
                        if res: finish_match(bot, room, game, res); return True
                        game.turn = 'X'

                img = build_board(game.board); url = utils.upload_image(img)
                if url: bot.send_image(room, url)
                return True
    return False

def finish_match(bot, room, game, res):
    if res == 'draw':
        bot.send_message(room, "🤝 **Draw!** Bet refunded.")
        if game.bet > 0:
            add_game_result(game.p1_id, game.p1_name, "tictactoe", game.bet)
            if game.p2_id != "BOT": add_game_result(game.p2_id, game.p2_name, "tictactoe", game.bet)
    else:
        # Determine Winner
        if res == 'X': w_id, w_nm, w_av = game.p1_id, game.p1_name, game.p1_av
        else: w_id, w_nm, w_av = game.p2_id, game.p2_name, game.p2_av

        if w_id == "BOT":
            bot.send_message(room, "🤖 **Bot Wins!** Better luck next time.")
        else:
            # Reward Logic
            reward = 0
            if game.mode == 1: reward = 500 # Single player fixed 500
            else: reward = (game.bet * 2) if game.bet > 0 else 500 # Multi: Pot or 500
            
            add_game_result(w_id, w_nm, "tictactoe", reward, True)
            bot.send_message(room, f"🏆 **@{w_nm} WINS!** Received {reward} coins.")
            
            # Draw Winner Card
            win_card = build_winner_card(w_nm, w_av, res)
            card_url = utils.upload_image(win_card)
            if card_url: bot.send_image(room, card_url)

    with games_lock:
        if room in games: del games[room]
        gc.collect() # Force Memory Cleanup
