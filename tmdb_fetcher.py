# tmdb_fetcher.py
import os
import time
import requests
from datetime import datetime, date, timedelta

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})

# ---------------------------------------------------------
# CONFIG: keyword NAMES (lowercase, exactly as on TMDB)
# ---------------------------------------------------------

BL_KEYWORD_NAMES = {
    "gay romance",
    "boys' love (bl)",
    "gay relationship",
    "fudanshi",
}

GL_KEYWORD_NAMES = {
    "girls' love (gl)",
    "lesbian relationship",
    "lesbian couple",
}

COMMON_NETWORKS = {
    "iqiyi international",
    "gmm 25",
    "gagaoolala",
    "one 31",
    "line tv",
}

OTHER_LGBT_KEYWORDS = {
    "coming out",
    "lgbt",
    "lgbt teen",
}

# Only shows from these countries are allowed
PRIORITY_COUNTRIES = ["TH", "JP", "KR", "CN", "TW", "PH", "VN", "HK", "MY"]

# Date window:
# - first air / release date must NOT be older than 6 months
# - and NOT more than 2 years in the future
TODAY = date.today()
SIX_MONTHS_AGO = TODAY - timedelta(days=6 * 30)
TWO_YEARS_AHEAD = TODAY + timedelta(days=2 * 365)

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
# Helpers
# ---------------------------------------------------------

def parse_date(dstr):
    if not dstr:
        return None
    try:
        return datetime.strptime(dstr, "%Y-%m-%d").date()
    except Exception:
        return None

def in_date_window(dstr):
    d = parse_date(dstr)
    if not d:
        return False
    if d < SIX_MONTHS_AGO:
        return False
    if d > TWO_YEARS_AHEAD:
        return False
    return True

def extract_keywords(details):
    """Return list of keyword dicts with 'id' and 'name'."""
    kw_block = details.get("keywords") or {}

    # Movies: {"keywords": [...]}
    if isinstance(kw_block, dict) and isinstance(kw_block.get("keywords"), list):
        return kw_block["keywords"]

    # TV: {"results": [...]}
    if isinstance(kw_block, dict) and isinstance(kw_block.get("results"), list):
        return kw_block["results"]

    if isinstance(kw_block, list):
        return kw_block

    return []

def extract_keyword_names(details):
    kws = extract_keywords(details)
    return {(k.get("name") or "").lower().strip() for k in kws if k.get("name")}

def extract_network_names(details):
    nets = details.get("networks") or []
    return {(n.get("name") or "").lower().strip() for n in nets if n.get("name")}

# ---------------------------------------------------------
# BL / GL classification (your exact rules)
# ---------------------------------------------------------

def classify_bl_gl(details, credits):
    """
    Your rules:
    - If it has any BL tags → BL
    - If it has any GL tags → GL
    - If it has both → decide by lead genders
    - Networks / other LGBT tags NEVER count alone; they only matter
      if BL/GL tags are present (which we already enforce).
    """
    kw_names = extract_keyword_names(details)

    has_bl = any(k in kw_names for k in BL_KEYWORD_NAMES)
    has_gl = any(k in kw_names for k in GL_KEYWORD_NAMES)

    # Must have at least one BL or GL tag
    if not has_bl and not has_gl:
        return None

    # Mixed case: both BL and GL tags present
    if has_bl and has_gl:
        cast = credits.get("cast") or []
        male_leads = [c for c in cast if c.get("gender") == 2][:2]
        female_leads = [c for c in cast if c.get("gender") == 1][:2]

        if len(male_leads) >= 2 and len(female_leads) == 0:
            return "bl"
        if len(female_leads) >= 2 and len(male_leads) == 0:
            return "gl"

        # If truly ambiguous, skip rather than misclassify
        return None

    if has_bl:
        return "bl"
    if has_gl:
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

    episodes = sorted(episodes, key=lambda e: e.get("episode_number", 0))

    next_ep_number = None
    next_ep_date = None
    last_ep_number = None
    last_ep_date = None

    for ep in episodes:
        air_date = ep.get("air_date")
        ep_num = ep.get("episode_number")

        if not air_date or not ep_num:
            continue

        d = parse_date(air_date)
        if not d:
            continue

        # Future episode → next episode
        if d > TODAY and next_ep_number is None:
            next_ep_number = ep_num
            next_ep_date = d.strftime("%b %d, %Y")

        # Past or today → last episode
        if d <= TODAY:
            last_ep_number = ep_num
            last_ep_date = d.strftime("%b %d, %Y")

    if next_ep_number:
        status = "ongoing"
    else:
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

    append = "keywords,credits"
    if kind == "tv":
        append = "keywords,credits,seasons"

    details = tmdb_get(
        f"/{kind}/{tmdb_id}",
        append_to_response=append
    )
    if not details:
        return None

    credits = details.get("credits") or {}

    # Country filter: ONLY priority countries
    if kind == "tv":
        origin = details.get("origin_country") or []
        country = origin[0] if origin else None
    else:
        countries = details.get("production_countries") or []
        country = countries[0].get("iso_3166_1") if countries else None

    if not country or country not in PRIORITY_COUNTRIES:
        return None

    # Date window filter: first_air_date or release_date
    if kind == "tv":
        first_date_str = details.get("first_air_date")
    else:
        first_date_str = details.get("release_date")

    if not in_date_window(first_date_str):
        return None

    # BL / GL classification
    category = classify_bl_gl(details, credits)
    if category not in ("bl", "gl"):
        return None

    # TV vs Movie status and episode info
    if kind == "tv":
        seasons = details.get("seasons") or []
        valid_seasons = [s for s in seasons if s.get("season_number", 0) > 0]
        if not valid_seasons:
            return None

        season_number = max(s["season_number"] for s in valid_seasons)
        season_info = analyze_season(tmdb_id, season_number)
        if not season_info:
            return None

        # If season-level status says ended, skip (you don't want ended shows)
        if season_info["status"] == "ended":
            return None

        next_ep_number = season_info["next_ep_number"]
        next_ep_date = season_info["next_ep_date"]
        status = season_info["status"]
        ep_total = season_info["last_ep_number"]

    else:
        # Movies: status based on release date vs today, but still within window
        d = parse_date(first_date_str)
        next_ep_number = None
        next_ep_date = None
        ep_total = None

        if d and d > TODAY:
            status = "upcoming"
            next_ep_date = d.strftime("%b %d, %Y")
        else:
            status = "ended"  # released already; but still within 6m–2y window

    title = details.get("name") or details.get("title")
    url = f"https://www.themoviedb.org/{kind}/{tmdb_id}"

    poster = None
    if details.get("poster_path"):
        poster = f"https://image.tmdb.org/t/p/w500{details['poster_path']}"

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
# Broad discover, then strict filtering
# ---------------------------------------------------------

