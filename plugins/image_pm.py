import threading
import random
import re
import io
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# Local imports
import utils
import db

# --- 🎨 DESIGN PRESETS (Yahan aur designs add kar sakte ho) ---
THEMES = [
    {
        "name": "Neon Purple",
        "bg_type": "gradient",
        "colors": [(43, 16, 80), (17, 24, 39)], # Dark Purple Gradient
        "font": "fonts/arial.ttf",
        "text_color": "#ffffff",
        "effect": "glow",
        "effect_color": "#a855f7" # Purple Glow
    },
    {
        "name": "Golden Royal",
        "bg_type": "solid",
        "colors": [(20, 18, 24)], # Solid Dark
        "font": "fonts/times.ttf",
        "text_color": "#fbbf24", # Gold
        "effect": "shadow",
        "effect_color": "#000000"
    },
    {
        "name": "Ocean Blue",
        "bg_type": "gradient",
        "colors": [(14, 58, 86), (17, 24, 39)], # Deep Blue Gradient
        "font": "fonts/verdana.ttf",
        "text_color": "#ffffff",
        "effect": "outline",
        "effect_color": "#0ea5e9" # Sky Blue Outline
    },
    {
        "name": "Pastel Dream",
        "bg_type": "solid",
        "colors": [(224, 231, 255)], # Light Lavender
        "font": "fonts/arial.ttf",
        "text_color": "#1e293b", # Dark Blue Text
        "effect": "none",
        "effect_color": ""
    }
]

# Emoji Font (Agar nahi hai to text dikhega)
EMOJI_FONT = "fonts/NotoColorEmoji.ttf"

def setup(bot):
    bot.log("🎨 Text-to-Image PM Plugin Loaded")

# --- 🧠 HELPER: AUTO TEXT WRAP ---
def text_wrap(text, font, max_width):
    """Lambi lines ko multiple lines me todta hai"""
    lines = []
    if font.getlength(text) <= max_width:
        lines.append(text)
    else:
        words = text.split(' ')
        i = 0
        while i < len(words):
            line = ''
            while i < len(words) and font.getlength(line + words[i]) <= max_width:
                line = line + words[i] + " "
                i += 1
            if not line:
                line = words[i]
                i += 1
            lines.append(line.strip())
    return lines

# --- 🖼️ IMAGE GENERATION ENGINE ---
def generate_image(sender, text):
    W, H = 512, 512
    
    # 1. Random Theme Chuno
    theme = random.choice(THEMES)
    
    # Canvas
    canvas = Image.new("RGB", (W, H))
    
    # 2. Background
    if theme['bg_type'] == 'gradient':
        utils.draw_gradient_bg(canvas, theme['colors'][0], theme['colors'][1])
    else:
        draw_temp = ImageDraw.Draw(canvas)
        draw_temp.rectangle([0, 0, W, H], fill=theme['colors'][0])

    draw = ImageDraw.Draw(canvas)
    
    # 3. Fonts
    try:
        main_font = ImageFont.truetype(theme['font'], 48)
    except:
        main_font = ImageFont.load_default()
        
    try:
        emoji_font = ImageFont.truetype(EMOJI_FONT, 42)
    except:
        emoji_font = main_font # Fallback
    
    # 4. Auto-wrap text
    lines = text_wrap(text, main_font, W - 80) # 40px margin
    
    # Vertical Centering
    total_height = sum([main_font.getbbox(line)[3] for line in lines])
    y_start = (H - total_height) // 2
    
    # 5. Draw Text (with effects)
    for i, line in enumerate(lines):
        x = W / 2
        y = y_start + (i * 55) # Line spacing
        
        # Effect Logic
        if theme['effect'] == 'shadow':
            draw.text((x+3, y+3), line, font=main_font, fill=theme['effect_color'], anchor="mm")
        elif theme['effect'] == 'outline':
            draw.text((x-2, y-2), line, font=main_font, fill=theme['effect_color'], anchor="mm")
            draw.text((x+2, y-2), line, font=main_font, fill=theme['effect_color'], anchor="mm")
            draw.text((x-2, y+2), line, font=main_font, fill=theme['effect_color'], anchor="mm")
            draw.text((x+2, y+2), line, font=main_font, fill=theme['effect_color'], anchor="mm")
        
        # Main Text
        draw.text((x, y), line, font=main_font, fill=theme['text_color'], anchor="mm")
        
        # Emoji Support (Overlay)
        # (This is a simplified approach)
        # A more robust emoji system would parse characters, but this works for many cases.
        try:
            draw.text((x, y), line, font=emoji_font, fill=(255,255,255,255), anchor="mm", embedded_color=True)
        except: pass

    # 6. Footer
    footer_font = utils.get_font("arial.ttf", 16)
    draw.text((W - 30, H - 30), f"Sent by: @{sender}", font=footer_font, fill="#ffffff80", anchor="rs")
    
    # Glow effect (Applied to whole image)
    if theme['effect'] == 'glow':
        glow = Image.new("RGB", (W, H), theme['effect_color'])
        mask = canvas.convert("L").point(lambda i: i * 0.5) # Create a faint mask
        canvas.paste(glow, (0,0), mask.filter(ImageFilter.GaussianBlur(15)))
        # Re-draw text to make it sharp
        for i, line in enumerate(lines):
            x = W / 2
            y = y_start + (i * 55)
            draw.text((x, y), line, font=main_font, fill=theme['text_color'], anchor="mm")

    return canvas

# --- 🧠 BACKGROUND WORKER ---
def process_image_task(bot, sender, target, message):
    try:
        # 1. Generate Image
        img = generate_image(sender, message)
        
        # 2. Upload
        url = utils.upload_image(img)
        
        # 3. Send PM
        if url:
            bot.send_pm_message(target, f"📩 You have a new image message from @{sender}:")
            bot.send_pm_image(target, url)
        else:
            bot.send_message(sender, "❌ Failed to generate or send image.")
            
    except Exception as e:
        print(f"Image PM Error: {e}")
    finally:
        gc.collect()

# --- 🚀 COMMAND HANDLER ---
def handle_command(bot, command, room_name, user, args, data):
    # This command works based on the full text, not just the command part
    full_text = f"!{command} {' '.join(args)}"
    
    # Use Regex to parse !img<target> message
    match = re.match(r'^!img<([^>]+)>(.*)', full_text, re.IGNORECASE)
    
    if match:
        target_user = match.group(1).strip()
        message = match.group(2).strip()
        
        if not target_user or not message:
            bot.send_message(room_name, "❌ Invalid format. Use: `!img<username> your message`")
            return True
            
        bot.send_message(room_name, f"✅ Sending image to @{target_user}'s PM...")
        
        # Start in background thread
        threading.Thread(target=process_image_task, args=(bot, user, target_user, message), daemon=True).start()
        
        return True

    return False
