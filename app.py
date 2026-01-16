from flask import Flask
from bot_engine import TalkinChatBot
from ui import register_routes
import os
import threading
import gc # 🛠️ RAM Management ke liye

# Bot ki memory ko control mein rakhne ke liye Garbage Collection enable karein
gc.enable()

app = Flask(__name__)
# Secret key environment se uthayein ya random generate karein
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

# Start Bot Instance
# Architecture ke mutabik ye connection aur plugins sambhalega
bot = TalkinChatBot()

# UI Routes ko Bot se connect karein
register_routes(app, bot)

if __name__ == "__main__":
    # Port handling for Render or Local
    port = int(os.environ.get("PORT", 5000))
    
    # 🚨 CRITICAL FIXES FOR PRODUCTION:
    # 1. threaded=True: Flask aur WebSocket parallel chalenge.
    # 2. use_reloader=False: Iske bina bot 2 baar login hoga aur disconnect ho jayega.
    # 3. debug=False: Production (Render) par debug band hona chahiye.
    
    app.run(
        host="0.0.0.0", 
        port=port, 
        threaded=True, 
        use_reloader=False, 
        debug=False
    )
