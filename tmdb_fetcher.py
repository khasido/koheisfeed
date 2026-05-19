# tmdb_fetcher.py
import os
import time
import requests

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})

# ----------------------------------------
# FIXES APPLIED:
# - timeout increased to 30s
# - retry logic (5 attempts)
# - 0.3s delay between calls
# ----------------------------------------

def tmdb_get(path, **params):
    params["api_key"] = TMDB_API_KEY

    for attempt in range(5):
        try:
            resp = SESSION.get(
                f"{BASE_URL}{path}",
                params=params,
                timeout=30  # FIX 1: longer timeout
            )
            resp.raise_for_status()
            return resp.json()

        except Exception as e:
            if attempt == 4:
                raise  # final failure
            time.sleep(0.5)  # small retry delay

    return None


# ----------------------------------------
# Build item from TMDB details
# ----------------------------------------

def build_item_from_tmdb(entry, kind):
    tmdb_id = entry["id"]

    # FIX 3: delay between API calls
    time.sleep(0.3)

    details = tmdb_get(
        f"/{kind}/{tmdb_id}",
        append_to_response="next_episode_to_air,last_episode_to_air"
    )

    if not details:
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
    status_raw = details.get("status", "").lower()
    if status_raw in ["ended", "canceled", "cancelled"]:
        status = "ended"
    elif next_ep_number:
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
# Discover items by keyword
# ----------------------------------------

def discover_tagged(kind, keywords):
    results = []

    for kw in keywords:
        # FIX 3: delay between calls
        time.sleep(0.3)

        data = tmdb_get(f"/search/{kind}", query=kw, include_adult=False)
        if not data or "results" not in data:
            continue

        for entry in data["results"]:
            item = build_item_from_tmdb(entry, kind)
            if item:
                results.append(item)

    return results


# ----------------------------------------
# Public fetchers
# ----------------------------------------

BL_KEYWORDS = [
    "gay theme", "bl", "boys love", "lgbt romance", "mlm romance"
]

GL_KEYWORDS = [
    "lesbian romance", "gl", "girls love", "wlw romance", "yuri"
]

def fetch_bl_items():
    tv_items = discover_tagged("tv", BL_KEYWORDS)
    movie_items = discover_tagged("movie", BL_KEYWORDS)
    return tv_items + movie_items

def fetch_gl_items():
    tv_items = discover_tagged("tv", GL_KEYWORDS)
    movie_items = discover_tagged("movie", GL_KEYWORDS)
    return tv_items + movie_items
