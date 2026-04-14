"""
Generate constraint-based gold sheet for the Maven evaluation benchmark.

For each query in queries.jsonl, creates a gold row with:
  - product_type, budget_ceiling, must_have_features,
  - must_not_have_terms, preferred_retailers, expected_price_band,
  - anchor_products, judge_notes

Run:
    python -m evaluation.generate_gold
"""

import json
import re
import pathlib


def _parse_budget(query_text: str) -> tuple[float | None, str | None]:
    """Extract budget ceiling and expected price band from query text."""
    # Match patterns like "under $500", "under 500", "$50-$80"
    m = re.search(r"under\s+\$?([\d,]+)", query_text, re.IGNORECASE)
    if m:
        ceiling = float(m.group(1).replace(",", ""))
        low = max(ceiling * 0.4, 10)
        band = f"${low:.0f}-${ceiling:.0f}"
        return ceiling, band

    m = re.search(r"\$?([\d,]+)\s*-\s*\$?([\d,]+)", query_text)
    if m:
        low = float(m.group(1).replace(",", ""))
        high = float(m.group(2).replace(",", ""))
        return high, f"${low:.0f}-${high:.0f}"

    return None, None


def _extract_must_have(query_text: str, category: str) -> list[str]:
    """Extract must-have features from query text."""
    features = []
    q = query_text.lower()

    # Common feature patterns
    feature_keywords = {
        "noise cancelling": ["noise cancelling", "anc", "noise cancellation"],
        "transparency mode": ["transparency mode", "transparency"],
        "wireless": ["wireless", "bluetooth"],
        "wired": ["wired"],
        "waterproof": ["waterproof", "water resistant", "water-resistant", "ip67", "ipx7", "ip68", "water resistance"],
        "long battery": ["long battery", "all-day battery", "battery life"],
        "USB-C": ["usb-c", "usb c", "type-c"],
        "HEPA filter": ["hepa"],
        "self-emptying": ["self-emptying", "self emptying"],
        "self-washing mop": ["self-washing mop"],
        "LiDAR navigation": ["lidar"],
        "hot-swappable": ["hot-swappable", "hot swap", "hotswap"],
        "mechanical": ["mechanical"],
        "ergonomic": ["ergonomic"],
        "standing desk": ["standing desk", "sit-stand", "sit stand"],
        "4K": ["4k"],
        "1440p": ["1440p"],
        "1080p": ["1080p"],
        "OLED": ["oled"],
        "AMOLED": ["amoled"],
        "120Hz": ["120hz"],
        "144Hz": ["144hz"],
        "165Hz": ["165hz"],
        "HDR": ["hdr600", "hdr"],
        "Thunderbolt": ["thunderbolt"],
        "HDMI 2.1": ["hdmi 2.1"],
        "DisplayPort": ["displayport"],
        "fingerprint": ["fingerprint"],
        "GPS": ["gps"],
        "NFC": ["nfc"],
        "5G": ["5g"],
        "dedicated GPU": ["dedicated gpu", "rtx 4060", "rtx 4070", "rtx"],
        "touch screen": ["stylus", "convertible", "2-in-1"],
        "IPS panel": ["ips panel", "ips", "nano-ips"],
        "color accurate": ["color-accurate", "color accurate", "srgb", "dci-p3", "color-grading"],
        "programmable": ["programmable", "presets"],
        "smart home compatible": ["alexa", "google home", "matter"],
        "no subscription": ["no monthly fee", "no subscription", "no monthly", "local storage"],
        "app control": ["app control", "app-guided", "companion app", "app tracking"],
        "detachable mic": ["detachable mic", "detachable boom"],
        "PID temperature": ["pid"],
        "ionic": ["ionic"],
        "pressure sensor": ["pressure sensor"],
        "spatial audio": ["spatial audio"],
        "microphone": ["with microphone", "with mic", "boom mic", "built-in mic"],
        "wireless charging": ["wireless charging", "wireless charging case"],
        "multipoint": ["multipoint"],
        "good camera": ["good camera", "excellent camera", "best camera", "camera phone"],
        "optical zoom": ["optical zoom"],
        "night mode": ["night mode"],
        "swim tracking": ["swim tracking"],
        "ECG": ["ecg"],
        "blood oxygen": ["blood oxygen", "spo2"],
        "sleep tracking": ["sleep tracking"],
        "obstacle avoidance": ["obstacle avoidance"],
        "no-go zones": ["no-go zones"],
        "pet hair friendly": ["pet hair", "for pets", "with pets", "large dogs"],
        "rotisserie": ["rotisserie"],
        "dehydrator": ["dehydrator", "dehydrate"],
        "built-in grinder": ["built-in grinder"],
        "steaming wand": ["steaming wand", "steam wand", "latte art"],
        "convection": ["convection"],
        "duplex scanning": ["double-sided"],
        "gasket mount": ["gasket mount", "gasket"],
        "PBT keycaps": ["pbt keycaps", "pbt"],
        "hall effect sticks": ["hall effect"],
        "KVM switch": ["kvm"],
        "USB hub": ["usb hub", "usb ports"],
        "power delivery": ["power delivery", "65w", "90w"],
        "pivot stand": ["pivot"],
        "color night vision": ["color night vision"],
        "package detection": ["package detection"],
        "motion sensor": ["motion sensor", "motion sensors"],
        "geofencing": ["geofencing"],
        "SOS button": ["sos button", "sos"],
        "always-on display": ["always-on display"],
        "offline music": ["offline spotify", "offline music"],
        "adjustable lumbar": ["adjustable lumbar", "lumbar support"],
        "cable management": ["cable management", "cable tray"],
        "anti-fatigue mat": ["anti-fatigue mat"],
        "bamboo top": ["bamboo"],
        "UV sanitizing": ["uv sanitizing", "uv sanitiz"],
        "infrared": ["infrared"],
        "brushless motor": ["brushless motor"],
        "replaceable parts": ["replaceable ear pads", "replaceable", "detachable cable"],
        "lightweight": ["lightweight", "under 1.5 pounds", "sub-50g", "under 300g", "under 3.5 pounds"],
        "quiet operation": ["quiet", "noise level under"],
        "fast charging": ["fast charging", "67w"],
        "stereo speakers": ["stereo speakers"],
        "expandable storage": ["expandable storage"],
        "Linux compatible": ["linux support", "linux-friendly", "linux compatible"],
        "SD card slot": ["sd card slot"],
        "good keyboard": ["good keyboard"],
        "dual SIM": ["dual-sim", "dual sim"],
        "thermal camera": ["thermal camera"],
        "ECC memory": ["ecc memory", "ecc"],
        "docking station": ["docking station"],
    }

    for feature, patterns in feature_keywords.items():
        if any(p in q for p in patterns):
            features.append(feature)

    # Extract specific numeric features
    m = re.search(r"(\d+)\s*(?:hour|hr)s?\s*battery", q)
    if m:
        features.append(f"{m.group(1)}+ hour battery")

    m = re.search(r"(\d+)\s*(?:gb|tb)\s*(ram|ssd|storage)", q, re.IGNORECASE)
    if m:
        features.append(f"{m.group(1)}{'GB' if 'gb' in m.group(0).lower() else 'TB'} {m.group(2).upper()}")

    # Extract "X-inch" form factors
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-\s*)?inch", q)
    if m:
        features.append(f"{m.group(1)}-inch")

    # Extract use-case hints
    use_cases = {
        "for running": "suitable for running",
        "for gym": "suitable for gym",
        "for travel": "suitable for travel",
        "for camping": "suitable for camping",
        "for gaming": "suitable for gaming",
        "for streaming": "suitable for streaming",
        "for commuting": "suitable for commuting",
        "for programming": "suitable for programming",
        "for coding": "suitable for coding",
        "for video editing": "suitable for video editing",
        "for photo editing": "suitable for photo editing",
        "for vlogging": "suitable for vlogging",
        "for beginners": "suitable for beginners",
        "for students": "suitable for students",
        "for seniors": "suitable for seniors",
        "for kids": "suitable for kids",
        "for office": "suitable for office",
        "for home": "suitable for home use",
        "for small kitchen": "compact size",
        "for small room": "compact size",
        "for small desk": "compact size",
        "for apartment": "suitable for apartments",
    }
    for trigger, feature in use_cases.items():
        if trigger in q:
            features.append(feature)

    return features[:10]  # cap at 10 features


