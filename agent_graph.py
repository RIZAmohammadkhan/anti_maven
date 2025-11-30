from typing import TypedDict, List, Annotated
from langgraph.graph import StateGraph, END
from agents import ManagerAgent, PrimaryResearcherAgent, ProductSpecialistAgent, ScraperFormatterAgent
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
workflow.add_node("scraper_formatter", scraper_formatter_node)

workflow.set_entry_point("manager")
workflow.add_edge("manager", "primary_researcher")
workflow.add_edge("primary_researcher", "product_specialist")
workflow.add_edge("product_specialist", "scraper_formatter")
workflow.add_edge("scraper_formatter", END)

app = workflow.compile()
