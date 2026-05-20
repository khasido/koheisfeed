# tmdb_fetcher.py (DIAGNOSTIC VERSION)
import os
import time
import requests
from datetime import datetime, date, timedelta

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})

# ---------------------------------------------------------
# HARD‑CODED KEYWORD + NETWORK IDs
# ---------------------------------------------------------

BL_KEYWORD_IDS = ["240305", "289844", "265777", "347855"]
GL_KEYWORD_IDS = ["280003", "9833", "315382"]

OTHER_LGBT_KEYWORD_IDS = ["1862", "158718", "163037"]

NETWORK_IDS = ["6316", "1974", "3266", "1784", "1671"]

PRIORITY_COUNTRIES = ["TH", "JP", "KR", "CN", "TW", "PH", "VN", "HK", "MY"]

TODAY = date.today()
SIX_MONTHS_AGO = TODAY - timedelta(days=6 * 30)
TWO_YEARS_AHEAD = TODAY + timedelta(days=2 * 365)

# ---------------------------------------------------------
# TMDB GET
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
        except Exception as e:
            if attempt == 4:
                print(f"❌ TMDB ERROR on {path}: {e}")
                return None
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
    kw_block = details.get("keywords") or {}

    if isinstance(kw_block, dict) and isinstance(kw_block.get("keywords"), list):
        return kw_block["keywords"]

    if isinstance(kw_block, dict) and isinstance(kw_block.get("results"), list):
        return kw_block["results"]

    if isinstance(kw_block, list):
        return kw_block

    return []

def extract_keyword_names(details):
    kws = extract_keywords(details)
    return {(k.get("name") or "").lower().strip() for k in kws if k.get("name")}

# ---------------------------------------------------------
# BL / GL classification
# ---------------------------------------------------------

def classify_bl_gl(details, credits):
    kw_names = extract_keyword_names(details)

    BL_NAMES = {
        "gay romance",
        "boys' love (bl)",
        "gay relationship",
        "fudanshi",
    }

    GL_NAMES = {
        "girls' love (gl)",
        "lesbian relationship",
        "lesbian couple",
    }

    has_bl = any(k in kw_names for k in BL_NAMES)
    has_gl = any(k in kw_names for k in GL_NAMES)

    if not has_bl and not has_gl:
        return None

    if has_bl and has_gl:
        cast = credits.get("cast") or []
        male_leads = [c for c in cast if c.get("gender") == 2][:2]
        female_leads = [c for c in cast if c.get("gender") == 1][:2]

        if len(male_leads) >= 2 and len(female_leads) == 0:
            return "bl"
        if len(female_leads) >= 2 and len(male_leads) == 0:
            return "gl"

        return None

    if has_bl:
        return "bl"
    if has_gl:
        return "gl"

    return None

# ---------------------------------------------------------
# Season-level inspection
# ---------------------------------------------------------

def analyze_season(tmdb_id, season_number):
    season = tmdb_get(f"/tv/{tmdb_id}/season/{season_number}")
    if not season or "episodes" not in season:
        print(f"[tv] reject {tmdb_id}: no season data")
        return None

    episodes = season["episodes"]
    if not episodes:
        print(f"[tv] reject {tmdb_id}: empty episodes")
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

        if d > TODAY and next_ep_number is None:
            next_ep_number = ep_num
            next_ep_date = d.strftime("%b %d, %Y")

        if d <= TODAY:
            last_ep_number = ep_num
            last_ep_date = d.strftime("%b %d, %Y")

    status = "ongoing" if next_ep_number else "ended"

    return {
        "next_ep_number": next_ep_number,
        "next_ep_date": next_ep_date,
        "last_ep_number": last_ep_number,
        "last_ep_date": last_ep_date,
        "status": status,
    }

# ---------------------------------------------------------
# Build normalized item (with debug prints)
# ---------------------------------------------------------

