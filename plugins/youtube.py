import threading
import requests
import json
import time

# Local imports
import utils

# --- CONFIGURATION ---
# 👇 Tera Naya Audio Server URL (JioSaavn wala)
API_URL = "https://mp3-2mgp.onrender.com/convert"

def setup(bot):
    bot.log("🎵 Music Plugin (Connected to mp3-2mgp) Loaded")

def music_task(bot, room_name, query, user):
    try:
        # 1. User ko batao hum dhoond rahe hain
        bot.send_message(room_name, f"🔎 **Searching:** `{query}`...\n(Fetching from High Speed Server...)")

        # 2. Server ko request bhejo
        payload = {"query": query}
        
        # Timeout 60s kaafi hai kyunki JioSaavn fast hai
        resp = requests.post(API_URL, json=payload, timeout=60)
        
        # 3. Error Checking
        if resp.status_code != 200:
            bot.send_message(room_name, f"❌ Server Error: {resp.status_code}")
            return

        data = resp.json()
        
        if not data.get("success"):
            error_msg = data.get('error', 'Unknown Error')
            bot.send_message(room_name, f"❌ Failed: {error_msg}")
            return

        # 4. Data Extract Karo
        title = data.get('title', 'Unknown Track')
        audio_url = data.get('audio_url')
        card_url = data.get('card_url')
        duration = data.get('duration', 'N/A')

        # 5. Image (Card) Bhejo
        if card_url:
            bot.send_image(room_name, card_url)
            # Thoda sa delay taaki image pehle load ho jaye
            time.sleep(0.5)
        
        # 6. Audio Bhejo
        if audio_url:
            bot.send_message(room_name, f"💿 **Playing:** {title}\n⏱ **Duration:** {duration}\n👤 **Req by:** @{user}")
            bot.send_audio(room_name, audio_url)
        else:
            bot.send_message(room_name, "❌ Audio URL nahi mila server se.")

    except Exception as e:
        print(f"Music Plugin Error: {e}")
        bot.send_message(room_name, "⚠️ Connection Timeout or Server Error.")

def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()
    
    if cmd == "play":
        if not args:
            bot.send_message(room_name, "❌ Usage: `!play song name`")
            return True
            
        query = " ".join(args)
        
        # Thread start karo (Background me chalega)
        t = threading.Thread(target=music_task, args=(bot, room_name, query, user))
        t.daemon = True
        t.start()
        
        return True

    return False
