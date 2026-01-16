import time
import threading
import random
import gc
from PIL import Image, ImageDraw, ImageFont

# Local imports
import utils
import db

# --- CONFIGURATION (Neon Theme) ---
NEON_GREEN = (57, 255, 20)
NEON_PINK = (255, 16, 240)
NEON_BLUE = (44, 255, 255)
BG_COLOR = (17, 24, 39)
GRID_COLOR = (139, 92, 246)
BOARD_SIZE = 500

# --- GLOBAL STATE & LOCKS ---
games = {}

# 🔒 BIG LOCK: Ye race conditions ko rokega. 
# Jab ek room ka logic chal raha ho, dusra wait karega.
big_lock = threading.Lock()

def setup(bot):
    bot.log("🎮 Tic Tac Toe (Thread-Safe & Optimized) Loaded")

# --- DATABASE HELPERS ---
def get_user_balance(user_id):
    try:
        conn = db.get_connection()
        cur = conn.cursor()
        ph = "%s" if db.DATABASE_URL.startswith("postgres") else "?"
        cur.execute(f"SELECT global_score FROM users WHERE user_id = {ph}", (str(user_id),))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else 0
    except: return 0

# --- BACKGROUND TASK: IMAGE SENDER ---
def _async_image_task(bot, room_name, game_snapshot, text_msg, is_win_card=False, winner_info=None):
    """
    Ye function alag thread mein chalta hai.
    Ye main bot ko slow hone se bachata hai.
    """
    img = None
    url = None
    try:
        # 1. Image Draw Karo
        if is_win_card and winner_info:
            img = draw_winner_card(winner_info['name'], winner_info['avatar'], winner_info['sym'], winner_info['amt'])
        else:
            img = draw_neon_board(game_snapshot)
        
        # 2. Upload Karo (Thread Safe Utils use karega)
        url = utils.upload_image(img)
        
        # 3. Message Bhejo
        if url:
            bot.send_image(room_name, url)
            bot.send_message(room_name, text_msg)
        else:
            # Fallback agar upload fail ho
            if not is_win_card:
                board_display = "\n".join([" | ".join(game_snapshot['board'][i:i+3]) for i in range(0, 9, 3)])
                bot.send_message(room_name, f"{text_msg}\n(Img Failed)\n`{board_display}`")
            else:
                bot.send_message(room_name, text_msg)

    except Exception as e:
        print(f"Async Error: {e}")
    finally:
        # 🧹 KACHRA SAAF (Memory Cleanup)
        if img: 
            del img
        gc.collect()

def send_game_update(bot, room_name, game, text_msg):
    """Thread launcher for board updates"""
    # Deep copy nahi, bas visual data copy karo taaki race condition na ho
    snapshot = {
        'board': game['board'][:], # List copy
        'turn': game['turn'],
        'names': game['names'].copy()
    }
    threading.Thread(target=_async_image_task, args=(bot, room_name, snapshot, text_msg)).start()

def send_win_card(bot, room_name, winner_name, avatar, symbol, amt, reason):
    """Thread launcher for winner card"""
    info = {'name': winner_name, 'avatar': avatar, 'sym': symbol, 'amt': amt}
    text = f"🏆 **{reason}**! {winner_name} Wins {amt}!"
    threading.Thread(target=_async_image_task, args=(bot, room_name, None, text, True, info)).start()