def _extract_product_type(query_text: str, category: str) -> str:
    """Extract the product type from query text."""
    q = query_text.lower()

    # Ordered by priority — longer/more-specific matches first.
    # Each entry is (pattern, product_type). Patterns are checked in order.
    type_rules: list[tuple[str, str]] = [
        # Audio
        ("bone conduction headphones", "bone conduction headphones"),
        ("bone conduction", "bone conduction headphones"),
        ("wireless earbuds", "wireless earbuds"),
        ("wired earbuds", "wired earbuds"),
        ("noise cancelling earbuds", "wireless earbuds"),
        ("true wireless earbuds", "wireless earbuds"),
        ("earbuds", "earbuds"),
        ("bluetooth speaker", "bluetooth speaker"),
        ("party speaker", "bluetooth speaker"),
        ("over-ear headphones", "over-ear headphones"),
        ("noise cancelling headphones", "noise cancelling headphones"),
        ("studio monitor headphones", "studio headphones"),
        ("headphones", "headphones"),
        ("portable dac", "DAC/amp"),
        ("dac amp", "DAC/amp"),
        ("speaker", "bluetooth speaker"),
        # Laptops (before "phone" to prevent "chromebook" → "phone")
        ("chromebook", "chromebook"),
        ("workstation laptop", "workstation laptop"),
        ("gaming laptop", "gaming laptop"),
        ("ultrabook", "ultrabook"),
        ("macbook air alternative", "laptop"),
        ("2-in-1", "2-in-1 laptop"),
        ("convertible laptop", "2-in-1 laptop"),
        ("laptop", "laptop"),
        # Phones & wearables
        ("kids' smartwatch", "kids smartwatch"),
        ("kids smartwatch", "kids smartwatch"),
        ("fitness tracker", "fitness tracker"),
        ("fitness band", "fitness tracker"),
        ("smartwatch", "smartwatch"),
        ("camera phone", "smartphone"),
        ("rugged phone", "rugged smartphone"),
        ("compact phone", "smartphone"),
        ("smartphone", "smartphone"),
        ("phone", "smartphone"),
        # Kitchen (longer matches before shorter)
        ("semi-automatic espresso", "espresso machine"),
        ("espresso machine", "espresso machine"),
        ("coffee maker", "coffee maker"),
        ("coffee grinder", "coffee grinder"),
        ("cold brew coffee", "cold brew maker"),
        ("cold brew", "cold brew maker"),
        ("pour-over", "pour-over coffee set"),
        ("high-speed blender", "blender"),
        ("air fryer oven", "air fryer oven combo"),
        ("air fryer", "air fryer"),
        ("toaster oven", "toaster oven"),
        ("countertop oven", "countertop oven"),
        ("blender", "blender"),
        ("electric kettle", "electric kettle"),
        ("kettle", "electric kettle"),
        ("microwave", "microwave"),
        ("food processor", "food processor"),
        ("stand mixer", "stand mixer"),
        ("slow cooker", "slow cooker"),
        ("induction cooktop", "induction cooktop"),
        ("kitchen system", "all-in-one kitchen system"),
        # Cleaning
        ("robot vacuum", "robot vacuum"),
        ("cordless vacuum", "cordless vacuum"),
        ("handheld vacuum", "handheld vacuum"),
        ("car vacuum", "car vacuum"),
        ("stick vacuum", "stick vacuum"),
        ("wet-dry vacuum", "wet-dry vacuum"),
        ("vacuum", "vacuum"),
        ("steam mop", "steam mop"),
        ("steam cleaner", "steam cleaner"),
        ("steam cleaning", "steam cleaner"),
        ("carpet extractor", "carpet extractor"),
        ("carpet cleaner", "carpet cleaner"),
        ("ultrasonic", "ultrasonic cleaner"),
        # Gaming (before generic "keyboard")
        ("gaming mouse", "gaming mouse"),
        ("gaming keyboard", "gaming keyboard"),
        ("mechanical keyboard", "mechanical keyboard"),
        ("gaming headset", "gaming headset"),
        ("gaming controller", "gaming controller"),
        ("gaming chair", "gaming chair"),
        ("capture card", "capture card"),
        ("streaming setup", "streaming setup"),
        ("stream deck", "stream deck"),
        ("macro pad", "macro pad"),
        ("webcam", "webcam"),
        ("mousepad", "mousepad"),
        ("mouse pad", "mousepad"),
        ("controller", "gaming controller"),
        ("keyboard", "keyboard"),
        # Monitors (before generic matches)
        ("portable monitor", "portable monitor"),
        ("ultrawide", "ultrawide monitor"),
        ("triple monitor", "triple monitor setup"),
        ("dual monitor stand", "monitor stand"),
        ("monitor stand", "monitor stand"),
        ("monitor arm", "monitor arm"),
        ("monitor light", "monitor light bar"),
        ("monitor", "monitor"),
        # Personal care
        ("sonic toothbrush", "electric toothbrush"),
        ("electric toothbrush", "electric toothbrush"),
        ("toothbrush", "electric toothbrush"),
        ("hair dryer", "hair dryer"),
        ("rotary shaver", "electric shaver"),
        ("electric shaver", "electric shaver"),
        ("shaver", "electric shaver"),
        ("hair straightener", "hair straightener"),
        ("water flosser", "water flosser"),
        ("hair clipper", "hair clipper"),
        ("grooming kit", "grooming kit"),
        ("ipl hair removal", "IPL device"),
        ("ipl", "IPL device"),
        ("facial cleansing", "facial cleansing brush"),
        ("eyelash curler", "heated eyelash curler"),
        ("light therapy mask", "LED light therapy mask"),
        ("light therapy", "LED light therapy mask"),
        ("microcurrent", "microcurrent device"),
        ("trimmer", "trimmer"),
        # Home office ("microphone" must come AFTER audio earbuds entries)
        ("video conferencing", "video conferencing kit"),
        ("desk lamp", "desk lamp"),
        ("office chair", "office chair"),
        ("standing desk converter", "standing desk converter"),
        ("desk converter", "standing desk converter"),
        ("standing desk", "standing desk"),
        ("desk setup", "desk setup"),
        ("keyboard and mouse", "keyboard and mouse combo"),
        ("mouse pad", "mouse pad"),
        ("wrist rest", "mouse pad"),
        ("usb hub", "USB hub"),
        ("document scanner", "document scanner"),
        ("vertical mouse", "vertical mouse"),
        ("desk shelf", "desk shelf riser"),
        ("usb microphone", "USB microphone"),
        ("condenser microphone", "USB microphone"),
        ("microphone", "USB microphone"),
        # Smart home
        ("smart home starter", "smart home starter kit"),
        ("security system", "smart security system"),
        ("smart thermostat", "smart thermostat"),
        ("video doorbell", "video doorbell"),
        ("doorbell camera", "video doorbell"),
        ("doorbell", "video doorbell"),
        ("security camera", "security camera"),
        ("smart lock", "smart lock"),
        ("door lock", "smart lock"),
        ("smart bulb", "smart bulb"),
        ("smart plug", "smart plug"),
        ("smart speaker", "smart speaker"),
        ("light strip", "smart light strip"),
        ("mesh wifi", "mesh WiFi system"),
        ("smart blinds", "smart blinds"),
        ("smoke detector", "smart smoke detector"),
        ("smoke and co", "smart smoke detector"),
        ("irrigation", "smart irrigation controller"),
        ("pathway lights", "smart outdoor lighting"),
        ("outdoor smart lighting", "smart outdoor lighting"),
        ("outdoor lighting", "smart outdoor lighting"),
    ]

    # Check rules in order (first match wins)
    for pattern, product_type in type_rules:
        if pattern in q:
            return product_type

    # Fallback — use category name
    return category.replace("_", " ")


