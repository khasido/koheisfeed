# tmdb_fetcher.py
import os
import time
import requests

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})

# ----------------------------------------
# TMDB keyword IDs (OR logic using "|")
# ----------------------------------------

BL_KEYWORDS = "210024|158718|210025|210026"  # BL, gay romance, fudanshi, fujoshi
GL_KEYWORDS = "12377|210027"  # lesbian, GL

# ----------------------------------------
# Robust TMDB GET with retries + timeout
# ----------------------------------------

def tmdb_get(path, **params):
    params["api_key"] = TMDB_API_KEY

    for attempt in range(5):
        try:
            resp = SESSION.get(
                f"{BASE_URL}{path}",
                params=params,
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()

        except Exception:
            if attempt == 4:
                raise
            time.sleep(0.5)

    return None

# ----------------------------------------
# Build item from TMDB details
# ----------------------------------------

def build_item_from_tmdb(entry, kind):
    tmdb_id = entry["id"]

    time.sleep(0.3)

    details = tmdb_get(
        f"/{kind}/{tmdb_id}",
        append_to_response="next_episode_to_air,last_episode_to_air"
    )

    if not details:
        return None

    # Skip ended/canceled shows entirely
    status_raw = details.get("status", "").lower()
    if status_raw in ["ended", "canceled", "cancelled"]:
        return None

    title = details.get("name") or details.get("title")
    url = f"https://www.themoviedb.org/{kind}/{tmdb_id}"

    poster = None
    if details.get("poster_path"):
        poster = f"https://image.tmdb.org/t/p/w500{details['poster_path']}"

    # Country
    country = None
    if "origin_country" in details and details["origin_country"]:
        country = details["origin_country"][0]

    # Episode count (TV only)
    ep_total = None
    if kind == "tv":
        ep_total = details.get("number_of_episodes")

    # Next episode info
    next_ep = details.get("next_episode_to_air")
    next_ep_number = None
    next_ep_date = None

    if next_ep:
        next_ep_number = next_ep.get("episode_number")
        air_date = next_ep.get("air_date")
        if air_date:
            try:
                dt = time.strptime(air_date, "%Y-%m-%d")
                next_ep_date = time.strftime("%b %d, %Y", dt)
            except:
                next_ep_date = air_date

    # Status
    if next_ep_number:
        status = "ongoing"
    else:
        status = "upcoming"

    return {
        "id": tmdb_id,
        "title": title,
        "url": url,
        "poster": poster,
        "country_code": country,
        "episode_count": ep_total,
        "next_ep_number": next_ep_number,
        "next_ep_date": next_ep_date,
        "status": status,
    }

# ----------------------------------------
# Discover items by TMDB keyword IDs (OR logic)
# ----------------------------------------

def discover_by_keywords(kind, keyword_ids):
    time.sleep(0.3)

    data = tmdb_get(
        f"/discover/{kind}",
        with_keywords=keyword_ids,  # OR logic using |
        include_adult=False,
        sort_by="popularity.desc"
    )

    if not data or "results" not in data:
        return []

    results = []
    for entry in data["results"]:
        item = build_item_from_tmdb(entry, kind)
        if item:
            results.append(item)

    return results

# ----------------------------------------
# Public fetchers
# ----------------------------------------

def fetch_bl_items():
    tv_items = discover_by_keywords("tv", BL_KEYWORDS)
    movie_items = discover_by_keywords("movie", BL_KEYWORDS)
    return tv_items + movie_items

def fetch_gl_items():
    tv_items = discover_by_keywords("tv", GL_KEYWORDS)
    movie_items = discover_by_keywords("movie", GL_KEYWORDS)
    return tv_items + movie_items
