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

CUISINE_TYPE_LOCK = {
    "pizza": {"pizza_restaurant"},
    "tacos": {"mexican_restaurant"},
    "ramen": {"ramen_restaurant", "japanese_restaurant"},
    "sushi": {"sushi_restaurant", "japanese_restaurant"},
    "thai": {"thai_restaurant"},
    "bbq": {"barbecue_restaurant"},
    "breakfast": {"breakfast_restaurant"},
    "burgers": {"hamburger_restaurant"},

    "italian": {"italian_restaurant"},
    "japanese": {"japanese_restaurant"},
    "mexican": {"mexican_restaurant"},
    "chinese": {"chinese_restaurant"},
    "indian": {"indian_restaurant"},
    "american": {"american_restaurant"},
    "korean": {"korean_restaurant"},
    "french": {"french_restaurant"},
    "greek": {"greek_restaurant"},
    "mediterranean": {"mediterranean_restaurant"},
    "vietnamese": {"vietnamese_restaurant"},
    "spanish": {"spanish_restaurant"},
    "middle eastern": {"middle_eastern_restaurant"},
    "middle_eastern": {"middle_eastern_restaurant"},
    "seafood": {"seafood_restaurant"},
    "filipino": {"filipino_restaurant"},
    "peruvian": {"peruvian_restaurant"},
    "cajun": {"cajun_restaurant"},
    "cajun/creole": {"cajun_restaurant"},
    "creole": {"cajun_restaurant"},

    "drinks": {"bar", "cafe", "coffee_shop"},
}

