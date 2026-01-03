from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import os, math, hashlib, re
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
# (You can expand this list later. This is the safest starter set.)
DISH_KEYWORDS = {
    "tacos": ["birria", "al pastor", "carnitas", "carne asada", "fish taco", "shrimp taco", "quesabirria", "burrito", "quesadilla", "salsa", "guacamole"],
    "pizza": ["pepperoni", "margherita", "mushroom", "sausage", "meatball", "garlic", "pesto", "white pizza", "deep dish", "thin crust", "calzone"],
    "ramen": ["tonkotsu", "shoyu", "miso", "spicy ramen", "chashu", "gyoza", "broth", "noodles"],
    "sushi": ["omakase", "roll", "nigiri", "sashimi", "spicy tuna", "salmon", "eel", "uni", "hand roll"],
    "thai": ["pad thai", "green curry", "red curry", "tom yum", "drunken noodles", "pad see ew", "thai tea"],
    "bbq": ["brisket", "ribs", "pulled pork", "burnt ends", "sausage", "smoked chicken", "mac and cheese"],
    "breakfast": ["pancakes", "waffles", "biscuits and gravy", "omelet", "eggs benedict", "hash browns", "french toast", "breakfast burrito"],
    "burgers": ["burger", "cheeseburger", "fries", "onion rings", "milkshake", "smashburger", "bacon"],
}

def mode_label(mode: str) -> str:
    mode = (mode or "").lower().strip()
    if mode == "strict":
        return "Top Local Picks"
    if mode == "best":
        return "Best Available"
    if mode == "hype":
        return "Hype"
    return "Unknown"

def is_chain(name: str) -> bool:
    name = (name or "").lower()
    return any(c in name for c in CHAIN_HINTS)

def places_text_search(query: str) -> list[dict]:
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_KEY,
        "X-Goog-FieldMask": (
            "places.id,"  # ✅ needed so we can fetch reviews for “what to order”
            "places.displayName,"
            "places.formattedAddress,"
            "places.rating,"
            "places.userRatingCount,"
            "places.googleMapsUri,"
            "places.primaryType,"
            "places.types"
        ),
    }
    body = {"textQuery": query}
    r = requests.post(url, headers=headers, json=body, timeout=20)
    r.raise_for_status()
    return r.json().get("places", [])

def place_reviews(place_id: str) -> list[str]:
    """
    Fetch a few review texts for a place.
    If anything fails, return [] (safe fallback).
    """
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
        for rv in reviews[:8]:  # limit
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

def stable_pick_index(s: str, n: int) -> int:
    h = hashlib.md5(s.encode("utf-8")).hexdigest()
    return int(h[:8], 16) % n

def why_line(mode: str, name: str, rating: float, reviews: int) -> str:
    mode = (mode or "").lower().strip()
    key = f"{mode}|{name}|{rating}|{reviews}"

    if mode == "strict":
        options = [
            "This one feels like a real local favorite — the numbers back it up.",
            "Quiet winner energy: strong rating, deep reviews, no chain vibes.",
            "If you only try one, start here. It’s a safe bet with real proof.",
            "Locals keep returning here — you can see it in the review depth.",
            "High confidence pick: people love it *and* enough people have weighed in.",
        ]
        return options[stable_pick_index(key, len(options))]

    if mode == "best":
        options = [
            "Solid choice for this area — it passes the “locals actually go here” test.",
            "Good everyday pick: strong enough reviews that it’s not a gamble.",
            "This is the kind of place you’d hear about from someone who lives nearby.",
            "Not fancy talk — just a dependable spot with real-world proof.",
            "If the town is small, this is exactly the type of pick you want.",
        ]
        return options[stable_pick_index(key, len(options))]

    options = [
        "This one has buzz — people are actively talking about it.",
        "Crowd magnet energy: more popular than average around here.",
        "This is the “everyone’s heard of it” type of pick — for better or worse.",
        "If you want the trending option, this is the lane.",
        "High visibility spot: lots of attention *and* still rated well.",
    ]
    return options[stable_pick_index(key, len(options))]

