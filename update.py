import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urljoin
from pathlib import Path
import re
import json

LIST_URL = "https://mydramalist.com/list/3kPbQnZ4"
BASE_URL = "https://mydramalist.com"
MAX_ITEMS = 100
FEED_TITLE = "Ongoing and Upcoming BLs"
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
    """Return absolute show URLs from the MDL list page."""
    soup = BeautifulSoup(html, "lxml")
    show_links = []

    # Find all list items (each li.list-group-item contains one show)
    for li in soup.find_all("li", {"class": "list-group-item"}):
        # Get the show link from the cover image or title
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


def get_text_after_label(soup, label):
    """Extract text after a labeled field in list items."""
    for li in soup.find_all("li", {"class": "list-item"}):
        b_tag = li.find("b")
        if b_tag and label in b_tag.get_text(strip=True):
            # Get all text in the li and remove the label part
            full_text = li.get_text(strip=True)
            label_pos = full_text.find(label)
            if label_pos >= 0:
                text_after = full_text[label_pos + len(label):].strip()
                return text_after
    return None

def parse_next_episode_date(html):
    """Extract next episode air date from JavaScript variable in the page."""
    try:
        match = re.search(r'var nextEpisodeAiring\s*=\s*({.*?});', html, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            if 'released_at' in data:
                timestamp = int(data['released_at'])
                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                return dt.strftime("%b %d, %Y")
    except (ValueError, KeyError, json.JSONDecodeError):
        pass
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
    air_date_str = get_text_after_label(soup, "Aired:")
    next_ep_date = parse_next_episode_date(html)

    synopsis = None
    synopsis_selectors = [
        "div.storyline p",
        "div.synopsis p",
        "section.show__description p",
        "div.content p",
    ]
    for selector in synopsis_selectors:
        p = soup.select_one(selector)
        if p and p.get_text(strip=True):
            synopsis = p.get_text(" ", strip=True)
            break

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
        except ValueError:
            countdown_str = None

    return {
        "title": title,
        "url": url,
        "poster": poster,
        "country": country,
        "episodes": episodes,
        "air_date": air_date_str,
        "synopsis": synopsis,
        "next_ep_date": next_ep_date,
        "countdown": countdown_str,
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
        except ValueError:
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
        except ValueError:
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
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")
    rss_items = []

    for it in items:
        desc_lines = []
        if it["poster"]:
            desc_lines.append(
                f"<img src=\"{it['poster']}\" alt=\"{it['title']} poster\" style=\"width:100%;max-width:400px;height:auto;display:block;margin-bottom:12px;\" />"
            )

        desc_lines.append(f"<strong><em>{it['title']}</em></strong>")

        country_episode = []
        if it["country"]:
            country_episode.append(it["country"])
        if it["episodes"]:
            country_episode.append(f"{it['episodes']} eps")
        if country_episode:
            desc_lines.append(f"{', '.join(country_episode)}")

        if it["air_date"]:
            desc_lines.append(f"Air Date: {it['air_date']}")

        if it["countdown"]:
            desc_lines.append("<strong>next episode airs in</strong>")
            desc_lines.append(it["countdown"])
        elif it["next_ep_date"]:
            desc_lines.append("<strong>next episode airs in</strong>")
            desc_lines.append(it["next_ep_date"])

        if it["synopsis"]:
            desc_lines.append(f"<p style=\"margin:0.5em 0 0 0;\">{it['synopsis']}</p>")

        description_html = "<br>".join(desc_lines) if desc_lines else "No additional info."
        media_tag = ""
        enclosure_tag = ""
        if it["poster"]:
            mime_type = image_mime_type(it["poster"])
            media_tag = (
                f"\n    <media:content url=\"{it['poster']}\" medium=\"image\" type=\"{mime_type}\" />"
                f"\n    <media:thumbnail url=\"{it['poster']}\" />"
            )
            enclosure_tag = f"\n    <enclosure url=\"{it['poster']}\" type=\"{mime_type}\" />"

        guid = hashlib.sha256(it['url'].encode('utf-8')).hexdigest()
        pub_date = format_rfc2822(it['air_date'] or it['next_ep_date'])
        item_xml = (
            "  <item>\n"
            f"    <title>{it['title']}</title>\n"
            f"    <link>{it['url']}</link>\n"
            f"    <guid isPermaLink=\"false\">{guid}</guid>\n"
            f"    <pubDate>{pub_date}</pubDate>\n"
            f"    <description><![CDATA[{description_html}]]></description>\n"
            f"    <content:encoded><![CDATA[{description_html}]]></content:encoded>\n"
            f"{media_tag}{enclosure_tag}\n"
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
            items.append(data)
        except Exception as exc:
            print(f"Error parsing {url}: {exc}")

    items.sort(key=lambda item: parse_sort_date(item['next_ep_date']) or parse_sort_date(item['air_date']) or datetime.max.replace(tzinfo=timezone.utc), reverse=True)
    rss_xml = build_rss(items)
    Path("feed.xml").write_text(rss_xml, encoding="utf-8")
    print("feed.xml updated.")

if __name__ == "__main__":
    main()
