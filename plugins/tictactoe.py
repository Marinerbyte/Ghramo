import time
import threading
import random
import io
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# Local imports based on your structure
import utils
import db

# --- CONFIGURATION ---
NEON_GREEN = (57, 255, 20)
NEON_PINK = (255, 16, 240)
NEON_BLUE = (44, 255, 255)
BG_COLOR = (17, 24, 39) # Dark background
GRID_COLOR = (139, 92, 246) # Purple glow
BOARD_SIZE = 500

# --- STATE MANAGEMENT ---
# Structure: { room_name: { status, board, players, bet, turn, timers, ... } }
games = {}
game_lock = threading.Lock()

def setup(bot):
    bot.log("🎮 Tic Tac Toe (Neon Edition) Loaded")

# --- DATABASE HELPERS (READ ONLY) ---
def get_user_balance(user_id):
    """Safely checks user balance without writing to DB."""
    try:
        conn = db.get_connection()
        cur = conn.cursor()
        # Handle Postgres vs SQLite placeholders
        ph = "%s" if db.DATABASE_URL.startswith("postgres") else "?"
        cur.execute(f"SELECT global_score FROM users WHERE user_id = {ph}", (str(user_id),))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else 0
    except:
        return 0

# --- IMAGE GENERATION ENGINE ---

def draw_neon_board(game_data):
    """Generates the glowing game board."""
    # Create Base
    canvas = utils.create_canvas(BOARD_SIZE, BOARD_SIZE, color=BG_COLOR)
    draw = ImageDraw.Draw(canvas)
    
    # Draw Grid (Neon Style)
    width = 8
    # Vertical
    draw.line([(166, 20), (166, 480)], fill=GRID_COLOR, width=width)
    draw.line([(332, 20), (332, 480)], fill=GRID_COLOR, width=width)
    # Horizontal
    draw.line([(20, 166), (480, 166)], fill=GRID_COLOR, width=width)
    draw.line([(20, 332), (480, 332)], fill=GRID_COLOR, width=width)

    # Helper function to get coordinates for box ID (1-9)
    def get_center(idx):
        row = (idx - 1) // 3
        col = (idx - 1) % 3
        return (col * 166 + 83, row * 166 + 83)

    # Draw Marks (X and O)
    font_lg = utils.get_font("arial.ttf", 100)
    font_sm = utils.get_font("arial.ttf", 40)
    
    for i, mark in enumerate(game_data['board']):
        cx, cy = get_center(i + 1)
        
        if mark == "X":
            # Neon X
            draw.text((cx, cy), "X", font=font_lg, fill=NEON_PINK, anchor="mm", stroke_width=2, stroke_fill=(255, 200, 255))
        elif mark == "O":
            # Neon O
            draw.text((cx, cy), "O", font=font_lg, fill=NEON_GREEN, anchor="mm", stroke_width=2, stroke_fill=(200, 255, 200))
        else:
            # Ghost Numbers (1-9) for guidance
            draw.text((cx, cy), str(i+1), font=font_sm, fill=(60, 60, 70), anchor="mm")

    return canvas

def draw_winner_card(winner_name, winner_avatar_url, symbol, amount):
    """Generates a celebratory winner card."""
    canvas = utils.create_canvas(BOARD_SIZE, BOARD_SIZE, color=BG_COLOR)
    
    # Background Glow
    utils.draw_gradient_bg(canvas, BG_COLOR, (30, 0, 30) if symbol == "X" else (0, 30, 0))
    
    draw = ImageDraw.Draw(canvas)
    
    # Draw Avatar
    cx, cy = BOARD_SIZE // 2, BOARD_SIZE // 2 - 50
    utils.draw_circle_avatar(canvas, winner_avatar_url, cx - 60, cy - 60, 120, border_color=NEON_PINK if symbol == "X" else NEON_GREEN)

    # Text Info
    font_main = utils.get_font("arial.ttf", 40)
    font_sub = utils.get_font("arial.ttf", 25)

    draw.text((cx, cy + 80), "WINNER", font=font_sub, fill=(200, 200, 200), anchor="mm")
    draw.text((cx, cy + 120), winner_name, font=font_main, fill="white", anchor="mm")
    
    prize_text = f"Won {amount} Coins!" if amount > 0 else "Victory!"
    draw.text((cx, cy + 160), prize_text, font=font_sub, fill=NEON_BLUE, anchor="mm")

    return canvas

