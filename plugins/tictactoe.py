import time, random, threading, sys, os, traceback, gc
from PIL import Image, ImageDraw, ImageFont, ImageOps
import utils

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
    BOT_INSTANCE.log("✅ TicTacToe: Neon UI & Multiplayer Fixed.")

# --- CLEANER THREAD (90s Timeout) ---
def game_cleanup_loop():
    while True:
        time.sleep(10)
        now = time.time()
        to_remove = []
        
        with games_lock:
            for r, g in games.items():
                # Check 90s inactivity
                if now - g.last_interaction > 90:
                    to_remove.append(r)
            
            for r in to_remove:
                g = games[r]
                # Refund logic
                if g.bet > 0:
                    add_game_result(g.p1_id, g.p1_name, "tictactoe", g.bet, False)
                    if g.p2_id and g.p2_id != "BOT":
                        add_game_result(g.p2_id, g.p2_name, "tictactoe", g.bet, False)
                
                if BOT_INSTANCE:
                    BOT_INSTANCE.send_message(r, "⌛ Game ended due to inactivity. (Bets refunded)")
                del games[r]
                gc.collect()

threading.Thread(target=game_cleanup_loop, daemon=True).start()

# --- VISUALS: PREMIUM DARK NEON BOARD ---
def build_board(board_state):
    # 1. Ultra Dark Background (Cyberpunk feel)
    canv = utils.create_canvas(450, 450, color=(5, 5, 10)) 
    d = ImageDraw.Draw(canv)
    
    # 2. Glowing Grid (Cyan Neon)
    # Layer 1: Wide faint glow
    for i in range(1, 3):
        d.line([(150*i, 20), (150*i, 430)], fill=(0, 100, 100), width=10)
        d.line([(20, 150*i), (430, 150*i)], fill=(0, 100, 100), width=10)
    # Layer 2: Sharp bright center
    for i in range(1, 3):
        d.line([(150*i, 20), (150*i, 430)], fill=(0, 255, 255), width=4)
        d.line([(20, 150*i), (430, 150*i)], fill=(0, 255, 255), width=4)

    # 3. Ghost Hint Numbers
    fnt_hint = utils.get_font("arial.ttf", 100)
    
    for i, val in enumerate(board_state):
        r, c = i // 3, i % 3
        bx, by = c * 150, r * 150
        cx, cy = bx + 75, by + 75
        
        if val is None:
            # Subtle Grey Number
            d.text((cx-30, cy-60), str(i+1), font=fnt_hint, fill=(30, 35, 45))
        
        elif val == "X":
            # Sharp Red Cross
            off = 40
            # Shadow
            d.line([(bx+off+2, by+off+2), (bx+150-off+2, by+150-off+2)], fill=(100, 0, 0), width=14)
            d.line([(bx+150-off+2, by+off+2), (bx+off+2, by+150-off+2)], fill=(100, 0, 0), width=14)
            # Main
            d.line([(bx+off, by+off), (bx+150-off, by+150-off)], fill=(255, 0, 60), width=12)
            d.line([(bx+150-off, by+off), (bx+off, by+150-off)], fill=(255, 0, 60), width=12)
            
        elif val == "O":
            # Sharp Blue Circle
            off = 40
            # Shadow
            d.ellipse([bx+off+2, by+off+2, bx+150-off+2, by+150-off+2], outline=(0, 0, 100), width=14)
            # Main
            d.ellipse([bx+off, by+off, bx+150-off, by+150-off], outline=(0, 150, 255), width=12)
            
    return canv

def build_winner_card(username, av_url, symbol):
    canv = utils.create_canvas(450, 450)
    utils.draw_gradient_bg(canv, (10, 10, 20), (5, 5, 10))
    
    color = (255, 0, 60) if symbol == "X" else (0, 150, 255)
    utils.draw_rounded_rect(canv, [15, 15, 435, 435], 25, color, width=8)
    utils.draw_circle_avatar(canv, av_url, 135, 60, 180, border_color=color)
    
    fnt_win = utils.get_font("impact.ttf", 60)
    fnt_name = utils.get_font("bebas-neue.ttf", 45)
    
    d = ImageDraw.Draw(canv)
    d.text((120, 270), "WINNER!", font=fnt_win, fill="yellow")
    d.text((140, 345), f"@{username[:12]}", font=fnt_name, fill="white")
    return canv

# --- GAME LOGIC ---
class TicGame:
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

def check_win(b):
    w = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
    for a,x,c in w:
        if b[a] and b[a] == b[x] == b[c]: return b[a]
    return 'draw' if None not in b else None

