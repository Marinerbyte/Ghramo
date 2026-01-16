import os
import io
import requests
import urllib3
import threading
import time
import gc # Garbage Collector for RAM management
import logging
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

# SSL warnings off
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIG & LOCKS ---
font_lock = threading.Lock()
FONT_CACHE = {}
MAX_FONT_CACHE = 30 # RAM bachane ke liye limit

# Error Logging setup
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("Utils")

# --- 1. RAM-FRIENDLY FONT LOADER ---

def get_font(font_name="arial.ttf", size=20):
    """Memory-efficient font loader."""
    global FONT_CACHE
    cache_key = f"{font_name}_{size}"
    
    with font_lock:
        if cache_key in FONT_CACHE:
            return FONT_CACHE[cache_key]
        
        # Cache clean up agar limit se bahar jaye
        if len(FONT_CACHE) >= MAX_FONT_CACHE:
            FONT_CACHE.clear()
            gc.collect() # Force clear memory
        
        search_paths = [
            f"fonts/{font_name}",
            font_name,
            f"/usr/share/fonts/truetype/dejavu/{font_name}"
        ]
        
        font_obj = None
        for path in search_paths:
            if os.path.exists(path):
                try:
                    font_obj = ImageFont.truetype(path, size)
                    break
                except Exception as e:
                    logger.error(f"Font Load Error ({path}): {e}")
        
        if not font_obj:
            font_obj = ImageFont.load_default()
            
        FONT_CACHE[cache_key] = font_obj
        return font_obj

# --- 2. TEXT TOOLS ---

def fancy_text(text):
    """Small caps converter (Thread-safe)."""
    normal = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    fancy  = "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ₀₁₂₃₄₅₆₇₈₉"
    return str(text).translate(str.maketrans(normal, fancy))

# --- 3. GRAPHIC ENGINE (Optimized for RAM) ---

def create_canvas(w, h, bg_color=(0, 0, 0)):
    """Naya board banana (Always use with explicit delete)."""
    return Image.new('RGB', (w, h), color=bg_color)

def draw_circle_avatar(canvas, url, x, y, size, border_color=(255, 255, 255), border_width=4):
    """User DP crop and paste (With Memory Safety)."""
    try:
        if not url or not url.startswith("http"): return
        
        # Strict timeout to prevent hanging threads
        resp = requests.get(url, timeout=7, verify=False)
        if resp.status_code != 200: return
        
        # Open and process avatar
        with Image.open(io.BytesIO(resp.content)) as av_raw:
            av_raw = av_raw.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
            
            mask = Image.new('L', (size, size), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.ellipse((0, 0, size, size), fill=255)
            
            canvas.paste(av_raw, (x, y), mask)
            
            # Explicit cleanup of temporary objects
            del mask
            
        if border_width > 0:
            d = ImageDraw.Draw(canvas)
            d.ellipse([x-border_width, y-border_width, x+size+border_width, y+size+border_width], 
                      outline=border_color, width=border_width)
        
        # Memory cleanup trigger
        gc.collect()
        
    except Exception as e:
        logger.error(f"draw_circle_avatar failed: {e}")

def draw_gradient_bg(canvas, start_color, end_color):
    """Gradient background (Memory efficient)."""
    w, h = canvas.size
    base = Image.new('RGB', (w, h), start_color)
    top = Image.new('RGB', (w, h), end_color)
    mask = Image.new('L', (w, h))
    mask_data = []
    for y in range(h):
        mask_data.extend([int(255 * (y / h))] * w)
    mask.putdata(mask_data)
    canvas.paste(top, (0, 0), mask)
    del base, top, mask, mask_data # Force release

# --- 4. MEDIA UPLOADERS ---

def upload_image(image):
    """Catbox Uploader with forceful RAM release."""
    url = None
    try:
        buf = io.BytesIO()
        image.save(buf, format='PNG', optimize=True) # Optimize for smaller size
        buf.seek(0)
        
        files = {
            'reqtype': (None, 'fileupload'),
            'fileToUpload': (f'bot_img_{int(time.time())}.png', buf, 'image/png')
        }
        
        r = requests.post('https://catbox.moe/user/api.php', files=files, timeout=12)
        if r.status_code == 200 and "http" in r.text:
            url = r.text.strip()
        
        buf.close()
        del buf
    except Exception as e:
        logger.error(f"upload_image failed: {e}")
    
    # Very important for Render: cleanup after heavy PIL usage
    gc.collect()
    return url

# --- 5. PAYLOAD HELPERS ---

def get_image_payload(room_name, url, caption=""):
    import uuid
    return {
        "handler": "room_message",
        "id": uuid.uuid4().hex,
        "room": room_name,
        "type": "image",
        "url": url,
        "body": caption,
        "length": ""
    }
