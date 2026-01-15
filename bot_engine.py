import websocket
import json
import threading
import time
import uuid
from plugin_loader import PluginManager
from db import init_db

# TalkinChat Configuration
WS_URL = "wss://chatp.net:5333/server"

class TalkinChatBot:
    def __init__(self):
        self.ws = None
        self.user_data = {}
        self.active_rooms = []
        self.logs = []
        self.running = False
        self.start_time = time.time()
        
        # Room tracking
        self.room_details = {} # {room_name: {users: [], chat_log: []}}
        
        init_db()
        self.plugins = PluginManager(self)
        self.log("Bot Initialized. Ready for TalkinChat.")

    def log(self, message):
        entry = f"[{time.strftime('%X')}] {message}"
        print(entry)
        self.logs.append(entry)
        if len(self.logs) > 200: self.logs.pop(0)

    def login_api(self, username, password):
        # TalkinChat handles login via WebSocket, so we just store credentials here
        # and trigger connection.
        self.user_data = {"username": username, "password": password}
        self.log(f"Credentials stored for {username}. Starting WS...")
        return True, "Credentials saved. Connecting..."

    def connect_ws(self):
        if not self.user_data: return
        self.log("Connecting to WebSocket...")
        
        self.ws = websocket.WebSocketApp(
            WS_URL,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.running = True
        self.ws_thread = threading.Thread(target=lambda: self.ws.run_forever(ping_interval=30, ping_timeout=10))
        self.ws_thread.daemon = True
        self.ws_thread.start()

    def on_open(self, ws):
        self.log("SUCCESS: WebSocket Connected. Sending Login...")
        self.start_time = time.time()
        
        # TalkinChat Login Payload
        payload = {
            "handler": "login",
            "id": uuid.uuid4().hex,
            "username": self.user_data.get('username'),
            "password": self.user_data.get('password')
        }
        self.send_json(payload)

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            handler = data.get("handler")
            
            # --- Login Event ---
            if handler == "login_event":
                if data.get("type") == "success":
                    self.log("SUCCESS: Login Authorized.")
                    # Re-join active rooms if any
                    for room in self.active_rooms:
                        self.join_room(room)
                else:
                    self.log(f"LOGIN FAILED: {data}")

            # --- Room Events (Messages/Joins) ---
            elif handler == "room_event":
                room_name = data.get("room")
                event_type = data.get("type")
                
                # Ensure local tracking exists
                if room_name and room_name not in self.room_details:
                    self.room_details[room_name] = {'users': [], 'chat_log': []}

                # 1. User Joined
                if event_type == "user_joined":
                    new_user = data.get("username")
                    if new_user and new_user not in self.room_details[room_name]['users']:
                        self.room_details[room_name]['users'].append(new_user)
                        self.log(f"Event: {new_user} joined {room_name}")

                # 2. Text/Image Message
                elif event_type == "text" or event_type == "image":
                    author = data.get("from", "Unknown")
                    text_body = data.get("body", "")
                    
                    # Log for UI
                    author_class = 'bot' if author == self.user_data.get('username') else 'user'
                    log_entry = {'author': author, 'text': text_body, 'type': author_class}
                    
                    if room_name in self.room_details:
                        self.room_details[room_name]['chat_log'].append(log_entry)
                        if len(self.room_details[room_name]['chat_log']) > 50:
                            self.room_details[room_name]['chat_log'].pop(0)
                    
                    # Pass to Plugin System
                    # TalkinChat structure: 'room' is the ID/Name, 'from' is user, 'body' is text
                    # We normalize this for plugins
                    self.plugins.process_message(data)

            # --- Private Message ---
            elif handler == "chat_message":
                # Handle PMs if needed (similar logic to room_event)
                pass

        except Exception as e:
            self.log(f"ERROR: on_message: {e}")
    
    def on_error(self, ws, error):
        self.log(f"ERROR: WebSocket: {error}")

    def on_close(self, ws, _, __):
        self.log("Connection Closed. Reconnecting in 5s...")
        if self.running:
            time.sleep(5)
            self.connect_ws()

    # --- HELPER FUNCTIONS ---
    def send_json(self, data):
        if self.ws and self.ws.sock and self.ws.sock.connected:
            self.ws.send(json.dumps(data))
        else:
            self.log("ERROR: Cannot send, WebSocket is not connected.")

    def send_message(self, room_name, text):
        # TalkinChat Group Message Payload
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
        # TalkinChat Image Payload
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
        self.log(f"Action: Joining room '{room_name}'...")
        # TalkinChat Join Payload
        self.send_json({
            "handler": "room_join",
            "id": uuid.uuid4().hex,
            "name": room_name
        })
        
        if room_name not in self.active_rooms:
            self.active_rooms.append(room_name)
        
        # Init local cache
        if room_name not in self.room_details:
             self.room_details[room_name] = {'users': [], 'chat_log': []}

    def leave_room(self, room_name):
        self.log(f"Action: Leaving room '{room_name}'...")
        self.send_json({
            "handler": "room_leave",
            "id": uuid.uuid4().hex,
            "name": room_name
        })
        if room_name in self.active_rooms:
            self.active_rooms.remove(room_name)

    def disconnect(self):
        self.log("Action: Disconnecting bot...")
        self.running = False
        self.room_details = {}
        if self.ws:
            self.ws.close()
