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

# 🔥 TINYPNG API KEY (Aapki Key daal di hai)
TINYPNG_API_KEY = "bkqK1RGz19FMtkstv9k6Ynwc0HHTXZf5"

# --- LOCKS & CACHE ---
font_lock = threading.Lock()
print_lock = threading.Lock()
FONT_CACHE = {}
MAX_FONT_CACHE = 30
logging.basicConfig(level=logging.ERROR)

def safe_print(msg):
    with print_lock: print(msg)

# --- 1. FONT LOADER (Full) ---
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

# --- 2. TEXT UTILS (Full) ---
def fancy_text(text):
    normal = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    fancy  = "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ₀₁₂₃₄₅₆₇₈₉"
    return str(text).translate(str.maketrans(normal, fancy))

# --- 3. GRAPHIC ENGINE (Full) ---
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

def draw_rounded_rect(canvas, coords, radius, color, width=0, outline=None):
    d = ImageDraw.Draw(canvas)
    if width > 0:
        d.rounded_rectangle(coords, radius=radius, outline=outline or color, width=width)
    else:
        d.rounded_rectangle(coords, radius=radius, fill=color)

# --- 🔥 TINYPNG UPLOADER (THE SPEED FIX) ---
def upload_image(image):
    url = None
    buf = None
    try:
        # 1. Image ko High Quality buffer me daalo
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format='JPEG', quality=90)
        
        # 2. TinyPNG se compress karo
        # safe_print("🚀 Compressing with TinyPNG...")
        api_url = "https://api.tinify.com/shrink"
        response = requests.post(api_url, auth=("api", TINYPNG_API_KEY), data=buf.getvalue(), timeout=30)
        
        if response.status_code != 201:
            safe_print(f"❌ TinyPNG Error: {response.text}")
            # Agar TinyPNG fail ho, toh Imgbb try karo
            return upload_fallback(image)

        # Compressed image ka URL
        compressed_url = response.json()['output']['url']
        
        # 3. Compressed image ko download karo
        compressed_data = requests.get(compressed_url).content
        
        # 4. Catbox par upload karo (Fastest for delivery)
        files = {'reqtype':(None,'fileupload'), 'fileToUpload':('tiny.jpg', compressed_data, 'image/jpeg')}
        r = requests.post('https://catbox.moe/user/api.php', files=files, headers={'Connection':'close'}, timeout=30)
        
        if r.status_code == 200:
            url = r.text.strip()
            # safe_print(f"🎉 Final URL: {url}")
            
    except Exception as e:
        safe_print(f"❌ Upload Error: {e}")
    finally:
        if buf: buf.close()
        gc.collect()
            
    return url

def upload_fallback(image):
    """Agar TinyPNG fail ho jaye to ye backup chalega"""
    safe_print("⚠️ TinyPNG failed. Using fallback uploader...")
    # (Yahan aap Imgbb ya Catbox ka direct code daal sakte hain, for now just Catbox)
    try:
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format='JPEG', quality=75)
        buf.seek(0)
        files = {'reqtype':(None,'fileupload'), 'fileToUpload':('fallback.jpg', buf, 'image/jpeg')}
        r = requests.post('https://catbox.moe/user/api.php', files=files, headers={'Connection':'close'}, timeout=30)
        if r.status_code == 200:
            return r.text.strip()
    except: return None
    return None
