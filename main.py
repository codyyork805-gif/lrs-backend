from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import os
import math
import hashlib
import re
import requests
from dotenv import load_dotenv

load_dotenv()
GOOGLE_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CHAIN_HINTS = [
    "mcdonald", "starbucks", "chipotle", "subway", "taco bell", "kfc", "wendy",
    "burger king", "domino", "pizza hut", "panera", "dunkin", "ihop", "applebee",
    "olive garden", "outback", "red lobster", "buffalo wild wings",
    "cheesecake factory", "yard house"
]

# If cuisine is one of these, we try to keep results within these Google place types
CUISINE_TYPE_LOCK = {
    "pizza": {"pizza_restaurant"},
    "tacos": {"mexican_restaurant"},
    "ramen": {"ramen_restaurant", "japanese_restaurant"},
    "sushi": {"sushi_restaurant", "japanese_restaurant"},
    "thai": {"thai_restaurant"},
    "bbq": {"barbecue_restaurant"},
    "breakfast": {"breakfast_restaurant"},
    "burgers": {"hamburger_restaurant"},
}

# Words we look for in reviews to guess “what to order”
# (We only expand this list — we do NOT change the logic.)
DISH_KEYWORDS = {
    # existing cuisines (kept + expanded)
    "tacos": [
        "birria", "al pastor", "carnitas", "carne asada", "fish taco", "shrimp taco",
        "quesabirria", "burrito", "quesadilla", "salsa", "guacamole",
        "barbacoa", "lengua", "pollo", "chile relleno", "pozole", "menudo"
    ],
    "pizza": [
        "pepperoni", "margherita", "mushroom", "sausage", "meatball", "garlic", "pesto",
        "white pizza", "deep dish", "thin crust", "calzone",
        "sicilian", "grandma slice", "four cheese"
    ],
    "ramen": [
        "tonkotsu", "shoyu", "miso", "spicy ramen", "chashu", "gyoza", "broth", "noodles"
    ],
    "sushi": [
        "omakase", "roll", "nigiri", "sashimi", "spicy tuna", "salmon", "eel", "uni", "hand roll"
    ],
    "thai": [
        "pad thai", "green curry", "red curry", "tom yum", "drunken noodles", "pad see ew", "thai tea"
    ],
    "bbq": [
        "brisket", "ribs", "pulled pork", "burnt ends", "sausage", "smoked chicken", "mac and cheese",
        "beef rib", "pork ribs", "tri tip", "smoked turkey"
    ],
    "breakfast": [
        "pancakes", "waffles", "biscuits and gravy", "omelet", "eggs benedict", "hash browns",
        "french toast", "breakfast burrito"
    ],
    "burgers": [
        "burger", "cheeseburger", "fries", "onion rings", "milkshake", "smashburger", "bacon",
        "double burger", "house burger", "patty melt", "bacon burger"
    ],

    # new cuisines (future-proof; still not brands)
    "italian": [
        "spaghetti", "meatballs", "lasagna",
        "chicken parmesan", "eggplant parmesan",
        "alfredo", "carbonara", "bolognese"
    ],
    "chinese": [
        "dumplings", "potstickers", "fried rice",
        "lo mein", "chow mein",
        "kung pao chicken", "mapo tofu"
    ],
    "mediterranean": [
        "shawarma", "gyro", "falafel",
        "hummus", "kebab", "chicken shawarma"
    ],
    "vietnamese": [
        "pho", "bun bo hue",
        "vermicelli", "banh mi", "spring rolls"
    ],
    "steak": [
        "ribeye", "new york strip",
        "filet mignon", "prime rib", "steak frites"
    ],
    "fried chicken": [
        "fried chicken", "hot chicken",
        "chicken and waffles",
        "collard greens", "cornbread", "mac and cheese"
    ],
}

# Hype-mode: when we go past 10 miles, we show ONE of these (stable rotation)
HYPE_DISTANCE_LINES = [
    "Popularity isn’t always neighborhood-bound.",
    "Popular spots often draw people from farther away.",
    "Hype isn’t always right around the corner.",
    "This kind of popularity isn’t always local.",
    "This kind of buzz isn’t always local.",
]

def mode_label(mode: str) -> str:
    mode = (mode or "").lower().strip()
    if mode == "strict":
        return "Top Local Picks"
    if mode == "best":
        return "Best Available"
    if mode == "hype":
        return "Hype"
    return "Unknown"