# --- GAME LOGIC ---

def stop_game(room_name, reason="Game Stopped."):
    """Cleans up game, cancels timers, refunds if needed."""
    with game_lock:
        if room_name in games:
            game = games[room_name]
            
            # Cancel Timers
            if game.get('timer_obj'):
                game['timer_obj'].cancel()
            
            # Refund Logic (Only checks, doesn't actually refund because we only deduct on loss)
            # Since we implement "Winner takes all, Loser pays at end", 
            # simply stopping means no database transaction occurs. Safe.
            
            del games[room_name]
            return True
    return False

def timeout_handler(bot, room_name, type="inactivity"):
    """Handles auto-stop events."""
    with game_lock:
        if room_name not in games: return
        game = games[room_name]
        
    if type == "inactivity":
        bot.send_message(room_name, "⚠️ **Game stopped due to inactivity.** All bets have been refunded.")
        stop_game(room_name)
    
    elif type == "turn":
        # Turn timeout - Auto forfeit
        current_turn = game['turn']
        # Swap turn to find winner
        winner_sym = "O" if current_turn == "X" else "X"
        winner_uid = game['players'][winner_sym]
        loser_uid = game['players'][current_turn]
        
        bot.send_message(room_name, f"⏳ @{game['names'][current_turn]} ran out of time!")
        end_game(bot, room_name, winner_sym, "Time Out")

def reset_timer(bot, room_name, duration=90, type="inactivity"):
    """Resets the game timer."""
    with game_lock:
        if room_name not in games: return
        
        # Cancel old timer
        if games[room_name].get('timer_obj'):
            games[room_name]['timer_obj'].cancel()
        
        # Start new timer
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
    
    # 1. Image Generation
    if winner_sym == "Draw":
        bot.send_message(room_name, "🤝 **It's a Draw!** No coins lost.")
    else:
        winner_uid = game['players'][winner_sym]
        loser_sym = "O" if winner_sym == "X" else "X"
        loser_uid = game['players'][loser_sym]
        winner_name = game['names'][winner_sym]
        
        # 2. Score Handling
        amt = game['bet']
        if game['mode'] == "single":
            amt = 500 # Fixed prize for single player
            db.add_game_result(winner_uid, winner_name, "tic_tac_toe", amt, is_win=True)
        elif game['mode'] == "multi":
            if amt > 0:
                # Winner gets +amt
                db.add_game_result(winner_uid, winner_name, "tic_tac_toe", amt, is_win=True)
                # Loser gets -amt
                db.add_game_result(loser_uid, game['names'][loser_sym], "tic_tac_toe", -amt, is_win=False)
        
        # 3. Send Visuals
        # Get Avatar (Passed in data or default)
        av_url = game.get('avatars', {}).get(winner_sym, "")
        
        img = draw_winner_card(winner_name, av_url, winner_sym, amt)
        url = utils.upload_image(img)
        
        bot.send_message(room_name, f"🏆 **{reason}**")
        if url:
            bot.send_image(room_name, url)
        else:
            bot.send_message(room_name, f"🎉 {winner_name} Wins {amt} Coins!")

    stop_game(room_name)

# --- COMMAND HANDLER ---