def _extract_must_not_have(query_text: str, product_type: str) -> list[str]:
    """Extract terms that indicate a wrong product category."""
    terms = []
    q = query_text.lower()
    pt = product_type.lower()

    # Basic exclusions based on product type
    if "earbuds" in pt:
        terms.extend(["over-ear headphones", "speaker", "soundbar"])
    elif "headphones" in pt and "over-ear" in q:
        terms.extend(["earbuds", "in-ear", "speaker"])
    elif "speaker" in pt:
        terms.extend(["headphones", "earbuds"])
    elif "laptop" in pt:
        terms.extend(["desktop", "tablet", "phone"])
    elif "phone" in pt or "smartphone" in pt:
        terms.extend(["laptop", "tablet"])
    elif "smartwatch" in pt:
        terms.extend(["phone", "fitness band"])
    elif "robot vacuum" in pt:
        terms.extend(["cordless vacuum", "upright vacuum", "handheld vacuum"])
    elif "cordless vacuum" in pt:
        terms.extend(["robot vacuum"])

    # Budget exclusions
    if "budget" in q or "cheap" in q or "affordable" in q:
        terms.append("premium")

    return terms[:5]


def _extract_preferred_retailers(query_text: str) -> list[str]:
    """Extract retailer preferences from query text."""
    retailers = []
    q = query_text.lower()
    if "amazon" in q:
        retailers.append("Amazon")
    if "walmart" in q:
        retailers.append("Walmart")
    if "best buy" in q or "bestbuy" in q:
        retailers.append("Best Buy")
    if "target" in q:
        retailers.append("Target")
    return retailers


