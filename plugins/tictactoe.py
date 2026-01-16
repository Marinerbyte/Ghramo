import time
import threading
import random
import gc
from PIL import Image, ImageDraw, ImageFont

# Local imports
import utils
import db

# --- 🎨 VISUAL CONFIGURATION ---
NEON_GREEN = (57, 255, 20)
NEON_PINK = (255, 16, 240)
NEON_BLUE = (44, 255, 255)
BG_COLOR = (17, 24, 39)
GRID_COLOR = (139, 92, 246)
BOARD_SIZE = 500

# ==========================================
# 🛠️ DATABASE WRAPPER
# ==========================================
def get_balance(user_id):
    try:
        conn = db.get_connection()
        cur = conn.cursor()
        ph = "%s" if db.DATABASE_URL.startswith("postgres") else "?"
        cur.execute(f"SELECT global_score FROM users WHERE user_id = {ph}", (str(user_id),))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else 0
    except: return 0

# ==========================================
# 📦 GAME INSTANCE
# ==========================================
class TicTacToeGame:
    def __init__(self, bot, room_name, creator_id, creator_name, icon):
        self.bot = bot
        self.room = room_name
        self.creator = creator_id
        self.lock = threading.Lock()
        
        self.players = {"X": creator_id, "O": None}
        self.names = {"X": creator_name, "O": None}
        self.avatars = {"X": icon, "O": ""} 
        
        self.board = [" "] * 9
        self.turn = "X"
        self.status = "MODE_SELECT" 
        self.mode = None
        self.bet = 0
        self.timer = None
        
        self.reset_timer(90, "inactivity")
        self.bot.send_message(self.room, "🎮 **Neon Tic Tac Toe**\nSelect Mode:\n`1` Single Player (vs Bot)\n`2` Multiplayer (PVP)")

    def timeout_handler(self, reason):
        with self.lock:
            if self.status == "ENDED": return
            if reason == "inactivity":
                self.bot.send_message(self.room, "⚠️ **Game Cancelled!** (Inactivity). Bets refunded.")
                self.cleanup()
            elif reason == "turn":
                winner_sym = "O" if self.turn == "X" else "X"
                self.end_game(winner_sym, "Time Out Victory")

    def reset_timer(self, seconds, reason):
        if self.timer: self.timer.cancel()
        self.timer = threading.Timer(seconds, self.timeout_handler, [reason])
        self.timer.daemon = True
        self.timer.start()

    # --- VISUALS ---
    def send_visuals(self, text_msg):
        snapshot = {
            'board': self.board[:],
            'turn': self.turn,
            'names': self.names.copy()
        }
        t = threading.Thread(target=self._bg_image_task, args=(snapshot, text_msg, False, None))
        t.daemon = True
        t.start()

    def _bg_image_task(self, snap, text, is_win, win_info):
        try:
            img = None
            if is_win:
                img = self.draw_winner_card(win_info)
            else:
                img = self.draw_board(snap)
            
            url = utils.upload_image(img)
            
            if url:
                self.bot.send_image(self.room, url)
                self.bot.send_message(self.room, text)
            else:
                if not is_win:
                    board_str = "\n".join([" | ".join(snap['board'][i:i+3]) for i in range(0, 9, 3)])
                    self.bot.send_message(self.room, f"{text}\n(Image Error)\n`{board_str}`")
                else:
                    self.bot.send_message(self.room, text)
        except Exception as e:
            print(f"[{self.room}] Visual Error: {e}")
        finally:
            if img: del img
            gc.collect()

    # --- GRAPHICS ---
    def draw_board(self, data):
        canvas = utils.create_canvas(BOARD_SIZE, BOARD_SIZE, color=BG_COLOR)
        draw = ImageDraw.Draw(canvas)
        w = 8
        draw.line([(166, 20), (166, 480)], fill=GRID_COLOR, width=w)
        draw.line([(332, 20), (332, 480)], fill=GRID_COLOR, width=w)
        draw.line([(20, 166), (480, 166)], fill=GRID_COLOR, width=w)
        draw.line([(20, 332), (480, 332)], fill=GRID_COLOR, width=w)
        
        f_lg = utils.get_font("arial.ttf", 100)
        f_sm = utils.get_font("arial.ttf", 40)
        def get_pos(i): return (((i-1)%3)*166+83, ((i-1)//3)*166+83)

        for i, mark in enumerate(data['board']):
            cx, cy = get_pos(i+1)
            if mark == "X": draw.text((cx, cy), "X", font=f_lg, fill=NEON_PINK, anchor="mm", stroke_width=2)
            elif mark == "O": draw.text((cx, cy), "O", font=f_lg, fill=NEON_GREEN, anchor="mm", stroke_width=2)
            else: draw.text((cx, cy), str(i+1), font=f_sm, fill=(60, 60, 70), anchor="mm")
        return canvas

    def draw_winner_card(self, info):
        canvas = utils.create_canvas(BOARD_SIZE, BOARD_SIZE, color=BG_COLOR)
        glow_color = (60, 0, 60) if info['sym'] == "X" else (0, 60, 0)
        utils.draw_gradient_bg(canvas, BG_COLOR, glow_color)
        draw = ImageDraw.Draw(canvas)
        cx, cy = BOARD_SIZE // 2, BOARD_SIZE // 2 - 50
        border_col = NEON_PINK if info['sym'] == "X" else NEON_GREEN
        utils.draw_circle_avatar(canvas, info['av'], cx-75, cy-75, 150, border_color=border_col, border_width=6)
        
        f_main = utils.get_font("arial.ttf", 45)
        f_sub = utils.get_font("arial.ttf", 25)
        draw.text((cx, cy + 100), "🏆 WINNER 🏆", font=f_sub, fill=(200, 200, 200), anchor="mm")
        draw.text((cx, cy + 145), info['name'], font=f_main, fill="white", anchor="mm")
        prize = f"💰 +{info['amt']} Coins" if info['amt'] > 0 else "👑 Victory!"
        draw.text((cx, cy + 190), prize, font=f_sub, fill=NEON_BLUE, anchor="mm")
        return canvas

    # --- LOGIC ---
    def process_input(self, cmd, user_id, user_name, icon):
        with self.lock:
            # 1. MODE SELECT
            if self.status == "MODE_SELECT" and user_id == self.creator:
                if cmd == "1":
                    self.mode = "single"; self.players['O'] = "BOT"; self.names['O'] = "Bot 🤖"
                    self.avatars['O'] = "https://robohash.org/talkinbot.png?set=set1"
                    self.status = "PLAYING"
                    self.send_visuals("🤖 Single Player Started!")
                    self.reset_timer(30, "turn")
                elif cmd == "2":
                    self.mode = "multi"; self.status = "BET_TYPE"
                    self.bot.send_message(self.room, "⚖️ **Multiplayer Options**\n`1` With Bet\n`2` Without Bet")
                    self.reset_timer(90, "inactivity")
                return True

            # 2. BET TYPE
            if self.status == "BET_TYPE" and user_id == self.creator:
                if cmd == "1":
                    self.status = "BET_AMT"
                    self.bot.send_message(self.room, "💰 Enter Bet Amount:")
                elif cmd == "2":
                    self.bet = 0; self.status = "WAITING"
                    self.bot.send_message(self.room, "⚔️ Fun Mode! Waiting for opponent... Type `join`.")
                self.reset_timer(90, "inactivity")
                return True

            # 3. BET AMT
            if self.status == "BET_AMT" and user_id == self.creator and cmd.isdigit():
                amt = int(cmd)
                if amt <= 0: return True
                bal = get_balance(user_id)
                if amt > bal:
                    self.bot.send_message(self.room, f"❌ Insufficient Balance! (You have {bal})")
                    return True
                self.bet = amt; self.status = "WAITING"
                self.bot.send_message(self.room, f"⚔️ Bet: {amt}. Waiting for opponent... Type `join`.")
                self.reset_timer(90, "inactivity")
                return True

            # 4. JOIN
            if self.status == "WAITING" and cmd == "join":
                # 🔥 Fix: Agar creator join kare to chup mat raho, batao use
                if user_id == self.creator:
                    self.bot.send_message(self.room, "❌ You cannot play against yourself!")
                    return True
                
                if self.bet > 0 and get_balance(user_id) < self.bet:
                    self.bot.send_message(self.room, "❌ Low Balance!")
                    return True
                
                self.players['O'] = user_id; self.names['O'] = user_name; self.avatars['O'] = icon 
                self.status = "PLAYING"
                
                self.send_visuals(f"⚔️ Match On! @{self.names['X']} vs @{user_name}")
                self.reset_timer(30, "turn")
                return True

            # 5. PLAY
            if self.status == "PLAYING" and cmd.isdigit():
                current_player_id = self.players[self.turn]
                if user_id != current_player_id: return False
                
                pos = int(cmd) - 1
                if 0 <= pos <= 8 and self.board[pos] == " ":
                    self.board[pos] = self.turn
                    
                    winner = self.check_win()
                    if winner:
                        self.end_game(winner, "Won")
                        return True
                    
                    self.turn = "O" if self.turn == "X" else "X"
                    
                    if self.mode == "single" and self.turn == "O":
                        avail = [i for i, x in enumerate(self.board) if x == " "]
                        if avail:
                            self.board[random.choice(avail)] = "O"
                            if self.check_win():
                                self.end_game(self.check_win(), "Bot Won")
                                return True
                            self.turn = "X"

                    self.send_visuals(f"Turn: @{self.names[self.turn]}")
                    self.reset_timer(30, "turn")
                    return True
                else:
                    self.bot.send_message(self.room, "❌ Invalid Move!")
                    return True

        return False

    def check_win(self):
        w = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
        for x,y,z in w:
            if self.board[x]==self.board[y]==self.board[z] and self.board[x]!=" ": return self.board[x]
        if " " not in self.board: return "Draw"
        return None

    def end_game(self, winner_sym, reason):
        if winner_sym == "Draw":
            self.bot.send_message(self.room, "🤝 **It's a Draw!** No coins exchanged.")
        else:
            w_uid = self.players[winner_sym]
            l_sym = "O" if winner_sym == "X" else "X"
            l_uid = self.players[l_sym]
            amt = self.bet
            
            if self.mode == "single":
                amt = 500
                db.add_game_result(w_uid, self.names[winner_sym], "tic_tac_toe", amt, is_win=True)
            elif self.mode == "multi" and amt > 0:
                db.add_game_result(w_uid, self.names[winner_sym], "tic_tac_toe", amt, is_win=True)
                db.add_game_result(l_uid, self.names[l_sym], "tic_tac_toe", -amt, is_win=False)
            
            info = {
                'name': self.names[winner_sym], 
                'av': self.avatars.get(winner_sym, ""), 
                'sym': winner_sym, 
                'amt': amt
            }
            
            t = threading.Thread(target=self._bg_image_task, args=(None, f"🏆 **{reason}**! {self.names[winner_sym]} Wins!", True, info))
            t.daemon = True
            t.start()

        self.cleanup()

    def cleanup(self):
        self.status = "ENDED"
        if self.timer: self.timer.cancel()
        if self.room in active_games: del active_games[self.room]
        gc.collect()

# ==========================================
# 🌍 GLOBAL REGISTRY
# ==========================================
active_games = {}

def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()
    uid = str(data.get("user_id", user))
    
    # 🔥 Fix: Check all possible keys for Avatar
    icon = data.get("avatar_url", data.get("icon", data.get("avatar", "")))

    if cmd == "tic":
        if not args: return False
        
        if args[0] == "0":
            if room_name in active_games:
                active_games[room_name].cleanup()
                bot.send_message(room_name, "🛑 Game stopped manually.")
            else:
                bot.send_message(room_name, "⚠️ No active game.")
            return True

        if args[0] == "1":
            if room_name in active_games:
                bot.send_message(room_name, "⚠️ Game already running!")
                return True
            
            new_game = TicTacToeGame(bot, room_name, uid, user, icon)
            active_games[room_name] = new_game
            return True

    if room_name in active_games:
        # Debug Log: Agar join fail hua to console me dikhega
        if cmd == "join":
            bot.log(f"📝 Join Attempt in {room_name} by {user} (ID: {uid})")
            
        return active_games[room_name].process_input(cmd, uid, user, icon)

    return False
