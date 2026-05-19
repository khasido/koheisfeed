# update.py
from pathlib import Path
import json
import os
from datetime import datetime

from tmdb_fetcher import fetch_bl_items, fetch_gl_items
from rss_builder import build_rss
from state_manager import load_state, save_state, has_changed

def load_blacklist():
    path = Path("data/blacklist.json")
    if not path.exists():
        return {"BL": [], "GL": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "BL": [t.lower() for t in data.get("BL", [])],
        "GL": [t.lower() for t in data.get("GL", [])]
    }

def sort_key(item):
    if item["next_ep_date"]:
        try:
            dt = datetime.strptime(item["next_ep_date"], "%b %d, %Y")
        except:
            dt = datetime.max
    else:
        dt = datetime.max
    return (dt, item["title"].lower())

def main():
    blacklist = load_blacklist()

    bl_items_raw = fetch_bl_items()
    gl_items_raw = fetch_gl_items()

    bl_items = [
        it for it in bl_items_raw
        if it["title"].lower() not in blacklist["BL"]
    ]
    gl_items = [
        it for it in gl_items_raw
        if it["title"].lower() not in blacklist["GL"]
    ]

    bl_items.sort(key=sort_key)
    gl_items.sort(key=sort_key)

    bl_state = load_state("state_bl.json")
    gl_state = load_state("state_gl.json")

    changed_bl = [it for it in bl_items if has_changed(bl_state, it)]
    changed_gl = [it for it in gl_items if has_changed(gl_state, it)]

    rss_bl = build_rss(
        bl_items,
        title="BL Updates (TMDB)",
        description="Auto-generated BL feed from TMDB",
        link="https://www.themoviedb.org"
    )
    rss_gl = build_rss(
        gl_items,
        title="GL Updates (TMDB)",
        description="Auto-generated GL feed from TMDB",
        link="https://www.themoviedb.org"
    )

    Path("feed_bl.xml").write_text(rss_bl, encoding="utf-8")
    Path("feed_gl.xml").write_text(rss_gl, encoding="utf-8")

    save_state("state_bl.json", bl_state)
    save_state("state_gl.json", gl_state)

    try:
        bl_webhook = os.environ.get("DISCORD_WEBHOOK_BL")
        gl_webhook = os.environ.get("DISCORD_WEBHOOK_GL")

        if changed_bl and bl_webhook:
                post_new_items("feed_bl.xml", bl_webhook)

        if changed_gl and gl_webhook:
                post_new_items("feed_gl.xml", gl_webhook)

    except Exception as exc:
        print(f"Error posting to Discord: {exc}")

if __name__ == "__main__":
    main()