def miles_to_meters(miles: float) -> int:
    return int(miles * 1609.344)

def meters_to_miles(meters: float) -> float:
    return float(meters) / 1609.344

def is_chain(name: str) -> bool:
    name = (name or "").lower()
    return any(c in name for c in CHAIN_HINTS)

def stable_pick_index(s: str, n: int) -> int:
    h = hashlib.md5(s.encode("utf-8")).hexdigest()
    return int(h[:8], 16) % n

def haversine_m(lat1, lon1, lat2, lon2) -> float:
    # distance in meters
    R = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def places_text_search(query: str, center: dict | None = None, radius_m: int | None = None) -> list[dict]:
    """Google Places Text Search (New Places API) with OPTIONAL location bias."""
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_KEY,
        "X-Goog-FieldMask": (
            "places.id,"
            "places.displayName,"
            "places.formattedAddress,"
            "places.rating,"
            "places.userRatingCount,"
            "places.googleMapsUri,"
            "places.primaryType,"
            "places.types,"
            "places.location"
        ),
    }
    body = {"textQuery": query}

    # Keep results near the user's location when we can
    if center and radius_m:
        body["locationBias"] = {
            "circle": {
                "center": center,
                "radius": int(radius_m),
            }
        }

    r = requests.post(url, headers=headers, json=body, timeout=20)
    r.raise_for_status()
    return r.json().get("places", [])

def location_center_from_text(location_text: str) -> dict | None:
    """Resolve a user location string into a lat/lng using the same Places Text Search."""
    try:
        if not (location_text or "").strip():
            return None

        url = "https://places.googleapis.com/v1/places:searchText"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GOOGLE_KEY,
            "X-Goog-FieldMask": "places.location,places.formattedAddress,places.displayName",
        }
        body = {"textQuery": location_text}
        r = requests.post(url, headers=headers, json=body, timeout=15)
        r.raise_for_status()
        places = r.json().get("places", [])
        if not places:
            return None

        loc = places[0].get("location") or None
        if not loc:
            return None

        if "latitude" in loc and "longitude" in loc:
            return {"latitude": float(loc["latitude"]), "longitude": float(loc["longitude"])}
        return None
    except Exception:
        return None

def place_reviews(place_id: str) -> list[str]:
    if not place_id:
        return []
    try:
        url = f"https://places.googleapis.com/v1/places/{place_id}"
        headers = {
            "X-Goog-Api-Key": GOOGLE_KEY,
            "X-Goog-FieldMask": "reviews.text.text",
        }
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        reviews = data.get("reviews") or []
        texts = []
        for rv in reviews[:8]:
            t = (((rv.get("text") or {}).get("text")) or "").strip()
            if t:
                texts.append(t)
        return texts
    except Exception:
        return []

def links_for(p: dict) -> dict:
    name = ((p.get("displayName") or {}).get("text") or "")
    addr = p.get("formattedAddress") or ""
    maps = p.get("googleMapsUri") or ""
    yelp = (
        "https://www.yelp.com/search?find_desc="
        + requests.utils.quote(name)
        + "&find_loc="
        + requests.utils.quote(addr)
    )
    return {"google_maps": maps, "yelp_search": yelp}

def key_for(p: dict) -> str:
    name = ((p.get("displayName") or {}).get("text") or "").strip().lower()
    addr = (p.get("formattedAddress") or "").strip().lower()
    return f"{name}||{addr}"

def score_lrs(p: dict) -> float:
    rating = float(p.get("rating") or 0)
    reviews = int(p.get("userRatingCount") or 0)
    review_strength = math.log10(max(1, reviews))
    return rating * 2 + review_strength

def score_hype(p: dict) -> float:
    rating = float(p.get("rating") or 0)
    reviews = int(p.get("userRatingCount") or 0)
    return (math.log10(max(1, reviews)) * 5) + (rating * 1.0)

def confidence_label(rating: float, reviews: int) -> str:
    if rating >= 4.5 and reviews >= 300:
        return "High"
    if rating >= 4.3 and reviews >= 100:
        return "Med"
    return "Low"

def confidence_explainer(label: str) -> str:
    if label == "High":
        return "High = lots of reviews + very strong rating."
    if label == "Med":
        return "Med = good rating with some real review depth."
    return "Low = fewer reviews. Could still be great, just less proof."

