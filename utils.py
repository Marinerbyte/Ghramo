import os
import io
import requests
import urllib3
import threading
import time
import gc
import uuid
import logging
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURATION ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
font_lock = threading.Lock()
print_lock = threading.Lock()
FONT_CACHE = {}
MAX_FONT_CACHE = 30 
logging.basicConfig(level=logging.ERROR)

def safe_print(msg):
    with print_lock: print(msg)

# --- 1. FONT LOADER (Aapka Original Code) ---
def get_font(font_name="arial.ttf", size=20):
    global FONT_CACHE
    cache_key = f"{font_name}_{size}"
    with font_lock:
        if cache_key in FONT_CACHE: return FONT_CACHE[cache_key]
        if len(FONT_CACHE) >= MAX_FONT_CACHE:
            FONT_CACHE.clear(); gc.collect()
        search_paths = [
            f"fonts/{font_name}", font_name,
            f"/usr/share/fonts/truetype/dejavu/{font_name}",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        ]
        font_obj = None
        for path in search_paths:
            if os.path.exists(path):
                try: font_obj = ImageFont.truetype(path, size); break
                except: continue
        if not font_obj:
            try: font_obj = ImageFont.load_default()
            except: pass
        FONT_CACHE[cache_key] = font_obj
        return font_obj

# --- 2. TEXT UTILS (Aapka Original Code) ---
def fancy_text(text):
    normal = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    fancy  = "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ₀₁₂₃₄₅₆₇₈₉"
    return str(text).translate(str.maketrans(normal, fancy))

# --- 3. GRAPHIC ENGINE (Aapka Original Code + Fix) ---
def create_canvas(w, h, color=(0, 0, 0)): 
    return Image.new('RGB', (w, h), color=color)

def draw_circle_avatar(canvas, url, x, y, size, border_color=(255, 255, 255), border_width=4):
    try:
        if not url or not url.startswith("http"): return
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=5, verify=False)
        if resp.status_code != 200: return
        with io.BytesIO(resp.content) as buf:
            with Image.open(buf) as av_raw:
                av_raw = av_raw.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
                mask = Image.new('L', (size, size), 0)
                draw_mask = ImageDraw.Draw(mask); draw_mask.ellipse((0, 0, size, size), fill=255)
                canvas.paste(av_raw, (x, y), mask)
        if border_width > 0:
            d = ImageDraw.Draw(canvas)
            d.ellipse([x-border_width, y-border_width, x+size+border_width, y+size+border_width], outline=border_color, width=border_width)
    except Exception as e: safe_print(f"❌ Avatar Error: {e}")

def draw_gradient_bg(canvas, start_color, end_color):
    w, h = canvas.size
    base = Image.new('RGB', (w, h), start_color)
    top = Image.new('RGB', (w, h), end_color)
    mask = Image.new('L', (w, h)); mask_data = []
    for y in range(h): mask_data.extend([int(255 * (y / h))] * w)
    mask.putdata(mask_data); canvas.paste(top, (0, 0), mask)

# 🔥 FIX: Added 'outline' and 'width' to match my advanced plugins
def draw_rounded_rect(canvas, coords, radius, color, width=0, outline=None):
    d = ImageDraw.Draw(canvas)
    if width > 0:
        d.rounded_rectangle(coords, radius=radius, outline=outline or color, width=width)
    else:
        d.rounded_rectangle(coords, radius=radius, fill=color)

# --- 4. UPLOAD IMAGE (Aapka Original Code + Fix) ---
def upload_image(image):
    url = None; buf = None
    try:
        buf = io.BytesIO()
        # 🔥 FIX: PNG -> JPEG for fast loading (ye zaroori hai)
        # PNG 200KB ki hoti thi, JPEG 30KB ki hogi
        image.convert("RGB").save(buf, format='JPEG', quality=85, optimize=True, progressive=True)
        buf.seek(0)
        
        unique_name = f'bot_{uuid.uuid4().hex}.jpg' # Extension changed to .jpg
        files = {'reqtype':(None,'fileupload'), 'fileToUpload':(unique_name, buf, 'image/jpeg')}
        headers = {'Connection': 'close'}
        
        r = requests.post('https://catbox.moe/user/api.php', files=files, headers=headers, timeout=30, verify=False)
        
        if r.status_code == 200 and "http" in r.text:
            url = r.text.strip()
        else: safe_print(f"❌ Upload Fail: {r.status_code} | {r.text}")
    except Exception as e: safe_print(f"❌ Upload Error: {e}")
    finally:
        if buf: buf.close()
    return url
