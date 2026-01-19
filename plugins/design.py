import os
import random
import threading
import gc
import io
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# Local imports
import utils

# --- 1. ASSET CONFIGURATION & AUTO-DOWNLOADER ---
ASSET_BASE = "assets/design"
FONTS_DIR = os.path.join(ASSET_BASE, "fonts")
STICKERS_DIR = os.path.join(ASSET_BASE, "stickers")
BACKGROUNDS_DIR = os.path.join(ASSET_BASE, "backgrounds")
EMOJI_FONT_PATH = os.path.join(FONTS_DIR, "NotoColorEmoji.ttf")

# List of assets to download if missing
ASSET_URLS = {
    "fonts": [
        ("https://github.com/google/fonts/raw/main/ofl/montserrat/Montserrat-Bold.ttf", "montserrat.ttf"),
        ("https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf", "oswald.ttf"),
        ("https://github.com/google/fonts/raw/main/apache/opensans/OpenSans-Bold.ttf", "opensans.ttf"),
        ("https://github.com/google/fonts/raw/main/ofl/notocoloremoji/NotoColorEmoji-Regular.ttf", "NotoColorEmoji.ttf")
    ],
    "backgrounds": [
        ("https://i.imgur.com/2cCIc4c.jpeg", "bg1.jpeg"), # Dark abstract
        ("https://i.imgur.com/s6h5t8l.jpeg", "bg2.jpeg"), # Neon grid
        ("https://i.imgur.com/M6y7O6j.jpeg", "bg3.jpeg")  # Galaxy
    ],
    "stickers": [
        ("https://i.imgur.com/O61JmDo.png", "crown.png"),   # Crown
        ("https://i.imgur.com/bW34f8a.png", "flame.png"),   # Flame
        ("https://i.imgur.com/1vYg7k6.png", "swords.png") # Swords
    ]
}

ASSET_CACHE = {"fonts": [], "stickers": [], "backgrounds": []}
COLOR_PALETTES = [{"text": "#FFFFFF", "shadow": "#111827"}, {"text": "#FBBF24", "shadow": "#000000"}]

def download_asset(url, save_path):
    """Downloads a single asset if it doesn't exist."""
    if not os.path.exists(save_path):
        print(f"📥 Downloading asset: {os.path.basename(save_path)}...")
        try:
            r = requests.get(url, stream=True, timeout=15)
            if r.status_code == 200:
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(1024):
                        f.write(chunk)
            else:
                print(f"❌ Failed to download {url}")
        except Exception as e:
            print(f"❌ Download Error: {e}")

def setup_assets():
    """Checks, downloads, and loads all assets."""
    print("🎨 Initializing design assets...")
    # Create folders
    for path in [FONTS_DIR, STICKERS_DIR, BACKGROUNDS_DIR]:
        os.makedirs(path, exist_ok=True)
    
    # Download missing assets
    for asset_type, urls in ASSET_URLS.items():
        for url, filename in urls:
            save_path = os.path.join(f"{ASSET_BASE}/{asset_type}", filename)
            download_asset(url, save_path)
    
    # Load into RAM
    # Fonts
    ASSET_CACHE["fonts"] = [os.path.join(FONTS_DIR, f) for f in os.listdir(FONTS_DIR) if f.endswith('.ttf')]
    # Stickers
    for f in os.listdir(STICKERS_DIR):
        with Image.open(os.path.join(STICKERS_DIR, f)) as img: ASSET_CACHE["stickers"].append(img.copy())
    # Backgrounds
    for f in os.listdir(BACKGROUNDS_DIR):
        with Image.open(os.path.join(BACKGROUNDS_DIR, f)) as img: ASSET_CACHE["backgrounds"].append(img.copy())
    
    print("✅ Design assets are ready!")

def setup(bot):
    bot.log("🎨 Design Plugin (Auto-Download) Initializing...")
    threading.Thread(target=setup_assets, daemon=True).start()

# --- (The rest of the code: get_random_from_cache, generate_design, handle_command, etc. is THE SAME) ---
# ...
# PASTE THE REST OF THE PREVIOUS `design.py` CODE HERE
# ...
