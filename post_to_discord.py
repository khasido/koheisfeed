import json
import requests
import random
import os
from datetime import datetime, timezone, timedelta

SOFT_EMOJIS = ["🌙", "💫", "⭐", "🌸", "🕊️", "✨"]

MINT_GREEN = 0xA8F0C6      # airing
PALE_YELLOW = 0xFFF4B8     # upcoming / no date
WEEKLY_PASTEL = 0xD9E8FF   # summary card pastel


def center(text):
    """Center-align text visually (Discord does not support true centering)."""
    return text


def clip_synopsis(text, limit=450):
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def build_embed(item):
    title = item["title"]
    url = item["url"]
    poster = item["poster"]
    country = item["country"]
    ep_total = item["episode_count"]
    next_ep = item["next_ep_number"]
    next_date = item["next_ep_date"]
    synopsis = clip_synopsis(item["synopsis"])
    status = item["status"]

    # Determine color
    if status in ["airing", "currently airing"]:
        color = MINT_GREEN
    else:
        color = PALE_YELLOW

    # Title: centered + soft emoji (no countdown)
    emoji = random.choice(SOFT_EMOJIS)
    embed_title = center(f"{title} {emoji}")

    # Country tag
    flag = {
        "thailand": "🇹🇭",
        "japan": "🇯🇵",
        "china": "🇨🇳",
        "south korea": "🇰🇷",
        "taiwan": "🇹🇼",
    }.get(country.lower() if country else "", "🌍")

    country_tag = center(f"{flag} {country[:2].upper()} • {status.title()}") if country else ""

    # Build fields (these appear to the right of the poster)
    fields = []

    if country:
        fields.append({
            "name": "🌍 Country",
            "value": center(country),
            "inline": False
        })

    if ep_total:
        fields.append({
            "name": "🎞️ Episodes",
            "value": center(f"{ep_total} total"),
            "inline": False
        })

    if next_ep and next_date:
        fields.append({
            "name": "📅 Next Episode",
            "value": center(f"Ep {next_ep} — {next_date}"),
            "inline": False
        })

    if next_date:
        try:
            dt = datetime.strptime(next_date, "%b %d, %Y").replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            days = (dt - now).days
            if days >= 0:
                fields.append({
                    "name": "⏳ Airs In",
                    "value": center(f"{days} days"),
                    "inline": False
                })
        except:
            pass

    fields.append({
        "name": "📡 Status",
        "value": center(status.title()),
        "inline": False
    })

    # Build embed (movie-card layout)
    embed = {
        "title": embed_title,
        "description": center(synopsis) if synopsis else "",
        "color": color,
        "thumbnail": {"url": poster} if poster else {},  # poster inside main embed box
        "fields": fields,
        "footer": {"text": "🔗 View on MDL"},
        "url": url
    }

    return embed


def build_weekly_summary(items):
    """Create the weekly grouped embed."""
    upcoming = []

    now = datetime.now(timezone.utc)
    week_later = now + timedelta(days=7)

    for it in items:
        if not it["next_ep_date"]:
            continue
        try:
            dt = datetime.strptime(it["next_ep_date"], "%b %d, %Y").replace(tzinfo=timezone.utc)
            if now <= dt <= week_later:
                upcoming.append((dt, it))
        except:
            continue

    if not upcoming:
        return None

    upcoming.sort(key=lambda x: (x[0], x[1]["title"].lower()))

    lines = ["📅 **Episodes Airing This Week**\n"]

    current_day = None
    for dt, it in upcoming:
        day_str = dt.strftime("%b %d")
        if day_str != current_day:
            emoji = random.choice(SOFT_EMOJIS)
            lines.append(f"\n{emoji} **{day_str}**")
            current_day = day_str

        ep = it["next_ep_number"]
        lines.append(f"• {it['title']} — Ep {ep}")

    embed = {
        "title": center("Weekly Airing Summary"),
        "description": "\n".join(lines),
        "color": WEEKLY_PASTEL,
        "footer": {"text": "🔗 View on MDL"}
    }

    return embed


def post_new_items(feed_path):
    from rss_parser import parse_feed_items

    with open(feed_path, "r", encoding="utf-8") as f:
        xml = f.read()

    items = parse_feed_items(xml)

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("No webhook URL set.")
        return

    # Post each embed
    for item in items:
        embed = build_embed(item)
        payload = {
            "embeds": [embed],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 1,
                            "label": "🔔 Track Airing",
                            "custom_id": "track_airing"
                        },
                        {
                            "type": 2,
                            "style": 1,
                            "label": "📩 Track Finale",
                            "custom_id": "track_finale"
                        }
                    ]
                }
            ]
        }
        requests.post(webhook_url, json=payload)

    # Weekly summary
    summary = build_weekly_summary(items)
    if summary:
        requests.post(webhook_url, json={"embeds": [summary]})
