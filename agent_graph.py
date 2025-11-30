from typing import TypedDict, List, Annotated
from langgraph.graph import StateGraph, END
from agents import ManagerAgent, PrimaryResearcherAgent, ProductSpecialistAgent, ScraperFormatterAgent, ImageSearchAgent, PriceComparisonAgent
from models import Product, ResearchResponse

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
    # Here, we just pass through, but we could analyze the query first.
    print(f"Manager received query: {state['query']}")
    return {}

def primary_research_node(state: ShoppingState):
    print("Primary Researcher finding products...")
    candidates = primary_researcher.search_products(state['query'])
    # Ensure candidates is a list
    if isinstance(candidates, dict) and 'products' in candidates:
        candidates = candidates['products']
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
    
    # Normalize rating - extract simple value from complex structures
    if 'rating' in report:
        rating = report['rating']
        if isinstance(rating, dict):
            # Try to extract a single rating value
            if 'score' in rating:
                report['rating'] = rating['score']
            else:
                # Get first numeric value
                for key, val in rating.items():
                    if isinstance(val, (int, float)):
                        report['rating'] = val
                        break
                else:
                    report['rating'] = None
        elif isinstance(rating, str):
            try:
                report['rating'] = float(rating.split('/')[0].strip())
            except:
                report['rating'] = None
        # Numeric values are fine
    else:
        report['rating'] = None
    
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
    print("Product Specialists analyzing...")
    reports = []
    # This loop simulates parallel execution. In a real production env, 
    # we would use map-reduce or parallel execution features of LangGraph.
    for candidate in state['product_candidates']:
        try:
            report = product_specialist.analyze_product(candidate['name'])
            normalized_report = normalize_product_data(report, candidate)
            reports.append(normalized_report)
        except Exception as e:
            print(f"Error analyzing {candidate.get('name')}: {e}")
    return {"detailed_reports": reports}

def image_search_node(state: ShoppingState):
    """Find accurate product images for each product"""
    print("Image Search Agent finding product images...")
    enriched_reports = []
    for report in state['detailed_reports']:
        try:
            product_name = report.get('name', '')
            product_url = report.get('url', '')
            
            # Find images for this product
            image_urls = image_search_agent.find_product_images(product_name, product_url)
            
            # Add images to the report
            report['image_urls'] = image_urls
            if image_urls and len(image_urls) > 0:
                report['image_url'] = image_urls[0]  # Set primary image
            
            enriched_reports.append(report)
        except Exception as e:
            print(f"Error finding images for {report.get('name')}: {e}")
            enriched_reports.append(report)
    
    return {"detailed_reports": enriched_reports}

def price_comparison_node(state: ShoppingState):
    """Compare prices across multiple retailers"""
    print("Price Comparison Agent finding best deals...")
    enriched_reports = []
    for report in state['detailed_reports']:
        try:
            product_name = report.get('name', '')
            
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
            
            enriched_reports.append(report)
        except Exception as e:
            print(f"Error comparing prices for {report.get('name')}: {e}")
            enriched_reports.append(report)
    
    return {"detailed_reports": enriched_reports}

def scraper_formatter_node(state: ShoppingState):
    print("Formatting final response...")
    response = scraper_formatter.format_results(state['detailed_reports'], state['query'])
    final_response = {
        "products": state['detailed_reports'],
        "final_recommendation": response.get("final_recommendation", "Here are the top products found.")
    }
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
