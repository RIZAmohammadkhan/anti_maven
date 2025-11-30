from typing import TypedDict, List, Annotated
from langgraph.graph import StateGraph, END
from agents import ManagerAgent, PrimaryResearcherAgent, ProductSpecialistAgent, ScraperFormatterAgent, ImageSearchAgent, PriceComparisonAgent
from models import Product, ResearchResponse

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

# Define State
class ShoppingState(TypedDict):
    query: str
    product_candidates: List[dict]
    detailed_reports: List[dict]
    final_response: dict

# Initialize Agents
manager = ManagerAgent()
primary_researcher = PrimaryResearcherAgent()
product_specialist = ProductSpecialistAgent()
scraper_formatter = ScraperFormatterAgent()
image_search_agent = ImageSearchAgent()
price_comparison_agent = PriceComparisonAgent()

# Define Nodes
def manager_node(state: ShoppingState):
    emit_progress(f" Analyzing query '{state['query'][:50]}...'")
    emit_progress(" Planning research strategy...")
    return {}

def primary_research_node(state: ShoppingState):
    emit_progress("Searching the web for top products...")
    emit_progress("Querying Tavily API for latest results...")
    candidates = primary_researcher.search_products(state['query'])
    # Ensure candidates is a list
    if isinstance(candidates, dict) and 'products' in candidates:
        candidates = candidates['products']
    
    candidate_count = len(candidates) if isinstance(candidates, list) else 0
    emit_progress(f"Found {candidate_count} product candidates")
    return {"product_candidates": candidates}

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
            elif 'best_buy' in price:
                report['price'] = price['best_buy']
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
    if 'reviews_count' in report and isinstance(report['reviews_count'], dict):
        report['reviews_count'] = None
    
    return report

def product_specialist_node(state: ShoppingState):
    emit_progress(f"Analyzing {len(state['product_candidates'])} products in detail...")
    reports = []
    # This loop simulates parallel execution. In a real production env, 
    # we would use map-reduce or parallel execution features of LangGraph.
    for idx, candidate in enumerate(state['product_candidates'], 1):
        try:
            product_name = candidate.get('name', 'Unknown')
            emit_progress(f"Analyzing {product_name} ({idx}/{len(state['product_candidates'])})")
            emit_progress(f"Reading reviews and specs for {product_name}...")
            
            report = product_specialist.analyze_product(candidate['name'])
            normalized_report = normalize_product_data(report, candidate)
            reports.append(normalized_report)
            
            emit_progress(f"Completed analysis for {product_name}")
        except Exception as e:
            emit_progress(f"Error analyzing {candidate.get('name')}: {e}")
            print(f"Error analyzing {candidate.get('name')}: {e}")
    
    emit_progress(f"Finished analyzing all {len(reports)} products")
    return {"detailed_reports": reports}

def image_search_node(state: ShoppingState):
    """Find accurate product image for each product"""
    emit_progress(f"Finding product images for {len(state['detailed_reports'])} products...")
    enriched_reports = []
    for idx, report in enumerate(state['detailed_reports'], 1):
        try:
            product_name = report.get('name', '')
            product_url = report.get('url', '')
            
            emit_progress(f"Searching for {product_name} image ({idx}/{len(state['detailed_reports'])})")
            
            # Find single best image for this product
            image_url = image_search_agent.find_product_image(product_name, product_url)
            
            # Add image to the report
            if image_url:
                report['image_url'] = image_url
                report['image_urls'] = [image_url]  # Keep as single-item list for compatibility
                emit_progress(f"Found image for {product_name}")
            else:
                emit_progress(f"No image found for {product_name}")
            
            enriched_reports.append(report)
        except Exception as e:
            emit_progress(f"Error finding image for {report.get('name')}: {e}")
            print(f"Error finding image for {report.get('name')}: {e}")
            enriched_reports.append(report)
    
    return {"detailed_reports": enriched_reports}

def price_comparison_node(state: ShoppingState):
    """Compare prices across multiple retailers"""
    emit_progress(f"Searching for best deals across retailers...")
    enriched_reports = []
    for idx, report in enumerate(state['detailed_reports'], 1):
        try:
            product_name = report.get('name', '')
            
            emit_progress(f"Checking prices for {product_name} ({idx}/{len(state['detailed_reports'])})")
            
            # Get price comparison data
            price_data = price_comparison_agent.compare_prices(product_name)
            
            # Add price comparison data to the report
            report['price_comparison'] = price_data.get('price_comparison', [])
            report['cheapest_link'] = price_data.get('cheapest_link', '')
            
            # Update the main price if we found a cheaper one
            if price_data.get('price_comparison'):
                prices = []
                for retailer_price in price_data['price_comparison']:
                    try:
                        price_val = retailer_price.get('price', 0)
                        if isinstance(price_val, str):
                            # Extract numeric value from string
                            import re
                            match = re.search(r'[\d,]+\.?\d*', str(price_val).replace(',', ''))
                            if match:
                                prices.append(float(match.group()))
                        elif isinstance(price_val, (int, float)):
                            prices.append(float(price_val))
                    except:
                        continue
                
                if prices:
                    min_price = min(prices)
                    report['price'] = f"${min_price:.2f}"
                    emit_progress(f"Best price for {product_name}: ${min_price:.2f}")
            
            enriched_reports.append(report)
        except Exception as e:
            emit_progress(f"Error comparing prices for {report.get('name')}: {e}")
            print(f"Error comparing prices for {report.get('name')}: {e}")
            enriched_reports.append(report)
    
    return {"detailed_reports": enriched_reports}

def scraper_formatter_node(state: ShoppingState):
    emit_progress("Compiling final recommendation...")
    emit_progress("Generating markdown summary...")
    response = scraper_formatter.format_results(state['detailed_reports'], state['query'])
    final_response = {
        "products": state['detailed_reports'],
        "final_recommendation": response.get("final_recommendation", "Here are the top products found.")
    }
    emit_progress("Research complete!")
    return {"final_response": final_response}

# Build Graph
workflow = StateGraph(ShoppingState)

workflow.add_node("manager", manager_node)
workflow.add_node("primary_researcher", primary_research_node)
workflow.add_node("product_specialist", product_specialist_node)
workflow.add_node("image_search", image_search_node)
workflow.add_node("price_comparison", price_comparison_node)
workflow.add_node("scraper_formatter", scraper_formatter_node)

workflow.set_entry_point("manager")
workflow.add_edge("manager", "primary_researcher")
workflow.add_edge("primary_researcher", "product_specialist")
workflow.add_edge("product_specialist", "image_search")
workflow.add_edge("image_search", "price_comparison")
workflow.add_edge("price_comparison", "scraper_formatter")
workflow.add_edge("scraper_formatter", END)

app = workflow.compile()
