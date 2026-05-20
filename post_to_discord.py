# post_to_discord.py
import requests
import random
from datetime import datetime, timezone, timedelta
from rss_parser import parse_feed_items
from image_utils import apply_cinematic_overlay

SOFT_EMOJIS = ["🌙", "💫", "⭐", "🌸", "🕊️", "✨"]
MINT_GREEN = 0xA8F0C6
PALE_YELLOW = 0xFFF4B8
WEEKLY_PASTEL = 0xD9E8FF

def shorten(text, limit=200):
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


from image_utils import apply_cinematic_overlay

def build_embed(item):
    emoji = random.choice(SOFT_EMOJIS)
    title = f"✦ {item['title']} {emoji} ✦"

    # Build cinematic card
    card_path = apply_cinematic_overlay(item)

    embed = {
        "title": title,
        "url": item["url"],
        "color": MINT_GREEN,
        "description": "",  # No metadata here — it's on the image
        "image": {"url": card_path},
        "footer": {"text": "Updated automatically • Wei Wei Feed"}
    }

    return embed

# -----------------------------
# Discord API helpers
# -----------------------------

def discord_post(webhook_url, payload):
    r = requests.post(webhook_url, json=payload)

    print("STATUS:", r.status_code)
    print("RESPONSE:", r.text)

    # Discord returns 204 No Content unless ?wait=true is used
    if r.status_code in (200, 204):
        try:
            data = r.json()
            return data.get("id")
        except:
            return None

    return None

def discord_edit(webhook_url, message_id, payload):
    url = webhook_url + f"/messages/{message_id}"
    requests.patch(url, json=payload)

def discord_delete(webhook_url, message_id):
    url = webhook_url + f"/messages/{message_id}"
    requests.delete(url)

# -----------------------------
# Main posting logic
# -----------------------------

def post_or_update(item, webhook_url, message_id):
    payload = {
        "embeds": [build_embed(item)],
        "components": [
            {
                "type": 1,
                "components": [
                    {"type": 2, "style": 1, "label": "🔔 Track Airing", "custom_id": "track_airing"},
                    {"type": 2, "style": 1, "label": "📩 Track Finale", "custom_id": "track_finale"}
                ]
            }
        ]
    }

    print("WEBHOOK URL:", webhook_url)
    print("PAYLOAD:", payload)

    if message_id:
        # Delete + repost to reorder correctly
        discord_delete(webhook_url, message_id)
        new_id = discord_post(webhook_url, payload)
        return new_id

    # First-time posting
    new_id = discord_post(webhook_url, payload)
    return new_id
