import threading
import random
import re
import gc
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# Local imports
import utils

# --- THEMES ---
THEMES = [
    {"bg_type":"gradient", "colors":[(43,16,80),(17,24,39)], "font":"fonts/arial.ttf", "text_color":"#ffffff", "effect":"glow", "effect_color":"#a855f7"},
    {"bg_type":"solid", "colors":[(20,18,24)], "font":"fonts/times.ttf", "text_color":"#fbbf24", "effect":"shadow", "effect_color":"#000000"},
    {"bg_type":"gradient", "colors":[(14,58,86),(17,24,39)], "font":"fonts/verdana.ttf", "text_color":"#ffffff", "effect":"outline", "effect_color":"#0ea5e9"}
]

def setup(bot):
    bot.log("🎨 PM Master (v3 - No Brackets) Loaded")

# ... (text_wrap and generate_image functions wahi rahenge, koi change nahi) ...
def text_wrap(text, font, max_w):
    lines = []; words = text.split(' ')
    i = 0
    while i < len(words):
        line = ''
        while i < len(words) and font.getlength(line + words[i]) <= max_w: line += words[i] + " "; i += 1
        if not line: line = words[i]; i += 1
        lines.append(line.strip())
    return lines

def generate_image(sender, text):
    W, H = 512, 512
    theme = random.choice(THEMES)
    canvas = Image.new("RGB", (W, H))
    if theme['bg_type'] == 'gradient': utils.draw_gradient_bg(canvas, theme['colors'][0], theme['colors'][1])
    else: ImageDraw.Draw(canvas).rectangle([0,0,W,H], fill=theme['colors'][0])
    draw = ImageDraw.Draw(canvas)
    
    try: font = ImageFont.truetype(theme['font'], 48)
    except: font = ImageFont.load_default()
    
    lines = text_wrap(text, font, W-80)
    y_start = (H - (len(lines)*55))//2
    
    for i, line in enumerate(lines):
        x, y = W/2, y_start + (i*55)
        if theme['effect'] == 'shadow': draw.text((x+3,y+3), line, font=font, fill=theme['effect_color'], anchor="mm")
        elif theme['effect'] == 'outline':
            for dx,dy in [(-2,-2),(2,-2),(-2,2),(2,2)]: draw.text((x+dx,y+dy), line, font=font, fill=theme['effect_color'], anchor="mm")
        draw.text((x,y), line, font=font, fill=theme['text_color'], anchor="mm")

    draw.text((W-30,H-30), f"From: @{sender}", font=utils.get_font("arial.ttf", 16), fill="#ffffff80", anchor="rs")
    return canvas

# --- BACKGROUND WORKERS ---
def pmi_task(bot, sender, target, message):
    try:
        img = generate_image(sender, message)
        url = utils.upload_image(img)
        
        if url:
            bot.send_pm_image(target, url)
            # Sender ko confirmation bhej sakte hain (Optional)
            bot.send_pm_message(sender, f"✅ Image successfully sent to @{target}")
        else:
            bot.send_pm_message(sender, f"❌ Failed to send image to @{target}. Upload error.")
    finally:
        gc.collect()

def pm_task(bot, sender, target, message):
    bot.send_pm_message(target, f"📩 PM from @{sender}: {message}")
    bot.send_pm_message(sender, f"✅ Text message sent to @{target}")

# --- COMMAND HANDLER ---
def handle_command(bot, command, room_name, user, args, data):
    cmd = command.lower().strip()
    
    # --- 1. IMAGE PM (!pmi) ---
    if cmd == "pmi":
        if len(args) < 2:
            bot.send_message(room_name, "❌ Use: `!pmi <user> <message>`")
            return True
        
        target_user = args[0]
        message_text = " ".join(args[1:])
        
        bot.send_message(room_name, f"✅ Preparing to send image PM to @{target_user}...")
        threading.Thread(target=pmi_task, args=(bot, user, target_user, message_text), daemon=True).start()
        
        return True

    # --- 2. TEXT PM (!pm) ---
    if cmd == "pm":
        if len(args) < 2:
            bot.send_message(room_name, "❌ Use: `!pm <user> <message>`")
            return True

        target_user = args[0]
        message_text = " ".join(args[1:])
        
        # Iske liye thread ki zaroorat nahi, ye fast hai
        pm_task(bot, user, target_user, message_text)
        
        return True

    return False
