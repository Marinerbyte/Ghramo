import time
import threading
import random
import gc
import queue  # <--- Queue System
from PIL import Image, ImageDraw, ImageFont

# Local imports
import utils
import db

# --- CONFIGURATION ---
NEON_GREEN = (57, 255, 20)
NEON_PINK = (255, 16, 240)
NEON_BLUE = (44, 255, 255)
BG_COLOR = (17, 24, 39)
GRID_COLOR = (139, 92, 246)
BOARD_SIZE = 500

# ==========================================
# 🚂 THE UPLOAD QUEUE (Single Line System)
# ==========================================
# Har game apni image yahan dalega.
# Worker ek-ek karke upload karega taaki fail na ho.
upload_queue = queue.Queue()

def upload_worker_loop(bot):
    """
    Ye function hamesha chalta rahega.
    Ye queue se data nikal kar shanti se upload karega.
    """
    bot.log("✅ Upload Queue Worker Started")
    
    while True:
        try:
            # 1. Queue se task nikalo (Wait karega agar khali hai)
            task = upload_queue.get()
            
            room_name = task['room']
            image_obj = task['image']
            text_msg = task['text']
            is_fallback_needed = task['fallback']
            game_obj = task['game_ref'] # Reference to calculate fallback text
            
            # 2. Upload Karo (Ab ye kabhi collide nahi karega)
            url = utils.upload_image(image_obj)
            
            # 3. Bhejo
            if url:
                bot.send_image(room_name, url)
                bot.send_message(room_name, text_msg)
            else:
                # Agar phir bhi fail hua, to Text Board bhejo
                if is_fallback_needed and game_obj:
                    # Fallback Text Generate
                    b_str = "\n".join([" | ".join(game_obj.board[i:i+3]) for i in range(0, 9, 3)])
                    bot.send_message(room_name, f"{text_msg}\n(Img Failed)\n`{b_str}`")
                else:
                    bot.send_message(room_name, text_msg)
            
            # Cleanup
            del image_obj
            gc.collect()
            
            # Batana ki kaam ho gaya
            upload_queue.task_done()
            
        except Exception as e:
            print(f"Queue Error: {e}")

# ==========================================
# MAIN SETUP
# ==========================================