def _extract_anchor_products(query_text: str, product_type: str, category: str) -> list[str]:
    """Suggest 0-3 well-known products that would be correct answers."""
    pt = product_type.lower()
    q = query_text.lower()
    anchors = []

    # Only provide anchors for well-known product categories
    anchor_db = {
        "wireless earbuds": ["Samsung Galaxy Buds FE", "JBL Tune Buds", "Sony WF-C700N"],
        "noise cancelling headphones": ["Sony WH-1000XM5", "Bose QuietComfort Ultra", "Apple AirPods Max"],
        "bluetooth speaker": ["JBL Flip 6", "Anker Soundcore Motion+", "Ultimate Ears WONDERBOOM 3"],
        "laptop": ["Acer Aspire 5", "Lenovo IdeaPad 3", "HP Pavilion 15"],
        "chromebook": ["Acer Chromebook 314", "Lenovo IdeaPad Duet", "HP Chromebook 14"],
        "smartphone": ["Samsung Galaxy A54", "Google Pixel 7a", "OnePlus Nord N30"],
        "smartwatch": ["Samsung Galaxy Watch 6", "Apple Watch SE", "Garmin Venu Sq 2"],
        "fitness tracker": ["Fitbit Inspire 3", "Xiaomi Smart Band 8", "Garmin Vivosmart 5"],
        "robot vacuum": ["iRobot Roomba Combo", "roborock Q7 Max", "Ecovacs Deebot N10"],
        "air fryer": ["Cosori Pro II", "Ninja AF101", "Instant Vortex"],
        "espresso machine": ["Breville Bambino Plus", "De'Longhi Dedica", "Gaggia Classic Pro"],
        "gaming mouse": ["Logitech G502 X", "Razer DeathAdder V3", "SteelSeries Aerox 3"],
        "gaming keyboard": ["Keychron K8", "Royal Kludge RK84", "Redragon K552"],
        "monitor": ["Dell S2722QC", "LG 27UL500-W", "ASUS ProArt PA278QV"],
        "electric toothbrush": ["Oral-B iO Series 5", "Philips Sonicare 4100", "Quip Smart"],
        "office chair": ["HON Ignition 2.0", "Autonomous ErgoChair", "Secretlab Titan"],
        "smart thermostat": ["Google Nest Learning", "Ecobee Smart Thermostat", "Amazon Smart Thermostat"],
        "smart lock": ["August WiFi Smart Lock", "Schlage Encode Plus", "Yale Assure Lock 2"],
        "video doorbell": ["Ring Video Doorbell", "Google Nest Doorbell", "Eufy Doorbell"],
    }

    for key, products in anchor_db.items():
        if key in pt:
            return products[:3]

    return anchors