# Words we look for in reviews to guess “what to order”
DISH_KEYWORDS = {
    "tacos": [
        "tacos", "street tacos", "birria", "quesabirria", "al pastor", "carnitas",
        "carne asada", "pollo asado", "barbacoa", "lengua", "chorizo",
        "fish taco", "shrimp taco", "breakfast taco", "taco plate",
        "burrito", "breakfast burrito", "california burrito", "bean and cheese",
        "quesadilla", "mulitas", "torta", "nachos", "chips and salsa",
        "guacamole", "salsa", "horchata", "agua fresca", "menudo",
    ],
    "mexican": [
        "tacos", "burrito", "breakfast burrito", "quesadilla", "nachos",
        "tamales", "enchiladas", "fajitas", "carne asada", "al pastor",
        "carnitas", "birria", "chile relleno", "pozole", "menudo",
        "mole", "torta", "ceviche", "coctel de camaron", "aguachile",
        "sopes", "gorditas", "tostadas", "chilaquiles", "elote",
        "guacamole", "salsa", "horchata", "agua fresca", "margarita",
    ],
    "italian": [
        "pizza", "margherita", "pepperoni", "sausage pizza", "white pizza",
        "pasta", "spaghetti", "meatballs", "lasagna", "bolognese",
        "carbonara", "alfredo", "pesto", "gnocchi", "ravioli",
        "fettuccine", "penne vodka", "cacio e pepe", "clam pasta", "seafood pasta",
        "chicken parmesan", "eggplant parmesan", "veal parmesan", "bruschetta",
        "caprese", "calamari", "tiramisu", "cannoli", "garlic bread", "antipasto",
    ],
    "pizza": [
        "pizza", "pepperoni", "margherita", "sausage", "meatball", "mushroom",
        "white pizza", "sicilian", "grandma slice", "new york slice", "deep dish",
        "thin crust", "detroit style", "wood fired", "neapolitan", "calzone",
        "stromboli", "garlic knots", "pepperoni slice", "supreme", "hawaiian",
        "four cheese", "buffalo chicken", "pesto", "ricotta", "prosciutto",
        "veggie pizza", "extra crispy", "gluten free", "slice", "pie",
    ],
    "japanese": [
        "ramen", "tonkotsu", "shoyu", "miso ramen", "spicy ramen",
        "udon", "tempura udon", "soba", "gyoza", "karaage",
        "katsu", "tonkatsu", "chicken katsu", "yakitori", "teriyaki",
        "donburi", "gyudon", "oyakodon", "curry", "katsu curry",
        "sushi", "nigiri", "sashimi", "hand roll", "roll",
        "chirashi", "omakase", "unagi", "matcha", "mochi",
    ],
    "ramen": [
        "ramen", "tonkotsu", "shoyu", "miso", "spicy ramen",
        "tsukemen", "shio", "black garlic", "chashu", "pork belly",
        "soft egg", "ajitama", "gyoza", "karaage", "broth",
        "noodles", "extra noodles", "spicy miso", "garlic", "corn",
        "butter", "narutomaki", "bamboo shoots", "bean sprouts",
        "rice bowl", "donburi", "takoyaki", "edamame",
        "yakitori", "tempura", "onigiri",
    ],
    "sushi": [
        "sushi", "omakase", "nigiri", "sashimi", "hand roll",
        "spicy tuna", "salmon", "eel", "unagi", "yellowtail",
        "hamachi", "tuna", "maguro", "albacore", "shrimp",
        "tempura roll", "california roll", "dragon roll", "rainbow roll",
        "uni", "ikura", "scallop", "octopus", "sea urchin",
        "miso soup", "edamame", "gyoza", "chirashi",
        "poke", "rice bowl", "bento",
    ],
    "chinese": [
        "dumplings", "potstickers", "fried rice", "chow mein", "lo mein",
        "kung pao chicken", "orange chicken", "general tso", "mapo tofu",
        "sweet and sour", "hot and sour soup", "wonton soup", "wontons",
        "bbq pork", "char siu", "pork belly", "beef and broccoli",
        "egg rolls", "spring rolls", "dan dan noodles", "hand pulled noodles",
        "xiao long bao", "soup dumplings", "sichuan", "spicy", "salt and pepper",
        "tea", "boba", "milk tea", "peking duck", "scallion pancake",
    ],
    "indian": [
        "butter chicken", "tikka masala", "chicken tikka", "biryani", "tandoori",
        "naan", "garlic naan", "paratha", "samosa", "pakora",
        "saag", "palak paneer", "paneer", "chana masala", "dal",
        "dal makhani", "vindaloo", "korma", "madras", "curry",
        "dosa", "idli", "sambar", "chutney", "rasam",
        "lamb curry", "goat curry", "rogan josh", "mango lassi", "chai",
    ],
    "american": [
        "burger", "cheeseburger", "smashburger", "double burger", "fries",
        "onion rings", "milkshake", "fried chicken", "wings", "tenders",
        "bbq", "brisket", "ribs", "pulled pork", "mac and cheese",
        "biscuits and gravy", "pancakes", "waffles", "french toast", "hash browns",
        "breakfast burrito", "omelet", "eggs benedict", "steak", "ribeye",
        "prime rib", "meatloaf", "grilled cheese", "chili", "clam chowder",
    ],
    "burgers": [
        "burger", "cheeseburger", "smashburger", "double burger", "bacon burger",
        "mushroom burger", "patty melt", "fries", "curly fries", "sweet potato fries",
        "onion rings", "milkshake", "shake", "house burger", "classic burger",
        "lettuce wrap", "chicken sandwich", "spicy chicken sandwich",
        "sliders", "loaded fries", "garlic fries", "chili fries",
        "bbq burger", "jalapeno burger", "avocado burger", "blue cheese",
        "truffle fries", "mac and cheese", "tater tots", "combo", "kids burger",
    ],
    "bbq": [
        "bbq", "brisket", "ribs", "pulled pork", "burnt ends",
        "sausage", "smoked chicken", "smoked turkey", "tri tip", "beef rib",
        "pork ribs", "rib plate", "bbq sandwich", "bbq sauce", "dry rub",
        "mac and cheese", "coleslaw", "baked beans", "cornbread", "potato salad",
        "smoked mac", "pickles", "jalapeno", "hot links", "smokehouse",
        "bbq platter", "brisket sandwich", "pulled pork sandwich", "banana pudding", "peach cobbler",
    ],
    "thai": [
        "pad thai", "pad see ew", "drunken noodles", "tom yum", "tom kha",
        "green curry", "red curry", "panang curry", "massaman curry", "thai basil",
        "basil chicken", "larb", "papaya salad", "som tam", "fried rice",
        "thai fried rice", "crispy pork", "satay", "spring rolls", "egg rolls",
        "pad kra pao", "pad prik king", "thai tea", "sticky rice", "mango sticky rice",
        "coconut rice", "boat noodles", "noodles", "spicy", "mild",
    ],
    "korean": [
        "kbbq", "korean bbq", "bulgogi", "galbi", "short ribs",
        "bibimbap", "kimchi", "kimchi stew", "soondubu", "tofu stew",
        "tteokbokki", "kimbap", "japchae", "fried chicken", "korean fried chicken",
        "ramen", "budae jjigae", "naengmyeon", "cold noodles", "mandu",
        "pajeon", "kimchi pancakes", "bossam", "samgyeopsal", "pork belly",
        "ssam", "banchan", "gochujang", "soju", "rice cakes",
    ],
    "vietnamese": [
        "pho", "bun bo hue", "banh mi", "spring rolls", "egg rolls",
        "vermicelli", "bun", "rice plate", "com tam", "broken rice",
        "grilled pork", "lemongrass chicken", "shaking beef", "bo luc lac",
        "bun cha", "bun rieu", "noodle soup", "fish sauce", "nuoc cham",
        "goi", "papaya salad", "fried rice", "garlic noodles", "pork belly",
        "shrimp", "beef pho", "chicken pho", "iced coffee", "ca phe sua da",
        "milk tea", "boba", "che",
    ],
    "greek": [
        "gyro", "souvlaki", "falafel", "hummus", "tzatziki",
        "greek salad", "spanakopita", "moussaka", "lamb", "chicken pita",
        "pita", "feta", "dolma", "dolmades", "baklava",
        "skewer", "kebab", "rice plate", "lemon chicken", "avgolemono",
        "orzo", "grilled octopus", "calamari", "fries", "pita chips",
        "dip", "meze", "tzatziki sauce", "shawarma", "tzatziki bowl",
    ],
    "mediterranean": [
        "shawarma", "gyro", "falafel", "hummus", "kebab",
        "pita", "rice bowl", "chicken shawarma", "beef shawarma", "lamb",
        "tzatziki", "garlic sauce", "toum", "tabbouleh", "fattoush",
        "greek salad", "baba ganoush", "dolma", "grape leaves", "lentil soup",
        "spanakopita", "halal plate", "chicken plate", "kofta", "kofte",
        "baklava", "knafeh", "labneh", "zaatar", "manakish",
    ],
    "middle eastern": [
        "shawarma", "falafel", "hummus", "kebab", "kofta",
        "pita", "toum", "garlic sauce", "tabbouleh", "fattoush",
        "baba ganoush", "labneh", "zaatar", "manakish", "kibbeh",
        "mujadara", "lentil soup", "chicken plate", "beef plate", "rice plate",
        "knafeh", "baklava", "sfiha", "sumac", "pickles",
        "grape leaves", "dolma", "shish tawook", "harissa", "pomegranate",
    ],
    "middle_eastern": [
        "shawarma", "falafel", "hummus", "kebab", "kofta",
        "pita", "toum", "garlic sauce", "tabbouleh", "fattoush",
        "baba ganoush", "labneh", "zaatar", "manakish", "kibbeh",
        "mujadara", "lentil soup", "chicken plate", "beef plate", "rice plate",
        "knafeh", "baklava", "sfiha", "sumac", "pickles",
        "grape leaves", "dolma", "shish tawook", "harissa", "pomegranate",
    ],
    "french": [
        "croissant", "baguette", "quiche", "crepe", "galette",
        "onion soup", "french onion soup", "steak frites", "duck confit", "coq au vin",
        "bouillabaisse", "salad nicoise", "escargot", "moules frites", "brie",
        "cheese plate", "charcuterie", "ratatouille", "cassoulet", "creme brulee",
        "tarte tatin", "macarons", "bistro", "pate", "terrine",
        "cafe", "espresso", "latte", "pain au chocolat", "omelet",
    ],
    "spanish": [
        "tapas", "paella", "patatas bravas", "croquetas", "jamon",
        "tortilla espanola", "gazpacho", "pintxos", "pan con tomate", "manchego",
        "garlic shrimp", "gambas al ajillo", "pulpo", "octopus", "chorizo",
        "sangria", "wine", "rioja", "cava", "calamari",
        "fried squid", "seafood", "prawns", "aioli", "flan",
        "churros", "hot chocolate", "basque cheesecake", "cheesecake", "tarta",
    ],
    "seafood": [
        "fish", "fish and chips", "shrimp", "prawns", "lobster",
        "crab", "oysters", "clam chowder", "clam", "mussels",
        "scallops", "ceviche", "poke", "sashimi", "grilled fish",
        "fried fish", "salmon", "tuna", "ahi", "halibut",
        "cioppino", "seafood boil", "crab boil", "shrimp boil", "seafood platter",
        "calamari", "octopus", "squid", "fish tacos", "shrimp tacos",
    ],
    "cajun": [
        "gumbo", "jambalaya", "crawfish", "shrimp", "po boy",
        "etouffee", "red beans and rice", "dirty rice", "fried catfish", "catfish",
        "blackened", "cajun", "creole", "boil", "seafood boil",
        "crab", "corn", "sausage", "andouille", "beignets",
        "boudin", "grits", "shrimp and grits", "oyster", "fried oysters",
        "hot sauce", "cajun fries", "crawfish pie", "praline", "bread pudding",
    ],
    "cajun/creole": [
        "gumbo", "jambalaya", "crawfish", "po boy", "etouffee",
        "red beans and rice", "dirty rice", "blackened", "andouille", "boudin",
        "shrimp and grits", "fried catfish", "seafood boil", "crab boil", "oysters",
        "fried oysters", "corn", "sausage", "hot sauce", "cajun",
        "creole", "beignets", "pralines", "bread pudding", "banana pudding",
        "catfish", "shrimp", "crab", "rice", "gumbo ya ya",
    ],
    "creole": [
        "gumbo", "jambalaya", "etouffee", "red beans and rice", "dirty rice",
        "shrimp", "crab", "oysters", "po boy", "andouille",
        "blackened", "creole", "cajun", "hot sauce", "beignets",
        "bread pudding", "pralines", "catfish", "boil", "seafood boil",
        "corn", "sausage", "grits", "shrimp and grits", "rice",
        "fried oysters", "fried catfish", "gumbo", "jambalaya", "etouffee", "po boy",
    ],
    "filipino": [
        "adobo", "chicken adobo", "pork adobo", "sinigang", "sisig",
        "lechon", "lechon kawali", "kare kare", "pancit", "pancit bihon",
        "lumpia", "bbq skewers", "tocino", "longganisa", "tapsilog",
        "silog", "garlic rice", "halo halo", "ube", "ube ice cream",
        "caldereta", "dinuguan", "bulalo", "tinola", "bistek",
        "kakanin", "puto", "bibingka", "ensaymada", "milk tea",
    ],
    "peruvian": [
        "ceviche", "lomo saltado", "aji de gallina", "pollo a la brasa", "anticuchos",
        "causa", "papa a la huancaina", "arroz con mariscos", "tallarines", "chicha morada",
        "pisco sour", "rocoto", "aji amarillo", "tiradito", "chaufa",
        "seafood", "octopus", "shrimp", "prawn", "steak",
        "rice", "beans", "plantains", "empanada", "soup",
        "grilled chicken", "salsa", "spicy", "dessert", "ceviche mixto",
    ],
    "breakfast": [
        "pancakes", "waffles", "french toast", "biscuits and gravy", "omelet",
        "eggs benedict", "hash browns", "breakfast burrito", "breakfast sandwich", "avocado toast",
        "scramble", "bacon", "sausage", "breakfast plate", "granola",
        "yogurt", "fruit", "bagel", "cream cheese", "coffee",
        "latte", "cappuccino", "mimosas", "bloody mary", "brunch",
        "chilaquiles", "home fries", "toast", "grits", "oatmeal",
    ],
    "steak": [
        "ribeye", "new york strip", "filet mignon", "prime rib", "sirloin",
        "steak frites", "skirt steak", "hanger steak", "t bone", "porterhouse",
        "chimichurri", "au poivre", "mashed potatoes", "baked potato", "creamed spinach",
        "asparagus", "mac and cheese", "lobster tail", "surf and turf", "bone in ribeye",
        "steak sandwich", "carpaccio", "tartare", "caesar salad", "wedge salad",
        "bread", "wine", "old fashioned", "martini", "peppercorn",
    ],
    "fried chicken": [
        "fried chicken", "hot chicken", "chicken sandwich", "spicy chicken sandwich", "wings",
        "tenders", "chicken and waffles", "biscuits", "mac and cheese", "collard greens",
        "cornbread", "gravy", "mashed potatoes", "fries", "slaw",
        "honey", "hot honey", "ranch", "blue cheese", "bbq sauce",
        "buffalo", "nashville", "spicy", "mild", "extra crispy",
        "dark meat", "white meat", "combo", "family meal", "banana pudding",
    ],
    "drinks": [
        "coffee", "iced coffee", "cold brew", "latte", "cappuccino",
        "espresso", "americano", "matcha", "chai", "boba",
        "milk tea", "thai tea", "lemonade", "agua fresca", "horchata",
        "smoothie", "shake", "milkshake", "mocktail", "cocktail",
        "margarita", "paloma", "mojito", "old fashioned", "martini",
        "negroni", "spritz", "beer", "craft beer", "ipa",
    ],
}

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
    R = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def places_text_search(query: str, center: dict | None = None, radius_m: int | None = None) -> list[dict]:
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
            "places.location,"
            "places.businessStatus,"
            "places.currentOpeningHours.openNow"
        ),
    }
    body = {"textQuery": query}

    if center and radius_m:
        body["locationBias"] = {"circle": {"center": center, "radius": int(radius_m)}}

    r = requests.post(url, headers=headers, json=body, timeout=20)
    r.raise_for_status()
    return r.json().get("places", [])

