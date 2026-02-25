import os
import re
import json
import httpx
from typing import Any, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_json_output(text: str) -> Any:
    """Extract JSON from LLM output, stripping think tags and markdown fences."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    match = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
    if match:
        text = match.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _get_required_env(name: str, provider: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required when LLM_PROVIDER={provider}")
    return value


def _create_llm():
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider not in {"gemini", "groq"}:
        raise ValueError("LLM_PROVIDER must be set to either 'gemini' or 'groq'")

    if provider == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise ImportError(
                "Gemini provider selected but dependency is missing. "
                "Install langchain-google-genai."
            ) from exc

        return ChatGoogleGenerativeAI(
            model=_get_required_env("GEMINI_MODEL", provider),
            google_api_key=_get_required_env("GEMINI_API_KEY", provider),
        )

    # groq
    try:
        from langchain_groq import ChatGroq
    except ImportError as exc:
        raise ImportError(
            "Groq provider selected but dependency is missing. "
            "Install langchain-groq."
        ) from exc

    return ChatGroq(
        model=_get_required_env("GROQ_MODEL", provider),
        groq_api_key=_get_required_env("GROQ_API_KEY", provider),
    )


default_llm = _create_llm()

# ---------------------------------------------------------------------------
# Tavily - prefer raw client for richer results, fall back to langchain tool
# ---------------------------------------------------------------------------

_tavily_api_key = os.getenv("TAVILY_API_KEY", "").strip()
if not _tavily_api_key:
    raise ValueError("TAVILY_API_KEY environment variable is required")

_tavily_client = None
try:
    from tavily import TavilyClient

    _tavily_client = TavilyClient(api_key=_tavily_api_key)
except ImportError:
    pass

from langchain_tavily import TavilySearch as _LCTavilySearch

_lc_tavily = _LCTavilySearch(max_results=5)


def tavily_search(
    query: str,
    max_results: int = 5,
    search_depth: str = "advanced",
    include_images: bool = False,
) -> dict:
    """Unified Tavily search returning {results: [...], images: [...]}."""
    if _tavily_client:
        try:
            return _tavily_client.search(
                query=query,
                search_depth=search_depth,
                include_images=include_images,
                max_results=max_results,
            )
        except Exception as e:
            print(f"[tavily-client] error: {e}")

    # Fallback - langchain wrapper (no images, string output)
    try:
        text = _lc_tavily.invoke({"query": query})
        return {"results": [{"content": text, "url": "", "title": ""}], "images": []}
    except Exception as e:
        print(f"[tavily-lc] error: {e}")
        return {"results": [], "images": []}


# ---------------------------------------------------------------------------
# Web-scraping utilities
# ---------------------------------------------------------------------------

_SCRAPER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def scrape_page_metadata(url: str, timeout: float = 10.0) -> dict:
    """Scrape a page for product metadata via og: tags, twitter: tags, and JSON-LD."""
    data: dict = {"image_url": None, "price": None, "title": None, "url": url}
    if not url or not url.startswith("http"):
        return data
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("Warning: beautifulsoup4 not installed - scraping disabled")
        return data

    try:
        with httpx.Client(
            follow_redirects=True, timeout=timeout, headers=_SCRAPER_HEADERS
        ) as client:
            resp = client.get(url)
            if resp.status_code >= 400:
                return data
            soup = BeautifulSoup(resp.text, "lxml")

            # -- Image --
            for prop in ("og:image", "og:image:url"):
                tag = soup.find("meta", property=prop)
                if tag and tag.get("content", "").startswith("http"):
                    data["image_url"] = tag["content"]
                    break
            if not data["image_url"]:
                tag = soup.find("meta", attrs={"name": "twitter:image"})
                if tag and tag.get("content", "").startswith("http"):
                    data["image_url"] = tag["content"]

            # -- Title --
            tag = soup.find("meta", property="og:title")
            if tag and tag.get("content"):
                data["title"] = tag["content"]
            elif soup.title and soup.title.string:
                data["title"] = soup.title.string.strip()

            # -- Price (meta) --
            for prop in ("og:price:amount", "product:price:amount"):
                tag = soup.find("meta", property=prop)
                if tag and tag.get("content"):
                    data["price"] = tag["content"]
                    break

            # -- Price (JSON-LD) --
            if not data["price"]:
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        ld = json.loads(script.string or "")
                        if isinstance(ld, list):
                            ld = ld[0] if ld else {}
                        offers = ld.get("offers", ld.get("Offers", {}))
                        if isinstance(offers, list):
                            offers = offers[0] if offers else {}
                        if isinstance(offers, dict):
                            pv = offers.get("price") or offers.get("lowPrice")
                            if pv:
                                data["price"] = str(pv)
                                break
                    except Exception:
                        continue

            # -- Canonical URL --
            canon = soup.find("link", rel="canonical")
            if canon and canon.get("href"):
                data["url"] = canon["href"]
    except Exception as e:
        print(f"[scraper] {url}: {e}")

    return data


def _search_images_tavily(product_name: str) -> list[str]:
    """Return product image URLs via Tavily include_images."""
    if not _tavily_client:
        return []
    try:
        res = _tavily_client.search(
            query=f"{product_name} product image",
            search_depth="basic",
            include_images=True,
            max_results=3,
        )
        return [
            img
            for img in res.get("images", [])
            if isinstance(img, str) and img.startswith("http")
        ][:5]
    except Exception as e:
        print(f"[tavily-img] {product_name}: {e}")
        return []


def _search_images_ddg(product_name: str, max_results: int = 5) -> list[str]:
    """Return product image URLs via DuckDuckGo (free, no API key)."""
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            hits = list(
                ddgs.images(f"{product_name} product official", max_results=max_results)
            )
            return [
                h["image"] for h in hits if h.get("image", "").startswith("http")
            ]
    except Exception as e:
        print(f"[ddg-img] {product_name}: {e}")
        return []


def find_product_image(
    product_name: str, scraped_image: Optional[str] = None
) -> Optional[str]:
    """Best-effort product image: scraped -> Tavily -> DuckDuckGo."""
    if scraped_image and scraped_image.startswith("http"):
        return scraped_image

    imgs = _search_images_tavily(product_name)
    if imgs:
        return imgs[0]

    imgs = _search_images_ddg(product_name, max_results=3)
    if imgs:
        return imgs[0]

    return None


# ---------------------------------------------------------------------------
# Personalization Agent
# ---------------------------------------------------------------------------


def _default_personalization_questions(query: str) -> list[dict[str, Any]]:
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
            "question": "List 2-3 must-have features.",
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
    seen: set[str] = set()

    for item in raw:
        if not isinstance(item, dict):
            continue
        qid = str(item.get("id", "")).strip()
        question = str(item.get("question", "")).strip()
        qtype = str(item.get("type", "text")).strip() or "text"
        options = item.get("options", [])
        if not qid or not question or qid in seen:
            continue
        if qtype not in {"text", "select"}:
            qtype = "text"
        if not isinstance(options, list) or qtype != "select":
            options = []
        else:
            options = [str(o) for o in options if isinstance(o, (str, int, float))][:8]
        normalized.append(
            {"id": qid, "question": question, "type": qtype, "options": options}
        )
        seen.add(qid)
        if len(normalized) >= 6:
            break

    return normalized or _default_personalization_questions(query)


class PersonalizationAgent:
    """Generate clarifying questions to personalize product research."""

    def __init__(self):
        self.llm = default_llm

    def generate_questions(self, query: str) -> list[dict[str, Any]]:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You generate short clarifying questions for shopping research.\n"
                    "Return ONLY a JSON array of 4-6 objects with keys: "
                    "id (snake_case), question (string), type (text|select), "
                    "options (array, only if select).\n"
                    "No <think> tags. No commentary. No markdown fences.",
                ),
                (
                    "user",
                    "User query: {query}\n\nGenerate 4-6 questions to personalize results.",
                ),
            ]
        )
        chain = prompt | self.llm | StrOutputParser()
        raw = parse_json_output(chain.invoke({"query": query}))
        return _normalize_questions(raw, query)


# ---------------------------------------------------------------------------
# Primary Researcher Agent
# ---------------------------------------------------------------------------


class PrimaryResearcherAgent:
    """Identifies top 3 product candidates from web search.

    Key design: product URLs come directly from Tavily search results,
    never from LLM generation, so buy-links are always real.
    """

    def __init__(self):
        self.llm = default_llm

    def search_products(self, query: str) -> list[dict]:
        # 1. Broad search
        search_data = tavily_search(
            query=f"best {query} 2025 review comparison",
            max_results=5,
            search_depth="advanced",
            include_images=True,
        )
        results = search_data.get("results", [])
        images = search_data.get("images", [])

        # 2. Number each result so the LLM can reference them by index
        numbered = []
        for i, r in enumerate(results):
            numbered.append(
                f"[{i}] Title: {r.get('title', '')}\n"
                f"    URL: {r.get('url', '')}\n"
                f"    Snippet: {r.get('content', '')[:600]}"
            )
        search_text = "\n\n".join(numbered)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a Product Research Specialist.\n"
                    "Identify the top 3 SPECIFIC products from the numbered search results below.\n\n"
                    "RULES:\n"
                    "1. Use FULL product names (e.g. 'Sony WH-1000XM5', not 'Sony headphones').\n"
                    "2. For each product include the search-result index [0]-[4] that mentions it.\n"
                    "3. Return ONLY a JSON array - no <think> tags, no markdown fences, no commentary.\n\n"
                    'Format: [{{"name": "Full Product Name", "source_index": 0}}, ...]',
                ),
                (
                    "user",
                    "User Query: {query}\n\nSearch Results:\n{search_results}",
                ),
            ]
        )
        chain = prompt | self.llm | StrOutputParser()
        raw = parse_json_output(
            chain.invoke({"query": query, "search_results": search_text})
        )
        if not isinstance(raw, list):
            raw = raw.get("products", []) if isinstance(raw, dict) else []

        # 3. Map source_index to real URL
        products: list[dict] = []
        for item in raw[:3]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue

            idx = item.get("source_index")
            url = ""
            if isinstance(idx, int) and 0 <= idx < len(results):
                url = results[idx].get("url", "")

            # Fallback: match first word of product name against titles
            if not url:
                first_word = name.lower().split()[0] if name else ""
                for r in results:
                    if first_word and first_word in r.get("title", "").lower():
                        url = r.get("url", "")
                        break

            products.append({"name": name, "url": url})

        # Attach any Tavily images for later use
        for i, p in enumerate(products):
            if i < len(images):
                p["search_image"] = images[i]

        return products


# ---------------------------------------------------------------------------
# Product Detail Agent (scrape + analyse in one pass)
# ---------------------------------------------------------------------------


class ProductDetailAgent:
    """Gathers comprehensive details for a single product.

    Workflow per product:
      1. Targeted Tavily search (review/specs/price)
      2. Scrape top URLs for og:image, JSON-LD price, canonical URL
      3. Dedicated image search if scraping yielded nothing
      4. LLM analyses collected text and produces structured fields
         (LLM never invents URLs or prices - those come from steps 1-3)
    """

    def __init__(self):
        self.llm = default_llm

    def gather_details(self, product_name: str, initial_url: str = "") -> dict:
        # -- 1. Targeted search --
        search_data = tavily_search(
            query=f"{product_name} detailed review price specs features",
            max_results=5,
            search_depth="advanced",
            include_images=True,
        )
        results = search_data.get("results", [])
        search_images = search_data.get("images", [])
        source_urls = [r["url"] for r in results if r.get("url")]

        # -- 2. Scrape top pages for metadata --
        best_scraped_image: Optional[str] = None
        best_scraped_price: Optional[str] = None
        best_buy_url = initial_url

        urls_to_scrape = ([initial_url] if initial_url else []) + source_urls[:3]
        seen: set[str] = set()

        for url in urls_to_scrape:
            if not url or url in seen:
                continue
            seen.add(url)
            meta = scrape_page_metadata(url)
            if not best_scraped_image and meta.get("image_url"):
                best_scraped_image = meta["image_url"]
            if not best_scraped_price and meta.get("price"):
                best_scraped_price = meta["price"]
            if not best_buy_url:
                best_buy_url = meta.get("url", url)

        # -- 3. Dedicated image search --
        image_url = find_product_image(product_name, best_scraped_image)
        if not image_url and search_images:
            for img in search_images:
                if isinstance(img, str) and img.startswith("http"):
                    image_url = img
                    break

        # -- 4. LLM analysis --
        content_parts = []
        for r in results:
            content_parts.append(
                f"Source: {r.get('url', '')}\n{r.get('content', '')}"
            )
        content_text = "\n\n---\n\n".join(content_parts)[:5000]

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a Product Analyst. Analyse the search content and return "
                    "a JSON object with these EXACT fields:\n"
                    "{{\n"
                    '  "name": "Full product name",\n'
                    '  "price": "numeric string e.g. 299.99 - use the scraped_price if provided",\n'
                    '  "rating": 4.5,\n'
                    '  "reviews_count": 1234,\n'
                    '  "features": ["feature 1", "feature 2"],\n'
                    '  "pros": ["pro 1", "pro 2", "pro 3"],\n'
                    '  "cons": ["con 1", "con 2"],\n'
                    '  "why_to_buy": "1-2 sentence compelling reason"\n'
                    "}}\n\n"
                    "RULES:\n"
                    "- rating MUST be a float 1.0-5.0.\n"
                    "- Extract REAL prices from search text. Prefer scraped_price when available.\n"
                    "- 3-5 features, 3-4 pros, 2-3 cons.\n"
                    "- Do NOT generate URLs.\n"
                    "- No <think> tags, no markdown fences, ONLY the JSON object.",
                ),
                (
                    "user",
                    "Product: {product_name}\n\n"
                    "Scraped Price: {scraped_price}\n\n"
                    "Search Content:\n{content}",
                ),
            ]
        )
        chain = prompt | self.llm | StrOutputParser()
        analysis = parse_json_output(
            chain.invoke(
                {
                    "product_name": product_name,
                    "scraped_price": best_scraped_price or "Not found via scraping",
                    "content": content_text,
                }
            )
        )
        if not isinstance(analysis, dict):
            analysis = {}

        # -- 5. Merge: LLM analysis + real URLs/images/prices --
        return {
            "name": analysis.get("name", product_name),
            "price": best_scraped_price or analysis.get("price", "Price not available"),
            "rating": analysis.get("rating", 4.0),
            "reviews_count": analysis.get("reviews_count"),
            "features": analysis.get("features", []),
            "pros": analysis.get("pros", []),
            "cons": analysis.get("cons", []),
            "why_to_buy": analysis.get("why_to_buy", ""),
            "url": best_buy_url or (source_urls[0] if source_urls else ""),
            "image_url": image_url,
            "source_urls": source_urls[:5],
        }


# ---------------------------------------------------------------------------
# Price Comparison Agent (URLs from search results, never hallucinated)
# ---------------------------------------------------------------------------


class PriceComparisonAgent:
    """Finds best prices across retailers.

    URLs are mapped from Tavily search result indices so they are always real.
    """

    def __init__(self):
        self.llm = default_llm

    def compare_prices(self, product_name: str, existing_url: str = "") -> dict:
        search_data = tavily_search(
            query=f'"{product_name}" buy price',
            max_results=5,
            search_depth="basic",
        )
        results = search_data.get("results", [])

        # Number results and build an index-to-URL map
        url_map: dict[int, str] = {}
        numbered: list[str] = []
        for i, r in enumerate(results):
            url_map[i] = r.get("url", "")
            numbered.append(
                f"[{i}] URL: {r.get('url', '')}\n"
                f"    Title: {r.get('title', '')}\n"
                f"    Snippet: {r.get('content', '')[:350]}"
            )
        search_text = "\n\n".join(numbered)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a Price Comparison Specialist.\n\n"
                    "RULES:\n"
                    "1. Reference results by index [0]-[4].\n"
                    "2. Extract REAL prices from the snippets - never invent prices.\n"
                    "3. Identify retailer from the URL domain "
                    "(amazon.com -> Amazon, bestbuy.com -> Best Buy, etc.).\n"
                    "4. Return ONLY JSON - no <think> tags, no markdown fences.\n\n"
                    "Format:\n"
                    "{{\n"
                    '  "retailers": [\n'
                    '    {{"retailer": "Amazon", "price": "299.99", "source_index": 0}},\n'
                    "    ...\n"
                    "  ],\n"
                    '  "best_price": "279.99",\n'
                    '  "best_source_index": 2\n'
                    "}}",
                ),
                (
                    "user",
                    "Product: {product_name}\n\nSearch Results:\n{search_results}",
                ),
            ]
        )
        chain = prompt | self.llm | StrOutputParser()
        raw = parse_json_output(
            chain.invoke(
                {
                    "product_name": product_name,
                    "search_results": search_text,
                }
            )
        )
        if not isinstance(raw, dict):
            raw = {}

        # Map indices to real URLs
        price_comparison: list[dict] = []
        for item in raw.get("retailers", []):
            if not isinstance(item, dict):
                continue
            idx = item.get("source_index", -1)
            real_url = url_map.get(idx, "")
            if not real_url:
                continue
            price_comparison.append(
                {
                    "retailer": item.get("retailer", "Unknown"),
                    "price": item.get("price", "N/A"),
                    "url": real_url,
                    "availability": "In Stock",
                }
            )

        # Determine cheapest link
        cheapest_link = existing_url
        best_idx = raw.get("best_source_index")
        if isinstance(best_idx, int) and best_idx in url_map:
            cheapest_link = url_map[best_idx]
        elif price_comparison:
            min_price = float("inf")
            for pc in price_comparison:
                try:
                    p = float(str(pc["price"]).replace("$", "").replace(",", ""))
                    if p < min_price:
                        min_price = p
                        cheapest_link = pc["url"]
                except (ValueError, TypeError):
                    pass

        return {
            "price_comparison": price_comparison,
            "cheapest_link": cheapest_link or existing_url,
            "best_price": raw.get("best_price"),
        }


# ---------------------------------------------------------------------------
# Recommendation Agent
# ---------------------------------------------------------------------------


class RecommendationAgent:
    """Generates the final markdown recommendation."""

    def __init__(self):
        self.llm = default_llm

    def recommend(self, products: list[dict], query: str) -> str:
        summaries = []
        for p in products:
            summaries.append(
                f"- **{p.get('name', 'Unknown')}**: "
                f"Price {p.get('price', 'N/A')}, "
                f"Rating {p.get('rating', 'N/A')}/5, "
                f"Pros: {', '.join(p.get('pros', [])[:3])}, "
                f"Cons: {', '.join(p.get('cons', [])[:2])}"
            )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are Maven's Recommendation Engine.\n\n"
                    "RULES:\n"
                    "- Maximum 4-5 sentences.\n"
                    "- Use **bold** for product names and key points.\n"
                    "- Clearly state the top pick and WHY.\n"
                    "- Mention price differences if significant.\n"
                    "- Be specific, not generic platitudes.\n"
                    "- Return ONLY the recommendation text "
                    "(no <think> tags, no markdown fences).",
                ),
                (
                    "user",
                    "Query: {query}\n\nProducts:\n{products}\n\n"
                    "Provide your recommendation.",
                ),
            ]
        )
        chain = prompt | self.llm | StrOutputParser()
        text = chain.invoke({"query": query, "products": "\n".join(summaries)})
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
