import xml.etree.ElementTree as ET

def parse_feed_items(xml_text):
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    items = []

    for item in channel.findall("item"):
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        description = item.findtext("description", "")
        encoded = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded", "")
        poster = None

        # Extract poster from enclosure
        enclosure = item.find("enclosure")
        if enclosure is not None:
            poster = enclosure.get("url")

        # Extract custom fields from description HTML
        # (We embedded all metadata inside the HTML)
        def extract(tag):
            if tag in encoded:
                start = encoded.find(f"<strong>{tag}</strong>")
                if start != -1:
                    segment = encoded[start:]
                    end = segment.find("</p>")
                    if end != -1:
                        return segment.split("</strong>")[1].split("</p>")[0].strip()
            return None

        country = extract("Country:")
        episodes = extract("Total Episodes:")
        next_ep = extract("Next Episode:")
        synopsis = encoded.split("</p>")[-2].strip() if encoded else ""

        # Parse next episode number + date
        next_ep_number = None
        next_ep_date = None
        if next_ep:
            parts = next_ep.split("—")
            if len(parts) == 2:
                left, right = parts
                # Extract episode number
                if "Ep" in left:
                    try:
                        next_ep_number = int(left.replace("Ep", "").strip())
                    except:
                        pass
                next_ep_date = right.strip()

        # Determine status
        status = "upcoming"
        if "Airs In" in encoded:
            status = "airing"

        items.append({
            "title": title,
            "url": link,
            "poster": poster,
            "country": country,
            "episode_count": int(episodes) if episodes and episodes.isdigit() else None,
            "next_ep_number": next_ep_number,
            "next_ep_date": next_ep_date,
            "synopsis": synopsis,
            "status": status
        })

    return items