def location_center_from_text(location_text: str) -> dict | None:
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

def is_closed_place(p: dict) -> bool:
    status = (p.get("businessStatus") or "").strip().upper()
    if status in {"CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"}:
        return True

    coh = p.get("currentOpeningHours") or {}
    open_now = coh.get("openNow")
    if open_now is False:
        return True

    return False

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
        if is_closed_place(p):
            continue

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

@app.get("/suggest")
def suggest(
    q: str = Query(..., min_length=2),
    limit: int = Query(6, ge=1, le=10),
):
    if not GOOGLE_KEY:
        return {"error": "Missing GOOGLE_PLACES_API_KEY"}

    try:
        places = places_text_search(q, center=None, radius_m=None)
        suggestions = []

        for p in places[:limit]:
            name = ((p.get("displayName") or {}).get("text") or "").strip()
            addr = (p.get("formattedAddress") or "").strip()
            if not (name or addr):
                continue

            label = addr if addr else name
            suggestions.append({
                "label": label,
                "name": name,
                "address": addr,
            })

        return {"q": q, "suggestions": suggestions}
    except Exception:
        return {"q": q, "suggestions": []}

@app.get("/lrs")
def lrs(
    location: str = Query(...),
    cuisine: str | None = Query(None),
    mode: str = Query("strict"),
):
    if not GOOGLE_KEY:
        return {"error": "Missing GOOGLE_PLACES_API_KEY"}

    mode = (mode or "strict").lower().strip()
    cuisine_clean = (cuisine or "").strip()

    if cuisine_clean.lower() == "drinks":
        base = f"drinks in {location}".strip()
    else:
        base = f"{(cuisine_clean + ' ') if cuisine_clean else ''}restaurants in {location}".strip()

    strict_query = f"best {base}".strip()
    best_query = base
    hype_query = f"popular {base}".strip()

    allowed_types = cuisine_lock_types(cuisine_clean)
    center = location_center_from_text(location)

    if not center:
        return {
            "query": base,
            "mode": mode,
            "mode_label": mode_label(mode),
            "picks": [],
            "limitation_note": "I couldn’t confidently interpret that location. Try adding a nearby city/state (example: 'Downtown San Jose, CA').",
            "debug": {
                "mode": mode,
                "mode_label": mode_label(mode),
                "center_resolved": False,
                "final_count": 0,
                "query_base": base,
                "strict_query": strict_query,
                "best_query": best_query,
                "hype_query": hype_query,
                "cuisine": cuisine_clean,
                "type_lock_active": bool(allowed_types),
                "allowed_types": sorted(list(allowed_types)) if allowed_types else None,
            }
        }

    STRICT_PRIMARY = miles_to_meters(5)
    STRICT_MAX = miles_to_meters(10)

    BEST_PRIMARY = miles_to_meters(10)
    BEST_MAX = miles_to_meters(15)

    HYPE_PRIMARY = miles_to_meters(10)
    HYPE_MAX = miles_to_meters(25)

    center_dbg = {
        "latitude": round(float(center["latitude"]), 6),
        "longitude": round(float(center["longitude"]), 6),
    }

    strict_places = places_text_search(strict_query, center=center, radius_m=STRICT_PRIMARY)
    strict_picks, strict_type_lock_fallback_used = build_with_type_fallback(
        strict_places, 4.3, 150, score_lrs, allowed_types, 3,
        center=center, max_radius_m=STRICT_PRIMARY
    )
    strict_picks = strict_picks[:5]
    strict_keys = set([p["key"] for p in strict_picks])

    if mode == "strict":
        limitation = None
        strict_used_wide = False
        strict_places_wide_len = None
        strict_type_lock_fallback_used_wide = None

        if len(strict_picks) < 3:
            strict_places_wide = places_text_search(strict_query, center=center, radius_m=STRICT_MAX)
            strict_places_wide_len = len(strict_places_wide)
            strict_picks_wide, strict_type_lock_fallback_used_wide = build_with_type_fallback(
                strict_places_wide, 4.3, 150, score_lrs, allowed_types, 3,
                center=center, max_radius_m=STRICT_MAX
            )
            if len(strict_picks_wide) > len(strict_picks):
                strict_picks = strict_picks_wide[:5]
                limitation = "This area is limited for that search, so I widened the search up to 10 miles."
                strict_used_wide = True

        add_order_from_reviews(strict_picks, cuisine_clean)
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
            "debug": {
                "mode": mode,
                "mode_label": mode_label(mode),
                "center_resolved": True,
                "center": center_dbg,
                "query_base": base,
                "strict_query": strict_query,
                "best_query": best_query,
                "hype_query": hype_query,
                "cuisine": cuisine_clean,
                "type_lock_active": bool(allowed_types),
                "allowed_types": sorted(list(allowed_types)) if allowed_types else None,
                "radius_m": {
                    "primary": STRICT_PRIMARY,
                    "max": STRICT_MAX,
                    "used": (STRICT_MAX if strict_used_wide else STRICT_PRIMARY),
                },
                "raw_counts": {
                    "primary": len(strict_places),
                    "wide": strict_places_wide_len,
                },
                "type_lock_fallback_used": strict_type_lock_fallback_used,
                "type_lock_fallback_used_wide": strict_type_lock_fallback_used_wide,
                "widened": strict_used_wide,
                "final_count": len(strict_picks),
            }
        }

    if mode == "best":
        limitation = None

        best_places = places_text_search(best_query, center=center, radius_m=BEST_PRIMARY)
        picks, best_type_lock_fallback_used = build_with_type_fallback(
            best_places, 4.1, 30, score_lrs, allowed_types, 3,
            center=center, max_radius_m=BEST_PRIMARY
        )

        best_used_wide = False
        best_places_wide_len = None
        best_type_lock_fallback_used_wide = None

        if len(picks) < 3:
            best_places_wide = places_text_search(best_query, center=center, radius_m=BEST_MAX)
            best_places_wide_len = len(best_places_wide)
            picks_wide, best_type_lock_fallback_used_wide = build_with_type_fallback(
                best_places_wide, 4.1, 30, score_lrs, allowed_types, 3,
                center=center, max_radius_m=BEST_MAX
            )
            if len(picks_wide) > len(picks):
                picks = picks_wide
                limitation = "This area is limited for that search, so I widened the search up to 15 miles."
                best_used_wide = True

        picks = prefer_new_first(picks, strict_keys)

        add_order_from_reviews(picks, cuisine_clean)
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
            "debug": {
                "mode": mode,
                "mode_label": mode_label(mode),
                "center_resolved": True,
                "center": center_dbg,
                "query_base": base,
                "strict_query": strict_query,
                "best_query": best_query,
                "hype_query": hype_query,
                "cuisine": cuisine_clean,
                "type_lock_active": bool(allowed_types),
                "allowed_types": sorted(list(allowed_types)) if allowed_types else None,
                "radius_m": {
                    "primary": BEST_PRIMARY,
                    "max": BEST_MAX,
                    "used": (BEST_MAX if best_used_wide else BEST_PRIMARY),
                },
                "raw_counts": {
                    "primary": len(best_places),
                    "wide": best_places_wide_len,
                },
                "type_lock_fallback_used": best_type_lock_fallback_used,
                "type_lock_fallback_used_wide": best_type_lock_fallback_used_wide,
                "widened": best_used_wide,
                "final_count": len(picks),
            }
        }

    if mode == "hype":
        limitation = None

        hype_places = places_text_search(hype_query, center=center, radius_m=HYPE_PRIMARY)
        picks, hype_type_lock_fallback_used = build_with_type_fallback(
            hype_places, 4.0, 80, score_hype, allowed_types, 3,
            center=center, max_radius_m=HYPE_PRIMARY
        )

        used_wide = False
        hype_places_wide_len = None
        hype_type_lock_fallback_used_wide = None

        if len(picks) < 3:
            hype_places_wide = places_text_search(hype_query, center=center, radius_m=HYPE_MAX)
            hype_places_wide_len = len(hype_places_wide)
            picks_wide, hype_type_lock_fallback_used_wide = build_with_type_fallback(
                hype_places_wide, 3.8, 20, score_hype, allowed_types, 3,
                center=center, max_radius_m=HYPE_MAX
            )
            if len(picks_wide) > len(picks):
                picks = picks_wide
                used_wide = True

        picks = prefer_new_first(picks, strict_keys)

        add_order_from_reviews(picks, cuisine_clean)
        for p in picks:
            p["why"] = why_line("hype", p["name"], float(p["rating"]), int(p["reviews"]))
            p.pop("key", None)
            p.pop("place_id", None)

        if used_wide:
            limitation = f"{hype_distance_line(location, cuisine_clean)} Showing hype picks up to 25 miles."

        return {
            "query": hype_query,
            "mode": mode,
            "mode_label": mode_label(mode),
            "picks": picks,
            "limitation_note": limitation,
            "debug": {
                "mode": mode,
                "mode_label": mode_label(mode),
                "center_resolved": True,
                "center": center_dbg,
                "query_base": base,
                "strict_query": strict_query,
                "best_query": best_query,
                "hype_query": hype_query,
                "cuisine": cuisine_clean,
                "type_lock_active": bool(allowed_types),
                "allowed_types": sorted(list(allowed_types)) if allowed_types else None,
                "radius_m": {
                    "primary": HYPE_PRIMARY,
                    "max": HYPE_MAX,
                    "used": (HYPE_MAX if used_wide else HYPE_PRIMARY),
                },
                "raw_counts": {
                    "primary": len(hype_places),
                    "wide": hype_places_wide_len,
                },
                "type_lock_fallback_used": hype_type_lock_fallback_used,
                "type_lock_fallback_used_wide": hype_type_lock_fallback_used_wide,
                "widened": used_wide,
                "final_count": len(picks),
            }
        }

    return {"error": "mode must be: strict, best, or hype"}
