import requests
import re
import urllib.parse

def setup(bot):
    bot.log("🎵 Simple Music Plugin Loaded")

def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()

    if cmd == "play":
        # Agar user ne gaana nahi likha
        if not args:
            bot.send_message(room_name, "❌ Song name likho.")
            return True

        song_name = " ".join(args)

        try:
            # 1. YouTube Search
            query_encoded = urllib.parse.quote(song_name)
            search_url = f"https://www.youtube.com/results?search_query={query_encoded}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }

            res = requests.get(search_url, headers=headers, timeout=10)
            
            # 2. Video ID Nikalo
            video_ids = re.findall(r'watch\?v=(\S{11})', res.text)

            if video_ids:
                video_id = video_ids[0]
                
                # 3. Direct MP3 Link Banao (Vevioz)
                music_url = f"https://api.vevioz.com/@api/button/mp3/{video_id}"
                
                # 🔥 MAIN CHEEZ: send_audio use kar rahe hain
                # Ye chat room mein "Link" nahi, "Player" banayega.
                bot.send_audio(room_name, music_url)
                
            else:
                bot.send_message(room_name, "❌ Song nahi mila.")

        except Exception as e:
            bot.log(f"Music Error: {e}")

        return True

    return False
