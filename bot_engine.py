import websocket
import json
import threading
import time
import uuid
import ssl
from plugin_loader import PluginManager
from db import init_db

# ✅ URL FIXED: Added /server back
WS_URL = "wss://chatp.net:5333/server"

class TalkinChatBot:
    def __init__(self):
        self.ws = None
        self.user_data = {}
        self.active_rooms = []
        self.logs = []
        self.running = False
        self.start_time = time.time()
        self.room_details = {} 
        init_db()
        self.plugins = PluginManager(self)
        self.log("Bot Initialized. Ready.")

    def log(self, message):
        entry = f"[{time.strftime('%H:%M:%S')}] {message}"
        print(entry)
        self.logs.append(entry)
        # ✅ Auto-clean logs (Max 100)
        if len(self.logs) > 100:
            self.logs.pop(0)

    def login_api(self, username, password):
        self.user_data = {"username": username, "password": password}
        self.log(f"Credentials stored. ready to connect.")
        return True, "Starting..."

    def connect_ws(self):
        # ✅ FIX: Check ACTUAL connection state, not just 'running' flag
        if self.ws and self.ws.sock and self.ws.sock.connected:
            self.log("⚠️ Bot is already connected.")
            return

        if not self.user_data: 
            self.log("❌ Error: No credentials.")
            return

        self.log(f"Connecting to {WS_URL} ...")
        self.running = True

        # ✅ Added Headers (Looks like a real browser to avoid blocks)
        self.ws = websocket.WebSocketApp(
            WS_URL,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            header={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        )
        
        self.ws_thread = threading.Thread(target=lambda: self.ws.run_forever(
            ping_interval=30, 
            ping_timeout=10,
            sslopt={"cert_reqs": ssl.CERT_NONE}
        ))
        self.ws_thread.daemon = True
        self.ws_thread.start()

    def on_open(self, ws):
        self.log("✅ Connected. Sending Login...")
        self.start_time = time.time()
        
        payload = {
            "handler": "login",
            "id": uuid.uuid4().hex,
            "username": self.user_data.get('username'),
            "password": self.user_data.get('password')
        }
        self.send_json(payload)

    def on_message(self, ws, message):
        try:
            # 📥 Show Incoming Payload
            self.log(f"📥 RECV: {message}")
            
            data = json.loads(message)
            handler = data.get("handler")
            
            if handler == "login_event":
                if data.get("type") == "success":
                    self.log("✅ Login Authorized.")
                    for room in self.active_rooms:
                        self.join_room(room)
                else:
                    self.log(f"❌ Login Failed: {data}")
                    self.disconnect() # Stop on bad password

            elif handler == "room_event":
                self.plugins.process_message(data)
                
                room_name = data.get("room")
                event_type = data.get("type")
                
                if room_name:
                    if room_name not in self.room_details:
                        self.room_details[room_name] = {'users': [], 'chat_log': []}

                    if event_type in ["text", "image"]:
                        author = data.get("from", "Unknown")
                        text_body = data.get("body", "")
                        author_class = 'bot' if author == self.user_data.get('username') else 'user'
                        
                        log_entry = {'author': author, 'text': text_body, 'type': author_class}
                        self.room_details[room_name]['chat_log'].append(log_entry)
                        
                        if len(self.room_details[room_name]['chat_log']) > 50:
                            self.room_details[room_name]['chat_log'].pop(0)

        except Exception as e:
            self.log(f"❌ JSON Error: {e}")
    
    def on_error(self, ws, error):
        if self.running:
            self.log(f"❌ Socket Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        # ✅ Logic: Agar user ne Stop dabaya hai (running=False), to bas ruk jao.
        if not self.running:
            self.log("🔒 Bot Stopped (User Action).")
            return
        
        # Agar error aaya (running=True), to Reconnect karo
        self.log(f"⚠️ Disconnected ({close_msg}). Reconnecting in 5s...")
        time.sleep(5)
        
        # ✅ Reconnect ke waqt wapas connect_ws call karenge
        # (Upar connect_ws me fix kar diya hai taaki loop na ho)
        self.connect_ws()

    # --- ACTIONS ---
    def send_json(self, data):
        try:
            if self.ws and self.ws.sock and self.ws.sock.connected:
                json_str = json.dumps(data)
                self.log(f"📤 SEND: {json_str}")
                self.ws.send(json_str)
            else:
                self.log("⚠️ Cannot Send: Not Connected")
        except Exception as e:
            self.log(f"❌ Send Error: {e}")

    def send_message(self, room_name, text):
        self.send_json({
            "handler": "room_message",
            "id": uuid.uuid4().hex,
            "room": room_name,
            "type": "text",
            "url": "",
            "body": text,
            "length": ""
        })

    def send_image(self, room_name, url):
        self.send_json({
            "handler": "room_message",
            "id": uuid.uuid4().hex,
            "room": room_name,
            "type": "image",
            "url": url,
            "body": "",
            "length": ""
        })

    # ✅ ADDED: Audio Sending Capability
    def send_audio(self, room_name, url):
        self.send_json({
            "handler": "room_message",
            "id": uuid.uuid4().hex,
            "room": room_name,
            "type": "audio",
            "url": url,
            "body": "",
            "length": "0"
        })
    
    def join_room(self, room_name):
        self.log(f"Joining {room_name}...")
        self.send_json({
            "handler": "room_join",
            "id": uuid.uuid4().hex,
            "name": room_name
        })
        if room_name not in self.active_rooms:
            self.active_rooms.append(room_name)

    def disconnect(self):
        self.log("🛑 Stopping Bot...")
        self.running = False # Flag False karte hi reconnect band ho jayega
        self.room_details = {}
        if self.ws:
            try: self.ws.close()
            except: pass
            self.ws = None
