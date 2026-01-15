import os
import importlib.util
import sys
import traceback

PLUGIN_DIR = "plugins"

class PluginManager:
    def __init__(self, bot):
        self.bot = bot
        self.plugins = {} 
        if not os.path.exists(PLUGIN_DIR): os.makedirs(PLUGIN_DIR)

    def load_plugins(self):
        loaded = []
        self.plugins.clear()
        for filename in os.listdir(PLUGIN_DIR):
            if filename.endswith(".py"):
                name = filename[:-3]
                try:
                    self.load_plugin(name)
                    loaded.append(name)
                except Exception as e:
                    print(f"[Plugins] Error loading {name}: {e}")
        # Bot log me batao ki plugins load ho gaye
        self.bot.log(f"🧩 Plugins Loaded: {', '.join(loaded)}")
        return loaded

    def load_plugin(self, name):
        path = os.path.join(PLUGIN_DIR, f"{name}.py")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        if hasattr(module, 'setup'): module.setup(self.bot)
        self.plugins[name] = module

    def process_message(self, data):
        """
        Processes incoming message from TalkinChat.
        Expected data format: {"body": "text", "room": "name", "from": "username", ...}
        """
        # 1. Safely get text
        text = data.get("body")
        if not text: 
            return # Ignore non-text messages (like images without caption)

        room_name = data.get("room")
        user = data.get("from", "Unknown")
        
        # 2. Debug Log (Ye batayega ki bot message padh raha hai)
        # self.bot.log(f"🔍 Checking: {text} | By: {user}")

        # 3. Parse Command
        cmd = ""
        args = []
        
        if text.startswith("!"):
            parts = text[1:].split(" ") # Remove '!' and split
            cmd = parts[0].lower()      # Command ko lowercase karo (tic, ping)
            args = parts[1:]            # Baaki sab arguments
            
            self.bot.log(f"⚡ Command Detected: [{cmd}] in {room_name}")

            # 4. Dispatch to Plugins
            handled = False
            for name, module in self.plugins.items():
                if hasattr(module, 'handle_command'):
                    try:
                        # Plugin ko call karo
                        if module.handle_command(self.bot, cmd, room_name, user, args, data):
                            self.bot.log(f"✅ Executed by Plugin: {name}")
                            handled = True
                            break # Command handle ho gaya, loop roko
                    except Exception as e:
                        self.bot.log(f"❌ Plugin Error ({name}): {e}")
                        traceback.print_exc()
            
            if not handled:
                self.bot.log(f"⚠️ Unknown Command: {cmd}")

        else:
            # Agar '!' nahi hai, tab bhi game plugins ko bhejo (jaise number guess ya tic tac toe move)
            cmd = text.strip()
            for name, module in self.plugins.items():
                if hasattr(module, 'handle_command'):
                    try:
                        if module.handle_command(self.bot, cmd, room_name, user, args, data):
                            return True
                    except:
                        pass
        return False
