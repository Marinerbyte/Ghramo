import random
import sys
import os

# --- DB IMPORT ---
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    import db
except:
    pass

games = {}

def setup(bot):
    print("Guess Plugin with Score System Loaded")

def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()
    global games
    user_id = data.get("user_id", user)

    if cmd == "guess":
        if room_name in games:
            bot.send_message(room_name, "⚠️ Game already running! Guess the number (1-100).")
            return True
        
        number = random.randint(1, 100)
        games[room_name] = {"num": number, "attempts": 0}
        bot.send_message(room_name, f"🔢 **Guess the Number (1-100)**\n@{user} started the game! Win 100 coins.")
        return True

    if room_name in games and cmd.isdigit():
        val = int(cmd)
        game = games[room_name]
        game["attempts"] += 1
        
        if val == game["num"]:
            # --- WINNER SCORE ADDED HERE ---
            reward = 100
            db.add_game_result(str(user_id), user, "guess_game", reward, is_win=True)
            
            bot.send_message(room_name, f"🎉 CORRECT! @{user} guessed it in {game['attempts']} tries and won {reward} coins! 💰")
            del games[room_name]
        elif val < game["num"]:
            bot.send_message(room_name, "🔼 Higher!")
        else:
            bot.send_message(room_name, "🔽 Lower!")
        return True

    return False
