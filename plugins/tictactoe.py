import requests
import io
import threading
import traceback
from PIL import Image, ImageDraw, ImageFont

# --- GAME STATE ---
games = {}
games_lock = threading.Lock()

# --- TALKINCHAT UPLOAD ---
# TalkinChat ka specific upload endpoint
UPLOAD_URL = "https://cdn.talkinchat.com/post.php"

def upload_image(bot, image):
    """
    Uploads PIL Image to TalkinChat CDN and logs the result
    """
    try:
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        files = {'file': ('game.png', img_byte_arr, 'image/png')}
        
        # Bot ko log bhejne ke liye
        bot.log("📤 Uploading Game Image...")
        
        r = requests.post(UPLOAD_URL, files=files, timeout=15)
        
        # TalkinChat usually returns the URL directly in text
        if r.status_code == 200:
            url = r.text.strip()
            if "http" in url:
                bot.log(f"✅ Image Uploaded: {url}")
                return url
            else:
                # Try JSON parsing if text isn't a URL
                try:
                    res = r.json()
                    url = res.get('url') or res.get('file')
                    bot.log(f"✅ Image Uploaded (JSON): {url}")
                    return url
                except:
                    bot.log(f"❌ Upload Response Invalid: {r.text[:50]}")
        else:
            bot.log(f"❌ Upload Failed: {r.status_code}")
            
    except Exception as e:
        bot.log(f"❌ Upload Error: {e}")
    return None

def draw_board(board):
    size = 300
    cell = size // 3
    img = Image.new('RGB', (size, size), (255, 255, 255))
    d = ImageDraw.Draw(img)
    
    # Grid Lines
    for i in range(1, 3):
        d.line([(cell*i, 0), (cell*i, size)], fill="black", width=5)
        d.line([(0, cell*i), (size, cell*i)], fill="black", width=5)
    
    # Try loading font
    try:
        font = ImageFont.truetype("arial.ttf", 60)
    except:
        font = ImageFont.load_default()

    # Draw X and O
    for i, val in enumerate(board):
        if val:
            row, col = i // 3, i % 3
            x = col * cell + cell // 2
            y = row * cell + cell // 2
            color = "red" if val == "X" else "blue"
            
            # Simple Text Drawing
            w, h = 40, 40 # Approx for default font
            d.text((x-10, y-20), val, fill=color, font=font)
            
    return img

class TicTacToe:
    def __init__(self, p1):
        self.board = [None] * 9
        self.turn = "X"
        self.p1 = p1
        self.p2 = None
        self.state = "waiting"

def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()
    global games
    
    try:
        with games_lock:
            game = games.get(room_name)
            
            # 1. Start Game
            if cmd == "!tic":
                if game:
                    bot.send_message(room_name, "⚠️ Game already running here!")
                    return True
                
                games[room_name] = TicTacToe(user)
                bot.send_message(room_name, f"🎮 **Tic Tac Toe Created!**\nHost: @{user}\nType `!join` to play.")
                return True

            # 2. Join Game
            if cmd == "!join":
                if not game:
                    bot.send_message(room_name, "❌ No game to join. Type `!tic`.")
                    return True
                
                if game.state == "waiting":
                    if user == game.p1:
                        bot.send_message(room_name, "⚠️ You are the host!")
                        return True
                        
                    game.p2 = user
                    game.state = "playing"
                    
                    bot.send_message(room_name, f"🥊 Match Started!\n@{game.p1} (X) vs @{game.p2} (O)\n@{game.p1} turn! Type 1-9.")
                    
                    # Initial Board
                    img = draw_board(game.board)
                    url = upload_image(bot, img)
                    if url: 
                        bot.send_image(room_name, url)
                    return True

            # 3. Play Move (Numbers 1-9)
            if game and game.state == "playing" and cmd.isdigit():
                idx = int(cmd) - 1
                if not (0 <= idx <= 8): return False # Ignore invalid numbers
                
                # Turn Logic
                curr_player = game.p1 if game.turn == "X" else game.p2
                
                if user != curr_player:
                    # Silent return if wrong player types number (don't spam chat)
                    return False 
                    
                if game.board[idx]: 
                    bot.send_message(room_name, "🚫 Box taken! Try another.")
                    return True
                    
                game.board[idx] = game.turn
                
                # Check Win
                wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
                won = False
                for a,b,c in wins:
                    if game.board[a] and game.board[a] == game.board[b] == game.board[c]:
                        won = True
                        break
                
                if won:
                    img = draw_board(game.board)
                    url = upload_image(bot, img)
                    if url: bot.send_image(room_name, url)
                    bot.send_message(room_name, f"🏆 **@{user} WINS!** 🏆")
                    del games[room_name]
                    return True
                
                if None not in game.board:
                    bot.send_message(room_name, "🤝 **It's a Draw!**")
                    del games[room_name]
                    return True

                # Switch Turn
                game.turn = "O" if game.turn == "X" else "X"
                
                # Send Board Update
                img = draw_board(game.board)
                url = upload_image(bot, img)
                if url: bot.send_image(room_name, url)
                
                next_p = game.p1 if game.turn == "X" else game.p2
