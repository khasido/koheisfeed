import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin
from pathlib import Path
from xml.sax.saxutils import escape
import re
import json

LIST_URL = "https://mydramalist.com/list/3kPbQnZ4"
BASE_URL = "https://mydramalist.com"
MAX_ITEMS = 100
FEED_TITLE = "BL Updates"
FEED_DESCRIPTION = "Auto-generated feed from MyDramaList list 3kPbQnZ4"
FEED_LINK = LIST_URL

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BL-RSS-Bot/1.0)"
}

def fetch(url):
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return response.text

def parse_list_page(html):
    soup = BeautifulSoup(html, "lxml")
    show_links = []

    for li in soup.find_all("li", {"class": "list-group-item"}):
        link = li.find("a", href=re.compile(r"^/\d+"))
        if link:
            href = link.get("href")
            if href and re.match(r"^/\d+-", href):
                full = urljoin(BASE_URL, href.split("#")[0])
                if full not in show_links:
                    show_links.append(full)

    return show_links

def parse_meta_description(soup):
    """Try meta description fallback for show synopsis."""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"].strip()

    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        return og_desc["content"].strip()

    return None


def safe_text(element):
    return element.get_text(" ", strip=True) if element else None


def xml_text(value):
    return escape(str(value)) if value is not None else ""


def get_text_after_label(soup, label):
    for li in soup.find_all("li", {"class": "list-item"}):
        b_tag = li.find("b")
        if b_tag and label in b_tag.get_text(strip=True):
            full_text = li.get_text(strip=True)
            label_pos = full_text.find(label)
            if label_pos >= 0:
                return full_text[label_pos + len(label):].strip()
    return None

def get_status(soup):
    status = get_text_after_label(soup, "Status:")
    if status:
        return status.lower()
    return None


def parse_episode_count(episodes):
    if not episodes:
        return None
    match = re.search(r"(\d+)", episodes)
    if match:
        return int(match.group(1))
    return None


