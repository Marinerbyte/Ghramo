import threading
import requests
import json
from PIL import Image

# Local imports
import utils

# --- CONFIGURATION ---
# 🔴 Aapka Naya Audio Server URL (Yahan set kar diya hai)
API_URL = "https://mp3-qj9e.onrender.com/convert"

def setup(bot):
    bot.log("🎧 YouTube Plugin (Remote Worker) Loaded")

def process_remote_task(bot, room_name, query, user):
    try:
        # User ko batao kaam shuru hai
        bot.send_message(room_name, f"🔎 **Searching & Processing:** `{query}`...\n(Please wait, downloading...)")

        # 1. API Call to Your New Worker Server
        payload = {"query": query}
        
        # Timeout 120s rakha hai kyunki download/upload mein time lagta hai
        resp = requests.post(API_URL, json=payload, timeout=120)
        
        if resp.status_code != 200:
            bot.send_message(room_name, f"❌ Server Error: {resp.status_code}")
            return

        data = resp.json()
        
        if not data.get("success"):
            error_msg = data.get('error', 'Unknown Error')
            bot.send_message(room_name, f"❌ Failed: {error_msg}")
            return

        # 2. Data aa gaya (URL of Audio & Image)
        title = data.get('title', 'Unknown Track')
        audio_url = data.get('audio_url')
        card_url = data.get('card_url')
        
        # 3. Send Music Card (Image)
        if card_url:
            bot.send_image(room_name, card_url)
        
        # 4. Send Audio File
        if audio_url:
            bot.send_message(room_name, f"💿 **Playing:** {title}\n👤 **Req by:** @{user}")
            bot.send_audio(room_name, audio_url)
        else:
            bot.send_message(room_name, "❌ Server finished but returned no audio URL.")

    except Exception as e:
        print(f"Remote Plugin Error: {e}")
        bot.send_message(room_name, "⚠️ Timeout or Connection Error with Audio Server.")

def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()
    
    if cmd == "play":
        if not args:
            bot.send_message(room_name, "❌ Usage: `!play song name`")
            return True
            
        query = " ".join(args)
        
        # Thread start karo taaki main bot block na ho
        t = threading.Thread(target=process_remote_task, args=(bot, room_name, query, user))
        t.daemon = True
        t.start()
        
        return True
    return False
