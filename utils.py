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
from requests_toolbelt.multipart.encoder import MultipartEncoder
# --- CONFIGURATION & SAFETY ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
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
    n = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    f = "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ₀₁₂₃₄₅₆₇₈₉"
    return str(text).translate(str.maketrans(n, f))

# --- 3. GRAPHIC ENGINE (Full) ---
def create_canvas(w, h, color=(0,0,0)): return Image.new('RGB', (w,h), color)
def draw_circle_avatar(canvas, url, x, y, size, **kwargs):
    try:
        if not url: return
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=5, verify=False)
        if r.status_code != 200: return
        with io.BytesIO(r.content) as buf, Image.open(buf) as av_raw:
            av = av_raw.convert("RGBA").resize((size,size), Image.Resampling.LANCZOS)
            mask = Image.new("L", (size,size), 0); ImageDraw.Draw(mask).ellipse((0,0,size,size), fill=255)
            canvas.paste(av, (x,y), mask)
        if kwargs.get('border_width', 0) > 0: ImageDraw.Draw(canvas).ellipse([x-kwargs['border_width'],y-kwargs['border_width'],x+size+kwargs['border_width'],y+size+kwargs['border_width']], outline=kwargs['border_color'], width=kwargs['border_width'])
    except: pass
def draw_gradient_bg(canvas, start, end):
    w,h=canvas.size; base=Image.new('RGB',(w,h),start); top=Image.new('RGB',(w,h),end)
    mask=Image.new('L',(w,h)); d=[]
    for y in range(h): d.extend([int(255*(y/h))]*w)
    mask.putdata(d); canvas.paste(top,(0,0),mask)
def draw_rounded_rect(canvas, coords, r, color, **kwargs):
    ImageDraw.Draw(canvas).rounded_rectangle(coords, r, fill=color, **kwargs)

# --- 🔥 THE ULTIMATE LIGHTWEIGHT UPLOADER 🔥 ---
def upload_image(image):
    url = None
    buf = None
    try:
        buf = io.BytesIO()
        
        # 1. Convert to RGB (zaroori hai JPEG ke liye)
        img_rgb = image.convert("RGB")
        
        # 2. Color Reduction (Quantize) - Size bohot kam kar dega
        # Ye colors ko 256 tak limit kar dega
        img_quantized = img_rgb.quantize(colors=256)
        
        # Quantize ke baad wapas RGB me convert karo taaki save ho sake
        img_to_save = img_quantized.convert("RGB")

        # 3. Save with Smart Quality & Progressive Scan
        img_to_save.save(buf,
                         format='JPEG',
                         quality=75,       # 75% quality (Best balance)
                         optimize=True,    # Faltu data hatao
                         progressive=True) # Fast loading effect
        
        buf.seek(0)
        files = {'reqtype':(None,'fileupload'), 'fileToUpload':(f'bot_{uuid.uuid4().hex}.jpg', buf, 'image/jpeg')}
        
        # Catbox fast hai, isliye wahi use karenge
        r = requests.post('https://catbox.moe/user/api.php', files=files, headers={'Connection':'close'}, timeout=30)
        
        if r.status_code == 200 and "http" in r.text:
            url = r.text.strip()
        else:
            safe_print(f"❌ Upload Fail (Catbox): {r.status_code}")

    except Exception as e:
        safe_print(f"❌ Internal Upload Error: {e}")
    finally:
        if buf: buf.close()
        gc.collect()
            
    return url

# --- 🔐 PRIVATE IMAGE UPLOADER (PM ONLY) ---
def upload_private_image(pil_image, bot_id, to_user):
    from io import BytesIO

    buf = None
    try:
        buf = BytesIO()
        pil_image.save(buf, format="PNG")
        buf.seek(0)

        multipart_data = MultipartEncoder(
            fields={
                "file": ("pm.png", buf, "image/png"),
                "jid": bot_id,
                "is_private": "yes",
                "to": to_user,
                "device_id": uuid.uuid4().hex
            }
        )

        r = requests.post(
            "https://cdn.chatp.net/post.php",
            data=multipart_data,
            headers={"Content-Type": multipart_data.content_type},
            timeout=30
        )

        if r.status_code == 200:
            return r.text.strip()

    except Exception as e:
        safe_print(f"❌ Private Upload Error: {e}")

    finally:
        if buf:
            buf.close()
        gc.collect()

    return None    