def parse_next_episode_number(html):
    try:
        match = re.search(r'var nextEpisodeAiring\s*=\s*({.*?});', html, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            if data:
                for key in ("episode_number", "episodeNumber", "episode"):
                    if key in data and data[key] is not None:
                        try:
                            return int(data[key])
                        except (TypeError, ValueError):
                            pass
    except:
        pass
    return None


def parse_next_episode_date(html):
    try:
        match = re.search(r'var nextEpisodeAiring\s*=\s*({.*?});', html, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            if 'released_at' in data:
                timestamp = int(data['released_at'])
                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                return dt.strftime("%b %d, %Y")
    except:
        pass
    return None


def parse_json_ld_description(soup):
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            continue

        if isinstance(data, dict):
            description = data.get("description")
            if description:
                return description.strip()

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("description"):
                    return item["description"].strip()
    return None


def parse_synopsis(soup):
    synopsis_selectors = [
        "div.show-synopsis",
        "div.storyline",
        "div.synopsis",
        "section.show__description",
        "div.content",
    ]
    for selector in synopsis_selectors:
        section = soup.select_one(selector)
        if section:
            for ui_node in section.select("a.text-primary, ul.mdl-synopsis-languages"):
                ui_node.decompose()

            paragraphs = [p.get_text(" ", strip=True) for p in section.find_all("p") if p.get_text(strip=True)]
            if paragraphs:
                return "\n\n".join(paragraphs[:2])
            text = section.get_text(" ", strip=True)
            if text:
                return text
    return None


def parse_show_page(url):
    html = fetch(url)
    soup = BeautifulSoup(html, "lxml")

    title = None
    title_el = soup.find("h1")
    if title_el:
        title = safe_text(title_el)
    else:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()

    if not title:
        title = url

    poster = None
    for selector in ("img.cover", "img[src*='mydramalist.com']", "img[src*='mydramalist']"):
        img = soup.select_one(selector)
        if img and img.get("src"):
            poster = img["src"].strip()
            break
    if poster and poster.startswith("//"):
        poster = f"https:{poster}"

    country = get_text_after_label(soup, "Country:")
    episodes = get_text_after_label(soup, "Episodes:")
    episode_count = parse_episode_count(episodes)
    air_date_str = get_text_after_label(soup, "Aired:")
    next_ep_date = parse_next_episode_date(html)
    next_ep_number = parse_next_episode_number(html)
    status = get_status(soup)

    synopsis = parse_synopsis(soup)
    if not synopsis:
        synopsis = parse_json_ld_description(soup)
    if not synopsis:
        synopsis = parse_meta_description(soup)

    countdown_str = None
    if next_ep_date:
        try:
            dt = datetime.strptime(next_ep_date, "%b %d, %Y").replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = dt - now
            if delta.days >= 0:
                countdown_str = f"Next episode in {delta.days} days"
        except:
            pass

    return {
        "title": title,
        "url": url,
        "poster": poster,
        "country": country,
        "episodes": episodes,
        "episode_count": episode_count,
        "air_date": air_date_str,
        "synopsis": synopsis,
        "next_ep_date": next_ep_date,
        "next_ep_number": next_ep_number,
        "countdown": countdown_str,
        "status": status,
    }

def format_rfc2822(date_str):
    if not date_str:
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")

    clean_date = re.split(r"\s*[-–]\s*", date_str)[0].strip()
    for fmt in ("%b %d, %Y", "%b %Y", "%Y"):
        try:
            dt = datetime.strptime(clean_date, fmt)
            dt = dt.replace(tzinfo=timezone.utc)
            return dt.strftime("%a, %d %b %Y %H:%M:%S %z")
        except:
            continue

    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")

def parse_sort_date(date_str):
    if not date_str:
        return None

    clean_date = re.split(r"\s*[-–]\s*", date_str)[0].strip()
    for fmt in ("%b %d, %Y", "%b %Y", "%Y"):
        try:
            dt = datetime.strptime(clean_date, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except:
            continue

    return None

def image_mime_type(url):
    url = url.lower()
    if url.endswith(".png"):
        return "image/png"
    if url.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


def build_rss(items):
    base_dt = datetime.now(timezone.utc)
    now = base_dt.strftime("%a, %d %b %Y %H:%M:%S %z")
    rss_items = []

    for it in items:
        desc_lines = []

        if it["poster"]:
            desc_lines.append(
                f"<p><img src=\"{it['poster']}\" alt=\"{it['title']} poster\" style=\"width:100%;max-width:700px;height:auto;border:0;display:block;margin:0 0 1em;\" /></p>"
            )

        if it["country"]:
            desc_lines.append(
                f"<p style=\"margin:0 0 0.6em 0;color:#333;line-height:1.5;\"><strong>Country:</strong> {escape(it['country'])}</p>"
            )

        if it.get("episode_count") is not None:
            desc_lines.append(
                f"<p style=\"margin:0 0 0.6em 0;color:#333;line-height:1.5;\"><strong>Total Episodes:</strong> {it['episode_count']}</p>"
            )

        next_episode_line = None
        if it.get("next_ep_date"):
            episode_number = it.get("next_ep_number")
            total_episodes = it.get("episode_count")
            if episode_number and total_episodes:
                next_episode_line = (
                    f"<strong>Next Episode:</strong> {episode_number} of {total_episodes} {escape(it['next_ep_date'])}"
                )
            else:
                next_episode_line = (
                    f"<strong>Next Episode:</strong> {escape(it['next_ep_date'])}"
                )

        if next_episode_line:
            desc_lines.append(
                f"<p style=\"margin:0 0 0.6em 0;color:#333;line-height:1.5;\">{next_episode_line}</p>"
            )

        if it["synopsis"]:
            desc_lines.append(
                f"<p style=\"margin:0 0 0.6em 0;color:#333;line-height:1.5;\">{escape(it['synopsis']).replace('\n\n', '<br><br>')}</p>"
            )

        desc_lines.append(
            f"<p style=\"margin:0;color:#555;line-height:1.5;\"><a href=\"{it['url']}\" style=\"color:#1a0dab;\">View on MyDramaList</a></p>"
        )

        description_html = "\n".join(desc_lines)

        enclosure_tag = ""
        if it["poster"]:
            mime_type = image_mime_type(it["poster"])
            enclosure_tag = (
                f"\n    <enclosure url=\"{it['poster']}\" "
                f"type=\"{mime_type}\" length=\"0\" />"
            )

        # assign a unique pubDate per item (decrementing by one second)
        idx = items.index(it)
        item_dt = base_dt - timedelta(seconds=idx)
        pub_date = item_dt.strftime("%a, %d %b %Y %H:%M:%S %z")
        # use a stable guid per show (based on its URL) so we can update existing posts
        guid = hashlib.sha256(it['url'].encode('utf-8')).hexdigest()
        item_xml = (
            "  <item>\n"
            f"    <title>{xml_text(it['title'])}</title>\n"
            f"    <link>{xml_text(it['url'])}</link>\n"
            f"    <guid isPermaLink=\"false\">{guid}</guid>\n"
            f"    <pubDate>{xml_text(pub_date)}</pubDate>\n"
            f"    <description><![CDATA[{description_html}]]></description>\n"
            f"    <content:encoded><![CDATA[{description_html}]]></content:encoded>\n"
            f"{enclosure_tag}\n"
            "  </item>"
        )
        rss_items.append(item_xml)

    rss_body = "\n".join(rss_items)
    channel_header = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<rss version=\"2.0\" xmlns:media=\"http://search.yahoo.com/mrss/\" xmlns:content=\"http://purl.org/rss/1.0/modules/content/\">\n"
        "<channel>\n"
        f"  <title>{FEED_TITLE}</title>\n"
        f"  <link>{FEED_LINK}</link>\n"
        f"  <description>{FEED_DESCRIPTION}</description>\n"
        "  <language>en-US</language>\n"
        "  <generator>BL-RSS Auto Generator</generator>\n"
        f"  <lastBuildDate>{now}</lastBuildDate>\n"
    )

    return f"{channel_header}{rss_body}\n</channel>\n</rss>\n"

def main():
    list_html = fetch(LIST_URL)
    show_urls = parse_list_page(list_html)[:MAX_ITEMS]

    items = []
    for url in show_urls:
        try:
            print(f"Parsing {url}")
            data = parse_show_page(url)

            status = data.get("status", "")
            if status not in ["completed", "finished", "ended"]:
                items.append(data)

        except Exception as exc:
            print(f"Error parsing {url}: {exc}")

    items.sort(
        key=lambda item: parse_sort_date(item['next_ep_date'])
        or parse_sort_date(item['air_date'])
        or datetime.max.replace(tzinfo=timezone.utc),
        reverse=True
    )

    rss_xml = build_rss(items)
    Path("feed.xml").write_text(rss_xml, encoding="utf-8")
    print("feed.xml updated.")
    # try posting to Discord if webhook is configured
    try:
        import os
        if os.environ.get("DISCORD_WEBHOOK_URL"):
            try:
                from post_to_discord import post_new_items
                post_new_items("feed.xml")
            except Exception as exc:
                print(f"Error posting to Discord: {exc}")
    except Exception:
        pass

if __name__ == "__main__":
    main()

