import random

# Simple in-memory state
games = {}

def setup(bot):
    print("Guess Plugin Loaded")

def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower()
    global games

    # Start Game
    if cmd == "!guess":
        if room_name in games:
            bot.send_message(room_name, "Game already running! Guess 1-100.")
            return True
        
        number = random.randint(1, 100)
        games[room_name] = {"num": number, "attempts": 0}
        bot.send_message(room_name, "🔢 **Guess the Number!** (1-100)\nType a number to guess.")
        return True

    # Check Guess (if it's a number and game exists)
    if room_name in games and command.isdigit():
        val = int(command)
        game = games[room_name]
        game["attempts"] += 1
        
        if val == game["num"]:
            bot.send_message(room_name, f"🎉 Correct! @{user} won in {game['attempts']} tries.")
            del games[room_name]
        elif val < game["num"]:
            bot.send_message(room_name, "🔼 Higher!")
        else:
            bot.send_message(room_name, "🔽 Lower!")
        return True
        
    if cmd == "!stopguess" and room_name in games:
        del games[room_name]
        bot.send_message(room_name, "❌ Game stopped.")
        return True

    return False
