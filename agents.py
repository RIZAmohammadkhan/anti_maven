import os
import base64
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_tavily import TavilySearch
from dotenv import load_dotenv
from models import Product, ResearchResponse, RetailerPrice
import json
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from PIL import Image, ImageFile
from io import BytesIO

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
tavily_tool = TavilySearch(max_results=3)

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

class ImageSearchAgent:
    """Agent specialized in finding accurate product images"""
    def __init__(self):
        self.llm = gemini_llm
        self.search_tool = tavily_tool
        self.official_domains = [
            'amazon.com', 'bestbuy.com', 'walmart.com', 'target.com',
            'newegg.com', 'bhphotovideo.com', 'apple.com', 'samsung.com',
            'dell.com', 'hp.com', 'lenovo.com', 'microsoft.com', 'sony.com',
            'lg.com', 'costco.com', 'homedepot.com', 'lowes.com'
        ]

    def validate_image(self, image_url: str, product_name: str):
        """Validate image by checking if it loads and extracting metadata"""
        try:
            ImageFile.LOAD_TRUNCATED_IMAGES = True
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(image_url, headers=headers, timeout=10, stream=True)
            response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get('Content-Type', '')
            if 'image' not in content_type.lower():
                return None
            
            # Load image to verify it's valid and get metadata
            image = Image.open(BytesIO(response.content))
            width, height = image.size
            
            # Filter out small images (likely icons/thumbnails)
            if width < 200 or height < 200:
                return None
            
            # Extract image metadata (EXIF, format, mode)
            metadata = {
                'url': image_url,
                'width': width,
                'height': height,
                'format': image.format,
                'mode': image.mode,
                'size_kb': len(response.content) / 1024,
                'aspect_ratio': round(width / height, 2)
            }
            
            # Get alt text and description from URL
            url_lower = image_url.lower()
            metadata['has_product_keywords'] = any(
                keyword in url_lower for keyword in product_name.lower().split()[:3]
            )
            
            return metadata
        except Exception as e:
            print(f"Error validating image {image_url}: {e}")
            return None

    def fetch_image_data_uri(self, image_url: str):
        """Fetch image bytes and return as data URI for stable loading"""
        try:
            if not image_url:
                return ""

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(image_url, headers=headers, timeout=12, stream=True)
            response.raise_for_status()

            content_type = response.headers.get('Content-Type', '')
            if 'image' not in content_type.lower():
                return ""

            content = response.content
            if len(content) > 2_500_000:  # avoid huge payloads in response
                return ""

            ImageFile.LOAD_TRUNCATED_IMAGES = True
            image = Image.open(BytesIO(content))
            width, height = image.size
            if width < 200 or height < 200:
                return ""

            mime = content_type.split(';')[0] if content_type else 'image/jpeg'
            b64 = base64.b64encode(content).decode('ascii')
            return f"data:{mime};base64,{b64}"
        except Exception as e:
            print(f"Error in fetch_image_data_uri for {image_url}: {e}")
            return ""

    def scrape_product_images(self, url: str, product_name: str = ""):
        """Scrape product page to extract and validate image URLs"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            image_candidates = []
            
            # Check if URL is from official/trusted domain
            domain = urlparse(url).netloc.lower()
            is_official = any(official in domain for official in self.official_domains)
            
            # Look for Open Graph images (commonly used for product images)
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                image_candidates.append({
                    'url': og_image['content'],
                    'source': 'og_image',
                    'priority': 10 if is_official else 8
                })
            
            # Look for Twitter card images
            twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
            if twitter_image and twitter_image.get('content'):
                image_candidates.append({
                    'url': twitter_image['content'],
                    'source': 'twitter_image',
                    'priority': 9 if is_official else 7
                })
            
            # Look for structured data (JSON-LD)
            json_ld_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_ld_scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        if 'image' in data:
                            img_data = data['image']
                            if isinstance(img_data, str):
                                image_candidates.append({
                                    'url': img_data,
                                    'source': 'json_ld',
                                    'priority': 10 if is_official else 8
                                })
                            elif isinstance(img_data, list) and img_data:
                                image_candidates.append({
                                    'url': img_data[0],
                                    'source': 'json_ld',
                                    'priority': 10 if is_official else 8
                                })
                except:
                    pass
            
            # Look for product-specific image tags
            product_images = soup.find_all('img', class_=lambda x: x and any(
                keyword in x.lower() for keyword in ['product', 'main', 'primary', 'hero', 'gallery']
            ))
            
            for img in product_images[:5]:
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                alt = img.get('alt', '')
                if src:
                    absolute_url = urljoin(url, src)
                    if absolute_url.startswith('http'):
                        # Higher priority if alt text contains product keywords
                        priority = 7 if is_official else 5
                        if product_name and any(kw in alt.lower() for kw in product_name.lower().split()[:3]):
                            priority += 1
                        
                        image_candidates.append({
                            'url': absolute_url,
                            'source': 'product_img_class',
                            'alt': alt,
                            'priority': priority
                        })
            
            # Look for any large images if we haven't found enough
            if len(image_candidates) < 5:
                all_images = soup.find_all('img')
                for img in all_images:
                    src = img.get('src') or img.get('data-src')
                    alt = img.get('alt', '')
                    if src:
                        absolute_url = urljoin(url, src)
                        # Filter out small icons and logos
                        if absolute_url.startswith('http') and not any(
                            x in absolute_url.lower() for x in ['icon', 'logo', 'sprite', 'pixel', 'blank', 'avatar']
                        ):
                            image_candidates.append({
                                'url': absolute_url,
                                'source': 'img_tag',
                                'alt': alt,
                                'priority': 3 if is_official else 2
                            })
                            if len(image_candidates) >= 15:
                                break
            
            # Remove duplicates
            seen_urls = set()
            unique_candidates = []
            for candidate in image_candidates:
                if candidate['url'] not in seen_urls:
                    seen_urls.add(candidate['url'])
                    unique_candidates.append(candidate)
            
            return unique_candidates
        except Exception as e:
            print(f"Error scraping images from {url}: {e}")
            return []

    def find_product_image(self, product_name: str, product_url: str = "", allow_web_search: bool = False):
        """Find single best product image using web scraping, validation, and metadata analysis"""
        try:
            all_candidates = []
            
            # First, try scraping the product URL if provided
            if product_url and product_url.startswith('http'):
                candidates = self.scrape_product_images(product_url, product_name)
                all_candidates.extend(candidates)
            
            # Optional secondary search to avoid extra outbound calls by default
            if allow_web_search and len(all_candidates) < 5:
                search_query = f"{product_name} site:amazon.com OR site:bestbuy.com OR site:walmart.com OR site:target.com official product"
                search_results = self.search_tool.invoke({"query": search_query})
                if isinstance(search_results, list):
                    for result in search_results[:3]:
                        if isinstance(result, dict) and 'url' in result:
                            candidates = self.scrape_product_images(result['url'], product_name)
                            all_candidates.extend(candidates)
                            if len(all_candidates) >= 12:
                                break
            
            if not all_candidates:
                return ""
            
            # Sort candidates by priority
            all_candidates.sort(key=lambda x: x.get('priority', 0), reverse=True)
            
            # Validate top candidates (check if images load and get metadata)
            validated_images = []
            for candidate in all_candidates[:10]:  # Check top 10
                metadata = self.validate_image(candidate['url'], product_name)
                if metadata:
                    # Combine candidate info with validation metadata
                    metadata['source'] = candidate.get('source', 'unknown')
                    metadata['priority'] = candidate.get('priority', 0)
                    metadata['alt'] = candidate.get('alt', '')
                    
                    # Boost priority for official domains
                    domain = urlparse(metadata['url']).netloc.lower()
                    if any(official in domain for official in self.official_domains):
                        metadata['priority'] += 2
                    
                    # Boost priority for images with product keywords
                    if metadata['has_product_keywords']:
                        metadata['priority'] += 1
                    
                    # Boost priority for large, high-quality images
                    if metadata['width'] >= 800 and metadata['height'] >= 800:
                        metadata['priority'] += 1
                    
                    validated_images.append(metadata)
                
                if len(validated_images) >= 5:
                    break
            
            if not validated_images:
                # Fallback to first candidate without validation
                return all_candidates[0]['url'] if all_candidates else ""
            
            # Pick best validated image with a deterministic score (no LLM)
            def score_image(meta: dict) -> float:
                score = float(meta.get('priority', 0))
                # Reward higher resolution
                if meta.get('width', 0) >= 800 and meta.get('height', 0) >= 800:
                    score += 2.0
                elif meta.get('width', 0) >= 400 and meta.get('height', 0) >= 400:
                    score += 1.0
                # Reward keyword matches
                if meta.get('has_product_keywords'):
                    score += 1.0
                # Penalize extreme aspect ratios
                aspect = meta.get('aspect_ratio', 1)
                if aspect < 0.6 or aspect > 1.8:
                    score -= 1.0
                return score

            validated_images.sort(key=score_image, reverse=True)
            return validated_images[0]['url'] if validated_images else ""
            
        except Exception as e:
            print(f"Error finding image for {product_name}: {e}")
            return ""

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

