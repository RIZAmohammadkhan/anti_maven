from typing import TypedDict, List
from agents import (
    PrimaryResearcherAgent,
    ProductSpecialistAgent,
    ScraperFormatterAgent,
    PriceComparisonAgent,
)

# Global progress callback registry
_progress_callback = None

def set_progress_callback(callback):
    """Set the global progress callback function"""
    global _progress_callback
    _progress_callback = callback

def clear_progress_callback():
    """Clear the global progress callback"""
    global _progress_callback
    _progress_callback = None

def emit_progress(message: str):
    """Emit progress message to UI if callback is available"""
    global _progress_callback
    # Always print for console logging
    print(message)
    # Send to UI if callback is set
    if _progress_callback:
        try:
            _progress_callback(message)
        except Exception as e:
            print(f"Error in progress callback: {e}")

class ShoppingState(TypedDict):
    query: str
    product_candidates: List[dict]
    detailed_reports: List[dict]
    final_response: dict


# Initialize agents (lightweight, sequential orchestration)
primary_researcher = PrimaryResearcherAgent()
product_specialist = ProductSpecialistAgent()
scraper_formatter = ScraperFormatterAgent()
price_comparison_agent = PriceComparisonAgent()

# Tunable limits to reduce external calls
MAX_PRODUCTS = 3
MAX_PRICE_CHECKS = 2

def normalize_product_data(report, candidate):
    """Normalize product data to match the Product model schema"""
    # Unwrap if wrapped in 'product' key
    if 'product' in report and isinstance(report['product'], dict):
        report = report['product']
    
    # Handle 'product' field as 'name'
    if 'product' in report and 'name' not in report:
        report['name'] = report.pop('product')
    
    # Ensure name exists
    if 'name' not in report:
        report['name'] = candidate.get('name', 'Unknown Product')
    
    # Merge url/image if missing in report but present in candidate
    if 'url' not in report or not report['url']:
        report['url'] = candidate.get('url', '')
    
    # Normalize price - extract simple value from complex structures
    if 'price' in report:
        price = report['price']
        if isinstance(price, dict):
            # Try to extract a single price value
            if 'starting' in price:
                report['price'] = price['starting']
            elif 'msrp' in price:
                report['price'] = price['msrp']
            else:
                # Get first numeric value
                for key, val in price.items():
                    if isinstance(val, (int, float)):
                        report['price'] = val
                        break
                else:
                    report['price'] = "Price varies"
        elif isinstance(price, str):
            # Keep string as-is
            pass
        # Numeric values are fine
    else:
        report['price'] = "Price not available"
    
    # Normalize rating - extract simple value from complex structures and ensure it's valid
    if 'rating' in report:
        rating = report['rating']
        if isinstance(rating, dict):
            # Try to extract a single rating value
            if 'score' in rating:
                report['rating'] = float(rating['score'])
            else:
                # Get first numeric value
                for key, val in rating.items():
                    if isinstance(val, (int, float)):
                        report['rating'] = float(val)
                        break
                else:
                    report['rating'] = 4.0  # Default to reasonable rating
        elif isinstance(rating, str):
            try:
                # Try to extract number from string like "4.5/5" or "4.5 stars"
                import re
                match = re.search(r'(\d+\.?\d*)', rating)
                if match:
                    report['rating'] = float(match.group(1))
                else:
                    report['rating'] = 4.0
            except:
                report['rating'] = 4.0
        elif isinstance(rating, (int, float)):
            report['rating'] = float(rating)
        elif rating is None:
            report['rating'] = 4.0  # Default rating if None
        # Ensure rating is between 1.0 and 5.0
        if isinstance(report['rating'], (int, float)):
            report['rating'] = max(1.0, min(5.0, float(report['rating'])))
    else:
        report['rating'] = 4.0  # Default rating if missing
    
    # Normalize features - convert dict to list
    if 'features' in report:
        features = report['features']
        if isinstance(features, dict):
            report['features'] = [f"{k}: {v}" for k, v in features.items()]
        elif not isinstance(features, list):
            report['features'] = []
    else:
        report['features'] = []
    
    # Ensure pros and cons are lists
    if 'pros' not in report or not isinstance(report['pros'], list):
        report['pros'] = []
    if 'cons' not in report or not isinstance(report['cons'], list):
        report['cons'] = []
    
    # Ensure reviews_count is valid
    if 'reviews_count' in report:
        reviews = report['reviews_count']
        if isinstance(reviews, dict):
            report['reviews_count'] = None
        elif isinstance(reviews, str):
            try:
                import re
                match = re.search(r"\d+", reviews.replace(',', ''))
                report['reviews_count'] = int(match.group()) if match else None
            except Exception:
                report['reviews_count'] = None
    
    return report

