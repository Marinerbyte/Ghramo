import threading
import requests

# --- CONFIGURATION ---
# Tera wahi naya server URL
API_URL = "https://mp3-2mgp.onrender.com/convert"

def setup(bot):
    bot.log("🎵 Fast Music Plugin Loaded")

def music_task(bot, room_name, query, user):
    try:
        # Request to our Link Extractor
        resp = requests.post(API_URL, json={"query": query}, timeout=15)
        
        if resp.status_code != 200:
            bot.send_message(room_name, f"❌ Music Service Busy. (Error {resp.status_code})")
            return

        data = resp.json()
        if not data.get("success"):
            bot.send_message(room_name, f"❌ {data.get('error')}")
            return

        # Sab kuch ready-made link hai, seedha bhej do!
        title = data['title']
        audio_url = data['audio_url']
        image_url = data['card_url']

        # 1. Send Cover Art
        if image_url:
            bot.send_image(room_name, image_url)
        
        # 2. Send Info & Audio
        bot.send_message(room_name, f"💿 **Playing:** {title}\n👤 **Req by:** @{user}")
        bot.send_audio(room_name, audio_url)

    except Exception as e:
        bot.send_message(room_name, "⚠️ Connection Error.")

def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()
    if cmd == "play":
        if not args:
            bot.send_message(room_name, "❌ Usage: `!play song name`")
            return True
            
        query = " ".join(args)
        # Background thread me daalo taki bot free rahe
        threading.Thread(target=music_task, args=(bot, room_name, query, user), daemon=True).start()
        return True
    return False
