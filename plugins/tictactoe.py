import time
import threading
import random
from PIL import Image, ImageDraw, ImageFont

# Local imports
import utils
import db

# --- VISUAL CONFIGURATION (Neon Theme) ---
NEON_GREEN = (57, 255, 20)
NEON_PINK = (255, 16, 240)
NEON_BLUE = (44, 255, 255)
BG_COLOR = (17, 24, 39)
GRID_COLOR = (139, 92, 246)
BOARD_SIZE = 500

# --- GAME STATE ---
games = {}
game_lock = threading.Lock()

def setup(bot):
    bot.log("🎮 Tic Tac Toe (Full & Robust) Loaded")

# --- DATABASE HELPERS ---
def get_user_balance(user_id):
    """User ka current balance check karta hai."""
    try:
        conn = db.get_connection()
        cur = conn.cursor()
        ph = "%s" if db.DATABASE_URL.startswith("postgres") else "?"
        cur.execute(f"SELECT global_score FROM users WHERE user_id = {ph}", (str(user_id),))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else 0
    except:
        return 0

# --- SAFE IMAGE SENDER (THE FIX) ---
def send_game_state(bot, room_name, game, text_msg):
    """
    Ye function pehle Image upload karne ki koshish karega.
    Agar fail hua, toh Text Board bhejega taaki game na ruke.
    """
    try:
        # 1. Image Generate karo
        img = draw_neon_board(game)
        # 2. Upload karo (Utils wala naya function)
        url = utils.upload_image(img)
        
        if url:
            # Success: Image bhejo
            bot.send_image(room_name, url)
            bot.send_message(room_name, text_msg)
        else:
            # Fail: Text Board Fallback
            board_display = "\n".join([" | ".join(game['board'][i:i+3]) for i in range(0, 9, 3)])
            fallback_msg = f"{text_msg}\n⚠️ (Image Upload Failed)\n\nCurrent Board:\n`{board_display}`"
            bot.send_message(room_name, fallback_msg)
            
    except Exception as e:
        print(f"Send Error: {e}")
        # Critical Fallback
        bot.send_message(room_name, text_msg)

