import random

games = {}

def setup(bot):
    print("Guess Plugin Loaded")

def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()
    global games

    # Command bina '!' ke check karein
    if cmd == "guess":
        if room_name in games:
            bot.send_message(room_name, "Game already running! Guess 1-100.")
            return True
        
        number = random.randint(1, 100)
        games[room_name] = {"num": number, "attempts": 0}
        bot.send_message(room_name, "🔢 **Guess the Number!** (1-100)\nType a number to guess.")
        return True

    if cmd == "stopguess" and room_name in games:
        del games[room_name]
        bot.send_message(room_name, "❌ Game stopped.")
        return True

    # Guessing logic (No '!' needed for numbers)
    if room_name in games and cmd.isdigit():
        val = int(cmd)
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

    return False