def bot_move(board):
    empty = [i for i, x in enumerate(board) if x is None]
    if not empty: return None
    for m in empty: # Win
        board[m] = 'O'; 
        if check_win(board) == 'O': board[m] = None; return m
        board[m] = None
    for m in empty: # Block
        board[m] = 'X'; 
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

        # 1. START GAME
        if cmd == "tic":
            if game:
                bot.send_message(room, f"⚠️ Game running! Finish or type `stop`.")
                return True
            games[room] = TicGame(room, uid, user, av)
            bot.send_message(room, f"🎮 **Tic-Tac-Toe**\n@{user}, Choose Mode:\n1️⃣ Single (vs Bot)\n2️⃣ Multi (vs Player)")
            return True

        if cmd == "stop" and game:
            # Check Admin or Player
            if uid == str(game.p1_id) or (game.p2_id and uid == str(game.p2_id)) or (db.is_admin(uid) if 'db' in globals() else False):
                if game.bet > 0:
                    add_game_result(game.p1_id, game.p1_name, "tictactoe", game.bet, False)
                    if game.p2_id and game.p2_id != "BOT":
                        add_game_result(game.p2_id, game.p2_name, "tictactoe", game.bet, False)
                    bot.send_message(room, "🛑 Game Stopped. Bets Refunded.")
                else:
                    bot.send_message(room, "🛑 Game Stopped.")
                del games[room]
                gc.collect()
            return True

        if game:
            game.touch() # Reset 90s timer
            
            # 2. MODE SELECT
            if game.state == 'setup_mode' and uid == str(game.p1_id):
                if cmd == "1":
                    game.mode = 1; game.p2_name, game.p2_id = "Bot", "BOT"
                    # Single player starts immediately
                    game.state = 'playing'
                    url = utils.upload_image(build_board(game.board))
                    bot.send_message(room, "🔥 **VS PRO BOT**\nReward: 500. Your Turn (1-9):")
                    if url: bot.send_image(room, url)
                    return True
                elif cmd == "2":
                    game.mode = 2; game.state = 'setup_bet'
                    bot.send_message(room, "💰 **Betting?**\n1️⃣ Fun (No Bet)\n2️⃣ Bet 100")
                    return True

            # 3. BET SELECT (Multi Only)
            elif game.state == 'setup_bet' and uid == str(game.p1_id):
                if cmd in ["1", "2"]:
                    game.bet = 0 if cmd == "1" else 100
                    if game.bet > 0: add_game_result(game.p1_id, game.p1_name, "tictactoe", -game.bet)
                    game.state = 'waiting_join'
                    bot.send_message(room, f"⚔️ **Lobby Open!** Bet: {game.bet}\nType `join` to play.")
                    return True

            # 4. JOIN (Multi Only)
            elif game.state == 'waiting_join' and cmd == "join":
                if uid == str(game.p1_id): return True
                game.p2_id, game.p2_name, game.p2_av = uid, user, av
                if game.bet > 0: add_game_result(uid, user, "tictactoe", -game.bet)
                game.state = 'playing'
                url = utils.upload_image(build_board(game.board))
                bot.send_message(room, f"🥊 **MATCH START!**\n@{game.p1_name} (X) vs @{game.p2_name} (O)\n@{game.p1_name}, your move!")
                if url: bot.send_image(room, url)
                return True

            # 5. PLAY MOVE
            elif game.state == 'playing' and cmd.isdigit():
                idx = int(cmd) - 1
                if not (0 <= idx <= 8): return False
                
                # Turn & ID Check (Fixed)
                curr_turn_id = str(game.p1_id) if game.turn == 'X' else str(game.p2_id)
                if uid != curr_turn_id: return True # Ignore wrong player
                if game.board[idx]: return True # Ignore taken box
                
                # Apply Move
                game.board[idx] = game.turn
                res = check_win(game.board)
                if res: finish_match(bot, room, game, res); return True

                # Switch Turn
                game.turn = 'O' if game.turn == 'X' else 'X'
                
                # Bot Logic
                if game.mode == 1 and game.turn == 'O':
                    m = bot_move(game.board)
                    if m is not None:
                        game.board[m] = 'O'
                        res = check_win(game.board)
                        if res: finish_match(bot, room, game, res); return True
                        game.turn = 'X'

                url = utils.upload_image(build_board(game.board))
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
        if res == 'X': w_id, w_nm, w_av = game.p1_id, game.p1_name, game.p1_av
        else: w_id, w_nm, w_av = game.p2_id, game.p2_name, game.p2_av

        if str(w_id) == "BOT":
            bot.send_message(room, "🤖 **Bot Wins!**")
        else:
            reward = 0
            if game.mode == 1: reward = 500
            else: reward = (game.bet * 2) if game.bet > 0 else 500
            
            add_game_result(w_id, w_nm, "tictactoe", reward, True)
            bot.send_message(room, f"🏆 **@{w_nm} WINS!** +{reward} Coins")
            
            url = utils.upload_image(build_winner_card(w_nm, w_av, res))
            if url: bot.send_image(room, url)

    with games_lock:
        if room in games:
            del games[room]
            gc.collect()
