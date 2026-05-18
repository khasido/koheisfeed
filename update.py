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
        # Look for the nextEpisodeAiring JavaScript variable
        match = re.search(r'var nextEpisodeAiring = ({[^}]+});', html)
        if match:
            data = json.loads(match.group(1))
            if 'released_at' in data:
                timestamp = int(data['released_at'])
                # Convert Unix timestamp to datetime
                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                return dt.strftime("%b %d, %Y")
    except (ValueError, KeyError, json.JSONDecodeError):
        pass
    return None
def get_status(soup):
    """Extract show status (Ongoing, Upcoming, Completed)."""
    status = get_text_after_label(soup, "Status:")
    if status:
        return status.lower()
    return None

def parse_show_page(url):
    html = fetch(url)
    soup = BeautifulSoup(html, "lxml")
status = get_status(soup)

    title_el = soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else url

    poster = None
    img = soup.select_one("img[src*='mydramalist.com'][class*='cover']")
    if img and img.get("src"):
        poster = img["src"]

    country = get_text_after_label(soup, "Country:")
    episodes = get_text_after_label(soup, "Episodes:")
    air_date_str = get_text_after_label(soup, "Aired:")
    next_ep_date = parse_next_episode_date(html)
    
    # Extract synopsis from first paragraph
    synopsis = None
    p = soup.find("p")
    if p:
        synopsis = p.get_text(strip=True)

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
            # Discord/MEE6 requires length="0"
            enclosure_tag = (
               f"\n    <enclosure url=\"{it['poster']}\" "
               f"type=\"{mime_type}\" length=\"0\" />"
            )
        item_xml = (
            "  <item>\n"
            f"    <title>{it['title']}</title>\n"
            f"    <link>{it['url']}</link>\n"
            f"    <description><![CDATA[{description_html}]]></description>\n"
            f"    <pubDate>{format_rfc2822(it['air_date'] or it['next_ep_date'])}</pubDate>"
            f"{media_tag}{enclosure_tag}\n"
            "  </item>"
        )
        rss_items.append(item_xml)

    rss_body = "\n".join(rss_items)
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<rss version=\"2.0\" xmlns:media=\"http://search.yahoo.com/mrss/\">\n"
        "<channel>\n"
        "  <title>Ongoing and Upcoming BLs</title>\n"
        f"  <link>{LIST_URL}</link>\n"
        "  <description>Auto-generated feed from MyDramaList list 3kPbQnZ4</description>\n"
        f"  <lastBuildDate>{now}</lastBuildDate>\n"
        f"{rss_body}\n"
        "</channel>\n"
        "</rss>\n"
    )

def main():
    list_html = fetch(LIST_URL)
    show_urls = parse_list_page(list_html)[:MAX_ITEMS]

    items = []
    for url in show_urls:
        try:
            print(f"Parsing {url}")
            data = parse_show_page(url)
            # Only include ongoing or upcoming shows
            status = data.get("status", "")
            if status not in ["completed", "finished", "ended"]:
            items.append(data)

        except Exception as exc:
            print(f"Error parsing {url}: {exc}")

    items.sort(key=lambda item: parse_sort_date(item['next_ep_date']) or parse_sort_date(item['air_date']) or datetime.max.replace(tzinfo=timezone.utc), reverse=True)
    rss_xml = build_rss(items)
    Path("feed.xml").write_text(rss_xml, encoding="utf-8")
    print("feed.xml updated.")

if __name__ == "__main__":
    main()
