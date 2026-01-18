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
        Processes incoming ROOM messages from TalkinChat.
        """
        text = data.get("body")
        if not text: 
            return

        room_name = data.get("room")
        user = data.get("from", "Unknown")
        
        cmd = ""
        args = []
        
        if text.startswith("!"):
            parts = text[1:].split(" ")
            cmd = parts[0].lower()
            args = parts[1:]
            
            self.bot.log(f"⚡ Command Detected: [{cmd}] in {room_name}")

            handled = False
            for name, module in self.plugins.items():
                if hasattr(module, 'handle_command'):
                    try:
                        if module.handle_command(self.bot, cmd, room_name, user, args, data):
                            self.bot.log(f"✅ Executed by Plugin: {name}")
                            handled = True
                            break
                    except Exception as e:
                        self.bot.log(f"❌ Plugin Error ({name}): {e}")
                        traceback.print_exc()
            
            if not handled:
                self.bot.log(f"⚠️ Unknown Command: {cmd}")

        else:
            # Handle non-command text (for games like TTT moves)
            cmd = text.strip()
            for name, module in self.plugins.items():
                if hasattr(module, 'handle_command'):
                    try:
                        if module.handle_command(self.bot, cmd, room_name, user, [], data):
                            return True
                    except:
                        pass
        return False

    # --- 🔥 NEW: PM (INBOX) MESSAGE HANDLER 🔥 ---
    def process_private_message(self, data):
        """
        Processes incoming PRIVATE messages from TalkinChat.
        """
        text = data.get("body", "").strip()
        user = data.get("from")
        
        if not text or not user: return

        # Command Parse karo
        if text.startswith("!"):
            parts = text[1:].split(" ")
            cmd = parts[0].lower()
            args = parts[1:]
            
            self.bot.log(f"⚡ PM Command Detected: [{cmd}] by {user}")

            # Plugin dhoondo jo 'handle_pm' support karta ho
            for name, module in self.plugins.items():
                if hasattr(module, 'handle_pm'):
                    try:
                        if module.handle_pm(self.bot, cmd, user, args, data):
                            self.bot.log(f"✅ PM Handled by Plugin: {name}")
                            break
                    except Exception as e:
                        self.bot.log(f"❌ PM Plugin Error ({name}): {e}")
                        traceback.print_exc()
