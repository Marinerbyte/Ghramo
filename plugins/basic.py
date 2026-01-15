import random

def setup(bot):
    print("Basic Plugin Loaded")

def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower()
    
    if cmd == "!ping":
        bot.send_message(room_name, f"@{user} Pong! 🏓")
        return True

    if cmd == "!dice":
        result = random.randint(1, 6)
        bot.send_message(room_name, f"@{user} rolled a 🎲 {result}")
        return True
    
    if cmd == "!join":
        # Owner only check can be added here
        if args:
            target_room = " ".join(args)
            bot.join_room(target_room)
            bot.send_message(room_name, f"Joining {target_room}...")
        return True

    return False