def build_item(entry, kind):
    tmdb_id = entry["id"]

    time.sleep(0.3)

    append = "keywords,credits"
    if kind == "tv":
        append = "keywords,credits,seasons"

    details = tmdb_get(f"/{kind}/{tmdb_id}", append_to_response=append)
    if not details:
        print(f"[{kind}] reject {tmdb_id}: no details")
        return None

    credits = details.get("credits") or {}

    # Country
    if kind == "tv":
        origin = details.get("origin_country") or []
        country = origin[0] if origin else None
    else:
        countries = details.get("production_countries") or []
        country = countries[0].get("iso_3166_1") if countries else None

    if not country or country not in PRIORITY_COUNTRIES:
        print(f"[{kind}] reject {tmdb_id}: country {country}")
        return None

    # Date window
    first_date_str = details.get("first_air_date") if kind == "tv" else details.get("release_date")
    if not in_date_window(first_date_str):
        print(f"[{kind}] reject {tmdb_id}: date {first_date_str}")
        return None

    # BL/GL classification
    category = classify_bl_gl(details, credits)
    if category not in ("bl", "gl"):
        print(f"[{kind}] reject {tmdb_id}: not BL/GL")
        return None

    # TV logic
    if kind == "tv":
        seasons = details.get("seasons") or []
        valid_seasons = [s for s in seasons if s.get("season_number", 0) > 0]
        if not valid_seasons:
            print(f"[tv] reject {tmdb_id}: no valid seasons")
            return None

        season_number = max(s["season_number"] for s in valid_seasons)
        season_info = analyze_season(tmdb_id, season_number)
        if not season_info:
            return None

        if season_info["status"] == "ended":
            print(f"[tv] reject {tmdb_id}: ended")
            return None

        if not season_info["next_ep_date"]:
            print(f"[tv] reject {tmdb_id}: no next ep date")
            return None

        next_ep_number = season_info["next_ep_number"]
        next_ep_date = season_info["next_ep_date"]
        status = season_info["status"]
        ep_total = season_info["last_ep_number"]

    else:
        # Movies
        d = parse_date(first_date_str)
        if not d or d <= TODAY:
            print(f"[movie] reject {tmdb_id}: movie already released")
            return None

        next_ep_number = None
        next_ep_date = d.strftime("%b %d, %Y")
        ep_total = None
        status = "upcoming"

    title = details.get("name") or details.get("title")
    url = f"https://www.themoviedb.org/{kind}/{tmdb_id}"

    poster = None
    if details.get("poster_path"):
        poster = f"https://image.tmdb.org/t/p/w500{details['poster_path']}"

    print(f"[{kind}] ACCEPT {tmdb_id}: {title}")

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
# Discover logic with debug prints
# ---------------------------------------------------------

def _discover_by_keywords(kind, max_pages=5):
    results = []
    seen_ids = set()

    keyword_query = "|".join(BL_KEYWORD_IDS + GL_KEYWORD_IDS)

    for page in range(1, max_pages + 1):
        time.sleep(0.3)

        params = {
            "include_adult": False,
            "sort_by": "popularity.desc",
            "with_genres": "18,10749",
            "page": page,
            "with_keywords": keyword_query,
        }

        data = tmdb_get(f"/discover/{kind}", **params)
        if not data or "results" not in data:
            break

        for entry in data["results"]:
            eid = entry["id"]
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            results.append(entry)

    return results


def _discover_by_networks(kind, max_pages=5):
    results = []
    seen_ids = set()

    network_query = "|".join(NETWORK_IDS)

    for page in range(1, max_pages + 1):
        time.sleep(0.3)

        params = {
            "include_adult": False,
            "sort_by": "popularity.desc",
            "with_genres": "18,10749",
            "page": page,
            "with_networks": network_query,
        }

        data = tmdb_get(f"/discover/{kind}", **params)
        if not data or "results" not in data:
            break

        for entry in data["results"]:
            eid = entry["id"]
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            results.append(entry)

    return results


def discover_candidates(kind, max_pages=5):
    print(f"\n=== DISCOVER {kind.upper()} START ===")

    by_kw = _discover_by_keywords(kind, max_pages=max_pages)
    by_net = _discover_by_networks(kind, max_pages=max_pages)

    print(f"[{kind}] discover_by_keywords: {len(by_kw)}")
    print(f"[{kind}] discover_by_networks: {len(by_net)}")

    combined = []
    seen_ids = set()

    for entry in by_kw + by_net:
        eid = entry["id"]
        if eid in seen_ids:
            continue
        seen_ids.add(eid)
        combined.append(entry)

    print(f"[{kind}] combined unique discover results: {len(combined)}")

    results = []
    for entry in combined:
        item = build_item(entry, kind)
        if item:
            results.append(item)

    print(f"[{kind}] FINAL ITEMS AFTER build_item: {len(results)}")
    print(f"=== DISCOVER {kind.upper()} END ===\n")

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
