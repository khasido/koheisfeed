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
            raw = json.loads(state_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                posted = raw
            elif isinstance(raw, list):
                # upgrade older list format -> dict with None message ids
                posted = {g: None for g in raw}
            else:
                posted = {}
        except Exception:
            posted = {}
    else:
        posted = {}

    soup = BeautifulSoup(feed_file.read_text(encoding="utf-8"), "lxml-xml")
    items = soup.find_all("item")
    # post older first so channel receives chronological order
    items = list(reversed(items))


    # parse webhook id/token for edit endpoint
    m = re.search(r"https?://[^/]+/api/webhooks/([^/]+)/([^/?#]+)", webhook)
    if not m:
        print("Webhook URL not recognized; must be a full Discord webhook URL.")
        return
    wh_id, wh_token = m.group(1), m.group(2)

    new_guids = []
    for item in items:
        guid = item.guid.string.strip() if item.guid and item.guid.string else None
        if not guid:
            link = item.link.string if item.link and item.link.string else ""
            pub = item.pubDate.string if item.pubDate and item.pubDate.string else ""
            guid = f"{link}|{pub}"

        existing_msg_id = posted.get(guid)

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
            max_retries = 3
            attempt = 0
            success = False

            if not existing_msg_id:
                while attempt < max_retries and not success:
                    r = requests.post(webhook, json=payload, timeout=10)
                    if 200 <= r.status_code < 300:
                        data = r.json()
                        msg_id = str(data.get("id"))
                        print(f"Posted: {title} -> message {msg_id}")
                        posted[guid] = msg_id
                        new_guids.append(guid)
                        success = True
                    elif r.status_code == 429:
                        retry_after = None
                        try:
                            retry_after = int(r.headers.get("Retry-After") or (r.json().get("retry_after") if r.text else None))
                        except Exception:
                            retry_after = None
                        wait = (retry_after or (2 ** attempt))
                        print(f"Rate limited posting {title}; sleeping {wait}s and retrying...")
                        time.sleep(wait)
                        attempt += 1
                    else:
                        print(f"Failed to post {title}: {r.status_code} {r.text}")
                        break
            else:
                edit_url = f"https://discord.com/api/webhooks/{wh_id}/{wh_token}/messages/{existing_msg_id}"
                while attempt < max_retries and not success:
                    r = requests.patch(edit_url, json={"embeds": [embed]}, timeout=10)
                    if 200 <= r.status_code < 300:
                        print(f"Updated: {title} (message {existing_msg_id})")
                        success = True
                    elif r.status_code == 429:
                        retry_after = None
                        try:
                            retry_after = int(r.headers.get("Retry-After") or (r.json().get("retry_after") if r.text else None))
                        except Exception:
                            retry_after = None
                        wait = (retry_after or (2 ** attempt))
                        print(f"Rate limited updating {title}; sleeping {wait}s and retrying...")
                        time.sleep(wait)
                        attempt += 1
                    else:
                        print(f"Failed to update {title}: {r.status_code} {r.text}")
                        # if update failed (deleted message?), try reposting once
                        try:
                            r2 = requests.post(webhook, json=payload, timeout=10)
                            if 200 <= r2.status_code < 300:
                                data = r2.json()
                                msg_id = str(data.get("id"))
                                print(f"Reposted: {title} -> message {msg_id}")
                                posted[guid] = msg_id
                                new_guids.append(guid)
                                success = True
                            else:
                                print(f"Repost failed: {r2.status_code} {r2.text}")
                        except Exception as exc:
                            print(f"Error reposting {title}: {exc}")
                        break
        except Exception as exc:
            print(f"Error posting/updating {title}: {exc}")
            # continue to next item instead of breaking out
            continue

        time.sleep(sleep_seconds)

    # persist state
    try:
        state_file.write_text(json.dumps(posted, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"Error saving state file: {exc}")

    if new_guids:
        print(f"Posted {len(new_guids)} new items to Discord.")
    else:
        print("No new items to post.")


if __name__ == "__main__":
    post_new_items()
