import websocket
import json
import threading
import time
import uuid
import ssl
from plugin_loader import PluginManager
from db import init_db

# Correct URL for TalkinChat
WS_URL = "wss://chatp.net:5333/"

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
        self.log("Bot Initialized. Waiting for login...")

    def log(self, message):
        # Time stamp ke saath log entry
        entry = f"[{time.strftime('%X')}] {message}"
        print(entry) # Terminal me print karega
        self.logs.append(entry)
        
        # Requirement: Auto-clean after 100 logs
        if len(self.logs) > 100:
            self.logs.pop(0)

    def login_api(self, username, password):
        self.user_data = {"username": username, "password": password}
        self.log(f"Credentials set for {username}.")
        return True, "Ready to connect."

    def connect_ws(self):
        if self.running:
            self.log("⚠️ Bot is already running.")
            return

        if not self.user_data: 
            self.log("❌ Error: No username/password.")
            return

        self.log(f"Connecting to {WS_URL} ...")
        self.running = True

        # SSL Context (Security warnings avoid karne ke liye)
        self.ws = websocket.WebSocketApp(
            WS_URL,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        
        self.ws_thread = threading.Thread(target=lambda: self.ws.run_forever(
            ping_interval=30, 
            ping_timeout=10,
            sslopt={"cert_reqs": ssl.CERT_NONE}
        ))
        self.ws_thread.daemon = True
        self.ws_thread.start()

    def on_open(self, ws):
        self.log("✅ WebSocket Connected.")
        self.start_time = time.time()
        
        # Login Payload Send
        payload = {
            "handler": "login",
            "id": uuid.uuid4().hex,
            "username": self.user_data.get('username'),
            "password": self.user_data.get('password')
        }
        self.send_json(payload)

    def on_message(self, ws, message):
        try:
            # 📥 LOG INCOMING PAYLOAD
            self.log(f"📥 RECV: {message}")
            
            data = json.loads(message)
            handler = data.get("handler")
            
            # --- Login Handler ---
            if handler == "login_event":
                if data.get("type") == "success":
                    self.log("✅ Login Successful.")
                    for room in self.active_rooms:
                        self.join_room(room)
                else:
                    self.log(f"❌ Login Failed: {data}")
                    self.disconnect()

            # --- Room Events ---
            elif handler == "room_event":
                self.plugins.process_message(data)
                
                room_name = data.get("room")
                event_type = data.get("type")
                
                # Room Details Update for UI
                if room_name:
                    if room_name not in self.room_details:
                        self.room_details[room_name] = {'users': [], 'chat_log': []}

                    if event_type in ["text", "image"]:
                        author = data.get("from", "Unknown")
                        text_body = data.get("body", "")
                        author_class = 'bot' if author == self.user_data.get('username') else 'user'
                        
                        log_entry = {'author': author, 'text': text_body, 'type': author_class}
                        self.room_details[room_name]['chat_log'].append(log_entry)
                        
                        # Keep UI Chat clean (50 msgs)
                        if len(self.room_details[room_name]['chat_log']) > 50:
                            self.room_details[room_name]['chat_log'].pop(0)

        except Exception as e:
            self.log(f"❌ JSON Error: {e}")
    
    def on_error(self, ws, error):
        if self.running:
            self.log(f"❌ WebSocket Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        if not self.running:
            self.log("🔒 Bot Stopped by User.")
            return
        
        self.log("⚠️ Connection Lost. Reconnecting in 5s...")
        time.sleep(5)
        self.connect_ws()

    # --- ACTIONS ---
    def send_json(self, data):
        try:
            if self.ws and self.ws.sock and self.ws.sock.connected:
                # 📤 LOG OUTGOING PAYLOAD
                json_data = json.dumps(data)
                self.log(f"📤 SEND: {json_data}")
                self.ws.send(json_data)
            else:
                self.log("⚠️ Cannot Send: Disconnected.")
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
        self.running = False  # Flag set False immediately
        self.room_details = {}
        if self.ws:
            try: self.ws.close()
            except: pass
            self.ws = None
