# tmdb_fetcher.py
import os
import time
import requests
from datetime import datetime, date

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})

# ---------------------------------------------------------
# CONFIG: exact TMDB keyword IDs (OR logic)
# ---------------------------------------------------------

# Replace these with the IDs you see on TMDB keyword pages
BL_KEYWORD_IDS = {
    210024,  # Boys' Love (BL)
    158718,  # Gay romance / relationship
    210025,  # Fudanshi
    210026,  # Fujoshi
}

GL_KEYWORD_IDS = {
    12377,   # Lesbian
    210027,  # Girls' Love (GL)
}

# Country priority (used in update.py for sorting, not filtering)
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
# Keyword extraction and classification
# ---------------------------------------------------------

def extract_keyword_ids(details):
    kw_block = details.get("keywords") or {}

    # Movies: {"keywords": [...]}
    if isinstance(kw_block, dict) and isinstance(kw_block.get("keywords"), list):
        return {k["id"] for k in kw_block["keywords"] if "id" in k}

    # TV: {"results": [...]}
    if isinstance(kw_block, dict) and isinstance(kw_block.get("results"), list):
        return {k["id"] for k in kw_block["results"] if "id" in k}

    if isinstance(kw_block, list):
        return {k["id"] for k in kw_block if "id" in k}

    return set()

def classify_by_keywords(details):
    kw_ids = extract_keyword_ids(details)

    # OR logic: at least one matching keyword is enough
    if kw_ids & BL_KEYWORD_IDS:
        return "bl"
    if kw_ids & GL_KEYWORD_IDS:
        return "gl"
    return None

# ---------------------------------------------------------
# Season-level inspection for TV
# ---------------------------------------------------------

def analyze_season(tmdb_id, season_number):
    """Fetch and analyze the season page to determine correct episode schedule."""
    season = tmdb_get(f"/tv/{tmdb_id}/season/{season_number}")
    if not season or "episodes" not in season:
        return None

    episodes = season["episodes"]
    if not episodes:
        return None

    # Sort episodes by episode number
    episodes = sorted(episodes, key=lambda e: e.get("episode_number", 0))

    next_ep_number = None
    next_ep_date = None
    last_ep_number = None
    last_ep_date = None

    today = date.today()

    for ep in episodes:
        air_date = ep.get("air_date")
        ep_num = ep.get("episode_number")

        if not air_date or not ep_num:
            continue

        try:
            dt = datetime.strptime(air_date, "%Y-%m-%d").date()
        except Exception:
            continue

        # Future episode → next episode
        if dt > today and next_ep_number is None:
            next_ep_number = ep_num
            next_ep_date = dt.strftime("%b %d, %Y")

        # Past or today → last episode
        if dt <= today:
            last_ep_number = ep_num
            last_ep_date = dt.strftime("%b %d, %Y")

    # Determine status from schedule
    if next_ep_number:
        status = "ongoing"
    else:
        # No future episodes in this season → treat as ended
        status = "ended"

    return {
        "next_ep_number": next_ep_number,
        "next_ep_date": next_ep_date,
        "last_ep_number": last_ep_number,
        "last_ep_date": last_ep_date,
        "status": status,
    }

# ---------------------------------------------------------
# Build normalized item
# ---------------------------------------------------------

def build_item(entry, kind):
    tmdb_id = entry["id"]

    time.sleep(0.3)

    # For TV we need seasons; for movies we don't
    append = "keywords"
    if kind == "tv":
        append = "keywords,seasons"

    details = tmdb_get(
        f"/{kind}/{tmdb_id}",
        append_to_response=append
    )
    if not details:
        return None

    # Strict tag classification (OR logic on keyword IDs)
    category = classify_by_keywords(details)
    if category not in ("bl", "gl"):
        return None

    # TV vs Movie handling
    if kind == "tv":
        # Pick the latest non-zero season number
        seasons = details.get("seasons") or []
        valid_seasons = [s for s in seasons if s.get("season_number", 0) > 0]
        if not valid_seasons:
            return None

        season_number = max(s["season_number"] for s in valid_seasons)

        season_info = analyze_season(tmdb_id, season_number)
        if not season_info:
            return None

        # If season-level status says ended, skip
        if season_info["status"] == "ended":
            return None

        next_ep_number = season_info["next_ep_number"]
        next_ep_date = season_info["next_ep_date"]
        status = season_info["status"]
        ep_total = season_info["last_ep_number"]

    else:
        # Movies: use release_date to determine upcoming vs released
        release_date = details.get("release_date")
        next_ep_number = None
        next_ep_date = None
        ep_total = None

        if release_date:
            try:
                rd = datetime.strptime(release_date, "%Y-%m-%d").date()
                if rd > date.today():
                    status = "upcoming"
                    next_ep_date = rd.strftime("%b %d, %Y")
                else:
                    status = "ended"
            except Exception:
                status = "ended"
        else:
            status = "upcoming"

    title = details.get("name") or details.get("title")
    url = f"https://www.themoviedb.org/{kind}/{tmdb_id}"

    poster = None
    if details.get("poster_path"):
        poster = f"https://image.tmdb.org/t/p/w500{details['poster_path']}"

    # Country code
    country = None
    if kind == "tv":
        if "origin_country" in details and details["origin_country"]:
            country = details["origin_country"][0]
    else:
        countries = details.get("production_countries") or []
        if countries:
            country = countries[0].get("iso_3166_1")

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
# Fetch by keyword (OR logic via union of all keyword results)
# ---------------------------------------------------------

def discover_by_keyword(kind, keyword_id, max_pages=3):
    """Get items for a single keyword ID, across a few pages."""
    results = []
    for page in range(1, max_pages + 1):
        time.sleep(0.3)
        data = tmdb_get(
            f"/discover/{kind}",
            include_adult=False,
            sort_by="popularity.desc",
            with_keywords=keyword_id,
            page=page,
        )
        if not data or "results" not in data or not data["results"]:
            break
        results.extend(data["results"])
    return results

def discover_candidates_for_set(kind, keyword_ids):
    """Union of all results for all keyword IDs (OR logic across tags)."""
    seen_ids = set()
    candidates = []

    for kw_id in keyword_ids:
        entries = discover_by_keyword(kind, kw_id)
        for e in entries:
            eid = e["id"]
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            candidates.append(e)

    items = []
    for entry in candidates:
        item = build_item(entry, kind)
        if item:
            items.append(item)

    return items

# ---------------------------------------------------------
# Public fetchers
# ---------------------------------------------------------

def fetch_bl_items():
    tv_items = discover_candidates_for_set("tv", BL_KEYWORD_IDS)
    movie_items = discover_candidates_for_set("movie", BL_KEYWORD_IDS)
    return tv_items + movie_items

def fetch_gl_items():
    tv_items = discover_candidates_for_set("tv", GL_KEYWORD_IDS)
    movie_items = discover_candidates_for_set("movie", GL_KEYWORD_IDS)
    return tv_items + movie_items
