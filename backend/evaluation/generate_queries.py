"""
Generate 200 shopping queries for the Maven evaluation benchmark.

Layout: 10 categories × 20 queries each (8 simple, 8 medium, 4 hard).

Run:
    python -m evaluation.generate_queries
"""

import json
import pathlib

# ---------------------------------------------------------------------------
# Query definitions — 10 categories × 20 queries
# ---------------------------------------------------------------------------

CATEGORIES: dict[str, dict[str, list[str]]] = {
    "audio": {
        "simple": [
            "best wireless earbuds under $50",
            "good bluetooth speaker for home",
            "affordable over-ear headphones",
            "cheap wired earbuds with microphone",
            "portable bluetooth speaker under $30",
            "best budget noise cancelling headphones",
            "wireless earbuds for gym workouts",
            "small bluetooth speaker for travel",
        ],
        "medium": [
            "best noise cancelling headphones under $200 for commuting",
            "wireless earbuds with ANC and long battery life under $100",
            "audiophile headphones for mixing and mastering under $300",
            "waterproof bluetooth speaker with 20+ hour battery for camping",
            "open-back headphones under $150 for gaming and music",
            "true wireless earbuds with multipoint connection under $80",
            "portable DAC amp combo for high-impedance headphones under $100",
            "bone conduction headphones for running with IP67 rating",
        ],
        "hard": [
            "best wireless earbuds under $60 with ANC, transparency mode, wireless charging case, and at least 8 hours battery that work well with both Android and iPhone",
            "studio monitor headphones under $250 with flat frequency response, replaceable ear pads, detachable cable, and comfortable for 6+ hour sessions",
            "bluetooth party speaker under $150 with stereo pairing capability, built-in lights, USB-C charging, waterproof IPX7, and at least 15 hours battery",
            "noise cancelling earbuds under $120 specifically for airplane travel with pressure equalization, companion app EQ, and case that fits in shirt pocket",
        ],
    },
    "laptops_computing": {
        "simple": [
            "best laptop under $500 for students",
            "good chromebook for school",
            "affordable laptop for web browsing",
            "cheap laptop for basic office work",
            "lightweight laptop under $400",
            "best budget laptop for college",
            "laptop for kids under $300",
            "reliable laptop for email and word processing",
        ],
        "medium": [
            "best laptop under $1000 for video editing with dedicated GPU",
            "thin and light laptop with 16GB RAM under $800 for programming",
            "2-in-1 convertible laptop with stylus support under $600",
            "gaming laptop under $1200 with RTX 4060 and good thermals",
            "MacBook Air alternative with similar build quality under $900",
            "business laptop with 4G LTE and fingerprint reader under $1000",
            "laptop for data science with 32GB RAM and good Linux support under $1500",
            "ultrabook with OLED display and all-day battery under $1100",
        ],
        "hard": [
            "development laptop under $1200 with 32GB RAM, 1TB SSD, good keyboard, Linux-friendly, USB-A ports, at least 10 hours battery, and under 3.5 pounds",
            "gaming and streaming laptop under $1500 with RTX 4070, 165Hz display, good webcam, Thunderbolt 4, and quiet fan profile option for library use",
            "creative professional laptop under $2000 with color-accurate 4K display covering 100% DCI-P3, 32GB RAM, Thunderbolt, SD card slot, and good speakers",
            "budget workstation laptop under $1800 for CAD and 3D modeling with dedicated GPU, ECC memory support, ISV certifications, and docking station compatibility",
        ],
    },
    "phones_wearables": {
        "simple": [
            "best smartphone under $300",
            "good fitness tracker under $50",
            "affordable smartwatch for Android",
            "cheap phone with good camera",
            "best budget phone for gaming",
            "simple smartwatch for seniors",
            "phone with longest battery life under $400",
            "waterproof fitness band under $40",
        ],
        "medium": [
            "best mid-range phone under $500 with excellent camera and 5G",
            "smartwatch with ECG and blood oxygen monitoring under $250",
            "rugged phone with thermal camera and huge battery under $400",
            "compact phone under 6 inches with flagship performance under $700",
            "fitness tracker with built-in GPS and swim tracking under $100",
            "phone with best video stabilization under $600 for vlogging",
            "smartwatch with offline Spotify and maps for running under $300",
            "dual-SIM phone with expandable storage under $350",
        ],
        "hard": [
            "best camera phone under $800 with optical zoom, night mode, 4K60 video, front-facing portrait mode, and storage of at least 256GB that has good trade-in value",
            "smartwatch under $350 with 5-day battery, always-on display, offline music, NFC payments, sleep tracking with smart alarm, and works with both iOS and Android",
            "phone under $500 with 120Hz AMOLED display, 5000mAh+ battery, 67W+ fast charging, NFC, stereo speakers, and guaranteed 4 years of OS updates",
            "kids' smartwatch under $150 with GPS tracking, SOS button, geofencing, school mode, water resistance, and no social media access",
        ],
    },
    "coffee_kitchen": {
        "simple": [
            "best drip coffee maker under $50",
            "good blender for smoothies",
            "affordable toaster oven",
            "cheap electric kettle",
            "best budget air fryer",
            "simple coffee grinder for home",
            "compact microwave for small kitchen",
            "basic food processor under $40",
        ],
        "medium": [
            "espresso machine with built-in grinder under $500 for beginners",
            "air fryer oven combo with dehydrator and rotisserie under $150",
            "quiet blender for early morning smoothies with at least 1000 watts under $100",
            "pour-over coffee setup for beginners including kettle and dripper under $80",
            "stand mixer with meat grinder attachment under $300",
            "programmable slow cooker with searing function under $80",
            "cold brew coffee maker that can make large batches under $50",
            "induction cooktop with precise temperature control under $100",
        ],
        "hard": [
            "semi-automatic espresso machine under $700 with PID temperature control, 58mm portafilter, steaming wand for latte art, and low counter depth under 15 inches",
            "countertop oven under $250 that can replace a full oven for a small apartment with air fry, convection bake, broil, toast, dehydrate, and fits a 12-inch pizza",
            "high-speed blender under $200 with hot soup capability, personal cup attachment, dishwasher-safe parts, and noise level under 80dB",
            "all-in-one kitchen system under $400 with food processing, blending, cooking, steaming, kneading, and weighing functions with guided recipes",
        ],
    },
    "home_cleaning": {
        "simple": [
            "best robot vacuum under $200",
            "good cordless vacuum for apartments",
            "affordable handheld vacuum",
            "cheap steam mop",
            "best budget stick vacuum",
            "robot vacuum for pet hair",
            "lightweight vacuum for seniors",
            "portable car vacuum cleaner under $30",
        ],
        "medium": [
            "robot vacuum and mop combo with self-emptying dock under $400",
            "cordless vacuum with HEPA filter for allergy sufferers under $300",
            "steam cleaner for grout and tile with multiple attachments under $100",
            "robot vacuum with LiDAR navigation and no-go zones under $350",
            "wet-dry vacuum for garage and workshop under $200",
            "cordless vacuum that converts to handheld under $250",
            "ultrasonic jewelry and glasses cleaner under $40",
            "carpet cleaner machine for deep stain removal under $200",
        ],
        "hard": [
            "robot vacuum with self-emptying, self-washing mop, obstacle avoidance, and app control under $600 that works well on both carpet and hardwood with pets",
            "cordless vacuum under $400 with 60+ minute runtime, wall-mounted charging dock, HEPA filtration, motorized floor head, and pet grooming attachment",
            "whole-home steam cleaning system under $300 with floor steamer, handheld steamer, garment steamer, and window cleaning attachments that heats up in under 30 seconds",
            "commercial-grade carpet extractor under $500 with heated cleaning, large tank capacity, upholstery tool, and stair cleaning capability for a home with 3 large dogs",
        ],
    },
    "gaming": {
        "simple": [
            "best gaming mouse under $30",
            "good gaming keyboard for beginners",
            "affordable gaming headset",
            "cheap gaming controller for PC",
            "best budget webcam for streaming",
            "gaming mousepad large size",
            "wireless gaming mouse under $50",
            "RGB gaming keyboard under $40",
        ],
        "medium": [
            "mechanical gaming keyboard with hot-swappable switches under $80",
            "wireless gaming mouse with less than 1ms latency under $70",
            "gaming headset with spatial audio and detachable mic under $100",
            "capture card for console streaming at 4K passthrough under $150",
            "ergonomic gaming chair with lumbar support under $250",
            "gaming monitor arm for dual 27-inch setup under $50",
            "stream deck or macro pad for content creators under $100",
            "gaming controller with hall effect sticks under $60",
        ],
        "hard": [
            "competitive FPS gaming mouse under $80 with sub-50g weight, optical switches, 8K polling rate support, PTFE feet, and grip tape included",
            "75% mechanical keyboard under $120 with wireless, hot-swap, gasket mount, south-facing LEDs, PBT keycaps, and compatible with VIA/QMK firmware",
            "gaming headset under $150 with planar magnetic drivers, detachable boom mic with noise cancellation, lightweight under 300g, and wired USB-C connection",
            "complete streaming setup under $500 including capture card, microphone with boom arm, cam link or webcam, and green screen that fits in a small room",
        ],
    },
    "monitors_accessories": {
        "simple": [
            "best monitor under $200 for office work",
            "good 27-inch monitor for home",
            "affordable monitor for Mac",
            "cheap second monitor for laptop",
            "best budget ultrawide monitor",
            "monitor with built-in speakers under $150",
            "portable monitor for travel",
            "24-inch monitor for small desk",
        ],
        "medium": [
            "4K monitor under $400 with USB-C and 65W power delivery for MacBook",
            "27-inch 1440p 144Hz gaming monitor with IPS panel under $300",
            "ultrawide 34-inch monitor for productivity under $400",
            "vertical monitor for coding with pivot stand under $200",
            "color-accurate monitor for photo editing covering 99% sRGB under $350",
            "curved 32-inch 4K monitor for mixed work and media under $450",
            "portable USB-C monitor 15.6 inch with built-in battery under $250",
            "dual monitor stand with gas spring arms for 27-inch monitors under $60",
        ],
        "hard": [
            "4K 144Hz gaming monitor under $600 with HDMI 2.1, DisplayPort 1.4, HDR600+, IPS panel, USB hub, and KVM switch for console and PC gaming",
            "ultrawide 38-inch monitor under $800 with Thunderbolt daisy-chaining, 90W PD, built-in KVM, nano-IPS panel, and 3840x1600 resolution",
            "professional color-grading monitor under $1000 with hardware calibration, 10-bit panel, Delta E < 2, USB-C, hood included, and Calman Ready",
            "triple monitor setup under $700 total with three matching 24-inch 1080p IPS displays and a triple monitor stand that clamps to standard desks",
        ],
    },
    "personal_care": {
        "simple": [
            "best electric toothbrush under $50",
            "good hair dryer under $40",
            "affordable electric shaver for men",
            "cheap hair straightener",
            "best budget water flosser",
            "electric trimmer for beard grooming",
            "simple facial cleansing brush",
            "compact travel hair dryer under $30",
        ],
        "medium": [
            "electric toothbrush with pressure sensor and app tracking under $100",
            "hair dryer with ionic technology and diffuser attachment under $80",
            "rotary shaver with wet/dry capability and pop-up trimmer under $70",
            "IPL hair removal device for home use under $200",
            "water flosser with multiple tips and countertop reservoir under $60",
            "hair clipper set with ceramic blades and guide combs under $50",
            "LED light therapy mask for acne treatment under $100",
            "heated eyelash curler with multiple temperature settings under $30",
        ],
        "hard": [
            "premium sonic toothbrush under $120 with UV sanitizing case, 5+ brushing modes, pressure sensor, smart timer, travel case, and 3-week battery life",
            "professional-grade hair dryer under $150 with brushless motor, ionic and infrared technology, multiple speed/heat settings, concentrator and diffuser nozzles, and lightweight under 1.5 pounds",
            "complete men's grooming kit under $100 with body trimmer, beard trimmer, nose/ear trimmer, foil shaver, all waterproof, with charging stand and travel case",
            "at-home microcurrent facial device under $200 with FDA clearance, app-guided routines, five intensity levels, and conductive gel included",
        ],
    },
    "home_office": {
        "simple": [
            "best desk lamp for studying",
            "good office chair under $200",
            "affordable standing desk converter",
            "cheap webcam for video calls",
            "best budget desk organizer",
            "wireless keyboard and mouse combo",
            "comfortable mouse pad with wrist rest",
            "USB hub for laptop under $20",
        ],
        "medium": [
            "ergonomic office chair with adjustable lumbar support under $400",
            "electric standing desk with programmable presets under $500",
            "monitor light bar that doesn't cause screen glare under $50",
            "mechanical keyboard for typing with quiet switches under $80",
            "noise cancelling USB microphone for video calls under $80",
            "desk shelf riser with USB ports and monitor stand under $40",
            "document scanner for home office that handles double-sided under $300",
            "ergonomic vertical mouse for carpal tunnel prevention under $40",
        ],
        "hard": [
            "complete home office desk setup under $800 including electric sit-stand desk, ergonomic chair with headrest, and cable management solution",
            "video conferencing kit under $300 with 4K webcam, USB condenser microphone with noise cancellation, ring light, and green screen",
            "electric standing desk under $600 with bamboo top, built-in wireless charging, USB-C hub, cable tray, and anti-fatigue mat included",
            "ergonomic office chair under $500 with mesh back, adjustable headrest, 4D armrests, seat depth adjustment, and 10-year warranty with good reviews for 6-foot tall users",
        ],
    },
    "smart_home": {
        "simple": [
            "best smart bulb under $15",
            "good smart plug for beginners",
            "affordable video doorbell",
            "cheap smart home speaker",
            "best budget smart thermostat",
            "smart light strip for room",
            "wireless security camera for home",
            "smart door lock under $100",
        ],
        "medium": [
            "smart thermostat with room sensors and energy reports under $200",
            "outdoor security camera with color night vision and local storage under $100",
            "smart lock with fingerprint reader and auto-lock under $200",
            "mesh WiFi system for 3000 sq ft home with smart home hub under $300",
            "smart blinds that work with Alexa and Google Home under $150",
            "video doorbell with package detection and no monthly fee under $150",
            "smart smoke and CO detector with phone alerts under $100",
            "smart irrigation controller with weather-based scheduling under $80",
        ],
        "hard": [
            "whole-home smart security system under $500 with doorbell camera, 2 outdoor cameras, motion sensors, door sensors, and no monthly fee with local storage and phone alerts",
            "smart home starter kit under $300 with hub, smart thermostat, 4 smart bulbs, 2 smart plugs, and motion sensor that all work together on one app without subscription",
            "smart lock under $250 with fingerprint, PIN, key card, app control, auto-lock, built-in camera, Works with Matter, and retrofit installation without changing deadbolt",
            "outdoor smart lighting system under $200 with pathway lights, spotlight, and floodlight controllable by voice and app with scheduling, motion activation, and color changing",
        ],
    },
}


def generate() -> list[dict]:
    """Generate all 200 queries and return as list of dicts."""
    queries: list[dict] = []
    for category, difficulty_map in CATEGORIES.items():
        for difficulty, query_list in difficulty_map.items():
            for idx, query_text in enumerate(query_list, 1):
                query_id = f"{category}_{difficulty}_{idx:02d}"
                queries.append(
                    {
                        "query_id": query_id,
                        "query_text": query_text,
                        "category": category,
                        "difficulty": difficulty,
                    }
                )
    return queries


def main():
    out_path = pathlib.Path(__file__).parent / "queries.jsonl"
    queries = generate()
    with open(out_path, "w") as f:
        for q in queries:
            f.write(json.dumps(q) + "\n")
    print(f"Generated {len(queries)} queries → {out_path}")

    # Verify counts
    from collections import Counter

    cat_counts = Counter(q["category"] for q in queries)
    diff_counts = Counter(q["difficulty"] for q in queries)
    print(f"Categories: {dict(cat_counts)}")
    print(f"Difficulties: {dict(diff_counts)}")


if __name__ == "__main__":
    main()
