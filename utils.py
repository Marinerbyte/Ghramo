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
# SSL Warnings ko chup karana zaroori hai
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- LOCKS (Thread Safety) ---
# Font Lock: Taaki 2 threads ek sath file na khole (Crash se bachata hai)
font_lock = threading.Lock()
# Print Lock: Taaki logs aapas mein mix na hon
print_lock = threading.Lock()

# RAM Management
FONT_CACHE = {}
MAX_FONT_CACHE = 30 
logging.basicConfig(level=logging.ERROR)

def safe_print(msg):
    """Thread-safe printing function"""
    with print_lock:
        print(msg)

# --- 1. RAM-FRIENDLY FONT LOADER ---
# Ye 5 tarah se font dhundhta hai, kabhi fail nahi hoga
def get_font(font_name="arial.ttf", size=20):
    global FONT_CACHE
    cache_key = f"{font_name}_{size}"
    
    with font_lock:
        if cache_key in FONT_CACHE:
            return FONT_CACHE[cache_key]
        
        # Agar cache full ho jaye, to safai karo (Memory Leak Protection)
        if len(FONT_CACHE) >= MAX_FONT_CACHE:
            FONT_CACHE.clear()
            gc.collect()
        
        search_paths = [
            f"fonts/{font_name}",
            font_name,
            f"/usr/share/fonts/truetype/dejavu/{font_name}",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        ]
        
        font_obj = None
        for path in search_paths:
            if os.path.exists(path):
                try:
                    font_obj = ImageFont.truetype(path, size)
                    break
                except: continue
        
        # Fallback: Agar koi font na mile to crash mat hone do
        if not font_obj:
            try: font_obj = ImageFont.load_default()
            except: pass
            
        FONT_CACHE[cache_key] = font_obj
        return font_obj

# --- 2. TEXT UTILS ---
def fancy_text(text):
    """Normal text ko Fancy text mein badalta hai"""
    normal = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    fancy  = "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ₀₁₂₃₄₅₆₇₈₉"
    return str(text).translate(str.maketrans(normal, fancy))

# --- 3. GRAPHIC ENGINE ---

def create_canvas(w, h, color=(0, 0, 0)): 
    """Naya Image Canvas banata hai"""
    return Image.new('RGB', (w, h), color=color)

def draw_circle_avatar(canvas, url, x, y, size, border_color=(255, 255, 255), border_width=4):
    """
    Avatar download karke Circle Crop karta hai.
    FIX: User-Agent add kiya taaki server block na kare.
    """
    try:
        if not url or not url.startswith("http"): return
        
        # Browser Headers (Server ko lagega ye Chrome hai)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        # Fresh Request (No Session)
        resp = requests.get(url, headers=headers, timeout=5, verify=False)
        
        if resp.status_code != 200: 
            return
            
        with io.BytesIO(resp.content) as buf:
            with Image.open(buf) as av_raw:
                av_raw = av_raw.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
                
                # Masking (Circle Crop)
                mask = Image.new('L', (size, size), 0)
                draw_mask = ImageDraw.Draw(mask)
                draw_mask.ellipse((0, 0, size, size), fill=255)
                
                canvas.paste(av_raw, (x, y), mask)
                
        if border_width > 0:
            d = ImageDraw.Draw(canvas)
            d.ellipse([x-border_width, y-border_width, x+size+border_width, y+size+border_width], outline=border_color, width=border_width)
            
    except Exception as e:
        safe_print(f"❌ Avatar Error: {e}")

def draw_gradient_bg(canvas, start_color, end_color):
    """Background mein Gradient bharta hai"""
    w, h = canvas.size
    base = Image.new('RGB', (w, h), start_color)
    top = Image.new('RGB', (w, h), end_color)
    mask = Image.new('L', (w, h))
    mask_data = []
    for y in range(h): mask_data.extend([int(255 * (y / h))] * w)
    mask.putdata(mask_data)
    canvas.paste(top, (0, 0), mask)

def draw_rounded_rect(canvas, coords, radius, color, width=0, outline=None):
    """Rounded Rectangle (Button style)"""
    d = ImageDraw.Draw(canvas)
    if width > 0:
        d.rounded_rectangle(coords, radius=radius, outline=outline or color, width=width)
    else:
        d.rounded_rectangle(coords, radius=radius, fill=color)

# --- 4. UPLOAD IMAGE (The Critical Part) ---
def upload_image(image):
    """
    Image Upload Logic:
    1. UUID use karta hai (Unique Name = No Race Condition).
    2. Connection: close use karta hai (No Blocking/Collision).
    3. Proper Error Handling aur Memory Cleanup.
    """
    url = None
    buf = None
    try:
        # Buffer creation (RAM mein)
        buf = io.BytesIO()
        image.save(buf, format='PNG', optimize=True)
        buf.seek(0)
        
        # Unique Filename generate karo
        unique_name = f'bot_{uuid.uuid4().hex}.png'
        
        files = {
            'reqtype': (None, 'fileupload'),
            'fileToUpload': (unique_name, buf, 'image/png')
        }
        
        # HEADERS: Force Close Connection (Ye Room Collision rokega)
        headers = {'Connection': 'close'}
        
        # Upload Request (30s timeout)
        r = requests.post('https://catbox.moe/user/api.php', files=files, headers=headers, timeout=30, verify=False)
        
        if r.status_code == 200 and "http" in r.text:
            url = r.text.strip()
            # safe_print(f"✅ Uploaded: {unique_name}")
        else:
            safe_print(f"❌ Upload Fail: {r.status_code} | {r.text}")
            
    except Exception as e:
        safe_print(f"❌ Upload Error: {e}")
    finally:
        # Memory Cleanup (Buffer close karna zaroori hai)
        if buf: buf.close()
            
    return url