def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()
    user_id = str(data.get("user_id", user))
    
    # 1. MASTER COMMANDS
    if cmd == "tic":
        if not args: return False
        action = args[0]
        
        # STOP
        if action == "0":
            if stop_game(room_name):
                bot.send_message(room_name, "🛑 Game stopped. Bets refunded.")
            else:
                bot.send_message(room_name, "⚠️ No active game to stop.")
            return True
            
        # START
        if action == "1":
            if room_name in games:
                bot.send_message(room_name, "⚠️ A game is already active here!")
                return True
                
            # Init Game
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
            reset_timer(bot, room_name, 90, "inactivity") # Global 90s timeout
            
            bot.send_message(room_name, "🎮 **Tic Tac Toe Started!**\nSelect Mode:\n`1` Single Player (vs Bot)\n`2` Multiplayer (vs Human)")
            return True

    # 2. GAME FLOW HANDLERS
    if room_name not in games:
        return False

    game = games[room_name]
    status = game['status']
    
    # --- MODE SELECTION ---
    if status == "SELECT_MODE" and user_id == game['creator']:
        if cmd == "1":
            game['mode'] = "single"
            game['players']['O'] = "BOT"
            game['names']['O'] = "Robot 🤖"
            game['status'] = "PLAYING"
            game['bet'] = 0
            
            # Start Game
            img = draw_neon_board(game)
            url = utils.upload_image(img)
            bot.send_image(room_name, url)
            bot.send_message(room_name, f"🤖 Single Player Mode.\n@{user} (X) vs Bot (O)\nType `1-9` to move.")
            reset_timer(bot, room_name, 30, "turn")
            return True
            
        elif cmd == "2":
            game['mode'] = "multi"
            game['status'] = "SELECT_BET"
            bot.send_message(room_name, "💰 **Multiplayer Mode**\nEnter bet amount (e.g. `100`) or type `0` for fun mode.")
            reset_timer(bot, room_name, 90, "inactivity")
            return True

    # --- BET SELECTION ---
    if status == "SELECT_BET" and user_id == game['creator']:
        if cmd.isdigit():
            amount = int(cmd)
            # Validate Balance
            bal = get_user_balance(user_id)
            if amount > bal:
                bot.send_message(room_name, f"❌ Insufficient funds! You have {bal} coins.")
                return True
            
            game['bet'] = amount
            game['status'] = "WAITING_JOIN"
            
            msg = "free fun" if amount == 0 else f"{amount} coins"
            bot.send_message(room_name, f"Waiting for opponent... playing for **{msg}**.\nType `join` to accept challenge!")
            reset_timer(bot, room_name, 90, "inactivity")
            return True

    # --- JOINING ---
    if status == "WAITING_JOIN" and cmd == "join":
        if user_id == game['creator']:
            bot.send_message(room_name, "❌ You cannot play against yourself.")
            return True
            
        # Check Balance for joiner
        bet = game['bet']
        if bet > 0:
            bal = get_user_balance(user_id)
            if bal < bet:
                bot.send_message(room_name, f"❌ You need {bet} coins to join! (Balance: {bal})")
                return True
        
        # Add Player
        game['players']['O'] = user_id
        game['names']['O'] = user
        game['avatars']['O'] = data.get("icon", "")
        game['status'] = "PLAYING"
        
        # Start
        img = draw_neon_board(game)
        url = utils.upload_image(img)
        bot.send_image(room_name, url)
        bot.send_message(room_name, f"⚔️ Match On! @{game['names']['X']} vs @{user}\nTurn: @{game['names']['X']} (X) - 30s")
        reset_timer(bot, room_name, 30, "turn")
        return True

    # --- GAMEPLAY (MOVES) ---
    if status == "PLAYING" and cmd.isdigit() and len(cmd) == 1:
        # Check if it's correct player's turn
        current_turn_sym = game['turn']
        current_player_id = game['players'][current_turn_sym]
        
        if user_id != current_player_id:
            return False # Ignore other people talking
            
        pos = int(cmd) - 1
        if 0 <= pos <= 8 and game['board'][pos] == " ":
            # VALID MOVE
            game['board'][pos] = current_turn_sym
            
            # Check Result
            res = check_win(game['board'])
            if res:
                end_game(bot, room_name, res, "Game Over")
                return True
            
            # Swap Turn
            next_sym = "O" if current_turn_sym == "X" else "X"
            game['turn'] = next_sym
            
            # If Single Player -> BOT MOVE
            if game['mode'] == "single" and next_sym == "O":
                avail = [i for i, x in enumerate(game['board']) if x == " "]
                if avail:
                    bot_move = random.choice(avail)
                    game['board'][bot_move] = "O"
                    
                    res_bot = check_win(game['board'])
                    if res_bot:
                        end_game(bot, room_name, res_bot, "Game Over")
                        return True
                    
                    # Back to Player
                    game['turn'] = "X"
            
            # Update Board Image
            img = draw_neon_board(game)
            url = utils.upload_image(img)
            
            next_name = game['names'][game['turn']]
            bot.send_image(room_name, url)
            bot.send_message(room_name, f"Turn: @{next_name} ({game['turn']}) - 30s")
            
            # Reset Turn Timer
            reset_timer(bot, room_name, 30, "turn")
            return True
        else:
            bot.send_message(room_name, "❌ Invalid move.")
            return True

    return False
