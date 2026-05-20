# update.py
import os
from pathlib import Path
from datetime import datetime

from tmdb_fetcher import fetch_bl_items, fetch_gl_items
from rss_builder import build_rss
from state_manager import (
    load_state, save_state, has_changed,
    update_state_entry, get_message_id, remove_entry
)
from post_to_discord import post_or_update

print(">>> UPDATE.PY STARTED")

PRIORITY_COUNTRIES = ["TH", "JP", "KR", "CN", "TW", "PH", "VN", "HK", "MY"]

def sort_key(item):
    # Priority: 0 = prioritized country, 1 = others
    priority = 0 if item["country_code"] in PRIORITY_COUNTRIES else 1

    # Parse next episode date
    if item["next_ep_date"]:
        try:
            dt = datetime.strptime(item["next_ep_date"], "%b %d, %Y")
        except:
            dt = datetime.max
    else:
        dt = datetime.max

    return (priority, dt, item["title"].lower())

def process_feed(items, state, webhook_url, state_path):
    print(">>> PROCESSING FEED, ITEMS:", len(items))
# HARD FILTER: remove anything that should not be posted
    filtered = []
    for it in items:
        # Must have category
        if it["category"] not in ("bl", "gl"):
            continue

        # Must have country
        if not it["country_code"] or it["country_code"] not in PRIORITY_COUNTRIES:
            continue

        # Must have next episode date (TV) or future release date (movie)
        if it["status"] == "ended":
            continue

        # Must have next episode date
        if not it["next_ep_date"]:
            continue

        filtered.append(it)

    items = filtered
    print(">>> PROCESSING FEED, ITEMS AFTER FILTER:", len(items))
    
    items.sort(key=sort_key)

    # Track which IDs still exist
    current_ids = set(str(it["id"]) for it in items)

    # Remove old entries
    for old_id in list(state["items"].keys()):
        if old_id not in current_ids:
            msg_id = state["items"][old_id].get("discord_message_id")
            if msg_id:
                from post_to_discord import discord_delete
                discord_delete(webhook_url, msg_id)
            remove_entry(state, old_id)

    # Process each item
    for it in items:
        sid = str(it["id"])
        changed = has_changed(state, it)
        msg_id = get_message_id(state, sid)

        if msg_id is None or changed:
            print(">>> POST_OR_UPDATE CALLED FOR:", it["title"])
            new_id = post_or_update(it, webhook_url, msg_id)
            update_state_entry(state, it, new_id)

    save_state(state_path, state)

def main():
    bl_webhook = os.getenv("DISCORD_WEBHOOK_BL")
    gl_webhook = os.getenv("DISCORD_WEBHOOK_GL")

    bl_items = fetch_bl_items()
    gl_items = fetch_gl_items()

    print(">>> BL ITEMS:", len(bl_items))
    print(">>> GL ITEMS:", len(gl_items))

    bl_state = load_state("state_bl.json")
    gl_state = load_state("state_gl.json")

    process_feed(bl_items, bl_state, bl_webhook, "state_bl.json")
    process_feed(gl_items, gl_state, gl_webhook, "state_gl.json")

if __name__ == "__main__":
    main()


