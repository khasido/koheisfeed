# tmdb_fetcher.py
import os
import time
import requests
import re

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})

# ---------------------------------------------------------
# Retry logic + timeout
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
# BL/GL detection signals
# ---------------------------------------------------------

BL_KEYWORDS = {
    "boys love", "bl", "gay", "mlm", "queer", "same-sex",
    "gay romance", "gay relationship", "male couple"
}

GL_KEYWORDS = {
    "girls love", "gl", "lesbian", "wlw", "yuri", "sapphic",
    "female couple", "women love"
}

BL_STUDIOS = {
    "GMMTV", "Studio Wabi Sabi", "Mandee", "WeTV", "iQIYI",
    "TV Asahi", "Line TV", "TV Thunder"
}

GL_STUDIOS = {
    "GagaOOLala", "Fuji TV", "TBS", "NHK"
}

PRIORITY_COUNTRIES = ["TH", "JP", "KR", "CN", "TW", "PH", "VN", "HK", "MY"]

# ---------------------------------------------------------
# Utility: normalize text
# ---------------------------------------------------------

def normalize(text):
    if not text:
        return ""
    return text.lower().strip()

# ---------------------------------------------------------
# Deep inspection classifier
# ---------------------------------------------------------

def classify_lgbtq(details, credits):
    overview = normalize(details.get("overview", ""))
    title = normalize(details.get("name") or details.get("title") or "")
    country = details.get("origin_country", [""])[0]
    networks = [n.get("name", "") for n in details.get("networks", [])]
    studios = [s.get("name", "") for s in details.get("production_companies", [])]

    # -----------------------------
    # STRONG SIGNALS
    # -----------------------------

    strong = 0
    weak = 0

    # 1. Overview text
    if any(word in overview for word in BL_KEYWORDS):
        strong += 1
        bl_flag = True
    elif any(word in overview for word in GL_KEYWORDS):
        strong += 1
        bl_flag = False
    else:
        bl_flag = None

    # 2. Cast gender pairing
    cast = credits.get("cast", [])
    male_leads = [c for c in cast if c.get("gender") == 2][:2]
    female_leads = [c for c in cast if c.get("gender") == 1][:2]

    if len(male_leads) >= 2:
        strong += 1
        bl_flag = True

    if len(female_leads) >= 2:
        strong += 1
        bl_flag = False

    # 3. Studio/network
    if any(s in BL_STUDIOS for s in studios + networks):
        strong += 1
        bl_flag = True

    if any(s in GL_STUDIOS for s in studios + networks):
        strong += 1
        bl_flag = False

    # -----------------------------
    # WEAK SIGNALS
    # -----------------------------

    # 4. Country
    if country in PRIORITY_COUNTRIES:
        weak += 1

    # 5. Title patterns
    if re.search(r"\bbl\b", title) or "boys love" in title:
        weak += 1
        bl_flag = True

    if re.search(r"\bgl\b", title) or "girls love" in title or "yuri" in title:
        weak += 1
        bl_flag = False

    # 6. Genres
    genres = [g["name"].lower() for g in details.get("genres", [])]
    if "romance" in genres:
        weak += 1

    # ---------------------------------------------------------
    # DECISION RULE
    # ---------------------------------------------------------

    # Must have at least 1 strong signal OR 1 strong + 2 weak
    if strong >= 1:
        return "bl" if bl_flag else "gl"

    if strong == 0 and weak >= 3:
        return "bl" if bl_flag else "gl"

    return None

# ---------------------------------------------------------
# Build item
# ---------------------------------------------------------

def build_item(entry, kind):
    tmdb_id = entry["id"]

    time.sleep(0.3)

    details = tmdb_get(
        f"/{kind}/{tmdb_id}",
        append_to_response="next_episode_to_air,last_episode_to_air,credits"
    )

    if not details:
        return None

    # Skip ended shows
    status_raw = details.get("status", "").lower()
    if status_raw in ["ended", "canceled", "cancelled"]:
        return None

    credits = details.get("credits", {})

    # Classify BL/GL
    category = classify_lgbtq(details, credits)
    if category not in ["bl", "gl"]:
        return None

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
        "category": category
    }

# ---------------------------------------------------------
# Broad discovery
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