def hype_reason(rating: float, reviews: int) -> str:
    if reviews >= 1500 and rating >= 4.4:
        return "Big buzz: tons of reviews + very high rating."
    if reviews >= 800:
        return "Popular spot: lots of reviews (people talk about it)."
    if rating >= 4.6 and reviews >= 200:
        return "High rating + solid review count (strong crowd signal)."
    if reviews >= 200:
        return "Decent buzz: good review volume for this area."
    return "Some buzz: not huge, but trending-ish locally."

def cuisine_lock_types(cuisine: str | None) -> set[str] | None:
    if not cuisine:
        return None
    return CUISINE_TYPE_LOCK.get(cuisine.strip().lower())

def matches_type_lock(place: dict, allowed: set[str] | None) -> bool:
    if not allowed:
        return True
    primary = (place.get("primaryType") or "").strip().lower()
    types = [t.strip().lower() for t in (place.get("types") or [])]
    if primary in allowed:
        return True
    return any(t in allowed for t in types)

def why_line(mode: str, name: str, rating: float, reviews: int) -> str:
    mode = (mode or "").lower().strip()
    key = f"{mode}|{name}|{rating}|{reviews}"

    if mode == "strict":
        options = [
            "This feels like a place locals genuinely rely on.",
            "Quiet winner energy — not flashy, just trusted.",
            "If you only try one, start here. It’s the safe local call.",
            "This has the kind of reputation that builds naturally over time.",
            "People keep coming back here — it’s a real local staple.",
        ]
        return options[stable_pick_index(key, len(options))]

    if mode == "best":
        options = [
            "A solid everyday choice for this area.",
            "The kind of place someone local would casually recommend.",
            "Dependable energy — not a risk pick.",
            "This fits how people actually eat around here.",
            "If options are limited, this is a sensible call.",
        ]
        return options[stable_pick_index(key, len(options))]

    options = [
        "This one gets talked about a lot.",
        "More attention than average around here.",
        "The kind of place people mention by name.",
        "If you’re chasing what’s popular, this is the lane.",
        "High visibility spot — it keeps showing up in conversation.",
    ]
    return options[stable_pick_index(key, len(options))]

