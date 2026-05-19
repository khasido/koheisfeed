import os
import json
import time
import re
from pathlib import Path
from bs4 import BeautifulSoup
import requests

STATE_DEFAULT = "posted.json"


def _extract_first_image(item):
    # try enclosure
    enc = item.find("enclosure")
    if enc and enc.get("url"):
        return enc.get("url")
    # look into description/content for first img
    for tag in ("content:encoded", "description"):
        node = item.find(tag)
        if node and node.string:
            m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', node.string)
            if m:
                return m.group(1)
    return None


def _html_to_text(html):
    # strip tags roughly
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_meta_from_html(html, label):
    # look for <strong>Label:</strong> value</p>
    pat = rf"<strong>{re.escape(label)}:</strong>\s*(.*?)</p>"
    m = re.search(pat, html, flags=re.I | re.S)
    if m:
        return _html_to_text(m.group(1))
    return None


def post_new_items(feed_path="feed.xml", state_path=STATE_DEFAULT, webhook_env="DISCORD_WEBHOOK_URL", sleep_seconds=1):
    webhook = os.environ.get(webhook_env)
    if not webhook:
        print(f"No webhook set in env {webhook_env}; skipping Discord posts.")
        return

    feed_file = Path(feed_path)
    if not feed_file.exists():
        print(f"Feed file {feed_path} not found; nothing to post.")
        return

    state_file = Path(state_path)
    if state_file.exists():
        try:
            posted = set(json.loads(state_file.read_text(encoding="utf-8")))
        except Exception:
            posted = set()
    else:
        posted = set()

    soup = BeautifulSoup(feed_file.read_text(encoding="utf-8"), "lxml-xml")
    items = soup.find_all("item")
    # post older first so channel receives chronological order
    items = list(reversed(items))

    new_guids = []
    for item in items:
        guid = item.guid.string.strip() if item.guid and item.guid.string else None
        if not guid:
            # fallback to url+pubDate
            link = item.link.string if item.link and item.link.string else ""
            pub = item.pubDate.string if item.pubDate and item.pubDate.string else ""
            guid = f"{link}|{pub}"

        if guid in posted:
            continue

        title = item.title.string if item.title and item.title.string else ""
        link = item.link.string if item.link and item.link.string else ""
        description_html = item.find("description").string if item.find("description") and item.find("description").string else ""
        description_text = _html_to_text(description_html)[:2048]
        image = _extract_first_image(item)

        # extract metadata fields
        country = _extract_meta_from_html(description_html, "Country") or ""
        total_eps = _extract_meta_from_html(description_html, "Total Episodes") or ""
        next_ep = _extract_meta_from_html(description_html, "Next Episode") or ""

        embed = {
            "title": title,
            "url": link,
            "description": description_text,
            "fields": [],
        }
        if image:
            embed["image"] = {"url": image}

        if country:
            embed["fields"].append({"name": "Country", "value": country, "inline": True})
        if total_eps:
            embed["fields"].append({"name": "Total Episodes", "value": total_eps, "inline": True})
        if next_ep:
            embed["fields"].append({"name": "Next Episode", "value": next_ep, "inline": True})

        payload = {"embeds": [embed]}

        try:
            r = requests.post(webhook, json=payload, timeout=10)
            if r.status_code >= 200 and r.status_code < 300:
                print(f"Posted: {title}")
                posted.add(guid)
                new_guids.append(guid)
            else:
                print(f"Failed to post {title}: {r.status_code} {r.text}")
                # stop on failure to avoid hitting rate limits
                break
        except Exception as exc:
            print(f"Error posting {title}: {exc}")
            break

        time.sleep(sleep_seconds)

    # persist state
    try:
        state_file.write_text(json.dumps(list(posted)), encoding="utf-8")
    except Exception as exc:
        print(f"Error saving state file: {exc}")

    if new_guids:
        print(f"Posted {len(new_guids)} new items to Discord.")
    else:
        print("No new items to post.")


if __name__ == "__main__":
    post_new_items()
