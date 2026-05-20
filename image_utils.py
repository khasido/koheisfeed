from PIL import Image, ImageDraw
import requests
from io import BytesIO
import os
import hashlib

CACHE_DIR = "cache/posters"

def ensure_cache_dir():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_filename(url):
    """
    Creates a stable filename based on the poster URL.
    """
    h = hashlib.md5(url.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{h}.jpg")

def apply_black_gradient_overlay(poster_url):
    """
    Returns a cached gradient poster if it exists.
    Otherwise downloads the poster, applies a black→transparent gradient,
    caches it, and returns the cached path.
    """
    ensure_cache_dir()
    cached_path = get_cache_filename(poster_url)

    # If cached version exists, return it immediately
    if os.path.exists(cached_path):
        return cached_path

    # Download poster
    response = requests.get(poster_url, timeout=30)
    response.raise_for_status()
    poster = Image.open(BytesIO(response.content)).convert("RGBA")

    width, height = poster.size

    # Create gradient mask
    gradient = Image.new("L", (width, height), color=0)
    draw = ImageDraw.Draw(gradient)

    # Black at bottom → transparent at top
    for y in range(height):
        opacity = int(255 * (y / height))  # 0 at top, 255 at bottom
        draw.line((0, y, width, y), fill=opacity)

    # Apply gradient as alpha mask
    black_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    black_overlay.putalpha(gradient)

    final = Image.alpha_composite(poster, black_overlay)

    # Save to cache
    final.convert("RGB").save(cached_path, format="JPEG", quality=95)

    return cached_path
