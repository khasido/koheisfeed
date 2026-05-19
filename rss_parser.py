# rss_parser.py
import xml.etree.ElementTree as ET
from html import unescape

def extract_between(text, start_tag, end_tag):
    start = text.find(start_tag)
    if start == -1:
        return None
    start += len(start_tag)
    end = text.find(end_tag, start)
    if end == -1:
        return None
    return text[start:end].strip()

def parse_feed_items(xml_text):
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    items = []

    for item in channel.findall("item"):
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        encoded = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded", "") or ""
        encoded = unescape(encoded)

        # Poster from enclosure
        enclosure = item.find("enclosure")
        poster = enclosure.get("url") if enclosure is not None else None

        # Extract metadata from HTML
        country = extract_between(encoded, "<strong>Country:</strong>", "</p>")
        if country:
            country = country.replace(":", "").strip()

        ep_total = extract_between(encoded, "<strong>Total Episodes:</strong>", "</p>")
        try:
            ep_total = int(ep_total) if ep_total else None
        except:
            ep_total = None

        next_ep_raw = extract_between(encoded, "<strong>Next Episode:</strong>", "</p>")
        next_ep_number = None
        next_ep_date = None

        if next_ep_raw:
            if "—" in next_ep_raw:
                left, right = next_ep_raw.split("—", 1)
                right = right.strip()
                next_ep_date = right
                if "Ep" in left:
                    try:
                        next_ep_number = int(left.replace("Ep", "").strip())
                    except:
                        pass
            else:
                next_ep_date = next_ep_raw.strip()

        # Synopsis = last <p> before the link
        parts = encoded.split("</p>")
        synopsis = None
        if len(parts) >= 2:
            syn = parts[-2].strip()
            if syn and not syn.startswith("<a "):
                synopsis = syn

        # Status inference
        status = "upcoming"
        if next_ep_number:
            status = "ongoing"

        items.append({
            "title": title,
            "url": link,
            "poster": poster,
            "country_code": country,
            "episode_count": ep_total,
            "next_ep_number": next_ep_number,
            "next_ep_date": next_ep_date,
            "synopsis": synopsis,
            "status": status
        })

    return items