def setup(bot):
    bot.log("🎮 Tic Tac Toe (Queue System) Loaded")
    
    # Worker Thread Start Karo (Sirf Ek Baar)
    t = threading.Thread(target=upload_worker_loop, args=(bot,), daemon=True)
    t.start()

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
# 📦 GAME CLASS (Object)
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
        self.bot.send_message(self.room, "🎮 **Tic Tac Toe**\n`1` Single Player\n`2` Multiplayer")

    def timeout_task(self, reason):
        with self.lock:
            if self.status == "ENDED": return
            if reason == "inactivity":
                self.bot.send_message(self.room, "⚠️ **Stopped (Inactivity).** Refunded.")
                self.cleanup()
            elif reason == "turn":
                winner = "O" if self.turn == "X" else "X"
                self.end_game(winner, "Time Out Victory")

    def reset_timer(self, seconds, reason):
        if self.timer: self.timer.cancel()
        self.timer = threading.Timer(seconds, self.timeout_task, [reason])
        self.timer.daemon = True
        self.timer.start()

    # --- SEND TO QUEUE (Ye turant return karega) ---
    def send_visuals(self, text_msg):
        # 1. Image Generate Karo (Ye fast hai)
        # Hamein board ka copy chahiye taaki logic aage badh sake
        board_copy = self.board[:] 
        
        # Is function ko thread me daal sakte hain agar image generation slow ho
        # Par abhi ke liye direct call theek hai
        img = self.draw_board(board_copy, self.turn)
        
        # 2. Queue me daal do (Manager sambhal lega)
        task = {
            'room': self.room,
            'image': img,
            'text': text_msg,
            'fallback': True,
            'game_ref': self
        }
        upload_queue.put(task)

    def send_win_card(self, text_msg, win_info):
        img = self.draw_winner(win_info)
        task = {
            'room': self.room,
            'image': img,
            'text': text_msg,
            'fallback': False,
            'game_ref': None
        }
        upload_queue.put(task)

    # --- GRAPHICS ---
    def draw_board(self, board_data, current_turn):
        canvas = utils.create_canvas(BOARD_SIZE, BOARD_SIZE, color=BG_COLOR)
        draw = ImageDraw.Draw(canvas)
        w = 8
        draw.line([(166, 20), (166, 480)], fill=GRID_COLOR, width=w)
        draw.line([(332, 20), (332, 480)], fill=GRID_COLOR, width=w)
        draw.line([(20, 166), (480, 166)], fill=GRID_COLOR, width=w)
        draw.line([(20, 332), (480, 332)], fill=GRID_COLOR, width=w)
        
        f_lg = utils.get_font("arial.ttf", 100)
        f_sm = utils.get_font("arial.ttf", 40)
        def gc(i): return (((i-1)%3)*166+83, ((i-1)//3)*166+83)

        for i, m in enumerate(board_data):
            cx, cy = gc(i+1)
            if m == "X": draw.text((cx, cy), "X", font=f_lg, fill=NEON_PINK, anchor="mm", stroke_width=2)
            elif m == "O": draw.text((cx, cy), "O", font=f_lg, fill=NEON_GREEN, anchor="mm", stroke_width=2)
            else: draw.text((cx, cy), str(i+1), font=f_sm, fill=(60, 60, 70), anchor="mm")
        return canvas

    def draw_winner(self, info):
        canvas = utils.create_canvas(BOARD_SIZE, BOARD_SIZE, color=BG_COLOR)
        glow = (60, 0, 60) if info['sym'] == "X" else (0, 60, 0)
        utils.draw_gradient_bg(canvas, BG_COLOR, glow)
        draw = ImageDraw.Draw(canvas)
        cx, cy = BOARD_SIZE//2, BOARD_SIZE//2 - 50
        border = NEON_PINK if info['sym'] == "X" else NEON_GREEN
        utils.draw_circle_avatar(canvas, info['av'], cx-75, cy-75, 150, border_color=border, border_width=6)
        
        f_m = utils.get_font("arial.ttf", 45)
        f_s = utils.get_font("arial.ttf", 25)
        draw.text((cx, cy+100), "🏆 WINNER 🏆", font=f_s, fill=(200,200,200), anchor="mm")
        draw.text((cx, cy+145), info['name'], font=f_m, fill="white", anchor="mm")
        prize = f"💰 +{info['amt']} Coins" if info['amt'] > 0 else "👑 Victory!"
        draw.text((cx, cy+190), prize, font=f_s, fill=NEON_BLUE, anchor="mm")
        return canvas

    # --- LOGIC ---
    def process_input(self, cmd, user_id, user_name, icon):
        with self.lock:
            # 1. MODE
            if self.status == "MODE_SELECT" and user_id == self.creator:
                if cmd == "1":
                    self.mode = "single"
                    self.players['O'] = "BOT"; self.names['O'] = "Bot 🤖"
                    self.avatars['O'] = "https://robohash.org/talkinbot.png?set=set1"
                    self.status = "PLAYING"
                    self.send_visuals("🤖 Single Player Started!")
                    self.reset_timer(30, "turn")
                elif cmd == "2":
                    self.mode = "multi"; self.status = "BET_TYPE"
                    self.bot.send_message(self.room, "⚖️ **Multiplayer**\n`1` With Bet\n`2` No Bet")
                    self.reset_timer(90, "inactivity")
                return True

            # 2. BET TYPE
            if self.status == "BET_TYPE" and user_id == self.creator:
                if cmd == "1":
                    self.status = "BET_AMT"
                    self.bot.send_message(self.room, "💰 Enter Amount:")
                elif cmd == "2":
                    self.bet = 0; self.status = "WAITING"
                    self.bot.send_message(self.room, "⚔️ Fun Mode! Type `join`.")
                self.reset_timer(90, "inactivity")
                return True

            # 3. BET AMT
            if self.status == "BET_AMT" and user_id == self.creator and cmd.isdigit():
                amt = int(cmd)
                if amt <= 0: return True
                bal = get_balance(user_id)
                if amt > bal:
                    self.bot.send_message(self.room, f"❌ Low Balance: {bal}")
                    return True
                self.bet = amt; self.status = "WAITING"
                self.bot.send_message(self.room, f"⚔️ Bet: {amt}. Type `join`.")
                self.reset_timer(90, "inactivity")
                return True

            # 4. JOIN
            if self.status == "WAITING" and cmd == "join":
                if user_id == self.creator: return True
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
                curr = self.players[self.turn]
                if user_id != curr: return False
                
                p = int(cmd) - 1
                if 0 <= p <= 8 and self.board[p] == " ":
                    self.board[p] = self.turn
                    
                    win = self.check_win()
                    if win:
                        self.end_game(win, "Won")
                        return True
                    
                    self.turn = "O" if self.turn == "X" else "X"
                    
                    if self.mode == "single" and self.turn == "O":
                        av = [i for i,x in enumerate(self.board) if x==" "]
                        if av:
                            self.board[random.choice(av)] = "O"
                            if self.check_win():
                                self.end_game(self.check_win(), "Bot Won")
                                return True
                            self.turn = "X"

                    self.send_visuals(f"Turn: @{self.names[self.turn]}")
                    self.reset_timer(30, "turn")
                    return True
                else:
                    self.bot.send_message(self.room, "❌ Invalid!")
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
            self.bot.send_message(self.room, "🤝 **Draw!**")
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
            
            info = {'name': self.names[winner_sym], 'av': self.avatars.get(winner_sym, ""), 'sym': winner_sym, 'amt': amt}
            self.send_win_card(f"🏆 **{reason}**! {self.names[winner_sym]} Wins!", info)

        self.cleanup()

    def cleanup(self):
        self.status = "ENDED"
        if self.timer: self.timer.cancel()
        if self.room in active_games: del active_games[self.room]
        gc.collect()

# ==========================================
# 🌍 GLOBAL HANDLER
# ==========================================
active_games = {}

def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()
    uid = str(data.get("user_id", user))
    icon = data.get("icon", data.get("avatar", ""))

    if cmd == "tic":
        if not args: return False
        if args[0] == "0":
            if room_name in active_games:
                active_games[room_name].cleanup()
                bot.send_message(room_name, "🛑 Stopped.")
            else: bot.send_message(room_name, "⚠️ No game.")
            return True

        if args[0] == "1":
            if room_name in active_games:
                bot.send_message(room_name, "⚠️ Game running!")
                return True
            active_games[room_name] = TicTacToeGame(bot, room_name, uid, user, icon)
            return True

    if room_name in active_games:
        return active_games[room_name].process_input(cmd, uid, user, icon)

    return False
