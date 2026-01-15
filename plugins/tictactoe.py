import requests
import io
import threading
from PIL import Image, ImageDraw, ImageFont

# --- GAME STATE ---
games = {}
games_lock = threading.Lock()

# --- TALKINCHAT UPLOAD ---
UPLOAD_URL = "https://cdn.talkinchat.com/post.php"

def upload_image(image):
    """
    Uploads PIL Image to TalkinChat CDN
    """
    try:
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        # Standard generic PHP upload structure
        files = {'file': ('game.png', img_byte_arr, 'image/png')}
        # Some generic uploaders need a key or type, checking prompt...
        # Prompt only gave URL, assuming standard multipart POST.
        
        r = requests.post(UPLOAD_URL, files=files, timeout=15)
        
        # Parse Response (Adapting to common returns or plain text)
        # If response is JSON containing url
        try:
            res = r.json()
            return res.get('url') or res.get('file') or res.get('data', {}).get('url')
        except:
            # If response is plain text URL
            if r.status_code == 200 and "http" in r.text:
                return r.text.strip()
    except Exception as e:
        print(f"Upload Error: {e}")
    return None

def draw_board(board):
    size = 300
    cell = size // 3
    img = Image.new('RGB', (size, size), (255, 255, 255))
    d = ImageDraw.Draw(img)
    
    # Grid
    for i in range(1, 3):
        d.line([(cell*i, 0), (cell*i, size)], fill="black", width=5)
        d.line([(0, cell*i), (size, cell*i)], fill="black", width=5)
    
    # Marks
    try:
        font = ImageFont.truetype("arial.ttf", 60)
    except:
        font = ImageFont.load_default()

    for i, val in enumerate(board):
        if val:
            row, col = i // 3, i % 3
            x = col * cell + cell // 2
            y = row * cell + cell // 2
            color = "red" if val == "X" else "blue"
            d.text((x, y), val, fill=color, font=font, anchor="mm")
            
    return img

class TicTacToe:
    def __init__(self, p1):
        self.board = [None] * 9
        self.turn = "X"
        self.p1 = p1
        self.p2 = None
        self.state = "waiting"

def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower()
    global games
    
    with games_lock:
        game = games.get(room_name)
        
        if cmd == "!tic":
            if game:
                bot.send_message(room_name, "Game in progress!")
                return True
            games[room_name] = TicTacToe(user)
            bot.send_message(room_name, f"🎮 **Tic Tac Toe**\nHost: @{user}\nType `!join` to play.")
            return True

        if cmd == "!join" and game and game.state == "waiting":
            if user == game.p1: return True
            game.p2 = user
            game.state = "playing"
            bot.send_message(room_name, f"Match: @{game.p1} (X) vs @{game.p2} (O)\nX goes first! Type 1-9.")
            
            # Send initial board
            img = draw_board(game.board)
            url = upload_image(img)
            if url: bot.send_image(room_name, url)
            return True

        if game and game.state == "playing" and command.isdigit():
            idx = int(command) - 1
            if not (0 <= idx <= 8): return False
            
            # Turn Logic
            curr_player = game.p1 if game.turn == "X" else game.p2
            if user != curr_player: return False
            if game.board[idx]: 
                bot.send_message(room_name, "Taken!")
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
                url = upload_image(img)
                if url: bot.send_image(room_name, url)
                bot.send_message(room_name, f"🏆 @{user} Wins!")
                del games[room_name]
                return True
            
            if None not in game.board:
                bot.send_message(room_name, "🤝 Draw!")
                del games[room_name]
                return True

            # Switch Turn
            game.turn = "O" if game.turn == "X" else "X"
            
            # Send Board Update
            img = draw_board(game.board)
            url = upload_image(img)
            if url: bot.send_image(room_name, url)
            
            next_p = game.p1 if game.turn == "X" else game.p2
            bot.send_message(room_name, f"Turn: @{next_p}")
            return True

    return False
