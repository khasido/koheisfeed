# image_utils.py — CINEMATIC POSTER BUILDER
import os
import textwrap
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

CACHE_DIR = "cache/posters"
os.makedirs(CACHE_DIR, exist_ok=True)

# Bold display font (Montserrat-like)
FONT_TITLE = ImageFont.truetype("fonts/Montserrat-Bold.ttf", 48)
FONT_META = ImageFont.truetype("fonts/Montserrat-SemiBold.ttf", 32)
FONT_DESC = ImageFont.truetype("fonts/Montserrat-Regular.ttf", 28)

def get_cache_filename(url):
    import hashlib
    h = hashlib.md5(url.encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{h}.jpg")

def apply_cinematic_overlay(item):
    """
    Builds a full cinematic card:
    - Poster
    - Gradient
    - Title (centered, bold)
    - Metadata (centered)
    - Justified clipped description
    """

    poster_url = item["poster"]
    cached_path = get_cache_filename(poster_url)

    if os.path.exists(cached_path):
        return cached_path

    # Download poster
    try:
        r = requests.get(poster_url, timeout=10)
        r.raise_for_status()
        poster = Image.open(BytesIO(r.content)).convert("RGBA")
    except:
        return poster_url

    W, H = poster.size

    # Create gradient overlay
    gradient = Image.new("L", (W, H), 0)
    draw_g = ImageDraw.Draw(gradient)
    for y in range(H):
        opacity = int(255 * (y / H))
        draw_g.line((0, y, W, y), fill=opacity)

    black_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    black_overlay.putalpha(gradient)

    final = Image.alpha_composite(poster, black_overlay)
    draw = ImageDraw.Draw(final)

    # -----------------------------
    # TEXT BLOCKS
    # -----------------------------

    # Title
    title = f"✦ {item['title']} ✦"

    # Metadata
    meta1 = f"{item['country_code']} • {item['category']} • {item['status'].capitalize()}"
    meta2 = f"Ep {item['episode_count'] or '—'} • Next {item['next_ep_date'] or '—'}"

    # Description (clipped + justified)
    desc_raw = item.get("overview", "")
    desc_clipped = desc_raw[:350].rsplit(" ", 1)[0] + "…"

    # Wrap description to ~50 chars per line
    wrapped = textwrap.fill(desc_clipped, width=50)

    # -----------------------------
    # POSITIONING
    # -----------------------------
    # We draw text starting from 70% down the image
    base_y = int(H * 0.70)

    # Title (centered)
    tw, th = draw.textsize(title, font=FONT_TITLE)
    draw.text(((W - tw) / 2, base_y), title, font=FONT_TITLE, fill="white")

    # Metadata line 1
    y2 = base_y + th + 10
    mw1, mh1 = draw.textsize(meta1, font=FONT_META)
    draw.text(((W - mw1) / 2, y2), meta1, font=FONT_META, fill="white")

    # Metadata line 2
    y3 = y2 + mh1 + 5
    mw2, mh2 = draw.textsize(meta2, font=FONT_META)
    draw.text(((W - mw2) / 2, y3), meta2, font=FONT_META, fill="white")

    # Description (justified block)
    y4 = y3 + mh2 + 20
    for line in wrapped.split("\n"):
        lw, lh = draw.textsize(line, font=FONT_DESC)
        draw.text(((W - lw) / 2, y4), line, font=FONT_DESC, fill="white")
        y4 += lh + 4

    # Save final card
    final.convert("RGB").save(cached_path, format="JPEG", quality=95)
    return cached_path