def normalize_text(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def most_mentioned_dish(review_texts: list[str], cuisine: str | None) -> str | None:
    """
    Returns a dish keyword that shows up the most in review texts.
    If nothing matches, returns None.
    """
    if not review_texts:
        return None

    c = (cuisine or "").strip().lower()
    keywords = DISH_KEYWORDS.get(c)

    # If cuisine isn’t in our keyword list, we can’t safely guess a dish
    if not keywords:
        return None

    joined = " ".join(normalize_text(t) for t in review_texts)

    counts = []
    for kw in keywords:
        k = normalize_text(kw)
        if not k:
            continue
        # simple count; safe and fast
        n = joined.count(k)
        if n > 0:
            counts.append((n, kw))

    if not counts:
        return None

    counts.sort(reverse=True, key=lambda x: x[0])
    return counts[0][1]

# ✅ Rotating “what people order” lines (human, calm, trustworthy)
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
    """
    If we found a dish from reviews:
      Sentence — dish.
    Otherwise:
      a gentle fallback.
    """
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

        picks.append({
            "key": key_for(p),
            "place_id": pid,  # keep internally so we can fetch reviews later
            "name": name,
            "location": addr,
            "rating": rating,
            "reviews": reviews,
            "confidence": conf,
            "confidence_explainer": confidence_explainer(conf),
            "why": "",
            "order": "Ask staff: “What do regulars order most?”",
            "links": links_for(p),
            "also_in_strict": False,
            "hype_reason": hype_reason(rating, reviews),
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
) -> tuple[list[dict], bool]:
    picks = build_picks(places, min_rating, min_reviews, sorter, allowed_types)
    if allowed_types and len(picks) < want_at_least:
        picks = build_picks(places, min_rating, min_reviews, sorter, None)
        return picks, True
    return picks, False

def add_order_from_reviews(picks: list[dict], cuisine: str | None):
    """
    For the final 5 picks, fetch reviews and set the order line.
    Safe fallback if reviews aren’t available.
    """
    for p in picks:
        pid = (p.get("place_id") or "").strip()
        texts = place_reviews(pid)
        dish = most_mentioned_dish(texts, cuisine)
        p["order"] = order_line(p.get("name", ""), dish)

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

    strict_places = places_text_search(strict_query)
    strict_picks, _ = build_with_type_fallback(strict_places, 4.3, 150, score_lrs, allowed_types, 3)
    strict_picks = strict_picks[:5]
    strict_keys = set([p["key"] for p in strict_picks])

    if mode == "strict":
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
            "limitation_note": None,
            "debug": {"mode": mode, "mode_label": mode_label(mode), "final_count": len(strict_picks)}
        }

    if mode == "best":
        best_places = places_text_search(best_query)
        picks, _ = build_with_type_fallback(best_places, 4.1, 30, score_lrs, allowed_types, 3)
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
            "limitation_note": None,
            "debug": {"mode": mode, "mode_label": mode_label(mode), "final_count": len(picks)}
        }

    if mode == "hype":
        hype_places = places_text_search(hype_query)
        picks, _ = build_with_type_fallback(hype_places, 4.0, 80, score_hype, allowed_types, 3)

        used_hype_fallback = False
        if len(picks) < 3:
            used_hype_fallback = True
            picks, _ = build_with_type_fallback(hype_places, 3.8, 20, score_hype, allowed_types, 3)

        picks = prefer_new_first(picks, strict_keys)

        add_order_from_reviews(picks, cuisine)
        for p in picks:
            p["why"] = why_line("hype", p["name"], float(p["rating"]), int(p["reviews"]))
            p.pop("key", None)
            p.pop("place_id", None)

        limitation = None
        if used_hype_fallback:
            limitation = "Small-town problem: not many big-buzz spots, so I widened the net a little."

        return {
            "query": hype_query,
            "mode": mode,
            "mode_label": mode_label(mode),
            "picks": picks,
            "limitation_note": limitation,
            "debug": {"mode": mode, "mode_label": mode_label(mode), "final_count": len(picks)}
        }

    return {"error": "mode must be: strict, best, or hype"}
