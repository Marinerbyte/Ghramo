import os
import io
import requests
import urllib3
import threading
import time
import gc
import uuid
import base64
import logging
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURATION ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 🔥 IMGBB API KEY (Aapki Key daal di hai)
IMGBB_API_KEY = "e4e441cad420ecfac5c61786331f1d37"

# --- LOCKS & CACHE ---
font_lock = threading.Lock()
print_lock = threading.Lock()
FONT_CACHE = {}
MAX_FONT_CACHE = 30
logging.basicConfig(level=logging.ERROR)

def safe_print(msg):
    with print_lock: print(msg)

# --- FONT LOADER ---
def get_font(font_name="arial.ttf", size=20):
    global FONT_CACHE
    cache_key = f"{font_name}_{size}"
    with font_lock:
        if cache_key in FONT_CACHE: return FONT_CACHE[cache_key]
        if len(FONT_CACHE) >= MAX_FONT_CACHE: FONT_CACHE.clear(); gc.collect()
        search_paths = [f"fonts/{font_name}", font_name, f"/usr/share/fonts/truetype/dejavu/{font_name}"]
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

# --- GRAPHIC ENGINE ---
def create_canvas(w, h, color=(0,0,0)): return Image.new('RGB', (w,h), color)

def draw_circle_avatar(canvas, url, x, y, size, border_color=(255,255,255), border_width=4):
    try:
        if not url: return
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=5, verify=False)
        if r.status_code != 200: return
        with io.BytesIO(r.content) as buf, Image.open(buf) as av_raw:
            av = av_raw.convert("RGBA").resize((size,size), Image.Resampling.LANCZOS)
            mask = Image.new("L", (size,size), 0); ImageDraw.Draw(mask).ellipse((0,0,size,size), fill=255)
            canvas.paste(av, (x,y), mask)
        if border_width > 0: ImageDraw.Draw(canvas).ellipse([x-border_width,y-border_width,x+size+border_width,y+size+border_width], outline=border_color, width=border_width)
    except Exception as e: safe_print(f"❌ Avatar Error: {e}")

def draw_gradient_bg(canvas, start, end):
    w, h = canvas.size; base=Image.new('RGB',(w,h),start); top=Image.new('RGB',(w,h),end)
    mask=Image.new('L',(w,h)); mask_data=[]
    for y in range(h): mask_data.extend([int(255*(y/h))]*w)
    mask.putdata(mask_data); canvas.paste(top,(0,0),mask)

def draw_rounded_rect(canvas, coords, r, color, **kwargs):
    ImageDraw.Draw(canvas).rounded_rectangle(coords, r, fill=color, **kwargs)

# --- 🔥 IMGBB UPLOADER (THE FIX) ---
def upload_image(image):
    url = None
    buf = None
    try:
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format='JPEG', quality=85)
        buf.seek(0)
        
        # Image ko Base64 me convert karo
        img_base64 = base64.b64encode(buf.read())
        
        payload = {
            'key': IMGBB_API_KEY,
            'image': img_base64
        }
        
        # Upload
        safe_print("⬆️ Uploading to imgbb...")
        r = requests.post("https://api.imgbb.com/1/upload", data=payload, timeout=30)
        
        data = r.json()
        if data['success']:
            url = data['data']['url']
            safe_print(f"✅ imgbb Link: {url}")
        else:
            safe_print(f"❌ imgbb Error: {data['error']['message']}")

    except Exception as e:
        safe_print(f"❌ Upload Error: {e}")
    finally:
        if buf: buf.close()
        gc.collect() # Cleanup
            
    return url
