# tmdb_fetcher.py
import os
import requests
from datetime import datetime

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w780"

SESSION = requests.Session()
SESSION.params = {"api_key": TMDB_API_KEY, "language": "en-US"}

PRIORITY_COUNTRIES = {
    "TH", "JP", "KR", "CN", "TW", "PH", "VN", "HK", "MY"
}

BL_KEYWORDS = ["gay theme", "boys love", "bl", "gay youth", "danmei"]
GL_KEYWORDS = ["lesbian", "girls love", "gl"]

def tmdb_get(path, **params):
    resp = SESSION.get(f"{BASE_URL}{path}", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

def map_status(tmdb_status: str) -> str:
    if not tmdb_status:
        return "unknown"
    s = tmdb_status.lower()
    if s == "returning series":
        return "ongoing"
    if s in ("in production", "planned", "post production", "pilot"):
        return "upcoming"
    if s == "canceled":
        return "canceled"
    if s == "ended":
        return "completed"
    return "unknown"

def build_item_from_tmdb(entry, kind: str):
    tmdb_id = entry["id"]
    details = tmdb_get(f"/{kind}/{tmdb_id}", append_to_response="next_episode_to_air,last_episode_to_air")

    title = details.get("name") or details.get("title")
    overview = details.get("overview") or ""
    poster_path = details.get("poster_path")
    poster = IMAGE_BASE + poster_path if poster_path else None

    origin_countries = details.get("origin_country") or []
    country_code = origin_countries[0] if origin_countries else None

    status = map_status(details.get("status"))
    # skip completed and canceled entirely
    if status in ("completed", "canceled"):
        return None

    next_ep = details.get("next_episode_to_air")
    next_ep_number = next_ep.get("episode_number") if next_ep else None
    next_ep_date = None
    if next_ep and next_ep.get("air_date"):
        dt = datetime.strptime(next_ep["air_date"], "%Y-%m-%d")
        next_ep_date = dt.strftime("%b %d, %Y")

    episode_count = None
    if kind == "tv":
        episode_count = details.get("number_of_episodes")
    elif kind == "movie":
        episode_count = 1

    url = f"https://www.themoviedb.org/{kind}/{tmdb_id}"

    return {
        "id": tmdb_id,
        "kind": kind,
        "title": title,
        "url": url,
        "poster": poster,
        "country_code": country_code,
        "episode_count": episode_count,
        "next_ep_number": next_ep_number,
        "next_ep_date": next_ep_date,
        "synopsis": overview,
        "status": status,
    }

def discover_tagged(kind: str, keywords: list[str]):
    results = {}
    for kw in keywords:
        data = tmdb_get(f"/search/{kind}", query=kw, include_adult=False)
        for entry in data.get("results", []):
            item = build_item_from_tmdb(entry, kind)
            if not item:
                continue
            # de‑duplicate by TMDB id
            results[item["id"]] = item
    return list(results.values())

def prioritize_countries(items):
    def key(it):
        code = (it["country_code"] or "").upper()
        priority = 0 if code in PRIORITY_COUNTRIES else 1
        return (priority, it["title"].lower())
    return sorted(items, key=key)

def fetch_bl_items():
    tv_items = discover_tagged("tv", BL_KEYWORDS)
    movie_items = discover_tagged("movie", BL_KEYWORDS)
    items = tv_items + movie_items
    items = [it for it in items if it["status"] in ("ongoing", "upcoming")]
    return prioritize_countries(items)

def fetch_gl_items():
    tv_items = discover_tagged("tv", GL_KEYWORDS)
    movie_items = discover_tagged("movie", GL_KEYWORDS)
    items = tv_items + movie_items
    items = [it for it in items if it["status"] in ("ongoing", "upcoming")]
    return prioritize_countries(items)