def discover_candidates(kind, max_pages=5):
    """
    Broad discover by Drama + Romance, then strict filtering by:
    - country
    - date window
    - BL/GL tags
    - season-level status (for TV)
    """
    results = []
    seen_ids = set()

    for page in range(1, max_pages + 1):
        time.sleep(0.3)
        data = tmdb_get(
            f"/discover/{kind}",
            include_adult=False,
            sort_by="popularity.desc",
            with_genres="18,10749",  # Drama + Romance
            page=page,
        )
        if not data or "results" not in data or not data["results"]:
            break

        for entry in data["results"]:
            eid = entry["id"]
            if eid in seen_ids:
                continue
            seen_ids.add(eid)

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
def debug_show(tmdb_id, kind="tv"):
    """
    Debug helper: prints everything needed to understand why a show
    was included or excluded.
    """

    print("\n================ DEBUG TMDB ITEM ================")
    print(f"ID: {tmdb_id}  |  Type: {kind.upper()}")

    append = "keywords,credits,seasons" if kind == "tv" else "keywords,credits"
    details = tmdb_get(f"/{kind}/{tmdb_id}", append_to_response=append)

    if not details:
        print("❌ Could not fetch details.")
        return

    # --- BASIC INFO ---
    title = details.get("name") or details.get("title")
    print(f"Title: {title}")

    # --- COUNTRY ---
    if kind == "tv":
        origin = details.get("origin_country") or []
        country = origin[0] if origin else None
    else:
        countries = details.get("production_countries") or []
        country = countries[0].get("iso_3166_1") if countries else None

    print(f"Country: {country}  |  Allowed: {country in PRIORITY_COUNTRIES}")

    # --- DATE WINDOW ---
    date_str = details.get("first_air_date") if kind == "tv" else details.get("release_date")
    print(f"Date: {date_str}  |  In window: {in_date_window(date_str)}")

    # --- KEYWORDS ---
    kw_names = extract_keyword_names(details)
    print(f"Keywords: {kw_names}")

    has_bl = any(k in kw_names for k in BL_KEYWORD_NAMES)
    has_gl = any(k in kw_names for k in GL_KEYWORD_NAMES)
    has_other = any(k in kw_names for k in OTHER_LGBT_KEYWORDS)

    print(f"BL tags: {has_bl}  |  GL tags: {has_gl}  |  Other LGBT tags: {has_other}")

    # --- NETWORKS ---
    nets = extract_network_names(details)
    print(f"Networks: {nets}")

    # --- CREDITS ---
    credits = details.get("credits") or {}
    cast = credits.get("cast") or []
    male_leads = [c.get("name") for c in cast if c.get("gender") == 2][:3]
    female_leads = [c.get("name") for c in cast if c.get("gender") == 1][:3]

    print(f"Male leads: {male_leads}")
    print(f"Female leads: {female_leads}")

    # --- CATEGORY ---
    category = classify_bl_gl(details, credits)
    print(f"Classifier result: {category}")

    # --- SEASON‑LEVEL INSPECTION ---
    if kind == "tv":
        seasons = details.get("seasons") or []
        valid_seasons = [s for s in seasons if s.get("season_number", 0) > 0]
        if valid_seasons:
            season_number = max(s["season_number"] for s in valid_seasons)
            print(f"Inspecting season: {season_number}")

            season_info = analyze_season(tmdb_id, season_number)
            print(f"Season info: {season_info}")
        else:
            print("❌ No valid seasons found.")

    print("================ END DEBUG ======================\n")
