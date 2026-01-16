import os
import io
import requests
import urllib3
import threading
import time
import gc
import uuid
import random
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURATION ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# LOCKS
font_lock = threading.Lock()
print_lock = threading.Lock()

FONT_CACHE = {}
MAX_FONT_CACHE = 30 
logging.basicConfig(level=logging.ERROR)

def safe_print(msg):
    with print_lock:
        print(msg)

# --- ADVANCED SESSION SETUP (Pooling) ---
# Ye 'Pool' ek saath 20 uploads sambhal lega bina crash hue
retry_strategy = Retry(
    total=4,  # 4 baar try karega
    backoff_factor=1,  # Har fail ke baad 1s, 2s, 4s rukega
    status_forcelist=[429, 500, 502, 503, 504],
)
adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retry_strategy)
http = requests.Session()
http.mount("https://", adapter)
http.mount("http://", adapter)

# --- FONT LOADER ---
def get_font(font_name="arial.ttf", size=20):
    global FONT_CACHE
    cache_key = f"{font_name}_{size}"
    with font_lock:
        if cache_key in FONT_CACHE: return FONT_CACHE[cache_key]
        if len(FONT_CACHE) >= MAX_FONT_CACHE:
            FONT_CACHE.clear(); gc.collect()
        
        search_paths = [f"fonts/{font_name}", font_name, f"/usr/share/fonts/truetype/dejavu/{font_name}", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]
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

# --- GRAPHICS ---
def create_canvas(w, h, color=(0, 0, 0)): 
    return Image.new('RGB', (w, h), color=color)

def draw_circle_avatar(canvas, url, x, y, size, border_color=(255, 255, 255), border_width=4):
    try:
        if not url or not url.startswith("http"): return
        # Use Global Session for faster download
        resp = http.get(url, timeout=5, verify=False)
        if resp.status_code != 200: return
        with io.BytesIO(resp.content) as buf:
            with Image.open(buf) as av_raw:
                av_raw = av_raw.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
                mask = Image.new('L', (size, size), 0)
                draw_mask = ImageDraw.Draw(mask)
                draw_mask.ellipse((0, 0, size, size), fill=255)
                canvas.paste(av_raw, (x, y), mask)
        if border_width > 0:
            d = ImageDraw.Draw(canvas)
            d.ellipse([x-border_width, y-border_width, x+size+border_width, y+size+border_width], outline=border_color, width=border_width)
    except: pass

def draw_gradient_bg(canvas, start_color, end_color):
    w, h = canvas.size
    base = Image.new('RGB', (w, h), start_color)
    top = Image.new('RGB', (w, h), end_color)
    mask = Image.new('L', (w, h))
    mask_data = []
    for y in range(h): mask_data.extend([int(255 * (y / h))] * w)
    mask.putdata(mask_data)
    canvas.paste(top, (0, 0), mask)

# --- ROBUST UPLOADER (SESSION POOL + JITTER) ---
def upload_image(image):
    url = None
    buf = None
    
    # Random Delay to prevent collision (0.1s to 0.5s)
    # Ye bohot zaroori hai taaki 2 rooms takraye nahi
    time.sleep(random.uniform(0.1, 0.5))
    
    try:
        buf = io.BytesIO()
        image.save(buf, format='PNG', optimize=True)
        buf.seek(0)
        unique_name = f'bot_{uuid.uuid4().hex}.png'
        files = {'reqtype': (None, 'fileupload'), 'fileToUpload': (unique_name, buf, 'image/png')}
        
        # Use Global Session (http.post instead of requests.post)
        r = http.post('https://catbox.moe/user/api.php', files=files, timeout=30, verify=False)
        
        if r.status_code == 200 and "http" in r.text:
            url = r.text.strip()
            # safe_print(f"✅ Upload: {unique_name}")
        else:
            safe_print(f"❌ Upload Fail Code: {r.status_code}")
            
    except Exception as e:
        safe_print(f"❌ Upload Err: {e}")
    finally:
        if buf: buf.close()
        # gc.collect() # Don't over-collect, let Python manage
            
    return url
