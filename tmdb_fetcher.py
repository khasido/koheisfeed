# tmdb_fetcher.py
import os
import time
import requests
from datetime import datetime

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})

# ---------------------------------------------------------
# CONFIG: EXACT TMDB KEYWORD IDs (OR logic)
# ---------------------------------------------------------

# Replace these with the exact IDs you verified on TMDB
BL_KEYWORD_IDS = {
    210024,  # Boys' Love (BL)
    158718,  # Gay Romance / Gay Relationship
    210025,  # Fudanshi
    210026,  # Fujoshi
}

GL_KEYWORD_IDS = {
    12377,   # Lesbian
    210027,  # Girls' Love (GL)
}

# ---------------------------------------------------------
# Country priority (used later in update.py)
# ---------------------------------------------------------

PRIORITY_COUNTRIES = ["TH", "JP", "KR", "CN", "TW", "PH", "VN", "HK", "MY"]

# ---------------------------------------------------------
# TMDB GET with retries + timeout
# ---------------------------------------------------------

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

# ---------------------------------------------------------
# Extract keyword IDs from detail page
# ---------------------------------------------------------

def extract_keyword_ids(details):
    kw_block = details.get("keywords") or {}

    # Movies: {"keywords": [...]}
    if isinstance(kw_block, dict) and isinstance(kw_block.get("keywords"), list):
        return {k["id"] for k in kw_block["keywords"] if "id" in k}

    # TV: {"results": [...]}
    if isinstance(kw_block, dict) and isinstance(kw_block.get("results"), list):
        return {k["id"] for k in kw_block["results"] if "id" in k}

    # Rare fallback
    if isinstance(kw_block, list):
        return {k["id"] for k in kw_block if "id" in k}

    return set()

# ---------------------------------------------------------
# Classify strictly by TMDB keyword IDs (OR logic)
# ---------------------------------------------------------

def classify_by_keywords(details):
    kw_ids = extract_keyword_ids(details)

    if kw_ids & BL_KEYWORD_IDS:
        return "bl"
    if kw_ids & GL_KEYWORD_IDS:
        return "gl"

    return None

# ---------------------------------------------------------
# Build normalized item
# ---------------------------------------------------------

def build_item(entry, kind):
    tmdb_id = entry["id"]

    time.sleep(0.3)

    details = tmdb_get(
        f"/{kind}/{tmdb_id}",
        append_to_response="next_episode_to_air,last_episode_to_air,keywords"
    )

    if not details:
        return None

    # -----------------------------------------------------
    # STRICT STATUS HANDLING (trust TMDB completely)
    # -----------------------------------------------------
    status_raw = (details.get("status") or "").lower()

    if status_raw in ["ended", "canceled", "cancelled", "completed", "finished"]:
        return None  # never include ended shows

    # -----------------------------------------------------
    # STRICT TAG CLASSIFICATION (OR logic)
    # -----------------------------------------------------
    category = classify_by_keywords(details)
    if category not in ("bl", "gl"):
        return None

    # -----------------------------------------------------
    # Extract fields
    # -----------------------------------------------------
    title = details.get("name") or details.get("title")
    url = f"https://www.themoviedb.org/{kind}/{tmdb_id}"

    poster = None
    if details.get("poster_path"):
        poster = f"https://image.tmdb.org/t/p/w500{details['poster_path']}"

    country = None
    if "origin_country" in details and details["origin_country"]:
        country = details["origin_country"][0]

    ep_total = None
    if kind == "tv":
        ep_total = details.get("number_of_episodes")

    # -----------------------------------------------------
    # STRICT NEXT-EPISODE HANDLING
    # -----------------------------------------------------
    next_ep = details.get("next_episode_to_air")
    next_ep_number = None
    next_ep_date = None

    if next_ep:
        next_ep_number = next_ep.get("episode_number")
        air_date = next_ep.get("air_date")
        if air_date:
            try:
                dt = datetime.strptime(air_date, "%Y-%m-%d")
                next_ep_date = dt.strftime("%b %d, %Y")
            except Exception:
                next_ep_date = air_date

    # If TMDB has a next episode → ongoing, else upcoming
    status = "ongoing" if next_ep_number else "upcoming"

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
        "category": category,
    }

# ---------------------------------------------------------
# Broad discovery (Drama + Romance only)
# ---------------------------------------------------------

def discover_candidates(kind):
    time.sleep(0.3)

    data = tmdb_get(
        f"/discover/{kind}",
        include_adult=False,
        sort_by="popularity.desc",
        with_genres="18,10749"  # Drama + Romance
    )

    if not data or "results" not in data:
        return []

    results = []
    for entry in data["results"]:
        item = build_item(entry, kind)
        if item:
            results.append(item)

    return results

# ---------------------------------------------------------
# Public fetchers
# ---------------------------------------------------------

def fetch_bl_items():
    tv_items = discover_candidates("tv")
    movie_items = discover_candidates("movie")
    return [i for i in tv_items + movie_items if i["category"] == "bl"]

def fetch_gl_items():
    tv_items = discover_candidates("tv")
    movie_items = discover_candidates("movie")
    return [i for i in tv_items + movie_items if i["category"] == "gl"]
