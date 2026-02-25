import re
from typing import TypedDict, List
from agents import (
    PrimaryResearcherAgent,
    ProductDetailAgent,
    PriceComparisonAgent,
    RecommendationAgent,
)

# ---------------------------------------------------------------------------
# Progress-callback plumbing (unchanged)
# ---------------------------------------------------------------------------
_progress_callback = None


def set_progress_callback(callback):
    global _progress_callback
    _progress_callback = callback


def clear_progress_callback():
    global _progress_callback
    _progress_callback = None


def emit_progress(message: str):
    global _progress_callback
    print(message)
    if _progress_callback:
        try:
            _progress_callback(message)
        except Exception as e:
            print(f"Error in progress callback: {e}")


# ---------------------------------------------------------------------------
# State type
# ---------------------------------------------------------------------------

class ShoppingState(TypedDict):
    query: str
    product_candidates: List[dict]
    detailed_products: List[dict]
    final_response: dict


# ---------------------------------------------------------------------------
# Agent instances
# ---------------------------------------------------------------------------
primary_researcher = PrimaryResearcherAgent()
product_detail_agent = ProductDetailAgent()
price_comparison_agent = PriceComparisonAgent()
recommendation_agent = RecommendationAgent()

MAX_PRODUCTS = 3


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalize_product_data(product: dict) -> dict:
    """Ensure product data matches the Product Pydantic model."""

    # -- name --
    if not product.get("name"):
        product["name"] = "Unknown Product"

    # -- price --
    price = product.get("price")
    if isinstance(price, dict):
        for key in ("starting", "msrp", "price", "lowPrice"):
            if key in price:
                product["price"] = price[key]
                break
        else:
            vals = [v for v in price.values() if isinstance(v, (int, float))]
            product["price"] = vals[0] if vals else "Price varies"
    elif price is None or price == "":
        product["price"] = "Price not available"

    # -- rating (float 1.0-5.0) --
    rating = product.get("rating", 4.0)
    if isinstance(rating, dict):
        rating = rating.get("score", rating.get("value", 4.0))
    if isinstance(rating, str):
        m = re.search(r"(\d+\.?\d*)", rating)
        rating = float(m.group(1)) if m else 4.0
    if rating is None:
        rating = 4.0
    try:
        rating = float(rating)
    except (ValueError, TypeError):
        rating = 4.0
    product["rating"] = max(1.0, min(5.0, rating))

    # -- features --
    features = product.get("features", [])
    if isinstance(features, dict):
        features = [f"{k}: {v}" for k, v in features.items()]
    elif not isinstance(features, list):
        features = []
    product["features"] = features

    # -- pros / cons --
    for key in ("pros", "cons"):
        val = product.get(key, [])
        if not isinstance(val, list):
            product[key] = []

    # -- reviews_count --
    rc = product.get("reviews_count")
    if isinstance(rc, dict):
        product["reviews_count"] = None
    elif isinstance(rc, str):
        m = re.search(r"\d+", rc.replace(",", ""))
        product["reviews_count"] = int(m.group()) if m else None

    # -- urls --
    if not product.get("url"):
        product["url"] = ""
    if not product.get("cheapest_link"):
        product["cheapest_link"] = product.get("url", "")

    # -- image --
    if not product.get("image_url"):
        product["image_url"] = None
    product["image_data"] = None  # legacy field, not used

    # -- drop internal-only keys --
    product.pop("source_urls", None)
    product.pop("search_image", None)

    return product


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_shopping_pipeline(query: str) -> dict:
    """Sequential multi-agent orchestration with progress hooks."""

    state: ShoppingState = {
        "query": query,
        "product_candidates": [],
        "detailed_products": [],
        "final_response": {},
    }

    # ── Step 1: Primary research ───────────────────────────────
    emit_progress(f"Analyzing query '{query[:60]}' ...")
    emit_progress("Searching the web for top products...")

    candidates = primary_researcher.search_products(query)
    if isinstance(candidates, dict) and "products" in candidates:
        candidates = candidates["products"]
    state["product_candidates"] = (
        (candidates or [])[:MAX_PRODUCTS] if isinstance(candidates, list) else []
    )
    emit_progress(
        f"Found {len(state['product_candidates'])} product candidates"
    )

    # ── Step 2: Detail gathering (scrape + analyse) ────────────
    products: list[dict] = []
    for idx, candidate in enumerate(state["product_candidates"], 1):
        name = candidate.get("name", "Unknown")
        url = candidate.get("url", "")
        emit_progress(
            f"Researching {name} ({idx}/{len(state['product_candidates'])}) ..."
        )
        try:
            product = product_detail_agent.gather_details(name, url)

            # Carry forward any search_image from primary step
            if not product.get("image_url") and candidate.get("search_image"):
                product["image_url"] = candidate["search_image"]

            products.append(product)
            img_status = "with image" if product.get("image_url") else "no image yet"
            emit_progress(f"Completed details for {name} ({img_status})")
        except Exception as exc:
            emit_progress(f"Error researching {name}: {exc}")

    # ── Step 3: Price comparison (all products) ────────────────
    emit_progress("Searching for best deals across retailers...")
    for idx, product in enumerate(products, 1):
        name = product.get("name", "Unknown")
        emit_progress(f"Checking prices for {name} ({idx}/{len(products)})")
        try:
            price_data = price_comparison_agent.compare_prices(
                name, product.get("url", "")
            )
            product["price_comparison"] = price_data.get("price_comparison", [])
            product["cheapest_link"] = price_data.get(
                "cheapest_link", product.get("url", "")
            )

            # Update price if we found a concrete one from comparison
            best_price = price_data.get("best_price")
            if best_price and product.get("price") in (
                "Price not available",
                "Price varies",
                None,
                "",
            ):
                product["price"] = best_price

            # Also try to extract a numeric price from the comparison results
            if product.get("price") in (
                "Price not available",
                "Price varies",
                None,
                "",
            ):
                prices_found: list[float] = []
                for rp in product.get("price_comparison", []):
                    pv = rp.get("price", "")
                    try:
                        prices_found.append(
                            float(str(pv).replace("$", "").replace(",", ""))
                        )
                    except (ValueError, TypeError):
                        pass
                if prices_found:
                    product["price"] = f"${min(prices_found):.2f}"

            emit_progress(
                f"Best price for {name}: {product.get('price', 'N/A')}"
            )
        except Exception as exc:
            emit_progress(f"Error comparing prices for {name}: {exc}")

    # ── Step 4: Normalise ──────────────────────────────────────
    normalized = [normalize_product_data(p) for p in products]
    state["detailed_products"] = normalized

    # ── Step 5: Final recommendation ───────────────────────────
    emit_progress("Compiling final recommendation...")
    recommendation = recommendation_agent.recommend(normalized, query)

    state["final_response"] = {
        "products": normalized,
        "final_recommendation": recommendation
        or "Here are the top products found.",
    }
    emit_progress("Research complete!")

    return state


# ---------------------------------------------------------------------------
# Thin wrapper to keep the .invoke() interface expected by main.py
# ---------------------------------------------------------------------------

class SimpleShoppingApp:
    def invoke(self, initial_state):
        query = (
            initial_state.get("query", "") if isinstance(initial_state, dict) else ""
        )
        return run_shopping_pipeline(query)


app = SimpleShoppingApp()
