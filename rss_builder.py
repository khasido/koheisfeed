# rss_builder.py
from datetime import datetime, timezone, timedelta
from xml.sax.saxutils import escape
import hashlib

def image_mime_type(url):
    url = url.lower()
    if url.endswith(".png"):
        return "image/png"
    if url.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"

def build_rss(items, title, description, link):
    base_dt = datetime.now(timezone.utc)
    now = base_dt.strftime("%a, %d %b %Y %H:%M:%S %z")
    rss_items = []

    for idx, it in enumerate(items):
        desc_lines = []

        if it["poster"]:
            desc_lines.append(
                f"<p><img src=\"{it['poster']}\" alt=\"{it['title']} poster\" "
                f"style=\"width:100%;max-width:700px;height:auto;border:0;display:block;margin:0 0 1em;\" /></p>"
            )

        if it.get("country_code"):
            desc_lines.append(f"<p><strong>Country:</strong> {escape(it['country_code'])}</p>")

        if it.get("episode_count") is not None:
            desc_lines.append(f"<p><strong>Total Episodes:</strong> {it['episode_count']}</p>")

        if it.get("next_ep_date"):
            ep = it.get("next_ep_number")
            if ep:
                desc_lines.append(
                    f"<p><strong>Next Episode:</strong> Ep {ep} — {escape(it['next_ep_date'])}</p>"
                )
            else:
                desc_lines.append(
                    f"<p><strong>Next Episode:</strong> {escape(it['next_ep_date'])}</p>"
                )

        if it["synopsis"]:
            syn = escape(it["synopsis"]).replace("\n\n", "<br><br>")
            desc_lines.append(f"<p>{syn}</p>")

        desc_lines.append(f"<p><a href=\"{it['url']}\">View on TMDB</a></p>")

        description_html = "\n".join(desc_lines)

        enclosure_tag = ""
        if it["poster"]:
            mime = image_mime_type(it["poster"])
            enclosure_tag = f"\n    <enclosure url=\"{it['poster']}\" type=\"{mime}\" length=\"0\" />"

        pub_date = (base_dt - timedelta(seconds=idx)).strftime("%a, %d %b %Y %H:%M:%S %z")
        guid = hashlib.sha256(it["url"].encode("utf-8")).hexdigest()

        item_xml = (
            "  <item>\n"
            f"    <title>{escape(it['title'])}</title>\n"
            f"    <link>{escape(it['url'])}</link>\n"
            f"    <guid isPermaLink=\"false\">{guid}</guid>\n"
            f"    <pubDate>{pub_date}</pubDate>\n"
            f"    <description><![CDATA[{description_html}]]></description>\n"
            f"    <content:encoded><![CDATA[{description_html}]]></content:encoded>\n"
            f"{enclosure_tag}\n"
            "  </item>"
        )
        rss_items.append(item_xml)

    channel_header = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<rss version=\"2.0\" xmlns:media=\"http://search.yahoo.com/mrss/\" "
        "xmlns:content=\"http://purl.org/rss/1.0/modules/content/\">\n"
        "<channel>\n"
        f"  <title>{escape(title)}</title>\n"
        f"  <link>{escape(link)}</link>\n"
        f"  <description>{escape(description)}</description>\n"
        "  <language>en-US</language>\n"
        "  <generator>BL/GL TMDB Auto Generator</generator>\n"
        f"  <lastBuildDate>{now}</lastBuildDate>\n"
    )

    return f"{channel_header}{''.join(rss_items)}\n</channel>\n</rss>\n"
