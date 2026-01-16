import os
import io
import requests
import urllib3
import threading
import time
import gc
import logging
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIG & LOCKS ---
font_lock = threading.Lock()
FONT_CACHE = {}
MAX_FONT_CACHE = 30 

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("Utils")

# --- 1. RAM-FRIENDLY FONT LOADER ---
def get_font(font_name="arial.ttf", size=20):
    global FONT_CACHE
    cache_key = f"{font_name}_{size}"
    
    with font_lock:
        if cache_key in FONT_CACHE:
            return FONT_CACHE[cache_key]
        
        if len(FONT_CACHE) >= MAX_FONT_CACHE:
            FONT_CACHE.clear()
            gc.collect()
        
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
                except: continue
        
        if not font_obj:
            font_obj = ImageFont.load_default()
            
        FONT_CACHE[cache_key] = font_obj
        return font_obj

def fancy_text(text):
    normal = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    fancy  = "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ₀₁₂₃₄₅₆₇₈₉"
    return str(text).translate(str.maketrans(normal, fancy))

# --- 3. GRAPHIC ENGINE (Fixed create_canvas) ---

def create_canvas(w, h, color=(0, 0, 0)): # Changed 'bg_color' to 'color' to match plugin usage
    """Naya board banana."""
    return Image.new('RGB', (w, h), color=color)

def draw_circle_avatar(canvas, url, x, y, size, border_color=(255, 255, 255), border_width=4):
    try:
        if not url or not url.startswith("http"): return
        
        resp = requests.get(url, timeout=7, verify=False)
        if resp.status_code != 200: return
        
        with Image.open(io.BytesIO(resp.content)) as av_raw:
            av_raw = av_raw.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
            
            mask = Image.new('L', (size, size), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.ellipse((0, 0, size, size), fill=255)
            
            canvas.paste(av_raw, (x, y), mask)
            
        if border_width > 0:
            d = ImageDraw.Draw(canvas)
            d.ellipse([x-border_width, y-border_width, x+size+border_width, y+size+border_width], 
                      outline=border_color, width=border_width)
        gc.collect()
    except: pass

def draw_gradient_bg(canvas, start_color, end_color):
    w, h = canvas.size
    base = Image.new('RGB', (w, h), start_color)
    top = Image.new('RGB', (w, h), end_color)
    mask = Image.new('L', (w, h))
    mask_data = []
    for y in range(h):
        mask_data.extend([int(255 * (y / h))] * w)
    mask.putdata(mask_data)
    canvas.paste(top, (0, 0), mask)
    del base, top, mask, mask_data

def draw_rounded_rect(canvas, coords, radius, color, width=0, outline=None):
    d = ImageDraw.Draw(canvas)
    if width > 0:
        d.rounded_rectangle(coords, radius=radius, outline=outline or color, width=width)
    else:
        d.rounded_rectangle(coords, radius=radius, fill=color)

# --- 4. MEDIA UPLOADERS ---

def upload_image(image):
    url = None
    try:
        buf = io.BytesIO()
        image.save(buf, format='PNG', optimize=True)
        buf.seek(0)
        
        files = {
            'reqtype': (None, 'fileupload'),
            'fileToUpload': (f'bot_img_{int(time.time())}.png', buf, 'image/png')
        }
        r = requests.post('https://catbox.moe/user/api.php', files=files, timeout=12)
        if r.status_code == 200 and "http" in r.text:
            url = r.text.strip()
        buf.close()
    except: pass
    gc.collect()
    return url