def generate_gold(queries: list[dict]) -> list[dict]:
    """Generate gold sheet entries for all queries."""
    gold = []
    for q in queries:
        query_text = q["query_text"]
        category = q["category"]
        product_type = _extract_product_type(query_text, category)
        budget_ceiling, expected_price_band = _parse_budget(query_text)
        must_have = _extract_must_have(query_text, category)
        must_not_have = _extract_must_not_have(query_text, product_type)
        preferred_retailers = _extract_preferred_retailers(query_text)
        anchor_products = _extract_anchor_products(query_text, product_type, category)

        # Build judge notes based on difficulty
        judge_notes = ""
        if q["difficulty"] == "hard":
            judge_notes = (
                f"Complex query with multiple constraints. "
                f"All specified features should be addressed. "
                f"Budget adherence is critical."
            )
        elif q["difficulty"] == "medium":
            judge_notes = f"Moderate complexity. Key features should be matched."
        else:
            judge_notes = f"Simple query. Product type and budget match are primary."

        gold.append(
            {
                "query_id": q["query_id"],
                "query_text": query_text,
                "category": category,
                "difficulty": q["difficulty"],
                "product_type": product_type,
                "budget_ceiling": budget_ceiling,
                "must_have_features": must_have,
                "must_not_have_terms": must_not_have,
                "preferred_retailers": preferred_retailers,
                "expected_price_band": expected_price_band,
                "anchor_products": anchor_products,
                "judge_notes": judge_notes,
            }
        )
    return gold


def main():
    queries_path = pathlib.Path(__file__).parent / "queries.jsonl"
    gold_path = pathlib.Path(__file__).parent / "gold.jsonl"

    if not queries_path.exists():
        print("queries.jsonl not found — run generate_queries first.")
        return

    queries = []
    with open(queries_path) as f:
        for line in f:
            line = line.strip()
            if line:
                queries.append(json.loads(line))

    gold = generate_gold(queries)

    with open(gold_path, "w") as f:
        for g in gold:
            f.write(json.dumps(g) + "\n")

    print(f"Generated {len(gold)} gold entries → {gold_path}")

    # Stats
    with_budget = sum(1 for g in gold if g["budget_ceiling"] is not None)
    avg_features = sum(len(g["must_have_features"]) for g in gold) / len(gold)
    with_anchors = sum(1 for g in gold if g["anchor_products"])
    print(f"  With budget: {with_budget}/{len(gold)}")
    print(f"  Avg must-have features: {avg_features:.1f}")
    print(f"  With anchor products: {with_anchors}/{len(gold)}")


if __name__ == "__main__":
    main()
