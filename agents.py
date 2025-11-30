import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_tavily import TavilySearch
from langchain_community.tools import DuckDuckGoSearchResults
from dotenv import load_dotenv
from models import Product, ResearchResponse, RetailerPrice
import json
import re

def parse_json_output(text):
    # Remove <think>...</think> blocks
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Find JSON substring (array or object)
    match = re.search(r'(\[.*\]|\{.*\})', text, re.DOTALL)
    if match:
        text = match.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback: try to find the last valid JSON block if multiple exist or if it's messy
        return {}

load_dotenv()

# Initialize LLMs
# Using Gemini for the Manager and Formatting (High reasoning)
gemini_llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", google_api_key=os.getenv("GOOGLE_API_KEY"))

# Using Groq for fast, parallel research tasks
# Tools
tavily_tool = TavilySearch(max_results=5)
ddg_search = DuckDuckGoSearchResults(max_results=10)

class ManagerAgent:
    def __init__(self):
        self.llm = gemini_llm

    def plan_research(self, query: str):
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are the Manager of a shopping assistant team. Your goal is to understand the user's request and direct the research team."),
            ("user", "User Query: {query}\n\nAnalyze this query. Is it a specific product search or a category search? What are the key features to look for?")
        ])
        chain = prompt | self.llm
        return chain.invoke({"query": query}).content

class PrimaryResearcherAgent:
    def __init__(self):
        self.llm = gemini_llm
        self.tool = tavily_tool

    def search_products(self, query: str):
        # First, use the tool to get search results
        search_results = self.tool.invoke({"query": f"best {query} reviews price"})
        
        # Then, use the LLM to parse these results into a list of potential products
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a Primary Researcher. Your goal is to identify the top 5 promising products based on search results. Return ONLY a JSON array of objects with 'name' and 'url' keys. Do not include any <think> tags or explanation."),
            ("user", "User Query: {query}\nSearch Results: {search_results}\n\nList the top 5 products found.")
        ])
        chain = prompt | self.llm | StrOutputParser()
        response_text = chain.invoke({"query": query, "search_results": search_results})
        return parse_json_output(response_text)

class ProductSpecialistAgent:
    def __init__(self):
        self.llm = gemini_llm
        self.tool = tavily_tool

    def analyze_product(self, product_name: str):
        # Deep dive search
        search_results = self.tool.invoke({"query": f"{product_name} detailed review pros cons price"})
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a Product Specialist. Analyze the product deeply. Return ONLY a JSON object matching the Product model. Do not include any <think> tags or explanation."),
            ("user", "Product: {product_name}\nSearch Results: {search_results}\n\nProvide a detailed analysis including price, rating, features, pros, cons, and a 'why to buy' summary.")
        ])
        chain = prompt | self.llm | StrOutputParser()
        response_text = chain.invoke({"product_name": product_name, "search_results": search_results})
        return parse_json_output(response_text)

class ScraperFormatterAgent:
    def __init__(self):
        self.llm = gemini_llm

    def format_results(self, products_data: list, original_query: str):
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are Maven's Recommendation Engine. Create a CONCISE final recommendation (max 3-4 sentences). Use markdown formatting with **bold** for product names and key points. Return ONLY a JSON object with 'final_recommendation' (string in markdown). Do not include any <think> tags or explanation."),
            ("user", "Query: {original_query}\nProduct Reports: {products_data}\n\nProvide a brief, actionable recommendation in markdown format. Highlight the top choice and why.")
        ])
        chain = prompt | self.llm | StrOutputParser()
        response_text = chain.invoke({"original_query": original_query, "products_data": products_data})
        return parse_json_output(response_text)

class ImageSearchAgent:
    """Agent specialized in finding accurate product images"""
    def __init__(self):
        self.llm = gemini_llm
        self.search_tool = ddg_search

    def find_product_images(self, product_name: str, product_url: str = ""):
        """Find high-quality product images using DuckDuckGo image search"""
        try:
            # Search for product images
            search_query = f"{product_name} product official image"
            search_results = self.search_tool.invoke({"query": search_query})
            
            # Use LLM to extract and validate image URLs
            prompt = ChatPromptTemplate.from_messages([
                ("system", """You are an Image Specialist. Extract valid image URLs from search results.
Return ONLY a JSON object with 'image_urls' (array of up to 5 valid image URLs).
Prioritize official product images, high-resolution images, and images from reputable retailers.
Do not include any <think> tags or explanation."""),
                ("user", "Product: {product_name}\nSearch Results: {search_results}\n\nExtract the best product image URLs.")
            ])
            chain = prompt | self.llm | StrOutputParser()
            response_text = chain.invoke({"product_name": product_name, "search_results": str(search_results)})
            result = parse_json_output(response_text)
            
            # Return list of image URLs
            if isinstance(result, dict) and 'image_urls' in result:
                return result['image_urls'][:5]
            return []
        except Exception as e:
            print(f"Error finding images for {product_name}: {e}")
            return []

class PriceComparisonAgent:
    """Agent specialized in finding the best prices across multiple retailers"""
    def __init__(self):
        self.llm = gemini_llm
        self.search_tool = tavily_tool

    def compare_prices(self, product_name: str):
        """Search multiple retailers to find the best price"""
        try:
            # Search across major retailers
            retailers_query = f"{product_name} price buy amazon walmart best buy target ebay"
            search_results = self.search_tool.invoke({"query": retailers_query})
            
            # Use LLM to extract price comparison data
            prompt = ChatPromptTemplate.from_messages([
                ("system", """You are a Price Comparison Specialist. Extract pricing information from multiple retailers.
Return ONLY a JSON object with:
- 'price_comparison': array of objects with 'retailer', 'price', 'url', 'availability'
- 'cheapest_link': URL to the cheapest option found

Prioritize reputable retailers like Amazon, Walmart, Best Buy, Target, etc.
Extract actual numeric prices when possible (e.g., 299.99, $450, etc.).
Do not include any <think> tags or explanation."""),
                ("user", "Product: {product_name}\nSearch Results: {search_results}\n\nFind the best prices from different retailers.")
            ])
            chain = prompt | self.llm | StrOutputParser()
            response_text = chain.invoke({"product_name": product_name, "search_results": str(search_results)})
            result = parse_json_output(response_text)
            
            return {
                'price_comparison': result.get('price_comparison', []),
                'cheapest_link': result.get('cheapest_link', '')
            }
        except Exception as e:
            print(f"Error comparing prices for {product_name}: {e}")
            return {'price_comparison': [], 'cheapest_link': ''}