def normalize_text(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def most_mentioned_dish(review_texts: list[str], cuisine: str | None) -> str | None:
    if not review_texts:
        return None

    c = (cuisine or "").strip().lower()
    keywords = DISH_KEYWORDS.get(c)

    if not keywords:
        return None

    joined = " ".join(normalize_text(t) for t in review_texts)

    counts = []
    for kw in keywords:
        k = normalize_text(kw)
        if not k:
            continue
        n = joined.count(k)
        if n > 0:
            counts.append((n, kw))

    if not counts:
        return None

    counts.sort(reverse=True, key=lambda x: x[0])
    return counts[0][1]

ORDER_SENTENCE_OPTIONS = [
    "Most people mention this",
    "Commonly mentioned by regulars",
    "Shows up often when locals talk about this place",
    "Mentioned repeatedly in reviews",
    "A frequent favorite among locals",
    "This is what people tend to order here",
    "This comes up a lot when locals talk about the place",
]

def order_line(place_name: str, dish: str | None) -> str:
    if dish:
        key = f"order|{place_name}|{dish}"
        sentence = ORDER_SENTENCE_OPTIONS[stable_pick_index(key, len(ORDER_SENTENCE_OPTIONS))]
        return f"{sentence} — {dish}."
    return "If you’re unsure, ask what regulars order most."

def build_picks(
    places: list[dict],
    min_rating: float,
    min_reviews: int,
    sorter,
    allowed_types: set[str] | None,
    center: dict | None = None,
    max_radius_m: int | None = None,
) -> list[dict]:
    filtered = []
    for p in places:
        name = ((p.get("displayName") or {}).get("text") or "").strip()
        if not name:
            continue
        if is_chain(name):
            continue
        if not matches_type_lock(p, allowed_types):
            continue

        rating = float(p.get("rating") or 0)
        reviews = int(p.get("userRatingCount") or 0)

        if rating < min_rating or reviews < min_reviews:
            continue

        # Hard distance filter (prevents LA/SF jumps)
        if center and max_radius_m:
            loc = p.get("location") or {}
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                d = haversine_m(center["latitude"], center["longitude"], float(lat), float(lon))
                if d > float(max_radius_m):
                    continue

        filtered.append(p)

    ranked = sorted(filtered, key=sorter, reverse=True)[:12]

    picks = []
    for p in ranked:
        pid = (p.get("id") or "").strip()
        name = ((p.get("displayName") or {}).get("text") or "").strip()
        addr = (p.get("formattedAddress") or "").strip()
        rating = float(p.get("rating") or 0)
        reviews = int(p.get("userRatingCount") or 0)
        conf = confidence_label(rating, reviews)

        # ✅ NEW: compute distance_miles so frontend can enforce caps too
        distance_miles = None
        if center:
            loc = p.get("location") or {}
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                d_m = haversine_m(center["latitude"], center["longitude"], float(lat), float(lon))
                distance_miles = round(meters_to_miles(d_m), 1)

        picks.append({
            "key": key_for(p),
            "place_id": pid,
            "name": name,
            "location": addr,
            "rating": rating,
            "reviews": reviews,
            "confidence": conf,
            "confidence_explainer": confidence_explainer(conf),
            "why": "",
            "order": "If you’re unsure, ask what regulars order most.",
            "links": links_for(p),
            "also_in_strict": False,
            "hype_reason": hype_reason(rating, reviews),
            "distance_miles": distance_miles,
        })

    return picks

def prefer_new_first(picks: list[dict], strict_keys: set[str]) -> list[dict]:
    new_ones = []
    overlaps = []
    for p in picks:
        if p["key"] in strict_keys:
            p["also_in_strict"] = True
            overlaps.append(p)
        else:
            new_ones.append(p)
    return (new_ones + overlaps)[:5]

def build_with_type_fallback(
    places: list[dict],
    min_rating: float,
    min_reviews: int,
    sorter,
    allowed_types: set[str] | None,
    want_at_least: int = 3,
    center: dict | None = None,
    max_radius_m: int | None = None,
) -> tuple[list[dict], bool]:
    picks = build_picks(places, min_rating, min_reviews, sorter, allowed_types, center, max_radius_m)
    if allowed_types and len(picks) < want_at_least:
        picks = build_picks(places, min_rating, min_reviews, sorter, None, center, max_radius_m)
        return picks, True
    return picks, False

def add_order_from_reviews(picks: list[dict], cuisine: str | None):
    for p in picks:
        pid = (p.get("place_id") or "").strip()
        texts = place_reviews(pid)
        dish = most_mentioned_dish(texts, cuisine)
        p["order"] = order_line(p.get("name", ""), dish)

def hype_distance_line(location: str, cuisine: str | None) -> str:
    key = f"hype_distance|{(location or '').strip().lower()}|{(cuisine or '').strip().lower()}"
    return HYPE_DISTANCE_LINES[stable_pick_index(key, len(HYPE_DISTANCE_LINES))]

@app.get("/lrs")
def lrs(
    location: str = Query(...),
    cuisine: str | None = Query(None),
    mode: str = Query("strict"),
):
    if not GOOGLE_KEY:
        return {"error": "Missing GOOGLE_PLACES_API_KEY"}

    mode = (mode or "strict").lower().strip()
    base = f"{(cuisine + ' ') if cuisine else ''}restaurants in {location}".strip()

    strict_query = f"best {base}".strip()
    best_query = base
    hype_query = f"popular {base}".strip()

    allowed_types = cuisine_lock_types(cuisine)

    # Resolve location center once (lets us keep results actually near the user)
    center = location_center_from_text(location)

    # TRUST HARDENING (DISTANCE): If we can't resolve a real center point, do NOT guess.
    # Without center, Google can return far-away matches and we can't enforce the 25-mile cap.
    if not center:
        return {
            "query": base,
            "mode": mode,
            "mode_label": mode_label(mode),
            "picks": [],
            "limitation_note": "I couldn’t confidently interpret that location. Try adding a nearby city/state (example: 'Downtown San Jose, CA').",
            "debug": {"mode": mode, "mode_label": mode_label(mode), "center_resolved": False, "final_count": 0}
        }

    # Locked radius rules (mode-based)
    STRICT_PRIMARY = miles_to_meters(5)
    STRICT_MAX = miles_to_meters(10)

    BEST_PRIMARY = miles_to_meters(10)
    BEST_MAX = miles_to_meters(15)

    HYPE_PRIMARY = miles_to_meters(10)
    HYPE_MAX = miles_to_meters(25)

    # Strict baseline (used for overlap keys) — keep it within strict primary range
    strict_places = places_text_search(strict_query, center=center, radius_m=STRICT_PRIMARY)
    strict_picks, _ = build_with_type_fallback(
        strict_places, 4.3, 150, score_lrs, allowed_types, 3,
        center=center, max_radius_m=STRICT_PRIMARY
    )
    strict_picks = strict_picks[:5]
    strict_keys = set([p["key"] for p in strict_picks])

    if mode == "strict":
        limitation = None

        # If strict returns too few, widen only up to 10 miles (locked max)
        if len(strict_picks) < 3:
            strict_places_wide = places_text_search(strict_query, center=center, radius_m=STRICT_MAX)
            strict_picks_wide, _ = build_with_type_fallback(
                strict_places_wide, 4.3, 150, score_lrs, allowed_types, 3,
                center=center, max_radius_m=STRICT_MAX
            )
            if len(strict_picks_wide) > len(strict_picks):
                strict_picks = strict_picks_wide[:5]
                limitation = "This area is limited for that search, so I widened the search up to 10 miles."

        add_order_from_reviews(strict_picks, cuisine)
        for p in strict_picks:
            p["why"] = why_line("strict", p["name"], float(p["rating"]), int(p["reviews"]))
            p.pop("key", None)
            p.pop("place_id", None)

        return {
            "query": strict_query,
            "mode": mode,
            "mode_label": mode_label(mode),
            "picks": strict_picks,
            "limitation_note": limitation,
            "debug": {"mode": mode, "mode_label": mode_label(mode), "final_count": len(strict_picks)}
        }

    if mode == "best":
        limitation = None

        best_places = places_text_search(best_query, center=center, radius_m=BEST_PRIMARY)
        picks, _ = build_with_type_fallback(
            best_places, 4.1, 30, score_lrs, allowed_types, 3,
            center=center, max_radius_m=BEST_PRIMARY
        )

        # If too few, widen only up to 15 miles (locked max)
        if len(picks) < 3:
            best_places_wide = places_text_search(best_query, center=center, radius_m=BEST_MAX)
            picks_wide, _ = build_with_type_fallback(
                best_places_wide, 4.1, 30, score_lrs, allowed_types, 3,
                center=center, max_radius_m=BEST_MAX
            )
            if len(picks_wide) > len(picks):
                picks = picks_wide
                limitation = "This area is limited for that search, so I widened the search up to 15 miles."

        picks = prefer_new_first(picks, strict_keys)

        add_order_from_reviews(picks, cuisine)
        for p in picks:
            p["why"] = why_line("best", p["name"], float(p["rating"]), int(p["reviews"]))
            p.pop("key", None)
            p.pop("place_id", None)

        return {
            "query": best_query,
            "mode": mode,
            "mode_label": mode_label(mode),
            "picks": picks,
            "limitation_note": limitation,
            "debug": {"mode": mode, "mode_label": mode_label(mode), "final_count": len(picks)}
        }

    if mode == "hype":
        limitation = None

        hype_places = places_text_search(hype_query, center=center, radius_m=HYPE_PRIMARY)
        picks, _ = build_with_type_fallback(
            hype_places, 4.0, 80, score_hype, allowed_types, 3,
            center=center, max_radius_m=HYPE_PRIMARY
        )

        # If too few, widen up to 25 miles (locked max for Hype)
        used_wide = False
        if len(picks) < 3:
            hype_places_wide = places_text_search(hype_query, center=center, radius_m=HYPE_MAX)
            picks_wide, _ = build_with_type_fallback(
                hype_places_wide, 3.8, 20, score_hype, allowed_types, 3,
                center=center, max_radius_m=HYPE_MAX
            )
            if len(picks_wide) > len(picks):
                picks = picks_wide
                used_wide = True

        picks = prefer_new_first(picks, strict_keys)

        add_order_from_reviews(picks, cuisine)
        for p in picks:
            p["why"] = why_line("hype", p["name"], float(p["rating"]), int(p["reviews"]))
            p.pop("key", None)
            p.pop("place_id", None)

        if used_wide:
            limitation = f"{hype_distance_line(location, cuisine)} Showing hype picks up to 25 miles."

        return {
            "query": hype_query,
            "mode": mode,
            "mode_label": mode_label(mode),
            "picks": picks,
            "limitation_note": limitation,
            "debug": {"mode": mode, "mode_label": mode_label(mode), "final_count": len(picks)}
        }

    return {"error": "mode must be: strict, best, or hype"}