# --- GRAPHICS ENGINE ---
def draw_neon_board(game_data):
    canvas = utils.create_canvas(BOARD_SIZE, BOARD_SIZE, color=BG_COLOR)
    draw = ImageDraw.Draw(canvas)
    
    # Grid Lines
    width = 8
    draw.line([(166, 20), (166, 480)], fill=GRID_COLOR, width=width)
    draw.line([(332, 20), (332, 480)], fill=GRID_COLOR, width=width)
    draw.line([(20, 166), (480, 166)], fill=GRID_COLOR, width=width)
    draw.line([(20, 332), (480, 332)], fill=GRID_COLOR, width=width)

    def get_center(idx):
        return (((idx - 1) % 3) * 166 + 83, ((idx - 1) // 3) * 166 + 83)

    font_lg = utils.get_font("arial.ttf", 100)
    font_sm = utils.get_font("arial.ttf", 40)
    
    for i, mark in enumerate(game_data['board']):
        cx, cy = get_center(i + 1)
        if mark == "X":
            draw.text((cx, cy), "X", font=font_lg, fill=NEON_PINK, anchor="mm", stroke_width=2)
        elif mark == "O":
            draw.text((cx, cy), "O", font=font_lg, fill=NEON_GREEN, anchor="mm", stroke_width=2)
        else:
            # Ghost numbers help user know where to click
            draw.text((cx, cy), str(i+1), font=font_sm, fill=(60, 60, 70), anchor="mm")
    return canvas

def draw_winner_card(winner_name, winner_avatar_url, symbol, amount):
    canvas = utils.create_canvas(BOARD_SIZE, BOARD_SIZE, color=BG_COLOR)
    utils.draw_gradient_bg(canvas, BG_COLOR, (30, 0, 30) if symbol == "X" else (0, 30, 0))
    draw = ImageDraw.Draw(canvas)
    cx, cy = BOARD_SIZE // 2, BOARD_SIZE // 2 - 50
    
    # Avatar
    utils.draw_circle_avatar(canvas, winner_avatar_url, cx - 60, cy - 60, 120, border_color=NEON_PINK if symbol == "X" else NEON_GREEN)
    
    # Text
    font_main = utils.get_font("arial.ttf", 40)
    font_sub = utils.get_font("arial.ttf", 25)
    
    draw.text((cx, cy + 80), "WINNER", font=font_sub, fill=(200, 200, 200), anchor="mm")
    draw.text((cx, cy + 120), winner_name, font=font_main, fill="white", anchor="mm")
    
    prize = f"Won {amount} Coins!" if amount > 0 else "Victory!"
    draw.text((cx, cy + 160), prize, font=font_sub, fill=NEON_BLUE, anchor="mm")
    return canvas

# --- CORE GAME LOGIC & RULES ---

def stop_game(room_name):
    """
    Game ko safely band karta hai.
    Refund logic: Since hum paisa tabhi kat te hain jab koi haarta hai,
    toh stop hone par kisi ka paisa nahi katega (Automatic Refund).
    """
    with game_lock:
        if room_name in games:
            # Timer band karo
            if games[room_name].get('timer_obj'): 
                games[room_name]['timer_obj'].cancel()
            
            # Data saaf karo
            del games[room_name]
            return True
    return False

def timeout_handler(bot, room_name, type="inactivity"):
    """
    Strict Timer Logic:
    - Inactivity (90s): Game Cancel + Refund.
    - Turn (30s): Player loses turn -> Opponent Wins.
    """
    with game_lock:
        if room_name not in games: return
        game = games[room_name]
        
    if type == "inactivity":
        bot.send_message(room_name, "⚠️ **Game stopped due to inactivity.** All bets have been refunded.")
        stop_game(room_name)
        
    elif type == "turn":
        # Turn Missed Rule: Opponent Wins
        current = game['turn']
        winner_sym = "O" if current == "X" else "X"
        
        bot.send_message(room_name, f"⏳ @{game['names'][current]} ran out of time!")
        end_game(bot, room_name, winner_sym, "Time Out Victory")

def reset_timer(bot, room_name, duration, type="inactivity"):
    """Purana timer rok kar naya shuru karta hai."""
    with game_lock:
        if room_name not in games: return
        
        if games[room_name].get('timer_obj'): 
            games[room_name]['timer_obj'].cancel()
            
        t = threading.Timer(duration, timeout_handler, [bot, room_name, type])
        games[room_name]['timer_obj'] = t
        t.start()

def check_win(board):
    wins = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
    for a,b,c in wins:
        if board[a] == board[b] == board[c] and board[a] != " ": 
            return board[a]
    if " " not in board: 
        return "Draw"
    return None

def end_game(bot, room_name, winner_sym, reason):
    game = games[room_name]
    
    if winner_sym == "Draw":
        bot.send_message(room_name, "🤝 **It's a Draw!** No coins exchanged.")
    else:
        amt = game['bet']
        winner_uid = game['players'][winner_sym]
        winner_name = game['names'][winner_sym]
        loser_sym = "O" if winner_sym == "X" else "X"
        loser_uid = game['players'][loser_sym]
        loser_name = game['names'][loser_sym]
        
        # --- SCORE HANDLING ---
        if game['mode'] == "single":
            amt = 500 # Single player fixed reward
            db.add_game_result(winner_uid, winner_name, "tic_tac_toe", amt, is_win=True)
            
        elif game['mode'] == "multi" and amt > 0:
            # Winner takes pot
            db.add_game_result(winner_uid, winner_name, "tic_tac_toe", amt, is_win=True)
            # Loser pays pot
            db.add_game_result(loser_uid, loser_name, "tic_tac_toe", -amt, is_win=False)
            
        # --- WINNER CARD ---
        img = draw_winner_card(winner_name, game['avatars'].get(winner_sym, ""), winner_sym, amt)
        url = utils.upload_image(img)
        
        if url: 
            bot.send_image(room_name, url)
        
        bot.send_message(room_name, f"🏆 **{reason}**! {winner_name} Wins {amt}!")
        
    stop_game(room_name)

# --- COMMAND HANDLER ---

def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()
    user_id = str(data.get("user_id", user))
    
    # 1. Start/Stop Logic
    if cmd == "tic":
        if not args: return False
        
        # !tic 0 -> STOP
        if args[0] == "0":
            if stop_game(room_name): 
                bot.send_message(room_name, "🛑 Game stopped. All bets refunded.")
            else:
                bot.send_message(room_name, "⚠️ No active game.")
            return True
            
        # !tic 1 -> START
        if args[0] == "1":
            if room_name in games: 
                bot.send_message(room_name, "⚠️ Game already running here!")
                return True
                
            games[room_name] = {
                "status": "SELECT_MODE", 
                "creator": user_id, 
                "players": {"X": user_id, "O": None}, 
                "names": {"X": user, "O": None},
                "avatars": {"X": data.get("icon", ""), "O": ""},
                "board": [" "] * 9, 
                "turn": "X", 
                "mode": None, 
                "bet": 0, 
                "timer_obj": None
            }
            # Global 90s countdown for setup
            reset_timer(bot, room_name, 90, "inactivity")
            bot.send_message(room_name, "🎮 **Neon Tic Tac Toe**\nSelect Mode:\n`1` Single Player (vs Bot)\n`2` Multiplayer (PVP)")
            return True

    # 2. Game Inputs
    if room_name not in games: return False
    game = games[room_name]
    
    # Step 1: Select Mode
    if game['status'] == "SELECT_MODE" and user_id == game['creator']:
        if cmd == "1":
            game['mode'] = "single"
            game['players']['O'] = "BOT"
            game['names']['O'] = "Bot"
            game['status'] = "PLAYING"
            
            # Start Single Player
            send_game_state(bot, room_name, game, f"🤖 Single Player. @{user} (X) starts! (30s)")
            reset_timer(bot, room_name, 30, "turn")
            return True
            
        elif cmd == "2":
            game['mode'] = "multi"
            game['status'] = "SELECT_BET"
            bot.send_message(room_name, "💰 **Betting Mode**\nEnter Amount (e.g. `100`) or `0` for fun.")
            reset_timer(bot, room_name, 90, "inactivity")
            return True

    # Step 2: Select Bet
    if game['status'] == "SELECT_BET" and user_id == game['creator'] and cmd.isdigit():
        amt = int(cmd)
        bal = get_user_balance(user_id)
        
        if amt > bal:
            bot.send_message(room_name, f"❌ Insufficient Balance! You have {bal}.")
            return True
            
        game['bet'] = amt
        game['status'] = "WAITING"
        msg = f"{amt} coins" if amt > 0 else "Free Fun"
        bot.send_message(room_name, f"Waiting for opponent... Playing for **{msg}**.\nType `join` to play!")
        reset_timer(bot, room_name, 90, "inactivity")
        return True

    # Step 3: Join Game
    if game['status'] == "WAITING" and cmd == "join":
        if user_id == game['creator']: 
            bot.send_message(room_name, "❌ Cannot play against yourself.")
            return True
            
        # Balance Check for Joiner
        if game['bet'] > get_user_balance(user_id):
            bot.send_message(room_name, f"❌ You need {game['bet']} coins to join.")
            return True
            
        game['players']['O'] = user_id
        game['names']['O'] = user
        game['avatars']['O'] = data.get("icon", "")
        game['status'] = "PLAYING"
        
        send_game_state(bot, room_name, game, f"⚔️ Match On! @{game['names']['X']} vs @{user}")
        reset_timer(bot, room_name, 30, "turn")
        return True

    # Step 4: Gameplay (Moves)
    if game['status'] == "PLAYING" and cmd.isdigit():
        # Turn Validation
        current_turn_uid = game['players'][game['turn']]
        if user_id != current_turn_uid: 
            return False # Not your turn
            
        pos = int(cmd) - 1
        if 0 <= pos <= 8 and game['board'][pos] == " ":
            # Make Move
            game['board'][pos] = game['turn']
            
            # Check Win
            res = check_win(game['board'])
            if res:
                end_game(bot, room_name, res, "Game Over")
                return True
            
            # Swap Turn
            game['turn'] = "O" if game['turn'] == "X" else "X"
            
            # --- BOT MOVE LOGIC ---
            if game['mode'] == "single" and game['turn'] == "O":
                avail = [i for i, x in enumerate(game['board']) if x == " "]
                if avail:
                    # Smart-ish Bot: Random move for now
                    game['board'][random.choice(avail)] = "O"
                    
                    if check_win(game['board']):
                        end_game(bot, room_name, check_win(game['board']), "Bot Won")
                        return True
                    
                    game['turn'] = "X" # Back to player

            # Send Updated Board
            next_player = game['names'][game['turn']]
            send_game_state(bot, room_name, game, f"Turn: @{next_player} ({game['turn']}) - 30s")
            reset_timer(bot, room_name, 30, "turn")
            return True
        else:
            bot.send_message(room_name, "❌ Invalid move!")
            return True

    return False
