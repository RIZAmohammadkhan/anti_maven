import os
from typing import Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_tavily import TavilySearch
from dotenv import load_dotenv
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
gemini_llm = ChatGoogleGenerativeAI(model="gemini-flash-lite-latest", google_api_key=os.getenv("GOOGLE_API_KEY"))

# Using Groq for fast, parallel research tasks
# Tools
tavily_tool = TavilySearch(max_results=3)


def _default_personalization_questions(query: str) -> list[dict[str, Any]]:
    # Keep IDs stable so the frontend can map answers consistently.
    return [
        {
            "id": "budget",
            "question": "What is your budget range (or max price)?",
            "type": "text",
            "options": [],
        },
        {
            "id": "use_case",
            "question": "What will you use it for most? (e.g., travel, gaming, office, gifting)",
            "type": "text",
            "options": [],
        },
        {
            "id": "must_have",
            "question": "List 2–3 must-have features.",
            "type": "text",
            "options": [],
        },
        {
            "id": "nice_to_have",
            "question": "Any nice-to-have features (optional)?",
            "type": "text",
            "options": [],
        },
        {
            "id": "avoid",
            "question": "Anything to avoid? (brands, materials, subscription, size, noise, etc.)",
            "type": "text",
            "options": [],
        },
    ]


def _normalize_questions(raw: Any, query: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return _default_personalization_questions(query)

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        qid = str(item.get("id", "")).strip()
        question = str(item.get("question", "")).strip()
        qtype = str(item.get("type", "text")).strip() or "text"
        options = item.get("options", [])

        if not qid or not question:
            continue
        if qid in seen_ids:
            continue
        if qtype not in {"text", "select"}:
            qtype = "text"
        if not isinstance(options, list) or qtype != "select":
            options = []
        else:
            options = [str(o) for o in options if isinstance(o, (str, int, float))]
            options = options[:8]

        normalized.append({"id": qid, "question": question, "type": qtype, "options": options})
        seen_ids.add(qid)
        if len(normalized) >= 6:
            break

    return normalized or _default_personalization_questions(query)


class PersonalizationAgent:
    """Generate a few clarifying questions to personalize product research."""

    def __init__(self):
        self.llm = gemini_llm

    def generate_questions(self, query: str) -> list[dict[str, Any]]:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You generate short clarifying questions for shopping research.
Return ONLY a JSON array of 4-6 objects with keys:
- id (stable snake_case)
- question (string)
- type (text|select)
- options (array, only if type=select)
No <think> tags. No commentary.""",
                ),
                (
                    "user",
                    "User query: {query}\n\nGenerate the best 4-6 questions to personalize results for this query.",
                ),
            ]
        )
        chain = prompt | self.llm | StrOutputParser()
        response_text = chain.invoke({"query": query})
        raw = parse_json_output(response_text)
        return _normalize_questions(raw, query)

class PrimaryResearcherAgent:
    def __init__(self):
        self.llm = gemini_llm
        self.tool = tavily_tool

    def search_products(self, query: str):
        # First, use the tool to get search results
        search_results = self.tool.invoke({"query": f"best {query} reviews price"})
        
        # Then, use the LLM to parse these results into a list of potential products
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a Primary Researcher. Your goal is to identify the top 3 promising products based on search results. Return ONLY a JSON array of objects with 'name' and 'url' keys. Do not include any <think> tags or explanation."),
            ("user", "User Query: {query}\nSearch Results: {search_results}\n\nList the top 3 products found.")
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
        search_results = self.tool.invoke({"query": f"{product_name} review rating score pros cons price specs"})
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a Product Specialist. Analyze the product deeply. Return ONLY a JSON object matching the Product model.
IMPORTANT: The 'rating' field MUST be a numeric value between 1.0 and 5.0 (e.g., 4.5, 3.8, 4.2).
Extract the actual rating from reviews. If no rating is found in search results, estimate a reasonable rating based on the overall sentiment and quality indicators (3.5-4.5 range).
Do not use null, N/A, or string values for rating. Always provide a numeric decimal rating.
Do not include any <think> tags or explanation."""),
            ("user", "Product: {product_name}\nSearch Results: {search_results}\n\nProvide a detailed analysis including price, rating (MUST be numeric 1.0-5.0), features, pros, cons, and a 'why to buy' summary.")
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


class PriceComparisonAgent:
    """Agent specialized in finding the best prices across multiple retailers"""
    def __init__(self):
        self.llm = gemini_llm
        self.search_tool = tavily_tool

    def compare_prices(self, product_name: str):
        """Search multiple retailers to find the best price"""
        try:
            # Domain-agnostic price search (no retailer bias)
            retailers_query = f"{product_name} price buy"
            search_results = self.search_tool.invoke({"query": retailers_query})
            
            # Use LLM to extract price comparison data
            prompt = ChatPromptTemplate.from_messages([
                ("system", """You are a Price Comparison Specialist. Extract pricing information from multiple retailers.
Return ONLY a JSON object with:
- 'price_comparison': array of objects with 'retailer', 'price', 'url', 'availability'
- 'cheapest_link': URL to the cheapest option found

Do not prefer or prioritize any retailer/domain. Use only what is present in the provided search results.
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