def run_shopping_pipeline(query: str) -> dict:
    """Sequential multi-agent orchestration with progress hooks"""
    state: ShoppingState = {
        "query": query,
        "product_candidates": [],
        "detailed_reports": [],
        "final_response": {},
    }

    emit_progress(f"Analyzing query '{query[:50]}...'")

    emit_progress(f"Searching the web for top products...")
    candidates = primary_researcher.search_products(query)
    if isinstance(candidates, dict) and "products" in candidates:
        candidates = candidates["products"]
    state["product_candidates"] = (candidates or [])[:MAX_PRODUCTS] if isinstance(candidates, list) else []
    emit_progress(f"Found {len(state['product_candidates'])} product candidates (capped at {MAX_PRODUCTS})")

    emit_progress(f"Analyzing {len(state['product_candidates'])} products in detail...")
    reports = []
    for idx, candidate in enumerate(state["product_candidates"], 1):
        product_name = candidate.get("name", "Unknown")
        try:
            emit_progress(f"Analyzing {product_name} ({idx}/{len(state['product_candidates'])})")
            report = product_specialist.analyze_product(product_name)
            normalized_report = normalize_product_data(report, candidate)
            reports.append(normalized_report)
            emit_progress(f"Completed analysis for {product_name}")
        except Exception as exc:
            emit_progress(f"Error analyzing {product_name}: {exc}")
    state["detailed_reports"] = reports
    emit_progress(f"Finished analyzing all {len(reports)} products")

    emit_progress("Image lookup skipped per request; omitting images from results.")
    for report in state["detailed_reports"]:
        report["image_url"] = None
        report["image_data"] = None

    emit_progress("Searching for best deals across retailers (limited)...")
    for idx, report in enumerate(state["detailed_reports"], 1):
        product_name = report.get("name", "")
        if idx > MAX_PRICE_CHECKS:
            emit_progress(f"Skipping price comparison for {product_name} to reduce requests")
            report["price_comparison"] = []
            report["cheapest_link"] = report.get("url", "")
            continue

        emit_progress(f"Checking prices for {product_name} ({idx}/{len(state['detailed_reports'])})")
        try:
            price_data = price_comparison_agent.compare_prices(product_name)
            report["price_comparison"] = price_data.get("price_comparison", [])
            report["cheapest_link"] = price_data.get("cheapest_link", "")

            prices = []
            for retailer_price in report["price_comparison"]:
                price_val = retailer_price.get("price", 0)
                if isinstance(price_val, str):
                    import re

                    match = re.search(r"[\d,]+\.?\d*", price_val.replace(",", ""))
                    if match:
                        prices.append(float(match.group()))
                elif isinstance(price_val, (int, float)):
                    prices.append(float(price_val))
            if prices:
                min_price = min(prices)
                report["price"] = f"${min_price:.2f}"
                emit_progress(f"Best price for {product_name}: ${min_price:.2f}")
        except Exception as exc:
            emit_progress(f"Error comparing prices for {product_name}: {exc}")

    emit_progress("Compiling final recommendation...")
    response = scraper_formatter.format_results(state["detailed_reports"], state["query"])
    state["final_response"] = {
        "products": state["detailed_reports"],
        "final_recommendation": response.get(
            "final_recommendation", "Here are the top products found."
        ),
    }
    emit_progress("Research complete!")

    return state


class SimpleShoppingApp:
    """Lightweight wrapper to maintain the .invoke interface used by FastAPI"""

    def invoke(self, initial_state: ShoppingState):
        query = initial_state.get("query", "") if isinstance(initial_state, dict) else ""
        return run_shopping_pipeline(query)


app = SimpleShoppingApp()
