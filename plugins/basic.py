import random

def setup(bot):
    print("Basic Plugin Loaded")

# Ye Room ke liye hai (Pehle jaisa)
def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()
    
    if cmd == "ping":
        bot.send_message(room_name, f"@{user} Pong! 🏓")
        return True

    if cmd == "dice":
        result = random.randint(1, 6)
        bot.send_message(room_name, f"@{user} rolled a 🎲 {result}")
        return True
    
    # ... baki commands ...

    return False

# --- 🔥 YE NAYA ADD KAR SAKTE HO (Optional) 🔥 ---
# Ye PM (Inbox) ke liye hai
def handle_pm(bot, command, user, args, data):
    cmd = command.lower().strip()
    
    if cmd == "ping":
        # Yahan hum send_message nahi, send_pm_message use karenge
        bot.send_pm_message(user, "Pong from your private assistant! 🏓")
        return True

    if cmd == "dice":
        result = random.randint(1, 6)
        bot.send_pm_message(user, f"You rolled a 🎲 {result}")
        return True
        
    return False