# --- GRAPHICS ENGINE (Optimized) ---
def draw_neon_board(game_data):
    canvas = utils.create_canvas(BOARD_SIZE, BOARD_SIZE, color=BG_COLOR)
    draw = ImageDraw.Draw(canvas)
    
    width = 8
    # Grid
    draw.line([(166, 20), (166, 480)], fill=GRID_COLOR, width=width)
    draw.line([(332, 20), (332, 480)], fill=GRID_COLOR, width=width)
    draw.line([(20, 166), (480, 166)], fill=GRID_COLOR, width=width)
    draw.line([(20, 332), (480, 332)], fill=GRID_COLOR, width=width)

    font_lg = utils.get_font("arial.ttf", 100)
    font_sm = utils.get_font("arial.ttf", 40)
    
    def get_center(idx): return (((idx - 1) % 3) * 166 + 83, ((idx - 1) // 3) * 166 + 83)

    for i, mark in enumerate(game_data['board']):
        cx, cy = get_center(i + 1)
        if mark == "X":
            draw.text((cx, cy), "X", font=font_lg, fill=NEON_PINK, anchor="mm", stroke_width=2)
        elif mark == "O":
            draw.text((cx, cy), "O", font=font_lg, fill=NEON_GREEN, anchor="mm", stroke_width=2)
        else:
            draw.text((cx, cy), str(i+1), font=font_sm, fill=(60, 60, 70), anchor="mm")
    return canvas

def draw_winner_card(name, avatar_url, symbol, amount):
    canvas = utils.create_canvas(BOARD_SIZE, BOARD_SIZE, color=BG_COLOR)
    glow = (60, 0, 60) if symbol == "X" else (0, 60, 0)
    utils.draw_gradient_bg(canvas, BG_COLOR, glow)
    
    draw = ImageDraw.Draw(canvas)
    cx, cy = BOARD_SIZE // 2, BOARD_SIZE // 2 - 50
    
    border = NEON_PINK if symbol == "X" else NEON_GREEN
    utils.draw_circle_avatar(canvas, avatar_url, cx - 75, cy - 75, 150, border_color=border, border_width=6)

    font_main = utils.get_font("arial.ttf", 45)
    font_sub = utils.get_font("arial.ttf", 25)
    
    draw.text((cx, cy + 100), "🏆 WINNER 🏆", font=font_sub, fill=(200, 200, 200), anchor="mm")
    draw.text((cx, cy + 145), name, font=font_main, fill="white", anchor="mm")
    prize = f"💰 +{amount} Coins" if amount > 0 else "👑 Victory!"
    draw.text((cx, cy + 190), prize, font=font_sub, fill=NEON_BLUE, anchor="mm")
    return canvas

# --- CORE LOGIC & RULES ---

def cleanup_room(room_name):
    """Safely removes game data and cancels timers."""
    if room_name in games:
        g = games[room_name]
        if g.get('timer'): g['timer'].cancel()
        del games[room_name]
        gc.collect() # Force cleanup

def timeout_logic(bot, room_name, reason):
    """Handles 90s Inactivity & 30s Turn Timeout."""
    # 🔒 LOCK ACQUIRED: Timer bhi lock ke andar chalega
    with big_lock:
        if room_name not in games: return
        
        game = games[room_name]
        
        if reason == "inactivity":
            bot.send_message(room_name, "⚠️ **Game stopped due to inactivity.** All bets refunded.")
            cleanup_room(room_name)
            
        elif reason == "turn":
            # 30s Turn Missed -> Opponent Wins
            curr = game['turn']
            winner_sym = "O" if curr == "X" else "X"
            end_game_logic(bot, room_name, winner_sym, "Time Out Victory")

def start_timer(bot, room_name, seconds, reason):
    """Starts a new timer thread."""
    if room_name in games:
        if games[room_name].get('timer'): 
            games[room_name]['timer'].cancel()
            
        t = threading.Timer(seconds, timeout_logic, [bot, room_name, reason])
        t.daemon = True
        games[room_name]['timer'] = t
        t.start()

def check_win(board):
    wins = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
    for a,b,c in wins:
        if board[a] == board[b] == board[c] and board[a] != " ": return board[a]
    if " " not in board: return "Draw"
    return None

def end_game_logic(bot, room_name, winner_sym, reason):
    """Finalizes game, updates DB, sends card."""
    game = games[room_name]
    
    if winner_sym == "Draw":
        bot.send_message(room_name, "🤝 **It's a Draw!** No coins exchanged.")
    else:
        amt = game['bet']
        winner_uid = game['players'][winner_sym]
        loser_sym = "O" if winner_sym == "X" else "X"
        loser_uid = game['players'][loser_sym]
        
        # --- SCORE UPDATE ---
        if game['mode'] == "single":
            amt = 500 # Fixed reward for beating bot
            db.add_game_result(winner_uid, game['names'][winner_sym], "tic_tac_toe", amt, is_win=True)
            
        elif game['mode'] == "multi" and amt > 0:
            # Winner gets +Amount
            db.add_game_result(winner_uid, game['names'][winner_sym], "tic_tac_toe", amt, is_win=True)
            # Loser gets -Amount
            db.add_game_result(loser_uid, game['names'][loser_sym], "tic_tac_toe", -amt, is_win=False)
            
        # Send Card
        av = game['avatars'].get(winner_sym, "")
        send_win_card(bot, room_name, game['names'][winner_sym], av, winner_sym, amt, reason)
        
    cleanup_room(room_name)

# --- COMMAND HANDLER (Thread Safe Entry Point) ---

def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()
    uid = str(data.get("user_id", user))
    # Icon/Avatar fetch safe way
    u_icon = data.get("icon", data.get("avatar", ""))

    # 🔒 GLOBAL LOCK: Har command execute hone se pehle lock check karega
    with big_lock:
        
        # --- MASTER COMMAND: !tic ---
        if cmd == "tic":
            if not args: return False
            
            # STOP
            if args[0] == "0":
                if room_name in games:
                    cleanup_room(room_name)
                    bot.send_message(room_name, "🛑 Game stopped. Bets refunded.")
                else:
                    bot.send_message(room_name, "⚠️ No active game.")
                return True

            # START
            if args[0] == "1":
                if room_name in games:
                    bot.send_message(room_name, "⚠️ Game already running here!")
                    return True
                
                # Init Game State
                games[room_name] = {
                    "status": "SELECT_MODE",
                    "creator": uid,
                    "players": {"X": uid, "O": None},
                    "names": {"X": user, "O": None},
                    "avatars": {"X": u_icon, "O": ""},
                    "board": [" "] * 9,
                    "turn": "X",
                    "mode": None,
                    "bet": 0,
                    "timer": None
                }
                start_timer(bot, room_name, 90, "inactivity")
                bot.send_message(room_name, "🎮 **Tic Tac Toe**\nSelect Mode:\n`1` Single Player\n`2` Multiplayer")
                return True

        # --- GAME FLOW ---
        if room_name not in games: return False
        game = games[room_name]
        
        # 1. SELECT MODE
        if game['status'] == "SELECT_MODE" and uid == game['creator']:
            if cmd == "1":
                # Single Player Setup
                game['mode'] = "single"
                game['players']['O'] = "BOT"
                game['names']['O'] = "Bot 🤖"
                game['avatars']['O'] = "https://robohash.org/talkinbot.png?set=set1"
                game['status'] = "PLAYING"
                
                send_game_update(bot, room_name, game, "🤖 Single Player Started! (Win=500)")
                start_timer(bot, room_name, 30, "turn")
                return True
                
            elif cmd == "2":
                # Multiplayer Setup
                game['mode'] = "multi"
                game['status'] = "SELECT_BET"
                bot.send_message(room_name, "💰 **Multiplayer**\nEnter Bet Amount (e.g. `100`) or `0` for fun.")
                start_timer(bot, room_name, 90, "inactivity")
                return True

        # 2. SELECT BET
        if game['status'] == "SELECT_BET" and uid == game['creator'] and cmd.isdigit():
            amt = int(cmd)
            # Check Balance
            bal = get_user_balance(uid)
            if amt > bal:
                bot.send_message(room_name, f"❌ Insufficient Balance! You have {bal}.")
                return True
            
            game['bet'] = amt
            game['status'] = "WAITING"
            msg = f"**{amt} Coins**" if amt > 0 else "**Free Fun**"
            bot.send_message(room_name, f"Waiting for opponent... Playing for {msg}.\nType `join` to play.")
            start_timer(bot, room_name, 90, "inactivity")
            return True

        # 3. JOIN GAME
        if game['status'] == "WAITING" and cmd == "join":
            if uid == game['creator']:
                bot.send_message(room_name, "❌ Cannot play vs yourself.")
                return True
            
            # Check Balance
            if game['bet'] > 0:
                bal = get_user_balance(uid)
                if bal < game['bet']:
                    bot.send_message(room_name, f"❌ Low Balance! You need {game['bet']}.")
                    return True
            
            # Setup Player O
            game['players']['O'] = uid
            game['names']['O'] = user
            game['avatars']['O'] = u_icon
            game['status'] = "PLAYING"
            
            send_game_update(bot, room_name, game, f"⚔️ Match On! @{game['names']['X']} vs @{user}")
            start_timer(bot, room_name, 30, "turn")
            return True

        # 4. GAMEPLAY
        if game['status'] == "PLAYING" and cmd.isdigit():
            # Validate Turn
            current_uid = game['players'][game['turn']]
            if uid != current_uid: return False 
            
            pos = int(cmd) - 1
            if 0 <= pos <= 8 and game['board'][pos] == " ":
                # Apply Move
                game['board'][pos] = game['turn']
                
                # Check Win
                res = check_win(game['board'])
                if res:
                    end_game_logic(bot, room_name, res, "Game Over")
                    return True
                
                # Swap Turn
                game['turn'] = "O" if game['turn'] == "X" else "X"
                
                # --- BOT LOGIC (Inside Lock) ---
                if game['mode'] == "single" and game['turn'] == "O":
                    avail = [i for i, x in enumerate(game['board']) if x == " "]
                    if avail:
                        game['board'][random.choice(avail)] = "O"
                        if check_win(game['board']):
                            end_game_logic(bot, room_name, check_win(game['board']), "Bot Won")
                            return True
                        game['turn'] = "X"
                
                # Update Board Visual
                next_p = game['names'][game['turn']]
                send_game_update(bot, room_name, game, f"Turn: @{next_p} ({game['turn']})")
                start_timer(bot, room_name, 30, "turn")
                return True
            else:
                bot.send_message(room_name, "❌ Invalid Move!")
                return True

    return False
